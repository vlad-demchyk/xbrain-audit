"""The window learns what a folder is, and says so.

Two gaps this closes, both of which existed because `xaudit audit` knew
something the desktop app did not.

**The exclusions.** `cli_impl.scanning._build_ignore_list` has applied the
detected stack's exclusions since `project_profile` existed; the window
applied only the flat default list. So the same WordPress folder produced
hundreds of findings in vendored `wp-includes/` from the window and none
from the CLI - findings against code the person cannot change, burying the
ones they can.

**The medium.** `--medium` has been on `audit` and `fullscan`; the window
had no way to say "these are emails". On an email the browser-only checks -
canonical, Open Graph, structured data, skip link, landmarks - are category
errors, and in one real workspace they were the six loudest rules of 1074
findings.

Neither is applied silently. A profile is evidence about ownership, and
evidence can be wrong: what it decided is on screen with its own reasons,
and it can be lifted.
"""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import project_profile
from analysis_modes import SOURCE_FILE, SOURCE_REPO, SOURCE_SITE

try:
    from PySide6.QtWidgets import QApplication

    from ui.app_state import AppState
    from ui.window_parts.setup_screen import SetupScreen
    from ui.tokens import palettes
    from ui.worker import audit_worker_for
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = AppState = None


def _wordpress(root: Path) -> None:
    (root / "wp-config.php").write_text("<?php\n")
    (root / "wp-includes").mkdir()


class TheProfileDecidesWhatIsNotYours(unittest.TestCase):
    """Mostly no Qt needed: the derivation is pure.

    Mostly, because `AppState` is the class the derivation lives on and it
    is a Qt object, so the half that compares the window against the CLI
    still needs Qt to be importable. The half that only asks `Profile` does
    not, and stays runnable on a machine without it.
    """

    def test_a_profile_adds_its_exclusions_without_repeating_any(self):
        with TemporaryDirectory() as folder:
            _wordpress(Path(folder))
            profile = project_profile.detect(folder)
            base = ["node_modules/", "wp-includes/"]
            merged = profile.applied_to(base)
        self.assertEqual(merged[:2], base)
        self.assertEqual(len(merged), len(set(merged)))
        self.assertIn("wp-includes/", merged)

    @unittest.skipIf(QApplication is None, "PySide6 not available")
    def test_the_cli_and_the_state_derive_the_same_list(self):
        """One function, called from both, because two copies of an ignore
        list is how one surface scans a directory the other skips."""
        from cli_impl.scanning import _build_ignore_list

        class _Args:
            use_default_excludes = True
            exclude = None

        with TemporaryDirectory() as folder:
            _wordpress(Path(folder))
            from_cli = _build_ignore_list(_Args(), target=folder)
            profile = project_profile.detect(folder)

        state = _State(profile)
        from_window = state.ignore_patterns_with_project(
            [p for p in from_cli if p not in profile.excludes()])
        self.assertEqual(sorted(from_cli), sorted(from_window))


class _State:
    """`AppState`'s derivation without Qt - the method under test is pure."""

    def __init__(self, profile, lifted=False):
        self._project = profile
        self._project_excludes_lifted = lifted

    # `getattr`, not `AppState.x if QApplication is not None else None`.
    # Both are safe, but the conditional is safe only because the two names
    # happen to fail together, and this line runs at import time - where a
    # `NameError` is a collection error, which stops the whole suite rather
    # than this file. See `tests/test_collection_survives_without_qt.py`.
    ignore_patterns_with_project = getattr(
        AppState, "ignore_patterns_with_project", None)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheStateHoldsIt(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState()

    def test_no_folder_chosen_means_the_persons_list_unchanged(self):
        self.assertEqual(self.state.ignore_patterns_with_project(["a/"]), ["a/"])

    def test_lifting_the_exclusions_puts_the_stacks_paths_back_in_scope(self):
        with TemporaryDirectory() as folder:
            _wordpress(Path(folder))
            self.state.set_project(project_profile.detect(folder))
        with_them = self.state.ignore_patterns_with_project([])
        self.assertTrue(with_them)
        self.state.set_project_excludes_lifted(True)
        self.assertEqual(self.state.ignore_patterns_with_project([]), [])

    def test_choosing_a_medium_is_remembered_and_announced(self):
        seen = []
        self.state.project_changed.connect(lambda: seen.append(self.state.medium))
        self.state.set_medium("email")
        self.assertEqual(self.state.medium, "email")
        self.assertEqual(seen, ["email"])

    def test_the_medium_starts_unset_so_the_markup_decides(self):
        """A default of "web" would drop nothing and a default of "email"
        would drop five categories of finding. Reading it off the file is
        right nearly always, and is what the CLI does too."""
        self.assertEqual(self.state.medium, "")


@unittest.skipIf(QApplication is None, "PySide6 not available")
class ItReachesTheRun(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_a_folder_audit_carries_the_medium(self):
        with TemporaryDirectory() as folder:
            worker, refusal = audit_worker_for(
                SOURCE_REPO, target=folder, depth=0, max_pages=30,
                medium="email")
        self.assertEqual(refusal, "")
        self.assertEqual(worker.medium, "email")

    def test_the_medium_reaches_the_engine_not_just_the_worker(self):
        """The seam that matters. A worker that stores the choice and does
        not pass it on is the same as no choice at all."""
        import audit
        from ui.worker import AuditWorker

        seen = {}

        def fake_analyze_files(files, root, **kwargs):
            seen.update(kwargs)
            return _EmptyResult()

        original = audit.analyze_files
        audit.analyze_files = fake_analyze_files
        try:
            with TemporaryDirectory() as folder:
                worker = AuditWorker(target=folder, depth=0, is_repo=True,
                                     medium="email")
                worker.run()
        finally:
            audit.analyze_files = original
        self.assertEqual(seen.get("force_medium"), "email")

    def test_reading_it_off_the_file_is_passed_as_no_choice(self):
        """Empty must arrive as `None`, not as `""` - `force_medium=""` is a
        value, and a falsy one that the engine would have to second-guess."""
        import audit
        from ui.worker import AuditWorker

        seen = {}
        original = audit.analyze_files
        audit.analyze_files = lambda files, root, **kw: (
            seen.update(kw) or _EmptyResult())
        try:
            with TemporaryDirectory() as folder:
                AuditWorker(target=folder, depth=0, is_repo=True).run()
        finally:
            audit.analyze_files = original
        self.assertIsNone(seen.get("force_medium"))

    def test_a_site_has_no_medium_to_choose(self):
        """A crawled page is a page. The keyword exists on the folder branch
        only, so a site worker cannot be given one by accident."""
        worker, _refusal = audit_worker_for(
            SOURCE_SITE, target="https://example.com", depth=0, max_pages=30,
            medium="email")
        self.assertEqual(worker.medium, "")


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheCardSaysWhatItDecided(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _screen(self, state):
        return SetupScreen(state, palettes()["light"], lang="en")

    def test_the_block_is_for_folders_only(self):
        state = AppState()
        screen = self._screen(state)
        for source in (SOURCE_SITE, SOURCE_FILE):
            with self.subTest(source=source):
                state.set_source(source)
                screen.refresh()
                self.assertFalse(screen.project_block.isVisibleTo(screen))
        state.set_source(SOURCE_REPO)
        screen.refresh()
        self.assertTrue(screen.project_block.isVisibleTo(screen))

    def test_it_names_the_stack_and_counts_what_it_skips(self):
        state = AppState()
        state.set_source(SOURCE_REPO)
        with TemporaryDirectory() as folder:
            _wordpress(Path(folder))
            state.set_project(project_profile.detect(folder))
        screen = self._screen(state)
        screen.refresh()
        self.assertIn("wordpress", screen.project_note.text())
        self.assertIn(str(len(state.project.excludes())),
                      screen.project_note.text())

    def test_the_reason_travels_with_the_answer(self):
        """A wrong profile has to be arguable, which it is only if the marker
        file that produced it is in reach."""
        state = AppState()
        state.set_source(SOURCE_REPO)
        with TemporaryDirectory() as folder:
            _wordpress(Path(folder))
            state.set_project(project_profile.detect(folder))
        screen = self._screen(state)
        screen.refresh()
        self.assertIn("wp-config.php", screen.project_note.toolTip())

    def test_an_unrecognised_folder_offers_nothing_to_lift(self):
        state = AppState()
        state.set_source(SOURCE_REPO)
        with TemporaryDirectory() as folder:
            state.set_project(project_profile.detect(folder))
        screen = self._screen(state)
        screen.refresh()
        self.assertIn("No stack recognised", screen.project_note.text())
        self.assertFalse(screen.project_lift_box.isVisibleTo(screen))

    def test_ticking_the_box_lifts_them(self):
        state = AppState()
        state.set_source(SOURCE_REPO)
        with TemporaryDirectory() as folder:
            _wordpress(Path(folder))
            state.set_project(project_profile.detect(folder))
        screen = self._screen(state)
        screen.refresh()
        screen.project_lift_box.setChecked(True)
        self.assertTrue(state.project_excludes_lifted)
        self.assertEqual(state.ignore_patterns_with_project([]), [])

    def test_the_medium_combo_writes_through_to_the_state(self):
        state = AppState()
        screen = self._screen(state)
        index = screen.medium_combo.findData("email")
        self.assertGreaterEqual(index, 0)
        screen.medium_combo.setCurrentIndex(index)
        self.assertEqual(state.medium, "email")

    def test_every_medium_choice_is_named_in_every_language(self):
        from i18n.translations import t
        from ui.window_parts.setup_screen import MEDIA

        for lang in ("en", "uk", "it"):
            for value in MEDIA:
                key = f"setup_medium_{value or 'auto'}"
                with self.subTest(lang=lang, medium=value or "auto"):
                    self.assertTrue(t(key, lang))
                    self.assertNotEqual(t(key, lang), key)


class _EmptyResult:
    documents = ()


if __name__ == "__main__":
    unittest.main()
