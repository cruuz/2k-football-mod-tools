"""b779-pt1: real official-headshot Player Card portraits for the created real free agents."""
from __future__ import annotations

import io
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_real_portraits as rp  # noqa: E402
from mod_editor.core import nfl2k5_rookie_faces as rf  # noqa: E402
from tests.mod_editor.test_b778_rh1_rookie_faces import Portraits  # noqa: E402


class Manifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = rp.load_manifest()

    def test_ids_are_in_their_own_window(self):
        ids = rp.portrait_ids(self.doc)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), list(range(rp.ID_BASE, rp.ID_BASE + len(ids))))
        self.assertLess(max(ids), rp.ID_LIMIT)
        self.assertLess(max(ids), 65536)

    def test_window_cannot_collide_with_other_portrait_users(self):
        """Retail 0..9507, coaches 7000..7037, the rookie bank (1000..21695), the alien (1947) and every no-photo
        selector (7100, 21696..23086) all sit below the window; the u16 holds it."""
        self.assertGreater(rp.ID_BASE, rf.ID_END)
        self.assertGreater(rp.ID_BASE, 23086)
        bank = rf.bank_ids(rf.load_bank())
        self.assertFalse(set(bank) & set(rp.portrait_ids(self.doc)))

    def test_every_player_is_identified_and_sourced(self):
        gsis = set()
        for r in self.doc["portraits"]:
            self.assertRegex(r["gsis_id"], r"^00-\d{7}$")
            self.assertNotIn(r["gsis_id"], gsis)
            gsis.add(r["gsis_id"])
            self.assertTrue(r["first"] and r["last"] and 1 <= r["birth_month"] <= 12 and 1 <= r["birth_day"] <= 31)
            self.assertTrue(r["source_url"].startswith(("https://static.www.nfl.com/", "https://a.espncdn.com/")))
            self.assertEqual(len(r["source_sha256"]), 64)
            self.assertIn(r["group"], ("free_agent", "refresh_created"))
            self.assertIn(r["review"], ("ok", "ok_flagged"))
        self.assertEqual(len(gsis), len(self.doc["portraits"]))

    def test_no_reference_photo_ships(self):
        """Only the 128x128 P8 atlases and the manifest are in the data folder."""
        names = sorted(p.name for p in rp.DATA_DIR.iterdir())
        self.assertEqual(names[0], "faces_00.png")
        self.assertTrue(all(n == "portraits.json" or n.startswith("faces_") for n in names), names)
        for sheet in self.doc["atlases"]:
            self.assertEqual(rp.sha((rp.DATA_DIR / sheet["file"]).read_bytes()), sheet["sha256"])

    def test_kaepernick_is_the_facing_camera_espn_headshot(self):
        rows = [r for r in self.doc["portraits"] if r["gsis_id"] == "00-0027974"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_url"], "https://a.espncdn.com/i/headshots/nfl/players/full/14001.png")


class Faces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = rp.load_manifest()
        cls.faces = rp.faces(cls.doc)

    def test_every_face_is_p8_with_soft_alpha(self):
        self.assertEqual(len(self.faces), len(self.doc["portraits"]))
        for pid, (idx, pal) in self.faces:
            self.assertEqual((len(idx), len(pal)), (128 * 128, 1024))
            self.assertLess(max(idx) if idx else 0, 256)
        pid, (idx, pal) = self.faces[0]
        alphas = {pal[4 * i + 3] for i in set(idx)}
        self.assertIn(0, alphas, "the cutout background is transparent like the retail portraits")
        self.assertGreater(len(alphas), 2, "soft edge alpha is kept")

    def test_faces_look_like_portraits(self):
        """Each cutout has a transparent border and an opaque face area (not blank, not a full-frame fill)."""
        for pid, (idx, pal) in self.faces:
            alpha = bytes(pal[4 * i + 3] for i in idx)
            opaque = sum(1 for a in alpha if a >= 200) / len(alpha)
            self.assertGreater(opaque, 0.25, pid)
            self.assertLess(opaque, 0.995, pid)
            self.assertGreater(len({idx[i] for i in range(0, len(idx), 7)}), 30, pid)

    def test_record_growth_with_p8_faces(self):
        """The portrait record takes already-P8 faces next to the bank and keeps every slot byte-exact: the slot
        decodes back to the very indices and palette that shipped (decode round trip)."""
        from tools import nfl_txtr as tx
        names = ["0001", "0102", "8000"]
        record = bytearray(b"CACR" + bytes(0x1C) + "portrait.cdf".encode("utf-16-le").ljust(0x40, b"\0"))
        hashes = sorted(rf.member_hash(n) for n in names)
        record += struct.pack("<II", 3, rf.SLOT) + struct.pack("<3I", *hashes) + bytes(20)
        struct.pack_into("<I", record, 4, len(record) - 32)
        by_hash = {rf.member_hash(n): Portraits._slot(n, tx) for n in names}
        cdf = b"".join(by_hash[h] for h in hashes)
        take = self.faces[:3]
        new_record, new_cdf, added = rf.build_portraits(bytes(record), cdf, take)
        self.assertEqual(added, 3)
        count, slot, new_hashes = rf.parse_record(new_record)
        self.assertEqual(count, 6)
        index = {h: i for i, h in enumerate(new_hashes)}
        for pid, (idx, pal) in take:
            i = index[rf.member_hash(f"{pid:04d}")]
            s = new_cdf[i * rf.SLOT:(i + 1) * rf.SLOT]
            self.assertEqual(rf.slot_name(s), str(pid))
            chunk = tx.parse_chunks(s[:rf.SPAN], allow_trailing=True)[0]
            decoded, _ = tx.decode_chunk(s[:rf.SPAN], chunk)
            tex = tx.parse_texture(decoded, chunk)
            video = decoded[chunk.system_bytes:]
            self.assertEqual(tx.unswizzle_2d(video[tex.pixel_offset:tex.pixel_offset + 16384], 128, 128, 1), idx)
            pal_bgra = video[tex.palette_offset:tex.palette_offset + 1024]
            self.assertEqual(b"".join(pal_bgra[4 * k + 2:4 * k + 3] + pal_bgra[4 * k + 1:4 * k + 2] + pal_bgra[4 * k:4 * k + 1]
                                      + pal_bgra[4 * k + 3:4 * k + 4] for k in range(256)), pal)
        for h, s in by_hash.items():
            i = index[h]
            self.assertEqual(new_cdf[i * rf.SLOT:(i + 1) * rf.SLOT], s)


class Assignment(unittest.TestCase):
    """plan_assignments on a fake roster document: match by first name, surname and birth day, never by slot."""

    class Rec:
        def __init__(self, photo, month, day):
            self.values = {"photo_id": photo}
            self._f = {"birth_month": month, "birth_day": day}

        def get(self, name):
            return self._f.get(name)

    class P:
        def __init__(self, pool, first, last, photo, month, day, offset):
            self.pool, self.first, self.last, self.offset = pool, first, last, offset
            self.record = Assignment.Rec(photo, month, day)

    class Doc:
        def __init__(self, players):
            self.players = players

    def manifest(self):
        return {"portraits": [
            {"id": 30000, "first": "Colin", "last": "Kaepernick", "birth_month": 11, "birth_day": 3},
            {"id": 30001, "first": "Jimmy", "last": "Garoppolo", "birth_month": 11, "birth_day": 2},
            {"id": 30002, "first": "Gone", "last": "Player", "birth_month": 1, "birth_day": 1},
            {"id": 30003, "first": "Same", "last": "Name", "birth_month": 5, "birth_day": 5},
        ]}

    def test_plan(self):
        P = self.P
        doc = self.Doc([P("primary", "Colin", "Kaepernick", 22554, 11, 3, 0x1000),       # no-photo selector: written
                        P("primary", "Jimmy", "Garoppolo", 1532, 11, 2, 0x2000),          # already a real portrait: kept
                        P("primary", "Same", "Name", 7100, 5, 5, 0x3000),
                        P("primary", "Same", "Name", 7100, 5, 5, 0x4000),                 # two matches: ambiguous
                        P("secondary", "Gone", "Player", 22000, 1, 1, 0x5000)])           # secondary pool: ignored
        plan = rp.plan_assignments(doc, self.manifest())
        self.assertEqual(plan["writes"], [(0x1000 + rp.PHOTO_FIELD, 30000, "Colin Kaepernick")])
        self.assertEqual(plan["kept"], ["Jimmy Garoppolo"])
        self.assertEqual(plan["ambiguous"], ["Same Name"])
        self.assertEqual(plan["missing"], ["Gone Player"])

    def test_index_shift_does_not_matter(self):
        P = self.P
        for offset in (0x1000, 0x9000):
            doc = self.Doc([P("primary", "Colin", "Kaepernick", 22554, 11, 3, offset)])
            plan = rp.plan_assignments(doc, self.manifest())
            self.assertEqual(plan["writes"][0][0], offset + rp.PHOTO_FIELD)

    def test_selector_ranges(self):
        for photo, expect in ((7100, True), (21696, True), (23086, True), (7099, False), (8000, False),
                              (10000, False), (21695, False), (0, False)):
            self.assertEqual(rp._selector(photo), expect, photo)


if __name__ == "__main__":
    unittest.main()
