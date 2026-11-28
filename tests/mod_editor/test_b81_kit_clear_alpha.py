"""b81-retail-free-art round 3: the kit fixes' ``clear`` rule may also set the cleared texels' alpha (the uf3 Ravens
helmet rows paint the retail logo's leftovers out in shell black at full reflection alpha). Synthetic and pinned."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_kit_fixes_2026 as kf  # noqa: E402


def texture():
    a = np.zeros((16, 16, 4), np.uint8)
    a[..., 3] = 254
    a[2:5, 3:9, :3] = (198, 160, 40)          # a gold mark
    a[3, 5, :3] = (1, 0, 1)                   # already shell black inside it
    a[10:12, 10:14, :3] = (60, 40, 140)       # purple art outside the box: kept
    a[12, 2, :3] = (198, 160, 40)             # gold outside the box: kept
    return a


class ClearAlphaTests(unittest.TestCase):
    def test_clear_sets_the_alpha_of_the_cleared_texels_only(self):
        op = dict(op="clear", to="#010001", boxes=[[2, 1, 10, 6]], above=8, alpha=255)
        out, hit = kf.clear_marks(texture(), op)
        self.assertEqual(int(hit.sum()), 17)
        self.assertTrue((out[hit][:, :3] == (1, 0, 1)).all() and (out[hit][:, 3] == 255).all())
        self.assertTrue((out[~hit][:, 3] == 254).all())
        self.assertEqual(tuple(out[12, 2, :3]), (198, 160, 40))
        painted, _ = kf.paint(texture(), [op])
        self.assertTrue(np.array_equal(painted, out))
        self.assertEqual(hashlib.sha256(out.tobytes()).hexdigest(),
                         "851ecdb16258179cd78724ef86773eb9be8db7ebfa7d063c98cdbea2cb8a1baf")

    def test_without_alpha_the_clear_keeps_the_alpha(self):
        out, hit = kf.clear_marks(texture(), dict(op="clear", to="#010001", boxes=[[2, 1, 10, 6]], above=8))
        self.assertEqual(int(hit.sum()), 17)
        self.assertTrue((out[..., 3] == 254).all())

    def test_an_alpha_outside_the_byte_is_refused(self):
        with self.assertRaises(ValueError):
            kf.clear_marks(texture(), dict(op="clear", to="#010001", boxes=[[2, 1, 10, 6]], alpha=256))


if __name__ == "__main__":
    unittest.main()
