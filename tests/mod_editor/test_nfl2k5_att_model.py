"""AT&T Stadium model (st2): geometry, the board's feed crop, markers, cameras, the field, the s07 row, the pins and the
composition with the 2026 venue art."""
import json
import math
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_att_model as hm  # noqa: E402
from mod_editor.core import nfl2k5_att_venue as hv  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = hm.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 30000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_field_wall_clears_the_sideline_props(self):
        """The wall stays outside the retail s07 sideline props (they reach x 37.8 m and z 68.2 m)."""
        loop = self.model.loop
        self.assertGreaterEqual(min(abs(lp.x) for lp in loop if abs(lp.z) < 40), 39.0)
        self.assertGreaterEqual(min(abs(lp.z) for lp in loop if abs(lp.x) < 12), 69.0)

    def test_the_stacks_fit_inside_the_facade(self):
        """Every rim walk ends inside the OpenStreetMap facade outline."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in hm.footprint()["facade"]]
        for lp in self.model.loop:
            sec = self.model.section(lp)
            x, _y, z = self.model.at(lp, sec["rim"][3], 0.0)
            self.assertTrue(sm._point_in_poly(x, z, ring), (round(x, 1), round(z, 1)))

    def test_the_roof_clears_the_stands_and_the_arches_hang_below_its_panels(self):
        """The dome stays at least 2.5 m over every rim's top (the upper deck's back), and inside the arches' trusses hang
        below the operable panels (the 2010 full view)."""
        for lp in self.model.loop:
            sec = self.model.section(lp)
            x, _y, z = self.model.at(lp, sec["rim"][0], 0.0)
            self.assertGreater(self.model.roof_height(x, z), sec["rim"][2] + 2.5, (round(x, 1), round(z, 1)))
        a = hm.PARAMS["arches"]
        for z in (0.0, 40.0, 80.0):
            self.assertLess(self.model.arch_y(z) - a["depth"], self.model.roof_height(a["x"] - 1.0, z) - 1.0)
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"att_panels", "att_roof_under", "att_truss"} <= mats)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_seats_and_decks(self):
        """Every seating tier lays its three seat bands; the Party Pass decks carry their floors and railings."""
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"att_seat_front", "att_seat_mid", "att_seat_back", "att_deck", "att_rail"} <= mats)

    def test_each_party_pass_floor_has_person_height_crowd(self):
        model = self.model
        end = min(model.loop, key=lambda lp: abs(lp.x) + abs(lp.nz - 1) * 1000)
        floors = model.section(end)["t2"][:-1]
        pairs = []
        for mesh in model.meshes.values():
            for strip in mesh.groups.get("crowd", ()):
                for a, b in zip(strip[::2], strip[1::2]):
                    pa, pb = mesh.P[a], mesh.P[b]
                    foot, head = (pa, pb) if pa[1] <= pb[1] else (pb, pa)
                    if abs(foot[0]) < 10 and foot[2] > 70:
                        pairs.append((foot, head))
        self.assertEqual(len(floors), 6)
        for depth, height in floors:
            matches = [(foot, head) for foot, head in pairs
                       if abs(foot[1] - (height + model.p["crowd"]["lift"])) < 1e-6
                       and abs(foot[2] - (end.z + depth + 0.15)) < 1e-6]
            self.assertTrue(matches, (depth, height))
            for foot, head in matches:
                self.assertAlmostEqual(head[1] - foot[1], 1.8, places=6)

    def test_the_board_shows_the_feed_at_each_screens_aspect(self):
        """Four screens on the live feed: each maps a crop of the 640 x 448 feed picture (u 0 to 0.625, v 0 to 0.875 of the
        render target) at the screen's own aspect, never stretched."""
        q = hm.PARAMS["board"]
        for w, h in ((q["side_w"], q["side_h"]), (q["end_w"], q["end_h"])):
            (u0, u1), (v0, v1) = self.model.board_crop(w / h)
            self.assertGreaterEqual(u0, 0.0); self.assertLessEqual(u1, 0.625 + 1e-9)
            self.assertGreaterEqual(v0, 0.0); self.assertLessEqual(v1, 0.875 + 1e-9)
            self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), w / h, places=3)
        feeds = [strip for m in self.model.meshes.values() for strip in m.groups.get("jumbo_tron", ())]
        self.assertEqual(len(feeds), 4)

    def test_the_board_hangs_over_midfield(self):
        """The board is centred over midfield, its bottom 90 ft over the field, its sideline screens along the field."""
        frames = self.model.board_frames
        self.assertEqual(len(frames), 2)
        for f in frames:
            self.assertAlmostEqual(float(f["centre"][2]), 0.0, places=6)
            self.assertAlmostEqual(float(f["centre"][1]), hm.PARAMS["board"]["bottom"], places=3)
            self.assertAlmostEqual(abs(float(f["face"][0])), 1.0, places=6)

    def test_markers_positions(self):
        self.assertEqual(len(self.model.markers["jumbo"]), 2)
        self.assertGreaterEqual(len(self.model.light_points), 16)
        pts = hm.flare_points(self.model)
        self.assertEqual(len(pts), 4)
        self.assertEqual(len({(round(p[0]), round(p[2])) for p in pts}), 4)


class Cameras(unittest.TestCase):
    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(hm.att_shots(), hm.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            if "pitch" not in present:
                self.assertEqual(shot["pitch"], 0.0)
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        """xemu draws a flare marker's lens flare through the canopy (u6's labs 2 and 3), so no shot may have one in its
        frustum along its 8 s path (a vertical field of view on a 16:9 picture, 3 degrees of margin)."""
        model = hm.build()
        flares = [np.array(p, float) for p in hm.flare_points(model)]
        for p in flares:
            self.assertGreater(p[1], 250.0)
        for k, shot in enumerate(hm.att_shots()):
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
        outside = [s for s in hm.att_shots() if max(abs(s["eye"][0]), abs(s["eye"][2])) > 150]
        self.assertGreaterEqual(len(outside), 2)

    def test_eyes_stay_in_the_open(self):
        model = hm.build()
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P])
        for k, s in enumerate(hm.att_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        retail = hm.read_retail(EXTRACTED)
        for name in ("s07dd.iff", "s07ns.iff"):
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), hm.CAMERA_COMPONENTS_PRESENT, name)


class SceneMarkers(unittest.TestCase):
    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_no_marker_registers_a_glow(self):
        """0x7F210 registers a glow at every marker whose name holds "light"; the sprites draw through the canopy (lab 1:
        a ring of them over the roof in the exterior shots), so no marker of the AT&T Stadium scene may carry the word."""
        retail = hm.read_retail(EXTRACTED)
        for name in ("s07dd.iff", "s07nd.iff"):
            sc = hm.build_scene(retail[name], name, hm.build())
            self.assertFalse([m.name for m in sc.markers if "light" in m.name], name)
            self.assertTrue([m.name for m in sc.markers if m.name.startswith("marker_lamp")], name)


class LeagueBanner(unittest.TestCase):
    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_kept_banners_carry_the_2026_league_cloths(self):
        """u4's reviewed league sheet goes over banner_corp's eight defunct cloths (st lab 1: a SEGA cloth at Highmark by
        night): exact on the dry bundles, carried to rain and snow from the dry bundle; nothing without the dry one."""
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        retail = hm.read_retail(EXTRACTED)
        entry = next(e for e in mv.LEAGUE_ART if e["key"] == hm.LEAGUE_BANNER)
        art = hm._rgba(mv.DATA_DIR / entry["art"])
        _i, dry = hm.league_banner(retail["s07dd.iff"], "s07dd.iff")
        for x0, y0, x1, y1 in entry["rects"]:
            self.assertTrue(np.array_equal(dry[y0:y1, x0:x1], art[y0:y1, x0:x1]))
        self.assertIsNone(hm.league_banner(retail["s07ns.iff"], "s07ns.iff"))
        # s07 is indoor: its retail banner_corp is the same texture in every weather, so the snow bundle's cloths are
        # the dry art exactly (u4's transfer is the identity between equal textures)
        _i, snow = hm.league_banner(retail["s07ns.iff"], "s07ns.iff", retail["s07nd.iff"])
        for x0, y0, x1, y1 in entry["rects"]:
            self.assertTrue(np.array_equal(snow[y0:y1, x0:x1], art[y0:y1, x0:x1]))


class VenueRow(unittest.TestCase):
    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_row_names_att_and_keeps_the_weather(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = archive.entries[hv.ROST_OUTER_INDEX]
            data = archive.read(e.virtual_offset, e.size)
        self.assertEqual(hv.rost_state(data), "retail")
        after, receipt = hv.rost_att(data)
        self.assertEqual(len(after), len(data))
        self.assertEqual(hv.rost_state(after), "applied")
        again, receipt2 = hv.rost_att(after)
        self.assertEqual(again, after)
        from mod_editor.core import nfl2k5_roster_records as rr
        H = rr.RESOURCE_HEADER_SIZE
        changed = [i - H for i, (a, b) in enumerate(zip(data, after)) if a != b]
        rec_off = receipt["records"][0]["record_offset"]
        block = receipt["records"][0]["block"]
        for i in changed:
            self.assertTrue(block[0] <= i < block[1] or rec_off <= i < rec_off + 0x80, i)
        # the indoor word stays 1 (the roof is closed, as retail), the surface word 0 (turf), the climate untouched
        body = after[H:]
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x18)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x1C)[0], 0)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x04)[0], hv.CAPACITY)
        self.assertEqual(body[rec_off + 0x28:rec_off + 0x7C], data[H:][rec_off + 0x28:rec_off + 0x7C])
        # composes with the 2026 venue renames in either order
        a, _ = mv.rost_rename(after)
        b, _ = hv.rost_att(mv.rost_rename(data)[0])
        self.assertEqual(a, b)


class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s07_to_att(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s07", "s03", "s22")}, league={"nfl_shield": {}}, skipped=[])
        with_att = [p for p, _t in mv.venues_to_write(art, att=True)]
        without = [p for p, _t in mv.venues_to_write(art)]
        self.assertIn("s07", without)
        self.assertNotIn("s07", with_att)
        self.assertEqual(set(without) - set(with_att), {"s07"})
        every = [p for p, _t in mv.venues_to_write(art, att=True, highmark=True, sofi=True)]
        self.assertEqual(set(without) - set(every), {"s07", "s03", "s23", "s24"})

    def test_option_is_off_in_every_preset(self):
        from mod_editor.core import mod_build
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_att"), False, name)
        self.assertIn("modern_att", mod_build.availability())
        from mod_editor.core import nfl2k5_build_settings as bs
        self.assertIn("modern_att", bs.FEATURE_KEYS)


@unittest.skipUnless(EXTRACTED.is_dir() and hm.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    def test_compiled_stretches_equal_their_pins(self):
        retail = hm.read_retail(EXTRACTED)
        for name in ("s07dd.iff", "s07as.iff", "s07nd.iff"):
            model, info = hm.model_bundle(retail[name], name, hm.build(), cameras=hm.att_shots(),
                                          dry_bundle=retail[hm.dry_of(name)])
            self.assertEqual(len(model), len(retail[name]))
            start, end = hm.stretch(retail[name])
            pin = hm._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(hm.sha(model[start:end]), pin["model_sha256"], name)
            self.assertEqual(hm.sha(retail[name][start:end]), pin["retail_sha256"])
            # One billboard per standing floor adds up to 10,240 decoded bytes over retail.
            # Keep the extra allocation bounded to 12 KiB; model_bundle also checks
            # the original stored span and native decode/readback.
            self.assertLessEqual(info["system"] + info["video"],
                                 info["retail_system"] + info["retail_video"] + 12 * 1024)

    def test_every_bundle_is_pinned_and_under_retail(self):
        pins = hm.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(hm.VARIANTS))
        for p in pins["bundles"]:
            self.assertLess(p["vertices"], 30000)

    def test_the_field_fits_with_the_bands_and_the_cowboys_art(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = hm.read_retail(EXTRACTED)
        name = "s07dd.iff"
        chunk = ml.bundle_scenes(retail[name])["field"]
        team = {"endzone_N_M": np.full((128, 256, 4), (0, 53, 148, 235), np.uint8)}
        span, info = hm.field_span(retail[name], name, team=team)
        self.assertEqual(len(span), 32 + chunk.stored_size)
        out = bytes(retail[name][:chunk.offset]) + span + bytes(retail[name][chunk.offset + len(span):])
        rec, dec = ml._scene(out, ml.bundle_scenes(out)["field"])
        g = sm._field_shape(rec, "A_grass_color")
        st0, st1 = sm._stream(g, 0), sm._stream(g, 1)
        su, sv, ou, ov = struct.unpack_from("<4f", dec, g["record_offset"] + 0x30)
        for i in sm._submesh_vertices(rec, dec, g, hm.GRASS_MATERIAL):
            _x, _y, z = struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i)
            qu = struct.unpack_from("<h", dec, st1["offset"] + st1["stride"] * i + 4)[0]
            self.assertAlmostEqual(qu / 32767.0 * su + ou, (45.72 - z / 100.0) / 91.44, places=3)


    def test_each_end_zone_takes_its_own_art(self):
        """With a south set in the art root, the panels at +z show the north art in their textures' bottom halves and
        the panels at -z the south art in the top halves (each panel's V squeezed into its half); without one, both ends
        keep the north art over the whole texture and the retail V."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = hm.read_retail(EXTRACTED)
        name = "s07dd.iff"
        chunk = ml.bundle_scenes(retail[name])["field"]
        rec, dec = ml._scene(retail[name], chunk)
        north = {f"endzone_N_{p}": np.full((128, 256, 4), (200, 10, 40, 255), np.uint8) for p in "LMR"}
        south = {f"endzone_S_{p}": np.full((128, 256, 4), (10, 40, 200, 255), np.uint8) for p in "LMR"}
        g = sm._field_shape(rec, "A_grass_color")
        st0, st1 = sm._stream(g, 0), sm._stream(g, 1)

        def ends(out):
            _su, sv, _ou, ov = struct.unpack_from("<4f", out, g["record_offset"] + 0x30)
            got = {}
            for end in "NS":
                for p in "LMR":
                    for i in sm._submesh_vertices(rec, out, g, f"endzone_{end}_{p}"):
                        z = struct.unpack_from("<3f", out, st0["offset"] + st0["stride"] * i)[2]
                        v = struct.unpack_from("<h", out, st1["offset"] + st1["stride"] * i + 6)[0] / 32767.0 * sv + ov
                        got.setdefault("north" if z > 0 else "south", []).append(v)
            return got
        painted = hm.paint_field(dec, rec, chunk.system_bytes, "d", team=dict(north, **south))
        v = ends(painted)
        self.assertTrue(all(0.5 <= x <= 1.0 for x in v["north"]) and all(0.0 <= x <= 0.5 for x in v["south"]))
        rows = ml.texture_rows(rec)
        for p in "LMR":
            rgba, _pal = ml.read_p8(painted, chunk.system_bytes, rows[f"endzone_N_{p}"])
            top, bottom = rgba[:64, :, :3].reshape(-1, 3).mean(0), rgba[64:, :, :3].reshape(-1, 3).mean(0)
            self.assertGreater(top[2], top[0])          # the south (blue) art on the top half, for the panels at -z
            self.assertGreater(bottom[0], bottom[2])    # the north (red) art on the bottom half, for the panels at +z
        plain = hm.paint_field(dec, rec, chunk.system_bytes, "d", team=north)
        self.assertEqual(ends(plain), ends(dec))


    def test_the_texas_stadium_marks_are_cleared(self):
        """The retail field's TEXAS STADIUM marks (two quads by the sidelines at midfield) draw nothing."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = hm.read_retail(EXTRACTED)
        chunk = ml.bundle_scenes(retail["s07dd.iff"])["field"]
        rec, dec = ml._scene(retail["s07dd.iff"], chunk)
        painted = hm.paint_field(dec, rec, chunk.system_bytes, "d")
        rgba, _pal = ml.read_p8(painted, chunk.system_bytes, ml.texture_rows(rec)[hm.STADIUM_LOGO])
        self.assertEqual(int(rgba[..., 3].max()), 0)


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        """Every authored PNG ships as an exact reviewed catalog entry, and the release checker pins the catalog."""
        import hashlib
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted((hm.DATA_DIR / "art").rglob("*.png"))
        manifest = json.loads((hm.DATA_DIR / "art" / "art.json").read_text(encoding="utf-8"))["art"]
        self.assertEqual(len(pngs), len(manifest))
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            self.assertEqual((row["width"], row["height"]), Image.open(png).size, rel)
            self.assertIn(rel, allow)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"', checker)


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
        tris = _feed_triangles(hm.build())
        self.assertTrue(tris)
        for k, shot in enumerate(hm.att_shots()):
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
                    c = hm.light("jumbo_tron", P, N, tod, weather, outside=outside)
                    self.assertTrue((c[:, :3] == hm.FEED_VERTEX).all() and (c[:, 3] == 255).all(), (tod, weather))
        self.assertTrue(0.85 <= 2 * hm.FEED_VERTEX / 255 <= 1.0)


if __name__ == "__main__":
    unittest.main()
