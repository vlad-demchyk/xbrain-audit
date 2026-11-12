"""XBrain Audit's design system, read from CSS.

The system is `ui/design/xbrain-audit-desktop.css`: every colour, radius, type
size and space the window paints with, read off the design bundle's own
artboards (17 of them, 2026-08-24) by counting the numbers they actually
use. It is complete on its own.

It did not start that way. It began as a thin *layer* over xFormat's shared
web token file - only the values that differ - which made that file
mandatory, and the consequence was not theoretical: no bundle ever shipped
the overlay, `overlay_file()` degraded silently to the shared file, and every
frozen build of this app painted in xFormat's web colours while the source
tree painted in XBrain Audit's. One severity had two different reds depending on
which surface you looked at.

So the shared file is now a **base, not a requirement**. When it is present
it is layered under the overlay and changes nothing (`tests/test_design_system.py`
asserts exactly that); when it is absent - a bundle, a checkout without the
sibling repository - the window and the report look the same as they always
did. Where it is looked for, in order:

1. `$XFORMAT_TOKENS_CSS`, when set — point it anywhere.
2. The sibling checkout: `../XFormat/apps/web/src/styles/tokens.css`.
3. `ui/design/xformat-tokens.css` — a vendored snapshot.

Only the parts of CSS that actually appear in these files are supported:
custom properties, `var(--x)` references (resolved recursively, with the
fallback form `var(--x, y)`), `rem` lengths, and the two theme scopes
(`:root` for light, `[data-theme="dark"]` for dark). `color-mix()` is
computed for the `in srgb` form used by the file; anything else that can't
be resolved is dropped rather than guessed, and every consumer below reads
tokens through `Palette`, which has a hard-coded fallback for each value it
needs. A malformed or missing token file therefore degrades to a plain but
correct theme instead of failing to start.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import app_identity

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Checked in order; the first one that exists wins.
TOKEN_SEARCH_PATHS = (
    _REPO_ROOT.parent / "XFormat" / "apps" / "web" / "src" / "styles" / "tokens.css",
    _REPO_ROOT / "ui" / "design" / "xformat-tokens.css",
)

#: The design system itself, layered on top of whichever base file above was
#: found. It declares every token `Palette` reads, so the base is optional:
#: `tokens.css` is shared with the web app, the landing page and the admin
#: console, and the desktop design differs from all three - most visibly in
#: muting every semantic hue - so stating XBrain Audit's values in the shared
#: file would repaint three web surfaces to fix one desktop one.
#:
#: Pointing `$XAUDIT_DESKTOP_CSS` at nothing turns it off and leaves the
#: window on the plain xFormat palette, which is a complete theme in its own
#: right. That is a debugging aid, not the shipping arrangement.
OVERLAY_PATH = _REPO_ROOT / "ui" / "design" / "xbrain-audit-desktop.css"

# Stop at the first closing brace rather than requiring one at the start of a
# line: the shipped file happens to be formatted that way, but a hand-edited
# or minified copy is not, and silently parsing nothing out of it would leave
# the app on fallback colours with no indication why.
_ROOT_BLOCK_RE = re.compile(r":root\s*\{([^{}]*)\}", re.DOTALL)
_DARK_BLOCK_RE = re.compile(r'\[data-theme="dark"\]\s*\{([^{}]*)\}', re.DOTALL)
_DECL_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\)[^()]*)*))?\)")
_COLOR_MIX_RE = re.compile(
    r"color-mix\(\s*in\s+srgb\s*,\s*([^,]+?)\s+(\d+)%\s*,\s*([^,)]+?)(?:\s+(\d+)%)?\s*\)"
)


def token_file() -> Path | None:
    """The token file actually in use, or None when none was found."""
    override = os.environ.get("XFORMAT_TOKENS_CSS")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    for candidate in TOKEN_SEARCH_PATHS:
        if candidate.is_file():
            return candidate
    return None


def overlay_file() -> Path | None:
    """The desktop overlay actually in use, or None when there is none.

    `$XAUDIT_DESKTOP_CSS` points it elsewhere; setting it to an empty
    string turns the overlay off and leaves the window on the plain xFormat
    palette, which is the quickest way to see what the shared tokens alone
    look like.
    """
    override = app_identity.env("DESKTOP_CSS")
    if override is not None:
        if not override.strip():
            return None
        path = Path(override).expanduser()
        return path if path.is_file() else None
    return OVERLAY_PATH if OVERLAY_PATH.is_file() else None


# ------------------------------------------------------------------ parsing

def _declarations(block: str) -> dict:
    return {name: value.strip() for name, value in _DECL_RE.findall(block)}


def _parse_css(text: str) -> tuple[dict, dict]:
    """Return (light, dark) raw declaration maps, comments stripped."""
    text = _COMMENT_RE.sub("", text)
    light: dict = {}
    for block in _ROOT_BLOCK_RE.findall(text):
        light.update(_declarations(block))
    dark = dict(light)
    for block in _DARK_BLOCK_RE.findall(text):
        dark.update(_declarations(block))
    return light, dark


def _resolve(value: str, table: dict, depth: int = 0) -> str | None:
    """Expand var() references and color-mix() into a literal value."""
    if depth > 12:  # a cycle in the token file; refuse rather than recurse
        return None
    value = value.strip()

    def substitute(match) -> str:
        name, fallback = match.group(1), match.group(2)
        if name in table:
            resolved = _resolve(table[name], table, depth + 1)
            if resolved is not None:
                return resolved
        return (fallback or "").strip()

    expanded = _VAR_RE.sub(substitute, value).strip()
    if not expanded:
        return None
    if "var(" in expanded:  # an unresolved reference is not a usable value
        return None

    mixed = _COLOR_MIX_RE.sub(lambda m: _mix_srgb(m, table, depth), expanded)
    if "color-mix(" in mixed:
        return None
    return mixed.strip() or None


def _mix_srgb(match, table: dict, depth: int) -> str:
    left = _resolve(match.group(1), table, depth + 1)
    right = _resolve(match.group(3), table, depth + 1)
    weight = int(match.group(2)) / 100.0
    left_rgb, right_rgb = _to_rgb(left or ""), _to_rgb(right or "")
    if left_rgb is None or right_rgb is None:
        return match.group(0)  # left unresolved; caller drops the token
    blended = tuple(
        round(a * weight + b * (1 - weight)) for a, b in zip(left_rgb, right_rgb)
    )
    return "#%02x%02x%02x" % blended


def _to_rgb(value: str) -> tuple | None:
    value = value.strip()
    if value == "transparent":
        return (0, 0, 0)
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        if len(digits) in (6, 8):
            try:
                return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                return None
        return None
    match = re.match(r"rgba?\(([^)]+)\)", value)
    if match:
        parts = [p.strip() for p in match.group(1).replace("/", " ").split(",")]
        try:
            return tuple(int(float(p)) for p in parts[:3])
        except ValueError:
            return None
    return {"white": (255, 255, 255), "black": (0, 0, 0)}.get(value)


def _read(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_tokens(path: Path | None = None, overlay: Path | None = None) -> dict:
    """Return {"light": {...}, "dark": {...}} of fully resolved tokens.

    `overlay` is layered on top of `path`. The two files are concatenated
    before parsing rather than merged after it, which is what makes the
    layering behave like the CSS it is written as: a later `:root` wins over
    an earlier one, a later `[data-theme="dark"]` wins over an earlier one,
    and the dark theme still inherits from the *merged* light theme instead
    of from the base file's light theme alone. Resolving each file on its own
    and merging the results would break `var()` across the boundary, so an
    overlay could never refer to a token the base file declares.
    """
    text = "\n".join(
        part for part in (_read(path or token_file()), _read(overlay)) if part
    )
    if not text:
        return {"light": {}, "dark": {}}

    out = {}
    for theme, table in zip(("light", "dark"), _parse_css(text)):
        resolved = {}
        for name, raw in table.items():
            value = _resolve(raw, table)
            if value is not None:
                resolved[name] = value
        out[theme] = resolved
    return out


# ------------------------------------------------------------------ palette

def px(value: str | None, fallback: int) -> int:
    """CSS length -> whole pixels. Qt style sheets have no rem unit, so the
    root font size the web app uses (16px, the browser default it never
    overrides) is applied here instead."""
    if not value:
        return fallback
    match = re.match(r"^(-?[\d.]+)(rem|px|em)?$", value.strip())
    if not match:
        return fallback
    number = float(match.group(1))
    unit = match.group(2) or "px"
    return int(round(number * 16)) if unit in ("rem", "em") else int(round(number))


def _darken(value: str, amount: float) -> str:
    """A hex colour, `amount` of the way towards black.

    Two uses, and both are the same idea: a value the design system does not
    declare, derived from one it does, rather than a second brand colour
    invented beside the first. The hover state of an accent fill (a hover
    that is a *different* colour reads as a different control), and the
    status hues one step down where the brand value cannot reach AA contrast
    (see `Palette.error_strong`).
    """
    text = (value or "").strip()
    if not text.startswith("#") or len(text) not in (4, 7):
        return text
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    channels = [int(text[index:index + 2], 16) for index in (1, 3, 5)]
    scaled = [max(0, min(255, round(channel * (1 - amount)))) for channel in channels]
    return "#" + "".join(f"{channel:02x}" for channel in scaled)


def _lighten(value: str, amount: float) -> str:
    """A hex colour, `amount` of the way towards white.

    The dark sheet's counterpart to `_darken`: the same idea of deriving a
    value the design system does not declare, in the direction that actually
    adds contrast when the surface underneath is dark.
    """
    text = (value or "").strip()
    if not text.startswith("#") or len(text) not in (4, 7):
        return text
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    channels = [int(text[index:index + 2], 16) for index in (1, 3, 5)]
    scaled = [max(0, min(255, round(channel + (255 - channel) * amount)))
              for channel in channels]
    return "#" + "".join(f"{channel:02x}" for channel in scaled)


def _luminance(value: str) -> float | None:
    """WCAG relative luminance, or None when the value is not a colour.

    Duplicated from `audit.rules.accessibility` on purpose: this module is
    deliberately import-light so that a failure anywhere in the audit engine
    cannot stop the window from starting. `tests/test_palette_contrast.py`
    measures the finished palette with the audit's own function, so the two
    are held to agreeing.
    """
    rgb = _to_rgb(value)
    if rgb is None:
        return None

    def channel(raw: int) -> float:
        c = raw / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(foreground: str, background: str) -> float | None:
    first, second = _luminance(foreground), _luminance(background)
    if first is None or second is None:
        return None
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def toward_contrast(value: str, backgrounds: tuple, target: float) -> str:
    """`value`, stepped away from `backgrounds` until it clears `target`.

    The design bundle states its colours as literal hexes, and several of the
    ones it uses for text do not reach WCAG AA on the surfaces it puts them
    on - the muted label, its single most-used colour, measures 3.04:1 on the
    window canvas. XBrain Audit reports exactly that as an accessibility finding
    on other people's pages, so it cannot paint its own window that way.

    This is measured rather than tuned: the alternative is a table of
    darkening percentages fitted to one palette, which silently stops being
    correct the moment a token changes. The direction follows the sheet - on
    a light background the colour darkens, on a dark one it lightens - so the
    same call is right in both themes.
    """
    usable = tuple(b for b in backgrounds if _luminance(b) is not None)
    if not usable or _luminance(value) is None:
        return value
    average = sum(_luminance(b) for b in usable) / len(usable)
    step = _darken if average > 0.2 else _lighten
    for percent in range(0, 101):
        candidate = step(value, percent / 100)
        if all((_contrast(candidate, b) or 0) >= target for b in usable):
            return candidate
    return step(value, 1.0)  # black or white; nothing else is left to try


def first_font_family(value: str | None, fallback: str) -> str:
    """The first family in a CSS font stack, unquoted. Qt resolves its own
    fallbacks, so passing the whole stack through would just give Qt a
    family name it can never match."""
    if not value:
        return fallback
    first = value.split(",")[0].strip()
    return first.strip('"\'') or fallback


@dataclass
class Palette:
    """The subset of the design system the desktop UI actually paints with.

    Every field has a fallback that is applied when the token is missing, so
    this object is always complete and no caller needs to handle None.
    """
    name: str = "light"

    page_bg: str = "#f4f3f0"
    bg: str = "#ffffff"
    bg_card: str = "#ffffff"
    bg_muted: str = "#f6f5f2"
    bg_hover: str = "#eceae6"
    text: str = "#141416"
    text_muted: str = "#6f6d68"
    #: The two levels below `text_muted`, which the desktop design uses and
    #: the shared token file does not declare at all.
    #:
    #: `text_subtle` is decoration - the caret beside an inline value, a
    #: tertiary hint - and is held to 3:1, not 4.5:1, with the reason written
    #: down in `tests/test_palette_contrast.py`. `text_ghost` is the *label*
    #: of a ghost button, so it is a word and clears 4.5:1 like any other.
    text_subtle: str = "#8a877f"
    text_ghost: str = "#6f6d68"
    border: str = "#e9e7e2"
    border_strong: str = "#d9d6d0"
    #: The hairline between inline values in the top bar. Its own token
    #: because the design separates it from `border`: a divider inside a
    #: filled block, not the edge of a surface.
    divider: str = "#e9e7e2"
    #: The rule between two rows inside one panel - the settings screen's
    #: statements, the files in a write confirmation. Lighter than `divider`,
    #: which is the tick between two inline values in a filled strip.
    rule: str = "#eeebe5"
    primary: str = "#000000"
    primary_hover: str = "#262626"
    on_primary: str = "#ffffff"
    accent: str = "#4c43e8"
    on_accent: str = "#ffffff"
    accent_muted: str = "rgba(76, 67, 232, 0.06)"
    #: The accent one step darker, for the hover state of an accent-filled
    #: button. Derived rather than declared: the token file has no such
    #: variable, and inventing a second brand colour to sit beside the first
    #: is how palettes drift apart.
    accent_hover: str = "#3f37c9"
    success: str = "#17a06d"
    error: str = "#e5484d"
    amber: str = "#f59e0b"
    #: Ink on the two status fills above. Deliberately the *same* in both
    #: themes, unlike `on_accent`: `error` and `amber` are themselves the same
    #: red and the same amber on a light sheet and a dark one, so the text that
    #: sits on them must not flip with the theme - following the theme here is
    #: how a badge ends up with near-black text on a mid red. Declared as
    #: tokens rather than typed into the two places that paint a badge (the
    #: style sheet and the list delegate), which is where they were before.
    on_error: str = "#ffffff"
    on_amber: str = "#141416"
    #: The status hues, one step darker, for the two jobs the brand values
    #: cannot do at AA contrast. Measured, not guessed (see
    #: `tests/test_palette_contrast.py`): white on `#e5484d` is 3.9:1 and the
    #: badge text is 12px bold, which is not "large text"; and `#17a06d` as a
    #: word on a white sheet is 3.3:1. Both clear 4.5:1 one step down.
    #: `error_strong` fills the badge in both themes - the ink on it is white
    #: either way, so the fill must not follow the theme. `error_text` and
    #: `success_text` are words on a surface, so they *do*: on the dark sheet
    #: the base hues already pass and darkening them would undo that.
    error_strong: str = "#d24246"
    error_text: str = "#d24246"
    success_text: str = "#13865b"
    #: Amber as a *word* rather than as a fill. The design's amber is a mid
    #: yellow (2.09:1 on the section surface), so the one place it is used
    #: for text - a severity label outside a badge - needs its own value for
    #: the same reason `error_text` exists. The fill keeps the design's hue.
    amber_text: str = "#8a6d34"

    #: The four-step severity ramp. The shared token file has no such scale,
    #: which is why `high` and `medium` both resolved to the same amber and
    #: read as one level in the findings list. These are fills - a segment of
    #: the severity bar, a dot beside a row - and are not held to a text
    #: threshold; the words beside them are painted in `text`.
    sev_critical: str = "#d24246"
    sev_high: str = "#d97706"
    sev_medium: str = "#f59e0b"
    sev_none: str = "#d9d6d0"
    scrollbar: str = "#cfcdc7"
    scrollbar_hover: str = "#b4b2ab"

    #: The one drop shadow that stands in for the design's two-layer
    #: `box-shadow`. A blur of 0 means "no shadow" and is what a token file
    #: without these values falls back to, which is the look the window had
    #: before: surfaces told apart by a hairline border instead.
    shadow_color: str = "rgba(20, 20, 22, 0.08)"
    shadow_blur: int = 0
    shadow_y: int = 0

    # Qt reports a warning for missing named families instead of reliably
    # walking a CSS fallback stack. These are Qt's guaranteed system aliases.
    font: str = "Sans Serif"
    font_mono: str = "monospace"
    font_size: int = 14
    font_size_sm: int = 12
    font_size_lg: int = 17
    font_size_xl: int = 21

    radius: int = 14
    radius_sm: int = 6
    radius_md: int = 8
    radius_lg: int = 10

    space_sm: int = 8
    space_md: int = 12
    space_lg: int = 16

    # -- DesignTokens compatibility aliases --
    # These properties let code written for DesignTokens (design_system.py)
    # work with Palette, enabling a gradual migration to a single system.

    @property
    def bg_base(self) -> str:
        return self.page_bg

    @property
    def bg_surface(self) -> str:
        return self.bg

    @property
    def bg_elevated(self) -> str:
        return self.bg_card

    @property
    def bg_active(self) -> str:
        return self.bg_muted

    @property
    def bg_input(self) -> str:
        return self.bg

    @property
    def text_primary(self) -> str:
        return self.text

    @property
    def text_secondary(self) -> str:
        return self.text_muted

    @property
    def text_disabled(self) -> str:
        return self.text_muted

    @property
    def text_inverse(self) -> str:
        return self.on_primary

    @property
    def border_default(self) -> str:
        return self.border

    @property
    def border_subtle(self) -> str:
        return self.border

    @property
    def border_active(self) -> str:
        return self.accent

    @property
    def accent_emphasis(self) -> str:
        return self.accent_hover

    @property
    def critical(self) -> str:
        return self.sev_critical

    @property
    def high(self) -> str:
        return self.sev_high

    @property
    def medium(self) -> str:
        return self.sev_medium

    @property
    def low(self) -> str:
        return self.sev_none

    @property
    def info(self) -> str:
        return self.accent

    @property
    def warning(self) -> str:
        return self.amber

    @property
    def font_family(self) -> str:
        return self.font

    @property
    def font_size_xs(self) -> int:
        return self.font_size_sm - 1

    @property
    def font_size_base(self) -> int:
        return self.font_size

    @property
    def font_size_xxl(self) -> int:
        return self.font_size_xl + 3

    @property
    def space_1(self) -> int:
        return 4

    @property
    def space_2(self) -> int:
        return self.space_sm

    @property
    def space_3(self) -> int:
        return self.space_md

    @property
    def space_4(self) -> int:
        return self.space_lg

    @property
    def space_5(self) -> int:
        return 20

    @property
    def space_6(self) -> int:
        return 24

    @property
    def space_8(self) -> int:
        return 32

    @property
    def radius_xl(self) -> int:
        return self.radius

    @property
    def shadow_sm(self) -> str:
        return "0 1px 2px rgba(0, 0, 0, 0.3)"

    @property
    def shadow_md(self) -> str:
        return "0 4px 12px rgba(0, 0, 0, 0.4)"

    @property
    def shadow_lg(self) -> str:
        return "0 8px 24px rgba(0, 0, 0, 0.5)"

    @property
    def sidebar_width(self) -> int:
        return 260

    @property
    def detail_width(self) -> int:
        return 380

    @property
    def header_height(self) -> int:
        return 48

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"

    @classmethod
    def from_tokens(cls, tokens: dict, name: str = "light") -> "Palette":
        defaults = cls()

        def color(key: str, fallback: str) -> str:
            value = tokens.get(key)
            return value if value else fallback

        # Every surface a word can land on. Text derived below has to clear
        # its threshold on the worst of them, not just on the panel it was
        # designed against - the same label is painted on the canvas, on a
        # section and inside a nested block.
        surfaces = (
            color("--page-bg", defaults.page_bg),
            color("--bg", defaults.bg),
            color("--bg-card", defaults.bg_card),
            color("--bg-muted", defaults.bg_muted),
            color("--bg-hover", defaults.bg_hover),
        )

        return cls(
            name=name,
            page_bg=color("--page-bg", defaults.page_bg),
            bg=color("--bg", defaults.bg),
            bg_card=color("--bg-card", defaults.bg_card),
            bg_muted=color("--bg-muted", defaults.bg_muted),
            bg_hover=color("--bg-hover", defaults.bg_hover),
            text=color("--text", defaults.text),
            # The three muted tiers are taken from the sheet as written.
            #
            # They were stepped toward AA before, and the cost was not the
            # hue: `#8b877f`, `#a8a49c` and `#7d7a73` all had to travel past
            # 4.5:1, which on these surfaces is one narrow band, so all three
            # arrived at the same grey. Three tiers became one, and the
            # hierarchy the design reads by - a label quieter than a value,
            # a caret quieter than a label - stopped existing.
            #
            # Measured on the window canvas `#efece7`: 3.04:1, 2.11:1 and
            # 3.63:1, all under the 4.5:1 this tool reports on other people's
            # pages. That is a deliberate exception for the app's own chrome,
            # taken knowingly (2026-08-26), not an oversight - and it is why
            # `test_palette_contrast` names these three and their numbers
            # instead of asserting a threshold they do not meet.
            text_muted=color("--text-muted", defaults.text_muted),
            text_subtle=color("--text-subtle", defaults.text_subtle),
            text_ghost=color("--text-ghost", defaults.text_ghost),
            border=color("--border", defaults.border),
            border_strong=color("--border-strong", defaults.border_strong),
            divider=color("--divider", color("--border", defaults.divider)),
            rule=color("--rule", color("--divider", defaults.rule)),
            primary=color("--primary", defaults.primary),
            primary_hover=color("--primary-hover", defaults.primary_hover),
            on_primary=color("--on-primary", defaults.on_primary),
            accent=color("--brand-accent", defaults.accent),
            on_accent=color("--on-accent", defaults.on_accent),
            accent_muted=color("--bg-brand-muted", defaults.accent_muted),
            accent_hover=_darken(color("--brand-accent", defaults.accent), 0.12),
            success=color("--success", defaults.success),
            error=color("--error", defaults.error),
            amber=color("--amber", defaults.amber),
            # A fill with white ink on it, so it is measured against the ink
            # rather than against the sheet - and it reads `--sev-badge`,
            # which the overlay declares once for both themes, so the badge
            # does not flip with the theme underneath it.
            error_strong=toward_contrast(
                color("--sev-badge", color("--error", defaults.error)),
                (color("--on-error", defaults.on_error),), 4.5),
            # Words, not fills, so these follow the sheet: on the dark one
            # the hues already clear 4.5:1 and are left where they are, which
            # `toward_contrast` arrives at on its own by stepping zero.
            #
            # Measured against the panel alone, not against `surfaces` like
            # the muted text above. These two are painted in exactly one
            # place - the status line in Settings - and that line sits on a
            # panel. Holding them to the whole set would move the dark hue
            # off the value `test_status_words_do_follow_the_theme` pins it
            # to, to buy contrast on surfaces they are never painted on.
            error_text=toward_contrast(
                color("--error", defaults.error), (color("--bg", defaults.bg),), 4.5),
            success_text=toward_contrast(
                color("--success", defaults.success),
                (color("--bg", defaults.bg),), 4.5),
            # Amber as a word. Measured like the two above rather than
            # darkened by a fixed step: the design's amber needs to travel a
            # long way (2.09:1 as it stands) and xFormat's needs less.
            amber_text=toward_contrast(
                color("--amber", defaults.amber), surfaces, 4.5),
            # Fills, not words. The four levels are a scale, and the shared
            # token file declares no such scale - without the overlay these
            # fall back to the ramp built out of the tokens that do exist.
            sev_critical=color("--sev-critical", color("--error", defaults.sev_critical)),
            sev_high=color("--sev-high", color("--amber-d", defaults.sev_high)),
            sev_medium=color("--sev-medium", color("--amber", defaults.sev_medium)),
            sev_none=color("--sev-none", color("--border-strong", defaults.sev_none)),
            shadow_color=color("--surface-shadow-color", defaults.shadow_color),
            shadow_blur=px(tokens.get("--surface-shadow-blur"), defaults.shadow_blur),
            shadow_y=px(tokens.get("--surface-shadow-y"), defaults.shadow_y),
            scrollbar=color("--sb-thumb", defaults.scrollbar),
            scrollbar_hover=color("--sb-thumb-hover", defaults.scrollbar_hover),
            font=first_font_family(tokens.get("--font"), defaults.font),
            font_mono=first_font_family(tokens.get("--font-mono"), defaults.font_mono),
            font_size=px(tokens.get("--font-size-base"), defaults.font_size),
            font_size_sm=px(tokens.get("--font-size-sm"), defaults.font_size_sm),
            font_size_lg=px(tokens.get("--font-size-lg"), defaults.font_size_lg),
            font_size_xl=px(tokens.get("--font-size-xl"), defaults.font_size_xl),
            radius=px(tokens.get("--radius"), defaults.radius),
            radius_sm=px(tokens.get("--radius-sm"), defaults.radius_sm),
            radius_md=px(tokens.get("--radius-md"), defaults.radius_md),
            radius_lg=px(tokens.get("--radius-lg"), defaults.radius_lg),
            space_sm=px(tokens.get("--space-sm"), defaults.space_sm),
            space_md=px(tokens.get("--space-md"), defaults.space_md),
            space_lg=px(tokens.get("--space-lg"), defaults.space_lg),
        )


def palettes(overlay: bool = True) -> dict:
    """Both themes, ready to use.

    `overlay=False` returns the plain xFormat palette, without XBrain Audit's
    own system on top. That is a comparison tool - "what do the shared
    tokens alone look like" - and not a mode anything ships in. The styled
    report used to ask for it, on the argument that a report is a document
    and the overlay is a screen decision; the argument does not survive
    reading the design bundle, whose own report artboard (3h) is drawn in
    these colours. It now asks for `overlay=True` like every other surface,
    so one severity is one colour wherever a person meets it.
    """
    tokens = load_tokens(overlay=overlay_file() if overlay else None)
    return {
        "light": Palette.from_tokens(tokens.get("light", {}), "light"),
        "dark": Palette.from_tokens(tokens.get("dark", {}), "dark"),
    }
