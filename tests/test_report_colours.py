"""What the styled report's colours mean, and what it must never cut off.

Two questions this file answers, both of which the report got wrong before
the scheme in `report/markup.py` existed:

* **Does a colour mean one thing?** Red and green are the direction of a
  diff. If an element role ever borrowed one of them, a `<video>` tag would
  read as "this is the fix", and the one visual convention every developer
  already knows would stop being reliable in the one document where it is
  load-bearing.
* **Is anything printed with its end missing?** A report is paper. Clipping
  belongs to surfaces that have one line to draw in, and every clip that
  reached this document was one a reader could not undo from any surface.
"""
import re
import unittest

from audit.base import Issue
from audit.explanations import ROW_LIMIT, one_line, render
from report.markup import (
    FALLBACK_ROLE, ROLES, ROLE_LABELS, element_of, highlight, role_css,
    role_of, roles_used,
)
from report.model import ReportFinding, ReportMeta, ReportModel
from report.template import render_html
from ui.tokens import palettes


class TheColoursComeFromTheDesignBundle(unittest.TestCase):
    """Not from the web palette, and not from a hex typed into a template."""

    def test_the_report_paints_with_the_xaudit_overlay(self):
        html = render_html(_model(), lang="en")
        overlay = palettes(overlay=True)["light"]
        web = palettes(overlay=False)["light"]
        self.assertIn(overlay.sev_critical, html)
        self.assertNotIn(web.sev_critical, html)

    def test_every_role_ink_is_a_palette_token(self):
        palette = palettes(overlay=True)["light"]
        for role, (_tags, ink) in ROLES.items():
            with self.subTest(role):
                self.assertTrue(hasattr(palette, ink))
                self.assertIn(getattr(palette, ink), role_css(palette))

    def test_no_role_borrows_the_diff_s_red_or_green(self):
        """The reserved pair. A role inked in either would make "before" and
        "after" stop meaning before and after."""
        palette = palettes(overlay=True)["light"]
        reserved = {palette.error_text.lower(), palette.success_text.lower()}
        for role, (_tags, ink) in ROLES.items():
            with self.subTest(role):
                self.assertNotIn(getattr(palette, ink).lower(), reserved)

    def test_the_six_roles_are_six_different_colours(self):
        palette = palettes(overlay=True)["light"]
        inks = [getattr(palette, ink).lower() for _t, ink in ROLES.values()]
        self.assertEqual(len(set(inks)), len(inks))

    def test_every_role_is_named_in_all_three_languages(self):
        for lang, names in ROLE_LABELS.items():
            with self.subTest(lang):
                self.assertEqual(set(names), set(ROLES))


class TheElementScheme(unittest.TestCase):

    def test_a_tag_belongs_to_exactly_one_role(self):
        seen: dict = {}
        for role, (tags, _ink) in ROLES.items():
            for tag in tags:
                self.assertNotIn(tag, seen, f"{tag} is in {seen.get(tag)} too")
                seen[tag] = role

    def test_an_unknown_element_is_a_wrapper_not_a_seventh_colour(self):
        self.assertEqual(role_of("my-widget"), FALLBACK_ROLE)

    def test_case_and_namespace_do_not_change_the_role(self):
        self.assertEqual(role_of("BUTTON"), role_of("button"))
        self.assertEqual(role_of("svg:path"), role_of("path"))

    def test_the_element_is_read_off_the_markup_first(self):
        self.assertEqual(element_of("<img src=x>", "div.wrap"), "img")

    def test_a_selector_answers_only_when_the_markup_cannot(self):
        self.assertEqual(element_of("", "header > button.search"), "button")

    def test_a_classes_only_selector_yields_nothing_rather_than_a_guess(self):
        self.assertEqual(element_of("", "#container > .element-1.tier-1"), "")


class QuotedMarkupIsInkedNotRewritten(unittest.TestCase):

    def test_the_tag_name_carries_its_role_and_the_attributes_do_not(self):
        out = highlight('<a href="/x">go</a>')
        self.assertIn('<span class="t-control">a</span>', out)
        self.assertIn('<span class="a-name">href</span>', out)
        self.assertIn('<span class="a-value">&quot;/x&quot;</span>', out)

    def test_prose_with_no_markup_comes_back_as_plain_escaped_text(self):
        """An AI-text finding quotes a sentence. Painting a sentence as
        though a colour in it meant something would be a lie about it."""
        self.assertEqual(highlight("a & b < c"), "a &amp; b &lt; c")

    def test_nothing_survives_as_live_markup(self):
        out = highlight('<img src=x onerror=alert(1)>')
        stripped = re.sub(r"</?span[^>]*>", "", out)
        self.assertEqual(stripped, "&lt;img src=x onerror=alert(1)&gt;")

    def test_a_quoted_attribute_value_may_contain_a_closing_bracket(self):
        out = highlight('<div style="a:url(data:image/svg+xml,<x>)">t</div>')
        stripped = re.sub(r"</?span[^>]*>", "", out)
        self.assertNotIn("<", stripped)

    def test_the_legend_names_only_the_roles_the_report_contains(self):
        findings = [_finding(element="img"), _finding(element="button")]
        self.assertEqual(roles_used(findings), ["control", "media"])


class TheDiffHasADirection(unittest.TestCase):

    def test_what_is_there_and_what_should_be_are_not_the_same_ink(self):
        model = _model(snippet="<b>x</b>", replacement="<strong>x</strong>")
        html = render_html(model, lang="en")
        self.assertIn("snip-found", html)
        self.assertIn("snip-fix", html)
        palette = palettes(overlay=True)["light"]
        self.assertIn(f"pre.snip-found {{ border-left-color: {palette.error_text}",
                      html)
        self.assertIn(f"pre.snip-fix {{ border-left-color: {palette.success_text}",
                      html)


class NothingIsRounded(unittest.TestCase):
    """A radius says "widget". This is a printed technical document."""

    def test_the_document_declares_no_border_radius_at_all(self):
        html = render_html(_model(snippet="<b>x</b>"), lang="en")
        self.assertNotIn("border-radius", html)


class OneRampEverywhere(unittest.TestCase):

    def test_the_totals_and_the_chart_ink_a_rank_the_same(self):
        """They were two maps: "serious" drew orange in the bar and amber in
        the card counting it, so the two halves of one overview disagreed
        about how bad the same pile was."""
        palette = palettes(overlay=True)["light"]
        model = ReportModel(meta=_meta(), findings=[
            _finding(severity="critical"), _finding(severity="serious"),
        ])
        html = render_html(model, lang="en")
        self.assertIn(f'border-top-color:{palette.sev_high}', html)
        self.assertIn(f'background:{palette.sev_high}', html)
        self.assertNotIn(palette.amber, html.split("<body>")[1])


class TheDocumentHasAGutterInBothMedia(unittest.TestCase):
    """A report is read on a screen before it is ever printed.

    The paper side changed shape 2026-09-01: `@page` went to `margin: 0` so
    the tinted background bleeds to the sheet edge, and the gutter the text
    needs became `body` padding under `@media print`. `report/pdf.py` passes
    a zero `QMarginsF` for the same reason - a page-layout margin there is
    outside the page box and prints a white band around the tint.

    One thing measured while these tests were brought back in line, and
    worth knowing before the shape changes again: a **CSS** `@page` margin
    does *not* cost the bleed. Rendering the same document both ways through
    `render_pdf` and reading the content streams, each variant paints the
    same full-sheet rectangle (0 0 794 1123). So the choice between the two
    is about where the vertical gutter comes from, not about the tint:
    `body` padding indents the first page only, because padding applies to
    the flow and not to each sheet, while a `@page` margin insets every
    page. The horizontal gutter is identical either way.
    """

    def test_the_page_box_is_the_whole_sheet_so_the_tint_bleeds(self):
        html = render_html(_model(), lang="en")
        self.assertIn("@page { size: A4; margin: 0; }", html)

    def test_the_text_gutter_is_body_padding_in_both_media(self):
        html = render_html(_model(), lang="en")
        screen = html.split("@media screen {")[1].split("}")[0]
        self.assertIn("padding:", screen)
        self.assertIn("@media print { body { padding: 0 18mm;", html)


class SeverityIsAMarkNotAWash(unittest.TestCase):

    def test_the_panel_is_the_neutral_tone_whatever_the_severity(self):
        palette = palettes(overlay=True)["light"]
        html = render_html(_model(), lang="en")
        self.assertIn(f"background: {palette.bg_muted}", html)
        # The class that used to paint both the badge and the panel now
        # paints only the badge - so it is scoped to `.badge`.
        for rank in range(4):
            with self.subTest(rank=rank):
                self.assertNotIn(f"\n.sev-{rank} {{", html)
                self.assertIn(f".badge.sev-{rank} {{", html)

    def test_the_rank_still_shows_as_a_rule_down_the_edge(self):
        palette = palettes(overlay=True)["light"]
        html = render_html(_model(), lang="en")
        self.assertIn(f".finding.rule-0 {{ border-left: 1.2mm solid "
                      f"{palette.sev_critical}", html)


class NothingIsPrintedWithItsEndMissing(unittest.TestCase):

    def test_an_engine_sentence_reaches_the_report_whole(self):
        long_help = ("This element has insufficient contrast at this "
                     "conformance level. Expected a contrast ratio of at "
                     "least 4.5:1, but text in this element has a contrast "
                     "ratio of 3.09:1. Recommendation: change background to "
                     "#767676.")
        self.assertGreater(len(long_help), ROW_LIMIT)
        issue = Issue(rule_id="axe:color-contrast", severity="serious",
                      selector="p", snippet="<p>x</p>",
                      details={"engine": "axe-core", "help": long_help,
                               "rule": "color-contrast"})
        self.assertEqual(render(issue, "en").title, long_help)

    def test_a_surface_with_one_line_still_gets_one_line(self):
        """The clip did not disappear - it moved to the callers that have a
        line to fill, which is where it belonged."""
        clipped = one_line("x" * 400)
        self.assertEqual(len(clipped), ROW_LIMIT)
        self.assertTrue(clipped.endswith("…"))

    def test_a_ranked_row_gives_its_label_a_whole_line(self):
        html = render_html(_model(), lang="en")
        self.assertNotIn(".rank-label { flex:", html)
        self.assertIn(".rank-label { display: block;", html)
        self.assertNotIn("text-overflow: ellipsis; }\n.rank-track", html)


class TheTechnicalIdentityIsPrinted(unittest.TestCase):
    """Which check produced a row. It was in the JSON and nowhere a person
    reading the printed report could see it."""

    def test_the_rule_id_engine_and_element_are_on_the_page(self):
        finding = _finding(rule_id="axe:button-name", engine="axe",
                           element="button")
        html = render_html(ReportModel(meta=_meta(), findings=[finding]),
                           lang="en")
        self.assertIn("axe:button-name", html)
        self.assertIn('<span class="elem t-control">&lt;button&gt;</span>', html)

    def test_two_checks_with_one_sentence_stay_two_findings(self):
        """A group prints one rule id above all its occurrences, so a group
        that merged two rule ids would print a fact wrong for half of them."""
        model = ReportModel(meta=_meta(), findings=[
            _finding(rule_id="axe:color-contrast", location="a"),
            _finding(rule_id="htmlcs:1_4_3", location="b"),
        ])
        self.assertEqual(len(model.grouped_findings()), 2)


# ------------------------------------------------------------------ helpers

def _meta() -> ReportMeta:
    return ReportMeta(target="t", mode="audit-web")


def _finding(**kwargs) -> ReportFinding:
    fields = dict(title="a finding", category="accessibility",
                  severity="critical", location="https://example.com/")
    fields.update(kwargs)
    return ReportFinding(**fields)


def _model(**kwargs) -> ReportModel:
    return ReportModel(meta=_meta(), findings=[_finding(**kwargs)])


if __name__ == "__main__":
    unittest.main()
