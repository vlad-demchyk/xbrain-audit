"""The terminal interface, driven for real.

Four defects are pinned here, all reported from using the thing:

1. A target without `https://` was refused.
2. Every screen ended with "See results in terminal" and showed no result.
3. Arrow keys did nothing - Textual binds only `tab` by default.
4. Clicking a report did nothing - the table had no selection handler.

Driven through Textual's own `run_test` pilot rather than by poking widgets,
because three of the four were about key and mouse handling and only a real
event loop exercises that.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import unittest
from pathlib import Path
from unittest import mock

from textual.widgets import Button, Checkbox, DataTable, Input, Label, Select

from tui.app import XBrainAuditApp
from tui import runner as tui_runner
from tui.runner import RunResult


def run(coroutine):
    """Drive one async test body. The suite is `unittest`, not pytest-asyncio."""
    return asyncio.new_event_loop().run_until_complete(coroutine)


class Runner(unittest.TestCase):
    """The capture layer that replaced "see results in terminal"."""

    def test_stdout_is_captured_and_parsed(self):
        def command(_args):
            print(json.dumps({"counts": {"total": 3}}))
            return 0

        result = self._run(command)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.payload(), {"counts": {"total": 3}})

    def test_progress_lines_are_reported_as_they_happen(self):
        import sys

        def command(_args):
            print("# [stage crawl]", file=sys.stderr)
            print("# [crawl done] 2 page(s)", file=sys.stderr)
            print("{}")
            return 0

        seen: list = []
        self._run(command, on_progress=seen.append)
        self.assertIn("# [stage crawl]", seen)
        self.assertIn("# [crawl done] 2 page(s)", seen)

    def test_report_paths_come_from_what_was_announced(self):
        import sys

        def command(_args):
            print("# report: /tmp/a/report.md", file=sys.stderr)
            print("# styled report: /tmp/a/report.pdf", file=sys.stderr)
            print("# run folder: /tmp/a", file=sys.stderr)
            print("{}")
            return 0

        result = self._run(command)
        self.assertEqual(result.report_paths(),
                         ["/tmp/a/report.md", "/tmp/a/report.pdf", "/tmp/a"])

    def test_an_exception_is_reported_not_swallowed(self):
        def command(_args):
            raise RuntimeError("boom")

        result = self._run(command)
        self.assertFalse(result.ok)
        self.assertIn("boom", result.error)

    def test_streams_are_restored_afterwards(self):
        """The capture is process-wide, so it must always be undone."""
        import sys

        before = sys.stdout

        def command(_args):
            raise RuntimeError("boom")

        self._run(command)
        self.assertIs(sys.stdout, before)

    def test_non_json_output_yields_no_payload(self):
        def command(_args):
            print("No findings.")
            return 0

        self.assertIsNone(self._run(command).payload())

    def _run(self, command, on_progress=None):
        """Run `command` through the runner and wait for it, without an app."""
        run = tui_runner.start(command, argparse.Namespace())
        run.join(timeout=10)
        self.assertIsNotNone(run.result, "the run never finished")
        if on_progress is not None:
            for line in run.new_lines():
                on_progress(line)
        return run.result


class ArrowNavigation(unittest.TestCase):
    """Defect 3: arrows did nothing, though the README promised them."""

    def test_down_moves_focus_forward(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.screen.focus_next()
                await pilot.pause()
                first = app.focused
                await pilot.press("down")
                await pilot.pause()
                return first, app.focused

        first, second = run(body())
        self.assertIsNotNone(first)
        self.assertIsNot(first, second)

    def test_up_moves_focus_back(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.screen.focus_next()
                await pilot.pause()
                first = app.focused
                await pilot.press("down")
                await pilot.press("up")
                await pilot.pause()
                return first, app.focused

        first, back = run(body())
        self.assertIs(first, back)

    def test_footer_shows_the_key_hints(self):
        """The bindings existed; nothing displayed them."""
        from textual.widgets import Footer

        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                return len(app.screen.query(Footer))

        self.assertEqual(run(body()), 1)


class MenuNavigation(unittest.TestCase):
    def test_narrow_menu_scrolls_to_the_last_action(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                menu = app.screen.query_one("#main-menu")
                for _ in range(8):
                    await pilot.press("down")
                await pilot.pause()
                return app.focused.id, menu.scroll_y

        focused_id, scroll_y = run(body())
        self.assertEqual(focused_id, "account")
        self.assertGreater(scroll_y, 0)

    def test_number_shortcut_opens_the_screen(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("4")
                await pilot.pause()
                return app.screen.__class__.__name__

        self.assertEqual(run(body()), "ReportsScreen")

    def test_escape_returns_to_the_menu(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("2")
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                return app.screen.__class__.__name__

        self.assertEqual(run(body()), "MainMenuScreen")

    def test_every_menu_entry_has_a_screen(self):
        from tui.screens.main_menu import MENU

        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                missing = []
                for _key, name in MENU:
                    if name not in app._installed_screens:
                        missing.append(name)
                return missing

        self.assertEqual(run(body()), [])


class SchemelessTarget(unittest.TestCase):
    """Defect 1: `example.com` typed into the form must reach the command."""

    def test_fullscan_passes_the_bare_host_through(self):
        async def body():
            app = XBrainAuditApp()
            captured: list = []

            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("3")
                await pilot.pause()
                screen = app.screen
                screen.query_one("#target", Input).value = "example.com"
                with mock.patch.object(screen, "start_run",
                                       side_effect=lambda *a, **k:
                                       captured.append((a, k)) or True):
                    screen._run_fullscan()
                await pilot.pause()
            return captured

        captured = run(body())
        self.assertEqual(len(captured), 1)
        (_command, args), _kwargs = captured[0]
        self.assertEqual(args.target, "example.com")

    def test_the_command_itself_accepts_it(self):
        """The form is only half of it - the CLI has to agree."""
        from cli_impl.auditpass import looks_like_url

        self.assertTrue(looks_like_url("example.com"))

    def test_empty_target_is_refused_with_a_sentence(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("3")
                await pilot.pause()
                app.screen._run_fullscan()
                await pilot.pause()
                return str(app.screen.query_one("#fullscan-status", Label)
                           .render())

        # Through the dictionary, not as the English string it used to be:
        # that literal passed only because the suite was reading the
        # developer's own `settings.json`, where `ui_language` happened to
        # be "en". With tests isolated (`P-13`) the default is "uk".
        from i18n.translations import t

        self.assertIn(t("tui_need_target", XBrainAuditApp().lang), run(body()))


class ResultsScreenShowsTheResult(unittest.TestCase):
    """Defect 2: the result was announced as being somewhere else."""

    def result(self):
        return RunResult(
            0,
            json.dumps({"target": "https://example.com",
                        "summary": {"total_findings": 14, "accessibility": 6}}),
            "# report: /tmp/nope/report.md\n",
        )

    def test_summary_rows_are_built_from_the_payload(self):
        from tui.screens.results import summary_rows

        rows = dict(summary_rows(self.result().payload()))
        self.assertEqual(rows["total findings"], "14")
        self.assertEqual(rows["accessibility"], "6")
        self.assertEqual(rows["target"], "https://example.com")

    def test_no_payload_means_no_rows_rather_than_a_crash(self):
        from tui.screens.results import summary_rows

        self.assertEqual(summary_rows(None), [])

    def test_screen_lists_what_was_written(self):
        from tui.screens.results import ResultsScreen

        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(ResultsScreen("Scan of x", self.result()))
                await pilot.pause()
                text = str(app.screen.query_one("#results-paths", Label)
                           .render())
                table = app.screen.query_one("#results-summary", DataTable)
                return text, table.row_count

        text, rows = run(body())
        self.assertIn("/tmp/nope/report.md", text)
        self.assertGreater(rows, 0)

    def test_a_missing_file_cannot_be_opened(self):
        from tui.screens.results import open_in_os

        from i18n.translations import t

        # The message is in the interface language now, so the test asks for
        # the string that language actually produces.
        self.assertEqual(open_in_os("/tmp/definitely-not-here-42", "en"),
                         t("tui_open_gone", "en",
                           path="/tmp/definitely-not-here-42"))

    def test_severity_rows_get_four_different_colours_not_one(self):
        """Before this, "critical" and "minor" were the table's default
        foreground - the same colour a run with no findings at all used for
        "target". The severity ramp existing in the palette does nothing for
        anyone if the one screen that lists severities by name never reads
        it.

        The cell is matched on its **last word**, the way `_severity_cell`
        matches, rather than on the whole string. Matching the whole string
        is what made this test fail for two weeks while the screen was right:
        the mark prefix for low-colour terminals turned "critical" into
        "!!! critical", the test found none of its four names, and an empty
        set is not a missing colour.
        """
        from tui.screens.results import ResultsScreen, SEVERITIES
        from i18n.translations import t

        result = RunResult(
            0,
            json.dumps({"counts": {"critical": 3, "serious": 8,
                                    "moderate": 15, "minor": 14}}),
            "",
        )

        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(ResultsScreen("Scan of x", result))
                await pilot.pause()
                table = app.screen.query_one("#results-summary", DataTable)
                styles = {}
                for row_key, _ in table.rows.items():
                    cell = table.get_cell(row_key, table.ordered_columns[0].key)
                    for severity in SEVERITIES:
                        translated = t(f"tui_sum_{severity}", app.lang)
                        if str(cell).endswith(translated):
                            styles[severity] = cell.style
                return styles

        styles = run(body())
        self.assertEqual(set(styles), set(SEVERITIES))
        self.assertEqual(len(set(styles.values())), 4,
                         f"expected four distinct colours, got {styles}")

    def test_a_severity_is_listed_once_not_twice(self):
        """`counts` means one thing for `scan` (a key per detector) and
        another for `audit` (a key per severity), and the audit shape fell
        through both passes: "by critical" and "critical", eight rows for
        four numbers, on every audit run the interface has ever shown.

        The payload here is the shape `cli.py audit --json` actually prints,
        not a hand-written one - which is how the defect stayed invisible.
        """
        from tui.screens.results import summary_rows

        rows = summary_rows({"root": ".", "mode": "repo",
                             "counts": {"critical": 0, "serious": 6,
                                        "moderate": 14, "minor": 10}})
        self.assertEqual([label for label, _ in rows],
                         ["critical", "serious", "moderate", "minor"])

        # The other shape keeps its per-detector rows, which are not severities.
        rows = summary_rows({"counts": {"offline": 1, "total": 1,
                                        "files": 1, "distinct": 1}})
        self.assertIn(("by offline", "1"), rows)

    def test_the_ramp_the_mark_and_the_order_name_the_same_four(self):
        from tui.screens.results import (SEVERITIES, _SEVERITY_MARK,
                                         _SEVERITY_VARIABLE)
        self.assertEqual(set(SEVERITIES), set(_SEVERITY_MARK))
        self.assertEqual(set(SEVERITIES), set(_SEVERITY_VARIABLE))


class ReportsScreenReacts(unittest.TestCase):
    """Defect 4: clicking a row did nothing."""

    def history(self, tmp: Path) -> list:
        return [{
            "at": "2026-01-01 10:00:00 UTC", "root": "/repo", "mode": "repo",
            "counts": {"critical": 1, "minor": 2}, "distinct": 2,
            "documents": 5, "fixed": 0, "report": str(tmp / "report.md"),
        }]

    def test_rows_come_from_the_history(self):
        import tempfile

        from tui.screens import reports as screen_module

        async def body(tmp):
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                with mock.patch.object(screen_module, "load_runs",
                                       return_value=self.history(tmp)):
                    await pilot.press("4")
                    await pilot.pause()
                    table = app.screen.query_one("#reports-table", DataTable)
                    detail = str(app.screen.query_one("#report-detail", Label)
                                 .render())
                    return table.row_count, detail

        with tempfile.TemporaryDirectory() as tmp:
            rows, detail = run(body(Path(tmp)))
        self.assertEqual(rows, 1)
        self.assertIn("/repo", detail)

    def test_selecting_a_row_opens_the_report(self):
        import tempfile

        from tui.screens import reports as screen_module

        async def body(tmp):
            app = XBrainAuditApp()
            opened: list = []
            async with app.run_test() as pilot:
                await pilot.pause()
                with mock.patch.object(screen_module, "load_runs",
                                       return_value=self.history(tmp)):
                    with mock.patch.object(screen_module, "open_in_os",
                                           side_effect=lambda p, lang="uk":
                                           opened.append(p) or "ok"):
                        await pilot.press("4")
                        await pilot.pause()
                        await pilot.press("enter")
                        await pilot.pause()
            return opened

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "report.md").write_text("x", encoding="utf-8")
            opened = run(body(Path(tmp)))
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].endswith("report.md"))

    def test_an_empty_history_says_so_instead_of_nothing(self):
        from tui.screens import reports as screen_module

        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                with mock.patch.object(screen_module, "load_runs",
                                       return_value=[]):
                    await pilot.press("4")
                    await pilot.pause()
                    return str(app.screen.query_one("#report-status", Label)
                               .render())

        from i18n.translations import t

        self.assertIn(t("tui_reports_empty", XBrainAuditApp().lang), run(body()))

    def test_the_list_is_rebuilt_on_every_visit(self):
        """It used to be built once, in `on_mount`, and never again."""
        import tempfile

        from tui.screens import reports as screen_module

        async def body(tmp):
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                with mock.patch.object(screen_module, "load_runs",
                                       return_value=[]):
                    await pilot.press("4")
                    await pilot.pause()
                    await pilot.press("escape")
                    await pilot.pause()
                with mock.patch.object(screen_module, "load_runs",
                                       return_value=self.history(tmp)):
                    await pilot.press("4")
                    await pilot.pause()
                    return app.screen.query_one("#reports-table",
                                                DataTable).row_count

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(body(Path(tmp))), 1)


class SettingsAreEditable(unittest.TestCase):
    def test_saving_writes_the_changed_value(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("5")
                await pilot.pause()
                screen = app.screen
                screen.query_one("#set-repo_scope", Select).value = "both"
                with mock.patch.object(screen.settings, "save") as save:
                    screen.action_save()
                    await pilot.pause()
                    return save.call_count, screen.settings.repo_scope

        calls, value = run(body())
        self.assertEqual(calls, 1)
        self.assertEqual(value, "both")

    def test_saving_nothing_says_nothing_changed(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("5")
                await pilot.pause()
                screen = app.screen
                with mock.patch.object(screen.settings, "save") as save:
                    screen.action_save()
                    await pilot.pause()
                    return save.call_count, str(
                        screen.query_one("#settings-status", Label).render())

        calls, status = run(body())
        self.assertEqual(calls, 0)
        from i18n.translations import t

        self.assertIn(t("tui_settings_nothing", XBrainAuditApp().lang), status)

    def test_integer_settings_are_saved_as_integers(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("5")
                await pilot.pause()
                screen = app.screen
                screen.query_one("#set-crawl_depth", Select).value = "3"
                with mock.patch.object(screen.settings, "save"):
                    screen.action_save()
                return screen.settings.crawl_depth

        self.assertEqual(run(body()), 3)


class OneRunAtATime(unittest.TestCase):
    """The captured streams are process-wide, so overlap must be impossible."""

    def test_a_second_start_is_refused_while_one_is_running(self):
        import threading

        gate = threading.Event()

        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("1")
                await pilot.pause()
                screen = app.screen
                first = screen.start_run(lambda _a: gate.wait(5) and 0,
                                         argparse.Namespace(), title="x")
                second = screen.start_run(lambda _a: 0,
                                          argparse.Namespace(), title="y")
                gate.set()
                return first, second

        first, second = run(body())
        self.assertTrue(first)
        self.assertFalse(second)

    def test_the_run_button_is_disabled_while_running(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("1")
                await pilot.pause()
                screen = app.screen
                screen._set_busy(True)
                await pilot.pause()
                return screen.query_one("#run", Button).disabled

        self.assertTrue(run(body()))


class DevServerConfirm(unittest.TestCase):
    """A repo target with missing dev-server deps asks before `start_run` -
    but only when "Start dev server" is checked. Off by default: the
    server may already be running elsewhere, and starting a second one on a
    different port is a confusing outcome, not a helpful one.
    """

    def _repo_with_missing_deps(self, tmp_path):
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        return tmp_path

    def test_unchecked_by_default_scans_statically_even_with_missing_deps(self):
        """The default: no modal, no server, the plain static scan runs -
        `cmd_fullscan` itself says a stack exists, this screen does not ask."""
        import tempfile
        from tui.screens.confirm import ConfirmModal

        async def body():
            with tempfile.TemporaryDirectory() as tmp:
                repo = self._repo_with_missing_deps(Path(tmp))
                app = XBrainAuditApp()
                captured: list = []
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("3")
                    await pilot.pause()
                    screen = app.screen
                    screen.query_one("#target", Input).value = str(repo)
                    self.assertFalse(screen.query_one("#devserver", Checkbox).value)
                    with mock.patch.object(
                            screen, "start_run",
                            side_effect=lambda *a, **k: captured.append((a, k)) or True):
                        screen._run_fullscan()
                    await pilot.pause()
                    pushed_modal = isinstance(app.screen, ConfirmModal)
                return captured, pushed_modal

        captured, pushed_modal = run(body())
        self.assertFalse(pushed_modal)
        self.assertEqual(len(captured), 1)
        (_command, args), _kwargs = captured[0]
        self.assertFalse(args.devserver)

    def test_checked_and_missing_deps_pushes_a_modal_before_running(self):
        import tempfile
        from tui.screens.confirm import ConfirmModal

        async def body():
            with tempfile.TemporaryDirectory() as tmp:
                repo = self._repo_with_missing_deps(Path(tmp))
                app = XBrainAuditApp()
                captured: list = []
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("3")
                    await pilot.pause()
                    screen = app.screen
                    screen.query_one("#target", Input).value = str(repo)
                    screen.query_one("#devserver", Checkbox).value = True
                    with mock.patch.object(
                            screen, "start_run",
                            side_effect=lambda *a, **k: captured.append((a, k)) or True):
                        screen._run_fullscan()
                    await pilot.pause()
                    pushed_modal = isinstance(app.screen, ConfirmModal)
                return captured, pushed_modal

        captured, pushed_modal = run(body())
        self.assertTrue(pushed_modal)
        # start_run must not have been called yet - the question is still open.
        self.assertEqual(captured, [])

    def test_confirming_yes_starts_the_run_with_yes_set(self):
        import tempfile

        async def body():
            with tempfile.TemporaryDirectory() as tmp:
                repo = self._repo_with_missing_deps(Path(tmp))
                app = XBrainAuditApp()
                captured: list = []
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("3")
                    await pilot.pause()
                    screen = app.screen
                    screen.query_one("#target", Input).value = str(repo)
                    screen.query_one("#devserver", Checkbox).value = True
                    with mock.patch.object(
                            screen, "start_run",
                            side_effect=lambda *a, **k: captured.append((a, k)) or True):
                        screen._run_fullscan()
                        await pilot.pause()
                        await pilot.click("#confirm-yes")
                        await pilot.pause()
                return captured

        captured = run(body())
        self.assertEqual(len(captured), 1)
        (_command, args), _kwargs = captured[0]
        self.assertTrue(args.yes)

    def test_confirming_no_still_starts_the_run_static_only(self):
        """Declining the install does not cancel the scan - it falls back
        to the static repo scan, exactly like the CLI path does."""
        import tempfile

        async def body():
            with tempfile.TemporaryDirectory() as tmp:
                repo = self._repo_with_missing_deps(Path(tmp))
                app = XBrainAuditApp()
                captured: list = []
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("3")
                    await pilot.pause()
                    screen = app.screen
                    screen.query_one("#target", Input).value = str(repo)
                    screen.query_one("#devserver", Checkbox).value = True
                    with mock.patch.object(
                            screen, "start_run",
                            side_effect=lambda *a, **k: captured.append((a, k)) or True):
                        screen._run_fullscan()
                        await pilot.pause()
                        await pilot.click("#confirm-no")
                        await pilot.pause()
                return captured

        captured = run(body())
        self.assertEqual(len(captured), 1)
        (_command, args), _kwargs = captured[0]
        self.assertFalse(args.yes)

    def test_checked_and_satisfied_deps_runs_immediately(self):
        import tempfile

        async def body():
            with tempfile.TemporaryDirectory() as tmp:
                repo = Path(tmp)
                (repo / "package.json").write_text("{}", encoding="utf-8")
                (repo / "node_modules").mkdir()
                app = XBrainAuditApp()
                captured: list = []
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("3")
                    await pilot.pause()
                    screen = app.screen
                    screen.query_one("#target", Input).value = str(repo)
                    screen.query_one("#devserver", Checkbox).value = True
                    with mock.patch.object(
                            screen, "start_run",
                            side_effect=lambda *a, **k: captured.append((a, k)) or True):
                        screen._run_fullscan()
                    await pilot.pause()
                return captured

        captured = run(body())
        self.assertEqual(len(captured), 1)

    def test_a_url_target_never_triggers_a_devserver_check(self):
        async def body():
            app = XBrainAuditApp()
            captured: list = []
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("3")
                await pilot.pause()
                screen = app.screen
                screen.query_one("#target", Input).value = "https://example.com"
                with mock.patch.object(
                        screen, "start_run",
                        side_effect=lambda *a, **k: captured.append((a, k)) or True):
                    screen._run_fullscan()
                await pilot.pause()
            return captured

        captured = run(body())
        self.assertEqual(len(captured), 1)


async def _selector_widths_in_sentence(menu_key: str):
    """`([(select_id, width), ...], row_width)` for the `.sentence` row on
    the screen `menu_key` opens from the main menu.

    Textual's `query()` result is a `DOMQuery`, which walks the live DOM the
    first time something reads `.nodes` and caches that - it does not hold a
    snapshot taken at query time. Returning the `DOMQuery` itself out of
    `run_test()`'s `async with` block, the way an early version of this test
    did, defers that first read to *after* the app has torn down and its
    widgets are unmounted, so the query silently finds nothing and every
    assertion in a `for select in (that empty query)` loop never runs - a
    test that always passes without ever having tested anything. Reading the
    widths here, while the app is still mounted, and returning plain tuples
    is what makes the caller's assertions real.
    """
    app = XBrainAuditApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press(menu_key)
        await pilot.pause()
        sentence = app.screen.query_one(".sentence")
        widths = [(select.id, select.size.width)
                  for select in sentence.query(Select)]
        return widths, sentence.size.width


class FullscanReadsAsASentence(unittest.TestCase):
    """The redesign's toolbar (artboard 3a) reads "analyze Site · depth 2"
    instead of a form of labelled dropdowns. FullscanScreen's language/
    depth/breakpoints selectors moved into one such sentence; this pins the
    part that actually matters - that they are still the same three
    controls under the same three ids, so nothing about running a scan
    changed underneath the new layout."""

    def test_the_three_selectors_still_answer_to_their_old_ids(self):
        async def body():
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("3")
                await pilot.pause()
                screen = app.screen
                return (
                    screen.query_one("#language", Select).value,
                    screen.query_one("#depth", Select).value,
                    screen.query_one("#breakpoints", Select).value,
                )

        language, depth, breakpoints = run(body())
        self.assertEqual(language, "")
        self.assertEqual(depth, "1")
        self.assertEqual(breakpoints, "desktop")

    def test_the_selectors_size_to_their_value_not_to_the_full_row(self):
        """Regression for a real defect found while building this screen:
        `SelectCurrent`'s own default CSS is `width: 1fr`, so without an
        explicit override each selector claimed the sentence's entire
        width and pushed everything after the first one off screen -
        `debug`-rendering the screen showed only the word "language" and
        nothing else in the row."""
        widths, row_width = run(_selector_widths_in_sentence("3"))
        self.assertTrue(widths, "no Select found in the sentence row at all")
        for select_id, width in widths:
            self.assertLess(
                width, row_width // 2,
                f"#{select_id} claimed {width} of a {row_width}-wide row")


class TheOtherFormsBecameSentencesToo(unittest.TestCase):
    """Scan (detector/scope) and Audit (language/depth/breakpoints) got the
    same treatment as Fullscan, for the same reason: one inline sentence
    instead of a stack of labelled dropdowns. This is the width regression
    from `FullscanReadsAsASentence` run against the other two screens,
    because the defect it guards against (`SelectCurrent`'s `width: 1fr`
    swallowing the row) is a property of the shared `.sentence` CSS, not of
    any one screen, and a screen added after this file was last read would
    hit it the same way if that CSS regressed.
    """

    def _selectors_fit_their_row(self, menu_key):
        widths, row_width = run(_selector_widths_in_sentence(menu_key))
        self.assertTrue(widths, "no Select found in the sentence row at all")
        for select_id, width in widths:
            self.assertLess(
                width, row_width // 2,
                f"#{select_id} claimed {width} of a {row_width}-wide row")

    def test_scan_screen_detector_and_scope_fit_their_row(self):
        self._selectors_fit_their_row("1")

    def test_audit_screen_language_depth_and_breakpoints_fit_their_row(self):
        self._selectors_fit_their_row("2")


if __name__ == "__main__":
    unittest.main()


class InterfaceLanguage(unittest.TestCase):
    """`ui_language` stops at the terminal no longer.

    The window and every report already honoured the setting; the TUI was
    written in English literals, so choosing Ukrainian changed everything
    except the interface the choice was made in - which is what "the option
    does nothing" looks like from the outside.
    """

    def _app(self, lang):
        import config

        app = XBrainAuditApp()
        app.lang = lang
        return app

    def test_the_menu_is_written_in_the_configured_language(self):
        from i18n.translations import t

        async def body():
            app = self._app("uk")
            async with app.run_test() as pilot:
                await pilot.pause()
                return [button.label.plain
                        for button in app.screen.query(Button)]

        labels = run(body())
        self.assertTrue(any(t("tui_menu_scan", "uk") in text for text in labels),
                        labels)
        self.assertFalse(any("Full Scan" in text for text in labels), labels)

    def test_italian_is_a_different_menu_again(self):
        from i18n.translations import t

        async def body():
            app = self._app("it")
            async with app.run_test() as pilot:
                await pilot.pause()
                return [button.label.plain
                        for button in app.screen.query(Button)]

        labels = run(body())
        self.assertTrue(
            any(t("tui_menu_audit", "it") in text for text in labels), labels)

    def test_the_footer_hints_are_translated_too(self):
        from i18n.translations import t

        async def body():
            app = self._app("uk")
            async with app.run_test() as pilot:
                await pilot.pause()
                mapping = app.screen._bindings.key_to_bindings
                return [b.description for bindings in mapping.values()
                        for b in bindings]

        descriptions = run(body())
        self.assertIn(t("tui_quit", "uk"), descriptions)
        self.assertNotIn("Quit", descriptions)

    def test_changing_the_language_rebuilds_the_screens_in_it(self):
        """Saved and not applied, the language is an option that appears to
        do nothing until the next launch."""
        from i18n.translations import t

        async def body():
            app = self._app("en")
            async with app.run_test() as pilot:
                await pilot.pause()
                app.set_language("uk")
                await pilot.pause()
                return app.lang, app.sub_title, [button.label.plain
                                                 for button in app.screen.query(Button)]

        lang, subtitle, labels = run(body())
        self.assertEqual(lang, "uk")
        from i18n.translations import t
        import config
        self.assertEqual(subtitle, t("tui_subtitle", "uk",
                                     version=config.APP_VERSION))
        self.assertTrue(any(t("tui_save", "uk") == text for text in labels),
                        labels)

    def test_confirmation_buttons_follow_the_interface_language(self):
        from i18n.translations import LANGUAGES, t
        from tui.screens.confirm import ConfirmModal

        async def body():
            result = {}
            for lang in LANGUAGES:
                app = XBrainAuditApp()
                app.lang = lang
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    app.push_screen(ConfirmModal("Question"))
                    await pilot.pause()
                    result[lang] = (
                        app.screen.query_one("#confirm-yes", Button).label.plain,
                        app.screen.query_one("#confirm-no", Button).label.plain,
                    )
            return result

        labels = run(body())
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                self.assertEqual(labels[lang],
                                 (t("tui_yes", lang), t("tui_no", lang)))

    def test_the_language_it_starts_in_is_the_saved_one(self):
        import config

        with mock.patch.object(config.Settings, "load",
                               staticmethod(lambda: config.Settings(ui_language="it"))):
            app = XBrainAuditApp()
        self.assertEqual(app.lang, "it")


class NoDecorativeControls(unittest.TestCase):
    """Every control on a form has to reach the command it belongs to.

    The defect this pins: the audit screen's "Browser rendering" checkbox
    was sent as `browser=`, and the command reads `no_browser` - so the box
    was decorative and the browser pass ran whether or not it was ticked. A
    control that changes nothing is worse than a missing one: it is a
    promise the run does not keep.
    """

    #: Form screen -> the files its command's arguments are read in.
    SOURCES = {
        "scan": ("cli.py", "cli_impl/scanning.py"),
        "audit": ("cli.py", "cli_impl/auditpass.py"),
        "fullscan": ("cli_impl/fullscan.py", "cli_impl/auditpass.py",
                     "cli_impl/scanning.py"),
    }

    def _sent(self, form):
        import re

        source = Path(f"tui/screens/{form}.py").read_text(encoding="utf-8")
        # `name=self.query_one("#widget", …)`, with or without a `not` in
        # front of it, which is how a positive control feeds a negative flag.
        return dict(re.findall(
            r"^\s+(\w+)=(?:not )?self\.query_one\(\"#([\w-]+)\"", source,
            re.M))

    def _read(self, form):
        import re

        names = set()
        for path in self.SOURCES[form]:
            text = Path(path).read_text(encoding="utf-8")
            names |= set(re.findall(r"args\.(\w+)", text))
            names |= set(re.findall(r'getattr\(args, "(\w+)"', text))
        return names

    def test_every_form_control_is_read_by_its_command(self):
        for form in self.SOURCES:
            with self.subTest(form=form):
                sent = self._sent(form)
                read = self._read(form)
                dead = {name: widget for name, widget in sent.items()
                        if name not in read}
                self.assertEqual(dead, {},
                                 f"{form}: these controls reach nothing")

    def test_the_audit_browser_box_reaches_the_browser_pass(self):
        sent = self._sent("audit")
        self.assertIn("no_browser", sent)
        self.assertEqual(sent["no_browser"], "browser")


class NothingUntranslated(unittest.TestCase):
    """No screen may put an English literal in front of a person.

    The Ukrainian pass covered the labels first and the *dynamic* text - the
    table heads, the statuses, the detail block - a commit later, which is
    how a screen ends up half in one language. This reads the source rather
    than the running app: a literal handed to a widget is the defect whether
    or not a test happens to open that screen.

    Parsed rather than grepped: a regex over the line cannot tell the label
    of a button from the id beside it.
    """

    #: Calls whose visible arguments are read by a person.
    SPEAKING = {"Label", "Button", "Static", "Checkbox", "add_columns",
                "add_row", "update"}

    #: Strings that are the same in every language, or are not sentences.
    ALLOWED = {"XBrain Audit", "ok", "-", "?", "·", ""}

    def _offences(self, path):
        import ast

        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        found = []

        def visible(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                if text in self.ALLOWED or not text.strip():
                    return
                if not any(ch.isalpha() for ch in text):
                    return
                found.append((node.lineno, text))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (node.func.attr if isinstance(node.func, ast.Attribute)
                        else getattr(node.func, "id", ""))
                if name in self.SPEAKING:
                    for argument in node.args:
                        visible(argument)
                for keyword in node.keywords:
                    if keyword.arg == "placeholder":
                        visible(keyword.value)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "label":
                        visible(node.value)
        return found

    def test_no_screen_speaks_english_directly(self):
        for path in sorted(Path("tui/screens").glob("*.py")):
            with self.subTest(screen=path.name):
                self.assertEqual(self._offences(path), [],
                                 f"{path}: untranslated text")


class TheFooterIsInTheInterfaceLanguage(unittest.TestCase):
    """Textual namespaces its own bindings (`app.focus_next`,
    `screen.copy_text`), and the prefix was not stripped before the label
    lookup - so six footer hints stayed English on every screen while the
    screens' own bindings translated fine. `only_errors` and `show_all` were
    simply missing from the table.
    """

    def test_no_footer_hint_is_left_in_english(self):
        """Compared against the table, not against "does it look English".

        An earlier version of this asserted the description was non-ASCII,
        which passes in Ukrainian and fails the moment another test leaves
        the interface language as English - where the correct translation is
        ASCII English.
        """
        from i18n.translations import t
        from tui.screens.base import BINDING_LABELS
        from tui.screens.logs import LogsScreen

        async def body():
            # Through `set_language`, inside the app context, which is the
            # production path: it re-translates the app's own bindings too.
            # Setting `app.lang` directly does not, so this test read whatever
            # language the app happened to be *constructed* in - and in a full
            # suite run that was Italian, left over from a neighbouring test.
            # A test that depends on the order it runs in is not a test.
            app = XBrainAuditApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.set_language("uk")
                await pilot.pause()
                app.push_screen(LogsScreen())
                await pilot.pause()
                found = []
                for source in (app.screen._bindings, app._bindings):
                    mapping = getattr(source, "key_to_bindings", {})
                    for bindings in mapping.values():
                        found.extend((b.action, b.description) for b in bindings)
                return found, app.lang

        rows, language = run(body())
        wrong = []
        for action, text in rows:
            key = BINDING_LABELS.get((action or "").split("(")[0].rsplit(".", 1)[-1])
            if key and text and text != t(key, language):
                wrong.append((action, text, t(key, language)))
        self.assertEqual(wrong, [])

        # And every footer action this screen has is in the table at all -
        # the six that stayed English were missing from it, or namespaced.
        unmapped = [a for a, _ in rows
                    if a and not a.endswith("help_quit")
                    and (a.split("(")[0].rsplit(".", 1)[-1] not in BINDING_LABELS)
                    and not a.startswith("go(")]
        self.assertEqual(unmapped, [])

    def test_a_namespaced_action_finds_its_label(self):
        from tui.screens.base import BINDING_LABELS

        for action in ("focus_next", "copy_text", "only_errors", "show_all",
                       "command_palette"):
            with self.subTest(action):
                self.assertIn(action, BINDING_LABELS)
