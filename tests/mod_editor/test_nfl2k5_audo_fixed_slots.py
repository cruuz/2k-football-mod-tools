"""Retail-free product tests for unique fixed-allocation AUDO replacement."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import wave

from mod_editor.core.nfl2k5_audo_fixed_slots import (
    EDITABLE_CLASSIFICATION,
    EXPECTED_GENERIC_SLOT_COUNT,
    EXPECTED_LEGACY_CLASSIFIED_COUNT,
    FixedAudoError,
    FixedAudoSlot,
    decode_xbox_ima,
    encode_xbox_ima,
    load_editable_slots,
    parse_strict_wav,
    quality,
)
from mod_editor.core.nfl2k5_audio_catalog import (
    FIXED_AUDO_CAPABILITY_ID,
    FIXED_AUDO_PROVIDER_ID,
    Nfl2k5AudioCatalog,
    Nfl2k5AudioService,
)
from mod_editor.studio.session import StudioSession
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture
from tests.mod_editor.test_studio_session import _Asset, _Catalog


TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_visual_mod_project as unified  # noqa: E402


def _wav(path: Path, *, channels: int, rate: int, frames: int) -> bytes:
    samples = tuple(
        int(12_000 * math.sin((frame * 2 + channel * 11) * math.pi / 73))
        for frame in range(frames)
        for channel in range(channels)
    )
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path.read_bytes()


class FixedAudoSlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.slots = load_editable_slots()

    def test_catalog_authorizes_all_849_generic_physical_slots(self) -> None:
        self.assertEqual(len(self.slots), EXPECTED_GENERIC_SLOT_COUNT)
        self.assertEqual(sum(slot.channels == 1 for slot in self.slots), 805)
        self.assertEqual(sum(slot.channels == 2 for slot in self.slots), 44)
        self.assertEqual(
            len({slot.asset_id for slot in self.slots}),
            EXPECTED_GENERIC_SLOT_COUNT,
        )
        self.assertNotIn((3, 101), {slot.selector for slot in self.slots})
        self.assertEqual(
            sum(slot.legacy_complete_pack_editable for slot in self.slots),
            EXPECTED_LEGACY_CLASSIFIED_COUNT,
        )
        self.assertEqual(
            sum(slot.classification == EDITABLE_CLASSIFICATION for slot in self.slots),
            EXPECTED_LEGACY_CLASSIFIED_COUNT,
        )
        self.assertTrue(all(slot.payload_size % (36 * slot.channels) == 0
                            for slot in self.slots))

        formerly_export_only = next(
            slot for slot in self.slots if slot.classification == "export-only"
        )
        self.assertIn(formerly_export_only.asset_id, formerly_export_only.replacement_warning)
        self.assertIn(
            "runtime selector ownership may be unknown",
            formerly_export_only.replacement_warning,
        )
        self.assertEqual(formerly_export_only.runtime_selector_owner, "unproved")
        self.assertEqual(formerly_export_only.runtime_visibility, "not-tested")

    def test_mono_and_stereo_strict_wavs_encode_to_exact_allocation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fixed-audo-codec-") as temporary:
            root = Path(temporary)
            for channels in (1, 2):
                base = self.slots[0]
                slot = replace(
                    base,
                    asset_id=f"synthetic-{channels}",
                    channels=channels,
                    sample_rate=22_050,
                    frame_count=64,
                    payload_size=36 * channels,
                )
                payload = _wav(
                    root / f"{channels}.wav",
                    channels=channels,
                    rate=22_050,
                    frames=64,
                )
                source = parse_strict_wav(payload, slot)
                encoded = encode_xbox_ima(source, slot)
                decoded = decode_xbox_ima(encoded, slot)
                measured = quality(source.samples, decoded, slot)
                self.assertEqual(len(encoded), 36 * channels)
                self.assertEqual(len(decoded), 64 * channels)
                self.assertTrue(measured["block_predictor_samples_exact"])

                wrong = replace(slot, frame_count=128, payload_size=72 * channels)
                with self.assertRaisesRegex(FixedAudoError, "128 frames"):
                    parse_strict_wav(payload, wrong)

    def test_unified_project_encodes_a_catalog_slot_without_raw_offsets(self) -> None:
        slot = min(
            (item for item in self.slots if item.classification == "export-only"),
            key=lambda item: item.frame_count,
        )
        with tempfile.TemporaryDirectory(prefix="fixed-audo-project-") as temporary:
            root = Path(temporary)
            wav_path = root / "mine.wav"
            _wav(
                wav_path,
                channels=slot.channels,
                rate=slot.sample_rate,
                frames=slot.frame_count,
            )
            project_path = root / "project.json"
            document = {
                "edits": [{
                    "asset_id": slot.asset_id,
                    "kind": "audo_audio",
                    "wav": str(wav_path),
                }],
                "purpose": "Synthetic user-authored standalone audio test.",
                "schema": unified.SCHEMA,
            }
            project_path.write_bytes(unified.canonical_json(document))
            project = unified.read_project(project_path)
            pins = unified.pin_project_inputs(project)
            def authorize(pin: unified.InputPin, **_kwargs: object) -> object:
                return SimpleNamespace(
                    wav_bytes=pin.payload,
                    wav_sha256=pin.sha256,
                    pcm_sha256=hashlib.sha256(pin.payload[44:]).hexdigest(),
                )

            with patch.object(
                unified, "authorize_audio_input", side_effect=authorize
            ):
                replacement, previews, report, selector, target = \
                    unified.build_audo_audio_import(
                        project.value["edits"][0], project, pins, slot, object()
                    )
            self.assertEqual(len(replacement), slot.payload_size)
            self.assertEqual(previews, [])
            self.assertEqual(selector, slot.asset_id)
            self.assertEqual(target["span_sha256"], slot.payload_sha256)
            self.assertEqual(
                report["catalog"]["legacy_capacity_classification"],
                "export-only",
            )
            self.assertEqual(report["catalog"]["product_edit_status"], "Editable")
            self.assertNotIn("classification", report["catalog"])
            self.assertTrue(
                report["claims"]["distinct_exact_physical_slot_boundary"]
            )
            self.assertFalse(
                report["claims"]["semantic_aliases_expand_write_span"]
            )
            self.assertFalse(report["claims"]["semantic_cue_identity_proved"])
            self.assertNotIn(
                "unique_name_and_decoded_content_boundary", report["claims"]
            )
            self.assertFalse(report["claims"]["public_project_contains_raw_offsets"])
            self.assertNotIn("pack_offset", document["edits"][0])
            validated = unified.validate_only(project_path)
            self.assertEqual(validated["kind_counts"], {"audo_audio": 1})

    def test_service_session_export_replace_revert_and_project_use_logical_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fixed-audo-session-") as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = Nfl2k5AudioCatalog(
                fixture.cache,
                capacity_report=fixture.report,
                expected_count=2,
                expected_report_sha256=None,
            )
            service = Nfl2k5AudioService(fixture.cache, catalog)
            fixture._ensure_private_audio_inventories(catalog)  # noqa: SLF001
            asset = catalog.assets[0]
            self.assertTrue(asset.editable)
            self.assertEqual(asset.classification, "export-only")
            self.assertFalse(asset.legacy_complete_pack_editable)
            self.assertIn(asset.asset_id, asset.replacement_warning)
            supplied = root / "user.wav"
            _wav(supplied, channels=1, rate=16_000, frames=64)
            metadata = service.validate_replacement(asset, supplied)
            self.assertEqual(metadata.capability_id, FIXED_AUDO_CAPABILITY_ID)
            self.assertEqual(metadata.provider_id, FIXED_AUDO_PROVIDER_ID)

            session = StudioSession(
                fixture.cache,
                _Catalog(_Asset()),
                root=root / "sessions",
                session_id="generic-audio",
            )
            session.attach_audio_service(service)
            self.assertTrue(session.replace_audio(asset, supplied).modified)
            self.assertEqual(session.canonical_document()["edits"], [{
                "asset_id": asset.asset_id,
                "kind": "audo_audio",
                "wav": str(session.current_audio_path(asset)),
            }])
            exported = session.export_audio(asset, root / "export.wav")
            self.assertEqual(exported.read_bytes(), supplied.read_bytes())
            project = session.save_shareable_project(root / "audio.2k5mod")
            self.assertNotIn(asset.payload_sha256.encode("ascii"), project.read_bytes())
            self.assertTrue(session.revert_audio(asset))
            self.assertNotIn(asset.asset_id, session.modified_audio_asset_ids)


if __name__ == "__main__":
    unittest.main()
