"""The focus pass reports nothing when it cannot see focus.

A document that does not itself have focus never matches `:focus` in
Chromium. `el.focus()` still sets `activeElement`, so the check believed it
had focused the element - but no focus rule applied, no computed style
changed, and every focusable element on the page came back with a missing
indicator.

Measured against `https://www.gov.uk/`, whose focus state is among the most
tested on the web: 588 serious findings across ten pages, one for very nearly
every element examined. Confirmed in a live browser - `document.hasFocus()`
was `false` and `el.matches(':focus')` was `false` immediately after
`el.focus()`.

Two rules follow, and this file pins both in the script's source, since the
script itself only runs inside a browser:

* the pass must establish that it *can* see focus before reporting that a
  ring is missing;
* what counts as an indicator is any visible change, not an outline - GOV.UK
  draws a yellow background, and 83 rules in its stylesheet set `background`
  on `:focus`.
"""
from __future__ import annotations

import unittest

from audit.states import STATE_RULES, STATE_SCRIPT, issues_from_states


class TheSkipLinkCheckIsNotWordMatching(unittest.TestCase):
    """A page is not missing a skip link because the tool speaks fewer
    languages than the page does.

    The check took the first five in-page anchors and matched their text
    against `skip|jump|перейти|content|main|vai`. Measured 2026-09-01 on a
    live trilingual site: the German page was reported as having no skip
    link, and the finding quoted that page's own skip link -
    `<a id="site-skip-to-content" class="…skiplink-link"
    href="#main-container">Zum Inhalt springen</a>` - as the element it was
    about. Whether it fires at all depends on what the other four anchors
    happen to say, which is a flaky answer as well as a wrong one.

    Two structural signals now come first, and they hold in any language:
    the element says `skip` in its own id or class, or its `href` points at
    the document's main landmark.
    """

    def test_the_element_s_own_name_is_read(self):
        self.assertIn("if (/skip/i.test(name)) return true;", STATE_SCRIPT)
        self.assertIn("a.getAttribute('id')", STATE_SCRIPT)

    def test_the_target_being_the_main_landmark_is_enough(self):
        self.assertIn("target.tagName === 'MAIN'", STATE_SCRIPT)
        self.assertIn("target.getAttribute('role') === 'main'", STATE_SCRIPT)

    def test_the_word_list_is_a_fallback_and_reads_the_accessible_name(self):
        self.assertIn("a.getAttribute('aria-label')", STATE_SCRIPT)
        for word in ("inhalt", "springen", "contenu", "contenido", "saltar"):
            with self.subTest(word):
                self.assertIn(word, STATE_SCRIPT)


class TheScriptChecksItCanMeasure(unittest.TestCase):
    def test_it_asks_whether_the_document_has_focus(self):
        self.assertIn("document.hasFocus()", STATE_SCRIPT)

    def test_it_confirms_the_probe_actually_matches_focus(self):
        self.assertIn("matches(':focus')", STATE_SCRIPT)

    def test_the_report_says_whether_focus_was_measurable(self):
        self.assertIn("focusMeasured", STATE_SCRIPT)

    def test_nothing_is_recorded_when_it_cannot_see_focus(self):
        self.assertIn("if (!canSeeFocus) return;", STATE_SCRIPT)


class WhatCountsAsAnIndicator(unittest.TestCase):
    def test_background_and_colour_count_too(self):
        for name in ("gainedBackground", "gainedColor"):
            with self.subTest(property=name):
                self.assertIn(name, STATE_SCRIPT)

    def test_the_original_three_are_still_there(self):
        for name in ("gainedOutline", "gainedShadow", "gainedBorder"):
            with self.subTest(property=name):
                self.assertIn(name, STATE_SCRIPT)


class OffCanvasIsNotBelowTheFold(unittest.TestCase):
    """`focus-outside-viewport` measured how long the page was.

    On `https://www.gov.uk/` it reported 151 `govuk-footer__link` elements -
    the ordinary footer - as focusable content outside the viewport. Content
    further down a page is reached by scrolling.
    """

    def test_the_page_length_condition_is_gone(self):
        self.assertNotIn("window.innerHeight + window.scrollY + 2000",
                         STATE_SCRIPT)

    def test_a_negative_edge_still_counts(self):
        self.assertIn("rect.bottom < 0 || rect.right < 0", STATE_SCRIPT)


class ModalState(unittest.TestCase):
    def test_an_open_modal_is_checked_without_clicking_it(self):
        self.assertIn("modal-focus-not-contained", STATE_RULES)
        self.assertIn('aria-modal="true"', STATE_SCRIPT)
        self.assertIn("openModal.contains(active)", STATE_SCRIPT)

    def test_modal_focus_escape_is_a_serious_accessibility_finding(self):
        found = issues_from_states({"findings": [{
            "rule": "modal-focus-not-contained", "selector": "div#dialog",
            "html": '<div role="dialog" aria-modal="true">',
        }]}, "https://example.test/")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "serious")


if __name__ == "__main__":
    unittest.main()
