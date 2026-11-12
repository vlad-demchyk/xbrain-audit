"""A PHP template is markup, and the audit has to read it as one.

Two defects, one symptom: markup written by a server-side template reported
critical accessibility failures against elements that are perfectly correct
at runtime. Measured across three real projects, the pair accounted for the
overwhelming majority of `control-name` criticals - on
a client's Bedrock repository, 471 became 30.

1. `<?php echo esc_html($name); ?>` is a *processing instruction* to an HTML
   parser and carries no text, so a link named only by the server read as
   nameless. See `repo_scanner.mask_server_tags`.

2. `#` in a `.php`/`.py`/`.rb` file was treated as a comment wherever it
   appeared, so `<use xlink:href="#it-share">` had the rest of the line -
   closing quote included - blanked. The attribute was then unterminated and
   the parser swallowed the element that followed. See
   `repo_scanner._mask_hash_comments`.

Both masks keep the file's length, because `sourceline` and every offset in
a finding index into the original text.
"""
from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from repo_scanner import mask_code_comments, mask_server_tags


def _text_of(markup: str, tag: str = "a") -> str:
    return BeautifulSoup(markup, "html.parser").find(tag).get_text(strip=True)


class ServerTagsBecomeBindings(unittest.TestCase):
    LINK = ('<a href="<?php echo esc_url($u); ?>">'
            '<svg aria-hidden="true"></svg>'
            '<span class="visually-hidden"><?php echo esc_html($n); ?></span>'
            '</a>')

    def test_a_link_named_by_the_server_is_not_nameless(self):
        self.assertEqual(_text_of(self.LINK), "",
                         "unmasked, the parser sees no text at all")
        self.assertNotEqual(_text_of(mask_server_tags(self.LINK)), "")

    def test_the_short_form_is_masked_too(self):
        self.assertNotIn("<?=", mask_server_tags('<span><?= $n ?></span>'))

    def test_a_computed_attribute_reads_as_a_binding(self):
        from audit.base import is_binding

        masked = mask_server_tags('<input id="<?php echo $id; ?>">')
        value = BeautifulSoup(masked, "html.parser").find("input")["id"]
        self.assertTrue(is_binding(value),
                        "a server-computed id must not be compared as a literal")

    def test_offsets_do_not_move(self):
        for source in (self.LINK, '<?= $x ?>', '<?php ?>', 'no tags here'):
            with self.subTest(source=source[:30]):
                self.assertEqual(len(mask_server_tags(source)), len(source))

    def test_markup_without_server_tags_is_untouched(self):
        plain = '<a href="/x">Link</a>'
        self.assertEqual(mask_server_tags(plain), plain)


class AHashInsideAStringIsNotAComment(unittest.TestCase):
    def test_a_sprite_reference_survives(self):
        source = '<use xlink:href="#it-share"></use>'
        self.assertEqual(mask_code_comments(source, "x.php"), source)

    def test_a_skip_link_survives(self):
        source = '<a href="#main">Skip</a>'
        self.assertEqual(mask_code_comments(source, "x.php"), source)

    def test_a_colour_survives(self):
        source = '<div style="color:#fff">x</div>'
        self.assertEqual(mask_code_comments(source, "x.php"), source)

    def test_the_element_after_it_is_still_readable(self):
        """The actual damage: an unterminated attribute ate the next tag."""
        source = ('<a href="/x"><svg><use xlink:href="#it-facebook"></use></svg>'
                  '<span>Facebook</span></a>')
        self.assertEqual(_text_of(mask_code_comments(source, "x.php")), "Facebook")

    def test_a_real_comment_is_still_masked(self):
        """The fix must not stop the masking it exists for."""
        masked = mask_code_comments('$x = 1;  # a real comment', "x.php")
        self.assertNotIn("real comment", masked)
        self.assertTrue(masked.startswith("$x = 1;"))

    def test_a_comment_after_a_string_is_still_masked(self):
        masked = mask_code_comments('name = "a#b"  # trailing', "x.py")
        self.assertIn('"a#b"', masked)
        self.assertNotIn("trailing", masked)

    def test_ruby_interpolation_is_still_spared(self):
        source = 'puts "#{name}"'
        self.assertEqual(mask_code_comments(source, "x.rb"), source)

    def test_offsets_do_not_move(self):
        for source, suffix in (('<a href="#main">Skip</a>', "php"),
                               ('$x = 1;  # comment', "php"),
                               ('# whole line', "py")):
            with self.subTest(source=source):
                self.assertEqual(len(mask_code_comments(source, "x." + suffix)),
                                 len(source))


if __name__ == "__main__":
    unittest.main()
