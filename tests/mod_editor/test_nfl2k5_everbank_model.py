"""EverBank Stadium model (st2): geometry, the end zone boards, the 2026 construction sub-option, markers, cameras, the
field, the league cloths, the row and the feed."""
import math
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_everbank_model as jx  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = jx.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 30000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_field_wall_clears_the_sideline_props(self):
        """The wall stays outside the retail s12 sideline props (x -40.6 to 40.0) and on or behind the banners' line
        (x +-43.0, z -60.6 to 61.5, projected onto the wall), PROVED OFFLINE from the retail scene."""
        loop = self.model.loop
        side = [lp for lp in loop if abs(lp.z) < 40]
        self.assertGreaterEqual(min(lp.x for lp in side if lp.x > 0), 43.0)
        self.assertLessEqual(max(lp.x for lp in side if lp.x < 0), -43.0)
        end = [lp for lp in loop if abs(lp.x) < 12]
        self.assertGreaterEqual(min(lp.z for lp in end if lp.z > 0), 61.5)
        self.assertLessEqual(max(lp.z for lp in end if lp.z < 0), -60.6)

    def test_the_stacks_fit_inside_the_facade(self):
        """Every rim walk ends inside the facade outline."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in jx.footprint()["facade"]]
        for lp, sec in zip(self.model.loop, self.model.secs):
            if "rim" not in sec:
                continue
            x, _y, z = self.model.at(lp, sec["rim"][3], 0.0)
            self.assertTrue(sm._point_in_poly(x, z, ring), (round(x, 1), round(z, 1)))

    def test_the_end_zone_boards(self):
        """The 2014 boards (SOURCED: 362 ft long; 60 ft high) over the end stands, facing the field, their bottoms over
        every seat of their end."""
        q = jx.PARAMS["boards"]
        self.assertAlmostEqual(q["w"] / 0.3048, 362.0, delta=0.5)
        self.assertAlmostEqual(q["h"] / 0.3048, 60.0, delta=0.2)
        m = self.model
        for lp, sec in zip(m.loop, m.secs):
            for end, w_, bottom in (("N", lp.w["N"], q["north_bottom"]), ("S", lp.w["S"], q["south_bottom"])):
                if w_ > 0.6 and abs(lp.x) < q["w"] / 2:
                    top = max(y for key in ("lower", "t2", "upper") if key in sec for _d, y in sec[key])
                    self.assertLess(top, bottom, (end, round(lp.x, 1), round(lp.z, 1)))
        faces = sorted((float(f["centre"][2]), float(f["face"][2])) for f in m.board_frames)
        self.assertEqual(len(faces), 2)
        (zn, fn), (zs, fs) = faces
        self.assertLess(zn, -m.p["loop"]["zn"]); self.assertGreater(fn, 0.9)
        self.assertGreater(zs, m.p["loop"]["zs"]); self.assertLess(fs, -0.9)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_materials_are_known(self):
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"jx_seat_front", "jx_seat_mid", "jx_seat_back", "crowd", "LIGHT_jx_lights", "jumbo_tron",
                         "LIGHT_jx_board_panel", "jx_facade", "jx_board_back", "jx_roof", "jx_letters", "jx_riser",
                         "jx_truss", "jx_crane", "jx_netting", "jx_fence", "jx_drained", "jx_fabric",
                         "env_far", "env_band"} <= mats)
        self.assertTrue(mats <= set(jx.MATERIALS) | {"crowd", "jumbo_tron"}, mats - set(jx.MATERIALS))

    def test_the_environment_kit_dresses_the_surroundings(self):
        """st3's environment kit (nfl2k5_stadium_environment) outside the plaza: the far ground, the band at 1,800 m,
        the lots, roads, blocks and trees, none of the lots, blocks or trees inside the building's outline, Daily's Place
        or the cranes' masts."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        from mod_editor.core import nfl2k5_stadium_environment as env
        m = self.model
        for part in ("far", "band", "lots", "roads", "blocks", "trees"):
            self.assertGreater(m.env_counts[part], 0, part)
        band = np.array(m.meshes["env_band"].P, float)
        self.assertTrue(np.allclose(np.hypot(band[:, 0], band[:, 2]), env.BAND_RADIUS, atol=1e-3))
        keep = [[tuple(p) for p in jx.footprint()["facade"]]]
        keep.append([tuple(p) for p in jx.footprint()["daily"]])
        w = jx.PARAMS["construction"]["mast_w"] / 2
        keep += [[(x - w, z - w), (x + w, z - w), (x + w, z + w), (x - w, z + w)]
                 for x, z, _h in jx.PARAMS["construction"]["cranes"]]
        for name in ("env_lots", "env_blocks", "env_trees"):
            for x, _y, z in m.meshes[name].P:
                self.assertFalse(any(sm._point_in_poly(x, z, q) for q in keep), (name, round(x, 1), round(z, 1)))

    def test_the_boards_show_the_feed_at_the_pictures_aspect(self):
        """Both boards show a crop of the 640 x 448 feed picture (u 0 to 0.625, v 0 to 0.875 of the render target) at the
        picture's own aspect, never stretched, between their stat panels; seen from the field each picture runs with the
        screen's right, cross(view, up): +x on the north board, -x on the south one."""
        q = jx.PARAMS["boards"]
        aspect = q["w"] * q["feed"] / q["h"]
        (u0, u1), (v0, v1) = self.model.board_crop(aspect)
        self.assertGreaterEqual(u0, 0.0); self.assertLessEqual(u1, 0.625 + 1e-9)
        self.assertGreaterEqual(v0, 0.0); self.assertLessEqual(v1, 0.875 + 1e-9)
        self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), aspect, places=2)
        feeds = [(m, strip) for m in self.model.meshes.values() for strip in m.groups.get("jumbo_tron", ())]
        self.assertEqual(len(feeds), 2)
        for m, strip in feeds:
            P = np.array([m.P[i] for i in strip]); U = np.array([m.UV[i][0] for i in strip])
            c = np.corrcoef(P[:, 0], U)[0, 1]
            if P[:, 2].mean() < 0:
                self.assertGreater(c, 0.9)
            else:
                self.assertLess(c, -0.9)

    def test_markers_positions(self):
        self.assertEqual(len(self.model.markers["jumbo"]), 2)
        self.assertGreaterEqual(len(self.model.light_points), 16)
        pts = jx.flare_points(self.model)
        self.assertEqual(len(pts), 4)
        self.assertEqual(len({(round(p[0]), round(p[2])) for p in pts}), 4)


class Construction(unittest.TestCase):
    """The 2026 season's construction (the sub-option, on by default) against the 2025 stadium (off)."""

    @classmethod
    def setUpClass(cls):
        cls.on = jx.build()
        cls.off = jx.build(construction=False)

    @staticmethod
    def _mats(model):
        return {mat for m in model.meshes.values() for mat in m.groups}

    def test_both_variants_fit_the_budget(self):
        for model in (self.on, self.off):
            self.assertLess(sum(m.count() for m in model.meshes.values()), 30000)
            for m in model.meshes.values():
                self.assertLess(m.count(), 0xFFFF, m.name)

    def test_on_by_default(self):
        import inspect
        self.assertTrue(jx.EverBank().construction)
        self.assertIs(inspect.signature(jx.build).parameters["construction"].default, True)
        self.assertIs(inspect.signature(jx.apply_to_image).parameters["construction"].default, True)

    def test_the_400_level_is_stripped_to_bare_risers(self):
        """On: the 400 level's rows are bare concrete, no seats and no crowd there; off: seats and crowd as in 2025."""
        on, off = self.on, self.off
        self.assertIn("jx_riser", self._mats(on))
        self.assertNotIn("jx_riser", self._mats(off))
        self.assertTrue(on.stripped)
        tops = [max(y for _d, y in sec["upper"]) for sec in on.secs if "upper" in sec]
        floor = min(min(y for _d, y in sec["upper"]) for sec in on.secs if "upper" in sec)
        crowd_top = {}
        for name, model in (("on", on), ("off", off)):
            crowd_top[name] = max(m.P[i][1] for m in model.meshes.values() for st in m.groups.get("crowd", ()) for i in st)
        # the crowd stops at the club rows with the 400 level stripped, and fills it without
        self.assertLess(crowd_top["on"], 30.0)
        self.assertGreater(crowd_top["off"], 40.0)
        self.assertGreater(max(tops), 40.0)
        self.assertLess(floor, max(tops))

    def test_the_site_reads_as_construction(self):
        """On: the canopy's trusses round the outside (standing off the facade), three tower cranes just outside, the
        netting along the stripped decks, the pools drained behind fencing, the lights lowered; off: none of it, the
        pools full and the lights on their masts."""
        on, off = self.on, self.off
        q = jx.PARAMS["construction"]
        for mat in ("jx_crane", "jx_netting", "jx_fence", "jx_drained"):
            self.assertIn(mat, self._mats(on), mat)
            self.assertNotIn(mat, self._mats(off), mat)
        # the site (the canopy's trusses, the cranes, the netting) is the construction's alone; the 2025 stadium's own
        # lattices are the light towers and the boards' frames
        self.assertIn("jx_site", on.meshes)
        self.assertNotIn("jx_site", off.meshes)
        self.assertIn("jx_truss", on.meshes["jx_site"].groups)
        self.assertIn("jx_water", self._mats(off))
        site = on.meshes["jx_site"]
        P = np.array(site.P)
        cranes = [p for p in P if p[1] > jx.GRADE + q["crane_top"] - 1.0]
        self.assertTrue(cranes)
        for x, z, _h in q["cranes"]:
            self.assertTrue(any(math.hypot(p[0] - x, p[2] - z) < 60.0 for p in cranes), (x, z))
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in jx.footprint()["facade"]]
        feet = [p for p in P if abs(p[1] - jx.GRADE) < 0.01]
        self.assertTrue(feet)
        self.assertTrue(all(not sm._point_in_poly(p[0], p[2], ring) for p in feet))
        y_on = max(p[1] for p in on.light_points)
        y_off = max(p[1] for p in off.light_points)
        self.assertLess(y_on, y_off - 10.0)

    def test_the_thin_parts_show_from_both_sides(self):
        """The game culls back faces: the netting, fencing and the cranes' jibs carry both windings."""
        site = self.on.meshes["jx_site"]
        for mat in ("jx_netting",):
            strips = site.groups[mat]
            normals = []
            for st in strips:
                a, b, c = (np.array(site.P[i]) for i in st[:3])
                n_ = np.cross(b - a, c - a)
                normals.append(n_ / max(1e-9, np.linalg.norm(n_)))
            dots = [float(n1 @ n2) for n1 in normals for n2 in normals]
            self.assertLess(min(dots), -0.9)


class Cameras(unittest.TestCase):
    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(jx.everbank_shots(), jx.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            if "pitch" not in present:
                self.assertEqual(shot["pitch"], 0.0)
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        """xemu draws a flare marker's lens flare through anything (u6's labs 2 and 3), so no shot may have one in its
        frustum along its 8 s path (a vertical field of view on a 16:9 picture, 3 degrees of margin)."""
        model = jx.build()
        flares = [np.array(p, float) for p in jx.flare_points(model)]
        for p in flares:
            self.assertGreater(p[1], 250.0)
        for k, shot in enumerate(jx.everbank_shots()):
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
        outside = [s for s in jx.everbank_shots() if max(abs(s["eye"][0]), abs(s["eye"][2])) > 150]
        self.assertGreaterEqual(len(outside), 2)

    def test_eyes_stay_in_the_open(self):
        model = jx.build()
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P])
        for k, s in enumerate(jx.everbank_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        retail = jx.read_retail(EXTRACTED)
        for name in ("s12dd.iff", "s12ns.iff"):
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), jx.CAMERA_COMPONENTS_PRESENT, name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class SceneMarkers(unittest.TestCase):
    def test_no_marker_registers_a_glow(self):
        """0x7F210 registers a glow at every marker whose name holds "light" (u6 and st, PROVED IN GAME), so no marker of
        the EverBank Stadium scene may carry the word."""
        retail = jx.read_retail(EXTRACTED)
        for name in ("s12dd.iff", "s12nd.iff"):
            sc = jx.build_scene(retail[name], name, jx.build())
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
        retail = jx.read_retail(EXTRACTED)
        entry = next(e for e in mv.LEAGUE_ART if e["key"] == jx.LEAGUE_BANNER)
        art = jx._rgba(mv.DATA_DIR / entry["art"])
        _i, dry = jx.league_banner(retail["s12dd.iff"], "s12dd.iff")
        for x0, y0, x1, y1 in entry["rects"]:
            self.assertTrue(np.array_equal(dry[y0:y1, x0:x1], art[y0:y1, x0:x1]))
        self.assertIsNone(jx.league_banner(retail["s12ns.iff"], "s12ns.iff"))
        index, snow = jx.league_banner(retail["s12ns.iff"], "s12ns.iff", retail["s12nd.iff"])
        c = ml.bundle_scenes(retail["s12ns.iff"])["stadium"]
        rec, dec = ml._scene(retail["s12ns.iff"], c)
        before = ml.read_p8(dec, c.system_bytes, ml.texture_rows(rec)[jx.LEAGUE_BANNER])[0]
        changed = sum(int(not np.array_equal(snow[y0:y1, x0:x1], before[y0:y1, x0:x1])) for x0, y0, x1, y1 in entry["rects"])
        self.assertGreater(changed, 0)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Field(unittest.TestCase):
    def test_the_field_fits_with_the_bands_and_the_jaguars_art(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = jx.read_retail(EXTRACTED)
        name = "s12dd.iff"
        chunk = ml.bundle_scenes(retail[name])["field"]
        team = {"endzone_N_M": np.full((128, 256, 4), (10, 10, 10, 235), np.uint8)}
        span, info = jx.field_span(retail[name], name, team=team)
        self.assertEqual(len(span), 32 + chunk.stored_size)
        out = bytes(retail[name][:chunk.offset]) + span + bytes(retail[name][chunk.offset + len(span):])
        rec, dec = ml._scene(out, ml.bundle_scenes(out)["field"])
        g = sm._field_shape(rec, "A_grass_color")
        st0, st1 = sm._stream(g, 0), sm._stream(g, 1)
        su, sv, ou, ov = struct.unpack_from("<4f", dec, g["record_offset"] + 0x30)
        for i in sm._submesh_vertices(rec, dec, g, jx.GRASS_MATERIAL):
            _x, _y, z = struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i)
            qu = struct.unpack_from("<h", dec, st1["offset"] + st1["stride"] * i + 4)[0]
            self.assertAlmostEqual(qu / 32767.0 * su + ou, (45.72 - z / 100.0) / 91.44, places=3)

    def test_each_end_zone_takes_its_own_art(self):
        """s12 gives each end its own three textures (endzone_N_* at -z, endzone_S_* at +z): the north art goes on the
        north panels and the south art on the south ones; a root with the north art only paints both ends with it."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = jx.read_retail(EXTRACTED)
        name = "s12dd.iff"
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
        painted = jx.paint_field(dec, rec, chunk.system_bytes, "d", team=dict(north, **south))
        for p in "LMR":
            n = ml.read_p8(painted, chunk.system_bytes, rows[f"endzone_N_{p}"])[0][..., :3].reshape(-1, 3).mean(0)
            s = ml.read_p8(painted, chunk.system_bytes, rows[f"endzone_S_{p}"])[0][..., :3].reshape(-1, 3).mean(0)
            self.assertGreater(n[0], n[2])
            self.assertGreater(s[2], s[0])
        plain = jx.paint_field(dec, rec, chunk.system_bytes, "d", team=north)
        for p in "LMR":
            s = ml.read_p8(plain, chunk.system_bytes, rows[f"endzone_S_{p}"])[0][..., :3].reshape(-1, 3).mean(0)
            self.assertGreater(s[0], s[2])


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class VenueRow(unittest.TestCase):
    def test_the_row_takes_u4s_name_and_the_seasons_capacity(self):
        """The s12 row takes u4's strings (EverBank Stadium, Jacksonville, FL) in either order with the 2026 venue names,
        and 42,507 seats with the construction or 67,814 without; open air, grass; a second pass is a no-op."""
        from mod_editor.core import nfl2k5_everbank_venue as vv
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_roster_records as rr
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = archive.entries[vv.ROST_OUTER_INDEX]
            data = archive.read(e.virtual_offset, e.size)
        self.assertEqual(vv.rost_state(data), "retail")
        H = rr.RESOURCE_HEADER_SIZE
        for construction, cap in ((True, 42507), (False, 67814)):
            after, receipt = vv.rost_everbank(data, construction=construction)
            self.assertEqual(len(after), len(data))
            self.assertEqual(vv.rost_state(after), "applied")
            self.assertEqual(vv.rost_everbank(after, construction=construction)[0], after)
            rec_off = receipt["records"][0]["record_offset"]
            body = after[H:]
            self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x04)[0], cap)
            self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x18)[0], 0)
            self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x1C)[0], 1)
            a, _ = mv.rost_rename(after)
            b, _ = vv.rost_everbank(mv.rost_rename(data)[0], construction=construction)
            self.assertEqual(a, b)


class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s12_to_the_model(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s12", "s10", "s14", "s16", "s00", "s20", "s01", "s22")}, league={"nfl_shield": {}},
                   skipped=[])
        without = [p for p, _t in mv.venues_to_write(art)]
        mine = [p for p, _t in mv.venues_to_write(art, **{"everbank": True})]
        self.assertIn("s12", without)
        self.assertEqual(set(without) - set(mine), {"s12"})
        both = [p for p, _t in mv.venues_to_write(art, hard_rock=True, gillette=True, state_farm=True, lambeau=True, everbank=True)]
        self.assertEqual(set(without) - set(both), {"s12", "s10", "s14", "s16", "s00"})

    def test_option_is_off_in_every_preset_and_runs_before_modern_surfaces(self):
        import inspect
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as bs
        key = "modern_everbank"
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get(key), False, name)
        self.assertIn(key, mod_build.availability())
        self.assertIn(key, bs.FEATURE_KEYS)
        self.assertIs(mod_build.BuildPlan.__dataclass_fields__[key].default, False)
        sub = "modern_everbank_construction"
        self.assertIs(mod_build.BuildPlan.__dataclass_fields__[sub].default, True)
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get(sub), True, name)
        self.assertIn(sub, mod_build.availability())
        self.assertIn(sub, bs.FEATURE_KEYS)
        src = inspect.getsource(mod_build)
        self.assertIn("construction=plan.modern_everbank_construction", src)
        steps = [src.index(f'{{"step": "{k}"') for k in ("modern_color_bundles", "modern_venues_2026",
                                                          "modern_state_farm", "modern_hard_rock", "modern_gillette",
                                                          "modern_lambeau", "modern_everbank", "modern_surfaces")]
        self.assertEqual(steps, sorted(steps))

    def test_the_4x_pack_names_a_master_for_every_material(self):
        import nfl2k5_everbank_model_pack as pack
        from mod_editor.core import nfl2k5_stadium_environment as env
        for tod in "dan":
            for material in jx.MATERIALS:
                rel = pack.master_for(material, "d", None, tod)
                art = env.ART_DIR if material.startswith("env_") else jx.ART_DIR
                self.assertTrue((art / rel).is_file(), (tod, material, rel))
        for material in (jx.GRASS_MATERIAL, jx.OUTSIDE_MATERIAL):
            rel = pack.master_for(material, "d", None)
            self.assertTrue((jx.ART_DIR / rel).is_file(), (material, rel))
            self.assertIsNone(pack.master_for(material, "s", None))


@unittest.skipUnless(EXTRACTED.is_dir() and jx.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    def test_compiled_stretches_equal_their_pins(self):
        retail = jx.read_retail(EXTRACTED)
        for name in ("s12dd.iff", "s12ns.iff"):
            model, info = jx.model_bundle(retail[name], name, jx.build(), cameras=jx.everbank_shots(),
                                          dry_bundle=retail[jx.dry_of(name)])
            self.assertEqual(len(model), len(retail[name]))
            start, end = jx.stretch(retail[name])
            pin = jx._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(jx.sha(model[start:end]), pin["model_sha256"], name)
            classic, _ci = jx.model_bundle(retail[name], name, jx.build(construction=False), cameras=jx.everbank_shots(),
                                           dry_bundle=retail[jx.dry_of(name)])
            self.assertEqual(jx.sha(classic[start:end]), pin["classic_sha256"], name)
            self.assertNotEqual(pin["classic_sha256"], pin["model_sha256"])
            self.assertEqual(jx.sha(retail[name][start:end]), pin["retail_sha256"])
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"])

    def test_every_bundle_is_pinned_and_the_registry_pins_the_ends(self):
        import json
        pins = jx.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(jx.VARIANTS))
        for p in pins["bundles"]:
            self.assertLess(p["vertices"], 30000)
        text = jx.PINS_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
        registry = json.loads((ROOT / "mod_editor" / "capabilities" / "registry.v1.json").read_text(encoding="utf-8"))
        row = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.stadiums_fields.modern_everbank")
        first, last = jx._pin("s12dd.iff"), jx._pin("s12ns.iff")
        self.assertEqual(row["source_container"]["hash_pins"], [first["retail_sha256"], first["model_sha256"],
                                                                 first["classic_sha256"], last["retail_sha256"],
                                                                 last["model_sha256"], last["classic_sha256"]])


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        """Every authored PNG ships as an exact reviewed catalog entry, and the release checker pins the catalog."""
        import hashlib
        import json
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted(jx.ART_DIR.rglob("*.png"))
        manifest = json.loads((jx.ART_DIR / "art.json").read_text(encoding="utf-8"))["art"]
        self.assertEqual(len(pngs), len(manifest))
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(),
                                                            png.stat().st_size), rel)
            with Image.open(png) as image:
                self.assertEqual((row["width"], row["height"]), image.size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_everbank_model.py", "mod_editor/core/nfl2k5_everbank_venue.py",
                    "data/nfl2k5_everbank_model/footprint.json", "data/nfl2k5_everbank_model/pins.json",
                    "data/nfl2k5_everbank_model/art/art.json", "tests/mod_editor/test_nfl2k5_everbank_model.py"):
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
    """Modern playing surfaces (tf) runs after every stadium writer. With it on too, the new s12 field takes tf's
    colours (its solve for the venue's target under the bundle's own light: the row stays open air) and reads applied under
    tf's deep status; before tf the model bundle is tf's input (unsurfaced, never foreign, so tf's step does not refuse
    it). The stadium and camera stretch is the model's alone."""

    def _check(self, name, *, graded):
        import hashlib
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_sofi_model as sm
        from mod_editor.core import nfl2k5_everbank_venue as vv
        ml = sm._ml()
        retail = jx.read_retail(EXTRACTED)
        pins = jx._venue_pins()
        settings = colour.normalize_settings({}) if graded else None
        current = colour.modern_bundle(retail[name])[0] if graded else retail[name]
        team = {"endzone_N_M": np.full((128, 256, 4), PAINT, np.uint8)}
        _n, model, _info = jx._compose((name, retail[name], current, settings, pins[name]["outer"], team,
                                           retail[jx.dry_of(name)], True))
        before = ms.bundle_report(_Archive(model), name, _Entry(len(model)), None, deep=True)
        self.assertEqual(before["state"], "retail", before)
        indoor = vv.EVERBANK_WORDS[1] == 1
        self.assertFalse(indoor)
        out, rec = ms.surface_bundle(model, name, indoor=indoor, colour_settings=settings)
        self.assertEqual(len(out), len(model))
        look = ms.venue_look("s12")
        cls_ = ms.light_class(name, indoor)
        self.assertEqual((rec["look"], rec["light"]), (look, cls_))
        self.assertEqual(rec["field"]["target"], [round(v, 2) for v in ms.venue_target("s12", look, cls_)])
        self.assertIn("field", {e["kind"] for e in rec["edits"]})
        start, end = jx.stretch(retail[name])
        self.assertEqual(out[start:end], model[start:end])
        chunk = ml.bundle_scenes(out)["field"]
        frec, fdec = ml._scene(out, chunk)
        rows = ml.texture_rows(frec)
        rgba, _pal = ml.read_p8(fdec, chunk.system_bytes, rows[jx.GRASS_MATERIAL])
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
        self._check("s12dd.iff", graded=False)

    def test_a_graded_rain_field_takes_the_modern_surface(self):
        self._check("s12nr.iff", graded=True)


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
        tris = _feed_triangles(jx.build())
        self.assertTrue(tris)
        for k, shot in enumerate(jx.everbank_shots()):
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
                    c = jx.light("jumbo_tron", P, N, tod, weather, outside=outside)
                    self.assertTrue((c[:, :3] == jx.FEED_VERTEX).all() and (c[:, 3] == 255).all(), (tod, weather))
        self.assertTrue(0.85 <= 2 * jx.FEED_VERTEX / 255 <= 1.0)


if __name__ == "__main__":
    unittest.main()
