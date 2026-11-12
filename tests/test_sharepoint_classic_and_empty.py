"""A SharePoint page with an empty canvas, or a classic page, is read.

On a live intranet audit, pages of both kinds came back as "no SharePoint
canvas recognised; it was not audited", and stderr said nothing about it:

* a modern page whose canvas exists and is empty has no authored content -
  that is a finding about the page, not a page the tool failed to read;
* a classic page has no modern canvas at all; its content is in
  `#DeltaPlaceHolderMain`, in web parts `div#WebPartWPQ<n>[webpartid]`.

The markup below is synthetic; its structure follows the live DOM.
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace

from audit import sharepoint_zones as zones
from models import PageDiagnostics, PageResult

URL = "https://contoso.sharepoint.com/sites/ExampleSite/SitePages/Empty.aspx"

EMPTY = """<!doctype html><html lang="it"><head><title>Benvenuto</title>
<script>var spClientSidePageContext = {};</script></head><body>
<div id="spPageChromeAppDiv" data-sp-feature-tag="Page Chrome" data-sp-feature-instance-id="_Page Chrome">
 <div id="SuiteNavWrapper"><button>App</button></div>
 <div data-automationid="SiteHeader"><a href="/">ExampleSite</a></div>
 <div id="spPageCanvasContent">
  <div data-sp-feature-tag="CanvasComponent.internal.0000">
   <div data-automation-id="Canvas" class="canvas"><div data-automation-id="CanvasLayout" class="layout"></div></div>
  </div>
 </div>
</div></body></html>"""

CLASSIC = """<!doctype html><html lang="it"><head><title>Notizie</title>
<script>var _spPageContextInfo = {};</script></head><body>
<form id="aspnetForm"><div id="s4-workspace"><div id="s4-bodyContainer">
 <div id="suiteBarDelta"><div id="O365_NavHeader"><button>App</button></div></div>
 <div id="s4-ribbonrow"><a href="#">Sfoglia</a></div>
 <div id="s4-titlerow"><div id="titleAreaBox">
  <div id="WebPartWPQ1" webpartid="11111111-1111-4111-8111-111111111111"><input type="search"></div>
 </div></div>
 <div id="contentRow">
  <div id="sideNavBox"><a href="/a">Home</a></div>
  <div id="contentBox"><div id="DeltaPlaceHolderMain">
   <div id="MSOZoneCell_WebPartWPQ2"><div id="WebPartWPQ2" webpartid="22222222-2222-4222-8222-222222222222">
    <div class="ms-rtestate-field"><p>Notizie</p><img src="/n.png"></div></div></div>
   <div id="MSOZoneCell_WebPartWPQ3"><div id="WebPartWPQ3" webpartid="33333333-3333-4333-8333-333333333333">
    <div class="ms-rtestate-field"><a href="/x"></a></div></div></div>
   <div id="MSOZoneCell_WebPartWPQ4"><div id="WebPartWPQ4" webpartid="44444444-4444-4444-8444-444444444444"></div></div>
  </div></div>
 </div>
</div></div></form></body></html>"""


def _run(markup, url=URL):
    from audit.engine import analyze_pages

    page = PageResult(url=url, depth=0, raw_html=markup,
                      diagnostics=PageDiagnostics(status_code=200))
    return analyze_pages([page], url, sharepoint=True, media=False)


class AnEmptyCanvas(unittest.TestCase):

    def test_it_is_recognised_with_no_zones_and_says_why(self):
        _document, zone_map = zones.map_page(EMPTY)
        self.assertTrue(zone_map.recognised)
        self.assertEqual(zone_map.zones, [])
        self.assertEqual(zone_map.page_kind, zones.PAGE_EMPTY_CANVAS)
        self.assertEqual(zone_map.note, "the page's canvas is empty")

    def test_the_run_reports_it_empty_not_unaudited(self):
        result = _run(EMPTY)
        self.assertEqual([d.error for d in result.documents], [None])
        self.assertEqual([d.issues for d in result.documents], [[]])
        self.assertEqual(result.sharepoint["pages_without_canvas"], [])
        self.assertEqual(result.sharepoint["pages_empty"],
                         [{"url": URL, "reason": "empty-canvas",
                           "note": "the page's canvas is empty"}])

    def test_a_canvas_with_content_is_not_empty(self):
        filled = EMPTY.replace('class="layout"></div>',
                               'class="layout"><div class="section"><p>x</p></div></div>')
        _document, zone_map = zones.map_page(filled)
        self.assertNotEqual(zone_map.page_kind, zones.PAGE_EMPTY_CANVAS)


class AClassicPage(unittest.TestCase):

    def test_each_web_part_with_content_is_a_custom_zone(self):
        _document, zone_map = zones.map_page(CLASSIC)
        self.assertEqual(zone_map.page_kind, zones.PAGE_CLASSIC)
        self.assertEqual([(z.kind, z.name) for z in zone_map.zones], [
            ("custom", "Classic web part (WPQ2)"),
            ("custom", "Classic web part (WPQ3)"),
        ])
        self.assertIn('id="WebPartWPQ2"', zone_map.zones[0].evidence)
        self.assertIn("22222222-2222-4222-8222-222222222222", zone_map.zones[0].evidence)

    def test_the_chrome_is_not_a_zone(self):
        _document, zone_map = zones.map_page(CLASSIC)
        # The search box web part in the title area is Microsoft's.
        self.assertNotIn("Classic web part (WPQ1)", [z.name for z in zone_map.zones])
        for region in ("classic-ribbon", "classic-title-area", "classic-nav",
                       "classic-suite-bar"):
            self.assertIn(region, zone_map.platform_regions)

    def test_every_rule_applies_to_the_site_owners_markup(self):
        result = _run(CLASSIC)
        rules = {i.rule_id for d in result.documents for i in d.issues}
        self.assertIn("image-alt", rules)
        self.assertIn("control-name", rules)
        names = {i.details.get("zone_name") for d in result.documents for i in d.issues}
        self.assertEqual(names, {"Classic web part (WPQ2)", "Classic web part (WPQ3)"})
        self.assertEqual(result.sharepoint["pages_classic"], [URL])
        self.assertEqual(result.sharepoint["pages_without_canvas"], [])

    def test_rich_text_outside_a_web_part_is_the_authors(self):
        publishing = CLASSIC.replace(
            '<div id="MSOZoneCell_WebPartWPQ2">',
            '<div class="ms-rtestate-field"><p>Articolo</p></div><div id="MSOZoneCell_WebPartWPQ2">')
        _document, zone_map = zones.map_page(publishing)
        self.assertEqual(zone_map.zones[0].kind, "author")
        self.assertEqual(zone_map.zones[0].name, "Classic page content")

    def test_a_classic_page_with_only_empty_web_parts_is_empty(self):
        bare = CLASSIC.replace('<p>Notizie</p><img src="/n.png">', "").replace(
            '<a href="/x"></a>', "")
        result = _run(bare)
        self.assertEqual(result.sharepoint["pages_empty"][0]["reason"], "classic-empty")

    def test_a_page_that_is_neither_is_still_not_audited(self):
        result = _run("<html><body><main><p>x</p></main></body></html>")
        self.assertIn("no SharePoint canvas", result.documents[0].error)


class TheRunSaysItOnStderr(unittest.TestCase):

    def test_not_audited_empty_and_classic_are_each_counted(self):
        from cli_impl.auditpass import say_zones

        result = SimpleNamespace(sharepoint={
            "pages_without_canvas": ["https://contoso.sharepoint.com/a"],
            "pages_empty": [{"url": "https://contoso.sharepoint.com/b",
                             "reason": "empty-canvas",
                             "note": "the page's canvas is empty"}],
            "pages_classic": ["https://contoso.sharepoint.com/c"]})
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            say_zones(result)
        text = buffer.getvalue()
        self.assertIn("1 page(s) not audited", text)
        self.assertIn("1 page(s) read and empty (the page's canvas is empty)", text)
        self.assertIn("1 classic page(s)", text)

    def test_the_report_section_says_it_in_every_language(self):
        from report.template import _LABELS, _sharepoint_section

        model = SimpleNamespace(sharepoint={
            "skipped": {}, "parts": {},
            "pages_empty": [{"url": "https://contoso.sharepoint.com/b",
                             "reason": "empty-canvas", "note": ""}],
            "pages_classic": ["https://contoso.sharepoint.com/c"]})
        for lang, labels in _LABELS.items():
            with self.subTest(lang=lang):
                html = _sharepoint_section(model, labels)
                self.assertIn("contoso.sharepoint.com/b", html)
                from report.template import _esc
                self.assertIn(_esc(labels["sharepoint_empty_reason"]["empty-canvas"]), html)


if __name__ == "__main__":
    unittest.main()
