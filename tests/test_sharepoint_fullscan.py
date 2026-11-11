"""`xanalyze fullscan` reads a SharePoint Online site the way `audit` does.

Same plan, same page tree, same refusals and the same exit code, through the
same functions in `cli_impl.auditpass`. Also: a refusal for a missing
sign-in leaves no run folder behind, in either command, and a resumed run
keeps the zones. Every address is a placeholder; nothing reaches a network.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sharepoint_tree as spt
from cli_impl import auditpass
from models import CrawlDiagnostics, PageDiagnostics, PageResult

SITE = "https://contoso.sharepoint.com/sites/ExampleSite"
FIXTURE = (Path(__file__).parent / "fixtures" / "sharepoint"
           / "modern_page.html")


def _tree(status, pages=()):
    tree = spt.SiteTree(site_url=SITE)
    tree.web = spt.TreeWeb(url=SITE, server_relative_url="/sites/ExampleSite")
    tree.webs = [tree.web]
    tree.pages = [spt.TreePage(url=url, source="sitepages") for url in pages]
    if status == spt.STATUS_AUTH:
        tree.auth_required, tree.auth_reason = True, spt.AUTH_FORMS_HEADER
    if status == spt.STATUS_ACCESS_DENIED:
        tree.access_denied = True
    assert tree.status == status, tree.status
    return tree


def _main(argv, *, signed_in, crawl_site=None, extra=()):
    import cli

    out, err = io.StringIO(), io.StringIO()
    host = "contoso.sharepoint.com" if signed_in else ""
    patches = [mock.patch("site_session.has_session", return_value=signed_in),
               mock.patch("cli_impl.auditpass.apply_session", return_value=host),
               mock.patch("cli.apply_session", return_value=host),
               # The content pass is not what this file is about, and its
               # detectors are slow to load.
               mock.patch("cli_impl.fullscan._content_findings_from_pages",
                          return_value=[]),
               *extra]
    if crawl_site is not None:
        patches.append(mock.patch.object(auditpass, "crawl_site", crawl_site))
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _never(*_a, **_k):
    raise AssertionError("crawled without a session")


class NoSignInLeavesNothingBehind(unittest.TestCase):
    def test_fullscan_refuses_before_the_run_folder(self):
        from cli_impl import runfolder

        with mock.patch.object(runfolder, "prepare",
                               side_effect=AssertionError("folder made")):
            code, _out, err = _main(
                ["fullscan", SITE, "--no-browser", "--no-hints"],
                signed_in=False, crawl_site=_never)
        self.assertEqual(code, 2)
        self.assertIn(f"xanalyze login {SITE}", err)

    def test_audit_refuses_before_the_run_folder(self):
        from cli_impl import runfolder

        with mock.patch.object(runfolder, "prepare_for",
                               side_effect=AssertionError("folder made")):
            code, _out, err = _main(
                ["audit", SITE, "--no-browser", "--no-hints"],
                signed_in=False, crawl_site=_never)
        self.assertEqual(code, 2)
        self.assertIn(f"xanalyze login {SITE}", err)

    def test_no_session_flag_is_refused_with_its_own_sentence(self):
        code, _out, err = _main(
            ["fullscan", SITE, "--no-browser", "--no-hints", "--no-session"],
            signed_in=True, crawl_site=_never)
        self.assertEqual(code, 2)
        self.assertIn("--no-session", err)

    def test_an_ordinary_site_is_not_asked_for_a_sign_in(self):
        self.assertEqual(auditpass.sign_in_refusal(
            "https://example.com/", mock.Mock(no_session=False)), "")


class FullscanReadsTheTree(unittest.TestCase):
    def test_a_refused_tree_exits_2_like_audit(self):
        for status, words in ((spt.STATUS_AUTH, "expired"),
                              (spt.STATUS_ACCESS_DENIED, "no permission")):
            with self.subTest(status):
                tree = _tree(status)
                code, _out, err = _main(
                    ["fullscan", SITE, "--no-browser", "--no-hints"],
                    signed_in=True, crawl_site=lambda *a, t=tree, **k: ([], t))
                self.assertEqual(code, 2)
                self.assertIn(words, err)
                self.assertIn(f"xanalyze login {SITE}", err)

    def test_the_tree_and_the_zones_reach_the_json(self):
        url = f"{SITE}/SitePages/Home.aspx"
        tree = _tree(spt.STATUS_OK, [url])
        page = PageResult(url=url, depth=0,
                          raw_html=FIXTURE.read_text(encoding="utf-8"),
                          diagnostics=PageDiagnostics(status_code=200))
        got = {}

        def fake_crawl_site(target, config, **kwargs):
            got.update(kwargs)
            kwargs["walk"].pages_read = 1
            return [page], tree

        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = _main(
                ["fullscan", SITE, "--no-browser", "--no-hints",
                 "--report", str(Path(tmp) / "r.md"),
                 "--styled-report", str(Path(tmp) / "r.html")],
                signed_in=True, crawl_site=fake_crawl_site)
        self.assertIn(code, (0, 1), err[-2000:])
        self.assertEqual((got["page_tree"], got["site_scope"]),
                         ("sharepoint", "/sites/ExampleSite"))
        data = json.loads(out[out.index("{"):])
        self.assertEqual(data["audit"]["page_tree"]["status"], "ok")
        self.assertEqual(data["audit"]["page_tree"]["pages_read"], 1)
        self.assertEqual(data["audit"]["sharepoint"]["pages"], 1)
        self.assertIn("[sharepoint] SharePoint site:", err)
        zones = {issue.get("zone") for issue in data["audit"]["issues"]}
        self.assertTrue(zones <= {"custom", "author", None, ""}, zones)
        self.assertIn("custom", zones)

    def test_the_flags_exist_on_fullscan(self):
        import cli

        args = cli.build_parser().parse_args(
            ["fullscan", SITE, "--page-tree", "links", "--site-scope",
             "/sites/Other", "--ootb-registry", "x.json"])
        self.assertEqual((args.page_tree, args.site_scope, args.ootb_registry),
                         ("links", "/sites/Other", "x.json"))


class WhatSurvivesAResume(unittest.TestCase):
    def test_the_checkpoint_keeps_the_zones_and_the_page_tree(self):
        from audit.engine import AccessibilityResult
        from cli_impl import checkpoint

        result = AccessibilityResult(root=SITE, mode="web")
        result.sharepoint = {"pages": 2, "zones": {"custom": 3}}
        result.page_tree = {"mode": "sharepoint", "status": "ok"}
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint.save_audit(tmp, result)
            loaded = checkpoint.load_audit(tmp)
        self.assertEqual(loaded.sharepoint, result.sharepoint)
        self.assertEqual(loaded.page_tree, result.page_tree)

    def test_out_of_scope_is_a_field(self):
        self.assertEqual(CrawlDiagnostics().out_of_scope, 0)


if __name__ == "__main__":
    unittest.main()
