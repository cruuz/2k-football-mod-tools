"""sea1 (b773): the Seattle helmet (logo fragment off the crown stripe, the helmet back's lines and band whole) and the
wolf-grey shoulder digits. The fourth kit-fix document (``seattle``), the palette scale, the authored shapes, the build
order, refusals and the in-place native repair."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from tools.b77 import sea1_repair as repair  # noqa: E402
import sea1_author as author  # noqa: E402


class PaletteScale(unittest.TestCase):
    def test_scale_darkens_every_hit_entry_and_keeps_alpha(self):
        palette = np.zeros((256, 4), np.int64)
        palette[:, :3] = (165, 172, 175)
        palette[:, 3] = np.arange(256)
        hit = np.ones(256, bool)
        new = palette.copy()
        num, den = author.DIGIT_SCALE
        new[hit, :3] = (palette[hit, :3] * num + den // 2) // den
        self.assertEqual(new[0, :3].tolist(), [99, 103, 105])
        self.assertEqual(new[:, 3].tolist(), list(range(256)))

    def test_scale_must_darken(self):
        source = (ROOT / "mod_editor/core/nfl2k5_kit_fixes_2026.py").read_text(encoding="utf-8")
        self.assertIn('require(0 < num < den, "a palette scale must darken")', source)
        self.assertEqual(author.DIGIT_SCALE, [3, 5])


class Shapes(unittest.TestCase):
    def test_design_is_mirror_symmetric_about_the_back_centre(self):
        for name, shape in author.design().items():
            pts = {(round(a, 6), round(h, 6)) for a, h in shape}
            self.assertEqual(pts, {(round(-a, 6), round(h, 6)) for a, h in shape}, name)

    def test_upper_line_descends_to_a_v_above_the_band_chevron(self):
        centre = sorted(author.LINE_CENTRE)
        self.assertEqual(centre[0][0], 0)
        self.assertTrue(all(h0 < h1 for (_, h0), (_, h1) in zip(centre, centre[1:])))
        apex_gap = centre[0][1] - author.LINE_HALF - author.BAND_TOP[-1][1]
        self.assertGreater(apex_gap, 3.0)                       # navy between the V and the band's top edge
        for a, h in centre:
            self.assertGreater(h - author.LINE_HALF, author.interp(author.BAND_TOP, a) + 2.0)

    def test_clear_stays_between_band_and_stripe(self):
        clear = author.clear_shape()
        # inside +-8 (the stripe's tip) the clear stops at the upper line's top edge
        for a, h in clear:
            if abs(a) < 7.95:
                self.assertLessEqual(h, author.interp(author.LINE_CENTRE, a) + author.LINE_HALF + 1e-9)
        for a, h in clear:
            self.assertLessEqual(abs(a), author.SPAN)
            self.assertGreaterEqual(h, author.interp(author.BAND_TOP, a))

    def test_crown_copy_mirrors_the_stripe_about_column_162(self):
        (op,) = author.crown_ops()
        x0, y0, x1, y1 = op["src"]
        dx, dy = op["dst"]
        self.assertEqual((op["flip"], dy, y0, y1), ("h", 40, 40, 100))
        self.assertEqual((dx, dx + (x1 - x0)), author.CROWN_COLS)
        # flipped: destination column x takes source column 324 - x
        for x in range(dx, dx + (x1 - x0)):
            self.assertEqual(x1 - 1 - (x - dx), 324 - x)
        self.assertGreaterEqual(dx, 142)                        # the side A island (x <= 140) is left as it is

    def test_painted_shapes_cover_only_the_back_and_the_crown_overlap(self):
        rgba = np.zeros((256, 256, 4), np.uint8)
        rgba[..., :3] = (12, 40, 72)
        rgba[..., 3] = 255
        rgba[40:100, 142:183, :3] = (156, 163, 166)             # a stripe-coloured block
        out, scope = fixes.paint(rgba, author.helmet_ops())
        ys, xs = np.nonzero(scope)
        self.assertTrue(len(xs))
        # every changed texel is in the crown overlap or the back-centre / side-island back regions
        crown = (xs >= 142) & (xs < 156) & (ys >= 40) & (ys < 100)
        back = (xs >= 100) & (xs < 192) & (((ys >= 25) & (ys < 100)) | ((ys >= 120) & (ys < 235)))
        self.assertTrue(np.all(crown | back))

    def test_shapes_file_matches_the_design(self):
        doc = json.loads(author.SHAPES.read_text(encoding="utf-8"))
        want = {k: [[round(a, 3), round(h, 3)] for a, h in v] for k, v in author.design().items()}
        self.assertEqual(doc["design"], want)
        self.assertEqual(set(doc["layers"]), set(want))
        for name, pieces in doc["layers"].items():
            self.assertTrue(pieces, name)
            for piece in pieces:
                self.assertGreaterEqual(len(piece), 3)
                self.assertTrue(all(-2 <= u <= 258 and -2 <= v <= 258 for u, v in piece))


class Data(unittest.TestCase):
    def test_pins_are_complete_and_unique(self):
        doc = fixes.seattle()
        keys = set()
        for row in doc["textures"]:
            self.assertIn(row["kind"], ("txtr", "palette"))
            for key in ("before_sha256", "after_sha256"):
                self.assertRegex(row[key], "^[0-9a-f]{64}$")
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertNotIn((row["selector"], row["chunk"]), keys)
            keys.add((row["selector"], row["chunk"]))
        self.assertEqual(sorted(k for k in keys if k[1] == 12), [("26A0", 12), ("26A4", 12), ("26H0", 12), ("26H4", 12)])
        self.assertEqual(sorted(k for k in keys if k[1] != 12),
                         sorted((s, c) for s in ("26H0", "26H4") for c in range(33, 43)))

    def test_shipped_data_is_exactly_what_the_author_tool_draws(self):
        rows = {(r["selector"], r["chunk"]): r for r in fixes.seattle()["textures"]}
        authored = author.entries()
        self.assertEqual(len(authored), len(rows))
        for entry in authored:
            row = rows[(entry["selector"], entry["chunk"])]
            for key in ("ops", "map", "kind", "texture"):
                self.assertEqual(json.loads(json.dumps(entry.get(key))), row.get(key), (entry["selector"], key))

    def test_helmet_rows_start_from_the_uf2_output(self):
        alts = {(r["selector"], r["chunk"]): r for r in fixes.alternates()["textures"]}
        for r in fixes.seattle()["textures"]:
            if r["chunk"] == 12:
                e = alts[(r["selector"], 12)]
                self.assertEqual((r["before_sha256"], r["offset"], r["length"]),
                                 (e["after_sha256"], e["offset"], e["length"]))

    def test_no_earlier_layer_owns_a_shoulder_digit_here(self):
        earlier = {(r["selector"], r["chunk"]) for doc in (fixes.spec(), fixes.alternates(), fixes.finish())
                   for r in doc["textures"]}
        for r in fixes.seattle()["textures"]:
            if r["chunk"] != 12:
                self.assertNotIn((r["selector"], r["chunk"]), earlier)
        self.assertFalse({s for s in fixes.selectors(fixes.finish())} & set(author.HELMETS))

    def test_documents_are_separate(self):
        self.assertEqual(len({fixes.DATA, fixes.DATA_ALTS, fixes.DATA_UF3, fixes.DATA_SEA1}), 4)
        self.assertEqual(len(fixes.spec()["textures"]), 60)
        self.assertEqual(len(fixes.alternates()["textures"]), 544)

    def test_no_private_paths_in_shipped_files(self):
        for path in (fixes.DATA_SEA1, author.SHAPES):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("/home/", text)
            self.assertNotIn("/media/", text)
            self.assertTrue(text.isascii())


class Refusals(unittest.TestCase):
    def test_unrelated_image_is_skipped_by_studio_but_refused_by_native_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "other.img"
            path.write_bytes(b"other game")
            self.assertEqual(fixes.apply_seattle(path)["state"], "other_image")
            self.assertEqual(path.read_bytes(), b"other game")
            with self.assertRaises(ValueError):
                fixes.apply_seattle(path, strict=True)

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

    def test_build_runs_sea1_after_uf3(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertLess(source.index("kit_fixes.apply_finish(target)"), source.index("kit_fixes.apply_seattle(target)"))
        self.assertLess(source.index("kit_fixes.apply_seattle(target)"), source.index('_core_module("nfl2k5_menu_icon_uf3")'))

    def test_partial_or_foreign_kit_is_left_alone_in_studio_and_refused_strict(self):
        row = [r for r in fixes.seattle()["textures"] if r["kind"] == "palette"][0]
        doc = dict(fixes.seattle(), textures=[row])
        raw = bytes(row["resource_size"])
        with self.assertRaises(ValueError):
            fixes.compile_resource(row["selector"], raw, strict=True, document=doc)


DISC = os.environ.get("NFL2K5_SEA1_DISC")


@unittest.skipUnless(DISC, "set NFL2K5_SEA1_DISC (the v0.6.1 base disc, read only) for native integration")
class NativeDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = fixes.seattle()
        cls.raws, cls.ranges, cls.extents = repair.read_resources(Path(DISC), cls.doc, {})
        cls.compiled = {}
        for selector, raw in cls.raws.items():
            parts, receipt = fixes.compile_resource(selector, raw, strict=True, document=cls.doc)
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
            parts, receipt = fixes.compile_resource(selector, fixed, strict=True, document=self.doc)
            self.assertEqual((parts, receipt["state"]), ([], "applied"))

    def test_shoulder_digits_are_three_fifths_of_the_chest_grey(self):
        from nfl_txtr import parse_chunks
        fixed = self.compiled["26H0"][2]
        chunks = {c.index: c for c in parse_chunks(fixed)}
        for index in range(33, 43):
            c = chunks[index]
            rgba = fixes.texture_rgba(fixed[c.offset:c.end_offset])
            self.assertEqual({tuple(p) for p in rgba[..., :3].reshape(-1, 3).tolist()}, {(99, 103, 105)})
        chest = chunks[17]
        rgba = fixes.texture_rgba(fixed[chest.offset:chest.end_offset])
        self.assertIn((165, 172, 175), {tuple(p) for p in rgba[..., :3].reshape(-1, 3).tolist()})

    def test_no_logo_texels_left_in_the_crown_stripe(self):
        from nfl_txtr import parse_chunks
        for selector in author.HELMETS:
            fixed = self.compiled[selector][2]
            c = [c for c in parse_chunks(fixed) if c.index == 12][0]
            rgba = fixes.texture_rgba(fixed[c.offset:c.end_offset]).astype(int)
            block = rgba[48:92, 142:156, :3]
            mirror = rgba[48:92, 169:183, :3][:, ::-1]
            self.assertEqual(int(np.abs(block - mirror).max()), 0, selector)

    def test_no_other_archive_entry_shares_an_owned_byte(self):
        self.assertEqual(repair.alias_check(self.ranges, self.extents), [])

    def test_no_owned_span_in_pack_0_and_none_overlaps_st1(self):
        self.assertFalse([r for r in self.ranges if r["file"].split("/")[-1] in repair.FORBIDDEN_PACKS])
        self.assertEqual(repair.st1_disjointness(self.ranges)["overlapping_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
