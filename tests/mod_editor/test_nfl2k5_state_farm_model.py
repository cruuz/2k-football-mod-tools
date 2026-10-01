"""State Farm Stadium model (st3): geometry, the roof drawn open with its parked panels and Brunel trusses, the end
boards' feed crop, markers, cameras, the collapsed cityscape, and the field with the Cardinals' art on tf's palette."""
import math
import sys
import unittest
from official_marks_fixture import requires_real_pack
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_state_farm_model as sf  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = sf.build()

    def test_budget(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 22000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)

    def test_field_wall_clears_the_sideline_props(self):
        """The wall stays outside the retail s00 sideline props (x -36.1 to 36.1; z -61.9 to 59.3)."""
        loop = self.model.loop
        side = [lp for lp in loop if abs(lp.z) < 40]
        self.assertGreaterEqual(min(lp.x for lp in side if lp.x > 0), 37.1)
        self.assertLessEqual(max(lp.x for lp in side if lp.x < 0), -37.1)
        end = [lp for lp in loop if abs(lp.x) < 12]
        self.assertGreaterEqual(min(lp.z for lp in end if lp.z > 0), 62.9)
        self.assertLessEqual(max(lp.z for lp in end if lp.z < 0), -62.9)

    def test_the_stacks_fit_inside_the_drum(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        ring = [tuple(p) for p in sf.footprint()["facade"]]
        for lp, sec in zip(self.model.loop, self.model.secs):
            x, _y, z = self.model.at(lp, sec["rim"][3], 0.0)
            self.assertTrue(sm._point_in_poly(x, z, ring), (round(x, 1), round(z, 1)))

    def test_the_roof_is_open_over_the_field_and_covers_the_stands(self):
        """The opening covers the whole field of play (the sidelines at 24.4 m, the end lines at 54.9 m); every rim lies
        under the fixed roof with 3 m or more over it; the crown is the rails' tangent point, 206 ft over grade."""
        m = self.model
        for x in (-24.4, 24.4):
            for z in (-54.8, 54.8):
                self.assertTrue(m.in_opening(x, z))
        for lp, sec in zip(m.loop, m.secs):
            x, _y, z = m.at(lp, sec["rim"][0], 0.0)
            self.assertFalse(m.in_opening(x, z))
            self.assertGreater(m.roof_under(x, z), sec["rim"][2] + 3.0, (round(x, 1), round(z, 1)))
        self.assertAlmostEqual(sf.PARAMS["roof"]["crown"] - sf.GRADE, 206 * 0.3048, delta=0.1)

    def test_the_panels_are_parked_open_over_the_ends(self):
        """Each retractable panel (78.6 x 83.8 m) sits over the fixed roof beyond the opening's end, above the fabric
        (main, 2026-09-27: the panels shown parked open so the opening reads as a roof that is open)."""
        m = self.model
        q = sf.PARAMS["roof"]
        mesh = m.meshes["sf_panels"]
        P = np.array([mesh.P[i] for st in mesh.groups["sf_panel_top"] for i in st])
        for sgn in (-1, 1):
            half = P[np.sign(P[:, 2]) == sgn]
            self.assertTrue(len(half))
            self.assertGreaterEqual(float(np.min(np.abs(half[:, 2]))), q["oz"] - 1e-6)
            for x, y, z in half:
                self.assertGreater(y, m.roof_top(x, z) + 0.5)
        self.assertIn("sf_truss", m.meshes["sf_truss"].groups)

    def test_the_boards_stand_at_the_ends_facing_the_field(self):
        """The north board 30 x 117 ft (Daktronics 2022) and the south board, each at its end facing the field, with a
        crop of the feed picture at its own aspect."""
        q = sf.PARAMS["boards"]
        self.assertAlmostEqual(q["w"], 117 * 0.3048, delta=0.1)
        self.assertAlmostEqual(q["h"], 30 * 0.3048, delta=0.1)
        (u0, u1), (v0, v1) = self.model.board_crop(q["w"] / q["h"])
        self.assertLessEqual(u1, 0.625 + 1e-9)
        self.assertLessEqual(v1, 0.875 + 1e-9)
        self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), q["w"] / q["h"], places=3)
        north, south = self.model.board_frames
        self.assertLess(float(north["centre"][2]), 0.0)
        self.assertGreater(float(south["centre"][2]), 0.0)
        for b in (north, south):
            self.assertLess(float(np.dot(b["face"], b["centre"])), 0.0)

    def test_the_drum_wordmark_sits_on_silver_between_two_slots(self):
        """Each drum wordmark centres on the silver middle of a petal (the drum texture's glass slot is the first tenth
        of every 40 m petal), fits between the two slots, faces out and stands 0.4 m proud of the drum wherever it spans
        it (a sign across a slot lost its dark letters to the dark glass behind its transparent ground: pass 2's flyover
        sheet, shot 1)."""
        q, lq = sf.PARAMS["facade"], sf.PARAMS["logo"]
        self.assertLessEqual(lq["w"], (1.0 - sf.StateFarm.SLOT_U) * q["petal"])
        outline = [np.array(p, float) for p in self.model.outline()]
        segs, s = [], 0.0
        for i, a in enumerate(outline):
            b = outline[(i + 1) % len(outline)]
            n = float(np.hypot(*(b - a)))
            if n >= 0.05:
                segs.append((a, b, s, n))
                s += n
        f = self.model.meshes["sf_facade"]
        P = np.array(f.P)
        L = P[sorted({i for st in f.groups["sf_logo"] for i in st})]
        D = P[sorted({i for st in f.groups["sf_drum"] for i in st})]
        for side in (-1, 1):
            sign = L[np.sign(L[:, 0]) == side]
            c = sign.mean(0)
            a, b = sign[np.argmin(sign[:, 2])], sign[np.argmax(sign[:, 2])]
            right = (b - a) * np.array([1.0, 0.0, 1.0])
            right /= np.linalg.norm(right)
            face = np.array([right[2], 0.0, -right[0]]) * (1.0 if right[2] * side > 0 else -1.0)
            self.assertGreater(face[0] * side, 0.95)
            rel = D - c
            near = (np.abs(rel @ right) <= lq["w"] / 2 + 0.5) & (np.abs(rel[:, 1]) <= lq["h"])
            self.assertTrue(near.any())
            self.assertLessEqual(float((rel @ face)[near].max()), -0.4 + 1e-6, side)
            # the arc length of the sign's foot on the outline, in petals: the silver middle of its petal
            best = None
            for a2, b2, s0, n in segs:
                t_ = float(np.clip(np.dot(c[[0, 2]] - a2, b2 - a2) / n ** 2, 0.0, 1.0))
                d = float(np.hypot(*(a2 + (b2 - a2) * t_ - c[[0, 2]])))
                if best is None or d < best[0]:
                    best = (d, s0 + n * t_)
            frac = (best[1] / q["petal"]) % 1.0
            self.assertAlmostEqual(frac, (sf.StateFarm.SLOT_U + 1.0) / 2.0, delta=0.02, msg=side)

    def test_materials(self):
        mats = {mat for m in self.model.meshes.values() for mat in m.groups}
        self.assertTrue({"sf_seat_front", "sf_seat_mid", "sf_seat_back", "crowd", "sf_fabric_under", "sf_fabric_top",
                         "sf_panel_top", "sf_truss", "sf_drum", "sf_logo", "LIGHT_sf_board_wing", "env_band", "env_lot", "env_far"} <= mats)
        self.assertTrue(mats <= set(sf.MATERIALS) | {"crowd", "jumbo_tron"}, mats - set(sf.MATERIALS))
        self.assertFalse({mat for mat in mats if "usb" in mat})

    def test_markers(self):
        self.assertEqual(len(self.model.markers["jumbo"]), 2)
        self.assertGreaterEqual(len(self.model.light_points), 16)
        self.assertEqual(len(sf.flare_points(self.model)), 4)

    def test_crowd_uv_convention(self):
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)


class Cameras(unittest.TestCase):
    def test_no_shot_lets_the_feed_screens_fill_the_view(self):
        """The feed screens show the game's own frame, so a shot the screens fill feeds back to solid white (st, PROVED IN
        GAME at AT&T Stadium, 2026-09-27): over every shot's 8 s path the screens cover at most 25 % of the frame."""
        from mod_editor.core import nfl2k5_usbank_model as usb
        model = sf.build()
        for k, shot in enumerate(sf.state_farm_shots()):
            worst, _trace = usb.feed_coverage(model, shot)
            self.assertLessEqual(worst, usb.FEED_COVERAGE_LIMIT, (k + 1, round(worst, 3)))

    def test_every_shot_wants_what_its_camera_can_carry(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for shot, present in zip(sf.state_farm_shots(), sf.CAMERA_COMPONENTS_PRESENT):
            self.assertEqual(sm.effective_shot(shot, present)["eye"], shot["eye"])
            for comp in shot.get("rates", {}):
                self.assertIn(comp, present)

    def test_two_exterior_shots(self):
        outside = [s for s in sf.state_farm_shots() if max(abs(s["eye"][0]), abs(s["eye"][2])) > 150]
        self.assertGreaterEqual(len(outside), 2)

    def test_eyes_stay_in_the_open(self):
        model = sf.build()
        P = np.concatenate([np.array(m.P) for m in model.meshes.values() if m.P and m.name != "sf_hills"])
        for k, s in enumerate(sf.state_farm_shots()):
            r = s.get("rates", {})
            for t in np.linspace(0, 8, 9):
                eye = np.array(s["eye"]) + np.array([r.get("x", 0), r.get("y", 0), r.get("z", 0)]) * t
                self.assertGreater(np.min(np.linalg.norm(P - eye, axis=1)), 3.0, (k, t))

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
    def test_the_camera_table_matches_the_retail_scenes(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_sofi_model as sm
        retail = sf.read_retail(EXTRACTED)
        for name in ("s00dd.iff", "s00ns.iff"):
            _c, dec = mm._cameras_chunk(retail[name])
            self.assertEqual(tuple(sm.camera_components(dec)), sf.CAMERA_COMPONENTS_PRESENT, name)


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
    """The Cardinals' end zones and a new midfield quad, the grass and apron on tf's palette in the bundle's own light
    class (s00 is open air: the rain bundle takes tf's rain look); Modern surfaces keeps the field and reads it applied."""

    @classmethod
    @requires_real_pack("modern_state_farm")
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_sofi_model as sm
        ml = sm._ml()
        retail = sf.read_retail(EXTRACTED)
        cls.name = name = "s00dr.iff"
        cls.retail = retail[name]
        _n, model, cls.minfo = sf._compile((name, retail[name], retail[sf.dry_of(name)]))
        logo = np.zeros((256, 256, 4), np.uint8)
        logo[:128, :, :] = (151, 35, 63, 255)
        team = {"endzone_N_M": np.full((128, 256, 4), (151, 35, 63, 255), np.uint8),
                "endzone_S_M": np.full((128, 256, 4), (255, 255, 255, 255), np.uint8), "center_logo": logo}
        field, cls.info = sf.field_span(retail[name], name, team=team)
        chunk = ml.bundle_scenes(retail[name])["field"]
        cls.span_size = 32 + chunk.stored_size
        cls.field = field
        cls.ours = model[:chunk.offset] + field + model[chunk.offset + len(field):]
        cls.after, cls.rec = ms.surface_bundle(cls.ours, name, indoor=False)

    def test_the_bundle_keeps_its_size_and_decodes_under_retail(self):
        self.assertEqual(len(self.ours), len(self.retail))
        self.assertEqual(len(self.field), self.span_size)
        self.assertLess(self.minfo["system"] + self.minfo["video"], self.minfo["retail_system"] + self.minfo["retail_video"])

    def test_the_field_is_on_tfs_palette_in_the_rain_light(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        surf = self.info["surface"]
        self.assertEqual((surf["look"], surf["light"]), (ms.venue_look("s00"), "rain"))
        self.assertIsNotNone(self.info["midfield"])

    def test_modern_surfaces_keeps_this_field_and_reads_it_applied(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        self.assertFalse(self.rec["field"]["refit"])
        at, size = ms.bundle_sites(self.ours)["field"]
        self.assertEqual(self.after[at:at + size], self.ours[at:at + size])
        row = ms.bundle_report(_Archive(self.after), self.name, _Entry(len(self.after)), None, deep=True)
        self.assertEqual(row["state"], "applied", row)



@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class VenueRow(unittest.TestCase):
    def test_the_row_names_state_farm_and_stays_open_air(self):
        import struct
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_roster_records as rr
        from mod_editor.core import nfl2k5_state_farm_venue as sv
        from mod_editor.core import nfl2k5_lucas_oil_venue as lv_
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = archive.entries[sv.ROST_OUTER_INDEX]
            data = archive.read(e.virtual_offset, e.size)
        self.assertEqual(sv.rost_state(data), "retail")
        after, receipt = sv.rost_state_farm(data)
        self.assertEqual(len(after), len(data))
        self.assertEqual(sv.rost_state(after), "applied")
        self.assertEqual(sv.rost_state_farm(after)[0], after)
        H = rr.RESOURCE_HEADER_SIZE
        rec_off = receipt["records"][0]["record_offset"]
        block = receipt["records"][0]["block"]
        for i in [i - H for i, (a, b) in enumerate(zip(data, after)) if a != b]:
            self.assertTrue(block[0] <= i < block[1] or rec_off <= i < rec_off + 0x80, i)
        body = after[H:]
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x18)[0], 0)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x1C)[0], 1)
        self.assertEqual(struct.unpack_from("<I", body, rec_off + 0x04)[0], sv.CAPACITY)
        self.assertEqual(body[rec_off + 0x28:rec_off + 0x7C], data[H:][rec_off + 0x28:rec_off + 0x7C])
        # the header's section pointer (s00's name opens the pool) keeps pointing at the pool's start
        self.assertEqual(struct.unpack_from("<i", body, rec_off - 4)[0], struct.unpack_from("<i", data[H:], rec_off - 4)[0])
        self.assertEqual(rec_off - 4 + struct.unpack_from("<i", body, rec_off - 4)[0] - 1, block[0])
        a, _ = mv.rost_rename(after)
        b, _ = sv.rost_state_farm(mv.rost_rename(data)[0])
        self.assertEqual(a, b)
        c, _ = lv_.rost_lucas_oil(after)
        d_, _ = sv.rost_state_farm(lv_.rost_lucas_oil(data)[0])
        self.assertEqual(c, d_)


class Composition(unittest.TestCase):
    def test_the_venue_art_leaves_s00_to_state_farm(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s00", "s11", "s15", "s22")}, league={"nfl_shield": {}}, skipped=[])
        with_it = [p for p, _t in mv.venues_to_write(art, state_farm=True)]
        without = [p for p, _t in mv.venues_to_write(art)]
        self.assertEqual(set(without) - set(with_it), {"s00"})

    def test_option_is_off_in_every_preset_and_runs_before_modern_surfaces(self):
        import inspect
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as bs
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_state_farm"), False, name)
        self.assertIn("modern_state_farm", mod_build.availability())
        self.assertIn("modern_state_farm", bs.FEATURE_KEYS)
        src = inspect.getsource(mod_build)
        steps = [src.index(f'{{"step": "{k}"') for k in ("modern_venues_2026", "modern_lucas_oil", "modern_state_farm",
                                                         "modern_surfaces")]
        self.assertEqual(steps, sorted(steps))

    @requires_real_pack("modern_state_farm")
    def test_the_4x_pack_names_a_master_for_every_material(self):
        import nfl2k5_state_farm_model_pack as pack
        from mod_editor.core import nfl2k5_stadium_environment as env
        for material in sf.MATERIALS:
            rel = pack.master_for(material, None, "d")
            art = env.ART_DIR if material.startswith("env_") else sf.ART_DIR
            self.assertTrue(sf.official.resolve_path(art / rel).is_file(), (material, rel))


@unittest.skipUnless(EXTRACTED.is_dir() and sf.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    @requires_real_pack("modern_state_farm")
    def test_compiled_stretches_equal_their_pins(self):
        retail = sf.read_retail(EXTRACTED)
        for name in ("s00dd.iff", "s00ns.iff"):
            model, info = sf.model_bundle(retail[name], name, sf.build(), cameras=sf.state_farm_shots(),
                                          dry_bundle=retail[sf.dry_of(name)])
            start, end = sf.stretch(retail[name])
            pin = sf._pin(name)
            self.assertEqual((pin["offset"], pin["length"]), (start, end - start))
            self.assertEqual(sf.sha(model[start:end]), pin["model_sha256"], name)
            self.assertEqual(sf.sha(retail[name][start:end]), pin["retail_sha256"])
            # the environment kit spends most of pass 2's margin; 4 KB stays spare (8.6 KB at the kit's first pass)
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"] - 4096)

    def test_every_bundle_is_pinned_and_the_registry_pins_the_ends(self):
        import json
        pins = sf.model_pins()
        self.assertEqual(sorted(p["name"] for p in pins["bundles"]), sorted(sf.VARIANTS))
        text = sf.PINS_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
        registry = json.loads((ROOT / "mod_editor" / "capabilities" / "registry.v1.json").read_text(encoding="utf-8"))
        row = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.stadiums_fields.modern_state_farm")
        first, last = sf._pin("s00dd.iff"), sf._pin("s00ns.iff")
        self.assertEqual(row["source_container"]["hash_pins"], [first["retail_sha256"], first["model_sha256"],
                                                                 last["retail_sha256"], last["model_sha256"]])


class ReleaseCatalog(unittest.TestCase):
    def test_the_reviewed_release_catalog_carries_the_art(self):
        import hashlib
        import json
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        pngs = sorted(sf.ART_DIR.rglob("*.png"))
        manifest = json.loads((sf.ART_DIR / "art.json").read_text(encoding="utf-8"))["art"]
        from mod_editor.core import nfl2k5_official_marks as official
        external = [p for p in official.CATALOG if p.startswith("data/nfl2k5_state_farm_model/art/")]
        self.assertEqual(len(pngs) + len(external), len(manifest))
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (hashlib.sha256(png.read_bytes()).hexdigest(), png.stat().st_size), rel)
            with Image.open(png) as image:
                self.assertEqual((row["width"], row["height"]), image.size, rel)
            self.assertIn(rel, allow)
        for rel in ("mod_editor/core/nfl2k5_state_farm_model.py", "mod_editor/core/nfl2k5_state_farm_venue.py",
                    "data/nfl2k5_state_farm_model/footprint.json", "data/nfl2k5_state_farm_model/pins.json",
                    "data/nfl2k5_state_farm_model/art/art.json"):
            self.assertIn(rel, allow)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"', checker)


if __name__ == "__main__":
    unittest.main()
