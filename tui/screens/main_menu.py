"""Main menu screen — navigation hub."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Button, Label, Static

import config

from tui.screens.base import XScreen

#: Menu entries: shortcut key, screen name, label. One list rather than a
#: block of `elif`s plus a matching block of `action_*` methods, which had
#: already drifted once (the README documented shortcuts 1-6 while the menu
#: had seven).
#:
#: Logs is 8 rather than 5, which would read better. The numbers 1-7 are
#: documented, are in muscle memory and are what the tests press: a new entry
#: that renumbers the existing ones makes every one of those wrong, and a
#: menu shortcut is a promise as much as a label.
MENU = (
    ("1", "scan"), ("2", "audit"), ("3", "fullscan"), ("4", "reports"),
    ("5", "settings"), ("6", "update"), ("7", "uninstall"), ("8", "logs"),
    # 9 for the same reason Logs is 8: the existing numbers are documented,
    # are in muscle memory and are what the tests press, so a new entry goes
    # on the end rather than renumbering seven promises.
    ("9", "account"),
)


class MainMenuScreen(XScreen):
    """Central menu with all major actions."""

    AUTO_FOCUS = "#scan"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ] + [Binding(key, f"go('{name}')", name, show=False)
         for key, name in MENU]

    def compose(self) -> ComposeResult:
        yield from self.compose_chrome()
        with Vertical(id="main-menu"):
            yield Label("XBrain Audit", classes="menu-title")
            yield Label(f"v{config.APP_VERSION}", id="version-hint")
            yield Static("")
            for key, name in MENU:
                yield Button(f"{key}  {self.tr('tui_menu_' + name)}",
                             id=name, classes="menu-item")
            yield Static("")
            yield Button(f"Q  {self.tr('tui_quit')}", id="quit",
                         classes="menu-item")
            yield Label(self.tr("tui_hint_move"), classes="hint")

    def action_go(self, name: str) -> None:
        self.app.push_screen(name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            self.app.exit()
        elif event.button.id in {name for _key, name in MENU}:
            self.app.push_screen(event.button.id)
