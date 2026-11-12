"""A row that repeats the one above it has to say what it is about.

A page with twenty images in an old format produced twenty rows reading
"Image with no dimensions set" and nothing else. The `src` that tells them
apart was in the finding and was not on the row, so the list said the same
thing twenty times - and the comment in `audit_panel.py` had already
written down why that is bad: a list where every row repeats the previous
one is a list nobody reads to the bottom.

Grouping is not the fix, and that was the first thing checked. Twenty images
are twenty different problems; merging them would lose which images, since
`places_of` reports the document and every one of them is on the same page.
The grouping was right. The row was under-informative.

So the distinguishing value is taken from the fields the rule's own
sentences interpolate - the value the explanation would have shown anyway,
rather than a second vocabulary invented for the list - and only when the
title actually repeats, because putting it on every row of every rule is how
a list stops being scannable in the other direction.

Headless: Qt runs on the offscreen platform, like the other widget tests.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    import audit
    from audit.explanations import template_fields_for
    from models import FileResult
    from ui.main_window import MainWindow
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not available")
class WhichFieldsASentenceUses(unittest.TestCase):
    """`template_fields_for`, which is what makes this language-independent."""

    def test_a_rule_that_names_an_address_reports_it(self):
        self.assertIn("src", template_fields_for("seo-image-dimensions"))

    def test_a_rule_that_names_nothing_reports_nothing(self):
        self.assertEqual(template_fields_for("color-contrast"), ())

    def test_an_unknown_rule_is_not_an_error(self):
        self.assertEqual(template_fields_for("no-such-rule-at-all"), ())

    def test_every_language_answers_the_same(self):
        """Load-bearing rather than lucky: every translation of one key
        carries the same placeholders - it has to, or `.format()` would
        raise - so the shape of a report cannot depend on the language it
        was read in."""
        import re

        import i18n.translations as translations

        table = next(v for v in vars(translations).values()
                     if isinstance(v, dict) and "a11y_image_alt_title" in v)
        placeholder = re.compile(r"\{(\w+)\}")
        differing = []
        for key, langs in table.items():
            if not key.startswith("a11y_"):
                continue
            sets = {frozenset(placeholder.findall(text))
                    for text in langs.values()}
            if len(sets) > 1:
                differing.append(key)
        self.assertEqual(differing, [])


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheRowsOfAPageOfImages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def rows_for(self, markup: str) -> list:
        path = Path(self.tmp.name) / "index.html"
        path.write_text(markup, encoding="utf-8")
        self.window.audit_result = audit.analyze_files(
            [FileResult(path=str(path), raw_text=markup)],
            self.tmp.name, media=False)
        self.window.app_state.set_unsettled(True)
        self.window._populate_audit_list()
        return [self.window.flagged_list.item(i).text()
                for i in range(self.window.flagged_list.count())]

    def page_of_images(self, count: int) -> str:
        images = "".join(f'<img src="/media/photo-{i}.png" alt="x">'
                         for i in range(count))
        return ("<html lang='uk'><head><title>x</title></head><body>"
                f"<h1>Hi</h1>{images}</body></html>")

    def test_no_two_rows_say_exactly_the_same_thing(self):
        """The defect, stated as the property it broke."""
        rows = self.rows_for(self.page_of_images(6))
        self.assertEqual(len(rows), len(set(rows)), rows)

    def test_a_repeating_row_names_the_file_it_is_about(self):
        rows = self.rows_for(self.page_of_images(6))
        repeated = [row for row in rows if "photo-3.png" in row]
        self.assertTrue(repeated, rows)

    def test_a_row_that_stands_alone_stays_clean(self):
        """Putting the detail on every row of every rule is how a list stops
        being scannable in the other direction.

        Asserted without naming a sentence: the window runs in whatever
        language the settings say, so a test that matched a Ukrainian
        substring passed or failed on the environment rather than on the
        behaviour.
        """
        rows = self.rows_for(self.page_of_images(1))
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(row=row):
                self.assertNotIn("·", row)

    def test_one_image_needs_no_disambiguation_at_all(self):
        rows = self.rows_for(self.page_of_images(1))
        self.assertEqual(len(rows), len(set(rows)), rows)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class WhatTellsAFindingApart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def issue(self, rule_id: str, **details):
        from audit.base import Issue

        return Issue(rule_id=rule_id, severity="minor",
                     selector="body > img:nth-child(2)", details=details)

    def apart(self, issue) -> str:
        from ui.window_parts.audit_panel import AuditPanelMixin

        return AuditPanelMixin._what_tells_it_apart(issue)

    def test_it_uses_the_value_the_explanation_would_have_shown(self):
        self.assertEqual(
            self.apart(self.issue("seo-image-dimensions", src="/a/b.png")),
            "/a/b.png")

    def test_a_rule_with_nothing_to_interpolate_falls_back_to_the_selector(self):
        self.assertEqual(self.apart(self.issue("color-contrast")),
                         "body > img:nth-child(2)")

    def test_a_long_address_is_trimmed_from_the_left(self):
        """It is recognised by its tail, and the row has to stay one line."""
        long = "/assets/generated/" + "x" * 80 + "/hero.png"
        apart = self.apart(self.issue("seo-image-dimensions", src=long))
        self.assertLessEqual(len(apart), 42)
        self.assertTrue(apart.endswith("hero.png"))

    def test_a_finding_with_no_details_and_no_selector_says_nothing(self):
        from audit.base import Issue

        self.assertEqual(
            self.apart(Issue(rule_id="color-contrast", severity="minor")), "")


if __name__ == "__main__":
    unittest.main()
