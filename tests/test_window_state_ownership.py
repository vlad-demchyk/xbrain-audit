"""One owner per fact, and the four faults that came of having two.

The MVVM refactor moved the run's state onto `MainViewModel` and `AppState`
but left the window reading its own copies. Nothing crashed, so nothing said
anything; what happened instead was this, all of it found by running the app:

* Auditing a folder sent `https:///Users/me/project` to the crawler. One
  document, a fetch error, zero findings - reported as a clean audit.
* A run that asked both questions showed only the copy findings. The audit's
  rows were gated on the window's `_last_request`, which nothing ever set.
* The browser pass never ran, gated on the same value.
* The extraction cache never hit, because the window compared a request built
  from its combos against one built from `AppState` - and `AppState` had no
  target until Analyze was pressed.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from analysis_modes import (
        CHECK_ACCESSIBILITY, CHECK_AI_PATTERNS, SOURCE_FILE, SOURCE_REPO,
        SOURCE_SITE,
    )
    from ui.main_window import MainWindow
    from ui.worker import audit_worker_for
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not available")
class AuditWorkerForSource(unittest.TestCase):
    """A folder is walked, a page is read, a site is fetched."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_a_folder_is_audited_as_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker, refusal = audit_worker_for(SOURCE_REPO, target=tmp,
                                               depth=0, max_pages=30)
        self.assertEqual(refusal, "")
        self.assertTrue(worker.is_repo)
        self.assertFalse(worker.is_page_file)

    def test_a_folder_path_is_never_turned_into_a_url(self):
        """The bug, stated directly."""
        with tempfile.TemporaryDirectory() as tmp:
            worker, _ = audit_worker_for(SOURCE_REPO, target=tmp, depth=0,
                                         max_pages=30)
        self.assertEqual(worker.target, tmp)
        self.assertNotIn("https://", worker.target)

    def test_a_single_page_is_audited_as_a_page(self):
        worker, refusal = audit_worker_for(SOURCE_FILE, target="/tmp/a.html",
                                           depth=0, max_pages=30)
        self.assertEqual(refusal, "")
        self.assertTrue(worker.is_page_file)
        self.assertFalse(worker.is_repo)

    def test_a_site_keeps_its_scheme(self):
        worker, _ = audit_worker_for(SOURCE_SITE, target="https://example.com",
                                     depth=1, max_pages=30)
        self.assertEqual(worker.target, "https://example.com")

    def test_a_site_typed_without_a_scheme_gets_one(self):
        worker, _ = audit_worker_for(SOURCE_SITE, target="example.com",
                                     depth=1, max_pages=30)
        self.assertEqual(worker.target, "https://example.com")

    def test_an_empty_target_is_refused(self):
        worker, refusal = audit_worker_for(SOURCE_SITE, target="  ", depth=0,
                                           max_pages=30)
        self.assertIsNone(worker)
        self.assertEqual(refusal, "no_target")

    def test_a_site_target_that_is_not_an_address_is_refused(self):
        worker, refusal = audit_worker_for(SOURCE_SITE, target="not a url",
                                           depth=0, max_pages=30)
        self.assertIsNone(worker)
        self.assertEqual(refusal, "not_a_url")

    def test_the_crawl_depth_reaches_the_worker(self):
        worker, _ = audit_worker_for(SOURCE_SITE, target="example.com",
                                     depth=3, max_pages=7)
        self.assertEqual(worker.depth, 3)
        self.assertEqual(worker.max_pages, 7)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class OneOwner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_the_window_reads_the_run_state_it_does_not_keep_it(self):
        self.assertIs(self.window._last_request,
                      self.window.view_model._last_request)

    def test_the_window_cannot_hold_a_second_copy(self):
        """A property, so a stale write is a failure rather than a divergence."""
        with self.assertRaises(AttributeError):
            self.window._last_request = "anything"

    def test_one_request_builder(self):
        self.assertEqual(self.window.current_request(),
                         self.window.view_model.current_request())

    def test_a_typed_target_reaches_the_state_before_analyze_is_pressed(self):
        self.window.app_state.set_source(SOURCE_SITE)
        self.window.url_edit.setText("example.com")
        self.app.processEvents()
        self.assertEqual(self.window.app_state.target, "example.com")

    def test_a_typed_folder_reaches_the_state(self):
        self.window.app_state.set_source(SOURCE_REPO)
        self.window.source = SOURCE_REPO
        self.window.repo_path_edit.setText("/tmp/project")
        self.app.processEvents()
        self.assertEqual(self.window.app_state.target, "/tmp/project")

    def test_the_depth_reaches_the_state(self):
        self.window.depth_spin.setValue(3)
        self.app.processEvents()
        self.assertEqual(self.window.app_state.depth, 3)

    def test_the_combos_initial_values_reach_the_state(self):
        """`_fill_combo` blocks signals, so the first fill emitted nothing.

        The state then answered with its own constructor default of
        "AI patterns only" while the combo showed "both questions".
        """
        self.assertEqual(set(self.window.app_state.checks),
                         {CHECK_ACCESSIBILITY})

    def test_the_choices_are_read_from_the_state_not_from_the_widget(self):
        self.window.app_state.set_checks((CHECK_ACCESSIBILITY,))
        self.assertEqual(self.window._chosen_checks(), (CHECK_ACCESSIBILITY,))

    def test_the_extraction_cache_hits_across_a_changed_question(self):
        """Changing the question must not re-crawl the site."""
        self.window.app_state.set_source(SOURCE_SITE)
        self.window.url_edit.setText("https://example.com")
        self.window.app_state.set_checks((CHECK_ACCESSIBILITY,))
        self.app.processEvents()
        self.window._remember_extraction(self.window.current_request(),
                                         pages=["one", "two"])
        self.window.app_state.set_checks((CHECK_AI_PATTERNS,))
        self.app.processEvents()
        self.assertEqual(self.window._reusable_pages(), ["one", "two"])

    def test_a_changed_target_drops_the_cache(self):
        self.window.app_state.set_source(SOURCE_SITE)
        self.window.url_edit.setText("https://example.com")
        self.app.processEvents()
        self.window._remember_extraction(self.window.current_request(),
                                         pages=["one"])
        self.window.url_edit.setText("https://other.example")
        self.app.processEvents()
        self.assertIsNone(self.window._reusable_pages())


@unittest.skipIf(QApplication is None, "PySide6 not available")
class GroupedAuditRows(unittest.TestCase):
    """The same problem on five files is one row that says so."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _result(self, sources):
        from audit.base import Issue

        class Document:
            def __init__(self, source):
                self.source = source
                self.error = None
                self.elements_checked = 1
                self.issues = [Issue(rule_id="image-alt", severity="critical",
                                     snippet="<img src=logo.png>",
                                     source=source, line=5)]

        class Result:
            mode = "repo"
            root = "/repo"

            def __init__(self):
                self.documents = [Document(s) for s in sources]

            def issues(self):
                return [i for d in self.documents for i in d.issues]

        return Result()

    def test_five_identical_findings_are_one_row(self):
        self.window.audit_result = self._result(
            [f"p{i}.html" for i in range(5)])
        self.assertEqual(self.window._add_audit_rows(), 1)

    def test_the_row_says_how_many_other_places(self):
        self.window.audit_result = self._result(
            [f"p{i}.html" for i in range(5)])
        self.window._add_audit_rows()
        self.assertIn("4", self.window.flagged_list.item(0).text())

    def test_the_grouped_issues_travel_with_the_row(self):
        """The detail card lists every place, so it needs them all."""
        from PySide6.QtCore import Qt

        self.window.audit_result = self._result(
            [f"p{i}.html" for i in range(5)])
        self.window._add_audit_rows()
        _kind, _issue, others = self.window.flagged_list.item(0).data(
            Qt.ItemDataRole.UserRole)
        self.assertEqual(len(others), 4)

    def test_one_finding_stays_one_row_with_no_count(self):
        self.window.audit_result = self._result(["only.html"])
        self.window._add_audit_rows()
        self.assertNotIn("·", self.window.flagged_list.item(0).text())


@unittest.skipIf(QApplication is None, "PySide6 not available")
class ExplanationsShowTheirMarkup(unittest.TestCase):
    """An explanation about a tag has to show the tag.

    Qt auto-detects rich text, so «add <html lang="uk">» rendered as an HTML
    tag: the example vanished and the sentence ended in a bare colon. Every
    explanation carrying a sample tag was truncated the same way.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_a_field_body_is_plain_text(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel

        from ui.widgets import field

        widget = field("how to fix", 'Add <html lang="uk"> to the root tag.')
        body = widget.findChildren(QLabel)[-1]
        self.assertIn('<html lang="uk">', body.text())
        self.assertEqual(body.textFormat(), Qt.TextFormat.PlainText)

    def test_rich_text_really_does_swallow_the_tag(self):
        """Why the format matters, shown rather than asserted on faith.

        Rendering the same sentence as HTML is what a reader saw: the
        example disappears and the sentence ends in a bare colon.
        """
        from PySide6.QtGui import QTextDocument

        document = QTextDocument()
        document.setHtml('Add <html lang="uk"> to the root tag.')
        self.assertNotIn("<html", document.toPlainText())

    def test_the_muted_label_is_plain_text(self):
        from PySide6.QtCore import Qt

        from ui.widgets import muted

        self.assertEqual(muted("about <img> tags").textFormat(),
                         Qt.TextFormat.PlainText)

    def test_a_heading_is_plain_text(self):
        from PySide6.QtCore import Qt

        from ui.widgets import heading

        self.assertEqual(heading("<img> without alt").textFormat(),
                         Qt.TextFormat.PlainText)

    def test_a_chip_is_plain_text(self):
        from PySide6.QtCore import Qt

        from ui.widgets import chip

        self.assertEqual(chip("<head>").textFormat(), Qt.TextFormat.PlainText)


if __name__ == "__main__":
    unittest.main()
