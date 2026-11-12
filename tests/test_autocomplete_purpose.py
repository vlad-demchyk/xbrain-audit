"""An invalid autocomplete token on a search box is not a 1.3.5 failure.

1.3.5 Identify Input Purpose covers fields that collect information about
the user. A live intranet's search box, `<input type="search"
autocomplete="search">`, came back from axe as *serious*. Synthetic payloads.
"""
from __future__ import annotations

import json
import unittest

from audit.base import ACCESSIBILITY, BEST_PRACTICES, MINOR, SERIOUS
from audit.browser import issues_from_axe


def _axe(html: str):
    payload = {"violations": [{"id": "autocomplete-valid", "impact": "serious",
                               "tags": ["wcag21aa", "wcag135"],
                               "nodes": [{"target": ["input"], "html": html}]}],
               "incomplete": []}
    return issues_from_axe(json.dumps(payload), "https://contoso.example/")[0]


class AutocompletePurpose(unittest.TestCase):

    def test_a_search_field_is_a_minor_best_practice(self):
        issue = _axe('<input type="search" autocomplete="search" placeholder="Cerca">')
        self.assertEqual((issue.severity, issue.category), (MINOR, BEST_PRACTICES))

    def test_a_field_about_the_user_keeps_axes_weight(self):
        for html in ('<input type="text" autocomplete="postal-code shipping">',
                     '<input type="text" autocomplete="family-name x-bogus">',
                     '<input type="email" autocomplete="mail">',
                     '<input autocomplete="tel-nationall" type="tel">'):
            with self.subTest(html=html):
                issue = _axe(html)
                self.assertEqual((issue.severity, issue.category), (SERIOUS, ACCESSIBILITY))

    def test_an_unreadable_node_keeps_axes_weight(self):
        self.assertEqual(_axe("").severity, SERIOUS)


if __name__ == "__main__":
    unittest.main()
