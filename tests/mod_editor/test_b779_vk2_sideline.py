"""b779-vk2: the full sideline-atlas audit (every 2026 kit on the v0.7 disc) and the measured sideline rows.

Model tests on synthetic atlases: the pinned rows, the wrong-team rows, the measured repair (mode colour, torso part,
donors, a colour swap, fill and inpaint boxes), convergence on a re-run, and the row validation. These tests do not
read a disc; the real 61 spans were compiled offline against the released v0.7 image (job report)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
import unittest

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77"), str(REPO / "tools/b765")]

from mod_editor.core import nfl2k5_kit_fixes_2026 as kit  # noqa: E402

# the shipped 2026 alternates that wore another team's (the retail Arizona slot's) sleeve, helmet or torso art
WRONG_TEAM = ("07A9", "18A7", "19A7", "21A13", "25A7", "27A6", "28A7", "29A9")


def atlas(pants=(200, 0, 50), torso=(80, 40, 130), sleeve=(80, 40, 130), helmet=(80, 40, 130)):
    image = np.zeros((128, 256, 4), np.uint8)
    image[..., 3] = 255
    image[..., :3] = torso
    image[0:90, 0:128, :3] = pants
    image[0:90, 46:66, :3] = (235, 224, 201)          # the pants stripe
    image[100:128, 190:256, :3] = sleeve
    image[90:128, 37:128, :3] = helmet
    image[100:128, 190:195, :3] = 255                  # the sleeve island's white border
    return image


def mode(image, part):
    return kit._sideline_part_colour(image, part)


class AuditRowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = {row["selector"]: row for row in kit.sideline()["kits"]}

    def test_the_list_validates_and_keeps_vk1_rows(self) -> None:
        kit._sideline_rows()                               # every row passes the validator
        self.assertEqual(len(self.rows), 63)
        for selector in ("03A9", "15A6", "15H6", "24A10", "22H5", "22A5"):
            self.assertIn(selector, self.rows)
        self.assertEqual(self.rows["15A6"]["parts"], ["pants", "sleeve", "helmet"])

    def test_every_wrong_team_kit_takes_its_parts_from_the_same_team(self) -> None:
        for selector in WRONG_TEAM:
            row = self.rows[selector]
            self.assertIn("field", row, selector)
            donors = [row.get("donor")] + list((row.get("donors") or {}).values())
            donors = [d for d in donors if d]
            self.assertTrue(donors, selector)
            for donor in donors:
                self.assertEqual(donor[:2], selector[:2], selector + " takes art from another team")
                self.assertNotEqual(donor, selector)

    def test_measured_rows_name_a_field_colour_for_every_part(self) -> None:
        for selector, row in self.rows.items():
            if "field" in row:
                self.assertEqual(sorted(row["field"]), sorted(row["parts"]), selector)

    def test_primary_rows_are_measured(self) -> None:
        for selector, row in self.rows.items():
            if int(selector[3:]) == 0:
                self.assertIn("field", row, selector)


class MeasuredRepairTests(unittest.TestCase):
    def test_the_mode_colour_moves_to_the_field_colour_and_the_stripe_stays(self) -> None:
        alt = atlas(pants=(200, 0, 50))
        row = {"selector": "99A1", "parts": ["pants"], "field": {"pants": [51, 35, 107]}}
        out, changed = kit.sideline_measured_repair(alt, {}, {"pants": np.array([51, 35, 107])}, row)
        self.assertGreater(changed["pants"], 5000)
        self.assertLess(int(np.abs(mode(out, "pants") - [51, 35, 107]).max()), 8)
        self.assertEqual(tuple(out[10, 56, :3]), (235, 224, 201))
        self.assertTrue(np.array_equal(out[:, 128:], alt[:, 128:]))   # torso, sleeve untouched

    def test_a_torso_donor_replaces_another_teams_torso(self) -> None:
        alt = atlas(torso=(240, 240, 240))
        donor = atlas(torso=(0, 29, 75))
        field = {"torso": np.array([0, 29, 75])}
        row = {"selector": "99A1", "parts": ["torso"], "field": {"torso": [0, 29, 75]}}
        out, changed = kit.sideline_measured_repair(alt, {"torso": donor}, field, row)
        self.assertGreater(changed["torso"], 10000)
        self.assertLess(int(np.abs(mode(out, "torso") - [0, 29, 75]).max()), 8)
        self.assertTrue(np.array_equal(out[0:90, 0:128], alt[0:90, 0:128]))

    def test_a_colour_swap_runs_once(self) -> None:
        # the Bengals' retail sleeve: black fabric with orange stripes; the field sleeve is orange with black stripes
        alt = atlas(sleeve=(36, 38, 43))
        alt[110:114, 196:256, :3] = (246, 79, 21)
        rules = [{"from": [36, 38, 43], "tolerance": 0.15}, {"from": [246, 79, 21], "to": [10, 10, 10]}]
        row = {"selector": "99H6", "parts": ["sleeve"], "field": {"sleeve": [250, 80, 20]}, "recolour": {"sleeve": rules}}
        field = {"sleeve": np.array([250, 80, 20])}
        once, changed = kit.sideline_measured_repair(alt, {}, field, row)
        self.assertGreater(changed["sleeve"], 100)
        self.assertLess(int(np.abs(once[120, 220, :3].astype(int) - [250, 80, 20]).max()), 12)
        self.assertLess(int(once[112, 220, :3].max()), 30)                   # the stripe is now black
        again, changed = kit.sideline_measured_repair(once, {}, field, row)
        self.assertFalse(any(changed.values()))
        self.assertTrue(np.array_equal(once, again))

    def test_a_fill_box_removes_a_logo_the_field_helmet_does_not_have(self) -> None:
        alt = atlas(helmet=(106, 73, 45))
        alt[107:123, 99:124, :3] = (237, 236, 237)                           # a G logo
        row = {"selector": "99H6", "parts": ["helmet"], "field": {"helmet": [107, 74, 46]},
               "fill": {"helmet": [[99, 107, 124, 123]]}}
        out, changed = kit.sideline_measured_repair(alt, {}, {"helmet": np.array([107, 74, 46])}, row)
        self.assertGreater(changed["helmet"], 300)
        self.assertEqual(tuple(out[115, 110, :3]), (106, 73, 45))

    def test_an_inpaint_box_continues_the_fabric_over_a_retail_panel(self) -> None:
        alt = atlas(torso=(210, 215, 223))
        alt[20:60, 150:162, :3] = (36, 38, 43)                               # a black side panel
        row = {"selector": "99A0", "parts": ["torso"], "field": {"torso": [255, 255, 255]},
               "inpaint": {"torso": [{"box": [147, 15, 166, 62], "keep": [210, 215, 223]}]}}
        out, changed = kit.sideline_measured_repair(alt, {}, {"torso": np.array([255, 255, 255])}, row)
        self.assertGreater(changed["torso"], 400)
        self.assertLess(int(np.abs(out[40, 156, :3].astype(int) - [210, 215, 223]).max()), 6)
        self.assertTrue(np.array_equal(out[70:100, 128:256], alt[70:100, 128:256]))

    def test_an_already_matching_part_is_left_alone(self) -> None:
        alt = atlas(pants=(52, 36, 106))
        row = {"selector": "99A1", "parts": ["pants"], "field": {"pants": [51, 35, 107]}}
        out, changed = kit.sideline_measured_repair(alt, {}, {"pants": np.array([51, 35, 107])}, row)
        self.assertEqual(changed["pants"], 0)
        self.assertTrue(np.array_equal(out, alt))

    def test_the_legacy_path_converges(self) -> None:
        alt = atlas(pants=(200, 0, 50))
        once, _ = kit.sideline_repair(alt, alt, {"pants": np.array([51, 35, 107])}, ["pants"])
        again, changed = kit.sideline_repair(once, once, {"pants": np.array([51, 35, 107])}, ["pants"])
        self.assertFalse(any(changed.values()))


class RowValidationTests(unittest.TestCase):
    def check(self, row):
        kit._sideline_rows({"schema": kit.SIDELINE_SCHEMA, "kits": [row]})

    def test_valid_measured_row(self) -> None:
        self.check({"selector": "06A0", "parts": ["torso", "sleeve"], "field": {"torso": [255, 255, 255], "sleeve": [255, 255, 255]},
                    "inpaint": {"torso": [{"box": [147, 15, 166, 62], "keep": [210, 215, 223]}]},
                    "recolour": {"sleeve": [{"from": [36, 38, 43]}]}})

    def test_refusals(self) -> None:
        base = {"selector": "06A0", "parts": ["sleeve"], "field": {"sleeve": [255, 255, 255]}}
        bad = [
            {"field": {"pants": [1, 2, 3]}},                                       # field part is not repaired
            {"field": {"sleeve": [1, 2]}},                                         # not a colour
            {"donors": {"helmet": "06H0"}},                                        # donor for an unlisted part
            {"donors": {"sleeve": "6H0"}},                                         # bad selector
            {"recolour": {"sleeve": [{"from": [1, 2, 3], "box": [0, 0, 300, 10]}]}},   # box outside the part
            {"fill": {"sleeve": [[10, 10, 20, 20]]}},                              # fill box outside the part
            {"inpaint": {"sleeve": [{"box": [195, 100, 200, 110]}]}},              # no fabric colour
            {"always": ["sleeve"]},                                                # always without recolour rules
        ]
        for extra in bad:
            row = copy.deepcopy(base)
            row.update(extra)
            with self.assertRaises(ValueError, msg=str(extra)):
                self.check(row)
        with self.assertRaises(ValueError):                                      # a primary needs field colours
            self.check({"selector": "06A0", "parts": ["pants"], "reason": "x"})
        with self.assertRaises(ValueError):                                      # torso needs field colours
            self.check({"selector": "06A5", "parts": ["torso"], "donor": "06H5"})


def texture(colour, size=(256, 512), stripe=None):
    image = np.zeros(size + (4,), np.uint8)
    image[..., 3] = 255
    image[..., :3] = colour
    if stripe is not None:
        x0, x1, c = stripe
        image[:, x0:x1, :3] = c
    return image


class QualityPassTests(unittest.TestCase):
    """The coordinator's quality pass: rough recolours are rebuilt from the kit's own field textures."""

    def setUp(self) -> None:
        self.rows = {row["selector"]: row for row in kit.sideline()["kits"]}

    def test_every_pants_island_is_laid_from_its_field_pants(self) -> None:
        for selector, row in self.rows.items():
            if "pants" in row["parts"] and "field" in row:
                self.assertIn("pants", row.get("compose", {}), selector)

    def test_the_bumblebee_torso_and_the_shells_are_rows(self) -> None:
        for selector in ("22H5", "22A5"):
            self.assertIn("torso", self.rows[selector]["compose"])
        for selector in ("05A4", "05H4", "19H2", "19A2", "25A7", "25H7", "27A6"):
            self.assertIn("decal", self.rows[selector]["shell"]["helmet"], selector)

    def test_compose_lays_the_field_crop_and_keeps_the_island_folds(self) -> None:
        alt = atlas(pants=(14, 75, 203))
        alt[30:40, 0:128, :3] = (10, 60, 160)                                    # a darker fold
        pants = texture((255, 255, 255), stripe=(357, 382, (200, 210, 230)))
        row = {"selector": "99A9", "parts": ["pants"], "field": {"pants": [255, 255, 255]}, "compose": {"pants": {}}}
        out, changed = kit.sideline_measured_repair(alt, {}, {"pants": np.array([255, 255, 255])}, row,
                                                    {"pants": pants})
        self.assertGreater(changed["pants"], 8000)
        self.assertGreater(int(out[60, 20, :3].min()), 225)                       # white fabric
        stripe = int(round((357 + 12 - 255) * 128 / 257))
        self.assertLess(int(out[60, stripe, 0]), 225)                            # the field stripe is there
        self.assertLess(int(out[35, 20, 0]), int(out[60, 20, 0]))                  # the fold still shades it
        again, changed = kit.sideline_measured_repair(out, {}, {"pants": np.array([255, 255, 255])}, row,
                                                      {"pants": pants})
        self.assertFalse(any(changed.values()))                                  # idempotent
        self.assertTrue(np.array_equal(out, again))

    def test_shell_repaints_the_helmet_and_places_the_field_logo(self) -> None:
        alt = atlas(helmet=(9, 17, 32))
        alt[109:120, 101:119, :3] = (181, 119, 59)                               # the retail orange C
        helmet = texture((209, 79, 24), size=(256, 256))
        helmet[150:190, 48:108, :3] = (13, 26, 50)                               # the field navy C
        row = {"selector": "99A4", "parts": ["helmet"], "field": {"helmet": [209, 79, 24]},
               "shell": {"helmet": {"decal": {"box": [48, 150, 108, 190], "at": [110, 113, 14]}}}}
        out, changed = kit.sideline_measured_repair(alt, {}, {"helmet": np.array([209, 79, 24])}, row,
                                                    {"helmet": helmet})
        self.assertGreater(changed["helmet"], 2000)
        self.assertLess(int(np.abs(out[100, 60, :3].astype(int) - [209, 79, 24]).max()), 30)   # orange shell
        self.assertLess(int(out[113, 110, :3].max()), 60)                                     # navy logo
        again, changed = kit.sideline_measured_repair(out, {}, {"helmet": np.array([209, 79, 24])}, row,
                                                      {"helmet": helmet})
        self.assertFalse(any(changed.values()))

    def test_a_shell_keeps_only_the_kept_marks_own_texels(self) -> None:
        alt = atlas(helmet=(253, 253, 253))
        alt[95:105, 40:90, :3] = (64, 26, 113)                                   # a retail blob
        alt[106:122, 100:120, :3] = (200, 160, 40)                               # the kept mark
        row = {"selector": "99A5", "parts": ["helmet"], "field": {"helmet": [239, 239, 237]},
               "shell": {"helmet": {"keep": [[98, 103, 126, 128]]}}}
        out, _ = kit.sideline_measured_repair(alt, {}, {"helmet": np.array([239, 239, 237])}, row,
                                              {"helmet": texture((239, 239, 237), size=(256, 256))})
        self.assertGreater(int(out[100, 60, :3].min()), 200)                     # the blob is gone
        self.assertEqual(tuple(out[112, 110, :3]), (200, 160, 40))               # the mark stays

    def test_compose_rows_validate(self) -> None:
        kit._sideline_rows({"schema": kit.SIDELINE_SCHEMA, "kits": [
            {"selector": "22H5", "parts": ["torso"], "field": {"torso": [245, 180, 24]},
             "compose": {"torso": {"keep": [[128, 0, 144, 48]]}}}]})
        for bad in ({"compose": {"helmet": {}}}, {"shell": {"torso": {}}},
                    {"compose": {"torso": {"keep": [[0, 0, 10, 10]]}}}):
            row = {"selector": "22H5", "parts": ["torso", "helmet"],
                   "field": {"torso": [245, 180, 24], "helmet": [0, 0, 0]}}
            row.update(bad)
            with self.assertRaises(ValueError, msg=str(bad)):
                kit._sideline_rows({"schema": kit.SIDELINE_SCHEMA, "kits": [row]})


if __name__ == "__main__":
    unittest.main()
