"""b81-retail-free-art: the Saints sleeve emblem rule gives the same bytes on every platform.

The rule (mod_editor/core/nfl2k5_kit_rule_emblem.py) renders the mod's own Saints emblem on the sleeve the build holds.
Its reduction is Pillow's BOX resample written out; this file checks that port against Pillow where Pillow is the
authoring version, and pins the rule's output on a synthetic sleeve so a change of arithmetic or summation order on
any platform fails here."""
import hashlib
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_kit_rule_emblem as em  # noqa: E402

PINS = {
    "box_resize": "5fa3330e43eb407c15b3aed326a849067409ddafdb27517dde3140c8ed694757",
    "sleeve": "d88cef5c61f7a289d103d0489602e1f4df9c27cac455c2eb298361e1ddd64cbe",
}


def synthetic_sleeve():
    h, w = 128, 128
    y = np.arange(h)[:, None]
    x = np.arange(w)[None, :]
    a = np.zeros((h, w, 4), np.uint8)
    a[..., 3] = 255
    a[..., :3] = 10
    a[..., 0] = (10 + (x * 3 + y) % 5).astype(np.uint8)
    for top in (8, 72):                                   # a squat old fleur on each half, gold with a light ring
        a[top:top + 26, 48:78, :3] = (217, 193, 145)
        a[top + 2:top + 24, 50:76, :3] = (255, 255, 255)
        a[top + 4:top + 22, 52:74, :3] = (217, 193, 145)
        a[top + 10:top + 14, 60:66, :3] = (10, 10, 10)
    template = np.zeros_like(a)
    template[..., :3] = 10
    template[..., 3] = 255
    template[100:104, 10:30, :3] = 250                    # the template's swoosh, far from the fleur
    return a, template


class EmblemRule(unittest.TestCase):
    def check(self, name, data):
        digest = hashlib.sha256(data).hexdigest()
        if PINS.get(name) is None:
            self.fail("no pin for %s: %s" % (name, digest))
        self.assertEqual(digest, PINS[name], name)

    def test_box_resize_is_pillows_box(self):
        rng = np.arange(57 * 41, dtype=np.float64).reshape(57, 41)
        m = ((rng * 0.6180339887) % 1.0).astype(np.float32)
        outs = []
        for w, h in ((19, 28), (22, 34), (7, 9), (41, 57), (12, 30)):
            ours = em._box_resize(m, w, h)
            outs.append(ours.tobytes())
            try:
                from PIL import Image
                theirs = np.asarray(Image.fromarray(m, "F").resize((w, h), Image.BOX))
                self.assertTrue(np.array_equal(ours, theirs), (w, h))
            except ImportError:
                pass
        self.check("box_resize", b"".join(outs))

    def test_the_rule_on_a_synthetic_sleeve(self):
        a, template = synthetic_sleeve()
        op = dict(op="rule", module="emblem", emblem="nfl2k5_scorebug_assets/logos/no.png", template="24H0:3",
                  halves=[dict(rows=[0, 64], nh=28, nw=19, flip=False), dict(rows=[64, 128], nh=29, nw=18, flip=False)])
        out = em.apply(a, op, a, {"24H0:3": template})
        op["halves"][0]["flip"] = True                     # a facing the colour fit does not choose is refused
        with self.assertRaises(ValueError):
            em.apply(a, op, a, {"24H0:3": template})
        self.assertFalse(np.array_equal(out, a))
        self.check("sleeve", out.tobytes())


if __name__ == "__main__":
    unittest.main()
