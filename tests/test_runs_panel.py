"""The runs catalogue in the window: what is on disk, and what can continue.

Before this the interface had no idea a run had ever stopped. A three-quarter
-hour scan that died in its last phase left a folder on the Desktop and told
nobody, so the only way to find out was to go looking.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from cli_impl import runstate
    from ui.main_window import MainWindow
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


class _Folder:
    def __init__(self, run: Path):
        self.project = run.parent
        self.run = run


def _make_run(root: Path, name: str, target: str, *, finished=False,
              failed=False, running=False):
    run = root / "example.com" / name
    run.mkdir(parents=True, exist_ok=True)
    state = runstate.RunState.begin(_Folder(run), target,
                                    argv=["fullscan", target])
    if finished:
        for phase in runstate.PHASES:
            state.start(phase)
            state.done(phase)
        state.finish()
    elif failed:
        state.start("scan")
        state.done("scan")
        state.skip("crawl", "not a website")
        state.start("audit")
        state.fail("audit", "the static audit failed")
    elif running:
        state.start("crawl")
    state.write_feedback()
    return state


@unittest.skipIf(QApplication is None, "PySide6 not available")
class RunsCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._previous_root = os.environ.get("XAUDIT_REPORT_ROOT")
        os.environ["XAUDIT_REPORT_ROOT"] = str(self.root)
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        # Put back what was there, not nothing: popping it sent every later
        # test's runs into the real ~/Documents/XBrain Audit (see conftest).
        if self._previous_root is None:
            os.environ.pop("XAUDIT_REPORT_ROOT", None)
        else:
            os.environ["XAUDIT_REPORT_ROOT"] = self._previous_root
        self.tmp.cleanup()

    def rows(self) -> list:
        layout = self.window.runs_rows_layout
        return [layout.itemAt(i).widget() for i in range(layout.count())]

    def test_an_empty_disk_shows_an_empty_state_not_an_empty_list(self):
        # `isHidden`, not `isVisible`: the panel lives inside the runs popup,
        # which is closed until someone asks for it, and a widget inside a
        # closed window is never `isVisible()` however it was set. What is
        # asserted is the panel's own choice between the two, which is
        # exactly what `isHidden` reports.
        self.assertEqual(self.window.refresh_runs(), 0)
        self.assertFalse(self.window.runs_empty.isHidden())
        self.assertTrue(self.window.runs_scroll.isHidden())

    def test_a_run_on_disk_is_listed(self):
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        self.assertEqual(self.window.refresh_runs(), 1)
        self.assertFalse(self.window.runs_scroll.isHidden())
        self.assertTrue(self.window.runs_empty.isHidden())

    def test_the_row_says_the_target_and_the_state(self):
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        self.window.refresh_runs()
        row = self.rows()[0]
        self.assertIn("example.com", row.target_label.text())
        self.assertIn("ago", row.age_label.text())

    def test_the_row_carries_its_data_rather_than_a_parsed_label(self):
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        self.window.refresh_runs()
        row = self.rows()[0].row
        self.assertEqual(row["target"], "https://example.com")
        self.assertTrue(row["resumable"])

    def test_newest_first(self):
        _make_run(self.root, "2026-08-24-1000", "https://old.example",
                  finished=True)
        _make_run(self.root, "2026-08-24-1200", "https://new.example",
                  failed=True)
        self.window.refresh_runs()
        self.assertEqual(len(self.rows()), 2)

    # -- the one action a row can actually take --------------------------
    #
    # The row used to carry Resume and Pause side by side, and one of the
    # two was always wrong for it: a finished run cannot be paused, a
    # running one cannot be resumed. Half the buttons on screen existed to
    # be refused, and a control that is enabled and then says "nothing to
    # resume" teaches people to distrust the controls.

    def test_a_stopped_run_offers_to_continue(self):
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        self.window.refresh_runs()
        from i18n.translations import t
        self.assertEqual(self.rows()[0].primary_btn.text(),
                         t("runs_resume", self.window.lang))

    def test_a_running_run_offers_to_pause(self):
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  running=True)
        self.window.refresh_runs()
        from i18n.translations import t
        self.assertEqual(self.rows()[0].primary_btn.text(),
                         t("runs_pause", self.window.lang))

    def test_a_finished_run_offers_neither_of_those(self):
        """It offers what it does have: the documents it produced."""
        from i18n.translations import t
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  finished=True)
        self.window.refresh_runs()
        label = self.rows()[0].primary_btn.text()
        self.assertEqual(label, t("runs_report", self.window.lang))
        self.assertNotEqual(label, t("runs_resume", self.window.lang))
        self.assertNotEqual(label, t("runs_pause", self.window.lang))

    def test_pausing_writes_the_request_where_the_run_will_see_it(self):
        state = _make_run(self.root, "2026-08-24-1200", "https://example.com",
                          running=True)
        self.window.refresh_runs()
        self.rows()[0].primary_btn.click()
        self.assertTrue(state.paused_requested())

    def test_the_menu_offers_only_what_the_row_can_do(self):
        """Everything else moved behind "...", and a menu entry that would
        be refused is the same broken promise as a dead button."""
        from i18n.translations import t
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  finished=True)
        self.window.refresh_runs()
        # `menu()`, not `_on_more()`: showing it would block on the event
        # loop, and what is being asserted is what it offers, not that it
        # opens.
        labels = [action.text() for action in self.rows()[0].menu().actions()]
        self.assertIn(t("runs_open", self.window.lang), labels)
        self.assertNotIn(t("runs_resume", self.window.lang), labels)
        self.assertNotIn(t("runs_pause", self.window.lang), labels)

    # -- what the table says ---------------------------------------------

    def test_a_run_that_never_recorded_a_count_shows_a_dash(self):
        """"0" would say it came back clean, which is the opposite of what
        happened to a crawl that stopped in its first phase."""
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        self.window.refresh_runs()
        self.assertEqual(self.rows()[0].found_label.text(), "-")

    def test_a_recorded_count_reaches_the_row(self):
        state = _make_run(self.root, "2026-08-24-1200", "https://example.com",
                          finished=True)
        state.record_findings(27)
        self.window.refresh_runs()
        self.assertEqual(self.rows()[0].found_label.text(), "27")

    def test_a_zero_is_shown_as_zero_not_as_a_dash(self):
        """A run that finished and found nothing is a real answer."""
        state = _make_run(self.root, "2026-08-24-1200", "https://example.com",
                          finished=True)
        state.record_findings(0)
        self.window.refresh_runs()
        self.assertEqual(self.rows()[0].found_label.text(), "0")

    def test_the_subtitle_tells_two_runs_of_one_target_apart(self):
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        self.window.refresh_runs()
        from i18n.translations import t
        self.assertIn(t("runs_kind_site", self.window.lang),
                      self.rows()[0].subtitle.text())

    def test_a_folder_scan_is_not_called_a_site(self):
        _make_run(self.root, "2026-08-24-1200", "/Users/me/code/shop",
                  failed=True)
        self.window.refresh_runs()
        from i18n.translations import t
        self.assertIn(t("runs_kind_repo", self.window.lang),
                      self.rows()[0].subtitle.text())

    def test_the_footer_says_where_the_rest_of_them_are(self):
        """The list is a window onto the disk, not the whole of it."""
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        self.window.refresh_runs()
        self.assertIn(str(self.root), self.window.runs_footer.text())

    def test_an_empty_disk_has_no_footer_to_show(self):
        self.window.refresh_runs()
        self.assertTrue(self.window.runs_footer.isHidden())

    def test_the_panel_and_the_cli_read_the_same_disk(self):
        """One fact, one owner.

        A registry kept by the interface would be a second answer to "what
        runs exist", and it would be the one that went stale as soon as a
        folder was moved by hand.
        """
        from cli_impl.runcmds import run_rows

        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        self.window.refresh_runs()
        panel = [widget.row for widget in self.rows()]
        cli = run_rows(runstate.all_runs(self.root))
        self.assertEqual([r["run"] for r in panel], [r["run"] for r in cli])

    def test_an_unreadable_disk_is_not_a_crash(self):
        (self.root / "broken" / "run").mkdir(parents=True)
        (self.root / "broken" / "run" / "state.json").write_text("{oh no")
        self.assertEqual(self.window.refresh_runs(), 0)

    def test_the_labels_follow_the_interface_language(self):
        _make_run(self.root, "2026-08-24-1200", "https://example.com",
                  failed=True)
        for lang in ("uk", "it", "en"):
            with self.subTest(lang=lang):
                self.window.lang = lang
                self.window._retranslate_runs()
                label = self.rows()[0].primary_btn.text()
                self.assertTrue(label)
                self.assertNotIn("runs_", label)

    def test_a_refresh_leaves_no_rows_from_the_last_one_on_screen(self):
        """`deleteLater` only schedules the deletion, so an unparented row
        would keep rendering under the new list."""
        from PySide6.QtWidgets import QWidget
        _make_run(self.root, "2026-08-24-1000", "https://a.example",
                  finished=True)
        _make_run(self.root, "2026-08-24-1200", "https://b.example",
                  finished=True)
        self.window.refresh_runs()
        import shutil
        shutil.rmtree(self.root / "example.com" / "2026-08-24-1000")
        self.window.refresh_runs()
        live = [child for child in self.window.runs_rows.findChildren(QWidget)
                if child.parent() is self.window.runs_rows]
        self.assertEqual(len(live), 1)

    def test_an_unknown_status_shows_the_word_not_a_translation_key(self):
        """`t` returns its key when it has no entry, and a user must never
        be shown `runs_status_whatever`."""
        from ui.window_parts.runs_panel import _state_text

        text = _state_text({"target": "x", "status": "surprising"},
                           self.window.lang)
        self.assertIn("surprising", text)
        self.assertNotIn("runs_status_", text)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class SourcePickerLabels(unittest.TestCase):
    """Two different strings shared one translation key.

    `source_file` was both the picker's "HTML file" label and a finding's
    "File: {path}:{line}" location line. The later definition won, so the main
    source dropdown offered a literal `Файл: {path}:{line}` as its third
    option, in all three languages. `pyflakes` had been reporting the
    duplicate key the whole time.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_the_picker_names_a_file_type_not_a_location(self):
        from i18n.translations import t

        for lang in ("uk", "it", "en"):
            label = t("source_file", lang)
            self.assertNotIn("{path}", label)
            self.assertNotIn("{line}", label)

    def test_the_location_line_still_takes_a_path_and_a_line(self):
        from i18n.translations import t

        for lang in ("uk", "it", "en"):
            self.assertIn("a.py", t("finding_file_line", lang,
                                    path="a.py", line=5))

    def test_no_translation_key_is_defined_twice(self):
        """The defect class, not just this instance.

        A duplicate key is silent: the later value wins and the earlier call
        site renders something that was written for somewhere else.
        """
        import ast
        import pathlib

        source = pathlib.Path("i18n/translations.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        duplicates = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            seen = set()
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if key.value in seen:
                        duplicates.append(key.value)
                    seen.add(key.value)
        self.assertEqual(duplicates, [])


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheColumnStaysNarrow(unittest.TestCase):
    """The runs panel must fit the popup it was moved into.

    Three buttons abreast once needed 284px in a 268px column. That raised
    the whole sidebar's minimum width to 308, turned on a horizontal
    scrollbar and clipped every control above it - "Sign in" rendered as
    "Sign i". Found by rendering the window and looking at it, which is why
    the width is asserted here rather than trusted.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._previous_root = os.environ.get("XAUDIT_REPORT_ROOT")
        os.environ["XAUDIT_REPORT_ROOT"] = str(Path(self.tmp.name))
        _make_run(Path(self.tmp.name), "2026-08-24-1200",
                  "https://a-very-long-host-name.cloudwaysapps.com/x",
                  failed=True)
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        # Put back what was there, not nothing: popping it sent every later
        # test's runs into the real ~/Documents/XBrain Audit (see conftest).
        if self._previous_root is None:
            os.environ.pop("XAUDIT_REPORT_ROOT", None)
        else:
            os.environ["XAUDIT_REPORT_ROOT"] = self._previous_root
        self.tmp.cleanup()

    def rows(self) -> list:
        layout = self.window.runs_rows_layout
        return [layout.itemAt(i).widget() for i in range(layout.count())]

    def test_the_panel_fits_the_popup_it_lives_in(self):
        """Opened the way it is actually opened. The popup sizes itself in
        `_on_runs_clicked`, and a test that sizes it by hand would pass over
        a window that clips."""
        self.window.resize(1300, 800)
        self.window.refresh_runs()
        self.window._on_runs_clicked()
        self.app.processEvents()
        self.assertLessEqual(self.window.runs_rows.sizeHint().width(),
                             self.window.runs_popup.width())
        self.window._on_runs_clicked()

    def test_the_list_never_scrolls_sideways(self):
        """A scrollbar here eats a row and widens the whole popup."""
        self.assertEqual(self.window.runs_scroll.horizontalScrollBarPolicy(),
                         Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def test_a_long_address_is_trimmed_from_the_left(self):
        """An address is recognised by its tail."""
        self.window.refresh_runs()
        first = self.rows()[0].target_label.text()
        self.assertTrue(first.startswith("…"))
        self.assertTrue(first.endswith("cloudwaysapps.com/x"))

    def test_nothing_trimmed_is_lost(self):
        self.window.refresh_runs()
        tip = self.rows()[0].toolTip()
        self.assertIn("a-very-long-host-name.cloudwaysapps.com", tip)

    def test_the_popup_opens_inside_the_window(self):
        """It opens under a button near the right edge of a wrapping row,
        and a table wide enough for six columns would otherwise open with
        its action column past the edge of the screen."""
        self.window.resize(1300, 800)
        self.app.processEvents()
        self.window._on_runs_clicked()
        self.app.processEvents()
        right = self.window.mapToGlobal(
            self.window.rect().topRight()).x()
        self.assertLessEqual(
            self.window.runs_popup.x() + self.window.runs_popup.width(), right)
        self.window._on_runs_clicked()

    def test_the_popup_is_never_wider_than_the_window(self):
        self.window.resize(700, 800)
        self.app.processEvents()
        self.window._on_runs_clicked()
        self.app.processEvents()
        self.assertLessEqual(self.window.runs_popup.width(),
                             self.window.width())
        self.window._on_runs_clicked()

    def test_a_long_list_scrolls_rather_than_growing_the_popup(self):
        """Twelve rows is taller than the popup wants to be on a small
        screen, and a list simply cut off hides the oldest runs - which are
        the ones someone opened this to find."""
        for minute in range(10, 22):
            _make_run(Path(self.tmp.name), f"2026-08-24-12{minute}",
                      "https://example.com", finished=True)
        self.window.refresh_runs()
        self.assertGreater(
            self.window.runs_rows.sizeHint().height(),
            self.window.runs_scroll.maximumHeight())


if __name__ == "__main__":
    unittest.main()
