"""One temporary config directory for the whole test run.

A test that touches `Settings` used to write the developer's real
`~/.config/xanalyze/settings.json`, because `config.CONFIG_FILE` was a module
constant computed during import: by the time a test could set
`XDG_CONFIG_HOME`, the path was already decided. That is not a theoretical
hazard. `tests/test_devserver_gui.py` flipped the real auto-start toggle on
disk and passed, and `tests/test_ui_suppression.py` carried three copies of

    window.settings.save = lambda: None  # do not touch the real settings.json

which is what the absence of a mechanism looks like: every author has to
remember, and forgetting is silent. See `P-13`.

`config.config_file()` now resolves the path at the moment of the read or the
write, so pointing one environment variable at a temporary directory isolates
the entire process — including code that saves settings five call levels deep,
which is where the leaks actually came from.

Set here, at collection time, rather than in a fixture: `config` is imported at
module scope by most of the suite, and `_config_dir()` creates the directory as
a side effect of the first call.

`tests/test_renaming_migration.py` overrides this again per test, and must: its
subject *is* the directory logic, so it needs to control both the old and the
new location itself.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

#: Kept alive for the process, not cleaned per test. The directory is the
#: shared "user config" the whole run sees, and removing it between tests
#: would make settings vanish mid-suite for no reason a test could explain.
_CONFIG_HOME = tempfile.TemporaryDirectory(prefix="xanalyze-tests-config-")
os.environ["XDG_CONFIG_HOME"] = _CONFIG_HOME.name

#: The same leak, for reports. Every test that ran a scan through the CLI or
#: the window saved its run under the developer's real `~/Documents/XAnalyze`
#: - one full run left a few dozen folders there, and `mixed-problems` had
#: grown to 366 of them. `XANALYZE_REPORT_ROOT` is the override the run folder
#: already honours; the tests of the root itself set and restore it per test.
_REPORT_ROOT = tempfile.TemporaryDirectory(prefix="xanalyze-tests-reports-")
os.environ["XANALYZE_REPORT_ROOT"] = _REPORT_ROOT.name

# Set this before pytest imports test modules, several of which create a
# QApplication directly instead of going through audit.driver's helper.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Windows: the offscreen platform finds no fonts on its own (see the helper).
if sys.platform == "win32":
    from audit.driver import offscreen_fonts

    offscreen_fonts()
_CHROMIUM_FLAGS = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
_HEADLESS_FLAGS = ("--disable-gpu", "--disable-software-rasterizer", "--no-sandbox")
_MISSING_HEADLESS_FLAGS = [flag for flag in _HEADLESS_FLAGS
                           if flag not in _CHROMIUM_FLAGS.split()]
if _MISSING_HEADLESS_FLAGS:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        f"{_CHROMIUM_FLAGS} {' '.join(_MISSING_HEADLESS_FLAGS)}").strip()

try:
    from PySide6.QtCore import QCoreApplication, Qt

    # QtWebEngine's browser and compositor share OpenGL contexts. This must be
    # set before any test creates QApplication; importing QtWebEngine alone
    # did not reliably set it for PySide6 on macOS.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
except ImportError:
    pass


_PROFILE_RELEASE_WARNING = (
    "Release of profile requested but WebEnginePage still not deleted")
_PROFILE_RELEASE_WARNINGS: list[str] = []
_PREVIOUS_QT_MESSAGE_HANDLER = None
_TEST_QAPPLICATION = None


def pytest_sessionstart(session):
    """Turn the WebEngine profile lifetime warning into a suite failure."""
    global _PREVIOUS_QT_MESSAGE_HANDLER

    try:
        from PySide6.QtCore import qInstallMessageHandler
    except ImportError:
        return

    def handle_qt_message(mode, context, message):
        rendered = str(message)
        if _PROFILE_RELEASE_WARNING in rendered:
            _PROFILE_RELEASE_WARNINGS.append(rendered)
        if _PREVIOUS_QT_MESSAGE_HANDLER is not None:
            _PREVIOUS_QT_MESSAGE_HANDLER(mode, context, message)
        else:
            print(rendered, file=sys.stderr)

    _PREVIOUS_QT_MESSAGE_HANDLER = qInstallMessageHandler(handle_qt_message)


def _drain_qt_webengine_widgets() -> None:
    """Close test-created WebEngine pages before their profiles/application."""
    global _TEST_QAPPLICATION

    widgets_module = sys.modules.get("PySide6.QtWidgets")
    app_type = getattr(widgets_module, "QApplication", None)
    app = app_type.instance() if app_type is not None else None
    if app is None:
        return
    # unittest classes sometimes own the only Python reference to QApplication.
    # Keep the singleton alive across later modules and Chromium callbacks.
    _TEST_QAPPLICATION = app

    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        return

    # The test process keeps this QApplication for later modules. Closing the
    # last offscreen window must not request that shared event loop to quit.
    app.setQuitOnLastWindowClosed(False)

    views = [widget for widget in app.allWidgets()
             if isinstance(widget, QWebEngineView)]
    windows = list(app.topLevelWidgets())

    for view in views:
        try:
            view.stop()
        except RuntimeError:
            pass
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass

    # A QWebEngineView creates a page it owns, while callers may also install
    # a separately owned page. Detach first, then ask any still-live wrapper
    # to delete later. The wrapper is already invalid for the owned-page case.
    for view in views:
        try:
            page = view.page()
            view.setPage(None)
        except RuntimeError:
            continue
        if page is not None:
            try:
                page.deleteLater()
            except RuntimeError:
                pass
        try:
            view.deleteLater()
        except RuntimeError:
            pass

    for window in windows:
        try:
            window.deleteLater()
        except RuntimeError:
            pass

    for _ in range(3):
        QCoreApplication.sendPostedEvents(
            None, QEvent.Type.DeferredDelete.value)
        app.processEvents()


@pytest.fixture(scope="module", autouse=True)
def _release_webengine_after_module():
    """Bound GUI-test page lifetime to one module and fail on Qt's warning."""
    warning_start = len(_PROFILE_RELEASE_WARNINGS)
    yield
    _drain_qt_webengine_widgets()
    new_warnings = _PROFILE_RELEASE_WARNINGS[warning_start:]
    if new_warnings:
        pytest.fail(
            "QtWebEngine released a profile before its page was deleted: "
            f"{new_warnings[0]}", pytrace=False)


def pytest_sessionfinish(session, exitstatus):
    """Catch delayed warnings that arrive after the last module fixture."""
    _drain_qt_webengine_widgets()
    if not _PROFILE_RELEASE_WARNINGS:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep(
            "!", f"{len(_PROFILE_RELEASE_WARNINGS)} QtWebEngine profile lifetime warning(s)")
    session.exitstatus = pytest.ExitCode.TESTS_FAILED
