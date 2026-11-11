"""Findings made out of bytes the run had already paid for.

Three passes that cost no request: the response headers the crawler was
discarding, the whole-crawl view no single-document rule can have, and the
image dimensions the media pass was downloading and dropping. Plus the
language check that had both halves in the codebase and had never introduced
them.
"""
import unittest

from audit import crosspage, headers, media
from audit.engine import analyze_document
from models import PageDiagnostics, PageResult


def _page(url: str, html: str = "<html></html>", **header_pairs) -> PageResult:
    diagnostics = PageDiagnostics()
    diagnostics.headers = {k.replace("_", "-"): v for k, v in header_pairs.items()}
    return PageResult(url=url, depth=0, raw_html=html, diagnostics=diagnostics)


class ResponseHeaders(unittest.TestCase):
    def test_a_bare_response_is_reported_once_per_missing_header(self):
        found = {i.rule_id for i in headers.issues_for("https://x/", {"server": "nginx"})}
        self.assertIn("sec-no-csp", found)
        self.assertIn("sec-no-hsts", found)
        self.assertIn("perf-no-compression", found)

    def test_a_page_that_was_never_fetched_says_nothing(self):
        # No headers is not evidence of missing headers - it is evidence the
        # crawl never got the page, and reporting it would be a finding about
        # our own failure.
        self.assertEqual(headers.issues_for("https://x/", {}), [])

    def test_hsts_is_not_asked_of_a_plain_http_page(self):
        found = {i.rule_id for i in headers.issues_for("http://x/", {"server": "nginx"})}
        self.assertNotIn("sec-no-hsts", found)

    def test_a_policy_in_the_markup_is_a_policy(self):
        markup = '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'">'
        found = {i.rule_id for i in
                 headers.issues_for("https://x/", {"server": "nginx"}, markup=markup)}
        self.assertNotIn("sec-no-csp", found)

    def test_frame_ancestors_answers_for_x_frame_options(self):
        found = {i.rule_id for i in headers.issues_for(
            "https://x/", {"content-security-policy": "frame-ancestors 'self'"})}
        self.assertNotIn("sec-no-frame-options", found)

    def test_a_fully_served_page_is_clean(self):
        found = headers.issues_for("https://x/", {
            "content-security-policy": "default-src 'self'",
            "strict-transport-security": "max-age=31536000",
            "x-content-type-options": "nosniff",
            "referrer-policy": "strict-origin",
            "x-frame-options": "SAMEORIGIN",
            "content-encoding": "br",
            "cache-control": "no-cache",
        })
        self.assertEqual(found, [])


class AcrossThePages(unittest.TestCase):
    HEAD = ('<html><head><title>{title}</title>'
            '<meta name="description" content="{desc}">'
            '<link rel="canonical" href="{canon}"></head></html>')

    def _pages(self, *specs):
        return [PageResult(url=f"https://x/{i}", depth=0,
                           raw_html=self.HEAD.format(**spec))
                for i, spec in enumerate(specs)]

    def test_one_title_on_two_pages_is_one_finding(self):
        pages = self._pages(
            {"title": "Home", "desc": "a", "canon": "https://x/0"},
            {"title": "Home", "desc": "b", "canon": "https://x/1"})
        found = [i for i in crosspage.issues_for(pages)
                 if i.rule_id == "seo-duplicate-title"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].details["count"], 2)

    def test_distinct_pages_report_nothing(self):
        pages = self._pages(
            {"title": "Home", "desc": "a", "canon": "https://x/0"},
            {"title": "Prices", "desc": "b", "canon": "https://x/1"})
        self.assertEqual(crosspage.issues_for(pages), [])

    def test_one_page_cannot_duplicate_itself(self):
        pages = self._pages({"title": "Home", "desc": "a", "canon": "https://x/0"})
        self.assertEqual(crosspage.issues_for(pages), [])

    def test_an_absent_value_is_not_a_duplicate(self):
        # Two pages with no description share nothing; the absence is a
        # different rule's finding and reporting it here would double it.
        pages = [PageResult(url=f"https://x/{i}", depth=0,
                            raw_html="<html><head><title>A</title></head></html>")
                 for i in range(2)]
        found = {i.rule_id for i in crosspage.issues_for(pages)}
        self.assertNotIn("seo-duplicate-description", found)

    def test_crawled_hreflang_target_must_link_back(self):
        pages = [
            PageResult(url="https://x/en/article", depth=0, raw_html=(
                '<html><head><link rel="alternate" hreflang="uk" '
                'href="https://x/uk/article"></head></html>')),
            PageResult(url="https://x/uk/article", depth=0,
                       raw_html="<html><head></head></html>"),
        ]
        found = [issue for issue in crosspage.issues_for(pages)
                 if issue.rule_id == "seo-hreflang-not-reciprocal"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].details["target"], "https://x/uk/article")

    def test_search_and_filter_views_are_left_out_and_counted(self):
        # 216 rows of one crawl: `?s=` and filter views carry the hreflang of
        # the page they were built on, and nothing links back to them.
        alt = ('<link rel="alternate" hreflang="en" href="https://x/en/">')
        pages = [
            PageResult(url="https://x/?s=town", depth=0,
                       raw_html=f"<html><head>{alt}</head></html>"),
            PageResult(url="https://x/eventi?pgrado=3", depth=0, raw_html=(
                f'<html><head><link rel="canonical" href="https://x/eventi">{alt}'
                "</head></html>")),
            PageResult(url="https://x/en/", depth=0,
                       raw_html="<html><head></head></html>"),
        ]
        issues = crosspage.issues_for(pages)
        self.assertEqual([i for i in issues
                          if i.rule_id == "seo-hreflang-not-reciprocal"], [])
        skipped = [i for i in issues
                   if i.rule_id == "seo-hreflang-parameterised-skipped"]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].details["count"], 2)
        self.assertEqual(skipped[0].severity, "minor")

    def test_a_query_page_that_names_itself_canonical_is_still_checked(self):
        # `?page_id=12` on WordPress without pretty links is a page.
        pages = [
            PageResult(url="https://x/?page_id=12", depth=0, raw_html=(
                '<html><head><link rel="canonical" href="https://x/?page_id=12">'
                '<link rel="alternate" hreflang="en" href="https://x/en/?page_id=13">'
                "</head></html>")),
            PageResult(url="https://x/en/?page_id=13", depth=0, raw_html=(
                '<html><head><link rel="canonical" href="https://x/en/?page_id=13">'
                "</head></html>")),
        ]
        found = [i for i in crosspage.issues_for(pages)
                 if i.rule_id == "seo-hreflang-not-reciprocal"]
        self.assertEqual(len(found), 1)

    def test_tracking_parameters_do_not_make_a_view(self):
        pages = [
            PageResult(url="https://x/en/article?utm_source=a", depth=0, raw_html=(
                '<html><head><link rel="alternate" hreflang="uk" '
                'href="https://x/uk/article"></head></html>')),
            PageResult(url="https://x/uk/article", depth=0,
                       raw_html="<html><head></head></html>"),
        ]
        found = [i for i in crosspage.issues_for(pages)
                 if i.rule_id == "seo-hreflang-not-reciprocal"]
        self.assertEqual(len(found), 1)

    def test_reciprocal_hreflang_is_clean(self):
        pages = [
            PageResult(url="https://x/en/article", depth=0, raw_html=(
                '<html><head><link rel="alternate" hreflang="uk" '
                'href="/uk/article/"></head></html>')),
            PageResult(url="https://x/uk/article", depth=0, raw_html=(
                '<html><head><link rel="alternate" hreflang="en" '
                'href="/en/article"></head></html>')),
        ]
        found = [issue for issue in crosspage.issues_for(pages)
                 if issue.rule_id == "seo-hreflang-not-reciprocal"]
        self.assertEqual(found, [])

    def test_hreflang_target_outside_the_crawl_is_not_assumed_broken(self):
        pages = [PageResult(url="https://x/en/article", depth=0, raw_html=(
            '<html><head><link rel="alternate" hreflang="uk" '
            'href="/uk/article"></head></html>'))]
        self.assertNotIn("seo-hreflang-not-reciprocal",
                         {issue.rule_id for issue in crosspage.issues_for(pages)})


class ImageDimensions(unittest.TestCase):
    def test_an_oversized_image_is_a_finding(self):
        scan = media.MediaFetchScan()
        scan.dimensions = [("https://x/hero.jpg", 6000, 4000)]
        found = media.oversized_issues(scan)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].details["width"], 6000)

    def test_an_ordinary_image_is_not(self):
        scan = media.MediaFetchScan()
        scan.dimensions = [("https://x/a.jpg", 1200, 800)]
        self.assertEqual(media.oversized_issues(scan), [])

    def test_dimensions_are_read_from_a_header_alone(self):
        from io import BytesIO

        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (3000, 200)).save(buffer, format="PNG")
        self.assertEqual(media._dimensions_of(buffer.getvalue()), (3000, 200))


class DeclaredLanguage(unittest.TestCase):
    UK = "Ми будуємо інструмент, який шукає проблеми на сторінках сайту. " * 8
    IT = "Costruiamo uno strumento che trova i problemi nelle pagine web. " * 8
    DE = "Wir bauen ein Werkzeug das Probleme auf Webseiten findet und meldet. " * 8

    def _rules(self, lang: str, text: str) -> set:
        document = analyze_document(
            f'<html lang="{lang}"><body><p>{text}</p></body></html>', "t")
        return {i.rule_id for i in document.issues}

    def test_english_declared_over_ukrainian_text_is_reported(self):
        self.assertIn("html-lang-mismatch", self._rules("en", self.UK))

    def test_a_correct_declaration_is_silent(self):
        self.assertNotIn("html-lang-mismatch", self._rules("uk", self.UK))
        self.assertNotIn("html-lang-mismatch", self._rules("it", self.IT))

    def test_a_regional_tag_still_matches(self):
        self.assertNotIn("html-lang-mismatch", self._rules("uk-UA", self.UK))

    def test_a_language_the_detector_does_not_know_is_left_alone(self):
        # The detector has no "some fourth language" verdict: anything
        # non-Cyrillic without Italian markers comes back `en`. Reporting
        # `lang="de"` as a lie would be this tool inventing a fact.
        self.assertNotIn("html-lang-mismatch", self._rules("de", self.DE))

    def test_a_short_page_is_not_judged(self):
        self.assertNotIn("html-lang-mismatch", self._rules("en", "Save"))


class ADensityNotAWord(unittest.TestCase):
    """One Italian marker in a long English page is an accident.

    Measured on live pages: `wordpress.org/news` and `squarespace.com` were
    both read as Italian, each on a single hit in several hundred words, and
    the `html-lang-mismatch` rule reported both as lying about their
    language. The corpus says what the real rate is - the English half
    contains no marker at all, the Italian half runs to 5.9 per 100 words.
    """

    def test_a_long_english_page_with_one_stray_marker_is_english(self):
        from lang_detect import guess_language_safe

        text = ("Skip to content Showcase Plugins Themes Hosting News Resources "
                "Learn Documentation Education Forums Developers Get involved "
                "About Five for the Future Enterprise Swag Store Gallery ") * 6
        self.assertEqual(guess_language_safe(text + " one per page "), "en")

    def test_a_short_italian_line_still_reads_as_italian(self):
        from lang_detect import guess_language_safe

        self.assertEqual(
            guess_language_safe("Carica il file che vuoi convertire"), "it")


if __name__ == "__main__":
    unittest.main()
