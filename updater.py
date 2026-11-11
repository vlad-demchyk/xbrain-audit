"""Self-update from GitHub Releases.

Checks the configured GitHub repository for a newer release, downloads
`XAnalyze.app.zip` and replaces the installed app. There is one artifact:
the window, the command line and the terminal interface are one executable
(see `app_entry`), and the `xanalyze` command is a symlink into the app, so
replacing the app updates all three at once.

Designed to be called two ways:

* ``xanalyze update`` — explicit, blocks until done, prints progress.
* Any other command — a quick, non-blocking version check that prints a
  one-line hint if a newer release exists.  Cached so it fires at most
  once a day (see ``_CHECK_INTERVAL``).

When running from source (``python cli.py``) there is nothing to replace,
so the check still runs but the update command says so and exits.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import config
from cli_impl import EXIT_ERROR, EXIT_OK
from update_trust import UPDATE_SIGNING_PUBLIC_KEYS

# ------------------------------------------------------------------ config

GITHUB_OWNER = "vlad-demchyk"
GITHUB_REPO = "xAnalyze-"
API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
MANIFEST_ASSET = "xanalyze-update-manifest.json"
SIGNATURE_ASSET = f"{MANIFEST_ASSET}.sig"

# Exact hosts used by the GitHub API and release-asset redirects. A suffix
# check would accept attacker-controlled names such as github.com.example.
_TRUSTED_UPDATE_HOSTS = frozenset({
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_SIGNATURE_BYTES = 4096
_MAX_ASSET_BYTES = 2 * 1024 * 1024 * 1024
#: Ceilings on what an archive may unpack to (P-19). The download is already
#: capped and checksummed, but a few megabytes of zip can claim gigabytes
#: once inflated, and the checksum only proves it is the file the manifest
#: named - not that the file is sane. Generous against the real bundle
#: (a few hundred MB, some thousands of files) and nowhere near a full disk.
_MAX_UNPACKED_BYTES = 4 * 1024 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 50_000
_MAX_COMPRESSION_RATIO = 200
#: How long the once-a-day hint may hold up a CLI command (P-37). The
#: explicit `xanalyze update` keeps the long timeout.
_QUIET_CHECK_TIMEOUT = 3
EXIT_UPDATE_PARTIAL = 3
_SHA256 = re.compile(r"[0-9a-f]{64}")

#: How often the background check fires.  The timestamp lives in the
#: config directory so it survives restarts but not manual deletion.
_CHECK_INTERVAL = 86400  # 24 hours

#: Asset name patterns to look for, in preference order.  ``{arch}`` is
#: replaced at runtime with ``arm64`` or ``x64``. The separate CLI archive of
#: earlier releases is gone: it was a second copy of the same program, and
#: updating it replaced the executable inside the app with a binary that
#: could not run without its own folder.
_GUI_ASSET_PATTERNS = [
    "XAnalyze.app.zip",
    "XAnalyze-macos-{arch}.app.zip",
]


# ------------------------------------------------------------------ types

@dataclass
class ReleaseInfo:
    tag: str
    version: str
    body: str
    assets: list[dict]
    html_url: str


@dataclass(frozen=True)
class AssetIntegrity:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class UpdateManifest:
    release: str
    assets: dict[str, AssetIntegrity]
    signature_verified: bool


# -------------------------------------------------------------- versioning

def parse_version(v: str) -> tuple[int, ...]:
    """``'0.5.0'`` → ``(0, 5, 0)``.  Strips a leading ``v``."""
    v = v.lstrip("v")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def newer(remote: str, local: str) -> bool:
    """Is *remote* strictly newer than *local*?"""
    return parse_version(remote) > parse_version(local)


# ----------------------------------------------------------- GitHub fetch

def _gh_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _require_trusted_url(url: str) -> str:
    """Accept only the exact HTTPS origins used for GitHub releases."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise RuntimeError("invalid update URL") from exc
    if (parsed.scheme.lower() != "https"
            or parsed.username is not None or parsed.password is not None
            or (parsed.hostname or "").lower() not in _TRUSTED_UPDATE_HOSTS
            or port not in {None, 443}):
        raise RuntimeError("untrusted update URL")
    return url


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


class _TrustedRedirectHandler(HTTPRedirectHandler):
    """Reject a redirect before urllib connects to its target.

    And drop the credential when the host changes. `urllib` copies every
    header except `content-length` and `content-type` onto the redirected
    request, so `Authorization: Bearer $GITHUB_TOKEN` followed the release
    asset from `api.github.com` to the download host. The asset URL is
    already signed and needs no token; sending one hands a personal access
    token to a host that never asked for it.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_trusted_url(newurl)
        request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if request is not None and _host_of(newurl) != _host_of(req.full_url):
            request.headers = {name: value
                               for name, value in request.headers.items()
                               if name.lower() != "authorization"}
        return request


def _tls_context():
    """Verify GitHub against the CA bundle shipped in the app.

    The default context trusts the CA file of the Python that built the
    bundle. Built on a CI runner, that path is the runner's and does not
    exist on anyone else's Mac, so every update check from a released app
    failed with CERTIFICATE_VERIFY_FAILED - while a local build, whose Python
    happens to point at Homebrew's bundle, worked. `certifi` travels with the
    app (requests needs it too), so it is the one file every build has.
    """
    import ssl

    try:
        import certifi
    except ImportError:  # pragma: no cover - requests depends on it
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _open_trusted(url: str, *, timeout: int):
    from urllib.request import HTTPSHandler

    _require_trusted_url(url)
    request = Request(url, headers=_gh_headers())
    response = build_opener(HTTPSHandler(context=_tls_context()),
                            _TrustedRedirectHandler()).open(
        request, timeout=timeout)
    try:
        _require_trusted_url(response.geturl())
    except Exception:
        response.close()
        raise
    return response


def fetch_latest(timeout: float = 15) -> ReleaseInfo:
    """GET the latest release from GitHub.  Raises on network / HTTP errors."""
    with _open_trusted(API_URL, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return ReleaseInfo(
        tag=data["tag_name"],
        version=data["tag_name"].lstrip("v"),
        body=data.get("body", ""),
        assets=data.get("assets", []),
        html_url=data.get("html_url", ""),
    )


# -------------------------------------------------------- asset selection

def _current_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return "x64"


def find_gui_asset(release: ReleaseInfo) -> dict | None:
    """Return the asset dict for the GUI app that matches this machine."""
    arch = _current_arch()
    for pattern in _GUI_ASSET_PATTERNS:
        name = pattern.format(arch=arch)
        for asset in release.assets:
            if asset["name"] == name:
                return asset
    # Fallback: any asset whose name contains "app" and ends with .zip
    for asset in release.assets:
        if "app" in asset["name"].lower() and asset["name"].endswith(".zip"):
            return asset
    return None


def _asset_named(release: ReleaseInfo, name: str) -> dict | None:
    for asset in release.assets:
        if asset.get("name") == name:
            return asset
    return None


def _read_remote_asset(asset: dict, *, limit: int) -> bytes:
    """Read a small release asset under a hard size and origin limit."""
    url = asset.get("browser_download_url", "")
    with _open_trusted(url, timeout=30) as response:
        raw_length = response.headers.get("Content-Length")
        try:
            declared = int(raw_length) if raw_length is not None else None
        except (TypeError, ValueError) as exc:
            raise RuntimeError("invalid update Content-Length") from exc
        if declared is not None and (declared < 0 or declared > limit):
            raise RuntimeError("update metadata is too large")
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise RuntimeError("update metadata is too large")
    if declared is not None and len(payload) != declared:
        raise RuntimeError("incomplete update metadata")
    return payload


def _verify_manifest_signature(payload: bytes, encoded_signature: bytes) -> bool:
    """Verify Ed25519 when configured, otherwise select the visible fallback."""
    public_keys = tuple(key.strip() for key in UPDATE_SIGNING_PUBLIC_KEYS
                        if key.strip())
    if not public_keys:
        return False
    if not encoded_signature.strip():
        raise RuntimeError("update manifest signature is missing")

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        signature = base64.b64decode(encoded_signature.strip(), validate=True)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("update manifest signature is invalid") from exc
    last_error = None
    for public_text in public_keys:
        try:
            public_bytes = base64.b64decode(public_text, validate=True)
            public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
            public_key.verify(signature, payload)
            return True
        except (InvalidSignature, TypeError, ValueError) as exc:
            last_error = exc
    raise RuntimeError("update manifest signature is invalid") from last_error


def _parse_update_manifest(payload: bytes, release: ReleaseInfo,
                           *, signature_verified: bool) -> UpdateManifest:
    try:
        data = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("update manifest is not valid JSON") from exc
    if (not isinstance(data, dict) or data.get("version") != 1
            or data.get("release") != release.tag
            or not isinstance(data.get("assets"), dict)):
        raise RuntimeError("update manifest does not match this release")

    assets: dict[str, AssetIntegrity] = {}
    for name, record in data["assets"].items():
        if (not isinstance(name, str) or Path(name).name != name
                or not isinstance(record, dict)):
            raise RuntimeError("update manifest contains an invalid asset")
        size = record.get("size")
        digest = record.get("sha256")
        if (not isinstance(size, int) or isinstance(size, bool)
                or size <= 0 or size > _MAX_ASSET_BYTES
                or not isinstance(digest, str)
                or _SHA256.fullmatch(digest.lower()) is None):
            raise RuntimeError("update manifest contains invalid integrity data")
        assets[name] = AssetIntegrity(name, size, digest.lower())
    if not assets:
        raise RuntimeError("update manifest contains no assets")
    return UpdateManifest(release.tag, assets, signature_verified)


def fetch_update_manifest(release: ReleaseInfo) -> UpdateManifest:
    """Fetch, authenticate and parse the integrity manifest for a release."""
    manifest_asset = _asset_named(release, MANIFEST_ASSET)
    if manifest_asset is None:
        raise RuntimeError("release has no update manifest")
    payload = _read_remote_asset(manifest_asset, limit=_MAX_MANIFEST_BYTES)

    signature_asset = _asset_named(release, SIGNATURE_ASSET)
    signature = (b"" if signature_asset is None else
                 _read_remote_asset(signature_asset,
                                    limit=_MAX_SIGNATURE_BYTES))
    verified = _verify_manifest_signature(payload, signature)
    return _parse_update_manifest(
        payload, release, signature_verified=verified)


def _asset_integrity(asset: dict, manifest: UpdateManifest) -> AssetIntegrity:
    name = asset.get("name")
    integrity = manifest.assets.get(name)
    if integrity is None:
        raise RuntimeError(f"asset is absent from update manifest: {name}")
    size = asset.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size != integrity.size:
        raise RuntimeError(f"asset size disagrees with update manifest: {name}")
    api_digest = asset.get("digest")
    if (api_digest is not None
            and api_digest != f"sha256:{integrity.sha256}"):
        raise RuntimeError(f"asset digest disagrees with update manifest: {name}")
    _require_trusted_url(asset.get("browser_download_url", ""))
    return integrity


# ------------------------------------------------------------- check cache

def _cache_path() -> Path:
    return config._config_dir() / "update_check.json"


def _last_check() -> float:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return float(data.get("at", 0))
    except (OSError, ValueError, TypeError):
        return 0.0


def _save_check(latest_version: str | None) -> None:
    try:
        _cache_path().write_text(json.dumps({
            "at": time.time(),
            "version": latest_version,
        }), encoding="utf-8")
    except OSError:
        pass


def check_for_update(*, quiet: bool = False) -> str | None:
    """Quick check: return the new version string if one is available.

    Respects the daily cache unless *quiet* is False (explicit command).
    Returns ``None`` when no update is available or the check fails.
    """
    now = time.time()
    if quiet and (now - _last_check()) < _CHECK_INTERVAL:
        return None

    try:
        if quiet:
            release = fetch_latest(timeout=_QUIET_CHECK_TIMEOUT)
        else:
            release = fetch_latest()
    except Exception:  # noqa: BLE001
        # Recorded as a check all the same (P-37): offline, the cache was
        # never written, so every command paid the timeout again.
        if quiet:
            _save_check(None)
        return None

    _save_check(release.version)

    if newer(release.version, config.APP_VERSION):
        return release.version
    return None


def print_update_hint(new_version: str) -> None:
    """One-line hint printed to stderr before the real command runs."""
    print(
        f"# XAnalyze {new_version} is available (you have {config.APP_VERSION}). "
        f"Run `xanalyze update` to upgrade.",
        file=sys.stderr,
    )


# ----------------------------------------------------------- binary locate

def _running_binary() -> Path | None:
    """The path to the frozen binary, or ``None`` when running from source."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve()


def _app_containing(executable: Path) -> Path | None:
    """The `.app` an executable sits in (`X.app/Contents/MacOS/x`), or None."""
    parts = executable.parts
    if len(parts) >= 4 and parts[-2] == "MacOS" and parts[-3] == "Contents" \
            and parts[-4].endswith(".app"):
        return Path(*parts[:-3])
    return None


#: Where the app is looked for when the running program is not inside one.
_APP_LOCATIONS = (Path("/Applications/XAnalyze.app"),
                  Path.home() / "Applications" / "XAnalyze.app")


def _installed_app() -> Path | None:
    """The app to update: the one this program runs from, else the usual places.

    Taken from the running executable first, because `/Applications` is only
    where most people put it: an app run from `~/Applications` or a download
    folder is still the one the person is using.
    """
    running = _running_binary()
    if running is not None:
        app = _app_containing(running)
        if app is not None and app.exists():
            return app
    for app in _APP_LOCATIONS:
        if app.exists():
            return app
    return None


def _legacy_cli() -> Path | None:
    """A standalone `xanalyze` from the old CLI archive, if that is what runs."""
    running = _running_binary()
    if running is not None and _app_containing(running) is None:
        return running
    return None


def _gui_app_path() -> Path | None:
    """Kept for callers of the old name; see `_installed_app`."""
    return _installed_app()


# --------------------------------------------------------- download+replace

def _download(url: str, dest: Path, integrity: AssetIntegrity) -> None:
    """Stream one trusted asset and prove its size and SHA-256."""
    with _open_trusted(url, timeout=30) as resp:
        raw_total = resp.headers.get("Content-Length")
        try:
            total = int(raw_total) if raw_total is not None else 0
        except (TypeError, ValueError) as exc:
            raise RuntimeError("invalid asset Content-Length") from exc
        if total and total != integrity.size:
            raise RuntimeError("asset Content-Length disagrees with manifest")
        downloaded = 0
        digest = hashlib.sha256()
        chunk_size = 1024 * 256  # 256 KB
        with open(dest, "wb") as f:
            while True:
                remaining = integrity.size - downloaded
                chunk = resp.read(min(chunk_size, remaining + 1))
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > integrity.size:
                    raise RuntimeError("downloaded asset exceeds manifest size")
                digest.update(chunk)
                f.write(chunk)
                if total:
                    pct = downloaded * 100 // total
                    mb = downloaded // (1024 * 1024)
                    total_mb = total // (1024 * 1024)
                    print(f"\r# downloading: {mb}/{total_mb} MB ({pct}%)",
                          end="", file=sys.stderr, flush=True)
        if total:
            print(file=sys.stderr)
    if downloaded != integrity.size:
        raise RuntimeError("downloaded asset size does not match manifest")
    if digest.hexdigest() != integrity.sha256:
        raise RuntimeError("downloaded asset checksum does not match manifest")


def _safe_member_name(name: str) -> bool:
    """A relative path that stays inside the folder it is unpacked into."""
    from pathlib import PurePosixPath

    if not name or "\\" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def _check_archive(entries) -> None:
    """Refuse an archive before anything is written (P-19).

    `entries` is `(name, unpacked_size, packed_size)` for every member.
    """
    count = 0
    total = 0
    packed = 0
    for name, size, compressed in entries:
        count += 1
        if count > _MAX_ARCHIVE_ENTRIES:
            raise RuntimeError("update archive has too many entries")
        if not _safe_member_name(name):
            raise RuntimeError(f"update archive has an unsafe path: {name!r}")
        total += max(int(size), 0)
        packed += max(int(compressed), 0)
        if total > _MAX_UNPACKED_BYTES:
            raise RuntimeError("update archive unpacks to more than allowed")
    if packed and total > packed * _MAX_COMPRESSION_RATIO:
        raise RuntimeError("update archive compression ratio is implausible")


def _work_dir(dest: Path | None, prefix: str) -> Path:
    """`dest` when the caller owns the cleanup, else a fresh temp dir."""
    if dest is None:
        return Path(tempfile.mkdtemp(prefix=prefix))
    dest.mkdir(parents=True, exist_ok=True)
    return dest


_S_IFMT = 0o170000
_S_IFLNK = 0o120000


def _zip_mode(info) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def _unzip_bundle(zf, dest: Path) -> None:
    """Extract an app bundle the way `ditto` packed it.

    `ZipFile.extractall` writes a symlink entry as a small file holding the
    link's text and drops every executable bit. An app bundle is full of
    both: Qt's frameworks are symlinks (`Versions/Current`), and
    `QtWebEngineProcess` is an executable the browser pass starts - extracted
    that way, the window opened and every page load failed. So links are
    made as links, after checking they stay inside the bundle, and the mode
    bits the archive recorded are put back.
    """
    import posixpath

    root = dest.resolve()
    links = []
    for info in zf.infolist():
        mode = _zip_mode(info)
        target = dest / info.filename
        if (mode & _S_IFMT) == _S_IFLNK:
            link = zf.read(info).decode("utf-8")
            resolved = posixpath.normpath(posixpath.join(
                posixpath.dirname(info.filename.rstrip("/")), link))
            if link.startswith("/") or resolved.startswith("../") or resolved == "..":
                raise RuntimeError(f"update archive link leaves the bundle: {info.filename}")
            links.append((target, link))
            continue
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.resolve().is_relative_to(root):
            raise RuntimeError(f"update archive path leaves the bundle: {info.filename}")
        with zf.open(info) as source, open(target, "wb") as out:
            shutil.copyfileobj(source, out)
        permissions = mode & 0o777
        if permissions:
            target.chmod(permissions & ~0o022 | 0o400)
    for target, link in links:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or target.exists():
            target.unlink()
        os.symlink(link, target)


def _extract_gui_app(archive: Path, dest: Path | None = None) -> Path:
    """Extract ``XAnalyze.app`` from a zip, links and modes kept."""
    import zipfile

    tmp = _work_dir(dest, "xanalyze-update-gui-")
    with zipfile.ZipFile(archive) as zf:
        _check_archive([(i.filename, i.file_size, i.compress_size)
                        for i in zf.infolist()])
        _unzip_bundle(zf, tmp)
    app = tmp / "XAnalyze.app"
    if not app.exists():
        # Walk to find it
        for p in tmp.rglob("XAnalyze.app"):
            if p.is_dir():
                return p
        raise RuntimeError("XAnalyze.app not found in the archive")
    return app


def _replace_gui_app(old: Path, new: Path) -> None:
    """Stage beside the installed app, then rename with a recoverable backup."""
    transaction = Path(tempfile.mkdtemp(prefix=".xanalyze-update-", dir=old.parent))
    staged = transaction / "XAnalyze.app"
    backup = transaction / "previous.app"
    committed = False
    try:
        shutil.copytree(new, staged, symlinks=True)
        with (staged / "Contents/Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        executable = info.get("CFBundleExecutable")
        if (info.get("CFBundlePackageType") != "APPL"
                or not isinstance(executable, str) or not executable
                or Path(executable).name != executable or executable in (".", "..")):
            raise RuntimeError("invalid application bundle metadata")
        binary = staged / "Contents/MacOS" / executable
        if not binary.is_file() or not binary.resolve().is_relative_to(staged.resolve()):
            raise RuntimeError("application bundle executable is missing or unsafe")
        # ZIP extraction does not preserve the executable mode.
        binary.chmod(binary.stat().st_mode | 0o111)
        old.rename(backup)
        try:
            staged.rename(old)
            committed = True
        except Exception:
            try:
                backup.rename(old)
            except Exception as rollback_error:
                raise RuntimeError(
                    f"update and rollback failed; previous app preserved at {backup}"
                ) from rollback_error
            raise
    finally:
        # Never delete the only remaining copy after a failed rollback.
        if not backup.exists() or committed:
            shutil.rmtree(transaction, ignore_errors=True)


def _new_app_location() -> Path:
    """Where an app goes when only the old standalone command was installed."""
    system = _APP_LOCATIONS[0]
    if os.access(system.parent, os.W_OK):
        return system
    return _APP_LOCATIONS[1]


def _install_new_app(target: Path, extracted: Path) -> None:
    """Put a first app in place, staged beside it and renamed in one step."""
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".xanalyze-install-", dir=target.parent))
    try:
        staged = staging / target.name
        shutil.copytree(extracted, staged, symlinks=True)
        staged.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _point_command_at(app: Path, legacy: Path | None) -> None:
    """Make `xanalyze` run the app that was just installed.

    A symlink that already points into the app needs nothing: the app was
    replaced underneath it. The old standalone command is moved over to the
    app, so the next `xanalyze` is the same program as the window, and the
    old folder is named so the person can delete it.
    """
    import cli_install

    executable = app / "Contents" / "MacOS" / "XAnalyze"
    current = cli_install.installed_target()
    if current is not None and _app_containing(current) == app and legacy is None:
        return
    if legacy is None and current is None:
        return
    try:
        link = cli_install.install(source=executable)
    except Exception as exc:  # noqa: BLE001 - the app is updated either way
        print(f"# could not link the command to the app: {exc}; run "
              f"{executable} --install-cli", file=sys.stderr)
        return
    print(f"# command: {link} -> {executable}", file=sys.stderr)
    if legacy is not None:
        print(f"# the old standalone command in {legacy.parent} is no longer "
              f"used and can be deleted", file=sys.stderr)


def do_update() -> int:
    """Full update flow: check → download → replace.

    Replaces the installed app - the one this program runs from, or the one
    in `/Applications` or `~/Applications`. An old standalone command is
    moved over to the app.

    Returns `EXIT_OK` when all installed components succeed, 3 on partial
    update, and `EXIT_ERROR` on failure. Not 1: elsewhere 1 means "something
    was found", and an update that could not reach GitHub has found nothing.
    See `cli_impl` for the whole list.
    """
    print(f"# XAnalyze updater — current version: {config.APP_VERSION}",
          file=sys.stderr)

    # 1. Check for update
    try:
        release = fetch_latest()
    except HTTPError as exc:
        print(f"error: GitHub API returned {exc.code}", file=sys.stderr)
        return EXIT_ERROR
    except URLError as exc:
        print(f"error: could not reach GitHub: {exc.reason}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"# latest release: {release.tag}", file=sys.stderr)

    if not newer(release.version, config.APP_VERSION):
        print("Already up to date.")
        return EXIT_OK

    try:
        manifest = fetch_update_manifest(release)
    except Exception as exc:  # noqa: BLE001
        print(f"error: release integrity check failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not manifest.signature_verified:
        print("# warning: update signing key is not configured; "
              "using HTTPS, size and SHA-256 fallback", file=sys.stderr)

    updated = 0
    failed = []

    # 2. One artifact: the app. The command line is a symlink into it.
    app = _installed_app()
    legacy = _legacy_cli()
    asset = find_gui_asset(release)
    if asset is None:
        print("# no XAnalyze.app.zip in this release", file=sys.stderr)
        failed.append("app (missing asset)")
    elif app is None and legacy is None:
        print("# no installed XAnalyze.app found; nothing to replace",
              file=sys.stderr)
    else:
        print(f"# asset: {asset['name']} ({asset['size'] // (1024*1024)} MB)",
              file=sys.stderr)
        target = app or _new_app_location()
        print(f"# app: {target}", file=sys.stderr)
        tmp_dir = Path(tempfile.mkdtemp(prefix="xanalyze-update-"))
        archive_path = tmp_dir / asset["name"]
        # Everything the rest of this run needs is imported now. A frozen
        # app reads its modules lazily from an archive inside the bundle, and
        # the bundle is about to be replaced under the running process: an
        # import after that read the new archive at the old offsets and failed
        # with "Error -3 while decompressing data" - reporting a finished
        # update as a failed one.
        import cli_install  # noqa: F401
        try:
            integrity = _asset_integrity(asset, manifest)
            _download(asset["browser_download_url"], archive_path, integrity)
            extracted = _extract_gui_app(archive_path, tmp_dir / "unpacked")
            if app is not None:
                _replace_gui_app(app, extracted)
            else:
                _install_new_app(target, extracted)
            updated += 1
            print(f"# app updated: {target}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            failed.append("app")
            print(f"# app update failed: {exc}", file=sys.stderr)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if updated:
            # After the swap, and outside the update's own failure: the app
            # is new either way, and the command is a convenience on top.
            try:
                _point_command_at(target, legacy)
            except Exception as exc:  # noqa: BLE001
                print(f"# could not check the `xanalyze` command: {exc}",
                      file=sys.stderr)

    if failed:
        print(f"Update {'partially completed' if updated else 'failed'}; "
              f"not updated: {', '.join(failed)}", file=sys.stderr)
        return EXIT_UPDATE_PARTIAL if updated else EXIT_ERROR

    if updated == 0:
        print("Nothing to update. Download manually from:\n"
              f"  {release.html_url}", file=sys.stderr)
        return EXIT_ERROR

    print(f"\nUpdated XAnalyze {config.APP_VERSION} → {release.version}")
    if release.body:
        print(f"\nRelease notes:\n{release.body[:500]}")
    return EXIT_OK
