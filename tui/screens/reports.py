"""Reports screen — list, read and open previous analysis reports.

Clicking a row used to do nothing at all: the table had no selection
handler, the list was built once and never refreshed, and the history it
read from lived in `.xaudit/` in the working directory - so starting
`xaudit` from anywhere else showed "No reports found" even when there were
dozens. All three are fixed here; the history itself moved to
`~/.xbrain-audit/history/` (see `cli_impl.reports._history_dir`).
"""
from __future__ import annotations

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label

from tui.cells import AUTO_HEIGHT, folded

from i18n.translations import t

from tui.screens.base import XScreen
from tui.screens.results import open_in_os


def _history_files() -> list:
    """Every history file worth reading, new location first.

    The legacy per-working-directory store is still read so a history
    recorded before the move is not invisible.
    """
    import app_identity
    from cli_impl.reports import _history_dir

    paths = []
    for directory in (_history_dir(),
                      app_identity.project_history_dir(Path.cwd())):
        if directory.is_dir():
            paths.extend(sorted(directory.glob("*.json")))
    return paths


def load_runs() -> list:
    """Every recorded run, newest first.

    Each history file holds the runs of one target, so all of them are read
    and merged rather than only the newest entry of each - the point of the
    screen is the history, and showing one row per file threw it away.
    """
    runs = []
    for path in _history_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, list):
            continue
        runs.extend(entry for entry in data if isinstance(entry, dict))
    seen = set()
    unique = []
    for run in sorted(runs, key=lambda r: r.get("at") or "", reverse=True):
        key = (run.get("at"), run.get("root"), run.get("mode"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(run)
    return unique


def _total(run: dict) -> int:
    counts = run.get("counts")
    return sum(counts.values()) if isinstance(counts, dict) else 0


class ReportsScreen(XScreen):
    """Previous runs, and the documents they wrote."""

    AUTO_FOCUS = "#reports-table"

    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "refresh", "Refresh"),
        ("o", "open_selected", "Open report"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._runs: list = []

    def compose(self) -> ComposeResult:
        yield from self.compose_chrome()
        with Vertical(id="reports-view"):
            yield Label(self.tr("tui_reports_title"), classes="menu-title")
            yield DataTable(id="reports-table", cursor_type="row")
            yield Label("", id="report-detail")
            with Horizontal():
                yield Button(self.tr("tui_open_report"), id="open", variant="primary")
                yield Button(self.tr("tui_open_folder"), id="open-folder")
                yield Button(self.tr("tui_refresh"), id="refresh")
                yield Button(self.tr("tui_back"), id="back")
            yield Label("", id="report-status")
            yield Label(self.tr("tui_reports_hint"), classes="hint")

    def on_mount(self) -> None:
        table = self.query_one("#reports-table", DataTable)
        table.add_columns(self.tr("tui_col_when"), self.tr("tui_col_target"),
                          self.tr("tui_col_mode"), self.tr("tui_col_findings"),
                          self.tr("tui_col_problems"))
        self.action_refresh()

    def on_screen_resume(self) -> None:
        """Rebuild on every visit.

        Screens are installed once and reused, so `on_mount` runs exactly
        once - the list a person saw after their first scan was the list
        they kept seeing after every later one.
        """
        self.action_refresh()

    def action_refresh(self) -> None:
        table = self.query_one("#reports-table", DataTable)
        table.clear()
        self._runs = load_runs()
        if not self._runs:
            self.query_one("#report-status", Label).update(
                self.tr("tui_reports_empty"))
            self._enable_actions(False)
            return
        for run in self._runs[:200]:
            distinct = run.get("distinct")
            # The target was kept as its *last* 46 characters, which drops
            # the domain: three runs against three different sites all read
            # as rows beginning with "...". It folds now - see `tui.cells`.
            table.add_row(
                folded((run.get("at") or "?").replace(" UTC", "")),
                folded(run.get("root") or "?"),
                folded(self._display_mode(run.get("mode"))),
                folded(_total(run)),
                folded("-" if distinct is None else distinct),
                height=AUTO_HEIGHT,
            )
        self.query_one("#report-status", Label).update(
            self.tr("tui_reports_count", n=len(self._runs)))
        self._show_detail(0)

    def _display_mode(self, mode: str | None) -> str:
        if not mode:
            return "?"
        key = {"web": "source_site", "repo": "source_repo",
               "file": "source_file"}.get(mode, f"tui_mode_{mode}")
        translated = self.tr(key)
        return translated if translated != key else mode

    def _enable_actions(self, enabled: bool) -> None:
        self.query_one("#open", Button).disabled = not enabled
        self.query_one("#open-folder", Button).disabled = not enabled

    def _selected(self) -> dict | None:
        table = self.query_one("#reports-table", DataTable)
        index = table.cursor_row
        if index is None or not (0 <= index < len(self._runs)):
            return None
        return self._runs[index]

    def _show_detail(self, index: int) -> None:
        if not (0 <= index < len(self._runs)):
            return
        run = self._runs[index]
        counts = run.get("counts") or {}
        report = run.get("report") or ""
        exists = report and Path(report).exists()
        lines = [
            f"{run.get('root', '?')}  ·  {self._display_mode(run.get('mode'))}",
            "  ".join(
                f"{t('severity_' + level, self.lang)} {counts.get(level, 0)}"
                for level in ("critical", "serious", "moderate", "minor")),
            self.tr("tui_report_examined",
                    documents=run.get("documents", "?"),
                    fixed=run.get("fixed", 0)),
        ]
        if report:
            lines.append(self.tr("tui_report_path", path=report)
                         + ("" if exists else self.tr("tui_report_gone")))
        else:
            # Runs recorded before the report path was stored.
            lines.append(self.tr("tui_report_unrecorded"))
        self.query_one("#report-detail", Label).update("\n".join(lines))
        self._enable_actions(bool(exists))

    def on_data_table_row_highlighted(
            self, event: DataTable.RowHighlighted) -> None:
        self._show_detail(event.cursor_row)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter, or a click, opens the report - the thing a row is for."""
        self._show_detail(event.cursor_row)
        self.action_open_selected()

    def action_open_selected(self) -> None:
        run = self._selected()
        status = self.query_one("#report-status", Label)
        if run is None:
            status.update(self.tr("tui_nothing_selected"))
            return
        report = run.get("report")
        if not report:
            status.update(self.tr("tui_no_report_path"))
            return
        status.update(open_in_os(report, self.lang))

    def action_open_folder(self) -> None:
        run = self._selected()
        status = self.query_one("#report-status", Label)
        report = (run or {}).get("report")
        if not report:
            status.update(self.tr("tui_no_folder"))
            return
        status.update(open_in_os(str(Path(report).parent), self.lang))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_back()
        elif event.button.id == "refresh":
            self.action_refresh()
        elif event.button.id == "open":
            self.action_open_selected()
        elif event.button.id == "open-folder":
            self.action_open_folder()
