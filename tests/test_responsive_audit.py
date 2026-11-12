"""Auditing one page at several widths, and folding the answers into one list.

Two halves, tested separately on purpose. The merge is pure data and is
tested exhaustively without a browser; the part that needs a real Chromium -
does the page actually believe it is 390 pixels wide - is one end-to-end test
against a local file, skipped where QtWebEngine is missing.

That split matters because the browser half is the one that can silently do
nothing: a page with no view has a viewport of 0x0, every `max-width` media
query matches, and three passes return the same mobile-shaped answer while
looking exactly like a working responsive audit.
"""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from audit.base import Issue, MINOR, ACCESSIBILITY
from audit import responsive
from audit.driver import PageAudit

#: A page whose burger button exists only under 700px and whose wide image
#: exists only above it - so each width has a finding the other cannot see.
RESPONSIVE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>A page with a mobile nav</title>
<style>
  .burger { display: none; }
  @media (max-width: 700px) {
    .burger { display: block; }
    .wide { display: none; }
  }
</style></head>
<body>
  <h1>Heading</h1>
  <button class="burger"><span aria-hidden="true">X</span></button>
  <img class="wide" src="chart.png">
  <p>An ordinary paragraph, visible at every width.</p>
</body></html>
"""


def issue(rule_id="image-alt", snippet="<img>", selector="html > img",
          source="page.html"):
    return Issue(rule_id=rule_id, severity=MINOR, category=ACCESSIBILITY,
                 selector=selector, snippet=snippet, source=source)


def audit(*issues, error="", **kwargs):
    return PageAudit(url="page.html", issues=list(issues), error=error, **kwargs)


class Merging(unittest.TestCase):
    def test_a_finding_at_every_width_is_one_row_naming_them_all(self):
        merged = responsive.merge({
            "desktop": audit(issue()), "tablet": audit(issue()),
            "mobile": audit(issue()),
        })
        self.assertEqual(len(merged.issues), 1)
        self.assertEqual(merged.issues[0].details["breakpoints"],
                         ["desktop", "tablet", "mobile"])
        self.assertEqual(responsive.only_at(merged.issues[0]), "")

    def test_a_finding_at_one_width_says_which(self):
        merged = responsive.merge({
            "desktop": audit(), "tablet": audit(),
            "mobile": audit(issue(rule_id="button-name", snippet="<button>")),
        })
        self.assertEqual(len(merged.issues), 1)
        self.assertEqual(responsive.only_at(merged.issues[0]), "mobile")

    def test_the_same_element_matches_even_when_its_selector_moved(self):
        """A narrower layout genuinely renumbers `nth-of-type` paths, so the
        element's own markup is the identity and the path is the fallback."""
        merged = responsive.merge({
            "desktop": audit(issue(selector="html > body > img:nth-of-type(1)")),
            "mobile": audit(issue(selector="html > body > div > img:nth-of-type(1)")),
        })
        self.assertEqual(len(merged.issues), 1)
        self.assertEqual(merged.issues[0].details["breakpoints"], ["desktop", "mobile"])

    def test_document_level_findings_match_on_the_rule_alone(self):
        """They have neither a selector nor a snippet - what they report is
        something absent - so the rule and the document are all there is."""
        empty = issue(rule_id="seo-canonical", snippet="", selector="")
        merged = responsive.merge({"desktop": audit(empty), "mobile": audit(empty)})
        self.assertEqual(len(merged.issues), 1)

    def test_two_different_elements_stay_two_rows(self):
        merged = responsive.merge({
            "desktop": audit(issue(snippet="<img src='a.png'>"),
                             issue(snippet="<img src='b.png'>")),
        })
        self.assertEqual(len(merged.issues), 2)

    def test_the_first_width_owns_the_measurements(self):
        merged = responsive.merge({
            "desktop": audit(measurements={"bytes": 10}),
            "mobile": audit(measurements={"bytes": 99}),
        })
        self.assertEqual(merged.measurements, {"bytes": 10})

    def test_a_width_that_failed_is_recorded_not_swallowed(self):
        merged = responsive.merge({
            "desktop": audit(issue()), "mobile": audit(error="the page did not load"),
        })
        self.assertFalse(merged.error)
        self.assertIn("mobile", merged.engine_errors)

    def test_a_page_that_failed_everywhere_is_an_error(self):
        merged = responsive.merge({
            "desktop": audit(error="the page did not load"),
            "mobile": audit(error="the page did not load"),
        })
        self.assertTrue(merged.error)
        self.assertEqual(merged.issues, [])

    def test_the_original_issue_is_not_mutated(self):
        """The per-width audits stay usable after a merge: the breakpoint
        list goes on a copy, not on the row the caller still holds."""
        original = issue()
        responsive.merge({"desktop": audit(original)})
        self.assertNotIn("breakpoints", original.details)


class AtRealWidths(unittest.TestCase):
    """The half that needs a browser."""

    @classmethod
    def setUpClass(cls):
        from audit import driver
        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)

    def test_the_page_is_read_at_the_width_it_was_given(self):
        from audit import browser, driver

        with TemporaryDirectory() as folder:
            path = Path(folder) / "page.html"
            path.write_text(RESPONSIVE_PAGE, encoding="utf-8")
            options = browser.BrowserAuditOptions(
                run_axe=False, run_htmlcs=False, run_states=False,
                run_measurements=False, allow_local_files=True, settle_ms=300,
                viewport=(1440, 900))
            driver.ensure_headless_application()
            runner = driver.BrowserAuditRunner(options)
            try:
                widths = []
                for _name, width, height in responsive.BREAKPOINTS:
                    runner.set_viewport(width, height)
                    runner.audit(path.resolve().as_uri())
                    widths.append(self._inner_width(runner))
            finally:
                runner.close()

        self.assertEqual(widths, [w for _n, w, _h in responsive.BREAKPOINTS],
                         "the page did not follow the viewport it was given")

    @staticmethod
    def _inner_width(runner) -> int:
        from PySide6.QtCore import QEventLoop, QTimer

        answer = {}
        loop = QEventLoop()

        def done(value):
            answer["width"] = value
            loop.quit()

        runner._page.runJavaScript("window.innerWidth", 0, done)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        return int(answer.get("width") or 0)


@unittest.skipIf(os.environ.get("XAUDIT_NO_QT"), "Qt disabled")
class PreviewSwitcher(unittest.TestCase):
    """The other half of "audited at three widths": being able to look at
    the page at the width a finding came from."""

    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
            from ui.main_window import MainWindow
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(str(exc))
        cls.app = QApplication.instance() or QApplication([])
        cls.window = MainWindow()

    def test_a_button_per_audited_width(self):
        self.assertEqual(tuple(self.window.breakpoint_buttons),
                         responsive.breakpoint_names())

    def test_choosing_one_pins_the_preview_to_it(self):
        self.window.resize(1300, 800)
        self.window.show()
        self.app.processEvents()
        self.window.breakpoint_buttons["mobile"][0].click()
        # Narrower than the column, so the widget itself is held to it.
        self.assertEqual(self.window.site_view.maximumWidth(), 390)
        self.assertAlmostEqual(self.window.site_view.zoomFactor(), 1.0, places=3)

    def test_choosing_it_again_lets_the_preview_go(self):
        self.window.breakpoint_buttons["mobile"][0].click()
        self.window.breakpoint_buttons["mobile"][0].click()
        self.assertGreater(self.window.site_view.maximumWidth(), 10_000)
        self.assertAlmostEqual(self.window.site_view.zoomFactor(), 1.0, places=3)

    def test_a_width_wider_than_the_column_is_scaled_not_demanded(self):
        """The defect this replaced: `setMinimumWidth(1440)` is a demand on
        the parent, so choosing a desktop width widened the whole window
        instead of changing anything inside the column."""
        self.window.resize(1300, 800)
        self.window.show()
        self.app.processEvents()
        before = self.window.minimumSizeHint().width()
        self.window.breakpoint_buttons["desktop"][0].click()
        self.app.processEvents()
        self.assertEqual(self.window.minimumSizeHint().width(), before)
        self.assertLess(self.window.site_view.zoomFactor(), 1.0)
        # And the page still lays out at the width that was chosen: CSS
        # pixels are what the zoom factor divides.
        laid_out = self.window.site_view.width() / self.window.site_view.zoomFactor()
        self.assertAlmostEqual(laid_out, 1440, delta=2)
        self.window.breakpoint_buttons["desktop"][0].click()

    def test_the_buttons_are_labelled_with_the_width(self):
        labels = {button.text() for button, _width in
                  self.window.breakpoint_buttons.values()}
        self.assertEqual(labels, {"1440", "834", "390", "320"})

    def test_only_one_width_is_ever_pressed(self):
        self.window.breakpoint_buttons["tablet"][0].click()
        self.window.breakpoint_buttons["desktop"][0].click()
        pressed = [name for name, (button, _w) in self.window.breakpoint_buttons.items()
                   if button.isChecked()]
        self.assertEqual(pressed, ["desktop"])

    def test_a_repository_has_no_width_to_look_at(self):
        from analysis_modes import SOURCE_REPO, SOURCE_SITE

        # A page in the preview, because the switcher belongs to the page:
        # with the column empty it is hidden whatever the source is.
        self.window.current_preview_url = "https://example.com/"
        self.window.source = SOURCE_REPO
        self.window._apply_mode_visibility()
        self.assertTrue(self.window.breakpoint_row.isHidden())
        self.window.source = SOURCE_SITE
        self.window._apply_mode_visibility()
        self.assertFalse(self.window.breakpoint_row.isHidden())

    def test_an_empty_preview_has_no_width_to_look_at_either(self):
        """Three widths to view nothing at is furniture above a sentence
        saying there is nothing."""
        from analysis_modes import SOURCE_SITE

        self.window.source = SOURCE_SITE
        self.window.current_preview_url = None
        self.window._apply_mode_visibility()
        self.assertTrue(self.window.breakpoint_row.isHidden())


if __name__ == "__main__":
    unittest.main()
