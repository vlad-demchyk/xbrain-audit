"""Where per-user files live on this operating system.

One place for the answer, because five modules computed it on their own as
`$XDG_CONFIG_HOME or ~/.config`. That is right on macOS and Linux and wrong on
Windows, where nothing else keeps settings in `C:\\Users\\<name>\\.config` and
a person looking for them, or a backup tool, looks in `%APPDATA%`.

`XDG_CONFIG_HOME` / `XDG_STATE_HOME` still win on every platform when set:
the test suite isolates a whole process through `XDG_CONFIG_HOME`
(`tests/conftest.py`), and that must keep working on Windows too.

Standard library only: `config`, `llm.credentials`, `applog` and the
uninstaller import this, and none of them may pull in anything heavier.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _windows_dir(variable: str, fallback: tuple[str, ...]) -> Path:
    value = os.environ.get(variable)
    return Path(value) if value else Path.home().joinpath(*fallback)


def default_config_home() -> Path:
    """The platform's own config base, ignoring `XDG_CONFIG_HOME`."""
    if sys.platform == "win32":
        return _windows_dir("APPDATA", ("AppData", "Roaming"))
    return Path.home() / ".config"


def config_home() -> Path:
    """The base directory settings, credentials and sessions go under."""
    override = os.environ.get("XDG_CONFIG_HOME")
    return Path(override) if override else default_config_home()


def state_home() -> Path:
    """The base directory for state that is not configuration (logs)."""
    override = os.environ.get("XDG_STATE_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return _windows_dir("LOCALAPPDATA", ("AppData", "Local"))
    return Path.home() / ".local" / "state"
