"""The Midway stored-ZIP reader and its ``.ZIH`` index, on sources this file builds.

No game data: every ZIP, every index and every payload here is built by
``blitz_zip``'s own synthetic builders or by this file.  What is proved:

* both index shapes parse, and each refuses a header word that lies;
* the index and the archive agree on names, sizes, data offsets and CRC-32s;
* a same-length member replacement rewrites the member and **all three** CRC-32
  sites, and the pair still agrees afterwards;
* a replacement of any other length is refused naming the byte count;
* a compressed member, a truncated archive and a mismatched index are refused.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest
import zipfile
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import blitz_zip  # noqa: E402

MEMBERS = [
    ("a/one.rtd", b"\x16\x00\x00\x00" + bytes(40)),
    ("b/two.ini", b"key = value\r\nsecond = line\r\n"),
    ("c/three.trv", bytes(80)),
    ("zz/last.dff", b"\x10\x00\x00\x00" + bytes(24)),
]


def _reader(blob: bytes):
    return lambda offset, length: blob[offset:offset + length]


class ReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.blob = blitz_zip.build_synthetic_zip(MEMBERS)
        self.archive = blitz_zip.read_zip(_reader(self.blob), len(self.blob))

    def test_every_member_is_stored_and_addressable(self) -> None:
        self.assertEqual([member.name for member in self.archive.members],
                         [name for name, _payload in MEMBERS])
        for name, payload in MEMBERS:
            self.assertEqual(self.archive.member_bytes(name), payload)
            self.assertEqual(self.archive.member(name).size, len(payload))
            self.assertEqual(self.archive.member(name).crc32,
                             zlib.crc32(payload) & 0xFFFFFFFF)

    def test_a_python_zipfile_reads_the_same_archive(self) -> None:
        import io

        with zipfile.ZipFile(io.BytesIO(self.blob)) as handle:
            self.assertEqual([info.filename for info in handle.infolist()],
                             [name for name, _payload in MEMBERS])
            for name, payload in MEMBERS:
                self.assertEqual(handle.read(name), payload)

    def test_both_index_shapes_describe_the_archive(self) -> None:
        for shape in (blitz_zip.SHAPE_INLINE, blitz_zip.SHAPE_TABLE):
            index = blitz_zip.read_index(blitz_zip.build_synthetic_index(self.blob, shape=shape))
            self.assertEqual(index.shape, shape)
            self.assertEqual(len(index.entries), len(MEMBERS))
            self.assertEqual(index.declared_body_bytes + blitz_zip.ZIH_HEADER_BYTES,
                             index.total_bytes)
            self.assertEqual(index.has_crc_column, shape == blitz_zip.SHAPE_INLINE)
            report = blitz_zip.cross_check(index, self.archive, crc_sample=len(MEMBERS))
            self.assertTrue(report["names_match_as_sets"])
            self.assertEqual(report["sizes_agree"], len(MEMBERS))
            self.assertEqual(report["data_offsets_agree"], len(MEMBERS))
            self.assertTrue(report["index_order_is_by_name"])
            self.assertTrue(report["zip_order_is_by_data_offset"])
            if shape == blitz_zip.SHAPE_INLINE:
                self.assertEqual(report["crc_column_agrees"], len(MEMBERS))
                self.assertEqual(report["crc_recomputed_agrees"], report["crc_recomputed"])

    def test_the_index_points_one_local_header_past_the_signature(self) -> None:
        index = blitz_zip.read_index(blitz_zip.build_synthetic_index(self.blob))
        for entry in index.entries:
            start = entry.data_offset - blitz_zip.LOCAL_HEADER_BYTES - len(entry.name)
            self.assertEqual(self.blob[start:start + 4], b"PK\x03\x04")
            name_len, extra_len = struct.unpack_from("<HH", self.blob, start + 26)
            self.assertEqual(extra_len, 0)
            self.assertEqual(self.blob[start + 30:start + 30 + name_len].decode("latin-1"),
                             entry.name)


class RefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.blob = blitz_zip.build_synthetic_zip(MEMBERS)

    def test_an_index_whose_body_word_lies_is_refused(self) -> None:
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.read_index(b"\x02\x00\x00\x00" + bytes(28))
        self.assertIn("body bytes", str(caught.exception))

    def test_an_index_declaring_no_entries_is_refused(self) -> None:
        with self.assertRaises(blitz_zip.BlitzZipError):
            blitz_zip.read_index(struct.pack("<II", 0, 12) + bytes(12))

    def test_a_short_file_is_refused(self) -> None:
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.read_index(b"\x00" * 8)
        self.assertIn("too short", str(caught.exception))

    def test_a_compressed_member_is_refused_by_name(self) -> None:
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as handle:
            handle.writestr("packed.ini", b"x" * 4096)
        packed = buffer.getvalue()
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.read_zip(_reader(packed), len(packed))
        self.assertIn("every member of the Midway ZIP is stored", str(caught.exception))

    def test_a_file_with_no_end_record_is_refused(self) -> None:
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.read_zip(_reader(b"not a zip" * 64), 9 * 64)
        self.assertIn("end-of-central-directory", str(caught.exception))

    def test_a_central_directory_that_runs_past_the_file_is_refused(self) -> None:
        blob = bytearray(self.blob)
        eocd = blob.rfind(b"PK\x05\x06")
        struct.pack_into("<I", blob, eocd + 12, 1 << 24)     # declared directory bytes
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.read_zip(_reader(bytes(blob)), len(blob))
        self.assertIn("truncated", str(caught.exception))

    def test_a_member_pointing_away_from_its_local_header_is_refused(self) -> None:
        blob = bytearray(self.blob)
        central = blob.rfind(b"PK\x01\x02")
        struct.pack_into("<I", blob, central + 42, 3)        # local header offset
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.read_zip(_reader(bytes(blob)), len(blob))
        self.assertIn("not a local file header", str(caught.exception))


class WriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.blob = blitz_zip.build_synthetic_zip(MEMBERS)
        self.archive = blitz_zip.read_zip(_reader(self.blob), len(self.blob))
        self.index_blob = blitz_zip.build_synthetic_index(self.blob)
        self.index = blitz_zip.read_index(self.index_blob)

    def test_a_same_length_replacement_rewrites_three_crc_sites(self) -> None:
        payload = b"key = OTHER\r\nsecond = LINE\r\n"
        original = self.archive.member_bytes("b/two.ini")
        self.assertEqual(len(payload), len(original))
        plan = blitz_zip.plan_member_replacement(self.archive, self.index, "b/two.ini", payload)
        self.assertEqual(len(plan.zip_ranges), 3)          # payload, local CRC, central CRC
        self.assertEqual(len(plan.index_ranges), 1)        # the index's CRC column
        self.assertEqual(plan.crc32, zlib.crc32(payload) & 0xFFFFFFFF)
        self.assertNotEqual(plan.crc32, plan.previous_crc32)

        zip_blob, index_blob = bytearray(self.blob), bytearray(self.index_blob)
        blitz_zip.apply_member_replacement(zip_blob, index_blob, plan)
        self.assertEqual(len(zip_blob), len(self.blob))
        self.assertEqual(len(index_blob), len(self.index_blob))

        after = blitz_zip.read_zip(_reader(bytes(zip_blob)), len(zip_blob))
        after_index = blitz_zip.read_index(bytes(index_blob))
        self.assertEqual(after.member_bytes("b/two.ini"), payload)
        self.assertEqual(after.member("b/two.ini").crc32, plan.crc32)
        self.assertEqual(after_index.entry("b/two.ini").crc32, plan.crc32)
        report = blitz_zip.cross_check(after_index, after, crc_sample=len(MEMBERS))
        self.assertEqual(report["crc_column_agrees"], len(MEMBERS))
        self.assertEqual(report["crc_recomputed_agrees"], report["crc_recomputed"])
        for name, original_payload in MEMBERS:
            if name != "b/two.ini":
                self.assertEqual(after.member_bytes(name), original_payload)

    def test_the_table_shaped_index_has_no_crc_range_to_write(self) -> None:
        index_blob = blitz_zip.build_synthetic_index(self.blob, shape=blitz_zip.SHAPE_TABLE)
        index = blitz_zip.read_index(index_blob)
        plan = blitz_zip.plan_member_replacement(self.archive, index, "c/three.trv", b"y" * 80)
        self.assertEqual(plan.index_ranges, ())
        zip_blob = bytearray(self.blob)
        blitz_zip.apply_member_replacement(zip_blob, None, plan)
        after = blitz_zip.read_zip(_reader(bytes(zip_blob)), len(zip_blob))
        self.assertEqual(after.member_bytes("c/three.trv"), b"y" * 80)

    def test_any_other_length_is_refused_naming_the_byte_count(self) -> None:
        for payload in (b"short", b"x" * 4096):
            with self.assertRaises(blitz_zip.BlitzZipError) as caught:
                blitz_zip.plan_member_replacement(self.archive, self.index, "b/two.ini", payload)
            self.assertIn("bytes on the disc", str(caught.exception))
            self.assertIn(str(len(payload)), str(caught.exception))

    def test_an_unknown_member_is_refused(self) -> None:
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.plan_member_replacement(self.archive, self.index, "no/such.ini", b"")
        self.assertIn("not a member of this archive", str(caught.exception))

    def test_an_index_that_disagrees_with_the_archive_stops_the_edit(self) -> None:
        blob = bytearray(self.index_blob)
        entry = self.index.entry("b/two.ini")
        struct.pack_into("<I", blob, entry.record_offset + 7 * 4, entry.size + 1)
        bad = blitz_zip.read_index(bytes(blob))
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.plan_member_replacement(self.archive, bad, "b/two.ini", b"x" * entry.size)
        self.assertIn("the pair disagrees", str(caught.exception))

    def test_applying_a_plan_to_the_wrong_buffer_is_refused(self) -> None:
        plan = blitz_zip.plan_member_replacement(self.archive, self.index, "b/two.ini",
                                                 b"z" * len(MEMBERS[1][1]))
        with self.assertRaises(blitz_zip.BlitzZipError):
            blitz_zip.apply_member_replacement(bytearray(16), bytearray(self.index_blob), plan)
        with self.assertRaises(blitz_zip.BlitzZipError) as caught:
            blitz_zip.apply_member_replacement(bytearray(self.blob), None, plan)
        self.assertIn("no index buffer was given", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
