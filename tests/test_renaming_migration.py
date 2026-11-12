"""Migration paths for the ai-content-scanner -> XAnalyze rename.

(XAnalyze is XBrain Audit since 0.74.0; that rename has its own tests in
`tests/test_rename_xbrain_audit.py`.)

A plain string rename of `config.APP_NAME` or `llm.credentials.SERVICE_NAME`
would be invisible to anyone who already used the app: settings live in a
config dir named after the old app, and account tokens (xFormat
access/refresh, an Anthropic key) live in the OS keychain under the old
service name. Change the name with no migration and the app looks like a
fresh install — it isn't that the data is gone, just that nothing points at
it any more.

Everything here runs against a temporary `XDG_CONFIG_HOME` and a stubbed
keyring backend, never the real `~/.config` or the real OS keychain.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from llm import credentials


class _EnvIsolatedCase(unittest.TestCase):
    """Points XDG_CONFIG_HOME at a scratch dir for the duration of a test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self._old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(self.base)

    def tearDown(self):
        if self._old_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old_xdg
        self._tmp.cleanup()


class ConfigDirMigration(_EnvIsolatedCase):
    """`config._config_dir()` copying settings.json from the old dir name."""

    def _old_dir(self) -> Path:
        return self.base / config.OLD_APP_NAME

    def _new_dir(self) -> Path:
        return self.base / config.APP_NAME

    def test_settings_are_copied_from_the_old_config_dir(self):
        old = self._old_dir()
        old.mkdir(parents=True)
        # A non-default value so a straight comparison actually proves the
        # file was copied, not just that a fresh default settings.json
        # happened to be written.
        payload = {"ui_language": "it", "ignore": {"suppressed": ["abc123"]}}
        (old / "settings.json").write_text(json.dumps(payload), encoding="utf-8")

        result_dir = config._config_dir()

        self.assertEqual(result_dir, self._new_dir())
        new_file = result_dir / "settings.json"
        self.assertTrue(new_file.exists())
        self.assertEqual(json.loads(new_file.read_text(encoding="utf-8")), payload)
        # The old file is left in place -- copied, not moved -- since an
        # older version of the app might still be pointed at it.
        self.assertTrue((old / "settings.json").exists())

    def test_migration_does_not_repeat_once_the_new_file_exists(self):
        old = self._old_dir()
        old.mkdir(parents=True)
        (old / "settings.json").write_text(json.dumps({"ui_language": "it"}), encoding="utf-8")

        config._config_dir()  # first call migrates

        new_file = self._new_dir() / "settings.json"
        # Simulate the user having changed a setting since upgrading.
        new_file.write_text(json.dumps({"ui_language": "en"}), encoding="utf-8")

        config._config_dir()  # second call must leave the newer file alone

        self.assertEqual(json.loads(new_file.read_text(encoding="utf-8"))["ui_language"], "en")

    def test_no_migration_when_there_is_no_old_config(self):
        result_dir = config._config_dir()
        self.assertFalse((result_dir / "settings.json").exists())


class _FakeKeyringBackend:
    """Minimal in-memory stand-in for the `keyring` module's public calls,
    keyed the same way the real backends are: (service, account)."""

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service, account):
        return self._store.get((service, account))

    def set_password(self, service, account, value):
        self._store[(service, account)] = value

    def delete_password(self, service, account):
        key = (service, account)
        if key not in self._store:
            raise KeyError(f"no such secret: {service}/{account}")
        del self._store[key]


class KeychainMigration(_EnvIsolatedCase):
    """`load_secret` falling back to, and migrating from, OLD_SERVICE_NAME."""

    def test_a_plain_rename_with_no_migration_would_strand_the_secret(self):
        """Documents the risk this migration exists to avoid: looked up
        under the *new* service name the way a bare `SERVICE_NAME` edit
        would, a token saved under the old name is simply not there."""
        fake = _FakeKeyringBackend()
        fake.set_password(credentials.OLD_SERVICE_NAME, "anthropic_api_key", "pre-rename-secret")
        self.assertIsNone(fake.get_password(credentials.SERVICE_NAME, "anthropic_api_key"))

    def test_load_secret_finds_and_migrates_the_old_entry(self):
        fake = _FakeKeyringBackend()
        fake.set_password(credentials.OLD_SERVICE_NAME, "xformat_refresh_token", "legacy-token-value")

        with mock.patch.object(credentials, "_keyring", return_value=fake):
            value = credentials.load_secret("xformat_refresh_token")

        self.assertEqual(value, "legacy-token-value")
        # Reachable under the new service name now...
        self.assertEqual(
            fake.get_password(credentials.SERVICE_NAME, "xformat_refresh_token"),
            "legacy-token-value",
        )
        # ...and the stale copy under the old name is gone, so it doesn't
        # sit around as unreferenced clutter in the keychain.
        self.assertIsNone(fake.get_password(credentials.OLD_SERVICE_NAME, "xformat_refresh_token"))

    def test_repeated_lookups_after_migration_use_the_new_name_directly(self):
        fake = _FakeKeyringBackend()
        fake.set_password(credentials.OLD_SERVICE_NAME, "anthropic_api_key", "legacy-key")

        with mock.patch.object(credentials, "_keyring", return_value=fake):
            first = credentials.load_secret("anthropic_api_key")
            second = credentials.load_secret("anthropic_api_key")

        self.assertEqual(first, "legacy-key")
        self.assertEqual(second, "legacy-key")

    def test_a_value_already_under_the_new_name_is_used_as_is(self):
        fake = _FakeKeyringBackend()
        fake.set_password(credentials.SERVICE_NAME, "anthropic_api_key", "already-migrated")

        with mock.patch.object(credentials, "_keyring", return_value=fake):
            value = credentials.load_secret("anthropic_api_key")

        self.assertEqual(value, "already-migrated")

    def test_nothing_saved_anywhere_returns_none(self):
        fake = _FakeKeyringBackend()
        with mock.patch.object(credentials, "_keyring", return_value=fake):
            self.assertIsNone(credentials.load_secret("anthropic_api_key"))


class FileFallbackMigration(_EnvIsolatedCase):
    """The keyring-less path: `_fallback_path` reusing config's file
    migration to move credentials.json the same way settings.json moves."""

    def test_credentials_file_is_copied_from_the_old_service_dir(self):
        old_dir = self.base / credentials.OLD_SERVICE_NAME
        old_dir.mkdir(parents=True)
        (old_dir / "credentials.json").write_text(
            json.dumps({"anthropic_api_key": "legacy-key"}), encoding="utf-8"
        )

        with mock.patch.object(credentials, "_keyring", return_value=None):
            value = credentials.load_secret("anthropic_api_key")

        self.assertEqual(value, "legacy-key")
        new_file = self.base / credentials.SERVICE_NAME / "credentials.json"
        self.assertTrue(new_file.exists())
        self.assertEqual(
            json.loads(new_file.read_text(encoding="utf-8"))["anthropic_api_key"],
            "legacy-key",
        )

    def test_migration_does_not_repeat_once_the_new_file_exists(self):
        old_dir = self.base / credentials.OLD_SERVICE_NAME
        old_dir.mkdir(parents=True)
        (old_dir / "credentials.json").write_text(
            json.dumps({"anthropic_api_key": "legacy-key"}), encoding="utf-8"
        )

        with mock.patch.object(credentials, "_keyring", return_value=None):
            credentials.load_secret("anthropic_api_key")  # first call migrates
            credentials.save_secret("anthropic_api_key", "rotated-key")  # user changes it
            value = credentials.load_secret("anthropic_api_key")

        self.assertEqual(value, "rotated-key")


if __name__ == "__main__":
    unittest.main()
