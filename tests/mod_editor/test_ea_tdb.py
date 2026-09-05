"""Tests for the EA ``TDB`` tabular-database package.

Synthetic databases only.  Nothing here reads a disc, a save or a fixture:
every byte a test looks at is one it built, so the suite runs for a contributor
who owns none of the games.

The load-bearing case is the bit order.  Fields are packed
least-significant-bit first both within a byte and within a field, and a reader
that gets that wrong still returns numbers -- plausible ones -- for every row of
every table.  So the order is pinned twice here: once against literal bytes laid
out by hand, and once by round-tripping widths chosen to straddle byte
boundaries.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_tdb  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


#: Widths deliberately chosen so that consecutive fields cross byte boundaries:
#: 3 + 5 fills one byte, then 11 and 14 and 6 leave nothing aligned.
PLAY_FIELDS = [
    ("PPOS", ea_tdb.FIELD_UINT, 5),
    ("ddep", ea_tdb.FIELD_UINT, 3),
    ("PGID", ea_tdb.FIELD_UINT, 11),
    ("PSA0", ea_tdb.FIELD_UINT, 14),
    ("SEYR", ea_tdb.FIELD_SINT, 6),
    ("caya", ea_tdb.FIELD_SINT, 18),
    ("PFNA", ea_tdb.FIELD_STRING, 88),
    ("PLNA", ea_tdb.FIELD_STRING, 104),
    ("PWGT", ea_tdb.FIELD_UINT, 9),
    ("GYTG", ea_tdb.FIELD_FLOAT, 32),
    ("PHSH", ea_tdb.FIELD_BINARY, 32),
]

PLAY_ROWS = [
    {"PPOS": 0, "ddep": 0, "PGID": 0, "PSA0": 0, "SEYR": 0, "caya": 0,
     "PFNA": "", "PLNA": "", "PWGT": 0, "GYTG": 0.0, "PHSH": b"\x00\x00\x00\x00"},
    {"PPOS": 31, "ddep": 7, "PGID": 2047, "PSA0": 16383, "SEYR": 31,
     "caya": 131071, "PFNA": "Willemijn", "PLNA": "Straddleworth",
     "PWGT": 511, "GYTG": 1000.0, "PHSH": b"\xDE\xAD\xBE\xEF"},
    {"PPOS": 17, "ddep": 5, "PGID": 1234, "PSA0": 9001, "SEYR": -32,
     "caya": -131072, "PFNA": "Ren\xe9", "PLNA": "Bo\xdfmann",
     "PWGT": 300, "GYTG": -17.5, "PHSH": b"\x01\x02\x03\x04"},
    {"PPOS": 1, "ddep": 1, "PGID": 1, "PSA0": 1, "SEYR": -1, "caya": -1,
     "PFNA": "A", "PLNA": "B", "PWGT": 1, "GYTG": 0.5, "PHSH": b"\xFF" * 4},
]

TEAM_FIELDS = [
    ("TDNA", ea_tdb.FIELD_STRING, 136),
    ("TGID", ea_tdb.FIELD_UINT, 10),
    ("TRV1", ea_tdb.FIELD_UINT, 10),
]

TEAM_ROWS = [
    {"TDNA": "Placeholders", "TGID": 1, "TRV1": 700},
    {"TDNA": "Stand-ins", "TGID": 2, "TRV1": 42},
]


def sample_tables():
    return [
        ("PLAY", PLAY_FIELDS, PLAY_ROWS, 64),
        ("TEAM", TEAM_FIELDS, TEAM_ROWS),
    ]


def sample_database() -> bytes:
    return ea_tdb.build_tdb(sample_tables())


class RoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.built = sample_database()
        self.parsed = ea_tdb.parse_tdb(self.built)

    def test_every_value_of_every_type_comes_back(self) -> None:
        for index, row in enumerate(PLAY_ROWS):
            with self.subTest(record=index):
                for name, expected in row.items():
                    read = self.parsed.value("PLAY", index, name)
                    if isinstance(expected, bytes):
                        expected = expected.hex()
                    self.assertEqual(read, expected, name)

    def test_negative_signed_fields_survive(self) -> None:
        # A SINT is sign-extended here, so the top bit reads negative rather
        # than as a large magnitude.  The season-year field is the documented
        # case: six bits covering -32..+31.
        self.assertEqual(self.parsed.value("PLAY", 2, "SEYR"), -32)
        self.assertEqual(self.parsed.value("PLAY", 3, "SEYR"), -1)
        self.assertEqual(self.parsed.value("PLAY", 2, "caya"), -131072)
        self.assertEqual(self.parsed.value("PLAY", 1, "caya"), 131071)

    def test_the_fields_this_suite_uses_really_do_straddle_bytes(self) -> None:
        # The test above proves nothing about bit order unless the fields are
        # unaligned, so assert that they are.
        table = self.parsed.table("PLAY")
        packed = [f for f in table.fields
                  if f.type_id in (ea_tdb.FIELD_UINT, ea_tdb.FIELD_SINT)]
        unaligned = [f for f in packed if not f.byte_aligned]
        self.assertGreaterEqual(len(unaligned), 4)
        straddling = [f for f in unaligned
                      if f.bit_offset // 8 != (f.bit_end - 1) // 8]
        self.assertGreaterEqual(len(straddling), 2)

    def test_text_is_decoded_latin_1_and_cut_at_its_terminator(self) -> None:
        self.assertEqual(self.parsed.value("PLAY", 2, "PFNA"), "Ren\xe9")
        self.assertEqual(self.parsed.value("PLAY", 3, "PLNA"), "B")
        self.assertEqual(self.parsed.value("PLAY", 0, "PFNA"), "")

    def test_a_high_byte_in_text_is_never_an_error(self) -> None:
        # utf-8 would raise on these; EA stored 8-bit characters, so a reader
        # that raises has turned a legible row into a failure.
        built = ea_tdb.build_tdb([("PLAY", [("PFNA", ea_tdb.FIELD_STRING, 32)],
                                   [{}], 1)])
        raw = bytearray(built)
        table = ea_tdb.parse_tdb(bytes(raw)).table("PLAY")
        start = table.records_offset
        raw[start:start + 4] = b"\xFF\xFE\x80\x00"
        self.assertEqual(ea_tdb.parse_tdb(bytes(raw)).value("PLAY", 0, "PFNA"),
                         "\xff\xfe\x80")

    def test_floats_are_read_little_endian(self) -> None:
        self.assertEqual(self.parsed.value("PLAY", 1, "GYTG"), 1000.0)
        self.assertEqual(self.parsed.value("PLAY", 2, "GYTG"), -17.5)

    def test_a_row_covers_every_field_of_the_table(self) -> None:
        table = self.parsed.table("PLAY")
        row = self.parsed.row(table, 1)
        self.assertEqual(sorted(row), sorted(table.field_names))
        self.assertEqual(row["PGID"], 2047)
        self.assertEqual(row["PLNA"], "Straddleworth")

    def test_a_record_slice_is_exactly_the_declared_stride(self) -> None:
        table = self.parsed.table("PLAY")
        for index in range(table.current_records):
            with self.subTest(record=index):
                self.assertEqual(len(self.parsed.record_bytes(table, index)),
                                 table.record_bytes)

    def test_a_table_or_a_field_may_be_named_or_handed_over(self) -> None:
        table = self.parsed.table("TEAM")
        field = table.field("TRV1")
        self.assertEqual(self.parsed.value("TEAM", 0, "TRV1"), 700)
        self.assertEqual(self.parsed.value(table, 0, field), 700)
        self.assertEqual(self.parsed.value(table, 0, "TRV1"), 700)


class BitOrderTests(unittest.TestCase):
    """The one decision that silently corrupts everything if it is wrong."""

    def test_bits_are_packed_least_significant_first_within_a_byte(self) -> None:
        # Two fields inside one byte: a 3-bit at offset 0 and a 5-bit at
        # offset 3.  LSB-first puts the second field in the byte's HIGH bits,
        # so 5 and 9 become 0b01001_101 = 0x4D.  MSB-first would write 0xB1.
        built = ea_tdb.build_tdb([
            ("BITS", [("aaaa", ea_tdb.FIELD_UINT, 3),
                      ("bbbb", ea_tdb.FIELD_UINT, 5)],
             [{"aaaa": 5, "bbbb": 9}]),
        ])
        parsed = ea_tdb.parse_tdb(built)
        record = parsed.record_bytes("BITS", 0)
        self.assertEqual(record[0], 0x4D)
        self.assertEqual(parsed.value("BITS", 0, "aaaa"), 5)
        self.assertEqual(parsed.value("BITS", 0, "bbbb"), 9)

    def test_a_field_that_crosses_a_byte_takes_the_low_bits_of_the_next(self) -> None:
        # A 12-bit field at bit 4: the low nibble of byte 0 is unused, the
        # field's low 4 bits are its high nibble, and its high 8 bits are all
        # of byte 1.  0xABC at offset 4 is therefore C0 AB.
        built = ea_tdb.build_tdb([
            ("BITS", [("pad0", ea_tdb.FIELD_UINT, 4),
                      ("wide", ea_tdb.FIELD_UINT, 12)],
             [{"pad0": 0, "wide": 0xABC}]),
        ])
        parsed = ea_tdb.parse_tdb(built)
        self.assertEqual(parsed.record_bytes("BITS", 0)[:2], b"\xC0\xAB")
        self.assertEqual(parsed.value("BITS", 0, "wide"), 0xABC)

    def test_a_signed_field_stores_twos_complement(self) -> None:
        built = ea_tdb.build_tdb([
            ("BITS", [("sign", ea_tdb.FIELD_SINT, 6),
                      ("pad1", ea_tdb.FIELD_UINT, 2)],
             [{"sign": -1, "pad1": 0}]),
        ])
        parsed = ea_tdb.parse_tdb(built)
        self.assertEqual(parsed.record_bytes("BITS", 0)[0], 0x3F)
        self.assertEqual(parsed.value("BITS", 0, "sign"), -1)


class StructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parsed = ea_tdb.parse_tdb(sample_database())

    def test_the_header_is_read(self) -> None:
        self.assertEqual(self.parsed.version, ea_tdb.TDB_VERSION)
        self.assertEqual(self.parsed.table_count, 2)
        self.assertEqual(len(self.parsed), 2)
        self.assertEqual(self.parsed.preamble_bytes, 0)
        self.assertEqual(self.parsed.table_names, ("PLAY", "TEAM"))

    def test_the_version_word_is_the_bytes_00_08_not_08_00(self) -> None:
        # The one field in the file that is not little-endian.  A reader that
        # takes it as a little-endian word reports 2048 for the same file.
        built = sample_database()
        self.assertEqual(built[2:4], b"\x00\x08")
        self.assertEqual(struct.unpack_from("<H", built, 2)[0], 2048)
        self.assertEqual(ea_tdb.parse_tdb(built).version, 8)

    def test_table_offsets_are_relative_to_the_end_of_the_directory(self) -> None:
        built = sample_database()
        parsed = ea_tdb.parse_tdb(built)
        directory_end = (ea_tdb.TDB_HEADER_SIZE
                         + parsed.table_count * ea_tdb.TDB_TABLE_ENTRY_SIZE)
        self.assertEqual(parsed.directory_end, directory_end)
        first, = struct.unpack_from("<I", built,
                                    ea_tdb.TDB_HEADER_SIZE + 4)
        self.assertEqual(parsed.tables[0].offset, directory_end + first)

    def test_each_table_reports_its_own_geometry(self) -> None:
        play = self.parsed.table("PLAY")
        self.assertEqual(play.current_records, len(PLAY_ROWS))
        self.assertEqual(play.max_records, 64)
        self.assertEqual(play.field_count, len(PLAY_FIELDS))
        self.assertEqual(play.field_names,
                         tuple(spec[0] for spec in PLAY_FIELDS))
        self.assertEqual(play.index_count, 0)

    def test_the_declared_bit_stride_is_one_short_of_the_byte_stride(self) -> None:
        # Measured in 561 of 561 real tables, and reproduced by the builder so
        # a caller comparing the two does not see a spurious difference.
        for table in self.parsed.tables:
            with self.subTest(table=table.name):
                self.assertEqual(table.record_bits, table.record_bytes * 8 - 1)

    def test_no_field_reaches_the_end_of_its_record(self) -> None:
        for table in self.parsed.tables:
            for field in table.fields:
                with self.subTest(table=table.name, field=field.name):
                    self.assertLessEqual(field.bit_end, table.record_bytes * 8)

    def test_byte_aligned_types_are_byte_aligned(self) -> None:
        for table in self.parsed.tables:
            for field in table.fields:
                if field.type_id in ea_tdb.BYTE_ALIGNED_TYPES:
                    with self.subTest(field=field.name):
                        self.assertTrue(field.byte_aligned)
                        self.assertEqual(field.bit_width % 8, 0)

    def test_a_field_names_its_type(self) -> None:
        play = self.parsed.table("PLAY")
        self.assertEqual(play.field("PGID").type_name, "UINT")
        self.assertEqual(play.field("SEYR").type_name, "SINT")
        self.assertEqual(play.field("PFNA").type_name, "STRING")
        self.assertEqual(play.field("GYTG").type_name, "FLOAT")
        self.assertEqual(play.field("PHSH").type_name, "BINARY")
        self.assertIn("unknown type",
                      ea_tdb.TdbField("junk", 9, 0, 1).type_name)

    def test_the_declared_size_ends_four_bytes_past_the_last_table(self) -> None:
        built = sample_database()
        parsed = ea_tdb.parse_tdb(built)
        last = parsed.tables[-1]
        end = (last.records_offset + last.max_records * last.record_bytes)
        self.assertEqual(parsed.db_size, end + 4)
        self.assertEqual(len(built), parsed.db_size)

    def test_every_crc_site_the_builder_writes_is_zero(self) -> None:
        # The builder is a fixture builder: it lays the CRCs out and leaves
        # them zero, which is exactly why nothing it produces will load.
        built = sample_database()
        parsed = ea_tdb.parse_tdb(built)
        self.assertEqual(parsed.checksum, 0)
        for table in parsed.tables:
            with self.subTest(table=table.name):
                self.assertEqual(table.prior_crc, 0)
                self.assertEqual(table.header_crc, 0)
        self.assertEqual(built[parsed.db_size - 4:], b"\x00\x00\x00\x00")


class PreambleTests(unittest.TestCase):
    def test_a_preamble_is_skipped_and_reported(self) -> None:
        built = sample_database()
        parsed = ea_tdb.parse_tdb(ea_tdb.PREAMBLE + built)
        self.assertEqual(parsed.preamble_bytes, len(ea_tdb.PREAMBLE))
        self.assertEqual(parsed.table_names, ("PLAY", "TEAM"))
        self.assertEqual(parsed.value("PLAY", 1, "PLNA"), "Straddleworth")

    def test_a_file_without_one_reports_zero(self) -> None:
        self.assertEqual(ea_tdb.parse_tdb(sample_database()).preamble_bytes, 0)

    def test_both_forms_read_identically(self) -> None:
        built = sample_database()
        plain = ea_tdb.parse_tdb(built)
        prefixed = ea_tdb.parse_tdb(ea_tdb.PREAMBLE + built)
        self.assertEqual(plain.summary()["tables"],
                         prefixed.summary()["tables"])


class ProbeTests(unittest.TestCase):
    def test_a_real_header_is_recognised_with_and_without_a_preamble(self) -> None:
        built = sample_database()
        self.assertTrue(ea_tdb.looks_like_tdb(built))
        self.assertTrue(ea_tdb.looks_like_tdb(ea_tdb.PREAMBLE + built))
        self.assertTrue(ea_tdb.looks_like_tdb(built[:ea_tdb.TDB_HEADER_SIZE]))

    def test_random_bytes_are_not_a_database(self) -> None:
        self.assertFalse(ea_tdb.looks_like_tdb(b""))
        self.assertFalse(ea_tdb.looks_like_tdb(b"\x01\x02\x03\x04" * 16))
        self.assertFalse(ea_tdb.looks_like_tdb(b"MMAP" + bytes(60)))

    def test_the_magic_alone_is_not_enough(self) -> None:
        # "DB" is two bytes and coincidences happen; an absurd table count says
        # these are not a database's first bytes.
        head = bytearray(sample_database()[:ea_tdb.TDB_HEADER_SIZE])
        struct.pack_into("<I", head, 0x10, 0xFFFF)
        self.assertFalse(ea_tdb.looks_like_tdb(bytes(head)))
        struct.pack_into("<I", head, 0x10, 0)
        self.assertFalse(ea_tdb.looks_like_tdb(bytes(head)))

    def test_a_truncated_head_is_not_claimed(self) -> None:
        self.assertFalse(
            ea_tdb.looks_like_tdb(sample_database()[:ea_tdb.TDB_HEADER_SIZE - 1]))


class RefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.built = sample_database()
        self.parsed = ea_tdb.parse_tdb(self.built)

    def test_every_refusal_is_a_contract_refusal(self) -> None:
        self.assertTrue(issubclass(ea_tdb.TdbError, Refusal))

    def test_bytes_that_are_not_a_database_are_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.parse_tdb(b"MMAP" + bytes(64))
        self.assertIn("Hand this reader the database itself",
                      str(caught.exception))

    def test_a_truncated_header_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.parse_tdb(self.built[:ea_tdb.TDB_HEADER_SIZE - 2])
        self.assertIn("truncated", str(caught.exception))

    def test_a_truncated_directory_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.parse_tdb(self.built[:ea_tdb.TDB_HEADER_SIZE + 4])
        self.assertIn("truncated", str(caught.exception))

    def test_a_file_cut_off_mid_records_is_refused_not_read_short(self) -> None:
        table = self.parsed.table("PLAY")
        cut = table.records_offset + table.record_bytes
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.parse_tdb(self.built[:cut])
        message = str(caught.exception)
        self.assertIn("PLAY", message)
        self.assertIn("truncated", message)

    def test_an_implausible_table_count_names_the_big_endian_case(self) -> None:
        broken = bytearray(self.built)
        struct.pack_into(">I", broken, 0x10, 2)     # a PS3 file's byte order
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.parse_tdb(bytes(broken))
        message = str(caught.exception)
        self.assertIn("big-endian", message)
        self.assertIn("does not open", message)

    def test_a_table_count_of_zero_is_refused(self) -> None:
        broken = bytearray(self.built)
        struct.pack_into("<I", broken, 0x10, 0)
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.parse_tdb(bytes(broken))

    def test_a_table_offset_outside_the_file_is_refused(self) -> None:
        broken = bytearray(self.built)
        struct.pack_into("<I", broken, ea_tdb.TDB_HEADER_SIZE + 4, 1 << 24)
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.parse_tdb(bytes(broken))
        self.assertIn("relative to the end of the directory",
                      str(caught.exception))

    def test_a_field_that_runs_past_its_record_is_refused(self) -> None:
        broken = bytearray(self.built)
        table = self.parsed.table("PLAY")
        # Widen the last field until it cannot fit in the record.
        base = (table.offset + ea_tdb.TDB_TABLE_HEADER_SIZE
                + (table.field_count - 1) * ea_tdb.TDB_FIELD_SIZE)
        struct.pack_into("<I", broken, base + 12, table.record_bytes * 8)
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.parse_tdb(bytes(broken))
        message = str(caught.exception)
        self.assertIn("PLAY", message)
        self.assertIn("wrong offset", message)

    def test_a_name_that_is_not_four_printable_characters_is_refused(self) -> None:
        broken = bytearray(self.built)
        broken[ea_tdb.TDB_HEADER_SIZE:ea_tdb.TDB_HEADER_SIZE + 4] = b"\x00\x01\x02\x03"
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.parse_tdb(bytes(broken))
        self.assertIn("wrong offset", str(caught.exception))

    def test_an_unknown_table_is_refused_by_name(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            self.parsed.table("ZZZZ")
        message = str(caught.exception)
        self.assertIn("PLAY", message)
        self.assertIn("pass one of those", message)

    def test_an_unknown_field_is_refused_by_name(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            self.parsed.table("PLAY").field("ZZZZ")
        message = str(caught.exception)
        self.assertIn("PGID", message)
        self.assertIn("pass one of those", message)
        with self.assertRaises(ea_tdb.TdbError):
            self.parsed.value("PLAY", 0, "ZZZZ")

    def test_a_field_from_another_table_is_refused(self) -> None:
        stranger = self.parsed.table("TEAM").field("TGID")
        with self.assertRaises(ea_tdb.TdbError) as caught:
            self.parsed.value("PLAY", 0, stranger)
        self.assertIn("does not belong", str(caught.exception))

    def test_a_record_index_outside_the_table_is_refused(self) -> None:
        for index in (-1, len(PLAY_ROWS), 9999):
            with self.subTest(index=index):
                with self.assertRaises(ea_tdb.TdbError) as caught:
                    self.parsed.record_bytes("PLAY", index)
                message = str(caught.exception)
                self.assertIn("has no record", message)
                self.assertIn("it holds %d" % len(PLAY_ROWS), message)
        with self.assertRaises(ea_tdb.TdbError):
            self.parsed.row("PLAY", 400)

    def test_an_unknown_field_type_is_refused_rather_than_guessed(self) -> None:
        broken = bytearray(self.built)
        table = self.parsed.table("PLAY")
        base = table.offset + ea_tdb.TDB_TABLE_HEADER_SIZE
        struct.pack_into("<I", broken, base, 7)
        reparsed = ea_tdb.parse_tdb(bytes(broken))
        with self.assertRaises(ea_tdb.TdbError) as caught:
            reparsed.value("PLAY", 0, "PPOS")
        self.assertIn("not one of the five", str(caught.exception))

    def test_a_misaligned_string_is_refused_rather_than_read_askew(self) -> None:
        broken = bytearray(self.built)
        table = self.parsed.table("PLAY")
        slot = table.field_names.index("PFNA")
        base = (table.offset + ea_tdb.TDB_TABLE_HEADER_SIZE
                + slot * ea_tdb.TDB_FIELD_SIZE)
        struct.pack_into("<I", broken, base + 4,
                         table.field("PFNA").bit_offset - 1)
        reparsed = ea_tdb.parse_tdb(bytes(broken))
        with self.assertRaises(ea_tdb.TdbError) as caught:
            reparsed.value("PLAY", 1, "PFNA")
        self.assertIn("record_bytes()", str(caught.exception))

    def test_the_builder_refuses_a_value_that_does_not_fit(self) -> None:
        for field_type, value in ((ea_tdb.FIELD_UINT, 64),
                                  (ea_tdb.FIELD_UINT, -1),
                                  (ea_tdb.FIELD_SINT, 32),
                                  (ea_tdb.FIELD_SINT, -33)):
            with self.subTest(type=field_type, value=value):
                with self.assertRaises(ea_tdb.TdbError) as caught:
                    ea_tdb.build_tdb([("BITS", [("wide", field_type, 6)],
                                       [{"wide": value}])])
                self.assertIn("does not fit", str(caught.exception))

    def test_the_builder_refuses_text_too_long_for_its_field(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.build_tdb([("PLAY", [("PFNA", ea_tdb.FIELD_STRING, 32)],
                               [{"PFNA": "far too long for four bytes"}])])
        self.assertIn("widen the field", str(caught.exception))

    def test_the_builder_refuses_a_malformed_spec(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.build_tdb([("PLAY", [("PFNA", ea_tdb.FIELD_STRING, 32)])])
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.build_tdb([("TOOLONG", [], [])])
        self.assertIn("four characters", str(caught.exception))
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.build_tdb([("PLAY", [("PFNA", ea_tdb.FIELD_STRING, 30)],
                               [{}])])
        self.assertIn("multiple of 8", str(caught.exception))
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.build_tdb([("PLAY", [("PGID", 9, 4)], [{}])])
        self.assertIn("format defines", str(caught.exception))

    def test_the_builder_refuses_more_rows_than_it_declared_room_for(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.build_tdb([("BITS", [("wide", ea_tdb.FIELD_UINT, 6)],
                               [{"wide": 1}] * 4, 2)])
        self.assertIn("was handed 4", str(caught.exception))


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parsed = ea_tdb.parse_tdb(sample_database())
        self.summary = self.parsed.summary()

    def test_it_serialises_as_json(self) -> None:
        text = json.dumps(self.summary)
        self.assertEqual(json.loads(text), self.summary)

    def test_it_reports_the_shape_and_only_the_shape(self) -> None:
        self.assertEqual(self.summary["version"], ea_tdb.TDB_VERSION)
        self.assertEqual(self.summary["table_count"], 2)
        names = [table["name"] for table in self.summary["tables"]]
        self.assertEqual(names, ["PLAY", "TEAM"])
        play = self.summary["tables"][0]
        self.assertEqual(play["current_records"], len(PLAY_ROWS))
        self.assertEqual(play["max_records"], 64)
        self.assertEqual(play["fields"], list(self.parsed.table("PLAY").field_names))

    def test_it_carries_no_payload(self) -> None:
        # Field and table names are the schema and are allowed; a value read
        # out of a record is not.  Nothing in the summary may be bytes, and no
        # string in it may be one this suite wrote into a row.
        text = json.dumps(self.summary, ensure_ascii=False)
        for row in PLAY_ROWS + TEAM_ROWS:
            for value in row.values():
                # Single characters collide with field names by chance; the
                # distinctive values are the ones worth hunting for.
                if isinstance(value, str) and len(value) >= 4:
                    self.assertNotIn(value, text)

        def walk(node: object) -> None:
            if isinstance(node, dict):
                for key, item in node.items():
                    self.assertIsInstance(key, str)
                    walk(item)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
            else:
                self.assertIsInstance(node, (str, int, float))
                self.assertNotIsInstance(node, (bytes, bytearray))

        walk(self.summary)


class MultipleTableTests(unittest.TestCase):
    def test_tables_do_not_bleed_into_one_another(self) -> None:
        parsed = ea_tdb.parse_tdb(sample_database())
        self.assertEqual(parsed.value("TEAM", 0, "TDNA"), "Placeholders")
        self.assertEqual(parsed.value("TEAM", 1, "TDNA"), "Stand-ins")
        self.assertEqual(parsed.value("TEAM", 1, "TGID"), 2)
        self.assertEqual(parsed.value("PLAY", 1, "PGID"), 2047)

    def test_unused_record_slots_are_allocated_and_not_read(self) -> None:
        parsed = ea_tdb.parse_tdb(sample_database())
        play = parsed.table("PLAY")
        self.assertGreater(play.max_records, play.current_records)
        with self.assertRaises(ea_tdb.TdbError):
            parsed.record_bytes(play, play.current_records)

    def test_a_database_of_one_empty_table_still_round_trips(self) -> None:
        built = ea_tdb.build_tdb([("PLAY", [("PGID", ea_tdb.FIELD_UINT, 15)],
                                   [], 8)])
        parsed = ea_tdb.parse_tdb(built)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed.table("PLAY").current_records, 0)
        self.assertEqual(parsed.table("PLAY").max_records, 8)

    def test_many_tables_keep_their_order_and_their_offsets(self) -> None:
        tables = [("T%03d" % n, [("PGID", ea_tdb.FIELD_UINT, 15)],
                   [{"PGID": n}]) for n in range(40)]
        parsed = ea_tdb.parse_tdb(ea_tdb.build_tdb(tables))
        self.assertEqual(len(parsed), 40)
        for n in range(40):
            with self.subTest(table=n):
                self.assertEqual(parsed.value("T%03d" % n, 0, "PGID"), n)


if __name__ == "__main__":
    unittest.main()
