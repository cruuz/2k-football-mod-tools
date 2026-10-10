"""Beta 77 sh1: the Seahawks' helmet side logos (head toward the rear on both sides, the back wrap joined to them).

Synthetic geometry only (no game data): a two-sided shell UV-mapped like shell C (the player's right, x < 0, in the upper
half of the texture, the left, x > 0, in the lower half, u growing toward the rear on both sides). Covers the position
map, the projection and its facing, the scope and alpha guarantees, the digitized wrap file shipped in ``data/``, the
recipes, the art tool hook, the photo digitizer and the repair (ownership, scope, idempotence, tamper refusal)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sh1 = _load("b77_sh1_helmet_test", "tools/b77/sh1_helmet.py")
repair = _load("b77_sh1_repair_test", "tools/b77/sh1_repair.py")
digitize = _load("b77_sh1_digitize_test", "tools/b77/sh1_digitize_wrap.py")
import nfl2k5_team_2026_art as art  # noqa: E402

SIZE = 256 * sh1.MASTER


def synthetic_geometry(nu: int = 24, nv: int = 20) -> dict:
    """A half-ellipsoid per side (z -3..23 front to back growing u, y 30..58), as quads cut into triangles.

    Right side (x < 0): texture rows 6..122 (upper half); left side (x > 0): rows 134..250. u runs 8..136 px from the
    front (z = 23) to the rear (z = -3) on both sides, like the real shell."""
    pos, uv, tris = [], [], []
    for sign, row0 in ((-1.0, 6.0), (1.0, 134.0)):
        base = len(pos)
        for j in range(nv + 1):
            tv = j / nv                                  # 0 bottom of the side, 1 top
            y = 30.0 + 27.0 * tv
            for i in range(nu + 1):
                tu = i / nu                              # 0 front, 1 rear
                z = 23.0 - 26.0 * tu
                r = 11.0 * math.sqrt(max(0.0, 1.0 - ((y - 42.0) / 16.0) ** 2)) * math.sqrt(max(0.0, 1.0 - ((z - 9.0) / 14.5) ** 2))
                pos.append([sign * (r + 0.5), y, z])
                # the left side is the right side's texture rows reversed (v flipped), as on the real shell
                v = row0 + (116.0 * (1.0 - tv) if sign < 0 else 116.0 * tv)
                uv.append([(8.0 + 128.0 * tu) / 256.0, v / 256.0])
        for j in range(nv):
            for i in range(nu):
                a = base + j * (nu + 1) + i
                b, c, d = a + 1, a + nu + 1, a + nu + 2
                tris += [[a, b, c], [b, d, c]]
    return {"HI_HELMET_C": {"pos": pos, "uv": uv, "tris": tris}}


GEOM = synthetic_geometry()


def asymmetric_mark() -> np.ndarray:
    """Facing right, head at the right end: left 70 % red (the tail), right 30 % blue (the head), a green eye in the head."""
    w, h = 400, 120
    img = np.zeros((h, w, 4), np.float32)
    img[..., 3] = 1.0
    img[:, :280, :3] = (0.9, 0.1, 0.1)
    img[:, 280:, :3] = (0.1, 0.1, 0.9)
    img[40:60, 330:350, :3] = (0.1, 0.9, 0.1)
    return img


def head_minus_tail_z(rgb: np.ndarray, pm: np.ndarray, side_mask: np.ndarray) -> float:
    ok = side_mask & ~np.isnan(pm[..., 2])
    blue = ok & (rgb[..., 2] > 0.6) & (rgb[..., 0] < 0.3) & (rgb[..., 1] < 0.3)
    red = ok & (rgb[..., 0] > 0.6) & (rgb[..., 1] < 0.3) & (rgb[..., 2] < 0.3)
    return float(pm[..., 2][blue].mean() - pm[..., 2][red].mean())


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pm = sh1.posmap(GEOM, SIZE)

    def test_position_map_covers_the_islands_and_interpolates(self):
        pm = self.pm
        ok = ~np.isnan(pm[..., 0])
        self.assertTrue(0.25 < ok.mean() < 0.6)
        sides = sh1.side_masks(pm)
        self.assertTrue((pm[..., 0][sides[sh1.RIGHT]] < 0).all() and (pm[..., 0][sides[sh1.LEFT]] > 0).all())
        # right island sits in the upper half of the texture, left in the lower half
        rows = np.nonzero(sides[sh1.RIGHT].any(1))[0]
        self.assertLess(rows.max(), SIZE // 2)
        rows = np.nonzero(sides[sh1.LEFT].any(1))[0]
        self.assertGreater(rows.min(), SIZE // 2)
        # u grows toward the rear (smaller z) on both sides
        for side in (sh1.RIGHT, sh1.LEFT):
            ys, xs = np.nonzero(sides[side])
            self.assertLess(np.corrcoef(xs, pm[ys, xs, 2])[0, 1], -0.9)

    def test_view_plane_and_normals(self):
        u, w = sh1.view_plane(np.array([[[2.0, 40.0, 5.0]]]), 30.0)
        self.assertAlmostEqual(float(u[0, 0]), -2.0)
        self.assertAlmostEqual(float(w[0, 0]), 40.0 * math.cos(math.radians(30)) + 5.0 * math.sin(math.radians(30)))
        n = sh1.surface_normals(self.pm)
        ok = ~np.isnan(self.pm[..., 0])
        lens = np.linalg.norm(n[ok], axis=1)
        self.assertTrue(np.all((lens > 0.99) | (lens < 1e-6)))
        # the rear of the shell faces back (-z), the side islands face sideways
        rear = ok & (np.nan_to_num(self.pm[..., 2]) < -1.5)
        self.assertLess(float(np.median(n[..., 2][rear])), -0.2)


class Projection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pm = sh1.posmap(GEOM, SIZE)
        cls.sides = sh1.side_masks(cls.pm)
        cls.mark = sh1.prepare_mark(asymmetric_mark(), 400)

    def paint(self, facing, side):
        rgb, alpha = sh1.project_mark(self.mark, self.pm, self.sides[side], (10.0, 44.0), 12.0, 30.0, facing)
        self.assertGreater((alpha > 0.5).sum(), 2000)
        return rgb * (alpha[..., None] > 0.5)

    def test_facing_rear_puts_the_head_behind_the_tail_on_both_sides(self):
        for side in (sh1.RIGHT, sh1.LEFT):
            rgb = self.paint("rear", side)
            self.assertLess(head_minus_tail_z(rgb, self.pm, self.sides[side]), -2.0, side)

    def test_facing_front_is_the_opposite(self):
        for side in (sh1.RIGHT, sh1.LEFT):
            rgb = self.paint("front", side)
            self.assertGreater(head_minus_tail_z(rgb, self.pm, self.sides[side]), 2.0, side)

    def test_both_sides_are_mirror_images_in_space(self):
        a_rgb, a_alpha = sh1.project_mark(self.mark, self.pm, self.sides[sh1.RIGHT], (10.0, 44.0), 12.0, 30.0, "rear")
        b_rgb, b_alpha = sh1.project_mark(self.mark, self.pm, self.sides[sh1.LEFT], (10.0, 44.0), 12.0, 30.0, "rear")

        def stats(alpha):
            ys, xs = np.nonzero(alpha > 0.5)
            return self.pm[ys, xs, 2].mean(), self.pm[ys, xs, 1].mean(), len(ys)

        za, ya, na = stats(a_alpha)
        zb, yb, nb = stats(b_alpha)
        self.assertAlmostEqual(za, zb, delta=0.15)
        self.assertAlmostEqual(ya, yb, delta=0.15)
        self.assertAlmostEqual(na / nb, 1.0, delta=0.05)

    def test_rejects_an_unknown_facing(self):
        with self.assertRaises(ValueError):
            sh1.project_mark(self.mark, self.pm, self.sides[sh1.RIGHT], (10.0, 44.0), 12.0, 30.0, "left")

    def test_the_decal_is_a_true_size_plane_seen_from_the_side(self):
        _, alpha = sh1.project_mark(self.mark, self.pm, self.sides[sh1.RIGHT], (10.0, 44.0), 12.0, 0.0, "rear")
        ys, xs = np.nonzero(alpha > 0.5)
        z, y = self.pm[ys, xs, 2], self.pm[ys, xs, 1]
        self.assertAlmostEqual(float(z.max() - z.min()), 12.0, delta=0.6)
        self.assertAlmostEqual(float(y.max() - y.min()), 12.0 * 120 / 400, delta=0.6)


class Author(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pm = sh1.posmap(GEOM, SIZE)
        cls.mark = sh1.prepare_mark(asymmetric_mark(), 400)
        rng = np.random.default_rng(3)
        base = np.zeros((256, 256, 4), np.uint8)
        base[..., :3] = (12, 40, 72)
        base[..., 3] = 255
        base[..., :3] += rng.integers(0, 3, (256, 256, 1), dtype=np.uint8)
        # an old head-forward logo in each side island (bright), a black vent that must survive
        base[40:90, 30:120, :3] = (240, 240, 240)
        base[160:210, 30:120, :3] = (240, 240, 240)
        base[110:116, 20:30, :3] = (0, 0, 0)
        base[0, :, 3] = 128                              # an alpha pattern that must be kept
        cls.base = base
        cls.layout = {"right": {"box": [20, 30, 140, 110]}, "left": {"box": [20, 150, 140, 215]}}
        cls.placement = {"centre": [10.0, 44.0], "width": 12.0, "angle": 30.0, "facing": "rear"}
        cls.result = sh1.author(base, cls.pm, cls.mark, cls.layout, cls.placement)

    def test_alpha_and_texels_outside_the_scope_are_exact(self):
        r, base = self.result, self.base
        self.assertTrue((r["native"][..., 3] == base[..., 3]).all())
        self.assertTrue((r["native"][~r["scope"]] == base[~r["scope"]]).all())
        self.assertGreater(r["scope_texels"], 1500)

    def test_old_logo_is_gone_and_the_vent_stays(self):
        n = r = self.result["native"]
        self.assertTrue((n[110:116, 20:30, :3] == 0).all())
        luma = n[..., :3].astype(float) @ sh1.LUMA
        # the old logos were 240; whatever remains of them is not a block of 240s
        self.assertLess(int((luma[40:90, 30:120] > 235).sum()), 60)
        self.assertLess(int((luma[160:210, 30:120] > 235).sum()), 60)

    def test_new_logo_faces_the_rear_on_both_sides(self):
        master = self.result["master"][..., :3]
        sides = sh1.side_masks(self.pm)
        # the synthetic mark's head is blue; the shell tint of the base is dark blue (0.05, 0.16, 0.28), so test the
        # saturated blue and red of the mark itself
        for side in (sh1.RIGHT, sh1.LEFT):
            self.assertLess(head_minus_tail_z(master, self.pm, sides[side]), -2.0, side)

    def test_deterministic(self):
        again = sh1.author(self.base, self.pm, self.mark, self.layout, self.placement)
        self.assertTrue((again["native"] == self.result["native"]).all())

    def test_wrap_joins_the_back_and_leaves_the_rest(self):
        wrap = sh1.load_wrap(ROOT / "data/nfl2k5_helmet_wraps/sea_wrap.png")
        r = sh1.author(self.base, self.pm, self.mark, self.layout, self.placement, wrap=wrap)
        self.assertTrue((r["native"][..., 3] == self.base[..., 3]).all())
        self.assertTrue((r["native"][~r["scope"]] == self.base[~r["scope"]]).all())
        self.assertGreaterEqual(r["scope_texels"], self.result["scope_texels"])


class MirrorLeft(unittest.TestCase):
    def test_left_takes_the_right_side_at_the_mirrored_point_inside_the_box_only(self):
        pm = sh1.posmap(GEOM, SIZE)
        sides = sh1.side_masks(pm)
        rng = np.random.default_rng(11)
        master = rng.random((SIZE, SIZE, 4)).astype(np.float32)
        before = master.copy()
        box = [20, 132, 120, 225]
        written = sh1.mirror_left(master, pm, box)
        self.assertGreater(int(written.sum()), 20000)
        self.assertTrue((written & ~sides[sh1.LEFT]).sum() == 0)
        # outside the box and the alpha channel nothing moves
        self.assertTrue((master[~written] == before[~written]).all())
        self.assertTrue((master[..., 3] == before[..., 3]).all())
        # a written left texel equals a right texel at (almost) the same height and depth
        ys, xs = np.nonzero(written)
        pick = np.random.default_rng(2).choice(len(ys), 200, replace=False)
        ry, rx = np.nonzero(sides[sh1.RIGHT])
        for i in pick:
            yz = pm[ys[i], xs[i]][[1, 2]]
            d = np.hypot(pm[ry, rx, 1] - yz[0], pm[ry, rx, 2] - yz[1])
            k = int(np.argmin(d))
            self.assertLess(d[k], 0.25)
            self.assertTrue(np.allclose(master[ys[i], xs[i], :3], before[ry[k], rx[k], :3]))

    def test_a_left_logo_that_faced_the_rear_now_faces_like_the_right(self):
        pm = sh1.posmap(GEOM, SIZE)
        sides = sh1.side_masks(pm)
        mark = sh1.prepare_mark(asymmetric_mark(), 400)
        master = np.zeros((SIZE, SIZE, 4), np.float32)
        master[..., :3] = (0.05, 0.16, 0.28)
        master[..., 3] = 1
        for side, facing in ((sh1.RIGHT, "front"), (sh1.LEFT, "rear")):      # the same-image convention
            rgb, alpha = sh1.project_mark(mark, pm, sides[side], (10.0, 44.0), 12.0, 30.0, facing)
            a = alpha[..., None]
            master[..., :3] = master[..., :3] * (1 - a) + rgb * a
        self.assertGreater(head_minus_tail_z(master[..., :3], pm, sides[sh1.RIGHT]), 2.0)
        self.assertGreater(-head_minus_tail_z(master[..., :3], pm, sides[sh1.LEFT]), 2.0)
        sh1.mirror_left(master, pm, [0, 128, 256, 256])
        for side in (sh1.RIGHT, sh1.LEFT):
            self.assertGreater(head_minus_tail_z(master[..., :3], pm, sides[side]), 2.0, side)


class DecalFacing(unittest.TestCase):
    def test_flip_rule(self):
        self.assertFalse(art.decal_flip("image"))
        self.assertTrue(art.decal_flip("front", "right"))      # a right-facing mark needs flipping to put its head at the front
        self.assertFalse(art.decal_flip("front", "left"))
        self.assertFalse(art.decal_flip("rear", "right"))
        self.assertTrue(art.decal_flip("rear", "left"))

    def test_front_puts_the_head_at_the_texture_left_in_both_decals(self):
        mark = Image.fromarray(_u8(asymmetric_mark()), "RGBA")            # head (blue) at the right end
        for name, vflip in (("lower", False), ("upper", True)):
            canvas = np.zeros((300, 300, 4), np.float32)
            canvas[..., 3] = 1
            art._place_logo(canvas, mark, (150, 150), 200, 60, rotate=False, flip_h=art.decal_flip("front"), flip_v=vflip)
            blue = (canvas[..., 2] > 0.6) & (canvas[..., 0] < 0.3)
            red = (canvas[..., 0] > 0.6) & (canvas[..., 2] < 0.3)
            xb, xr = np.nonzero(blue)[1].mean(), np.nonzero(red)[1].mean()
            self.assertLess(xb, xr, name)
        # the old convention: the lower decal keeps the head at the right, the upper (turned 180) at the left
        for name, rot, expect_left in (("lower", False, False), ("upper", True, True)):
            canvas = np.zeros((300, 300, 4), np.float32)
            canvas[..., 3] = 1
            art._place_logo(canvas, mark, (150, 150), 200, 60, rotate=rot)
            blue = (canvas[..., 2] > 0.6) & (canvas[..., 0] < 0.3)
            red = (canvas[..., 0] > 0.6) & (canvas[..., 2] < 0.3)
            self.assertEqual(np.nonzero(blue)[1].mean() < np.nonzero(red)[1].mean(), expect_left, name)

    def test_the_two_alternates_ask_for_the_front(self):
        for rel, key in (("nfl2k5_uniform_alternates_2026_u3d.json", "NE:9"), ("nfl2k5_uniform_alternates_2026.json", "ARI:7")):
            doc = json.loads((ROOT / "data" / rel).read_text(encoding="utf-8"))["alternates"]
            rec = doc[key] if isinstance(doc, dict) else [x for x in doc if x["key"] == key][0]
            for side in ("H", "A"):
                kit = rec["spec"]["kits"][side]
                helmet = kit["helmet"] if "helmet" in kit else kit["merge"]["helmet"]
                self.assertEqual(helmet["decal"]["facing"], "front", (key, side))


class WrapFile(unittest.TestCase):
    def test_the_shipped_mask_loads_and_is_symmetric(self):
        wrap = sh1.load_wrap(ROOT / "data/nfl2k5_helmet_wraps/sea_wrap.png")
        m = wrap["mask"]
        self.assertEqual(set(np.unique(m)) - {0, 1, 2}, set())
        white, grey = int((m == 1).sum()), int((m == 2).sum())
        self.assertTrue(8000 < white < 30000 and 12000 < grey < 60000, (white, grey))
        # the design is symmetric about u = 0: the mask and its mirror agree
        cols = m.shape[1]
        self.assertAlmostEqual(-wrap["u0"] / wrap["res"], cols / 2.0, delta=1.0)
        fg = m > 0
        flip = fg[:, ::-1]
        iou = (fg & flip).sum() / float((fg | flip).sum())
        self.assertGreater(iou, 0.99)

    def test_rejects_other_files(self):
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "x.png"
            Image.fromarray(np.full((8, 8), 7, np.uint8), "L").save(png)
            (Path(td) / "x.json").write_text(json.dumps({"schema": "nope"}))
            with self.assertRaises(ValueError):
                sh1.load_wrap(png)

    def test_digitizer_classifies_a_synthetic_back_photo(self):
        # a 1200 px photo: navy helmet silhouette, one white V line, a grey band under it
        n = 1200
        img = np.zeros((n, n, 4), np.uint8)
        img[300:1000, 150:1050] = (12, 40, 72, 255)
        for x in range(160, 1040):
            y = int(500 + abs(x - 600) * -0.5 + 300)
            img[y - 8:y + 8, x] = (250, 250, 250, 255)              # white line (a V)
        img[760:900, 200:1000] = (165, 172, 175, 255)                  # grey band
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "p.png"
            Image.fromarray(img, "RGBA").save(path)
            white, inside = digitize.classify(path)
        self.assertGreater(int(white.sum()), 5000)
        self.assertFalse(white[800, 600] and not inside[800, 600])


class Recipes(unittest.TestCase):
    DATA = ROOT / "data"

    def helmet(self, rel, side):
        return json.loads((self.DATA / rel).read_text(encoding="utf-8"))["kits"][side]["helmet"]

    def test_every_seahawks_recipe_uses_the_uni_atlas_measurements(self):
        for rel in ("nfl2k5_teams_2026/SEA.json", "nfl2k5_uniform_alt_specs_2026/SEA_3.json",
                    "nfl2k5_uniform_alt_specs_2026/SEA_4.json"):
            for side in ("home", "away"):
                h = self.helmet(rel, side)
                self.assertNotIn("side_logo", h)
                p = h["atlas_decal"]["placements"]
                self.assertEqual(p["upper"]["flip"], [-1, -1])
                self.assertEqual(p["lower"]["flip"], [-1, 1])
                for colour in ("green", "grey"):
                    self.assertFalse([d for d in h.get("decorations", []) if d.get("colour") == colour and "rect" in d
                                      and d["rect"][0] in (154, 155.5)], rel)

    def test_kit_table_matches_the_slot_plan(self):
        self.assertEqual(set(sh1.SEA_KITS), {"26H0", "26A0", "26H3", "26A3", "26H4", "26A4"})
        self.assertEqual(sh1.SEA_KITS["26H4"]["same_as"], "26H0")
        self.assertEqual(sh1.SEA_KITS["26A4"]["same_as"], "26A0")
        self.assertFalse(sh1.SEA_KITS["26H3"]["wrap"])


class ArtToolHook(unittest.TestCase):
    def test_author_helmet_uses_atlas_placement_without_geometry(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            spec = art.Spec(ROOT / "data/nfl2k5_teams_2026/SEA.json")
            retail = tmp / "retail" / "26H0"
            retail.mkdir(parents=True)
            base = np.zeros((256, 256, 4), np.uint8)
            base[..., :3] = (34, 83, 127)
            base[..., 3] = 255
            Image.fromarray(base, "RGBA").save(retail / "helmet_helmet02.png")
            marks = tmp / "marks"
            marks.mkdir()
            Image.fromarray(_u8(asymmetric_mark()), "RGBA").save(marks / "club_logo_full.png")
            art.use_helmet_geometry(None)
            out = art.author_helmet(spec, spec.data["kits"]["home"], tmp / "retail", "helmet02", marks)
            # The right-facing mark's blue head must land at smaller U on both islands.
            for lo, hi in ((30, 120), (136, 226)):
                rgb = out[lo*4:hi*4, 25*4:158*4, :3]
                yy, xx = np.indices(rgb.shape[:2])
                blue = (rgb[..., 2] > .7) & (rgb[..., 0] < .3)
                red = (rgb[..., 0] > .7) & (rgb[..., 2] < .3)
                self.assertLess(xx[blue].mean(), xx[red].mean())
            self.assertTrue(np.all(out[..., 3] == 1))


def _u8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


class RenderTool(unittest.TestCase):
    def test_shell_option_picks_the_texture_family_of_the_game_routes(self):
        render = _load("b77_u1_render_kit_test", "tools/b77/u1_render_kit.py")
        with tempfile.TemporaryDirectory() as td:
            c = render.item_for("X", "/art", "000000", 12, Path(td), "none", "C")
            a = render.item_for("X", "/art", "000000", 12, Path(td), "none", "A")
        self.assertEqual(c["shell"], "C")
        self.assertEqual(a["shell"], "A")
        # roster helmet 1 (Revolution, shell C) wears helmet02; helmet 0 (Standard, shell A) wears helmet00
        for name in ("HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C"):
            self.assertTrue(c["tex"][name].endswith("helmet_helmet02.png"), name)
        for name in ("HI_HELMET_A", "HELMET_A_accessories", "LOGO_helmet"):
            self.assertTrue(a["tex"][name].endswith("helmet_helmet00.png"), name)
        self.assertIn("NUMBER_helmet_C_L", c["tex"])
        self.assertIn("NUMBER_helmet_A_L", a["tex"])
        self.assertNotIn("NUMBER_helmet_A*", a["hide"])


class Repair(unittest.TestCase):
    def manifest(self, base: Path, original: bytes, offset: int, replacement: bytes, name: str) -> Path:
        digest = hashlib.sha256(replacement).hexdigest()
        (base / f"{digest}.span").write_bytes(replacement)
        doc = {"schema": repair.SCHEMA, "resources": {name: [{
            "label": "helmet02", "offset": offset, "length": len(replacement), "replacement": f"{digest}.span",
            "before_sha256": hashlib.sha256(original[offset:offset + len(replacement)]).hexdigest(),
            "after_sha256": digest}]}}
        path = base / "native_manifest.json"
        path.write_text(json.dumps(doc), encoding="utf-8", newline="\n")
        return path

    def test_manifest_owns_only_the_seahawks_kits_and_the_card_packs(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.json"
            for name in ("26H0.IFF", "26A0.IFF", "26H3.IFF", "26A3.IFF", "26H4.IFF", "26A4.IFF", "00H7.IFF", "00A7.IFF",
                         "16H9.IFF", "16A9.IFF", "outer:3102", "outer:3105"):
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                self.assertIn(name, repair.load_manifest(path)["resources"])
            for name in ("26H1.IFF", "26A2.IFF", "22H0.IFF", "16H0.IFF", "26H5.IFF", "outer:3741", "26H0.IFFX", "00H0.IFF",
                         "00H6.IFF", "16H4.IFF", "16H90.IFF"):
                path.write_text(json.dumps({"schema": repair.SCHEMA, "resources": {name: []}}))
                with self.assertRaises(ValueError):
                    repair.load_manifest(path)
            path.write_text(json.dumps({"schema": "b77/u2d/texture-repair/v1", "resources": {"26H0.IFF": []}}))
            with self.assertRaises(ValueError):
                repair.load_manifest(path)

    def test_loose_repair_is_scoped_idempotent_and_refuses_other_input(self):
        original = np.random.default_rng(9).integers(0, 256, 8192, dtype=np.uint8).tobytes()
        replacement = bytes(range(64)) * 4
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td).resolve()
            path = self.manifest(tmp, original, 2048, replacement, "26H0.IFF")
            manifest = repair.load_manifest(path)
            (tmp / "in").mkdir()
            (tmp / "in/26H0.IFF").write_bytes(original)
            receipt = repair.repair_resources(tmp / "in", tmp / "out", manifest, path.parent)
            data = (tmp / "out/26H0.IFF").read_bytes()
            self.assertEqual(data[:2048] + data[2048 + 256:], original[:2048] + original[2048 + 256:])
            self.assertEqual(data[2048:2048 + 256], replacement)
            self.assertTrue(receipt["resources"]["26H0.IFF"]["outside_scope_identical"])
            again = repair.repair_resources(tmp / "out", tmp / "again", manifest, path.parent)
            self.assertEqual((tmp / "again/26H0.IFF").read_bytes(), data)
            self.assertTrue(again["resources"]["26H0.IFF"]["spans"][0]["already_applied"])
            tampered = bytearray(original)
            tampered[2100] ^= 0xFF
            (tmp / "bad").mkdir()
            (tmp / "bad/26H0.IFF").write_bytes(bytes(tampered))
            with self.assertRaisesRegex(ValueError, "unexpected input span"):
                repair.repair_resources(tmp / "bad", tmp / "bad_out", manifest, path.parent)

    def test_loose_mode_does_not_take_card_resources(self):
        original = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td).resolve()
            path = self.manifest(tmp, original, 16, b"\1" * 16, "outer:3105")
            (tmp / "in").mkdir()
            with self.assertRaisesRegex(ValueError, "kit packages only"):
                repair.repair_resources(tmp / "in", tmp / "out", repair.load_manifest(path), path.parent)


if __name__ == "__main__":
    unittest.main()
