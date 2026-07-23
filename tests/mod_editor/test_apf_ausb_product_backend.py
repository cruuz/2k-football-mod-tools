"""Synthetic product-session/project tests for APF AUSB exact-slot editing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.catalog import ApfCatalog
from mod_editor.apf_studio.asset_io import AudioPreviewCancelled
from mod_editor.apf_studio.inspectors import ExportIdentity
from mod_editor.apf_studio.models import (
    AUSB_EXACT_SLOT_KIND,
    AUSB_EXACT_SLOT_WRITER_SCHEMA,
    ApfSource,
)
from mod_editor.apf_studio.project import ProjectError
from mod_editor.apf_studio.session import ApfSession, SessionError
import apf_ausb_exact_slot as session_writer
from tools import apf_ausb_exact_slot as writer


def _packets(count: int = 2, fill: int = 0x5A) -> bytes:
    packets = []
    for index in range(count):
        packet = bytearray([fill + index] * 0x800)
        struct.pack_into(">I", packet, 0, 0x08000000)
        packets.append(bytes(packet))
    return b"".join(packets)


def _fingerprints(
    *payloads: bytes,
) -> session_writer.apf_audo_exact_slot.SourceAudioFingerprints:
    packet_hashes = {
        hashlib.sha256(payload[offset : offset + 0x800]).digest()
        for payload in payloads
        for offset in range(0, len(payload), 0x800)
    }
    payload_hashes = {
        hashlib.sha256(payload).hexdigest() for payload in payloads
    }
    return session_writer.apf_audo_exact_slot.SourceAudioFingerprints(
        domain=session_writer.SOURCE_AUDIO_DOMAIN,
        payload_sha256s=frozenset(payload_hashes),
        packet_sha256s=frozenset(packet_hashes or {b"\x99" * 32}),
        payload_occurrence_count=session_writer.EXPECTED_CANONICAL_RANGE_COUNT,
        packet_occurrence_count=max(1, len(packet_hashes)),
    )


def _rewrite_project(
    source: Path,
    destination: Path,
    *,
    mutate_manifest: object | None = None,
    mutate_payload: bool = False,
) -> Path:
    with zipfile.ZipFile(source, "r") as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["project.json"])
    if mutate_manifest is not None:
        mutate_manifest(manifest)
    members["project.json"] = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if mutate_payload:
        payload_name = next(name for name in members if name != "project.json")
        members[payload_name] = members[payload_name][:-1] + bytes(
            [members[payload_name][-1] ^ 0xFF]
        )
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return destination


class ApfAusbProductBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        # These focused AUSB tests supply a synthetic AUSB inventory. The
        # opposite-family scanner is isolated here; dedicated cross-domain
        # tests exercise the real combined session boundary.
        self.audo_scan = patch(
            "mod_editor.apf_studio.session.apf_audo_exact_slot.original_audio_fingerprints",
            return_value=object(),
        )
        self.audo_reject = patch(
            "mod_editor.apf_studio.session.apf_audo_exact_slot.reject_source_audio_reuse"
        )
        self.audo_scan.start()
        self.audo_reject.start()
        self.hash_count = patch.object(
            session_writer, "EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT", 1
        )
        self.hash_count.start()
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-ausb-product-")
        self.root = Path(self.temporary.name)
        game = self.root / "game"
        game.mkdir()
        index = game / "0A"
        index.write_bytes(b"synthetic index")
        self.source = ApfSource(
            selected_path=game,
            game_root=game,
            index_0a=index,
            source_sha256="1" * 64,
            source_size=index.stat().st_size,
            xex_sha256="2" * 64,
            display_name="Synthetic APF",
        )
        self.catalog = ApfCatalog(
            source_sha256=self.source.source_sha256,
            outer_count=0,
            iff_count=0,
            non_iff_count=0,
            inner_count=0,
            assets=(),
            uniform_assets=(),
            capabilities=(),
            audio_selection_manifest=self.root / "selection.json",
        )
        self.identity = ExportIdentity(
            "ausb_substream", 137, 8, 0, "cwdloop-00000"
        )
        self.payload = _packets()
        first_owner = writer.AusbOwner(
            descriptor_outer_index=137,
            descriptor_inner_index=8,
            substream_index=0,
            bank_name="cwdloop",
            external_filename="cwdloop.bin",
            channels=2,
            sample_rate=48_000,
            duration_value_bits=0x4271AC08,
            duration_seconds=60.418_666_839_599_61,
            declared_sample_count=2_900_096,
        )
        second_owner = writer.AusbOwner(
            descriptor_outer_index=659,
            descriptor_inner_index=289,
            substream_index=0,
            bank_name="cwdloop",
            external_filename="cwdloop.bin",
            channels=2,
            sample_rate=48_000,
            duration_value_bits=0x4271AC08,
            duration_seconds=60.418_666_839_599_61,
            declared_sample_count=2_900_096,
        )
        self.resolved = writer.ResolvedExactSlot(
            asset_id=first_owner.asset_id,
            requested_owner=first_owner,
            owners=(first_owner, second_owner),
            canonical_physical_id="apf:audio:ausb:physical:717:0:4096",
            external_outer_index=717,
            external_range_offset=0,
            target=writer.ExactSlotTarget(
                channels=2,
                sample_rate=48_000,
                encoded_size=len(self.payload),
                declared_sample_count=2_900_096,
            ),
            physical_spans=(writer.PhysicalSpan("0A", 0x123400, len(self.payload), 0),),
            source_payload_sha256="a" * 64,
        )
        self.supplied = self.root / "user.xma"
        self.supplied.write_bytes(b"RIFF user-authored fixture")
        self.safe_fingerprints = _fingerprints(_packets(fill=0x33))

    def tearDown(self) -> None:
        self.temporary.cleanup()
        self.hash_count.stop()
        self.audo_reject.stop()
        self.audo_scan.stop()

    def _result(self) -> writer.ExactSlotImportResult:
        digest = hashlib.sha256(self.payload).hexdigest()
        return writer.ExactSlotImportResult(
            payload=self.payload,
            receipt={
                "schema": writer.SCHEMA,
                "replacement": {"payload_sha256": digest},
            },
        )

    def _patch_replace(self) -> object:
        return (
            patch(
                "mod_editor.apf_studio.session.apf_ausb_exact_slot.resolve_target",
                return_value=self.resolved,
            ),
            patch(
                "mod_editor.apf_studio.session.apf_ausb_exact_slot.validate_exact_slot_import",
                return_value=self._result(),
            ),
            patch(
                "mod_editor.apf_studio.session.apf_ausb_exact_slot.original_audio_fingerprints",
                return_value=self.safe_fingerprints,
            ),
        )

    def test_replace_revert_streamed_project_round_trip_is_semantic_only(self) -> None:
        session = ApfSession(
            self.source, self.catalog, cache_root=self.root / "cache-one"
        )
        try:
            resolve, validate, hashes = self._patch_replace()
            with resolve, validate, hashes as fingerprint_scan:
                modification = session.replace_ausb_exact_slot(
                    self.identity, self.supplied
                )
                self.assertEqual(modification.kind, AUSB_EXACT_SLOT_KIND)
                self.assertEqual(modification.replacement_path.read_bytes(), self.payload)
                self.assertEqual(
                    modification.metadata["writer_schema"],
                    AUSB_EXACT_SLOT_WRITER_SCHEMA,
                )
                self.assertEqual(
                    modification.metadata["shared_owner_asset_ids"],
                    [
                        "apf:audio:ausb:137:8:0",
                        "apf:audio:ausb:659:289:0",
                    ],
                )
                self.assertEqual(
                    set(modification.metadata),
                    {
                        "outer_table_index",
                        "inner_file_index",
                        "substream_index",
                        "encoded_size",
                        "sample_rate",
                        "channel_count",
                        "declared_sample_count",
                        "packet_count",
                        "shared_owner_asset_ids",
                        "owner_fingerprint",
                        "writer_schema",
                    },
                )
                combined_metadata = json.dumps(modification.metadata)
                for forbidden in (
                    "canonical_physical_id",
                    "external_range_offset",
                    "physical_spans",
                    "source_payload_sha256",
                    "pack_offset",
                ):
                    self.assertNotIn(forbidden, combined_metadata)

                self.assertTrue(session.revert(modification.asset_id))
                self.assertEqual(session.modified_count, 0)
                self.assertTrue(session.undo())
                self.assertEqual(session.modified_count, 1)

                # Saving replacement members must retain the existing chunked
                # file/Zip64 route; Path.read_bytes is never used for payloads.
                with patch.object(
                    Path,
                    "read_bytes",
                    side_effect=AssertionError("project save must stream payloads"),
                ):
                    project = session.save_project(self.root / "audio.apf2k8mod")
                fingerprint_scan.assert_called_once_with(self.source.index_0a)

            with zipfile.ZipFile(project) as archive:
                manifest = json.loads(archive.read("project.json"))
                row = manifest["replacements"][0]
                self.assertEqual(row["kind"], AUSB_EXACT_SLOT_KIND)
                self.assertEqual(row["metadata"], modification.metadata)
                payload_member = row["payload"]
                self.assertEqual(archive.read(payload_member), self.payload)
                self.assertNotIn(b"RIFF", archive.read(payload_member))
                manifest_text = json.dumps(manifest, sort_keys=True)
                for source_digest in self.safe_fingerprints.payload_sha256s:
                    self.assertNotIn(source_digest, manifest_text)
                for source_packet_digest in self.safe_fingerprints.packet_sha256s:
                    self.assertNotIn(source_packet_digest.hex(), manifest_text)

            loaded = ApfSession(
                self.source, self.catalog, cache_root=self.root / "cache-two"
            )
            try:
                with (
                    patch(
                        "mod_editor.apf_studio.session.apf_ausb_exact_slot.resolve_target",
                        return_value=self.resolved,
                    ),
                    patch(
                        "mod_editor.apf_studio.session.apf_ausb_exact_slot.validate_stored_payload_complete",
                        return_value=self._result(),
                    ),
                    patch(
                        "mod_editor.apf_studio.session.apf_ausb_exact_slot.original_audio_fingerprints",
                        return_value=self.safe_fingerprints,
                    ),
                ):
                    self.assertEqual(loaded.load_project(project), 1)
                restored = loaded.modification(modification.asset_id)
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertEqual(restored.replacement_path.read_bytes(), self.payload)
                self.assertEqual(restored.metadata, modification.metadata)
            finally:
                loaded.close()
        finally:
            session.close()

    def test_replacement_preview_receipt_cache_and_tamper_detection(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        try:
            resolve, validate, hashes = self._patch_replace()
            with resolve, validate, hashes:
                session.replace_ausb_exact_slot(self.identity, self.supplied)

                calls = []

                def decode(
                    payload: bytes,
                    resolved: writer.ResolvedExactSlot,
                    protected_hashes: frozenset[str],
                    destination: Path,
                ) -> dict[str, object]:
                    calls.append((payload, resolved, protected_hashes, destination))
                    wav = b"RIFF synthetic decoded preview"
                    destination.write_bytes(wav)
                    return {
                        "schema": writer.WAV_EXPORT_SCHEMA,
                        "payload_sha256": hashlib.sha256(payload).hexdigest(),
                        "wav_sha256": hashlib.sha256(wav).hexdigest(),
                    }

                with patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.decode_stored_payload_to_wav",
                    side_effect=decode,
                ):
                    preview = session.prepare_audio_preview(self.identity)
                    self.assertEqual(session.prepare_audio_preview(self.identity), preview)
                    self.assertEqual(len(calls), 1)
                    preview.write_bytes(preview.read_bytes() + b"tamper")
                    with self.assertRaisesRegex(SessionError, "changed after decoding"):
                        session.prepare_audio_preview(self.identity)
        finally:
            session.close()

    def test_cancelled_replacement_preview_removes_partial_wav_and_receipt(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        cancelled = threading.Event()
        try:
            resolve, validate, hashes = self._patch_replace()
            with resolve, validate, hashes:
                session.replace_ausb_exact_slot(self.identity, self.supplied)

                def decode(
                    _payload: bytes,
                    _resolved: writer.ResolvedExactSlot,
                    _protected_hashes: frozenset[str],
                    destination: Path,
                    *,
                    cancel_requested: object,
                ) -> dict[str, object]:
                    self.assertFalse(cancel_requested())  # type: ignore[operator]
                    destination.write_bytes(b"partial pcm")
                    cancelled.set()
                    raise session_writer.apf_audio.AudioCancelled(
                        "synthetic preview cancellation"
                    )

                with patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.decode_stored_payload_to_wav",
                    side_effect=decode,
                ), self.assertRaises(AudioPreviewCancelled):
                    session.prepare_audio_preview(
                        self.identity,
                        cancel_requested=cancelled.is_set,
                    )
            preview_root = session.working_root / "audio-previews"
            self.assertEqual(tuple(preview_root.iterdir()), ())
            self.assertEqual(session._audo_preview_receipts, {})
        finally:
            session.close()

    def test_retail_payload_is_rejected_even_if_validator_receipt_is_spoofed(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        try:
            with (
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.resolve_target",
                    return_value=self.resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.validate_exact_slot_import",
                    return_value=self._result(),
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.original_audio_fingerprints",
                    return_value=_fingerprints(self.payload),
                ),
            ):
                with self.assertRaisesRegex(SessionError, "complete audio payload"):
                    session.replace_ausb_exact_slot(self.identity, self.supplied)
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)
        finally:
            session.close()

    def test_project_load_rejects_retail_payload_even_if_validator_is_spoofed(self) -> None:
        authoring = ApfSession(
            self.source, self.catalog, cache_root=self.root / "cache-authoring"
        )
        try:
            resolve, validate, hashes = self._patch_replace()
            with resolve, validate, hashes:
                authoring.replace_ausb_exact_slot(self.identity, self.supplied)
                project = authoring.save_project(self.root / "retail-gate.apf2k8mod")
        finally:
            authoring.close()

        loaded = ApfSession(
            self.source, self.catalog, cache_root=self.root / "cache-loading"
        )
        try:
            with (
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.resolve_target",
                    return_value=self.resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.validate_stored_payload_complete",
                    return_value=self._result(),
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.original_audio_fingerprints",
                    return_value=_fingerprints(self.payload),
                ),
                self.assertRaisesRegex(SessionError, "complete audio payload"),
            ):
                loaded.load_project(project)
            self.assertEqual(loaded.modified_count, 0)
            self.assertFalse(loaded.can_undo)
        finally:
            loaded.close()

    def test_project_load_rejects_one_bit_near_source_packet_reuse(self) -> None:
        authoring = ApfSession(
            self.source, self.catalog, cache_root=self.root / "cache-near-authoring"
        )
        try:
            resolve, validate, hashes = self._patch_replace()
            with resolve, validate, hashes:
                authoring.replace_ausb_exact_slot(self.identity, self.supplied)
                project = authoring.save_project(
                    self.root / "near-source.apf2k8mod"
                )
        finally:
            authoring.close()

        near_source = bytearray(self.payload)
        near_source[-1] ^= 0x01
        loaded = ApfSession(
            self.source, self.catalog, cache_root=self.root / "cache-near-loading"
        )
        try:
            with (
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.resolve_target",
                    return_value=self.resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.validate_stored_payload_complete",
                    return_value=self._result(),
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.original_audio_fingerprints",
                    return_value=_fingerprints(bytes(near_source)),
                ),
                self.assertRaisesRegex(
                    SessionError, "reuses a complete 0x800-byte"
                ),
            ):
                loaded.load_project(project)
            self.assertEqual(loaded.modified_count, 0)
            self.assertFalse(loaded.can_undo)
        finally:
            loaded.close()

    def test_project_payload_and_semantic_metadata_tampering_fail_closed(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache-one")
        try:
            resolve, validate, hashes = self._patch_replace()
            with resolve, validate, hashes:
                session.replace_ausb_exact_slot(self.identity, self.supplied)
                project = session.save_project(self.root / "base.apf2k8mod")
        finally:
            session.close()

        payload_tamper = _rewrite_project(
            project, self.root / "payload-tamper.apf2k8mod", mutate_payload=True
        )
        loaded = ApfSession(self.source, self.catalog, cache_root=self.root / "cache-two")
        try:
            with self.assertRaisesRegex(ProjectError, "failed validation"):
                loaded.load_project(payload_tamper)
            self.assertEqual(loaded.modified_count, 0)
        finally:
            loaded.close()

        def add_physical_metadata(manifest: dict[str, object]) -> None:
            manifest["replacements"][0]["metadata"]["external_range_offset"] = 0

        physical_tamper = _rewrite_project(
            project,
            self.root / "physical-metadata-tamper.apf2k8mod",
            mutate_manifest=add_physical_metadata,
        )
        loaded = ApfSession(self.source, self.catalog, cache_root=self.root / "cache-three")
        try:
            with self.assertRaisesRegex(ProjectError, "metadata is invalid"):
                loaded.load_project(physical_tamper)
            self.assertEqual(loaded.modified_count, 0)
        finally:
            loaded.close()

        def change_semantic_shape(manifest: dict[str, object]) -> None:
            metadata = manifest["replacements"][0]["metadata"]
            metadata["declared_sample_count"] += 1

        semantic_tamper = _rewrite_project(
            project,
            self.root / "semantic-tamper.apf2k8mod",
            mutate_manifest=change_semantic_shape,
        )
        loaded = ApfSession(self.source, self.catalog, cache_root=self.root / "cache-four")
        try:
            with (
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.resolve_target",
                    return_value=self.resolved,
                ),
                self.assertRaisesRegex(SessionError, "target changed"),
            ):
                loaded.load_project(semantic_tamper)
            self.assertEqual(loaded.modified_count, 0)
        finally:
            loaded.close()


if __name__ == "__main__":
    unittest.main()
