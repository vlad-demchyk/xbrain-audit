"""`runs`, `resume` and `pause`: the catalogue of runs and what to do with one.

A full scan of a large site is a long job that can stop for reasons that have
nothing to do with the target - a wedged renderer, a laptop closing, a person
deciding they want their machine back. These three commands exist so stopping
is not the same as losing: the catalogue says what state every run is in, and
one command continues any of them.

`resume` re-enters `cmd_fullscan` with the recorded invocation rather than
reimplementing the phases. That is the whole reason the argv is stored: a
resume that rebuilt the arguments from the state file would be a second answer
to "what run is this", and it would be the one that drifted.
"""
from __future__ import annotations

import argparse
import json
import sys

import progress
from datetime import datetime, timezone

from cli_impl import EXIT_ERROR, EXIT_OK
from cli_impl import runstate


def _age(created: str) -> str:
    """`2026-08-24 09:38:57 UTC` -> `12m ago`."""
    try:
        when = datetime.strptime(created, "%Y-%m-%d %H:%M:%S UTC").replace(
            tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return "-"
    seconds = (datetime.now(timezone.utc) - when).total_seconds()
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _depth_of(argv: list) -> int | None:
    """The crawl depth this run was started with, or None.

    Read out of the recorded invocation rather than stored separately: the
    invocation is already kept verbatim so `resume` reproduces the run, and
    a second copy of one flag is a second thing that can disagree with it.
    None when the run did not name a depth - the default is not the same
    statement as an explicit choice, and this is a row in a catalogue, not
    a form.
    """
    for index, item in enumerate(argv):
        text = str(item)
        if text.startswith("--depth="):
            value = text.split("=", 1)[1]
        elif text == "--depth" and index + 1 < len(argv):
            value = str(argv[index + 1])
        else:
            continue
        try:
            return int(value)
        except ValueError:
            return None
    return None


def run_rows(states) -> list:
    """One row per run, as data. Shared with the GUI catalogue."""
    rows = []
    for state in states:
        data = state.data
        # Where it stopped, not where a resume would begin. The two differ
        # whenever an earlier phase was never reached: a run that failed in
        # the crawl showed "scan" as its stage, because scan was the first
        # phase still pending. The reader is asking what went wrong, and the
        # phase that went wrong is the one that recorded a reason.
        stage = state.feedback()["stopped_in"] or state.next_phase()
        rows.append({
            "run": str(state.run_dir),
            "name": state.run_dir.name,
            "target": data.get("target", ""),
            # `state.status()`, not the recorded field: a killed run never
            # got to write a final state, so the file still says `running`
            # and the catalogue would claim work is in progress that stopped
            # an hour ago.
            "status": state.status(),
            "stage": stage or "-",
            "created": data.get("created", ""),
            "age": _age(data.get("created", "")),
            "artifacts": len(state.artifacts()),
            # None, not 0, when the run never got far enough to record one:
            # a crawl that stopped found nothing *yet*, and printing 0 for
            # it says it came back clean.
            "findings": data.get("findings"),
            # What kind of thing was scanned, and how deep. The catalogue
            # holds several runs of the same target more often than not, and
            # the address alone does not tell two of them apart.
            "kind": "site" if str(data.get("target", "")).startswith(
                ("http://", "https://")) else "repo",
            "depth": _depth_of(data.get("argv") or []),
            "resumable": state.resumable(),
        })
    return rows


def cmd_runs(args) -> int:
    """List known runs, newest first."""
    states = runstate.all_runs(getattr(args, "root", None))
    rows = run_rows(states)
    if getattr(args, "json", False):
        print(json.dumps({"runs": rows}, indent=2, ensure_ascii=False))
        return EXIT_OK
    if not rows:
        print("no runs recorded yet")
        return EXIT_OK
    width = max(len(r["target"]) for r in rows)
    width = min(max(width, 6), 48)
    print(f"{'run':<17} {'status':<12} {'stage':<9} {'found':>6} "
          f"{'age':<9} target")
    for row in rows:
        target = row["target"]
        if len(target) > width:
            target = target[:width - 1] + "…"
        # A dash, not a zero, for a run that never recorded a count.
        found = "-" if row["findings"] is None else str(row["findings"])
        print(f"{row['name']:<17} {row['status']:<12} {row['stage']:<9} "
              f"{found:>6} {row['age']:<9} {target}")
    unfinished = [r for r in rows if r["resumable"]]
    if unfinished:
        print()
        print(f"{len(unfinished)} run(s) can be continued, e.g. "
              f"xaudit resume {unfinished[0]['name']}")
    return EXIT_OK


def cmd_pause(args) -> int:
    """Ask a run to stop at its next phase boundary.

    Cooperative rather than a kill: a phase stopped mid-way leaves nothing
    reusable, and a boundary is exactly where the state file is consistent
    and the checkpoint has just been written.
    """
    state = runstate.find_run(args.run, getattr(args, "root", None))
    if state is None:
        print(f"no run found for: {args.run}", file=sys.stderr)
        return EXIT_ERROR
    if state.next_phase() is None:
        # Refused rather than recorded. Writing the request anyway reported
        # success, did nothing, and left a `PAUSE` file in the folder that
        # nothing would ever clear - so a later run of that folder would have
        # paused itself for a reason nobody remembered asking for.
        print(f"{state.run_dir} is already complete; nothing to pause")
        return EXIT_OK
    state.request_pause()
    print(f"pause requested for {state.run_dir}")
    print("the run stops at its next phase boundary; continue it with "
          f"xaudit resume {state.run_dir.name}")
    return EXIT_OK


def cmd_resume(args) -> int:
    """Continue a paused or stopped run from its first unfinished phase."""
    state = runstate.find_run(args.run, getattr(args, "root", None))
    if state is None:
        print(f"no run found for: {args.run}", file=sys.stderr)
        return EXIT_ERROR
    if state.next_phase() is None:
        print(f"{state.run_dir} is already complete; nothing to resume")
        return EXIT_OK
    # A pause request left over from the stop would otherwise pause the
    # resume at its first boundary, which reads as the resume not working.
    state.clear_pause()

    argv = list(state.data.get("argv") or [])
    if not argv:
        print(f"{state.run_dir} recorded no invocation to resume",
              file=sys.stderr)
        return EXIT_ERROR

    import cli

    parser = cli.build_parser()
    try:
        resumed_args = parser.parse_args(argv)
    except SystemExit:
        print(f"the recorded invocation no longer parses: {' '.join(argv)}",
              file=sys.stderr)
        return EXIT_ERROR
    if getattr(resumed_args, "func", None) is not cli.cmd_fullscan:
        print("only fullscan runs can be resumed", file=sys.stderr)
        return EXIT_ERROR

    # The state object itself, not its path: `cmd_fullscan` must write into
    # the same run folder, so the phases it skips are the ones this file says
    # are done rather than a fresh set in a new folder.
    resumed_args._resume_state = state
    progress.notice("resume", f"{state.run_dir} from {state.next_phase()}",
                    human=f"# [resume] {state.run_dir} from "
                          f"{state.next_phase()}",
                    run=str(state.run_dir), phase=state.next_phase())
    return resumed_args.func(resumed_args)


def add_run_parsers(sub) -> None:
    """Register `runs`, `resume` and `pause` on the top-level subparsers."""
    p_runs = sub.add_parser(
        "runs", help="list scan runs and whether they can be continued")
    p_runs.add_argument("--json", action="store_true",
                        help="machine-readable output")
    p_runs.add_argument("--root", default=argparse.SUPPRESS,
                        help="where run folders live (default: ~/Documents/XBrain Audit)")
    p_runs.set_defaults(func=cmd_runs)

    p_resume = sub.add_parser(
        "resume", help="continue a run that was paused or stopped")
    p_resume.add_argument("run", help="run folder, or the timestamp shown by "
                                      "`xaudit runs`")
    p_resume.add_argument("--root", default=argparse.SUPPRESS)
    p_resume.set_defaults(func=cmd_resume)

    p_pause = sub.add_parser(
        "pause", help="ask a running scan to stop at its next phase boundary")
    p_pause.add_argument("run", help="run folder, or the timestamp shown by "
                                     "`xaudit runs`")
    p_pause.add_argument("--root", default=argparse.SUPPRESS)
    p_pause.set_defaults(func=cmd_pause)
