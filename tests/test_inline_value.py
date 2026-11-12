"""The inline selector: a control drawn as part of a sentence.

The design's top row reads as prose - "аналізувати Сайт · глибина 2" - where
the emphasised words are the controls. A restyled `QComboBox` cannot be that
(it insists on a frame and on a size hint built from its longest item), so
`InlineValue` is its own widget, and this file holds it to the behaviour a
combo box would have given for free.

The keyboard cases are the point. XBrain Audit reports controls that cannot be
reached without a mouse as an accessibility finding on other people's pages,
so a selector of its own that only opened on click would be the same defect
shipped inwards.

Headless: Qt runs on the offscreen platform. `isVisible()` is False for every
widget that was never shown, so visibility is asserted with `isHidden()`,
which reflects the explicit hide the widget itself performs.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    from ui import theme
    from ui.widgets import InlineValue, hairline
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


def press(widget, key) -> None:
    widget.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, key, Qt.NoModifier))


@unittest.skipIf(QApplication is None, "PySide6 not available")
class Inline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def selector(self, label="глибина", items=(("1", 1), ("2", 2), ("3", 3)),
                 index=1):
        widget = InlineValue(label)
        widget.set_items(items, index=index)
        # Held on the test case: a widget only referenced by the expression
        # under test is collected before the assertion runs, and Qt deletes
        # its children with it - which surfaces as "C++ object already
        # deleted" on the child label rather than as anything to do with the
        # behaviour being checked.
        self._alive = getattr(self, "_alive", [])
        self._alive.append(widget)
        return widget

    def test_setting_the_items_does_not_announce_a_change(self):
        """Populating a control is not the user picking something. Emitting
        here would run an analysis the moment the window was built."""
        widget = InlineValue("глибина")
        seen = []
        widget.currentIndexChanged.connect(seen.append)
        widget.set_items([("1", 1), ("2", 2)], index=1)
        self.assertEqual(seen, [])
        self.assertEqual(widget.current_data(), 2)

    def test_arrow_keys_step_through_the_choices(self):
        widget = self.selector()
        seen = []
        widget.currentIndexChanged.connect(seen.append)

        press(widget, Qt.Key_Right)
        self.assertEqual(widget.current_data(), 3)
        press(widget, Qt.Key_Left)
        self.assertEqual(widget.current_data(), 2)
        self.assertEqual(seen, [2, 1])

    def test_stepping_stops_at_the_ends(self):
        """No wrap: a value that jumps from the last choice to the first on
        one keypress is how a depth of 3 silently becomes a depth of 1."""
        widget = self.selector(index=0)
        press(widget, Qt.Key_Left)
        self.assertEqual(widget.current_index(), 0)

        widget.set_index(2)
        press(widget, Qt.Key_Right)
        self.assertEqual(widget.current_index(), 2)

    def test_it_takes_keyboard_focus(self):
        self.assertEqual(self.selector().focusPolicy(), Qt.StrongFocus)

    def test_the_value_is_announced_with_its_label(self):
        """A screen reader reading "2" alone says nothing about what is 2."""
        self.assertEqual(self.selector().accessibleName(), "глибина 2")

    def test_a_single_choice_shows_no_caret(self):
        """The caret is the promise that there is something to pick. One
        item is not a choice, so promising one would be a lie."""
        widget = InlineValue("режим")
        widget.set_items(["Сайт"])
        self.assertTrue(widget._caret.isHidden())

    def test_several_choices_show_a_caret(self):
        self.assertFalse(self.selector()._caret.isHidden())

    def test_free_text_is_not_a_selector(self):
        """The scanned URL sits in the same strip but is not a choice, so it
        loses the caret, the focus stop and the pointer cursor with it."""
        widget = InlineValue("")
        widget.set_value_text("xformat.net")
        self.assertTrue(widget._caret.isHidden())
        self.assertEqual(widget.focusPolicy(), Qt.NoFocus)
        self.assertIsNone(widget.current_data())

    def test_an_empty_label_is_not_a_gap_in_the_row(self):
        widget = InlineValue("")
        self.assertTrue(widget._label.isHidden())

    def test_set_index_clamps_rather_than_raising(self):
        """Restored settings outlive the list they indexed into - a saved
        depth of 5 must not crash a build that offers three."""
        widget = self.selector()
        widget.set_index(99)
        self.assertEqual(widget.current_index(), 2)
        widget.set_index(-4)
        self.assertEqual(widget.current_index(), 0)

    def test_the_three_inks_are_three_different_colours(self):
        """Label, value and caret carry the hierarchy. Two of them sharing a
        colour is what turns the row back into a form."""
        palette = theme.current_palette("light")
        self.assertEqual(
            len({palette.text, palette.text_muted, palette.text_subtle}), 3)

    # -- the QComboBox surface the window addresses it through -------------

    def test_it_answers_the_combo_box_calls_the_window_makes(self):
        """`InlineValue` replaces `QComboBox` in the window by keeping the
        names, so every call the code and the tests already make has to land.
        Checked as one list rather than one test each: the point is the
        *surface*, and a gap anywhere in it is the same failure."""
        widget = InlineValue("оцінює")
        self._alive = getattr(self, "_alive", [])
        self._alive.append(widget)

        widget.addItem("локальний двигун", "local")
        widget.addItem("модель", "model")
        self.assertEqual(widget.count(), 2)
        self.assertEqual(widget.currentIndex(), 0)
        self.assertEqual(widget.currentData(), "local")
        self.assertEqual(widget.currentText(), "локальний двигун")
        self.assertEqual(widget.itemData(1), "model")
        self.assertEqual(widget.itemText(1), "модель")
        self.assertEqual(widget.findData("model"), 1)

        widget.setCurrentIndex(1)
        self.assertEqual(widget.currentData(), "model")

        widget.clear()
        self.assertEqual(widget.count(), 0)
        self.assertEqual(widget.currentIndex(), -1)

    def test_find_data_reports_a_miss_the_way_qt_does(self):
        """Call sites branch on -1. Returning None or raising would take a
        path none of them were written for."""
        self.assertEqual(self.selector().findData("nope"), -1)

    def test_the_first_item_becomes_the_value_without_announcing_it(self):
        """`_populate_providers` clears and refills on every provider change;
        emitting on the refill would re-enter the handler that caused it."""
        widget = InlineValue("оцінює")
        self._alive = getattr(self, "_alive", [])
        self._alive.append(widget)
        seen = []
        widget.currentIndexChanged.connect(seen.append)
        widget.addItem("перший", "a")
        self.assertEqual(widget.currentData(), "a")
        self.assertEqual(seen, [])

    def test_setting_the_index_it_already_has_announces_nothing(self):
        """Qt stays quiet on a no-op change, and the window relies on it:
        `_sync_choices_to_state` writes the index back on every state pass."""
        widget = self.selector()
        seen = []
        widget.currentIndexChanged.connect(seen.append)
        widget.setCurrentIndex(widget.currentIndex())
        self.assertEqual(seen, [])

    def test_a_second_item_brings_the_caret_back(self):
        """One choice draws no caret; adding a second makes it a choice."""
        widget = InlineValue("режим")
        self._alive = getattr(self, "_alive", [])
        self._alive.append(widget)
        widget.addItem("Сайт", "web")
        self.assertTrue(widget._caret.isHidden())
        widget.addItem("Репозиторій", "repo")
        self.assertFalse(widget._caret.isHidden())

    def test_the_ignored_sizing_calls_do_not_explode(self):
        """The window calls both on every selector it builds. They mean
        nothing here, but they must not stop the build."""
        widget = self.selector()
        widget.setSizeAdjustPolicy(None)
        widget.setMinimumContentsLength(12)

    def test_the_hairline_is_a_hairline(self):
        line = hairline()
        self.assertEqual(line.width(), 1)
        self.assertEqual(line.property("class"), theme.CLASS_HAIRLINE)


if __name__ == "__main__":
    unittest.main()
