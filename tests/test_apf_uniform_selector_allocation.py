#!/usr/bin/env python3
"""Focused tests for the APF all-family selector allocation checkpoint."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_uniform_selector_allocation as allocation  # noqa: E402


class APFUniformSelectorAllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory, cls.inventory_raw = allocation.load_inventory(
            allocation.DEFAULT_INVENTORY
        )
        cls.report = allocation.build_report(cls.inventory, cls.inventory_raw)
        cls.by_family = {row["family"]: row for row in cls.report["families"]}

    def test_exact_inventory_copy_is_required_even_at_an_alternate_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "inventory.json"
            copied.write_bytes(self.inventory_raw)
            value, raw = allocation.load_inventory(copied)
            self.assertEqual(value["schema"], allocation.INVENTORY_SCHEMA)
            self.assertEqual(raw, self.inventory_raw)
            copied.write_bytes(self.inventory_raw[:-1] + b" ")
            with self.assertRaisesRegex(
                allocation.AllocationError,
                "identity drift",
            ):
                allocation.load_inventory(copied)

    def test_strict_json_rejects_duplicate_nonfinite_and_noncanonical_forms(self) -> None:
        with self.assertRaisesRegex(allocation.AllocationError, "duplicate key"):
            allocation._strict_json_object(b'{"a":1,"a":2}\n', "fixture")
        with self.assertRaisesRegex(allocation.AllocationError, "forbidden constant"):
            allocation._strict_json_object(b'{"a":NaN}\n', "fixture")
        with self.assertRaisesRegex(allocation.AllocationError, "not canonical"):
            allocation._strict_json_object(b'{"a":1}\n', "fixture")

    def test_all_filename_owned_slots_and_two_bank_records_are_covered(self) -> None:
        expected = [
            (2, "glove", ["glove"], 3),
            (3, "helmet", ["helmet"], 24),
            (4, "jersey", ["jersey"], 24),
            (5, "logo", ["logo"], 118),
            (6, "textlogo", ["textlogo"], 206),
            (7, "font", ["font"], 11),
            (8, "number", ["number"], 24),
            (9, "pants", ["pants"], 24),
            (10, "shoe", ["shoe"], 11),
            (11, "shoulder", ["shoulder", "shoulder_normal"], 24),
            (12, "sock", ["sock"], 24),
        ]
        self.assertEqual(
            [
                (
                    row["selector_slot"],
                    row["family"],
                    row["physical_families"],
                    row["catalog_count"],
                )
                for row in self.report["families"]
            ],
            expected,
        )
        records = [
            record
            for family in self.report["families"]
            for team in family["retail"]["selector_evidence"]
            for record in team["bank_selector_records"]
        ]
        self.assertEqual(len(records), 880)
        self.assertEqual(len({row["selector_record_index"] for row in records}), 880)
        self.assertEqual(len({row["selector_record_offset"] for row in records}), 880)
        self.assertTrue(
            all(
                family["retail"]["bank_byte_0_equal_for_every_team"]
                for family in self.report["families"]
            )
        )

    def test_allocator_reserves_later_retail_identity_and_minimizes_changes(self) -> None:
        retail = [1, 1, 0] + [0] * 37
        plan = allocation.maximum_isolation_plan(retail, 3, 3)
        self.assertEqual(plan["assignment_vector"], [1, 2, 0])
        self.assertEqual(plan["changed_team_indices"], [1])
        self.assertEqual(plan["minimum_changed_team_count_for_upper_bound"], 1)
        exhausted = allocation.maximum_isolation_plan(retail, 2, 3)
        self.assertEqual(exhausted["assignment_vector"], [1, 1, 0])
        self.assertEqual(exhausted["changed_team_indices"], [])
        self.assertEqual(exhausted["distinct_asset_count_after"], 2)

    def test_every_plan_reaches_the_bound_with_the_proved_minimum_writes(self) -> None:
        for family in self.report["families"]:
            for key in ("built_in_plan", "all_team_plan"):
                with self.subTest(family=family["family"], scope=key):
                    plan = family[key]
                    self.assertEqual(
                        plan["distinct_asset_count_after"],
                        plan["catalog_capacity_upper_bound"],
                    )
                    self.assertEqual(
                        plan["changed_team_count"],
                        plan["minimum_changed_team_count_for_upper_bound"],
                    )
                    self.assertEqual(
                        len(set(plan["assignment_vector"])),
                        plan["distinct_asset_count_after"],
                    )
                    self.assertEqual(
                        plan["changed_selector_byte_count_both_banks"],
                        2 * plan["changed_team_count"],
                    )

    def test_capacity_summary_and_combined_change_counts_are_exact(self) -> None:
        self.assertEqual(
            self.report["summary"]["built_in_24_scope_internally_isolatable_families"],
            [
                "helmet",
                "jersey",
                "logo",
                "textlogo",
                "number",
                "pants",
                "shoulder",
                "sock",
            ],
        )
        self.assertEqual(
            self.report["summary"]["all_40_scope_internally_isolatable_families"],
            ["logo", "textlogo"],
        )
        self.assertEqual(
            self.report["combined_plans"],
            {
                "all_40": {
                    "changed_selector_byte_count_both_banks": 250,
                    "changed_team_family_assignment_count": 125,
                    "component_family_plan_count": 11,
                },
                "built_in_24": {
                    "changed_selector_byte_count_both_banks": 190,
                    "changed_team_family_assignment_count": 95,
                    "component_family_plan_count": 11,
                },
            },
        )

    def test_jersey_built_in_plan_matches_checked_writer_recipe_exactly(self) -> None:
        recipe = json.loads(
            (
                ROOT
                / "reports/asset_samples/apf_roster/jersey_all_24_built_in_unique.v1.json"
            ).read_text(encoding="utf-8")
        )
        expected = [
            row["replacement_asset_index"] for row in recipe["assignments"]
        ]
        jersey = self.by_family["jersey"]
        self.assertEqual(jersey["built_in_plan"]["assignment_vector"], expected)
        self.assertEqual(jersey["built_in_plan"]["changed_team_count"], 15)
        self.assertEqual(
            jersey["built_in_plan"]["outside_scope_boundary"],
            {
                "asset_indices_shared_with_unchanged_outside_scope": [12, 13],
                "outside_scope_team_count": 16,
                "scope_team_indices_sharing_with_unchanged_outside_scope": [6, 14],
            },
        )

    def test_bank_disagreement_and_family_group_drift_fail_closed(self) -> None:
        changed = copy.deepcopy(self.inventory)
        selector = changed["team_selector_graph"]["teams"][0]["banks"][1][
            "selectors"
        ][4]
        selector["asset_index_byte_0"] = 7
        selector["raw_record_hex"] = "07" + selector["raw_record_hex"][2:]
        with self.assertRaisesRegex(allocation.AllocationError, "differs between"):
            allocation.build_report(changed, self.inventory_raw)

        changed = copy.deepcopy(self.inventory)
        changed["family_specs"][0]["selector_slot"] = 1
        with self.assertRaisesRegex(allocation.AllocationError, "grouping drift"):
            allocation.build_report(changed, self.inventory_raw)

    def test_committed_report_regenerates_byte_exact(self) -> None:
        path = ROOT / "reports/assets/apf_uniform_selector_allocation.json"
        self.assertEqual(
            path.read_bytes(),
            allocation.canonical_json_bytes(self.report),
        )

    def test_machine_spec_matches_reports_and_freezes_writer_boundary(self) -> None:
        spec, spec_raw = allocation.load_allocation_spec()
        self.assertEqual(spec_raw, allocation.canonical_pretty_json_bytes(spec))
        probe = json.loads(
            (
                ROOT / "reports/assets/apf_uniform_selector_capacity_probe.json"
            ).read_text(encoding="utf-8")
        )
        expected_contracts = []
        for family in self.report["families"]:
            expected_contracts.append({
                "all_40_changed_team_count": family["all_team_plan"][
                    "changed_team_count"
                ],
                "all_40_distinct_upper_bound": family["all_team_plan"][
                    "catalog_capacity_upper_bound"
                ],
                "built_in_24_changed_team_count": family["built_in_plan"][
                    "changed_team_count"
                ],
                "built_in_24_distinct_upper_bound": family["built_in_plan"][
                    "catalog_capacity_upper_bound"
                ],
                "catalog_count": family["catalog_count"],
                "family": family["family"],
                "physical_families": family["physical_families"],
                "selector_slot": family["selector_slot"],
            })
        self.assertEqual(spec["family_contracts"], expected_contracts)
        self.assertEqual(
            spec["capacity_results"]["built_in_24"][
                "combined_h7a_payload_headroom_bytes"
            ],
            probe["combined"]["built_in_24"]["h7a_payload_headroom_bytes"],
        )
        self.assertEqual(
            spec["capacity_results"]["all_40"][
                "combined_h7a_payload_headroom_bytes"
            ],
            probe["combined"]["all_40"]["h7a_payload_headroom_bytes"],
        )
        self.assertEqual(
            spec["writer_admission"]["admitted_fail_closed_selector_writer_families"],
            ["jersey"],
        )
        self.assertFalse(
            spec["writer_admission"]["generic_or_additional_family_writer_available"]
        )

    def test_capacity_probe_is_canonical_pinned_and_fit_only(self) -> None:
        path = ROOT / "reports/assets/apf_uniform_selector_capacity_probe.json"
        raw = path.read_bytes()
        probe = json.loads(raw)
        self.assertEqual(raw, allocation.canonical_json_bytes(probe))
        allocation_raw = (
            ROOT / "reports/assets/apf_uniform_selector_allocation.json"
        ).read_bytes()
        self.assertEqual(
            probe["source"]["allocation_report_sha256"],
            allocation.sha256_bytes(allocation_raw),
        )
        self.assertEqual(
            (
                probe["combined"]["built_in_24"]["changed_decoded_byte_count"],
                probe["combined"]["built_in_24"]["h7a_payload_size_bytes"],
                probe["combined"]["built_in_24"]["h7a_payload_headroom_bytes"],
            ),
            (190, 435_528, 496),
        )
        self.assertEqual(
            (
                probe["combined"]["all_40"]["changed_decoded_byte_count"],
                probe["combined"]["all_40"]["h7a_payload_size_bytes"],
                probe["combined"]["all_40"]["h7a_payload_headroom_bytes"],
            ),
            (250, 435_727, 297),
        )
        self.assertTrue(
            all(
                scope["fits_fixed_h7a_payload_limit"]
                for family in probe["families"]
                for scope in family["scopes"].values()
            )
        )
        self.assertFalse(
            probe["claim_boundary"]["binary_fit_is_recipe_or_write_authority"]
        )


if __name__ == "__main__":
    unittest.main()
