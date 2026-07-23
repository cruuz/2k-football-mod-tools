from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import static_topology_conformance_spec as spec_tool  # noqa: E402


class StaticTopologyConformanceSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = json.loads(spec_tool.DEFAULT_SPEC.read_text(encoding="utf-8"))

    def test_checked_json_is_canonical_and_contains_no_retail_geometry(self) -> None:
        self.assertEqual(self.spec, spec_tool.canonical_spec())
        self.assertEqual(spec_tool.DEFAULT_SPEC.read_bytes(), spec_tool.canonical_bytes())
        policy = self.spec["data_policy"]
        for key in (
            "contains_retail_vertex_values",
            "contains_retail_index_values",
            "contains_retail_command_payload",
            "contains_retail_geometry",
        ):
            self.assertFalse(policy[key])

    def test_nfl_native_budget_and_first_profile_are_exact(self) -> None:
        nfl = self.spec["titles"]["nfl2k5_xbox"]
        profile = nfl["selected_first_topology_profile"]
        self.assertEqual(
            profile["status"],
            "offline_writer_and_independent_verifier_implemented_runtime_unproved",
        )
        self.assertEqual(
            profile["profile_contract_reference"],
            spec_tool.NFL_GROUP36_PROFILE_CONTRACT_REFERENCE,
        )
        self.assertEqual(
            profile["immutable_profile_contract"],
            spec_tool.NFL_GROUP36_PROFILE_CONTRACT,
        )
        self.assertEqual(
            spec_tool.hashlib.sha256(
                spec_tool.canonical_profile_contract_bytes(profile["immutable_profile_contract"])
            ).hexdigest(),
            profile["profile_contract_reference"]["fingerprint"],
        )
        self.assertEqual(profile["target"]["primary_command_word_count"], 7)
        self.assertEqual(profile["target"]["push_size_bytes"], 28)
        self.assertEqual(spec_tool.nfl_element16_command_words(4), 7)
        self.assertEqual(spec_tool.nfl_element32_command_words(4), 9)
        self.assertIn("each below vertex_count", profile["authoring_input"])
        self.assertIn("duplicates are structurally encodable", profile["authoring_input"])
        self.assertIn("permutation", profile["degenerate_policy"]["first_non_degenerate_witness"])
        self.assertTrue(any("four u16 index halfwords" in item for item in profile["allowed_decoded_changes"]))
        self.assertTrue(any("all seven command" in item for item in profile["must_remain_exact"]))

    def test_apf_profile_has_bounded_offline_writer_and_independent_verifier(self) -> None:
        apf = self.spec["titles"]["apf2k8_xbox360"]
        profile = apf["analogous_same_footprint_profile"]
        self.assertEqual(
            profile["status"],
            "offline_writer_and_independent_verifier_implemented_runtime_unproved",
        )
        self.assertEqual(profile["target"]["index_component_bits"], 16)
        self.assertEqual(profile["target"]["index_count"], 4)
        self.assertEqual(profile["target"]["index_size_bytes"], 8)
        self.assertEqual(spec_tool.apf_index_payload_bytes(16, 4), 8)
        self.assertIn("permutation", profile["admission"])
        self.assertTrue(profile["draw_invariants"]["draw_record_exact"])
        self.assertEqual(profile["proof"]["changed_decoded_bytes"], 2)
        self.assertEqual(profile["proof"]["allocation_slack_after_bytes"], 1_403)
        self.assertTrue(profile["proof"]["no_op_complete_1a_byte_identical"])
        self.assertFalse(profile["proof"]["no_op_recompressed"])
        self.assertIn("all 47,112", apf["read_status"]["draw_record_semantics"])

    def test_fixed_budget_future_profiles_do_not_invent_attribute_semantics(self) -> None:
        nfl = self.spec["titles"]["nfl2k5_xbox"]["fixed_budget_subset_profile_gap"]
        apf = self.spec["titles"]["apf2k8_xbox360"]["fixed_budget_subset_profile_gap"]
        self.assertIn("source-derived vertex-count reduction", nfl["would_enable"])
        self.assertEqual(
            nfl["status"],
            "upper_deck_target_contract_and_count_only_fixed_span_probes_proved_writer_not_implemented",
        )
        probe = nfl["selected_probe_boundary"]
        self.assertEqual(probe["target_id"], "nfl2k5/stadium/o3280/c5/s1")
        self.assertEqual(probe["changed_vertex_counts"], [4, 8])
        self.assertEqual(probe["active_stream_strides"], [12, 10])
        self.assertEqual(probe["coupled_changed_bytes_for_prefix_shrink"], [30540, 69887])
        self.assertFalse(probe["archive_writer_implemented"])
        self.assertFalse(probe["runtime_proved"])
        self.assertTrue(any("complete-record prefix remap" in item for item in nfl["still_required"]))
        self.assertEqual(apf["status"], "same_footprint_closed_changed_count_unimplemented")
        self.assertTrue(any("draw field" in item for item in apf["still_required"]))
        shared = self.spec["shared_conformance_contract"]
        self.assertIn("source-vertex subset", shared["external_mesh_admission"]["attribute_rule"])
        self.assertTrue(any("compression savings" in item for item in shared["allocation_ledger"]["rules"]))
        self.assertEqual(shared["bounds_and_culling"]["current_status"], "not recovered for either title")

    def test_noop_changed_and_mandatory_rejection_contracts_are_complete(self) -> None:
        shared = self.spec["shared_conformance_contract"]
        self.assertTrue(any("verbatim" in item for item in shared["no_op_verification"]))
        self.assertTrue(any("complete copied pack/volume" in item for item in shared["no_op_verification"]))
        self.assertTrue(any(
            "before decoded-object mutation or container recompression" in item
            for item in shared["no_op_verification"]
        ))
        self.assertTrue(any("exact decoded changed-byte set" in item for item in shared["changed_output_verification"]))
        self.assertTrue(any("independently decompress" in item for item in shared["changed_output_verification"]))
        self.assertTrue(any("recompression overflow" in item for item in shared["mandatory_rejections"]))
        self.assertTrue(any("pointer alias" in item for item in shared["mandatory_rejections"]))

    def test_all_unproved_claims_remain_false(self) -> None:
        flags = self.spec["claim_flags"]
        self.assertTrue(flags["requirements_specified"])
        self.assertTrue(flags["nfl_same_footprint_profile_selected"])
        proved = {
            "requirements_specified",
            "nfl_same_footprint_profile_selected",
            "nfl_topology_writer_implemented",
            "nfl_selected_profile_offline_writeback_proved",
            "nfl_changed_count_target_contract_probed",
            "apf_topology_writer_implemented",
        }
        for key, value in flags.items():
            if key not in proved:
                self.assertFalse(value, key)
            else:
                self.assertTrue(value, key)

    def test_geometry_implementation_evidence_is_hash_pinned_and_nongeometric(self) -> None:
        evidence = self.spec["source_evidence"]
        for key in (
            "nfl_group36_geometry_writer",
            "nfl_group36_geometry_independent_verifier",
            "nfl_group36_geometry_recipe_schema",
            "nfl_group36_geometry_nonretail_recipe",
            "nfl_group36_geometry_roundtrip_report",
            "nfl_upper_deck_changed_count_boundary",
            "apf_draw_topology_spec",
            "apf_draw_topology_corpus",
            "apf_topology_writer",
            "apf_topology_independent_verifier",
            "apf_topology_recipe_schema",
            "apf_topology_public_nonretail_recipe",
            "apf_topology_roundtrip_report",
        ):
            self.assertIn(key, evidence)
            self.assertEqual(len(evidence[key]["sha256"]), 64)
        report = json.loads((
            ROOT / evidence["nfl_group36_geometry_roundtrip_report"]["path"]
        ).read_text(encoding="utf-8"))
        self.assertEqual(
            report["profile_contract"],
            spec_tool.NFL_GROUP36_PROFILE_CONTRACT_REFERENCE,
        )
        self.assertTrue(
            report["claims"]["offline_same_footprint_native_quad_write_back_proved"]
        )
        self.assertFalse(report["claims"]["runtime_visibility_proved"])
        self.assertFalse(report["data_policy"]["contains_retail_geometry"])
        self.assertEqual(
            report["controlled_nonretail_changed_witness"]["decoded_changed_byte_count"],
            50,
        )
        changed_count = json.loads((
            ROOT / evidence["nfl_upper_deck_changed_count_boundary"]["path"]
        ).read_text(encoding="utf-8"))
        self.assertEqual(
            changed_count["topology_contract"]["changed_vertex_counts"], [4, 8]
        )
        self.assertFalse(
            changed_count["claim_flags"]["changed_count_archive_writer_implemented"]
        )
        self.assertFalse(changed_count["claim_flags"]["runtime_visibility_proved"])
        apf_topology = json.loads((
            ROOT / evidence["apf_topology_roundtrip_report"]["path"]
        ).read_text(encoding="utf-8"))
        self.assertTrue(
            apf_topology["claim_flags"]["offline_byte_level_roundtrip_proved"]
        )
        self.assertFalse(apf_topology["claim_flags"]["runtime_proved"])
        self.assertEqual(
            apf_topology["changed_nonretail_permutation"]["changed_decoded_dram_bytes"],
            2,
        )
        self.assertTrue(apf_topology["preservation"]["draw_record_exact"])

    def test_pointer_and_budget_helpers_fail_closed(self) -> None:
        for count in (-1, 0, 1, 3):
            with self.assertRaises(spec_tool.SpecError):
                spec_tool.nfl_element16_command_words(count)
        with self.assertRaises(spec_tool.SpecError):
            spec_tool.nfl_element32_command_words(0)
        for bits, count in ((8, 4), (64, 4), (16, 0)):
            with self.assertRaises(spec_tool.SpecError):
                spec_tool.apf_index_payload_bytes(bits, count)
        self.assertIsNone(spec_tool.relative_target(0x100, 0))
        encoded = spec_tool.relative_value(0x100, 0x234)
        self.assertEqual(spec_tool.relative_target(0x100, encoded), 0x234)

    def test_mutated_claim_profile_or_budget_is_rejected(self) -> None:
        mutations = (
            lambda data: data["claim_flags"].__setitem__("nfl_topology_writer_implemented", False),
            lambda data: data["data_policy"].__setitem__("contains_retail_index_values", True),
            lambda data: data["titles"]["nfl2k5_xbox"]["selected_first_topology_profile"]["target"].__setitem__("primary_command_word_count", 8),
            lambda data: data["titles"]["apf2k8_xbox360"]["analogous_same_footprint_profile"]["proof"].__setitem__("changed_decoded_bytes", 3),
        )
        for mutate in mutations:
            changed = copy.deepcopy(self.spec)
            mutate(changed)
            with self.assertRaises(spec_tool.SpecError):
                spec_tool.validate_spec(changed)


if __name__ == "__main__":
    unittest.main()
