"""The SharePoint pipeline end to end, without a tenant.

Every network answer here is a stand-in: the crawl's session, the page tree,
the browser. What is under test is the plumbing between them - that a seeded
crawl reads its list and nothing else, that a scope holds, that a missing or
refused sign-in stops the run with a sentence instead of auditing the
sign-in page, and that what the run left out reaches its JSON summary.
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from unittest import mock

import crawler
import sharepoint_tree as spt
from cli_impl import auditpass
from crawler import CrawlConfig, crawl, in_site_scope
from models import CrawlDiagnostics, PageDiagnostics, PageResult

SITE = "https://contoso.sharepoint.com/sites/ExampleSite"
FIXTURE = (Path(__file__).parent / "fixtures" / "sharepoint"
           / "modern_page.html")


class _Response:
    def __init__(self, url, text):
        self.url = url
        self.text = text
        self.status_code = 200
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def raise_for_status(self):
        return None


class _Session:
    """Every page links to the same set of addresses."""

    headers: dict = {}

    def __init__(self, links=()):
        self.fetched = []
        self.links = links

    def get(self, url, timeout=None, **_kwargs):
        self.fetched.append(url)
        anchors = "".join(f'<a href="{href}">link</a>' for href in self.links)
        html = (f"<html lang='en'><body><h1>A page with real copy on it</h1>"
                f"{anchors}</body></html>")
        return _Response(url, html)


def _crawl(start, *, links=(), **kwargs):
    session = _Session(links)
    walk = CrawlDiagnostics()
    config = kwargs.pop("config", None) or CrawlConfig(max_depth=3,
                                                       max_pages=20)
    with mock.patch("crawler.requests.Session", return_value=session):
        pages = crawl(start, config, walk=walk, **kwargs)
    return pages, walk, session


# -- crawler ----------------------------------------------------------------


class SeedsInsteadOfAWalk(unittest.TestCase):
    def test_only_the_seeds_are_read(self):
        seeds = [f"{SITE}/SitePages/A.aspx", f"{SITE}/SitePages/B.aspx"]
        _pages, walk, session = _crawl(
            SITE, links=(f"{SITE}/SitePages/Linked.aspx",), seeds=seeds)
        self.assertEqual(session.fetched, seeds)
        self.assertEqual(walk.pages_read, 2)
        self.assertEqual(walk.queued_when_stopped, 0)

    def test_max_pages_still_applies_and_says_what_it_left(self):
        seeds = [f"{SITE}/SitePages/{n}.aspx" for n in range(5)]
        _pages, walk, session = _crawl(
            SITE, seeds=seeds, config=CrawlConfig(max_pages=2))
        self.assertEqual(len(session.fetched), 2)
        self.assertEqual(walk.queued_when_stopped, 3)

    def test_without_seeds_the_walk_is_what_it_was(self):
        _pages, _walk, session = _crawl(
            "https://example.test/", links=("/a", "/b"),
            config=CrawlConfig(max_depth=1, max_pages=10))
        self.assertEqual(len(session.fetched), 3)


class TheScopeHolds(unittest.TestCase):
    def test_links_outside_the_site_are_counted_not_read(self):
        _pages, walk, session = _crawl(
            f"{SITE}/", site_scope="/sites/ExampleSite",
            links=("/SITES/examplesite/SitePages/Same.aspx",
                   "/sites/ExampleSite2/SitePages/Other.aspx",
                   "/sites/HR/SitePages/Home.aspx"),
            config=CrawlConfig(max_depth=1, max_pages=10))
        self.assertEqual(
            [u.lower() for u in session.fetched],
            [f"{SITE}".lower(), f"{SITE}/sitepages/same.aspx".lower()])
        self.assertEqual(walk.out_of_scope, 2)

    def test_a_seed_outside_the_scope_is_counted_too(self):
        _pages, walk, session = _crawl(
            SITE, site_scope="/sites/ExampleSite",
            seeds=[f"{SITE}/SitePages/A.aspx",
                   "https://contoso.sharepoint.com/sites/HR/SitePages/B.aspx"])
        self.assertEqual(session.fetched, [f"{SITE}/SitePages/A.aspx"])
        self.assertEqual(walk.out_of_scope, 1)

    def test_segment_aware_and_case_blind(self):
        self.assertTrue(in_site_scope(f"{SITE}/x", "/sites/examplesite"))
        self.assertTrue(in_site_scope(SITE, "/sites/ExampleSite/"))
        self.assertFalse(in_site_scope(f"{SITE}2/x", "/sites/ExampleSite"))
        self.assertTrue(in_site_scope("https://x.test/a", ""))


class OneSessionForEveryReader(unittest.TestCase):
    def test_the_page_tree_uses_the_crawlers_public_session(self):
        record = {"name": "FedAuth", "value": "synthetic",
                  "domain": "contoso.sharepoint.com", "path": "/",
                  "host_only": True}
        with mock.patch.object(crawler, "http_session",
                               wraps=crawler.http_session) as made:
            session = spt.session_from_cookies([record], SITE)
        made.assert_called_once()
        self.assertEqual([c.name for c in session.cookies], ["FedAuth"])


# -- site_session ----------------------------------------------------------------


class TheFetcherCopyIsFiltered(unittest.TestCase):
    def test_save_cookies_never_writes_the_sharepoint_session(self):
        """The session stays in the browser profile (`SESSION_BROWSER`):
        no FedAuth, no rtFa, no HttpOnly cookie, nothing off the tenant."""
        import site_session

        host = "contoso.sharepoint.com"
        try:
            site_session.save_cookies(host, [
                {"name": "FedAuth", "value": "s", "domain": host},
                {"name": "ESTSAUTHPERSISTENT", "value": "s",
                 "domain": "login.microsoftonline.com"},
                {"name": "rtFa", "value": "s", "domain": ".sharepoint.com"},
                {"name": "other", "value": "s", "domain": host,
                 "http_only": True},
                {"name": "lang", "value": "s", "domain": host},
            ])
            saved = site_session.load_cookies(host)
        finally:
            site_session.forget(host)
        self.assertEqual([(c["name"], c["domain"]) for c in saved],
                         [("lang", host)])

    def test_the_window_uses_the_same_filter(self):
        try:
            from ui import site_sign_in
        except Exception:  # noqa: BLE001
            self.skipTest("PySide6 not available")
        import site_session

        self.assertIs(site_sign_in.cookie_is_for_fetcher,
                      site_session.cookie_is_for_fetcher)


# -- auditpass ----------------------------------------------------------------


def _tree(status, pages=(), **fields):
    tree = spt.SiteTree(site_url=SITE)
    if status not in (spt.STATUS_ERROR,):
        tree.web = spt.TreeWeb(url=SITE, server_relative_url="/sites/ExampleSite")
        tree.webs = [tree.web]
    tree.pages = [spt.TreePage(url=url, source="sitepages") for url in pages]
    if status == spt.STATUS_AUTH:
        tree.auth_required, tree.auth_reason = True, spt.AUTH_FORMS_HEADER
    if status == spt.STATUS_ACCESS_DENIED:
        tree.access_denied = True
    if status in (spt.STATUS_ERROR, spt.STATUS_PARTIAL):
        tree.errors.append(spt.TreeError(source="web", url=SITE,
                                         message="HTTP 500", status=500))
    for key, value in fields.items():
        setattr(tree, key, value)
    assert tree.status == status, tree.status
    return tree


class ThePageList(unittest.TestCase):
    def _run(self, tree, **kwargs):
        calls = []

        def fake_crawl(target, config, **kw):
            calls.append(kw)
            return ["page"]

        with mock.patch("crawler.crawl", fake_crawl):
            pages, got = auditpass.sharepoint_pages(
                SITE, CrawlConfig(), page_tree="sharepoint",
                site_scope="/sites/ExampleSite", session=object(),
                discover=lambda *a, **k: tree, **kwargs)
        return pages, got, calls

    def test_a_tree_seeds_the_crawl(self):
        tree = _tree(spt.STATUS_OK, [f"{SITE}/SitePages/Home.aspx",
                                     f"{SITE}/SitePages/About.aspx"])
        pages, got, calls = self._run(tree)
        self.assertIs(got, tree)
        self.assertEqual(calls[0]["seeds"], [f"{SITE}/SitePages/Home.aspx",
                                             f"{SITE}/SitePages/About.aspx"])
        self.assertEqual(calls[0]["site_scope"], "/sites/ExampleSite")

    def test_a_partial_tree_still_seeds(self):
        tree = _tree(spt.STATUS_PARTIAL, [f"{SITE}/SitePages/Home.aspx"])
        _pages, _got, calls = self._run(tree)
        self.assertIn("seeds", calls[0])

    def test_a_refused_sign_in_crawls_nothing(self):
        for status in (spt.STATUS_AUTH, spt.STATUS_ACCESS_DENIED):
            with self.subTest(status):
                pages, got, calls = self._run(_tree(status))
                self.assertEqual((pages, calls), ([], []))
                self.assertEqual(got.status, status)

    def test_an_unreadable_tree_falls_back_to_links_inside_the_scope(self):
        _pages, got, calls = self._run(_tree(spt.STATUS_ERROR))
        self.assertNotIn("seeds", calls[0])
        self.assertEqual(calls[0]["site_scope"], "/sites/ExampleSite")
        self.assertEqual(got.status, spt.STATUS_ERROR)

    def test_links_mode_never_asks_for_a_tree(self):
        with mock.patch("crawler.crawl", return_value=[]) as fake:
            pages, tree = auditpass.sharepoint_pages(
                "https://example.test/", CrawlConfig(),
                discover=lambda *a, **k: self.fail("tree asked for"))
        self.assertEqual((pages, tree), ([], None))
        fake.assert_called_once()


class WhatTheTargetDecides(unittest.TestCase):
    def _args(self, **values):
        defaults = {"page_tree": None, "site_scope": None, "render": None,
                    "no_browser": False, "repo": None}
        defaults.update(values)
        return types.SimpleNamespace(**defaults)

    def test_a_sharepoint_site(self):
        run = auditpass.plan_sharepoint(f"{SITE}/SitePages/Home.aspx",
                                        self._args())
        self.assertTrue(run.sharepoint)
        self.assertEqual((run.page_tree, run.site_scope, run.render),
                         ("sharepoint", "/sites/ExampleSite", "always"))
        self.assertEqual(set(run.automatic),
                         {"page_tree", "site_scope", "render"})

    def test_a_flag_typed_by_hand_wins(self):
        run = auditpass.plan_sharepoint(SITE, self._args(
            page_tree="links", render="never", site_scope="/sites/Other"))
        self.assertEqual((run.page_tree, run.site_scope, run.render),
                         ("links", "/sites/Other", None))
        self.assertEqual(run.automatic, ())

    def test_no_browser_means_no_render_override(self):
        run = auditpass.plan_sharepoint(SITE, self._args(no_browser=True))
        self.assertIsNone(run.render)

    def test_an_ordinary_site_is_left_alone(self):
        run = auditpass.plan_sharepoint("https://example.com/", self._args())
        self.assertFalse(run.sharepoint)
        self.assertEqual((run.page_tree, run.site_scope, run.render,
                          run.automatic), ("links", "", None, ()))

    def test_explicit_tree_on_premises(self):
        run = auditpass.plan_sharepoint("https://intranet.example.test/",
                                        self._args(page_tree="sharepoint"))
        self.assertTrue(run.sharepoint)


class WhatTheRunSays(unittest.TestCase):
    def test_refusals_name_the_way_back_in(self):
        auth = auditpass.tree_refusal(_tree(spt.STATUS_AUTH), SITE)
        denied = auditpass.tree_refusal(_tree(spt.STATUS_ACCESS_DENIED), SITE)
        self.assertIn(f"xanalyze login {SITE}", auth)
        self.assertIn("expired", auth)
        self.assertIn("no permission", denied)
        self.assertEqual(auditpass.tree_refusal(_tree(spt.STATUS_OK, [SITE]),
                                                SITE), "")
        self.assertEqual(auditpass.tree_refusal(None, SITE), "")

    def test_the_summary_carries_what_was_left_out(self):
        tree = _tree(spt.STATUS_OK, [f"{SITE}/SitePages/Home.aspx"])
        tree.documents = [spt.TreeDocument(url=f"{SITE}/Shared%20Documents/a.pdf",
                                           title="a")]
        tree.skipped = [spt.SkippedUrl("x", spt.SKIP_OTHER_SITE),
                        spt.SkippedUrl("y", spt.SKIP_LIST_FORM)]
        walk = CrawlDiagnostics(pages_read=1, limit=30, queued_when_stopped=0)
        walk.out_of_scope = 4
        summary = auditpass.page_tree_summary(tree, walk, "/sites/ExampleSite",
                                              "sharepoint")
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["skipped"], {"other-site": 1, "list-form": 1})
        self.assertEqual(summary["documents"][0]["title"], "a")
        self.assertEqual(summary["out_of_scope"], 4)
        json.dumps(summary)

    def test_ootb_registry_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reg.json"
            path.write_text(json.dumps({
                "web_parts": [{"id": "00000000-0000-0000-0000-000000000001",
                               "name": "Quick links"}],
                "feature_tags": ["Some new part"]}), encoding="utf-8")
            registry, entries = auditpass.load_ootb_registry(str(path))
            self.assertEqual(entries, 2)
            self.assertEqual(
                registry.name_for_id("00000000-0000-0000-0000-000000000001"),
                "Quick links")
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with self.assertRaises(SystemExit):
                auditpass.load_ootb_registry(str(bad))
        self.assertEqual(auditpass.load_ootb_registry(""), (None, 0))


# -- browser pass ----------------------------------------------------------------


class TheBrowserPassReadsZones(unittest.TestCase):
    def test_options_are_confined_and_skipped_findings_are_counted(self):
        from audit import sharepoint_zones
        from audit.engine import AccessibilityResult, DocumentReport

        result = AccessibilityResult(root=SITE, mode="web")
        result.documents = [DocumentReport(source=f"{SITE}/SitePages/Home.aspx")]
        result.sharepoint = {"pages": 1, "skipped": {
            "elements": 3, "findings": 1, "by_rule": {"region": 1}}}
        seen = {}

        class _Audit:
            url = f"{SITE}/SitePages/Home.aspx"
            error = ""
            engine_errors = {}
            html = "<html></html>"
            issues = ["kept", "dropped"]

        def _fake(urls, options, sizes, on_page=None, markup=None, **_kw):
            seen["options"] = options
            return [_Audit()]

        def _classify(issues, markup, web_parts=(), registry=None,
                      summary=None):
            seen["classified"] = (list(issues), markup, registry)
            summary.skip_finding(types.SimpleNamespace(rule_id="axe:region"))
            return ["kept"]

        registry = sharepoint_zones.OotbRegistry()
        args = types.SimpleNamespace(within=None, _web_parts_found=[],
                                     _ootb_registry=registry, no_session=True,
                                     breakpoints=None)
        merged = []
        with mock.patch("audit.driver.available", return_value=(True, "")), \
                mock.patch.object(auditpass, "_audit_at_widths", _fake), \
                mock.patch.object(sharepoint_zones, "classify_browser_issues",
                                  _classify), \
                mock.patch("audit.browser.merge_page_audit",
                           side_effect=lambda r, d, a: merged.append(list(a.issues))), \
                mock.patch("audit.engine.attribute_ownership"):
            auditpass._run_browser_pass(result, mock.Mock(selectors=[], rules=[]),
                                        args)
        options = seen["options"]
        self.assertTrue(options.capture_html)
        self.assertFalse(options.run_htmlcs or options.run_states
                         or options.run_measurements)
        # Nothing included: SPFx markup moved out of the canvas has no selector.
        self.assertEqual(options.include, [])
        self.assertIn("#SuiteNavWrapper", options.exclude)
        self.assertIs(seen["classified"][2], registry)
        self.assertEqual(merged, [["kept"]])
        skipped = result.sharepoint["skipped"]
        self.assertEqual(skipped["findings"], 2)
        self.assertEqual(skipped["by_rule"], {"axe:region": 1, "region": 1})
        self.assertEqual(skipped["elements"], 3)

    def test_an_ordinary_site_is_not_confined(self):
        from audit.engine import AccessibilityResult, DocumentReport

        result = AccessibilityResult(root="https://x.test/", mode="web")
        result.documents = [DocumentReport(source="https://x.test/")]
        seen = {}

        class _Audit:
            url = "https://x.test/"
            error = ""
            engine_errors = {}
            issues = []

        def _fake(urls, options, sizes, on_page=None, markup=None, **_kw):
            seen["options"] = options
            return [_Audit()]

        with mock.patch("audit.driver.available", return_value=(True, "")), \
                mock.patch.object(auditpass, "_audit_at_widths", _fake), \
                mock.patch("audit.browser.merge_page_audit"), \
                mock.patch("audit.engine.attribute_ownership"):
            auditpass._run_browser_pass(result, mock.Mock(selectors=[], rules=[]))
        self.assertFalse(seen["options"].capture_html)
        self.assertEqual(result.sharepoint, {})


# -- the command ------------------------------------------------------------------


class TheCommand(unittest.TestCase):
    """`xanalyze audit` on a SharePoint Online address."""

    def _main(self, argv, *, session_host="", crawl_site=None):
        import contextlib
        import io

        import cli

        out, err = io.StringIO(), io.StringIO()

        def signed(target, config, use_session=True):
            # A placeholder value: what matters is that the fetcher got one.
            if session_host and use_session:
                config.cookies = [{"name": "placeholder", "value": "x"}]
                return session_host
            return ""

        patches = [mock.patch("cli_impl.auditpass.apply_session",
                              side_effect=signed),
                   mock.patch("cli.apply_session", side_effect=signed),
                   # The refusal asked before the run folder exists.
                   mock.patch("site_session.has_session",
                              return_value=bool(session_host))]
        if crawl_site is not None:
            patches.append(mock.patch.object(auditpass, "crawl_site",
                                             crawl_site))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_no_session_is_an_error_with_the_way_in(self):
        def never(*_a, **_k):
            raise AssertionError("crawled without a session")

        code, _out, err = self._main(
            ["audit", SITE, "--no-browser", "--json", "--no-hints"],
            crawl_site=never)
        self.assertEqual(code, 2)
        self.assertIn(f"xanalyze login {SITE}", err)
        self.assertIn("SharePoint Online", err)

    def test_an_expired_session_is_an_error_not_an_audit(self):
        tree = _tree(spt.STATUS_AUTH)
        code, out, err = self._main(
            ["audit", SITE, "--no-browser", "--json", "--no-hints"],
            session_host="contoso.sharepoint.com",
            crawl_site=lambda *a, **k: ([], tree))
        self.assertEqual(code, 2)
        self.assertIn("expired", err)
        self.assertIn(f"xanalyze login {SITE}", err)
        self.assertEqual(out.strip(), "")

    def test_access_denied_is_its_own_sentence(self):
        tree = _tree(spt.STATUS_ACCESS_DENIED)
        code, _out, err = self._main(
            ["audit", SITE, "--no-browser", "--json", "--no-hints"],
            session_host="contoso.sharepoint.com",
            crawl_site=lambda *a, **k: ([], tree))
        self.assertEqual(code, 2)
        self.assertIn("no permission", err)

    def test_a_tree_run_reports_its_page_list_and_zones(self):
        url = f"{SITE}/SitePages/Home.aspx"
        tree = _tree(spt.STATUS_OK, [url])
        tree.skipped = [spt.SkippedUrl("x", spt.SKIP_OTHER_SITE)]
        page = PageResult(url=url, depth=0,
                          raw_html=FIXTURE.read_text(encoding="utf-8"),
                          diagnostics=PageDiagnostics(status_code=200))
        got = {}

        def fake_crawl_site(target, config, **kwargs):
            got.update(kwargs, render=config.render_mode)
            kwargs["walk"].pages_read = 1
            return [page], tree

        code, out, _err = self._main(
            ["audit", SITE, "--no-browser", "--json", "--no-hints"],
            session_host="contoso.sharepoint.com",
            crawl_site=fake_crawl_site)
        self.assertEqual(code, 0)
        self.assertEqual((got["page_tree"], got["site_scope"]),
                         ("sharepoint", "/sites/ExampleSite"))
        data = json.loads(out)
        self.assertEqual(data["page_tree"]["status"], "ok")
        self.assertEqual(data["page_tree"]["skipped"], {"other-site": 1})
        self.assertEqual(data["page_tree"]["pages_read"], 1)
        self.assertEqual(data["sharepoint"]["pages"], 1)
        self.assertIn("skipped", data["sharepoint"])

    def test_render_always_unless_typed(self):
        tree = _tree(spt.STATUS_OK, [SITE])
        seen = {}

        def fake(target, config, **kwargs):
            seen["render"] = config.render_mode
            return [], tree

        self._main(["audit", SITE, "--json", "--no-hints"],
                   session_host="contoso.sharepoint.com", crawl_site=fake)
        self.assertEqual(seen["render"], "always")
        self._main(["audit", SITE, "--json", "--no-hints", "--render", "auto"],
                   session_host="contoso.sharepoint.com", crawl_site=fake)
        self.assertEqual(seen["render"], "auto")


if __name__ == "__main__":
    unittest.main()
