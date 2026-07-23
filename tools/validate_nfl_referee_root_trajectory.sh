#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
inventory='reports/assets/nfl2k5_motion_inventory.json'
ownership='reports/assets/nfl_ref_clip_ownership.json'
axis='reports/assets/nfl_axis_root_motion.json'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
trace_dir='reports/assets/nfl_referee_root_trajectory_ghidra'
trace="$trace_dir/nfl_referee_root_trajectory_trace.txt"
pseudo="$trace_dir/nfl_referee_root_trajectory_focused_pseudo_c.c"
report='reports/assets/nfl_referee_root_trajectory.json'
samples='reports/assets/nfl_referee_root_trajectory_samples.tsv'
doc='docs/research/nfl_referee_root_trajectory.md'

expected_report_sha256='d055c7e435417e15f868ca9f4f5de81325b774015bd85131565576b14fd58bd6'
expected_samples_sha256='faf666e77c117e3379662e152baa496f48c031bb0f40b1f5a746290a97ad4ff6'
expected_trace_sha256='dd8163b99f8f149e24414de6aae3ada96afd18f9e4f17e5e1bff01bd921ed196'
expected_pseudo_sha256='0bdb542236ad4fb6245845cd459419cafe010e71525bb1b3f4c6e71a44eecb5d'

required=(
  "$index" "$inventory" "$ownership" "$axis" "$xbe" "$xbe_header"
  "$trace" "$pseudo" "$report" "$samples" "$doc"
  tools/nfl_referee_root_trajectory.py tools/nfl_outer.py
  tools/ghidra_scripts/NflRefereeRootTrajectoryTrace.java
)
for path in "${required[@]}"; do
  test -f "$path"
done

hash_of() {
  sha256sum "$1" | cut -d ' ' -f 1
}

test "$(hash_of "$report")" = "$expected_report_sha256"
test "$(hash_of "$samples")" = "$expected_samples_sha256"
test "$(hash_of "$trace")" = "$expected_trace_sha256"
test "$(hash_of "$pseudo")" = "$expected_pseudo_sha256"

temporary=$(mktemp -d /tmp/nfl-referee-root-trajectory.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"
python3 -m py_compile tools/nfl_referee_root_trajectory.py tools/nfl_outer.py

PYTHONPATH=tools python3 tools/nfl_referee_root_trajectory.py \
  --json "$temporary/report.json" \
  --samples-tsv "$temporary/samples.tsv"
cmp "$temporary/report.json" "$report"
cmp "$temporary/samples.tsv" "$samples"

python3 - "$report" "$samples" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import json
from pathlib import Path
import sys

report_path, samples_path, trace_path, pseudo_path, doc_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_referee_root_trajectory/v1"

sources = report["sources"]
assert set(sources) == {
    "archive_index", "axis_report", "generator", "ghidra_pseudo_c",
    "ghidra_script", "ghidra_trace", "motion_inventory",
    "ownership_report",
}
assert sources["generator"]["path"] == "tools/nfl_referee_root_trajectory.py"
assert sources["archive_index"]["sha256"] == (
    "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
)
assert sources["ownership_report"]["sha256"] == (
    "17c728da2b25099a9ed1271e4476c9f8ff1ce25daaaff6af2a1ff70b517fc8d3"
)

executable = report["executable"]
assert executable["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert executable["sha256"] == (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
ranges = executable["function_ranges"]
assert len(ranges) == 17
assert len({row["name"] for row in ranges}) == 17
assert sum(row["size"] for row in ranges) == 5511
by_name = {row["name"]: row for row in ranges}
assert by_name["trajectory_sampler"]["sha256"] == (
    "260a3ae8bcf68d7e497aed99b57ff727d94e7dc11bac6bbfb5a5354acaceedec"
)
assert by_name["referee_trajectory_callback"]["sha256"] == (
    "5fa00a474133d7fb286cfe373d104c30d2b641cbbad2a4aed740041ab834c344"
)
assert by_name["live_transform_state_step"]["sha256"] == (
    "7ecfc414ae2d74ab7909a41634adb6584e36bffda75fd0bbeee8c46c930ed85e"
)
assert (
    by_name["controller_fixed_turn_sincos"]["sha256"]
    == by_name["callback_fixed_turn_sincos"]["sha256"]
    == "9d49afda920e19ec04aed9b2bf756a668ab7ce729a451d91e818c8f389eb5509"
)

clip = report["selected_clip"]
assert clip == {
    "body_sha256": "75b67ce8f338943a8cc6bdc46718f61c7c2d9c4945d186983796a090aa31363f",
    "body_size": 4400,
    "chunk_index": 27,
    "chunk_offset": 304128,
    "flags": 2,
    "frame_count": 46,
    "looping": False,
    "mirrored": False,
    "name": "ANM_REF_PENALTY_DELAY_OF_GAME_R",
    "outer_id": "0xda37aa9d",
    "outer_index": 3107,
    "sample_rate_hz": 15,
}

trajectory = report["serialized_trajectory"]
assert trajectory["body_offset"] == 164
assert trajectory["size"] == 368
assert trajectory["sha256"] == (
    "829de7b7999ea1a47401d81b4ccc7bfa042d872614e0ee50c792babdded111fa"
)
assert trajectory["record_stride"] == 8
assert trajectory["record_count"] == 46
assert trajectory["position_scale_cm_per_short"] == 0.125
assert trajectory["turn_units_per_short"] == 8
assert trajectory["turn_units_per_revolution"] == 65536
assert trajectory["packed_lane_summary"] == {
    "turn": {"maximum": 117, "minimum": -12, "unique_count": 38},
    "x": {"maximum": 4, "minimum": -10, "unique_count": 11},
    "y": {"maximum": 874, "minimum": 865, "unique_count": 10},
    "z": {"maximum": 23, "minimum": -11, "unique_count": 27},
}
assert trajectory["first_record"]["packed_y"] == 867
assert trajectory["first_record"]["y_cm"] == "108.375"
assert trajectory["last_serialized_record"]["packed_turn"] == 39
assert trajectory["last_serialized_record"]["turn_units"] == 312

endpoint = trajectory["title_duration_endpoint"]
assert endpoint["duration_raw"] == "0x403ddddf"
assert endpoint["left_frame"] == 44 and endpoint["right_frame"] == 45
assert endpoint["last_serialized_frame_reached_at_title_duration"] is False
assert abs(float(endpoint["sample_frame_position"]) - 44.5000041) < 1e-7
assert endpoint["spatial_cm_before_controller"] == [
    "0.5", "108.25", "1.18749949"
]
assert "0x000DEBD0" in endpoint["turn_quantization"]

with samples_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 46
assert [int(row["frame_index"]) for row in rows] == list(range(46))
assert rows[0]["x_cm"] == "0" and rows[-1]["z_cm"] == "1.125"
assert min(float(row["x_cm"]) for row in rows) == -1.25
assert max(float(row["z_cm"]) for row in rows) == 2.875
assert min(int(row["turn_units"]) for row in rows) == -96
assert max(int(row["turn_units"]) for row in rows) == 936

chain = report["gameplay_instruction_chain"]
assert [row["step"] for row in chain] == list(range(1, 8))
assert [row["function_va"] for row in chain] == [
    "0x002180d0", "0x00218010", "0x002406e0", "0x0031b2e0",
    "0x002cc570", "0x00318310", "0x002cc570",
]
assert chain[3]["xz_rotation"] == {
    "cosine_field": "controller+0x30",
    "sine_field": "controller+0x2c",
    "x_prime": "x*cos + z*sin",
    "z_prime": "z*cos - x*sin",
}
assert chain[4]["writes"]["y"] == "+0x34 = transformed_y"
assert all("instruction" in row["confidence"] for row in chain)

boundary = report["confidence_boundary"]
assert len(boundary["proved"]) == 5
assert len(boundary["unproved"]) == 4
assert boundary["gltf_root_translation_emitted"] is False
assert "do not export raw" in boundary["decision"]
assert len(report["worked"]) == 4
assert len(report["failed"]) == 3
assert len(report["portme"]) == 4
assert all(line.startswith("// PORTME") for line in report["portme"])

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
doc = doc_path.read_text(encoding="utf-8")
assert trace.count("\nFUNCTION 0x") == 17
assert pseudo.count("/* 0x") == 17
assert "// PORTME: could not decompile function at" not in pseudo
for required in (
    "0x00218115 MOV ESI,dword ptr [0x00e60274]",
    "0x00218021 PUSH 0x2cc570",
    "0x0031B391 CALL 0x000df3d0",
    "0x0031B49E CALL dword ptr [ESP + 0x80]",
    "0x002CC5AF CALL 0x00318310",
    "0x002CC5FA MOV dword ptr [ESI + 0x50],ECX",
):
    assert required in trace, required
for token in (
    "selected dynamic one-of-seven actor record",
    "actor scale and heading/facing inputs",
    "final referee render external-root consumer",
):
    assert token in pseudo, token
for portme in report["portme"]:
    assert portme in doc, portme
for token in (
    "46 records", "368 bytes", "44.5000041", "0x0031B2E0",
    "0x002CC570", "0x00318310", "one-of-seven", "not emitted",
):
    assert token in doc, token

print("NFL_REFEREE_ROOT_TRAJECTORY_JSON_TSV_XBE_GHIDRA_ASSERTIONS_PASS")
PY

expect_rejected() {
  local label=$1
  shift
  if "$@" >"$temporary/$label.log" 2>&1; then
    echo "negative test unexpectedly succeeded: $label" >&2
    return 1
  fi
}

jq '.runtime_ownership.specific_pool_record_instance_link_proved = true' \
  "$ownership" >"$temporary/bad-ownership.json"
expect_rejected bad_ownership \
  env PYTHONPATH=tools python3 tools/nfl_referee_root_trajectory.py \
  --ownership "$temporary/bad-ownership.json" \
  --json "$temporary/rejected.json" --samples-tsv "$temporary/rejected.tsv"

jq '.proved_contract.position_units = "meters"' "$axis" \
  >"$temporary/bad-axis.json"
expect_rejected bad_axis \
  env PYTHONPATH=tools python3 tools/nfl_referee_root_trajectory.py \
  --axis-report "$temporary/bad-axis.json" \
  --json "$temporary/rejected.json" --samples-tsv "$temporary/rejected.tsv"

jq '(.resources[] | select(.name == "ANM_REF_PENALTY_DELAY_OF_GAME_R") |
  .packed_regions[] | select(.owner_pointer_field_relative == 40) |
  .sha256) = "bad"' "$inventory" >"$temporary/bad-inventory.json"
expect_rejected bad_inventory \
  env PYTHONPATH=tools python3 tools/nfl_referee_root_trajectory.py \
  --inventory "$temporary/bad-inventory.json" \
  --json "$temporary/rejected.json" --samples-tsv "$temporary/rejected.tsv"

if [[ ${NFL_REFEREE_ROOT_TRAJECTORY_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflRefereeRootTrajectoryTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_referee_root_trajectory_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_referee_root_trajectory_focused_pseudo_c.c" \
      "$pseudo"
fi

echo 'NFL_REFEREE_ROOT_TRAJECTORY_VALIDATION_PASS records=46 functions=17 negative_tests=3 gltf_root_translation_emitted=0'
