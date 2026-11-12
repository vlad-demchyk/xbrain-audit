"""The screen before the first run: four choices, in the order they are made.

Artboard 3b. The window used to open on its working layout - three columns
of results, all empty - with the run's settings folded into one line of
inline values above them. That line is right *during* work, where the
question is "what will the next run be" and the answer has to fit beside
the findings of the last one. It is wrong before any work, where the same
line is the entire task and is written in eight words across the top of a
window that is otherwise blank.

So: one screen while nothing has run, the working layout once something has.

The four cards are the four axes, and they are four because they are chosen
independently - what is looked at, how it is read, what is looked for, and
who judges. The screen writes every choice into `AppState`, which the top
row already reads, so the two surfaces cannot disagree: they are two
renderings of one object, not two copies of one decision.

**Card 2 states rather than asks.** How a source is read is derived
(`mode_rules.auto_readers`) - a site is read both ways because the
difference between the two readings is itself a finding. A selector here
would be a control nothing consults, which this window has had before and
removed on purpose. It says what will happen and why, and takes no clicks.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from analysis_modes import (
    CHECK_ACCESSIBILITY, CHECK_AI_PATTERNS, METHOD_AI, METHOD_EMBEDDING,
    METHOD_LOCAL, READER_BROWSER, SOURCE_FILE, SOURCE_REPO, SOURCE_SITE,
)
from audit.base import CATEGORIES, CONFIDENCE_ORDER
from audit.medium import EMAIL, WEB
from i18n.translations import t
from ui import theme
from ui.widgets import FlowLayout

#: The three sources, with the sentence each one is described by.
#: What a folder's documents are for. Empty first, because reading it off
#: the markup is right nearly always - and because a wrong default here
#: silently drops whole categories of finding.
MEDIA = ("", WEB, EMAIL)

SOURCES = (
    (SOURCE_SITE, "source_site", "setup_source_site_hint"),
    (SOURCE_REPO, "source_repo", "setup_source_repo_hint"),
    (SOURCE_FILE, "source_file", "setup_source_file_hint"),
)

#: The judges. `METHOD_AI` needs an account, which is why it carries a flag
#: rather than being filtered out of the list: a choice that is missing looks
#: like a choice that does not exist.
METHODS = (
    (METHOD_LOCAL, "method_local", "setup_method_local_hint", False),
    (METHOD_EMBEDDING, "method_embedding", "setup_method_embedding_hint", False),
    (METHOD_AI, "method_both", "setup_method_ai_hint", True),
)


#: The certainty floor, weakest first, with "no floor" in front of it.
#: Read from `audit.base` rather than spelled again here: a fourth level
#: would otherwise exist in the audit and not in the window that runs it.
CERTAINTIES = ("",) + CONFIDENCE_ORDER


def _under_home(path) -> str:
    """`~/Downloads/page.html` rather than the whole absolute path.

    The design writes it this way and it is not only shorter: the part that
    identifies the file is its tail, and a temporary directory's path can be
    sixty characters of nothing anybody typed.
    """
    from pathlib import Path

    try:
        return "~/" + Path(path).relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def _human_size(size: int) -> str:
    """Bytes as somebody would say them. Two units are enough here: a saved
    page is kilobytes or a few megabytes, never gigabytes."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _two_line(title: str, hint: str) -> QWidget:
    """A name over the sentence that says what choosing it means."""
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    name = QLabel(title)
    column.addWidget(name)
    if hint:
        note = QLabel(hint)
        note.setProperty("class", theme.CLASS_MUTED)
        note.setWordWrap(True)
        column.addWidget(note)
    return holder


class SetupCard(QWidget):
    """One numbered card: a step label and whatever the step is choosing."""

    def __init__(self, step_key: str, lang: str = "en", parent=None):
        super().__init__(parent)
        self.step_key = step_key
        self.lang = lang
        self.setProperty("class", theme.CLASS_INSET)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(12, 11, 12, 11)
        self.column.setSpacing(7)
        self.step = QLabel(t(step_key, lang))
        self.step.setProperty("class", theme.CLASS_FIELD_LABEL)
        self.column.addWidget(self.step)


class SetupScreen(QWidget):
    """Everything a run is, before it is one."""

    #: The screen asks; the window owns the picker and the field it fills.
    choose_file_requested = Signal()

    def __init__(self, app_state, palette, lang: str = "en", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.palette_ = palette
        self.lang = lang
        self.setProperty("class", theme.CLASS_PANEL)
        self.setProperty("view", "setup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        body.setProperty("class", theme.CLASS_PANEL_BODY)
        column = QVBoxLayout(body)
        column.setContentsMargins(44, 30, 44, 24)
        column.setSpacing(18)
        outer.addWidget(body, stretch=1)

        self.title = QLabel(t("setup_title", lang))
        self.title.setProperty("class", theme.CLASS_HEADING)
        self.subtitle = QLabel(t("setup_subtitle", lang))
        self.subtitle.setProperty("class", theme.CLASS_MUTED)
        self.subtitle.setWordWrap(True)
        heading = QWidget()
        heading_column = QVBoxLayout(heading)
        heading_column.setContentsMargins(0, 0, 0, 0)
        heading_column.setSpacing(2)
        heading_column.addWidget(self.title)
        heading_column.addWidget(self.subtitle)
        column.addWidget(heading)

        # The target row is filled by the window, which owns the fields: the
        # address, the folder and the file are three different widgets with
        # three different pickers, and copying them here would be a second
        # place for the same value to be wrong in.
        self.target_row = QWidget()
        self.target_row.setProperty("class", theme.CLASS_INSET)
        self.target_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Capped, as the design caps it. A single address stretched across
        # 1300px reads as a form field in an empty room; the row is the one
        # thing on this screen that is typed into, and it should look like a
        # sentence rather than like the width of the window.
        self.target_row.setMaximumWidth(720)
        self.target_row.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.target_layout = QHBoxLayout(self.target_row)
        self.target_layout.setContentsMargins(10, 6, 6, 6)
        self.target_layout.setSpacing(8)
        column.addWidget(self.target_row)

        # The single-page source is the one target you can bring rather than
        # type, so it gets the area the design draws for it (artboard 3o).
        # It sits under the target row and takes the same drop the window
        # takes anywhere on itself.
        self.drop_zone = self._build_drop_zone()
        column.addWidget(self.drop_zone)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self._build_source_card(), stretch=1)
        cards.addWidget(self._build_reading_card(), stretch=1)
        cards.addWidget(self._build_question_card(), stretch=1)
        cards.addWidget(self._build_judge_card(), stretch=1)
        column.addLayout(cards)

        # The fifth choice, on its own line rather than as a fifth column.
        # Four cards already divide 1300px into quarters, and a fifth would
        # take each below the width its two-line rows need - the same width
        # budget the top row is measured against in `test_window_shell`.
        # It is also a different kind of choice: the four above decide what
        # the run *is*, this one decides what is shown of it, and it stays
        # usable after the run because it changes no run at all.
        column.addWidget(self._build_report_card())
        column.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.summary = QLabel()
        self.summary.setProperty("class", theme.CLASS_MUTED)
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        bottom.addWidget(self.summary, stretch=1)
        column.addLayout(bottom)

        # No footer strip. The design draws one ("Готово до роботи · ⌘K …")
        # and the window already has a status bar saying exactly that, at the
        # bottom of the same window. Two places for one sentence is how one
        # of them comes to be stale.

        self.app_state.any_changed.connect(self.refresh)
        self.retranslate(lang)

    def _build_drop_zone(self) -> QWidget:
        zone = QWidget()
        zone.setProperty("class", theme.CLASS_INSET)
        zone.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        zone.setMaximumWidth(720)
        column = QVBoxLayout(zone)
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(4)

        self.drop_arrow = QLabel("↓")
        self.drop_arrow.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(self.drop_arrow)
        self.drop_title = QLabel()
        self.drop_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(self.drop_title)
        self.drop_note = QLabel()
        self.drop_note.setProperty("class", theme.CLASS_MUTED)
        self.drop_note.setWordWrap(True)
        self.drop_note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(self.drop_note)

        row = QHBoxLayout()
        row.addStretch(1)
        self.drop_choose_btn = QPushButton()
        self.drop_choose_btn.setProperty("class", theme.CLASS_QUIET)
        self.drop_choose_btn.clicked.connect(self.choose_file_requested)
        row.addWidget(self.drop_choose_btn)
        row.addStretch(1)
        column.addLayout(row)

        # What was chosen, once something is: the design puts the file's own
        # name and size here, because "412 KB" is how somebody notices they
        # dropped the wrong export.
        self.drop_chosen = QLabel()
        self.drop_chosen.setProperty("class", theme.CLASS_CODE)
        self.drop_chosen.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.drop_chosen.setVisible(False)
        column.addWidget(self.drop_chosen)
        return zone

    def refresh_target(self) -> None:
        """The two things that read the target: the drop zone and the sentence.

        `AppState.set_target` carries no signal - the target changes on every
        keystroke and a repaint per character is not worth it - so the window
        calls this when the value has actually settled.
        """
        self._refresh_project()
        self._refresh_profile()
        self._refresh_drop_zone()
        self._refresh_summary()

    def _refresh_drop_zone(self) -> None:
        from pathlib import Path

        state = self.app_state
        self.drop_zone.setVisible(state.source == SOURCE_FILE)
        if state.source != SOURCE_FILE:
            return
        target = (state.target or "").strip()
        path = Path(target) if target else None
        if path is not None and path.is_file():
            size = path.stat().st_size
            self.drop_chosen.setText(t("setup_drop_chosen", self.lang,
                                       name=_under_home(path),
                                       size=_human_size(size)))
            self.drop_chosen.setVisible(True)
        else:
            self.drop_chosen.setVisible(False)

    # ------------------------------------------------------------- cards

    def _build_source_card(self) -> QWidget:
        card = SetupCard("setup_step_source", self.lang)
        self.source_buttons = {}
        self.source_group = QButtonGroup(self)
        self.source_group.setExclusive(True)
        for value, label_key, hint_key in SOURCES:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            button = QRadioButton()
            button.toggled.connect(
                lambda checked, chosen=value: checked and self.app_state.set_source(chosen))
            self.source_group.addButton(button)
            line.addWidget(button)
            line.addWidget(_two_line(t(label_key, self.lang),
                                     t(hint_key, self.lang)), stretch=1)
            self.source_buttons[value] = (button, row)
            card.column.addWidget(row)
        # The depth belongs to the source: it is how far the crawl goes from
        # the page you name, and it means nothing for a folder or one file.
        self.depth_holder = QWidget()
        self.depth_layout = QHBoxLayout(self.depth_holder)
        self.depth_layout.setContentsMargins(0, 0, 0, 0)
        self.depth_layout.setSpacing(6)
        self.depth_note = QLabel()
        self.depth_note.setProperty("class", theme.CLASS_MUTED)
        self.depth_layout.addWidget(self.depth_note)
        card.column.addWidget(self.depth_holder)
        card.column.addWidget(self._build_project_block())
        card.column.addWidget(self._build_profile_block())
        card.column.addStretch(1)
        self.source_card = card
        return card

    def _build_project_block(self) -> QWidget:
        """What the chosen folder turned out to be, and two things that
        follow from it: what its documents are for, and whether the
        exclusions the stack implies should stand.

        Shown only for a folder, and only there because that is where both
        questions exist: a crawled site has no `vendor/` to skip and no
        `.eml` to mistake for a page.

        The exclusions are the point. Until now the window applied only the
        flat default list while `xanalyze audit` also applied the detected
        stack's - so the same WordPress folder produced hundreds of findings
        in vendored core from the window and none from the CLI. Applying them
        without saying so would trade that for the opposite failure: a scan
        that quietly skipped a directory the person does maintain. So it is
        stated, with the profile's own evidence in reach, and it can be
        lifted in one click.
        """
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)

        self.project_title = QLabel(t("setup_project_title", self.lang))
        self.project_title.setProperty("class", theme.CLASS_FIELD_LABEL)
        column.addWidget(self.project_title)

        self.project_note = QLabel()
        self.project_note.setProperty("class", theme.CLASS_MUTED)
        self.project_note.setWordWrap(True)
        column.addWidget(self.project_note)

        self.project_lift_box = QCheckBox(t("setup_project_lift", self.lang))
        self.project_lift_box.toggled.connect(
            self.app_state.set_project_excludes_lifted)
        column.addWidget(self.project_lift_box)
        self.project_lift_hint = QLabel(t("setup_project_lift_hint", self.lang))
        self.project_lift_hint.setProperty("class", theme.CLASS_MUTED)
        self.project_lift_hint.setWordWrap(True)
        column.addWidget(self.project_lift_hint)

        self.medium_label = QLabel(t("setup_project_medium", self.lang))
        self.medium_label.setProperty("class", theme.CLASS_FIELD_LABEL)
        column.addWidget(self.medium_label)
        self.medium_combo = QComboBox()
        self.medium_combo.currentIndexChanged.connect(self._on_medium_changed)
        column.addWidget(self.medium_combo)
        self.medium_hint = QLabel(t("setup_project_medium_hint", self.lang))
        self.medium_hint.setProperty("class", theme.CLASS_MUTED)
        self.medium_hint.setWordWrap(True)
        column.addWidget(self.medium_hint)

        self.project_block = holder
        self._fill_media()
        return holder

    def _build_profile_block(self) -> QWidget:
        """What the target asked the run to switch on, and why.

        The profile used to be a caption: it named the stack and changed
        nothing, so a person who chose an SPFx checkout still had to know
        that `--web-parts` existed and that it needed the site's address.
        Now it decides - and every decision it makes is on screen with the
        marker file that justified it, because a default that changes the
        run without saying so is the failure this block exists to avoid.

        Shown for any source, unlike the project block above: the case that
        needs it most is a *site* paired with a checkout.
        """
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)

        # Which project, when the folder holds more than one. A list rather
        # than a text field: twenty SPFx solutions is something to pick from,
        # not something to spell.
        self.project_label = QLabel(t("setup_project_which", self.lang))
        self.project_label.setProperty("class", theme.CLASS_FIELD_LABEL)
        column.addWidget(self.project_label)
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_chosen)
        column.addWidget(self.project_combo)

        self.web_parts_box = QCheckBox(t("setup_web_parts", self.lang))
        self.web_parts_box.toggled.connect(self.app_state.set_web_parts)
        column.addWidget(self.web_parts_box)

        # `--no-session`: read the site the way a stranger sees it. Only for
        # a site, because a folder has no door and a local file no session.
        self.no_session_box = QCheckBox(t("setup_no_session", self.lang))
        self.no_session_box.toggled.connect(self.app_state.set_no_session)
        column.addWidget(self.no_session_box)
        self.no_session_hint = QLabel(t("setup_no_session_hint", self.lang))
        self.no_session_hint.setProperty("class", theme.CLASS_MUTED)
        self.no_session_hint.setWordWrap(True)
        column.addWidget(self.no_session_hint)

        # `--start-command` and `--dev-server-port`. Detection reads one
        # script name out of `package.json`, and a monorepo has several: the
        # root's `dev` is not the same server as an application's. Shown
        # only where there is a server to start.
        self.start_command_label = QLabel(t("setup_start_command", self.lang))
        self.start_command_label.setProperty("class", theme.CLASS_FIELD_LABEL)
        column.addWidget(self.start_command_label)
        self.start_command_edit = QLineEdit()
        self.start_command_edit.setPlaceholderText(
            t("setup_start_command_placeholder", self.lang))
        self.start_command_edit.textChanged.connect(
            self.app_state.set_start_command)
        column.addWidget(self.start_command_edit)
        self.dev_port_label = QLabel(t("setup_dev_port", self.lang))
        self.dev_port_label.setProperty("class", theme.CLASS_FIELD_LABEL)
        column.addWidget(self.dev_port_label)
        self.dev_port_spin = QSpinBox()
        self.dev_port_spin.setRange(0, 65535)
        self.dev_port_spin.setSpecialValueText(
            t("setup_dev_port_auto", self.lang))
        self.dev_port_spin.valueChanged.connect(
            self.app_state.set_dev_server_port)
        column.addWidget(self.dev_port_spin)

        self.profile_note = QLabel()
        self.profile_note.setProperty("class", theme.CLASS_MUTED)
        self.profile_note.setWordWrap(True)
        column.addWidget(self.profile_note)

        self.projects_note = QLabel()
        self.projects_note.setProperty("class", theme.CLASS_MUTED)
        self.projects_note.setWordWrap(True)
        column.addWidget(self.projects_note)

        self.profile_block = holder
        return holder

    def _on_project_chosen(self, _index: int) -> None:
        self.app_state.set_chosen_project(self.project_combo.currentData() or "")

    def _fill_projects(self, plan) -> None:
        """Offer the projects in this folder, or hide the question."""
        several = plan is not None and plan.ambiguous()
        self.project_label.setVisible(several)
        self.project_combo.setVisible(several)
        if not several:
            # A choice made inside another folder does not survive it: the
            # name belonged to that folder, and carrying it over would audit
            # a path that is no longer under the target.
            self.app_state.set_chosen_project("")
            return
        from pathlib import Path

        current = self.app_state.chosen_project
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem(t("setup_project_whole", self.lang),
                                   userData="")
        for profile in plan.projects:
            self.project_combo.addItem(Path(profile.root).name,
                                       userData=profile.root)
        index = self.project_combo.findData(current)
        self.project_combo.setCurrentIndex(max(index, 0))
        self.project_combo.blockSignals(False)
        if index < 0 and current:
            self.app_state.set_chosen_project("")

    def _refresh_profile(self) -> None:
        """The suggestions, their reasons, and the several-projects question."""
        import run_profile

        plan = self.app_state.run_plan
        self._fill_projects(plan)
        if plan is None:
            self.profile_block.setVisible(False)
            return
        wants_parts = plan.suggestion("web_parts") is not None
        self.web_parts_box.setVisible(wants_parts)
        if wants_parts:
            self.web_parts_box.blockSignals(True)
            self.web_parts_box.setChecked(self.app_state.web_parts)
            self.web_parts_box.blockSignals(False)

        lines = [run_profile.explain(item, self.lang)
                 for item in plan.suggestions if plan.applies(item.option)]
        lines += [run_profile.explain(prompt, self.lang, enabled=False)
                  for prompt in plan.prompts]
        self.profile_note.setText("  ".join(lines))
        self.profile_note.setVisible(bool(lines))

        # A site can be read signed out; a folder and a file cannot.
        site = self.app_state.source == SOURCE_SITE
        self.no_session_box.setVisible(site)
        self.no_session_hint.setVisible(site)
        if site:
            self.no_session_box.blockSignals(True)
            self.no_session_box.setChecked(self.app_state.no_session)
            self.no_session_box.blockSignals(False)

        # The dev-server overrides, only where a server exists to override.
        serves = bool(getattr(plan, "servers", ()))
        for widget in (self.start_command_label, self.start_command_edit,
                       self.dev_port_label, self.dev_port_spin):
            widget.setVisible(serves)

        several = plan.ambiguous()
        if several:
            from pathlib import Path

            names = ", ".join(Path(p.root).name for p in plan.projects[:4])
            self.projects_note.setText(t("setup_projects_several", self.lang)
                                       .format(count=len(plan.projects),
                                               names=names))
        self.projects_note.setVisible(several)
        self.profile_block.setVisible(bool(lines) or wants_parts or several
                                      or site or serves)

    def _fill_media(self) -> None:
        current = (self.medium_combo.currentData()
                   if self.medium_combo.count() else self.app_state.medium)
        self.medium_combo.blockSignals(True)
        self.medium_combo.clear()
        for value in MEDIA:
            self.medium_combo.addItem(
                t(f"setup_medium_{value or 'auto'}", self.lang), userData=value)
        index = self.medium_combo.findData(current or "")
        self.medium_combo.setCurrentIndex(max(index, 0))
        self.medium_combo.blockSignals(False)

    def _on_medium_changed(self, _index: int) -> None:
        self.app_state.set_medium(self.medium_combo.currentData() or "")

    #: How many excluded patterns are named before the rest become a count.
    #: Enough to recognise the stack's shape; a folder card is not the place
    #: for a twenty-line list, and the full one is a click away in the
    #: exclusions dialog.
    PATTERNS_SHOWN = 4

    def _refresh_project(self) -> None:
        folder = self.app_state.source == SOURCE_REPO
        self.project_block.setVisible(folder)
        if not folder:
            return
        profile = self.app_state.project
        stacks = [stack.name for stack in getattr(profile, "stacks", ())]
        if not stacks:
            self.project_note.setText(t("setup_project_none", self.lang))
            self.project_note.setToolTip("")
            self.project_lift_box.setVisible(False)
            self.project_lift_hint.setVisible(False)
            return
        patterns = profile.excludes()
        shown = ", ".join(patterns[:self.PATTERNS_SHOWN])
        if len(patterns) > self.PATTERNS_SHOWN:
            shown += ", …"
        lines = [t("setup_project_detected", self.lang).format(
            stacks=", ".join(stacks))]
        if patterns:
            lines.append(t("setup_project_excluded", self.lang).format(
                count=len(patterns), patterns=shown))
        self.project_note.setText("  ".join(lines))
        # Why each stack was decided, verbatim from the profile: a wrong
        # answer has to be arguable, and it is only arguable if the marker
        # file that produced it is in reach.
        self.project_note.setToolTip("\n".join(profile.reasons()))
        self.project_lift_box.setVisible(bool(patterns))
        self.project_lift_hint.setVisible(bool(patterns))
        self.project_lift_box.blockSignals(True)
        self.project_lift_box.setChecked(self.app_state.project_excludes_lifted)
        self.project_lift_box.blockSignals(False)

    def _build_reading_card(self) -> QWidget:
        card = SetupCard("setup_step_reading", self.lang)
        self.reading_rows = {}
        for key, hint_key in (("setup_reading_code", "setup_reading_code_hint"),
                              ("setup_reading_browser", "setup_reading_browser_hint")):
            row = _two_line(t(key, self.lang), t(hint_key, self.lang))
            self.reading_rows[key] = row
            card.column.addWidget(row)
        self.reading_note = QLabel(t("setup_reading_note", self.lang))
        self.reading_note.setProperty("class", theme.CLASS_MUTED)
        self.reading_note.setWordWrap(True)
        card.column.addWidget(self.reading_note)
        card.column.addStretch(1)
        self.reading_card = card
        return card

    def _build_question_card(self) -> QWidget:
        card = SetupCard("setup_step_question", self.lang)
        self.check_boxes = {}
        for value, label_key, hint_key in (
                (CHECK_ACCESSIBILITY, "check_accessibility",
                 "setup_check_accessibility_hint"),
                (CHECK_AI_PATTERNS, "check_ai_patterns", "setup_check_ai_hint")):
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            box = QCheckBox()
            box.toggled.connect(self._on_checks_toggled)
            line.addWidget(box)
            line.addWidget(_two_line(t(label_key, self.lang), ""), stretch=1)
            self.check_boxes[value] = (box, row, hint_key, line)
            card.column.addWidget(row)
        self.checks_note = QLabel()
        self.checks_note.setProperty("class", theme.CLASS_MUTED)
        self.checks_note.setWordWrap(True)
        card.column.addWidget(self.checks_note)
        card.column.addStretch(1)
        self.question_card = card
        return card

    def _build_judge_card(self) -> QWidget:
        card = SetupCard("setup_step_judge", self.lang)
        self.method_buttons = {}
        self.method_group = QButtonGroup(self)
        self.method_group.setExclusive(True)
        for value, label_key, hint_key, needs_account in METHODS:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            button = QRadioButton()
            button.toggled.connect(
                lambda checked, chosen=value:
                checked and self.app_state.set_methods((chosen,)))
            self.method_group.addButton(button)
            line.addWidget(button)
            line.addWidget(_two_line(t(label_key, self.lang),
                                     t(hint_key, self.lang)), stretch=1)
            self.method_buttons[value] = (button, row, needs_account)
            card.column.addWidget(row)
        self.account_note = QLabel()
        self.account_note.setProperty("class", theme.CLASS_MUTED)
        self.account_note.setWordWrap(True)
        card.column.addWidget(self.account_note)
        card.column.addStretch(1)
        self.judge_card = card
        return card

    def _build_report_card(self) -> QWidget:
        """Category, certainty and site controls: `--category`,
        `--confidence` and `--site-controls`, which the CLI has had all
        along and the window did not (`P-23`).

        The first two are a view over one finished pass, so they are wired
        to `AppState` and read again every time the list is built, and the
        third is a run choice: two extra requests to the same domain, which
        is why it is off until asked for and hidden for a folder or a file.
        """
        card = SetupCard("setup_step_report", self.lang)
        row = QHBoxLayout()
        row.setSpacing(16)

        self.category_boxes = {}
        categories_holder = QWidget()
        categories_column = QVBoxLayout(categories_holder)
        categories_column.setContentsMargins(0, 0, 0, 0)
        categories_column.setSpacing(4)
        self.categories_label = QLabel(t("setup_report_categories", self.lang))
        self.categories_label.setProperty("class", theme.CLASS_FIELD_LABEL)
        categories_column.addWidget(self.categories_label)
        # Wraps rather than pushes. Six labelled boxes in a row need about
        # 700px, and a box layout hands that width to the window as its own
        # minimum - which is the exact regression the top row was rebuilt to
        # avoid (`test_window_shell`, the 1271px floor). At 900px the chips
        # take a second line and the window still opens at 900px.
        chip_holder = QWidget()
        chips = FlowLayout(chip_holder, margin=0, spacing=8)
        chips.setContentsMargins(0, 0, 0, 0)
        for value in CATEGORIES:
            box = QCheckBox(t(f"audit_category_{value}", self.lang))
            box.setProperty("class", "filter-chip")
            box.setMinimumHeight(34)
            box.toggled.connect(self._on_categories_toggled)
            self.category_boxes[value] = box
            chips.addWidget(box)
        categories_column.addWidget(chip_holder)
        self.categories_hint = QLabel(t("setup_report_categories_hint", self.lang))
        self.categories_hint.setProperty("class", theme.CLASS_MUTED)
        self.categories_hint.setWordWrap(True)
        categories_column.addWidget(self.categories_hint)
        row.addWidget(categories_holder, stretch=1)

        certainty_holder = QWidget()
        certainty_column = QVBoxLayout(certainty_holder)
        certainty_column.setContentsMargins(0, 0, 0, 0)
        certainty_column.setSpacing(4)
        self.certainty_label = QLabel(t("setup_report_certainty", self.lang))
        self.certainty_label.setProperty("class", theme.CLASS_FIELD_LABEL)
        certainty_column.addWidget(self.certainty_label)
        self.certainty_combo = QComboBox()
        self.certainty_combo.currentIndexChanged.connect(self._on_certainty_changed)
        certainty_column.addWidget(self.certainty_combo)
        self.certainty_hint = QLabel(t("setup_report_certainty_hint", self.lang))
        self.certainty_hint.setProperty("class", theme.CLASS_MUTED)
        self.certainty_hint.setWordWrap(True)
        certainty_column.addWidget(self.certainty_hint)
        row.addWidget(certainty_holder, stretch=1)

        card.column.addLayout(row)

        self.unsettled_box = QCheckBox(t("setup_report_unsettled", self.lang))
        self.unsettled_box.toggled.connect(self.app_state.set_unsettled)
        card.column.addWidget(self.unsettled_box)
        self.unsettled_hint = QLabel(t("setup_report_unsettled_hint", self.lang))
        self.unsettled_hint.setProperty("class", theme.CLASS_MUTED)
        self.unsettled_hint.setWordWrap(True)
        card.column.addWidget(self.unsettled_hint)

        self.site_controls_box = QCheckBox(
            t("setup_report_site_controls", self.lang))
        self.site_controls_box.toggled.connect(self.app_state.set_site_controls)
        card.column.addWidget(self.site_controls_box)
        self.site_controls_hint = QLabel(
            t("setup_report_site_controls_hint", self.lang))
        self.site_controls_hint.setProperty("class", theme.CLASS_MUTED)
        self.site_controls_hint.setWordWrap(True)
        card.column.addWidget(self.site_controls_hint)

        self.report_card = card
        self._fill_certainties()
        return card

    def _fill_certainties(self) -> None:
        current = (self.certainty_combo.currentData()
                   if self.certainty_combo.count() else self.app_state.confidence_floor)
        self.certainty_combo.blockSignals(True)
        self.certainty_combo.clear()
        for value in CERTAINTIES:
            label = (t("certainty_any", self.lang) if not value
                     else t(f"certainty_{value}", self.lang))
            self.certainty_combo.addItem(label, userData=value)
        index = self.certainty_combo.findData(current or "")
        self.certainty_combo.setCurrentIndex(max(index, 0))
        self.certainty_combo.blockSignals(False)

    def _on_categories_toggled(self, _checked: bool) -> None:
        chosen = tuple(value for value, box in self.category_boxes.items()
                       if box.isChecked())
        # Every box ticked and none ticked are the same request - show all
        # six - and storing the first as a list would make a later category
        # invisible to anyone who had once ticked the boxes by hand.
        if len(chosen) == len(CATEGORIES):
            chosen = ()
        self.app_state.set_categories(chosen)

    def _on_certainty_changed(self, _index: int) -> None:
        self.app_state.set_confidence_floor(self.certainty_combo.currentData() or "")

    # ------------------------------------------------------------ filling

    def _on_checks_toggled(self, _checked: bool) -> None:
        chosen = tuple(value for value, (box, *_rest) in self.check_boxes.items()
                       if box.isChecked())
        # Neither question asked is not a run, it is a walk over the pages
        # with nothing to say about them, so the state keeps the last one.
        if chosen:
            self.app_state.set_checks(chosen)
        self.refresh()

    def retranslate(self, lang: str) -> None:
        self.lang = lang
        self.title.setText(t("setup_title", lang))
        self.subtitle.setText(t("setup_subtitle", lang))
        self.reading_note.setText(t("setup_reading_note", lang))
        self.drop_title.setText(t("setup_drop_title", lang))
        self.drop_note.setText(t("setup_drop_note", lang))
        self.drop_choose_btn.setText(t("setup_drop_choose", lang))
        self.report_card.step.setText(t("setup_step_report", lang))
        self.categories_label.setText(t("setup_report_categories", lang))
        self.categories_hint.setText(t("setup_report_categories_hint", lang))
        self.certainty_label.setText(t("setup_report_certainty", lang))
        self.certainty_hint.setText(t("setup_report_certainty_hint", lang))
        self.unsettled_box.setText(t("setup_report_unsettled", lang))
        self.unsettled_hint.setText(t("setup_report_unsettled_hint", lang))
        self.site_controls_box.setText(t("setup_report_site_controls", lang))
        self.site_controls_hint.setText(t("setup_report_site_controls_hint", lang))
        for value, box in self.category_boxes.items():
            box.setText(t(f"audit_category_{value}", lang))
        self.project_title.setText(t("setup_project_title", lang))
        self.web_parts_box.setText(t("setup_web_parts", lang))
        self.project_label.setText(t("setup_project_which", lang))
        self.no_session_box.setText(t("setup_no_session", lang))
        self.no_session_hint.setText(t("setup_no_session_hint", lang))
        self.start_command_label.setText(t("setup_start_command", lang))
        self.start_command_edit.setPlaceholderText(
            t("setup_start_command_placeholder", lang))
        self.dev_port_label.setText(t("setup_dev_port", lang))
        self.dev_port_spin.setSpecialValueText(t("setup_dev_port_auto", lang))
        self.project_lift_box.setText(t("setup_project_lift", lang))
        self.project_lift_hint.setText(t("setup_project_lift_hint", lang))
        self.medium_label.setText(t("setup_project_medium", lang))
        self.medium_hint.setText(t("setup_project_medium_hint", lang))
        self._fill_certainties()
        self._fill_media()
        self.refresh()

    def refresh(self) -> None:
        """Every control back from `AppState`, which is what actually holds
        the run. Written this way round so that a choice made in the top row
        shows here too, rather than the two drifting apart."""
        state = self.app_state
        for value, (button, _row) in self.source_buttons.items():
            button.blockSignals(True)
            button.setChecked(state.source == value)
            button.blockSignals(False)

        self._refresh_profile()
        site = state.source == SOURCE_SITE
        self.depth_holder.setVisible(site)
        self.depth_note.setText(t("setup_depth_zero", self.lang))

        # Card 2 states what the chosen source means, and only the readings
        # that will actually happen.
        readers = state.readers
        self.reading_rows["setup_reading_browser"].setVisible(
            READER_BROWSER in readers)

        for value, (box, _row, hint_key, line) in self.check_boxes.items():
            box.blockSignals(True)
            box.setChecked(value in state.checks)
            box.blockSignals(False)
        self.checks_note.setText(
            t("setup_checks_note", self.lang) if len(state.checks) > 1
            else t("setup_checks_one_at_least", self.lang))

        ai_ready = state.ai_available
        for value, (button, row, needs_account) in self.method_buttons.items():
            button.blockSignals(True)
            button.setChecked(value in state.methods)
            button.blockSignals(False)
            if needs_account:
                button.setEnabled(ai_ready)
                row.setEnabled(ai_ready)
        self.account_note.setText("" if ai_ready
                                  else t("setup_method_needs_account", self.lang))
        self.account_note.setVisible(not ai_ready)
        # The categories and the certainty are about audit findings, so the
        # card says nothing while nothing is being audited - a control that
        # governs a list nobody asked for is a control that lies about what
        # the run will do.
        auditing = CHECK_ACCESSIBILITY in state.checks
        self.report_card.setEnabled(auditing)
        chosen = set(state.categories)
        for value, box in self.category_boxes.items():
            box.blockSignals(True)
            box.setChecked(value in chosen)
            box.blockSignals(False)
        index = self.certainty_combo.findData(state.confidence_floor or "")
        if index >= 0 and index != self.certainty_combo.currentIndex():
            self.certainty_combo.blockSignals(True)
            self.certainty_combo.setCurrentIndex(index)
            self.certainty_combo.blockSignals(False)
        self.unsettled_box.blockSignals(True)
        self.unsettled_box.setChecked(state.unsettled)
        self.unsettled_box.blockSignals(False)
        # Two extra requests to a domain, so it exists only where there is a
        # domain: a folder and a single file have no robots.txt to read.
        site = state.source == SOURCE_SITE
        self.site_controls_box.setVisible(site)
        self.site_controls_hint.setVisible(site)
        self.site_controls_box.blockSignals(True)
        self.site_controls_box.setChecked(state.site_controls)
        self.site_controls_box.blockSignals(False)
        self._refresh_project()
        self._refresh_drop_zone()
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        state = self.app_state
        source_key = {SOURCE_SITE: "source_site", SOURCE_REPO: "source_repo",
                      SOURCE_FILE: "source_file"}[state.source]
        readers = ", ".join(
            t("setup_reading_browser" if reader == READER_BROWSER
              else "setup_reading_code", self.lang).lower()
            for reader in state.readers)
        checks = (t("checks_both", self.lang) if len(state.checks) > 1
                  else t("check_accessibility" if CHECK_ACCESSIBILITY in state.checks
                         else "check_ai_patterns", self.lang))
        method_key = {METHOD_LOCAL: "method_local", METHOD_EMBEDDING: "method_embedding",
                      METHOD_AI: "method_both"}.get(
                          state.methods[0] if state.methods else METHOD_LOCAL,
                          "method_local")

        def strong(text: str) -> str:
            return f"<b>{text}</b>"

        self.summary.setText(t("setup_summary", self.lang).format(
            source=t(source_key, self.lang),
            target=strong(state.target or "…"),
            reading=strong(readers),
            # Not lowercased: "AI" is not a word that has a small form, and
            # the label already reads as a phrase in the middle of a sentence.
            checks=strong(checks),
            method=strong(t(method_key, self.lang).lower()),
        ))
