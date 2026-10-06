"""The authored family gate protects every digit and native registration."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.b765.u1_fonts import DEFAULT_FAMILIES, selected_blocks, validate_family


class SourcedFontGateTest(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "data/nfl2k5_teams_2026/LAC.json").read_text())
        self.block = copy.deepcopy(self.spec["kits"]["home"]["digits"])

    def test_full_family_and_helmet_use_same_shapes(self):
        for kit in self.spec["kits"].values():
            validate_family(kit["digits"])
            validate_family(kit["helmet_digits"])
            self.assertEqual(kit["digits"]["glyph_shapes"], kit["helmet_digits"]["glyph_shapes"])
        self.assertTrue(self.block["glyph_shapes"]["0"]["holes"])
        self.assertEqual(len(self.block["glyph_shapes"]["8"]["holes"]), 2)

    def test_incomplete_family_refused(self):
        del self.block["glyph_shapes"]["7"]
        with self.assertRaisesRegex(ValueError, "exactly digits"):
            validate_family(self.block)

    def test_bounds_and_nonfinite_coordinates_refused(self):
        for point in ([float("nan"), 0], [-1, 0], [0, 1001]):
            block = copy.deepcopy(self.block)
            block["glyph_shapes"]["3"]["contours"][0][0] = point
            with self.assertRaises(ValueError):
                validate_family(block)

    def test_registration_drift_and_conflicting_font_refused(self):
        self.block["registration"] = "retail"
        with self.assertRaisesRegex(ValueError, "as_authored"):
            validate_family(self.block)
        self.block["registration"] = "as_authored"
        self.block["font"] = "another-font.ttf"
        with self.assertRaisesRegex(ValueError, "no font"):
            validate_family(self.block)

    def test_jersey_only_does_not_validate_or_select_helmet_donor(self):
        kit = dict(digits=self.block, helmet_digits={"glyph_donor": "unchanged"})
        self.assertEqual(selected_blocks(kit, ("jersey_digit",)),
                         [("digits", "digit_jersey", "jersey_digit")])
        with self.assertRaisesRegex(ValueError, "exactly digits"):
            selected_blocks(kit, DEFAULT_FAMILIES)

    def test_empty_duplicate_and_unowned_family_selection_refused(self):
        kit = self.spec["kits"]["home"]
        for families in ((), ("jersey_digit", "jersey_digit"), ("unknown",), ("jersey_digit", "nameplate")):
            with self.assertRaisesRegex(ValueError, "select unique"):
                selected_blocks(kit, families)

    def test_default_still_selects_both_validated_families(self):
        self.assertEqual(selected_blocks(self.spec["kits"]["home"], DEFAULT_FAMILIES),
                         [("digits", "digit_jersey", "jersey_digit"),
                          ("helmet_digits", "digit_helmet", "helmet_digit")])

    def test_blank_arm_preserved_and_visible_arm_validated(self):
        kit = dict(digits=self.block, arm_digits="none")
        families = ("jersey_digit", "arm_digit")
        self.assertEqual(selected_blocks(kit, families), [("digits", "digit_jersey", "jersey_digit")])
        kit["arm_digits"] = copy.deepcopy(self.block)
        self.assertEqual(selected_blocks(kit, families)[1], ("arm_digits", "digit_arm", "arm_digit"))
        del kit["arm_digits"]["glyph_shapes"]["8"]
        with self.assertRaisesRegex(ValueError, "exactly digits"):
            selected_blocks(kit, families)


if __name__ == "__main__":
    unittest.main()
