"""The run as it happens, in a shape an agent can read while it happens.

`--json` answers only at the end. On a thirty-page site that is minutes of
silence, and the thing driving the CLI cannot tell a slow crawl from a hung
one. The human lines on stderr (`# [crawl 3/30] depth=1 …`) were readable
but were never a contract: no schema, no event type, and no promise the
wording would survive the next edit.

`--progress jsonl` turns those same points into one JSON object per line on
stderr. **The same points**, not a second set: every call here prints either
the human line or the object, from one call site with one set of values, so
the two cannot drift into describing different runs. Without the flag
nothing changes - the human line is what gets printed, byte for byte what it
was before.

Every object carries `event` (one of `EVENTS`) and `ts` (UTC, ISO 8601).
`finding` is off unless asked for (`--progress jsonl=findings`): a large site
produces tens of thousands of them, and a progress stream that is mostly
findings is a report, not progress.

Like `applog`, nothing here may break a run: every public function swallows
its own errors. A progress stream that can kill a scan is worse than none.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import app_identity

#: Every event name this module will ever emit. The list is the contract:
#: `tests/test_progress_protocol.py` runs real commands and fails on any line
#: whose `event` is not here, so adding an event means adding it here first.
EVENTS = (
    "run.start",
    "stage",
    "page",
    "file",
    "notice",
    "finding",
    "run.end",
)

#: `--progress` spellings. `human` is the default and is what every run did
#: before this module existed.
MODE_HUMAN = "human"
MODE_JSONL = "jsonl"

#: Stage names. A stage is a phase of work the run can be inside of, and the
#: set is small on purpose: an agent switches on it.
STAGES = ("devserver", "scan", "crawl", "audit", "browser", "report")

#: `stage.state`. `progress` is a stage saying it is still working and how
#: far along - batches of a judged scan, for one - which is neither a begin
#: nor an end and would be a lie as either.
STAGE_STATES = ("begin", "progress", "end")

#: `notice.kind` values. These are the bracketed prefixes the human lines
#: already used, so the JSON says the same word the terminal said.
NOTICES = (
    "hint", "profile", "session", "authwall", "devserver", "within",
    "web-parts", "resume", "images", "report", "audit", "scan",
    "ai-patterns", "browser", "spa", "warning", "run-folder", "error",
)

_mode = MODE_HUMAN
_findings = False
_summary: dict = {}


#: Set this and every run in the shell speaks JSONL, without the flag on each
#: command. It exists because the flag is not the right default and the wish
#: behind "make it the default" still is: a person at a terminal wants the
#: sentences, an agent wants the objects, and which one is reading is a
#: property of the environment rather than of the command. The flag wins over
#: it, so one run can always be read by eye.
ENV_VAR = "XAUDIT_PROGRESS"


def configure(spec: str | None) -> str:
    """Read `--progress`, falling back to `$XAUDIT_PROGRESS`
    (or the old `$XANALYZE_PROGRESS`).

    Accepts `human`, `jsonl` and `jsonl=findings`. An unknown spelling is
    argparse's job to reject on the command line, so anything unrecognised
    here falls back to the human output rather than to an error: a progress
    format is not worth failing a scan over, and an environment variable
    with a typo in it must not break every command in the shell.
    """
    global _mode, _findings

    _mode, _findings = MODE_HUMAN, False
    text = (spec or "").strip().lower()
    if not text or text == MODE_HUMAN:
        # `--progress human` is a deliberate "give me the sentences", so it
        # overrides the environment; an absent flag is not, so it does not.
        if spec is None or not spec.strip():
            text = (app_identity.env("PROGRESS") or "").strip().lower()
    if not text or text == MODE_HUMAN:
        return _mode
    name, _, option = text.partition("=")
    if name == MODE_JSONL:
        _mode = MODE_JSONL
        _findings = option == "findings"
    return _mode


def mode() -> str:
    return _mode


def enabled() -> bool:
    """Is the machine-readable stream on?

    Call sites use it to skip work that only the human output needs - never
    to decide *whether* to report something.
    """
    return _mode == MODE_JSONL


def wants_findings() -> bool:
    return _mode == MODE_JSONL and _findings


def reset() -> None:
    """Back to the default. For tests, and for the window, which runs many
    scans in one process and must not inherit the last one's flag."""
    global _mode, _findings, _summary

    _mode, _findings = MODE_HUMAN, False
    _summary = {}


def set_summary(**fields) -> None:
    """What `run.end` should carry, recorded where the numbers are known.

    The command that counted the findings is not the one that knows the exit
    code - `cli.main` is - so the two halves of `run.end` meet here instead
    of being threaded through every return statement.
    """
    _summary.update({k: v for k, v in fields.items() if v is not None})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _plain(value):
    """Whatever came in, as something `json.dumps` will take.

    Paths, enums and the odd dataclass reach these calls; a progress line is
    not the place to discover that one of them is not serialisable.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    return str(value)


def emit(event: str, human: str = "", *, stream=None, **fields) -> None:
    """One point in the run, in whichever form was asked for.

    `human` is printed as-is when the stream is off, so the terminal output
    stays exactly what it was; `fields` become the JSON object when it is on.
    Both come from this one call, which is what keeps them describing the
    same run.

    `stream` is for the one caller that already takes a destination
    (`cli_impl.prerun`, whose tests read the lines back out of a buffer);
    everything else writes to stderr.

    An empty `human` means "nothing to say to a person here" - the point is
    real, but the human output never had a line for it (`run.start`,
    `run.end`). The reverse never happens: every human line goes through a
    call that names an event.
    """
    try:
        out = stream if stream is not None else sys.stderr
        if _mode != MODE_JSONL:
            if human:
                print(human, file=out, flush=True)
            return
        record = {"event": event, "ts": _now()}
        for key, value in fields.items():
            if value is None:
                continue
            record[key] = _plain(value)
        print(json.dumps(record, ensure_ascii=False), file=out, flush=True)
    except Exception:  # noqa: BLE001 - never the reason a run fails
        pass


# ------------------------------------------------------------------ events

def run_start(command: str, target: str, version: str) -> None:
    emit("run.start", "", command=command, target=target, version=version)


def run_end(exit_code: int, counts=None, documents=None) -> None:
    """The last line of the stream.

    `documents` counts audited documents and `sources` the addresses behind
    them; they differ because one page is several documents (its own rules,
    its response headers, an image's provenance). Both are carried rather
    than one, because a stream that says "2" in one event and "4" in another
    under the same name is worse than either number alone.
    """
    emit("run.end", "", exit_code=exit_code,
         counts=counts if counts is not None else _summary.get("counts"),
         documents=(documents if documents is not None
                    else _summary.get("documents")),
         sources=_summary.get("sources"))


def stage(name: str, state: str, human: str = "", **fields) -> None:
    """A phase starting, reporting its way through, or ending.

    `name` is one of `STAGES`, `state` one of `STAGE_STATES`.
    """
    emit("stage", human, name=name, state=state, **fields)


def page(n: int, of, url: str, depth=None, status=None, human: str = "") -> None:
    emit("page", human, n=n, of=of, url=url, depth=depth, status=status)


def file_read(n: int, of, path: str, human: str = "") -> None:
    """One file opened. Named `file_read` because `file` was a builtin long
    enough that a module-level `file` still reads as a mistake."""
    emit("file", human, n=n, of=of, path=path)


def notice(kind: str, text: str, human: str | None = None, *,
           stream=None, **fields) -> None:
    """Something worth saying that is not progress: a hint, a session, a
    warning, a wall the crawl hit.

    `text` is the sentence; `human` is the line the terminal shows, which
    usually carries a `# [kind]` prefix the JSON does not need. When they are
    the same, pass only `text`.
    """
    emit("notice", text if human is None else human, stream=stream,
         kind=kind, text=text, **fields)


def finding(rule: str, severity: str = "", source: str = "", line=None,
            **fields) -> None:
    """A finding, as soon as it exists rather than at the end.

    Off unless `--progress jsonl=findings`: the whole point of the flag is
    that this one event can outnumber every other by three orders of
    magnitude.
    """
    if not wants_findings():
        return
    emit("finding", "", rule=rule, severity=severity, source=source,
         line=line, **fields)
