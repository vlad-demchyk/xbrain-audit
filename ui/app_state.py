"""Centralized application state with change notifications.

AppState holds every user-facing choice (source, reader, check, method,
provider) and emits Qt signals when any of them change. The toolbar
combos write to this object; the UI subscribes to its signals to
update visibility, enabled state, and combo contents.

This replaces the scattered ``self.source``, ``self._chosen_checks()``,
``self._chosen_methods()`` etc. that lived directly on MainWindow.
"""
from __future__ import annotations


from PySide6.QtCore import QObject, Signal

from analysis_modes import (
    CHECK_ACCESSIBILITY,
    METHOD_LOCAL,
    SOURCE_SITE,
)
from ui.mode_rules import (
    auto_readers,
    derive_mode,
    normalize_method_choice,
    provider_visible,
)


class AppState(QObject):
    """Observable state for the entire application.

    Every setter validates the new value, normalises it, and emits the
    appropriate changed signal only when the value actually differs.
    The UI connects to these signals once, at startup.
    """

    # -- signals -----------------------------------------------------------
    source_changed = Signal(str)          # new source
    checks_changed = Signal(tuple)        # new checks tuple
    method_changed = Signal(tuple)        # new methods tuple
    provider_changed = Signal(str)        # new provider key
    ai_available_changed = Signal(bool)   # account state changed
    mode_changed = Signal(str)            # derived mode changed
    scope_changed = Signal(str)           # new scope
    project_changed = Signal()            # detected stack, or its exclusions lifted
    view_changed = Signal()               # audit categories or certainty floor

    # Fired after any axis changes, in addition to the specific signal.
    # Listeners that care about the combined state (e.g. button visibility)
    # connect to this one signal instead of all five.
    any_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._source: str = SOURCE_SITE
        self._checks: tuple[str, ...] = (CHECK_ACCESSIBILITY,)
        self._methods: tuple[str, ...] = (METHOD_LOCAL,)
        self._provider: str = ""
        self._ai_available: bool = False
        self._target: str = ""
        self._depth: int = 0
        self._scope: str = "content"
        self._incremental: bool = False
        self._extensions: tuple[str, ...] = ()
        #: Which audit categories to report, and how certain a finding has to
        #: be. Empty means every category and every certainty - the state a
        #: run starts in, and the reason neither is stored as a full tuple of
        #: everything: "no choice made" and "chose all six" are the same
        #: answer and must not be two.
        self._categories: tuple[str, ...] = ()
        self._confidence_floor: str = ""
        #: Whether the undecided are listed. Off, like everywhere else: an
        #: engine's "this element is on a background image, check by hand" is
        #: not a finding, and on one page it was 312 of 348 contrast rows.
        self._unsettled: bool = False
        #: `--site-controls`: fetch robots.txt and the sitemaps it declares.
        #: Off by default on both surfaces, because it is two extra requests
        #: to an address the user did not name.
        self._site_controls: bool = False
        #: What the chosen folder turned out to be (`project_profile.Profile`),
        #: and whether the person has overruled the exclusions it implies.
        #:
        #: Both live here rather than on the window because they are a run
        #: choice like every other one on this object, and because the
        #: *effective* ignore list has to be derived from them in one place -
        #: two copies of an ignore list is how one surface ends up scanning
        #: `wp-includes/` while another does not.
        self._project = None
        self._project_excludes_lifted: bool = False
        #: `run_profile.Plan` for the current target: what kind of thing it
        #: is, what its stack asks the run to switch on, and whether the
        #: folder holds more than one project. Rebuilt by the window when
        #: the target, the source or the paired checkout changes - never
        #: derived here, because building it touches the filesystem and this
        #: object is read on every repaint.
        self._run_plan = None
        #: Options the person set by hand, so a profile suggestion never
        #: overwrites one. See `run_profile.Plan.apply`.
        self._profile_touched: set = set()
        #: `--web-parts`: confine the audit to the SPFx parts the paired
        #: checkout ships. Off unless the profile asks and nobody says
        #: otherwise; meaningless without a paired repository, which is why
        #: `run_profile` only ever suggests it for a site that has one.
        self._web_parts: bool = False
        #: One project inside the chosen folder, by absolute path, or empty
        #: for the whole folder. A directory of twenty SPFx solutions is
        #: twenty deliverables, and reading it as one root reported them as
        #: one - see `project_profile.projects`.
        self._chosen_project: str = ""
        #: `--no-session`: read the site the way a stranger sees it. Off, so
        #: the ordinary run is the one that reads what the person can see -
        #: and switching it on is how they find out how much of the site is
        #: behind the door they walked through without noticing.
        self._no_session: bool = False
        #: `--start-command` and `--dev-server-port`: what to run instead of
        #: the detected script, and which port to expect. Both empty in the
        #: ordinary case. They exist because detection reads one script name
        #: out of `package.json`, and a monorepo has several - the root's
        #: `dev` is not the same server as an application's.
        self._start_command: str = ""
        self._dev_server_port: int = 0
        #: `--medium`: what the documents in a folder are *for*. Empty means
        #: "read it off each file", which is the right answer nearly always -
        #: an Outlook namespace or a merge tag settles it. It is here for the
        #: deliverable that carries neither, where the run would otherwise
        #: ask an email for a canonical URL, Open Graph tags, a skip link and
        #: landmarks: 1074 findings over 144 documents in a real workspace,
        #: with the six loudest rules all browser concepts. See `audit.medium`.
        self._medium: str = ""
        #: `--repo`: the checkout that serves the site being scanned. Empty
        #: is the normal case, and the whole feature is what happens when it
        #: is not: a passage found on a page gets the file and the line that
        #: wrote it, because a page address tells a reader where to look and
        #: never where to edit. Only meaningful for a site - a folder run is
        #: already reading the files.
        self._paired_repo: str = ""
        self._within: str = ""

    # -- paired repository -------------------------------------------------
    @property
    def paired_repo(self) -> str:
        return self._paired_repo

    def set_paired_repo(self, value: str) -> None:
        value = (value or "").strip()
        if value == self._paired_repo:
            return
        self._paired_repo = value
        self.project_changed.emit()
        self.any_changed.emit()

    #: `--within`: read only the subtree this selector matches. Empty is the
    #: whole document, which is what nearly every run wants; it is here for
    #: the delivered web part or embedded widget that lives inside somebody
    #: else's page. A selector that matches nothing is an error and not an
    #: empty result - see `audit.within`.
    @property
    def within(self) -> str:
        return self._within

    def set_within(self, value: str) -> None:
        value = (value or "").strip()
        if value == self._within:
            return
        self._within = value
        self.view_changed.emit()
        self.any_changed.emit()

    # -- medium ------------------------------------------------------------
    @property
    def medium(self) -> str:
        return self._medium

    def set_medium(self, value: str) -> None:
        value = (value or "").strip()
        if value == self._medium:
            return
        self._medium = value
        self.project_changed.emit()
        self.any_changed.emit()

    # -- project -----------------------------------------------------------
    @property
    def project(self):
        return self._project

    def set_project(self, value) -> None:
        if value is self._project:
            return
        self._project = value
        self.project_changed.emit()
        self.any_changed.emit()

    # -- what the target asks for ------------------------------------------
    @property
    def run_plan(self):
        return self._run_plan

    def set_run_plan(self, value) -> None:
        """Store the plan. Deliberately silent.

        `any_changed` is wired to `MainWindow._sync_source_from_state`, which
        writes the state's source back over the window's own - so emitting
        here would make *reading the target* rewrite which source is
        selected. The surfaces that show the plan are refreshed by the same
        call that rebuilt it; there is nothing here for a signal to wake.
        """
        self._run_plan = value

    @property
    def chosen_project(self) -> str:
        return self._chosen_project

    def set_chosen_project(self, value: str) -> None:
        value = (value or "").strip()
        if value == self._chosen_project:
            return
        self._chosen_project = value
        self.project_changed.emit()
        self.any_changed.emit()

    @property
    def no_session(self) -> bool:
        return self._no_session

    def set_no_session(self, value: bool) -> None:
        value = bool(value)
        if value == self._no_session:
            return
        self._no_session = value
        self.any_changed.emit()

    @property
    def start_command(self) -> str:
        return self._start_command

    def set_start_command(self, value: str) -> None:
        value = (value or "").strip()
        if value == self._start_command:
            return
        self._start_command = value

    @property
    def dev_server_port(self) -> int:
        return self._dev_server_port

    def set_dev_server_port(self, value: int) -> None:
        try:
            value = int(value or 0)
        except (TypeError, ValueError):
            value = 0
        if value == self._dev_server_port:
            return
        self._dev_server_port = value

    @property
    def scan_target(self) -> str:
        """What a run actually reads.

        The typed path, unless one project inside it was chosen. Separate
        from `target` on purpose: the field keeps showing the folder the
        person picked, and only the run narrows - so clearing the choice
        cannot lose the path it was made inside.
        """
        return self._chosen_project or self._target

    @property
    def profile_touched(self) -> set:
        return set(self._profile_touched)

    def touch_option(self, option: str) -> None:
        """Record that the person set this option themselves."""
        if option:
            self._profile_touched.add(option)

    @property
    def web_parts(self) -> bool:
        return self._web_parts

    def set_web_parts(self, value: bool, by_person: bool = True) -> None:
        """Confine the audit to the parts the paired checkout ships.

        `by_person` is False when the profile is the one asking, so that a
        suggestion does not register as a deliberate choice and then block
        the next one.
        """
        value = bool(value)
        if by_person:
            self.touch_option("web_parts")
        if value == self._web_parts:
            return
        self._web_parts = value
        self.project_changed.emit()

    @property
    def project_excludes_lifted(self) -> bool:
        return self._project_excludes_lifted

    def set_project_excludes_lifted(self, value: bool) -> None:
        """Scan what the profile says is not the product after all.

        A profile is evidence about *ownership*, not a certainty: a fork of a
        theme, a vendored library somebody does in fact maintain, or a wrong
        marker makes the exclusion wrong. It is arguable by design - so it is
        arguable from the window, in one click, with the profile's own
        reasons on screen beside it.
        """
        value = bool(value)
        if value == self._project_excludes_lifted:
            return
        self._project_excludes_lifted = value
        self.project_changed.emit()
        self.any_changed.emit()

    def ignore_patterns_with_project(self, base) -> list:
        """The ignore list a folder run actually uses.

        Derived, never stored: the person's own list plus what the detected
        stack says is not theirs, unless they have lifted it.
        """
        patterns = list(base or [])
        if self._project is None or self._project_excludes_lifted:
            return patterns
        return self._project.applied_to(patterns)

    # -- source ------------------------------------------------------------
    @property
    def source(self) -> str:
        return self._source

    def set_source(self, value: str) -> None:
        if value == self._source:
            return
        old_mode = self.mode
        self._source = value
        self.source_changed.emit(value)
        self._emit_mode_if_changed(old_mode)
        self.any_changed.emit()

    def set_source_and_target_for_resolved_run(
            self, source: str, target: str) -> tuple[str, str]:
        """Set source and target for one run, without `source_changed`.

        Returns `(previous_source, previous_target)` so the caller can put
        them back once the run this was for has started. For a repo whose
        dev server was just started and is now read as a site: the widgets
        must keep showing "Repository" - the user's actual choice - not flip
        to "Website" because a server answered behind the scenes. `target`
        already has no signal to suppress (see `set_target`); `source` does,
        which is the only reason this method exists alongside the ordinary
        setters.
        """
        previous = (self._source, self._target)
        self._source = source
        self._target = target
        return previous

    # -- readers (auto-determined from source) -----------------------------
    @property
    def readers(self) -> tuple[str, ...]:
        """The readers for the current source, determined automatically."""
        return auto_readers(self._source)

    # -- checks ------------------------------------------------------------
    @property
    def checks(self) -> tuple[str, ...]:
        return self._checks

    def set_checks(self, value: tuple[str, ...]) -> None:
        if value == self._checks:
            return
        old_mode = self.mode
        self._checks = value
        self.checks_changed.emit(value)
        self._emit_mode_if_changed(old_mode)
        self.any_changed.emit()

    # -- methods -----------------------------------------------------------
    @property
    def methods(self) -> tuple[str, ...]:
        return self._methods

    def set_methods(self, value: tuple[str, ...]) -> None:
        normalised = normalize_method_choice(value, ai_available=self._ai_available)
        if normalised == self._methods:
            return
        self._methods = normalised
        self.method_changed.emit(normalised)
        self.any_changed.emit()

    # -- provider ----------------------------------------------------------
    @property
    def provider(self) -> str:
        return self._provider

    def set_provider(self, value: str) -> None:
        if value == self._provider:
            return
        self._provider = value
        self.provider_changed.emit(value)
        self.any_changed.emit()

    # -- ai_available ------------------------------------------------------
    @property
    def ai_available(self) -> bool:
        return self._ai_available

    def set_ai_available(self, value: bool) -> None:
        if value == self._ai_available:
            return
        self._ai_available = value
        if not value:
            self._methods = normalize_method_choice(self._methods, ai_available=False)
            self.method_changed.emit(self._methods)
        self.ai_available_changed.emit(value)
        self.any_changed.emit()

    # -- target / depth (no signals, read by ViewModel) --------------------
    @property
    def target(self) -> str:
        return self._target

    def set_target(self, value: str) -> None:
        self._target = value

    @property
    def depth(self) -> int:
        return self._depth

    def set_depth(self, value: int) -> None:
        self._depth = max(0, value)

    # -- scope -------------------------------------------------------------
    @property
    def scope(self) -> str:
        return self._scope

    def set_scope(self, value: str) -> None:
        if value == self._scope:
            return
        self._scope = value
        self.scope_changed.emit(value)
        self.any_changed.emit()

    @property
    def incremental(self) -> bool:
        return self._incremental

    def set_incremental(self, value: bool) -> None:
        value = bool(value)
        if value == self._incremental:
            return
        self._incremental = value
        self.any_changed.emit()

    @property
    def extensions(self) -> tuple[str, ...]:
        return self._extensions

    def set_extensions(self, value) -> None:
        extensions = tuple(dict.fromkeys(
            extension if extension.startswith(".") else f".{extension}"
            for item in (value or ())
            if (extension := str(item).strip().lower())
        ))
        if extensions == self._extensions:
            return
        self._extensions = extensions
        self.any_changed.emit()

    # -- the view over a finished audit ------------------------------------
    #
    # Category and certainty narrow what is *shown*, never what is run: the
    # rules are cheap and share one parse, so a run is made once and read
    # through `audit.base.issues_in_view`. Storing them here rather than in
    # the audit result is what lets the choice change after the run without
    # re-auditing, and what keeps the window's answer identical to
    # `--category`/`--confidence` on the same page.
    @property
    def categories(self) -> tuple[str, ...]:
        return self._categories

    def set_categories(self, value) -> None:
        chosen = tuple(value or ())
        if chosen == self._categories:
            return
        self._categories = chosen
        self.view_changed.emit()
        self.any_changed.emit()

    @property
    def confidence_floor(self) -> str:
        return self._confidence_floor

    def set_confidence_floor(self, value: str) -> None:
        if value == self._confidence_floor:
            return
        self._confidence_floor = value or ""
        self.view_changed.emit()
        self.any_changed.emit()

    @property
    def unsettled(self) -> bool:
        return self._unsettled

    def set_unsettled(self, value: bool) -> None:
        value = bool(value)
        if value == self._unsettled:
            return
        self._unsettled = value
        self.view_changed.emit()
        self.any_changed.emit()

    # -- site controls -----------------------------------------------------
    @property
    def site_controls(self) -> bool:
        return self._site_controls

    def set_site_controls(self, value: bool) -> None:
        value = bool(value)
        if value == self._site_controls:
            return
        self._site_controls = value
        self.any_changed.emit()

    # -- derived -----------------------------------------------------------
    @property
    def mode(self) -> str:
        return derive_mode(self._source, self._checks)

    @property
    def wants_provider(self) -> bool:
        return provider_visible(self._checks, self._methods)

    def _emit_mode_if_changed(self, old_mode: str) -> None:
        new_mode = self.mode
        if new_mode != old_mode:
            self.mode_changed.emit(new_mode)
