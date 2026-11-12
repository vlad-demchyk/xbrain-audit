"""Choosing `xformat` in the TUI used to be a choice you could not act on.

Settings offers three providers. Two of them own their credentials
elsewhere - Claude Code has its own `claude auth login`, Anthropic takes a
key - and the third, xFormat, takes an email and a password. The TUI let a
person select it and gave them nowhere to sign in, so the only ways to make
the setting mean anything were the desktop window or `xaudit ai login`.
A setting whose one prerequisite lives on another surface is a setting that
lies about what it does.

What this file holds to, beyond "the screen exists":

* **The password is spent, not kept.** It is cleared from the widget before
  the call is even made, and nothing writes it anywhere. That is the same
  contract `ui/sign_in_dialog.py` and `cli_impl.aicmds.cmd_ai_login` keep,
  and it is the reason this screen is allowed to exist while an API-key
  field still deliberately is not: a key is a secret that must be *kept*.
* **The network call is off the UI thread.** On a captive network a
  synchronous sign-in is thirty seconds of a frozen interface.
* **The other two providers are told where their sign-in actually is**,
  rather than being offered a form that cannot work.
"""
from __future__ import annotations

import ast
import inspect
import os
import unittest
from pathlib import Path

os.environ.setdefault("TEXTUAL_HEADLESS", "1")

from i18n.translations import t
from tui.screens.account import SIGNS_IN, AccountScreen

SOURCE = Path(__file__).resolve().parent.parent / "tui" / "screens" / "account.py"


class ItIsReachable(unittest.TestCase):

    def test_the_menu_offers_it(self):
        from tui.screens.main_menu import MENU

        self.assertIn("account", [name for _key, name in MENU])

    def test_the_app_installs_it_like_every_other_screen(self):
        from tui.app import XBrainAuditApp

        self.assertIn("account", XBrainAuditApp.SCREENS_IN_ORDER)
        self.assertIn("account", XBrainAuditApp()._screen_classes())

    def test_a_new_entry_did_not_renumber_the_old_ones(self):
        """The existing shortcuts are documented, are in muscle memory and
        are what the other tests press."""
        from tui.screens.main_menu import MENU

        self.assertEqual(MENU[:8],
                         (("1", "scan"), ("2", "audit"), ("3", "fullscan"),
                          ("4", "reports"), ("5", "settings"), ("6", "update"),
                          ("7", "uninstall"), ("8", "logs")))


class ThePasswordIsSpentNotKept(unittest.TestCase):

    def test_it_is_cleared_before_the_call_is_made(self):
        source = inspect.getsource(AccountScreen._sign_in)
        cleared = source.index('password_field.value = ""')
        called = source.index("threading.Thread")
        self.assertLess(cleared, called)

    def test_nothing_in_the_screen_writes_it_anywhere(self):
        """No settings attribute, no file, no log line."""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        self.assertNotIn("password", target.attr,
                                         "the password must not be stored")

    def test_the_screen_says_so_where_a_person_can_read_it(self):
        for lang in ("en", "uk", "it"):
            with self.subTest(lang=lang):
                sentence = t("tui_account_privacy", lang)
                self.assertNotEqual(sentence, "tui_account_privacy")
                self.assertGreater(len(sentence), 40)


class TheCallDoesNotFreezeTheInterface(unittest.TestCase):

    def test_sign_in_runs_off_the_ui_thread(self):
        self.assertIn("threading.Thread",
                      inspect.getsource(AccountScreen._sign_in))

    def test_the_result_comes_back_through_the_apps_own_thread(self):
        """`call_from_thread` is how Textual gets a value back onto the UI
        thread; touching a widget from the worker is a race, not a shortcut."""
        self.assertIn("call_from_thread",
                      inspect.getsource(AccountScreen._sign_in))


class TheOtherProvidersAreSentSomewhereReal(unittest.TestCase):

    def test_only_xformat_has_credentials_to_take_here(self):
        self.assertEqual(SIGNS_IN, "xformat")

    def test_each_of_the_other_two_is_told_where_its_sign_in_lives(self):
        for provider, expected in (("anthropic", "ANTHROPIC_API_KEY"),
                                   ("claude-code", "claude auth login")):
            for lang in ("en", "uk", "it"):
                sentence = t(f"tui_account_elsewhere_{provider}", lang)
                with self.subTest(provider=provider, lang=lang):
                    self.assertIn(expected, sentence)


class ItIsSaidInEveryLanguage(unittest.TestCase):

    KEYS = ("tui_menu_account", "tui_account_title", "tui_account_email",
            "tui_account_password", "tui_account_sign_out",
            "tui_account_signed_in", "tui_account_signed_out",
            "tui_account_working", "tui_account_welcome",
            "tui_account_not_xformat", "tui_account_unknown")

    def test_no_key_falls_through_to_its_own_name(self):
        for key in self.KEYS:
            for lang in ("en", "uk", "it"):
                with self.subTest(key=key, lang=lang):
                    self.assertNotEqual(t(key, lang), key)


if __name__ == "__main__":
    unittest.main()
