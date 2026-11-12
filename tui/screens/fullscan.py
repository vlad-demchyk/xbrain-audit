"""Fullscan screen — combined AI patterns + accessibility in one run."""
from __future__ import annotations

import argparse

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from audit.base import CONFIDENCE_ORDER
from cli import cmd_fullscan
from tui.screens.base import RunScreen
from tui.screens.confirm import ConfirmModal


def _port_or_none(text: str):
    """A port number, or `None` for "work it out".

    A field is text and a port is a number, and a person types neither
    reliably: anything that is not a number means the same as an empty
    field, which is the answer that lets the run continue.
    """
    try:
        value = int((text or "").strip())
    except ValueError:
        return None
    return value if 0 < value < 65536 else None


class FullscanScreen(RunScreen):
    """Form to configure and run a full scan."""

    status_id = "fullscan-status"
    DEFAULT_FIELDS = {"depth": "depth"}

    def __init__(self) -> None:
        super().__init__()
        self._defaults = self.run_defaults()
    profile_note_id = "fullscan-profile"

    #: Which control sets which run option. See `RunScreen.FIELD_OPTIONS`.
    FIELD_OPTIONS = {
        "depth": "depth",
        "breakpoints": "breakpoints",
        "medium": "medium",
        "confidence": "confidence",
        "within": "within",
        "no-session": "no_session",
        "incremental": "incremental",
        "unsettled": "unsettled",
        "site-controls": "site_controls",
        "agent": "agent",
        "no-browser": "no_browser",
        "devserver": "devserver",
    }

    def compose(self) -> ComposeResult:
        yield from self.compose_chrome()
        with Vertical(id="fullscan-form"):
            yield Label(self.tr("tui_fullscan_title"), classes="menu-title")
            yield Static("")

            yield Label(self.tr("tui_target_any"))
            # `example.com` is enough - the scheme is added for you.
            yield Input(placeholder=self.tr("tui_placeholder_repo"), id="target")

            # The address an SPFx checkout ships into; see AuditScreen for
            # why a folder alone cannot answer it.
            yield Label(self.tr("tui_site_url"), classes="field-site-url")
            yield Input(placeholder=self.tr("tui_site_url_placeholder"),
                        id="site-url", classes="field-site-url")

            # What the target's own stack asked for, and why.
            # Which project, when the folder holds more than one. Hidden
            # until one does - see `RunScreen._fill_projects`.
            yield Label(self.tr("tui_project_label"), classes="field-project")
            yield Select([(self.tr("tui_project_whole"), "")], value="",
                         allow_blank=False, id="project",
                         classes="field-project")

            yield Label("", id="fullscan-profile", classes="hint")

            # The design's toolbar (artboard 3a) reads "analyze Site ·
            # depth 2" - one sentence with the choices inline rather than a
            # label above every one of them. `Select(compact=True)` is
            # Textual's own version of that: no frame, sized to its current
            # value, opens the same way. Three selectors read as one
            # sentence this way where three stacked "Label: dropdown" rows
            # read as a form - which is the whole difference the redesign
            # was for.
            with Horizontal(classes="sentence"):
                yield Static(self.tr("tui_label_language"), classes="inline-label")
                yield Select(
                    [
                        ("auto", ""),
                        ("English", "en"),
                        ("Українська", "uk"),
                        ("Italiano", "it"),
                    ],
                    value="",
                    id="language",
                    compact=True,
                    classes="inline-select",
                )
                yield Static("·", classes="inline-sep field-depth")
                yield Static(self.tr("tui_label_depth"),
                             classes="inline-label field-depth")
                yield Select(
                    [
                        ("1", "1"),
                        (self.tr("setup_depth_zero"), "0"),
                        ("2", "2"),
                        ("3", "3"),
                    ],
                    value=self._defaults.depth,
                    id="depth",
                    compact=True,
                    classes="inline-select",
                )
                yield Static("·", classes="inline-sep")
                yield Static(self.tr("tui_label_widths"), classes="inline-label")
                # Every width `responsive.BREAKPOINTS` knows, as on the audit
                # screen. `tablet` and `reflow` were missing from this list
                # for the same reason they were missing from that one - the
                # list was typed out rather than derived - so the width that
                # finds WCAG 1.4.10 overflow was unreachable from here.
                yield Select(
                    [
                        (self.tr("breakpoint_desktop"), "desktop"),
                        (self.tr("breakpoint_all"), "all"),
                        (self.tr("breakpoint_desktop_mobile"), "desktop,mobile"),
                        (self.tr("breakpoint_tablet"), "tablet"),
                        (self.tr("breakpoint_mobile"), "mobile"),
                        (self.tr("breakpoint_reflow"), "reflow"),
                    ],
                    value="desktop",
                    id="breakpoints",
                    compact=True,
                    classes="inline-select",
                )
                yield Static("·", classes="inline-sep")
                yield Static(self.tr("tui_label_certainty"), classes="inline-label")
                yield Select(
                    [(self.tr("certainty_any"), "")]
                    + [(self.tr(f"certainty_{value}"), value)
                       for value in CONFIDENCE_ORDER],
                    value="",
                    id="confidence",
                    compact=True,
                    classes="inline-select",
                )

            with Horizontal(classes="sentence"):
                yield Static(self.tr("tui_medium_label"), classes="inline-label")
                yield Select(
                    [
                        (self.tr("tui_medium_auto"), ""),
                        (self.tr("setup_medium_web"), "web"),
                        (self.tr("setup_medium_email"), "email"),
                    ],
                    value="",
                    id="medium",
                    compact=True,
                    classes="inline-select",
                )

            yield Static("")
            # Four of the nine flags this screen was missing. `--repo` is
            # not among them on purpose: a full scan of a URL takes a
            # checkout, and that is a path field the window has room for and
            # a terminal form does not - `xaudit fullscan --repo` remains
            # the way to ask for it. `--web-parts` follows it out for the
            # same reason: it reads part manifests from that checkout.
            yield Label(self.tr("within_placeholder"))
            yield Input(placeholder=self.tr("tui_within_placeholder"), id="within")
            yield Static("")
            yield Checkbox(self.tr("tui_no_session"), id="no-session")
            yield Checkbox(self.tr("tui_incremental_full"), id="incremental")
            yield Checkbox(self.tr("tui_unsettled"), id="unsettled")
            yield Checkbox(self.tr("tui_site_controls"), id="site-controls")
            yield Checkbox(self.tr("tui_agent_mode"), id="agent")
            yield Checkbox(self.tr("tui_no_browser"), id="no-browser")
            # Off by default: a repo's dev server may already be running
            # elsewhere, and starting a second one on a different port is a
            # confusing outcome, not a helpful one. A repo scanned with this
            # unchecked is scanned statically, same as always.
            yield Checkbox(self.tr("tui_devserver"), id="devserver")
            # What to run instead of the detected script, and the port to
            # expect for the stacks that do not announce their own. Shown
            # only where there is a server to start.
            yield Label(self.tr("setup_start_command"), classes="field-server")
            yield Input(placeholder=self.tr("setup_start_command_placeholder"),
                        id="start-command", classes="field-server")
            yield Label(self.tr("setup_dev_port"), classes="field-server")
            yield Input(placeholder=self.tr("setup_dev_port_auto"),
                        id="dev-server-port", classes="field-server")

            yield Static("")
            with Horizontal():
                yield Button(self.tr("tui_fullscan_run"), id="run", variant="primary")
                yield Button(self.tr("tui_back"), id="back")

            yield Static("")
            yield Label("", id="fullscan-status")
            yield Label(self.tr("tui_documents_hint"), classes="hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_back()
        elif event.button.id == "run":
            self._run_fullscan()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "target":
            self._run_fullscan()

    def _run_fullscan(self) -> None:
        from cli_impl.auditpass import unquote_target

        target = unquote_target(self.query_one("#target", Input).value)
        if not target:
            self.status(self.tr("tui_need_target"))
            return

        # An SPFx checkout plus the site it ships into is one run - see
        # `AuditScreen._run_audit`, which does the same pivot.
        site_url = unquote_target(self.query_one("#site-url", Input).value)
        repo = None
        web_parts = False
        if site_url and self._plan is not None and self._plan.asks_for("site_url"):
            repo, target, web_parts = target, site_url, True
            # The plan was built for the folder; the run is now about the
            # site, and `settle` below reads the plan to decide which
            # options are in play. Left as it was, it would blank the very
            # `--repo` this branch just set.
            import run_profile
            self._plan = run_profile.build(target, repo=repo)

        args = argparse.Namespace(
            target=target,
            url=False,
            web_parts=web_parts,
            project=self.chosen_project() or None,
            profile_defaults=False,
            _explicit=set(self._touched),
            depth=int(self.query_one("#depth", Select).value or 0),
            max_pages=self.run_defaults().max_pages,
            max_files=5000,
            ext=None,
            exclude=None,
            no_default_excludes=False,
            repo=repo,
            devserver=self.query_one("#devserver", Checkbox).value,
            start_command=(self.query_one("#start-command", Input).value.strip()
                           or None),
            dev_server_port=_port_or_none(
                self.query_one("#dev-server-port", Input).value),
            yes=False,
            detector="offline",
            scope="both",
            no_typography=False,
            confidence=self.query_one("#confidence", Select).value or None,
            unsettled=self.query_one("#unsettled", Checkbox).value,
            site_controls=self.query_one("#site-controls", Checkbox).value,
            styled_report=None,
            report=None,
            check=False,
            # Empty means "work it out from the page content" - see
            # `cli_impl.fullscan._detect_report_language`.
            language=self.query_one("#language", Select).value or None,
            breakpoints=self.query_one("#breakpoints", Select).value,
            agent=self.query_one("#agent", Checkbox).value,
            no_browser=self.query_one("#no-browser", Checkbox).value,
            json=True,
            within=self.query_one("#within", Input).value.strip(),
            no_session=self.query_one("#no-session", Checkbox).value,
            incremental=self.query_one("#incremental", Checkbox).value,
            medium=self.query_one("#medium", Select).value or None,
            no_hints=True,
        )

        args = self.settle(args)
        title = self.tr("tui_fullscan_of", target=target)
        if args.devserver:
            stack = self._devserver_stack_needing_confirm(target)
            if stack is not None:
                question = self.tr("devserver_confirm",
                                   stack=stack.name, repo=target)
                self.app.push_screen(
                    ConfirmModal(question),
                    lambda confirmed: self._on_devserver_confirmed(confirmed, args, title))
                return
        # Not checked: scanned statically, same as always. If a stack exists,
        # `cmd_fullscan` says so itself (a "# [devserver] ..." stderr line),
        # which this screen already surfaces through the ordinary status-line
        # mechanism - no separate notice needed here.
        self.start_run(cmd_fullscan, args, title=title)

    def _devserver_stack_needing_confirm(self, target: str):
        """The detected stack, if it needs an install confirmed - else `None`.

        Cheap filesystem/`--version`-class checks only, run synchronously on
        the UI thread before anything starts: this is not the server itself,
        which is what `tui.runner`'s worker goes on to start once `start_run`
        is called below, exactly as it always has.
        """
        from pathlib import Path

        import devserver
        from cli_impl.auditpass import looks_like_url

        if looks_like_url(target):
            return None
        path = Path(target)
        if not path.is_dir():
            return None
        stack = devserver.detect_stack(path)
        if stack is None or stack.deps_satisfied(path):
            return None
        return stack

    def _on_devserver_confirmed(self, confirmed: bool, args: argparse.Namespace,
                                title: str) -> None:
        # A separate call, not a resumed one: the modal answers on its own
        # callback, on the UI thread, well after `_run_fullscan` already
        # returned - there is no suspended call frame to continue.
        args.yes = confirmed
        self.start_run(cmd_fullscan, args, title=title)
