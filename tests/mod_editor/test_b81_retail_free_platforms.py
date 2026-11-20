"""b81-retail-free-art: the build-time derivations give the same bytes on every platform the Studio runs on.

The 2026 relief base (mod_editor/core/nfl2k5_relief_2026.py: jersey, sleeve and pants base maps from the user's own
disc) and the b81u glyph edit instructions (nfl2k5_glyph_fixes_2026.derive_digit) run on the user's machine, and
their output is checked against pins made on the authoring machine (Linux x86-64, CPython 3.12, numpy 1.26.4). One
rounding difference between platforms, numpy or Python versions would make a build refuse the step. This test runs
the whole derivation on synthetic inputs generated here with integer arithmetic only (no random generator whose
stream could change), at the real sizes and value ranges and with the edge cases (channel values 0 and 255, a
2004-style mesh region the construction lift-out must find, collar opening, island edges, odd picture sizes), and
compares SHA-256 hashes of the results with values pinned on the authoring machine. It needs no game file, so it
runs in the hosted matrix (Linux, Windows, macOS; Python 3.11, 3.12, 3.13 with numpy 1.26.4 or 2.3.5) and under
the Windows installer runtime (packaging/windows/local_windows_ci.py)."""
import hashlib
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_glyph_fixes_2026 as gf  # noqa: E402
from mod_editor.core import nfl2k5_relief_2026 as rl  # noqa: E402

#: pinned on the authoring machine (Linux x86-64, CPython 3.12.3, numpy 1.26.4); see retail-free/REVIEW_ME.md
PINS = {
    "composed_mips": "87c50339f0064a79ca2bf41dcc08d798121f4f805aa9ce0b70fe1b9ef158e6c5",
    "edge_31x33": "9b63684a8e282a9ca4bf1eb04e3e4973de794a7cdd2c460dc50892382d8d475b",
    "edge_32x32": "3ea76b7e7e979e7d1a241037bc06ed54483e86f04d49227f1796d3a40d7c6692",
    "edge_64x64": "d905afed82e2fffad3592ce7fc3d215164079611de1c5cad15a8da7ce87d68dd",
    "embolden_-1_False_31x33": "92e63e15226f817f776c38fa99dbbf3dfb545e2faa2a663ec1f45d71b106a288",
    "embolden_-1_False_32x32": "24d8f3ed91813ff32fe2ad2b7ceea0cb37a5895ebbb343c3971e259fc9421acf",
    "embolden_-1_False_64x64": "e48b055f8fe7fe64cf0bf568ddcab74966445ddb277846c86c3443849959e48a",
    "embolden_0_True_31x33": "1c27e3708c191a3df5e48934a061057a73fbfc35496cbf9fa724829624581bec",
    "embolden_0_True_32x32": "25e5b71490a6c4b514f347e7606d1307084913ba44928daa9bd62a8d3282c9dd",
    "embolden_0_True_64x64": "36436fa8f8d654418d4c40ded39287bac8c3e0ca9651fa1d4574bffb583682e9",
    "embolden_1_False_31x33": "159983e7440367e6e390733d6813deba222d4eadfae22f144add4f418880a1dd",
    "embolden_1_False_32x32": "20fe7453f0b33c096d7bc97670a0ae26a52d7de53ed9655e34f817847ab35500",
    "embolden_1_False_64x64": "64a2e62da6436d9bf0f9d840a476d5b3108075ba745e72e97e107c75abb72143",
    "embolden_2_True_31x33": "3793c95f9382b3e35053776ef5715d84887c31a48703ecc963ecc4a6fd3c42b3",
    "embolden_2_True_32x32": "df5e2ef3433de770fe782d7371b4f5c0c72ee9ab0d0aadf975a689798d3f3e4f",
    "embolden_2_True_64x64": "3eac4c6fa815ad67b7721d256fc17c49551168e3600c5f36a3def2d5c8ad6376",
    "inline_dark_31x33": "71e64e6efb55df426a0820ecb3eb7ac1b4dcf79a34a6e53a62e38b799615515c",
    "inline_dark_32x32": "950043b0cf2f09931b4b2b0a9007c1489584a9456c8410e4ba2028448e6d4e0e",
    "inline_dark_64x64": "d0722f204f59d4038cb5a3a56d595a73ae932fbebea9b111488638e97e759280",
    "inline_fill_31x33": "119114f0f05d6fa21371557a69515f0967f16b6e785fe4cb8445901a7f2aa5c0",
    "inline_fill_32x32": "3a2baa706109b8f332eed3440ac266bf8daf0e4b1032062696b2054590c4bfde",
    "inline_fill_64x64": "3dcd2cacb3a617ded7679961ce78448fb52186e1912c602b95ed163aba547749",
    "jersey_base": "994996c3141dddf98a97386fef5be64532c95427740201f464d55a0cd0853d3f",
    "jersey_base_odd": "d5d2e1ef804b93fab2c686577ea1a46085f8b7b4a78e338a67d5da946459cde4",
    "old_construction": "a4d79abc3160641730becf6441649efac94adedf754dbdd43b9a9c9bade7eabb",
    "paint_31x33": "300481b60fc80b2eddde9c8895937756b98f5c2948e64f92239083b0f913f4a7",
    "paint_32x32": "0777876215f1d47ff7dd0ec6762932eeae46cf4f792b195f5ae4e85ea99c50e8",
    "paint_64x64": "c2b47df1e746ace4839e5c485c90e7e2c5bcf900da1c8e49f68717913c18b8a6",
    "pairwise_mean": "d1e92a813d4c3b78778e3bc9624e60df79f1f87f349444d868bfbeb5c9d3aa60",
    "pants_base": "496a802de9ecac074b9d299d387725f697a89b2fe1eee5425a9e1b8d4d1b9053",
    "recolour_31x33": "c731be63189a8cf08bcc94bd232041aa7c3849b53a7ce5eccf2f5b7a314d77c4",
    "recolour_32x32": "01fb0061347c9f0445cde1310ee975409ae2c940301090185dc88f558f37c5ca",
    "recolour_64x64": "f01ded9ee8469d532003379feeaf3206161c7d757141f434f9f3077a8998bf40",
    "remap_31x33": "4f135c760d02136ef8b3f3d20f6991546d28673a220d20f1056cf96f3267ca50",
    "remap_32x32": "be3a394310ff4543c07a3b15d7d5b8516bbbfff0f0195dfbffebde58239a5b20",
    "remap_64x64": "cfec48e75804cdf11385b72256249833fc6e81e3101822e0f1b39619d8f25df6",
    "sleeve_base": "ad0e97c9c8b84b7416167dfe6a2eeae4d871bec31d29ec471b1427e6d0883851",
}


def sha(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def noise(h, w, salt):
    """Deterministic integers 0..255 from a 32-bit integer hash of (row, column, salt): same on every platform."""
    y = np.arange(h, dtype=np.uint64)[:, None]
    x = np.arange(w, dtype=np.uint64)[None, :]
    v = (y * np.uint64(73856093)) ^ (x * np.uint64(19349663)) ^ np.uint64(salt * 83492791)
    v = (v * np.uint64(2654435761)) & np.uint64(0xFFFFFFFF)
    v ^= v >> np.uint64(15)
    return (v & np.uint64(0xFF)).astype(np.int64)


def normal_map(h, w, salt, mesh=None):
    """A tangent-space normal map like the retail ones: broad folds (integer waves), a little texture noise, an open
    mesh of pits on a diagonal 4-texel lattice inside ``mesh`` (y0, y1, x0, x1), and saturated texels."""
    y = np.arange(h, dtype=np.int64)[:, None]
    x = np.arange(w, dtype=np.int64)[None, :]
    nx = ((x * 7 + y * 3) % 61) - 30 + (noise(h, w, salt) % 9) - 4
    ny = ((y * 5 + x * 2) % 47) - 23 + (noise(h, w, salt + 1) % 9) - 4
    if mesh is not None:
        y0, y1, x0, x1 = mesh
        pit = ((x + y) % 4 == 0) & ((x - y) % 4 == 0)
        ring = (((x + y) % 4 == 2) | ((x - y) % 4 == 2))
        inside = (y >= y0) & (y < y1) & (x >= x0) & (x < x1)
        nx = np.where(inside & pit, 90, np.where(inside & ring, -70, nx))
        ny = np.where(inside & pit, -85, np.where(inside & ring, 75, ny))
    r = np.clip(128 + nx, 0, 255)
    g = np.clip(128 + ny, 0, 255)
    b = np.clip(255 - (np.abs(nx) + np.abs(ny)) // 3, 0, 255)
    out = np.stack([r, g, b, np.full((h, w), 255)], -1).astype(np.uint8)
    out[0, :5] = (0, 0, 0, 255)                   # saturation at both ends of every channel
    out[1, :5] = (255, 255, 255, 255)
    out[2, :5] = (0, 255, 128, 255)
    out[h - 1, w - 5:] = (255, 0, 255, 255)
    return out


def collar(h, w):
    """A V-shaped front opening and a rounded back neck, native texels (like the kits' collar openings)."""
    y = np.arange(h)[:, None]
    x = np.arange(w)[None, :]
    front = (y < 40) & (np.abs(x - 161) < 18 - (y * 18) // 40)
    back = (y < 12) & (np.abs(x - 391) < 26)
    return front | back


def islands(h2, w2):
    """UV-island coverage on the 2x grid: two body islands with a notch, as the jersey layout has."""
    y = np.arange(h2)[:, None]
    x = np.arange(w2)[None, :]
    front = (x >= 20) & (x < w2 // 2 - 30) & (y >= 4) & (y < h2 - 10)
    back = (x >= w2 // 2 + 10) & (x < w2 - 24) & (y >= 4) & (y < h2 - 16)
    notch = (np.abs(x - w2 // 4) < 40) & (y < 60)
    return (front | back) & ~notch


class ReliefDerivation(unittest.TestCase):
    """The three base maps and a composed map, from synthetic retail-like inputs, hash for hash."""

    @classmethod
    def setUpClass(cls):
        cls.gauss = rl.Kernels(rl.relief_b81u()["gauss_kernels"])        # the shipped Gaussian weights

    def test_jersey_base(self):
        retail = normal_map(256, 512, 1, mesh=(60, 160, 40, 200))
        base = rl.jersey_base(self.gauss, retail, collar(256, 512), rl.dilate(islands(512, 1024), 6))
        self.assertEqual(base.shape, (256, 512, 4))
        self.assertCheck("jersey_base", base)

    def test_jersey_base_at_an_odd_size(self):
        retail = normal_map(67, 129, 2, mesh=(10, 60, 5, 120))
        y = np.arange(67)[:, None]
        x = np.arange(129)[None, :]
        opening = (y < 9) & (np.abs(x - 64) < 9 - y)
        island = np.ones((134, 258), bool)
        island[:, :7] = False
        base = rl.jersey_base(self.gauss, retail, opening, island)
        self.assertEqual(base.shape, (67, 129, 4))
        self.assertCheck("jersey_base_odd", base)

    def test_the_mesh_region_is_found_and_lifted(self):
        xy = rl.decode_map(normal_map(256, 512, 1, mesh=(60, 160, 40, 200)))[..., :2]
        old = rl.old_construction(self.gauss, xy)
        self.assertTrue(old[160:280, 120:360].mean() > 0.9)                # the 2x grid: rows 120-320, cols 80-400
        self.assertTrue(old[400:, 600:].mean() < 0.1)
        self.assertCheck("old_construction", np.packbits(old))

    def test_sleeve_base(self):
        self.assertCheck("sleeve_base", rl.sleeve_base(self.gauss, normal_map(128, 128, 3)))

    def test_pants_base(self):
        before = normal_map(256, 512, 4)
        worked = [tuple(b) for b in rl.OLD_PANTS] + [(80, 22, 116, 40), (402, 26, 420, 42)]
        self.assertCheck("pants_base", rl.pants_base(self.gauss, before, worked))

    def test_pairwise_mean(self):
        values = (noise(37, 23, 9).astype(np.float64) - 127.5) / 3.0
        means = [float(rl.pairwise_mean(values.ravel()[:n])).hex() for n in (1, 7, 8, 9, 127, 128, 129, 300, 851)]
        self.assertCheck("pairwise_mean", " ".join(means).encode("ascii"))

    def test_a_composed_map_and_its_mip_chain(self):
        base = normal_map(256, 512, 5)
        difference = np.zeros_like(base)
        difference[..., 3] = 255
        difference[10:20, 10:20, :3] = (1, 255, 254)                       # +1 and -1, -2 modulo 256 (wrap at 0/255)
        difference[0, :5, :3] = (255, 1, 2)
        composed = rl.add_difference(base, difference)
        self.assertTrue(np.array_equal(rl.difference_of(composed, base)[..., :3], difference[..., :3]))
        chain = rl.mip_levels(composed, 6)
        self.assertCheck("composed_mips", b"".join(level.tobytes() for level in chain))

    def assertCheck(self, name, value):
        digest = hashlib.sha256(value if isinstance(value, bytes) else np.ascontiguousarray(value).tobytes()).hexdigest()
        if name not in PINS:
            self.fail("no pin for %s: %s" % (name, digest))
        self.assertEqual(digest, PINS[name], name)


def glyph(h, w, salt):
    """A synthetic numeral: a soft-edged outlined ring with a stem, fill, outline and semi-clear rim texels."""
    y = np.arange(h)[:, None]
    x = np.arange(w)[None, :]
    cy, cx = h // 2, w // 2
    d = (y - cy) * (y - cy) * 4 + (x - cx) * (x - cx) * 9
    ring = (d < (min(h, w) * min(h, w) * 2)) & (d > (min(h, w) * min(h, w) // 2))
    stem = (np.abs(x - cx - w // 6) < 3) & (y > 2) & (y < h - 3)
    shape = ring | stem
    outline = shape & ~rl.erode(shape, 1)
    rim = rl.dilate(shape, 1) & ~shape
    a = np.zeros((h, w, 4), np.uint8)
    a[shape] = (250, 250, 250, 255)
    a[outline] = (20, 20, 20, 255)
    a[rim] = (20, 20, 20, 128)
    a[shape & (noise(h, w, salt) % 17 == 0)] = (240, 236, 228, 255)    # near-fill texels (within the 24/40 windows)
    return a


class GlyphInstructions(unittest.TestCase):
    """Every b81u glyph operation, alone and chained as the derived rows chain them, hash for hash."""

    def run_ops(self, name, a, ops):
        out = gf.derive_digit(a, ops)
        digest = hashlib.sha256(np.ascontiguousarray(out).tobytes()).hexdigest()
        if name not in PINS:
            self.fail("no pin for %s: %s" % (name, digest))
        self.assertEqual(digest, PINS[name], name)
        return out

    def test_each_operation_kind(self):
        for size in ((64, 64), (32, 32), (31, 33)):
            a = glyph(*size, salt=size[1])
            h, w = size
            tag = "%dx%d" % size
            rows = [-1] + list(range(h - 1))
            cols = list(range(w // 2)) + [w // 2] + list(range(w // 2 + 1, w - 1)) + [-1]
            self.run_ops("remap_" + tag, a, [dict(op="remap", rows=rows, cols=cols)])
            for k, extra in ((1, False), (-1, False), (0, True), (2, True)):
                self.run_ops("embolden_%d_%s_%s" % (k, extra, tag), a,
                             [dict(op="embolden", k=k, extra=extra, fill="#FAFAFA", outline="#141414", ring=1),
                              dict(op="remap", rows=list(range(8, 8 + h)), cols=list(range(8, 8 + w)))])
            self.run_ops("edge_" + tag, a, [dict(op="edge", keep=1, edge="#141414", fill="#FAFAFA")])
            self.run_ops("inline_fill_" + tag, a, [dict(op="inline_fill", colour="#D96428", fill="#FAFAFA")])
            self.run_ops("inline_dark_" + tag, a, [dict(op="inline_dark", colour="#D96428")])
            self.run_ops("recolour_" + tag, a, [dict(op="recolour", pairs=[["#141414", "#A5ADB0"], ["#FAFAFA", "#0E2878"]])])
            self.run_ops("paint_" + tag, a, [dict(op="paint", runs=[[0, 0, "00000000FFFFFFFF"], [h - 1, w - 2, "D9642880FF00FF00"]])])


if __name__ == "__main__":
    unittest.main()
