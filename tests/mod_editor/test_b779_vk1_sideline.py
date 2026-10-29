"""b779-vk1: the 2026 alternate sideline-atlas repair (SWeaR 10/27, the Vikings 2026 Alternate 2 on the sideline).

Model tests on synthetic atlases: the pinned list, the pants fabric, the donor sleeve/helmet sides, and that a part
not listed is left alone. The span compiler is exercised against the real 22 spans offline (the shipped v0.7 disc);
these tests do not read a disc."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77"), str(REPO / "tools/b765")]

from mod_editor.core import nfl2k5_kit_fixes_2026 as kit  # noqa: E402


def atlas(pants, sleeve=(80, 40, 130), helmet=(80, 40, 130), torso=(80, 40, 130)):
    image = np.zeros((128, 256, 4), np.uint8)
    image[..., 3] = 255
    image[..., :3] = torso
    image[0:90, 0:128, :3] = pants
    image[0:90, 46:66, :3] = (235, 224, 201)          # the pants stripe
    image[13:23, 69:85, :3] = (183, 155, 85)          # the pants maker mark
    image[100:128, 190:256, :3] = sleeve
    image[120:128, 190:256, :3] = (183, 155, 85)   # the sleeve band
    image[90:128, 37:128, :3] = helmet
    return image


def median(image, box, exclude=()):
    mask = kit._sideline_box(image.shape[:2], box)
    for x0, y0, x1, y1 in exclude:
        mask[y0:y1, x0:x1] = False
    mask &= image[..., 3] > 128
    return np.median(image[..., :3][mask], axis=0).astype(int)


class PinnedListTests(unittest.TestCase):
    def test_the_list_names_2026_alternate_kits_with_known_parts_only(self) -> None:
        document = kit.sideline()
        self.assertEqual(document["schema"], kit.SIDELINE_SCHEMA)
        rows = document["kits"]
        selectors = [row["selector"] for row in rows]
        self.assertEqual(selectors, sorted(set(selectors)))
        self.assertGreaterEqual(len(rows), 22)          # vk1's 22, extended by the b779-vk2 audit
        for row in rows:
            self.assertRegex(row["selector"], r"^\d\d[HA]\d+$")
            self.assertTrue(row["parts"] and all(part in kit.SIDELINE_PARTS for part in row["parts"]))
            if "field" not in row and any(part in ("sleeve", "helmet") for part in row["parts"]):
                self.assertRegex(row["donor"], r"^\d\d[HA]\d+$")

    def test_the_reported_vikings_away_kit_names_all_three_parts(self) -> None:
        rows = {row["selector"]: row for row in kit.sideline()["kits"]}
        self.assertEqual(rows["15A6"]["parts"], ["pants", "sleeve", "helmet"])
        self.assertEqual(rows["15A6"]["donor"], "15H0")
        self.assertEqual(rows["15H6"]["parts"], ["sleeve"])


class SidelineRepairTests(unittest.TestCase):
    def test_the_pants_fabric_takes_the_field_colour_and_the_stripe_stays(self) -> None:
        alt = atlas((200, 0, 50))
        out, changed = kit.sideline_repair(alt, alt, {"pants": np.array([51, 35, 107])}, ["pants"])
        self.assertGreater(changed["pants"], 5000)
        got = median(out, kit.SIDELINE_BOXES["pants"], (kit.SIDELINE_BOXES["pants_stripe"],
                                                       kit.SIDELINE_BOXES["pants_maker"]))
        self.assertLess(int(np.abs(got - np.array([51, 35, 107])).max()), 8)
        self.assertEqual(tuple(out[10, 56, :3]), (235, 224, 201))       # the stripe is not the fabric
        self.assertEqual(tuple(out[20, 200, :3]), (80, 40, 130))        # the torso colour is untouched

    def test_a_part_not_listed_is_left_alone(self) -> None:
        alt = atlas((200, 0, 50), sleeve=(240, 240, 240), helmet=(240, 240, 240))
        out, changed = kit.sideline_repair(alt, alt, {"pants": np.array([51, 35, 107])}, ["pants"])
        self.assertEqual(sorted(changed), ["pants"])
        self.assertTrue(np.array_equal(out[100:128, 190:256], alt[100:128, 190:256]))
        self.assertTrue(np.array_equal(out[90:128, 37:128], alt[90:128, 37:128]))

    def test_the_sleeve_and_helmet_sides_come_from_the_primary_atlas(self) -> None:
        alt = atlas((200, 0, 50), sleeve=(240, 240, 240), helmet=(240, 240, 240))
        donor = atlas((51, 35, 107), sleeve=(80, 40, 130), helmet=(80, 40, 130))
        field = {"sleeve": np.array([51, 35, 107]), "helmet": np.array([36, 27, 88])}
        out, changed = kit.sideline_repair(alt, donor, field, ["sleeve", "helmet"])
        self.assertGreater(changed["sleeve"], 100)
        self.assertGreater(changed["helmet"], 100)
        sleeve = median(out, kit.SIDELINE_SLEEVE_FABRIC)
        self.assertLess(int(np.abs(sleeve - field["sleeve"]).max()), 24)
        shell = kit._sideline_shell(out, kit.SIDELINE_BOXES["helmet"])
        self.assertLess(int(np.abs(shell - field["helmet"]).max()), 24)
        self.assertEqual(tuple(out[125, 240, :3]), (183, 155, 85))      # the donor's sleeve band survives
        self.assertTrue(np.array_equal(out[0:90, 0:128], alt[0:90, 0:128]))   # the unlisted pants are untouched

    def test_the_repair_is_idempotent(self) -> None:
        alt = atlas((200, 0, 50), sleeve=(240, 240, 240), helmet=(240, 240, 240))
        donor = atlas((51, 35, 107), sleeve=(80, 40, 130), helmet=(80, 40, 130))
        field = {"pants": np.array([51, 35, 107]), "sleeve": np.array([51, 35, 107]),
                 "helmet": np.array([36, 27, 88])}
        once, _ = kit.sideline_repair(alt, donor, field, ["pants", "sleeve", "helmet"])
        again, changed = kit.sideline_repair(once, donor, field, ["pants", "sleeve", "helmet"])
        self.assertFalse(any(changed.values()))
        self.assertTrue(np.array_equal(once, again))


if __name__ == "__main__":
    unittest.main()
