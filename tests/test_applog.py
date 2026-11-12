"""The log the app keeps about itself.

Written because the first question after a run that went wrong is "what did
it actually do", and stderr is gone by then. These check the three things
that decide whether such a log is worth having: it records, it cleans up
after itself, and it never breaks the thing it is logging.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import applog


class LogDirectory(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("XAUDIT_LOG_DIR")
        self.directory = Path(tempfile.mkdtemp())
        os.environ["XAUDIT_LOG_DIR"] = str(self.directory)
        applog._reset_for_tests()

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("XAUDIT_LOG_DIR", None)
        else:
            os.environ["XAUDIT_LOG_DIR"] = self._previous
        applog._reset_for_tests()


class Writing(LogDirectory):
    def test_a_record_survives_the_process_that_wrote_it(self):
        applog.info("scan.start", target="https://x/", pages=4)
        records = applog.read_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "scan.start")
        self.assertEqual(records[0]["pages"], 4)

    def test_the_run_id_travels_with_every_record(self):
        applog.set_run("run-7")
        applog.info("a")
        applog.info("b")
        self.assertEqual({r["run"] for r in applog.read_records()}, {"run-7"})

    def test_debug_is_off_unless_asked_for(self):
        applog.debug("noisy")
        self.assertEqual(applog.read_records(), [])

    def test_a_filter_by_level_keeps_the_worse_ones(self):
        applog.info("quiet")
        applog.error("loud")
        found = [r["event"] for r in applog.read_records(level="warning")]
        self.assertEqual(found, ["loud"])

    def test_one_record_cannot_become_the_whole_file(self):
        applog.info("big", blob="x" * (applog.MAX_RECORD_BYTES * 2))
        line = (applog.file_for()).read_text(encoding="utf-8").strip()
        self.assertLess(len(line), applog.MAX_RECORD_BYTES * 2)
        self.assertTrue(json.loads(line)["truncated"])

    def test_an_object_json_cannot_serialise_does_not_lose_the_record(self):
        applog.info("odd", value=object())
        self.assertEqual(len(applog.read_records()), 1)

    def test_logging_never_raises(self):
        # The one thing this module must not do is become the reason a scan
        # fails, so an unwritable directory is silence, not an exception.
        os.environ["XAUDIT_LOG_DIR"] = "/proc/nonexistent/xaudit"
        applog._reset_for_tests()
        applog.info("into the void")


class CleaningUp(LogDirectory):
    def _old_file(self, days: int) -> Path:
        stamp = datetime.now(timezone.utc) - timedelta(days=days)
        path = applog.file_for(stamp)
        path.write_text('{"event":"old"}\n', encoding="utf-8")
        os.utime(path, (stamp.timestamp(), stamp.timestamp()))
        return path

    def test_a_file_past_the_retention_window_is_removed(self):
        stale = self._old_file(applog.RETENTION_DAYS + 3)
        fresh = self._old_file(1)
        applog.clean()
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_the_directory_is_trimmed_to_its_budget_oldest_first(self):
        older = self._old_file(3)
        newer = self._old_file(1)
        older.write_text("x" * 4000, encoding="utf-8")
        newer.write_text("y" * 4000, encoding="utf-8")
        applog.clean(max_total_bytes=5000)
        # The newest file is what an investigation is about, so it is the
        # last thing to go.
        self.assertFalse(older.exists())
        self.assertTrue(newer.exists())

    def test_cleaning_runs_once_per_process_not_per_record(self):
        calls = []
        original = applog.clean
        applog.clean = lambda *a, **k: calls.append(1) or {}
        try:
            applog.info("a")
            applog.info("b")
            applog.info("c")
        finally:
            applog.clean = original
        self.assertEqual(len(calls), 1)


class Reading(LogDirectory):
    def test_a_torn_line_is_shown_rather_than_dropped(self):
        applog.file_for().write_text('{"event":"good"}\n{"event":"tor',
                                     encoding="utf-8")
        events = [r["event"] for r in applog.read_records()]
        self.assertIn("unparsed", events)
        self.assertIn("good", events)

    def test_the_summary_says_where_and_how_much(self):
        applog.info("a")
        summary = applog.summary()
        self.assertEqual(summary["directory"], str(self.directory))
        self.assertGreater(summary["bytes"], 0)
        self.assertEqual(summary["retention_days"], applog.RETENTION_DAYS)

    def test_every_surface_formats_the_same_record(self):
        applog.info("scan.start", target="https://x/")
        line = applog.format_line(applog.read_records()[0])
        self.assertIn("scan.start", line)
        self.assertIn("target=https://x/", line)

    def test_known_log_labels_follow_the_interface_language(self):
        from i18n.translations import t

        record = {"at": "2026-01-02T03:04:05Z", "level": "warning",
                  "event": "command.failed", "command": "audit"}
        for lang in ("uk", "en", "it"):
            with self.subTest(lang=lang):
                line = applog.format_line(record, lang)
                self.assertIn(t("tui_log_level_warning", lang), line)
                self.assertIn(t("tui_log_event_command_failed", lang), line)
                self.assertIn("command=audit", line)


if __name__ == "__main__":
    unittest.main()
