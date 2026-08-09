"""Retail-free product tests for the NFL 2K5 AUDO browser/service."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import zlib

from mod_editor.core.model import GameId, SourceRecord
from mod_editor.core.nfl2k5_audio_catalog import (
    AudioReplacementContract,
    FIXED_AUDO_CAPABILITY_ID,
    FIXED_AUDO_PROVIDER_ID,
    MENU_BACK_CAPABILITY_ID,
    MENU_BACK_PROVIDER_ID,
    Nfl2k5AudioCatalog,
    Nfl2k5AudioCatalogError,
    Nfl2k5AudioService,
    _decode_streaming_xbox_ima_pcm,
)
from mod_editor.core.nfl2k5_audio_containment_fingerprints import (
    SourcePcmCueInput,
    build_private_containment_inventory,
)
from mod_editor.core.nfl2k5_audio_source_containment import (
    Nfl2k5AudioSourceContainmentStore,
)
from mod_editor.core.nfl2k5_audio_source_fingerprints import (
    Nfl2k5AudioSourceFingerprintStore,
)
from mod_editor.core.nfl2k5_ausb_fixed_slots import build_streaming_slot_catalog
from mod_editor.core.nfl2k5_source_cache import SOURCE_SHA256, SourceCache
from mod_editor.core.nfl_audio import (
    NFL_MENU_BACK_AUDIO_FRAME_COUNT,
    load_nfl_menu_back_audio_recipe,
)

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from nfl_scene_probe import decode_xbox_ima  # noqa: E402


ENTRY_OFFSET = 8192
OUTER_SIZE = 16_384
OUTER_ID = "0x44444444"
BANK_NAME = "femusic"
BANK_FILENAME = "femusic.bin"
BANK_SIZE = 4_032
FIRST_RANGE_SIZE = 1_008


def _audo_body(name: str, payload: bytes, *, channels: int, rate: int) -> tuple[bytes, bytes]:
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
        rate,
    )
    body = bytes(system) + payload + b"\0" * 12
    pcm_samples = decode_xbox_ima(payload, channels)
    pcm = struct.pack(f"<{len(pcm_samples)}h", *pcm_samples)
    return body, pcm


def _wrapper(body: bytes, payload_size: int) -> bytes:
    return struct.pack(
        "<4s7I", b"AUDO", len(body), 128, payload_size, 0, 0, 0, 0
    ) + body


def _ausb_body() -> bytes:
    body = bytearray(0xA4)
    body[0x0C:0x10] = b"AUSB"
    struct.pack_into("<i", body, 0x10, 0x20 - 0x0F)
    encoded_name = (BANK_NAME + "\0").encode("utf-16le")
    body[0x20:0x20 + len(encoded_name)] = encoded_name
    encoded_filename = (BANK_FILENAME + "\0").encode("utf-16le")
    body[0x40:0x40 + len(encoded_filename)] = encoded_filename
    struct.pack_into("<5I", body, 0x80, 2, 0, 2, 22_050, 0x12000)
    struct.pack_into("<3I", body, 0x98, 0, FIRST_RANGE_SIZE, BANK_SIZE)
    return bytes(body)


def _group(group_id: str) -> dict[str, object]:
    return {"group_id": group_id, "member_count": 2}


def _capacity_row(
    *,
    chunk_index: int,
    chunk_offset: int,
    body: bytes,
    payload: bytes,
    pcm: bytes,
    editable: bool,
) -> dict[str, object]:
    blocks = len(payload) // 36
    classification = (
        "candidate-for-separately-authorized-fixed-slot-writer"
        if editable else "export-only"
    )
    authoring = {
        "channels": 1,
        "exact_frame_count": blocks * 64,
        "format": "strict RIFF PCM16LE",
        "metadata_chunks_allowed": False,
        "sample_rate": 16_000,
    }
    return {
        "key": f"outer_0003_chunk_{chunk_index:04d}",
        "name": "menu-back_01",
        "outer": {
            "head_ascii": "AUDO",
            "id": OUTER_ID,
            "index": 3,
            "size": OUTER_SIZE,
            "virtual_start": ENTRY_OFFSET,
        },
        "chunk": {
            "index": chunk_index,
            "kind": "AUDO",
            "offset_in_outer": chunk_offset,
            "stored_body_bytes": len(body),
            "wrapper_span_bytes": len(body) + 0x20,
        },
        "classification": classification,
        "classification_reasons": [
            "fixed synthetic writer" if editable else "duplicate cue ownership is ambiguous"
        ],
        "format": {
            "block_count": blocks,
            "block_frames": 64,
            "channel_block_bytes": 36,
            "channels": 1,
            "codec_flags": "0x00000035",
            "codec_word": "0x00000011",
            "data_offset": 0,
            "frame_count": blocks * 64,
            "payload_allocation_bytes": len(payload),
            "pcm16le_bytes": len(pcm),
            "sample_rate": 16_000,
            "system_bytes": 128,
            "tail_bytes": 12,
            "total_block_align": 36,
        },
        "groups": {
            "duplicate_name": _group("name:synthetic-menu-back"),
            "equal_decoded_content": None,
            "equal_payload": None,
            "equal_resource_span": None,
            "physical_span_shared": False,
        },
        "hashes": {
            "decoded_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "resource_body_sha256": hashlib.sha256(body).hexdigest(),
        },
        "ownership": {
            "fixed_slot_authorization": (
                "public-offline-writer-proved" if editable else "none"
            ),
            "physical_resource_owner": "exact outer/chunk/span",
            "runtime_selector_owner": "unproved",
            "runtime_visibility": "not-tested",
        },
        "structural_import": {
            "authoring_contract": authoring,
            "metadata_change_required": False,
            "same_allocation": True,
        },
    }


class AudioFixture:
    def __init__(self, root: Path) -> None:
        # Private audio stores are shared by alternate containers for the same
        # canonical game identity.  Keep the SourceRecord deliberately
        # different below so persisted inventories/sidecars prove they bind to
        # this canonical directory, not the selected container hash.
        root = root / SOURCE_SHA256
        root.mkdir(mode=0o700)
        self.root = root
        self.pack0 = root / "0"
        self.inventory = root / "inventory.json"
        self.report = root / "capacity.json"
        self.originals = root / "originals"
        self.originals.mkdir()

        duplicate_payload = bytes([1, 0, 12, 0]) + bytes(range(32))
        menu_payload = (bytes([0, 0, 32, 0]) + b"\0" * 32) * 89
        duplicate_body, duplicate_pcm = _audo_body(
            "menu-back_01", duplicate_payload, channels=1, rate=16_000
        )
        menu_body, menu_pcm = _audo_body(
            "menu-back_01", menu_payload, channels=1, rate=16_000
        )
        duplicate_wrapper = _wrapper(duplicate_body, len(duplicate_payload))
        menu_offset = len(duplicate_wrapper)
        menu_wrapper = _wrapper(menu_body, len(menu_payload))
        ausb_body = _ausb_body()
        ausb_offset = menu_offset + len(menu_wrapper)
        ausb_wrapper = struct.pack(
            "<4s7I", b"AUSB", len(ausb_body), 0, 0, 0, 0, 0, 0
        ) + ausb_body
        external_id = zlib.crc32(
            BANK_FILENAME.upper().encode("utf-16le")
        ) & 0xFFFFFFFF
        self.bank_payload = b"".join(
            struct.pack("<hH", (index * 29) % 2048 - 1024, index % 89)
            + bytes((index + nibble) & 0xFF for nibble in range(32))
            for index in range(BANK_SIZE // 36)
        )

        pack = bytearray(30_720)
        struct.pack_into("<III", pack, 0, 6, 0, 1)
        struct.pack_into("<36I", pack, 12, 15, *([0] * 35))
        entries = (
            (0x11111111, 2048, 1),
            (0x22222222, 2048, 2),
            (0x33333333, 2048, 3),
            (int(OUTER_ID, 0), OUTER_SIZE, 4),
            (external_id, BANK_SIZE, 12),
            (0x55555555, 2_048, 14),
        )
        cursor = 0x0C + 36 * 4
        for entry in entries:
            struct.pack_into("<III", pack, cursor, *entry)
            cursor += 12
        pack[2048:2052] = b"FILL"
        pack[4096:4100] = b"FILL"
        pack[6144:6148] = b"FILL"
        pack[ENTRY_OFFSET:ENTRY_OFFSET + len(duplicate_wrapper)] = duplicate_wrapper
        start = ENTRY_OFFSET + menu_offset
        pack[start:start + len(menu_wrapper)] = menu_wrapper
        start = ENTRY_OFFSET + ausb_offset
        pack[start:start + len(ausb_wrapper)] = ausb_wrapper
        pack[24_576:24_576 + BANK_SIZE] = self.bank_payload
        pack[28_672:28_676] = b"FILL"
        self.pack0.write_bytes(pack)

        rows = []
        capacity = []
        for chunk_index, offset, body, payload, pcm, editable in (
            (100, 0, duplicate_body, duplicate_payload, duplicate_pcm, False),
            (101, menu_offset, menu_body, menu_payload, menu_pcm, True),
        ):
            rows.append(
                {
                    "outer_index": 3,
                    "outer_id": OUTER_ID,
                    "outer_head": "AUDO",
                    "outer_size": OUTER_SIZE,
                    "chunk_index": chunk_index,
                    "chunk_offset": offset,
                    "zero_padding_before": 0,
                    "kind": "AUDO",
                    "stored_size": len(body),
                    "end_offset": offset + 0x20 + len(body),
                    "word_08": 128,
                    "word_0c": len(payload),
                    "word_10": "0x00000000",
                    "word_14": 0,
                }
            )
            capacity.append(
                _capacity_row(
                    chunk_index=chunk_index,
                    chunk_offset=offset,
                    body=body,
                    payload=payload,
                    pcm=pcm,
                    editable=editable,
                )
            )
        rows.append(
            {
                "outer_index": 3,
                "outer_id": OUTER_ID,
                "outer_head": "AUDO",
                "outer_size": OUTER_SIZE,
                "chunk_index": 102,
                "chunk_offset": ausb_offset,
                "zero_padding_before": 0,
                "kind": "AUSB",
                "stored_size": len(ausb_body),
                "end_offset": ausb_offset + 0x20 + len(ausb_body),
                "word_08": 0,
                "word_0c": 0,
                "word_10": "0x00000000",
                "word_14": 0,
            }
        )
        self.inventory.write_text(
            json.dumps(
                {
                    "schema": "nfl2k5_resource_chunk_inventory/v1",
                    "summary": {"resource_chunk_count": 3},
                    "chunks": rows,
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        self.report.write_text(
            json.dumps(
                {
                    "schema": "nfl2k5_audo_import_capacity/v1",
                    "summary": {"record_count": 2},
                    "records": capacity,
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        source = SourceRecord(
            selected_path=str(root / "synthetic.xiso"),
            inspected_path=str(root / "synthetic.xiso"),
            kind="xiso",
            sha256="f" * 64,
            size=1,
            recognized=True,
            fingerprint_id="retail-free-test-fixture",
            detected_game=GameId.NFL2K5.value,
        )
        self.cache = SourceCache(
            source=source,
            root=root,
            pack0=self.pack0,
            inventory=self.inventory,
            originals=self.originals,
            resource_count=3,
            outer_entry_count=6,
            kind_counts={"AUDO": 2, "AUSB": 1},
        )
        self._standalone_pcm = {
            "nfl2k5.audio.audo.o0003.c0100": duplicate_pcm,
            "nfl2k5.audio.audo.o0003.c0101": menu_pcm,
        }

    def catalog(self) -> Nfl2k5AudioCatalog:
        catalog = Nfl2k5AudioCatalog(
            self.cache,
            capacity_report=self.report,
            expected_count=2,
            expected_report_sha256=None,
        )
        self._ensure_private_audio_inventories(catalog)
        return catalog

    def _ensure_private_audio_inventories(
        self, catalog: Nfl2k5AudioCatalog
    ) -> None:
        from nfl_outer import parse_archive

        slots = build_streaming_slot_catalog(
            catalog.streaming_ranges, parse_archive(self.pack0)
        ).slots

        def slot_pcm(slot: object) -> bytes:
            payload = self.bank_payload[slot.range_start:slot.range_end]
            samples = decode_xbox_ima(payload, slot.channels)
            return struct.pack(f"<{len(samples)}h", *samples)

        exact_store = Nfl2k5AudioSourceFingerprintStore(
            expected_source_sha256=SOURCE_SHA256,
            expected_standalone_count=len(catalog.assets),
            expected_streaming_slot_count=len(slots),
            expected_streaming_owner_count=sum(len(slot.owners) for slot in slots),
        )
        exact_store.ensure(
            self.cache,
            catalog.assets,
            slots,
            lambda slot: hashlib.sha256(slot_pcm(slot)).hexdigest(),
            publication_guard=lambda _digest: None,
        )
        owner_ids = tuple(sorted(
            [asset.asset_id for asset in catalog.assets]
            + [owner.asset_id for slot in slots for owner in slot.owners]
        ))
        policy = Nfl2k5AudioService._containment_policy(catalog.assets, slots)
        cues = tuple(
            SourcePcmCueInput(
                owner_asset_ids=(asset.asset_id,),
                channels=asset.channels,
                sample_rate=asset.sample_rate,
                frame_count=asset.frame_count,
                pcm16le=self._standalone_pcm[asset.asset_id],
            )
            for asset in catalog.assets
        ) + tuple(
            SourcePcmCueInput(
                owner_asset_ids=tuple(owner.asset_id for owner in slot.owners),
                channels=slot.channels,
                sample_rate=slot.sample_rate,
                frame_count=slot.frame_count,
                pcm16le=slot_pcm(slot),
            )
            for slot in slots
        )
        containment_store = Nfl2k5AudioSourceContainmentStore(
            expected_source_sha256=SOURCE_SHA256,
            expected_cue_count=len(cues),
            expected_owner_count=len(owner_ids),
        )
        containment_store.ensure(
            self.cache,
            policy,
            owner_ids,
            lambda: build_private_containment_inventory(
                SOURCE_SHA256,
                policy,
                cues,
                expected_cue_count=len(cues),
                expected_owner_count=len(owner_ids),
            ),
            publication_guard=lambda _digest: None,
        )


def _valid_menu_wav(path: Path, *, rate: int = 16_000, frames: int = 5_696) -> Path:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(b"\0\0" * frames)
    return path


class Nfl2k5AudioCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = AudioFixture(self.root)
        self.catalog = self.fixture.catalog()
        self.service = Nfl2k5AudioService(self.fixture.cache, self.catalog)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_shared_cache_reuses_inventories_and_wav_sidecars_across_source_records(self) -> None:
        exact, containment = self.service.load_private_origin_inventories()
        self.assertEqual(exact.source_sha256, SOURCE_SHA256)
        self.assertEqual(containment.source_binding_sha256, SOURCE_SHA256)

        alternate_source = replace(self.fixture.cache.source, sha256="e" * 64)
        alternate_cache = replace(self.fixture.cache, source=alternate_source)
        alternate_service = Nfl2k5AudioService(alternate_cache, self.catalog)

        alternate_exact, alternate_containment = (
            alternate_service.load_private_origin_inventories()
        )
        self.assertEqual(alternate_exact, exact)
        self.assertEqual(alternate_containment, containment)

        standalone = self.catalog.assets[0]
        standalone_wav = self.service.ensure_original(standalone)
        self.assertEqual(
            alternate_service.ensure_original(standalone), standalone_wav
        )
        standalone_sidecar = json.loads(
            standalone_wav.with_suffix(".json").read_text(encoding="utf-8")
        )
        self.assertEqual(standalone_sidecar["source_sha256"], SOURCE_SHA256)

        streaming = self.catalog.streaming_ranges[0]
        streaming_wav = self.service.ensure_streaming_range_wav(streaming)
        self.assertEqual(
            alternate_service.ensure_streaming_range_wav(streaming), streaming_wav
        )
        streaming_sidecar_path = streaming_wav.with_suffix(".json")
        streaming_sidecar = json.loads(
            streaming_sidecar_path.read_text(encoding="utf-8")
        )
        self.assertEqual(streaming_sidecar["source_sha256"], SOURCE_SHA256)

        # A container-specific binding must not be accepted as a shortcut around
        # the canonical shared-cache identity or the existing sidecar checks.
        streaming_sidecar["source_sha256"] = "e" * 64
        streaming_sidecar_path.write_text(
            json.dumps(streaming_sidecar, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "changed outside"):
            alternate_service.ensure_streaming_range_wav(streaming)

    def test_catalog_uses_physical_stable_ids_for_every_exact_slot(self) -> None:
        self.assertEqual(self.catalog.asset_count, 2)
        self.assertEqual(self.catalog.editable_count, 2)
        self.assertEqual(self.catalog.export_only_count, 0)
        generic, menu_back = self.catalog.assets
        self.assertEqual(generic.name, menu_back.name)
        self.assertEqual(generic.asset_id, "nfl2k5.audio.audo.o0003.c0100")
        self.assertEqual(menu_back.asset_id, "nfl2k5.audio.audo.o0003.c0101")
        self.assertTrue(generic.editable)
        self.assertTrue(menu_back.editable)
        self.assertFalse(generic.legacy_complete_pack_editable)
        self.assertTrue(menu_back.legacy_complete_pack_editable)
        self.assertIn("Alias-related", generic.alias_status)
        self.assertIn(generic.asset_id, generic.replacement_warning)
        self.assertIn("semantic cue identity", generic.replacement_warning)
        self.assertIn("runtime selector ownership may be unknown", generic.action_note)
        self.assertNotEqual(generic.suggested_filename, menu_back.suggested_filename)
        self.assertEqual(self.catalog.query(status="Editable"), (generic, menu_back))
        self.assertEqual(self.catalog.query(status="Export-only"), ())
        self.assertEqual(self.catalog.query(search="c0100"), (generic,))
        self.assertEqual(self.catalog.get_selector(3, 101), menu_back)

    def test_catalog_cold_import_defers_provider_registry_until_factory_call(self) -> None:
        script = "\n".join((
            "import importlib, sys",
            "import mod_editor.core",
            "sys.modules.pop('mod_editor.core.providers', None)",
            "sys.modules.pop('mod_editor.core.nfl_audio_provider', None)",
            "sys.modules.pop('mod_editor.core.nfl2k5_audio_catalog', None)",
            "catalog = importlib.import_module('mod_editor.core.nfl2k5_audio_catalog')",
            "assert 'mod_editor.core.providers' not in sys.modules",
            "provider = catalog.Nfl2k5AudioService.replacement_provider()",
            "assert provider.provider_id == 'nfl2k5-menu-back-audio-v1'",
            "assert 'mod_editor.core.providers' in sys.modules",
        ))
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_lazy_preview_and_export_decode_verified_pcm(self) -> None:
        duplicate = self.catalog.assets[0]
        private = self.service.original_path(duplicate)
        self.assertFalse(private.exists())
        playback = self.service.playback_path(duplicate)
        self.assertEqual(playback, private)
        self.assertTrue(playback.is_file())
        with wave.open(str(playback), "rb") as stream:
            self.assertEqual(stream.getnchannels(), 1)
            self.assertEqual(stream.getframerate(), 16_000)
            self.assertEqual(stream.getnframes(), 64)
        exported = self.root / duplicate.suggested_filename
        self.assertEqual(self.service.export_wav(duplicate, exported), exported.resolve())
        self.assertEqual(exported.read_bytes(), playback.read_bytes())
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "already exists"):
            self.service.export_wav(duplicate, exported)
        self.assertEqual(self.service.playback_path(duplicate), playback)

    def test_user_replacement_rejects_pcm_owned_by_any_source_cue(self) -> None:
        selected = next(asset for asset in self.catalog.assets if asset.editable)
        supplied = self.root / "authored.wav"
        with wave.open(str(supplied), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16_000)
            stream.writeframes(b"\x17\x00" * selected.frame_count)
        accepted = self.service.validate_user_replacement(selected, supplied)
        self.assertEqual(accepted.wav_path, supplied.resolve())

        with self.assertRaisesRegex(
            Nfl2k5AudioCatalogError,
            "exactly matches decoded source audio",
        ):
            self.service.validate_user_replacement(
                selected, self.service.ensure_original(selected)
            )

    def test_user_replacement_rejects_verified_cached_streaming_pcm(self) -> None:
        streaming = self.catalog.streaming_ranges[0]
        decoded_source = self.service.ensure_streaming_range_wav(streaming)
        with self.assertRaisesRegex(
            Nfl2k5AudioCatalogError,
            "exactly matches decoded source audio",
        ):
            self.service.validate_user_replacement(streaming, decoded_source)

    def test_streaming_bank_is_browsable_and_raw_export_only(self) -> None:
        self.assertEqual(self.catalog.streaming_bank_count, 1)
        self.assertEqual(self.catalog.streaming_external_bank_count, 1)
        self.assertEqual(self.catalog.streaming_range_count, 2)
        self.assertEqual(self.catalog.streaming_range_family_counts, {"music": 2})
        bank = self.catalog.streaming_banks[0]
        self.assertEqual(bank.name, BANK_NAME)
        self.assertEqual(bank.family_label, "Soundtrack & music")
        self.assertEqual(bank.edit_status, "Export-only")
        self.assertEqual(bank.replacement_status, "Edit individual indexed ranges")
        self.assertIn("not one playable cue", bank.action_note)
        self.assertIn("individual cues as WAV", bank.action_note)
        output = self.root / bank.suggested_filename
        self.assertEqual(
            self.service.export_streaming_bank(bank, output), output.resolve()
        )
        self.assertEqual(output.read_bytes(), self.fixture.bank_payload)
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "already exists"):
            self.service.export_streaming_bank(bank, output)
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, r"\.bin filename"):
            self.service.export_streaming_bank(bank, self.root / "not-a-wav.wav")

        first, second = self.catalog.streaming_ranges
        self.assertEqual(
            (first.asset_id, second.asset_id),
            (
                f"{bank.asset_id}.r00000",
                f"{bank.asset_id}.r00001",
            ),
        )
        self.assertEqual(
            (first.start, first.end, first.stored_size),
            (0, FIRST_RANGE_SIZE, FIRST_RANGE_SIZE),
        )
        self.assertEqual(
            (second.start, second.end, second.stored_size),
            (FIRST_RANGE_SIZE, BANK_SIZE, BANK_SIZE - FIRST_RANGE_SIZE),
        )
        first_output = self.root / first.suggested_filename
        second_output = self.root / second.suggested_filename
        self.assertEqual(
            self.service.export_streaming_range(first, first_output),
            first_output.resolve(),
        )
        self.assertEqual(
            first_output.read_bytes(), self.fixture.bank_payload[:FIRST_RANGE_SIZE]
        )
        self.assertEqual(
            self.service.export_streaming_range(second.asset_id, second_output),
            second_output.resolve(),
        )
        self.assertEqual(
            second_output.read_bytes(), self.fixture.bank_payload[FIRST_RANGE_SIZE:]
        )
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "already exists"):
            self.service.export_streaming_range(first, first_output)
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, r"\.bin filename"):
            self.service.export_streaming_range(first, self.root / "range.wav")

    def test_streaming_range_decodes_to_verified_private_wav_and_export(self) -> None:
        item = self.catalog.streaming_ranges[0]
        self.assertTrue(item.playable)
        self.assertEqual(item.channels, 2)
        self.assertEqual(item.frame_count, FIRST_RANGE_SIZE // 72 * 64)
        self.assertAlmostEqual(
            item.duration_seconds, item.frame_count / item.sample_rate
        )

        progress: list[tuple[int, int]] = []
        private = self.service.ensure_streaming_range_wav(
            item, lambda completed, total: progress.append((completed, total))
        )
        self.assertEqual(private, self.service.streaming_range_original_path(item))
        self.assertTrue(private.is_file())
        sidecar = private.with_suffix(".json")
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertEqual(
            record["schema"], "2k5_mod_studio_streaming_range_original_wav/v1"
        )
        self.assertEqual(record["encoded_range_size"], item.stored_size)
        with wave.open(str(private), "rb") as stream:
            self.assertEqual(stream.getnchannels(), item.channels)
            self.assertEqual(stream.getframerate(), item.sample_rate)
            self.assertEqual(stream.getnframes(), item.frame_count)
            self.assertEqual(stream.getsampwidth(), 2)
            decoded_pcm = stream.readframes(item.frame_count)
        expected_samples = decode_xbox_ima(
            self.fixture.bank_payload[:FIRST_RANGE_SIZE], item.channels
        )
        self.assertEqual(
            decoded_pcm,
            struct.pack(f"<{len(expected_samples)}h", *expected_samples),
        )
        self.assertEqual(progress[0], (0, item.stored_size))
        self.assertEqual(progress[-1], (item.stored_size, item.stored_size))

        exported = self.root / item.suggested_wav_filename
        self.assertEqual(
            self.service.export_streaming_range_wav(item, exported),
            exported.resolve(),
        )
        self.assertEqual(exported.read_bytes(), private.read_bytes())
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "already exists"):
            self.service.export_streaming_range_wav(item, exported)

        private.write_bytes(private.read_bytes()[:-2])
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "changed outside"):
            self.service.ensure_streaming_range_wav(item)

    def test_streaming_range_bad_ima_header_leaves_no_private_cache(self) -> None:
        item = self.catalog.streaming_ranges[1]
        pack = bytearray(self.fixture.pack0.read_bytes())
        struct.pack_into(
            "<H", pack, 24_576 + item.start + 2, 89
        )
        self.fixture.pack0.write_bytes(pack)
        private = self.service.streaming_range_original_path(item)
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "step index 89"):
            self.service.ensure_streaming_range_wav(item)
        self.assertFalse(private.exists())
        self.assertFalse(private.with_suffix(".json").exists())

    def test_streaming_decoder_falls_back_without_audioop(self) -> None:
        item = self.catalog.streaming_ranges[0]
        payload = self.fixture.bank_payload[:FIRST_RANGE_SIZE]
        progress: list[tuple[int, int]] = []
        with patch.dict(sys.modules, {"audioop": None}):
            pcm = _decode_streaming_xbox_ima_pcm(
                payload,
                item.channels,
                lambda completed, total: progress.append((completed, total)),
            )
        expected_samples = decode_xbox_ima(payload, item.channels)
        self.assertEqual(
            pcm,
            struct.pack(f"<{len(expected_samples)}h", *expected_samples),
        )
        self.assertEqual(progress[-1], (len(payload), len(payload)))

    def test_generic_slot_and_menu_back_keep_separate_provider_routes(self) -> None:
        generic, menu_back = self.catalog.assets
        generic_wav = _valid_menu_wav(
            self.root / "generic-user-authored.wav", frames=generic.frame_count
        )
        generic_metadata = self.service.validate_replacement(generic, generic_wav)
        self.assertEqual(generic_metadata.capability_id, FIXED_AUDO_CAPABILITY_ID)
        self.assertEqual(generic_metadata.provider_id, FIXED_AUDO_PROVIDER_ID)
        self.assertEqual(generic_metadata.target, generic.asset_id)

        wav = _valid_menu_wav(self.root / "user-authored.wav")
        invalid = _valid_menu_wav(self.root / "wrong-rate.wav", rate=22_050)
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "16,000 Hz"):
            self.service.validate_replacement(menu_back, invalid)
        linked = self.root / "linked.wav"
        linked.symlink_to(wav)
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "regular WAV"):
            self.service.validate_replacement(menu_back, linked)

        metadata = self.service.validate_replacement(menu_back, wav)
        self.assertEqual(metadata.capability_id, MENU_BACK_CAPABILITY_ID)
        self.assertEqual(metadata.provider_id, MENU_BACK_PROVIDER_ID)
        self.assertEqual(metadata.frame_count, NFL_MENU_BACK_AUDIO_FRAME_COUNT)
        plan = self.service.create_replacement_plan(
            menu_back,
            wav,
            self.root / "audio.recipe.json",
            purpose="Replace the menu-back cue in my own dump",
        )
        self.assertEqual(plan.provider_id, MENU_BACK_PROVIDER_ID)
        self.assertEqual(plan.capability_id, MENU_BACK_CAPABILITY_ID)
        self.assertEqual(
            load_nfl_menu_back_audio_recipe(plan.recipe_path).wav_path, wav.resolve()
        )
        self.assertEqual(
            self.service.replacement_provider().provider_id, MENU_BACK_PROVIDER_ID
        )

    def test_catalog_and_cache_tampering_fail_closed(self) -> None:
        fixed = self.catalog.assets[1]
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "does not match"):
            self.catalog.get_asset(replace(fixed, name="forged"))
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "page size"):
            self.catalog.query(limit=0)

        private = self.service.ensure_original(fixed)
        private.write_bytes(private.read_bytes() + b"tamper")
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "changed outside"):
            self.service.ensure_original(fixed)

        document = json.loads(self.fixture.inventory.read_text(encoding="utf-8"))
        document["chunks"][0]["word_0c"] += 36
        self.fixture.inventory.write_text(json.dumps(document, indent=2) + "\n")
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "disagree"):
            self.fixture.catalog()

    def test_report_pin_and_nonlink_rules_are_enforced(self) -> None:
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "changed"):
            Nfl2k5AudioCatalog(
                self.fixture.cache,
                capacity_report=self.fixture.report,
                expected_count=2,
                expected_report_sha256="0" * 64,
            )
        link = self.root / "linked-capacity.json"
        link.symlink_to(self.fixture.report)
        with self.assertRaisesRegex(Nfl2k5AudioCatalogError, "regular file"):
            Nfl2k5AudioCatalog(
                self.fixture.cache,
                capacity_report=link,
                expected_count=2,
                expected_report_sha256=None,
            )


if __name__ == "__main__":
    unittest.main()
