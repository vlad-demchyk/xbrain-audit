"""A window where a person signs in to the site themselves.

Nothing else in this application handles anybody's credentials, and this
does not either: it opens a real browser view on the site's own sign-in
page, and whatever the site gives that browser is what the run will use.
2FA, SSO, a captcha, a corporate identity provider - all of them work here
for the same reason they work in a browser, because this *is* one.

Two things it must get right:

* **The profile is persistent and named after the host.** An off-the-record
  profile is the right default for auditing a stranger's site and the wrong
  one here: the session would not survive the window closing. See
  `audit.driver.open_session_profile` and `site_session`.
* **The fetcher gets the session too.** The crawl reads pages with
  `requests`, which shares no storage with QtWebEngine, so the cookies are
  copied across as they arrive. Without that half, the browser sees the
  account and the crawl sees the login form - one run, two answers.

* **The fetcher gets only the site's cookies.** The browser profile keeps
  everything, the identity provider's cookies included, because that is
  what lets it sign in again silently next time. The copy written for the
  fetcher is narrowed to the site's host and its parent domains - and for
  SharePoint Online to the tenant's own two hosts (`<tenant>.sharepoint.com`
  and `<tenant>-my.sharepoint.com`). A Microsoft sign-in cookie
  (`ESTSAUTH*` on `login.microsoftonline.com`) is the person's whole
  Microsoft account; it has no business in a file a crawl reads.

* **The profile holds the site and the sign-in, nothing else.** The
  profile is named after the host and keeps what it is given, so a person
  who followed a link elsewhere in this window left that other site's
  cookies in it. A top-level navigation is kept here only when it goes to
  the site (for SharePoint Online: the tenant's two hosts), to an identity
  provider, to a host Microsoft's sign-in and MFA set-up use, or to a host
  the sign-in itself led to (a server redirect, or a form or script on a
  sign-in page - how a federated ADFS or another identity provider is
  reached). Anything else opens in the system browser. See
  `navigation_decision`.

What is deliberately *not* here: any attempt to fill the form, remember a
password, or detect which field is which. The window is a browser and the
person is the one signing in.
"""
from __future__ import annotations

from urllib.parse import urlparse

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout,
)

import project_profile
import site_session
from audit import authwall
from i18n.translations import t

#: Where the window is in a sign-in, as `sign_in_stage` reports it.
STAGE_IDENTITY_PROVIDER = "identity-provider"
STAGE_SITE = "site"
STAGE_ELSEWHERE = "elsewhere"

def _text(key: str, lang: str, **fields) -> str:
    return t(key, lang, **fields)


def _later(ms: int, callback) -> None:
    """Run `callback` on the event loop after `ms`. A seam for tests."""
    from PySide6.QtCore import QTimer

    QTimer.singleShot(ms, callback)


#: How long the store gets to report what `loadAllCookies` asked for.
RECHECK_MS = 1500


def _profile_storage(host: str) -> str:
    """The folder of `host`'s profile if it exists, else `""`. Creates nothing."""
    try:
        path = site_session.profile_dir(host)
    except Exception:  # noqa: BLE001 - a profile of another host: no snapshot
        return ""
    return str(path) if path.is_dir() else ""


def _bare_host(host_or_url: str) -> str:
    return project_profile._host_of(host_or_url)


# The fetcher's filter lives where the file is written: `site_session`.
from site_session import cookie_is_for_fetcher, cookies_for_fetcher  # noqa: E402,F401


#: Hosts a Microsoft sign-in passes through that are not an identity
#: provider in `authwall`'s sense: the MFA set-up and security-info pages
#: (`aka.ms/mfasetup` lands on them), seamless SSO, the device-code page,
#: password reset, and a personal account's own pages. Kept apart from
#: `authwall.IDENTITY_PROVIDER_HOSTS` on purpose: that list also decides
#: when "Done" is offered and which cookies the fetcher never gets.
SIGN_IN_FLOW_HOSTS = (
    "aka.ms",
    "mysignins.microsoft.com",
    "account.activedirectory.windowsazure.com",
    "autologon.microsoftazuread-sso.com",
    "device.login.microsoftonline.com",
    "microsoft.com",  # microsoft.com/devicelogin, the device-code page
    "www.microsoft.com",
    "passwordreset.microsoftonline.com",
    "account.live.com",
    "account.microsoft.com",
    "login.microsoftonline.us",
)

#: What `navigation_decision` answers.
NAV_ALLOW = "allow"
NAV_EXTERNAL = "external"

#: Navigation kinds, independent of Qt's enum (`_NAV_KINDS` maps it).
NAV_LINK = "link"
NAV_TYPED = "typed"
NAV_FORM = "form"
NAV_BACK_FORWARD = "back-forward"
NAV_RELOAD = "reload"
NAV_REDIRECT = "redirect"
NAV_OTHER = "other"

#: Schemes that never leave the page: let them be.
_INERT_SCHEMES = ("about", "data", "blob", "javascript")


def _site_of(host: str) -> str:
    """A guess at the registrable domain, for a site that is not SharePoint.

    The last two labels, or three under a two-letter country code with a
    short second level (`example.co.uk`). A guess, used only to let a site's
    own sign-in host (`sso.example.com` for `app.example.com`) stay in the
    window; it never decides which cookies the fetcher gets.
    """
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return host
    if len(labels[-1]) == 2 and len(labels[-2]) <= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _is_sign_in_flow_host(host: str) -> bool:
    return (authwall.is_identity_provider_host(host)
            or host in SIGN_IN_FLOW_HOSTS)


def _belongs_to_site(host: str, site_host: str) -> bool:
    target = _bare_host(site_host)
    if not host or not target:
        return False
    if host == target:
        return True
    tenant_hosts = project_profile.sharepoint_tenant_hosts(target)
    if tenant_hosts:
        # `.sharepoint.com` is every tenant's parent: only the tenant's own.
        return host in tenant_hosts
    site = _site_of(target)
    return "." in site and (host == site or host.endswith("." + site))


def navigation_decision(url: str, site_host: str, *, kind: str = NAV_LINK,
                        from_url: str = "", learned=None) -> str:
    """Should a top-level navigation to `url` stay in the sign-in window?

    `NAV_ALLOW` for the site, an identity provider, a host of Microsoft's
    sign-in and MFA set-up, a host this sign-in already led to (`learned`),
    and any address that is a sign-in step by its path (ADFS, an OAuth
    authorize endpoint). A host the sign-in leads to - a server redirect, or
    a form or script on a page that is not the site's own (the identity
    provider handing over to a federated one) - is allowed and added to
    `learned`, so its own pages work too. Everything else, a link a person
    clicked on the site above all, is `NAV_EXTERNAL`: opened in the system
    browser, and its cookies never reach this host's profile.
    """
    learned = learned if learned is not None else set()
    parsed = urlparse(url or "")
    scheme = (parsed.scheme or "").lower()
    if scheme in _INERT_SCHEMES or not scheme:
        return NAV_ALLOW
    if scheme not in ("http", "https"):
        return NAV_EXTERNAL  # mailto:, an app's own scheme: not a page here
    host = (parsed.hostname or "").lower().rstrip(".")
    if (_belongs_to_site(host, site_host) or _is_sign_in_flow_host(host)
            or host in learned):
        return NAV_ALLOW
    if kind in (NAV_BACK_FORWARD, NAV_RELOAD):
        return NAV_ALLOW  # in the history only because it was let in
    if authwall.is_definite_login_url(url):
        learned.add(host)
        return NAV_ALLOW
    from_host = (urlparse(from_url or "").hostname or "").lower().rstrip(".")
    mid_sign_in = (not from_host or not _belongs_to_site(from_host, site_host)
                   or authwall.is_definite_login_url(from_url))
    if kind == NAV_REDIRECT or (kind in (NAV_FORM, NAV_OTHER) and mid_sign_in):
        learned.add(host)
        return NAV_ALLOW
    return NAV_EXTERNAL


def _open_external(url: str) -> None:
    """Hand `url` to the system browser. A seam for tests."""
    from PySide6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl(url))


def _nav_kind(qt_type) -> str:
    """Qt's navigation type as one of the `NAV_*` kinds."""
    name = str(getattr(qt_type, "name", qt_type) or "")
    for marker, kind in (("LinkClicked", NAV_LINK), ("Typed", NAV_TYPED),
                         ("FormSubmitted", NAV_FORM),
                         ("BackForward", NAV_BACK_FORWARD),
                         ("Reload", NAV_RELOAD), ("Redirect", NAV_REDIRECT)):
        if marker in name:
            return kind
    return NAV_OTHER


def sign_in_stage(url: str, site_host: str) -> str:
    """Is the window on the identity provider, back on the site, or elsewhere?"""
    if authwall.is_definite_login_url(url):
        return STAGE_IDENTITY_PROVIDER
    host = _bare_host(url)
    target = _bare_host(site_host)
    if host and (host == target
                 or host in project_profile.sharepoint_tenant_hosts(target)):
        return STAGE_SITE
    return STAGE_ELSEWHERE


class SiteSignInDialog(QDialog):
    """Sign in to `url` in a real browser view, and keep the session."""

    #: How big the view has to be for a real sign-in page - including the
    #: identity provider's, which is usually the taller of the two.
    SIZE = (980, 760)

    def __init__(self, url: str, lang: str = "uk", parent=None):
        super().__init__(parent)
        self.lang = lang
        self.url = url
        self.host = site_session.host_of(url)
        self.saved = False
        #: Whether Done had been pressed for this host before this window:
        #: Cancel must not take away a session the person already had.
        self._had_session = site_session.has_session(self.host)
        #: Collected as the site sets them, because `allCookies()` is not a
        #: question a cookie store answers synchronously.
        self._cookies: dict[tuple[str, str, str], dict] = {}
        self._page = None
        #: Hosts this sign-in led to, kept for the window's life.
        self._learned_hosts: set[str] = set()

        self.setWindowTitle(t("sign_in_site_title", lang, host=self.host))
        self.resize(*self.SIZE)

        layout = QVBoxLayout(self)
        note = QLabel(t("sign_in_site_note", lang, host=self.host))
        note.setWordWrap(True)
        layout.addWidget(note)

        from PySide6.QtWebEngineWidgets import QWebEngineView

        from audit import driver

        # The session this profile already holds is read from its file
        # *before* the profile is opened, for two reasons checked on
        # Windows with PySide6 6.12: a cookie restored from disk is never
        # reported by `cookieAdded`, `loadAllCookies()` included, so a person
        # signed in last time is signed in here with nothing collected; and
        # once QtWebEngine holds the profile, every other open of that file
        # is refused, so reading it at Done finds nothing. What the site sets
        # from now on arrives through the signals and replaces this.
        self._take_from_profile_file(_profile_storage(self.host))
        self.profile = driver.open_session_profile(self.host, parent=self)
        self.view = QWebEngineView(self)
        self._attach_page()
        layout.addWidget(self.view, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QDialogButtonBox(self)
        self.done_btn = buttons.addButton(t("sign_in_site_done", lang),
                                          QDialogButtonBox.ButtonRole.AcceptRole)
        self.forget_btn = buttons.addButton(t("sign_in_site_forget", lang),
                                            QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.done_btn.clicked.connect(self._on_done)
        self.forget_btn.clicked.connect(self._on_forget)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)

        self.view.urlChanged.connect(self._on_url_changed)
        self.view.load(QUrl(self.url))

    def _attach_page(self) -> None:
        from PySide6.QtWebEngineCore import QWebEnginePage

        dialog = self

        class _GuardedPage(QWebEnginePage):
            """A page that keeps top-level navigation on the sign-in."""

            def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802 - Qt's name
                if not is_main_frame:
                    return True  # a frame's address is not this window's
                return dialog._accept_navigation(
                    url.toString(), _nav_kind(nav_type), self.url().toString())

        page = _GuardedPage(self.profile, self)
        self._page = page
        self.view.setPage(page)
        store = self.profile.cookieStore()
        store.cookieAdded.connect(self._on_cookie)
        store.cookieRemoved.connect(self._on_cookie_removed)
        # `cookieAdded` reports what is set from now on. A profile that was
        # signed in last time already holds its cookies, and without this
        # they never reach `_cookies`: Done would save an empty session for
        # a person who is visibly signed in.
        store.loadAllCookies()

    def _accept_navigation(self, url: str, kind: str, from_url: str) -> bool:
        """Keep the navigation here, or send it to the system browser."""
        learned = getattr(self, "_learned_hosts", None)
        if learned is None:
            learned = self._learned_hosts = set()
        decision = navigation_decision(url, self.host, kind=kind,
                                       from_url=from_url, learned=learned)
        if decision == NAV_ALLOW:
            return True
        _open_external(url)
        target = (urlparse(url).hostname or url) if url else ""
        self.status.setText(_text("sign_in_site_elsewhere", self.lang,
                                  host=self.host, target=target))
        return False

    def _on_url_changed(self, qurl) -> None:
        """Say where the sign-in is, and offer Done only off the provider."""
        url = qurl.toString() if hasattr(qurl, "toString") else str(qurl)
        stage = sign_in_stage(url, self.host)
        self.done_btn.setEnabled(stage != STAGE_IDENTITY_PROVIDER)
        if stage == STAGE_IDENTITY_PROVIDER:
            self.status.setText(_text("sign_in_site_on_idp", self.lang,
                                      host=self.host))
        elif stage == STAGE_SITE:
            self.done_btn.setDefault(True)
            self.status.setText(_text("sign_in_site_back", self.lang,
                                      host=self.host))

    # ------------------------------------------------------------- cookies
    @staticmethod
    def _cookie_record(cookie) -> dict:
        domain = (cookie.domain() or "").lower()
        expires = None
        if not cookie.isSessionCookie():
            expiration = cookie.expirationDate()
            if expiration.isValid():
                expires = int(expiration.toSecsSinceEpoch())
        policy = cookie.sameSitePolicy()
        return {
            "name": bytes(cookie.name()).decode("utf-8", "replace"),
            "value": bytes(cookie.value()).decode("utf-8", "replace"),
            "domain": domain,
            "path": cookie.path() or "/",
            "secure": cookie.isSecure(),
            "http_only": cookie.isHttpOnly(),
            "same_site": getattr(policy, "name", "Default"),
            "expires": expires,
            "host_only": not domain.startswith("."),
        }

    @staticmethod
    def _cookie_key(record: dict) -> tuple[str, str, str]:
        return record["name"], record["domain"], record["path"]

    def _on_cookie(self, cookie) -> None:
        record = self._cookie_record(cookie)
        self._cookies[self._cookie_key(record)] = record

    def _on_cookie_removed(self, cookie) -> None:
        """Forget a cookie - the one that was removed, not its successor.

        An overwrite is reported as a removal of the old value and an
        addition of the new one, under the same name, domain and path. Those
        two signals are not promised in that order, and popping by key alone
        threw away the new value whenever the removal arrived second: a
        session cookie rewritten during the sign-in was gone by Done.
        """
        record = self._cookie_record(cookie)
        key = self._cookie_key(record)
        held = self._cookies.get(key)
        if held is not None and held.get("value") == record.get("value"):
            self._cookies.pop(key, None)

    # ------------------------------------------------------------- actions
    def _on_done(self) -> None:
        """Keep what the browser was given, and say what was kept.

        The count is the only thing shown - never a name and never a value.
        A dialog that prints a session cookie has handed the session to
        whoever is looking at the screen, and to whoever reads the
        screenshot afterwards.

        For SharePoint Online a session is known to need two cookies
        (`site_session.SHAREPOINT_SESSION_COOKIES`). They come from the
        signals, or from the profile's file read when the window opened.
        When neither had both, three things are tried: ask the store for
        everything it holds again and look once more after `RECHECK_MS`;
        then read the two names from the profile's file again (works where
        the open profile does not lock it - not on Windows); then say the
        sign-in is not complete and save nothing - "session stored" over
        half a session is a run that audits the sign-in page.
        """
        kept = cookies_for_fetcher(self.host, self._cookies.values())
        missing = site_session.missing_session_cookies(self.host, kept)
        if missing and not getattr(self, "_rechecked", False):
            self._rechecked = True
            self.done_btn.setEnabled(False)
            self.status.setText(_text("sign_in_site_checking", self.lang,
                                      host=self.host))
            try:
                self.profile.cookieStore().loadAllCookies()
            except Exception:  # noqa: BLE001 - the file read below still runs
                pass
            _later(RECHECK_MS, self._on_done)
            return
        if missing:
            self._take_from_profile_file()
            kept = cookies_for_fetcher(self.host, self._cookies.values())
            missing = site_session.missing_session_cookies(self.host, kept)
        if missing:
            self._rechecked = False
            self.done_btn.setEnabled(True)
            self.status.setText(_text("sign_in_site_incomplete", self.lang,
                                      host=self.host))
            return
        site_session.save_cookies(self.host, kept)
        self.saved = True
        self.status.setText(t("sign_in_site_saved", self.lang,
                              host=self.host, count=len(kept)))
        self.accept()

    def _take_from_profile_file(self, storage=None) -> None:
        """Fill in the session cookies from the profile's cookie file.

        Never over a cookie the signals reported: theirs is the newer value.
        """
        if storage is None:
            try:
                storage = self.profile.persistentStoragePath()
            except Exception:  # noqa: BLE001 - an off-the-record profile has none
                return
        if not storage:
            return
        for record in site_session.read_profile_cookies(storage, self.host):
            self._cookies.setdefault(self._cookie_key(record), record)

    def _on_forget(self) -> None:
        site_session.forget(self.host)
        self._cookies.clear()
        self.saved = False
        self.status.setText(t("sign_in_site_forgotten", self.lang, host=self.host))

    def _drop_what_was_not_confirmed(self) -> None:
        """Leave nothing behind from a sign-in that was not confirmed.

        Cancel and the title-bar button mean "not this". The fetcher's copy
        is only ever written by Done, and `site_session.has_session` reads
        that copy, so a scan never uses the browser profile of a window that
        was walked away from. When there was no session before, the cookies
        the page set in the profile are deleted as well, so the next window
        does not open already half signed in.
        """
        if self.saved or self._had_session:
            return
        try:
            self.profile.cookieStore().deleteAllCookies()
        except Exception:  # noqa: BLE001 - a profile already gone is fine
            pass
        self._cookies.clear()

    def _release_page(self) -> None:
        """Detach the page from the view before the dialog goes away."""
        try:
            store = self.profile.cookieStore()
            store.cookieAdded.disconnect(self._on_cookie)
            store.cookieRemoved.disconnect(self._on_cookie_removed)
        except Exception:  # noqa: BLE001 - already gone is fine
            pass
        # Order matters and Qt says so out loud: releasing a profile whose
        # page is still alive prints "Release of profile requested but
        # WebEnginePage still not deleted. Expect troubles!" - and the
        # troubles are a renderer process outliving the dialog.
        self.view.setPage(None)
        if self._page is not None:
            self._page.setParent(None)
            self._page.deleteLater()
            self._page = None

    def done(self, result: int) -> None:  # noqa: D102 - Qt's name
        # Every way out passes here: Done (accept), Cancel, Escape and the
        # title-bar button (closeEvent -> reject).
        if result != QDialog.DialogCode.Accepted:
            self._drop_what_was_not_confirmed()
        if self._page is not None:
            self._release_page()
        super().done(result)
