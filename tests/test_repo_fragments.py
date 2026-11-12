"""Repo mode reads source files as fragments, not as finished pages.

Both halves of that statement are checked here, because getting either one
wrong is what filled a real report with noise: a component is not missing a
doctype, and `onClick={close}` is not an inline event handler.
"""
import unittest

from audit import engine
from audit.base import RuleRegistry, is_binding
from models import FileResult


COMPONENT = (
    'export function Panel({ onClose }) {\n'
    '  return <div className="panel">\n'
    '    <button onClick={onClose} aria-label="Close">x</button>\n'
    '    <label htmlFor="q">Search</label>\n'
    '    <input id="q" onChange={update} value={query} />\n'
    '    <img src={photo.url} alt={photo.caption} />\n'
    '  </div>;\n'
    '}\n'
)

PAGE = (
    '<!DOCTYPE html><html lang="en"><head><title>Real page</title></head>'
    '<body><h1>Real page</h1><button onclick="go()">Go</button></body></html>'
)


def _run(path, text):
    return engine.analyze_files([FileResult(path=path, raw_text=text)], root=".")


def _rules(result):
    return {issue.rule_id for issue in result.issues()}


class Bindings(unittest.TestCase):
    def test_expression_kinds_are_recognised(self):
        self.assertEqual(is_binding("{onClose}"), "expression")
        self.assertEqual(is_binding("{{ title }}"), "mustache")
        self.assertEqual(is_binding("${url}"), "template")

    def test_a_literal_value_is_not_a_binding(self):
        self.assertEqual(is_binding("go()"), "")
        self.assertEqual(is_binding(""), "")
        self.assertEqual(is_binding(None), "")


class Fragments(unittest.TestCase):
    def test_a_component_is_not_missing_a_doctype_or_a_title(self):
        found = _rules(_run("src/Panel.tsx", COMPONENT))
        for rule in ("bp-doctype", "document-title", "html-lang", "page-has-h1"):
            self.assertNotIn(rule, found)

    def test_a_framework_handler_is_not_an_inline_handler(self):
        self.assertNotIn("bp-inline-handlers", _rules(_run("src/Panel.tsx", COMPONENT)))

    def test_a_field_labelled_with_htmlFor_counts_as_labelled(self):
        self.assertNotIn("control-name", _rules(_run("src/Panel.tsx", COMPONENT)))

    def test_a_component_image_with_no_size_attributes_is_not_flagged(self):
        """`seo-image-dimensions` needs a stylesheet to know whether the
        space is reserved, and a fragment carries none - the same reasoning
        that already excuses it from `page_level` rules, on a different
        rule attribute (`needs_external_css`). Confirmed live: every one of
        48 such findings on `~/repositories/xformat` .tsx files had no
        width/height *and* no className/style either - nothing bound to
        read, evidence genuinely unavailable rather than hidden."""
        self.assertNotIn("seo-image-dimensions", _rules(_run("src/Panel.tsx", COMPONENT)))


class Pages(unittest.TestCase):
    def test_an_html_file_is_still_judged_as_a_page(self):
        # The same run over a real page must keep every page-level rule, or
        # the fix would have traded noise for blindness.
        result = _run("public/index.html", '<html><body><p>hi</p></body></html>')
        found = _rules(result)
        self.assertIn("bp-doctype", found)
        self.assertIn("document-title", found)

    def test_a_real_inline_handler_is_still_reported(self):
        self.assertIn("bp-inline-handlers", _rules(_run("public/index.html", PAGE)))

    def test_an_undersized_image_on_a_real_page_is_still_reported(self):
        """Fixing the fragment must not also blind the page: an external
        stylesheet is unknown there too, but the tool has always reported it,
        now with an honest needs-browser caveat rather than silence."""
        page = ('<!DOCTYPE html><html lang="en"><head><title>x</title></head>'
               '<body><h1>x</h1><img src="hero.jpg" alt="Hero"></body></html>')
        self.assertIn("seo-image-dimensions", _rules(_run("public/index.html", page)))

    def test_page_level_rules_exist_and_are_a_minority(self):
        rules = RuleRegistry.all_rules()
        page_level = [r.id for r in rules if getattr(r, "page_level", False)]
        self.assertTrue(page_level)
        self.assertLess(len(page_level), len(rules))

    def test_needs_external_css_rules_are_skipped_only_for_fragments(self):
        rules = RuleRegistry.all_rules()
        marked = [r.id for r in rules if getattr(r, "needs_external_css", False)]
        self.assertIn("seo-image-dimensions", marked)


class ReachesTheFragment(unittest.TestCase):
    """A `.tsx` file must actually be read.

    Every `assertNotIn` in `Fragments` above passed for two months while
    `.tsx` was in `SKIP_AUDIT_SUFFIXES` and no rule ran on it at all: an
    empty finding set satisfies "this rule did not fire" perfectly. So the
    negative cases need a positive one beside them, or they assert nothing.
    See `P-19`.
    """

    #: A component whose fields carry a placeholder and nothing else - the
    #: shape that fills a real admin console, and the shape the audit was
    #: reporting as clean.
    UNLABELLED = (
        'export function Form() {\n'
        '  return <form>\n'
        '    <input name="vendor" placeholder="Vendor" />\n'
        '    <button className="go">Go</button>\n'
        '  </form>;\n'
        '}\n'
    )

    def test_a_component_is_opened_at_all(self):
        result = _run("src/Form.tsx", self.UNLABELLED)
        self.assertTrue(result.documents,
                        "the .tsx file was never read; every negative case "
                        "above is passing vacuously")

    def test_a_literal_placeholder_provides_a_fallback_name(self):
        self.assertNotIn("control-name", _rules(_run("src/Form.tsx", self.UNLABELLED)))

    def test_a_field_without_any_name_is_reported(self):
        source = self.UNLABELLED.replace(' placeholder="Vendor"', '')
        self.assertIn("control-name", _rules(_run("src/Form.tsx", source)))

    def test_jsx_extensions_are_not_skipped(self):
        for path in ("src/Form.tsx", "src/Form.jsx"):
            with self.subTest(path=path):
                self.assertFalse(engine._is_skipped_path(path))

    def test_plain_script_extensions_stay_skipped(self):
        """`if (a < b)` in a `.ts` file is an operator, not an open tag."""
        for path in ("src/util.ts", "src/util.js", "src/util.mjs"):
            with self.subTest(path=path):
                self.assertTrue(engine._is_skipped_path(path))


class BoundAttributes(unittest.TestCase):
    """A value the framework computes is not a value the audit can compare.

    Both cases here were live false alarms on `~/repositories/XFormat`, found
    the moment repo mode could read `.tsx` again (`P-19`).
    """

    LIST = (
        'export function Thread({ messages }) {\n'
        '  return <div>{messages.map((m) => <article id={m.id} key={m.id}>{m.text}</article>)}</div>;\n'
        '}\n'
    )

    MEDIA = (
        'export function Preview({ url }) {\n'
        '  return <iframe className="preview-iframe" src={url} title="Preview" />;\n'
        '}\n'
    )

    def test_a_bound_id_rendered_in_a_list_is_not_a_duplicate(self):
        self.assertNotIn("duplicate-id", _rules(_run("src/Thread.tsx", self.LIST)))

    def test_a_literal_duplicate_id_is_still_reported(self):
        """The fix must not blind the rule on the case it exists for."""
        page = ('<!DOCTYPE html><html lang="en"><head><title>x</title></head>'
                '<body><h1>x</h1><p id="dup">a</p><p id="dup">b</p></body></html>')
        self.assertIn("duplicate-id", _rules(_run("public/index.html", page)))

    def test_a_component_iframe_is_not_told_to_reserve_space(self):
        """Whether `.preview-iframe` sets `aspect-ratio` is the stylesheet's
        answer, and a fragment carries none."""
        self.assertNotIn("perf-layout-shift", _rules(_run("src/Preview.tsx", self.MEDIA)))

    def test_a_page_iframe_is_still_told_to(self):
        page = ('<!DOCTYPE html><html lang="en"><head><title>x</title></head>'
                '<body><h1>x</h1><iframe src="/e" title="e"></iframe></body></html>')
        self.assertIn("perf-layout-shift", _rules(_run("public/index.html", page)))


class SkippedPaths(unittest.TestCase):
    """What "not the product" means, and what it must not swallow."""

    def test_real_tests_are_skipped(self):
        for path in ("src/Panel.test.tsx", "src/Panel.spec.tsx",
                     "src/Panel.stories.tsx", "src/bundle.min.html",
                     "src/__tests__/Panel.tsx", "tests/Panel.tsx",
                     "node_modules/pkg/index.html", "dist/index.html"):
            with self.subTest(path=path):
                self.assertTrue(engine._is_skipped_path(path))

    def test_a_screen_whose_name_contains_test_is_not_skipped(self):
        """Matched as a path segment, never as a substring.

        `"test" in path` also matches the first two, which are real screens
        in `~/repositories/XFormat` and were being dropped as test files. The
        last one is why `spec` is not a skipped directory name at all: this
        repository's own `specs/` holds written specifications.
        """
        for path in ("src/features/coach/CoachTestEditor.tsx",
                     "src/features/smart/components/SmartTestModal.tsx",
                     "src/features/marketing/Testimonials.tsx",
                     "specs/read-once/overview.html"):
            with self.subTest(path=path):
                self.assertFalse(engine._is_skipped_path(path))

    def test_a_windows_path_is_read_the_same_way(self):
        self.assertTrue(engine._is_skipped_path(r"src\__tests__\Panel.tsx"))


if __name__ == "__main__":
    unittest.main()
