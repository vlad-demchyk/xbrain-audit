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

What is deliberately *not* here: any attempt to fill the form, remember a
password, or detect which field is which. The window is a browser and the
person is the one signing in.
"""
from __future__ import annotations

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

#: Sentences this window needs before the shared dictionary carries them.
#: `t()` wins as soon as `i18n.translations` has the key.
_FALLBACK = {
    "sign_in_site_on_idp": {
        "uk": "Завершіть вхід у цьому вікні. «Готово» стане доступною, коли сторінка повернеться на {host}.",
        "it": "Completa l'accesso in questa finestra. «Fatto» sarà disponibile quando la pagina tornerà su {host}.",
        "en": "Finish signing in in this window. \"Done\" becomes available once the page is back on {host}.",
    },
    "sign_in_site_back": {
        "uk": "Ви знову на {host}. Якщо бачите сайт, а не форму входу, натисніть «Готово».",
        "it": "Sei di nuovo su {host}. Se vedi il sito e non il modulo di accesso, premi «Fatto».",
        "en": "You are back on {host}. If you see the site rather than a sign-in form, press \"Done\".",
    },
}


def _text(key: str, lang: str, **fields) -> str:
    text = t(key, lang, **fields)
    if text != key:
        return text
    entry = _FALLBACK.get(key, {})
    template = entry.get(lang) or entry.get("en") or key
    return template.format(**fields)


def _bare_host(host_or_url: str) -> str:
    return project_profile._host_of(host_or_url)


# The fetcher's filter lives where the file is written: `site_session`.
from site_session import cookie_is_for_fetcher, cookies_for_fetcher  # noqa: E402,F401


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

        self.setWindowTitle(t("sign_in_site_title", lang, host=self.host))
        self.resize(*self.SIZE)

        layout = QVBoxLayout(self)
        note = QLabel(t("sign_in_site_note", lang, host=self.host))
        note.setWordWrap(True)
        layout.addWidget(note)

        from PySide6.QtWebEngineWidgets import QWebEngineView

        from audit import driver

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

        page = QWebEnginePage(self.profile, self)
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
        record = self._cookie_record(cookie)
        self._cookies.pop(self._cookie_key(record), None)

    # ------------------------------------------------------------- actions
    def _on_done(self) -> None:
        """Keep what the browser was given, and say what was kept.

        The count is the only thing shown - never a name and never a value.
        A dialog that prints a session cookie has handed the session to
        whoever is looking at the screen, and to whoever reads the
        screenshot afterwards.
        """
        kept = cookies_for_fetcher(self.host, self._cookies.values())
        site_session.save_cookies(self.host, kept)
        self.saved = True
        self.status.setText(t("sign_in_site_saved", self.lang,
                              host=self.host, count=len(kept)))
        self.accept()

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
