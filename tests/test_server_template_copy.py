"""A server template is a page, not a program: its copy has to be read.

Measured 2026-09-02: the same markup read **2** blocks as `.html` and **1**
as `.blade.php`. `_extract_blocks` skipped the tag walk for everything in
`BACKEND_EXTENSIONS`, `.php` among them - correct for a controller, wrong for
every Blade view and every WordPress theme file, which are markup with a
server language mixed in. So the AI-pattern and character passes never opened
the visible copy of a Laravel front end at all, while the audit - which had
always masked the server tags and parsed the markup - reported its missing
`alt` attributes from the same file.

The audit half is asserted here too, not because it was broken, but because
the two halves reading the same file differently is what the defect was.
"""
from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audit import engine  # noqa: E402
from repo_scanner import scan_file  # noqa: E402

#: One passage of copy no scanner should miss, and one the templating
#: language produces at runtime - which is not copy and must not be read as
#: it. Every fixture below is the same page in a different template language.
COPY = ("Unlock the full potential of your workflow — it is worth noting "
        "that this comprehensive solution delves into the intricacies.")

BLADE = textwrap.dedent(f"""\
    @extends('layouts.app')
    @section('content')
      <h1>{{{{ $plan->name }}}} — a heading with a variable in it</h1>
      @if ($user->trial)
        <p>{COPY}</p>
      @endif
      <img src="/hero.png">
      <a href="{{{{ route('signup') }}}}">Get started</a>
    @endsection
    """)

WORDPRESS_THEME = textwrap.dedent(f"""\
    <?php
    /**
     * Theme header. This comment mentions <img> and is not markup.
     */
    if ( ! defined( 'ABSPATH' ) ) {{ exit; }}
    ?>
    <header class="site-header">
      <a class="brand" href="<?php echo esc_url( home_url( '/' ) ); ?>"><?php
        echo esc_html( get_bloginfo( 'name' ) ); ?></a>
      <p>{COPY}</p>
    </header>
    """)

TWIG = textwrap.dedent(f"""\
    {{% extends "base.twig" %}}
    {{% block body %}}
      <h2>{{{{ product.name }}}} in a heading</h2>
      <p>{COPY}</p>
    {{% endblock %}}
    """)

#: A controller, not a view. The tag walk must stay off here: `$id < 10 &&
#: $id > 0` is a comparison, and the reason the walk was skipped for `.php`
#: in the first place.
CONTROLLER = textwrap.dedent("""\
    <?php
    namespace App\\Http\\Controllers;

    class PricingController extends Controller
    {
        public function show($id)
        {
            if ($id < 10 && $id > 0) {
                return view('pricing', ['plan' => $id]);
            }
            return abort(404);
        }
    }
    """)


class TemplateCopyIsRead(unittest.TestCase):

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _blocks(self, name: str, source: str):
        path = Path(self.tmp.name) / name
        path.write_text(source, encoding="utf-8")
        return scan_file(str(path)).blocks

    def _texts(self, name: str, source: str):
        return [b.text for b in self._blocks(name, source)]

    def test_a_blade_view_hands_over_its_copy(self):
        self.assertIn(COPY, self._texts("page.blade.php", BLADE))

    def test_a_wordpress_theme_file_hands_over_its_copy(self):
        self.assertIn(COPY, self._texts("header.php", WORDPRESS_THEME))

    def test_a_twig_template_hands_over_its_copy(self):
        self.assertIn(COPY, self._texts("page.twig", TWIG))

    def test_a_template_reads_the_same_as_the_html_it_produces(self):
        """The property behind all three: the suffix must not change what
        counts as copy."""
        as_html = set(self._texts("page.html", BLADE.replace("@", "<!--@")))
        as_blade = set(self._texts("page.blade.php", BLADE))
        self.assertIn(COPY, as_html & as_blade)

    def test_the_heading_after_an_interpolation_is_not_lost(self):
        """`{{ $plan->name }}` carries a `>`.

        Unmasked, it ended the walk's idea of the tag, and the heading - and
        everything after it on the line - was never read.
        """
        self.assertIn("— a heading with a variable in it",
                      self._texts("page.blade.php", BLADE))

    def test_what_the_template_language_produces_is_not_copy(self):
        for text in self._texts("page.blade.php", BLADE):
            self.assertNotIn("$plan->name", text)
            self.assertNotIn("route('signup')", text)
            self.assertNotIn("@endsection", text)

    def test_a_php_comment_that_mentions_markup_is_still_a_comment(self):
        for text in self._texts("header.php", WORDPRESS_THEME):
            self.assertNotIn("Theme header", text)

    def test_a_controller_is_still_read_as_code(self):
        """The `<` and `>` in `$id < 10 && $id > 0` are comparisons."""
        blocks = self._blocks("PricingController.php", CONTROLLER)
        self.assertEqual([b.text for b in blocks], [])

    def test_offsets_still_point_at_the_original_file(self):
        """A block whose span does not match the file cannot be corrected.

        The walk runs over a masked copy; the runs are cut from the original.
        If those two ever disagree, `fix` writes into the wrong place - so
        this is asserted rather than assumed.
        """
        path = Path(self.tmp.name) / "page.blade.php"
        path.write_text(BLADE, encoding="utf-8")
        raw = path.read_text(encoding="utf-8")
        for block in scan_file(str(path)).blocks:
            self.assertEqual(raw[block.start:block.end], block.text)


class TheAuditReadsTheSameFile(unittest.TestCase):
    """Both passes over one template, so they cannot disagree about it."""

    def _rules(self, name: str, source: str):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(source, encoding="utf-8")
            result = engine.analyze_page_file(str(path))
        return {issue.rule_id for issue in result.issues()}

    def test_a_blade_view_is_audited_as_markup(self):
        self.assertIn("image-alt", self._rules("page.blade.php", BLADE))

    def test_a_link_named_by_the_server_is_not_reported_nameless(self):
        """`<?php echo esc_html(...) ?>` is a name, not an empty element.

        Measured 2026-09-02: `analyze_files` masked the server tags and
        `analyze_page_file` did not, so `xaudit audit header.php` and the
        same file inside a folder scan disagreed about this link. Both call
        `_mask_for_audit` now.
        """
        rules = self._rules("header.php", WORDPRESS_THEME)
        self.assertNotIn("control-name", rules)
        self.assertNotIn("seo-empty-link", rules)

    def test_the_two_audit_entry_points_agree_about_one_file(self):
        """The property, not the instance: one file, one answer."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "header.php"
            path.write_text(WORDPRESS_THEME, encoding="utf-8")
            from repo_scanner import ScanConfig, scan_repo

            named = engine.analyze_page_file(str(path))
            in_folder = engine.analyze_files(
                scan_repo(tmp, ScanConfig()), tmp)
        self.assertEqual({i.rule_id for i in named.issues()},
                         {i.rule_id for i in in_folder.issues()})


if __name__ == "__main__":
    unittest.main()
