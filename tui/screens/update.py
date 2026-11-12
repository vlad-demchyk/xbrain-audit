"""Update screen — check for and install updates."""
from __future__ import annotations

import threading

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static

import config

from tui.screens.base import XScreen


class UpdateScreen(XScreen):
    """Check for updates and install them."""

    BINDINGS = [
        ("escape", "back", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._release = None
        self._busy = False
        self._install_armed = False
        self._run = None
        self._timer = None

    def action_back(self) -> None:
        if self._busy:
            return
        self._install_armed = False
        super().action_back()

    def compose(self) -> ComposeResult:
        yield from self.compose_chrome()
        with Vertical(id="update-view"):
            yield Label(self.tr("tui_update_title"), classes="menu-title")
            yield Static("")
            yield Label(self.tr("tui_update_current_version",
                                version=config.APP_VERSION))
            yield Static("")
            with Horizontal():
                yield Button(self.tr("tui_update_check"), id="check", variant="primary")
                yield Button(self.tr("tui_update_install"), id="install", disabled=True)
                yield Button(self.tr("tui_back"), id="back")
            yield Static("")
            yield Label("", id="update-status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_back()
        elif event.button.id == "check":
            self._check_update()
        elif event.button.id == "install":
            self._install()

    def _status(self, text: str) -> None:
        self.query_one("#update-status", Label).update(text)

    def _check_update(self) -> None:
        """Ask GitHub, off the UI thread.

        A network call on the UI thread froze the whole interface until it
        answered - or until it timed out, which on a captive network is
        thirty seconds of a dead screen.
        """
        if self._busy:
            return
        self._install_armed = False
        self._release = None
        button = self.query_one("#install", Button)
        button.disabled = True
        button.label = self.tr("tui_update_install")
        self._busy = True
        self._status(self.tr("tui_update_checking"))

        def work() -> None:
            import updater

            try:
                release = updater.fetch_latest()
            except Exception as exc:  # noqa: BLE001 - shown to the user
                self.app.call_from_thread(self._checked, None, str(exc))
                return
            self.app.call_from_thread(self._checked, release, "")

        threading.Thread(target=work, daemon=True).start()

    def _checked(self, release, error: str) -> None:
        import updater

        self._busy = False
        if error:
            self._status(self.tr("tui_update_check_failed", error=error))
            return
        self._release = release
        if updater.newer(release.version, config.APP_VERSION):
            self.query_one("#install", Button).disabled = False
            self._status(
                self.tr("tui_update_available", version=release.version)
                + f"\n{release.html_url}\n"
                + self.tr("tui_update_press_install"))
        else:
            self._status(self.tr("tui_update_current", version=config.APP_VERSION))

    def _install(self) -> None:
        """Install the release found by the check.

        Two presses, not one: this replaces the installed program, and the
        `Install` button only becomes pressable after a check has actually
        found something newer.
        """
        if self._busy or self._release is None:
            return
        button = self.query_one("#install", Button)
        if not self._install_armed:
            self._install_armed = True
            button.label = self.tr("tui_update_confirm_install")
            self._status(self.tr("tui_update_confirm"))
            return
        self._install_armed = False
        button.label = self.tr("tui_update_install")
        button.disabled = True
        self._busy = True
        self._status(self.tr("tui_update_installing"))

        # `do_update` is the same flow `xaudit update` runs: it checks,
        # downloads, and replaces the binary, reporting progress on stderr.
        # Driven through the shared runner so that progress reaches the
        # screen instead of the terminal underneath it.
        import argparse

        import updater

        from tui import runner

        try:
            self._run = runner.start(lambda _args: updater.do_update(),
                                     argparse.Namespace(),
                                     self.tr("tui_update_installing"))
        except runner.RunBusy as exc:
            # Replacing the binary under a scan that is still reading with it
            # is the one thing worse than waiting.
            button.disabled = False
            self._busy = False
            self._status(self.tr("tui_run_other_active",
                                 title=exc.active.title or "…"))
            return
        self._timer = self.set_interval(0.15, self._poll_install)

    def _poll_install(self) -> None:
        run = self._run
        if run is None:
            return
        for line in run.new_lines():
            self._status(line.lstrip("# ").strip() or line)
        if not run.running:
            self._timer.stop()
            self._timer = None
            self._run = None
            self._installed(run.result)

    def _installed(self, result) -> None:
        self._busy = False
        self._install_armed = False
        self._release = None
        if result.error:
            self._status(self.tr("tui_update_install_failed", error=result.error))
            return
        output = (result.stderr if result.exit_code else result.stdout) or result.stderr or result.stdout
        tail = [line for line in output
                .splitlines() if line.strip()]
        summary = tail[-1] if tail else ""
        if result.exit_code == 0:
            self._status(f"{summary}\n" + self.tr("tui_update_restart"))
        else:
            self._status(self.tr("tui_update_unfinished",
                                 code=result.exit_code) + f"\n{summary}")
