"""One run at a time, Settings as the starting values, an honest Done.

P-26: the run lock belongs to the process, because the worker swaps
`sys.stdout`/`sys.stderr` for the whole process.
P-31: the run screens start from Settings, not from numbers of their own.
P-32: a command that returns 2 is a failure even though it raised nothing.
"""
from __future__ import annotations

import argparse
import threading
import unittest

from tui import run_defaults, runner


class ExitCodes(unittest.TestCase):
    def test_zero_and_one_are_a_finished_job(self):
        self.assertTrue(runner.RunResult(0, "", "").ok)
        self.assertTrue(runner.RunResult(1, "", "").ok)

    def test_two_is_a_failure_without_an_exception(self):
        self.assertFalse(runner.RunResult(2, "", "").ok)
        self.assertFalse(runner.RunResult(3, "", "").ok)

    def test_an_exception_is_a_failure_whatever_the_code(self):
        self.assertFalse(runner.RunResult(0, "", "", error="boom").ok)

    def test_the_screen_does_not_paint_a_returned_two_green(self):
        from tui.screens.base import RunScreen

        said, pushed = [], []

        class _App:
            def push_screen(self, screen):
                pushed.append(screen)

        class _Screen:
            app = _App()

            def tr(self, key, **values):
                return key, values

            def status(self, text, *, ok=False):
                said.append((text, ok))

        from unittest import mock

        with mock.patch("tui.screens.results.ResultsScreen",
                        lambda title, result: (title, result)):
            RunScreen.show_result(_Screen(), "t", runner.RunResult(2, "", "x"))
        self.assertEqual(said, [(("tui_run_failed_code", {"code": 2}), False)])
        self.assertEqual(len(pushed), 1, "the log stays reachable")


class OneRunAtATime(unittest.TestCase):
    def test_a_second_run_is_refused_while_the_first_is_going(self):
        gate = threading.Event()
        first = runner.start(lambda _a: gate.wait(5) and 0,
                             argparse.Namespace(), "crawl")
        try:
            self.assertTrue(runner.busy())
            with self.assertRaises(runner.RunBusy) as caught:
                runner.start(lambda _a: 0, argparse.Namespace(), "audit")
            self.assertIs(caught.exception.active, first)
        finally:
            gate.set()
            first.join(5)
        self.assertFalse(runner.busy())
        second = runner.start(lambda _a: 0, argparse.Namespace(), "audit")
        second.join(5)
        self.assertEqual(second.result.exit_code, 0)


class StartingValues(unittest.TestCase):
    def _settings(self, **values):
        import config

        settings = config.Settings()
        for name, value in values.items():
            setattr(settings, name, value)
        return settings

    def test_the_stored_settings_become_the_run_defaults(self):
        got = run_defaults.from_settings(self._settings(
            crawl_depth=3, max_pages=0, repo_scope="both",
            default_method="local+ai"))
        self.assertEqual(got, run_defaults.RunDefaults(
            depth="3", max_pages=0, scope="both", detector="hybrid"))

    def test_each_method_picks_its_detector(self):
        for method, detector in (("local", "offline"), ("ai", "llm-judge"),
                                 ("local+ai", "hybrid")):
            with self.subTest(method=method):
                self.assertEqual(run_defaults.from_settings(
                    self._settings(default_method=method)).detector, detector)

    def test_a_value_no_control_offers_falls_back(self):
        got = run_defaults.from_settings(self._settings(
            crawl_depth=9, max_pages=-1, repo_scope="all",
            default_method="psychic"))
        self.assertEqual(got, run_defaults.RunDefaults())

    def test_unreadable_settings_still_draw_a_form(self):
        from unittest import mock

        import config

        with mock.patch.object(config.Settings, "load",
                               side_effect=OSError("gone")):
            self.assertEqual(run_defaults.load(), run_defaults.RunDefaults())


class TheScreensReadThem(unittest.TestCase):
    """The run screens start where Settings says, and follow a later Save."""

    def test_audit_and_scan_start_from_settings(self):
        import asyncio
        from unittest import mock

        from textual.widgets import Select

        from tui.app import XBrainAuditApp

        stored = run_defaults.RunDefaults(depth="2", max_pages=10,
                                          scope="technical", detector="hybrid")
        later = run_defaults.RunDefaults(depth="3", max_pages=10,
                                         scope="both", detector="offline")

        async def scenario():
            with mock.patch.object(run_defaults, "load", return_value=stored):
                app = XBrainAuditApp()
                async with app.run_test(size=(140, 50)) as pilot:
                    app.push_screen("audit")
                    await pilot.pause()
                    audit = app.screen
                    self.assertEqual(audit.query_one("#depth", Select).value, "2")
                    app.pop_screen()
                    app.push_screen("scan")
                    await pilot.pause()
                    scan = app.screen
                    self.assertEqual(scan.query_one("#scope", Select).value,
                                     "technical")
                    self.assertEqual(scan.query_one("#detector", Select).value,
                                     "hybrid")
                    app.pop_screen()
                    with mock.patch.object(run_defaults, "load",
                                           return_value=later):
                        app.push_screen("audit")
                        await pilot.pause()
                        self.assertEqual(
                            audit.query_one("#depth", Select).value, "3")
                        self.assertNotIn("depth", audit._touched)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
