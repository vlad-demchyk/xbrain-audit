"""The first-launch offer to put `xaudit` on `PATH` (`main.offer_cli_install`).

`cli_install.offer_is_due` decides *whether* to ask, and its own tests cover
that. This file covers what needs a window: that the question is asked once
and only once even when the install fails, and that "Later" leaves the
machine exactly as it was.

Headless: Qt runs on the offscreen platform, like the other widget tests, and
every path here is driven by patching `QMessageBox` rather than by clicking -
a real modal would block the suite forever.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    import cli_install
    import config
    import main
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = QMessageBox = None


class _Box:
    """A stand-in for the modal. `accepted` decides which button 'was clicked'.

    `ButtonRole` and the class-level `warning`/`information` are the parts of
    `QMessageBox` this function touches on the class rather than the instance.
    """

    accepted = True
    #: `getattr`, not `QMessageBox.ButtonRole`. A class body runs at *import*
    #: time, so on a machine without Qt this line raised `NameError` before
    #: the `skipIf` below ever got the chance to fire, and the whole file
    #: failed to collect - which stops the entire suite, not one test.
    #: Measured 2026-09-02 on CI, where `libEGL.so.1` is absent.
    ButtonRole = getattr(QMessageBox, "ButtonRole", None)
    warning = staticmethod(lambda *a, **k: None)
    information = staticmethod(lambda *a, **k: None)

    def __init__(self, parent=None):
        self.buttons = []

    def setWindowTitle(self, text):
        self.title = text

    def setText(self, text):
        self.text = text

    def addButton(self, label, role):
        button = object()
        self.buttons.append(button)
        return button

    def exec(self):
        return 0

    def clickedButton(self):
        return self.buttons[0] if self.accepted else self.buttons[-1]


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheFirstLaunchOffer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = Path(self._tmp.name) / "settings.json"
        self._patches = [
            mock.patch("config.config_file", return_value=path),
            mock.patch("cli_install.offer_is_due", return_value=True),
        ]
        for patch in self._patches:
            patch.start()
        self.settings = config.Settings()

    def tearDown(self):
        for patch in self._patches:
            patch.stop()
        self._tmp.cleanup()

    def _run(self, accepted, install=None):
        box = type("Box", (_Box,), {"accepted": accepted})
        with mock.patch("main.QMessageBox", box), \
                mock.patch("cli_install.install",
                           install or mock.Mock(return_value=Path("/x/xaudit"))) as installed:
            main.offer_cli_install(None, self.settings)
        return installed

    def test_accepting_installs_and_remembers_the_question(self):
        installed = self._run(accepted=True)
        installed.assert_called_once()
        self.assertTrue(self.settings.cli_install_offered)
        self.assertTrue(config.Settings.load().cli_install_offered)

    def test_declining_changes_nothing_but_is_still_remembered(self):
        installed = self._run(accepted=False)
        installed.assert_not_called()
        self.assertTrue(config.Settings.load().cli_install_offered)

    def test_a_failed_install_does_not_come_back_next_launch(self):
        """The flag is written on the *question*, not on the answer. A refused
        administrator prompt used to be the shape that turns a convenience
        into a dialog on every single launch."""
        failing = mock.Mock(side_effect=cli_install.CliInstallError("nope"))
        self._run(accepted=True, install=failing)
        self.assertTrue(config.Settings.load().cli_install_offered)

    def test_nothing_happens_when_the_offer_is_not_due(self):
        with mock.patch("cli_install.offer_is_due", return_value=False), \
                mock.patch("main.QMessageBox") as box:
            main.offer_cli_install(None, self.settings)
        box.assert_not_called()
        self.assertFalse(self.settings.cli_install_offered)


if __name__ == "__main__":
    unittest.main()
