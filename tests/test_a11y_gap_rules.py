"""Checks added after an audit of a real site found what the tool had missed.

A 55-criterion audit of a three-language tourism site was compared with what
`audit` reports on the same defects. Five things a person found by hand were
silent here: a video embedded as an `<iframe>`, a "load more" button with no
live region, a link that goes somewhere else in the translation, a focus ring
the colour of its background, and a focused element under a sticky header.
The sixth - an `alt` that is a slug - was caught only with a file extension.

Each class below pins one of them, and every one asserts the quiet case as
firmly as the loud one: a rule that fires on correct markup is how a report
gets switched off.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

import audit
from audit import analyze_document
from audit.base import ACCESSIBILITY, ADVISORY, MODERATE, Issue, RuleRegistry
from audit.crosspage import CROSSPAGE_WCAG, RULE_LINK_TARGET_DIFFERS, link_target_issues
from audit.explanations import render
from audit.states import STATE_RULES, STATE_SCRIPT, STATE_WCAG, issues_from_states


def found(markup: str, rule_id: str) -> list:
    return [i for i in analyze_document(markup, "t.html", line_numbers=True).issues
            if i.rule_id == rule_id]


class EmbeddedVideo(unittest.TestCase):
    RULE = "embedded-video-alternatives"

    def test_a_youtube_iframe_is_flagged_as_advisory(self):
        hits = found('<iframe title="Video" src="https://www.youtube.com/embed/abc123"></iframe>',
                     self.RULE)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].confidence, ADVISORY)
        self.assertEqual(hits[0].details["provider"], "YouTube")
        self.assertFalse(hits[0].details["transcript"])

    def test_other_hosted_players_are_flagged_too(self):
        for src, provider in (
                ("https://player.vimeo.com/video/1", "Vimeo"),
                ("https://www.youtube-nocookie.com/embed/x", "YouTube"),
                ("https://www.dailymotion.com/embed/video/x", "Dailymotion")):
            with self.subTest(src=src):
                hits = found(f'<iframe src="{src}"></iframe>', self.RULE)
                self.assertEqual([h.details["provider"] for h in hits], [provider])

    def test_a_transcript_on_the_page_is_recorded_not_a_reason_to_stay_silent(self):
        hits = found('<h2>Trascrizione del video</h2>'
                     '<iframe src="https://www.youtube.com/embed/abc"></iframe>', self.RULE)
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].details["transcript"])

    def test_a_map_or_form_iframe_is_not_a_video(self):
        for src in ("https://www.google.com/maps/embed?pb=1", "/forms/contact",
                    "https://notyoutube.com/embed/x"):
            with self.subTest(src=src):
                self.assertEqual(found(f'<iframe src="{src}"></iframe>', self.RULE), [])

    def test_a_muted_controlless_background_embed_has_nothing_to_caption(self):
        src = "https://www.youtube.com/embed/x?controls=0&mute=1&autoplay=1&loop=1"
        self.assertEqual(found(f'<iframe src="{src}"></iframe>', self.RULE), [])


class StatusMessages(unittest.TestCase):
    RULE = "status-message-live-region"

    def test_a_load_more_button_without_any_live_region_is_flagged(self):
        for label in ("Carica altri risultati", "Load more", "Mehr laden", "Завантажити ще"):
            with self.subTest(label=label):
                hits = found(f'<main><button type="button">{label}</button></main>', self.RULE)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0].confidence, ADVISORY)
                self.assertIn("aria-live", hits[0].fix_snippet)

    def test_the_trigger_is_recognised_by_its_class_when_the_label_is_an_icon(self):
        hits = found('<button class="btn load-more" aria-label="+"></button>', self.RULE)
        self.assertEqual(len(hits), 1)

    def test_any_live_region_on_the_page_silences_it(self):
        for region in ('<p role="status"></p>', '<div aria-live="polite"></div>',
                       '<div role="alert"></div>', "<output></output>"):
            with self.subTest(region=region):
                self.assertEqual(found(
                    f'<button id="load-more-btn">Load more</button>{region}', self.RULE), [])

    def test_aria_live_off_is_not_a_live_region(self):
        self.assertEqual(len(found(
            '<button id="load-more-btn">Load more</button><div aria-live="off"></div>',
            self.RULE)), 1)

    def test_ordinary_buttons_and_links_are_left_alone(self):
        for markup in ('<button>Invia</button>', '<a href="/more">Leggi la storia</a>',
                       '<button>Mostra il menu</button>'):
            with self.subTest(markup=markup):
                self.assertEqual(found(markup, self.RULE), [])


def page(url: str, html: str):
    return SimpleNamespace(url=url, raw_html=html, error=None, diagnostics=None)


def _doc(lang: str, alternates: dict, body: str) -> str:
    links = "".join(f'<link rel="alternate" hreflang="{code}" href="{href}">'
                    for code, href in alternates.items())
    return f'<html lang="{lang}"><head>{links}</head><body>{body}</body></html>'


ALTERNATES = {"it": "https://s.test/", "en": "https://s.test/en/", "de": "https://s.test/de/"}


class TranslatedLinks(unittest.TestCase):
    def pages(self, it_body, en_body, de_body=None):
        built = [
            page("https://s.test/", _doc("it", ALTERNATES, it_body)),
            page("https://s.test/en/", _doc("en", ALTERNATES, en_body)),
        ]
        if de_body is not None:
            built.append(page("https://s.test/de/", _doc("de", ALTERNATES, de_body)))
        return built

    def test_the_same_link_pointing_elsewhere_in_a_translation_is_found(self):
        pages = self.pages(
            '<a href="https://town.example/">Town</a><a href="https://x.test/b">B</a>',
            '<a href="https://village.example/">Town</a><a href="https://x.test/b">B</a>')
        hits = link_target_issues(pages)
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit.rule_id, RULE_LINK_TARGET_DIFFERS)
        self.assertEqual(hit.source, "https://s.test/en/")
        self.assertEqual(hit.category, ACCESSIBILITY)
        self.assertEqual(hit.confidence, ADVISORY)
        self.assertEqual(hit.details["href"], "https://village.example/")
        self.assertEqual(hit.details["target"], "https://town.example/")

    def test_a_language_only_difference_is_the_same_destination(self):
        pages = self.pages(
            '<a href="https://it.wikipedia.org/wiki/Town">Town</a>'
            '<a href="https://site.test/it/contatti?utm_source=a">Contatti</a>',
            '<a href="https://en.wikipedia.org/wiki/Town">Town</a>'
            '<a href="https://site.test/en/contatti">Contacts</a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_pages_with_different_numbers_of_links_are_not_compared(self):
        pages = self.pages('<a href="https://a.test/">A</a><a href="https://b.test/">B</a>',
                           '<a href="https://b.test/">B</a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_anchors_scripts_and_mail_links_are_not_destinations(self):
        pages = self.pages('<a href="#top">Su</a><a href="mailto:a@b.test">Mail</a>',
                           '<a href="#start">Up</a><a href="mailto:c@d.test">Mail</a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_internal_links_are_judged_through_hreflang_when_both_were_crawled(self):
        alt_a = {"it": "https://s.test/a", "en": "https://s.test/en/a-en"}
        alt_b = {"it": "https://s.test/b", "en": "https://s.test/en/b-en"}
        home = ALTERNATES
        crawled = [
            page("https://s.test/a", _doc("it", alt_a, "")),
            page("https://s.test/en/a-en", _doc("en", alt_a, "")),
            page("https://s.test/b", _doc("it", alt_b, "")),
            page("https://s.test/en/b-en", _doc("en", alt_b, "")),
        ]
        right = [page("https://s.test/", _doc("it", home, '<a href="/a">Hotel</a>')),
                 page("https://s.test/en/", _doc("en", home, '<a href="/en/a-en">Hotel</a>'))]
        wrong = [page("https://s.test/", _doc("it", home, '<a href="/a">Hotel</a>')),
                 page("https://s.test/en/", _doc("en", home, '<a href="/en/b-en">Hotel</a>'))]
        self.assertEqual(link_target_issues(right + crawled), [])
        hits = link_target_issues(wrong + crawled)
        self.assertEqual([h.source for h in hits], ["https://s.test/en/"])

    def test_a_share_button_carries_its_own_page_and_that_is_not_a_destination(self):
        # Measured on the three-language site: 86 pages each reported four
        # share buttons, because `sharer.php?u=<this page>` is different on
        # every page by construction.
        pages = self.pages(
            '<a href="https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fs.test%2F">F</a>',
            '<a href="https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fs.test%2Fen%2F">F</a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_a_share_button_to_a_different_network_is_still_a_difference(self):
        pages = self.pages(
            '<a href="https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fs.test%2F">F</a>',
            '<a href="https://twitter.com/intent/tweet?text=https%3A%2F%2Fs.test%2Fen%2F">F</a>')
        self.assertEqual(len(link_target_issues(pages)), 1)

    def test_the_same_packages_in_another_order_are_not_wrong_links(self):
        # The municipal site's packages: the German page lists them in another order,
        # so by position each link stands opposite another package, and each
        # still leads to its own translation.
        names = ("cultura", "natura", "gusto")
        alts = {n: {"it": f"https://s.test/pacchetto-borgo-{n}",
                    "de": f"https://s.test/de/paket-borgo-{n}"} for n in names}
        crawled = []
        for n in names:
            crawled += [page(alts[n]["it"], _doc("it", alts[n], "")),
                        page(alts[n]["de"], _doc("de", alts[n], ""))]
        it_body = "".join(f'<a href="/pacchetto-borgo-{n}">Pacchetto Borgo {n}</a>'
                          for n in names)
        de_body = "".join(f'<a href="/de/paket-borgo-{n}">Paket Borgo {n}</a>'
                          for n in reversed(names))
        home = {"it": "https://s.test/", "de": "https://s.test/de/"}
        pages = [page("https://s.test/", _doc("it", home, it_body)),
                 page("https://s.test/de/", _doc("de", home, de_body))]
        self.assertEqual(link_target_issues(pages + crawled), [])

    def test_external_links_in_another_order_are_not_wrong_links(self):
        pages = self.pages(
            '<a href="https://town.example/">Town</a>'
            '<a href="https://unesco.example/">Town UNESCO</a>',
            '<a href="https://unesco.example/">Town UNESCO</a>'
            '<a href="https://town.example/">Town</a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_a_wrong_link_is_found_beside_a_link_to_where_it_leads(self):
        """The case the rule exists for must survive the set comparison: the
        page also links to the village, but under the village's own name."""
        pages = self.pages(
            '<a href="https://town.example/">Town</a>'
            '<a href="https://village.example/">Village</a>',
            '<a href="https://village.example/">Town</a>'
            '<a href="https://village.example/">Village</a>')
        hits = link_target_issues(pages)
        self.assertEqual([h.details["href"] for h in hits], ["https://village.example/"])

    def test_paginated_and_filtered_archive_links_have_no_declared_translation(self):
        # Both targets were crawled, neither declares an hreflang pair: "not
        # declared" is not "different". 229 internal findings of this shape,
        # none a defect, came from one crawl.
        home = ALTERNATES
        crawled = [page("https://s.test/arch/page/2/", _doc("it", {}, "")),
                   page("https://s.test/en/arch/page/2/", _doc("en", {}, ""))]
        pages = [page("https://s.test/", _doc("it", home, '<a href="/arch/page/2/">2</a>')),
                 page("https://s.test/en/", _doc("en", home, '<a href="/en/arch/page/2/">2</a>'))]
        self.assertEqual(link_target_issues(pages + crawled), [])

    def test_a_third_party_site_with_a_different_path_is_a_translated_address(self):
        # `ger/intro.mp3` against `ita/intro.mp3`, `/de/2017/03/16/x` against
        # `/2017/02/03/x`: the same site, so only a different *site* counts.
        pages = self.pages(
            '<a href="https://media.test/audio/ita/intro.mp3">Audio</a>',
            '<a href="https://media.test/audio/ger/intro.mp3">Audio</a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_a_filter_whose_value_is_a_translated_slug_is_not_a_different_page(self):
        home = ALTERNATES
        alt_a = {"it": "https://s.test/a", "en": "https://s.test/en/a-en"}
        crawled = [page("https://s.test/a?f=dentro", _doc("it", alt_a, "")),
                   page("https://s.test/en/a-en?f=inside", _doc("en", alt_a, ""))]
        pages = [page("https://s.test/", _doc("it", home, '<a href="/a?f=dentro">Dentro</a>')),
                 page("https://s.test/en/", _doc("en", home, '<a href="/en/a-en?f=inside">Inside</a>'))]
        self.assertEqual(link_target_issues(pages + crawled), [])

    def test_pages_whose_links_mostly_differ_are_not_comparable_by_position(self):
        # An archive lists its cards in the order each language sorts them.
        it = "".join(f'<a href="https://a.test/{n}">{n}</a>' for n in range(8))
        en = "".join(f'<a href="https://b.test/{n}">{n}</a>' for n in range(8))
        self.assertEqual(link_target_issues(self.pages(it, en)), [])

    def test_two_links_with_nothing_in_common_are_two_different_links(self):
        # Cards of a listing in a different order: same position, different
        # card, so a different target is simply true. Not the town against
        # the village under one label.
        pages = self.pages('<a href="https://a.test/1">Porta Udine</a>',
                           '<a href="https://b.test/2">Duomo Dogale</a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_an_icon_link_with_no_text_is_no_evidence(self):
        pages = self.pages('<a href="https://a.test/1"><i></i></a>',
                           '<a href="https://b.test/2"><i></i></a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_the_odd_link_out_among_many_is_still_found(self):
        same = "".join(f'<a href="https://a.test/{n}">{n}</a>' for n in range(20))
        pages = self.pages(same + '<a href="https://town.test/">Town</a>',
                           same + '<a href="https://village.test/">Town</a>')
        self.assertEqual([h.details["href"] for h in link_target_issues(pages)],
                         ["https://village.test/"])

    def test_an_uncrawled_internal_target_is_not_guessed_at(self):
        pages = self.pages('<a href="/a">Casa</a>', '<a href="/en/zzz">Home</a>')
        self.assertEqual(link_target_issues(pages), [])

    def test_the_source_language_page_is_never_the_one_blamed(self):
        pages = self.pages('<a href="https://x.test/1">A</a>', '<a href="https://y.test/1">A</a>')
        self.assertEqual({h.source for h in link_target_issues(pages)}, {"https://s.test/en/"})


class StateRulesAreWiredThrough(unittest.TestCase):
    NEW = ("focus-indicator-low-contrast", "focus-obscured")

    def test_the_new_checks_are_registered_serious_state_rules(self):
        for name in self.NEW:
            with self.subTest(name):
                self.assertIn(name, STATE_RULES)
                self.assertEqual(STATE_RULES[name], "serious")

    def test_every_state_rule_names_the_criteria_it_contributes_to(self):
        self.assertEqual(set(STATE_RULES), set(STATE_WCAG))
        self.assertIn("2.4.11", STATE_WCAG["focus-obscured"])
        self.assertIn("1.4.11", STATE_WCAG["focus-indicator-low-contrast"])

    def test_the_script_measures_contrast_and_what_covers_the_focused_element(self):
        for fragment in ("rule: 'focus-indicator-low-contrast'", "record('focus-obscured'",
                         "elementFromPoint", "function contrastOf", "stuckBox"):
            with self.subTest(fragment):
                self.assertIn(fragment, STATE_SCRIPT)

    def test_transitions_are_switched_off_for_the_measurement_and_put_back(self):
        self.assertIn("setProperty('transition', 'none', 'important')", STATE_SCRIPT)
        self.assertIn("removeProperty('transition')", STATE_SCRIPT)

    def test_nothing_is_clicked_or_typed(self):
        for forbidden in (".click(", "dispatchEvent(new MouseEvent", ".submit("):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, STATE_SCRIPT)

    def test_findings_come_back_as_issues_with_their_details(self):
        payload = ('{"findings": [{"rule": "focus-obscured", "selector": "a", "html": "<a>",'
                   ' "edge": "top", "coveredBy": "header", "coverHeight": 98, "count": 4}]}')
        issues = issues_from_states(payload, "https://s.test/")
        self.assertEqual([i.rule_id for i in issues], ["state:focus-obscured"])
        self.assertEqual(issues[0].severity, "serious")
        self.assertEqual(issues[0].details["coverHeight"], 98)


_FOCUS_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Focus fixture</title><meta name="viewport" content="width=device-width">
<style>
 body{margin:0;font-family:sans-serif;background:#fff}
 header{position:sticky;top:0;height:98px;background:#fff;z-index:10}
 header a{display:inline-block;margin:30px}
 a.bad:focus{outline:3px solid #fff;outline-offset:2px}
 a.good:focus{outline:3px solid #111;outline-offset:2px}
 a.dual:focus{outline:2px solid #fff;box-shadow:0 0 0 4px #111}
 a.pale{transition:all .3s} a.pale:focus{outline:none;box-shadow:0 0 0 3px #e6e6e6}
 a.fill{background:#fff;padding:4px} a.fill:focus{background:#111;color:#fff;outline:2px solid #111}
 a.none:focus{outline:none}
</style></head><body>
<header><a href="/" class="good">Logo</a><a href="/s" class="bad">Search</a></header>
<main><nav aria-label="breadcrumb"><a href="/" class="good">Home</a></nav>
<h1>Title</h1>
<p><a href="/2" class="good">Dark ring</a> <a href="/3" class="dual">Dual ring</a>
<a href="/4" class="pale">Pale shadow</a> <a href="/5" class="fill">Fill</a>
<a href="/6" class="none">Nothing</a></p>
""" + "".join(f"<p>Filler {i}</p>" for i in range(80)) + "</main></body></html>"


class InARealBrowser(unittest.TestCase):
    """The state checks, run against a page by QtWebEngine.

    The text-level tests above pin the script's source; this one runs it, which
    is the only way to know the colour arithmetic and the point-sampling agree
    with what Chromium draws. Skipped where no browser can start.
    """

    @classmethod
    def setUpClass(cls):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from audit import browser, driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "focus.html"
            path.write_text(_FOCUS_PAGE, encoding="utf-8")
            options = browser.BrowserAuditOptions(
                run_axe=False, run_htmlcs=False, run_states=True,
                run_measurements=False, allow_local_files=True, settle_ms=300)
            driver.ensure_headless_application()
            runner = driver.BrowserAuditRunner(options)
            try:
                result = runner.audit(path.resolve().as_uri())
            finally:
                runner.close()
        cls.found: dict = {}
        for issue in result.issues:
            cls.found.setdefault(issue.rule_id, []).append(issue)

    def classes_of(self, rule_id: str) -> set:
        import re
        return {m for i in self.found.get(rule_id, [])
                for m in re.findall(r'class="(\w+)"', i.snippet)}

    def test_focus_was_measurable_in_a_command_line_run(self):
        self.assertNotIn("state:focus-not-measured", self.found)

    def test_a_white_ring_on_a_white_page_and_a_pale_shadow_are_found(self):
        self.assertEqual(self.classes_of("state:focus-indicator-low-contrast"), {"bad", "pale"})

    def test_a_dark_ring_a_double_ring_and_a_strong_fill_are_not(self):
        flagged = self.classes_of("state:focus-indicator-low-contrast")
        self.assertFalse(flagged & {"good", "dual", "fill"})

    def test_the_contrast_finding_carries_its_numbers(self):
        white = next(i for i in self.found["state:focus-indicator-low-contrast"]
                     if 'class="bad"' in i.snippet)
        self.assertEqual(white.details["ratio"], 1)
        self.assertEqual(white.details["indicator"], "outline")
        self.assertEqual(white.details["required"], 3)

    def test_no_focus_at_all_is_still_reported_and_only_for_that_element(self):
        self.assertEqual(self.classes_of("state:focus-not-visible"), {"none"})

    def test_what_the_sticky_header_covers_is_found_with_its_height(self):
        hits = self.found.get("state:focus-obscured", [])
        self.assertTrue(hits)
        self.assertEqual(hits[0].details["edge"], "top")
        self.assertIn("header", hits[0].details["coveredBy"])
        self.assertEqual(hits[0].details["coverHeight"], 98)
        # Both boxes and the window, so the finding can be checked by hand.
        cover = [int(v) for v in hits[0].details["coverBox"].split(",")]
        self.assertEqual(cover[3], 98)
        self.assertEqual(len(hits[0].details["elementBox"].split(",")), 4)
        self.assertRegex(hits[0].details["viewport"], r"^\d+x\d+$")

    def test_the_measurement_leaves_no_trace_in_the_quoted_markup(self):
        for issues in self.found.values():
            for issue in issues:
                self.assertNotIn("transition: none", issue.snippet)
                self.assertNotIn('style=""', issue.snippet)


class EveryNewRuleReadsInEveryLanguage(unittest.TestCase):
    def rendered(self, rule_id, details, lang):
        return render(Issue(rule_id=rule_id, severity=MODERATE, category=ACCESSIBILITY,
                            source="x", details=details), lang)

    def assert_readable(self, explanation, rule_id, lang):
        for field in ("title", "found", "why", "fix"):
            value = getattr(explanation, field)
            self.assertTrue(value, f"{rule_id}/{lang}: {field} is empty")
            self.assertFalse(value.startswith("a11y_"),
                             f"{rule_id}/{lang}: {field} is the raw key {value!r}")
            self.assertNotIn("{", value, f"{rule_id}/{lang}: {field} has an unfilled slot")

    def test_registered_rules(self):
        for lang in ("uk", "it", "en"):
            for rule_id in ("embedded-video-alternatives", "status-message-live-region",
                            "image-alt-filename"):
                with self.subTest(lang=lang, rule=rule_id):
                    self.assertIn(rule_id, RuleRegistry.available())
                    self.assert_readable(self.rendered(
                        rule_id, {"provider": "YouTube", "src": "https://y/x",
                                  "transcript": False, "element": "button",
                                  "alt": "mappa-parlante-example", "kind": "slug"}, lang),
                        rule_id, lang)

    def test_state_rules_with_their_measurements(self):
        details = {"ratio": 1.0, "required": 3, "indicator": "outline",
                   "color": "rgb(255, 255, 255)", "background": "rgb(255, 255, 255)",
                   "edge": "top", "coveredBy": "header#h", "coverHeight": 98, "count": 4}
        for lang in ("uk", "it", "en"):
            for name in ("focus-indicator-low-contrast", "focus-obscured"):
                with self.subTest(lang=lang, rule=name):
                    explanation = self.rendered(f"state:{name}", details, lang)
                    self.assert_readable(explanation, name, lang)
                    self.assertEqual(explanation.wcag, STATE_WCAG[name])

    def test_the_window_edge_is_a_word_in_the_readers_language(self):
        base = {"coveredBy": "header", "coverHeight": 98, "count": 1}
        self.assertIn("верхнього", self.rendered(
            "state:focus-obscured", {**base, "edge": "top"}, "uk").found)
        self.assertIn("inferiore", self.rendered(
            "state:focus-obscured", {**base, "edge": "bottom"}, "it").found)
        self.assertIn("top edge", self.rendered(
            "state:focus-obscured", {**base, "edge": "top"}, "en").found)

    def test_the_crawl_rule_carries_its_criterion(self):
        details = {"text": "Town", "href": "https://a/s", "target": "https://a/p",
                   "language": "it", "other_text": "Town"}
        for lang in ("uk", "it", "en"):
            with self.subTest(lang=lang):
                explanation = self.rendered(RULE_LINK_TARGET_DIFFERS, details, lang)
                self.assert_readable(explanation, RULE_LINK_TARGET_DIFFERS, lang)
                self.assertEqual(explanation.wcag, CROSSPAGE_WCAG[RULE_LINK_TARGET_DIFFERS])


if __name__ == "__main__":
    unittest.main()
