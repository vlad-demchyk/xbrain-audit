"""The desktop design's surfaces, which are separated by tone and a shadow
rather than by a border.

QSS has no `box-shadow`, so the two shadows the design stacks on every
surface become one `QGraphicsDropShadowEffect` carried in the palette. The
part worth testing is not the look but the fallback: a token file without the
desktop overlay must produce `shadow_blur == 0`, and a zero blur must clear
any effect already on the widget rather than draw a blurless smudge. That is
what keeps the plain xFormat palette - which the window still starts on when
`$XAUDIT_DESKTOP_CSS` is empty - on its hairline-border look.

Headless: Qt runs on the offscreen platform, like the other widget tests.
"""
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui import tokens

try:
    from PySide6.QtWidgets import QApplication, QWidget
    from ui import theme
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


OVERLAY = tokens.OVERLAY_PATH


class ShadowTokens(unittest.TestCase):
    def test_the_overlay_declares_a_shadow_for_both_sheets(self):
        loaded = tokens.load_tokens(overlay=OVERLAY)
        for name in ("light", "dark"):
            palette = tokens.Palette.from_tokens(loaded[name], name)
            with self.subTest(theme=name):
                self.assertGreater(palette.shadow_blur, 0)
                self.assertTrue(palette.shadow_color.startswith("rgba("))

    def test_the_two_sheets_do_not_share_a_shadow(self):
        """A shadow tuned for a near-white canvas is invisible on a near-black
        one, so the overlay states each separately."""
        loaded = tokens.load_tokens(overlay=OVERLAY)
        light = tokens.Palette.from_tokens(loaded["light"], "light")
        dark = tokens.Palette.from_tokens(loaded["dark"], "dark")
        self.assertNotEqual(light.shadow_color, dark.shadow_color)

    def test_without_the_overlay_there_is_no_shadow(self):
        """The fallback that keeps the plain xFormat palette usable."""
        palette = tokens.Palette.from_tokens(
            tokens.load_tokens(overlay=None).get("light", {}), "light")
        self.assertEqual(palette.shadow_blur, 0)


class TheReportIsPaintedInTheProductsOwnPalette(unittest.TestCase):
    """One product, one set of colours - the design bundle's.

    This class used to say the opposite, and pinned the report to the plain
    xFormat web palette on the argument that a report is paper while the
    desktop overlay is a screen decision. The argument does not survive
    looking at the bundle: the overlay *is* XBrain Audit's palette, the bundle
    draws the report itself in it (artboard 3h, down to the severity dots),
    and its sheet is a paper tone rather than a screen one. What the old
    arrangement actually produced was one severity in two different reds - the
    window's #c0564f and the web's #e5484d - depending on which surface a
    person happened to be looking at.

    What was right in the old class and is kept: this is checked at the call
    site, because the two palettes are one keyword apart and the wrong one
    still renders a perfectly plausible document.
    """

    def test_the_report_generator_asks_for_the_design_bundle_palette(self):
        import inspect

        from report import template

        source = inspect.getsource(template.render_html)
        self.assertIn("palettes(overlay=True)", source)

    def test_the_sheet_it_prints_on_is_still_paper(self):
        """The one property the old reasoning was protecting. The overlay's
        surface is a warm near-white, not a screen grey: light enough to be
        paper, which is what a printed page has to be."""
        sheet = tokens.palettes(overlay=True)["light"].bg
        red, green, blue = (int(sheet[i:i + 2], 16) for i in (1, 3, 5))
        self.assertGreater(min(red, green, blue), 0xF5)

    def test_one_severity_is_one_colour_across_every_surface(self):
        """The window's severity bar, the TUI's table and the report all read
        the same four tokens, so a person comparing two surfaces is comparing
        the same thing."""
        window = tokens.palettes()["light"]
        from report.template import _severity_inks

        self.assertEqual(list(_severity_inks(window).values()),
                         [window.sev_critical, window.sev_high,
                          window.sev_medium, window.sev_none])


@unittest.skipIf(QApplication is None, "PySide6 not available")
class SurfacePainting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_qcolor_keeps_the_alpha_the_css_states(self):
        # 0.07 of 255 is 18. Losing this is the failure mode that matters:
        # a shadow at full alpha is a black box, not a shadow.
        colour = theme.qcolor("rgba(28, 27, 25, 0.07)")
        self.assertEqual(
            (colour.red(), colour.green(), colour.blue(), colour.alpha()),
            (28, 27, 25, 18))

    def test_qcolor_accepts_the_other_forms_the_token_file_uses(self):
        self.assertEqual(theme.qcolor("#1c1b19").alpha(), 255)
        self.assertEqual(theme.qcolor("#d8d6d0a3").alpha(), 0xA3)

    def test_qcolor_refuses_to_guess(self):
        """An unparseable value becomes fully transparent rather than an
        arbitrary colour - an invisible shadow beats a black one."""
        self.assertEqual(theme.qcolor("not-a-colour").alpha(), 0)
        self.assertEqual(theme.qcolor("").alpha(), 0)

    def test_a_shadow_is_applied_and_then_cleared(self):
        widget = QWidget()
        shadowed = tokens.Palette(shadow_blur=18, shadow_y=3,
                                  shadow_color="rgba(28, 27, 25, 0.07)")
        effect = theme.soft_shadow(widget, shadowed)
        self.assertIsNotNone(effect)
        self.assertEqual(effect.blurRadius(), 18)
        self.assertEqual(effect.yOffset(), 3)
        self.assertIs(widget.graphicsEffect(), effect)

        # Switching to a palette with no shadow must take the old one off.
        # Qt deletes the replaced effect, so the check is on the widget.
        self.assertIsNone(theme.soft_shadow(widget, tokens.Palette()))
        self.assertIsNone(widget.graphicsEffect())

    def test_the_surfaces_are_drawn_without_a_border(self):
        """The design draws none, and a hairline on top of tone plus shadow
        reads as a seam."""
        qss = theme.build_qss(theme.current_palette("light"))
        for name in (theme.CLASS_SURFACE, theme.CLASS_INSET):
            with self.subTest(surface=name):
                block = qss.split(f'QWidget[class="{name}"] {{')[1].split("}")[0]
                self.assertIn("border: none", block)

    def test_the_three_surface_levels_are_distinct(self):
        """Tone is what separates them, so two levels sharing a colour would
        make the middle one disappear."""
        palette = theme.current_palette("light")
        levels = {palette.page_bg, palette.bg, palette.bg_muted}
        self.assertEqual(len(levels), 3)


class RenderedWindow:
    """A window rendered in one theme, with its pixels readable.

    A mixin rather than a `TestCase`: subclassed per sheet so a failure names
    the theme it happened in, and not a case in its own right, so the suite
    does not report seven phantom skips for a base class nobody runs.
    """
    THEME = "light"

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from ui.main_window import MainWindow

        cls.palette = theme.current_palette(cls.THEME)
        cls.window = MainWindow()
        # The working layout: this file measures the surfaces of the toolbar,
        # the inline strip and the three columns, and the window opens on the
        # setup screen while nothing has run.
        cls.window.show_setup(False)
        cls.window.resize(1300, 800)
        # On the window, not on the application: setting the sheet on the
        # QApplication re-polishes every live widget in the process and
        # segfaults a full run. See the same note in `test_window_shell.py`.
        cls.window.setStyleSheet(theme.build_qss(cls.palette))
        # The delegate and the drop shadow keep their own copy of the
        # palette, so the sheet alone would leave them on the other theme.
        cls.window.apply_palette(cls.palette)
        cls.window.show()
        cls.app.processEvents()
        cls.app.processEvents()
        cls.shot = cls.window.grab().toImage()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()

    def pixel(self, x: int, y: int) -> str:
        colour = self.shot.pixelColor(x, y)
        return "#%02x%02x%02x" % (colour.red(), colour.green(), colour.blue())

    def test_the_canvas_is_the_canvas(self):
        self.assertEqual(self.pixel(4, 400), self.palette.page_bg)

    def test_the_top_row_sits_on_a_surface(self):
        # Above the inline strip, in the row's own padding.
        self.assertEqual(self.pixel(1000, 14), self.palette.bg)

    def test_the_inline_strip_is_the_level_below_the_row(self):
        """The selectors sit in a filled block inside the row. Two levels, so
        a caret reads as "this word can be changed" rather than as a stray
        glyph floating on the surface."""
        self.assertEqual(self.pixel(400, 25), self.palette.bg_muted)

    def test_a_column_sits_on_a_surface_not_on_the_canvas(self):
        """The failure this class exists for: the columns rendered in the
        canvas colour, so the window read as one flat sheet with lines drawn
        on it."""
        # Below everything the empty state draws. It grew a mark and two
        # buttons (artboard 3i), and y=300 landed on one of them - a test
        # that samples wherever content happens not to be is a test that
        # breaks whenever the content is right.
        for x in (700, 1100):
            with self.subTest(column_at=x):
                self.assertEqual(self.pixel(x, 500), self.palette.bg)

    def test_a_panel_head_is_the_level_between(self):
        self.assertEqual(self.pixel(700, 90), self.palette.bg_muted)

    def test_a_column_has_no_border_drawn_round_it(self):
        """The design draws none. The hairline this used to have was clearest
        on the dark sheet, where it outlined every column in #3a3631 - tone
        and shadow are what separate a zone from the canvas now."""
        edge = self.pixel(490, 300)
        self.assertNotEqual(edge, self.palette.border)
        self.assertNotEqual(edge, self.palette.border_strong)

    def test_the_levels_actually_differ_on_screen(self):
        """Stated as a rendered comparison rather than a palette one, so that
        a change which makes them equal fails here even if the tokens still
        say they are three colours."""
        levels = {self.pixel(4, 400), self.pixel(700, 300), self.pixel(700, 90)}
        self.assertEqual(len(levels), 3)


@unittest.skipIf(QApplication is None, "PySide6 not available")
class LightSheet(RenderedWindow, unittest.TestCase):
    THEME = "light"


@unittest.skipIf(QApplication is None, "PySide6 not available")
class DarkSheet(RenderedWindow, unittest.TestCase):
    """The dark theme is a warm graphite of its own, not an inversion of the
    light one, and until this class existed nothing had ever rendered it."""
    THEME = "dark"


if __name__ == "__main__":
    unittest.main()


def _spec_text(spec: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent / spec).read_text(
        encoding="utf-8")


class EveryBundleCarriesWhatTheCodeReads(unittest.TestCase):
    """A frozen app has no source tree to fall back to.

    Two assets went missing this way, and both failed silently, which is what
    makes the class worth a test rather than two fixes:

    * `xbrain-audit-desktop.css` - `overlay_file()` degrades to the shared token
      file, so every bundle ever built painted in xFormat's web colours while
      the source tree painted in XBrain Audit's, and it looked deliberate.
    * `ui/design/assets` in the CLI spec - the report logo of the time (since removed)
      returns `""` when it cannot read the mark, so the built CLI produced
      perfectly valid, unbranded reports and said nothing.

    So the check is not a list of filenames. It reads the directories the
    *code* points at and asserts each spec names them, which is the property
    that was violated both times.
    """

    # One bundle since T-2571: the CLI is the app under another name.
    SPECS = ("packaging/XBrainAudit.spec",)

    #: Every runtime resource under `ui/design`, as the module that reads it
    #: names it. A new one added to the tree and to no spec fails here.
    def _design_resources(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "ui" / "design"
        for entry in sorted(root.iterdir()):
            if entry.name.startswith("."):
                continue
            yield entry

    def test_every_design_resource_is_named_in_every_spec(self):
        for entry in self._design_resources():
            for spec in self.SPECS:
                with self.subTest(resource=entry.name, spec=spec):
                    self.assertIn(entry.name, _spec_text(spec))

    def test_the_files_the_specs_name_are_the_files_the_code_reads(self):
        """Named in the spec but renamed on disk is the same failure with an
        extra step, so the spec is checked against the modules, not against
        string literals."""
        from ui import theme

        for path in (tokens.token_file(), tokens.OVERLAY_PATH, theme._ICONS):
            with self.subTest(path=getattr(path, "name", path)):
                self.assertIsNotNone(path)
                self.assertTrue(path.exists())

    def test_both_ticks_the_window_draws_are_on_disk(self):
        """QSS `url()` is a path, and a missing one draws nothing at all -
        an empty checkbox that is in fact ticked."""
        from ui import theme

        for name in ("check-on-light.svg", "check-on-dark.svg"):
            with self.subTest(icon=name):
                self.assertTrue((theme._ICONS / name).is_file())
        for sheet in ("light", "dark"):
            palette = tokens.palettes()[sheet]
            with self.subTest(theme=sheet):
                self.assertTrue(Path(theme._check_mark(palette)).is_file())


@unittest.skipIf(QApplication is None, "PySide6 not available")
class TheWindowDrawsItsOwnControls(unittest.TestCase):
    """Left to the platform style, an indicator is drawn from the *system*
    palette rather than from this design's - which on the dark sheet gave a
    ticked checkbox and an empty one as nearly the same grey square. The
    radio button was fixed for this reason; the checkbox had the same defect
    and was not."""

    def test_a_ticked_box_and_an_empty_one_are_not_the_same_square(self):
        for sheet in ("light", "dark"):
            palette = tokens.palettes()[sheet]
            qss = theme.build_qss(palette)
            with self.subTest(theme=sheet):
                self.assertIn("QCheckBox::indicator:checked", qss)
                block = qss.split("QCheckBox::indicator:checked {")[1].split("}")[0]
                self.assertIn(theme.qss_color(palette.primary), block)
                self.assertIn("image: url(", block)

    def test_the_tick_inverts_with_the_sheet(self):
        """It is baked into the SVG, because QSS cannot tint an image - so
        the wrong file is an invisible tick, not a differently coloured one."""
        light = theme._check_mark(tokens.palettes()["light"])
        dark = theme._check_mark(tokens.palettes()["dark"])
        self.assertNotEqual(light, dark)
        self.assertIn(tokens.palettes()["light"].on_primary.lower(),
                      Path(light).read_text(encoding="utf-8").lower())

    def test_the_foot_of_the_window_belongs_to_the_window(self):
        """The design draws it as a band inside the surface, not as the
        canvas with a hairline - which read as native chrome under the app."""
        for sheet in ("light", "dark"):
            palette = tokens.palettes()[sheet]
            block = theme.build_qss(palette).split("QStatusBar {")[1].split("}")[0]
            with self.subTest(theme=sheet):
                self.assertIn(theme.qss_color(palette.bg_hover), block)
                self.assertIn("border: none", block)
