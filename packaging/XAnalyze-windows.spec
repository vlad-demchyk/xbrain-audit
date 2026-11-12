# -*- mode: python ; coding: utf-8 -*-
"""Windows build of XAnalyze: one folder, two executables.

Run from the repository root (or use `scripts/build_windows.ps1`):

    venv\\Scripts\\pyinstaller packaging\\XAnalyze-windows.spec --noconfirm

The result is `dist\\XAnalyze\\` with

* `XAnalyze.exe` - the window. Linked as a GUI program, so starting it does
  not open a console next to it.
* `xanalyze-cli.exe` - the command line and, with no subcommand, the TUI.
  Linked as a console program, because Windows decides that when a program
  is linked: a GUI executable has no stdout to print `--help` to.

Both are built from the same `Analysis` and share one `_internal\\` folder,
so the second executable costs a few hundred kilobytes, not a second copy of
Qt. `app_entry.py` tells them apart by the executable's name.

What is the same as `packaging/XAnalyze.spec`, and why it is copied rather
than shared: the data files below must stay the list the macOS spec ships
(`tests/test_windows_packaging.py` compares the two), but the macOS spec is
built only on a Mac and is the release path - changing its structure without
a Mac to build it on would trade a known-good release for a tidier file.

What differs: no `.app` bundle and no `.icns`, the Windows keychain backend
(Credential Manager) instead of the macOS one, and no post-build repair of
the QtWebEngine framework layout - that repair is for a macOS-only
flattening; on Windows PyInstaller's own hook places `QtWebEngineProcess.exe`
correctly, and the check at the end of this file says so if it ever stops.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = Path(SPECPATH).resolve().parent
DIST = Path(DISTPATH).resolve()

datas = [
    (str(ROOT / "ui" / "design" / "xformat-tokens.css"), "ui/design"),
    (str(ROOT / "ui" / "design" / "xanalyze-desktop.css"), "ui/design"),
    (str(ROOT / "audit" / "vendor" / "axe.min.js"), "audit/vendor"),
    (str(ROOT / "audit" / "vendor" / "HTMLCS.js"), "audit/vendor"),
    (str(ROOT / "audit" / "vendor" / "engine_codes.json"), "audit/vendor"),
    (str(ROOT / "corpus" / "labelled.jsonl"), "corpus"),
    (str(ROOT / "audit" / "vendor" / "axe-LICENSE.txt"), "audit/vendor"),
    (str(ROOT / "audit" / "vendor" / "web-vitals.attribution.iife.js"), "audit/vendor"),
    (str(ROOT / "audit" / "vendor" / "web-vitals-LICENSE.txt"), "audit/vendor"),
    (str(ROOT / "audit" / "vendor" / "web-vitals.json"), "audit/vendor"),
    (str(ROOT / "ui" / "design" / "assets"), "ui/design/assets"),
    *collect_data_files("textual"),
]


def _c2pa_bundle():
    """The optional C2PA reader, when the build environment has it."""
    try:
        import c2pa
    except Exception:  # noqa: BLE001 - building without it is allowed
        return [], []
    package = Path(c2pa.__file__).parent
    binaries = [(str(lib), "c2pa/c2pa") for lib in package.rglob("*.dll")]
    names = collect_submodules("c2pa") + collect_submodules("cryptography")
    return binaries, names


_C2PA_BINARIES, _C2PA_IMPORTS = _c2pa_bundle()

hiddenimports = [
    *collect_submodules("detectors"),
    *collect_submodules("audit"),
    *collect_submodules("llm"),
    *collect_submodules("tui"),
    *collect_submodules("textual"),
    *collect_submodules("cryptography"),
    # `keyring` finds its backend through entry points, which a frozen app
    # does not have; without this the Credential Manager is never used.
    "keyring.backends.Windows",
    "keyring.backends.fail",
    *_C2PA_IMPORTS,
]

analysis = Analysis(
    [str(ROOT / "app_entry.py")],
    pathex=[str(ROOT)],
    binaries=_C2PA_BINARIES,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSerialPort",
        "PySide6.QtTest", "PySide6.QtDesigner", "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)


def _executable(name: str, console: bool):
    return EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
    )


window = _executable("XAnalyze", console=False)
command_line = _executable("xanalyze-cli", console=True)

collected = COLLECT(
    window,
    command_line,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="XAnalyze",
)

# A build whose browser cannot start is not a build worth shipping: the site
# preview and the whole browser audit pass run in this helper process.
_helpers = list((DIST / "XAnalyze").rglob("QtWebEngineProcess.exe"))
if not _helpers:
    raise SystemExit(
        "XAnalyze: QtWebEngineProcess.exe is missing from the build - the "
        "site preview and the browser audit pass would both be dead.")
