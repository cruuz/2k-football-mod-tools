"""2026 venue art (experimental): the venue table, the art contract, the helpers and a retail bundle refit."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_venues_2026 as mv  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"
CLASSES = {"wall", "board", "sign", "fan", "colour", "league"}


#: st3's logo sweep (2026-09-29) appends its own rect extras to some venues; these tests pin st2's own ones
_SWEEP_ARTS = {mv._sweep_art(p, k) for p, k in getattr(mv, "SWEEP_RECTS", {})}


def _own_extras(prefix):
    """The venue's table extras less the logo sweep's (tests/mod_editor/test_nfl2k5_modern_venues_2026_st3.py)."""
    return [e for e in mv.venues()[prefix]["extras"] if e["art"] not in _SWEEP_ARTS]


def _own_items(prefix, supplied):
    shas = {e["sha256"] for e in mv.venues()[prefix]["extras"] if e["art"] in _SWEEP_ARTS}
    return [i for i in mv._extra_items(prefix, supplied) if i["sha256"] not in shas]


def _png(path, rgba):
    from PIL import Image
    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(rgba, dtype=np.uint8), "RGBA").save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _solid(width, height, colour, alpha=255):
    import numpy as np
    out = np.zeros((height, width, 4), dtype=np.uint8)
    out[..., :3] = colour
    out[..., 3] = alpha
    return out


def _shield(size=64):
    """A synthetic stand-in for a league mark: a navy disc with a white band."""
    import numpy as np
    yy, xx = np.mgrid[0:size, 0:size]
    disc = (xx - size / 2 + 0.5) ** 2 + (yy - size / 2 + 0.5) ** 2 <= (size * 0.45) ** 2
    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[disc] = (1, 51, 105, 255)
    out[disc & (abs(yy - size / 2) < size * 0.08)] = (255, 255, 255, 255)
    return out


def _art_root(root, prefix="s03", items=(), spec_banners=None, league=False):
    """A one-team art root in the division layout: <root>/TEAM/venue/manifest.json + TEAM/spec.json."""
    venue = root / "TEAM" / "venue"
    rows = []
    for scene, key, layer, rgba in items:
        rel = f"retail/{scene}/{key}.png"
        rows.append(dict(scene=scene, material=key, size=[rgba.shape[1], rgba.shape[0]], file=rel,
                         master=f"master4x/{scene}/{key}.png", layer=layer, sha256=_png(venue / rel, rgba)))
    venue.mkdir(parents=True, exist_ok=True)
    (venue / "manifest.json").write_text(json.dumps(dict(schema=mv.ART_SCHEMA, team="TST", venue_prefix=prefix,
                                                         items=rows)))
    (root / "TEAM" / "spec.json").write_text(json.dumps(dict(venue=dict(banners=spec_banners or {}))))
    if league:
        marks = {}
        for mark in mv.LEAGUE_MARKS:
            marks[mark] = dict(file=f"{mark}.png", sha256=_png(root / "_league" / f"{mark}.png", _shield()))
        (root / "_league" / "manifest.json").write_text(json.dumps(dict(schema=mv.LEAGUE_SCHEMA, marks=marks)))
    return root


class TableTests(unittest.TestCase):
    def test_the_table_covers_every_home_venue_but_the_giants_and_jets(self):
        venues = mv.venues()
        self.assertEqual(len(mv.table()["venues"]), 30)
        self.assertGreaterEqual(len(venues), 30)
        self.assertFalse(set(venues) & set(mv.METLIFE_VENUES))
        self.assertIn("s37", venues)  # Houston's asset code
        for prefix, row in venues.items():
            self.assertEqual([b["name"] for b in row["bundles"]], list(mv.bundle_names(prefix)), prefix)
            for pin in row["bundles"]:
                self.assertEqual([s["kind"] for s in pin["sites"]], list(mv.SCENES), pin["name"])
                self.assertEqual(pin["name_id"], mv.name_id(pin["name"]))
            for target in row["targets"]:
                self.assertIn(target["class"], CLASSES, target)
                self.assertEqual(set(target["variants"]), set(mv.CODES), target["key"])
                self.assertEqual(target["variants"]["dd"][0], target["texture"])
            for entry in row.get("league", ()):
                self.assertIn(entry["mark"], mv.LEAGUE_MARKS)
                x0, y0, x1, y1 = entry["rect"]
                self.assertTrue(0 <= x0 < x1 <= entry["size"][0] and 0 <= y0 < y1 <= entry["size"][1], entry)
                self.assertNotIn(None, entry["variants"].values(), (prefix, entry["key"]))

    def test_the_known_variant_oddities_are_mapped(self):
        venues = mv.venues()
        target = lambda prefix, key: next(t for t in venues[prefix]["targets"] if t["key"] == key)  # noqa: E731
        # Chicago's afternoon bundles call the ribbon atlas bearwall02: the same texture
        self.assertTrue(all(target("s05", "bearwall01")["variants"][c] for c in mv.CODES))
        # Miami's snow bundles hold the walls at 256x256
        self.assertEqual(target("s14", "wall05")["variants"]["ds"][1:], [256, 256])
        # Foxborough's night wall04 is other art: not mapped
        self.assertIsNone(target("s16", "wall04")["variants"]["nd"])
        self.assertEqual(venues["s06"]["field"], {"endzones": "shared", "center_logo": True})
        self.assertFalse(venues["s00"]["field"]["center_logo"])

    def test_names_rename_only_same_building_venues(self):
        rows = mv.names()["venues"]
        self.assertEqual(set(rows), set(mv.table()["venues"]))
        for code, row in rows.items():
            self.assertIn(row["building"], ("same", "moved"), code)
            self.assertTrue(row["sources"], code)
            if row["rename"]:
                self.assertEqual(row["building"], "same", code)
                self.assertNotEqual(row["rename"]["name"], row["retail"]["name"], code)
        self.assertEqual(len(mv.renames()), 12)
        self.assertIsNone(rows["s23"]["rename"])  # the Rams moved: the model is the old dome
        self.assertIsNone(rows["s37"]["rename"])  # Reliant Stadium again in 2026

    def test_the_league_sponsor_sheet_reaches_every_home_venue(self):
        art = mv.DATA_DIR / mv.LEAGUE_ART[0]["art"]
        for prefix, row in mv.table()["venues"].items():
            entries = row["league_art"]
            self.assertEqual([e["key"] for e in entries], ["banner_corp"], prefix)
            self.assertEqual(entries[0]["sha256"], mv.sha(art.read_bytes()), prefix)
            self.assertNotIn(None, entries[0]["variants"].values(), prefix)
            self.assertEqual(entries[0]["rects"], mv.LEAGUE_ART[0]["rects"])

    def test_the_tampa_bay_ship_banner_takes_the_2026_name(self):
        """s27's lambert12, a cloth on Buccaneer Cove's ship, reads TAMPA BAY STADIUM (the building the stadium replaced
        in 1998); the table's overlay extra paints RAYMOND JAMES STADIUM in plain type over its top cloth only, and the
        table's generator keeps the extra (st2, 2026-09-28)."""
        import numpy as np
        extras = _own_extras("s27")
        self.assertEqual([(e["scene"], e["key"], e["layer"], e["from"]) for e in extras],
                         [("stadium", "lambert12", "overlay", "table"), ("stadium", "lambert63", "full", "table")])
        path = mv.DATA_DIR / extras[0]["art"]
        self.assertEqual(extras[0]["sha256"], mv.sha(path.read_bytes()))
        self.assertEqual(mv.TABLE_EXTRAS["s27"][0], ("stadium", "lambert12", "overlay", extras[0]["art"]))
        self.assertEqual([e for e in mv._table_extras(mv.TABLE_EXTRAS["s27"]) if e["art"] not in _SWEEP_ARTS], extras)
        rgba = mv._rgba(path.read_bytes())
        self.assertEqual(rgba.shape, (64, 64, 4))
        rows = np.nonzero(rgba[..., 3].max(axis=1))[0]
        self.assertLessEqual(int(rows.max()), 26)        # the top cloth only: the other cloths and the ball stay retail
        items = _own_items("s27", set())
        self.assertEqual([(i["key"], i["layer"], i["source"]) for i in items],
                         [("lambert12", "overlay", "table"), ("lambert63", "full", "table")])
        self.assertEqual([i["key"] for i in _own_items("s27", {("stadium", "lambert12")})], ["lambert63"])

    def test_the_tampa_bay_sideline_fascia_takes_the_2026_name(self):
        """s27's lambert63 draws TAMPA B / AY STADIUM end to end along both sideline fascias (the SN audit); the rect
        extra redraws its two rows as one run of RAYMOND JAMES STADIUM, and nothing else (st2, 2026-09-28)."""
        import numpy as np
        import nfl2k5_modern_venues_2026_art as art_tool
        extra = mv.venues()["s27"]["extras"][1]
        self.assertEqual(extra["rects"], [list(r) for r in mv.TB_LAMBERT63_RECTS])
        self.assertEqual([row for row, _start in art_tool.TB_FASCIA_ROWS], list(mv.TB_LAMBERT63_RECTS))
        data = (mv.DATA_DIR / extra["art"]).read_bytes()
        self.assertEqual(extra["sha256"], mv.sha(data))
        rgba = mv._rgba(data)
        self.assertEqual(rgba.shape, (128, 128, 4))
        inside = np.zeros((128, 128), dtype=bool)
        for x0, y0, x1, y1 in mv.TB_LAMBERT63_RECTS:
            inside[y0:y1, x0:x1] = True
        self.assertTrue((rgba[..., 3][inside] == 255).all())
        self.assertFalse(rgba[..., 3][~inside].any())            # the league marks' area stays clear
        # the lettering continues across the two rows: ink at the end of row one and at the start of row two's run
        lum = rgba[..., :3].astype(float).mean(axis=-1)
        bg = float(np.median(lum[inside]))
        self.assertTrue((lum[2:19, 110:126] < bg - 30).any() and (lum[23:40, 12:28] < bg - 30).any())

    def test_washingtons_defunct_sponsor_cells_take_the_league_type(self):
        """u4's s29 art keeps MOTOROLA, Reebok and ESPN VIDEOGAMES cells in banner01 (the club-level fascia ring) and
        exit01 (the header over the exit tunnels). The table's rect extras redraw only those cells in u4's type panels
        and go under the team's own banner01 slots (main, 2026-09-28, under u4's league sponsor policy)."""
        import numpy as np
        import nfl2k5_modern_venues_2026_art as art_tool
        extras = _own_extras("s29")
        self.assertEqual([(e["scene"], e["key"], e["layer"], e["from"]) for e in extras],
                         [("stadium", "banner01", "full", "table"), ("stadium", "exit01", "full", "table")])
        self.assertEqual([e for e in mv._table_extras(mv.TABLE_EXTRAS["s29"]) if e["art"] not in _SWEEP_ARTS], extras)
        for extra, rects in zip(extras, (mv.WAS_BANNER01_RECTS, mv.WAS_EXIT01_RECTS)):
            self.assertEqual(extra["rects"], [list(r) for r in rects])
            self.assertEqual(set(art_tool.WAS_CELLS[extra["key"]]), set(rects))   # the generator draws every cell
            data = (mv.DATA_DIR / extra["art"]).read_bytes()
            self.assertEqual(extra["sha256"], mv.sha(data))
            rgba = mv._rgba(data)
            inside = np.zeros(rgba.shape[:2], dtype=bool)
            for x0, y0, x1, y1 in rects:
                inside[y0:y1, x0:x1] = True
            self.assertTrue((rgba[..., 3][inside] == 255).all())
            self.assertFalse(rgba[..., 3][~inside].any())        # nothing outside the cells: no retail pixel ships
        # the rect extras apply where the team supplies the key too, and compose before the team's items
        items = _own_items("s29", {("stadium", "banner01"), ("stadium", "exit01")})
        self.assertEqual([(i["key"], i["source"], len(i["rects"])) for i in items],
                         [("banner01", "table", 9), ("exit01", "table", 1)])
        self.assertLess(mv.SOURCE_ORDER["table"], mv.SOURCE_ORDER["team"])
        current = _solid(32, 32, (10, 20, 30))
        table = dict(scene="stadium", key="banner01", layer="full", size=[32, 32], rects=[[0, 0, 16, 8]])
        team = dict(scene="stadium", key="banner01", layer="full", size=[32, 32], rects=[[0, 16, 32, 24]])
        under = mv.compose(table, current, current, _solid(32, 32, (250, 250, 250)), "d")
        out = mv.compose(team, current, current, _solid(32, 32, (1, 51, 105)), "d", canvas=under)
        self.assertTrue((out[0:8, 0:16, :3] == 250).all() and (out[16:24, :, :3] == (1, 51, 105)).all())
        self.assertTrue(np.array_equal(out[8:16], current[8:16]) and np.array_equal(out[24:], current[24:]))

    def test_seattles_tower_takes_lumen_field_and_the_league_type(self):
        """s26: the tower's name band (lambert73) reads SEAHAWKS STADIUM, its panels MOTOROLA and ESPN VIDEOGAMES
        (lambert70), its message board a Visual Concepts welcome (lambert69), and lambert74 Reebok and ESPN THE
        MAGAZINE; the table's rect extras redraw only those cells (the SN audit and u4's sponsor policy, st2
        2026-09-28)."""
        import numpy as np
        import nfl2k5_modern_venues_2026_art as art_tool
        extras = mv.venues()["s26"]["extras"]
        self.assertEqual([(e["key"], e["layer"], e["from"]) for e in extras],
                         [("lambert73", "full", "table"), ("lambert70", "full", "table"), ("lambert69", "full", "table"),
                          ("lambert74", "full", "table")])
        self.assertEqual(mv._table_extras(mv.TABLE_EXTRAS["s26"]), extras)
        rects = {"lambert73": mv.SEA_LAMBERT73_RECTS, "lambert70": mv.SEA_LAMBERT70_RECTS,
                 "lambert69": mv.SEA_LAMBERT69_RECTS, "lambert74": mv.SEA_LAMBERT74_RECTS}
        self.assertEqual(tuple(art_tool.SEA_NAME[0:1]), mv.SEA_LAMBERT73_RECTS)
        for extra in extras:
            key = extra["key"]
            self.assertEqual(extra["rects"], [list(r) for r in rects[key]])
            if key != "lambert73":
                self.assertEqual(set(art_tool.SEA_CELLS[key]), set(rects[key]))
            data = (mv.DATA_DIR / extra["art"]).read_bytes()
            self.assertEqual(extra["sha256"], mv.sha(data))
            rgba = mv._rgba(data)
            inside = np.zeros(rgba.shape[:2], dtype=bool)
            for x0, y0, x1, y1 in rects[key]:
                inside[y0:y1, x0:x1] = True
            self.assertTrue((rgba[..., 3][inside] == 255).all(), key)
            self.assertFalse(rgba[..., 3][~inside].any(), key)          # no retail pixel ships
        self.assertEqual([i["key"] for i in mv._extra_items("s26", set())], ["lambert73", "lambert70", "lambert69",
                                                                            "lambert74"])

    def test_pittsburghs_scoreboard_marks_become_type_over_the_team_art(self):
        """s22: d2's board art draws the Acrisure A mark and three Nike swooshes; the table's extras go over the team's
        art (table_over) and redraw only those cells: ACRISURE STADIUM in plain type and PLAY 60 panels (main,
        2026-09-28)."""
        import numpy as np
        import nfl2k5_modern_venues_2026_art as art_tool
        extras = mv.venues()["s22"]["extras"]
        self.assertEqual([(e["key"], e["layer"], e.get("over")) for e in extras],
                         [("ad_bb01", "full", True), ("ad_bb02", "full", True)])
        self.assertEqual(mv._table_extras(mv.TABLE_EXTRAS["s22"]), extras)
        rects = {"ad_bb01": mv.PIT_AD_BB01_RECTS, "ad_bb02": mv.PIT_AD_BB02_RECTS}
        self.assertEqual(set(art_tool.PIT_CELLS["ad_bb01"]) | {art_tool.PIT_NAME[0]}, set(mv.PIT_AD_BB01_RECTS))
        self.assertEqual(set(art_tool.PIT_CELLS["ad_bb02"]), set(mv.PIT_AD_BB02_RECTS))
        for extra in extras:
            data = (mv.DATA_DIR / extra["art"]).read_bytes()
            self.assertEqual(extra["sha256"], mv.sha(data))
            rgba = mv._rgba(data)
            inside = np.zeros(rgba.shape[:2], dtype=bool)
            for x0, y0, x1, y1 in rects[extra["key"]]:
                inside[y0:y1, x0:x1] = True
            self.assertTrue((rgba[..., 3][inside] == 255).all())
            self.assertFalse(rgba[..., 3][~inside].any())
        # they apply where the team supplies the key and compose after the team's items
        items = mv._extra_items("s22", {("stadium", "ad_bb01"), ("stadium", "ad_bb02")})
        self.assertEqual([(i["key"], i["source"]) for i in items], [("ad_bb01", "table_over"), ("ad_bb02", "table_over")])
        self.assertGreater(mv.SOURCE_ORDER["table_over"], mv.SOURCE_ORDER["team"])
        current = _solid(32, 32, (10, 20, 30))
        team = dict(scene="stadium", key="ad_bb01", layer="full", size=[32, 32], rects=[[0, 0, 32, 16]])
        over = dict(scene="stadium", key="ad_bb01", layer="full", size=[32, 32], rects=[[0, 0, 16, 8]])
        mid = mv.compose(team, current, current, _solid(32, 32, (0, 0, 0)), "d")
        out = mv.compose(over, current, current, _solid(32, 32, (250, 250, 250)), "d", canvas=mid)
        self.assertTrue((out[0:8, 0:16, :3] == 250).all() and (out[0:8, 16:, :3] == 0).all() and (out[8:16, :, :3] == 0).all())
        self.assertTrue(np.array_equal(out[16:], current[16:]))
        # an extra over the team's art must name its rects
        from unittest import mock
        row = dict(mv.venues()["s22"], extras=[dict(extras[1], rects=[])])
        with mock.patch.object(mv, "venues", return_value={"s22": row}):
            with self.assertRaises(mv.ModernVenuesError):
                mv._extra_items("s22", set())

    def test_kansas_city_fallback_is_arrowheads_art_without_the_yard_markers(self):
        extras = [e for e in mv.venues()[mv.ARROWHEAD_VENUE]["extras"] if e.get("from") == "modern_arrowhead"]
        keys = {e["key"] for e in extras}
        self.assertFalse(keys & {"yardside", "yardfront"})
        for extra in extras:
            self.assertEqual(extra["sha256"], mv.sha(mv.arrowhead_art_path(extra["art"]).read_bytes()), extra["art"])

    def test_kansas_city_ad01_loses_its_defunct_sponsors_around_u4s_slots(self):
        """s13: the team folder's own ad01 item keeps Modern Arrowhead's fallback off, so the retail ESPN THE MAGAZINE,
        MOTOROLA, ESPN VIDEOGAMES, PLAYERS INC and VISUAL CONCEPTS stay around u4's slots; the table's rect extra (after
        Modern Arrowhead's own, which record_table keeps first) redraws only those cells (st2, 2026-09-28)."""
        import numpy as np
        import nfl2k5_modern_venues_2026_art as art_tool
        extras = mv.venues()["s13"]["extras"]
        self.assertEqual(extras[:-1], mv._arrowhead_extras())
        extra = extras[-1]
        self.assertEqual([extra], mv._table_extras(mv.TABLE_EXTRAS["s13"]))
        self.assertEqual((extra["key"], extra["layer"], extra["from"]), ("ad01", "full", "table"))
        self.assertEqual(set(art_tool.KC_CELLS["ad01"]), set(mv.KC_AD01_RECTS))
        data = (mv.DATA_DIR / extra["art"]).read_bytes()
        self.assertEqual(extra["sha256"], mv.sha(data))
        rgba = mv._rgba(data)
        inside = np.zeros(rgba.shape[:2], dtype=bool)
        for x0, y0, x1, y1 in mv.KC_AD01_RECTS:
            inside[y0:y1, x0:x1] = True
        self.assertTrue((rgba[..., 3][inside] == 255).all())
        self.assertFalse(rgba[..., 3][~inside].any())
        # every cell stays clear of u4's two ad01 slots ([0, 0, 128, 64] and [128, 192, 256, 256])
        for x0, y0, x1, y1 in mv.KC_AD01_RECTS:
            for a0, b0, a1, b1 in ((0, 0, 128, 64), (128, 192, 256, 256)):
                self.assertTrue(x1 <= a0 or x0 >= a1 or y1 <= b0 or y0 >= b1, (x0, y0, x1, y1))
        items = mv._extra_items("s13", {("stadium", "ad01")})
        self.assertEqual([(i["key"], i["source"]) for i in items if i["key"] == "ad01"], [("ad01", "table")])


class ContractTests(unittest.TestCase):
    def test_slots_become_rects_and_hashes_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = _art_root(Path(folder), items=[("stadium", "billswall_01", "full", _solid(128, 128, (0, 51, 141)))],
                             spec_banners={"billswall_01": {"banners": [{"slot": [0, 0, 128, 64]}]}})
            art = mv.load_art(root)
            item = art["venues"]["s03"]["items"][0]
            self.assertEqual(item["rects"], [[0, 0, 128, 64]])
            manifest = root / "TEAM" / "venue" / "manifest.json"
            doc = json.loads(manifest.read_text())
            doc["items"][0]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(mv.ModernVenuesError, "differs from its manifest"):
                mv.load_art(root)

    def test_giants_and_jets_are_skipped_and_bad_items_refuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root = _art_root(Path(folder), prefix="s18", items=[("field", "center_logo", "overlay", _solid(256, 256, (1, 2, 3)))])
            art = mv.load_art(root)
            self.assertEqual(art["venues"], {})
            self.assertEqual(art["skipped"][0]["venue"], "s18")
        with tempfile.TemporaryDirectory() as folder:
            root = _art_root(Path(folder), items=[("field", "yard_numbers", "overlay", _solid(256, 256, (1, 2, 3)))])
            with self.assertRaisesRegex(mv.ModernVenuesError, "not an end zone panel"):
                mv.load_art(root)

    def test_league_marks_load_from_the_art_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = _art_root(Path(folder), items=[("field", "center_logo", "overlay", _solid(256, 256, (1, 2, 3)))], league=True)
            art = mv.load_art(root)
            self.assertEqual(sorted(art["league"]), sorted(mv.LEAGUE_MARKS))
            todo = mv.venues_to_write(art)
            self.assertEqual(len(todo), len(mv.venues()))  # league-wide pass also reaches sponsor-only special venues
            self.assertEqual([p for p, team in todo if team is not None], ["s03"])
            with self.assertRaisesRegex(mv.ModernVenuesError, "Kansas City"):
                mv.venues_to_write(dict(art, venues={"s13": art["venues"]["s03"]}), modern_arrowhead=True)
            self.assertNotIn("s13", [p for p, _t in mv.venues_to_write(art, modern_arrowhead=True)])


class HelperTests(unittest.TestCase):
    def test_export_key_and_names(self):
        self.assertEqual(mv.export_key(["ad_bb01", "LIGHT_ad_bb01"]), "ad_bb01_LIGHT_ad_bb01")
        self.assertEqual(mv._norm(["LIGHT_ad_bb01"]), mv._norm(["ad_bb01"]))

    def test_letterbox_keeps_aspect_and_clears_the_sides(self):
        out = mv.letterbox(_solid(256, 256, (200, 0, 0)), 512, 256)
        self.assertEqual(out.shape, (256, 512, 4))
        self.assertEqual(int(out[128, 10, 3]), 0)
        self.assertEqual(int(out[128, 256, 3]), 255)

    def test_clean_turf_fills_marks_and_flattens_patterns(self):
        import numpy as np
        turf = _solid(64, 32, (60, 110, 50))
        turf[10:20, 10:40] = (250, 250, 250, 255)
        clean = mv.clean_turf(turf)
        self.assertLess(int(np.abs(clean[15, 20, :3].astype(int) - (60, 110, 50)).max()), 3)
        stripes = _solid(64, 32, (240, 120, 20))
        stripes[:, ::2] = (0, 0, 0, 255)
        flat = mv.clean_turf(stripes)
        self.assertEqual(len({tuple(p) for p in flat[..., :3].reshape(-1, 3)}), 1)

    def test_league_art_replaces_only_its_rect(self):
        import numpy as np
        base = _solid(64, 64, (90, 90, 90))
        base[20:40, 20:40] = (200, 30, 30, 255)
        marks = {"nfl_shield": dict(rgba=_shield(), sha256="x")}
        out = mv.league_art(base, dict(rect=[18, 18, 42, 42], mark="nfl_shield"), marks)
        self.assertTrue(np.array_equal(out[:18], base[:18]) and np.array_equal(out[42:], base[42:]))
        self.assertFalse(np.array_equal(out[18:42, 18:42], base[18:42, 18:42]))
        white = mv.knockout_white(_shield())
        self.assertTrue((white[..., :3] == 255).all())

    def test_compose_keeps_pixels_outside_the_rects(self):
        import numpy as np
        current = _solid(32, 32, (10, 20, 30))
        art = _solid(32, 32, (250, 250, 250))
        item = dict(scene="stadium", key="wall01", layer="full", size=[32, 32], rects=[[0, 0, 16, 32]])
        out = mv.compose(item, current, current, art, "d")
        self.assertTrue(np.array_equal(out[:, 16:], current[:, 16:]))
        self.assertTrue((out[:, :16, :3] == 250).all())


class StateTests(unittest.TestCase):
    def test_bundle_states_from_site_hashes_and_the_receipt(self):
        class Entry:
            name_id, size, virtual_offset = 7, 8, 0

        class Archive:
            entries = [Entry()]

            def __init__(self, blob):
                self.blob = blob

            def read(self, at, size):
                return self.blob[at:at + size]

        pin = dict(name="s03dd.iff", outer=0, name_id=7, size=8,
                   sites=[dict(kind="field", offset=0, size=4, retail=mv.sha(b"aaaa")),
                          dict(kind="stadium", offset=4, size=4, retail=mv.sha(b"cccc"))])
        self.assertEqual(mv.bundle_state(Archive(b"aaaacccc"), pin, None, None), "retail")
        self.assertEqual(mv.bundle_state(Archive(b"aaaazzzz"), pin, None, None), "foreign")
        colour = {"bundle_pins": {"s03dd.iff": {"sites": [dict(kind="field", applied=mv.sha(b"gggg"))]}}}
        self.assertEqual(mv.bundle_state(Archive(b"ggggcccc"), pin, None, colour), "retail")
        receipt = {"bundles": {"s03dd.iff": {"applied_sha256": mv.sha(b"bbbbdddd")}}}
        self.assertEqual(mv.bundle_state(Archive(b"bbbbdddd"), pin, receipt, None), "venues")
        self.assertEqual(mv.bundle_state(Archive(b"aaaacccc"), pin, receipt, None), "foreign")


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class RetailTests(unittest.TestCase):
    def _bundles(self, prefix):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        with mv._outer_image()(PACKS) as archive:
            out = {}
            for pin in mv.venues()[prefix]["bundles"]:
                entry = mv._entry(archive, pin)
                out[pin["name"]] = archive.read(entry.virtual_offset, entry.size)
        return out

    def test_the_packs_read_as_retail(self):
        self.assertEqual(mv.image_status(PACKS), "retail")

    def test_a_bundle_refit_changes_only_the_planned_textures(self):
        import numpy as np
        bundles = self._bundles("s03")
        for name, data in bundles.items():
            self.assertEqual(mv.sha(data), next(p for p in mv.venues()["s03"]["bundles"] if p["name"] == name)["retail_sha256"])
        with tempfile.TemporaryDirectory() as folder:
            end_zone = _solid(256, 128, (0, 51, 141), alpha=235)
            root = _art_root(Path(folder), items=[("field", "endzone_N_M", "overlay", end_zone),
                                                   ("stadium", "billswall_01", "full", _solid(128, 128, (0, 51, 141)))],
                             spec_banners={"billswall_01": {"banners": [{"slot": [0, 0, 128, 128]}]}}, league=True)
            art = mv.load_art(root)
            plan = mv.plan_venue("s03", art["venues"]["s03"], bundles, art["league"])
        base = plan.pop("base")
        self.assertIn("billswall_04", plan["uncovered"])
        name = "s03nr.iff"
        after, edits = mv.modern_bundle(bundles[name], name, plan, base)
        data = bundles[name]
        self.assertEqual(len(after), len(data))
        a, r = np.frombuffer(after, np.uint8), np.frombuffer(data, np.uint8)
        outside = np.ones(len(a), dtype=bool)
        for e in edits:
            outside[e["offset"]:e["offset"] + e["size"]] = False
            self.assertEqual(after[e["offset"]:e["offset"] + 32], data[e["offset"]:e["offset"] + 32])
        self.assertEqual(int(np.count_nonzero((a != r) & outside)), 0)
        before_scenes, after_scenes = mv.decode_scenes(data), mv.decode_scenes(after)
        planned = {(e["kind"], t["texture"]) for e in edits for t in e["detail"]["textures"]}
        changed = set()
        for scene in mv.SCENES:
            rb, db = before_scenes[scene]
            ra, da = after_scenes[scene]
            self.assertEqual(db[:int(rb["system_bytes"])], da[:int(ra["system_bytes"])], scene)
            for index, row in mv.p8_rows(rb).items():
                if not np.array_equal(mv.read_texture(db, rb, row), mv.read_texture(da, ra, mv.p8_rows(ra)[index])):
                    changed.add((scene, index))
        self.assertEqual(changed, planned)
        self.assertTrue(any(i["source"] == "league" for e in edits for t in e["detail"]["textures"] for i in t["items"]))

    def test_same_building_venues_take_their_2026_names_and_nothing_else_moves(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        mm = mv._mm()
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        with mv._outer_image()(PACKS) as archive:
            _entry, rost = mv._read_rost(archive)
        self.assertEqual(mv.rost_state(rost), "retail")
        after, receipt = mv.rost_rename(rost)
        self.assertEqual(len(after), len(rost))
        self.assertEqual(mv.rost_state(after), "applied")
        header = rr.RESOURCE_HEADER_SIZE
        allowed = set()
        records = dict(mm._stadium_records(rost[header:]))
        for row in receipt["records"]:
            start, end = row["block"]
            allowed |= set(range(header + start, header + end))
        for offset, fields in records.items():
            if fields["asset_code"][1] in mv.renames():
                allowed |= {header + offset + f + k for f, _n in mm.ROST_STRING_FIELDS for k in range(4)}
        changed = {i for i, (a, b) in enumerate(zip(rost, after)) if a != b}
        self.assertTrue(changed and changed <= allowed)
        again, second = mv.rost_rename(after)
        self.assertEqual(again, after)
        self.assertEqual({r["state"] for r in second["records"]}, {"already_applied"})
        codes = {f["asset_code"][1]: {k: v[1] for k, v in f.items()} for _o, f in mm._stadium_records(after[header:])}
        self.assertEqual(codes["s22"]["name"], "Acrisure Stadium")
        self.assertEqual(codes["s08"]["display_name"], "Empower Field at Mile High")
        self.assertEqual(codes["s22"]["asset_code"], "s22")
        for code in ("s00", "s13", "s18", "s19", "s37"):  # moved, already right, MetLife's
            before = {k: v[1] for k, v in records[next(o for o, f in records.items() if f["asset_code"][1] == code)].items()}
            self.assertEqual(codes[code], before, code)

    def test_the_resolver_reproduces_the_table(self):
        bundles = self._bundles("s05")
        decoded = {mv.code_of(n): mv.decode_scenes(d)["stadium"] for n, d in bundles.items()}
        target = next(t for t in mv.venues()["s05"]["targets"] if t["key"] == "bearwall01")
        found = mv.resolve_variants(target["texture"], decoded)
        self.assertEqual({c: v[0] for c, v in found.items()}, {c: v[0] for c, v in target["variants"].items()})


if __name__ == "__main__":
    unittest.main()
