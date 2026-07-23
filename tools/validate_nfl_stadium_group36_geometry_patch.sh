#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

INDEX='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
PACK='extracted/ESPN NFL 2K5 (USA)/vc_53450030/9'
SCHEMA='reports/specs/nfl2k5_group36_same_footprint_geometry_recipe.schema.json'
SAMPLE='reports/asset_samples/nfl_scne/stadium_group36_zero_positions_permuted_quad_recipe.json'
REPORT='reports/assets/nfl_stadium_group36_same_footprint_geometry_roundtrip.json'
TOPOLOGY_SPEC='reports/specs/2k_static_topology_conformance_requirements.v1.json'

check_pin() {
  local path="$1" size="$2" digest="$3"
  test "$(stat -c %s "$path")" = "$size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$digest"
}

check_pin "$SCHEMA" 2691 98a3467b4ece8876f9e613a46aedbfbf5e98ed7d9ae6d913a637276d65051802
check_pin "$SAMPLE" 1786 e940739abb9f901607ce2b3c35a629b2cf3ccbda0ba11c4d8963fccadad078fe
check_pin "$REPORT" 5488 75e20ced325aa09f75ba0831a28eaee1436ae31b669985396f967d047d0aff20
check_pin "$TOPOLOGY_SPEC" 37020 c25d577be8dc81fe1e0f569ed99ea9df03401663de5abc7e677ed471d211f882

jq -e '
  .schema == "nfl2k5_group36_same_footprint_geometry_roundtrip/v1" and
  .data_policy.contains_retail_geometry == false and
  .data_policy.contains_retail_vertex_values == false and
  .data_policy.contains_retail_index_values == false and
  .profile_contract.fingerprint == "668cfc91f6ff398e23a649a695dec950ad8e2529f32a772d65bd8861a447e284" and
  .target.vertex_count == 4 and
  .target.index_count == 4 and
  .target.primary_command_word_count == 7 and
  .no_op_witness.complete_volume_9_byte_identical == true and
  .controlled_nonretail_changed_witness.decoded_changed_byte_count == 50 and
  .controlled_nonretail_changed_witness.rebuilt_consumed_bytes == 908830 and
  .controlled_nonretail_changed_witness.zero_gap_bytes == 34 and
  .controlled_nonretail_changed_witness.scratch_bytes == 64 and
  .controlled_nonretail_changed_witness.indices_are_permutation == true and
  .controlled_nonretail_changed_witness.nondegenerate_triangle_count == 2 and
  .controlled_nonretail_changed_witness.outside_authorized_geometry_bit_exact == true and
  .refusal_witnesses.topology_only_retail_position_permutation_vc_lz_overflow_refused == true and
  .refusal_witnesses.topology_only_permutation_output_artifact_created == false and
  .refusal_witnesses.staged_volume_symlink_redirection_refused_without_victim_mutation == true and
  .claims.offline_same_footprint_native_quad_write_back_proved == true and
  .claims.changed_vertex_or_index_count_write_back == false and
  .claims.runtime_visibility_proved == false and
  .claims.original_xbox_hardware_proved == false and
  .claims.automatic_decimator_implemented == false and
  .claims.production_mesh_importer == false
' "$REPORT" >/dev/null

python3 -m unittest tests.test_nfl_stadium_group36_geometry_patch >/dev/null
bash tools/validate_static_topology_conformance_spec.sh >/dev/null

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

index_before="$(sha256sum "$INDEX" | cut -d' ' -f1)"
pack_before="$(sha256sum "$PACK" | cut -d' ' -f1)"
test "$index_before" = 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
test "$pack_before" = 779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a

PYTHONPATH=tools python3 tools/nfl_stadium_group36_geometry_proof_recipes.py \
  --index "$INDEX" --mode no-op --output "$tmp/noop.json" >/dev/null
PYTHONPATH=tools python3 tools/nfl_stadium_group36_geometry_proof_recipes.py \
  --index "$INDEX" --mode topology-only-permutation --output "$tmp/overflow.json" >/dev/null
test "$(sha256sum "$tmp/noop.json" | cut -d' ' -f1)" = c653061381e35e7eab13a6943e7a1109dedc2c8107f942bcae76ba1e738d70ed
test "$(sha256sum "$tmp/overflow.json" | cut -d' ' -f1)" = 86f9ee5e6f8a179ed5551892a22870f3c29001d02f236f789fa9dbd6b6644ede

PYTHONPATH=tools python3 tools/nfl_stadium_group36_geometry_patch.py \
  --index "$INDEX" --recipe "$tmp/noop.json" --output-dir "$tmp/noop" >/dev/null
test "$(find "$tmp/noop" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')" = '9 manifest.json '
test "$(sha256sum "$tmp/noop/9" | cut -d' ' -f1)" = 779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a
test "$(sha256sum "$tmp/noop/manifest.json" | cut -d' ' -f1)" = 67db24b8400b38479d3c5a7b58df7442cc367609654f44303b410a192f12c67d
noop_verify="$(PYTHONPATH=tools python3 tools/nfl_stadium_group36_geometry_verify.py \
  --index "$INDEX" --recipe "$tmp/noop.json" --output-dir "$tmp/noop")"
jq -e '
  .mode == "no_op" and .decoded_changed_byte_count == 0 and
  .output_volume_sha256 == "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a" and
  .outside_authorized_geometry_bit_exact == true and .fixed_tail_exact == true and
  .runtime_proved == false and .production_ready == false
' <<<"$noop_verify" >/dev/null

PYTHONPATH=tools python3 tools/nfl_stadium_group36_geometry_patch.py \
  --index "$INDEX" --recipe "$SAMPLE" --output-dir "$tmp/changed" >/dev/null
test "$(sha256sum "$tmp/changed/9" | cut -d' ' -f1)" = 6bc202ee8a01caaa02885c58810fe9add2dae7afd862793a6a479622d63770e4
test "$(sha256sum "$tmp/changed/manifest.json" | cut -d' ' -f1)" = c8033acaf39f032d69d05e0a3f4a2ea235f35867dd40b7450547df49fa7c7917
changed_verify="$(PYTHONPATH=tools python3 tools/nfl_stadium_group36_geometry_verify.py \
  --index "$INDEX" --recipe "$SAMPLE" --output-dir "$tmp/changed")"
jq -e '
  .mode == "patched" and .decoded_changed_byte_count == 50 and
  .consumed_bytes == 908830 and .zero_gap_bytes == 34 and .scratch_bytes == 64 and
  .indices_are_permutation == true and .unique_index_count == 4 and
  .nondegenerate_triangle_count == 2 and .degenerate_triangle_count == 0 and
  .outside_authorized_geometry_bit_exact == true and .outside_chunk_bit_exact == true and
  .source_unchanged == true and .runtime_proved == false and .production_ready == false
' <<<"$changed_verify" >/dev/null

if PYTHONPATH=tools python3 tools/nfl_stadium_group36_geometry_patch.py \
  --index "$INDEX" --recipe "$tmp/overflow.json" --output-dir "$tmp/overflow-output" \
  >"$tmp/overflow.stdout" 2>"$tmp/overflow.stderr"; then
  echo 'error: topology-only VC-LZ overflow unexpectedly succeeded' >&2
  exit 1
fi
test ! -e "$tmp/overflow-output"
grep -q 'same footprint does not imply compressed-container fit' "$tmp/overflow.stderr"

if PYTHONPATH=tools python3 tools/nfl_stadium_group36_geometry_patch.py \
  --index "$INDEX" --recipe "$SAMPLE" --output-dir "$tmp/changed" \
  >"$tmp/existing.stdout" 2>"$tmp/existing.stderr"; then
  echo 'error: existing output directory unexpectedly accepted' >&2
  exit 1
fi
grep -q 'refusing to overwrite existing output directory' "$tmp/existing.stderr"
test "$(sha256sum "$tmp/changed/9" | cut -d' ' -f1)" = 6bc202ee8a01caaa02885c58810fe9add2dae7afd862793a6a479622d63770e4

index_after="$(sha256sum "$INDEX" | cut -d' ' -f1)"
pack_after="$(sha256sum "$PACK" | cut -d' ' -f1)"
test "$index_after" = "$index_before"
test "$pack_after" = "$pack_before"

echo "NFL_GROUP36_GEOMETRY_PATCH_VALIDATION_PASS profile=668cfc91 vertices=4 indices=4 command_words=7 noop_exact=true noop_recompress=false changed_decoded=50 consumed=908830/908864 gap=34 scratch=64 nondegenerate=2 outside_authorized_exact=true fixed_tail=true topology_only_overflow_refused=true existing_output_refused=true source_unchanged=true independent_verify=true tests=10 runtime=false hardware=false production=false report_sha256=75e20ced325aa09f75ba0831a28eaee1436ae31b669985396f967d047d0aff20"
