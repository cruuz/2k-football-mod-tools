"""Allegiant Stadium model (st2): geometry, the roof and the lanai, the boards' feed crop, markers, cameras, the field
and the league cloths."""
import math
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_allegiant_model as lv  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = lv.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 30000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_field_wall_clears_the_sideline_props(self):
        """The wall stays outside the retail s20 sideline props (x -40.6 and, after the nudge, 46.4; z -68.7 and 57.3)."""
        loop = self.model.loop
        side = [lp for lp in loop if abs(lp.z) < 40]
        self.assertGreaterEqual(min(lp.x for lp in side if lp.x > 0), lv.PROP_LIMIT_X + 1.0)
        self.assertLessEqual(max(lp.x for lp in side if lp.x < 0), -41.5)
        end = [lp for lp in loop if abs(lp.x) < 12]
        self.assertGreaterEqual(min(lp.z for lp in end if lp.z > 0), 58.3)
        self.assertLessEqual(max(lp.z for lp in end if lp.z < 0), -69.5)

    def test_the_stacks_fit_inside_the_facade(self):
        """Every rim walk ends inside the OpenStreetMap facade outline."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in lv.footprint()["facade"]]
        for lp, sec in zip(self.model.loop, self.model.secs):
            if "rim" not in sec:
                continue
            x, _y, z = self.model.at(lp, sec["rim"][3], 0.0)
            self.assertTrue(sm._point_in_poly(x, z, ring), (round(x, 1), round(z, 1)))

    def test_the_roof_covers_the_bowl_and_the_lanai_reaches_it(self):
        """The fixed roof stays at least 2 m over every rim's top; the lanai's glass runs from the north club tier's walk
        up to its measured top on the outline's north curve, centred on the field axis, the header over it up to the
        roof's ring, the torch in front of it with its top where the 2022 photo puts it."""
        m = self.model
        for lp, sec in zip(m.loop, m.secs):
            x, _y, z = m.at(lp, sec["rim"][0], 0.0)
            self.assertGreater(m.roof_height(x, z), sec["rim"][2] + 2.0, (round(x, 1), round(z, 1)))
        la = m.lanai
        self.assertAlmostEqual(la["x0"], -la["x1"], places=6)
        self.assertLess(la["z"], -140.0)
        self.assertAlmostEqual(la["y1"], lv.PARAMS["lanai"]["glass_top"], places=6)
        self.assertTrue(24.0 < la["y0"] < 28.0, la["y0"])
        self.assertGreater(la["header"], la["y1"] + 8.0)
        self.assertAlmostEqual(la["roof"], m.roof_height(0.0, la["z"]) - 0.4, places=3)
        self.assertAlmostEqual(m.torch_top, lv.PARAMS["torch"]["top"], places=6)
        self.assertGreater(lv.PARAMS["torch"]["z"], la["z"])
        for lp, sec in zip(m.loop, m.secs):
            if m.lanai_zone(lp):
                self.assertNotIn("upper", sec)

    def test_the_measured_heights(self):
        """The heights the two solved photo poses measured: the lower bowl's ribbon near 16 to 17 m at both ends, the
        north club tier's top walk near 26 m, the upper decks' top rows in the side stands 54 to 60 m, the roof's ring
        from 60 m at the outline to 66 m, the drum's top 69 m (OSM: 69 m over the plaza's grade less the dome)."""
        m = self.model
        for key, want in (("N", (15.0, 17.5)), ("S", (15.5, 18.0))):
            lp = min(m.loop[:-1], key=lambda l_, k=key: (l_.nz - (1 if k == "S" else -1)) ** 2 + (l_.x / 30.0) ** 2)
            rib = m.section(lp)["ribbon"]
            self.assertTrue(want[0] < rib[2] < want[1], (key, rib))
        lp = min(m.loop[:-1], key=lambda l_: (l_.nz + 1) ** 2 + (l_.x / 30.0) ** 2)
        self.assertTrue(25.0 < m.section(lp)["rim"][2] < 27.0)
        for key in "WE":
            lp = min(m.loop[:-1], key=lambda l_, k=key: (l_.nx - (1 if k == "E" else -1)) ** 2 + (l_.z / 30.0) ** 2)
            top = m.section(lp)["upper"][-1][1]
            self.assertTrue(54.0 < top < 60.0, (key, top))
        q = lv.PARAMS["roof"]
        self.assertAlmostEqual(m.roof_height(0.0, -146.4), q["eave"], delta=0.5)
        self.assertAlmostEqual(q["ring_top"] + q["depth"], 69.0, places=6)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_seats_tower_and_trusses(self):
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"ag_seat_front", "ag_seat_mid", "ag_seat_back", "crowd", "ag_roof_under", "LIGHT_ag_lanai",
                         "ag_torch", "LIGHT_ag_flame", "LIGHT_ag_lights", "ag_facade", "LIGHT_ag_mesh", "LIGHT_ag_strip",
                         "ag_pyramid", "env_band"} <= mats)
        self.assertTrue(mats <= set(lv.MATERIALS) | {"crowd", "jumbo_tron"}, mats - set(lv.MATERIALS))

    def test_the_boards_show_the_feed_at_the_pictures_aspect(self):
        """Every board shows a crop of the 640 x 448 feed picture (u 0 to 0.625, v 0 to 0.875 of the render target) at the
        picture's own aspect, never stretched: the south board's middle between its stat panels, the north boards
        whole."""
        q = lv.PARAMS["boards"]
        for aspect in (q["south_w"] * q["feed"] / q["south_h"], q["north_w"] / q["north_h"]):
            (u0, u1), (v0, v1) = self.model.board_crop(aspect)
            self.assertGreaterEqual(u0, 0.0); self.assertLessEqual(u1, 0.625 + 1e-9)
            self.assertGreaterEqual(v0, 0.0); self.assertLessEqual(v1, 0.875 + 1e-9)
            self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), aspect, places=3)
        feeds = [strip for m in self.model.meshes.values() for strip in m.groups.get("jumbo_tron", ())]
        self.assertEqual(len(feeds), 3)

    def test_the_boards_stand_at_the_ends(self):
        """The south board over the south end on the field axis, facing north; the north pair over the corner seats at
        their measured places, mirror images, each turned in toward the field; no seat reaches up into a board, and the
        wall behind each top walk stands behind the boards over it."""
        (south,) = self.model.board_frames
        self.assertGreater(float(south["centre"][2]), 100.0)
        self.assertAlmostEqual(float(south["centre"][0]), 0.0, places=6)
        self.assertAlmostEqual(float(south["face"][2]), -1.0, places=6)
        self.assertEqual(len(south["panels"]), 2)
        q = lv.PARAMS["boards"]
        self.assertAlmostEqual(q["north_w"] * q["north_h"] / 0.3048 ** 2, 5978.0, delta=60.0)
        north = sorted((p for p in self.model.markers["jumbo"] if p[2] < 0), key=lambda p: p[0])
        self.assertEqual(len(north), 2)
        self.assertAlmostEqual(north[0][0], -north[1][0], places=6)
        self.assertAlmostEqual(north[0][2], north[1][2], places=6)
        self.assertTrue(55.0 < abs(north[0][0]) < 72.0 and -105.0 < north[0][2] < -90.0, north[0])
        m = self.model
        for lp, sec in zip(m.loop, m.secs):
            for t, b in m.board_hits(lp):
                if "upper" in sec:
                    self.assertLess(sec["upper"][-1][1], b["bottom"], (round(lp.x, 1), round(lp.z, 1)))
                self.assertGreaterEqual(sec["rim"][3], min(t + b["depth"], m.facade_depth(lp) - 1.0) - 1e-6)

    def test_markers_positions(self):
        self.assertEqual(len(self.model.markers["jumbo"]), 3)
        self.assertGreaterEqual(len(self.model.light_points), 16)
        pts = lv.flare_points(self.model)
        self.assertEqual(len(pts), 4)
        self.assertEqual(len({(round(p[0]), round(p[2])) for p in pts}), 4)


class Cameras(unittest.TestCase):
    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(lv.allegiant_shots(), lv.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            if "pitch" not in present:
                self.assertEqual(shot["pitch"], 0.0)
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        """xemu draws a flare marker's lens flare through anything (u6's labs 2 and 3), so no shot may have one in its
        frustum along its 8 s path (a vertical field of view on a 16:9 picture, 3 degrees of margin)."""
        model = lv.build()
        flares = [np.array(p, float) for p in lv.flare_points(model)]
        for p in flares:
            self.assertGreater(p[1], 250.0)
        for k, shot in enumerate(lv.allegiant_shots()):
            r = shot.get("rates", {})
            for t in range(0, 9):
                eye = np.array(shot["eye"], float) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                yaw = math.radians(shot["yaw"] + r.get("yaw", 0) * t)
                pitch = math.radians(shot["pitch"] + r.get("pitch", 0) * t)
                f = np.array([-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)])
                right = np.cross(f, (0.0, 1.0, 0.0))
                right /= np.linalg.norm(right)
                up = np.cross(right, f)
                vf = math.radians(shot["fov"])
                hf = 2 * math.atan(math.tan(vf / 2) * 16 / 9)
                for p in flares:
                    d = (p - eye) / np.linalg.norm(p - eye)
                    x, y, z = d @ right, d @ up, d @ f
                    inside = z > 0 and abs(math.atan2(x, z)) <= hf / 2 + 0.05 and abs(math.atan2(y, z)) <= vf / 2 + 0.05
                    self.assertFalse(inside, (k + 1, t, tuple(np.round(p))))

    def test_two_exterior_shots(self):
        outside = [s for s in lv.allegiant_shots() if max(abs(s["eye"][0]), abs(s["eye"][2])) > 150]
        self.assertGreaterEqual(len(outside), 2)

    def test_eyes_stay_in_the_open(self):
        model = lv.build()
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P])
        for k, s in enumerate(lv.allegiant_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        retail = lv.read_retail(EXTRACTED)
        for name in ("s20dd.iff", "s20ns.iff"):
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), lv.CAMERA_COMPONENTS_PRESENT, name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class SceneMarkers(unittest.TestCase):
    def test_no_marker_registers_a_glow(self):
        """0x7F210 registers a glow at every marker whose name holds "light" (u6 and st, PROVED IN GAME), so no marker of
        the Allegiant scene may carry the word."""
        retail = lv.read_retail(EXTRACTED)
        for name in ("s20dd.iff", "s20nd.iff"):
            sc = lv.build_scene(retail[name], name, lv.build())
            self.assertFalse([m.name for m in sc.markers if "light" in m.name], name)
            self.assertTrue([m.name for m in sc.markers if m.name.startswith("marker_lamp")], name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class LeagueBanner(unittest.TestCase):
    def test_the_kept_banners_carry_the_2026_league_cloths(self):
        """u4's reviewed league sheet goes over banner_corp's defunct cloths: exact on the dry bundles, carried to rain
        and snow from the dry bundle; nothing without the dry one."""
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = lv.read_retail(EXTRACTED)
        entry = next(e for e in mv.LEAGUE_ART if e["key"] == lv.LEAGUE_BANNER)
        art = lv._rgba(mv.DATA_DIR / entry["art"])
        _i, dry = lv.league_banner(retail["s20dd.iff"], "s20dd.iff")
        for x0, y0, x1, y1 in entry["rects"]:
            self.assertTrue(np.array_equal(dry[y0:y1, x0:x1], art[y0:y1, x0:x1]))
        self.assertIsNone(lv.league_banner(retail["s20ns.iff"], "s20ns.iff"))
        index, snow = lv.league_banner(retail["s20ns.iff"], "s20ns.iff", retail["s20nd.iff"])
        c = ml.bundle_scenes(retail["s20ns.iff"])["stadium"]
        rec, dec = ml._scene(retail["s20ns.iff"], c)
        before = ml.read_p8(dec, c.system_bytes, ml.texture_rows(rec)[lv.LEAGUE_BANNER])[0]
        changed = sum(int(not np.array_equal(snow[y0:y1, x0:x1], before[y0:y1, x0:x1])) for x0, y0, x1, y1 in entry["rects"])
        self.assertGreater(changed, 0)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Field(unittest.TestCase):
    def test_the_field_fits_with_the_bands_and_the_raiders_art(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = lv.read_retail(EXTRACTED)
        name = "s20dd.iff"
        chunk = ml.bundle_scenes(retail[name])["field"]
        team = {"endzone_N_M": np.full((128, 256, 4), (10, 10, 10, 235), np.uint8)}
        span, info = lv.field_span(retail[name], name, team=team)
        self.assertEqual(len(span), 32 + chunk.stored_size)
        out = bytes(retail[name][:chunk.offset]) + span + bytes(retail[name][chunk.offset + len(span):])
        rec, dec = ml._scene(out, ml.bundle_scenes(out)["field"])
        g = sm._field_shape(rec, "A_grass_color")
        st0, st1 = sm._stream(g, 0), sm._stream(g, 1)
        su, sv, ou, ov = struct.unpack_from("<4f", dec, g["record_offset"] + 0x30)
        for i in sm._submesh_vertices(rec, dec, g, lv.GRASS_MATERIAL):
            _x, _y, z = struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i)
            qu = struct.unpack_from("<h", dec, st1["offset"] + st1["stride"] * i + 4)[0]
            self.assertAlmostEqual(qu / 32767.0 * su + ou, (45.72 - z / 100.0) / 91.44, places=3)

    def test_each_end_zone_takes_its_own_art(self):
        """s20, like s25, gives each end its own three textures (endzone_N_* at -z, endzone_S_* at +z): the north art goes on the
        north panels and the south art on the south ones; a root with the north art only paints both ends with it."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = lv.read_retail(EXTRACTED)
        name = "s20dd.iff"
        chunk = ml.bundle_scenes(retail[name])["field"]
        rec, dec = ml._scene(retail[name], chunk)
        rows = ml.texture_rows(rec)
        g = sm._field_shape(rec, "A_grass_color")
        st0 = sm._stream(g, 0)
        for p in "LMR":
            for end, sign in (("N", -1), ("S", 1)):
                idx = sm._submesh_vertices(rec, dec, g, f"endzone_{end}_{p}")
                z = np.mean([struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i)[2] for i in idx])
                self.assertEqual(np.sign(z), sign)
            self.assertNotEqual(rows[f"endzone_N_{p}"]["index"], rows[f"endzone_S_{p}"]["index"])
        north = {f"endzone_N_{p}": np.full((128, 256, 4), (200, 10, 40, 255), np.uint8) for p in "LMR"}
        south = {f"endzone_S_{p}": np.full((128, 256, 4), (10, 40, 200, 255), np.uint8) for p in "LMR"}
        painted = lv.paint_field(dec, rec, chunk.system_bytes, "d", team=dict(north, **south))
        for p in "LMR":
            n = ml.read_p8(painted, chunk.system_bytes, rows[f"endzone_N_{p}"])[0][..., :3].reshape(-1, 3).mean(0)
            s = ml.read_p8(painted, chunk.system_bytes, rows[f"endzone_S_{p}"])[0][..., :3].reshape(-1, 3).mean(0)
            self.assertGreater(n[0], n[2])
            self.assertGreater(s[2], s[0])
        plain = lv.paint_field(dec, rec, chunk.system_bytes, "d", team=north)
        for p in "LMR":
            s = ml.read_p8(plain, chunk.system_bytes, rows[f"endzone_S_{p}"])[0][..., :3].reshape(-1, 3).mean(0)
            self.assertGreater(s[0], s[2])


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class VenueRow(unittest.TestCase):
    def test_the_row_names_the_stadium_and_its_weather(self):
        from mod_editor.core import nfl2k5_allegiant_venue as vv
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_roster_records as rr
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = archive.entries[vv.ROST_OUTER_INDEX]
            data = archive.read(e.virtual_offset, e.size)
        self.assertEqual(vv.rost_state(data), "retail")
        after, receipt = vv.rost_allegiant(data)
        self.assertEqual(len(after), len(data))
        self.assertEqual(vv.rost_state(after), "applied")
        again, _receipt2 = vv.rost_allegiant(after)
        self.assertEqual(again, after)
        H = rr.RESOURCE_HEADER_SIZE
        changed = [i - H for i, (a, b) in enumerate(zip(data, after)) if a != b]
        rec_off = receipt["records"][0]["record_offset"]
        block = receipt["records"][0]["block"]
        for i in changed:
            self.assertTrue(block[0] <= i < block[1] or rec_off <= i < rec_off + 0x80, i)
        body = after[H:]
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x18)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x1C)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x04)[0], vv.CAPACITY)
        self.assertEqual(body[rec_off + 0x28:rec_off + 0x7C], data[H:][rec_off + 0x28:rec_off + 0x7C])
        # composes with the 2026 venue renames in either order
        a, _ = mv.rost_rename(after)
        b, _ = vv.rost_allegiant(mv.rost_rename(data)[0])
        self.assertEqual(a, b)


class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s20_to_the_model(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s25", "s20", "s01", "s07", "s03", "s22")}, league={"nfl_shield": {}}, skipped=[])
        without = [p for p, _t in mv.venues_to_write(art)]
        mine = [p for p, _t in mv.venues_to_write(art, **{"allegiant": True})]
        self.assertIn("s20", without)
        self.assertEqual(set(without) - set(mine), {"s20"})
        every = [p for p, _t in mv.venues_to_write(art, att=True, levis=True, highmark=True, sofi=True, allegiant=True,
                                                   mercedes_benz=True)]
        self.assertEqual(set(without) - set(every), {"s25", "s20", "s01", "s07", "s03", "s23", "s24"})

    def test_option_is_off_in_every_preset(self):
        from mod_editor.core import mod_build
        key = "modern_allegiant"
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get(key), False, name)
        self.assertIn(key, mod_build.availability())
        from mod_editor.core import nfl2k5_build_settings as bs
        self.assertIn(key, bs.FEATURE_KEYS)


@unittest.skipUnless(EXTRACTED.is_dir() and lv.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    def test_compiled_stretches_equal_their_pins(self):
        retail = lv.read_retail(EXTRACTED)
        for name in ("s20dd.iff", "s20as.iff"):
            model, info = lv.model_bundle(retail[name], name, lv.build(), cameras=lv.allegiant_shots(),
                                          dry_bundle=retail[lv.dry_of(name)])
            self.assertEqual(len(model), len(retail[name]))
            start, end = lv.stretch(retail[name])
            pin = lv._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(lv.sha(model[start:end]), pin["model_sha256"], name)
            self.assertEqual(lv.sha(retail[name][start:end]), pin["retail_sha256"])
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"])

    def test_every_bundle_is_pinned_and_under_retail(self):
        pins = lv.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(lv.VARIANTS))
        for p in pins["bundles"]:
            self.assertLess(p["vertices"], 30000)


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        """Every authored PNG ships as an exact reviewed catalog entry, and the release checker pins the catalog."""
        import hashlib
        import json
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted((lv.DATA_DIR / "art").rglob("*.png"))
        manifest = json.loads((lv.DATA_DIR / "art" / "art.json").read_text(encoding="utf-8"))["art"]
        self.assertEqual(len(pngs), len(manifest))
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            self.assertEqual((row["width"], row["height"]), Image.open(png).size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_allegiant_model.py", "mod_editor/core/nfl2k5_allegiant_venue.py",
                    "data/nfl2k5_allegiant_model/footprint.json", "data/nfl2k5_allegiant_model/pins.json"):
            self.assertIn(rel, allow)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"', checker)


class _Entry:
    def __init__(self, size):
        self.virtual_offset, self.size = 0, size


class _Archive:
    """One bundle as an archive: read(offset, size) over its bytes."""
    def __init__(self, data):
        self.data = bytes(data)

    def read(self, offset, size):
        return self.data[offset:offset + size]


#: a paint colour no turf takes (the end-zone check)
PAINT = (167, 25, 48, 255)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Surfaces(unittest.TestCase):
    """Modern playing surfaces (tf) runs after every stadium writer. With it on too, the new s20 field takes tf's
    colours (its solve for the venue's target under the dome rig: the row's indoor word is 1) and reads applied under
    tf's deep status; before tf the model bundle is tf's input (unsurfaced, never foreign, so tf's step does not refuse
    it). The stadium and camera stretch is the model's alone."""

    def _check(self, name, *, graded):
        import hashlib
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_sofi_model as sm
        from mod_editor.core import nfl2k5_allegiant_venue as vv
        ml = sm._ml()
        retail = lv.read_retail(EXTRACTED)
        pins = lv._venue_pins()
        settings = colour.normalize_settings({}) if graded else None
        current = colour.modern_bundle(retail[name])[0] if graded else retail[name]
        team = {"endzone_N_M": np.full((128, 256, 4), PAINT, np.uint8)}
        _n, model, _info = lv._compose((name, retail[name], current, settings, pins[name]["outer"], team,
                                           retail[lv.dry_of(name)]))
        before = ms.bundle_report(_Archive(model), name, _Entry(len(model)), None, deep=True)
        self.assertEqual(before["state"], "retail", before)
        indoor = vv.ALLEGIANT_WORDS[1] == 1
        self.assertTrue(indoor)
        out, rec = ms.surface_bundle(model, name, indoor=indoor, colour_settings=settings)
        self.assertEqual(len(out), len(model))
        look = ms.venue_look("s20")
        self.assertEqual((rec["look"], rec["light"]), (look, "dome"))
        self.assertEqual(rec["field"]["target"], [round(v, 2) for v in ms.venue_target("s20", look, "dome")])
        self.assertIn("field", {e["kind"] for e in rec["edits"]})
        start, end = lv.stretch(retail[name])
        self.assertEqual(out[start:end], model[start:end])
        chunk = ml.bundle_scenes(out)["field"]
        frec, fdec = ml._scene(out, chunk)
        rows = ml.texture_rows(frec)
        rgba, _pal = ml.read_p8(fdec, chunk.system_bytes, rows[lv.GRASS_MATERIAL])
        mean = rgba[..., :3].reshape(-1, 3).astype(float).mean(0)
        for got, want in zip(mean, rec["field"]["map_mean"]):
            self.assertAlmostEqual(got, want, delta=max(4.0, 0.06 * want))
        ez, _pal = ml.read_p8(fdec, chunk.system_bytes, rows["endzone_N_M"])
        c = ez[..., :3].reshape(-1, 3).astype(float).mean(0)
        self.assertGreater(c[0], c[1] + 40)                     # the club's paint survives tf's turf recolour
        row = ms.bundle_report(_Archive(out), name, _Entry(len(out)), None, deep=True)
        self.assertEqual(row["state"], "applied", row)
        self.assertIn("planar field UVs", row["reason"])
        receipt = dict(bundles={name: dict(applied_sha256=hashlib.sha256(out).hexdigest(), edits=rec["edits"])})
        row = ms.bundle_report(_Archive(out), name, _Entry(len(out)), receipt, deep=True)
        self.assertEqual(row["state"], "applied", row)
        self.assertEqual(ms.surface_bundle(out, name, indoor=indoor, colour_settings=settings)[0], out)

    def test_a_day_field_takes_the_modern_surface(self):
        self._check("s20dd.iff", graded=False)

    def test_a_graded_snow_field_takes_the_modern_surface(self):
        self._check("s20ns.iff", graded=True)


def _feed_coverage(tris, shot, t, nx=64, ny=48, aspect=4 / 3):
    """Share of a 4:3 picture whose ray meets a live-feed triangle at ``t`` seconds into the shot (no occlusion: an
    upper bound)."""
    r = shot.get("rates", {})
    eye = np.array(shot["eye"], float) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
    yaw = math.radians(shot["yaw"] + r.get("yaw", 0) * t)
    pitch = math.radians(shot["pitch"] + r.get("pitch", 0) * t)
    f = np.array([-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)])
    right = np.cross(f, (0.0, 1.0, 0.0))
    right /= np.linalg.norm(right)
    up = np.cross(right, f)
    th = math.tan(math.radians(shot["fov"]) / 2)
    X, Y = np.meshgrid(((np.arange(nx) + 0.5) / nx * 2 - 1) * th * aspect, ((np.arange(ny) + 0.5) / ny * 2 - 1) * th)
    D = (f[None, None, :] + X[..., None] * right[None, None, :] + Y[..., None] * up[None, None, :]).reshape(-1, 3)
    hit = np.zeros(len(D), bool)
    for a, b, c in tris:
        e1, e2 = b - a, c - a
        pv = np.cross(D, e2)
        det = pv @ e1
        ok = np.abs(det) > 1e-9
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = eye - a
        u = (pv @ s) * inv
        q = np.cross(s, e1)
        v = (D @ q) * inv
        hit |= ok & (u >= 0) & (v >= 0) & (u + v <= 1) & ((q @ e2) * inv > 0)
    return float(hit.mean())


def _feed_triangles(model):
    tris = []
    for mesh in model.meshes.values():
        P = np.array(mesh.P, float) if mesh.P else None
        for strip in mesh.groups.get("jumbo_tron", ()):
            for i in range(len(strip) - 2):
                k = strip[i:i + 3]
                if len(set(k)) == 3:
                    tris.append((P[k[0]], P[k[1]], P[k[2]]))
    return tris


class FeedLoop(unittest.TestCase):
    """The live feed is the game's own frame, so a screen in view shows itself (st2 lab 2, 2026-09-27: AT&T's board went
    solid white while pass 1's shot 3 filled 57 to 65 percent of the picture with it)."""

    def test_no_feed_screen_fills_a_flyover_shot(self):
        """At most a quarter of the picture is live feed at any half second of any shot's 8 s path (Levi's boards, at
        9 percent, played clean in lab 2)."""
        tris = _feed_triangles(lv.build())
        self.assertTrue(tris)
        for k, shot in enumerate(lv.allegiant_shots()):
            for t in np.linspace(0, 8, 17):
                self.assertLessEqual(_feed_coverage(tris, shot, t), 0.25, (k + 1, t))

    def test_the_feed_draws_at_about_the_frames_brightness(self):
        """The screen draws the game's own previous frame at twice its vertex colour (st2 lab 2, fly-026: the copy of the
        stands 2.0 to 2.3 times the stands under vertex colour 245), so the feed's vertex colour holds the loop gain near
        1 in every light and weather: a screen that sees itself cannot flood white."""
        P = np.zeros((4, 3))
        N = np.tile([0.0, 1.0, 0.0], (4, 1))
        for tod in "dan":
            for weather in "drs":
                for outside in (False, True):
                    c = lv.light("jumbo_tron", P, N, tod, weather, outside=outside)
                    self.assertTrue((c[:, :3] == lv.FEED_VERTEX).all() and (c[:, 3] == 255).all(), (tod, weather))
        self.assertTrue(0.85 <= 2 * lv.FEED_VERTEX / 255 <= 1.0)


if __name__ == "__main__":
    unittest.main()
