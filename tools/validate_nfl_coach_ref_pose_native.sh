#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
resource_scan='reports/assets/nfl2k5_resource_chunks_v2.json'
motion_inventory='reports/assets/nfl2k5_motion_inventory.json'

for required in \
  "$index" "$xbe" "$xbe_header" "$resource_scan" "$motion_inventory" \
  include/recovered/nfl2k5/coach_ref_pose.h \
  src/recovered/nfl2k5/coach_ref_pose.c \
  include/recovered/nfl2k5/motion_pose_sample.h \
  src/recovered/nfl2k5/motion_pose_sample.c \
  include/recovered/nfl2k5/packed_pose.h \
  src/recovered/nfl2k5/packed_pose.c \
  include/recovered/nfl2k5/quaternion_interpolation.h \
  src/recovered/nfl2k5/quaternion_interpolation.c \
  src/recovered/nfl2k5/quaternion_interpolation_table.inc \
  tests/nfl_coach_ref_pose_test.c \
  tools/nfl_coach_ref_pose_native_validate.py \
  tools/nfl_outer.py tools/nfl_scene_probe.py tools/nfl_scne_inventory.py \
  tools/nfl_quaternion_interpolation.py \
  docs/research/nfl_coach_ref_pose_native.md; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_coach_ref_pose_native_validate.py

temporary=$(mktemp -d /tmp/nfl-coach-ref-pose.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

sources=(
  src/recovered/nfl2k5/coach_ref_pose.c
  src/recovered/nfl2k5/motion_pose_sample.c
  src/recovered/nfl2k5/packed_pose.c
  src/recovered/nfl2k5/quaternion_interpolation.c
)
strict=(
  -std=c11 -O2 -fno-fast-math
  -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
  -Wstrict-prototypes -Wmissing-prototypes
  -Iinclude
)

for compiler in gcc clang-18; do
  command -v "$compiler" >/dev/null
  label=${compiler%-18}
  "$compiler" "${strict[@]}" tests/nfl_coach_ref_pose_test.c \
    "${sources[@]}" -lm -o "$temporary/${label}-test"
  "$temporary/${label}-test"

  "$compiler" "${strict[@]}" -fPIC -shared "${sources[@]}" -lm \
    -o "$temporary/libvc_nfl_coach_ref_pose_${label}.so"
  PYTHONPATH=tools python3 tools/nfl_coach_ref_pose_native_validate.py \
    --index "$index" \
    --resource-scan "$resource_scan" \
    --motion-inventory "$motion_inventory" \
    --xbe "$xbe" \
    --xbe-header "$xbe_header" \
    --library "$temporary/libvc_nfl_coach_ref_pose_${label}.so" \
    --label "$label"
done

gcc "${strict[@]}" -O1 -fsanitize=undefined \
  -fno-sanitize-recover=all tests/nfl_coach_ref_pose_test.c \
  "${sources[@]}" -lm -o "$temporary/ubsan-test"
"$temporary/ubsan-test"

rg -q 'PORTME: emulate 0x001C2870' \
  include/recovered/nfl2k5/coach_ref_pose.h
rg -q 'PORTME: prove the live gameplay controller' \
  docs/research/nfl_coach_ref_pose_native.md

echo 'NFL_COACH_REF_POSE_NATIVE_VALIDATION_PASS compilers=2 witness_frames=73 sampled_poses=40 sampled_channels=1000 axis_copies=8'
