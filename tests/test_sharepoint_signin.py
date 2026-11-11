"""Signing in to SharePoint Online: what the fetcher keeps, and when Done fits.

The browser profile keeps everything - the identity provider's cookies are
what let it sign in silently next time. The copy written for `requests` is
narrowed to the tenant's own hosts: a Microsoft account cookie
(`ESTSAUTH*` on `login.microsoftonline.com`) never reaches `cookies.json`.

All values are synthetic.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

import site_session  # noqa: E402
from ui import site_sign_in as ssi  # noqa: E402

SITE = "contoso.sharepoint.com"


def record(name, domain, value="synthetic"):
    return {"name": name, "value": value, "domain": domain, "path": "/",
            "secure": True, "http_only": True, "same_site": "None_",
            "expires": None, "host_only": not domain.startswith(".")}


SIGNED_IN = [
    record("FedAuth", SITE),
    record("rtFa", ".sharepoint.com"),
    record("rtFa", ".contoso.sharepoint.com"),
    record("FedAuth", "contoso-my.sharepoint.com"),
    record("ESTSAUTHPERSISTENT", "login.microsoftonline.com"),
    record("ESTSAUTH", ".login.microsoftonline.com"),
    record("buid", "login.live.com"),
    record("FedAuth", "fabrikam.sharepoint.com"),
    record("x", "contoso.b2clogin.com"),
]


# -- the filter ---------------------------------------------------------------


def test_sharepoint_keeps_only_the_tenants_own_hosts():
    kept = ssi.cookies_for_fetcher(SITE, SIGNED_IN)
    assert [(r["name"], r["domain"]) for r in kept] == [
        ("FedAuth", SITE),
        ("rtFa", ".contoso.sharepoint.com"),
        ("FedAuth", "contoso-my.sharepoint.com"),
    ]


def test_an_identity_provider_cookie_never_reaches_the_fetcher():
    for domain in ("login.microsoftonline.com", ".login.microsoftonline.com",
                   "login.windows.net", "tenant.b2clogin.com"):
        assert not ssi.cookie_is_for_fetcher(SITE, domain)
        assert not ssi.cookie_is_for_fetcher("intranet.example.com", domain)


def test_an_ordinary_site_keeps_its_host_and_parent_domains():
    host = "app.example.com"
    assert ssi.cookie_is_for_fetcher(host, "app.example.com")
    assert ssi.cookie_is_for_fetcher(host, ".example.com")
    assert not ssi.cookie_is_for_fetcher(host, "other.example.com")
    assert not ssi.cookie_is_for_fetcher(host, ".com")
    assert not ssi.cookie_is_for_fetcher(host, "example.org")
    # A port is part of the session's host, not of the cookie's domain.
    assert ssi.cookie_is_for_fetcher("localhost:3000", "localhost")
    assert not ssi.cookie_is_for_fetcher("localhost:3000", "localhost.test")
    assert ssi.cookie_is_for_fetcher("dev.example.com:8443", ".example.com")


# -- where the window is --------------------------------------------------------


@pytest.mark.parametrize("url, stage", [
    ("https://login.microsoftonline.com/common/oauth2/authorize?x=1",
     ssi.STAGE_IDENTITY_PROVIDER),
    ("https://contoso.sharepoint.com/_layouts/15/Authenticate.aspx?Source=%2F",
     ssi.STAGE_IDENTITY_PROVIDER),
    ("https://contoso.sharepoint.com/_forms/default.aspx", ssi.STAGE_IDENTITY_PROVIDER),
    ("https://contoso.sharepoint.com/sites/ExampleSite", ssi.STAGE_SITE),
    ("https://contoso-my.sharepoint.com/personal/x", ssi.STAGE_SITE),
    ("https://www.office.com/", ssi.STAGE_ELSEWHERE),
])
def test_sign_in_stage(url, stage):
    assert ssi.sign_in_stage(url, SITE) == stage


class _Button:
    def __init__(self):
        self.enabled = True
        self.default = False

    def setEnabled(self, value):
        self.enabled = value

    def setDefault(self, value):
        self.default = value


class _Label:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _Url:
    def __init__(self, url):
        self._url = url

    def toString(self):
        return self._url


def _dialog(host=SITE, lang="en"):
    dialog = ssi.SiteSignInDialog.__new__(ssi.SiteSignInDialog)
    dialog.host = host
    dialog.lang = lang
    dialog.saved = False
    dialog._had_session = False
    dialog._cookies = {}
    dialog.done_btn = _Button()
    dialog.status = _Label()
    return dialog


def test_done_waits_while_the_window_is_on_the_identity_provider():
    dialog = _dialog()
    dialog._on_url_changed(_Url(
        "https://login.microsoftonline.com/common/oauth2/authorize"))
    assert dialog.done_btn.enabled is False
    assert SITE in dialog.status.text and "Done" in dialog.status.text
    dialog._on_url_changed(_Url(
        "https://contoso.sharepoint.com/sites/ExampleSite/SitePages/Home.aspx"))
    assert dialog.done_btn.enabled is True and dialog.done_btn.default
    assert "back on" in dialog.status.text


def test_the_hint_reads_in_every_language():
    for lang in ("uk", "it", "en"):
        dialog = _dialog(lang=lang)
        dialog._on_url_changed(_Url("https://login.microsoftonline.com/x"))
        assert dialog.status.text and "sign_in_site" not in dialog.status.text


# -- Done writes only the filtered copy ------------------------------------------


def test_done_saves_only_what_the_fetcher_should_send():
    host = "contoso.sharepoint.com"
    dialog = _dialog(host=host)
    for item in SIGNED_IN:
        dialog._cookies[dialog._cookie_key(item)] = item
    dialog.accept = lambda: None
    try:
        dialog._on_done()
        saved = site_session.load_cookies(host)
        assert {r["domain"] for r in saved} == {
            "contoso.sharepoint.com", ".contoso.sharepoint.com",
            "contoso-my.sharepoint.com"}
        assert not any("ESTSAUTH" in r["name"] for r in saved)
        assert "3" in dialog.status.text
        # The browser half keeps everything for a silent re-sign-in.
        assert len(dialog._cookies) == len(SIGNED_IN)
    finally:
        site_session.forget(host)


# -- a profile that was signed in before -----------------------------------------


def test_cookies_already_in_the_profile_are_loaded(monkeypatch):
    core = pytest.importorskip("PySide6.QtWebEngineCore")

    class _Signal:
        def __init__(self):
            self.slots = []

        def connect(self, slot):
            self.slots.append(slot)

    class _Store:
        def __init__(self):
            self.cookieAdded = _Signal()
            self.cookieRemoved = _Signal()
            self.loaded = 0

        def loadAllCookies(self):
            self.loaded += 1

    class _Profile:
        def __init__(self):
            self.store = _Store()

        def cookieStore(self):
            return self.store

    class _View:
        def setPage(self, page):
            self.page = page

    class _Page:
        def __init__(self, profile, parent):
            self.profile = profile

    monkeypatch.setattr(core, "QWebEnginePage", _Page)
    dialog = _dialog()
    dialog.profile = _Profile()
    dialog.view = _View()
    dialog._attach_page()
    assert dialog.profile.store.loaded == 1
    assert dialog.profile.store.cookieAdded.slots == [dialog._on_cookie]
