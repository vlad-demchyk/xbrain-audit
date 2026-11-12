"""The file column of a repository scan, and what the summary says about it.

The preview column answered a narrower question than the one a repository
asks. It showed whichever file the selected finding happened to be in, so
there was no way to see that twenty-one findings sit in nine files out of
four hundred, and no way to reach a file without first finding a finding
that lives in it.

Two defects this file also pins down, both of them silent.

A repository scan never showed the run summary at all - not a decision, a
missing call - and had it been made it would have raised, because
`_summary_line` asked a `RepoAnalysisResult` for `pages`, which is the web
result's word for it.

And a repo result reaches this window by two paths. Only one of them was
doing this work, so a scan started one way had a file column and a summary
and a scan started the other way had neither.

Headless: Qt runs on the offscreen platform, like the other widget tests.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from models import (
        CodeBlock, Confidence, FileResult, RepoAnalysisResult, ScanDiagnostics,
        TextSpan,
    )
    from ui.main_window import MainWindow
    from ui.window_parts.repo_files import PATH_ROLE, _folder_of
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


def repo(findings: dict, *, clean_files=0, walk=None) -> "RepoAnalysisResult":
    """`findings` maps a path to how many flagged blocks it holds."""
    files, spans, index = [], [], 0
    for path, count in findings.items():
        blocks = []
        for _ in range(count):
            index += 1
            block = CodeBlock(block_id=f"b{index}", file_path=path, text="x",
                              start=0, end=1, line_number=1)
            blocks.append(block)
            spans.append(TextSpan(block_id=block.block_id, start=0, end=1,
                                  score=0.9, confidence=Confidence.HIGH,
                                  detector_name="test"))
        files.append(FileResult(path=path, blocks=blocks,
                                raw_text="one\ntwo\nthree\n"))
    files += [FileResult(path=f"quiet/f{i}.py", raw_text="")
              for i in range(clean_files)]
    return RepoAnalysisResult(root_dir="/tmp/repo", files=files, spans=spans,
                              diagnostics=walk or ScanDiagnostics())


@unittest.skipIf(QApplication is None, "PySide6 not available")
class Folders(unittest.TestCase):
    def test_a_file_in_a_folder(self):
        self.assertEqual(_folder_of("src/components/Hero.tsx"), "src/components/")

    def test_a_file_at_the_root(self):
        self.assertEqual(_folder_of("README.md"), "")

    def test_a_windows_path_groups_the_same_way(self):
        self.assertEqual(_folder_of("src\\components\\Hero.tsx"), "src/components/")


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheFileColumn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def tree(self):
        return self.window.repo_files.tree

    def folders(self) -> list:
        tree = self.tree()
        return [tree.topLevelItem(i).text(0)
                for i in range(tree.topLevelItemCount())]

    def rows(self) -> dict:
        """path -> the count shown beside it."""
        tree, out = self.tree(), {}
        for i in range(tree.topLevelItemCount()):
            folder = tree.topLevelItem(i)
            for j in range(folder.childCount()):
                child = folder.child(j)
                out[child.data(0, PATH_ROLE)] = child.text(1)
        return out

    def test_files_are_grouped_by_folder(self):
        self.window._on_repo_finished(repo({
            "src/components/Hero.tsx": 6, "src/components/Footer.tsx": 1,
            "src/locales/uk.json": 5}))
        self.assertEqual(self.folders(), ["src/components/", "src/locales/"])

    def test_each_file_carries_its_count(self):
        self.window._on_repo_finished(repo({"src/Hero.tsx": 6, "src/Foot.tsx": 1}))
        self.assertEqual(self.rows(), {"src/Hero.tsx": "6", "src/Foot.tsx": "1"})

    def test_a_row_carries_its_path_rather_than_a_parsed_label(self):
        self.window._on_repo_finished(repo({"src/a/Hero.tsx": 1}))
        self.assertIn("src/a/Hero.tsx", self.rows())

    def test_quiet_files_are_counted_not_listed(self):
        """Four hundred rows with a zero beside them is a directory listing,
        and the one number that matters is easier to read as a number."""
        self.window._on_repo_finished(repo({"src/Hero.tsx": 2}, clean_files=311))
        self.assertEqual(len(self.rows()), 1)
        self.assertIn("311", self.window.repo_files.footer.text())

    def test_a_scan_with_nothing_clean_says_nothing_about_it(self):
        self.window._on_repo_finished(repo({"src/Hero.tsx": 2}))
        self.assertTrue(self.window.repo_files.footer.isHidden())

    def test_the_column_counts_what_the_list_shows(self):
        """Low confidence is a finding to `spans` and not to the list, so
        counting spans here would put a number on screen that the list
        beside it does not match."""
        result = repo({"src/Hero.tsx": 1})
        result.spans.append(TextSpan(block_id=result.files[0].blocks[0].block_id,
                                     start=0, end=1, score=0.1,
                                     confidence=Confidence.LOW,
                                     detector_name="test"))
        self.window._on_repo_finished(result)
        self.assertEqual(self.rows(), {"src/Hero.tsx": "1"})

    def test_a_file_name_is_trimmed_from_the_right(self):
        """The rows people click carry a bare file name, and a name is
        recognised by its head: `ElideLeft` turned `index.html` into
        `...ex.html`."""
        from PySide6.QtCore import Qt
        self.assertEqual(self.tree().textElideMode(),
                         Qt.TextElideMode.ElideRight)

    def test_nothing_trimmed_is_lost(self):
        self.window._on_repo_finished(repo({"src/components/Hero.tsx": 1}))
        tree = self.tree()
        folder = tree.topLevelItem(0)
        self.assertEqual(folder.toolTip(0), "src/components/")
        self.assertEqual(folder.child(0).toolTip(0), "src/components/Hero.tsx")

    def test_choosing_a_file_opens_it_under_the_list(self):
        self.window._on_repo_finished(repo({"src/Hero.tsx": 1}))
        tree = self.tree()
        tree.setCurrentItem(tree.topLevelItem(0).child(0))
        self.assertIn("two", self.window.code_view.toPlainText())

    def test_a_second_scan_replaces_the_first_one_s_files(self):
        self.window._on_repo_finished(repo({"src/Old.tsx": 1}))
        self.window._on_repo_finished(repo({"src/New.tsx": 1}))
        self.assertEqual(list(self.rows()), ["src/New.tsx"])

    def test_a_web_result_leaves_the_column_alone(self):
        """`refresh_repo_files` is called from the repo path only, but the
        guard is what keeps a shared handler from clearing it."""
        self.window._on_repo_finished(repo({"src/Hero.tsx": 1}))
        from models import AnalysisResult
        self.window.result = AnalysisResult(root_url="https://example.com")
        self.window.refresh_repo_files()
        self.assertEqual(list(self.rows()), ["src/Hero.tsx"])


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheSummaryOfARepositoryScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def test_it_appears_at_all(self):
        """It never did. The call was missing, not withheld."""
        self.window._on_repo_finished(repo({"src/Hero.tsx": 2}))
        self.assertFalse(self.window.summary_bar.isHidden())

    def test_it_does_not_ask_a_repository_for_pages(self):
        """`_summary_line` used the web result's word, so this raised."""
        self.window._on_repo_finished(repo({"src/Hero.tsx": 2}))
        self.assertTrue(self.window.summary_label.text())

    def test_it_says_how_many_files_were_read(self):
        self.window._on_repo_finished(repo(
            {"src/Hero.tsx": 2}, walk=ScanDiagnostics(files_read=412)))
        self.assertIn("412", self.window.summary_label.text())

    def test_it_says_how_many_were_skipped_on_purpose(self):
        """A walk that read 412 and skipped 38 by `.xaudit-ignore` is a
        different result from one that read 450, and "no findings" means
        something different in each."""
        self.window._on_repo_finished(repo(
            {"src/Hero.tsx": 2},
            walk=ScanDiagnostics(files_read=412, skipped_ignored=38)))
        self.assertIn("38", self.window.summary_label.text())

    def test_a_walk_that_skipped_nothing_does_not_say_so(self):
        self.window._on_repo_finished(repo(
            {"src/Hero.tsx": 2}, walk=ScanDiagnostics(files_read=412)))
        self.assertNotIn("ignore", self.window.summary_label.text())

    def test_it_says_which_files_the_findings_are_in(self):
        self.window._on_repo_finished(repo({"a.py": 6, "b.py": 4, "c.py": 1}))
        self.assertIn("3", self.window.summary_label.text())

    def test_the_column_and_the_strip_count_against_the_same_total(self):
        """Two denominators on one screen is the window contradicting
        itself."""
        self.window._on_repo_finished(repo(
            {"a.py": 1}, clean_files=5, walk=ScanDiagnostics(files_read=412)))
        self.assertIn("411", self.window.repo_files.footer.text())
        self.assertIn("412", self.window.summary_label.text())

    def test_a_walk_that_recorded_nothing_still_counts_its_files(self):
        """A result assembled by something that did not fill in diagnostics
        would otherwise report zero files read beside its own findings."""
        self.window._on_repo_finished(repo({"a.py": 1}, clean_files=5))
        self.assertIn("6", self.window.summary_label.text())


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheColumnNamesTheRightSource(unittest.TestCase):
    """It said "Page preview" over a repository's files."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def head(self) -> str:
        return self.window.col1_header.text()

    def test_a_site_is_a_page_preview(self):
        from analysis_modes import SOURCE_SITE
        from i18n.translations import t
        self.window.source = SOURCE_SITE
        self.window._apply_mode_visibility()
        self.assertEqual(self.head(), t("site_preview_header", self.window.lang))

    def test_a_repository_is_its_files(self):
        from analysis_modes import SOURCE_REPO
        from i18n.translations import t
        self.window.source = SOURCE_REPO
        self.window._apply_mode_visibility()
        self.assertEqual(self.head(), t("repo_preview_header", self.window.lang))

    def test_it_follows_the_interface_language(self):
        """One head is set from a different place than the rest, which is
        how it came to be the one left in the old language."""
        from analysis_modes import SOURCE_REPO
        from i18n.translations import t
        self.window.source = SOURCE_REPO
        for lang in ("uk", "it", "en"):
            with self.subTest(lang=lang):
                self.window.lang = lang
                self.window._retranslate_ui()
                self.assertEqual(self.head(), t("repo_preview_header", lang))

    def test_a_repository_is_measured_in_files_not_pages(self):
        """A scan of four hundred files reported "318 pages"."""
        from i18n.translations import t

        result = repo({"a.py": 1}, clean_files=2)
        self.window._on_repo_finished(result)
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            t("status_done_repo", self.window.lang, pages=len(result.files),
              blocks=len(result.blocks()), flags=1))


if __name__ == "__main__":
    unittest.main()
