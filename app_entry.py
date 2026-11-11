"""Frozen entry point: one executable, two roles, chosen by invocation name.

Only used by `packaging/XAnalyze.spec` — a `python main.py` / `python cli.py`
dev run never touches this file.

The alternative considered was PyInstaller's `MERGE()`, building a genuinely
separate `xanalyze-cli` executable alongside the GUI one. `MERGE()` gives
every executable *after* the first "onefile" semantics: it has to extract
its referenced dependencies from the first executable's directory into a
temp dir on every single launch. The CLI depends on the same PySide6/
QtWebEngine binaries as the GUI (`audit.driver`, used by `cli.py audit
--render`, imports `QtWebEngineCore` too), so every `xanalyze scan ...`
invocation would pay that extraction cost - fine for an app opened once,
wrong for a command meant to start quickly and often.

Instead: one binary, exposed under a second name via a symlink
(`cli_install.py`). The shell sets `sys.argv[0]` to the name actually typed,
not the name of the file the symlink resolves to - the same mechanism `git`
uses for `git-<subcommand>` and BusyBox uses for its applets - so the two
roles are told apart with no extra process, no extra copy, no extraction.

When invoked as ``xanalyze`` with no subcommand, launches the interactive
TUI (terminal interface). With a subcommand, runs the CLI. As
``XAnalyze``, launches the GUI.
"""
from __future__ import annotations

import sys
from pathlib import Path

#: Must match `cli_install.CLI_NAME` - the name the symlink is installed
#: under. Not imported from there to keep this dispatch trivial to read
#: without following another module first.
_CLI_INVOCATION_NAME = "xanalyze"

#: The Windows build's console executable (`packaging/XAnalyze-windows.spec`).
#: Not `xanalyze.exe`: Windows file names ignore case, so it would be the same
#: file as the window's `XAnalyze.exe`. A second executable at all, because
#: Windows decides console versus window when the program is linked, not
#: when it is run - one binary cannot be both.
_WINDOWS_CLI_STEM = "xanalyze-cli"


def _invoked_as_cli() -> bool:
    if sys.platform == "win32":
        # The executable itself rather than argv[0]: what cmd puts in
        # argv[0] is what was typed, and `XAnalyze` typed in lower case
        # would otherwise be taken for the command line.
        return Path(sys.executable).stem.lower() == _WINDOWS_CLI_STEM
    return Path(sys.argv[0]).name == _CLI_INVOCATION_NAME


def _warn_if_stale() -> None:
    """If this frozen binary was built from a different source version, say so."""
    import config

    # For onedir builds the executable sits next to _internal/.  Walk up from
    # the executable's real path until we find a .build_version marker; if the
    # version inside does not match what was compiled in, the binary is stale.
    exe = Path(sys.executable).resolve()
    for candidate in [exe.parent, exe.parent.parent]:
        marker = candidate / ".build_version"
        if marker.exists():
            try:
                build_ver = marker.read_text(encoding="utf-8").strip()
            except OSError:
                return
            if build_ver != config.APP_VERSION:
                print(
                    f"# WARNING: binary is version {config.APP_VERSION} but was "
                    f"built from source {build_ver}.\n"
                    f"# Run: make rebuild  (from the repo root)",
                    file=sys.stderr,
                )
            return


def _install_cli() -> int:
    """`XAnalyze --install-cli`: link this app as `xanalyze`, without a window.

    For a person who wants only the command line: the app is the one
    download, and this is what the separate CLI archive used to be for.
    """
    import cli_install

    try:
        link = cli_install.install()
    except cli_install.CliInstallError as exc:
        print(f"could not install the command: {exc}", file=sys.stderr)
        return 2
    print(f"installed: {link} -> {cli_install.bundled_cli_path()}")
    if not cli_install.is_dir_on_path(link.parent):
        print(f"add {link.parent} to PATH to run it as `xanalyze`")
    return 0


def run() -> int:
    # A frozen binary re-executes *itself* to start a child process, so
    # anything that spawns one hands the child our own argv - and `xanalyze`
    # answered with `invalid choice: 'from multiprocessing.resource_tracker
    # import main;main(9)'`. Measured on the built CLI: every run of the
    # embedding detector (`scan --detector embedding`, `compare`) printed an
    # argparse error and `resource_tracker: process died unexpectedly, some
    # resources might leak` - the scan finished, and it leaked a semaphore
    # and shouted about it each time. `freeze_support` is what turns that
    # re-execution back into a child process; it does nothing when the code
    # is not frozen, which is why it can sit here unconditionally.
    import multiprocessing

    multiprocessing.freeze_support()
    _warn_if_stale()
    as_cli = _invoked_as_cli()

    if not as_cli and sys.argv[1:2] == ["--install-cli"]:
        return _install_cli()

    if as_cli:
        # No subcommand → interactive TUI
        if len(sys.argv) == 1:
            from tui.app import run_tui
            return run_tui()
        import cli
        return cli.main(sys.argv[1:])

    import main as gui_main
    return gui_main.main()


if __name__ == "__main__":
    sys.exit(run())
