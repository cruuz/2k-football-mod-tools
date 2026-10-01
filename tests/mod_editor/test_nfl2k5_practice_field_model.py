"""Practice facility model (pf): geometry clear of what the engine keeps on the ground, the crowd convention, the
board's feed crop, markers, cameras, the field and the bundles, the composition with Modern colour and Modern playing
surfaces, the Build option, the pins and the reviewed release catalog."""
import math
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_practice_field_model as pf  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = pf.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 20000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_nothing_stands_where_the_engine_keeps_the_sidelines(self):
        """No new geometry above the ground inside the box the retail sideline props and markers use (props to x 41.7,
        the media, security and VIP markers to x 38.6 and z 62.2), nor on the field scene's own grass (x 58.5, z 87.7)
        below walkway height."""
        for m in self.model.meshes.values():
            P = np.array(m.P) if m.P else np.zeros((0, 3))
            high = P[P[:, 1] > 0.1] if len(P) else P
            inside = high[(np.abs(high[:, 0]) < 42.5) & (np.abs(high[:, 2]) < 62.5)] if len(high) else high
            self.assertEqual(len(inside), 0, (m.name, inside[:3].round(1).tolist() if len(inside) else None))
        g = np.array(self.model.meshes["pf_ground"].P)
        on_field = g[(np.abs(g[:, 0]) < 58.49) & (np.abs(g[:, 2]) < 87.69)]
        self.assertEqual(len(on_field), 0)

    def test_the_broadcast_eye_stays_in_the_open(self):
        """The game's broadcast camera eye (x 56.5 m, 16.5 m up; u5) keeps 3 m from the model along the whole side."""
        P = np.concatenate([np.array(m.P) for m in self.model.meshes.values() if m.P])
        for z in np.linspace(-50, 50, 11):
            eye = np.array([56.5, 16.5, z])
            self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, z)

    def test_crowd_uv_convention(self):
        """u5's convention: U a quarter strip of the runtime crowd atlas (top 0.0075, bottom 0.2425 into it)."""
        crowd = 0
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)
                crowd += 1
        self.assertGreater(crowd, 10)

    def test_materials_and_art(self):
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue(mats <= set(pf.MATERIALS) | {"crowd", "jumbo_tron"}, mats - set(pf.MATERIALS))
        self.assertTrue({"pf_fh_wall", "LIGHT_pf_glass", "pf_windscreen", "pf_field_strip", "pf_turf_strip", "pf_yellow",
                         "LIGHT_pf_led", "pf_scissor", "pf_bleacher", "crowd", "jumbo_tron", "pf_clock"} <= mats)
        for key, _cls in pf.MATERIALS.values():
            if key.startswith("city:"):
                continue
            self.assertTrue((pf.ART_DIR / f"{key}.png").is_file(), key)
            if key in pf.NIGHT_ART:
                self.assertTrue((pf.ART_DIR / f"{key}_night.png").is_file(), key)
        self.assertTrue((pf.FIELD_ART / "pf_clear.png").is_file())
        self.assertFalse((pf.FIELD_ART / "pf_midfield.png").exists())     # league marks never ship

    def test_the_board_shows_the_feed_at_its_own_aspect(self):
        """The feed is a 640 x 448 picture in a 1024 x 512 target (u5b, u6); the board's window takes a crop at the
        board's aspect, never a stretch."""
        u0, u1, v0, v1 = pf.PracticeFacility.FEED_UV
        self.assertLessEqual(u1, 640 / 1024 + 1e-9)
        self.assertLessEqual(v1, 448 / 512 + 1e-9)
        q = pf.PARAMS["video_board"]
        self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), q["w"] / q["h"], places=6)
        m = self.model.meshes["pf_video_board"]
        idx = sorted({i for st in m.groups["jumbo_tron"] for i in st})
        P = np.array([m.P[i] for i in idx])
        self.assertAlmostEqual(np.ptp(P[:, 0]), q["w"], places=4)
        self.assertAlmostEqual(np.ptp(P[:, 1]), q["h"], places=4)

    def test_markers(self):
        m = self.model
        self.assertEqual(len(m.markers["jumbo"]), 2)
        self.assertEqual(len(m.light_points), 8)
        for p in pf.flare_points(m):
            self.assertGreater(p[1], 250.0)
        x, y, z = m.nosebleed
        q = pf.PARAMS["bleachers"]
        self.assertTrue(q["x0"] < x < q["x0"] + q["rows"] * q["tread"] + 0.5 and q["z0"] < z < q["z1"])


class Cameras(unittest.TestCase):
    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(pf.practice_shots(), pf.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            if "pitch" not in present:
                self.assertEqual(shot["pitch"], 0.0)
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        model = pf.build()
        flares = [np.array(p, float) for p in pf.flare_points(model)]
        for k, shot in enumerate(pf.practice_shots()):
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

    def test_eyes_stay_in_the_open(self):
        model = pf.build()
        flat = ("pf_ground", "pf_walks", "pf_field_grass", "pf_field_turf", "pf_site")      # ground level: the height check
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P and m.name not in flat])
        for k, s in enumerate(pf.practice_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))
                self.assertGreater(eye[1], 1.5, (k, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        retail = pf.read_retail(EXTRACTED)
        for name in pf.VARIANTS:
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), pf.CAMERA_COMPONENTS_PRESENT, name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Scene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = pf.read_retail(EXTRACTED)

    def test_no_marker_registers_a_glow_and_the_engine_names_stay(self):
        for name in ("s32dd.iff", "s32ns.iff"):
            sc = pf.build_scene(self.retail[name], name, pf.build())
            self.assertFalse([m.name for m in sc.markers if "light" in m.name], name)
            self.assertEqual(len([m for m in sc.markers if m.name.startswith("marker_lamp")]), 8, name)
            names = {m.name for m in sc.materials}
            self.assertTrue({"crowd", "jumbo_tron"} <= names, name)
            self.assertTrue(any(n.startswith("digit_") for n in names), name)
            shapes = {s.name for s in sc.shapes}
            self.assertTrue({"sideline_home_north", "sideline_away_south", "pyG001", "pf_yard", "pf_digits"} <= shapes)

    def test_the_lawn_matches_the_fields(self):
        """The cloned retail grass is regraded to the practice fields' tone (detail kept, the index plane untouched)."""
        city = pf.city_textures(self.retail["s32dd.iff"])
        t = pf.regrade_palette(city["grass_01"], pf.lawn_mean())
        self.assertEqual(t.pixels, city["grass_01"].pixels)
        idx = np.frombuffer(t.pixels[:t.width * t.height], np.uint8)
        pal = np.frombuffer(t.palette, np.uint8).reshape(256, 4)[:, [2, 1, 0]].astype(float)
        mean = pal[idx].mean(0)
        for a, b in zip(mean, pf.lawn_mean()):
            self.assertLess(abs(a - b), 3.0)

    def test_the_bundle_keeps_its_size_and_the_stadium_block_shrinks(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        tx = ml._tools()[0]
        for name in ("s32dd.iff", "s32ns.iff"):
            retail = self.retail[name]
            out, info = pf.model_bundle(retail, name, pf.build(), cameras=pf.practice_shots())
            self.assertEqual(len(out), len(retail))
            self.assertEqual([c.kind for c in tx.parse_chunks(out, allow_trailing=True)],
                             [c.kind for c in tx.parse_chunks(retail, allow_trailing=True)])
            start, end = pf.stretch(retail)
            self.assertEqual(out[:start], retail[:start])
            self.assertEqual(out[end:], retail[end:])
            st = ml.bundle_scenes(retail)["stadium"]
            self.assertLess(info["system"] + info["video"], st.system_bytes + st.video_bytes)


def stand_in_shield():
    """A stand-in for the venue art folder's current NFL shield (the real mark never ships): a navy shield shape with a
    red band, on a clear ground, 512 x 600."""
    h, w = 600, 512
    yy, xx = np.mgrid[0:h, 0:w]
    inside = (np.abs(xx - w / 2) < (w / 2 - 6) * np.where(yy < 420, 1.0, np.clip((h - 6 - yy) / (h - 426), 0, 1))) \
        & (yy > 6) & (yy < h - 6)
    out = np.zeros((h, w, 4), np.uint8)
    out[inside] = (1, 51, 105, 255)
    out[inside & (yy > 200) & (yy < 330)] = (213, 10, 10, 255)
    return out


def _field(ml, bundle):
    chunk = ml.bundle_scenes(bundle)["field"]
    rec, dec = ml._scene(bundle, chunk)
    return chunk, rec, dec


def _midfield_quad(sm, rec, dec, material=None):
    g = sm._field_shape(rec, "D_graphic_overlays")
    st0 = sm._stream(g, 0)
    idx = sm._submesh_vertices(rec, dec, g, material or pf.MIDFIELD)
    return np.array([struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i) for i in idx]) / 100.0


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Field(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_sofi_model as sm
        cls.ml = sm._ml()
        cls.sm = sm
        cls.retail = pf.read_retail(EXTRACTED)

    def test_the_field_fits_and_carries_the_practice_marks(self):
        """With the venue art folder's shield: the conference shields and the playoff mark cleared, the shield on a
        10 m square quad at midfield, plain grass end zones."""
        ml, sm = self.ml, self.sm
        name = "s32dd.iff"
        bundle = self.retail[name]
        chunk = ml.bundle_scenes(bundle)["field"]
        span, info = pf.field_span(bundle, name, shield=stand_in_shield())
        self.assertEqual(len(span), 32 + chunk.stored_size)
        self.assertEqual(info["look"], pf.SURFACE_LOOK)
        self.assertTrue(info["shield"])
        out = bytes(bundle[:chunk.offset]) + span + bytes(bundle[chunk.offset + len(span):])
        _c, rec, dec = _field(ml, out)
        rows = ml.texture_rows(rec)
        for mat in pf.CLEARED:
            rgba = ml.read_p8(dec, chunk.system_bytes, rows[mat])[0]
            self.assertEqual(int(rgba[..., 3].max()), 0, mat)
        P = _midfield_quad(sm, rec, dec)
        self.assertAlmostEqual(np.ptp(P[:, 0]), 2 * pf.MIDFIELD_HALF, places=3)
        self.assertAlmostEqual(np.ptp(P[:, 2]), 2 * pf.MIDFIELD_HALF, places=3)
        mid = ml.read_p8(dec, chunk.system_bytes, rows[pf.MIDFIELD])[0]
        self.assertGreater(float((mid[..., 3] > 128).mean()), 0.25)
        for mat in pf.ENDZONE_TEXTURES:
            ez = ml.read_p8(dec, chunk.system_bytes, rows[mat])[0][..., :3].astype(float)
            self.assertLess(float(ez.std(axis=(0, 1)).max()), 12.0, mat)      # plain grass: no lettering

    def test_without_the_art_folder_the_midfield_stays_the_games(self):
        """League marks never ship: without the venue art folder the midfield keeps the retail mark and quad."""
        ml, sm = self.ml, self.sm
        name = "s32dd.iff"
        bundle = self.retail[name]
        chunk, rec0, dec0 = _field(ml, bundle)
        span, info = pf.field_span(bundle, name)
        self.assertFalse(info["shield"])
        out = bytes(bundle[:chunk.offset]) + span + bytes(bundle[chunk.offset + len(span):])
        _c, rec, dec = _field(ml, out)
        np.testing.assert_array_equal(_midfield_quad(sm, rec, dec), _midfield_quad(sm, rec0, dec0))
        row0, row = ml.texture_rows(rec0)[pf.MIDFIELD], ml.texture_rows(rec)[pf.MIDFIELD]
        np.testing.assert_array_equal(ml.read_p8(dec, chunk.system_bytes, row)[0],
                                      ml.read_p8(dec0, chunk.system_bytes, row0)[0])

    def test_the_team_logo_midfield_is_named_teamlogo_and_nothing_else_moves(self):
        """P1: the midfield material renamed teamlogo (the only material of that name; retail s32 carries none), the
        field otherwise identical to the one without the swap, and still tf's surface under its deep status."""
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        ml = self.ml
        name = "s32ns.iff"
        bundle = self.retail[name]
        chunk, rec0, _dec0 = _field(ml, bundle)
        self.assertNotIn(pf.TEAM_LOGO, [m["name"] for m in rec0["materials"]])
        plain, _ = pf.field_span(bundle, name)
        named, info = pf.field_span(bundle, name, team_logo=True)
        self.assertTrue(info["team_logo"])
        out = bytes(bundle[:chunk.offset]) + named + bytes(bundle[chunk.offset + len(named):])
        _c, rec, dec = _field(ml, out)
        names = [m["name"] for m in rec["materials"]]
        self.assertEqual(names.count(pf.TEAM_LOGO), 1)
        self.assertNotIn(pf.MIDFIELD, names)
        _c, rec_p, dec_p = _field(ml, bytes(bundle[:chunk.offset]) + plain + bytes(bundle[chunk.offset + len(plain):]))
        at = next(m for m in rec_p["materials"] if m["name"] == pf.MIDFIELD)["name_target"]
        diff = [i for i, (a, b) in enumerate(zip(dec, dec_p)) if a != b]
        self.assertTrue(diff and at <= min(diff) and max(diff) < at + 2 * len(pf.MIDFIELD) + 2, (at, diff[:4]))
        full = bytes(out)
        sites = ms.bundle_sites(full)
        at_f, size_f = sites["field"]
        self.assertIn(ms.field_uv_constant(full[at_f:at_f + size_f]), ms.SURFACED_CONSTANTS)

    def test_the_midfield_art_is_the_shield_centred_at_its_own_proportions(self):
        art = pf.midfield_art(stand_in_shield(), (256, 256))
        self.assertEqual(art.shape, (256, 256, 4))
        ys, xs = np.nonzero(art[..., 3] > 128)
        self.assertAlmostEqual((xs.min() + xs.max()) / 2, 127.5, delta=2)
        self.assertAlmostEqual((ys.min() + ys.max()) / 2, 127.5, delta=2)
        self.assertAlmostEqual((xs.ptp() + 1) / (ys.ptp() + 1), 512 / 600, delta=0.03)
        self.assertEqual(int(art[0, 0, 3]), 0)


class _Archive:
    def __init__(self, data):
        self.data = data

    def read(self, offset, size):
        return self.data[offset:offset + size]


class _Entry:
    def __init__(self, size):
        self.virtual_offset, self.size = 0, size


def baked_means(bundle):
    """{material: (r, g, b)} as the stadium scene draws it on level ground (texture x vertex colour): the green texels'
    mean of the texture's top level (all texels for the lawn's retail grass) times the material's mean vertex colour."""
    from mod_editor.core import nfl2k5_sofi_model as sm
    from mod_editor.core import nfl2k5_scne_builder as sb
    ml = sm._ml()
    c = ml.bundle_scenes(bundle)["stadium"]
    _rec, dec = ml._scene(bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    names = [m.name for m in sc.materials]
    colours = {}
    for shape in sc.shapes:
        if shape.streams[1] is None or shape.stride(1) != 10:
            continue
        s1 = shape.streams[1]
        for sub in shape.submeshes:
            idx = sorted({i for _m, ix in sb.decode_words(sub.words) for i in ix})
            for i in idx:
                b, g, r, _a = s1[10 * i:10 * i + 4]
                colours.setdefault(names[sub.material], []).append((r, g, b))
    out = {}
    for mat in ("pf_field_strip", "pf_endzone_grass", "pf_turf_strip", "pf_endzone_turf", "pf_ground"):
        tex = sc.textures[sc.materials[sc.material_index(mat)].texture]
        pal = np.frombuffer(tex.palette, np.uint8).reshape(256, 4)[:, [2, 1, 0]].astype(float)
        px = pal[np.frombuffer(tex.pixels[:tex.width * tex.height], np.uint8)]
        if mat != "pf_ground":
            r, g, b = px[:, 0], px[:, 1], px[:, 2]
            mx, mn = px.max(1), px.min(1)
            px = px[(g >= r) & (g >= b) & (mx > 1) & ((mx - mn) / np.maximum(mx, 1) > 0.12)]
        vc = np.array(colours[mat], float).mean(0)
        out[mat] = tuple(px.mean(0) * vc / 255.0)
    return out


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class ComposeWithSurfaces(unittest.TestCase):
    """Modern practice facility and Modern playing surfaces both on (main, 2026-09-27, after tf-v2): s32 is not one of
    tf's 288 home bundles, so tf's step leaves it to this option; the practice field is painted by tf's own painter with
    tf's detail normal, so it reads applied under tf's deep status (tf's signature: its detail normal and the planar
    field UVs), Modern colour off and on; the side fields and lawns baked into the stadium scene land on tf's day
    targets."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        cls.ms = ms
        cls.retail = pf.read_retail(EXTRACTED)
        pins = pf._venue_pins()
        cls.composed = {}
        for name, settings in (("s32dd.iff", None), ("s32nr.iff", colour.default_settings())):
            retail, outer = cls.retail[name], pins[name]["outer"]
            current = retail if settings is None else colour.modern_bundle(retail, outer_index=outer, settings=settings)[0]
            out, info = pf.compose_bundle(retail, current, name, colour_settings=settings, outer_index=outer)
            cls.composed[name] = (current, out, info)

    def test_tf_leaves_s32_to_the_practice_facility(self):
        self.assertFalse(set(pf.VARIANTS) & set(self.ms.HOME_BUNDLES))
        src = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        self.assertLess(src.index('progress("Modern practice facility: practice field packages"'),
                        src.index('progress("Modern playing surfaces: home-venue fields"'))

    def test_the_main_field_reads_applied_under_tfs_deep_status(self):
        ms = self.ms
        for name, (current, out, info) in self.composed.items():
            report = ms.bundle_report(_Archive(out), name, _Entry(len(out)), None, deep=True)
            self.assertEqual(report["state"], "applied", (name, report))
            self.assertTrue(report["reason"].startswith("signature: detail blade_bluegrass"), report)
            before = ms.bundle_report(_Archive(current), name, _Entry(len(current)), None, deep=True)
            self.assertEqual(before["state"], "retail", (name, before))
            field = info["field"]
            cls_ = "rain" if name[4] == "r" else "snow" if name[4] == "s" else {"d": "day", "a": "afternoon",
                                                                                   "n": "night"}[name[3]]
            self.assertEqual(field["layout"], "grid")
            self.assertEqual(field["response"], ms.field_response(pf.SURFACE_LOOK, cls_, "grid"))
            np.testing.assert_allclose(field["target"], ms.target_rgb(pf.SURFACE_LOOK, cls_), atol=0.01)

    def test_only_the_practice_facilitys_sites_change(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        for name, (current, out, _info) in self.composed.items():
            sites = self.ms.bundle_sites(current)
            start, end = pf.stretch(current)
            keep = bytearray(out)
            for a, b in [(start, end)] + [(at, at + size) for k, (at, size) in sites.items() if k in ("field", "normal", "divots")]:
                keep[a:b] = current[a:b]
            self.assertEqual(bytes(keep), current, name)
            self.assertEqual(ml.bundle_scenes(out)["field"].offset, ml.bundle_scenes(current)["field"].offset)

    def test_the_side_fields_and_lawns_land_on_tfs_day_targets(self):
        ms = self.ms
        _current, out, _info = self.composed["s32dd.iff"]
        means = baked_means(out)
        for mat, look, shade in (("pf_field_strip", pf.SURFACE_LOOK, 1.0), ("pf_endzone_grass", pf.SURFACE_LOOK, 1.0),
                                 ("pf_turf_strip", pf.SYNTHETIC_LOOK, 1.0), ("pf_endzone_turf", pf.SYNTHETIC_LOOK, 1.0),
                                 ("pf_ground", pf.SURFACE_LOOK, ms.OUTSIDE_SHADE)):
            target = [v * shade for v in ms.target_rgb(look, "day")]
            for got, want in zip(means[mat], target):
                self.assertLess(abs(got - want) / want, 0.03, (mat, [round(v, 1) for v in means[mat]], target))


class _FakeImage:
    """An outer archive in memory standing in for a disc image: the nine s32 bundles at their pinned outers (retail, or
    given bytes), every other bundle Modern colour pins as zeros of its pinned size (never written)."""
    SPACING = 1 << 22

    def __init__(self, bundles):
        from types import SimpleNamespace
        from mod_editor.core import nfl2k5_modern_color as colour
        pins = colour._pins()["bundles"]
        self.entries = [None] * (max(p["outer"] for p in pins) + 1)
        for p in pins:
            self.entries[p["outer"]] = SimpleNamespace(virtual_offset=p["outer"] * self.SPACING, size=p["size"],
                                                       name_id=p["name_id"])
        self.store = {pf._venue_pins()[n]["outer"]: bytearray(b) for n, b in bundles.items()}

    def opener(self, path, writable=False):
        image = self

        class _Open:
            def __enter__(self_):
                return self_

            def __exit__(self_, *exc):
                return False

            entries = image.entries

            def read(self_, offset, size):
                outer, at = divmod(offset, image.SPACING)
                data = image.store.get(outer)
                return bytes(size) if data is None else bytes(data[at:at + size])

            def write(self_, offset, data):
                assert writable, "the image was opened read-only"
                outer, at = divmod(offset, image.SPACING)
                image.store[outer][at:at + len(data)] = data
                return len(data)
        return _Open()


@unittest.skipUnless(EXTRACTED.is_dir() and pf.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class BuildStep(unittest.TestCase):
    """The Build step on an image in memory (the disc I/O is the shared OuterImage's): retail in, the practice facility
    out and recognized, its receipt beside the image; with Modern colour's receipt the colour state of s32 still reads
    applied; a field another option wrote is refused."""

    @classmethod
    def setUpClass(cls):
        cls.retail = pf.read_retail(EXTRACTED)

    def run_step(self, bundles, colour_receipt=None, art_root=None):
        import tempfile
        from unittest import mock
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_roster_records as rr
        real = rr._outer_image()
        image = _FakeImage(bundles)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        target = Path(folder.name) / "lab.iso"

        def opener(path, writable=False):
            return image.opener(path, writable) if str(path) == str(target) else real(path, writable=writable)
        patch = mock.patch.object(rr, "_outer_image", lambda: opener)
        patch.start()
        self.addCleanup(patch.stop)
        if colour_receipt is not None:
            colour._save_image_receipt(target, colour_receipt)
        receipt = pf.apply_to_image(target, retail_source=EXTRACTED, art_root=art_root, workers=3)
        return image, target, receipt

    def test_retail_in_the_practice_facility_out(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        image, target, receipt = self.run_step(dict(self.retail))
        self.assertEqual(receipt["state"], "applied")
        self.assertEqual(receipt["bundles_written"], 9)
        self.assertFalse(receipt["shield"])
        self.assertEqual(pf.image_status(target), "applied")
        doc = pf.read_receipt(target)
        self.assertEqual(sorted(doc["bundles"]), sorted(pf.VARIANTS))
        for name in pf.VARIANTS:
            data = bytes(image.store[pf._venue_pins()[name]["outer"]])
            self.assertEqual(len(data), len(self.retail[name]))
            report = ms.bundle_report(_Archive(data), name, _Entry(len(data)), None, deep=True)
            self.assertEqual(report["state"], "applied", (name, report))
        with self.assertRaises(ValueError):
            pf.apply_to_image(target, retail_source=EXTRACTED)       # the receipt says it is there already

    def test_with_modern_colour_the_colour_state_stays_applied(self):
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_sofi_model as sm
        settings = colour.normalize_settings(None)
        pins = {p["name"]: p for p in colour._pins()["bundles"]}
        graded, rows = {}, {}
        for name in pf.VARIANTS:
            pin = pins[name]
            after, edits = colour.modern_bundle(self.retail[name], outer_index=pin["outer"], settings=settings)
            graded[name] = after
            rows[name] = dict(pin, applied_sha256=pf.sha(after), sites=[
                dict(kind=e["kind"], offset=e["offset"], size=e["size"], retail=e["before_sha256"],
                     applied=e["after_sha256"]) for e in edits])
        for name, pin in pins.items():
            rows.setdefault(name, dict(pin))
        receipt = dict(schema=colour.RECEIPT_SCHEMA, settings=settings, settings_sha256=colour.settings_id(settings),
                       state="applied", bundle_pins=rows)
        image, target, out = self.run_step(graded, colour_receipt=receipt)
        self.assertTrue(out["colour"])
        after = colour.read_image_receipt(target)
        self.assertEqual(sorted(after["practice_field"]["bundles"]), sorted(pf.VARIANTS))
        states = sm._colour_states(target, after)
        for name in pf.VARIANTS:
            self.assertEqual(states[name], "applied", name)

    def test_a_field_another_option_wrote_is_refused(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        bundles = dict(self.retail)
        name = "s32ad.iff"
        data = bytearray(bundles[name])
        chunk = ml.bundle_scenes(bytes(data))["field"]
        data[chunk.offset + 40] ^= 0xFF
        bundles[name] = bytes(data)
        with self.assertRaisesRegex(ValueError, "another option wrote it"):
            self.run_step(bundles)


class Option(unittest.TestCase):
    def test_option_is_off_in_every_preset(self):
        from mod_editor.core import mod_build
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_practice_field"), False, name)
        self.assertIn("modern_practice_field", mod_build.availability())
        self.assertIs(mod_build.BuildPlan.__dataclass_fields__["modern_practice_field"].default, False)
        from mod_editor.core import nfl2k5_build_settings as bs
        self.assertIn("modern_practice_field", bs.FEATURE_KEYS)

    def test_the_team_logo_sub_option_is_off_and_needs_the_facility(self):
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as bs
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_practice_field_team_logo"), False, name)
        self.assertIn("modern_practice_field_team_logo", mod_build.availability())
        self.assertIn("modern_practice_field_team_logo", bs.FEATURE_KEYS)
        plan = mod_build.BuildPlan(source="retail.iso", target="out.iso", modern_practice_field_team_logo=True)
        self.assertEqual(len(mod_build.validate_plan(plan)), 1)
        self.assertIn("needs the Modern practice facility", mod_build.validate_plan(plan)[0])
        self.assertEqual(mod_build.validate_plan(mod_build.BuildPlan(
            source="retail.iso", target="out.iso", modern_practice_field=True, modern_practice_field_team_logo=True)), [])
        src = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        at = src.index('progress("Modern practice facility: practice field packages"')
        self.assertIn("team_logo=plan.modern_practice_field_team_logo", src[at:src.index("if plan.modern_surfaces:", at)])

    def test_the_build_step_takes_the_venue_art_folder_for_the_shield(self):
        src = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        at = src.index('progress("Modern practice facility: practice field packages"')
        block = src[at:src.index("if plan.modern_surfaces:", at)]
        self.assertIn("art_root=plan.modern_venues_2026 or None", block)
        self.assertIn("require_step_source(", block)


@unittest.skipUnless(EXTRACTED.is_dir() and pf.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    def test_compiled_stretches_equal_their_pins(self):
        retail = pf.read_retail(EXTRACTED)
        for name in ("s32dd.iff", "s32as.iff"):
            model, info = pf.model_bundle(retail[name], name, pf.build(), cameras=pf.practice_shots())
            self.assertEqual(len(model), len(retail[name]))
            start, end = pf.stretch(retail[name])
            pin = pf._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(pf.sha(model[start:end]), pin["model_sha256"], name)
            self.assertEqual(pf.sha(retail[name][start:end]), pin["retail_sha256"])
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"])

    def test_every_bundle_is_pinned_and_under_retail(self):
        pins = pf.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(pf.VARIANTS))
        for p in pins["bundles"]:
            self.assertLess(p["vertices"], 20000)

    def test_the_pins_follow_tfs_current_targets(self):
        """The side fields and lawns follow job tf's targets: re-record the pins after tf changes them."""
        pins = pf.model_pins()
        for look in (pf.SURFACE_LOOK, pf.SYNTHETIC_LOOK):
            self.assertEqual(tuple(pins["surface_targets"][look]), pf.surface_target(look), look)


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        """Every authored PNG ships as an exact reviewed catalog entry, the release checker pins the catalog, and no
        league or team mark ships (the midfield shield comes from the user's venue art folder)."""
        import hashlib
        import json
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted((pf.DATA_DIR / "art").rglob("*.png"))
        manifest = json.loads((pf.DATA_DIR / "art" / "art.json").read_text(encoding="utf-8"))["art"]
        self.assertEqual(len(pngs), len(manifest))
        self.assertNotIn("field/pf_midfield", manifest)
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            self.assertEqual((row["width"], row["height"]), Image.open(png).size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_practice_field_model.py", "data/nfl2k5_practice_field_model/pins.json",
                    "data/nfl2k5_practice_field_model/art/art.json", "tests/mod_editor/test_nfl2k5_practice_field_model.py"):
            self.assertIn(rel, allow)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"', checker)


if __name__ == "__main__":
    unittest.main()
