"""U.S. Bank Stadium model (st3): geometry, the roof, the west end, the boards' feed crop, markers, cameras, the field
with the added midfield quad, and the builder's secondary push words."""
import json
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

from mod_editor.core import nfl2k5_usbank_model as um  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = um.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 24000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_field_wall_clears_the_sideline_props(self):
        """The wall stays outside the retail s15 sideline props (x -41.5 to 41.4; one away piece reaches z 63.3)."""
        loop = self.model.loop
        side = [lp for lp in loop if abs(lp.z) < 40]
        self.assertGreaterEqual(min(lp.x for lp in side if lp.x > 0), 42.5)
        self.assertLessEqual(max(lp.x for lp in side if lp.x < 0), -42.5)
        end = [lp for lp in loop if abs(lp.x) < 12]
        self.assertGreaterEqual(min(lp.z for lp in end if lp.z > 0), 64.3)
        self.assertLessEqual(max(lp.z for lp in end if lp.z < 0), -64.3)

    def test_the_stacks_fit_inside_the_facade(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in um.footprint()["facade"]]
        for lp, sec in zip(self.model.loop, self.model.secs):
            if "rim" not in sec:
                continue
            x, _y, z = self.model.at(lp, sec["rim"][3], 0.0)
            self.assertTrue(sm._point_in_poly(x, z, ring), (round(x, 1), round(z, 1)))

    def test_the_roof_covers_the_bowl_and_rises_to_the_prow(self):
        """The roof's underside stays at least 3 m over every rim's top; the ridge rises from the east to the west and the
        prow's tip is the roof's highest point (205 ft at the east, 272 ft at the prow over the street, GRADE over the
        field)."""
        m = self.model
        for lp, sec in zip(m.loop, m.secs):
            x, _y, z = m.at(lp, sec["rim"][0], 0.0)
            self.assertGreater(m.roof_under(x, z), sec["rim"][2] + 3.0, (round(x, 1), round(z, 1)))
        q = um.PARAMS["roof"]
        self.assertLess(m.roof_top(q["ridge_x"], 100.0), m.roof_top(q["ridge_x"], -100.0))
        tip = m.prow_tip()
        self.assertAlmostEqual(m.roof_top(*tip), q["tip"], places=6)
        self.assertAlmostEqual(q["tip"] - um.GRADE, 272 * 0.3048, delta=0.1)
        self.assertAlmostEqual(q["ridge_e"] - um.GRADE, 205 * 0.3048, delta=0.1)

    def test_the_west_end_is_the_lower_bowl_alone(self):
        for lp, sec in zip(self.model.loop, self.model.secs):
            if self.model.west_zone(lp):
                self.assertNotIn("upper", sec)

    def test_the_u044_camera_stands_in_the_east_upper_deck(self):
        """The 2023 photo u044 solves to an eye 33.7 m up, 41.7 m behind the east wall at x 30.9 (PnP on the field lines,
        rms 12 px): the east upper deck's tread under that eye lies 0.8 to 2.5 m below it (pass 1 had the deck's front
        at the eye, the grey slab main saw on the pass 1 sheet)."""
        m = self.model
        eye = np.array([30.89, 33.66, 106.72])
        lp = min((lp for lp in m.loop if lp.w["E"] > 0.99), key=lambda l: abs(l.x - eye[0]))
        sec = m.section(lp)
        up = sec["upper"]
        d = eye[2] - lp.z
        k = min(range(len(up)), key=lambda i: abs(up[i][0] - d))
        self.assertTrue(0.8 <= eye[1] - up[k][1] <= 2.5, (d, up[k]))

    def test_the_gutters_run_level(self):
        """Both slopes fall to level gutters (the aerials u053 to u055) while the ridge rises 13.5 m toward the prow:
        along the south and the north outline the roof's edge varies by under 4 m, and the ridge stands north of the
        field's axis (the ETFE, south of it, is the larger share)."""
        m = self.model
        q = um.PARAMS["roof"]
        for side, pick, eave, at in (("S", lambda p: p[0] < -100.0, q["eave_s"], q["eave_x"]),
                                     ("N", lambda p: p[0] > 100.0 and -80.0 < p[1] < 60.0, q["eave_n"], q["eave_xn"])):
            pts = [p for p in m.outline() if pick(p)]
            tops = [m.roof_top(float(x), float(z)) for x, z in pts]
            self.assertGreater(len(pts), 3, side)
            self.assertLess(max(tops) - min(tops), 4.0, side)
            self.assertAlmostEqual(m.roof_top(at, 0.0), eave, places=6)
        self.assertGreater(q["ridge_x"], 0.0)
        self.assertGreater(q["ridge_x"] - q["eave_x"], q["eave_xn"] - q["ridge_x"])

    def test_the_blade_carries_the_wordmark_and_the_display(self):
        """The prow's blade is the triangle between the tip, the glass wall's top and its foot (u036, u047); the wordmark
        and the display sit inside it, clear of its lower edge and of the roof."""
        m = self.model
        blade, nw = m._prow_edges()
        self.assertIsNotNone(blade)
        self.assertGreaterEqual(len(nw), 1)
        a, b, _n, _w = m._edges()[blade]
        L = float(np.linalg.norm(b - a))
        self.assertEqual(len(m.prow_boxes), 2)
        for mat, s0, s1, y0, y1 in m.prow_boxes:
            self.assertGreaterEqual(s0, 0.0, mat)
            for s_ in (s0, s1):
                p = a + (b - a) * (s_ / L)
                self.assertGreaterEqual(y0, m.blade_edge(s_) - 1e-6, (mat, s_))
                self.assertLessEqual(y1, m.roof_top(float(p[0]), float(p[1])) - 1.0, (mat, s_))
        (_m1, _a1, _b1, ly0, _ly1), (_m2, _a2, _b2, _dy0, dy1) = m.prow_boxes
        self.assertLess(dy1, ly0)

    def test_the_east_board_hangs_at_the_club_level(self):
        """The east board sits between the lower bowl and the upper deck (u003, u019: the upper deck's seats show over
        it); its top within 4 m of the upper deck's front, clear of the lower bowl's rows and of the club tier."""
        m = self.model
        east = m.board_frames[1]
        q = um.PARAMS["boards"]
        lp = min((lp for lp in m.loop if lp.w["E"] > 0.99), key=lambda l: abs(l.x))
        sec = m.section(lp)
        up_front = sec["upper"][0]
        top = q["e_y"] + q["e_h"]
        self.assertLess(abs(top - up_front[1]), 4.0)
        d_front, d_back = q["e_z"] - q["depth"] / 2 - lp.z, q["e_z"] + q["depth"] / 2 - lp.z
        lower = [r for r in sec["lower"] if d_front - 1.0 <= r[0] <= d_back + 1.0]
        self.assertTrue(lower)
        self.assertGreater(q["e_y"] - 0.6, max(r[1] for r in lower) + 1.5)
        self.assertLess(d_back, sec["t2"][0][0])
        self.assertAlmostEqual(float(east["centre"][2]), q["e_z"], places=6)

    def test_the_wall_panels_hang_inside_under_the_roof(self):
        """The banner, the 3M panel and the Land O'Lakes panel stand inside the outline and under the roof."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        m = self.model
        ring = [tuple(p) for p in m.outline()]
        mesh = m.meshes["usb_east"]
        for mat in ("LIGHT_usb_blue_sign", "LIGHT_usb_panels"):
            idx = {i for st in mesh.groups[mat] for i in st}
            for i in idx:
                x, y, z = mesh.P[i]
                self.assertTrue(sm._point_in_poly(x, z, ring), (mat, round(x, 1), round(z, 1)))
                self.assertLess(y, m.roof_under(x, z) - 1.0, (mat, round(y, 1)))

    def test_the_flag_hangs_with_the_union_at_the_top_left(self):
        """Seen from the field the hung flag's union is at its top left: the front quad's top-left corner maps to the
        texture's union corner (0, 0) and its top edge runs across the stripes (v)."""
        mesh = self.model.meshes["usb_flag"]
        strip = mesh.groups["usb_flag"][0]
        P = [np.array(mesh.P[i]) for i in strip]
        UV = [mesh.UV[i] for i in strip]
        face = -np.array([P[0][0], 0.0, P[0][2]]); face /= np.linalg.norm(face)
        right = -np.cross(face, (0.0, 1.0, 0.0)); right /= np.linalg.norm(right)
        top = max(p[1] for p in P)
        tops = [(float(p @ right), uv) for p, uv in zip(P, UV) if abs(p[1] - top) < 1e-6]
        tops.sort()
        self.assertEqual(tuple(tops[0][1]), (0, 0))
        self.assertEqual(tuple(tops[-1][1]), (0, 1))

    def test_every_sign_reads_left_to_right(self):
        """Seen from the side it faces, every sign's, board's and panel's texture runs left to right (u grows toward the
        viewer's right): the pass 2 fascia bands were mirrored (the flyover's dolly, 2026-09-27)."""
        text = ("LIGHT_usb_signs", "usb_letters", "usb_header", "LIGHT_usb_blue_sign", "LIGHT_usb_panels",
                "usb_prow_letters", "LIGHT_usb_prow_display", "jumbo_tron", "LIGHT_usb_board_wing")
        seen = 0
        for mesh in self.model.meshes.values():
            for mat in text:
                for strip in mesh.groups.get(mat, ()):
                    if len(strip) != 4:
                        continue
                    n = np.array(mesh.N[strip[0]])
                    if abs(n[1]) > 0.9:
                        continue
                    right = -np.cross(n, (0.0, 1.0, 0.0))
                    right /= np.linalg.norm(right)
                    lo = min(strip, key=lambda i: (mesh.UV[i][0], mesh.UV[i][1]))
                    hi = max(strip, key=lambda i: (mesh.UV[i][0], -mesh.UV[i][1]))
                    self.assertGreater(float((np.array(mesh.P[hi]) - np.array(mesh.P[lo])) @ right), 0.0,
                                       (mesh.name, mat))
                    seen += 1
        self.assertGreater(seen, 15)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_materials(self):
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"usb_seat_front", "usb_seat_mid", "usb_seat_back", "crowd", "usb_etfe_under", "usb_roof_under",
                         "usb_truss", "LIGHT_usb_glasswall", "usb_zinc", "usb_prow_letters", "LIGHT_usb_prow_display",
                         "usb_header", "LIGHT_usb_board_wing", "LIGHT_usb_towers", "usb_sky", "usb_roof_letters",
                         "usb_flag", "LIGHT_usb_blue_sign", "LIGHT_usb_panels", "LIGHT_usb_clerestory"} <= mats)
        self.assertTrue(mats <= set(um.MATERIALS) | {"crowd", "jumbo_tron"}, mats - set(um.MATERIALS))

    def test_the_boards_show_the_feed_at_the_pictures_aspect(self):
        """Each board shows a crop of the 640 x 448 feed picture (u 0 to 0.625, v 0 to 0.875) at its own aspect."""
        q = um.PARAMS["boards"]
        for aspect in (q["w_w"] / q["w_h"], q["e_w"] / q["e_h"]):
            (u0, u1), (v0, v1) = self.model.board_crop(aspect)
            self.assertGreaterEqual(u0, 0.0); self.assertLessEqual(u1, 0.625 + 1e-9)
            self.assertGreaterEqual(v0, 0.0); self.assertLessEqual(v1, 0.875 + 1e-9)
            self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), aspect, places=3)
        feeds = [strip for m in self.model.meshes.values() for strip in m.groups.get("jumbo_tron", ())]
        self.assertEqual(len(feeds), 2)

    def test_the_boards_stand_at_the_ends(self):
        """The west board (68 x 120 ft) facing east over the west concourse, its bottom 20.4 m over the field (the solved
        2023 end-zone photo); the east board (51 x 88 ft) facing west."""
        west, east = self.model.board_frames
        self.assertLess(float(west["centre"][2]), -100.0)
        self.assertAlmostEqual(float(west["face"][2]), 1.0, places=6)
        self.assertAlmostEqual(float(west["centre"][1]), 20.4, places=6)
        self.assertAlmostEqual(west["width"], 120 * 0.3048, delta=0.05)
        self.assertAlmostEqual(west["height"], 68 * 0.3048, delta=0.05)
        self.assertGreater(float(east["centre"][2]), 90.0)
        self.assertAlmostEqual(float(east["face"][2]), -1.0, places=6)
        self.assertAlmostEqual(east["width"], 88 * 0.3048, delta=0.05)
        self.assertEqual(len(west["panels"]), 2)

    def test_markers_positions(self):
        self.assertEqual(len(self.model.markers["jumbo"]), 2)
        self.assertGreaterEqual(len(self.model.light_points), 16)
        pts = um.flare_points(self.model)
        self.assertEqual(len(pts), 4)
        self.assertEqual(len({(round(p[0]), round(p[2])) for p in pts}), 4)


class Cameras(unittest.TestCase):
    def test_no_shot_lets_the_feed_screens_fill_the_view(self):
        """The feed screens show the game's own frame, so a shot the screens fill feeds back to solid white (st, PROVED IN
        GAME at AT&T Stadium, 2026-09-27): over every shot's 8 s path the screens cover at most 25 % of the frame."""
        from mod_editor.core import nfl2k5_usbank_model as usb
        model = um.build()
        for k, shot in enumerate(um.usbank_shots()):
            worst, _trace = usb.feed_coverage(model, shot)
            self.assertLessEqual(worst, usb.FEED_COVERAGE_LIMIT, (k + 1, round(worst, 3)))

    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(um.usbank_shots(), um.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            if "pitch" not in present:
                self.assertEqual(shot["pitch"], 0.0)
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        model = um.build()
        flares = [np.array(p, float) for p in um.flare_points(model)]
        for p in flares:
            self.assertGreater(p[1], 250.0)
        for k, shot in enumerate(um.usbank_shots()):
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
        outside = [s for s in um.usbank_shots() if max(abs(s["eye"][0]), abs(s["eye"][2])) > 150]
        self.assertGreaterEqual(len(outside), 2)

    def test_eyes_stay_in_the_open(self):
        model = um.build()
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P and m.name != "usb_sky"])
        for k, s in enumerate(um.usbank_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        retail = um.read_retail(EXTRACTED)
        for name in ("s15dd.iff", "s15ns.iff"):
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), um.CAMERA_COMPONENTS_PRESENT, name)

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_animated_field_of_view_holds_the_shots(self):
        """s15's camera 1 animates its field of view (multi-segment): the writer holds every segment at the shot's."""
        from mod_editor.core import nfl2k5_metlife_model as mm
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        retail = um.read_retail(EXTRACTED)
        _c, dec = mm._cameras_chunk(retail["s15dd.iff"])
        shots = um.usbank_shots()
        out = um.write_cameras(dec, shots)
        info = mm.parse_cameras(out)
        seen = 0
        for ch in info["channels"]:
            if ch["field"] != 0x50:
                continue
            for comp in ch["comps"]:
                if "const" in comp:
                    continue
                for seg in range(comp["count"]):
                    self.assertEqual(struct.unpack_from("<4f", out, comp["segs"] + 16 * seg)[3],
                                     np.float32(shots[ch["camera"]]["fov"]))
                    seen += 1
        self.assertGreater(seen, 0)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class SceneMarkers(unittest.TestCase):
    @requires_real_pack("modern_usbank")
    def test_no_marker_registers_a_glow(self):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        retail = um.read_retail(EXTRACTED)
        for name in ("s15dd.iff", "s15nd.iff"):
            sc = um.build_scene(retail[name], name, um.build())
            self.assertFalse([m.name for m in sc.markers if "light" in m.name], name)
            self.assertTrue([m.name for m in sc.markers if m.name.startswith("marker_lamp")], name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Field(unittest.TestCase):
    def test_secondary_push_words(self):
        """The builder refuses a field scene's secondary push words by default (every scene built before keeps its bytes)
        and carries them verbatim when asked (a round trip keeps every stream, word and texture)."""
        from mod_editor.core import nfl2k5_scne_builder as sb
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        retail = um.read_retail(EXTRACTED)
        data = retail["s15dd.iff"]
        c = ml.bundle_scenes(data)["field"]
        _rec, dec = ml._scene(data, c)
        with self.assertRaises(sb.ScneBuildError):
            sb.parse(dec, c.system_bytes)
        sc = sb.parse(dec, c.system_bytes, secondary=True)
        out, system, _video = sb.serialize(sc)
        sc2 = sb.parse(out, system, secondary=True)
        self.assertEqual([s.streams for s in sc.shapes], [s.streams for s in sc2.shapes])
        self.assertEqual([[x.words for x in s.submeshes] for s in sc.shapes], [[x.words for x in s.submeshes] for s in sc2.shapes])
        self.assertEqual([t.pixels for t in sc.textures], [t.pixels for t in sc2.textures])

    def test_the_field_carries_the_midfield_head(self):
        """The painted field with the u4 art's ``center_logo``: a 15.2 m quad at the centre spot with the mark's top
        toward +x and its right toward +z; the span keeps its stored size and the retail scratch word."""
        from mod_editor.core import nfl2k5_scne_builder as sb
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        tx = ml._tools()[0]
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        retail = um.read_retail(EXTRACTED)
        name = "s15dd.iff"
        chunk = ml.bundle_scenes(retail[name])["field"]
        logo = np.zeros((256, 256, 4), np.uint8)
        logo[:128, :, :] = (250, 200, 40, 255)                 # the mark's top half gold
        team = {"endzone_N_M": np.full((128, 256, 4), (79, 38, 131, 255), np.uint8), "center_logo": logo}
        span, info = um.field_span(retail[name], name, team=team)
        self.assertEqual(len(span), 32 + chunk.stored_size)
        self.assertEqual(tx.HEADER.unpack_from(span, 0)[5], tx.HEADER.unpack_from(ml.scene_span(retail[name], chunk), 0)[5])
        self.assertIsNotNone(info["midfield"])
        dec, _i = tx.decode_chunk(span, tx.parse_chunks(span, allow_trailing=True)[0])
        head = tx.HEADER.unpack_from(span, 0)
        sc = sb.parse(dec, head[2], secondary=True)
        ov = sc.shape("D_graphic_overlays")
        mat = sc.material_index(um.MIDFIELD_MATERIAL)
        (sub,) = [s for s in ov.submeshes if s.material == mat]
        idx = sorted({i for _m, ix in sb.decode_words(sub.words) for i in ix})
        P = np.array([struct.unpack_from("<3f", ov.streams[0], 12 * i) for i in idx]) / 100.0
        self.assertAlmostEqual(float(P[:, 0].max()), um.MIDFIELD_HALF, places=4)
        self.assertAlmostEqual(float(P[:, 2].min()), -um.MIDFIELD_HALF, places=4)
        su, sv, ou, ov_ = struct.unpack_from("<4f", ov.record, 0x30)
        for i, p in zip(idx, P):
            _b, _g, _r, _a, qu, qv, _z = struct.unpack_from("<4B2hh", ov.streams[1], 10 * i)
            u, v = qu / 32767.0 * su + ou, qv / 32767.0 * sv + ov_
            self.assertAlmostEqual(u, 0.0 if p[2] < 0 else 1.0, places=2)      # the mark's right toward +z
            self.assertAlmostEqual(v, 0.0 if p[0] > 0 else 1.0, places=2)      # the mark's top toward +x



@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class VenueRow(unittest.TestCase):
    def test_the_row_names_us_bank_and_keeps_the_dome(self):
        from mod_editor.core import nfl2k5_usbank_venue as uv
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_roster_records as rr
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = archive.entries[uv.ROST_OUTER_INDEX]
            data = archive.read(e.virtual_offset, e.size)
        self.assertEqual(uv.rost_state(data), "retail")
        after, receipt = uv.rost_usbank(data)
        self.assertEqual(len(after), len(data))
        self.assertEqual(uv.rost_state(after), "applied")
        again, _receipt2 = uv.rost_usbank(after)
        self.assertEqual(again, after)
        H = rr.RESOURCE_HEADER_SIZE
        changed = [i - H for i, (a, b) in enumerate(zip(data, after)) if a != b]
        self.assertTrue(changed)
        rec_off = receipt["records"][0]["record_offset"]
        block = receipt["records"][0]["block"]
        for i in changed:
            self.assertTrue(block[0] <= i < block[1] or rec_off <= i < rec_off + 0x80, i)
        # the indoor word stays 1 (the fixed roof), the surface word 0 (synthetic turf), the climate untouched
        body = after[H:]
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x18)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x1C)[0], 0)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x04)[0], uv.CAPACITY)
        self.assertEqual(body[rec_off + 0x28:rec_off + 0x7C], data[H:][rec_off + 0x28:rec_off + 0x7C])
        # composes with the 2026 venue renames in either order
        a, _ = mv.rost_rename(after)
        b, _ = uv.rost_usbank(mv.rost_rename(data)[0])
        self.assertEqual(a, b)


def _team_art():
    logo = np.zeros((256, 256, 4), np.uint8)
    logo[:128, :, :] = (250, 200, 40, 255)
    return {"endzone_N_M": np.full((128, 256, 4), (79, 38, 131, 255), np.uint8), "center_logo": logo}


class _Entry:
    def __init__(self, size):
        self.virtual_offset, self.size = 0, size


class _Archive:
    def __init__(self, data):
        self.data = bytes(data)

    def read(self, offset, size):
        return self.data[offset:offset + size]


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class SurfacesComposition(unittest.TestCase):
    """This option's field already stands on tf's palette (modern_surfaces' own painter, composed after the end zones);
    with Modern surfaces on as well (the last stadium writer), the new field keeps tf's colours, its midfield head and
    reads applied under tf's deep status (main, 2026-09-27)."""

    @classmethod
    @requires_real_pack("modern_usbank")
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        retail = um.read_retail(EXTRACTED)
        cls.name = name = "s15nd.iff"
        _n, model, _i = um._compile((name, retail[name], retail[um.dry_of(name)]))
        field, cls.info = um.field_span(retail[name], name, team=_team_art())
        chunk = ml.bundle_scenes(retail[name])["field"]
        cls.ours = model[:chunk.offset] + field + model[chunk.offset + len(field):]
        cls.after, cls.rec = ms.surface_bundle(cls.ours, name, indoor=True)

    def test_the_field_is_on_tfs_palette(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        surf = self.info["surface"]
        look = ms.venue_look("s15")
        self.assertEqual((surf["look"], surf["light"], surf["layout"]), (look, "dome", "quad"))
        self.assertEqual(tuple(surf["target"]), tuple(round(v, 2) for v in ms.venue_target("s15", look, "dome")))

    def test_modern_surfaces_keeps_this_field(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        self.assertEqual(len(self.after), len(self.ours))
        self.assertFalse(self.rec["field"]["refit"])
        at, size = ms.bundle_sites(self.ours)["field"]
        self.assertEqual(self.after[at:at + size], self.ours[at:at + size])
        self.assertEqual(self.rec["field"]["map_mean"], self.info["surface"]["map_mean"])
        self.assertEqual(ms.surface_bundle(self.after, self.name, indoor=True)[0], self.after)

    def test_the_deep_status_reads_applied(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        row = ms.bundle_report(_Archive(self.after), self.name, _Entry(len(self.after)), None, deep=True)
        self.assertEqual(row["state"], "applied", row)
        self.assertIn("planar field UVs", row["reason"])
        mine = ms.bundle_report(_Archive(self.ours), self.name, _Entry(len(self.ours)), None, deep=True)
        self.assertEqual(mine["state"], "retail", mine)          # this option alone: not surfaced (retail normal)



class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s15_to_us_bank(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s15", "s25", "s07", "s03", "s22")}, league={"nfl_shield": {}}, skipped=[])
        with_usbank = [p for p, _t in mv.venues_to_write(art, usbank=True)]
        without = [p for p, _t in mv.venues_to_write(art)]
        self.assertIn("s15", without)
        self.assertNotIn("s15", with_usbank)
        self.assertEqual(set(without) - set(with_usbank), {"s15"})
        every = [p for p, _t in mv.venues_to_write(art, att=True, levis=True, highmark=True, sofi=True, usbank=True)]
        self.assertEqual(set(without) - set(every), {"s15", "s25", "s07", "s03", "s23", "s24"})

    def test_option_is_off_in_every_preset(self):
        from mod_editor.core import mod_build
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_usbank"), False, name)
        self.assertIn("modern_usbank", mod_build.availability())
        from mod_editor.core import nfl2k5_build_settings as bs
        self.assertIn("modern_usbank", bs.FEATURE_KEYS)

    def test_the_build_runs_it_after_the_venue_art_and_before_modern_surfaces(self):
        """The Build writes the Vikings' packages after Modern colour and the 2026 venue art and before Modern surfaces,
        the last stadium writer (which keeps this field's paint: SurfacesComposition)."""
        import inspect
        from mod_editor.core import mod_build
        src = inspect.getsource(mod_build)
        steps = [src.index(f'{{"step": "{k}"') for k in ("modern_venues_2026", "modern_levis", "modern_usbank",
                                                         "modern_surfaces")]
        self.assertEqual(steps, sorted(steps))

    @requires_real_pack("modern_usbank")
    def test_the_4x_pack_names_a_master_for_every_material(self):
        """The Edition pack's masters carry the same names as the native art: the sky per time of day and the night
        drawings in the night bundles."""
        import nfl2k5_usbank_model_pack as pack
        from mod_editor.core import nfl2k5_stadium_environment as env
        for tod in "dan":
            for material in um.MATERIALS:
                rel = pack.master_for(material, None, tod)
                art = env.ART_DIR if material.startswith("env_") else um.ART_DIR
                self.assertTrue(um.official.resolve_path(art / rel).is_file(), (tod, material, rel))


@unittest.skipUnless(EXTRACTED.is_dir() and um.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    @requires_real_pack("modern_usbank")
    def test_compiled_stretches_equal_their_pins(self):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        retail = um.read_retail(EXTRACTED)
        for name in ("s15dd.iff", "s15ns.iff"):
            model, info = um.model_bundle(retail[name], name, um.build(), cameras=um.usbank_shots(),
                                          dry_bundle=retail[um.dry_of(name)])
            self.assertEqual(len(model), len(retail[name]))
            start, end = um.stretch(retail[name])
            pin = um._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(um.sha(model[start:end]), pin["model_sha256"], name)
            self.assertEqual(um.sha(retail[name][start:end]), pin["retail_sha256"])
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"])

    def test_every_bundle_is_pinned_and_under_retail(self):
        pins = um.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(um.VARIANTS))
        for p in pins["bundles"]:
            self.assertLess(p["vertices"], 30000)
        text = um.PINS_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")

    def test_the_registry_row_pins_the_first_and_last_stretch(self):
        registry = json.loads((ROOT / "mod_editor" / "capabilities" / "registry.v1.json").read_text(encoding="utf-8"))
        row = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.stadiums_fields.modern_usbank")
        first, last = um._pin("s15dd.iff"), um._pin("s15ns.iff")
        self.assertEqual(row["source_container"]["hash_pins"], [first["retail_sha256"], first["model_sha256"],
                                                                 last["retail_sha256"], last["model_sha256"]])
        self.assertIs(row["gui"]["default_enabled"], False)


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        """Every authored PNG ships as an exact reviewed catalog entry, and the release checker pins the catalog."""
        import hashlib
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted(um.ART_DIR.rglob("*.png"))
        manifest = json.loads((um.ART_DIR / "art.json").read_text(encoding="utf-8"))["art"]
        from mod_editor.core import nfl2k5_official_marks as official
        external = [p for p in official.CATALOG if p.startswith("data/nfl2k5_usbank_model/art/")]
        self.assertEqual(len(pngs) + len(external), len(manifest))
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            with Image.open(png) as image:
                self.assertEqual((row["width"], row["height"]), image.size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_usbank_model.py", "mod_editor/core/nfl2k5_usbank_venue.py",
                    "data/nfl2k5_usbank_model/footprint.json", "data/nfl2k5_usbank_model/pins.json",
                    "data/nfl2k5_usbank_model/art/art.json"):
            self.assertIn(rel, allow)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"', checker)


if __name__ == "__main__":
    unittest.main()
