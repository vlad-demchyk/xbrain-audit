"""The report's performance section is a summary, not a line per page.

A hundred-page SharePoint run printed a hundred lines of `address: lab;
1440×900; CPU/network: unthrottled; LCP …; CLS …; INP unknown (…)` in the
PDF. The reader needs how many pages, the median and the worst, and which
pages are worst by name; the per-page numbers stay in the JSON.
"""
from __future__ import annotations

import unittest

from audit.vitals import performance_lines, performance_summary
from report.model import page_label

SITE = "https://contoso.sharepoint.com/sites/ExampleSite"


def _page(name, lcp, cls):
    return {"source": f"{SITE}/SitePages/{name}.aspx", "measurements": {
        "conditions": {"viewport": {"width": 1440, "height": 900},
                       "cpu": {"throttling": "none"}, "network": {"throttling": "none"}},
        "vitals": {"LCP": {"status": "checked", "value": lcp},
                   "CLS": {"status": "checked", "value": cls},
                   "INP": {"status": "unknown", "reason": "no measured interactions"}}}}


COVERAGE = {"performance": [_page(f"Page{n}", 1000 + 100 * n, n / 100) for n in range(40)]
            + [_page("Home", 9000, 0.5)]}


class PerformanceSummary(unittest.TestCase):
    def _lines(self, lang="it"):
        return performance_summary(COVERAGE, lang, label=lambda url: page_label(url, SITE))

    def test_a_few_lines_whatever_the_number_of_pages(self):
        title, lines = self._lines()
        self.assertEqual(title, "Prestazioni")
        self.assertLessEqual(len(lines), 6)
        self.assertGreater(len(performance_lines(COVERAGE, "it")[1]), 40)
        self.assertFalse(any(SITE in line for line in lines))

    def test_median_worst_and_the_worst_pages_by_name(self):
        _title, lines = self._lines()
        self.assertEqual(lines[0], "Pagine misurate: 41 · misura di laboratorio, 1440×900, "
                                   "nessun limite CPU/rete")
        lcp = next(line for line in lines if line.startswith("LCP"))
        self.assertIn("mediana 3000 ms", lcp)
        self.assertIn("peggiore 9000 ms", lcp)
        self.assertIn("Più lente: Home (9000 ms), Page39 (4900 ms), Page38 (4800 ms)", lcp)
        cls = next(line for line in lines if line.startswith("CLS"))
        self.assertIn("peggiore 0.5", cls)
        self.assertIn("Home (0.5)", cls)

    def test_inp_is_one_line_with_why(self):
        _title, lines = self._lines()
        self.assertIn("INP: non misurato su 41 pagine (nessuna interazione misurata)", lines)
        _title, english = self._lines("en")
        self.assertIn("INP: not measured on 41 pages (no measured interactions)", english)

    def test_the_styled_report_prints_the_summary(self):
        from audit.base import Issue
        from audit.engine import AccessibilityResult, DocumentReport
        from report.model import from_accessibility
        from report.template import render_html

        result = AccessibilityResult(root=SITE, mode="web", documents=[DocumentReport(
            source=f"{SITE}/SitePages/Home.aspx",
            issues=[Issue("image-alt", "serious", snippet="<img>",
                          source=f"{SITE}/SitePages/Home.aspx")])])
        model = from_accessibility(result, "it")
        model.coverage = COVERAGE
        html = render_html(model, "it")
        section = html.split("<h2>Prestazioni</h2>")[1].split("</section>")[0]
        self.assertEqual(section.count("<li>"), len(self._lines()[1]))
        self.assertNotIn("Page12", section)


if __name__ == "__main__":
    unittest.main()
