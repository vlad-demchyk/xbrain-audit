"""A SharePoint Online target, as the window, the TUI and the report see it.

The CLI reads a SharePoint site through `cli_impl.auditpass`; these tests pin
that the other surfaces read it through the same functions rather than a
copy of them, and that each says what the person has to do when there is no
sign-in. All addresses are placeholders: nothing here reaches a network.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SITE = "https://contoso.sharepoint.com/sites/ExampleSite"

try:
    from PySide6.QtWidgets import QApplication, QPushButton, QStatusBar
except Exception:  # noqa: BLE001 - the GUI half is skipped without Qt
    QApplication = None


class TheReasonsAreTranslated(unittest.TestCase):
    KEYS = ("why_render_sharepoint", "why_page_tree_sharepoint",
            "why_site_scope_sharepoint", "why_sign_in_sharepoint",
            "sign_in_site_on_idp", "sign_in_site_back",
            "sign_in_site_required", "tui_sharepoint_login",
            "sign_in_site_incomplete", "sign_in_site_checking",
            "sign_in_site_elsewhere")

    def test_every_key_has_three_languages(self):
        from i18n.translations import _STRINGS as TRANSLATIONS

        for key in self.KEYS:
            with self.subTest(key=key):
                self.assertIn(key, TRANSLATIONS)
                self.assertEqual(set(TRANSLATIONS[key]), {"uk", "it", "en"})
                for text in TRANSLATIONS[key].values():
                    self.assertTrue(text.strip())

    def test_the_sign_in_dialog_has_one_source_of_wording(self):
        """The dialog used to carry a fallback table of its own; two copies
        of a sentence is two chances for one to drift. Every key it reads is
        in the shared dictionary, in all three languages."""
        import re
        from pathlib import Path

        from i18n.translations import _STRINGS
        from ui import site_sign_in

        self.assertFalse(hasattr(site_sign_in, "_FALLBACK"))
        source = Path(site_sign_in.__file__).read_text(encoding="utf-8")
        keys = set(re.findall(r'_text\(\s*"([a-z_]+)"', source))
        keys |= set(re.findall(r'\bt\(\s*"([a-z_]+)"', source))
        self.assertTrue({"sign_in_site_on_idp", "sign_in_site_back",
                         "sign_in_site_incomplete",
                         "sign_in_site_elsewhere"} <= keys)
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(key, _STRINGS)
                self.assertEqual(set(_STRINGS[key]), {"uk", "it", "en"})

    def test_every_recipe_reason_resolves(self):
        import run_profile
        from i18n.translations import _STRINGS as TRANSLATIONS

        for recipe in (*run_profile.RECIPES, *run_profile.PROMPTS):
            with self.subTest(reason=recipe.reason):
                self.assertIn(recipe.reason, TRANSLATIONS)


class OwnershipReadsTheAddress(unittest.TestCase):
    def test_sharepoint_host_owns_its_layouts_assets_without_markup(self):
        from audit.engine import attribute_ownership

        issue = SimpleNamespace(
            snippet='<img src="/_layouts/15/images/x.png">', owner="")
        result = SimpleNamespace(root=SITE, markup_sample="",
                                 issues=lambda: [issue])
        counts = attribute_ownership(result)
        self.assertEqual(issue.owner, "sharepoint")
        self.assertEqual(counts, {"sharepoint": 1})

    def test_ordinary_host_without_markup_owns_nothing(self):
        from audit.engine import attribute_ownership

        issue = SimpleNamespace(
            snippet='<img src="/_layouts/15/images/x.png">', owner="")
        result = SimpleNamespace(root="https://example.com/", markup_sample="",
                                 issues=lambda: [issue])
        self.assertEqual(attribute_ownership(result), {})
        self.assertEqual(issue.owner, "")


class TheTuiNamesTheCommand(unittest.TestCase):
    def test_hint_is_the_cli_login_command(self):
        try:
            from tui.screens.base import sign_in_hint
        except ImportError as exc:  # textual is optional
            self.skipTest(str(exc))
        from cli_impl.auditpass import login_hint

        for lang in ("uk", "it", "en"):
            with self.subTest(lang=lang):
                text = sign_in_hint(SITE, lang)
                self.assertIn(login_hint(SITE), text)
                self.assertIn("contoso.sharepoint.com", text)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheWindowAsksForTheSignIn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        from ui.main_window import MainWindow

        class Stub:
            _apply_run_plan = MainWindow._apply_run_plan
            _ask_for_sign_in = MainWindow._ask_for_sign_in

        stub = Stub()
        stub.lang = "en"
        stub.sign_in_site_btn = QPushButton()
        stub.status_bar = QStatusBar()
        stub.app_state = SimpleNamespace(target=SITE, profile_touched=set(),
                                         set_web_parts=lambda *a, **k: None)
        return stub

    def _plan(self, signed_in):
        import run_profile

        return run_profile.build(SITE, forced_url=True, signed_in=signed_in)

    def test_no_session_highlights_the_button_and_says_why(self):
        from ui import theme

        window = self._window()
        window._apply_run_plan(self._plan(signed_in=False))
        self.assertEqual(window.sign_in_site_btn.property("class"),
                         theme.CLASS_PRIMARY)
        self.assertIn("contoso.sharepoint.com",
                      window.status_bar.currentMessage())

    def test_a_session_turns_the_highlight_off(self):
        window = self._window()
        window._apply_run_plan(self._plan(signed_in=False))
        window._apply_run_plan(self._plan(signed_in=True))
        self.assertEqual(window.sign_in_site_btn.property("class") or "", "")

    def test_sharepoint_recipes_tick_nothing_on_the_window(self):
        """`render`, `page_tree` and `site_scope` have no control here: the
        view model reads them at run time. Applying the plan must not fail on
        them, nor reach for a control that does not exist."""
        window = self._window()
        plan = self._plan(signed_in=True)
        self.assertTrue({"render", "page_tree", "site_scope"}
                        <= {item.option for item in plan.suggestions})
        window._apply_run_plan(plan)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheViewModelPlansLikeTheCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _run(self, source, target, repo=""):
        from ui.view_model import MainViewModel

        stub = SimpleNamespace(state=SimpleNamespace(
            source=source, scan_target=target, paired_repo=repo))
        return MainViewModel._sharepoint_run(stub)

    def test_sharepoint_site_gets_tree_scope_and_render(self):
        from analysis_modes import SOURCE_SITE
        from cli_impl.auditpass import PAGE_TREE_SHAREPOINT

        run = self._run(SOURCE_SITE, SITE)
        self.assertIsNotNone(run)
        self.assertTrue(run.sharepoint)
        self.assertEqual(run.page_tree, PAGE_TREE_SHAREPOINT)
        self.assertEqual(run.site_scope, "/sites/ExampleSite")
        self.assertEqual(run.render, "always")

    def test_other_site_and_other_sources_get_nothing(self):
        from analysis_modes import SOURCE_REPO, SOURCE_SITE

        self.assertIsNone(self._run(SOURCE_SITE, "https://example.com/"))
        self.assertIsNone(self._run(SOURCE_REPO, SITE))
        self.assertIsNone(self._run(SOURCE_SITE, ""))


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheWorkerCrawlsThroughTheSharedFunction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from cli_impl import auditpass

        self.auditpass = auditpass
        self.original = auditpass.sharepoint_pages
        self.addCleanup(setattr, auditpass, "sharepoint_pages", self.original)

    def _worker(self, plan):
        from ui.worker import AuditWorker

        return AuditWorker(target=SITE, depth=1, max_pages=5, sharepoint=plan)

    def _plan(self):
        from cli_impl.auditpass import PAGE_TREE_SHAREPOINT, SharePointRun

        return SharePointRun(sharepoint=True, page_tree=PAGE_TREE_SHAREPOINT,
                             site_scope="/sites/ExampleSite")

    def test_tree_pages_are_the_run_and_the_audit_is_zoned(self):
        calls = {}
        tree = SimpleNamespace(status="ok")

        def fake(target, config, **kwargs):
            calls.update(kwargs, target=target)
            return ["page"], tree

        self.auditpass.sharepoint_pages = fake
        worker = self._worker(self._plan())
        pages = worker._crawl(SimpleNamespace(), None, None)
        self.assertEqual(pages, ["page"])
        self.assertIs(worker.page_tree, tree)
        self.assertEqual(calls["page_tree"], "sharepoint")
        self.assertEqual(calls["site_scope"], "/sites/ExampleSite")
        self.assertEqual(worker._sharepoint_kwargs(), {"sharepoint": True})

    def test_missing_sign_in_fails_the_run_instead_of_a_clean_report(self):
        import sharepoint_tree

        tree = SimpleNamespace(status=sharepoint_tree.STATUS_AUTH,
                               auth_reason="")
        self.auditpass.sharepoint_pages = lambda *a, **k: ([], tree)
        worker = self._worker(self._plan())
        failures = []
        worker.failed.connect(failures.append)
        self.assertIsNone(worker._crawl(SimpleNamespace(), None, None))
        self.assertEqual(len(failures), 1)
        self.assertIn(self.auditpass.login_hint(SITE), failures[0])

    def test_no_plan_is_the_ordinary_crawl(self):
        worker = self._worker(None)
        self.assertEqual(worker._sharepoint_kwargs(), {})


if __name__ == "__main__":
    unittest.main()
