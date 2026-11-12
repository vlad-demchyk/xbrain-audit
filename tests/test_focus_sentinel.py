"""Fluent UI's Tabster focus sentinels are not `aria-hidden-focus` defects."""

from __future__ import annotations

import json
import unittest

from audit.browser import issues_from_axe


def _axe(html: str, rule: str = "aria-hidden-focus") -> str:
    return json.dumps({"violations": [{
        "id": rule, "impact": "serious", "help": "", "description": "",
        "nodes": [{"html": html, "target": ["i"], "failureSummary": ""}]}],
        "incomplete": []})


class FocusSentinels(unittest.TestCase):
    def test_a_tabster_dummy_is_not_reported(self):
        html = ('<i tabindex="0" role="none" data-tabster-dummy="" '
                'aria-hidden="true" style="position: fixed;"></i>')
        self.assertEqual(issues_from_axe(_axe(html), "https://x.test/"), [])

    def test_any_other_hidden_focusable_element_still_is(self):
        html = '<div tabindex="-1" class="slick-slide" aria-hidden="true">'
        found = issues_from_axe(_axe(html), "https://x.test/")
        self.assertEqual([i.rule_id for i in found], ["axe:aria-hidden-focus"])

    def test_the_marker_only_excuses_that_rule(self):
        html = '<i tabindex="0" data-tabster-dummy="" aria-hidden="true"></i>'
        found = issues_from_axe(_axe(html, "button-name"), "https://x.test/")
        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
