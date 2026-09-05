"""Tests for the EA ``TERF`` container package.

Synthetic containers only.  Nothing here reads a disc, a retail file or a
fixture: every byte a test looks at is one it built, so the suite runs for a
contributor who owns none of the games.
"""

from __future__ import annotations

from pathlib import Path
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_terf  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


def round_up(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


class _BitWriter:
    """MSB-first bit writer -- the mirror of the codec's reader.

    Only the tests have one.  It exists so an ``LZH1`` stream can be built from
    the grammar rather than pasted in as a hex blob whose provenance nobody can
    check.
    """

    def __init__(self) -> None:
        self.bits: list = []

    def write(self, value: int, width: int) -> "_BitWriter":
        for shift in range(width - 1, -1, -1):
            self.bits.append((value >> shift) & 1)
        return self

    def bytes(self) -> bytes:
        padded = self.bits + [0] * (-len(self.bits) % 8)
        out = bytearray()
        for index in range(0, len(padded), 8):
            byte = 0
            for bit in padded[index:index + 8]:
                byte = (byte << 1) | bit
            out.append(byte)
        return bytes(out)


#: Literal/length code lengths that make the canonical code of every symbol
#: equal to the symbol itself: 258 symbols (0..255 literals, 256 end-of-block,
#: 257 = a length-3 match) all nine bits wide.
_LITERAL_LENGTHS = [9] * 258 + [0] * (ea_terf.LZH1_LITERAL_SYMBOLS - 258)
#: One distance symbol, one bit wide: symbol 0 is a distance of 1.
_DISTANCE_LENGTHS = [1] + [0] * (ea_terf.LZH1_DISTANCE_SYMBOLS - 1)


def lzh1_stream(symbols) -> bytes:
    """Assemble one ``LZH1`` block emitting *symbols*, then end the stream.

    *symbols* is a sequence of ints: a literal 0..255, or ``257`` for a
    three-byte match at distance 1 (which repeats the previous byte).
    """
    writer = _BitWriter()
    writer.write(0, 1)                       # a block follows
    for length in _LITERAL_LENGTHS:
        writer.write(length, 4)
    for length in _DISTANCE_LENGTHS:
        writer.write(length, 4)
    for symbol in symbols:
        writer.write(symbol, 9)
        if symbol == 257:
            writer.write(0, 1)               # distance symbol 0 -> distance 1
    writer.write(256, 9)                     # end of block
    writer.write(1, 1)                       # end of stream
    writer.write(0, 32)                      # ... and its ignored trailer
    return writer.bytes()


def mmap_member(width: int, height: int, payload_size: int = 512) -> bytes:
    """A synthetic ``MMAP`` member with the header fields the parser reads."""
    header = bytearray(b"MMAP")
    header += struct.pack("<I", 2)               # +0x04 version
    header += b"\x00\x01\x02\x03"                # +0x08 marker
    header += struct.pack("<HH", 1, 1)           # +0x0C
    header += struct.pack("<I", 1)               # +0x10
    header += struct.pack("<I", payload_size)    # +0x14
    header += struct.pack("<I", ea_terf.MMAP_HEADER_SIZE)   # +0x18
    header += struct.pack("<III", 100, 200, 300)            # +0x1C..0x24
    header += struct.pack("<HH", width, height)             # +0x28
    header += b"\xAB" * 20
    return bytes(header)


PAYLOADS = [
    b"MMAP" + bytes(range(60)),
    b"",
    b"DB\x00\x08" + b"\x00" * 12 + struct.pack("<I", 4) + b"TEAMPLAY",
    b"the quick brown fox jumps over the lazy dog and keeps on going",
]


class BuildAndParseTests(unittest.TestCase):
    def test_a_plain_container_round_trips(self) -> None:
        built = ea_terf.build_terf(PAYLOADS)
        parsed = ea_terf.parse_terf(built)
        self.assertEqual(parsed.member_count, len(PAYLOADS))
        self.assertEqual(parsed.chunk_chain, "TERF -> DIR1 -> DATA")
        self.assertFalse(parsed.compressed)
        self.assertEqual([parsed.member(i) for i in range(len(PAYLOADS))],
                         PAYLOADS)

    def test_a_compressed_container_round_trips_through_both_codecs(self) -> None:
        codecs = [ea_terf.CODEC_STORED, ea_terf.CODEC_STORED,
                  ea_terf.CODEC_RLE1, ea_terf.CODEC_RLE1]
        built = ea_terf.build_terf(PAYLOADS, chunk="COMP", codecs=codecs)
        parsed = ea_terf.parse_terf(built)
        self.assertEqual(parsed.chunk_chain, "TERF -> DIR1 -> COMP -> DATA")
        self.assertTrue(parsed.compressed)
        self.assertEqual([m.codec for m in parsed.members], codecs)
        self.assertEqual([parsed.member(i) for i in range(len(PAYLOADS))],
                         PAYLOADS)
        self.assertEqual(parsed.codec_histogram(),
                         {"NONE (stored)": 2, "RLE1": 2})

    def test_the_writer_agrees_with_the_readers_layout_rules(self) -> None:
        for alignment in (4, 16, 64, 2048):
            with self.subTest(alignment=alignment):
                built = ea_terf.build_terf(PAYLOADS, alignment=alignment)
                parsed = ea_terf.parse_terf(built)
                self.assertEqual(parsed.layout_violations(), [])
                self.assertEqual(parsed.alignment, alignment)
                self.assertEqual(parsed.header_size,
                                 max(ea_terf.MIN_HEADER_SIZE, alignment))
                self.assertEqual(len(built) % alignment, 0)
                directory = parsed.chunk("DIR1")
                assert directory is not None
                self.assertEqual(
                    directory.size,
                    round_up(ea_terf.CHUNK_HEADER_SIZE + 8 * len(PAYLOADS),
                             alignment))

    def test_the_data_chunk_declares_its_size_to_end_of_file(self) -> None:
        built = ea_terf.build_terf(PAYLOADS)
        parsed = ea_terf.parse_terf(built)
        self.assertEqual(parsed.data_offset + parsed.data_size, len(built))

    def test_an_empty_member_still_occupies_one_alignment_unit(self) -> None:
        # This is the rule 323 of Madden 09's members depend on: a writer that
        # packs an empty member at zero width relocates everything after it.
        built = ea_terf.build_terf([b"a", b"", b"", b"z"], alignment=64)
        parsed = ea_terf.parse_terf(built)
        offsets = [member.offset for member in parsed.members]
        self.assertEqual(offsets, [64, 128, 192, 256])
        self.assertEqual(parsed.member(3), b"z")

    def test_member_offsets_are_relative_to_the_data_tag(self) -> None:
        # The natural misreading -- offsets relative to the *payload* of the
        # DATA chunk -- is off by the eight-byte chunk header and corrupts
        # every member.  Pin the right one.
        built = ea_terf.build_terf([b"first-member"], alignment=64)
        parsed = ea_terf.parse_terf(built)
        member = parsed.members[0]
        start = parsed.data_offset + member.offset
        self.assertEqual(built[start:start + member.stored_size], b"first-member")

    def test_gaps_and_the_tail_are_zero_filled(self) -> None:
        built = ea_terf.build_terf([b"a" * 3, b"b" * 5], alignment=64)
        parsed = ea_terf.parse_terf(built)
        body = built[parsed.data_offset:]
        cursor = ea_terf.CHUNK_HEADER_SIZE
        for member in parsed.members:
            self.assertEqual(set(body[cursor:member.offset]) - {0}, set())
            cursor = member.offset + member.stored_size
        self.assertEqual(set(body[cursor:]) - {0}, set())

    def test_the_chunk_chain_is_walked_by_tag_not_by_a_fixed_offset(self) -> None:
        # UIS_FONT.DAT is the disc's one container with an extra chunk between
        # the header and the directory; a reader with a hard-coded DIR1 offset
        # refuses it.  Splice the same shape together and read it.
        built = bytearray(ea_terf.build_terf(PAYLOADS, alignment=64))
        parsed = ea_terf.parse_terf(bytes(built))
        extra = bytearray(ea_terf.HSH1_MAGIC + struct.pack("<I", 64))
        extra += b"\x00" * (64 - len(extra))
        spliced = built[:parsed.header_size] + extra + built[parsed.header_size:]
        reparsed = ea_terf.parse_terf(bytes(spliced))
        self.assertEqual(reparsed.chunk_chain, "TERF -> HSH1 -> DIR1 -> DATA")
        self.assertEqual([reparsed.member(i) for i in range(len(PAYLOADS))],
                         PAYLOADS)


class RewriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plain = ea_terf.build_terf(PAYLOADS)
        self.packed = ea_terf.build_terf(
            PAYLOADS, chunk="COMP",
            codecs=[ea_terf.CODEC_STORED, ea_terf.CODEC_STORED,
                    ea_terf.CODEC_RLE1, ea_terf.CODEC_RLE1])

    def test_a_rewrite_leaves_every_other_member_byte_identical(self) -> None:
        replacement = b"MMAP" + b"\xEE" * 200
        rewritten = ea_terf.rewrite_member(self.plain, 0, replacement)
        parsed = ea_terf.parse_terf(rewritten)
        self.assertEqual(parsed.member(0), replacement)
        for index in range(1, len(PAYLOADS)):
            self.assertEqual(parsed.member(index), PAYLOADS[index])
        self.assertEqual(parsed.layout_violations(), [])

    def test_a_same_slot_rewrite_changes_nothing_outside_the_slot(self) -> None:
        original = ea_terf.parse_terf(self.plain)
        member = original.members[3]
        replacement = b"x" * member.stored_size
        rewritten = ea_terf.rewrite_member(self.plain, 3, replacement)
        self.assertEqual(len(rewritten), len(self.plain))
        start = original.data_offset + member.offset
        self.assertEqual(rewritten[:start], self.plain[:start])
        end = start + member.stored_size
        self.assertEqual(rewritten[end:], self.plain[end:])

    def test_a_bigger_member_shifts_the_rest_and_still_reads_back(self) -> None:
        replacement = b"Z" * 5000
        rewritten = ea_terf.rewrite_member(self.plain, 0, replacement)
        self.assertGreater(len(rewritten), len(self.plain))
        parsed = ea_terf.parse_terf(rewritten)
        self.assertEqual(parsed.member(0), replacement)
        self.assertEqual([parsed.member(i) for i in range(1, len(PAYLOADS))],
                         PAYLOADS[1:])
        self.assertEqual(parsed.data_offset + parsed.data_size, len(rewritten))

    def test_a_rewrite_in_a_comp_container_stores_the_new_member(self) -> None:
        replacement = b"MMAP" + b"\x11" * 100
        rewritten = ea_terf.rewrite_member(self.packed, 3, replacement)
        parsed = ea_terf.parse_terf(rewritten)
        self.assertEqual(parsed.members[3].codec, ea_terf.CODEC_STORED)
        self.assertEqual(parsed.members[3].decompressed_size, len(replacement))
        self.assertEqual(parsed.member(3), replacement)
        # the untouched RLE1 member keeps its codec and its bytes
        self.assertEqual(parsed.members[2].codec, ea_terf.CODEC_RLE1)
        self.assertEqual(parsed.member(2), PAYLOADS[2])

    def test_a_rewrite_refuses_an_index_that_does_not_exist(self) -> None:
        for index in (-1, len(PAYLOADS), 9999):
            with self.subTest(index=index):
                with self.assertRaises(ea_terf.TerfError) as caught:
                    ea_terf.rewrite_member(self.plain, index, b"x")
                self.assertIn("does not exist", str(caught.exception))
                self.assertIn("Nothing was changed", str(caught.exception))

    def test_a_rewrite_refuses_a_container_it_cannot_rebuild(self) -> None:
        broken = bytearray(self.plain)
        parsed = ea_terf.parse_terf(self.plain)
        directory = parsed.chunk("DIR1")
        assert directory is not None
        # Slide the last member back on top of its predecessor: still inside
        # the file, so it parses, but not where the layout rule puts it.
        last = len(PAYLOADS) - 1
        struct.pack_into("<I", broken, directory.offset + 8 + 8 * last,
                         parsed.members[last - 1].offset)
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.rewrite_member(bytes(broken), 0, b"x")
        self.assertIn("layout rules", str(caught.exception))


class BuildRefusalTests(unittest.TestCase):
    def test_a_plain_container_refuses_a_codec_table(self) -> None:
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.build_terf([b"x"], chunk="DATA", codecs=[ea_terf.CODEC_RLE1])
        self.assertIn("no codec table", str(caught.exception))

    def test_writing_lzh1_is_refused_by_name(self) -> None:
        with self.assertRaises(ea_terf.UnsupportedCodec) as caught:
            ea_terf.build_terf([b"x"], chunk="COMP",
                               codecs=[ea_terf.CODEC_LZH1])
        message = str(caught.exception)
        self.assertIn("LZH1", message)
        self.assertIn("no lzh1 encoder exists", message.lower())

    def test_an_unknown_chunk_kind_is_refused(self) -> None:
        with self.assertRaises(ea_terf.TerfError):
            ea_terf.build_terf([b"x"], chunk="DIR1")

    def test_a_non_power_of_two_alignment_is_refused(self) -> None:
        with self.assertRaises(ea_terf.TerfError):
            ea_terf.build_terf([b"x"], alignment=48)

    def test_one_codec_per_member_is_required(self) -> None:
        with self.assertRaises(ea_terf.TerfError):
            ea_terf.build_terf([b"x", b"y"], chunk="COMP", codecs=[0])


class ParseRefusalTests(unittest.TestCase):
    def test_a_non_terf_file_is_refused_by_name(self) -> None:
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_terf(b"\x7fELF" + bytes(200))
        self.assertIn("not an EA TERF container", str(caught.exception))

    def test_every_refusal_is_a_contract_refusal(self) -> None:
        self.assertTrue(issubclass(ea_terf.TerfError, Refusal))
        with self.assertRaises(Refusal):
            ea_terf.parse_terf(b"nope")

    def test_a_container_whose_data_chunk_overruns_is_refused(self) -> None:
        built = bytearray(ea_terf.build_terf(PAYLOADS))
        parsed = ea_terf.parse_terf(bytes(built))
        struct.pack_into("<I", built, parsed.data_offset + 4,
                         parsed.data_size + 64)
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_terf(bytes(built))
        self.assertIn("DATA chunk", str(caught.exception))


class ShortlyRecordedContainerTests(unittest.TestCase):
    """A container handed fewer bytes than it declares.

    Six containers on the community's Madden 09 Deluxe disc are recorded in
    ISO9660 as 4 to 26,168 bytes shorter than their own DATA chunk says.  The
    bytes are on the disc; a reader that trusts the directory record loses
    every member past the cut.
    """

    def test_declared_length_reads_the_length_off_the_chunk_chain(self) -> None:
        built = ea_terf.build_terf(PAYLOADS)
        self.assertEqual(ea_terf.declared_length(built), len(built))
        # and it only needs the head, not the body
        parsed = ea_terf.parse_terf(built)
        head = built[:parsed.data_offset + ea_terf.CHUNK_HEADER_SIZE]
        self.assertEqual(ea_terf.declared_length(head), len(built))

    def test_declared_length_refuses_a_head_with_no_data_chunk(self) -> None:
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.declared_length(
                ea_terf.TERF_MAGIC + struct.pack("<I", 64) + bytes(56))
        self.assertIn("no DATA chunk", str(caught.exception))

    def test_a_short_buffer_is_refused_by_default(self) -> None:
        built = ea_terf.build_terf(PAYLOADS)
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_terf(built[:-4])
        self.assertIn("allow_size_mismatch", str(caught.exception))

    def test_a_short_buffer_is_read_when_the_caller_allows_it(self) -> None:
        built = ea_terf.build_terf(PAYLOADS)
        whole = ea_terf.parse_terf(built)
        last = whole.members[-1]
        tail = len(built) - (whole.data_offset + last.offset + last.stored_size)
        self.assertGreater(tail, 0, "this container has no tail to trim")
        trimmed = built[:-tail]       # inside the zero tail, so nothing is lost
        parsed = ea_terf.parse_terf(trimmed, allow_size_mismatch=True)
        self.assertEqual(parsed.size_mismatch, tail)
        self.assertEqual(parsed.declared_length, len(built))
        self.assertEqual([parsed.member(i) for i in range(len(PAYLOADS))],
                         PAYLOADS)

    def test_a_member_lost_to_the_cut_is_still_refused(self) -> None:
        built = ea_terf.build_terf(PAYLOADS)
        parsed = ea_terf.parse_terf(built)
        cut = parsed.data_offset + parsed.members[-1].offset + 8
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_terf(built[:cut], allow_size_mismatch=True)
        self.assertIn("past the end", str(caught.exception))

    def test_a_member_running_past_the_end_is_refused(self) -> None:
        built = bytearray(ea_terf.build_terf(PAYLOADS))
        parsed = ea_terf.parse_terf(bytes(built))
        directory = parsed.chunk("DIR1")
        assert directory is not None
        struct.pack_into("<I", built, directory.offset + 8 + 4, 1 << 24)
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_terf(bytes(built))
        self.assertIn("past the end", str(caught.exception))

    def test_a_member_index_out_of_range_is_refused(self) -> None:
        parsed = ea_terf.parse_terf(ea_terf.build_terf(PAYLOADS))
        with self.assertRaises(ea_terf.TerfError):
            parsed.member(len(PAYLOADS))
        with self.assertRaises(ea_terf.TerfError):
            parsed.stored(-1)

    def test_a_member_with_a_codec_we_cannot_decode_is_refused_by_name(self) -> None:
        built = bytearray(ea_terf.build_terf(
            PAYLOADS, chunk="COMP",
            codecs=[ea_terf.CODEC_STORED] * len(PAYLOADS)))
        parsed = ea_terf.parse_terf(bytes(built))
        compression = parsed.chunk("COMP")
        assert compression is not None
        struct.pack_into("<I", built, compression.offset + 8, ea_terf.CODEC_HUFF)
        reparsed = ea_terf.parse_terf(bytes(built))
        with self.assertRaises(ea_terf.UnsupportedCodec) as caught:
            reparsed.member(0)
        message = str(caught.exception)
        self.assertIn("HUFF", message)
        self.assertIn("refusal, not an empty member", message)


class Lzh1Tests(unittest.TestCase):
    def test_literals_decode(self) -> None:
        payload = b"Madden on a PlayStation 2 disc"
        stream = lzh1_stream(list(payload))
        self.assertEqual(ea_terf.lzh1_decompress(stream, len(payload)), payload)

    def test_a_match_repeats_earlier_output(self) -> None:
        # literal 'A', then a length-3 match at distance 1
        stream = lzh1_stream([ord("A"), 257])
        self.assertEqual(ea_terf.lzh1_decompress(stream, 4), b"AAAA")

    def test_max_output_stops_early_without_the_size_check(self) -> None:
        payload = bytes(range(64)) * 4
        stream = lzh1_stream(list(payload))
        self.assertEqual(ea_terf.lzh1_decompress(stream, max_output=8),
                         payload[:8])

    def test_a_truncated_stream_is_refused_rather_than_padded(self) -> None:
        # Cut into the symbol body, not the trailer: a decode that has already
        # produced every declared byte never reads the end-of-stream marker,
        # so losing the last four bytes is invisible by design.
        payload = b"a longer body so the stream has plenty to lose here"
        stream = lzh1_stream(list(payload))
        with self.assertRaises(ea_terf.TruncatedStream) as caught:
            ea_terf.lzh1_decompress(stream[:-20], len(payload))
        self.assertIn("will not pad it with zeros", str(caught.exception))

    def test_a_deliberate_prefix_is_allowed_only_when_the_caller_says_so(self) -> None:
        payload = b"prefix only, please, and then some more body to lose"
        stream = lzh1_stream(list(payload))
        short = stream[:-20]
        with self.assertRaises(ea_terf.TruncatedStream):
            ea_terf.lzh1_decompress(short, len(payload))
        self.assertEqual(
            ea_terf.lzh1_decompress(short, allow_truncation=True, max_output=6),
            payload[:6])

    def test_max_output_stops_a_stream_made_only_of_literals(self) -> None:
        # The early abort has to be reachable from the literal branch too: a
        # member that is all literals is exactly the one a magic-only census
        # must not decode in full.
        payload = b"L" * 4000
        stream = lzh1_stream(list(payload))
        self.assertEqual(ea_terf.lzh1_decompress(stream, max_output=4), b"LLLL")

    def test_a_decode_of_the_wrong_length_is_refused(self) -> None:
        payload = b"exactly this long"
        stream = lzh1_stream(list(payload))
        with self.assertRaises(ea_terf.TruncatedStream) as caught:
            ea_terf.lzh1_decompress(stream, len(payload) + 1)
        self.assertIn("wrong length", str(caught.exception))


class Rle1Tests(unittest.TestCase):
    def test_the_encoder_and_the_decoder_agree(self) -> None:
        cases = [
            b"",
            b"abc",
            b"a" * 300,
            b"\x00" * 1024 + b"tail",
            b"mixed " + b"\xFF" * 40 + b" middle " + b"\x00" * 7,
            bytes(range(256)),
            b"!!!!! exclamation marks are the escape byte !!",
        ]
        for payload in cases:
            with self.subTest(payload=payload[:16]):
                packed = ea_terf.rle1_compress(payload)
                self.assertEqual(
                    ea_terf.rle1_decompress(packed, len(payload)), payload)

    def test_a_lone_escape_byte_survives(self) -> None:
        payload = b"a!b"
        packed = ea_terf.rle1_compress(payload)
        self.assertEqual(ea_terf.rle1_decompress(packed, 3), payload)

    def test_a_run_longer_than_a_byte_can_count_is_split(self) -> None:
        payload = b"q" * (ea_terf.RLE1_MAX_RUN * 3 + 7)
        packed = ea_terf.rle1_compress(payload)
        self.assertEqual(ea_terf.rle1_decompress(packed, len(payload)), payload)

    def test_a_stream_ending_mid_escape_is_refused(self) -> None:
        with self.assertRaises(ea_terf.Rle1Error) as caught:
            ea_terf.rle1_decompress(bytes([ea_terf.RLE1_ESCAPE, 0x41]))
        self.assertIn("mid-escape", str(caught.exception))

    def test_a_decode_of_the_wrong_length_is_refused(self) -> None:
        with self.assertRaises(ea_terf.Rle1Error) as caught:
            ea_terf.rle1_decompress(b"abc", 4)
        self.assertIn("short result", str(caught.exception))

    def test_max_output_suppresses_the_length_check(self) -> None:
        packed = ea_terf.rle1_compress(b"z" * 100)
        self.assertEqual(ea_terf.rle1_decompress(packed, max_output=5),
                         b"zzzzz")


class IdentifyTests(unittest.TestCase):
    def test_each_known_magic_is_named(self) -> None:
        cases = {
            b"MMAP" + bytes(40): "MMAP",
            b"SMF\x00" + bytes(40): "SMF",
            b"DMF\x00" + bytes(40): "DMF",
            b"TERF" + bytes(40): "TERF",
            b"QL01" + bytes(40): "QL01",
            b"HSH1" + bytes(40): "HSH1",
            b"BIGF" + bytes(40): "BIGF",
            b"SCHl" + bytes(40): "SCHl",
            b"BNKl" + bytes(40): "BNKl",
            b"1LKS" + bytes(40): "SKL1",
            b"\x7fELF" + bytes(40): "ELF",
        }
        for payload, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(ea_terf.identify_member(payload), expected)

    def test_empty_is_its_own_answer(self) -> None:
        self.assertEqual(ea_terf.identify_member(b""), ea_terf.FORMAT_EMPTY)

    def test_a_tdb_is_recognised_by_a_plausible_table_count(self) -> None:
        good = b"DB\x00\x08" + bytes(12) + struct.pack("<I", 21) + b"PLAY"
        self.assertEqual(ea_terf.identify_member(good), ea_terf.FORMAT_TDB)
        # "DB" is two bytes and coincidences happen: an absurd table count
        # means these are not a database's first bytes.
        bogus = b"DB\x00\x08" + bytes(12) + struct.pack("<I", 999999) + b"junk"
        self.assertNotEqual(ea_terf.identify_member(bogus), ea_terf.FORMAT_TDB)

    def test_text_is_judged_over_the_whole_head_not_the_first_bytes(self) -> None:
        self.assertEqual(ea_terf.identify_member(b"a plain english headline"),
                         ea_terf.FORMAT_TEXT)
        mostly = b"readable-for-a-while" + bytes(20)
        self.assertIsNone(ea_terf.identify_member(mostly))

    def test_an_unknown_head_is_none_not_an_error(self) -> None:
        self.assertIsNone(ea_terf.identify_member(b"\x01\x02\x03\x04" * 10))

    def test_the_histogram_separates_unclassified_from_undecodable(self) -> None:
        built = bytearray(ea_terf.build_terf(
            [b"MMAP" + bytes(40), b"\x01\x02\x03\x04" * 10],
            chunk="COMP", codecs=[ea_terf.CODEC_STORED] * 2))
        parsed = ea_terf.parse_terf(bytes(built))
        self.assertEqual(parsed.format_histogram(),
                         {"MMAP": 1, "unclassified": 1})
        compression = parsed.chunk("COMP")
        assert compression is not None
        struct.pack_into("<I", built, compression.offset + 8 + 8,
                         ea_terf.CODEC_LZM1)
        broken = ea_terf.parse_terf(bytes(built))
        self.assertEqual(broken.format_histogram(),
                         {"MMAP": 1, "undecodable": 1})


class MmapHeaderTests(unittest.TestCase):
    def test_the_header_fields_are_read(self) -> None:
        header = ea_terf.parse_mmap_header(mmap_member(128, 64, 4096))
        self.assertEqual(header.version, 2)
        self.assertEqual(header.marker, b"\x00\x01\x02\x03")
        self.assertEqual(header.header_size, ea_terf.MMAP_HEADER_SIZE)
        self.assertEqual(header.payload_size, 4096)
        self.assertEqual((header.size_a, header.size_b, header.size_c),
                         (100, 200, 300))
        self.assertEqual(header.dimensions, (128, 64))

    def test_the_undecoded_descriptor_bytes_come_back_verbatim(self) -> None:
        member = mmap_member(32, 32)
        header = ea_terf.parse_mmap_header(member)
        self.assertEqual(header.descriptor, member[ea_terf.MMAP_HEADER_SIZE:0x40])

    def test_a_member_that_is_not_an_mmap_is_refused(self) -> None:
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_mmap_header(b"SMF\x00" + bytes(60))
        self.assertIn("Decompress the member first", str(caught.exception))

    def test_a_truncated_mmap_is_refused(self) -> None:
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_mmap_header(b"MMAP" + bytes(8))
        self.assertIn("truncated", str(caught.exception))


class CommandLineTests(unittest.TestCase):
    def test_the_selftest_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/ea_terf_inspect.py"), "--selftest"],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EA_TERF_SELFTEST_PASS", result.stdout)

    def test_it_refuses_with_a_sentence_when_given_nothing(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/ea_terf_inspect.py")],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("refused:", result.stderr)

    def test_it_reports_a_container_built_here(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ea_terf_inspect", ROOT / "tools/ea_terf_inspect.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        container = ea_terf.parse_terf(ea_terf.build_terf(PAYLOADS))
        report = module.describe(container, "synthetic")
        self.assertEqual(report["member_count"], len(PAYLOADS))
        self.assertEqual(report["chunk_kind"], "DATA")
        self.assertEqual(report["format_counts"],
                         {"MMAP": 1, "empty": 1, "TDB": 1, "TEXT": 1})
        self.assertEqual(report["layout_violations"], [])


class BufferViewTests(unittest.TestCase):
    """The parser reads a memoryview or an mmap exactly as it reads bytes, so a disc mapper
    can walk a 1.7 GB movie container through the page cache instead of loading it."""

    def test_memoryview_and_mmap_match_bytes(self) -> None:
        import mmap, tempfile, os
        payload = ea_terf.build_terf([b"DB\x00\x08" + bytes(60), b"MMAP" + bytes(300), b"TEXT" + bytes(40), b""], chunk="COMP")
        expect = ea_terf.parse_terf(payload)
        view = ea_terf.parse_terf(memoryview(payload))
        self.assertEqual(view.format_histogram(), expect.format_histogram())
        self.assertEqual(view.codec_histogram(), expect.codec_histogram())
        self.assertEqual(view.chunk_chain, expect.chunk_chain)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.dat")
            with open(path, "wb") as handle:
                handle.write(bytes(8192) + payload)   # a container that does not start at offset 0
            with open(path, "rb") as handle:
                mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
                view = memoryview(mapped)
                try:
                    container = ea_terf.parse_terf(view[8192:8192 + len(payload)])
                    self.assertEqual(container.format_histogram(), expect.format_histogram())
                    self.assertEqual(container.member(0), expect.member(0))
                finally:
                    del container          # the container holds a slice of the view
                    view.release()         # every exported pointer must go before the map closes
                    mapped.close()


class TrailingEmptyMemberTests(unittest.TestCase):
    """The Deluxe disc's under-counted trailing empty member: tolerated only when the caller accepts a size mismatch."""

    def _cut_before_the_empty_member(self) -> bytes:
        container = ea_terf.build_terf([b"payload" * 8, b""], chunk="DATA")
        parsed = ea_terf.parse_terf(container)
        start = parsed.data_offset + parsed.members[1].offset
        self.assertEqual(parsed.members[1].stored_size, 0)
        return container[:start - 8]   # member 0 is whole; the empty member 1 starts 8 bytes past the end

    def test_empty_member_past_the_end_is_tolerated_with_allow_size_mismatch(self) -> None:
        cut = self._cut_before_the_empty_member()
        parsed = ea_terf.parse_terf(cut, allow_size_mismatch=True)
        self.assertEqual(parsed.member_count, 2)
        self.assertEqual(parsed.member(1), b"")
        self.assertEqual(parsed.member_format(1), ea_terf.FORMAT_EMPTY)
        self.assertGreater(parsed.size_mismatch, 0)
        self.assertEqual(parsed.layout_violations(), [], "the container is otherwise ordinary; only the bytes handed over are short")

    def test_without_the_flag_the_size_mismatch_still_refuses(self) -> None:
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_terf(self._cut_before_the_empty_member())
        self.assertIn("allow_size_mismatch", str(caught.exception))

    def test_a_member_with_bytes_past_the_end_still_refuses(self) -> None:
        container = ea_terf.build_terf([b"payload" * 8, b"tail" * 4], chunk="DATA")
        parsed = ea_terf.parse_terf(container)
        start = parsed.data_offset + parsed.members[1].offset
        with self.assertRaises(ea_terf.TerfError) as caught:
            ea_terf.parse_terf(container[:start + 4], allow_size_mismatch=True)
        self.assertIn("past the end", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
