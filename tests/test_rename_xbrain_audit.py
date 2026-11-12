"""XAnalyze became XBrain Audit in 0.74.0. What still works under the old names.

Each compatibility point the rename promises has a test here, because each
one fails silently: a command that is not linked, a variable nobody reads, a
data folder left behind - none of them raises, the app just behaves like a
fresh install. Everything runs against temporary directories and a fake
keyring; nothing here touches the real home, PATH or keychain.
"""
from __future__ import annotations

import base64
import json
import os
import plistlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app_identity  # noqa: E402

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32",
                                 reason="the command is a symlink on macOS/Linux only")


# ------------------------------------------------------------- 1. command

class TestTheOldCommandStillWorks:

    @pytest.mark.parametrize("name, as_cli", [
        ("xaudit", True), ("xanalyze", True),
        ("XBrain Audit", False), ("XAnalyze", False),
    ])
    def test_invocation_names(self, name, as_cli):
        import app_entry

        with mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(sys, "argv", [f"/Users/me/.local/bin/{name}"]):
            assert app_entry._invoked_as_cli() is as_cli

    @pytest.mark.parametrize("executable, as_cli", [
        (r"C:\XBrain Audit\xaudit.exe", True),
        (r"C:\XAnalyze\xanalyze-cli.exe", True),
        (r"C:\XBrain Audit\XBrain Audit.exe", False),
        (r"C:\XAnalyze\XAnalyze.exe", False),
    ])
    def test_windows_executable_names(self, executable, as_cli):
        import app_entry

        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys, "executable", executable), \
                mock.patch.object(sys, "argv", ["xaudit"]):
            assert app_entry._invoked_as_cli() is as_cli

    @_POSIX_ONLY
    def test_install_links_both_names_to_the_same_program(self, tmp_path):
        import cli_install

        source = tmp_path / "XBrain Audit"
        source.write_text("#!/bin/sh\n", encoding="utf-8")
        link_dir = tmp_path / "bin"
        with mock.patch.object(cli_install, "_clear_quarantine"):
            link = cli_install.install(source=source, link_dir=link_dir)
        assert link == link_dir / "xaudit"
        for name in ("xaudit", "xanalyze"):
            assert (link_dir / name).is_symlink()
            assert Path(os.readlink(link_dir / name)) == source.absolute()

    @_POSIX_ONLY
    def test_uninstall_removes_both_names(self, tmp_path):
        import cli_install

        link_dir = tmp_path / "bin"
        link_dir.mkdir()
        for name in ("xaudit", "xanalyze"):
            (link_dir / name).symlink_to(tmp_path / "anything")
        assert cli_install.uninstall(link_dir=link_dir) is True
        assert not any(link_dir.iterdir())
        assert cli_install.uninstall(link_dir=link_dir) is False

    @_POSIX_ONLY
    def test_an_install_from_before_the_rename_counts_as_installed(self, tmp_path):
        """Only `xanalyze` is linked: the offer to install must not reappear."""
        import cli_install

        link_dir = tmp_path / "bin"
        link_dir.mkdir()
        (link_dir / "xanalyze").symlink_to(tmp_path / "XAnalyze")
        assert cli_install.installed_target(link_dir) == tmp_path / "XAnalyze"

    @_POSIX_ONLY
    def test_the_uninstaller_lists_and_removes_both_links(self, tmp_path):
        import uninstaller

        bin_dir = tmp_path / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        for name in ("xaudit", "xanalyze"):
            (bin_dir / name).symlink_to(tmp_path / "app")
        with mock.patch.object(uninstaller.Path, "home",
                               classmethod(lambda cls: tmp_path)), \
                mock.patch.object(uninstaller, "_config_base",
                                  return_value=tmp_path / "config"), \
                mock.patch.object(uninstaller, "_keychain_has", return_value=False):
            items = uninstaller.enumerate_items()
        ours = [i for i in items if i.kind == "symlink" and i.exists]
        assert sorted(i.path.name for i in ours) == ["xanalyze", "xaudit"]
        removed, errors = uninstaller.remove_all(ours)
        assert not errors and len(removed) == 2
        assert not any(bin_dir.iterdir())

    def test_the_uninstaller_knows_the_old_bundle_and_config(self, tmp_path):
        import uninstaller

        with mock.patch.object(uninstaller, "_config_base",
                               return_value=tmp_path / "config"), \
                mock.patch.object(uninstaller, "_keychain_has", return_value=False):
            items = uninstaller.enumerate_items()
        paths = {str(i.path) for i in items if i.path is not None}
        assert "/Applications/XBrain Audit.app" in paths
        assert "/Applications/XAnalyze.app" in paths
        assert str(tmp_path / "config" / "xbrain-audit") in paths
        assert str(tmp_path / "config" / "xanalyze") in paths


# ------------------------------------------------------- 2. environment

class TestOldVariablesAreAFallback:

    def test_the_new_name_wins(self, monkeypatch):
        monkeypatch.setenv("XAUDIT_SOMETHING", "new")
        monkeypatch.setenv("XANALYZE_SOMETHING", "old")
        assert app_identity.env("SOMETHING") == "new"

    def test_the_old_name_is_read_when_the_new_one_is_absent(self, monkeypatch):
        monkeypatch.delenv("XAUDIT_SOMETHING", raising=False)
        monkeypatch.setenv("XANALYZE_SOMETHING", "old")
        assert app_identity.env("SOMETHING") == "old"

    def test_an_empty_new_value_is_a_value(self, monkeypatch):
        """`XAUDIT_DESKTOP_CSS=` means "no overlay", not "ask the old one"."""
        monkeypatch.setenv("XAUDIT_SOMETHING", "")
        monkeypatch.setenv("XANALYZE_SOMETHING", "old")
        assert app_identity.env("SOMETHING") == ""

    def test_neither_gives_the_default(self, monkeypatch):
        monkeypatch.delenv("XAUDIT_SOMETHING", raising=False)
        monkeypatch.delenv("XANALYZE_SOMETHING", raising=False)
        assert app_identity.env("SOMETHING", "d") == "d"

    def test_a_real_reader_honours_the_old_report_root(self, monkeypatch, tmp_path):
        from cli_impl import runfolder

        monkeypatch.delenv("XAUDIT_REPORT_ROOT", raising=False)
        monkeypatch.setenv("XANALYZE_REPORT_ROOT", str(tmp_path / "old-root"))
        assert runfolder.default_root() == tmp_path / "old-root"

    def test_a_real_reader_honours_the_old_cache_variable(self, monkeypatch, tmp_path):
        import judgment_cache

        monkeypatch.delenv("XAUDIT_JUDGMENT_CACHE", raising=False)
        monkeypatch.setenv("XANALYZE_JUDGMENT_CACHE", str(tmp_path / "j"))
        assert judgment_cache.cache_dir() == tmp_path / "j"

    def test_no_reader_is_left_on_os_environ_with_an_old_name(self):
        """One helper, not a fallback copied to each site: a module that reads
        `XANALYZE_` itself is a site the next rename forgets."""
        offenders = []
        for path in ROOT.rglob("*.py"):
            rel = path.relative_to(ROOT)
            if rel.parts[0] in {"venv", "build", "dist", "tests", ".claude", ".git"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "XANALYZE_" in text and rel.as_posix() != "app_identity.py":
                for line in text.splitlines():
                    if "XANALYZE_" in line and ("environ" in line or "getenv" in line):
                        offenders.append(f"{rel}: {line.strip()}")
        assert offenders == []


# --------------------------------------------------------- 3. migration

def _legacy_tree(home: Path, config: Path, state: Path) -> None:
    (home / ".xanalyze" / "history").mkdir(parents=True)
    (home / ".xanalyze" / "history" / "abc.json").write_text("[1]", encoding="utf-8")
    (config / "xanalyze").mkdir(parents=True)
    (config / "xanalyze" / "settings.json").write_text('{"ui_language": "it"}',
                                                       encoding="utf-8")
    (state / "xanalyze" / "logs").mkdir(parents=True)
    (home / "Documents" / "XAnalyze" / "example.com").mkdir(parents=True)


class TestDataMovesOnce:

    def _paths(self, tmp_path):
        home, config, state = tmp_path / "home", tmp_path / "config", tmp_path / "state"
        _legacy_tree(home, config, state)
        return home, config, state

    def test_every_old_folder_is_renamed(self, tmp_path):
        home, config, state = self._paths(tmp_path)
        moves = app_identity.migrate_legacy_data(home, (config,), state)
        assert {m.outcome for m in moves} == {"moved"}
        assert (home / ".xbrain-audit" / "history" / "abc.json").read_text() == "[1]"
        assert json.loads((config / "xbrain-audit" / "settings.json").read_text()) == {
            "ui_language": "it"}
        assert (state / "xbrain-audit" / "logs").is_dir()
        assert (home / "Documents" / "XBrain Audit" / "example.com").is_dir()
        for old in (home / ".xanalyze", config / "xanalyze", state / "xanalyze",
                    home / "Documents" / "XAnalyze"):
            assert not old.exists()

    def test_a_second_start_changes_nothing(self, tmp_path):
        home, config, state = self._paths(tmp_path)
        app_identity.migrate_legacy_data(home, (config,), state)
        again = app_identity.migrate_legacy_data(home, (config,), state)
        assert {m.outcome for m in again} == {"skipped"}

    def test_an_existing_new_folder_is_never_merged_into(self, tmp_path):
        home, config, state = self._paths(tmp_path)
        (home / ".xbrain-audit").mkdir()
        (home / ".xbrain-audit" / "mine.txt").write_text("x", encoding="utf-8")
        moves = app_identity.migrate_legacy_data(home, (config,), state)
        data = next(m for m in moves if m.new == home / ".xbrain-audit")
        assert data.outcome == "skipped"
        assert (home / ".xanalyze" / "history" / "abc.json").exists()
        assert [p.name for p in (home / ".xbrain-audit").iterdir()] == ["mine.txt"]

    def test_a_failed_move_keeps_the_old_folder_in_use(self, tmp_path):
        home, config, state = self._paths(tmp_path)
        with mock.patch.object(app_identity.os, "rename",
                               side_effect=OSError("busy")), \
                mock.patch("applog.warning") as warned:
            moves = app_identity.migrate_legacy_data(home, (config,), state)
        assert {m.outcome for m in moves} == {"failed"}
        assert all(m.reason == "busy" for m in moves)
        assert warned.call_count == len(moves)
        assert app_identity.data_home(home) == home / ".xanalyze"
        assert app_identity.app_dir(config) == config / "xanalyze"
        assert app_identity.reports_root(home) == home / "Documents" / "XAnalyze"

    def test_before_the_move_the_old_folders_are_the_ones_in_use(self, tmp_path):
        home, config, state = self._paths(tmp_path)
        assert app_identity.data_home(home) == home / ".xanalyze"
        app_identity.migrate_legacy_data(home, (config,), state)
        assert app_identity.data_home(home) == home / ".xbrain-audit"

    def test_a_fresh_machine_gets_only_new_names(self, tmp_path):
        assert app_identity.data_home(tmp_path) == tmp_path / ".xbrain-audit"
        assert app_identity.app_dir(tmp_path) == tmp_path / "xbrain-audit"

    def test_the_test_switch_stops_only_the_implicit_call(self, tmp_path, monkeypatch):
        monkeypatch.setenv(app_identity.SKIP_MIGRATION_ENV, "1")
        with mock.patch.object(app_identity.os, "rename") as renamed:
            assert app_identity.migrate_legacy_data() == []
        renamed.assert_not_called()
        home, config, state = self._paths(tmp_path)
        assert app_identity.migrate_legacy_data(home, (config,), state)

    def test_config_reads_the_old_folder_until_it_moves(self, tmp_path, monkeypatch):
        import config

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        (tmp_path / "xanalyze").mkdir()
        (tmp_path / "xanalyze" / "settings.json").write_text('{"ui_language": "en"}',
                                                             encoding="utf-8")
        assert config.config_file() == tmp_path / "xanalyze" / "settings.json"
        assert not (tmp_path / "xbrain-audit").exists()

    def test_cli_calls_the_migration_first(self):
        import cli

        with mock.patch.object(app_identity, "migrate_legacy_data") as migrate, \
                pytest.raises(SystemExit):
            cli.main(["--version"])
        migrate.assert_called_once_with()

    def test_the_tui_calls_the_migration(self):
        from tui import app as tui_app

        with mock.patch.object(app_identity, "migrate_legacy_data") as migrate, \
                mock.patch.object(tui_app, "XBrainAuditApp"):
            tui_app.run_tui()
        migrate.assert_called_once_with()

    def test_the_frozen_entry_calls_the_migration(self):
        import app_entry

        with mock.patch.object(app_identity, "migrate_legacy_data") as migrate, \
                mock.patch.object(app_entry, "_warn_if_stale"), \
                mock.patch.object(app_entry, "_invoked_as_cli", return_value=True), \
                mock.patch.object(sys, "argv", ["xanalyze", "scan"]), \
                mock.patch("cli.main", return_value=0) as cli_main:
            assert app_entry.run() == 0
        migrate.assert_called_once_with()
        cli_main.assert_called_once_with(["scan"])

    def test_the_window_calls_the_migration(self):
        pytest.importorskip("PySide6.QtWidgets")
        import main

        with mock.patch.object(app_identity, "migrate_legacy_data") as migrate, \
                mock.patch.object(sys, "argv", ["XBrain Audit", "--version"]):
            assert main.main() == 0
        migrate.assert_called_once_with()


# --------------------------------------------------------- 4. per project

class TestProjectFilesAreNotChurned:

    def test_only_the_old_ignore_file_is_read_and_written(self, tmp_path):
        import suppression

        old = tmp_path / ".xanalyze-ignore"
        old.write_text("[phrases]\nhouse style\n", encoding="utf-8")
        loaded = suppression.Suppressions.load(root=str(tmp_path))
        assert "house style" in loaded.phrases
        written = suppression.add_fingerprint_to_ignore_file(str(tmp_path), "abc123")
        assert written == old
        assert "abc123" in old.read_text(encoding="utf-8")
        assert not (tmp_path / ".xaudit-ignore").exists()

    def test_a_project_without_one_gets_the_new_name(self, tmp_path):
        import suppression

        written = suppression.add_fingerprint_to_ignore_file(str(tmp_path), "abc123")
        assert written == tmp_path / ".xaudit-ignore"
        assert not (tmp_path / ".xanalyze-ignore").exists()

    def test_the_new_file_wins_when_both_exist(self, tmp_path):
        import suppression

        (tmp_path / ".xanalyze-ignore").write_text("[phrases]\nold\n", encoding="utf-8")
        (tmp_path / ".xaudit-ignore").write_text("[phrases]\nnew\n", encoding="utf-8")
        loaded = suppression.Suppressions.load(root=str(tmp_path))
        assert "new" in loaded.phrases and "old" not in loaded.phrases
        assert suppression.ignore_file(tmp_path) == tmp_path / ".xaudit-ignore"

    def test_the_history_folder_follows_the_same_rule(self, tmp_path):
        assert app_identity.project_history_dir(tmp_path) == tmp_path / ".xaudit"
        (tmp_path / ".xanalyze").mkdir()
        assert app_identity.project_history_dir(tmp_path) == tmp_path / ".xanalyze"
        (tmp_path / ".xaudit").mkdir()
        assert app_identity.project_history_dir(tmp_path) == tmp_path / ".xaudit"

    def test_old_per_folder_history_is_still_counted(self, tmp_path, monkeypatch):
        from cli_impl import reports

        (tmp_path / ".xanalyze").mkdir()
        entry = {"at": "2026-01-01T00:00:00", "root": "/site", "mode": "audit"}
        (tmp_path / ".xanalyze" / "old.json").write_text(json.dumps([entry]),
                                                         encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert reports._legacy_history("/site", "audit") == [entry]


# ----------------------------------------------------------- 5. keyring

class _FakeKeyring:
    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, account):
        return self.store.get((service, account))

    def set_password(self, service, account, value):
        self.store[(service, account)] = value

    def delete_password(self, service, account):
        if (service, account) not in self.store:
            raise KeyError(account)
        del self.store[(service, account)]


class TestKeychainItemsCarryOver:

    def test_an_xanalyze_item_is_found_and_copied(self):
        from llm import credentials

        fake = _FakeKeyring()
        fake.set_password("xanalyze", "xformat_refresh_token", "token")
        with mock.patch.object(credentials, "_keyring", return_value=fake):
            assert credentials.load_secret("xformat_refresh_token") == "token"
        assert fake.get_password("xbrain-audit", "xformat_refresh_token") == "token"
        # Copied, not moved: an older release beside this one still reads it.
        assert fake.get_password("xanalyze", "xformat_refresh_token") == "token"

    def test_the_new_service_is_read_first(self):
        from llm import credentials

        fake = _FakeKeyring()
        fake.set_password("xanalyze", "anthropic_api_key", "old")
        fake.set_password("xbrain-audit", "anthropic_api_key", "new")
        with mock.patch.object(credentials, "_keyring", return_value=fake):
            assert credentials.load_secret("anthropic_api_key") == "new"

    def test_signing_out_does_not_come_back_from_the_old_service(self):
        from llm import credentials

        fake = _FakeKeyring()
        fake.set_password("xanalyze", "xformat_access_token", "token")
        with mock.patch.object(credentials, "_keyring", return_value=fake), \
                mock.patch.object(credentials, "_locked_file",
                                  side_effect=OSError("no file store")):
            assert credentials.load_secret("xformat_access_token") == "token"
            credentials.delete_secret("xformat_access_token")
            assert credentials.load_secret("xformat_access_token") is None


# ------------------------------------------------------------ 6. updater

def _release(*names):
    import updater

    assets = [{"name": name, "size": 10,
               "browser_download_url": f"https://github.com/o/r/releases/download/v1/{name}"}
              for name in names]
    return updater.ReleaseInfo("v9.9.9", "9.9.9", "", assets, "https://github.com/o/r")


def _bundle(path: Path, executable: str = "XBrain Audit", content: str = "app") -> Path:
    binary = path / "Contents" / "MacOS" / executable
    binary.parent.mkdir(parents=True)
    binary.write_text(content, encoding="utf-8")
    (path / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundlePackageType": "APPL", "CFBundleExecutable": executable}))
    return path


def _zip_bundle(archive: Path, top: str, content: str = "new") -> None:
    """A zip shaped like `ditto -c -k --keepParent`, links included."""
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(f"{top}/Contents/Info.plist", plistlib.dumps({
            "CFBundlePackageType": "APPL", "CFBundleExecutable": "XBrain Audit"}))
        info = zipfile.ZipInfo(f"{top}/Contents/MacOS/XBrain Audit")
        info.external_attr = (0o100755 << 16)
        zf.writestr(info, content)
        link = zipfile.ZipInfo(f"{top}/Contents/MacOS/XAnalyze")
        link.external_attr = (0o120777 << 16)
        zf.writestr(link, "XBrain Audit")


class TestTheUpdaterTransition:

    def test_new_assets_are_preferred(self):
        import updater

        release = _release("XAnalyze.app.zip", "XBrainAudit.app.zip")
        assert updater.find_gui_asset(release)["name"] == "XBrainAudit.app.zip"

    def test_an_older_release_is_still_readable(self):
        import updater

        release = _release("XAnalyze.app.zip")
        assert updater.find_gui_asset(release)["name"] == "XAnalyze.app.zip"

    @pytest.mark.parametrize("names, expected", [
        (("xbrain-audit-update-manifest.json", "xbrain-audit-update-manifest.json.sig",
          "xanalyze-update-manifest.json", "xanalyze-update-manifest.json.sig"),
         "xbrain-audit-update-manifest.json"),
        (("xanalyze-update-manifest.json", "xanalyze-update-manifest.json.sig"),
         "xanalyze-update-manifest.json"),
    ])
    def test_manifest_new_name_first_old_as_fallback(self, names, expected):
        import updater

        release = _release(*names)
        payload = json.dumps({"version": 1, "release": "v9.9.9", "assets": {
            "XBrainAudit.app.zip": {"size": 10, "sha256": "0" * 64}}}).encode()
        read = []

        def fake_read(asset, *, limit):
            read.append(asset["name"])
            return b"" if asset["name"].endswith(".sig") else payload

        with mock.patch.object(updater, "_read_remote_asset", side_effect=fake_read), \
                mock.patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEYS", ()):
            manifest = updater.fetch_update_manifest(release)
        assert read == [expected, expected + ".sig"]
        assert "XBrainAudit.app.zip" in manifest.assets

    @pytest.mark.parametrize("top", ["XBrain Audit.app", "XAnalyze.app"])
    @_POSIX_ONLY
    def test_either_archive_unpacks_with_its_link(self, tmp_path, top):
        import updater

        archive = tmp_path / "a.zip"
        _zip_bundle(archive, top)
        app = updater._extract_gui_app(archive, tmp_path / "out")
        assert app.name == top
        link = app / "Contents" / "MacOS" / "XAnalyze"
        assert link.is_symlink() and os.readlink(link) == "XBrain Audit"

    def test_an_app_at_the_old_path_moves_to_the_new_name(self, tmp_path, monkeypatch, capsys):
        import updater

        apps = tmp_path / "Applications"
        old_app = _bundle(apps / "XAnalyze.app", "XAnalyze", "old")
        extracted = _bundle(tmp_path / "unpacked" / "XAnalyze.app", content="new")
        release = _release("XBrainAudit.app.zip")
        pointed = []
        monkeypatch.setattr(updater, "fetch_latest", lambda: release)
        monkeypatch.setattr(updater, "fetch_update_manifest",
                            lambda _: updater.UpdateManifest("v9.9.9", {}, True))
        monkeypatch.setattr(updater, "_installed_app", lambda: old_app)
        monkeypatch.setattr(updater, "_legacy_cli", lambda: None)
        monkeypatch.setattr(updater, "_asset_integrity", lambda *a: None)
        monkeypatch.setattr(updater, "_download", lambda *a: None)
        monkeypatch.setattr(updater, "_extract_gui_app", lambda *a, **k: extracted)
        monkeypatch.setattr(updater, "_point_command_at",
                            lambda app, legacy: pointed.append(app))
        assert updater.do_update() == 0
        new_app = apps / "XBrain Audit.app"
        assert (new_app / "Contents" / "MacOS" / "XBrain Audit").read_text() == "new"
        assert not old_app.exists()
        assert pointed == [new_app]

    def test_a_failed_install_keeps_the_old_app(self, tmp_path, monkeypatch):
        import updater

        old_app = _bundle(tmp_path / "XAnalyze.app", "XAnalyze", "old")
        monkeypatch.setattr(updater, "fetch_latest", lambda: _release("XBrainAudit.app.zip"))
        monkeypatch.setattr(updater, "fetch_update_manifest",
                            lambda _: updater.UpdateManifest("v9.9.9", {}, True))
        monkeypatch.setattr(updater, "_installed_app", lambda: old_app)
        monkeypatch.setattr(updater, "_legacy_cli", lambda: None)
        monkeypatch.setattr(updater, "_asset_integrity", lambda *a: None)
        monkeypatch.setattr(updater, "_download", lambda *a: None)
        monkeypatch.setattr(updater, "_extract_gui_app",
                            mock.Mock(side_effect=RuntimeError("bad archive")))
        assert updater.do_update() == 2
        assert (old_app / "Contents" / "MacOS" / "XAnalyze").read_text() == "old"
        assert not (tmp_path / "XBrain Audit.app").exists()

    @_POSIX_ONLY
    def test_both_commands_are_repointed_at_the_renamed_app(self, tmp_path, monkeypatch):
        import cli_install
        import updater

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        old_exe = tmp_path / "XAnalyze.app" / "Contents" / "MacOS" / "XAnalyze"
        (bin_dir / "xanalyze").symlink_to(old_exe)
        new_app = _bundle(tmp_path / "XBrain Audit.app")
        monkeypatch.setattr(cli_install, "USER_BIN_DIR", bin_dir)
        monkeypatch.setattr(cli_install, "_clear_quarantine", lambda path: None)
        updater._point_command_at(new_app, None)
        executable = new_app / "Contents" / "MacOS" / "XBrain Audit"
        for name in ("xaudit", "xanalyze"):
            assert Path(os.readlink(bin_dir / name)) == executable.absolute()

    def test_old_locations_are_still_searched(self):
        import updater

        names = [path.name for path in updater._APP_LOCATIONS]
        assert names[:2] == ["XBrain Audit.app"] * 2
        assert names[2:] == ["XAnalyze.app"] * 2


# ------------------------------------------------------------ 7. release

class TestTheReleaseCarriesTheOldAssets:

    def test_one_manifest_under_both_names_with_one_signature(self, tmp_path):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        import updater
        sys.path.insert(0, str(ROOT / "scripts"))
        import update_manifest

        key = Ed25519PrivateKey.generate()
        private = base64.b64encode(key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption())).decode()
        public = base64.b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        assets = []
        for name in ("XBrainAudit.app.zip", "XAnalyze.app.zip"):
            (tmp_path / name).write_bytes(b"zip")
            assets.append(tmp_path / name)
        new = tmp_path / "xbrain-audit-update-manifest.json"
        old = tmp_path / "xanalyze-update-manifest.json"
        update_manifest.write_manifest("v9.9.9", assets, new, private, also=(old,))
        assert new.read_bytes() == old.read_bytes()
        signature = (tmp_path / "xanalyze-update-manifest.json.sig").read_bytes()
        assert signature == (tmp_path / "xbrain-audit-update-manifest.json.sig").read_bytes()
        with mock.patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEYS", (public,)):
            assert updater._verify_manifest_signature(old.read_bytes(), signature)
        assert set(json.loads(old.read_bytes())["assets"]) == {
            "XBrainAudit.app.zip", "XAnalyze.app.zip"}

    @pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("ditto"),
                        reason="the release is packed with macOS ditto")
    def test_package_script_writes_both_archives(self, tmp_path):
        import updater

        dist = tmp_path / "dist"
        app = _bundle(dist / "XBrain Audit.app", content="built")
        (app / "Contents" / "MacOS" / "XAnalyze").symlink_to("XBrain Audit")
        env = {**os.environ, "DIST_DIR": str(dist), "PYTHON": sys.executable}
        env.pop("UPDATE_SIGNING_KEY", None)
        subprocess.run([str(ROOT / "scripts" / "package_release.sh"), "9.9.9"],
                       check=True, env=env, capture_output=True)
        for archive, top in (("XBrainAudit.app.zip", "XBrain Audit.app"),
                             ("XAnalyze.app.zip", "XAnalyze.app")):
            with zipfile.ZipFile(dist / archive) as zf:
                # `__MACOSX/` holds extended attributes (`--sequesterRsrc`).
                tops = {n.split("/")[0] for n in zf.namelist()} - {"__MACOSX"}
                assert tops == {top}
            unpacked = updater._extract_gui_app(dist / archive, tmp_path / archive)
            link = unpacked / "Contents" / "MacOS" / "XAnalyze"
            assert link.is_symlink()
            assert (link.parent / "XBrain Audit").read_text() == "built"
        manifest = json.loads((dist / "xanalyze-update-manifest.json").read_text())
        assert manifest["release"] == "v9.9.9"
        assert set(manifest["assets"]) == {"XBrainAudit.app.zip", "XAnalyze.app.zip"}
        assert (dist / "xbrain-audit-update-manifest.json").read_bytes() == \
            (dist / "xanalyze-update-manifest.json").read_bytes()
        assert not list(dist.glob(".legacy-asset.*"))

    def test_the_bundle_keeps_the_old_executable_name_as_a_link(self):
        """An installed XAnalyze's `xanalyze` link points at
        `XAnalyze.app/Contents/MacOS/XAnalyze`, and its own updater leaves
        that link alone. Without the link inside the bundle it would dangle."""
        spec = (ROOT / "packaging" / "XBrainAudit.spec").read_text(encoding="utf-8")
        assert 'legacy_exe = macos_dir / "XAnalyze"' in spec
        assert "os.symlink(gui_exe.name, legacy_exe)" in spec

    def test_the_workflow_publishes_the_old_assets(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        assert "scripts/package_release.sh" in workflow
        for name in ("dist/XAnalyze.app.zip", "dist/xanalyze-update-manifest.json",
                     "dist/xanalyze-update-manifest.json.sig"):
            assert name in workflow


# ----------------------------------------------------------- 8. identity

def test_the_xformat_client_slug_is_the_renamed_one():
    """The backend's current id; `xanalyze` is only its alias there."""
    from llm import xformat_provider

    assert xformat_provider.CLIENT_APP_SLUG == "xbrain-audit"
