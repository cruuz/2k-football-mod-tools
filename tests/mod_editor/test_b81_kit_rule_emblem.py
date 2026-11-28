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


def pillow_box(image, width, height, fused):
    """Pillow's ImagingResampleHorizontal/Vertical_32bpc for mode F with em._coeffs (precompute_coeffs, BOX): each
    output texel is ``ss += pixel * k`` over its taps in double, stored as float32; horizontal pass first. With
    ``fused`` each step is one rounding of ss + pixel * k (a fused multiply-add, computed exactly with Fractions)."""
    from fractions import Fraction

    def run(rows, n_in, n_out):
        out = np.zeros((rows.shape[0], n_out), np.float32)
        for xx, (xmin, k) in enumerate(em._coeffs(n_in, n_out)):
            for r in range(rows.shape[0]):
                ss = 0.0
                for x, kx in enumerate(k):
                    p = float(rows[r, xmin + x])
                    ss = float(Fraction(p) * Fraction(kx) + Fraction(ss)) if fused else ss + p * kx
                out[r, xx] = ss
        return out

    a = np.asarray(image, np.float32)
    if width != a.shape[1]:
        a = run(a, a.shape[1], width)
    if height != a.shape[0]:
        a = run(a.T, a.shape[0], height).T
    return a


class EmblemRule(unittest.TestCase):
    def check(self, name, data):
        digest = hashlib.sha256(data).hexdigest()
        if PINS.get(name) is None:
            self.fail("no pin for %s: %s" % (name, digest))
        self.assertEqual(digest, PINS[name], name)

    def test_box_resize_is_pillows_box(self):
        """Pillow's float resample adds ``pixel * k`` into a double per tap. The authoring Pillow (x86-64, and the
        Windows and Linux wheels) rounds the product and the sum separately; a build compiled with floating-point
        contraction fuses them into one multiply-add (clang's default on arm64: the macOS wheels), which changes the
        last bit of a float32 texel at (7, 9) and (12, 30) here (hosted run 44923189204 failed at (7, 9) on all three
        macOS jobs; a local Pillow 13.0.0 built with clang -mfma -ffp-contract=on fails the same way). So the port is
        checked to the bit against Pillow's loop written out with separate roundings, and the installed Pillow against
        the same loop with the arithmetic its build uses, on every size: a Pillow whose algorithm changed fails on
        every platform, and the pin holds the port's own bytes everywhere."""
        rng = np.arange(57 * 41, dtype=np.float64).reshape(57, 41)
        m = ((rng * 0.6180339887) % 1.0).astype(np.float32)
        try:
            from PIL import Image
        except ImportError:
            Image = None
        outs, separate, fused, tells = [], [], [], False
        for w, h in ((19, 28), (22, 34), (7, 9), (41, 57), (12, 30)):
            ours = em._box_resize(m, w, h)
            outs.append(ours.tobytes())
            plain, fma = pillow_box(m, w, h, fused=False), pillow_box(m, w, h, fused=True)
            self.assertTrue(np.array_equal(ours, plain), (w, h))
            tells = tells or not np.array_equal(plain, fma)
            if Image is not None:
                theirs = np.asarray(Image.fromarray(m, "F").resize((w, h), Image.BOX))
                separate.append(np.array_equal(theirs, plain))
                fused.append(np.array_equal(theirs, fma))
        self.assertTrue(tells, "no size tells separate roundings from a fused multiply-add any more")
        if Image is not None:
            self.assertTrue(all(separate) or all(fused), ("Pillow BOX", separate, fused))
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
