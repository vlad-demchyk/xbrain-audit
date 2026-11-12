"""What a run has done so far, written down as it happens.

A `fullscan` of a real 192-page site takes about three quarters of an hour and
ends with a step that takes two minutes. When that last step failed, the whole
run was lost: the crawl, the audit, the browser pass over 158 pages at three
widths - forty-six minutes of work thrown away because the sixth of six
phases raised.

So each phase records its outcome **on transition, not at the end**. That
distinction is the entire design: a file written when the run finishes is
worthless to a run that never finishes, which is precisely the case worth
surviving.

`state.json` is written for two readers and says the same thing to both:

* a person, who wants to know which stage stopped and what is on disk;
* an agent, which wants the reason in a field it can branch on and the exact
  command that continues from here. `feedback` exists for the second reader.

Pause uses the same machinery. A paused run and a stalled run differ only in
their recorded reason, and both resume through one code path - two paths would
drift, and only one of them would ever be tested.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

#: The phases of a full scan, in the order they run. Resume restarts at the
#: first one that is not `done`, which is why the order is data and not just
#: the order of statements in `cmd_fullscan`.
#:
#: `"devserver"` is never trusted as `done` on resume - see `_run_phases` in
#: `cli_impl/fullscan.py` - because the process it would refer to no longer
#: exists once the CLI has exited. It is recorded for the same reason every
#: other phase is: visibility, and a place for `skip`/`fail` to say why the
#: browser pass never ran.
PHASES = ("devserver", "scan", "crawl", "audit", "browser", "reports", "documents")

#: Human labels, so the catalogue and the timings agree on what to call a
#: stage. Kept next to `PHASES` rather than in the i18n table: these names
#: also go into `state.json`, which is read by machines and must not move
#: when the interface language changes.
PHASE_LABELS = {
    "devserver": "starting dev server",
    "scan": "AI patterns scan",
    "crawl": "crawl",
    "audit": "static audit",
    "browser": "browser pass",
    "reports": "writing reports",
    "documents": "run documents",
}

PENDING, RUNNING, DONE, FAILED, SKIPPED, PAUSED = (
    "pending", "running", "done", "failed", "skipped", "paused")

#: Recorded as `running`, but the process that recorded it is gone. Never
#: written to the file - it is derived by `RunState.status()`, because the run
#: that would have written it is exactly the run that was killed before it
#: could write anything.
INTERRUPTED = "interrupted"

#: Bumped when the file's shape changes in a way a reader must notice. A
#: reader that does not recognise the number should say so rather than guess.
SCHEMA = 1

STATE_FILE = "state.json"
PAUSE_FILE = "PAUSE"


class Paused(Exception):
    """The user asked for a stop at the next boundary.

    An exception rather than a return value because it has to unwind out of
    whatever phase noticed it, and not an `Exception` subclass anybody catches
    by accident - `cmd_fullscan` catches it explicitly and records `paused`,
    which is a normal ending and not a failure.
    """


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class RunState:
    """The state file for one run folder."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = Path(path)
        self.data = data

    # ------------------------------------------------------------- opening
    @classmethod
    def begin(cls, folder, target: str, *, command: str = "fullscan",
              argv: list | None = None, phases=PHASES) -> "RunState":
        """Start a state file in `folder.run`, every phase pending."""
        data = {
            "schema": SCHEMA,
            "target": target,
            "command": command,
            # The invocation, so `resume` reproduces the run rather than
            # guessing at its flags. Recorded as given: a resume that
            # silently used different options would be a different run.
            "argv": list(argv if argv is not None else sys.argv[1:]),
            "created": _now(),
            "updated": _now(),
            "status": RUNNING,
            "pid": os.getpid(),
            "phases": [{"name": name, "label": PHASE_LABELS.get(name, name),
                        "status": PENDING, "started": None, "finished": None,
                        "seconds": None, "artifacts": [], "reason": None}
                       for name in phases],
        }
        state = cls(Path(folder.run) / STATE_FILE, data)
        state.save()
        return state

    @classmethod
    def load(cls, run: Path) -> "RunState | None":
        path = Path(run) / STATE_FILE if Path(run).is_dir() else Path(run)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or "phases" not in data:
            return None
        return cls(path, data)

    # -------------------------------------------------------------- saving
    def save(self) -> None:
        """Write the file, atomically.

        Atomic because the reader is a catalogue that may run at any moment,
        including during a write: a half-written `state.json` would make a
        healthy run look corrupt.
        """
        self.data["updated"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        temp.replace(self.path)

    # ------------------------------------------------------------- phases
    @property
    def run_dir(self) -> Path:
        return self.path.parent

    def phase(self, name: str) -> dict | None:
        for entry in self.data["phases"]:
            if entry["name"] == name:
                return entry
        return None

    def start(self, name: str) -> None:
        entry = self.phase(name)
        if entry is None:
            return
        entry.update(status=RUNNING, started=_now(), reason=None)
        entry["_began"] = time.monotonic()
        self.data["status"] = RUNNING
        self.save()

    def done(self, name: str, *, artifacts=()) -> None:
        self._close(name, DONE, artifacts=artifacts)

    def skip(self, name: str, reason: str = "not applicable to this target") -> None:
        """A phase that correctly did not run - a repo has no crawl.

        Distinct from `done` so the catalogue can say "no browser pass here"
        rather than implying one happened, and distinct from `pending` so
        resume does not try to run it.
        """
        entry = self.phase(name)
        if entry is None:
            return
        entry.update(status=SKIPPED, reason=reason)
        self.save()

    def fail(self, name: str, reason: str) -> None:
        self._close(name, FAILED, reason=reason)
        self.data["status"] = FAILED
        self.save()

    def pause(self, name: str) -> None:
        self._close(name, PENDING, reason="paused before it finished")
        self.data["status"] = PAUSED
        self.save()

    def _close(self, name: str, status: str, *, artifacts=(),
               reason: str | None = None) -> None:
        entry = self.phase(name)
        if entry is None:
            return
        began = entry.pop("_began", None)
        entry.update(status=status, finished=_now(), reason=reason)
        if began is not None:
            entry["seconds"] = round(time.monotonic() - began, 2)
        if artifacts:
            entry["artifacts"] = [str(a) for a in artifacts]
        self.save()

    def finish(self) -> None:
        """The run ended normally."""
        self.data["status"] = DONE
        self.save()

    def record_findings(self, count: int) -> None:
        """How many findings this run ended with.

        Recorded because nothing else can answer it later. The catalogue of
        runs is built by walking the folders, and "36 findings, now 27" is
        the single most useful thing to know about a run you are deciding
        whether to reopen - but a finished run's count lives only inside its
        report, and re-reading every report to list five rows is not a list,
        it is a second scan.

        Absent rather than zero when it was never recorded: a run that
        stopped in the crawl found nothing *yet*, and a catalogue that
        prints 0 for it says it came back clean.
        """
        self.data["findings"] = int(count)
        self.save()

    # --------------------------------------------------------------- pause
    def paused_requested(self) -> bool:
        return (self.run_dir / PAUSE_FILE).exists()

    def request_pause(self) -> None:
        """Ask a running scan to stop at its next phase boundary.

        A file rather than a signal: the scan may be in another process, the
        GUI may not own it, and a file is the one channel both ends already
        have. It is also visible - someone looking at the folder can see that
        a pause was asked for, which a signal would not show anybody.
        """
        (self.run_dir / PAUSE_FILE).write_text(_now(), encoding="utf-8")

    def clear_pause(self) -> None:
        (self.run_dir / PAUSE_FILE).unlink(missing_ok=True)

    def checkpoint(self, name: str) -> None:
        """Raise `Paused` if a pause was asked for. Call between phases."""
        if self.paused_requested():
            self.pause(name)
            self.clear_pause()
            raise Paused(f"paused before {PHASE_LABELS.get(name, name)}")

    # -------------------------------------------------------------- resume
    def next_phase(self) -> str | None:
        """The first phase that still has work, or None when there is none."""
        for entry in self.data["phases"]:
            if entry["status"] in (PENDING, RUNNING, FAILED):
                return entry["name"]
        return None

    def alive(self) -> bool:
        """Is the process that recorded this run still running?

        A run that is killed - Ctrl-C, a closed laptop, an `OOM` - never gets
        to write a final state, so the file keeps saying `running` forever.
        The catalogue then claims work is in progress that stopped an hour
        ago, which is worse than saying nothing: it is the one status a
        reader would act on.

        Checked with signal 0, which asks the kernel whether the pid exists
        without touching it. `PermissionError` means it exists and belongs to
        someone else - still alive, still not ours to signal.
        """
        pid = self.data.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def status(self) -> str:
        """The recorded status, corrected for a process that is gone.

        Derived rather than stored, because the correction can only be made
        by asking now: the run that would have written `interrupted` is
        precisely the run that was not around to write anything.
        """
        recorded = self.data.get("status", "")
        if recorded == RUNNING and not self.alive():
            return INTERRUPTED
        return recorded

    def resumable(self) -> bool:
        return (self.status() in (PAUSED, FAILED, RUNNING, INTERRUPTED)
                and self.next_phase() is not None)

    def resume_command(self) -> str:
        return f"xaudit resume {self.run_dir}"

    def artifacts(self) -> list:
        """Files the run actually produced, in phase order.

        Read back off disk rather than trusted from the record: the point of
        this list is to tell a reader what they can open right now, and a
        recorded path whose file is gone would be a promise, not a fact.
        """
        found: list = []
        seen: set = set()
        for entry in self.data["phases"]:
            for name in entry.get("artifacts", ()):
                path = Path(name)
                # Deduplicated: two phases legitimately record the same file -
                # the audit writes its checkpoint and the browser pass
                # rewrites it - and a reader counting what is on disk should
                # not be told about one file twice.
                if str(path) in seen or not path.exists():
                    continue
                seen.add(str(path))
                found.append(str(path))
        return found

    # ------------------------------------------------------------ feedback
    def feedback(self) -> dict:
        """The block written for a machine.

        Everything an agent needs to act without reading anything else: what
        stopped, why, in which phase, what exists on disk, and the single
        command that continues. Flat and named, so it can be branched on
        rather than parsed out of a sentence.
        """
        stopped = None
        for entry in self.data["phases"]:
            if entry["status"] in (FAILED, PENDING) and entry.get("reason"):
                stopped = entry
                break
        return {
            "status": self.status(),
            "target": self.data.get("target"),
            "stopped_in": stopped["name"] if stopped else None,
            "stopped_because": stopped.get("reason") if stopped else None,
            "completed_phases": [e["name"] for e in self.data["phases"]
                                 if e["status"] == DONE],
            "remaining_phases": [e["name"] for e in self.data["phases"]
                                 if e["status"] in (PENDING, RUNNING, FAILED)],
            "artifacts": self.artifacts(),
            "resume_with": self.resume_command() if self.resumable() else None,
            # Said explicitly because it is the question an agent actually
            # has: not "did it work" but "is there anything for me to do".
            "action_required": bool(stopped),
        }

    def write_feedback(self) -> None:
        self.data["feedback"] = self.feedback()
        self.data["resume"] = {
            "command": self.resume_command() if self.resumable() else None,
            "from_phase": self.next_phase(),
        }
        self.save()

    def as_markdown(self) -> str:
        """`state.md`: the same facts for a person, no JSON to read."""
        info = self.feedback()
        lines = [f"# Run state: {self.data.get('target', '')}", "",
                 f"Status **{info['status']}**, started {self.data.get('created')}.",
                 ""]
        if info["stopped_because"]:
            lines += [f"Stopped in **{info['stopped_in']}**: "
                      f"{info['stopped_because']}", ""]
        lines += ["| stage | status | duration | reason |", "|---|---|---|---|"]
        for entry in self.data["phases"]:
            seconds = entry.get("seconds")
            duration = f"{seconds:.1f}s" if seconds is not None else "-"
            lines.append(f"| {entry['label']} | {entry['status']} | "
                         f"{duration} | {entry.get('reason') or '-'} |")
        lines.append("")
        if info["artifacts"]:
            lines += ["## Written so far", ""]
            # The name alone when the file is in this folder, the whole path
            # when it is not. Naming `--report` or `--styled-report` sends
            # those documents wherever the caller asked, and this list -
            # which lives *inside* the run folder - was printing their bare
            # names as if they were here: a reader who opens the folder
            # finds no `briefing.md` and has nothing to search for.
            for artifact in info["artifacts"]:
                path = Path(artifact)
                inside = path.parent.resolve() == Path(self.run_dir).resolve()
                lines.append(f"- `{path.name}`" if inside else f"- `{path}`")
            lines.append("")
        if info["resume_with"]:
            lines += ["## Continue", "",
                      "Fix what the reason names, then run:", "",
                      f"```\n{info['resume_with']}\n```", "",
                      "Finished phases are not recomputed; the run picks up "
                      f"at **{info['stopped_in'] or self.next_phase()}**.", ""]
        return "\n".join(lines)

    def write_markdown(self) -> Path:
        path = self.run_dir / "state.md"
        path.write_text(self.as_markdown(), encoding="utf-8")
        return path


# ------------------------------------------------------------- catalogue
def all_runs(root: Path | None = None) -> list:
    """Every run with a state file, newest first.

    Derived by walking the project folders, not read from an index. One fact,
    one owner: an index would be a second answer to "what runs exist", and it
    would be the one that goes stale the moment a folder is moved or deleted
    by hand.
    """
    from . import runfolder

    base = Path(root) if root is not None else runfolder.default_root()
    if not base.is_dir():
        return []
    found = []
    for project in sorted(base.iterdir()):
        if not project.is_dir():
            continue
        for run in sorted(project.iterdir()):
            if not run.is_dir():
                continue
            state = RunState.load(run)
            if state is not None:
                found.append(state)
    found.sort(key=lambda s: s.data.get("created", ""), reverse=True)
    return found


def find_run(reference: str, root: Path | None = None) -> "RunState | None":
    """Resolve a run from a path, or from the tail of one.

    A path so `resume` can take what the run folder line printed; a tail so a
    person can type the timestamp they see in the catalogue instead of the
    whole path.
    """
    direct = Path(reference).expanduser()
    if direct.exists():
        state = RunState.load(direct)
        if state is not None:
            return state
    text = str(reference).rstrip("/")
    for state in all_runs(root):
        run = state.run_dir
        if run.name == text or str(run).endswith(text):
            return state
    return None
