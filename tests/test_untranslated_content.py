"""Text left in another language's wording on an otherwise translated page.

The comparison is exact; the judgement comes from the surroundings. A string
identical across two language versions means nothing by itself - the pair may
be one page served twice - so the rule speaks only when everything around
that string differs.

Half of these tests are about what it must not say. The reviewer's own report
states that street names and organisation names are *meant* to stay in the
source language, so a rule that reported those would be arguing with the
house style of every multilingual site.
"""
import unittest

from audit import crosspage

RULE = "seo-untranslated-content"

IT_BODY = [
    "Il borgo è una città fortezza patrimonio mondiale",
    "Gli eventi in programma nella città stellata",
    "Scopri i percorsi guidati tra i bastioni",
    "Il museo storico militare della fortezza",
    "Informazioni utili per la tua visita",
    "Come raggiungere la piazza principale",
]
DE_BODY = [
    "Der Ort ist eine Festungsstadt des Weltkulturerbes",
    "Die geplanten Veranstaltungen in der Sternenstadt",
    "Entdecke die Führungen entlang der Bastionen",
    "Das historische Militärmuseum der Festung",
    "Nützliche Informationen für deinen Besuch",
    "So erreichen Sie den Hauptplatz",
]


class _Page:
    def __init__(self, url, html):
        self.url, self.raw_html, self.error, self.diagnostics = url, html, None, None


def document(lang, url_it, url_de, paragraphs, extra=""):
    links = (f'<link rel="alternate" hreflang="it" href="{url_it}">'
             f'<link rel="alternate" hreflang="de" href="{url_de}">')
    body = "".join(f"<p>{text}</p>" for text in paragraphs)
    return (f'<html lang="{lang}"><head>{links}</head>'
            f"<body>{body}{extra}</body></html>")


def build(de_paragraphs, de_extra="", it_extra=""):
    it_url, de_url = "https://example.com/pagina/", "https://example.com/de/seite/"
    return [
        _Page(it_url, document("it", it_url, de_url, IT_BODY, it_extra)),
        _Page(de_url, document("de", it_url, de_url, de_paragraphs, de_extra)),
    ]


def findings(pages) -> list:
    return [i for i in crosspage.issues_for(pages) if i.rule_id == RULE]


class TheFragmentLeftBehind(unittest.TestCase):

    def test_a_paragraph_still_in_the_other_language_is_reported(self):
        left_behind = DE_BODY[:-1] + [IT_BODY[-1]]
        found = findings(build(left_behind))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].details["text"], IT_BODY[-1])

    def test_the_finding_lands_on_the_translation(self):
        found = findings(build(DE_BODY[:-1] + [IT_BODY[-1]]))
        self.assertEqual(found[0].source, "https://example.com/de/seite/")
        self.assertEqual(found[0].details["language"], "it")

    def test_chrome_counts_as_much_as_prose(self):
        # A breadcrumb crumb and a filter option are where this was found by
        # hand, and neither is a paragraph.
        crumb = '<nav><a href="/x">Vivere il comune oggi</a></nav>'
        found = findings(build(DE_BODY, de_extra=crumb, it_extra=crumb))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].details["text"], "Vivere il comune oggi")

    def test_one_string_is_named_once_however_many_nodes_hold_it(self):
        twice = ('<nav><a href="/x">Vivere il comune oggi</a></nav>'
                 '<footer><a href="/x">Vivere il comune oggi</a></footer>')
        self.assertEqual(len(findings(build(DE_BODY, twice, twice))), 1)


class WhereItMustStaySilent(unittest.TestCase):

    def test_a_fully_translated_page_is_silent(self):
        self.assertEqual(findings(build(DE_BODY)), [])

    def test_a_pair_that_is_identical_throughout_is_not_this_finding(self):
        # Two addresses serving one page: the canonical rules describe that.
        self.assertEqual(findings(build(IT_BODY)), [])

    def test_a_two_word_proper_noun_is_left_alone(self):
        # "Contrada Barbaro", "Borgo Udine": the report says these are meant
        # to stay in the source language.
        name = '<p>Contrada Barbaro</p>'
        self.assertEqual(findings(build(DE_BODY, name, name)), [])

    def test_a_page_with_little_to_compare_says_nothing(self):
        short_it = IT_BODY[:2]
        short_de = DE_BODY[:1] + IT_BODY[1:2]
        it_url, de_url = "https://example.com/p/", "https://example.com/de/s/"
        pages = [_Page(it_url, document("it", it_url, de_url, short_it)),
                 _Page(de_url, document("de", it_url, de_url, short_de))]
        self.assertEqual(findings(pages), [])

    def test_numbers_and_addresses_are_not_prose(self):
        for text in ("33100 Esempio UD", "+39 0432 000000",
                     "info@example.com", "2026 - 2027"):
            with self.subTest(text=text):
                node = f"<p>{text}</p>"
                self.assertEqual(findings(build(DE_BODY, node, node)), [])

    def test_a_single_page_run_says_nothing(self):
        self.assertEqual(findings(build(DE_BODY)[:1]), [])


if __name__ == "__main__":
    unittest.main()
