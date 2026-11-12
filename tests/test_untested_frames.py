"""A frame axe could not enter is a gap in coverage, not a defect.

`axe:frame-tested` says axe could not inject into an iframe (a cross-origin
one). On a live intranet audit it was counted among the findings, four times,
as if the page had a problem. It is reported where coverage is: per page,
with the frame's origin. Synthetic markup.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from audit import browser
from audit.base import Issue
from audit.coverage import coverage_summary

SOURCE = "https://contoso.sharepoint.com/sites/ExampleSite/p.aspx"


def _frame():
    return Issue(rule_id="axe:frame-tested", severity="minor", engine="axe",
                 source=SOURCE, selector=["iframe"],
                 snippet='<iframe src="https://forms.example.org/f?id=1">')


def _result():
    return SimpleNamespace(documents=[], browser_errors=[], coverage={},
                           browser_coverage=[])


class FramesAreCoverage(unittest.TestCase):

    def test_the_finding_leaves_the_counts_and_lands_in_coverage(self):
        document = SimpleNamespace(source=SOURCE, error="", issues=[])
        result = _result()
        result.documents = [document]
        audit = SimpleNamespace(error="", engine_errors={}, measurements={},
                                html="", issues=[_frame(), Issue(
                                    rule_id="axe:list", severity="serious",
                                    engine="axe", source=SOURCE, selector="ul",
                                    snippet="<ul>")])
        browser.merge_page_audit(result, document, audit)
        self.assertEqual([i.rule_id for i in document.issues], ["axe:list"])
        self.assertEqual(result.coverage["untested_frames"], [{
            "source": SOURCE,
            "frames": [{"origin": "https://forms.example.org", "selector": "iframe"}],
            "origins": ["https://forms.example.org"]}])
        self.assertEqual(result.browser_coverage[-1]["status"], "unknown")
        self.assertIn("https://forms.example.org", result.browser_coverage[-1]["reason"])

    def test_the_report_says_which_origins_were_not_tested(self):
        coverage = {"untested_frames": [{"source": SOURCE, "frames": [],
                                         "origins": ["https://forms.example.org"]}]}
        for lang in ("en", "uk", "it"):
            with self.subTest(lang=lang):
                _title, text = coverage_summary(coverage, lang)
                self.assertIn("https://forms.example.org", text)

    def test_sharepoint_zoning_does_not_count_it_as_skipped(self):
        from audit import sharepoint_zones

        summary = sharepoint_zones.Summary()
        kept = sharepoint_zones.classify_browser_issues(
            [_frame()], "<html><body><div id='SuiteNavWrapper'><iframe src='https://forms.example.org/f'></iframe></div></body></html>",
            summary=summary)
        self.assertEqual([i.rule_id for i in kept], ["axe:frame-tested"])
        self.assertEqual(summary.skipped_findings, 0)


if __name__ == "__main__":
    unittest.main()
