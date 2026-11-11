"""The Windows build and the per-user directories on Windows.

Both run on every platform: they read files and swap `sys.platform`, nothing
here needs Windows to be true.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

_DATA_ENTRY = re.compile(r'\(str\(ROOT((?: / "[^"]+")+)\), "([^"]+)"\)')


def _data_files(spec: str) -> set[tuple[str, str]]:
    text = (ROOT / "packaging" / spec).read_text(encoding="utf-8")
    return {(source, target) for source, target in _DATA_ENTRY.findall(text)}


class TheWindowsSpecShipsWhatTheMacOSSpecShips(unittest.TestCase):
    """The data list is copied between the two specs (see the Windows spec's
    docstring for why), so a file added to one and not the other is a build
    that runs from source and breaks frozen, on one platform only."""

    def test_same_data_files(self):
        mac = _data_files("XAnalyze.spec")
        windows = _data_files("XAnalyze-windows.spec")
        self.assertTrue(mac, "no data entries parsed from XAnalyze.spec")
        self.assertEqual(mac, windows)

    def test_windows_keychain_backend_is_named(self):
        text = (ROOT / "packaging" / "XAnalyze-windows.spec").read_text(encoding="utf-8")
        self.assertIn('"keyring.backends.Windows"', text)


class TheCliExecutableIsRecognisedOnWindows(unittest.TestCase):
    def test_console_executable_runs_the_cli(self):
        import app_entry

        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys, "executable", r"C:\XAnalyze\xanalyze-cli.exe"):
            self.assertTrue(app_entry._invoked_as_cli())

    def test_window_executable_typed_in_lower_case_is_still_the_window(self):
        import app_entry

        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys, "executable", r"C:\XAnalyze\XAnalyze.exe"), \
                mock.patch.object(sys, "argv", ["xanalyze"]):
            self.assertFalse(app_entry._invoked_as_cli())


class PerUserDirectoriesOnWindows(unittest.TestCase):
    def test_config_goes_to_appdata_and_logs_to_localappdata(self):
        import platform_dirs

        env = {"APPDATA": r"C:\Users\x\AppData\Roaming",
               "LOCALAPPDATA": r"C:\Users\x\AppData\Local"}
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict("os.environ", env, clear=True):
            self.assertEqual(platform_dirs.config_home(), Path(env["APPDATA"]))
            self.assertEqual(platform_dirs.state_home(), Path(env["LOCALAPPDATA"]))

    def test_xdg_override_still_wins_on_windows(self):
        # The whole test suite is isolated through this variable.
        import platform_dirs

        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": "elsewhere",
                                               "APPDATA": "roaming"}, clear=True):
            self.assertEqual(platform_dirs.config_home(), Path("elsewhere"))

    def test_posix_keeps_dot_config(self):
        import platform_dirs

        home = Path("/home/someone")
        with mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch.object(Path, "home", return_value=home):
            self.assertEqual(platform_dirs.config_home(), home / ".config")
            self.assertEqual(platform_dirs.state_home(), home / ".local" / "state")


class TheCliWritesUtf8WhenPiped(unittest.TestCase):
    def test_help_survives_a_pipe(self):
        import os
        import subprocess

        env = dict(os.environ)
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        result = subprocess.run(
            [sys.executable, str(ROOT / "cli.py"), "--help"],
            capture_output=True, env=env, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn("→", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
