"""The category counts in the `fullscan` summary must count something.

`"best_practices"` was written out by hand next to a constant spelled
`"best-practices"`, so that row read 0 on every scan ever run and no test
noticed - a summary number is exactly the kind of value nothing asserts on.
These tests assert on it against the real category constants.
"""
from __future__ import annotations

import unittest

from audit.base import (
    ACCESSIBILITY, ADVISORY, BEST_PRACTICES, CATEGORIES, EXACT, GEO, Issue,
    NEEDS_BROWSER, PERFORMANCE, SECURITY, SEO,
)
from cli_impl.fullscan import _build_combined, _count, _issues_at_floor


def _issue(category: str) -> Issue:
    return Issue(rule_id="r", severity="minor", category=category,
                 source="https://example.test/", details={})


class Args:
    pass


class EveryCategoryRowCounts(unittest.TestCase):
    def test_no_category_name_is_retyped_with_the_wrong_separator(self):
        # The defect in one line: a hyphenated constant compared against an
        # underscored literal.
        self.assertEqual(BEST_PRACTICES, "best-practices")
        self.assertNotIn("best_practices", CATEGORIES)

    def test_the_summary_counts_each_category_it_names(self):
        issues = [_issue(ACCESSIBILITY), _issue(SEO), _issue(SEO),
                  _issue(GEO), _issue(PERFORMANCE), _issue(BEST_PRACTICES),
                  _issue(BEST_PRACTICES), _issue(BEST_PRACTICES)]
        summary = _build_combined(Args(), "https://example.test/", True, "en",
                                  None, [], issues)["summary"]
        self.assertEqual(summary["accessibility"], 1)
        self.assertEqual(summary["seo"], 2)
        self.assertEqual(summary["geo"], 1)
        self.assertEqual(summary["performance"], 1)
        self.assertEqual(summary["best_practices"], 3)

    def test_a_category_with_no_findings_reads_zero_not_missing(self):
        summary = _build_combined(Args(), "https://example.test/", True, "en",
                                  None, [], [_issue(SECURITY)])["summary"]
        self.assertEqual(summary["best_practices"], 0)

    def test_count_takes_the_constant_not_a_copy_of_it(self):
        self.assertEqual(_count([_issue(BEST_PRACTICES)], BEST_PRACTICES), 1)
        self.assertEqual(_count([_issue(BEST_PRACTICES)], "best_practices"), 0)


class TheConfidenceFloorReachesTheJson(unittest.TestCase):
    """`--confidence` must answer the same in the JSON as in the report.

    The filter ran after the documents had been flattened into the list the
    JSON and the summary are built from, so on `https://www.python.org/`
    `--confidence exact` left 1030 findings and 46 GEO rows in the JSON
    while the HTML showed 918 and none.
    """

    def _result(self):
        from audit.engine import AccessibilityResult, DocumentReport
        issues = [
            Issue(rule_id="a", severity="serious", category=ACCESSIBILITY,
                  confidence=EXACT, source="https://example.test/", details={}),
            Issue(rule_id="geo-article-schema", severity="minor", category=GEO,
                  confidence=ADVISORY, source="https://example.test/", details={}),
            Issue(rule_id="c", severity="minor", category=SEO,
                  confidence=NEEDS_BROWSER, source="https://example.test/",
                  details={}),
        ]
        return AccessibilityResult(root="https://example.test/", documents=[
            DocumentReport(source="https://example.test/", issues=issues)])

    def test_exact_drops_the_advisory_rows_from_the_flattened_list(self):
        kept = _issues_at_floor(self._result(), EXACT)
        self.assertEqual([issue.rule_id for issue in kept], ["a"])

    def test_a_low_floor_does_not_implicitly_enable_recommendations(self):
        kept = _issues_at_floor(self._result(), ADVISORY)
        self.assertEqual(sorted(i.rule_id for i in kept),
                         ["a"])

    def test_no_floor_keeps_everything_that_is_decided(self):
        self.assertEqual(len(_issues_at_floor(self._result(), None)), 1)

    def test_asking_for_the_undecided_brings_them_back(self):
        kept = _issues_at_floor(self._result(), None, unsettled=True)
        self.assertEqual(len(kept), 3)

    def test_the_summary_counts_what_survived_the_floor(self):
        kept = _issues_at_floor(self._result(), EXACT)
        summary = _build_combined(Args(), "https://example.test/", True, "en",
                                  None, [], kept)["summary"]
        self.assertEqual(summary["geo"], 0)
        self.assertEqual(summary["accessibility"], 1)

    def test_a_missing_result_is_not_an_error(self):
        self.assertEqual(_issues_at_floor(None, EXACT), [])


if __name__ == "__main__":
    unittest.main()
