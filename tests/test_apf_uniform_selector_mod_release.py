#!/usr/bin/env python3
"""Focused tests for the packaged APF all-family selector mod release."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_uniform_selector_mod_release_verify as release_verify  # noqa: E402


REPORT = ROOT / "reports/assets/apf_uniform_selector_mod_release.v1.json"
QUEUE = ROOT / "reports/assets/apf_uniform_selector_xenia_replay_queue.v1.json"


class APFUniformSelectorModReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.queue = json.loads(QUEUE.read_text(encoding="utf-8"))

    def test_release_is_metadata_only_and_runtime_claim_is_bounded_negative(self) -> None:
        self.assertEqual(self.report["schema"], "apf_uniform_selector_mod_release/v1")
        self.assertEqual(self.report["version"], "1.0.0")
        self.assertFalse(self.report["distribution"]["retail_game_bytes_included"])
        self.assertFalse(self.report["distribution"]["copied_output_volume_included"])
        self.assertTrue(self.report["claim_boundary"]["offline_installable_mod_proved"])
        self.assertFalse(self.report["claim_boundary"]["assassins_helmet_runtime_proved"])
        self.assertEqual(
            self.report["runtime_queue"]["status"],
            "executed_from_frozen_queue_negative",
        )
        self.assertTrue(
            self.report["claim_boundary"]["assassins_logo_selection_negative_proved"]
        )
        self.assertFalse(self.report["claim_boundary"]["assassins_helmet_runtime_proved"])
        self.assertEqual(
            self.report["production_integration"]["capability_id"],
            "apf2k8.colors.uniform_selector_all_family_capacity",
        )
        self.assertFalse(self.report["production_integration"]["gui_exposed"])

    def test_exact_output_and_preservation_facts_are_frozen(self) -> None:
        result = self.report["offline_proof"]["result"]
        self.assertEqual(result["copied_0a_size_bytes"], 1_140_850_688)
        self.assertEqual(
            result["copied_0a_sha256"],
            "d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a",
        )
        self.assertEqual(result["decoded_changed_byte_count"], 190)
        self.assertTrue(result["all_bytes_outside_outer_entry_bit_exact"])
        self.assertTrue(result["all_online_and_user_slots_bit_exact"])
        self.assertTrue(result["selector_bytes_1_through_7_bit_exact"])
        self.assertFalse(result["retail_source_modified"])

    def test_builder_is_copy_only_and_never_hard_links_retail_files(self) -> None:
        source = (ROOT / "tools/build_apf_uniform_selector_mod.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("--preflight-only", source)
        self.assertIn("refusing to replace output game directory", source)
        self.assertIn(".owned-by-apf-uniform-selector-builder", source)
        self.assertIn("cp --reflink=auto", source)
        self.assertNotIn("cp -l", source)
        self.assertNotIn("rm -rf -- \"$source_game\"", source)

    def test_queued_replay_is_exact_and_exclusive(self) -> None:
        gate = self.queue["exclusive_input_gate"]
        self.assertTrue(gate["required"])
        self.assertEqual(gate["shared_controller_release_event"], "event19")
        self.assertFalse(gate["release_received"])
        self.assertEqual(
            self.queue["toolchain"]["controller"],
            "tools/apf_uniform_selector_xenia_gamepad.py",
        )
        self.assertEqual(
            self.queue["toolchain"]["controller_scope"],
            "dedicated_hash_stable_apf_replay_only",
        )
        self.assertEqual(
            [row["command"] for row in self.queue["ordered_inputs"]],
            [
                "TAP START 5.00",
                "TAP A 0.50",
                "TAP A 0.50",
                "TAP A 0.50",
                "TAP START 0.50",
                "TAP A 0.50",
                "TAP START 0.50",
                "TAP START 0.50",
                "TAP RT 0.35",
            ],
        )
        self.assertEqual(self.queue["capture_contract"]["frame_count_per_run"], 48)
        self.assertFalse(self.queue["capture_contract"]["uniform_package_accepted"])

    def test_release_verifier_imports_no_writer_or_allocation_planner(self) -> None:
        tree = ast.parse(
            (ROOT / "tools/apf_uniform_selector_mod_release_verify.py").read_text(
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

    def test_duplicate_release_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"one","schema":"two"}\n', encoding="utf-8")
            with self.assertRaisesRegex(release_verify.ReleaseVerifyError, "duplicate key"):
                release_verify.load_json(path, "fixture")

    def test_metadata_gate_does_not_stat_cleaned_replay_inputs(self) -> None:
        queue = release_verify._validate_replay_queue(ROOT, self.report)
        self.assertEqual(queue["status"], "queued_not_executed")
        self.assertFalse(Path(queue["runs"][0]["game_0a"]).exists())
        self.assertFalse(Path(queue["runs"][1]["game_0a"]).exists())

    def test_metadata_gate_never_calls_the_full_volume_verifier(self) -> None:
        with mock.patch.object(
            release_verify.selector_verify,
            "verify",
            side_effect=AssertionError("full-volume verifier was called"),
        ) as deep:
            result = release_verify.verify(
                ROOT,
                REPORT,
                full_volume=False,
            )
        self.assertFalse(result["full_volume_verified"])
        deep.assert_not_called()

    def test_full_volume_mode_requires_both_explicit_volumes(self) -> None:
        with self.assertRaisesRegex(
            release_verify.ReleaseVerifyError, "--source-volume is required"
        ):
            release_verify.verify(ROOT, REPORT, full_volume=True)

    def test_registered_shell_is_metadata_only(self) -> None:
        shell = (ROOT / "tools/validate_apf_uniform_selector_mod_release.sh").read_text()
        self.assertIn("--metadata-only", shell)
        self.assertNotIn("tests.test_apf_uniform_selector_xenia_runtime_verify", shell)
        self.assertNotIn("apf-selector-release-validation-unused", shell)


if __name__ == "__main__":
    unittest.main()
