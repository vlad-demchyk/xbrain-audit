"""A local site's server is not the project's defect.

On `http://town.local` a crawl reported 365 critical findings that were all
`http://` form actions, and four missing security headers on 381 pages. Nothing
in the code could fix them. They are left out of the list on a local address,
counted and named, and `--include-environment` brings them back; everything
about the page itself is untouched.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

import audit
from audit import environment
from audit.base import SERIOUS, Issue
from audit.engine import AccessibilityResult, DocumentReport


def issue(rule: str, source: str, severity: str = SERIOUS) -> Issue:
    return Issue(rule_id=rule, severity=severity, category="security",
                 source=source, snippet=f"<x {rule}>")


class WhatCountsAsLocal(unittest.TestCase):
    def test_development_names_and_addresses_are_local(self):
        for url in ("http://localhost:8080/", "http://town.local/", "http://app.test/",
                    "http://shop/", "http://127.0.0.1/", "http://192.168.1.20/",
                    "http://10.0.0.5:3000/", "http://[::1]/", "http://x.localhost/",
                    "http://dev.internal/"):
            with self.subTest(url=url):
                self.assertTrue(environment.is_local_url(url))

    def test_public_names_are_never_local(self):
        for url in ("https://www.visit-example.it/", "https://example.com/",
                    "https://8.8.8.8/", "https://localhost.example.com/",
                    "https://a.b.co.uk/"):
            with self.subTest(url=url):
                self.assertFalse(environment.is_local_url(url))

    def test_an_empty_or_malformed_address_is_not_local(self):
        for url in ("", "not a url", None):
            self.assertFalse(environment.is_local_url(url or ""))


def result_of(*pairs) -> AccessibilityResult:
    documents = [DocumentReport(source=source, issues=list(issues), elements_checked=1)
                 for source, issues in pairs]
    return AccessibilityResult(root=pairs[0][0], mode="web", documents=documents)


class TheServerIsLeftOutAndCounted(unittest.TestCase):
    LOCAL = "http://town.local/"

    def setUp(self):
        self.result = result_of(
            (self.LOCAL, [issue("sec-no-csp", self.LOCAL),
                          issue("sec-form-insecure-action", self.LOCAL),
                          issue("seo-noindex", self.LOCAL),
                          issue("image-alt", self.LOCAL),
                          issue("perf-third-party-sync", self.LOCAL)]),
            ("http://town.local/b", [issue("sec-no-nosniff", "http://town.local/b")]),
        )

    def test_environment_findings_are_removed_and_the_rest_stay(self):
        summary = environment.apply(self.result)
        self.assertEqual([i.rule_id for i in self.result.documents[0].issues],
                         ["image-alt", "perf-third-party-sync"])
        self.assertEqual(self.result.documents[1].issues, [])
        self.assertEqual(summary["hidden"], 4)

    def test_it_says_what_it_left_out(self):
        summary = environment.apply(self.result)
        self.assertEqual(summary["by_rule"], {"sec-form-insecure-action": 1, "sec-no-csp": 1,
                                              "sec-no-nosniff": 1, "seo-noindex": 1})
        self.assertEqual(summary["hosts"], ["town.local"])
        self.assertTrue(summary["local"])
        self.assertIs(self.result.environment, summary)

    def test_including_the_environment_keeps_everything_and_still_counts(self):
        summary = environment.apply(self.result, include=True)
        self.assertEqual(len(self.result.issues()), 6)
        self.assertEqual(summary["hidden"], 0)
        self.assertEqual(summary["would_hide"], 4)
        self.assertTrue(summary["included"])

    def test_a_script_loaded_synchronously_is_a_defect_on_a_local_site_too(self):
        self.assertNotIn("perf-third-party-sync", environment.LOCAL_ONLY_RULES)
        self.assertNotIn("sec-script-integrity", environment.LOCAL_ONLY_RULES)

    def test_a_public_site_loses_nothing(self):
        public = "https://www.visit-example.it/"
        result = result_of((public, [issue("sec-no-csp", public),
                                     issue("sec-form-insecure-action", public)]))
        summary = environment.apply(result)
        self.assertEqual(len(result.issues()), 2)
        self.assertEqual(summary["hidden"], 0)
        self.assertFalse(summary["local"])

    def test_only_the_local_half_of_a_mixed_run_is_hidden(self):
        local, public = "http://town.local/", "https://www.visit-example.it/"
        result = result_of((local, [issue("sec-no-csp", local)]),
                           (public, [issue("sec-no-csp", public)]))
        environment.apply(result)
        self.assertEqual([i.source for i in result.issues()], [public])


class ItReachesTheWebAudit(unittest.TestCase):
    PAGE = ("<!doctype html><html lang='it'><head><title>t pagina</title></head>"
            "<body><main><h1>x</h1><form action='http://town.local/s' method='get'>"
            "<input name='q' aria-label='cerca'></form></main></body></html>")

    def pages(self, url):
        return [SimpleNamespace(url=url, raw_html=self.PAGE, error=None, diagnostics=None,
                                status=200, headers={})]

    def test_a_local_http_form_is_not_listed_by_default(self):
        result = audit.analyze_pages(self.pages("http://town.local/"),
                                     "http://town.local/", media=False)
        self.assertNotIn("sec-form-insecure-action", [i.rule_id for i in result.issues()])
        self.assertGreaterEqual(result.environment["would_hide"], 1)

    def test_asking_for_it_lists_it(self):
        result = audit.analyze_pages(self.pages("http://town.local/"),
                                     "http://town.local/", media=False,
                                     include_environment=True)
        self.assertIn("sec-form-insecure-action", [i.rule_id for i in result.issues()])

    def test_the_same_form_on_a_public_address_is_listed(self):
        public = "http://www.visit-example.it/"
        result = audit.analyze_pages(self.pages(public), public, media=False)
        self.assertIn("sec-form-insecure-action", [i.rule_id for i in result.issues()])

    def test_the_command_offers_the_flag_that_brings_it_back(self):
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        self.assertIn("--include-environment",
                      subprocess.run([sys.executable, str(root / "cli.py"), "audit", "--help"],
                                     capture_output=True, text=True, encoding="utf-8", cwd=str(root)).stdout)


if __name__ == "__main__":
    unittest.main()
