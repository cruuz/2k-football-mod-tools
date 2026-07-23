#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
inventory='reports/assets/nfl2k5_motion_inventory.json'
meter_manifest='reports/assets/nfl_meter_skin_gltf_manifest.json'
meter_gltf='assets/intermediate/nfl2k5/meter_skin_samples/0346_0109_referee_meter_skin.gltf'
ownership='reports/assets/nfl_ref_clip_ownership.json'
root_trajectory='reports/assets/nfl_referee_root_trajectory.json'
render_root='reports/assets/nfl_referee_render_root.json'
canonical_dir='assets/intermediate/nfl2k5/animated_samples'
canonical_name='0346_0109_referee_penalty_delay_game_R_120hz'
canonical_gltf="$canonical_dir/$canonical_name.gltf"
canonical_bin="$canonical_dir/$canonical_name.bin"
canonical_manifest='reports/assets/nfl_referee_animated_gltf_manifest.json'
expected_ownership_sha256='17c728da2b25099a9ed1271e4476c9f8ff1ce25daaaff6af2a1ff70b517fc8d3'
expected_gltf_sha256='685fe2b2ca8fa23da87eabdf7846125e9555884bd81880b682d508d322883b9f'
expected_bin_sha256='c00087012f1152ac75d29652639b1f0a6b99962f2c573e57cfc4caf7525fbd55'
expected_manifest_sha256='4c3b32185495a4e6ab69b4ca3978c8ceb5b5356d1c6732b8e2010ff63bb44625'

native_sources=(
  src/recovered/nfl2k5/coach_ref_pose.c
  src/recovered/nfl2k5/motion_pose_sample.c
  src/recovered/nfl2k5/packed_pose.c
  src/recovered/nfl2k5/quaternion_interpolation.c
)
required=(
  "$index"
  "$inventory"
  "$meter_manifest"
  "$meter_gltf"
  "${meter_gltf%.gltf}.bin"
  "$ownership"
  "$root_trajectory"
  "$render_root"
  "$canonical_gltf"
  "$canonical_bin"
  "$canonical_manifest"
  tools/nfl_referee_animated_gltf.py
  tools/nfl_referee_animated_gltf_validate.py
  tools/nfl_outer.py
  tools/nfl_rest_orientation.py
  docs/research/nfl_referee_animated_gltf.md
  include/recovered/nfl2k5/coach_ref_pose.h
  include/recovered/nfl2k5/motion_pose_sample.h
  include/recovered/nfl2k5/packed_pose.h
  include/recovered/nfl2k5/quaternion_interpolation.h
  src/recovered/nfl2k5/quaternion_interpolation_table.inc
  "${native_sources[@]}"
)
for path in "${required[@]}"; do
  test -f "$path"
done

hash_of() {
  sha256sum "$1" | cut -d ' ' -f 1
}

check_hash() {
  local path=$1
  local expected=$2
  local actual
  actual=$(hash_of "$path")
  if [[ $actual != "$expected" ]]; then
    echo "hash differs for $path: $actual != $expected" >&2
    return 1
  fi
}

check_hash "$ownership" "$expected_ownership_sha256"
command -v gcc >/dev/null
command -v clang-18 >/dev/null
command -v jq >/dev/null

temporary=$(mktemp -d /tmp/nfl-referee-animated-gltf.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"
python3 -m py_compile \
  tools/nfl_referee_animated_gltf.py \
  tools/nfl_referee_animated_gltf_validate.py

strict=(
  -std=c11 -O2 -fno-fast-math
  -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
  -Wstrict-prototypes -Wmissing-prototypes
  -Iinclude -fPIC -shared
)

for compiler in gcc clang-18; do
  label=${compiler%-18}
  output_dir="$temporary/$label"
  mkdir "$output_dir"
  "$compiler" "${strict[@]}" "${native_sources[@]}" -lm \
    -o "$temporary/libvc_nfl_coach_ref_pose_$label.so"
  PYTHONPATH=tools python3 tools/nfl_referee_animated_gltf.py \
    --index "$index" \
    --motion-inventory "$inventory" \
    --meter-manifest "$meter_manifest" \
    --source-gltf "$meter_gltf" \
    --library "$temporary/libvc_nfl_coach_ref_pose_$label.so" \
    --ownership-report "$ownership" \
    --root-trajectory-report "$root_trajectory" \
    --render-root-report "$render_root" \
    --output "$output_dir/$canonical_name.gltf" \
    --manifest "$output_dir/manifest.json"
  PYTHONPATH=tools python3 tools/nfl_referee_animated_gltf_validate.py \
    --manifest "$output_dir/manifest.json" \
    --asset-dir "$output_dir" \
    --ownership-report "$ownership" \
    --root-trajectory-report "$root_trajectory" \
    --render-root-report "$render_root"
  check_hash "$output_dir/$canonical_name.gltf" "$expected_gltf_sha256"
  check_hash "$output_dir/$canonical_name.bin" "$expected_bin_sha256"
  check_hash "$output_dir/manifest.json" "$expected_manifest_sha256"
done

cmp "$temporary/gcc/$canonical_name.gltf" \
    "$temporary/clang/$canonical_name.gltf"
cmp "$temporary/gcc/$canonical_name.bin" \
    "$temporary/clang/$canonical_name.bin"
cmp "$temporary/gcc/manifest.json" "$temporary/clang/manifest.json"
check_hash "$canonical_gltf" "$expected_gltf_sha256"
check_hash "$canonical_bin" "$expected_bin_sha256"
check_hash "$canonical_manifest" "$expected_manifest_sha256"
cmp "$temporary/gcc/$canonical_name.gltf" "$canonical_gltf"
cmp "$temporary/gcc/$canonical_name.bin" "$canonical_bin"
cmp "$temporary/gcc/manifest.json" "$canonical_manifest"

expect_rejected() {
  local label=$1
  shift
  if "$@" >"$temporary/$label.log" 2>&1; then
    echo "negative test unexpectedly succeeded: $label" >&2
    return 1
  fi
}

expect_rejected missing_ownership \
  env PYTHONPATH=tools python3 tools/nfl_referee_animated_gltf.py \
  --library "$temporary/libvc_nfl_coach_ref_pose_gcc.so" \
  --output "$temporary/rejected.gltf" \
  --manifest "$temporary/rejected.json"

jq '.runtime_ownership.confidence = "unproved"' "$ownership" \
  >"$temporary/bad-confidence.json"
expect_rejected bad_confidence \
  env PYTHONPATH=tools python3 tools/nfl_referee_animated_gltf.py \
  --library "$temporary/libvc_nfl_coach_ref_pose_gcc.so" \
  --ownership-report "$temporary/bad-confidence.json" \
  --root-trajectory-report "$root_trajectory" \
  --render-root-report "$render_root" \
  --output "$temporary/rejected.gltf" \
  --manifest "$temporary/rejected.json"

jq '.runtime_ownership.specific_pool_record_instance_link_proved = true' \
  "$ownership" >"$temporary/bad-pool-instance.json"
expect_rejected bad_pool_instance \
  env PYTHONPATH=tools python3 tools/nfl_referee_animated_gltf.py \
  --library "$temporary/libvc_nfl_coach_ref_pose_gcc.so" \
  --ownership-report "$temporary/bad-pool-instance.json" \
  --root-trajectory-report "$root_trajectory" \
  --render-root-report "$render_root" \
  --output "$temporary/rejected.gltf" \
  --manifest "$temporary/rejected.json"

jq '.cutscene_type4_relation.instance_level_link_proved = true' \
  "$ownership" >"$temporary/bad-cutscene-instance.json"
expect_rejected bad_cutscene_instance \
  env PYTHONPATH=tools python3 tools/nfl_referee_animated_gltf.py \
  --library "$temporary/libvc_nfl_coach_ref_pose_gcc.so" \
  --ownership-report "$temporary/bad-cutscene-instance.json" \
  --root-trajectory-report "$root_trajectory" \
  --render-root-report "$render_root" \
  --output "$temporary/rejected.gltf" \
  --manifest "$temporary/rejected.json"

jq '.confidence_boundary.gltf_root_translation_emitted = true' \
  "$root_trajectory" >"$temporary/bad-root-trajectory.json"
expect_rejected bad_root_trajectory \
  env PYTHONPATH=tools python3 tools/nfl_referee_animated_gltf.py \
  --library "$temporary/libvc_nfl_coach_ref_pose_gcc.so" \
  --ownership-report "$ownership" \
  --root-trajectory-report "$temporary/bad-root-trajectory.json" \
  --render-root-report "$render_root" \
  --output "$temporary/rejected.gltf" \
  --manifest "$temporary/rejected.json"

jq '.result.actor_transform_to_renderer_external_root_edge_proved = false' \
  "$render_root" >"$temporary/bad-render-root.json"
expect_rejected bad_render_root \
  env PYTHONPATH=tools python3 tools/nfl_referee_animated_gltf.py \
  --library "$temporary/libvc_nfl_coach_ref_pose_gcc.so" \
  --ownership-report "$ownership" \
  --root-trajectory-report "$root_trajectory" \
  --render-root-report "$temporary/bad-render-root.json" \
  --output "$temporary/rejected.gltf" \
  --manifest "$temporary/rejected.json"

echo 'NFL_REFEREE_ANIMATED_GLTF_VALIDATION_PASS compilers=2 keys=357 channels=25 targets=50 bake_hz=120 sampled_grid_max_degrees=0.0507245908 ownership_negative_tests=6 canonical_outputs_verified=3'
