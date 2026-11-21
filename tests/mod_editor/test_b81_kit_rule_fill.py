"""b81 retail-free (ruling 2, the "fill" family): exact build-time fill rules (mod_editor/core/nfl2k5_kit_rule_fill.py).

The b81-art helmet cleanup and two b81-uniforms mark removals shipped their result as runs of texel colours (base
content). Their rows now carry a rule the build applies to the texture it holds. These tests pin the rule's output on
synthetic textures made here with integer arithmetic only (no game file, no random generator), so a platform, Python
or numpy difference in the arithmetic would show as a changed hash: the harmonic fill (fixed Jacobi sweeps, float64,
neighbour sums written out), the nearest-texel fill (the separable Euclidean feature transform, integers), the palette
snaps and the mask rules. Pinned on the authoring machine (Linux x86-64, CPython 3.12.3, numpy 1.26.4). With the
released v0.9 disc and the retail disc on the machine, converted document rows are also compiled to their pins."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as kf  # noqa: E402
from mod_editor.core import nfl2k5_kit_rule_fill as rf  # noqa: E402

#: pinned on the authoring machine (Linux x86-64, CPython 3.12.3, numpy 1.26.4)
PINS = {
    "hardware": "9cc51ebbf1c41075cab3782561d4e825ccfa68005718d86d1dbbd169aa62472b",
    "harmonic_41x37": "7890a603dde1457f174794ec0ab55fa5d953b51737472f097aac2e33cca3382f",
    "helmet_full_nearest": "90da249d544dfcfa5075c947daff294bf9798ba2246a25413dd11e9b956f2be0",
    "helmet_plain": "d72ea3e75f64a5eb424c55b4db2682f1668e1bd61e18aa817d21fca0daeae46d",
    "helmet_ring": "8878ada80fe00d78adac2ba811e72ec46fb2982f21f5a769311b859388845d2a",
    "nearest_41x37": "2108f74d9d5ee6bf393aad82fe5c1cbe381a0b1a015657d99c28dec774e76c73",
    "row_fill": "224805c100bd35397990aec997df715c1c374362cfcda2f93bbad802df327653",
    "standard_shell_boxes": "7f49d2007f9362a7a770a9379c4fb6ef41ba6fa50090794c5f8aa40e93f3f0db",
    "vent_masks": "54b1be047487c1c5158e4ff225fdb3e7aae476da1519115f08fb69899965a2f1",
}
#: SHA-256 of the retail disc's blank Cleveland shells (30H0.IFF chunk 12 helmet02, chunk 11 helmet00)
RETAIL_SHELLS = {12: "e5ed0352d68c9a7c74ff69d122d0f056c05aaedb7720c59124fbd299f09df612",
                 11: "ad6444c89152abf926f2b265431f6182c6b2a3bda02f3f24c22e01545cb7c924"}


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def blank_shell():
    """A 256 x 256 helmet02-sized blank shell: flat shell colour with a soft dark blob in each vent box (integers)."""
    y, x = np.mgrid[0:256, 0:256].astype(np.int64)
    rgb = np.zeros((256, 256, 3), np.int64)
    rgb[...] = (200, 90, 40)
    for i, (x0, y0, x1, y1) in enumerate(rf.VENT_BOXES):
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        rx, ry = (x1 - x0) // 3 + i % 2, (y1 - y0) // 3
        inside = ((x - cx) * (x - cx) * ry * ry + (y - cy) * (y - cy) * rx * rx) * 4 <= 4 * rx * rx * ry * ry
        rgb[inside] = (120 + 7 * i, 50, 20)
        ring = ((x - cx) * (x - cx) * ry * ry + (y - cy) * (y - cy) * rx * rx) <= 2 * rx * rx * ry * ry
        rgb[ring & ~inside] = (190, 84, 36)
    out = np.zeros((256, 256, 4), np.uint8)
    out[..., :3] = rgb
    out[..., 3] = 255
    return out


def helmet_texture():
    """A finished 2026 shell: shaded field, painted vent twins, a transparent flag diamond with a dotted outline, a
    logo block, two old-ink pieces and an old shell square; a few alpha classes (reflection mask)."""
    y, x = np.mgrid[0:256, 0:256].astype(np.int64)
    r = 30 + (x * 3 + y * 5) % 23
    g = 60 + (x * 7 + y * 2) % 19
    b = 140 + (x + y * 3) % 31
    rgb = np.stack([r, g, b], axis=-1)
    for i, (x0, y0, x1, y1) in enumerate(rf.VENT_BOXES):
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        hit = ((x - cx) * (x - cx) + 3 * (y - cy) * (y - cy)) <= 40 + 9 * i
        rgb[hit] = (10 + 3 * i, 20, 70)
    d = (np.abs(x - 122) + np.abs(y - 127)) <= 18
    edge = ((np.abs(x - 122) + np.abs(y - 127)) == 19) & ((x + y) % 2 == 0)
    rgb[edge] = (240, 240, 240)
    rgb[(x >= 60) & (x < 90) & (y >= 60) & (y < 80)] = (250, 200, 0)
    rgb[(x >= 30) & (x < 34) & (y >= 200) & (y < 206)] = (230, 20, 20)
    rgb[(x >= 100) & (x < 104) & (y >= 200) & (y < 203)] = (5, 5, 5)
    out = np.zeros((256, 256, 4), np.uint8)
    out[..., :3] = rgb
    out[..., 3] = 255 - ((x // 32 + y // 64) % 3)
    out[d, 3] = 0
    return out


HELMET_OP = {
    "op": "rule", "module": "fill", "kind": "helmet", "hardware": "retail:30H0:12", "vents": "hnhh-n",
    "keep": {"grow": 1, "of": {"all": [{"box": [64, 104, 84, 118]}, {"near": "#0D1446", "within": 6}]}},
    "flag": {"from": "self", "paint": "ring", "how": "h"},
    "old": {"all": [{"box": [28, 198, 36, 208]}, {"far2": "#E61414", "above": -1}]},
    "boxes": {"all": [{"box": [98, 198, 106, 205]}, {"dark": 30}]},
    "snap": [[255, "#123456"]],
}


def case_outputs():
    """{name: output array} of every pinned case."""
    blank = blank_shell()
    texture = helmet_texture()
    donors = {"retail:30H0:12": blank}
    out = {}
    out["vent_masks"] = np.stack(rf.vent_masks(blank))
    out["hardware"] = rf.hardware_mask(blank)
    out["helmet_ring"] = rf.apply(texture.copy(), HELMET_OP, texture, donors)
    full = dict(HELMET_OP, vents="nnnnnn", flag={"from": "self", "paint": "full", "how": "n"})
    out["helmet_full_nearest"] = rf.apply(texture.copy(), full, texture, donors)
    plain = {k: v for k, v in HELMET_OP.items() if k not in ("old", "boxes", "keep")}
    out["helmet_plain"] = rf.apply(texture.copy(), plain, texture, donors)
    standard = {"op": "rule", "module": "fill", "kind": "helmet", "hardware": "retail:30H0:12", "zone": [6, 16, 150, 240],
                "vents": "------", "boxes": HELMET_OP["boxes"]}
    out["standard_shell_boxes"] = rf.apply(texture.copy(), standard, texture, donors)
    y, x = np.mgrid[0:37, 0:41].astype(np.int64)
    rgb = np.stack([(x * 9 + y * 4) % 256, (x * 3 + y * 11) % 256, (x * y) % 256], axis=-1).astype(np.float64)
    hole = ((x - 20) * (x - 20) + (y - 18) * (y - 18)) <= 81
    out["harmonic_41x37"] = rf.band_fill(rgb, hole, np.zeros_like(hole))
    out["nearest_41x37"] = rf.nearest_fill(rgb, hole, (x + y) % 5 == 0)
    stripe = np.zeros((40, 64, 4), np.uint8)
    stripe[..., :3] = 20
    stripe[..., 3] = 255
    stripe[:, 20:27, 1] = 95
    stripe[7, :, :3] = 17
    row_op = {"op": "rule", "module": "fill", "kind": "row",
              "mask": {"all": [{"box": [10, 0, 40, 40]}, {"far": "#141414", "above": 8}]}}
    out["row_fill"] = rf.apply(stripe.copy(), row_op, stripe, {})
    return out


class FillRuleArithmetic(unittest.TestCase):
    def test_outputs_match_the_authoring_machine(self):
        got = {name: digest(array) for name, array in case_outputs().items()}
        if not PINS:
            self.skipTest("pins not written yet: " + json.dumps(got, sort_keys=True))
        self.assertEqual(got, PINS)

    def test_nearest_source_is_scipys_feature_transform(self):
        try:
            from scipy import ndimage
        except ImportError:
            self.skipTest("scipy absent")
        for h, w, step in ((7, 9, 3), (33, 31, 5), (64, 64, 7), (5, 40, 11)):
            y, x = np.mgrid[0:h, 0:w]
            not_source = ((x * 7 + y * 13) % step) != 0
            iy, ix = ndimage.distance_transform_edt(not_source, return_distances=False, return_indices=True)
            jy, jx = rf.nearest_source(not_source)
            self.assertTrue((iy == jy).all() and (ix == jx).all(), (h, w, step))

    def test_row_fill_takes_the_nearest_unmasked_texel_ties_to_the_left(self):
        t = np.zeros((1, 7, 4), np.uint8)
        t[0, :, :3] = [[1, 1, 1], [200, 0, 0], [200, 0, 0], [200, 0, 0], [200, 0, 0], [3, 3, 3], [4, 4, 4]]
        op = {"kind": "row", "mask": {"far": "#000000", "above": 100}}
        got = rf.apply(t.copy(), op, t, {})
        self.assertEqual(got[0, :, 0].tolist(), [1, 1, 1, 3, 3, 3, 4])

    def test_unknown_kinds_and_mask_rules_are_refused(self):
        t = np.zeros((4, 4, 4), np.uint8)
        with self.assertRaises(ValueError):
            rf.apply(t, {"kind": "smudge"}, t, {})
        with self.assertRaises(ValueError):
            rf.mask_of({"blur": 3}, t)
        with self.assertRaises(ValueError):
            rf.apply(t, dict(HELMET_OP), t, {})              # the blank shell donor is absent

    def test_the_rule_names_no_colour_for_the_palette(self):
        # the compile adds the colours of ops with a "color" key; a fill asks for none
        self.assertEqual(kf.art_colours([op for op in [HELMET_OP] if "color" in op]), [])
        self.assertNotIn("color", HELMET_OP)


class ConvertedDocument(unittest.TestCase):
    def test_converted_rows_carry_one_rule_and_the_retail_shell_pin(self):
        document = kf.helmets_b81()
        rules = [r for r in document["textures"] if any(op["op"] == "rule" for op in r["ops"])
                 and r["ops"][0].get("kind") == "helmet"]
        self.assertGreater(len(rules), 100)
        for row in rules:
            kinds = [op["op"] for op in row["ops"]]
            # a rule, or a rule and the runs of the project's own drawing it does not make (keyline, real mark)
            self.assertIn(kinds, (["rule"], ["rule", "runs"]), row["selector"])
            op = row["ops"][0]
            self.assertEqual((op["module"], op["kind"]), ("fill", "helmet"))
            # the blank retail Cleveland shell of the row's family, read from the user's disc (pinned retail bytes)
            self.assertEqual(op["hardware"], "retail:30H0:%d" % row["chunk"])
            self.assertEqual(row["donors"][op["hardware"]], RETAIL_SHELLS[row["chunk"]])
            self.assertNotIn("color", json.dumps(op))
        self.assertIn("30H0", kf.retail_donor_kits(document))
        self.assertNotIn("retail", kf.donor_kits(document))

    def test_converted_rows_compile_to_their_pins_from_the_discs(self):
        disc = os.environ.get("NFL2K5_V09_XISO", "")
        retail = os.environ.get("NFL2K5_RETAIL_XISO", "")
        if not (disc and Path(disc).is_file() and retail and Path(retail).is_file()):
            self.skipTest("the released v0.9 disc or the retail disc is absent")
        document = kf.helmets_b81()
        picked = []
        for row in document["textures"]:
            if row["ops"][0]["op"] == "rule" and row["selector"][2] == "H" and row["selector"] not in {
                    r["selector"] for r in picked}:
                picked.append(row)
            if len(picked) >= 6:
                break
        selectors = sorted({r["selector"] for r in picked})
        kits = kf.read_kits(disc, sorted(set(selectors) | set(kf.donor_kits(document))))
        retail_kits = kf.read_kits(retail, kf.retail_donor_kits(document))
        logos = kf.read_logos(disc, kf.logo_donor_names(document))
        for selector in selectors:
            sub = dict(document, textures=[r for r in document["textures"] if r["selector"] == selector])
            replacements, receipt = kf.compile_resource(selector, kits[selector], strict=True, document=sub,
                                                        kits=kits, retail_kits=retail_kits, logos=logos)
            self.assertEqual(receipt["state"], "applied", selector)
            self.assertEqual(len(replacements), len(sub["textures"]), selector)


#: far_helmet on synthetic textures (integers only)
FAR_PINS = {
    "far_helmet": "03e5524636343bffb562036bbb84803cb71c54b98d09343cd9357f43d7a4d22c",
    "far_helmet_black_fabric": "9212a0451a80ab5262ea5d2911aa422088c50494fb1343d21860213ab5374d6b",
    "far_helmet_flip": "c088ffb21f3d8eae4a55f68aa21cd37cff89cfbb1d79a5b67011ba51960f5033",
    "far_helmet_light": "c205643a6d8f03550b188d1c4cc04a5c7a774ca577df779dd2081e891b0c7538",
    "far_weights": "acbae245ba023876c7fc46e752ec6aa48e7d09b415cc1c0e9b30b51cdb854470",
}
#: the new after of 04H2:51 and 04A2:51 (kf.compile_texture of the far_helmet row on the released v0.9 span)
FAR_AFTER = "f2478f281fc36d8ea6d37c2bd8eba6c54f377031be06c8fb6cc3902bff561513"
#: the old rows' after (runs copying the v0.9-only 04H0 far helmet): must never come back
FAR_OLD_AFTER = "7870638bc1fa30f699d9d3ff1ce2210b5ea978bf115432d848437dcb93624a12"
#: digest() of the level 0 the rule reads as its near helmet: the league project's import of the black 2012 helmet into
#: 04H2/04A2 chunk 12 (span 30b66cc3...), whose level 0 equals the released v0.9 disc's 04H0 chunk 12 level 0
FAR_NEAR_LEVEL0 = "91cf21287ccb4bb3a7bfcf2d5b0ae6896dec2653d49982c5c30f8202b1acc54e"
FAR_OP = {"op": "rule", "module": "fill", "kind": "far_helmet", "near": 12, "island": [38, 91, 126, 128],
          "decal": {"box": [34, 148, 132, 202], "to": [99, 107, 121, 119]}}


def far_atlas(fabric=(60, 62, 66)):
    """A 256 x 128 splayer-sized atlas: a helmet island of ``fabric`` with integer folds, its border, a dark crown
    band at the top right and an old logo (light oval in a blue ring) where the retail panther sits."""
    y, x = np.mgrid[0:128, 0:256].astype(np.int64)
    rgb = np.zeros((128, 256, 3), np.int64)
    rgb[...] = (90, 120, 60)
    island = (x >= 38) & (x < 126) & (y >= 91)
    wave = (x * 5 + y * 3) % 13 - 6 - 12 * (((x + 2 * y) % 17) < 3)
    for c in range(3):
        rgb[..., c] = np.where(island, fabric[c] + wave, rgb[..., c])
    rgb[90, 37:128] = (120, 190, 90)
    rgb[90:128, 37] = (120, 190, 90)
    rgb[island & (x >= 80) & (y < 97) & ((x - 80) > 6 * (y - 91))] = (8, 8, 8)
    inner = ((x - 110) * (x - 110) * 4 + (y - 113) * (y - 113) * 16) <= 400
    outer = ((x - 110) * (x - 110) * 4 + (y - 113) * (y - 113) * 16) <= 640
    rgb[island & inner] = (200, 200, 200)
    rgb[island & outer & ~inner] = (0, 120, 200)
    out = np.zeros((128, 256, 4), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255)
    out[..., 3] = 255
    return out


def far_near(shell=(18, 18, 25)):
    """A 256 x 256 helmet02-sized near helmet: a shell with a 3-level ripple and, in the lower logo box, a dark oval
    body inside a blue ring with a white eye and teeth; a few alpha-254 texels."""
    y, x = np.mgrid[0:256, 0:256].astype(np.int64)
    rgb = np.zeros((256, 256, 3), np.int64)
    for c in range(3):
        rgb[..., c] = shell[c] + (x + y) % 3
    body = ((x - 83) * (x - 83) * 576 + (y - 175) * (y - 175) * 2025) <= 1166400
    ring = ((x - 83) * (x - 83) * 729 + (y - 175) * (y - 175) * 2304) <= 1679616
    rgb[ring & ~body] = (0, 133, 202)
    rgb[body] = (2, 2, 2)
    rgb[((x - 55) * (x - 55) + (y - 170) * (y - 170)) <= 9] = (240, 240, 240)
    rgb[(x >= 50) & (x < 60) & (y >= 180) & (y < 184)] = (230, 230, 230)
    out = np.zeros((256, 256, 4), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255)
    out[..., 3] = np.where((x * y) % 97 == 0, 254, 255)
    return out


def far_cases():
    near, atlas = far_near(), far_atlas()
    out = {"far_helmet": rf.apply(atlas.copy(), FAR_OP, atlas, {12: near})}
    flip = dict(FAR_OP, decal=dict(FAR_OP["decal"], flip=True))
    out["far_helmet_flip"] = rf.apply(atlas.copy(), flip, atlas, {12: near})
    light, light_near = far_atlas((200, 200, 205)), far_near((230, 230, 228))
    out["far_helmet_light"] = rf.apply(light.copy(), FAR_OP, light, {12: light_near})
    black = far_atlas((12, 12, 14))
    out["far_helmet_black_fabric"] = rf.apply(black.copy(), FAR_OP, black, {12: near})
    out["far_weights"] = np.concatenate([rf._far_weights(98, 22).ravel(), rf._far_weights(54, 12).ravel()])
    return out


class FarHelmetRule(unittest.TestCase):
    def test_outputs_match_the_authoring_machine(self):
        got = {name: digest(array) for name, array in far_cases().items()}
        if not FAR_PINS:
            self.skipTest("pins not written yet: " + json.dumps(got, sort_keys=True))
        self.assertEqual(got, FAR_PINS)

    def test_area_weights_are_whole_overlaps(self):
        for source, target in ((98, 22), (54, 12), (8, 2), (7, 7), (5, 3)):
            w = rf._far_weights(source, target)
            self.assertEqual(w.dtype, np.int64)
            self.assertTrue((w.sum(axis=1) == source).all(), (source, target))    # each target texel: B units
            self.assertTrue((w.sum(axis=0) == target).all(), (source, target))    # each source texel: W units
        self.assertEqual(rf._far_weights(8, 2).tolist(), [[2, 2, 2, 2, 0, 0, 0, 0], [0, 0, 0, 0, 2, 2, 2, 2]])

    def test_only_the_island_rgb_changes(self):
        near, atlas = far_near(), far_atlas()
        got = rf.apply(atlas.copy(), FAR_OP, atlas, {12: near})
        x0, y0, x1, y1 = FAR_OP["island"]
        outside = np.ones(atlas.shape[:2], bool)
        outside[y0:y1, x0:x1] = False
        self.assertTrue((got[outside] == atlas[outside]).all())
        self.assertTrue((got[..., 3] == atlas[..., 3]).all())
        self.assertGreater(int((got[~outside] != atlas[~outside]).any(axis=1).sum()), 2000)
        # the old logo is gone: its oval takes the shell (near black), the decal sits in its target only
        self.assertLess(int(got[113, 110, :3].max()), 60)

    def test_refusals(self):
        near, atlas = far_near(), far_atlas()
        with self.assertRaises(ValueError):
            rf.apply(atlas.copy(), FAR_OP, atlas, {})                               # the near helmet is absent
        with self.assertRaises(ValueError):
            rf.apply(atlas.copy(), dict(FAR_OP, decal={"box": [34, 148, 132, 202], "to": [99, 80, 121, 119]}),
                     atlas, {12: near})                                              # target outside the island
        with self.assertRaises(ValueError):
            rf.apply(atlas.copy(), dict(FAR_OP, decal={"box": [34, 148, 44, 158], "to": [99, 107, 121, 119]}),
                     atlas, {12: near})                                              # not a downsample
        self.assertNotIn("color", json.dumps(FAR_OP))


class CarolinaFarHelmetRows(unittest.TestCase):
    def test_the_rows_are_one_far_helmet_rule_on_the_kits_own_near_helmet(self):
        rows = {(r["selector"], r["chunk"]): r for r in kf.helmets_b81()["textures"]}
        for selector in ("04H2", "04A2"):
            row = rows[(selector, 51)]
            self.assertEqual([op["op"] for op in row["ops"]], ["rule"], selector)      # no runs, no texels
            self.assertEqual(row["ops"][0], FAR_OP, selector)
            # the donor is the kit's own chunk 12 as the helmet pass finds it: the league import its own row starts from
            self.assertEqual(row["donors"], {"12": rows[(selector, 12)]["before_sha256"]}, selector)
            self.assertEqual(row["after_sha256"], FAR_AFTER, selector)
            self.assertNotEqual(row["after_sha256"], FAR_OLD_AFTER, selector)
            self.assertEqual(row.get("max_blend_slots"), 64, selector)

    def test_the_rows_compile_to_their_pin_from_the_released_disc(self):
        disc = os.environ.get("NFL2K5_V09_XISO", "")
        if not (disc and Path(disc).is_file()):
            self.skipTest("the released v0.9 disc is absent")
        rows = {(r["selector"], r["chunk"]): r for r in kf.helmets_b81()["textures"]}
        kits = kf.read_kits(disc, ["04H0", "04H2", "04A2"])
        # the level 0 the rule reads (the league import in 04H2/04A2 chunk 12) is the released 04H0 chunk 12 level 0
        c = kf._chunk_for(kits["04H0"], 12)
        near = kf.texture_rgba(kits["04H0"][c.offset:c.end_offset])
        self.assertEqual(digest(near), FAR_NEAR_LEVEL0)
        for selector in ("04H2", "04A2"):
            row = rows[(selector, 51)]
            c = kf._chunk_for(kits[selector], 51)
            span = kits[selector][c.offset:c.end_offset]
            self.assertEqual(hashlib.sha256(span).hexdigest(), row["before_sha256"], selector)
            new, _detail = kf.compile_texture(span, row, {12: near})
            self.assertEqual(hashlib.sha256(new).hexdigest(), FAR_AFTER, selector)


if __name__ == "__main__":
    unittest.main()
