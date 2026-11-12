"""Three defects that only a run of the built application could show.

None of them fails a unit test, and all three were found by building the
bundles and using them:

1. **The browser pass was invisible in the window.** Its findings are merged
   into the documents after the list on screen was built, and nothing
   repainted. Measured on one page: 12 rows against 31 findings - axe,
   HTML_CodeSniffer, the state pass and every load measurement present in
   the result and none of them displayed. The CLI never had it because it
   prints after the merge.

2. **The report language of an Italian site came out English.** Every block
   voted, and a navigation label is one or two words: on a site whose prose
   is 9:2 Italian the vote was 23 `en` to 19 `it`. The advice that names a
   better detector for Italian is chosen by that answer, so it never
   reached an Italian reader either.

3. **`--version` opened the window.** The Makefile tells whoever builds the
   bundle to verify it with `XBrain Audit.app/Contents/MacOS/XBrain Audit
   --version`; that sat there with a window open instead of printing, on the
   surface where a stale binary is hardest to notice.

The fourth, `multiprocessing.freeze_support()`, is not here: it is only
observable in a frozen binary, where a child process re-executes the
bundle's own argv. `tests/test_bundle_entry.py` covers what can be covered
from source - that the call exists and runs before anything else.
"""
from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cli_impl.fullscan import _detect_report_language

try:
    from PySide6.QtWidgets import QApplication

    from ui.main_window import MainWindow
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


class Block:
    def __init__(self, text: str, language_hint: str):
        self.text = text
        self.language_hint = language_hint


class Page:
    def __init__(self, blocks):
        self.blocks = blocks


ITALIAN_PROSE = (
    "Nel cuore della citta fortezza, la piazza esagonale conserva l'impianto "
    "veneziano che ne ha fatto un patrimonio riconosciuto in tutto il mondo"
)
ENGLISH_LABEL = "Search"


class TheReportLanguageIsDecidedByProse(unittest.TestCase):

    def test_short_labels_do_not_outvote_the_text(self):
        """The shape of the real page: many menu items in one language, the
        actual writing in another."""
        page = Page([Block(ENGLISH_LABEL, "en") for _ in range(23)]
                    + [Block(ITALIAN_PROSE, "it") for _ in range(9)])
        self.assertEqual(_detect_report_language(None, [page]), "it")

    def test_an_explicit_language_still_wins(self):
        page = Page([Block(ITALIAN_PROSE, "it")])
        self.assertEqual(_detect_report_language("en", [page]), "en")

    def test_a_page_of_only_labels_still_has_a_language(self):
        """Falling back to English there would be the same defect pointing
        the other way."""
        page = Page([Block("Cerca", "it"), Block("Accedi", "it")])
        self.assertEqual(_detect_report_language(None, [page]), "it")

    def test_no_hints_at_all_is_english(self):
        self.assertEqual(_detect_report_language(None, [Page([])]), "en")


class TheFrozenEntryPointSurvivesAChildProcess(unittest.TestCase):
    """A frozen binary re-executes itself to spawn one, so the child is
    handed our argv and answers `invalid choice: 'from
    multiprocessing.resource_tracker import main;main(9)'`."""

    def test_freeze_support_is_called_before_anything_else(self):
        import app_entry

        source = inspect.getsource(app_entry.run)
        self.assertIn("multiprocessing.freeze_support()", source)
        self.assertLess(source.index("freeze_support"),
                        source.index("_warn_if_stale"))


class TheVersionFlagPrintsAndExits(unittest.TestCase):
    def test_main_answers_version_without_building_a_window(self):
        # Parsed from the file rather than imported: `import main` builds
        # nothing, but it does `from PySide6.QtWidgets import QApplication`
        # at the top, so on a machine with no working Qt this assertion -
        # which is entirely about text - failed with an `ImportError`. That
        # is the opposite of what it checks. Scoped to `main()` because the
        # order it asserts is only meaningful inside that function: the file
        # imports `QApplication` at line 21, long before any argument.
        import ast

        text = (Path(__file__).resolve().parent.parent
                / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "main")
        source = ast.get_source_segment(text, fn)
        self.assertIn('"--version" in sys.argv', source)
        self.assertLess(source.index("--version"), source.index("QApplication"))


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheBrowserPassRepaints(unittest.TestCase):

    def test_the_window_redraws_after_merging(self):
        """The merge happens after the list was built. Without a repaint the
        window shows the static pass and calls it the audit."""
        source = inspect.getsource(MainWindow._run_browser_pass)
        merge = source.index("merge_page_audit")
        for call in ("_populate_audit_list()", "_refresh_summary()"):
            with self.subTest(call=call):
                self.assertIn(call, source)
                self.assertGreater(source.index(call), merge)


if __name__ == "__main__":
    unittest.main()
