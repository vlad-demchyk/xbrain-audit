"""An SVG sprite outside the canvas is nobody's web part.

On a live intranet, Microsoft's file-icon definitions
(`<svg class="ColoredFolderDefs_<hash>"><defs>...</defs></svg>`) became a
custom part, "SPFx outside the canvas (ColoredFolderDefs)", on every page
that showed a document. Synthetic markup, the shape of it only.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from audit import sharepoint_zones as zones

FIXTURE = Path(__file__).parent / "fixtures" / "sharepoint" / "modern_page.html"
POPUP = '<div class="contosoPopup_9a8b7c6d">'


def _names(extra: str) -> list:
    markup = FIXTURE.read_text(encoding="utf-8").replace(POPUP, extra + POPUP, 1)
    _document, zone_map = zones.map_page(markup)
    return [zone.name for zone in zone_map.zones]


class DefinitionsAreNotAPart(unittest.TestCase):

    def test_an_svg_of_definitions_is_skipped(self):
        names = _names('<svg class="ColoredFolderDefs_2bdacb26" style="position:absolute">'
                       '<defs><linearGradient id="g"><stop offset="0"/></linearGradient>'
                       '<path id="p" d="M0 0h1v1z"/></defs></svg>')
        self.assertFalse(any("ColoredFolderDefs" in name for name in names))

    def test_a_wrapper_holding_only_a_sprite_is_skipped(self):
        names = _names('<div class="iconSprite_0c0ffee1" aria-hidden="true">'
                       '<svg><symbol id="s"><circle r="1"/></symbol></svg></div>')
        self.assertFalse(any("iconSprite" in name for name in names))

    def test_an_svg_that_draws_is_still_a_part(self):
        names = _names('<svg class="drawnIcon_0c0ffee1"><defs><path id="p" d="M0 0"/></defs>'
                       '<use href="#p"/></svg>')
        self.assertIn("SPFx outside the canvas (drawnIcon)", names)

    def test_the_popup_with_content_is_still_a_part(self):
        self.assertIn("SPFx outside the canvas (contosoPopup)", _names(""))


if __name__ == "__main__":
    unittest.main()
