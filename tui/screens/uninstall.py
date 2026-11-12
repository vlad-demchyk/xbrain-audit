"""Uninstall screen — remove XBrain Audit from this machine."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label, Static

import uninstaller

from tui.screens.base import XScreen


class UninstallScreen(XScreen):
    """List what is installed and remove it after an explicit confirm."""

    BINDINGS = [
        ("escape", "back", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._armed = False

    def compose(self) -> ComposeResult:
        yield from self.compose_chrome()
        with Vertical(id="uninstall-view"):
            yield Label(self.tr("tui_uninstall_title"), classes="menu-title")
            yield Static("")
            yield Label("", id="uninstall-list")
            yield Static("")
            yield Button(self.tr("tui_uninstall_remove"), id="remove", variant="error")
            yield Static("")
            yield Label("", id="uninstall-status")
            yield Static("")
            yield Button(self.tr("tui_back"), id="back")

    def on_screen_resume(self) -> None:
        self._armed = False
        items = [i for i in uninstaller.enumerate_items() if i.exists]
        listing = self.query_one("#uninstall-list", Label)
        if items:
            listing.update("\n".join(
                f"• {uninstaller.display_item(i, self.lang)}" for i in items))
        else:
            listing.update(self.tr("tui_uninstall_none"))
        self.query_one("#remove", Button).display = bool(items)
        status = self.query_one("#uninstall-status", Label)
        status.update("")
        notes = uninstaller.remaining_notes(self.lang)
        if notes:
            status.update(self.tr("tui_uninstall_kept", what="; ".join(notes)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_back()
        elif event.button.id == "remove":
            self._remove()

    def _remove(self) -> None:
        status = self.query_one("#uninstall-status", Label)
        button = self.query_one("#remove", Button)
        if not self._armed:
            # Two presses rather than one: a destructive action behind a
            # single mis-click is how "I didn't mean to" stories start.
            self._armed = True
            button.label = self.tr("tui_uninstall_confirm")
            return
        items = uninstaller.enumerate_items()
        removed, _errors = uninstaller.remove_all(items)
        self._armed = False
        button.label = self.tr("tui_uninstall_remove")
        button.display = False
        listing = self.query_one("#uninstall-list", Label)
        listing.update(self.tr("tui_uninstall_none"))
        failures = [f"{uninstaller.display_item(item, self.lang)}: {item.error}"
                    for item in items if item.error]
        if failures:
            status.update(self.tr("tui_uninstall_errors",
                                  what="; ".join(failures)))
        else:
            status.update(self.tr("tui_uninstall_done", n=len(removed)))
