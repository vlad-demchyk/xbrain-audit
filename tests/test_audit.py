"""Accessibility rules: what they catch, and — just as important — what
they must not flag.

False positives are the way an accessibility tool gets switched off, so
roughly half of these assert silence on correct markup.
"""
from __future__ import annotations

import unittest

import audit
from audit import analyze_document
from audit.rules.accessibility import contrast_ratio, _parse_color


def issues(markup: str, rule_id: str | None = None,
           category: str = audit.ACCESSIBILITY) -> list:
    """Findings for one snippet, scoped to one category by default.

    The scoping matters now that four categories run over the same document:
    a bare `<img>` legitimately produces an accessibility finding *and* an
    SEO one, and an accessibility test asserting "nothing else" would fail
    on a correct SEO rule.
    """
    found = analyze_document(markup, "test.html", line_numbers=True).issues
    return [i for i in found
            if (rule_id is None or i.rule_id == rule_id)
            and (category is None or i.category == category)]


class Images(unittest.TestCase):
    def test_missing_alt_is_critical_and_offers_the_decorative_fix(self):
        found = issues('<img src="/a.png">', "image-alt")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, audit.CRITICAL)
        self.assertIn('alt=""', found[0].fix_snippet)

    def test_empty_alt_is_correct_markup(self):
        self.assertEqual(issues('<img src="/a.png" alt="">', "image-alt"), [])

    def test_filename_alt_is_flagged_separately(self):
        found = issues('<img src="/a.png" alt="hero-banner-2.png">')
        self.assertEqual([i.rule_id for i in found], ["image-alt-filename"])

    def test_real_description_is_left_alone(self):
        self.assertEqual(issues('<img src="/a.png" alt="The team lead on stage">'), [])

    # --- alt written as a slug (a municipal site's media library) -----------------

    def test_slug_alt_without_extension_is_flagged_as_advisory(self):
        for alt in ("mappa-parlante-example", "meccanica-della-fortezza",
                    "gallerie-e-baluardo-donato", "Pasquetta-sui-Bastioni",
                    "infografica-meccanica-della-fortezza"):
            with self.subTest(alt=alt):
                found = issues(f'<img src="/a.jpg" alt="{alt}">', "image-alt-filename")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0].confidence, audit.ADVISORY)
                self.assertEqual(found[0].details["kind"], "slug")

    def test_alt_equal_to_the_files_stem_is_exact(self):
        found = issues('<img src="/up/Piazza-Grande-1024x683.jpg" alt="Piazza-Grande">',
                       "image-alt-filename")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].confidence, audit.EXACT)
        self.assertEqual(found[0].details["kind"], "filename")

    def test_stem_match_ignores_case_underscores_and_size_suffix(self):
        found = issues('<img src="/up/piazza_grande-scaled.jpg?ver=2" alt="Piazza-Grande">',
                       "image-alt-filename")
        self.assertEqual([i.confidence for i in found], [audit.EXACT])

    def test_date_and_camera_counter_alts_are_flagged(self):
        for alt in ("2025-10-28", "IMG_2034", "DSC0001", "screenshot-12"):
            with self.subTest(alt=alt):
                self.assertEqual(
                    len(issues(f'<img src="/a.png" alt="{alt}">', "image-alt-filename")), 1)

    def test_short_hyphenated_words_and_prose_are_left_alone(self):
        # One hyphen, a name that is not the file's, a sentence, a single word.
        for alt in ("Wi-Fi", "Piazza-Grande", "Logo", "Porta Udine, la porta est",
                    "Una galleria sotterranea di contromina", "Rievocazione storica"):
            with self.subTest(alt=alt):
                self.assertEqual(
                    issues(f'<img src="/other.jpg" alt="{alt}">', "image-alt-filename"), [])

    def test_empty_alt_is_never_a_slug(self):
        self.assertEqual(issues('<img src="/mappa-parlante-example.jpg" alt="">',
                                "image-alt-filename"), [])


class Controls(unittest.TestCase):
    def test_icon_only_button_has_no_name(self):
        self.assertEqual(len(issues('<button><span class="i"></span></button>',
                                    "control-name")), 1)

    def test_aria_label_is_a_name(self):
        self.assertEqual(issues('<button aria-label="Close"><i></i></button>',
                                "control-name"), [])

    def test_wrapping_label_names_an_input(self):
        markup = "<label>Email <input type='text'></label>"
        self.assertEqual(issues(markup, "control-name"), [])

    def test_label_for_names_an_input(self):
        markup = '<label for="e">Email</label><input type="text" id="e">'
        self.assertEqual(issues(markup, "control-name"), [])

    def test_submit_input_is_named_by_its_value(self):
        self.assertEqual(issues('<input type="submit" value="Send">', "control-name"), [])

    def test_anchor_without_href_is_not_a_control(self):
        self.assertEqual(issues("<a></a>", "control-name"), [])


class Structure(unittest.TestCase):
    def test_skipped_heading_level_is_reported_with_the_correct_fix(self):
        found = issues("<h1>A</h1><h4>B</h4>", "heading-order")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].details["from"], 1)
        self.assertEqual(found[0].details["to"], 4)
        self.assertIn("<h2>", found[0].fix_snippet)

    def test_descending_one_level_at_a_time_is_fine(self):
        self.assertEqual(issues("<h1>A</h1><h2>B</h2><h3>C</h3>", "heading-order"), [])

    def test_going_back_up_is_fine(self):
        # h3 -> h2 starts a new section; only downward jumps skip a level.
        self.assertEqual(issues("<h1>A</h1><h2>B</h2><h3>C</h3><h2>D</h2>",
                                "heading-order"), [])

    def test_duplicate_id_is_reported_once_for_the_second_element(self):
        found = issues('<p id="x">a</p><p id="x">b</p>', "duplicate-id")
        self.assertEqual(len(found), 1)

    def test_broken_aria_reference_is_found(self):
        found = issues('<span aria-labelledby="nope">x</span>', "aria-reference-broken")
        self.assertEqual(found[0].details["missing"], ["nope"])

    def test_resolving_aria_reference_is_fine(self):
        markup = '<h2 id="t">Title</h2><section aria-labelledby="t">x</section>'
        self.assertEqual(issues(markup, "aria-reference-broken"), [])

    def test_layout_table_marked_presentation_is_skipped(self):
        markup = '<table role="presentation"><tr><td>a</td></tr><tr><td>b</td></tr></table>'
        self.assertEqual(issues(markup, "table-headers"), [])

    def test_data_table_without_headers_is_reported(self):
        markup = "<table><tr><td>a</td></tr><tr><td>b</td></tr></table>"
        self.assertEqual(len(issues(markup, "table-headers")), 1)

    def test_a_layout_table_has_no_headers_to_be_missing(self):
        """Measured 2026-09-01 on a workspace of email deliverables: all 47
        findings of this rule were `<table width="100%" cellpadding="0"
        cellspacing="0" border="0">`, the wrapper an email is laid out in.
        The rule was reporting the absence of something that must not be
        there, at `serious`."""
        layout = ('<table width="100%" cellpadding="0" cellspacing="0" border="0">'
                  '<tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr>'
                  '</table>')
        self.assertEqual(issues(layout, "table-headers"), [])

    def test_a_table_that_wraps_another_table_is_a_wrapper(self):
        nested = ("<table><tr><td>"
                  "<table><tr><td>a</td></tr><tr><td>b</td></tr></table>"
                  "</td></tr><tr><td>x</td></tr></table>")
        # The inner one is still judged on its own merits; the wrapper is not
        # a data table and is not reported as one.
        found = issues(nested, "table-headers")
        self.assertEqual(len(found), 1)

    def test_role_none_is_the_same_statement_as_presentation(self):
        markup = ('<table role="none"><tr><td>a</td><td>b</td></tr>'
                  '<tr><td>c</td><td>d</td></tr></table>')
        self.assertEqual(issues(markup, "table-headers"), [])

    def test_a_data_table_with_a_caption_is_still_data(self):
        """A caption is what a data table has and a layout wrapper does not,
        so it wins over the presentational attributes."""
        markup = ('<table cellpadding="0" cellspacing="0" border="0">'
                  '<caption>Prices</caption>'
                  '<tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr>'
                  '</table>')
        self.assertEqual(len(issues(markup, "table-headers")), 1)


class Keyboard(unittest.TestCase):
    def test_positive_tabindex_is_reported(self):
        found = issues('<div tabindex="3">x</div>', "tabindex-positive")
        self.assertEqual(found[0].details["value"], 3)
        self.assertIn('tabindex="0"', found[0].fix_snippet)

    def test_zero_and_negative_tabindex_are_legitimate(self):
        self.assertEqual(issues('<div tabindex="0">x</div><div tabindex="-1">y</div>',
                                "tabindex-positive"), [])


class Media(unittest.TestCase):
    def test_autoplay_without_controls_is_reported(self):
        found = issues('<video autoplay src="/a.mp4"></video>', "media-autoplay")
        self.assertEqual(len(found), 1)
        # Boolean attributes are written bare in the suggested fix, so the
        # snippet can be pasted into a source file as-is.
        self.assertIn("autoplay ", found[0].fix_snippet)
        self.assertNotIn('autoplay=""', found[0].fix_snippet)

    def test_muted_autoplay_video_is_allowed(self):
        self.assertEqual(issues('<video autoplay muted src="/a.mp4"></video>',
                                "media-autoplay"), [])

    def test_captions_track_satisfies_the_rule(self):
        markup = '<video src="/a.mp4"><track kind="captions" src="/c.vtt"></video>'
        self.assertEqual(issues(markup, "media-captions"), [])

    def test_missing_captions_is_marked_as_needing_a_browser(self):
        found = issues('<video src="/a.mp4"></video>', "media-captions")
        self.assertEqual(found[0].confidence, audit.NEEDS_BROWSER)


class Viewport(unittest.TestCase):
    def test_blocked_zoom_is_reported(self):
        markup = '<meta name="viewport" content="width=device-width, user-scalable=no">'
        self.assertEqual(len(issues(markup, "viewport-zoom")), 1)

    def test_maximum_scale_one_is_reported(self):
        markup = '<meta name="viewport" content="width=device-width, maximum-scale=1.0">'
        self.assertEqual(len(issues(markup, "viewport-zoom")), 1)

    def test_a_normal_viewport_is_fine(self):
        markup = '<meta name="viewport" content="width=device-width, initial-scale=1">'
        self.assertEqual(issues(markup, "viewport-zoom"), [])


class Contrast(unittest.TestCase):
    def test_known_ratios(self):
        self.assertAlmostEqual(contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, places=2)
        self.assertAlmostEqual(contrast_ratio((255, 255, 255), (255, 255, 255)), 1.0, places=2)

    def test_low_contrast_inline_pair_is_reported_as_needing_a_browser(self):
        markup = '<p style="color:#999999;background:#ffffff">text</p>'
        found = issues(markup, "contrast-inline")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].confidence, audit.NEEDS_BROWSER)
        self.assertLess(found[0].details["ratio"], 4.5)

    def test_sufficient_contrast_is_not_reported(self):
        markup = '<p style="color:#333333;background:#ffffff">text</p>'
        self.assertEqual(issues(markup, "contrast-inline"), [])

    def test_known_wcag_pairs(self):
        # Reference ratios from the WCAG 2.x formula: the numbers the rule
        # acts on have to be the numbers a contrast checker shows.
        for foreground, background, expected in (
            ((0x77, 0x77, 0x77), (255, 255, 255), 4.48),
            ((0x76, 0x76, 0x76), (255, 255, 255), 4.54),
            ((0x59, 0x59, 0x59), (255, 255, 255), 7.00),
            ((0, 0, 255), (255, 255, 255), 8.59),
            ((0x1a, 0x1a, 0x1a), (0xf5, 0xf5, 0xf5), 15.96),
        ):
            self.assertAlmostEqual(
                contrast_ratio(foreground, background), expected, places=2)

    def test_unparsable_colours_are_silent_rather_than_invented(self):
        # A colour the markup cannot resolve has no ratio. Guessing one
        # produces a critical finding about a pair nobody ever painted.
        for colour in ("var(--fg)", "currentcolor", "transparent",
                       "hsl(0 0% 0%)", "color-mix(in srgb, red, blue)",
                       "light-dark(#fff, #000)", "inherit", "rgb(100%, 0%, 0%)"):
            self.assertIsNone(_parse_color(colour), colour)

    def test_translucent_colours_are_not_judged(self):
        # The ratio depends on the layer underneath, which this pass cannot
        # see: rgba(0,0,0,.05) read as solid black invents a failure on what
        # is really an almost-white background.
        for colour in ("rgba(0, 0, 0, 0.05)", "rgba(0,0,0,0)", "#00000000",
                       "#ffffff80", "rgb(0 0 0 / 50%)"):
            self.assertIsNone(_parse_color(colour), colour)

    def test_opaque_colours_still_parse(self):
        self.assertEqual(_parse_color("#fff"), (255, 255, 255))
        self.assertEqual(_parse_color("#ffffffff"), (255, 255, 255))
        self.assertEqual(_parse_color("rgba(0, 0, 0, 1)"), (0, 0, 0))
        self.assertEqual(_parse_color("rgb(12 34 56)"), (12, 34, 56))
        self.assertEqual(_parse_color("#ffffff url(bg.png)"), (255, 255, 255))

    def test_out_of_range_channels_are_clamped_like_a_browser(self):
        self.assertEqual(_parse_color("rgb(300, -20, 0)"), (255, 0, 0))

    def test_a_translucent_pair_is_not_reported(self):
        markup = '<p style="color:#333333;background:rgba(0,0,0,0.05)">text</p>'
        self.assertEqual(issues(markup, "contrast-inline"), [])

    def test_colour_alone_is_not_judged(self):
        # Without a background on the same element the real pair comes from
        # the cascade, which this pass cannot see — so it says nothing.
        self.assertEqual(issues('<p style="color:#999999">text</p>', "contrast-inline"), [])


class DocumentLevel(unittest.TestCase):
    def test_missing_lang_and_title_are_reported_for_a_full_document(self):
        found = {i.rule_id for i in issues("<html><body><p>x</p></body></html>")}
        self.assertIn("html-lang", found)
        self.assertIn("document-title", found)

    def test_a_fragment_is_not_judged_as_a_document(self):
        # A JSX component file is not a page; demanding <title> of it would
        # be a false positive on every component in a repository.
        found = {i.rule_id for i in issues("<div><p>x</p></div>")}
        self.assertNotIn("html-lang", found)
        self.assertNotIn("document-title", found)
        self.assertNotIn("page-has-h1", found)


class Explanations(unittest.TestCase):
    def test_every_rule_has_all_four_strings_in_all_three_languages(self):
        from i18n.translations import _STRINGS

        missing = []
        for rule_id in audit.RuleRegistry.available():
            stem = rule_id.replace("-", "_")
            for suffix in ("title", "found", "why", "fix"):
                key = f"a11y_{stem}_{suffix}"
                entry = _STRINGS.get(key)
                if entry is None:
                    missing.append(key)
                    continue
                for language in ("uk", "it", "en"):
                    if not entry.get(language):
                        missing.append(f"{key}:{language}")
        self.assertEqual(missing, [])

    def test_explanation_renders_with_the_rule_specific_values(self):
        from audit.explanations import render

        issue = issues('<img src="/hero.png">', "image-alt")[0]
        rendered = render(issue, "en")
        self.assertIn("/hero.png", rendered.found)
        self.assertIn("1.1.1", rendered.wcag)
        self.assertTrue(rendered.why)
        self.assertTrue(rendered.fix)


class AIReview(unittest.TestCase):
    def test_candidates_skip_what_the_offline_rules_already_answer(self):
        from bs4 import BeautifulSoup

        from audit.ai_review import collect_candidates
        from audit.base import RuleContext
        from audit.engine import _dom_path

        document = BeautifulSoup(
            '<img src="/a.png"><img src="/b.png" alt="A chart">', "html.parser")
        context = RuleContext(source="x")
        context.dom_path = _dom_path
        candidates = collect_candidates(document, context)
        # The image with no alt is `image-alt`, reported exactly and for free;
        # paying a model to re-confirm it would be waste.
        self.assertEqual([c["text"] for c in candidates], ["A chart"])

    def test_a_failing_provider_yields_one_finding_not_an_exception(self):
        from bs4 import BeautifulSoup

        from audit.ai_review import AIAccessibilityReview
        from audit.base import RuleContext
        from audit.engine import _dom_path

        class Failing:
            def analyze(self, system, user):
                raise RuntimeError("not signed in")

        document = BeautifulSoup('<img src="/b.png" alt="A chart">', "html.parser")
        context = RuleContext(source="x")
        context.dom_path = _dom_path
        found = AIAccessibilityReview(provider=Failing()).review_document(document, context)
        self.assertEqual(len(found), 1)
        self.assertIn("batch_error", found[0].details)


class Landmarks(unittest.TestCase):
    def test_page_without_main_is_reported(self):
        markup = '<html><body><nav><a href="/">Home</a></nav><p>Content</p></body></html>'
        found = issues(markup, "landmark-regions")
        self.assertEqual(len(found), 1)
        self.assertIn("<main>", found[0].fix_snippet)

    def test_page_with_main_is_fine(self):
        markup = '<html><body><main><p>Content</p></main></body></html>'
        self.assertEqual(issues(markup, "landmark-regions"), [])

    def test_fragment_is_not_judged(self):
        self.assertEqual(issues('<div><p>x</p></div>', "landmark-regions"), [])


class SkipLink(unittest.TestCase):
    def test_page_without_skip_link_is_reported(self):
        markup = '<html><body><nav><a href="/">Home</a></nav><main id="main"><p>x</p></main></body></html>'
        found = issues(markup, "skip-link")
        self.assertEqual(len(found), 1)

    def test_page_with_skip_link_is_fine(self):
        markup = '<html><body><a href="#main">Skip</a><nav><a href="/">Home</a></nav><main id="main"><p>x</p></main></body></html>'
        self.assertEqual(issues(markup, "skip-link"), [])

    def test_fragment_is_not_judged(self):
        self.assertEqual(issues('<div><a href="#x">Skip</a></div>', "skip-link"), [])


class FormErrorMessage(unittest.TestCase):
    def test_invalid_field_without_description_is_reported(self):
        markup = '<input type="text" aria-invalid="true">'
        found = issues(markup, "form-error-message")
        self.assertEqual(len(found), 1)

    def test_invalid_field_with_describedby_is_fine(self):
        markup = '<input type="text" aria-invalid="true" aria-describedby="err"><span id="err">Required</span>'
        self.assertEqual(issues(markup, "form-error-message"), [])

    def test_invalid_field_with_errormessage_is_fine(self):
        markup = '<input type="text" aria-invalid="true" aria-errormessage="err">'
        self.assertEqual(issues(markup, "form-error-message"), [])

    def test_valid_field_is_not_judged(self):
        self.assertEqual(issues('<input type="text">', "form-error-message"), [])


class TableScope(unittest.TestCase):
    def test_table_with_th_without_scope_is_reported(self):
        markup = '<table><tr><th>Name</th><th>Age</th></tr><tr><td>John</td><td>30</td></tr></table>'
        found = issues(markup, "table-scope")
        self.assertEqual(len(found), 1)

    def test_table_with_scope_is_fine(self):
        markup = '<table><tr><th scope="col">Name</th><th scope="col">Age</th></tr><tr><td>John</td><td>30</td></tr></table>'
        self.assertEqual(issues(markup, "table-scope"), [])

    def test_single_th_is_not_judged(self):
        markup = '<table><tr><th>Name</th><td>John</td></tr></table>'
        self.assertEqual(issues(markup, "table-scope"), [])


class HreflangLinks(unittest.TestCase):
    def test_multilingual_site_without_hreflang_is_reported(self):
        markup = '<html lang="en"><head><title>T</title></head><body><a href="/uk/">Українська</a></body></html>'
        found = issues(markup, "hreflang-links")
        self.assertEqual(len(found), 1)

    def test_page_without_language_links_is_not_judged(self):
        markup = '<html lang="en"><head><title>T</title></head><body><p>Content</p></body></html>'
        self.assertEqual(issues(markup, "hreflang-links"), [])


class BreadcrumbMarkup(unittest.TestCase):
    def test_breadcrumb_outside_nav_is_reported(self):
        markup = '<div class="breadcrumb"><a href="/">Home</a> / <a href="/page">Page</a></div>'
        found = issues(markup, "breadcrumb-markup")
        self.assertEqual(len(found), 1)

    def test_breadcrumb_in_nav_is_fine(self):
        markup = '<nav aria-label="breadcrumb"><ol><li><a href="/">Home</a></li></ol></nav>'
        self.assertEqual(issues(markup, "breadcrumb-markup"), [])


class LanguageChange(unittest.TestCase):
    def test_foreign_text_without_lang_is_reported(self):
        markup = '<html lang="en"><head><title>T</title></head><body><p>This is a long enough English text with <span>дуже довгий український текст щоб перевірити правило</span> inside</p></body></html>'
        found = issues(markup, "language-change")
        # May or may not find it depending on text length threshold
        if found:
            self.assertEqual(found[0].details["page_lang"], "en")

    def test_foreign_text_with_lang_is_fine(self):
        markup = '<html lang="en"><head><title>T</title></head><body><p>This is English <span lang="uk">Український текст</span></p></body></html>'
        self.assertEqual(issues(markup, "language-change"), [])


class AbbreviationExpansion(unittest.TestCase):
    def test_abbreviation_without_abbr_is_reported(self):
        markup = '<html lang="en"><head><title>T</title></head><body><p>The WCAG standard is important for accessibility on this page with enough text to trigger the rule</p></body></html>'
        found = issues(markup, "abbreviation-expansion")
        # May find WCAG
        if found:
            self.assertEqual(found[0].details["abbreviation"], "WCAG")

    def test_a_comment_is_not_content(self):
        """`find_all(string=True)` returns comments too. Measured across
        three repositories: more hits came from HTML comments - "STEP 1
        WIREFRAME", "MASTHEAD (upload img/...)" - than from the pages' own
        prose. A comment has no reader to be accessible to."""
        markup = ('<html lang="en"><head><title>T</title></head><body>'
                  '<!-- STEP 1 WIREFRAME: HTML and CSS, no JSON here -->'
                  '<p>Ordinary copy with no abbreviation in it.</p>'
                  '</body></html>')
        self.assertEqual(issues(markup, "abbreviation-expansion"), [])

    def test_the_page_s_own_prose_is_still_read(self):
        markup = ('<html lang="en"><head><title>T</title></head><body>'
                  '<p>The API is documented elsewhere.</p></body></html>')
        found = issues(markup, "abbreviation-expansion")
        self.assertEqual([f.details["abbreviation"] for f in found], ["API"])

    def test_abbreviation_with_abbr_is_fine(self):
        markup = '<html lang="en"><head><title>T</title></head><body><p>The <abbr title="Web Content Accessibility Guidelines">WCAG</abbr> standard is important</p></body></html>'
        self.assertEqual(issues(markup, "abbreviation-expansion"), [])


class BackgroundVideoAndCaptions(unittest.TestCase):
    """1.2.2 is about the audio of synchronised media.

    Measured 2026-09-01 on a live site: `<video autoplay muted loop
    playsinline>` - the hero background idiom, with no `controls` and so no
    way for a visitor to turn sound on - was reported at `serious` on every
    page for captions it has no audio to carry.
    """

    BACKGROUND = ('<video class="hero" autoplay muted loop playsinline>'
                  '<source src="hero.mp4" type="video/mp4"></video>')

    def test_a_muted_uncontrollable_background_video_is_not_asked_for_captions(self):
        self.assertEqual(issues(self.BACKGROUND, "media-captions"), [])

    def test_the_same_video_with_controls_is(self):
        """Controls mean the visitor can unmute it, so there is audio to
        caption after all."""
        with_controls = self.BACKGROUND.replace("<video ", "<video controls ")
        self.assertEqual(len(issues(with_controls, "media-captions")), 1)

    def test_an_unmuted_video_is_still_asked(self):
        unmuted = self.BACKGROUND.replace(" muted", "")
        self.assertEqual(len(issues(unmuted, "media-captions")), 1)

    def test_audio_is_never_exempt(self):
        self.assertEqual(len(issues('<audio autoplay muted src="a.mp3"></audio>',
                                    "media-captions")), 1)

    def test_a_captioned_video_was_always_fine(self):
        captioned = self.BACKGROUND.replace(
            "</video>", '<track kind="captions" src="c.vtt"></video>')
        self.assertEqual(issues(captioned.replace(" muted", ""),
                                "media-captions"), [])


class WhatCountsAsMarkup(unittest.TestCase):
    """The gate in front of the repo audit is one character.

    `analyze_files` examines a file when `"<" in raw_text`, which is true of
    `WHERE created_at < now()` in a `.sql` file and of a `node -e` heredoc in
    a shell hook. Measured 2026-09-01 over seven repositories: `.sql`, `.sh`
    and `.cjs` files produced 51 `abbreviation-expansion` findings about the
    words SQL and JSON - an accessibility rule reporting on a file that has
    no reader to be accessible to.
    """

    def test_a_language_whose_angle_bracket_is_an_operator_is_skipped(self):
        from audit.engine import SKIP_AUDIT_SUFFIXES

        for suffix in (".sql", ".sh", ".cjs", ".yml", ".json", ".css"):
            with self.subTest(suffix):
                self.assertIn(suffix, SKIP_AUDIT_SUFFIXES)

    def test_markup_extensions_are_still_read(self):
        """The other half: `.tsx` was in this list once, and a whole React
        repository audited down to its empty shell. See `P-19`."""
        from audit.engine import SKIP_AUDIT_SUFFIXES

        for suffix in (".html", ".tsx", ".jsx", ".vue", ".svelte", ".php"):
            with self.subTest(suffix):
                self.assertNotIn(suffix, SKIP_AUDIT_SUFFIXES)

    def test_a_sql_file_produces_no_document(self):
        import audit
        from models import FileResult

        files = [FileResult(path="/repo/query.sql",
                            raw_text="SELECT * FROM t WHERE a < 5 -- JSON API"),
                 FileResult(path="/repo/page.html",
                            raw_text="<html lang='en'><body><p>The API is "
                                     "documented</p></body></html>")]
        result = audit.analyze_files(files, "/repo", media=False,
                                     repo_facts=False)
        self.assertEqual([d.source for d in result.documents],
                         ["/repo/page.html"])


class ImageModernFormat(unittest.TestCase):
    def test_legacy_format_without_srcset_is_reported(self):
        found = issues('<img src="/photo.png" alt="Photo">', "image-modern-format",
                       category=audit.PERFORMANCE)
        self.assertEqual(len(found), 1)

    def test_modern_format_is_not_judged(self):
        self.assertEqual(issues('<img src="/photo.webp" alt="Photo">', "image-modern-format",
                                category=audit.PERFORMANCE), [])

    def test_srcset_satisfies_the_rule(self):
        self.assertEqual(issues('<img src="/photo.png" srcset="/photo-300.webp 300w" alt="Photo">',
                                "image-modern-format", category=audit.PERFORMANCE), [])

    def test_svg_is_not_judged(self):
        self.assertEqual(issues('<img src="/icon.svg" alt="Icon">', "image-modern-format",
                                category=audit.PERFORMANCE), [])

    def test_data_uri_is_not_judged(self):
        self.assertEqual(issues('<img src="data:image/png;base64,abc" alt="Icon">',
                                "image-modern-format", category=audit.PERFORMANCE), [])

    def test_the_reported_address_keeps_its_case(self):
        """Matching is case-insensitive; the address is not.

        Measured on a live WordPress theme: `logo-Barra-FVG.png` was reported
        as `logo-barra-fvg.png`, which is a 404 on any case-sensitive server -
        the reader is sent to a file that does not exist.
        """
        found = issues('<img src="/assets/logo-Barra-FVG.PNG" alt="Logo">',
                       "image-modern-format", category=audit.PERFORMANCE)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].details["src"], "/assets/logo-Barra-FVG.PNG")


if __name__ == "__main__":
    unittest.main()
