"""The suite must not be able to write the person's own settings.

This is the case `P-13` existed for. `config.CONFIG_FILE` used to be a module
constant resolved during import, so `XDG_CONFIG_HOME` set by a test came too
late and `Settings.save()` always landed on the real
`~/.config/xbrain-audit/settings.json`. Two tests found that out by damage rather
than by failure - one flipped the developer's auto-start toggle on disk, one
passed only because their `ui_language` happened to be `en` - and the fix was
copy-pasted per test as `window.settings.save = lambda: None`.

The mechanism is now `config.config_file()` plus `tests/conftest.py`. These
cases assert the mechanism itself, because a mechanism nobody checks is how
the constant came back last time.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

import config


class TheConfigPathFollowsTheEnvironment(unittest.TestCase):
    def test_conftest_redirected_this_run(self):
        """The whole suite is pointed somewhere temporary, not at $HOME."""
        home_config = Path.home() / ".config" / config.APP_NAME
        self.assertNotEqual(config.config_file().parent.resolve(),
                            home_config.resolve())

    def test_the_path_is_resolved_per_call_not_per_import(self):
        """The property the constant did not have.

        If this ever fails, `config_file()` has been turned back into
        something computed once, and every test in the suite is writing the
        developer's real file again.
        """
        before = config.config_file()
        original = os.environ.get("XDG_CONFIG_HOME")
        try:
            os.environ["XDG_CONFIG_HOME"] = str(Path(before).parent.parent / "elsewhere")
            self.assertNotEqual(config.config_file(), before)
        finally:
            if original is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = original
        self.assertEqual(config.config_file(), before)

    def test_saving_writes_where_the_environment_points(self):
        settings = config.Settings()
        settings.ui_language = "it"
        settings.save()
        written = config.config_file()
        self.assertTrue(written.exists())
        self.assertIn('"ui_language": "it"', written.read_text(encoding="utf-8"))

    def test_no_test_reaches_the_real_settings_file(self):
        """A save cannot land in the person's config directory.

        Asserted as a path relationship rather than by watching the file,
        because the failure this guards against is silent: the real file is
        simply different afterwards, and nothing in a green run says so.
        """
        real = (Path.home() / ".config" / config.APP_NAME / "settings.json").resolve()
        config.Settings().save()
        self.assertNotEqual(config.config_file().resolve(), real)


if __name__ == "__main__":
    unittest.main()
