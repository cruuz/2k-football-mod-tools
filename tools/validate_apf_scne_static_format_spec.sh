#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SPEC='reports/specs/apf2k8_scne_static_serializer.v1.json'
EXPECTED_SIZE=75227
EXPECTED_SHA256='8c945740e987b1a27786b29858e46d6a99da65fa96abb019b7e1f28cc1f92b0c'

test "$(stat -c %s "$SPEC")" = "$EXPECTED_SIZE"
test "$(sha256sum "$SPEC" | cut -d' ' -f1)" = "$EXPECTED_SHA256"

jq -e '
  .schema == "apf2k8_scne_static_serializer/v1" and
  .spec_version == 1 and
  .data_policy.contains_retail_geometry == false and
  .data_policy.contains_retail_vertex_values == false and
  .data_policy.contains_retail_index_values == false and
  .corpus_proof.scne_resources == 1303 and
  .corpus_proof.mesh_nodes == 13006 and
  .corpus_proof.position_formats == {"float32x3":12416,"snorm16x4":365,"snorm10_10_10":225} and
  .corpus_proof.dram_only_scne == 504 and
  .corpus_proof.dram_vram_scne == 799 and
  .corpus_proof.scne_sram_part_count == 0 and
  .scne.system_part.minimum_header_bytes == 100 and
  .scne.mesh_node.size_bytes == 176 and
  .scne.hierarchy_table.header_size_bytes == 0 and
  .scne.hierarchy_table.byte_length_formula == "count * 0x30" and
  .scne.hierarchy_table.ordinary_record_size_bytes == 48 and
  .scne.hierarchy_table.terminal_rule == "all records, including the last, contain vector_a and vector_b" and
  (.scne.hierarchy_table.core_fields | map([.name,.offset_bytes])) == [["vector_a",0],["vector_b",16],["name",32],["name_crc32",36],["parent",40],["first_child",42],["next_sibling",44],["reserved",46]] and
  .scne.vertex_declaration.size_bytes == 64 and
  .scne.mesh_descriptor.stream_record.size_bytes == 24 and
  (.scne.position0_formats | map(.format_code_hex)) == ["0x002a23b9","0x001a215a","0x002a2187"] and
  (.scne.index_strip.supported_widths | map(.bits)) == [16,32] and
  (.write_profiles | keys) == ["outer14_inner8_node17_four_be16_strip/v1","same_count_position_only/v1"] and
  .claim_flags.same_count_position_profile_specified == true and
  .claim_flags.same_count_position_writer_implemented == false and
  .claim_flags.pinned_outer14_node17_same_count_position_writer_implemented == true and
  .claim_flags.pinned_outer14_node17_offline_structural_writeback_proved == true and
  .claim_flags.outer14_additional_static_target_catalog_proved == true and
  .claim_flags.outer14_catalog_all_77_targets_structurally_authorized == true and
  .claim_flags.outer14_catalog_same_count_position_dispatcher_implemented == true and
  .claim_flags.pinned_outer14_node3_representative_h7a_rebuild_fit_proved == true and
  .claim_flags.pinned_outer14_node3_writer_implemented == true and
  .claim_flags.pinned_outer14_node3_offline_structural_writeback_proved == true and
  .claim_flags.general_scne_same_count_position_dispatcher_implemented == false and
  .outer14_stadium_static_target_catalog.additional_target_count == 77 and
  .outer14_stadium_static_target_catalog.selected_second_target_handoff.node_index == 3 and
  .outer14_stadium_static_target_catalog.selected_second_target_handoff.draw_record_count == 3 and
  .outer14_stadium_static_target_catalog.selected_second_target_handoff.allocation_slack_after_bytes == 1367 and
  .outer14_stadium_static_target_catalog.selected_second_target_handoff.historical_catalog_generation_time_writer_complete == false and
  .outer14_stadium_static_target_catalog.selected_second_target_handoff.downstream_catalog_dispatcher_now_implemented == true and
  .outer14_stadium_static_target_catalog.selected_second_target_handoff.runtime_rigid_attachment_proved == false and
  .catalog_dispatcher_implementation_witness.changed_all_zero_node3.output_1a_sha256 == "cf8cd039e6ef3f078f193c1563bce76d3983372cd67b30a0b051487699378022" and
  .catalog_dispatcher_implementation_witness.changed_all_zero_node3.output_outer_sha256 == "23e15b372b7e3be49a2b0a475232c4f44b9c4de9d4a7a572e5e98a8df9d7af9e" and
  .catalog_dispatcher_implementation_witness.changed_all_zero_node3.changed_decoded_block0_bytes == 284 and
  .catalog_dispatcher_implementation_witness.changed_all_zero_node3.authorized_lane_bytes == 288 and
  .catalog_dispatcher_implementation_witness.changed_all_zero_node3.allocation_slack_after_bytes == 21907 and
  .catalog_dispatcher_implementation_witness.preservation.independent_verifier_imports_any_position_writer == false and
  .catalog_dispatcher_implementation_witness.retail_or_retail_derived_recipe_coordinates_committed == false and
  .pinned_implementation_witness.retail_or_retail_derived_recipe_coordinates_committed == false and
  .pinned_implementation_witness.changed_plus_1_2_3.output_1a_sha256 == "6f275ccb780acfee0cba9cd59c38e4bb2aedb18d01dec7030d61546441026b40" and
  .pinned_implementation_witness.changed_plus_1_2_3.output_outer_sha256 == "89ec32ee6da2a73f494667c01aa8ea9968c49c97317ec85d3c0342c84eb632fa" and
  .scne.draw_record.size_bytes == 48 and
  (.scne.draw_record.fields | length) == 12 and
  .claim_flags.changed_topology_writer_proved == true and
  .claim_flags.pinned_outer14_node17_same_footprint_topology_writer_implemented == true and
  .claim_flags.pinned_outer14_node17_same_footprint_topology_offline_roundtrip_proved == true and
  .claim_flags.general_scne_topology_dispatcher_implemented == false and
  .pinned_same_footprint_topology_implementation_witness.changed_nonretail_permutation.changed_decoded_dram_bytes == 2 and
  .pinned_same_footprint_topology_implementation_witness.changed_nonretail_permutation.allocation_slack_after_bytes == 1403 and
  .pinned_same_footprint_topology_implementation_witness.no_op.complete_1a_byte_identical == true and
  .pinned_same_footprint_topology_implementation_witness.no_op.h7a_recompressed == false and
  .claim_flags.skinned_mesh_writer_proved == false and
  .claim_flags.emulator_runtime_visibility_proved == false and
  .claim_flags.xbox_360_hardware_acceptance_proved == false and
  .claim_flags.production_mesh_importer_proved == false
' "$SPEC" >/dev/null

validation="$(python3 tools/apf_scne_static_format_spec.py)"
test "$validation" = "{\"catalog_dispatcher_implemented\": true, \"catalog_targets\": 77, \"mesh_nodes\": 13006, \"node3_rebuild_fit\": true, \"node3_writer_implemented\": true, \"pinned_writer_implemented\": true, \"position_formats\": 3, \"retail_geometry\": false, \"runtime_proved\": false, \"schema\": \"apf2k8_scne_static_serializer_validation/v1\", \"scne_resources\": 1303, \"spec_sha256\": \"$EXPECTED_SHA256\", \"topology_allocation_slack_after\": 1403, \"topology_changed_decoded_bytes\": 2, \"topology_writer_implemented\": true, \"write_profiles\": 2, \"writer_implemented\": false}"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
python3 tools/apf_scne_static_format_spec.py --generate "$tmp" >/dev/null
cmp -s "$SPEC" "$tmp"

python3 -m unittest tests.test_apf_scne_static_format_spec >/dev/null

echo "APF_SCNE_STATIC_FORMAT_SPEC_VALIDATION_PASS schema=v1 scne=1303 nodes=13006 position_formats=3 iff=true h7a=true write_profiles=2 pinned_writer=true catalog_targets=77 catalog_dispatcher=true node3_writer=true node3_fit=true general_scne_writer=false topology=true topology_changed_bytes=2 topology_slack=1403 general_topology=false runtime=false hardware=false production=false retail_geometry=false tests=9 sha256=$EXPECTED_SHA256"
