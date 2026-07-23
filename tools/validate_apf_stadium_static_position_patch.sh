#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

GAME_DIR='extracted/All-Pro Football 2K8 (USA)'
SAMPLE_RECIPE='reports/asset_samples/apf_scene/stadium_polySurface19930_nonretail_zero_recipe.json'
NOOP_MANIFEST='reports/assets/apf_scne_same_count_position_noop_manifest.json'
NOOP_VERIFY='reports/assets/apf_scne_same_count_position_noop_verification.json'
CHANGED_MANIFEST='reports/assets/apf_scne_same_count_position_changed_manifest.json'
CHANGED_VERIFY='reports/assets/apf_scne_same_count_position_changed_verification.json'
REPORT='reports/assets/apf_scne_same_count_position_roundtrip.json'

check_pin() {
  local path="$1" size="$2" digest="$3"
  test "$(stat -c %s "$path")" = "$size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$digest"
}

check_pin reports/specs/apf2k8_scne_same_count_position_recipe.schema.json 4064 8094a4a64325728082091e87ba3fcd0e5ed30c8c6f06f1e7074934720438af51
check_pin "$SAMPLE_RECIPE" 1938 fc3b3e010cc534634470e29e8395a5e56c6b0cbc2d714464355a27be3f59764b
check_pin "$NOOP_MANIFEST" 5821 b735c62338158315052717f4f7ba7352aafc4e43e0017f1126f3e4a4b2585d23
check_pin "$NOOP_VERIFY" 2479 1be207ffd820faa7356d0c7f0d73f166bda06271a537dc936c049b696ac4deb9
check_pin "$CHANGED_MANIFEST" 5925 62673e228fcc501669d9bd3fd98d16598d872bf1e24b8ef81f190228b8aae116
check_pin "$CHANGED_VERIFY" 2481 b2873a1c45057eb434444aebe9eb15f625bf0af7995c25bf689bc7b7005759ae
check_pin "$REPORT" 6971 5e85c58cf258b19ab40f7b046f7da3010a510dac8d2cd83ede976883af8ab5dd

jq -e '
  .schema == "apf2k8_scne_same_count_position_roundtrip/v1" and
  .contains_retail_geometry == false and
  .contains_replacement_bytes == false and
  .recipe_distribution.retail_or_retail_derived_recipe_coordinates_committed == false and
  .target.vertex_count == 4 and
  .target.authorized_position_lane_bytes == 48 and
  .no_op_witness.complete_1a_byte_identical == true and
  .no_op_witness.source_and_output_1a_sha256 == "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb" and
  .changed_witness.output_1a_sha256 == "6f275ccb780acfee0cba9cd59c38e4bb2aedb18d01dec7030d61546441026b40" and
  .changed_witness.output_outer_sha256 == "89ec32ee6da2a73f494667c01aa8ea9968c49c97317ec85d3c0342c84eb632fa" and
  .changed_witness.changed_decoded_dram_bytes == 14 and
  .changed_witness.allocation_slack_bytes == 1391 and
  .preservation_proof.twelve_non_target_parts_exact == true and
  .claims.offline_structural_write_back_proved == true and
  .claims.rigid_attachment_proved == false and
  .claims.changed_topology_proved == false and
  .claims.emulator_runtime_visibility_proved == false and
  .claims.xbox_360_hardware_proved == false and
  .claims.production_mesh_importer_proved == false
' "$REPORT" >/dev/null

python3 -m unittest tests.test_apf_stadium_static_position_patch >/dev/null
proof_validation="$(python3 tools/apf_stadium_static_position_proof.py)"
test "$proof_validation" = '{"non_target_parts": 12, "report_sha256": "5e85c58cf258b19ab40f7b046f7da3010a510dac8d2cd83ede976883af8ab5dd", "runtime": false, "schema": "apf2k8_scne_same_count_position_roundtrip_validation/v1", "vertices": 4, "witnesses": 2}'

tmp="$(mktemp -d)"
cleanup() {
  rm -rf -- "$tmp"
}
trap cleanup EXIT
python3 tools/apf_stadium_static_position_proof.py --generate "$tmp/report.json" >/dev/null
cmp -s "$REPORT" "$tmp/report.json"

if test "${APF_SCNE_POSITION_FAST:-0}" = 1; then
  echo 'APF_SCNE_SAME_COUNT_POSITION_VALIDATION_PASS mode=fast schema=v1 vertices=4 witnesses=2 tests=10 full_copied_1a=skipped report_sha256=5e85c58cf258b19ab40f7b046f7da3010a510dac8d2cd83ede976883af8ab5dd runtime=false hardware=false'
  exit 0
fi

source_before="$(sha256sum "$GAME_DIR/0A" "$GAME_DIR/0B" "$GAME_DIR/1A" "$GAME_DIR/1B")"
NOOP_RECIPE="$tmp/noop_recipe.json"
CHANGED_RECIPE="$tmp/changed_recipe.json"
proof_recipes="$(python3 tools/apf_stadium_static_position_proof_recipes.py --game-dir "$GAME_DIR" --noop-output "$NOOP_RECIPE" --changed-output "$CHANGED_RECIPE")"
test "$proof_recipes" = 'APF_SCNE_PROOF_RECIPES_LOCAL_ONLY_PASS noop_sha256=1adf02c37cb458afef1509a8cbe4cfa82260b897833553222af5d1fa97403faf changed_sha256=18ae4558668a1a1831031bb6191e3ff914abaaa867ca369836f8673521173d2b committed=false'

noop_patch="$(python3 tools/apf_stadium_static_position_patch.py --game-dir "$GAME_DIR" --recipe "$NOOP_RECIPE" --output-dir "$tmp/noop")"
test "$noop_patch" = 'APF_SCNE_SAME_COUNT_POSITION_PATCH_PASS mode=no_op vertices=4 copied_pack=1A outer_sha256=347503ffdcd910b57425584869e1520238b1298e516f643936568b83d5a5a07a output_pack_sha256=9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb runtime=false hardware=false'
test "$(find "$tmp/noop" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')" = '1A apf2k8_scne_same_count_position_manifest.json '
cmp -s "$NOOP_MANIFEST" "$tmp/noop/apf2k8_scne_same_count_position_manifest.json"
noop_verified="$(python3 tools/apf_stadium_static_position_verify.py --game-dir "$GAME_DIR" --recipe "$NOOP_RECIPE" --output-dir "$tmp/noop" --artifact "$tmp/noop_verify.json")"
test "$noop_verified" = 'APF_SCNE_SAME_COUNT_POSITION_VERIFY_PASS mode=no_op vertices=4 output_pack_sha256=9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb siblings=11 non_target_parts=12 runtime=false hardware=false'
cmp -s "$NOOP_VERIFY" "$tmp/noop_verify.json"
cmp -s "$GAME_DIR/1A" "$tmp/noop/1A"

changed_patch="$(python3 tools/apf_stadium_static_position_patch.py --game-dir "$GAME_DIR" --recipe "$CHANGED_RECIPE" --output-dir "$tmp/changed")"
test "$changed_patch" = 'APF_SCNE_SAME_COUNT_POSITION_PATCH_PASS mode=changed vertices=4 copied_pack=1A outer_sha256=89ec32ee6da2a73f494667c01aa8ea9968c49c97317ec85d3c0342c84eb632fa output_pack_sha256=6f275ccb780acfee0cba9cd59c38e4bb2aedb18d01dec7030d61546441026b40 runtime=false hardware=false'
test "$(find "$tmp/changed" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')" = '1A apf2k8_scne_same_count_position_manifest.json '
cmp -s "$CHANGED_MANIFEST" "$tmp/changed/apf2k8_scne_same_count_position_manifest.json"
changed_verified="$(python3 tools/apf_stadium_static_position_verify.py --game-dir "$GAME_DIR" --recipe "$CHANGED_RECIPE" --output-dir "$tmp/changed" --artifact "$tmp/changed_verify.json")"
test "$changed_verified" = 'APF_SCNE_SAME_COUNT_POSITION_VERIFY_PASS mode=changed vertices=4 output_pack_sha256=6f275ccb780acfee0cba9cd59c38e4bb2aedb18d01dec7030d61546441026b40 siblings=11 non_target_parts=12 runtime=false hardware=false'
cmp -s "$CHANGED_VERIFY" "$tmp/changed_verify.json"

mkdir "$tmp/mutant"
cp --reflink=auto "$tmp/changed/1A" "$tmp/mutant/1A"
cp "$tmp/changed/apf2k8_scne_same_count_position_manifest.json" "$tmp/mutant/apf2k8_scne_same_count_position_manifest.json"
python3 -c 'import os,sys; p=sys.argv[1]; fd=os.open(p,os.O_RDWR); o=404643840+0x84; b=os.pread(fd,1,o); os.pwrite(fd,bytes([b[0]^1]),o); os.close(fd)' "$tmp/mutant/1A"
if python3 tools/apf_stadium_static_position_verify.py --game-dir "$GAME_DIR" --recipe "$CHANGED_RECIPE" --output-dir "$tmp/mutant" --artifact "$tmp/mutant_verify.json" >/dev/null 2>&1; then
  echo 'error: independent verifier accepted forbidden IFF file-descriptor mutation' >&2
  exit 1
fi
test ! -e "$tmp/mutant_verify.json"

source_after="$(sha256sum "$GAME_DIR/0A" "$GAME_DIR/0B" "$GAME_DIR/1A" "$GAME_DIR/1B")"
test "$source_after" = "$source_before"

echo 'APF_SCNE_SAME_COUNT_POSITION_VALIDATION_PASS mode=full schema=v1 vertices=4 witnesses=2 tests=10 full_copied_1a=true noop_exact=true changed_outer=89ec32ee6da2a73f494667c01aa8ea9968c49c97317ec85d3c0342c84eb632fa changed_1a=6f275ccb780acfee0cba9cd59c38e4bb2aedb18d01dec7030d61546441026b40 siblings=11 non_target_parts=12 mutation_refused=true source_unchanged=true report_sha256=5e85c58cf258b19ab40f7b046f7da3010a510dac8d2cd83ede976883af8ab5dd runtime=false hardware=false'
