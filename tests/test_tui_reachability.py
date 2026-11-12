"""The TUI has to be usable: by keyboard, on a real terminal, from a clean
install.

Three failures found in one live session, and none of them is a crash - each
is the interface being *present* and unusable:

* the Account screen disabled both fields and the sign-in button whenever the
  chosen provider was not xFormat, which is the default. Signing in to the
  subscription required first choosing the subscription in Settings, which is
  the wrong way round;
* `scan`, `audit` and `fullscan` - the three screens where work starts - had
  no key bindings at all, so a run could only be started with a mouse;
* on an 80-column terminal, lines up to 161 characters were drawn past the
  right edge, where a terminal has no horizontal scroll to get them back.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

os.environ.setdefault("TEXTUAL_HEADLESS", "1")

from textual.widgets import Button, Checkbox, Input, Label


def run(coro):
    return asyncio.run(coro)


class _Isolated(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name
        self.addCleanup(self._restore)

    def _restore(self):
        if self._previous is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._previous


class TheAccountScreenCanBeUsed(_Isolated):
    async def _open(self, pilot, app):
        from tui.screens.account import AccountScreen

        await app.push_screen(AccountScreen())
        await pilot.pause()
        return app.screen

    def test_a_fresh_install_can_sign_in(self):
        """The default provider is `anthropic`, and this used to disable the
        whole form - so the one screen that signs in to the subscription was
        unusable until the subscription was already selected."""
        import config
        from tui.app import XBrainAuditApp

        self.assertNotEqual(config.Settings().llm_provider, "xformat")

        async def main():
            app = XBrainAuditApp()
            async with app.run_test(size=(100, 44)) as pilot:
                screen = await self._open(pilot, app)
                self.assertFalse(screen.query_one("#account-email", Input).disabled)
                self.assertFalse(screen.query_one("#account-password", Input).disabled)
                self.assertFalse(screen.query_one("#sign-in", Button).disabled)

        run(main())

    def test_switching_who_pays_is_offered_only_when_somebody_else_pays(self):
        import config
        from tui.app import XBrainAuditApp

        async def main():
            app = XBrainAuditApp()
            async with app.run_test(size=(100, 44)) as pilot:
                screen = await self._open(pilot, app)
                self.assertTrue(screen.query_one("#use-xformat", Button).display)
                settings = config.Settings.load()
                settings.llm_provider = "xformat"
                settings.save()
                screen.action_refresh()
                await pilot.pause()
                self.assertFalse(screen.query_one("#use-xformat", Button).display)

        run(main())

    def test_switching_is_a_separate_press_and_it_works(self):
        """Signing in and changing who pays are two decisions. Doing the
        second silently as part of the first bills somebody somewhere they
        did not choose."""
        import config
        from tui.app import XBrainAuditApp

        async def main():
            app = XBrainAuditApp()
            async with app.run_test(size=(100, 44)) as pilot:
                screen = await self._open(pilot, app)
                screen._use_xformat()
                await pilot.pause()
                self.assertEqual(config.Settings.load().llm_provider, "xformat")

        run(main())


class EveryRunScreenAnswersTheKeyboard(_Isolated):
    SCREENS = ("scan", "audit", "fullscan")

    def test_each_one_binds_escape_and_a_run_key(self):
        import importlib

        from tui.app import XBrainAuditApp

        async def main():
            for name in self.SCREENS:
                module = importlib.import_module(f"tui.screens.{name}")
                cls = next(v for k, v in vars(module).items()
                           if k.endswith("Screen") and k != "RunScreen")
                app = XBrainAuditApp()
                async with app.run_test(size=(100, 44)) as pilot:
                    await app.push_screen(cls())
                    await pilot.pause()
                    keys = set(app.screen._bindings.key_to_bindings)
                    self.assertIn("escape", keys, name)
                    self.assertIn("ctrl+r", keys, name)
                    self.assertIn("f5", keys, name)

        run(main())

    def test_the_run_key_starts_the_run_and_says_what_is_missing(self):
        from tui.app import XBrainAuditApp
        from tui.screens.audit import AuditScreen

        async def main():
            app = XBrainAuditApp()
            async with app.run_test(size=(100, 44)) as pilot:
                await app.push_screen(AuditScreen())
                await pilot.pause()
                await pilot.press("ctrl+r")
                await pilot.pause()
                said = str(app.screen.query_one("#audit-status", Label).render())
                self.assertTrue(said.strip(), "the run key did nothing at all")

        run(main())

    def test_a_modal_can_be_answered_without_a_mouse(self):
        from tui.app import XBrainAuditApp
        from tui.screens.confirm import ConfirmModal

        async def main():
            app = XBrainAuditApp()
            answers = []
            async with app.run_test(size=(100, 44)) as pilot:
                app.push_screen(ConfirmModal("Sure?"), answers.append)
                await pilot.pause()
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(answers, [True])
                app.push_screen(ConfirmModal("Sure?"), answers.append)
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                self.assertEqual(answers, [True, False])

        run(main())


class NothingIsDrawnPastTheEdge(_Isolated):
    """A terminal has no horizontal scroll. Anything wider than the screen is
    simply gone, and 80 columns is what a terminal is until somebody widens
    it."""

    SIZES = ((80, 24), (120, 40))

    def _screens(self):
        from tui.screens import (
            account, audit, fullscan, logs, reports, scan, settings,
            uninstall, update,
        )
        return [
            (scan.ScanScreen, "scan"), (audit.AuditScreen, "audit"),
            (fullscan.FullscanScreen, "fullscan"),
            (settings.SettingsScreen, "settings"),
            (account.AccountScreen, "account"),
            (reports.ReportsScreen, "reports"), (logs.LogsScreen, "logs"),
            (update.UpdateScreen, "update"),
            (uninstall.UninstallScreen, "uninstall"),
        ]

    def test_no_widget_is_wider_than_the_terminal(self):
        from tui.app import XBrainAuditApp

        async def main():
            for width, height in self.SIZES:
                for cls, name in self._screens():
                    app = XBrainAuditApp()
                    async with app.run_test(size=(width, height)) as pilot:
                        await app.push_screen(cls())
                        await pilot.pause()
                        over = [node.__class__.__name__
                                for node in app.screen.query("*")
                                if (region := getattr(node, "region", None))
                                and region.width
                                and region.x + region.width > width
                                # Textual draws its own footer and clips it
                                # itself; the forms are what this is about.
                                and node.__class__.__name__ != "FooterKey"]
                        self.assertEqual(
                            over, [],
                            f"{name} at {width}x{height} draws past the edge")

        run(main())

    def test_a_narrow_terminal_turns_sentences_into_columns(self):
        """Below ~72 columns three selectors cannot share a line, so the row
        becomes a column - taller, and on screen."""
        from tui.app import XBrainAuditApp
        from tui.screens.fullscan import FullscanScreen

        async def main():
            app = XBrainAuditApp()
            async with app.run_test(size=(60, 20)) as pilot:
                await app.push_screen(FullscanScreen())
                await pilot.pause()
                self.assertTrue(app.screen.has_class("narrow"))
            app = XBrainAuditApp()
            async with app.run_test(size=(120, 40)) as pilot:
                await app.push_screen(FullscanScreen())
                await pilot.pause()
                self.assertFalse(app.screen.has_class("narrow"))

        run(main())


class TheFormsAskWhatTheCommandAsks(_Isolated):
    """Measured 2026-09-01: of the flags each command accepts, `audit` had
    five with no control here and `fullscan` nine. These are the ones that
    change what a run reads."""

    def test_audit_can_narrow_to_a_selector_and_refuse_the_session(self):
        from tui.app import XBrainAuditApp
        from tui.screens.audit import AuditScreen

        async def main():
            app = XBrainAuditApp()
            async with app.run_test(size=(100, 44)) as pilot:
                await app.push_screen(AuditScreen())
                await pilot.pause()
                screen = app.screen
                screen.query_one("#target", Input).value = "example.test"
                screen.query_one("#within", Input).value = ".widget"
                screen.query_one("#no-session", Checkbox).value = True
                sent = {}
                screen.start_run = lambda _fn, args, **_kw: sent.update(vars(args))
                screen._run_audit()
                self.assertEqual(sent.get("within"), ".widget")
                self.assertIs(sent.get("no_session"), True)

        run(main())

    def test_fullscan_can_reuse_the_cache_and_refuse_the_session(self):
        from tui.app import XBrainAuditApp
        from tui.screens.fullscan import FullscanScreen

        async def main():
            app = XBrainAuditApp()
            async with app.run_test(size=(100, 44)) as pilot:
                await app.push_screen(FullscanScreen())
                await pilot.pause()
                screen = app.screen
                screen.query_one("#target", Input).value = "example.test"
                screen.query_one("#incremental", Checkbox).value = True
                screen.query_one("#no-session", Checkbox).value = True
                sent = {}
                screen.start_run = lambda _fn, args, **_kw: sent.update(vars(args))
                screen._run_fullscan()
                self.assertIs(sent.get("incremental"), True)
                self.assertIs(sent.get("no_session"), True)

        run(main())


if __name__ == "__main__":
    unittest.main()
