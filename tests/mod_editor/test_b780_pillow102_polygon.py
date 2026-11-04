"""b780: the Unc Bowl pants masks are the same on every Pillow.

The pins of the CIN pants (06H5 chunks 2 and 51) were recorded with Pillow 10.2.0. Pillow 11 fills a sharp corner's tip
differently: with the Studio's own runtime (Pillow 11.3.0, in Windows Setup, the Linux .venv and on Python 3.13) the
broad-stripe mask lost 7 pixels, the compile missed its pins and the repair was left out. The module now fills its
polygons with an exact copy of Pillow 10.2.0's fill.
"""
import hashlib
import inspect
import random
import sys
import unittest
from pathlib import Path

import numpy as np
import PIL
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_unc_bowl_uniforms as unc  # noqa: E402

# sha256 of the two masks as Pillow 10.2.0 draws them (the masks behind the recorded pins)
MAIN_MASK_SHA256 = "3210f3d4dd55548a668c4d69c3cbe70a733bbfcf40372722d8020632e3494e15"
FAR_MASK_SHA256 = "ede7287c982a9fe3805643906b90239a191987630a78c2b087c4c2c9db98270e"


def main_polygons():
    polygons = []
    for row in range(7):
        y = row * 32
        points = [(111, y + 44), (111, y + 23), (174, y + 10), (157, y + 28)]
        polygons.append([(x * 4, yy * 4) for x, yy in points])
        polygons.append([((512 - x) * 4, yy * 4) for x, yy in points])
    return polygons


def far_polygons():
    return [[(42 * 4, (row * 12 + 18) * 4), (42 * 4, (row * 12 + 9) * 4), (68 * 4, (row * 12 + 3) * 4),
             (61 * 4, (row * 12 + 11) * 4)] for row in range(7)]


def pillow_fill(size, polygons):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for points in polygons:
        draw.polygon(points, fill=255)
    return mask


def sha(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


class PolygonMask(unittest.TestCase):
    def test_both_pants_masks_are_the_pinned_pillow_10_2_masks(self):
        self.assertEqual(sha(unc._polygon_mask((2048, 1024), main_polygons())), MAIN_MASK_SHA256)
        self.assertEqual(sha(unc._polygon_mask((1024, 512), far_polygons())), FAR_MASK_SHA256)

    def test_the_mask_is_an_l_image_of_0_and_255(self):
        mask = unc._polygon_mask((1024, 512), far_polygons())
        self.assertEqual((mask.mode, mask.size), ("L", (1024, 512)))
        self.assertEqual(set(np.unique(np.asarray(mask)).tolist()), {0, 255})

    def test_the_pants_compiles_no_longer_draw_with_pillow(self):
        for function in (unc._pants, unc._far_pants):
            source = inspect.getsource(function)
            self.assertNotIn("ImageDraw", source)
            self.assertIn("_polygon_mask(", source)

    @unittest.skipUnless(PIL.__version__ == "10.2.0", "the reference fill is Pillow 10.2.0's own")
    def test_the_fill_equals_pillow_10_2_on_random_polygons(self):
        rng = random.Random(780)
        for _ in range(300):
            size = rng.choice([(64, 48), (200, 120), (333, 211)])
            polygons = [[(rng.randint(-10, size[0] + 10), rng.randint(-10, size[1] + 10))
                         for _ in range(rng.randint(3, 6))] for _ in range(rng.randint(1, 3))]
            self.assertEqual(sha(unc._polygon_mask(size, polygons)), sha(pillow_fill(size, polygons)), polygons)
        self.assertEqual(sha(pillow_fill((2048, 1024), main_polygons())), MAIN_MASK_SHA256)
        self.assertEqual(sha(pillow_fill((1024, 512), far_polygons())), FAR_MASK_SHA256)


if __name__ == "__main__":
    unittest.main()
