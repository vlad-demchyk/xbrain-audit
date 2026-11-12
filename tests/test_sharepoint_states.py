"""The browser pass on SharePoint reads states, geometry and HTML_CodeSniffer too.

Until 0.77.0 `sharepoint_zones.browser_options` switched off the state pass,
the measurements and HTML_CodeSniffer, because they read the whole document
and their findings could not be tied to a zone. A SharePoint audit therefore
checked no keyboard, no focus and no hover state, and `perf-image-loading`
never settled. Now each of them leaves the chrome regions alone, records
where its element is (`dom_path`), and `classify_browser_issues` places the
finding in a zone, drops it as Microsoft's, or keeps it and counts it as
unplaced - never silently.

The markup is synthetic (`fixtures/sharepoint/*.html`); the last class runs
the real browser on it.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from audit import sharepoint_zones as zones
from audit.base import Issue

FIXTURES = Path(__file__).parent / "fixtures" / "sharepoint"
MODERN = FIXTURES / "modern_page.html"
STATES = FIXTURES / "states_page.html"


def _markup(path=MODERN) -> str:
    return path.read_text(encoding="utf-8")


def _path_to(markup: str, css: str) -> str:
    """The path the browser scripts record, built here from the same DOM."""
    from bs4 import Tag

    document, _map = zones.map_page(markup)
    node = document.select_one(css)
    steps = []
    while node is not None and node.name != "[document]":
        parent = node.parent
        if parent is None or parent.name == "[document]":
            steps.insert(0, node.name)
            break
        siblings = [child for child in parent.children if isinstance(child, Tag)]
        steps.insert(0, f"{node.name}:{siblings.index(node)}")
        node = parent
    return "/".join(steps)


def _state(rule, path="", selector="", snippet=""):
    return Issue(f"state:{rule}", "serious", selector=selector, snippet=snippet,
                 engine="browser", details={"engine": "state-pass", "dom_path": path})


class ThePath(unittest.TestCase):
    def test_a_recorded_path_finds_exactly_that_element(self):
        markup = _markup()
        path = _path_to(markup, ".newsCarousel_1a2b3c4d")
        document, _map = zones.map_page(markup)
        found = zones.element_by_path(document, path)
        self.assertEqual(found.get("tabindex"), "8")

    def test_a_path_that_no_longer_fits_finds_nothing_rather_than_a_neighbour(self):
        markup = _markup()
        document, _map = zones.map_page(markup)
        path = _path_to(markup, ".newsCarousel_1a2b3c4d")
        for broken in (path.rsplit("/", 1)[0] + "/a:0",       # another tag there
                       path.rsplit("/", 1)[0] + "/div:99",    # past the last child
                       "body:1/div:0",                         # not from the root
                       "html/body:x", ""):
            with self.subTest(broken):
                self.assertIsNone(zones.element_by_path(document, broken))

    def test_the_path_wins_over_a_selector_that_matches_another_element(self):
        """The state pass's selector is short and relative; two carousels
        spell it the same way. The path says which one."""
        markup = _markup()
        second = _path_to(markup, '[data-sp-feature-instance-id="10000000-0000-4000-8000-000000000005"] .newsCarousel_1a2b3c4d')
        issue = _state("focus-not-visible", path=second,
                       selector="div.newsCarousel_1a2b3c4d")
        document, _map = zones.map_page(markup)
        self.assertEqual(zones.element_for(document, issue).get("tabindex"), "9")


class PlacingStateFindings(unittest.TestCase):
    def setUp(self):
        self.markup = _markup()
        self.summary = zones.Summary()

    def _classify(self, issues):
        return zones.classify_browser_issues(issues, self.markup, summary=self.summary)

    def _engine(self, name="states"):
        return self.summary.browser.get("engines", {}).get(name, {})

    def test_a_finding_in_a_custom_part_carries_the_zone(self):
        issue = _state("focus-not-visible",
                       path=_path_to(self.markup, ".newsCarousel_1a2b3c4d"))
        kept = self._classify([issue])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].details["zone"], "custom")
        self.assertEqual(kept[0].details["zone_name"], "Contoso News Carousel")
        self.assertEqual(self._engine(), {"placed": 1})

    def test_a_finding_in_the_chrome_is_dropped_and_counted_as_microsofts(self):
        issue = _state("keyboard-trap", path=_path_to(self.markup, "#spCommandBar button"))
        self.assertEqual(self._classify([issue]), [])
        self.assertEqual(self.summary.skipped_by_rule, {"state:keyboard-trap": 1})
        self.assertEqual(self._engine(), {"platform": 1})

    def test_a_finding_in_a_microsoft_part_is_its_markup_and_skipped(self):
        """Focus styling inside Quick links is Microsoft's CSS, not the
        author's content: counted as skipped, like axe's would be."""
        issue = _state("focus-not-visible", path=_path_to(self.markup, ".quickLinks"))
        self.assertEqual(self._classify([issue]), [])
        self.assertEqual(self._engine(), {"skipped": 1})

    def test_a_finding_nobody_can_place_is_kept_and_counted(self):
        issue = _state("hover-only-content", path="html/body:1/div:42",
                       selector="div.gone > span", snippet='<span class="gone">')
        kept = self._classify([issue])
        self.assertEqual(kept, [issue])
        self.assertEqual(issue.details["zone"], "")
        self.assertEqual(self._engine(), {"unplaced": 1})
        self.assertEqual(self.summary.browser["unplaced_by_rule"],
                         {"state:hover-only-content": 1})
        self.assertEqual(self.summary.as_dict()["browser"]["engines"]["states"],
                         {"unplaced": 1})

    def test_no_skip_link_is_the_page_frames_even_when_it_points_into_a_part(self):
        issue = _state("no-skip-link", path=_path_to(self.markup, ".newsCarousel_1a2b3c4d"))
        self.assertEqual(self._classify([issue]), [])
        self.assertEqual(self.summary.skipped_by_rule, {"state:no-skip-link": 1})
        self.assertEqual(self._engine(), {"platform": 1})

    def test_htmlcs_bypass_is_the_frames_but_an_untitled_iframe_is_placed(self):
        part = _path_to(self.markup, ".newsCarousel_1a2b3c4d img")
        bypass = Issue("htmlcs:2_4_1", "serious", engine="htmlcs",
                       details={"code": "WCAG2AA.Principle2.Guideline2_4.2_4_1.G1,G123,G124.NoSuchID",
                                "dom_path": part})
        iframe = Issue("htmlcs:2_4_1", "serious", engine="htmlcs",
                       details={"code": "WCAG2AA.Principle2.Guideline2_4.2_4_1.H64.1",
                                "dom_path": part})
        kept = self._classify([bypass, iframe])
        self.assertEqual(kept, [iframe])
        self.assertEqual(iframe.details["zone_name"], "Contoso News Carousel")

    def test_run_facts_pass_through_and_are_not_unplaced(self):
        facts = [Issue("state:focus-not-measured", "minor", engine="browser"),
                 Issue("state-pass", "moderate", engine="browser",
                       details={"engine_error": "boom"}),
                 Issue("htmlcs", "moderate", engine="htmlcs",
                       details={"engine_error": "boom"})]
        self.assertEqual(self._classify(list(facts)), facts)
        self.assertEqual(self.summary.browser.get("engines", {}), {})

    def test_page_load_budgets_are_not_listed_but_counted(self):
        issue = Issue("perf-page-weight", "moderate", engine="browser",
                      category="performance", details={"metric": "transferBytes"})
        self.assertEqual(self._classify([issue]), [])
        self.assertEqual(self._engine("measurements"), {"page_level": 1})
        self.assertEqual(self.summary.skipped_findings, 0)

    def test_an_htmlcs_finding_is_placed_by_its_path(self):
        alt = Issue("htmlcs:1_1_1", "serious", engine="htmlcs",
                    snippet='<img src="/sites/ExampleSite/news/1.jpg">',
                    details={"dom_path": _path_to(self.markup, ".newsCarousel_1a2b3c4d img")})
        kept = self._classify([alt])
        self.assertEqual(kept[0].details["zone_name"], "Contoso News Carousel")
        self.assertEqual(self._engine("htmlcs"), {"placed": 1})

    def test_htmlcs_content_codes_stay_in_microsoft_parts_and_structure_does_not(self):
        link = _path_to(self.markup, '.quickLinks a')
        content = Issue("htmlcs:2_4_4", "serious", engine="htmlcs", details={"dom_path": link})
        structure = Issue("htmlcs:1_3_1", "serious", engine="htmlcs", details={"dom_path": link})
        kept = self._classify([content, structure])
        self.assertEqual(kept, [content])
        self.assertTrue(content.details["zone_content_only"])


class TheOptions(unittest.TestCase):
    def test_sharepoint_runs_every_engine_and_captures_the_dom(self):
        from audit import browser

        options = zones.browser_options(browser.BrowserAuditOptions())
        self.assertTrue(options.run_axe and options.run_states
                        and options.run_measurements and options.run_htmlcs)
        self.assertTrue(options.capture_html)
        self.assertIn("#spCommandBar", options.exclude)

    def test_the_state_and_htmlcs_scripts_are_told_the_chrome(self):
        from audit import browser, states

        script = states.state_script(["#spCommandBar", "#SuiteNavWrapper"])
        self.assertIn('var EXCLUDE = ["#spCommandBar", "#SuiteNavWrapper"];', script)
        self.assertIn("var EXCLUDE = [];", states.state_script())
        self.assertIn('var __xaExclude = ["#spCommandBar"];',
                      browser.htmlcs_script(exclude=["#spCommandBar"]))

    def test_passes_are_recorded_for_the_coverage(self):
        from audit import browser

        summary = zones.Summary()
        summary.record_passes(zones.browser_options(browser.BrowserAuditOptions()))
        passes = summary.as_dict()["browser"]["passes"]
        self.assertTrue(passes["states"] and passes["measurements"])
        self.assertEqual(passes["htmlcs"], browser.engines_available()["htmlcs"])


class TheCoverageSays(unittest.TestCase):
    BROWSER = {"passes": {"axe": True, "states": True, "measurements": True,
                          "htmlcs": False},
               "engines": {"states": {"placed": 4, "platform": 2, "unplaced": 3},
                           "axe": {"unplaced": 1},
                           "measurements": {"page_level": 2}}}

    def test_each_language_names_the_passes_and_the_unplaced_count(self):
        from audit.coverage import coverage_summary

        for lang, words in (("en", ("state pass (keyboard, focus) ran",
                                    "HTML_CodeSniffer off", "3 could not be placed")),
                            ("uk", ("перевірка станів (клавіатура, фокус) виконано",
                                    "HTML_CodeSniffer вимкнено", "3 не вдалося")),
                            ("it", ("controllo degli stati (tastiera, focus) eseguito",
                                    "HTML_CodeSniffer disattivato", "3 non attribuibili"))):
            with self.subTest(lang):
                _title, text = coverage_summary({"status": "checked",
                                                 "sharepoint_browser": self.BROWSER}, lang)
                for word in words:
                    self.assertIn(word, text)

    def test_other_engines_and_page_budgets_are_said_too(self):
        from audit.coverage import sharepoint_browser_sentence

        text = sharepoint_browser_sentence(self.BROWSER, "en")
        self.assertIn("could not be placed (listed without a zone): 1", text)
        self.assertIn("Page-load measurement findings not listed: 2", text)

    def test_an_ordinary_run_says_nothing_about_sharepoint(self):
        from audit.coverage import coverage_summary

        _title, text = coverage_summary({"status": "checked"}, "en")
        self.assertNotIn("SharePoint", text)

    def test_build_coverage_carries_the_record(self):
        from argparse import Namespace

        from audit.coverage import build_coverage
        from audit.engine import AccessibilityResult

        result = AccessibilityResult("https://contoso.sharepoint.com/sites/ExampleSite",
                                     mode="web")
        result.sharepoint = {"pages": 1, "browser": self.BROWSER}
        coverage = build_coverage(result, Namespace(no_browser=True))
        self.assertEqual(coverage["sharepoint_browser"], self.BROWSER)
        self.assertEqual(build_coverage(AccessibilityResult("x", mode="web"),
                                        Namespace(no_browser=True))["sharepoint_browser"], {})


class TheRealBrowser(unittest.TestCase):
    """The pass itself on SharePoint-shaped markup: what it examines, what it
    records, and where `classify_browser_issues` puts each finding."""

    @classmethod
    def setUpClass(cls):
        from audit import browser, driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)
        cls.options = zones.browser_options(browser.BrowserAuditOptions(
            run_axe=False, allow_local_files=True, settle_ms=300))
        driver.ensure_headless_application()
        runner = driver.BrowserAuditRunner(cls.options)
        try:
            cls.audit = runner.audit(STATES.resolve().as_uri())
        finally:
            runner.close()
        cls.raw = list(cls.audit.issues)
        cls.summary = zones.Summary()
        cls.summary.record_passes(cls.options)
        cls.kept = zones.classify_browser_issues(
            list(cls.audit.issues), cls.audit.html, summary=cls.summary)

    def _kept(self, rule):
        return [issue for issue in self.kept if issue.rule_id == rule]

    def test_the_page_loaded_and_focus_was_measurable(self):
        self.assertFalse(self.audit.error)
        self.assertEqual(self.audit.engine_errors, {})
        self.assertNotIn("state:focus-not-measured", {i.rule_id for i in self.raw})

    def test_every_state_finding_records_its_path(self):
        states = [i for i in self.raw if i.rule_id.startswith("state:")]
        self.assertTrue(states)
        for issue in states:
            self.assertTrue(issue.details.get("dom_path", "").startswith("html/body:"))

    def test_an_excluded_region_is_never_examined(self):
        """`#spCommandBar` holds a button with no focus style and an image
        with no alt: neither engine reports it at all."""
        for issue in self.raw:
            self.assertNotIn('type="button">Edit<', issue.snippet)
            self.assertNotIn("command.png", issue.snippet)

    def test_focus_in_the_custom_part_is_placed_there(self):
        hits = self._kept("state:focus-not-visible")
        self.assertEqual(len(hits), 1)
        self.assertIn("First tile", hits[0].snippet)
        self.assertEqual((hits[0].details["zone"], hits[0].details["zone_name"]),
                         ("custom", "Contoso Tiles"))

    def test_the_text_of_a_focused_button_is_measured_against_its_new_fill(self):
        hits = self._kept("state:focus-text-low-contrast")
        self.assertEqual(len(hits), 1)
        self.assertIn("paleFocus_1a2b3c4d", hits[0].snippet)
        self.assertEqual(hits[0].details["zone_name"], "Contoso Tiles")
        self.assertLess(hits[0].details["ratio"], 1.5)
        self.assertEqual(hits[0].details["required"], 4.5)
        self.assertEqual(hits[0].details["background"], "rgb(232, 232, 232)")

    def test_microsofts_own_toolbar_is_found_and_dropped(self):
        self.assertTrue(any("Share" in i.snippet for i in self.raw
                            if i.rule_id == "state:focus-not-visible"))
        self.assertFalse(any("Share" in i.snippet for i in self.kept))
        self.assertGreaterEqual(self.summary.browser["engines"]["states"]["platform"], 1)

    def test_nothing_was_left_unplaced(self):
        for engine, counts in self.summary.browser["engines"].items():
            with self.subTest(engine):
                self.assertNotIn("unplaced", counts)

    def test_htmlcs_finds_the_parts_image_and_places_it(self):
        hits = self._kept("htmlcs:1_1_1")
        self.assertTrue(hits)
        self.assertTrue(all(hit.details["zone_name"] == "Contoso Tiles" for hit in hits))
        self.assertTrue(any("above_1a2b3c4d" in hit.snippet for hit in hits))

    def test_image_geometry_settles_perf_image_loading(self):
        """The static rule's guess about the part's two images: the one the
        browser saw above the fold is dropped, the one far below is
        confirmed - which is what never happened on SharePoint before."""
        from audit import browser
        from audit.base import NEEDS_BROWSER

        above = self.audit.measurements["imagesAboveFold"]
        below = self.audit.measurements["imagesBelowFold"]
        self.assertTrue(any(src.startswith("data:image/gif;base64,R0lGODlhAQABAAAAACw")
                            for src in above))
        self.assertEqual(len(below), 1)
        static = [Issue("perf-image-loading", "minor", confidence=NEEDS_BROWSER,
                        details={"src": src}) for src in (above[-1], below[0])]
        settled = browser.settle_image_loading(static, self.audit.measurements)
        self.assertEqual([issue.details["src"] for issue in settled], [below[0]])
        self.assertEqual(settled[0].confidence, "exact")


if __name__ == "__main__":
    unittest.main()
