"""b780-b12 (D14): the sideline-atlas flaws left after b779-vk2, staged for Noah's review.

Model tests on synthetic atlases (no disc): the D14 rows, the fold sources (a same-team plain light retail island
lights a compose; an absent, panelled or dark source falls back to the island's own folds and says so), the flat
recolour rule for a narrow collar band, and the row validation. The real spans were compiled offline against the
released v0.7 image and compared with v0.8 (job report: 68 written, a re-run writes 0, retail writes 0, the 55 rows
this job did not change are byte for byte the v0.8 spans)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
import unittest
from unittest import mock

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77"), str(REPO / "tools/b765")]

from mod_editor.core import nfl2k5_kit_fixes_2026 as kit  # noqa: E402

KEEP_TORSO = [[128, 0, 144, 48], [128, 95, 256, 100]]


def atlas(torso=(229, 98, 53), sleeve=(80, 40, 130), helmet=(80, 40, 130), pants=(255, 255, 255)):
    image = np.zeros((128, 256, 4), np.uint8)
    image[..., 3] = 255
    image[..., :3] = torso
    image[0:90, 0:128, :3] = pants
    image[100:128, 190:256, :3] = sleeve
    image[90:128, 37:128, :3] = helmet
    return image


def template(top=(240, 242, 248), bottom=(176, 182, 196)):
    """A plain light island whose folds are a smooth top-to-bottom shade (the retail white jersey template)."""
    image = atlas(torso=top)
    for y in range(100):
        t = y / 99.0
        image[y, 128:256, :3] = np.round(np.asarray(top) * (1 - t) + np.asarray(bottom) * t).astype(np.uint8)
    return image


def texture(colour, size=(256, 512)):
    image = np.zeros(size + (4,), np.uint8)
    image[..., 3] = 255
    image[..., :3] = colour
    return image


class D14RowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = {row["selector"]: row for row in kit._sideline_rows()}

    def test_the_list_holds_every_d14_kit(self) -> None:
        self.assertEqual(len(self.rows), 71)
        for selector in ("06H6", "06A6", "11H3", "11A3", "06H0", "27H6", "27A6", "14H0", "14A0", "18H7", "18A7",
                         "00H6", "00A6"):
            self.assertIn(selector, self.rows)
            self.assertIn("b780-b12", self.rows[selector]["reason"], selector)

    def test_fold_sources_are_plain_retail_kits_of_the_same_team(self) -> None:
        sources = {"06H6": "06A3", "06A6": "06A3", "11H3": "11A7", "11A3": "11A7", "00H6": "00A4", "00A6": "00A4",
                   "11H4": "11A7", "11A4": "11A7"}
        for selector, source in sources.items():
            op = self.rows[selector]["compose"]["torso"]
            self.assertEqual(op["folds"], source, selector)
            self.assertEqual(op["keep"], KEEP_TORSO, selector)
            self.assertEqual(source[:2], selector[:2])
        # no other row names a fold source
        named = {s for s, row in self.rows.items() for op in (row.get("compose") or {}).values() if op.get("folds")}
        self.assertEqual(named, set(sources))

    def test_collar_trims(self) -> None:
        # the Bengals home neck holes: filled from the black jersey, clear of the NFL shield (rows 28 and below)
        boxes = [op["box"] for op in self.rows["06H0"]["inpaint"]["torso"]]
        self.assertEqual(boxes, [[166, 0, 196, 28], [240, 0, 256, 22], [142, 0, 145, 44]])
        for op in self.rows["06H0"]["inpaint"]["torso"]:
            self.assertEqual((op["keep"], op["tolerance"]), ([0, 0, 0], 0.1))
        # the pewter Buccaneers: the old torso recolour stays first, the red collar takes the flat pewter
        for selector in ("27H6", "27A6"):
            rules = self.rows[selector]["recolour"]["torso"]
            self.assertEqual(rules[0], {"from": [26, 27, 29], "to": "field", "tolerance": 0.18})
            self.assertEqual([r["box"] for r in rules[1:]], [[166, 0, 196, 31], [238, 0, 256, 24]])
            self.assertTrue(all(r["flat"] for r in rules[1:]))

    def test_older_marks_are_rebuilt_from_the_field_textures(self) -> None:
        for selector in ("14H0", "14A0"):
            self.assertEqual(self.rows[selector]["parts"], ["sleeve"])
            self.assertEqual(self.rows[selector]["compose"], {"sleeve": {}})
        for selector in ("18H7", "18A7"):
            self.assertEqual(self.rows[selector]["shell"]["helmet"]["decal"],
                             {"box": [42, 162, 115, 192], "at": [111, 115, 10]})
        for selector in ("00H6", "00A6"):
            row = self.rows[selector]
            self.assertEqual(row["parts"], ["torso", "sleeve", "helmet"])
            self.assertEqual(row["shell"]["helmet"], {"keep": [[78, 92, 126, 128]]})
            self.assertEqual(row["field"]["torso"], [23, 23, 26])

    def test_the_extras_found_on_the_way(self) -> None:
        # the blotchy Colts 2026 Alternate 3 torso and the Cardinals road sleeve's retail flag, fixed the same way
        for selector in ("11H4", "11A4"):
            self.assertEqual(self.rows[selector]["parts"], ["torso"])
            self.assertIn("b780-b12 extra", self.rows[selector]["reason"])
        self.assertEqual(self.rows["00A0"]["compose"], {"sleeve": {}})
        self.assertIn("b780-b12 extra", self.rows["00A0"]["reason"])


class FoldSourceTests(unittest.TestCase):
    box = kit.SIDELINE_COMPOSE["torso"][0]

    def test_only_a_plain_light_island_is_a_fold_source(self) -> None:
        self.assertTrue(kit._sideline_fold_source(template(), self.box)[0])
        panelled = template()
        panelled[0:100, 150:200, :3] = (20, 20, 24)                         # wide retail side panels
        ok, why = kit._sideline_fold_source(panelled, self.box)
        self.assertFalse(ok)
        self.assertIn("not plain", why)
        ok, why = kit._sideline_fold_source(atlas(torso=(40, 40, 44)), self.box)
        self.assertFalse(ok)
        self.assertIn("not a light island", why)

    def test_a_fold_source_lights_the_compose_without_the_islands_panel_ghosts(self) -> None:
        alt = atlas(torso=(229, 98, 53))
        alt[0:100, 150:156, :3] = (20, 20, 24)                              # a retail panel with dark edges
        alt[0:100, 148:150, :3] = (150, 64, 35)
        alt[0:100, 156:158, :3] = (150, 64, 35)
        jersey = texture((250, 80, 20))
        own = kit._sideline_compose(alt, "torso", jersey, {"keep": KEEP_TORSO})
        lit = kit._sideline_compose(alt, "torso", jersey, {"keep": KEEP_TORSO}, template())
        luma = lambda image: image[..., :3].astype(np.float32) @ kit.SIDELINE_LUMA
        # the template's folds: the top of the torso is lighter than the bottom, the same across the panel columns
        self.assertGreater(float(luma(lit)[10, 200]), float(luma(lit)[90, 200]) + 8)
        self.assertLess(abs(float(luma(lit)[50, 152]) - float(luma(lit)[50, 200])), 3)
        # the island's own folds keep a ghost line at the panel edges
        self.assertGreater(abs(float(luma(own)[50, 147]) - float(luma(own)[50, 200])), 3)

    def test_the_repair_with_a_fold_source_is_idempotent(self) -> None:
        alt = atlas(torso=(58, 61, 64))
        alt[40:60, 160:200, :3] = (14, 75, 203)                            # retail blue blotches
        row = {"selector": "99H3", "parts": ["torso"], "field": {"torso": [58, 61, 64]},
               "compose": {"torso": {"keep": KEEP_TORSO, "folds": "99A7"}}}
        field = {"torso": np.array([58, 61, 64])}
        textures = {"torso": texture((58, 61, 64))}
        folds = {"torso": template()}
        once, changed = kit.sideline_measured_repair(alt, {}, field, row, textures, folds)
        self.assertGreater(changed["torso"], 1000)
        self.assertLess(int(once[50, 180, 2]), 120)                         # the blotch is gone
        again, changed = kit.sideline_measured_repair(once, {}, field, row, textures, folds)
        self.assertFalse(any(changed.values()))
        self.assertTrue(np.array_equal(once, again))

    def test_a_missing_or_unusable_source_falls_back_to_the_islands_own_folds(self) -> None:
        row = {"selector": "99H3", "parts": ["torso"], "field": {"torso": [58, 61, 64]},
               "compose": {"torso": {"keep": KEEP_TORSO, "folds": "99A7"}}}
        chunk = mock.Mock(index=51, kind="TXTR", offset=0, end_offset=4)

        def absent(_selector):
            raise ValueError("99A7 kit package absent or duplicated")

        atlases, notes = kit._sideline_fold_atlases(row, absent)
        self.assertEqual(atlases, {})
        self.assertIn("not readable", notes["torso"])
        atlases, notes = kit._sideline_fold_atlases(row, None)             # no image (the ek1 donor helper)
        self.assertEqual(atlases, {})
        panelled = template()
        panelled[0:100, 150:200, :3] = (20, 20, 24)
        with mock.patch.object(kit, "parse_chunks", return_value=[chunk]), \
                mock.patch.object(kit, "_sideline_rgba", return_value=panelled):
            atlases, notes = kit._sideline_fold_atlases(row, lambda s: (None, b"\0" * 4))
        self.assertEqual(atlases, {})
        self.assertIn("not plain", notes["torso"])
        with mock.patch.object(kit, "parse_chunks", return_value=[chunk]), \
                mock.patch.object(kit, "_sideline_rgba", return_value=template()):
            atlases, notes = kit._sideline_fold_atlases(row, lambda s: (None, b"\0" * 4))
        self.assertIn("torso", atlases)
        self.assertEqual(notes["torso"], "99A7: plain light island")


class FlatRuleTests(unittest.TestCase):
    def band(self):
        image = atlas(torso=(75, 70, 65))
        image[0:30, 170:174, :3] = (160, 27, 48)                            # the collar band
        image[0:30, 169, :3] = (72, 20, 25)                                 # its dark anti-aliased edges
        image[0:30, 174, :3] = (72, 20, 25)
        return image

    def test_a_flat_rule_takes_the_target_without_the_bands_dark_edges(self) -> None:
        region = kit._sideline_rule_region((128, 256), "torso")
        shaded = kit._sideline_apply_rules(self.band(), region,
                                           [([160, 27, 48], [75, 70, 65], 0.35, [166, 0, 196, 31], False)])
        flat = kit._sideline_apply_rules(self.band(), region,
                                         [([160, 27, 48], [75, 70, 65], 0.35, [166, 0, 196, 31], True)])
        self.assertLess(int(shaded[10, 169, 0]), 50)                         # shading kept: a dark outline stays
        for x in (169, 171, 174):
            self.assertLess(int(np.abs(flat[10, x, :3].astype(int) - [75, 70, 65]).max()), 4, x)
        self.assertTrue(np.array_equal(flat[40:, :, :3], self.band()[40:, :, :3]))   # outside the box untouched

    def test_a_flat_collar_row_runs_once(self) -> None:
        alt = self.band()
        alt[0:100, 128:169, :3] = (26, 27, 29)                               # the black retail torso
        alt[0:100, 175:256, :3] = (26, 27, 29)
        alt[30:100, 169:175, :3] = (26, 27, 29)
        row = {"selector": "99H6", "parts": ["torso"], "field": {"torso": [75, 70, 65]},
               "recolour": {"torso": [{"from": [26, 27, 29], "to": "field", "tolerance": 0.18},
                                      {"from": [160, 27, 48], "to": "field", "tolerance": 0.35, "flat": True,
                                       "box": [166, 0, 196, 31]}]}}
        field = {"torso": np.array([75, 70, 65])}
        once, changed = kit.sideline_measured_repair(alt, {}, field, row)
        self.assertGreater(changed["torso"], 10000)
        self.assertLess(int(np.abs(once[10, 171, :3].astype(int) - [75, 70, 65]).max()), 4)
        again, changed = kit.sideline_measured_repair(once, {}, field, row)
        self.assertFalse(any(changed.values()))


class ValidationTests(unittest.TestCase):
    def check(self, row):
        kit._sideline_rows({"schema": kit.SIDELINE_SCHEMA, "kits": [row]})

    def base(self, **extra):
        row = {"selector": "06H6", "parts": ["torso"], "field": {"torso": [250, 80, 20]},
               "compose": {"torso": {"keep": KEEP_TORSO, "folds": "06A3"}}}
        row.update(extra)
        return row

    def test_a_same_team_fold_source_validates(self) -> None:
        self.check(self.base())

    def test_refusals(self) -> None:
        for source in ("11A7", "06H6", "6A3", 7):                          # another team, itself, bad selectors
            row = self.base()
            row["compose"]["torso"]["folds"] = source
            with self.assertRaises(ValueError, msg=str(source)):
                self.check(row)
        row = copy.deepcopy(self.base(parts=["torso", "sleeve"], field={"torso": [1, 2, 3], "sleeve": [1, 2, 3]}))
        row["recolour"] = {"sleeve": [{"from": [1, 2, 3], "flat": "yes"}]}
        with self.assertRaises(ValueError):                                 # flat must be true or false
            self.check(row)


if __name__ == "__main__":
    unittest.main()
