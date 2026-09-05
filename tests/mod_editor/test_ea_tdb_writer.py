"""The EA TDB writer: checksums, round-trips and the refusals. No game data.

Every byte these tests read is built here from the format's grammar through
``ea_tdb.build_tdb``; nothing is copied from a disc or a save.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_tdb  # noqa: E402


def sample() -> bytes:
    """A two-table database with every field type and awkward bit widths.

    ``TWIN`` is signed and five bits, ``PGID`` fifteen and ``POVR`` seven, so a
    record's fields straddle byte boundaries in both tables; a writer that
    packs most-significant-bit first, or that forgets to sign-extend, moves a
    neighbouring field and the round-trip test sees it.
    """

    return ea_tdb.build_tdb((
        (
            "TEAM",
            (
                ("TGID", ea_tdb.FIELD_UINT, 11),
                ("TDNA", ea_tdb.FIELD_STRING, 16 * 8),
                ("TWIN", ea_tdb.FIELD_SINT, 5),
                ("TFLT", ea_tdb.FIELD_FLOAT, 32),
                ("TBIN", ea_tdb.FIELD_BINARY, 24),
            ),
            (
                {"TGID": 1, "TDNA": "ALPHA", "TWIN": 3, "TFLT": 1.5,
                 "TBIN": b"\x01\x02\x03"},
                {"TGID": 900, "TDNA": "BETA", "TWIN": -4, "TFLT": -2.25,
                 "TBIN": b"\xff\x00\xaa"},
            ),
            4,
        ),
        (
            "PLAY",
            (
                ("PGID", ea_tdb.FIELD_UINT, 15),
                ("POVR", ea_tdb.FIELD_UINT, 7),
                ("PWGT", ea_tdb.FIELD_UINT, 9),
            ),
            tuple({"PGID": 16384 + n, "POVR": 40 + n, "PWGT": 180 + n}
                  for n in range(4)),
        ),
    ))


class Crc32Mpeg2Tests(unittest.TestCase):
    """The algorithm, against the values the specification publishes."""

    def test_the_published_check_value(self) -> None:
        # CRC-32/MPEG-2's own check vector: the ASCII digits 1..9.
        self.assertEqual(ea_tdb.crc32_mpeg2(b"123456789"), 0x0376E6E7)

    def test_the_empty_string_is_the_initial_value(self) -> None:
        self.assertEqual(ea_tdb.crc32_mpeg2(b""), ea_tdb.CRC_INITIAL)

    def test_it_is_not_reflected_so_it_is_not_the_zip_crc(self) -> None:
        import zlib

        self.assertNotEqual(ea_tdb.crc32_mpeg2(b"123456789"),
                            zlib.crc32(b"123456789") & 0xFFFFFFFF)

    def test_the_table_matches_a_bit_at_a_time_loop(self) -> None:
        """The fast path is the same function the reference writers walk."""

        def slow(data: bytes) -> int:
            register = 0xFFFFFFFF
            for byte in data:
                register ^= byte << 24
                for _ in range(8):
                    register = (((register << 1) ^ ea_tdb.CRC_POLYNOMIAL)
                                if register & 0x80000000 else register << 1) & 0xFFFFFFFF
            return register

        for payload in (b"", b"\x00", b"DB\x00\x08", bytes(range(256)), b"a" * 1000):
            self.assertEqual(ea_tdb.crc32_mpeg2(payload), slow(payload), payload[:8])


class CrcSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = sample()
        self.fixed = ea_tdb.recompute_crcs(self.raw)

    def test_the_fixture_builder_writes_zeros_and_verify_says_so(self) -> None:
        problems = ea_tdb.verify_crcs(self.raw)
        self.assertEqual(len(problems), 6, problems)
        for line in problems:
            self.assertIn("stores 00000000", line)

    def test_recompute_makes_every_site_agree(self) -> None:
        self.assertEqual(ea_tdb.verify_crcs(self.fixed), [])

    def test_recompute_changes_nothing_but_the_slots(self) -> None:
        differing = {index for index in range(len(self.raw))
                     if self.raw[index] != self.fixed[index]}
        slots = {site.offset + step for site in ea_tdb.crc_sites(self.fixed)
                 for step in range(4)}
        self.assertTrue(differing)
        self.assertTrue(differing <= slots, sorted(differing - slots)[:8])
        self.assertEqual(len(self.fixed), len(self.raw))

    def test_the_four_kinds_are_all_there(self) -> None:
        kinds = [site.kind for site in ea_tdb.crc_sites(self.fixed)]
        self.assertEqual(kinds.count(ea_tdb.CRC_SITE_FILE_HEADER), 1)
        self.assertEqual(kinds.count(ea_tdb.CRC_SITE_END_OF_FILE), 1)
        self.assertEqual(kinds.count(ea_tdb.CRC_SITE_TABLE_PRIOR), 2)
        self.assertEqual(kinds.count(ea_tdb.CRC_SITE_TABLE_HEADER), 2)

    def test_the_file_header_site_covers_the_first_twenty_bytes(self) -> None:
        site = next(item for item in ea_tdb.crc_sites(self.fixed)
                    if item.kind == ea_tdb.CRC_SITE_FILE_HEADER)
        self.assertEqual((site.covers_start, site.covers_end, site.offset), (0, 20, 20))
        self.assertEqual(site.computed, ea_tdb.crc32_mpeg2(self.fixed[:20]))

    def test_the_end_of_file_site_sits_at_the_declared_size(self) -> None:
        database = ea_tdb.parse_tdb(self.fixed)
        site = next(item for item in ea_tdb.crc_sites(self.fixed)
                    if item.kind == ea_tdb.CRC_SITE_END_OF_FILE)
        self.assertEqual(site.offset, database.db_size - 4)

    def test_the_first_table_prior_site_covers_the_table_directory(self) -> None:
        database = ea_tdb.parse_tdb(self.fixed)
        site = next(item for item in ea_tdb.crc_sites(self.fixed)
                    if item.kind == ea_tdb.CRC_SITE_TABLE_PRIOR)
        self.assertEqual(site.covers_start, ea_tdb.TDB_HEADER_SIZE)
        self.assertEqual(site.covers_end, database.directory_end)

    def test_one_flipped_record_byte_is_caught_by_name(self) -> None:
        broken = bytearray(self.fixed)
        table = ea_tdb.parse_tdb(self.fixed).table("PLAY")
        broken[table.records_offset] ^= 0xFF
        problems = ea_tdb.verify_crcs(bytes(broken))
        self.assertTrue(problems)
        self.assertTrue(any("end-of-file" in line for line in problems), problems)

    def test_a_preamble_is_carried_through_and_its_sites_shift(self) -> None:
        with_preamble = ea_tdb.PREAMBLE + self.raw
        fixed = ea_tdb.recompute_crcs(with_preamble)
        self.assertEqual(fixed[:len(ea_tdb.PREAMBLE)], ea_tdb.PREAMBLE)
        self.assertEqual(ea_tdb.verify_crcs(fixed), [])
        site = next(item for item in ea_tdb.crc_sites(fixed)
                    if item.kind == ea_tdb.CRC_SITE_FILE_HEADER)
        self.assertEqual(site.offset, len(ea_tdb.PREAMBLE) + 20)

    def test_a_truncated_database_is_refused_rather_than_checksummed(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.crc_sites(self.fixed[:40])


class RoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = ea_tdb.recompute_crcs(sample())
        self.database = ea_tdb.parse_tdb(self.data)

    def test_writing_nothing_but_recomputing_gives_the_same_bytes(self) -> None:
        again = ea_tdb.recompute_crcs(self.data)
        self.assertEqual(again, self.data)

    def test_a_written_value_reads_back_and_nothing_else_moves(self) -> None:
        before = {name: [self.database.row(name, index)
                         for index in range(self.database.table(name).current_records)]
                  for name in ("TEAM", "PLAY")}
        edited = ea_tdb.set_value(self.database, "PLAY", 2, "POVR", 97)
        after = ea_tdb.parse_tdb(edited)
        self.assertEqual(after.value("PLAY", 2, "POVR"), 97)
        self.assertEqual(len(edited), len(self.data))
        self.assertEqual(ea_tdb.verify_crcs(edited), [])
        for name in ("TEAM", "PLAY"):
            for index, row in enumerate(before[name]):
                found = after.row(name, index)
                if (name, index) == ("PLAY", 2):
                    self.assertEqual(found["PGID"], row["PGID"])
                    self.assertEqual(found["PWGT"], row["PWGT"])
                    continue
                self.assertEqual(found, row, f"{name} {index}")

    def test_every_type_survives_a_write(self) -> None:
        wanted = {"TGID": 2047, "TDNA": "OMEGA", "TWIN": -16, "TFLT": -0.5,
                  "TBIN": b"\x10\x20\x30"}
        edited = ea_tdb.write_records(self.database, "TEAM", {0: dict(wanted)})
        after = ea_tdb.parse_tdb(edited)
        self.assertEqual(after.value("TEAM", 0, "TGID"), 2047)
        self.assertEqual(after.value("TEAM", 0, "TDNA"), "OMEGA")
        self.assertEqual(after.value("TEAM", 0, "TWIN"), -16)
        self.assertEqual(after.value("TEAM", 0, "TFLT"), -0.5)
        self.assertEqual(after.value("TEAM", 0, "TBIN"), "102030")
        self.assertEqual(after.row("TEAM", 1), self.database.row("TEAM", 1))

    def test_a_signed_field_at_its_extremes_round_trips(self) -> None:
        for value in (-16, -1, 0, 15):
            edited = ea_tdb.set_value(self.database, "TEAM", 1, "TWIN", value)
            self.assertEqual(ea_tdb.parse_tdb(edited).value("TEAM", 1, "TWIN"), value)

    def test_writing_the_same_value_back_gives_the_same_file(self) -> None:
        edited = ea_tdb.set_value(self.database, "PLAY", 0, "POVR",
                                  self.database.value("PLAY", 0, "POVR"))
        self.assertEqual(edited, self.data)

    def test_a_shorter_string_is_padded_so_the_reader_cuts_at_its_terminator(self) -> None:
        edited = ea_tdb.set_value(self.database, "TEAM", 0, "TDNA", "AB")
        after = ea_tdb.parse_tdb(edited)
        self.assertEqual(after.value("TEAM", 0, "TDNA"), "AB")
        field = after.table("TEAM").field("TDNA")
        record = after.record_bytes("TEAM", 0)
        start = field.bit_offset // 8
        self.assertEqual(record[start:start + field.bit_width // 8],
                         b"AB" + bytes(14))

    def test_two_records_in_one_call_both_land(self) -> None:
        edited = ea_tdb.write_records(self.database, "PLAY",
                                      {0: {"POVR": 11}, 3: {"PWGT": 511}})
        after = ea_tdb.parse_tdb(edited)
        self.assertEqual(after.value("PLAY", 0, "POVR"), 11)
        self.assertEqual(after.value("PLAY", 3, "PWGT"), 511)
        self.assertEqual(after.value("PLAY", 1, "POVR"), 41)

    def test_a_record_offset_points_at_the_record_the_reader_returns(self) -> None:
        start = self.database.record_offset("PLAY", 2)
        stride = self.database.table("PLAY").record_bytes
        self.assertEqual(self.data[start:start + stride],
                         self.database.record_bytes("PLAY", 2))

    def test_recompute_can_be_declined_so_a_stale_file_can_be_built(self) -> None:
        stale = ea_tdb.set_value(self.database, "PLAY", 0, "POVR", 12, recompute=False)
        self.assertEqual(ea_tdb.parse_tdb(stale).value("PLAY", 0, "POVR"), 12)
        self.assertTrue(ea_tdb.verify_crcs(stale))


class RefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = ea_tdb.recompute_crcs(sample())
        self.database = ea_tdb.parse_tdb(self.data)

    def test_every_refusal_is_a_contract_refusal(self) -> None:
        from mod_editor.games.contract import Refusal

        self.assertTrue(issubclass(ea_tdb.TdbError, Refusal))

    def test_a_value_too_wide_for_its_field_is_refused_with_the_range(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.set_value(self.database, "PLAY", 0, "POVR", 128)
        self.assertIn("0..127", str(caught.exception))

    def test_a_negative_value_in_an_unsigned_field_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.set_value(self.database, "PLAY", 0, "POVR", -1)

    def test_a_signed_field_still_has_a_floor(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.set_value(self.database, "TEAM", 0, "TWIN", -17)

    def test_text_in_a_number_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.set_value(self.database, "PLAY", 0, "POVR", "88")
        self.assertIn("pass an int", str(caught.exception))

    def test_a_bool_is_not_an_int_here(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.set_value(self.database, "PLAY", 0, "POVR", True)

    def test_a_number_in_a_text_field_is_written_as_its_own_text(self) -> None:
        edited = ea_tdb.set_value(self.database, "TEAM", 0, "TDNA", 42)
        self.assertEqual(ea_tdb.parse_tdb(edited).value("TEAM", 0, "TDNA"), "42")

    def test_text_too_long_for_its_field_is_refused_with_the_length(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.set_value(self.database, "TEAM", 0, "TDNA", "X" * 17)
        self.assertIn("16 byte(s)", str(caught.exception))

    def test_text_outside_the_encoding_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.set_value(self.database, "TEAM", 0, "TDNA", "中")
        self.assertIn("latin-1", str(caught.exception))

    def test_binary_too_long_for_its_field_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.set_value(self.database, "TEAM", 0, "TBIN", b"\x00" * 4)

    def test_a_record_index_outside_the_table_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.set_value(self.database, "PLAY", 4, "POVR", 50)
        self.assertIn("has no record 4", str(caught.exception))

    def test_an_unknown_field_is_refused_by_name(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.set_value(self.database, "PLAY", 0, "ZZZZ", 1)
        self.assertIn("no field 'ZZZZ'", str(caught.exception))

    def test_an_unknown_table_is_refused_by_name(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.set_value(self.database, "ZZZZ", 0, "POVR", 1)

    def test_writing_no_record_at_all_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.write_records(self.database, "PLAY", {})
        self.assertIn("nothing to write", str(caught.exception))

    def test_a_non_integer_record_index_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.write_records(self.database, "PLAY", {"0": {"POVR": 1}})

    def test_a_field_that_is_not_a_mapping_is_refused(self) -> None:
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.write_records(self.database, "PLAY", {0: 88})

    def test_a_field_from_another_table_is_refused(self) -> None:
        other = self.database.table("TEAM").field("TGID")
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.set_value(self.database, "PLAY", 0, other, 1)

    def test_a_string_that_is_not_byte_aligned_cannot_be_written(self) -> None:
        skewed = ea_tdb.TdbField("TDNA", ea_tdb.FIELD_STRING, 3, 16)
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.encode_field(skewed, bytes(8), "AB")
        self.assertIn("byte boundary", str(caught.exception))

    def test_a_field_wider_than_the_record_is_refused(self) -> None:
        oversize = ea_tdb.TdbField("PGID", ea_tdb.FIELD_UINT, 0, 96)
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.encode_field(oversize, bytes(4), 1)
        self.assertIn("does not belong to this table", str(caught.exception))

    def test_an_unknown_field_type_is_refused_rather_than_guessed(self) -> None:
        strange = ea_tdb.TdbField("PGID", 9, 0, 8)
        with self.assertRaises(ea_tdb.TdbError):
            ea_tdb.encode_field(strange, bytes(4), 1)

    def test_a_database_whose_tables_are_out_of_order_is_refused(self) -> None:
        """A data block runs to the next table, so file order has to hold."""

        scrambled = bytearray(self.data)
        first = ea_tdb.TDB_HEADER_SIZE
        second = first + ea_tdb.TDB_TABLE_ENTRY_SIZE
        one = struct.unpack_from("<I", scrambled, first + 4)[0]
        two = struct.unpack_from("<I", scrambled, second + 4)[0]
        struct.pack_into("<I", scrambled, first + 4, two)
        struct.pack_into("<I", scrambled, second + 4, one)
        with self.assertRaises(ea_tdb.TdbError) as caught:
            ea_tdb.crc_sites(bytes(scrambled))
        self.assertIn("not in the order", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
