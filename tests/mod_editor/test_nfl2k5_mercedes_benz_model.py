"""Mercedes-Benz Stadium model (st2): geometry, the roof and the Halo, the window to the city, the feed crop, the sourced
marks, markers, cameras, the field and the league cloths."""
import math
import struct
import sys
import unittest
from official_marks_fixture import requires_real_pack
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_mercedes_benz_model as mb  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = mb.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 30000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_field_wall_clears_the_sideline_props_and_banners(self):
        """The wall stays outside the retail s01 sideline props (x -38.9 to 40.6, z -61.9 to 32.9) and at the banners'
        line or beyond (x +-42.5, z +-66.7, projected onto the wall)."""
        loop = self.model.loop
        side = [lp for lp in loop if abs(lp.z) < 40]
        self.assertGreaterEqual(min(lp.x for lp in side if lp.x > 0), 42.5)
        self.assertLessEqual(max(lp.x for lp in side if lp.x < 0), -42.5)
        end = [lp for lp in loop if abs(lp.x) < 12]
        self.assertGreaterEqual(min(lp.z for lp in end if lp.z > 0), 62.0)
        self.assertLessEqual(max(lp.z for lp in end if lp.z < 0), -62.0)

    def test_the_stacks_fit_inside_the_facade(self):
        """Every rim walk ends inside the OpenStreetMap facade outline."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in mb.footprint()["facade"]]
        for lp, sec in zip(self.model.loop, self.model.secs):
            x, _y, z = self.model.at(lp, sec["rim"][3], 0.0)
            self.assertTrue(sm._point_in_poly(x, z, ring), (round(x, 1), round(z, 1)))

    def test_the_roof_clears_the_stands_and_the_halo_hangs_under_the_opening(self):
        """The roof stays at least 2 m over every rim's top; the Halo's top hangs under the opening's edge and over every
        seat; its ring is 1,100 ft round and 58 ft tall (Wikipedia)."""
        m = self.model
        for lp, sec in zip(m.loop, m.secs):
            x, _y, z = m.at(lp, sec["rim"][0], 0.0)
            self.assertGreater(m.roof_height(x, z), sec["rim"][2] + 2.0, (round(x, 1), round(z, 1)))
        q = mb.PARAMS["halo"]
        self.assertAlmostEqual(2 * math.pi * q["r"] / 0.3048, 1100.0, delta=2.0)
        self.assertAlmostEqual(q["h"] / 0.3048, 58.0, delta=0.2)
        self.assertLess(q["bottom"] + q["h"], mb.PARAMS["roof"]["rim"])
        self.assertLess(q["r"], mb.PARAMS["roof"]["oculus_r"])
        top_seat = max(max(y for _d, y in sec["upper"]) for sec in m.secs if "upper" in sec)
        self.assertGreater(q["bottom"], top_seat - 5.0)

    def _verts(self, mesh_name, material):
        mesh = self.model.meshes[mesh_name]
        idx = sorted({i for st in mesh.groups.get(material, []) for i in st})
        return np.array(mesh.P, float)[idx]

    def test_pass3_the_petals_are_irregular(self):
        """Main's pass-3 note: irregular petals (sizes, pitches, heights; not a regular octagon). The units' chords
        differ by more than half again, the south-west unit is the widest and the north-east one next; the corners'
        heights span at least 10 m and their leans at least 3 m; the tips stand at different heights."""
        lay = self.model.petal_layout()
        C = lay["corners"]
        chords = [math.dist(C[k]["base"], C[(k + 1) % 8]["base"]) for k in range(8)]
        self.assertGreater(max(chords) / min(chords), 1.5)
        order = sorted(range(8), key=lambda k: -chords[k])
        self.assertEqual(order[:2], [4, 0])
        bearing = lambda x, z: (349.5 + math.degrees(math.atan2(z, x))) % 360  # noqa: E731
        mid = [(np.array(C[k]["base"]) + np.array(C[(k + 1) % 8]["base"])) / 2 for k in range(8)]
        self.assertTrue(180 < bearing(*mid[4]) < 270, bearing(*mid[4]))      # the south-west unit
        self.assertTrue(0 < bearing(*mid[0]) < 90, bearing(*mid[0]))         # the north-east unit
        ys = [c["top"][1] for c in C]
        self.assertGreaterEqual(max(ys) - min(ys), 10.0)
        leans = [math.dist(c["base"], (c["top"][0], c["top"][2])) for c in C]
        self.assertGreaterEqual(max(leans) - min(leans), 3.0)
        self.assertGreater(len({round(t[1], 1) for t in lay["tips"]}), 5)

    def test_pass3_the_big_south_west_petal_carries_the_star(self):
        """The star rides the widest unit's metal petal, on the south-west, the largest of the facade's stars."""
        places = self.model.sign_places
        stars = [p_ for p_ in places if p_["what"] == "mb_star"]
        big = max(stars, key=lambda p_: p_["size"])
        self.assertEqual(big["unit"], 4)
        self.assertGreaterEqual(big["size"], 20.0)
        self.assertIn(4, {p_["unit"] for p_ in stars})
        x, _y, z = big["centre"]
        self.assertTrue(180 < (349.5 + math.degrees(math.atan2(z, x))) % 360 < 270)

    def test_pass3_the_ring_stands_proud_of_the_petals(self):
        """The ring round the opening rises clear of every petal's top (its outer wall at least 5 m over the highest
        corner), white from above; the pinwheel rises from the ring's top."""
        q = mb.PARAMS["roof"]
        tops = self._verts("mb_roof_top", "mb_panel_top")
        self.assertGreaterEqual(q["ring_top"] - tops[:, 1].max(), 5.0)
        ring = self._verts("mb_roof_top", "mb_roof_top")
        r = np.hypot(ring[:, 0], ring[:, 2])
        self.assertTrue(np.any((np.abs(ring[:, 1] - q["ring_top"]) < 1e-6) & (r > q["oculus_r"] + 1.0)))
        pin = self._verts("mb_roof_top", "mb_pinwheel")
        self.assertGreaterEqual(pin[:, 1].min(), q["ring_top"])

    def test_pass3_the_roof_stays_inside_the_facade(self):
        """The underside's outer edge keeps inside the petals' chords at the eave (the pair lab's exterior frames and
        the renders: the old edge on the outline cut through the petals as dark streaks)."""
        m = self.model
        cx, cz = m.petal_layout()["centre"]
        for mesh_name, mat in (("mb_roof_under", "mb_ring"),):
            P = self._verts(mesh_name, mat)
            low = P[P[:, 1] < mb.PARAMS["roof"]["eave"] + 3.0]
            ang = [math.atan2(z - cz, x - cx) for x, _y, z in low]
            sec = m.facade_section_radius(mb.PARAMS["roof"]["eave"], ang)
            for (x, y, z), rs in zip(low, sec):
                self.assertLess(math.hypot(x - cx, z - cz), rs - 0.5, (round(x, 1), round(y, 1), round(z, 1)))

    def test_pass3_the_band_has_fewer_larger_panes(self):
        """Main's pass-3 note: fewer, larger glass facets. The band round the concourses carries its own texture (two
        rows of four panes) at one repeat per 36 m: panes 9 m wide."""
        mesh = self.model.meshes["mb_facade"]
        idx = sorted({i for st in mesh.groups["mb_glass_base"] for i in st})
        P = np.array(mesh.P, float)[idx]
        U = np.array(mesh.UV, float)[idx][:, 0]
        self.assertEqual(mb.PARAMS["facade"]["band_u_m"], 36.0)
        # one repeat per 36 m round the band (the old band repeated every 10 m: about 88 repeats round the building)
        perimeter = float(np.sum(np.hypot(np.diff(P[P[:, 1] < mb.GRADE][:, 0]), np.diff(P[P[:, 1] < mb.GRADE][:, 2]))))
        self.assertAlmostEqual(U.max() - U.min(), perimeter / 36.0, delta=0.5)
        self.assertLess(U.max() - U.min(), 30.0)
        art = mb._rgba(mb.ART_DIR / "mb_glass_base.png")
        self.assertEqual(art.shape[:2], (64, 128))

    @requires_real_pack("modern_mercedes_benz")
    def test_pass3_a_sky_backdrop_surrounds_everything(self):
        """s01's retail bundles carry no sky (the pair lab: black over the building in the exterior shots): the model
        draws its own backdrop at 1,900 m (u6's SoFi radius), every other surface inside it, the texture the bundle's
        hour (overcast in the rain and snow bundles by day), drawn at its own colour."""
        R = mb.PARAMS["sky"]["radius"]
        for name, mesh in self.model.meshes.items():
            P = np.array(mesh.P, float)
            r = np.hypot(P[:, 0], P[:, 2])
            if name == "mb_sky":
                self.assertTrue(np.allclose(r, R, atol=1e-3))
            else:
                self.assertLess(r.max(), R - 50.0, name)
        self.assertEqual(mb.sky_kind("d", "r"), "o")
        self.assertEqual(mb.sky_kind("n", "s"), "n")
        self.assertEqual(mb.sky_kind("a", "d"), "a")
        tex = mb._textures("s01", "d", "r")
        self.assertTrue(np.array_equal(tex["mb_sky"], mb._rgba(mb.ART_DIR / "mb_sky_o.png")))
        c = mb.light("mb_sky", np.zeros((2, 3)), np.zeros((2, 3)), "d", "d", outside=True)
        self.assertTrue(np.all(c[:, :3] == mb.SKY_VERTEX))

    def test_the_window_stands_on_the_east_face(self):
        """The window to the city on the outline's east curve over the east 200 level (no 300 level in front of it),
        centred on the field axis, with the star on its black panel under it and the column board at its side."""
        m = self.model
        w = m.window
        self.assertAlmostEqual(w["x0"], -w["x1"], places=6)
        self.assertGreater(w["z"], 140.0)
        for lp, sec in zip(m.loop, m.secs):
            if m.window_zone(lp):
                self.assertNotIn("upper", sec)
        mats = {mat for mesh in m.meshes.values() for mat in mesh.groups}
        self.assertTrue({"LIGHT_mb_window", "mb_star", "LIGHT_mb_column", "mb_sign", "mb_name"} <= mats)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_materials_are_known(self):
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"mb_seat_front", "mb_seat_mid", "mb_seat_back", "crowd", "mb_roof_under", "mb_ring",
                         "LIGHT_mb_halo", "jumbo_tron", "LIGHT_mb_lights", "mb_panel", "mb_glass_out",
                         "LIGHT_mb_skyline",
                         "env_far", "env_band"} <= mats)
        self.assertTrue(mats <= set(mb.MATERIALS) | {"crowd", "jumbo_tron"}, mats - set(mb.MATERIALS))

    def test_the_environment_kit_dresses_the_surroundings(self):
        """st3's environment kit (nfl2k5_stadium_environment) outside the plaza: the far ground, the band at 1,800 m,
        the lots, roads, blocks and trees, none of the lots, blocks or trees inside the building's outline."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        from mod_editor.core import nfl2k5_stadium_environment as env
        m = self.model
        for part in ("far", "band", "lots", "roads", "blocks", "trees"):
            self.assertGreater(m.env_counts[part], 0, part)
        band = np.array(m.meshes["env_band"].P, float)
        self.assertTrue(np.allclose(np.hypot(band[:, 0], band[:, 2]), env.BAND_RADIUS, atol=1e-3))
        keep = [[tuple(p) for p in mb.footprint()["facade"]]]
        for name in ("env_lots", "env_blocks", "env_trees"):
            for x, _y, z in m.meshes[name].P:
                self.assertFalse(any(sm._point_in_poly(x, z, q) for q in keep), (name, round(x, 1), round(z, 1)))

    def test_the_halo_shows_the_feed_at_the_pictures_aspect(self):
        """Every other Halo panel shows a crop of the 640 x 448 feed picture (u 0 to 0.625, v 0 to 0.875 of the render
        target) at the panel's own aspect, never stretched; the digits' two graphics panels face the sidelines."""
        q = mb.PARAMS["halo"]
        aspect = 2 * math.pi * q["r"] / q["panels"] / q["h"]
        (u0, u1), (v0, v1) = self.model.board_crop(aspect)
        self.assertGreaterEqual(u0, 0.0); self.assertLessEqual(u1, 0.625 + 1e-9)
        self.assertGreaterEqual(v0, 0.0); self.assertLessEqual(v1, 0.875 + 1e-9)
        self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), aspect, places=3)
        feeds = [f for f in self.model.halo_frames if f["feed"]]
        self.assertEqual(len(feeds), q["panels"] // 2)
        digits = [f for f in self.model.halo_frames if not f["feed"] and abs(math.sin(f["angle"])) <= 0.5]
        self.assertEqual(len(digits), 2)
        self.assertAlmostEqual(abs(digits[0]["centre"][0]), q["r"], places=3)

    def test_markers_positions(self):
        self.assertEqual(len(self.model.markers["jumbo"]), 2)
        self.assertGreaterEqual(len(self.model.light_points), 16)
        pts = mb.flare_points(self.model)
        self.assertEqual(len(pts), 4)
        self.assertEqual(len({(round(p[0]), round(p[2])) for p in pts}), 4)


class SourcedMarks(unittest.TestCase):
    @requires_real_pack("modern_mercedes_benz")
    def test_the_star_and_the_sign_are_the_sourced_renders(self):
        """The star texture is the rendered official vector and the sign the wordmark of the venue's own logo (both
        recorded by SHA-256 in the art tool); the art manifest pins every texture."""
        import json
        import nfl2k5_mercedes_benz_model_art as art
        self.assertEqual(len(art.STAR_SVG_SHA256), 64)
        self.assertEqual(len(art.LOGO_SVG_SHA256), 64)
        manifest = json.loads((mb.ART_DIR / "art.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "nfl2k5_mercedes_benz_model_art/v1")
        for key in ("mb_star", "mb_sign", "mb_name"):
            self.assertIn(key, manifest["art"])
        star = mb._rgba(mb.ART_DIR / "mb_star.png")
        self.assertGreater(int(star[..., 3].max()), 200)
        self.assertEqual(int(star[0, 0, 3]), 0)


class Cameras(unittest.TestCase):
    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(mb.mb_shots(), mb.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            if "pitch" not in present:
                self.assertEqual(shot["pitch"], 0.0)
            if "x" not in present:
                self.assertEqual(shot["eye"][0], 0.0)
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        """xemu draws a flare marker's lens flare through anything (u6's labs 2 and 3), so no shot may have one in its
        frustum along its 8 s path (a vertical field of view on a 16:9 picture, 3 degrees of margin)."""
        model = mb.build()
        flares = [np.array(p, float) for p in mb.flare_points(model)]
        for p in flares:
            self.assertGreater(p[1], 250.0)
        for k, shot in enumerate(mb.mb_shots()):
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
        outside = [s for s in mb.mb_shots() if max(abs(s["eye"][0]), abs(s["eye"][2])) > 150]
        self.assertGreaterEqual(len(outside), 2)

    def test_eyes_stay_in_the_open(self):
        model = mb.build()
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P])
        for k, s in enumerate(mb.mb_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        retail = mb.read_retail(EXTRACTED)
        for name in ("s01dd.iff", "s01ns.iff"):
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), mb.CAMERA_COMPONENTS_PRESENT, name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class SceneMarkers(unittest.TestCase):
    @requires_real_pack("modern_mercedes_benz")
    def test_no_marker_registers_a_glow(self):
        """0x7F210 registers a glow at every marker whose name holds "light" (u6 and st, PROVED IN GAME), so no marker of
        the Mercedes-Benz scene may carry the word."""
        retail = mb.read_retail(EXTRACTED)
        for name in ("s01dd.iff", "s01nd.iff"):
            sc = mb.build_scene(retail[name], name, mb.build())
            self.assertFalse([m.name for m in sc.markers if "light" in m.name], name)
            self.assertTrue([m.name for m in sc.markers if m.name.startswith("marker_lamp")], name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Field(unittest.TestCase):
    def test_the_field_fits_with_the_bands_and_the_falcons_art(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = mb.read_retail(EXTRACTED)
        name = "s01dd.iff"
        chunk = ml.bundle_scenes(retail[name])["field"]
        team = {"endzone_N_M": np.full((128, 256, 4), (167, 25, 48, 235), np.uint8)}
        span, info = mb.field_span(retail[name], name, team=team)
        self.assertEqual(len(span), 32 + chunk.stored_size)
        out = bytes(retail[name][:chunk.offset]) + span + bytes(retail[name][chunk.offset + len(span):])
        rec, dec = ml._scene(out, ml.bundle_scenes(out)["field"])
        g = sm._field_shape(rec, "A_grass_color")
        st0, st1 = sm._stream(g, 0), sm._stream(g, 1)
        su, sv, ou, ov = struct.unpack_from("<4f", dec, g["record_offset"] + 0x30)
        for i in sm._submesh_vertices(rec, dec, g, mb.GRASS_MATERIAL):
            _x, _y, z = struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i)
            qu = struct.unpack_from("<h", dec, st1["offset"] + st1["stride"] * i + 4)[0]
            self.assertAlmostEqual(qu / 32767.0 * su + ou, (45.72 - z / 100.0) / 91.44, places=3)

    @requires_real_pack("modern_mercedes_benz")
    def test_the_two_ends_share_their_textures(self):
        """s01, like s07, lays both ends' panels on the same three textures (endzone_N_* at -z, endzone_S_* at +z;
        PROVED OFFLINE): a root with one end's art paints both ends with it and keeps the retail V."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = mb.read_retail(EXTRACTED)
        chunk = ml.bundle_scenes(retail["s01dd.iff"])["field"]
        rec, dec = ml._scene(retail["s01dd.iff"], chunk)
        rows = ml.texture_rows(rec)
        for p in "LMR":
            self.assertEqual(rows[f"endzone_N_{p}"]["index"], rows[f"endzone_S_{p}"]["index"])
        north = {f"endzone_N_{p}": np.full((128, 256, 4), (167, 25, 48, 255), np.uint8) for p in "LMR"}
        painted = mb.paint_field(dec, rec, chunk.system_bytes, "d", team=north)
        for p in "LMR":
            rgba, _pal = ml.read_p8(painted, chunk.system_bytes, rows[f"endzone_N_{p}"])
            c = rgba[..., :3].reshape(-1, 3).mean(0)
            self.assertGreater(c[0], c[2])


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class VenueRow(unittest.TestCase):
    def test_the_row_names_the_stadium_and_its_weather(self):
        from mod_editor.core import nfl2k5_mercedes_benz_venue as vv
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_roster_records as rr
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = archive.entries[vv.ROST_OUTER_INDEX]
            data = archive.read(e.virtual_offset, e.size)
        self.assertEqual(vv.rost_state(data), "retail")
        after, receipt = vv.rost_mercedes_benz(data)
        self.assertEqual(len(after), len(data))
        self.assertEqual(vv.rost_state(after), "applied")
        again, _receipt2 = vv.rost_mercedes_benz(after)
        self.assertEqual(again, after)
        H = rr.RESOURCE_HEADER_SIZE
        changed = [i - H for i, (a, b) in enumerate(zip(data, after)) if a != b]
        rec_off = receipt["records"][0]["record_offset"]
        block = receipt["records"][0]["block"]
        for i in changed:
            self.assertTrue(block[0] <= i < block[1] or rec_off <= i < rec_off + 0x80, i)
        body = after[H:]
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x18)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x1C)[0], 0)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x04)[0], vv.CAPACITY)
        self.assertEqual(body[rec_off + 0x28:rec_off + 0x7C], data[H:][rec_off + 0x28:rec_off + 0x7C])
        # composes with the 2026 venue renames in either order
        a, _ = mv.rost_rename(after)
        b, _ = vv.rost_mercedes_benz(mv.rost_rename(data)[0])
        self.assertEqual(a, b)


class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s01_to_the_model(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s25", "s20", "s01", "s07", "s03", "s22")}, league={"nfl_shield": {}}, skipped=[])
        without = [p for p, _t in mv.venues_to_write(art)]
        mine = [p for p, _t in mv.venues_to_write(art, **{"mercedes_benz": True})]
        self.assertIn("s01", without)
        self.assertEqual(set(without) - set(mine), {"s01"})
        every = [p for p, _t in mv.venues_to_write(art, att=True, levis=True, highmark=True, sofi=True, allegiant=True,
                                                   mercedes_benz=True)]
        self.assertEqual(set(without) - set(every), {"s25", "s20", "s01", "s07", "s03", "s23", "s24"})

    def test_option_is_off_in_every_preset(self):
        from mod_editor.core import mod_build
        key = "modern_mercedes_benz"
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get(key), False, name)
        self.assertIn(key, mod_build.availability())
        from mod_editor.core import nfl2k5_build_settings as bs
        self.assertIn(key, bs.FEATURE_KEYS)


@unittest.skipUnless(EXTRACTED.is_dir() and mb.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    @requires_real_pack("modern_mercedes_benz")
    def test_compiled_stretches_equal_their_pins(self):
        retail = mb.read_retail(EXTRACTED)
        for name in ("s01dd.iff", "s01as.iff"):
            model, info = mb.model_bundle(retail[name], name, mb.build(), cameras=mb.mb_shots(),
                                          dry_bundle=retail[mb.dry_of(name)])
            self.assertEqual(len(model), len(retail[name]))
            start, end = mb.stretch(retail[name])
            pin = mb._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(mb.sha(model[start:end]), pin["model_sha256"], name)
            self.assertEqual(mb.sha(retail[name][start:end]), pin["retail_sha256"])
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"])

    def test_every_bundle_is_pinned_and_under_retail(self):
        pins = mb.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(mb.VARIANTS))
        for p in pins["bundles"]:
            self.assertLess(p["vertices"], 30000)

    def test_the_registry_pins_the_first_and_last_stretch(self):
        """The registry row's hash pins follow the pins file (they went stale once, after the Halo fix)."""
        import json
        text = mb.PINS_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
        registry = json.loads((ROOT / "mod_editor" / "capabilities" / "registry.v1.json").read_text(encoding="utf-8"))
        row = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.stadiums_fields.modern_mercedes_benz")
        first, last = mb._pin("s01dd.iff"), mb._pin("s01ns.iff")
        self.assertEqual(row["source_container"]["hash_pins"], [first["retail_sha256"], first["model_sha256"],
                                                                 last["retail_sha256"], last["model_sha256"]])


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        """Every authored PNG ships as an exact reviewed catalog entry, and the release checker pins the catalog."""
        import hashlib
        import json
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted((mb.DATA_DIR / "art").rglob("*.png"))
        manifest = json.loads((mb.DATA_DIR / "art" / "art.json").read_text(encoding="utf-8"))["art"]
        from mod_editor.core import nfl2k5_official_marks as official
        external = [p for p in official.CATALOG if p.startswith("data/nfl2k5_mercedes_benz_model/art/")]
        self.assertEqual(len(pngs) + len(external), len(manifest))
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            self.assertEqual((row["width"], row["height"]), Image.open(png).size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_mercedes_benz_model.py", "mod_editor/core/nfl2k5_mercedes_benz_venue.py",
                    "data/nfl2k5_mercedes_benz_model/footprint.json", "data/nfl2k5_mercedes_benz_model/pins.json"):
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
    """Modern playing surfaces (tf) runs after every stadium writer. With it on too, the new s01 field takes tf's
    colours (its solve for the venue's target under the dome rig: the row's indoor word is 1) and reads applied under
    tf's deep status; before tf the model bundle is tf's input (unsurfaced, never foreign, so tf's step does not refuse
    it). The stadium and camera stretch is the model's alone."""

    def _check(self, name, *, graded):
        import hashlib
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_sofi_model as sm
        from mod_editor.core import nfl2k5_mercedes_benz_venue as vv
        ml = sm._ml()
        retail = mb.read_retail(EXTRACTED)
        pins = mb._venue_pins()
        settings = colour.normalize_settings({}) if graded else None
        current = colour.modern_bundle(retail[name])[0] if graded else retail[name]
        team = {"endzone_N_M": np.full((128, 256, 4), PAINT, np.uint8)}
        _n, model, _info = mb._compose((name, retail[name], current, settings, pins[name]["outer"], team,
                                           retail[mb.dry_of(name)]))
        before = ms.bundle_report(_Archive(model), name, _Entry(len(model)), None, deep=True)
        self.assertEqual(before["state"], "retail", before)
        indoor = vv.MERCEDES_BENZ_WORDS[1] == 1
        self.assertTrue(indoor)
        out, rec = ms.surface_bundle(model, name, indoor=indoor, colour_settings=settings)
        self.assertEqual(len(out), len(model))
        look = ms.venue_look("s01")
        self.assertEqual((rec["look"], rec["light"]), (look, "dome"))
        self.assertEqual(rec["field"]["target"], [round(v, 2) for v in ms.venue_target("s01", look, "dome")])
        self.assertIn("field", {e["kind"] for e in rec["edits"]})
        start, end = mb.stretch(retail[name])
        self.assertEqual(out[start:end], model[start:end])
        chunk = ml.bundle_scenes(out)["field"]
        frec, fdec = ml._scene(out, chunk)
        rows = ml.texture_rows(frec)
        rgba, _pal = ml.read_p8(fdec, chunk.system_bytes, rows[mb.GRASS_MATERIAL])
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

    @requires_real_pack("modern_mercedes_benz")
    def test_a_day_field_takes_the_modern_surface(self):
        self._check("s01dd.iff", graded=False)

    @requires_real_pack("modern_mercedes_benz")
    def test_a_graded_snow_field_takes_the_modern_surface(self):
        self._check("s01ns.iff", graded=True)


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
        tris = _feed_triangles(mb.build())
        self.assertTrue(tris)
        for k, shot in enumerate(mb.mb_shots()):
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
                    c = mb.light("jumbo_tron", P, N, tod, weather, outside=outside)
                    self.assertTrue((c[:, :3] == mb.FEED_VERTEX).all() and (c[:, 3] == 255).all(), (tod, weather))
        self.assertTrue(0.85 <= 2 * mb.FEED_VERTEX / 255 <= 1.0)


class HaloOrientation(unittest.TestCase):
    """The pair lab (2026-09-28, PROVED IN GAME, fly-016): pass 1's Halo graphics read mirrored from inside (ATL as
    "JTA", FALCONS and RISE UP reversed) and the feed showed the frame mirrored, because u ran against the angle round the
    ring; the game's digits, laid along cross(view, up), read left to right. Four graphics panels showed the digits'
    window empty."""

    @classmethod
    def setUpClass(cls):
        cls.model = mb.build()
        mesh = cls.model.meshes["mb_halo"]
        cls.P, cls.N, cls.UV = np.array(mesh.P, float), np.array(mesh.N, float), np.array(mesh.UV, float)
        cls.panels = [(mat, sorted(set(strip))) for mat in ("jumbo_tron", "LIGHT_mb_halo") for strip in mesh.groups[mat]]
        q = mb.PARAMS["halo"]
        shot = mb.mb_shots()[2]
        r = shot.get("rates", {})
        cls.eyes = [np.array(shot["eye"], float) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                    for t in (0.0, 4.0, 8.0)] + [np.array([0.0, q["bottom"] + q["h"] / 2, 0.0])]

    def test_every_panel_reads_left_to_right_and_upright_from_the_camera_side(self):
        """From the Halo shot's eye along its path and from the ring's centre, an upright camera turned to each panel
        sees its front (the normals face the eye), its u growing to screen right (cross(view, up)) and its v growing
        down the screen: the feed's picture and the club graphics read as drawn, never mirrored or upside down."""
        self.assertEqual(len(self.panels), mb.PARAMS["halo"]["panels"])
        up = np.array([0.0, 1.0, 0.0])
        for mat, idx in self.panels:
            P, N, UV = self.P[idx], self.N[idx], self.UV[idx]
            centre = P.mean(axis=0)
            for eye in self.eyes:
                f = (centre - eye) / np.linalg.norm(centre - eye)
                self.assertGreater(float(N.mean(axis=0) @ (eye - centre)), 0.0, (mat, tuple(np.round(centre))))
                right = np.cross(f, up)
                right /= np.linalg.norm(right)
                sup = np.cross(right, f)
                depth = (P - eye) @ f
                x, y = ((P - eye) @ right) / depth, ((P - eye) @ sup) / depth
                self.assertGreater(np.corrcoef(UV[:, 0], x)[0, 1], 0.9, (mat, tuple(np.round(centre))))
                self.assertLess(np.corrcoef(UV[:, 1], y)[0, 1], -0.9, (mat, tuple(np.round(centre))))

    def test_only_the_digit_panels_show_the_window(self):
        """The two graphics panels over the sidelines (where adjust_digits lays the game's digits) map the texture's
        top half, the dark window's; the other four its bottom half, the club layout, whose middle is type, not black."""
        digit_angles = sorted(round(f["angle"], 6) for f in self.model.halo_frames
                              if not f["feed"] and abs(math.sin(f["angle"])) <= 0.5)
        self.assertEqual(len(digit_angles), 2)
        seen = []
        for mat, idx in self.panels:
            if mat != "LIGHT_mb_halo":
                continue
            c = self.P[idx].mean(axis=0)
            v = self.UV[idx, 1]
            lo, hi = (mb.HALO_DIGIT_V if abs(math.sin(math.atan2(c[2], c[0]))) <= 0.5 else mb.HALO_CLUB_V)
            self.assertAlmostEqual(float(v.min()), lo, places=6)
            self.assertAlmostEqual(float(v.max()), hi, places=6)
            seen.append(lo == mb.HALO_DIGIT_V[0])
        self.assertEqual(sorted(seen), [False] * 4 + [True] * 2)
        art = mb._rgba(mb.ART_DIR / "LIGHT_mb_halo.png")[..., :3].astype(float)
        h, w = art.shape[:2]
        box = lambda top: art[top + int(h / 2 * 0.2):top + int(h / 2 * 0.55), int(w * 0.33):int(w * 0.67)].mean()  # noqa: E731
        self.assertLess(box(0), 30.0)
        self.assertGreater(box(h // 2), 80.0)


if __name__ == "__main__":
    unittest.main()
