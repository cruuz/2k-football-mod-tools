#!/usr/bin/env python3
"""Focused tests for the bounded APF selector runtime verifier."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_uniform_selector_xenia_runtime_verify as runtime_verify  # noqa: E402


RUNTIME = Path(
    "/media/noah/Storage/.codex-tmp/apf-all-family-selector-runtime-20260716"
)
REPORT = ROOT / "reports/assets/apf_uniform_selector_xenia_runtime.json"


class APFUniformSelectorXeniaRuntimeVerifyTests(unittest.TestCase):
    @unittest.skipUnless(REPORT.is_file(), "final runtime report is unavailable")
    def test_final_logo_selection_result_is_bounded_negative(self) -> None:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(
            report["outcome"]["classification"],
            "pose_matched_assassins_helmet_selector_not_visible_in_logo_selection_xenia",
        )
        self.assertFalse(report["outcome"]["localization_gate_passed"])
        search = report["visual_probe"]["localization_gate_search"]
        self.assertEqual(search["reference_eligible_pair_count"], 79)
        self.assertEqual(search["all_gate_pair_count"], 0)
        self.assertAlmostEqual(
            report["visual_probe"]["observed"][
                "evidence_to_reference_mad_ratio"
            ],
            0.46033725750686016,
        )

    @unittest.skipUnless(
        (RUNTIME / "game-retail/0A").is_file()
        and (RUNTIME / "game-all-family/0A").is_file(),
        "local APF selector runtime copies are unavailable",
    )
    def test_team_one_witness_is_exactly_helmet_one_to_two_in_both_banks(self) -> None:
        witness = runtime_verify.selector_witness(
            RUNTIME / "game-retail/0A", RUNTIME / "game-all-family/0A"
        )
        self.assertEqual(witness["changed_families"], ["helmet"])
        self.assertEqual(witness["source_asset_indices"]["helmet"], 1)
        self.assertEqual(witness["output_asset_indices"]["helmet"], 2)
        self.assertEqual(
            witness["helmet_banks"],
            [
                {
                    "bank": 0,
                    "selector_record_index": 465,
                    "selector_record_offset": "0x1e10b0",
                    "source_record_hex": "0105020201000000",
                    "output_record_hex": "0205020201000000",
                    "opaque_bytes_1_through_7_bit_exact": True,
                },
                {
                    "bank": 1,
                    "selector_record_index": 451,
                    "selector_record_offset": "0x1e1040",
                    "source_record_hex": "0105020201000000",
                    "output_record_hex": "0205020201000000",
                    "opaque_bytes_1_through_7_bit_exact": True,
                },
            ],
        )
        self.assertTrue(witness["other_ten_family_records_bit_exact"])

    def test_runtime_verifier_imports_no_selector_writer_or_planner(self) -> None:
        tree = ast.parse(
            (ROOT / "tools/apf_uniform_selector_xenia_runtime_verify.py").read_text(
                encoding="utf-8"
            )
        )
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("apf_uniform_selector_patch", imported)
        self.assertNotIn("apf_uniform_selector_allocation", imported)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"one","schema":"two"}\n', encoding="utf-8")
            with self.assertRaisesRegex(runtime_verify.RuntimeVerifyError, "duplicate key"):
                runtime_verify.load_json(path, "fixture")

    def test_pose_reference_and_evidence_boxes_are_disjoint(self) -> None:
        def intersects(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
            return not (
                left[2] <= right[0] or right[2] <= left[0]
                or left[3] <= right[1] or right[3] <= left[1]
            )

        for reference in runtime_verify.pose_match.REFERENCE_BOXES:
            for evidence in runtime_verify.pose_match.EVIDENCE_BOXES:
                self.assertFalse(intersects(reference, evidence))


if __name__ == "__main__":
    unittest.main()
