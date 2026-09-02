#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
pack='extracted/ESPN NFL 2K5 (USA)/vc_53450030/9'
schema='reports/specs/nfl2k5_static_position_recipe.schema.json'
recipe='reports/asset_samples/nfl_scne/stadium_group36_zero_recipe.json'
roundtrip='reports/assets/nfl_stadium_group36_position_patch_roundtrip.json'
spec='reports/specs/nfl2k5_xbox_static_scne.v1.json'
doc='docs/research/nfl_static_position_writeback.md'
temporary=$(mktemp -d "$root/.nfl-group36-position-validate.XXXXXX")
trap 'rm -rf "$temporary"' EXIT

for required in \
  "$index" "$pack" "$schema" "$recipe" "$roundtrip" "$spec" "$doc" \
  tools/nfl_stadium_group36_position_patch.py \
  tools/nfl_stadium_group36_position_verify.py \
  tests/test_nfl_stadium_group36_position_patch.py \
  tests/nfl_stadium_group36_position_patch_test.py; do
  test -f "$required"
done

test "$(stat -c %s "$schema")" = 1381
test "$(sha256sum "$schema" | cut -d' ' -f1)" = \
  'a43644c1e75addc9f478aad655fa74120aede16406195a37f2cde94fb081cefb'
test "$(stat -c %s "$recipe")" = 787
test "$(sha256sum "$recipe" | cut -d' ' -f1)" = \
  'ad6b4fd7e658512c54770c66731adeea81e8b08b7731c981a0757b713a356781'
test "$(stat -c %s "$roundtrip")" = 7455
test "$(sha256sum "$roundtrip" | cut -d' ' -f1)" = \
  '45f65c16b4b4d25a30fb63643d3ec1a8f7476a8993e3ca370df33c244cbbef05'
test "$(stat -c %s "$spec")" = 47126
test "$(sha256sum "$spec" | cut -d' ' -f1)" = \
  '5947b18a7f9fe4b4f6895ca4ea37e5aadd55edb5d365128f46561011fdf8a01e'
test "$(stat -c %s "$doc")" = 7365
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  'e42f5bb608b65ad0b8e11f81f910f555c6fd1924f23906c154f6edb7c32af4d1'

test "$(sha256sum tools/nfl_stadium_group36_position_patch.py | cut -d' ' -f1)" = \
  'd781d49a8adaa23941e5854f734d531b458d1da70c6725f5ad0f2c7c1f92e82b'
test "$(sha256sum tools/nfl_stadium_group36_position_verify.py | cut -d' ' -f1)" = \
  '626a54b109f604274311ce14576516a3f6dd3f583a4617f2420c741e76a6c8cc'

jq -e '
  .properties.target.const.outer_index == 3280 and
  .properties.target.const.outer_id == "0xe4d6b0bc" and
  .properties.target.const.chunk_index == 5 and
  .properties.target.const.scene_index == 2648 and
  .properties.target.const.shape_index == 4 and
  .properties.target.const.shape_name == "group36" and
  .properties.encoding.const == {
    "component_type":"float32_le",
    "components_per_vertex":3,
    "coordinate_space":"raw_xbox",
    "stride_bytes":12,
    "vertex_count":4
  } and
  .additionalProperties == false
' "$schema" >/dev/null

jq -e '
  .schema == "nfl2k5_static_position_patch_roundtrip/v1" and
  .source.retail_modified == false and
  .no_op.mode == "no_op" and
  .no_op.output.pack_changed_byte_count == 0 and
  .no_op.output.volume_sha256 == "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a" and
  .no_op.compression.consumed_bytes == 908864 and
  .controlled_all_zero_edit.mode == "patched" and
  .controlled_all_zero_edit.output.volume_sha256 == "c48117938862fa03b5b3d871db87cb7d3c32a9653be497d46dc188ba51993fca" and
  .controlled_all_zero_edit.decoded.outside_position_bit_exact == true and
  .controlled_all_zero_edit.compression == {
    "consumed_bytes":908825,
    "fixed_tail_sha256":"cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4",
    "minimum_alias_scratch_bytes":39,
    "padding_bytes":55,
    "retail_cap":908864,
    "scratch_bytes":64,
    "zero_gap_bytes":39
  } and
  .refusals.existing_output_directory == true and
  .refusals.tail_consuming_growth_recipe == true and
  .refusals.hardlink_source_alias == true and
  .refusals.recursive_manifest_extra_key == true and
  .refusals.symlinked_output_parent == true and
  .refusals.prepublication_raced_name == true and
  .refusals.partial_second_link_collision == true and
  .refusals.staged_replacement_before_unlink == true and
  .refusals.growth_output_artifact_created == false and
  .safety.output_directory_atomically_reserved == true and
  .safety.link_if_absent_publication_never_replaces == true and
  .safety.cleanup_unlinks_owned_regular_inodes_only == true and
  .safety.attacker_raced_inodes_preserved == true and
  .claims.same_count_group36_float3_write_back_proved == true and
  .claims.arbitrary_static_mesh_write_back_proved == false and
  .claims.changed_topology_write_back_proved == false and
  .claims.runtime_visibility_proved == false and
  .claims.production_ready == false
' "$roundtrip" >/dev/null

PYTHONPYCACHEPREFIX="$temporary/pycache" PYTHONPATH=tools python3 -m py_compile \
  tools/nfl_stadium_group36_position_patch.py \
  tools/nfl_stadium_group36_position_verify.py \
  tests/test_nfl_stadium_group36_position_patch.py \
  tests/nfl_stadium_group36_position_patch_test.py

python3 -m unittest tests.test_nfl_stadium_group36_position_patch >/dev/null
bash tools/validate_nfl_scne_static_format_spec.sh >/dev/null

PYTHONPATH=tools python3 tests/nfl_stadium_group36_position_patch_test.py \
  --report "$temporary/roundtrip.json"
cmp "$roundtrip" "$temporary/roundtrip.json"

patch_line=$(PYTHONPATH=tools python3 tools/nfl_stadium_group36_position_patch.py \
  --index "$index" --recipe "$recipe" --output-dir "$temporary/cli-output")
test "$patch_line" = \
  'NFL_GROUP36_POSITION_PATCH_COMPLETE mode=patched output='"$temporary"'/cli-output/9 sha256=c48117938862fa03b5b3d871db87cb7d3c32a9653be497d46dc188ba51993fca'

verify_line=$(python3 tools/nfl_stadium_group36_position_verify.py \
  --source-index "$index" --recipe "$recipe" \
  --output-dir "$temporary/cli-output" --report "$temporary/cli-verify.json")
test "$verify_line" = \
  'NFL_GROUP36_POSITION_VERIFY_PASS mode=patched consumed=908825 scratch=64 runtime=false'

jq -e '
  .schema == "nfl2k5_static_position_verify/v1" and
  .mode == "patched" and
  .output.volume_sha256 == "c48117938862fa03b5b3d871db87cb7d3c32a9653be497d46dc188ba51993fca" and
  .output.outside_chunk_bit_exact == true and
  .decoded.outside_position_bit_exact == true and
  .compression.consumed_bytes == 908825 and
  .compression.zero_gap_bytes == 39 and
  .compression.scratch_bytes == 64 and
  .rigid_static.material == "cement01" and
  .rigid_static.native_quads_indices == [0,1,2,3] and
  .claims.topology_write_back == false and
  .claims.runtime_proved == false and
  .claims.production_ready == false
' "$temporary/cli-verify.json" >/dev/null

test "$(sha256sum "$index" | cut -d' ' -f1)" = \
  '34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d'
test "$(sha256sum "$pack" | cut -d' ' -f1)" = \
  '779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a'

echo 'NFL_GROUP36_POSITION_PATCH_VALIDATION_PASS target=3280/5/2648/4:group36 vertices=4 format=FLOAT3 noop_pack_exact=true changed_decoded_bytes=48 changed_consumed=908825/908864 zero_gap=39 scratch=64 fixed_tail=16 outside_chunk_exact=true growth_refused=true hardlink_refused=true symlink_parent_refused=true publication_races_refused=true independent_verify=true output_pack_sha256=c48117938862fa03b5b3d871db87cb7d3c32a9653be497d46dc188ba51993fca report_sha256=45f65c16b4b4d25a30fb63643d3ec1a8f7476a8993e3ca370df33c244cbbef05 spec_sha256=5947b18a7f9fe4b4f6895ca4ea37e5aadd55edb5d365128f46561011fdf8a01e runtime=false production=false originals_unchanged=yes'
