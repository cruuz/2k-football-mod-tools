"""uf1: 2026 home/away kit fixes. Exact 4x art, pinned native compile, refusals and disc proof."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from tools.b77 import uf1_repair as repair  # noqa: E402
import uf1_author as author  # noqa: E402


def canvas(h=16, w=16, colour=(10, 20, 30)):
    a = np.zeros((h, w, 4), np.uint8)
    a[..., :3] = colour
    a[..., 3] = 255
    return a


class Art(unittest.TestCase):
    def test_polygon_coverage_is_exact_and_four_by_four(self):
        cover = fixes.polygon_coverage([[1, 1], [3, 1], [3, 3], [1, 3]], 4, 4)
        self.assertEqual(cover[1:3, 1:3].tolist(), [[16, 16], [16, 16]])
        self.assertEqual(int(cover.sum()), 64)
        half = fixes.polygon_coverage([[0, 0], [1.5, 0], [1.5, 1], [0, 1]], 4, 4)
        self.assertEqual(half[0, :3].tolist(), [16, 8, 0])
        # the same input gives the same integers on every platform (no float accumulation)
        tri = [[0.3, 0.2], [7.7, 1.1], [2.2, 6.9]]
        self.assertEqual(fixes.polygon_coverage(tri, 8, 8).tolist(), fixes.polygon_coverage(tri, 8, 8).tolist())

    def test_composite_blends_by_coverage_and_keeps_alpha(self):
        a = canvas(colour=(0, 0, 0))
        a[..., 3] = 200
        out, scope = fixes.paint(a, [{"op": "poly", "color": "#FFFFFF", "points": [[0, 0], [1.5, 0], [1.5, 1], [0, 1]]}])
        self.assertEqual(out[0, 0, :3].tolist(), [255, 255, 255])
        self.assertEqual(out[0, 1, :3].tolist(), [128, 128, 128])
        self.assertTrue((out[..., 3] == 200).all())
        self.assertEqual(int(scope.sum()), 2)

    def test_recolour_against_original_and_inverted(self):
        a = canvas()
        a[2, 2, :3] = (255, 255, 255)
        ops = [{"op": "poly", "color": "#FFFFFF", "points": [[0, 0], [4, 0], [4, 4], [0, 4]]},
               {"op": "recolor", "box": [0, 0, 4, 4], "from": ["#FFFFFF"], "color": "#0A2343", "match": "original"}]
        out, _ = fixes.paint(a, ops)
        self.assertEqual(out[2, 2, :3].tolist(), [10, 35, 67])
        self.assertEqual(out[1, 1, :3].tolist(), [255, 255, 255])
        out, _ = fixes.paint(a, [{"op": "recolor", "box": [0, 0, 4, 4], "from": ["#0A141E"], "color": "#0A141E",
                                  "tolerance": 2, "invert": True}])
        self.assertEqual(out[2, 2, :3].tolist(), [10, 20, 30])

    def test_grow_respects_into_except_and_radius(self):
        a = canvas(colour=(255, 255, 255))
        a[8, 8, :3] = 0
        a[8, 10, :3] = (220, 220, 220)
        out, scope = fixes.paint(a, [{"op": "grow", "box": [0, 0, 16, 16], "from": ["#000000"], "into": ["*"],
                                      "except": ["#DCDCDC"], "color": "#000000", "radius": 2, "tolerance": 5}])
        self.assertEqual(out[8, 10, :3].tolist(), [220, 220, 220])
        self.assertEqual(out[6, 8, :3].tolist(), [0, 0, 0])
        self.assertEqual(out[6, 6, :3].tolist(), [255, 255, 255])   # sqrt(8) > 2
        self.assertEqual(int(scope.sum()), 11)

    def test_enclosed_fills_only_holes(self):
        a = canvas(colour=(90, 15, 18))
        a[2:7, 2, :3] = a[2:7, 6, :3] = a[2, 2:7, :3] = a[6, 2:7, :3] = (255, 182, 18)
        out, scope = fixes.paint(a, [{"op": "enclosed", "box": [0, 0, 10, 10], "edge": ["#FFB612"],
                                      "color": "#FFB612", "tolerance": 10}])
        self.assertEqual(int(scope.sum()), 9)
        self.assertEqual(out[0, 0, :3].tolist(), [90, 15, 18])

    def test_copy_moves_art_and_protect_keeps_a_band(self):
        a = canvas(colour=(255, 255, 255))
        a[9:13, :, :3] = (200, 0, 0)           # band
        a[10:12, 5, :3] = (0, 0, 0)            # a letter on the band
        out, _ = fixes.paint(a, [{"op": "copy", "src": [0, 9, 16, 13], "dst": [0, 2], "skip_col": 0}])
        self.assertEqual(out[3, 5, :3].tolist(), [0, 0, 0])
        self.assertEqual(out[3, 4, :3].tolist(), [255, 255, 255])
        out, _ = fixes.paint(a, [{"op": "poly", "color": "#C80000", "points": [[0, 8], [16, 8], [16, 14], [0, 14]],
                                  "protect": {"box": [0, 0, 16, 16], "colors": ["#C80000"], "tolerance": 4}}])
        self.assertEqual(out[10, 5, :3].tolist(), [0, 0, 0])
        self.assertEqual(out[8, 5, :3].tolist(), [200, 0, 0])

    def test_unknown_operation_is_refused(self):
        with self.assertRaisesRegex(ValueError, "unknown art operation"):
            fixes.paint(canvas(), [{"op": "smudge"}])


class Data(unittest.TestCase):
    def test_pins_are_complete_and_unique(self):
        spec = fixes.spec()
        rows = spec["textures"]
        self.assertEqual(len(rows), 60)
        self.assertEqual(len(fixes.selectors(spec)), 33)
        for row in rows:
            for key in ("before_sha256", "after_sha256"):
                self.assertRegex(row[key], "^[0-9a-f]{64}$")
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertTrue(row["defects"])
            if row["kind"] == "copy_video":
                self.assertEqual(row["donor_chunk"] + 20, row["chunk"])
        spans = [(r["selector"], r["offset"], r["offset"] + r["length"]) for r in rows]
        for sel in {s for s, _, _ in spans}:
            mine = sorted((a, b) for s, a, b in spans if s == sel)
            for (a0, b0), (a1, _) in zip(mine, mine[1:]):
                self.assertLessEqual(b0, a1)

    def test_shipped_data_is_exactly_what_the_author_tool_draws(self):
        rows = {(r["selector"], r["chunk"]): r for r in fixes.spec()["textures"]}
        authored = author.entries()
        self.assertEqual(len(authored), len(rows))
        for entry in authored:
            row = rows[(entry["selector"], entry["chunk"])]
            self.assertEqual(json.loads(json.dumps(entry.get("ops"))), row.get("ops"))
            self.assertEqual(entry["texture"], row["texture"])

    def test_no_private_paths_or_retail_bytes_in_data(self):
        text = fixes.DATA.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/media/", text)
        self.assertTrue(text.isascii())


class Refusals(unittest.TestCase):
    def test_unrelated_image_is_skipped_by_studio_but_refused_by_native_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "other.img"
            path.write_bytes(b"other game")
            receipt = fixes.apply_to_image(path)
            self.assertEqual(receipt["state"], "other_image")
            self.assertEqual(path.read_bytes(), b"other game")
            with self.assertRaises(ValueError):
                fixes.apply_to_image(path, strict=True)

    def test_native_tool_refuses_wrong_disc_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bad.iso"
            source.write_bytes(b"not a disc")
            output = root / "out.iso"
            with self.assertRaisesRegex(ValueError, "unknown input"):
                repair.run(SimpleNamespace(input=source, output=output, receipts=root / "receipts"))
            self.assertFalse(output.exists())

    def test_build_runs_the_pass_after_the_giants_numbers(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertLess(source.index('_core_module("nfl2k5_nyg_numbers")'),
                        source.index('_core_module("nfl2k5_kit_fixes_2026")'))


BASE = os.environ.get("NFL2K5_UF1_BASE")


@unittest.skipUnless(BASE, "set NFL2K5_UF1_BASE to the pinned ny1 input disc for native integration")
class NativeDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raws, cls.ranges, cls.extents = repair.read_resources(Path(BASE))
        cls.compiled = {}
        for selector in ("18A0", "26H0", "18H7", "13H0", "25A0"):
            parts, receipt = fixes.compile_resource(selector, cls.raws[selector])
            out = bytearray(cls.raws[selector])
            for at, data in parts:
                out[at:at + len(data)] = data
            cls.compiled[selector] = (parts, receipt, bytes(out))

    def test_compile_matches_pins_and_only_owned_bytes_change(self):
        for selector, (parts, receipt, fixed) in self.compiled.items():
            rows = [r for r in fixes.spec()["textures"] if r["selector"] == selector]
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
            parts, receipt = fixes.compile_resource(selector, fixed)
            self.assertEqual((parts, receipt["state"]), ([], "applied"))

    def test_protected_texels_hold_within_one_level(self):
        for selector, (_, receipt, _) in self.compiled.items():
            for part in receipt["parts"]:
                if "mips" in part:
                    self.assertTrue(all(m["scope_texels"] >= 0 for m in part["mips"]))
                    self.assertLessEqual(part["protected_texels_moved_one_level"], 16)

    def test_tampered_and_partial_kits_are_refused(self):
        rows = [r for r in fixes.spec()["textures"] if r["selector"] == "26H0"]
        bad = bytearray(self.raws["26H0"])
        bad[rows[0]["offset"] + rows[0]["length"] - 1] ^= 1
        with self.assertRaisesRegex(ValueError, "unknown or partially"):
            fixes.compile_resource("26H0", bytes(bad))
        partial = bytearray(self.raws["26H0"])
        at, data = self.compiled["26H0"][0][0]
        partial[at:at + len(data)] = data
        with self.assertRaisesRegex(ValueError, "unknown or partially"):
            fixes.compile_resource("26H0", bytes(partial))

    def test_a_users_own_kit_is_left_alone(self):
        spec = fixes.spec()
        other = dict(spec, textures=[dict(r, before_sha256="0" * 64, after_sha256="1" * 64) for r in spec["textures"]])
        parts, receipt = fixes.compile_resource("18A0", self.raws["18A0"], strict=False, document=other)
        self.assertEqual((parts, receipt["state"]), ([], "other_uniform"))

    def test_giants_style7_shoulders_equal_the_chest_digits(self):
        from nfl_txtr import decode_chunk, parse_chunks
        _, _, fixed = self.compiled["18H7"]
        chunks = {c.index: c for c in parse_chunks(fixed)}
        for d in range(10):
            arm, chest = chunks[33 + d], chunks[13 + d]
            a, _ = decode_chunk(fixed, arm)
            c, _ = decode_chunk(fixed, chest)
            self.assertEqual(a[arm.system_bytes:], c[chest.system_bytes:])

    def test_no_other_archive_entry_shares_an_owned_byte(self):
        self.assertEqual(repair.alias_check(self.ranges, self.extents), [])


if __name__ == "__main__":
    unittest.main()
