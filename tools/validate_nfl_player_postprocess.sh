#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

temporary=$(mktemp -d /tmp/nfl-player-postprocess-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
report='reports/assets/nfl_player_postprocess.json'
transforms='reports/assets/nfl_player_postprocess_transforms.tsv'
writes='reports/assets/nfl_player_postprocess_writes.tsv'
calls='reports/assets/nfl_player_postprocess_calls.tsv'
constants='reports/assets/nfl_player_postprocess_constants.tsv'
trace='reports/assets/nfl_player_postprocess_ghidra/nfl_player_postprocess_trace.txt'
pseudo='reports/assets/nfl_player_postprocess_ghidra/nfl_player_postprocess_focused_pseudo_c.c'
doc='docs/research/nfl_player_postprocess.md'

test "$(md5sum "$xbe" | cut -d' ' -f1)" = '444064a9ec984dd29d2c05a43f5c96e8'

PYTHONPATH=tools python3 -m py_compile \
  tools/nfl_player_postprocess.py \
  tools/nfl_player_current_postprocess_native_validate.py

PYTHONPATH=tools python3 tools/nfl_player_postprocess.py \
  --json "$temporary/nfl_player_postprocess.json" \
  --transforms-tsv "$temporary/nfl_player_postprocess_transforms.tsv" \
  --writes-tsv "$temporary/nfl_player_postprocess_writes.tsv" \
  --calls-tsv "$temporary/nfl_player_postprocess_calls.tsv" \
  --constants-tsv "$temporary/nfl_player_postprocess_constants.tsv"

cmp "$temporary/nfl_player_postprocess.json" "$report"
cmp "$temporary/nfl_player_postprocess_transforms.tsv" "$transforms"
cmp "$temporary/nfl_player_postprocess_writes.tsv" "$writes"
cmp "$temporary/nfl_player_postprocess_calls.tsv" "$calls"
cmp "$temporary/nfl_player_postprocess_constants.tsv" "$constants"
echo NFL_PLAYER_POSTPROCESS_REGEN_PASS

python3 - "$report" "$transforms" "$writes" "$calls" "$constants" "$trace" "$pseudo" "$doc" <<'PY'
import csv
from collections import Counter
import json
from pathlib import Path
import sys

(
    report_path, transforms_path, writes_path, calls_path,
    constants_path, trace_path, pseudo_path, doc_path,
) = map(Path, sys.argv[1:])

report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_player_postprocess/v1"
assert report["executable"]["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert report["ghidra"]["focused_function_count"] == 33
assert report["counts"] == {
    "constant_rows": 1146,
    "direct_current_callers": 8,
    "high_transforms": 62,
    "low_transforms": 25,
    "ordered_call_rows": 265,
    "persistent_write_rows": 154,
    "skel_vectors": 25,
}

functions = {row["start"]: row for row in report["executable"]["functions"]}
expected_targets = {
    "0x00092140": (5814, "27d5220ca131c3f41d5c40e8a715fa6386d7d5fb50c1618ff0abf3ac7dffcacb"),
    "0x00093800": (73, "cf008441aa4b2bfb1308df4c4ef6df410bbd2dc3d4fcc954b6ec95ea813ef4fd"),
    "0x00093850": (745, "e8328476d6c3282ed48f9729f790068334a846c41e7dfd6d1043e5d7087d8d5f"),
}
for address, (size, digest) in expected_targets.items():
    assert functions[address]["size"] == size
    assert functions[address]["sha256"] == digest
assert report["matrix_contract"]["all_high_matrices_have_a_local_writer"] is True
assert report["matrix_contract"]["all_high_matrices_have_a_current_scale_source"] is True
assert len(report["runtime_inputs"]) == 8
assert report["function_0x00092140"]["portable_status"].endswith("PORTME")
assert report["function_0x00092140"]["condition_count"] == 21
assert len(report["function_0x00092140"]["conditions"]) == 10
assert "high[j] = high[j] * pivot_scale" in report["function_0x00093850"]["high_loop"]
assert len(report["function_0x00093850"]["profiles"]) == 4
assert len(report["function_0x00093850"]["skel_vectors"]) == 25
assert len(report["function_0x00093850"]["conditions"]) == 9
assert [row["reference"] for row in report["function_0x00093850"]["profiles"]] == [180.0, 190.0, 240.0, 280.0]
assert [row["multiplier"] for row in report["function_0x00093850"]["profiles"]] == [
    0.01666666753590107, 0.019999999552965164,
    0.019999999552965164, 0.014285714365541935,
]
callers = {row["callsite"]: row for row in report["function_0x00093850"]["direct_callers"]}
assert len(callers) == 8
assert callers["0x001dfadf"]["enabled_names"] == "neck,head"
assert callers["0x0028e99d"]["enabled_count"] == 23
assert "neck" not in callers["0x0028e99d"]["enabled_names"].split(",")
assert "head" not in callers["0x0028e99d"]["enabled_names"].split(",")

def tsv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))

transform_rows = tsv(transforms_path)
assert len(transform_rows) == 62
assert [int(row["high_index"]) for row in transform_rows] == list(range(62))
assert transform_rows[0]["high_name"] == "root"
assert transform_rows[37]["high_name"] == "lhand"
assert transform_rows[51]["high_name"] == "rhand"
assert transform_rows[61]["high_name"] == "l_gluteus_muscle_2"
assert {row["initial_low_name"] for row in transform_rows if row["initial_low_name"]} == {
    "root", "lfemur", "ltibia", "lfoot", "ltoes",
    "rfemur", "rtibia", "rfoot", "rtoes", "waist", "thorax",
    "neck", "head", "lcollar", "lhumerus", "lelbow", "lhand",
    "rcollar", "rhumerus", "relbow", "rhand", "lshoulderpad", "rshoulderpad",
}
assert all(row["local_final_writer"] for row in transform_rows)
assert all(0 <= int(row["current_scale_source_index"]) < 25 for row in transform_rows)

write_rows = tsv(writes_path)
assert len(write_rows) == 154
assert Counter(row["phase"] for row in write_rows) == {
    "local_name_remap": 25,
    "local_auxiliary_or_adjustment": 41,
    "current_low_axis_scale": 25,
    "current_high_pivot_scale": 62,
    "conditional_low_head_basis_scale": 1,
}
remaps = [row for row in write_rows if row["phase"] == "local_name_remap"]
skips = [row for row in remaps if row["destination_index"] == ""]
assert [(row["source_index"], row["source_name"]) for row in skips] == [
    ("16", "lwrist"), ("21", "rwrist")
]
assert {int(row["destination_index"]) for row in write_rows if row["phase"] == "current_high_pivot_scale"} == set(range(62))
head_rows = [row for row in write_rows if row["phase"] == "conditional_low_head_basis_scale"]
assert len(head_rows) == 1 and head_rows[0]["destination_name"] == "head"

call_rows = tsv(calls_path)
assert len(call_rows) == 265
assert Counter(row["owner"] for row in call_rows)["0x00092140"] == 127
assert Counter(row["owner"] for row in call_rows)["0x00093800"] == 4
assert Counter(row["owner"] for row in call_rows)["0x00093850"] == 7
switch = [row for row in call_rows if row["callsite"] in ("0x0012f97b", "0x0012f996")]
assert len(switch) == 2
assert all(row["owner_scope"] == "direct_caller_raw_switch_arm" for row in switch)
for owner, rows in __import__("itertools").groupby(call_rows, key=lambda row: row["owner"]):
    grouped = list(rows)
    assert [int(row["sequence"]) for row in grouped] == list(range(1, len(grouped) + 1)), owner
    assert [int(row["callsite"], 16) for row in grouped] == sorted(int(row["callsite"], 16) for row in grouped)

constant_rows = tsv(constants_path)
assert len(constant_rows) == 1146
categories = Counter(row["category"] for row in constant_rows)
assert categories == {
    "fixed_angle_lut_f32": 512,
    "signed_angle_coefficients_f32": 6,
    "projection_clamp_f32": 1,
    "common_zero_half_one_f32": 2,
    "common_one_f32": 1,
    "angle_scale_f32": 1,
    "blend_scale_f32": 1,
    "lower_clamp_f32": 1,
    "current_scale_profiles_f32": 208,
    "current_high_schedule_u8": 62,
    "local_postprocess_constants_f32": 351,
}
by_va = {row["va"]: row for row in constant_rows}
assert by_va["0x004efe54"]["bits"] == "0x3ff33333"
assert by_va["0x004efe58"]["value"] == "450"
assert by_va["0x004e88e4"]["value"] == "150"
assert report["constants"]["ranges"][0]["sha256"] == "51f388051e96e2ba5a159303a9204614c0454b4badd4674f932830a89b441b9c"

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
assert "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8" in trace
assert "RANGE 0x00092140..0x000937F5" in trace
assert "RANGE 0x00093850..0x00093B38" in trace
assert "DATA 0x004E53E8..0x004E5BE7" in trace
assert "0x0012F996 CALL 0x00093850" in trace
assert "0x00093A4E CALL 0x00031110" in trace
assert "PORTME: could not decompile function" not in pseudo

doc = doc_path.read_text(encoding="utf-8")
assert "116-case numeric oracle" in doc
assert "all 62 indices" in doc.lower()
assert "right multiplication" in doc.lower()
assert "no player animation was exported" in doc.lower()
for portme in report["portme"]:
    assert portme in doc
    assert portme in pseudo

print("NFL_PLAYER_POSTPROCESS_JSON_TSV_GHIDRA_ASSERTIONS_PASS")
PY

gcc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  -Iinclude \
  src/recovered/nfl2k5/player_current_postprocess.c \
  tests/nfl_player_current_postprocess_test.c \
  -lm -o "$temporary/player-current-gcc"
"$temporary/player-current-gcc"

clang-18 -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  -Iinclude \
  src/recovered/nfl2k5/player_current_postprocess.c \
  tests/nfl_player_current_postprocess_test.c \
  -lm -o "$temporary/player-current-clang"
"$temporary/player-current-clang"

gcc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -fPIC -shared \
  -Iinclude src/recovered/nfl2k5/player_current_postprocess.c \
  -lm -o "$temporary/libplayer-current.so"
PYTHONPATH=tools python3 tools/nfl_player_current_postprocess_native_validate.py \
  --library "$temporary/libplayer-current.so"

if [[ ${NFL_PLAYER_POSTPROCESS_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflPlayerPostprocessTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_player_postprocess_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_player_postprocess_focused_pseudo_c.c" "$pseudo"
  echo NFL_PLAYER_POSTPROCESS_GHIDRA_REGEN_PASS
fi

echo 'NFL_PLAYER_POSTPROCESS_VALIDATION_PASS low=25 high=62 writes=154 calls=265 constants=1146 native_cases=116'
