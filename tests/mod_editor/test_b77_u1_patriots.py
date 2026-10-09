"""Beta 77 u1: the 2026 Patriots recipe (yoke stripe bands, band painting, helmet mips, NE.json) and its repair."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl2k5_team_2026_art as art  # noqa: E402


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


u1 = _load("b77_u1_patriots_test", "tools/b77/u1_patriots.py")
repair = _load("b77_u1_repair_test", "tools/b77/u1_repair.py")

SIZE = (256, 512)       # retail torso texture (rows, columns)
FLAT = {k: v for k, v in u1.YOKE.items() if k != "back_lateral"}    # the seam distance only (the tube's back is flat)


def tube(step: float = 2.0) -> list[np.ndarray]:
    """A welded stand-in for the jersey: front (z +5) and back (z -5) sheets joined over the top (y 70), x -24..24 cm,
    open at the armholes (x +-24) and the hem (y 30). Three UV islands at 4 px per cm: front u = 128 + 4x,
    back u = 384 + 4x, both v = 4 (70 - y); top u = 128 + 4x, v = 170 + 4 (z + 5)."""
    xs = np.arange(-24.0, 24.0 + 1e-9, step)
    ys = np.arange(30.0, 70.0 + 1e-9, step)
    zs = np.arange(-5.0, 5.0 + 1e-9, 2.5)
    tris = []

    def quad(a, b, c, d):
        tris.extend([np.array([a, b, c], float), np.array([a, c, d], float)])
    for x0, x1 in zip(xs[:-1], xs[1:]):
        for y0, y1 in zip(ys[:-1], ys[1:]):
            for z, u0 in ((5.0, 128.0), (-5.0, 384.0)):
                p = lambda x, y: (x, y, z, u0 + 4 * x, 4 * (70 - y))  # noqa: E731
                quad(p(x0, y0), p(x1, y0), p(x1, y1), p(x0, y1))
        for z0, z1 in zip(zs[:-1], zs[1:]):
            p = lambda x, z: (x, 70.0, z, 128 + 4 * x, 170 + 4 * (z + 5))  # noqa: E731
            quad(p(x0, z0), p(x1, z0), p(x1, z1), p(x0, z1))
    return tris


def band_coverage(decoration: dict) -> list[np.ndarray]:
    out = []
    for band in decoration["bands"]:
        cov = np.zeros(SIZE, np.float32)
        for polygon in band["polygons"]:
            cov += art.polygon_coverage(SIZE, polygon)
        out.append(np.clip(cov, 0.0, 1.0))
    return out


class YokeStripes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tris = tube()
        cls.deco = u1.yoke_stripe_bands(cls.tris, ["red", "white", "red"], FLAT)
        cls.cov = band_coverage(cls.deco)

    def at(self, u: int, v: int) -> list[float]:
        return [round(float(c[v, u]), 3) for c in self.cov]

    def test_armhole_is_the_open_boundary_above_the_chest(self):
        segs = u1.armhole_segments(self.tris)
        self.assertTrue(np.all(np.abs(segs[:, [0, 3]]) == 24.0))
        self.assertTrue(np.all(segs[:, [1, 4]].min(axis=1) > 40.0))

    def test_fields_taper_on_the_front_and_end_at_the_yoke_seams(self):
        segs = np.array([[x, 40, z, x, 70, z] for x in (24, -24) for z in (5, -5)], float)
        p = FLAT
        points = np.array([[20, 70, 5], [20, 56.7, 5], [20, 61.6, 5], [-20, 61.6, -5], [20, 50, -5]], float)
        d, width, above = u1.yoke_fields(points, segs, p)
        np.testing.assert_allclose(d, [4, 4, 4, 4, 4], atol=1e-9)
        np.testing.assert_allclose(width, [p["panel_back_cm"], p["panel_front_end_cm"], 8.0, p["panel_back_cm"],
                                           p["panel_back_cm"]], atol=1e-9)
        np.testing.assert_allclose(above, [70 - p["front_end_y"], 0.0, 61.6 - p["front_end_y"],
                                           61.6 - p["back_end_y"], 50 - p["back_end_y"]], atol=1e-9)

    def test_three_bands_in_order_from_the_armhole(self):
        self.assertEqual([b["colour"] for b in self.deco["bands"]], ["red", "white", "red"])
        v = 8                                    # y 67.75-68 cm, above the front taper (panel 9 cm)
        self.assertEqual(self.at(218, v), [1.0, 0.0, 0.0])      # x 22.5 cm: 1.25-1.5 cm from the seam
        self.assertEqual(self.at(206, v), [0.0, 1.0, 0.0])      # 4.25-4.5 cm
        self.assertEqual(self.at(193, v), [0.0, 0.0, 1.0])      # 7.5-7.75 cm
        self.assertEqual(self.at(37, v), [1.0, 0.0, 0.0])       # the other shoulder, mirrored
        self.assertEqual(self.at(180, v), [0.0, 0.0, 0.0])      # 11 cm from the seam: plain jersey
        self.assertEqual(self.at(128, v), [0.0, 0.0, 0.0])      # the neck line stays clear

    def test_front_panel_narrows_and_ends_above_the_back(self):
        # y 59.75-60 cm, d 8.25-8.5 cm: past the narrowed front panel, still inside the back one
        self.assertEqual(self.at(190, 40), [0.0, 0.0, 0.0])
        self.assertEqual(self.at(446, 40), [0.0, 0.0, 1.0])
        # y 55.75-56 cm: below the front yoke seam (56.7), above the back one (55.5)
        self.assertEqual(self.at(218, 56), [0.0, 0.0, 0.0])
        self.assertEqual(self.at(474, 56), [1.0, 0.0, 0.0])
        self.assertEqual(self.at(474, 64), [0.0, 0.0, 0.0])     # y 53.75-54: below both

    def test_bands_cross_the_shoulder_top(self):
        for v in (174, 190, 206):                # the top island, front to back
            self.assertEqual(self.at(218, v), [1.0, 0.0, 0.0])
            self.assertEqual(self.at(206, v), [0.0, 1.0, 0.0])

    def test_pieces_stay_inside_the_texture_gutter(self):
        # 1.5 px of padding across the island outlines; at a corner the padded line meets the neighbouring edge
        # within 1.5 / sin(45 deg) = 2.1 px on this mesh
        for band in self.deco["bands"]:
            pts = np.array([q for polygon in band["polygons"] for q in polygon])
            self.assertGreaterEqual(pts[:, 0].min(), 32 - 2.2)
            self.assertLessEqual(pts[:, 0].max(), 480 + 2.2)

    def test_pieces_meet_without_overlap_inside_an_island(self):
        # the pieces' coverages, summed without clipping: inside the front island no texel is covered twice (the
        # rasteriser fills a shared edge for both pieces, a supersample row per edge through the texel; padding
        # inside the island would cover 1.5 px strips twice, sums near 2)
        for band in self.deco["bands"]:
            total = np.zeros(SIZE, np.float32)
            for polygon in band["polygons"]:
                total += art.polygon_coverage(SIZE, polygon)
            self.assertLess(float(total[3:157, 35:221].max()), 1.5)

    def test_outline_padding_moves_outline_edges_only(self):
        square = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
        same = u1.bleed_outline_edges(square, [], 1.5)
        np.testing.assert_array_equal(same, square)
        padded = u1.bleed_outline_edges(square, [(np.array([0.0, 0.0]), np.array([10.0, 0.0]))], 1.5)
        np.testing.assert_allclose(sorted(padded[:, 1]), [-1.5, -1.5, 10, 10])
        np.testing.assert_allclose(sorted(padded[:, 0]), [0, 0, 10, 10])
        outline = u1.uv_outline_edges(self.tris)
        inner = tuple(sorted(((128.0, 0.0), (136.0, 8.0))))       # a front-island diagonal (x 0..2, y 70..68)
        self.assertNotIn(inner, outline)
        self.assertIn(tuple(sorted(((224.0, 0.0), (224.0, 8.0)))), outline)   # the armhole edge at x 24

    def test_back_lateral_field_runs_straight_down_the_back(self):
        segs = np.array([[x, 40, z, x, 70, z] for x in (24, -24) for z in (5, -5)], float)
        lat = {"x_ref": 26.0, "z_full": -8.0, "z_zero": -1.0}
        params = dict(FLAT, back_lateral=lat)
        pts = np.array([[20, 60, -12], [20, 50, -9], [-21, 60, -8], [20, 60, 0], [20, 60, 5], [20, 60, -4.5]], float)
        d, _, _ = u1.yoke_fields(pts, segs, params)
        flat, _, _ = u1.yoke_fields(pts, segs, FLAT)
        np.testing.assert_allclose(d[:3], [6.0, 6.0, 5.0], atol=1e-9)     # x_ref - |x| on the back
        np.testing.assert_allclose(d[3:5], flat[3:5], atol=1e-9)          # the seam distance over the top and front
        self.assertTrue(min(flat[5], 6.0) < d[5] < max(flat[5], 6.0))     # blended across the shoulder top
        self.assertEqual(u1.YOKE["back_lateral"]["z_zero"], -1.0)

    def test_no_stripe_without_an_armhole(self):
        flat = [t for t in self.tris if np.all(np.abs(t[:, 0]) <= 8)]
        with self.assertRaises(ValueError):
            u1.yoke_stripe_bands(flat, ["red", "white", "red"], FLAT)


class BandPainting(unittest.TestCase):
    def spec(self, tmp: Path) -> "art.Spec":
        path = tmp / "spec.json"
        path.write_text(json.dumps({"schema": art.SCHEMA, "albedo": {
            "navy": "#0A2550", "red": "#C8102E", "white": "#FFFFFF"}}), encoding="utf-8", newline="\n")
        return art.Spec(path)

    def test_pieces_and_neighbouring_bands_show_no_jersey_seam(self):
        with tempfile.TemporaryDirectory() as td:
            spec = self.spec(Path(td))
            m = art.MASTER
            out = np.zeros((16 * m, 32 * m, 4), np.float32)
            out[..., :3] = spec.colour("navy")
            out[..., 3] = 1.0
            item = {"bands": [
                {"colour": "red", "polygons": [[[2, 2], [10.3, 2], [10.3, 12]], [[2, 2], [10.3, 12], [2, 12]]]},
                {"colour": "white", "polygons": [[[10.3, 2], [20.7, 2], [20.7, 12], [10.3, 12]]]},
                {"colour": "red", "polygons": [[[20.7, 2], [28, 2], [28, 7]], [[20.7, 7], [28, 7], [28, 12], [20.7, 12]],
                                               [[20.7, 2], [28, 7], [20.7, 7]]]},
            ]}
            art.decorate(out, spec, [item], None)
            inner = out[2 * m + 1:12 * m - 1, 2 * m + 1:28 * m - 1]
            red = spec.colour("red")
            # every pixel inside the stripes is a mix of the band colours only: no navy fringe at a piece edge (the
            # diagonals) or between bands (x 10.3 and 20.7 split pixels)
            self.assertGreaterEqual(float(inner[..., 0].min()), float(red[0]) - 1e-5)
            np.testing.assert_allclose(inner[..., 3], 1.0, atol=1e-6)
            diagonal = out[7 * m, 6 * m, :3]
            np.testing.assert_allclose(diagonal, red[:3], atol=1e-6)
            self.assertTrue(np.all(out[0, 0, :3] == spec.colour("navy")[:3]))


class SpecFormat(unittest.TestCase):
    def test_dumps_round_trips_with_one_polygon_per_line(self):
        polys = [[[1.5, 2.25], [3.0, 4.0], [5.125, 6.0]], [[7.0, 8.0], [9.0, 10.0], [11.0, 12.0], [13.0, 14.5]]]
        spec = {"team": "NE", "kits": {"home": {"torso": {"decorations": [
            {"bands": [{"colour": "red", "polygons": polys}]}, {"mark": "logo_full", "center": [1, 2]}]}}}}
        before = json.dumps(spec)
        text = u1.dumps_spec(spec)
        self.assertEqual(json.loads(text), spec)
        self.assertEqual(json.dumps(spec), before)
        self.assertTrue(text.endswith("}\n"))
        lines = [line.strip().rstrip(",") for line in text.splitlines()]
        self.assertIn(json.dumps(polys[0], separators=(", ", ": ")), lines)
        self.assertIn(json.dumps(polys[1], separators=(", ", ": ")), lines)


class HelmetMips(unittest.TestCase):
    def test_coarse_levels_keep_texels_whose_footprint_misses_the_scope(self):
        rng = np.random.default_rng(77)
        stored = [rng.integers(0, 256, (s, s, 4), dtype=np.uint8) for s in (8, 4, 2, 1)]
        scope = np.zeros((8, 8), bool)
        scope[0:2, 0:3] = True
        native = stored[0].copy()
        native[scope] = [255, 0, 0, 255]
        tail, locked = u1.authored_mips(stored, native, scope)
        self.assertEqual(len(tail), (16 + 4 + 1) * 4)
        l1 = np.frombuffer(tail[:64], np.uint8).reshape(4, 4, 4)
        l2 = np.frombuffer(tail[64:80], np.uint8).reshape(2, 2, 4)
        l3 = np.frombuffer(tail[80:], np.uint8).reshape(1, 1, 4)
        box = lambda a: ((a.astype(np.int64).reshape(a.shape[0] // 2, 2, a.shape[1] // 2, 2, 4)  # noqa: E731
                          .sum(axis=(1, 3)) + 2) // 4).astype(np.uint8)
        m1 = np.zeros((4, 4), bool)
        m1[0, 0:2] = True
        np.testing.assert_array_equal(l1[~m1], stored[1][~m1])
        np.testing.assert_array_equal(l1[m1], box(native)[m1])
        m2 = np.zeros((2, 2), bool)
        m2[0, 0] = True
        np.testing.assert_array_equal(l2[~m2], stored[2][~m2])
        np.testing.assert_array_equal(l2[m2], box(l1)[m2])
        np.testing.assert_array_equal(l3, box(l2))
        kept = {tuple(c) for c in stored[1][~m1].tolist()} | {tuple(c) for c in stored[2][~m2].tolist()}
        kept |= {tuple(c) for c in native[~scope].tolist()}
        self.assertEqual(set(map(tuple, locked)), kept)

    def test_mismatched_levels_are_refused(self):
        stored = [np.zeros((8, 8, 4), np.uint8), np.zeros((4, 4, 4), np.uint8)]
        with self.assertRaises(ValueError):
            u1.authored_mips(stored, np.zeros((4, 4, 4), np.uint8), np.zeros((4, 4), bool))


class Recipe(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "data/nfl2k5_teams_2026/NE.json").read_text(encoding="utf-8"))

    def test_2026_kits(self):
        kits = self.spec["kits"]
        self.assertEqual(kits["home"]["pants"]["stripe"], [["red", 10], ["jersey_navy", 10], ["red", 10]])
        self.assertEqual(kits["away"]["pants"]["stripe"], [["red", 10], ["white", 10], ["red", 10]])
        self.assertEqual(kits["home"]["pants"]["base_colour"], "pants_silver")
        self.assertEqual(kits["away"]["pants"]["base_colour"], "jersey_navy")
        self.assertEqual(kits["home"]["socks"], {"colour": "jersey_navy"})
        self.assertEqual(kits["away"]["socks"], {"colour": "white"})
        for side, middle, wordmark in (("home", "white", "white"), ("away", "jersey_navy", "jersey_navy")):
            kit = kits[side]
            bands, logo = kit["torso"]["decorations"]
            self.assertEqual([b["colour"] for b in bands["bands"]], ["red", middle, "red"])
            self.assertTrue(all(len(b["polygons"]) > 100 for b in bands["bands"]))
            pts = np.array([q for b in bands["bands"] for poly in b["polygons"] for q in poly])
            self.assertTrue(np.all((pts >= -2) & (pts <= [514, 258])))
            self.assertEqual(logo["mark"], "logo_full")
            self.assertEqual(kit["torso"]["chest_mark"]["mark"], "wordmark")
            self.assertEqual(kit["torso"]["chest_mark"]["colour"], wordmark)
            self.assertEqual(kit["helmet_digits"]["fill"], "helmet_navy")
            self.assertEqual(set(kit["helmet_digits"]["glyph_shapes"]), set("0123456789"))
            self.assertEqual(kit["unif_color"]["facemask"], "#C8102E")
            self.assertEqual(kit["arm_digits"], "none")
            self.assertEqual((kit["digits"]["outline"], kit["digits"]["outline2"]), ("number_silver", "red"))

    def test_sources_are_recorded(self):
        sources = self.spec["sources_u1_b77"]
        self.assertTrue(all("https://" in text for key, text in sources.items() if key != "placement_reference"))
        self.assertIn("no file or pixel reused", sources["placement_reference"])
        self.assertIn("uniform_shoot_2026", sources)
        self.assertIn("pat_patriot_throwback", self.spec["alternates_2026_not_built"])
        self.assertEqual(self.spec["u1_b77"]["pants_stripe_px"], u1.PANTS_STRIPE_PX)

    def test_us_flag_follows_its_specification(self):
        flag = u1.us_flag(1900, 1000)
        red, white, blue = ([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
                            for h in (u1.HELMET_BACK["colours"][k] for k in ("red", "white", "blue")))
        stripe = 1000 / 13
        for i in range(13):
            np.testing.assert_allclose(flag[int((i + 0.5) * stripe), 1500, :3], red if i % 2 == 0 else white,
                                       atol=1e-6)
        np.testing.assert_allclose(flag[530, 750, :3], blue, atol=1e-6)        # canton: 0.76 of the hoist wide
        np.testing.assert_allclose(flag[530, 770, :3], red if 530 // stripe % 2 == 0 else white, atol=1e-6)
        stars = 0
        cw, ch = 760.0, 7 * stripe
        for row in range(9):
            for col in range(6 if row % 2 == 0 else 5):
                x = (col * 2 + (1 if row % 2 == 0 else 2)) * cw / 12
                y = (row + 1) * ch / 10
                stars += bool(np.allclose(flag[int(round(y)), int(round(x)), :3], white, atol=1e-6))
        self.assertEqual(stars, 50)


class Repair(unittest.TestCase):
    def manifest(self, tmp: Path, original: bytes, offset: int, replacement: bytes, name="16H0.IFF") -> Path:
        base = tmp / "manifest"
        base.mkdir()
        digest = hashlib.sha256(replacement).hexdigest()
        (base / f"{digest}.span").write_bytes(replacement)
        doc = {"schema": repair.SCHEMA, "resources": {name: [{
            "label": "torso", "offset": offset, "length": len(replacement), "replacement": f"{digest}.span",
            "before_sha256": hashlib.sha256(original[offset:offset + len(replacement)]).hexdigest(),
            "after_sha256": digest}]}}
        path = base / "native_manifest.json"
        path.write_text(json.dumps(doc), encoding="utf-8", newline="\n")
        return path

    def test_manifest_owns_only_the_patriots_kits_and_cards(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.json"
            for resources, ok in (({"16H0.IFF": []}, True), ({"outer:3102": [], "outer:3105": []}, True),
                                  ({"17H0.IFF": []}, False), ({"outer:3741": []}, False), ({}, False)):
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": resources}))
                if ok:
                    self.assertEqual(repair.load_manifest(path)["resources"], resources)
                else:
                    with self.assertRaises(ValueError):
                        repair.load_manifest(path)
            path.write_text(json.dumps({"schema": "other", "resources": {"16H0.IFF": []}}))
            with self.assertRaises(ValueError):
                repair.load_manifest(path)

    def test_loose_repair_is_scoped_idempotent_and_refuses_other_input(self):
        rng = np.random.default_rng(5)
        original = rng.integers(0, 256, 4096, dtype=np.uint8).tobytes()
        replacement = bytes(64)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = self.manifest(tmp, original, 1024, replacement)
            manifest = repair.load_manifest(path)
            (tmp / "in").mkdir()
            (tmp / "in/16H0.IFF").write_bytes(original)
            receipt = repair.repair_resources(tmp / "in", tmp / "out", manifest, path.parent)
            data = (tmp / "out/16H0.IFF").read_bytes()
            self.assertEqual(data[:1024] + data[1088:], original[:1024] + original[1088:])
            self.assertEqual(data[1024:1088], replacement)
            r = receipt["resources"]["16H0.IFF"]
            self.assertTrue(r["outside_scope_identical"])
            self.assertFalse(r["spans"][0]["already_applied"])
            again = repair.repair_resources(tmp / "out", tmp / "again", manifest, path.parent)
            self.assertEqual((tmp / "again/16H0.IFF").read_bytes(), data)
            self.assertTrue(again["resources"]["16H0.IFF"]["spans"][0]["already_applied"])
            tampered = bytearray(original)
            tampered[1030] ^= 0xFF
            (tmp / "bad").mkdir()
            (tmp / "bad/16H0.IFF").write_bytes(bytes(tampered))
            with self.assertRaisesRegex(ValueError, "unexpected input span"):
                repair.repair_resources(tmp / "bad", tmp / "bad_out", manifest, path.parent)
            self.assertFalse((tmp / "bad_out/16H0.IFF").exists())

    def test_loose_mode_does_not_take_card_resources(self):
        original = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = self.manifest(tmp, original, 16, b"\1" * 16, name="outer:3102")
            (tmp / "in").mkdir()
            with self.assertRaisesRegex(ValueError, "kit packages only"):
                repair.repair_resources(tmp / "in", tmp / "out", repair.load_manifest(path), path.parent)


if __name__ == "__main__":
    unittest.main()
