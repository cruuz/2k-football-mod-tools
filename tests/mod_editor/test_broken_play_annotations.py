"""Broken-play annotations for Ace/Dime/Bear — discovery only, no byte writes."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


class CommunityLegendContractTests(unittest.TestCase):
    """Teachable G1/G2/G13 legend ships in the playbooks panel (source contract)."""

    def test_legend_and_empty_flagged_copy_exist_in_shipped_panel(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (root / "mod_editor/gui/playbooks_panel_qt.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("community_legend", source)
        self.assertIn("G1 ILB→OLB", source)
        self.assertIn("G2 TE→WR", source)
        self.assertIn("G13", source)
        self.assertIn("0 matching books under ⚠ Community-flagged", source)
        self.assertIn("APF_GAMEPLAY_BUG_MAP.md", source)
        self.assertIn("G1 tip: set Link/Package donor", source)
        self.assertIn("Nickel→Dime", source)


if __name__ == "__main__":
    unittest.main()
