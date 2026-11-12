"""Findings about one element merge only when they are one problem (T-2823).

Reviewed on a live intranet audit:

* `aria-reference-broken` and axe's `aria-valid-attr-value` on the same
  `<button aria-describedby="counter_N">` were two rows for one dangling
  reference;
* `duplicate-id` and `aria-reference-broken` shared a family, and so did
  `media-captions` and `media-autoplay`: one element with both problems lost
  one of them in the merge;
* a zone's `aria-describedby` that names an element elsewhere on the page was
  reported broken, because the zone is audited as a fragment.
"""
from __future__ import annotations

import unittest

from audit import browser
from audit import sharepoint_zones as zones
from audit.base import Issue

SOURCE = "https://contoso.sharepoint.com/p"
BUTTON = '<button aria-describedby="like_count_7" class="like">'


def _issue(rule, engine, snippet=BUTTON, why="", severity="serious", confidence="exact"):
    return Issue(rule_id=rule, severity=severity, engine=engine, source=SOURCE,
                 selector="button" if engine == "axe" else "div > button",
                 snippet=snippet, confidence=confidence, details={"why": why})


class Families(unittest.TestCase):

    def test_an_axe_dangling_reference_joins_the_static_one(self):
        kept = browser.deduplicate([
            _issue("aria-reference-broken", "static"),
            _issue("axe:aria-valid-attr-value", "axe", severity="minor",
                   confidence="needs-browser",
                   why='Fix any of the following:\n  ARIA attribute element ID does '
                       'not exist on the page: aria-describedby="like_count_7"'),
        ])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].details["also_found_by"], ["axe"])

    def test_a_wrong_value_stays_its_own_problem(self):
        kept = browser.deduplicate([
            _issue("aria-reference-broken", "static"),
            _issue("axe:aria-valid-attr-value", "axe",
                   why='Fix all of the following:\n  Invalid ARIA attribute value: '
                       'aria-expanded="maybe"'),
        ])
        self.assertEqual(len(kept), 2)

    def test_duplicate_id_and_broken_reference_are_two_problems(self):
        snippet = '<button id="b" aria-describedby="nothing">'
        kept = browser.deduplicate([
            _issue("duplicate-id", "static", snippet),
            _issue("aria-reference-broken", "static", snippet),
            _issue("axe:duplicate-id", "axe", snippet),
        ])
        self.assertEqual(sorted(i.rule_id for i in kept),
                         ["aria-reference-broken", "duplicate-id"])

    def test_captions_and_autoplay_are_two_problems(self):
        video = '<video autoplay src="/v.mp4">'
        kept = browser.deduplicate([
            _issue("media-captions", "static", video),
            _issue("media-autoplay", "static", video),
            _issue("axe:video-caption", "axe", video, severity="minor",
                   confidence="needs-browser"),
        ])
        self.assertEqual(sorted(i.rule_id for i in kept),
                         ["media-autoplay", "media-captions"])
        captions = next(i for i in kept if i.rule_id == "media-captions")
        self.assertEqual(captions.severity, "serious")


class AReferenceTheWholePageResolves(unittest.TestCase):

    def test_a_zone_reference_to_an_id_elsewhere_on_the_page_is_dropped(self):
        from bs4 import BeautifulSoup

        page = BeautifulSoup('<div id="title">T</div><div class="zone">'
                             '<button aria-describedby="title">x</button></div>',
                             "html.parser")
        broken = Issue(rule_id="aria-reference-broken", severity="serious",
                       details={"attribute": "aria-describedby", "missing": ["title"]})
        really = Issue(rule_id="aria-reference-broken", severity="serious",
                       details={"attribute": "aria-describedby", "missing": ["nowhere"]})
        self.assertEqual(zones.settle_references([broken, really], page), [really])


if __name__ == "__main__":
    unittest.main()
