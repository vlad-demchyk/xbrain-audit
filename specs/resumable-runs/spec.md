# Resumable runs and an activity-based render watchdog

## Problem

A `fullscan` of a 192-page site takes ~46 minutes and ends by printing a PDF
that took 108 seconds. Two failure modes were observed on that real run:

1. **A fixed 30s print ceiling killed a render that was still working.** The
   first run of that site spent ~50 minutes and wrote *nothing at all*.
2. **Removing the ceiling (`RENDER_TIMEOUT_MS = 0`) removed the floor too.**
   A render process that dies or wedges now hangs the writer with no entry in
   any log, forever.

Both are the same design error: **elapsed time was used as a proxy for
progress.** Time is not evidence. A render that has been going for ten
minutes and is still burning CPU is healthy; one that has been silent for
forty seconds with a dead render process is not, at any elapsed time.

Separately, a run that stops for *any* reason - a stall, a crash, the user
closing the window - currently loses everything it computed. 46 minutes of
crawling is thrown away because the last step of six failed.

## Acceptance criteria

### A. The watchdog stops on evidence, never on a clock

1. A render making progress is never interrupted, no matter how long it
   takes. Progress means any of: a `loadProgress` change, or the render
   process consuming more CPU time than at the previous poll.
2. A render whose process dies (`renderProcessTerminated`) stops
   immediately, with the exit status and termination kind in the message.
   No retry: a crashed renderer is an answer, not a silence.
3. A render with no progress of any kind for `STALL_SECONDS` stops, and the
   message says which phase stalled and for how long, never "timed out
   after 30s".
4. With no way to observe the render process (no pid, `ps` unavailable), the
   watchdog degrades to load-progress only and says so in the reason - it
   must not silently become a fixed timer again.
5. `RENDER_TIMEOUT_MS` keeps working as an absolute cap when set above 0, so
   tests can still bound a render.

### B. A stopped run keeps what it has

6. Every phase of `fullscan` records its outcome in the run folder as it
   happens: `pending`, `running`, `done` with artifacts, or `failed` with the
   reason. Written on transition, not at the end - the point is to survive a
   run that has no end.
7. When a phase fails, the run folder still contains every artifact the
   earlier phases produced, plus `state.json` naming the phase that stopped
   and what remains.
8. `state.json` is machine-readable and self-describing: an agent reading it
   alone can tell what was done, what failed, why, and the exact command that
   continues from there.
9. Nothing already computed is recomputed on resume: the crawl's pages and
   the audit's findings are reloaded from the run folder.

### C. The interface can pause and resume

10. `xaudit runs` lists known runs with status, target, stage and age.
11. `xaudit resume <run>` continues a paused or failed run from its first
    unfinished phase.
12. The GUI shows a catalogue of runs with their status, and can pause a
    running one and resume a paused one.
13. Pausing is cooperative and leaves the run folder valid: a paused run is
    indistinguishable from a stalled one to the resume path, so there is one
    resume path and not two.

## Non-goals

- Resuming *inside* a phase. A stopped browser pass restarts that pass; it
  does not resume at page 97. Per-page checkpointing is a larger change and
  the crawl, which is the expensive part, is already reusable.
- A progress bar for `printToPdf`. Qt does not expose one; CPU time is the
  evidence available and this spec uses it as evidence, not as a percentage.
