#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SPEC='reports/specs/2k_static_topology_conformance_requirements.v1.json'
EXPECTED_SIZE=41139
EXPECTED_SHA256='9412a862689ba2bddca3c934df1345c218c5a75080793b6bb1c92330132a49cd'

test "$(stat -c %s "$SPEC")" = "$EXPECTED_SIZE"
test "$(sha256sum "$SPEC" | cut -d' ' -f1)" = "$EXPECTED_SHA256"

jq -e '
  .schema == "2k_static_topology_conformance_requirements/v1" and
  .data_policy.contains_retail_vertex_values == false and
  .data_policy.contains_retail_index_values == false and
  .data_policy.contains_retail_command_payload == false and
  .data_policy.contains_retail_geometry == false and
  .first_profile_selection.selected == "nfl2k5_group36_same_footprint_quad_index_replace/v1" and
  .first_profile_selection.selection_is_implementation_claim == true and
  .first_profile_selection.selection_is_runtime_claim == false and
  .titles.nfl2k5_xbox.selected_first_topology_profile.status == "offline_writer_and_independent_verifier_implemented_runtime_unproved" and
  .titles.nfl2k5_xbox.selected_first_topology_profile.profile_contract_reference.fingerprint == "668cfc91f6ff398e23a649a695dec950ad8e2529f32a772d65bd8861a447e284" and
  .titles.nfl2k5_xbox.selected_first_topology_profile.target.primary_command_word_count == 7 and
  .titles.nfl2k5_xbox.selected_first_topology_profile.target.push_size_bytes == 28 and
  (.titles.nfl2k5_xbox.selected_first_topology_profile.authoring_input | contains("duplicates are structurally encodable")) and
  (.titles.nfl2k5_xbox.selected_first_topology_profile.degenerate_policy.first_non_degenerate_witness | contains("permutation")) and
  .titles.nfl2k5_xbox.fixed_budget_subset_profile_gap.status == "upper_deck_target_contract_and_count_only_fixed_span_probes_proved_writer_not_implemented" and
  .titles.nfl2k5_xbox.fixed_budget_subset_profile_gap.selected_probe_boundary.target_id == "nfl2k5/stadium/o3280/c5/s1" and
  .titles.nfl2k5_xbox.fixed_budget_subset_profile_gap.selected_probe_boundary.changed_vertex_counts == [4,8] and
  .titles.nfl2k5_xbox.fixed_budget_subset_profile_gap.selected_probe_boundary.coupled_changed_bytes_for_prefix_shrink == [30540,69887] and
  .titles.nfl2k5_xbox.fixed_budget_subset_profile_gap.selected_probe_boundary.archive_writer_implemented == false and
  .titles.nfl2k5_xbox.fixed_budget_subset_profile_gap.selected_probe_boundary.runtime_proved == false and
  .titles.apf2k8_xbox360.analogous_same_footprint_profile.status == "offline_writer_and_independent_verifier_implemented_runtime_unproved" and
  .titles.apf2k8_xbox360.analogous_same_footprint_profile.target.index_size_bytes == 8 and
  (.titles.apf2k8_xbox360.analogous_same_footprint_profile.admission | contains("permutation")) and
  .titles.apf2k8_xbox360.analogous_same_footprint_profile.draw_invariants.draw_record_exact == true and
  .titles.apf2k8_xbox360.analogous_same_footprint_profile.proof.changed_decoded_bytes == 2 and
  .titles.apf2k8_xbox360.analogous_same_footprint_profile.proof.allocation_slack_after_bytes == 1403 and
  .titles.apf2k8_xbox360.analogous_same_footprint_profile.proof.no_op_complete_1a_byte_identical == true and
  .titles.apf2k8_xbox360.analogous_same_footprint_profile.proof.no_op_recompressed == false and
  (.titles.apf2k8_xbox360.read_status.draw_record_semantics | contains("all 47,112")) and
  (.gap_matrix | length) == 8 and
  .claim_flags.requirements_specified == true and
  .claim_flags.nfl_same_footprint_profile_selected == true and
  .claim_flags.nfl_topology_writer_implemented == true and
  .claim_flags.nfl_selected_profile_offline_writeback_proved == true and
  .claim_flags.nfl_changed_count_target_contract_probed == true and
  .claim_flags.apf_topology_writer_implemented == true and
  .claim_flags.changed_vertex_count_writer_implemented == false and
  .claim_flags.automatic_decimator_implemented == false and
  .claim_flags.edited_gltf_importer_implemented == false and
  .claim_flags.bounds_culling_proved == false and
  .claim_flags.runtime_proved == false and
  .claim_flags.hardware_proved == false and
  .claim_flags.production_ready == false
' "$SPEC" >/dev/null

validation="$(python3 tools/static_topology_conformance_spec.py)"
test "$validation" = '{"apf_index_bytes": 8, "apf_topology_writer_implemented": true, "changed_count_target_probed": true, "changed_count_writer_implemented": false, "gap_rows": 8, "nfl_command_words": 7, "runtime_proved": false, "schema": "2k_static_topology_conformance_validation/v1", "selected_profile": "nfl2k5_group36_same_footprint_quad_index_replace/v1", "topology_writer_implemented": true}'

python3 -m unittest tests.test_static_topology_conformance_spec >/dev/null

echo "STATIC_TOPOLOGY_CONFORMANCE_SPEC_VALIDATION_PASS version=1 nfl_profile=group36_quad_index_replace nfl_words=7 apf_profile=node17_four_be16_strip apf_index_bytes=8 apf_changed_bytes=2 apf_slack=1403 changed_count_target=upper_deck changed_counts=4,8 changed_count_writer=false gaps=8 topology_writers=true runtime=false hardware=false production=false retail_geometry=false spec_sha256=$EXPECTED_SHA256"
