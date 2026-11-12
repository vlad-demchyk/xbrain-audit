"""Pages read as pages, components add up, and a group never joins unrelated findings.

Seen in a short PDF of a SharePoint run: "pages with the most findings"
listed `…aspx — div:nth-of-type(1) > … > img` rows (elements counted as
pages), the cards printed a full address and a nine-step CSS path per place,
and the overview gave totals nobody could check against the parts of the
site they came from.
"""
from __future__ import annotations

import os
import re
import unittest
from unittest import mock

from audit.base import EXACT, Issue
from audit.engine import AccessibilityResult, DocumentReport
from report.model import (from_accessibility, page_index, page_label, readable_location,
                          short_selector)
from report.template import render_html

SITE = "https://contoso.sharepoint.com/sites/ExampleSite"
BACKUP = f"{SITE}/SitePages/Backup/I%20nostri%20Obiettivi%20strategici.aspx"


class ReadablePages(unittest.TestCase):
    def test_a_page_is_named_by_its_decoded_path_below_the_site(self):
        self.assertEqual(page_label(BACKUP, SITE), "Backup / I nostri Obiettivi strategici")
        self.assertEqual(page_label(f"{SITE}/SitePages/Home.aspx", SITE), "Home")
        self.assertEqual(page_label("https://example.com/", "https://example.com/"), "/")

    def test_a_place_is_the_page_and_the_last_two_steps(self):
        where = f"{BACKUP} — div:nth-of-type(1) > div > section > figure > img:nth-of-type(1)"
        self.assertEqual(readable_location(where, SITE),
                         "Backup / I nostri Obiettivi strategici — … > figure > img:nth-of-type(1)")
        self.assertEqual(short_selector("a > b"), "a > b")


def _result():
    documents = []
    for name in ("Home", "Backup/I%20nostri%20Obiettivi%20strategici", "News"):
        source = f"{SITE}/SitePages/{name}.aspx"
        issues = [Issue("axe:button-name", "critical", selector=f"div > header > button:nth-of-type({n})",
                        snippet=f'<button class="ms-Button root-{n}">', source=source, engine="axe",
                        details={"zone": "custom", "zone_name": "Contoso Header"})
                  for n in range(6)]
        issues += [Issue("image-alt", "serious",
                         selector=f"div:nth-of-type(1) > div > section > figure > img:nth-of-type({n})",
                         snippet=f'<img src="/i/{name}-{n}.png">', source=source,
                         details={"zone": "author", "zone_name": "Text"}) for n in range(2)]
        documents.append(DocumentReport(source=source, issues=issues))
        # A second document of the same page (another zone): one page, not two.
        documents.append(DocumentReport(source=source, issues=[]))
    return AccessibilityResult(root=SITE, mode="web", documents=documents)


def _model(lang="en"):
    result = _result()
    model = from_accessibility(result, lang)
    model.pages = page_index({"source": d.source, "findings_count": len(d.issues), "error": ""}
                             for d in result.documents)
    return model


class ThePagesLists(unittest.TestCase):
    def test_most_findings_counts_pages_not_elements(self):
        places = _model().counts_by_place()
        self.assertEqual(len(places), 3)
        self.assertIn(("Backup / I nostri Obiettivi strategici", 8), places)
        for label, _count in places:
            self.assertNotIn("nth-of-type", label)

    def test_the_pages_examined_link_the_full_address_under_a_readable_name(self):
        html = render_html(_model(), "en")
        section = html.split('<section class="pages">')[1].split("</section>")[0]
        self.assertIn(f'<a href="{BACKUP}">Backup / I nostri Obiettivi strategici</a>', section)
        self.assertEqual(section.count("<tr>") - 1, 3)

    def test_cards_name_places_readably(self):
        html = render_html(_model(), "en")
        findings = html.split('<section class="findings">')[1].split("</section>")[0]
        self.assertNotIn("div:nth-of-type(1) > div > section", findings)
        self.assertIn("Backup / I nostri Obiettivi strategici — … &gt; figure &gt;", findings)

    def test_places_that_read_the_same_are_one_line_with_a_count(self):
        from report.model import ReportFinding
        from report.template import _locations_block, _labels

        finding = ReportFinding(
            title="t", category="accessibility", severity="serious", location="",
            locations=[f"{BACKUP} — div:nth-of-type({n}) > div > video:nth-of-type(1)"
                       for n in range(1, 4)])
        block = _locations_block(finding, _labels("en"), SITE)
        self.assertEqual(block.count("<li>"), 1)
        self.assertIn("(×3)", block)
        self.assertIn("Found in 3 places", block)

    def test_the_overview_counts_pages_out_of_the_pages_examined(self):
        for lang, words in (("en", "on 3 of the 3 pages"), ("it", "su 3 delle 3 pagine")):
            with self.subTest(lang):
                self.assertIn(words, render_html(_model(lang), lang))


class TheComponentsAddUp(unittest.TestCase):
    def test_each_component_once_and_the_rows_sum_to_the_totals(self):
        html = render_html(_model(), "en")
        rows = re.findall(r'<tr class="component-row"><td>([^<]*)</td><td class="num">(\d+)</td>'
                          r'<td class="num">(\d+)</td><td class="num">(\d+)</td></tr>', html)
        names = [row[0] for row in rows]
        self.assertEqual(sorted(names), ["Author content: Text", "SPFx: Contoso Header"])
        line = re.search(r'<p class="tally">(.*?)</p>', html).group(1)
        problems, occurrences = map(int, re.findall(r"\d+", line)[:2])
        self.assertEqual(problems, sum(int(row[1]) for row in rows))
        self.assertEqual(occurrences, sum(int(row[2]) for row in rows))
        header = dict((row[0], row[1:]) for row in rows)["SPFx: Contoso Header"]
        self.assertEqual(header, ("1", "18", "3"))    # one component problem on 3 pages

    def test_a_run_without_zones_prints_no_component_table(self):
        result = AccessibilityResult(root="https://example.com/", mode="web", documents=[
            DocumentReport(source="https://example.com/", issues=[
                Issue("image-alt", "serious", snippet='<img src="a.png">',
                      source="https://example.com/")])])
        self.assertNotIn("components-table", render_html(from_accessibility(result, "en"), "en"))


class AGroupNeverJoinsUnrelatedFindings(unittest.TestCase):
    def _issue(self, rule, snippet, zone="custom", zone_name="Contoso Header"):
        return Issue(rule, "serious", snippet=snippet, confidence=EXACT,
                     details={"zone": zone, "zone_name": zone_name})

    def test_the_conflicts_are_named(self):
        from duplicates import group_conflict

        button = '<button class="ms-Button">'
        self.assertEqual(group_conflict(self._issue("axe:button-name", button),
                                        self._issue("control-name", button)), "")
        self.assertIn("family", group_conflict(self._issue("axe:button-name", button),
                                               self._issue("axe:color-contrast", button)))
        self.assertIn("zone", group_conflict(self._issue("axe:button-name", button),
                                             self._issue("axe:button-name", button, zone_name="News")))
        self.assertIn("shape", group_conflict(self._issue("axe:button-name", button),
                                              self._issue("axe:button-name", '<button class="menu_1a2b3c4d">')))
        self.assertIn("identity", group_conflict(
            self._issue("image-alt", '<img src="a.png" alt="a">', zone="author", zone_name="Text"),
            self._issue("image-alt", '<img src="b.png" alt="b">', zone="author", zone_name="Text")))

    def test_a_key_that_merges_unrelated_findings_raises_under_tests(self):
        import duplicates

        issues = [self._issue("axe:button-name", '<button class="ms-Button">'),
                  self._issue("axe:color-contrast", '<span class="x">')]
        with mock.patch.object(duplicates, "issue_identity", return_value=("same",)):
            with self.assertRaises(duplicates.GroupInvariantError):
                duplicates.group_issues(issues)

    def test_in_production_it_is_split_instead(self):
        import duplicates

        issues = [self._issue("axe:button-name", '<button class="ms-Button">'),
                  self._issue("axe:color-contrast", '<span class="x">')]
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTEST_CURRENT_TEST", "XAUDIT_STRICT_GROUPS")}
        with mock.patch.object(duplicates, "issue_identity", return_value=("same",)), \
                mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(len(duplicates.group_issues(issues)), 2)


if __name__ == "__main__":
    unittest.main()
