"""Turns an xFormat design-system palette into a Qt style sheet.

`ui/tokens.py` reads the colours, radii and type scale out of the frontend's
`tokens.css`; this module is what paints with them. The two are kept apart
because they fail differently: parsing can find nothing (and falls back to
the palette defaults), while this file always produces a complete style
sheet from whatever palette it is handed.

Where the web app and the desktop app deliberately differ:

* Qt style sheets have no cascade and no custom properties, so every value
  is expanded here rather than referenced. That is why this is generated
  from tokens instead of hand-written — a token change stays a one-line
  change upstream.
* `box-shadow` doesn't exist in QSS. The web app's monolithic-card-on-soft-
  shadow look is approximated with a hairline border in `--border`, which
  reads as the same "surface floating on the canvas" separation without
  drawing fake shadows into the pixmap. The desktop design draws no borders
  at all, so the surfaces it introduces (`CLASS_SURFACE`, `CLASS_INSET`)
  take a real `QGraphicsDropShadowEffect` from `soft_shadow` instead - see
  the note there for why one effect stands in for the design's two layers.
* Qt needs an explicit widget-by-widget selector list where CSS would
  inherit; the shape of this file follows Qt's needs, the values follow the
  design system's.

`build_textual_theme` below does the same job for the TUI. It stops short of
generating a full `.tcss` file the way `build_qss` generates a full QSS
string, because Textual's CSS already has variables and a cascade - the
`.tcss` files under `tui/` are hand-written once and reference `$primary`,
`$sev-critical` and so on, the same way a hand-written stylesheet on the web
would. What has to be generated is the *values* those variables resolve to,
because that is the part that would otherwise become a third copy of the
palette. Textual also derives a full set of tints and shades from a handful
of base colours (`textual.design.ColorSystem`); accepting that derivation
for chrome nobody has opinions about (scrollbar, cursor, footer) and
overriding only the values this app actually measured - `text_muted`,
`text_subtle`, the four severity fills - keeps one contrast computation
instead of two disagreeing ones.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import re

from textual.theme import Theme

from ui.tokens import Palette, palettes

#: Class names set with `widget.setProperty("class", ...)` and matched below.
CLASS_CARD = "card"
CLASS_HEADING = "heading"
CLASS_MUTED = "muted"
CLASS_PRIMARY = "primary"
CLASS_TOOLBAR = "toolbar"
CLASS_BADGE_HIGH = "badge-high"
CLASS_BADGE_MEDIUM = "badge-medium"
CLASS_BADGE_LOW = "badge-low"
CLASS_EMPTY = "empty"
#: A zone of the window with its own surface: the toolbar, a column, a panel
#: inside the detail column. The design the web app uses is one of monolithic
#: cards on a warm canvas, and a Qt window that paints everything on one flat
#: sheet reads as a different product entirely.
CLASS_PANEL = "panel"
#: The header strip of a panel: its name, and whatever belongs on the same
#: line. Separated by a hairline rather than by whitespace so the eye finds
#: the boundary of each zone without the layout having to grow.
CLASS_PANEL_HEAD = "panel-head"
#: A small labelled block inside a panel - "what was found", "why it matters".
CLASS_FIELD = "field"
CLASS_FIELD_LABEL = "field-label"
#: A quiet pill: the rule id, the engine that found it, the file position.
CLASS_CHIP = "chip"
#: The accent-filled variant, for the one action a panel exists to offer.
CLASS_ACCENT = "accent"
#: A button that reads as a link: secondary, never the thing to press first.
CLASS_QUIET = "quiet"
#: A hairline. A QFrame with this class draws the divider between zones.
CLASS_DIVIDER = "divider"
#: Monospaced markup shown as evidence, not as something to edit.
CLASS_CODE = "code"
#: The window's own header: the mark, the product name, the mode.
CLASS_BRAND = "brand"

#: The desktop design's three surface levels. The canvas is the window
#: itself; `CLASS_SURFACE` is a section sitting on it, `CLASS_INSET` a block
#: nested inside a section. Separated by tone and by `soft_shadow` rather
#: than by a border - which is the whole difference from `CLASS_CARD` above,
#: and why they are separate classes instead of a change to that one: the
#: two coexist while the window is migrated screen by screen.
CLASS_SURFACE = "surface"
CLASS_INSET = "inset"
#: The top controls row. A surface like any other, plus the compact button
#: metrics the design draws it with - stated here rather than on every
#: button in the window, because a 28px button is right in a one-line row
#: and wrong in a panel where it stands on its own.
CLASS_TOP_ROW = "top-row"

#: The parts of an inline selector: the word that names the setting, the
#: value itself, and the small caret that says the value can be changed.
#: Three classes rather than one because they are three different inks -
#: muted, full, and subtle - and that difference is what makes the row read
#: as a sentence instead of as a form.
CLASS_INLINE_LABEL = "inline-label"
CLASS_INLINE_VALUE = "inline-value"
CLASS_INLINE_CARET = "inline-caret"
#: The hairline standing between two inline values.
CLASS_HAIRLINE = "hairline"
#: The whole selector, which is what takes keyboard focus.
CLASS_INLINE_FIELD = "inline-field"
#: The fillable area of a `panel()`, under its head.
CLASS_PANEL_BODY = "panel-body"

#: The settings screen (artboards 3d, 3q). `CLASS_SEGMENTED` is the strip a
#: `Segmented` control sits in, `CLASS_SEGMENT` one of its choices;
#: `CLASS_RAIL_ITEM` is a section name in the left-hand rail. All three are
#: checkable states, which is why they need style of their own: a checked
#: `QPushButton` is otherwise drawn as a pressed button.
CLASS_SEGMENTED = "segmented"
CLASS_SEGMENT = "segment"
CLASS_RAIL_ITEM = "rail-item"


def qcolor(value: str):
    """A palette colour as a `QColor`, alpha included.

    `qss_color` exists to hand colours to a *style sheet*; this hands one to
    a widget API, which needs the alpha as a number rather than as text.
    Accepts what the token file actually contains: `#rgb`, `#rrggbb`,
    `#rrggbbaa` and `rgba(r, g, b, a)`.
    """
    from PySide6.QtGui import QColor

    text = (value or "").strip()
    # `#rrggbbaa` first, and by hand: Qt reads an 8-digit hex as `#aarrggbb`,
    # alpha *first*, which is the opposite of the CSS form the token file is
    # written in. Handing xFormat's `--sb-thumb: #d8d6d0a3` straight to
    # QColor yields alpha 0xd8 and a colour shifted a channel over - wrong
    # in a way that still renders, which is the kind that survives review.
    match = re.fullmatch(r"#([0-9a-fA-F]{8})", text)
    if match:
        from PySide6.QtGui import QColor

        digits = match.group(1)
        r, g, b, a = (int(digits[i:i + 2], 16) for i in (0, 2, 4, 6))
        return QColor(r, g, b, a)

    match = re.fullmatch(r"rgba?\(([^)]+)\)", text)
    if match:
        parts = [p.strip() for p in match.group(1).split(",")]
        try:
            r, g, b = (int(float(p)) for p in parts[:3])
            alpha = float(parts[3]) if len(parts) > 3 else 1.0
        except (ValueError, IndexError):
            return QColor(0, 0, 0, 0)
        # CSS writes alpha 0..1; Qt wants 0..255.
        return QColor(r, g, b, max(0, min(255, round(alpha * 255))))
    colour = QColor(text)
    return colour if colour.isValid() else QColor(0, 0, 0, 0)


def soft_shadow(widget, p: Palette):
    """Give `widget` the design's surface shadow, or take it away.

    The bundle stacks two shadows on every surface - a 1px contact shadow and
    a wide ambient one. `QGraphicsDropShadowEffect` draws exactly one, so the
    palette carries a single blur/offset/colour tuned to stand in for both,
    and this applies it. A palette with `shadow_blur == 0` (any token file
    without the desktop overlay) clears the effect instead, which leaves the
    widget on the hairline-border look the rest of the window still uses.

    Returns the effect, or None when none was applied. Qt takes ownership of
    the effect, and setting a new one deletes the old, so this is safe to
    call again on every theme change - which `MainWindow.apply_palette` does,
    because the shadow colour differs between the two sheets.
    """
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    if p.shadow_blur <= 0:
        widget.setGraphicsEffect(None)
        return None
    # No parent. `setGraphicsEffect` takes ownership on its own, and giving
    # the effect the widget as a parent as well hands the same object to two
    # owners - which Qt frees twice when the window goes away. It survived
    # every test that built one window and segfaulted in the full suite,
    # where windows are built and destroyed in the dozens.
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(p.shadow_blur)
    effect.setXOffset(0)
    effect.setYOffset(p.shadow_y)
    effect.setColor(qcolor(p.shadow_color))
    widget.setGraphicsEffect(effect)
    return effect


def qss_color(value: str) -> str:
    """Qt style sheets accept `#rgb`/`#rrggbb` and `rgba(...)`, but not the
    8-digit `#rrggbbaa` form CSS allows — and xFormat's scrollbar tokens use
    it. Convert rather than drop, so the token still lands."""
    value = (value or "").strip()
    match = re.fullmatch(r"#([0-9a-fA-F]{8})", value)
    if not match:
        return value
    digits = match.group(1)
    r, g, b, a = (int(digits[i:i + 2], 16) for i in (0, 2, 4, 6))
    return f"rgba({r}, {g}, {b}, {a / 255:.3f})"


#: Where the two tick marks live. A file rather than a data URI because Qt
#: style sheets accept `url()` only as a path, and two files rather than one
#: because QSS cannot tint an image: the tick sits on `--primary`, which is
#: near-black on the light sheet and near-white on the dark one, so the ink
#: has to be baked in. Both are `--on-primary`, exactly.
_ICONS = Path(__file__).resolve().parent / "design" / "assets" / "icons"


def _check_mark(p: Palette) -> str:
    name = "check-on-light.svg" if p.name == "dark" else "check-on-dark.svg"
    return (_ICONS / name).as_posix()


def build_qss(p: Palette) -> str:
    p = _palette_with_installed_fonts(p)
    c = qss_color
    # Selection colours: the accent at full strength is too loud behind body
    # text, so selections use the muted brand fill the web app uses for the
    # same job (rows, chips) and keep the normal text colour on top.
    selection_bg = c(p.accent_muted) if p.accent_muted.startswith("rgba") else c(p.bg_hover)

    return f"""
/* Generated from xFormat design tokens — edit tokens.css, not this string. */

/* No background here on purpose. A blanket fill on `QWidget` paints every
   plain container in the window with the canvas colour - including the
   unnamed wrappers inside a panel, which then cover the surface the panel
   just painted. That is what flattened the three surface levels back into
   one: the panel drew #fbfaf8 and an anonymous child drew #efece7 straight
   over it. The canvas belongs to the window; everything above it is either
   transparent or declares a surface of its own. */
QWidget {{
    color: {c(p.text)};
    font-family: "{p.font}";
    font-size: {p.font_size}px;
}}

QMainWindow, QDialog, QMainWindow > QWidget {{
    background-color: {c(p.page_bg)};
}}

/* ---------------------------------------------------------------- surfaces */

QWidget[class="{CLASS_CARD}"] {{
    background-color: {c(p.bg_card)};
    border: 1px solid {c(p.border)};
    border-radius: {p.radius}px;
}}

QWidget[class="{CLASS_TOOLBAR}"] {{
    background-color: {c(p.bg_card)};
    border: 1px solid {c(p.border)};
    border-radius: {p.radius}px;
}}

/* The desktop design's surfaces. No border on purpose: the separation is
   tone plus `soft_shadow`, and a hairline on top of both reads as a seam. */
QWidget[class="{CLASS_SURFACE}"] {{
    background-color: {c(p.bg)};
    border: none;
    border-radius: {p.radius}px;
}}

QWidget[class="{CLASS_TOP_ROW}"] {{
    background-color: {c(p.bg)};
    border: none;
    border-radius: {p.radius}px;
}}

QWidget[class="{CLASS_TOP_ROW}"] QPushButton {{
    padding: 5px 13px;
    border-radius: {p.radius_md}px;
}}

QWidget[class="{CLASS_INSET}"] {{
    background-color: {c(p.bg_muted)};
    border: none;
    border-radius: {p.radius_lg - 1}px;
}}

/* Controls inside the strip lose their own box. In the design the scanned
   address is text sitting in the filled strip, not a field drawn on top of
   one - a bordered input inside a bordered block is two nested boxes saying
   the same thing, and it is what made the row 68px tall against the 44px
   the design draws. The focus ring below is what still says which control
   the keyboard is on, since the border no longer can. */
QWidget[class="{CLASS_INSET}"] QLineEdit,
QWidget[class="{CLASS_INSET}"] QSpinBox {{
    background: transparent;
    border: none;
    border-radius: {p.radius_sm}px;
    padding: 1px 3px;
}}

QWidget[class="{CLASS_INSET}"] QLineEdit:focus,
QWidget[class="{CLASS_INSET}"] QSpinBox:focus {{
    background-color: {c(p.bg)};
    border: none;
}}

/* ------------------------------------------------------- inline selectors */

QLabel[class="{CLASS_INLINE_LABEL}"] {{
    color: {c(p.text_muted)};
    font-size: {p.font_size_sm}px;
}}

QLabel[class="{CLASS_INLINE_VALUE}"] {{
    color: {c(p.text)};
    font-weight: 500;
}}

QLabel[class="{CLASS_INLINE_CARET}"] {{
    color: {c(p.text_subtle)};
    font-size: {max(9, p.font_size_sm - 3)}px;
}}

QFrame[class="{CLASS_HAIRLINE}"] {{
    background-color: {c(p.divider)};
    border: none;
}}

/* The focus ring. An inline selector has no box of its own, so without this
   there is nothing at all to say which one the keyboard is on - and this
   window is the one that reports missing focus indicators on other people's
   pages. */
QWidget[class="{CLASS_INLINE_FIELD}"]:focus {{
    background-color: {c(p.bg_hover)};
    border-radius: {p.radius_sm}px;
}}

QLabel {{
    background: transparent;
}}

QLabel[class="{CLASS_HEADING}"] {{
    font-size: {p.font_size_lg}px;
    font-weight: 600;
    color: {c(p.text)};
}}

QLabel[class="{CLASS_MUTED}"] {{
    color: {c(p.text_muted)};
    font-size: {p.font_size_sm}px;
}}

QWidget[view="setup"] QLabel[class="{CLASS_MUTED}"] {{
    color: {c(p.text)};
    font-size: {p.font_size_sm + 1}px;
}}

QLabel[class="{CLASS_EMPTY}"] {{
    color: {c(p.text_muted)};
    font-size: {p.font_size}px;
    padding: {p.space_lg}px;
}}

/* Confidence badges. Colour alone never carries the meaning — the label
   spells out the level — so these stay readable for colour-blind users and
   in a screenshot printed in grayscale. */
QLabel[class="{CLASS_BADGE_HIGH}"],
QLabel[class="{CLASS_BADGE_MEDIUM}"],
QLabel[class="{CLASS_BADGE_LOW}"] {{
    border-radius: {p.radius_sm}px;
    padding: 2px {p.space_sm}px;
    font-size: {p.font_size_sm}px;
    font-weight: 600;
}}
QLabel[class="{CLASS_BADGE_HIGH}"] {{
    background-color: {c(p.error_strong)};
    color: {c(p.on_error)};
}}
QLabel[class="{CLASS_BADGE_MEDIUM}"] {{
    background-color: {c(p.amber)};
    color: {c(p.on_amber)};
}}
QLabel[class="{CLASS_BADGE_LOW}"] {{
    background-color: {c(p.bg_muted)};
    color: {c(p.text_muted)};
}}

/* ----------------------------------------------------------------- inputs */

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background-color: {c(p.bg_muted)};
    border: 1px solid {c(p.border)};
    border-radius: {p.radius_lg}px;
    padding: {p.space_sm}px {p.space_md}px;
    color: {c(p.text)};
    selection-background-color: {c(p.accent)};
    selection-color: {c(p.on_accent)};
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c(p.accent)};
}}

QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled,
QSpinBox:disabled, QComboBox:disabled {{
    color: {c(p.text_muted)};
    background-color: {c(p.bg_muted)};
}}

QLineEdit[class="field-error"] {{
    border: 1px solid {c(p.error)};
}}

QLabel[class="field-error"] {{
    color: {c(p.error)};
    font-size: {p.font_size_sm}px;
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background-color: {c(p.bg_card)};
    border: 1px solid {c(p.border)};
    border-radius: {p.radius_md}px;
    padding: {p.space_sm // 2}px;
    selection-background-color: {c(p.bg_hover)};
    selection-color: {c(p.text)};
    outline: none;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px;
    border: none;
    background: transparent;
}}

/* ---------------------------------------------------------------- buttons */

QPushButton {{
    background-color: {c(p.bg_card)};
    border: 1px solid {c(p.border_strong)};
    border-radius: {p.radius_lg}px;
    padding: {p.space_sm}px {p.space_lg}px;
    color: {c(p.text)};
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {c(p.bg_hover)};
}}

QPushButton:pressed {{
    background-color: {c(p.bg_muted)};
}}

QPushButton:disabled {{
    color: {c(p.text_muted)};
    border-color: {c(p.border)};
    background-color: {c(p.bg_muted)};
}}

QPushButton[class="{CLASS_PRIMARY}"] {{
    background-color: {c(p.primary)};
    color: {c(p.on_primary)};
    border: 1px solid {c(p.primary)};
}}

QPushButton[class="{CLASS_PRIMARY}"]:hover {{
    background-color: {c(p.primary_hover)};
    border-color: {c(p.primary_hover)};
}}

QPushButton[class="{CLASS_PRIMARY}"]:disabled {{
    background-color: {c(p.bg_muted)};
    border-color: {c(p.border)};
    color: {c(p.text_muted)};
}}

/* ------------------------------------------------------------------ zones */

/* Every zone is a surface on the canvas rather than a region of one flat
   sheet. This is the single largest difference between a Qt window that looks
   like a Qt window and one that looks like the rest of the product. */
/* No border. The design separates a zone from the canvas by tone and by
   `soft_shadow`, and the hairline this rule used to draw sat on top of both
   as a visible seam - clearest on the dark sheet, where #3a3631 outlined
   every column. The head strip below still carries its own fill, which is
   what marks the top of a zone now. */
QWidget[class="{CLASS_PANEL}"] {{
    background-color: {c(p.bg_card)};
    border: none;
    border-radius: {p.radius}px;
}}

/* Transparent, so the panel's own surface shows through it. Without this
   the blanket `QWidget` rule at the top of this sheet paints the canvas
   colour over the panel that contains it, and the three surface levels
   collapse into one flat sheet - which is exactly what a screenshot of the
   rebuilt window showed: canvas #efece7 where the panel had painted its
   #fbfaf8. The head below keeps its own fill and is matched after this. */
QWidget[class="{CLASS_PANEL_BODY}"] {{
    background: transparent;
}}

QWidget[class="{CLASS_PANEL_HEAD}"] {{
    background-color: {c(p.bg_muted)};
    border: none;
    border-bottom: 1px solid {c(p.border)};
    border-top-left-radius: {p.radius}px;
    border-top-right-radius: {p.radius}px;
}}

QWidget[class="settings-rule"] {{
    background-color: {c(p.rule)};
    border: none;
}}

QFrame[class="{CLASS_DIVIDER}"] {{
    background-color: {c(p.border)};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

QWidget[class="{CLASS_FIELD}"] {{
    background-color: {c(p.bg_muted)};
    border: 1px solid {c(p.border)};
    border-radius: {p.radius_md}px;
}}

QLabel[class="{CLASS_FIELD_LABEL}"] {{
    color: {c(p.text_muted)};
    font-size: {p.font_size_sm}px;
    font-weight: 600;
    /* Small caps by spacing rather than by font: the label is a signpost, and
       at this size letter-spacing separates it from the sentence under it
       more reliably than weight alone. */
    letter-spacing: 1px;
}}

QLabel[class="{CLASS_CHIP}"] {{
    background-color: {c(p.bg_muted)};
    border: 1px solid {c(p.border_strong)};
    border-radius: {p.radius_sm}px;
    padding: 2px {p.space_sm}px;
    color: {c(p.text_muted)};
    font-size: {p.font_size_sm}px;
}}

QPlainTextEdit[class="{CLASS_CODE}"], QTextEdit[class="{CLASS_CODE}"] {{
    background-color: {c(p.bg_muted)};
    border: 1px solid {c(p.border)};
    border-radius: {p.radius_md}px;
    font-family: "{p.font_mono}";
    font-size: {p.font_size_sm}px;
    color: {c(p.text)};
}}

QWidget[class="{CLASS_BRAND}"] {{
    background: transparent;
}}

QPushButton[class="{CLASS_ACCENT}"] {{
    background-color: {c(p.accent)};
    color: {c(p.on_accent)};
    border: 1px solid {c(p.accent)};
    font-weight: 600;
}}

QPushButton[class="{CLASS_ACCENT}"]:hover {{
    background-color: {c(p.accent_hover)};
    border-color: {c(p.accent_hover)};
}}

QPushButton[class="{CLASS_ACCENT}"]:disabled {{
    background-color: {c(p.bg_muted)};
    border-color: {c(p.border)};
    color: {c(p.text_muted)};
}}

/* The artboard's own values: the strip is `--bg-hover` (#f6f4f0) with no
   border at all, and the chosen segment is `--bg-muted` (#f2efeb) at a 5px
   radius. A bordered strip and a raised white segment were a plausible
   reading of "segmented control" and not what the design draws. */
QWidget[class="{CLASS_SEGMENTED}"] {{
    background-color: {c(p.bg_hover)};
    border: none;
    border-radius: {p.radius_lg}px;
}}

QPushButton[class="{CLASS_SEGMENT}"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {p.radius_sm}px;
    padding: 1px {p.space_sm}px;
    color: {c(p.text_muted)};
    font-size: {p.font_size_sm}px;
    font-weight: 500;
}}

QPushButton[class="{CLASS_SEGMENT}"]:hover {{
    color: {c(p.text)};
}}

/* The chosen segment is a raised card on the strip, not a pressed button:
   the strip is the track and the choice is what sits on it. */
QPushButton[class="{CLASS_SEGMENT}"]:checked {{
    background-color: {c(p.bg_muted)};
    border-color: transparent;
    border-radius: {p.radius_sm}px;
    color: {c(p.text)};
    font-weight: 500;
}}

QPushButton[class="{CLASS_RAIL_ITEM}"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {p.radius_md}px;
    padding: {p.space_sm // 2}px {p.space_sm}px;
    color: {c(p.text_muted)};
    text-align: left;
    font-weight: 500;
}}

QPushButton[class="{CLASS_RAIL_ITEM}"]:hover {{
    background-color: {c(p.bg_hover)};
    color: {c(p.text)};
}}

QPushButton[class="{CLASS_RAIL_ITEM}"]:checked {{
    background-color: {c(p.bg)};
    border-color: {c(p.border)};
    color: {c(p.text)};
    font-weight: 600;
}}

QPushButton[class="{CLASS_QUIET}"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {c(p.text_muted)};
    padding: {p.space_sm // 2}px {p.space_sm}px;
    font-weight: 500;
}}

QPushButton[class="{CLASS_QUIET}"]:hover {{
    background-color: {c(p.bg_hover)};
    color: {c(p.text)};
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

QSplitter::handle {{
    background: transparent;
}}

/* ------------------------------------------------------------------ lists */

QListWidget {{
    background-color: {c(p.bg_card)};
    /* No border: the list lives inside a panel that already has one, and two
       concentric rounded rectangles a pixel apart look like a mistake. */
    border: none;
    border-radius: 0;
    padding: {p.space_sm // 2}px;
    outline: none;
}}

QListWidget::item {{
    border-radius: {p.radius_md}px;
    padding: {p.space_sm}px;
    margin: 1px 0;
    color: {c(p.text)};
}}

QListWidget::item:hover {{
    background-color: {c(p.bg_hover)};
}}

QListWidget::item:selected {{
    background-color: {selection_bg};
    color: {c(p.text)};
}}

/* The file column of a repository scan is a tree, and Qt paints an
   unstyled one with the platform's own selection blue - the one colour in
   the window that belongs to no palette. It gets the list's treatment,
   which is what it is. */

QTreeWidget, QTreeView {{
    background-color: {c(p.bg_card)};
    border: none;
    outline: none;
    padding: {p.space_sm // 2}px;
}}

QTreeWidget::item, QTreeView::item {{
    border-radius: {p.radius_md}px;
    padding: {p.space_sm // 2}px {p.space_sm}px;
    color: {c(p.text)};
}}

QTreeWidget::item:hover, QTreeView::item:hover {{
    background-color: {c(p.bg_hover)};
}}

QTreeWidget::item:selected, QTreeView::item:selected {{
    background-color: {selection_bg};
    color: {c(p.text)};
}}

/* --------------------------------------------------------------- chrome */

QSplitter::handle {{
    background: transparent;
    width: {p.space_md}px;
}}

/* The strip along the foot of every screen. The design draws it as a band
   *inside* the surface - `#f6f4f0` on `#fbfaf8`, small muted type, no rule
   above it (artboards 3b, 3g, 3h) - and it was taking the canvas colour with
   a hairline, which on the light sheet read as a native window chrome
   sitting under the app rather than as part of it. */
QStatusBar {{
    background-color: {c(p.bg_hover)};
    color: {c(p.text_muted)};
    border: none;
    font-size: {p.font_size_sm}px;
    padding: 2px {p.space_lg}px;
}}

QStatusBar QLabel {{
    color: {c(p.text_muted)};
    font-size: {p.font_size_sm}px;
}}

QStatusBar::item {{
    border: none;
}}

QToolTip {{
    background-color: {c(p.bg_card)};
    color: {c(p.text)};
    border: 1px solid {c(p.border_strong)};
    border-radius: {p.radius_md}px;
    padding: {p.space_sm}px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {c(p.scrollbar)};
    border-radius: 5px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c(p.scrollbar_hover)};
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {c(p.scrollbar)};
    border-radius: 5px;
    min-width: 28px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c(p.scrollbar_hover)};
}}

QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
    border: none;
    height: 0;
    width: 0;
}}

QProgressBar {{
    background-color: {c(p.bg_muted)};
    border: none;
    border-radius: {p.radius_sm}px;
    height: 6px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {c(p.accent)};
    border-radius: {p.radius_sm}px;
}}

QCheckBox {{
    spacing: {p.space_sm}px;
    min-height: 28px;
    padding: 2px 0;
}}

/* Category filters are independent choices, so give each one a clear target
   and a visible selected state. The extra padding belongs to the whole
   control, not just its tiny indicator. */
QCheckBox[class="filter-chip"] {{
    spacing: 9px;
    min-height: 32px;
    padding: 4px 10px;
    border: 1px solid {c(p.border)};
    border-radius: {p.radius_lg}px;
    background-color: {c(p.bg_card)};
    color: {c(p.text)};
    font-weight: 500;
}}

QCheckBox[class="filter-chip"]:hover {{
    background-color: {c(p.bg_hover)};
    border-color: {c(p.accent)};
}}

QCheckBox[class="filter-chip"]:checked {{
    background-color: {c(p.bg_hover)};
    border-color: {c(p.accent)};
    color: {c(p.text)};
    font-weight: 600;
}}

QCheckBox[class="filter-chip"]:disabled {{
    background-color: {c(p.bg_muted)};
    border-color: {c(p.border)};
    color: {c(p.text_subtle)};
}}

/* The same reasoning as the radio below, and the same defect: left to the
   platform style the indicator is drawn from the *system* palette, so on the
   dark sheet a ticked box and an empty one were nearly the same grey square
   and there was no way to see which categories were on. The design draws a
   filled near-black square with a light tick (artboards 3b, 3j, 3l); the
   fill is `--primary`, which inverts with the sheet, and the tick is
   `--on-primary` baked into the two SVGs above. */
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    /* The unchecked box is the only visible state cue at rest. A decorative
       surface border is too faint here, so use the muted ink that clears
       the control-boundary contrast threshold in both themes. */
    border: 1px solid {c(p.text_muted)};
    background-color: {c(p.bg)};
}}

QCheckBox::indicator:hover {{
    border-color: {c(p.text)};
}}

QCheckBox::indicator:checked {{
    border-color: {c(p.primary)};
    background-color: {c(p.primary)};
    image: url({_check_mark(p)});
}}

QCheckBox::indicator:disabled {{
    border-color: {c(p.border)};
    background-color: {c(p.bg_muted)};
}}

QCheckBox:disabled {{
    color: {c(p.text_subtle)};
}}

/* The radio in a provider row (3d) says which account a run uses, so
   "chosen" has to be legible in both themes. Left to the platform style it
   is drawn from the system palette, which on the dark sheet gave three
   identical white discs and no way to see which one was selected. */
QRadioButton {{
    spacing: {p.space_sm}px;
    min-height: 28px;
}}

/* The radius has to match the *outer* box, which is the content plus both
   borders: a 12px indicator with a 4px border is 20px across, and a radius
   of 7 there draws a rounded square rather than a dot. */
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: none;
    background-color: {c(p.divider)};
}}

QRadioButton::indicator:hover {{
    background-color: {c(p.border_strong)};
}}

QRadioButton::indicator:checked {{
    border: 4px solid {c(p.accent)};
    border-radius: 11px;
    background-color: {c(p.bg)};
}}

QRadioButton:disabled {{
    color: {c(p.text_subtle)};
}}

QMessageBox, QFileDialog {{
    background-color: {c(p.bg_card)};
}}
"""


#: Textual variable name -> Palette attribute, for the values this app has
#: actually measured and does not want `ColorSystem` re-deriving from a base
#: hue. `text-muted` and `text-disabled` are the two Textual computes by
#: alpha-blending `foreground`, which is a plausible-looking grey with no
#: relationship to the AA threshold `Palette.text_muted` was stepped to; left
#: alone, the TUI's muted label would drift from the same word painted by
#: the Qt window and by the accessibility rule it is named after.
_TEXTUAL_VARIABLE_OVERRIDES = {
    "text-muted": "text_muted",
    "text-disabled": "text_subtle",
    "border": "border",
    "sev-critical": "sev_critical",
    "sev-high": "sev_high",
    "sev-medium": "sev_medium",
    "sev-none": "sev_none",
    #: Same three roles as the Qt inline selector (`CLASS_INLINE_*`), so a
    #: `.tcss` file can build the "analyze Site · depth 2" sentence out of
    #: the same three inks instead of picking its own.
    "inline-label": "text_muted",
    "inline-value": "text",
    "inline-caret": "text_subtle",
    "divider": "divider",
}


def build_textual_theme(p: Palette) -> Theme:
    """A Textual `Theme` carrying the same values `build_qss` paints with.

    Textual themes are registered by name and switched at runtime
    (`App.theme = "..."`), so this returns one `Theme` for one `Palette`
    rather than a style-sheet string; `build_textual_themes` below builds
    both and names them so the TUI can pick the one that matches Qt's.
    """
    return Theme(
        name=f"xaudit-{p.name}",
        dark=p.is_dark,
        primary=p.primary,
        secondary=p.accent,
        accent=p.accent,
        warning=p.amber,
        error=p.error,
        success=p.success,
        foreground=p.text,
        background=p.page_bg,
        surface=p.bg,
        panel=p.bg_muted,
        variables={
            name: getattr(p, attr) for name, attr in _TEXTUAL_VARIABLE_OVERRIDES.items()
        },
    )


def build_textual_themes() -> dict:
    """Both themes, named to match `palettes()` - `{"light": ..., "dark": ...}`."""
    return {name: build_textual_theme(palette) for name, palette in palettes().items()}


def resolve_mode(mode: str) -> str:
    """'auto' follows the OS; anything else is taken literally."""
    if mode in ("light", "dark"):
        return mode
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import Qt

        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    except Exception:  # noqa: BLE001 - old Qt, or no GUI; light is the safe answer
        return "light"


def _palette_with_installed_fonts(palette: Palette) -> Palette:
    """Use concrete installed families in QSS instead of CSS generic aliases.

    Qt's QSS font-family property logs a warning for generic names such as
    ``Sans Serif`` and ``monospace`` on macOS, even though QFont can resolve
    them. Ask Qt for the system family and select a fixed-width family from
    its installed list so a clean install never requests Geist or an alias
    QSS cannot resolve.
    """
    try:
        from PySide6.QtGui import QFontDatabase, QGuiApplication

        # QFontDatabase.families() aborts the process on some Qt/macOS builds
        # when no GUI application exists yet. Headless callers keep the
        # generic palette; the live window resolves concrete installed fonts.
        if QGuiApplication.instance() is None:
            return palette

        installed = {name.casefold(): name for name in QFontDatabase.families()}
        if not installed:
            return palette

        system = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.GeneralFont).family()
        general = installed.get(system.casefold())
        # Linux reports the alias itself ("Sans Serif") as the system family,
        # and lists it as installed - the very name QSS cannot resolve.
        if general is not None and general.casefold() in _GENERIC_FAMILIES:
            general = None
        if general is None:
            general = next((installed[name.casefold()] for name in (
                "Helvetica Neue", "Arial", "Segoe UI", "Noto Sans",
                "Liberation Sans", "DejaVu Sans",
            ) if name.casefold() in installed), next(
                (name for name in installed.values()
                 if name.casefold() not in _GENERIC_FAMILIES),
                next(iter(installed.values()))))

        fixed_names = (
            "Menlo", "SF Mono", "Cascadia Code", "Consolas", "Monaco",
            "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono",
            "Courier New",
        )
        fixed = next((installed[name.casefold()] for name in fixed_names
                      if name.casefold() in installed), None)
        if fixed is None:
            fixed = next((name for name in installed.values()
                          if name.casefold() not in _GENERIC_FAMILIES
                          and ("mono" in name.casefold()
                               or "courier" in name.casefold())), general)
        return replace(palette, font=general, font_mono=fixed)
    except Exception:  # noqa: BLE001 - preserve the palette if Qt font data is unavailable
        return palette


#: Family names that are aliases, not fonts: QSS warns on every one of them.
_GENERIC_FAMILIES = {"sans serif", "sans-serif", "sans", "serif", "monospace",
                     "system-ui", "geist", "geist mono"}


def current_palette(mode: str = "auto") -> Palette:
    return _palette_with_installed_fonts(palettes()[resolve_mode(mode)])


def apply_theme(app, mode: str = "auto") -> Palette:
    """Style the whole application and return the palette that was used, so
    callers can paint the few things QSS can't reach (web-preview HTML, a
    syntax highlighter's colours) with the same values."""
    palette = current_palette(mode)
    from PySide6.QtGui import QFont

    app_font = QFont(app.font())
    app_font.setFamily(palette.font)
    app.setFont(app_font)
    app.setStyleSheet(build_qss(palette))
    return palette
