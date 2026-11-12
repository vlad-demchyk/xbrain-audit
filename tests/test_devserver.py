"""Starting a repo's own dev server, so `fullscan` can read the render.

`DevServerProcess.wait_ready`'s loop is driven with fake `time` and a fake
`Popen`-alike, not a real subprocess, for the same reason
`tests/test_render_activity.py` drives `ActivityWatch` with a fake clock: the
part worth testing is "what counts as ready and what counts as stalled", and
a real subprocess would make that slow and flaky instead of exercising it.
One real, opt-in end-to-end test proves the actual `Popen` + thread + kill
wiring works; it is gated so the ordinary suite stays fast and hermetic.
"""
from __future__ import annotations

import os
import shlex
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import devserver
from devserver import (
    DevServerNeverReady,
    DevServerPlan,
    DevServerProcess,
    DevServerUnavailable,
    DjangoStack,
    NodeStack,
    RailsStack,
    detect_stack,
)


class DetectStack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_package_json_is_node(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        self.assertIsInstance(detect_stack(self.repo), NodeStack)

    def test_manage_py_is_django(self):
        (self.repo / "manage.py").write_text("", encoding="utf-8")
        self.assertIsInstance(detect_stack(self.repo), DjangoStack)

    def test_gemfile_alone_is_not_rails(self):
        """`bin/rails` has to exist too - a bare Gemfile is any Ruby project."""
        (self.repo / "Gemfile").write_text("", encoding="utf-8")
        self.assertIsNone(detect_stack(self.repo))

    def test_gemfile_and_bin_rails_is_rails(self):
        (self.repo / "Gemfile").write_text("", encoding="utf-8")
        (self.repo / "bin").mkdir()
        (self.repo / "bin" / "rails").write_text("", encoding="utf-8")
        self.assertIsInstance(detect_stack(self.repo), RailsStack)

    def test_an_empty_repo_has_no_stack(self):
        self.assertIsNone(detect_stack(self.repo))

    def test_node_is_checked_before_django(self):
        """Order is data, not an accident - the first match wins."""
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "manage.py").write_text("", encoding="utf-8")
        self.assertIsInstance(detect_stack(self.repo), NodeStack)


class NodeStackBehaviour(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.stack = NodeStack()

    def tearDown(self):
        self.tmp.cleanup()

    def test_deps_satisfied_by_node_modules(self):
        self.assertFalse(self.stack.deps_satisfied(self.repo))
        (self.repo / "node_modules").mkdir()
        self.assertTrue(self.stack.deps_satisfied(self.repo))

    def test_package_manager_follows_the_lockfile(self):
        (self.repo / "pnpm-lock.yaml").write_text("", encoding="utf-8")
        self.assertEqual(self.stack._package_manager(self.repo), "pnpm")
        (self.repo / "pnpm-lock.yaml").unlink()
        (self.repo / "yarn.lock").write_text("", encoding="utf-8")
        self.assertEqual(self.stack._package_manager(self.repo), "yarn")
        (self.repo / "yarn.lock").unlink()
        self.assertEqual(self.stack._package_manager(self.repo), "npm")

    def test_start_argv_prefers_dev_then_start_then_serve(self):
        import json

        (self.repo / "package.json").write_text(
            json.dumps({"scripts": {"start": "node x.js", "serve": "y"}}),
            encoding="utf-8")
        with patch("shutil.which", return_value="/usr/bin/npm"):
            argv = self.stack.start_argv(self.repo, None)
        # The *name* "start" is read; the *value* "node x.js" is never run -
        # npm resolves it, argv stays ["npm", "run", "start"].
        self.assertEqual(argv, ["/usr/bin/npm", "run", "start"])

    def test_start_argv_never_runs_the_scripts_value_directly(self):
        import json

        (self.repo / "package.json").write_text(
            json.dumps({"scripts": {"dev": "rm -rf /"}}), encoding="utf-8")
        with patch("shutil.which", return_value="/usr/bin/npm"):
            argv = self.stack.start_argv(self.repo, None)
        self.assertEqual(argv, ["/usr/bin/npm", "run", "dev"])
        self.assertNotIn("rm -rf /", argv)

    def test_no_runnable_script_raises(self):
        import json

        (self.repo / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8")
        with patch("shutil.which", return_value="/usr/bin/npm"):
            with self.assertRaises(DevServerUnavailable):
                self.stack.start_argv(self.repo, None)

    def test_malformed_manifest_raises(self):
        (self.repo / "package.json").write_text("{not json", encoding="utf-8")
        with patch("shutil.which", return_value="/usr/bin/npm"):
            with self.assertRaises(DevServerUnavailable):
                self.stack.start_argv(self.repo, None)

    def test_missing_npm_binary_raises(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        with patch("shutil.which", return_value=None):
            with self.assertRaises(DevServerUnavailable):
                self.stack.install_argv(self.repo)


class DjangoStackBehaviour(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.stack = DjangoStack()

    def tearDown(self):
        self.tmp.cleanup()

    def test_python_prefers_the_repos_own_venv(self):
        venv_python = self.repo / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("", encoding="utf-8")
        self.assertEqual(self.stack._python(self.repo), str(venv_python))

    def test_python_falls_back_to_the_running_interpreter(self):
        import sys

        self.assertEqual(self.stack._python(self.repo), sys.executable)

    def test_deps_not_satisfied_without_django_importable(self):
        # This test's own interpreter has no reason to have Django installed.
        self.assertFalse(self.stack.deps_satisfied(self.repo))

    def test_install_argv_needs_requirements_txt(self):
        with self.assertRaises(DevServerUnavailable):
            self.stack.install_argv(self.repo)
        (self.repo / "requirements.txt").write_text("Django\n", encoding="utf-8")
        argv = self.stack.install_argv(self.repo)
        self.assertIn("requirements.txt", argv[-1])

    def test_start_argv_uses_the_chosen_port(self):
        argv = self.stack.start_argv(self.repo, 4242)
        self.assertIn("127.0.0.1:4242", argv)


class RailsStackBehaviour(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.stack = RailsStack()

    def tearDown(self):
        self.tmp.cleanup()

    def test_deps_satisfied_reads_bundle_check(self):
        with patch("shutil.which", return_value="/usr/bin/bundle"), \
             patch("subprocess.run") as run:
            run.return_value.returncode = 0
            self.assertTrue(self.stack.deps_satisfied(self.repo))
            run.return_value.returncode = 1
            self.assertFalse(self.stack.deps_satisfied(self.repo))

    def test_missing_bundle_raises(self):
        with patch("shutil.which", return_value=None):
            with self.assertRaises(DevServerUnavailable):
                self.stack.deps_satisfied(self.repo)

    def test_start_argv_uses_the_chosen_port(self):
        argv = self.stack.start_argv(self.repo, 4242)
        self.assertEqual(argv, ["bin/rails", "server", "-p", "4242", "-b", "127.0.0.1"])


class ReadyPatternMatching(unittest.TestCase):
    """Real dev-server banners, matched directly - no process involved."""

    def test_vite_style_banner(self):
        self.assertTrue(devserver._READY_RE.search("  ➕  Local:   http://localhost:5173/"))

    def test_django_style_banner(self):
        self.assertTrue(
            devserver._READY_RE.search("Starting development server at http://127.0.0.1:8000/"))

    def test_unrelated_output_does_not_match(self):
        self.assertIsNone(devserver._READY_RE.search("Compiling... done in 400ms"))


class PickPort(unittest.TestCase):
    def test_a_port_is_returned_and_usable(self):
        port = devserver.pick_port()
        self.assertIsInstance(port, int)
        self.assertGreater(port, 0)


class StartCommandOverrideParsing(unittest.TestCase):
    """`--start-command` is split client-side into a fixed argv - never a
    shell string - before it reaches `subprocess.Popen`."""

    def test_a_simple_command(self):
        self.assertEqual(shlex.split("npm run dev:custom"),
                         ["npm", "run", "dev:custom"])

    def test_quoted_arguments_survive(self):
        self.assertEqual(shlex.split('npm run "dev:custom thing"'),
                         ["npm", "run", "dev:custom thing"])

    def test_a_bare_script_name(self):
        self.assertEqual(shlex.split("./start.sh"), ["./start.sh"])


class _FakePopen:
    """Just enough of `subprocess.Popen` for `wait_ready`'s loop: `poll()`
    and `returncode`. No real process, no thread, no stdout pipe."""

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode


def _process(*, fixed_port=None) -> DevServerProcess:
    plan = DevServerPlan(stack="fake", start_argv=["true"], cwd=Path("."),
                         fixed_port=fixed_port)
    return DevServerProcess(popen=_FakePopen(), plan=plan)


class WaitReadyLoop(unittest.TestCase):
    """Driven with a fake clock and a fake process - the same reason
    `ActivityWatch` is tested that way: real time would make the stall path
    either slow or flaky, and the part worth testing is the decision, not
    the sleeping."""

    def test_a_matching_line_already_present_is_found_immediately(self):
        proc = _process()
        proc._lines.append("  Local:   http://localhost:5173/")
        with patch("devserver.time.sleep"):
            url = proc.wait_ready(timeout_s=5)
        # The regex stops at the port - a trailing path is not part of the
        # server's address, so it is not part of the match.
        self.assertEqual(url, "http://localhost:5173")

    def test_the_process_exiting_before_ready_raises_with_the_tail(self):
        proc = _process()
        proc._lines.append("Error: something went wrong")
        proc.popen.returncode = 1
        with patch("devserver.time.sleep"):
            with self.assertRaises(DevServerNeverReady) as ctx:
                proc.wait_ready(timeout_s=5)
        self.assertIn("exited with code 1", str(ctx.exception))
        self.assertIn("something went wrong", str(ctx.exception))

    def test_a_fixed_port_becoming_reachable_is_found(self):
        proc = _process(fixed_port=4242)
        with patch("devserver.time.sleep"), \
             patch("devserver._port_open", return_value=True):
            url = proc.wait_ready(timeout_s=5)
        self.assertEqual(url, "http://127.0.0.1:4242")

    def test_stalled_output_raises_before_the_full_timeout(self):
        """No new line for `STALL_SECONDS`, well inside a much longer
        overall timeout - the stall clock is what fires, not the deadline.

        `_last_line_at` is moved into the fake clock's frame of reference,
        and that is the whole point of this line. It is stamped at
        construction with the *real* `time.monotonic`, whose reference point
        Python explicitly leaves undefined - and the two interpreters this
        project has run on disagree about it: 3.9 starts near zero per
        process, 3.14 returns seconds since boot. Left alone, the idle time
        this test measures is `0 - 351537`, the stall never fires, and the
        failure reads like a bug in the server loop rather than a test
        comparing two different clocks.
        """
        proc = _process()
        proc._lines.append("starting up...")
        clock = [0.0]
        proc._last_line_at = clock[0]

        def fake_monotonic():
            clock[0] += devserver.STALL_SECONDS  # one poll past the stall window
            return clock[0]

        with patch("devserver.time.sleep"), \
             patch("devserver.time.monotonic", side_effect=fake_monotonic):
            with self.assertRaises(DevServerNeverReady) as ctx:
                proc.wait_ready(timeout_s=10_000)
        self.assertIn("no output for", str(ctx.exception))

    def test_never_ready_within_the_timeout_raises(self):
        proc = _process()
        clock = [0.0]

        def fake_monotonic():
            clock[0] += 1000.0
            return clock[0]

        with patch("devserver.time.sleep"), \
             patch("devserver.time.monotonic", side_effect=fake_monotonic):
            with self.assertRaises(DevServerNeverReady) as ctx:
                proc.wait_ready(timeout_s=1)
        self.assertIn("not ready after", str(ctx.exception))


@unittest.skipUnless(os.environ.get("XAUDIT_LIVE_TESTS"),
                     "spawns a real subprocess; run with "
                     "XAUDIT_LIVE_TESTS=1 to exercise the actual "
                     "Popen + thread + kill wiring end to end")
class RealProcessEndToEnd(unittest.TestCase):
    def test_a_real_process_is_started_read_and_stopped(self):
        port = devserver.pick_port()
        plan = DevServerPlan(
            stack="fake-live", cwd=Path("."), fixed_port=port,
            start_argv=["python3", "-c",
                       f"import socket,time;"
                       f"s=socket.socket();"
                       f"s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
                       f"s.bind(('127.0.0.1',{port}));s.listen(1);"
                       f"time.sleep(5)"])
        proc = DevServerProcess.start(plan)
        try:
            url = proc.wait_ready(timeout_s=10)
            self.assertEqual(url, f"http://127.0.0.1:{port}")
        finally:
            proc.stop()
        # A short wait for the SIGTERM to land - stop() itself blocks on it,
        # but the OS reaping the zombie can trail by an instant.
        time.sleep(0.2)
        self.assertIsNotNone(proc.popen.poll())


if __name__ == "__main__":
    unittest.main()
