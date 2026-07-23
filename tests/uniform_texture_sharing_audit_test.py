#!/usr/bin/env python3
"""Deterministic assertions for the cross-title uniform-sharing audit."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import uniform_texture_sharing_audit as audit  # noqa: E402


class UniformTextureSharingAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report, cls.nfl_groups, cls.apf_rows = audit.build_report()

    def test_nfl_content_aliases_are_not_physical_span_aliases(self) -> None:
        nfl = self.report["nfl2k5"]
        self.assertEqual(nfl["uniform_selector_count"], 634)
        self.assertEqual(nfl["physical_storage"]["write_unit_count"], 3170)
        self.assertEqual(nfl["physical_storage"]["distinct_interval_count"], 3170)
        self.assertEqual(nfl["physical_storage"]["cross_selector_overlap_count"], 0)
        self.assertTrue(nfl["physical_storage"]["all_intervals_pairwise_disjoint"])
        self.assertFalse(nfl["practical_fix"]["archive_growth_required"])
        self.assertFalse(nfl["practical_fix"]["xdvdfs_relayout_required"])
        self.assertFalse(nfl["practical_fix"]["code_or_pointer_change_required"])
        self.assertFalse(nfl["practical_fix"]["arbitrary_input_guaranteed_to_fit"])

    def test_nfl_role_counts_and_exact_cross_team_owners_are_frozen(self) -> None:
        roles = {
            role["texture_name"]: role
            for family in self.report["nfl2k5"]["families"]
            for role in family["roles"]
        }
        expected = {
            "jersey00": (382, 13, 123),
            "jersey00_mud": (382, 13, 123),
            "pants00": (340, 0, 0),
            "pants00_mud": (340, 0, 0),
            "sleeve00": (353, 3, 75),
            "sleeve00_mud": (353, 3, 75),
            "helmet00": (222, 0, 0),
            "helmet02": (220, 0, 0),
        }
        self.assertEqual(set(roles), set(expected))
        for name, values in expected.items():
            self.assertEqual(
                (
                    roles[name]["exact_visual_identity_count"],
                    roles[name]["cross_asset_code_identity_group_count"],
                    roles[name]["cross_asset_code_affected_selector_count"],
                ),
                values,
            )
        self.assertEqual(len(self.nfl_groups), 32)
        self.assertEqual(sum(group["owner_count"] for group in self.nfl_groups), 396)
        for group in self.nfl_groups:
            self.assertGreater(group["asset_code_count"], 1)
            spans = {
                (owner["xiso_absolute_span_offset"], owner["span_size"])
                for owner in group["owners"]
            }
            self.assertEqual(len(spans), group["owner_count"])

    def test_apf_selector_aliases_and_capacity_boundary_are_exact(self) -> None:
        apf = self.report["apf2k8"]
        self.assertEqual(apf["jersey_catalog_asset_count"], 24)
        self.assertEqual(apf["selector_row_count"], 80)
        self.assertEqual(apf["used_asset_indices"], [0, 2, 4, 6, 8, 11, 12, 13, 19, 23])
        self.assertEqual(
            apf["unreferenced_asset_indices"],
            [1, 3, 5, 7, 9, 10, 14, 15, 16, 17, 18, 20, 21, 22],
        )
        assets = {row["asset_index"]: row for row in apf["assets"]}
        self.assertEqual((assets[6]["selector_owner_count"], assets[6]["team_count"]), (2, 1))
        self.assertEqual((assets[23]["selector_owner_count"], assets[23]["team_count"]), (26, 13))
        self.assertEqual({row["bank"] for row in assets[23]["owners"]}, {0, 1})
        self.assertNotIn("home", json.dumps(assets[23]).lower())
        self.assertNotIn("away", json.dumps(assets[23]).lower())

    def test_apf_plan_uses_all_assets_and_bounds_offline_writer_claim(self) -> None:
        plan = self.report["apf2k8"]["built_in_unique_allocation_plan"]
        self.assertEqual(len(plan["plan"]), 24)
        self.assertEqual(
            sorted(row["proposed_unique_asset_index"] for row in plan["plan"]),
            list(range(24)),
        )
        self.assertEqual(sum(row["changes_selector_byte_0"] for row in plan["plan"]), 15)
        conflicts = [row for row in plan["plan"] if row["retail_placeholder_conflict"]]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["proposed_unique_asset_index"], 12)
        practical = self.report["apf2k8"]["practical_fix"]
        self.assertTrue(practical["safe_offline_cli_dealias_writer_available"])
        self.assertFalse(practical["public_gui_dealias_writer_available"])
        self.assertFalse(practical["runtime_witness_available"])
        self.assertIn("independently verified offline", plan["status"])

    def test_committed_outputs_regenerate_byte_exact(self) -> None:
        committed = ROOT / "reports/assets/uniform_texture_sharing.v2.json"
        self.assertEqual(committed.read_bytes(), audit.canonical_json(self.report))
        legacy = ROOT / "reports/assets/uniform_texture_sharing.json"
        self.assertEqual(
            legacy.read_bytes(),
            audit.canonical_json(audit.legacy_v1_report(self.report)),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nfl = root / "nfl.tsv"
            apf = root / "apf.tsv"
            audit.write_nfl_tsv(nfl, self.nfl_groups)
            audit.write_apf_tsv(apf, self.apf_rows)
            self.assertEqual(
                nfl.read_bytes(),
                (ROOT / "reports/assets/nfl2k5_uniform_texture_sharing.tsv").read_bytes(),
            )
            self.assertEqual(
                apf.read_bytes(),
                (ROOT / "reports/assets/apf2k8_jersey_selector_sharing.tsv").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
