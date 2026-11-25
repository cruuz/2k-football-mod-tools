"""b81 portrait cutout (owner report 2026-11-25): no shipped Player Card portrait carries a studio wall.

"the rookie photos have a grey background, while the normal images we used have no background. see how this is
jarring in the depth chart" -- the 4,254 fictional draft faces were opaque 128 x 128 pictures.  Every shipped real
portrait and every draft face must now have a transparent border, and a future headshot with an opaque source must not
reach the pack without the cutout step.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "b81"))

import numpy as np  # noqa: E402

from mod_editor.core import nfl2k5_real_portraits as rp  # noqa: E402
from mod_editor.core import nfl2k5_rookie_faces as rf  # noqa: E402
import portrait_cutout as pc  # noqa: E402



def rgba_of(face):
    """128 x 128 x 4 uint8 of a P8 face ((indices, RGBA palette) bytes)."""
    cell, pal = face
    return np.frombuffer(pal, np.uint8).reshape(256, 4)[np.frombuffer(cell, np.uint8).reshape(128, 128)]


def border_report(rgba):
    """(transparent share of the border, alpha mean): a studio wall reads 0 on the border."""
    return pc.border_transparent(rgba), float(rgba[..., 3].mean() / 255.0)


class ShippedRealPortraits(unittest.TestCase):
    """The NFL.com headshots came with a transparent cutout (sources: source_alpha)."""

    @classmethod
    def setUpClass(cls):
        cls.doc = rp.load_manifest()
        cls.faces = dict(rp.faces(cls.doc))

    def test_every_real_portrait_has_a_transparent_border(self):
        bad = []
        for row in self.doc["portraits"]:
            corners, mean = border_report(rgba_of(self.faces[row["id"]]))
            if corners < 0.5 or not 0.1 < mean < 0.97:
                bad.append((row["id"], row["first"], row["last"], round(corners, 2), round(mean, 2)))
        self.assertEqual(bad, [], "a real portrait with an opaque or empty background")

    def test_every_row_says_how_it_was_cut_out(self):
        methods = {r.get("cutout") for r in self.doc["portraits"]}
        self.assertLessEqual(methods, {"source_transparent", pc.METHOD}, methods)
        self.assertNotIn(None, methods)


class ShippedDraftFaces(unittest.TestCase):
    """The fictional draft faces: the grey studio wall is gone, the palettes carry alpha."""

    @classmethod
    def setUpClass(cls):
        cls.bank = rf.load_bank()
        cls.faces = list(rf.bank_faces(cls.bank))

    def test_every_draft_face_is_a_cutout_p8(self):
        self.assertEqual(len(self.faces), len(rf.bank_ids(self.bank)) + len(rf.legacy_ids(self.bank)))
        bad = []
        for pid, face in self.faces:
            if not isinstance(face, tuple):
                bad.append((pid, "opaque"))
                continue
            corners, mean = border_report(rgba_of(face))
            if corners < pc.BORDER_TRANSPARENT_MIN or not 0.1 < mean < 0.97:
                bad.append((pid, round(corners, 2), round(mean, 2)))
        self.assertEqual(bad, [], "a draft face with an opaque or empty background")

    def test_the_face_itself_is_still_there(self):
        """The cutout keeps the head: the middle of every face is opaque."""
        weak = [pid for pid, face in self.faces if (rgba_of(face)[40:100, 40:88, 3] < 250).mean() > 0.06]
        self.assertEqual(weak, [])

    def test_the_bank_names_the_method_per_face(self):
        self.assertEqual({f.get("cutout") for f in self.bank["faces"]}, {pc.METHOD})
        self.assertEqual(self.bank["cutout"]["model"], pc.MODEL)

    def test_a_palette_has_at_most_256_entries_and_indices_fit(self):
        for _pid, face in self.faces[:200]:
            cell, pal = face
            self.assertEqual((len(cell), len(pal)), (16384, 1024))

    def test_the_portrait_writer_puts_the_alpha_into_the_texture(self):
        """build_portraits hands a (indices, RGBA palette) face to its slot: the palette alpha reaches the P8 texture."""
        import struct  # noqa: PLC0415
        from tests.mod_editor.test_b778_rh1_rookie_faces import Portraits  # noqa: PLC0415
        from tools import nfl_txtr as tx  # noqa: PLC0415
        pid, face = self.faces[0]
        names = ["0001", "0102", "8000"]
        template = Portraits._slot("8000", tx)
        record = bytearray(b"CACR" + bytes(0x1C) + "portrait.cdf".encode("utf-16-le").ljust(0x40, b"\0"))
        hashes = sorted(rf.member_hash(n) for n in names)
        record += struct.pack("<II", 3, rf.SLOT) + struct.pack("<3I", *hashes) + bytes(20)
        struct.pack_into("<I", record, 4, len(record) - 32)
        by_hash = {rf.member_hash(n): Portraits._slot(n, tx) for n in names}
        cdf = b"".join(by_hash[h] for h in hashes)
        new_record, new_cdf, added = rf.build_portraits(bytes(record), cdf, [(pid, face)])
        self.assertEqual(added, 1)
        _count, _slot, new_hashes = rf.parse_record(new_record)
        slot = new_cdf[new_hashes.index(rf.member_hash(f"{pid:04d}")) * rf.SLOT:][:rf.SLOT]
        chunk = tx.parse_chunks(bytes(slot[:rf.SPAN]), allow_trailing=True)[0]
        decoded, _ = tx.decode_chunk(bytes(slot[:rf.SPAN]), chunk)
        texture = tx.parse_texture(decoded, chunk)
        base = 32 + chunk.system_bytes
        palette = slot[base + texture.palette_offset:base + texture.palette_offset + 1024]
        alphas = set(palette[3::4])
        self.assertIn(0, alphas, "the wall is transparent in the written texture")
        self.assertIn(255, alphas)


class Tool(unittest.TestCase):
    def test_border_test_tells_a_wall_from_a_cutout(self):
        wall = np.full((128, 128, 4), 255, np.uint8)
        self.assertEqual(pc.border_transparent(wall), 0.0)
        cut = wall.copy()
        cut[:30, :, 3] = 0
        cut[:, :20, 3] = 0
        cut[:, -20:, 3] = 0
        self.assertGreater(pc.border_transparent(cut), pc.BORDER_TRANSPARENT_MIN)
        hair = wall.copy()
        hair[:, :, 3] = 0
        hair[:40, 30:100, 3] = 255                     # big hair off the top edge, wall clear at the sides
        self.assertGreater(pc.border_transparent(hair), 0.7)

    @unittest.skipUnless(__import__("importlib").util.find_spec("scipy"), "scipy not installed")
    def test_clean_drops_speckle_and_fills_holes(self):
        alpha = np.zeros((128, 128), np.float32)
        alpha[30:120, 30:100] = 1.0
        alpha[60:64, 60:64] = 0.0                      # a hole inside the subject (an eye, a tooth)
        alpha[5:8, 5:8] = 1.0                          # a speck far from the subject
        alpha[10, 64] = 0.02                           # wall noise
        out = pc.clean(alpha)
        self.assertEqual(float(out[5:8, 5:8].max()), 0.0)
        self.assertEqual(float(out[60:64, 60:64].min()), 1.0)
        self.assertEqual(float(out[10, 64]), 0.0)
        self.assertEqual(float(out[80, 60]), 1.0)

    def test_audit_finds_every_portrait_cut_out(self):
        for folder in ("nfl2k5_real_portraits", "nfl2k5_rookie_faces"):
            rows = pc.audit_rows(ROOT / "data" / folder)
            self.assertTrue(rows)
            self.assertTrue(all(r[2] >= pc.BORDER_TRANSPARENT_MIN for r in rows), folder)

    @unittest.skipUnless(__import__("importlib").util.find_spec("pymatting"), "pymatting not installed")
    def test_a_solid_pixel_keeps_its_colour_and_an_edge_pixel_loses_the_wall(self):
        wall = (110, 112, 118)
        rgb = np.zeros((32, 32, 3), np.uint8)
        rgb[:] = wall
        rgb[:, 10:] = (150, 90, 60)                    # the subject, brown
        rgb[:, 10] = (130, 100, 90)                    # an edge column: a brown and wall mix
        alpha = np.zeros((32, 32), np.float32)
        alpha[:, 10] = 0.5
        alpha[:, 11:] = 1.0
        fg = pc.foreground(rgb, alpha)
        self.assertEqual(tuple(fg[16, 20]), (150, 90, 60))
        self.assertLess(abs(int(fg[16, 10, 0]) - 150), abs(130 - 150), "the edge pixel moves toward the subject, away from the wall")

    def test_the_headshot_pipeline_refuses_an_opaque_source_without_the_cutout_step(self):
        from tools.b780 import rst2_headshots as hs  # noqa: PLC0415
        row = {"gsis": "00-1", "alpha": [255, 255]}
        self.assertTrue(hs.opaque_without_cutout(row, {}))
        self.assertTrue(hs.opaque_without_cutout(row, {"00-1": {"cutout": "source_transparent"}}))
        self.assertFalse(hs.opaque_without_cutout(row, {"00-1": {"cutout": pc.METHOD}}))
        self.assertFalse(hs.opaque_without_cutout({"gsis": "00-2", "alpha": [0, 255]}, {}))

    def test_pack_reads_the_documented_manifest_shape(self):
        doc = json.loads((rf.DATA_DIR / "bank.json").read_text(encoding="utf-8"))
        for sheet in doc["atlases"]:
            self.assertEqual(rf.sha((rf.DATA_DIR / sheet["file"]).read_bytes()), sheet["sha256"])


if __name__ == "__main__":
    unittest.main()
