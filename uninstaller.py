"""Removing XAnalyze from this machine.

The counterpart of `updater.py`: where update replaces the binary with a
newer one, uninstall removes everything the app ever put outside its own
directory. One implementation here; the CLI command and the TUI screen are
thin frontends over `enumerate_items` / `remove_item`.

What counts as "the app":
  * the PATH symlink(s) (`~/.local/bin/xanalyze`, `/usr/local/bin/xanalyze`)
  * the GUI bundle (/Applications/XAnalyze.app), when present
  * the config dir (~/.config/xanalyze) — settings and the scan cache
  * the pre-rename config dir (~/.config/ai-content-scanner)
  * keychain entries under both service names, for every account key the
    app has ever used

What deliberately stays:
  * `.xanalyze/` run-history folders inside scanned projects — they live in
    the user's repositories, next to their files
  * reports already written to ~/Documents/XAnalyze — user data, not app state
  * `.xanalyze-ignore` files and `.bak` backups inside repositories

Both lists are shown to the user before anything is removed.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

#: Every secret key the app has ever saved, under either service name.
_KNOWN_SECRET_KEYS = (
    "xformat_access_token",
    "xformat_refresh_token",
    "xformat_account_email",
    "anthropic_api_key",
)

_SERVICE_NAME = "xanalyze"
_OLD_SERVICE_NAME = "ai-content-scanner"


@dataclass
class UninstallItem:
    """One thing uninstall can remove (or report on)."""

    key: str
    label: str
    kind: str                    # symlink | bundle | dir | keychain | note
    path: Path | None = None     # None for keychain entries
    service: str | None = None   # keychain service name
    account: str | None = None   # keychain account name
    exists: bool = True
    error: str | None = field(default=None, repr=False)


def _config_base() -> Path:
    import platform_dirs

    return platform_dirs.config_home()


def _keychain_has(service: str, account: str) -> bool:
    try:
        import keyring
        value = keyring.get_password(service, account)
    except Exception:  # noqa: BLE001 - locked/unavailable keychain: nothing to remove
        return False
    return value is not None


def enumerate_items() -> list[UninstallItem]:
    """Everything uninstall would touch, in removal order."""
    items: list[UninstallItem] = []

    for link_dir in (Path.home() / ".local" / "bin", Path("/usr/local/bin")):
        target = link_dir / "xanalyze"
        items.append(UninstallItem(
            key=f"symlink:{link_dir}", kind="symlink", path=target,
            label=f"{target} (command on PATH)",
            exists=target.is_symlink() or target.exists(),
        ))

    app = Path("/Applications/XAnalyze.app")
    items.append(UninstallItem(
        key="app", kind="bundle", path=app,
        label=f"{app} (application)", exists=app.exists(),
    ))

    config_dir = _config_base() / _SERVICE_NAME
    items.append(UninstallItem(
        key="config", kind="dir", path=config_dir,
        label=f"{config_dir} (settings, scan cache)",
        exists=config_dir.exists(),
    ))

    legacy_dir = _config_base() / _OLD_SERVICE_NAME
    items.append(UninstallItem(
        key="legacy-config", kind="dir", path=legacy_dir,
        label=f"{legacy_dir} (pre-rename settings)", exists=legacy_dir.exists(),
    ))

    for service in (_SERVICE_NAME, _OLD_SERVICE_NAME):
        for account in _KNOWN_SECRET_KEYS:
            if _keychain_has(service, account):
                items.append(UninstallItem(
                    key=f"keychain:{service}:{account}", kind="keychain",
                    label=f"keychain: {service} / {account}",
                    service=service, account=account,
                ))
    return items


def display_item(item: UninstallItem, lang: str = "en") -> str:
    """A translated label for an uninstall item, with its path intact."""
    from i18n.translations import t

    path = str(item.path) if item.path is not None else ""
    if item.kind == "symlink":
        return t("tui_uninstall_item_command", lang, path=path)
    if item.kind == "bundle":
        return t("tui_uninstall_item_app", lang, path=path)
    if item.key == "config":
        return t("tui_uninstall_item_config", lang, path=path)
    if item.key == "legacy-config":
        return t("tui_uninstall_item_legacy_config", lang, path=path)
    if item.kind == "keychain":
        return t("tui_uninstall_item_keychain", lang, service=item.service,
                 account=item.account)
    return item.label


def remaining_notes(lang: str | None = None) -> list[str]:
    """Things uninstall does not remove, so the summary says so plainly."""
    notes = []
    # The archive of run folders, wherever it currently is. `migrate=False`:
    # this function describes what will be left behind and must not move
    # anything while doing it.
    from cli_impl import runfolder

    root = runfolder.default_root(migrate=False)
    if root.is_dir():
        runs = [p for p in root.iterdir() if p.is_dir()]
        if lang is None:
            notes.append(f"{len(runs)} report folder(s) left in {root}")
        else:
            from i18n.translations import t

            notes.append(t("tui_uninstall_reports_left", lang,
                           n=len(runs), path=str(root)))
    # Loose files from before run folders existed. Still named, because they
    # are still on people's Desktops.
    desktop = Path.home() / "Desktop"
    desktop_reports = [p for pattern in ("xanalyze-*.pdf", "xanalyze-*.html",
                                         "xanalyze-*.md")
                       for p in desktop.glob(pattern)]
    if desktop_reports:
        if lang is None:
            notes.append(f"{len(desktop_reports)} older report(s) left on ~/Desktop")
        else:
            from i18n.translations import t

            notes.append(t("tui_uninstall_old_reports_left", lang,
                           n=len(desktop_reports)))
    if lang is None:
        notes.append(".xanalyze/ history folders and .xanalyze-ignore files "
                     "inside your repositories are left untouched")
    else:
        from i18n.translations import t

        notes.append(t("tui_uninstall_history_kept", lang))
    return notes


def remove_item(item: UninstallItem) -> UninstallItem:
    """Remove one item in place; on failure records `item.error`."""
    try:
        if item.kind == "keychain":
            import keyring
            keyring.delete_password(item.service, item.account)
        elif item.kind == "symlink":
            item.path.unlink()
        elif item.kind == "bundle":
            # The bundle may be owned by an admin drag-install; a plain rmtree
            # is tried first and the error surfaces honestly if it cannot.
            shutil.rmtree(item.path)
        elif item.kind == "dir":
            shutil.rmtree(item.path)
    except Exception as exc:  # noqa: BLE001 - each failure removes the rest anyway
        item.error = str(exc)
    return item


def remove_all(items: list[UninstallItem]) -> tuple[list[UninstallItem], list[str]]:
    """Remove every existing item; returns (removed, errors)."""
    removed: list[UninstallItem] = []
    errors: list[str] = []
    for item in items:
        if not item.exists:
            continue
        remove_item(item)
        if item.error:
            errors.append(f"{item.label}: {item.error}")
        else:
            removed.append(item)
    return removed, errors
