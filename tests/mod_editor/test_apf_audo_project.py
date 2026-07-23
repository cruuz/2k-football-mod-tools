"""Retail-free project tests for APF standalone exact-slot XMA1 edits."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from mod_editor.apf_studio.models import (
    AUDO_EXACT_SLOT_KIND,
    AUDO_EXACT_SLOT_WRITER_SCHEMA,
    Modification,
)
from mod_editor.apf_studio.project import ProjectError, load_project, save_project


def _packet_payload(packet_count: int = 1) -> bytes:
    packet = bytearray(0x800)
    struct.pack_into(">I", packet, 0, 2 << 26)
    return bytes(packet) * packet_count


class ApfAudoProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-audo-project-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _modification(self, payload: bytes | None = None) -> Modification:
        data = payload if payload is not None else _packet_payload()
        digest = hashlib.sha256(data).hexdigest()
        source = self.root / f"{digest}.xma1-packets"
        source.write_bytes(data)
        return Modification(
            asset_id="apf:audio:audo:988:19",
            kind=AUDO_EXACT_SLOT_KIND,
            replacement_path=source,
            replacement_sha256=digest,
            metadata={
                "outer_table_index": 988,
                "inner_file_index": 19,
                "encoded_size": len(data),
                "sample_rate": 22_050,
                "channel_count": 1,
                "declared_sample_count": 4_096,
                "packet_count": len(data) // 0x800,
                "writer_schema": AUDO_EXACT_SLOT_WRITER_SCHEMA,
            },
        )

    def test_round_trip_stores_only_raw_user_packet_payload(self) -> None:
        modification = self._modification()
        destination = self.root / "audio.apf2k8mod"
        save_project(
            destination,
            source_sha256="1" * 64,
            modifications=(modification,),
        )
        with zipfile.ZipFile(destination) as archive:
            names = archive.namelist()
            payload_names = [name for name in names if name != "project.json"]
            self.assertEqual(len(payload_names), 1)
            self.assertTrue(payload_names[0].endswith(".xma1-packets"))
            self.assertEqual(
                archive.read(payload_names[0]),
                modification.replacement_path.read_bytes(),
            )
            self.assertNotIn(b"RIFF", archive.read(payload_names[0]))
        _manifest, loaded, _annotations = load_project(
            destination,
            expected_source_sha256="1" * 64,
            destination_dir=self.root / "loaded",
        )
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].kind, AUDO_EXACT_SLOT_KIND)
        self.assertEqual(
            loaded[0].replacement_path.read_bytes(),
            modification.replacement_path.read_bytes(),
        )

    def test_protected_source_audio_hash_is_refused(self) -> None:
        modification = self._modification()
        with self.assertRaisesRegex(ProjectError, "protected source game data"):
            save_project(
                self.root / "blocked.apf2k8mod",
                source_sha256="1" * 64,
                modifications=(modification,),
                protected_replacement_hashes=(
                    modification.replacement_sha256,
                ),
            )
        self.assertFalse((self.root / "blocked.apf2k8mod").exists())

    def test_invalid_packet_header_is_refused(self) -> None:
        modification = self._modification(bytes(0x800))
        with self.assertRaisesRegex(ProjectError, "not APF XMA1 packet data"):
            save_project(
                self.root / "invalid.apf2k8mod",
                source_sha256="1" * 64,
                modifications=(modification,),
            )
        self.assertFalse((self.root / "invalid.apf2k8mod").exists())


if __name__ == "__main__":
    unittest.main()
