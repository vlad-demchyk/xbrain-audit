"""A SharePoint page is three owners' markup, and only two of them can act.

`audit.sharepoint_zones` splits a modern page into Microsoft's chrome (not
audited, counted), custom SPFx parts and placeholders (audited in full,
named), and what the author wrote (the Text web part in full; Microsoft's
own parts held to the content rules only).

The fixture is synthetic - see the comment at its top. Its attribute names
are the module's hypotheses about SharePoint's DOM, so these tests pin the
*behaviour* the classification promises; the selectors themselves are to be
confirmed on a live tenant.
"""
import json
import tempfile
import unittest
from pathlib import Path

from audit import sharepoint_zones as zones
from audit.base import Issue
from models import PageDiagnostics, PageResult

FIXTURE = Path(__file__).parent / "fixtures" / "sharepoint" / "modern_page.html"
URL = "https://contoso.sharepoint.com/sites/ExampleSite/SitePages/Home.aspx"
CAROUSEL_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _markup() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _page(markup=None, url=URL) -> PageResult:
    return PageResult(url=url, depth=0, raw_html=markup or _markup(),
                      diagnostics=PageDiagnostics(status_code=200))


def _run(markup=None, **kwargs):
    from audit.engine import analyze_pages

    return analyze_pages([_page(markup)], URL, sharepoint=True, media=False,
                         **kwargs)


def _issues(result):
    return [issue for document in result.documents for issue in document.issues]


class TheMapOfOnePage(unittest.TestCase):
    def test_a_sharepoint_page_is_recognised_and_an_ordinary_one_is_not(self):
        self.assertTrue(zones.is_sharepoint_page(_markup()))
        self.assertFalse(zones.is_sharepoint_page(
            "<html><body><main><h1>Hello</h1></main></body></html>"))

    def test_each_part_lands_in_the_zone_whose_owner_can_fix_it(self):
        _document, zone_map = zones.map_page(_markup())
        found = [(zone.kind, zone.name, zone.content_only)
                 for zone in zone_map.zones]
        self.assertEqual(found, [
            ("custom", "Application customizer (Top)", False),
            ("author", "Page header", True),
            ("author", "Text", False),
            ("author", "Quick links", True),
            ("custom", "Contoso News Carousel", False),
            ("custom", "Contoso News Carousel", False),
            ("custom", "Application customizer (Bottom)", False),
        ])

    def test_the_chrome_is_left_out_and_counted_by_name(self):
        _document, zone_map = zones.map_page(_markup())
        self.assertGreater(zone_map.platform_elements, 0)
        self.assertLess(zone_map.platform_elements, zone_map.elements_total)
        self.assertEqual(set(zone_map.platform_regions), {
            "suite-bar", "app-bar", "site-header", "hub-nav", "command-bar",
            "comments", "footer"})

    def test_an_element_in_the_chrome_belongs_to_no_zone(self):
        document, zone_map = zones.map_page(_markup())
        self.assertIsNone(zone_map.zone_of(document.select_one("#O365_NavHeader button")))
        carousel = document.select_one('img[src$="news/2.jpg"]')
        self.assertEqual(zone_map.zone_of(carousel).name, "Contoso News Carousel")


class WhoKnowsWhichPartIsMicrosofts(unittest.TestCase):
    def test_an_unknown_part_is_custom_and_audited_in_full(self):
        """The safe direction for a wrong guess: a part nobody recognised is
        read with every rule rather than dropped as Microsoft's."""
        markup = ('<div data-sp-feature-tag="Something New web part">'
                  '<img src="a.png"></div>')
        _document, zone_map = zones.map_page(markup)
        self.assertEqual(zone_map.zones[0].kind, "custom")
        self.assertEqual(zone_map.zones[0].name, "Something New")

    def test_a_name_learned_from_a_live_page_makes_it_microsofts(self):
        registry = zones.OotbRegistry()
        markup = ('<div data-sp-feature-tag="Something New web part">'
                  '<img src="a.png"></div>')
        registry.register(name="Something New")
        _document, zone_map = zones.map_page(markup, registry=registry)
        self.assertEqual(zone_map.zones[0].kind, "author")
        self.assertTrue(zone_map.zones[0].content_only)

    def test_ids_are_read_from_a_file_not_from_memory(self):
        registry = zones.OotbRegistry()
        self.assertEqual(registry.ids, {})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ootb.json"
            path.write_text(json.dumps({
                "web_parts": [{"id": "{12345678-0000-0000-0000-00000000ABCD}",
                               "name": "Countdown"}],
                "feature_tags": ["Brand new"]}), encoding="utf-8")
            self.assertEqual(registry.load_file(path), 2)
        markup = ('<div data-sp-web-part-id="12345678-0000-0000-0000-00000000abcd">'
                  '<img src="a.png"></div>')
        _document, zone_map = zones.map_page(markup, registry=registry)
        self.assertEqual((zone_map.zones[0].kind, zone_map.zones[0].name),
                         ("author", "Countdown"))
        self.assertTrue(registry.knows_name("Brand new web part"))

    def test_the_repository_names_its_own_part_first(self):
        """A custom part whose title collides with a Microsoft name is still
        recognised as the repository's by its manifest GUID."""
        from audit.spfx import WebPart

        part = WebPart(alias="NewsCarouselWebPart", id=CAROUSEL_ID.upper(),
                       manifest="src/webparts/news/NewsCarouselWebPart.manifest.json",
                       title="Contoso News Carousel")
        markup = _markup().replace('"Contoso News Carousel web part"', '"News web part"')
        _document, zone_map = zones.map_page(markup, web_parts=[part])
        named = [zone for zone in zone_map.zones if zone.manifest]
        self.assertEqual(len(named), 2)
        self.assertEqual({zone.kind for zone in named}, {"custom"})
        self.assertEqual(named[0].name, "Contoso News Carousel")


class WhatIsReported(unittest.TestCase):
    def setUp(self):
        self.result = _run()
        self.issues = _issues(self.result)

    def test_nothing_from_the_chrome_is_reported(self):
        snippets = " ".join(str(issue.snippet) for issue in self.issues)
        for chrome in ("suite-logo", "o365sx", "footer-logo", "Aggiungi un commento",
                       "SiteAssets/logo.png", "sharepoint.aspx"):
            with self.subTest(chrome):
                self.assertNotIn(chrome, snippets)

    def test_every_finding_says_whose_part_it_is_in(self):
        self.assertTrue(self.issues)
        for issue in self.issues:
            with self.subTest(issue.rule_id, snippet=issue.snippet):
                self.assertIn(issue.details["zone"], ("custom", "author"))
                self.assertTrue(issue.details["zone_name"])

    def test_a_custom_part_is_audited_in_full_and_named(self):
        carousel = [issue for issue in self.issues
                    if issue.details["zone_name"] == "Contoso News Carousel"]
        rules = {issue.rule_id for issue in carousel}
        self.assertIn("tabindex-positive", rules)
        self.assertIn("image-alt", rules)
        self.assertEqual({issue.details["web_part"] for issue in carousel},
                         {"Contoso News Carousel"})

    def test_both_placements_of_a_part_are_read(self):
        carousel = " ".join(str(issue.snippet) for issue in self.issues
                            if issue.details["zone_name"] == "Contoso News Carousel")
        self.assertIn("news/1.jpg", carousel)
        self.assertIn("news/2.jpg", carousel)
        self.assertEqual(
            self.result.sharepoint["parts"]["Contoso News Carousel"]["placements"], 2)

    def test_the_text_web_part_is_the_authors_and_gets_every_rule(self):
        text = {issue.rule_id for issue in self.issues
                if issue.details["zone_name"] == "Text"}
        self.assertEqual(text, {"heading-order", "link-text-vague"})

    def test_a_microsoft_part_keeps_only_what_the_author_wrote(self):
        quick = [issue for issue in self.issues
                 if issue.details["zone_name"] == "Quick links"]
        self.assertTrue(quick)
        for issue in quick:
            with self.subTest(issue.rule_id):
                self.assertTrue(zones.is_content_finding(issue))
        header = {issue.rule_id for issue in self.issues
                  if issue.details["zone_name"] == "Page header"}
        self.assertIn("image-alt", header)
        self.assertNotIn("tabindex-positive", header)

    def test_what_was_left_out_is_counted_not_lost(self):
        skipped = self.result.sharepoint["skipped"]
        self.assertGreater(skipped["elements"], 0)
        self.assertGreaterEqual(skipped["by_rule"].get("tabindex-positive", 0), 2)
        self.assertEqual(skipped["findings"], sum(skipped["by_rule"].values()))

    def test_the_response_headers_are_not_the_sites_to_fix(self):
        rules = {issue.rule_id for issue in self.issues}
        self.assertFalse(any(rule.startswith("hdr-") or rule.startswith("header")
                             for rule in rules))

    def test_a_page_without_a_canvas_is_said_not_audited_whole(self):
        plain = ("<!doctype html><html lang='it'><head><title>Lista</title></head>"
                 "<body><img src='x.png'><a href='/a'></a></body></html>")
        result = _run(plain)
        self.assertEqual(len(result.documents), 1)
        self.assertIn("no SharePoint canvas", result.documents[0].error)
        self.assertEqual(result.sharepoint["pages_without_canvas"], [URL])

    def test_an_ordinary_run_carries_no_sharepoint_summary(self):
        from audit.engine import analyze_pages

        result = analyze_pages([_page()], URL, media=False)
        self.assertEqual(result.sharepoint, {})


class ContentRules(unittest.TestCase):
    def test_the_families_the_author_writes_are_content(self):
        for rule in ("image-alt", "axe:link-name", "heading-order",
                     "axe:empty-heading", "language-change", "ai-cliche-wording"):
            with self.subTest(rule):
                self.assertTrue(zones.is_content_finding(Issue(rule, "minor")))

    def test_structure_and_colour_are_not(self):
        for rule in ("tabindex-positive", "control-name", "axe:aria-allowed-attr",
                     "axe:color-contrast", "landmark-regions"):
            with self.subTest(rule):
                self.assertFalse(zones.is_content_finding(Issue(rule, "minor")))

    def test_a_rule_that_crashed_is_never_hidden(self):
        issue = Issue("tabindex-positive", "minor", details={"rule_error": "boom"})
        self.assertTrue(zones.is_content_finding(issue))


class TheBrowserPass(unittest.TestCase):
    def _axe(self, rule, target, snippet=""):
        return Issue(f"axe:{rule}", "serious", selector=target, snippet=snippet,
                     engine="axe")

    def test_browser_findings_are_placed_by_their_target(self):
        summary = zones.Summary()
        issues = [
            self._axe("button-name", "#O365_NavHeader > button"),
            self._axe("image-alt", 'img[src$="news/1.jpg"]'),
            self._axe("aria-allowed-role", ".quickLinks"),
            self._axe("link-name", 'a[href="/sites/ExampleSite/Shared%20Documents"]'),
            self._axe("region", "#nowhere-at-all"),
        ]
        kept = zones.classify_browser_issues(issues, _markup(), summary=summary)
        placed = {(issue.rule_id, issue.details.get("zone"),
                   issue.details.get("zone_name")) for issue in kept}
        self.assertEqual(placed, {
            ("axe:image-alt", "custom", "Contoso News Carousel"),
            ("axe:link-name", "author", "Quick links"),
            # Unplaceable: kept and marked, never silently dropped.
            ("axe:region", "", None),
        })
        self.assertEqual(summary.skipped_findings, 2)

    def test_a_quoted_element_is_found_when_the_selector_is_not_readable(self):
        issue = Issue("htmlcs:H37", "serious", snippet='<img src="/sites/ExampleSite/news/2.jpg">',
                      engine="htmlcs")
        kept = zones.classify_browser_issues([issue], _markup())
        self.assertEqual(kept[0].details["zone_name"], "Contoso News Carousel")

    def test_axe_is_confined_to_the_zones(self):
        from audit import browser

        options = zones.browser_options(browser.BrowserAuditOptions(exclude=[".mine"]))
        self.assertEqual(options.include, list(zones.AXE_INCLUDE))
        self.assertIn(".mine", options.exclude)
        self.assertIn("#SuiteNavWrapper", options.exclude)
        self.assertFalse(options.run_htmlcs or options.run_states
                         or options.run_measurements)
        self.assertTrue(options.capture_html)
        script = browser.axe_script(options)
        self.assertIn('"[data-sp-feature-tag]"', script)
        self.assertIn("scope_empty", script)

    def test_an_unscoped_axe_call_is_unchanged(self):
        from audit import browser

        self.assertNotIn("scope_empty", browser.axe_script(browser.BrowserAuditOptions()))

    def test_lazy_loading_scripts_are_bounded_and_pollable(self):
        self.assertIn("limit = 60", zones.SCROLL_SCRIPT)
        self.assertIn("__xaScrollDone", zones.SCROLL_DONE_SCRIPT)
        self.assertIn("data-sp-feature-tag", zones.CANVAS_COUNT_SCRIPT)


class TheReportSaysWhose(unittest.TestCase):
    def setUp(self):
        self.result = _run()

    def test_the_model_carries_the_zone_and_the_summary(self):
        from report.model import from_accessibility

        model = from_accessibility(self.result, "en")
        self.assertEqual(model.sharepoint, self.result.sharepoint)
        zones_seen = {(f.zone, f.zone_name) for f in model.findings}
        self.assertIn(("custom", "Contoso News Carousel"), zones_seen)
        self.assertIn(("author", "Text"), zones_seen)

    def test_the_html_names_the_part_and_says_what_was_skipped_in_every_language(self):
        from report.model import from_accessibility
        from report.template import render_html

        expected = {"en": ("SPFx: Contoso News Carousel", "Microsoft: skipped"),
                    "uk": ("SPFx: Contoso News Carousel", "Microsoft: пропущено"),
                    "it": ("SPFx: Contoso News Carousel", "Microsoft: elementi saltati")}
        for lang, (badge, skipped) in expected.items():
            with self.subTest(lang):
                html = render_html(from_accessibility(self.result, lang), lang)
                self.assertIn(badge, html)
                self.assertIn(skipped, html)
                self.assertIn("badge-zone", html)

    def test_an_ordinary_report_has_no_sharepoint_section(self):
        from audit.engine import analyze_pages
        from report.model import from_accessibility
        from report.template import render_html

        result = analyze_pages([_page()], URL, media=False)
        html = render_html(from_accessibility(result, "en"), "en")
        self.assertNotIn("SharePoint: what was audited", html)
        self.assertNotIn('class="badge badge-zone', html)

    def test_the_json_record_names_the_zone(self):
        from cli_impl.reports import _file_map, _problem_map
        from audit.explanations import render
        from finding_contract import serialize_issue

        issue = next(i for i in _issues(self.result)
                     if i.details["zone_name"] == "Contoso News Carousel")
        record = serialize_issue(issue, source=URL)
        self.assertEqual((record["zone"], record["zone_name"]),
                         ("custom", "Contoso News Carousel"))
        rows = [row for entry in _file_map(self.result, render, "en")
                for row in entry.get("findings", entry.get("issues", []))]
        self.assertTrue(any(row.get("zone") == "custom" for row in rows))
        problems = _problem_map(self.result, render, "en")
        self.assertTrue(any(p["zone_name"] == "Text" for p in problems))

    def test_an_ordinary_record_keeps_its_shape(self):
        from finding_contract import serialize_issue

        self.assertNotIn("zone", serialize_issue(Issue("image-alt", "serious"),
                                                 source=URL))


if __name__ == "__main__":
    unittest.main()
