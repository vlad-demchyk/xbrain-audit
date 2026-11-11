"""Bringing a target instead of typing one (artboard 3o).

A page saved as one file is the one target somebody has in their hand rather
than in their head, so the window takes it as a drop. The tests here cover
what a drop is allowed to be, what it does to the run, and the two things
the screen has to notice afterwards - the file's own name and size, and the
fields moving to the source that was just chosen.
"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtWidgets import QApplication
    from analysis_modes import SOURCE_FILE, SOURCE_REPO, SOURCE_SITE
    from ui.main_window import MainWindow
    from ui.window_parts.setup_screen import _human_size, _under_home
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


def _drop(*paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return mime


@unittest.skipIf(QApplication is None, "PySide6 not available")
class WhatMayBeDropped(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.window = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()

    def test_a_saved_page_is_the_single_file_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = os.path.join(tmp, "pricing.html")
            Path(page).write_text("<html></html>", encoding="utf-8")
            self.assertEqual(self.window._dropped_target(_drop(page)),
                             (SOURCE_FILE, page))

    def test_a_folder_is_the_repository_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.window._dropped_target(_drop(tmp)),
                             (SOURCE_REPO, tmp))

    def test_anything_else_is_refused(self):
        """Accepted-and-ignored is indistinguishable from broken."""
        with tempfile.TemporaryDirectory() as tmp:
            image = os.path.join(tmp, "shot.png")
            Path(image).write_bytes(b"x")
            self.assertIsNone(self.window._dropped_target(_drop(image)))

    def test_a_url_from_a_browser_is_not_a_target(self):
        mime = QMimeData()
        mime.setUrls([QUrl("https://example.com/page.html")])
        self.assertIsNone(self.window._dropped_target(mime))


@unittest.skipIf(QApplication is None, "PySide6 not available")
class AfterADrop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_the_fields_follow_the_source_immediately(self):
        """The defect this found: `_apply_mode_visibility` read the legacy
        `self.source` copy, and was connected *before* the signal that
        refreshes it - so choosing a source painted the window one source
        behind until something else happened to repaint it."""
        window = MainWindow()
        window.app_state.set_source(SOURCE_FILE)
        self.app.processEvents()
        self.assertEqual(window.source_controls_stack.currentIndex(), 2)
        window.app_state.set_source(SOURCE_REPO)
        self.app.processEvents()
        self.assertEqual(window.source_controls_stack.currentIndex(), 1)
        window.app_state.set_source(SOURCE_SITE)
        self.app.processEvents()
        self.assertEqual(window.source_controls_stack.currentIndex(), 0)
        window.close()
        window.deleteLater()

    def test_the_drop_zone_shows_the_file_that_was_chosen(self):
        window = MainWindow()
        window.show_setup(True)
        with tempfile.TemporaryDirectory() as tmp:
            page = os.path.join(tmp, "pricing.html")
            Path(page).write_text("<html>" + "x" * 3000 + "</html>",
                                  encoding="utf-8")
            window.app_state.set_source(SOURCE_FILE)
            window.file_path_edit.setText(page)
            self.app.processEvents()
            self.assertTrue(window.setup_screen.drop_chosen.isVisibleTo(
                window.setup_screen))
            self.assertIn("pricing.html",
                          window.setup_screen.drop_chosen.text())
            self.assertIn("KB", window.setup_screen.drop_chosen.text())
        window.close()
        window.deleteLater()

    def test_the_zone_is_only_there_for_a_single_page(self):
        window = MainWindow()
        window.show_setup(True)
        window.app_state.set_source(SOURCE_REPO)
        self.app.processEvents()
        self.assertFalse(window.setup_screen.drop_zone.isVisibleTo(
            window.setup_screen))
        window.close()
        window.deleteLater()


@unittest.skipIf(QApplication is None, "PySide6 not available")
class Formatting(unittest.TestCase):
    def test_sizes_are_said_the_way_people_say_them(self):
        self.assertEqual(_human_size(512), "512 B")
        self.assertEqual(_human_size(400 * 1024), "400 KB")
        self.assertEqual(_human_size(3 * 1024 * 1024), "3.0 MB")

    def test_a_path_under_home_is_written_from_home(self):
        inside = Path.home() / "Downloads" / "page.html"
        self.assertEqual(_under_home(inside), "~/Downloads/page.html")
        # Outside home the path is shown as the OS writes it.
        self.assertEqual(_under_home(Path("/etc/hosts")), str(Path("/etc/hosts")))



@unittest.skipIf(QApplication is None, "PySide6 not available")
class WidthSpecificFindings(unittest.TestCase):
    """A finding seen at one width out of three says so (artboard 3o).

    The mobile menu's unnamed button does not exist in the desktop DOM at
    all, so "only at 390" is a different fact from "everywhere", and
    `audit.responsive.merge` already records which widths saw it. Until now
    nothing in the window read that.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.window = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()

    def _issue(self, breakpoints):
        from audit.base import Issue

        return Issue(rule_id="button-name", severity="serious",
                     selector="button.menu", snippet="<button class='menu'>",
                     fix_snippet='<button class="menu" aria-label="Menu">',
                     engine="axe", source="https://example.com",
                     details={"breakpoints": list(breakpoints)})

    def _chip_texts(self, issue):
        from PySide6.QtWidgets import QLabel

        widget = self.window._build_audit_detail_widget(issue)
        return [label.text() for label in widget.findChildren(QLabel)]

    def test_one_width_out_of_three_is_named(self):
        texts = self._chip_texts(self._issue(["mobile"]))
        self.assertTrue(any("390" in text for text in texts), texts)

    def test_a_finding_at_every_width_says_nothing_about_width(self):
        texts = self._chip_texts(self._issue(["desktop", "tablet", "mobile"]))
        self.assertFalse(any("390" in text for text in texts), texts)

    def test_a_static_finding_has_no_width_chip(self):
        from audit.base import Issue

        texts = self._chip_texts(Issue(rule_id="html-lang", severity="serious",
                                       source="/tmp/page.html", engine="static"))
        self.assertFalse(any("390" in text for text in texts), texts)


if __name__ == "__main__":
    unittest.main()
