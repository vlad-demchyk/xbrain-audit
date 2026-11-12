"""The `uninstall` command: remove XBrain Audit from this machine."""
from __future__ import annotations

import sys

from cli_impl import EXIT_ERROR, EXIT_OK


def _confirm(items) -> bool:
    """The yes/no prompt shared by the interactive path."""
    try:
        answer = input(f"Remove these {sum(1 for i in items if i.exists)} item(s)? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def cmd_uninstall(args) -> int:
    """Remove everything XBrain Audit put on this machine.

    Lists what was found (PATH symlinks, the application bundle, the config
    directory, keychain entries), asks for confirmation, then removes it.
    Repository files (.xaudit-ignore, .bak backups, run history inside
    scanned projects) and reports in ~/Documents/XBrain Audit are never touched.

    With --dry-run: only list. With --yes: skip the confirmation.
    """
    import uninstaller

    items = uninstaller.enumerate_items()
    present = [i for i in items if i.exists]

    if not present:
        print("XBrain Audit is not installed - nothing to remove.")
        for note in uninstaller.remaining_notes():
            print(f"note: {note}")
        return EXIT_OK

    print("Found:")
    for item in present:
        print(f"  - {item.label}")

    if getattr(args, "dry_run", False):
        print("dry run: nothing removed.")
        return EXIT_OK

    if not getattr(args, "yes", False) and not _confirm(present):
        print("Cancelled - nothing removed.")
        return EXIT_OK

    removed, errors = uninstaller.remove_all(items)
    for item in removed:
        print(f"removed: {item.label}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)

    for note in uninstaller.remaining_notes():
        print(f"note: {note}")

    if errors:
        print(f"Done with {len(errors)} error(s).", file=sys.stderr)
        return EXIT_ERROR
    print(f"Uninstalled ({len(removed)} item(s)).")
    return EXIT_OK
