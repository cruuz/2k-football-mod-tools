"""Tests for the Midway ``PAK `` reader.  Synthetic packs only: no disc byte enters this file."""

from __future__ import annotations

import io
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import midway_pak as pak  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


OBJECTS = [
    (0x240FA0D0, "alpha", [(0x35B5CD30, "one.dbd", b"D" * 100), (0x1628E992, "one.dbs", b"S" * 5000), (0x0BB5E6AB, "two.rtd", b"\x16" + bytes(63))]),
    (0x3A36D186, "beta", []),
    (0xBD44C854, "gamma", [(0xEAEB4039, "only.sec", b" CES" + bytes(124))]),
]


def _open(blob: bytes, **kw) -> pak.MidwayPak:
    return pak.MidwayPak(io.BytesIO(blob), **kw)


class Layout2005Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.blob = pak.build_pack(OBJECTS, layout=pak.LAYOUT_2005, unlisted=[0x3A36D186])
        self.pack = _open(self.blob)

    def test_the_header_adds_up_and_the_directory_locates_every_object(self) -> None:
        h = self.pack.header
        self.assertEqual(h.body_bytes + h.metadata_offset, len(self.blob))
        self.assertEqual(h.metadata_offset, 2048)
        ids = self.pack.identities()
        self.assertEqual(ids["objects"], 3)
        self.assertEqual(ids["listed_in_metadata"], 2)
        self.assertEqual(ids["unlisted"], ["3a36d186.of"])
        self.assertTrue(ids["first_object_is_first_sector_after_metadata"])
        self.assertTrue(ids["objects_tile_body_to_directory"])
        self.assertTrue(ids["node_table_bytes_is_header_word3"])
        self.assertTrue(ids["name_table_bytes_is_header_word4"])
        self.assertTrue(ids["metadata_leaf_is_metadata_region"])
        self.assertEqual(ids["metadata_slots_copy_object_records"], 2)
        self.assertEqual(ids["record_stem_is_hash"], 3)
        self.assertEqual(ids["layouts"], [pak.LAYOUT_2005])
        self.assertEqual([o.category for o in self.pack.objects], ["alpha", "beta", "gamma"])
        self.assertEqual(self.pack.objects[0].offset, 2048 + pak.round_up(8 + 2 * 2048))

    def test_members_are_named_sized_and_extracted_from_their_records(self) -> None:
        alpha = self.pack.object_named("alpha")
        members = self.pack.load_members(alpha)
        self.assertEqual([m.name for m in members], ["one.dbd", "one.dbs", "two.rtd"])
        self.assertEqual([m.size for m in members], [100, 5000, 64])
        self.assertEqual(members[0].record_offset, alpha.directory_bytes)
        self.assertEqual(self.pack.extract(alpha, members[1]), b"S" * 5000)
        self.assertEqual(self.pack.member_head(alpha, members[2], 4), b"\x16\x00\x00\x00")
        self.assertEqual(alpha.checks["records_agree"], 3)
        self.assertEqual(alpha.checks["tiled"], 3)
        self.assertEqual(alpha.checks["aligned"], 3)
        self.assertTrue(alpha.checks["first_member_at_directory_end"])
        self.assertEqual(alpha.trailing_bytes, 0)
        self.assertEqual(alpha.member("two.rtd").extension, "rtd")
        self.assertEqual(alpha.record.timestamp_words, (0x11223344, 0x08C70000))
        self.assertEqual(members[0].timestamp_words, (0x11223344, 0x08C70000))

    def test_an_object_with_no_members_and_lookups_that_miss(self) -> None:
        beta = self.pack.object_named("beta")
        self.assertEqual(self.pack.load_members(beta), [])
        self.assertFalse(beta.listed)
        self.assertEqual(beta.trailing_bytes, 0)
        with self.assertRaises(Refusal) as caught:
            self.pack.object_named("delta")
        self.assertEqual(str(caught.exception), "the pack has no object whose category is delta")
        with self.assertRaises(Refusal) as caught:
            self.pack.object_named("alpha").member("none.bin")
        self.assertIn("has no member named none.bin", str(caught.exception))

    def test_the_pack_can_sit_inside_a_larger_stream(self) -> None:
        outer = bytes(4096) + self.blob + bytes(1000)
        inner = _open(outer, base=4096, size=len(self.blob))
        inner.load_all()
        self.assertEqual(inner.identities()["objects"], 3)
        self.assertEqual(inner.extract(inner.objects[2], inner.objects[2].members[0])[:4], b" CES")


class Layout2003Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = _open(pak.build_pack(OBJECTS, layout=pak.LAYOUT_2003))

    def test_paths_and_module_strings_are_read_and_checked(self) -> None:
        alpha = self.pack.object_named("alpha")
        members = self.pack.load_members(alpha)
        self.assertEqual(alpha.layout, pak.LAYOUT_2003)
        self.assertEqual(alpha.record.timestamp_words, (2003, 9, 25, 18, 43, 53, 216))
        self.assertEqual(members[0].path, "modules\\240fa0d0\\35b5cd30.mf")
        self.assertEqual(members[0].module, "ResDefaultModule")
        self.assertEqual(members[0].name, "one.dbd")
        self.assertEqual(alpha.checks["paths_match"], 3)
        self.assertEqual(alpha.directory_bytes, pak.round_up(2048 + 3 * 64))
        self.assertTrue(alpha.checks["first_member_at_directory_end"])
        self.assertEqual(self.pack.identities()["layouts"], [pak.LAYOUT_2003])
        self.assertEqual(self.pack.identities()["listed_in_metadata"], 3)


class RefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.blob = bytearray(pak.build_pack(OBJECTS, layout=pak.LAYOUT_2005))

    def test_not_a_pack(self) -> None:
        with self.assertRaises(Refusal) as caught:
            _open(b"PAK " + bytes(4000))
        self.assertEqual(str(caught.exception), "not a Midway PAK: the file does not begin with 'PAK ' as a little-endian word")
        self.assertFalse(pak.looks_like_pak(b"PAK "))
        self.assertTrue(pak.looks_like_pak(b" KAP"))

    def test_a_body_word_that_does_not_add_up(self) -> None:
        struct.pack_into("<I", self.blob, 8, 12345)
        with self.assertRaises(Refusal) as caught:
            _open(bytes(self.blob))
        self.assertIn("body bytes 12345 plus metadata offset 2048 is not the file's", str(caught.exception))

    def test_a_directory_leaf_that_points_past_the_trailer(self) -> None:
        trailer_at = len(self.blob) - 2048
        # the first object leaf is the fourth node; make its size run into the trailer
        struct.pack_into("<I", self.blob, trailer_at + 3 * 16 + 12, len(self.blob))
        with self.assertRaises(Refusal) as caught:
            _open(bytes(self.blob))
        self.assertIn("runs into the directory trailer", str(caught.exception))

    def test_an_object_whose_record_magic_is_wrong(self) -> None:
        first = 2048 + pak.round_up(8 + 3 * 2048)
        self.blob[first + 3] = 0x99
        with self.assertRaises(Refusal) as caught:
            _open(bytes(self.blob))
        self.assertIn("does not begin with a 0x222222xx object record", str(caught.exception))

    def test_a_member_record_that_disagrees_with_its_directory(self) -> None:
        p = _open(bytes(self.blob))
        alpha = p.object_named("alpha")
        record_at = alpha.offset + alpha.directory_bytes
        struct.pack_into("<I", self.blob, record_at + 4, 0xDEADBEEF)
        p = _open(bytes(self.blob))
        with self.assertRaises(Refusal) as caught:
            p.load_members(p.object_named("alpha"))
        self.assertIn("disagrees with its directory entry", str(caught.exception))

    def test_a_layout_mismatch_between_record_and_directory_is_named(self) -> None:
        p = _open(bytes(self.blob))
        alpha = p.object_named("alpha")
        # forge a 2003-style path into the 2005 directory entry: the record still says 2005
        self.blob[alpha.offset + 2048 + 16:alpha.offset + 2048 + 24] = b"modules\\"
        with self.assertRaises(Refusal) as caught:
            _open(bytes(self.blob))
        self.assertIn("directory is the 2003 layout but its record is the 2005 layout", str(caught.exception))

    def test_a_range_outside_the_pack_is_refused(self) -> None:
        p = _open(bytes(self.blob))
        with self.assertRaises(Refusal) as caught:
            p.read(len(self.blob) - 4, 8)
        self.assertIn("lies outside the", str(caught.exception))


class RecordParserTests(unittest.TestCase):
    def test_object_record_layouts_are_told_apart_by_the_triple_offset(self) -> None:
        for layout in (pak.LAYOUT_2005, pak.LAYOUT_2003):
            rec = pak.parse_object_record(pak._object_record(0x0FD26C79, 7, "cheer", layout))
            self.assertEqual((rec.layout, rec.member_count, rec.category, rec.path), (layout, 7, "cheer", "objects\\fd26c79.of"))
            self.assertTrue(rec.stem_matches_hash)
        with self.assertRaises(Refusal) as caught:
            pak.parse_object_record(bytes(2048), "slot 0")
        self.assertIn("does not begin with a 0x222222xx object record", str(caught.exception))

    def test_member_record_layouts(self) -> None:
        a = pak.parse_member_record(pak._member_record(1, 300, "x.rws", pak.LAYOUT_2005, hash2=9, type_word=13), pak.LAYOUT_2005)
        self.assertEqual((a["size"], a["hash2"], a["type_word"], a["name"], a["module"]), (300, 9, 13, "x.rws", ""))
        b = pak.parse_member_record(pak._member_record(1, 300, "x.rws", pak.LAYOUT_2003, module="ResOther"), pak.LAYOUT_2003)
        self.assertEqual((b["name"], b["module"], b["timestamp_words"][0]), ("x.rws", "ResOther", 2003))
        c = pak.parse_member_record(pak._member_record(1, 300, "x.num", pak.LAYOUT_2003, module=""), pak.LAYOUT_2003)
        self.assertEqual(c["module"], "")
        with self.assertRaises(Refusal):
            pak.parse_member_record(bytes(2048), pak.LAYOUT_2005)


if __name__ == "__main__":
    unittest.main()
