#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

V1_SPEC='reports/specs/apf2k8_uniform_texture_formats.v1.json'
V2_SPEC='reports/specs/apf2k8_uniform_texture_formats.v2.json'
EXPECTED_V1_SIZE=53829
EXPECTED_V1_SHA256='e46fd58ca3069e1d846c20cd3420a4bdf9fe2e144b02f7dc67608ba6fae0c388'
EXPECTED_V2_SIZE=67332
EXPECTED_V2_SHA256='08ef2528097f4a4c6d26bb6eab486b8f4cde183064e23a97ace4e85c83dc79d7'

test "$(stat -c %s "$V1_SPEC")" = "$EXPECTED_V1_SIZE"
test "$(sha256sum "$V1_SPEC" | cut -d' ' -f1)" = "$EXPECTED_V1_SHA256"
test "$(stat -c %s "$V2_SPEC")" = "$EXPECTED_V2_SIZE"
test "$(sha256sum "$V2_SPEC" | cut -d' ' -f1)" = "$EXPECTED_V2_SHA256"

jq -e '
  .schema == "apf2k8_uniform_texture_formats/v2" and
  .contains_retail_pixels == false and
  (.scope.closed_families == ["jersey_color","pants_color","helmet_color","shoulder_color"]) and
  (.families | length) == 4 and
  ([.families[].per_slot_fixed_allocations | length] | add) == 96 and
  ([.families[].mip_layout | length] | add) == 33 and
  (.families.shoulder_color.paired_normal_fixed_allocations | length) == 24 and
  (.families.shoulder_color.preserved_sibling_files | length) == 3 and
  .families.shoulder_color.controlled_fit_proof.minimum_post_rebuild_slack_bytes == 4723 and
  .families.shoulder_color.claim_flags.three_sibling_textures_preserved_all_24 == true and
  .families.shoulder_color.claim_flags.paired_normal_packages_preserved_all_24 == true and
  .families.shoulder_color.claim_flags.paired_normal_authoring_proved == false and
  ([.families[].claim_flags.production_encoder_proved] | all(. == false)) and
  ([.families[].claim_flags.xbox_360_hardware_proved] | all(. == false))
' "$V2_SPEC" >/dev/null

v1_validation="$(python3 tools/apf_uniform_texture_format_spec.py --spec "$V1_SPEC")"
test "$v1_validation" = '{"families": 3, "mips": 24, "schema": "apf2k8_uniform_texture_format_spec_validation/v2", "slots": 72, "version": 1}'
v2_validation="$(python3 tools/apf_uniform_texture_format_spec.py)"
test "$v2_validation" = '{"families": 4, "mips": 33, "schema": "apf2k8_uniform_texture_format_spec_validation/v2", "slots": 96, "version": 2}'

python3 -m unittest tests.test_apf_uniform_texture_format_spec >/dev/null

echo "APF_UNIFORM_TEXTURE_FORMAT_SPEC_VALIDATION_PASS canonical=v2 immutable_v1=true families=4 slots=96 mips=33 shoulder_slots=24 paired_normals=24 sibling_files=3 retail_pixels=false drift_refusals=4 v1_sha256=$EXPECTED_V1_SHA256 v2_sha256=$EXPECTED_V2_SHA256"
