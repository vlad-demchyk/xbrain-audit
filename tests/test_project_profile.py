"""What a directory is, on evidence, and what that lets a scan skip.

Every exclusion this tool had was added after a false-positive class turned
up in a real audit - the last one, `wp-admin/`, after 455 findings arrived
from vendored WordPress core. `project_profile` is the attempt to stop
learning that per stack.

Two failure directions, and both are cheap to get wrong:

* **detecting nothing** leaves the scan exactly as it was, which is safe.
* **detecting the wrong stack** applies somebody else's exclusions, and an
  exclusion hides source. That one is silent: the report simply comes back
  shorter. `xformat-backend` was identified as a Hugo site by its
  `supabase/config.toml`, which would have excluded its `public/` directory.

So the tests below spend more effort on what must *not* be detected than on
what must.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import project_profile


def _tree(root: Path, files: dict) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class _Built(unittest.TestCase):
    def profile(self, files: dict):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        _tree(root, files)
        return project_profile.detect(root)

    def names(self, files: dict) -> set:
        return {stack.name for stack in self.profile(files).stacks}


class MarkersIdentifyAStack(_Built):
    def test_each_stack_is_found_by_its_own_marker(self):
        cases = {
            "wordpress": {"wp-config.php": "<?php"},
            "laravel": {"artisan": "#!/usr/bin/env php"},
            "django": {"manage.py": "import django"},
            "rails": {"bin/rails": "#!/usr/bin/env ruby"},
            "nextjs": {"next.config.mjs": "export default {}"},
            "nuxt": {"nuxt.config.ts": "export default {}"},
            "astro": {"astro.config.mjs": "export default {}"},
            "sveltekit": {"svelte.config.js": "export default {}"},
            "angular": {"angular.json": "{}"},
            "spfx": {"config/package-solution.json": "{}"},
            "vite": {"vite.config.ts": "export default {}"},
        }
        for expected, files in cases.items():
            with self.subTest(stack=expected):
                self.assertIn(expected, self.names(files))

    def test_a_dependency_identifies_a_stack_with_no_config_file(self):
        found = self.names({"package.json": json.dumps(
            {"dependencies": {"next": "15.0.0"}})})
        self.assertIn("nextjs", found)

    def test_evidence_names_the_file_that_proved_it(self):
        profile = self.profile({"web/wp-config.php": "<?php"})
        self.assertEqual(profile.evidence["wordpress"], "web/wp-config.php")

    def test_a_monorepo_marker_is_found_below_the_root(self):
        """Every real project on this machine but one was invisible at depth 0."""
        found = self.names({"apps/admin/vite.config.ts": "export default {}"})
        self.assertIn("vite", found)

    def test_a_marker_too_deep_is_not_this_project(self):
        found = self.names({"a/b/c/d/artisan": "#!/usr/bin/env php"})
        self.assertNotIn("laravel", found)


class AGenericNameIsNotEvidence(_Built):
    """The failure that hides source, tested harder than the one that does not."""

    def test_a_supabase_config_is_not_a_hugo_site(self):
        """The real case: `xformat-backend/supabase/config.toml`.

        Hugo's exclusion is `public/`, which in a Node backend is source.
        """
        found = self.names({"supabase/config.toml": "[db]\nport = 54322\n"})
        self.assertNotIn("hugo", found)

    def test_hugo_needs_its_own_layout_beside_the_config(self):
        found = self.names({"config.toml": "baseURL = '/'",
                            "layouts/index.html": "<html></html>"})
        self.assertIn("hugo", found)

    def test_a_bare_config_yml_is_not_a_jekyll_site(self):
        found = self.names({"_config.yml": "key: value"})
        self.assertNotIn("jekyll", found)

    def test_jekyll_needs_posts_or_layouts(self):
        found = self.names({"_config.yml": "title: x",
                            "_posts/2020-01-01-x.md": "# x"})
        self.assertIn("jekyll", found)

    def test_a_bare_configuration_php_is_not_joomla(self):
        found = self.names({"configuration.php": "<?php $config = [];"})
        self.assertNotIn("joomla", found)

    def test_a_vendored_config_does_not_speak_for_the_project(self):
        """A marker inside `node_modules/` describes a dependency."""
        found = self.names({"node_modules/pkg/next.config.js": "module.exports = {}"})
        self.assertNotIn("nextjs", found)

    def test_a_fixture_directory_does_not_speak_for_the_project(self):
        found = self.names({"fixtures/site/artisan": "#!/usr/bin/env php"})
        self.assertNotIn("laravel", found)


class ExclusionsFollowFromTheStack(_Built):
    def test_wordpress_excludes_core_but_not_the_theme(self):
        from repo_scanner import build_matcher, is_ignored

        profile = self.profile({"web/wp-config.php": "<?php"})
        matcher = build_matcher(profile.excludes())
        self.assertTrue(is_ignored("web/wp-includes/x.php", matcher))
        self.assertTrue(is_ignored("web/wp-admin/x.php", matcher))
        self.assertFalse(is_ignored("web/wp-content/themes/mine/header.php", matcher))

    def test_bedrock_is_wordpress_installed_somewhere_else(self):
        """`web/wp/` is core and `web/app/` is the content directory, so
        every exclusion that knows WordPress by `wp-content/` misses all of
        it. Measured on a client's Bedrock repository: 106 of 129
        findings were about code the project does not write."""
        from repo_scanner import build_matcher, is_ignored

        profile = self.profile({"web/wp-config.php": "<?php",
                                "config/application.php": "<?php"})
        self.assertIn("bedrock", {stack.name for stack in profile.stacks})
        matcher = build_matcher(profile.excludes())
        for hidden in ("web/wp/xmlrpc.php", "web/app/plugins/acf/acf.php",
                       "web/app/languages/it_IT.l10n.php",
                       "web/app/cache/acorn/x.php",
                       "web/app/themes/twentytwentyfour/index.php"):
            self.assertTrue(is_ignored(hidden, matcher), hidden)
        self.assertFalse(is_ignored(
            "web/app/themes/mine/resources/views/page.blade.php", matcher))

    def test_a_config_directory_alone_is_not_bedrock(self):
        """`config/application.php` is a name half the PHP world could use.
        Detecting the wrong stack hides source, so both halves are required."""
        self.assertNotIn("bedrock", self.names({"config/application.php": "<?php"}))

    def test_an_undetected_project_excludes_nothing_extra(self):
        profile = self.profile({"README.md": "# hello"})
        self.assertEqual(profile.excludes(), [])
        self.assertEqual(profile.describe(), "")

    def test_every_stack_says_why(self):
        """A reason a person cannot argue with is one they cannot correct."""
        for stack in project_profile.STACKS:
            with self.subTest(stack=stack.name):
                self.assertTrue(stack.why, f"{stack.name} has no reason")

    def test_a_checkout_stack_excludes_something(self):
        """That is what detecting it is *for*. A hosted platform is the
        exception: there is no checkout, so there is nothing to exclude - what
        it gives is the knowledge that the shell is somebody else's."""
        for stack in project_profile.STACKS:
            if stack.hosted:
                continue
            with self.subTest(stack=stack.name):
                self.assertTrue(stack.excludes, f"{stack.name} excludes nothing")

    def test_a_hosted_platform_has_no_markers_to_find_on_disk(self):
        for stack in project_profile.STACKS:
            if not stack.hosted:
                continue
            with self.subTest(stack=stack.name):
                self.assertEqual(stack.markers, ())
                self.assertEqual(stack.excludes, ())

    def test_no_stack_excludes_a_bare_source_directory(self):
        """`repo_scanner` records that guessing at `lib/` blinded the scanner
        to 67 real findings. `lib/` appears once, for SPFx, where it is the
        compiler's output directory - and nowhere else."""
        risky = {"src/", "app/", "components/", "lib/", "assets/"}
        for stack in project_profile.STACKS:
            for pattern in stack.excludes:
                if pattern in risky:
                    with self.subTest(stack=stack.name, pattern=pattern):
                        self.assertEqual(stack.name, "spfx")


class GeneratedFilesAreNotSomebodysWork(unittest.TestCase):
    """A finding in a generated file is unactionable, not wrong.

    The fix belongs in the generator and the file is overwritten on the next
    build, so reporting it spends a reader's attention on something they
    cannot change.
    """

    def test_the_common_markers_are_recognised(self):
        for header in ("// Code generated by protoc-gen-go. DO NOT EDIT.",
                       "/* eslint-disable */\n// @generated by GraphQL codegen",
                       "<!-- This file is auto-generated. Do not modify. -->",
                       "# Automatically generated by openapi-generator"):
            with self.subTest(header=header[:30]):
                self.assertTrue(project_profile.looks_generated(header + "\n<img>"))

    def test_ordinary_source_is_not_caught(self):
        self.assertFalse(project_profile.looks_generated(
            "export function Panel() { return <div/>; }"))

    def test_prose_about_generated_code_further_down_is_not_caught(self):
        """The marker is a header convention; a README is not a header."""
        body = "# Contributing\n" + ("x " * 400) + "\nThis file is auto-generated.\n"
        self.assertFalse(project_profile.looks_generated(body))


class ServedMarkupSaysWhatBuiltIt(_Built):
    """A crawled site had no stack detection at all.

    `detect()` reads marker files and a URL has none, so a site scan knew
    nothing about what it was reading while the same project on disk knew
    everything. Measured on `phpstack-1451965-6319681.cloudwaysapps.com`:
    `<meta name="generator" content="WordPress 7.1">` was sitting in the
    markup the whole time.
    """

    def _names(self, markup: str) -> set:
        return {s.name for s in project_profile.detect_from_markup(markup).stacks}

    def test_a_generator_meta_is_evidence(self):
        cases = {
            "wordpress": '<meta name="generator" content="WordPress 7.1" />',
            "drupal": '<meta name="generator" content="Drupal 10 (https://www.drupal.org)">',
            "hugo": '<meta name="generator" content="Hugo 0.128.0">',
            "ghost": '<meta name="generator" content="Ghost 5.0">',
            "astro": '<meta name="generator" content="Astro v4.5">',
        }
        for expected, markup in cases.items():
            with self.subTest(platform=expected):
                self.assertIn(expected, self._names(markup))

    def test_an_asset_host_is_evidence(self):
        cases = {
            "shopify": '<script src="https://cdn.shopify.com/s/f.js"></script>',
            "wix": '<link href="https://static.parastorage.com/x.css">',
            "squarespace": '<script src="https://assets.squarespace.com/x.js"></script>',
            "webflow": '<html data-wf-site="abc123">',
            "beehiiv": '<img src="https://cdn.beehiiv.com/a.png">',
            "carrd": '<link href="https://cdn.carrd.co/assets/x.css">',
        }
        for expected, markup in cases.items():
            with self.subTest(platform=expected):
                self.assertIn(expected, self._names(markup))

    def test_a_runtime_payload_is_evidence(self):
        cases = {
            "nextjs": '<script id="__NEXT_DATA__" type="application/json">{}</script>',
            "nuxt": '<script>window.__NUXT__ = {}</script>',
            "angular": '<app-root ng-version="17.0.1"></app-root>',
            "sveltekit": '<link href="/_app/immutable/entry/start.js">',
        }
        for expected, markup in cases.items():
            with self.subTest(platform=expected):
                self.assertIn(expected, self._names(markup))

    def test_a_hand_built_page_is_undetected(self):
        """Which is what almost every page is, and what the scan handles."""
        markup = ('<!DOCTYPE html><html lang="en"><head><title>x</title></head>'
                  '<body><main><h1>Hello</h1></main></body></html>')
        self.assertEqual(self._names(markup), set())

    def test_the_word_wordpress_in_prose_is_not_evidence(self):
        """A signature is a literal the platform emits, not a mention of it."""
        markup = "<p>We migrated off WordPress last year and never looked back.</p>"
        self.assertEqual(self._names(markup), set())

    def test_two_true_answers_are_both_kept(self):
        """A WordPress site behind Shopify's CDN is two facts, not a contest."""
        markup = ('<meta name="generator" content="WordPress 6.5">'
                  '<script src="https://cdn.shopify.com/s/f.js"></script>')
        self.assertEqual(self._names(markup), {"wordpress", "shopify"})

    def test_the_evidence_names_what_it_saw(self):
        profile = project_profile.detect_from_markup(
            '<meta name="generator" content="WordPress 7.1">')
        self.assertIn("generator meta", profile.evidence["wordpress"])

    def test_the_version_is_read_out_of_the_markup(self):
        """"WordPress" is a guess someone has to verify; "WordPress 7.1" is a
        fact they can act on."""
        cases = {
            "wordpress": ('<meta name="generator" content="WordPress 7.1">', "7.1"),
            "hugo": ('<meta name=generator content="Hugo 0.165.0">', "0.165.0"),
            "angular": ('<app-root ng-version="22.1.4"></app-root>', "22.1.4"),
            "jekyll": ('<meta name="generator" content="Jekyll v4.4.1">', "4.4.1"),
        }
        for stack, (markup, version) in cases.items():
            with self.subTest(stack=stack):
                profile = project_profile.detect_from_markup(markup)
                self.assertEqual(profile.versions.get(stack), version)

    def test_an_unquoted_attribute_is_still_a_generator_meta(self):
        """HTML has always allowed it, and `gohugo.io` - the Hugo project's
        own site - writes `<meta name=generator content="Hugo 0.165.0">`.
        Requiring quotes made a whole class of pages invisible."""
        found = self._names('<meta name=generator content="Hugo 0.165.0">')
        self.assertIn("hugo", found)

    def test_a_weak_signature_alone_names_nothing(self):
        """Below 100 means "this could be here for another reason". The
        literal `SPFx` appears in prose about SharePoint as often as in a page
        built with it."""
        self.assertEqual(self._names("<p>We build with SPFx these days.</p>"), set())

    def test_two_weak_signatures_add_up(self):
        markup = '<p>SPFx</p><script src="/ClientSideAssets/x.js"></script>'
        self.assertIn("spfx", self._names(markup))

    def test_one_strong_signature_is_enough_on_its_own(self):
        self.assertIn("spfx", self._names("<script>_spPageContextInfo={}</script>"))


class SharePointIsThePlatform(unittest.TestCase):
    """SharePoint the platform, apart from SPFx the web parts on it."""

    def test_the_online_host_is_sharepoint_before_any_markup(self):
        profile = project_profile.detect_from_url(
            "https://contoso.sharepoint.com/sites/ExampleSite")
        self.assertEqual([s.name for s in profile.stacks], ["sharepoint"])
        self.assertTrue(profile.stacks[0].hosted)
        self.assertIn("contoso.sharepoint.com", profile.evidence["sharepoint"])

    def test_tenant_hosts(self):
        for host in ("contoso.sharepoint.com", "contoso-my.sharepoint.com",
                     "contoso-admin.sharepoint.com",
                     "https://CONTOSO.sharepoint.com/sites/x"):
            with self.subTest(host=host):
                self.assertEqual(project_profile.sharepoint_tenant(host),
                                 "contoso")
        for host in ("sharepoint.com", "example.com", "a.b.sharepoint.com",
                     "contoso.sharepoint.com.evil.test"):
            with self.subTest(host=host):
                self.assertEqual(project_profile.sharepoint_tenant(host), "")
        self.assertEqual(
            project_profile.sharepoint_tenant_hosts("contoso.sharepoint.com"),
            ("contoso.sharepoint.com", "contoso-my.sharepoint.com"))

    def test_site_path(self):
        cases = {
            "https://contoso.sharepoint.com/sites/ExampleSite/SitePages/a.aspx":
                "/sites/ExampleSite",
            "https://contoso.sharepoint.com/teams/T": "/teams/T",
            "https://contoso.sharepoint.com/": "/",
            "https://contoso.sharepoint.com/SitePages/Home.aspx": "/",
        }
        for url, path in cases.items():
            with self.subTest(url=url):
                self.assertEqual(project_profile.sharepoint_site_path(url), path)

    def test_on_premises_is_recognised_by_its_page_context(self):
        for markup in ("<script>var _spPageContextInfo={};</script>",
                       "<script>window.spClientSidePageContext={}</script>"):
            with self.subTest(markup=markup):
                names = [s.name for s in
                         project_profile.detect_from_markup(markup).stacks]
                self.assertIn("sharepoint", names)

    def test_layouts_alone_is_not_enough(self):
        names = [s.name for s in project_profile.detect_from_markup(
            '<link href="/_layouts/15/a.css">').stacks]
        self.assertNotIn("sharepoint", names)

    def test_microsofts_chrome_is_owned_by_sharepoint_not_spfx(self):
        markup = "<script>_spPageContextInfo={}</script>"
        names = [s.name for s in
                 project_profile.detect_from_markup(markup).stacks]
        self.assertEqual(names[0], "sharepoint")
        for snippet in ('<link href="/_layouts/15/odsp-next/suite.css">',
                        '<script src="https://res-1.cdn.office.net/files/'
                        'sp-client/sp-pages-assembly.js"></script>'):
            with self.subTest(snippet=snippet):
                self.assertEqual(
                    project_profile.platform_owner(names, snippet),
                    "sharepoint")
        # The tenant's own SPFx bundle is the author's.
        self.assertEqual(project_profile.platform_owner(
            names, '<script src="/sites/x/ClientSideAssets/part.js">'), "")
        self.assertEqual(project_profile.platform_owner(
            names, '<script src="https://publiccdn.sharepointonline.com/'
                   'contoso.sharepoint.com/x.js">'), "")


if __name__ == "__main__":
    unittest.main()
