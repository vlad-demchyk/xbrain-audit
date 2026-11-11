"""The full page tree of a SharePoint Online site, read through its REST API.

A link-following crawl sees what a page links to. On a SharePoint site that
is the navigation and whatever an editor happened to link, which leaves out
every page nobody linked: drafts promoted later, news posts older than the
news web part shows, a subsite reachable only from the site contents. The
site itself knows its pages - they are items in a library - so this module
asks it, and hands the crawler a list of addresses to read instead of a
starting point to wander from.

Sources, in order of authority:

* ``sitepages`` - the Site Pages library of every web, read with
  ``GetList('<web>/SitePages')``. Never ``getbytitle('Site Pages')``: the
  title is localized (``Pagine del sito`` on an Italian tenant) while the URL
  is not. A library at another address (a publishing ``Pagine`` library,
  template 850) is found through ``lists?$filter=BaseTemplate eq 119 or
  BaseTemplate eq 850``. ``FileRef`` is the canonical spelling of a page.
* ``webs`` - subsites, recursively, with a depth and count ceiling and a
  visited set (``_api/web/webs``).
* ``welcome`` - each web's home page (``rootfolder/WelcomePage``), so a link
  to the bare web address dedupes with the page it opens.
* ``navigation`` - Quick Launch and the top navigation bar of every web.
* ``search`` - ``contentclass:STS_ListItem_WebPageLibrary`` under the site
  path: catches page libraries the list walk could not read.

Every page keeps the sources that named it. Everything dropped is counted
with a reason (another site collection, a system page, a list form, a sharing
link), files are kept apart as ``documents``, and an expired or missing
sign-in is a result of its own (``auth_required``), never an empty list: a
tree that came back empty because the session expired and one that came back
empty because the site has no pages must not look the same.

Cookies and request headers never reach a log line, an error or the result;
URLs in errors carry no query string.
"""
from __future__ import annotations

import email.utils
import re
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

import applog
from audit import authwall

ACCEPT_JSON = "application/json;odata=nometadata"

SOURCE_SITEPAGES = "sitepages"
SOURCE_WELCOME = "welcome"
SOURCE_NAVIGATION = "navigation"
SOURCE_SEARCH = "search"
SOURCE_LIBRARY = "library"
SOURCE_WEBS = "webs"

#: Which source's spelling and metadata win when two name the same page.
_SOURCE_RANK = {
    SOURCE_SITEPAGES: 0,
    SOURCE_WELCOME: 1,
    SOURCE_SEARCH: 2,
    SOURCE_LIBRARY: 3,
    SOURCE_NAVIGATION: 4,
}

# Reasons an address was not taken as a page.
SKIP_OTHER_HOST = "other-host"
SKIP_OTHER_SITE = "other-site"
SKIP_SYSTEM = "system-page"
SKIP_LIST_FORM = "list-form"
SKIP_LIST_VIEW = "list-view"
SKIP_SHARING_LINK = "sharing-link"
SKIP_NOT_HTTP = "not-http"
SKIP_NO_LINK = "no-link"
SKIP_FOLDER = "folder"
SKIP_NOT_A_PAGE = "not-a-page"
SKIP_PAGE_LIMIT = "page-limit"
SKIP_WEB_LIMIT = "web-limit"
SKIP_WEB_DEPTH = "web-depth"
#: `SitePages/Templates/*.aspx`: page templates, not pages anyone visits.
SKIP_PAGE_TEMPLATE = "page-template"

# Why a sign-in is needed.
AUTH_STATUS_401 = "status-401"
AUTH_LOGIN_REDIRECT = "login-redirect"
AUTH_FORMS_HEADER = "forms-auth-required"
AUTH_LOGIN_PAGE = "login-page"

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_EMPTY = "empty"
STATUS_ERROR = "error"
STATUS_AUTH = "auth-required"
#: Signed in, but not allowed into this site: a bare 403 on the site itself.
STATUS_ACCESS_DENIED = "access-denied"

#: Managed paths under which a tenant keeps its other site collections. A
#: walk that starts at the tenant's root site must not take them as its own.
_MANAGED_PATHS = ("sites", "teams", "personal", "portals")

_PAGE_LIBRARY_TEMPLATES = (119, 850)
_DOCUMENT_LIBRARY_TEMPLATE = 101
#: A list's or library's views: a table of its items, not a page.
_LIST_VIEWS = {"allitems.aspx", "allpages.aspx"}
#: A list's item forms.
_LIST_FORMS = {"dispform.aspx", "editform.aspx", "newform.aspx",
               "upload.aspx"}
_SYSTEM_SEGMENTS = {"_layouts", "_vti_bin", "_api", "_catalogs", "_forms",
                    "_vti_pvt", "_cts", "_private"}
_RETRY_STATUSES = {429, 503}
_TRANSIENT_STATUSES = {500, 502, 504}
_ITEM_FIELDS = "FileRef,FileLeafRef,Title,Modified,PromotedState,FSObjType"
_ITEM_FIELDS_PLAIN = "FileRef,FileLeafRef,Title,Modified,FSObjType"
_PATH_SAFE = "/-._~!$&'()*+,;=:@"
#: `/:w:/r/...`, `/:b:/g/...`: a sharing link, not an address of the page.
_SHARING_SEGMENT = re.compile(r"^:[a-z]:$", re.IGNORECASE)


def default_user_agent() -> str:
    """``ISV|Company|App/Version``, the decoration Microsoft asks for.

    Throttling on SharePoint Online is attributed by this string; an
    undecorated client is throttled first. The version is read lazily so the
    module stays importable without the app's settings layer.
    """
    try:
        from config import APP_VERSION  # noqa: PLC0415 - optional dependency
    except Exception:  # noqa: BLE001 - a version is nice, not required
        APP_VERSION = "0"
    return f"ISV|Crowdm|XAnalyze/{APP_VERSION}"


# --------------------------------------------------------------------------
# Result


@dataclass
class TreePage:
    url: str
    title: str = ""
    #: Absolute URL of the web the page belongs to.
    web: str = ""
    #: The most authoritative source that named it (see `_SOURCE_RANK`).
    source: str = ""
    sources: tuple[str, ...] = ()
    modified: str = ""
    #: 0 page, 1 news waiting to be promoted, 2 news post; None when unknown.
    promoted_state: int | None = None


@dataclass
class TreeWeb:
    url: str
    title: str = ""
    server_relative_url: str = ""
    language: int | None = None
    depth: int = 0
    parent: str = ""
    welcome_page: str = ""


@dataclass
class TreeDocument:
    url: str
    title: str = ""
    web: str = ""
    source: str = ""
    modified: str = ""


@dataclass
class SkippedUrl:
    url: str
    reason: str
    source: str = ""


@dataclass
class TreeError:
    source: str
    url: str
    message: str
    status: int | None = None


@dataclass
class SiteTree:
    site_url: str
    web: TreeWeb | None = None
    pages: list[TreePage] = field(default_factory=list)
    webs: list[TreeWeb] = field(default_factory=list)
    documents: list[TreeDocument] = field(default_factory=list)
    skipped: list[SkippedUrl] = field(default_factory=list)
    errors: list[TreeError] = field(default_factory=list)
    auth_required: bool = False
    auth_reason: str = ""
    #: The session works but has no permission on the site (bare 403, no
    #: sign-in header, no redirect). Not `auth_required`: signing in again
    #: as the same person changes nothing.
    access_denied: bool = False
    #: A ceiling (pages, webs, requests) or a cancel cut the walk short.
    truncated: bool = False
    requests_made: int = 0

    @property
    def status(self) -> str:
        """One word that keeps "nothing there" apart from "could not look"."""
        if self.auth_required:
            return STATUS_AUTH
        if self.access_denied:
            return STATUS_ACCESS_DENIED
        if self.web is None:
            return STATUS_ERROR
        if not self.pages:
            return STATUS_ERROR if self.errors else STATUS_EMPTY
        if self.errors or self.truncated:
            return STATUS_PARTIAL
        return STATUS_OK

    def skipped_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.skipped:
            counts[item.reason] = counts.get(item.reason, 0) + 1
        return counts


def seed_urls(tree: SiteTree) -> list[str]:
    """The page addresses for a crawler to read, home pages first."""
    return [page.url for page in tree.pages]


# --------------------------------------------------------------------------
# HTTP


class AuthRequired(Exception):
    def __init__(self, reason: str, url: str):
        super().__init__(reason)
        self.reason = reason
        self.url = url


class _BudgetExhausted(Exception):
    pass


class _DeadlineReached(Exception):
    pass


class _Cancelled(Exception):
    pass


class RestError(Exception):
    def __init__(self, url: str, message: str, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.message = message
        self.status = status


def _redact(url: str) -> str:
    """The address without its query: paging tokens stay out of reports."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def _retry_after(value: str | None, now: float) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    return max(0.0, when.timestamp() - now)


class _Client:
    """GET with throttling discipline, a request budget and auth detection."""

    def __init__(self, session, *, host: str, user_agent: str,
                 timeout: float, max_requests: int, min_interval: float,
                 max_retries: int, backoff_base: float, max_wait: float,
                 sleep: Callable[[float], None], clock: Callable[[], float],
                 wall_clock: Callable[[], float],
                 cancelled: Callable[[], bool] | None):
        self.session = session
        self.host = host.lower()
        self.headers = {"Accept": ACCEPT_JSON, "User-Agent": user_agent}
        self.timeout = timeout
        self.max_requests = max_requests
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_wait = max_wait
        self.sleep = sleep
        self.clock = clock
        self.wall_clock = wall_clock
        self.cancelled = cancelled
        self.requests_made = 0
        self._last: float | None = None
        #: `clock()` value after which no request starts; None for none.
        self.deadline: float | None = None

    def _pace(self) -> None:
        if self.cancelled and self.cancelled():
            raise _Cancelled
        if self.max_requests and self.requests_made >= self.max_requests:
            raise _BudgetExhausted
        if self.deadline is not None and self.clock() >= self.deadline:
            raise _DeadlineReached
        if self._last is not None and self.min_interval > 0:
            wait = self._last + self.min_interval - self.clock()
            if wait > 0:
                self.sleep(wait)
        self.requests_made += 1
        self._last = self.clock()

    def get_json(self, url: str):
        if (urlparse(url).hostname or "").lower() != self.host:
            # A nextLink pointing elsewhere must not receive the session.
            raise RestError(_redact(url), "refused: another host")
        attempt = 0
        hops = 0
        while True:
            self._pace()
            try:
                resp = self.session.get(url, headers=self.headers,
                                        timeout=self.timeout,
                                        allow_redirects=False)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt >= self.max_retries:
                    raise RestError(_redact(url),
                                    f"network: {type(exc).__name__}") from None
                self.sleep(self._backoff(attempt))
                attempt += 1
                continue
            status = resp.status_code
            headers = resp.headers or {}
            applog.debug("sharepoint_tree.request", url=_redact(url),
                         status=status)
            # One source of truth for "this is a sign-in": `audit.authwall`.
            if authwall.forms_auth_required(headers):
                raise AuthRequired(AUTH_FORMS_HEADER, _redact(url))
            if status in (301, 302, 303, 307, 308):
                # A browser transport cannot see where a redirect went when
                # it left the site; for a signed-in request that is the
                # identity provider (see `audit.browser_fetch`).
                if _header(headers, "X-XAnalyze-Redirect") == "off-site":
                    raise AuthRequired(AUTH_LOGIN_REDIRECT, _redact(url))
                location = urljoin(url, _header(headers, "Location") or "")
                if authwall.is_definite_login_url(location):
                    raise AuthRequired(AUTH_LOGIN_REDIRECT, _redact(url))
                hops += 1
                if hops > 3 or not location:
                    raise RestError(_redact(url), "too many redirects", status)
                url = location
                if (urlparse(url).hostname or "").lower() != self.host:
                    raise RestError(_redact(url), "redirected off the site",
                                    status)
                continue
            if status == 401:
                raise AuthRequired(AUTH_STATUS_401, _redact(url))
            if status in _RETRY_STATUSES or status in _TRANSIENT_STATUSES:
                if attempt >= self.max_retries:
                    raise RestError(_redact(url), "throttled or unavailable",
                                    status)
                hinted = _retry_after(_header(headers, "Retry-After"),
                                      self.wall_clock())
                if hinted is not None and hinted > self.max_wait:
                    # Asking again sooner than the server said is what
                    # turns throttling into a block. Stop and say so.
                    raise RestError(
                        _redact(url),
                        f"throttled: server asked to wait {round(hinted)}s, "
                        f"more than max_wait {round(self.max_wait)}s", status)
                wait = hinted if hinted is not None else self._backoff(attempt)
                if (self.deadline is not None
                        and self.clock() + wait > self.deadline):
                    raise _DeadlineReached
                applog.info("sharepoint_tree.throttled", url=_redact(url),
                            status=status, wait=round(wait, 1))
                self.sleep(wait)
                attempt += 1
                continue
            if status == 403:
                raise RestError(_redact(url), _error_message(resp) or "forbidden",
                                status)
            if status >= 400:
                raise RestError(_redact(url), _error_message(resp)
                                or f"HTTP {status}", status)
            try:
                return resp.json()
            except ValueError:
                text = _safe_text(resp)
                if any(host in text.lower()
                       for host in authwall.IDENTITY_PROVIDER_HOSTS):
                    raise AuthRequired(AUTH_LOGIN_PAGE, _redact(url)) from None
                raise RestError(_redact(url), "response is not JSON",
                                status) from None

    def _backoff(self, attempt: int) -> float:
        return min(self.backoff_base * (2 ** attempt), self.max_wait)


def _header(headers, name: str) -> str:
    try:
        value = headers.get(name)
    except AttributeError:
        return ""
    if value is None and isinstance(headers, dict):
        lowered = name.lower()
        for key, item in headers.items():
            if key.lower() == lowered:
                return str(item)
    return "" if value is None else str(value)


def _safe_text(resp) -> str:
    try:
        return resp.text or ""
    except Exception:  # noqa: BLE001
        return ""


def _error_message(resp) -> str:
    """SharePoint's own error sentence, which never carries credentials."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(body, dict):
        return ""
    error = body.get("odata.error") or body.get("error") or {}
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, dict):
            message = message.get("value")
        if message:
            return str(message)[:300]
    return ""


# --------------------------------------------------------------------------
# OData shapes


def _rows(body) -> list:
    if not isinstance(body, dict):
        return []
    if isinstance(body.get("value"), list):
        return body["value"]
    d = body.get("d")
    if isinstance(d, dict) and isinstance(d.get("results"), list):
        return d["results"]
    return []


def _next_link(body) -> str:
    if not isinstance(body, dict):
        return ""
    for key in ("odata.nextLink", "@odata.nextLink"):
        if body.get(key):
            return str(body[key])
    d = body.get("d")
    if isinstance(d, dict) and d.get("__next"):
        return str(d["__next"])
    return ""


def _single(body) -> dict:
    if isinstance(body, dict) and isinstance(body.get("d"), dict):
        return body["d"]
    return body if isinstance(body, dict) else {}


def _results(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("results"), list):
        return value["results"]
    return []


def _odata_string(value: str) -> str:
    return value.replace("'", "''")


def _encode_path(path: str) -> str:
    return quote(path, safe=_PATH_SAFE)


# --------------------------------------------------------------------------
# Scope and classification


def _web_url_guess(url: str) -> str:
    """Cut a page or library address back to the web it lives in."""
    parsed = urlparse(url.strip())
    segments = [s for s in unquote(parsed.path).split("/") if s]
    kept: list[str] = []
    for segment in segments:
        low = segment.lower()
        if (low.startswith("_") or low in {"sitepages", "lists", "pages",
                                           "shared documents", "forms"}
                or "." in segment):
            break
        kept.append(segment)
    path = "/" + "/".join(kept) if kept else ""
    return f"{parsed.scheme or 'https'}://{parsed.netloc}{_encode_path(path)}"


def _path_key(path: str) -> str:
    path = unquote(path)
    if len(path) > 1:
        path = path.rstrip("/")
    return path.casefold()


def _in_scope(path_key: str, scope_key: str) -> bool:
    if not scope_key or scope_key == "/":
        return True
    return path_key == scope_key or path_key.startswith(scope_key + "/")


def _in_site(path_key: str, scope_key: str) -> bool:
    """`_in_scope` for the walk's own site.

    The tenant's root site has the scope `/`, under which everything on the
    host sits - including every other site collection. Those live under
    managed paths (`/sites/`, `/teams/`, ...), so for the root site anything
    under one of them is another site.
    """
    if not scope_key or scope_key == "/":
        first = path_key.strip("/").split("/", 1)[0]
        return first not in _MANAGED_PATHS
    return _in_scope(path_key, scope_key)


@dataclass
class _Candidate:
    url: str
    source: str
    title: str = ""
    web: str = ""
    modified: str = ""
    promoted_state: int | None = None
    is_folder: bool = False


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class _Walk:
    def __init__(self, site_url: str, client: _Client, tree: SiteTree, *,
                 max_pages: int, max_webs: int, max_web_depth: int,
                 max_documents: int, use_navigation: bool, use_search: bool,
                 inventory_documents: bool, progress_cb,
                 search_page_size: int = 500):
        self.site_url = site_url
        self.client = client
        self.tree = tree
        self.max_pages = max_pages
        self.max_webs = max_webs
        self.max_web_depth = max_web_depth
        self.max_documents = max_documents
        self.use_navigation = use_navigation
        self.use_search = use_search
        self.inventory_documents = inventory_documents
        self.progress_cb = progress_cb
        self.search_page_size = search_page_size
        self.candidates: list[_Candidate] = []
        self.origin = ""
        self.host = ""
        self.scope_key = ""
        self.web_paths: dict[str, TreeWeb] = {}
        self._documents_seen: set[str] = set()

    # -- helpers

    def _progress(self, stage: str, url: str) -> None:
        if self.progress_cb:
            try:
                self.progress_cb(stage, url)
            except Exception:  # noqa: BLE001 - a UI hook must not stop the walk
                pass

    def _error(self, source: str, exc: RestError) -> None:
        self.tree.errors.append(TreeError(source=source, url=exc.url,
                                          message=exc.message,
                                          status=exc.status))
        applog.warning("sharepoint_tree.error", source=source, url=exc.url,
                       status=exc.status, message=exc.message)

    def _api(self, web_url: str, tail: str) -> str:
        return web_url.rstrip("/") + "/_api/" + tail

    def _paged(self, url: str) -> Iterable[dict]:
        seen: set[str] = set()
        while url and url not in seen:
            seen.add(url)
            body = self.client.get_json(url)
            yield from _rows(body)
            url = _next_link(body)

    def _abs(self, server_relative: str) -> str:
        return self.origin + _encode_path(server_relative)

    # -- phases

    def root(self) -> TreeWeb:
        guess = _web_url_guess(self.site_url)
        parsed = urlparse(guess)
        self.host = (parsed.hostname or "").lower()
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.client.host = self.host
        self._progress("web", guess)
        body = _single(self.client.get_json(self._api(
            guess, "web?$select=Url,Title,ServerRelativeUrl,Language")))
        srv = str(body.get("ServerRelativeUrl") or urlparse(guess).path or "/")
        web = TreeWeb(url=str(body.get("Url") or guess).rstrip("/"),
                      title=str(body.get("Title") or ""),
                      server_relative_url=srv,
                      language=_int_or_none(body.get("Language")),
                      depth=0)
        self.scope_key = _path_key(srv)
        return web

    def webs(self, root: TreeWeb) -> None:
        self.tree.webs.append(root)
        self.web_paths[_path_key(root.server_relative_url)] = root
        queue = deque([root])
        while queue:
            parent = queue.popleft()
            if parent.depth >= self.max_web_depth:
                continue
            try:
                rows = list(self._paged(self._api(
                    parent.url,
                    "web/webs?$select=Url,Title,ServerRelativeUrl,Language")))
            except RestError as exc:
                self._error(SOURCE_WEBS, exc)
                continue
            for row in rows:
                srv = str(row.get("ServerRelativeUrl") or "")
                url = str(row.get("Url") or (self._abs(srv) if srv else ""))
                if not srv and url:
                    srv = unquote(urlparse(url).path)
                key = _path_key(srv)
                if not srv or key in self.web_paths:
                    continue  # a cycle or a repeat
                if not _in_site(key, self.scope_key):
                    self.tree.skipped.append(SkippedUrl(url, SKIP_OTHER_SITE,
                                                        SOURCE_WEBS))
                    continue
                if self.max_webs and len(self.tree.webs) >= self.max_webs:
                    self.tree.truncated = True
                    self.tree.skipped.append(SkippedUrl(url, SKIP_WEB_LIMIT,
                                                        SOURCE_WEBS))
                    continue
                child = TreeWeb(url=url.rstrip("/"),
                                title=str(row.get("Title") or ""),
                                server_relative_url=srv,
                                language=_int_or_none(row.get("Language")),
                                depth=parent.depth + 1, parent=parent.url)
                if child.depth > self.max_web_depth:
                    self.tree.skipped.append(SkippedUrl(url, SKIP_WEB_DEPTH,
                                                        SOURCE_WEBS))
                    continue
                self.web_paths[key] = child
                self.tree.webs.append(child)
                queue.append(child)

    def welcome(self, web: TreeWeb) -> None:
        try:
            body = _single(self.client.get_json(self._api(
                web.url, "web/rootfolder?$select=WelcomePage")))
        except RestError as exc:
            self._error(SOURCE_WELCOME, exc)
            return
        page = str(body.get("WelcomePage") or "").lstrip("/")
        if not page:
            return
        path = web.server_relative_url.rstrip("/") + "/" + page.split("?")[0]
        web.welcome_page = self._abs(path)
        self.candidates.append(_Candidate(web.welcome_page, SOURCE_WELCOME,
                                          web=web.url))

    def page_libraries(self, web: TreeWeb) -> None:
        read: set[str] = set()
        site_pages = web.server_relative_url.rstrip("/") + "/SitePages"
        primary_failed: RestError | None = None
        try:
            self._items(web, site_pages, SOURCE_SITEPAGES)
            read.add(_path_key(site_pages))
        except RestError as exc:
            primary_failed = exc
        # Libraries at another address: a renamed library, or a publishing
        # `Pages` library whose URL is localized (`Pagine`).
        filter_ = " or ".join(f"BaseTemplate eq {t}"
                              for t in _PAGE_LIBRARY_TEMPLATES)
        try:
            libs = list(self._paged(self._api(
                web.url, "web/lists?$select=Title,BaseTemplate,Hidden,"
                "RootFolder/ServerRelativeUrl&$expand=RootFolder"
                f"&$filter={quote(filter_)}")))
        except RestError as exc:
            if primary_failed is not None:
                self._error(SOURCE_SITEPAGES, primary_failed)
            self._error(SOURCE_SITEPAGES, exc)
            return
        found_any = False
        for lib in libs:
            root = _single(lib.get("RootFolder") or {})
            path = str(root.get("ServerRelativeUrl") or "")
            if not path or _path_key(path) in read:
                continue
            found_any = True
            try:
                self._items(web, path, SOURCE_SITEPAGES)
                read.add(_path_key(path))
            except RestError as exc:
                self._error(SOURCE_SITEPAGES, exc)
        if primary_failed is not None and primary_failed.status != 404 \
                and not found_any:
            self._error(SOURCE_SITEPAGES, primary_failed)

    def _items(self, web: TreeWeb, library_path: str, source: str,
               *, documents: bool = False) -> None:
        self._progress(source, self._abs(library_path))
        base = self._api(web.url, "web/GetList('"
                         + quote(_odata_string(library_path), safe="/")
                         + "')/items")
        fields = _ITEM_FIELDS if not documents else _ITEM_FIELDS_PLAIN
        try:
            rows = list(self._paged(f"{base}?$select={fields}&$top=500"))
        except RestError as exc:
            if exc.status != 400 or fields == _ITEM_FIELDS_PLAIN:
                raise
            # A library without the PromotedState column (publishing pages).
            rows = list(self._paged(
                f"{base}?$select={_ITEM_FIELDS_PLAIN}&$top=500"))
        for row in rows:
            ref = str(row.get("FileRef") or "")
            if not ref:
                continue
            if documents and len(self._documents_seen) >= self.max_documents:
                self.tree.truncated = True
                return
            self.candidates.append(_Candidate(
                url=self._abs(ref), source=source,
                title=str(row.get("Title") or row.get("FileLeafRef") or ""),
                web=web.url, modified=str(row.get("Modified") or ""),
                promoted_state=_int_or_none(row.get("PromotedState")),
                is_folder=str(row.get("FSObjType")) == "1"))
            if documents:
                self._documents_seen.add(ref.casefold())

    def document_libraries(self, web: TreeWeb) -> None:
        try:
            libs = list(self._paged(self._api(
                web.url, "web/lists?$select=Title,Hidden,"
                "RootFolder/ServerRelativeUrl&$expand=RootFolder&$filter="
                + quote(f"BaseTemplate eq {_DOCUMENT_LIBRARY_TEMPLATE} "
                        "and Hidden eq false"))))
        except RestError as exc:
            self._error(SOURCE_LIBRARY, exc)
            return
        for lib in libs:
            root = _single(lib.get("RootFolder") or {})
            path = str(root.get("ServerRelativeUrl") or "")
            if not path:
                continue
            try:
                self._items(web, path, SOURCE_LIBRARY, documents=True)
            except RestError as exc:
                self._error(SOURCE_LIBRARY, exc)

    def navigation(self, web: TreeWeb) -> None:
        for menu in ("QuickLaunch", "TopNavigationBar"):
            try:
                rows = list(self._paged(self._api(
                    web.url, f"web/navigation/{menu}?$expand=Children")))
            except RestError as exc:
                self._error(SOURCE_NAVIGATION, exc)
                continue
            stack = list(rows)
            while stack:
                node = stack.pop(0)
                if not isinstance(node, dict):
                    continue
                raw = str(node.get("Url") or "")
                if raw:
                    self.candidates.append(_Candidate(
                        url=urljoin(web.url + "/", raw),
                        source=SOURCE_NAVIGATION,
                        title=str(node.get("Title") or ""), web=web.url))
                stack.extend(_results(node.get("Children")))

    def search(self, root: TreeWeb) -> None:
        query = (f'path:"{root.url}" '
                 "contentclass:STS_ListItem_WebPageLibrary")
        if _path_key(root.server_relative_url) == "/":
            # `path:` on the root site matches the whole tenant.
            origin = root.url.rstrip("/")
            query += "".join(f' -path:"{origin}/{managed}"'
                             for managed in _MANAGED_PATHS)
        start = 0
        rowlimit = max(1, min(self.search_page_size, 500))
        while True:
            if self.max_pages and start >= self.max_pages * 2:
                self.tree.truncated = True
                return
            url = self._api(
                root.url,
                "search/query?querytext=" + quote(f"'{query}'", safe="")
                + "&selectproperties=" + quote(
                    "'Path,Title,LastModifiedTime,SPWebUrl'", safe="")
                + f"&rowlimit={rowlimit}&startrow={start}"
                "&trimduplicates=false")
            try:
                body = self.client.get_json(url)
            except RestError as exc:
                self._error(SOURCE_SEARCH, exc)
                return
            rows, total = _search_rows(body)
            for cells in rows:
                path = cells.get("Path") or ""
                if not path:
                    continue
                self.candidates.append(_Candidate(
                    url=path, source=SOURCE_SEARCH,
                    title=cells.get("Title") or "",
                    web=(cells.get("SPWebUrl") or "").rstrip("/"),
                    modified=cells.get("LastModifiedTime") or ""))
            start += len(rows)
            if len(rows) < rowlimit or (total is not None and start >= total):
                return

    # -- resolution

    def resolve(self) -> None:
        tree = self.tree
        pages: dict[str, TreePage] = {}
        ranks: dict[str, int] = {}
        docs: dict[str, TreeDocument] = {}
        welcome_by_web = {key: web.welcome_page
                          for key, web in self.web_paths.items()
                          if web.welcome_page}
        for cand in self.candidates:
            kind, value = self._classify(cand, welcome_by_web)
            if kind == "skip":
                tree.skipped.append(SkippedUrl(_redact(cand.url), value,
                                               cand.source))
                continue
            parsed = urlparse(value)
            key = _path_key(parsed.path)
            if kind == "document":
                if key not in docs:
                    docs[key] = TreeDocument(url=value, title=cand.title,
                                             web=cand.web, source=cand.source,
                                             modified=cand.modified)
                continue
            rank = _SOURCE_RANK.get(cand.source, 9)
            page = pages.get(key)
            if page is None:
                if self.max_pages and len(pages) >= self.max_pages:
                    tree.truncated = True
                    tree.skipped.append(SkippedUrl(value, SKIP_PAGE_LIMIT,
                                                   cand.source))
                    continue
                pages[key] = TreePage(url=value, title=cand.title,
                                      web=cand.web or self._web_of(key),
                                      source=cand.source,
                                      sources=(cand.source,),
                                      modified=cand.modified,
                                      promoted_state=cand.promoted_state)
                ranks[key] = rank
                continue
            if cand.source not in page.sources:
                page.sources = page.sources + (cand.source,)
            if rank < ranks[key]:
                # The better source's spelling is the canonical one.
                ranks[key] = rank
                page.url = value
                page.source = cand.source
                page.title = cand.title or page.title
                page.web = cand.web or page.web
            page.modified = page.modified or cand.modified
            if page.promoted_state is None:
                page.promoted_state = cand.promoted_state
            if not page.title:
                page.title = cand.title
        welcome = {_path_key(urlparse(u).path) for u in welcome_by_web.values()}
        tree.pages = sorted(pages.values(), key=lambda p: (
            0 if _path_key(urlparse(p.url).path) in welcome else 1,
            self._web_depth(p.web)))
        tree.documents = list(docs.values())

    def _web_depth(self, web_url: str) -> int:
        web = self.web_paths.get(_path_key(urlparse(web_url).path))
        return web.depth if web else 0

    def _web_of(self, path_key: str) -> str:
        best = None
        for key, web in self.web_paths.items():
            if _in_scope(path_key, key) and (best is None
                                             or len(key) > len(best[0])):
                best = (key, web)
        return best[1].url if best else ""

    def _web_depth_of(self, path_key: str) -> int:
        """How many path segments belong to the deepest web holding it."""
        best = ""
        for web_key in self.web_paths:
            if _in_scope(path_key, web_key) and len(web_key) > len(best):
                best = web_key
        return len([s for s in best.split("/") if s])

    def _web_spelling(self, path: str) -> str:
        """The path with its web part spelled as the web spells itself.

        A navigation link typed as `/SITES/PORTAL/...` opens the same page;
        the report should not show the editor's capitalization.
        """
        path = path.rstrip("/") or "/"
        key = path.casefold()
        best = ""
        for web_key in self.web_paths:
            if _in_scope(key, web_key) and len(web_key) > len(best):
                best = web_key
        if not best or best == "/":
            return path
        web = self.web_paths[best]
        return web.server_relative_url.rstrip("/") + path[len(best):]

    def _classify(self, cand: _Candidate, welcome_by_web) -> tuple[str, str]:
        raw = cand.url.strip()
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https"):
            return "skip", SKIP_NOT_HTTP
        host = (parsed.hostname or "").lower()
        if host == "linkless.header":
            return "skip", SKIP_NO_LINK
        if host != self.host:
            return "skip", SKIP_OTHER_HOST
        path = unquote(parsed.path)
        segments = [s for s in path.split("/") if s]
        if segments and _SHARING_SEGMENT.match(segments[0]):
            return "skip", SKIP_SHARING_LINK
        key = _path_key(path)
        if not _in_site(key, self.scope_key):
            return "skip", SKIP_OTHER_SITE
        lowered = [s.lower() for s in segments]
        if any(s in _SYSTEM_SEGMENTS for s in lowered):
            return "skip", SKIP_SYSTEM
        if cand.is_folder:
            return "skip", SKIP_FOLDER
        # `Lists`, `Forms` and `SitePages` mean something only inside a web:
        # a subsite may itself be called `Lists`.
        inner = lowered[self._web_depth_of(key):]
        if inner and inner[-1] in _LIST_VIEWS:
            return "skip", SKIP_LIST_VIEW
        if "forms" in inner or (inner and inner[-1] in _LIST_FORMS):
            return "skip", SKIP_LIST_FORM
        if "lists" in inner:
            return "skip", SKIP_LIST_VIEW
        if (len(inner) > 2 and inner[0] == "sitepages"
                and inner[1] == "templates"):
            return "skip", SKIP_PAGE_TEMPLATE
        canonical = self.origin + _encode_path(self._web_spelling(path))
        if key in welcome_by_web:
            return "page", welcome_by_web[key]
        if key in self.web_paths:
            # A web without a known home page: its address is the page.
            return "page", canonical
        leaf = lowered[-1] if lowered else ""
        if leaf.endswith(".aspx"):
            return "page", canonical
        if "." in leaf:
            return "document", canonical
        return "skip", SKIP_NOT_A_PAGE


def _search_rows(body) -> tuple[list[dict], int | None]:
    data = _single(body)
    if "query" in data and isinstance(data["query"], dict):
        data = data["query"]  # verbose: d.query.PrimaryQueryResult
    relevant = ((data.get("PrimaryQueryResult") or {})
                .get("RelevantResults") or {})
    total = _int_or_none(relevant.get("TotalRows"))
    table = relevant.get("Table") or {}
    out: list[dict] = []
    for row in _results(table.get("Rows")):
        cells = {}
        for cell in _results((row or {}).get("Cells")):
            if isinstance(cell, dict) and cell.get("Key"):
                value = cell.get("Value")
                cells[str(cell["Key"])] = "" if value is None else str(value)
        out.append(cells)
    return out, total


# --------------------------------------------------------------------------
# Public entry points


def session_from_cookies(cookies, site_url: str):
    """A Requests session carrying the person's signed-in cookies.

    Built by the crawler's own helper so both read the site with one cookie
    policy (host-only cookies stay host-only).
    """
    from crawler import CrawlConfig, http_session  # noqa: PLC0415

    return http_session(CrawlConfig(cookies=cookies or []), site_url)


def _walk_all(walk: _Walk, tree: SiteTree, root: TreeWeb, *,
              use_navigation: bool, use_search: bool,
              inventory_documents: bool) -> None:
    walk.webs(root)
    for web in list(tree.webs):
        walk.welcome(web)
        walk.page_libraries(web)
        if use_navigation:
            walk.navigation(web)
        if inventory_documents:
            walk.document_libraries(web)
    if use_search:
        walk.search(root)


def discover(site_url: str, session, *, max_pages: int = 2000,
             max_webs: int = 100, max_web_depth: int = 5,
             max_requests: int = 1500, max_documents: int = 5000,
             use_navigation: bool = True, use_search: bool = True,
             inventory_documents: bool = False, search_page_size: int = 500,
             timeout: float = 30.0, min_interval: float = 0.2,
             max_retries: int = 4, backoff_base: float = 2.0,
             max_wait: float = 120.0, max_duration: float = 1800.0,
             user_agent: str | None = None,
             sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.monotonic,
             wall_clock: Callable[[], float] = time.time,
             cancelled: Callable[[], bool] | None = None,
             progress_cb: Callable[[str, str], None] | None = None,
             ) -> SiteTree:
    """Every page of a SharePoint Online site and its subsites.

    ``session`` is a ``requests.Session`` that already carries the sign-in
    (see `session_from_cookies`), or anything with the same ``get`` - the
    signed-in browser's own transport (`audit.browser_fetch`) above all; it
    is not modified. ``site_url`` may be the
    site, a subsite or a page inside one - it is cut back to the web.

    ``max_duration`` (seconds, 0 for none) caps the whole walk, waits
    included; a ``Retry-After`` longer than ``max_wait`` is an error rather
    than an early retry.

    Never raises for an HTTP or sign-in failure: the outcome is in the
    returned tree (`SiteTree.status`, `errors`, `auth_required`,
    `access_denied`).
    """
    tree = SiteTree(site_url=_redact(site_url))
    client = _Client(session, host=urlparse(site_url).hostname or "",
                     user_agent=user_agent or default_user_agent(),
                     timeout=timeout, max_requests=max_requests,
                     min_interval=min_interval, max_retries=max_retries,
                     backoff_base=backoff_base, max_wait=max_wait,
                     sleep=sleep, clock=clock, wall_clock=wall_clock,
                     cancelled=cancelled)
    if max_duration:
        client.deadline = clock() + max_duration
    walk = _Walk(site_url, client, tree, max_pages=max_pages,
                 max_webs=max_webs, max_web_depth=max_web_depth,
                 max_documents=max_documents, use_navigation=use_navigation,
                 use_search=use_search,
                 inventory_documents=inventory_documents,
                 progress_cb=progress_cb, search_page_size=search_page_size)
    try:
        try:
            root = walk.root()
        except RestError as exc:
            if exc.status == 403:
                # A bare 403 on the site itself. A missing or expired
                # session announces itself (401, the forms-auth header, a
                # redirect to sign in) and is caught as `AuthRequired`
                # before this; what is left is a session that works and has
                # no permission here - the weak 403 of `audit.authwall`.
                tree.access_denied = True
                tree.errors.append(TreeError(
                    source="access", url=exc.url, status=403,
                    message="access denied: signed in, but without "
                            "permission on this site"))
            else:
                walk._error("web", exc)
            root = None
        if root is not None:
            tree.web = root
            _walk_all(walk, tree, root, use_navigation=use_navigation,
                      use_search=use_search,
                      inventory_documents=inventory_documents)
    except AuthRequired as exc:
        tree.auth_required = True
        tree.auth_reason = exc.reason
        tree.errors.append(TreeError(source="auth", url=exc.url,
                                     message="sign-in required or expired"))
        applog.warning("sharepoint_tree.auth_required", reason=exc.reason,
                       url=exc.url)
    except _BudgetExhausted:
        tree.truncated = True
        tree.errors.append(TreeError(source="budget", url="",
                                     message="request budget exhausted"))
    except _DeadlineReached:
        tree.truncated = True
        tree.errors.append(TreeError(source="budget", url="",
                                     message="time budget exhausted"))
    except _Cancelled:
        tree.truncated = True
    finally:
        tree.requests_made = client.requests_made
    # Resolved even after a sign-in failure: what was read before the session
    # expired is kept, and `status` still says the tree is not complete.
    walk.resolve()
    applog.info("sharepoint_tree.done", site=tree.site_url, status=tree.status,
                pages=len(tree.pages), webs=len(tree.webs),
                documents=len(tree.documents), skipped=len(tree.skipped),
                errors=len(tree.errors), requests=tree.requests_made)
    return tree
