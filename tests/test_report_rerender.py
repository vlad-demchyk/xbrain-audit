"""`xaudit report <run-folder>` writes the styled report again without crawling.

The run folder's checkpoint is the audit's product; the report is a view of
it. Re-rendering applies the current code's masking (findings are rebuilt
through `finding_contract`, so `privacy` masks them at birth), grouping and
compact sections, and the certainty view asked for now.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from audit.base import EXACT, NEEDS_BROWSER, Issue
from audit.engine import AccessibilityResult, DocumentReport

SITE = "https://contoso.sharepoint.com/sites/ExampleSite"


def _run_folder(folder: Path) -> Path:
    from cli_impl import checkpoint

    documents = []
    for page in range(4):
        source = f"{SITE}/SitePages/P{page}.aspx"
        issues = [Issue("axe:color-contrast", "serious", selector=f"span:nth-of-type({n})",
                        snippet=f'<span class="name_1a2b3c4d">Person {page}-{n}</span>',
                        confidence=NEEDS_BROWSER, source=source, engine="axe",
                        details={"zone": "custom", "zone_name": "People Directory"})
                  for n in range(50)]
        issues.append(Issue("axe:image-alt", "serious", selector="img",
                            snippet='<img src="/_layouts/15/userphoto.aspx?accountname=jane.doe@contoso.com">',
                            confidence=EXACT, source=source, engine="axe",
                            details={"zone": "custom", "zone_name": "People Directory"}))
        documents.append(DocumentReport(source=source, issues=issues))
    result = AccessibilityResult(root=SITE, mode="web", documents=documents)
    run = folder / "run"
    checkpoint.save_audit(run, result)
    # The checkpoint as an older build wrote it: the address unmasked.
    path = run / checkpoint.AUDIT_FILE
    payload = json.loads(path.read_text(encoding="utf-8"))
    for document in payload["documents"]:
        for issue in document["issues"]:
            if "userphoto" in json.dumps(issue):
                issue["snippet"] = ('<img src="/_layouts/15/userphoto.aspx?'
                                    'accountname=jane.doe@contoso.com">')
    path.write_text(json.dumps(payload), encoding="utf-8")
    (run / "state.json").write_text(json.dumps({
        "argv": ["fullscan", SITE, "--language", "it", "--unsettled"]}), encoding="utf-8")
    return run


class ReRenderingARunFolder(unittest.TestCase):
    def _render(self, *extra):
        from cli import build_parser

        with tempfile.TemporaryDirectory() as tmp:
            run = _run_folder(Path(tmp))
            out = Path(tmp) / "short.html"
            args = build_parser().parse_args(
                ["report", str(run), "--styled-report", str(out), *extra])
            with mock.patch("audit.driver.available", return_value=(False, "no browser")):
                code = args.func(args)
            return code, out.read_text(encoding="utf-8") if out.exists() else ""

    def test_it_writes_the_report_from_the_checkpoint_without_crawling(self):
        with mock.patch("cli_impl.auditpass._run_browser_pass", side_effect=AssertionError("audited")):
            code, html = self._render("--language", "it", "--unsettled")
        self.assertEqual(code, 0)
        self.assertIn("Da verificare manualmente (1)", html)
        # 200 undecided contrasts on one part's names: one compact row.
        self.assertEqual(html.count('<tr class="side-row">'), 1)

    def test_masking_is_applied_again(self):
        _code, html = self._render("--unsettled")
        self.assertNotIn("jane.doe@contoso.com", html)

    def test_without_unsettled_the_to_check_section_is_left_out(self):
        _code, html = self._render("--language", "en")
        self.assertNotIn("To check by hand", html)
        self.assertIn("axe:image-alt", html)

    def test_a_folder_without_a_run_is_refused(self):
        from cli import build_parser

        with tempfile.TemporaryDirectory() as tmp:
            args = build_parser().parse_args(
                ["report", tmp, "--styled-report", str(Path(tmp) / "x.html")])
            self.assertEqual(args.func(args), 2)


if __name__ == "__main__":
    unittest.main()
