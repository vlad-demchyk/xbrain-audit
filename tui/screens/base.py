"""What every screen shares: the key hints, going back, and running a scan.

The key hints matter more than they look. The bindings were always there,
but nothing displayed them, so the only way to learn that `Esc` goes back
was to try it - and the one key people do try, an arrow, did nothing. A
`Footer` turns the bindings into an interface.
"""
from __future__ import annotations

import argparse

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label

from i18n.translations import t


#: Action name -> the key its footer hint is written under. The footer is
#: part of the interface, so it is translated with everything else; the
#: bindings themselves are class-level and therefore built in one language,
#: which is why the descriptions are rewritten per instance below.
BINDING_LABELS = {
    "back": "tui_back",
    "quit": "tui_quit",
    "save": "tui_save",
    "reload": "tui_reload",
    "focus_next": "tui_next",
    "focus_previous": "tui_previous",
    "run": "tui_run",
    "refresh": "tui_refresh",
    "open_selected": "tui_open_report",
    "open_folder": "tui_open_folder",
    "open_first": "tui_open_report",
    "only_errors": "tui_errors_only",
    "show_all": "tui_show_all",
    "copy_text": "tui_copy",
    "command_palette": "tui_palette",
}


#: "no value recorded", distinct from a control whose value really is None.
_UNSET = object()


class XScreen(Screen):
    """Base screen: a header, a footer of key hints, and `Esc` to go back."""

    BINDINGS = [
        ("escape", "back", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._translate_bindings()

    @property
    def lang(self) -> str:
        return getattr(self.app, "lang", "uk")

    def tr(self, key: str, **kwargs) -> str:
        """One string in the interface language, from the shared table."""
        return t(key, self.lang, **kwargs)

    def _translate_bindings(self) -> None:
        """Rewrite the footer hints of this instance in the app's language.

        `BINDINGS` is class-level and evaluated at import, so it can only be
        written in one language. Textual copies it into a per-instance map,
        and that copy is what the footer reads - so this rewrites the copy
        and leaves the class alone.
        """
        from dataclasses import replace

        language = getattr(self.app, "lang", None) or "uk"
        mapping = getattr(self._bindings, "key_to_bindings", None)
        if not mapping:
            return
        for key, bindings in list(mapping.items()):
            rewritten = []
            for binding in bindings:
                # Textual namespaces its own bindings - `app.focus_next`,
                # `screen.copy_text` - and the prefix was not stripped before
                # the lookup, so six footer labels stayed English on every
                # screen while the screens' own bindings translated fine:
                # "Focus Next", "Focus Previous", "Copy selected text" (twice)
                # and "palette", plus `only_errors` and `show_all`, which were
                # simply missing from the table.
                action = (binding.action or "").split("(")[0]
                action = action.rsplit(".", 1)[-1]
                label_key = BINDING_LABELS.get(action)
                if action == "go":
                    # The menu's number keys: each one names a screen, and
                    # the screen's own name is already translated.
                    target = (binding.action or "").strip("go()'\" ")
                    label_key = f"tui_menu_{target}"
                if label_key and binding.description:
                    binding = replace(binding, description=t(label_key, language))
                rewritten.append(binding)
            mapping[key] = rewritten

    #: Below this many columns an inline sentence cannot stay one line: a
    #: `Select` has a minimum width of its own, and three of them plus their
    #: labels need about seventy. Measured at 60x20, where the Full Scan
    #: form put five widgets past the right edge - and a terminal has no
    #: horizontal scroll to get them back.
    NARROW_COLUMNS = 72

    def on_resize(self, event) -> None:
        """Let the stylesheet know the terminal is narrow.

        Textual has no media queries, so the screen carries the answer as a
        class and `.narrow .sentence` turns each sentence into a column. The
        row is longer to read that way and it is *readable*, which the
        half-off-screen version was not.
        """
        self.set_class(event.size.width < self.NARROW_COLUMNS, "narrow")

    def compose_chrome(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def action_back(self) -> None:
        # The main menu is the bottom of the stack; popping it would leave
        # the app with no screen at all, so there it means "quit".
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.exit()


class RunScreen(XScreen):
    """A screen whose form starts a scan.

    Holds the one rule that keeps the captured-output trick safe: at most
    one command runs at a time (see `tui.runner.run_in_thread`). It also
    keeps the button and the status line honest while a run is in flight -
    a second press used to start a second, interleaved scan.
    """

    # A focused target field scrolls the form just far enough to hide its
    # title on short terminals. Keep the top of the form visible; Tab and the
    # arrow bindings still move focus into the controls.
    AUTO_FOCUS = ""

    # Every run screen answers the same three keys, declared once here
    # rather than three times below. Before this, `scan`, `audit` and
    # `fullscan` - the three screens where work is actually started - had no
    # BINDINGS at all: `Escape` worked only because the app caught it, and
    # there was no way to start a run without a mouse.
    BINDINGS = [
        ("escape", "back", "Back"),
        ("ctrl+r", "run_now", "Run"),
        ("f5", "run_now", "Run"),
    ]

    #: Set by the subclass: the id of the status label and of the run button.
    status_id = "status"
    run_button_id = "run"

    #: How often the worker is checked for new progress lines. A status line
    #: does not need sub-frame latency, and polling is what keeps the capture
    #: from re-entering the app - see `tui.runner`.
    poll_interval = 0.15

    # -- status ------------------------------------------------------------

    def status(self, text: str, *, ok: bool = False) -> None:
        label = self.query_one(f"#{self.status_id}", Label)
        label.update(text)
        label.set_class(ok, "ok")

    @property
    def busy(self) -> bool:
        from tui import runner

        return self._run is not None or runner.busy()

    def action_run_now(self) -> None:
        """Start the run from the keyboard.

        Deliberately not Enter: these forms have text fields, and Enter in a
        field means "I finished typing this", not "start a scan over the
        whole site". Ctrl+R and F5 are the keys a person already presses to
        run something.
        """
        if self._run is not None:
            return
        from tui import runner

        other = runner.active()
        if other is not None:
            # Another screen's run: a key that does nothing teaches that
            # the key does nothing, so say what is in the way.
            self.status(self.tr("tui_run_other_active",
                                title=other.title or "…"))
            return
        try:
            button = self.query_one(f"#{self.run_button_id}", Button)
        except Exception:  # noqa: BLE001 - a screen may have no run button
            return
        if not button.disabled:
            button.press()

    def _set_busy(self, busy: bool) -> None:
        try:
            button = self.query_one(f"#{self.run_button_id}")
        except Exception:  # noqa: BLE001 - a screen may have no run button
            return
        button.disabled = busy

    # -- the form the target asks for --------------------------------------

    #: `widget id -> the run option it sets`. A subclass fills this in and
    #: gets two things from it: fields that reach nothing for the current
    #: target are hidden, and a parameter the target's stack asks for is
    #: pre-ticked with the sentence that says who asked.
    #:
    #: Hiding is not tidying. `--depth` on a folder, `--incremental` on a
    #: URL and `--site-controls` on a single file are controls that were
    #: always there and always did nothing, and a control that does nothing
    #: teaches a person that this tool's controls do nothing.
    FIELD_OPTIONS: dict = {}

    #: The id of the label that carries the "enabled, because …" sentences.
    profile_note_id = ""

    def __init__(self) -> None:
        super().__init__()
        self._run = None
        self._timer = None
        self._title = ""
        #: Options the person set by hand. A suggestion never overwrites one
        #: - see `run_profile.Plan.apply`.
        self._touched: set = set()
        self._plan = None
        #: False until the form has finished drawing. `Select` posts
        #: `Changed` as it mounts, so every dropdown on the screen counted
        #: as a deliberate choice before anybody had touched one - and a
        #: deliberate choice is exactly what the profile refuses to
        #: overwrite. The whole feature was silently off because of it.
        self._ready = False
        #: `option -> value` this screen wrote from the profile. A widget
        #: posts its `Changed` message after the write returns, so a flag
        #: held across the write is already down by the time the message
        #: arrives - and the profile's own tick came back as the person's.
        #: Matching on the value is what survives the delay.
        self._auto: dict = {}
        #: `widget id -> value` last written from Settings; see
        #: `apply_run_defaults`.
        self._defaults_shown: dict = {}

    #: `widget id -> RunDefaults attribute`: the controls whose starting
    #: value comes from Settings (P-31). Filled in by a subclass.
    DEFAULT_FIELDS: dict = {}

    def run_defaults(self):
        from tui import run_defaults

        return run_defaults.load()

    def apply_run_defaults(self) -> None:
        """Bring the Settings-backed controls up to the stored settings.

        Only a control still showing the default this screen last put there:
        one the person or the target's profile changed is theirs. Called on
        every return to the screen, because Settings is saved on another
        screen while this one is already built.
        """
        from textual.widgets import Select

        defaults = self.run_defaults()
        for widget_id, attribute in self.DEFAULT_FIELDS.items():
            try:
                widget = self.query_one(f"#{widget_id}", Select)
            except Exception:  # noqa: BLE001 - a screen without that control
                continue
            wanted = getattr(defaults, attribute)
            shown = self._defaults_shown.get(widget_id, widget.value)
            if widget.value != shown:
                continue
            if widget.value != wanted:
                option = self.FIELD_OPTIONS.get(widget_id)
                if option:
                    self._auto[option] = wanted
                try:
                    widget.value = wanted
                except Exception:  # noqa: BLE001 - a value not in the list
                    if option:
                        self._auto.pop(option, None)
                    continue
            self._defaults_shown[widget_id] = wanted

    def on_screen_resume(self) -> None:
        if self._run is None:
            self.apply_run_defaults()

    def on_mount(self) -> None:
        # After the first refresh, not during mount: the mount-time
        # `Changed` messages are already in flight by then.
        self.call_after_refresh(self._form_ready)

    def _form_ready(self) -> None:
        self._ready = True

    def current_target(self) -> str:
        """The target field, unquoted the way the CLI unquotes it."""
        from textual.widgets import Input

        from cli_impl.auditpass import unquote_target

        try:
            return unquote_target(self.query_one("#target", Input).value)
        except Exception:  # noqa: BLE001 - a screen may have no target field
            return ""

    def on_input_blurred(self, event) -> None:
        """Re-read the target once the person has finished typing it.

        On blur rather than on every keystroke, deliberately: a form whose
        fields appear and disappear mid-word is a form that moves the thing
        you were about to click. `p`, `pa`, `pat` are three different target
        kinds and none of them is the answer.
        """
        if getattr(event.input, "id", "") == "target":
            self.reshape_for_target()

    def on_checkbox_changed(self, event) -> None:
        """Remember that this switch is now the person's, not the profile's."""
        self._note_change(getattr(event.checkbox, "id", ""), event.value)

    def on_select_changed(self, event) -> None:
        self._note_change(getattr(event.select, "id", ""), event.value)

    #: What each option means when it is not in play. A control this target
    #: cannot use is hidden, and a hidden control must not still be read: a
    #: `--devserver` ticked for a repository and left ticked while a single
    #: file was audited would have started a dev server for a file.
    INERT = {
        "depth": 0,
        "site_controls": False,
        "no_session": False,
        "incremental": False,
        "devserver": False,
        "web_parts": False,
        "project": None,
        "start_command": None,
        "dev_server_port": None,
        "repo": None,
        "medium": None,
        "max_files": 5000,
    }

    def settle(self, args):
        """Blank every option this target cannot use, and hand `args` back."""
        if self._plan is None:
            return args
        for option, inert in self.INERT.items():
            if not self._plan.applies(option) and hasattr(args, option):
                setattr(args, option, inert)
        return args

    def _fill_projects(self, plan) -> None:
        """Offer the projects in this folder, or hide the question."""
        from textual.widgets import Select

        try:
            select = self.query_one("#project", Select)
        except Exception:  # noqa: BLE001 - a screen without the control
            return
        shown = plan.ambiguous()
        for widget in self.query(".field-project"):
            widget.display = shown
        select.display = shown
        if not shown:
            select.set_options([(self.tr("tui_project_whole"), "")])
            select.value = ""
            return
        options = [(self.tr("tui_project_whole"), "")]
        options += [(name, name) for name in plan.choices()]
        current = select.value
        select.set_options(options)
        # A folder that was already narrowed keeps the choice; a different
        # folder cannot, because the name belonged to the previous one.
        select.value = current if current in dict(options) else ""

    def chosen_project(self) -> str:
        """The project the person picked, or `""` for the whole folder."""
        from textual.widgets import Select

        try:
            select = self.query_one("#project", Select)
        except Exception:  # noqa: BLE001 - a screen without the control
            return ""
        if not select.display:
            return ""
        return select.value or ""

    def _note_change(self, widget_id: str, value) -> None:
        """Record a control the person changed - and only the person."""
        if not self._ready:
            return
        option = self.FIELD_OPTIONS.get(widget_id)
        if not option:
            return
        if self._auto.get(option, _UNSET) == value:
            self._auto.pop(option, None)
            return
        self._touched.add(option)

    def reshape_for_target(self) -> None:
        """Show what this target can use, and pre-tick what it asks for."""
        import run_profile
        from textual.widgets import Checkbox, Label, Select

        target = self.current_target()
        if not target:
            return
        try:
            plan = run_profile.build(target)
        except Exception:  # noqa: BLE001 - a form must never fail to draw
            return
        self._plan = plan
        for widget_id, option in self.FIELD_OPTIONS.items():
            shown = plan.applies(option)
            for widget in self.query(f".field-{widget_id}"):
                widget.display = shown
            try:
                self.query_one(f"#{widget_id}").display = shown
            except Exception:  # noqa: BLE001 - an id a screen does not have
                pass
        # Which project, when the folder holds more than one. Filled from
        # the plan rather than typed: a folder of twenty solutions is a list
        # to pick from, and typing one of twenty names correctly is not the
        # question a person should be asked.
        self._fill_projects(plan)

        # The dev-server overrides, only where there is a server to
        # override. Detection reads one script name out of `package.json`,
        # and a monorepo has several - see `devserver.servers_under`.
        serves = bool(getattr(plan, "servers", ()))
        for widget in self.query(".field-server"):
            widget.display = serves

        # The URL field an SPFx checkout asks for, and nothing else does.
        for prompt in ("site-url",):
            wanted = plan.asks_for(prompt.replace("-", "_"))
            for widget in self.query(f".field-{prompt}"):
                widget.display = wanted
            try:
                self.query_one(f"#{prompt}").display = wanted
            except Exception:  # noqa: BLE001 - an id a screen does not have
                pass

        by_option = {option: widget_id
                     for widget_id, option in self.FIELD_OPTIONS.items()}
        lines = []
        for item in plan.suggestions:
            if item.option in self._touched or not plan.applies(item.option):
                continue
            widget_id = by_option.get(item.option)
            if widget_id is None:
                continue
            try:
                widget = self.query_one(f"#{widget_id}")
            except Exception:  # noqa: BLE001 - a screen without that control
                continue
            if isinstance(widget, Checkbox) and widget.value != item.value:
                self._auto[item.option] = bool(item.value)
                widget.value = bool(item.value)
            elif isinstance(widget, Select) and widget.value != item.value:
                try:
                    self._auto[item.option] = item.value
                    widget.value = item.value
                except Exception:  # noqa: BLE001 - a value not in the list
                    self._auto.pop(item.option, None)
                    continue
            else:
                continue
            lines.append(run_profile.explain(item, self.lang))
        for prompt in plan.prompts:
            lines.append(run_profile.explain(prompt, self.lang, enabled=False))
            if prompt.field == "sign_in":
                lines.append(sign_in_hint(target, self.lang))
        if plan.ambiguous():
            lines.append(self.tr("tui_projects_several",
                                 count=len(plan.projects),
                                 names=", ".join(
                                     _folder_name(p.root)
                                     for p in plan.projects[:4])))
        if self.profile_note_id:
            try:
                note = self.query_one(f"#{self.profile_note_id}", Label)
            except Exception:  # noqa: BLE001 - a screen without the note
                return
            note.update("\n".join(lines))
            note.display = bool(lines)

    # -- running -----------------------------------------------------------

    def start_run(self, command, args: argparse.Namespace, *,
                  title: str) -> bool:
        """Run `command(args)` on a worker thread. False if one is already on.

        `title` is what the results screen is called, so a person who ran
        three things can tell which result they are looking at.

        One at a time, and that is not a nicety: the worker captures stdout
        and stderr by replacing them process-wide, so two overlapping runs
        would interleave into each other's output.
        """
        from tui import runner

        if self._run is not None:
            return False
        try:
            run = runner.start(command, args, title)
        except runner.RunBusy as exc:
            # Another screen's run: say whose, rather than a button that
            # silently does nothing.
            self.status(self.tr("tui_run_other_active",
                                title=exc.active.title or "…"))
            return False
        self._title = title
        self._run = run
        self._set_busy(True)
        self.status(self.tr("tui_run_starting", title=title))
        self._timer = self.set_interval(self.poll_interval, self._poll)
        return True

    def _poll(self) -> None:
        """Drain progress, and finish once the worker has a result."""
        run = self._run
        if run is None:
            return
        for line in run.new_lines():
            # Only the tool's own progress lines: a library warning on
            # stderr is kept for the log but must not become the status.
            if line.startswith("#"):
                self.status(line.lstrip("# ").strip() or line)
        if run.running:
            return
        result = run.result
        self._run = None
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._set_busy(False)
        self.show_result(self._title, result)

    def show_result(self, title: str, result) -> None:
        """Show the finished run. Overridable; the default opens Results."""
        from tui.screens.results import ResultsScreen

        if result.error:
            self.status(self.tr("tui_run_failed", error=result.error))
            return
        if not result.ok:
            # Returned 2+ without raising: the run could not do its work.
            # Results still opens, because its log is where the reason is.
            self.status(self.tr("tui_run_failed_code", code=result.exit_code))
            self.app.push_screen(ResultsScreen(title, result))
            return
        self.status(self.tr("tui_run_done"), ok=True)
        self.app.push_screen(ResultsScreen(title, result))


def _folder_name(path: str) -> str:
    """The last component of a path, for naming one project among several."""
    from pathlib import Path

    return Path(path).name or path


def sign_in_hint(target: str, lang: str) -> str:
    """The command that signs in to a SharePoint site, said in the form.

    The TUI cannot open a browser window of its own, and a SharePoint run
    without a session audits Microsoft's sign-in page. So the form names
    the one command that fixes it - the same sentence the CLI ends with
    (`cli_impl.auditpass.login_hint`) - before the run is started.
    """
    import site_session
    from cli_impl.auditpass import login_hint

    return t("tui_sharepoint_login", lang, host=site_session.host_of(target),
             command=login_hint(target))
