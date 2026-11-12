"""An engine that cannot decide must not outrank one that found something.

Both vendored engines report "I could not work this out" through the same
channel as a confirmed failure, and both were arriving at full weight.

* HTML_CodeSniffer's contrast check emits `.Abs` - "this element is
  absolutely positioned and the background color can not be determined" - as
  a *serious* violation. On ten pages of `https://www.gov.uk/`, 60 of 61
  `1_4_3` findings were that; on ten pages of a municipal WordPress site, 93 of 103.

* axe puts a result in `incomplete` precisely when it cannot decide, and the
  entry still carries the `impact` of a real failure. That made "Unable to
  determine if aria-controls referenced ID exists" a *critical*. Checked
  against the live page: all five `aria-controls` targets exist.

GOV.UK is the control that makes the size of this obvious. A pass reporting
605 serious accessibility failures across ten pages of the site whose focus
and contrast states are among the most tested on the web is describing
itself, not the site.
"""
from __future__ import annotations

import json
import unittest

from audit.base import EXACT, MINOR, NEEDS_BROWSER
from audit.browser import issues_from_axe, issues_from_htmlcs


def _htmlcs(code: str, kind: int = 1) -> list:
    payload = json.dumps({"messages": [
        {"type": kind, "code": code, "html": "<p>x</p>", "msg": "…", "tag": "p"}]})
    return issues_from_htmlcs(payload, "https://site/")


def _axe(bucket: str, impact: str = "critical") -> list:
    entry = {"id": "aria-valid-attr-value", "impact": impact,
             "help": "…", "description": "…",
             "nodes": [{"target": "button", "html": "<button></button>",
                        "failureSummary": "Unable to determine…"}]}
    payload = json.dumps({"violations": [], "incomplete": [], bucket: [entry]})
    return issues_from_axe(payload, "https://site/")


class HtmlCodeSnifferUncertainty(unittest.TestCase):
    ABS = "WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Abs"
    FAIL = "WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail"

    def test_an_undetermined_contrast_is_a_note(self):
        issue = _htmlcs(self.ABS)[0]
        self.assertEqual(issue.severity, MINOR)
        self.assertEqual(issue.confidence, NEEDS_BROWSER)
        self.assertTrue(issue.details["undetermined"])

    def test_a_caption_suggestion_is_a_prompt_not_a_defect(self):
        issue = _htmlcs("WCAG2AA.Principle1.Guideline1_3.1_3_1.H39.3.NoCaption", kind=2)[0]
        self.assertEqual(issue.severity, MINOR)
        self.assertTrue(issue.details["manual_check"])

    def test_a_real_contrast_failure_keeps_its_weight(self):
        """The fix must not quiet the finding the rule exists for."""
        issue = _htmlcs(self.FAIL)[0]
        self.assertNotEqual(issue.severity, MINOR)
        self.assertEqual(issue.confidence, EXACT)
        self.assertFalse(issue.details["undetermined"])

    def test_every_undetermined_marker_is_recognised(self):
        for marker in (".Abs", ".BgImage", ".Alpha", ".BgGradient"):
            with self.subTest(marker=marker):
                code = "WCAG2AA.Principle1.Guideline1_4.1_4_3.G18" + marker
                self.assertEqual(_htmlcs(code)[0].severity, MINOR)


class AxeUncertainty(unittest.TestCase):
    def test_an_incomplete_is_a_note_whatever_its_impact(self):
        issue = _axe("incomplete")[0]
        self.assertEqual(issue.severity, MINOR)
        self.assertEqual(issue.confidence, NEEDS_BROWSER)

    def test_a_violation_keeps_its_impact(self):
        issue = _axe("violations")[0]
        self.assertNotEqual(issue.severity, MINOR)
        self.assertEqual(issue.confidence, EXACT)

    def test_the_bucket_is_recorded_either_way(self):
        self.assertEqual(_axe("incomplete")[0].details["bucket"], "incomplete")
        self.assertEqual(_axe("violations")[0].details["bucket"], "violation")


if __name__ == "__main__":
    unittest.main()
