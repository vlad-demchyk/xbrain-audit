"""What a run found, shown here rather than deferred to the terminal.

Every form used to end with "See results in terminal", which was not true:
the interface owns the terminal while it runs, so the JSON either vanished
or drew over the screen. The result is captured (`tui.runner`) and laid out
here - a summary, the documents that were written, and the full log for
anything the summary does not cover.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, RichLog, Static

from i18n.translations import t

from tui.screens.base import XScreen

#: Severity name -> the theme variable painting its step of the four-level
#: ramp (`ui.theme.build_textual_theme`, itself the same four fields
#: `ui.widgets.SeverityBar` paints in the Qt window). Before this, every
#: severity in this table was the table's default foreground - "27 critical"
#: and "27 minor" read as the same colour, which is the defect the ramp
#: exists to fix, and it reached the summary table but not this one.
_SEVERITY_VARIABLE = {
    "critical": "sev-critical",
    "serious": "sev-high",
    "moderate": "sev-medium",
    "minor": "sev-none",
}

#: The same four steps as a mark, for terminals that cannot show four
#: colours. Measured (`P-11`): the dark palette's ramp is `#d97a72`,
#: `#d89874`, `#cfae66`, `#5f5a53`, and on a 16-colour terminal those become
#: ANSI 9, **7**, **7**, 8 - `serious` and `moderate` land on the same white,
#: so four steps read as three and the two in the middle are indistinguishable.
#: At 256 colours all four differ (173, 174, 179, 240).
#:
#: A mark rather than a different colour, because the colours come from the
#: design system (`ui/tokens.py` parses it, `ui/theme.py` paints with it) and
#: picking a new one here to dodge an ANSI collision would put this file at
#: odds with the artboard. The mark also happens to be what a person who
#: cannot distinguish these hues needs, on any terminal.
_SEVERITY_MARK = {
    "critical": "!!!",
    "serious": "!!",
    "moderate": "!",
    "minor": "\u00b7",
}


def _ramp_is_legible(app) -> bool:
    """Can this terminal show the four steps as four colours?

    Asked of the live console rather than assumed, because the answer is a
    property of where the program is running - the same build is fine over a
    modern terminal and flat over `TERM=xterm`. Anything short of 256 colours
    collapses `serious` into `moderate`; `truecolor` and `256` are fine.
    """
    console = getattr(app, "console", None)
    name = str(getattr(console, "color_system", "") or "")
    return name in ("256", "truecolor", "windows")


def open_in_os(path: str, lang: str = "uk") -> str:
    """Hand a file or folder to the desktop. Returns a message for the user.

    A report the tool just wrote is only useful if it can be opened, and the
    interface cannot render a PDF. Nothing is sent anywhere - this is the
    same double-click the person would do themselves.
    """
    target = Path(path)
    if not target.exists():
        return t("tui_open_gone", lang, path=path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        elif os.name == "nt":  # pragma: no cover - not the supported platform
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except OSError as exc:
        return t("tui_open_failed", lang, error=exc)
    return t("tui_opened", lang, name=target.name)


#: Worst first, and the order the rows are laid out in. Named once because
#: three places have to agree on it: the ramp, the mark, and this ordering.
SEVERITIES = ("critical", "serious", "moderate", "minor")

_SUMMARY_DETECTOR_KEYS = {
    "offline": "tui_detector_offline",
    "heuristic": "tui_detector_heuristic",
    "unicode-anomalies": "tui_detector_unicode_anomalies",
    "hybrid": "tui_detector_hybrid",
    "embedding": "tui_detector_embedding",
    "claude-llm-judge": "tui_detector_claude",
    "claude-code-llm-judge": "tui_detector_claude_code",
    "xformat-llm-judge": "tui_detector_xformat",
}


def summary_label(label: str, lang: str) -> str:
    """Translate result labels, including dynamic detector and severity rows."""
    if label.startswith("by "):
        detector = label[3:]
        key = _SUMMARY_DETECTOR_KEYS.get(detector)
        name = t(key, lang) if key else detector
        return t("tui_sum_by", lang, detector=name)
    if label.startswith("audit "):
        severity = label[6:]
        name = t(f"severity_{severity}", lang)
        if name.startswith("severity_"):
            name = severity
        return t("tui_sum_audit_severity", lang, severity=name)
    key = f"tui_sum_{label.replace(' ', '_')}"
    translated = t(key, lang)
    return translated if translated != key else label


def summary_rows(payload: dict | None) -> list:
    """`(label, value)` pairs for whichever command produced this payload.

    The three commands print three different documents. Rather than a branch
    per command, each known shape contributes the rows it has - a payload
    from a future command still renders, just with fewer rows.
    """
    if not payload:
        return []
    rows: list = []
    summary = payload.get("summary")
    audit_counts = (payload.get("audit") or {}).get("category_problems")
    if isinstance(summary, dict):
        # fullscan: one document covering both passes.
        for key in ("total_findings", "ai_patterns", "characters",
                    "accessibility", "seo", "performance", "best_practices"):
            if key in summary:
                if isinstance(audit_counts, dict) and key == "total_findings":
                    rows.append(("distinct problems", str(summary["distinct_problems"])))
                    rows.append(("occurrences", str(summary[key])))
                elif isinstance(audit_counts, dict) and key in (
                        "accessibility", "seo", "performance", "best_practices"):
                    rows.append((key.replace("_", " "),
                                 str(audit_counts.get(key.replace('_', '-'), 0))))
                else:
                    rows.append((key.replace("_", " "), str(summary[key])))
    counts = payload.get("counts")
    if isinstance(counts, dict):
        # `counts` carries two different shapes. `scan` fills it with one key
        # per detector; `audit` fills it with one key per severity. The rows
        # below take each shape once - the severity names are excluded from
        # the "by ..." pass precisely because the pass after it owns them.
        #
        # Without that exclusion every audit run listed its four numbers
        # twice, as "by critical" and again as "critical". It was invisible
        # from a `scan` payload, which has no severity key at all, and the
        # test that covered this screen used a hand-written payload rather
        # than one the CLI produces.
        for key in ("total", "distinct", "files"):
            if key in counts:
                rows.append((key, str(counts[key])))
        for key, value in counts.items():
            if key not in ("total", "distinct", "files") and key not in SEVERITIES:
                rows.append((f"by {key}", str(value)))
        for severity in SEVERITIES:
            if severity in counts:
                rows.append((severity, str(counts[severity])))
    # An `audit` payload counts distinct problems and says so beside the
    # number of places they were found: the severity rows above are the former.
    if isinstance(payload.get("distinct"), int) and isinstance(payload.get("occurrences"), dict):
        rows.append(("distinct problems", str(payload["distinct"])))
        rows.append(("occurrences", str(sum(payload["occurrences"].values()))))
    audit = payload.get("audit")
    if isinstance(audit, dict) and isinstance(audit.get("counts"), dict):
        for severity, value in audit["counts"].items():
            rows.append((f"audit {severity}", str(value)))
    if "target" in payload:
        rows.insert(0, ("target", str(payload["target"])))
    return rows


class ResultsScreen(XScreen):
    """Summary, documents written, and the full log of one run."""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("o", "open_first", "Open report"),
    ]

    def __init__(self, title: str, result) -> None:
        super().__init__()
        self._title = title
        self._result = result
        self._paths = result.report_paths()

    def compose(self) -> ComposeResult:
        yield from self.compose_chrome()
        with Vertical(id="results-view"):
            yield Label(self.tr("tui_result_title", title=self._title),
                        classes="menu-title")
            yield Label(self.tr("tui_exit_code", code=self._result.exit_code),
                        id="results-exit")
            yield DataTable(id="results-summary")
            yield Static("")
            yield Label("", id="results-paths")
            with Horizontal(id="results-actions"):
                yield Button(self.tr("tui_open_report"), id="open-report", variant="primary")
                yield Button(self.tr("tui_open_folder"), id="open-folder")
                yield Button(self.tr("tui_back"), id="back")
            yield Label("", id="report-status")
            yield RichLog(id="results-log", highlight=False, markup=False,
                          wrap=True)

    def on_mount(self) -> None:
        table = self.query_one("#results-summary", DataTable)
        table.add_columns(self.tr("tui_col_what"), self.tr("tui_col_count"))
        rows = summary_rows(self._result.payload())
        if rows:
            variables = self.app.get_css_variables()
            marked = not _ramp_is_legible(self.app)
            for label, value in rows:
                # The payload's keys are machine names; the table is read by
                # a person, so each one is said in their language and falls
                # back to the raw key when a command grows a new field.
                shown = summary_label(label, self.lang)
                table.add_row(
                    self._severity_cell(label, variables, shown, marked=marked),
                    value)
        else:
            table.add_row(self.tr("tui_no_summary"), "-")

        paths = self.query_one("#results-paths", Label)
        if self._paths:
            paths.update(self.tr("tui_written") + "\n"
                         + "\n".join(f"  {p}" for p in self._paths))
        else:
            paths.update(self.tr("tui_nothing_written"))
        self.query_one("#open-report", Button).disabled = not self._file_paths()
        self.query_one("#open-folder", Button).disabled = not self._paths

        log = self.query_one("#results-log", RichLog)
        for line in (self._result.stderr.splitlines()
                     + self._result.stdout.splitlines()):
            log.write(line)

    @staticmethod
    def _severity_cell(label: str, variables: dict,
                       shown: str | None = None,
                       marked: bool = False) -> Text | str:
        """`shown` painted in `label`'s step of the ramp, or left unpainted.

        The severity is matched on the payload's own key, not on the words
        the person reads: the label is translated by the time it reaches the
        table, and matching on a translated word would paint the ramp in one
        language and nothing in the other two.

        Matched on the last word rather than the whole key, because a row can
        read "critical" (scan) or "audit critical" (audit) for the same
        severity - see `summary_rows`, which reconciles the two shapes.

        `marked` prefixes the step's mark, for a terminal whose palette
        cannot keep the four steps apart. Set from `_ramp_is_legible`, not
        from a setting: the person should not have to know why two rows look
        the same before they can fix it.
        """
        text = label if shown is None else shown
        last_word = label.rsplit(" ", 1)[-1]
        if marked and last_word in _SEVERITY_MARK:
            text = f"{_SEVERITY_MARK[last_word]} {text}"
        variable = _SEVERITY_VARIABLE.get(last_word)
        if variable is None or variable not in variables:
            return text
        return Text(text, style=variables[variable])

    def _file_paths(self) -> list:
        return [p for p in self._paths if Path(p).is_file()]

    def _folder(self) -> str:
        for path in self._paths:
            candidate = Path(path)
            if candidate.is_dir():
                return str(candidate)
        files = self._file_paths()
        return str(Path(files[0]).parent) if files else ""

    def action_open_first(self) -> None:
        files = self._file_paths()
        if files:
            self.query_one("#report-status", Label).update(open_in_os(files[0], self.lang))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_back()
        elif event.button.id == "open-report":
            self.action_open_first()
        elif event.button.id == "open-folder":
            folder = self._folder()
            if folder:
                self.query_one("#report-status", Label).update(
                    open_in_os(folder, self.lang))
