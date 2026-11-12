"""`xbrain-audit-desktop.css` is the design system, and it is complete.

It began as a thin layer over xFormat's shared web token file - only the
values that differ - which quietly made that file mandatory. The cost was
not theoretical: no bundle ever shipped the overlay, `overlay_file()`
degrades to the shared file without saying so, and every frozen build
painted in xFormat's web colours while the source tree painted in
XBrain Audit's. The same severity was #e5484d in one place and #c0564f in
another, in one product.

Two properties keep that from coming back, and they are different claims:

* **Complete.** Every token `Palette` reads is declared here, in both
  themes, so the app is correct with no base file at all.
* **Authoritative.** Layering the shared file underneath changes nothing.
  Completeness alone would not give this - a token could be declared here
  and still be overridden if the layering ran the other way.

The values themselves are read off the design bundle's artboards by counting
what they use, so the numbers in `KNOWN_FROM_THE_ARTBOOK` below are
assertions about the bundle, not preferences.
"""
from __future__ import annotations

import dataclasses
import re
import unittest
from pathlib import Path

from ui import tokens

#: A path that certainly is not a token file, so `load_tokens` reads the
#: overlay and nothing else. `None` would not do it: that means "find one".
NO_BASE = Path("/nonexistent/xformat-tokens.css")


def _overlay_only(theme: str) -> tokens.Palette:
    loaded = tokens.load_tokens(path=NO_BASE, overlay=tokens.OVERLAY_PATH)
    return tokens.Palette.from_tokens(loaded[theme], theme)


def _token_names_palette_reads() -> set:
    import inspect

    source = inspect.getsource(tokens.Palette.from_tokens)
    return set(re.findall(r'"(--[\w-]+)"', source))


def _declared(scope: str) -> set:
    text = tokens.OVERLAY_PATH.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    light, dark = text.split('[data-theme="dark"]', 1)
    block = light if scope == "light" else light + dark
    return set(re.findall(r"(--[\w-]+)\s*:", block))


class ItIsComplete(unittest.TestCase):

    def test_every_token_the_palette_reads_is_declared(self):
        for theme in ("light", "dark"):
            declared = _declared(theme)
            for name in sorted(_token_names_palette_reads()):
                with self.subTest(theme=theme, token=name):
                    self.assertIn(name, declared)

    def test_the_app_is_correct_with_no_shared_file_at_all(self):
        """The bundle case, and the case of a checkout without the sibling
        repository. Both used to be silently different from a dev machine."""
        for theme in ("light", "dark"):
            alone = _overlay_only(theme)
            together = tokens.palettes(overlay=True)[theme]
            for field in dataclasses.fields(alone):
                with self.subTest(theme=theme, token=field.name):
                    self.assertEqual(getattr(alone, field.name),
                                     getattr(together, field.name))

    def test_no_field_falls_back_to_the_dataclass_default(self):
        """A field that happens to equal its Python fallback is not proof of
        a bug, but a *colour* that does means the CSS never supplied it -
        and the fallbacks are xFormat's, not this design's."""
        fallbacks = tokens.Palette()
        alone = _overlay_only("light")
        for name in ("page_bg", "bg", "bg_muted", "text", "text_muted",
                     "border", "border_strong", "accent", "error", "amber",
                     "success", "primary"):
            with self.subTest(token=name):
                self.assertNotEqual(getattr(alone, name),
                                    getattr(fallbacks, name))


class ItIsAuthoritative(unittest.TestCase):

    def test_the_shared_file_underneath_changes_nothing(self):
        base = tokens.token_file()
        self.assertIsNotNone(base, "the vendored snapshot should be found")
        layered = tokens.Palette.from_tokens(
            tokens.load_tokens(path=base, overlay=tokens.OVERLAY_PATH)["light"],
            "light")
        self.assertEqual(dataclasses.asdict(layered),
                         dataclasses.asdict(_overlay_only("light")))

    def test_turning_it_off_is_still_a_complete_theme(self):
        """The debugging aid has to keep working: without the overlay the
        window falls back to xFormat's system rather than to nothing."""
        plain = tokens.palettes(overlay=False)["light"]
        self.assertTrue(plain.bg.startswith("#"))
        self.assertNotEqual(plain.error, _overlay_only("light").error)


#: Read off the artboards, by counting what they use rather than by taste.
#: A number here that stops matching the bundle is a design decision someone
#: made without the bundle, which is the drift this file exists to catch.
KNOWN_FROM_THE_ARTBOOK = {
    # Surfaces: canvas, panel, block inside a panel.
    "page_bg": "#efece7", "bg": "#fbfaf8", "bg_muted": "#f2efeb",
    "text": "#1c1b19", "text_muted": "#8b877f", "text_subtle": "#a8a49c",
    "border": "#e2ded7", "border_strong": "#c9c4ba",
    "accent": "#4b46b8", "accent_muted": "#e8e5f7",
    "primary": "#1c1b19", "on_primary": "#fbfaf8",
    # The four-step severity ramp the shared tokens do not have.
    "sev_critical": "#c0564f", "sev_high": "#cf7a52",
    "sev_medium": "#d6a94e", "sev_none": "#c9c4ba",
    "success": "#3f7a58", "error": "#c0564f", "amber": "#d6a94e",
    # Panel 14, nested block 10, button 8, chip 7.
    "radius": 14, "radius_lg": 10, "radius_md": 8, "radius_sm": 7,
    "font_size": 14, "font_size_sm": 12, "font_size_lg": 15,
    "font_size_xl": 22,
}


class ItIsTheBundlesValues(unittest.TestCase):

    def test_the_light_sheet_matches_what_the_artboards_draw(self):
        palette = _overlay_only("light")
        for name, expected in KNOWN_FROM_THE_ARTBOOK.items():
            with self.subTest(token=name):
                self.assertEqual(getattr(palette, name), expected)

    def test_dark_is_its_own_ramp_and_not_an_inversion_of_light(self):
        """The bundle says so explicitly, and it matters: a warm graphite
        read as inverted light gives cold greys and a red that glows."""
        light, dark = _overlay_only("light"), _overlay_only("dark")
        for name in ("page_bg", "bg", "text", "sev_critical", "accent"):
            with self.subTest(token=name):
                self.assertNotEqual(getattr(light, name), getattr(dark, name))
        # A corner is not a colour: the geometry is one system on both sheets.
        for name in ("radius", "radius_lg", "radius_md", "radius_sm",
                     "font_size", "space_sm", "space_md", "space_lg"):
            with self.subTest(token=name):
                self.assertEqual(getattr(light, name), getattr(dark, name))


if __name__ == "__main__":
    unittest.main()
