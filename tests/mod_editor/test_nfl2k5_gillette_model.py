"""Gillette Stadium model (st2): geometry, the north end and the lighthouse, the boards, markers, cameras, the field,
the league cloths, the row and the feed."""
import math
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_gillette_model as ne  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = ne.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 30000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_field_wall_clears_the_sideline_props(self):
        """The wall stays outside the retail s16 sideline props (x -43.1 to 44.0) and on the 2002 end walls (z +-70.5)."""
        loop = self.model.loop
        side = [lp for lp in loop if abs(lp.z) < 40]
        self.assertGreaterEqual(min(lp.x for lp in side if lp.x > 0), 44.5)
        self.assertLessEqual(max(lp.x for lp in side if lp.x < 0), -44.5)
        end = [lp for lp in loop if abs(lp.x) < 12]
        self.assertGreaterEqual(min(lp.z for lp in end if lp.z > 0), 70.5)
        self.assertLessEqual(max(lp.z for lp in end if lp.z < 0), -70.5)

    def test_the_stacks_fit_inside_the_facade(self):
        """Every rim walk ends inside the facade outline."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in ne.footprint()["facade"]]
        for lp, sec in zip(self.model.loop, self.model.secs):
            if "rim" not in sec:
                continue
            x, _y, z = self.model.at(lp, sec["rim"][3], 0.0)
            self.assertTrue(sm._point_in_poly(x, z, ring), (round(x, 1), round(z, 1)))

    def test_the_north_end_and_the_lighthouse(self):
        """The 2023 north board (Daktronics: 60 x 370 ft, 22,200 sq ft, convex) over the north stands, bowed toward the
        field, its bottom over every north seat; the lighthouse (218 ft) on the plaza behind it where OpenStreetMap puts it;
        the south board (Wikipedia: 41.5 x 164 ft) over the south stands."""
        q = ne.PARAMS["boards"]
        self.assertAlmostEqual(q["north_w"] * q["north_h"] / 0.3048 ** 2, 22200.0, delta=150.0)
        self.assertAlmostEqual(q["south_w"] / 0.3048, 164.0, delta=0.5)
        self.assertAlmostEqual(q["south_h"] / 0.3048, 41.5, delta=0.1)
        lh = ne.PARAMS["lighthouse"]
        self.assertAlmostEqual(lh["top"] / 0.3048, 218.0, delta=0.5)
        self.assertLess(lh["z"], q["north_z"] - q["depth"])
        m = self.model
        for lp, sec in zip(m.loop, m.secs):
            if lp.w["N"] > 0.6:
                top = max(y for key in ("lower", "t2") if key in sec for _d, y in sec[key])
                self.assertLess(top, q["north_bottom"])
        north = next(f for f in m.board_frames if f["width"] == q["north_w"])
        self.assertAlmostEqual(float(north["centre"][2]), q["north_z"] + q["north_bow"], places=6)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_materials_are_known(self):
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"ne_seat_front", "ne_seat_mid", "ne_seat_back", "crowd", "LIGHT_ne_lights", "jumbo_tron",
                         "LIGHT_ne_board_panel", "ne_facade", "ne_tower", "LIGHT_ne_lantern", "ne_letters",
                         "env_far", "env_band"} <= mats)
        self.assertTrue(mats <= set(ne.MATERIALS) | {"crowd", "jumbo_tron"}, mats - set(ne.MATERIALS))

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
        keep = [[tuple(p) for p in ne.footprint()["facade"]]]
        for name in ("env_lots", "env_blocks", "env_trees"):
            for x, _y, z in m.meshes[name].P:
                self.assertFalse(any(sm._point_in_poly(x, z, q) for q in keep), (name, round(x, 1), round(z, 1)))

    def test_the_boards_show_the_feed_at_the_pictures_aspect(self):
        """Both boards show a crop of the 640 x 448 feed picture (u 0 to 0.625, v 0 to 0.875 of the render target) at the
        picture's own aspect, never stretched, between their stat wings; the north board's picture runs with x (screen
        right from the field)."""
        q = ne.PARAMS["boards"]
        for aspect in (q["north_w"] * q["feed"] / q["north_h"], q["south_w"] * q["feed"] / q["south_h"]):
            (u0, u1), (v0, v1) = self.model.board_crop(aspect)
            self.assertGreaterEqual(u0, 0.0); self.assertLessEqual(u1, 0.625 + 1e-9)
            self.assertGreaterEqual(v0, 0.0); self.assertLessEqual(v1, 0.875 + 1e-9)
            self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), aspect, places=2)
        feeds = [(m, strip) for m in self.model.meshes.values() for strip in m.groups.get("jumbo_tron", ())]
        self.assertEqual(len(feeds), 2)
        for m, strip in feeds:
            P = np.array([m.P[i] for i in strip]); U = np.array([m.UV[i][0] for i in strip])
            if P[:, 2].mean() < 0:
                self.assertGreater(np.corrcoef(P[:, 0], U)[0, 1], 0.9)

    def test_markers_positions(self):
        self.assertEqual(len(self.model.markers["jumbo"]), 2)
        self.assertGreaterEqual(len(self.model.light_points), 16)
        pts = ne.flare_points(self.model)
        self.assertEqual(len(pts), 4)
        self.assertEqual(len({(round(p[0]), round(p[2])) for p in pts}), 4)


class Cameras(unittest.TestCase):
    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(ne.gillette_shots(), ne.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            if "pitch" not in present:
                self.assertEqual(shot["pitch"], 0.0)
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        """xemu draws a flare marker's lens flare through anything (u6's labs 2 and 3), so no shot may have one in its
        frustum along its 8 s path (a vertical field of view on a 16:9 picture, 3 degrees of margin)."""
        model = ne.build()
        flares = [np.array(p, float) for p in ne.flare_points(model)]
        for p in flares:
            self.assertGreater(p[1], 250.0)
        for k, shot in enumerate(ne.gillette_shots()):
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
        outside = [s for s in ne.gillette_shots() if max(abs(s["eye"][0]), abs(s["eye"][2])) > 150]
        self.assertGreaterEqual(len(outside), 2)

    def test_eyes_stay_in_the_open(self):
        model = ne.build()
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P])
        for k, s in enumerate(ne.gillette_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        retail = ne.read_retail(EXTRACTED)
        for name in ("s16dd.iff", "s16ns.iff"):
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), ne.CAMERA_COMPONENTS_PRESENT, name)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class SceneMarkers(unittest.TestCase):
    def test_no_marker_registers_a_glow(self):
        """0x7F210 registers a glow at every marker whose name holds "light" (u6 and st, PROVED IN GAME), so no marker of
        the Gillette Stadium scene may carry the word."""
        retail = ne.read_retail(EXTRACTED)
        for name in ("s16dd.iff", "s16nd.iff"):
            sc = ne.build_scene(retail[name], name, ne.build())
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
        retail = ne.read_retail(EXTRACTED)
        entry = next(e for e in mv.LEAGUE_ART if e["key"] == ne.LEAGUE_BANNER)
        art = ne._rgba(mv.DATA_DIR / entry["art"])
        _i, dry = ne.league_banner(retail["s16dd.iff"], "s16dd.iff")
        for x0, y0, x1, y1 in entry["rects"]:
            self.assertTrue(np.array_equal(dry[y0:y1, x0:x1], art[y0:y1, x0:x1]))
        self.assertIsNone(ne.league_banner(retail["s16ns.iff"], "s16ns.iff"))
        index, snow = ne.league_banner(retail["s16ns.iff"], "s16ns.iff", retail["s16nd.iff"])
        c = ml.bundle_scenes(retail["s16ns.iff"])["stadium"]
        rec, dec = ml._scene(retail["s16ns.iff"], c)
        before = ml.read_p8(dec, c.system_bytes, ml.texture_rows(rec)[ne.LEAGUE_BANNER])[0]
        changed = sum(int(not np.array_equal(snow[y0:y1, x0:x1], before[y0:y1, x0:x1])) for x0, y0, x1, y1 in entry["rects"])
        self.assertGreater(changed, 0)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Field(unittest.TestCase):
    def test_the_field_fits_with_the_bands_and_the_patriots_art(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = ne.read_retail(EXTRACTED)
        name = "s16dd.iff"
        chunk = ml.bundle_scenes(retail[name])["field"]
        team = {"endzone_N_M": np.full((128, 256, 4), (10, 10, 10, 235), np.uint8)}
        span, info = ne.field_span(retail[name], name, team=team)
        self.assertEqual(len(span), 32 + chunk.stored_size)
        out = bytes(retail[name][:chunk.offset]) + span + bytes(retail[name][chunk.offset + len(span):])
        rec, dec = ml._scene(out, ml.bundle_scenes(out)["field"])
        g = sm._field_shape(rec, "A_grass_color")
        st0, st1 = sm._stream(g, 0), sm._stream(g, 1)
        su, sv, ou, ov = struct.unpack_from("<4f", dec, g["record_offset"] + 0x30)
        for i in sm._submesh_vertices(rec, dec, g, ne.GRASS_MATERIAL):
            _x, _y, z = struct.unpack_from("<3f", dec, st0["offset"] + st0["stride"] * i)
            qu = struct.unpack_from("<h", dec, st1["offset"] + st1["stride"] * i + 4)[0]
            self.assertAlmostEqual(qu / 32767.0 * su + ou, (45.72 - z / 100.0) / 91.44, places=3)

    def test_the_two_ends_share_their_textures_and_each_takes_its_own_half(self):
        """s16 lays both ends' panels on the same three textures (endzone_N_* at -z, endzone_S_* at +z; PROVED OFFLINE):
        the north art goes in the north panels' half and the south art in the south panels' half (u6's split)."""
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = ne.read_retail(EXTRACTED)
        name = "s16dd.iff"
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
            self.assertEqual(rows[f"endzone_N_{p}"]["index"], rows[f"endzone_S_{p}"]["index"])
        north = {f"endzone_N_{p}": np.full((128, 256, 4), (200, 10, 40, 255), np.uint8) for p in "LMR"}
        south = {f"endzone_S_{p}": np.full((128, 256, 4), (10, 40, 200, 255), np.uint8) for p in "LMR"}
        painted = ne.paint_field(dec, rec, chunk.system_bytes, "d", team=dict(north, **south))
        for p in "LMR":
            rgba = ml.read_p8(painted, chunk.system_bytes, rows[f"endzone_N_{p}"])[0][..., :3].astype(float)
            h = rgba.shape[0] // 2
            top, bottom = rgba[:h].reshape(-1, 3).mean(0), rgba[h:].reshape(-1, 3).mean(0)
            self.assertNotEqual(bool(top[0] > top[2]), bool(bottom[0] > bottom[2]))

@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class VenueRow(unittest.TestCase):
    def test_the_row_names_the_stadium_and_its_weather(self):
        from mod_editor.core import nfl2k5_gillette_venue as vv
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_roster_records as rr
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = archive.entries[vv.ROST_OUTER_INDEX]
            data = archive.read(e.virtual_offset, e.size)
        self.assertEqual(vv.rost_state(data), "retail")
        after, receipt = vv.rost_gillette(data)
        self.assertEqual(len(after), len(data))
        self.assertEqual(vv.rost_state(after), "applied")
        again, _receipt2 = vv.rost_gillette(after)
        self.assertEqual(again, after)
        H = rr.RESOURCE_HEADER_SIZE
        changed = [i - H for i, (a, b) in enumerate(zip(data, after)) if a != b]
        rec_off = receipt["records"][0]["record_offset"]
        block = receipt["records"][0]["block"]
        for i in changed:
            self.assertTrue(block[0] <= i < block[1] or rec_off <= i < rec_off + 0x80, i)
        body = after[H:]
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x18)[0], 0)          # open air: the field is open
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x1C)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x04)[0], vv.CAPACITY)
        self.assertEqual(body[rec_off + 0x28:rec_off + 0x7C], data[H:][rec_off + 0x28:rec_off + 0x7C])
        # composes with the 2026 venue renames in either order
        a, _ = mv.rost_rename(after)
        b, _ = vv.rost_gillette(mv.rost_rename(data)[0])
        self.assertEqual(a, b)



class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s16_to_the_model(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s14", "s16", "s00", "s20", "s01", "s22")}, league={"nfl_shield": {}},
                   skipped=[])
        without = [p for p, _t in mv.venues_to_write(art)]
        mine = [p for p, _t in mv.venues_to_write(art, **{"gillette": True})]
        self.assertIn("s16", without)
        self.assertEqual(set(without) - set(mine), {"s16"})
        both = [p for p, _t in mv.venues_to_write(art, hard_rock=True, gillette=True, state_farm=True)]
        self.assertEqual(set(without) - set(both), {"s14", "s16", "s00"})

    def test_option_is_off_in_every_preset_and_runs_before_modern_surfaces(self):
        import inspect
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as bs
        key = "modern_gillette"
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get(key), False, name)
        self.assertIn(key, mod_build.availability())
        self.assertIn(key, bs.FEATURE_KEYS)
        self.assertIs(mod_build.BuildPlan.__dataclass_fields__[key].default, False)
        src = inspect.getsource(mod_build)
        steps = [src.index(f'{{"step": "{k}"') for k in ("modern_color_bundles", "modern_venues_2026",
                                                          "modern_state_farm", "modern_hard_rock", "modern_gillette",
                                                          "modern_surfaces")]
        self.assertEqual(steps, sorted(steps))

    def test_the_4x_pack_names_a_master_for_every_material(self):
        import nfl2k5_gillette_model_pack as pack
        from mod_editor.core import nfl2k5_stadium_environment as env
        for tod in "dan":
            for material in ne.MATERIALS:
                rel = pack.master_for(material, "d", None, tod)
                art = env.ART_DIR if material.startswith("env_") else ne.ART_DIR
                self.assertTrue((art / rel).is_file(), (tod, material, rel))
        for material in (ne.GRASS_MATERIAL, ne.OUTSIDE_MATERIAL):
            rel = pack.master_for(material, "d", None)
            self.assertTrue((ne.ART_DIR / rel).is_file(), (material, rel))
            self.assertIsNone(pack.master_for(material, "s", None))


@unittest.skipUnless(EXTRACTED.is_dir() and ne.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    def test_compiled_stretches_equal_their_pins(self):
        retail = ne.read_retail(EXTRACTED)
        for name in ("s16dd.iff", "s16ns.iff"):
            model, info = ne.model_bundle(retail[name], name, ne.build(), cameras=ne.gillette_shots(),
                                          dry_bundle=retail[ne.dry_of(name)])
            self.assertEqual(len(model), len(retail[name]))
            start, end = ne.stretch(retail[name])
            pin = ne._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(ne.sha(model[start:end]), pin["model_sha256"], name)
            self.assertEqual(ne.sha(retail[name][start:end]), pin["retail_sha256"])
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"])

    def test_every_bundle_is_pinned_and_the_registry_pins_the_ends(self):
        import json
        pins = ne.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(ne.VARIANTS))
        for p in pins["bundles"]:
            self.assertLess(p["vertices"], 30000)
        text = ne.PINS_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
        registry = json.loads((ROOT / "mod_editor" / "capabilities" / "registry.v1.json").read_text(encoding="utf-8"))
        row = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.stadiums_fields.modern_gillette")
        first, last = ne._pin("s16dd.iff"), ne._pin("s16ns.iff")
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
        pngs = sorted(ne.ART_DIR.rglob("*.png"))
        manifest = json.loads((ne.ART_DIR / "art.json").read_text(encoding="utf-8"))["art"]
        self.assertEqual(len(pngs), len(manifest))
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(),
                                                            png.stat().st_size), rel)
            with Image.open(png) as image:
                self.assertEqual((row["width"], row["height"]), image.size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_gillette_model.py", "mod_editor/core/nfl2k5_gillette_venue.py",
                    "data/nfl2k5_gillette_model/footprint.json", "data/nfl2k5_gillette_model/pins.json",
                    "data/nfl2k5_gillette_model/art/art.json", "tests/mod_editor/test_nfl2k5_gillette_model.py"):
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
    """Modern playing surfaces (tf) runs after every stadium writer. With it on too, the new s16 field takes tf's
    colours (its solve for the venue's target under the bundle's own light: the row stays open air) and reads applied under
    tf's deep status; before tf the model bundle is tf's input (unsurfaced, never foreign, so tf's step does not refuse
    it). The stadium and camera stretch is the model's alone."""

    def _check(self, name, *, graded):
        import hashlib
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_sofi_model as sm
        from mod_editor.core import nfl2k5_gillette_venue as vv
        ml = sm._ml()
        retail = ne.read_retail(EXTRACTED)
        pins = ne._venue_pins()
        settings = colour.normalize_settings({}) if graded else None
        current = colour.modern_bundle(retail[name])[0] if graded else retail[name]
        team = {"endzone_N_M": np.full((128, 256, 4), PAINT, np.uint8)}
        _n, model, _info = ne._compose((name, retail[name], current, settings, pins[name]["outer"], team,
                                           retail[ne.dry_of(name)]))
        before = ms.bundle_report(_Archive(model), name, _Entry(len(model)), None, deep=True)
        self.assertEqual(before["state"], "retail", before)
        indoor = vv.GILLETTE_WORDS[1] == 1
        self.assertFalse(indoor)
        out, rec = ms.surface_bundle(model, name, indoor=indoor, colour_settings=settings)
        self.assertEqual(len(out), len(model))
        look = ms.venue_look("s16")
        cls_ = ms.light_class(name, indoor)
        self.assertEqual((rec["look"], rec["light"]), (look, cls_))
        self.assertEqual(rec["field"]["target"], [round(v, 2) for v in ms.venue_target("s16", look, cls_)])
        self.assertIn("field", {e["kind"] for e in rec["edits"]})
        start, end = ne.stretch(retail[name])
        self.assertEqual(out[start:end], model[start:end])
        chunk = ml.bundle_scenes(out)["field"]
        frec, fdec = ml._scene(out, chunk)
        rows = ml.texture_rows(frec)
        rgba, _pal = ml.read_p8(fdec, chunk.system_bytes, rows[ne.GRASS_MATERIAL])
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
        self._check("s16dd.iff", graded=False)

    def test_a_graded_rain_field_takes_the_modern_surface(self):
        self._check("s16nr.iff", graded=True)


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
        tris = _feed_triangles(ne.build())
        self.assertTrue(tris)
        for k, shot in enumerate(ne.gillette_shots()):
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
                    c = ne.light("jumbo_tron", P, N, tod, weather, outside=outside)
                    self.assertTrue((c[:, :3] == ne.FEED_VERTEX).all() and (c[:, 3] == 255).all(), (tod, weather))
        self.assertTrue(0.85 <= 2 * ne.FEED_VERTEX / 255 <= 1.0)


if __name__ == "__main__":
    unittest.main()
