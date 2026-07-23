from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl2k5_ps2_fixture_audit as audit  # noqa: E402


REPORT = ROOT / "reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json"


class FixtureAuditUnitTests(unittest.TestCase):
    def test_parses_pcsx2_authorities_strictly(self) -> None:
        game = audit.parse_game_index(
            'SLUS-20919:\n'
            '  name: "ESPN - NFL 2K5"\n'
            '  region: "NTSC-U"\n'
            '  compat: 5\n'
        )
        self.assertEqual(game, {
            "compat": 5,
            "name": "ESPN - NFL 2K5",
            "region": "NTSC-U",
            "serial": "SLUS-20919",
        })
        redump = audit.parse_redump_database(
            "- hashes:\n"
            "  - md5: 46ef5e7a2e155994e7c3e5627293e068\n"
            "    size: 4665081856\n"
            "  name: ESPN NFL 2K5 (USA)\n"
            "  serial: SLUS-20919\n"
            "  version: '1.01'\n"
        )
        self.assertEqual(redump["size"], 4_665_081_856)
        with self.assertRaises(audit.FixtureAuditError):
            audit.parse_game_index(
                'SLUS-20919:\n  name: "ESPN - NFL 2K5"\n  region: "PAL-E"\n'
            )

    def test_classifies_xdvdfs_and_iso9660_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            xbox = Path(temporary) / "named-like-ps2.iso"
            xbox_payload = bytearray(0x10000 + 64)
            xbox_payload[0x10000:0x10000 + len(audit.XDVDFS_MAGIC)] = (
                audit.XDVDFS_MAGIC
            )
            xbox.write_bytes(xbox_payload)
            self.assertEqual(audit.classify_disc_header(xbox), "xdvdfs_xbox")

            ps2 = Path(temporary) / "fixture.iso"
            ps2_payload = bytearray(0x9000)
            ps2_payload[0x8001:0x8006] = b"CD001"
            ps2.write_bytes(ps2_payload)
            self.assertEqual(audit.classify_disc_header(ps2), "iso9660")

    def test_memory_card_marker_inventory_is_metadata_only(self) -> None:
        payload = (
            audit.MEMORY_CARD_MAGIC
            + b"\x00" * 64
            + b"BASLUS-20919FFran 1\x00"
            + b"\x00" * 16
            + b"BASLUS-20529TSett 1\x00"
        )
        self.assertEqual(audit.memory_card_names(payload), [
            "BASLUS-20529TSett 1", "BASLUS-20919FFran 1"
        ])

    def test_exact_size_scan_hashes_and_rejects_wrong_md5(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "tiny.iso"
            fixture.write_bytes(b"fixture")
            original_size = audit.EXPECTED_ISO_SIZE
            try:
                audit.EXPECTED_ISO_SIZE = len(b"fixture")
                result = audit.scan_for_fixtures((Path(temporary),))
            finally:
                audit.EXPECTED_ISO_SIZE = original_size
            self.assertEqual(len(result["exact_size_disc_candidates"]), 1)
            self.assertFalse(result["exact_size_disc_candidates"][0]["accepted"])


class CanonicalFixtureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_target_and_local_absence_are_explicit(self) -> None:
        self.assertEqual(cls_report := self.report["target"], {
            "boot_elf_expected_name": "SLUS_209.19",
            "disc_version": "1.01",
            "expected_iso_md5": "46ef5e7a2e155994e7c3e5627293e068",
            "expected_iso_size": 4_665_081_856,
            "platform": "PlayStation 2",
            "region": "NTSC-U",
            "serial": "SLUS-20919",
        })
        self.assertEqual(cls_report["serial"], self.report["summary"]["serial"])
        summary = self.report["summary"]
        self.assertFalse(summary["expected_iso_present"])
        self.assertFalse(summary["extracted_boot_elf_present"])
        self.assertFalse(summary["save_directory_marker_present"])
        self.assertFalse(summary["pcsx2_texture_dump_present"])
        self.assertFalse(summary["safe_ps2_patch_ready"])

    def test_both_memory_cards_are_hash_pinned_and_target_marker_free(self) -> None:
        cards = self.report["local_evidence"]["memory_cards"]
        self.assertEqual(len(cards), 2)
        self.assertEqual([row["sha256"] for row in cards], [
            "811ed6525e124c8222d151e5eb69442875387bdfd5d88e451097eaf620ac803a",
            "bd4a6c2303426f9d22c3c17e14619b83b6cbc679d4c25ad669605e591bdcb256",
        ])
        self.assertTrue(all(row["nfl2k5_marker_occurrence_count"] == 0 for row in cards))

    def test_xbox_images_are_rejected_by_header_not_repurposed(self) -> None:
        suspects = self.report["local_evidence"]["rejected_named_disc_suspects"]
        self.assertEqual(len(suspects), 2)
        self.assertTrue(all(row["classification"] == "xdvdfs_xbox" for row in suspects))
        self.assertTrue(all(not row["accepted_as_target_ps2_disc"] for row in suspects))

    def test_four_limit_rows_never_reuse_xbox_ownership(self) -> None:
        rows = self.report["limitations"]
        self.assertEqual([row["id"] for row in rows], [
            "draft_trade_logic",
            "salary_cap_contracts",
            "super_bowl_future_stadium",
            "shared_team_textures",
        ])
        for row in rows:
            self.assertEqual(
                row["ps2_owner_status"],
                "unmapped_no_verified_ps2_elf_or_save_fixture",
            )
            self.assertFalse(row["address_reuse_from_xbox_allowed"])
            self.assertFalse(row["safe_ps2_patch_ready"])

    def test_tool_has_no_mutation_or_payload_export_surface(self) -> None:
        source = (ROOT / "tools/nfl2k5_ps2_fixture_audit.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "--apply", "--extract", "--patch", "O_RDWR", "O_WRONLY", "r+b"
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("os.O_RDONLY", source)
        self.assertIn("xbox_addresses_reused", source)


if __name__ == "__main__":
    unittest.main()
