"""The styled report: `report/model.py`, `report/template.py`,
`report/pdf.py` and `report/export.py`.

Three layers, tested at the level each one actually promises:

* the model adapters are plain Python — no Qt, no I/O — so they are checked
  against hand-built `AnalysisResult` / `RepoAnalysisResult` /
  `AccessibilityResult` objects, the same way `tests/test_audit.py` checks
  `analyze_document` against hand-built markup;
* the HTML template is checked as a string: the sections it must contain,
  and that anything user-controlled (a code snippet, a passage of "AI-
  sounding" prose) is escaped rather than interpreted as markup;
* the PDF path is checked with a real, offscreen `QWebEnginePage` render —
  mocking `printToPdf` would only prove the mock was called, not that a
  real page load followed by a real print produces real bytes. This is the
  one place in this module that needs Qt, so it follows the same
  `QT_QPA_PLATFORM=offscreen` setup as `tests/test_flow_layout.py` and the
  rest of this repo's headless Qt tests.
"""
from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import audit
from audit.base import Issue
from audit.engine import AccessibilityResult, DocumentReport
from models import (
    AnalysisResult, CodeBlock, Confidence, PageResult, RepoAnalysisResult,
    TextBlock, TextSpan,
)
from report.model import (
    CATEGORY_AI_TEXT, ReportFinding, ReportMeta, ReportModel,
    from_accessibility, from_text_analysis,
)
from report.template import render_html

try:
    from PySide6.QtWidgets import QApplication
    from report.pdf import PdfRenderer, render_pdf
    QT_AVAILABLE = True
except Exception:  # noqa: BLE001 - PySide6/QtWebEngine not installed
    QApplication = None
    QT_AVAILABLE = False


# --------------------------------------------------------------- model: text

class FromTextAnalysisWebMode(unittest.TestCase):
    """Building a `ReportModel` from an `AnalysisResult` (a crawled site)."""

    def setUp(self):
        self.block = TextBlock(
            block_id="b1", page_url="https://example.com/", dom_path="p:nth-of-type(1)",
            text="This solution leverages a robust framework to deliver value.",
        )
        span = TextSpan(
            block_id="b1", start=0, end=20, score=0.81, confidence=Confidence.HIGH,
            detector_name="offline", explanation="style-uniformity=0.9",
            details={"source": "style"},
        )
        page = PageResult(url="https://example.com/", depth=0, blocks=[self.block])
        self.result = AnalysisResult(root_url="https://example.com/",
                                     pages=[page], spans=[span])

    def test_the_flagged_text_becomes_a_finding(self):
        model = from_text_analysis(self.result)
        self.assertEqual(len(model.findings), 1)
        finding = model.findings[0]
        self.assertEqual(finding.category, CATEGORY_AI_TEXT)
        self.assertEqual(finding.severity, "high")
        self.assertEqual(finding.location, "https://example.com/")
        self.assertIn("This solution", finding.snippet)

    def test_meta_carries_the_root_url_and_mode(self):
        model = from_text_analysis(self.result)
        self.assertEqual(model.meta.target, "https://example.com/")
        self.assertEqual(model.meta.mode, "text-web")

    def test_low_confidence_is_dropped(self):
        low = TextSpan(block_id="b1", start=0, end=5, score=0.1,
                       confidence=Confidence.LOW, detector_name="offline")
        self.result.spans.append(low)
        model = from_text_analysis(self.result)
        self.assertEqual(len(model.findings), 1)  # still just the HIGH one

    def test_a_draft_becomes_the_replacement(self):
        key = ("b1", 0, 20)
        model = from_text_analysis(self.result, drafts={key: "This tool uses a framework."})
        self.assertEqual(model.findings[0].fix, "This tool uses a framework.")
        self.assertEqual(model.findings[0].replacement, "This tool uses a framework.")

    def test_a_span_with_no_matching_block_is_skipped_not_crashed_on(self):
        orphan = TextSpan(block_id="does-not-exist", start=0, end=1, score=0.9,
                          confidence=Confidence.HIGH, detector_name="offline")
        self.result.spans.append(orphan)
        model = from_text_analysis(self.result)
        self.assertEqual(len(model.findings), 1)


class FromTextAnalysisRepoMode(unittest.TestCase):
    """Building a `ReportModel` from a `RepoAnalysisResult` (a folder scan)."""

    def test_the_location_is_file_and_line(self):
        block = CodeBlock(block_id="c1", file_path="src/app.py", start=0, end=40,
                          text="# This solution leverages a framework", line_number=12)
        span = TextSpan(block_id="c1", start=2, end=38, score=0.5,
                        confidence=Confidence.MEDIUM, detector_name="offline",
                        explanation="cliche match")
        result = RepoAnalysisResult(root_dir="src", files=[], spans=[span])
        result.files = [type("F", (), {"blocks": [block], "path": "src/app.py",
                                       "error": None, "raw_text": block.text})()]
        model = from_text_analysis(result, target="src")
        self.assertEqual(len(model.findings), 1)
        self.assertEqual(model.findings[0].location, "src/app.py:12")
        self.assertEqual(model.meta.mode, "text-repo")
        self.assertEqual(model.meta.target, "src")


# ---------------------------------------------------------- model: audit

class FromAccessibility(unittest.TestCase):
    def setUp(self):
        # `import audit` (above) has already registered the real rules;
        # this constructs findings directly rather than running them, since
        # the adapter's job is to flatten `Issue`s, not to reproduce
        # `tests/test_audit.py`.
        issue = Issue(
            rule_id="img_alt_missing", severity="critical", selector="img:nth-of-type(1)",
            line=5, snippet='<img src="cat.jpg">', details={"src": "cat.jpg"},
            fix_snippet='<img src="cat.jpg" alt="...">', category=audit.ACCESSIBILITY,
            engine="static", source="index.html",
        )
        document = DocumentReport(source="index.html", issues=[issue], elements_checked=10)
        self.result = AccessibilityResult(root="index.html", mode="file",
                                          documents=[document], rules_run=["img_alt_missing"])

    def test_one_issue_becomes_one_finding(self):
        model = from_accessibility(self.result, lang="en")
        self.assertEqual(len(model.findings), 1)
        finding = model.findings[0]
        self.assertEqual(finding.severity, "critical")
        self.assertEqual(finding.category, audit.ACCESSIBILITY)
        self.assertIn("index.html", finding.location)
        self.assertIn("line 5", finding.location)
        self.assertTrue(finding.title)  # rendered via audit.explanations, not empty
        self.assertEqual(finding.replacement, '<img src="cat.jpg" alt="...">')

    def test_meta_carries_root_and_mode(self):
        model = from_accessibility(self.result)
        self.assertEqual(model.meta.target, "index.html")
        self.assertEqual(model.meta.mode, "audit-file")

    def test_a_rule_error_still_renders_a_row(self):
        broken = DocumentReport(source="broken.html", issues=[
            Issue(rule_id="whatever", severity="minor", source="broken.html",
                 details={"rule_error": "boom"}),
        ])
        result = AccessibilityResult(root="broken.html", mode="file", documents=[broken])
        model = from_accessibility(result)
        self.assertEqual(len(model.findings), 1)
        self.assertTrue(model.findings[0].found)


# -------------------------------------------------------------------- model

class ReportModelShape(unittest.TestCase):
    def test_counts_by_severity_and_category(self):
        model = ReportModel(meta=ReportMeta(target="x", mode="audit-file"), findings=[
            ReportFinding(title="a", category="accessibility", severity="critical", location="a"),
            ReportFinding(title="b", category="accessibility", severity="minor", location="b"),
            ReportFinding(title="c", category="seo", severity="critical", location="c"),
        ])
        self.assertEqual(model.counts_by_severity(), {"critical": 2, "minor": 1})
        self.assertEqual(model.counts_by_category(), {"accessibility": 2, "seo": 1})

    def test_sorted_findings_puts_the_worst_first(self):
        model = ReportModel(meta=ReportMeta(target="x", mode="audit-file"), findings=[
            ReportFinding(title="minor one", category="seo", severity="minor", location="z"),
            ReportFinding(title="critical one", category="seo", severity="critical", location="a"),
        ])
        self.assertEqual(model.sorted_findings()[0].title, "critical one")

    def test_unknown_severity_sorts_last_not_raising(self):
        model = ReportModel(meta=ReportMeta(target="x", mode="audit-file"), findings=[
            ReportFinding(title="mystery", category="seo", severity="who-knows", location="a"),
            ReportFinding(title="known", category="seo", severity="minor", location="b"),
        ])
        ordered = model.sorted_findings()
        self.assertEqual(ordered[-1].title, "mystery")


# ---------------------------------------------------------------- template

class HtmlTemplateContract(unittest.TestCase):
    def _model(self, **finding_kwargs):
        defaults = dict(title="a finding", category=CATEGORY_AI_TEXT, severity="high",
                        location="src/app.py:1", why="explanation", snippet="text",
                        replacement="")
        defaults.update(finding_kwargs)
        return ReportModel(meta=ReportMeta(target="my-project", mode="text-repo"),
                           findings=[ReportFinding(**defaults)])

    def test_a_valid_html_document(self):
        html = render_html(self._model(), lang="en")
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("<html", html)
        self.assertIn("</html>", html)
        self.assertIn("@page", html)  # print CSS, not a screen-only layout

    def test_the_page_has_no_margin_and_body_pads_only_inline(self):
        """The tint bleeds to the paper edge; only the text gets a gutter,
        and only left/right - see `report.template`'s docstring."""
        from report.template import CONTENT_PADDING_H_MM

        html = render_html(self._model(), lang="en")
        self.assertIn("@page { size: A4; margin: 0; }", html)
        self.assertIn(
            f"@media print {{ body {{ padding: 0 {CONTENT_PADDING_H_MM}mm;", html)

    def test_expected_sections_are_present(self):
        html = render_html(self._model(), lang="en")
        self.assertIn("Overview", html)
        self.assertIn("Findings", html)
        self.assertIn("my-project", html)

    def test_the_overview_opens_with_charts(self):
        """Counts in a table are exact and shapeless.

        A reader opening a report wants to see where the weight is before
        reading a number, and the bars are what answer that.
        """
        html = render_html(self._model(), lang="en")
        self.assertIn('class="charts"', html)
        self.assertIn("bar-fill", html)

    def test_the_charts_need_no_script_and_no_image(self):
        """`printToPdf` is the consumer; anything else prints blank."""
        html = render_html(self._model(), lang="en")
        chart = html[html.index('class="charts"'):]
        chart = chart[:chart.index("</section>")]
        self.assertNotIn("<script", chart)
        self.assertNotIn("<img", chart)
        self.assertNotIn("<canvas", chart)

    def test_what_was_found_is_one_table_not_several(self):
        """The category counts, the AI bands and the character tallies were
        three tables in three sections separated by the findings."""
        html = render_html(self._model(), lang="en")
        self.assertIn("What was found", html)
        self.assertIn("find-table", html)
        overview = html[html.index('class="summary"'):]
        overview = overview[:overview.index("</section>")]
        self.assertEqual(overview.count("<table"), 1)

    def test_cards_may_break_across_pages(self):
        """Forbidding it is what left a third of many pages blank: a card
        that did not fit moved to the next page whole."""
        html = render_html(self._model(), lang="en")
        self.assertIn("break-inside: auto", html)
        self.assertIn("orphans: 3", html)

    def test_headings_are_never_stranded_at_a_page_foot(self):
        html = render_html(self._model(), lang="en")
        self.assertIn("break-after: avoid", html)

    def test_a_table_row_is_never_split(self):
        html = render_html(self._model(), lang="en")
        self.assertIn("table.category-table tr { break-inside: avoid;", html)

    @staticmethod
    def _quoted(html: str) -> str:
        """Every `<pre>` block, with the highlighter's own spans removed.

        Quoted markup is inked tag by tag now (`report.markup.highlight`), so
        the escaped text of a snippet is no longer one contiguous run in the
        document - `&lt;` and `img` sit in two different spans. Stripping the
        spans and comparing the whole remainder is the stronger check anyway:
        it says the entire snippet survived escaping, where a substring test
        only ever said its first few characters did.
        """
        blocks = re.findall(r"<pre[^>]*>(.*?)</pre>", html, re.S)
        return "\n".join(re.sub(r"</?span[^>]*>", "", block) for block in blocks)

    def test_html_in_a_snippet_is_escaped_not_rendered(self):
        model = self._model(snippet='<img src=x onerror=alert(1)>',
                            found="<script>evil()</script>")
        html = render_html(model, lang="en")
        self.assertNotIn("<img src=x onerror=alert(1)>", html)
        self.assertNotIn("<script>evil()</script>", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", self._quoted(html))

    def test_a_replacement_is_also_escaped(self):
        model = self._model(replacement='<b onclick="x()">bold</b>')
        html = render_html(model, lang="en")
        self.assertNotIn('<b onclick="x()">bold</b>', html)
        self.assertIn("&lt;b onclick=&quot;x()&quot;&gt;bold&lt;/b&gt;",
                      self._quoted(html))

    def test_no_findings_still_renders_a_clean_document(self):
        empty = ReportModel(meta=ReportMeta(target="clean-repo", mode="text-repo"), findings=[])
        html = render_html(empty, lang="en")
        self.assertIn("clean-repo", html)
        self.assertIn("(0)", html)

    def test_localised_labels_switch_with_lang(self):
        html_en = render_html(self._model(), lang="en")
        html_uk = render_html(self._model(), lang="uk")
        html_it = render_html(self._model(), lang="it")
        self.assertIn("Findings", html_en)
        self.assertIn("Знахідки", html_uk)
        self.assertIn("Rilievi", html_it)

    def test_an_unknown_lang_falls_back_to_english(self):
        html = render_html(self._model(), lang="fr")
        self.assertIn("Findings", html)

    def test_a_long_snippet_wraps_instead_of_overflowing(self):
        html = render_html(self._model())
        self.assertIn("white-space: pre-wrap", html)
        self.assertIn("overflow-wrap: anywhere", html)

    def test_finding_cards_avoid_breaking_across_pages(self):
        html = render_html(self._model())
        self.assertIn(".finding {", html)
        self.assertIn("break-inside: avoid", html)

    def test_wcag_reference_is_shown_for_an_audit_finding(self):
        model = self._model(category="accessibility", severity="serious",
                            wcag=("1.1.1", "4.1.2"))
        html = render_html(model, lang="en")
        self.assertIn("1.1.1", html)
        self.assertIn("4.1.2", html)


# --------------------------------------------------------------- PDF render

@unittest.skipUnless(QT_AVAILABLE, "PySide6/QtWebEngine not available")
class PdfRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_a_small_document_renders_to_real_pdf_bytes(self):
        html = "<!doctype html><html><body><h1>hello</h1></body></html>"
        pdf_bytes = render_pdf(html)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 100)

    def test_a_real_report_model_renders_to_pdf(self):
        model = ReportModel(
            meta=ReportMeta(target="smoke-test", mode="text-repo"),
            findings=[ReportFinding(
                title="a flagged sentence", category=CATEGORY_AI_TEXT, severity="high",
                location="a.py:1", why="style-uniformity=0.9",
                snippet="This solution leverages a robust framework.",
            )],
        )
        pdf_bytes = render_pdf(render_html(model, lang="uk"))
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_a_renderer_can_be_reused_for_more_than_one_document(self):
        with PdfRenderer() as renderer:
            first = renderer.render("<html><body>one</body></html>")
            second = renderer.render("<html><body>two</body></html>")
        self.assertTrue(first.startswith(b"%PDF"))
        self.assertTrue(second.startswith(b"%PDF"))

    def test_printToPdf_gets_zero_page_margins(self):
        # Deliberate: the report's tinted background must bleed to the
        # physical page edge (see template.py's docstring and its
        # `@page { margin: 0 }`). The reader's gutter around the *text*
        # lives as horizontal-only CSS padding on `body` instead - a
        # non-zero margin here would print a band of plain white between
        # the paper's edge and the tint. Guards against reintroducing that,
        # by intercepting the layout `printToPdf` is actually called with.
        from unittest.mock import patch

        from PySide6.QtGui import QPageLayout
        from PySide6.QtWebEngineCore import QWebEnginePage

        captured = {}

        def fake_print_to_pdf(self, callback, layout):
            captured["layout"] = layout
            callback(b"%PDF-fake")

        with patch.object(QWebEnginePage, "printToPdf", fake_print_to_pdf):
            render_pdf("<!doctype html><html><body>x</body></html>")

        margins = captured["layout"].margins(QPageLayout.Unit.Millimeter)
        self.assertEqual(margins.left(), 0)
        self.assertEqual(margins.right(), 0)
        self.assertEqual(margins.top(), 0)
        self.assertEqual(margins.bottom(), 0)


# --------------------------------------------------------------- export.py

@unittest.skipUnless(QT_AVAILABLE, "PySide6/QtWebEngine not available")
class WriteStyledReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _model(self):
        return ReportModel(meta=ReportMeta(target="t", mode="text-repo"), findings=[
            ReportFinding(title="x", category=CATEGORY_AI_TEXT, severity="high", location="a.py:1"),
        ])

    def test_an_html_suffix_writes_html(self):
        import tempfile
        from pathlib import Path

        from report.export import write_styled_report

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            write_styled_report(str(path), self._model(), "en")
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("<!doctype html>"))

    def test_a_pdf_suffix_writes_a_real_pdf(self):
        import tempfile
        from pathlib import Path

        from report.export import write_styled_report

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.pdf"
            write_styled_report(str(path), self._model(), "en")
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertGreater(len(data), 0)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(QT_AVAILABLE, "PySide6/QtWebEngine not available")
class LostCallback(unittest.TestCase):
    """Qt occasionally takes the job and never calls back - about one
    full-suite run in three, on a document that renders in a third of a
    second by itself. Seen in both phases: `loadFinished` missing, and
    `printToPdf` missing. The renderer answers with exactly one retry
    against a fresh page, and only for a callback that never came - never
    for a load that answered "no"."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_a_lost_callback_is_retried_once(self):
        from report import pdf as pdf_module

        renderer = pdf_module.PdfRenderer()
        calls = []
        real = renderer._render_once

        def flaky(html, base_url=""):
            calls.append(html)
            if len(calls) == 1:
                raise pdf_module._CallbackLost("the printer did not answer")
            return real(html, base_url)

        renderer._render_once = flaky
        try:
            data = renderer.render("<html><body>one</body></html>")
        finally:
            renderer.close()
        self.assertEqual(len(calls), 2)
        self.assertTrue(data.startswith(b"%PDF"))

    def test_a_second_loss_is_reported_not_retried_forever(self):
        from report import pdf as pdf_module

        renderer = pdf_module.PdfRenderer()
        calls = []

        def always_lost(html, base_url=""):
            calls.append(html)
            raise pdf_module._CallbackLost("the printer did not answer")

        renderer._render_once = always_lost
        try:
            with self.assertRaises(RuntimeError) as caught:
                renderer.render("<html><body>one</body></html>")
        finally:
            renderer.close()
        self.assertEqual(len(calls), 2)
        # The caller sees a plain RuntimeError: `_PrintLost` is the retry's
        # own signal and must not escape as something callers could catch
        # separately and then retry a third time.
        self.assertNotIsInstance(caught.exception, pdf_module._CallbackLost)
        self.assertIsInstance(caught.exception, RuntimeError)

    def test_the_message_names_the_phase_that_went_quiet(self):
        """Which callback was lost is the only clue a user or a log has,
        and the two have different causes."""
        from report import pdf as pdf_module

        state = {"finished": False, "error": "boom", "pdf": None, "phase": "loading"}
        self.assertIn("loading", pdf_module._timeout_message(state))
        state["phase"] = "printing"
        self.assertIn("printer", pdf_module._timeout_message(state))


class ReportReadability(unittest.TestCase):
    """The layout complaints from a real 192-page report, as assertions.

    That report printed 192 numbered lines of index before the first finding,
    kept its four count-tables in four places separated by the findings, and
    left large blank areas wherever a card did not fit in what was left of a
    page.
    """

    def _model(self, pages=0, chars=0, ai=None):
        from report.model import ReportFinding, ReportMeta, ReportModel

        return ReportModel(
            meta=ReportMeta(target="https://example.com", mode="audit-web"),
            findings=[
                ReportFinding(title="Image without alt", category="accessibility",
                              severity="critical", location="a.html"),
                ReportFinding(title="Slow font", category="performance",
                              severity="minor", location="b.html"),
            ],
            pages=[{"source": f"https://example.com/page-{i}",
                    "findings_count": i} for i in range(pages)],
            ai_patterns=ai or {},
            typography={"total": sum(range(chars)),
                        "by_character": {f"char-{i}": i for i in range(chars)}}
            if chars else {})

    def test_the_page_index_is_a_table_in_small_type(self):
        html = render_html(self._model(pages=5), lang="en")
        self.assertIn("pages-table", html)
        self.assertIn("table.pages-table { font-size: 8pt;", html)

    def test_the_page_index_is_cut_short_rather_than_printed_in_full(self):
        html = render_html(self._model(pages=200), lang="en")
        self.assertIn("and 160 more pages", html)
        self.assertEqual(html.count("https://example.com/page-"), 40)

    def test_the_page_index_leads_with_the_worst_pages(self):
        """Cut short is only acceptable if what survives is what matters."""
        html = render_html(self._model(pages=200), lang="en")
        self.assertIn("page-199", html)
        self.assertNotIn("page-0<", html)

    def test_the_page_index_comes_after_the_findings(self):
        """It is context, not content, and it used to precede them."""
        html = render_html(self._model(pages=5), lang="en")
        self.assertGreater(html.index('class="pages"'),
                           html.index('class="findings"'))

    def test_the_page_count_is_still_stated_in_full(self):
        """Truncating the list must not truncate the fact."""
        html = render_html(self._model(pages=200), lang="en")
        self.assertIn("Pages examined (200)", html)

    def test_one_address_is_one_row_in_the_styled_report(self):
        """`report.model.page_index` is the owner; this is the other reader
        of it. A page is several documents, and the index is a list of
        pages."""
        from report.model import page_index

        model = self._model(pages=0)
        model.pages = page_index([
            {"source": "https://example.com/a", "findings_count": 2, "error": ""},
            {"source": "https://example.com/a", "findings_count": 1, "error": ""},
            {"source": "https://example.com/b", "findings_count": 1, "error": ""},
        ])
        html = render_html(model, lang="en")
        self.assertIn("Pages examined (2)", html)
        self.assertEqual(html.count("https://example.com/a"), 1)

    def test_no_page_index_when_nothing_was_crawled(self):
        self.assertNotIn('class="pages"', render_html(self._model(), lang="en"))

    def test_ai_bands_and_characters_join_the_one_table(self):
        model = self._model(chars=3, ai={"total": 9, "high": 2, "medium": 7})
        html = render_html(model, lang="en")
        table = html[html.index("find-table"):]
        table = table[:table.index("</table>")]
        for expected in ("Accessibility", "Performance", "Confidence: high",
                         "char-2"):
            self.assertIn(expected, table)

    def test_a_long_character_tally_is_summarised_rather_than_listed(self):
        html = render_html(self._model(chars=30), lang="en")
        table = html[html.index("find-table"):]
        table = table[:table.index("</table>")]
        self.assertIn("and 18 more", table)

    def test_the_top_patterns_table_keeps_only_what_a_tally_cannot_hold(self):
        """The confidence counts moved into the one table; the passages and
        their explanations are what is left, because they are not counts."""
        model = self._model(ai={"total": 2, "high": 2, "top_patterns": [
            {"score": 0.8, "confidence": "high", "text": "a passage",
             "explanation": "cliché: delve"}]})
        html = render_html(model, lang="en")
        self.assertIn("Highest-scoring passages", html)
        self.assertIn("a passage", html)

    def test_no_top_patterns_section_when_there_are_none(self):
        model = self._model(ai={"total": 3, "low": 3})
        self.assertNotIn("ai-patterns", render_html(model, lang="en"))

    def test_a_matched_repo_path_rides_inside_the_explanation_cell(self):
        """Not a fifth column: most reports have no `--repo` to show, and a
        column empty in every row but a few reads as a layout defect."""
        model = self._model(ai={"total": 1, "high": 1, "top_patterns": [
            {"score": 0.8, "confidence": "high", "text": "a passage",
             "explanation": "cliché: delve",
             "source_file": "/repo/hero.php", "source_line": 12}]})
        html = render_html(model, lang="en")
        start = html.index("ai-patterns")
        table = html[start:html.index("</table>", start)]
        self.assertIn("/repo/hero.php:12", table)
        # One <tr>, not two: the path is a line inside the explanation cell.
        self.assertEqual(table.count("<tr>"), 2)  # header row + the one finding

    def test_an_unmatched_passage_shows_no_source_line(self):
        model = self._model(ai={"total": 1, "high": 1, "top_patterns": [
            {"score": 0.8, "confidence": "high", "text": "a passage",
             "explanation": "cliché: delve"}]})
        html = render_html(model, lang="en")
        self.assertNotIn('class="src"', html)

    def test_repo_coverage_note_appears_only_when_repo_was_given(self):
        model = self._model(ai={"total": 2, "high": 2, "repo_matched": 1,
                                "repo_total": 2, "top_patterns": [
            {"score": 0.8, "confidence": "high", "text": "a", "explanation": "e"}]})
        html = render_html(model, lang="en")
        self.assertIn("Matched to the given repository: 1/2 passages", html)

    def test_no_repo_coverage_note_without_repo_total(self):
        model = self._model(ai={"total": 1, "high": 1, "top_patterns": [
            {"score": 0.8, "confidence": "high", "text": "a", "explanation": "e"}]})
        html = render_html(model, lang="en")
        # The class name is always in the stylesheet; the element it styles
        # must not be, for a report with nothing to say about coverage.
        self.assertNotIn('class="repo-coverage"', html)

    def test_every_language_renders_the_coverage_note_without_a_raw_placeholder(self):
        for lang in ("uk", "it", "en"):
            model = self._model(ai={"total": 1, "high": 1, "repo_matched": 1,
                                    "repo_total": 1, "top_patterns": [
                {"score": 0.8, "confidence": "high", "text": "a", "explanation": "e"}]})
            html = render_html(model, lang=lang)
            self.assertNotIn("{matched}", html)
            self.assertNotIn("{total}", html)

    def test_every_language_renders_the_new_sections(self):
        for lang in ("uk", "it", "en"):
            html = render_html(self._model(pages=3, chars=2), lang=lang)
            self.assertIn("find-table", html)
            self.assertIn("pages-table", html)
            self.assertNotIn("{count}", html)
