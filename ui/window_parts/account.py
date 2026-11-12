"""The xFormat account control in the brand header."""
from __future__ import annotations

from copy import deepcopy
from queue import Empty, Queue
from threading import Thread

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog

from analysis_modes import METHOD_AI, METHOD_LOCAL
from i18n.translations import t


def _ask_account_later(window) -> None:
    """Ask about the account once the window is on screen.

    Deferred rather than skipped: the header should end up telling the truth,
    it just must not make startup wait for a round trip to do so.
    """
    QTimer.singleShot(0, lambda: window._refresh_account_control(refresh=True))


def _query_account_and_provider(settings, generation, results):
    """Only providers and a queue cross the thread boundary, never widgets."""
    from llm.base import LLMProviderFactory
    import rewriter
    account_status = None
    account = provider = None
    try:
        account = LLMProviderFactory.create("xformat", base_url=settings.xformat_base_url,
                                            endpoints=settings.xformat_endpoints or {})
    except Exception:  # noqa: BLE001
        pass
    try:
        provider = rewriter.build_provider(settings)  # The desktop honours the explicit provider.
    except Exception:  # noqa: BLE001
        pass
    if getattr(provider, "name", None) != "xformat":
        Thread(target=_query_provider_ready, args=(provider, generation, results),
               daemon=True, name="xaudit-provider-status").start()
    try:
        status = account.auth_status(read_only=True)
        account_status = status if status and status.signed_in else None
    except Exception:  # noqa: BLE001 - status failure cannot disable another provider
        pass
    results.put((generation, "account", account_status))
    if getattr(provider, "name", None) == "xformat":
        results.put((generation, "provider", account_status is not None))


def _query_provider_ready(provider, generation, results):
    try:
        available = bool(provider.auth_status().signed_in)
    except Exception:  # noqa: BLE001 - unavailable credentials are an answer
        available = False
    results.put((generation, "provider", available))


#: "This has not been asked yet", distinct from "the answer is no".
UNASKED = object()

# Private alias: the name this lived under inside main_window.py before the
# split, kept so older call sites read unchanged.
_UNASKED = UNASKED


class AccountMixin:
    """Sign-in state for the header's account button.

    Reads `self.settings`, `self.lang`, `self.account_label`,
    `self.account_btn` and the choice widgets from the facade.
    """

    def _xformat_provider(self):
        from llm.base import LLMProviderFactory

        return LLMProviderFactory.create(
            "xformat",
            base_url=self.settings.xformat_base_url,
            endpoints=self.settings.xformat_endpoints or {},
        )

    def _account_status(self, refresh: bool = False, ask: bool = True):
        """Return the cached header account; schedule probes without waiting."""
        if refresh:
            self._invalidate_account_check()
            self._account_cache = _UNASKED
            self._provider_ready = _UNASKED
        if ask and (self._account_cache is _UNASKED or getattr(self, "_provider_ready", _UNASKED) is _UNASKED):
            self._start_account_check()
        return None if self._account_cache is _UNASKED else self._account_cache

    def _invalidate_account_check(self):
        self._account_generation = getattr(self, "_account_generation", 0) + 1
        self._account_checking = False
        self._account_check_pending = set()
        timer = getattr(self, "_account_timer", None)
        if timer is not None:
            timer.stop()

    def _start_account_check(self):
        if getattr(self, "_account_checking", False) or getattr(self, "_account_probe_closed", False):
            return
        if not hasattr(self, "_account_results"):
            self._account_results = Queue()
            self._account_timer = QTimer(self)
            self._account_timer.timeout.connect(self._poll_account_check)
        self._account_checking = True
        self._account_check_pending = {"account", "provider"}
        self._account_timer.start(25)
        if getattr(self, "_provider_ready", _UNASKED) is _UNASKED:
            if METHOD_AI in self.app_state.methods:
                self._pending_ai_methods = self.app_state.methods
            self.app_state.set_ai_available(False)
        self._update_account_run_button()
        Thread(target=_query_account_and_provider,
               args=(deepcopy(self.settings), getattr(self, "_account_generation", 0), self._account_results),
               daemon=True, name="xaudit-account-status").start()

    def _poll_account_check(self):
        if getattr(self, "_account_probe_closed", False):
            return
        while True:
            try:
                generation, kind, value = self._account_results.get_nowait()
            except Empty:
                return
            if generation != getattr(self, "_account_generation", 0):
                continue
            self._account_check_pending.discard(kind)
            self._account_checking = bool(self._account_check_pending)
            if not self._account_checking:
                self._account_timer.stop()
            if kind == "account":
                self._account_cache = value
                self._refresh_account_control(ask=False)
                continue
            available = value
            self._provider_ready = available
            self.app_state.set_ai_available(available)
            pending = getattr(self, "_pending_ai_methods", None)
            self._pending_ai_methods = None
            if available and pending:
                self.app_state.set_methods(pending)
            elif pending and hasattr(self, "status_bar"):
                self.status_bar.showMessage(t("method_ai_unavailable", self.lang))
            self._update_account_run_button()
            self._refresh_account_control(ask=False)

    def _discard_pending_ai_method(self, *_args):
        self._pending_ai_methods = None
        self._update_account_run_button()

    def _update_account_run_button(self):
        if hasattr(self, "analyze_btn"):
            busy = getattr(getattr(self, "view_model", None), "is_busy", False)
            pending = getattr(self, "_account_checking", False) and getattr(self, "_pending_ai_methods", None)
            self.analyze_btn.setEnabled(not busy and not pending)
            if not hasattr(self, "_account_run_tooltip"):
                self._account_run_tooltip = self.analyze_btn.toolTip()
            if pending:
                if self.analyze_btn.toolTip() != getattr(self, "_account_checking_tooltip", None):
                    self._account_run_tooltip = self.analyze_btn.toolTip()
                self._account_checking_tooltip = t("provider_checking", self.lang)
                self.analyze_btn.setToolTip(self._account_checking_tooltip)
            else:
                self.analyze_btn.setToolTip(self._account_run_tooltip)
                self._account_checking_tooltip = None

    def _stop_account_checks(self):
        self._account_probe_closed = True
        self._invalidate_account_check()

    def _refresh_account_control(self, refresh: bool = False,
                                 ask: bool = True) -> None:
        status = self._account_status(refresh=refresh, ask=ask)
        if status is not None:
            self.account_label.setText(status.detail)
            self.account_btn.setText(t("settings_sign_out", self.lang))
        else:
            checking = self._account_cache is _UNASKED and getattr(self, "_account_checking", False)
            self.account_label.setText(t("account_checking", self.lang) if checking else "")
            self.account_btn.setText(t("account_checking_button", self.lang) if checking else t("settings_sign_in", self.lang))
        self.account_btn.setEnabled(self._account_cache is not _UNASKED)
        self.account_btn.setAccessibleName(self.account_btn.text())
        self.account_btn.setToolTip(self.account_label.text())
        ready = getattr(self, "_provider_ready", _UNASKED)
        if ready is not _UNASKED:
            self.app_state.set_ai_available(ready)

    def _on_account_clicked(self) -> None:
        if self._account_cache is _UNASKED:
            return
        if self._account_status(ask=False) is not None:
            self._sign_out()
            return
        self._sign_in()

    def _sign_in(self) -> None:
        from ui.sign_in_dialog import SignInDialog

        dialog = SignInDialog(self._xformat_provider(), self.lang, self)
        if (dialog.exec() != QDialog.DialogCode.Accepted or dialog.status is None
                or not dialog.status.signed_in):
            return
        # Signing in *is* the choice of who pays: an account that was just
        # connected and then ignored in favour of a personal key would make the
        # sign-in pointless. The CLI's rule is the opposite and stays that way -
        # inside a Claude Code session its own signed-in account pays.
        self.settings.llm_provider = "xformat"
        self.settings.save()
        self._invalidate_account_check()
        self._account_cache, self._provider_ready = dialog.status, True
        self._pending_ai_methods = None
        self.app_state.set_provider("xformat")
        self.app_state.set_ai_available(True)
        if hasattr(self, "_populate_providers"):
            self._populate_providers()
        self._select_ai_method()
        self._update_account_run_button()
        self._refresh_account_control(ask=False)
        self.status_bar.showMessage(
            t("sign_in_switched", self.lang, detail=dialog.status.detail))

    def _sign_out(self) -> None:
        ready = getattr(self, "_provider_ready", _UNASKED)
        self._invalidate_account_check()
        try:
            self._xformat_provider().sign_out()
        except Exception as exc:  # noqa: BLE001 - the tokens are gone either way
            self.status_bar.showMessage(str(exc))
        self._account_cache = None
        self._provider_ready = False if self.settings.llm_provider == "xformat" else ready
        if self.settings.llm_provider == "xformat":
            self._pending_ai_methods = None
        self._refresh_account_control()
        self._update_account_run_button()
        # The method combo drops its AI entries when nothing can pay for them,
        # and a request that asked for AI normalises back to the offline engine.
        self._retranslate_choices()
        self.status_bar.showMessage(t("signed_out_message", self.lang))

    def _select_ai_method(self) -> None:
        """Offer the AI method and pick it, now that there is an account.

        Both rather than AI alone: the offline engine costs nothing and finds
        the exact character defects a model does not, so dropping it in
        exchange would be a downgrade disguised as an upgrade.
        """
        self._retranslate_choices()
        index = self.method_combo.findData(
            self.choice_key((METHOD_LOCAL, METHOD_AI)))
        if index >= 0:
            self.method_combo.setCurrentIndex(index)
