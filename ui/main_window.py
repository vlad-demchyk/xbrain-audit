from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, QUrl, Qt
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox,
    QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QSplitter,
    QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

import config
import suppression
from ui.app_state import AppState
from ui.view_model import MainViewModel
from audit import explanations as audit_explanations
from detectors.factory import DetectorFactory
from detectors.judges import PROVIDER_ORDER, judge_for_provider


def responsive_breakpoints():
    """The widths the audit runs at, imported lazily.

    Through a function rather than a module-level import because
    `audit.responsive` pulls in the driver, and the window must stay
    constructible on a machine where QtWebEngine is missing - the browser
    pass refuses itself with a sentence there, and a failed import at the
    top of this file would instead take the whole window down.
    """
    from audit.responsive import BREAKPOINTS
    return BREAKPOINTS
from analysis_modes import (
    CHECKS, CHECK_ACCESSIBILITY, CHECK_AI_PATTERNS, METHOD_AI, METHOD_EMBEDDING,
    METHOD_LOCAL, SOURCE_FILE, SOURCE_REPO, SOURCE_SITE,
    AnalysisRequest,
)
from i18n.translations import plural, t
from models import AnalysisResult, Confidence, RepoAnalysisResult, TextSpan
from repo_scanner import (
    DEFAULT_IGNORE_PATTERNS, SCOPE_BOTH, SCOPE_CONTENT, SCOPE_TECHNICAL,
    _parse_ignore_text,
)
from ui import theme
from ui.preview_loader import CapturedHtmlLoader
from ui.window_parts.account import (
    AccountMixin, _UNASKED, _ask_account_later,
)
from ui.window_parts.audit_panel import AuditPanelMixin
from ui.window_parts.bulk_rewrite import BulkRewriteMixin
from ui.window_parts.report_export import (
    ReportExportMixin,
)
from ui.window_parts.findings_panel import FindingsPanelMixin
from ui.window_parts.diagnosis_strip import DiagnosisStripMixin
from ui.window_parts.report_documents import RunDocumentsPanel
from ui.window_parts.repo_files import RepoFilesMixin
from ui.window_parts.run_comparison import RunComparisonPanel
from ui.window_parts.run_progress import (
    DONE, RUNNING, RunProgressPanel,
)
from ui.window_parts.runs_panel import RunsPanel
from ui.window_parts.setup_screen import SetupScreen
from ui.window_parts.shared import (
    MODE_AUDIT, MODE_FILE, MODE_REPO, MODE_WEB, _browser_url,
)
from ui.widgets import (
    EmptyState, FindingDelegate, FlowLayout, InlineValue, SeverityBar, divider, hairline, muted, panel, restyle,
)
from ui.worker import (
    AnalysisWorker, RepoAnalysisWorker, RewriteAllWorker,
)

#: How many characters a combo in the controls column reserves room for.
#: Every combo uses the same number: a column where each dropdown is a
#: different width reads as misalignment rather than as information, and the
#: longest label ("Claude Code session") does not have to fit - the popup
#: shows it in full.
_COMBO_CHARS = 10

#: The height of the top controls row when it fits on one line. Not a width
#: any more: the controls used to be a 268px column beside the results, and
#: are now a strip above them, so what they cost the body is height. The row
#: wraps to a second line rather than forcing the window wider - see
#: `_build_ui` - which is why this is what it fits into, not what it demands.
#:
#: The design draws this row at 44px, from a 28px control inside 8px of
#: padding. Qt reaches 52px at the same paddings, because its buttons and
#: labels are taller than the browser's at the same font size. Measured
#: rather than decreed: trimming the padding to land on 44 would distort the
#: design's spacing to pay for a difference in font metrics.
TOP_ROW_HEIGHT = 52
#: The width the Claude Design bundle (2026-08-24) draws the window at, and
#: the width it opens at. Not a minimum: the layout wraps below it on purpose.
DESIGN_WIDTH = 1300

#: Where a copy-scan confidence lands on the severity ramp. Three levels onto
#: four, by consequence rather than by position: a high-confidence flag is the
#: one worth acting on first. `LOW` never reaches this table - the window does
#: not count it as a finding, in the summary or in the status line.
_CONFIDENCE_LEVEL = {
    Confidence.HIGH: "critical",
    Confidence.MEDIUM: "serious",
}

# Below this window width, the detail panel collapses from a persistent
# third column into an inline panel that expands under the clicked list row.
WIDE_BREAKPOINT = 1000

# Below this narrower width, the preview column (site render or source code)
# gives way too, leaving only the findings list. Two breakpoints rather than
# one: a single cutoff made the window jump from three columns straight to a
# squeezed two, since a column that "stays visible" but no longer fits its
# own minimum width doesn't read as staying - it reads as broken. Columns
# now fold one at a time, widest-dependency first: the detail column (which
# has an inline fallback already) goes first, the preview column (which has
# no substitute) goes only when there truly isn't room for it.
MEDIUM_BREAKPOINT = 620

#: Shipped design assets: the mark, in both themes, and the application icon.
#: Kept in the repository rather than reached for in the xFormat checkout, so
#: the app is the same whether it runs from source or from a bundle.
ASSETS = Path(__file__).resolve().parent / "design" / "assets"


def _brand_pixmap(path: Path, widget) -> QPixmap:
    """The mark at 20 pt, sharp on whatever screen the window is on.

    Scaled to the widget's device pixel ratio and told about it, because a
    20x20 pixmap on a 2x display is drawn at 20 physical pixels and looks
    like a thumbnail of itself.
    """
    ratio = widget.devicePixelRatioF() if widget is not None else 1.0
    side = max(1, int(round(20 * ratio)))
    pixmap = QPixmap(str(path)).scaled(
        side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap

# Translated like everything else now. It was hardcoded English, with a
# comment explaining that the translations file belonged to someone else at
# the time - so the one button on the detail card that was not in the user's
# language sat next to eight that were.


class MainWindow(AccountMixin, AuditPanelMixin, DiagnosisStripMixin,
                 FindingsPanelMixin, RepoFilesMixin, ReportExportMixin,
                 BulkRewriteMixin, RunsPanel, QMainWindow):
    def __init__(self, palette=None):
        super().__init__()
        self.settings = config.Settings.load()
        self.lang = self.settings.ui_language
        # The xFormat design-system palette in force. Passed in by main.py so
        # the app is styled before any widget exists; resolved here as well so
        # the window is still usable when constructed directly (tests, or a
        # future second window).
        self.palette_tokens = palette or theme.current_palette(self.settings.theme)
        #: When the current run began. Set for real at the start of each run;
        #: None means the documents are being written without one, in which
        #: case `Timings` measures from itself, which is the best that can be
        #: said honestly.
        self._run_began = None
        #: The source being examined. What used to be `self.mode` is now
        #: derived from this and from the chosen checks, so downstream code
        #: that asks "which kind of run is this" still gets an answer.
        #: Cached answer to "is an xFormat account connected". `_UNASKED`
        #: rather than None because "not asked yet" and "signed out" are
        #: different states and only one of them is worth a round trip.
        self._account_cache = _UNASKED
        self.source = SOURCE_SITE
        # The run's state - which request ran, and which documents its fetch
        # produced - lives on the view model and is read from there through
        # the properties below. It used to be duplicated here, and the copy
        # on this side was never written to: `analyze()` records the request
        # on the view model, so the window's `_last_request` stayed None for
        # the life of the process. Three visible consequences, all reported
        # as separate faults: an audit's findings never appeared in a
        # both-questions run (the list gated them on this value), the browser
        # pass never ran (`_on_audit_finished` gates on it too), and the
        # extraction cache never hit, so changing the question re-crawled the
        # whole site. One owner instead.

        self.worker = None  # AnalysisWorker | RepoAnalysisWorker | None
        self._rewrite_worker: RewriteAllWorker | None = None
        # Every QThread this window starts is tracked here until it finishes.
        # Two reasons: a thread whose last Python reference is dropped gets
        # garbage-collected mid-run (which happened when a second "additional
        # analysis" click overwrote the first worker), and closeEvent needs
        # the full set so it can stop them — Qt aborts the process with
        # "QThread: Destroyed while thread is still running" otherwise.
        self._active_workers: list = []
        #: The repo's own dev server, started for the run in progress - a
        #: plain subprocess wrapper, not a QThread, so it outlives the worker
        #: that started it. Stopped when the analysis it was started for
        #: finishes (`_on_busy_changed`) and again on close, in case neither
        #: ever ran.
        self._devserver_proc = None
        self.result: AnalysisResult | RepoAnalysisResult | None = None
        #: The audit's own result, kept apart from `self.result` rather than
        #: unioned into it: the two carry different objects, and a single
        #: attribute holding either is a type check at every use site.
        self.audit_result = None
        self.drafts: dict[tuple, str] = {}  # (block_id, start, end) -> replacement text
        # A saved page or a folder can be dropped on the window (artboard 3o);
        # what happens then is `dropEvent` below.
        self.setAcceptDrops(True)

        self.current_preview_url: str | None = None       # web mode
        self.current_preview_path: str | None = None      # repo mode
        self._pending_highlight_dom_path: str | None = None
        #: The element's own opening tag, used when the selector no longer
        #: matches because the page's own scripts moved things around.
        self._pending_highlight_tag: str = ""
        self._expanded_item: QListWidgetItem | None = None
        self._last_selected_key: tuple | None = None
        self.wide_mode: bool | None = None  # forces first resizeEvent to initialize layout
        self.medium_mode: bool | None = None  # the second, narrower breakpoint; see MEDIUM_BREAKPOINT
        #: The person's own exclusion list. What a run skips is
        #: `effective_ignore_patterns`, which also carries what the detected
        #: stack says is not theirs - see `AppState.ignore_patterns_with_project`.
        self.repo_ignore_patterns: list[str] = _parse_ignore_text(DEFAULT_IGNORE_PATTERNS)

        # -- MVVM: centralized state and business logic --
        self.app_state = AppState(self)
        self.view_model = MainViewModel(self.app_state, self.settings, self)
        self.view_model.repo_ignore_patterns = self.repo_ignore_patterns

        self.resize(DESIGN_WIDTH, 800)
        #: `showEvent` widens the window once, if the language it opened in
        #: needs more than the design width to keep the controls on one line.
        self._opening_width_settled = False
        icon = ASSETS / "app-icon.png"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self._build_ui()
        self._retranslate_ui()
        self._wire_app_state()
        self._setup_shortcuts()
        self._sync_choices_to_state()
        self._update_layout_mode(force=True)
        _ask_account_later(self)

    # ------------------------------------------------------------------ UI

    def _wire_app_state(self) -> None:
        """Connect toolbar combos to AppState and subscribe to changes.

        This is the MVVM wiring: combos write to AppState, AppState
        validates and normalises, then signals flow back to update the UI.
        """
        # -- combos -> AppState --
        self.mode_combo.currentIndexChanged.connect(self._on_mode_to_state)
        self.checks_combo.currentIndexChanged.connect(self._on_checks_to_state)
        self.method_combo.currentIndexChanged.connect(self._on_method_to_state)
        self.method_combo.activated.connect(self._discard_pending_ai_method)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_to_state)

        # -- fields -> AppState --
        # As they are edited, not only when Analyze is pressed. The state was
        # pushed once, inside `_on_analyze_clicked`, so until the first run
        # `AppState.target` was empty - and anything that asked the view
        # model what the current request was got a request for nothing. That
        # is what made the extraction cache never match: the window compared
        # a request with a target against one without.
        for field_widget in (self.url_edit, self.repo_path_edit,
                             self.file_path_edit):
            field_widget.textChanged.connect(self._sync_target_to_state)
        self.depth_spin.valueChanged.connect(self.app_state.set_depth)
        self.scope_combo.currentIndexChanged.connect(self._sync_scope_to_state)

        # -- AppState -> UI updates --
        # Order matters, and it was wrong: `_apply_mode_visibility` reads the
        # legacy `self.source` copy, which `_sync_source_from_state` is what
        # updates. Connected the other way round, every source change painted
        # the window one source behind - choosing "HTML file" left the address
        # field and the depth on screen until some later change happened to
        # repaint. The copy is refreshed first, and then the window is drawn
        # from it.
        self.app_state.any_changed.connect(self._sync_source_from_state)
        self.app_state.any_changed.connect(self._apply_mode_visibility)
        # The account is asked for after the window is on screen, so the
        # answer arrives later than the combo that depends on it. Rebuilt when
        # it does; before this, an account found at startup did not add the AI
        # entries until the user signed in and out again.
        self.app_state.ai_available_changed.connect(
            lambda _ready: self._retranslate_choices())
        # Category and certainty are a view over findings that already exist,
        # so changing either repaints the list instead of re-auditing the
        # site. Nothing is re-fetched and nothing is re-parsed: that is the
        # whole difference between this and a run choice.
        self.app_state.view_changed.connect(self._on_view_narrowed)

        # -- ViewModel -> UI updates --
        self.view_model.busy_changed.connect(self._on_busy_changed)
        self.view_model.buttons_changed.connect(self._update_repo_buttons_enabled)
        self.view_model.error.connect(self._on_vm_error)
        self.view_model.status_message.connect(self.status_bar.showMessage)
        self.view_model.web_result_ready.connect(self._on_vm_web_result)
        self.view_model.repo_result_ready.connect(self._on_vm_repo_result)
        self.view_model.audit_result_ready.connect(self._on_vm_audit_result)
        self.view_model.rewrite_ready.connect(self._on_rewrite_finished)
        self.view_model.browser_pass_needed.connect(self._run_browser_pass)
        self.view_model.undo_outcome.connect(self._on_undo_outcome)
        self.view_model.download_choice_needed.connect(self._on_download_choice_needed)
        self.view_model.unicode_fixed.connect(self._on_unicode_fixed)

    def _on_view_narrowed(self) -> None:
        """Repaint what is shown of a finished audit, without running one."""
        if self.audit_result is None:
            return
        self._populate_audit_list()
        self._refresh_summary()
        self._update_audit_buttons_enabled()

    def _setup_shortcuts(self) -> None:
        """Keyboard shortcuts, and the keyboard itself.

        The shortcuts were here for power users. The rest of this - a tab
        order in reading order, a focus policy that includes buttons, a name
        on every unlabelled control - is not a convenience: without it the
        window cannot be operated without a mouse, and this tool reports
        exactly that as a critical finding on other people's pages.
        """
        # Esc = Cancel running analysis
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._on_cancel_clicked)
        # Ctrl+K / Cmd+K = Focus URL/path field
        focus_url = QShortcut(QKeySequence("Ctrl+K"), self)
        focus_url.activated.connect(self._focus_target_field)
        # Ctrl+Return = start the run from anywhere, including from inside a
        # text field, where plain Return means "I finished typing".
        run = QShortcut(QKeySequence("Ctrl+Return"), self)
        run.activated.connect(self._on_analyze_clicked)
        run_enter = QShortcut(QKeySequence("Ctrl+Enter"), self)
        run_enter.activated.connect(self._on_analyze_clicked)
        # Ctrl+, is the settings shortcut on every desktop that has one.
        settings = QShortcut(QKeySequence("Ctrl+,"), self)
        settings.activated.connect(self._on_settings_clicked)
        self._apply_keyboard_order()
        self._apply_accessible_names()

    def _focus_target_field(self) -> None:
        """Focus the input field for the current source."""
        if self.app_state.source == SOURCE_REPO:
            self.repo_path_edit.setFocus()
        elif self.app_state.source == SOURCE_FILE:
            self.file_path_edit.setFocus()
        else:
            self.url_edit.setFocus()

    def _on_mode_to_state(self, _idx: int) -> None:
        data = self.mode_combo.currentData()
        if data:
            self.app_state.set_source(data)
            # The target belongs to the source: switching from a site to a
            # folder means the state must now hold the folder's path, not the
            # URL still sitting in the other field.
            self._sync_target_to_state()

    def _sync_choices_to_state(self) -> None:
        """Push what the combos currently show into the state, once.

        `_fill_combo` blocks signals while it rebuilds - otherwise every
        refill would look like a user choice - so the first fill of the
        session never reached `AppState`. The state then answered with its own
        constructor defaults, and "both questions", which is what the combo
        showed, became "AI patterns only", which is what actually ran.
        """
        self._on_mode_to_state(0)
        self._on_checks_to_state(0)
        self._on_method_to_state(0)
        self._on_provider_to_state(0)
        self._sync_target_to_state()
        self._sync_scope_to_state()
        self.app_state.set_depth(self.depth_spin.value())

    def _sync_target_to_state(self, _text: str = "") -> None:
        self.app_state.set_target(self._current_target())
        self._detect_project()
        self._refresh_run_plan()
        # `set_target` carries no signal, so the setup screen would not learn
        # that a file was chosen or dropped - and its drop zone is the one
        # place that shows the file's own name and size.
        if getattr(self, "setup_screen", None) is not None:
            self.setup_screen.refresh_target()
            self.setup_screen.refresh()

    def _detect_project(self) -> None:
        """Read what the chosen folder is, once per folder.

        Cheap and bounded - marker files two levels down, no file contents -
        but it is filesystem work on the UI thread, so it runs when the path
        changes rather than on every repaint. Anything but a folder clears
        the profile: a stale one would go on excluding a previous project's
        `vendor/` from the next scan.
        """
        from analysis_modes import SOURCE_REPO

        # The chosen project when there is one: its `vendor/` is what this
        # run will skip, and the folder above it may be a different stack
        # entirely.
        path = (self._run_folder() if self.app_state.source == SOURCE_REPO
                else "")
        if path == getattr(self, "_profiled_path", None):
            return
        self._profiled_path = path
        if not path or not Path(path).is_dir():
            self.app_state.set_project(None)
            return
        import project_profile

        try:
            self.app_state.set_project(project_profile.detect(path))
        except OSError:
            # An unreadable folder is the scan's problem to report, not a
            # reason for the setup screen to fail to draw.
            self.app_state.set_project(None)

    def _refresh_run_plan(self) -> None:
        """What the current target asks the run to do, once per target.

        Filesystem work, like `_detect_project` above and for the same
        reason: it walks a directory looking for markers, so it runs when
        something it reads has changed rather than on every repaint. The key
        is the whole question - source, target and paired checkout - because
        the same folder means one thing as a target and another as the
        repository behind a site.
        """
        from analysis_modes import SOURCE_SITE

        key = (self.app_state.source, self.app_state.target,
               self.app_state.chosen_project, self.app_state.paired_repo)
        if key == getattr(self, "_planned_key", None):
            return
        self._planned_key = key
        import project_profile
        import run_profile

        try:
            # Built for what the run will read, but told about every project
            # in the folder the person picked: narrowing must not make the
            # list of things to narrow to disappear.
            folder = self.app_state.target
            projects = None
            if (self.app_state.chosen_project
                    and self.app_state.source != SOURCE_SITE):
                projects = project_profile.projects(folder)
            plan = run_profile.build(
                self.app_state.scan_target,
                forced_url=self.app_state.source == SOURCE_SITE,
                profile=self.app_state.project,
                projects=projects,
                repo=self.app_state.paired_repo)
        except OSError:
            # An unreadable folder is the scan's problem to report, not a
            # reason for the setup screen to fail to draw.
            plan = None
        self.app_state.set_run_plan(plan)
        self._apply_run_plan(plan)
        # `set_run_plan` is silent on purpose (see `AppState`), so the one
        # surface that draws the plan is refreshed here, by the call that
        # rebuilt it.
        if getattr(self, "setup_screen", None) is not None:
            self.setup_screen.refresh()

    def _apply_run_plan(self, plan) -> None:
        """Switch on what the target asks for - and only what nobody touched.

        The window is where this is allowed to happen, because the window
        shows the tick and the sentence under it before anything runs. The
        CLI deliberately does not; see `cli_impl.prerun.profile`.
        """
        self._ask_for_sign_in(plan is not None and plan.asks_for("sign_in"))
        if plan is None:
            return
        touched = self.app_state.profile_touched
        for item in plan.suggestions:
            if item.option in touched or not plan.applies(item.option):
                continue
            if item.option in ("render", "page_tree", "site_scope"):
                # SharePoint's recipes. No control on this window owns them,
                # so there is nothing to tick: the view model reads them at
                # run time through `cli_impl.auditpass.plan_sharepoint`, the
                # one function the CLI reads them through too. A second
                # copy here would be a second owner of the same three facts.
                continue
            if item.option == "web_parts":
                self.app_state.set_web_parts(bool(item.value), by_person=False)
            elif item.option == "devserver":
                # The window's own spelling of `--devserver`: start the
                # repository's server before the run. Only ticked, never
                # started here - starting is still a button.
                if not self.auto_devserver_check.isChecked():
                    self.auto_devserver_check.blockSignals(True)
                    self.auto_devserver_check.setChecked(True)
                    self.auto_devserver_check.blockSignals(False)
                    self.settings.auto_start_devserver = True

    def _ask_for_sign_in(self, asked: bool) -> None:
        """Point at "Sign in to the site" when the target cannot be read without it.

        SharePoint Online without a stored session answers every address
        with Microsoft's sign-in page; the run would audit that page and call
        it the site. The button turns primary and the status bar says why,
        so the next step is visible before anything runs.
        """
        button = getattr(self, "sign_in_site_btn", None)
        if button is None:
            return
        wanted = theme.CLASS_PRIMARY if asked else ""
        if (button.property("class") or "") != wanted:
            button.setProperty("class", wanted)
            button.style().unpolish(button)
            button.style().polish(button)
        if asked:
            import site_session

            host = site_session.host_of(self.app_state.target or "")
            self.status_bar.showMessage(
                t("sign_in_site_required", self.lang, host=host))

    def _sync_scope_to_state(self, _idx: int = 0) -> None:
        self.app_state.set_scope(self._repo_scope())

    def _on_checks_to_state(self, _idx: int) -> None:
        data = self.checks_combo.currentData()
        if data:
            self.app_state.set_checks(self._decode_choice(data, CHECKS))

    def _on_method_to_state(self, _idx: int) -> None:
        data = self.method_combo.currentData()
        if data:
            self.app_state.set_methods(self._decode_choice(data, (METHOD_LOCAL,)))

    def _on_provider_to_state(self, _idx: int) -> None:
        data = self.provider_combo.currentData()
        if data:
            self.app_state.set_provider(data)
            if data != self.settings.llm_provider:
                self.settings.llm_provider = data
                self.settings.save()
                self._refresh_account_control(refresh=True)

    def _sync_source_from_state(self) -> None:
        """Keep the legacy self.source in sync during the transition."""
        self.source = self.app_state.source
        index = self.mode_combo.findData(self.source)
        if index >= 0 and index != self.mode_combo.currentIndex():
            blocked = self.mode_combo.blockSignals(True)
            try:
                self.mode_combo.setCurrentIndex(index)
            finally:
                self.mode_combo.blockSignals(blocked)
        # Switching *to* a folder with a path already typed is the other way
        # a folder becomes current, and the path itself did not change.
        self._detect_project()
        self._refresh_run_plan()

    def _on_busy_changed(self, busy: bool) -> None:
        pending = getattr(self, "_account_checking", False) and getattr(self, "_pending_ai_methods", None)
        self.analyze_btn.setEnabled(not busy and not pending)
        self.cancel_btn.setEnabled(busy)
        if busy:
            self._begin_run_progress()
        else:
            self._stop_devserver_if_any()
            self._end_run_progress()

    def _begin_run_progress(self) -> None:
        """Declare the stages this run will have, and show them.

        Declared from the request rather than discovered as they happen: a
        stage that has not started is still on the list, which is what makes
        the panel say how much is left. Discovering them would grow the list
        as the run went, and a list that only ever shows the past cannot
        answer "how much longer".
        """
        import time

        # When the run began, so `timings.md` can report a total that is the
        # run's wall clock rather than the age of the object that writes it.
        self._run_began = time.monotonic()
        # The previous run's diagnoses describe the previous run. Leaving
        # them up over a new one is how "the server refused seven addresses"
        # comes to be read about a run that had no trouble at all.
        self.clear_diagnoses()
        self.run_progress.reset()
        self.run_progress.set_stages(self._stages_for_run())
        self.col1_stack.setCurrentIndex(2)
        # The width switcher belongs to the preview, and there is no preview
        # while the panel is up - three buttons that change nothing are worse
        # than no buttons.
        self.breakpoint_row.setVisible(False)
        self.col1_header.setText(t("progress_title", self.lang))

    def _end_run_progress(self) -> None:
        """Back to the preview once there is something to preview.

        The panel is left populated rather than cleared: the run that just
        finished is the one someone is about to ask questions about, and its
        log is the answer to most of them.
        """
        self._mark_remaining_stages_done()
        # `_apply_mode_visibility` owns the width switcher; calling it back
        # is how it returns to whatever the current source says it should be,
        # rather than to what it happened to be before the run. The header is
        # not its business, so it is put back too - the column would
        # otherwise keep saying "Run in progress" over a finished one.
        self._show_preview_column()

    def _stages_for_run(self) -> list:
        """Which stages this run actually has, in the order it does them."""
        lang = self.lang
        if self.source == SOURCE_REPO:
            # No crawl and no browser: a repository is read off disk.
            return [("scan", t("stage_scan", lang)),
                    ("detect", t("stage_detect", lang))]

        stages = [("crawl", t("stage_crawl", lang)),
                  ("extract", t("stage_extract", lang))]
        if CHECK_ACCESSIBILITY in self._chosen_checks():
            stages.append(("browser", t("stage_browser", lang)))
        if CHECK_AI_PATTERNS in self._chosen_checks():
            stages.append(("detect", t("stage_detect", lang)))
        return stages

    def _mark_remaining_stages_done(self) -> None:
        """A finished run has no stage still running.

        The workers report that a stage *started*, never that it ended, so
        the last one would sit on "running" forever after the run came back.
        Closing them here keeps the panel honest without asking four workers
        to each learn a new signal.
        """
        for key, _label in self._stages_for_run():
            if self.run_progress.stage_state(key) == RUNNING:
                self.run_progress.mark(key, DONE)

    def _advance_stage(self, key: str, detail: str, message: str) -> None:
        """One stage becomes the current one, and the log records why.

        Everything before it is done: the workers run their stages in order
        and only ever report the one they are in, so hearing about a later
        stage is the only signal that an earlier one finished.
        """
        keys = [stage for stage, _label in self._stages_for_run()]
        if key in keys:
            for earlier in keys[:keys.index(key)]:
                if self.run_progress.stage_state(earlier) != DONE:
                    self.run_progress.mark(earlier, DONE)
            self.run_progress.mark(key, RUNNING, detail)
        self.run_progress.add_log(message)

    def _show_run_documents(self, documents) -> None:
        """Hand the preview column over to what the run produced."""
        self.run_documents.show_documents(documents)
        self.run_documents.set_timings(self.run_progress.durations())
        self.col1_stack.setCurrentIndex(3)
        # Same reasoning as during the run: the width switcher constrains a
        # preview, and there is no preview under it while this panel is up.
        self.breakpoint_row.setVisible(False)
        self.col1_header.setText(t("documents_title", self.lang))

    def _show_run_comparison(self) -> None:
        """The last run and this one, side by side."""
        documents = self.run_documents.documents
        if documents is None or documents.comparison is None:
            return
        self.run_comparison.show_comparison(
            documents.comparison, documents.written.get("changes.md"))
        self.col1_stack.setCurrentIndex(4)
        self.breakpoint_row.setVisible(False)
        self.col1_header.setText(t("comparison_title", self.lang))

    # ------------------------------------------------------- setup vs work

    def _show_setup_if_nothing_has_run(self) -> None:
        """The setup screen until there is something to show instead.

        "Something" is a result, not a press: a run that fails on its first
        page should leave the person on the screen where the address is,
        which is the setup screen, rather than on three empty columns.
        """
        self.show_setup(self.result is None and self.audit_result is None)

    def show_setup(self, setup: bool) -> None:
        if setup == (self.body_stack.currentIndex() == 0):
            return
        self.body_stack.setCurrentIndex(0 if setup else 1)
        # The target fields move with the question being asked. On the setup
        # screen the address *is* the task and sits in the middle of it; in
        # the working layout it is one value on a line above the findings.
        if setup:
            self.setup_screen.target_layout.insertWidget(
                0, self.source_controls_stack, stretch=1)
            self.setup_screen.target_layout.addWidget(self.analyze_btn)
        else:
            self._strip_layout.insertWidget(self._strip_target_index,
                                            self.source_controls_stack)
            self._toolbar_actions.insertWidget(self._analyze_index,
                                               self.analyze_btn)
        # A `QStackedWidget` asks for the widest of *all* its pages, always,
        # so the setup screen's four cards would put a floor under the window
        # even while the working layout is showing - and the window has to be
        # able to shrink past its own narrowest breakpoint. Same fix as
        # `_size_stack_to_its_page`: the page that is not showing stops
        # contributing a size hint.
        for index in range(self.body_stack.count()):
            page = self.body_stack.widget(index)
            page.setSizePolicy(
                QSizePolicy.Policy.Preferred if index == self.body_stack.currentIndex()
                else QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred if index == self.body_stack.currentIndex()
                else QSizePolicy.Policy.Ignored)
        self.inline_strip.setVisible(not setup)
        # The top row keeps only what is about the window, not about the run:
        # the run is the screen. "More…" reveals the judge and the provider,
        # which are card 4; Cancel belongs to a run in flight and there is
        # none while this screen is up.
        self.advanced_toggle.setVisible(not setup)
        if setup:
            self.advanced_row.setVisible(False)
        self.cancel_btn.setVisible(not setup)
        # The depth is a number with no unit. In the strip a hairline and the
        # words around it said what it was; on its own in the target row it
        # needs its label back.
        self.depth_label.setVisible(setup and self.source == SOURCE_SITE)
        self._size_stack_to_its_page()
        if setup:
            self.setup_screen.refresh()

    def _show_preview_column(self) -> None:
        """Give the column back to the preview it belongs to.

        `_apply_mode_visibility` owns both the page and the head, so it is
        the one that puts the head back - naming the head here as well is
        how it came to say "Page preview" over a repository.
        """
        self._apply_mode_visibility()

    def _stop_devserver_if_any(self) -> None:
        if self._devserver_proc is not None:
            self._devserver_proc.stop()
            self._devserver_proc = None

    def _on_vm_error(self, message: str) -> None:
        QMessageBox.warning(self, "", message)

    def _on_advanced_toggle(self, checked: bool) -> None:
        """Show or hide the advanced toolbar controls (reader, method, provider)."""
        self.advanced_row.setVisible(checked)
        lang = self.lang
        self.advanced_toggle.setText(
            t("advanced_hide", lang) if checked else t("advanced_show", lang))

    def _show_field_error(self, field: QLineEdit, message: str) -> None:
        """Highlight field and show error in status bar."""
        field.setProperty("class", "field-error")
        field.style().unpolish(field)
        field.style().polish(field)
        self.status_bar.showMessage(message)

    def _clear_field_error(self, field: QLineEdit) -> None:
        """Clear error highlight when user types."""
        field.setProperty("class", "")
        field.style().unpolish(field)
        field.style().polish(field)
        self.status_bar.clearMessage()

    def _on_vm_web_result(self, result) -> None:
        """ViewModel finished a web scan - update the UI."""
        self.result = result
        self._populate_flagged_list()
        n_flags = sum(1 for s in result.spans if s.confidence != Confidence.LOW)
        self.status_bar.showMessage(
            t("status_done", self.lang, pages=len(result.pages),
              blocks=len(result.blocks()), flags=n_flags))
        self._update_repo_buttons_enabled()
        self._refresh_summary()

    def _on_vm_repo_result(self, result) -> None:
        """ViewModel finished a repo scan - update the UI."""
        self.result = result
        self._populate_flagged_list()
        n_flags = sum(1 for s in result.spans if s.confidence != Confidence.LOW)
        self.status_bar.showMessage(
            t("status_done_repo", self.lang, pages=len(result.files),
              blocks=len(result.blocks()), flags=n_flags))
        self._update_repo_buttons_enabled()
        self.refresh_repo_files()
        # A repository scan never showed the summary strip. It was not a
        # decision: this line was missing, and had it been here it would
        # have raised - `_summary_line` asked a `RepoAnalysisResult` for
        # `pages`, which is the web result's word.
        self._refresh_summary()

    #: How an audit severity is counted into the bar. The audit's four
    #: levels and the design's four-step ramp are the same four, in the same
    #: order of consequence, so this is an identity rather than a mapping -
    #: written out so that a fifth level added upstream fails visibly here
    #: instead of being silently dropped into the last segment.
    _SUMMARY_LEVELS = ("critical", "serious", "moderate", "minor")

    def _refresh_summary(self) -> None:
        """Fill the run summary strip, or hide it when there is no run.

        Counts come from whichever result the run produced. An audit carries
        real severities; a copy scan carries confidences, which are three
        levels rather than four, so they are placed on the ramp by
        consequence - a high-confidence flag is the one worth acting on
        first. A run that did both shows them together rather than picking
        one to report.

        `LOW` spans are left out for the same reason the status line leaves
        them out: they are below the threshold the window treats as a
        finding, and counting them here would put a number in the summary
        that the list underneath does not match.
        """
        counts = {level: 0 for level in self._SUMMARY_LEVELS}
        total = 0

        if self.audit_result is not None:
            # The same view the list is built from. Counting everything while
            # showing a narrowed list is how a summary comes to disagree with
            # the rows underneath it.
            for issue in self._issues_in_view():
                if issue.severity in counts:
                    counts[issue.severity] += 1
                    total += 1

        if self.result is not None:
            for span in self.result.spans:
                if span.confidence == Confidence.LOW:
                    continue
                counts[_CONFIDENCE_LEVEL.get(span.confidence, "moderate")] += 1
                total += 1

        if self.audit_result is None and self.result is None:
            self.summary_bar.setVisible(False)
            return

        self.severity_bar.set_counts(counts)
        self.summary_count.setText(t(
            "summary_findings", self.lang, count=total,
            noun=plural(total, self.lang, *self._FINDINGS_NOUN[self.lang])))
        self.summary_label.setText(self._summary_line())
        self.summary_bar.setVisible(True)

    #: The noun after the count, by language. Ukrainian needs all three
    #: forms; Italian and English only distinguish one from the rest, so the
    #: third is the same word - the calculation still runs and the table stays
    #: readable as one shape per language.
    _FINDINGS_NOUN = {
        "uk": ("знахідка", "знахідки", "знахідок"),
        "it": ("riscontro", "riscontri", "riscontri"),
        "en": ("finding", "findings", "findings"),
    }

    def _summary_line(self) -> str:
        """What was scanned, in the row's quietest ink.

        A repository is described by its own counts rather than by a page
        count it does not have (artboard 3f). The two skip numbers are the
        interesting half: a walk that read 412 files and skipped 38 of them
        by `.xanalyze-ignore` is a different result from one that read 450,
        and "no findings" means something different in each.
        """
        parts = [self._current_target() or ""]
        if self.audit_result is not None:
            parts.append(t("summary_documents", self.lang,
                           count=len(self.audit_result.documents)))
        elif isinstance(self.result, RepoAnalysisResult):
            parts.extend(self._repo_summary_parts(self.result))
        elif self.result is not None:
            parts.append(t("summary_pages", self.lang,
                           count=len(self.result.pages)))
        return " · ".join(part for part in parts if part)

    def _repo_summary_parts(self, result) -> list:
        """Files read, files deliberately skipped, and where the findings are."""
        walk = result.diagnostics
        # `files_read` when the walk recorded it, and the length of the list
        # otherwise: a result assembled by something that did not fill in
        # diagnostics would report zero files read next to its own findings,
        # which is a contradiction on one line.
        read = walk.files_read or len(result.files)
        parts = [t("summary_files", self.lang, count=read)]
        if walk.skipped_ignored:
            parts.append(t("summary_skipped_ignored", self.lang,
                           count=walk.skipped_ignored))
        flagged = {span.block_id for span in result.spans
                   if span.confidence != Confidence.LOW}
        blocks = {block.block_id: block for block in result.blocks()}
        files = {blocks[block_id].file_path for block_id in flagged
                 if block_id in blocks}
        if files:
            parts.append(t("summary_in_files", self.lang, count=len(files)))
        return parts

    def _on_vm_audit_result(self, result) -> None:
        """ViewModel finished an audit - update the UI."""
        self.audit_result = result
        self._populate_audit_list()
        first = next((d for d in result.documents if not d.error), None)
        if first is not None:
            address = _browser_url(first.source)
            self.current_preview_url = address
            # The run already owns this revision. Loading its URL again just
            # to paint the preview made an honest two-pass analysis issue a
            # third page request, and the preview could then show a newer
            # revision than the findings beside it. Use the captured
            # extraction whatever its size (`ui/preview_loader.py` owns Qt's
            # setHtml limit); only a page that was never captured is loaded
            # from its address.
            snapshot = self.view_model._snapshot
            preview = next(
                (page.raw_html for page in (snapshot.pages if snapshot else ())
                 if page.url in (first.source, address) and page.raw_html), "")
            if preview:
                self.site_loader.load(preview, QUrl(address))
                self.mirror_preview_to_comparison(html=preview,
                                                  base=QUrl(address))
            else:
                self.site_loader.navigate(QUrl(address))
                self.mirror_preview_to_comparison(QUrl(address))
        self._update_audit_buttons_enabled()
        self.diagnose_finished_run()
        self._refresh_summary()
        self.status_bar.showMessage(
            audit_explanations.summary_line(result, self.lang))

    def _on_rewrite_finished(self, drafts: dict) -> None:
        """ViewModel finished bulk rewrite - update drafts and refresh list."""
        for key, text in drafts.items():
            self.drafts[key] = text
        self._populate_flagged_list()

    def _build_brand_header(self) -> QWidget:
        """The mark, and nothing else that needs a line of its own.

        This used to be a stacked block - mark, name, tagline, account - which
        is what a 268px column had room for. In a top row it has room for one
        thing, and the mark is the thing worth keeping: it is what says at a
        glance that this is one application in a family. The name is beside it
        only while there is width for it.

        `brand_tagline`, `account_label` and `account_btn` are still built and
        still named, because `_retranslate_ui` and `_refresh_account_control`
        write to all three. The tagline is simply not shown here - a sentence
        explaining the app belongs on the empty state, which is where someone
        who needs it is actually looking. The account moves to the right end
        of the row; see `_build_account_control`.
        """

        bar = QWidget()
        bar.setProperty("class", theme.CLASS_BRAND)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.palette_tokens.space_sm)

        # One file for both themes. The mark is a single blue on
        # transparency, so it reads on either canvas and there is no light
        # copy to go invisible on a dark one - which is what the two SVGs
        # existed to work around.
        mark = ASSETS / "logo-small.png"
        if mark.is_file():
            self.brand_mark = QLabel()
            self.brand_mark.setFixedSize(QSize(20, 20))
            self.brand_mark.setPixmap(_brand_pixmap(mark, self.brand_mark))
            layout.addWidget(self.brand_mark)
        else:
            self.brand_mark = None

        self.brand_name = QLabel("XAnalyze")
        self.brand_name.setProperty("class", theme.CLASS_HEADING)
        layout.addWidget(self.brand_name)

        # Built, named, written to by `_retranslate_ui` - and not in the row.
        self.brand_tagline = muted()
        self.brand_tagline.setWordWrap(True)
        self.brand_tagline.setVisible(False)
        return bar

    def _build_account_control(self) -> QWidget:
        """The account, at the right end of the top row.

        The xFormat account belongs where it can be seen. The selected AI
        provider has its own independent readiness probe.

        The label keeps its text for `_refresh_account_control` and for the
        tooltip, but the row shows the button alone - a whole sentence about
        who is signed in cannot share a line with five selectors.
        """
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.palette_tokens.space_1)

        self.account_label = muted()
        self.account_label.setVisible(False)
        layout.addWidget(self.account_label)

        self.account_btn = QPushButton()
        self.account_btn.setProperty("class", theme.CLASS_QUIET)
        self.account_btn.clicked.connect(self._on_account_clicked)
        layout.addWidget(self.account_btn)

        # Drawn from what is known, which at build time is nothing. The real
        # answer is asked once the window exists; see `_ask_account_later`.
        self._refresh_account_control(ask=False)
        return box

    #: Which Lucide icon stands for which action. Kept next to the row it
    #: draws rather than in `ui/icons.py`: the file knows how to render an
    #: icon, this knows what the buttons mean.
    _ACTION_ICONS = (
        ("fix_unicode_btn", "eraser"),
        ("generate_list_btn", "list"),
        ("auto_replace_btn", "replace"),
        ("fix_on_disk_btn", "file-pen"),
        ("undo_fix_btn", "undo-2"),
        ("download_btn", "download"),
    )

    def _apply_action_icons(self) -> None:
        """Draw the action row as icons in the current theme's ink.

        Re-run on every theme change for the same reason `_repaint_brand` is:
        the icons are rasterised in one colour, and the colour that reads on
        a light sheet disappears on a dark one.
        """
        from ui import icons as icon_set

        if not icon_set.available():
            return
        ratio = self.devicePixelRatioF() or 1.0
        size = icon_set.DEFAULT_SIZE
        for attribute, name in self._ACTION_ICONS:
            button = getattr(self, attribute, None)
            if button is None:
                continue
            drawn = icon_set.icon(name, self.palette_tokens.text, size, ratio)
            if drawn is None:
                continue
            button.setIcon(drawn)
            button.setIconSize(QSize(size, size))
            # Cleared only now: until an icon is in hand, the label is the
            # only thing identifying the button.
            button.setText("")

    def _repaint_brand(self) -> None:
        """Redraw the mark after a theme change.

        It no longer swaps files - one mark serves both canvases - but the
        pixmap is still re-made, because a theme change can follow a move to
        a screen with a different pixel ratio and a stale pixmap is a blurry
        one.
        """
        if getattr(self, "brand_mark", None) is None:
            return
        mark = ASSETS / "logo-small.png"
        if mark.is_file():
            self.brand_mark.setPixmap(_brand_pixmap(mark, self.brand_mark))

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        # A left column of controls beside the results, not a strip of them
        # above. Every control is the same object it was as a toolbar - the
        # panels, the mixins and the tests all address these widgets by name -
        # only the geometry changed: a form reads top to bottom, and a row
        # that has to wrap to fit eleven controls reads in no direction at
        # all. The sidebar also gives each control room for its label, which
        # the wrapping row could only afford by abbreviating them away.
        # A top row of controls above the results, not a column beside them.
        # The column existed because eleven *labelled* controls cannot share a
        # row: four combo boxes side by side need about 520px, and a row that
        # wraps to fit them reads in no direction at all. The design answers
        # that objection rather than argues with it - every selector is now an
        # inline value (`ui/widgets.py::InlineValue`), which is as wide as the
        # word it shows instead of as wide as its longest choice, so the whole
        # set reads as one sentence and fits. What the column cost was the
        # width it took from the results for the entire life of the window,
        # to hold a form that is read once per run.
        root = QVBoxLayout(central)
        gap = self.palette_tokens.space_sm
        root.setContentsMargins(gap, gap, gap, gap)
        root.setSpacing(gap)

        # The controls live on their own surface rather than floating on the
        # page canvas — the same "monolithic card on a warm canvas" the web
        # app uses to separate chrome from content.
        self.toolbar = QWidget()
        self.toolbar.setProperty("class", theme.CLASS_TOP_ROW)
        self.toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.toolbar.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Minimum)
        # A flow layout, not a box. A `QHBoxLayout` hands the widget the sum
        # of its children's minimum widths as its own, and a top row is as
        # wide as the window - so the row set a 1271px floor under the whole
        # window and made both narrow layouts unreachable. That is the exact
        # failure the sidebar was once shaped to avoid, arriving from the
        # other direction.
        #
        # `FlowLayout` wraps instead of pushing, which is also what the design
        # asks for at 1000px: the row keeps the target and the action, and the
        # rest goes onto a second line rather than off the screen.
        controls = FlowLayout(self.toolbar, margin=0,
                              spacing=self.palette_tokens.space_sm)
        controls.setContentsMargins(10, 8, 10, 8)
        #: Kept so the window can ask, once it is on screen, how wide this row
        #: needs to be to stay on one line in the language it is showing. See
        #: `showEvent` and `P-18`.
        self.controls_layout = controls
        self.toolbar.setMinimumWidth(0)

        # A header strip with the mark and the product name. Not decoration:
        # this is one application in a family, and the thing that says so at a
        # glance is the mark, in the same indigo, in the same place as the web
        # app puts it.
        controls.addWidget(self._build_brand_header())

        self.mode_label = QLabel()
        self.mode_combo = InlineValue()
        self.mode_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.mode_combo.setMinimumContentsLength(_COMBO_CHARS)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        # --- web-mode controls ---
        # Stacked, not in a row. Four controls side by side need about 520px
        # to stay readable, which is twice the column's width - the row fitted
        # only by squeezing the URL field down to a few characters.
        web_controls = QWidget()
        web_layout = QHBoxLayout(web_controls)
        web_layout.setContentsMargins(0, 0, 0, 0)
        web_layout.setSpacing(self.palette_tokens.space_1)
        self.url_label = QLabel()
        self.url_edit = QLineEdit()
        self.url_edit.textChanged.connect(lambda: self._clear_field_error(self.url_edit))
        self.depth_label = QLabel()
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(0, 5)
        self.depth_spin.setValue(self.settings.crawl_depth)
        for w in (self.url_label, self.url_edit, self.depth_label, self.depth_spin):
            web_layout.addWidget(w)
        # The URL is the only flexible control in this row. Without an
        # explicit stretch, a recalculation after other setup controls change
        # can leave a large blank gap before Analyze and clip the address.
        web_layout.setStretch(web_layout.indexOf(self.url_edit), 1)
        self.url_error = muted()
        self.url_error.setProperty("class", "field-error")
        self.url_error.setVisible(False)

        # --- repo-mode controls ---
        repo_controls = QWidget()
        repo_layout = QHBoxLayout(repo_controls)
        repo_layout.setContentsMargins(0, 0, 0, 0)
        repo_layout.setSpacing(self.palette_tokens.space_1)
        self.repo_path_edit = QLineEdit()
        self.repo_path_edit.textChanged.connect(lambda: self._clear_field_error(self.repo_path_edit))
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        self.exclusions_btn = QPushButton()
        self.exclusions_btn.clicked.connect(self._on_exclusions_clicked)
        self.scope_label = QLabel()
        self.scope_combo = InlineValue()
        self.scope_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.scope_combo.setMinimumContentsLength(_COMBO_CHARS)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)
        repo_layout.addWidget(self.repo_path_edit)
        # These two are short and belong together - the only pair worth a row.
        repo_buttons = QWidget()
        repo_buttons_layout = QHBoxLayout(repo_buttons)
        repo_buttons_layout.setContentsMargins(0, 0, 0, 0)
        repo_buttons_layout.setSpacing(self.palette_tokens.space_1)
        repo_buttons_layout.addWidget(self.browse_btn)
        repo_buttons_layout.addWidget(self.exclusions_btn)
        repo_layout.addWidget(repo_buttons)
        repo_layout.addWidget(self.scope_label)
        repo_layout.addWidget(self.scope_combo)
        self.repo_error = muted()
        self.repo_error.setProperty("class", "field-error")
        self.repo_error.setVisible(False)

        # Off by default (`Settings.auto_start_devserver`): a repo's own dev
        # server may already be running in another terminal, and Analyze
        # starting a second one on a different port is a confusing outcome,
        # not a helpful one. Checking this restores the one-click behaviour;
        # unchecked, the button below is the explicit, one-time equivalent.
        #
        # Not placed in `repo_controls`: that page is one of three sharing
        # `source_controls_stack`'s width budget (`_size_stack_to_its_page`
        # explains the constraint), and it is already the tightest of the
        # three - two more widgets there reintroduced the exact regression
        # this file's own tests exist to catch (`toolbar.height() 52 -> 89`
        # even in site mode, `repo_controls` hidden or not). The advanced row
        # is a widget of its own, invisible by default, so it cannot
        # contaminate a measurement of the row it is not part of.
        # --- the two run parameters the CLI had and the window did not ---
        #
        # `--repo`: the checkout that serves this site. A finding on a page
        # names the page, which is where to look and never where to edit; with
        # a checkout paired, every passage that also exists in it carries the
        # file and the line. See `repo_pairing`.
        #
        # `--within`: read only this part of the page. A delivered SharePoint
        # web part or an embedded widget sits inside somebody else's document,
        # and auditing the whole page reports their markup as the deliverer's
        # problem. A selector that matches nothing is refused rather than
        # returning zero findings - see `audit.within`.
        #
        # Both live in the advanced row rather than the target strip: that row
        # is measured by `tests/test_window_shell.py` and two more widgets in
        # it put a floor under the whole window (see `auto_devserver_check`).
        self.paired_repo_edit = QLineEdit()
        self.paired_repo_edit.setText(self.settings.last_paired_repo or "")
        self.paired_repo_edit.textChanged.connect(self._on_paired_repo_changed)
        self.paired_repo_btn = QPushButton()
        self.paired_repo_btn.clicked.connect(self._on_browse_paired_repo)
        self.within_edit = QLineEdit()
        self.within_edit.textChanged.connect(self._on_within_changed)

        # Half of what is worth auditing is behind a login, and the only way
        # in that does not involve this app handling anybody's credentials is
        # for the person to sign in themselves, in a real browser window. See
        # `ui.site_sign_in` and `site_session`.
        self.sign_in_site_btn = QPushButton()
        self.sign_in_site_btn.clicked.connect(self._on_sign_in_site)

        self.auto_devserver_check = QCheckBox()
        self.auto_devserver_check.setChecked(self.settings.auto_start_devserver)
        self.auto_devserver_check.toggled.connect(self._on_auto_devserver_toggled)
        self.start_server_btn = QPushButton()
        self.start_server_btn.clicked.connect(self._on_start_server_clicked)

        # --- single-file controls ---
        file_controls = QWidget()
        file_layout = QHBoxLayout(file_controls)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(self.palette_tokens.space_1)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.textChanged.connect(lambda: self._clear_field_error(self.file_path_edit))
        self.file_browse_btn = QPushButton()
        self.file_browse_btn.clicked.connect(self._on_browse_file_clicked)
        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(self.file_browse_btn)
        self.file_error = muted()
        self.file_error.setProperty("class", "field-error")
        self.file_error.setVisible(False)

        self.source_controls_stack = QStackedWidget()
        self.source_controls_stack.addWidget(web_controls)   # index 0
        self.source_controls_stack.addWidget(repo_controls)  # index 1
        self.source_controls_stack.addWidget(file_controls)  # index 2

        # Which account reads the text, not which detector class to build.
        # The dropdown used to list backends by name, which made the method
        # combo beside it decorative: the backend carried the decision, so
        # "AI" with an offline backend selected ran the offline engine and
        # said nothing. The method decides *what runs* now, and this decides
        # *who pays* - see `_detector_for_request`.
        self.provider_label = QLabel()
        self.provider_combo = InlineValue()
        # Provider labels can be long ("Claude Code session"). Without this,
        # the combo's minimum size hint is set to fit its longest item, which
        # alone can keep the whole window from ever shrinking below ~1300px
        # and would silently defeat the narrow-window layout below.
        self.provider_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.provider_combo.setMinimumContentsLength(_COMBO_CHARS)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._populate_providers()

        # Loading every page in a real browser costs seconds per page and is
        # the only way to see what JavaScript rendered, so it is the user's
        # call rather than a default. Off by default: a first audit should be
        # fast, and the static pass already reports most of what is wrong.
        # --- the three choices that used to be one -------------------------
        #
        # Reading, question and judge are independent of each other and of the
        # source. Kept as three combos rather than one list of combinations:
        # the combinations multiply (3 x 3 x 3), and the point of separating
        # them is that the user changes one without restating the other two.
        self.checks_label = QLabel()
        self.checks_combo = InlineValue()
        self.method_label = QLabel()
        self.method_combo = InlineValue()
        for combo in (self.checks_combo, self.method_combo):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(_COMBO_CHARS)
            combo.currentIndexChanged.connect(self._on_choice_changed)

        # --- advanced controls (hidden by default) ---
        self.advanced_toggle = QPushButton()
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.clicked.connect(self._on_advanced_toggle)
        self.advanced_toggle.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.analyze_btn = QPushButton()
        self.analyze_btn.setDefault(True)
        self.analyze_btn.clicked.connect(self._on_analyze_clicked)
        self.cancel_btn = QPushButton()
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.cancel_btn.setEnabled(False)
        self.settings_btn = QPushButton()
        self.settings_btn.clicked.connect(self._on_settings_clicked)

        # The sidebar keeps only what changes per scan. Language, API keys and
        # endpoint mapping live in the Settings dialog, which is what stops
        # this column from growing unusable.
        self.source_controls_stack.setMinimumWidth(0)
        self.source_controls_stack.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # The separate label widgets are built, translated and hidden: every
        # selector now carries its own label inside itself, so putting the
        # QLabel in the row too would print the word twice. They stay because
        # `_retranslate_ui` writes to them and because the settings dialog
        # reads their text, and because a label that is merely not shown is a
        # smaller change than one that no longer exists.
        for spare in (self.mode_label, self.checks_label, self.method_label,
                      self.provider_label, self.scope_label,
                      self.url_label, self.depth_label):
            spare.setVisible(False)

        # One filled block holding the whole sentence, with hairlines between
        # its clauses - the design's own shape for it. Grouping them is not
        # decoration: a caret floating on the surface reads as a stray glyph,
        # while the same caret inside a filled strip reads as "this word can
        # be changed".
        #
        # `setMinimumWidth(0)` and the shrinkable field inside it are what
        # keep this from putting a floor under the window again: a box layout
        # hands its parent the sum of its children's minimums, and this box
        # now holds most of the row. `test_window_shell.py` measures it.
        self.inline_strip = QWidget()
        self.inline_strip.setProperty("class", theme.CLASS_INSET)
        self.inline_strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        strip = QHBoxLayout(self.inline_strip)
        strip.setContentsMargins(10, 5, 10, 5)
        strip.setSpacing(7)
        strip.addWidget(self.mode_combo)
        strip.addWidget(hairline())
        strip.addWidget(self.source_controls_stack)
        strip.addWidget(hairline())
        strip.addWidget(self.checks_combo)
        # Kept so the target fields can be lent to the setup screen and given
        # back. They are one set of widgets with one set of pickers; a second
        # address field on the setup screen would be a second place for the
        # same value to be wrong in.
        self._strip_layout = strip
        self._strip_target_index = strip.indexOf(self.source_controls_stack)
        self.inline_strip.setMinimumWidth(0)
        controls.addWidget(self.inline_strip)

        # The advanced controls: a container rather than a second row, so
        # showing them extends the column instead of pushing the results
        # down. Same widget, same name, same `setVisible` from
        # `_on_advanced_toggle`.
        self.advanced_row = QWidget()
        adv_layout = QHBoxLayout(self.advanced_row)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(self.palette_tokens.space_sm)
        for w in (self.method_label, self.method_combo,
                  self.provider_label, self.provider_combo,
                  self.paired_repo_edit, self.paired_repo_btn,
                  self.within_edit, self.sign_in_site_btn,
                  self.auto_devserver_check, self.start_server_btn):
            adv_layout.addWidget(w)
        self.advanced_row.setVisible(False)

        controls.addWidget(self.advanced_toggle)
        controls.addWidget(self.advanced_row)

        # The catalogue of runs, below the controls and above the buttons:
        # it is about work that already happened, so it must not sit between
        # the target and Analyze, and it must not be the thing that scrolls
        # off the bottom either.
        # Previous runs are a list, and a list cannot live in a one-line row.
        # It moves behind a button, which is where the design puts it too: the
        # row says what the *next* run will be, and history is one click away
        # rather than permanently occupying a third of a column.
        #
        # A `Qt.Popup` rather than a dialog: it closes when you click away,
        # which is the behaviour of every other "show me the list" control in
        # the window, and it does not steal focus from the row behind it.
        self.runs_popup = QWidget(self, Qt.WindowType.Popup)
        self.runs_popup.setProperty("class", theme.CLASS_SURFACE)
        self.runs_popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        popup_layout = QVBoxLayout(self.runs_popup)
        popup_layout.setContentsMargins(gap, gap, gap, gap)
        popup_layout.addWidget(self._build_runs_panel())
        # A floor, not a fixed width. The catalogue is a table now (artboard
        # 3c) and a table's width follows its columns; pinning it to the 320
        # the old two-line list wanted would clip the action column, which is
        # the half of a row that does anything. `_on_runs_clicked` caps it
        # against the window, so it can grow without leaving the screen.
        self.runs_popup.setMinimumWidth(320)

        self.runs_btn = QPushButton()
        self.runs_btn.setProperty("class", theme.CLASS_QUIET)
        # Settings is the same kind of button as Runs - a way out of the
        # row, not an action on the run being set up - and the design
        # draws them alike. It was the only bordered button up there
        # beside Analyze, which made it read as a second primary.
        self.settings_btn.setProperty("class", theme.CLASS_QUIET)
        self.runs_btn.clicked.connect(self._on_runs_clicked)

        # Remembered for the same reason as the target fields: the button
        # moves to the setup screen and comes back.
        self._toolbar_actions = controls
        self._analyze_index = controls.count()
        controls.addWidget(self.analyze_btn)
        controls.addWidget(self.cancel_btn)
        controls.addWidget(self.runs_btn)
        controls.addWidget(self.settings_btn)
        controls.addWidget(self._build_account_control())
        self.analyze_btn.setProperty("class", theme.CLASS_PRIMARY)

        # The top row is a fixed strip, not a scrolled column: it holds one
        # line of inline values, so there is nothing for it to scroll. The
        # scroll area that used to wrap the sidebar is gone with it - it
        # existed because a column of stacked combo boxes grew taller than a
        # laptop window, which a single row cannot do.
        #
        # `sidebar_scroll` and `body_splitter` are gone too. The body no
        # longer shares its width with a form, so there are no two panes to
        # split; the columns splitter is now the only one, and it is added
        # straight to the root box below.
        theme.soft_shadow(self.toolbar, self.palette_tokens)
        root.addWidget(self.toolbar)

        # The run summary: what was scanned, how the findings divide between
        # severities, and how many there are. Its own strip under the
        # controls, as the design draws it, and hidden until there is a run
        # to summarise - an empty bar beside "0 findings" is a row of
        # furniture that says nothing.
        #
        # The bar answers what the count cannot: 27 findings that are all
        # minor and 27 that are all critical are the same number and a
        # different afternoon.
        self.summary_bar = QWidget()
        self.summary_bar.setProperty("class", theme.CLASS_SURFACE)
        self.summary_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.summary_bar.setSizePolicy(QSizePolicy.Policy.Preferred,
                                       QSizePolicy.Policy.Fixed)
        summary = QHBoxLayout(self.summary_bar)
        summary.setContentsMargins(12, 7, 12, 7)
        summary.setSpacing(14)
        self.summary_label = muted()
        summary.addWidget(self.summary_label)
        self.severity_bar = SeverityBar(self.palette_tokens)
        summary.addWidget(self.severity_bar)
        self.summary_count = QLabel()
        summary.addWidget(self.summary_count)
        summary.addStretch(1)
        self.summary_bar.setVisible(False)
        theme.soft_shadow(self.summary_bar, self.palette_tokens)
        root.addWidget(self.summary_bar)

        # Under the summary and above the results, because it is about the
        # run rather than about a finding: "the server refused seven of
        # twelve addresses" belongs beside "27 findings", not inside the
        # list of the 27.
        root.addWidget(self._build_diagnosis_strip())

        # --- three-column body -------------------------------------------------
        self.columns_splitter = QSplitter(Qt.Orientation.Horizontal)
        # A gap between the zones, not a seam: panels that touch read as one
        # wide panel with lines drawn in it, which is exactly the flat-sheet
        # look the surfaces exist to avoid.
        self.columns_splitter.setHandleWidth(gap)
        self.columns_splitter.setChildrenCollapsible(False)

        # Two bodies, one at a time: the setup screen while nothing has run
        # (artboard 3b), the working layout once something has (3a). The
        # window used to open on the working one with all three columns
        # empty, which is the settings of a run written in eight words across
        # the top of a blank window.
        self.body_stack = QStackedWidget()
        self.setup_screen = SetupScreen(self.app_state, self.palette_tokens,
                                        self.lang)
        # The screen asks for a file; the picker and the field it fills stay
        # here, so there is still one place a chosen path can be wrong in.
        self.setup_screen.choose_file_requested.connect(
            self._on_browse_file_clicked)
        # The plan the setup screen draws was already built - by the startup
        # sync, before this screen existed - and the cache below would have
        # made the next call a no-op. So the screen is handed it now, or the
        # controls that depend on it appear on the first unrelated click
        # instead of at startup, and the window's minimum width moves under
        # somebody who only pressed a breakpoint button.
        self._planned_key = None
        self._refresh_run_plan()
        self.body_stack.addWidget(self.setup_screen)       # index 0
        self.body_stack.addWidget(self.columns_splitter)   # index 1
        # Starts on the working layout so that the first `show_setup(True)`
        # is a real change and actually moves the fields across. It ran as a
        # no-op when the stack already sat on index 0, which left the setup
        # screen with an empty space where the address belongs.
        self.body_stack.setCurrentIndex(1)
        root.addWidget(self.body_stack, stretch=1)

        # Column 1: graphical copy of the site OR the raw source file being
        # analyzed, depending on mode.
        # Each column is a zone with its own surface and its own titled head,
        # the way the web app separates one part of a page from another. A Qt
        # window that paints three regions of one flat sheet reads as a
        # different product, however correct its colours are.
        self.col1, col1_layout, self.col1_header = panel()
        col1_layout.setContentsMargins(10, 10, 10, 10)

        self.col1_stack = QStackedWidget()
        self.site_view = QWebEngineView()
        # Through the loader, not `loadFinished`: for a large captured page
        # Qt finishes loading an empty bootstrap before the page is written
        # into it, and a highlight run then would find nothing.
        self.site_loader = CapturedHtmlLoader(self.site_view)
        self.site_loader.ready.connect(self._on_preview_loaded)
        # Chromium paints white until the page has something to draw, which in
        # a dark theme reads as a broken pane for the second or two a real site
        # takes to arrive.
        self.site_view.page().setBackgroundColor(QColor(self.palette_tokens.page_bg))
        self.col1_stack.addWidget(self.site_view)  # index 0: web

        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        mono = self.code_view.font()
        # The design system's mono face, with Qt resolving its own fallback
        # when that family isn't installed.
        mono.setFamily(self.palette_tokens.font_mono)
        self.code_view.setFont(mono)

        # The files over the file. Which files a repository scan found
        # things in is the question a repository is actually asking, and the
        # column used to answer a narrower one: whichever file the selected
        # finding happened to be in. Split rather than stacked, because the
        # two are read together - the shape of the work, and the passage.
        self.repo_split = QSplitter(Qt.Orientation.Vertical)
        self.repo_split.addWidget(self._build_repo_files())
        self.repo_split.addWidget(self.code_view)
        # Nearly even. The file list is the navigation on a repository -
        # it is how you get anywhere - so giving the preview twice its space
        # makes the thing you steer with the smaller of the two.
        self.repo_split.setStretchFactor(0, 1)
        self.repo_split.setStretchFactor(1, 1)
        self.repo_split.setSizes([320, 380])
        self.repo_split.setChildrenCollapsible(False)
        self.col1_stack.addWidget(self.repo_split)  # index 1: repo

        # Index 2: what the run is doing, shown in the preview column while
        # there is nothing to preview yet. The column is empty for the whole
        # crawl otherwise, and the run's own progress is the most useful
        # thing that can stand there - it is the question being asked at
        # exactly that moment.
        self.run_progress = RunProgressPanel(self.palette_tokens, self.lang)
        self.col1_stack.addWidget(self.run_progress)  # index 2: a run in flight

        # Index 3: what the run produced (artboard 3h). The same column
        # again, and for the same reason: right after a run ends, "where are
        # the documents" is the question being asked, and the preview is
        # what the person has just spent the whole run looking at.
        self.run_documents = RunDocumentsPanel(self.palette_tokens, self.lang)
        self.run_documents.back_btn.clicked.connect(self._show_preview_column)
        self.run_documents.comparison_btn.clicked.connect(
            self._show_run_comparison)
        self.col1_stack.addWidget(self.run_documents)  # index 3: what it produced

        # Index 4: this run against the last one (artboard 3n). Reached from
        # the documents rather than shown instead of them: the comparison is
        # a reading of `changes.md`, and the folder is where that lives.
        self.run_comparison = RunComparisonPanel(self.palette_tokens, self.lang)
        self.run_comparison.back_btn.clicked.connect(self._show_preview_column)
        self.col1_stack.addWidget(self.run_comparison)  # index 4: what changed

        # Index 5: nothing opened yet. Before this the column opened on an
        # empty `QWebEngineView`, which paints its own background over the
        # panel - a canvas-coloured rectangle with square corners where the
        # design has a surface. It also said nothing: a blank browser is not
        # a state, it is the absence of one, and this window has a component
        # for saying which absence it is.
        self.preview_empty = EmptyState(self.palette_tokens)
        self.col1_stack.addWidget(self.preview_empty)  # index 5: nothing yet

        # The width switcher, above the preview rather than beside it: the
        # audit now runs at three widths (see `audit/responsive.py`), and a
        # finding labelled "found at mobile only" is not checkable in a
        # preview that is always desktop-shaped. These buttons constrain the
        # preview itself, so the reader sees the layout the finding came from.
        self.breakpoint_row = QWidget()
        # Wrapping, for the third time and the same reason: a `QHBoxLayout`
        # hands its parent the sum of its children's minimums, so three
        # buttons here were a 278px floor under the preview column and
        # therefore under the whole window - which left five pixels of slack
        # under the narrowest breakpoint the window is required to reach.
        breakpoint_layout = FlowLayout(self.breakpoint_row, margin=0,
                                       spacing=self.palette_tokens.space_sm)
        self.breakpoint_buttons = {}
        #: Which width the preview is pinned to, or None for the full column.
        self._preview_width_name = None
        for name, width, _height in responsive_breakpoints():
            button = QPushButton()
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, chosen=name: self._on_breakpoint_clicked(chosen))
            breakpoint_layout.addWidget(button)
            self.breakpoint_buttons[name] = (button, width)
        # Artboard 3o asks for two widths *at once*, and the switcher above
        # can only ever answer one at a time: a person checking "this only
        # breaks on mobile" has to flip back and forth and hold the desktop
        # layout in their head. Side by side, the difference is the thing on
        # screen rather than the thing being remembered.
        self.compare_widths_btn = QPushButton()
        self.compare_widths_btn.setCheckable(True)
        self.compare_widths_btn.clicked.connect(self._on_compare_widths)
        breakpoint_layout.addWidget(self.compare_widths_btn)
        #: The second view, built on first use. A `QWebEngineView` is a
        #: renderer process; making one for a comparison nobody asked for
        #: would cost every user of this window for the sake of a button.
        self.compare_view = None
        self.compare_pane = None
        col1_layout.addWidget(self.breakpoint_row)

        # A row rather than the stack alone, so the comparison pane can sit
        # beside it without the stack having to know about it.
        preview_row = QWidget()
        self._preview_row = QHBoxLayout(preview_row)
        self._preview_row.setContentsMargins(0, 0, 0, 0)
        self._preview_row.setSpacing(self.palette_tokens.space_1)
        self._preview_row.addWidget(self.col1_stack, 1)
        col1_layout.addWidget(preview_row, stretch=1)
        # Added to the splitter below rather than here. The columns are built
        # preview-first because the preview owns the width switcher and the
        # stack the other panels are pushed onto, but they are *read* findings
        # first, as artboard 3a lays them out - the list is what the window is
        # for, and the preview is what a selected finding is checked against.

        # Column 2: the list of flagged passages (+ repo-mode bulk actions).
        col2, col2_layout, self.flagged_header = panel()
        col2_layout.setContentsMargins(1, 0, 1, 1)

        self.flagged_list = QListWidget()
        self.flagged_list.setMouseTracking(True)  # so the delegate sees hover
        self.finding_delegate = FindingDelegate(self.palette_tokens, self.flagged_list)
        self.flagged_list.setItemDelegate(self.finding_delegate)
        self.flagged_list.itemClicked.connect(self._on_flagged_item_clicked)

        # An empty findings list is ambiguous — clean, not-yet-scanned and
        # "the crawler got nothing" all look identical as a blank list — so
        # the list is one page of a stack and an explanation is the other.
        self.empty_state = EmptyState(self.palette_tokens)
        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(self.flagged_list)   # index 0
        self.results_stack.addWidget(self.empty_state)    # index 1
        col2_layout.addWidget(self.results_stack, stretch=1)

        # Bulk actions. The unicode fix is offline and free, so it's offered
        # in both modes; the two LLM-backed buttons are repo-only.
        self.bulk_actions_row = QWidget()
        # Up to six buttons here, and which ones depends on the question asked.
        # A flow keeps their labels readable at any width instead of clipping
        # them all equally.
        bulk_layout = FlowLayout(self.bulk_actions_row,
                                 spacing=self.palette_tokens.space_sm)
        bulk_layout.setContentsMargins(12, 10, 12, 12)
        self.fix_unicode_btn = QPushButton()
        self.fix_unicode_btn.clicked.connect(self._on_fix_unicode_clicked)
        self.generate_list_btn = QPushButton()
        self.generate_list_btn.clicked.connect(self._on_generate_list_clicked)
        self.auto_replace_btn = QPushButton()
        self.auto_replace_btn.clicked.connect(self._on_auto_replace_clicked)
        # Writing an audit correction back into the file, and taking it back.
        # Both live next to each other on purpose: an action that edits
        # someone's source is only comfortable to press when the way out is
        # visible at the same moment.
        self.fix_on_disk_btn = QPushButton()
        self.fix_on_disk_btn.clicked.connect(self._on_fix_on_disk_clicked)
        self.undo_fix_btn = QPushButton()
        self.undo_fix_btn.clicked.connect(self._on_undo_fix_clicked)
        # One entry point for two different documents. They stay two
        # documents - an agent briefing (`cli._write_report`'s markdown/JSON)
        # and the branded PDF/HTML a person reads - because they are read by
        # different readers; what was merged is the *button*, since two
        # exports side by side made the row ask a question ("which of these
        # two is the report?") before the user had decided to export at all.
        self.download_btn = QPushButton()
        self.download_btn.clicked.connect(self._on_download_clicked)
        for b in (self.fix_unicode_btn, self.generate_list_btn, self.auto_replace_btn,
                  self.fix_on_disk_btn, self.undo_fix_btn, self.download_btn):
            bulk_layout.addWidget(b)
        col2_layout.addWidget(divider())
        col2_layout.addWidget(self.bulk_actions_row)
        # Kept as an alias so the repo-only visibility logic reads clearly.
        self.repo_actions_row = self.bulk_actions_row

        # Reading order: findings, then the preview they point into, then the
        # detail of the one that is selected.
        self.columns_splitter.addWidget(col2)
        self.columns_splitter.addWidget(self.col1)

        # Column 3 (wide layout only): input box + actions for the selected passage.
        # A panel with a head, like the other two columns. It was a bare
        # widget, so its contents floated directly on the page canvas while
        # its neighbours sat on titled surfaces - which read as a column that
        # had failed to render rather than as a third zone.
        self.col3, self.detail_layout, self.detail_header = panel()
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(0)
        self.columns_splitter.addWidget(self.col3)

        # The preview is the widest: it holds a rendered page at up to three
        # widths, and the other two hold text that wraps.
        self.columns_splitter.setSizes([380, 450, 380])
        self._show_setup_if_nothing_has_run()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._apply_mode_visibility()
        # A blank white pane is the one thing the empty state exists to
        # prevent, and it was exactly what the window opened with: the state
        # was only ever shown after a scan produced no rows, never before the
        # first scan.
        self._show_empty_state()

    def _populate_providers(self) -> None:
        """Offer every account, including ones not connected yet.

        Not filtered down to what is currently usable: the method combo
        already refuses the AI pass when nothing can pay for it, and a list
        that silently loses an entry is a worse answer than one whose entry
        explains, when picked, what it needs.
        """
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        for name in PROVIDER_ORDER:
            self.provider_combo.addItem(t(f"provider_{name}", self.lang), userData=name)
        idx = self.provider_combo.findData(self.settings.llm_provider)
        self.provider_combo.setCurrentIndex(max(idx, 0))
        self.provider_combo.blockSignals(False)

    def _on_provider_changed(self, _idx: int = 0) -> None:
        """The toolbar and the Settings dialog change one setting, not two.

        Writing it straight through means a provider picked here is the one
        `ai status`, the rewrite calls and the Settings dialog all report -
        two places holding two answers to "whose account pays" is how the
        window came to disagree with the CLI in the first place.
        """
        chosen = self.provider_combo.currentData()
        if chosen and chosen != self.settings.llm_provider:
            self.settings.llm_provider = chosen
            self.settings.save()
            self._account_cache = _UNASKED
            self._refresh_account_control(refresh=True)
            self._retranslate_choices()

    #: The order a keyboard walks the window in, by attribute name.
    #:
    #: Qt's default is creation order, and the columns here are *built*
    #: preview-first (the preview owns the width switcher and the stack the
    #: other panels are pushed onto) while they are *read* findings-first -
    #: which is stated in this file already and was true of the tab order
    #: too, so Tab from the address field landed in the preview pane rather
    #: than on Analyze. This is the reading order instead: say what to look
    #: at, say what to look for, start, then walk the results.
    KEYBOARD_ORDER = (
        "mode_combo", "url_edit", "depth_spin", "repo_path_edit", "browse_btn",
        "exclusions_btn", "scope_combo", "file_path_edit", "file_browse_btn",
        "checks_combo", "advanced_toggle", "method_combo", "provider_combo",
        "paired_repo_edit", "paired_repo_btn", "within_edit",
        "sign_in_site_btn", "auto_devserver_check", "start_server_btn",
        "analyze_btn", "cancel_btn", "settings_btn",
        "flagged_list",
    )

    def _apply_keyboard_order(self) -> None:
        """Chain the controls in reading order, and let every one take focus.

        `QLineEdit` and `QComboBox` are focusable by default; a `QPushButton`
        on macOS is **not** - Qt follows the platform, where Tab visits text
        fields and lists only. That default is right for a Mac app whose
        buttons are all one click away and wrong for a window whose main
        action is a button, so the policy is set explicitly here.
        """
        previous = None
        for name in self.KEYBOARD_ORDER:
            widget = getattr(self, name, None)
            if widget is None:
                continue
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            if previous is not None:
                self.setTabOrder(previous, widget)
            previous = widget

    #: What a control is called for someone who cannot see it: attribute name
    #: -> translation key. Anything with a visible label of its own is absent
    #: on purpose - a screen reader would then say the name twice.
    ACCESSIBLE_NAMES = {
        "url_edit": "url_label_full",
        "depth_spin": "depth_label_full",
        "repo_path_edit": "repo_path_placeholder",
        "file_path_edit": "tui_target_path",
        "paired_repo_edit": "paired_repo_full",
        "within_edit": "within_full",
        "sign_in_site_btn": "sign_in_site_full",
        "flagged_list": "flagged_list_header",
        "mode_combo": "mode_label_full",
        "checks_combo": "checks_label_full",
        "method_combo": "method_label_full",
        "provider_combo": "provider_label_full",
        "scope_combo": "scope_label_full",
    }

    def _apply_accessible_names(self) -> None:
        """Give every unlabelled control a name a screen reader can read.

        This tool reports `control-name` as a critical finding on other
        people's pages. Its own window had none: measured before this, zero
        calls to `setAccessibleName` in the whole of `ui/`.
        """
        for name, key in self.ACCESSIBLE_NAMES.items():
            widget = getattr(self, name, None)
            if widget is None:
                continue
            text = t(key, self.lang)
            if text and text != key:
                widget.setAccessibleName(text)
                widget.setAccessibleDescription(text)

    def _retranslate_ui(self) -> None:
        lang = self.lang
        self.setWindowTitle(t("app_title", lang))
        # The preview column's head is owned by `_apply_mode_visibility`,
        # because what it says depends on the source. Called from here too,
        # or a language change leaves that one head in the old language.
        self._apply_mode_visibility()
        self.run_progress.retranslate(lang)
        self.run_documents.retranslate(lang)
        self.repo_files.retranslate(lang)
        self.run_comparison.retranslate(lang)
        self.mode_label.setText(t("mode_label", lang))
        self.mode_combo.set_label(t("mode_label", lang))
        self.brand_tagline.setText(t("app_tagline", lang))
        current_mode_data = self.mode_combo.currentData() if self.mode_combo.count() else None
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        # One entry per source, not per source-and-question pair: "site audit"
        # and "web page" were the same site asked two questions, and offering
        # them as separate sources meant choosing the source twice.
        self.mode_combo.addItem(t("source_site", lang), userData=SOURCE_SITE)
        self.mode_combo.addItem(t("source_repo", lang), userData=SOURCE_REPO)
        self.mode_combo.addItem(t("source_file", lang), userData=SOURCE_FILE)
        idx = self.mode_combo.findData(current_mode_data or self.source)
        self.mode_combo.setCurrentIndex(max(idx, 0))
        self.mode_combo.blockSignals(False)
        self._retranslate_choices()
        self._refresh_account_control(ask=False)

        self.url_label.setText(t("url_label", lang))
        self.url_label.setToolTip(t("url_label_full", lang))
        self.url_edit.setPlaceholderText(t("url_placeholder", lang))
        self.depth_label.setText(t("depth_label", lang))
        self.depth_label.setToolTip(t("depth_label_full", lang))
        self.repo_path_edit.setPlaceholderText(t("repo_path_placeholder", lang))
        self.browse_btn.setText(t("browse_button", lang))
        self.exclusions_btn.setText(t("scan_options_button", lang))
        self.exclusions_btn.setToolTip(t("scan_options_button_full", lang))
        self.auto_devserver_check.setText(t("auto_devserver_check", lang))
        self.paired_repo_edit.setPlaceholderText(t("paired_repo_placeholder", lang))
        self.paired_repo_edit.setToolTip(t("paired_repo_full", lang))
        self.paired_repo_btn.setText(t("browse_button", lang))
        self.paired_repo_btn.setToolTip(t("paired_repo_full", lang))
        self._refresh_sign_in_button()
        self.within_edit.setPlaceholderText(t("within_placeholder", lang))
        self.within_edit.setToolTip(t("within_full", lang))
        self.auto_devserver_check.setToolTip(t("auto_devserver_check_full", lang))
        self.start_server_btn.setText(t("start_server_button", lang))
        self.start_server_btn.setToolTip(t("start_server_button_full", lang))

        self.scope_label.setText(t("scope_label", lang))
        self.scope_combo.set_label(t("scope_label", lang))
        self.scope_label.setToolTip(t("scope_label_full", lang))
        current_scope = self.scope_combo.currentData() if self.scope_combo.count() else None
        self.scope_combo.blockSignals(True)
        self.scope_combo.clear()
        for value in (SCOPE_CONTENT, SCOPE_TECHNICAL, SCOPE_BOTH):
            self.scope_combo.addItem(t(f"scope_{value}", lang), userData=value)
            self.scope_combo.setItemData(
                self.scope_combo.count() - 1,
                t(f"scope_{value}_full", lang),
                Qt.ItemDataRole.ToolTipRole,
            )
        idx = self.scope_combo.findData(current_scope or self.settings.repo_scope)
        self.scope_combo.setCurrentIndex(max(idx, 0))
        self.scope_combo.blockSignals(False)
        self.scope_combo.setToolTip(t(f"scope_{self._repo_scope()}_full", lang))

        self.compare_widths_btn.setText(t("compare_widths", self.lang))
        self.compare_widths_btn.setToolTip(t("compare_widths_full", self.lang))
        for name, (button, width) in self.breakpoint_buttons.items():
            # The number, as artboard 3a writes it. "desktop" and "mobile"
            # name a device; the page lays out to a width, and the width is
            # the thing a finding labelled "found at 390 only" is checked
            # against. The word stays in the tooltip.
            label = t(f"breakpoint_{name}", lang)
            button.setText(str(width))
            button.setToolTip(t("breakpoint_tooltip", lang,
                                name=label, width=width))
        # Refilled, not just relabelled: the entries themselves are words.
        self._populate_providers()
        self.provider_label.setText(t("provider_label", lang))
        self.provider_combo.set_label(t("provider_label", lang))
        self.provider_label.setToolTip(t("provider_label_full", lang))
        self.provider_combo.setToolTip(t("provider_label_full", lang))
        self.file_path_edit.setPlaceholderText(t("file_path_placeholder", lang))
        self.file_browse_btn.setText(t("browse_button", lang))
        self.checks_label.setText(t("checks_label", lang))
        self.checks_combo.set_label(t("checks_label", lang))
        self.checks_label.setToolTip(t("checks_label_full", lang))
        self.method_label.setText(t("method_label", lang))
        self.method_combo.set_label(t("method_label", lang))
        self.method_label.setToolTip(t("method_label_full", lang))
        for button, label_key, mnemonic_key in (
            (self.analyze_btn, "analyze_button", "analyze_button_mnemonic"),
            (self.cancel_btn, "cancel_button", "cancel_button_mnemonic"),
            (self.settings_btn, "settings_button", "settings_button_mnemonic"),
        ):
            label = t(label_key, lang)
            button.setText(t(mnemonic_key, lang))
            # The marker is Qt syntax. Give assistive technology the plain
            # translated action name rather than relying on button text.
            button.setAccessibleName(label)
            button.setAccessibleDescription(label)
        # The button that opens the run history. The panel's own heading is
        # "Runs:", with the colon that introduces a list under it - on a
        # button the colon is a promise of something that is not there, so
        # it is stripped rather than given a second translation key to drift
        # apart from the first.
        self.runs_btn.setText(t("runs_title", lang).rstrip(":").strip())
        self.advanced_toggle.setText(
            t("advanced_hide", lang) if self.advanced_toggle.isChecked()
            else t("advanced_show", lang))
        self.flagged_header.setText(t("flagged_list_header", lang))
        self.detail_header.setText(t("detail_header", lang))
        # The action row is icons, and the words move into the tooltips: six
        # buttons of six different widths read as a heap rather than as a row,
        # and their labels are long in every language this app speaks. The
        # label is still set - and then cleared by `_apply_action_icons` only
        # if an icon was actually found - so a build without the icon files
        # degrades to the readable version instead of to six blank squares.
        for button, key, tip in (
            (self.fix_unicode_btn, "fix_unicode_button", "fix_unicode_tooltip"),
            (self.generate_list_btn, "generate_list_button", ""),
            (self.auto_replace_btn, "auto_replace_button", ""),
            (self.fix_on_disk_btn, "fix_on_disk_button", "fix_on_disk_tooltip"),
            (self.undo_fix_btn, "undo_fix_button", "undo_fix_tooltip"),
            (self.download_btn, "download_button", "download_tooltip"),
        ):
            label = t(key, lang)
            button.setText(label)
            # Tooltip: the long explanation where there is one, the label
            # itself where there is not - an icon with no tooltip at all is
            # a button that cannot be identified.
            button.setToolTip(f"{label} - {t(tip, lang)}" if tip else label)
        self._apply_action_icons()
        self.status_bar.showMessage(t("status_idle", lang))
        self._reset_detail_panel()

        # The names a screen reader announces are strings like any other,
        # so they follow the interface language instead of being fixed at
        # construction in whatever language that happened to be.
        self._apply_accessible_names()

    def _on_breakpoint_clicked(self, chosen: str) -> None:
        """Show the preview at one width, or back at full width.

        Clicking the pressed button again releases it: the widths are a
        temporary way of looking at the page, not a mode to get stuck in.
        """
        # Decided from what was selected before, not from the button's own
        # checked state: a checkable button has already toggled itself by the
        # time this runs when a person clicks it, and has not when the same
        # action is invoked from anywhere else. Reading the remembered choice
        # makes both paths agree.
        release = self._preview_width_name == chosen
        self._preview_width_name = None if release else chosen
        for name, (other, _width) in self.breakpoint_buttons.items():
            other.setChecked(name == self._preview_width_name)
        width = self.breakpoint_buttons[chosen][1]
        self._apply_preview_width(None if release else width)

    def _on_compare_widths(self, checked: bool) -> None:
        """Show the page at the widest and the narrowest width, side by side.

        Which two: the first and the last of `audit.responsive.BREAKPOINTS`,
        which is desktop against the 320px reflow check - the pair a
        responsive failure is nearly always between. The width buttons keep
        working on the left-hand pane, so a person can put any width against
        the reflow one.
        """
        if checked and self.compare_pane is None:
            self._build_compare_pane()
        if self.compare_pane is None:
            self.compare_widths_btn.setChecked(False)
            return
        self.compare_pane.setVisible(checked)
        if checked:
            address = self.current_preview_url or ""
            if address:
                self.compare_loader.navigate(QUrl(address))
            elif self.site_view.url().isValid():
                self.compare_loader.navigate(self.site_view.url())
        self._fit_preview_zoom()

    def _build_compare_pane(self) -> None:
        """The second view, and the column that holds it."""
        from PySide6.QtWidgets import QVBoxLayout

        widths = responsive_breakpoints()
        if len(widths) < 2:
            return
        self._compare_width = widths[-1][1]
        self.compare_view = QWebEngineView()
        self.compare_loader = CapturedHtmlLoader(self.compare_view)
        self.compare_view.page().setBackgroundColor(
            QColor(self.palette_tokens.page_bg))
        self.compare_pane = QWidget()
        pane = QVBoxLayout(self.compare_pane)
        pane.setContentsMargins(0, 0, 0, 0)
        pane.setSpacing(self.palette_tokens.space_1)
        caption = muted(t("compare_widths_caption", self.lang,
                          width=self._compare_width))
        caption.setWordWrap(True)
        pane.addWidget(caption)
        pane.addWidget(self.compare_view, 1)
        self.compare_pane.setVisible(False)
        # Beside the stack, inside the same column: the comparison is a way
        # of looking at the preview, not a fourth panel to switch to.
        self._preview_row.addWidget(self.compare_pane, 1)

    def _apply_preview_width(self, width) -> None:
        """Show the page as it lays out at one viewport width.

        Zoom, not size. Pinning the widget with `setMinimumWidth(1440)` does
        make the page lay out at 1440, but a minimum is a demand on the
        parent: the column could not be narrower than that, so choosing
        "desktop" widened the whole window instead of changing anything
        inside it. The simulation has to happen in the column that is there,
        the way a browser's device toolbar does it.

        Scaling down leaves `window.innerWidth` at the chosen width - CSS
        pixels are what the zoom factor divides - so media queries answer for
        the breakpoint while the pixels on screen stay inside the column.
        Never scaled *up*: a 390px layout blown up to fill 500px of column is
        a picture of a phone, not a page at 390.
        """
        self._preview_width = int(width) if width else None
        self._fit_preview_zoom()

    def _fit_preview_zoom(self) -> None:
        """Re-fit the simulated width into whatever width the column has now.

        Called on every resize as well as on every choice: the column is one
        pane of a splitter, so its width changes without the chosen
        breakpoint changing at all.
        """
        pane = getattr(self, "compare_pane", None)
        if pane is not None and pane.isVisible():
            self._fit_compare_zoom()
        chosen = getattr(self, "_preview_width", None)
        if not chosen:
            self.site_view.setMaximumWidth(16777215)  # Qt's own "no maximum"
            self.site_view.setZoomFactor(1.0)
            return
        available = self.col1_stack.width() or self.site_view.width()
        if available <= 0:
            return
        if available >= chosen:
            # Room to spare: hold the widget itself to the width, which lays
            # the page out at exactly it. A *maximum* is safe where the
            # minimum was not - it never asks the parent for anything.
            self.site_view.setMaximumWidth(chosen)
            self.site_view.setZoomFactor(1.0)
        else:
            # Narrower than the breakpoint. Scale instead, so the page still
            # lays out at the chosen width rather than at whatever the column
            # happens to be - which would be a different breakpoint wearing
            # the label of this one.
            self.site_view.setMaximumWidth(16777215)
            self.site_view.setZoomFactor(available / chosen)

    def mirror_preview_to_comparison(self, url=None, html: str = "",
                                     base=None) -> None:
        """Give the comparison pane whatever the main preview was just given.

        Called by the places that load the preview, so the two panes are the
        same page at two widths rather than two pages. Silent when the pane
        does not exist or is hidden, which is the normal case.
        """
        pane = getattr(self, "compare_pane", None)
        if pane is None or not pane.isVisible() or self.compare_view is None:
            return
        if html:
            self.compare_loader.load(html, base or QUrl())
        elif url is not None:
            self.compare_loader.navigate(
                url if isinstance(url, QUrl) else QUrl(url))
        self._fit_compare_zoom()

    def _fit_compare_zoom(self) -> None:
        """Fit the narrow view into its half of the column.

        Same rule as the single preview: scale down so the page still lays
        out at the width it is labelled with, never up - a 320px layout blown
        up to fill 500px is a picture of a phone rather than a page at 320.
        """
        if self.compare_view is None:
            return
        available = self.compare_pane.width()
        if available <= 0:
            return
        chosen = getattr(self, "_compare_width", 320) or 320
        if available >= chosen:
            self.compare_view.setMaximumWidth(chosen)
            self.compare_view.setZoomFactor(1.0)
        else:
            self.compare_view.setMaximumWidth(16777215)
            self.compare_view.setZoomFactor(available / chosen)

    def _repaint_preview_background(self) -> None:
        self.site_view.page().setBackgroundColor(QColor(self.palette_tokens.page_bg))

    def apply_palette(self, palette) -> None:
        """Adopt a new design-system palette at runtime.

        Called when the theme is switched in Settings. The style sheet is
        applied application-wide by `theme.apply_theme`; what has to happen
        here is everything QSS cannot reach — the delegate that paints the
        findings rows, and the monospaced face on the code preview.
        """
        self.palette_tokens = palette
        self.finding_delegate.set_palette(palette)
        # Both of these paint their own inks, per state and per row, which
        # is exactly what QSS cannot reach - a theme switch would otherwise
        # leave the stage list and the document list in the old sheet's
        # colours, on the new sheet's background.
        self.run_progress.apply_palette(palette)
        self.run_documents.apply_palette(palette)
        self.run_comparison.apply_palette(palette)
        self._repaint_preview_background()
        self._repaint_brand()
        self._apply_action_icons()
        mono = self.code_view.font()
        mono.setFamily(palette.font_mono)
        self.code_view.setFont(mono)
        self.empty_state.apply_palette(palette)
        for widget in (self.toolbar, self.empty_state):
            restyle(widget)
        self.flagged_list.viewport().update()

    def _on_runs_clicked(self) -> None:
        """Show the run history under the button that asked for it."""
        if self.runs_popup.isVisible():
            self.runs_popup.hide()
            return
        # Resized, not `adjustSize`d. `adjustSize` clamps a top-level widget
        # against the screen and settled on a width narrower than the popup
        # asked for, which clipped the action column off the right of the
        # table - the half of a row that does anything.
        hint = self.runs_popup.sizeHint()
        cap = max(320, self.width() - 40)
        self.runs_popup.resize(min(hint.width(), cap), hint.height())
        corner = self.runs_btn.mapToGlobal(
            QPoint(0, self.runs_btn.height() + self.palette_tokens.space_1))
        # Kept on screen. The popup opens under a button near the right edge
        # of a wrapping row, and a table wide enough to hold six columns
        # would otherwise open with half of itself past the window - with the
        # action column, which is the far right one, as the half that goes.
        right = self.mapToGlobal(QPoint(self.width(), 0)).x()
        corner.setX(min(corner.x(), right - self.runs_popup.width() - 8))
        self.runs_popup.move(corner)
        self.runs_popup.show()

    def _on_settings_clicked(self) -> None:
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.settings, self.lang, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Language may have changed in the dialog; re-apply everything.
            self.lang = self.settings.ui_language
            self._retranslate_ui()
            self._populate_flagged_list()
            self._refresh_account_control(refresh=True)

    # ------------------------------------------------------- responsive layout

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Open on one line, in whatever language the interface is in.

        The design draws the controls strip as one line at 1300px, and that
        measurement was taken in English. Ukrainian - the default language -
        needs 1330px for the same six controls, so the window as written
        opened already wrapped for its default user, and Italian sat 20px from
        doing the same. Nothing was broken by it: the row wraps rather than
        clips, which is the designed answer to a narrow window. It was simply
        never the width the design asks for.

        Measured rather than tabulated per language, because a translation
        changing length is not an event anyone would remember to re-measure
        after - which is how this went unseen. `toolbar.width()` subtracted
        from the window's gives the chrome around it, so the deficit converts
        straight into window pixels.

        Once, and only from the opening size: a window the person has already
        resized, or one restored from a session, is theirs.
        """
        super().showEvent(event)
        if self._opening_width_settled:
            return
        self._opening_width_settled = True
        if self.width() != DESIGN_WIDTH:
            return
        needed = self.controls_layout.one_line_width()
        available = self.toolbar.width()
        if available and needed > available:
            self.resize(DESIGN_WIDTH + (needed - available), self.height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._update_layout_mode()
        # The simulated width is a fraction of the column's width, and the
        # column follows the window.
        self._fit_preview_zoom()

    # ------------------------------------------------------ thread lifecycle

    def _track_worker(self, worker) -> None:
        """Hold a reference until the thread finishes, so it can't be
        garbage-collected mid-run, and so closeEvent can find it."""
        self._active_workers.append(worker)
        worker.finished.connect(lambda: self._untrack_worker(worker))

    def _untrack_worker(self, worker) -> None:
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._stop_account_checks()
        self._stop_devserver_if_any()
        self.view_model.shutdown()
        for worker in list(self._active_workers):
            if hasattr(worker, "cancel"):
                worker.cancel()
        for worker in list(self._active_workers):
            if worker.isRunning():
                worker.wait(5000)
        self._persist_settings()
        self._release_site_view()
        super().closeEvent(event)

    def _release_site_view(self) -> None:
        """Let go of the preview's `QWebEnginePage` before its profile.

        `audit/driver.close()` spells out why the order matters; this window
        had the same hazard and left it to interpreter teardown, where Qt's
        ordering guarantees are gone. `tests/test_window_shell.py` passed
        every assertion and then aborted the process (SIGABRT alone, SIGSEGV
        in a full run, printing "Release of profile requested but
        WebEnginePage still not deleted" once per window built), which is why
        the release gate in `.github/workflows/release.yml` would have failed
        on its exit code with nothing failing in it.
        """
        from PySide6.QtCore import QCoreApplication, QEvent

        view = getattr(self, "site_view", None)
        if view is None:
            return
        # Set to None *before* anything else: Qt can deliver `closeEvent`
        # twice, and the second pass would reach a half-released view.
        self.site_view = None
        # `setPage(None)` is the whole release. Unlike `audit/driver`, which
        # builds `QWebEnginePage(profile, None)` and therefore owns it, a bare
        # `QWebEngineView` creates and **owns** its page - so Qt destroys the
        # old page inside `setPage`, and calling `deleteLater()` on the
        # Python wrapper afterwards raises "Internal C++ object already
        # deleted". That mistake cost 44 red tests before this comment.
        view.setPage(None)
        view.deleteLater()
        app = QCoreApplication.instance()
        if app is not None:
            # `DeferredDelete` explicitly: a plain `processEvents` does not run
            # deferred deletions posted at another event-loop level, so the
            # view would still be alive when the profile goes.
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)

    def _persist_settings(self) -> None:
        self.settings.ui_language = self.lang
        self.settings.crawl_depth = self.depth_spin.value()
        self.settings.repo_scope = self._repo_scope()
        # The method, not a detector name: what to run is the user's choice,
        # and which class implements it is derived from it (see
        # `_detector_for_request`).
        method = self.method_combo.currentData()
        if method:
            self.settings.default_method = method
        provider = self.provider_combo.currentData()
        if provider:
            self.settings.llm_provider = provider
        self.settings.save()

    def _update_layout_mode(self, force: bool = False) -> None:
        wide = self.width() >= WIDE_BREAKPOINT
        medium = self.width() >= MEDIUM_BREAKPOINT
        if not force and wide == self.wide_mode and medium == self.medium_mode:
            return
        self.wide_mode = wide
        self.medium_mode = medium
        self.col3.setVisible(wide)
        # The preview column folds only once the detail column already has -
        # collapsing both together is the jump from three columns to one that
        # this second breakpoint exists to remove.
        self.col1.setVisible(medium)
        # Nothing to resize here any more: the controls are a strip across
        # the top, so they take height rather than width, and the body gets
        # the whole window at every breakpoint. What used to happen at this
        # point - narrowing a 268px form so a 350px findings list could
        # breathe - is a problem the top row does not have.
        self._collapse_inline_detail()
        self._reset_detail_panel()

    # --------------------------------------------------------------- events

    @property
    def mode(self) -> str:
        """The kind of run, derived rather than chosen.

        Everything downstream - which preview to show, which buttons write to
        disk, how a clicked row is dispatched - was written against these four
        names, and they are still the right names for it. What changed is that
        the user no longer picks one: the source and the question together say
        which it is.
        """
        if self.source == SOURCE_REPO:
            return MODE_REPO
        if self.source == SOURCE_FILE:
            return MODE_FILE
        return MODE_AUDIT if self._chosen_checks() == (CHECK_ACCESSIBILITY,) else MODE_WEB

    def _text_row_kind(self) -> str:
        """How a copy finding's row is tagged, independently of the mode.

        A run over a site that asks both questions is `MODE_AUDIT` by the rule
        above, but its copy findings are still copy findings and must not be
        dispatched as audit issues.
        """
        return MODE_REPO if self.source == SOURCE_REPO else MODE_WEB

    @staticmethod
    def choice_key(values) -> str:
        """The combo's stored value for a set of choices.

        A string, not the tuple itself: Qt carries item data through QVariant,
        which turns a tuple into a list, and `findData` then never matches what
        was stored - so restoring the previous choice silently fell back to the
        first item every time the source changed.
        """
        return "+".join(values)

    @staticmethod
    def _decode_choice(data, fallback) -> tuple:
        if not data:
            return fallback
        if isinstance(data, str):
            return tuple(part for part in data.split("+") if part)
        return tuple(data)

    # The combos are the input device; `AppState` is the answer. Reading the
    # widget here as well gave the window a second opinion about what the
    # user had chosen, and the two were compared against each other.

    def _chosen_checks(self) -> tuple:
        return self.app_state.checks

    def _chosen_readers(self) -> tuple:
        return self.app_state.readers

    def _chosen_methods(self) -> tuple:
        return self.app_state.methods

    def _ai_available(self) -> bool:
        """Read the provider probe's cached answer, without network or subprocess."""
        return self.app_state.ai_available

    def current_request(self) -> AnalysisRequest:
        """The run the current choices describe.

        Delegated: the view model builds this from `AppState`, and a second
        builder here - reading the combos directly - meant the window and the
        view model could describe different runs at the same moment. They
        did, and comparing one against the other is what stopped the
        extraction cache from ever matching.
        """
        return self.view_model.current_request()

    def _current_target(self) -> str:
        """The target, as a person actually supplied it.

        Dragging a folder in pastes it quoted or as a `file://` URL,
        depending on where it was dragged from, and both used to arrive here
        verbatim and fail as "path not found" with the quotes still in the
        message. Normalised in one place, shared with the CLI - see
        `cli_impl.auditpass.unquote_target`.
        """
        from cli_impl.auditpass import unquote_target

        if self.source == SOURCE_REPO:
            return unquote_target(self.repo_path_edit.text())
        if self.source == SOURCE_FILE:
            return unquote_target(self.file_path_edit.text())
        return unquote_target(self.url_edit.text())

    # ------------------------------------------- run state, owned elsewhere
    #
    # Read-only views onto the view model. The window needs these values -
    # the findings list asks whether the run wanted an audit, the audit
    # handler asks whether it wanted a browser - but it must not hold a
    # second copy of them. See the note in `__init__`.

    @property
    def _last_request(self):
        """The request that actually ran, or None before the first run."""
        return self.view_model._last_request

    @property
    def _extraction_request(self):
        return self.view_model._extraction_request

    @property
    def _cached_pages(self):
        return self.view_model._cached_pages

    @property
    def _cached_files(self):
        return self.view_model._cached_files

    @property
    def _cached_scope(self):
        return self.view_model._cached_scope

    def _reusable_pages(self):
        """Pages an earlier run already fetched for this exact target, or None.

        This is the payoff of separating the axes: changing the question or the
        judge used to mean crawling the site again, which is the slowest
        possible way to answer a question about pages already on this machine.
        """
        return self.view_model._reusable_pages()

    def _reusable_files(self):
        """The repository counterpart, with one extra condition.

        The scope decides what is extracted at all - copy, comments, or both -
        so a changed scope is a changed extraction and cannot be reused.
        """
        return self.view_model._reusable_files()

    def _remember_extraction(self, request, *, pages=None, files=None,
                             scope=None) -> None:
        self.view_model._remember_extraction(request, pages=pages, files=files,
                                             scope=scope)

    def _forget_extraction(self) -> None:
        """Drop the cache. Called when the source or the target changes: those
        are the two things the cached documents *are*."""
        self.view_model.forget_extraction()

    def _on_choice_changed(self, _idx: int = 0) -> None:
        """A changed question does not invalidate the fetched pages.

        This is the whole reason the axes were separated: switching from
        accessibility to copy, or from the offline engine to a model, used to
        mean crawling the site again. Only the source and the target clear the
        result now.
        """
        self._apply_mode_visibility()

    def _on_mode_changed(self, _idx: int) -> None:
        self.source = self.mode_combo.currentData() or SOURCE_SITE
        self._forget_extraction()
        self._retranslate_choices()
        self._apply_mode_visibility()
        # Switching source invalidates whatever was scanned before.
        self.result = None
        self.audit_result = None
        self.flagged_list.clear()
        self._expanded_item = None
        self._reset_detail_panel()
        self.status_bar.showMessage(t("status_idle", self.lang))

    def _retranslate_choices(self) -> None:
        """Fill the three choice combos for the source in force.

        Rebuilt on every source change rather than filled once and disabled,
        because what is *possible* changes with the source: a repository has
        no rendered form, so offering "in a browser" greyed out would be a
        control that exists only to be refused.
        """
        lang = self.lang
        # No reader selector. There used to be one, hidden, filled on every
        # source change and read by nothing: `ui.mode_rules.auto_readers`
        # decides how a source is read, and a site is always read both ways
        # because the difference between the two readings is itself a
        # finding. A control whose value nothing consults is worse than an
        # absent one - it looks like the answer to "how is this being read"
        # and is not, which is exactly how it misled the empty-state work
        # into offering a "re-read in a browser" button for a pass that had
        # already run.

        # Both by default: one pass over the fetched pages answers both
        # questions, and a first run that silently examined only half of what
        # the tool checks is how a report gets trusted for the wrong reason.
        self._fill_combo(self.checks_combo, [
            (t("checks_both", lang), self.choice_key((CHECK_ACCESSIBILITY, CHECK_AI_PATTERNS))),
            (t("check_accessibility", lang), self.choice_key((CHECK_ACCESSIBILITY,))),
            (t("check_ai_patterns", lang), self.choice_key((CHECK_AI_PATTERNS,))),
        ])

        ai_ready = self.app_state.ai_available
        method_options = [
            (t("method_local", lang), self.choice_key((METHOD_LOCAL,))),
            (t("method_embedding", lang), self.choice_key((METHOD_EMBEDDING,))),
        ]
        if ai_ready:
            method_options.append((t("method_ai", lang), self.choice_key((METHOD_AI,))))
            method_options.append((t("method_both", lang), self.choice_key((METHOD_LOCAL, METHOD_AI))))
        # First fill of the session restores the stored method; every later
        # one keeps whatever is selected, which is what `_fill_combo` does on
        # its own. Split like this because the two cases are different
        # questions: "what did this user choose last time" and "is the
        # current choice still on offer".
        first_fill = self.method_combo.currentData() is None
        self._fill_combo(self.method_combo, method_options)
        if first_fill:
            stored = self.method_combo.findData(self.settings.default_method)
            if stored >= 0:
                self.method_combo.setCurrentIndex(stored)
        self.method_combo.setEnabled(ai_ready)
        self.method_combo.setToolTip(
            t("method_label_full", lang) if ai_ready
            else t("method_ai_unavailable", lang))

    @staticmethod
    def _fill_combo(combo, options) -> None:
        """Refill a combo, keeping the current choice if it is still offered."""
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for label, value in options:
            combo.addItem(label, userData=value)
        index = combo.findData(previous) if previous is not None else -1
        combo.setCurrentIndex(max(index, 0))
        combo.blockSignals(False)

    def _size_stack_to_its_page(self) -> None:
        """Make the source stack as wide as the page it is showing.

        A `QStackedWidget` asks for the widest of *all* its pages, always.
        In a column that cost nothing - the column was a fixed width anyway.
        In the top row it costs 462px of the 1284 available, most of it
        reserved for the repository fields while a site scan is running, and
        that alone is enough to push the row onto a second line.

        The fix is the usual one: every hidden page is given an ignored size
        policy, so it stops contributing a size hint, and the current page
        gets its own back.
        """
        stack = self.source_controls_stack
        for index in range(stack.count()):
            page = stack.widget(index)
            if index == stack.currentIndex():
                page.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Fixed)
            else:
                page.setSizePolicy(QSizePolicy.Policy.Ignored,
                                   QSizePolicy.Policy.Ignored)
        # This screen borrows the stack as a stretched field in its target
        # row. `adjustSize()` resizes it to its small content hint and the
        # parent layout does not necessarily run again after a category or
        # check change, leaving empty space before Analyze. Invalidate the
        # hint so the parent can preserve the row's stretch allocation.
        stack.updateGeometry()

    def _apply_mode_visibility(self) -> None:
        is_repo = self.source == SOURCE_REPO
        is_file = self.source == SOURCE_FILE
        checks = self._chosen_checks()
        # What the run will actually look for, which is now a separate
        # question from where it looks.
        wants_copy = CHECK_AI_PATTERNS in checks
        wants_audit = CHECK_ACCESSIBILITY in checks
        # Auditing a site takes a URL and a depth, exactly like the web scan,
        # so it reuses those fields rather than growing a second pair beside
        # them. Auditing one file needs a path and nothing else.
        self.source_controls_stack.setCurrentIndex(
            2 if is_file else (1 if is_repo else 0))
        self._size_stack_to_its_page()
        # A single file is previewed as a rendered page, not as source: it is
        # a page, and its markup is what the third column already shows.
        # A rendered preview only once there is a page in it; until then the
        # empty state, which says so.
        self.col1_stack.setCurrentIndex(
            1 if is_repo else (0 if self.current_preview_url else 5))
        self.preview_empty.show_message(t("preview_empty_title", self.lang),
                                        t("preview_empty_body", self.lang))
        # And the head says which. It read "Page preview" over a list of a
        # repository's files, which is the column naming the wrong source.
        self.col1_header.setText(t("repo_preview_header" if is_repo
                                   else "site_preview_header", self.lang))
        # The width switcher belongs to the rendered preview. A repository is
        # previewed as source, which has no layout to look at narrow - and
        # neither has an empty column, where three widths to view nothing at
        # is a row of furniture above a sentence saying there is nothing.
        self.breakpoint_row.setVisible(not is_repo
                                       and bool(self.current_preview_url))
        # The detector belongs to the copy pass, so it follows the question
        # rather than the source. It used to be hidden whenever an audit was
        # selected, which meant that asking both questions at once left no way
        # to say which engine judged the copy.
        # ... and only when a model is actually going to read anything:
        # whose account pays is not a question an offline-only run has.
        wants_model = METHOD_AI in self._chosen_methods()
        self.provider_label.setVisible(wants_copy and wants_model)
        self.provider_combo.setVisible(wants_copy and wants_model)
        # A repo-only pair: a URL or a single file has no dev server of its
        # own to start.
        self.auto_devserver_check.setVisible(is_repo)
        self.start_server_btn.setVisible(is_repo)
        # Pairing a checkout is a question about a *site*: a folder run is
        # already reading the files, and it only means anything while the copy
        # pass is running, because that is the pass whose findings are
        # passages a file can be found for.
        pairing_useful = not is_repo and not is_file and wants_copy
        self.paired_repo_edit.setVisible(pairing_useful)
        self.paired_repo_btn.setVisible(pairing_useful)
        # `--within` narrows a document, so it belongs wherever there is one
        # to narrow: a page on a site, or a page in a file.
        self.within_edit.setVisible(not is_repo and wants_audit)
        # Signing in is a question about a site and nothing else: a folder
        # has no door and a local file has no session.
        self.sign_in_site_btn.setVisible(not is_repo and not is_file)
        self._refresh_sign_in_button()
        # The row is shared, but the two halves never appear together: three
        # buttons rewrite prose, three act on an audit, and offering both at
        # once would mean six buttons of which half do nothing.
        self.fix_unicode_btn.setVisible(wants_copy)
        self.fix_on_disk_btn.setVisible(wants_audit)
        self.undo_fix_btn.setVisible(wants_audit)
        self.download_btn.setVisible(wants_copy or wants_audit)
        # The row itself is always shown — the unicode fix works in both
        # modes — but the two file-writing buttons only apply to a repo.
        # The list is not a copy-pass button any more: it shows the audit's
        # corrections too, so it is offered wherever a run can write to disk
        # at all. Whether it has anything to show is decided by the enabled
        # state below, which asks the passes rather than the mode.
        self.generate_list_btn.setVisible(is_repo or wants_audit)
        self.auto_replace_btn.setVisible(is_repo and wants_copy)
        self._update_repo_buttons_enabled()

    def _update_repo_buttons_enabled(self) -> None:
        has_flags = bool(
            self.result and self.mode == MODE_REPO
            and any(s.confidence != Confidence.LOW for s in self.result.spans)
        )
        self.generate_list_btn.setEnabled(
            has_flags or bool(self._unicode_spans()) or self._audit_writable())
        self.auto_replace_btn.setEnabled(has_flags)
        self.fix_unicode_btn.setEnabled(bool(self._unicode_spans()))
        self._update_audit_buttons_enabled()

    def _audit_writable(self) -> bool:
        """Does the audit hold a correction for a file this machine can open?

        A crawled page has no file to write back to, and a finding with no
        ready correction is not an edit, so neither counts as something a
        write button can promise.
        """
        documents = self.audit_result.documents if self.audit_result else []
        local = [d for d in documents
                 if not d.source.startswith(("http://", "https://"))]
        return bool(local and any(
            issue.fix_snippet for d in local for issue in d.issues))

    def _update_audit_buttons_enabled(self) -> None:
        """A button that writes to disk is only offered when it has something
        to write, and only for a file it can actually open."""
        from audit import fixer

        documents = self.audit_result.documents if self.audit_result else []
        self.fix_on_disk_btn.setEnabled(self._audit_writable())
        self.undo_fix_btn.setEnabled(bool(fixer.backups_for(documents)))
        # Not gated on `self.mode == MODE_REPO` like the buttons above: a
        # styled report is offered for a web-text scan too, so this looks at
        # both result slots directly rather than reusing `has_flags`.
        self.download_btn.setEnabled(
            bool(documents) or bool(self.result and self.result.spans))

    def _active_unicode_categories(self):
        if not self.settings.unicode_check_enabled:
            return None
        return tuple(self.settings.unicode_categories or ())

    def _unicode_spans(self) -> list:
        """Every finding from the non-keyboard-character pass, in either mode.

        Selected on `details["source"]` rather than on the detector name:
        the character pass now runs inside the offline detector as well as
        standalone alongside a paid one, so its findings arrive under more
        than one detector name but always with the same source stamp.
        """
        if not self.result:
            return []
        return [s for s in self.result.spans
                if (s.details or {}).get("source") == "characters"]

    def _on_analyze_clicked(self) -> None:
        if getattr(self, "_account_checking", False) and getattr(self, "_pending_ai_methods", None):
            self.status_bar.showMessage(t("provider_checking", self.lang))
            return
        # Inline validation before starting
        if not self._validate_target():
            return
        self._sync_state_from_ui()
        self._reset_scan_ui()
        self._save_settings_from_combos()

        stack = self._devserver_stack_for_repo()
        if stack is not None and self.settings.auto_start_devserver:
            self._begin_devserver_flow(stack)
            return
        if stack is not None:
            # Not started: said once, not blocked on - the static scan below
            # still runs. A repo that happens to have a start command is the
            # ordinary case, not something worth a dialog every time.
            self.status_bar.showMessage(
                t("devserver_available", self.lang, stack=stack.name))

        self._show_missed_depth()

        error = self.view_model.analyze()
        if error and error != "browser_failed":
            QMessageBox.warning(self, "", error)

    def _show_missed_depth(self) -> None:
        """Say what this run is not going to reach, before it starts.

        The CLI has printed these since `cli_impl/prerun.py` and the window
        said nothing, so a person here could not know that the same tool,
        asked differently, would have answered more. Same source of truth -
        `prerun.missed` - rendered as notices rather than as English lines
        with flag names in them.

        `breakpoints` is deliberately not offered here: the window has no
        multi-width audit to switch on, and a notice whose move does not
        exist is worse than no notice. The width buttons in the preview
        column are a different thing - they resize what is on screen.
        """
        import argparse

        import diagnosis as dx
        from cli_impl import prerun

        request = self.view_model.current_request()
        args = argparse.Namespace(
            repo=self.app_state.paired_repo,
            devserver=self.settings.auto_start_devserver,
            url=False,
            no_browser=not request.wants_browser,
            breakpoints=True,   # see the docstring
            no_hints=False,
        )
        command = ("audit" if CHECK_ACCESSIBILITY in self._chosen_checks()
                   else "scan")
        found = prerun.missed(command, self.app_state.target, args,
                              is_url=self.source == SOURCE_SITE)
        self.show_diagnoses(dx.diagnose_missed_depth(found))

    def _on_start_server_clicked(self) -> None:
        """The explicit, one-time equivalent of the auto-start toggle."""
        if not self._validate_target():
            return
        stack = self._devserver_stack_for_repo()
        if stack is None:
            self.status_bar.showMessage(t("devserver_none_detected", self.lang))
            return
        self._sync_state_from_ui()
        self._reset_scan_ui()
        self._save_settings_from_combos()
        self._begin_devserver_flow(stack)

    def _on_auto_devserver_toggled(self, checked: bool) -> None:
        self.settings.auto_start_devserver = checked
        self.settings.save()

    def _devserver_stack_for_repo(self):
        """The detected stack for the current repo target, or `None`.

        Cheap filesystem checks only - detection, not the server itself.
        Deliberately says nothing about whether deps are satisfied: that
        distinction belongs to `_begin_devserver_flow`, which is the one
        place that decides whether to ask before installing. Conflating the
        two here once meant a repo whose deps were already installed never
        started a server at all - `deps_satisfied() == True` returned `None`
        just like `deps_satisfied() == False` did once the user declined,
        and both read the same to the caller.
        """
        if self.app_state.source != SOURCE_REPO:
            return None
        import devserver

        repo = Path(self._run_folder())
        if not repo.is_dir():
            return None
        return devserver.detect_stack(repo)

    def _run_folder(self) -> str:
        """The folder a run actually reads.

        The typed path, unless one project inside it was chosen. Everything
        that acts on "the repository" - the dev server, the ignore file, the
        scan itself - has to agree about which one, or the server started
        would belong to a different project from the one being audited.
        """
        return (self.app_state.chosen_project
                or self.repo_path_edit.text().strip())

    def _begin_devserver_flow(self, stack) -> None:
        """Confirm an install if (and only if) one is needed, then start."""
        repo = Path(self._run_folder())
        if stack.deps_satisfied(repo):
            self._start_devserver_then_analyze(True)  # nothing to install
            return
        answer = QMessageBox.question(
            self, "",
            t("devserver_confirm", self.lang, stack=stack.name, repo=str(repo)))
        self._start_devserver_then_analyze(
            answer == QMessageBox.StandardButton.Yes)

    def _start_devserver_then_analyze(self, install_confirmed: bool) -> None:
        """Install (if confirmed) and start the dev server, then run the
        analysis the confirm dialog was already asked for.

        The window does not flip the source selector to "Website" for this -
        `_on_devserver_ready` builds a resolved request instead of touching
        `AppState`, so the user's actual choice (Repository) stays what the
        UI shows throughout.
        """
        from ui.worker import DevServerWorker

        repo_path = self._run_folder()
        self.status_bar.showMessage(t("devserver_starting", self.lang))
        # `busy_changed` has not fired yet - `analyze()` has not been called -
        # so the button is disabled by hand for this phase, exactly as
        # `_on_busy_changed` would do once it has.
        self.analyze_btn.setEnabled(False)
        worker = DevServerWorker(repo_path, install_confirmed,
                                 start_command=self.app_state.start_command,
                                 port=self.app_state.dev_server_port)
        worker.ready.connect(self._on_devserver_ready)
        worker.failed.connect(self._on_devserver_failed)
        worker.finished.connect(self._on_worker_thread_finished)
        self._track_worker(worker)
        worker.start()

    def _on_devserver_ready(self, url: str, proc) -> None:
        self._devserver_proc = proc
        self.status_bar.showMessage(t("devserver_ready", self.lang, url=url))
        # Source and target are set for the duration of this one call only:
        # `analyze()` -> `_start_audit`/`_start_copy_pass` read them straight
        # from `AppState` (not from a request object), and both capture what
        # they need into the worker they start before this method returns -
        # nothing downstream keeps reading `AppState` afterward, which is
        # what makes restoring it immediately safe.
        previous = self.app_state.set_source_and_target_for_resolved_run(
            SOURCE_SITE, url)
        try:
            error = self.view_model.analyze()
        finally:
            self.app_state.set_source_and_target_for_resolved_run(*previous)
        self._recover_button_if_nothing_started(error)
        if error and error != "browser_failed":
            QMessageBox.warning(self, "", error)

    def _on_devserver_failed(self, reason: str) -> None:
        # Falls back to the static repo scan rather than stopping here,
        # exactly like the CLI path: a server that could not start must not
        # cost the analysis that could still run.
        self.status_bar.showMessage(t("devserver_failed", self.lang, reason=reason))
        error = self.view_model.analyze()
        self._recover_button_if_nothing_started(error)
        if error and error != "browser_failed":
            QMessageBox.warning(self, "", error)

    def _recover_button_if_nothing_started(self, error: str | None) -> None:
        """Undo the manual disable from `_start_devserver_then_analyze`.

        `analyze()` returns an error - "browser_failed" included - on every
        path that never called `_start_audit`/`_start_copy_pass`, which is
        also every path that will never emit `busy_changed(False)` to
        re-enable the button on its own. `error is None` means a worker is
        now running and that signal is coming; anything else means one is
        not, and this is the only re-enable that will ever happen.
        """
        if error is not None:
            self.analyze_btn.setEnabled(True)

    def _validate_target(self) -> bool:
        """Validate the current target field inline. Returns True if valid."""
        self._clear_all_field_errors()
        target = self._current_target()
        if target:
            return True
        lang = self.lang
        if self.app_state.source == SOURCE_REPO:
            self._show_field_error(self.repo_path_edit,
                                   t("no_repo_path", lang))
        elif self.app_state.source == SOURCE_FILE:
            self._show_field_error(self.file_path_edit,
                                   t("no_file_path", lang))
        else:
            self._show_field_error(self.url_edit,
                                   t("url_label_full", lang))
        return False

    def _clear_all_field_errors(self) -> None:
        """Clear all inline error indicators."""
        for edit in (self.url_edit, self.repo_path_edit, self.file_path_edit):
            self._clear_field_error(edit)

    def _sync_state_from_ui(self) -> None:
        """Push current widget values into AppState before an action."""
        self.app_state.set_target(self._current_target())
        self.app_state.set_depth(self.depth_spin.value())

    def _save_settings_from_combos(self) -> None:
        """Persist combo selections to settings."""
        self.settings.crawl_depth = self.depth_spin.value()
        method = self.method_combo.currentData()
        if method:
            self.settings.default_method = method
        provider = self.provider_combo.currentData()
        if provider:
            self.settings.llm_provider = provider
        self.settings.save()

    def _missing_target_message(self) -> str:
        if self.source == SOURCE_REPO:
            return t("no_repo_path", self.lang)
        if self.source == SOURCE_FILE:
            return t("no_file_path", self.lang)
        return t("url_label_full", self.lang)

    def _note_message(self, note: str) -> str:
        """A normalisation note as a sentence for the status bar.

        The request records notes in one language for the log; the window says
        the two the user can actually act on in theirs, and falls back to the
        raw note for anything else rather than swallowing it.
        """
        if "browser" in note:
            return t("reader_browser_unavailable", self.lang)
        if "AI pass" in note or "account or key" in note:
            return t("method_ai_unavailable", self.lang)
        return note

    def _start_copy_pass(self) -> None:
        """The AI-patterns question, over whichever source is selected."""
        if self.source == SOURCE_REPO:
            self._start_repo_analysis()
        elif self.source == SOURCE_FILE:
            # A rendered file is a page, and is read as one: the DOM the
            # browser built is not on disk, so the file reader cannot see it.
            if self._reusable_pages() is not None:
                self._start_web_analysis(root=_browser_url(
                    self.file_path_edit.text().strip()))
            else:
                self._start_file_copy_analysis()
        else:
            self._start_web_analysis()

    def _detector_for_request(self) -> tuple[str, dict]:
        """The engine the copy pass runs, worked out from the method.

        This is the fix for a silent failure, so it is worth stating what it
        replaces: the window used to take the engine straight from a
        dropdown of backend names, and never read the method choice at all.
        `AnalysisRequest.wants_ai` existed, was normalised, was reported in
        the status bar - and no code path consulted it. Choosing "AI" with
        the offline backend still selected ran the offline engine and
        presented its findings as the answer.

        Now the method decides what runs and the account decides who pays:

            offline only  -> the free local engine
            AI only       -> the judge for the selected account
            hybrid        -> both, merged (see `detectors/hybrid.py`)

        The request is the normalised one, so a method that asked for a model
        with no account behind it has already fallen back to offline here -
        with a note in the status bar saying so, rather than in silence.
        """
        request = self._last_request or self.current_request()
        judge = judge_for_provider(
            self.provider_combo.currentData() or self.settings.llm_provider)
        if request.wants_ai and request.wants_local:
            name = "hybrid"
        elif request.wants_ai:
            name = judge
        elif request.wants_embedding:
            name = "embedding"
        else:
            name = "offline"
        return name, self._detector_config_for(name, judge)

    def _detector_config_for(self, detector_name: str, judge_name: str = "") -> dict:
        """Per-detector construction arguments.

        Resolved through the factory first, so a legacy name stored in an
        old settings.json ("heuristic") is configured as what it actually
        builds ("offline") rather than falling through to no arguments.
        """
        resolved = DetectorFactory.resolve(detector_name)
        if resolved == "hybrid":
            # The hybrid owns the character pass through its offline half,
            # and its judge half is configured exactly like a bare judge -
            # by asking this same function, so there is one answer to "how
            # is an xFormat judge built" rather than two.
            judge = judge_name or judge_for_provider(self.settings.llm_provider)
            return {
                "categories": self._active_unicode_categories() or (),
                "judge_name": judge,
                "judge_config": self._detector_config_for(judge),
            }
        if resolved in ("claude-llm-judge", "claude-official-watermark"):
            return {"api_key": config.get_anthropic_api_key(), "model": self.settings.claude_model}
        if resolved == "xformat-llm-judge":
            return {
                "base_url": self.settings.xformat_base_url,
                "endpoints": self.settings.xformat_endpoints,
            }
        if resolved == "offline":
            # The character categories are a content decision the user makes
            # in Settings; style analysis is always on in this detector.
            return {"categories": self._active_unicode_categories() or ()}
        if resolved == "embedding":
            # Embedding detector uses sentence-transformers, no API key needed
            return {}
        return {}

    def _reset_scan_ui(self) -> None:
        # A run is starting: the working layout is where it is watched, and
        # the run's own progress panel is the preview column's page for it.
        self.show_setup(False)
        self.analyze_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.flagged_list.clear()
        self._expanded_item = None
        self.current_preview_url = None
        self.current_preview_path = None
        self.site_loader.load("", QUrl())
        self.code_view.setPlainText("")
        self._reset_detail_panel()

    def _start_web_analysis(self, root: str = "") -> None:
        """The copy pass over fetched pages.

        `root` overrides the URL field, for the one case where the pages did
        not come from that field: a single local file that was rendered in
        the browser.
        """
        url = root or self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "", t("url_label_full", self.lang))
            return
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url

        detector_name, detector_config = self._detector_for_request()
        self._reset_scan_ui()

        reused = self._reusable_pages()
        if reused is not None:
            self.status_bar.showMessage(t("status_reusing_pages", self.lang,
                                         count=len(reused)))

        self.worker = AnalysisWorker(
            pages=reused,
            root_url=url,
            depth=self.depth_spin.value(),
            detector_name=detector_name,
            detector_config=detector_config,
            max_pages=self.settings.max_pages,
            unicode_categories=self._active_unicode_categories(),
            settings=self.settings,
        )
        self.worker.crawling.connect(self._on_crawling)
        self.worker.detecting.connect(self._on_detecting)
        self.worker.finished_ok.connect(self._on_web_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_thread_finished)
        self._track_worker(self.worker)
        self.worker.start()

    def _start_file_copy_analysis(self) -> None:
        """The copy question asked of one HTML file.

        The same worker as a repository, over a single named path: a file that
        was named is a file to read, so the extension list and the exclusions
        that a walk needs do not apply to it.
        """
        self._start_repo_analysis(self.file_path_edit.text().strip())

    def _start_repo_analysis(self, path: str | None = None) -> None:
        path = path if path is not None else self._run_folder()
        if not path:
            QMessageBox.warning(self, "", t("no_repo_path", self.lang))
            return

        detector_name, detector_config = self._detector_for_request()
        self._reset_scan_ui()

        self.worker = RepoAnalysisWorker(
            files=(self._reusable_files()
                   if self.app_state.incremental else None),
            root_dir=path,
            ignore_patterns=self.effective_ignore_patterns,
            detector_name=detector_name,
            detector_config=detector_config,
            unicode_categories=self._active_unicode_categories(),
            scope=self._repo_scope(),
            settings=self.settings,
            extensions=self.app_state.extensions or None,
            incremental=self.app_state.incremental,
        )
        self.worker.scanning.connect(self._on_scanning_repo)
        self.worker.detecting.connect(self._on_detecting)
        self.worker.finished_ok.connect(self._on_repo_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_thread_finished)
        self._track_worker(self.worker)
        self.worker.start()

    # --------------------------------------------------------- suppression

    def _ignore_scan_root(self) -> str | None:
        """The folder a fingerprint suppression should be written into, or
        None when the current source has no folder at all.

        A repository scan has one, obviously; a single file's suppression
        also goes there, so a second finding in a sibling file lands in the
        same list instead of starting a second `.xanalyze-ignore` next to it.
        A site has no folder on this machine - see `_add_fingerprint_suppression`.
        """
        if self.source == SOURCE_REPO:
            path = self._run_folder()
            return path or None
        if self.source == SOURCE_FILE:
            path = self.file_path_edit.text().strip()
            return str(Path(path).parent) if path else None
        return None

    def _add_fingerprint_suppression(self, value: str, label: str = "") -> None:
        """Record "ignore this exact finding", in whichever list applies.

        The project's `.xanalyze-ignore` when the source is a folder or a
        file on disk - that is the shared, committed list `suppression.py`
        documents. A personal, cross-project setting otherwise, since a page
        fetched over the network has no folder to hold a project file in.
        """
        root = self._ignore_scan_root()
        if root:
            suppression.add_fingerprint_to_ignore_file(root, value, label)
            return
        fingerprints = list((self.settings.ignore or {}).get("fingerprints") or [])
        if value not in fingerprints:
            fingerprints.append(value)
            ignore = dict(self.settings.ignore or {})
            ignore["fingerprints"] = fingerprints
            if label:
                labels = dict(ignore.get("labels") or {})
                labels[value] = label
                ignore["labels"] = labels
            self.settings.ignore = ignore
            self.settings.save()

    def _on_ignore_span_clicked(self, span: TextSpan, block) -> None:
        """"Ignore this finding": suppress it and drop it from the list
        immediately, with an honest recount - not a re-run of the scan."""
        self._add_fingerprint_suppression(suppression.span_fingerprint(span, block),
                                          suppression.span_label(span, block))
        if self.result is not None:
            self.result.spans = [s for s in self.result.spans if s is not span]
        self._collapse_inline_detail()
        self._reset_detail_panel()
        self._populate_flagged_list()
        self._update_repo_buttons_enabled()

    def _on_ignore_issue_clicked(self, issue) -> None:
        """The audit counterpart of `_on_ignore_span_clicked`."""
        self._add_fingerprint_suppression(suppression.issue_fingerprint(issue),
                                          suppression.issue_label(issue))
        if self.audit_result is not None:
            for document in self.audit_result.documents:
                if issue in document.issues:
                    document.issues = [i for i in document.issues if i is not issue]
        self._collapse_inline_detail()
        self._reset_detail_panel()
        self._populate_flagged_list()
        self._update_audit_buttons_enabled()

    def _build_ignore_button(self, on_click) -> QPushButton:
        button = QPushButton(t("ignore_finding", self.lang))
        button.setToolTip(t("ignore_finding_hint", self.lang))
        button.clicked.connect(on_click)
        return button

    # ------------------------------------------------------------------ audit

    def _on_browse_file_clicked(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, t("mode_file", self.lang), "",
            "HTML (*.html *.htm *.xhtml);;" + t("all_files", self.lang) + " (*)")
        if path:
            self.file_path_edit.setText(path)

    def _start_audit(self) -> None:
        """Audit the chosen source: accessibility, SEO, performance, best
        practices. Reached from the re-audit after a fix (see
        `ui.window_parts.report_export`); the first audit of a run goes
        through the view model. Both build the worker with the same function,
        because when they built it separately they were separately wrong -
        see `ui.worker.audit_worker_for`."""
        from ui.worker import audit_worker_for

        worker, refusal = audit_worker_for(
            self.source,
            target=self._current_target(),
            depth=self.depth_spin.value(),
            max_pages=self.settings.max_pages,
            pages=self._reusable_pages() if self.source == SOURCE_SITE else None,
            ignore_patterns=self.effective_ignore_patterns,
            max_files=self.settings.max_files,
            extensions=self.app_state.extensions or None,
            files=(self._reusable_files()
                   if self.source == SOURCE_REPO
                   and self.app_state.incremental else None),
            incremental=self.app_state.incremental,
            settings=self.settings,
            site_controls=self.app_state.site_controls,
            medium=self.app_state.medium,
        )
        if worker is None:
            QMessageBox.warning(self, "", self._missing_target_message()
                                if refusal == "no_target"
                                else t("url_label_full", self.lang))
            return

        self.audit_result = None
        self._reset_scan_ui()
        self.worker = worker
        self.worker.crawling.connect(self._on_crawling)
        self.worker.auditing.connect(self._on_auditing)
        self.worker.finished_ok.connect(self._on_audit_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_thread_finished)
        self._track_worker(self.worker)
        self.worker.start()

    def _on_auditing(self, target: str) -> None:
        self.status_bar.showMessage(t("status_auditing", self.lang, target=target))
        self._advance_stage("browser", target, f"browser {target}")

    def _on_audit_finished(self, result) -> None:
        self.audit_result = result
        if self._last_request is not None and self._last_request.wants_browser:
            self._run_browser_pass()
        self._populate_audit_list()
        # Show the audited page straight away rather than waiting for a click.
        # An empty white pane next to a full list of findings reads as
        # something having gone wrong, which is the opposite of what happened.
        first = next((d for d in result.documents if not d.error), None)
        if first is not None:
            address = _browser_url(first.source)
            self.current_preview_url = address
            self.site_loader.navigate(QUrl(address))
        # Recomputed here, not only when the mode changes: whether there is
        # anything to write, and whether there is anything to take back, are
        # both facts about the result that just arrived.
        self._update_audit_buttons_enabled()
        # The same sentence the CLI prints, from the same function: two
        # wordings of one summary is two things to keep true.
        self.status_bar.showMessage(
            audit_explanations.summary_line(result, self.lang))
        # There are two ways an audit result reaches this window, and the
        # other one already does this. Both, or a run started one way says
        # what it could not read and a run started the other way does not.
        self.diagnose_finished_run()
        if getattr(self, "_pending_copy_pass", False):
            # The second half of a both-questions run. `_reset_scan_ui` would
            # wipe the audit rows that just arrived, so the copy pass appends
            # to them instead: `_populate_flagged_list` puts the audit findings
            # back first.
            self._pending_copy_pass = False
            self._start_copy_pass()

    def _render_crawl(self, url: str):
        """Crawl with a browser in the loop, on this thread.

        Returns the pages, or None when the user should be told rather than
        given a silently worse reading. The point of doing this at all: a page
        whose copy is written by JavaScript has nothing to read in the response,
        and until now the tool could only say so.
        """
        from audit import driver
        from crawler import RENDER_ALWAYS, CrawlConfig, crawl

        usable, reason = driver.available()
        if not usable:
            QMessageBox.information(self, t("reader_browser", self.lang), reason)
            return None

        config = CrawlConfig(max_depth=self.depth_spin.value(),
                             max_pages=self.settings.max_pages,
                             render_mode=RENDER_ALWAYS)

        def progress(page_url: str, _depth: int) -> None:
            self.status_bar.showMessage(
                t("status_browser_pass", self.lang, url=page_url))

        try:
            with driver.html_renderer(within=self.app_state.within) as render:
                return crawl(url, config, progress_cb=progress, render=render)
        except Exception as exc:  # noqa: BLE001 - a failed browser is worth a
            # sentence, not a traceback: the run can still be repeated without
            # one, and the user is the one who chose to use it.
            QMessageBox.warning(self, t("reader_browser", self.lang), str(exc))
            return None

    def _render_single_file(self, path: str):
        """The DOM a browser builds for one local file, as one page.

        Returns None when the user should be told rather than handed a
        quietly worse reading - the same contract as `_render_crawl`.
        """
        from audit import driver
        from crawler import page_from_html

        if not path:
            QMessageBox.warning(self, "", t("no_file_path", self.lang))
            return None
        usable, reason = driver.available()
        if not usable:
            QMessageBox.information(self, t("reader_browser", self.lang), reason)
            return None
        address = _browser_url(path)
        self.status_bar.showMessage(
            t("status_browser_pass", self.lang, url=address))
        try:
            with driver.html_renderer() as render:
                html = render(address) or ""
        except Exception as exc:  # noqa: BLE001 - see `_render_crawl`
            QMessageBox.warning(self, t("reader_browser", self.lang), str(exc))
            return None
        if not html:
            QMessageBox.warning(self, t("reader_browser", self.lang),
                                t("reader_browser_empty", self.lang))
            return None
        return [page_from_html(html, address)]

    def _run_browser_pass(self) -> None:
        """Re-audit each page in a real browser, on this thread.

        On this thread on purpose: QtWebEngine is only usable from the thread
        that owns the application, so there is no version of this that runs in
        `AuditWorker`. The driver pumps the event loop while it waits, which is
        why the window stays repainted through a pass that takes seconds per
        page.
        """
        from audit import browser as browser_mod
        from audit import driver

        result = self.view_model.audit_result
        if result is None:
            return

        usable, reason = driver.available()
        if not usable:
            QMessageBox.information(self, t("browser_pass_label", self.lang), reason)
            return

        from cli_impl.auditpass import _is_renderable, unread_sources

        targets = []
        seen_sources = set()
        snapshot = self.view_model._snapshot
        acquired_sources = {
            getattr(page, "url", "")
            for page in (snapshot.pages if snapshot else ())
            if getattr(page, "url", "")
        }
        unread = unread_sources(result.documents)
        for document in result.documents:
            if (document.error or document.source in seen_sources
                    or document.source in unread
                    or not _is_renderable(document.source)
                    or (self.source == SOURCE_SITE and acquired_sources
                        and document.source not in acquired_sources)):
                continue
            targets.append(document)
            seen_sources.add(document.source)
        if not targets:
            return

        suppressions = suppression.Suppressions.load(self.settings, None)
        options = browser_mod.BrowserAuditOptions(
            exclude=list(suppressions.selectors),
            disabled_rules=list(suppressions.rules),
            # Only a file the user picked themselves may read its neighbours
            # on disk; a page off the network never may.
            allow_local_files=self.mode == MODE_FILE,
            # The browser reader and audit are one Chromium pass. Its first
            # viewport returns the rendered DOM for our own rules and, when
            # requested, copy analysis. The remaining viewports only rerun
            # responsive probes; serialising the DOM does not navigate again.
            capture_html=True,
        )
        # A SharePoint run reads the zones, not the chrome - the same options
        # and the same classification `fullscan`'s browser pass uses.
        zone_summary = None
        if getattr(result, "sharepoint", None):
            from audit import sharepoint_zones

            options = sharepoint_zones.browser_options(options)
            zone_summary = sharepoint_zones.Summary()
        # Every width, not just the one this screen happens to be: the point
        # of asking a browser at all is to see what a visitor sees, and a
        # visitor on a phone is shown a different document. The merge keeps
        # the list the same length - a finding present at several widths is
        # one row that records them - so this costs time, not noise. See
        # `audit/responsive.py`.
        from dataclasses import replace

        from audit import responsive

        sizes = responsive.BREAKPOINTS
        # The same cache the CLI uses, keyed on the markup the crawl already
        # received: a page whose bytes have not changed is not loaded again.
        # Measured on `python.org`: 7.0 s against 0.53 s for the second run
        # of an unchanged page, with identical findings.
        import browser_cache

        served = getattr(result, "markup_by_source", None) or {}
        cache = browser_cache.BrowserCache(options, sizes) if served else None
        profile = (driver.session_profile(self.view_model.session_host)
                   if not self.app_state.no_session else None)
        runner = driver.BrowserAuditRunner(
            replace(options, viewport=(sizes[0][1], sizes[0][2])),
            profile=profile,
            cancelled=lambda: self.view_model.cancellation_requested)
        rendered_by_source = {}
        page_audits = []
        try:
            for document in targets:
                self.status_bar.showMessage(t("status_browser_pass_widths",
                                              self.lang, url=document.source,
                                              n=len(sizes)))
                markup = served.get(document.source)
                page_audit = (cache.get(markup, document.source)
                              if (cache is not None and markup) else None)
                if page_audit is None:
                    page_audit = responsive.audit_responsive(
                        _browser_url(document.source), sizes, options,
                        runner=runner)
                    if (cache is not None and markup and not page_audit.error
                            and not page_audit.engine_errors):
                        cache.put(markup, page_audit)
                if zone_summary is not None and not page_audit.error:
                    # A copy, not in place: the cache holds this object and
                    # saves it after the loop, and a cached audit that was
                    # already zoned would drop Microsoft's findings without
                    # counting them on the next run.
                    page_audit = replace(
                        page_audit,
                        issues=sharepoint_zones.classify_browser_issues(
                            page_audit.issues, page_audit.html,
                            self.view_model._web_parts_for_run(),
                            summary=zone_summary))
                page_audits.append((document.source, page_audit))
                if page_audit.html:
                    rendered_by_source[document.source] = page_audit.html
                if self.view_model.cancellation_requested:
                    break
        finally:
            runner.close()
            if cache is not None:
                cache.save()

        self.view_model.remember_browser_html(rendered_by_source)
        # Refreshing the static result must happen first. Browser measurements
        # can disprove a static loading warning, and merging before the
        # refresh would let that warning be created again afterwards.
        for source, page_audit in page_audits:
            document = next(
                (item for item in result.documents
                 if item.source == source and not item.error), None)
            if document is not None:
                browser_mod.merge_page_audit(result, document, page_audit)
        if zone_summary is not None:
            from cli_impl.auditpass import _add_skipped

            _add_skipped(result, zone_summary)

        # Repaint, or the pass was invisible. The findings are merged into
        # the documents above and the list on screen was built before that,
        # so without this the window shows the static pass and nothing else:
        # measured on one page, 12 rows on screen against 31 findings in the
        # result - axe, HTML_CodeSniffer, the state pass and every load
        # measurement, all present and none of them displayed. The CLI never
        # had it because it prints after the merge.
        # The ViewModel emits the completed audit after this synchronous
        # continuation returns. Direct legacy callers already own the result
        # on the window and still need an immediate repaint.
        if self.audit_result is result:
            self._populate_audit_list()
            self._refresh_summary()
            self._update_audit_buttons_enabled()
            self.diagnose_finished_run()
            self.status_bar.showMessage(t("status_idle", self.lang))


    def _repo_scope(self) -> str:
        return self.scope_combo.currentData() or self.settings.repo_scope or SCOPE_CONTENT

    def _on_scope_changed(self, _idx: int) -> None:
        """Changing the scope invalidates the results: a findings list built
        from comments has nothing to say about a scan of page copy, and
        leaving it on screen would invite acting on the wrong one."""
        self.settings.repo_scope = self._repo_scope()
        self.scope_combo.setToolTip(t(f"scope_{self.settings.repo_scope}_full", self.lang))
        if self.mode == MODE_REPO and self.result is not None:
            self.result = None
            self._populate_flagged_list()
            self._reset_detail_panel()
            self.status_bar.showMessage(t("status_idle", self.lang))

    # ------------------------------------------------- dropping a target in

    #: What a dropped file may be for the single-page source (artboard 3o).
    #: A page saved as one file is the whole case: it can be rendered *and*
    #: read as code, which is why it is a source of its own.
    DROPPABLE_PAGES = (".html", ".htm")

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Accept a saved page or a folder, and nothing else.

        Refused rather than accepted-and-ignored: a window that takes the
        drop and then does nothing is indistinguishable from one that is
        broken, and the cursor is the only place to say so before the drop.
        """
        if self._dropped_target(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        target = self._dropped_target(event.mimeData())
        if target is None:
            event.ignore()
            return
        source, path = target
        self.app_state.set_source(source)
        edit = (self.file_path_edit if source == SOURCE_FILE
                else self.repo_path_edit)
        edit.setText(path)
        # Straight to the setup screen rather than starting a run: dropping
        # a file says what to look at, not that everything else about the
        # run is already right.
        self.show_setup(True)
        self.status_bar.showMessage(t("status_dropped", self.lang,
                                      path=Path(path).name))
        event.acceptProposedAction()

    def _dropped_target(self, mime):
        """`(source, path)` for a drop this window can act on, or None."""
        if mime is None or not mime.hasUrls():
            return None
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                return SOURCE_REPO, str(path)
            if path.suffix.lower() in self.DROPPABLE_PAGES:
                return SOURCE_FILE, str(path)
        return None

    def _on_sign_in_site(self) -> None:
        """Open a browser window on the target and let the person sign in.

        Nothing is typed for them and nothing is remembered about them: the
        window is a browser, the site's own form is what they fill in, and
        what survives is what the site handed that browser.
        """
        import site_session
        from ui.site_sign_in import SiteSignInDialog

        self._sync_state_from_ui()
        target = (self.app_state.target or "").strip()
        host = site_session.host_of(target)
        if not host:
            self.status_bar.showMessage(t("sign_in_site_needs_url", self.lang))
            return
        address = target if "://" in target else f"https://{target}"
        dialog = SiteSignInDialog(address, lang=self.lang, parent=self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._refresh_sign_in_button()
        # The plan's sign-in prompt depends on the session, which the key
        # `_refresh_run_plan` caches on does not include: rebuild it, so a
        # person who just signed in stops being asked to.
        self._planned_key = None
        self._refresh_run_plan()
        if accepted and dialog.saved:
            self.status_bar.showMessage(
                t("sign_in_site_active", self.lang, host=host))

    def _refresh_sign_in_button(self) -> None:
        """Say whether this host already has a session, on the button itself.

        A person has to be able to see that this machine holds a way into
        their account without opening a dialog to find out.
        """
        import site_session

        host = site_session.host_of(self.url_edit.text())
        signed_in = bool(host) and site_session.has_session(host)
        self.sign_in_site_btn.setText(
            t("sign_in_site_change", self.lang) if signed_in
            else t("sign_in_site_button", self.lang))
        self.sign_in_site_btn.setToolTip(
            t("sign_in_site_have", self.lang, host=host) if signed_in
            else t("sign_in_site_full", self.lang))

    def _on_browse_paired_repo(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.paired_repo_btn.text())
        if path:
            self.paired_repo_edit.setText(path)

    def _on_paired_repo_changed(self, text: str) -> None:
        """Remember the checkout, so the second audit of a site does not ask.

        Written to settings on every edit rather than on run: a person who
        picks the folder and then changes their mind about the URL has still
        told us which checkout this machine works on.
        """
        value = (text or "").strip()
        self.app_state.set_paired_repo(value)
        # A checkout is half of what decides the run: an SPFx solution paired
        # with a site is the one case where `--web-parts` means anything.
        self._refresh_run_plan()
        if self.settings.last_paired_repo != value:
            self.settings.last_paired_repo = value
            self.settings.save()

    def _on_within_changed(self, text: str) -> None:
        self.app_state.set_within(text)

    def _on_browse_clicked(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.browse_btn.text())
        if path:
            self.repo_path_edit.setText(path)

    @property
    def effective_ignore_patterns(self) -> list:
        """What a folder run actually skips. See `_on_project_changed`."""
        return self.app_state.ignore_patterns_with_project(
            self.repo_ignore_patterns)

    def _on_exclusions_clicked(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(t("scan_options_title", self.lang))
        layout = QVBoxLayout(dlg)
        incremental = QCheckBox(t("incremental_check", self.lang))
        incremental.setObjectName("scan-incremental")
        incremental.setChecked(self.app_state.incremental)
        incremental.setToolTip(t("incremental_check_full", self.lang))
        incremental.setAccessibleDescription(
            t("incremental_check_full", self.lang))
        layout.addWidget(incremental)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        max_files = QSpinBox()
        max_files.setObjectName("scan-max-files")
        max_files.setRange(100, 200000)
        max_files.setValue(max(100, int(self.settings.max_files or 5000)))
        extensions = QLineEdit()
        extensions.setObjectName("scan-extensions")
        extensions.setText(", ".join(self.app_state.extensions))
        extensions.setPlaceholderText(t("scan_extensions_placeholder", self.lang))
        form.addRow(t("scan_max_files", self.lang), max_files)
        form.addRow(t("scan_extensions", self.lang), extensions)
        layout.addLayout(form)

        layout.addWidget(QLabel(t("scan_exclusions", self.lang)))
        editor = QPlainTextEdit()
        editor.setObjectName("scan-exclusions")
        editor.setPlainText("\n".join(self.repo_ignore_patterns))
        editor.setMinimumHeight(120)
        layout.addWidget(editor)
        note = QLabel(t("scan_extensions_hint", self.lang))
        note.setWordWrap(True)
        note.setProperty("class", "muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.resize(560, 460)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            raw_extensions = [part for part in re.split(
                r"[,;\s]+", extensions.text().strip()) if part]
            normalized_extensions = tuple(
                part.lower() if part.startswith(".") else f".{part.lower()}"
                for part in raw_extensions
            )
            if any(not re.fullmatch(r"\.[a-z0-9_-]+", item)
                   for item in normalized_extensions):
                QMessageBox.warning(
                    self, "", t("scan_extensions_invalid", self.lang))
                return
            self.settings.max_files = max_files.value()
            self.settings.save()
            self.app_state.set_incremental(incremental.isChecked())
            self.app_state.set_extensions(normalized_extensions)
            self.repo_ignore_patterns = _parse_ignore_text(editor.toPlainText())
            # The view model holds the same list, and held it by *reference*:
            # rebinding here left it pointing at the pre-edit one, so an
            # exclusion added in this dialog was honoured by the audit and
            # ignored by the text scan.
            self.view_model.repo_ignore_patterns = self.repo_ignore_patterns

    def _on_cancel_clicked(self) -> None:
        self.view_model.cancel()
        self.cancel_btn.setEnabled(False)

    def _on_crawling(self, url: str, depth: int) -> None:
        self.status_bar.showMessage(t("status_crawling", self.lang, url=url, depth=depth))
        self._advance_stage("crawl", url, f"crawl {url} (depth {depth})")

    def _on_scanning_repo(self, rel_path: str) -> None:
        self.status_bar.showMessage(t("status_scanning_repo", self.lang, path=rel_path))
        self._advance_stage("scan", rel_path, f"read {rel_path}")

    def _on_detecting(self, detector_label: str) -> None:
        self.status_bar.showMessage(t("status_detecting", self.lang, detector=detector_label))
        self._advance_stage("detect", detector_label, f"detect {detector_label}")

    def _on_web_finished(self, result: AnalysisResult) -> None:
        self.result = result
        # Remembered on success only: a cancelled or failed fetch has nothing
        # worth answering the next question from.
        self._remember_extraction(self._last_request, pages=result.pages)
        # A run can finish and still have failed to read most of the site.
        # Refused addresses and a truncated crawl were both recorded and
        # then never mentioned, so a clean result stood for pages nobody
        # had opened.
        self.diagnose_finished_run(result)
        self._populate_flagged_list()
        n_flags = sum(1 for s in result.spans if s.confidence != Confidence.LOW)
        self.status_bar.showMessage(
            t("status_done", self.lang, pages=len(result.pages), blocks=len(result.blocks()), flags=n_flags)
        )
        self._update_repo_buttons_enabled()

    def _on_repo_finished(self, result: RepoAnalysisResult) -> None:
        self.result = result
        self._remember_extraction(self._last_request, files=result.files,
                                  scope=self._repo_scope())
        self._populate_flagged_list()
        n_flags = sum(1 for s in result.spans if s.confidence != Confidence.LOW)
        self.status_bar.showMessage(
            t("status_done_repo", self.lang, pages=len(result.files),
              blocks=len(result.blocks()), flags=n_flags)
        )
        self._update_repo_buttons_enabled()
        # The same three lines as the view-model path. There are two ways a
        # repo result reaches this window and only one of them was doing
        # this, which is how a scan started one way had a file column and a
        # summary and a scan started the other way had neither.
        self.refresh_repo_files()
        self._refresh_summary()

    def _on_failed(self, message: str) -> None:
        """A run that raised, shown as something a person can act on.

        Not a modal any more. It had one empty title bar for every kind of
        failure, and - the part that cost something - once it was dismissed
        the explanation was gone and the window looked exactly as it does
        after a run that went fine.
        """
        import diagnosis as dx

        self.status_bar.showMessage(t("status_error", self.lang, error=message))
        self.show_diagnoses([dx.diagnose_failure(message)])

    def _on_worker_thread_finished(self) -> None:
        self.analyze_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # -- ViewModel signal handlers -----------------------------------------
    def _on_undo_outcome(self, message: str) -> None:
        QMessageBox.information(self, t("undo_fix_button", self.lang), message)
        self._reaudit_after_fix()

    def _on_download_choice_needed(self, has_audit: bool, has_text: bool) -> None:
        """Both reports, one folder. There is no longer a choice to make.

        This used to ask which of the two reports to save, which is a
        question with no good answer: the report a person reads and the
        briefing an agent reads are not alternatives, they are two documents
        of one run. Writing the folder produces both, so the dialog was
        asking someone to give one of them up for no reason.
        """
        self._on_styled_report_clicked()

    def _on_unicode_fixed(self, filled: int) -> None:
        self._populate_flagged_list()
        self._update_repo_buttons_enabled()
        QMessageBox.information(self, "", t("unicode_fixed_summary", self.lang, n=filled))
