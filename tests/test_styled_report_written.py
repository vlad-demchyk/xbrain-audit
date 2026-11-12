"""`fullscan` writes the styled report it says it writes.

Measured 2026-09-02: it did not. `_styled_report_model` read `args` - a name
it never received - and every writer call is wrapped in `try/except` so the
run kept going and printed one line about it:

    # warning: styled report failed: name 'args' is not defined

So every `fullscan` since `2460da7` (2026-09-01) produced no PDF and no HTML,
on every target, and the suite stayed green through twelve commits: nothing
asserted that the file exists, only that the writer was called.

That is what this file asserts, and it asserts it the only way that could
have caught it - by running the real command and looking on disk. The report
folder is a temporary directory, not the Desktop default, so the test does
not write into wherever the person running it keeps their reports.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "simulations" / "mixed-problems"

#: A `.pdf` styled report is printed by QtWebEngine, so this half of the file
#: needs a browser engine and not merely Qt. Without one the run still writes
#: a one-page notice and says so - correct behaviour, and not what this test
#: is about. Measured 2026-09-02 on CI, where PySide6 installs and
#: `libEGL.so.1` does not.
try:
    from audit.driver import available

    # The codebase's own answer to "is there a browser engine", rather than
    # a second probe that could disagree with it. Importing `report.pdf` is
    # not that answer: every `PySide6` import in it is inside a function, so
    # the module imports cleanly on a machine that cannot print at all.
    _CAN_PRINT = bool(available()[0])
except Exception:  # noqa: BLE001 - no engine here is a skip, not a failure
    _CAN_PRINT = False


def _fullscan(*extra):
    return subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), "fullscan", str(TARGET),
         "--no-browser", "--no-update-check", *extra],
        capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=str(ROOT))


class StyledReportIsWritten(unittest.TestCase):

    @unittest.skipIf(not _CAN_PRINT, "no browser engine to print a PDF")
    def test_the_named_styled_report_exists_afterwards(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "report.pdf"
            done = _fullscan("--styled-report", str(pdf),
                             "--report", str(Path(tmp) / "report.md"))
            self.assertIn(done.returncode, (0, 1), done.stderr[-800:])
            self.assertNotIn("styled report failed", done.stderr)
            # Written, and not an empty file: an exception inside the export
            # leaves a zero-byte PDF behind, which opens as a corrupt
            # document rather than as an error.
            self.assertTrue(pdf.exists(),
                            f"no styled report: {done.stderr[-800:]}")
            self.assertGreater(pdf.stat().st_size, 1000)

    def test_the_run_header_names_the_command_that_produced_it(self):
        """The header is what `args` was needed for in the first place.

        A styled report that exists but cannot say which flags produced it is
        the same defect one step later: the reader cannot tell a `--no-browser`
        run from a full one, and the two answer different questions.
        """
        from cli_impl.fullscan import _styled_report_model

        class _Args:
            command = "fullscan"
            styled_report = "x.pdf"
            report = None
            no_browser = True
            depth = 0

        from audit import engine

        page = TARGET / "mixed-issues.html"
        result = engine.analyze_page_file(str(page))
        model = _styled_report_model(_Args(), result, [], "en")
        self.assertIsNotNone(model)
        self.assertTrue(model.meta.run,
                        "the styled report cannot say what produced it")


if __name__ == "__main__":
    unittest.main()
