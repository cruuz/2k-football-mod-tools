"""fn2 (b776): Bears/Chiefs nameplate letters on their retail structure, and the redrawn Titans 7."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from mod_editor.core import nfl2k5_glyph_fixes_2026 as glyphs
from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba

LETTERS = "'-ABCDEFGHIJKLMNOPQRSTUVWXYZc"
TEN_SEVEN = [[0, 0], [60, 0], [60, 32.7], [45.3, 80], [51, 80], [51, 100], [14, 100], [14, 80], [24.3, 80],
             [42, 23], [19, 23], [19, 33], [0, 33]]


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Palette(unittest.TestCase):
    def test_retint_maps_the_retail_line_onto_the_kit_line_and_clears_to_the_outline(self):
        palette = np.array([[192, 56, 0, 255], [0, 25, 51, 255], [96, 40, 25, 128], [33, 33, 33, 0],
                            [255, 153, 107, 255]], np.int64)
        out = glyphs.retint_palette(palette, (192, 56, 0), (0, 25, 51), (200, 56, 3), (13, 26, 50))
        self.assertEqual(out[0].tolist(), [200, 56, 3, 255])          # retail outline -> kit outline
        self.assertEqual(out[1].tolist(), [13, 26, 50, 255])          # retail fill -> kit fill
        self.assertEqual(out[2, 3], 128)                                # alpha kept
        self.assertTrue(np.all(np.abs(out[2, :3] - [106, 41, 26]) <= 1))  # the blend stays a blend
        self.assertEqual(out[3].tolist(), [200, 56, 3, 0])            # clear entries fade in the outline colour
        self.assertEqual(out[4].tolist(), [200, 56, 3, 255])          # a highlight beyond the outline clamps to it

    def test_identical_retail_colours_are_refused(self):
        with self.assertRaises(ValueError):
            glyphs.retint_palette(np.zeros((256, 4), np.int64), (1, 2, 3), (1, 2, 3), (0, 0, 0), (9, 9, 9))


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = glyphs.spec()

    def test_only_the_known_spans_are_owned(self):
        owned = {(r["selector"], r["chunk"], r["kind"]) for r in self.doc["textures"]}
        names = {(s, 43, "names_retint") for s in ("05A0", "05H0", "05A4", "05H4", "13A0", "13H0")}
        sevens = {(s, c, "digit_png") for s in ("28H0", "28A0") for c in (20, 40)}
        # b776-ku1: the 2026 Chiefs numbers (jersey 13..22 and shoulder 33..42 on both kits): the retail digits re-tinted
        chiefs = {(s, c, "digit_retint") for s in ("13H0", "13A0") for c in (*range(13, 23), *range(33, 43))}
        self.assertEqual(owned, names | sevens | chiefs)
        for row in self.doc["textures"]:
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            if row["kind"] in ("names_retint", "digit_retint"):
                self.assertEqual(row["retail_selector"], row["selector"])   # NAME metrics equal the same retail kit
        bears = {r["selector"]: r for r in self.doc["textures"] if r["selector"] in ("05A0", "05H0")}
        # 2025/26 Bears: road navy letters, home white letters, both with the orange the numbers use
        self.assertEqual((bears["05A0"]["fill"], bears["05A0"]["outline"]), ("#0D1A32", "#C83803"))
        self.assertEqual((bears["05H0"]["fill"], bears["05H0"]["outline"]), ("#FFFFFF", "#C83803"))

    def test_shipped_digit_art_is_pinned_and_as_authored(self):
        from PIL import Image
        for row in self.doc["textures"]:
            if row["kind"] != "digit_png":
                continue
            path = glyphs.ART / row["png"]
            self.assertEqual(sha(path.read_bytes()), row["png_sha256"])
            with Image.open(path) as im:
                self.assertEqual(im.mode, "RGBA")
                self.assertEqual(im.info.get("nfl2k5_digit_registration"), "as_authored")
                self.assertEqual(im.size, (64, 64) if row["chunk"] == 20 else (32, 32))

    def test_team_spec_holds_the_redrawn_seven(self):
        spec = json.loads((ROOT / "data/nfl2k5_teams_2026/TEN.json").read_text())
        for side in ("home", "away"):
            for family in ("digits", "arm_digits"):
                self.assertEqual(spec["kits"][side][family]["glyph_shapes"]["7"]["contours"], [TEN_SEVEN])

    def test_seven_stem_has_a_constant_width_and_no_step_in(self):
        pts = dict(enumerate(TEN_SEVEN))
        # stem edges: right (60,32.7)->(45.3,80), left (42,23)->(24.3,80)
        (rx0, ry0), (rx1, ry1) = pts[2], pts[3]
        (lx1, ly1), (lx0, ly0) = pts[8], pts[9]
        slope_r = (rx1 - rx0) / (ry1 - ry0)
        slope_l = (lx1 - lx0) / (ly1 - ly0)
        self.assertAlmostEqual(slope_r, slope_l, places=2)
        width = lambda y: (rx0 + slope_r * (y - ry0)) - (lx0 + slope_l * (y - ly0))
        self.assertAlmostEqual(width(ry0), width(80), places=1)
        self.assertGreater(width(ry0), 20)
        self.assertEqual(pts[1], [60, 0])        # the right edge runs straight from the bar into the stem
        self.assertEqual(pts[2][0], 60)

    def test_packaging_and_build_order(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text().split("\n")
        for path in ["mod_editor/core/nfl2k5_glyph_fixes_2026.py", "data/nfl2k5_glyph_fixes_2026.json",
                     *("data/nfl2k5_glyph_fixes_2026/" + r["png"] for r in self.doc["textures"] if r.get("png"))]:
            self.assertIn(path, allow)
        text = (ROOT / "mod_editor/core/mod_build.py").read_text()
        self.assertLess(text.index("kit_fixes.apply_overlaps(target)"), text.index("glyph_fixes.apply_to_image(target"))
        self.assertLess(text.index("glyph_fixes.apply_to_image(target"), text.index('_core_module("nfl2k5_pants_hem_2026")'))
        self.assertIn('"mod_editor.core.nfl2k5_glyph_fixes_2026"',
                      (ROOT / "packaging/check_2k5_mod_studio_runtime.py").read_text())

    def test_not_an_image_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            junk = Path(tmp) / "junk.iso"
            junk.write_bytes(b"not a disc")
            self.assertEqual(glyphs.apply_to_image(junk)["state"], "other_image")
            self.assertEqual(junk.read_bytes(), b"not a disc")
            with self.assertRaises(ValueError):
                glyphs.apply_to_image(junk, strict=True)


def _read_kits(disc, selectors):
    from nfl2k5_playbook_position_recode import OuterImage
    from nfl_uniform_inventory import logical_name_candidates
    cand = logical_name_candidates()
    out = {}
    with OuterImage(Path(disc)) as image:
        for entry in image.entries:
            if entry.name_id in cand and cand[entry.name_id].name[:-4] in selectors:
                out[cand[entry.name_id].name[:-4]] = image.read(entry.virtual_offset, entry.size)
    return out


def _fixture(directory, raws):
    """Real kit packages in a tiny native extracted pack set (ov1's layout), not a disc copy."""
    from nfl_uniform_inventory import logical_name_candidates
    ids = {v.name[:-4]: k for k, v in logical_name_candidates().items()}
    payload, entries = bytearray(), []
    for sel, raw in sorted(raws.items()):
        entries.append((ids[sel], len(raw), 1 + len(payload) // 2048))
        payload.extend(raw)
        payload.extend(bytes((-len(payload)) % 2048))
    table = bytearray(2048)
    struct.pack_into("<III", table, 0, len(entries), 0, 2)
    struct.pack_into("<II", table, 12, 1, len(payload) // 2048)
    for i, entry in enumerate(entries):
        struct.pack_into("<III", table, bump.INDEX_HEADER_SIZE + i * 12, *entry)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "0").write_bytes(table)
    (directory / "1").write_bytes(payload)


def _names_rgba(span):
    chunk = parse_chunks(span)[0]
    decoded, _ = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    return np.frombuffer(texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(32, 1024, 4)


@unittest.skipUnless(os.environ.get("NFL2K5_FN2_DISC") and os.environ.get("NFL2K5_FN2_RETAIL"),
                     "set NFL2K5_FN2_DISC (the b775 disc) and NFL2K5_FN2_RETAIL for read-only native checks")
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = glyphs.spec()
        sels = glyphs.selectors(cls.doc)
        cls.raws = _read_kits(os.environ["NFL2K5_FN2_DISC"], set(sels))
        cls.retail = _read_kits(os.environ["NFL2K5_FN2_RETAIL"], set(sels))
        cls.compiled = {}
        for sel in sels:
            parts, receipt = glyphs.compile_resource(sel, cls.raws[sel], document=cls.doc, retail_kits=cls.retail)
            buf = bytearray(cls.raws[sel])
            for at, data in parts:
                buf[at:at + len(data)] = data
            cls.compiled[sel] = bytes(buf)

    def test_only_owned_spans_change(self):
        for sel, new in self.compiled.items():
            old = self.raws[sel]
            self.assertEqual(len(old), len(new))
            owned = [(r["offset"], r["offset"] + r["length"]) for r in self.doc["textures"] if r["selector"] == sel]
            mask = np.zeros(len(old), bool)
            for a, b in owned:
                mask[a:b] = True
            diff = np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8)
            self.assertFalse(diff[~mask].any(), sel)
            self.assertTrue(diff[mask].any(), sel)

    def test_letters_have_fill_and_counters(self):
        for row in self.doc["textures"]:
            if row["kind"] != "names_retint":
                continue
            raw = self.compiled[row["selector"]]
            names = glyphs._chunk_for(raw, 43)
            meta = glyphs._chunk_for(raw, 44)
            body = raw[meta.body_offset:meta.end_offset]
            metrics = [struct.unpack_from("<HH", body, 0x2C + i * 4) for i in range(29)]
            rgba = _names_rgba(raw[names.offset:names.end_offset]).astype(np.int64)
            fill = np.array(glyphs.hex_rgb(row["fill"]))
            near_fill = (np.abs(rgba[..., :3] - fill).max(axis=2) <= 24) & (rgba[..., 3] >= 128)
            for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                x, w = metrics[LETTERS.index(ch)]
                self.assertGreater(int(near_fill[:, x:x + w].sum()), 30, (row["selector"], ch))  # b775: I had 0
            x, w = metrics[LETTERS.index("W")]
            cell = near_fill[:, x:x + w]
            # the W's strokes are separated over much of its height (its counters are back; b775 had 1 or 2 rows)
            runs = [int((r[1:] & ~r[:-1]).sum() + r[0]) for r in cell]
            self.assertGreaterEqual(sum(1 for v in runs if v >= 2), 8, row["selector"])

    def test_digits_equal_the_studio_import_of_the_shipped_art(self):
        for row in self.doc["textures"]:
            if row["kind"] != "digit_png":
                continue
            raw = self.compiled[row["selector"]]
            span = raw[row["offset"]:row["offset"] + row["length"]]
            self.assertEqual(sha(span), row["after_sha256"])
            chunk = parse_chunks(span)[0]
            decoded, _ = decode_chunk(span, chunk)
            self.assertEqual(parse_texture(decoded, chunk).name, row["texture"])

    def test_replay_is_zero_bytes_and_foreign_art_is_refused(self):
        for sel, new in self.compiled.items():
            parts, receipt = glyphs.compile_resource(sel, new, document=self.doc, retail_kits=self.retail)
            self.assertEqual((parts, receipt["changed_bytes"]), ([], 0))
            row = next(r for r in self.doc["textures"] if r["selector"] == sel)
            bad = bytearray(self.raws[sel])
            bad[row["offset"] + 40] ^= 1
            with self.assertRaisesRegex(ValueError, "unknown input hashes"):
                glyphs.compile_resource(sel, bytes(bad), document=self.doc, retail_kits=self.retail)
            parts, receipt = glyphs.compile_resource(sel, bytes(bad), document=self.doc, retail_kits=self.retail,
                                                     strict=False)
            self.assertIn(row["chunk"], receipt["skipped_textures"])

    def test_without_the_retail_disc_the_letters_are_skipped_not_guessed(self):
        parts, receipt = glyphs.compile_resource("05A0", self.raws["05A0"], document=self.doc, retail_kits=None,
                                                 strict=False)
        self.assertEqual((parts, receipt["skipped_textures"]), ([], [43]))
        with self.assertRaisesRegex(ValueError, "retail nameplate donor is absent"):
            glyphs.compile_resource("05A0", self.raws["05A0"], document=self.doc, retail_kits=None)

    def test_image_writer_and_replay_equal_compiled_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, retail = Path(tmp) / "target", Path(tmp) / "retail"
            _fixture(target, self.raws)
            _fixture(retail, self.retail)
            first = glyphs.apply_to_image(target, lambda: retail, strict=True)
            self.assertEqual(first["written_spans"], len(self.doc["textures"]))
            self.assertEqual(glyphs.apply_to_image(target, retail, strict=True)["written_bytes"], 0)
            with bump._Image.open(target, writable=False) as image:
                index = bump._parsed_index(image)
                for entry in index.entries:
                    sel = bump.logical_name_for(entry.name_id)[:-4]
                    self.assertEqual(image.read_segments(index.sub_extents(entry, 0, entry.size)), self.compiled[sel])


if __name__ == "__main__":
    unittest.main()
