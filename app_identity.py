"""What this product is called, and what it was called before.

XAnalyze became XBrain Audit in 0.74.0. A rename is a dozen names changing
at once - the window title, the command, the data folders, the environment
variables, the per-project files - and every one of them is also a promise
an existing install relies on. This module owns both halves: the current
names, and each old name that is still honoured, with the rule for it. A
second copy of either anywhere else is how one site forgets the fallback.

What still works under the old name, and where that is decided:

* the `xanalyze` command - `app_entry` accepts it, `cli_install` links it
  next to `xaudit`, the uninstaller removes both;
* `XANALYZE_*` variables - `env()` reads `XAUDIT_*` first, then the old one;
* `~/.xanalyze`, `<config home>/xanalyze`, `~/Documents/XAnalyze` - moved
  once by `migrate_legacy_data()`, which every entry point calls first; while
  a move has not happened (or failed) `current_or_legacy()` keeps answering
  with the old folder, so nothing is split between two places;
* `.xanalyze-ignore` and `.xanalyze/` inside a project - read when the new
  name is absent, and written to when only the old one exists, so a
  person's repository is not churned by an upgrade;
* the keychain service `xanalyze` - `llm.credentials` reads it and copies the
  item to the new service.

Standard library only: `config`, `applog`, `platform_dirs` users and the
uninstaller import this, and none of them may pull in anything heavier.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: The name a person reads: window titles, report footers, the README.
PRODUCT_NAME = "XBrain Audit"
LEGACY_PRODUCT_NAME = "XAnalyze"

#: The machine name: the config folder, the keychain service, the log folder.
APP_SLUG = "xbrain-audit"
LEGACY_APP_SLUG = "xanalyze"

#: The command on PATH. The old one stays installed as an alias.
CLI_NAME = "xaudit"
LEGACY_CLI_NAME = "xanalyze"

#: Environment variables are `XAUDIT_<NAME>`; `XANALYZE_<NAME>` still counts.
ENV_PREFIX = "XAUDIT_"
LEGACY_ENV_PREFIX = "XANALYZE_"

#: The per-user data folder in the home directory: run history and caches.
DATA_DIR_NAME = ".xbrain-audit"
LEGACY_DATA_DIR_NAME = ".xanalyze"

#: The folder run documents go in, under Documents.
REPORTS_FOLDER = "XBrain Audit"
LEGACY_REPORTS_FOLDER = "XAnalyze"

#: Files a project keeps about itself.
PROJECT_IGNORE_FILE = ".xaudit-ignore"
LEGACY_PROJECT_IGNORE_FILE = ".xanalyze-ignore"
PROJECT_HISTORY_DIR = ".xaudit"
LEGACY_PROJECT_HISTORY_DIR = ".xanalyze"

#: Set (to anything) and `migrate_legacy_data()` with no explicit paths does
#: nothing. The test suite sets it: tests run under the developer's real
#: home, and a test that starts the CLI must not move the developer's data.
SKIP_MIGRATION_ENV = "XAUDIT_NO_DATA_MIGRATION"


# ------------------------------------------------------------ environment

def env_name(name: str) -> str:
    """`env_name("LOG_DIR")` -> `"XAUDIT_LOG_DIR"`, the name to document."""
    return ENV_PREFIX + name


def env(name: str, default: str | None = None) -> str | None:
    """`$XAUDIT_<name>`, else `$XANALYZE_<name>`, else `default`.

    "Set" means present, not non-empty: an empty `XAUDIT_DESKTOP_CSS` is a
    deliberate "no overlay", and it must win over an old variable rather
    than fall through to it.
    """
    for prefix in (ENV_PREFIX, LEGACY_ENV_PREFIX):
        value = os.environ.get(prefix + name)
        if value is not None:
            return value
    return default


# ------------------------------------------------------------ locations

def current_or_legacy(new: Path, old: Path) -> Path:
    """The new path, unless only the old one exists.

    One rule for every renamed location. Before the move (or after a move
    that failed) the old folder is the one holding the data, so reading and
    writing both go there instead of starting an empty second copy beside
    it. Once the new one exists it wins, and the old one is ignored.
    """
    if not new.exists() and old.exists():
        return old
    return new


def _home(home: Path | None) -> Path:
    return Path(home) if home is not None else Path.home()


def data_home(home: Path | None = None) -> Path:
    """`~/.xbrain-audit`, or `~/.xanalyze` while that is still the only one."""
    base = _home(home)
    return current_or_legacy(base / DATA_DIR_NAME, base / LEGACY_DATA_DIR_NAME)


def app_dir(base: Path) -> Path:
    """`<base>/xbrain-audit`, or `<base>/xanalyze` while only that exists.

    `base` is a platform folder: the config home, the state home.
    """
    base = Path(base)
    return current_or_legacy(base / APP_SLUG, base / LEGACY_APP_SLUG)


def documents_dir(home: Path | None = None) -> Path:
    """Documents, or the home folder when there is no Documents.

    A machine without `~/Documents` - a container, a server - must still get
    its documents somewhere findable rather than an error.
    """
    base = _home(home)
    documents = base / "Documents"
    return documents if documents.is_dir() else base


def reports_root(home: Path | None = None) -> Path:
    """`~/Documents/XBrain Audit`, or the old `XAnalyze` while only it exists."""
    documents = documents_dir(home)
    return current_or_legacy(documents / REPORTS_FOLDER,
                             documents / LEGACY_REPORTS_FOLDER)


def project_ignore_file(folder: Path) -> Path:
    """The ignore file of a project: `.xaudit-ignore`, or the old one.

    For reading and for writing alike: a project that committed
    `.xanalyze-ignore` keeps getting its edits there, because renaming a
    file in somebody's repository is their decision, not an upgrade's.
    """
    folder = Path(folder)
    return current_or_legacy(folder / PROJECT_IGNORE_FILE,
                             folder / LEGACY_PROJECT_IGNORE_FILE)


def project_history_dir(folder: Path) -> Path:
    """A project's `.xaudit/` history folder, or the old `.xanalyze/`."""
    folder = Path(folder)
    return current_or_legacy(folder / PROJECT_HISTORY_DIR,
                             folder / LEGACY_PROJECT_HISTORY_DIR)


# ------------------------------------------------------------ migration

@dataclass(frozen=True)
class Move:
    """One renamed folder and what happened to it."""

    old: Path
    new: Path
    #: `moved`, `failed`, or `skipped` (nothing to move, or already moved).
    outcome: str
    reason: str = ""


def legacy_locations(home: Path | None = None,
                     config_bases: tuple[Path, ...] | None = None,
                     state_base: Path | None = None) -> list[tuple[Path, Path]]:
    """Every `(old, new)` folder pair the rename moves."""
    import platform_dirs

    base = _home(home)
    if config_bases is None:
        config_bases = (platform_dirs.config_home(),
                        platform_dirs.default_config_home())
    if state_base is None:
        state_base = platform_dirs.state_home()
    pairs = [(base / LEGACY_DATA_DIR_NAME, base / DATA_DIR_NAME)]
    seen: set[Path] = set()
    for config_base in (*config_bases, state_base):
        config_base = Path(config_base)
        if config_base in seen:
            continue
        seen.add(config_base)
        pairs.append((config_base / LEGACY_APP_SLUG, config_base / APP_SLUG))
    documents = documents_dir(home)
    pairs.append((documents / LEGACY_REPORTS_FOLDER, documents / REPORTS_FOLDER))
    return pairs


def migrate_legacy_data(home: Path | None = None,
                        config_bases: tuple[Path, ...] | None = None,
                        state_base: Path | None = None) -> list[Move]:
    """Move each pre-rename folder to its new name, once.

    Called first thing by every entry point (window, command line, terminal
    interface). A folder is moved only when the new one is absent and the
    old one exists, with one `os.rename`: never merged, never copied, never
    deleted. If the rename fails - another volume, a locked folder, a sync
    client holding it - the old folder stays where it is, `current_or_legacy`
    keeps pointing at it, and the reason goes to the log.

    With no explicit paths and `$XAUDIT_NO_DATA_MIGRATION` set, nothing
    happens: that is how the test suite keeps the developer's home intact.
    """
    explicit = home is not None or config_bases is not None or state_base is not None
    if not explicit and os.environ.get(SKIP_MIGRATION_ENV):
        return []
    try:
        pairs = legacy_locations(home, config_bases, state_base)
    except Exception:  # noqa: BLE001 - a broken home must not stop the app
        return []
    moves: list[Move] = []
    for old, new in pairs:
        try:
            if new.exists() or not old.is_dir() or old.is_symlink():
                moves.append(Move(old, new, "skipped"))
                continue
            os.rename(old, new)
        except OSError as exc:
            moves.append(Move(old, new, "failed", str(exc)))
            continue
        moves.append(Move(old, new, "moved"))
    _log(moves)
    return moves


def _log(moves: list[Move]) -> None:
    """Say what moved and what could not, in the app's own log."""
    try:
        import applog
    except Exception:  # noqa: BLE001 - logging must not break startup
        return
    for move in moves:
        if move.outcome == "moved":
            applog.info("rename-migration", old=str(move.old), new=str(move.new))
        elif move.outcome == "failed":
            applog.warning("rename-migration-failed", old=str(move.old),
                           new=str(move.new), reason=move.reason,
                           using=str(move.old))
