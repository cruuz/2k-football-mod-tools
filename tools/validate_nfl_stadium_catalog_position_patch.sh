#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
pack='extracted/ESPN NFL 2K5 (USA)/vc_53450030/9'
catalog='reports/specs/nfl2k5_stadium_static_target_catalog.v1.json'
schema='reports/specs/nfl2k5_catalog_static_position_recipe.v2.schema.json'
recipe='reports/asset_samples/nfl_scne/stadium_upper_deck_nonretail_zero_recipe.v2.json'
roundtrip='reports/assets/nfl_stadium_catalog_position_patch_roundtrip.v2.json'
spec='reports/specs/nfl2k5_xbox_static_scne.v1.json'
doc='docs/research/nfl_stadium_catalog_position_writeback.md'
temporary=$(mktemp -d "$root/.nfl-catalog-position-validate.XXXXXX")
trap 'rm -rf "$temporary"' EXIT

for required in "$index" "$pack" "$catalog" "$schema" "$recipe" "$roundtrip" \
  "$spec" "$doc" tools/nfl_stadium_catalog_position_patch.py \
  tools/nfl_stadium_catalog_position_verify.py \
  tests/test_nfl_stadium_catalog_position_patch.py \
  tests/nfl_stadium_catalog_position_patch_test.py; do
  test -f "$required"
done

test "$(stat -c %s "$catalog")" = 858600
test "$(sha256sum "$catalog" | cut -d' ' -f1)" = \
  'f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa'
test "$(stat -c %s tools/nfl_stadium_catalog_position_patch.py)" = 29227
test "$(sha256sum tools/nfl_stadium_catalog_position_patch.py | cut -d' ' -f1)" = \
  'c43dcf39fec5c7bc542fe7c8ebf98abd7ab23491878dcf3b36295a45d6c01885'
test "$(stat -c %s tools/nfl_stadium_catalog_position_verify.py)" = 30504
test "$(sha256sum tools/nfl_stadium_catalog_position_verify.py | cut -d' ' -f1)" = \
  '05236caff5f518a8703ef9196621ac5d284f2c8a958e87253abdd700b5896cf1'
test "$(stat -c %s "$schema")" = 1399
test "$(sha256sum "$schema" | cut -d' ' -f1)" = \
  '6fd2213905d2333650581ace6d5bfd8b5381fe92dc070f2d8ef61179bae39920'
test "$(stat -c %s "$recipe")" = 751
test "$(sha256sum "$recipe" | cut -d' ' -f1)" = \
  'f8781df9ebb6af67f47be2024bf7992285423f7aa149a589cef5630e5e9b35a4'
test "$(stat -c %s "$roundtrip")" = 7150
test "$(sha256sum "$roundtrip" | cut -d' ' -f1)" = \
  '05ab26057b0ebd244a0a090d2268f1cac49b3b820269b410e38c5e6b89a6d9c3'
test "$(stat -c %s "$doc")" = 8327
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  '70814b7af841359ec638cce98ac934afa000f987cb05d6c7b07469523ffee7a1'
test "$(stat -c %s "$spec")" = 47126
test "$(sha256sum "$spec" | cut -d' ' -f1)" = \
  '5947b18a7f9fe4b4f6895ca4ea37e5aadd55edb5d365128f46561011fdf8a01e'

# The original one-target implementation stays byte-identical.
test "$(sha256sum tools/nfl_stadium_group36_position_patch.py | cut -d' ' -f1)" = \
  'd781d49a8adaa23941e5854f734d531b458d1da70c6725f5ad0f2c7c1f92e82b'
test "$(sha256sum tools/nfl_stadium_group36_position_verify.py | cut -d' ' -f1)" = \
  '626a54b109f604274311ce14576516a3f6dd3f583a4617f2420c741e76a6c8cc'

jq -e '
  .additionalProperties == false and
  .properties.catalog.properties.sha256.const == "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa" and
  .properties.schema.const == "nfl2k5_catalog_static_position_recipe/v2" and
  .properties.positions.maxItems == 1877 and
  (.description | contains("procedural loader"))
' "$schema" >/dev/null

jq -e '
  .schema == "nfl2k5_catalog_static_position_recipe/v2" and
  .target_id == "nfl2k5/stadium/o3280/c5/s1" and
  .catalog.sha256 == "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa" and
  (.positions | length) == 12 and
  all(.positions[]; . == [0,0,0])
' "$recipe" >/dev/null

jq -e '
  .schema == "nfl2k5_catalog_static_position_patch_roundtrip/v2" and
  .catalog.authorized_target_count == 75 and
  .source.retail_modified == false and
  .target.target_id == "nfl2k5/stadium/o3280/c5/s1" and
  .target.vertex_count == 12 and
  .target.mechanically_rigid_only == true and
  .target.runtime_ownership_proved == false and
  .no_op.mode == "no_op" and
  .no_op.output.volume_sha256 == "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a" and
  .no_op.output.pack_changed_byte_count == 0 and
  .no_op.compression.consumed_bytes == 908864 and
  .no_op.compression.scratch_bytes == 16 and
  .controlled_nonretail_all_zero_edit.mode == "patched" and
  .controlled_nonretail_all_zero_edit.output.volume_sha256 == "96c2d8dd4ed4f65df67157ad6a822878bcbd4eefc960135176cd8030c9f9b176" and
  .controlled_nonretail_all_zero_edit.decoded.output_sha256 == "b2d70bb82f95cffc30a43b82b7263f9d211737fec8ed47b9fd8408c2babfb5f1" and
  .controlled_nonretail_all_zero_edit.decoded.decoded_changed_byte_count == 144 and
  .controlled_nonretail_all_zero_edit.decoded.outside_position_bit_exact == true and
  .controlled_nonretail_all_zero_edit.compression.consumed_bytes == 908799 and
  .controlled_nonretail_all_zero_edit.compression.zero_gap_bytes == 65 and
  .controlled_nonretail_all_zero_edit.compression.minimum_alias_scratch_bytes == 66 and
  .controlled_nonretail_all_zero_edit.compression.scratch_bytes == 96 and
  .refusals.consumed_stream_overflow == true and
  .refusals.existing_output_directory == true and
  .refusals.hardlink_source_alias == true and
  .refusals.mutated_manifest == true and
  .refusals.overflow_output_artifact_created == false and
  .refusals.partial_second_link_collision == true and
  .refusals.prepublication_raced_name == true and
  .refusals.staged_volume_symlink_redirection == true and
  .refusals.symlinked_output_parent == true and
  .refusals.wrong_catalog_hash == true and
  .refusals.wrong_target_id == true and
  .refusals.wrong_vertex_count == true and
  .claims.catalog_backed_same_count_float3_dispatcher_implemented == true and
  .claims.authorized_catalog_targets == 75 and
  .claims.upper_deck_full_copied_volume_roundtrip_proved == true and
  .claims.changed_topology_or_count_proved == false and
  .claims.runtime_visibility_proved == false and
  .claims.semantic_rigidity_proved == false and
  .claims.production_ready == false
' "$roundtrip" >/dev/null

jq -e '
  .claim_flags.pinned_group36_float3_same_count_writer_implemented == true and
  .claim_flags.stadium_catalog_75_float3_dispatch_implemented == true and
  .claim_flags.general_eligibility_profile_writer_dispatch_implemented == false and
  .same_count_position_write_boundary_v1.implemented_stadium_catalog_v2.authorized_target_count == 75 and
  .same_count_position_write_boundary_v1.implemented_stadium_catalog_v2.second_target_name == "upper_deck" and
  .claim_flags.topology_write_proved == false and
  .claim_flags.runtime_proved == false and
  .claim_flags.production_ready == false
' "$spec" >/dev/null

! rg -q 'nfl_stadium_catalog_position_patch|from nfl_|import nfl_' \
  tools/nfl_stadium_catalog_position_verify.py

PYTHONPYCACHEPREFIX="$temporary/pycache" PYTHONPATH=tools python3 -m py_compile \
  tools/nfl_stadium_catalog_position_patch.py \
  tools/nfl_stadium_catalog_position_verify.py \
  tests/test_nfl_stadium_catalog_position_patch.py \
  tests/nfl_stadium_catalog_position_patch_test.py

python3 -m unittest tests.test_nfl_stadium_catalog_position_patch >/dev/null
bash tools/validate_nfl_scne_static_format_spec.sh >/dev/null

PYTHONPATH=tools python3 tests/nfl_stadium_catalog_position_patch_test.py \
  --report "$temporary/roundtrip.json"
cmp "$roundtrip" "$temporary/roundtrip.json"

patch_line=$(PYTHONPATH=tools python3 tools/nfl_stadium_catalog_position_patch.py \
  --index "$index" --catalog "$catalog" --recipe "$recipe" \
  --output-dir "$temporary/cli-output")
test "$patch_line" = \
  'NFL_CATALOG_POSITION_PATCH_COMPLETE target=nfl2k5/stadium/o3280/c5/s1 mode=patched vertices=12 sha256=96c2d8dd4ed4f65df67157ad6a822878bcbd4eefc960135176cd8030c9f9b176'

verify_line=$(python3 tools/nfl_stadium_catalog_position_verify.py \
  --source-index "$index" --catalog "$catalog" --recipe "$recipe" \
  --output-dir "$temporary/cli-output" --report "$temporary/cli-verify.json")
test "$verify_line" = \
  'NFL_CATALOG_POSITION_VERIFY_PASS target=nfl2k5/stadium/o3280/c5/s1 mode=patched vertices=12 consumed=908799 scratch=96 runtime=false'

jq -e '
  .schema == "nfl2k5_catalog_static_position_verify/v2" and
  .target_id == "nfl2k5/stadium/o3280/c5/s1" and
  .vertex_count == 12 and
  .output.volume_sha256 == "96c2d8dd4ed4f65df67157ad6a822878bcbd4eefc960135176cd8030c9f9b176" and
  .decoded.decoded_changed_byte_count == 144 and
  .decoded.outside_position_bit_exact == true and
  .compression.consumed_bytes == 908799 and
  .compression.minimum_alias_scratch_bytes == 66 and
  .compression.scratch_bytes == 96 and
  .rigid_static.mechanical_only == true and
  .claims.catalog_dispatcher == true and
  .claims.runtime_proved == false and
  .claims.production_ready == false
' "$temporary/cli-verify.json" >/dev/null

test "$(sha256sum "$index" | cut -d' ' -f1)" = \
  '34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d'
test "$(sha256sum "$pack" | cut -d' ' -f1)" = \
  '779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a'

echo 'NFL_CATALOG_POSITION_PATCH_VALIDATION_PASS target=3280/5/2648/1:upper_deck vertices=12 catalog_targets=75 format=FLOAT3 noop_pack_exact=true changed_decoded_bytes=144 changed_consumed=908799/908864 zero_gap=65 alias=66 scratch=96 fixed_tail=16 outside_chunk_exact=true overflow_refused=true wrong_target_count_hash_refused=true hardlink_refused=true symlink_parent_refused=true staged_symlink_redirection_refused=true publication_races_refused=true manifest_tamper_refused=true independent_verify=true output_pack_sha256=96c2d8dd4ed4f65df67157ad6a822878bcbd4eefc960135176cd8030c9f9b176 report_sha256=05ab26057b0ebd244a0a090d2268f1cac49b3b820269b410e38c5e6b89a6d9c3 spec_sha256=5947b18a7f9fe4b4f6895ca4ea37e5aadd55edb5d365128f46561011fdf8a01e runtime=false semantic_rigidity=false production=false originals_unchanged=yes tests=10'
