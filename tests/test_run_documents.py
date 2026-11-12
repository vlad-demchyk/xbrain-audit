"""What a run produced: the folder, the four documents, and the panel.

Three things are worth holding still here.

The first is that there is no save dialog any more. A run produces four
documents that only mean something together, and their home is decided by
`cli_impl.runfolder`; the window's job is to write them and say where, not
to ask four times.

The second is that an absent document is information. `changes.md` is not
written on a first run - deliberately, since an empty comparison reads as a
broken one - so the panel must distinguish "there is nothing to compare
against yet" from "the comparison failed" from "you did not ask for the
audit that would produce one". Three different pieces of news that would
otherwise all render as a missing row.

The third is a regression guard. `export_styled_report` called
`write_styled_report(model, path)` against a `(path, model)` signature, so
the button raised `TypeError` every single time it was pressed, and no test
noticed because every test called the writer directly.

Headless: Qt runs on the offscreen platform, like the other widget tests.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from audit.base import Issue
    from audit.engine import AccessibilityResult, DocumentReport
    from cli_impl import runfolder
    from cli_impl.runfolder import RunDocuments
    from models import AnalysisResult, Confidence, PageResult, TextSpan
    from ui import theme
    from ui.main_window import MainWindow
    from ui.window_parts.report_documents import (
        FIRST_RUN, NO_AUDIT, NOT_COMPARABLE, RunDocumentsPanel, TimingBar,
    )
    from ui.window_parts.run_progress import DONE, RUNNING
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


def audit_result(root: str = "https://example.com") -> "AccessibilityResult":
    """One page with one real finding on it."""
    issue = Issue(rule_id="image-alt", severity="critical",
                  selector="img", source=root)
    return AccessibilityResult(
        root=root, mode="web",
        documents=[DocumentReport(source=root, issues=[issue],
                                  elements_checked=12)],
        rules_run=["image-alt"])


def text_result(root: str = "https://example.com") -> "AnalysisResult":
    span = TextSpan(block_id="b", start=0, end=1, score=0.9,
                    confidence=Confidence.HIGH, detector_name="test")
    return AnalysisResult(root_url=root,
                          pages=[PageResult(url=root, depth=0)],
                          spans=[span])


@unittest.skipIf(QApplication is None, "PySide6 not available")
class Panel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.palette = theme.current_palette("light")

    def panel(self) -> "RunDocumentsPanel":
        widget = RunDocumentsPanel(self.palette)
        self._alive = getattr(self, "_alive", [])
        self._alive.append(widget)
        return widget

    def documents(self, written=None, absent=None) -> "RunDocuments":
        folder = runfolder.RunFolder(Path("/tmp/x"), Path("/tmp/x/2026-08-25-1200"))
        return RunDocuments(folder=folder, target="example.com",
                            written=written or {}, absent=absent or {})

    def test_all_four_are_listed_even_when_three_were_written(self):
        """A reader who knows there are four documents and is shown three
        cannot tell which one is missing."""
        panel = self.panel()
        panel.show_documents(self.documents(
            written={"report.pdf": Path("a"), "report.md": Path("b"),
                     "timings.md": Path("c")},
            absent={"changes.md": FIRST_RUN}))
        self.assertEqual(set(panel._rows), set(RunDocuments.ORDER))

    def test_an_absent_document_says_why(self):
        panel = self.panel()
        panel.show_documents(self.documents(absent={"changes.md": FIRST_RUN}))
        self.assertNotEqual(panel._rows["changes.md"].note.text(), "")

    def test_the_three_reasons_read_differently(self):
        """"First run" and "the comparison could not be made" are opposite
        pieces of news and must not render as the same grey row."""
        panel = self.panel()
        notes = set()
        for reason in (FIRST_RUN, NOT_COMPARABLE, NO_AUDIT):
            panel.show_documents(self.documents(absent={"changes.md": reason}))
            notes.add(panel._rows["changes.md"].note.text())
        self.assertEqual(len(notes), 3)

    def test_a_written_document_and_an_absent_one_are_different_inks(self):
        panel = self.panel()
        panel.show_documents(self.documents(
            written={"report.pdf": Path("a")},
            absent={"changes.md": FIRST_RUN}))
        self.assertNotEqual(panel._rows["report.pdf"].label.styleSheet(),
                            panel._rows["changes.md"].label.styleSheet())

    def test_the_title_says_which_run_this_was(self):
        """Not just which target: the folder holds every run of it, and
        "example.com" alone does not say which one is on screen."""
        panel = self.panel()
        panel.show_documents(self.documents())
        self.assertIn("example.com", panel.target_label.text())
        self.assertIn("2026-08-25-1200", panel.target_label.text())

    def test_the_folder_path_is_shown_and_can_be_copied(self):
        """It is the thing someone pastes into a terminal."""
        from PySide6.QtCore import Qt
        panel = self.panel()
        panel.show_documents(self.documents())
        self.assertIn("2026-08-25-1200", panel.folder_label.text())
        self.assertTrue(panel.folder_label.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextSelectableByMouse)

    def test_shares_are_of_the_stages_shown(self):
        """Against a total that includes time no bar accounts for, every bar
        would be short - which reads as "all the stages were fast" on a run
        that took an hour."""
        panel = self.panel()
        panel.set_timings([("crawl", 30.0), ("browser", 90.0)])
        self.assertAlmostEqual(panel._timing_widgets[0]._share, 0.25)
        self.assertAlmostEqual(panel._timing_widgets[1]._share, 0.75)

    def test_a_stage_that_never_ran_gets_no_bar(self):
        """A run without the browser pass did not do it in no time; it did
        not do it, and a zero-length row says the opposite."""
        panel = self.panel()
        panel.set_timings([("crawl", 30.0), ("browser", None)])
        self.assertEqual(len(panel._timing_widgets), 1)

    def test_the_timing_section_disappears_when_nothing_was_timed(self):
        panel = self.panel()
        panel.set_timings([])
        self.assertTrue(panel.timings_title.isHidden()
                        or not panel.timings_title.isVisibleTo(panel))

    def test_open_folder_without_a_run_does_nothing(self):
        panel = self.panel()
        panel._on_open_folder()  # must not raise

    def test_a_bar_paints_its_share(self):
        bar = TimingBar(self.palette)
        bar.resize(100, TimingBar.HEIGHT)
        bar.set_share(0.5)
        image = bar.grab().toImage()
        colour = image.pixelColor(10, TimingBar.HEIGHT // 2)
        self.assertEqual("#%02x%02x%02x" % (colour.red(), colour.green(),
                                            colour.blue()),
                         self.palette.accent)
        bar.deleteLater()


@unittest.skipIf(QApplication is None, "PySide6 not available")
class WritingTheFolder(unittest.TestCase):
    """`view_model.save_run_documents` against a real temporary Desktop."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.previous = os.environ.get(runfolder.ROOT_ENV)
        os.environ[runfolder.ROOT_ENV] = self.root.name
        self.addCleanup(self._restore_root)
        # History lives in the home folder and is shared with the CLI, so a
        # test that wrote there would compare against the developer's own
        # runs and leave entries behind.
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.previous_home = os.environ.get("HOME")
        os.environ["HOME"] = self.home.name
        # `Path.home()` reads USERPROFILE on Windows, not HOME: without this
        # the test compared against, and wrote into, the real history.
        self.previous_profile = os.environ.get("USERPROFILE")
        os.environ["USERPROFILE"] = self.home.name
        self.addCleanup(self._restore_home)
        # And the working directory, because `_read_history` also merges in
        # the legacy `./.xanalyze/` files - this repository has its own, full
        # of real runs against example.com, so a "first run" test standing in
        # it compares against the developer's history and finds a previous
        # run that has nothing to do with the test.
        self.cwd = os.getcwd()
        os.chdir(self.home.name)
        self.addCleanup(lambda: os.chdir(self.cwd))
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)
        self.view_model = self.window.view_model

    def _restore_root(self):
        if self.previous is None:
            os.environ.pop(runfolder.ROOT_ENV, None)
        else:
            os.environ[runfolder.ROOT_ENV] = self.previous

    def _restore_home(self):
        if self.previous_home is not None:
            os.environ["HOME"] = self.previous_home
        if self.previous_profile is None:
            os.environ.pop("USERPROFILE", None)
        else:
            os.environ["USERPROFILE"] = self.previous_profile

    def save(self, *, audit=True, text=True, target="https://example.com",
             timings=None):
        self.view_model.state.set_target(target)
        self.view_model.audit_result = audit_result(target) if audit else None
        self.view_model.result = text_result(target) if text else None
        return self.view_model.save_run_documents(stage_timings=timings or [])

    def test_the_documents_land_in_one_folder(self):
        """Four documents in four places is what a save dialog produces."""
        documents = self.save()
        folders = {path.parent for path in documents.written.values()}
        self.assertEqual(len(folders), 1)
        self.assertEqual(folders.pop(), documents.folder.run)

    def test_the_report_and_the_timings_are_really_on_disk(self):
        documents = self.save()
        for name in ("report.md", "report.pdf", "timings.md"):
            with self.subTest(document=name):
                self.assertTrue(documents.written[name].exists())

    def test_a_first_run_has_no_comparison_and_says_so(self):
        documents = self.save()
        self.assertNotIn("changes.md", documents.written)
        self.assertEqual(documents.absent["changes.md"], "first_run")
        self.assertFalse(documents.folder.changes.exists())

    def test_a_second_run_of_the_same_target_gets_one(self):
        """The comparison is the reason the folders sit side by side."""
        self.save()
        documents = self.save()
        self.assertIn("changes.md", documents.written)
        self.assertTrue(documents.written["changes.md"].exists())

    def test_a_copy_scan_has_no_briefing_and_names_the_reason(self):
        """`report.md` is a rule-by-rule briefing; a run that asked no rules
        has none to write, which is not the same as a failure."""
        documents = self.save(audit=False)
        self.assertEqual(documents.absent["report.md"], "no_audit")
        self.assertIn("report.pdf", documents.written)

    def test_each_target_gets_its_own_folder(self):
        first = self.save(target="https://example.com")
        second = self.save(target="https://other.test")
        self.assertNotEqual(first.folder.project, second.folder.project)

    def test_the_measured_stages_reach_timings_md(self):
        documents = self.save(timings=[("Crawling links", 38.0),
                                       ("Browser pass", 180.0)])
        written = documents.written["timings.md"].read_text()
        self.assertIn("Crawling links", written)
        self.assertIn("3m 00s", written)

    def test_a_run_with_nothing_found_writes_nothing(self):
        self.view_model.state.set_target("https://example.com")
        self.view_model.audit_result = None
        self.view_model.result = None
        self.assertIsNone(self.view_model.save_run_documents())

    def test_the_styled_report_takes_its_arguments_in_the_right_order(self):
        """The regression this file exists for: the window's report button
        called `write_styled_report(model, path)` against a `(path, model)`
        signature, so it raised `TypeError` every time it was pressed."""
        self.view_model.state.set_target("https://example.com")
        self.view_model.result = text_result()
        self.view_model.audit_result = None
        target = Path(self.root.name) / "one-off.html"
        self.view_model.export_styled_report(str(target))
        self.assertTrue(target.exists())

    def test_the_report_is_written_in_the_window_s_language(self):
        """It used to be called without one, so an Italian window would have
        printed an English report if it had printed one at all."""
        self.view_model.settings.ui_language = "it"
        self.view_model.state.set_target("https://example.com")
        self.view_model.result = text_result()
        self.view_model.audit_result = None
        target = Path(self.root.name) / "it.html"
        self.view_model.export_styled_report(str(target))
        html = target.read_text(encoding="utf-8")
        self.assertIn('lang="it"', html)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class InTheWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def documents(self):
        folder = runfolder.RunFolder(Path("/tmp/x"), Path("/tmp/x/2026-08-25-1200"))
        return RunDocuments(folder=folder, target="example.com",
                            written={"report.pdf": Path("/tmp/x/a")},
                            absent={"changes.md": FIRST_RUN})

    def test_a_stage_records_how_long_it_ran(self):
        """This is the number `timings.md` reports, so it is measured rather
        than estimated: a made-up duration answers the question wrongly and
        looks exactly the same."""
        self.window._on_busy_changed(True)
        self.window.run_progress.mark("crawl", RUNNING, now=100.0)
        self.window.run_progress.mark("crawl", DONE, now=138.0)
        self.assertEqual(dict(self.window.run_progress.durations())
                         [self.window.run_progress._rows["crawl"].label], 38.0)

    def test_a_stage_that_never_started_reports_no_duration(self):
        self.window._on_busy_changed(True)
        self.assertEqual(self.window.run_progress.durations(), [])

    def test_the_panel_takes_the_column_and_renames_the_header(self):
        before = self.window.col1_header.text()
        self.window._show_run_documents(self.documents())
        self.assertEqual(self.window.col1_stack.currentIndex(), 3)
        self.assertNotEqual(self.window.col1_header.text(), before)

    def test_the_width_switcher_goes_away_under_it(self):
        """It constrains a preview, and there is no preview under this."""
        self.window._show_run_documents(self.documents())
        self.assertTrue(self.window.breakpoint_row.isHidden())

    def test_back_gives_the_column_to_the_preview_again(self):
        before = self.window.col1_header.text()
        self.window._show_run_documents(self.documents())
        self.window.run_documents.back_btn.click()
        self.assertNotEqual(self.window.col1_stack.currentIndex(), 3)
        self.assertEqual(self.window.col1_header.text(), before)

    def test_the_measured_stages_reach_the_panel(self):
        self.window._on_busy_changed(True)
        self.window.run_progress.mark("crawl", RUNNING, now=0.0)
        self.window.run_progress.mark("crawl", DONE, now=12.0)
        self.window._show_run_documents(self.documents())
        self.assertEqual(len(self.window.run_documents._timing_widgets), 1)

    def test_nothing_to_report_means_no_folder_is_written(self):
        """Pressing the button on an empty window must not leave a folder
        behind on someone's Desktop."""
        self.window.result = None
        self.window.audit_result = None
        self.window._on_styled_report_clicked()
        self.assertNotEqual(self.window.col1_stack.currentIndex(), 3)


if __name__ == "__main__":
    unittest.main()
