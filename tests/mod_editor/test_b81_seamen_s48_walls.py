"""b81-seamen: ESPN Stadium (s48) with plain white field walls.

The owner (2026-11-25, the classic Seamen's home venue): "also, it uses the espn stadium, make the walls all white".

The venue-art pass (nfl2k5_modern_venues_2026) owns s48's stadium scene (the shared-art sponsor boards) and refuses a
bundle whose stadium scene is not retail, so the walls are two more shared-art items of a new kind, "wall" (s48 only):
the padded wall ``espnwall01`` (blue band, stripes and the ESPN logo, khaki sides) and the kick plate of
``wall_fance01`` become authored plain white (tools/nfl2k5_s48_white_walls.py, no retail pixel), and the pass gives
each of the nine time-of-day and weather bundles the retail dry-day to variant look plus, for walls, the snow drift.

Offline evidence: the venue pass's own bundle worker composes the nine retail s48 bundles. Not a played game.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests")]
from mod_editor.core import nfl2k5_modern_venues_2026 as mv  # noqa: E402
from mod_editor.core import nfl2k5_stadium_shared_art as shared  # noqa: E402

from tests.nfl2k5_supersim_draft_fixture import XBE  # noqa: E402  (the private retail extraction, as the other suites)
RETAIL = XBE.parent


class CatalogTests(unittest.TestCase):
    def test_the_two_wall_items_are_authored_white_and_only_s48_may_carry_walls(self):
        walls = [i for i in shared.items("s48") if i["kind"] == "wall"]
        self.assertEqual({i["key"]: i["rects"] for i in walls},
                         {"espnwall01": [[0, 7, 256, 128], [0, 135, 256, 256]], "wall_fance01": [[0, 100, 128, 128]]})
        for item in walls:
            self.assertEqual((item["scene"], item["layer"], item.get("class")), ("stadium", "full", "wall"))
            rgba = item["rgba"].astype(int)
            mask = np.zeros(rgba.shape[:2], bool)
            for x0, y0, x1, y1 in item["rects"]:
                mask[y0:y1, x0:x1] = True
            self.assertFalse(rgba[~mask].any())                       # transparent outside: the caps stay retail
            self.assertTrue((rgba[mask][:, 3] == 255).all())
            inside = rgba[mask][:, :3]
            self.assertLessEqual(int((inside.max(1) - inside.min(1)).max()), 6)   # no colour, only shading
            self.assertGreater(float(np.median(inside)), 225)                   # white
        self.assertEqual(shared.PLAIN_WALL_VENUES, frozenset({"s48"}))

    def test_the_art_is_what_the_tool_draws(self):
        spec = importlib.util.spec_from_file_location("walls", ROOT / "tools/nfl2k5_s48_white_walls.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual(tool.main(["--check"]), 0)


@unittest.skipUnless((RETAIL / "vc_53450030/0").is_file(), "the private retail extraction is absent")
class NineBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_roster_records as rr
        from mod_editor.core import nfl2k5_espn25_more_moments as mm
        names = mv.bundle_names("s48")
        with rr._outer_image()(RETAIL) as archive:
            by_id = {x.name_id: x for x in archive.entries}
            cls.retail = {n: archive.read(by_id[mm.name_id(n)].virtual_offset, by_id[mm.name_id(n)].size) for n in names}
        plan = mv.plan_venue("s48", None, cls.retail, {})
        base = plan.pop("base")
        cls.after = {}
        for name in names:
            _name, after, _edits = mv._compile_job((name, cls.retail[name], None, plan, base, 0, None))
            cls.after[name] = after

    @staticmethod
    def texture(bundle, key):
        rec, decoded = mv.decode_scenes(bundle)["stadium"]
        index = mv.find_stadium_texture(rec, key)
        return mv.read_texture(decoded, rec, mv.p8_rows(rec)[index]).astype(int)

    def test_every_bundle_has_white_walls_and_keeps_its_caps(self):
        for name in mv.bundle_names("s48"):
            with self.subTest(bundle=name):
                wall, before = self.texture(self.after[name], "espnwall01"), self.texture(self.retail[name], "espnwall01")
                pad = np.concatenate([wall[12:120].reshape(-1, 4), wall[140:248].reshape(-1, 4)])[:, :3]
                was = np.concatenate([before[12:120].reshape(-1, 4), before[140:248].reshape(-1, 4)])[:, :3]
                self.assertGreater(float((was.max(1) - was.min(1)).mean()), 40)     # retail: blue and red
                self.assertLess(float((pad.max(1) - pad.min(1)).mean()), 12)        # now: no hue
                self.assertGreater(float(pad.mean()), float(was.mean()) + 60)        # and far lighter
                cap = (slice(0, 6), slice(None))
                self.assertLessEqual(int(np.abs(wall[cap][..., :3] - before[cap][..., :3]).max()), 24)
                plate = self.texture(self.after[name], "wall_fance01")[104:126, :, :3]
                self.assertLess(float((plate.max(2) - plate.min(2)).mean()), 12)

    def test_each_bundle_follows_its_own_retail_variant(self):
        """The pass fits each bundle's wall from the retail dry-day to that bundle's pair. s48's nine bundles carry the
        same retail espnwall01 and wall_fance01 (no time-of-day or weather variant of these two textures; lighting is
        not baked into them), so all nine get the dry-day white wall."""
        day_retail = self.texture(self.retail["s48dd.iff"], "espnwall01")
        day_after = self.texture(self.after["s48dd.iff"], "espnwall01")
        for name in mv.bundle_names("s48"):
            with self.subTest(bundle=name):
                self.assertTrue(np.array_equal(self.texture(self.retail[name], "espnwall01"), day_retail))
                self.assertLessEqual(int(np.abs(self.texture(self.after[name], "espnwall01") - day_after).max()), 8)

if __name__ == "__main__":
    unittest.main()
