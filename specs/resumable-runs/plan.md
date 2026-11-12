# Plan

## New modules

| Module | Job |
|---|---|
| `report/activity.py` | Evidence of progress for a Qt render: load progress, render-process CPU time, process death. No Qt import at module scope. |
| `cli_impl/runstate.py` | `state.json` in the run folder: one row per phase, written on every transition. Produces the resume command and the agent feedback block. |
| `cli_impl/checkpoint.py` | Serialise/rehydrate a phase's product (audit result, scan findings) so resume does not recompute it. |

## `report/activity.py`

`ActivityWatch(page, stall_seconds, poll_seconds)`.

Evidence, in the order it is trusted:

1. `renderProcessTerminated` -> stop now, `kind` + `exit_code` in the reason.
   Not retried: a dead renderer is an answer.
2. `loadProgress(int)` changed since the last poll -> progress.
3. Render-process CPU time increased since the last poll -> progress. Read
   with `ps -o cputime= -p <pid>`; centiseconds on darwin, whole seconds on
   Linux, hence a stall window of tens of seconds rather than a few.
4. Neither for `stall_seconds` -> stop, naming the phase and the silence.

`observable` is False when there is no pid or `ps` fails; the reason string
then says the watchdog was watching load progress only, so a stall report can
never be mistaken for a measured one.

## `cli_impl/runstate.py`

```
PHASES = ("scan", "crawl", "audit", "browser", "reports", "documents")
```

`state.json`: `{schema, target, command, args, created, updated, status,
phases: [{name, status, started, finished, seconds, artifacts, reason}],
resume: {command, from_phase}, feedback: {...}}`

`status` is one of `running`, `paused`, `failed`, `done`.

`feedback` is the part written for a machine: what stopped, the phase, the
reason, the artifacts that do exist, and the one command that continues.

Pause is a `PAUSE` file in the run folder. Phases check `state.paused()` at
their boundaries and raise `Paused`, which is not an error: the state goes to
`paused`, the artifacts stay, the resume path is the same one a failure uses.
That is deliberate - two resume paths would drift, and only one of them would
be tested.

## `cmd_fullscan` changes

Each phase is wrapped so that a failure records itself and *stops the run
without losing the earlier phases*. The existing per-writer isolation stays:
a failed styled report is already survivable and must not become fatal now.

After the audit phase, its product is checkpointed; resume rehydrates it and
skips straight to the reports.

## CLI

- `xaudit runs [--json]` - the catalogue, newest first.
- `xaudit resume <run>` - continue from the first unfinished phase.
- `xaudit pause <run>` - ask a running one to stop at the next boundary.

The catalogue is derived by walking `XBrain Audit/*/*/state.json`, not from an
index file. One fact, one owner: an index would be a second answer to "what
runs exist" and would be the one that goes stale.

## GUI

A `Runs` section in the control column listing target, status, stage and age,
with Resume and Pause. It reads the same walk the CLI does.

## Risks

- `ps` resolution on Linux is one second: a renderer using <1s of CPU per
  poll can look idle. Mitigated by the stall window being tens of seconds.
- Rehydrated audit results are shells with the attributes the writers read.
  A writer that later reads something else gets an `AttributeError` on resume
  only - so the rehydration test asserts the attribute set, not just a count.
