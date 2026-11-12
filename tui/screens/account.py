"""Sign in to the account that pays for AI calls.

Settings has always let a person choose `xformat` as the provider, and the
TUI had no way to sign in to it - so choosing it and having no session was
reachable from here and only fixable from the window or from
`xaudit ai login`. A setting whose one prerequisite lives on another
surface is a setting that lies about what it does.

The password is never stored, here or anywhere: `sign_in` exchanges it for a
token that goes to the OS keychain, and the field is cleared before the
result is even looked at. That is the same contract `ui/sign_in_dialog.py`
and `cli_impl.aicmds.cmd_ai_login` keep, and it is why this screen exists
while an API-key field still deliberately does not - a key is a secret that
would have to be *kept*, and a password here is one that is spent.

The call is made off the UI thread. A sign-in on a captive network is thirty
seconds of a frozen interface otherwise, which is the same reason
`UpdateScreen` threads its own network call.
"""
from __future__ import annotations

import threading

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

import config

from tui.screens.base import XScreen

#: The only provider with credentials to take. Claude Code owns its own
#: sign-in and Anthropic takes a key, so for those this screen says where to
#: go rather than pretending to a flow it does not have - the same three-way
#: answer `xaudit ai login` gives.
SIGNS_IN = "xformat"


class AccountScreen(XScreen):
    """Who is signed in, and the two buttons that change it."""

    AUTO_FOCUS = ""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("ctrl+r", "refresh", "Refresh"),
        # Enter signs in from either field, which is what every sign-in form
        # anywhere does. Without it the only way in was a mouse.
        ("enter", "sign_in", "Sign in"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._busy = False

    def compose(self) -> ComposeResult:
        yield from self.compose_chrome()
        with Vertical(id="account-view"):
            yield Label(self.tr("tui_account_title"), classes="menu-title")
            yield Static("")
            yield Label("", id="account-state")
            yield Static("")
            yield Label(self.tr("tui_account_email"))
            yield Input(placeholder=self.tr("tui_account_email_placeholder"),
                        id="account-email")
            yield Label(self.tr("tui_account_password"))
            yield Input(password=True, id="account-password")
            yield Static("")
            with Horizontal():
                yield Button(self.tr("settings_sign_in"), id="sign-in",
                             variant="primary")
                yield Button(self.tr("tui_account_sign_out"), id="sign-out")
                # Shown only while another provider is the one that pays.
                # Offered *after* a sign-in rather than demanded before one.
                yield Button(self.tr("tui_account_use_xformat"),
                             id="use-xformat")
                yield Button(self.tr("tui_back"), id="back")
            yield Static("")
            yield Label("", id="account-status")
            yield Label(self.tr("tui_account_privacy"), classes="hint")

    def on_mount(self) -> None:
        self.action_refresh()

    def on_screen_resume(self) -> None:
        self.action_refresh()

    # ------------------------------------------------------------- state
    def _provider(self):
        from llm.base import LLMProviderFactory

        settings = config.Settings.load()
        return LLMProviderFactory.create(
            SIGNS_IN, base_url=settings.xformat_base_url,
            endpoints=settings.xformat_endpoints,
        ), settings

    def action_refresh(self) -> None:
        """Say who is signed in, and never stand in the way of signing in.

        This used to disable both fields and the button whenever the chosen
        provider was not xFormat - which is the default - so a fresh install
        could not sign in from here at all. The reasoning was that a screen
        reporting the xFormat session while the run pays through Claude Code
        answers a question nobody asked; the effect was a circular
        dependency, because choosing xFormat in Settings before having an
        account is exactly backwards.

        So the state line still says which provider pays, and the form stays
        usable. Signing in while another provider is selected offers to
        switch - after the sign-in worked, when there is something to switch
        to.
        """
        settings = config.Settings.load()
        state = self.query_one("#account-state", Label)
        elsewhere = settings.llm_provider != SIGNS_IN
        self.query_one("#use-xformat", Button).display = elsewhere
        self._enable(True)
        if elsewhere:
            state.update(self.tr(f"tui_account_elsewhere_{settings.llm_provider}")
                         if settings.llm_provider in ("anthropic", "claude-code")
                         else self.tr("tui_account_not_xformat"))
            return
        try:
            provider, _settings = self._provider()
            status = provider.auth_status()
        except Exception as exc:  # noqa: BLE001 - shown, never swallowed
            state.update(self.tr("tui_account_unknown", detail=str(exc)))
            return
        if status.signed_in:
            state.update(self.tr("tui_account_signed_in",
                                 email=status.email or "?"))
        else:
            state.update(self.tr("tui_account_signed_out"))

    def _enable(self, enabled: bool) -> None:
        for widget_id in ("sign-in", "sign-out"):
            self.query_one(f"#{widget_id}", Button).disabled = not enabled
        for widget_id in ("account-email", "account-password"):
            self.query_one(f"#{widget_id}", Input).disabled = not enabled

    def _status(self, text: str) -> None:
        self.query_one("#account-status", Label).update(text)

    # ------------------------------------------------------------ actions
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_back()
        elif event.button.id == "sign-in":
            self._sign_in()
        elif event.button.id == "sign-out":
            self._sign_out()
        elif event.button.id == "use-xformat":
            self._use_xformat()

    def action_sign_in(self) -> None:
        """Enter, from anywhere on the screen."""
        self._sign_in()

    def _sign_in(self) -> None:
        if self._busy:
            return
        email = self.query_one("#account-email", Input).value.strip()
        password_field = self.query_one("#account-password", Input)
        password = password_field.value
        if not email or not password:
            self._status(self.tr("settings_need_credentials"))
            return
        # Cleared here, before the call: whatever happens next, it is not
        # sitting in a widget waiting to be read off a shared screen.
        password_field.value = ""
        self._busy = True
        self._status(self.tr("tui_account_working"))

        def work() -> None:
            try:
                provider, _settings = self._provider()
                status = provider.sign_in(email, password)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                self.app.call_from_thread(self._done, None, str(exc))
                return
            self.app.call_from_thread(self._done, status, "")

        threading.Thread(target=work, daemon=True).start()

    def _use_xformat(self) -> None:
        """Make xFormat the provider that pays for AI calls.

        A separate press, and only offered when another provider is selected:
        signing in and changing who pays are two decisions, and doing the
        second silently as part of the first is how a person ends up billed
        somewhere they did not choose.
        """
        settings = config.Settings.load()
        settings.llm_provider = SIGNS_IN
        settings.save()
        self._status(self.tr("tui_account_now_xformat"))
        self.action_refresh()

    def _sign_out(self) -> None:
        try:
            provider, _settings = self._provider()
            provider.sign_out()
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self._status(str(exc))
            return
        self._status(self.tr("tui_account_signed_out"))
        self.action_refresh()

    def _done(self, status, error: str) -> None:
        self._busy = False
        if error:
            self._status(error)
        elif status is not None and not status.signed_in:
            self._status(self.tr("settings_not_signed_in",
                                 detail=status.detail))
        else:
            settings = config.Settings.load()
            self._status(self.tr("tui_account_welcome")
                         if settings.llm_provider == SIGNS_IN
                         else self.tr("tui_account_welcome_switch"))
        self.action_refresh()
