"""Everything the user has hidden, in one place they can undo it (artboard 3k).

There was already a way to hide a finding and a way to list what had been
hidden, but they were not the same surface and neither answered the question
this screen exists for: *what did I switch off, and what would come back if I
switched it on again.* The settings tab showed five list boxes of raw values,
which for a fingerprint means sixteen hex characters - so the one action it
offered could not be taken on purpose.

Three panes, and the split is not cosmetic. A hidden **finding** is a
decision about one thing somebody wrote; **files and folders** are a decision
about where the tool should not look at all; a **disabled rule** switches off
a whole check everywhere. They are read differently and they are undone
differently, so they are not one list of five levels.

Two lists, kept apart on purpose: a personal entry travels with the user
across every project, a project entry lives in a committed `.xaudit-ignore`
and belongs to the team. `Suppressions.load` merges them, which is right for
"is this hidden" and wrong here - "put it back" has to remove the line from
the list it is actually in, and a merged object can no longer say which that
was. Each row therefore carries its origin, and Restore writes to that one.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

import suppression
from i18n.translations import t
from ui import theme
from ui.widgets import FlowLayout

#: Which levels the left-hand list owns. Paths and rules have panes of their
#: own on the right, and showing them in both places would be two editors of
#: one fact.
HIDDEN_LEVELS = ("fingerprints", "phrases", "selectors")

#: The dot beside a row marks **how broad** the entry is, which is the one
#: thing about a hidden entry whose consequence differs: a fingerprint hides
#: exactly one finding, a phrase hides a word everywhere, a selector hides a
#: region of every page. Not severity - a hidden finding no longer has one.
LEVEL_INK = {
    "selectors": "sev_high",
    "phrases": "sev_medium",
    "fingerprints": "sev_none",
}


def _dot(colour: str) -> QLabel:
    dot = QLabel("●")
    dot.setStyleSheet(f"color: {colour};")
    return dot


class HiddenRow(QWidget):
    """One hidden entry: what it was, where the record lives, and Restore."""

    def __init__(self, level: str, value: str, label: str, origin: str,
                 palette, lang: str = "en", parent=None):
        super().__init__(parent)
        self.level = level
        self.value = value

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        row.addWidget(_dot(getattr(palette, LEVEL_INK.get(level, "sev_none"),
                                   palette.text_muted)))

        text = QWidget()
        column = QVBoxLayout(text)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        # The note first, because it is the sentence; the entry itself below
        # it in mono, because that is what is written in the file and what
        # somebody grepping for it would look for.
        headline = QLabel(label or value)
        headline.setToolTip(label or value)
        column.addWidget(headline)
        meta = QLabel(" · ".join((value, origin)) if label
                      else " · ".join((level, origin)))
        meta.setProperty("class", theme.CLASS_CODE)
        column.addWidget(meta)
        row.addWidget(text, stretch=1)

        self.restore_btn = QPushButton(t("noise_restore", lang))
        self.restore_btn.setProperty("class", theme.CLASS_QUIET)
        row.addWidget(self.restore_btn)


class NoiseDialog(QDialog):
    """What not to show: hidden findings, excluded paths, disabled rules."""

    def __init__(self, settings, lang: str = "en", root: str | None = None,
                 palette=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.lang = lang
        self.root = root
        self.palette_ = palette or getattr(parent, "palette_tokens", None)
        self.setWindowTitle(t("noise_title", lang))
        self.resize(980, 560)

        self.sources = suppression.sources(settings, root)
        #: The list an edit that has no origin of its own goes into: the
        #: project's file when the scan has one, since that is the decision a
        #: team shares, and the personal list otherwise.
        self.target = next((s for s in self.sources
                            if s.kind == suppression.PROJECT), self.sources[0])

        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        outer.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(8)
        body.addWidget(self._build_hidden_pane(), stretch=13)
        body.addWidget(self._build_side_pane(), stretch=10)
        outer.addLayout(body)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._reload()

    # ----------------------------------------------------------- building

    def _build_header(self) -> QWidget:
        head = QWidget()
        head.setProperty("class", theme.CLASS_PANEL_HEAD)
        row = QHBoxLayout(head)
        row.setSpacing(8)
        title = QLabel(t("noise_title", self.lang))
        title.setProperty("class", theme.CLASS_HEADING)
        row.addWidget(title)
        where = QLabel(t("noise_where", self.lang))
        where.setProperty("class", theme.CLASS_MUTED)
        where.setWordWrap(True)
        row.addWidget(where, stretch=1)
        return head

    def _build_hidden_pane(self) -> QWidget:
        pane, body = self._panel(t("noise_hidden", self.lang),
                                 t("noise_hidden_hint", self.lang))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.hidden_host = QWidget()
        self.hidden_layout = QVBoxLayout(self.hidden_host)
        self.hidden_layout.setContentsMargins(0, 0, 0, 0)
        self.hidden_layout.setSpacing(2)
        scroll.setWidget(self.hidden_host)
        body.addWidget(scroll)

        # Hiding something normally starts from a finding on screen, which is
        # where the decision is actually made. This row is the other way in,
        # kept because it was the only way to add a phrase or a region by
        # hand and nothing else offers it: a word you already know you never
        # want flagged, or a part of every page that is not yours.
        add_row = QHBoxLayout()
        self.level_combo = QComboBox()
        for level in ("phrases", "selectors"):
            self.level_combo.addItem(t(f"suppression_{level}", self.lang),
                                     userData=level)
        self.hidden_entry = QLineEdit()
        self.hidden_entry.setPlaceholderText(
            t("suppression_add_placeholder", self.lang))
        self.hidden_entry.returnPressed.connect(self._on_add_hidden)
        add_hidden_btn = QPushButton(t("suppression_add", self.lang))
        add_hidden_btn.setProperty("class", theme.CLASS_QUIET)
        add_hidden_btn.clicked.connect(self._on_add_hidden)
        add_row.addWidget(self.level_combo)
        add_row.addWidget(self.hidden_entry, stretch=1)
        add_row.addWidget(add_hidden_btn)
        body.addLayout(add_row)
        return pane

    def _build_side_pane(self) -> QWidget:
        side = QWidget()
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        paths_pane, paths_body = self._panel(t("noise_paths", self.lang),
                                             t("noise_paths_hint", self.lang))
        self.paths_edit = QPlainTextEdit()
        self.paths_edit.setProperty("class", theme.CLASS_CODE)
        paths_body.addWidget(self.paths_edit)
        column.addWidget(paths_pane, stretch=1)

        rules_pane, rules_body = self._panel(t("noise_rules", self.lang), "")
        self.rules_host = QWidget()
        self.rules_flow = FlowLayout(self.rules_host, spacing=5)
        rules_body.addWidget(self.rules_host)

        add_row = QHBoxLayout()
        self.rule_combo = QComboBox()
        self.rule_combo.setEditable(True)
        for category, ids in suppression.known_rule_ids().items():
            for rule_id in ids:
                self.rule_combo.addItem(f"{rule_id}  ({category})", userData=rule_id)
        self.rule_combo.setCurrentIndex(-1)
        self.rule_combo.lineEdit().setPlaceholderText(
            t("suppression_rule_placeholder", self.lang))
        add_btn = QPushButton(t("noise_rules_add", self.lang))
        add_btn.setProperty("class", theme.CLASS_QUIET)
        add_btn.clicked.connect(self._on_add_rule)
        add_row.addWidget(self.rule_combo, stretch=1)
        add_row.addWidget(add_btn)
        rules_body.addLayout(add_row)
        column.addWidget(rules_pane)
        return side

    def _panel(self, title: str, hint: str):
        """A titled surface, returning it and the layout its contents go in."""
        pane = QWidget()
        pane.setProperty("class", theme.CLASS_PANEL)
        pane.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        column = QVBoxLayout(pane)
        column.setSpacing(4)
        head = QHBoxLayout()
        label = QLabel(title)
        label.setProperty("class", theme.CLASS_FIELD_LABEL)
        head.addWidget(label)
        if hint:
            note = QLabel(hint)
            note.setProperty("class", theme.CLASS_MUTED)
            head.addWidget(note, stretch=1)
        head.addStretch(0)
        column.addLayout(head)
        return pane, column

    # ------------------------------------------------------------ filling

    def _origin(self, source) -> str:
        if source.kind == suppression.PROJECT:
            return t("noise_origin_project", self.lang)
        return t("noise_origin_personal", self.lang)

    def _reload(self) -> None:
        self._fill_hidden()
        self.paths_edit.setPlainText(self.target.entries.section_text("paths"))
        self._fill_rules()

    def _clear(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _fill_hidden(self) -> None:
        self._clear(self.hidden_layout)
        rows = 0
        for source in self.sources:
            for level in HIDDEN_LEVELS:
                for value in getattr(source.entries, level):
                    row = HiddenRow(level, value,
                                    source.entries.labels.get(value, ""),
                                    self._origin(source), self.palette_,
                                    self.lang, self)
                    row.restore_btn.clicked.connect(
                        lambda _=False, s=source, lv=level, v=value:
                        self._on_restore(s, lv, v))
                    self.hidden_layout.addWidget(row)
                    rows += 1
        if not rows:
            empty = QLabel(t("noise_hidden_empty", self.lang))
            empty.setProperty("class", theme.CLASS_EMPTY)
            self.hidden_layout.addWidget(empty)
        self.hidden_layout.addStretch(1)

    def _fill_rules(self) -> None:
        self._clear(self.rules_flow)
        for source in self.sources:
            for rule_id in source.entries.rules:
                chip = QPushButton(f"{rule_id}  ✕")
                chip.setProperty("class", theme.CLASS_CHIP)
                note = source.entries.labels.get(rule_id, "")
                chip.setToolTip(" · ".join(p for p in (note, self._origin(source)) if p))
                chip.clicked.connect(
                    lambda _=False, s=source, r=rule_id:
                    self._on_restore(s, "rules", r))
                self.rules_flow.addWidget(chip)

    # ------------------------------------------------------------ actions

    def _on_restore(self, source, level: str, value: str) -> None:
        """Un-hide one entry, out of the list it is actually written in."""
        if source.remove(level, value):
            self._reload()

    def _on_add_hidden(self) -> None:
        value = self.hidden_entry.text().strip()
        level = self.level_combo.currentData()
        if not value:
            return
        values = getattr(self.target.entries, level)
        if value not in values:
            values.append(value)
            self.target.entries.__post_init__()
        self.hidden_entry.clear()
        self._fill_hidden()

    def _on_add_rule(self) -> None:
        rule_id = (self.rule_combo.currentData()
                   or self.rule_combo.currentText()).strip()
        if not rule_id:
            return
        if rule_id not in self.target.entries.rules:
            self.target.entries.rules.append(rule_id)
            self.target.entries.__post_init__()
        self.rule_combo.setCurrentIndex(-1)
        self.rule_combo.clearEditText()
        self._fill_rules()

    def _on_accept(self) -> None:
        # The box owns the paths of one list only, so it is spliced into that
        # list rather than written over it: a pane for files must not be able
        # to drop a rule somebody disabled in the pane below it.
        self.target.entries.replace_section("paths",
                                            self.paths_edit.toPlainText())
        for source in self.sources:
            source.save(self.settings)
        self.accept()
