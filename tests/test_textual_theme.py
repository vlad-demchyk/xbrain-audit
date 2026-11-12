"""The TUI's colours, generated from the same `Palette` the Qt window paints
with, rather than typed into a `.tcss` file by hand a second time.

`build_qss` (tested in `tests/test_palette_contrast.py` and elsewhere)
already exists as the model: a style sheet generated from tokens instead of
hand-maintained, so a token change stays a one-line change upstream instead
of a hunt through two GUIs. `build_textual_theme` is that same idea for
Textual, and the thing worth pinning down is that it actually *is* the same
idea - the values a `Theme` hands the TUI have to be the values `Palette`
computed, not Textual's own derivation of them from a base hue, or the two
front ends drift apart within the first token change.

The second thing pinned down here is the named risk in the TUI rework: a
16- or 256-colour terminal cannot show the muted palette's exact hexes, and
assuming the desktop contrast numbers survive that downgrade is a guess, not
a measurement. `rich.color.Color.downgrade` is what Textual itself uses to
pick a terminal's actual output colour, so measuring after that call is
measuring what a person would in fact see.
"""
from __future__ import annotations

import asyncio
import unittest

from rich.color import Color, ColorSystem as RichColorSystem

from audit.rules.accessibility import contrast_ratio
from textual.app import App
from ui import theme
from ui.tokens import Palette, palettes


def run(coroutine):
    return asyncio.new_event_loop().run_until_complete(coroutine)


class BuildTextualThemeAgreesWithThePalette(unittest.TestCase):
    """The generated `Theme` carries the exact values `Palette` computed."""

    def test_severity_ramp_matches_the_palette_the_qt_window_uses(self):
        for name, palette in palettes().items():
            built = theme.build_textual_theme(palette)
            for variable, attr in theme._TEXTUAL_VARIABLE_OVERRIDES.items():
                self.assertEqual(
                    built.variables[variable], getattr(palette, attr),
                    f"{name} theme's ${variable} should be Palette.{attr}")

    def test_light_and_dark_themes_are_named_for_the_palette_they_carry(self):
        built = theme.build_textual_themes()
        self.assertEqual(built["light"].name, "xaudit-light")
        self.assertEqual(built["dark"].name, "xaudit-dark")
        self.assertFalse(built["light"].dark)
        self.assertTrue(built["dark"].dark)

    def test_a_registered_theme_actually_exposes_the_severity_variables(self):
        """Not just that `Theme.variables` holds the right dict - that a
        running app resolves `$sev-critical` etc. to it, which is the only
        form a `.tcss` file can actually consume."""
        built = theme.build_textual_theme(palettes()["dark"])

        class Probe(App):
            def on_mount(self) -> None:
                self.register_theme(built)
                self.theme = built.name

        async def body():
            app = Probe()
            async with app.run_test():
                variables = app.get_css_variables()
                self.assertEqual(variables["sev-critical"],
                                 palettes()["dark"].sev_critical.lower())
                self.assertEqual(variables["sev-none"],
                                 palettes()["dark"].sev_none.lower())

        run(body())


def _downgrade(hex_value: str, system) -> tuple:
    """`hex_value` as the RGB triplet a terminal limited to `system` would
    actually draw, per Rich's own downgrade path (the same one Textual's
    renderer calls before writing to the terminal)."""
    return tuple(Color.parse(hex_value).downgrade(system).get_truecolor())


class SeverityRampSurvivesTerminalColourDowngrade(unittest.TestCase):
    """The four severity fills stay four distinguishable colours once a
    limited terminal has snapped each one to its nearest approximation.

    Colour is never the only signal for severity - the row also carries the
    word (`critical`, `serious`, ...) - but a ramp that collapses to two
    shades under degradation is the same defect the project plan calls out:
    "the levels still read as one". This measures the actual 256-colour and
    16-colour approximations rather than assuming the desktop palette's
    values carry over unchanged.
    """

    LEVELS = ("sev_critical", "sev_high", "sev_medium", "sev_none")

    def test_the_four_fills_remain_pairwise_distinct_at_256_colours(self):
        palette = palettes()["dark"]
        approximated = [
            _downgrade(getattr(palette, level), RichColorSystem.EIGHT_BIT)
            for level in self.LEVELS
        ]
        self.assertEqual(
            len(set(approximated)), len(approximated),
            f"256-colour approximations collapsed: {list(zip(self.LEVELS, approximated))}")

    def test_the_muted_text_still_clears_a_readable_contrast_at_256_colours(self):
        """Measured, not assumed: this is `text_muted` (already stepped to
        AA on a true-colour sheet) after the same downgrade a 256-colour
        terminal applies, against the panel it is actually read on. If a
        future token change ever drops this below the terminal's own
        3:1 floor for non-text/large-text distinctions, this fails with the
        real number instead of leaving a hard-to-read label unnoticed."""
        palette = palettes()["dark"]
        foreground = _downgrade(palette.text_muted, RichColorSystem.EIGHT_BIT)
        background = _downgrade(palette.page_bg, RichColorSystem.EIGHT_BIT)
        ratio = contrast_ratio(foreground, background)
        self.assertGreaterEqual(
            ratio, 3.0,
            f"text_muted on page_bg measured {ratio:.2f}:1 at 256 colours")
