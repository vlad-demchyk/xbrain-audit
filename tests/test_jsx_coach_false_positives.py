"""Static audit of React source: what a run on Coach got wrong (T-2337).

`xaudit audit apps/coach/src --category accessibility` reported 25
problems, one of them real. Each test is the shape of one false group,
checked against the file it came from.
"""
from __future__ import annotations

import unittest

from audit.base import RuleRegistry
from audit.engine import analyze_document
from audit.jsx_branches import Branches


def _audit(source: str, rule: str) -> list:
    report = analyze_document(source, "Comp.tsx", rules=[RuleRegistry.create(rule)],
                              line_numbers=True, document_kind="fragment",
                              syntax="jsx")
    return [i for i in report.issues if i.rule_id == rule]


class DuplicateIdInExclusiveBranches(unittest.TestCase):
    def test_the_two_arms_of_a_conditional(self):
        # MarketOverlay.tsx: `failed ? … : !detail ? … : …`, one h2 per arm.
        source = """export function M() {
  return (<div>{failed ? (<h2 id="t">A</h2>) : !detail ? (<h2 id="t">B</h2>)
    : (<><h2 id="t">C</h2></>)}</div>);
}"""
        self.assertEqual(_audit(source, "duplicate-id"), [])

    def test_and_against_its_negation(self):
        source = """export function M() {
  return (<div>{busy && <p id="s">Busy, don't leave</p>}{!busy && <p id="s">Idle</p>}</div>);
}"""
        self.assertEqual(_audit(source, "duplicate-id"), [])

    def test_an_early_return(self):
        source = """export function M() {
  if (sent) return <h1 id="t">Check your email</h1>;
  return (<section><h1 id="t">Sign in</h1></section>);
}"""
        self.assertEqual(_audit(source, "duplicate-id"), [])

    def test_two_in_one_render_are_still_a_duplicate(self):
        """The defect the rule is for must survive."""
        source = """export function M() {
  return (<div>{open ? <p>x</p> : null}<h2 id="t">A</h2><h2 id="t">B</h2></div>);
}"""
        self.assertEqual(len(_audit(source, "duplicate-id")), 1)

    def test_a_map_callback_return_is_part_of_the_outer_one(self):
        source = """export function M() {
  return (<ul id="t">{items.map(i => { return <li key={i}>{i}</li>; })}<li id="t"/></ul>);
}"""
        self.assertEqual(len(_audit(source, "duplicate-id")), 1)

    def test_plain_html_is_not_read_as_jsx(self):
        report = analyze_document('<p id="a">x</p><p id="a">y</p>', "a.html",
                                  rules=[RuleRegistry.create("duplicate-id")])
        self.assertEqual(len([i for i in report.issues
                              if i.rule_id == "duplicate-id"]), 1)


class ComponentWithALabelProp(unittest.TestCase):
    def test_a_labelled_component_is_named(self):
        # live/LessonSwitcher.tsx: @xformat/ui turns `label` into aria-labelledby.
        source = """export function S() {
  return (<div><Select label={t("lesson")} value={id} options={o} onChange={set} /></div>);
}"""
        self.assertEqual(_audit(source, "control-name"), [])

    def test_a_component_with_only_a_placeholder_keeps_its_weight(self):
        """`<Input placeholder=…>` on XFormat: a placeholder is not a name."""
        source = """export function S() { return (<div><Input placeholder={t("x")} /></div>); }"""
        found = _audit(source, "control-name")
        self.assertEqual([i.severity for i in found], ["critical"])

    def test_an_unnamed_dom_select_is_still_critical(self):
        source = """export function S() { return (<div><select value={id}></select></div>); }"""
        found = _audit(source, "control-name")
        self.assertEqual([i.severity for i in found], ["critical"])


class AriaReferenceInAnExpression(unittest.TestCase):
    def test_a_conditional_literal_that_exists(self):
        # pages/TeacherOverview.tsx
        source = """export function T() { return (<section aria-labelledby={s === undefined ? undefined : "next-title"}>
  <h2 id="next-title">Next</h2></section>); }"""
        self.assertEqual(_audit(source, "aria-reference-broken"), [])

    def test_a_template_literal_written_as_the_id_is(self):
        # lessons/MediaPicker.tsx
        source = """export function M() { return (<form><input aria-describedby={cyrillic ? `${block.id}-english` : undefined} />
  {cyrillic && <p id={`${block.id}-english`}>English only</p>}</form>); }"""
        self.assertEqual(_audit(source, "aria-reference-broken"), [])

    def test_a_prop_is_for_the_browser_to_settle(self):
        # sessions/Modal.tsx
        source = """export function M({labelledBy}) { return (<div role="dialog" aria-labelledby={labelledBy}>x</div>); }"""
        found = _audit(source, "aria-reference-broken")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "minor")
        self.assertEqual(found[0].confidence, "needs-browser")

    def test_a_literal_with_no_element_is_still_broken(self):
        source = """export function M() { return (<div aria-labelledby={open ? "nowhere" : undefined}>x</div>); }"""
        found = _audit(source, "aria-reference-broken")
        self.assertEqual([i.severity for i in found], ["serious"])


class ModalBackdrop(unittest.TestCase):
    SOURCE = """export function M() {
  return (<div className="modal">
    <div className="modal-dim" onClick={() => close.current()} aria-hidden="true" />
    <div role="dialog" aria-modal="true" tabIndex={-1}>x</div>
  </div>);
}"""

    def test_the_dimmed_layer_behind_a_dialog_is_not_a_control(self):
        for rule in ("jsx-click-without-key", "jsx-noninteractive-handler"):
            with self.subTest(rule=rule):
                self.assertEqual(_audit(self.SOURCE, rule), [])

    def test_a_hidden_clickable_div_with_no_dialog_is_still_reported(self):
        source = """export function M() {
  return (<div><div onClick={() => go()} aria-hidden="true" /></div>);
}"""
        self.assertEqual(len(_audit(source, "jsx-click-without-key")), 1)


class AbbreviationsInCode(unittest.TestCase):
    def test_code_is_not_text(self):
        source = """const FAQ_ITEMS = [];
export function A() {
  const v = JSON.parse(raw); const u = new URL(href); CSS.escape(id);
  return (<main><p>Read the FAQ</p></main>);
}"""
        found = {i.details["abbreviation"] for i in _audit(source, "abbreviation-expansion")}
        self.assertEqual(found, {"FAQ"})


class ReadableSelectors(unittest.TestCase):
    def test_typescript_generics_do_not_become_ancestors(self):
        source = """export function L() {
  const [s, set] = useState<string>("");
  const m: Record<Participant["status"], number> = {};
  return (<section className="card"><div className="list"><img src={x} /></div></section>);
}"""
        found = _audit(source, "image-alt")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].selector, "section.card > div.list > img")


class HeadingsPerRender(unittest.TestCase):
    def test_an_early_return_with_its_own_heading_is_not_a_jump(self):
        source = """export function P() {
  if (!user) return <main><h1>Sign in</h1></main>;
  return (<main><h3>History</h3></main>);
}"""
        self.assertEqual(_audit(source, "heading-order"), [])

    def test_the_other_arm_of_a_conditional_is_not_a_jump(self):
        source = """export function P() {
  return (<section>{tab === "a" ? <h2>Now</h2> : <h4>Then</h4>}</section>);
}"""
        self.assertEqual(_audit(source, "heading-order"), [])

    def test_a_jump_in_one_render_is_still_reported(self):
        # SessionsPage.tsx before e214956f: h1, then h3 in the same page.
        source = """export function P() {
  return (<main><h1>Sessions</h1><section><h3>Monday</h3></section></main>);
}"""
        found = _audit(source, "heading-order")
        self.assertEqual([(i.details["from"], i.details["to"]) for i in found], [(1, 3)])


class UntranslatedLiteral(unittest.TestCase):
    def test_a_literal_beside_translated_texts(self):
        source = """export function S() { const { t } = useTranslation();
  return (<div><h2>{t("title")}</h2><input aria-label="Пошук у списку" placeholder={t("q")} /></div>); }"""
        found = _audit(source, "jsx-untranslated-literal")
        self.assertEqual([(i.details["attribute"], i.details["value"]) for i in found],
                         [("aria-label", "Пошук у списку")])
        self.assertEqual(found[0].confidence, "advisory")

    def test_examples_and_addresses_are_not_prose(self):
        source = """export function S() { return (<div>{t("x")}
  <input placeholder="https://meet.google.com/…" /><input placeholder="you@example.com" />
  <img alt={`${text}`} /></div>); }"""
        self.assertEqual(_audit(source, "jsx-untranslated-literal"), [])

    def test_a_file_that_translates_nothing_is_left_alone(self):
        source = """export function S() { return (<input aria-label="Search" />); }"""
        self.assertEqual(_audit(source, "jsx-untranslated-literal"), [])


class UndecidedChecksAreNamed(unittest.TestCase):
    def test_the_notice_says_which_rules(self):
        from audit.base import EXACT, Issue, NEEDS_BROWSER, unsettled_summary

        issues = [Issue("media-captions", "serious", confidence=NEEDS_BROWSER),
                  Issue("media-captions", "serious", confidence=NEEDS_BROWSER),
                  Issue("aria-reference-broken", "minor", confidence=NEEDS_BROWSER),
                  Issue("image-alt", "critical", confidence=EXACT)]
        self.assertEqual(unsettled_summary(issues),
                         "media-captions ×2, aria-reference-broken")
        self.assertEqual(unsettled_summary(issues, limit=1), "media-captions ×2, +1")


class Scanner(unittest.TestCase):
    def test_typescript_generics_and_comparisons_are_not_jsx(self):
        source = """const [v, set] = useState<string>("a");
if (a < b) { x = 1; }
return cond ? <i id="a"/> : <i id="b"/>;"""
        branches = Branches(source)
        self.assertTrue(branches.exclusive(source.index('<i id="a"'),
                                           source.index('<i id="b"')))

    def test_apostrophes_in_jsx_text_do_not_open_a_string(self):
        source = """return (<div><p>Don't stop</p>{x ? <b id="1"/> : <b id="2"/>}</div>);"""
        branches = Branches(source)
        self.assertTrue(branches.exclusive(source.index('<b id="1"'),
                                           source.index('<b id="2"')))

    def test_unbalanced_input_is_never_exclusive(self):
        source = """return (<div>{x ? <b id="1"/> : <b id="2"/>"""
        branches = Branches(source)
        # Whatever it decides about these, it must not crash.
        branches.exclusive(source.index('<b id="1"'), source.index('<b id="2"'))


if __name__ == "__main__":
    unittest.main()
