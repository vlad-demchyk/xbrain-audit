"""The CLI's side of starting a dev server: asking, and falling back.

`_confirm_install` mirrors `cli_impl.uninstall._confirm` on purpose - a bare
`input()`, `EOFError` (no interactive stdin) read as "no", and a `--yes`
bypass for a script driving this CLI. `_maybe_start_devserver` is tested
against a fully mocked `devserver` module: what matters here is that every
failure falls back to `(repo_path, None, reason)` rather than raising, since
that fallback is what keeps `fullscan` running the static scan it always
could.
"""
from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cli_impl.fullscan import _confirm_install, _maybe_start_devserver
from devserver import (
    DevServerInstallFailed,
    DevServerNeverReady,
    DevServerPlan,
    DevServerUnavailable,
)


class ConfirmInstall(unittest.TestCase):
    def test_yes_flag_bypasses_the_prompt(self):
        args = argparse.Namespace(yes=True)
        with patch("builtins.input") as prompted:
            self.assertTrue(_confirm_install("node", ["npm", "install"], args))
        prompted.assert_not_called()

    def test_y_answers_yes(self):
        args = argparse.Namespace(yes=False)
        with patch("builtins.input", return_value="y"):
            self.assertTrue(_confirm_install("node", ["npm", "install"], args))

    def test_anything_else_answers_no(self):
        args = argparse.Namespace(yes=False)
        with patch("builtins.input", return_value="nah"):
            self.assertFalse(_confirm_install("node", ["npm", "install"], args))

    def test_no_interactive_stdin_answers_no(self):
        """A script driving this CLI has nothing to answer with - `EOFError`
        must not read as "yes", which is why the bypass is an explicit flag
        rather than "no answer defaults to proceeding"."""
        args = argparse.Namespace(yes=False)
        with patch("builtins.input", side_effect=EOFError):
            self.assertFalse(_confirm_install("node", ["npm", "install"], args))


class MaybeStartDevserver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self, **overrides):
        base = dict(start_command=None, dev_server_port=None, yes=False)
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_no_stack_detected_is_not_a_failure(self):
        with patch("devserver.detect_stack", return_value=None):
            target, proc, reason = _maybe_start_devserver(self._args(), self.repo)
        self.assertEqual(target, self.repo)
        self.assertIsNone(proc)
        self.assertIsNone(reason)  # nothing to explain - this is the ordinary path

    def test_plan_unavailable_falls_back_with_a_reason(self):
        stack = MagicMock(name="node")
        stack.name = "node"
        with patch("devserver.detect_stack", return_value=stack), \
             patch("devserver.build_plan", side_effect=DevServerUnavailable("no npm")):
            target, proc, reason = _maybe_start_devserver(self._args(), self.repo)
        self.assertEqual(target, self.repo)
        self.assertIsNone(proc)
        self.assertIn("no npm", reason)

    def test_declined_install_falls_back_and_never_starts_a_process(self):
        stack = MagicMock(name="node")
        stack.name = "node"
        plan = DevServerPlan(stack="node", start_argv=["npm", "run", "dev"],
                             cwd=Path(self.repo), install_argv=["npm", "install"])
        with patch("devserver.detect_stack", return_value=stack), \
             patch("devserver.build_plan", return_value=plan), \
             patch("cli_impl.fullscan._confirm_install", return_value=False) as confirm, \
             patch("devserver.DevServerProcess") as proc_cls:
            target, proc, reason = _maybe_start_devserver(self._args(), self.repo)
        confirm.assert_called_once()
        proc_cls.start.assert_not_called()
        self.assertEqual(target, self.repo)
        self.assertIsNone(proc)
        self.assertIn("declined", reason)

    def test_failed_install_falls_back(self):
        stack = MagicMock(name="node")
        stack.name = "node"
        plan = DevServerPlan(stack="node", start_argv=["npm", "run", "dev"],
                             cwd=Path(self.repo), install_argv=["npm", "install"])
        with patch("devserver.detect_stack", return_value=stack), \
             patch("devserver.build_plan", return_value=plan), \
             patch("cli_impl.fullscan._confirm_install", return_value=True), \
             patch("devserver.run_install",
                  side_effect=DevServerInstallFailed("exit 1")):
            target, proc, reason = _maybe_start_devserver(self._args(), self.repo)
        self.assertEqual(target, self.repo)
        self.assertIsNone(proc)
        self.assertIn("exit 1", reason)

    def test_server_never_ready_falls_back_and_is_stopped(self):
        stack = MagicMock(name="node")
        stack.name = "node"
        plan = DevServerPlan(stack="node", start_argv=["npm", "run", "dev"],
                             cwd=Path(self.repo))
        fake_proc = MagicMock()
        fake_proc.wait_ready.side_effect = DevServerNeverReady("no output for 30s")
        with patch("devserver.detect_stack", return_value=stack), \
             patch("devserver.build_plan", return_value=plan), \
             patch("devserver.DevServerProcess.start", return_value=fake_proc):
            target, proc, reason = _maybe_start_devserver(self._args(), self.repo)
        fake_proc.stop.assert_called_once()
        self.assertEqual(target, self.repo)
        self.assertIsNone(proc)
        self.assertIn("no output for 30s", reason)

    def test_success_returns_the_url_and_the_running_process(self):
        stack = MagicMock(name="node")
        stack.name = "node"
        plan = DevServerPlan(stack="node", start_argv=["npm", "run", "dev"],
                             cwd=Path(self.repo))
        fake_proc = MagicMock()
        fake_proc.wait_ready.return_value = "http://localhost:5173"
        with patch("devserver.detect_stack", return_value=stack), \
             patch("devserver.build_plan", return_value=plan), \
             patch("devserver.DevServerProcess.start", return_value=fake_proc):
            target, proc, reason = _maybe_start_devserver(self._args(), self.repo)
        self.assertEqual(target, "http://localhost:5173")
        self.assertIs(proc, fake_proc)
        self.assertIsNone(reason)

    def test_start_command_override_is_shlex_split_not_a_shell_string(self):
        stack = MagicMock(name="node")
        stack.name = "node"
        plan = DevServerPlan(stack="node", start_argv=["npm", "run", "dev:custom"],
                             cwd=Path(self.repo))
        fake_proc = MagicMock()
        fake_proc.wait_ready.return_value = "http://localhost:5173"
        with patch("devserver.detect_stack", return_value=stack), \
             patch("devserver.build_plan", return_value=plan) as build_plan, \
             patch("devserver.DevServerProcess.start", return_value=fake_proc):
            _maybe_start_devserver(
                self._args(start_command="npm run dev:custom"), self.repo)
        _, kwargs = build_plan.call_args
        self.assertEqual(kwargs["start_argv"], ["npm", "run", "dev:custom"])


class DevserverIsOffByDefault(unittest.TestCase):
    """`fullscan ./repo` end to end: a repo's own server may already be
    running elsewhere, so a start command found is not a start command run,
    unless `--devserver` says so.

    Built through the real argument parser rather than a hand-listed
    `argparse.Namespace` - `cmd_fullscan` reads dozens of fields, and a
    Namespace built by hand silently drifts from what the CLI actually
    produces the moment a flag is added or renamed.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.report_root = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "package.json").write_text(
            '{"scripts": {"dev": "node server.js"}}', encoding="utf-8")
        self._env_patch = patch.dict(
            "os.environ", {"XAUDIT_REPORT_ROOT": self.report_root.name})
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        self.tmp.cleanup()
        self.report_root.cleanup()

    def _args(self, extra_argv=()):
        import cli

        parser = cli.build_parser()
        return parser.parse_args(["fullscan", str(self.repo), *extra_argv])

    def test_without_the_flag_no_server_is_ever_built(self):
        from cli_impl.fullscan import cmd_fullscan

        args = self._args()
        self.assertFalse(args.devserver)
        with patch("devserver.build_plan") as build_plan, \
             patch("devserver.DevServerProcess.start") as start:
            cmd_fullscan(args)
        build_plan.assert_not_called()
        start.assert_not_called()

    def test_without_the_flag_the_detected_stack_is_still_announced(self):
        import sys
        from io import StringIO

        from cli_impl.fullscan import cmd_fullscan

        args = self._args()
        captured = StringIO()
        real_stderr = sys.stderr
        sys.stderr = captured
        try:
            cmd_fullscan(args)
        finally:
            sys.stderr = real_stderr
        self.assertIn("node detected but not started", captured.getvalue())
        self.assertIn("--devserver", captured.getvalue())

    def test_with_the_flag_a_plan_is_built(self):
        from cli_impl.fullscan import cmd_fullscan

        args = self._args(["--devserver"])
        self.assertTrue(args.devserver)
        with patch("devserver.build_plan") as build_plan:
            build_plan.side_effect = DevServerUnavailable("stubbed for the test")
            cmd_fullscan(args)
        build_plan.assert_called_once()


if __name__ == "__main__":
    unittest.main()
