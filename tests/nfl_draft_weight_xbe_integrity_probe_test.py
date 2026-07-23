#!/usr/bin/env python3
"""Focused tests for the read-only NFL draft-weight integrity probe."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_draft_weight_xbe_integrity_probe as probe  # noqa: E402


class DraftWeightIntegrityProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = probe.generate()

    def test_exact_target_and_both_integrity_branches_are_bounded(self) -> None:
        report = self.report
        self.assertEqual(report["schema"], probe.SCHEMA)
        self.assertEqual(report["target"]["float_count"], 17)
        self.assertEqual(report["target"]["section"]["name"], ".rdata")
        self.assertEqual(report["target"]["file_offset"], "0x0057EAA8")
        self.assertEqual(
            [row["position"] for row in report["target"]["rows"]],
            list(probe.POSITIONS),
        )
        stale = report["integrity_branches"]["payload_only_stale_section_digest"]
        repaired = report["integrity_branches"]["payload_plus_updated_section_digest"]
        self.assertFalse(stale["section_digest_matches"])
        self.assertFalse(stale["signed_header_changed"])
        self.assertTrue(repaired["section_digest_matches"])
        self.assertTrue(repaired["signed_header_changed"])
        self.assertTrue(repaired["original_rsa_signature_bytes_reused"])
        self.assertEqual(report["claims"], {
            "retail_xbe_modified": False,
            "copied_xbe_written": False,
            "draft_weight_writer_proved": False,
            "retail_signed_xbe_patch_proved": False,
            "emulator_runtime_proved": False,
            "original_xbox_hardware_proved": False,
            "integrity_blocker_reproduced_in_memory": True,
        })

    def test_report_creation_is_canonical_exclusive_and_refuses_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "probe.json"
            created = probe.write_new(output, self.report)
            payload = created.read_bytes()
            self.assertEqual(payload, probe.canonical_json(json.loads(payload)))
            with self.assertRaisesRegex(probe.ProbeError, "already exists"):
                probe.write_new(output, self.report)

            broken = root / "broken.json"
            broken.symlink_to(root / "missing")
            with self.assertRaisesRegex(probe.ProbeError, "already exists"):
                probe.write_new(broken, self.report)
            self.assertTrue(broken.is_symlink())

    def test_pinned_reader_rejects_a_symlink_without_changing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_bytes(b"fixture")
            linked = root / "linked"
            linked.symlink_to(target)
            with self.assertRaisesRegex(probe.ProbeError, "non-symlink"):
                probe.read_pinned(
                    linked, len(b"fixture"), probe.sha256(b"fixture"), "fixture"
                )
            self.assertEqual(target.read_bytes(), b"fixture")


if __name__ == "__main__":
    unittest.main()
