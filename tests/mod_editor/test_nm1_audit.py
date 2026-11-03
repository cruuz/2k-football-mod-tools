"""The diagnostic must not mistake whole-word scoreboard tiles for an alphabet."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.b77.nm1_audit import can_spell, font_report
from mod_editor.core.nfl2k5_scorebug_sprite import load_layout


class TileCoverageTests(unittest.TestCase):
    def test_whole_tiles_cannot_be_split_implicitly(self):
        self.assertTrue(can_spell("GOAL", {"GOAL"}))
        self.assertFalse(can_spell("GALA", {"GOAL"}))

    def test_overlapping_tokens_require_non_greedy_coverage(self):
        self.assertTrue(can_spell("ABC", {"AB", "A", "BC", ""}))
        self.assertFalse(can_spell("ABCD", {"AB", "A", "BC", ""}))

    def test_current_scorebug_is_not_a_name_alphabet(self):
        spec, image = load_layout()
        report = font_report(spec, image)
        self.assertFalse(report["samples"]["WILLIAMS"])
        self.assertTrue(report["samples"]["Inches"])
        self.assertNotIn("T", report["standalone_uppercase"])
        # b780 p2-playcall: the ball-spot team abbreviations brought J and K inside whole-word tiles, so splitting
        # tiles would now miss only Q; no letter stands alone and no sample name can be spelled.
        self.assertEqual(report["standalone_uppercase"], "")
        self.assertIn("Q", report["absent_even_if_text_tiles_split"])
        self.assertFalse(report["samples"]["JONES"])
        self.assertFalse(any(ok for name, ok in report["samples"].items() if name != "Inches"))


if __name__ == "__main__":
    unittest.main()
