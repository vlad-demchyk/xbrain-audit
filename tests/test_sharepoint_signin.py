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
    # Another cookie on the shared parent: every tenant's, never kept.
    record("SPOIDCRL", ".sharepoint.com"),
]


# -- the filter ---------------------------------------------------------------


def test_sharepoint_keeps_only_the_tenants_own_hosts():
    kept = ssi.cookies_for_fetcher(SITE, SIGNED_IN)
    assert [(r["name"], r["domain"], r["host_only"]) for r in kept] == [
        ("FedAuth", SITE, True),
        # rtFa lives on `.sharepoint.com`; SharePoint answers 403 without
        # it, so it is kept - as a host-only cookie of the tenant's host.
        ("rtFa", SITE, True),
        ("rtFa", ".contoso.sharepoint.com", False),
        ("FedAuth", "contoso-my.sharepoint.com", True),
    ]


def test_only_rtfa_is_taken_from_the_shared_parent():
    assert ssi.cookie_is_for_fetcher(SITE, ".sharepoint.com", "rtFa")
    assert not ssi.cookie_is_for_fetcher(SITE, ".sharepoint.com", "FedAuth")
    assert not ssi.cookie_is_for_fetcher(SITE, ".sharepoint.com", "")
    # Not for a host that is not a tenant of that parent.
    assert not ssi.cookie_is_for_fetcher("intranet.example.com",
                                         ".sharepoint.com", "rtFa")


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
        assert not any(r["name"] == "SPOIDCRL" for r in saved)
        assert "4" in dialog.status.text
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


# -- B1: the session SharePoint actually needs ------------------------------------


class _FakeQtCookie:
    def __init__(self, name, value, domain):
        self._name, self._value, self._domain = name, value, domain

    def name(self):
        return self._name.encode()

    def value(self):
        return self._value.encode()

    def domain(self):
        return self._domain

    def path(self):
        return "/"

    def isSecure(self):
        return True

    def isHttpOnly(self):
        return True

    def isSessionCookie(self):
        return True

    def sameSitePolicy(self):
        return None


def test_an_overwrite_reported_out_of_order_keeps_the_new_value():
    dialog = _dialog()
    dialog._on_cookie(_FakeQtCookie("FedAuth", "old", SITE))
    dialog._on_cookie(_FakeQtCookie("FedAuth", "new", SITE))
    # The removal of the old value arrives after the new value was added.
    dialog._on_cookie_removed(_FakeQtCookie("FedAuth", "old", SITE))
    assert [r["value"] for r in dialog._cookies.values()] == ["new"]
    dialog._on_cookie_removed(_FakeQtCookie("FedAuth", "new", SITE))
    assert dialog._cookies == {}


def test_missing_session_cookies_only_for_sharepoint():
    both = [record("FedAuth", SITE), record("rtFa", SITE)]
    assert site_session.missing_session_cookies(SITE, both) == []
    assert site_session.missing_session_cookies(
        SITE, [record("FedAuth", SITE)]) == ["rtFa"]
    assert site_session.missing_session_cookies(
        SITE, [record("FedAuth", SITE, value="")]) == ["FedAuth", "rtFa"]
    assert site_session.missing_session_cookies("app.example.com", []) == []


def _chromium_cookie_file(path, rows):
    import sqlite3

    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT,"
                   " encrypted_value BLOB, path TEXT, is_secure INTEGER,"
                   " is_httponly INTEGER, expires_utc INTEGER)")
        db.executemany("INSERT INTO cookies VALUES (?,?,?,?,?,?,?,?)", rows)
    return path


def test_reading_the_profile_file_takes_only_the_session_names(tmp_path):
    _chromium_cookie_file(tmp_path / "Cookies", [
        (SITE, "FedAuth", "synthetic-a", b"", "/", 1, 1, 0),
        (".sharepoint.com", "rtFa", "synthetic-b", b"", "/", 1, 1, 0),
        (".sharepoint.com", "SPOIDCRL", "synthetic-c", b"", "/", 1, 1, 0),
        ("login.microsoftonline.com", "ESTSAUTH", "synthetic-d", b"", "/", 1, 1, 0),
        ("fabrikam.sharepoint.com", "FedAuth", "synthetic-e", b"", "/", 1, 1, 0),
        # Encrypted by Chromium: not guessed at.
        ("contoso-my.sharepoint.com", "FedAuth", "", b"v10xxxx", "/", 1, 1, 0),
    ])
    found = site_session.read_profile_cookies(tmp_path, SITE)
    assert sorted((r["name"], r["domain"]) for r in found) == [
        ("FedAuth", SITE), ("rtFa", ".sharepoint.com")]
    assert all(r["expires"] is None for r in found)


def test_reading_a_missing_or_broken_file_is_empty(tmp_path):
    assert site_session.read_profile_cookies(tmp_path, SITE) == []
    (tmp_path / "Cookies").write_bytes(b"not a database")
    assert site_session.read_profile_cookies(tmp_path, SITE) == []
    assert site_session.read_profile_cookies("", SITE) == []


class _Store:
    def __init__(self):
        self.loaded = 0

    def loadAllCookies(self):
        self.loaded += 1


class _Profile:
    def __init__(self, storage):
        self.store = _Store()
        self.storage = str(storage)

    def cookieStore(self):
        return self.store

    def persistentStoragePath(self):
        return self.storage


def test_done_without_rtfa_asks_again_then_reads_the_file(tmp_path, monkeypatch):
    scheduled = []
    monkeypatch.setattr(ssi, "_later", lambda ms, fn: scheduled.append(fn))
    dialog = _dialog()
    dialog.profile = _Profile(tmp_path)
    dialog.accept = lambda: setattr(dialog, "was_accepted", True)
    dialog._on_cookie(_FakeQtCookie("FedAuth", "synthetic", SITE))
    try:
        dialog._on_done()
        # First: nothing saved, the store asked again, a second look queued.
        assert scheduled and dialog.profile.store.loaded == 1
        assert dialog.done_btn.enabled is False
        assert not site_session.has_session(SITE)
        _chromium_cookie_file(tmp_path / "Network" / "Cookies", [
            (".sharepoint.com", "rtFa", "synthetic", b"", "/", 1, 1, 0)])
        scheduled.pop()()
        saved = site_session.load_cookies(SITE)
        assert sorted(r["name"] for r in saved) == ["FedAuth", "rtFa"]
        assert getattr(dialog, "was_accepted", False)
    finally:
        site_session.forget(SITE)


def test_done_with_half_a_session_saves_nothing_and_says_so(tmp_path, monkeypatch):
    scheduled = []
    monkeypatch.setattr(ssi, "_later", lambda ms, fn: scheduled.append(fn))
    dialog = _dialog()
    dialog.profile = _Profile(tmp_path)
    dialog.accept = lambda: setattr(dialog, "was_accepted", True)
    dialog._on_cookie(_FakeQtCookie("FedAuth", "synthetic", SITE))
    dialog._on_done()
    scheduled.pop()()
    assert not site_session.has_session(SITE)
    assert not getattr(dialog, "was_accepted", False)
    assert dialog.done_btn.enabled is True
    assert "not complete" in dialog.status.text
    assert "synthetic" not in dialog.status.text
    # The next Done starts the checks again rather than giving up.
    dialog._on_done()
    assert len(scheduled) == 1


# -- B3: the window stays on the site and its sign-in ----------------------------


def _decide(url, kind=ssi.NAV_LINK, from_url=f"https://{SITE}/sites/ExampleSite",
            learned=None, host=SITE):
    return ssi.navigation_decision(url, host, kind=kind, from_url=from_url,
                                   learned=learned)


def test_the_site_and_the_tenant_stay_in_the_window():
    assert _decide(f"https://{SITE}/sites/ExampleSite/SitePages/A.aspx") == ssi.NAV_ALLOW
    assert _decide("https://contoso-my.sharepoint.com/personal/x") == ssi.NAV_ALLOW
    # Another tenant on the same parent is somebody else's site.
    assert _decide("https://fabrikam.sharepoint.com/sites/X") == ssi.NAV_EXTERNAL


def test_identity_providers_and_mfa_set_up_stay_in_the_window():
    for url in ("https://login.microsoftonline.com/common/oauth2/authorize",
                "https://login.live.com/login.srf",
                "https://contoso.b2clogin.com/x",
                "https://aka.ms/mfasetup",
                "https://mysignins.microsoft.com/security-info",
                "https://account.activedirectory.windowsazure.com/proofup.aspx",
                "https://microsoft.com/devicelogin",
                "https://autologon.microsoftazuread-sso.com/x"):
        assert _decide(url) == ssi.NAV_ALLOW, url


def test_a_link_to_another_site_goes_to_the_system_browser():
    assert _decide("https://news.example.org/story") == ssi.NAV_EXTERNAL
    assert _decide("https://news.example.org/story",
                   kind=ssi.NAV_OTHER) == ssi.NAV_EXTERNAL
    assert _decide("mailto:someone@example.org") == ssi.NAV_EXTERNAL
    assert _decide("about:blank") == ssi.NAV_ALLOW


def test_a_federated_provider_reached_by_the_sign_in_is_learned():
    learned = set()
    idp = "https://login.microsoftonline.com/common/login"
    # The provider hands over to the organisation's own sign-in by a form.
    assert _decide("https://sso.example.org/signin", kind=ssi.NAV_FORM,
                   from_url=idp, learned=learned) == ssi.NAV_ALLOW
    assert learned == {"sso.example.org"}
    # Its own links then work, even clicked.
    assert _decide("https://sso.example.org/mfa", learned=learned) == ssi.NAV_ALLOW
    # ADFS by its path, from anywhere; a server redirect too.
    assert _decide("https://fs.example.net/adfs/ls/?wa=x") == ssi.NAV_ALLOW
    assert _decide("https://idp.example.com/x", kind=ssi.NAV_REDIRECT) == ssi.NAV_ALLOW


def test_an_ordinary_site_keeps_its_own_sign_in_host():
    host = "app.example.com"
    assert _decide("https://sso.example.com/login", host=host,
                   from_url="https://app.example.com/") == ssi.NAV_ALLOW
    assert _decide("https://other.example.org/", host=host,
                   from_url="https://app.example.com/") == ssi.NAV_EXTERNAL
    assert ssi._site_of("shop.example.co.uk") == "example.co.uk"


def test_a_refused_navigation_opens_outside_and_says_so(monkeypatch):
    opened = []
    monkeypatch.setattr(ssi, "_open_external", opened.append)
    dialog = _dialog()
    assert dialog._accept_navigation("https://news.example.org/story",
                                     ssi.NAV_LINK, f"https://{SITE}/") is False
    assert opened == ["https://news.example.org/story"]
    assert "news.example.org" in dialog.status.text
    assert "system browser" in dialog.status.text
    assert dialog._accept_navigation(f"https://{SITE}/sites/ExampleSite",
                                     ssi.NAV_LINK, "") is True
    assert opened == ["https://news.example.org/story"]


def test_qt_navigation_types_map_to_kinds():
    from PySide6.QtWebEngineCore import QWebEnginePage

    kinds = {ssi._nav_kind(member) for member in QWebEnginePage.NavigationType}
    assert kinds == {ssi.NAV_LINK, ssi.NAV_TYPED, ssi.NAV_FORM, ssi.NAV_BACK_FORWARD,
                     ssi.NAV_RELOAD, ssi.NAV_OTHER, ssi.NAV_REDIRECT}
