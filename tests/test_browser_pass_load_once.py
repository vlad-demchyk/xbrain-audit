"""One page, one load: what the browser pass is allowed to spend.

Measured 2026-09-01 on a live 250-page WordPress site. The audit reports
findings per *document*, and a page produces several: its own rules, the
response headers, the provenance of an image on it. The browser pass was
driven by that list, so 250 addresses arrived as **474 loads**, each at four
widths - and 50 of those documents were `.jpg`, `.webp` and `.pdf`, which a
page engine has no business opening at all.

Nothing was wrong in the report that came out; the cost was. The browser
pass is the expensive half of an audit (12 s per page at four widths against
0.05 s for every static rule), so a duplicate is not a rounding error - it
was half the run, about three hours of the six.
"""
import unittest
from unittest import mock

from audit.engine import AccessibilityResult, DocumentReport
from audit.browser import BrowserAuditOptions
from cli_impl import auditpass


class _Audit:
    """What `runner.audit` hands back, reduced to what this pass reads."""

    def __init__(self, url):
        self.url = url
        self.error = ""
        self.engine_errors = {}


class WhichDocumentsReachABrowser(unittest.TestCase):

    def test_a_page_is_renderable(self):
        for url in ("https://x.test/", "https://x.test/page",
                    "https://x.test/a.html", "https://x.test/i.php?src=a.jpg"):
            with self.subTest(url):
                self.assertTrue(auditpass._is_renderable(url))

    def test_a_page_the_crawl_refused_is_not_loaded_by_another_pass(self):
        """A headers document carries no error; the page's own did."""
        from types import SimpleNamespace as Doc

        documents = [Doc(source="https://x.test/big", error="page larger than 10 MB, not read"),
                     Doc(source="https://x.test/big", error=""),
                     Doc(source="https://x.test/", error="")]
        self.assertEqual(auditpass.unread_sources(documents), {"https://x.test/big"})

    def test_a_file_that_is_not_a_page_is_not(self):
        for url in ("https://x.test/photo.jpg", "https://x.test/a.WEBP",
                    "https://x.test/brochure.pdf", "https://x.test/clip.mp4"):
            with self.subTest(url):
                self.assertFalse(auditpass._is_renderable(url))


class WhatThePassActuallySends(unittest.TestCase):
    """The filter has to hold where the pass reads it, not only in a helper.

    An image document reaching `_audit_at_widths` is the defect: the address
    is opened in a page engine, axe runs against whatever the browser wraps
    it in, and the result is merged into a document that describes a file.
    """

    def test_media_documents_never_reach_the_browser(self):
        result = AccessibilityResult(root="https://x.test/", mode="web")
        result.documents = [
            DocumentReport(source="https://x.test/"),
            DocumentReport(source="https://x.test/photo.jpg"),
            DocumentReport(source="https://x.test/brochure.pdf"),
            DocumentReport(source="https://x.test/page"),
        ]
        seen = {}

        def _fake(urls, options, sizes, on_page=None, markup=None):
            seen["urls"] = list(urls)
            return [_Audit(url) for url in urls]

        with mock.patch("audit.driver.available", return_value=(True, "")), \
                mock.patch.object(auditpass, "_audit_at_widths", _fake), \
                mock.patch("audit.browser.merge_into_document"):
            auditpass._run_browser_pass(result, mock.Mock(selectors=[], rules=[]))
        self.assertEqual(seen["urls"],
                         ["https://x.test/", "https://x.test/page"])

    def test_one_page_is_merged_into_one_document(self):
        """The browser answers about a page. Folding that answer into every
        document naming the page counted each browser finding two or three
        times: measured on a live site, `perf-page-weight` for the home page
        appeared three times in one report."""
        result = AccessibilityResult(root="https://x.test/", mode="web")
        page, headers, other = (DocumentReport(source="https://x.test/"),
                                DocumentReport(source="https://x.test/"),
                                DocumentReport(source="https://x.test/page"))
        result.documents = [page, headers, other]
        merged = []

        def _fake(urls, options, sizes, on_page=None, markup=None):
            return [_Audit(url) for url in urls]

        with mock.patch("audit.driver.available", return_value=(True, "")), \
                mock.patch.object(auditpass, "_audit_at_widths", _fake), \
                mock.patch("audit.browser.merge_into_document",
                           side_effect=lambda doc, audit, **_: merged.append(doc)):
            auditpass._run_browser_pass(result, mock.Mock(selectors=[], rules=[]))
        self.assertEqual(merged, [page, other])

    def test_the_count_it_announces_is_pages_not_documents(self):
        """"browser pass over 9 page(s)" for a four-page site, then a run
        that stops at "4/9", is a progress line that reads as a failure."""
        result = AccessibilityResult(root="https://x.test/", mode="web")
        result.documents = [DocumentReport(source="https://x.test/"),
                            DocumentReport(source="https://x.test/"),
                            DocumentReport(source="https://x.test/page")]
        lines = []

        def _fake(urls, options, sizes, on_page=None, markup=None):
            if on_page:
                on_page(1, urls[0])
            return [_Audit(url) for url in urls]

        with mock.patch("audit.driver.available", return_value=(True, "")), \
                mock.patch.object(auditpass, "_audit_at_widths", _fake), \
                mock.patch("audit.browser.merge_into_document"), \
                mock.patch("sys.stderr") as err:
            err.write.side_effect = lambda text: lines.append(text)
            auditpass._run_browser_pass(result, mock.Mock(selectors=[], rules=[]))
        printed = "".join(lines)
        self.assertIn("browser pass over 2 page(s)", printed)
        self.assertIn("[browser 1/2]", printed)


class HowManyTimesOnePageIsLoaded(unittest.TestCase):
    """`_audit_at_widths` renders each address once and shares the answer."""

    def _run(self, urls):
        rendered = []

        class _Runner:
            def __init__(self, options):
                pass

            def audit(self, url):
                rendered.append(url)
                return _Audit(url)

            def close(self):
                pass

        # Patched on the module rather than in `sys.modules`: the pass does
        # `from audit import driver`, which reads the attribute on the
        # package once it has been imported, and a suite where some other
        # test imported it first would get the real browser.
        with mock.patch("audit.driver.BrowserAuditRunner", _Runner), \
                mock.patch("audit.driver.ensure_headless_application"):
            results = auditpass._audit_at_widths(urls, options=BrowserAuditOptions(),
                                                 sizes=())
        return rendered, results

    def test_the_same_address_twice_is_one_load(self):
        urls = ["https://x.test/a", "https://x.test/a", "https://x.test/b"]
        rendered, results = self._run(urls)
        self.assertEqual(rendered, ["https://x.test/a", "https://x.test/b"])
        # Every document still gets an answer - the second copy is shared,
        # not dropped, or its findings would never reach the report.
        self.assertEqual([r.url for r in results],
                         ["https://x.test/a", "https://x.test/a",
                          "https://x.test/b"])

    def test_a_repeat_asks_the_cache_nothing(self):
        """The cache is keyed on the markup, so a second lookup for the same
        address can only return the same answer - and counting it made the
        summary line read "9/9 page(s) unchanged" for a four-page site."""
        stored = _Audit("https://x.test/a")
        cache = mock.Mock()
        cache.get.return_value = stored
        cache.summary.return_value = ""
        with mock.patch("browser_cache.BrowserCache", return_value=cache), \
                mock.patch("audit.driver.ensure_headless_application"):
            results = auditpass._audit_at_widths(
                ["https://x.test/a", "https://x.test/a"],
                options=BrowserAuditOptions(), sizes=(),
                markup={"https://x.test/a": "<html>a</html>"})
        self.assertEqual(cache.get.call_count, 1)
        self.assertEqual(results, [stored, stored])

    def test_a_repeat_far_from_the_first_is_still_one_load(self):
        """The duplicates are not always adjacent: a page's media document
        can land at the end of the list, long after the page itself."""
        urls = (["https://x.test/a"] + [f"https://x.test/{n}" for n in range(5)]
                + ["https://x.test/a"])
        rendered, results = self._run(urls)
        self.assertEqual(len(rendered), 6)
        self.assertEqual(rendered.count("https://x.test/a"), 1)
        self.assertIsNotNone(results[-1])
        self.assertEqual(results[-1].url, "https://x.test/a")


if __name__ == "__main__":
    unittest.main()
