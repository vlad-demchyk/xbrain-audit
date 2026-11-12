"""The report shows what it could not settle, separately, and counts only proof.

An unsettled finding (axe could not measure contrast over an image, a video
without a caption track) may be a real failure, and a recommendation (WebP,
an AAA abbreviation) is not one. Hiding the first lost real problems from the
report; mixing both into the list counted them as proven defects.
"""

from __future__ import annotations

import re
import unittest

import audit
from audit.base import ADVISORY, EXACT, NEEDS_BROWSER
from models import PageDiagnostics, PageResult
from report.model import from_accessibility
from report.template import render_html


def _model():
    html = ("<html lang='en'><body><main><h1>T</h1>"
            "<button></button><img src='a.png'><p>Text</p></main></body></html>")
    page = PageResult(url="https://x.test/", depth=0, raw_html=html,
                      diagnostics=PageDiagnostics(status_code=200, final_url="", headers={}))
    model = from_accessibility(audit.analyze_pages([page], "https://x.test", media=False), "en")
    from report.model import page_index
    model.pages = page_index([{"source": "https://x.test/", "findings_count": 3, "error": ""}])
    return model


class TheReportSaysHowSureItIs(unittest.TestCase):
    def test_three_sections_and_totals_from_proof_only(self):
        model = _model()
        self.assertGreaterEqual(len(model.findings), 2)
        model.findings[0].confidence = NEEDS_BROWSER
        model.findings[1].confidence = ADVISORY
        for finding in model.findings[2:]:
            finding.confidence = EXACT
        proven = len(model.grouped_findings()) - 2
        for lang, verify, advise in (("en", "To check by hand", "Recommendations"),
                                     ("it", "Da verificare manualmente", "Raccomandazioni"),
                                     ("uk", "Перевірити вручну", "Рекомендації")):
            with self.subTest(lang=lang):
                html = render_html(model, lang)
                self.assertIn(f"{verify} (1)", html)
                self.assertIn(f"{advise} (1)", html)
                main = re.search(r'<section class="findings">\s*<h2>[^<]*\((\d+)\)</h2>', html)
                self.assertEqual(int(main.group(1)), proven)
                # Advice is the very last section: after the findings, the
                # to-check list and the pages examined.
                self.assertGreater(html.index(f"{advise} (1)"), html.index('<section class="pages"'))
                self.assertLess(html.index(f"{verify} (1)"), html.index('<section class="pages"'))

    def test_no_extra_sections_when_everything_is_proven(self):
        model = _model()
        for finding in model.findings:
            finding.confidence = EXACT
        html = render_html(model, "it")
        self.assertNotIn("Da verificare manualmente", html)
        self.assertNotIn("Raccomandazioni (", html)


if __name__ == "__main__":
    unittest.main()
