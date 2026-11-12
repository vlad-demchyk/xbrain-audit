"""Putting the frozen `xanalyze` command on the user's `PATH`.

Only meaningful for a packaged macOS build — running from source, `python
cli.py` already *is* the command. Modeled on VS Code's "Shell Command:
Install 'code' command in PATH": one button, one symlink, no installer
package.

There is only one frozen executable (`packaging/XAnalyze.spec` builds it
from `app_entry.py`, not `main.py`/`cli.py` directly) — the GUI and the CLI
are the same binary, told apart at runtime by the name it was invoked as
(see `app_entry.py`). So "installing the CLI" is just symlinking that one
executable under the name `app_entry.py` looks for, `xanalyze` — no second
copy, no separate build artifact.

Two things make macOS special here, both because the app ships unsigned (no
Developer ID yet — see `manual-todo.md`):

* A `.dmg` download tags every file it contains with the `com.apple.quarantine`
  extended attribute. Approving the GUI once (right-click -> Open) only
  clears Gatekeeper's opinion of *that* invocation; running the same binary
  directly from a terminal afterward, under the new name, can still hit its
  own "unidentified developer" refusal unless the attribute is stripped
  explicitly — see `_clear_quarantine`.
* There is no postinstall hook to do this automatically (a plain drag-to-
  Applications `.dmg` has no script step), so it has to be a deliberate,
  user-triggered action — the button this module backs.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

#: The name the symlink is installed under, and what `app_entry.py` checks
#: `sys.argv[0]` against to decide it should run the CLI, not the GUI.
CLI_NAME = "xanalyze"

#: Default install location: writable without a password prompt, and on
#: `PATH` for most modern shell setups (though not universally — see
#: `is_dir_on_path`, which callers use to warn honestly rather than assume).
USER_BIN_DIR = Path.home() / ".local" / "bin"

#: The traditional system-wide alternative (same directory Homebrew's
#: Intel-Mac installs use), for someone who wants every shell and every
#: user on the machine to see the command. Writing here needs elevation.
SYSTEM_BIN_DIR = Path("/usr/local/bin")


class CliInstallError(RuntimeError):
    """Something in the install/uninstall path failed. The message is
    written to be shown to the user as-is."""


def bundled_cli_path() -> Path | None:
    """The running executable's own path, when frozen — the same file the
    CLI symlink should point at (see the module docstring). `None` when not
    running frozen (a `python main.py` dev run has nothing to symlink; the
    CLI is just `python cli.py` directly)."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve()


def is_dir_on_path(directory: Path) -> bool:
    """Whether `directory` appears in the current process's `PATH` — used
    only to decide what to tell the user, never to change behaviour: the
    symlink is written either way, since a shell started after this call
    (a fresh Terminal tab, tomorrow) may pick up a `PATH` this process
    never saw, e.g. one set in a shell rc file that only takes effect for
    new shells."""
    parts = os.environ.get("PATH", "").split(os.pathsep)
    target = str(directory)
    return any(Path(p) == directory or p == target for p in parts if p)


def _clear_quarantine(path: Path) -> None:
    """Strip `com.apple.quarantine` from `path`, if present.

    `xattr -d` exits non-zero when the attribute is simply absent (e.g. a
    build made locally rather than downloaded) — that case is not an error
    and must not be surfaced as one; any other failure is real and should
    stop the install rather than leave a binary Gatekeeper will still block.

    Off macOS there is no quarantine flag and no `xattr`, so there is
    nothing to strip and the call is skipped rather than attempted.
    Measured 2026-09-02 on Linux CI: `subprocess.run(["xattr", ...])` raised
    `FileNotFoundError` and took the whole install down with it. The check is
    on the platform and not on the tool being findable, because on macOS
    `xattr` is part of the system - a silent skip there would leave a binary
    Gatekeeper still blocks, which is the one outcome this function exists
    to prevent.
    """
    if sys.platform != "darwin":
        return
    result = subprocess.run(
        ["xattr", "-d", "com.apple.quarantine", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and "No such xattr" not in (result.stderr or ""):
        raise CliInstallError(
            f"could not clear the quarantine flag on {path}: {result.stderr.strip()}")


def _run_admin(shell_command: str) -> None:
    """Run `shell_command` elevated via the same one-dialog-password pattern
    Homebrew uses for `/usr/local` — no code signing involved, just the
    standard macOS privilege-escalation prompt."""
    escaped = shell_command.replace("\\", "\\\\").replace('"', '\\"')
    result = subprocess.run(
        ["osascript", "-e", f'do shell script "{escaped}" with administrator privileges'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise CliInstallError(result.stderr.strip() or "the administrator prompt was cancelled")


def install(source: Path | None = None, link_dir: Path = USER_BIN_DIR,
           use_admin: bool = False) -> Path:
    """Symlink `link_dir/xanalyze` -> `source` (default: the bundled CLI
    next to this executable), clearing quarantine on `source` first.

    Raises `CliInstallError` (never silently leaves a half-done state) when
    there is no bundled CLI to link (dev run), the source is missing, or the
    filesystem operation itself fails.
    """
    if sys.platform == "win32":
        # A symlink on Windows needs Developer Mode or an administrator, and
        # the Windows build does not need one: it ships the command as its
        # own console executable (`packaging/XAnalyze-windows.spec`).
        raise CliInstallError(
            "on Windows the command is xanalyze-cli.exe in the XAnalyze "
            "folder: add that folder to PATH to run it from any terminal")
    if source is None:
        source = bundled_cli_path()
    if source is None:
        raise CliInstallError(
            "no bundled CLI found — this only applies to the packaged app")
    if not source.exists():
        raise CliInstallError(f"CLI executable not found at {source}")

    source = source.absolute()
    link_dir = link_dir.absolute()
    if any(ord(c) < 32 or ord(c) == 127 for c in str(source) + str(link_dir)):
        raise CliInstallError("control characters are not allowed in installation paths")

    _clear_quarantine(source)
    target = link_dir / CLI_NAME

    if use_admin:
        _run_admin(f"/bin/mkdir -p {shlex.quote(str(link_dir))} && "
                   f"/bin/ln -sfh {shlex.quote(str(source))} {shlex.quote(str(target))}")
    else:
        try:
            link_dir.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or target.exists():
                target.unlink()
            os.symlink(source, target)
        except OSError as exc:
            raise CliInstallError(f"could not create {target}: {exc}") from exc
    return target


def uninstall(link_dir: Path = USER_BIN_DIR, use_admin: bool = False) -> bool:
    """Remove `link_dir/xanalyze` if it is there. Returns whether anything
    was actually removed, so a caller can tell "already gone" from "just
    removed it" without a second existence check."""
    target = link_dir.absolute() / CLI_NAME
    if any(ord(c) < 32 or ord(c) == 127 for c in str(target)):
        raise CliInstallError("control characters are not allowed in installation paths")
    if not target.is_symlink() and not target.exists():
        return False
    if use_admin:
        _run_admin(f"/bin/rm -f {shlex.quote(str(target))}")
    else:
        try:
            target.unlink()
        except OSError as exc:
            raise CliInstallError(f"could not remove {target}: {exc}") from exc
    return True


def installed_target(link_dir: Path = USER_BIN_DIR) -> Path | None:
    """The symlink's current target, or `None` if nothing is installed at
    `link_dir` — used by the UI to show an accurate install/not-installed
    state instead of assuming."""
    target = link_dir / CLI_NAME
    if target.is_symlink():
        return Path(os.readlink(target))
    return None


def offer_is_due(already_offered: bool,
                 link_dir: Path = USER_BIN_DIR) -> bool:
    """Whether the packaged app should offer to install the command itself.

    The button in Settings was the only way in, and a command nobody finds
    is a command nobody has: the frozen binary already *is* the CLI and the
    TUI, and the only thing between the user and both of them is a symlink
    they have to go looking for.

    Three conditions, and each one is a refusal to nag:

    * `already_offered` - asked once, ever. The answer "no" is an answer,
      and asking again on the next launch would make it a nag.
    * `bundled_cli_path()` - a dev run has nothing to link (`python cli.py`
      is the command already), so there is nothing to ask about.
    * `installed_target()` - somebody who already pressed the button, or who
      linked the binary by hand, gets no dialog at all.

    A pure function of those three so the decision can be tested without a
    QApplication; the dialog it gates lives in `main.py`.
    """
    if already_offered:
        return False
    # Nothing to link on Windows: see `install`.
    if sys.platform == "win32":
        return False
    if bundled_cli_path() is None:
        return False
    return installed_target(link_dir) is None
