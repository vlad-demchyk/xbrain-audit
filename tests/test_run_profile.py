"""What a target implies about how to read it.

`project_profile` is tested for what it must *not* detect, because a wrong
stack hides source. This module has the mirror risk: a wrong suggestion
changes what the run does. Two directions, and both are silent.

* **Suggesting nothing** leaves the run exactly as it was, which is safe.
* **Suggesting the wrong thing** - or, worse, overwriting a choice somebody
  made on purpose - changes the answer without telling anyone. Half the
  tests below are about that second one: that `_explicit` wins, that a
  hidden control never reaches a run, and that every suggestion carries the
  marker file that justified it.
"""
from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

import project_profile
import run_profile


def _tree(root: Path, files: dict) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class _Built(unittest.TestCase):
    def build(self, files: dict) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        _tree(root, files)
        return root


class TargetKind(_Built):
    def test_scheme_is_a_site(self):
        self.assertEqual(run_profile.target_kind("https://example.com"),
                         run_profile.KIND_SITE)

    def test_bare_host_is_a_site(self):
        self.assertEqual(run_profile.target_kind("example.com"),
                         run_profile.KIND_SITE)

    def test_folder_is_a_repo(self):
        root = self.build({"index.html": "<html></html>"})
        self.assertEqual(run_profile.target_kind(str(root)),
                         run_profile.KIND_REPO)

    def test_page_file_is_a_file(self):
        root = self.build({"page.html": "<html></html>"})
        self.assertEqual(run_profile.target_kind(str(root / "page.html")),
                         run_profile.KIND_FILE)

    def test_url_flag_wins_over_a_path_that_exists(self):
        """`--url` is how a person says "I meant the address"."""
        root = self.build({"example.com": "not a site"})
        self.assertEqual(
            run_profile.target_kind(str(root / "example.com"), forced_url=True),
            run_profile.KIND_SITE)

    def test_a_typo_shows_every_field(self):
        """Neither a host nor a path: nothing may be hidden from a half-typed
        target, because the person is still answering the question."""
        kind = run_profile.target_kind("/no/such/place")
        self.assertEqual(kind, run_profile.KIND_REPO)


class FieldsReachSomething(unittest.TestCase):
    def test_crawl_depth_is_for_sites(self):
        self.assertTrue(run_profile.applies("depth", run_profile.KIND_SITE))
        self.assertFalse(run_profile.applies("depth", run_profile.KIND_REPO))
        self.assertFalse(run_profile.applies("depth", run_profile.KIND_FILE))

    def test_incremental_is_for_folders(self):
        self.assertTrue(run_profile.applies("incremental",
                                            run_profile.KIND_REPO))
        self.assertFalse(run_profile.applies("incremental",
                                             run_profile.KIND_SITE))

    def test_widths_reach_all_three(self):
        for kind in run_profile.KINDS:
            self.assertTrue(run_profile.applies("breakpoints", kind))

    def test_an_unknown_option_is_shown_not_hidden(self):
        """A flag nobody remembered to list must appear everywhere rather
        than disappear from every surface."""
        for kind in run_profile.KINDS:
            self.assertTrue(run_profile.applies("brand-new-flag", kind))


class WhatAStackAsksFor(_Built):
    def test_a_vite_app_asks_for_its_dev_server(self):
        root = self.build({"vite.config.ts": "export default {}",
                           "package.json": '{"dependencies":{"vite":"5"}}'})
        plan = run_profile.build(str(root))
        item = plan.suggestion("devserver")
        self.assertIsNotNone(item)
        self.assertIs(item.value, True)
        self.assertEqual(item.stack, "vite")

    def test_every_suggestion_names_the_file_that_proved_it(self):
        """A wrong answer has to be arguable, and it is only arguable if the
        marker file that produced it is in reach."""
        root = self.build({"next.config.js": "module.exports = {}"})
        plan = run_profile.build(str(root))
        item = plan.suggestion("devserver")
        self.assertIn("next.config.js", item.evidence)

    def test_a_plain_folder_asks_for_nothing(self):
        root = self.build({"index.html": "<html></html>"})
        self.assertEqual(run_profile.build(str(root)).suggestions, ())

    def test_web_parts_needs_both_the_site_and_the_checkout(self):
        """`--web-parts` reads manifests out of a checkout and confines a
        *page*. One half of the pair is not a run it can be suggested for."""
        root = self.build({"config/package-solution.json": "{}"})
        folder_only = run_profile.build(str(root))
        self.assertIsNone(folder_only.suggestion("web_parts"))
        paired = run_profile.build("https://contoso.sharepoint.com/sites/x",
                                   repo=str(root))
        self.assertIsNotNone(paired.suggestion("web_parts"))

    def test_an_spfx_checkout_asks_where_it_ships(self):
        root = self.build({"config/package-solution.json": "{}"})
        plan = run_profile.build(str(root))
        self.assertTrue(plan.asks_for("site_url"))

    def test_a_single_file_is_read_at_every_width(self):
        root = self.build({"page.html": "<html></html>"})
        plan = run_profile.build(str(root / "page.html"))
        self.assertEqual(plan.suggestion("breakpoints").value, "all")


class ApplyingIsNeverSilent(_Built):
    def test_a_choice_made_by_hand_is_not_overwritten(self):
        root = self.build({"vite.config.ts": "export default {}"})
        plan = run_profile.build(str(root))
        args = argparse.Namespace(devserver=False)
        applied = plan.apply(args, touched={"devserver"})
        self.assertEqual(applied, [])
        self.assertFalse(args.devserver)

    def test_what_is_applied_is_returned(self):
        root = self.build({"vite.config.ts": "export default {}"})
        plan = run_profile.build(str(root))
        args = argparse.Namespace(devserver=False)
        applied = plan.apply(args)
        self.assertTrue(args.devserver)
        self.assertEqual([item.option for item in applied], ["devserver"])

    def test_a_value_that_already_agrees_is_not_reported(self):
        """"Enabled, because …" about a value nobody changed is a lie."""
        root = self.build({"vite.config.ts": "export default {}"})
        plan = run_profile.build(str(root))
        args = argparse.Namespace(devserver=True)
        self.assertEqual(plan.apply(args), [])

    def test_the_sentence_names_the_stack_and_the_evidence(self):
        root = self.build({"vite.config.ts": "export default {}"})
        plan = run_profile.build(str(root))
        sentence = run_profile.explain(plan.suggestion("devserver"), "en")
        self.assertIn("vite", sentence)
        self.assertIn("vite.config.ts", sentence)

    def test_the_sentence_exists_in_every_interface_language(self):
        root = self.build({"page.html": "<html></html>"})
        plan = run_profile.build(str(root / "page.html"))
        item = plan.suggestion("breakpoints")
        seen = {lang: run_profile.explain(item, lang)
                for lang in ("en", "uk", "it")}
        self.assertEqual(len(set(seen.values())), 3)
        for sentence in seen.values():
            self.assertTrue(sentence.strip())


class SeveralProjectsInOneFolder(_Built):
    def test_a_container_of_solutions_is_several_projects(self):
        root = self.build({
            "one/config/package-solution.json": "{}",
            "two/config/package-solution.json": "{}",
        })
        found = project_profile.projects(root)
        self.assertEqual(sorted(Path(p.root).name for p in found),
                         ["one", "two"])
        self.assertTrue(run_profile.build(str(root)).ambiguous())

    def test_a_project_of_its_own_is_one_project(self):
        """A repository that proved something itself **is** the project;
        what is under it is its parts, not four more deliverables."""
        root = self.build({
            "config/package-solution.json": "{}",
            "src/webparts/one/One.ts": "",
        })
        found = project_profile.projects(root)
        self.assertEqual([Path(p.root).name for p in found],
                         [Path(root).name])
        self.assertFalse(run_profile.build(str(root)).ambiguous())

    def test_vendored_core_is_not_a_project_to_audit(self):
        """Bedrock keeps WordPress in `web/wp/`, which its own exclusions
        already skip. A directory the run will not read is not a project the
        run can be pointed at."""
        root = self.build({
            "config/application.php": "<?php",
            "web/wp-config.php": "<?php",
            "web/wp/wp-load.php": "<?php",
        })
        found = project_profile.projects(root)
        self.assertNotIn("wp", [Path(p.root).name for p in found])

    def test_a_folder_that_is_nothing_has_no_projects(self):
        root = self.build({"notes.txt": "hello"})
        self.assertEqual(project_profile.projects(root), [])


if __name__ == "__main__":
    unittest.main()


class OneProjectOutOfSeveral(_Built):
    def test_a_project_is_named_by_its_folder_or_by_a_path(self):
        root = self.build({
            "apps/web/vite.config.ts": "export default {}",
            "apps/admin/vite.config.ts": "export default {}",
        })
        plan = run_profile.build(str(root))
        self.assertEqual(sorted(plan.choices()), ["admin", "web"])
        for spelling in ("web", "apps/web", str(root / "apps" / "web")):
            with self.subTest(spelling=spelling):
                self.assertEqual(run_profile.choose_project(plan, spelling),
                                 str(root / "apps" / "web"))

    def test_a_name_nothing_matches_is_refused(self):
        """Silently auditing the whole folder is the behaviour `--project`
        exists to replace, and it would look exactly like success."""
        root = self.build({"apps/web/vite.config.ts": "export default {}",
                           "apps/admin/vite.config.ts": "export default {}"})
        plan = run_profile.build(str(root))
        self.assertEqual(run_profile.choose_project(plan, "nope"), "")

    def test_choosing_is_only_offered_where_there_is_a_choice(self):
        root = self.build({"vite.config.ts": "export default {}"})
        plan = run_profile.build(str(root))
        self.assertFalse(plan.ambiguous())
        self.assertEqual(plan.choices(), [Path(root).name])


class WhichDevServerAMonorepoMeans(_Built):
    def _monorepo(self) -> Path:
        return self.build({
            "package.json": '{"workspaces":["apps/*"],'
                            '"scripts":{"dev":"turbo dev"}}',
            "apps/web/package.json": '{"scripts":{"dev":"vite"}}',
            "apps/web/vite.config.ts": "export default {}",
            "apps/admin/package.json": '{"scripts":{"dev":"vite"}}',
            "apps/admin/vite.config.ts": "export default {}",
        })

    def test_the_root_and_each_application_are_different_servers(self):
        plan = run_profile.build(str(self._monorepo()))
        roots = {Path(server.root).name for server in plan.servers}
        self.assertIn("web", roots)
        self.assertIn("admin", roots)
        self.assertIsNotNone(plan.shared_server())
        self.assertEqual(len(plan.project_servers()), 2)

    def test_the_reason_says_which_one_would_start(self):
        """`--devserver` was deciding this silently, and a root's `dev`
        script is not the application's."""
        plan = run_profile.build(str(self._monorepo()))
        sentence = run_profile.explain(plan.suggestion("devserver"), "en")
        self.assertIn("monorepo root", sentence)

    def test_an_ordinary_project_says_the_ordinary_thing(self):
        root = self.build({"package.json": '{"scripts":{"dev":"vite"}}',
                           "vite.config.ts": "export default {}"})
        plan = run_profile.build(str(root))
        self.assertIsNone(plan.shared_server())
        self.assertNotIn("monorepo",
                         run_profile.explain(plan.suggestion("devserver"), "en"))

    def test_a_folder_that_serves_nothing_lists_no_servers(self):
        root = self.build({"index.html": "<html></html>"})
        self.assertEqual(run_profile.build(str(root)).servers, [])


class ADevServerIsFoundWhereItLives(_Built):
    def test_a_workspace_root_is_read_from_its_own_manifest(self):
        import devserver

        root = self.build({"package.json": '{"workspaces":["apps/*"]}'})
        self.assertTrue(devserver.is_workspace_root(Path(root)))

    def test_a_plain_project_is_not_a_workspace(self):
        import devserver

        root = self.build({"package.json": '{"scripts":{"dev":"vite"}}'})
        self.assertFalse(devserver.is_workspace_root(Path(root)))

    def test_a_pnpm_workspace_is_one_too(self):
        import devserver

        root = self.build({"pnpm-workspace.yaml": "packages:\n  - apps/*\n"})
        self.assertTrue(devserver.is_workspace_root(Path(root)))


class ASharePointSite(unittest.TestCase):
    URL = "https://contoso.sharepoint.com/sites/ExampleSite/SitePages/Home.aspx"

    def test_without_a_checkout_it_asks_for_the_whole_tree(self):
        plan = run_profile.build(self.URL, signed_in=True)
        self.assertEqual(plan.suggestion("render").value, "always")
        self.assertEqual(plan.suggestion("page_tree").value, "sharepoint")
        self.assertEqual(plan.suggestion("site_scope").value,
                         "/sites/ExampleSite")
        for option in ("render", "page_tree", "site_scope"):
            item = plan.suggestion(option)
            self.assertEqual(item.stack, "sharepoint")
            self.assertIn("contoso.sharepoint.com", item.evidence)
        self.assertFalse(plan.asks_for("sign_in"))

    def test_without_a_session_it_asks_for_a_sign_in(self):
        plan = run_profile.build(self.URL, signed_in=False)
        self.assertTrue(plan.asks_for("sign_in"))

    def test_the_session_is_looked_up_when_not_given(self):
        # The test run's config directory is empty: no session stored.
        self.assertTrue(run_profile.build(self.URL).asks_for("sign_in"))

    def test_a_paired_checkout_keeps_web_parts_and_drops_the_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            _tree(Path(tmp), {"config/package-solution.json": "{}"})
            plan = run_profile.build(self.URL, repo=tmp, signed_in=True)
        self.assertIsNotNone(plan.suggestion("web_parts"))
        self.assertEqual(plan.suggestion("render").value, "always")
        self.assertIsNone(plan.suggestion("page_tree"))
        self.assertIsNone(plan.suggestion("site_scope"))
        self.assertEqual(plan.stacks(), ["sharepoint", "spfx"])

    def test_an_ordinary_site_asks_for_none_of_it(self):
        plan = run_profile.build("https://example.com/", signed_in=False)
        self.assertEqual(plan.suggestions, ())
        self.assertEqual(plan.prompts, ())
        self.assertIsNone(plan.profile)

    def test_the_new_options_belong_to_a_site_only(self):
        for option in ("page_tree", "site_scope"):
            self.assertEqual(run_profile._OPTION_KINDS[option],
                             (run_profile.KIND_SITE,))

    def test_applying_never_overwrites_a_hand_set_render(self):
        plan = run_profile.build(self.URL, signed_in=True)
        args = argparse.Namespace(render="never")
        applied = plan.apply(args, touched={"render"})
        self.assertEqual(args.render, "never")
        self.assertNotIn("render", [item.option for item in applied])
        self.assertEqual(args.page_tree, "sharepoint")


if __name__ == "__main__":
    unittest.main()
