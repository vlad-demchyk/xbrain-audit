"""GET requests made by the signed-in browser profile itself.

The browser-mode session: the cookies a site gave the sign-in window never
leave the QtWebEngine profile they were given to. A request that has to be
made as the person - SharePoint's REST API above all - is made *by that
profile*: a hidden page on it opens the site, and `fetch(url, {credentials:
"include"})` runs in that page. Whatever the site needs (HttpOnly session
cookies, a parent-domain cookie, a token the page refreshed on load) goes
with the request the way it goes with any request the person's browser
makes, and nothing is copied out to do it.

Shaped like the slice of `requests.Session` that `sharepoint_tree` uses
(`get(url, headers=, timeout=, allow_redirects=)` returning something with
`status_code`, `headers`, `text`, `json()`), so the throttling, retry,
budget and sign-in detection there stay one implementation for both modes.

Not tied to SharePoint: any host whose profile is signed in can be read
this way (`site_session.SESSION_BROWSER`).

Everything runs on the Qt thread, like `driver.html_renderer`: a call waits
for its answer in a nested event loop, which keeps the application's own
loop turning instead of blocking it. Called from any other thread it
refuses rather than crash QtWebEngine.

What it never does: log or return a cookie, put a response body in a log,
or read anything from another origin than the page it opened.
"""
from __future__ import annotations

import itertools
import json
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from requests.structures import CaseInsensitiveDict

#: Response headers handed back to the caller - the ones a decision is made
#: on. A fetch can read every header of a same-origin answer; the rest are
#: not needed and stay in the page.
RESPONSE_HEADERS = ("content-type", "retry-after",
                    "x-forms_based_auth_required", "x-msdavext_error",
                    "location", "www-authenticate")
#: Request headers a page's `fetch` may set and that mean something here.
#: `User-Agent` is not one: Chromium sends its own.
_REQUEST_HEADERS = ("accept", "accept-language")

#: Set on a redirect `fetch` could not show (`redirect: "manual"` gives an
#: opaque answer): `same-site` when following it stayed on the page's origin
#: (and `Location` says where it ended), `off-site` when following it left
#: the origin - which, for a signed-in request, is the identity provider.
REDIRECT_HEADER = "X-XAnalyze-Redirect"
REDIRECT_OFF_SITE = "off-site"
REDIRECT_SAME_SITE = "same-site"

#: How often the parked answer is looked for.
POLL_MS = 50
#: How long opening the site may take before the transport gives up.
LOAD_TIMEOUT_S = 60.0

_ids = itertools.count(1)


class BrowserFetchError(RuntimeError):
    """The browser could not be used at all (no Qt, wrong thread)."""


@dataclass
class BrowserResponse:
    """What a `fetch` answered, shaped like a `requests.Response`."""
    status_code: int
    url: str = ""
    text: str = ""
    headers: CaseInsensitiveDict = field(default_factory=CaseInsensitiveDict)

    def json(self):
        try:
            return json.loads(self.text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"not JSON: {exc}") from None


def _origin(url: str) -> str:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port else ""
    return f"{(parsed.scheme or '').lower()}://{host}{port}"


def _fetch_script(slot: int, url: str, headers: dict, timeout_ms: int,
                  redirect: str) -> str:
    """The JavaScript that starts one fetch and parks its answer."""
    wanted = json.dumps(list(RESPONSE_HEADERS))
    return f"""
(function() {{
  var box = (window.__xanalyzeFetch = window.__xanalyzeFetch || {{}});
  var key = {json.dumps(str(slot))};
  box[key] = null;
  var park = function(value) {{ box[key] = JSON.stringify(value); }};
  try {{
    var controller = new AbortController();
    setTimeout(function() {{ controller.abort(); }}, {int(timeout_ms)});
    fetch({json.dumps(url)}, {{
      method: "GET", credentials: "include", cache: "no-store",
      redirect: {json.dumps(redirect)}, headers: {json.dumps(headers)},
      signal: controller.signal
    }}).then(function(r) {{
      var picked = {{}};
      {wanted}.forEach(function(name) {{
        var value = r.headers.get(name);
        if (value !== null) {{ picked[name] = value; }}
      }});
      return r.text().then(function(body) {{
        park({{ok: true, status: r.status, type: r.type, url: r.url,
              redirected: r.redirected, headers: picked, body: body}});
      }});
    }}, function(err) {{
      park({{ok: false, error: (err && err.name) || String(err)}});
    }});
  }} catch (err) {{
    park({{ok: false, error: (err && err.name) || String(err)}});
  }}
  return true;
}})()
"""


def _take_script(slot: int) -> str:
    key = json.dumps(str(slot))
    return (f"(function() {{ var box = window.__xanalyzeFetch || {{}};"
            f" var value = box[{key}];"
            f" if (value) {{ delete box[{key}]; }}"
            f" return value || null; }})()")


class BrowserTransport:
    """GET through a hidden page on a (signed-in) QtWebEngine profile.

    `profile` is the host's session profile (`driver.session_profile`);
    `None` means there is no signed-in profile, and every request then
    answers as SharePoint answers a stranger - `403` with
    `X-Forms_Based_Auth_Required` - so the caller's sign-in handling says
    "sign in" rather than auditing a sign-in page.
    """

    #: Script world the fetches run in: not the page's own, so nothing the
    #: site runs can see or touch what is parked there.
    WORLD_ID = 1

    def __init__(self, site_url: str, profile=None, *,
                 load_timeout: float = LOAD_TIMEOUT_S):
        self.site_url = site_url
        self.profile = profile
        self.load_timeout = load_timeout
        self.origin = _origin(site_url)
        self._page = None
        self._opened = False
        #: Why requests answer "sign in" without being made, or `""`.
        self.signed_out = "" if profile is not None else "no signed-in profile"
        #: Where opening the site ended, for a diagnosis. An address, never
        #: a value.
        self.landed = ""
        self.requests_made = 0

    # ----------------------------------------------------------- lifecycle
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    @staticmethod
    def _check_thread() -> None:
        try:
            from PySide6.QtCore import QCoreApplication, QThread
        except ImportError as exc:
            raise BrowserFetchError(f"QtWebEngine is not available: {exc}") from None
        app = QCoreApplication.instance()
        if app is None:
            raise BrowserFetchError("no Qt application")
        if QThread.currentThread() is not app.thread():
            raise BrowserFetchError(
                "the browser can only be used from the Qt thread")

    def open(self) -> None:
        """Open the site in a hidden page, so fetches carry its origin."""
        if self._opened:
            return
        self._opened = True
        if self.profile is None:
            return
        self._check_thread()
        from PySide6.QtCore import QEventLoop, QTimer, QUrl
        from PySide6.QtWebEngineCore import QWebEnginePage

        from audit import authwall

        self._page = QWebEnginePage(self.profile)
        loop = QEventLoop()
        outcome = {}

        def finished(ok):
            outcome["ok"] = bool(ok)
            loop.quit()

        self._page.loadFinished.connect(finished)
        QTimer.singleShot(int(self.load_timeout * 1000), loop.quit)
        self._page.load(QUrl(self.site_url))
        loop.exec()
        try:
            self._page.loadFinished.disconnect(finished)
        except Exception:  # noqa: BLE001 - already gone is fine
            pass
        self.landed = self._page.url().toString()
        if "ok" not in outcome:
            # Slow, not signed out: the page's origin is set, and the
            # fetches will say what the site says.
            self._page.triggerAction(QWebEnginePage.WebAction.Stop)
        if authwall.is_definite_login_url(self.landed):
            self.signed_out = "the site opened on its sign-in page"
        elif _origin(self.landed) != self.origin and self.landed:
            self.signed_out = "the site opened somewhere else"

    def close(self) -> None:
        if self._page is not None:
            try:
                self._page.triggerAction(self._page.WebAction.Stop)
            except Exception:  # noqa: BLE001
                pass
            self._page.deleteLater()
            self._page = None

    # ------------------------------------------------------------ requests
    def sleep(self, seconds: float) -> None:
        """Wait without stopping the event loop (for `discover(sleep=)`)."""
        if seconds <= 0:
            return
        try:
            from PySide6.QtCore import QEventLoop, QTimer
        except ImportError:
            time.sleep(seconds)
            return
        loop = QEventLoop()
        QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()

    def get(self, url: str, headers=None, timeout: float = 30,
            allow_redirects: bool = False, **_ignored) -> BrowserResponse:
        """GET `url` as the signed-in browser. Same-origin only."""
        self.open()
        if self.signed_out:
            return BrowserResponse(
                403, url=url, text="",
                headers=CaseInsensitiveDict({
                    "X-Forms_Based_Auth_Required": "true"}))
        if _origin(url) != self.origin:
            # The page's cookies are its origin's; anything else is not a
            # request this transport makes.
            raise requests.ConnectionError("another origin than the site")
        sent = {name: value for name, value in (headers or {}).items()
                if name.lower() in _REQUEST_HEADERS}
        redirect = "follow" if allow_redirects else "manual"
        answer = self._run(url, sent, timeout, redirect)
        if answer.get("ok") and answer.get("type") == "opaqueredirect":
            # `manual` hides where a redirect goes. Follow it once to find
            # out: staying on the origin gives the address; leaving it fails
            # (the identity provider does not answer this origin's fetch).
            followed = self._run(url, sent, timeout, "follow")
            if followed.get("ok"):
                return BrowserResponse(
                    302, url=url, text="",
                    headers=CaseInsensitiveDict({
                        "Location": followed.get("url") or "",
                        REDIRECT_HEADER: REDIRECT_SAME_SITE}))
            return BrowserResponse(
                302, url=url, text="",
                headers=CaseInsensitiveDict({REDIRECT_HEADER: REDIRECT_OFF_SITE}))
        if not answer.get("ok"):
            error = str(answer.get("error") or "fetch failed")
            if error == "AbortError":
                raise requests.Timeout(f"browser fetch timed out after {timeout}s")
            raise requests.ConnectionError(f"browser fetch failed: {error}")
        return BrowserResponse(
            int(answer.get("status") or 0), url=str(answer.get("url") or url),
            text=str(answer.get("body") or ""),
            headers=CaseInsensitiveDict(answer.get("headers") or {}))

    def _run(self, url: str, headers: dict, timeout: float, redirect: str) -> dict:
        """Start one fetch in the page and wait for its parked answer."""
        self._check_thread()
        from PySide6.QtCore import QEventLoop, QTimer

        slot = next(_ids)
        timeout_ms = max(1000, int((timeout or 30) * 1000))
        deadline = time.monotonic() + timeout_ms / 1000 + 5
        loop = QEventLoop()
        result = {}

        def read(value):
            if value:
                try:
                    result.update(json.loads(value))
                except (TypeError, ValueError):
                    result.update(ok=False, error="unreadable answer")
                loop.quit()
                return
            if time.monotonic() >= deadline:
                result.update(ok=False, error="AbortError")
                loop.quit()
                return
            QTimer.singleShot(POLL_MS, poll)

        def poll():
            if self._page is None:
                result.update(ok=False, error="page closed")
                loop.quit()
                return
            self._page.runJavaScript(_take_script(slot), self.WORLD_ID, read)

        self.requests_made += 1
        self._page.runJavaScript(
            _fetch_script(slot, url, headers, timeout_ms, redirect),
            self.WORLD_ID, lambda _ignored: poll())
        loop.exec()
        return result


def transport_for(site_url: str, *, profile=None) -> BrowserTransport:
    """A transport on the host's signed-in profile (`None` profile: signed out).

    The profile is the one the renderer uses - one per host per process,
    from `driver.session_profile` - so the hidden page and the rendered
    pages are the same browser.
    """
    if profile is None:
        import site_session
        from audit import driver

        driver.ensure_headless_application()
        # Before the profile is touched: a profile made off the Qt thread
        # is the crash this refuses to cause.
        BrowserTransport._check_thread()
        profile = driver.session_profile(site_session.host_of(site_url))
    return BrowserTransport(site_url, profile)


def discover_in_browser(site_url: str, session=None, *, profile=None, **kwargs):
    """`sharepoint_tree.discover`, with its requests made by the browser.

    Same call shape as `discover(site_url, session, ...)` so a caller swaps
    one for the other; `session` is ignored - the session is the profile's.
    Waits (`sleep`) through the event loop rather than blocking it.
    """
    import sharepoint_tree

    with transport_for(site_url, profile=profile) as transport:
        kwargs.setdefault("sleep", transport.sleep)
        return sharepoint_tree.discover(site_url, transport, **kwargs)
