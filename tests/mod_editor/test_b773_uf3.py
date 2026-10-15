"""uf3 (b773): uniform elements judged against the 2026 game highlights. The third kit-fix document (``finish``), its
new chunk kinds (the nameplate glyph metrics from a donor kit, the Unif arm-number route), the texel op, the authored
Washington helmet W, the build order, refusals and the in-place native repair."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from tools.b77 import uf3_repair as repair  # noqa: E402
import uf3_author as author  # noqa: E402


def unif_span(route=4, facemask=b"\x00\x00\x00\xff"):
    body = bytearray(80)
    body[0x30:0x34] = facemask
    struct.pack_into("<I", body, 0x38, route)
    header = struct.pack("<4s7I", b"Unif", 80, 0, 0, 0, 0, 0, 0)
    return header + bytes(body)


def name_span(widths):
    body = bytearray(160)
    body[12:16] = b"NAME"
    pairs = []
    for i, w in enumerate(widths):
        pairs += [32 * (i + 1), w]
    struct.pack_into("<58H", body, 0x2C, *pairs)
    header = struct.pack("<4s7I", b"NAME", 160, 0, 0, 0, 0, 0, 0)
    return header + bytes(body)


class Kinds(unittest.TestCase):
    def test_unif_route_is_set_and_checked(self):
        span = unif_span(route=4)
        new, detail = fixes.compile_unif(span, {"ints": {"number_route": 1}})
        self.assertEqual(len(new), len(span))
        self.assertEqual(struct.unpack_from("<I", new, 32 + 0x38)[0], 1)
        self.assertEqual([i for i in range(len(span)) if span[i] != new[i]], [32 + 0x38])
        self.assertEqual(detail["ints"], {"number_route": 1})
        with self.assertRaisesRegex(ValueError, "already hold"):
            fixes.compile_unif(new, {"ints": {"number_route": 1}})
        with self.assertRaisesRegex(ValueError, "unsupported"):
            fixes.compile_unif(span, {"ints": {"number_route": 7}})
        with self.assertRaisesRegex(ValueError, "unexpected stored"):
            fixes.compile_unif(unif_span(route=9), {"ints": {"number_route": 1}})

    def test_nameplate_takes_only_the_donor_widths(self):
        mine, donor = name_span([9] * 29), name_span([16] * 29)
        new, detail = fixes.compile_name(mine, donor, {"donor_selector": "22H0"})
        self.assertEqual(new, donor)
        self.assertEqual(detail["widths_changed"], 29)
        changed = [i for i in range(len(mine)) if mine[i] != new[i]]
        self.assertTrue(changed and min(changed) >= 32 + 0x2C and max(changed) < 32 + 0xA0)
        with self.assertRaisesRegex(ValueError, "already has"):
            fixes.compile_name(donor, donor, {"donor_selector": "22H0"})
        other = bytearray(donor)
        other[32 + 4] = 1                                          # differs outside the metric pairs
        with self.assertRaisesRegex(ValueError, "outside its metrics"):
            fixes.compile_name(mine, bytes(other), {"donor_selector": "22H0"})
        moved = bytearray(donor)
        struct.pack_into("<H", moved, 32 + 0x2C, 999)              # a different atlas layout
        with self.assertRaisesRegex(ValueError, "atlas offsets differ"):
            fixes.compile_name(mine, bytes(moved), {"donor_selector": "22H0"})

    def test_retint_field_moves_a_white_field_mark_onto_a_coloured_one(self):
        a = np.zeros((4, 4, 4), np.uint8)
        a[..., :3] = (255, 255, 255)
        a[1, 1, :3] = (10, 36, 78)                                      # the mark
        a[1, 2, :3] = (132, 145, 166)                                    # half-way anti-aliasing
        out, _ = fixes.paint(a, [{"op": "retint", "box": [0, 0, 4, 4], "base": "#FFFFFF", "source": "#0A244E",
                                  "color": "#0A2343", "field": "#FC4C02", "tolerance": 30}])
        self.assertEqual(out[1, 1, :3].tolist(), [10, 35, 67])
        self.assertTrue(all(abs(int(v) - w) <= 3 for v, w in zip(out[1, 2, :3], (131, 55, 34))))
        self.assertEqual(out[0, 0, :3].tolist(), [255, 255, 255])      # t below 5 %: the field itself is untouched

    def test_stamp_from_another_kit_uses_its_key(self):
        src = np.zeros((8, 8, 4), np.uint8)
        src[..., :3] = 255
        src[..., 3] = 255
        src[2, 2, :3] = (0, 0, 0)
        out, scope = fixes.paint(np.zeros((8, 8, 4), np.uint8), [{"op": "stamp", "donor": "16A0:3", "src": [0, 0, 8, 8],
                                 "dst": [0, 0, 8, 8], "skip": ["#FFFFFF"]}], {"16A0:3": src})
        self.assertEqual(int(scope.sum()), 0)                           # black on black: drawn, unchanged
        out, scope = fixes.paint(np.full((8, 8, 4), 200, np.uint8), [{"op": "stamp", "donor": "16A0:3",
                                 "src": [0, 0, 8, 8], "dst": [0, 0, 8, 8], "skip": ["#FFFFFF"]}], {"16A0:3": src})
        self.assertEqual(int(scope.sum()), 1)
        self.assertEqual(out[2, 2, :3].tolist(), [0, 0, 0])
        doc = {"textures": [{"donor_selector": "22H0"}, {"donors": {"16A0:3": "x", "4": "y"}}]}
        self.assertEqual(fixes.donor_kits(doc), ["16A0", "22H0"])

    def test_texels_paint_listed_points_and_alpha(self):
        a = np.zeros((8, 8, 4), np.uint8)
        a[..., 3] = 252
        out, scope = fixes.paint(a, [{"op": "texels", "color": "#010203", "alpha": 255, "points": [[1, 2], [3, 4]]}])
        self.assertEqual(int(scope.sum()), 2)
        self.assertEqual(out[2, 1].tolist(), [1, 2, 3, 255])
        self.assertEqual(out[4, 3].tolist(), [1, 2, 3, 255])
        with self.assertRaisesRegex(ValueError, "outside the texture"):
            fixes.paint(a, [{"op": "texels", "color": "#010203", "points": [[8, 0]]}])


class WashingtonW(unittest.TestCase):
    def test_four_strokes_split_by_thin_lines(self):
        pieces = author.w_pieces("B")
        self.assertEqual(len(pieces), 4)
        # the decal keeps the outlined v0.6 W's place: 61 texels wide, 33.5 tall, top-left near (49, 162)
        xs = [x for p in pieces for x, _ in p]
        ys = [y for p in pieces for _, y in p]
        self.assertAlmostEqual(min(xs), 49.2, delta=0.5)
        self.assertAlmostEqual(max(xs) - min(xs), 61.4, delta=0.5)
        self.assertAlmostEqual(max(ys) - min(ys), 33.5, delta=0.5)
        # splits: (69 - 2 * 16) units scaled, about 1.3 texels
        split = (69 - 2 * author.W_GROW) * author.W_SCALE * author.W_TEXEL
        self.assertTrue(1.1 < split < 1.5)

    def test_both_sides_are_the_same_w_turned_half_a_turn(self):
        b, a = author.w_pieces("B"), author.w_pieces("A")
        for pb, pa in zip(b, a):
            for (xb, yb), (xa, ya) in zip(pb, pa):
                # side A = side B rotated 180 degrees about the texture point where the two placements meet
                self.assertAlmostEqual(xa, 115.0 - 4.758 - (xb - 45.0 - 4.495), delta=1e-3)
                self.assertAlmostEqual(ya, 98.0 - 5.334 - (yb - 157.0 - 5.524), delta=1e-3)

    def test_ops_paint_gold_strokes_and_burgundy_splits(self):
        shell = np.zeros((256, 256, 4), np.uint8)
        shell[..., :3] = (91, 15, 18)
        shell[..., 3] = 255
        out, scope = fixes.paint(shell, author.was_w_ops())
        gold = (out[..., 0] > 230) & (out[..., 1] > 160)
        self.assertGreater(int(gold[150:205, 40:120].sum()), 900)       # side B
        self.assertGreater(int(gold[50:105, 40:120].sum()), 900)        # side A
        # the first split crosses mid-height between stroke 1 and stroke 2: a burgundy texel between gold ones
        row = out[178, 40:120]
        runs = np.flatnonzero(np.diff((row[:, 0] > 200).astype(int)) != 0)
        self.assertGreaterEqual(len(runs), 6)                         # four gold runs across the W


class Data(unittest.TestCase):
    def test_pins_are_complete_and_unique(self):
        doc = fixes.finish()
        rows = doc["textures"]
        keys = set()
        for row in rows:
            self.assertIn(row["kind"], fixes.KINDS)
            for key in ("before_sha256", "after_sha256"):
                self.assertRegex(row[key], "^[0-9a-f]{64}$")
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertNotIn((row["selector"], row["chunk"]), keys)
            keys.add((row["selector"], row["chunk"]))
            if row["kind"] == "name":
                self.assertRegex(row["donor_sha256"], "^[0-9a-f]{64}$")
                self.assertNotIn(row["donor_selector"], fixes.selectors(doc))
        spans = [(r["selector"], r["offset"], r["offset"] + r["length"]) for r in rows]
        for sel in {s for s, _, _ in spans}:
            mine = sorted((a, b) for s, a, b in spans if s == sel)
            for (a0, b0), (a1, _) in zip(mine, mine[1:]):
                self.assertLessEqual(b0, a1)

    def test_shipped_data_is_exactly_what_the_author_tool_draws(self):
        rows = {(r["selector"], r["chunk"]): r for r in fixes.finish()["textures"]}
        authored = author.entries()
        self.assertEqual(len(authored), len(rows))
        for entry in authored:
            row = rows[(entry["selector"], entry["chunk"])]
            for key in ("ops", "ints", "kind", "texture", "donor_selector"):
                self.assertEqual(json.loads(json.dumps(entry.get(key))), row.get(key), (entry["selector"], key))

    def test_rows_revising_uf1_and_uf2_start_from_their_output(self):
        # the later document owns the final bytes when both earlier passes touched a texture
        earlier = {(r["selector"], r["chunk"]): r for r in fixes.spec()["textures"] + fixes.alternates()["textures"]}
        both = [r for r in fixes.finish()["textures"] if (r["selector"], r["chunk"]) in earlier]
        self.assertEqual(sorted((r["selector"], r["chunk"]) for r in both),
                         [("03A0", 3), ("05A0", 3), ("05H0", 3), ("08A0", 3), ("08H0", 3), ("13A0", 3), ("19A0", 3),
                          ("19H0", 3), ("29A0", 12), ("29H0", 12)])
        for r in both:
            e = earlier[(r["selector"], r["chunk"])]
            self.assertEqual((r["before_sha256"], r["offset"], r["length"]), (e["after_sha256"], e["offset"], e["length"]))

    def test_documents_are_separate_and_unchanged(self):
        self.assertEqual(len(fixes.spec()["textures"]), 60)
        self.assertEqual(len(fixes.alternates()["textures"]), 544)
        self.assertEqual(len({fixes.DATA, fixes.DATA_ALTS, fixes.DATA_UF3}), 3)

    def test_no_private_paths_in_data(self):
        text = fixes.DATA_UF3.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/media/", text)
        self.assertTrue(text.isascii())

    def test_baltimore_leftovers_decode(self):
        for chunk, count in ((11, 358), (12, 349)):
            points = author.runs_to_points(author.BAL_REMNANTS[chunk])
            self.assertEqual(len(points), count)
            self.assertEqual(len({tuple(p) for p in points}), count)
            self.assertTrue(all(0 <= x < 256 and 0 <= y < 256 for x, y in points))

    def test_swoosh_moves_only_on_sleeve_number_kits(self):
        moved = sorted(author.SWOOSH_FORWARD)
        self.assertNotIn("37H0", moved)                                  # Noah: the Texans are right as they are
        self.assertNotIn("24H0", moved)                                  # the Chargers wear no arm number
        self.assertEqual(len(moved), 14)


class Refusals(unittest.TestCase):
    def test_unrelated_image_is_skipped_by_studio_but_refused_by_native_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "other.img"
            path.write_bytes(b"other game")
            self.assertEqual(fixes.apply_finish(path)["state"], "other_image")
            self.assertEqual(path.read_bytes(), b"other game")
            with self.assertRaises(ValueError):
                fixes.apply_finish(path, strict=True)

    def test_native_tool_refuses_a_wrong_disc_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            disc = root / "bad.iso"
            disc.write_bytes(b"not a disc")
            with self.assertRaisesRegex(ValueError, "unexpected disc size"):
                repair.run(SimpleNamespace(disc=disc, receipts=root / "receipts", rollback=False))
            self.assertEqual(disc.read_bytes(), b"not a disc")
            self.assertFalse((root / "receipts").exists())
        self.assertEqual(repair.BASE_SHA256, "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4")

    def test_build_runs_uf3_after_the_alternates(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertLess(source.index("kit_fixes.apply_alternates(target)"), source.index("kit_fixes.apply_finish(target)"))

    def test_name_rows_need_their_donor(self):
        row = [r for r in fixes.finish()["textures"] if r["kind"] == "name"][0]
        doc = dict(fixes.finish(), textures=[row])
        raw = bytes(row["resource_size"])
        with self.assertRaises(ValueError):
            fixes.compile_resource(row["selector"], raw, strict=True, document=doc)


DISC = os.environ.get("NFL2K5_UF3_DISC")


@unittest.skipUnless(DISC, "set NFL2K5_UF3_DISC (the v0.6.1 base disc, read only) for native integration")
class NativeDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = fixes.finish()
        cls.donors = {}
        cls.raws, cls.ranges, cls.extents = repair.read_resources(Path(DISC), cls.doc, cls.donors)
        cls.compiled = {}
        for selector, raw in cls.raws.items():
            parts, receipt = fixes.compile_resource(selector, raw, document=cls.doc, kits=cls.donors)
            out = bytearray(raw)
            for at, data in parts:
                out[at:at + len(data)] = data
            cls.compiled[selector] = (parts, receipt, bytes(out))

    def test_compile_matches_pins_and_only_owned_bytes_change(self):
        for selector, (parts, receipt, fixed) in self.compiled.items():
            rows = [r for r in self.doc["textures"] if r["selector"] == selector]
            self.assertEqual(len(parts), len(rows))
            owned = set()
            for r in rows:
                owned.update(range(r["offset"], r["offset"] + r["length"]))
                self.assertEqual(fixes.sha(fixed[r["offset"]:r["offset"] + r["length"]]), r["after_sha256"])
            changed = {i for i, (a, b) in enumerate(zip(self.raws[selector], fixed)) if a != b}
            self.assertTrue(changed)
            self.assertFalse(changed - owned)

    def test_replay_is_a_no_op(self):
        for selector, (_, _, fixed) in self.compiled.items():
            parts, receipt = fixes.compile_resource(selector, fixed, document=self.doc, kits=self.donors)
            self.assertEqual((parts, receipt["state"]), ([], "applied"))

    def test_unc_bowl_kit_takes_the_jersey_route_and_widths(self):
        from nfl_txtr import parse_chunks
        fixed = self.compiled["22A4"][2]
        chunks = parse_chunks(fixed)
        self.assertEqual(struct.unpack_from("<I", fixed, chunks[0].body_offset + 0x38)[0], 1)
        donor = self.donors["22H0"]
        d44 = parse_chunks(donor)[44]
        self.assertEqual(fixed[chunks[44].offset:chunks[44].end_offset], donor[d44.offset:d44.end_offset])
        self.assertEqual(struct.unpack_from("<I", self.compiled["22H4"][2], 32 + 0x38)[0], 1)

    def test_no_other_archive_entry_shares_an_owned_byte(self):
        self.assertEqual(repair.alias_check(self.ranges, self.extents), [])

    def test_no_owned_span_in_pack_0_and_none_overlaps_st1(self):
        self.assertFalse([r for r in self.ranges if r["file"].split("/")[-1] in repair.FORBIDDEN_PACKS])
        self.assertEqual(repair.st1_disjointness(self.ranges)["overlapping_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
