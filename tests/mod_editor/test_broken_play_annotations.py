"""Broken-play annotations for Ace/Dime/Bear — discovery only, no byte writes."""

from __future__ import annotations

import unittest

from mod_editor.gui.playbooks_panel_qt import (
    broken_play_annotations,
    format_play_name_with_warnings,
)


class BrokenPlayAnnotationTests(unittest.TestCase):
    def test_ace_is_flagged(self) -> None:
        notes = broken_play_annotations("Ace Twins Right")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].code, "Ace package")
        self.assertIn("G2", notes[0].detail)

    def test_dime_is_flagged(self) -> None:
        notes = broken_play_annotations("Dime Cover 2")
        self.assertEqual(notes[0].code, "Dime package")
        self.assertIn("G1", notes[0].detail)

    def test_bear_is_flagged(self) -> None:
        notes = broken_play_annotations("Bear Under")
        self.assertEqual(notes[0].code, "Bear front")
        self.assertIn("G13", notes[0].detail)

    def test_unrelated_name_is_quiet(self) -> None:
        self.assertEqual(broken_play_annotations("I Form Pro Right"), ())

    def test_format_appends_warning_tag(self) -> None:
        text = format_play_name_with_warnings("Slant", "Ace")
        self.assertIn("Slant", text)
        self.assertIn("⚠", text)
        self.assertIn("Ace", text)

    def test_formation_and_play_both_scanned(self) -> None:
        notes = broken_play_annotations("Quick Out", "Nickel Dime")
        codes = {note.code for note in notes}
        self.assertIn("Dime package", codes)


if __name__ == "__main__":
    unittest.main()
