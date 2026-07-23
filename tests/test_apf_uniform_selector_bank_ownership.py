#!/usr/bin/env python3
"""Tests for the APF uniform HOME/AWAY selector-bank closure."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_uniform_selector_bank_ownership as ownership  # noqa: E402


EXPORT_ROOT = ROOT / "research/functions/apf2k8"
TRACE = ROOT / "reports/assets/apf_uniform_ghidra/uniform_trace.txt"
REPORT = ROOT / "reports/specs/apf2k8_uniform_selector_bank_ownership.v1.json"


class UniformSelectorBankOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = ownership.build_report(EXPORT_ROOT, TRACE)

    def test_orientation_is_closed_by_literal_wrappers_and_accessors(self) -> None:
        report = self.report
        self.assertEqual(report["status"], "static_home_away_bank_orientation_closed")
        self.assertEqual(report["orientation_anchors"]["home"], {
            "literal": {"address": "0x845F21E8", "value": "HOME"},
            "wrapper": "0x849DC2C8",
            "family": "shoulder_normal",
            "selector_mode": 1,
            "bank_index": 0,
            "resource_class": "0x84E30180",
        })
        self.assertEqual(report["orientation_anchors"]["away"], {
            "literal": {"address": "0x845F21F4", "value": "AWAY"},
            "wrapper": "0x849DC378",
            "family": "shoulder_normal",
            "selector_mode": 0,
            "bank_index": 1,
            "resource_class": "0x84E318C0",
        })
        self.assertEqual(report["selector"]["mode_1"]["accessor_equation"],
                         "config[slot]")
        self.assertEqual(report["selector"]["mode_0"]["accessor_equation"],
                         "config[slot + 14]")
        self.assertTrue(report["claims"]["bank_0_is_home"])
        self.assertTrue(report["claims"]["bank_1_is_away"])

    def test_all_twelve_filename_families_have_exact_mode_pairs(self) -> None:
        pairs = self.report["family_pairs"]
        self.assertEqual(self.report["family_pair_count"], 12)
        self.assertEqual(self.report["wrapper_count"], 24)
        self.assertEqual(
            [pair["family"] for pair in pairs],
            [
                "glove", "helmet", "jersey", "logo", "textlogo", "font",
                "number", "pants", "shoe", "shoulder", "shoulder_normal", "sock",
            ],
        )
        for pair in pairs:
            self.assertEqual(pair["home"]["selector_mode"], 1)
            self.assertEqual(pair["home"]["bank_index"], 0)
            self.assertEqual(pair["away"]["selector_mode"], 0)
            self.assertEqual(pair["away"]["bank_index"], 1)
            if pair["family"] != "font":
                self.assertEqual(pair["home"]["resource_class"], "0x84E30180")
                self.assertEqual(pair["away"]["resource_class"], "0x84E318C0")

    def test_claim_boundary_remains_fail_closed(self) -> None:
        claims = self.report["claims"]
        self.assertFalse(claims["selector_bytes_1_through_7_semantics_proved"])
        self.assertFalse(claims["logo_selection_preview_consumption_proved"])
        self.assertFalse(claims["gameplay_runtime_consumption_proved"])
        self.assertFalse(claims["arbitrary_selector_writer_authorized"])

    def test_committed_report_is_canonical_and_exactly_reproducible(self) -> None:
        payload = REPORT.read_bytes()
        value = json.loads(payload)
        self.assertEqual(payload, ownership.canonical_json(value))
        regenerated = subprocess.check_output(
            [sys.executable, "tools/apf_uniform_selector_bank_ownership.py"],
            cwd=ROOT,
        )
        self.assertEqual(regenerated, payload)

    def test_tampered_home_anchor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            export = tmp / "apf2k8"
            (export / "pseudo_c").mkdir(parents=True)
            (export / "ledger").mkdir()
            shutil.copy2(EXPORT_ROOT / "manifest.json", export / "manifest.json")
            shutil.copy2(EXPORT_ROOT / ownership.PSEUDO_SHARD,
                         export / ownership.PSEUDO_SHARD)
            ledger = export / ownership.LEDGER_SHARD
            shutil.copy2(EXPORT_ROOT / ownership.LEDGER_SHARD, ledger)
            text = ledger.read_text(encoding="utf-8")
            self.assertIn('"value":"HOME"', text)
            ledger.write_text(text.replace('"value":"HOME"', '"value":"HOMX"'),
                              encoding="utf-8")
            with self.assertRaisesRegex(ownership.EvidenceError, "HOME anchor mismatch"):
                ownership.build_report(export, TRACE)

    def test_tampered_family_mode_pair_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            export = tmp / "apf2k8"
            (export / "pseudo_c").mkdir(parents=True)
            (export / "ledger").mkdir()
            shutil.copy2(EXPORT_ROOT / "manifest.json", export / "manifest.json")
            pseudo = export / ownership.PSEUDO_SHARD
            shutil.copy2(EXPORT_ROOT / ownership.PSEUDO_SHARD, pseudo)
            shutil.copy2(EXPORT_ROOT / ownership.LEDGER_SHARD,
                         export / ownership.LEDGER_SHARD)
            text = pseudo.read_text(encoding="utf-8")
            needle = "Function_849D6BD0(0x5a37fc45,0)"
            self.assertIn(needle, text)
            pseudo.write_text(text.replace(needle, "Function_849D6BD0(0x5a37fc45,1)"),
                              encoding="utf-8")
            with self.assertRaisesRegex(ownership.EvidenceError,
                                        "does not have one wrapper per mode"):
                ownership.build_report(export, TRACE)


if __name__ == "__main__":
    unittest.main()
