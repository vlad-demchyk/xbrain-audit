"""In a custom web part the same defect on every instance is one problem.

A custom SPFx web part is code somebody deployed: an unnamed `ms-Button` in a
custom header placed on every page is one defect with one fix in the
component's code, not 383 rows. Inside a `custom` zone a problem is the
rule's family, the web part and the element's shape (`duplicates.
component_identity`); everywhere else - the author's own content, any site
that is not SharePoint - each image and each link needs its own fix and keeps
`issue_identity` as it was. The HTML report, the JSON summary and the window
share the identity; the findings themselves are all kept.
"""
from __future__ import annotations

import unittest

from audit.base import EXACT, NEEDS_BROWSER, Issue
from duplicates import element_shape, group_issues, issue_identity

PAGE = "https://contoso.sharepoint.com/sites/ExampleSite/SitePages/{}.aspx"


def _issue(rule, snippet, zone_name="Contoso Header", zone="custom", severity="serious",
           confidence=EXACT, page="A", engine="axe", selector=""):
    return Issue(rule, severity, snippet=snippet, selector=selector, confidence=confidence,
                 source=PAGE.format(page), engine=engine,
                 details={"zone": zone, "zone_name": zone_name})


class WhatMergesInACustomPart(unittest.TestCase):
    def test_a_state_class_and_a_fluent_counter_do_not_split_a_problem(self):
        a = _issue("axe:button-name", '<button type="button" class="ms-Button root-262">')
        b = _issue("axe:button-name", '<button type="button" class="ms-Button is-disabled root-340">',
                   page="B")
        self.assertEqual(issue_identity(a), issue_identity(b))

    def test_griffel_atomic_classes_do_not_split_it(self):
        self.assertEqual(element_shape('<span class="fui-Tab__content f16hsg94 ___1q2w3e_0000000">'),
                         "span.fui-Tab__content")

    def test_different_images_of_one_part_are_one_problem(self):
        a = _issue("image-alt", '<img class="icon_89ac8aab" src="/i/a.png" alt="a.png">',
                   engine="static")
        b = _issue("image-alt", '<img class="icon_89ac8aab" src="/i/b.png" alt="b.png">',
                   engine="static", page="B")
        self.assertEqual(issue_identity(a), issue_identity(b))

    def test_the_static_rule_and_axe_of_one_family_are_one_problem(self):
        a = _issue("control-name", '<button class="search_button_fd3679fe">', engine="static",
                   severity="critical")
        b = _issue("axe:button-name", '<button class="search_button_fd3679fe root-262">')
        self.assertEqual(issue_identity(a), issue_identity(b))

    def test_outside_the_canvas_is_the_same_web_part(self):
        a = _issue("axe:button-name", '<button class="ms-Button">', zone_name="Contoso Header")
        b = _issue("axe:button-name", '<button class="ms-Button">',
                   zone_name="Contoso Header (outside the canvas)")
        self.assertEqual(issue_identity(a), issue_identity(b))

    def test_a_selector_gives_the_shape_when_nothing_was_quoted(self):
        self.assertEqual(element_shape("", "div#x > button.ms-Button.root-12:nth-of-type(2)"),
                         "button.ms-Button")


class WhatMustNotMerge(unittest.TestCase):
    def test_different_rule_families_stay_apart(self):
        markup = '<button class="ms-Button">'
        self.assertNotEqual(issue_identity(_issue("axe:button-name", markup)),
                            issue_identity(_issue("axe:color-contrast", markup)))

    def test_different_web_parts_stay_apart(self):
        markup = '<button class="ms-Button">'
        self.assertNotEqual(issue_identity(_issue("axe:button-name", markup, zone_name="Contoso Header")),
                            issue_identity(_issue("axe:button-name", markup, zone_name="Contoso News")))

    def test_a_different_semantic_class_is_a_different_element(self):
        self.assertNotEqual(
            issue_identity(_issue("axe:button-name", '<button class="ms-Button searchbar_fd3679fe">')),
            issue_identity(_issue("axe:button-name", '<button class="ms-Button menu_fd3679fe">')))

    def test_certainty_is_never_mixed(self):
        markup = '<span class="name_1a2b3c4d">Ann</span>'
        self.assertNotEqual(
            issue_identity(_issue("axe:color-contrast", markup, confidence=NEEDS_BROWSER)),
            issue_identity(_issue("axe:color-contrast", markup, confidence=EXACT)))

    def test_author_images_with_different_alt_are_two_fixes(self):
        a = _issue("image-alt", '<img class="icon" src="/i/a.png" alt="a.png">',
                   zone="author", zone_name="Text", engine="static")
        b = _issue("image-alt", '<img class="icon" src="/i/b.png" alt="b.png">',
                   zone="author", zone_name="Text", engine="static")
        self.assertNotEqual(issue_identity(a), issue_identity(b))

    def test_an_ordinary_site_keeps_one_problem_per_element(self):
        a = Issue("link-text-vague", "moderate", snippet='<a class="more" href="/a">click here</a>')
        b = Issue("link-text-vague", "moderate", snippet='<a class="more" href="/b">read more</a>')
        self.assertNotEqual(issue_identity(a), issue_identity(b))


class EverySurfaceGroupsTheSameWay(unittest.TestCase):
    def _issues(self):
        issues = [_issue("axe:button-name", f'<button class="ms-Button root-{n}">',
                         page=f"P{n % 9}", selector=f"button:nth-of-type({n})")
                  for n in range(383)]
        issues.append(_issue("control-name", '<button class="ms-Button">', severity="critical",
                             engine="static", page="P0", selector="header button"))
        return issues

    def test_the_json_summary_is_one_problem_at_its_worst_with_every_engine(self):
        from audit.engine import AccessibilityResult, DocumentReport
        from audit.explanations import render
        from cli_impl.reports import _problem_map

        result = AccessibilityResult(root=PAGE.format("A"), mode="web",
                                     documents=[DocumentReport(source=PAGE.format("A"),
                                                               issues=self._issues())])
        problems = _problem_map(result, render, "en")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["occurrences"], 384)   # every occurrence kept
        self.assertEqual(problems[0]["severity"], "critical")
        self.assertEqual(set(problems[0]["engine"].split(", ")), {"axe", "static"})

    def test_the_styled_report_prints_one_card_that_says_one_fix(self):
        from audit.engine import AccessibilityResult, DocumentReport
        from report.model import from_accessibility
        from report.template import render_html

        result = AccessibilityResult(root=PAGE.format("A"), mode="web", documents=[
            DocumentReport(source=PAGE.format(f"P{n}"),
                           issues=[i for i in self._issues() if i.source == PAGE.format(f"P{n}")])
            for n in range(9)])
        for lang, words in (("en", "One fix in the code of Contoso Header fixes all"),
                            ("uk", "Одне виправлення в коді Contoso Header"),
                            ("it", "Una sola correzione nel codice di Contoso Header")):
            with self.subTest(lang):
                model = from_accessibility(result, lang)
                self.assertEqual(len(model.grouped_findings()), 1)
                html = render_html(model, lang)
                self.assertEqual(html.count('<article class="finding'), 1)
                self.assertIn(words, html)


if __name__ == "__main__":
    unittest.main()
