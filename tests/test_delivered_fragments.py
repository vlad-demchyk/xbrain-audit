"""Work that is delivered as a piece of somebody else's site.

Two shapes, and neither is the whole thing a scan usually gets pointed at:

* a **WordPress theme or plugin**, handed over on its own. Its templates are
  fragments by construction - `<html>` opens in `header.php` and closes in
  `footer.php` - and the folder carries none of the markers of the
  installation around it. WordPress itself identifies them by a *header
  inside a file*: `Theme Name:` in `style.css`, `Plugin Name:` in the
  plugin's main PHP file.
* a **SharePoint web part**, which is one subtree of a page the tenant owns.
  Auditing the page around it reports the suite bar, the site navigation and
  the comment rail - hundreds of findings against markup the developer
  cannot reach - and buries the handful that are theirs.

The first needed a marker that reads content rather than file names; the
second needed the opposite of the suppression list, "only inside this part",
and a way to survive the identifiers the platform generates.
"""
import tempfile
import unittest
from pathlib import Path

import project_profile
from audit.engine import analyze_document
from audit.within import ScopeNotFound, narrow, stem


class WhatAWordPressDeliveryLooksLike(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_a_theme_is_recognised_by_the_header_in_its_stylesheet(self):
        (self.root / "style.css").write_text(
            "/*\nTheme Name: Municipal\nVersion: 1.0\n*/\n", encoding="utf-8")
        profile = project_profile.detect(self.root)
        self.assertEqual([s.name for s in profile.stacks], ["wordpress-theme"])
        self.assertIn("style.css", profile.evidence["wordpress-theme"])

    def test_a_plugin_is_recognised_by_the_header_in_its_php(self):
        (self.root / "shop-widget.php").write_text(
            "<?php\n/*\nPlugin Name: Shop Widget\n*/\n", encoding="utf-8")
        profile = project_profile.detect(self.root)
        self.assertEqual([s.name for s in profile.stacks],
                         ["wordpress-plugin"])

    def test_a_stylesheet_without_the_header_is_not_a_theme(self):
        """Every project has a `style.css`. The header is the marker, and
        matching the file name alone would call half the web WordPress."""
        (self.root / "style.css").write_text("body { margin: 0 }",
                                             encoding="utf-8")
        self.assertEqual(project_profile.detect(self.root).stacks, [])

    def test_a_theme_template_is_a_fragment_and_keeps_page_rules_off(self):
        """`header.php` opens the document and `footer.php` closes it, so no
        single file is a page. Asking one for a canonical link, an `<h1>` or
        a skip link is asking a piece for a property of the whole."""
        header = self.root / "header.php"
        header.write_text(
            "<!doctype html><html <?php language_attributes(); ?>>"
            "<head><?php wp_head(); ?></head><body>"
            "<header><img src='/logo.png'></header>", encoding="utf-8")
        # Through repo mode, which is the path a theme folder takes:
        # `_is_page_file` is false for `.php`, so nobody ever declares this
        # file a page, and `_document_kind` reads it as the fragment it is.
        import audit
        from models import FileResult

        result = audit.analyze_files(
            [FileResult(path=str(header),
                        raw_text=header.read_text(encoding="utf-8"))],
            str(self.root), media=False, repo_facts=False)
        fired = {issue.rule_id for issue in result.issues()}
        self.assertIn("image-alt", fired)
        for page_level in ("seo-canonical", "seo-open-graph", "page-has-h1",
                           "landmark-regions", "skip-link"):
            with self.subTest(page_level):
                self.assertNotIn(page_level, fired)


class WhatASharePointDeliveryLooksLike(unittest.TestCase):

    PAGE = ('<!doctype html><html lang="en"><head><title>Tenant</title></head>'
            '<body>'
            '<div id="SuiteNavPlaceHolder"><img src="suite.png"><button></button></div>'
            '<nav class="ms-HorizontalNav"><img src="nav.png"></nav>'
            '<div class="CanvasZone_9f8e7d"><section id="WebPartWPQ3">'
            '<h2>Ours</h2><img src="part.png"></section></div>'
            '<footer><img src="foot.png"></footer></body></html>')

    def test_a_web_part_folder_is_recognised_without_the_solution(self):
        with tempfile.TemporaryDirectory() as tmp:
            part = Path(tmp) / "src" / "webparts" / "hello"
            part.mkdir(parents=True)
            (part / "HelloWebPart.ts").write_text("export default class {}",
                                                  encoding="utf-8")
            profile = project_profile.detect(tmp)
        self.assertEqual([s.name for s in profile.stacks], ["spfx"])

    def test_only_the_part_is_read(self):
        whole = {i.rule_id for i in analyze_document(self.PAGE, "p.html").issues}
        part = {i.rule_id for i in
                analyze_document(self.PAGE, "p.html",
                                 within="#WebPartWPQ3").issues}
        self.assertIn("image-alt", part)
        # The tenant's chrome and the page's own head are not this
        # developer's work and are not in the answer.
        self.assertTrue(whole - part)
        for page_level in ("seo-canonical", "seo-title-length", "bp-charset"):
            with self.subTest(page_level):
                self.assertNotIn(page_level, part)

    def test_the_scope_makes_it_a_fragment_not_a_small_page(self):
        """A subtree has no `<head>`, so most page rules go quiet on their
        own - but not all of them. `seo-image-dimensions` is page-level and
        fires happily on a headless document, so without the fragment
        reading a scoped run would report the web part for a property of the
        page it is embedded in."""
        from bs4 import BeautifulSoup

        subtree = str(BeautifulSoup(self.PAGE, "html.parser")
                      .select_one("#WebPartWPQ3"))
        as_page = {i.rule_id for i in
                   analyze_document(subtree, "p.html").issues}
        as_scope = {i.rule_id for i in
                    analyze_document(self.PAGE, "p.html",
                                     within="#WebPartWPQ3").issues}
        self.assertIn("seo-image-dimensions", as_page)
        self.assertNotIn("seo-image-dimensions", as_scope)

    def test_a_generated_suffix_does_not_have_to_be_typed(self):
        """`CanvasZone_9f8e7d` changes between renders and environments. The
        stem is what the developer wrote, and it is what is matched."""
        markup, how = narrow(self.PAGE, ".CanvasZone")
        self.assertEqual(how, "stem")
        self.assertIn("WebPartWPQ3", markup)

    def test_an_exact_match_is_preferred_and_named_as_such(self):
        _markup, how = narrow(self.PAGE, "#WebPartWPQ3")
        self.assertEqual(how, "exact")

    def test_a_selector_that_matches_nothing_is_an_error_not_a_clean_page(self):
        with self.assertRaises(ScopeNotFound):
            narrow(self.PAGE, "#NoSuchPart")
        report = analyze_document(self.PAGE, "p.html", within="#NoSuchPart")
        self.assertIn("matched nothing", report.error or "")
        self.assertEqual(report.issues, [])

    def test_two_web_parts_are_not_confused_by_their_stems(self):
        """`WebPartWPQ3` and `WebPartWPQ7` are two parts on one page, and a
        stem that collapsed them would audit the wrong one."""
        with self.assertRaises(ScopeNotFound):
            narrow(self.PAGE, "#WebPartWPQ7")

    def test_the_stem_strips_what_platforms_generate(self):
        for generated, wanted in (("ControlZone_1a2b3c", "ControlZone"),
                                  ("root-137", "root"),
                                  ("ms-Button", "ms-Button")):
            with self.subTest(generated):
                self.assertEqual(stem(generated), wanted)


class ManyWebPartsInOneRepository(unittest.TestCase):
    """The shape a real SharePoint solution has.

    The repositories this was measured against ship **30** and **19** web
    parts. Three questions follow and they are not the same one: a single
    part as code (the folder is the scope), a single part on the site
    (`--within`), and *this repository's parts across the whole site* -
    which is `--web-parts`. With no scoping flag and a repository given, the
    answer stays the whole site and the repository names the file behind a
    finding.
    """

    PAGE = ('<!doctype html><html lang="en"><head><title>Intranet</title></head>'
            '<body><div id="SuiteNavPlaceHolder"><img src="suite.png"></div>'
            '<div data-sp-web-part-id="bc4ab074-e95b-45ee-bfc1-3eaf0c0132ee">'
            '<img src="ours.png"></div>'
            '<div class="ricerche_9a8b7c"><img src="alsoOurs.png"></div>'
            '<div data-sp-web-part-id="00000000-0000-0000-0000-000000000000">'
            '<img src="someone-elses.png"></div></body></html>')

    def _repo(self, tmp, alias, identifier, scss=""):
        """A minimal SPFx solution: one manifest, JSONC as the generator
        writes it - comments that contain quotes, and a trailing comma."""
        folder = Path(tmp) / "src" / "webparts" / alias.lower()
        folder.mkdir(parents=True)
        (folder / f"{alias}.manifest.json").write_text(
            '{\n'
            '  "$schema": "https://developer.microsoft.com/schema.json",\n'
            f'  "id": "{identifier}",\n'
            f'  "alias": "{alias}",\n'
            '  "componentType": "WebPart",\n'
            '  // The "*" signifies that the version comes from package.json\n'
            '  "version": "*",\n'
            '  "preconfiguredEntries": [{ "title": { "default": "Ours" } }],\n'
            '}\n', encoding="utf-8")
        if scss:
            (folder / f"{alias}.module.scss").write_text(scss, encoding="utf-8")
        return tmp

    def test_a_jsonc_manifest_is_read(self):
        """`json.loads` refuses comments and trailing commas, and every SPFx
        manifest has both. Measured on a real solution: reading them as JSON
        found 2 web parts where there are 30."""
        from audit.spfx import web_parts

        with tempfile.TemporaryDirectory() as tmp:
            self._repo(tmp, "OursWebPart",
                       "bc4ab074-e95b-45ee-bfc1-3eaf0c0132ee")
            found = web_parts(tmp)
        self.assertEqual([p.alias for p in found], ["OursWebPart"])
        self.assertEqual(found[0].title, "Ours")

    def test_a_part_is_found_by_its_guid(self):
        import audit
        from audit.spfx import web_parts

        with tempfile.TemporaryDirectory() as tmp:
            self._repo(tmp, "OursWebPart",
                       "bc4ab074-e95b-45ee-bfc1-3eaf0c0132ee")
            parts = web_parts(tmp)
            page = Path(tmp) / "page.html"
            page.write_text(self.PAGE, encoding="utf-8")
            result = audit.analyze_page_file(str(page), web_parts=parts)
        issues = [i for d in result.documents for i in d.issues]
        self.assertTrue(issues)
        for issue in issues:
            with self.subTest(issue.rule_id):
                self.assertEqual(issue.details["web_part"], "OursWebPart")
                self.assertIn("exact", issue.details["matched_by"])
        # The tenant's chrome and another vendor's part are not in the answer.
        snippets = " ".join(str(i.snippet) for i in issues)
        self.assertNotIn("suite.png", snippets)
        self.assertNotIn("someone-elses.png", snippets)

    def test_a_part_without_a_guid_in_the_page_is_found_by_its_class(self):
        import audit
        from audit.spfx import web_parts

        with tempfile.TemporaryDirectory() as tmp:
            self._repo(tmp, "RicercheWebPart",
                       "36abb284-0fc8-486d-9abf-eedc088593d1",
                       scss=".ricerche { display: block; }")
            parts = web_parts(tmp)
            page = Path(tmp) / "page.html"
            page.write_text(self.PAGE, encoding="utf-8")
            result = audit.analyze_page_file(str(page), web_parts=parts)
        issues = [i for d in result.documents for i in d.issues]
        self.assertTrue(issues)
        self.assertIn("class", issues[0].details["matched_by"])
        self.assertIn("alsoOurs.png", str(issues[0].snippet)
                      + " ".join(str(i.snippet) for i in issues))

    def test_every_placement_of_a_part_is_read_not_only_the_first(self):
        """A part put on a page twice is two deliveries of the same code.
        Only the first used to be audited, and the second went unread
        without the report saying so."""
        import audit
        from audit.spfx import web_parts

        guid = "bc4ab074-e95b-45ee-bfc1-3eaf0c0132ee"
        page_markup = ('<!doctype html><html lang="en"><head><title>x</title>'
                       '</head><body>'
                       f'<div data-sp-web-part-id="{guid}"><img src="first.png"></div>'
                       '<p>between</p>'
                       f'<div data-sp-web-part-id="{guid}"><img src="second.png"></div>'
                       '</body></html>')
        with tempfile.TemporaryDirectory() as tmp:
            self._repo(tmp, "OursWebPart", guid)
            parts = web_parts(tmp)
            page = Path(tmp) / "page.html"
            page.write_text(page_markup, encoding="utf-8")
            result = audit.analyze_page_file(str(page), web_parts=parts)
        self.assertEqual(len(result.documents), 2)
        snippets = " ".join(str(i.snippet) for d in result.documents
                            for i in d.issues)
        self.assertIn("first.png", snippets)
        self.assertIn("second.png", snippets)
        instances = {i.details.get("instance") for d in result.documents
                     for i in d.issues}
        self.assertEqual(instances, {1, 2})

    def test_narrow_all_keeps_the_outermost_match_only(self):
        """A part's wrapper and an element inside it that also matches are
        one placement: reading both would report each defect twice."""
        from bs4 import BeautifulSoup

        from audit.within import narrow_all

        document = BeautifulSoup(
            '<div class="part_1a2b3c"><div class="part_9f8e7d">x</div></div>'
            '<div class="part_4d5e6f">y</div>', "html.parser")
        found = narrow_all(document, ['[data-none="1"]', ".part"])
        self.assertEqual([element.get_text() for element, _how, _s in found],
                         ["x", "y"])
        self.assertEqual({how for _e, how, _s in found}, {"stem"})
        with self.assertRaises(ScopeNotFound):
            narrow_all(document, ['[data-none="1"]'])

    def test_a_page_carrying_none_of_them_produces_no_documents(self):
        """A repository ships thirty parts and a page carries three.
        Reporting the twenty-seven as absent would be a finding about the
        tenant's page composition, which is not this repository's business."""
        import audit
        from audit.spfx import web_parts

        with tempfile.TemporaryDirectory() as tmp:
            self._repo(tmp, "OursWebPart",
                       "11111111-1111-1111-1111-111111111111")
            parts = web_parts(tmp)
            page = Path(tmp) / "page.html"
            page.write_text(self.PAGE, encoding="utf-8")
            result = audit.analyze_page_file(str(page), web_parts=parts)
        self.assertEqual(result.documents, [])


class MarkupInsideATemplateLiteral(unittest.TestCase):
    """A classic SPFx web part builds its interface in a backtick string.

    `.ts`, `.js` and `.mjs` are skipped as files, and rightly - in them a
    `<` is an operator, and `if (a < b)` handed to an HTML parser is an open
    tag swallowing the rest of the file. But a template literal is not code.
    Measured 2026-09-01 on a real SharePoint solution: **72 of 168** `.ts`
    files build markup this way, none of it was ever read, and reading it
    finds 132 things - 60 controls with no accessible name, 21 images with
    no alt, 24 links opening a new tab without `rel`.
    """

    SOURCE = '''
import styles from './X.module.scss';
export default class X {
  private count = 0;
  public render(): void {
    // A comparison, not a tag: this must stay unread.
    if (this.count < 3) { this.count = this.count + 1; }
    this.domElement.innerHTML = `
      <div class="${styles.wrapper}">
        <input type="text" placeholder="Search" id="q">
        <img src="logo.png">
      </div>`;
  }
}
'''

    def _findings(self, source, name="X.ts"):
        import audit
        from models import FileResult

        result = audit.analyze_files(
            [FileResult(path=f"/repo/{name}", raw_text=source)],
            "/repo", media=False, repo_facts=False)
        return [i for d in result.documents for i in d.issues]

    def test_the_markup_in_the_literal_is_read(self):
        rules = {i.rule_id for i in self._findings(self.SOURCE)}
        self.assertIn("control-name", rules)
        self.assertIn("image-alt", rules)

    def test_the_code_around_it_is_still_not_read(self):
        """`this.count < 3` is arithmetic. A parser told to read it as
        markup opens a tag and never closes it."""
        for issue in self._findings(self.SOURCE):
            with self.subTest(issue.rule_id):
                self.assertNotIn("count", str(issue.snippet))

    def test_a_finding_points_at_the_line_the_literal_starts_on(self):
        found = self._findings(self.SOURCE)
        self.assertTrue(found)
        for issue in found:
            with self.subTest(issue.rule_id):
                self.assertEqual(issue.line, 8)
                self.assertEqual(issue.details["embedded_in"],
                                 "template literal")

    def test_a_file_with_no_markup_in_its_strings_produces_nothing(self):
        self.assertEqual(
            self._findings("const q = `SELECT * FROM t WHERE a < 5`;\n"), [])

    def test_an_interpolation_becomes_a_value_not_a_hole(self):
        """`class="${styles.wrapper}"` must read as an attribute that is
        present. Left empty, every rule that asks "is there a class" would
        be answered wrongly by the substitution rather than by the file."""
        from audit.embedded import PLACEHOLDER, markup_fragments

        markup, _line = markup_fragments(self.SOURCE)[0]
        self.assertIn(f'class="{PLACEHOLDER}"', markup)
        self.assertNotIn("${", markup)

    def test_a_tsx_file_is_left_to_the_ordinary_path(self):
        """`.tsx` is audited as markup already; reading its literals too
        would report the same element twice."""
        from audit.embedded import markup_fragments

        self.assertTrue(markup_fragments(self.SOURCE))
        rules = {i.rule_id for i in self._findings(self.SOURCE, name="X.tsx")}
        self.assertNotIn("embedded", " ".join(rules))


class WhatTheBrowserPassDoesWhenScoped(unittest.TestCase):

    def test_axe_is_given_the_include_context(self):
        from audit.browser import BrowserAuditOptions, axe_script

        script = axe_script(BrowserAuditOptions(within="#WebPartWPQ3"))
        self.assertIn('"include"', script)
        self.assertIn("#WebPartWPQ3", script)

    def test_the_engines_that_read_the_whole_document_are_switched_off(self):
        """HTML_CodeSniffer walks from `document`, the state pass tabs
        through the page, and a measurement is a property of the load. Left
        on, they would answer about the tenant's page under a report the
        caller narrowed on purpose."""
        import argparse
        from unittest import mock

        from audit.engine import AccessibilityResult, DocumentReport
        from cli_impl import auditpass

        result = AccessibilityResult(root="https://x.test/", mode="web")
        result.documents = [DocumentReport(source="https://x.test/")]
        seen = {}

        def _fake(urls, options, sizes, on_page=None, markup=None):
            seen["options"] = options
            return []

        args = argparse.Namespace(within="#WebPartWPQ3", breakpoints=None)
        with mock.patch("audit.driver.available", return_value=(True, "")), \
                mock.patch.object(auditpass, "_audit_at_widths", _fake), \
                mock.patch("audit.browser.merge_into_document"):
            auditpass._run_browser_pass(result,
                                        mock.Mock(selectors=[], rules=[]),
                                        args)
        options = seen["options"]
        self.assertEqual(options.within, "#WebPartWPQ3")
        self.assertTrue(options.run_axe)
        self.assertFalse(options.run_htmlcs)
        self.assertFalse(options.run_states)
        self.assertFalse(options.run_measurements)


if __name__ == "__main__":
    unittest.main()
