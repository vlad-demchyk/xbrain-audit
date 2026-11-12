"""Settings: five sections in a rail, and a row per decision (3d, 3q).

This exists mainly to keep the main window's toolbar short. Everything you
set once and rarely change (language, which account pays for rewrites, API
keys, endpoint mapping) lives here; the toolbar keeps only what you touch
on every scan (source, target, detector, Analyze).

The design replaced the tab strip with a rail down the left and full-width
form fields with **rows**: the label on the left, a small control on the
right, a hairline between them. The reason is not decoration. A settings
screen is read as a list of statements about how the tool behaves, and a
row says one; a stretched combo box in a two-column form makes the control
look like the subject and the sentence like its caption.

Three shapes, chosen by what the choice is:

- a **switch** for on/off, because that is the row's state rather than one
  item picked out of several;
- a **segmented control** for two to four alternatives, where seeing the
  options is the explanation (theme, effort);
- a **combo box** only where the list is long or open-ended (language,
  model).

What the design shows and this does not build is listed in
`_UNBUILT_ROWS` - a control that saves nothing is worse than a missing one.
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QScrollArea,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

import cli_install
import config
from i18n.translations import LANGUAGES, t
from llm import credentials
from llm.base import LLMAuthError, LLMProviderFactory, LLMUnavailable
from ui import theme
from ui.widgets import Segmented, Switch, muted

#: Rows the artboards draw that this screen does not, and why. Each one is a
#: control over a setting that does not exist in `config.Settings`, and a
#: control that saves nothing is worse than a missing one - it is a promise
#: the next run does not keep. Kept as a list rather than as a comment
#: because it is the to-do for whoever adds the setting behind one.
_UNBUILT_ROWS = {
    "browser pass by default": "no such setting; the browser pass is a "
                               "per-run choice made in the window",
    "daily update check": "the updater is asked when it is opened, never on "
                          "a schedule",
    "documents folder": "the run folder is derived from the target, one "
                        "folder per target, and is not configurable",
    "render timeout": "the watchdog's timeout is a constant in the browser "
                      "pass, not a setting",
}

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_XFORMAT = "xformat"

def _select_data(combo, value) -> None:
    """Select the entry whose `userData` is `value`, if there is one.

    Falls back to leaving the current index alone rather than to index 0: a
    settings file holding a model this build does not offer should show as
    unrecognised, not be silently rewritten to the first item on save.
    """
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


class SettingsDialog(QDialog):
    def __init__(self, settings: config.Settings, lang: str, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.lang = lang
        self._xformat_provider = None
        # Used for the handful of things QSS class selectors don't reach
        # here: the status colours (success/error are semantic, not literal
        # hex codes chosen to match one theme) and one indent.
        self._palette = theme.current_palette(settings.theme)
        # The application may still carry Qt's unresolved "Sans Serif"
        # default. Dialog children inherit this concrete installed family.
        self.setFont(QFont(self._palette.font))
        self._original_palette = getattr(parent, "palette_tokens", self._palette)
        self._original_stylesheet = QApplication.instance().styleSheet()
        self._theme_previewed = False

        self.setWindowTitle(t("settings_title", lang))
        self.resize(820, 560)

        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.stack = QStackedWidget()
        body.addWidget(self._build_rail(), stretch=0)
        panel = QWidget()
        panel.setProperty("class", theme.CLASS_PANEL)
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel_column = QVBoxLayout(panel)
        panel_column.setContentsMargins(12, 8, 12, 8)
        panel_column.addWidget(self.stack)
        body.addWidget(panel, stretch=1)
        outer.addLayout(body, stretch=1)
        outer.addWidget(self._build_footer())

        # The order of the rail is the order of the design: the account
        # first, because "who reads the text and who pays" is the setting
        # people come here for, and the endpoint JSON last.
        for key, page in (
            ("provider", self._build_provider_tab()),
            ("general", self._build_general_tab()),
            ("unicode", self._build_unicode_tab()),
            ("noise", self._build_suppression_tab()),
            ("advanced", self._build_advanced_tab()),
        ):
            self._add_page(key, page)
        self._rail_buttons[1].setChecked(True)
        self.stack.setCurrentIndex(1)

        self._refresh_provider_ui()

    # ------------------------------------------------------------- shell

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        column = QVBoxLayout(rail)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        title = QLabel(t("settings_title", self.lang))
        title.setProperty("class", theme.CLASS_HEADING)
        column.addWidget(title)
        column.addSpacing(4)

        self._rail_host = QVBoxLayout()
        self._rail_host.setSpacing(2)
        column.addLayout(self._rail_host)
        column.addStretch(1)

        # The full path is available on hover, while the rail shows only the
        # filename. Long home-directory paths wrap into a second paragraph
        # here and steal attention from the setting sections.
        config_path = config.config_file()
        where = muted(config_path.name)
        where.setToolTip(str(config_path))
        where.setWordWrap(False)
        where.setProperty("class", theme.CLASS_CODE)
        column.addWidget(where)

        rail.setFixedWidth(210)
        self._rail_group = QButtonGroup(self)
        self._rail_group.setExclusive(True)
        self._rail_buttons: list = []
        return rail

    def _add_page(self, key: str, page: QWidget) -> None:
        button = QPushButton(t(f"settings_tab_{key}", self.lang))
        button.setProperty("class", theme.CLASS_RAIL_ITEM)
        button.setCheckable(True)
        index = self.stack.count()
        self._rail_group.addButton(button, index)
        button.clicked.connect(lambda _=False, i=index: self.stack.setCurrentIndex(i))
        self._rail_host.addWidget(button)
        self._rail_buttons.append(button)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.stack.addWidget(scroll)

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        row = QHBoxLayout(foot)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        note = muted(t("settings_keys_note", self.lang))
        note.setWordWrap(True)
        row.addWidget(note, stretch=1)

        cancel = QPushButton(t("cancel_button", self.lang))
        cancel.setProperty("class", theme.CLASS_QUIET)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)

        save = QPushButton(t("save_button", self.lang))
        save.setProperty("class", theme.CLASS_PRIMARY)
        save.clicked.connect(self._on_accept)
        row.addWidget(save)
        self.save_btn, self.cancel_btn = save, cancel
        return foot

    # -------------------------------------------------------------- rows

    def _page(self) -> tuple:
        """An empty settings page and the column its rows go in."""
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(0)
        return page, column

    def _row(self, label: str, control: QWidget, note: str = "") -> QWidget:
        """One statement: what it is on the left, what it is set to on the right."""
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 6, 0, 6)
        line.setSpacing(8)

        text = QWidget()
        stack = QVBoxLayout(text)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(1)
        name = QLabel(label)
        name.setWordWrap(True)
        stack.addWidget(name)
        if note:
            hint = muted(note)
            hint.setWordWrap(True)
            stack.addWidget(hint)
        line.addWidget(text, stretch=1)
        line.addWidget(control, stretch=0, alignment=Qt.AlignmentFlag.AlignRight)
        return row

    def _rule(self) -> QWidget:
        rule = QWidget()
        rule.setFixedHeight(1)
        rule.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # `rule`, not `divider`: the artboards draw the line between two rows
        # inside a panel as #eeebe5, which is lighter than the tick between
        # two inline values in a filled strip.
        rule.setProperty("class", "settings-rule")
        return rule

    def _section(self, column, title: str, note: str = "") -> None:
        heading = QLabel(title)
        heading.setProperty("class", theme.CLASS_FIELD_LABEL)
        column.addSpacing(6)
        column.addWidget(heading)
        if note:
            hint = muted(note)
            hint.setWordWrap(True)
            column.addWidget(hint)

    def _rows(self, column, rows) -> None:
        """Add rows with a hairline between them, and none after the last."""
        for index, widget in enumerate(rows):
            if index:
                column.addWidget(self._rule())
            column.addWidget(widget)

    def _switch(self, checked: bool) -> Switch:
        control = Switch(self._palette)
        control.setChecked(checked)
        return control

    # ------------------------------------------------------------- tabs

    def _build_general_tab(self) -> QWidget:
        page, column = self._page()

        self.lang_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, userData=code)
        index = self.lang_combo.findData(self.settings.ui_language)
        self.lang_combo.setCurrentIndex(max(index, 0))

        self.theme_seg = Segmented([(t(f"theme_{value}", self.lang), value)
                                    for value in ("auto", "light", "dark")])
        self.theme_seg.set_current_data(self.settings.theme)
        # Applied as it changes rather than on Save: a colour scheme is judged
        # by looking at it, and a preview that needs a dialog round-trip is
        # not a preview.
        self.theme_seg.changed.connect(self._on_theme_changed)

        self.max_pages_spin = QSpinBox()
        self.max_pages_spin.setRange(1, 500)
        self.max_pages_spin.setValue(self.settings.max_pages)
        self.max_pages_spin.setFixedWidth(90)

        # `--max-files`. A monorepo hits this and the run says so through
        # `ScanDiagnostics.truncated`; before this the number itself was not
        # reachable from the window at all.
        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(100, 200000)
        self.max_files_spin.setSingleStep(500)
        self.max_files_spin.setValue(self.settings.max_files)
        self.max_files_spin.setFixedWidth(110)

        self.unicode_enabled_box = self._switch(self.settings.unicode_check_enabled)
        self.devserver_switch = self._switch(self.settings.auto_start_devserver)

        self._rows(column, [
            self._row(t("ui_language_label_full", self.lang), self.lang_combo),
            # The shared key ends in a colon because the window's toolbar
            # uses it as a field label; a row is a statement, not a field.
            self._row(t("theme_label", self.lang).rstrip(":"), self.theme_seg),
            self._row(t("settings_max_pages", self.lang), self.max_pages_spin),
            self._row(t("settings_max_files", self.lang), self.max_files_spin,
                      t("settings_max_files_note", self.lang)),
            self._row(t("settings_unicode_enabled", self.lang),
                      self.unicode_enabled_box),
            self._row(t("settings_devserver_row", self.lang),
                      self.devserver_switch,
                      t("settings_devserver_note", self.lang)),
        ])
        column.addStretch(1)
        return page

    def _on_theme_changed(self) -> None:
        from PySide6.QtWidgets import QApplication
        from ui import theme

        app = QApplication.instance()
        if app is None:
            return
        self._theme_previewed = True
        palette = theme.apply_theme(app, self.theme_seg.current_data() or "auto")
        self._palette = palette
        # Two things paint themselves rather than being styled, and both have
        # to be handed the new palette: the findings delegate in the window,
        # and every switch on this screen.
        for switch in self.findChildren(Switch):
            switch.set_palette(palette)
        window = self.parent()
        if window is not None and hasattr(window, "apply_palette"):
            window.apply_palette(palette)

    def done(self, result: int) -> None:
        if result == QDialog.DialogCode.Rejected and self._theme_previewed:
            QApplication.instance().setStyleSheet(self._original_stylesheet)
            self._palette = self._original_palette
            for switch in self.findChildren(Switch):
                switch.set_palette(self._original_palette)
            window = self.parent()
            if window is not None and hasattr(window, "apply_palette"):
                window.apply_palette(self._original_palette)
            self._theme_previewed = False
        super().done(result)

    def _build_unicode_tab(self) -> QWidget:
        """Artboard 3q: one row per category, with what it actually catches.

        The old tab was five checkboxes with category names on them, which
        means the choice could only be made by someone who already knew what
        "styled" covers. Each row now shows an example of the characters it
        is about - that is the difference between a setting and a quiz.
        """
        page, column = self._page()
        self._section(column, t("settings_tab_unicode", self.lang),
                      t("settings_unicode_note", self.lang))

        active = set(self.settings.unicode_categories or [])
        self.category_boxes: dict = {}
        rows = []
        for key in ("invisible", "space", "homoglyph", "styled", "typography"):
            switch = self._switch(key in active)
            self.category_boxes[key] = switch
            rows.append(self._row(t(f"settings_cat_{key}", self.lang), switch,
                                  t(f"settings_cat_{key}_example", self.lang)))
        self._rows(column, rows)

        self.category_host = QWidget()
        host_column = QVBoxLayout(self.category_host)
        host_column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.category_host)

        # The master switch lives on the General page; the categories are
        # meaningless while it is off, and a row that still looks settable
        # would be the screen contradicting itself.
        for row in rows:
            self.unicode_enabled_box.toggled.connect(row.setEnabled)
            row.setEnabled(self.unicode_enabled_box.isChecked())

        column.addStretch(1)
        return page

    #: The three ways the AI pass can be paid for, in the order the design
    #: lists them, with the settings group each one owns.
    _PROVIDER_ROWS = (PROVIDER_XFORMAT, PROVIDER_ANTHROPIC, "claude-code")

    def _build_provider_tab(self) -> QWidget:
        """Who reads the text and who pays for it (artboard 3d).

        Three rows, one per account, each saying what *its own* state is -
        a key in the keychain, a session on this machine, a subscription -
        and the choice is which of them the run uses. The dropdown this
        replaces named the three but described none of them, so the answer
        to "why is the AI pass unavailable" was three group boxes down the
        page rather than on the row you were choosing.

        Every status on this page is read locally and cheaply. Asking the
        `claude` CLI takes a subprocess and up to thirty seconds, and the
        subscription's remaining quota is a network call - neither may
        happen while a settings screen is opening, so both sit behind the
        row's own Check button.
        """
        page, column = self._page()

        self.account_card = QWidget()
        self.account_card.setProperty("class", theme.CLASS_INSET)
        self.account_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card_row = QHBoxLayout(self.account_card)
        card_row.setContentsMargins(10, 8, 10, 8)
        card_row.setSpacing(8)
        self.account_initials = QLabel("")
        self.account_initials.setProperty("class", theme.CLASS_CHIP)
        card_row.addWidget(self.account_initials)
        card_text = QWidget()
        card_column = QVBoxLayout(card_text)
        card_column.setContentsMargins(0, 0, 0, 0)
        card_column.setSpacing(1)
        self.account_name = QLabel("")
        card_column.addWidget(self.account_name)
        self.account_note = muted("")
        self.account_note.setWordWrap(True)
        card_column.addWidget(self.account_note)
        card_row.addWidget(card_text, stretch=1)
        self.sign_out_btn = QPushButton(t("settings_sign_out", self.lang))
        self.sign_out_btn.setProperty("class", theme.CLASS_QUIET)
        self.sign_out_btn.clicked.connect(self._on_sign_out)
        card_row.addWidget(self.sign_out_btn)
        column.addWidget(self.account_card)

        self._section(column, t("settings_who_pays", self.lang),
                      t("settings_provider_note", self.lang))

        self.provider_group = QButtonGroup(self)
        self.provider_group.setExclusive(True)
        self.provider_buttons: dict = {}
        self.provider_details: dict = {}
        rows = []
        for name in self._PROVIDER_ROWS:
            rows.append(self._provider_row(name))
        self._rows(column, rows)
        self.provider_group.buttonClicked.connect(
            lambda *_: self._refresh_provider_ui())

        # The details of the chosen account, one group at a time. Shown
        # rather than merely enabled: two greyed-out boxes under the one in
        # use is three answers on screen to a question with one.
        for name in self._PROVIDER_ROWS:
            column.addWidget(self.provider_details[name])

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        column.addWidget(self.status_label)
        column.addStretch(1)
        return page

    def _provider_row(self, name: str) -> QWidget:
        choice = QRadioButton(self._provider_label(name))
        choice.setChecked(name == self.settings.llm_provider)
        self.provider_group.addButton(choice)
        choice.setProperty("provider", name)
        self.provider_buttons[name] = choice

        note = muted("")
        note.setWordWrap(True)
        self.provider_details[name] = self._provider_group_box(name)

        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 6, 0, 6)
        line.setSpacing(8)
        text = QWidget()
        stack = QVBoxLayout(text)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(1)
        stack.addWidget(choice)
        stack.addWidget(note)
        line.addWidget(text, stretch=1)

        check = QPushButton(t("settings_check", self.lang))
        check.setProperty("class", theme.CLASS_QUIET)
        check.clicked.connect(lambda _=False, n=name: self._on_check_status(n))
        line.addWidget(check)
        self.provider_notes = getattr(self, "provider_notes", {})
        self.provider_notes[name] = note
        self.provider_checks = getattr(self, "provider_checks", {})
        self.provider_checks[name] = check
        return row

    def _provider_label(self, name: str) -> str:
        """The account's name in the interface language.

        `display_name` on the provider classes is English and belongs to the
        log and the CLI; falling back to it here would put one English row
        in a Ukrainian list, which is the same defect the dialog's OK button
        had.
        """
        label = t(f"provider_name_{name}", self.lang)
        if label != f"provider_name_{name}":
            return label
        try:
            return LLMProviderFactory.create(name).display_name
        except Exception:  # noqa: BLE001 - a provider that cannot be built
            return name                                    # still has a row

    def _provider_group_box(self, name: str) -> QWidget:
        if name == PROVIDER_ANTHROPIC:
            box = QGroupBox("Anthropic")
            form = QFormLayout(box)
            self.api_key_edit = QLineEdit()
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            existing = config.get_anthropic_api_key()
            if existing:
                self.api_key_edit.setPlaceholderText("•••• " + existing[-4:])
            form.addRow(t("settings_api_key", self.lang), self.api_key_edit)
            self.model_edit = QLineEdit(self.settings.claude_model)
            form.addRow(t("settings_model", self.lang), self.model_edit)
            return box

        if name == "claude-code":
            # Its own box, because it is a different account from the one
            # above: this is the session already signed in on this machine,
            # and what it costs is a setting rather than a detail - the AI
            # pass runs over every block on a site.
            box = QGroupBox("Claude Code")
            form = QFormLayout(box)
            self.cc_model_combo = QComboBox()
            for label, value in (("—", ""), ("sonnet", "sonnet"),
                                 ("opus", "opus"), ("haiku", "haiku")):
                self.cc_model_combo.addItem(label, userData=value)
            _select_data(self.cc_model_combo, self.settings.claude_code_model)
            form.addRow(t("settings_cc_model", self.lang), self.cc_model_combo)
            # Segmented rather than a dropdown (3q): four short options, and
            # seeing them together is what says the setting is about how hard
            # the session thinks rather than which model runs.
            self.cc_effort_seg = Segmented(
                [(t("settings_as_session", self.lang), ""),
                 (t("effort_low", self.lang), "low"),
                 (t("effort_medium", self.lang), "medium"),
                 (t("effort_high", self.lang), "high")])
            self.cc_effort_seg.set_current_data(self.settings.claude_code_effort)
            form.addRow(t("settings_cc_effort", self.lang), self.cc_effort_seg)
            return box

        box = QGroupBox("app.xformat.net")
        layout = QVBoxLayout(box)
        form = QFormLayout()
        self.xformat_url_edit = QLineEdit(self.settings.xformat_base_url)
        form.addRow(t("settings_base_url", self.lang), self.xformat_url_edit)
        self.xformat_email_edit = QLineEdit(
            credentials.load_secret("xformat_account_email") or "")
        form.addRow(t("settings_email", self.lang), self.xformat_email_edit)
        self.xformat_password_edit = QLineEdit()
        self.xformat_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.xformat_password_edit.setPlaceholderText(
            t("settings_password_hint", self.lang))
        form.addRow(t("settings_password", self.lang), self.xformat_password_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.sign_in_btn = QPushButton(t("settings_sign_in", self.lang))
        self.sign_in_btn.clicked.connect(self._on_sign_in)
        buttons.addWidget(self.sign_in_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.storage_label = muted(
            t("settings_storage_keyring", self.lang) if credentials.using_keyring()
            else t("settings_storage_file", self.lang))
        self.storage_label.setWordWrap(True)
        layout.addWidget(self.storage_label)
        return box

    def _build_suppression_tab(self) -> QWidget:
        """The way in to noise control, not a second copy of it.

        This tab used to be five list boxes of raw values - the whole of the
        suppression UI, and the reason a dismissed finding was sixteen hex
        characters with a Remove button. The screen the design asks for
        (artboard 3k) reads the two lists apart, says what each hidden entry
        was and where the record lives, and can put one back into the list it
        is actually written in. Keeping the boxes here as well would be two
        editors of one fact, and the one that lies is always the other one.
        """
        w = QWidget()
        layout = QVBoxLayout(w)
        note = QLabel(t("suppression_note", self.lang))
        note.setWordWrap(True)
        note.setProperty("class", theme.CLASS_MUTED)
        layout.addWidget(note)

        # A count, so the tab says something before it is opened: an empty
        # panel with one button reads as a feature that is not set up, when
        # in fact it may be holding five decisions.
        self.noise_count = QLabel()
        self.noise_count.setProperty("class", theme.CLASS_MUTED)
        self._refresh_noise_count()
        layout.addWidget(self.noise_count)

        open_btn = QPushButton(t("noise_open", self.lang))
        open_btn.setProperty("class", theme.CLASS_QUIET)
        open_btn.clicked.connect(self._on_open_noise_control)
        row = QHBoxLayout()
        row.addWidget(open_btn)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addStretch(1)
        return w

    def _on_open_noise_control(self) -> None:
        from ui.window_parts.noise_control import NoiseDialog

        dialog = NoiseDialog(self.settings, self.lang,
                             root=self._project_ignore_root(),
                             palette=getattr(self.parent(), "palette_tokens", None),
                             parent=self)
        dialog.exec()
        self._refresh_noise_count()

    def _refresh_noise_count(self) -> None:
        import suppression

        total = sum(len(getattr(source.entries, level))
                    for source in suppression.sources(self.settings,
                                                      self._project_ignore_root())
                    for level in suppression.LEVELS)
        self.noise_count.setText(t("noise_count", self.lang).format(count=total))

    def _project_ignore_root(self) -> str | None:
        """The folder whose `.xaudit-ignore` is worth showing, if the
        window this dialog was opened from has one at the moment."""
        window = self.parent()
        for attr in ("repo_path_edit", "file_path_edit"):
            edit = getattr(window, attr, None)
            if edit is not None and edit.text().strip():
                return edit.text().strip()
        return None

    def _build_advanced_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        note = QLabel(t("settings_endpoints_note", self.lang))
        note.setWordWrap(True)
        note.setProperty("class", theme.CLASS_MUTED)
        layout.addWidget(note)

        self.endpoints_edit = QPlainTextEdit()
        self.endpoints_edit.setProperty("class", theme.CLASS_CODE)
        self.endpoints_edit.setPlainText(
            json.dumps(self.settings.xformat_endpoints or {}, indent=2, ensure_ascii=False)
        )
        self.endpoints_edit.setFont(QFont(self._palette.font_mono))
        layout.addWidget(self.endpoints_edit, stretch=1)

        defaults_btn = QPushButton(t("settings_show_defaults", self.lang))
        defaults_btn.clicked.connect(self._show_endpoint_defaults)
        layout.addWidget(defaults_btn)

        # Translated like everything else. It was English on the grounds of
        # being small and technical, which is a rule that ends with half a
        # settings screen in one language and half in another.
        cli_group = QGroupBox(t("settings_cli_group", self.lang))
        cli_layout = QVBoxLayout(cli_group)
        self.cli_status_label = QLabel()
        self.cli_status_label.setWordWrap(True)
        self.cli_status_label.setProperty("class", theme.CLASS_MUTED)
        cli_layout.addWidget(self.cli_status_label)
        self.cli_install_btn = QPushButton()
        self.cli_install_btn.clicked.connect(self._on_cli_install_clicked)
        cli_layout.addWidget(self.cli_install_btn)
        layout.addWidget(cli_group)
        self._refresh_cli_status()

        # --- sessions this machine holds ---------------------------------
        # A tool that quietly keeps a way into somebody's account and offers
        # no way to see or remove it is not a tool anyone should install. The
        # hosts are listed; nothing about their contents is, ever.
        self.sessions_label = muted("")
        self.sessions_label.setWordWrap(True)
        layout.addWidget(self.sessions_label)
        session_actions = QHBoxLayout()
        self.forget_sessions_btn = QPushButton(
            t("settings_forget_sessions", self.lang))
        self.forget_sessions_btn.setProperty("class", theme.CLASS_QUIET)
        self.forget_sessions_btn.clicked.connect(self._on_forget_sessions)
        session_actions.addWidget(self.forget_sessions_btn)
        session_actions.addStretch(1)
        layout.addLayout(session_actions)
        self._refresh_sessions_label()

        # --- what a run leaves behind ------------------------------------
        # Artboard 3q puts the cache and the uninstall here, and both are
        # about the same thing: what this tool has put on the machine.
        self.cache_label = muted("")
        self.cache_label.setWordWrap(True)
        layout.addWidget(self.cache_label)

        actions = QHBoxLayout()
        self.clear_cache_btn = QPushButton(t("settings_clear_cache", self.lang))
        self.clear_cache_btn.setProperty("class", theme.CLASS_QUIET)
        self.clear_cache_btn.clicked.connect(self._on_clear_cache)
        actions.addWidget(self.clear_cache_btn)
        self.uninstall_btn = QPushButton(t("settings_uninstall", self.lang))
        self.uninstall_btn.setProperty("class", theme.CLASS_QUIET)
        self.uninstall_btn.clicked.connect(self._on_uninstall)
        actions.addWidget(self.uninstall_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._refresh_cache_label()

        # The log belongs beside the cache and the uninstaller: all three
        # answer "what has this tool put on my machine". It is also the only
        # place a person can see why a run did what it did after the run has
        # ended - the CLI and the TUI show the same records.
        self.logs_label = muted("")
        self.logs_label.setWordWrap(True)
        layout.addWidget(self.logs_label)
        log_actions = QHBoxLayout()
        self.view_logs_btn = QPushButton(t("settings_view_logs", self.lang))
        self.view_logs_btn.setProperty("class", theme.CLASS_QUIET)
        self.view_logs_btn.clicked.connect(self._on_view_logs)
        log_actions.addWidget(self.view_logs_btn)
        self.clean_logs_btn = QPushButton(t("settings_clean_logs", self.lang))
        self.clean_logs_btn.setProperty("class", theme.CLASS_QUIET)
        self.clean_logs_btn.clicked.connect(self._on_clean_logs)
        log_actions.addWidget(self.clean_logs_btn)
        log_actions.addStretch(1)
        layout.addLayout(log_actions)
        self._refresh_logs_label()

        return w

    def _refresh_sessions_label(self) -> None:
        import site_session

        hosts = site_session.known_hosts()
        self.sessions_label.setText(
            t("settings_sessions_none", self.lang) if not hosts
            else t("settings_sessions", self.lang, hosts=", ".join(hosts),
                   count=len(hosts)))
        self.forget_sessions_btn.setEnabled(bool(hosts))

    def _on_forget_sessions(self) -> None:
        """Delete every stored site session. Asked first: this is the thing
        that makes signing in again necessary, and a stray click should not
        cost somebody a round of 2FA."""
        from PySide6.QtWidgets import QMessageBox

        import site_session

        hosts = site_session.known_hosts()
        if not hosts:
            return
        answer = QMessageBox.question(
            self, "", t("settings_forget_sessions_confirm", self.lang,
                        hosts=", ".join(hosts)))
        if answer != QMessageBox.StandardButton.Yes:
            return
        site_session.forget_all()
        self._refresh_sessions_label()

    def _refresh_logs_label(self) -> None:
        import applog

        summary = applog.summary()
        megabytes = summary["bytes"] / (1024 * 1024)
        self.logs_label.setText(t("settings_logs_note", self.lang,
                                  n=len(summary["files"]),
                                  mb=f"{megabytes:.2f}",
                                  days=summary["retention_days"],
                                  path=summary["directory"]))

    def _on_view_logs(self) -> None:
        from ui.window_parts.action_dialogs import LogViewerDialog

        LogViewerDialog(self.lang, parent=self).exec()

    def _on_clean_logs(self) -> None:
        """Apply the retention limits now rather than at the next write.

        The limits run on their own; this exists for the moment somebody is
        looking at the number and wants it to be true immediately."""
        import applog

        applog.clean()
        self._refresh_logs_label()

    def _refresh_cache_label(self) -> None:
        """How much is cached, and where, in one line.

        A count rather than "cache: on": the question this answers is
        whether clearing it would throw anything away.
        """
        import judgment_cache

        directory = judgment_cache.cache_dir()
        files = list(directory.glob("*.json")) if directory.exists() else []
        self.cache_label.setText(t("settings_cache_note", self.lang,
                                   n=len(files), path=str(directory)))
        self.clear_cache_btn.setEnabled(bool(files))

    def _on_clear_cache(self) -> None:
        """Throw away what a model has already said about passages.

        Offered because a cached judgment outlives the reason it was right:
        a detector change, a different model, a rewritten rubric. The cache
        is keyed on all three, so this is rarely needed - which is why it is
        a button here rather than an option on every run.
        """
        import shutil

        import judgment_cache

        directory = judgment_cache.cache_dir()
        if not directory.exists():
            self._refresh_cache_label()
            return
        answer = QMessageBox.question(
            self, t("settings_clear_cache", self.lang),
            t("settings_clear_cache_confirm", self.lang, path=str(directory)))
        if answer != QMessageBox.StandardButton.Yes:
            return
        shutil.rmtree(directory, ignore_errors=True)
        self._refresh_cache_label()

    def _on_uninstall(self) -> None:
        """Remove XBrain Audit from this machine, after saying what that means.

        The list is enumerated first and shown in the question, because
        "uninstall" covers four different things here - the app, the command
        line link, the configuration, the keychain entries - and someone
        agreeing to it should be agreeing to the actual list. Reports already
        written and run folders are not on it: those are their work, not the
        tool's state.
        """
        import uninstaller

        items = uninstaller.enumerate_items()
        present = [i for i in items if i.exists]
        if not present:
            QMessageBox.information(self, t("settings_uninstall", self.lang),
                                    t("settings_uninstall_nothing", self.lang))
            return
        lines = [t("settings_uninstall_confirm", self.lang), ""]
        lines += [f"  · {uninstaller.display_item(item, self.lang)}"
                  for item in present]
        notes = uninstaller.remaining_notes(self.lang)
        if notes:
            lines += ["", t("settings_uninstall_kept", self.lang)]
            lines += [f"  · {note}" for note in notes]
        answer = QMessageBox.question(self, t("settings_uninstall", self.lang),
                                      "\n".join(lines))
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed, _problems = uninstaller.remove_all(present)
        message = t("settings_uninstall_done", self.lang, n=len(removed))
        failures = [f"{uninstaller.display_item(item, self.lang)}: {item.error}"
                    for item in present if item.error]
        if failures:
            message += "\n\n" + "\n".join(failures)
        QMessageBox.information(self, t("settings_uninstall", self.lang), message)

    # ---------------------------------------------------------- behaviour

    def current_provider(self) -> str:
        for name, button in self.provider_buttons.items():
            if button.isChecked():
                return name
        return self.settings.llm_provider

    def _refresh_provider_ui(self) -> None:
        chosen = self.current_provider()
        for name, box in self.provider_details.items():
            box.setVisible(name == chosen)
        self._refresh_local_statuses()

    def _refresh_local_statuses(self) -> None:
        """What each account is, read without a request and without a subprocess.

        Everything here is a local file, a keychain entry or a `which`. The
        two answers that cost something - the subscription's quota and the
        CLI's session - are what the Check button is for, and until it is
        pressed the row says what is known rather than guessing.
        """
        import shutil

        email = credentials.load_secret("xformat_account_email") or ""
        token = credentials.load_secret("xformat_refresh_token") or ""
        self.provider_notes[PROVIDER_XFORMAT].setText(
            t("settings_account_as", self.lang, email=email) if token and email
            else t("settings_account_none", self.lang))

        key = config.get_anthropic_api_key()
        self.provider_notes[PROVIDER_ANTHROPIC].setText(
            t("settings_key_in_keychain", self.lang, masked="•••• " + key[-4:])
            if key else t("settings_key_missing", self.lang))

        binary = shutil.which("claude")
        self.provider_notes["claude-code"].setText(
            t("settings_cli_found", self.lang, path=binary) if binary
            else t("settings_cli_missing", self.lang))

        self._refresh_account_card(email, bool(token))

    def _refresh_account_card(self, email: str, signed_in: bool) -> None:
        """The card the design puts on top: who this machine is signed in as.

        Only the subscription can be signed *in* - a key and a CLI session
        are not accounts this dialog opened - so the card is about xFormat,
        and it says so plainly when there is nobody to name.
        """
        if signed_in and email:
            initials = "".join(part[0] for part in email.split("@")[0]
                               .replace(".", " ").split() if part)[:2].upper()
            self.account_initials.setText(initials or "?")
            self.account_name.setText(email)
            self.account_note.setText(t("settings_account_note", self.lang))
            self.sign_out_btn.setVisible(True)
        else:
            self.account_initials.setText("—")
            self.account_name.setText(t("settings_account_none", self.lang))
            self.account_note.setText(t("settings_account_none_note", self.lang))
            self.sign_out_btn.setVisible(False)

    def _build_xformat_provider(self):
        endpoints = self._parse_endpoints(silent=True)
        return LLMProviderFactory.create(
            PROVIDER_XFORMAT,
            base_url=self.xformat_url_edit.text().strip() or self.settings.xformat_base_url,
            endpoints=endpoints,
        )

    def _on_sign_in(self) -> None:
        email = self.xformat_email_edit.text().strip()
        password = self.xformat_password_edit.text()
        if not email or not password:
            self._set_status(t("settings_need_credentials", self.lang), ok=False)
            return
        provider = self._build_xformat_provider()
        try:
            status = provider.sign_in(email, password)
        except (LLMAuthError, LLMUnavailable) as exc:
            self._set_status(str(exc), ok=False)
            return
        # The password is not kept anywhere — only the returned tokens are.
        self.xformat_password_edit.clear()
        self._report_status(status)
        self._refresh_local_statuses()

    def _on_sign_out(self) -> None:
        provider = self._build_xformat_provider()
        provider.sign_out()
        self._set_status(t("settings_signed_out", self.lang), ok=True)
        self._refresh_local_statuses()

    def _on_check_status(self, name: str = PROVIDER_XFORMAT) -> None:
        """Ask one account what it actually says about itself.

        Per row rather than per dialog: "check" means three different things
        here - a request to the subscription, a keychain read, a subprocess -
        and only the row that was clicked should pay for its own answer.
        """
        try:
            provider = (self._build_xformat_provider()
                        if name == PROVIDER_XFORMAT
                        else LLMProviderFactory.create(name))
            status = provider.auth_status()
        except (LLMAuthError, LLMUnavailable) as exc:
            self._set_status(str(exc), ok=False)
            return
        except Exception as exc:  # noqa: BLE001 - a provider that cannot even
            self._set_status(str(exc), ok=False)      # be built is an answer
            return
        self.provider_notes[name].setText(status.detail or "")
        self._report_status(status)

    def _report_status(self, status) -> None:
        if not status.signed_in:
            self._set_status(t("settings_not_signed_in", self.lang, detail=status.detail), ok=False)
            return
        text = t("settings_signed_in", self.lang, detail=status.detail)
        if status.quota_remaining is not None:
            text += " · " + t("settings_quota", self.lang, n=status.quota_remaining)
        self._set_status(text, ok=True)

    def _set_status(self, text: str, ok: bool) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {self._palette.success_text};" if ok
            else f"color: {self._palette.error_text};")

    def _parse_endpoints(self, silent: bool = False) -> dict:
        raw = self.endpoints_edit.toPlainText().strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            return data
        except (json.JSONDecodeError, ValueError) as exc:
            if not silent:
                QMessageBox.warning(self, "", t("settings_bad_json", self.lang, error=str(exc)))
            return {}

    def _show_endpoint_defaults(self) -> None:
        from dataclasses import asdict
        from llm.xformat_provider import XFormatEndpoints
        QMessageBox.information(
            self, "", json.dumps(asdict(XFormatEndpoints()), indent=2, ensure_ascii=False)
        )

    def _refresh_cli_status(self) -> None:
        """Reflects reality rather than assuming it: re-reads the actual
        symlink state every time, so a change made from a terminal (or a
        previous install this same session) is never shown stale."""
        bundled = cli_install.bundled_cli_path()
        if bundled is None:
            self.cli_status_label.setText(t("settings_cli_dev_only", self.lang))
            self.cli_install_btn.setEnabled(False)
            self.cli_install_btn.setText(t("settings_cli_install", self.lang))
            return

        self.cli_install_btn.setEnabled(True)
        target = cli_install.installed_target()
        if target is None:
            self.cli_status_label.setText(t("settings_cli_absent", self.lang))
            self.cli_install_btn.setText(t("settings_cli_install", self.lang))
            return

        path_note = "" if cli_install.is_dir_on_path(cli_install.USER_BIN_DIR) else (
            t("settings_cli_not_on_path", self.lang,
              dir=cli_install.USER_BIN_DIR))
        self.cli_status_label.setText(
            t("settings_cli_installed", self.lang,
              path=cli_install.USER_BIN_DIR / cli_install.CLI_NAME) + path_note)
        self.cli_install_btn.setText(t("settings_cli_remove", self.lang))

    def _on_cli_install_clicked(self) -> None:
        try:
            if cli_install.installed_target() is not None:
                cli_install.uninstall()
            else:
                cli_install.install()
        except cli_install.CliInstallError as exc:
            QMessageBox.warning(self, "", str(exc))
            return
        self._refresh_cli_status()

    def _on_accept(self) -> None:
        raw = self.endpoints_edit.toPlainText().strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("expected a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                QMessageBox.warning(self, "", t("settings_bad_json", self.lang, error=str(exc)))
                return
            self.settings.xformat_endpoints = parsed
        else:
            self.settings.xformat_endpoints = {}

        self.settings.ui_language = self.lang_combo.currentData()
        self.settings.theme = self.theme_seg.current_data() or "auto"
        self.settings.max_pages = self.max_pages_spin.value()
        self.settings.max_files = self.max_files_spin.value()
        self.settings.unicode_check_enabled = self.unicode_enabled_box.isChecked()
        self.settings.auto_start_devserver = self.devserver_switch.isChecked()
        self.settings.unicode_categories = [
            key for key, box in self.category_boxes.items() if box.isChecked()
        ]
        self.settings.llm_provider = self.current_provider()
        self.settings.claude_model = self.model_edit.text().strip() or self.settings.claude_model
        # Empty is a real answer here - "whatever the session is set to" -
        # so these are read straight rather than falling back to the old
        # value the way the free-text model field above has to.
        self.settings.claude_code_model = self.cc_model_combo.currentData() or ""
        self.settings.claude_code_effort = self.cc_effort_seg.current_data() or ""
        self.settings.xformat_base_url = self.xformat_url_edit.text().strip() or self.settings.xformat_base_url

        typed_key = self.api_key_edit.text().strip()
        if typed_key:
            config.set_anthropic_api_key(typed_key)

        self.settings.save()
        self.accept()
