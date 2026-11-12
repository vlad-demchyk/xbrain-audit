"""The to-check and recommendations sections are one row per rule, not a card each.

A live run over a 104-page intranet printed 1436 "to check by hand" entries
as full finding cards - most of them one people-directory web part's photos
whose contrast could not be measured - and the PDF ran to 1018 pages. The
open questions are now a compact table: per rule its title, WCAG, why it is
not settled, how often, on how many pages, in which parts, and three
examples. Proven findings keep their cards, and no total changes.
"""
from __future__ import annotations

import re
import unittest

from audit.base import ADVISORY, EXACT, NEEDS_BROWSER
from report.model import ReportFinding, ReportMeta, ReportModel
from report.template import render_html

SITE = "https://contoso.sharepoint.com/sites/ExampleSite/SitePages"


def _finding(rule, index, confidence, title, zone_name="People Directory"):
    return ReportFinding(
        title=title, category="accessibility", severity="serious",
        location=f"{SITE}/Page{index % 40}.aspx — div.person:nth-of-type({index})",
        why="The text sits over a photo, so its contrast cannot be measured.",
        caveat="An engine could not decide this: open the page in a browser.",
        snippet=f'<img class="photo" src="/sites/ExampleSite/photos/{rule}-{index}.jpg">',
        engine="axe", wcag=("1.4.3",), rule_id=rule, confidence=confidence,
        zone="custom", zone_name=zone_name)


def _model():
    findings = []
    rules = (("axe:color-contrast", "Text contrast over an image"),
             ("axe:video-caption", "Video captions"),
             ("htmlcs:1_4_10", "Reflow at 320 px"))
    for index in range(500):
        rule, title = rules[index % 3]
        findings.append(_finding(rule, index, NEEDS_BROWSER, title))
    for index in range(20):
        findings.append(_finding("image-modern-format", index, ADVISORY,
                                 "Image format", zone_name="Text"))
    findings.append(_finding("axe:image-alt", 1, EXACT, "Image without alt"))
    findings.append(_finding("axe:button-name", 2, EXACT, "Button without a name"))
    return ReportModel(meta=ReportMeta(target=SITE, mode="audit-web"), findings=findings)


def _section(html, key):
    match = re.search(rf'<section class="findings {key}">.*?</section>', html, re.S)
    return match.group(0) if match else ""


class TheOpenQuestionsAreCompact(unittest.TestCase):
    def test_to_check_is_one_row_per_rule(self):
        html = render_html(_model(), "en")
        section = _section(html, "to_verify")
        self.assertEqual(section.count('<tr class="side-row">'), 3)
        self.assertNotIn("<article", section)
        self.assertIn("To check by hand (3)", section)

    def test_a_row_says_how_often_where_and_why(self):
        section = _section(render_html(_model(), "en"), "to_verify")
        row = next(r for r in section.split('<tr class="side-row">')[1:]
                   if "axe:color-contrast" in r)
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        self.assertIn("1.4.3", cells[1])
        self.assertIn("could not decide", cells[2])
        self.assertEqual(cells[3], "167")      # every occurrence, counted once
        self.assertEqual(cells[4], "40")       # distinct pages
        self.assertEqual(cells[5], "People Directory")
        self.assertEqual(cells[6].count("<li>"), 3)
        self.assertIn("and 164 more", cells[6])
        self.assertIn("Page0.aspx", cells[6])

    def test_one_rule_in_two_parts_is_two_rows(self):
        model = _model()
        model.findings.append(_finding("axe:color-contrast", 900, NEEDS_BROWSER,
                                       "Text contrast over an image", zone_name="News"))
        section = _section(render_html(model, "en"), "to_verify")
        self.assertEqual(section.count('<tr class="side-row">'), 4)

    def test_recommendations_are_compact_too_and_last(self):
        html = render_html(_model(), "en")
        section = _section(html, "recommendations")
        self.assertEqual(section.count('<tr class="side-row">'), 1)
        self.assertNotIn("<article", section)

    def test_proven_findings_keep_their_cards_and_the_totals(self):
        html = render_html(_model(), "en")
        main = re.search(r'<section class="findings">\s*<h2>[^<]*\((\d+)\)</h2>', html)
        self.assertEqual(int(main.group(1)), 2)
        self.assertEqual(html.count('<article class="finding'), 2)

    def test_the_document_stays_small(self):
        """520 open findings used to be 520 cards; now they are four rows."""
        self.assertLess(len(render_html(_model(), "en")), 120_000)

    def test_labels_in_every_language(self):
        for lang, words in (("uk", ("Чому не вирішено", "Сторінок", "і ще 164")),
                            ("it", ("Perché non è deciso", "Pagine", "e altri 164"))):
            with self.subTest(lang):
                section = _section(render_html(_model(), lang), "to_verify")
                for word in words:
                    self.assertIn(word, section)


if __name__ == "__main__":
    unittest.main()
