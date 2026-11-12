"""What a run is doing while it does it.

The status bar holds one line and overwrites it, which says the run is alive
and nothing else. The design (artboard 3g) replaces that with two lists: the
stages, which say where the run is in its own plan, and the log, which says
what just happened.

The behaviour worth pinning down is the bookkeeping, because it is derived
rather than reported. The workers only ever say which stage they have
*started* - none of them says a stage ended - so "everything before the
current one is finished" and "nothing is still running once the run comes
back" are both inferences this window makes, and both would fail silently:
a stage stuck on "running" still renders.

Headless: Qt runs on the offscreen platform, like the other widget tests.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from analysis_modes import CHECK_ACCESSIBILITY, CHECK_AI_PATTERNS
    from ui import theme
    from ui.main_window import MainWindow
    from ui.window_parts.run_progress import (
        DONE, LOG_LIMIT, PENDING, RUNNING, RunProgressPanel,
    )
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not available")
class Panel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.palette = theme.current_palette("light")

    def panel(self) -> RunProgressPanel:
        widget = RunProgressPanel(self.palette)
        self._alive = getattr(self, "_alive", [])
        self._alive.append(widget)
        return widget

    def test_stages_start_pending_and_all_of_them_are_shown(self):
        """A stage that has not begun is what tells you how much is left."""
        panel = self.panel()
        panel.set_stages([("a", "One"), ("b", "Two"), ("c", "Three")])
        for key in ("a", "b", "c"):
            with self.subTest(stage=key):
                self.assertEqual(panel.stage_state(key), PENDING)

    def test_a_stage_can_be_moved_and_reports_a_detail(self):
        panel = self.panel()
        panel.set_stages([("a", "One")])
        panel.mark("a", RUNNING, "7 of 12")
        self.assertEqual(panel.stage_state("a"), RUNNING)
        self.assertEqual(panel._rows["a"].detail.text(), "7 of 12")

    def test_an_unknown_stage_is_ignored_not_raised(self):
        """Four different workers feed this. One emitting a stage the panel
        did not list must not take the window down."""
        panel = self.panel()
        panel.set_stages([("a", "One")])
        panel.mark("nope", RUNNING)
        self.assertEqual(panel.stage_state("nope"), PENDING)

    def test_setting_stages_again_replaces_them(self):
        panel = self.panel()
        panel.set_stages([("a", "One"), ("b", "Two")])
        panel.set_stages([("c", "Three")])
        self.assertEqual(set(panel._rows), {"c"})

    def test_the_log_is_newest_first(self):
        """The order the design shows, and the order someone watching reads."""
        panel = self.panel()
        panel.add_log("first")
        panel.add_log("second")
        self.assertIn("second", panel.log.item(0).text())
        self.assertIn("first", panel.log.item(1).text())

    def test_every_log_line_is_stamped(self):
        panel = self.panel()
        panel.add_log("crawl /pricing")
        # HH:MM:SS, then the message.
        text = panel.log.item(0).text()
        self.assertRegex(text, r"^\d{2}:\d{2}:\d{2}\s+crawl /pricing$")

    def test_the_log_stops_growing(self):
        """A crawl of a large site emits thousands of lines; keeping them all
        turns a glance into a scroll and holds every URL for the whole run."""
        panel = self.panel()
        for index in range(LOG_LIMIT + 50):
            panel.add_log(f"line {index}")
        self.assertEqual(panel.log.count(), LOG_LIMIT)
        # The newest survived, the oldest did not.
        self.assertIn(f"line {LOG_LIMIT + 49}", panel.log.item(0).text())

    def test_reset_clears_the_log_and_the_states(self):
        panel = self.panel()
        panel.set_stages([("a", "One")])
        panel.mark("a", DONE, "done")
        panel.add_log("x")
        panel.reset()
        self.assertEqual(panel.log.count(), 0)
        self.assertEqual(panel.stage_state("a"), PENDING)

    def test_the_three_states_are_three_different_inks(self):
        """The state of five stages has to be one glance, not five readings."""
        panel = self.panel()
        panel.set_stages([("a", "One")])
        inks = set()
        for state in (PENDING, RUNNING, DONE):
            panel.mark("a", state)
            inks.add(panel._rows["a"].name.styleSheet())
        self.assertEqual(len(inks), 3)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class RunBookkeeping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def stages(self) -> list:
        return [key for key, _label in self.window._stages_for_run()]

    def test_a_site_run_lists_the_stages_it_will_do(self):
        self.window.checks_combo.setCurrentIndex(
            self.window.checks_combo.findData(
                (CHECK_ACCESSIBILITY, CHECK_AI_PATTERNS)))
        self.assertEqual(self.stages()[:2], ["crawl", "extract"])

    def test_the_panel_takes_the_preview_column_while_running(self):
        """The column has nothing to preview during a crawl, and the run's
        own progress is the question being asked at that moment."""
        self.window._on_busy_changed(True)
        self.assertEqual(self.window.col1_stack.currentIndex(), 2)

    def test_it_gives_the_column_back_when_the_run_ends(self):
        self.window._on_busy_changed(True)
        self.window._on_busy_changed(False)
        self.assertNotEqual(self.window.col1_stack.currentIndex(), 2)

    def test_hearing_about_a_later_stage_finishes_the_earlier_ones(self):
        """No worker says a stage ended. Being told about a later one is the
        only signal that the earlier ones are behind us."""
        from analysis_modes import CHECK_AI_PATTERNS

        self.window.app_state.set_checks((CHECK_AI_PATTERNS,))
        self.window._on_busy_changed(True)
        self.window._on_detecting("local engine")
        state = self.window.run_progress.stage_state
        self.assertEqual(state("crawl"), DONE)
        self.assertEqual(state("extract"), DONE)
        self.assertEqual(state("detect"), RUNNING)

    def test_no_stage_is_left_running_after_the_run_comes_back(self):
        """The last stage would otherwise sit on "running" forever, which
        renders perfectly and is a lie."""
        self.window._on_busy_changed(True)
        self.window._on_crawling("https://example.com", 1)
        self.window._on_busy_changed(False)
        running = [key for key in self.stages()
                   if self.window.run_progress.stage_state(key) == RUNNING]
        self.assertEqual(running, [])

    def test_the_log_survives_the_run_that_wrote_it(self):
        """The run that just finished is the one about to be asked questions,
        and its log is the answer to most of them."""
        self.window._on_busy_changed(True)
        self.window._on_crawling("https://example.com", 1)
        self.window._on_busy_changed(False)
        self.assertGreater(self.window.run_progress.log.count(), 0)

    def test_the_width_switcher_goes_away_and_comes_back(self):
        """It belongs to the preview, and there is no preview while the panel
        is up - three buttons that change nothing are worse than none."""
        # A page in the preview: the switcher is hidden by an empty column
        # too, and this test is about the run, not about that.
        self.window.current_preview_url = "https://example.com/"
        self.window._on_busy_changed(True)
        self.assertTrue(self.window.breakpoint_row.isHidden())
        self.window._on_busy_changed(False)
        self.assertFalse(self.window.breakpoint_row.isHidden())

    def test_the_column_stops_calling_itself_a_run(self):
        """A finished run under a header that says "Run in progress" is a
        label that renders perfectly and is wrong."""
        before = self.window.col1_header.text()
        self.window._on_busy_changed(True)
        self.assertNotEqual(self.window.col1_header.text(), before)
        self.window._on_busy_changed(False)
        self.assertEqual(self.window.col1_header.text(), before)

    def test_a_new_run_starts_from_a_clean_panel(self):
        self.window._on_busy_changed(True)
        self.window._on_crawling("https://example.com", 1)
        self.window._on_busy_changed(False)
        self.window._on_busy_changed(True)
        self.assertEqual(self.window.run_progress.log.count(), 0)
        self.assertEqual(self.window.run_progress.stage_state("crawl"), PENDING)


if __name__ == "__main__":
    unittest.main()
