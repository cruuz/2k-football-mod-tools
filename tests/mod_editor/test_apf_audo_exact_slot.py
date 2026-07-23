from __future__ import annotations

from dataclasses import replace
from contextlib import redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import struct
import sys
import tempfile
import unittest
from unittest import mock
import wave
import zlib


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_audo_exact_slot as writer  # noqa: E402
import apf_audio  # noqa: E402
import apf_inner  # noqa: E402


def packet_payload(packet_count: int = 1, first_word: int = 0x08000000) -> bytes:
    packets: list[bytes] = []
    for index in range(packet_count):
        packet = bytearray(apf_audio.XMA_PACKET_SIZE)
        struct.pack_into(">I", packet, 0, first_word)
        packet[4:] = bytes(((position + index) % 251) + 1 for position in range(len(packet) - 4))
        packets.append(bytes(packet))
    return b"".join(packets)


def source_fingerprints(*payloads: bytes) -> writer.SourceAudioFingerprints:
    packet_hashes = {
        hashlib.sha256(payload[offset : offset + writer.SOURCE_PACKET_SIZE]).digest()
        for payload in payloads
        for offset in range(0, len(payload), writer.SOURCE_PACKET_SIZE)
    }
    return writer.SourceAudioFingerprints(
        domain=writer.SOURCE_AUDIO_DOMAIN,
        payload_sha256s=frozenset(
            hashlib.sha256(payload).hexdigest() for payload in payloads
        ),
        packet_sha256s=frozenset(packet_hashes),
        payload_occurrence_count=writer.EXPECTED_STANDALONE_AUDO_COUNT,
        packet_occurrence_count=max(1, len(packet_hashes)),
    )


def target_for(payload: bytes, **changes: int) -> writer.ExactSlotTarget:
    values = {
        "channels": 2,
        "sample_rate": 48_000,
        "encoded_size": len(payload),
        "declared_sample_count": 512,
        "loop_start_bit": 32,
        "loop_end_bit": len(payload) * 8 - 32,
        "loop_subframe": 3,
    }
    values.update(changes)
    return writer.ExactSlotTarget(**values)


def riff_for(payload: bytes, target: writer.ExactSlotTarget) -> bytes:
    return apf_audio.make_xma1_riff(
        payload,
        target.channels,
        target.sample_rate,
        target.loop_start_bit,
        target.loop_end_bit,
        target.loop_subframe,
    )


def append_chunk(riff: bytes, chunk_id: bytes, payload: bytes) -> bytes:
    chunk = chunk_id + struct.pack("<I", len(payload)) + payload
    if len(payload) & 1:
        chunk += b"\0"
    body = riff[8:] + chunk
    return b"RIFF" + struct.pack("<I", len(body)) + body


class PcmRunner:
    def __init__(
        self,
        *,
        channels: int,
        sample_rate: int,
        frames: int,
        returncode: int = 0,
        stderr: bytes = b"",
        create_output: bool = True,
    ) -> None:
        self.channels = channels
        self.sample_rate = sample_rate
        self.frames = frames
        self.returncode = returncode
        self.stderr = stderr
        self.create_output = create_output
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command: list[str], **kwargs: object) -> SimpleNamespace:
        self.calls.append((command, kwargs))
        if self.create_output:
            with wave.open(command[-1], "wb") as output:
                output.setnchannels(self.channels)
                output.setsampwidth(2)
                output.setframerate(self.sample_rate)
                output.writeframes(b"\0" * self.frames * self.channels * 2)
        return SimpleNamespace(returncode=self.returncode, stderr=self.stderr, stdout=b"")


class RiffAndValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = packet_payload(2)
        self.target = target_for(self.payload)
        self.riff = riff_for(self.payload, self.target)
        independent_source = bytearray(packet_payload(1))
        independent_source[16] ^= 0x80
        self.source_fingerprints = source_fingerprints(bytes(independent_source))

    def test_strict_one_stream_parser_recovers_only_packet_payload(self) -> None:
        parsed = writer.parse_xma1_riff(self.riff)
        self.assertEqual(parsed.channels, 2)
        self.assertEqual(parsed.sample_rate, 48_000)
        self.assertEqual(parsed.bits_per_sample, 16)
        self.assertEqual(parsed.payload, self.payload)
        self.assertEqual(parsed.ancillary_chunk_count, 0)

        with_extra = append_chunk(self.riff, b"JUNK", b"user note")
        parsed_extra = writer.parse_xma1_riff(with_extra)
        self.assertEqual(parsed_extra.payload, self.payload)
        self.assertEqual(parsed_extra.ancillary_chunk_count, 1)

    def test_riff_container_and_fmt_corruption_fail_closed(self) -> None:
        cases: list[tuple[str, bytes, str]] = []

        wrong_size = bytearray(self.riff)
        struct.pack_into("<I", wrong_size, 4, len(wrong_size))
        cases.append(("size", bytes(wrong_size), "size"))

        wrong_tag = bytearray(self.riff)
        struct.pack_into("<H", wrong_tag, 20, 1)
        cases.append(("tag", bytes(wrong_tag), "format tag"))

        two_streams = bytearray(self.riff)
        struct.pack_into("<H", two_streams, 28, 2)
        cases.append(("streams", bytes(two_streams), "one stream"))

        wrong_pseudo = bytearray(self.riff)
        struct.pack_into("<I", wrong_pseudo, 32, 1)
        cases.append(("pseudo", bytes(wrong_pseudo), "pseudo-byte rate"))

        duplicate_data = append_chunk(self.riff, b"data", self.payload)
        cases.append(("duplicate data", duplicate_data, "exactly one data"))

        truncated = self.riff[:-1]
        cases.append(("truncated", truncated, "size"))

        for label, data, pattern in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(writer.ExactSlotImportError, pattern):
                    writer.parse_xma1_riff(data)

    def test_non_packet_multiple_and_nonzero_riff_padding_are_rejected(self) -> None:
        malformed = apf_audio.make_xma1_riff(
            self.payload,
            2,
            48_000,
            32,
            len(self.payload) * 8 - 32,
            3,
        )
        data_offset = malformed.index(b"data")
        shortened = bytearray(malformed[:-2])
        struct.pack_into("<I", shortened, 4, len(shortened) - 8)
        struct.pack_into("<I", shortened, data_offset + 4, len(self.payload) - 2)
        with self.assertRaisesRegex(writer.ExactSlotImportError, "packet multiple"):
            writer.parse_xma1_riff(bytes(shortened))

        padded = append_chunk(self.riff, b"note", b"x")
        corrupted_pad = bytearray(padded)
        corrupted_pad[-1] = 7
        with self.assertRaisesRegex(writer.ExactSlotImportError, "nonzero pad"):
            writer.parse_xma1_riff(bytes(corrupted_pad))

    def test_target_shape_and_every_apf_packet_header_field_are_enforced(self) -> None:
        with self.assertRaisesRegex(writer.ExactSlotImportError, "requires 1"):
            writer._prepare_validation_riff(
                self.riff, replace(self.target, channels=1)
            )
        with self.assertRaisesRegex(writer.ExactSlotImportError, "requires 22050"):
            writer._prepare_validation_riff(
                self.riff, replace(self.target, sample_rate=22_050)
            )
        with self.assertRaisesRegex(writer.ExactSlotImportError, "requires 6144"):
            writer._prepare_validation_riff(
                self.riff,
                replace(self.target, encoded_size=len(self.payload) + 2048),
            )

        invalid_words = {
            "sequence nibble 0": 0x18000000,
            "classify as XMA1": 0x00000000,
            "packet skip 0": 0x08000001,
        }
        for expected, word in invalid_words.items():
            invalid = packet_payload(1, word)
            invalid_target = target_for(invalid)
            with self.subTest(word=f"0x{word:08x}"):
                with self.assertRaisesRegex(writer.ExactSlotImportError, expected):
                    writer._prepare_validation_riff(
                        riff_for(invalid, invalid_target), invalid_target
                    )

    def test_import_returns_raw_packets_only_and_decodes_ephemeral_target_wrapper(self) -> None:
        supplied = append_chunk(self.riff, b"JUNK", b"discard me")
        runner = PcmRunner(
            channels=2,
            sample_rate=48_000,
            frames=self.target.declared_sample_count + 127,
        )
        with mock.patch.object(writer.subprocess, "run", runner):
            result = writer.validate_exact_slot_import(
                supplied,
                self.target,
                self.source_fingerprints,
                ffmpeg_path="/fixture/ffmpeg",
            )

        self.assertEqual(result.payload, self.payload)
        self.assertFalse(hasattr(result, "canonical_riff"))
        self.assertEqual(len(runner.calls), 1)
        command, kwargs = runner.calls[0]
        self.assertIn("-xerror", command)
        self.assertEqual(command[command.index("-f") + 1], "wav")
        ephemeral = writer.parse_xma1_riff(kwargs["input"])
        self.assertEqual(ephemeral.payload, self.payload)
        self.assertEqual(ephemeral.ancillary_chunk_count, 0)
        self.assertEqual(ephemeral.loop_start_bit, self.target.loop_start_bit)
        self.assertEqual(ephemeral.loop_end_bit, self.target.loop_end_bit)

        receipt_text = result.receipt_bytes.decode("ascii")
        self.assertEqual(result.receipt_bytes, writer.encode_receipt(result.receipt))
        self.assertIn('"input_kind":"riff_xma1"', receipt_text)
        self.assertIn('"input_ancillary_chunks_discarded":1', receipt_text)
        self.assertNotIn("loop_start", receipt_text)
        self.assertNotIn("loop_end", receipt_text)
        self.assertNotIn("loop_subframe", receipt_text)
        self.assertNotIn(self.payload[:32].hex(), receipt_text)
        for source_digest in self.source_fingerprints.payload_sha256s:
            self.assertNotIn(source_digest, receipt_text)
        for source_packet_digest in self.source_fingerprints.packet_sha256s:
            self.assertNotIn(source_packet_digest.hex(), receipt_text)
        self.assertEqual(
            result.receipt["replacement"]["payload_sha256"],
            hashlib.sha256(self.payload).hexdigest(),
        )
        self.assertEqual(
            result.receipt["validation"]["decode"]["target_minus_decoded_samples"],
            -127,
        )

    def test_packet_gate_rejects_exact_near_and_cross_source_reuse(self) -> None:
        cross_source = bytearray(self.payload)
        cross_source[32] ^= 0x20
        cross_source[writer.SOURCE_PACKET_SIZE + 32] ^= 0x40
        protected = source_fingerprints(self.payload, bytes(cross_source))

        near_source = bytearray(self.payload)
        near_source[writer.SOURCE_PACKET_SIZE + 64] ^= 0x01

        independent = bytearray(self.payload)
        independent[64] ^= 0x02
        independent[writer.SOURCE_PACKET_SIZE + 64] ^= 0x04

        cross_reuse = bytearray(independent)
        cross_reuse[writer.SOURCE_PACKET_SIZE :] = cross_source[
            writer.SOURCE_PACKET_SIZE :
        ]

        runner = PcmRunner(
            channels=2,
            sample_rate=48_000,
            frames=self.target.declared_sample_count,
        )
        with mock.patch.object(writer.subprocess, "run", runner):
            with self.assertRaisesRegex(
                writer.ExactSlotImportError, "complete audio payload"
            ):
                writer.validate_exact_slot_import(
                    self.riff,
                    self.target,
                    protected,
                    ffmpeg_path="/fixture/ffmpeg",
                )
            with self.assertRaisesRegex(
                writer.ExactSlotImportError, "reuses a complete 0x800-byte"
            ):
                writer.validate_exact_slot_import(
                    riff_for(bytes(near_source), self.target),
                    self.target,
                    protected,
                    ffmpeg_path="/fixture/ffmpeg",
                )
            with self.assertRaisesRegex(
                writer.ExactSlotImportError, "reuses a complete 0x800-byte"
            ):
                writer.validate_exact_slot_import(
                    riff_for(bytes(cross_reuse), self.target),
                    self.target,
                    protected,
                    ffmpeg_path="/fixture/ffmpeg",
                )
            accepted = writer.validate_exact_slot_import(
                riff_for(bytes(independent), self.target),
                self.target,
                protected,
                ffmpeg_path="/fixture/ffmpeg",
            )
        self.assertEqual(accepted.payload, bytes(independent))
        self.assertEqual(len(runner.calls), 1)

    def test_raw_project_payload_gets_cheap_and_complete_reauthorization(self) -> None:
        self.assertEqual(
            writer.validate_stored_payload(self.payload, self.target), self.payload
        )
        with self.assertRaisesRegex(writer.ExactSlotImportError, "exact slot"):
            writer.validate_stored_payload(self.payload[:2048], self.target)

        runner = PcmRunner(
            channels=2,
            sample_rate=48_000,
            frames=self.target.declared_sample_count,
        )
        with mock.patch.object(writer.subprocess, "run", runner):
            result = writer.validate_stored_payload_complete(
                self.payload,
                self.target,
                self.source_fingerprints,
                ffmpeg_path="/fixture/ffmpeg",
            )
        self.assertEqual(result.payload, self.payload)
        self.assertEqual(
            result.receipt["validation"]["input_kind"], "raw_xma1_packets"
        )

    def test_staged_payload_pcm_preview_is_verified_and_published_no_replace(self) -> None:
        runner = PcmRunner(
            channels=2,
            sample_rate=48_000,
            frames=self.target.declared_sample_count,
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "replacement-preview.wav"
            with mock.patch.object(writer.subprocess, "run", runner):
                receipt = writer.decode_stored_payload_to_wav(
                    self.payload,
                    self.target,
                    destination,
                    ffmpeg_path="/fixture/ffmpeg",
                )
            self.assertTrue(destination.is_file())
            layout = apf_audio.parse_pcm_wav(destination)
            self.assertEqual(layout["channels"], 2)
            self.assertEqual(layout["sample_rate"], 48_000)
            self.assertEqual(receipt["schema"], writer.WAV_EXPORT_SCHEMA)
            self.assertTrue(receipt["atomic_no_replace"])
            self.assertFalse(receipt["contains_target_wrapper"])
            self.assertNotIn(str(destination), str(receipt))
            self.assertEqual(
                receipt["wav_sha256"], hashlib.sha256(destination.read_bytes()).hexdigest()
            )
            with self.assertRaisesRegex(writer.ExactSlotImportError, "already exists"):
                writer.decode_stored_payload_to_wav(
                    self.payload,
                    self.target,
                    destination,
                    ffmpeg_path="/fixture/ffmpeg",
                )

    def test_failed_pcm_preview_leaves_no_destination_or_hidden_temp(self) -> None:
        runner = PcmRunner(
            channels=2,
            sample_rate=48_000,
            frames=self.target.declared_sample_count,
            returncode=1,
            stderr=b"synthetic failure",
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "failed.wav"
            with mock.patch.object(writer.subprocess, "run", runner):
                with self.assertRaisesRegex(writer.ExactSlotImportError, "decode cleanly"):
                    writer.decode_stored_payload_to_wav(
                        self.payload,
                        self.target,
                        destination,
                        ffmpeg_path="/fixture/ffmpeg",
                    )
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_ffmpeg_error_layout_error_and_128_sample_delta_are_rejected(self) -> None:
        runners = (
            (
                PcmRunner(
                    channels=2,
                    sample_rate=48_000,
                    frames=512,
                    returncode=1,
                    stderr=b"synthetic decoder error",
                ),
                "did not decode cleanly",
            ),
            (
                PcmRunner(channels=1, sample_rate=48_000, frames=512),
                "Decoded replacement has 1 channel",
            ),
            (
                PcmRunner(channels=2, sample_rate=44_100, frames=512),
                "Decoded replacement is 44100 Hz",
            ),
            (
                PcmRunner(channels=2, sample_rate=48_000, frames=640),
                "allowed -127 through 127",
            ),
        )
        for runner, pattern in runners:
            with self.subTest(pattern=pattern):
                with mock.patch.object(writer.subprocess, "run", runner):
                    with self.assertRaisesRegex(writer.ExactSlotImportError, pattern):
                        writer.validate_exact_slot_import(
                            self.riff,
                            self.target,
                            self.source_fingerprints,
                            ffmpeg_path="/fixture/ffmpeg",
                        )

    def test_target_metadata_aliases_agree_and_reject_bool_or_bad_bounds(self) -> None:
        metadata = {
            "derived_channel_count": 2,
            "sample_rate": 48_000,
            "encoded_size": len(self.payload),
            "declared_sample_count": 512,
            "xma1_loop_start_bit_candidate": 32,
            "xma1_loop_end_bit_candidate": len(self.payload) * 8 - 32,
            "xma1_loop_subframe_candidate": 3,
        }
        self.assertEqual(writer.target_from_metadata(metadata), self.target)
        with self.assertRaisesRegex(writer.ExactSlotImportError, "whole number"):
            writer.target_from_metadata({**metadata, "sample_rate": True})
        with self.assertRaisesRegex(writer.ExactSlotImportError, "disagrees"):
            writer.target_from_metadata({**metadata, "channels": 1})
        with self.assertRaisesRegex(writer.ExactSlotImportError, "bit bounds"):
            writer.validate_target(
                replace(self.target, loop_end_bit=len(self.payload) * 8 + 1)
            )

    def test_standalone_cli_prints_receipt_only_and_refuses_source_payload(self) -> None:
        resolved = writer.ResolvedExactSlot(
            asset_id="apf:audio:audo:7:0",
            name="synthetic",
            outer_index=7,
            inner_index=0,
            target=self.target,
            pack_name="0A",
            pack_offset=0x1000,
            encoded_size=len(self.payload),
            source_payload_sha256="1" * 64,
        )
        result = writer.ExactSlotImportResult(
            payload=self.payload,
            receipt={"schema": writer.SCHEMA, "status": "accepted"},
        )
        with tempfile.TemporaryDirectory() as directory:
            supplied = Path(directory) / "user.xma"
            supplied.write_bytes(self.riff)
            stdout = StringIO()
            with (
                mock.patch.object(writer, "resolve_target", return_value=resolved),
                mock.patch.object(
                    writer, "validate_exact_slot_import", return_value=result
                ),
                mock.patch.object(
                    writer,
                    "original_audio_fingerprints",
                    return_value=self.source_fingerprints,
                ),
                redirect_stdout(stdout),
            ):
                status = writer.main(
                    [
                        "/synthetic/0A",
                        "--entry",
                        "7",
                        "--file",
                        "0",
                        "--input-xma",
                        str(supplied),
                        "--validate-exact-slot",
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(stdout.getvalue().encode("ascii"), result.receipt_bytes)
            self.assertNotIn(self.payload[:32].hex(), stdout.getvalue())

            stderr = StringIO()
            with (
                mock.patch.object(writer, "resolve_target", return_value=resolved),
                mock.patch.object(
                    writer, "validate_exact_slot_import", return_value=result
                ),
                mock.patch.object(
                    writer,
                    "original_audio_fingerprints",
                    return_value=source_fingerprints(self.payload),
                ),
                redirect_stderr(stderr),
            ):
                status = writer.main(
                    [
                        "/synthetic/0A",
                        "--entry",
                        "7",
                        "--file",
                        "0",
                        "--input-xma",
                        str(supplied),
                        "--validate-exact-slot",
                    ]
                )
            self.assertEqual(status, 2)
            self.assertIn("complete audio payload", stderr.getvalue())


class FakeArchiveReader:
    def __init__(self, metadata: bytes, payload: bytes, record: object) -> None:
        self.metadata = metadata
        self.payload = payload
        self.record = record

    def __enter__(self) -> "FakeArchiveReader":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _entry: object, offset: int, size: int) -> bytes:
        metadata_block = self.record.blocks[0]
        payload_block = self.record.blocks[1]
        if offset == metadata_block.start_offset and size == len(self.metadata):
            return self.metadata
        if offset == payload_block.start_offset + 0x20 and size == len(self.payload):
            return self.payload
        raise AssertionError(f"unexpected synthetic source read: {offset:#x}+{size:#x}")


def source_fixture(item_count: int = 1) -> tuple[object, object, FakeArchiveReader, bytes]:
    payload = packet_payload(1)
    metadata = struct.pack(
        ">11I",
        1,
        5,
        5,
        512,
        48_000,
        0,
        len(payload),
        0,
        32,
        len(payload) * 8 - 32,
        3,
    )
    segment = SimpleNamespace(pack_name="0A", pack_offset=0x1000, size=0x8000)
    entry = SimpleNamespace(
        table_index=7,
        head_hex=f"{apf_inner.IFF_MAGIC:08x}",
        segments=(segment,),
    )
    dram_hash = zlib.crc32(b"DRAM") & 0xFFFFFFFF
    sram_hash = zlib.crc32(b"SRAM") & 0xFFFFFFFF
    blocks = (
        SimpleNamespace(
            type_hash=dram_hash,
            is_compressed=False,
            uncompressed_length=len(metadata),
            start_offset=0x80,
        ),
        SimpleNamespace(
            type_hash=sram_hash,
            is_compressed=False,
            uncompressed_length=len(payload) + 0x40,
            start_offset=0x200,
        ),
    )
    parts = (
        apf_inner.FilePart(block_index=0, offset=0, length=len(metadata)),
        apf_inner.FilePart(block_index=1, offset=0x20, length=len(payload)),
    )
    items = tuple(
        apf_inner.DataFile(
            index=index,
            file_id=0x1000 + index,
            type_hash=zlib.crc32(b"AUDO") & 0xFFFFFFFF,
            offsets=(),
            parts=parts,
            name=f"synthetic_{index:04d}",
            type_name="AUDO",
        )
        for index in range(item_count)
    )
    record = SimpleNamespace(entry=entry, warnings=[], blocks=blocks, files=items)
    archive = SimpleNamespace(entries=(entry,))
    return archive, record, FakeArchiveReader(metadata, payload, record), payload


class SourceResolverTests(unittest.TestCase):
    def _patch_source(self, archive: object, record: object, reader: FakeArchiveReader):
        return (
            mock.patch.object(writer.apf_outer, "parse_archive", return_value=archive),
            mock.patch.object(writer.apf_inner, "parse_iff", return_value=record),
            mock.patch.object(writer.apf_inner, "ArchiveReader", return_value=reader),
        )

    def test_resolver_pins_stable_identity_and_one_absolute_0a_span(self) -> None:
        archive, record, reader, payload = source_fixture()
        patches = self._patch_source(archive, record, reader)
        with patches[0], patches[1], patches[2]:
            resolved = writer.resolve_target(Path("/synthetic/0A"), 7, 0)

        self.assertEqual(resolved.asset_id, "apf:audio:audo:7:0")
        self.assertEqual(resolved.name, "synthetic_0000")
        self.assertEqual(resolved.pack_name, "0A")
        self.assertEqual(resolved.pack_offset, 0x1220)
        self.assertEqual(resolved.encoded_size, len(payload))
        self.assertEqual(resolved.target.channels, 2)
        self.assertEqual(
            resolved.source_payload_sha256, hashlib.sha256(payload).hexdigest()
        )

    def test_batch_resolver_uses_one_archive_reader_and_one_parse_per_outer(self) -> None:
        archive, record, reader, _payload = source_fixture(3)
        parse = mock.Mock(return_value=record)
        with (
            mock.patch.object(writer.apf_outer, "parse_archive", return_value=archive),
            mock.patch.object(writer.apf_inner, "parse_iff", parse),
            mock.patch.object(writer.apf_inner, "ArchiveReader", return_value=reader),
        ):
            resolved = writer.resolve_targets(
                Path("/synthetic/0A"), ((7, 2), (7, 0), (7, 1))
            )
        self.assertEqual(tuple(resolved), ((7, 0), (7, 1), (7, 2)))
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(resolved[(7, 2)].asset_id, "apf:audio:audo:7:2")
        with self.assertRaisesRegex(writer.ExactSlotImportError, "selected twice"):
            writer.resolve_targets(Path("/synthetic/0A"), ((7, 0), (7, 0)))

    def test_resolver_rejects_compressed_or_non_0a_sram(self) -> None:
        archive, record, reader, _payload = source_fixture()
        record.blocks[1].is_compressed = True
        patches = self._patch_source(archive, record, reader)
        with patches[0], patches[1], patches[2]:
            with self.assertRaisesRegex(writer.ExactSlotImportError, "compressed"):
                writer.resolve_target(Path("/synthetic/0A"), 7, 0)

        archive, record, reader, _payload = source_fixture()
        record.entry.segments[0].pack_name = "1B"
        patches = self._patch_source(archive, record, reader)
        with patches[0], patches[1], patches[2]:
            with self.assertRaisesRegex(writer.ExactSlotImportError, "not the bounded 0A"):
                writer.resolve_target(Path("/synthetic/0A"), 7, 0)

    def test_one_pass_inventory_covers_all_payloads_and_packets_without_bytes(self) -> None:
        archive, record, reader, payload = source_fixture(
            writer.EXPECTED_STANDALONE_AUDO_COUNT
        )
        patches = self._patch_source(archive, record, reader)
        with patches[0], patches[1], patches[2]:
            inventory = writer.original_audio_fingerprints(Path("/synthetic/0A"))
        self.assertEqual(
            inventory.payload_sha256s,
            frozenset((hashlib.sha256(payload).hexdigest(),)),
        )
        self.assertEqual(
            inventory.packet_sha256s,
            frozenset((hashlib.sha256(payload).digest(),)),
        )
        self.assertEqual(
            inventory.payload_occurrence_count,
            writer.EXPECTED_STANDALONE_AUDO_COUNT,
        )
        self.assertEqual(
            inventory.packet_occurrence_count,
            writer.EXPECTED_STANDALONE_AUDO_COUNT,
        )

    def test_hash_inventory_fails_if_the_complete_source_count_changes(self) -> None:
        archive, record, reader, _payload = source_fixture(2)
        patches = self._patch_source(archive, record, reader)
        with patches[0], patches[1], patches[2]:
            with self.assertRaisesRegex(writer.ExactSlotImportError, "found 2, expected 2261"):
                writer.original_payload_hashes(Path("/synthetic/0A"))


if __name__ == "__main__":
    unittest.main()
