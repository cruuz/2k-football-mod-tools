"""Lucas Oil Stadium model (st3): geometry, the gabled roof, the north window, the corner boards' feed crop, markers,
cameras, the field with the Colts' art on tf's palette, and the s11 row."""
import math
import sys
import unittest
from official_marks_fixture import requires_real_pack
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_lucas_oil_model as lo  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = lo.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 24000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_field_wall_clears_the_sideline_props(self):
        """The wall stays outside the retail s11 sideline props (x -35.4 to 36.3; the home south piece reaches z 52.4)."""
        loop = self.model.loop
        side = [lp for lp in loop if abs(lp.z) < 40]
        self.assertGreaterEqual(min(lp.x for lp in side if lp.x > 0), 37.3)
        self.assertLessEqual(max(lp.x for lp in side if lp.x < 0), -36.4)
        end = [lp for lp in loop if abs(lp.x) < 12]
        self.assertGreaterEqual(min(lp.z for lp in end if lp.z > 0), 53.4)
        self.assertLessEqual(max(lp.z for lp in end if lp.z < 0), -53.4)

    def test_the_stacks_fit_inside_the_facade(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in lo.footprint()["facade"]]
        for lp, sec in zip(self.model.loop, self.model.secs):
            if "rim" not in sec:
                continue
            x, _y, z = self.model.at(lp, sec["rim"][3], 0.0)
            self.assertTrue(sm._point_in_poly(x, z, ring), (round(x, 1), round(z, 1)))

    def test_the_gabled_roof_covers_the_bowl(self):
        """The roof's underside stays at least 3 m over every rim's top; the ridge on the axis is the roof's top (Uni-Systems:
        the gable's peak runs down the centre of the field) and each half falls to the eaves."""
        m = self.model
        for lp, sec in zip(m.loop, m.secs):
            x, _y, z = m.at(lp, sec["rim"][0], 0.0)
            self.assertGreater(m.roof_under(x, z), sec["rim"][2] + 3.0, (round(x, 1), round(z, 1)))
        q = lo.PARAMS["roof"]
        self.assertAlmostEqual(m.roof_top(0.0, 0.0), q["ridge"], places=6)
        self.assertGreater(m.roof_top(20.0, 0.0), m.roof_top(80.0, 0.0))
        self.assertAlmostEqual(m.roof_top(-50.0, 30.0), m.roof_top(50.0, -30.0), places=6)

    def test_the_north_window_stands_over_the_north_stands(self):
        """The window's sill is over the north stands' back wall and its top under the roof; it is 214 x 88 ft (Uni-Systems)."""
        m = self.model
        q = lo.PARAMS["window"]
        self.assertAlmostEqual(q["w"], 214 * 0.3048, delta=0.1)
        self.assertAlmostEqual(q["h"], 88 * 0.3048, delta=0.1)
        north = [sec for lp, sec in zip(m.loop, m.secs) if m.west_zone(lp)]
        self.assertTrue(north)
        self.assertGreater(q["sill"], max(sec["rim"][2] for sec in north))
        z = m.north_wall_z()
        for x in np.linspace(-q["w"] / 2, q["w"] / 2, 9):
            self.assertLess(m.window_top(x) + 1.0, m.roof_under(x, z))
        self.assertIn("LIGHT_los_window", m.meshes["los_window"].groups)

    def test_the_north_end_has_no_upper_deck(self):
        for lp, sec in zip(self.model.loop, self.model.secs):
            if self.model.west_zone(lp):
                self.assertNotIn("upper", sec)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_materials(self):
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"los_seat_front", "los_seat_mid", "los_seat_back", "crowd", "los_roof_under", "los_truss",
                         "los_panel_top", "los_fixed_top", "LIGHT_los_window", "los_brick", "los_arch_windows",
                         "los_logo", "LIGHT_los_board_wing", "LIGHT_los_towers", "los_sky", "los_banners"} <= mats)
        self.assertTrue(mats <= set(lo.MATERIALS) | {"crowd", "jumbo_tron"}, mats - set(lo.MATERIALS))
        self.assertFalse({mat for mat in mats if "usb" in mat})

    def test_the_boards_stand_in_the_corners_at_the_pictures_aspect(self):
        """Two 37 x 97 ft boards in the north-west and south-east corners (the stadium's facts), each facing the field's
        centre with a crop of the 640 x 448 feed picture at its own aspect."""
        q = lo.PARAMS["boards"]
        self.assertAlmostEqual(q["w"], 97 * 0.3048, delta=0.1)
        self.assertAlmostEqual(q["h"], 37 * 0.3048, delta=0.1)
        (u0, u1), (v0, v1) = self.model.board_crop(q["w"] / q["h"])
        self.assertLessEqual(u1, 0.625 + 1e-9)
        self.assertLessEqual(v1, 0.875 + 1e-9)
        self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), q["w"] / q["h"], places=3)
        nw, se = self.model.board_frames
        self.assertLess(float(nw["centre"][0]), 0.0)
        self.assertLess(float(nw["centre"][2]), 0.0)
        self.assertGreater(float(se["centre"][0]), 0.0)
        self.assertGreater(float(se["centre"][2]), 0.0)
        for b in (nw, se):
            self.assertLess(float(np.dot(b["face"], b["centre"])), 0.0)
        feeds = [s for m in self.model.meshes.values() for s in m.groups.get("jumbo_tron", ())]
        self.assertEqual(len(feeds), 2)

    def test_markers(self):
        self.assertEqual(len(self.model.markers["jumbo"]), 2)
        self.assertGreaterEqual(len(self.model.light_points), 16)
        pts = lo.flare_points(self.model)
        self.assertEqual(len(pts), 4)

    def test_every_sign_reads_left_to_right(self):
        text = ("los_logo", "los_logo_aux", "los_banners", "jumbo_tron", "LIGHT_los_board_wing")
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
                    lo_ = min(strip, key=lambda i: (mesh.UV[i][0], mesh.UV[i][1]))
                    hi = max(strip, key=lambda i: (mesh.UV[i][0], -mesh.UV[i][1]))
                    self.assertGreater(float((np.array(mesh.P[hi]) - np.array(mesh.P[lo_])) @ right), 0.0,
                                       (mesh.name, mat))
                    seen += 1
        self.assertGreater(seen, 10)


class Cameras(unittest.TestCase):
    def test_no_shot_lets_the_feed_screens_fill_the_view(self):
        """The feed screens show the game's own frame, so a shot the screens fill feeds back to solid white (st, PROVED IN
        GAME at AT&T Stadium, 2026-09-27): over every shot's 8 s path the screens cover at most 25 % of the frame."""
        from mod_editor.core import nfl2k5_usbank_model as usb
        model = lo.build()
        for k, shot in enumerate(lo.lucas_oil_shots()):
            worst, _trace = usb.feed_coverage(model, shot)
            self.assertLessEqual(worst, usb.FEED_COVERAGE_LIMIT, (k + 1, round(worst, 3)))

    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(lo.lucas_oil_shots(), lo.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_two_exterior_shots(self):
        outside = [s for s in lo.lucas_oil_shots() if max(abs(s["eye"][0]), abs(s["eye"][2])) > 150]
        self.assertGreaterEqual(len(outside), 2)

    def test_eyes_stay_in_the_open(self):
        model = lo.build()
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P and m.name != "los_sky"])
        for k, s in enumerate(lo.lucas_oil_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))

    def test_no_flare_marker_is_in_any_flyover_shot(self):
        model = lo.build()
        flares = [np.array(p, float) for p in lo.flare_points(model)]
        for k, shot in enumerate(lo.lucas_oil_shots()):
            r = shot.get("rates", {})
            for t in range(0, 9):
                eye = np.array(shot["eye"], float) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                yaw = math.radians(shot["yaw"] + r.get("yaw", 0) * t)
                pitch = math.radians(shot["pitch"] + r.get("pitch", 0) * t)
                f = np.array([-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)])
                right = np.cross(f, (0.0, 1.0, 0.0))
                right /= np.linalg.norm(right)
                upv = np.cross(right, f)
                vf = math.radians(shot["fov"])
                hf = 2 * math.atan(math.tan(vf / 2) * 16 / 9)
                for p in flares:
                    d = (p - eye) / np.linalg.norm(p - eye)
                    x, y, z = d @ right, d @ upv, d @ f
                    inside = z > 0 and abs(math.atan2(x, z)) <= hf / 2 + 0.05 and abs(math.atan2(y, z)) <= vf / 2 + 0.05
                    self.assertFalse(inside, (k + 1, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        retail = lo.read_retail(EXTRACTED)
        for name in ("s11dd.iff", "s11ns.iff"):
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), lo.CAMERA_COMPONENTS_PRESENT, name)


class _Entry:
    def __init__(self, size):
        self.virtual_offset, self.size = 0, size


class _Archive:
    def __init__(self, data):
        self.data = bytes(data)

    def read(self, offset, size):
        return self.data[offset:offset + size]


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Field(unittest.TestCase):
    """The Colts' end zones and midfield in the retail field's own textures, the turf and apron on tf's palette; with
    Modern surfaces on as well the field keeps its bytes and reads applied under tf's deep status."""

    @classmethod
    @requires_real_pack("modern_lucas_oil")
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = lo.read_retail(EXTRACTED)
        cls.name = name = "s11nd.iff"
        cls.retail = retail[name]
        _n, model, cls.minfo = lo._compile((name, retail[name], retail[lo.dry_of(name)]))
        logo = np.zeros((256, 256, 4), np.uint8)
        logo[:128, :, :] = (0, 44, 95, 255)
        team = {"endzone_N_M": np.full((128, 256, 4), (0, 44, 95, 255), np.uint8),
                "endzone_S_M": np.full((128, 256, 4), (255, 255, 255, 255), np.uint8), "center_logo": logo}
        field, cls.info = lo.field_span(retail[name], name, team=team)
        chunk = ml.bundle_scenes(retail[name])["field"]
        cls.span_size = 32 + chunk.stored_size
        cls.field = field
        cls.ours = model[:chunk.offset] + field + model[chunk.offset + len(field):]
        cls.after, cls.rec = ms.surface_bundle(cls.ours, name, indoor=True)

    def test_the_bundle_keeps_its_size_and_decodes_under_retail(self):
        self.assertEqual(len(self.ours), len(self.retail))
        self.assertEqual(len(self.field), self.span_size)
        self.assertLess(self.minfo["system"] + self.minfo["video"], self.minfo["retail_system"] + self.minfo["retail_video"])

    def test_each_end_takes_its_own_art_and_the_midfield_its_logo(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        tx = ml._tools()[0]
        chunk = tx.parse_chunks(self.field, allow_trailing=True)[0]
        rec, dec = ml._scene(self.field, chunk)
        rows = ml.texture_rows(rec)
        n = ml.read_p8(dec, chunk.system_bytes, rows["endzone_N_M"])[0][..., :3].reshape(-1, 3).mean(0)
        s = ml.read_p8(dec, chunk.system_bytes, rows["endzone_S_M"])[0][..., :3].reshape(-1, 3).mean(0)
        self.assertLess(n.mean(), 80.0)
        self.assertGreater(s.mean(), 200.0)
        c = ml.read_p8(dec, chunk.system_bytes, rows["center_logo"])[0]
        self.assertLess(c[:100, :, 0].mean(), 20.0)

    def test_the_field_is_on_tfs_palette(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        surf = self.info["surface"]
        look = ms.venue_look("s11")
        self.assertEqual((surf["look"], surf["light"]), (look, "dome"))
        self.assertEqual(tuple(surf["target"]), tuple(round(v, 2) for v in ms.venue_target("s11", look, "dome")))

    def test_modern_surfaces_keeps_this_field_and_reads_it_applied(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        self.assertFalse(self.rec["field"]["refit"])
        at, size = ms.bundle_sites(self.ours)["field"]
        self.assertEqual(self.after[at:at + size], self.ours[at:at + size])
        row = ms.bundle_report(_Archive(self.after), self.name, _Entry(len(self.after)), None, deep=True)
        self.assertEqual(row["state"], "applied", row)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class FieldWithoutVenueArt(unittest.TestCase):
    """The 2026 venue art off: no team art reaches s11's field, so it keeps the RCA Dome end zones and midfield, takes tf's
    turf and apron and fits its span, with Modern colour and without. The zlib estimate overstates this field past the
    ladder's gate, which once skipped every rung untried (b763, 2026-10-02: the Experimental preset with every modern
    stadium, Modern colour and Modern surfaces but no venue art refused to build at s11ad)."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        cls.name = name = "s11ad.iff"
        cls.retail = lo.read_retail(EXTRACTED)[name]
        cls.chunk = ml.bundle_scenes(cls.retail)["field"]
        cls.span = ml.scene_span(cls.retail, cls.chunk)
        cls.fields = {
            "plain": lo.field_span(cls.retail, name),
            "colour": lo.field_span(cls.retail, name, colour_settings=colour.normalize_settings({}),
                                    outer_index=lo._venue_pins()[name]["outer"]),
        }

    def test_the_field_fits_its_span_with_and_without_colour(self):
        for label, (field, info) in self.fields.items():
            with self.subTest(label):
                self.assertEqual(len(field), len(self.span))
                self.assertEqual(field[:32], self.span[:32])
                self.assertEqual(info["team_art"], [])
                self.assertEqual(info["fit_attempts"], [])
                self.assertEqual(info["colour"], label == "colour")
                self.assertTrue(info["surface"]["refit"])

    def test_the_end_zones_and_midfield_keep_their_retail_texels(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        tx = ml._tools()[0]
        rec, retail = ml._scene(self.retail, self.chunk)
        rows = ml.texture_rows(rec)
        system = self.chunk.system_bytes
        marks = [m for m in lo.TEAM_FIELD if m in rows]
        self.assertTrue(marks)

        def texels(decoded, row):
            return bytes(decoded[system + int(row["pixel_offset"]):system + int(row["palette_offset"])])
        for label, (field, _info) in self.fields.items():
            _rec, decoded = ml._scene(field, tx.parse_chunks(field, allow_trailing=True)[0])
            for material in marks:
                with self.subTest(label, material=material):
                    self.assertEqual(texels(decoded, rows[material]), texels(retail, rows[material]))

    def test_modern_surfaces_keeps_this_field_and_reads_it_applied(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        field, _info = self.fields["plain"]
        ours = self.retail[:self.chunk.offset] + field + self.retail[self.chunk.offset + len(field):]
        after, rec = ms.surface_bundle(ours, self.name, indoor=True)
        self.assertFalse(rec["field"]["refit"])
        at, size = ms.bundle_sites(ours)["field"]
        self.assertEqual(after[at:at + size], ours[at:at + size])
        row = ms.bundle_report(_Archive(after), self.name, _Entry(len(after)), None, deep=True)
        self.assertEqual(row["state"], "applied", row)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class VenueRow(unittest.TestCase):
    def test_the_row_names_lucas_oil_and_keeps_the_dome(self):
        import struct
        from mod_editor.core import nfl2k5_lucas_oil_venue as lv
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_roster_records as rr
        from mod_editor.core import nfl2k5_usbank_venue as uv
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = archive.entries[lv.ROST_OUTER_INDEX]
            data = archive.read(e.virtual_offset, e.size)
        self.assertEqual(lv.rost_state(data), "retail")
        after, receipt = lv.rost_lucas_oil(data)
        self.assertEqual(len(after), len(data))
        self.assertEqual(lv.rost_state(after), "applied")
        self.assertEqual(lv.rost_lucas_oil(after)[0], after)
        H = rr.RESOURCE_HEADER_SIZE
        rec_off = receipt["records"][0]["record_offset"]
        block = receipt["records"][0]["block"]
        for i in [i - H for i, (a, b) in enumerate(zip(data, after)) if a != b]:
            self.assertTrue(block[0] <= i < block[1] or rec_off <= i < rec_off + 0x80, i)
        body = after[H:]
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x18)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x1C)[0], 0)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x04)[0], lv.CAPACITY)
        self.assertEqual(body[rec_off + 0x28:rec_off + 0x7C], data[H:][rec_off + 0x28:rec_off + 0x7C])
        # composes with the 2026 venue renames and with U.S. Bank's row in any order
        a, _ = mv.rost_rename(after)
        b, _ = lv.rost_lucas_oil(mv.rost_rename(data)[0])
        self.assertEqual(a, b)
        c, _ = uv.rost_usbank(after)
        d_, _ = lv.rost_lucas_oil(uv.rost_usbank(data)[0])
        self.assertEqual(c, d_)


class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s11_to_lucas_oil(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s11", "s15", "s25", "s22")}, league={"nfl_shield": {}}, skipped=[])
        with_it = [p for p, _t in mv.venues_to_write(art, lucas_oil=True)]
        without = [p for p, _t in mv.venues_to_write(art)]
        self.assertEqual(set(without) - set(with_it), {"s11"})
        every = [p for p, _t in mv.venues_to_write(art, att=True, levis=True, highmark=True, sofi=True, usbank=True,
                                                    lucas_oil=True)]
        self.assertEqual(set(without) - set(every), {"s11", "s15", "s25", "s07", "s03", "s23", "s24"})

    def test_option_is_off_in_every_preset_and_runs_before_modern_surfaces(self):
        import inspect
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as bs
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_lucas_oil"), False, name)
        self.assertIn("modern_lucas_oil", mod_build.availability())
        self.assertIn("modern_lucas_oil", bs.FEATURE_KEYS)
        src = inspect.getsource(mod_build)
        steps = [src.index(f'{{"step": "{k}"') for k in ("modern_venues_2026", "modern_usbank", "modern_lucas_oil",
                                                         "modern_surfaces")]
        self.assertEqual(steps, sorted(steps))

    @requires_real_pack("modern_lucas_oil")
    def test_the_4x_pack_names_a_master_for_every_material(self):
        import nfl2k5_lucas_oil_model_pack as pack
        from mod_editor.core import nfl2k5_stadium_environment as env
        for tod in "dan":
            for material in lo.MATERIALS:
                rel = pack.master_for(material, None, tod)
                art = env.ART_DIR if material.startswith("env_") else lo.ART_DIR
                self.assertTrue(lo.official.resolve_path(art / rel).is_file(), (tod, material, rel))


@unittest.skipUnless(EXTRACTED.is_dir() and lo.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    @requires_real_pack("modern_lucas_oil")
    def test_compiled_stretches_equal_their_pins(self):
        retail = lo.read_retail(EXTRACTED)
        for name in ("s11dd.iff", "s11ns.iff"):
            model, info = lo.model_bundle(retail[name], name, lo.build(), cameras=lo.lucas_oil_shots(),
                                          dry_bundle=retail[lo.dry_of(name)])
            start, end = lo.stretch(retail[name])
            pin = lo._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(lo.sha(model[start:end]), pin["model_sha256"], name)
            self.assertEqual(lo.sha(retail[name][start:end]), pin["retail_sha256"])
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"])

    def test_every_bundle_is_pinned_and_the_registry_pins_the_ends(self):
        import json
        pins = lo.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(lo.VARIANTS))
        text = lo.PINS_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
        registry = json.loads((ROOT / "mod_editor" / "capabilities" / "registry.v1.json").read_text(encoding="utf-8"))
        row = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.stadiums_fields.modern_lucas_oil")
        first, last = lo._pin("s11dd.iff"), lo._pin("s11ns.iff")
        self.assertEqual(row["source_container"]["hash_pins"], [first["retail_sha256"], first["model_sha256"],
                                                                 last["retail_sha256"], last["model_sha256"]])
        self.assertIs(row["gui"]["default_enabled"], False)


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        import hashlib
        import json
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted(lo.ART_DIR.rglob("*.png"))
        manifest = json.loads((lo.ART_DIR / "art.json").read_text(encoding="utf-8"))["art"]
        from mod_editor.core import nfl2k5_official_marks as official
        external = [p for p in official.CATALOG if p.startswith("data/nfl2k5_lucas_oil_model/art/")]
        self.assertEqual(len(pngs) + len(external), len(manifest))
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            with Image.open(png) as image:
                self.assertEqual((row["width"], row["height"]), image.size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_lucas_oil_model.py", "mod_editor/core/nfl2k5_lucas_oil_venue.py",
                    "data/nfl2k5_lucas_oil_model/footprint.json", "data/nfl2k5_lucas_oil_model/pins.json",
                    "data/nfl2k5_lucas_oil_model/art/art.json"):
            self.assertIn(rel, allow)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"', checker)


if __name__ == "__main__":
    unittest.main()
