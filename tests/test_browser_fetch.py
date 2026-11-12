"""The browser-mode session: requests made by the signed-in profile itself.

A local HTTP server stands in for the site: its root page sets an HttpOnly
session cookie, and its API answers JSON only to a request carrying that
cookie - the way SharePoint answers only a request carrying the session the
profile holds. Every value is synthetic; nothing leaves 127.0.0.1.
"""
from __future__ import annotations

import http.server
import json
import threading
import time
import unittest
from unittest import mock

import pytest

pytest.importorskip("PySide6.QtWebEngineCore")

import crawler  # noqa: E402
import sharepoint_tree  # noqa: E402
import site_session  # noqa: E402
from audit import browser_fetch  # noqa: E402


class _Site(http.server.BaseHTTPRequestHandler):
    throttled = {"left": 0}

    def _send(self, status, body=b"", headers=()):
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - the stdlib's name
        signed_in = "session=synthetic" in (self.headers.get("Cookie") or "")
        if self.path == "/":
            self._send(200, b"<html><body>site</body></html>", [
                ("Content-Type", "text/html"),
                ("Set-Cookie", "session=synthetic; Path=/; HttpOnly")])
        elif not signed_in:
            self._send(403, b"", [("X-Forms_Based_Auth_Required", "x")])
        elif self.path == "/_api/web":
            if _Site.throttled["left"] > 0:
                _Site.throttled["left"] -= 1
                self._send(429, b"", [("Retry-After", "1")])
                return
            body = json.dumps({"Title": "Example", "accept":
                               self.headers.get("Accept", "")}).encode()
            self._send(200, body, [("Content-Type", "application/json")])
        elif self.path == "/moved":
            self._send(302, b"", [("Location", "/_api/web")])
        elif self.path == "/away":
            self._send(302, b"", [("Location", "http://localhost:9/x")])
        else:
            self._send(404, b"{}")

    def log_message(self, *_args):
        pass


class BrowserTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from audit import driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)
        driver.ensure_headless_application()
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Site)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.root = f"http://127.0.0.1:{cls.server.server_address[1]}/"

        from PySide6.QtWebEngineCore import QWebEngineProfile

        cls.profile = QWebEngineProfile()  # off the record: no file anywhere

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _transport(self):
        transport = browser_fetch.BrowserTransport(self.root, self.profile)
        self.addCleanup(transport.close)
        return transport

    def test_the_request_carries_the_profiles_session(self):
        transport = self._transport()
        answer = transport.get(self.root + "_api/web", headers={
            "Accept": sharepoint_tree.ACCEPT_JSON, "User-Agent": "dropped"})
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["Title"], "Example")
        self.assertEqual(answer.json()["accept"], sharepoint_tree.ACCEPT_JSON)
        self.assertIn("application/json", answer.headers["content-type"])

    def test_throttling_goes_through_the_same_client(self):
        _Site.throttled["left"] = 1
        transport = self._transport()
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            transport.sleep(min(seconds, 0.05))

        client = sharepoint_tree._Client(
            transport, host="127.0.0.1", user_agent="x", timeout=10,
            max_requests=10, min_interval=0, max_retries=2, backoff_base=0.01,
            max_wait=30, sleep=sleep, clock=time.monotonic,
            wall_clock=time.time, cancelled=None)
        self.assertEqual(client.get_json(self.root + "_api/web")["Title"],
                         "Example")
        self.assertEqual(slept, [1.0])  # Retry-After, read through fetch

    def test_a_redirect_on_the_site_says_where_it_went(self):
        answer = self._transport().get(self.root + "moved")
        self.assertEqual(answer.status_code, 302)
        self.assertTrue(answer.headers["Location"].endswith("/_api/web"))

    def test_a_redirect_off_the_site_reads_as_a_sign_in(self):
        transport = self._transport()
        answer = transport.get(self.root + "away")
        self.assertEqual(answer.headers[browser_fetch.REDIRECT_HEADER],
                         browser_fetch.REDIRECT_OFF_SITE)
        client = sharepoint_tree._Client(
            transport, host="127.0.0.1", user_agent="x", timeout=10,
            max_requests=10, min_interval=0, max_retries=0, backoff_base=0,
            max_wait=1, sleep=transport.sleep, clock=time.monotonic,
            wall_clock=time.time, cancelled=None)
        with self.assertRaises(sharepoint_tree.AuthRequired):
            client.get_json(self.root + "away")

    def test_no_profile_answers_as_a_stranger(self):
        transport = browser_fetch.BrowserTransport(self.root, None)
        answer = transport.get(self.root + "_api/web")
        self.assertEqual(answer.status_code, 403)
        self.assertTrue(sharepoint_tree.authwall.forms_auth_required(
            answer.headers))
        self.assertEqual(transport.requests_made, 0)

    def test_another_origin_is_never_asked(self):
        import requests

        with self.assertRaises(requests.ConnectionError):
            self._transport().get("http://localhost:9/_api/web")


def test_off_the_qt_thread_it_refuses():
    from audit import driver

    driver.ensure_headless_application()
    caught = []

    def worker():
        try:
            browser_fetch.BrowserTransport._check_thread()
        except browser_fetch.BrowserFetchError as exc:
            caught.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert caught


# -- the run: browser mode for a signed-in SharePoint site ------------------------

SITE = "contoso.sharepoint.com"
TARGET = f"https://{SITE}/sites/ExampleSite"


def _signed_in():
    site_session.mark_signed_in(SITE)


def test_the_marker_alone_is_a_session_read_by_the_browser():
    try:
        assert not site_session.has_session(SITE)
        _signed_in()
        assert site_session.has_session(SITE)
        assert site_session.session_mode(SITE) == site_session.SESSION_BROWSER
        assert site_session.session_mode("app.example.com") == ""
    finally:
        site_session.forget(SITE)
    assert not site_session.has_session(SITE)


def test_cookie_mode_suggests_the_browser_after_a_wall():
    host = "app.example.com"
    try:
        site_session.save_cookies(host, [])
        assert site_session.session_mode(host) == site_session.SESSION_COOKIES
        assert not site_session.should_switch_to_browser(host, True)
        site_session.mark_signed_in(host)
        assert site_session.should_switch_to_browser(host, True)
        assert not site_session.should_switch_to_browser(host, False)
    finally:
        site_session.forget(host)


def test_an_empty_copy_is_not_refused_in_browser_mode():
    from cli_impl import auditpass

    config = crawler.CrawlConfig()
    try:
        _signed_in()
        assert auditpass.session_refusal(TARGET, config, SITE, False) == ""
        assert auditpass.sign_in_refusal(
            TARGET, mock.Mock(no_session=False)) == ""
    finally:
        site_session.forget(SITE)
    # Without the marker the refusal stands.
    assert auditpass.session_refusal(TARGET, config, "", False)


def test_browser_mode_discovers_in_the_browser_and_reads_by_render(monkeypatch):
    from cli_impl import auditpass

    seen = {}

    def fake_discover(target, session, **kwargs):
        seen["target"] = target
        tree = sharepoint_tree.SiteTree(site_url=target)
        return tree

    monkeypatch.setattr(browser_fetch, "discover_in_browser", fake_discover)
    fetched = []
    monkeypatch.setattr(crawler, "_http_session", lambda *_a: mock.Mock(
        get=lambda url, **_k: fetched.append(url)))
    config = crawler.CrawlConfig(max_pages=1)
    try:
        _signed_in()
        pages, _tree = auditpass.sharepoint_pages(
            TARGET, config, page_tree=auditpass.PAGE_TREE_SHAREPOINT,
            render=lambda url: "<html><body><p>Rendered page text.</p>"
                               "</body></html>")
    finally:
        site_session.forget(SITE)
    assert seen["target"] == TARGET
    assert config.session_mode == "browser"
    assert fetched == []  # no `requests` read of a page
    assert pages and crawler.RENDERED in pages[0].diagnostics.reasons
    assert "Rendered page text." in pages[0].raw_html


def test_a_page_the_browser_could_not_read_is_an_error_not_a_blank():
    def render(url):
        raise RuntimeError("load failed")

    config = crawler.CrawlConfig(max_pages=1, session_mode="browser")
    pages = crawler.crawl(TARGET, config, render=render)
    assert pages[0].error and crawler.EMPTY_ERROR in pages[0].diagnostics.reasons
