"""`cli_install`'s symlink/quarantine logic, entirely on a scratch directory.

Every test passes an explicit `link_dir` under a `tempfile.TemporaryDirectory`
and a `source` under the same scratch tree — never `cli_install.USER_BIN_DIR`
or `cli_install.SYSTEM_BIN_DIR` — so nothing here can touch this machine's
real `~/.local/bin` or `/usr/local/bin`. The admin-elevated path is exercised
only against a mocked `subprocess.run`, since it would otherwise pop a real
macOS password dialog.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli_install

#: Linking the command is a symlink into `~/.local/bin`: macOS and Linux.
#: The Windows build ships the command as its own executable instead, and
#: `install` refuses there (see `OnWindows` below).
_POSIX_ONLY = unittest.skipIf(sys.platform == "win32",
                              "the command is a symlink on macOS/Linux only")


class _ScratchCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.link_dir = self.base / "bin"
        self.source = self.base / "xanalyze-cli"
        self.source.write_text("#!/bin/sh\necho fake cli\n", encoding="utf-8")
        os.chmod(self.source, 0o755)

    def tearDown(self):
        self._tmp.cleanup()


class BundledCliPath(unittest.TestCase):
    def test_none_when_not_frozen(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertIsNone(cli_install.bundled_cli_path())

    def test_the_running_executables_own_path_when_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_executable = Path(tmp).resolve() / "XAnalyze"
            fake_executable.write_text("stub", encoding="utf-8")
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "executable", str(fake_executable)):
                self.assertEqual(cli_install.bundled_cli_path(), fake_executable)


class IsDirOnPath(unittest.TestCase):
    def test_a_directory_present_in_path_is_reported_as_such(self):
        with mock.patch.dict(os.environ, {"PATH": f"/usr/bin{os.pathsep}/opt/here"}):
            self.assertTrue(cli_install.is_dir_on_path(Path("/opt/here")))

    def test_a_directory_absent_from_path_is_reported_as_such(self):
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin"}):
            self.assertFalse(cli_install.is_dir_on_path(Path("/opt/nowhere")))


@_POSIX_ONLY
class InstallAndUninstall(_ScratchCase):
    def test_install_creates_a_symlink_to_the_source(self):
        target = cli_install.install(source=self.source, link_dir=self.link_dir)
        self.assertEqual(target, self.link_dir / cli_install.CLI_NAME)
        self.assertTrue(target.is_symlink())
        self.assertEqual(Path(os.readlink(target)), self.source)

    def test_install_clears_the_quarantine_flag(self):
        # A fresh temp file has no quarantine attribute; the point of this
        # test is that clearing a *missing* attribute is not treated as a
        # failure -- install must still succeed.
        target = cli_install.install(source=self.source, link_dir=self.link_dir)
        self.assertTrue(target.exists())

    def test_install_replaces_a_pre_existing_symlink(self):
        other_source = self.base / "other-cli"
        other_source.write_text("stub", encoding="utf-8")
        cli_install.install(source=other_source, link_dir=self.link_dir)
        target = cli_install.install(source=self.source, link_dir=self.link_dir)
        self.assertEqual(Path(os.readlink(target)), self.source)

    def test_install_raises_when_the_source_is_missing(self):
        missing = self.base / "nope"
        with self.assertRaises(cli_install.CliInstallError):
            cli_install.install(source=missing, link_dir=self.link_dir)

    def test_install_with_no_source_and_not_frozen_raises(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            with self.assertRaises(cli_install.CliInstallError):
                cli_install.install(link_dir=self.link_dir)

    def test_uninstall_removes_the_symlink_and_reports_it_removed(self):
        cli_install.install(source=self.source, link_dir=self.link_dir)
        removed = cli_install.uninstall(link_dir=self.link_dir)
        self.assertTrue(removed)
        self.assertFalse((self.link_dir / cli_install.CLI_NAME).exists())

    def test_uninstall_when_nothing_installed_reports_nothing_removed(self):
        self.assertFalse(cli_install.uninstall(link_dir=self.link_dir))

    def test_installed_target_reflects_current_symlink(self):
        self.assertIsNone(cli_install.installed_target(link_dir=self.link_dir))
        cli_install.install(source=self.source, link_dir=self.link_dir)
        self.assertEqual(cli_install.installed_target(link_dir=self.link_dir), self.source)


@_POSIX_ONLY
class AdminElevatedPath(_ScratchCase):
    """The `/usr/local/bin` path, with `subprocess.run` mocked so no real
    macOS password dialog appears during the test suite."""

    def test_install_with_admin_shells_out_instead_of_symlinking_directly(self):
        with mock.patch("cli_install.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stderr="")
            target = cli_install.install(source=self.source, link_dir=self.link_dir,
                                         use_admin=True)
        self.assertEqual(target, self.link_dir / cli_install.CLI_NAME)
        # Not actually created on disk -- the mocked call never really ran
        # `ln -sf`, which is exactly the point: no real elevation happened.
        self.assertFalse(target.exists())
        admin_calls = [c for c in run.call_args_list
                      if "administrator privileges" in c.args[0][-1]]
        self.assertEqual(len(admin_calls), 1)

    def test_install_with_admin_raises_when_the_prompt_is_cancelled(self):
        with mock.patch("cli_install.subprocess.run") as run:
            run.side_effect = [
                mock.Mock(returncode=1, stderr="No such xattr: com.apple.quarantine"),
                mock.Mock(returncode=1, stderr="User canceled."),
            ]
            with self.assertRaises(cli_install.CliInstallError):
                cli_install.install(source=self.source, link_dir=self.link_dir,
                                    use_admin=True)

    def test_uninstall_with_admin_shells_out(self):
        with mock.patch("cli_install.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stderr="")
            # uninstall() with use_admin checks existence first via Path, not
            # a shell call, so create the symlink locally to make it "exist".
            (self.link_dir).mkdir(parents=True)
            (self.link_dir / cli_install.CLI_NAME).symlink_to(self.source)
            removed = cli_install.uninstall(link_dir=self.link_dir, use_admin=True)
        self.assertTrue(removed)
        admin_calls = [c for c in run.call_args_list
                      if "administrator privileges" in c.args[0][-1]]
        self.assertEqual(len(admin_calls), 1)


@_POSIX_ONLY
class TheFirstRunOffer(_ScratchCase):
    """`cli_install.offer_is_due`: asked once, in the packaged app, when the
    command is not there yet. Every branch is a refusal to nag."""

    def _frozen(self):
        return mock.patch("cli_install.bundled_cli_path",
                          return_value=self.source)

    def test_a_packaged_run_without_the_command_is_asked(self):
        with self._frozen():
            self.assertTrue(cli_install.offer_is_due(False, link_dir=self.link_dir))

    def test_a_dev_run_is_never_asked(self):
        # `python main.py` has nothing to link: the CLI is `python cli.py`.
        with mock.patch("cli_install.bundled_cli_path", return_value=None):
            self.assertFalse(cli_install.offer_is_due(False, link_dir=self.link_dir))

    def test_asking_once_is_asking_once(self):
        with self._frozen():
            self.assertFalse(cli_install.offer_is_due(True, link_dir=self.link_dir))

    def test_an_already_installed_command_asks_nothing(self):
        self.link_dir.mkdir(parents=True)
        (self.link_dir / cli_install.CLI_NAME).symlink_to(self.source)
        with self._frozen():
            self.assertFalse(cli_install.offer_is_due(False, link_dir=self.link_dir))


class OnWindows(_ScratchCase):
    def test_install_explains_instead_of_trying_a_symlink(self):
        with mock.patch.object(sys, "platform", "win32"):
            with self.assertRaises(cli_install.CliInstallError) as caught:
                cli_install.install(self.source, self.link_dir)
        self.assertIn("xanalyze-cli.exe", str(caught.exception))
        self.assertFalse((self.link_dir / cli_install.CLI_NAME).exists())

    def test_the_first_run_offer_is_not_made(self):
        with mock.patch.object(sys, "platform", "win32"),                 mock.patch.object(cli_install, "bundled_cli_path", return_value=self.source):
            self.assertFalse(cli_install.offer_is_due(False, self.link_dir))


class TheOfferIsRememberedAcrossLaunches(unittest.TestCase):
    """The flag lives in `config.Settings`, so it survives a restart - which
    is the whole point of asking only once."""

    def test_the_flag_round_trips_through_settings(self):
        import config

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("config.config_file",
                            return_value=Path(tmp) / "settings.json"):
                settings = config.Settings()
                self.assertFalse(settings.cli_install_offered)
                settings.cli_install_offered = True
                settings.save()
                self.assertTrue(config.Settings.load().cli_install_offered)


if __name__ == "__main__":
    unittest.main()
