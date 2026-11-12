"""Findings that were wrong, measured on a run over sixteen real targets.

Ten live sites and six repositories produced 3348 findings, and reading the
top rules by volume is what turned four of them into defects rather than
opinions. Each test here is the failing case that measurement found.
"""
import subprocess
import unittest
from pathlib import Path

import audit.rules  # noqa: F401 - registers the rules
from audit import repo_facts
from audit.engine import SKIP_AUDIT_DIRS, analyze_document


def _rules_of(markup: str, source: str = "https://example.test/page") -> list:
    return [i.rule_id for i in analyze_document(markup, source).issues]


class AbbreviationsAreWordsNotSubstrings(unittest.TestCase):
    """446 findings, and the words were not abbreviations.

    `"UI" in text` matched "building" and "guide", `PR` matched "PRODUCT",
    `HR` matched "THROUGH". The rule also carried a comment promising one
    finding per page per abbreviation and had never done it.
    """

    def test_a_word_that_merely_contains_the_letters_is_not_an_abbreviation(self):
        markup = ("<html><body><p>We are building a guide through PRODUCT "
                  "pages for our users.</p></body></html>")
        self.assertNotIn("abbreviation-expansion", _rules_of(markup))

    def test_a_real_abbreviation_still_reports(self):
        markup = "<html><body><p>The API is documented.</p></body></html>"
        self.assertIn("abbreviation-expansion", _rules_of(markup))

    def test_the_same_abbreviation_reports_once_per_document(self):
        markup = ("<html><body><p>The API is here.</p><p>The API is there.</p>"
                  "<p>And the API again.</p></body></html>")
        found = [r for r in _rules_of(markup) if r == "abbreviation-expansion"]
        self.assertEqual(len(found), 1)


class TargetBlankIsAboutSomebodyElsesPage(unittest.TestCase):
    """325 findings, 144 of them at the page's own host.

    The risk is that the opened page steers the tab that opened it. A page
    opening its own site cannot be that attacker without already being one.
    """

    def test_a_link_to_the_same_host_is_not_a_finding(self):
        markup = ('<html><body><a href="https://example.test/about" '
                  'target="_blank">About</a></body></html>')
        self.assertNotIn("bp-target-blank", _rules_of(markup))

    def test_a_relative_link_is_not_a_finding(self):
        markup = '<html><body><a href="/about" target="_blank">About</a></body></html>'
        self.assertNotIn("bp-target-blank", _rules_of(markup))

    def test_a_cross_origin_link_still_reports(self):
        markup = ('<html><body><a href="https://elsewhere.test/x" '
                  'target="_blank">Out</a></body></html>')
        self.assertIn("bp-target-blank", _rules_of(markup))

    def test_rel_noopener_answers_it(self):
        markup = ('<html><body><a href="https://elsewhere.test/x" target="_blank" '
                  'rel="noopener">Out</a></body></html>')
        self.assertNotIn("bp-target-blank", _rules_of(markup))


class IntegrityIsAboutSomebodyElsesScript(unittest.TestCase):
    """61 of 162 findings were the site's own asset subdomain."""

    def test_an_asset_subdomain_of_the_page_is_the_page(self):
        markup = ('<html><head><script src="https://assets.example.test/a.js">'
                  '</script></head></html>')
        self.assertNotIn("sec-script-integrity",
                         _rules_of(markup, "https://www.example.test/"))

    def test_a_genuinely_foreign_script_still_reports(self):
        markup = ('<html><head><script src="https://cdn.other.test/a.js">'
                  '</script></head></html>')
        self.assertIn("sec-script-integrity",
                      _rules_of(markup, "https://www.example.test/"))


class FixturesAreNotTheProject(unittest.TestCase):
    def test_the_two_modules_agree_on_what_a_fixture_directory_is(self):
        import project_profile

        for name in ("fixtures", "__fixtures__", "testdata"):
            self.assertIn(name, SKIP_AUDIT_DIRS)
            self.assertIn(name, project_profile._MARKER_BLIND)


class GitCouldNotLookIsNotAnAnswer(unittest.TestCase):
    """A `serious` credential finding produced by a race.

    An audit that ran while a commit held `index.lock` reported this
    repository's ignored `.env.e2e.local` as unignored, and the next run did
    not. `git check-ignore` speaks through its exit code - 0 ignored, 1 not
    ignored, anything else "I could not look" - and the third was being read
    as the second.
    """

    def _repo(self) -> Path:
        import tempfile

        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True,
                       capture_output=True)
        (root / ".gitignore").write_text(".env.*\n", encoding="utf-8")
        (root / ".env.local").write_text("SECRET=1\n", encoding="utf-8")
        return root

    def test_an_ignored_env_file_is_not_reported(self):
        facts = repo_facts.read_facts(self._repo())
        self.assertEqual(facts.exposed_env, [])

    def test_the_exit_codes_are_what_the_fix_rests_on(self):
        root = self._repo()
        self.assertEqual(
            repo_facts._git_status(root, "check-ignore", "-q", "--", ".env.local"), 0)
        self.assertEqual(
            repo_facts._git_status(root, "check-ignore", "-q", "--", "README.md"), 1)
        # No path at all: git refuses, and that must not read as "not ignored".
        self.assertNotIn(
            repo_facts._git_status(root, "check-ignore", "-q", "--"), (0, 1))

    def test_an_unanswerable_check_stays_quiet_and_says_why(self):
        facts = repo_facts.RepoFacts()
        facts.is_git = True
        quiet = repo_facts._git_ignores(Path("/nonexistent-repo-xyz"),
                                        ".env.local", facts)
        self.assertTrue(quiet)
        self.assertTrue(facts.git_unavailable)


class AFormatNobodyLookedAt(unittest.TestCase):
    """430 of 514 `image-modern-format` findings were about bytes nobody saw.

    Wix, Squarespace, Photon, imgix, Cloudflare and Next.js all serve WebP
    from a `.jpg` address to a browser that accepts it. The extension names
    the source file; a pipeline decides what arrives. Establishing which
    needs a request with an `Accept` header, so the rule says nothing there.
    """

    def test_a_negotiating_cdn_is_not_a_legacy_format(self):
        markup = ('<html><body><img src="https://static.wixstatic.com/media/'
                  'abc~mv2.jpg/v1/fill/w_600/photo.jpg"></body></html>')
        self.assertNotIn("image-modern-format", _rules_of(markup))

    def test_a_transformed_url_is_not_a_legacy_format(self):
        markup = '<html><body><img src="/_next/image?url=%2Fa.png&w=640"></body></html>'
        self.assertNotIn("image-modern-format", _rules_of(markup))

    def test_a_plain_static_file_still_reports(self):
        markup = '<html><body><img src="/img/photo.jpg"></body></html>'
        self.assertIn("image-modern-format", _rules_of(markup))


class TwoThingsAtOnePlaceAreTwoFindings(unittest.TestCase):
    """`Issue.key` made the element the whole identity.

    It was `selector or snippet`, so two abbreviations in one paragraph were
    one finding: the second was dropped as a duplicate of the first at the
    same selector.
    """

    def test_both_abbreviations_in_one_paragraph_survive(self):
        markup = "<html><body><p>Use HTML and CSS.</p></body></html>"
        found = [i for i in analyze_document(markup, "t").issues
                 if i.rule_id == "abbreviation-expansion"]
        self.assertEqual({i.details["abbreviation"] for i in found}, {"HTML", "CSS"})

    def test_two_elements_are_still_two_problems(self):
        # The counterpart, and the thing the wider key must not break: two
        # images missing `alt` are two jobs even when the markup matches.
        markup = '<html><body><img src="a.png"><img src="a.png"></body></html>'
        found = [i for i in analyze_document(markup, "t").issues
                 if i.rule_id == "image-alt"]
        self.assertEqual(len(found), 2)


class NamedThingsAreNotEmpty(unittest.TestCase):
    def test_a_logo_link_with_a_titled_svg_is_not_an_empty_link(self):
        markup = ('<html><body><a href="/"><svg><title>Home</title></svg></a>'
                  '</body></html>')
        self.assertNotIn("seo-empty-link", _rules_of(markup))

    def test_a_link_with_nothing_in_it_still_reports(self):
        markup = '<html><body><a href="/"><svg></svg></a></body></html>'
        self.assertIn("seo-empty-link", _rules_of(markup))


class SpaceIsReservedHoweverItIsWritten(unittest.TestCase):
    def test_inline_width_and_height_reserve_the_box(self):
        markup = ('<html><body><img src="a.png" style="width:96px;height:96px">'
                  '</body></html>')
        self.assertNotIn("seo-image-dimensions", _rules_of(markup))

    def test_a_deliberately_prioritised_image_is_not_told_to_defer(self):
        images = "".join(f'<img src="{n}.png">' for n in range(4))
        markup = (f'<html><body>{images}'
                  '<img src="hero.png" fetchpriority="high"></body></html>')
        found = [i for i in analyze_document(markup, "t").issues
                 if i.rule_id == "perf-image-loading"
                 and "hero" in (i.details or {}).get("src", "")]
        self.assertEqual(found, [])


class AnIconIsNotAFormField(unittest.TestCase):
    def test_a_duplicate_id_inside_svg_is_lighter(self):
        markup = ('<html><body>'
                  '<svg><filter id="f0"></filter></svg>'
                  '<svg><filter id="f0"></filter></svg></body></html>')
        found = [i for i in analyze_document(markup, "t").issues
                 if i.rule_id == "duplicate-id"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "minor")
        self.assertTrue(found[0].details["in_svg"])

    def test_a_duplicate_id_in_the_page_keeps_its_weight(self):
        markup = ('<html><body><input id="email"><input id="email"></body></html>')
        found = [i for i in analyze_document(markup, "t").issues
                 if i.rule_id == "duplicate-id"]
        self.assertEqual(found[0].severity, "moderate")


class AControlNobodyCanReachNeedsNoName(unittest.TestCase):
    """`critical` findings about elements that are not controls.

    Every upload button in the world hides a file input and clicks it from
    script. Measured on `XFormat`: `<input type="file" hidden>` and the same
    with `style="display:none"` were reported as unnamed controls, on the
    rule whose whole value is that a `critical` here is worth acting on.
    """

    def test_a_hidden_file_input_is_not_reported(self):
        markup = '<html><body><input type="file" hidden onchange="x"></body></html>'
        self.assertNotIn("control-name", _rules_of(markup))

    def test_display_none_counts_too(self):
        markup = '<html><body><input type="file" style="display:none"></body></html>'
        self.assertNotIn("control-name", _rules_of(markup))

    def test_a_hidden_ancestor_hides_what_is_inside_it(self):
        markup = '<html><body><div aria-hidden="true"><button></button></div></body></html>'
        self.assertNotIn("control-name", _rules_of(markup))

    def test_a_visible_control_with_no_name_still_reports(self):
        self.assertIn("control-name", _rules_of("<html><body><button></button></body></html>"))


class WhatOnlyABrowserKnows(unittest.TestCase):
    """`aria-controls` points at markup the page has not built yet.

    A dropdown Alpine renders on click, a Wix panel that appears on focus:
    a fetched page has not clicked anything. A missing *name*, by contrast,
    is a fact about the page as served.
    """

    def test_a_dangling_aria_controls_is_not_settled(self):
        markup = '<html><body><button aria-controls="menu">M</button></body></html>'
        found = [i for i in analyze_document(markup, "https://t/").issues
                 if i.rule_id == "aria-reference-broken"]
        self.assertEqual(found[0].confidence, "needs-browser")

    def test_a_dangling_name_reference_is_settled(self):
        markup = '<html><body><div aria-labelledby="gone">x</div></body></html>'
        found = [i for i in analyze_document(markup, "https://t/").issues
                 if i.rule_id == "aria-reference-broken"]
        self.assertEqual(found[0].confidence, "exact")

    def test_an_id_with_a_space_can_never_resolve(self):
        # No browser makes this work: ids cannot contain whitespace.
        markup = '<html><body><div aria-owns="two words">x</div></body></html>'
        found = [i for i in analyze_document(markup, "https://t/").issues
                 if i.rule_id == "aria-reference-broken"]
        self.assertEqual(found[0].confidence, "exact")


class DecisionsTheAuthorAlreadyMade(unittest.TestCase):
    def test_an_explicitly_eager_image_is_left_alone(self):
        images = "".join(f'<img src="{n}.png" alt="x">' for n in range(4))
        markup = f'<html><body>{images}<img src="e.png" alt="x" loading="eager"></body></html>'
        found = [i for i in analyze_document(markup, "https://t/").issues
                 if i.rule_id == "perf-image-loading"]
        self.assertEqual(len(found), 1)

    def test_an_image_with_no_address_loads_nothing(self):
        images = "".join(f'<img src="{n}.png" alt="x">' for n in range(4))
        markup = f'<html><body>{images}<img alt="" style="aspect-ratio:3/4"></body></html>'
        found = [i for i in analyze_document(markup, "https://t/").issues
                 if i.rule_id == "perf-image-loading"]
        self.assertEqual(len(found), 1)

    def test_the_recommended_async_css_pattern_is_not_a_defect(self):
        markup = ('<html><head><link rel="stylesheet" media="print" href="/a.css" '
                  'onload="this.media=\'all\'"></head></html>')
        self.assertNotIn("bp-inline-handlers", _rules_of(markup))

    def test_an_inline_handler_on_a_control_still_reports(self):
        markup = '<html><body><a href="/x" onclick="go()">x</a></body></html>'
        self.assertIn("bp-inline-handlers", _rules_of(markup))

    def test_nomodule_is_the_browsers_own_opt_out(self):
        markup = ('<html><head><script nomodule src="https://cdn.other.test/p.js">'
                  '</script></head></html>')
        self.assertNotIn("perf-third-party-sync",
                         _rules_of(markup, "https://www.example.test/"))


class ContextIsPartOfLinkPurpose(unittest.TestCase):
    def test_a_title_that_says_what_the_link_is_for_answers_it(self):
        markup = '<html><body><a href="/e/" title="More Events">More</a></body></html>'
        self.assertNotIn("link-text-vague", _rules_of(markup))

    def test_vague_text_with_no_context_still_reports(self):
        self.assertIn("link-text-vague",
                      _rules_of('<html><body><a href="/e/">More</a></body></html>'))


class TheSitesOwnSubdomainIsTheSite(unittest.TestCase):
    def test_a_link_to_the_forum_is_not_tabnabbing(self):
        markup = ('<html><body><a href="https://forum.example.test/" target="_blank">'
                  'Forum</a></body></html>')
        self.assertNotIn("bp-target-blank",
                         _rules_of(markup, "https://www.example.test/"))


if __name__ == "__main__":
    unittest.main()


class ADuplicateIdNothingPointsAt(unittest.TestCase):
    """WCAG 2.2 dropped 4.1.1: a duplicate id harms where it is referenced
    (or on a control a label will point at). Seen on a live intranet: 52 at
    one weight, most of them unreferenced wrapper ids. T-2823."""

    def _severity(self, markup):
        found = [i for i in analyze_document(markup, "t").issues
                 if i.rule_id == "duplicate-id"]
        self.assertEqual(len(found), 1)
        return found[0].severity

    def test_an_unreferenced_wrapper_is_a_note(self):
        self.assertEqual(self._severity(
            '<html><body><div id="w">a</div><div id="w">b</div></body></html>'), "minor")

    def test_a_referenced_one_keeps_its_weight(self):
        self.assertEqual(self._severity(
            '<html><body><p id="d">a</p><p id="d">b</p>'
            '<button aria-describedby="d">Go</button></body></html>'), "moderate")
        self.assertEqual(self._severity(
            '<html><body><a href="#s">skip</a><div id="s">a</div><div id="s">b</div>'
            '</body></html>'), "moderate")
