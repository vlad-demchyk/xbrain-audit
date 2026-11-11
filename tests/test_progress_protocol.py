"""`--progress jsonl`: the run, as an agent reads it while it happens.

These run the **real CLI** in a subprocess rather than calling the emitters
directly. That is the whole point of the file: the risk this protocol carries
is not that `progress.emit` writes bad JSON, it is that some line of a real
run never went through `progress` at all and lands in the stream as prose. A
unit test of the module cannot see that; a real `fullscan` can.

The three properties, in order of what breaks first:

1. every line of the stream parses, and its `event` is one this module
   declares (`progress.EVENTS`) - a new event added without declaring it
   fails here;
2. the run is bracketed - `run.start` first, `run.end` last, with an exit
   code that matches the process's own;
3. without the flag nothing changed - the same human lines, no JSON.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import progress  # noqa: E402

#: A folder with something to find in it, so the run reaches every phase a
#: repository target has: scan, audit, reports.
TARGET = ROOT / "simulations" / "mixed-problems"


def _run(*extra, target=None, command="fullscan"):
    """A real run, with the browser off so it is seconds not minutes.

    `--no-update-check` because the update hint is written before the command
    starts and would be the one line in the stream nobody emitted.
    """
    argv = [sys.executable, str(ROOT / "cli.py"), command,
            str(target or TARGET), "--no-update-check", *extra]
    if command in ("fullscan", "audit"):
        argv.insert(4, "--no-browser")
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=300,
                          cwd=str(ROOT))


def _objects(stderr: str):
    """Every JSON object in the stream, in order.

    Lines that do not parse are handed back separately rather than ignored:
    Qt writes its own diagnostics straight to file descriptor 2 (`GPUInfo not
    initialized`), so "nothing else may appear" is not a property this can
    assert - but "nothing else that *we* wrote" is, and the second list is
    what the tests below check that against.
    """
    parsed, other = [], []
    for line in stderr.splitlines():
        if not line.strip():
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            other.append(line)
    return parsed, other


class ProgressStreamShape(unittest.TestCase):
    """What every line of the stream must be."""

    @classmethod
    def setUpClass(cls):
        cls.done = _run("--progress", "jsonl")
        cls.events, cls.other = _objects(cls.done.stderr)

    def test_the_run_produced_a_stream_at_all(self):
        self.assertTrue(self.events,
                        f"no JSON on stderr; got: {self.done.stderr[:400]}")

    def test_every_event_is_one_the_module_declares(self):
        for record in self.events:
            self.assertIn("event", record, record)
            self.assertIn(record["event"], progress.EVENTS, record)

    def test_every_event_is_timestamped(self):
        for record in self.events:
            self.assertIn("ts", record, record)
            # ISO 8601 with an offset, so a reader can order two runs.
            self.assertRegex(record["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:")

    def test_every_notice_names_a_kind_the_module_declares(self):
        kinds = [r["kind"] for r in self.events if r["event"] == "notice"]
        self.assertTrue(kinds, "a real run says nothing at all")
        for kind in kinds:
            self.assertIn(kind, progress.NOTICES)

    def test_every_stage_names_a_stage_and_a_state(self):
        stages = [r for r in self.events if r["event"] == "stage"]
        self.assertTrue(stages)
        for record in stages:
            self.assertIn(record["name"], progress.STAGES, record)
            self.assertIn(record["state"], progress.STAGE_STATES, record)

    def test_no_line_of_ours_escaped_the_stream(self):
        """Anything unparsed must not be something this codebase printed.

        The human output is recognisable: it starts with `#`. A `#` line in
        the JSONL stream is a call site that still prints instead of
        emitting, which is exactly the drift this protocol exists to stop.
        """
        ours = [line for line in self.other if line.lstrip().startswith("#")]
        self.assertEqual(ours, [], f"human lines in the jsonl stream: {ours}")


class ProgressStreamBrackets(unittest.TestCase):
    """The run says when it began and how it ended."""

    @classmethod
    def setUpClass(cls):
        cls.done = _run("--progress", "jsonl")
        cls.events, _ = _objects(cls.done.stderr)

    def test_it_opens_with_run_start(self):
        self.assertEqual(self.events[0]["event"], "run.start")
        self.assertEqual(self.events[0]["command"], "fullscan")
        self.assertTrue(self.events[0]["version"])

    def test_it_closes_with_run_end_carrying_the_exit_code(self):
        last = self.events[-1]
        self.assertEqual(last["event"], "run.end")
        self.assertEqual(last["exit_code"], self.done.returncode)

    def test_run_end_carries_the_numbers_the_json_reports(self):
        """The stream's summary and the document's summary are one number.

        Two counts of the same run that disagree is worse than one count, and
        `run.end` is read by whatever did not wait for stdout.
        """
        last = self.events[-1]
        document = json.loads(self.done.stdout)
        self.assertEqual(last["counts"]["total_findings"],
                         document["summary"]["total_findings"])

    def test_a_failed_run_still_ends(self):
        done = _run("--progress", "jsonl", target=ROOT / "no-such-folder")
        events, _ = _objects(done.stderr)
        self.assertEqual(events[-1]["event"], "run.end")
        self.assertEqual(events[-1]["exit_code"], done.returncode)
        self.assertNotEqual(done.returncode, 0)
        self.assertTrue([r for r in events
                         if r["event"] == "notice" and r["kind"] == "error"])


class ProgressStagesAndPages(unittest.TestCase):
    """The events that say work is happening, not that it happened."""

    @classmethod
    def setUpClass(cls):
        cls.events, _ = _objects(_run("--progress", "jsonl").stderr)

    def test_the_phases_a_repository_run_has_all_report_themselves(self):
        seen = {(r["name"], r["state"]) for r in self.events
                if r["event"] == "stage"}
        for name in ("scan", "audit", "report"):
            self.assertIn((name, "begin"), seen, f"{name} never began")
            self.assertIn((name, "end"), seen, f"{name} never ended")

    def test_each_file_read_is_an_event_with_its_place_in_the_walk(self):
        files = [r for r in self.events if r["event"] == "file"]
        self.assertTrue(files, "a folder scan read no files")
        self.assertEqual([r["n"] for r in files],
                         list(range(1, len(files) + 1)))
        for record in files:
            self.assertTrue(record["path"])


class FindingsAreOptIn(unittest.TestCase):
    """One event per finding is a report, so it is asked for."""

    def test_plain_jsonl_says_nothing_about_individual_findings(self):
        events, _ = _objects(_run("--progress", "jsonl").stderr)
        self.assertEqual([r for r in events if r["event"] == "finding"], [])

    def test_jsonl_findings_emits_one_per_finding_and_counts_the_same(self):
        done = _run("--progress", "jsonl=findings")
        events, _ = _objects(done.stderr)
        findings = [r for r in events if r["event"] == "finding"]
        self.assertTrue(findings)
        total = json.loads(done.stdout)["summary"]["total_findings"]
        self.assertEqual(len(findings), total)
        for record in findings:
            self.assertIn(record["kind"], ("content", "audit"))
            self.assertTrue(record["rule"])


class WithoutTheFlagNothingChanged(unittest.TestCase):
    """The default output is the one that existed before this module."""

    @classmethod
    def setUpClass(cls):
        cls.done = _run()

    def test_stderr_carries_no_json_objects(self):
        events, _ = _objects(self.done.stderr)
        self.assertEqual(events, [],
                         "the human run emitted machine-readable lines")

    def test_the_human_lines_are_the_ones_the_terminal_always_showed(self):
        lines = [l for l in self.done.stderr.splitlines()
                 if l.startswith("#")]
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("# report: ", joined)
        self.assertIn("# run folder: ", joined)

    def test_the_document_on_stdout_is_unchanged_by_the_flag(self):
        """The flag is about stderr. stdout must not move.

        Compared on the shape rather than byte for byte: the run folder is
        dated, so two runs differ in their paths and in nothing else.
        """
        quiet = json.loads(self.done.stdout)
        loud = json.loads(_run("--progress", "jsonl").stdout)
        self.assertEqual(quiet["summary"], loud["summary"])
        self.assertEqual(quiet["audit"]["counts"], loud["audit"]["counts"])


class EveryCommandThatRunsSpeaksTheProtocol(unittest.TestCase):
    """Not only `fullscan`. `scan` and `audit` are runs too.

    An agent that can watch one command and not the other has to know which
    is which, which is the same as having no protocol.
    """

    def _stream(self, command, *extra):
        done = _run(*extra, command=command)
        events, other = _objects(done.stderr)
        ours = [line for line in other if line.lstrip().startswith("#")]
        self.assertEqual(ours, [], f"{command}: human lines in the stream")
        return done, events

    def test_scan_brackets_its_run_and_names_its_target(self):
        done, events = self._stream("scan", "--progress", "jsonl")
        self.assertEqual(events[0]["event"], "run.start")
        self.assertEqual(events[0]["command"], "scan")
        self.assertTrue(events[0]["target"],
                        "a scan reported an empty target")
        self.assertEqual(events[-1]["event"], "run.end")
        self.assertEqual(events[-1]["exit_code"], done.returncode)

    def test_audit_reports_its_stage_and_its_counts(self):
        done, events = self._stream("audit", "--progress", "jsonl")
        stages = {(r["name"], r["state"]) for r in events
                  if r["event"] == "stage"}
        self.assertIn(("audit", "begin"), stages)
        self.assertIn(("audit", "end"), stages)
        self.assertIn("counts", events[-1])


class OneNameMeansOneNumber(unittest.TestCase):
    """`documents` said 4 in one event and 2 in another.

    A page is several documents - its own rules, its response headers, an
    image's provenance - so the two counts are both real and both wanted.
    What is not allowed is calling them the same thing.
    """

    def test_documents_and_sources_agree_across_the_stream(self):
        events, _ = _objects(_run("--progress", "jsonl").stderr)
        end_of_audit = [r for r in events if r["event"] == "stage"
                        and r["name"] == "audit" and r["state"] == "end"]
        self.assertTrue(end_of_audit)
        last = events[-1]
        for field in ("documents", "sources"):
            self.assertEqual(end_of_audit[0][field], last[field],
                             f"{field} changed between the audit and the end")


class ConfigureReadsTheFlag(unittest.TestCase):
    """The one part worth a unit test: what the spellings mean."""

    def tearDown(self):
        progress.reset()

    def test_no_flag_is_the_human_output(self):
        self.assertEqual(progress.configure(None), progress.MODE_HUMAN)
        self.assertFalse(progress.enabled())

    def test_jsonl_turns_the_stream_on_without_findings(self):
        self.assertEqual(progress.configure("jsonl"), progress.MODE_JSONL)
        self.assertTrue(progress.enabled())
        self.assertFalse(progress.wants_findings())

    def test_jsonl_findings_turns_both_on(self):
        progress.configure("jsonl=findings")
        self.assertTrue(progress.enabled())
        self.assertTrue(progress.wants_findings())

    def test_an_unknown_spelling_falls_back_rather_than_raising(self):
        """A progress format is not worth failing a scan over."""
        self.assertEqual(progress.configure("yaml"), progress.MODE_HUMAN)
        self.assertFalse(progress.enabled())


if __name__ == "__main__":
    unittest.main()
