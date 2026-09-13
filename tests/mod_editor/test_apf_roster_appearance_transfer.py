"""Synthetic roster transfer receipts, preservation, and refusal contract."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import roster_appearance_transfer as subject
from mod_editor.apf_studio import ps3_roster_convert as ps3
from mod_editor.apf_studio.save_appearance import SaveAppearanceServiceError
from tests.test_apf_save_custom_team_appearance import synthetic_save, synthetic_stfs, writer, appearance_writer
from tests.mod_editor.test_apf_ps3_roster_convert import Fixture
import apf_stfs_roster_extract as stfs


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.raw = synthetic_save()
        self.source = self.root / "Roster.ROS"
        self.source.write_bytes(self.raw)
        self.edits = tuple(appearance_writer.eagles_2017_preset(row.appearance)
                           for row in writer.parse_save(self.raw).slots[:2])

    def test_multiple_slots_raw_and_stfs_output_reparse(self):
        for package in (False, True):
            with self.subTest(package=package):
                original = synthetic_stfs(self.raw, copies=2, active=1) if package else self.raw
                self.source.write_bytes(original)
                doc = subject.inspect_transfer_source(self.source)
                output = self.root / ("new.stfs" if package else "new.ROS")
                result = subject.write_transfer(doc, self.edits, output, xenia_package=package)
                receipt = json.loads(result.manifest.read_text())
                self.assertEqual(self.source.read_bytes(), original)
                self.assertEqual(result.changed_slots, (32, 33))
                self.assertEqual(receipt["appearance_patch"]["authorized_byte_count"], 224)
                self.assertEqual(subject.verify_transfer(original, output.read_bytes(), receipt)["changed_slots"], [32, 33])
                raw_output = stfs.extract_roster_payload(output.read_bytes()).payload if package else output.read_bytes()
                parsed = writer.parse_save(raw_output)
                self.assertEqual([r.appearance for r in parsed.slots[:2]], list(self.edits))
                self.assertFalse(receipt["verification"]["runtime_in_game_proved"])

    def test_ps3_zip_carries_other_uniform_selectors_and_receipts_override(self):
        raw = bytearray(Fixture().ps3())
        appearance = ps3.team_appearance(bytes(raw))
        # Distinct jersey/shoulder codes and opaque tails for both banks.
        for bank in appearance[32]["banks"]:
            for slot in (4, 11):
                offset = bank["selectors"][slot]["offset"]
                raw[offset:offset + 8] = bytes((29 + slot, 91, 82, 73, 64, 55, 46, 37))
        appearance = ps3.team_appearance(bytes(raw))
        archive = self.root / "ps3.zip"
        member = "BLUS30049-ROS/USERDATA"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(member, raw)
        original = archive.read_bytes()
        doc = subject.inspect_transfer_source(archive)
        self.assertEqual(doc.kind, "ps3")
        self.assertFalse(doc.xenia_package_supported)
        output = self.root / "converted.ROS"
        result = subject.write_transfer(doc, self.edits[:1], output)
        receipt = json.loads(result.manifest.read_text())
        converted, _ = ps3.convert(bytes(raw))
        after = ps3.team_appearance(output.read_bytes())
        for before_bank, after_bank in zip(appearance[32]["banks"], after[32]["banks"]):
            for slot in (4, 11):
                self.assertEqual(before_bank["selectors"][slot]["record_hex"], after_bank["selectors"][slot]["record_hex"])
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(receipt["ps3_conversion"]["team_appearance"]["verification"]["selector_records"], 1120)
        self.assertTrue(receipt["ps3_conversion"]["team_appearance"]["refused"])
        self.assertTrue(subject.verify_transfer(bytes(raw), output.read_bytes(), receipt)["ps3_conversion_reverified"])
        self.assertEqual(writer.parse_save(output.read_bytes()).slots[1:], writer.parse_save(converted).slots[1:])

    def test_refuses_source_overwrite_existing_output_receipt_and_stale_source(self):
        doc = subject.inspect_transfer_source(self.source)
        with self.assertRaisesRegex(SaveAppearanceServiceError, "separate"):
            subject.write_transfer(doc, self.edits, self.source)
        output = self.root / "new.ROS"
        output.write_bytes(b"keep")
        with self.assertRaisesRegex(SaveAppearanceServiceError, "overwrite"):
            subject.write_transfer(doc, self.edits, output)
        self.assertEqual(output.read_bytes(), b"keep")
        output.unlink()
        manifest = writer.default_manifest_path(output)
        manifest.write_bytes(b"keep receipt")
        with self.assertRaisesRegex(SaveAppearanceServiceError, "overwrite"):
            subject.write_transfer(doc, self.edits, output)
        self.assertFalse(output.exists())
        self.assertEqual(manifest.read_bytes(), b"keep receipt")
        self.source.write_bytes(self.raw + b"changed")
        with self.assertRaisesRegex(SaveAppearanceServiceError, "changed after inspection"):
            subject.write_transfer(doc, self.edits, output)
        self.assertFalse(output.exists())

    def test_receipt_slots_cannot_lie_and_raw_cannot_be_packaged(self):
        doc = subject.inspect_transfer_source(self.source)
        output = self.root / "new.ROS"
        with self.assertRaises(SaveAppearanceServiceError):
            subject.write_transfer(doc, self.edits, output, xenia_package=True)
        self.assertFalse(output.exists())
        result = subject.write_transfer(doc, self.edits, output)
        receipt = json.loads(result.manifest.read_text())
        receipt["changed_slots"] = [39]
        with self.assertRaisesRegex(writer.SaveAppearanceError, "slot list"):
            subject.verify_transfer(self.raw, output.read_bytes(), receipt)

    def test_extractable_xenia_incompatible_package_keeps_raw_route(self):
        package = bytearray(synthetic_stfs(self.raw))
        package[0xA000 + 24 + 21:0xA000 + 24 + 24] = b"\xff\xff\xff"
        top = 0xA000 + 0xAB * 4096
        package[top:top + 20] = hashlib.sha1(package[0xA000:0xB000]).digest()
        package[0x381:0x395] = hashlib.sha1(package[top:top + 4096]).digest()
        package[0x32C:0x340] = hashlib.sha1(package[0x344:0xA000]).digest()
        self.source.write_bytes(package)
        doc = subject.inspect_transfer_source(self.source)
        self.assertFalse(doc.xenia_package_supported)
        self.assertIn("Xenia traversal", doc.package_reason)
        result = subject.write_transfer(doc, self.edits, self.root / "fallback.ROS")
        self.assertTrue(result.verification_passed)
        self.assertFalse(result.output_is_package)


if __name__ == "__main__":
    unittest.main()
