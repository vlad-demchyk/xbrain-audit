"""Web parts rendered only when scrolled into view are read anyway.

SharePoint Online is believed to render a web part when it comes into view
(a HYPOTHESIS until a live page confirms it - see `audit.sharepoint_zones`).
A page read without scrolling then has nothing below the fold, and an audit
of nothing comes back clean. The page here plays that part: its second web
part exists only after the page has been scrolled.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

LAZY_PAGE = """<!DOCTYPE html><html lang="en"><head><title>Home</title>
<script>var _spPageContextInfo = {"siteServerRelativeUrl": "/sites/ExampleSite"};</script>
</head><body style="margin:0">
<div data-sp-feature-tag="Rich Text Editor"><p>Above the fold</p></div>
<div style="height:4000px"></div>
<div id="slot"></div>
<script>
window.addEventListener('scroll', function () {
  if (window.scrollY > 1000 && !document.getElementById('late')) {
    document.getElementById('slot').innerHTML =
      '<div id="la' + 'te" data-sp-feature-tag="Late web part"><img src="late.png"></div>';
  }
});
</script></body></html>"""

PLAIN_PAGE = """<!DOCTYPE html><html lang="en"><head><title>Plain</title></head>
<body><p>Nothing lazy here</p></body></html>"""


def _audit(page: str, lazy: str = "auto"):
    from audit import browser, driver

    with TemporaryDirectory() as folder:
        path = Path(folder) / "page.html"
        path.write_text(page, encoding="utf-8")
        options = browser.BrowserAuditOptions(
            run_axe=False, run_htmlcs=False, run_states=False,
            run_measurements=False, allow_local_files=True, settle_ms=100,
            capture_html=True, capture_text=False, viewport=(1024, 600))
        driver.ensure_headless_application()
        runner = driver.BrowserAuditRunner(options, lazy_scroll=lazy)
        try:
            return runner.audit(path.resolve().as_uri())
        finally:
            runner.close()


class InARealBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from audit import driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)

    def test_a_sharepoint_page_is_scrolled_until_its_parts_stop_arriving(self):
        result = _audit(LAZY_PAGE)
        self.assertEqual(result.error, "")
        self.assertIn('id="late"', result.html)
        self.assertTrue(result.lazy["scrolled"])
        self.assertTrue(result.lazy["stable"])
        self.assertEqual(result.lazy["canvas_controls"], 2)

    def test_never_reads_the_page_as_it_first_appears(self):
        result = _audit(LAZY_PAGE, lazy="never")
        self.assertNotIn('id="late"', result.html)
        self.assertEqual(result.lazy, {})

    def test_an_ordinary_page_is_not_scrolled(self):
        result = _audit(PLAIN_PAGE)
        self.assertEqual(result.error, "")
        self.assertEqual(result.lazy, {})


class TheChoiceIsChecked(unittest.TestCase):
    def test_an_unknown_mode_is_refused(self):
        from audit import driver

        with self.assertRaises(ValueError):
            driver.BrowserAuditRunner(lazy_scroll="sometimes")

    def test_the_wait_is_bounded(self):
        from audit import driver

        self.assertLessEqual(driver.LAZY_WAIT_MS, 30_000)
        self.assertGreaterEqual(driver.LAZY_STABLE_POLLS, 2)


if __name__ == "__main__":
    unittest.main()
