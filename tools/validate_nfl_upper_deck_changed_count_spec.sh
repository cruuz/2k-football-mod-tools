#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SPEC='reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json'
TOOL='tools/nfl_upper_deck_changed_count_spec.py'
INDEX='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
VOLUME='extracted/ESPN NFL 2K5 (USA)/vc_53450030/9'

EXPECTED_SPEC_SIZE=25285
EXPECTED_SPEC_SHA256='54e6d20dcf9c525a5248d94b4f45516425f0e69702df31dfd93fc351efd43eab'
EXPECTED_TOOL_SIZE=46226
EXPECTED_TOOL_SHA256='92d492a82f7090a31bbdc1e6d15ad0dc53ab07cea398d185517093a483a1937c'
EXPECTED_INDEX_SHA256='34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d'
EXPECTED_VOLUME_SHA256='779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a'

test "$(stat -c %s "$SPEC")" = "$EXPECTED_SPEC_SIZE"
test "$(sha256sum "$SPEC" | cut -d' ' -f1)" = "$EXPECTED_SPEC_SHA256"
test "$(stat -c %s "$TOOL")" = "$EXPECTED_TOOL_SIZE"
test "$(sha256sum "$TOOL" | cut -d' ' -f1)" = "$EXPECTED_TOOL_SHA256"
test "$(sha256sum "$INDEX" | cut -d' ' -f1)" = "$EXPECTED_INDEX_SHA256"
test "$(sha256sum "$VOLUME" | cut -d' ' -f1)" = "$EXPECTED_VOLUME_SHA256"

jq -e '
  .schema == "nfl2k5_upper_deck_changed_count_boundary/v1" and
  .data_policy.contains_retail_vertex_values == false and
  .data_policy.contains_retail_attribute_values == false and
  .data_policy.contains_retail_index_values == false and
  .data_policy.contains_retail_command_payload == false and
  .data_policy.contains_modified_archive_bytes == false and
  .target_selection.target_id == "nfl2k5/stadium/o3280/c5/s1" and
  .target_selection.selection_is_writer_claim == false and
  .target_selection.selection_is_runtime_claim == false and
  .recipe_contract.schema == "nfl2k5_upper_deck_source_subset_recipe/v1" and
  .recipe_contract.admitted_changed_counts == [4,8] and
  .recipe_contract.source_vertex_ids_must_be_unique == true and
  .recipe_contract.external_positions_or_attributes_admitted == false and
  .recipe_contract.writer_implemented == false and
  .shape_and_coupled_fields.source_vertex_count == 12 and
  .shape_and_coupled_fields.vertex_count_field.offset == 30540 and
  .shape_and_coupled_fields.inactive_blend_pointer_alias.count == 0 and
  .shape_and_coupled_fields.inactive_blend_pointer_alias.pointer_target == 69744 and
  (.vertex_record_contract.streams | map([.stream_index,.stride_bytes])) == [[0,12],[1,10]] and
  .topology_contract.admissible_vertex_counts == [4,8,12] and
  .topology_contract.changed_vertex_counts == [4,8] and
  .topology_contract.primary_word_count == 6 and
  .topology_contract.secondary_word_count == 0 and
  .topology_contract.only_mutable_topology_bits.count_byte_offset == 69887 and
  (.prefix_shrink_probe.probes | map(.new_vertex_count)) == [8,4] and
  (.prefix_shrink_probe.probes | all(
    .changed_decoded_byte_count == 2 and
    .changed_decoded_offsets == [30540,69887] and
    .physical_stream_payloads_changed == false and
    .outside_two_count_bytes_bit_exact == true and
    .rebuilt_consumed_bytes <= .retail_consumed_cap_bytes and
    .aligned_scratch_bytes == 32 and
    .full_decode_exact == true and
    .fixed_final_tail_exact == true and
    .output_archive_published == false and
    .runtime_tested == false
  )) and
  .claim_flags.target_structure_closed_for_prefix_shrink_probe == true and
  .claim_flags.two_count_bytes_and_fixed_span_fit_probed == true and
  .claim_flags.source_subset_record_copy_algorithm_specified == true and
  .claim_flags.changed_count_archive_writer_implemented == false and
  .claim_flags.independent_changed_count_verifier_implemented == false and
  .claim_flags.bounds_or_culling_serializer_proved == false and
  .claim_flags.runtime_visibility_proved == false and
  .claim_flags.production_ready == false and
  (.evidence_classification.blockers | length) >= 5
' "$SPEC" >/dev/null

validation="$(python3 "$TOOL" --index "$INDEX")"
test "$validation" = '{"changed_bytes_per_prefix_probe": 2, "changed_counts": [4, 8], "push_words": 6, "runtime_proved": false, "schema": "nfl2k5_upper_deck_changed_count_boundary_validation/v1", "source_vertices": 12, "streams": 2, "target": "nfl2k5/stadium/o3280/c5/s1", "writer_implemented": false}'

python3 -m unittest tests.test_nfl_upper_deck_changed_count_spec >/dev/null

test "$(sha256sum "$INDEX" | cut -d' ' -f1)" = "$EXPECTED_INDEX_SHA256"
test "$(sha256sum "$VOLUME" | cut -d' ' -f1)" = "$EXPECTED_VOLUME_SHA256"

echo "NFL_UPPER_DECK_CHANGED_COUNT_SPEC_VALIDATION_PASS target=upper_deck source_vertices=12 changed_counts=4,8 streams=2 push_words=6 changed_bytes=2 fit_8=908863/908864 fit_4=908862/908864 writer=false runtime=false retail_geometry=false spec_sha256=$EXPECTED_SPEC_SHA256"
