# Tasks

- [x] 1. `report/activity.py` + tests: progress keeps a render alive, a dead
      render process stops it, silence stops it, unobservable says so.
      *25 tests, including a real render surviving a 2s stall window.*
- [x] 2. Wire it into `PdfRenderer._render_once`, keeping `RENDER_TIMEOUT_MS`
      as an optional absolute cap.
- [x] 3. `cli_impl/runstate.py` + tests: transitions, `state.json` shape,
      resume command, agent feedback, pause. *40 tests.*
- [x] 4. `cli_impl/checkpoint.py` + tests: audit result round-trips with the
      attributes the report writers read. *Exact round trip - all three are
      dataclasses, so the "shell" the plan expected was not needed.*
- [x] 5. Phase wrapping in `cmd_fullscan`; partial artifacts on failure.
      *Verified end to end: forced failure -> exit 3 + feedback -> fix ->
      `resume` reused scan and audit and finished.*
- [x] 6. `xaudit runs` / `resume` / `pause`.
- [x] 7. GUI runs catalogue + tests. *15 tests.*
- [x] 8. README x3 (0 broken anchors), `Devs/`, `Problems.md`, STATE, Planning.

## Found on the way, fixed here

- `MODE_FILE` was referenced by `MainWindow.mode` and by the browser pass's
  `allow_local_files` and **defined nowhere**: choosing "single file" as the
  source raised `NameError` on a property half the window reads. No test
  selected that source and then asked for the mode, so nothing caught it.
- Naming both report paths used to mean no run folder at all, so the one
  caller who wanted control over their output was the only one who could not
  resume. The reports now go where they were asked for and the run still gets
  a folder for its state.
- A repo scan left `crawl` pending forever, so a finished run reported itself
  unfinished and offered to continue. Phases that correctly do not run are
  now `skipped`, which is neither `done` (a claim) nor `pending` (work).

## Deliberately not done

Per-page resume inside the browser pass. A stopped pass restarts that pass.
The crawl is the expensive part and it is already reused; per-page
checkpointing is a larger change than the failure it would save.
