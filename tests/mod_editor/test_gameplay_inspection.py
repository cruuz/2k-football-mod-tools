"""Public-editor gameplay and franchise inspection tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.gameplay_inspection import (
    DEFAULT_FRANCHISE_REPORT,
    DEFAULT_NFL_SAVE_REPORT,
    DEFAULT_PS2_FIXTURE_REPORT,
    DEFAULT_TUNING_REPORT,
    inspect_draft_priority,
    inspect_gameplay_sliders,
    inspect_nfl_franchise_limit,
    inspect_nfl_save_inventory,
)


RAW_ADDRESS = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)


class GameplayInspectionTests(unittest.TestCase):
    def test_shared_slider_names_and_stock_range_are_exact(self) -> None:
        nfl = inspect_gameplay_sliders("NFL2K5")
        apf = inspect_gameplay_sliders("apf2k8")
        self.assertEqual(nfl["slider_count"], 21)
        self.assertEqual(apf["slider_count"], 21)
        self.assertEqual(
            [row["name"] for row in nfl["sliders"]],
            [row["name"] for row in apf["sliders"]],
        )
        self.assertEqual(nfl["sliders"][3]["name"], "Human Catching")
        self.assertEqual(nfl["sliders"][12]["name"], "CPU Catching")
        self.assertEqual(nfl["sliders"][20]["name"], "Interception")
        self.assertEqual(
            nfl["stock_ui_range"], {"minimum": 0.0, "maximum": 1.0, "step": 0.025}
        )
        self.assertFalse(nfl["save_or_profile_writer_available"])
        self.assertTrue(nfl["observed_fixture_values_available"])
        self.assertEqual(nfl["sliders"][3]["observed_settings1_value"], 0.5)
        self.assertEqual(nfl["sliders"][3]["observed_franchise1_value"], 0.35)
        self.assertFalse(apf["observed_fixture_values_available"])
        self.assertFalse(apf["executable_writer_available"])
        self.assertFalse(apf["out_of_range_runtime_safety_proved"])

    def test_platform_specific_slider_proof_is_not_overstated(self) -> None:
        nfl = inspect_gameplay_sliders("nfl2k5")
        apf = inspect_gameplay_sliders("apf2k8")
        self.assertTrue(
            nfl["platform_proof"][
                "all_human_cpu_controls_reach_an_aggregate_consumer"
            ]
        )
        self.assertFalse(
            nfl["platform_proof"]["final_catch_or_drop_branch_proved"]
        )
        self.assertEqual(apf["platform_proof"]["exact_serialized_byte_count"], 84)
        self.assertFalse(
            apf["platform_proof"]["final_catch_or_drop_consumer_proved"]
        )

    def test_nfl_and_apf_draft_lineage_have_different_proof_status(self) -> None:
        nfl = inspect_draft_priority("nfl2k5")
        apf = inspect_draft_priority("apf2k8")
        expected = [
            ("QB", 2.0), ("K", 0.1), ("P", 0.2), ("WR", 1.4),
            ("CB", 1.0), ("FS", 1.1), ("SS", 1.1), ("RB", 1.7),
            ("FB", 1.0), ("TE", 1.2), ("OLB", 1.2), ("ILB", 0.7),
            ("C", 0.5), ("G", 1.1), ("T", 1.3), ("DT", 1.4),
            ("DE", 1.3),
        ]
        for value in (nfl, apf):
            self.assertEqual(value["position_weight_count"], 17)
            self.assertEqual(
                [(row["position"], row["weight"]) for row in value["position_weights"]],
                expected,
            )
            self.assertFalse(value["safe_writer_available"])
            self.assertFalse(value["runtime_patch_performed"])
        self.assertTrue(nfl["proof_status"]["cpu_selector_owner_proved"])
        self.assertFalse(apf["proof_status"]["cpu_selector_owner_proved"])
        self.assertEqual(apf["proof_status"]["table_copy_count"], 2)

    def test_complete_franchise_matrix_has_no_writer(self) -> None:
        value = inspect_nfl_franchise_limit("all")
        self.assertEqual(value["target_count"], 5)
        self.assertEqual(value["safe_writer_count"], 0)
        self.assertEqual(value["archive_only_fix_count"], 0)
        self.assertFalse(value["pcsx2_patch_coordinates_available"])
        self.assertEqual(value["pcsx2_target"]["serial"], "SLUS-20919")
        self.assertEqual(value["pcsx2_target"]["boot_elf_expected_name"], "SLUS_209.19")
        self.assertFalse(value["pcsx2_local_fixture_status"]["safe_patch_ready"])
        self.assertEqual(len(value["pcsx2_limitation_status"]), 4)
        self.assertTrue(all(
            not row["xbox_address_reuse_allowed"]
            for row in value["pcsx2_limitation_status"]
        ))
        self.assertEqual(
            [row["id"] for row in value["targets"]],
            [
                "cpu_fantasy_draft_priority",
                "cpu_trade_evaluation",
                "salary_cap_enforcement",
                "contract_model_and_serialization",
                "future_super_bowl_stadium_assignment",
            ],
        )
        self.assertTrue(all(not row["archive_only_fix"] for row in value["targets"]))
        self.assertTrue(all(not row["current_writer_safe"] for row in value["targets"]))
        self.assertIsNone(RAW_ADDRESS.search(json.dumps(value)))

    def test_named_salary_and_super_bowl_evidence_is_actionable_but_read_only(self) -> None:
        salary = inspect_nfl_franchise_limit("salary-cap")["target"]
        self.assertEqual(salary["id"], "salary_cap_enforcement")
        self.assertEqual(
            salary["named_evidence"]["maximum_roster_count_allowed_by_gate"], 54
        )
        self.assertFalse(salary["named_evidence"]["annual_cap_growth_formula_proved"])

        venue = inspect_nfl_franchise_limit("super-bowl")["target"]
        evidence = venue["named_evidence"]
        self.assertEqual(len(evidence["season_zero_through_four"]), 5)
        self.assertEqual(
            evidence["season_five_and_later"]["location"], "San Jose, CA"
        )
        self.assertTrue(
            evidence["season_five_and_later"]["all_later_seasons_collapse_here"]
        )
        self.assertFalse(evidence["year_five_or_six_runtime_reproduction_complete"])

    def test_every_named_franchise_target_resolves(self) -> None:
        expected = {
            "draft": "cpu_fantasy_draft_priority",
            "trade": "cpu_trade_evaluation",
            "salary-cap": "salary_cap_enforcement",
            "contracts": "contract_model_and_serialization",
            "super-bowl": "future_super_bowl_stadium_assignment",
        }
        for target, row_id in expected.items():
            with self.subTest(target=target):
                result = inspect_nfl_franchise_limit(target)
                self.assertEqual(result["target_name"], target)
                self.assertEqual(result["target"]["id"], row_id)
                self.assertFalse(result["target"]["current_writer_safe"])

    def test_sanitized_nfl_save_inventory_has_values_and_signature_boundary(self) -> None:
        value = inspect_nfl_save_inventory()
        self.assertEqual(value["container_count"], 8)
        self.assertEqual(
            {row["type"] for row in value["containers"]},
            {"USR", "STG", "FXG", "TMM"},
        )
        self.assertEqual(len(value["observed_slider_values"]), 21)
        self.assertEqual(value["observed_slider_values"][3], {
            "name": "Human Catching",
            "settings1": 0.5,
            "franchise1": 0.35,
        })
        self.assertTrue(value["integrity_boundary"]["savegame_signature_owned"])
        self.assertEqual(value["integrity_boundary"]["extra_size"], 20)
        self.assertFalse(value["integrity_boundary"]["safe_writer_available"])
        self.assertIsNone(RAW_ADDRESS.search(json.dumps(value)))

    def test_raw_or_unknown_selectors_are_refused(self) -> None:
        for game in ("xbox", "ps2", "offset:123"):
            with self.subTest(game=game), self.assertRaises(ValidationError):
                inspect_gameplay_sliders(game)
            with self.subTest(draft_game=game), self.assertRaises(ValidationError):
                inspect_draft_priority(game)
        for target in ("cap-offset", "address:123", "venue-table", ""):
            with self.subTest(target=target), self.assertRaises(ValidationError):
                inspect_nfl_franchise_limit(target)

    def test_symlink_and_tampered_reports_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tuning_link = root / "tuning-link.json"
            tuning_link.symlink_to(DEFAULT_TUNING_REPORT)
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_gameplay_sliders("nfl2k5", tuning_link)

            tuning_changed = root / "tuning-changed.json"
            tuning_payload = bytearray(DEFAULT_TUNING_REPORT.read_bytes())
            tuning_payload[-2] = ord(" ")
            tuning_changed.write_bytes(tuning_payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_draft_priority("apf2k8", tuning_changed)

            franchise_link = root / "franchise-link.json"
            franchise_link.symlink_to(DEFAULT_FRANCHISE_REPORT)
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_nfl_franchise_limit("all", franchise_link)

            franchise_changed = root / "franchise-changed.json"
            franchise_payload = bytearray(DEFAULT_FRANCHISE_REPORT.read_bytes())
            franchise_payload[-2] = ord(" ")
            franchise_changed.write_bytes(franchise_payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_nfl_franchise_limit("trade", franchise_changed)

            save_link = root / "save-link.json"
            save_link.symlink_to(DEFAULT_NFL_SAVE_REPORT)
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_nfl_save_inventory(save_link)

            save_changed = root / "save-changed.json"
            save_payload = bytearray(DEFAULT_NFL_SAVE_REPORT.read_bytes())
            save_payload[-2] = ord(" ")
            save_changed.write_bytes(save_payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_nfl_save_inventory(save_changed)

            save_copy = root / "save-copy.json"
            save_copy.write_bytes(DEFAULT_NFL_SAVE_REPORT.read_bytes())
            save_hardlink = root / "save-hardlink.json"
            os.link(save_copy, save_hardlink)
            for aliased_report in (save_copy, save_hardlink):
                with self.subTest(aliased_report=aliased_report), self.assertRaisesRegex(
                    ValidationError, "single-link"
                ):
                    inspect_nfl_save_inventory(aliased_report)

            ps2_link = root / "ps2-link.json"
            ps2_link.symlink_to(DEFAULT_PS2_FIXTURE_REPORT)
            with self.assertRaisesRegex(ValidationError, "non-symlink"):
                inspect_nfl_franchise_limit(
                    "all", ps2_fixture_report_path=ps2_link
                )

            ps2_changed = root / "ps2-changed.json"
            ps2_payload = bytearray(DEFAULT_PS2_FIXTURE_REPORT.read_bytes())
            ps2_payload[-2] = ord(" ")
            ps2_changed.write_bytes(ps2_payload)
            with self.assertRaisesRegex(ValidationError, "hash"):
                inspect_nfl_franchise_limit(
                    "trade", ps2_fixture_report_path=ps2_changed
                )


if __name__ == "__main__":
    unittest.main()
