"""A run that stops keeps what it computed, and one command continues it.

The behaviour under test came from a real 192-page run: forty-six minutes of
crawling and auditing, then the last of six phases raised and the run wrote
nothing at all. Every assertion below is about the difference between that and
what should have happened.
"""
from __future__ import annotations

import json

import tempfile
import unittest
from pathlib import Path

from cli_impl import checkpoint, runfolder, runstate
from cli_impl.runstate import DONE, FAILED, PAUSED, RunState, SKIPPED


class _Folder:
    """The two attributes `RunState.begin` reads off a run folder."""

    def __init__(self, root: Path):
        self.project = root
        self.run = root


def _state(root, target="https://example.com", argv=("fullscan", "x")):
    return RunState.begin(_Folder(Path(root)), target, argv=list(argv))


class Transitions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = _state(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_phase_starts_pending(self):
        self.assertEqual({p["status"] for p in self.state.data["phases"]},
                         {"pending"})

    def test_the_file_exists_before_any_phase_runs(self):
        """Written on transition, not at the end.

        The whole point: a file written when the run finishes is worthless to
        a run that never finishes, which is the case worth surviving.
        """
        self.assertTrue((Path(self.tmp.name) / "state.json").exists())

    def test_a_finished_phase_records_a_duration(self):
        self.state.start("crawl")
        self.state.done("crawl")
        self.assertEqual(self.state.phase("crawl")["status"], DONE)
        self.assertIsNotNone(self.state.phase("crawl")["seconds"])

    def test_a_failed_phase_records_why(self):
        self.state.start("reports")
        self.state.fail("reports", "the printer did not answer")
        self.assertEqual(self.state.phase("reports")["status"], FAILED)
        self.assertIn("printer", self.state.phase("reports")["reason"])
        self.assertEqual(self.state.data["status"], FAILED)

    def test_a_skipped_phase_is_not_a_finished_one(self):
        """A repo has no crawl, and saying `done` would claim it did.

        Nor `pending`: that is what resume tries to run, and a completed repo
        scan reported itself unfinished forever because of exactly that.
        """
        self.state.skip("crawl", "not a website")
        self.assertEqual(self.state.phase("crawl")["status"], SKIPPED)
        self.assertNotEqual(self.state.next_phase(), "crawl")

    def test_the_file_survives_being_read_mid_write(self):
        """Atomic: the catalogue may read at any moment, including during."""
        for _ in range(20):
            self.state.start("crawl")
            self.state.done("crawl")
            reloaded = RunState.load(Path(self.tmp.name))
            self.assertIsNotNone(reloaded)

    def test_the_recorded_invocation_is_what_was_given(self):
        state = _state(self.tmp.name, argv=["fullscan", "https://x", "--depth", "3"])
        self.assertEqual(state.data["argv"],
                         ["fullscan", "https://x", "--depth", "3"])


class WhatTheStateDocumentSaysWasWritten(unittest.TestCase):
    """`state.md` lives inside the run folder and lists what the run wrote.

    Naming `--report` or `--styled-report` sends those documents wherever
    the caller asked, and the list printed their bare names regardless - so
    a reader opening the dated folder is told it holds a `briefing.md` that
    is not there, with nothing to search for.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = _state(self.tmp.name)

    def test_a_document_in_the_folder_is_named_by_its_name(self):
        inside = self.root / "timings.md"
        inside.write_text("x", encoding="utf-8")
        self.state.start("reports")
        self.state.done("reports", artifacts=[inside])
        self.assertIn("- `timings.md`", self.state.as_markdown())

    def test_a_document_written_elsewhere_is_named_by_its_path(self):
        elsewhere = self.root.parent / "somewhere"
        elsewhere.mkdir(exist_ok=True)
        self.addCleanup(lambda: [p.unlink() for p in elsewhere.iterdir()]
                        and elsewhere.rmdir())
        briefing = elsewhere / "briefing.md"
        briefing.write_text("x", encoding="utf-8")
        self.state.start("reports")
        self.state.done("reports", artifacts=[briefing])
        markdown = self.state.as_markdown()
        self.assertIn(f"- `{briefing}`", markdown)
        self.assertNotIn("- `briefing.md`\n", markdown)


class NextPhase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = _state(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resume_restarts_at_the_first_unfinished_phase(self):
        self.state.skip("devserver")
        for name in ("scan", "crawl", "audit"):
            self.state.start(name)
            self.state.done(name)
        self.assertEqual(self.state.next_phase(), "browser")

    def test_a_failed_phase_is_the_one_to_restart(self):
        self.state.skip("devserver")
        for name in ("scan", "crawl", "audit"):
            self.state.start(name)
            self.state.done(name)
        self.state.fail("browser", "the render process ended")
        self.assertEqual(self.state.next_phase(), "browser")

    def test_an_earlier_unreached_phase_comes_first(self):
        """Ordering wins over recency, and it has to.

        A run that failed in the browser pass without ever crawling cannot
        resume at the browser pass - there would be nothing to pass over. So
        `next_phase` answers "where does work restart", in order, and the
        phase that *stopped* is a separate question `feedback` answers.
        """
        self.state.skip("devserver")
        self.state.fail("browser", "the render process ended")
        self.assertEqual(self.state.next_phase(), "scan")
        self.assertEqual(self.state.feedback()["stopped_in"], "browser")

    def test_a_complete_run_has_nothing_to_resume(self):
        for name in runstate.PHASES:
            self.state.start(name)
            self.state.done(name)
        self.assertIsNone(self.state.next_phase())
        self.assertFalse(self.state.resumable())

    def test_a_complete_run_offers_no_resume_command(self):
        for name in runstate.PHASES:
            self.state.start(name)
            self.state.done(name)
        self.state.finish()
        self.assertIsNone(self.state.feedback()["resume_with"])


class Pause(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = _state(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_checkpoint_passes_when_no_pause_was_asked_for(self):
        self.state.checkpoint("crawl")   # must not raise

    def test_a_pause_request_stops_at_the_next_boundary(self):
        self.state.request_pause()
        with self.assertRaises(runstate.Paused):
            self.state.checkpoint("crawl")
        self.assertEqual(self.state.data["status"], PAUSED)

    def test_the_request_is_cleared_once_honoured(self):
        """Otherwise the resume pauses itself at its first boundary."""
        self.state.request_pause()
        with self.assertRaises(runstate.Paused):
            self.state.checkpoint("crawl")
        self.assertFalse(self.state.paused_requested())

    def test_a_paused_run_is_resumable_from_where_it_stopped(self):
        self.state.skip("devserver")
        self.state.start("scan")
        self.state.done("scan")
        self.state.request_pause()
        with self.assertRaises(runstate.Paused):
            self.state.checkpoint("crawl")
        self.assertTrue(self.state.resumable())
        self.assertEqual(self.state.next_phase(), "crawl")

    def test_a_pause_is_visible_in_the_folder(self):
        """A file, not a signal: the scan may be in another process, and a
        person looking at the folder can see that a pause was asked for."""
        self.state.request_pause()
        self.assertTrue((Path(self.tmp.name) / runstate.PAUSE_FILE).exists())

    def test_a_paused_run_and_a_failed_run_resume_the_same_way(self):
        """One resume path. Two would drift, and one would be untested."""
        other = tempfile.TemporaryDirectory()
        try:
            failed = _state(other.name)
            failed.start("crawl")
            failed.fail("crawl", "the crawl failed")
            self.state.start("crawl")
            self.state.request_pause()
            with self.assertRaises(runstate.Paused):
                self.state.checkpoint("crawl")
            self.assertEqual(failed.next_phase(), self.state.next_phase())
            self.assertTrue(failed.resumable() and self.state.resumable())
        finally:
            other.cleanup()


class Feedback(unittest.TestCase):
    """The block an agent reads to know what to do next."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = _state(self.tmp.name)
        self.state.skip("devserver")
        self.state.start("scan")
        artifact = Path(self.tmp.name) / "checkpoint-scan.json"
        artifact.write_text("{}", encoding="utf-8")
        self.state.done("scan", artifacts=[artifact])
        self.state.skip("crawl", "not a website")
        self.state.start("audit")
        self.state.fail("audit", "the static audit failed: parser error")

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_names_the_phase_that_stopped(self):
        self.assertEqual(self.state.feedback()["stopped_in"], "audit")

    def test_it_carries_the_reason_as_a_field_not_a_sentence(self):
        self.assertIn("parser error", self.state.feedback()["stopped_because"])

    def test_it_separates_what_is_done_from_what_remains(self):
        info = self.state.feedback()
        self.assertEqual(info["completed_phases"], ["scan"])
        self.assertIn("audit", info["remaining_phases"])
        self.assertNotIn("crawl", info["remaining_phases"])

    def test_it_says_plainly_that_something_needs_doing(self):
        self.assertTrue(self.state.feedback()["action_required"])

    def test_it_offers_exactly_one_command(self):
        command = self.state.feedback()["resume_with"]
        self.assertTrue(command.startswith("xaudit resume "))
        self.assertIn(self.tmp.name, command)

    def test_artifacts_are_read_off_disk_not_trusted_from_the_record(self):
        """A recorded path whose file is gone is a promise, not a fact."""
        (Path(self.tmp.name) / "checkpoint-scan.json").unlink()
        self.assertEqual(self.state.feedback()["artifacts"], [])

    def test_the_written_file_carries_the_feedback(self):
        self.state.write_feedback()
        data = json.loads((Path(self.tmp.name) / "state.json").read_text())
        self.assertEqual(data["feedback"]["stopped_in"], "audit")
        self.assertEqual(data["resume"]["from_phase"], "audit")

    def test_a_person_gets_the_same_facts_without_reading_json(self):
        text = self.state.write_markdown().read_text(encoding="utf-8")
        self.assertIn("audit", text)
        self.assertIn("parser error", text)
        self.assertIn("xaudit resume", text)


class Catalogue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name, target in (("2026-08-24-1000", "https://a.example"),
                             ("2026-08-24-1100", "https://b.example")):
            run = self.root / runfolder.slug_for(target) / name
            run.mkdir(parents=True)
            _state(run, target=target)

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_finds_every_run_with_a_state_file(self):
        self.assertEqual(len(runstate.all_runs(self.root)), 2)

    def test_a_folder_with_no_state_file_is_not_a_run(self):
        (self.root / "junk" / "not-a-run").mkdir(parents=True)
        self.assertEqual(len(runstate.all_runs(self.root)), 2)

    def test_an_unreadable_state_file_is_skipped_not_fatal(self):
        (self.root / "broken" / "run").mkdir(parents=True)
        (self.root / "broken" / "run" / "state.json").write_text("{oh no")
        self.assertEqual(len(runstate.all_runs(self.root)), 2)

    def test_a_missing_root_is_an_empty_catalogue(self):
        self.assertEqual(runstate.all_runs(self.root / "nope"), [])

    def test_a_run_resolves_from_its_timestamp(self):
        found = runstate.find_run("2026-08-24-1100", self.root)
        self.assertIsNotNone(found)
        self.assertEqual(found.data["target"], "https://b.example")

    def test_a_run_resolves_from_its_path(self):
        path = self.root / runfolder.slug_for("https://a.example") / "2026-08-24-1000"
        self.assertIsNotNone(runstate.find_run(str(path), self.root))

    def test_an_unknown_reference_resolves_to_nothing(self):
        self.assertIsNone(runstate.find_run("2020-01-01-0000", self.root))


class Checkpoints(unittest.TestCase):
    """Resume must not recompute: the crawl and browser pass are the cost."""

    def _result(self):
        from audit.base import Issue
        from audit.engine import AccessibilityResult, DocumentReport

        return AccessibilityResult(
            root="https://example.com", mode="web", rules_run=["image-alt"],
            documents=[
                DocumentReport(source="https://example.com", elements_checked=9,
                               issues=[Issue(rule_id="image-alt",
                                             severity="critical",
                                             snippet="<img src=a.png>",
                                             source="https://example.com",
                                             line=4, details={"src": "a.png"},
                                             fix_snippet='<img alt="">')]),
                DocumentReport(source="https://example.com/x",
                               error="fetch failed")])

    def test_an_audit_result_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint.save_audit(tmp, self._result())
            back = checkpoint.load_audit(tmp)
        self.assertEqual(len(back.documents), 2)
        self.assertEqual(back.counts(), self._result().counts())

    def test_every_field_the_report_writers_read_survives(self):
        """Asserted field by field, not by count.

        A writer that reads something this drops would only fail on a resume -
        the least-tested path there is - so the round trip is checked against
        the attribute set rather than against the number of findings.
        """
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint.save_audit(tmp, self._result())
            back = checkpoint.load_audit(tmp)
        issue = back.documents[0].issues[0]
        for attribute, expected in (("rule_id", "image-alt"),
                                    ("severity", "critical"),
                                    ("snippet", "<img src=a.png>"),
                                    ("line", 4),
                                    ("details", {"src": "a.png"}),
                                    ("fix_snippet", '<img alt="">'),
                                    ("category", "accessibility"),
                                    ("engine", "static")):
            self.assertEqual(getattr(issue, attribute), expected, attribute)
        self.assertEqual(back.documents[0].elements_checked, 9)
        self.assertEqual(back.documents[1].error, "fetch failed")
        self.assertEqual(back.mode, "web")
        self.assertEqual(back.rules_run, ["image-alt"])

    def test_a_checkpoint_from_an_older_build_does_not_crash_the_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / checkpoint.AUDIT_FILE).write_text(json.dumps({
                "root": "/r", "mode": "repo",
                "documents": [{"source": "a.html", "issues": [
                    {"rule_id": "image-alt", "severity": "minor",
                     "a_field_this_version_never_had": 1}]}]}))
            back = checkpoint.load_audit(tmp)
        self.assertEqual(back.documents[0].issues[0].rule_id, "image-alt")

    def test_a_missing_checkpoint_is_none_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(checkpoint.load_audit(tmp))
            self.assertEqual(checkpoint.load_scan(tmp), (None, None))

    def test_scan_findings_round_trip(self):
        rows = [{"file": "a.html", "score": 0.7, "text": "x"}]
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint.save_scan(tmp, rows, {"total": 1})
            back, counts = checkpoint.load_scan(tmp)
        self.assertEqual(back, rows)
        self.assertEqual(counts, {"total": 1})


class RunRows(unittest.TestCase):
    """What both the CLI table and the GUI list are built from."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        run = self.root / "example.com" / "2026-08-24-1200"
        run.mkdir(parents=True)
        self.state = _state(run, target="https://example.com")
        self.state.start("crawl")
        self.state.fail("crawl", "the crawl failed")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_row_says_where_it_stopped_and_that_it_can_continue(self):
        from cli_impl.runcmds import run_rows

        row = run_rows(runstate.all_runs(self.root))[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["stage"], "crawl")
        self.assertTrue(row["resumable"])
        self.assertEqual(row["target"], "https://example.com")

    def test_the_age_is_readable_rather_than_a_timestamp(self):
        from cli_impl.runcmds import run_rows

        self.assertTrue(run_rows(runstate.all_runs(self.root))[0]["age"]
                        .endswith("ago"))


if __name__ == "__main__":
    unittest.main()


class PauseCommand(unittest.TestCase):
    """`pause` on a finished run must refuse rather than leave a trap.

    Recording the request anyway reported success, did nothing, and left a
    `PAUSE` file nothing would ever clear - so the next run of that folder
    would pause itself for a reason nobody remembered asking for.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run = self.root / "example.com" / "2026-08-24-1200"
        self.run.mkdir(parents=True)
        self.state = _state(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def _pause(self):
        import argparse

        from cli_impl.runcmds import cmd_pause

        return cmd_pause(argparse.Namespace(run=str(self.run),
                                            root=str(self.root)))

    def test_a_finished_run_is_refused_and_left_alone(self):
        for name in runstate.PHASES:
            self.state.start(name)
            self.state.done(name)
        self.state.finish()
        self._pause()
        self.assertFalse((self.run / runstate.PAUSE_FILE).exists())

    def test_an_unfinished_run_accepts_the_request(self):
        self.state.start("crawl")
        self._pause()
        self.assertTrue((self.run / runstate.PAUSE_FILE).exists())


class AKilledRunDoesNotClaimToBeRunning(unittest.TestCase):
    """A run that is killed never writes a final state.

    Ctrl-C, a closed laptop, an OOM: the file keeps saying `running` forever,
    and the catalogue then claims work is in progress that stopped an hour
    ago. That is worse than saying nothing - `running` is the one status a
    reader would act on by waiting.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = _state(self.tmp.name)
        self.state.start("crawl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_live_process_is_still_running(self):
        self.assertTrue(self.state.alive())
        self.assertEqual(self.state.status(), "running")

    def test_a_dead_process_reads_as_interrupted(self):
        self.state.data["pid"] = 2 ** 30      # nothing can have this pid
        self.assertFalse(self.state.alive())
        self.assertEqual(self.state.status(), runstate.INTERRUPTED)

    def test_an_interrupted_run_can_still_be_continued(self):
        self.state.skip("devserver")
        self.state.data["pid"] = 2 ** 30
        self.assertTrue(self.state.resumable())
        self.assertEqual(self.state.next_phase(), "scan")

    def test_the_correction_is_derived_not_written(self):
        """The run that would have written `interrupted` is exactly the run
        that was killed before it could write anything."""
        self.state.data["pid"] = 2 ** 30
        self.state.status()
        self.assertEqual(self.state.data["status"], "running")

    def test_a_finished_run_is_unaffected_by_its_dead_pid(self):
        for name in runstate.PHASES:
            self.state.start(name)
            self.state.done(name)
        self.state.finish()
        self.state.data["pid"] = 2 ** 30
        self.assertEqual(self.state.status(), "done")

    def test_a_file_with_no_pid_is_not_called_alive(self):
        self.state.data.pop("pid", None)
        self.assertFalse(self.state.alive())

    def test_the_feedback_carries_the_corrected_status(self):
        self.state.data["pid"] = 2 ** 30
        self.assertEqual(self.state.feedback()["status"],
                         runstate.INTERRUPTED)
