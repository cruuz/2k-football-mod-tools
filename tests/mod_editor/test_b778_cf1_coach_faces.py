"""b778 cf1: scanned coach faces (tools/b77/cf1_face_scan.py) shipped as head.png and a head shape in geometry.json.

The always-on tests read only the repository: every scanned coach has a recipe, a pinned head texture and a pinned
head-shape edit on the model he wears, and the edit keeps the scalp, ears and neck (it moves only the face). The
helper tests check the projection pieces on small synthetic inputs (they need numpy, Pillow, scipy and OpenCV, which
only the art tool uses, and skip without them).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tools" / "b77"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402

RECIPES = ROOT / "tools" / "b77" / "cf1_recipes"
# every coach with a scan recipe (phase 1: JAX, PIT, TB, CLE; Noah 10/22: "Build every single coach a proper face");
# follow-up jobs add recipe files only, never edit this list
SCANNED = tuple(sorted(p.stem for p in RECIPES.glob("*.json")))
PHASE1 = ("JAX", "PIT", "TB", "CLE")


def _have(*names):
    return all(importlib.util.find_spec(n) is not None for n in names)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ShippedScans(unittest.TestCase):
    def setUp(self):
        self.pins = mc.pins()
        self.rows = {r["team"]: r for r in self.pins["teams"]}

    def test_every_recipe_names_a_club_and_its_coach(self):
        files = sorted(RECIPES.glob("*.json"))
        self.assertTrue(set(PHASE1) <= {f.stem for f in files})
        for path in files:
            recipe = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(path.stem, self.rows, path.name)
            self.assertTrue(recipe.get("who"), path.name)
            self.assertIn(recipe.get("mouth", "photo"), ("close", "photo"), path.name)
            for key in ("eyes", "hair_colour", "skin"):
                if key in recipe:
                    self.assertEqual(len(recipe[key]), 3, f"{path.name} {key}")
                    self.assertTrue(all(0 <= int(v) <= 255 for v in recipe[key]), f"{path.name} {key}")

    def test_scanned_heads_and_shapes_are_pinned(self):
        for team in SCANNED:
            row = self.rows[team]
            self.assertEqual(_sha(mc.art_path(team, "head")), row["art"]["head"], team)
            self.assertTrue(row.get("geometry"), f"{team}: no geometry pin")
            self.assertEqual(_sha(mc.geometry_path(team)), row["geometry"], team)

    def test_the_head_shape_moves_the_face_only(self):
        for team in SCANNED:
            doc = json.loads(mc.geometry_path(team).read_text(encoding="utf-8"))
            self.assertEqual(doc["archive"], self.rows[team]["archive"], team)
            heads = [s for s in doc["shapes"] if s["name"] == "coachHeadGrp1"]
            self.assertEqual(len(heads), 1, f"{team}: no head shape edit")
            head = heads[0]
            self.assertGreater(len(head["positions"]), 100, team)
            # a scan never touches every vertex: the scalp, ears and back of the head stay (only Quinn's bald head,
            # not scanned here, moves the scalp)
            self.assertLess(len(head["positions"]), head["vertex_count"], team)

    def test_earlier_faces_are_recognised(self):
        for team in SCANNED:
            row = self.rows[team]
            self.assertTrue(row["superseded_sha256"], team)
            self.assertNotIn(row["applied_sha256"], row["superseded_sha256"], team)


@unittest.skipUnless(_have("numpy", "scipy", "cv2", "PIL"), "the art tool's numpy, scipy, OpenCV and Pillow")
class Helpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        cls.np = np
        spec = importlib.util.spec_from_file_location("cf1_face_scan", ROOT / "tools/b77/cf1_face_scan.py")
        cls.fs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.fs)

    def test_rasterise_keeps_the_nearest_triangle(self):
        np = self.np
        V = np.array([[1, 1], [9, 1], [1, 9], [1, 1], [9, 1], [1, 9]], float)
        depth = np.array([5, 5, 5, 1, 1, 1], float)
        T = np.array([[0, 1, 2], [3, 4, 5]])
        tri, bary, zb = self.fs.rasterise(V, depth, T, 10, 10)
        self.assertEqual(int(tri[2, 2]), 1)
        self.assertAlmostEqual(float(zb[2, 2]), 1.0)
        self.assertAlmostEqual(float(bary[2, 2].sum()), 1.0)
        self.assertEqual(int(tri[9, 9]), -1)

    def test_smooth3d_keeps_a_constant(self):
        np = self.np
        pos = np.stack(np.meshgrid(np.linspace(0, 6, 24), np.linspace(0, 6, 24), [0.0], indexing="ij"), -1)[:, :, 0]
        values = np.full(pos.shape[:2], 7.0)
        mask = np.ones(pos.shape[:2], bool)
        out = self.fs.smooth3d(values, mask, pos, sigma=1.0)
        self.assertTrue(np.allclose(out, 7.0, atol=1e-6))

    def test_mirror_pairs_on_a_symmetric_set(self):
        np = self.np
        L = np.array([[-2, 0, 1], [2, 0, 1], [0, 3, 2], [-1, -1, 0], [1, -1, 0]], float)
        pairs = self.fs.mirror_pairs(L)
        self.assertEqual(pairs.tolist(), [1, 0, 2, 4, 3])

    def test_backdrop_is_not_projected(self):
        np = self.np
        H = W = 200
        photo = np.full((H, W, 3), 180.0)                      # a plain grey studio backdrop
        yy, xx = np.mgrid[0:H, 0:W]
        face = (xx - 100) ** 2 / 50 ** 2 + (yy - 110) ** 2 / 65 ** 2 < 1
        photo[face] = (200, 150, 130)
        t = np.linspace(0, 2 * np.pi, 468, endpoint=False)
        L2 = np.c_[100 + 48 * np.cos(t), 110 + 62 * np.sin(t)]
        L2[10] = (100, 48); L2[152] = (100, 172); L2[33] = (80, 95); L2[263] = (120, 95)
        L2[self.fs.FACE_OVAL] = np.c_[100 + 48 * np.cos(np.linspace(-np.pi / 2, 1.5 * np.pi, len(self.fs.FACE_OVAL),
                                                                   endpoint=False)),
                                      110 + 62 * np.sin(np.linspace(-np.pi / 2, 1.5 * np.pi, len(self.fs.FACE_OVAL),
                                                                    endpoint=False))]
        m = self.fs.photo_face_mask((H, W), L2, photo=photo)
        self.assertGreater(float(m[110, 100]), 0.9)                 # the face
        self.assertLess(float(m[20, 100]), 0.1)                     # backdrop above the head
        self.assertLess(float(m[195, 100]), 0.1)                    # below the jaw (his collar)

    def test_iris_recolour_keeps_the_white_and_pupil(self):
        np = self.np
        rgba = np.zeros((16, 16, 4), np.uint8); rgba[..., 3] = 255
        rgba[..., :3] = 230                                           # sclera
        rgba[5:11, 5:11, :3] = (110, 80, 50)                          # brown iris
        rgba[7:9, 7:9, :3] = 10                                       # pupil
        P = np.array([[0, 0, 14], [1, 0, 14], [0, 1, 14], [5, 5, 0]], float)
        U = np.array([[0, 0], [1, 0], [0, 1], [0.5, 0.5]], float)
        head = dict(P=P, U=U, T=np.array([[0, 1, 2]]), mats=[("headShader1", 1)])
        self.fs.skin_tris = lambda h: (h["T"], np.array([False]))
        out = self.fs.recolour_iris(rgba, head, (90, 130, 170))
        self.assertTrue((out[0, 0, :3] == 230).all())
        self.assertTrue((out[7, 7, :3] == 10).all())
        r, g, b = out[5, 5, :3].astype(int)
        self.assertGreater(b, r)


if __name__ == "__main__":
    unittest.main()
