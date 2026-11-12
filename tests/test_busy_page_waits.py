"""A page that says it is still loading is measured when it is done (T-2337).

Coach's /app showed a skeleton under `aria-busy="true"` while its data came
in, and the pass read that: no `<h1>`, and a card whose `aria-labelledby`
pointed at a heading not rendered yet.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

LOADING = """<!DOCTYPE html><html lang="en"><head><title>App</title></head><body>
<main><div role="status" aria-busy="true" id="s">Loading</div></main>
<script>setTimeout(function() {
  document.querySelector('main').innerHTML = '<h1>Loaded</h1>';
}, %d);</script></body></html>"""


def _audit(page: str):
    from audit import browser, driver

    with TemporaryDirectory() as folder:
        path = Path(folder) / "page.html"
        path.write_text(page, encoding="utf-8")
        options = browser.BrowserAuditOptions(
            run_axe=False, run_htmlcs=False, run_states=False,
            run_measurements=False, allow_local_files=True, settle_ms=100,
            capture_html=True, capture_text=False)
        driver.ensure_headless_application()
        runner = driver.BrowserAuditRunner(options)
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

    def test_the_page_is_read_after_it_stops_being_busy(self):
        result = _audit(LOADING % 1200)
        self.assertIn("<h1>Loaded</h1>", result.html)
        self.assertNotIn("busy", result.engine_errors)

    def test_a_page_busy_for_ever_is_measured_anyway_and_says_so(self):
        from audit import driver

        with mock.patch.object(driver, "BUSY_WAIT_MS", 500):
            result = _audit(LOADING % 600000)
        self.assertIn("Loading", result.html)
        self.assertIn("busy", result.engine_errors)


#: SharePoint's search suggestions popup: busy, empty and not rendered, on
#: every page. Synthetic, the shape of it only.
HIDDEN_BUSY = """<!DOCTYPE html><html lang="en"><head><title>Intranet</title></head>
<body><main><h1>News</h1></main>
<div id="searchux-popup-0" role="listbox" aria-busy="true" style="display:none"></div>
<div aria-hidden="true"><div role="status" aria-busy="true">Loading</div></div>
<div role="status" aria-busy="true" style="visibility:hidden">Loading</div>
<div role="status" aria-busy="true"></div>
</body></html>"""


class OnlyARenderedBusyElementIsWaitedFor(unittest.TestCase):
    setUpClass = InARealBrowser.setUpClass

    def test_hidden_and_empty_busy_elements_do_not_hold_the_page(self):
        import time

        started = time.monotonic()
        result = _audit(HIDDEN_BUSY)
        elapsed = time.monotonic() - started
        self.assertNotIn("busy", result.engine_errors)
        self.assertLess(elapsed, 6)

    def test_a_visible_skeleton_is_still_waited_for(self):
        # The Coach case, again, beside the hidden popup.
        page = (LOADING % 1200).replace(
            "</body>", '<div role="listbox" aria-busy="true" hidden></div></body>')
        result = _audit(page)
        self.assertIn("<h1>Loaded</h1>", result.html)


FADING = """<!DOCTYPE html><html lang="en"><head><title>App</title><style>
  @keyframes appear { from { opacity: 0.1; } to { opacity: 1; } }
  h1 { animation: appear 1.5s ease-out forwards; }
  .spin { animation: turn 1s linear infinite; }
  @keyframes turn { to { transform: rotate(360deg); } }
</style></head><body><main><h1 id="t">Exam</h1><i class="spin">*</i></main>
</body></html>"""


class Animations(unittest.TestCase):
    setUpClass = InARealBrowser.setUpClass

    def test_a_fade_in_is_over_before_the_page_is_read(self):
        from audit import browser, driver

        with TemporaryDirectory() as folder:
            path = Path(folder) / "page.html"
            path.write_text(FADING, encoding="utf-8")
            options = browser.BrowserAuditOptions(
                run_axe=False, run_htmlcs=False, run_states=False,
                run_measurements=False, allow_local_files=True, settle_ms=100,
                capture_html=True, capture_text=False)
            driver.ensure_headless_application()
            runner = driver.BrowserAuditRunner(options)
            try:
                import time
                started = time.monotonic()
                result = runner.audit(path.resolve().as_uri())
                elapsed = time.monotonic() - started
            finally:
                runner.close()
        # Waited for the 1.5 s fade, and not for the infinite spinner.
        self.assertGreater(elapsed, 1.3)
        self.assertLess(elapsed, 7)
        self.assertNotIn("busy", result.engine_errors)


if __name__ == "__main__":
    unittest.main()
