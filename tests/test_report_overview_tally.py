"""The overview says what it counts: problems, places, pages, and the two side sections.

The stat cards and "what was found" count distinct problems and never said
so, and the to-check and recommendations sections were not mentioned in the
overview at all. One line under the cards now names every number, and each
is the count of the list it summarises.
"""
from __future__ import annotations

import re
import unittest

from audit.base import ADVISORY, NEEDS_BROWSER, Issue
from audit.engine import AccessibilityResult, DocumentReport
from report.model import from_accessibility
from report.template import render_html

SITE = "https://contoso.sharepoint.com/sites/ExampleSite/SitePages/"


def _result():
    documents = []
    for page in range(5):
        source = f"{SITE}P{page}.aspx"
        issues = [Issue("axe:button-name", "critical", selector=f"button:nth-of-type({n})",
                        snippet=f'<button class="ms-Button root-{n}">', source=source,
                        engine="axe", details={"zone": "custom", "zone_name": "Contoso Header"})
                  for n in range(10)]
        issues += [Issue("image-alt", "serious", selector=f"img:nth-of-type({n})",
                         snippet=f'<img src="/i/{page}-{n}.png">', source=source,
                         details={"zone": "author", "zone_name": "Text"}) for n in range(3)]
        issues += [Issue("axe:color-contrast", "serious", selector=f"span:nth-of-type({n})",
                         snippet='<span class="name_1a2b3c4d">x</span>', source=source,
                         engine="axe", confidence=NEEDS_BROWSER,
                         details={"zone": "custom", "zone_name": "People Directory"})
                   for n in range(8)]
        issues.append(Issue("image-modern-format", "minor", selector="img.hero",
                            snippet=f'<img class="hero" src="/i/h{page}.jpg" alt="Hero">',
                            source=source, confidence=ADVISORY,
                            details={"zone": "author", "zone_name": "Text"}))
        documents.append(DocumentReport(source=source, issues=issues))
    return AccessibilityResult(root=SITE, mode="web", documents=documents)


def _count(html, pattern):
    match = re.search(pattern, html)
    return int(match.group(1)) if match else 0


class TheOverviewSaysWhatItCounts(unittest.TestCase):
    def test_the_line_names_every_number_in_each_language(self):
        for lang, words in (("en", ("distinct problems", "occurrences on", "to check by hand",
                                    "recommendations")),
                            ("it", ("problemi distinti", "occorrenze su", "da verificare",
                                    "raccomandazioni")),
                            ("uk", ("Окремих проблем", "входжень", "перевірити вручну",
                                    "рекомендацій"))):
            with self.subTest(lang):
                html = render_html(from_accessibility(_result(), lang), lang)
                line = re.search(r'<p class="tally">(.*?)</p>', html).group(1)
                for word in words:
                    self.assertIn(word, line)

    def test_its_numbers_are_the_sections_counts(self):
        html = render_html(from_accessibility(_result(), "en"), "en")
        line = re.search(r'<p class="tally">(.*?)</p>', html).group(1)
        problems, occurrences, pages, verify, advice = map(int, re.findall(r"\d+", line))
        self.assertEqual(problems, _count(html, r'<section class="findings">\s*<h2>[^<]*\((\d+)\)'))
        self.assertEqual(verify, _count(html, r'<section class="findings to_verify"><h2>[^<]*\((\d+)\)'))
        self.assertEqual(advice, _count(html, r'<section class="findings recommendations"><h2>[^<]*\((\d+)\)'))
        # One component's button group (50 places) and 15 author images, each its own.
        self.assertEqual((problems, occurrences, pages), (16, 65, 5))


if __name__ == "__main__":
    unittest.main()
