"""b81-retail-free-art (ruling 2): the kit-fix recolour and move rules (mod_editor/core/nfl2k5_kit_rule_recolour.py)
give the same bytes on every platform, and behave as documented.

The rules run on the user's machine over the kit textures the Studio builds from the user's own disc; their output is
then compiled and checked against the row's ``after_sha256`` pin, so one rounding difference between platforms, numpy
or Python versions would make the build refuse the kit. This test needs no game file: it runs every rule kind on
synthetic textures generated here with integer arithmetic only (no random generator), with the edge cases (channel
values 0 and 255, exact rounding ties, odd sizes, overlapping moves), and compares SHA-256 hashes with values pinned on
the authoring machine (Linux x86-64, CPython 3.12, numpy 1.26.4)."""
import hashlib
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as kf  # noqa: E402

#: pinned on the authoring machine (Linux x86-64, CPython 3.12, numpy 1.26.4)
PINS = {
    "boxres_31x33": "661d39b8c61cd63a73bc5c73436b8efeb0f057a0f22669c43cca5d02b77835f5",
    "boxres_32x32": "c9d937082d69b669e54b356af77fbce8a62770c14ba4ac811fb7c582ed06cab6",
    "boxres_64x64": "4822fd07b3379b05a3db1d7ac21dd64f71053f1cccec945cb339fbd9d1a4975b",
    "cols_31x33": "e9e5373523bba4a7a1f4cc2e299bc800a67220884c7abb26a936beb6f5597bad",
    "cols_32x32": "25ca52b625713ad13f4e8ebe455a38fb3919cdd37b77cdbfd1ea508ad75674ab",
    "cols_64x64": "d5fdf875264ac35268cbd5526ae447434b3e3fbd91db4a05bed2671f16a06388",
    "erase_31x33": "cf2f3e3bae10909132c78e95eedd098cb43a06115458e20552e63bd390e4c78e",
    "erase_32x32": "5f9af58d0dd39141f47521cb750e07c289c1d2b21cf4fd86ec123f5dd630e5e5",
    "erase_64x64": "a9fa6a14c281faca5375617c395957f9ef1718e5dbf2cb824256137c682f3bc0",
    "map_31x33": "b69da070eaed4e9f30fa10aa0b25f1158fbef3955b5f422f9078fd38030fe469",
    "map_32x32": "b4f0c02d905a6d90661e962b5d4a38194515af9d19f39e2349b2415ae08a751b",
    "map_64x64": "f5a79065f745c2f45047c074dbca274b240933a920f4a775257f183e03151d53",
    "move_cloth_31x33": "abab0aca6dbcff96890df976e5d7d65608f5b025ba0f55a9e3a93a2c85d25fb1",
    "move_cloth_32x32": "e36ae0e4be10651332935e5e3d5e05604100931f652a3664444470199ce36ebb",
    "move_cloth_64x64": "24433d396de54fbd26002cae46a9c90815f7433f0bd7aeb2179ff017f564762a",
    "move_flat_31x33": "fd020bdf9b535454003e66d122d04315f077ccf995725ac76da2148fbe57d707",
    "move_flat_32x32": "f61ce2099351303109786c36edbb68e89868c45247bd0052f28664dc841b2b74",
    "move_flat_64x64": "e8713f8bd3fe5839cbc3b90810e0d5e9ba2b739ee907868a09d947d3a19604b5",
    "ramp_cuts_31x33": "be4931e0d8e8a3c2d555cd856ef10f1344e86bd683bb041228ba29990eff2579",
    "ramp_cuts_32x32": "041cc713486bd4cb382f0139492d79b6d3da14976e393600b7b6087a426b2539",
    "ramp_cuts_64x64": "9241c6e3b6ff169a930ac40f75068261e71eaed6670ebc4155a6d86777c58a2a",
    "ramp_near_31x33": "f2f736a969e4eb6129049599f9c069f235c4dff659b28dd88973eb6c26959727",
    "ramp_near_32x32": "a8ebe25887fc68c144f431b29232e49de9cfa3436af4518032fcedc88aabbe7e",
    "ramp_near_64x64": "5d991671acc32105ea0880ff0928439ce8a14cec3c167755930a774acdaf54ee",
    "ramp_round_31x33": "50caa56cd330f967fb0da5786786c3a072ae201221f2acc42aa4bd981c3fbf1e",
    "ramp_round_32x32": "8e1253b3389bdfd5abeaad205e99c209f2f9d4224c59013caffbeab7cc036bad",
    "ramp_round_64x64": "b0aab7fd1f9779a57fad1669d6df10f6c3f157bea4e4c43644deb19e48de7358",
    "ramp_seeded_31x33": "a64c883034d991c41e76985feaa0796df4682d8169324a307abadb0c3d49a0a0",
    "ramp_seeded_32x32": "069115e4ffee550c87127f42acf66bac40d10248486637cc9ea5f601e0205b92",
    "ramp_seeded_64x64": "685c391c8f3c0ee0150e05314b6bf83ef06a4a813bcb689721537a655d566033",
    "rowfill_31x33": "27929dc8af4716e941bed938da8bd04e8544d5ecebc570613c5a5b5b94d28668",
    "rowfill_32x32": "47eef0f4f121e9e6f05fd50c55798570d53c11df6ce5de5838850b64e636c016",
    "rowfill_64x64": "d24c690dea84e7d560f7995e135c1183061a35898af99e58cfae9183589485ec",
    "scale_31x33": "6278ae6a286ef0465780bb8726aef53aff0487ed9acca406725d766f269771ac",
    "scale_32x32": "6ab38b02dcfe8eea375557b92003572719d4f64909ffea83ceba260b6956ea0e",
    "scale_64x64": "baab14d377ae4f1053a23c500ad3336e8893ede3789f94677718ddf64ed4e29e",
}


def sha(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def noise(h, w, salt):
    """Deterministic integers 0..255 from a 32-bit integer hash of (row, column, salt)."""
    y = np.arange(h, dtype=np.uint64)[:, None]
    x = np.arange(w, dtype=np.uint64)[None, :]
    v = (y * np.uint64(73856093)) ^ (x * np.uint64(19349663)) ^ np.uint64(salt * 83492791)
    v = (v * np.uint64(2654435761)) & np.uint64(0xFFFFFFFF)
    v ^= v >> np.uint64(15)
    return (v & np.uint64(0xFF)).astype(np.int64)


def kit(h, w, salt):
    """A kit-like texture: a cloth field with shading, a soft-edged mark (blends of the field and the mark colour on
    one line), a stripe of the mark colour, cloth specks off that line, and saturated texels."""
    y = np.arange(h, dtype=np.int64)[:, None]
    x = np.arange(w, dtype=np.int64)[None, :]
    field = np.array([0xE3, 0xE5, 0xE7], np.int64)
    mark = np.array([0x4B, 0x2E, 0x9A], np.int64)
    shade = 160 + ((x * 3 + y * 5) % 97)                       # 160..256 of 256: shading toward black
    cloth = (field[None, None, :] * np.minimum(shade, 256)[..., None]) // 256
    # mark: a disc with a soft edge (mix 0..8 of 8) and a stripe
    r2 = (x - w // 3) ** 2 + (y - h // 2) ** 2
    rad = max(min(h, w) // 4, 3)
    mix = np.clip((rad * rad - r2) * 8 // max(rad * 2, 1), 0, 8)
    mix = np.where((x >= w - w // 5) & (x < w - w // 5 + 3), 8, mix)
    out = (cloth * (8 - mix[..., None]) + mark[None, None, :] * mix[..., None] + 4) // 8
    speck = noise(h, w, salt) > 247
    out = np.where(speck[..., None], np.array([0xCF, 0xB6, 0x9A]), out)
    rgba = np.concatenate([np.clip(out, 0, 255), np.full((h, w, 1), 255)], -1).astype(np.uint8)
    rgba[0, :3] = (0, 0, 0, 255)
    rgba[1, :3] = (255, 255, 255, 255)
    return rgba


def rule(**kw):
    op = dict(op="rule", module="recolour")
    op.update(kw)
    return op


def cases(h, w):
    full = [[0, 0, w, h]]
    left = [[0, 0, w // 2, h]]
    return {
        "ramp_round": rule(do="ramp", boxes=full, ends=["#E3E5E7", "#4B2E9A"], min=[1, 16],
                           levels=["#FFFFFF", "#FEDCD0", "#FDB9A1", "#FD9572", "#FC7243", "#FB4F14"]),
        "ramp_cuts": rule(do="ramp", boxes=full, ends=["#000000", "#E3E5E7"], off=2, min=[2, 3],
                          levels=["#788091", "#9DA4B8", "#B1BFCE", "#B6C1DB"], cuts=[[3, 4], [7, 8], [31, 32]]),
        "ramp_near": rule(do="ramp", boxes=left, keep=[[0, 0, 2, 2]], near=["#4B2E9A", "#000000"], tolerance=6,
                          ends=["#000000", "#FFFFFF"], levels=["#D3BC8D"]),
        "ramp_seeded": rule(do="ramp", boxes=full, ends=["#E3E5E7", "#4B2E9A"], min=[1, 2], off=24,
                            seeds=[[w // 3, h // 2]], levels=["#E3E5E7", "#B5202E"]),
        "scale": rule(do="scale", boxes=full, ends=["#000000", "#E3E5E7"], min=[1, 4], off_above=0, off=40,
                      **{"from": "#E3E5E7", "to": "#B6C1DB"}),
        "map": rule(do="map", boxes=left, pairs=[["#FFFFFF", "#121212"], ["#CFB69A", "#0D0D0D"]]),
        "move_flat": rule(do="move", src=[1, 1, w // 2, h // 2], by=[w // 4, h // 3], far=["#E3E5E7"],
                          far_tolerance=40, vacate={"to": "#E3E5E7"}),
        "move_cloth": rule(do="move", src=[2, 2, w // 2, h - 4], by=[1, 2], ends=["#E3E5E7", "#4B2E9A"], min=[1, 8],
                           off=16, vacate={"copy_by": [0, 2]}),
        "cols": rule(do="cols", rows=[2, h // 2], dy=1, at=3, src=[[1, 4], [6, w // 2]], boxes=[[1, 2, w // 2, h // 2]],
                     far=["#E3E5E7"], far_tolerance=30, vacate={"to": "#E3E5E7"}),
        "rowfill": rule(do="rowfill", boxes=[[w // 4, 2, w // 2, h - 2]], from_x=w // 4 - 1,
                        levels=["#FFFFFF", "#B9BDC1", "#002244", "#4B2E9A"]),
        "erase": rule(do="erase", boxes=[[2, 2, w - 2, h - 2]], to="#E3E5E7", far=32, dilate=1),
        "boxres": rule(do="boxres", src=[1, 1, w - 1, h - 1], dst=[3, 4, 3 + (w - 2) * 4 // 5, 4 + (h - 2) * 4 // 5],
                       field="#E3E5E7", far=24, pairs=[["#4B2E9A", "#121212"], ["#E3E5E7", "#FFFFFF"]]),
    }


def run_all():
    out = {}
    for h, w in ((31, 33), (32, 32), (64, 64)):
        base = kit(h, w, h * 131 + w)
        for name, op in cases(h, w).items():
            painted, _ = kf.paint(base, [op])
            out["%s_%dx%d" % (name, h, w)] = sha(painted)
    return out


class KitRuleRecolourTest(unittest.TestCase):
    def test_pinned_hashes(self):
        got = run_all()
        self.assertEqual(sorted(got), sorted(PINS))
        for key, value in sorted(got.items()):
            self.assertEqual(value, PINS[key], key)

    def test_ramp_rounds_half_to_even(self):
        # t = 1/10, 3/10, 1/2, 7/10, 9/10 on a 0..250 grey axis are exact ties of t * 5
        base = np.zeros((1, 5, 4), np.uint8)
        base[0, :, :3] = np.array([25, 75, 125, 175, 225])[:, None]
        base[..., 3] = 255
        op = rule(do="ramp", boxes=[[0, 0, 5, 1]], ends=["#000000", "#FAFAFA"],
                  levels=["#000000", "#010101", "#020202", "#030303", "#040404", "#050505"])
        out, _ = kf.paint(base, [op])
        self.assertEqual(out[0, :, 0].tolist(), [0, 2, 2, 4, 4])

    def test_cuts_are_inclusive_and_exact(self):
        base = np.zeros((1, 3, 4), np.uint8)
        base[0, :, :3] = np.array([99, 100, 101])[:, None]
        base[..., 3] = 255
        op = rule(do="ramp", boxes=[[0, 0, 3, 1]], ends=["#000000", "#C8C8C8"], levels=["#111111", "#222222"],
                  cuts=[[1, 2]])
        out, _ = kf.paint(base, [op])
        self.assertEqual(out[0, :, 0].tolist(), [0x11, 0x22, 0x22])

    def test_move_vacates_then_lands(self):
        base = np.full((6, 6, 4), 255, np.uint8)
        base[1, 1, :3] = (10, 20, 30)
        base[2, 1, :3] = (40, 50, 60)
        op = rule(do="move", src=[0, 0, 3, 3], by=[0, 1], far=["#FFFFFF"], vacate={"to": "#FFFFFF"})
        out, _ = kf.paint(base, [op])
        self.assertEqual(out[1, 1, :3].tolist(), [255, 255, 255])
        self.assertEqual(out[2, 1, :3].tolist(), [10, 20, 30])
        self.assertEqual(out[3, 1, :3].tolist(), [40, 50, 60])
        self.assertTrue((out[..., 3] == 255).all())

    def test_cols_takes_columns_out(self):
        base = np.full((3, 8, 4), 255, np.uint8)
        base[1, 1:6, :3] = np.array([[1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4], [5, 5, 5]])
        op = rule(do="cols", rows=[1, 2], dy=0, at=1, src=[[1, 3], [4, 6]], boxes=[[1, 1, 6, 2]], far=["#FFFFFF"],
                  vacate={"to": "#FFFFFF"})
        out, _ = kf.paint(base, [op])
        self.assertEqual(out[1, :, 0].tolist(), [255, 1, 2, 4, 5, 255, 255, 255])

    def test_mirror_lays_the_other_islands_image_colour_only(self):
        """b81 R55: the Hail Raiser upper logo as the lower one's mirror image about the atlas axis (rows y, 255 - y)."""
        a = np.zeros((256, 64, 4), np.uint8)
        a[..., 0] = (np.arange(256)[:, None] * 7 + np.arange(64)[None, :] * 3) % 251
        a[..., 1] = (np.arange(256)[:, None] * 5) % 253
        a[..., 3] = (np.arange(64)[None, :] * 4) % 256
        op = {"op": "rule", "module": "recolour", "do": "mirror", "box": [8, 40, 50, 90], "axis": 255}
        out, _ = kf.paint(a, [op])
        self.assertTrue(np.array_equal(out[40:90, 8:50, :3], a[166:216, 8:50, :3][::-1]))
        self.assertTrue(np.array_equal(out[..., 3], a[..., 3]))                   # alpha never moves
        self.assertTrue(np.array_equal(out[:40], a[:40]) and np.array_equal(out[90:], a[90:]))
        self.assertEqual(hashlib.sha256(out.tobytes()).hexdigest(),
                         "10bf9957f7800cd410705e80de5256164f759024f05678c817ed14687d92d366")

    def test_rules_name_no_palette_colour(self):
        base = kit(8, 8, 1)
        with self.assertRaises(ValueError):
            kf.paint(base, [rule(do="ramp", boxes=[[0, 0, 8, 8]], ends=["#000000", "#FFFFFF"], levels=["#FFFFFF"],
                                 color="#FFFFFF")])
        self.assertEqual(kf.art_colours([o for o in [cases(8, 8)["ramp_round"]] if "color" in o]), [])

    def test_seed_must_be_a_member(self):
        base = kit(16, 16, 2)
        with self.assertRaises(ValueError):
            kf.paint(base, [rule(do="ramp", boxes=[[0, 0, 16, 16]], ends=["#E3E5E7", "#4B2E9A"], min=[1, 1],
                                 seeds=[[2, 12]], levels=["#000000"])])



def inpaint_case():
    """A donor with a clean swoosh-like band (mark over field, with half-coverage edges) and a kit whose old band sits
    at an offset across a field and a piece of dark art."""
    h = w = 48
    f0, m0 = np.array([38, 65, 58]), np.array([255, 255, 255])
    donor = np.zeros((h, w, 4), np.uint8); donor[..., :3] = f0; donor[..., 3] = 255
    kit = np.zeros((h, w, 4), np.uint8); kit[..., :3] = (180, 20, 40); kit[..., 3] = 200
    kit[22:41, 14:21, :3] = (12, 12, 14)                                    # dark art beside the old band
    for y in range(4, 17):
        for x in range(w):
            k = 2 * x - y
            cov = 255 if 40 <= k <= 52 else 128 if k in (38, 39, 53, 54) else 0
            if cov:
                donor[y, x, :3] = f0 + (m0 - f0) * cov // 255
                kit[y + 20, x + 2, :3] = np.array([180, 20, 40]) + (np.array([250, 248, 246]) - [180, 20, 40]) * cov // 255
    op = {"op": "rule", "module": "recolour", "do": "inpaint", "rows": [16, 48],
          "footprint": {"donor": "10H0:3", "field": "#26413A", "mark": "#FFFFFF", "box": [10, 2, 40, 20],
                        "above_milli": 5, "offset": [2, 20]}}
    return kit, donor, op


class InpaintTests(unittest.TestCase):
    """b81-retail-free-art round 3 (coordinator's ruling on sw1): the old swoosh's remnants filled from the nearest
    texel outside its own footprint, the footprint read from the build's donor swoosh; integers only, pinned."""

    def test_the_old_band_is_filled_from_outside_and_pinned(self):
        kit, donor, op = inpaint_case()
        out, _ = kf.paint(kit, [op], {"10H0:3": donor})
        changed = (out != kit).any(-1)
        self.assertGreater(int(changed.sum()), 40)
        self.assertFalse(changed[:24].any() or changed[37:].any())            # only the old band's rows
        self.assertTrue(np.array_equal(out[..., 3], kit[..., 3]))              # alpha never moves
        self.assertFalse(((out[changed][:, :3] >= 240).all(-1)).any())         # no white left where it changed
        self.assertEqual(sha(out), "24e0dd06c1d17236c6e5150a9bb380a16970d6f6f985ef345dc2c35cca46e13e")

    def test_texels_an_earlier_rule_changed_are_left(self):
        kit, donor, op = inpaint_case()
        first = {"op": "clear", "to": "#B41428", "boxes": [[20, 24, 30, 30]], "above": 8}
        out, _ = kf.paint(kit, [first, op], {"10H0:3": donor})
        alone, _ = kf.paint(kit, [first], {"10H0:3": donor})
        self.assertTrue(np.array_equal(out[24:30, 20:30], alone[24:30, 20:30]))

    def test_a_missing_donor_is_refused(self):
        kit, donor, op = inpaint_case()
        with self.assertRaises(ValueError):
            kf.paint(kit, [op], {})


if __name__ == "__main__":
    if "--print-pins" in sys.argv:
        for key, value in sorted(run_all().items()):
            print('    "%s": "%s",' % (key, value))
    else:
        unittest.main()
