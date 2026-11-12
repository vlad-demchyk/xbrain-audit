"""A field named only by its placeholder is a 3.3.2 finding, not a missing name.

Found on a live SharePoint intranet: the header search box
`<input placeholder="Type to search">` was reported on every page as a
critical `control-name` ("no accessible name"), while axe passed it - the
accessible name computation does fall back to the placeholder. What is wrong
is that the hint vanishes when one types.
"""

from __future__ import annotations

import unittest

from audit.base import MODERATE
from audit.engine import analyze_document
from audit.explanations import render as explain
from i18n.translations import t


def _found(markup: str, *rule_ids) -> list:
    found = analyze_document(markup, "test.html", line_numbers=True).issues
    return [i for i in found if i.rule_id in rule_ids]


class APlaceholderIsANameButNotALabel(unittest.TestCase):
    def test_placeholder_only_is_moderate_3_3_2_and_not_control_name(self):
        markup = '<input type="text" class="searchbar" placeholder="Type to search">'
        self.assertEqual(_found(markup, "control-name"), [])
        found = _found(markup, "label-placeholder-only")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, MODERATE)
        self.assertEqual(found[0].details["placeholder"], "Type to search")

    def test_a_number_field_with_a_placeholder_is_reported_once(self):
        markup = '<input type="number" placeholder="Amount">'
        self.assertEqual(_found(markup, "control-name"), [])
        self.assertEqual(len(_found(markup, "label-placeholder-only")), 1)

    def test_a_field_with_no_name_at_all_is_still_critical(self):
        self.assertEqual(len(_found('<input type="text">', "control-name")), 1)
        self.assertEqual(_found('<input type="text">', "label-placeholder-only"), [])

    def test_a_labelled_field_is_neither(self):
        for markup in (
            '<label for="q">Search</label><input id="q" placeholder="e.g. invoices">',
            '<input aria-label="Search" placeholder="e.g. invoices">',
            '<label>Search <input placeholder="e.g. invoices"></label>',
            '<input type="hidden" placeholder="x">',
            '<input placeholder="x" style="display:none">',
        ):
            with self.subTest(markup=markup):
                self.assertEqual(_found(markup, "control-name", "label-placeholder-only"), [])

    def test_the_texts_exist_in_every_language(self):
        issue = _found('<textarea placeholder="Your message"></textarea>',
                       "label-placeholder-only")[0]
        for lang in ("uk", "it", "en"):
            with self.subTest(lang=lang):
                text = explain(issue, lang)
                self.assertNotEqual(text.title, "a11y_label_placeholder_only_title")
                self.assertTrue(t("a11y_label_placeholder_only_fix", lang))


if __name__ == "__main__":
    unittest.main()
