"""The 2026 venue art's fixes in st3's board-kit venues (st3, job st7): the table's rect extras for s30 lambert39
(HUNTINGTON BANK FIELD), s17 swall3 (SAINTS / WHO DAT), s17 corp_temp_adbanner01/02 and s37 texscore01/02 (u4's
sponsor policy), on st2's mechanism as it is. Each extra draws only its rects (opaque) and nothing else; the art tool's cells are the table's
rects; with the hydrated archive, the real planner paints every one of them in the dry-day and night bundles."""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_modern_venues_2026 as mv  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"
RECTS = {("s30", "lambert39"): mv.CLE_LAMBERT39_RECTS, ("s17", "swall3"): mv.NO_SWALL3_RECTS,
         ("s17", "corp_temp_adbanner01"): mv.NO_ADBANNER01_RECTS, ("s17", "corp_temp_adbanner02"): mv.NO_ADBANNER02_RECTS,
         ("s37", "texscore01"): mv.HOU_TEXSCORE01_RECTS, ("s37", "texscore02"): mv.HOU_TEXSCORE02_RECTS}


#: st3's own extras by (prefix, key, art): the rects each PNG draws (the sweep's by its SWEEP_RECTS; Paycor's moved
#: residual by its one cell)
OWN = {(p, k, f"extras/{p}_{k}.png"): r for (p, k), r in RECTS.items()}
OWN.update({(p, k, mv._sweep_art(p, k)): r for (p, k), r in mv.SWEEP_RECTS.items()})
OWN[("s06", "signsA1", "extras/s06_signsA1.png")] = mv.CIN_SIGNSA1_RECTS
#: fb2's s06 signsA1.png (c3407046), which the table now carries byte for byte
FB2_S06_SIGNSA1 = "adb5dfa580032fe38ea8ca8db4abe7c192b0524f91204b7afbf13fa2958f19db"


class Extras(unittest.TestCase):
    def test_the_table_carries_each_extra_with_its_rects(self):
        for prefix in ("s30", "s17", "s37"):
            extras = [e for e in mv.venues()[prefix]["extras"] if (prefix, e["key"]) not in mv.SWEEP_RECTS]
            self.assertEqual(mv._table_extras(mv.TABLE_EXTRAS[prefix])[:len(extras)], extras, prefix)
            for extra in extras:
                self.assertEqual((extra["scene"], extra["layer"], extra["from"]), ("stadium", "full", "table"))
                self.assertEqual(extra["rects"], [list(r) for r in RECTS[(prefix, extra["key"])]])
                self.assertNotIn("over", extra)                    # under the team's own art, as st2's WAS and SEA
            self.assertTrue({e["key"] for e in extras} <= {i["key"] for i in mv._extra_items(prefix, set())})

    def test_each_png_draws_only_its_rects(self):
        for (prefix, key, png), rects in OWN.items():
            extra = next(e for e in mv.venues()[prefix]["extras"] if e["key"] == key and e["art"] == png)
            data = (mv.DATA_DIR / extra["art"]).read_bytes()
            self.assertEqual(extra["sha256"], mv.sha(data))
            rgba = mv._rgba(data)
            inside = np.zeros(rgba.shape[:2], dtype=bool)
            for x0, y0, x1, y1 in rects:
                inside[y0:y1, x0:x1] = True
            self.assertTrue((rgba[..., 3][inside] == 255).all(), key)
            self.assertFalse(rgba[..., 3][~inside].any(), key)          # no retail pixel ships

    def test_the_art_tool_cells_are_the_table_rects(self):
        import nfl2k5_modern_venues_2026_st3_art as tool
        self.assertEqual({tool.CLE_HEADER} | set(tool.CLE_CELLS["lambert39"]), set(mv.CLE_LAMBERT39_RECTS))
        self.assertEqual({tool.NO_PHOTO, tool.NO_STRIP}, set(mv.NO_SWALL3_RECTS))
        self.assertEqual(set(tool.HOU_CELLS["texscore01"]), set(mv.HOU_TEXSCORE01_RECTS))
        self.assertEqual(set(tool.HOU_CELLS["texscore02"]), set(mv.HOU_TEXSCORE02_RECTS))
        self.assertEqual(set(tool.NO_CELLS["corp_temp_adbanner01"]), set(mv.NO_ADBANNER01_RECTS))
        self.assertEqual(set(tool.NO_CELLS["corp_temp_adbanner02"]), set(mv.NO_ADBANNER02_RECTS))
        texts = {text for cells in tool.HOU_CELLS.values() for text, _style in cells.values()}
        self.assertEqual(texts, {"NFL NETWORK", "PLAY 60", "ESPN", "NFL+"})       # u4's approved type panels only
        texts = {text for cells in tool.NO_CELLS.values() for text, _style in cells.values()}
        self.assertEqual(texts, {"NFL NETWORK", "PLAY 60", "ESPN", "NFLPA"})
        self.assertEqual(tool.CLE_TEXT, "HUNTINGTON BANK FIELD")

    def test_the_sweep_table_and_tool_agree(self):
        """The league-wide logo sweep: every cell of the tool is a table rect, in the venue table as an extra under the
        team's art, in u4's type panels only; Cleveland's kit slot (LIGHT_jumbotronA1) is never one."""
        import nfl2k5_modern_venues_2026_st3_art as tool
        self.assertEqual({(p, k): set(c) for p, cells in tool.SWEEP_CELLS.items() for k, c in cells.items()},
                         {pk: set(r) for pk, r in mv.SWEEP_RECTS.items()})
        texts = {cell[0] for cells in tool.SWEEP_CELLS.values() for c in cells.values() for cell in c.values()}
        self.assertEqual(texts, {"NFL NETWORK", "PLAY 60", "ESPN", "NFL+", "NFLPA", "NFL FLAG", "SUPER BOWL", "LXI"})
        for (prefix, key), rects in mv.SWEEP_RECTS.items():
            extra = next(e for e in mv.venues()[prefix]["extras"] if e["key"] == key and e["art"] == mv._sweep_art(prefix, key))
            self.assertEqual((extra["scene"], extra["layer"], extra["from"]), ("stadium", "full", "table"))
            self.assertEqual(extra["rects"], [list(r) for r in rects])
            self.assertNotIn("over", extra)
        self.assertNotIn(("s30", "LIGHT_jumbotronA1"), mv.SWEEP_RECTS)
        self.assertNotIn(("s05", "texscore02_fence"), mv.SWEEP_RECTS)          # fb2's shared-art residual item
        from mod_editor.core import nfl2k5_board_kit as bk
        painted = {e["material"] for v in bk.venues() for e in bk.spec(v).get("paint", ())}
        self.assertFalse(painted & {k for _p, k in mv.SWEEP_RECTS})

    def test_the_sweep_stays_off_u4s_team_rects(self):
        """No sweep cell overlaps a rect of u4's own art for the same texture (the team composes after the table)."""
        def overlap(a, b):
            return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])
        team = {("s02", "ad03"): [(2, 40, 126, 57)], ("s04", "panthers_score01"): [(0, 88, 98, 104)],
                ("s04", "panthers_score02"): [(0, 50, 97, 68), (0, 107, 32, 126), (32, 107, 64, 126), (64, 107, 97, 126)],
                ("s09", "sign02_sign04"): [(0, 0, 84, 86), (112, 86, 222, 170), (0, 172, 110, 256), (112, 172, 222, 256)],
                ("s28", "ad_bb02"): [(0, 0, 128, 52)], ("s29", "ad_bb01_LIGHT_ad_bb01"): [(130, 98, 256, 124), (128, 128, 256, 256)],
                ("s29", "ad_bb02"): [(128, 97, 256, 128)], ("s29", "banner_home_team"): [(0, 64, 128, 128)],
                ("s27", "lambert63"): [(0, 2, 128, 19), (0, 23, 128, 40)]}      # (st2's name rows, another extra)
        for pk, rects in mv.SWEEP_RECTS.items():
            for r in rects:
                self.assertFalse([t_ for t_ in team.get(pk, ()) if overlap(r, t_)], (pk, r))

    def test_paycors_moved_residual_goes_over_the_team_art(self):
        """fb2's s06 residual, moved into the table when tier 3 put Paycor Stadium on the board kit: fb2's PNG byte for
        byte, and the one st3 extra marked over, since its cell refills the panel under u4's [86, 88, 169, 128] rect."""
        extras = [e for e in mv.venues()["s06"]["extras"] if e["key"] == "signsA1"]
        self.assertEqual(len(extras), 1)
        extra = extras[0]
        self.assertEqual((extra["scene"], extra["layer"], extra["from"], extra.get("over")), ("stadium", "full", "table", True))
        self.assertEqual(extra["rects"], [[86, 83, 169, 126]])
        self.assertEqual(extra["sha256"], FB2_S06_SIGNSA1)
        items = [i for i in mv._extra_items("s06", set()) if i["key"] == "signsA1"]
        self.assertEqual([i["source"] for i in items], ["table_over"])
        self.assertGreater(mv.SOURCE_ORDER["table_over"], mv.SOURCE_ORDER["team"])
        overs = {(p, k) for p, k, art in OWN
                 for e in mv.venues()[p]["extras"] if e["key"] == k and e["art"] == art and e.get("over")}
        self.assertEqual(overs, {("s06", "signsA1")})

    def test_the_rects_stay_off_u4s_own_texans_slots_but_compose_under_them(self):
        """texscore01's Reebok cell touches the bull's rect (the team's art composes over it); nothing else overlaps."""
        def overlap(a, b):
            return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])
        bull, texans = (184, 2, 252, 56), ((4, 112, 160, 152), (192, 168, 256, 200))
        self.assertEqual([r for r in mv.HOU_TEXSCORE01_RECTS if overlap(r, bull)], [(183, 52, 256, 90)])
        self.assertEqual([r for r in mv.HOU_TEXSCORE02_RECTS for t in texans if overlap(r, t)], [])


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Planner(unittest.TestCase):
    """The real planner (an empty team folder, no league marks) paints each extra's cells in the dry-day and night
    bundles alike."""

    def test_the_planner_paints_the_cells_in_day_and_night(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            for prefix in ("s30", "s17", "s37"):
                pins = {p["name"]: p for p in mv.venues()[prefix]["bundles"]}
                bundles = {}
                for name, pin in pins.items():
                    e = mv._entry(archive, pin)
                    bundles[name] = archive.read(e.virtual_offset, e.size)
                # a team folder with no items of its own: the table extras apply only under team art (st2's rule)
                plan = mv.plan_venue(prefix, {"items": []}, bundles, {})
                base = plan.pop("base")
                keys = {i["key"] for i in plan["items"] if i.get("source") == "table"}
                self.assertEqual(keys, {e["key"] for e in mv.venues()[prefix]["extras"]}, prefix)
                for code in ("dd", "nd"):
                    name = f"{prefix}{code}.iff"
                    after, _edits = mv.modern_bundle(bundles[name], name, plan, base)
                    rec, dec = mv.decode_scenes(after)["stadium"]
                    rec0, dec0 = mv.decode_scenes(bundles[name])["stadium"]
                    rows = {mv.export_key(r.get("mapped_material_names")): r for r in mv.p8_rows(rec).values()}
                    rows0 = {mv.export_key(r.get("mapped_material_names")): r for r in mv.p8_rows(rec0).values()}
                    for extra in mv.venues()[prefix]["extras"]:
                        if (prefix, extra["key"]) in mv.SWEEP_RECTS:
                            continue                                # the sweep's cells: Sweep.test_the_planner_paints_the_sweep
                        key = next(k for k in rows if k == extra["key"] or k.endswith(extra["key"]))
                        now = mv.read_texture(dec, rec, rows[key])[..., :3].astype(int)
                        was = mv.read_texture(dec0, rec0, rows0[key])[..., :3].astype(int)
                        for x0, y0, x1, y1 in extra["rects"]:
                            changed = np.abs(now[y0:y1, x0:x1] - was[y0:y1, x0:x1]).sum(axis=2) > 24
                            self.assertGreater(float(changed.mean()), 0.3, (name, key, (x0, y0, x1, y1)))

    def test_the_planner_paints_paycors_moved_residual_in_all_nine_bundles(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            pins = {p["name"]: p for p in mv.venues()["s06"]["bundles"]}
            bundles = {}
            for name, pin in pins.items():
                e = mv._entry(archive, pin)
                bundles[name] = archive.read(e.virtual_offset, e.size)
        plan = mv.plan_venue("s06", {"items": []}, bundles, {})
        base = plan.pop("base")
        item = next(i for i in plan["items"] if i["key"] == "signsA1" and i.get("source") == "table_over")
        self.assertEqual(set(item["variants"]), set(mv.CODES))
        for name in sorted(bundles):
            code = name[3:5]
            after, _edits = mv.modern_bundle(bundles[name], name, plan, base)
            rec, dec = mv.decode_scenes(after)["stadium"]
            rec0, dec0 = mv.decode_scenes(bundles[name])["stadium"]
            k, w, h = item["variants"][code]
            now = mv.read_texture(dec, rec, mv.p8_rows(rec)[k])[..., :3].astype(int)
            was = mv.read_texture(dec0, rec0, mv.p8_rows(rec0)[k])[..., :3].astype(int)
            x0, y0, x1, y1 = (round(v * s) for v, s in zip(mv.CIN_SIGNSA1_RECTS[0], (w / 256, h / 256, w / 256, h / 256)))
            changed = np.abs(now[y0:y1, x0:x1] - was[y0:y1, x0:x1]).sum(axis=2) > 24
            self.assertGreater(float(changed.mean()), 0.3, name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Sweep(unittest.TestCase):
    """The logo sweep's cells, painted by the real planner (an empty team folder) in the dry-day and night bundles of
    every swept venue."""

    def test_the_planner_paints_the_sweep(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            for prefix in sorted({p for p, _k in mv.SWEEP_RECTS}):
                pins = {p["name"]: p for p in mv.venues()[prefix]["bundles"]}
                bundles = {}
                for name, pin in pins.items():
                    e = mv._entry(archive, pin)
                    bundles[name] = archive.read(e.virtual_offset, e.size)
                plan = mv.plan_venue(prefix, {"items": []}, bundles, {})
                base = plan.pop("base")
                for code in ("dd", "nd"):
                    name = f"{prefix}{code}.iff"
                    after, _edits = mv.modern_bundle(bundles[name], name, plan, base)
                    rec, dec = mv.decode_scenes(after)["stadium"]
                    rec0, dec0 = mv.decode_scenes(bundles[name])["stadium"]
                    for (p, key), rects in mv.SWEEP_RECTS.items():
                        if p != prefix:
                            continue
                        item = next(i for i in plan["items"] if i["key"] == key and i.get("rects") == [list(r) for r in rects])
                        k = item["dd"]["index"] if code == "dd" else item["variants"][code][0]   # the planner's own map
                        now = mv.read_texture(dec, rec, mv.p8_rows(rec)[k])[..., :3].astype(int)
                        was = mv.read_texture(dec0, rec0, mv.p8_rows(rec0)[k])[..., :3].astype(int)
                        for x0, y0, x1, y1 in rects:
                            changed = np.abs(now[y0:y1, x0:x1] - was[y0:y1, x0:x1]).sum(axis=2) > 24
                            self.assertGreater(float(changed.mean()), 0.3, (name, key, (x0, y0, x1, y1)))


if __name__ == "__main__":
    unittest.main()
