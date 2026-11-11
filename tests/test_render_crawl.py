"""Rendering during a crawl, with a stub browser.

No Qt here on purpose: the crawler takes `render` as a callable precisely so
the decision of *when* to render can be tested without starting one.
"""
import unittest
from unittest.mock import patch

from crawler import (
    EMPTY_ALREADY_SEEN, EMPTY_JS_RENDERED, EMPTY_REDIRECTED, RENDER_ALWAYS,
    RENDER_AUTO, RENDER_NEVER, RENDERED, CrawlConfig, _should_render, crawl,
)
from models import PageDiagnostics

SHELL = ('<!DOCTYPE html><html lang="en"><head><title>App</title></head>'
         '<body><div id="root"></div>'
         '<script src="/assets/index-a1b2c3.js" type="module"></script>'
         '</body></html>')

RENDERED_HTML = (
    '<!DOCTYPE html><html lang="en"><head><title>App</title></head><body>'
    '<h1>Every document, one place</h1>'
    '<p>Convert, translate and read files without uploading them anywhere.</p>'
    '<a href="/pricing/">Pricing</a>'
    '</body></html>'
)


class WhenToRender(unittest.TestCase):
    def _diag(self, reasons=(), blocks_kept=0):
        diagnostics = PageDiagnostics()
        diagnostics.reasons = list(reasons)
        diagnostics.blocks_kept = blocks_kept
        return diagnostics

    def test_never_means_never(self):
        self.assertFalse(_should_render(RENDER_NEVER,
                                       self._diag([EMPTY_JS_RENDERED])))

    def test_always_means_always(self):
        self.assertTrue(_should_render(RENDER_ALWAYS,
                                       self._diag(blocks_kept=40)))

    def test_auto_renders_a_shell(self):
        self.assertTrue(_should_render(RENDER_AUTO,
                                       self._diag([EMPTY_JS_RENDERED])))

    def test_auto_renders_a_page_that_read_as_empty(self):
        self.assertTrue(_should_render(RENDER_AUTO, self._diag()))

    def test_auto_leaves_a_page_that_already_had_copy(self):
        # Rendering it would cost seconds per page to confirm what is known.
        self.assertFalse(_should_render(RENDER_AUTO, self._diag(blocks_kept=40)))


class _Response:
    status_code = 200
    headers = {"Content-Type": "text/html; charset=utf-8"}

    def __init__(self, url, text):
        self.url = url
        self.text = text

    def raise_for_status(self):
        return None


class _Session:
    headers: dict = {}

    def __init__(self, text):
        self.text = text
        self.fetched = []

    def update(self, *_a, **_kw):
        return None

    def get(self, url, timeout=None, **_kwargs):
        self.fetched.append(url)
        return _Response(url, self.text)


class RenderingACrawl(unittest.TestCase):
    def _crawl(self, render=None, mode=RENDER_AUTO, depth=0):
        session = _Session(SHELL)
        with patch("crawler.requests.Session", return_value=session):
            pages = crawl("https://example.com",
                          CrawlConfig(max_depth=depth, max_pages=4,
                                      render_mode=mode),
                          render=render)
        return pages, session

    def test_a_shell_read_without_a_browser_has_nothing_in_it(self):
        pages, _ = self._crawl(mode=RENDER_NEVER)
        self.assertEqual(len(pages[0].blocks or []), 0)
        self.assertIn(EMPTY_JS_RENDERED, pages[0].diagnostics.reasons)

    def test_the_rendered_page_is_what_gets_read(self):
        pages, _ = self._crawl(render=lambda url: RENDERED_HTML)
        page = pages[0]
        self.assertTrue(page.blocks)
        texts = " ".join(b.text for b in page.blocks)
        self.assertIn("Every document, one place", texts)
        # The old diagnosis described the shell and is no longer true of what
        # was read, so it must not survive alongside the new reading.
        self.assertNotIn(EMPTY_JS_RENDERED, page.diagnostics.reasons)
        self.assertIn(RENDERED, page.diagnostics.reasons)

    def test_links_come_from_the_rendered_page_so_depth_works(self):
        pages, session = self._crawl(render=lambda url: RENDERED_HTML, depth=1)
        self.assertGreater(len(pages), 1)
        # The trailing slash is normalized away, so `/pricing/` and `/pricing`
        # are fetched once, under one name.
        self.assertIn("https://example.com/pricing", session.fetched)

    def test_a_trailing_slash_does_not_make_a_second_page(self):
        pages, session = self._crawl(
            render=lambda url: RENDERED_HTML.replace(
                "/pricing", "/pricing/"), depth=1)
        fetched_roots = [u for u in session.fetched
                         if u in ("https://example.com",
                                  "https://example.com/")]
        self.assertEqual(len(fetched_roots), 1,
                         "root crawled twice under two spellings")

    def test_a_failed_render_leaves_the_fetched_reading_and_says_why(self):
        def render(_url):
            raise RuntimeError("the page did not load")

        pages, _ = self._crawl(render=render)
        page = pages[0]
        self.assertEqual(page.diagnostics.render_error, "the page did not load")
        self.assertEqual(page.raw_html, SHELL)
        self.assertIn(EMPTY_JS_RENDERED, page.diagnostics.reasons)

    def test_an_empty_render_is_not_mistaken_for_a_rendered_page(self):
        pages, _ = self._crawl(render=lambda url: "")
        self.assertNotIn(RENDERED, pages[0].diagnostics.reasons)


if __name__ == "__main__":
    unittest.main()


class _RedirectingSession:
    """A site where two addresses land on one page, the way a real site
    redirects `/a` and `/b` to the page that replaced them."""

    headers: dict = {}

    def __init__(self, pages: dict, redirects: dict):
        self.pages = pages
        self.redirects = redirects
        self.fetched = []

    def update(self, *_a, **_kw):
        return None

    def get(self, url, timeout=None, **_kwargs):
        self.fetched.append(url)
        landing = self.redirects.get(url, url)
        return _Response(landing, self.pages[landing])


INDEX = ('<!DOCTYPE html><html lang="en"><head><title>Index</title></head>'
         '<body><p>An index page carrying enough visible words to be kept.</p>'
         '<a href="/a">a</a><a href="/b">b</a></body></html>')
LANDING = ('<!DOCTYPE html><html lang="en"><head><title>Page</title></head>'
           '<body><p>The one page that both addresses really lead to.</p>'
           '</body></html>')


class RedirectsToOnePage(unittest.TestCase):
    def _crawl(self):
        session = _RedirectingSession(
            pages={"https://example.com/": INDEX,
                   "https://example.com/page": LANDING},
            redirects={"https://example.com/a": "https://example.com/page",
                       "https://example.com/b": "https://example.com/page"},
        )
        with patch("crawler.requests.Session", return_value=session):
            pages = crawl("https://example.com",
                          CrawlConfig(max_depth=1, max_pages=10,
                                      render_mode=RENDER_NEVER))
        return pages, session

    def test_the_landing_page_is_analysed_once(self):
        # Counting the same copy once per address inflates the page count,
        # repeats every finding, and spends an AI call per repeat.
        pages, _ = self._crawl()
        with_copy = [p for p in pages if p.blocks]
        self.assertEqual(len(with_copy), 2)  # the index and the landing page

    def test_the_second_address_is_recorded_not_dropped(self):
        pages, _ = self._crawl()
        second = [p for p in pages if p.url == "https://example.com/b"][0]
        self.assertEqual(second.blocks, [])
        self.assertIn(EMPTY_REDIRECTED, second.diagnostics.reasons)
        self.assertIn(EMPTY_ALREADY_SEEN, second.diagnostics.reasons)
        self.assertEqual(second.diagnostics.final_url, "https://example.com/page")

    def test_the_redirect_is_still_reported_on_the_page_that_was_read(self):
        pages, _ = self._crawl()
        first = [p for p in pages if p.url == "https://example.com/a"][0]
        self.assertEqual(first.diagnostics.reasons.count(EMPTY_REDIRECTED), 1)


class TheRenderTimeoutIsPortable(unittest.TestCase):
    """The bound on a render used to be `SIGALRM`: absent on Windows and
    unusable off the main thread, and the `except` around it swallowed both,
    so the browser was never asked and a JavaScript page read as empty."""

    def _crawl(self, render):
        session = _Session(SHELL)
        with patch("crawler.requests.Session", return_value=session):
            return crawl("https://example.com",
                         CrawlConfig(max_depth=0, max_pages=1,
                                     render_mode=RENDER_AUTO,
                                     render_timeout=7.5),
                         render=render)

    def test_render_is_called_on_windows(self):
        import sys

        with patch.object(sys, "platform", "win32"):
            pages = self._crawl(lambda url: RENDERED_HTML)
        self.assertEqual(pages[0].diagnostics.reasons, [RENDERED])
        self.assertEqual(pages[0].diagnostics.render_error, "")

    def test_render_is_called_off_the_main_thread(self):
        import threading

        out = {}
        worker = threading.Thread(
            target=lambda: out.setdefault("pages", self._crawl(lambda url: RENDERED_HTML)))
        worker.start()
        worker.join(30)
        self.assertEqual(out["pages"][0].diagnostics.reasons, [RENDERED])

    def test_a_renderer_that_takes_a_timeout_is_given_the_configured_one(self):
        seen = {}

        def render(url, timeout=None):
            seen["timeout"] = timeout
            return RENDERED_HTML

        self._crawl(render)
        self.assertEqual(seen["timeout"], 7.5)

    def test_a_timeout_is_recorded_against_the_page(self):
        def render(url, timeout=None):
            raise TimeoutError(f"render timed out after {timeout}s")

        pages = self._crawl(render)
        self.assertIn("timed out", pages[0].diagnostics.render_error)


class TheRendererStopsItselfAtTheDeadline(unittest.TestCase):
    """`html_renderer` takes the timeout as a deadline its runner polls on
    the Qt thread; no Qt is needed to check the bookkeeping around it."""

    def _renderer(self, audit):
        from audit import driver

        renderer = driver.html_renderer()
        renderer.runner = type("Runner", (), {"audit": staticmethod(audit)})()
        return renderer

    def test_a_page_past_its_deadline_is_a_timeout(self):
        import time
        from types import SimpleNamespace

        holder = {}

        def audit(url):
            time.sleep(0.05)
            # What the runner's 50 ms cancellation poll does.
            cancelled = holder["renderer"]._expired()
            return SimpleNamespace(error="cancelled" if cancelled else "", html="")

        holder["renderer"] = renderer = self._renderer(audit)
        with self.assertRaises(TimeoutError):
            renderer("https://example.com", timeout=0.01)
        self.assertIsNone(renderer._deadline)

    def test_without_a_timeout_nothing_expires(self):
        from types import SimpleNamespace

        holder = {}

        def audit(url):
            holder["expired"] = holder["renderer"]._expired()
            return SimpleNamespace(error="the page did not load", html="")

        holder["renderer"] = renderer = self._renderer(audit)
        with self.assertRaisesRegex(RuntimeError, "did not load"):
            renderer("https://example.com")
        self.assertFalse(holder["expired"])
