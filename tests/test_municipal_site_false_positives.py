"""False positives the final audit of a municipal WordPress site found (T-1961).

Each test is the shape the 381-page crawl produced, checked against its HTML.
"""
from __future__ import annotations

import json
import unittest

from audit.base import ADVISORY, EXACT, MINOR
from audit.browser import issues_from_htmlcs

H30_2 = "WCAG2AA.Principle1.Guideline1_1.1_1_1.H30.2"


def _h30(html: str, label: str | None = None):
    message = {"type": 1, "code": H30_2, "html": html, "msg": "…", "tag": "a"}
    if label is not None:
        message["label"] = label
    return issues_from_htmlcs(json.dumps({"messages": [message]}),
                              "https://site/")[0]


class GalleryLinkNamedByAttribute(unittest.TestCase):
    def test_aria_label_reported_by_the_collector_makes_it_a_note(self):
        issue = _h30('<a href="/a.jpg"><img src="a.jpg"></a>',
                     label="Apri immagine 1")
        self.assertEqual(issue.severity, MINOR)
        self.assertEqual(issue.confidence, ADVISORY)
        self.assertEqual(issue.details["accessible_name_from_attributes"],
                         "Apri immagine 1")

    def test_a_cached_payload_without_label_reads_the_opening_tag(self):
        for tag in ('<a href="/a.jpg" aria-label="Piazza Grande"><img src="a.jpg"></a>',
                    "<a title='Piazza' href=/a.jpg><img></a>",
                    '<a aria-labelledby="cap1" href="#"><img></a>'):
            with self.subTest(tag=tag):
                self.assertEqual(_h30(tag).severity, MINOR)

    def test_an_unnamed_link_keeps_its_weight(self):
        """The rule's real finding must survive the fix."""
        for tag in ('<a href="/a.jpg"><img src="a.jpg"></a>',
                    '<a href="/a.jpg" aria-label=""><img src="a.jpg"></a>',
                    # A name on the image, not the link, is not read here.
                    '<a href="/a.jpg"><img src="a.jpg" title="x"></a>'):
            with self.subTest(tag=tag):
                issue = _h30(tag, label="")
                self.assertNotEqual(issue.severity, MINOR)
                self.assertEqual(issue.confidence, EXACT)

    def test_other_htmlcs_codes_are_not_touched(self):
        message = {"type": 1, "code": "WCAG2AA.Principle1.Guideline1_1.1_1_1.H37",
                   "html": '<img aria-label="x">', "msg": "…", "tag": "img",
                   "label": "x"}
        issue = issues_from_htmlcs(json.dumps({"messages": [message]}),
                                   "https://site/")[0]
        self.assertNotEqual(issue.severity, MINOR)


class EnglishPageWithAnItalianName(unittest.TestCase):
    """The municipal site's English pages: 23 of 24 `html-lang-mismatch` were false.

    The header and footer repeat "Youtube di Città di Esempio" and the
    footer says "Comune di Esempio": ` di ` seven times in 300 words, the
    rate of Italian prose, from one repeated name.
    """

    CHROME = ("Join us on: Instagramm Facebook Youtube di Città di Esempio "
              "Home Experiences Itineraries Places to visit Events Schools ")

    def test_a_repeated_name_does_not_make_a_page_italian(self):
        import lang_detect

        body = (self.CHROME * 4 + "Experiences Countermine Tunnels of the 2nd "
                "Ravelin and Donato Bastion Multimedia Video Room Virtualift "
                "Virtual Elevator Town Talking Map Tools and machines for "
                "building the Fortress Museum of the Great War Civic Museum "
                "Copyright 2026 Comune di Esempio Privacy Policy ")
        self.assertGreater(len(body.split()), 100)
        self.assertEqual(lang_detect.guess_language_safe(body), "en")

    def test_untranslated_italian_paragraphs_still_read_as_italian(self):
        import lang_detect

        body = ("L'Associazione Guide Turistiche del Friuli Venezia Giulia, una "
                "delle più antiche in Italia, è stata fondata nel 1955, anno in "
                "cui sono state abilitate le prime guide operanti sul "
                "territorio. Da allora riunisce un alto numero di "
                "professionisti iscritti all'Albo regionale, molti dei quali "
                "anche accompagnatori, residenti in Friuli Venezia Giulia ed in "
                "grado di soddisfare tutte le richieste di visite guidate da "
                "svolgere nella regione nelle principali lingue europee. "
                "Collabora con enti ed operatori pubblici e privati al fine di "
                "promuovere l'offerta e valorizzare il territorio regionale. ") * 2
        self.assertEqual(lang_detect.guess_language_safe(body), "it")


SKIP_LINK_PAGE = """<!DOCTYPE html><html lang="it"><head><title>t</title><style>
  header { background: #050505; padding: 20px; }
  .skip { position: fixed; color: #007a52; clip: rect(0 0 0 0); width: 1px;
          height: 1px; overflow: hidden; }
  .skip:focus { clip: auto; width: auto; height: auto; color: #333; background: #fff; }
  .faint { color: #9a9a9a; background: #ffffff; }
</style></head><body><header><a class="skip" href="#main">Vai al contenuto</a>
<span style="color:#fff">Town</span></header>
<main id="main"><h1>Titolo</h1><p class="faint">Testo grigio chiaro su bianco.</p></main>
</body></html>"""


class HiddenSkipLinkContrast(unittest.TestCase):
    """`htmlcs:1_4_3` on the municipal site's skip link, 327 times: measured while
    clipped to one pixel against the header's dark background (3.79:1); as
    shown on focus it is 12.63:1."""

    @classmethod
    def setUpClass(cls):
        from audit import driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from audit import browser

        with TemporaryDirectory() as folder:
            path = Path(folder) / "page.html"
            path.write_text(SKIP_LINK_PAGE, encoding="utf-8")
            options = browser.BrowserAuditOptions(
                run_axe=False, run_htmlcs=True, run_states=False,
                run_measurements=False, allow_local_files=True, settle_ms=200)
            driver.ensure_headless_application()
            runner = driver.BrowserAuditRunner(options)
            try:
                issues = runner.audit(path.resolve().as_uri()).issues
            finally:
                runner.close()
        cls.contrast = [i for i in issues if i.rule_id == "htmlcs:1_4_3"]

    def test_the_hidden_skip_link_is_a_question_not_a_violation(self):
        skip = [i for i in self.contrast if "skip" in i.snippet]
        self.assertTrue(skip, [i.snippet for i in self.contrast])
        for issue in skip:
            self.assertEqual(issue.severity, MINOR)
            self.assertTrue(issue.details["visually_hidden"])

    def test_visible_low_contrast_text_keeps_its_weight(self):
        faint = [i for i in self.contrast if "faint" in i.snippet]
        self.assertTrue(faint, [i.snippet for i in self.contrast])
        self.assertNotEqual(faint[0].severity, MINOR)


if __name__ == "__main__":
    unittest.main()
