#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nfl_franchise_limit_feasibility",
    ROOT / "tools/nfl_franchise_limit_feasibility.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FranchiseLimitFeasibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = MODULE.generate()

    def test_matrix_is_exactly_bounded(self) -> None:
        self.assertEqual(
            [row["id"] for row in self.report["matrix"]],
            [
                "cpu_fantasy_draft_priority",
                "cpu_trade_evaluation",
                "salary_cap_enforcement",
                "contract_model_and_serialization",
                "future_super_bowl_stadium_assignment",
            ],
        )
        self.assertTrue(all(not row["archive_only_fix"] for row in self.report["matrix"]))
        self.assertTrue(all(not row["current_writer_safe"] for row in self.report["matrix"]))

    def test_exact_static_anchors_are_not_generalized(self) -> None:
        draft = self.report["matrix"][0]
        cap = self.report["matrix"][2]
        stadium = self.report["matrix"][4]
        self.assertEqual(draft["proof"]["weight_count"], 17)
        self.assertEqual(cap["proof"]["team_total_field"], "+0x124 in the runtime team object")
        self.assertFalse(cap["proof"]["annual_cap_growth_formula_proved"])
        self.assertEqual(stadium["proof"]["classifier_condition"],
                         "franchise phase/mode 9 and week 0x14")
        self.assertTrue(stadium["proof"]["venue_rotation_table_proved"])
        self.assertEqual(
            [row["stadium_key"] for row in stadium["proof"]["season_index_mapping"]],
            ["s40", "s42", "s43", "s41", "s44"],
        )
        self.assertEqual(stadium["proof"]["default_mapping"]["condition"],
                         "season_index >= 5")
        self.assertEqual(stadium["proof"]["default_mapping"]["stadium_key"], "s45")
        self.assertEqual(stadium["proof"]["default_mapping"]["location"], "San Jose, CA")
        self.assertTrue(stadium["proof"]["all_season_indices_at_or_above_5_collapse_to_s45"])

    def test_pcsx2_boundary_is_explicit(self) -> None:
        boundary = self.report["platform_boundary"]
        self.assertFalse(boundary["pcsx2_ps2_executable_is_a_canonical_input"])
        self.assertFalse(boundary["xbox_virtual_addresses_transfer_to_ps2"])
        self.assertIn("PS2 ELF", boundary["conclusion"])

    def test_canonical_outputs_match_generator(self) -> None:
        report_path = ROOT / "reports/gameplay_tuning/nfl_franchise_limit_feasibility.json"
        tsv_path = ROOT / "reports/gameplay_tuning/nfl_franchise_limit_feasibility.tsv"
        self.assertEqual(report_path.read_bytes(), MODULE.canonical_json(self.report))
        self.assertEqual(tsv_path.read_text(), MODULE.matrix_tsv(self.report))

    def test_output_refuses_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text("do not replace\n")
            link = root / "report.json"
            link.symlink_to(target)
            with self.assertRaises(MODULE.FeasibilityError):
                MODULE.write_output(link, b"{}\n")
            self.assertEqual(target.read_text(), "do not replace\n")


if __name__ == "__main__":
    unittest.main()
