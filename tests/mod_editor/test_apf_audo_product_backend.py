"""Product-session tests for APF exact-slot standalone audio replacement."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.catalog import ApfCatalog
from mod_editor.apf_studio.inspectors import ExportIdentity
from mod_editor.apf_studio.models import (
    AUDO_EXACT_SLOT_KIND,
    AUDO_EXACT_SLOT_WRITER_SCHEMA,
    ApfSource,
)
from mod_editor.apf_studio.session import ApfSession, SessionError
import apf_audo_exact_slot as session_writer
from tools.apf_audo_exact_slot import (
    ExactSlotImportResult,
    ExactSlotTarget,
    ResolvedExactSlot,
)


def _packets(count: int = 1, fill: int = 0x5A) -> bytes:
    packet = bytearray([fill] * 0x800)
    struct.pack_into(">I", packet, 0, 2 << 26)
    return bytes(packet) * count


def _fingerprints(*payloads: bytes) -> session_writer.SourceAudioFingerprints:
    packet_hashes = {
        hashlib.sha256(payload[offset : offset + 0x800]).digest()
        for payload in payloads
        for offset in range(0, len(payload), 0x800)
    }
    return session_writer.SourceAudioFingerprints(
        domain=session_writer.SOURCE_AUDIO_DOMAIN,
        payload_sha256s=frozenset(
            hashlib.sha256(payload).hexdigest() for payload in payloads
        ),
        packet_sha256s=frozenset(packet_hashes),
        payload_occurrence_count=session_writer.EXPECTED_STANDALONE_AUDO_COUNT,
        packet_occurrence_count=max(1, len(packet_hashes)),
    )


class ApfAudoProductBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        # These focused AUDO tests supply a synthetic AUDO inventory. The
        # opposite-family scanner is isolated here; dedicated cross-domain
        # tests exercise the real combined session boundary.
        self.ausb_scan = patch(
            "mod_editor.apf_studio.session.apf_ausb_exact_slot.original_audio_fingerprints",
            return_value=object(),
        )
        self.ausb_reject = patch(
            "mod_editor.apf_studio.session.apf_ausb_exact_slot.reject_source_audio_reuse"
        )
        self.ausb_scan.start()
        self.ausb_reject.start()
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-audo-product-")
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
        self.identity = ExportIdentity("audo", 988, 19, None, "menu-gameplan-out_01")
        self.payload = _packets(5)
        self.target = ExactSlotTarget(
            channels=1,
            sample_rate=22_050,
            encoded_size=len(self.payload),
            declared_sample_count=21_604,
            loop_start_bit=0,
            loop_end_bit=len(self.payload) * 8,
            loop_subframe=0,
        )
        self.resolved = ResolvedExactSlot(
            asset_id="apf:audio:audo:988:19",
            name="menu-gameplan-out_01",
            outer_index=988,
            inner_index=19,
            target=self.target,
            pack_name="0A",
            pack_offset=0x123400,
            encoded_size=len(self.payload),
            source_payload_sha256="a" * 64,
        )
        self.supplied = self.root / "user.xma"
        self.supplied.write_bytes(b"RIFF user-authored fixture")
        self.safe_fingerprints = _fingerprints(_packets(fill=0x33))

    def tearDown(self) -> None:
        self.temporary.cleanup()
        self.ausb_reject.stop()
        self.ausb_scan.stop()

    def _result(self) -> ExactSlotImportResult:
        digest = hashlib.sha256(self.payload).hexdigest()
        return ExactSlotImportResult(
            payload=self.payload,
            receipt={
                "replacement": {
                    "payload_sha256": digest,
                }
            },
        )

    def test_replace_revert_undo_and_project_round_trip_store_packets_only(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache-one")
        try:
            with (
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_exact_slot_import",
                    return_value=self._result(),
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.original_audio_fingerprints",
                    return_value=self.safe_fingerprints,
                ) as fingerprint_scan,
            ):
                modification = session.replace_audo_exact_slot(
                    self.identity, self.supplied
                )
                self.assertEqual(modification.kind, AUDO_EXACT_SLOT_KIND)
                self.assertEqual(modification.replacement_path.read_bytes(), self.payload)
                self.assertEqual(
                    modification.metadata["writer_schema"],
                    AUDO_EXACT_SLOT_WRITER_SCHEMA,
                )
                self.assertIn(modification.asset_id, session.modified_asset_ids)
                self.assertTrue(session.revert(modification.asset_id))
                self.assertNotIn(modification.asset_id, session.modified_asset_ids)
                self.assertTrue(session.undo())
                self.assertIn(modification.asset_id, session.modified_asset_ids)

                project = session.save_project(self.root / "audio.apf2k8mod")
                fingerprint_scan.assert_called_once_with(self.source.index_0a)
                with zipfile.ZipFile(project) as archive:
                    payload_members = [
                        name for name in archive.namelist() if name != "project.json"
                    ]
                    self.assertEqual(len(payload_members), 1)
                    self.assertEqual(archive.read(payload_members[0]), self.payload)
                    self.assertNotIn(b"RIFF", archive.read(payload_members[0]))

                loaded = ApfSession(
                    self.source, self.catalog, cache_root=self.root / "cache-two"
                )
                try:
                    with (
                        patch(
                            "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                            return_value=self.resolved,
                        ),
                        patch(
                            "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_stored_payload_complete",
                            return_value=self._result(),
                        ),
                        patch(
                            "mod_editor.apf_studio.session.apf_audo_exact_slot.original_audio_fingerprints",
                            return_value=self.safe_fingerprints,
                        ),
                    ):
                        self.assertEqual(loaded.load_project(project), 1)
                    restored = loaded.modification(modification.asset_id)
                    self.assertIsNotNone(restored)
                    assert restored is not None
                    self.assertEqual(restored.replacement_path.read_bytes(), self.payload)
                finally:
                    loaded.close()
        finally:
            session.close()

    def test_source_audo_payload_is_rejected_before_edit_state_changes(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        try:
            with (
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_exact_slot_import",
                    return_value=self._result(),
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.original_audio_fingerprints",
                    return_value=_fingerprints(self.payload),
                ),
            ):
                with self.assertRaisesRegex(SessionError, "complete audio payload"):
                    session.replace_audo_exact_slot(self.identity, self.supplied)
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)
        finally:
            session.close()

    def test_project_load_rejects_one_bit_near_source_packet_reuse(self) -> None:
        authoring = ApfSession(
            self.source, self.catalog, cache_root=self.root / "cache-authoring"
        )
        try:
            with (
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_exact_slot_import",
                    return_value=self._result(),
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.original_audio_fingerprints",
                    return_value=self.safe_fingerprints,
                ),
            ):
                authoring.replace_audo_exact_slot(self.identity, self.supplied)
                project = authoring.save_project(self.root / "near-source.apf2k8mod")
        finally:
            authoring.close()

        near_source = bytearray(self.payload)
        near_source[-1] ^= 0x01
        loaded = ApfSession(
            self.source, self.catalog, cache_root=self.root / "cache-loading"
        )
        try:
            with (
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_stored_payload_complete",
                    return_value=self._result(),
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.original_audio_fingerprints",
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


if __name__ == "__main__":
    unittest.main()
