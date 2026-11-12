"""A target nothing was read from still produces the reports it was asked for.

The founding defect of this project, found again on a real path. `fullscan`
over a directory the scanner reads nothing in used to answer `None` from
`_audit_fullscan_target`, and `None` travels: `_write_markdown_briefing`
skips on it, `_styled_report_model` returns `None` on it, so both writers
returned without a word. The run printed `total_findings: 0`, exited 0, and
wrote neither `--report` nor `--styled-report`.

Two people are hurt by that. Whoever reads the output sees a clean bill of
health for a target nothing was opened in. Whatever runs next - an agent, a
CI step - opens `--report` and finds no file, after a success exit.

Found on `~/Desktop/XBrain Audit/contrast.html`, which is a directory of old run
folders rather than the page its name suggests. An over-broad `--exclude`, an
`--ext` that matches nothing, or one wrong path component all land here.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cli_impl.fullscan import _audit_fullscan_target


def _args():
    return SimpleNamespace(ext=None, exclude=None, no_default_excludes=False,
                           max_files=5000, no_ignore=False)


class AnUnreadableTargetStillHasAResult(unittest.TestCase):
    def test_an_empty_directory_is_a_result_not_a_none(self):
        with tempfile.TemporaryDirectory() as folder:
            result = _audit_fullscan_target(False, False, folder, _args(), None)
        self.assertIsNotNone(
            result,
            "None here silences both report writers without a word")
        self.assertEqual(result.mode, "repo")

    def test_it_reports_zero_rather_than_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            result = _audit_fullscan_target(False, False, folder, _args(), None)
        self.assertEqual(sum(result.counts().values()), 0)
        self.assertEqual(result.documents_with_issues(), [])

    def test_a_directory_with_a_readable_file_is_unaffected(self):
        """The fix must not change the case that already worked."""
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder, "a.html")
            page.write_text('<!DOCTYPE html><html><body><img src="x">'
                            '</body></html>', encoding="utf-8")
            result = _audit_fullscan_target(False, False, folder, _args(), None)
        self.assertTrue(result.documents_with_issues())


class TheReportWriterAcceptsIt(unittest.TestCase):
    """The half that was silently skipped, exercised directly."""

    def test_a_briefing_is_written_for_an_empty_result(self):
        from cli_impl.fullscan import _write_markdown_briefing

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder, "target")
            target.mkdir()
            report = Path(folder, "briefing.json")
            args = _args()
            args.report = str(report)
            result = _audit_fullscan_target(False, False, str(target), args, None)
            payload = _write_markdown_briefing(args, result, False, [], [], "en")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["summary"]["total"], 0)

    def test_the_file_lands_on_disk_and_parses(self):
        from cli_impl.fullscan import _write_markdown_briefing

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder, "target")
            target.mkdir()
            report = Path(folder, "briefing.json")
            args = _args()
            args.report = str(report)
            result = _audit_fullscan_target(False, False, str(target), args, None)
            _write_markdown_briefing(args, result, False, [], [], "en")

            self.assertTrue(report.exists(),
                            "--report was asked for and not written")
            written = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(written["summary"]["distinct_problems"], 0)


if __name__ == "__main__":
    unittest.main()
