"""The shared stadium environment kit (st3): the layouts, the art (reproducible, crisp bands), the geometry (outside the
stadium's keep-out, inside the band, to each venue's budgets, the cameras' eyes kept clear) and the light (the far
ground meets the haze ring and the band at one colour)."""
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

# The Pillow release the shipped stadium environment art was drawn with (tools/nfl2k5_stadium_environment_art.py).
ART_PILLOW = "10.2.0"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_metlife_model as mm  # noqa: E402
from mod_editor.core import nfl2k5_sofi_model as sm  # noqa: E402
from mod_editor.core import nfl2k5_stadium_environment as env  # noqa: E402


class _Model:
    def __init__(self):
        self.meshes = {}


def _ring(r, n=48):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


class Layouts(unittest.TestCase):
    def test_every_venue_has_a_layout_in_its_frame(self):
        for venue in env.STYLE:
            L = env.layout(venue)
            self.assertEqual(L["schema"], env.SCHEMA)
            self.assertEqual(len(L["terrain"]), 360)
            rows = L["landuse"]["rows"]
            self.assertEqual({len(r) for r in rows}, {len(rows)})
            self.assertAlmostEqual((L["frame"]["field_bearing"] - L["frame"]["x_bearing"]) % 360.0, 90.0)
            self.assertIn("OpenStreetMap", L["source"])
            text = (env.DATA_DIR / f"{env.site_of(venue)}.json").read_text(encoding="utf-8")
            self.assertEqual(text, json.dumps(json.loads(text), sort_keys=True, separators=(", ", ": ")) + "\n")
            run = 0
            for ch in text:                         # the release checker's blob guard: no whitespace-free run over 4 KiB
                run = 0 if ch.isspace() else run + 1
                self.assertLessEqual(run, 4096, venue)


class Art(unittest.TestCase):
    def test_the_art_reproduces_pixel_for_pixel(self):
        import PIL
        from PIL import Image
        manifest = json.loads((env.ART_DIR / "art.json").read_text(encoding="utf-8"))["art"]
        for name, row in manifest.items():   # the shipped art always matches its release pins
            shipped = env.ART_DIR / f"{name}.png"
            self.assertEqual(hashlib.sha256(shipped.read_bytes()).hexdigest(), row["sha256"], name)
        if PIL.__version__ != ART_PILLOW:
            self.skipTest(f"the stadium environment art was drawn with Pillow {ART_PILLOW}; this Pillow "
                          f"{PIL.__version__} draws rounded rectangles differently (env_lot's cars), so the "
                          f"regeneration comparison runs only on {ART_PILLOW}")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(ROOT / "tools" / "nfl2k5_stadium_environment_art.py"), tmp,
                            "--venues", *sorted(env.STYLE)], check=True, capture_output=True)
            for name, row in manifest.items():
                shipped = env.ART_DIR / f"{name}.png"
                # Keep the released artifact pin exact. The generator's PNG
                # compression can differ between Pillow/zlib builds; its
                # decoded dimensions and every RGBA byte must still match.
                self.assertEqual(hashlib.sha256(shipped.read_bytes()).hexdigest(), row["sha256"], name)
                with Image.open(shipped) as have, Image.open(Path(tmp) / f"{name}.png") as made:
                    self.assertEqual(have.size, made.size, name)
                    # The procedural noise can round a channel one or two levels differently on another
                    # platform's numpy/libm (seen: Windows CPython under Wine, env_lot); a wrong or broken
                    # texture differs far more, so allow at most 2 levels per channel and a tiny mean.
                    a = np.asarray(have.convert("RGBA"), dtype=np.int16)
                    b = np.asarray(made.convert("RGBA"), dtype=np.int16)
                    diff = np.abs(a - b)
                    self.assertLessEqual(int(diff.max()), 2, name)
                    self.assertLess(float(diff.mean()), 0.05, name)

    def test_every_material_draws_a_texture_by_day_and_night(self):
        from PIL import Image
        for venue in env.STYLE:
            for mat, (key, _cls) in env.materials(venue).items():
                for tod in "dan":
                    self.assertTrue((env.ART_DIR / f"{env.texture_name(key, tod)}.png").is_file(), (venue, mat, tod))
            band = np.asarray(Image.open(env.ART_DIR / f"env_band_{env.site_of(venue)}.png").convert("RGBA"))
            self.assertEqual(set(np.unique(band[..., 3]).tolist()), {0, 255}, venue)   # crisp silhouettes
            self.assertEqual(band.shape[1::-1], tuple(env.STYLE[venue]["band_size"]))
            self.assertTrue((band[-2:, :, 3] == 255).all(), venue)                     # the haze at the foot
            pad = int(round(env.BAND_PAD * band.shape[0]))
            self.assertTrue((band[:pad, :, 3] == 0).all(), venue)                     # the clear top the wrap meets

    def test_rain_and_snow_bundles_keep_their_native_ground(self):
        for venue in env.STYLE:
            for mat in env.materials(venue):
                for w in "rs":
                    name = env.master_name(mat, venue, "d", w)
                    if name is not None:
                        self.assertTrue((env.ART_DIR / name).is_file())
            self.assertIsNone(env.master_name("env_lot", venue, "d", "s"))
            self.assertEqual(env.master_name("env_band", venue, "n"), f"env_band_{env.site_of(venue)}_n.png")
        dry = env.textures("s00", "d", "d")["env_lot"][..., :3].mean()
        snow = env.textures("s00", "d", "s")["env_lot"][..., :3].mean()
        self.assertGreater(snow, dry + 40)


class Dress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keep = _ring(170.0)
        cls.eyes = [(300.0, 40.0, 0.0), (0.0, 20.0, -260.0)]
        cls.models = {}
        for venue in env.STYLE:
            m = _Model()
            m.counts = env.dress(m, venue, grade=5.0, keep_out=[cls.keep], inner=cls.keep, eyes=cls.eyes)
            cls.models[venue] = m

    def test_nothing_inside_the_keep_out_and_nothing_past_the_band(self):
        for venue, m in self.models.items():
            for name in ("env_lots", "env_trees", "env_blocks", "env_green"):
                P = np.array(m.meshes[name].P) if m.meshes[name].P else np.zeros((0, 3))
                if name == "env_trees":
                    per = env.ROUND_TREE if env.STYLE[venue].get("crowns") == "round" else 6
                    P = P.reshape(-1, per, 3).mean(axis=1)        # a tree by its centre (its crown may overhang)
                inside = [p for p in P if sm._point_in_poly(p[0], p[2], self.keep)]
                self.assertLessEqual(len(inside), 0 if name != "env_green" else len(P) // 20, (venue, name))
            for name, mesh in m.meshes.items():
                if not mesh.P:
                    continue
                P = np.array(mesh.P)
                self.assertLessEqual(float(np.hypot(P[:, 0], P[:, 2]).max()), env.BAND_RADIUS + 1.0, (venue, name))
            B = np.array(m.meshes["env_band"].P)
            self.assertTrue(np.allclose(np.hypot(B[:, 0], B[:, 2]), env.BAND_RADIUS))
            V = np.array(m.meshes["env_band"].UV)[:, 1]
            self.assertAlmostEqual(float(V.min()), env.BAND_PAD)                    # the top edge in the clear pad

    def test_each_part_keeps_to_its_budget(self):
        for venue, m in self.models.items():
            budget = dict(env.BUDGET, **env.STYLE[venue].get("budget", {}))
            for part, mesh in (("lots", "env_lots"), ("grass", "env_green"), ("water", "env_water"),
                               ("roads", "env_roads"), ("blocks", "env_blocks"), ("trees", "env_trees")):
                self.assertLessEqual(m.meshes[mesh].count(), budget[part], (venue, part))

    def test_the_cameras_eyes_stay_in_the_open(self):
        for venue, m in self.models.items():
            if not m.meshes["env_blocks"].P:
                continue
            P = np.array(m.meshes["env_blocks"].P)
            for x, _y, z in self.eyes:
                self.assertGreater(float(np.hypot(P[:, 0] - x, P[:, 2] - z).min()), env.EYE_CLEAR - 1e-6, venue)

    def test_the_kit_is_deterministic(self):
        m = _Model()
        env.dress(m, "s00", grade=5.0, keep_out=[self.keep], inner=self.keep, eyes=self.eyes)
        for name, mesh in m.meshes.items():
            self.assertEqual(mesh.P, self.models["s00"].meshes[name].P, name)
            self.assertEqual(mesh.groups, self.models["s00"].meshes[name].groups, name)

    def test_crowns_and_walls_face_out(self):
        # pass 3 reached every venue (st2's five opted in, main 2026-09-29), so every crown is round on a trunk: every
        # crown face looks out of its crown, every trunk face out of its trunk (st3's s15 and st2's s16 sampled)
        self.assertEqual([v for v in env.STYLE if env.STYLE[v].get("crowns") != "round"], [])
        for venue, per, crown in (("s16", env.ROUND_TREE, 18), ("s15", env.ROUND_TREE, 18)):
            tr = self.models[venue].meshes["env_trees"]
            P = np.array(tr.P)
            self.assertTrue(len(P) and len(P) % per == 0, venue)
            for strip in tr.groups["env_tree"][:80]:
                a, b, c = (P[i] for i in strip)
                base = (strip[0] // per) * per
                centre = P[base:base + crown].mean(axis=0)
                self.assertGreater(float(np.dot(np.cross(b - a, c - a), (a + b + c) / 3 - centre)), 0, venue)
            for strip in tr.groups.get("env_trunk", [])[:30]:
                a, b, c = (P[i] for i in strip)
                base = (strip[0] // per) * per
                axis = P[base + crown:base + per].mean(axis=0)
                out = (a + b + c) / 3 - axis
                out[1] = 0.0
                self.assertGreater(float(np.dot(np.cross(b - a, c - a), out)), 0, venue)
        self.assertIn("env_trunk", self.models["s15"].meshes["env_trees"].groups)
        self.assertIn("env_trunk", self.models["s16"].meshes["env_trees"].groups)


class Light(unittest.TestCase):
    def test_the_far_ground_meets_the_haze_at_one_colour(self):
        N = np.array([[0.0, 1.0, 0.0]])
        for venue in env.STYLE:
            for tod in "dan":
                for w in "drs":
                    haze = np.clip(env.haze_colour(venue, tod, w), 0, 255)
                    edge = np.array([[env.HAZE_END, 5.0, 0.0]])
                    foot = np.array([[env.BAND_RADIUS, 5.0, 0.0]])
                    vc = env.light("env_far", edge, N, tod, w, venue)[0, :3].astype(float)
                    mean = env._tex_mean(env.texture_name(env.materials(venue)["env_far"][0], tod), w)
                    far = mean * vc / 255.0
                    inner = env.light("env_haze", edge, N, tod, w, venue)[0, :3].astype(float)
                    outer = env.light("env_haze", foot, N, tod, w, venue)[0, :3].astype(float)
                    self.assertTrue(np.all(np.abs(far - inner) <= 3.0), (venue, tod, w, far, inner))
                    self.assertTrue(np.all(np.abs(outer - haze) <= 1.0), (venue, tod, w, outer, haze))
                    band = env.light("env_band", foot, N, tod, w, venue)[0, :3].astype(float)
                    if env.STYLE[venue].get("sky_haze"):
                        # pass 3: the band's foot row takes the haze (the sky's horizon), its upper rows keep the band's
                        # own light (the family haze, white at night)
                        self.assertTrue(np.all(np.abs(band - haze) <= 1.0), (venue, tod, w))
                        rows = np.array([[env.BAND_RADIUS, 5.0 + y, 0.0] for y in
                                         (-env.BAND_FOOT, env.BAND_MID, env.BAND_MID + 1.0, env.BAND_TOP)])
                        vc = env.light("env_band", rows, np.repeat(N, 4, axis=0), tod, w, venue)[:, :3].astype(float)
                        own = np.full(3, 255.0) if tod == "n" else np.clip(env.band_light(venue, tod, w), 0, 255)
                        self.assertTrue(np.all(np.abs(vc[:2] - haze) <= 1.0), (venue, tod, w))
                        self.assertTrue(np.all(np.abs(vc[2:] - own) <= 1.0), (venue, tod, w))
                    else:
                        self.assertTrue(np.all(np.abs(band - (255.0 if tod == "n" else haze)) <= 1.0), (venue, tod, w))

    def test_pass3_is_the_owners_choice(self):
        """Every model takes the sky's horizon and the round trees: st3's nine, and st2's five once their owner opted in
        (main, 2026-09-29)."""
        for venue in env.STYLE:
            mine = venue in env.ST3_PASS3
            self.assertEqual(bool(env.STYLE[venue].get("sky_haze")), mine, venue)
            self.assertEqual(env.STYLE[venue].get("crowns") == "round", mine, venue)
            self.assertEqual("env_trunk" in env.materials(venue), mine, venue)
            self.assertEqual(env.materials(venue)["env_tree"][0], "env_leaf" if mine else "env_green", venue)
            for tod in "dan":
                for w in "drs":
                    same = np.allclose(env.haze_colour(venue, tod, w), env.band_light(venue, tod, w))
                    self.assertTrue(same or mine, (venue, tod, w))
        self.assertEqual(set(env.STYLE) - set(env.ST3_PASS3), set())


EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class SkyHaze(unittest.TestCase):
    def test_the_sky_haze_is_the_sky_textures_horizon(self):
        """SKY_HAZE is the mean of rows 238 to 250 of the "sky" TXTR of each time of day and weather (the same texture in
        every bundle of that kind; PROVED on the nine s00 bundles and the day ones of three more venues)."""
        import nfl_txtr as tx
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv

        def sky(archive, pin):
            e = archive.entries[pin["outer"]]
            data = archive.read(e.virtual_offset, e.size)
            for c in tx.parse_chunks(data, allow_trailing=True):
                if c.kind != "TXTR":
                    continue
                dec, _ = tx.decode_chunk(data, c)
                t = tx.parse_texture(dec, c)
                if t.name == "sky":
                    a = np.frombuffer(tx.texture_to_rgba(dec, c, t), np.uint8).reshape(t.height, t.width, 4)
                    return a[238:251, :, :3].reshape(-1, 3).astype(float).mean(axis=0)
            return None
        table = mv.venues()
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            pins = {p["name"]: p for p in table["s00"]["bundles"]}
            for tod in "dan":
                for w in "drs":
                    got = sky(archive, pins[f"s00{tod}{w}.iff"])
                    self.assertTrue(np.all(np.abs(got - np.array(env.SKY_HAZE[(tod, w)])) <= 1.0), (tod, w, got))
            for venue in ("s07", "s20", "s25"):
                pin = next(p for p in table[venue]["bundles"] if p["name"] == f"{venue}dd.iff")
                self.assertTrue(np.all(np.abs(sky(archive, pin) - np.array(env.SKY_HAZE[("d", "d")])) <= 1.0), venue)

if __name__ == "__main__":
    unittest.main()
