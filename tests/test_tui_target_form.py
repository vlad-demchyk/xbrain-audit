"""The terminal form asks only what the target can answer.

Both run screens offered the same eleven controls for a URL, a folder and a
single HTML file. Most of them were dead for two of the three: `--depth`
crawls links a folder has none of, `--incremental` compares mtimes a URL has
none of, `--site-controls` fetches a `robots.txt` a local file has none of.
A control that reaches nothing teaches a person that this tool's controls
reach nothing.

The other half is the risk that came with fixing it. A hidden control still
holds its last value, and a `--devserver` ticked for a repository and left
ticked while a file was audited would start a dev server for a file. So the
run is built through `RunScreen.settle`, and these tests are mostly about
what must *not* reach a run.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("TEXTUAL_HEADLESS", "1")

from textual.widgets import Checkbox, Input, Label, Select


def run(coro):
    return asyncio.run(coro)


class _Form(unittest.TestCase):
    """A run screen, driven headless, with the runner replaced by a spy."""

    screen_class = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name
        self.addCleanup(self._restore)

        import tui.runner as runner

        self._real_start = runner.start
        self.addCleanup(lambda: setattr(runner, "start", self._real_start))
        self.started = {}

        def spy(command, args, title=""):
            self.started["args"] = args

            class _Finished:
                running = False
                # `report_paths` is part of what a finished run answers -
                # `ResultsScreen.__init__` calls it. Whether the screen gets
                # built at all is a race with the poll timer, so a stub
                # missing it fails only sometimes: it passed here for weeks
                # and fell over on 2026-09-02 in a slower environment, with
                # an `AttributeError` about the stub rather than about
                # anything under test.
                result = type("_R", (), {"error": None, "output": "",
                                         "code": 0, "exit_code": 0,
                                         "report_paths": lambda self: []})()

                def new_lines(self):
                    return []

            return _Finished()

        runner.start = spy

    def _restore(self):
        if self._previous is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._previous

    def tree(self, files: dict) -> Path:
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return self.root

    async def open(self, pilot, app):
        await app.push_screen(self.screen_class())
        await pilot.pause()
        await pilot.pause()
        return app.screen

    async def aim(self, pilot, screen, target: str):
        screen.query_one("#target", Input).value = target
        screen.reshape_for_target()
        await pilot.pause()


class TheAuditFormFollowsTheTarget(_Form):
    def setUp(self):
        super().setUp()
        from tui.screens.audit import AuditScreen

        self.screen_class = AuditScreen

    def test_crawl_controls_are_for_sites_only(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                folder = self.tree({"index.html": "<html></html>"})
                await self.aim(pilot, screen, str(folder))
                self.assertFalse(screen.query_one("#depth").display)
                self.assertFalse(screen.query_one("#site-controls").display)
                await self.aim(pilot, screen, "https://example.com")
                self.assertTrue(screen.query_one("#depth").display)
                self.assertTrue(screen.query_one("#site-controls").display)
                app.exit()

        run(go())

    def test_an_spfx_checkout_is_offered_the_site_it_ships_to(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                await self.aim(pilot, screen, str(self.tree(
                    {"config/package-solution.json": "{}"})))
                self.assertTrue(screen.query_one("#site-url").display)
                app.exit()

        run(go())

    def test_a_plain_folder_is_not(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                await self.aim(pilot, screen,
                               str(self.tree({"index.html": "<html></html>"})))
                self.assertFalse(screen.query_one("#site-url").display)
                app.exit()

        run(go())

    def test_a_site_and_a_checkout_run_as_one_audit(self):
        """The pivot: the address is what gets audited, the checkout is what
        names the file behind each finding, and `--web-parts` keeps the
        audit to the parts that checkout ships."""
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                folder = self.tree({"config/package-solution.json": "{}"})
                await self.aim(pilot, screen, str(folder))
                screen.query_one("#site-url", Input).value = \
                    "https://contoso.sharepoint.com/sites/intranet"
                screen._run_audit()
                await pilot.pause()
                args = self.started["args"]
                self.assertEqual(args.target,
                                 "https://contoso.sharepoint.com/sites/intranet")
                self.assertEqual(args.repo, str(folder))
                self.assertTrue(args.web_parts)
                app.exit()

        run(go())


class TheFullScanFormFollowsTheTarget(_Form):
    def setUp(self):
        super().setUp()
        from tui.screens.fullscan import FullscanScreen

        self.screen_class = FullscanScreen

    def test_a_served_stack_pre_ticks_its_dev_server(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                await self.aim(pilot, screen, str(self.tree(
                    {"vite.config.ts": "export default {}"})))
                self.assertTrue(screen.query_one("#devserver", Checkbox).value)
                self.assertNotIn("devserver", screen._touched)
                app.exit()

        run(go())

    def test_the_reason_is_on_screen_beside_it(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                await self.aim(pilot, screen, str(self.tree(
                    {"vite.config.ts": "export default {}"})))
                note = screen.query_one("#fullscan-profile", Label)
                self.assertTrue(note.display)
                text = str(getattr(note, "_Static__content", ""))
                self.assertIn("vite.config.ts", text)
                app.exit()

        run(go())

    def test_a_switch_the_person_set_is_not_overwritten(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                box = screen.query_one("#devserver", Checkbox)
                box.value = False
                await pilot.pause()
                screen._touched.add("devserver")
                await self.aim(pilot, screen, str(self.tree(
                    {"vite.config.ts": "export default {}"})))
                self.assertFalse(box.value)
                app.exit()

        run(go())

    def test_a_hidden_switch_never_reaches_the_run(self):
        """Ticked for a repository, then a single file is audited: the run
        must not carry a dev server it has no repository to start."""
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                folder = self.tree({"vite.config.ts": "export default {}",
                                    "page.html": "<html></html>"})
                await self.aim(pilot, screen, str(folder))
                self.assertTrue(screen.query_one("#devserver", Checkbox).value)
                await self.aim(pilot, screen, str(folder / "page.html"))
                screen._run_fullscan()
                await pilot.pause()
                args = self.started["args"]
                self.assertFalse(args.devserver)
                self.assertFalse(args.incremental)
                self.assertEqual(args.depth, 0)
                app.exit()

        run(go())

    def test_several_projects_are_named_rather_than_merged_silently(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 60)) as pilot:
                screen = await self.open(pilot, app)
                folder = self.tree({
                    "one/config/package-solution.json": "{}",
                    "two/config/package-solution.json": "{}",
                })
                await self.aim(pilot, screen, str(folder))
                text = str(getattr(
                    screen.query_one("#fullscan-profile", Label),
                    "_Static__content", ""))
                self.assertIn("one", text)
                self.assertIn("two", text)
                app.exit()

        run(go())


class OneProjectOutOfSeveral(_Form):
    def setUp(self):
        super().setUp()
        from tui.screens.fullscan import FullscanScreen

        self.screen_class = FullscanScreen

    def _monorepo(self) -> Path:
        return self.tree({
            "package.json": '{"workspaces":["apps/*"],'
                            '"scripts":{"dev":"turbo dev"}}',
            "apps/web/package.json": '{"scripts":{"dev":"vite"}}',
            "apps/web/vite.config.ts": "export default {}",
            "apps/admin/package.json": '{"scripts":{"dev":"vite"}}',
            "apps/admin/vite.config.ts": "export default {}",
        })

    def test_the_projects_are_offered_and_the_choice_reaches_the_run(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 70)) as pilot:
                screen = await self.open(pilot, app)
                await self.aim(pilot, screen, str(self._monorepo()))
                picker = screen.query_one("#project", Select)
                self.assertTrue(picker.display)
                offered = {label for label, _value in picker._options
                           if isinstance(label, str)}
                self.assertTrue({"web", "admin"} <= offered)
                picker.value = "web"
                # The profile pre-ticks the dev server for a Vite project,
                # and an unbuilt one asks to install first - a modal, not a
                # run. This test is about the project picker.
                screen.query_one("#devserver", Checkbox).value = False
                await pilot.pause()
                screen._run_fullscan()
                await pilot.pause()
                self.assertEqual(self.started["args"].project, "web")
                app.exit()

        run(go())

    def test_a_folder_with_one_project_is_not_asked(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 70)) as pilot:
                screen = await self.open(pilot, app)
                await self.aim(pilot, screen, str(self.tree(
                    {"vite.config.ts": "export default {}"})))
                self.assertFalse(screen.query_one("#project").display)
                screen._run_fullscan()
                await pilot.pause()
                self.assertIsNone(self.started["args"].project)
                app.exit()

        run(go())

    def test_the_dev_server_overrides_appear_only_where_a_server_does(self):
        async def go():
            from tui.app import XBrainAuditApp

            app = XBrainAuditApp()
            async with app.run_test(size=(120, 70)) as pilot:
                screen = await self.open(pilot, app)
                folder = self.tree({"package.json": '{"scripts":{"dev":"v"}}',
                                    "page.html": "<html></html>"})
                await self.aim(pilot, screen, str(folder))
                self.assertTrue(screen.query_one("#start-command").display)
                screen.query_one("#start-command", Input).value = "npm run x"
                screen.query_one("#dev-server-port", Input).value = "5173"
                await self.aim(pilot, screen, str(folder / "page.html"))
                self.assertFalse(screen.query_one("#start-command").display)
                screen.query_one("#devserver", Checkbox).value = False
                await pilot.pause()
                screen._run_fullscan()
                await pilot.pause()
                args = self.started["args"]
                self.assertIsNone(args.start_command)
                self.assertIsNone(args.dev_server_port)
                app.exit()

        run(go())

    def test_a_port_that_is_not_a_number_means_work_it_out(self):
        from tui.screens.fullscan import _port_or_none

        self.assertIsNone(_port_or_none(""))
        self.assertIsNone(_port_or_none("soon"))
        self.assertIsNone(_port_or_none("99999"))
        self.assertEqual(_port_or_none("5173"), 5173)


if __name__ == "__main__":
    unittest.main()
