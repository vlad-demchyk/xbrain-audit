"""Where a signed-in browser session for a site is kept, and who may read it.

Half of what is worth auditing is behind a login, and the only way in that
does not involve this tool handling anybody's credentials is the obvious one:
a person signs in themselves, in a real browser window, and the run reuses
what that browser was given. QtWebEngine stores that for us - a named,
persistent profile with `ForcePersistentCookies` is the same mechanism a
browser profile is - so this module is only about *where* it lives, *whose*
it is, and how to get rid of it.

Three rules, and none of them is optional:

* **Nothing here ever reaches a report, a log or a run folder.** What a
  document may say is "this run was signed in as a session for host X". The
  values are the session; printing them is handing the session over.
* **One profile per host.** A session for `staging.example.com` has no
  business travelling to `example.com`, and a single shared profile would
  mean the last site signed into decides who the next scan is.
* **It can be forgotten, and the person can see that it exists.** A tool
  that quietly keeps a way into somebody's account is not a tool anybody
  should install. `forget()` is the whole answer, and `known_hosts()` is how
  a surface shows what there is to forget.

**No credentials are stored, ever.** This tool never sees a password: the
sign-in happens in the browser window, against the site's own form, and what
survives is what the site chose to give that browser.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import config

#: Where the profiles live. Under the app's own config directory rather than
#: anywhere near a repository: a checkout gets committed, and this must not
#: be a thing that can be committed by accident.
_DIRNAME = "sessions"

#: The pre-hash directory-name rule, retained only to discover old profiles.
_SAFE = re.compile(r"[^a-z0-9._-]+")
_PROFILE = "profile.json"
#: How `known_hosts()` names a profile whose owner it could not prove. It is
#: not a host and never resolves to one, but `forget()` takes it back.
_LEGACY_PREFIX = "legacy:"
_PROFILE_VERSION = 1
_PROFILE_PREFIX = "profile-"


def _canonical_host(value: str) -> str:
    """Return one canonical hostname with its optional explicit port."""
    text = (value or "").strip()
    # A bare host may have a path, but filesystem-looking control inputs must
    # never be interpreted as one.
    if (not text or text in {".", ".."}
            or text.startswith(("./", "../", "/"))):
        raise ValueError("invalid session host")
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("invalid session host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("invalid session host")
    try:
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid session host") from exc
    if not hostname or "/" in hostname or "\\" in hostname:
        raise ValueError("invalid session host")

    try:
        canonical_name = ipaddress.ip_address(hostname).compressed.lower()
    except ValueError:
        try:
            canonical_name = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("invalid session host") from exc
        labels = canonical_name.split(".")
        if (len(canonical_name) > 253
                or any(not label or len(label) > 63
                       or label.startswith("-") or label.endswith("-")
                       or not re.fullmatch(r"[a-z0-9-]+", label)
                       for label in labels)):
            raise ValueError("invalid session host")

    display_name = (f"[{canonical_name}]" if ":" in canonical_name
                    else canonical_name)
    return f"{display_name}:{port}" if port is not None else display_name


def host_of(url: str) -> str:
    """The host a session belongs to, or "" if there is not one.

    The port is part of it: `localhost:3000` and `localhost:8080` are two
    different applications on nearly every developer's machine.
    """
    try:
        return _canonical_host(url)
    except ValueError:
        return ""


def _slug(host: str) -> str:
    """The legacy, lossy profile name used before hashed identities."""
    return _SAFE.sub("-", (host or "").lower()).strip("-")


def _profile_name(host: str) -> str:
    """A collision-resistant profile name for a canonical host and port."""
    canonical = _canonical_host(host)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_PROFILE_PREFIX}{digest}"


def sessions_root() -> Path:
    """The directory holding every profile, created 0700 on first use."""
    root = Path(config.config_file()).parent / _DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        # A filesystem that does not do POSIX modes (a mounted share) is not
        # a reason to refuse to work; it is a reason not to pretend the
        # permission was set.
        pass
    return root


def _direct_child(root: Path, name: str) -> Path:
    """Resolve one profile child without ever following it outside root."""
    candidate = root / name
    path = candidate.resolve(strict=False)
    if path == root or path.parent != root or candidate.is_symlink():
        raise ValueError("session profile escapes the sessions directory")
    return path


def _profile_has_data(path: Path) -> bool:
    try:
        return (not path.is_symlink() and path.is_dir()
                and any(entry.name != _PROFILE for entry in path.iterdir()))
    except OSError:
        return False


def _read_profile_host(path: Path) -> str:
    """Return the proven owner of a profile, or ``""`` if it is unknown."""
    try:
        with open(path / _PROFILE, encoding="utf-8") as handle:
            data = json.load(handle)
        if (not isinstance(data, Mapping)
                or data.get("version") != _PROFILE_VERSION):
            return ""
        return _canonical_host(data.get("host", ""))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass

    # Cookie-store v2 originally had no profile metadata. A top-level owner
    # added by this version is authoritative. An exact host-only cookie also
    # proves an old no-port profile, but a cookie domain cannot prove a port.
    try:
        with open(path / _COOKIES, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, Mapping) and isinstance(data.get("host"), str):
            return _canonical_host(data["host"])
        records = data.get("cookies") if isinstance(data, Mapping) else None
        owners = {
            str(record.get("domain", "")).lstrip(".").lower()
            for record in records or []
            if isinstance(record, Mapping) and record.get("host_only") is True
        }
        if len(owners) == 1:
            owner = owners.pop()
            canonical = _canonical_host(owner)
            if ":" not in canonical:
                return canonical
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return ""


def _write_profile_metadata(path: Path, host: str) -> None:
    metadata = path / _PROFILE
    descriptor = os.open(metadata, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"version": _PROFILE_VERSION, "host": host}, handle)


def _legacy_profile(root: Path, host: str) -> Path | None:
    name = _slug(host)
    if name in {"", ".", ".."}:
        return None
    try:
        return _direct_child(root, name)
    except ValueError:
        return None


def profile_dir(host: str, create: bool = False) -> Path:
    """Where this host's browser profile lives."""
    canonical = _canonical_host(host)
    name = _profile_name(canonical)
    root = sessions_root().resolve()
    path = _direct_child(root, name)

    if path.is_dir():
        owner = _read_profile_host(path)
        if owner and owner != canonical:
            raise ValueError("session profile belongs to another host")
    else:
        legacy = _legacy_profile(root, canonical)
        if (legacy is not None and legacy.is_dir()
                and _read_profile_host(legacy) == canonical):
            _write_profile_metadata(legacy, canonical)
            legacy.rename(path)

    if create:
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass
        if not (path / _PROFILE).is_file():
            _write_profile_metadata(path, canonical)
    return path


def has_session(host: str) -> bool:
    """Has a sign-in for this host been confirmed with Done?

    The browser profile is not the proof. QtWebEngine writes it the moment
    the sign-in page sets anything at all - a consent cookie, a tracker, a
    half-finished login - and a person who pressed Cancel must not be told
    they are signed in, nor have the crawl use what they walked away from.
    Done writes the marker (`mark_signed_in`) and the fetcher's copy of the
    cookies, so either file is what makes a session - the marker alone for a
    site read by the browser (`SESSION_BROWSER`), whose copy may be empty.
    """
    try:
        path = profile_dir(host)
    except ValueError:
        return False
    if not _profile_has_data(path):
        return False
    for name in (_COOKIES, _SIGNED_IN):
        marker = path / name
        if marker.is_file() and not marker.is_symlink():
            return True
    return False


def known_hosts() -> list:
    """Every host with a stored session, so a surface can list them."""
    root = sessions_root()
    if not root.is_dir():
        return []
    hosts = []
    for entry in list(root.iterdir()):
        if entry.is_symlink():
            hosts.append(_LEGACY_PREFIX + entry.name)
            continue
        if not _profile_has_data(entry):
            continue
        owner = _read_profile_host(entry)
        if owner and entry.name == _profile_name(owner):
            hosts.append(owner)
        elif owner:
            # Reading the owner proved this legacy directory can be migrated.
            migrated = profile_dir(owner)
            if _profile_has_data(migrated):
                hosts.append(owner)
        else:
            # It remains visible and removable, but is never attached to a
            # guessed host because the old slug may represent several inputs.
            hosts.append(_LEGACY_PREFIX + entry.name)
    return sorted(set(hosts))


def _forget_legacy(name: str) -> bool:
    """Remove one entry `known_hosts()` listed without being able to name it.

    Such an entry has no host to resolve, so the ordinary path cannot reach
    it - and an entry a person can see in the list but cannot remove is the
    one thing this whole feature promises not to be.
    """
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        return False
    root = sessions_root().resolve()
    candidate = root / name
    if candidate.is_symlink():
        # A symlink is what `_direct_child` refuses and what `known_hosts()`
        # lists as legacy. Remove the link, never what it points at.
        candidate.unlink(missing_ok=True)
        return True
    try:
        path = _direct_child(root, name)
    except ValueError:
        return False
    if not path.is_dir():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


def forget(host: str) -> bool:
    """Delete this host's profile. `True` if there was one to delete.

    Also accepts a `legacy:` token exactly as `known_hosts()` printed it,
    because that list is what a person reads before deciding what to remove.
    """
    text = (host or "").strip()
    if text.startswith(_LEGACY_PREFIX):
        return _forget_legacy(text[len(_LEGACY_PREFIX):])
    try:
        path = profile_dir(host)
    except ValueError:
        return False
    if not path.is_dir():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


def forget_all() -> int:
    """Delete every stored session, and say how many there were."""
    root = sessions_root().resolve()
    entries = list(root.iterdir())
    count = sum(_profile_has_data(entry) or entry.is_symlink()
                for entry in entries)
    for entry in entries:
        if entry.is_symlink():
            entry.unlink(missing_ok=True)
        elif entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
    return count


#: The cookies a fetch needs, written beside the browser profile.
#:
#: Two clients read one site: QtWebEngine renders the pages, and `requests`
#: fetches them for the crawl. They share no storage, so a sign-in performed
#: in the browser leaves the fetcher looking at the login form - the two
#: halves of one run disagreeing about who is asking. This file is the
#: bridge, and it is the one genuinely sensitive thing this tool writes:
#: 0600, beside the profile, never logged, never in a report, and deleted by
#: `forget()` along with everything else for that host.
_COOKIES = "cookies.json"
_COOKIE_STORE_VERSION = 2
_SAME_SITE_VALUES = {"Default", "None_", "Lax", "Strict"}


def cookies_path(host: str) -> Path:
    return profile_dir(host) / _COOKIES


def _cookie_domain(host: str) -> str:
    """Hostname without a port, suitable for a cookie scope."""
    parsed = urlparse(host if "://" in host else f"https://{host}")
    return (parsed.hostname or "").lower()


def _cookie_records(host: str, cookies) -> list[dict]:
    """Normalize the current store and the old ``{name: value}`` format."""
    fallback_domain = _cookie_domain(host)
    if isinstance(cookies, Mapping):
        stored = cookies.get("cookies")
        if isinstance(stored, list):
            values = stored
        else:
            values = [
                {
                    "name": name,
                    "value": value,
                    "domain": fallback_domain,
                    "path": "/",
                    "host_only": True,
                }
                for name, value in cookies.items()
            ]
    elif isinstance(cookies, (list, tuple)):
        values = cookies
    else:
        return []

    records: list[dict] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        name = str(value.get("name") or "")
        if not name:
            continue
        domain = str(value.get("domain") or fallback_domain).strip().lower()
        if not domain:
            continue
        path = str(value.get("path") or "/")
        if not path.startswith("/"):
            path = "/"
        same_site = str(value.get("same_site") or "Default")
        if same_site not in _SAME_SITE_VALUES:
            same_site = "Default"
        expires = value.get("expires")
        try:
            expires = int(expires) if expires is not None else None
        except (TypeError, ValueError):
            expires = None
        records.append({
            "name": name,
            "value": str(value.get("value") or ""),
            "domain": domain,
            "path": path,
            "secure": bool(value.get("secure", False)),
            "http_only": bool(value.get("http_only", False)),
            "same_site": same_site,
            "expires": expires,
            "host_only": bool(value.get(
                "host_only", not domain.startswith("."))),
        })
    return records


def _bare_host(host_or_url: str) -> str:
    text = (host_or_url or "").strip()
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.hostname or "").lower().rstrip(".")


#: SharePoint Online's session cookies: `FedAuth` on the tenant's host,
#: `rtFa` on `.sharepoint.com`, both HttpOnly. They never leave the browser
#: profile: a SharePoint site is read *by* the profile (`SESSION_BROWSER`,
#: `audit.browser_fetch`), so the fetcher's copy has no use for them, and a
#: file holding them is a copy of the person's session on disk.
SHAREPOINT_SESSION_COOKIES = ("FedAuth", "rtFa")


def cookie_is_for_fetcher(site_host: str, cookie_domain: str,
                          name: str = "") -> bool:
    """Is a cookie set on `cookie_domain` in the scope of `site_host`?

    Yes for the site's own host and its parent domains (what a browser would
    send there), never for an identity provider, and for SharePoint Online
    only the tenant's own hosts: `.sharepoint.com` is every tenant's parent.
    A Microsoft sign-in cookie (`ESTSAUTH*` on `login.microsoftonline.com`)
    is the person's whole Microsoft account; the browser profile keeps it
    for a silent sign-in, the fetcher's copy never does. `name` is accepted
    for callers that have one; scope does not depend on it.
    """
    from audit.authwall import is_identity_provider_host
    from project_profile import sharepoint_tenant_hosts

    host = _bare_host(site_host)
    domain = (cookie_domain or "").strip().lower().lstrip(".")
    if not host or not domain:
        return False
    if is_identity_provider_host(domain):
        return False
    tenant_hosts = sharepoint_tenant_hosts(host)
    if tenant_hosts:
        return domain in tenant_hosts
    if host == domain:
        return True  # `localhost` included: a host is its own scope
    # A parent domain, but never a bare top-level one.
    return "." in domain and host.endswith("." + domain)


def cookies_for_fetcher(site_host: str, records) -> list:
    """The records the fetcher's copy (`cookies.json`) of `site_host` gets.

    Those in scope (`cookie_is_for_fetcher`); for SharePoint Online also
    never an HttpOnly cookie and never a session cookie by name - that
    session stays in the browser profile (`SHAREPOINT_SESSION_COOKIES`).
    """
    from project_profile import sharepoint_tenant

    host = _bare_host(site_host)
    sharepoint = bool(sharepoint_tenant(host))
    kept = []
    for record in records or ():
        domain = str(record.get("domain", "") or "")
        name = str(record.get("name", "") or "")
        if not cookie_is_for_fetcher(site_host, domain, name):
            continue
        if sharepoint and (record.get("http_only")
                           or name in SHAREPOINT_SESSION_COOKIES):
            continue
        kept.append(record)
    return kept


#: The marker Done writes: "this profile was signed in, confirmed by the
#: person". Holds the host and a time, nothing secret.
_SIGNED_IN = "signed_in.json"

#: How a run reads a signed-in site. `browser`: every request is made by the
#: host's QtWebEngine profile (the hidden page of `audit.browser_fetch`, and
#: the renderer) and no cookie leaves it. `cookies`: `requests` carries the
#: copy Done wrote to `cookies.json`, the browser renders.
SESSION_BROWSER = "browser"
SESSION_COOKIES = "cookies"


def mark_signed_in(host: str) -> None:
    """Record that the person confirmed a sign-in to `host` with Done."""
    import datetime

    path = profile_dir(host, create=True) / _SIGNED_IN
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "host": _canonical_host(host),
                   "at": datetime.datetime.now(datetime.timezone.utc)
                   .isoformat(timespec="seconds")}, handle)


def profile_signed_in(host: str) -> bool:
    """Did Done confirm a sign-in in this host's browser profile?"""
    try:
        path = profile_dir(host) / _SIGNED_IN
    except ValueError:
        return False
    return path.is_file() and not path.is_symlink()


def session_mode(host: str) -> str:
    """`SESSION_BROWSER`, `SESSION_COOKIES`, or `""` with no session.

    SharePoint Online is always read by the browser: its session cookies are
    never exported. Every other site keeps the cookie copy for now; a site
    with a signed-in profile and no usable copy is where `browser` is the
    one decision to change (see `should_switch_to_browser`).
    """
    from project_profile import sharepoint_tenant

    if not has_session(host):
        return ""
    if sharepoint_tenant(_bare_host(host)):
        return SESSION_BROWSER
    return SESSION_COOKIES


def should_switch_to_browser(host: str, auth_wall: bool) -> bool:
    """Would the browser mode read what the cookie copy could not?

    True when a cookie-mode run met a sign-in wall and the host's profile was
    confirmed signed in - the copy is stale or incomplete, the profile is
    not. The extension point for a run plan's automatic fallback; today a
    caller says so rather than switching.
    """
    return (bool(auth_wall) and session_mode(host) == SESSION_COOKIES
            and profile_signed_in(host))


def _cookie_rows(path: Path):
    """The rows of a Chromium cookie file, or `None` when it cannot be read.

    Read-only with ordinary locking first, which sees a consistent file and
    leaves a rollback journal to its owner; `immutable` second, for a file
    whose leftover journal a read-only connection may not roll back. Neither
    writes. A file an open browser holds is refused by Windows to both -
    `None` then, and the caller reads it before the browser opens it.
    """
    import sqlite3

    query = ("SELECT host_key, name, value, path, is_secure, "
             "is_httponly, expires_utc FROM cookies")
    for mode in ("mode=ro", "mode=ro&immutable=1"):
        db = None
        try:
            uri = path.resolve().as_uri() + "?" + mode
            db = sqlite3.connect(uri, uri=True, timeout=0.5)
            return db.execute(query).fetchall()
        except Exception:  # noqa: BLE001 - see `read_profile_cookies`
            continue
        finally:
            if db is not None:
                db.close()
    return None


#: Chromium counts cookie expiry in microseconds since 1601-01-01.
_CHROMIUM_EPOCH_OFFSET = 11_644_473_600


def read_profile_cookies(storage_path, site_host: str,
                         names=SHAREPOINT_SESSION_COOKIES) -> list:
    """The named cookies of `site_host` from a browser profile's own store.

    How the sign-in window learns a session the profile already holds: the
    cookie store never reports a cookie restored from disk. Read before the
    profile is opened - an open profile's file is refused on Windows (see
    `_cookie_rows`). Only `names`, only the hosts `cookie_is_for_fetcher`
    allows, and only a value stored in clear: a value Chromium encrypted is
    left alone rather than guessed at. Never writes, never raises; `[]` on
    anything unexpected, and no value is ever logged.
    """
    base = Path(storage_path or "")
    candidates = [base / "Cookies", base / "Network" / "Cookies"]
    wanted = set(names or ())
    out: list = []
    for path in candidates:
        if not path.is_file():
            continue
        rows = _cookie_rows(path)
        if rows is None:
            continue
        for host_key, name, value, cookie_path, secure, http_only, expires in rows:
            if name not in wanted or not value:
                continue
            if not cookie_is_for_fetcher(site_host, host_key, name):
                continue
            seconds = None
            if expires:
                seconds = int(expires // 1_000_000 - _CHROMIUM_EPOCH_OFFSET)
            out.append({
                "name": str(name), "value": str(value),
                "domain": str(host_key).lower(), "path": cookie_path or "/",
                "secure": bool(secure), "http_only": bool(http_only),
                "same_site": "Default", "expires": seconds,
                "host_only": not str(host_key).startswith("."),
            })
        if out:
            break
    return out


def save_cookies(host: str, cookies) -> None:
    """Write the fetcher's copy of the session, readable only by its owner.

    Only the cookies `cookie_is_for_fetcher` allows are written, whoever
    calls: the filter lives where the file is written, not in one window.
    """
    canonical = _canonical_host(host)
    path = profile_dir(host, create=True) / _COOKIES
    # Created with the mode set, not chmod'ed after: between the write and
    # the chmod the file is world-readable, and the window in between is
    # exactly when another process on a shared machine would read it.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({
            "version": _COOKIE_STORE_VERSION,
            "host": canonical,
            "cookies": cookies_for_fetcher(host, _cookie_records(host, cookies)),
        }, handle)


def load_cookies(host: str) -> list[dict]:
    """The fetcher's scoped cookie records, or ``[]``. Never raises.

    Version 1 stored only ``{name: value}``. It is read as host-only cookies
    for this profile rather than as Requests' domainless supercookies.

    A session that cannot be
    read is a run without one, not a failed run."""
    path = cookies_path(host)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:  # noqa: BLE001 - see the docstring
        return []
    return _cookie_records(host, data)


def apply_to(config, target: str) -> tuple:
    """Sign a crawl config in for `target`, and say what happened.

    Returns `(host, count)`: the host to render as and how many values were
    given to the fetcher, or `("", 0)` when there is no session. Both halves
    or neither - `requests` and QtWebEngine share no storage, and handing the
    session to one of them produces a run where the browser sees the account
    and the fetch sees the login form.

    Quiet on purpose: every surface says this differently - the CLI prints a
    line, the window shows a status - and a shared helper that printed would
    make one of them say it twice.
    """
    host = host_of(target)
    if not host or not has_session(host):
        return "", 0
    cookies = load_cookies(host)
    if cookies:
        config.cookies = list(cookies)
    return host, len(cookies)


def describe(host: str) -> str:
    """One line about a session, with nothing secret in it.

    This is what a report or a run header may carry: the fact, the host, and
    nothing else. Deliberately not "a session cookie for X" - what is stored
    is a browser profile, and naming cookies invites somebody to print one.
    """
    return f"signed-in session for {host}" if has_session(host) else ""


#: The environment variable a test uses to keep every profile out of the
#: developer's own config directory. `config.config_file()` already resolves
#: at call time (see its docstring), so setting `XDG_CONFIG_HOME` is enough -
#: this name exists so the reason is written down somewhere.
ISOLATION_ENV = "XDG_CONFIG_HOME"


def env_isolated(path) -> None:
    """Point this module at `path` for the rest of the process."""
    os.environ[ISOLATION_ENV] = str(path)
