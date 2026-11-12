"""Tests for AppState - centralized state with signals."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from analysis_modes import (
        CHECK_ACCESSIBILITY,
        CHECK_AI_PATTERNS,
        METHOD_AI,
        METHOD_LOCAL,
        SOURCE_FILE,
        SOURCE_REPO,
        SOURCE_SITE,
    )
    from ui.app_state import AppState
except Exception:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TestSourceChanges(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState()

    def test_initial_source(self):
        self.assertEqual(self.state.source, SOURCE_SITE)

    def test_set_source(self):
        self.state.set_source(SOURCE_REPO)
        self.assertEqual(self.state.source, SOURCE_REPO)

    def test_source_signal(self):
        received = []
        self.state.source_changed.connect(lambda v: received.append(v))
        self.state.set_source(SOURCE_REPO)
        self.assertEqual(received, [SOURCE_REPO])

    def test_no_signal_on_same_value(self):
        received = []
        self.state.source_changed.connect(lambda v: received.append(v))
        self.state.set_source(SOURCE_SITE)
        self.assertEqual(received, [])


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TestChecksChanges(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState()

    def test_set_checks(self):
        self.state.set_checks((CHECK_ACCESSIBILITY,))
        self.assertEqual(self.state.checks, (CHECK_ACCESSIBILITY,))

    def test_mode_changes_with_checks(self):
        self.state.set_checks((CHECK_AI_PATTERNS,))
        modes = []
        self.state.mode_changed.connect(lambda v: modes.append(v))
        self.state.set_checks((CHECK_ACCESSIBILITY,))
        # source=site, checks=accessibility -> audit
        self.assertEqual(self.state.mode, "audit")
        self.assertIn("audit", modes)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TestMethodChanges(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState()

    def test_drops_ai_when_unavailable(self):
        self.state.set_ai_available(False)
        self.state.set_methods((METHOD_AI,))
        self.assertEqual(self.state.methods, (METHOD_LOCAL,))

    def test_keeps_ai_when_available(self):
        self.state.set_ai_available(True)
        self.state.set_methods((METHOD_AI,))
        self.assertEqual(self.state.methods, (METHOD_AI,))


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TestAiAvailable(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState()

    def test_disabling_ai_forces_local(self):
        self.state.set_ai_available(True)
        self.state.set_methods((METHOD_AI,))
        self.state.set_ai_available(False)
        self.assertEqual(self.state.methods, (METHOD_LOCAL,))

    def test_signal(self):
        received = []
        self.state.ai_available_changed.connect(lambda v: received.append(v))
        self.state.set_ai_available(True)
        self.assertEqual(received, [True])


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TestMode(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState()

    def test_initial_mode(self):
        self.assertEqual(self.state.mode, "audit")
        self.assertEqual(self.state.checks, (CHECK_ACCESSIBILITY,))

    def test_repo_mode(self):
        self.state.set_checks((CHECK_AI_PATTERNS,))
        self.state.set_source(SOURCE_REPO)
        self.assertEqual(self.state.mode, "repo")

    def test_file_mode(self):
        self.state.set_checks((CHECK_AI_PATTERNS,))
        self.state.set_source(SOURCE_FILE)
        self.assertEqual(self.state.mode, "file")

    def test_audit_mode(self):
        self.state.set_checks((CHECK_ACCESSIBILITY,))
        self.assertEqual(self.state.mode, "audit")


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TestWantsProvider(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState()

    def test_visible_when_ai_and_ai_method(self):
        self.state.set_checks((CHECK_AI_PATTERNS,))
        self.state.set_ai_available(True)
        self.state.set_methods((METHOD_AI,))
        self.assertTrue(self.state.wants_provider)

    def test_hidden_when_local(self):
        self.state.set_methods((METHOD_LOCAL,))
        self.assertFalse(self.state.wants_provider)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TestAnyChanged(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState()

    def test_fires_on_source(self):
        count = []
        self.state.any_changed.connect(lambda: count.append(1))
        self.state.set_source(SOURCE_REPO)
        self.assertEqual(len(count), 1)

    def test_fires_on_checks(self):
        count = []
        self.state.any_changed.connect(lambda: count.append(1))
        self.state.set_checks((CHECK_AI_PATTERNS,))
        self.assertEqual(len(count), 1)

    def test_not_fired_on_same_value(self):
        count = []
        self.state.any_changed.connect(lambda: count.append(1))
        self.state.set_source(SOURCE_SITE)
        self.assertEqual(len(count), 0)


if __name__ == "__main__":
    unittest.main()
