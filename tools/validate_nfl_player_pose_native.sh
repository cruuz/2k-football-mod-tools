#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
resource_scan='reports/assets/nfl2k5_resource_chunks_v2.json'
motion_inventory='reports/assets/nfl2k5_motion_inventory.json'
report='reports/assets/nfl_player_pose_native.json'

for required in \
  "$index" "$xbe" "$xbe_header" "$resource_scan" "$motion_inventory" \
  include/recovered/nfl2k5/player_pose.h \
  src/recovered/nfl2k5/player_pose.c \
  include/recovered/nfl2k5/motion_pose_sample.h \
  src/recovered/nfl2k5/motion_pose_sample.c \
  include/recovered/nfl2k5/packed_pose.h \
  src/recovered/nfl2k5/packed_pose.c \
  include/recovered/nfl2k5/quaternion_interpolation.h \
  src/recovered/nfl2k5/quaternion_interpolation.c \
  src/recovered/nfl2k5/quaternion_interpolation_table.inc \
  tests/nfl_player_pose_test.c \
  tools/nfl_player_pose_native_validate.py \
  tools/nfl_coach_ref_pose_native_validate.py \
  tools/nfl_outer.py tools/nfl_scene_probe.py tools/nfl_scne_inventory.py \
  tools/nfl_quaternion_interpolation.py \
  docs/research/nfl_player_pose_native.md; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_player_pose_native_validate.py

temporary=$(mktemp -d /tmp/nfl-player-pose.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$(dirname -- "$report")"

sources=(
  src/recovered/nfl2k5/player_pose.c
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
  "$compiler" "${strict[@]}" tests/nfl_player_pose_test.c \
    "${sources[@]}" -lm -o "$temporary/${label}-test"
  "$temporary/${label}-test"

  "$compiler" "${strict[@]}" -fPIC -shared "${sources[@]}" -lm \
    -o "$temporary/libvc_nfl_player_pose_${label}.so"
  if [[ "$label" == gcc ]]; then
    output_json=$report
  else
    output_json="$temporary/${label}.json"
  fi
  PYTHONPATH=tools python3 tools/nfl_player_pose_native_validate.py \
    --index "$index" \
    --resource-scan "$resource_scan" \
    --motion-inventory "$motion_inventory" \
    --xbe "$xbe" \
    --xbe-header "$xbe_header" \
    --library "$temporary/libvc_nfl_player_pose_${label}.so" \
    --label "$label" \
    --json "$output_json"
done

cmp "$report" "$temporary/clang.json"

gcc "${strict[@]}" -O1 -fsanitize=undefined \
  -fno-sanitize-recover=all tests/nfl_player_pose_test.c \
  "${sources[@]}" -lm -o "$temporary/ubsan-test"
"$temporary/ubsan-test"

python3 - "$report" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_player_pose_native/v1"
assert report["executable"]["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert report["executable"]["player_map"]["disabled_logical_channels"] == [16, 21]
assert report["corpus_axes"]["copy_count"] == 2
assert report["motion_witness"]["name"] == "ANM_CELEBRATE_USER_34"
assert report["motion_witness"]["frame_count"] == 93
assert report["motion_witness"]["packed_channels_per_frame"] == 23
assert report["motion_witness"]["addressed_packed_bytes"] == 8556
assert report["motion_witness"]["zero_slack_bytes"] == 12
assert report["validation"]["poses"] == 22
assert report["validation"]["channels"] == 550
assert report["validation"]["gltf_reorders"] == 550
assert report["validation"]["maximum_lane_error"] <= 3.0e-6
assert report["validation"]["linear_interpolations"] > 0
assert report["validation"]["fixed_slerp_interpolations"] > 0
assert report["validation"]["shortest_path_interpolations"] == 0
assert report["native_contract"]["twist_xbox_bit_exact"] is False
assert len(report["portme"]) == 3
PY

rg -q 'PORTME: emulate 0x001C2530' \
  include/recovered/nfl2k5/player_pose.h
rg -q 'PORTME: attach the proved local pose' \
  docs/research/nfl_player_pose_native.md

echo 'NFL_PLAYER_POSE_NATIVE_VALIDATION_PASS compilers=2 witness_frames=93 poses=22 channels=550 axis_records=2'
