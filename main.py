"""Entry point: python main.py

Thin on purpose. This file used to carry a second, simplified `MainWindow`
of its own - a redesign that became the entry point in `31fe7f2` and left
`ui/main_window.py` orphaned. The consequences were not cosmetic: that
window drove the analysis workers directly instead of going through
`ui.view_model`, so the accessibility audit never ran (it computed
`wants_audit` and never read it), the scope and method chosen in its sidebar
never reached the scan, and report export, fix-on-disk, undo, bulk rewrite
and the preview highlight did not exist. Every UI test in the suite was
meanwhile exercising the window nobody launched.

There is one window again, it is the complete one, and its controls now live
in a left-hand column - the shape the redesign was reaching for. See
`ui.main_window.SIDEBAR_WIDTH`.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

import cli_install
import app_identity
import config
import detectors  # noqa: F401 -- side effect: registers built-in detectors
from i18n.translations import t
from ui import theme
from ui.main_window import MainWindow


def offer_cli_install(parent, settings: "config.Settings") -> None:
    """Ask once, on the first launch of the packaged app, whether to put the
    `xaudit` command on `PATH`.

    Why here and not silently: the symlink lands in the user's `PATH`, and
    writing there without asking is the installer behaviour this app does
    not have and does not want. Why at all: the frozen binary already *is*
    the CLI and the TUI (`app_entry.py` tells the roles apart by the name it
    was invoked as), so someone who never finds the button in Settings has
    two of the three surfaces sitting in the bundle, unreachable.

    The flag is written before the install is attempted, so a failure - a
    refused administrator prompt, an unwritable directory - does not turn
    into the same dialog on every launch. `cli_install.offer_is_due` holds
    the conditions; this function holds only what needs a window.
    """
    if not cli_install.offer_is_due(settings.cli_install_offered):
        return
    lang = settings.ui_language
    box = QMessageBox(parent)
    box.setWindowTitle(t("cli_offer_title", lang))
    box.setText(t("cli_offer_body", lang, dir=cli_install.USER_BIN_DIR))
    yes = box.addButton(t("cli_offer_yes", lang), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(t("cli_offer_no", lang), QMessageBox.ButtonRole.RejectRole)
    box.exec()

    settings.cli_install_offered = True
    settings.save()
    if box.clickedButton() is not yes:
        return
    try:
        target = cli_install.install()
    except cli_install.CliInstallError as exc:
        QMessageBox.warning(parent, t("cli_offer_title", lang), str(exc))
        return
    note = "" if cli_install.is_dir_on_path(cli_install.USER_BIN_DIR) else (
        t("settings_cli_not_on_path", lang, dir=cli_install.USER_BIN_DIR))
    QMessageBox.information(parent, t("cli_offer_title", lang),
                            t("cli_offer_done", lang, path=target) + note)


def main() -> int:
    # Before anything reads a path: folders from before the rename move to
    # their new names once (`app_identity.migrate_legacy_data`). The command
    # line and the terminal interface make the same call.
    app_identity.migrate_legacy_data()

    # `--version` before a QApplication exists. The Makefile tells whoever
    # builds the bundle to verify it with
    # `XBrain Audit.app/Contents/MacOS/XBrain Audit --version`, and that opened the
    # window and sat there instead: the one instruction written down for
    # checking a build could not be followed, on the surface where a stale
    # binary is hardest to notice.
    if "--version" in sys.argv[1:]:
        print(f"{app_identity.PRODUCT_NAME} {config.APP_VERSION}")
        return 0

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName(app_identity.PRODUCT_NAME)
    app.setOrganizationName("xFormat")

    # Styled before the window is built, so every widget is created with the
    # palette already in place — applying it afterwards makes the window
    # flash in the default Qt grey on slower machines. The palette is
    # returned and handed to the window because a few things QSS cannot
    # reach (the delegate that paints the findings list, the injected
    # preview stylesheet) need the same colour values.
    settings = config.Settings.load()
    palette = theme.apply_theme(app, settings.theme)

    window = MainWindow(palette=palette)
    window.show()
    # After `show()`: the dialog is modal to the window, and a modal parented
    # to a window that has not been shown yet opens behind it on macOS.
    offer_cli_install(window, settings)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
