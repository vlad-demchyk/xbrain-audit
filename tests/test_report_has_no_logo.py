"""The report carries no product logo.

The old XAnalyze mark went with the rename to XBrain Audit, and a report is
about the audited site, not the tool. The header is the name, the target and
the run line; an image in it would be the old logo coming back.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import audit
from models import PageDiagnostics, PageResult
from report.model import from_accessibility
from report.template import render_html


def _page(html: str) -> PageResult:
    return PageResult(url="https://x.test/", depth=0, raw_html=html,
                      diagnostics=PageDiagnostics(status_code=200, final_url="",
                                                  headers={}))


class TheReportHasNoLogo(unittest.TestCase):
    def test_the_header_holds_no_image_in_any_language(self):
        model = from_accessibility(
            audit.analyze_pages([_page("<html><body><img src=a.png></body></html>")],
                                "https://x.test", media=False), "en")
        for lang in ("uk", "it", "en"):
            with self.subTest(lang=lang):
                html = render_html(model, lang)
                header = re.search(r'<header class="report-header">(.*?)</header>',
                                   html, re.S)
                self.assertIsNotNone(header)
                self.assertNotIn("<img", header.group(1))
                self.assertNotIn("data:image/png;base64", html)

    def test_the_old_mark_is_not_shipped(self):
        root = Path(__file__).resolve().parent.parent
        self.assertFalse((root / "ui" / "design" / "assets" / "logo.png").exists())


if __name__ == "__main__":
    unittest.main()
