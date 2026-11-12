"""Two stack packs, and the discipline that let them in.

`audit.medium` already stops the browser-only rules firing on an email. These
are the checks that only make sense *because* the document is an email, plus
the one WordPress check that could be measured on real WordPress code.

Every rule here shipped with a number behind it, and the tests say what the
number was, because the number is the argument: four other WordPress
candidates and two other email candidates measured zero on the same corpora
and were left out.
"""
from __future__ import annotations

import unittest

import audit
from audit.explanations import render

#: Enough of an email for `audit.medium` to say so without any help.
EMAIL_HEAD = ('<html xmlns:v="urn:schemas-microsoft-com:vml"><head>'
              '<meta charset="utf-8"></head><body>')


def email_findings(body: str, prefix: str = "email-"):
    report = audit.analyze_document(EMAIL_HEAD + body + "</body></html>",
                                    "campaign.html")
    return [issue for issue in report.issues if issue.rule_id.startswith(prefix)]


def page_findings(body: str, prefix: str = "email-"):
    report = audit.analyze_document("<html><head><title>x</title></head><body>"
                                    + body + "</body></html>", "page.html")
    return [issue for issue in report.issues if issue.rule_id.startswith(prefix)]


class TheEmailPackStaysInTheInbox(unittest.TestCase):
    def test_a_page_never_receives_email_advice(self):
        body = ('<p style="font-family: Brand Grotesk">'
                '<a href="/x">Read</a></p>')
        self.assertEqual(page_findings(body), [])

    def test_an_email_receives_it(self):
        body = '<p style="font-family: Brand Grotesk">hello</p>'
        self.assertEqual([issue.rule_id for issue in email_findings(body)
                          if issue.rule_id == "email-font-no-fallback"],
                         ["email-font-no-fallback"])


class FontFallback(unittest.TestCase):
    """Measured: 10 of 18 emails in `~/repositories/VSC`."""

    def test_a_generic_family_at_the_end_is_the_fix(self):
        body = '<p style="font-family: Brand Grotesk, Arial, sans-serif">hi</p>'
        self.assertEqual([i for i in email_findings(body)
                          if i.rule_id == "email-font-no-fallback"], [])

    def test_the_same_stack_on_forty_cells_is_one_finding(self):
        """The fix is one edit to the stack, not forty to the cells."""
        body = "".join('<td style="font-family: Brand Grotesk">x</td>'
                       for _ in range(40))
        found = [i for i in email_findings(body)
                 if i.rule_id == "email-font-no-fallback"]
        self.assertEqual(len(found), 1)

    def test_a_second_distinct_stack_is_a_second_finding(self):
        body = ('<p style="font-family: Brand Grotesk">a</p>'
                '<p style="font-family: Brand Mono">b</p>')
        found = [i for i in email_findings(body)
                 if i.rule_id == "email-font-no-fallback"]
        self.assertEqual(len(found), 2)


class LinkColour(unittest.TestCase):
    """Measured: 11 links in 3 of the same 18 emails."""

    def test_an_unstyled_link_will_be_repainted_by_the_client(self):
        found = [i.rule_id for i in email_findings('<a href="/x">Read</a>')]
        self.assertIn("email-link-no-colour", found)

    def test_an_inline_colour_settles_it(self):
        body = '<a href="/x" style="color:#0b5cad">Read</a>'
        self.assertEqual([i for i in email_findings(body)
                          if i.rule_id == "email-link-no-colour"], [])

    def test_a_background_colour_is_not_the_text_colour(self):
        body = '<a href="/x" style="background-color:#0b5cad">Read</a>'
        self.assertTrue([i for i in email_findings(body)
                         if i.rule_id == "email-link-no-colour"])

    def test_a_stylesheet_rule_answers_for_every_link_at_once(self):
        body = ('<style>a { color: #0b5cad; }</style>'
                '<a href="/x">Read</a><a href="/y">More</a>')
        self.assertEqual([i for i in email_findings(body)
                          if i.rule_id == "email-link-no-colour"], [])

    def test_an_image_link_has_no_text_to_paint(self):
        body = '<a href="/x"><img src="b.png" alt="Buy"></a>'
        self.assertEqual([i for i in email_findings(body)
                          if i.rule_id == "email-link-no-colour"], [])


class Preheader(unittest.TestCase):
    """Measured: 12 of the same 18 emails ship without one."""

    def test_an_email_with_no_hidden_preview_text_is_reported(self):
        found = [i.rule_id for i in email_findings("<p>Hello</p>")]
        self.assertIn("email-no-preheader", found)

    def test_a_hidden_block_is_a_preheader(self):
        body = ('<div style="display:none; max-height:0; overflow:hidden">'
                'Your March invoice is ready</div><p>Hello</p>')
        self.assertEqual([i for i in email_findings(body)
                          if i.rule_id == "email-no-preheader"], [])

    def test_the_outlook_spelling_counts_too(self):
        body = '<div style="mso-hide:all">Preview</div><p>Hello</p>'
        self.assertEqual([i for i in email_findings(body)
                          if i.rule_id == "email-no-preheader"], [])


def wp_findings(php: str, stacks=("wordpress",)):
    report = audit.analyze_document(php, "theme/single.php",
                                    document_kind="fragment", stacks=stacks)
    return [issue for issue in report.issues
            if issue.rule_id == "wp-unescaped-output"]


class WordPressEscaping(unittest.TestCase):
    """Measured: 592 on `~/Local Sites/municipal-site` - 577 in the installed
    theme, 15 in the site's own. The four other candidates in the plan
    measured zero there and were not written."""

    def test_a_bare_variable_printed_into_markup_is_reported(self):
        found = wp_findings("<p><?php echo $descrizione; ?></p>")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].details["value"], "$descrizione")
        self.assertIn("esc_html($descrizione)", found[0].fix_snippet)

    def test_a_property_and_an_index_are_variables_too(self):
        self.assertEqual(len(wp_findings(
            "<p><?php echo $post->post_title; ?><?= $row['name'] ?></p>")), 2)

    def test_a_ternary_between_two_literals_is_safe_and_silent(self):
        """By far the most common shape in a template. Reporting it was 536
        findings on this corpus, nearly all of them wrong."""
        self.assertEqual(wp_findings(
            "<div class=\"<?php echo $open ? 'is-open' : ''; ?>\">x</div>"), [])

    def test_an_escaped_call_is_not_a_bare_variable(self):
        self.assertEqual(wp_findings("<p><?php echo esc_html($x); ?></p>"), [])

    def test_the_rule_is_silent_where_no_wordpress_was_detected(self):
        """A stack that was not proved is not a stack a rule may assume."""
        self.assertEqual(wp_findings("<p><?php echo $x; ?></p>", stacks=()), [])

    def test_it_is_a_best_practice_rather_than_a_security_finding(self):
        """`security` was opened on the condition that nothing in it infers,
        and this cannot see whether the variable was sanitised earlier."""
        issue = wp_findings("<p><?php echo $x; ?></p>")[0]
        self.assertEqual(issue.category, "best-practices")
        self.assertEqual(issue.confidence, "advisory")


class Wording(unittest.TestCase):
    def test_both_packs_read_as_sentences_in_every_language(self):
        body = ('<p style="font-family: Brand Grotesk">'
                '<a href="/x">Read</a></p>')
        found = email_findings(body) + wp_findings("<p><?php echo $x; ?></p>")
        self.assertTrue(found)
        for issue in found:
            for lang in ("uk", "it", "en"):
                explanation = render(issue, lang)
                for field in ("title", "found", "why", "fix"):
                    value = getattr(explanation, field)
                    self.assertTrue(value, f"{issue.rule_id}.{field} is empty")
                    self.assertFalse(value.startswith("a11y_"))


if __name__ == "__main__":
    unittest.main()
