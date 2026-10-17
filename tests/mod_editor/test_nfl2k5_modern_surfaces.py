"""Modern playing surfaces (experimental): the venue table, the art, the colour solve, the end-zone recolour and the
retail bundle transform (fit, planar UVs, preserved end zones, detail normals, divots, idempotence)."""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_surfaces as ms  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"


def _hsv(rgb):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))
    return h * 360, s, v


class TableTests(unittest.TestCase):
    def test_every_home_venue_has_a_cited_surface_and_a_matching_look(self):
        rows = ms.venues()
        self.assertEqual(set(rows), set(ms.HOME_PREFIXES))
        for prefix, row in rows.items():
            self.assertIn(row["surface"], ("synthetic", "grass"), prefix)
            self.assertEqual(ms.LOOKS[row["look"]]["family"], row["surface"], prefix)
            self.assertTrue(row["sources"] and all("http" in s for s in row["sources"]), prefix)
        self.assertEqual(sum(r["surface"] == "grass" for r in rows.values()), 16)

    def test_the_2026_venues_that_went_back_to_turf_after_the_world_cup_are_synthetic(self):
        rows = ms.venues()
        for prefix in ("s01", "s07", "s16", "s18", "s19", "s23", "s24", "s26", "s37"):
            self.assertEqual(rows[prefix]["surface"], "synthetic", prefix)
        for prefix in ("s03", "s13", "s20", "s22", "s00"):   # Highmark, Arrowhead, Allegiant, Acrisure, State Farm
            self.assertEqual(rows[prefix]["surface"], "grass", prefix)

    def test_overrides_pick_a_look_per_family_and_refuse_the_wrong_family(self):
        self.assertEqual(ms.venue_look("s26", {"synthetic": "synthetic_vivid"}), "synthetic_vivid")
        self.assertEqual(ms.venue_look("s13", {"synthetic": "synthetic_vivid"}), ms.venues()["s13"]["look"])
        with self.assertRaises(ms.ModernSurfacesError):
            ms.venue_look("s26", {"synthetic": "grass_bermuda"})

    def test_the_table_is_canonical_json(self):
        text = ms.VENUES_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")


class ArtTests(unittest.TestCase):
    def test_every_detail_kind_loads_six_levels_and_one_palette(self):
        for kind in {look["detail"] for look in ms.LOOKS.values()}:
            levels, palette = ms.detail_art(kind)
            self.assertEqual([lv.shape for lv in levels], [(256 >> k, 512 >> k) for k in range(6)], kind)
            self.assertEqual(len(palette), 1024)
            tiles, tile_palette = ms.detail_tile_art(kind)
            self.assertEqual(len(tiles), 3)
            for tile in tiles:
                self.assertEqual([t.shape for t in tile], [(64 >> k, 64 >> k) for k in range(6)], kind)
            self.assertEqual(tile_palette, palette)
            self.assertEqual(len(ms.detail_video(kind)), 175_744)
            self.assertEqual(len(ms.detail_video(kind, tiled=True)), 175_744)

    def test_the_blades_live_in_the_alpha_and_fade_with_distance(self):
        import numpy as np
        for kind in {look["detail"] for look in ms.LOOKS.values()}:
            levels, palette = ms.detail_art(kind)
            bgra = np.frombuffer(palette, np.uint8).reshape(256, 4)
            self.assertTrue(np.all(bgra[:, :3] == (255, 128, 128)), kind)           # one flat normal
            self.assertEqual(bgra[:, 3].tolist(), list(range(256)))                  # alpha = the index
            mean = ms.DETAIL_ALPHA[kind]
            want = ms.detail_rel(kind)
            spread = []
            for k, lv in enumerate(levels):
                a = lv.astype(np.float64)
                self.assertAlmostEqual(float(a.mean()), mean, delta=0.5, msg=kind)   # the measured brightness kept
                spread.append(float(a.std() / a.mean()))
                self.assertAlmostEqual(spread[-1], want[k], delta=0.03 * want[k] + 0.0005, msg=(kind, k, spread))
            # tf-v4 at Noah's strengths: up close well under tf-v3's gravel (0.225 at mip 0), and the far mips the
            # play camera samples (2 to 5) keep about twice tf-v3.1's grain
            self.assertLess(spread[0], 0.11, kind)
            self.assertLess(spread[0], ms.GRAVEL_REL / 2, kind)
            self.assertTrue(all(x > y for x, y in zip(spread, spread[1:])), (kind, spread))
            for k in (2, 3, 4, 5):
                self.assertGreater(spread[k], 1.25 * ms.DETAIL_REL_ANCHOR[kind][k], (kind, k, spread))
            a = levels[0].astype(np.float64) - levels[0].mean()
            lag3 = float((a * np.roll(a, 3, 1)).mean() / (a * a).mean())
            self.assertLess(abs(lag3), 0.2, kind)      # short-range: the per-triangle UV seams stay invisible

    def test_every_level_keeps_its_structure_short_at_full_strength(self):
        # gr2's lattice guard: each premipped level carries its own short clumps, never long strokes boxed down from
        # mip 0 (a long structure draws E_detail's triangle lattice); lag-2 autocorrelation under 0.35 on both axes
        import numpy as np
        for kind in ms.DETAIL_ALPHA:
            full = [ms.detail_art(kind, 1.0)[0]] + [list(t) for t in ms.detail_tile_art(kind, 1.0)[0]]
            for levels in full:
                for k, lv in enumerate(levels):
                    if min(lv.shape) < 16:                 # an 8-texel tile level is too small to measure
                        continue
                    a = lv.astype(np.float64) - lv.mean()
                    for axis in (0, 1):
                        lag2 = float((a * np.roll(a, 2, axis)).mean() / (a * a).mean())
                        self.assertLess(lag2, 0.35, (kind, k, axis))

    def test_the_strength_runs_from_tf_v3_1_to_candidate_a(self):
        self.assertEqual(ms.DETAIL_STRENGTH, {"synthetic": 0.15, "grass": 0.20})          # Noah, 2026-10-16
        self.assertEqual(ms.detail_rel("fibre", 0.0), ms.DETAIL_REL_ANCHOR["fibre"])
        self.assertEqual(ms.detail_rel("blade_bermuda", 1.0), ms.DETAIL_REL_FULL)
        for kind, family in ms.DETAIL_FAMILY.items():
            t = ms.DETAIL_STRENGTH[family]
            for got, a, f in zip(ms.detail_rel(kind), ms.DETAIL_REL_ANCHOR[kind], ms.DETAIL_REL_FULL):
                self.assertAlmostEqual(got, a + t * (f - a), places=12)
            self.assertEqual(ms.strength_percent(kind, {family: 0.5}), 50)
            self.assertEqual(ms.strength_percent(kind), round(100 * t))
            levels, _ = ms.detail_art(kind, 0.0)
            for k, lv in enumerate(levels):                                               # 0 % is tf-v3.1's calm
                self.assertAlmostEqual(float(lv.std() / lv.mean()), ms.DETAIL_REL_ANCHOR[kind][k],
                                       delta=0.0006 + 0.02 * ms.DETAIL_REL_ANCHOR[kind][k], msg=(kind, k))
            full, _ = ms.detail_art(kind, 1.0)
            self.assertTrue(all(a is b for a, b in zip(full, ms._full_detail_art(kind)[0])))   # 100 % = the PNG
        # whole bytes per strength, the same on every call (integer scaling), and a different video per strength
        self.assertEqual(ms.detail_video("fibre"), ms._detail_video.__wrapped__("fibre", False, 15))
        self.assertNotEqual(ms.detail_video("fibre", strength=0.35), ms.detail_video("fibre"))
        for bad in (-0.1, 1.5, 0.155, True, "0.2"):
            with self.assertRaises(ms.ModernSurfacesError, msg=bad):
                ms.strength_percent("fibre", bad)

    def test_v0_6_1_normals_and_other_strengths_keep_reading_as_this_option(self):
        # tf-v3.1's eight videos (v0.6 and v0.6.1) stay signatures; a receipt that chose another strength adds its own
        legacy = {row for row in ms.LEGACY_DETAIL_SHA256.values()}
        self.assertEqual(len(ms.LEGACY_DETAIL_SHA256), 24)
        self.assertEqual(legacy, {(k, v) for k in ms.DETAIL_ALPHA for v in ("full", "tiled")})
        self.assertEqual(ms.LEGACY_DETAIL_SHA256["54b17f691baed3947e9dd81494185623eb62c28798e26092ccab1474d06d6e80"],
                         ("blade_bermuda", "full"))
        known = ms._detail_by_hash()
        self.assertEqual(known[hashlib.sha256(ms.detail_video("fibre")).hexdigest()], ("fibre", "full"))
        other = hashlib.sha256(ms.detail_video("blade_bermuda", strength=0.35)).hexdigest()
        self.assertNotIn(other, known)
        receipt = dict(detail_strength={"grass": 0.35, "synthetic": 0.15})
        self.assertEqual(ms._detail_by_hash_at(ms._receipt_strengths(receipt))[other], ("blade_bermuda", "full"))
        self.assertIs(ms._receipt_strengths(dict(detail_strength=None)), None)

    def test_the_three_tiles_repeat_every_third_swizzled_block(self):
        import numpy as np
        tx, HEADER = ms._tools()
        video = ms.detail_video("fibre", tiled=True)
        level0 = video[:131072]
        blocks = [level0[k * 4096:(k + 1) * 4096] for k in range(32)]
        for k in range(3, 32):
            self.assertEqual(blocks[k], blocks[k - 3], k)
        self.assertEqual(len({blocks[0], blocks[1], blocks[2]}), 3)
        self.assertEqual(sorted({t for row in ms.TILE_GRID for t in row}), [0, 1, 2])

    def test_patterns_centre_on_the_mean_and_keep_one_period(self):
        import numpy as np
        for look in ms.LOOKS:
            pat = ms.pattern_art(look)
            self.assertEqual(pat["map"].shape, (64, 128))
            self.assertEqual(pat["map_square"].shape, (128, 128))
            self.assertEqual(pat["outside"].shape, (128, 128))
            for key in ("map", "map_square", "outside"):
                self.assertAlmostEqual(float(pat[key].mean()), 1.0, delta=0.02, msg=(look, key))
            self.assertTrue(np.all(ms.pattern_level(look, "map", 0) == 1.0))
            self.assertEqual(len(np.unique(ms.pattern_level(look, "map", 1))), 2)

    def test_band_looks_put_the_bands_along_the_field(self):
        import numpy as np
        for look in ("synthetic_fieldturf", "grass_bermuda"):
            cols = ms.pattern_art(look)["map"].mean(0)          # u runs along the field
            self.assertGreater(cols[:64].mean() - cols[64:].mean(), 0.05, look)


class ColourTests(unittest.TestCase):
    def test_light_classes_follow_the_engine_rig_selection(self):
        self.assertEqual(ms.light_class("s13dd.iff", False), "day")
        self.assertEqual(ms.light_class("s13ad.iff", False), "afternoon")
        self.assertEqual(ms.light_class("s13nd.iff", False), "night")
        self.assertEqual(ms.light_class("s13nr.iff", False), "rain")
        self.assertEqual(ms.light_class("s13ds.iff", False), "snow")
        self.assertEqual(ms.light_class("s23ad.iff", True), "dome")
        self.assertEqual(ms.rig_name("dome", "a"), "night_indoor")

    def test_the_solved_map_draws_the_broadcast_target_under_modern_colour(self):
        from mod_editor.core import nfl2k5_modern_color as colour
        settings = colour.normalize_settings({})
        for look in ("synthetic_fieldturf", "grass_bermuda"):
            for cls, rig in (("night", "night_indoor"), ("dome", "night_indoor"), ("day", "day")):
                for layout in ("grid", "quad"):
                    response = ms.field_response(look, cls, layout)
                    mean = ms.solve_map_mean(look, cls, rig, colour_settings=settings, response=response)
                    self._drawn_on_target(look, cls, rig, settings, mean, response)

    def _drawn_on_target(self, look, cls, rig, settings, mean, response):
        self.assertLessEqual(max(mean), ms.MAP_CEILING + 1e-6)
        shown = [m * g * f * response for m, g, f in zip(mean, ms.rig_gain(rig, settings), ms.screen_factor(rig))]
        target = ms.target_rgb(look, cls)
        if max(mean) < ms.MAP_CEILING - 1e-6:
            for a, b in zip(shown, target):
                self.assertAlmostEqual(a, b, delta=1.0, msg=(look, cls))
        else:   # green ceiling: the hue is kept
            self.assertAlmostEqual(_hsv(shown)[0], _hsv(target)[0], delta=6, msg=(look, cls))

    def test_the_game_response_tables_follow_the_lab(self):
        for kind, table in ms.FIELD_RESPONSE.items():
            self.assertEqual(set(table), {"day", "afternoon", "night", "dome"}, kind)
            self.assertTrue(table["night"] < table["afternoon"] < table["day"], kind)
        for look in ms.LOOKS:
            for cls in ms.LIGHT_CLASSES:
                self.assertGreater(ms.field_response(look, cls, "quad"), ms.field_response(look, cls, "grid"))
        # the lab: fibre and helix draw brighter over the model than the blades, and a quad 1.07 x a grid
        self.assertGreater(ms.field_response("synthetic_fieldturf", "night"), ms.field_response("grass_bermuda", "night") + 0.1)
        self.assertAlmostEqual(ms.field_response("grass_bluegrass", "day", "quad"), 1.16, delta=0.01)
        self.assertAlmostEqual(ms.field_response("synthetic_fieldturf", "night", "quad"), 1.25, delta=0.01)
        for cls in ms.LIGHT_CLASSES:
            response = ms.apron_response(cls)
            self.assertTrue(all(1.8 < r < 2.3 for r in response), cls)

    def test_the_apron_draws_the_field_colour_a_touch_darker(self):
        from mod_editor.core import nfl2k5_modern_color as colour
        settings = colour.normalize_settings({})
        for look in ms.LOOKS:
            for cls, rig in (("day", "day"), ("night", "night_indoor"), ("dome", "night_indoor"), ("afternoon", "afternoon")):
                target = ms.target_rgb(look, cls)
                mean = ms.solve_outside_mean(look, cls, rig, colour_settings=settings, vertex=(246, 246, 246))
                shown = [m * g * f * (246 / 255) * r for m, g, f, r in
                         zip(mean, ms.rig_gain(rig, settings), ms.screen_factor(rig), ms.apron_response(cls))]
                if max(mean) < ms.MAP_CEILING - 1e-6:
                    for a, b in zip(shown, target):
                        self.assertAlmostEqual(a, b * ms.OUTSIDE_SHADE, delta=1.0, msg=(look, cls))
                self.assertAlmostEqual(_hsv(shown)[0], _hsv(target)[0], delta=2, msg=(look, cls))   # no lime apron

    def test_a_venue_with_its_own_broadcast_lands_on_it(self):
        # turf: the look's targets are the broadcast medians, and a venue's own broadcast is met exactly
        measured = {p: row["broadcast"] for p, row in ms.venues().items() if row.get("broadcast")}
        self.assertGreaterEqual(len(measured), 12)
        for prefix, seen in measured.items():
            self.assertIn("frames", seen["source"])
            look = ms.venue_look(prefix)
            aim = ms.venues()[prefix].get("design") or seen     # a design target replaces the measurement (Allegiant)
            got = ms.venue_target(prefix, look, aim["light"])
            if ms.LOOKS[look]["family"] == "synthetic" or ms.venues()[prefix].get("design"):
                for a, b in zip(got, aim["rgb"]):
                    self.assertAlmostEqual(a, b, delta=0.01, msg=prefix)
        self.assertEqual(ms.venue_target("s03", "grass_bluegrass", "day"), ms.target_rgb("grass_bluegrass", "day"))

    def test_a_grass_venue_keeps_its_character_at_the_deep_level(self):
        # tf-v4: a grass venue's broadcast over the look's measured median, at unit luminance and a capped hue turn
        import colorsys
        luma = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        hue = lambda c: colorsys.rgb_to_hsv(*c)[0] * 360
        grass = [p for p, row in ms.venues().items() if row.get("broadcast") and not row.get("design")
                 and row["surface"] == "grass"]
        self.assertEqual(sorted(grass), ["s12", "s13", "s21", "s22"])
        for prefix in grass:
            look, seen = ms.venue_look(prefix), ms.venues()[prefix]["broadcast"]
            for cls in ("day", "afternoon", "night", "dome", "rain"):
                got, base = ms.venue_target(prefix, look, cls), ms.target_rgb(look, cls)
                self.assertAlmostEqual(luma(got), luma(base), delta=0.01, msg=(prefix, cls))
                self.assertLessEqual(abs(hue(got) - hue(base)), ms.VENUE_HUE_CAP + 1e-6, (prefix, cls))
            # its character: the per-channel ratio of its broadcast to the look's measured median at that light
            ratio = [m / b for m, b in zip(seen["rgb"], ms.broadcast_rgb(look, seen["light"]))]
            for cls in ("day", "night"):
                base = ms.target_rgb(look, cls)
                raw = [t * k for t, k in zip(base, ratio)]
                if abs(hue(raw) - hue(base)) <= ms.VENUE_HUE_CAP:
                    want = [v * luma(base) / luma(raw) for v in raw]
                    for a, b in zip(ms.venue_target(prefix, look, cls), want):
                        self.assertAlmostEqual(a, b, delta=1e-6, msg=(prefix, cls))

    def test_grass_lands_on_nohas_pick_after_broadcast_greens(self):
        from mod_editor.core import nfl2k5_broadcast_greens as greens
        luma = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        self.assertEqual(set(greens.GRASS_GAIN), {ms.GR1_GRASS_GAIN})
        day = [v * ms.GR1_GRASS_GAIN for v in ms.target_rgb("grass_bermuda", "day")]
        for a, b in zip(day, ms.GRASS_DAY_ON_SCREEN):
            self.assertAlmostEqual(a, b, delta=0.1)
        for look in ("grass_bluegrass", "grass_checker"):
            self.assertAlmostEqual(luma(ms.target_rgb(look, "day")), luma(ms.target_rgb("grass_bermuda", "day")), delta=0.1)
        for look, row in ms.LOOKS.items():
            if row["family"] == "synthetic":                       # turf unchanged: gr1 lands it on tonight's turf
                self.assertNotIn("broadcast", row, look)
                continue
            for cls in ("day", "afternoon", "night", "dome"):     # every other light keeps its measured ratio to day
                for t, d, b, bd in zip(row["targets"][cls], row["targets"]["day"], row["broadcast"][cls],
                                       row["broadcast"]["day"]):
                    self.assertAlmostEqual(t / d, b / bd, delta=0.002, msg=(look, cls))
                self.assertLess(luma(row["targets"][cls]) * ms.GR1_GRASS_GAIN, 0.85 * luma(row["broadcast"][cls]),
                                (look, cls))                       # deeper on screen than the bright medians

    def test_only_allegiant_has_a_design_target_and_it_is_darker_and_cooler_than_its_broadcast(self):
        import colorsys
        designed = {p: row["design"] for p, row in ms.venues().items() if row.get("design")}
        self.assertEqual(sorted(designed), ["s20"])        # Beta 77 ALG pass 4; every other venue keeps its measurement
        seen, aim = ms.venues()["s20"]["broadcast"], designed["s20"]
        self.assertEqual((aim["light"], seen["light"]), ("dome", "dome"))
        luma = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        hue = lambda c: colorsys.rgb_to_hsv(*(v / 255 for v in c))[0] * 360
        self.assertLess(luma(aim["rgb"]), luma(seen["rgb"]) * 0.92)
        self.assertGreater(hue(aim["rgb"]), hue(seen["rgb"]) + 2)
        self.assertLess(hue(aim["rgb"]), 100)               # a natural green, not a blue-green
        # the other lights follow the same per-channel ratio to the look, and every other venue still follows its measurement
        look = ms.venue_look("s20")
        for cls in ("day", "afternoon", "night"):
            got = ms.venue_target("s20", look, cls)
            want = [t * (m / b) for t, m, b in zip(ms.target_rgb(look, cls), aim["rgb"], ms.target_rgb(look, "dome"))]
            for a, b in zip(got, want):
                self.assertAlmostEqual(a, b, delta=0.01)
        for prefix, row in ms.venues().items():
            if prefix == "s20" or row["surface"] == "grass":    # grass venues: see the deep-level character test
                continue
            look = ms.venue_look(prefix)
            for cls in ("day", "night", "dome"):
                base = ms.target_rgb(look, cls)
                if row.get("broadcast"):
                    ref = ms.target_rgb(look, row["broadcast"]["light"])
                    base = tuple(t * (m / b) for t, m, b in zip(base, row["broadcast"]["rgb"], ref))
                self.assertEqual(tuple(ms.venue_target(prefix, look, cls)), tuple(base), (prefix, cls))

    def test_a_design_target_needs_a_light_an_rgb_and_a_source(self):
        import tempfile
        doc = json.loads(ms.VENUES_PATH.read_text(encoding="utf-8"))
        row = next(r for r in doc["venues"] if r["prefix"] == "s20")
        good, original = dict(row["design"]), ms.VENUES_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                for broken in (dict(good, light="midnight"), dict(good, rgb=[1, 2]), dict(good, source="")):
                    row["design"] = broken
                    path = Path(tmp) / "venues.json"
                    path.write_text(json.dumps(doc), encoding="utf-8")
                    ms.VENUES_PATH = path
                    ms.venues.cache_clear()
                    with self.assertRaises(ms.ModernSurfacesError):
                        ms.venues()
        finally:
            ms.VENUES_PATH = original
            ms.venues.cache_clear()
        self.assertEqual(ms.venues()["s20"]["design"], good)

    def test_maps_stay_green_under_the_warm_retail_rigs(self):
        for look in ms.LOOKS:
            for cls in ("day", "afternoon", "rain"):
                r, g, b = ms.solve_map_mean(look, cls, ms.rig_name(cls, "d"), tint=(255, 238, 205), vertex=(255, 238, 205))
                self.assertLessEqual(r, ms.MAP_RED_OVER_GREEN * g + 1e-6)
                self.assertLessEqual(b, ms.MAP_BLUE_OVER_GREEN * g + 1e-6)

    def test_end_zone_recolour_takes_turf_and_leaves_paint(self):
        turf = [(100, 125, 66), (90, 115, 60), (110, 132, 72), (96, 120, 63)]
        env = ms.turf_envelope(turf)
        paint = [(255, 209, 0), (32, 55, 49), (255, 255, 255), (0, 53, 148), (18, 87, 64), (0, 76, 84)]
        entries = turf + paint + [(0, 0, 0)] * (256 - len(turf) - len(paint))
        palette = b"".join(bytes((b, g, r, 255)) for r, g, b in entries)
        new, changed = ms.recolour_end_zone_palette(palette, env, (99, 123, 65), (150, 190, 120))
        self.assertEqual(changed, len(turf))
        for i, rgb in enumerate(entries[:len(turf) + len(paint)]):
            b, g, r, a = new[i * 4:i * 4 + 4]
            if i < len(turf):
                self.assertGreater(g, rgb[1])
            else:
                self.assertEqual((r, g, b), rgb, rgb)


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class RetailBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_roster_records as rr
        pins = {row["name"]: row for row in ms.pins()["bundles"]}
        cls.bundles = {}
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        with rr._outer_image()(PACKS) as archive:
            for name in ("s10dd.iff", "s26dd.iff", "s28nd.iff", "s11dd.iff"):
                entry = archive.entries[pins[name]["outer"]]
                cls.bundles[name] = archive.read(entry.virtual_offset, entry.size)
        cls.pins = pins

    def _uvs(self, data, material):
        ml = ms._ml()
        tx, HEADER = ms._tools()
        at, size = ms.bundle_sites(data)["field"]
        span = bytes(data[at:at + size])
        chunk = tx.parse_chunks(span, allow_trailing=True)[0]
        rec, dec = ml._scene(span, chunk)
        shape = ms._shape(rec, ms.COLOUR_SHAPE)
        su, sv, ou, ov = struct.unpack_from("<4f", dec, shape["record_offset"] + 0x30)
        a0, st0 = ms._stream(shape, 0)
        a6, st6 = ms._stream(shape, 6)
        out = {}
        for i in ms._submesh_vertices(rec, dec, shape, material):
            x, _y, z = struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i + a0["byte_offset"])
            qu, qv = struct.unpack_from("<2h", dec, st6["offset"] + st6["stride"] * i + a6["byte_offset"])
            out[i] = ((x, z), (qu / 32767 * su + ou, qv / 32767 * sv + ov))
        return out

    def test_the_pins_match_the_retail_packs_and_the_shipped_art(self):
        for name, data in self.bundles.items():
            pin = self.pins[name]
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin["retail_sha256"], name)
            for kind, (at, size) in ms.bundle_sites(data).items():
                site = pin["sites"][kind]
                self.assertEqual((at, size), (site["offset"], site["size"]), (name, kind))
        details = ms.pins()["details"]
        for kind, row in details.items():
            self.assertEqual(hashlib.sha256(ms.detail_video(kind)).hexdigest(), row["full"], kind)
            self.assertEqual(hashlib.sha256(ms.detail_video(kind, tiled=True)).hexdigest(), row["tiled"], kind)

    def test_a_grid_field_refits_with_planar_uvs_and_unmoved_end_zones(self):
        data = self.bundles["s10dd.iff"]
        out, rec = ms.surface_bundle(data, "s10dd.iff", indoor=False)
        self.assertEqual(len(out), len(data))
        sites = ms.bundle_sites(data)
        changed = {e["kind"] for e in rec["edits"]}
        self.assertEqual(changed, {"field", "normal", "divots"})     # grass: no wear-colour write
        self.assertEqual(rec["field"]["layout"], "grid")
        self.assertAlmostEqual(rec["field"]["response"], ms.field_response("grass_bluegrass", "day", "grid"))
        for kind, (at, size) in sites.items():
            if kind not in changed:
                self.assertEqual(out[at:at + size], data[at:at + size], kind)
        at, size = sites["field"]
        self.assertEqual(out[at:at + 32], data[at:at + 32])            # the retail wrapper, scratch word included
        mask = bytearray(len(data))
        for at, size in sites.values():
            mask[at:at + size] = b"\x01" * size
        self.assertTrue(all(a == b for a, b, m in zip(out, data, mask) if not m))
        for (x, z), (u, v) in self._uvs(out, ms.COLOUR_MATERIAL).values():
            self.assertAlmostEqual(u, (ms.GOAL_Z - z / 100) / ms.PERIOD, delta=1 / 2048)
            self.assertAlmostEqual(v, (x / 100 + ms.HALF_WIDTH) / ms.PERIOD, delta=1 / 2048)
        for part in ("endzone_N_L", "endzone_S_R"):
            before, after = self._uvs(data, part), self._uvs(out, part)
            self.assertEqual(set(before), set(after))
            for i in before:
                for a, b in zip(before[i][1], after[i][1]):
                    self.assertAlmostEqual(a, b, delta=1 / 2048)
        self.assertEqual(ms.surface_bundle(out, "s10dd.iff", indoor=False)[0], out)   # idempotent

    def test_a_material_only_field_borrows_the_outside_texture(self):
        data = self.bundles["s26dd.iff"]
        out, rec = ms.surface_bundle(data, "s26dd.iff", indoor=False)
        self.assertTrue(rec["field"]["colour_map"].startswith("borrowed"))
        self.assertEqual(rec["field"]["layout"], "quad")
        self.assertAlmostEqual(rec["field"]["response"], ms.field_response("synthetic_fieldturf", "day", "quad"))
        self.assertEqual(rec["field"]["target"], [round(v, 2) for v in ms.venue_target("s26", "synthetic_fieldturf", "day")])
        self.assertEqual(rec["field"]["outside"], "plain colour")
        ml = ms._ml()
        tx, HEADER = ms._tools()
        at, size = ms.bundle_sites(out)["field"]
        span = bytes(out[at:at + size])
        chunk = tx.parse_chunks(span, allow_trailing=True)[0]
        scene, dec = ml._scene(span, chunk)
        self.assertTrue(ms.borrowed(dec, scene))
        self.assertTrue(ms.surfaced(dec, scene))
        self.assertEqual(ms.surface_bundle(out, "s26dd.iff", indoor=False)[0], out)
        # a quad is sampled clamped: the whole field lies inside 0..1, goal line to goal line between the margins
        uvs = self._uvs(out, ms.COLOUR_MATERIAL)
        self.assertEqual(len(uvs), 4)
        for (x, z), (u, v) in uvs.values():
            self.assertAlmostEqual(u, 4 / 128 + (ms.GOAL_Z - z / 100) / (2 * ms.GOAL_Z) * 120 / 128, delta=1 / 4096)
            self.assertTrue(0.0 < u < 1.0 and 0.0 < v < 1.0)
        for part in ("endzone_N_L", "endzone_S_R"):
            before, after = self._uvs(data, part), self._uvs(out, part)
            for i in before:
                for a, b in zip(before[i][1], after[i][1]):
                    self.assertAlmostEqual(a, b, delta=1 / 2048)

    def test_a_quad_pattern_lays_twenty_five_yard_bands(self):
        import numpy as np
        for look in ("synthetic_fieldturf", "grass_bluegrass"):
            pat = ms.quad_pattern(look, (128, 64), detail=1)
            row = pat[32]
            tones = [float(row[4 + 6 * k: 10 + 6 * k].mean()) for k in range(20)]
            for k in range(19):
                self.assertNotAlmostEqual(tones[k], tones[k + 1], delta=0.01)
                self.assertEqual(tones[k] > tones[k + 1], k % 2 == 0)
            self.assertTrue(np.all(row[:4] == row[4]) and np.all(row[124:] == row[123]))

    def test_synthetic_turf_hides_divots_and_tints_wear(self):
        data = self.bundles["s28nd.iff"]
        out, rec = ms.surface_bundle(data, "s28nd.iff", indoor=False)
        self.assertEqual(rec["family"], "synthetic")
        tx, HEADER = ms._tools()
        at, size = ms.bundle_sites(out)["divots"]
        span = bytes(out[at:at + size])
        chunk = tx.parse_chunks(span, allow_trailing=True)[0]
        dec, _ = tx.decode_chunk(span, chunk)
        info = tx.parse_texture(dec, chunk)
        pal = dec[chunk.system_bytes + info.palette_offset:][:1024]
        self.assertTrue(all(pal[i * 4 + 3] == 0 for i in range(256)))
        fat, _ = ms.bundle_sites(out)["fldd"]
        self.assertEqual(struct.unpack_from("<I", out, fat + 4)[0], ms.SYNTHETIC_WEAR)
        self.assertEqual(struct.unpack_from("<I", out, fat + 8)[0], struct.unpack_from("<I", data, fat + 8)[0])

    def test_a_compressed_detail_normal_takes_the_tiled_art(self):
        data = self.bundles["s11dd.iff"]
        out, rec = ms.surface_bundle(data, "s11dd.iff", indoor=True)
        self.assertEqual(rec["normal"], "tiled")
        self.assertEqual(rec["light"], "dome")
        tx, HEADER = ms._tools()
        at, size = ms.bundle_sites(out)["normal"]
        span = bytes(out[at:at + size])
        chunk = tx.parse_chunks(span, allow_trailing=True)[0]
        self.assertEqual(span[:32], data[at:at + 32])
        dec, _ = tx.decode_chunk(span, chunk)
        self.assertEqual(dec[chunk.system_bytes:], ms.detail_video("helix", tiled=True))


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class LoanVenueTests(unittest.TestCase):
    """tf-v4 (gr3): the four venues whose detail normal lends allocation to the field take the TILED art, compressed
    into exactly the loan the v0.6.1 disc carries, so every field span keeps its proven size."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_roster_records as rr
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        pins = {row["name"]: row for row in ms.pins()["bundles"]}
        cls.normals = {}
        with rr._outer_image()(PACKS) as archive:
            for prefix in sorted(ms.LOAN_NORMAL_VENUES):
                entry = archive.entries[pins[prefix + "dd.iff"]["outer"]]
                data = archive.read(entry.virtual_offset, entry.size)
                at, size = ms.bundle_sites(data)["normal"]
                cls.normals[prefix] = bytes(data[at:at + size])

    def test_every_loan_venue_holds_the_tiled_art_in_its_reviewed_loan(self):
        from mod_editor.core import nfl2k5_midfield_art as mf
        tx, HEADER = ms._tools()
        self.assertEqual(set(mf.TILED_NORMAL_LOANS), set(ms.LOAN_NORMAL_VENUES))
        stored = {"s09": 155280, "s22": 149664, "s29": 174192, "s30": 146880}      # the v0.6.1 disc's spans
        for prefix, raw in self.normals.items():
            kind = ms.LOOKS[ms.venue_look(prefix)]["detail"]
            tiled, variant = ms.normal_span(raw, kind, variant="tiled")
            self.assertEqual((variant, len(tiled)), ("tiled", len(raw)), prefix)
            chunk = tx.parse_chunks(tiled)[0]
            decoded, _ = tx.decode_chunk(tiled, chunk)
            self.assertEqual(decoded[chunk.system_bytes:], ms.detail_video(kind, tiled=True), prefix)
            self.assertTrue(ms.tiled_video(decoded[chunk.system_bytes:]))
            self.assertEqual(mf.normal_loan(prefix, tiled), mf.TILED_NORMAL_LOANS[prefix])
            self.assertIsNone(mf.normal_loan(prefix, ms.normal_span(raw, kind)[0]))   # the full art: the old route
            compressed, loan = mf.compress_detail_normal(tiled, loan_bytes=mf.normal_loan(prefix, tiled))
            self.assertEqual((loan["stored"], loan["scratch"], loan["alias_scratch"], loan["tiled"]),
                             (stored[prefix], 0, 0, True), prefix)
            self.assertEqual(len(compressed), HEADER.size + stored[prefix])
            back, _ = tx.decode_chunk(compressed, tx.parse_chunks(compressed)[0])
            self.assertEqual(back, decoded, prefix)
            tx.check_vc_lz_native(compressed[HEADER.size:], stored[prefix], 0, decoded)
            kept, kept_variant = ms.normal_span(compressed, kind, preserve_full=True)     # the final pass keeps it
            self.assertEqual((kept, kept_variant), (compressed, "tiled"), prefix)

    def test_only_loan_venues_take_a_tiled_raw_normal(self):
        with self.assertRaisesRegex(ms.ModernSurfacesError, "not reviewed for s13"):
            ms.surface_bundle(b"unparsed", "s13dd.iff", indoor=False, tiled_normal=True)
        with self.assertRaisesRegex(ms.ModernSurfacesError, "unreviewed venue"):
            ms.apply_to_image("/nonexistent.iso", tiled_normal_prefixes=("s13",))

    def test_the_worker_passes_the_tiled_loan_and_the_strength(self):
        from unittest import mock
        with mock.patch.object(ms, "surface_bundle", return_value=(b"after", {})) as writer:
            ms._job(("s22dd.iff", b"before", False, None, None, False, False, True))
            writer.assert_called_once_with(b"before", "s22dd.iff", indoor=False, colour_settings=None,
                                           overrides=None, tiled_normal=True)
        with mock.patch.object(ms, "surface_bundle", return_value=(b"after", {})) as writer:
            ms._job(("s13dd.iff", b"before", False, None, None, False, False, False, {"grass": 0.35}))
            writer.assert_called_once_with(b"before", "s13dd.iff", indoor=False, colour_settings=None,
                                           overrides=None, detail_strength={"grass": 0.35})


class ReleaseTests(unittest.TestCase):
    def test_every_art_png_is_reviewed_and_allowlisted(self):
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted(ms.ART_DIR.glob("*.png"))
        self.assertEqual(len(pngs), 14)
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            with Image.open(png) as image:
                self.assertEqual((row["width"], row["height"]), image.size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_modern_surfaces.py", "data/nfl2k5_modern_surfaces/venues.json",
                    "data/nfl2k5_modern_surfaces/pins.json", "data/nfl2k5_modern_surfaces/art/art.json"):
            self.assertIn(rel, allow)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"', checker)

    def test_pins_are_canonical_json(self):
        text = ms.PINS_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")


class _Entry:
    def __init__(self, size):
        self.virtual_offset, self.size = 0, size


class _Archive:
    """One bundle as an archive: read(offset, size) over its bytes."""
    def __init__(self, data):
        self.data = bytes(data)

    def read(self, offset, size):
        return self.data[offset:offset + size]


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class StatusTests(unittest.TestCase):
    """The status reads the receipt, and without it (a disc published without its sidecar, the 2026-09-25 lab 1
    refusal) or after a later writer changed other chunks, this option's own signature."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_roster_records as rr
        pins = {row["name"]: row for row in ms.pins()["bundles"]}
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        with rr._outer_image()(PACKS) as archive:
            entry = archive.entries[pins["s10dd.iff"]["outer"]]
            cls.retail = archive.read(entry.virtual_offset, entry.size)
            entry = archive.entries[pins["s11dd.iff"]["outer"]]
            cls.retail11 = archive.read(entry.virtual_offset, entry.size)
        cls.out, cls.rec = ms.surface_bundle(cls.retail, "s10dd.iff", indoor=False)
        cls.out11, cls.rec11 = ms.surface_bundle(cls.retail11, "s11dd.iff", indoor=True)
        cls.receipt = dict(bundles={"s10dd.iff": dict(applied_sha256=hashlib.sha256(cls.out).hexdigest(),
                                                       edits=cls.rec["edits"])})

    def report(self, data, receipt=None, name="s10dd.iff", deep=False):
        return ms.bundle_report(_Archive(data), name, _Entry(len(data)), receipt, deep=deep)

    def test_the_receipt_reads_applied(self):
        self.assertEqual(self.report(self.out, self.receipt), dict(state="applied", reason="receipt"))

    def test_without_the_receipt_the_signature_reads_applied(self):
        row = self.report(self.out, None, deep=True)
        self.assertEqual(row["state"], "applied", row)
        self.assertIn("no receipt row", row["reason"])
        row = self.report(self.out11, None, name="s11dd.iff", deep=True)   # the compressed, tiled detail normal
        self.assertEqual(row["state"], "applied", row)
        self.assertIn("tiled", row["reason"])

    def test_a_later_writer_outside_the_surface_keeps_it_applied(self):
        changed = bytearray(self.out)
        sites = ms.bundle_sites(self.out)
        end = max(at + size for at, size in sites.values())
        changed[end + 100] ^= 0xFF                          # a byte of a later chunk (the stadium, the sky ...)
        row = self.report(bytes(changed), self.receipt, deep=True)
        self.assertEqual(row["state"], "applied", row)
        self.assertIn("outside its sites", row["reason"])

    def test_a_field_rebuilt_from_retail_is_caught_by_the_deep_status(self):
        rebuilt = bytearray(self.out)
        at, size = ms.bundle_sites(self.out)["field"]
        rebuilt[at:at + size] = self.retail[at:at + size]
        self.assertEqual(self.report(bytes(rebuilt), self.receipt)["state"], "applied")        # fast: the signature
        row = self.report(bytes(rebuilt), self.receipt, deep=True)
        self.assertEqual(row["state"], "foreign", row)
        self.assertIn("lost the planar colour UVs", row["reason"])

    def test_retail_and_foreign_bundles(self):
        self.assertEqual(self.report(self.retail)["state"], "retail")
        self.assertEqual(self.report(self.retail, self.receipt)["state"], "foreign")
        other = bytearray(self.retail)
        at, size = ms.bundle_sites(self.retail)["normal"]
        other[at + size - 2000] ^= 0x55                      # a detail normal another writer changed
        self.assertEqual(self.report(bytes(other))["state"], "retail")          # not surfaced: this step's input
        self.assertEqual(self.report(bytes(other), self.receipt)["state"], "foreign")

    def test_a_colour_graded_bundle_is_this_steps_input_and_reads_unsurfaced(self):
        # lab 2 (2026-09-25): Modern colour flattens every detail normal's palette before this step runs; the build
        # step refused its own input when that read as foreign
        from mod_editor.core import nfl2k5_modern_color as colour
        graded, _edits = colour.modern_bundle(self.retail)
        self.assertNotEqual(ms.bundle_sites(graded)["normal"], None)
        row = self.report(graded, None, deep=True)
        self.assertEqual(row["state"], "retail", row)
        self.assertIn("another writer", row["reason"])
        out, _rec = ms.surface_bundle(graded, "s10dd.iff", indoor=False, colour_settings=colour.normalize_settings({}))
        self.assertEqual(self.report(out, None, deep=True)["state"], "applied")

    def test_the_build_publishes_the_receipt_with_the_disc(self):
        import tempfile
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        self.assertIn("surfaces.save_receipt(target, surfaces_receipt)", source)
        with tempfile.TemporaryDirectory() as tmp:
            disc = Path(tmp) / "disc.iso"
            disc.write_bytes(b"")
            doc = dict(schema=ms.RECEIPT_SCHEMA, bundles={"s10dd.iff": dict(applied_sha256="0" * 64)})
            ms.save_receipt(disc, doc)
            self.assertEqual(ms.read_receipt(disc), doc)


class BuildWiringTests(unittest.TestCase):
    def test_the_option_is_off_in_every_preset_and_available(self):
        from mod_editor.core import mod_build
        self.assertIn("modern_surfaces", mod_build.BuildPlan.__dataclass_fields__)
        self.assertIs(mod_build.BuildPlan.__dataclass_fields__["modern_surfaces"].default, False)
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_surfaces"), False, name)
        self.assertIn("modern_surfaces", mod_build.availability())

    def test_the_saved_settings_carry_the_choice(self):
        from mod_editor.core import nfl2k5_build_settings as bs
        self.assertIn("modern_surfaces", bs.FEATURE_KEYS)


if __name__ == "__main__":
    unittest.main()
