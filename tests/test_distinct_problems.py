"""The number a run leads with is distinct problems, and prompts are not defects.

A crawl of 381 pages of one site reported 15 338 findings. About 980 were
different: a header, a footer and an icon sprite sit on every page, so four
repeated ids were 2 612 rows. On top of that, HTML_CodeSniffer's "check this by
hand" warnings and a success criterion WCAG 2.2 dropped (4.1.1) were reported
at `serious` and `moderate`. Roughly half of the list was not work to do.

These tests pin the three corrections: the headline counts a problem once; the
engine's prompts and the obsolete criterion are demoted, not deleted; and what
the engine *measured* keeps its weight.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from audit.base import ACCESSIBILITY, ADVISORY, EXACT, MINOR, MODERATE, SERIOUS, Issue
from audit.browser import issues_from_htmlcs
from audit.engine import AccessibilityResult, DocumentReport
from audit.explanations import _wcag_for, summary_line
from duplicates import group_issues

ROOT = Path(__file__).resolve().parents[1]


def issue(source: str, snippet: str = "<a id='x'></a>", rule: str = "duplicate-id",
          severity: str = SERIOUS, **details) -> Issue:
    return Issue(rule_id=rule, severity=severity, category=ACCESSIBILITY,
                 source=source, snippet=snippet, details=details)


def result_of(*documents: tuple) -> AccessibilityResult:
    return AccessibilityResult(root="r", documents=[
        DocumentReport(source=source, issues=list(issues), elements_checked=1)
        for source, issues in documents])


class TheHeadlineCountsAProblemOnce(unittest.TestCase):
    def setUp(self):
        shared = "<symbol id='it-arrow-up'></symbol>"
        self.result = result_of(
            ("/a", [issue("/a", shared), issue("/a", "<img>", "image-alt", SERIOUS)]),
            ("/b", [issue("/b", shared)]),
            ("/c", [issue("/c", shared)]),
        )

    def test_occurrences_are_still_counted(self):
        self.assertEqual(self.result.counts()["serious"], 4)

    def test_distinct_counts_a_repeated_problem_once(self):
        self.assertEqual(self.result.distinct_counts()["serious"], 2)
        self.assertEqual(len(self.result.distinct()), 2)

    def test_nothing_is_dropped_by_grouping(self):
        first, others = self.result.distinct()[0]
        self.assertEqual(len(others), 2)
        self.assertEqual({i.source for i in [first, *others]}, {"/a", "/b", "/c"})

    def test_the_summary_leads_with_the_distinct_number_and_keeps_the_other(self):
        for lang, lead, tail in (("uk", "Унікальних проблем 2", "4 разів"),
                                 ("it", "Problemi unici 2", "4 volte"),
                                 ("en", "2 unique problems", "4 times")):
            with self.subTest(lang=lang):
                line = summary_line(self.result, lang)
                self.assertIn(lead, line)
                self.assertIn(tail, line)

    def test_a_run_where_nothing_repeats_keeps_the_short_sentence(self):
        plain = result_of(("/a", [issue("/a", "<p>1</p>")]), ("/b", [issue("/b", "<p>2</p>")]))
        self.assertNotIn("Унікальних", summary_line(plain, "uk"))
        self.assertIn("серйозних 2", summary_line(plain, "uk"))


class FindingsAboutThePageNeedSomethingToTellThemApart(unittest.TestCase):
    """473 strings left untranslated had no snippet and no selector, so with no
    other evidence every one of them was "the same problem"."""

    def make(self, source, text):
        return Issue(rule_id="seo-untranslated-content", severity=MODERATE,
                     category="seo", source=source, details={"text": text})

    def test_different_texts_are_different_problems(self):
        groups = group_issues([self.make("/de/a", "Domande frequenti"),
                               self.make("/de/b", "Info Point")])
        self.assertEqual(len(groups), 2)

    def test_the_same_text_on_two_pages_is_one(self):
        groups = group_issues([self.make("/de/a", "Info Point"), self.make("/de/b", "Info Point")])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0][1]), 1)


def htmlcs(*messages) -> list:
    return issues_from_htmlcs(json.dumps({"messages": [
        {"type": t, "code": c, "msg": "m", "html": "<a>", "tag": "a"} for t, c in messages]}),
        "/p")


class EnginePromptsAreNotDefects(unittest.TestCase):
    PREFIX = "WCAG2AA.Principle2.Guideline2_5."

    def test_the_label_in_name_prompt_is_advisory_and_minor(self):
        found = htmlcs((2, self.PREFIX + "2_5_3.F96"))[0]
        self.assertEqual((found.severity, found.confidence), (MINOR, ADVISORY))
        self.assertTrue(found.details["manual_check"])

    def test_the_fixed_position_reflow_prompt_is_advisory_and_minor(self):
        found = htmlcs((2, "WCAG2AA.Principle1.Guideline1_4.1_4_10.C32,C31,C33,C38,SCR34,G206"))[0]
        self.assertEqual((found.severity, found.confidence), (MINOR, ADVISORY))

    def test_a_decorative_image_notice_and_list_recommendations_are_too(self):
        for code in ("WCAG2AA.Principle1.Guideline1_1.1_1_1.H67.2",
                     "WCAG2AA.Principle1.Guideline1_3.1_3_1.H48",
                     "WCAG2AA.Principle1.Guideline1_3.1_3_1.H85.2"):
            with self.subTest(code=code):
                found = htmlcs((2, code))[0]
                self.assertEqual((found.severity, found.confidence), (MINOR, ADVISORY))

    def test_what_the_engine_measured_keeps_its_weight(self):
        contrast = htmlcs((1, "WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail"))[0]
        self.assertEqual((contrast.severity, contrast.confidence), (SERIOUS, EXACT))
        link = htmlcs((1, "WCAG2AA.Principle1.Guideline1_1.1_1_1.H30.2"))[0]
        self.assertEqual((link.severity, link.confidence), (SERIOUS, EXACT))
        self.assertFalse(link.details["manual_check"])

    def test_a_prompt_of_a_shape_not_listed_is_left_alone(self):
        found = htmlcs((2, "WCAG2AA.Principle1.Guideline1_3.1_3_1.H42"))[0]
        self.assertEqual(found.severity, MODERATE)


class ParsingIsNotInWcag22(unittest.TestCase):
    def test_the_engine_s_duplicate_id_is_minor_advisory_and_cites_nothing(self):
        found = htmlcs((1, "WCAG2AA.Principle4.Guideline4_1.4_1_1.F77"))[0]
        self.assertEqual((found.severity, found.confidence), (MINOR, ADVISORY))
        self.assertTrue(found.details["obsolete_criterion"])
        self.assertEqual(_wcag_for(found.rule_id), ())

    def test_the_static_duplicate_id_rule_does_not_cite_it_either(self):
        self.assertEqual(_wcag_for("duplicate-id"), ())

    def test_other_criteria_are_still_cited(self):
        self.assertEqual(_wcag_for("htmlcs:2_5_3"), ("2.5.3",))
        self.assertEqual(_wcag_for("htmlcs:1_4_3"), ("1.4.3",))


class TheJsonCarriesBothNumbers(unittest.TestCase):
    PAGE = ("<!doctype html><html lang='it'><head><meta charset='utf-8'><title>t pagina</title>"
            "</head><body><main><h1>x</h1>"
            "<img src='/a.jpg' alt='mappa-parlante-example'>"
            "<img src='/b.jpg' alt='mappa-parlante-example'>"
            "</main></body></html>")

    def run_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "p.html"
            path.write_text(self.PAGE, encoding="utf-8")
            done = subprocess.run(
                [sys.executable, str(ROOT / "cli.py"), "--no-update-check", "audit", str(path),
                 "--category", "accessibility", "--no-browser", "--json"],
                capture_output=True, text=True, encoding="utf-8", cwd=folder, timeout=120)
        return json.loads(done.stdout)

    def test_counts_are_distinct_and_occurrences_are_beside_them(self):
        data = self.run_cli()
        self.assertEqual(sum(data["counts"].values()), data["distinct"])
        self.assertGreaterEqual(sum(data["occurrences"].values()), data["distinct"])
        self.assertTrue(data["problems"])
        slug = [p for p in data["problems"] if p["rule"] == "image-alt-filename"]
        self.assertEqual(len(slug), 2)  # two different images: two problems
        self.assertTrue(all(p["occurrences"] == 1 for p in slug))
        for problem in data["problems"]:
            self.assertIn("pages", problem)
            self.assertIn("sources", problem)

    def test_every_finding_is_still_listed(self):
        data = self.run_cli()
        self.assertEqual(len(data["issues"]), sum(data["occurrences"].values()))


if __name__ == "__main__":
    unittest.main()
