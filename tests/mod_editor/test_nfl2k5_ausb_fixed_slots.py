"""Synthetic, retail-free tests for fixed-allocation NFL 2K5 AUSB ranges."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import io
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core.nfl2k5_audio_catalog import (
    Nfl2k5StreamingAudioBank,
    Nfl2k5StreamingAudioRange,
)
from mod_editor.core.nfl2k5_ausb_fixed_slots import (
    Nfl2k5AusbFixedSlotError,
    StreamingEncodeCancelled,
    build_streaming_slot_catalog,
    decode_xbox_ima_time_block,
    encode_strict_pcm16_wav,
    streaming_slot_write_plan,
    verify_xbox_ima_stream,
)


TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_outer import Archive, Entry, Pack, Segment  # noqa: E402


EXTERNAL_ID = 0x1234ABCD


def _archive() -> Archive:
    packs = (
        Pack(0, "0", 1, 256, 0, Path("/synthetic/0")),
        Pack(1, "1", 1, 256, 256, Path("/synthetic/1")),
    )
    entry = Entry(
        table_index=77,
        name_id=EXTERNAL_ID,
        size=144,
        offset_blocks=0,
        virtual_offset=206,
        head_hex="00000000",
        head_ascii="....",
        segments=(
            Segment(0, "0", 206, 50),
            Segment(1, "1", 0, 94),
        ),
    )
    return Archive(
        index_path=Path("/synthetic/0"),
        reserved=0,
        populated_pack_count=2,
        packs=packs,
        entries=(entry,),
    )


def _bank(*, descriptor: int, channels: int = 2,
          boundaries: tuple[int, ...] = (0, 144)) -> Nfl2k5StreamingAudioBank:
    return Nfl2k5StreamingAudioBank(
        asset_id=f"nfl2k5.audio.ausb.o{descriptor:04d}.c0000",
        name="cwdloop",
        role_class="diagnostic_or_ambient",
        outer_index=descriptor,
        outer_id=f"0x{descriptor:08x}",
        outer_head="AUSB",
        outer_size=512,
        chunk_index=0,
        chunk_offset=32,
        stored_size=480,
        external_filename="cwdloop.bin",
        external_outer_index=77,
        external_outer_id=f"0x{EXTERNAL_ID:08x}",
        external_size=144,
        entry_count=len(boundaries) - 1,
        sample_rate=22_050,
        channel_word=channels,
        unknown_word=0x6000,
        unit_word=0x12000,
        boundaries=boundaries,
        descriptor_sha256=f"{descriptor:064x}",
        shared_external_descriptor_count=2,
    )


def _ranges() -> tuple[Nfl2k5StreamingAudioRange, ...]:
    return tuple(
        Nfl2k5StreamingAudioRange(bank, 0, 0, 144)
        for bank in (_bank(descriptor=10), _bank(descriptor=11))
    )


def _wav(*, channels: int = 2, rate: int = 22_050,
         frames: int = 128, trailing: bytes = b"") -> bytes:
    samples = tuple(
        ((frame * 503 + channel * 7_001) % 30_001) - 15_000
        for frame in range(frames)
        for channel in range(channels)
    )
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    header = (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
        + b"fmt " + struct.pack(
            "<IHHIIHH", 16, 1, channels, rate, rate * channels * 2,
            channels * 2, 16,
        )
        + b"data" + struct.pack("<I", len(pcm))
    )
    return header + pcm + trailing


def _wav_with_metadata() -> bytes:
    canonical = _wav()
    fmt_chunk = canonical[12:36]
    pcm = canonical[44:]
    body = fmt_chunk + b"JUNK" + struct.pack("<I", 4) + b"test" \
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


class Nfl2k5AusbFixedSlotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.archive = _archive()
        self.logical_ranges = _ranges()
        self.catalog = build_streaming_slot_catalog(
            self.logical_ranges, self.archive
        )
        self.slot = self.catalog.slots[0]

    def test_alias_seam_stream_round_trip_preserves_every_other_byte(self) -> None:
        self.assertEqual(len(self.catalog.slots), 1)
        self.assertEqual(len(self.slot.owners), 2)
        self.assertTrue(self.slot.shared_effect)
        self.assertIs(
            self.catalog.resolve(self.logical_ranges[0].asset_id),
            self.catalog.resolve(self.logical_ranges[1].asset_id),
        )
        self.assertIs(self.catalog.resolve(self.slot.canonical_id), self.slot)

        spans = streaming_slot_write_plan(self.slot)
        self.assertEqual(
            [(span.pack_name, span.pack_offset, span.length, span.payload_offset)
             for span in spans],
            [("0", 206, 50, 0), ("1", 0, 94, 50)],
        )
        self.assertNotEqual(spans[0].length % (36 * self.slot.channels), 0)

        progress = []
        output = io.BytesIO()
        result = encode_strict_pcm16_wav(
            io.BytesIO(_wav()),
            output,
            self.slot,
            progress=lambda update: progress.append(update.completed_blocks),
            progress_interval_blocks=1,
        )
        encoded = output.getvalue()
        self.assertEqual(progress, [0, 1, 2])
        self.assertEqual(result.encoded_size, 144)
        self.assertEqual(result.block_count, 2)
        self.assertEqual(len(encoded), 144)
        self.assertEqual(result.encoded_sha256, hashlib.sha256(encoded).hexdigest())

        verified = verify_xbox_ima_stream(io.BytesIO(encoded), self.slot)
        decoded = b"".join(
            decode_xbox_ima_time_block(encoded[offset:offset + 72], 2)
            for offset in range(0, len(encoded), 72)
        )
        self.assertEqual(verified.encoded_sha256, result.encoded_sha256)
        self.assertEqual(verified.decoded_pcm_sha256, result.decoded_pcm_sha256)
        self.assertEqual(verified.decoded_pcm_sha256, hashlib.sha256(decoded).hexdigest())
        second = io.BytesIO()
        encode_strict_pcm16_wav(io.BytesIO(_wav()), second, self.slot)
        self.assertEqual(second.getvalue(), encoded)

        before = {
            "0": bytes((index * 3 + 1) & 0xFF for index in range(256)),
            "1": bytes((index * 5 + 7) & 0xFF for index in range(256)),
        }
        packs = {name: bytearray(payload) for name, payload in before.items()}
        descriptor_bytes = bytes((index * 11) & 0xFF for index in range(173))
        descriptor_before = descriptor_bytes
        for span in spans:
            packs[span.pack_name][span.pack_offset:span.pack_offset + span.length] = \
                encoded[span.payload_offset:span.payload_offset + span.length]

        expected = {name: bytearray(payload) for name, payload in before.items()}
        expected["0"][206:256] = encoded[:50]
        expected["1"][0:94] = encoded[50:]
        self.assertEqual(packs, expected)
        self.assertEqual(
            b"".join(
                packs[span.pack_name][span.pack_offset:span.pack_offset + span.length]
                for span in spans
            ),
            encoded,
        )
        self.assertEqual(descriptor_bytes, descriptor_before)

    def test_strict_wav_shape_and_metadata_fail_closed_with_empty_output(self) -> None:
        cases = {
            "sample rate": _wav(rate=44_100),
            "channels": _wav(channels=1),
            "frame count": _wav(frames=64),
            "metadata": _wav_with_metadata(),
            "trailing bytes": _wav(trailing=b"not-part-of-data"),
        }
        for label, wav in cases.items():
            with self.subTest(label=label):
                output = io.BytesIO()
                with self.assertRaises(Nfl2k5AusbFixedSlotError):
                    encode_strict_pcm16_wav(io.BytesIO(wav), output, self.slot)
                self.assertEqual(output.getvalue(), b"")

    def test_cancellation_occurs_between_blocks_and_rolls_back_output(self) -> None:
        completed = []
        output = io.BytesIO()
        with self.assertRaisesRegex(StreamingEncodeCancelled, "before block 2"):
            encode_strict_pcm16_wav(
                io.BytesIO(_wav()),
                output,
                self.slot,
                progress=lambda update: completed.append(update.completed_blocks),
                cancelled=lambda: completed == [0, 1],
                progress_interval_blocks=1,
            )
        self.assertEqual(completed, [0, 1])
        self.assertEqual(output.getvalue(), b"")
        self.assertEqual(output.tell(), 0)

    def test_structural_verifier_rejects_bad_index_truncation_and_trailing(self) -> None:
        valid = bytes(self.slot.encoded_size)
        bad_index = bytearray(valid)
        struct.pack_into("<H", bad_index, 2, 89)
        cases = (bytes(bad_index), valid[:-1], valid + b"x")
        for payload in cases:
            with self.subTest(size=len(payload)):
                with self.assertRaises(Nfl2k5AusbFixedSlotError):
                    verify_xbox_ima_stream(io.BytesIO(payload), self.slot)

    def test_conflicting_alias_shape_and_nonidentical_overlap_fail_closed(self) -> None:
        conflicting = Nfl2k5StreamingAudioRange(
            _bank(descriptor=12, channels=1), 0, 0, 144
        )
        with self.assertRaisesRegex(
            Nfl2k5AusbFixedSlotError, "Aliased streaming owners disagree"
        ):
            build_streaming_slot_catalog(
                (self.logical_ranges[0], conflicting), self.archive
            )

        first_bank = _bank(descriptor=13, channels=1, boundaries=(0, 72, 144))
        second_bank = _bank(descriptor=14, channels=1, boundaries=(0, 36, 144))
        overlapping = (
            Nfl2k5StreamingAudioRange(first_bank, 0, 0, 72),
            Nfl2k5StreamingAudioRange(second_bank, 1, 36, 144),
        )
        with self.assertRaisesRegex(
            Nfl2k5AusbFixedSlotError, "Non-identical streaming ranges overlap"
        ):
            build_streaming_slot_catalog(overlapping, self.archive)

    def test_entry_segments_must_equal_the_ordered_virtual_projection(self) -> None:
        legitimate = self.archive.entries[0].segments
        forged_cases = {
            "reversed seam": tuple(reversed(legitimate)),
            "duplicate": (
                Segment(0, "0", 100, 72),
                Segment(0, "0", 100, 72),
            ),
            "overlap": (
                Segment(0, "0", 100, 80),
                Segment(0, "0", 150, 64),
            ),
            "wrong same-size projection": (
                Segment(0, "0", 0, 50),
                Segment(1, "1", 0, 94),
            ),
        }
        for label, segments in forged_cases.items():
            with self.subTest(label=label):
                forged_entry = replace(self.archive.entries[0], segments=segments)
                forged_archive = replace(self.archive, entries=(forged_entry,))
                with self.assertRaisesRegex(
                    Nfl2k5AusbFixedSlotError,
                    "exact ordered virtual projection",
                ):
                    build_streaming_slot_catalog(
                        (self.logical_ranges[0],), forged_archive
                    )


if __name__ == "__main__":
    unittest.main()
