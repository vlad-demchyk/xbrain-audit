"""A link named in ARIA is not vague, and a name that drops the visible
label fails 2.5.3.

Seen on a live intranet: `<a aria-label="Leggi Novità del portale">
Leggi di più</a>` was reported as vague link text under 2.4.4, though the
name a screen reader's links list reads out says exactly where it goes. What
is wrong with it is the other criterion: a voice-control user says "Leggi di
più" and the control is not called that.
"""
from __future__ import annotations

import unittest

from audit import browser
from audit.base import MODERATE, Issue
from audit.engine import analyze_document
from audit.explanations import render as explain
from i18n.translations import t


def _rules(markup: str, *rule_ids) -> list:
    found = analyze_document(markup, "test.html", line_numbers=True).issues
    return [i for i in found if i.rule_id in rule_ids]


DESCRIBED = ('<p><a href="/news/1" aria-label="Leggi Novità del portale">'
             'Leggi di più</a></p>')


class AnAriaNameIsContext(unittest.TestCase):

    def test_an_aria_label_that_says_where_it_goes_is_not_vague(self):
        self.assertEqual(_rules(DESCRIBED, "link-text-vague"), [])

    def test_a_resolved_labelledby_is_not_vague_either(self):
        markup = ('<h2 id="h">Novità del portale</h2>'
                  '<a href="/n" aria-labelledby="h">Leggi di più</a>')
        self.assertEqual(_rules(markup, "link-text-vague"), [])

    def test_a_vague_aria_label_is_still_vague(self):
        markup = '<a href="/n" aria-label="Read more">Read more</a>'
        self.assertEqual(len(_rules(markup, "link-text-vague")), 1)

    def test_a_plain_vague_link_is_still_reported(self):
        self.assertEqual(len(_rules('<a href="/n">Leggi di più</a>', "link-text-vague")), 1)


class LabelInName(unittest.TestCase):

    def test_the_visible_words_missing_from_the_name_is_a_finding(self):
        found = _rules(DESCRIBED, "label-in-name")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, MODERATE)
        self.assertEqual(found[0].details["text"], "Leggi di più")

    def test_a_counter_is_content_not_a_label(self):
        """A like button showing "38" or a bell showing "0" names itself in
        aria-label; the number is what it shows, not what it is called."""
        for markup in (
            '<button aria-label="Like this news">38</button>',
            '<a href="/n" aria-label="Go to your notifications"><span>0</span></a>',
            '<button aria-label="Like the article">1 234</button>',
        ):
            with self.subTest(markup=markup):
                self.assertEqual(_rules(markup, "label-in-name"), [])
        # Words beside the number are still a label.
        self.assertEqual(len(_rules('<button aria-label="Like this">38 likes</button>',
                                    "label-in-name")), 1)

    def test_a_name_that_contains_the_label_passes(self):
        for markup in (
            '<a href="/n" aria-label="Leggi di più: comunicazioni">Leggi di più</a>',
            '<button aria-label="SEND the form">Send</button>',
            '<a href="/n" aria-label="Più, leggi di">leggi di più!</a>',
        ):
            with self.subTest(markup=markup):
                self.assertEqual(_rules(markup, "label-in-name"), [])

    def test_no_aria_label_or_no_visible_words_is_not_its_question(self):
        for markup in (
            '<a href="/n">Leggi di più</a>',
            '<button aria-label="Close">×</button>',
            '<button aria-label="Close"><svg></svg></button>',
            '<a href="/n" aria-labelledby="x" aria-label="Other">Visible</a>',
            '<button aria-label="Close" hidden>Chiudi</button>',
        ):
            with self.subTest(markup=markup):
                self.assertEqual(_rules(markup, "label-in-name"), [])

    def test_visually_hidden_text_is_not_part_of_the_label(self):
        markup = ('<a href="/n" aria-label="Read more about pricing">Read more'
                  '<span class="sr-only"> on our tariffs</span></a>')
        self.assertEqual(_rules(markup, "label-in-name"), [])

    def test_a_role_button_counts(self):
        markup = '<div role="button" tabindex="0" aria-label="Apri menu">Menu principale</div>'
        self.assertEqual(len(_rules(markup, "label-in-name")), 1)

    def test_it_is_one_row_with_axe(self):
        static = _rules(DESCRIBED, "label-in-name")[0]
        axe = Issue(rule_id="axe:label-content-name-mismatch", severity="serious",
                    source=static.source, engine="axe", selector="a",
                    snippet='<a href="/news/1" aria-label="Leggi Novità del portale">')
        self.assertEqual(len(browser.deduplicate([static, axe])), 1)

    def test_it_explains_itself_in_every_language(self):
        issue = _rules(DESCRIBED, "label-in-name")[0]
        for lang in ("uk", "it", "en"):
            with self.subTest(lang=lang):
                text = explain(issue, lang)
                self.assertIn("Leggi di più", text.found)
                self.assertNotEqual(text.title, "a11y_label_in_name_title")
                self.assertTrue(t("a11y_label_in_name_fix", lang))
                self.assertEqual(text.wcag, ("2.5.3",))


class LinkInTextBlockIsNotLinkText(unittest.TestCase):

    def test_a_colour_only_link_and_a_vague_link_are_two_problems(self):
        vague = Issue(rule_id="link-text-vague", severity="moderate", engine="static",
                      source="p", selector="p > a", snippet='<a href="/n">')
        colour = Issue(rule_id="axe:link-in-text-block", severity="serious", engine="axe",
                       source="p", selector="a", snippet='<a href="/n">')
        self.assertEqual(len(browser.deduplicate([vague, colour])), 2)


if __name__ == "__main__":
    unittest.main()
