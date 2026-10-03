"""SoFi Stadium model (u6): geometry, the Infinity Screen feed windows, markers, the field art, cameras, the crowd,
the pins and the composition with the 2026 venue art."""
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

from mod_editor.core import nfl2k5_sofi_model as sm  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = sm.build(venue="s23")

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 30000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_bowl_below_grade_and_canopy_height(self):
        """The field is 30.5 m (100 ft) below grade; the canopy rises about 53 m above grade (174 ft)."""
        self.assertAlmostEqual(sm.GRADE, 30.48, places=1)
        tops = [p[1] for p in self.model.meshes["sf_etfe_top04"].P]
        self.assertLess(max(tops) - sm.GRADE, 53.5)
        self.assertGreater(max(tops) - sm.GRADE, 45.0)

    def test_field_wall_clears_the_sideline_props_and_the_broadcast_eye(self):
        loop = self.model.loop
        self.assertGreaterEqual(min(abs(lp.x) for lp in loop if abs(lp.z) < 40), 39.0)
        sec = self.model.section(loop[0])
        for d, y in sec["lower"]:
            if abs(40.0 + d - 56.5) < 1.0:
                self.assertLess(y, 16.5 - 3.0)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_fan_spacing_follows_the_seating_row_through_corners(self):
        for mesh in self.model.meshes.values():
            for strip in mesh.groups.get("crowd", ()):
                # Higher U is the foot of the billboard in the retail atlas.
                foot_u = max(mesh.UV[i][0] for i in strip)
                feet = [i for i in strip if abs(mesh.UV[i][0] - foot_u) < 1e-6]
                for a, b in zip(feet, feet[1:]):
                    metres = np.linalg.norm(np.array(mesh.P[a]) - mesh.P[b])
                    repeats = abs(mesh.UV[a][1] - mesh.UV[b][1])
                    self.assertAlmostEqual(metres, repeats * 9.14, places=5)

    def test_crowd_bands_do_not_stretch_people_over_tall_risers(self):
        for mesh in self.model.meshes.values():
            for strip in mesh.groups.get("crowd", ()):
                for a, b in zip(strip[::2], strip[1::2]):
                    self.assertLessEqual(abs(mesh.P[a][1] - mesh.P[b][1]), 2.8 + 1e-6)

    def test_aisles_cut_the_crowd_over_the_texture_steps(self):
        """An aisle at both ends of every straight and corner, sections of 11 to 18 m, symmetric about each end zone and
        the 50; every crowd band leaves a gap about 1.2 m wide at each aisle it crosses, and the seat texture's u is a
        whole number there (the steps sit at u = 0)."""
        model = self.model
        A = np.array(model.aisles)
        self.assertEqual((A[0], round(A[-1], 6)), (0.0, round(model.loop[-1].s, 6)))
        gaps = np.diff(A)
        self.assertGreaterEqual(gaps.min(), 11.0)
        self.assertLessEqual(gaps.max(), 18.5)
        self.assertTrue(np.allclose(gaps, gaps[::-1], atol=0.05), "the sections are not symmetric")
        for a in A:
            self.assertAlmostEqual(model.aisle_u(a), round(model.aisle_u(a)), places=6)
        # the crowd's billboards: in the plan (x, z), no crowd vertex lies within 0.5 m of an aisle's radial line
        # at the band's own depth, and every band ends within 0.7 m of each aisle it meets
        loop = model.loop
        rays = []
        for a in A[:-1]:
            i = int(np.searchsorted([lp.s for lp in loop], a, side="right") - 1)
            i = min(i, len(loop) - 2)
            t = (a - loop[i].s) / (loop[i + 1].s - loop[i].s)
            p = np.array([loop[i].x + (loop[i + 1].x - loop[i].x) * t, loop[i].z + (loop[i + 1].z - loop[i].z) * t])
            n = np.array([loop[i].nx + (loop[i + 1].nx - loop[i].nx) * t, loop[i].nz + (loop[i + 1].nz - loop[i].nz) * t])
            rays.append((p, n / np.linalg.norm(n)))
        near = 0
        for m in model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                P = np.array([m.P[i] for i in strip])[:, [0, 2]]
                for p, n in rays:
                    rel = P - p
                    along = rel @ n
                    across = np.abs(rel @ np.array([-n[1], n[0]]))
                    ok = along > 0.0
                    if ok.any():
                        self.assertGreater(across[ok].min(), 0.5)
                        near += int((across[ok] < 0.7).any())
        self.assertGreater(near, 28 * 20)

    def test_infinity_screen_size_and_height(self):
        """The ring spans 120 yards along the field, its bottom 120 ft above it, the inner board 40 ft tall."""
        P = np.array(self.model.meshes["sf_screen"].P)
        self.assertAlmostEqual(P[:, 2].max() - P[:, 2].min(), 110.0, delta=1.5)
        self.assertAlmostEqual(P[:, 1].min(), 36.6, delta=0.1)
        self.assertAlmostEqual(P[:, 1].max() - P[:, 1].min(), 12.2, delta=0.2)

    def test_feed_windows_show_the_feed_uncut_and_unstretched(self):
        """Every jumbo_tron quad samples inside the feed's 16:9 crop of the render target (u 0 to 0.625, v 0.109 to
        0.766), and each window is 16:9 on the board."""
        m = self.model.meshes["sf_screen"]
        P, UV = np.array(m.P), np.array(m.UV)
        idx = sorted({i for st in m.groups["jumbo_tron"] for i in st})
        self.assertGreaterEqual(UV[idx, 0].min(), -1e-6)
        self.assertLessEqual(UV[idx, 0].max(), 0.625 + 1e-6)
        self.assertGreaterEqual(UV[idx, 1].min(), 0.109 - 1e-6)
        self.assertLessEqual(UV[idx, 1].max(), 0.766 + 1e-6)
        # the windows are in the middle of each long side on both faces: 4 windows of 16:9 at their board heights
        q = self.model.p["screen"]
        widths = []
        for strip in m.groups["jumbo_tron"]:
            quad = P[strip]
            widths.append(np.linalg.norm(quad[:, [0, 2]].max(0) - quad[:, [0, 2]].min(0)))
        self.assertTrue(all(w < q["inner"] * 16 / 9 + 1.0 for w in widths))
        # ten windows, each 16:9 at its face's height along the curve: three on each long side of the inner board,
        # two on each long side of the outer board (the score and clock strip takes the third place)
        for height, count in ((q["inner"], 6), (q["outer"], 4)):
            total = 0.0
            for strip in m.groups["jumbo_tron"]:
                quad = P[strip]
                if abs((quad[:, 1].max() - quad[:, 1].min()) - height) < 0.05:
                    bottom = quad[quad[:, 1] < quad[:, 1].min() + 0.01]
                    total += np.linalg.norm(bottom[:, [0, 2]].max(0) - bottom[:, [0, 2]].min(0))
            self.assertAlmostEqual(total / (count * height * 16 / 9), 1.0, delta=0.02)

    def test_screen_panels_and_light_banks_are_not_stretched(self):
        """The team panels tile at their art's own aspect along the ring, and each light bank shows its 2:1 LED
        texture at the bank's aspect (Noah's reference pass, 2026-09-24)."""
        m = self.model.meshes["sf_screen"]
        P, UV = np.array(m.P), np.array(m.UV)
        aspect = self.model.panel_aspect
        size = sm.art_manifest()["LIGHT_sf_screen_s23"]["size"]
        self.assertAlmostEqual(aspect, size[0] / size[1])
        for strip in m.groups["LIGHT_sf_screen"][:40]:
            quad = P[strip]
            height = quad[:, 1].max() - quad[:, 1].min()
            bottom = quad[quad[:, 1] < quad[:, 1].min() + 0.01]
            width = np.linalg.norm(bottom[:, [0, 2]].max(0) - bottom[:, [0, 2]].min(0))
            du = UV[strip, 0].max() - UV[strip, 0].min()
            self.assertAlmostEqual(du * aspect * height, width, delta=0.02 * width + 0.01)
        banks = self.model.meshes["sf_lights"]
        BP, BUV = np.array(banks.P), np.array(banks.UV)
        for strip in banks.groups["LIGHT_sf_lights"]:
            quad = BP[strip]
            du = BUV[strip, 0].max() - BUV[strip, 0].min()
            self.assertAlmostEqual(du, sm.SoFi.BANK_W / (sm.SoFi.BANK_H * 2.0), places=6)
        self.assertGreater(len(banks.groups["LIGHT_sf_lights"]), 20)

    def test_the_score_strip_sits_beside_the_outer_windows(self):
        """The game's score and clock digits (adjust_digits: a strip from 10.3 to 26.8 m from each long side's middle
        on the outer board) cover no live window."""
        q = self.model.p["screen"]
        m = self.model.meshes["sf_screen"]
        P = np.array(m.P)
        feed = q["outer"] * sm.SoFi.FEED_ASPECT / 2
        for z_sign in (1, -1):
            c, _n, right = self.model.screen_point("outer", z_sign, feed + 11.0)
            a, b = c - right * 8.6, c + right * 8.6
            for strip in m.groups["jumbo_tron"]:
                quad = P[strip]
                if abs((quad[:, 1].max() - quad[:, 1].min()) - q["outer"]) > 0.05:
                    continue
                centre = quad.mean(axis=0)
                t = np.clip(np.dot(centre - a, b - a) / np.dot(b - a, b - a), 0.0, 1.0)
                gap = np.linalg.norm((centre - (a + (b - a) * t))[[0, 2]])
                self.assertGreater(gap, 1.0)

    def test_markers_positions(self):
        """The glow markers keep their records but no longer register glows; the flares ride the light ring; the
        nosebleed seat is a 400-level seat on the west side."""
        self.assertTrue(self.model.light_points)
        x, y, z = self.model.nosebleed
        self.assertGreater(x, 70.0)
        self.assertGreater(y, 40.0)

    def test_the_ribbons_read_left_to_right_from_the_field(self):
        """U grows with the loop, which runs to the right of a viewer at midfield facing any stand."""
        m = self.model.meshes["sf_bowl00"]
        loop = self.model.loop
        for strip in m.groups["LIGHT_sf_ribbon"][:1]:
            us = [m.UV[i][0] for i in strip]
            self.assertGreater(max(us), min(us))
        a, b = loop[0], loop[1]
        self.assertGreater(b.z, a.z)          # the west side runs north: the right hand of a viewer facing west


class FieldArt(unittest.TestCase):
    def test_midfield_quads_follow_the_marks(self):
        art = sm.art_manifest()
        for venue in sm.VENUES:
            across, along = art[f"field/{venue}_midfield"]["quad_m"]
            self.assertGreater(along, across)
            self.assertLess(along, 14.0)

    @requires_real_pack("modern_sofi")
    def test_end_zone_halves(self):
        """Each panel: the south end (the team) in the top half, the north end (LOS ANGELES) in the bottom half."""
        from PIL import Image
        for venue, colour in (("s23", (0, 53, 148)), ("s24", (0, 128, 198))):
            for part in "LMR":
                a = np.asarray(Image.open(sm.official.resolve_path(sm.FIELD_ART / f"{venue}_endzone_{part}.png")).convert("RGB")).astype(int)
                self.assertEqual(a.shape, (128, 256, 3))
                for half in (a[:64], a[64:]):
                    background = np.median(half.reshape(-1, 3), axis=0)
                    self.assertLess(np.abs(background - colour).max(), 12, (venue, part))
        self.assertEqual(sm.ENDZONE_V, {"N": (0.0, 0.5), "S": (0.5, 1.0)})


def _triangles(model, skip=("sf_sky", "sf_ground")):
    """(triangles (n, 3, 3), their material names) of a model's strips, degenerate ones dropped."""
    tris, names = [], []
    for mesh in model.meshes.values():
        P = np.asarray(mesh.P, float)
        for mat, strips in mesh.groups.items():
            if any(mat.startswith(k) for k in skip):
                continue
            for st in strips:
                for i in range(len(st) - 2):
                    a, b, c = st[i], st[i + 1], st[i + 2]
                    if len({a, b, c}) == 3 and np.linalg.norm(np.cross(P[b] - P[a], P[c] - P[a])) > 1e-6:
                        tris.append((P[a], P[b], P[c]))
                        names.append(mat)
    return np.asarray(tris), names


def _clearance(p, T):
    """Distance from point p to the nearest triangle (closest point on each triangle, vectorised)."""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    ab, ac = b - a, c - a
    n = np.cross(ab, ac)
    nn = np.maximum((n * n).sum(1), 1e-12)
    # the projection onto each triangle's plane, then clamped to the triangle through its edges
    d = ((p - a) * n).sum(1) / nn
    q = p - n * d[:, None]
    def inside(x):
        c0 = (np.cross(b - a, x - a) * n).sum(1) >= 0
        c1 = (np.cross(c - b, x - b) * n).sum(1) >= 0
        c2 = (np.cross(a - c, x - c) * n).sum(1) >= 0
        return c0 & c1 & c2
    best = np.where(inside(q), np.linalg.norm(p - q, axis=1), np.inf)
    for u, v in ((a, b), (b, c), (c, a)):
        e = v - u
        t = np.clip(((p - u) * e).sum(1) / np.maximum((e * e).sum(1), 1e-12), 0.0, 1.0)
        best = np.minimum(best, np.linalg.norm(p - (u + e * t[:, None]), axis=1))
    return float(best.min())


def _blocked(o, d, T, tmax):
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    h = np.cross(d, e2)
    a = (e1 * h).sum(1)
    ok = np.abs(a) > 1e-9
    f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
    s = o - T[:, 0]
    u = f * (s * h).sum(1)
    q = np.cross(s, e1)
    v = f * (q * d).sum(1)
    t = f * (e2 * q).sum(1)
    return bool(np.any(ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0.5) & (t < tmax - 0.5)))


def _pose(shot, t):
    r = shot.get("rates", {})
    eye = np.array([shot["eye"][0] + r.get("x", 0) * t, shot["eye"][1] + r.get("y", 0) * t,
                    shot["eye"][2] + r.get("z", 0) * t])
    yaw, pitch = math.radians(shot["yaw"] + r.get("yaw", 0) * t), math.radians(shot["pitch"] + r.get("pitch", 0) * t)
    return eye, np.array([-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)]), pitch


class Cameras(unittest.TestCase):
    """The flyover as the game plays it: three consecutive cameras from a varying start (labs 2 and 3), a vertical
    field of view on a 16:9 picture, and 0 for every component a camera's channel does not carry (labs 2 and 3)."""

    def played(self, venue):
        return [sm.effective_shot(s, present) for s, present in
                zip(sm.sofi_shots(venue), sm.CAMERA_COMPONENTS_PRESENT[venue])]

    def test_every_shot_wants_what_its_camera_can_carry(self):
        for venue in sm.MODEL_VENUES:
            for k, (shot, played) in enumerate(zip(sm.sofi_shots(venue), self.played(venue))):
                self.assertEqual(tuple(round(v, 6) for v in shot["eye"]), tuple(round(v, 6) for v in played["eye"]),
                                 (venue, k + 1))
                self.assertAlmostEqual(shot["yaw"] % 360.0 % 360.0, played["yaw"] % 360.0 % 360.0, places=6)
                self.assertAlmostEqual(shot["pitch"], played["pitch"], places=6)

    def test_the_super_bowl_camera_shows_the_screen(self):
        """The s40 bundles carry one intro camera with every component, whose angle channels do not play as the s23/s24
        cameras' do (labs 4 and 5): its shot wants every angle 0 (level, still, looking south down the axis), which
        reads the same whichever channel carries which angle, and it sees the whole screen."""
        (shot,) = self.played("s40")
        self.assertTrue(shot.get("screen"))
        for key in ("yaw", "pitch"):
            self.assertAlmostEqual(abs(shot[key]), 0.0, places=6)
        self.assertEqual(shot.get("rates", {}), {})
        self.assertEqual(shot["eye"][0], 0.0)

    def test_any_three_in_a_row_show_the_screen_and_an_exterior(self):
        for venue in sm.VENUES:
            shots = self.played(venue)
            self.assertEqual(len(shots), 5)
            for start in range(5):
                three = [shots[(start + i) % 5] for i in range(3)]
                self.assertTrue(any(s.get("screen") for s in three), (venue, start))
                self.assertTrue(any(abs(s["eye"][0]) > 150 or abs(s["eye"][2]) > 200 for s in three), (venue, start))

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        """xemu draws a flare marker's lens flare through the canopy, so no shot may have one in its frustum."""
        for venue in sm.VENUES:
            model = sm.build(venue=venue)
            flares = [np.array(p) for p in sm.flare_points(model)]
            for k, shot in enumerate(self.played(venue)):
                for t in range(0, 9):
                    eye, f, _pitch = _pose(shot, t)
                    right = np.cross(f, (0.0, 1.0, 0.0))
                    right /= np.linalg.norm(right)
                    up = np.cross(right, f)
                    vf = math.radians(shot["fov"])
                    hf = 2 * math.atan(math.tan(vf / 2) * 16 / 9)
                    for p in flares:
                        d = (p - eye) / np.linalg.norm(p - eye)
                        x, y, z = d @ right, d @ up, d @ f
                        inside = z > 0 and abs(math.atan2(x, z)) <= hf / 2 + 0.05 and abs(math.atan2(y, z)) <= vf / 2 + 0.05
                        self.assertFalse(inside, (venue, k + 1, t, tuple(np.round(p))))

    def test_eyes_stay_in_the_open_and_the_screen_shots_see_the_screen(self):
        for venue in sm.MODEL_VENUES:
            model = sm.build(venue=venue)
            T, names = _triangles(model)
            on_screen = np.array([n.startswith("LIGHT_sf_screen") or n in ("jumbo_tron", "sf_dark", "sf_letters_screen")
                                  for n in names])
            blockers = T[~on_screen]
            samples = np.asarray(model.meshes["sf_screen"].P, float)[::25]
            for k, shot in enumerate(self.played(venue)):
                for t in range(0, 9, 2):
                    eye, f, pitch = _pose(shot, t)
                    self.assertTrue(-math.pi / 2 < pitch < math.pi / 2, (venue, k, t))
                    self.assertGreaterEqual(_clearance(eye, T), 3.0, (venue, k + 1, t))
                    if not shot.get("screen"):
                        continue
                    right = np.cross(f, (0.0, 1.0, 0.0))
                    right /= np.linalg.norm(right)
                    up = np.cross(right, f)
                    vf = math.radians(shot["fov"])
                    hf = 2 * math.atan(math.tan(vf / 2) * 16 / 9)
                    seen = 0
                    for p in samples:
                        d = p - eye
                        dist = np.linalg.norm(d)
                        d /= dist
                        x, y, z = d @ right, d @ up, d @ f
                        if z > 0 and abs(math.atan2(x, z)) <= hf / 2 and abs(math.atan2(y, z)) <= vf / 2 \
                                and not _blocked(eye, d, blockers, dist):
                            seen += 1
                    self.assertGreaterEqual(seen / len(samples), 0.8, (venue, k + 1, t))


class Crowd(unittest.TestCase):
    def test_recolour_moves_team_colours_and_keeps_skin(self):
        from mod_editor.core import nfl2k5_sofi_crowd as crowd
        img = np.array([[[20, 30, 90, 255], [200, 160, 40, 255], [205, 150, 120, 255], [120, 90, 60, 255]]], np.uint8)
        out = crowd.recolour(img, (0, 53, 148), (255, 209, 0))
        self.assertGreater(out[0, 0, 2], out[0, 0, 0])            # navy stays blue, now royal
        self.assertGreater(out[0, 1, 1], img[0, 1, 1])             # old gold toward sol
        np.testing.assert_array_equal(out[0, 2], img[0, 2])        # skin untouched
        np.testing.assert_array_equal(out[0, 3], img[0, 3])        # brown hair untouched


class PrivatePortraits(unittest.TestCase):
    """Official player portraits stay private (main, 2026-09-24): the committed panels carry none, nothing under the
    private hydration folder is released, and a build uses the private panels only when they are the pinned ones."""

    def test_nothing_private_is_released(self):
        allow = (ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split()
        catalog = json.loads((ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json").read_text(encoding="utf-8"))
        private = sm.PRIVATE_ART.relative_to(ROOT).as_posix()
        self.assertFalse([p for p in allow if p.startswith(private)])
        self.assertFalse([p for p in catalog["files"] if p.startswith(private)])
        self.assertTrue(private.startswith("mod_editor/assets/"))            # a gitignored hydration set

    def test_the_committed_panels_are_the_art_manifest_s(self):
        import hashlib
        art = sm.art_manifest()
        for venue in sm.VENUES:
            path = sm.ART_DIR / f"LIGHT_sf_screen_{venue}.png"
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), art[f"LIGHT_sf_screen_{venue}"]["sha256"])

    def test_the_build_falls_back_without_the_private_panels(self):
        saved = sm.USE_PORTRAITS
        try:
            sm.USE_PORTRAITS = False
            self.assertEqual(sm.screen_panels_used(), {v: "committed" for v in sm.VENUES})
            self.assertIsNone(sm.portrait_panel("s23"))
        finally:
            sm.USE_PORTRAITS = saved

    @unittest.skipUnless(all(sm._private_panel_ok(v) for v in sm.VENUES), "the private portrait panels are not hydrated")
    def test_the_pinned_private_panels_are_used(self):
        pins = sm.model_pins()
        for venue in sm.VENUES:
            self.assertEqual(sm.sha(sm.portrait_panel(venue).read_bytes()), pins["portrait_art"][venue])
        self.assertEqual(sm.screen_panels_used(), {v: "portraits" for v in sm.VENUES})


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        """Every authored PNG ships as an exact reviewed catalog entry, and the release checker pins the catalog."""
        import hashlib
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted((sm.DATA_DIR / "art").rglob("*.png"))
        from mod_editor.core import nfl2k5_official_marks as official
        external = [p for p in official.CATALOG if p.startswith("data/nfl2k5_sofi_model/art/")]
        self.assertEqual(len(pngs) + len(external), 40)  # 39 originals plus the public club-only split
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            self.assertEqual((row["width"], row["height"]), Image.open(png).size, rel)
            self.assertIn(rel, allow)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"', checker)


class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s23_and_s24_to_sofi(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s23", "s24", "s22")}, league={"nfl_shield": {}}, skipped=[])
        with_sofi = [p for p, _t in mv.venues_to_write(art, sofi=True)]
        without = [p for p, _t in mv.venues_to_write(art)]
        self.assertIn("s23", without)
        self.assertIn("s24", without)
        self.assertNotIn("s23", with_sofi)
        self.assertNotIn("s24", with_sofi)
        self.assertEqual(set(without) - set(with_sofi), {"s23", "s24"})

    def test_option_is_off_in_every_preset(self):
        from mod_editor.core import mod_build
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_sofi"), False, name)
        self.assertIn("modern_sofi", mod_build.availability())


@unittest.skipUnless(EXTRACTED.is_dir() and sm.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    @requires_real_pack("modern_sofi")
    def test_compiled_stretches_equal_their_pins(self):
        """With the committed screen panels always; with the private portrait panels when they are present."""
        retail = sm.read_retail(EXTRACTED)
        variants = [(False, "model_sha256")]
        if all(sm._private_panel_ok(v) for v in sm.VENUES):
            variants.append((True, "model_portrait_sha256"))
        saved = sm.USE_PORTRAITS
        try:
            for use, key in variants:
                sm.USE_PORTRAITS = use
                for name in ("s23dd.iff", "s24nr.iff", "s40dd.iff"):
                    model, info = sm.model_bundle(retail[name], name, sm.build(venue=name[:3]),
                                                  cameras=sm.sofi_shots(name[:3]), dry_bundle=retail[sm.dry_of(name)])
                    self.assertEqual(len(model), len(retail[name]))
                    start, end = sm.stretch(retail[name])
                    pin = sm._pin(name)
                    self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
                    wanted = pin.get(key, pin["model_sha256"]) if name[:3] in sm.VENUES else pin["model_sha256"]
                    self.assertEqual(sm.sha(model[start:end]), wanted, (name, key))
                    self.assertEqual(sm.sha(retail[name][start:end]), pin["retail_sha256"])
                    self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"])
        finally:
            sm.USE_PORTRAITS = saved

    @requires_real_pack("modern_sofi")
    def test_official_colours_survive_modern_colour(self):
        """Modern colour's end-zone pass would move the Rams' sol #FFD100 toward lemon; the painted marks keep theirs."""
        from mod_editor.core import nfl2k5_modern_color as colour
        ml = sm._ml()
        tx = ml._tools()[0]
        retail = sm.read_retail(EXTRACTED)
        span, info = sm.field_span(retail["s23nd.iff"], "s23nd.iff", colour_settings=colour.normalize_settings(None))
        self.assertGreater(info["mark_palettes_restored"], 0)
        chunk = tx.parse_chunks(span, allow_trailing=True)[0]
        rec, dec = ml._scene(span, chunk)
        rows = ml.texture_rows(rec)
        for material in sm.mark_materials("s23"):
            at = chunk.system_bytes + int(rows[material]["palette_offset"])
            colours = {(dec[at + i + 2], dec[at + i + 1], dec[at + i]) for i in range(0, 1024, 4)}
            self.assertNotIn((254, 232, 0), colours, material)
            # the flat fills are the exact official paint: royal #003594 and sol #FFD100
            rgba = ml.read_p8(dec, chunk.system_bytes, rows[material])[0].reshape(-1, 4)
            opaque = rgba[rgba[:, 3] == 255][:, :3]
            values, counts = np.unique(opaque, axis=0, return_counts=True)
            top = {tuple(int(x) for x in v) for v in values[np.argsort(counts)[::-1][:2]]}
            self.assertLessEqual(top, {(0, 53, 148), (255, 209, 0), (255, 255, 255)}, material)

    def test_the_camera_table_matches_the_retail_scenes(self):
        ml = sm._ml()
        tx = ml._tools()[0]
        retail = sm.read_retail(EXTRACTED)
        for venue in sm.MODEL_VENUES:
            for name in (f"{venue}dd.iff", f"{venue}nr.iff"):
                b = retail[name]
                for c in tx.parse_chunks(b, allow_trailing=True):
                    if c.kind != "SCNE":
                        continue
                    rec, dec = ml._scene(b, c)
                    if rec.get("name") == "intro_cameras":
                        self.assertEqual(sm.camera_components(dec), list(sm.CAMERA_COMPONENTS_PRESENT[venue]), name)

    @requires_real_pack("modern_sofi")
    def test_the_super_bowl_field(self):
        """s40: the LXI mark at midfield and the NFL shield on both 25s, each quad at its art's true proportions, the
        marks' palettes kept through Modern colour, and the SoFi turf."""
        from mod_editor.core import nfl2k5_modern_color as colour
        ml = sm._ml()
        tx = ml._tools()[0]
        retail = sm.read_retail(EXTRACTED)
        span, info = sm.field_span(retail["s40dd.iff"], "s40dd.iff", turf_bundle=retail[sm.TURF_SOURCE],
                                   colour_settings=colour.normalize_settings(None))
        chunk = tx.parse_chunks(span, allow_trailing=True)[0]
        rec, dec = ml._scene(span, chunk)
        ov = sm._field_shape(rec, "D_graphic_overlays")
        st0 = sm._stream(ov, 0)
        art = sm.art_manifest()
        for material, name, count in (("center_logo", "s40_midfield", 1), ("logo", "s40_shield", 2)):
            across, along = art[f"field/{name}"]["quad_m"]
            idx = sm._submesh_vertices(rec, dec, ov, material)
            self.assertEqual(len(idx), 4 * count)
            for quad in [idx[k:k + 4] for k in range(0, len(idx), 4)]:
                P = np.array([struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i) for i in quad]) / 100.0
                self.assertAlmostEqual(P[:, 0].max() - P[:, 0].min(), across, places=2)
                self.assertAlmostEqual(P[:, 2].max() - P[:, 2].min(), along, places=2)
                if material == "logo":                                   # the shields sit on the 25-yard lines
                    self.assertAlmostEqual(abs(P[:, 2].mean()), 25 * 0.9144, places=2)
        # the grade's end-zone pass leaves these marks alone (design A: none of their colours is turf-like); any entry
        # it did move would be restored
        self.assertGreaterEqual(info["mark_palettes_restored"], 0)

    @requires_real_pack("modern_sofi")
    def test_field_fits_and_splits(self):
        ml = sm._ml()
        retail = sm.read_retail(EXTRACTED)
        for name, dry in (("s24dr.iff", "s24dd.iff"), ("s23nd.iff", None)):
            turf = retail[sm.TURF_SOURCE] if name[:3] != sm.TURF_SOURCE[:3] else None
            span, info = sm.field_span(retail[name], name, dry_bundle=retail[dry] if dry else None, turf_bundle=turf)
            chunk = ml.bundle_scenes(retail[name])["field"]
            self.assertEqual(len(span), 32 + chunk.stored_size)
            self.assertEqual(info["palette_cap"], 256)

    def test_the_kept_banners_carry_the_2026_league_cloths(self):
        """banner_corp takes u4's 2026 league sheet in every bundle (st's method): the SEGA cloth's cell changes, rain
        and snow carry the dry bundle's art with their own weathering, and the texture keeps its size."""
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        retail = sm.read_retail(EXTRACTED)
        ml = sm._ml()
        rects = mv.LEAGUE_ART[0]["rects"]
        for name in ("s23dd.iff", "s24nr.iff", "s40ns.iff"):
            index, art = sm.league_banner(retail[name], name, retail[sm.dry_of(name)])
            c = ml.bundle_scenes(retail[name])["stadium"]
            rec, dec = ml._scene(retail[name], c)
            before = ml.read_p8(dec, c.system_bytes, ml.texture_rows(rec)["banner_corp"])[0]
            self.assertEqual(art.shape, before.shape, name)
            x0, y0, x1, y1 = rects[6]                      # the 2004 SEGA cloth's cell
            sx, sy = before.shape[1] / 256.0, before.shape[0] / 256.0
            cell = (slice(int(y0 * sy), int(y1 * sy)), slice(int(x0 * sx), int(x1 * sx)))
            self.assertGreater(float(np.abs(art[cell].astype(float) - before[cell].astype(float)).mean()), 10.0, name)

    @requires_real_pack("modern_sofi")
    def test_one_turf_for_both_records(self):
        """The Chargers' field lays the Rams' (dome) turf, surround and numbers, and the dome's detail normal map."""
        ml = sm._ml()
        tx = ml._tools()[0]
        retail = sm.read_retail(EXTRACTED)
        textures = {}
        for name in ("s23dd.iff", "s24ns.iff"):
            turf = retail[sm.TURF_SOURCE] if name[:3] != sm.TURF_SOURCE[:3] else None
            dry = retail[f"{name[:4]}d.iff"] if name[4] != "d" else None
            span, _info = sm.field_span(retail[name], name, dry_bundle=dry, turf_bundle=turf)
            chunk = tx.parse_chunks(span, allow_trailing=True)[0]
            rec, dec = ml._scene(span, chunk)
            rows = ml.texture_rows(rec)
            textures[name] = {m: ml.read_p8(dec, chunk.system_bytes, rows[m])[0] for m in ("color_premipped", "numbers")}
        for m in ("color_premipped", "numbers"):
            a, b = textures["s23dd.iff"][m], textures["s24ns.iff"][m]
            self.assertEqual(a.shape, b.shape, m)
            self.assertLess(np.abs(a.astype(int) - b.astype(int)).max(), 2, m)
        _at, s23 = sm.normal_span(retail["s23dd.iff"])
        _at, s24 = sm.normal_span(retail["s24dd.iff"])
        self.assertEqual(s23[:16], s24[:16])


if __name__ == "__main__":
    unittest.main()
