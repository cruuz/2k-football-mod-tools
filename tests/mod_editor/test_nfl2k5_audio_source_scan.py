"""Synthetic, retail-free tests for the read-only 2K5 source audio scanner."""

from __future__ import annotations

from dataclasses import replace

import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from mod_editor.core import nfl2k5_audio_source_fingerprints as fingerprint_module
from mod_editor.core.model import GameId, SourceRecord
from mod_editor.core.nfl2k5_audio_source_fingerprints import (
    AudioSourceFingerprintCancelled,
    Nfl2k5AudioSourceFingerprintStore,
)
from mod_editor.core.nfl2k5_audio_source_scan import (
    AudioSourceScanError,
    AudioSourceScanPins,
    Nfl2k5AudioSourceScanner,
    decode_xbox_ima_batch,
)
from mod_editor.core.nfl2k5_ausb_fixed_slots import (
    decode_xbox_ima_time_block,
)
from mod_editor.core.nfl2k5_source_cache import SourceCache

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402


PACK0_OFFSET = 64 * 2048
PACK0_SIZE = 2 * 2048
PACK1_OFFSET = 66 * 2048
PACK1_SIZE = 9 * 2048
SOURCE_SIZE = 76 * 2048
OUTER_ID = 0x11111111
BANK_NAME = "femusic"
BANK_FILENAME = f"{BANK_NAME}.bin"
EXTERNAL_ID = zlib.crc32(BANK_FILENAME.upper().encode("utf-16le")) & 0xFFFFFFFF


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _ausb_body() -> bytes:
    body = bytearray(0xA4)
    body[0x0C:0x10] = b"AUSB"
    struct.pack_into("<i", body, 0x10, 0x20 - 0x0F)
    name = (BANK_NAME + "\0").encode("utf-16le")
    body[0x20:0x20 + len(name)] = name
    filename = (BANK_FILENAME + "\0").encode("utf-16le")
    body[0x40:0x40 + len(filename)] = filename
    struct.pack_into("<5I", body, 0x80, 2, 0, 1, 22_050, 0x12000)
    struct.pack_into("<3I", body, 0x98, 0, 36, PACK1_SIZE)
    return bytes(body)


def _audo_body(
    name: str,
    payload: bytes,
    *,
    channels: int,
    sample_rate: int,
) -> tuple[bytes, bytes]:
    system = bytearray(128)
    system[0x0C:0x10] = b"AUDO"
    struct.pack_into("<i", system, 0x10, 0x20 - 0x0F)
    struct.pack_into("<i", system, 0x14, 0x40 - 0x13)
    encoded_name = (name + "\0").encode("utf-16le")
    system[0x20:0x20 + len(encoded_name)] = encoded_name
    struct.pack_into(
        "<8I",
        system,
        0x40,
        channels,
        channels,
        0x11,
        0x35,
        len(payload),
        0,
        len(payload) // channels,
        sample_rate,
    )
    body = bytes(system) + payload + b"\0" * 12
    block_align = 36 * channels
    pcm = b"".join(
        decode_xbox_ima_time_block(
            payload[offset:offset + block_align], channels
        )
        for offset in range(0, len(payload), block_align)
    )
    return body, pcm


def _valid_bank_payload() -> bytes:
    return b"".join(
        struct.pack("<hH", (index * 31) % 4096 - 2048, index % 89)
        + bytes((index * 3 + nibble) & 0xFF for nibble in range(32))
        for index in range(PACK1_SIZE // 36)
    )


class SyntheticSourceFixture:
    def __init__(self, parent: Path) -> None:
        self.source = parent / "synthetic-source.xiso"
        self.bank_payload = _valid_bank_payload()
        body = _ausb_body()
        wrapper = struct.pack(
            "<4s7I", b"AUSB", len(body), 0, 0, 0, 0, 0, 0
        ) + body
        self.standalone_name = "synthetic-audo"
        self.standalone_payload = (
            struct.pack("<hH", 321, 17)
            + bytes((index * 7 + 3) & 0xFF for index in range(32))
        )
        audo_body, self.standalone_pcm = _audo_body(
            self.standalone_name,
            self.standalone_payload,
            channels=1,
            sample_rate=16_000,
        )
        audo_wrapper = struct.pack(
            "<4s7I",
            b"AUDO",
            len(audo_body),
            128,
            len(self.standalone_payload),
            0,
            0,
            0,
            0,
        ) + audo_body
        pack0 = bytearray(PACK0_SIZE)
        struct.pack_into("<III", pack0, 0, 2, 0, 2)
        struct.pack_into("<36I", pack0, 12, 2, 9, *([0] * 34))
        table = 0x0C + 36 * 4
        struct.pack_into("<III", pack0, table, OUTER_ID, 512, 1)
        struct.pack_into("<III", pack0, table + 12, EXTERNAL_ID, PACK1_SIZE, 2)
        pack0[2048:2048 + len(wrapper)] = wrapper
        pack0[2048 + 256:2048 + 256 + len(audo_wrapper)] = audo_wrapper
        self.pack0_payload = bytes(pack0)

        image = bytearray(SOURCE_SIZE)
        image[PACK0_OFFSET:PACK0_OFFSET + PACK0_SIZE] = self.pack0_payload
        image[PACK1_OFFSET:PACK1_OFFSET + PACK1_SIZE] = self.bank_payload
        self.source.write_bytes(image)
        self.source_sha256 = hashlib.sha256(image).hexdigest()

        self.inventory_document = {
            "schema": "nfl2k5_resource_chunk_inventory/v1",
            "summary": {"resource_chunk_count": 2},
            "chunks": [
                {
                    "outer_index": 0,
                    "outer_id": f"0x{OUTER_ID:08x}",
                    "outer_head": "AUSB",
                    "outer_size": 512,
                    "chunk_index": 0,
                    "chunk_offset": 0,
                    "zero_padding_before": 0,
                    "kind": "AUSB",
                    "stored_size": len(body),
                    "end_offset": 0x20 + len(body),
                    "word_08": 0,
                    "word_0c": 0,
                    "word_10": "0x00000000",
                    "word_14": 0,
                },
                {
                    "outer_index": 0,
                    "outer_id": f"0x{OUTER_ID:08x}",
                    "outer_head": "AUSB",
                    "outer_size": 512,
                    "chunk_index": 1,
                    "chunk_offset": 256,
                    "zero_padding_before": 0,
                    "kind": "AUDO",
                    "stored_size": len(audo_body),
                    "end_offset": 256 + 0x20 + len(audo_body),
                    "word_08": 128,
                    "word_0c": len(self.standalone_payload),
                    "word_10": "0x00000000",
                    "word_14": 0,
                },
            ],
        }
        self.inventory_payload = _canonical_json(self.inventory_document)
        self.capacity_document = {
            "schema": "nfl2k5_audo_import_capacity/v1",
            "summary": {"record_count": 1},
            "records": [{
                "key": "outer_0000_chunk_0001",
                "name": self.standalone_name,
                "outer": {
                    "index": 0,
                    "id": f"0x{OUTER_ID:08x}",
                    "head_ascii": "AUSB",
                    "size": 512,
                },
                "chunk": {
                    "index": 1,
                    "kind": "AUDO",
                    "offset_in_outer": 256,
                    "stored_body_bytes": len(audo_body),
                    "wrapper_span_bytes": 0x20 + len(audo_body),
                },
                "format": {
                    "channels": 1,
                    "sample_rate": 16_000,
                    "frame_count": 64,
                    "payload_allocation_bytes": len(self.standalone_payload),
                    "pcm16le_bytes": len(self.standalone_pcm),
                    "system_bytes": 128,
                    "tail_bytes": 12,
                    "data_offset": 0,
                },
                "hashes": {
                    "decoded_pcm_sha256": hashlib.sha256(
                        self.standalone_pcm
                    ).hexdigest(),
                    "payload_sha256": hashlib.sha256(
                        self.standalone_payload
                    ).hexdigest(),
                    "resource_body_sha256": hashlib.sha256(audo_body).hexdigest(),
                    "resource_span_sha256": hashlib.sha256(audo_wrapper).hexdigest(),
                },
            }],
        }
        self.capacity_payload = _canonical_json(self.capacity_document)
        self.capacity_report = parent / "capacity.json"
        self.capacity_report.write_bytes(self.capacity_payload)

        self.cache_root = parent / self.source_sha256
        self.cache_root.mkdir()
        packs = self.cache_root / "packs"
        packs.mkdir()
        self.cache_pack0 = packs / "0"
        self.cache_pack0.write_bytes(self.pack0_payload)
        # Deliberately wrong extracted payload. The scanner must never read it.
        self.cache_pack1 = packs / "1"
        self.cache_pack1.write_bytes(b"\xEE" * PACK1_SIZE)
        self.cache_inventory = self.cache_root / "inventory.json"
        self.cache_inventory.write_bytes(self.inventory_payload)
        originals = self.cache_root / "originals"
        originals.mkdir()
        source_record = SourceRecord(
            selected_path=str(self.source),
            inspected_path=str(self.source),
            kind="xiso",
            sha256=self.source_sha256,
            size=SOURCE_SIZE,
            recognized=True,
            fingerprint_id="retail-free-synthetic-xiso",
            detected_game=GameId.NFL2K5.value,
        )
        self.cache = SourceCache(
            source=source_record,
            root=self.cache_root.resolve(),
            pack0=self.cache_pack0,
            inventory=self.cache_inventory,
            originals=originals,
            resource_count=2,
            outer_entry_count=2,
            kind_counts={"AUSB": 1, "AUDO": 1},
        )
        self.pins = AudioSourceScanPins(
            source_size=SOURCE_SIZE,
            source_sha256=self.source_sha256,
            pack0_size=PACK0_SIZE,
            pack0_sha256=hashlib.sha256(self.pack0_payload).hexdigest(),
            inventory_size=len(self.inventory_payload),
            inventory_sha256=hashlib.sha256(self.inventory_payload).hexdigest(),
            capacity_report_sha256=hashlib.sha256(
                self.capacity_payload
            ).hexdigest(),
            standalone_count=1,
            streaming_bank_count=1,
            streaming_range_count=2,
            streaming_slot_count=2,
            streaming_owner_count=2,
            pack_names=("0", "1"),
        )
        self.store = Nfl2k5AudioSourceFingerprintStore(
            expected_source_sha256=self.source_sha256,
            expected_standalone_count=1,
            expected_streaming_slot_count=2,
            expected_streaming_owner_count=2,
            progress_interval_items=1,
        )
        self.parser_calls = 0

    def parser(self, _descriptor: int, image_size: int):
        self.parser_calls += 1
        if image_size != SOURCE_SIZE:
            raise ValueError("synthetic image size mismatch")
        return {
            "vc_53450030/0": xiso.XdvdfsEntry(
                "vc_53450030/0", PACK0_OFFSET // 2048, PACK0_SIZE, 0x20
            ),
            "vc_53450030/1": xiso.XdvdfsEntry(
                "vc_53450030/1", PACK1_OFFSET // 2048, PACK1_SIZE, 0x20
            ),
        }, {"synthetic": 1}

    def scanner(self, **kwargs: object) -> Nfl2k5AudioSourceScanner:
        return Nfl2k5AudioSourceScanner(
            pins=self.pins,
            capacity_report=self.capacity_report,
            store=self.store,
            xdvdfs_parser=self.parser,
            decode_batch_bytes=144,
            **kwargs,
        )

    @property
    def fingerprint_path(self) -> Path:
        return self.store.inventory_path(self.cache)


class Nfl2k5AudioSourceScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = SyntheticSourceFixture(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_complete_scan_reads_xiso_not_mutable_cached_payloads(self) -> None:
        source_before = hashlib.sha256(self.fixture.source.read_bytes()).hexdigest()
        pack0_before = self.fixture.cache_pack0.read_bytes()
        inventory_before = self.fixture.cache_inventory.read_bytes()
        cached_pack1_before = self.fixture.cache_pack1.read_bytes()
        events = []

        result = self.fixture.scanner().ensure(
            self.fixture.source.resolve(),
            self.fixture.cache,
            progress=events.append,
        )

        self.assertFalse(result.reused_inventory)
        self.assertEqual(result.standalone_count, 1)
        self.assertEqual(result.streaming_bank_count, 1)
        self.assertEqual(result.streaming_range_count, 2)
        self.assertEqual(result.streaming_slot_count, 2)
        self.assertEqual(result.streaming_owner_count, 2)
        self.assertEqual(result.streaming_encoded_bytes, PACK1_SIZE)
        self.assertTrue(result.inventory.private)
        self.assertFalse(result.inventory.shareable)
        self.assertEqual(
            hashlib.sha256(self.fixture.source.read_bytes()).hexdigest(),
            source_before,
        )
        self.assertEqual(self.fixture.cache_pack0.read_bytes(), pack0_before)
        self.assertEqual(self.fixture.cache_inventory.read_bytes(), inventory_before)
        self.assertEqual(self.fixture.cache_pack1.read_bytes(), cached_pack1_before)
        self.assertNotIn(b"\xEE" * 36, result.inventory.path.read_bytes())
        self.assertTrue(any(
            event.stage == "Rechecking source XISO after audio scan"
            for event in events
        ))
        self.assertEqual(events[-1].stage, "Private audio fingerprint inventory ready")

        first_pcm = decode_xbox_ima_time_block(self.fixture.bank_payload[:36], 1)
        first_match = result.inventory.resolve(
            "nfl2k5.audio.ausb.o0000.c0000.r00000"
        )
        self.assertEqual(
            first_match.pcm_sha256, hashlib.sha256(first_pcm).hexdigest()
        )
        standalone_match = result.inventory.resolve(
            "nfl2k5.audio.audo.o0000.c0001"
        )
        self.assertEqual(
            standalone_match.pcm_sha256,
            hashlib.sha256(self.fixture.standalone_pcm).hexdigest(),
        )

    def test_completed_inventory_rehashes_source_audo_but_not_streaming_slots(self) -> None:
        first = self.fixture.scanner().ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        decoded_payloads: list[bytes] = []

        def recording_decoder(
            payload: bytes, channels: int, cancelled: object
        ) -> bytes:
            decoded_payloads.append(payload)
            return decode_xbox_ima_batch(payload, channels, cancelled)

        second = self.fixture.scanner(batch_decoder=recording_decoder).ensure(
            self.fixture.source.resolve(), self.fixture.cache
        )
        self.assertTrue(second.reused_inventory)
        self.assertEqual(decoded_payloads, [self.fixture.standalone_payload])
        self.assertEqual(first.inventory, second.inventory)

    def test_standalone_report_hash_is_only_a_cross_check_not_fingerprint_input(self) -> None:
        changed = json.loads(json.dumps(self.fixture.capacity_document))
        changed["records"][0]["hashes"]["decoded_pcm_sha256"] = "0" * 64
        payload = _canonical_json(changed)
        self.fixture.capacity_report.write_bytes(payload)
        self.fixture.pins = replace(
            self.fixture.pins,
            capacity_report_sha256=hashlib.sha256(payload).hexdigest(),
        )

        with self.assertRaisesRegex(
            AudioSourceScanError, "decoded PCM disagrees with pinned metadata"
        ):
            self.fixture.scanner().ensure(
                self.fixture.source.resolve(), self.fixture.cache
            )
        self.assertFalse(self.fixture.fingerprint_path.exists())

    def test_cache_pack0_and_inventory_must_authenticate_before_topology(self) -> None:
        original_pack0 = self.fixture.cache_pack0.read_bytes()
        changed = bytearray(original_pack0)
        changed[-1] ^= 0x80
        self.fixture.cache_pack0.write_bytes(changed)
        with self.assertRaisesRegex(AudioSourceScanError, "pack-0 index hash"):
            self.fixture.scanner().ensure(
                self.fixture.source.resolve(), self.fixture.cache
            )
        self.assertEqual(self.fixture.parser_calls, 0)
        self.assertFalse(self.fixture.fingerprint_path.exists())

        self.fixture.cache_pack0.write_bytes(original_pack0)
        inventory = bytearray(self.fixture.cache_inventory.read_bytes())
        inventory[-2] ^= 1
        self.fixture.cache_inventory.write_bytes(inventory)
        with self.assertRaisesRegex(AudioSourceScanError, "resource inventory hash"):
            self.fixture.scanner().ensure(
                self.fixture.source.resolve(), self.fixture.cache
            )
        self.assertEqual(self.fixture.parser_calls, 0)
        self.assertFalse(self.fixture.fingerprint_path.exists())

    def test_cancellation_during_stream_hash_publishes_nothing(self) -> None:
        should_cancel = False

        def progress(event: object) -> None:
            nonlocal should_cancel
            if (
                event.stage == "Hashing streaming source PCM"
                and event.completed > 0
            ):
                should_cancel = True

        with self.assertRaisesRegex(
            AudioSourceFingerprintCancelled, "no fingerprint inventory was published"
        ):
            self.fixture.scanner().ensure(
                self.fixture.source.resolve(),
                self.fixture.cache,
                progress=progress,
                cancelled=lambda: should_cancel,
            )
        self.assertFalse(self.fixture.fingerprint_path.exists())

    def test_source_content_change_during_scan_fails_before_publication(self) -> None:
        mutated = False

        def progress(event: object) -> None:
            nonlocal mutated
            if (
                not mutated
                and event.stage == "Hashing streaming source PCM"
                and event.completed > 0
            ):
                with self.fixture.source.open("r+b") as stream:
                    stream.seek(PACK1_OFFSET + 100)
                    value = stream.read(1)
                    stream.seek(PACK1_OFFSET + 100)
                    stream.write(bytes((value[0] ^ 0x20,)))
                    stream.flush()
                    os.fsync(stream.fileno())
                mutated = True

        with self.assertRaisesRegex(
            AudioSourceScanError, "Source XISO (content|identity/content metadata) changed"
        ):
            self.fixture.scanner().ensure(
                self.fixture.source.resolve(), self.fixture.cache, progress=progress
            )
        self.assertTrue(mutated)
        self.assertFalse(self.fixture.fingerprint_path.exists())

    def test_source_path_swap_during_scan_fails_before_publication(self) -> None:
        replacement = self.fixture.source.with_suffix(".replacement")
        replacement.write_bytes(self.fixture.source.read_bytes())
        swapped = False

        def progress(event: object) -> None:
            nonlocal swapped
            if (
                not swapped
                and event.stage == "Hashing streaming source PCM"
                and event.completed > 0
            ):
                os.replace(replacement, self.fixture.source)
                swapped = True

        with self.assertRaisesRegex(
            AudioSourceScanError, "identity/content metadata changed"
        ):
            self.fixture.scanner().ensure(
                self.fixture.source.resolve(), self.fixture.cache, progress=progress
            )
        self.assertTrue(swapped)
        self.assertFalse(self.fixture.fingerprint_path.exists())

    def test_source_mutation_after_final_hash_rolls_back_owned_publication(self) -> None:
        real_publish = fingerprint_module._rename_noreplace_at
        mutated = False

        def publish_then_mutate(
            directory_fd: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            nonlocal mutated
            real_publish(directory_fd, source_name, destination_name)
            with self.fixture.source.open("r+b") as stream:
                stream.seek(PACK1_OFFSET + 200)
                original = stream.read(1)
                stream.seek(PACK1_OFFSET + 200)
                stream.write(bytes((original[0] ^ 0x40,)))
                stream.flush()
                os.fsync(stream.fileno())
            mutated = True

        with patch(
            "mod_editor.core.nfl2k5_audio_source_fingerprints._rename_noreplace_at",
            side_effect=publish_then_mutate,
        ):
            with self.assertRaisesRegex(
                AudioSourceScanError, "post-publication source recheck"
            ):
                self.fixture.scanner().ensure(
                    self.fixture.source.resolve(), self.fixture.cache
                )
        self.assertTrue(mutated)
        self.assertFalse(self.fixture.fingerprint_path.exists())
        self.assertEqual(tuple(self.fixture.fingerprint_path.parent.glob("*.tmp")), ())

    def test_bad_stream_step_index_fails_without_inventory(self) -> None:
        image = bytearray(self.fixture.source.read_bytes())
        struct.pack_into("<H", image, PACK1_OFFSET + 2, 89)
        self.fixture.source.write_bytes(image)
        changed_sha = hashlib.sha256(image).hexdigest()
        source = self.fixture.cache.source
        self.fixture.cache = SourceCache(
            source=SourceRecord(
                selected_path=source.selected_path,
                inspected_path=source.inspected_path,
                kind=source.kind,
                sha256=changed_sha,
                size=source.size,
                recognized=True,
                fingerprint_id=source.fingerprint_id,
                detected_game=source.detected_game,
            ),
            root=(Path(self.temporary.name) / changed_sha).resolve(),
            pack0=self.fixture.cache_pack0,
            inventory=self.fixture.cache_inventory,
            originals=self.fixture.cache.originals,
            resource_count=2,
            outer_entry_count=2,
            kind_counts={"AUSB": 1, "AUDO": 1},
        )
        self.fixture.cache.root.mkdir()
        pins = replace(self.fixture.pins, source_sha256=changed_sha)
        store = Nfl2k5AudioSourceFingerprintStore(
            expected_source_sha256=changed_sha,
            expected_standalone_count=1,
            expected_streaming_slot_count=2,
            expected_streaming_owner_count=2,
        )
        scanner = Nfl2k5AudioSourceScanner(
            pins=pins,
            capacity_report=self.fixture.capacity_report,
            store=store,
            xdvdfs_parser=self.fixture.parser,
            decode_batch_bytes=144,
        )
        with self.assertRaisesRegex(AudioSourceScanError, "step index exceeds 88"):
            scanner.ensure(self.fixture.source.resolve(), self.fixture.cache)
        self.assertFalse(store.inventory_path(self.fixture.cache).exists())


class XboxImaBatchDecoderTests(unittest.TestCase):
    def test_vectorized_batch_is_byte_identical_to_established_decoder(self) -> None:
        for channels in (1, 2):
            payload = b"".join(
                struct.pack("<hH", block * 17 - channel * 23, (block + channel) % 89)
                + bytes(
                    (block * 7 + channel * 13 + index) & 0xFF
                    for index in range(32)
                )
                for block in range(37)
                for channel in range(channels)
            )
            block_align = 36 * channels
            expected = b"".join(
                decode_xbox_ima_time_block(
                    payload[offset:offset + block_align], channels
                )
                for offset in range(0, len(payload), block_align)
            )
            self.assertEqual(decode_xbox_ima_batch(payload, channels), expected)

    def test_invalid_index_and_cancellation_fail_closed(self) -> None:
        invalid = struct.pack("<hH", 0, 0xFFFF) + b"\0" * 32
        with self.assertRaisesRegex(AudioSourceScanError, "step index exceeds 88"):
            decode_xbox_ima_batch(invalid, 1)
        valid = struct.pack("<hH", 0, 0) + b"\0" * 32
        with self.assertRaises(AudioSourceFingerprintCancelled):
            decode_xbox_ima_batch(valid, 1, lambda: True)

    def test_scalar_fallback_is_exact_when_numpy_is_unavailable(self) -> None:
        payload = b"".join(
            struct.pack("<hH", index * 19 - 300, index % 89)
            + bytes((index + value * 3) & 0xFF for value in range(32))
            for index in range(11)
        )
        expected = b"".join(
            decode_xbox_ima_time_block(payload[offset:offset + 36], 1)
            for offset in range(0, len(payload), 36)
        )
        with patch.dict(sys.modules, {"numpy": None}):
            self.assertEqual(decode_xbox_ima_batch(payload, 1), expected)


if __name__ == "__main__":
    unittest.main()
