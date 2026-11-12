"""The catalogue of runs: what is on disk, and what can be continued.

A full scan of a large site is a three-quarter-hour job, and it can stop for
reasons that have nothing to do with the target - a wedged renderer, a laptop
closing, someone wanting their machine back. Before this the interface had no
idea any of that had happened: a stopped run was simply gone, and the only
evidence was a folder in Documents nobody was told about.

The list is built by walking the run folders, the same walk `xaudit runs`
does, and not from a registry the interface keeps of its own. One fact, one
owner: a registry would be a second answer to "what runs exist", it would be
the one that went stale the moment a folder was moved by hand, and the CLI and
the GUI would then disagree about the same disk.

Artboard 3c turns it from a list into a table, and the reason is the action
column. A row used to carry Resume and Pause side by side, and one of the two
was always wrong for it - a finished run cannot be paused and a running one
cannot be resumed, so half the buttons on screen existed to be refused. Now
each row offers the one thing its state actually allows, spelled as a word,
and everything else moves behind a "..." menu. What a row can do is a
property of the row, not a fixed pair of controls repeated down the column.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from i18n.translations import t
from ui import theme
from ui.widgets import muted

#: How many runs the panel lists. The catalogue is for continuing recent work,
#: not for browsing history - that is what the folders on disk are.
_RUNS_SHOWN = 12

#: The state of a run, as a mark and an ink. Read at a glance down a column
#: or not at all: five rows of five words is five readings.
_STATE_MARK = {
    "running": "\u25cf",
    "paused": "\u25d0",
    "done": "\u2713",
    "failed": "\u2715",
    "interrupted": "\u2715",
}
_STATE_INK = {
    "running": "accent",
    "paused": "amber_text",
    "done": "success_text",
    "failed": "error_text",
    "interrupted": "error_text",
}

#: Column widths, in pixels, shared by the head and every row. Fixed rather
#: than left to each layout's own stretch: a head and a row are two separate
#: layouts, so matching stretch factors line them up only as long as the
#: content happens to be the same width - the moment one row holds "complete"
#: and the next "interrupted", the heads sit over the wrong columns.
_COL_STATE, _COL_FOUND, _COL_WHEN = 120, 56, 76

#: Which single action a row offers, by state. The one thing that state
#: actually allows; everything else is in the menu.
_PRIMARY = {
    "running": "pause",
    "paused": "resume",
    "failed": "resume",
    "interrupted": "resume",
    "done": "report",
}


class RunRow(QWidget):
    """One run: what it was, how it went, and the one thing to do with it."""

    def __init__(self, row: dict, palette, lang: str, panel, widths=None,
                 parent=None):
        super().__init__(parent)
        self.row = row
        widths = widths or {"state": _COL_STATE, "found": _COL_FOUND,
                            "when": _COL_WHEN}
        self.palette_ = palette
        self.lang = lang
        self.panel = panel

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(8)

        target = QWidget()
        target_column = QVBoxLayout(target)
        target_column.setContentsMargins(0, 0, 0, 0)
        target_column.setSpacing(0)
        self.target_label = QLabel(_short_target(row.get("target", "")))
        target_column.addWidget(self.target_label)
        self.subtitle = QLabel(_subtitle(row, lang))
        self.subtitle.setProperty("class", theme.CLASS_MUTED)
        target_column.addWidget(self.subtitle)
        layout.addWidget(target, stretch=1)

        state = QWidget()
        state.setFixedWidth(widths["state"])
        state_column = QVBoxLayout(state)
        state_column.setContentsMargins(0, 0, 0, 0)
        state_column.setSpacing(0)
        self.state_label = QLabel(_state_text(row, lang))
        state_column.addWidget(self.state_label)
        # Under the state rather than in a column of its own: where a run
        # stopped is only a question about a run that stopped, and giving it
        # a column of its own means a blank cell on every finished row and
        # eighty pixels the table does not have.
        self.stage_label = QLabel(_stage_text(row, lang))
        self.stage_label.setProperty("class", theme.CLASS_MUTED)
        self.stage_label.setVisible(bool(self.stage_label.text()))
        state_column.addWidget(self.stage_label)
        layout.addWidget(state)

        self.found_label = QLabel(_found_text(row))
        self.found_label.setProperty("class", theme.CLASS_MUTED)
        self.found_label.setFixedWidth(widths["found"])
        self.found_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                      | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.found_label)

        self.age_label = QLabel(row.get("age", ""))
        self.age_label.setProperty("class", theme.CLASS_MUTED)
        self.age_label.setFixedWidth(widths["when"])
        self.age_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                    | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.age_label)

        self.primary_btn = QPushButton(_primary_text(row, lang))
        self.primary_btn.clicked.connect(self._on_primary)
        layout.addWidget(self.primary_btn)

        self.more_btn = QPushButton("\u2026")
        self.more_btn.setToolTip(t("runs_more", lang))
        self.more_btn.setProperty("class", theme.CLASS_QUIET)
        self.more_btn.clicked.connect(self._on_more)
        layout.addWidget(self.more_btn)

        self.setToolTip(f"{row.get('target', '')}\n{row.get('run', '')}")
        self.apply_palette(palette)

    def _on_primary(self) -> None:
        action = _PRIMARY.get(self.row.get("status", ""), "report")
        {"pause": self.panel.pause_run,
         "resume": self.panel.resume_run,
         "report": self.panel.open_run}[action](self.row)

    def menu(self) -> QMenu:
        """Everything the row can do that is not its one obvious move.

        A menu rather than more buttons: the actions differ per row, and a
        column of controls that changes shape from row to row is harder to
        read than a column of one. Built here and shown by `_on_more`, so
        what a row offers can be asked without opening anything - a test
        that has to `exec` a menu to read it blocks on the event loop.
        """
        menu = QMenu(self)
        menu.addAction(t("runs_open", self.lang),
                       lambda: self.panel.open_run(self.row))
        if self.row.get("resumable"):
            menu.addAction(t("runs_resume", self.lang),
                           lambda: self.panel.resume_run(self.row))
        if self.row.get("status") == "running":
            menu.addAction(t("runs_pause", self.lang),
                           lambda: self.panel.pause_run(self.row))
        return menu

    def _on_more(self) -> None:
        self.menu().exec(self.more_btn.mapToGlobal(
            self.more_btn.rect().bottomLeft()))

    def apply_palette(self, palette) -> None:
        self.palette_ = palette
        ink = getattr(palette, _STATE_INK.get(self.row.get("status", ""), ""),
                      palette.text_muted)
        self.state_label.setStyleSheet(f"color: {ink};")


def _short_target(target: str) -> str:
    """From the left: an address is recognised by its tail."""
    #: Characters kept. Short, because the column is narrow at every width
    #: and this list holds runs of the *same* project more often than not.
    limit = 22
    if len(target) <= limit:
        return target
    return "\u2026" + target[-(limit - 1):]


def _subtitle(row: dict, lang: str) -> str:
    """What kind of thing was scanned, and how deep."""
    parts = [t("runs_kind_" + row.get("kind", "site"), lang)]
    depth = row.get("depth")
    if depth is not None:
        parts.append(t("runs_depth", lang, n=depth))
    return " \u00b7 ".join(parts)


def _state_text(row: dict, lang: str) -> str:
    status = row.get("status", "")
    # `t` returns the key when it has no entry, so an unrecognised status
    # would print `runs_status_whatever` at the user. The raw word is a
    # worse label but a true one, so it is what an unknown status gets.
    key = f"runs_status_{status}"
    word = t(key, lang)
    if word == key:
        word = status
    mark = _STATE_MARK.get(status, "\u00b7")
    return f"{mark} {word}"


def _stage_text(row: dict, lang: str) -> str:
    """Where the run stopped, for a run that can be continued.

    Empty for anything else. A finished run has no stage worth naming - it
    reached the end - and `run_rows` reports the next pending phase for one,
    which would read as a stage it is still in.
    """
    if not row.get("resumable"):
        return ""
    stage = row.get("stage") or ""
    return "" if stage == "-" else stage


def _found_text(row: dict) -> str:
    """A dash, not a zero, for a run that never recorded a count.

    A crawl that stopped early found nothing *yet*, and "0" says it came
    back clean - which is the opposite of what happened.
    """
    findings = row.get("findings")
    return "-" if findings is None else str(findings)


def _primary_text(row: dict, lang: str) -> str:
    return {"pause": t("runs_pause", lang),
            "resume": t("runs_resume", lang),
            "report": t("runs_report", lang)}[
        _PRIMARY.get(row.get("status", ""), "report")]


class RunsPanel:
    """The runs table in the popup, and the actions a row can take.

    Reads `self.lang`, `self.palette_tokens` and `self.status_bar` from the
    facade, exactly as the other window mixins do.
    """

    def _build_runs_panel(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.palette_tokens.space_1)

        head = QWidget()
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(8)
        self.runs_label = QLabel(t("runs_title", self.lang))
        self.runs_label.setProperty("class", theme.CLASS_HEADING)
        head_row.addWidget(self.runs_label)
        # Said out loud, because it is the answer to "why is a run I deleted
        # gone from here" and to "why does the CLI show the same five".
        self.runs_source = muted(t("runs_source", self.lang))
        head_row.addWidget(self.runs_source)
        head_row.addStretch(1)
        layout.addWidget(head)

        self.runs_head = QWidget()
        head_cols = QHBoxLayout(self.runs_head)
        head_cols.setContentsMargins(0, 0, 0, 0)
        head_cols.setSpacing(8)
        self.runs_columns = {}
        # The same widths the rows use, so the heads stay over their columns
        # whatever the rows happen to contain.
        for key, align in (("target", Qt.AlignmentFlag.AlignLeft),
                           ("state", Qt.AlignmentFlag.AlignLeft),
                           ("found", Qt.AlignmentFlag.AlignRight),
                           ("when", Qt.AlignmentFlag.AlignRight)):
            label = QLabel()
            label.setProperty("class", theme.CLASS_FIELD_LABEL)
            label.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            head_cols.addWidget(label, stretch=1 if key == "target" else 0)
            self.runs_columns[key] = label
        # Empty, to reserve exactly the width the action column takes in a
        # row. Without it every head sits one column to the right of the
        # data it names.
        self.runs_action_spacer = QLabel()
        head_cols.addWidget(self.runs_action_spacer)
        layout.addWidget(self.runs_head)

        self.runs_rows = QWidget()
        self.runs_rows_layout = QVBoxLayout(self.runs_rows)
        self.runs_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.runs_rows_layout.setSpacing(0)
        # Scrolled rather than capped in height: twelve rows is taller than
        # the popup wants to be on a small screen, and a list that is simply
        # cut off hides exactly the oldest runs, which are the ones someone
        # opened this to find.
        self.runs_scroll = QScrollArea()
        self.runs_scroll.setWidgetResizable(True)
        self.runs_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.runs_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.runs_scroll.setMaximumHeight(260)
        self.runs_scroll.setWidget(self.runs_rows)
        layout.addWidget(self.runs_scroll)

        self.runs_empty = muted(t("runs_empty", self.lang))
        layout.addWidget(self.runs_empty)

        self.runs_footer = muted("")
        self.runs_footer.setWordWrap(True)
        layout.addWidget(self.runs_footer)

        self._retranslate_run_columns()
        self.refresh_runs()
        return box

    def _retranslate_run_columns(self) -> None:
        """Label the columns, and let the labels decide how wide they are.

        Measured rather than fixed, because a head is the widest thing in
        its column: `ЗНАХІДОК` is half again the width of `FOUND`, and a
        column sized for the English word rendered the Ukrainian one as
        `АХІДОК` - a clipped head over correct data, which reads as data
        that is wrong.
        """
        designed = {"state": _COL_STATE, "found": _COL_FOUND, "when": _COL_WHEN}
        self._col_widths = {}
        for key, label in self.runs_columns.items():
            label.setText(t(f"runs_col_{key}", self.lang))
            if key == "target":
                continue
            width = max(designed[key], label.sizeHint().width())
            label.setFixedWidth(width)
            self._col_widths[key] = width

    # ------------------------------------------------------------ refreshing
    def refresh_runs(self) -> int:
        """Re-read the run folders. Returns how many rows are listed."""
        from cli_impl import runfolder, runstate
        from cli_impl.runcmds import run_rows

        try:
            all_rows = run_rows(runstate.all_runs())
        except Exception:  # noqa: BLE001 - an unreadable disk is not a crash
            all_rows = []
        rows = all_rows[:_RUNS_SHOWN]

        while self.runs_rows_layout.count():
            item = self.runs_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Unparented before deleting: `deleteLater` only schedules
                # it, so the previous refresh's rows would stay on screen
                # underneath the new ones.
                widget.setParent(None)
                widget.deleteLater()
        self._run_rows = []
        for row in rows:
            widget = RunRow(row, self.palette_tokens, self.lang, self,
                            getattr(self, "_col_widths", None))
            self._run_rows.append(widget)
            self.runs_rows_layout.addWidget(widget)

        self._align_action_column()
        # The rows live in a scroll area with no horizontal scrollbar, so a
        # scroll area narrower than its content simply clips it - and what
        # is on the right is the action column, the half of a row that does
        # anything. Asked of the content rather than assumed.
        self.runs_scroll.setMinimumWidth(self.runs_rows.sizeHint().width())
        self.runs_scroll.setVisible(bool(rows))
        self.runs_head.setVisible(bool(rows))
        self.runs_empty.setVisible(not rows)
        # Named, because the list is a window onto the disk and not the whole
        # of it - and because the folder is where the rest actually is.
        self.runs_footer.setText(
            t("runs_footer", self.lang, shown=len(rows),
              root=str(runfolder.default_root())) if rows else "")
        self.runs_footer.setVisible(bool(rows))
        return len(rows)

    def _align_action_column(self) -> None:
        """One width for every primary button, and a head spacer to match.

        The word differs per row - Pause, Resume, Report - and per language,
        so left to their own size hints the buttons form a ragged right edge
        and the column heads sit over nothing in particular. Measured rather
        than guessed at: "Продовжити" and "Report" are not the same width,
        and a hard-coded number would be right in one language.
        """
        rows = getattr(self, "_run_rows", ())
        if not rows:
            self.runs_action_spacer.setFixedWidth(0)
            return
        width = max(widget.primary_btn.sizeHint().width() for widget in rows)
        more = max(widget.more_btn.sizeHint().width() for widget in rows)
        for widget in rows:
            widget.primary_btn.setFixedWidth(width)
            widget.more_btn.setFixedWidth(more)
        self.runs_action_spacer.setFixedWidth(width + more + 8)

    def apply_run_palette(self, palette) -> None:
        for widget in getattr(self, "_run_rows", ()):
            widget.apply_palette(palette)

    # --------------------------------------------------------------- actions
    def open_run(self, row: dict) -> None:
        _open_in_os(Path(row["run"]))

    def pause_run(self, row: dict) -> None:
        from cli_impl import runstate

        state = runstate.RunState.load(Path(row["run"]))
        if state is None:
            return
        state.request_pause()
        self.status_bar.showMessage(t("runs_pause_requested", self.lang))
        self.refresh_runs()

    def resume_run(self, row: dict) -> None:
        """Continue a run, in a worker so the window stays alive.

        The resume re-enters the CLI's own `resume`, which re-enters
        `fullscan` with the recorded invocation. Deliberately the same path
        the terminal takes: a second implementation of "continue this run"
        would be a second set of phase decisions to keep in step.
        """
        if not row.get("resumable"):
            return
        self.status_bar.showMessage(
            t("runs_resuming", self.lang, run=Path(row["run"]).name))
        self._run_resume_worker(row["run"])

    def _run_resume_worker(self, run: str) -> None:
        from PySide6.QtCore import QThread, Signal

        panel = self

        class _Resume(QThread):
            finished_with = Signal(int, str)

            def run(self) -> None:                     # noqa: D102
                try:
                    from cli_impl.runcmds import cmd_resume
                    import argparse

                    code = cmd_resume(argparse.Namespace(run=run, root=None))
                    self.finished_with.emit(int(code), "")
                except Exception as exc:  # noqa: BLE001 - reported, not lost
                    self.finished_with.emit(2, str(exc))

        worker = _Resume()
        worker.finished_with.connect(panel._on_resume_finished)
        # Kept on the window: a QThread that goes out of scope while running
        # is destroyed mid-run, which Qt warns about and which loses the work.
        self._resume_worker = worker
        worker.start()

    def _on_resume_finished(self, code: int, error: str) -> None:
        if error:
            self.status_bar.showMessage(
                t("runs_resume_failed", self.lang, reason=error))
        elif code == 0:
            self.status_bar.showMessage(t("runs_resume_done", self.lang))
        else:
            self.status_bar.showMessage(
                t("runs_resume_incomplete", self.lang))
        self.refresh_runs()

    def _retranslate_runs(self) -> None:
        self.runs_label.setText(t("runs_title", self.lang))
        self.runs_source.setText(t("runs_source", self.lang))
        self.runs_empty.setText(t("runs_empty", self.lang))
        self._retranslate_run_columns()
        # The rows are rebuilt rather than relabelled: every string in one
        # of them is derived from the row's data, so rebuilding is both
        # shorter and the only version that cannot go half-translated.
        self.refresh_runs()


def _open_in_os(path: Path) -> None:
    """Open a folder in Finder/Explorer/the desktop's file manager."""
    import subprocess

    if not path.exists():
        return
    if sys.platform == "darwin":
        command = ["open", str(path)]
    elif sys.platform.startswith("win"):
        command = ["explorer", str(path)]
    else:
        command = ["xdg-open", str(path)]
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        pass
