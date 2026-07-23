from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_audio  # noqa: E402
import apf_audo_exact_slot  # noqa: E402
import apf_ausb_exact_slot as writer  # noqa: E402


PRIVATE_SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def packet_payload(packet_count: int, seed: int = 1) -> bytes:
    packets = []
    for packet_index in range(packet_count):
        packet = bytearray(apf_audio.XMA_PACKET_SIZE)
        struct.pack_into(">I", packet, 0, 0x08000000)
        packet[4:] = bytes(
            ((position + packet_index + seed) % 251) + 1
            for position in range(apf_audio.XMA_PACKET_SIZE - 4)
        )
        packets.append(bytes(packet))
    return b"".join(packets)


def source_fingerprints(
    payload_hashes: frozenset[str],
    *payloads: bytes,
) -> apf_audo_exact_slot.SourceAudioFingerprints:
    packet_hashes = {
        hashlib.sha256(
            payload[offset : offset + apf_audio.XMA_PACKET_SIZE]
        ).digest()
        for payload in payloads
        for offset in range(0, len(payload), apf_audio.XMA_PACKET_SIZE)
    }
    if not packet_hashes:
        packet_hashes.add(b"\x99" * 32)
    return apf_audo_exact_slot.SourceAudioFingerprints(
        domain=writer.SOURCE_AUDIO_DOMAIN,
        payload_sha256s=payload_hashes,
        packet_sha256s=frozenset(packet_hashes),
        payload_occurrence_count=writer.EXPECTED_CANONICAL_RANGE_COUNT,
        packet_occurrence_count=len(packet_hashes),
    )


def owner(
    *,
    bank_name: str = "testbank",
    channels: int = 2,
    sample_rate: int = 48_000,
    outer: int = 10,
    inner: int = 20,
    substream: int = 3,
) -> writer.AusbOwner:
    return writer.AusbOwner(
        descriptor_outer_index=outer,
        descriptor_inner_index=inner,
        substream_index=substream,
        bank_name=bank_name,
        external_filename=f"{bank_name}.bin",
        channels=channels,
        sample_rate=sample_rate,
        duration_value_bits=0x3F800000,
        duration_seconds=1.0,
        declared_sample_count=sample_rate,
    )


def target(
    payload: bytes,
    *,
    target_owner: writer.AusbOwner | None = None,
    owners: tuple[writer.AusbOwner, ...] | None = None,
    spans: tuple[writer.PhysicalSpan, ...] | None = None,
    canonical: str = "apf:audio:ausb:physical:99:0:4096",
) -> writer.ResolvedExactSlot:
    target_owner = target_owner or owner()
    owners = owners or (target_owner,)
    spans = spans or (
        writer.PhysicalSpan("0A", 0x1000, len(payload), 0),
    )
    return writer.ResolvedExactSlot(
        asset_id=target_owner.asset_id,
        requested_owner=target_owner,
        owners=owners,
        canonical_physical_id=canonical,
        external_outer_index=99,
        external_range_offset=0,
        target=writer.ExactSlotTarget(
            channels=target_owner.channels,
            sample_rate=target_owner.sample_rate,
            encoded_size=len(payload),
            declared_sample_count=target_owner.declared_sample_count,
        ),
        physical_spans=spans,
        source_payload_sha256="a" * 64,
    )


def nested_result(payload: bytes) -> apf_audo_exact_slot.ExactSlotImportResult:
    return apf_audo_exact_slot.ExactSlotImportResult(
        payload=payload,
        receipt={
            "schema": apf_audo_exact_slot.SCHEMA,
            "validation": {
                "input_kind": "riff_xma1",
                "decode": {
                    "status": "decoder_verified_exact_target_samples",
                    "channels": 2,
                    "sample_rate": 48_000,
                    "decoded_sample_count_per_channel": 48_000,
                    "target_minus_decoded_samples": 0,
                    "ffmpeg_xerror": True,
                },
            },
        },
    )


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = packet_payload(2)
        self.other_payload = packet_payload(2, seed=17)
        self.target = target(self.payload)
        self.hashes = frozenset({"1" * 64, "2" * 64})
        self.hash_count = mock.patch.object(
            writer, "EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT", 2
        )
        self.hash_count.start()
        self.fingerprints = source_fingerprints(self.hashes)

    def tearDown(self) -> None:
        self.hash_count.stop()

    def test_product_facing_constants_are_exact(self) -> None:
        self.assertEqual(writer.SCHEMA, "apf2k8_ausb_exact_slot_import/v1")
        self.assertEqual(writer.MODIFICATION_KIND, "ausb_exact_slot_xma1")
        self.assertEqual(writer.ASSET_ID_PREFIX, "apf:audio:ausb")

    def test_import_wraps_strict_validator_and_receipt_contains_no_source_bytes(self) -> None:
        supplied = b"synthetic RIFF input"
        with mock.patch.object(
            apf_audo_exact_slot,
            "validate_exact_slot_import",
            return_value=nested_result(self.other_payload),
        ) as validate:
            result = writer.validate_exact_slot_import(
                supplied,
                self.target,
                self.fingerprints,
                ffmpeg_path="/fixture/ffmpeg",
            )
        validate.assert_called_once()
        self.assertEqual(result.payload, self.other_payload)
        self.assertEqual(result.receipt["schema"], writer.SCHEMA)
        self.assertFalse(result.receipt["shared_effect"])
        self.assertEqual(result.receipt["owner_asset_ids"], [self.target.asset_id])
        receipt = result.receipt_bytes.decode("ascii")
        self.assertIn(hashlib.sha256(self.other_payload).hexdigest(), receipt)
        self.assertNotIn(self.other_payload[:32].hex(), receipt)
        self.assertNotIn("source_payload_sha256", receipt)
        self.assertNotIn(str(PRIVATE_SOURCE), receipt)
        for source_digest in self.fingerprints.payload_sha256s:
            self.assertNotIn(source_digest, receipt)
        for source_packet_digest in self.fingerprints.packet_sha256s:
            self.assertNotIn(source_packet_digest.hex(), receipt)
        self.assertFalse(result.receipt["descriptor_policy"]["descriptor_bytes_changed"])
        self.assertFalse(
            result.receipt["descriptor_policy"]["explicit_substream_loop_fields_present"]
        )

    def test_complete_hash_gate_and_any_retail_payload_are_rejected(self) -> None:
        with self.assertRaisesRegex(writer.AusbExactSlotError, "complete source"):
            writer.validate_stored_payload(self.payload, self.target, {"1" * 64})

        retail_hash = hashlib.sha256(self.other_payload).hexdigest()
        hashes = frozenset({retail_hash, "2" * 64})
        fingerprints = source_fingerprints(hashes, self.other_payload)
        with mock.patch.object(
            apf_audo_exact_slot,
            "validate_exact_slot_import",
            return_value=nested_result(self.other_payload),
        ):
            with self.assertRaisesRegex(
                writer.AusbExactSlotError, "complete audio payload"
            ):
                writer.validate_exact_slot_import(
                    b"input",
                    self.target,
                    fingerprints,
                    ffmpeg_path="/fixture/ffmpeg",
                )

    def test_packet_gate_rejects_exact_near_and_cross_source_reuse(self) -> None:
        second_source = packet_payload(2, seed=41)
        protected_hashes = frozenset(
            {
                hashlib.sha256(self.payload).hexdigest(),
                hashlib.sha256(second_source).hexdigest(),
            }
        )
        protected = source_fingerprints(
            protected_hashes,
            self.payload,
            second_source,
        )

        near_source = bytearray(self.payload)
        near_source[apf_audio.XMA_PACKET_SIZE + 64] ^= 0x01

        independent = bytearray(self.payload)
        independent[64] ^= 0x02
        independent[apf_audio.XMA_PACKET_SIZE + 64] ^= 0x04

        cross_reuse = bytearray(independent)
        cross_reuse[apf_audio.XMA_PACKET_SIZE :] = second_source[
            apf_audio.XMA_PACKET_SIZE :
        ]

        def accepted(data: bytes, *_args: object, **_kwargs: object):
            return nested_result(data)

        with mock.patch.object(
            apf_audo_exact_slot,
            "validate_exact_slot_import",
            side_effect=accepted,
        ):
            with self.assertRaisesRegex(
                writer.AusbExactSlotError, "complete audio payload"
            ):
                writer.validate_exact_slot_import(
                    self.payload, self.target, protected
                )
            with self.assertRaisesRegex(
                writer.AusbExactSlotError, "reuses a complete 0x800-byte"
            ):
                writer.validate_exact_slot_import(
                    bytes(near_source), self.target, protected
                )
            with self.assertRaisesRegex(
                writer.AusbExactSlotError, "reuses a complete 0x800-byte"
            ):
                writer.validate_exact_slot_import(
                    bytes(cross_reuse), self.target, protected
                )
            result = writer.validate_exact_slot_import(
                bytes(independent), self.target, protected
            )
        self.assertEqual(result.payload, bytes(independent))

    def test_cross_volume_compiler_slices_payload_exactly(self) -> None:
        spans = (
            writer.PhysicalSpan("0A", 0x2000, 2048, 0),
            writer.PhysicalSpan("0B", 0, 2048, 2048),
        )
        split_target = target(self.payload, spans=spans)
        writes = writer.compile_physical_writes(
            self.payload, split_target, self.hashes
        )
        self.assertEqual(
            [(item.pack_name, item.pack_offset, item.length) for item in writes],
            [("0A", 0x2000, 2048), ("0B", 0, 2048)],
        )
        self.assertEqual(b"".join(item.payload for item in writes), self.payload)
        self.assertEqual(writes[1].side_payload_offset, 2048)

    def test_alias_merge_deduplicates_identical_and_rejects_divergent_writes(self) -> None:
        original = writer.CompiledAusbWrite(
            "0A", 0x1000, self.payload[:2048], "canonical", 0
        )
        identical = writer.CompiledAusbWrite(
            "0A", 0x1000, self.payload[:2048], "canonical", 0
        )
        self.assertEqual(writer.merge_compiled_writes(((original,), (identical,))), (original,))

        divergent = writer.CompiledAusbWrite(
            "0A", 0x1000, self.other_payload[:2048], "canonical", 0
        )
        with self.assertRaisesRegex(writer.AusbExactSlotError, "Divergent"):
            writer.merge_compiled_writes(((original,), (divergent,)))

    def test_preview_wraps_existing_atomic_decoder_contract(self) -> None:
        nested = {
            "status": "decoder_verified_exact_target_samples",
            "payload_sha256": hashlib.sha256(self.payload).hexdigest(),
            "wav_sha256": "f" * 64,
            "channels": 2,
            "sample_rate": 48_000,
            "bits_per_sample": 16,
            "decoded_sample_count_per_channel": 48_000,
            "target_minus_decoded_samples": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "preview.wav"
            with mock.patch.object(
                apf_audo_exact_slot,
                "decode_stored_payload_to_wav",
                return_value=nested,
            ):
                receipt = writer.decode_stored_payload_to_wav(
                    self.payload,
                    self.target,
                    self.fingerprints,
                    destination,
                    ffmpeg_path="/fixture/ffmpeg",
                )
        self.assertEqual(receipt["schema"], writer.WAV_EXPORT_SCHEMA)
        self.assertEqual(
            receipt["payload_sha256"], hashlib.sha256(self.payload).hexdigest()
        )
        self.assertEqual(receipt["decoded_sample_count_per_channel"], 48_000)
        self.assertTrue(receipt["atomic_no_replace"])
        self.assertFalse(receipt["contains_original_payload"])

    def test_paired_jukebox_validation_requires_both_correct_sides(self) -> None:
        stereo_owner = owner(bank_name="jukeboxmusic", channels=2, sample_rate=48_000)
        mono_owner = owner(
            bank_name="jukebox22",
            channels=1,
            sample_rate=22_050,
            inner=21,
        )
        stereo_target = target(self.payload, target_owner=stereo_owner)
        mono_target = target(self.payload, target_owner=mono_owner)
        stereo_result = writer.ExactSlotImportResult(
            self.payload, {"schema": writer.SCHEMA}
        )
        mono_result = writer.ExactSlotImportResult(
            self.other_payload, {"schema": writer.SCHEMA}
        )
        with mock.patch.object(
            writer,
            "validate_exact_slot_import",
            side_effect=(stereo_result, mono_result),
        ) as validate:
            pair = writer.validate_paired_soundtrack_import(
                b"stereo",
                b"mono",
                stereo_target,
                mono_target,
                self.fingerprints,
            )
        self.assertEqual(validate.call_count, 2)
        self.assertEqual(pair.stereo.payload, self.payload)
        self.assertEqual(pair.mono.payload, self.other_payload)
        self.assertFalse(pair.receipt["retail_data"]["contains_original_payload"])


@unittest.skipUnless(PRIVATE_SOURCE.is_file(), "private APF source is unavailable")
class RecognizedSourceTests(unittest.TestCase):
    def test_jukebox_cross_volume_target_and_cwdloop_alias_are_exact(self) -> None:
        stereo, mono = writer.resolve_jukebox_pair(PRIVATE_SOURCE, 2)
        self.assertEqual(stereo.asset_id, "apf:audio:ausb:1310:21:2")
        self.assertEqual(stereo.external_outer_index, 793)
        self.assertEqual(stereo.external_range_offset, 7_301_120)
        self.assertEqual(stereo.target.encoded_size, 3_868_672)
        self.assertEqual(
            [
                (span.pack_name, span.pack_offset, span.length, span.payload_offset)
                for span in stereo.physical_spans
            ],
            [
                ("0A", 1_138_427_904, 2_422_784, 0),
                ("0B", 0, 1_445_888, 2_422_784),
            ],
        )
        self.assertEqual(mono.asset_id, "apf:audio:ausb:1310:403:2")
        self.assertEqual(mono.target.encoded_size, 1_544_192)
        self.assertEqual(mono.target.channels, 1)
        self.assertEqual(mono.target.sample_rate, 22_050)

        aliases = writer.resolve_targets(
            PRIVATE_SOURCE, ((137, 8, 0), (659, 289, 0))
        )
        left = aliases[(137, 8, 0)]
        right = aliases[(659, 289, 0)]
        self.assertEqual(left.canonical_physical_id, right.canonical_physical_id)
        self.assertEqual(left.source_payload_sha256, right.source_payload_sha256)
        self.assertTrue(left.shared_effect)
        self.assertEqual(
            [owner.asset_id for owner in left.owners],
            ["apf:audio:ausb:137:8:0", "apf:audio:ausb:659:289:0"],
        )

    def test_complete_retail_gate_scans_every_payload_and_packet(self) -> None:
        inventory = writer.original_audio_fingerprints(PRIVATE_SOURCE)
        self.assertEqual(len(inventory.payload_sha256s), 40_316)
        self.assertEqual(
            inventory.payload_occurrence_count,
            writer.EXPECTED_CANONICAL_RANGE_COUNT,
        )
        self.assertGreater(inventory.packet_occurrence_count, 40_316)
        self.assertTrue(inventory.packet_sha256s)
        self.assertTrue(all(len(value) == 32 for value in inventory.packet_sha256s))


if __name__ == "__main__":
    unittest.main()
