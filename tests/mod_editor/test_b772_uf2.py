"""uf2: 2026 alternate, throwback and Rivalries kit fixes. New art operations, the second data document, the new
chunk kinds (palette-only, cleared TV digits, Unif facemask), refusals and the in-place native repair."""
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
from tools.b77 import uf2_repair as repair  # noqa: E402
import uf2_author as author  # noqa: E402


def canvas(h=16, w=16, colour=(10, 20, 30), alpha=255):
    a = np.zeros((h, w, 4), np.uint8)
    a[..., :3] = colour
    a[..., 3] = alpha
    return a


class NewArt(unittest.TestCase):
    def test_ring_takes_the_inner_border_of_a_shape(self):
        a = canvas()
        a[4:12, 4:12, :3] = (200, 0, 0)
        out, scope = fixes.paint(a, [{"op": "ring", "box": [0, 0, 16, 16], "inside": ["#C80000"], "from": 0,
                                      "to": 1.5, "color": "#FFFFFF"}])
        self.assertEqual(int(scope.sum()), 28)
        self.assertEqual(out[4, 4, :3].tolist(), [255, 255, 255])
        self.assertEqual(out[6, 6, :3].tolist(), [200, 0, 0])
        # "opaque" rings follow the alpha edge (digits on a transparent field); ``to`` None fills the interior
        d = canvas(alpha=0)
        d[4:12, 4:12, 3] = 255
        out, scope = fixes.paint(d, [{"op": "ring", "box": [0, 0, 16, 16], "inside": "opaque", "from": 1.5,
                                      "to": None, "color": "#FFFFFF"}])
        self.assertEqual(int(scope.sum()), 36)
        self.assertTrue((out[..., 3] == d[..., 3]).all())

    def test_inverted_ring_outlines_everything_but_the_field(self):
        a = canvas(colour=(209, 79, 24))
        a[6:10, 6:10, :3] = (11, 22, 42)
        out, scope = fixes.paint(a, [{"op": "ring", "box": [0, 0, 16, 16], "inside": ["#D14F18"], "invert": True,
                                      "from": 0, "to": 1.3, "color": "#FFFFFF", "tolerance": 30}])
        self.assertEqual(int(scope.sum()), 12)

    def test_halo_stays_outside_the_shape(self):
        a = canvas()
        a[4:12, 4, :3] = a[4:12, 11, :3] = a[4, 4:12, :3] = a[11, 4:12, :3] = (255, 255, 255)
        out, scope = fixes.paint(a, [{"op": "halo", "box": [0, 0, 16, 16], "edge": ["#FFFFFF"], "radius": 1.0,
                                      "color": "#FF0000"}])
        self.assertEqual(out[7, 7, :3].tolist(), [10, 20, 30])           # the inside is not reached
        self.assertEqual(out[7, 3, :3].tolist(), [255, 0, 0])
        self.assertEqual(int(scope.sum()), 32)

    def test_close_fills_gaps_between_lines(self):
        a = canvas()
        for x in (4, 6, 8):
            a[4:12, x, :3] = (0, 0, 0)
        out, scope = fixes.paint(a, [{"op": "close", "box": [0, 0, 16, 16], "colors": ["#000000"], "tolerance": 4,
                                      "radius": 1.5, "color": "#050505"}])
        self.assertEqual(out[8, 5, :3].tolist(), [5, 5, 5])
        self.assertEqual(out[8, 2, :3].tolist(), [10, 20, 30])

    def test_stamp_resamples_exactly_skips_and_remaps(self):
        src = canvas(8, 8, (0, 0, 255))
        src[:4, :, :3] = (255, 255, 255)
        out, scope = fixes.paint(canvas(), [{"op": "stamp", "donor": 3, "src": [0, 0, 8, 8], "dst": [0, 0, 4, 4],
                                             "skip": ["#0000FF"]}], {3: src})
        self.assertEqual(out[0, 0, :3].tolist(), [255, 255, 255])
        self.assertEqual(out[3, 0, :3].tolist(), [10, 20, 30])
        self.assertEqual(int(scope.sum()), 8)
        out, _ = fixes.paint(canvas(), [{"op": "stamp", "donor": 3, "src": [8, 0, 0, 8], "dst": [0, 0, 8, 8],
                                         "remap": [{"from": ["#FFFFFF"], "to": "#00FF00"}]}], {3: src})
        self.assertEqual(out[0, 0, :3].tolist(), [0, 255, 0])
        self.assertEqual(out[7, 7, :3].tolist(), [0, 0, 255])
        with self.assertRaisesRegex(ValueError, "donor texture absent"):
            fixes.paint(canvas(), [{"op": "stamp", "donor": 9, "src": [0, 0, 8, 8], "dst": [0, 0, 4, 4]}])

    def test_lift_poly_only_and_inverted_enclosed(self):
        a = canvas(colour=(100, 100, 100))
        out, _ = fixes.paint(a, [{"op": "lift", "box": [0, 0, 16, 16], "from": ["#646464"], "tolerance": 2,
                                  "keep": [2, 5]}])
        self.assertEqual(out[0, 0, :3].tolist(), [193, 193, 193])
        b = canvas()
        b[:, 8:, :3] = (200, 0, 0)
        out, _ = fixes.paint(b, [{"op": "poly", "color": "#FFFFFF", "points": [[0, 0], [16, 0], [16, 16], [0, 16]],
                                  "only": ["#C80000"]}])
        self.assertEqual(out[0, 0, :3].tolist(), [10, 20, 30])
        self.assertEqual(out[0, 9, :3].tolist(), [255, 255, 255])
        c = canvas(colour=(209, 79, 24))
        c[4:12, 4:12, :3] = (0, 0, 0)
        c[6:10, 6:10, :3] = (209, 79, 24)
        out, scope = fixes.paint(c, [{"op": "enclosed", "box": [0, 0, 16, 16], "edge": ["#D14F18"], "invert": True,
                                      "color": "#0B162A"}])
        self.assertEqual(int(scope.sum()), 16)

    def test_retint_keeps_anti_aliasing_and_multipoly_has_no_seams(self):
        a = canvas(colour=(255, 255, 255))
        a[2, 2, :3] = (14, 40, 120)                       # the mark
        a[2, 3, :3] = (134, 147, 187)                     # half blend with the white field
        a[5, 5, :3] = (0, 200, 0)                         # other art stays
        out, scope = fixes.paint(a, [{"op": "retint", "box": [0, 0, 16, 16], "base": "#FFFFFF", "source": "#0E2878",
                                      "color": "#B81A35"}])
        self.assertEqual(out[2, 2, :3].tolist(), [184, 26, 53])
        self.assertTrue(abs(int(out[2, 3, 0]) - 220) <= 2 and abs(int(out[2, 3, 1]) - 140) <= 2)
        self.assertEqual(out[5, 5, :3].tolist(), [0, 200, 0])
        self.assertEqual(int(scope.sum()), 2)
        cover = fixes.multipolygon_coverage([[[0, 0], [1.5, 0], [1.5, 1], [0, 1]], [[1.5, 0], [3, 0], [3, 1], [1.5, 1]],
                                             [[0, 0], [3, 0], [3, 1], [0, 1]]], 4, 4)
        self.assertEqual(cover[0].tolist(), [16, 16, 16, 0])

    def test_poly_alpha_makes_a_hidden_decal_opaque(self):
        a = canvas(alpha=0)
        out, _ = fixes.paint(a, [{"op": "poly", "color": "#B22234", "alpha": 255,
                                  "points": [[0, 0], [4, 0], [4, 2.25], [0, 2.25]]}])
        self.assertTrue((out[:2, :4, 3] == 255).all())
        self.assertTrue((out[3:, :, 3] == 0).all())

    def test_pair_mud_follows_the_nearest_dirt_ratio(self):
        clean = np.array([[200, 100, 50, 255], [0, 0, 0, 255], [100, 50, 25, 255]], np.int64)
        mud = np.array([[100, 50, 25, 255], [0, 0, 0, 255], [0, 0, 0, 0]], np.int64)
        out = fixes.pair_mud(clean, mud, [2], [0, 1, 2])
        self.assertEqual(out[2].tolist(), [50, 25, 13, 255])


class Data(unittest.TestCase):
    def test_pins_are_complete_and_unique(self):
        doc = fixes.alternates()
        rows = doc["textures"]
        self.assertEqual(len(rows), 544)
        self.assertEqual(len(fixes.selectors(doc)), 92)
        keys = set()
        for row in rows:
            self.assertIn(row["kind"], fixes.KINDS)
            for key in ("before_sha256", "after_sha256"):
                self.assertRegex(row[key], "^[0-9a-f]{64}$")
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertNotIn((row["selector"], row["chunk"]), keys)
            keys.add((row["selector"], row["chunk"]))
            for pin in (row.get("donors") or {}).values():
                self.assertRegex(pin, "^[0-9a-f]{64}$")
        spans = [(r["selector"], r["offset"], r["offset"] + r["length"]) for r in rows]
        for sel in {s for s, _, _ in spans}:
            mine = sorted((a, b) for s, a, b in spans if s == sel)
            for (a0, b0), (a1, _) in zip(mine, mine[1:]):
                self.assertLessEqual(b0, a1)

    def test_shipped_data_is_exactly_what_the_author_tool_draws(self):
        rows = {(r["selector"], r["chunk"]): r for r in fixes.alternates()["textures"]}
        authored = author.entries()
        self.assertEqual(len(authored), len(rows))
        for entry in authored:
            row = rows[(entry["selector"], entry["chunk"])]
            for key in ("ops", "map", "fields", "mip", "kind", "texture"):
                self.assertEqual(json.loads(json.dumps(entry.get(key))), row.get(key), (entry["selector"], key))
            self.assertEqual(sorted(entry.get("donors") or {}), sorted(row.get("donors") or {}))

    def test_every_finding_has_a_row_or_a_reason(self):
        """Every uw2 alternate-kit finding uf2 reviewed is fixed by a row or listed with its reason."""
        covered = {d for r in fixes.alternates()["textures"] for d in r["defects"] if d.startswith("uw2-")}
        reasons = author.VERDICTS
        self.assertFalse(covered & set(reasons))
        self.assertEqual(len(covered) + len(reasons), 232)   # 220 snapshot rows + 12 added by uw2 later

    def test_rows_revising_uf1_start_from_uf1_output(self):
        """Noah's 10/14 items revise four uf1 textures: each starts from uf1's output pin, at the same span."""
        uf1 = {(r["selector"], r["chunk"]): r for r in fixes.spec()["textures"]}
        both = [r for r in fixes.alternates()["textures"] if (r["selector"], r["chunk"]) in uf1]
        self.assertEqual(sorted((r["selector"], r["chunk"]) for r in both),
                         [("18A0", 3), ("26A0", 1), ("26A0", 12), ("26H0", 12)])
        for r in both:
            u = uf1[(r["selector"], r["chunk"])]
            self.assertEqual((r["before_sha256"], r["offset"], r["length"]), (u["after_sha256"], u["offset"], u["length"]))

    def test_uf1_document_is_unchanged(self):
        self.assertEqual(len(fixes.spec()["textures"]), 60)
        self.assertNotEqual(fixes.DATA, fixes.DATA_ALTS)

    def test_no_private_paths_in_data(self):
        text = fixes.DATA_ALTS.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/media/", text)
        self.assertTrue(text.isascii())


def unif_span(facemask=b"\x4a\x17\x0d\xff"):
    body = bytearray(80)
    body[0x30:0x34] = facemask
    header = struct.pack("<4s7I", b"Unif", 80, 0, 0, 0, 0, 0, 0)
    return header + bytes(body)


class Kinds(unittest.TestCase):
    def test_unif_facemask_field(self):
        span = unif_span()
        new, detail = fixes.compile_unif(span, {"fields": {"facemask": "#F2F3F6"}})
        self.assertEqual(len(new), len(span))
        self.assertEqual(new[32 + 0x30:32 + 0x34], bytes((0xF6, 0xF3, 0xF2, 0xFF)))
        self.assertEqual([i for i in range(len(span)) if span[i] != new[i]], [80, 81, 82])
        with self.assertRaisesRegex(ValueError, "already hold"):
            fixes.compile_unif(new, {"fields": {"facemask": "#F2F3F6"}})


class Refusals(unittest.TestCase):
    def test_unrelated_image_is_skipped_by_studio_but_refused_by_native_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "other.img"
            path.write_bytes(b"other game")
            self.assertEqual(fixes.apply_alternates(path)["state"], "other_image")
            self.assertEqual(path.read_bytes(), b"other game")
            with self.assertRaises(ValueError):
                fixes.apply_alternates(path, strict=True)

    def test_native_tool_refuses_a_wrong_disc_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            disc = root / "bad.iso"
            disc.write_bytes(b"not a disc")
            with self.assertRaisesRegex(ValueError, "unexpected disc size"):
                repair.run(SimpleNamespace(disc=disc, receipts=root / "receipts", rollback=False))
            self.assertEqual(disc.read_bytes(), b"not a disc")
            self.assertFalse((root / "receipts").exists())

    def test_repair_keeps_out_of_pack_0_and_st1s_ranges(self):
        self.assertEqual(repair.FORBIDDEN_PACKS, {"0"})
        self.assertEqual(repair.ST1_RANGES, ((98189312, 99736736), (99737600, 101366032)))
        hit = repair.st1_disjointness([dict(start=99736000, end=99738000, selector="x", chunk=1, file="vc_53450030/9")])
        self.assertEqual(hit["overlapping_bytes"], 736 + 400)
        clear = repair.st1_disjointness([dict(start=101366032, end=101366100, selector="x", chunk=1,
                                              file="vc_53450030/9")])
        self.assertEqual((clear["overlapping_bytes"], clear["nearest"]["gap_bytes"]), (0, 0))
        self.assertEqual(repair.UF1_SHA256, "351bf0949d26583ba0cb5fec546069b14f183fbfb1519d543a4bb64f13a13759")

    def test_build_runs_the_alternates_after_the_home_away_pass(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertLess(source.index("kit_fixes.apply_to_image(target)"),
                        source.index("kit_fixes.apply_alternates(target)"))


DISC = os.environ.get("NFL2K5_UF2_DISC")
RECORD = os.environ.get("NFL2K5_UF2_RECORD")


@unittest.skipUnless(DISC and RECORD, "set NFL2K5_UF2_DISC (the repaired disc) and NFL2K5_UF2_RECORD (its receipt "
                                      "folder with the recorded uf1 spans) for native integration")
class NativeDisc(unittest.TestCase):
    SELECTORS = ("05H4", "22A5", "08A5", "10A6", "24A9", "02A3", "37H2", "26A3", "00H6", "00H7")

    @classmethod
    def setUpClass(cls):
        cls.doc = fixes.alternates()
        cls.raws, cls.ranges, cls.extents = repair.read_resources(Path(DISC), cls.doc)
        recorded = (Path(RECORD) / (repair.BACKUP + ".bin")).read_bytes()
        cls.base = repair.originals(cls.raws, cls.ranges, recorded)
        cls.compiled = {}
        for selector in cls.SELECTORS:
            parts, receipt = fixes.compile_resource(selector, cls.base[selector], document=cls.doc)
            out = bytearray(cls.base[selector])
            for at, data in parts:
                out[at:at + len(data)] = data
            cls.compiled[selector] = (parts, receipt, bytes(out))

    def test_compile_matches_pins_the_disc_and_only_owned_bytes_change(self):
        for selector, (parts, receipt, fixed) in self.compiled.items():
            rows = [r for r in self.doc["textures"] if r["selector"] == selector]
            self.assertEqual(len(parts), len(rows))
            owned = set()
            for r in rows:
                owned.update(range(r["offset"], r["offset"] + r["length"]))
                self.assertEqual(fixes.sha(fixed[r["offset"]:r["offset"] + r["length"]]), r["after_sha256"])
            self.assertEqual(fixed, self.raws[selector])
            changed = {i for i, (a, b) in enumerate(zip(self.base[selector], fixed)) if a != b}
            self.assertTrue(changed)
            self.assertFalse(changed - owned)

    def test_replay_is_a_no_op(self):
        for selector, (_, _, fixed) in self.compiled.items():
            parts, receipt = fixes.compile_resource(selector, fixed, document=self.doc)
            self.assertEqual((parts, receipt["state"]), ([], "applied"))

    def test_palette_rows_keep_their_indices_and_cleared_digits_are_transparent(self):
        from nfl_txtr import decode_chunk, parse_chunks, parse_texture
        for selector in ("10A6", "24A9"):
            before = {c.index: c for c in parse_chunks(self.base[selector])}
            after = {c.index: c for c in parse_chunks(self.compiled[selector][2])}
            row = [r for r in self.doc["textures"] if r["selector"] == selector and r["kind"] == "palette"][0]
            b, _ = decode_chunk(self.base[selector], before[row["chunk"]])
            a, _ = decode_chunk(self.compiled[selector][2], after[row["chunk"]])
            t = parse_texture(b, before[row["chunk"]])
            pal = slice(before[row["chunk"]].system_bytes + t.palette_offset,
                        before[row["chunk"]].system_bytes + t.palette_offset + 1024)
            self.assertNotEqual(a[pal], b[pal])
            self.assertEqual(a[:pal.start] + a[pal.stop:], b[:pal.start] + b[pal.stop:])
        fixed = self.compiled["10A6"][2]
        for chunk in [c for c in parse_chunks(fixed) if 33 <= c.index <= 42]:
            decoded, _ = decode_chunk(fixed, chunk)
            t = parse_texture(decoded, chunk)
            planes = fixes.read_planes(decoded, chunk, dict(pixel=t.pixel_offset, width=t.width, height=t.height,
                                                            mips=t.mip_levels))
            palette = fixes.read_palette(decoded, chunk, dict(palette=t.palette_offset))
            self.assertTrue(all((palette[p][..., 3] == 0).all() for p in planes))

    def test_tampered_and_partial_kits_are_refused(self):
        rows = [r for r in self.doc["textures"] if r["selector"] == "05H4"]
        bad = bytearray(self.base["05H4"])
        bad[rows[0]["offset"] + rows[0]["length"] - 1] ^= 1
        with self.assertRaisesRegex(ValueError, "unknown or partially"):
            fixes.compile_resource("05H4", bytes(bad), document=self.doc)
        partial = bytearray(self.base["05H4"])
        at, data = self.compiled["05H4"][0][0]
        partial[at:at + len(data)] = data
        with self.assertRaisesRegex(ValueError, "unknown or partially"):
            fixes.compile_resource("05H4", bytes(partial), document=self.doc)

    def test_studio_keeps_a_users_replaced_stamp_donor(self):
        rows = [r for r in self.doc["textures"] if r["selector"] == "11A3"]
        donor_rows = [r for r in rows if r.get("donors")]
        self.assertTrue(donor_rows)
        user = bytearray(self.base_11a3())
        logo = fixes._chunk_for(bytes(user), 49)
        user[logo.end_offset - 1] ^= 1                                   # the user's own team logo
        parts, receipt = fixes.compile_resource("11A3", bytes(user), strict=False, document=self.doc)
        self.assertEqual(receipt["skipped_textures"], [r["chunk"] for r in donor_rows])
        self.assertEqual(len(parts), len(rows) - len(donor_rows))
        with self.assertRaisesRegex(ValueError, "stamp donor differs"):
            fixes.compile_resource("11A3", bytes(user), strict=True, document=self.doc)

    def base_11a3(self):
        rows = [r for r in self.doc["textures"] if r["selector"] == "11A3"]
        raws, ranges, _ = repair.read_resources(Path(DISC), dict(self.doc, textures=rows))
        all_ranges = self.ranges
        recorded = (Path(RECORD) / (repair.BACKUP + ".bin")).read_bytes()
        pieces, at = [], 0
        for r in all_ranges:
            n = r["end"] - r["start"]
            if r["selector"] == "11A3":
                pieces.append(recorded[at:at + n])
            at += n
        return repair.originals(raws, ranges, b"".join(pieces))["11A3"]

    def test_no_other_archive_entry_shares_an_owned_byte(self):
        self.assertEqual(repair.alias_check(self.ranges, self.extents), [])

    def test_no_owned_span_in_pack_0_and_none_overlaps_st1(self):
        self.assertFalse([r for r in self.ranges if r["file"].split("/")[-1] in repair.FORBIDDEN_PACKS])
        self.assertEqual(repair.st1_disjointness(self.ranges)["overlapping_bytes"], 0)
        self.assertEqual(sorted({r["selector"] for r in self.ranges if r["file"].endswith("/9")}), ["00H6", "00H7"])


if __name__ == "__main__":
    unittest.main()
