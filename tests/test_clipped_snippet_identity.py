"""A clipped snippet is still the element it was cut from.

`base.snippet_of` clips an opening tag at 160 characters and appends an
ellipsis; axe quotes the whole tag. Compared as text, the static `image-alt`
on an image with a long CDN address and axe's `image-alt` on the same image
were two elements: on a live SharePoint intranet the same images were listed
58 times by one engine and 23 times by the other. The same cut defeated the
browser's settling of `perf-image-loading` (a 120-character `src` against a
500-character one), so header icons the browser had measured above the fold
were reported, as `exact`, with "add loading=lazy".

And a page that is several documents (a SharePoint page is one per zone) must
still meet the browser's findings in each of them.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from audit import browser
from audit.base import (
    ACCESSIBILITY, EXACT, NEEDS_BROWSER, SERIOUS, Issue, RuleRegistry,
    snippet_of,
)

LONG = ("https://cdn.contoso.example/sites/ExampleSite/assets/icons/"
        "generated/2026/11/very/long/path/that/keeps/going/and/going/"
        "until/it/passes/the/clip/limit/icon-a-0123456789abcdef.svg")
OTHER = LONG.replace("icon-a-", "icon-b-")


def _issue(rule_id, engine, snippet, selector="", source="https://contoso.sharepoint.com/p"):
    return Issue(rule_id=rule_id, severity=SERIOUS, category=ACCESSIBILITY,
                 source=source, engine=engine, snippet=snippet,
                 selector=selector)


def _static_snippet(src: str) -> str:
    from bs4 import BeautifulSoup

    tag = BeautifulSoup(f'<img src="{src}" class="icon">', "html.parser").img
    return snippet_of(tag)


class AClippedSnippetIsAPattern(unittest.TestCase):

    def test_the_static_snippet_is_really_clipped(self):
        snippet = _static_snippet(LONG)
        self.assertTrue(snippet.endswith("…"))
        self.assertNotIn(">", snippet)

    def test_static_and_axe_on_one_long_image_become_one_row(self):
        kept = browser.deduplicate([
            _issue("image-alt", "static", _static_snippet(LONG), "div > img"),
            _issue("axe:image-alt", "axe", f'<img src="{LONG}" class="icon">', "img"),
        ])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].details["also_found_by"], ["axe"])

    def test_the_merge_holds_with_the_page_as_evidence(self):
        markup = f'<body><img src="{LONG}" class="icon"><img src="{OTHER}"></body>'
        kept = browser.deduplicate([
            _issue("image-alt", "static", _static_snippet(LONG), "div > img"),
            _issue("axe:image-alt", "axe", f'<img src="{LONG}" class="icon">', "img"),
        ], markup=markup)
        self.assertEqual(len(kept), 1)

    def test_two_images_the_pattern_fits_are_not_merged_on_the_page(self):
        # Both images start with the same 150 characters: the clipped static
        # snippet fits both, so it identifies neither.
        markup = (f'<body><img src="{LONG}" class="icon">'
                  f'<img src="{OTHER}" class="icon"></body>')
        kept = browser.deduplicate([
            _issue("image-alt", "static", _static_snippet(LONG), "div > img"),
            _issue("axe:image-alt", "axe", f'<img src="{LONG}" class="icon">', "img"),
        ], markup=markup)
        self.assertEqual(len(kept), 2)

    def test_a_pattern_is_paired_with_one_element_never_two(self):
        # No page to count on: the pattern takes the first image it fits and
        # leaves the second axe finding standing, rather than hide it.
        kept = browser.deduplicate([
            _issue("image-alt", "static", _static_snippet(LONG), "div > img"),
            _issue("axe:image-alt", "axe", f'<img src="{LONG}" class="icon">', "img"),
            _issue("axe:image-alt", "axe", f'<img src="{OTHER}" class="icon">', "img:nth-child(2)"),
        ])
        self.assertEqual(len(kept), 2)

    def test_an_element_the_pattern_does_not_fit_is_not_merged(self):
        kept = browser.deduplicate([
            _issue("image-alt", "static", _static_snippet(LONG), "div > img"),
            _issue("axe:image-alt", "axe", '<img src="/short.png" class="icon">', "img"),
        ])
        self.assertEqual(len(kept), 2)

    def test_one_engine_never_merges_with_itself_through_a_pattern(self):
        kept = browser.deduplicate([
            _issue("image-alt", "static", _static_snippet(LONG), "div > img:nth-of-type(1)"),
            _issue("image-alt", "static", f'<img src="{LONG}" class="icon">', "div > img:nth-of-type(2)"),
        ])
        self.assertEqual(len(kept), 2)

    def test_a_short_clip_identifies_nothing(self):
        self.assertEqual(browser._element_key(_issue("x", "static", "<img src=\"/a…")), "")


class APageOfSeveralDocuments(unittest.TestCase):

    def test_the_browser_finding_meets_the_static_one_in_another_zone(self):
        source = "https://contoso.sharepoint.com/sites/ExampleSite/p.aspx"
        first = SimpleNamespace(source=source, error="", issues=[
            _issue("heading-order", "static", "<h4>", "h4", source)])
        second = SimpleNamespace(source=source, error="", issues=[
            _issue("image-alt", "static", _static_snippet(LONG), "div > img", source)])
        result = SimpleNamespace(documents=[first, second], browser_errors=[],
                                 coverage={})
        audit = SimpleNamespace(error="", engine_errors={}, measurements={},
                                html="", issues=[
            _issue("axe:image-alt", "axe", f'<img src="{LONG}" class="icon">', "img", source)])
        self.assertTrue(browser.merge_page_audit(result, first, audit))
        rules = [i.rule_id for d in (first, second) for i in d.issues]
        self.assertEqual(rules, ["heading-order", "image-alt"])
        self.assertEqual(second.issues[0].details["also_found_by"], ["axe"])

    def test_what_no_zone_absorbs_lands_on_the_page_document(self):
        source = "https://contoso.sharepoint.com/p"
        first = SimpleNamespace(source=source, error="", issues=[])
        second = SimpleNamespace(source=source, error="", issues=[])
        result = SimpleNamespace(documents=[first, second], browser_errors=[],
                                 coverage={})
        audit = SimpleNamespace(error="", engine_errors={}, measurements={},
                                html="", issues=[
            _issue("axe:list", "axe", "<ul>", "ul", source)])
        browser.merge_page_audit(result, first, audit)
        self.assertEqual([i.rule_id for i in first.issues], ["axe:list"])
        self.assertEqual(second.issues, [])

    def test_static_findings_of_two_zones_never_merge_with_each_other(self):
        source = "https://contoso.sharepoint.com/p"
        same = "div:nth-of-type(1) > button:nth-of-type(1)"
        first = SimpleNamespace(source=source, error="", issues=[
            _issue("control-name", "static", "<button>", same, source)])
        second = SimpleNamespace(source=source, error="", issues=[
            _issue("control-name", "static", "<button>", same, source)])
        result = SimpleNamespace(documents=[first, second], browser_errors=[],
                                 coverage={})
        audit = SimpleNamespace(error="", engine_errors={}, measurements={},
                                html="", issues=[])
        browser.merge_page_audit(result, first, audit)
        self.assertEqual(len(first.issues) + len(second.issues), 2)


class ImageLoadingIsSettledOnTheWholeAddress(unittest.TestCase):

    def _finding(self):
        from bs4 import BeautifulSoup

        markup = "".join(f'<img src="/i{n}.png">' for n in range(3))
        markup += f'<img src="{LONG}">'
        document = BeautifulSoup(markup, "html.parser")
        rule = RuleRegistry.create("perf-image-loading")
        context = SimpleNamespace(source="https://contoso.sharepoint.com/p",
                                  locate=lambda tag: ("img", None))
        found = rule.check(document, context)
        self.assertEqual(len(found), 1)
        return found[0]

    def test_the_finding_says_it_needs_a_browser(self):
        # It was `exact` by default: the rule declared `needs-browser` and
        # never put it on the finding.
        self.assertEqual(self._finding().confidence, NEEDS_BROWSER)

    def test_a_long_address_the_browser_measured_above_the_fold_is_dropped(self):
        found = self._finding()
        self.assertEqual(browser.settle_image_loading(
            [found], {"imagesAboveFold": [LONG[:500]]}), [])

    def test_an_address_the_browser_did_not_list_stays_unsettled(self):
        found = self._finding()
        kept = browser.settle_image_loading([found], {"imagesAboveFold": ["/i0.png"]})
        self.assertEqual(kept, [found])
        self.assertNotEqual(kept[0].confidence, EXACT)


    def test_an_address_measured_below_the_fold_is_settled_as_exact(self):
        found = self._finding()
        kept = browser.settle_image_loading(
            [found], {"imagesAboveFold": ["/i0.png"], "imagesBelowFold": [LONG]})
        self.assertEqual(kept, [found])
        self.assertEqual(kept[0].confidence, EXACT)

    def test_an_address_both_above_and_below_counts_as_above(self):
        found = self._finding()
        self.assertEqual(browser.settle_image_loading(
            [found], {"imagesAboveFold": [LONG], "imagesBelowFold": [LONG]}), [])


class EveryRuleStampsTheConfidenceItDeclares(unittest.TestCase):

    def test_no_static_rule_drops_its_declared_confidence(self):
        """A rule that declares less than `exact` and builds an `Issue`
        without passing it reports `exact`: the dataclass default. That is
        how 227 `perf-image-loading` guesses became facts."""
        import ast
        from pathlib import Path

        offenders = []
        for path in sorted(Path("audit/rules").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                declared = None
                for statement in node.body:
                    if isinstance(statement, ast.Assign) and any(
                            getattr(t, "id", "") == "confidence" for t in statement.targets):
                        declared = ast.unparse(statement.value)
                if not declared or declared == "EXACT":
                    continue
                for call in ast.walk(node):
                    if (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "Issue"
                            and not any(k.arg == "confidence" for k in call.keywords)):
                        offenders.append(f"{path.name}:{node.name}:{call.lineno}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()


class AClipThroughAnEmptyValue(unittest.TestCase):
    """`data-x=` just before the clip: the empty value made `raw[-1]` raise
    IndexError, and a live run ended with "string index out of range" and
    an empty JSON (T-2823)."""

    def test_an_empty_unquoted_value_before_the_cut_does_not_raise(self):
        for snippet in (f'<img src="{LONG}" data-x= …',
                        f'<img src="{LONG}" data-x=…',
                        f'<img src="{LONG}" alt="" …'):
            with self.subTest(snippet=snippet):
                identity = browser._element_of(_issue("image-alt", "static", snippet))
                self.assertIsNotNone(identity)
                self.assertTrue(identity.clipped)

    def test_deduplicate_survives_it(self):
        kept = browser.deduplicate([
            _issue("image-alt", "static", f'<img src="{LONG}" data-x= …', "div > img"),
            _issue("axe:image-alt", "axe", f'<img src="{LONG}" data-x="">', "img"),
        ])
        self.assertEqual(len(kept), 1)


class TheCliSaysWhereItBroke(unittest.TestCase):

    def test_the_trace_is_printed_on_request(self):
        import io
        import os
        from contextlib import redirect_stderr
        from unittest import mock

        import cli

        def boom(args):
            raise IndexError("string index out of range")

        buffer = io.StringIO()
        args = mock.Mock(command="logs", func=boom, paths=[], progress=None,
                         target="", color_scheme=None, no_update_check=True)
        with mock.patch.dict(os.environ, {"XAUDIT_TRACEBACK": "1"}), \
                mock.patch("app_identity.migrate_legacy_data"), \
                mock.patch.object(cli, "build_parser") as parser, \
                redirect_stderr(buffer):
            parser.return_value.parse_args.return_value = args
            code = cli.main(["logs"])
        self.assertNotEqual(code, 0)
        self.assertIn("Traceback", buffer.getvalue())
        self.assertIn("boom", buffer.getvalue())
