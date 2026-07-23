from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_upper_deck_changed_count_spec as boundary  # noqa: E402


class NflUpperDeckChangedCountSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(boundary.DEFAULT_SPEC.read_text(encoding="utf-8"))

    def test_checked_spec_is_private_and_does_not_claim_a_writer_or_runtime(self) -> None:
        self.assertEqual(self.data["schema"], boundary.SCHEMA)
        policy = self.data["data_policy"]
        for key in (
            "contains_retail_vertex_values",
            "contains_retail_attribute_values",
            "contains_retail_index_values",
            "contains_retail_command_payload",
            "contains_modified_archive_bytes",
        ):
            self.assertFalse(policy[key], key)
        flags = self.data["claim_flags"]
        self.assertTrue(flags["target_structure_closed_for_prefix_shrink_probe"])
        self.assertTrue(flags["two_count_bytes_and_fixed_span_fit_probed"])
        self.assertTrue(flags["source_subset_record_copy_algorithm_specified"])
        for key in (
            "changed_count_archive_writer_implemented",
            "independent_changed_count_verifier_implemented",
            "arbitrary_external_vertex_authoring_proved",
            "bounds_or_culling_serializer_proved",
            "collision_or_lod_ownership_proved",
            "runtime_visibility_proved",
            "original_xbox_hardware_proved",
            "production_ready",
        ):
            self.assertFalse(flags[key], key)

    def test_selected_target_closes_every_count_stream_and_command_field(self) -> None:
        self.assertEqual(self.data["target_selection"]["target_id"], boundary.TARGET_ID)
        shape = self.data["shape_and_coupled_fields"]
        self.assertEqual(shape["source_vertex_count"], 12)
        self.assertEqual(shape["vertex_count_field"]["offset"], boundary.VERTEX_COUNT_FIELD)
        self.assertIn("partial", shape["vertex_count_field"]["consumer_closure"])
        self.assertEqual(shape["inactive_blend_pointer_alias"]["count"], 0)
        self.assertEqual(
            shape["inactive_blend_pointer_alias"]["pointer_target"],
            boundary.SUBMESH_OFFSET,
        )
        streams = self.data["vertex_record_contract"]["streams"]
        self.assertEqual([(row["stream_index"], row["stride_bytes"]) for row in streams], [(0, 12), (1, 10)])
        self.assertEqual([row["record_bytes_covered_by_declarations"] for row in streams], [12, 10])
        topology = self.data["topology_contract"]
        self.assertEqual(topology["primary_word_count"], 6)
        self.assertEqual(topology["secondary_word_count"], 0)
        self.assertEqual(topology["only_mutable_topology_bits"]["count_byte_offset"], boundary.DRAW_COUNT_BYTE_OFFSET)
        self.assertIn("no command is added or removed", topology["command_capacity_result"])

    def test_future_recipe_schema_cannot_admit_external_attributes_or_wrong_lengths(self) -> None:
        contract = self.data["recipe_contract"]
        self.assertEqual(contract["admitted_changed_counts"], [4, 8])
        self.assertEqual(contract["source_vertex_id_domain"], [0, 11])
        self.assertTrue(contract["source_vertex_ids_must_be_unique"])
        self.assertFalse(contract["external_positions_or_attributes_admitted"])
        self.assertFalse(contract["writer_implemented"])
        schema = json.loads((ROOT / contract["path"]).read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["new_vertex_count"]["enum"], [4, 8]
        )
        self.assertTrue(schema["properties"]["source_vertex_ids"]["uniqueItems"])
        self.assertEqual(
            [branch["properties"]["source_vertex_ids"]["minItems"] for branch in schema["oneOf"]],
            [4, 8],
        )
        self.assertNotIn("positions", schema["properties"])
        self.assertNotIn("attributes", schema["properties"])

    def test_draw_arrays_inverse_and_admissible_quad_count_derivation(self) -> None:
        self.assertEqual(boundary.admissible_quad_counts(), (4, 8, 12))
        for count in (1, 4, 8, 12, 256):
            encoded = boundary.encode_draw_arrays(0x1234, count)
            self.assertEqual(boundary.decode_draw_arrays(encoded), (0x1234, count))
        for count in (0, 257):
            with self.assertRaises(boundary.BoundaryError):
                boundary.encode_draw_arrays(0, count)
        with self.assertRaises(boundary.BoundaryError):
            boundary.encode_draw_arrays(0x1000000, 4)
        for source_count in (0, 257):
            with self.assertRaises(boundary.BoundaryError):
                boundary.admissible_quad_counts(source_count)

    def test_synthetic_whole_record_remap_preserves_the_physical_tail(self) -> None:
        source_count = 12
        stride = 3
        source = bytes(range(source_count * stride))
        subset = (7, 2, 10, 0)
        remapped = boundary.remap_stream_prefix(source, stride, source_count, subset)
        expected_prefix = b"".join(
            source[source_id * stride:(source_id + 1) * stride]
            for source_id in subset
        )
        self.assertEqual(remapped[:len(expected_prefix)], expected_prefix)
        self.assertEqual(remapped[len(expected_prefix):], source[len(expected_prefix):])
        self.assertEqual(source, bytes(range(source_count * stride)))

    def test_subset_contract_rejects_welding_escape_and_partial_quads(self) -> None:
        invalid = (
            (),
            (0, 1, 2),
            (0, 1, 2, 12),
            (0, 1, 1, 2),
            (0, 1, 2, True),
            tuple(range(9)),
        )
        for subset in invalid:
            with self.assertRaises(boundary.BoundaryError, msg=repr(subset)):
                boundary.validate_subset_ids(12, subset)
        with self.assertRaises(boundary.BoundaryError):
            boundary.remap_stream_prefix(bytes(35), 3, 12, (0, 1, 2, 3))

    def test_count_only_probes_change_exactly_two_bytes_and_fit_fixed_span(self) -> None:
        probes = self.data["prefix_shrink_probe"]["probes"]
        self.assertEqual([row["new_vertex_count"] for row in probes], [8, 4])
        for row in probes:
            self.assertEqual(row["changed_decoded_byte_count"], 2)
            self.assertEqual(
                row["changed_decoded_offsets"],
                [boundary.VERTEX_COUNT_FIELD, boundary.DRAW_COUNT_BYTE_OFFSET],
            )
            self.assertFalse(row["physical_stream_payloads_changed"])
            self.assertTrue(row["outside_two_count_bytes_bit_exact"])
            self.assertEqual(row["reparsed_shape_vertex_count"], row["new_vertex_count"])
            self.assertEqual(row["reparsed_draw_vertex_count"], row["new_vertex_count"])
            self.assertEqual(row["reparsed_maximum_vertex_index"], row["new_vertex_count"] - 1)
            self.assertLessEqual(row["rebuilt_consumed_bytes"], row["retail_consumed_cap_bytes"])
            self.assertEqual(row["aligned_scratch_bytes"], 32)
            self.assertTrue(row["full_decode_exact"])
            self.assertTrue(row["fixed_final_tail_exact"])
            self.assertFalse(row["output_archive_published"])
            self.assertFalse(row["runtime_tested"])

    def test_alias_scan_retains_heuristic_limit_and_explains_nonowner_value(self) -> None:
        scan = self.data["interval_and_alias_ledger"]["aligned_raw_word_scan"]
        self.assertEqual(len(scan["stream0_candidates"]), 1)
        self.assertEqual(len(scan["stream1_candidates"]), 2)
        self.assertEqual(scan["stream1_candidates"][1]["field_offset"], 399120)
        self.assertIn("attribute_stream_1", scan["stream1_candidates"][1]["containing_payload_class"])
        self.assertIn("does not exclude", scan["proof_limit"])

    def test_validation_rejects_overclaim_or_changed_count_drift(self) -> None:
        boundary.validate_spec(self.data)
        changed = copy.deepcopy(self.data)
        changed["claim_flags"]["runtime_visibility_proved"] = True
        with self.assertRaises(boundary.BoundaryError):
            boundary.validate_spec(changed)
        changed = copy.deepcopy(self.data)
        changed["topology_contract"]["changed_vertex_counts"] = [8]
        with self.assertRaises(boundary.BoundaryError):
            boundary.validate_spec(changed)


if __name__ == "__main__":
    unittest.main()
