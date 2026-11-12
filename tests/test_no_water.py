"""Four changes that came out of using the built app on real sites.

**The undecided are not findings.** Measured on one page of `python.org`
with a real browser: 348 contrast findings, **312** of them an engine saying
it could not tell - "this element is on a background image", "absolutely
positioned, the background colour cannot be determined" - against 36
measured failures. A report two thirds made of "we do not know" is not a
list anybody works through. `fullscan` loads the page in a browser precisely
to settle these; what is undecided after that is not something the tool
knows, and where no browser ran it knows less still. The whole run: 497
findings before, **182** after.

**The saturation guard was blind on one page.** It measured the share of
*documents* a rule reached, so it needed three of them - and a single page
is exactly where the noise is loudest, because every rule reaches "all" of
one document. The population of a page is its elements.

**The browser pass is cached.** It is the expensive half: 7.0 s against
0.53 s for the second run of an unchanged page, identical findings. Keyed on
the markup the crawler already received, never on the address - a page
changes, and a cache keyed on where it lives would answer about yesterday.

**The report is about the page, not about last Tuesday.** The comparison
section left the report; `changes.md` in the run folder is where that
question already had a home.
"""
from __future__ import annotations

import unittest

from audit.base import (
    ACCESSIBILITY, ADVISORY, EXACT, Issue, MINOR, NEEDS_BROWSER, SERIOUS,
    issues_in_view, unsettled_count,
)
from audit.engine import AccessibilityResult, DocumentReport
from audit.saturation import saturated_rules


def issue(rule, confidence=EXACT, category=ACCESSIBILITY, severity=MINOR):
    return Issue(rule_id=rule, severity=severity, category=category,
                 confidence=confidence, source="https://example.test/",
                 details={})


class TheUndecidedStayOut(unittest.TestCase):

    def setUp(self):
        self.issues = [issue("image-alt"),
                       issue("htmlcs:1_4_3", NEEDS_BROWSER),
                       issue("geo-article-schema", ADVISORY)]

    def test_the_default_view_is_what_the_tool_knows(self):
        self.assertEqual([i.rule_id for i in issues_in_view(self.issues)],
                         ["image-alt"])

    def test_the_number_left_out_is_available(self):
        self.assertEqual(unsettled_count(self.issues), 2)

    def test_asking_brings_them_back(self):
        self.assertEqual(len(issues_in_view(self.issues, unsettled=True)), 3)

    def test_the_cli_says_how_many_it_hid(self):
        """Dropped in silence is a report lying by omission."""
        import inspect

        import cli

        source = inspect.getsource(cli)
        self.assertIn("could not be decided", source)
        self.assertIn("--unsettled", source)

    def test_fullscan_says_it_too(self):
        import inspect

        from cli_impl import fullscan

        self.assertIn("could not be decided", inspect.getsource(fullscan))


class TheGuardSeesOnePage(unittest.TestCase):
    """The shape it exists for, at the size it used to be blind at."""

    @staticmethod
    def _result(counts, elements):
        issues = []
        for rule, n in counts.items():
            issues += [issue(rule) for _ in range(n)]
        return AccessibilityResult(root="r", documents=[
            DocumentReport(source="p", issues=issues,
                           elements_checked=elements)])

    def test_a_rule_that_fires_on_half_a_page_is_caught(self):
        """The GOV.UK focus failure: 59 findings against the 120 elements the
        pass examines per page."""
        found = saturated_rules(self._result({"state:focus-not-visible": 59}, 120))
        self.assertEqual([s.rule for s in found], ["state:focus-not-visible"])
        self.assertAlmostEqual(found[0].element_share, 59 / 120, places=3)

    def test_the_noisiest_real_rule_is_not_caught(self):
        """`htmlcs:1_4_3` on python.org: 145 findings against 833 elements.
        Loud, and still describing the page."""
        self.assertEqual(saturated_rules(self._result({"htmlcs:1_4_3": 145}, 833)), [])

    def test_a_handful_of_findings_is_never_saturation(self):
        self.assertEqual(saturated_rules(self._result({"image-alt": 5}, 6)), [])

    def test_a_document_that_counted_nothing_is_skipped(self):
        """Dividing by an assumption would invent the number the guard exists
        to check."""
        self.assertEqual(saturated_rules(self._result({"x": 50}, 0)), [])

    def test_the_message_says_what_was_measured(self):
        found = saturated_rules(self._result({"state:focus-not-visible": 59}, 120))
        self.assertIn("120 elements", found[0].message())
        self.assertIn("49%", found[0].message())


class TheBrowserPassRemembersPages(unittest.TestCase):

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _cache(self, sizes=(("desktop", 1440, 900),)):
        import browser_cache

        class Options:
            exclude = ()
            disabled_rules = ()
            run_axe = run_htmlcs = run_states = run_measurements = True
            allow_local_files = False
            settle_ms = 0

        return browser_cache.BrowserCache(Options(), sizes,
                                          directory=self.tmp.name)

    @staticmethod
    def _audit(url="https://example.test/"):
        from audit.driver import PageAudit

        return PageAudit(url=url, issues=[issue("image-alt")],
                         measurements={"lcp": 1200})

    def test_the_same_markup_comes_back(self):
        cache = self._cache()
        cache.put("<html>a</html>", self._audit())
        cache.save()
        stored = self._cache().get("<html>a</html>", "https://example.test/")
        self.assertIsNotNone(stored)
        self.assertEqual([i.rule_id for i in stored.issues], ["image-alt"])
        self.assertEqual(stored.measurements["lcp"], 1200)
        self.assertTrue(stored.measurements["conditions"]["cacheHit"])
        self.assertFalse(stored.measurements["conditions"]["freshMeasurement"])

    def test_changed_markup_is_a_different_page(self):
        cache = self._cache()
        cache.put("<html>a</html>", self._audit())
        self.assertIsNone(cache.get("<html>b</html>", "https://example.test/"))

    def test_different_widths_are_a_different_question(self):
        cache = self._cache()
        cache.put("<html>a</html>", self._audit())
        cache.save()
        other = self._cache(sizes=(("mobile", 390, 844),))
        self.assertIsNone(other.get("<html>a</html>", "https://example.test/"))

    def test_a_failed_pass_is_not_remembered(self):
        from audit.driver import PageAudit

        cache = self._cache()
        cache.put("<html>a</html>",
                  PageAudit(url="u", error="the page did not load"))
        self.assertIsNone(cache.get("<html>a</html>", "u"))

    def test_the_address_comes_from_the_caller_not_the_cache(self):
        """The same markup can be served at two URLs, and a finding has to
        point at the page in hand."""
        cache = self._cache()
        cache.put("<html>a</html>", self._audit("https://one.test/"))
        stored = cache.get("<html>a</html>", "https://two.test/")
        self.assertEqual(stored.issues[0].source, "https://two.test/")

    def test_it_says_when_it_saved_a_pass(self):
        cache = self._cache()
        cache.put("<html>a</html>", self._audit())
        cache.get("<html>a</html>", "u")
        self.assertIn("read from cache", cache.summary())

    def test_the_result_carries_the_markup_the_cache_keys_on(self):
        """Without it the pass has nothing honest to key on."""
        result = AccessibilityResult(root="r")
        self.assertEqual(result.markup_by_source, {})


class TheReportIsAboutThePage(unittest.TestCase):

    def test_no_comparison_section_is_written(self):
        import inspect

        from cli_impl import reports

        self.assertNotIn('"## Since the last run"', inspect.getsource(reports))

    def test_the_comparison_document_still_exists(self):
        """Removed from the report, not from the tool: it is a different
        genre and it already had a file of its own."""
        from cli_impl.reports import compare_runs  # noqa: F401

    def test_the_report_says_what_repeats_and_where(self):
        from report.model import ReportFinding, ReportMeta, ReportModel

        model = ReportModel(
            meta=ReportMeta(target="t", mode="audit-web"),
            findings=[
                ReportFinding(category="accessibility", severity="critical",
                              title="Control with no accessible name",
                              found="f", why="w", fix="x",
                              location="https://a/1"),
                ReportFinding(category="accessibility", severity="critical",
                              title="Control with no accessible name",
                              found="f", why="w", fix="x",
                              location="https://a/2"),
                ReportFinding(category="seo", severity="moderate",
                              title="Missing description", found="f", why="w",
                              fix="x", location="https://a/1"),
            ])
        self.assertEqual(model.counts_by_title()[0][2], 2)
        # The page, as a person names it (`report.model.page_label`).
        self.assertEqual(model.counts_by_place()[0], ("1", 2))

    def test_the_section_renders_in_every_language(self):
        from report.model import ReportFinding, ReportMeta, ReportModel
        from report.template import render_html

        model = ReportModel(
            meta=ReportMeta(target="t", mode="audit-web"),
            findings=[ReportFinding(category="seo", severity="moderate",
                                    title="Missing description", found="f",
                                    why="w", fix="x", location="https://a/1")])
        for lang in ("uk", "it", "en"):
            with self.subTest(lang=lang):
                html = render_html(model, lang)
                self.assertIn("rank-grid", html)
                self.assertNotIn("{", html.split("<style>")[0])


if __name__ == "__main__":
    unittest.main()
