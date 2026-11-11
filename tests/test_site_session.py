"""A signed-in run, and the rules that make one acceptable to ship.

Half of what is worth auditing is behind a login. The way in that does not
involve this tool handling credentials is the obvious one: a person signs in
themselves in a real browser window, and the run reuses what that browser was
given. Everything below is about the other half of that bargain - the session
is per host, it can be seen, it can be removed, and nothing about its
contents ever leaves the machine's own storage.
"""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path


def _can_symlink() -> bool:
    """Windows creates a symlink only in Developer Mode or as an
    administrator; without either there is no symlink to escape through,
    and the escape tests have nothing to set up."""
    with tempfile.TemporaryDirectory() as folder:
        try:
            (Path(folder) / "link").symlink_to(folder, target_is_directory=True)
        except OSError:
            return False
    return True


_NEEDS_SYMLINKS = unittest.skipUnless(
    _can_symlink(), "this account cannot create symlinks (Windows without Developer Mode)")


def _cookie(name="sid", value="x", domain="a.example", path="/",
            secure=False, http_only=False, same_site="Default",
            expires=None, host_only=True):
    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "secure": secure,
        "http_only": http_only,
        "same_site": same_site,
        "expires": expires,
        "host_only": host_only,
    }


class _Isolated(unittest.TestCase):
    """Every case runs against its own config directory, never the
    developer's - a test that writes a session into the real one is a test
    that hands the next run somebody's account."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name
        self.addCleanup(self._restore)

    def _restore(self):
        if self._previous is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._previous


class WhichSessionBelongsToWhom(_Isolated):
    def test_the_port_is_part_of_the_host(self):
        import site_session as ss

        self.assertEqual(ss.host_of("http://localhost:3000/admin"), "localhost:3000")
        self.assertNotEqual(ss.host_of("http://localhost:3000/"),
                            ss.host_of("http://localhost:8080/"))

    def test_equivalent_hosts_have_one_canonical_identity(self):
        import site_session as ss

        self.assertEqual(ss.host_of("HTTPS://Example.COM./account"),
                         "example.com")
        self.assertEqual(ss.host_of("https://Example.COM.:443/account"),
                         "example.com:443")
        self.assertEqual(ss.host_of("https://bücher.example/"),
                         "xn--bcher-kva.example")

    def test_a_bare_hostname_is_read_as_one(self):
        import site_session as ss

        self.assertEqual(ss.host_of("staging.example.com/admin"),
                         "staging.example.com")

    def test_nothing_is_not_a_host(self):
        import site_session as ss

        self.assertEqual(ss.host_of(""), "")
        self.assertEqual(ss.host_of("   "), "")

    def test_filesystem_control_paths_are_not_hosts(self):
        import site_session as ss

        for target in (".", "..", "../other", r"..\other"):
            with self.subTest(target=target):
                self.assertEqual(ss.host_of(target), "")

    def test_a_profile_is_always_a_child_of_the_sessions_directory(self):
        import site_session as ss

        for host in ("", ".", "..", "/", r"..\other"):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    ss.profile_dir(host)

    @_NEEDS_SYMLINKS
    def test_a_profile_symlink_cannot_escape_the_sessions_directory(self):
        import site_session as ss

        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        (ss.sessions_root() / ss._profile_name("a.example")).symlink_to(
            outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            ss.profile_dir("a.example")

        self.assertEqual(ss.known_hosts(),
                         [f"legacy:{ss._profile_name('a.example')}"])
        self.assertEqual(ss.forget_all(), 1)
        self.assertTrue(outside.exists())

    def test_a_session_for_one_host_is_not_a_session_for_another(self):
        import site_session as ss

        ss.save_cookies("staging.example.com", {"sid": "x"})
        self.assertTrue(ss.has_session("staging.example.com"))
        self.assertFalse(ss.has_session("example.com"))
        self.assertEqual(ss.load_cookies("example.com"), [])

    def test_hosts_that_used_to_share_a_slug_have_distinct_profiles(self):
        import hashlib
        import site_session as ss

        first = "example.com:3000"
        second = "example.com-3000"
        self.assertEqual(ss._slug(first), ss._slug(second))
        first_path = ss.profile_dir(first)
        second_path = ss.profile_dir(second)
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(
            first_path.name,
            "profile-" + hashlib.sha256(first.encode("utf-8")).hexdigest(),
        )

        ss.save_cookies(first, {"sid": "first"})
        ss.save_cookies(second, {"sid": "second"})

        self.assertEqual(ss.load_cookies(first)[0]["value"], "first")
        self.assertEqual(ss.load_cookies(second)[0]["value"], "second")
        self.assertEqual(ss.known_hosts(), sorted([first, second]))

    def test_an_empty_directory_is_not_a_session(self):
        """The profile directory is created when the sign-in window opens.
        Somebody who closed that window without signing in must not be told
        they are signed in."""
        import site_session as ss

        ss.profile_dir("example.com", create=True)
        self.assertFalse(ss.has_session("example.com"))


class ItCanBeSeenAndRemoved(_Isolated):
    def test_the_hosts_are_listable(self):
        import site_session as ss

        ss.save_cookies("a.example", {"s": "1"})
        ss.save_cookies("b.example", {"s": "1"})
        self.assertEqual(ss.known_hosts(), ["a.example", "b.example"])

    def test_forgetting_one_host_leaves_the_other(self):
        import site_session as ss

        ss.save_cookies("a.example", {"s": "1"})
        ss.save_cookies("b.example", {"s": "1"})
        self.assertTrue(ss.forget("a.example"))
        self.assertEqual(ss.known_hosts(), ["b.example"])

    def test_forgetting_removes_the_cookies_too_and_not_only_the_profile(self):
        import site_session as ss

        ss.save_cookies("a.example", {"s": "1"})
        path = ss.cookies_path("a.example")
        ss.forget("a.example")
        self.assertFalse(path.exists())
        self.assertEqual(ss.load_cookies("a.example"), [])

    def test_forgetting_everything_reports_how_much_there_was(self):
        import site_session as ss

        ss.save_cookies("a.example", {"s": "1"})
        ss.save_cookies("b.example", {"s": "1"})
        self.assertEqual(ss.forget_all(), 2)
        self.assertEqual(ss.known_hosts(), [])

    def test_forgetting_a_host_that_has_nothing_says_so(self):
        import site_session as ss

        self.assertFalse(ss.forget("nobody.example"))

    def test_forgetting_a_control_path_never_touches_the_config_root(self):
        import config
        import site_session as ss

        marker = config.config_file()
        marker.write_text("keep", encoding="utf-8")
        self.assertFalse(ss.forget(".."))
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_a_proven_legacy_profile_is_migrated_to_its_hash(self):
        import json
        import site_session as ss

        host = "old.example"
        legacy = ss.sessions_root() / ss._slug(host)
        legacy.mkdir()
        (legacy / "cookies.json").write_text(json.dumps({
            "version": 2,
            "host": host,
            "cookies": [_cookie(domain=host)],
        }), encoding="utf-8")

        current = ss.profile_dir(host)

        self.assertFalse(legacy.exists())
        self.assertTrue(current.is_dir())
        self.assertEqual(ss.load_cookies(host)[0]["value"], "x")

    def test_an_ambiguous_legacy_profile_is_never_given_to_a_host(self):
        import json
        import site_session as ss

        host = "example.com:3000"
        legacy = ss.sessions_root() / ss._slug(host)
        legacy.mkdir()
        (legacy / "cookies.json").write_text(json.dumps({"sid": "secret"}),
                                               encoding="utf-8")

        self.assertFalse(ss.has_session(host))
        self.assertEqual(ss.load_cookies(host), [])
        self.assertEqual(ss.known_hosts(), [f"legacy:{ss._slug(host)}"])
        self.assertEqual(ss.forget_all(), 1)
        self.assertFalse(legacy.exists())

    def test_a_listed_legacy_profile_can_be_removed_by_the_name_shown(self):
        """`known_hosts()` prints it, so `forget()` has to take it back.

        The token is not a host and never resolves to one, so the ordinary
        path refused it - leaving an entry a person could see in the list
        and had no way to remove except `forget_all()`.
        """
        import json
        import site_session as ss

        host = "example.com:3000"
        legacy = ss.sessions_root() / ss._slug(host)
        legacy.mkdir()
        (legacy / "cookies.json").write_text(json.dumps({"sid": "secret"}),
                                               encoding="utf-8")

        listed = ss.known_hosts()
        self.assertEqual(listed, [f"legacy:{ss._slug(host)}"])
        self.assertTrue(ss.forget(listed[0]))
        self.assertFalse(legacy.exists())
        self.assertEqual(ss.known_hosts(), [])
        self.assertFalse(ss.forget(listed[0]))

    @_NEEDS_SYMLINKS
    def test_a_legacy_symlink_is_unlinked_and_its_target_is_left_alone(self):
        import site_session as ss

        outside = Path(self._tmp.name) / "not-a-session"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep", encoding="utf-8")
        link = ss.sessions_root() / "old-profile"
        link.symlink_to(outside, target_is_directory=True)

        self.assertEqual(ss.known_hosts(), ["legacy:old-profile"])
        self.assertTrue(ss.forget("legacy:old-profile"))
        self.assertFalse(link.exists())
        self.assertFalse(link.is_symlink())
        self.assertTrue((outside / "keep.txt").is_file())

    def test_a_legacy_token_never_reaches_outside_the_sessions_directory(self):
        import site_session as ss

        for name in ("", ".", "..", "../escape", "a/b", "\\"):
            with self.subTest(name=name):
                self.assertFalse(ss.forget(f"legacy:{name}"))

    def test_a_colliding_legacy_profile_moves_only_to_its_proven_owner(self):
        import json
        import site_session as ss

        owner = "example.com:3000"
        collision = "example.com-3000"
        legacy = ss.sessions_root() / ss._slug(owner)
        self.assertEqual(legacy.name, ss._slug(collision))
        legacy.mkdir()
        (legacy / "cookies.json").write_text(json.dumps({
            "version": 2,
            "host": owner,
            "cookies": [_cookie(value="owner", domain="example.com")],
        }), encoding="utf-8")

        self.assertEqual(ss.load_cookies(collision), [])
        self.assertTrue(legacy.exists())
        self.assertEqual(ss.load_cookies(owner)[0]["value"], "owner")
        self.assertFalse(legacy.exists())


class NothingLeaksOut(_Isolated):
    def test_the_cookie_file_is_readable_by_its_owner_only(self):
        import site_session as ss

        ss.save_cookies("a.example", {"sid": "secret"})
        mode = stat.S_IMODE(ss.cookies_path("a.example").stat().st_mode)
        # No POSIX modes on Windows (see tests/test_local_security.py); the
        # file is under the user's own %APPDATA%, which NTFS restricts.
        if os.name != "nt":
            self.assertEqual(mode, 0o600)
        self.assertTrue(ss.cookies_path("a.example").is_file())

    def test_cookie_scope_and_security_attributes_survive_storage(self):
        import site_session as ss

        records = [
            _cookie(path="/private", secure=True, http_only=True,
                    same_site="Strict", expires=2_000_000_000),
            _cookie(value="other", path="/account"),
        ]
        ss.save_cookies("a.example", records)
        self.assertEqual(ss.load_cookies("a.example"), records)

    def test_the_old_name_value_store_migrates_to_host_only_scope(self):
        import json

        import site_session as ss

        path = ss.profile_dir("a.example", create=True) / "cookies.json"
        path.write_text(json.dumps({"sid": "old"}), encoding="utf-8")
        self.assertEqual(
            ss.load_cookies("a.example"),
            [_cookie(value="old")],
        )

    def test_the_description_carries_the_fact_and_not_the_session(self):
        import site_session as ss

        ss.save_cookies("a.example", {"sid": "secret"})
        described = ss.describe("a.example")
        self.assertIn("a.example", described)
        self.assertNotIn("secret", described)
        self.assertNotIn("sid", described)

    def test_a_host_with_no_session_describes_as_nothing(self):
        import site_session as ss

        self.assertEqual(ss.describe("a.example"), "")

    def test_an_unreadable_store_is_a_run_without_a_session(self):
        """Never an exception: a session that cannot be read is one the run
        does not have, and a scan that raises over it has thrown away work
        it already did."""
        import site_session as ss

        path = ss.profile_dir("a.example", create=True) / "cookies.json"
        path.write_text("{ this is not json", encoding="utf-8")
        self.assertEqual(ss.load_cookies("a.example"), [])


class BothClientsOrNeither(_Isolated):
    """`requests` fetches the pages and QtWebEngine renders them, and they
    share no storage. Handing the session to one produces a run where the
    browser sees the account and the fetch sees the login form."""

    def config(self):
        from crawler import CrawlConfig

        return CrawlConfig(max_depth=0, max_pages=1)

    def test_applying_a_session_fills_the_fetchers_cookies(self):
        import site_session as ss

        ss.save_cookies("a.example", {"sid": "x", "csrf": "y"})
        config = self.config()
        host, count = ss.apply_to(config, "https://a.example/admin")
        self.assertEqual((host, count), ("a.example", 2))
        self.assertEqual(
            {(cookie["name"], cookie["value"]) for cookie in config.cookies},
            {("sid", "x"), ("csrf", "y")},
        )
        self.assertTrue(all(cookie["domain"] == "a.example"
                            for cookie in config.cookies))

    def test_no_session_changes_nothing(self):
        import site_session as ss

        config = self.config()
        self.assertEqual(ss.apply_to(config, "https://a.example/"), ("", 0))
        self.assertEqual(config.cookies, [])

    def test_the_crawler_sends_what_it_was_given(self):
        """Set on the session rather than as a header, so redirects and the
        site's own Set-Cookie behave the way a browser makes them behave."""
        import crawler

        captured = {}

        class _FakeSession:
            def __init__(self):
                self.headers = {}
                self.cookies = self

            def set(self, name, value, **scope):
                captured[name] = (value, scope)

            def get(self, *_args, **_kwargs):
                raise RuntimeError("stop here")

        original = crawler.requests.Session
        crawler.requests.Session = _FakeSession
        try:
            crawler.crawl("https://a.example/",
                          crawler.CrawlConfig(max_depth=0, max_pages=1,
                                              cookies={"sid": "x"}))
        except Exception:  # noqa: BLE001 - the fake stops the walk on purpose
            pass
        finally:
            crawler.requests.Session = original
        value, scope = captured["sid"]
        self.assertEqual(value, "x")
        self.assertEqual(scope["domain"], "a.example")
        self.assertEqual(scope["path"], "/")

    def test_every_redirect_target_rechecks_cookie_scope(self):
        import requests

        import crawler

        config = crawler.CrawlConfig(cookies=[_cookie(
            path="/private", secure=True, http_only=True,
            same_site="Strict")])
        session = crawler._http_session(config, "https://a.example/private")

        def header(url):
            request = requests.Request("GET", url)
            return session.prepare_request(request).headers.get("Cookie", "")

        self.assertEqual(header("https://a.example/private/page"), "sid=x")
        self.assertEqual(header("https://sub.a.example/private/page"), "")
        self.assertEqual(header("https://b.example/private/page"), "")
        self.assertEqual(header("http://a.example/private/page"), "")
        self.assertEqual(header("https://a.example/public"), "")
        stored = next(iter(session.cookies))
        self.assertEqual(stored._rest["HttpOnly"], True)
        self.assertEqual(stored._rest["SameSite"], "Strict")

        domain_session = crawler._http_session(
            crawler.CrawlConfig(cookies=[_cookie(
                domain=".a.example", host_only=False)]),
            "https://a.example/",
        )
        request = requests.Request("GET", "https://sub.a.example/")
        prepared = domain_session.prepare_request(request)
        self.assertEqual(prepared.headers.get("Cookie"), "sid=x")

    def test_requests_rechecks_scope_while_following_a_redirect(self):
        import requests
        from requests.adapters import BaseAdapter

        import crawler

        class _Redirect(BaseAdapter):
            def __init__(self, destination):
                self.destination = destination
                self.sent = []

            def send(self, request, **_kwargs):
                self.sent.append((request.url, request.headers.get("Cookie", "")))
                response = requests.Response()
                response.request = request
                response.url = request.url
                response._content = b""
                if len(self.sent) == 1:
                    response.status_code = 302
                    response.headers["Location"] = self.destination
                else:
                    response.status_code = 200
                return response

            def close(self):
                pass

        session = crawler._http_session(
            crawler.CrawlConfig(cookies=[_cookie(
                path="/private", secure=True)]),
            "https://a.example/private",
        )
        adapter = _Redirect("https://sub.a.example/private")
        session.mount("https://", adapter)
        session.get("https://a.example/private")
        self.assertEqual(adapter.sent, [
            ("https://a.example/private", "sid=x"),
            ("https://sub.a.example/private", ""),
        ])

    def test_qt_cookie_attributes_are_copied_without_flattening(self):
        from ui.site_sign_in import SiteSignInDialog

        class _Expiration:
            def isValid(self):
                return True

            def toSecsSinceEpoch(self):
                return 2_000_000_000

        class _Policy:
            name = "Lax"

        class _QtCookie:
            def name(self):
                return b"sid"

            def value(self):
                return b"secret"

            def domain(self):
                return ".a.example"

            def path(self):
                return "/private"

            def isSecure(self):
                return True

            def isHttpOnly(self):
                return True

            def isSessionCookie(self):
                return False

            def expirationDate(self):
                return _Expiration()

            def sameSitePolicy(self):
                return _Policy()

        dialog = SiteSignInDialog.__new__(SiteSignInDialog)
        dialog._cookies = {}
        cookie = _QtCookie()
        dialog._on_cookie(cookie)
        self.assertEqual(list(dialog._cookies.values()), [_cookie(
            value="secret", domain=".a.example", path="/private",
            secure=True, http_only=True, same_site="Lax",
            expires=2_000_000_000, host_only=False)])
        dialog._on_cookie_removed(cookie)
        self.assertEqual(dialog._cookies, {})


class ClosingTheWindow(_Isolated):
    """Only Done makes a session (P-25).

    Cancel, Escape and the title-bar button mean "not this": nothing is
    written for the fetcher, the renderer's profile is not used by a scan,
    and the cookies the page set are removed when there was no session yet.
    """

    def setUp(self):
        super().setUp()
        try:
            from PySide6.QtWidgets import QApplication  # noqa: F401
        except Exception:  # noqa: BLE001
            self.skipTest("PySide6 not available")

    class _Store:
        def __init__(self):
            self.deleted = 0

        def deleteAllCookies(self):
            self.deleted += 1

    class _Profile:
        def __init__(self, store):
            self._store = store

        def cookieStore(self):
            return self._store

    def _dialog(self, had_session=False):
        from ui.site_sign_in import SiteSignInDialog

        dialog = SiteSignInDialog.__new__(SiteSignInDialog)
        dialog.host = "a.example"
        dialog.saved = False
        dialog._had_session = had_session
        dialog._cookies = {("sid", "a.example", "/"): _cookie()}
        dialog._store = self._Store()
        dialog.profile = self._Profile(dialog._store)
        return dialog

    def test_closing_without_done_keeps_nothing(self):
        import site_session as ss

        dialog = self._dialog()
        dialog._drop_what_was_not_confirmed()
        self.assertFalse(dialog.saved)
        self.assertEqual(dialog._cookies, {})
        self.assertEqual(dialog._store.deleted, 1)
        self.assertFalse(ss.has_session("a.example"))
        self.assertEqual(ss.load_cookies("a.example"), [])

    def test_cancel_does_not_take_away_an_earlier_session(self):
        import site_session as ss

        ss.save_cookies("a.example", [_cookie()])
        dialog = self._dialog(had_session=True)
        dialog._drop_what_was_not_confirmed()
        self.assertEqual(dialog._store.deleted, 0)
        self.assertTrue(ss.has_session("a.example"))

    def test_a_profile_the_browser_wrote_is_not_a_session(self):
        import site_session as ss

        path = ss.profile_dir("a.example", create=True)
        (path / "Cookies").write_bytes(b"sqlite")
        self.assertFalse(ss.has_session("a.example"))
        ss.save_cookies("a.example", [_cookie()])
        self.assertTrue(ss.has_session("a.example"))

    def test_every_way_out_goes_through_done(self):
        from PySide6.QtWidgets import QDialog

        dialog = self._dialog()
        calls = []
        dialog._drop_what_was_not_confirmed = lambda: calls.append("drop")
        dialog._page = None
        from unittest import mock
        with mock.patch.object(QDialog, "done", lambda self, r: calls.append(r)):
            type(dialog).done(dialog, QDialog.DialogCode.Rejected)
            type(dialog).done(dialog, QDialog.DialogCode.Accepted)
        self.assertEqual(calls, ["drop", QDialog.DialogCode.Rejected,
                                 QDialog.DialogCode.Accepted])


class TheCommandLine(_Isolated):
    def test_listing_says_so_when_there_is_nothing(self):
        import cli

        args = type("A", (), {"list": True, "forget": False, "url": ""})()
        self.assertEqual(cli.cmd_login(args), 0)

    def test_forgetting_without_a_url_forgets_everything(self):
        import cli
        import site_session as ss

        ss.save_cookies("a.example", {"s": "1"})
        args = type("A", (), {"list": False, "forget": True, "url": ""})()
        self.assertEqual(cli.cmd_login(args), 0)
        self.assertEqual(ss.known_hosts(), [])

    def test_forgetting_one_host_by_url(self):
        import cli
        import site_session as ss

        ss.save_cookies("a.example", {"s": "1"})
        ss.save_cookies("b.example", {"s": "1"})
        args = type("A", (), {"list": False, "forget": True,
                              "url": "https://a.example/x"})()
        cli.cmd_login(args)
        self.assertEqual(ss.known_hosts(), ["b.example"])

    def test_an_invalid_forget_target_does_not_forget_everything(self):
        import cli
        import site_session as ss

        ss.save_cookies("a.example", {"s": "1"})
        args = type("A", (), {"list": False, "forget": True,
                              "url": ".."})()
        self.assertEqual(cli.cmd_login(args), 2)
        self.assertEqual(ss.known_hosts(), ["a.example"])

    def test_signing_in_needs_an_address(self):
        import cli

        args = type("A", (), {"list": False, "forget": False, "url": ""})()
        self.assertEqual(cli.cmd_login(args), 2)


if __name__ == "__main__":
    unittest.main()
