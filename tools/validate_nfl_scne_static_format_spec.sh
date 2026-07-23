#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SPEC='reports/specs/nfl2k5_xbox_static_scne.v1.json'
EXPECTED_SIZE=47126
EXPECTED_SHA256='d1e684a0b86c3a933355217174938cb95c5192eb2680c8b9698f7eb15ac39884'

test "$(stat -c %s "$SPEC")" = "$EXPECTED_SIZE"
test "$(sha256sum "$SPEC" | cut -d' ' -f1)" = "$EXPECTED_SHA256"

jq -e '
  .schema == "nfl2k5_xbox_static_scne_format/v1" and
  .contains_retail_geometry_or_pixel_bytes == false and
  (.scene_descriptor.top_level_tables | length) == 8 and
  .scene_descriptor.size == 84 and
  .shape_record.stride == 256 and
  .submesh_record.stride == 128 and
  (.vertex_declaration.formats | length) == 20 and
  .corpus_facts.scene_count == 4616 and
  .corpus_facts.shape_count == 54966 and
  .corpus_facts.submesh_count == 276642 and
  .same_count_position_write_boundary_v1.eligibility_corpus_count == 51679 and
  .claim_flags.complete_static_position_read_spec == true and
  .claim_flags.same_count_position_writer_implemented == false and
  .claim_flags.pinned_group36_float3_same_count_writer_implemented == true and
  .claim_flags.stadium_catalog_75_float3_dispatch_implemented == true and
  .claim_flags.general_eligibility_profile_writer_dispatch_implemented == false and
  .same_count_position_write_boundary_v1.implemented_group36_witness.shape_name == "group36" and
  .same_count_position_write_boundary_v1.implemented_group36_witness.no_op_whole_volume_bit_exact == true and
  .same_count_position_write_boundary_v1.implemented_stadium_catalog_v2.authorized_target_count == 75 and
  .same_count_position_write_boundary_v1.implemented_stadium_catalog_v2.second_target_name == "upper_deck" and
  .same_count_position_write_boundary_v1.implemented_stadium_catalog_v2.second_target_no_op_whole_volume_bit_exact == true and
  .claim_flags.topology_write_proved == false and
  .claim_flags.runtime_proved == false and
  .claim_flags.production_ready == false
' "$SPEC" >/dev/null

validation="$(python3 tools/nfl_scne_static_format_spec.py)"
test "$validation" = '{"general_writer_implemented": false, "group36_writer_implemented": true, "scenes": 4616, "schema": "nfl2k5_xbox_static_scne_format_spec_validation/v1", "shapes": 54966, "stadium_catalog_writer_implemented": true, "submeshes": 276642, "tables": 8, "vertex_formats": 20}'

python3 -m unittest tests.test_nfl_scne_static_format_spec >/dev/null

echo "NFL_SCNE_STATIC_FORMAT_SPEC_VALIDATION_PASS version=1 scenes=4616 shapes=54966 submeshes=276642 tables=8 formats=20 static_candidates=51679 group36_writer=true stadium_catalog_writer=true catalog_targets=75 general_writer=false retail_geometry=false runtime=false spec_sha256=$EXPECTED_SHA256"
