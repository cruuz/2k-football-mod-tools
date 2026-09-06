"""Tests for the EA ``BIG`` archive package.

Synthetic archives only.  Nothing here reads a disc, a retail file or a
fixture: every byte a test looks at is one it built, so the suite runs for a
contributor who owns none of the games.

The RefPack streams are **composed from the grammar**, opcode by opcode,
rather than pasted in as hex blobs whose provenance nobody can check.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_big  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


# --------------------------------------------------------------------------
# RefPack streams, built from the grammar
# --------------------------------------------------------------------------

def refpack_header(decompressed: int, *, long_sizes: bool = False,
                   compressed: "int | None" = None) -> bytes:
    flags = ea_big.REFPACK_FAMILY
    if long_sizes:
        flags |= ea_big.REFPACK_FLAG_LONG
    if compressed is not None:
        flags |= ea_big.REFPACK_FLAG_COMPRESSED_SIZE
    width = 4 if long_sizes else 3
    out = bytes((flags, ea_big.REFPACK_SIGNATURE))
    if compressed is not None:
        out += compressed.to_bytes(width, "big")
    return out + decompressed.to_bytes(width, "big")


def literal_run(payload: bytes) -> bytes:
    """``0xE0..0xFB``: 4 to 112 literals, in multiples of four, no copy."""
    assert len(payload) % 4 == 0 and 4 <= len(payload) <= 112
    return bytes((0xE0 | ((len(payload) - 4) >> 2),)) + payload


def short_copy(offset: int, length: int, literals: bytes = b"") -> bytes:
    """``0x00..0x7F``: 0-3 literals, offset <= 1,024, length 3-10."""
    assert 0 <= len(literals) <= 3 and 3 <= length <= 10 and 1 <= offset <= 1024
    biased = offset - 1
    first = (((biased >> 8) & 0x03) << 5) | (((length - 3) & 0x07) << 2) | len(literals)
    return bytes((first, biased & 0xFF)) + literals


def medium_copy(offset: int, length: int, literals: bytes = b"") -> bytes:
    """``0x80..0xBF``: 0-3 literals, offset <= 16,384, length 4-67."""
    assert 0 <= len(literals) <= 3 and 4 <= length <= 67 and 1 <= offset <= 16384
    biased = offset - 1
    return (bytes((0x80 | (length - 4),
                   (len(literals) << 6) | ((biased >> 8) & 0x3F),
                   biased & 0xFF)) + literals)


def long_copy(offset: int, length: int, literals: bytes = b"") -> bytes:
    """``0xC0..0xDF``: 0-3 literals, offset <= 131,072, length 5-1,028."""
    assert 0 <= len(literals) <= 3 and 5 <= length <= 1028 and 1 <= offset <= 131072
    biased = offset - 1
    span = length - 5
    first = (0xC0 | ((biased >> 16) << 4) | ((span >> 8) << 2) | len(literals))
    return (bytes((first, (biased >> 8) & 0xFF, biased & 0xFF, span & 0xFF))
            + literals)


def stop(literals: bytes = b"") -> bytes:
    """``0xFC..0xFF``: 0-3 final literals, then the stream ends."""
    assert 0 <= len(literals) <= 3
    return bytes((0xFC | len(literals),)) + literals


class RefpackTests(unittest.TestCase):

    def test_a_literal_run_and_a_terminator_round_trip(self) -> None:
        want = b"abcdefgh" + b"ij"
        stream = refpack_header(len(want)) + literal_run(b"abcdefgh") + stop(b"ij")
        self.assertEqual(ea_big.refpack_decompress(stream), want)

    def test_the_two_byte_opcode_copies_with_overlap(self) -> None:
        # 4 literals, then 5 bytes copied from 4 back: the source and the
        # destination overlap, which is the case a slice copy gets wrong.
        want = b"abcd" + b"abcda"
        stream = (refpack_header(len(want)) + literal_run(b"abcd")
                  + short_copy(4, 5) + stop())
        self.assertEqual(ea_big.refpack_decompress(stream), want)

    def test_the_three_byte_opcode_carries_its_literals(self) -> None:
        want = b"abcdefgh" + b"xy" + b"abcdefgh"
        stream = (refpack_header(len(want)) + literal_run(b"abcdefgh")
                  + medium_copy(10, 8, b"xy") + stop())
        self.assertEqual(ea_big.refpack_decompress(stream), want)

    def test_the_four_byte_opcode_reaches_the_furthest(self) -> None:
        head = bytes(range(32)) * 4          # 128 bytes, no repeats within 32
        want = head + b"z" + head[:100]
        stream = (refpack_header(len(want))
                  + b"".join(literal_run(head[i:i + 8]) for i in range(0, 128, 8))
                  + long_copy(129, 100, b"z") + stop())
        self.assertEqual(ea_big.refpack_decompress(stream), want)

    def test_four_byte_sizes_and_a_compressed_size_are_both_read(self) -> None:
        want = b"abcdefgh"
        stream = (refpack_header(len(want), long_sizes=True, compressed=99)
                  + literal_run(want) + stop())
        header = ea_big.refpack_header(stream)
        assert header is not None
        self.assertTrue(header.long_sizes)
        self.assertEqual(header.compressed_size, 99)
        self.assertEqual(header.decompressed_size, len(want))
        self.assertEqual(header.header_bytes, 10)
        self.assertEqual(ea_big.refpack_decompress(stream), want)

    def test_a_header_that_disagrees_with_its_own_stream_is_refused(self) -> None:
        stream = refpack_header(99) + literal_run(b"abcd") + stop()
        with self.assertRaises(ea_big.RefpackError) as caught:
            ea_big.refpack_decompress(stream)
        self.assertIn("disagree", str(caught.exception))

    def test_a_truncated_stream_is_refused_not_returned_short(self) -> None:
        want = b"abcdefgh"
        stream = refpack_header(len(want)) + literal_run(b"abcdefgh")
        stream = stream[:-3]
        with self.assertRaises(ea_big.RefpackError):
            ea_big.refpack_decompress(stream)

    def test_a_bounded_read_stops_early_and_tolerates_a_short_front(self) -> None:
        want = b"abcdefgh" * 8
        stream = (refpack_header(len(want))
                  + b"".join(literal_run(want[i:i + 8]) for i in range(0, 64, 8))
                  + stop())
        self.assertEqual(ea_big.refpack_decompress(stream, max_output=5),
                         want[:5])
        # Only the front of the stream -- five header bytes, one opcode and
        # eight literals: bounded mode returns what it produced.
        self.assertEqual(ea_big.refpack_decompress(stream[:14], max_output=64),
                         want[:8])

    def test_a_copy_from_before_the_start_is_refused(self) -> None:
        stream = refpack_header(8) + short_copy(4, 5) + stop()
        with self.assertRaises(ea_big.RefpackError) as caught:
            ea_big.refpack_decompress(stream)
        self.assertIn("damaged or is not RefPack", str(caught.exception))

    def test_bytes_that_are_not_refpack_are_named_as_such(self) -> None:
        self.assertIsNone(ea_big.refpack_header(b"BIGF\x00\x00\x00\x00"))
        self.assertFalse(ea_big.is_refpack(b"BIGF"))
        self.assertTrue(ea_big.is_refpack(bytes((0x10, 0xFB))))
        with self.assertRaises(ea_big.RefpackError) as caught:
            ea_big.refpack_decompress(b"not a stream")
        self.assertIn("0xFB", str(caught.exception))


# --------------------------------------------------------------------------
# The archive
# --------------------------------------------------------------------------

def packed(payload: bytes) -> bytes:
    """*payload* as a RefPack stream of literal runs (no matches)."""
    body = b""
    position = 0
    while len(payload) - position >= 4:
        take = min(112, (len(payload) - position) // 4 * 4)
        body += literal_run(payload[position:position + take])
        position += take
    return refpack_header(len(payload)) + body + stop(payload[position:])


class ArchiveTests(unittest.TestCase):

    def sample(self) -> bytes:
        return ea_big.build_big([
            ("alpha.txt", b"the first entry"),
            ("beta.bin", bytes(range(200))),
            ("gamma.dat", b""),
        ])

    def test_the_header_mixes_byte_orders_the_way_the_discs_do(self) -> None:
        archive = self.sample()
        self.assertEqual(archive[:4], ea_big.BIGF_MAGIC)
        # The length is little-endian ...
        self.assertEqual(struct.unpack_from("<I", archive, 4)[0], len(archive))
        # ... and the count and the table size are big-endian.
        count, index_bytes = struct.unpack_from(">II", archive, 8)
        self.assertEqual(count, 3)
        parsed = ea_big.parse_big(archive)
        self.assertEqual(parsed.index_bytes, index_bytes)
        self.assertEqual(parsed.size_endian, "little")
        self.assertEqual(parsed.declared_size, len(archive))
        self.assertEqual(parsed.size_mismatch, 0)

    def test_entries_come_back_by_index_and_by_name(self) -> None:
        parsed = ea_big.parse_big(self.sample())
        self.assertEqual(len(parsed), 3)
        self.assertEqual([entry.name for entry in parsed],
                         ["alpha.txt", "beta.bin", "gamma.dat"])
        self.assertEqual(parsed.member(0), b"the first entry")
        self.assertEqual(parsed.member("beta.bin"), bytes(range(200)))
        self.assertEqual(parsed.member("gamma.dat"), b"")
        self.assertEqual(parsed.entry("beta.bin").extension, "bin")
        self.assertTrue(parsed.entries[2].empty)

    def test_a_name_that_is_not_there_says_how_many_are(self) -> None:
        parsed = ea_big.parse_big(self.sample())
        with self.assertRaises(Refusal) as caught:
            parsed.member("nothing.bin")
        self.assertIn("has no entry called", str(caught.exception))
        self.assertIn("it has 3", str(caught.exception))

    def test_an_index_past_the_end_is_refused_with_the_range(self) -> None:
        parsed = ea_big.parse_big(self.sample())
        with self.assertRaises(Refusal) as caught:
            parsed.member(9)
        self.assertIn("(0..2)", str(caught.exception))

    def test_a_packed_entry_is_unpacked_by_the_reader(self) -> None:
        payload = b"repeat me " * 40
        archive = ea_big.build_big([("plain.bin", b"stored"),
                                    ("packed.bin", packed(payload))])
        parsed = ea_big.parse_big(archive)
        self.assertFalse(parsed.is_compressed(0))
        self.assertTrue(parsed.is_compressed(1))
        header = parsed.compression(1)
        assert header is not None
        self.assertEqual(header.decompressed_size, len(payload))
        self.assertEqual(parsed.member(1), payload)
        self.assertEqual(parsed.member(1, max_output=6), payload[:6])
        # The stored bytes are the packed ones; the member is the unpacked.
        self.assertNotEqual(parsed.stored(1), payload)

    def test_entry_formats_are_named_after_decompression(self) -> None:
        text = b"a plain text entry\n" * 4
        archive = ea_big.build_big([
            ("t.txt", text),
            ("t.packed", packed(text)),
            ("empty.bin", b""),
            ("bank.ssh", b"SHPS" + b"\x00" * 40),
        ])
        parsed = ea_big.parse_big(archive)
        self.assertEqual(parsed.entry_format(0), ea_big.FORMAT_TEXT)
        # The packed entry's *stored* head is a RefPack header and claims no
        # format; only the decompressed bytes do.
        self.assertEqual(parsed.entry_format(1), ea_big.FORMAT_TEXT)
        self.assertEqual(parsed.entry_format(2), ea_big.FORMAT_EMPTY)
        self.assertEqual(parsed.entry_format(3), "SHPS")

    def test_a_nested_archive_opens_stored_or_packed(self) -> None:
        inner = ea_big.build_big([("leaf.txt", b"a leaf entry")])
        archive = ea_big.build_big([("inner.big", inner),
                                    ("inner2.big", packed(inner))])
        parsed = ea_big.parse_big(archive)
        self.assertEqual(parsed.entry_format(0), "BIGF")
        self.assertEqual(parsed.entry_format(1), "BIGF")
        for index in (0, 1):
            nested = parsed.nested(index)
            self.assertEqual(len(nested), 1)
            self.assertEqual(nested.member(0), b"a leaf entry")
            self.assertIn("!inner", nested.name)
        counts = parsed.format_histogram(follow_nested=True)
        self.assertEqual(counts["BIGF"], 2)
        self.assertEqual(counts["nested:" + ea_big.FORMAT_TEXT], 2)

    def test_a_ranged_reader_opens_an_archive_inside_a_larger_file(self) -> None:
        archive = self.sample()
        blob = b"\x00" * 4096 + archive + b"\xff" * 32

        def read(offset: int, size: int) -> bytes:
            return blob[offset:offset + size]

        parsed = ea_big.parse_big(read, size=len(archive), base=4096,
                                  name="/DATA/SAMPLE.BIG")
        self.assertEqual(parsed.member("alpha.txt"), b"the first entry")
        self.assertEqual(parsed.name, "/DATA/SAMPLE.BIG")

    def test_a_ranged_reader_without_a_size_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            ea_big.parse_big(lambda offset, size: b"")
        self.assertIn("pass size=", str(caught.exception))

    def test_alignment_is_measured_not_assumed(self) -> None:
        self.assertEqual(ea_big.parse_big(
            ea_big.build_big([("a", b"x"), ("b", b"y")], alignment=64)
        ).alignment(), 64)
        self.assertEqual(ea_big.parse_big(
            ea_big.build_big([("a", b"x"), ("b", b"y")], alignment=4)
        ).alignment(), 4)

    def test_an_ordinary_archive_has_no_layout_notes(self) -> None:
        self.assertEqual(ea_big.parse_big(self.sample()).layout_notes(), [])

    def test_a_self_overlapping_archive_says_so(self) -> None:
        archive = bytearray(self.sample())
        parsed = ea_big.parse_big(bytes(archive))
        # Point entry 1 at entry 0's payload and give it the whole tail.
        row = ea_big.BIG_HEADER_SIZE + ea_big.BIG_ROW_FIXED + len("alpha.txt") + 1
        struct.pack_into(">II", archive, row, parsed.entries[0].offset,
                         parsed.entries[1].size)
        notes = ea_big.parse_big(bytes(archive)).layout_notes()
        self.assertTrue(any("inside entry" in note for note in notes), notes)

    def test_duplicate_names_are_counted_and_the_first_wins(self) -> None:
        archive = ea_big.build_big([("same.bin", b"first"),
                                    ("same.bin", b"second")])
        parsed = ea_big.parse_big(archive)
        self.assertEqual(parsed.duplicate_names, 1)
        self.assertEqual(parsed.member("same.bin"), b"first")
        self.assertIn("appear more than once", " ".join(parsed.layout_notes()))

    def test_a_summary_carries_counts_and_no_payload(self) -> None:
        summary = ea_big.parse_big(self.sample()).summary()
        self.assertEqual(summary["entries"], 3)
        self.assertEqual(summary["empty_entries"], 1)
        self.assertEqual(summary["format"], "BIGF")
        self.assertEqual(summary["layout_notes"], [])

    def test_declared_length_reads_the_header_only(self) -> None:
        archive = self.sample()
        self.assertEqual(ea_big.declared_length(archive[:16]), len(archive))


class RefusalTests(unittest.TestCase):

    def test_something_that_is_not_an_archive_is_named(self) -> None:
        with self.assertRaises(Refusal) as caught:
            ea_big.parse_big(b"TERF" + b"\x00" * 60, name="/DATA/X.DAT")
        self.assertIn("not an EA BIG archive", str(caught.exception))
        self.assertIn("/DATA/X.DAT", str(caught.exception))

    def test_big4_is_refused_by_name_not_misread(self) -> None:
        archive = bytearray(ea_big.build_big([("a", b"x")]))
        archive[:4] = ea_big.BIG4_MAGIC
        with self.assertRaises(ea_big.UnsupportedArchive) as caught:
            ea_big.parse_big(bytes(archive))
        self.assertIn("BIG4", str(caught.exception))

    def test_a_refpack_wrapped_archive_is_refused_by_name(self) -> None:
        archive = bytearray(ea_big.build_big([("a", b"x")]))
        archive[:2] = ea_big.C0FB_HEAD
        with self.assertRaises(ea_big.UnsupportedArchive) as caught:
            ea_big.parse_big(bytes(archive))
        self.assertIn("refpack_decompress", str(caught.exception))

    def test_a_wrong_endian_count_is_refused_rather_than_allocated_for(self) -> None:
        archive = bytearray(ea_big.build_big([("a", b"x")]))
        struct.pack_into("<I", archive, 8, 1)      # count, written the wrong way
        with self.assertRaises(Refusal) as caught:
            ea_big.parse_big(bytes(archive))
        self.assertIn("wrong byte order", str(caught.exception))

    def test_an_archive_cut_short_says_how_far_it_reaches(self) -> None:
        archive = ea_big.build_big([("a", b"x" * 300), ("b", b"y" * 300)])
        parsed = ea_big.parse_big(archive[:-256], size=len(archive) - 256,
                                  name="short.big")
        with self.assertRaises(ea_big.TruncatedArchive) as caught:
            parsed.member(1)
        self.assertIn("past the", str(caught.exception))


class WriterSketchTests(unittest.TestCase):

    def test_a_replacement_inside_the_slot_is_priced_without_blockers(self) -> None:
        archive = ea_big.build_big([("a.bin", b"x" * 100), ("b.bin", b"y" * 100)],
                                   alignment=64)
        parsed = ea_big.parse_big(archive)
        plan = ea_big.plan_entry_rewrite(parsed, 0, b"z" * 90)
        self.assertTrue(plan.fits_slot)
        self.assertFalse(plan.source_compressed)
        self.assertEqual(plan.slot_bytes, 128)
        self.assertIn("size word in the table", plan.note)
        # The only blocker left is the one no offline work can clear.
        self.assertEqual(len(plan.blockers), 1)
        self.assertIn("has been loaded by any game", plan.blockers[0])

    def test_a_replacement_past_the_slot_names_what_would_move(self) -> None:
        archive = ea_big.build_big([("a.bin", b"x" * 100), ("b.bin", b"y" * 100)],
                                   alignment=64)
        plan = ea_big.plan_entry_rewrite(ea_big.parse_big(archive), 0, b"z" * 500)
        self.assertFalse(plan.fits_slot)
        self.assertTrue(any("would move" in blocker for blocker in plan.blockers))
        self.assertIn("do not fit", plan.note)

    def test_a_packed_entry_is_priced_after_repacking(self) -> None:
        archive = ea_big.build_big([("p.bin", packed(b"repeat " * 40))])
        plan = ea_big.plan_entry_rewrite(ea_big.parse_big(archive), 0, b"repeat " * 40)
        self.assertTrue(plan.source_compressed)
        self.assertTrue(plan.fits_slot)
        self.assertIn("re-packed", plan.note)
        # A payload that does not pack small enough is refused by its packed size.
        plan = ea_big.plan_entry_rewrite(ea_big.parse_big(archive), 0, os.urandom(4000))
        self.assertFalse(plan.fits_slot)
        self.assertTrue(any("not fit even compressed" in blocker
                            for blocker in plan.blockers))

    def test_rewrite_replaces_a_stored_entry_inside_its_slot(self) -> None:
        archive = ea_big.build_big([("a.bin", b"x" * 100), ("b.bin", b"y" * 100)],
                                   alignment=64)
        parsed = ea_big.parse_big(archive)
        result = ea_big.rewrite_entry(parsed, 0, b"z" * 90)
        again = ea_big.parse_big(result.archive)
        self.assertEqual(len(result.archive), len(archive))
        self.assertEqual(again.member(0), b"z" * 90)
        self.assertEqual(again.member(1), b"y" * 100)
        self.assertEqual(again.entry(0).size, 90)
        self.assertEqual(again.entry(0).offset, parsed.entry(0).offset)
        self.assertFalse(result.compressed)
        # The old bytes past the new size are zeroed, not left behind.
        tail = result.archive[parsed.entry(0).offset + 90:parsed.entry(0).offset + 100]
        self.assertEqual(tail, bytes(10))
        # Exactly two ranges: the size word and the entry's span.
        self.assertEqual(len(result.ranges), 2)
        self.assertEqual(result.ranges[0][:2], (parsed.row_offset(0) + 4, 4))
        self.assertEqual(result.ranges[1][:2], (parsed.entry(0).offset, 100))
        changed = [index for index in range(len(archive))
                   if archive[index] != result.archive[index]]
        declared = set()
        for start, length, _reason in result.ranges:
            declared.update(range(start, start + length))
        self.assertTrue(set(changed) <= declared)

    def test_rewrite_repacks_a_packed_entry_and_it_reads_back(self) -> None:
        plain = b"the quick brown fox jumps over the lazy dog " * 30
        archive = ea_big.build_big([("p.bin", packed(plain)), ("q.bin", b"q" * 10)])
        parsed = ea_big.parse_big(archive)
        replacement = plain.replace(b"lazy", b"idle")
        result = ea_big.rewrite_entry(parsed, "p.bin", replacement)
        again = ea_big.parse_big(result.archive)
        self.assertTrue(again.is_compressed(0))
        self.assertEqual(again.member(0), replacement)
        self.assertEqual(again.member(1), b"q" * 10)
        self.assertTrue(result.compressed)
        self.assertLessEqual(result.stored_bytes, result.slot_bytes)

    def test_rewrite_refuses_a_replacement_that_does_not_fit(self) -> None:
        archive = ea_big.build_big([("a.bin", b"x" * 100)])
        parsed = ea_big.parse_big(archive)
        with self.assertRaises(Refusal) as caught:
            ea_big.rewrite_entry(parsed, 0, b"z" * 500)
        message = str(caught.exception)
        self.assertIn("owns a", message)
        self.assertIn("Nothing was changed.", message)
        archive2 = ea_big.build_big([("p.bin", packed(b"abc" * 20))])
        with self.assertRaises(Refusal) as caught:
            ea_big.rewrite_entry(ea_big.parse_big(archive2), 0, os.urandom(3000))
        self.assertIn("once RefPack-packed", str(caught.exception))

    def test_row_offsets_walk_the_variable_length_table(self) -> None:
        archive = ea_big.build_big([("a.bin", b"1"), ("longer-name.bin", b"2"),
                                    ("c.bin", b"3")])
        parsed = ea_big.parse_big(archive)
        self.assertEqual(parsed.row_offset(0), 16)
        self.assertEqual(parsed.row_offset(1), 16 + 8 + len("a.bin") + 1)
        self.assertEqual(parsed.row_offset(2),
                         parsed.row_offset(1) + 8 + len("longer-name.bin") + 1)
        for index in range(3):
            row = parsed.row_offset(index)
            self.assertEqual(struct.unpack_from(">II", archive, row),
                             (parsed.entry(index).offset, parsed.entry(index).size))


class RefpackEncoderTests(unittest.TestCase):
    """The encoder is proved by the decoder: every stream it writes reads back."""

    def round_trip(self, data: bytes, **kw) -> bytes:
        packed_bytes = ea_big.refpack_compress(data, **kw)
        self.assertTrue(ea_big.is_refpack(packed_bytes))
        self.assertEqual(ea_big.refpack_decompress(packed_bytes), data)
        return packed_bytes

    def test_empty_and_tiny_inputs_round_trip(self) -> None:
        for data in (b"", b"a", b"ab", b"abc", b"abcd", b"abcde"):
            self.round_trip(data)

    def test_the_header_is_the_discs_ten_fb_shape(self) -> None:
        stream = self.round_trip(b"hello" * 10)
        header = ea_big.refpack_header(stream)
        self.assertEqual(stream[:2], b"\x10\xfb")
        self.assertFalse(header.long_sizes)
        self.assertIsNone(header.compressed_size)
        self.assertEqual(header.decompressed_size, 50)

    def test_long_sizes_write_the_four_byte_form(self) -> None:
        stream = self.round_trip(b"x" * 100, long_sizes=True)
        self.assertEqual(stream[0] & ea_big.REFPACK_FLAG_LONG, ea_big.REFPACK_FLAG_LONG)
        self.assertEqual(ea_big.refpack_header(stream).decompressed_size, 100)

    def test_repetitive_data_compresses_and_random_data_survives(self) -> None:
        text = b"the quick brown fox jumps over the lazy dog. " * 200
        packed_bytes = self.round_trip(text)
        self.assertLess(len(packed_bytes), len(text) // 10)
        noise = os.urandom(20000)
        self.round_trip(noise)

    def test_every_opcode_shape_is_exercised(self) -> None:
        near = b"abcdefgh" * 40
        mid = os.urandom(3000) + b"pattern-mid" * 3 + os.urandom(5000) + b"pattern-mid" * 3
        far = os.urandom(20000) + b"far-pattern-here" + os.urandom(30000) + b"far-pattern-here"
        long_run = b"\x00" * 5000 + b"tail"
        for data in (near, mid, far, long_run):
            self.round_trip(data)

    def test_an_overlapping_copy_is_written_and_read_as_a_repeat(self) -> None:
        packed_bytes = self.round_trip(b"ab" * 3000)
        self.assertLess(len(packed_bytes), 64)

    def test_chain_depth_changes_size_never_correctness(self) -> None:
        data = (b"alpha,beta,gamma,delta\r\n" * 300) + os.urandom(500)
        shallow = self.round_trip(data, chain_limit=1)
        deep = self.round_trip(data, chain_limit=256)
        self.assertLessEqual(len(deep), len(shallow))


if __name__ == "__main__":
    unittest.main()
