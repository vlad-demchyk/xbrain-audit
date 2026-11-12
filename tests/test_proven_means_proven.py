"""Only what was established counts as proven, and one element's problem is one finding.

From a live check of a final SharePoint report:
* HTML_CodeSniffer warnings (H42 "should this be a heading?", G141, F24) were
  counted as defects - a warning is the engine's question to a person;
* a keyboard-trap candidate the runner had not tried with real keys stayed a
  proven trap (eight of them; real Tab left each one at the first press);
* the same field, text or button found by two engines in two zone documents
  stayed two findings.
"""
from __future__ import annotations

import json
import unittest

from audit.base import EXACT, NEEDS_BROWSER, Issue
from audit.engine import DocumentReport


class HtmlcsWarningsAreQuestions(unittest.TestCase):
    def _issues(self, kind):
        from audit.browser import issues_from_htmlcs

        payload = json.dumps({"messages": [{
            "type": kind, "code": "WCAG2AA.Principle1.Guideline1_3.1_3_1.H42",
            "msg": "Heading markup should be used if this content is intended as a heading.",
            "html": "<p><strong>Title</strong></p>", "tag": "p"}]})
        return issues_from_htmlcs(payload, "https://contoso.sharepoint.com/")

    def test_a_warning_goes_to_the_to_check_list(self):
        issue = self._issues(2)[0]
        self.assertEqual(issue.confidence, NEEDS_BROWSER)
        self.assertEqual(issue.details["htmlcs_type"], "warning")

    def test_an_error_stays_proven(self):
        issue = self._issues(1)[0]
        self.assertEqual(issue.confidence, EXACT)
        self.assertEqual(issue.details["htmlcs_type"], "error")


class UntriedTrapsAreQuestions(unittest.TestCase):
    def test_an_unverified_candidate_is_not_proven(self):
        from audit.states import issues_from_states

        payload = json.dumps({"findings": [
            {"rule": "keyboard-trap", "selector": "a", "html": "<a href='#'>x</a>", "unverified": True},
            {"rule": "keyboard-trap", "selector": "b", "html": "<b tabindex='0'>y</b>",
             "verified": "real Tab and Shift+Tab did not leave it"}]})
        untried, tried = issues_from_states(payload, "https://example.com/")
        self.assertEqual(untried.confidence, NEEDS_BROWSER)
        self.assertEqual(tried.confidence, EXACT)


def _issue(rule, snippet, engine, confidence=EXACT, severity="serious", zone_name="Text",
           source="https://contoso.sharepoint.com/sites/ExampleSite/SitePages/A.aspx"):
    return Issue(rule, severity, snippet=snippet, engine=engine, confidence=confidence,
                 source=source, details={"zone": "author", "zone_name": zone_name})


class OneElementOneFinding(unittest.TestCase):
    def test_engines_in_different_zone_documents_merge_on_the_element(self):
        from audit.browser import merge_same_element

        field = '<input type="text" placeholder="Cerca" class="searchbar_a1b2c3d4">'
        static = _issue("label-placeholder-only", field + "…", "static")
        state = _issue("state:form-placeholder-as-label", field, "browser")
        text = '<span style="color:#777">Note</span>'
        axe = _issue("axe:color-contrast", text, "axe", confidence=NEEDS_BROWSER)
        htmlcs = _issue("htmlcs:1_4_3", text + "<b>more</b>", "htmlcs", severity="serious")
        first = DocumentReport(source=static.source, issues=[static, axe])
        second = DocumentReport(source=static.source, issues=[state, htmlcs])
        merge_same_element([first, second])
        left = first.issues + second.issues
        self.assertEqual(len(left), 2)
        contrast = next(i for i in left if "contrast" in i.rule_id or i.rule_id.startswith("htmlcs"))
        # The settled one is kept over the unsettled one, and names the other.
        self.assertEqual(contrast.rule_id, "htmlcs:1_4_3")
        self.assertEqual(contrast.details["also_found_by"], ["axe:color-contrast"])
        self.assertEqual(contrast.details["agreement"], 2)

    def test_different_elements_parts_or_pages_stay_apart(self):
        from audit.browser import merge_same_element

        a = _issue("axe:color-contrast", '<span class="a">x</span>', "axe")
        b = _issue("htmlcs:1_4_3", '<span class="b">x</span>', "htmlcs")
        c = _issue("htmlcs:1_4_3", '<span class="a">x</span>', "htmlcs", zone_name="News")
        d = _issue("htmlcs:1_4_3", '<span class="a">x</span>', "htmlcs",
                   source="https://contoso.sharepoint.com/sites/ExampleSite/SitePages/B.aspx")
        document = DocumentReport(source=a.source, issues=[a, b, c, d])
        merge_same_element([document])
        self.assertEqual(len(document.issues), 4)

    def test_a_rule_with_no_cross_engine_twin_is_never_merged(self):
        from audit.browser import merge_same_element

        one = _issue("link-text-vague", '<a href="/x">clicca qui</a>', "static")
        two = _issue("link-text-vague", '<a href="/x">clicca qui</a>', "static")
        document = DocumentReport(source=one.source, issues=[one, two])
        merge_same_element([document])
        self.assertEqual(len(document.issues), 2)


if __name__ == "__main__":
    unittest.main()
