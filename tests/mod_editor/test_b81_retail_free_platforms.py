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
    "clear_rgb_31x33": "9e7d7b9c75213972f86141a8fc036eee6ffe1fda36c0f04ee3b0e735ebbf1274",
    "clear_rgb_32x32": "7a5edc907766b988225fd6043df5f1d62fc30f4722d524713b34b5ee6c8a58f4",
    "clear_rgb_64x64": "15980bed239226ee8b58116ce51d6a8b44445df44a34357b731ab34481fecbb4",
    "collar_opening": "d52d11ff9a2d5addbbcb87d4515bfc40063e3cd06439b57a1f0980cfbadd4615",
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
    "far_compose": "60a11e128bbca9da8ace186fb550806a0d5d1c309aa81d4498a1846a1e94a108",
    "far_compose_mips": "c216acee9a9f5f3c8ff8b2c4afcebcfa2e2e6eec350e03e2a2792c289e97c7e5",
    "far_compose_palette": "312e8a6c3d267f6f8a828a6d51e23508826d98dabf75a0c268a42ca76e0cbe58",
    "gauss_1.6": "2d49df4d46064df6076574cc24383e073e22fd81029c4d64dc6865bc1b720103",
    "gauss_10.0": "7566dfcc24ae03a802d04ed00c05092cf288fc3d8d646a4581ea18898173d1e7",
    "gauss_3.0": "faa5d937b558a8e001ba212a93fbf2f092b9586a0507d45ada73fd358fde3c70",
    "gauss_3.2": "0c73df3ee548908d678d547244ee7cd4ca004dbbeb06ad9baec08e342848b9af",
    "gauss_3.6": "e82fc0618c7749800aa475589cc8dcb61d9791782c734289ec8a5e4e5926bea1",
    "gauss_4.0": "db0c4ff101c8279201a567ce2ed5dfd4aed1d5b5fce045f506d8bd670143d9e3",
    "gauss_4.6": "eb0a007e9a83f6976378b0e4a2cab339776fa1ce6395dbdac6501bace42a4954",
    "gauss_6.0": "3eb0b9c48179972ba1c9c7075fea7d08705290105eab739b90c43899190a432e",
    "gauss_9.0": "481251e46681e64efdf7ed7c7b9beaffadd386f1aca872be25381083958fe931",
    "inline_dark_31x33": "71e64e6efb55df426a0820ecb3eb7ac1b4dcf79a34a6e53a62e38b799615515c",
    "inline_dark_32x32": "950043b0cf2f09931b4b2b0a9007c1489584a9456c8410e4ba2028448e6d4e0e",
    "inline_dark_64x64": "d0722f204f59d4038cb5a3a56d595a73ae932fbebea9b111488638e97e759280",
    "inline_fill_31x33": "119114f0f05d6fa21371557a69515f0967f16b6e785fe4cb8445901a7f2aa5c0",
    "inline_fill_32x32": "3a2baa706109b8f332eed3440ac266bf8daf0e4b1032062696b2054590c4bfde",
    "inline_fill_64x64": "3dcd2cacb3a617ded7679961ce78448fb52186e1912c602b95ed163aba547749",
    "jersey_base": "994996c3141dddf98a97386fef5be64532c95427740201f464d55a0cd0853d3f",
    "jersey_base_odd": "d5d2e1ef804b93fab2c686577ea1a46085f8b7b4a78e338a67d5da946459cde4",
    "jersey_folds": "b8a925e688d4582ff03bca23e67e78fbc37204ae470e4eb633733b6387f4e846",
    "kit_clear": "83363279a89b09b3803da9476b5160fb440a7725e6cde9ff69177901d03c1443",
    "old_construction": "a4d79abc3160641730becf6441649efac94adedf754dbdd43b9a9c9bade7eabb",
    "paint_31x33": "300481b60fc80b2eddde9c8895937756b98f5c2948e64f92239083b0f913f4a7",
    "paint_32x32": "0777876215f1d47ff7dd0ec6762932eeae46cf4f792b195f5ae4e85ea99c50e8",
    "paint_64x64": "c2b47df1e746ace4839e5c485c90e7e2c5bcf900da1c8e49f68717913c18b8a6",
    "pairwise_mean": "d1e92a813d4c3b78778e3bc9624e60df79f1f87f349444d868bfbeb5c9d3aa60",
    "pants_base": "496a802de9ecac074b9d299d387725f697a89b2fe1eee5425a9e1b8d4d1b9053",
    "pants_lifted": "f81f67906ca704c2e8e60880ae5b87f7ad1b8c5cf5cae7122b8856d5234615e2",
    "raster_islands": "4e29ccc4365161d7e1f5ac2349f215d1104ad006d5d28a894c4f9e9580d827d8",
    "raster_islands_dilated": "b48d0735a4e1baf76417be0418c293afceb1f8c7f2f98a49ab06fa26ecf9a0b8",
    "recolour_31x33": "c731be63189a8cf08bcc94bd232041aa7c3849b53a7ce5eccf2f5b7a314d77c4",
    "recolour_32x32": "01fb0061347c9f0445cde1310ee975409ae2c940301090185dc88f558f37c5ca",
    "recolour_64x64": "f01ded9ee8469d532003379feeaf3206161c7d757141f434f9f3077a8998bf40",
    "recolour_hidden_31x33": "73887e3de01d8797f5122c78306b2ebcc7d285944c2c2999852745147892907a",
    "recolour_hidden_32x32": "8560d9601a2df4279993327848df2d09a6887730f51b3d01999854c0a764df3c",
    "recolour_hidden_64x64": "1b7af4a7a5a2e6f2e934674ea08ddac530a81b7ed2b633baaffe64c9a435e5f2",
    "remap_31x33": "4f135c760d02136ef8b3f3d20f6991546d28673a220d20f1056cf96f3267ca50",
    "remap_32x32": "be3a394310ff4543c07a3b15d7d5b8516bbbfff0f0195dfbffebde58239a5b20",
    "remap_64x64": "cfec48e75804cdf11385b72256249833fc6e81e3101822e0f1b39619d8f25df6",
    "sleeve_base": "ad0e97c9c8b84b7416167dfe6a2eeae4d871bec31d29ec471b1427e6d0883851",
    "sleeve_folds": "44464e37c5fe13e95f5f295a63c5491790d0eeb8b4a10b83c71a8063a6fd46e5",
    "slopes": "c3da6eb49aa5cf1f7faee20e9dba748651344a16c5a92a1a628f7b86bf38b627",
    "thin_letters_2_2": "7129b34b02079c016c8cc955c3ab9bd282ae1941c90aef2c94b43c3eb3d2a67b",
    "thin_letters_3_3": "e22191b39a4510020811b7ed696f1c788c8a210331cdee792f7eecf33570b62f",
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

    def test_the_float_stages_bit_for_bit(self):
        """Review F6: the uint8 maps hide most last-bit float differences (rounding absorbs them), so the float64
        stages are pinned themselves: every Gaussian, the slopes, the folds before reduction, the membrane fill. A
        changed summation order or a fused multiply-add on any platform changes these hashes."""
        field = (noise(96, 160, 11).astype(np.float64) - 127.5) / 97.0 + (noise(96, 160, 12).astype(np.float64) / 1e5)
        for sigma in rl.SIGMAS:
            self.assertCheck("gauss_%r" % float(sigma), self.gauss(field, sigma))
        retail = normal_map(256, 512, 1, mesh=(60, 160, 40, 200))
        self.assertCheck("slopes", rl.slopes(rl.decode_map(retail)[..., :2]))
        self.assertCheck("jersey_folds", rl.jersey_folds(self.gauss, retail, collar(256, 512), rl.dilate(islands(512, 1024), 6)))
        self.assertCheck("sleeve_folds", rl.sleeve_folds(self.gauss, normal_map(128, 128, 3)))
        self.assertCheck("pants_lifted", rl.pants_lifted(self.gauss, normal_map(256, 512, 4)))

    def test_island_rasteriser(self):
        """Review F1: the UV coverage rule the build applies to the game mesh, on triangles that share edges and
        vertices, and vertices placed exactly on texel centres and on texel corners."""
        w, h = 64, 32
        uv = np.array([[2.5, 1.5], [30.5, 1.5], [30.5, 29.5], [2.5, 29.5], [16.0, 16.0], [61.0, 3.0], [40.0, 30.0],
                       [33.0, 2.0], [47.25, 17.75]], np.float64) / np.array([float(w), float(h)])
        uv = np.frombuffer(np.asarray(uv, "<f4").tobytes(), "<f4").reshape(-1, 2).astype(np.float64)   # as the export
        tris = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [5, 6, 7], [5, 8, 6], [0, 0, 1]], np.int64)
        mask = rl.raster_islands(uv, tris, w, h)
        self.assertTrue(mask[16, 16] and mask[2, 3] and not mask[31, 63])
        self.assertCheck("raster_islands", np.packbits(mask).tobytes())
        self.assertCheck("raster_islands_dilated", np.packbits(rl.dilate(mask, 6)).tobytes())

    def test_collar_opening(self):
        """Review F2: the opening the build reads from a kit's torso texture (seeded flood fill, integers only)."""
        torso = np.zeros((256, 512, 4), np.uint8)
        torso[..., :3] = 40
        torso[..., 3] = 255
        torso[collar(256, 512)] = (220, 220, 220, 255)
        torso[10:12, 150:170] = (226, 221, 219, 255)               # within 14 levels: part of the opening
        torso[30:33, 155:160] = (240, 200, 200, 255)               # not within 14: a notch
        self.assertCheck("collar_opening", np.packbits(rl.collar_opening(torso)).tobytes())

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

    def test_thin_letters(self):
        """Review F3: the Jaguars strip rule on a synthetic strip: 29 glyph cells of letter-like shapes."""
        strip = np.zeros((32, 1024, 4), np.uint8)
        strip[..., :3] = (200, 30, 30)
        offsets = [32 * (i + 1) for i in range(29)]
        for i, x0 in enumerate(offsets):
            w = 9 + (i % 7)
            strip[4:28, x0 + (i % 2):x0 + (i % 2) + w, 3] = 255
            strip[10:12, x0 + 3:x0 + w - 2, 3] = 0                  # a counter slit
            strip[4:6, x0:x0 + 2, 3] = 140 if i % 3 else 90          # soft corners (alpha 128 is the ink line)
        weights = {"W": ["0x1.8p+1", "0x1.4p+1", "0x1.4p+1"], "M": ["0x1.8p+1", "0x1.2p+1", "0x1.2p+1"],
                   "N": ["0x1.4p+1", "0x1.6p+1"], "K": ["0x1.4p+1", "0x1.4p+1", "0x1.2p+1", "0x1.1p+1"],
                   "X": ["0x1.4p+1", "0x1.4p+1", "0x1.4p+1"], "Y": ["0x1.4p+1", "0x1.4p+1", "0x1.4p+1"],
                   "Z": ["0x1.4p+1", "0x1.4p+1"]}
        for stem, bar in ((2, 2), (3, 3)):
            op = dict(op="thin_letters", stem=stem, bar=bar, top=4, cap=24, fill="#101010", offsets=offsets,
                      weights=weights)
            self.run_ops("thin_letters_%d_%d" % (stem, bar), strip, [op])

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
            self.run_ops("recolour_hidden_" + tag, a, [dict(op="recolour", pairs=[["#141414", "#A5ADB0"]], hidden=True)])
            self.run_ops("clear_rgb_" + tag, a, [dict(op="clear_rgb", colour="#102030")])

    def test_kit_clear_marks(self):
        """The kit-fix ``clear`` (an old mark removed by rule): integer distances and a 4-neighbour grow."""
        from mod_editor.core import nfl2k5_kit_fixes_2026 as kf
        h, w = 64, 128
        tex = np.zeros((h, w, 4), np.uint8)
        tex[...] = (250, 250, 250, 255)
        tex[..., :3] = np.clip(250 - (noise(h, w, 7) % 9), 0, 255).astype(np.uint8)[..., None]
        tex[10:30, 20:26, :3] = (0, 0, 0)                      # a dark mark
        tex[9, 20:26, :3] = (230, 230, 230)                    # its soft edge (within 20 of the field)
        tex[40:50, 60:100, :3] = (251, 79, 20)                 # another mark, kept by ``keep``
        op = dict(op="clear", to="#FAFAFA", boxes=[[16, 4, 40, 36], [56, 36, 104, 56]], keep=[[58, 38, 102, 52]],
                  above=20, grow=1)
        out, hit = kf.clear_marks(tex, op)
        self.assertTrue((out[10:30, 20:26, :3] == 250).all() and (out[40:50, 60:100, :3] == (251, 79, 20)).all())
        digest = hashlib.sha256(out.tobytes() + np.packbits(hit).tobytes()).hexdigest()
        if "kit_clear" not in PINS:
            self.fail("no pin for kit_clear: %s" % digest)
        self.assertEqual(digest, PINS["kit_clear"], "kit_clear")


def far_atlas(salt):
    """A synthetic far-player atlas (the 256 x 128 splayer): a light fabric with integer fold waves and palette-like
    noise, a stripe down the pants island, a mark on the sleeve island, a dark helmet side and saturated texels."""
    h, w = 128, 256
    y = np.arange(h, dtype=np.int64)[:, None]
    x = np.arange(w, dtype=np.int64)[None, :]
    fold = ((x * 5 + y * 3) % 37) - 18 + (noise(h, w, salt) % 5) - 2
    a = np.zeros((h, w, 4), np.int64)
    a[..., 0] = 222 + fold
    a[..., 1] = 218 + fold
    a[..., 2] = 210 + fold
    a[..., 3] = 255
    a[0:90, 46:66, :3] = (120, 30, 30)                       # the pants stripe the uniform pass changed
    a[104:116, 200:212, :3] = (40, 40, 160)                  # a sleeve mark
    a[91:128, 38:126, :3] = (30, 30, 34)                     # the helmet side
    a[0, :4] = (0, 0, 0, 255)
    a[1, :4] = (255, 255, 255, 255)
    return np.clip(a, 0, 255).astype(np.uint8)


def field_texture(h, w, colour, salt, stripes=()):
    """A finished field texture: one kit colour with a little noise, stripe bands and a shield-like block."""
    t = np.zeros((h, w, 4), np.int64)
    t[..., :3] = np.asarray(colour, np.int64) + ((noise(h, w, salt) % 7) - 3)[..., None]
    t[..., 3] = 255
    for x0, x1, c in stripes:
        t[:, x0:x1, :3] = c
    t[h // 6:h // 6 + 12, w // 5:w // 5 + 14, :3] = (250, 250, 250)
    return np.clip(t, 0, 255).astype(np.uint8)


class FarPlayerAtlasCompose(unittest.TestCase):
    """R2-G (art director, rule 4 of retail-free/REVIEW_ME.md section 8): the far-player atlas step
    (``sideline_2026_b81u``, data/nfl2k5_sideline_2026_b81u.json) composes pants and sleeve pieces at build time with
    the shipped sideline compose: area reduction of the field texture's crop, fold lighting from the island, settle,
    the integer mip chain and the integer palette fit. One pants rule with the R54 crop and one sleeve rule, from
    synthetic inputs, hash for hash. The compose itself is the shipped b779/b780 code and uses float32 arithmetic and
    Pillow's BOX resampling (not rule 4's integer or ordered-IEEE form); a platform where these pins differ would see
    that step leave the atlas as it is (``after_differs``), never a wrong span."""

    def test_a_pants_rule_with_its_crop_and_a_sleeve_rule(self):
        from mod_editor.core import nfl2k5_kit_fixes_2026 as kf
        import nfl_tset_png_import as palette_tools
        atlas = far_atlas(21)
        orange = (233, 92, 30)                                  # the pants stripe bands sit where the shipped mask expects
        textures = {"pants": field_texture(256, 512, (20, 34, 88), 22, ((130, 155, orange), (357, 382, orange))),
                    "sleeve": field_texture(128, 128, (228, 92, 28), 23)}
        field = {part: kf._sideline_field_mode(textures[part], part) for part in textures}
        row = {"selector": "06A0", "parts": ["pants", "sleeve"], "field": {p: [int(v) for v in c] for p, c in field.items()},
               "compose": {"pants": {"crop": [23, 0, 297, 230]}, "sleeve": {}}}
        out, changed = kf.sideline_measured_repair(atlas, {}, field, row, textures)
        self.assertGreater(changed["pants"], 1000)
        self.assertGreater(changed["sleeve"], 500)
        self.assertCheck("far_compose", out)
        levels = kf._sideline_mips(out, 256, 128, 4)
        self.assertCheck("far_compose_mips", b"".join(level.rgba for level in levels))
        palette, indices, _quality = palette_tools.quantize_levels(levels, 256)
        self.assertCheck("far_compose_palette", bytes(v for colour in palette for v in colour) + b"".join(indices))

    def assertCheck(self, name, value):
        digest = hashlib.sha256(value if isinstance(value, bytes) else np.ascontiguousarray(value).tobytes()).hexdigest()
        if name not in PINS:
            self.fail("no pin for %s: %s" % (name, digest))
        self.assertEqual(digest, PINS[name], name)


if __name__ == "__main__":
    unittest.main()
