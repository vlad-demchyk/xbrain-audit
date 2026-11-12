"""One problem on thirty pages is one problem, and a re-run must say so.

Two defects are pinned here, both found by running the tool rather than by
reading it:

* A crawl of pages that share a header repeated every fault of that header
  once per page, so a report of fourteen problems on five pages read as
  seventy problems.
* Run history was keyed on the report file path, and `fullscan` puts a
  timestamp in the path it generates - so every run got a fresh key, every
  history read came back empty, and the comparison with the previous run
  never appeared once.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duplicates
from audit.base import Issue
from cli_impl import reports
from report.model import ReportFinding, ReportMeta, ReportModel


def finding(location, title="Missing meta description", snippet="",
            category="seo", severity="moderate"):
    return ReportFinding(title=title, category=category, severity=severity,
                         location=location, found="none", why="search",
                         fix="add one", snippet=snippet)


class GroupedFindings(unittest.TestCase):
    def model(self, findings):
        model = ReportModel(meta=ReportMeta(target="https://x.com",
                                            mode="audit-web"))
        model.findings = list(findings)
        return model

    def test_identical_findings_collapse_and_keep_every_place(self):
        model = self.model(finding(f"https://x.com/p{i}") for i in range(30))
        grouped = model.grouped_findings()
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0].occurrences, 30)
        self.assertEqual(len(grouped[0].locations), 30)
        self.assertIn("https://x.com/p7", grouped[0].locations)

    def test_different_markup_stays_separate(self):
        """Two images missing alt are two problems, not one."""
        model = self.model([
            finding("p1", title="No alt", snippet="<img src=a.png>"),
            finding("p2", title="No alt", snippet="<img src=b.png>"),
        ])
        self.assertEqual(len(model.grouped_findings()), 2)

    def test_same_place_twice_is_not_two_places(self):
        model = self.model([finding("p1"), finding("p1")])
        grouped = model.grouped_findings()
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0].locations, ["p1"])

    def test_ungrouped_finding_reports_one_occurrence(self):
        self.assertEqual(finding("p1").occurrences, 1)

    def test_grouped_counts_count_each_problem_once(self):
        model = self.model(finding(f"p{i}") for i in range(10))
        self.assertEqual(model.counts_by_severity()["moderate"], 10)
        self.assertEqual(model.counts_by_severity_grouped()["moderate"], 1)

    def test_rendered_report_names_the_places(self):
        from report.template import render_html

        model = self.model(finding(f"https://x.com/p{i}") for i in range(30))
        html = render_html(model, "en")
        self.assertIn("Found in 30 places", html)
        # Each place by the page's readable name (`report.model.page_label`).
        self.assertIn('<a href="https://x.com/p0">p0</a>', html)
        # Not every one of the thirty: a card that is only a list of URLs
        # stops being a finding.
        self.assertIn("and 18 more", html)


class GroupedIssues(unittest.TestCase):
    def issue(self, source, rule="image-alt", snippet="<img src=logo.png>"):
        return Issue(rule_id=rule, severity="critical", snippet=snippet,
                     source=source, line=5)

    def test_same_markup_across_documents_is_one_problem(self):
        issues = [self.issue(f"p{i}.html") for i in range(5)]
        grouped = duplicates.group_issues(issues)
        self.assertEqual(len(grouped), 1)
        first, others = grouped[0]
        self.assertEqual(len(duplicates.places_of(first, others)), 5)

    def test_different_rules_stay_apart(self):
        grouped = duplicates.group_issues(
            [self.issue("p1.html"), self.issue("p1.html", rule="html-lang")])
        self.assertEqual(len(grouped), 2)

    def test_places_are_deduplicated(self):
        issues = [self.issue("p1.html"), self.issue("p1.html")]
        first, others = duplicates.group_issues(issues)[0]
        self.assertEqual(duplicates.places_of(first, others), ["p1.html:5"])

    def test_selector_identifies_a_finding_with_no_markup(self):
        a = Issue(rule_id="r", severity="minor", selector="body > main",
                  source="p1")
        b = Issue(rule_id="r", severity="minor", selector="body > footer",
                  source="p1")
        self.assertEqual(len(duplicates.group_issues([a, b])), 2)


class HistoryKey(unittest.TestCase):
    def test_keyed_on_target_not_on_report_path(self):
        """The bug: a new report file name meant a new, empty history."""
        first = reports._history_key("https://x.com", "web")
        second = reports._history_key("https://x.com", "web")
        self.assertEqual(first, second)

    def test_mode_is_part_of_the_identity(self):
        self.assertNotEqual(reports._history_key("/repo", "web"),
                            reports._history_key("/repo", "repo"))

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(reports, "_history_dir",
                                   return_value=Path(tmp)):
                with mock.patch.object(reports, "_legacy_history",
                                       return_value=[]):
                    reports._write_history("/repo", "repo", [
                        {"at": "2026-01-01 00:00:00 UTC", "root": "/repo",
                         "mode": "repo", "counts": {"minor": 3}},
                    ])
                    back = reports._read_history("/repo", "repo")
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0]["counts"], {"minor": 3})

    def test_legacy_entries_are_folded_in(self):
        """Runs recorded under the old per-report-path scheme still count."""
        with tempfile.TemporaryDirectory() as tmp:
            legacy = [{"at": "2026-01-01 00:00:00 UTC", "root": "/repo",
                       "mode": "repo", "counts": {"minor": 9}}]
            with mock.patch.object(reports, "_history_dir",
                                   return_value=Path(tmp)):
                with mock.patch.object(reports, "_legacy_history",
                                       return_value=legacy):
                    back = reports._read_history("/repo", "repo")
        self.assertEqual([e["counts"] for e in back], [{"minor": 9}])


class Comparison(unittest.TestCase):
    def payload(self, total, by_rule, history):
        return {
            "generated": "2026-01-02 00:00:00 UTC",
            "root": "/repo", "mode": "repo",
            "summary": {"total": total, "distinct_problems": len(by_rule)},
            "problems": [{"rule": name} for name in by_rule],
            "by_rule": [{"rule": name, "count": count}
                        for name, count in by_rule.items()],
            "history": history,
        }

    def previous(self, total, rule_counts):
        return {"at": "2026-01-01 00:00:00 UTC", "root": "/repo",
                "mode": "repo", "counts": {"minor": total},
                "distinct": len(rule_counts),
                "rules": sorted(rule_counts),
                "rule_counts": dict(rule_counts)}

    def test_no_previous_run_means_no_comparison(self):
        payload = self.payload(5, {"a": 5}, history=[])
        self.assertIsNone(reports.compare_runs(payload))

    def test_places_corrected_counts_the_work_done(self):
        previous = self.previous(70, {"image-alt": 5, "html-lang": 5})
        payload = self.payload(67, {"image-alt": 2, "html-lang": 5},
                               history=[previous, {"at": "now"}])
        comparison = reports.compare_runs(payload)
        self.assertEqual(comparison["places_fixed"], 3)
        self.assertEqual(comparison["places_added"], 0)
        self.assertEqual([r["rule"] for r in comparison["moved_rules"]],
                         ["image-alt"])

    def test_a_rule_that_stopped_firing_is_named(self):
        previous = self.previous(10, {"image-alt": 5, "html-lang": 5})
        payload = self.payload(5, {"html-lang": 5},
                               history=[previous, {"at": "now"}])
        comparison = reports.compare_runs(payload)
        self.assertEqual(comparison["solved_rules"], ["image-alt"])
        self.assertEqual(comparison["new_rules"], [])

    def test_an_older_run_without_rule_detail_claims_nothing(self):
        """The previous run recorded totals only.

        Comparing rule sets against nothing would announce every rule as
        brand new - a confident statement about data we do not have.
        """
        previous = {"at": "2026-01-01 00:00:00 UTC", "root": "/repo",
                    "mode": "repo", "counts": {"minor": 70}}
        payload = self.payload(70, {"image-alt": 5},
                               history=[previous, {"at": "now"}])
        comparison = reports.compare_runs(payload)
        self.assertFalse(comparison["comparable_rule_set"])
        self.assertEqual(comparison["new_rules"], [])
        self.assertEqual(comparison["moved_rules"], [])

    def test_document_is_not_written_without_a_previous_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changes.md"
            wrote = reports.write_comparison_document(
                path, self.payload(5, {"a": 5}, history=[]))
        self.assertFalse(wrote)
        self.assertFalse(path.exists())

    def test_document_says_what_was_corrected(self):
        previous = self.previous(70, {"image-alt": 5})
        payload = self.payload(67, {"image-alt": 2},
                               history=[previous, {"at": "now"}])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changes.md"
            self.assertTrue(reports.write_comparison_document(path, payload))
            text = path.read_text(encoding="utf-8")
        self.assertIn("3 place(s) corrected", text)
        self.assertIn("`image-alt`", text)


class ProblemsSection(unittest.TestCase):
    def test_markdown_lists_each_problem_once_with_its_places(self):
        payload = {
            "root": "/repo", "mode": "repo",
            "generated": "2026-01-02 00:00:00 UTC",
            "summary": {"counts": {"critical": 5}, "total": 5,
                        "distinct_problems": 1, "documents": 5,
                        "documents_with_findings": 5, "rules_triggered": 1},
            "problems": [{
                "rule": "image-alt", "severity": "critical",
                "category": "accessibility", "engine": "static",
                "title": "Image with no alt", "found": "found",
                "why": "why", "fix": "fix", "ready_fix": "",
                "snippet": "<img>", "selector": "",
                "occurrences": 5,
                "places": [f"p{i}.html:5" for i in range(5)],
            }],
            "by_rule": [{"rule": "image-alt", "count": 5,
                         "severity": "critical",
                         "category": "accessibility",
                         "title": "t", "fix": "f", "where": []}],
            "files": [], "history": [], "changed_this_run": {},
            "ai_patterns": {}, "typography": {},
        }
        text = reports._report_markdown(payload, "en")
        self.assertEqual(text.count("Image with no alt"), 1)
        self.assertIn("5×", text)
        self.assertIn("p4.html:5", text)
        # Both counts, because they answer different questions.
        self.assertIn("distinct problems", text)


if __name__ == "__main__":
    unittest.main()


class BriefingPageIndex(unittest.TestCase):
    """The index of examined pages is context, not content.

    On a 192-page crawl it was 192 numbered lines before the first finding -
    a table of contents burying the thing the reader opened the file for.
    """

    def _payload(self, pages):
        return {
            "root": "https://example.com", "mode": "web",
            "generated": "2026-08-24 11:36:30 UTC",
            "summary": {"counts": {"critical": 1}, "total": 1,
                        "distinct_problems": 1, "documents": pages,
                        "documents_with_findings": pages,
                        "rules_triggered": 1},
            "problems": [], "by_rule": [],
            "files": [{"source": f"https://example.com/page-{i}",
                       "findings": [{}] * i, "error": ""}
                      for i in range(pages)],
            "history": [], "changed_this_run": {},
            "ai_patterns": {}, "typography": {},
        }

    def _render(self, pages):
        from cli_impl.reports import _report_markdown

        return _report_markdown(self._payload(pages), "en")

    def test_it_is_a_table_not_a_numbered_list(self):
        text = self._render(5)
        self.assertIn("| page or file | findings |", text)
        self.assertNotIn("1. https://example.com/page-", text)

    def test_a_large_crawl_is_cut_short(self):
        text = self._render(200)
        self.assertIn("and 160 more", text)
        self.assertEqual(text.count("https://example.com/page-"), 40)

    def test_what_survives_the_cut_is_what_matters(self):
        """Truncating is only acceptable if the worst pages are what stay."""
        text = self._render(200)
        self.assertIn("page-199", text)

    def test_the_full_count_survives_the_truncation(self):
        self.assertIn("Pages examined (200)", self._render(200))

    def test_one_address_is_one_row(self):
        """A page is several documents - its own rules, its headers, an
        image's provenance. Measured on a live site: a four-page crawl was
        listed as nine pages, the home page three times with three counts."""
        from cli_impl.reports import _report_markdown

        payload = self._payload(1)
        payload["files"] = [
            {"source": "https://example.com/page-0", "findings": [{}, {}],
             "error": ""},
            {"source": "https://example.com/page-0", "findings": [{}],
             "error": ""},
            {"source": "https://example.com/other", "findings": [{}],
             "error": ""},
        ]
        text = _report_markdown(payload, "en")
        self.assertIn("Pages examined (2)", text)
        self.assertEqual(text.count("| [page-0](https://example.com/page-0) |"), 1)
        self.assertIn("| [page-0](https://example.com/page-0) | 3 |", text)

    def test_a_page_that_failed_is_listed_before_the_rest(self):
        from cli_impl.reports import _report_markdown

        payload = self._payload(3)
        payload["files"].append({"source": "https://example.com/broken",
                                 "findings": [], "error": "fetch failed"})
        text = _report_markdown(payload, "en")
        self.assertIn("*error: fetch failed*", text)


if __name__ == "__main__":
    unittest.main()


class GeneratedIdentifiersDoNotSplitAProblem(unittest.TestCase):
    """A theme that stamps a unique id per page turns one bug into ten.

    WordPress writes `aria-controls="page-toc-panel-6a8c2c05ce8bd"`. The
    markup then differs on every page while describing one broken component
    in one template, and a live ten-page crawl reported it as ten separate
    critical findings - the inflation grouping exists to remove, in a
    different disguise.
    """

    class _Issue:
        def __init__(self, snippet, source):
            self.rule_id = "axe:aria-allowed-attr"
            self.category = "accessibility"
            self.severity = "critical"
            self.snippet = snippet
            self.selector = ""
            self.source = source
            self.line = None

    def _toc(self, suffix, page):
        return self._Issue(
            f'<span class="page-toc__toggle" aria-expanded="true" '
            f'aria-controls="page-toc-panel-{suffix}">', page)

    def test_one_component_is_one_problem(self):
        from duplicates import group_issues

        issues = [self._toc(s, f"p{i}.html") for i, s in enumerate(
            ("6a8c2c05ce8bd", "6a8c2c534c8eb", "6a8c2c7063e18", "6a8c2ca11f22"))]
        self.assertEqual(len(group_issues(issues)), 1)

    def test_every_place_is_still_named(self):
        """Nothing is dropped: a fix has to visit each page."""
        from duplicates import group_issues, places_of

        issues = [self._toc(s, f"p{i}.html") for i, s in enumerate(
            ("6a8c2c05ce8bd", "6a8c2c534c8eb", "6a8c2c7063e18"))]
        first, others = group_issues(issues)[0]
        self.assertEqual(len(places_of(first, others)), 3)

    def test_genuinely_different_elements_stay_apart(self):
        """Over-masking would hide a real problem behind a merged one."""
        from duplicates import group_issues

        issues = [self._Issue('<span class="page-toc__toggle">', "a.html"),
                  self._Issue('<button class="nav-link">', "a.html")]
        self.assertEqual(len(group_issues(issues)), 2)

    def test_short_numbers_are_meaningful_and_kept(self):
        """`col-6` and `h2` are structure, not machine noise."""
        from duplicates import mask_generated_ids

        self.assertEqual(mask_generated_ids('<div class="col-6"><h2>'),
                         '<div class="col-6"><h2>')

    def test_a_uuid_is_masked_whole(self):
        from duplicates import mask_generated_ids

        masked = mask_generated_ids(
            'id="a3f1b2c4-5d6e-7f80-91a2-b3c4d5e6f708"')
        self.assertEqual(masked, 'id="#"')

    def test_a_long_digit_run_is_masked(self):
        from duplicates import mask_generated_ids

        self.assertEqual(mask_generated_ids('data-post="128374"'),
                         'data-post="#"')

    def test_empty_markup_is_left_alone(self):
        from duplicates import mask_generated_ids

        self.assertEqual(mask_generated_ids(""), "")


class MeasurementsAreNotWork(unittest.TestCase):
    """A timing that moved is not a defect that was fixed.

    A live pair of runs reported "**11 place(s) corrected**" when nothing had
    been touched: `perf-first-paint` fired on ten pages in the first run and
    none in the second, because the second hit a warm cache. That is the one
    thing a progress document must never get wrong.
    """

    def _payload(self, now_counts, before_counts, measured=()):
        return {
            "root": "https://example.com", "mode": "web",
            "generated": "2026-08-24 12:00:00 UTC",
            "summary": {"counts": {"critical": 1}, "total": sum(now_counts.values()),
                        "distinct_problems": len(now_counts), "documents": 10,
                        "documents_with_findings": 10,
                        "rules_triggered": len(now_counts)},
            "problems": [], "files": [], "changed_this_run": {},
            "ai_patterns": {}, "typography": {},
            "measured_rules": sorted(measured),
            "by_rule": [{"rule": r, "count": c, "severity": "minor",
                         "category": "performance", "title": "t", "fix": "f",
                         "where": []} for r, c in now_counts.items()],
            # Two entries: `_previous_run` drops the last one as this run's
            # own, so a single-entry history has no previous run at all.
            "history": [
                {"at": "2026-08-24 11:00:00 UTC",
                 "root": "https://example.com", "mode": "web",
                 "counts": {"minor": sum(before_counts.values())},
                 "rules": sorted(before_counts),
                 "rule_counts": dict(before_counts),
                 "measured_rules": sorted(measured),
                 "distinct": len(before_counts)},
                {"at": "2026-08-24 12:00:00 UTC",
                 "root": "https://example.com", "mode": "web",
                 "counts": {"minor": sum(now_counts.values())},
                 "rules": sorted(now_counts),
                 "rule_counts": dict(now_counts),
                 "measured_rules": sorted(measured),
                 "distinct": len(now_counts)},
            ],
        }

    def test_a_measurement_that_moved_is_not_counted_as_corrected(self):
        from cli_impl.reports import compare_runs

        result = compare_runs(self._payload(
            now_counts={"perf-first-paint": 0, "image-alt": 5},
            before_counts={"perf-first-paint": 10, "image-alt": 5},
            measured={"perf-first-paint"}))
        self.assertEqual(result["places_fixed"], 0)

    def test_a_real_fix_is_still_counted(self):
        from cli_impl.reports import compare_runs

        result = compare_runs(self._payload(
            now_counts={"image-alt": 2},
            before_counts={"image-alt": 5},
            measured={"perf-first-paint"}))
        self.assertEqual(result["places_fixed"], 3)

    def test_the_measurement_is_reported_rather_than_hidden(self):
        """Suppressing it would be its own lie: the number did change."""
        from cli_impl.reports import compare_runs

        result = compare_runs(self._payload(
            now_counts={"perf-first-paint": 0},
            before_counts={"perf-first-paint": 10},
            measured={"perf-first-paint"}))
        self.assertEqual(len(result["moved_measurements"]), 1)
        self.assertEqual(result["moved_rules"], [])

    def test_the_document_says_why_they_are_listed_apart(self):
        from cli_impl.reports import _comparison_lines, compare_runs

        text = "\n".join(_comparison_lines(compare_runs(self._payload(
            now_counts={"perf-first-paint": 0},
            before_counts={"perf-first-paint": 10},
            measured={"perf-first-paint"}))))
        self.assertIn("Measurements that moved", text)
        self.assertIn("counted as corrections", text)
        self.assertIn("0 place(s) corrected", text)

    def test_a_rule_measured_in_either_run_counts_as_measured(self):
        """The previous run may predate the marker, or the rule may not have
        fired this time - either way it is still a measurement."""
        from cli_impl.reports import compare_runs

        payload = self._payload(
            now_counts={"perf-load-time": 0},
            before_counts={"perf-load-time": 1},
            measured=())
        payload["history"][0]["measured_rules"] = ["perf-load-time"]
        self.assertEqual(compare_runs(payload)["places_fixed"], 0)
