#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

GAME_DIR='extracted/All-Pro Football 2K8 (USA)'
CATALOG='mod_editor/data/apf2k8_stadium_static_position_target_catalog.v1.json'
SCHEMA='mod_editor/data/apf2k8_stadium_position_recipe.v2.schema.json'
SAMPLE='reports/asset_samples/apf_scene/stadium_node3_nonretail_zero_recipe.json'
REPORT='reports/assets/apf_scne_catalog_position_roundtrip.json'

check_pin() {
  local path="$1" size="$2" digest="$3"
  test "$(stat -c %s "$path")" = "$size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$digest"
}

check_pin "$CATALOG" 456821 e2b21ebf4d358358627d26b7d7ea3c6cf600ea3f9d1e139cb9caa8ff1748a424
check_pin "$SCHEMA" 5585 41fcf955c65d81bb5da2d229d6a2ffee692a9c5ae80eda1c0849911c90950277
check_pin "$SAMPLE" 2971 329d3290201407f1acb905d432bf8b53547a654fd895cd37a347ae979c4b60a9
check_pin "$REPORT" 5932 eebd060dbcbeb07a01ccb2ac5a3491f0306ec43424080b33ad49258819333eea

jq -e '
  .schema == "apf2k8_scne_catalog_position_roundtrip/v2" and
  .contains_retail_geometry == false and
  .contains_replacement_bytes == false and
  .catalog.authorized_additional_targets == 77 and
  .target.target_id == "outer14.inner8.node3" and
  .target.vertex_count == 24 and
  .target.draw_record_count == 3 and
  .target.approved_position_lane_bytes == 288 and
  .no_op_witness.complete_1a_byte_identical == true and
  .no_op_witness.retail_coordinates_committed == false and
  .changed_witness.output_outer14_sha256 == "23e15b372b7e3be49a2b0a475232c4f44b9c4de9d4a7a572e5e98a8df9d7af9e" and
  .changed_witness.output_1a_sha256 == "cf8cd039e6ef3f078f193c1563bce76d3983372cd67b30a0b051487699378022" and
  .changed_witness.changed_decoded_block0_bytes == 284 and
  .changed_witness.changed_decoded_bytes_subset_of_288_authorized_lane_bytes == true and
  .changed_witness.allocation_slack_after_bytes == 21907 and
  .preservation_proof.all_scne_bytes_outside_selected_position_lanes_exact == true and
  .preservation_proof.all_twelve_non_target_parts_exact == true and
  .independent_verifier.imports_any_position_writer == false and
  .claims.catalog_backed_dispatcher_implemented == true and
  .claims.changed_topology_proved == false and
  .claims.rigid_attachment_proved == false and
  .claims.emulator_runtime_visibility_proved == false and
  .claims.xbox_360_hardware_proved == false and
  .claims.production_mesh_importer_proved == false
' "$REPORT" >/dev/null

python3 -m unittest tests.test_apf_stadium_catalog_position_patch >/dev/null

if test "${APF_SCNE_CATALOG_POSITION_FAST:-0}" = 1; then
  echo 'APF_SCNE_CATALOG_POSITION_VALIDATION_PASS mode=fast schema=v2 targets=77 target=outer14.inner8.node3 vertices=24 draws=3 witnesses=2 tests=14 full_copied_1a=skipped report_sha256=eebd060dbcbeb07a01ccb2ac5a3491f0306ec43424080b33ad49258819333eea runtime=false hardware=false production=false'
  exit 0
fi

tmp="$(mktemp -d)"
cleanup() {
  rm -rf -- "$tmp"
}
trap cleanup EXIT

source_before="$(sha256sum "$GAME_DIR/0A" "$GAME_DIR/0B" "$GAME_DIR/1A" "$GAME_DIR/1B")"

noop_recipe="$tmp/noop.json"
recipe_result="$(python3 tools/apf_stadium_catalog_position_proof_recipes.py --game-dir "$GAME_DIR" --noop-output "$noop_recipe")"
test "$recipe_result" = 'APF_SCNE_CATALOG_PROOF_RECIPE_LOCAL_ONLY_PASS target=outer14.inner8.node3 vertices=24 sha256=aafdba85d416a7e636f6256683451c1709b10611d9bf12fc31b206bffdcf131e committed=false'

noop_patch="$(python3 tools/apf_stadium_catalog_position_patch.py --game-dir "$GAME_DIR" --recipe "$noop_recipe" --output-dir "$tmp/noop")"
test "$noop_patch" = 'APF_SCNE_CATALOG_POSITION_PATCH_PASS mode=no_op target=outer14.inner8.node3 vertices=24 copied_pack=1A outer_sha256=347503ffdcd910b57425584869e1520238b1298e516f643936568b83d5a5a07a output_pack_sha256=9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb runtime=false hardware=false production=false'
test "$(find "$tmp/noop" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')" = '1A apf2k8_scne_catalog_position_manifest.json '
noop_verify="$(python3 tools/apf_stadium_catalog_position_verify.py --game-dir "$GAME_DIR" --recipe "$noop_recipe" --output-dir "$tmp/noop" --artifact "$tmp/noop_verify.json")"
test "$noop_verify" = 'APF_SCNE_CATALOG_POSITION_VERIFY_PASS mode=no_op target=outer14.inner8.node3 vertices=24 output_pack_sha256=9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb siblings=11 non_target_parts=12 runtime=false hardware=false production=false'
cmp -s "$GAME_DIR/1A" "$tmp/noop/1A"
check_pin "$tmp/noop/apf2k8_scne_catalog_position_manifest.json" 6147 ae6215ad2e71d220749932384288a68f82ab4b6e9d3e9bc0f785ba1a67a82ead
check_pin "$tmp/noop_verify.json" 2889 f74be14d22bc83a00923ffc19e092f3e6a1a07b638fdfed9f238eaea343aad0f

changed_patch="$(python3 tools/apf_stadium_catalog_position_patch.py --game-dir "$GAME_DIR" --recipe "$SAMPLE" --output-dir "$tmp/changed")"
test "$changed_patch" = 'APF_SCNE_CATALOG_POSITION_PATCH_PASS mode=changed target=outer14.inner8.node3 vertices=24 copied_pack=1A outer_sha256=23e15b372b7e3be49a2b0a475232c4f44b9c4de9d4a7a572e5e98a8df9d7af9e output_pack_sha256=cf8cd039e6ef3f078f193c1563bce76d3983372cd67b30a0b051487699378022 runtime=false hardware=false production=false'
test "$(find "$tmp/changed" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')" = '1A apf2k8_scne_catalog_position_manifest.json '
changed_verify="$(python3 tools/apf_stadium_catalog_position_verify.py --game-dir "$GAME_DIR" --recipe "$SAMPLE" --output-dir "$tmp/changed" --artifact "$tmp/changed_verify.json")"
test "$changed_verify" = 'APF_SCNE_CATALOG_POSITION_VERIFY_PASS mode=changed target=outer14.inner8.node3 vertices=24 output_pack_sha256=cf8cd039e6ef3f078f193c1563bce76d3983372cd67b30a0b051487699378022 siblings=11 non_target_parts=12 runtime=false hardware=false production=false'
check_pin "$tmp/changed/apf2k8_scne_catalog_position_manifest.json" 6253 b350705a1ddfea61c6d5bae065e88a702750296ec723342d38103e513ea3f851
check_pin "$tmp/changed_verify.json" 2891 507c6adda8902b671bf1ade87bb52cd5655c305d7853a902683cf779eea0f00f
test "$(sha256sum "$tmp/changed/1A" | cut -d' ' -f1)" = cf8cd039e6ef3f078f193c1563bce76d3983372cd67b30a0b051487699378022

mkdir "$tmp/mutant"
cp --reflink=auto "$tmp/changed/1A" "$tmp/mutant/1A"
cp "$tmp/changed/apf2k8_scne_catalog_position_manifest.json" "$tmp/mutant/apf2k8_scne_catalog_position_manifest.json"
python3 -c 'import os,sys; p=sys.argv[1]; fd=os.open(p,os.O_RDWR); o=404643840+0x84; b=os.pread(fd,1,o); os.pwrite(fd,bytes([b[0]^1]),o); os.close(fd)' "$tmp/mutant/1A"
if python3 tools/apf_stadium_catalog_position_verify.py --game-dir "$GAME_DIR" --recipe "$SAMPLE" --output-dir "$tmp/mutant" --artifact "$tmp/mutant_verify.json" >/dev/null 2>&1; then
  echo 'error: independent verifier accepted forbidden IFF descriptor mutation' >&2
  exit 1
fi
test ! -e "$tmp/mutant_verify.json"

source_after="$(sha256sum "$GAME_DIR/0A" "$GAME_DIR/0B" "$GAME_DIR/1A" "$GAME_DIR/1B")"
test "$source_after" = "$source_before"

echo 'APF_SCNE_CATALOG_POSITION_VALIDATION_PASS mode=full schema=v2 targets=77 target=outer14.inner8.node3 vertices=24 draws=3 witnesses=2 tests=14 full_copied_1a=true noop_exact=true changed_outer=23e15b372b7e3be49a2b0a475232c4f44b9c4de9d4a7a572e5e98a8df9d7af9e changed_1a=cf8cd039e6ef3f078f193c1563bce76d3983372cd67b30a0b051487699378022 changed_decoded=284 slack=21907 siblings=11 non_target_parts=12 mutation_refused=true overflow_refused=true symlink_refused=true hardlink_refused=true publication_races_refused=true source_unchanged=true independent_verify=true report_sha256=eebd060dbcbeb07a01ccb2ac5a3491f0306ec43424080b33ad49258819333eea runtime=false hardware=false production=false'
