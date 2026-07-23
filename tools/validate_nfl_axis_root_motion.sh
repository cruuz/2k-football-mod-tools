#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
motion_inventory='reports/assets/nfl2k5_motion_inventory.json'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
hierarchy='reports/assets/nfl_rest_orientation_hierarchy.tsv'
report='reports/assets/nfl_axis_root_motion.json'
witnesses='reports/assets/nfl_axis_root_motion_witnesses.tsv'
trace='reports/assets/nfl_axis_root_motion_ghidra/nfl_axis_root_motion_trace.txt'
pseudo='reports/assets/nfl_axis_root_motion_ghidra/nfl_axis_root_motion_focused_pseudo_c.c'
doc='docs/research/nfl_axis_root_motion.md'

report_sha256='4276631512d178873be590d2e1fe5f39fad6b138fdee4eec5010d5cb30c5d3c9'
witnesses_sha256='777dcde88208e04fec97091efa83821f48513b668926b1ad55dbe4791d3eb5fe'
trace_sha256='5b308d3d36bd4f67e0f316b04a2d2c58631b15e6d199c8c6550186c40511d0c4'
pseudo_sha256='0dcb055db361c53ca9cbe0201abb1eee58addb6807b1cef46eeaba1f3e5d4830'

for required in \
  "$index" "$motion_inventory" "$xbe" "$xbe_header" "$hierarchy" \
  tools/nfl_axis_root_motion.py tools/nfl_outer.py \
  tools/ghidra_scripts/NflAxisRootMotionTrace.java \
  "$report" "$witnesses" "$trace" "$pseudo" "$doc"; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_axis_root_motion.py tools/nfl_outer.py

temporary=$(mktemp -d /tmp/nfl-axis-root-motion.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_axis_root_motion.py "$index" \
  --motion-inventory "$motion_inventory" \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --hierarchy-tsv "$hierarchy" \
  --json "$temporary/report.json" \
  --witnesses-tsv "$temporary/witnesses.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/witnesses.tsv" "$witnesses"

test "$(sha256sum "$report" | cut -d' ' -f1)" = "$report_sha256"
test "$(sha256sum "$witnesses" | cut -d' ' -f1)" = "$witnesses_sha256"
test "$(sha256sum "$trace" | cut -d' ' -f1)" = "$trace_sha256"
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = "$pseudo_sha256"

python3 - "$report" "$witnesses" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import json
import math
from pathlib import Path
import sys

report_path, witness_path, trace_path, pseudo_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_axis_root_motion/v1"

executable = report["executable"]
assert executable["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert executable["sha256"] == "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
assert len(executable["function_ranges"]) == 18
assert len({item["name"] for item in executable["function_ranges"]}) == 18
assert executable["trajectory_scale"] == {
    "bits": "0x3e000000", "va": "0x004f24e4", "value": 0.125,
}
assert executable["player_root_baseline"]["value"] == 100.0
assert executable["player_root_baseline"]["consumer_instruction"].startswith("0x0035B5E1")
sine = executable["fixed_sine_table"]
assert sine["size"] == 2048 and sine["pair_count"] == 256
assert sine["sha256"] == "51f388051e96e2ba5a159303a9204614c0454b4badd4674f932830a89b441b9c"
assert float(sine["maximum_error_against_binary64_sine"]) < 5.0e-5
assert [item["turn_units"] for item in sine["cardinals"]] == [0, 16384, 32768, 49152]
assert executable["field_strings"] == {
    "0x00e66380": "endzone_north_left",
    "0x00e664f0": "field",
    "0x00e66534": "ticks",
    "0x00e66540": "marks",
}
rectangles = executable["field_rectangles"]
assert [item["name"] for item in rectangles] == [
    "negative_lateral_boundary", "positive_lateral_boundary",
    "positive_longitudinal_boundary", "negative_longitudinal_boundary",
]
assert [item["push_instruction_vas"] for item in rectangles] == [
    ["0x0009be90", "0x0009be95", "0x0009be9a", "0x0009be9f"],
    ["0x0009bea9", "0x0009beae", "0x0009beb3", "0x0009beb8"],
    ["0x0009bec2", "0x0009bec7", "0x0009becc", "0x0009bed1"],
    ["0x0009bedb", "0x0009bee0", "0x0009bee5", "0x0009beea"],
]
for item in rectangles:
    assert float(item["yard_roundtrip_error"]) <= 2.0e-6

trajectory = report["trajectory_corpus"]
assert trajectory["resource_count"] == 5198
assert trajectory["root_count"] == 6068
assert trajectory["record_count"] == 567075
assert trajectory["stride_root_counts"] == {"6": 4263, "8": 1805}
assert trajectory["raw_lane_minimum"] == [-11599, -29, -8900, -11991]
assert trajectory["raw_lane_maximum"] == [7985, 3530, 12287, 10545]
assert trajectory["scaled_position_lane_minimum"] == ["-1449.875", "-3.625", "-1112.5"]
assert trajectory["scaled_position_lane_maximum"] == ["998.125", "441.25", "1535.875"]
assert trajectory["decoded_final_position_minimum"] == ["-1381.625", "0", "-1112.5"]
assert trajectory["decoded_final_position_maximum"] == ["998.125", "420", "1535.875"]
assert trajectory["turn_root_count"] == 1805
assert trajectory["turn_units_per_revolution"] == 65536
assert trajectory["turn_raw_short_unit_turn_units"] == 8
assert float(trajectory["turn_raw_short_unit_degrees"]) == 0.0439453125
assert trajectory["unique_payload_flagless_groups"] == 2850
assert trajectory["identical_payload_mirror_pair_group_count"] == 692
assert trajectory["identical_payload_mirror_pair_occurrence_count"] == 1392
assert trajectory["identical_payload_mirror_cross_product_count"] == 704
assert len(trajectory["named_mirror_witnesses"]) == 12
for item in trajectory["named_mirror_witnesses"]:
    normal = [float(value) for value in item["normal_final"]]
    mirrored = [float(value) for value in item["mirrored_final"]]
    assert mirrored == [-normal[0], normal[1], normal[2]]
    assert item["mirrored_turn_units"] == -item["normal_turn_units"]

bones = report["bone_corpus"]
assert bones["sample_count"] == 5 and bones["row_count"] == 125
assert bones["named_left_right_pair_count"] == 50
assert bones["left_x_greater_than_right_x_count"] == 50
assert float(bones["head_to_foot_span_minimum"]) > 160.0
assert float(bones["head_to_foot_span_maximum"]) < 165.0
for item in bones["witnesses"]:
    assert float(item["left_femur_x"]) > float(item["right_femur_x"])
    assert float(item["head_y"]) > float(item["lowest_foot_y"])
    assert float(item["left_toes_local_z"]) > 0.0
    assert float(item["right_toes_local_z"]) > 0.0

contract = report["proved_contract"]
assert contract["coordinate_axes"] == {
    "X": "field lateral; positive X is character-left in all canonical named skeleton witnesses",
    "Y": "vertical; positive Y points from named feet toward named head",
    "Z": "field longitudinal; positive/negative end signs are not assigned north/south by this trace",
}
assert contract["position_units"] == "centimeters; 1 engine position unit = 0.01 meter"
assert "right-handed" in contract["handedness"]
assert "Y1" in contract["interval_0x000df3d0"]
assert "bone_y+absolute_end_y" in contract["bone_plus_root_0x00218150"]
assert "multiply all position translations by 0.01" in contract["gltf_basis"]
assert len(report["proof_tiers"]["instruction_proof"]) == 8
assert len(report["proof_tiers"]["corpus_corroboration"]) == 5
assert len(report["proof_tiers"]["inference_only"]) == 3

expected_portmes = [
    "// PORTME at 0x000DF3D0: preserve its asymmetric interval contract: X/Z/turn are differences, Y is the absolute end sample.",
    "// PORTME at 0x00304BF0: classify every caller's external parent as model, attachment, camera, or world space before flattening nodes.",
    "// PORTME at 0x00093800: retain caller-supplied external-root ownership; it is not universally world space.",
    "// PORTME: prove scene-node ownership and loop-boundary accumulation before emitting complete glTF root tracks.",
]
assert report["portme"] == expected_portmes

with witness_path.open(encoding="utf-8", newline="") as stream:
    witnesses = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(witnesses) == 33
assert sum(row["kind"] == "instruction_field_rectangle" for row in witnesses) == 4
assert sum(row["kind"] == "corpus_named_skeleton" for row in witnesses) == 5
assert sum(row["kind"] == "corpus_identical_payload_mirror" for row in witnesses) == 12
assert sum(row["kind"] == "corpus_trajectory_endpoint" for row in witnesses) == 12

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
doc = doc_path.read_text(encoding="utf-8")
assert trace.count("\nFUNCTION 0x") == 27
assert pseudo.count("/* 0x") == 27
assert "// PORTME: could not decompile function at" not in pseudo
for required in (
    "0x0009BE90 PUSH 0x45ab7333",
    "0x0009BE9F PUSH 0xc51b04f6",
    "0x0009BFA6 CALL 0x0009b080",
    "0x000DEEB6 FSTP float ptr [EDX]",
    "0x000DEED2 FSTP float ptr [EDX + 0x4]",
    "0x000DEEEF FSTP float ptr [EDX + 0x8]",
    "0x000DF3F2 CALL 0x000dee30",
    "0x000DF410 MOV dword ptr [ESI],EDX",
    "0x000DF417 FSTP float ptr [ESI + 0x8]",
    "0x000DF41A MOV dword ptr [ESI + 0x10],EDX",
    "0x0021817A CALL 0x000df3d0",
    "0x00304B75 CALL 0x000df3d0",
    "0x00304C40 CALL 0x00304700",
    "0x0035B5E1 FSUB float ptr [0x004e5cac]",
    "0x0035B636 CALL 0x00093800",
    "0x00B2B698 refs=",
):
    assert required in trace, required
for required in (
    "param_3[1] = local_3c + local_20;",
    "local_14 + param_3 * *(float *)((int)fVar2 + 0x10)",
    "*(float *)(iVar3 + 0x34) + *(float *)(param_2 + 0x14)",
    "fVar1 = local_1f0 - _DAT_004e5cac;",
):
    assert required in pseudo, required
for portme in expected_portmes:
    assert portme in pseudo
    assert portme in doc
for required in (
    "567,075", "6,068", "right-handed", "0.125 cm", "0.01",
    "absolute Y sample", "692 payload groups", "0x0035B520",
    "camera distance", "Inference",
):
    assert required in doc, required

print("NFL_AXIS_ROOT_MOTION_JSON_TSV_XBE_GHIDRA_ASSERTIONS_PASS")
PY

if [[ ${NFL_AXIS_ROOT_MOTION_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflAxisRootMotionTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_axis_root_motion_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_axis_root_motion_focused_pseudo_c.c" "$pseudo"
  echo NFL_AXIS_ROOT_MOTION_GHIDRA_REGEN_PASS
fi

echo 'NFL_AXIS_ROOT_MOTION_VALIDATION_PASS roots=6068 records=567075 mirror_groups=692 axes=XYZ units=centimeters handedness=right'
