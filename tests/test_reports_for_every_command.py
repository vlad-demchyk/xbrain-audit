"""Every command that finds something can write a document about it.

`fullscan` has kept a dated folder per run since it existed, with a briefing,
a styled report, timings and a comparison in it. `scan` and `audit` - the two
commands a person is most likely to run first - wrote wherever they were told
and nowhere otherwise, and `scan` had no briefing at all: `--styled-report`
for a person, `--json` for a pipeline, and nothing for the agent in between.

Two rules, and they are the ones `fullscan` already follows:

* a named `--report` or `--styled-report` goes exactly where it was asked;
* everything else lands in a dated folder for that target.

With one exception, which is why `prepare_for` takes the flags: `--json` and
`--check` mean the output is being parsed, and a pipeline step must not start
leaving folders on somebody's Desktop.

Every document also opens with what the run *was* - the command and the
parameters that changed what it measured. Two reports on one site differ by a
factor of three depending on whether the browser ran, and neither of them
used to say which one it was.
"""
import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli_impl import runfolder
from cli_impl.runheader import as_line, describe


def _args(**kwargs):
    base = dict(json=False, check=False, report=None, styled_report=None,
                detector="offline", scope="content", language=None,
                paths=["/repo"], no_browser=False)
    base.update(kwargs)
    return argparse.Namespace(**base)


class WhereTheDocumentsGo(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patch = mock.patch.dict("os.environ",
                                {"XAUDIT_REPORT_ROOT": self._tmp.name})
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_plain_run_gets_a_folder_and_both_documents(self):
        args = _args()
        folder = runfolder.prepare_for("/repo/shop", args)
        self.assertIsNotNone(folder)
        self.assertEqual(args.report, str(folder.report))
        self.assertEqual(args.styled_report, str(folder.styled_report))
        self.assertTrue(folder.run.exists())

    def test_a_named_path_is_left_exactly_where_it_was_asked(self):
        args = _args(report="/somewhere/briefing.md")
        folder = runfolder.prepare_for("/repo/shop", args)
        self.assertEqual(args.report, "/somewhere/briefing.md")
        # The other document still gets a home, and the folder still exists
        # to hold it.
        self.assertEqual(args.styled_report, str(folder.styled_report))

    def test_a_pipeline_run_leaves_nothing_behind(self):
        for flag in ("json", "check"):
            with self.subTest(flag=flag):
                args = _args(**{flag: True})
                self.assertIsNone(runfolder.prepare_for("/repo/shop", args))
                self.assertIsNone(args.report)
                self.assertIsNone(args.styled_report)


class WhatTheDocumentSaysAboutItsRun(unittest.TestCase):

    def test_the_command_and_target_are_always_there(self):
        rows = dict(describe("audit", "https://x.test/", _args()))
        self.assertEqual(rows["command"], "audit")
        self.assertEqual(rows["target"], "https://x.test/")

    def test_the_parameters_that_changed_the_measurement_are_named(self):
        args = _args(detector="hybrid", scope="both", depth=4, max_pages=250,
                     breakpoints="all", site_controls=True, unsettled=True,
                     confidence="exact")
        rows = dict(describe("fullscan", "https://x.test/", args,
                             language="it"))
        self.assertEqual(rows["detector"], "hybrid")
        self.assertEqual(rows["scope"], "both")
        self.assertEqual(rows["depth"], "4")
        self.assertEqual(rows["max pages"], "250")
        self.assertEqual(rows["breakpoints"], "all")
        self.assertEqual(rows["confidence"], "exact")
        self.assertEqual(rows["site controls"], "yes")
        self.assertEqual(rows["report language"], "it")

    def test_the_browser_is_named_because_it_is_the_biggest_difference(self):
        on = dict(describe("fullscan", "https://x.test/", _args()))
        off = dict(describe("fullscan", "https://x.test/",
                            _args(no_browser=True)))
        self.assertEqual(on["browser"], "on")
        self.assertIn("off", off["browser"])

    def test_a_scan_is_not_told_it_ran_a_browser(self):
        """`scan` has no browser to run, and claiming one either way would be
        a statement about a pass that never happened."""
        rows = dict(describe("scan", "/repo", _args()))
        self.assertNotIn("browser", rows)

    def test_where_the_file_went_is_not_part_of_what_was_measured(self):
        rows = dict(describe("scan", "/repo",
                             _args(report="/tmp/a.md",
                                   styled_report="/tmp/a.pdf")))
        self.assertNotIn("report", rows)
        self.assertNotIn("styled_report", rows)

    def test_the_one_line_form_carries_the_same_facts(self):
        args = _args(depth=2)
        line = as_line(describe("fullscan", "https://x.test/", args))
        self.assertIn("command fullscan", line)
        self.assertIn("depth 2", line)


class TheTextScanHasABriefing(unittest.TestCase):

    def _briefing(self, findings, files=()):
        from cli_impl.reports import write_text_briefing

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            write_text_briefing(list(files), findings,
                                _args(paths=["/repo"]), path)
            return path.read_text(encoding="utf-8")

    def test_it_names_the_run_and_the_findings(self):
        text = self._briefing([
            {"file": "/repo/a.py", "line": 3, "source": "characters",
             "confidence": "medium", "score": 0.5,
             "explanation": "[typography] U+2013 EN DASH -> '-'"},
        ])
        self.assertIn("# Scan of /repo", text)
        self.assertIn("## This run", text)
        self.assertIn("**command:** scan", text)
        self.assertIn("| characters | 1 |", text)
        self.assertIn("/repo/a.py:3", text)

    def test_nothing_found_is_said_as_a_result_not_an_empty_table(self):
        text = self._briefing([])
        self.assertIn("Nothing.", text)
        self.assertNotIn("| kind | count |", text)


if __name__ == "__main__":
    unittest.main()
