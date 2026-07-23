#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
ledger='research/functions/nfl2k5/functions.tsv'
channel_maps='reports/assets/nfl_motion_channel_maps.json'
bone_binding='reports/assets/nfl_bone_binding.json'
rest_orientation='reports/assets/nfl_rest_orientation.json'
motion_sampler='reports/assets/nfl_motion_sampler_inventory.json'
report='reports/assets/nfl_pose_matrix_apply.json'
channels='reports/assets/nfl_pose_matrix_apply_channels.tsv'
witness='reports/assets/nfl_pose_matrix_apply_matrix_witness.tsv'
trace='reports/assets/nfl_pose_matrix_apply_ghidra/nfl_pose_matrix_apply_trace.txt'
pseudo='reports/assets/nfl_pose_matrix_apply_ghidra/nfl_pose_matrix_apply_focused_pseudo_c.c'
doc='docs/research/nfl_pose_matrix_apply.md'

report_sha256='0c7978ea9b60d6e82e598ce3b253cff374ab8c996e1391f422c223c9cc671d8c'
channels_sha256='b14eea15a0389ed32132cf131580a9d9266b9709c7b65763991c582733f9d7f9'
witness_sha256='f205a4cd35a69f61ea183af4cfd8be75574a1c9781abb2a28d168ad4c575cb5d'
trace_sha256='cfff6591df38e88b46a7d2dad07390de71073275b1eec880680cf2b11674d5ba'
pseudo_sha256='ff6443c130efe9c2e8ae1d410b21ae33c884cb9e666e2a481926c1328422a082'

for required in \
  "$xbe" "$xbe_header" "$ledger" "$channel_maps" "$bone_binding" \
  "$rest_orientation" "$motion_sampler" \
  tools/nfl_pose_matrix_apply.py \
  tools/ghidra_scripts/NflPoseMatrixApplyTrace.java \
  "$report" "$channels" "$witness" "$trace" "$pseudo" "$doc"; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_pose_matrix_apply.py

temporary=$(mktemp -d /tmp/nfl-pose-matrix-apply.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_pose_matrix_apply.py \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --ledger "$ledger" \
  --channel-maps "$channel_maps" \
  --bone-binding "$bone_binding" \
  --rest-orientation "$rest_orientation" \
  --motion-sampler "$motion_sampler" \
  --json "$temporary/report.json" \
  --channels-tsv "$temporary/channels.tsv" \
  --witness-tsv "$temporary/witness.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/channels.tsv" "$channels"
cmp "$temporary/witness.tsv" "$witness"

test "$(sha256sum "$report" | cut -d' ' -f1)" = "$report_sha256"
test "$(sha256sum "$channels" | cut -d' ' -f1)" = "$channels_sha256"
test "$(sha256sum "$witness" | cut -d' ' -f1)" = "$witness_sha256"
test "$(sha256sum "$trace" | cut -d' ' -f1)" = "$trace_sha256"
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = "$pseudo_sha256"

python3 - "$report" "$channels" "$witness" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import sys

report_path, channels_path, witness_path, trace_path, pseudo_path, doc_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_pose_matrix_apply/v2"

exe = report["executable"]
assert exe["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert exe["sha256"] == "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
assert len(exe["function_ranges"]) == 34
assert len(exe["raw_ranges"]) == 5
assert all(item["size"] > 0 and len(item["sha256"]) == 64
           for item in exe["function_ranges"] + exe["raw_ranges"])
assert {item["name"] for item in exe["function_ranges"]} >= {
    "skin_palette_builder", "hierarchy_expander", "matrix_multiply",
    "packed_pose_sampler", "cutscene_pose_builder",
    "cutscene_descriptor_constructor", "generic_full_pose_builder",
    "direct_player_vertical_builder", "direct_player_trajectory_builder",
    "player_pose_postprocess", "player_current_matrix_postprocess",
    "quaternion_array_to_matrix",
}
assert exe["jump_tables"] == {
    "apply_dispatch": {
        "raw_hex": "bff9120037f9120070f912009df91200aff91200",
        "targets": [
            "0x0012f9bf", "0x0012f937", "0x0012f970", "0x0012f99d",
            "0x0012f9af",
        ],
        "va": "0x0012fa08",
    },
    "sample_dispatch": {
        "raw_hex": "77f81200c5f71200eff712001df812004bf81200",
        "targets": [
            "0x0012f877", "0x0012f7c5", "0x0012f7ef", "0x0012f81d",
            "0x0012f84b",
        ],
        "va": "0x0012f9f4",
    },
}
assert exe["constants"]["special_player_lane1_origin"]["value"] == 100.0
assert math.isclose(
    exe["constants"]["player_basis_scale_per_byte"]["value"],
    0.012927484698593616,
    rel_tol=0.0,
    abs_tol=0.0,
)

source = report["source_evidence"]
assert set(source) == {
    "channel_maps", "bone_binding", "rest_orientation", "motion_sampler",
}
assert all(len(item["sha256"]) == 64 for item in source.values())
assert report["installed_channel_maps"] == {
    "0x0051cd70": {
        "disabled_logical_channels": [16, 21],
        "enabled_channel_count": 23,
        "raw_hex": "00000105020603070408050106020703080409090a0a0b0b0c0c0d110e120f13ffff1014110d120e130fffff141015161615",
        "sha256": "9d1b0670498bde0a18ee06d0270c1a3e54793638f3671b050b4168636240a0d3",
    },
    "0x0051d010": {
        "disabled_logical_channels": [15, 17, 21, 23],
        "enabled_channel_count": 21,
        "raw_hex": "00000105020603070408050106020703080409090a0a0b0b0c0c0d110e12ffff0f13ffff1014110d120effff130fffff1410",
        "sha256": "39a441532daab4cdbe4ff777641021bc179da9a5a69d43a94cdcb45fcc21e435",
    },
}

descriptor = report["cutscene_descriptor"]
assert descriptor["record_stride"] == 40
assert [item["type"] for item in descriptor["types"]] == [0, 1, 2, 3, 4]
assert [item["name"] for item in descriptor["types"]] == [
    "no_op", "generic", "player", "coach", "referee",
]
assert "loads SCNE name 'cutscene'" in descriptor["constructor"]

contract = report["channel_matrix_contract"]
assert contract["named_row_count"] == 75
assert contract["per_family_channel_count"] == 25
assert contract["logical_slot_equals_pre_postprocess_matrix_index"] is True
assert contract["sampler_output_stride"] == 16
assert contract["matrix_output_stride"] == 64
assert contract["quaternion_layout"] == "scalar-first [w,x,y,z]"
assert "fills every skipped slot" in contract["disabled_channel_rule"]

with channels_path.open(encoding="utf-8", newline="") as stream:
    channels = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(channels) == 75
assert Counter(row["target_family"] for row in channels) == {
    "player": 25, "coach": 25, "referee": 25,
}
assert Counter(int(row["descriptor_type"]) for row in channels) == {
    2: 25, 3: 25, 4: 25,
}
assert Counter(row["final_quaternion_source"] for row in channels) == {
    "sampled": 59,
    "sampled_then_callback_adjusted": 6,
    "callback_synthesized": 6,
    "callback_identity": 4,
}
by_family = defaultdict(dict)
for row in channels:
    family = row["target_family"]
    channel = int(row["logical_channel"])
    assert channel == int(row["matrix_index_before_player_postprocess"])
    assert channel not in by_family[family]
    by_family[family][channel] = row
    assert row["enabled_in_signed_map"] in {"True", "False"}
    if row["enabled_in_signed_map"] == "False":
        assert row["final_quaternion_source"].startswith("callback_")
    assert row["source_detail"]
for family in by_family:
    assert set(by_family[family]) == set(range(25))
assert {channel for channel, row in by_family["player"].items()
        if row["enabled_in_signed_map"] == "False"} == {16, 21}
for family in ("coach", "referee"):
    assert {channel for channel, row in by_family[family].items()
            if row["enabled_in_signed_map"] == "False"} == {15, 17, 21, 23}
assert by_family["player"][16]["bone_name"] == "lwrist"
assert by_family["player"][21]["bone_name"] == "rwrist"
assert by_family["coach"][15]["bone_name"] == "ltwist"
assert by_family["referee"][23]["bone_name"] == "rwrist"

translation = report["translation_contract"]
assert "no sampled per-joint translation curve" in translation["joint_translation"]
assert "intentionally not differenced" in (
    translation["trajectory_difference_0x000df3d0"]["lane_1"]
)
assert "ignores lane4" in translation["cutscene_use"]
assert "subtracts 100" in translation["direct_player_full_use"]

multiply = report["multiplication_contract"]
assert multiply["cutscene_external_root"] == (
    "T(trajectory lanes 0..2) * descriptor[+0x10] * controller[+0x10]"
)
assert multiply["hierarchy"] == (
    "current[i] = local[i] * (current[parent] or external_root)"
)
assert multiply["skin_palette"] == (
    "T(-transform[+0x40].xyz) * current[i]"
)
errors = multiply["matrix_witness"]["errors_against_reversed_orders"]
assert set(errors) == {
    "external_reversed_order_error", "root_parent_left_error",
    "child_parent_left_error",
}
assert min(errors.values()) > 12.0

with witness_path.open(encoding="utf-8", newline="") as stream:
    matrices = list(csv.DictReader(stream, dialect="excel-tab"))
assert [row["stage"] for row in matrices] == [
    "trajectory_translation", "descriptor_root", "controller_root",
    "external_root", "root_local_after_bind_translation", "root_current",
    "child_local_after_bind_translation", "child_current",
]
assert len(matrices) == 8
for row in matrices:
    values = [float(row[f"m{r}{c}"]) for r in range(4) for c in range(4)]
    assert all(math.isfinite(value) for value in values)

assert "never writes a matrix array" in (
    report["query_helper_boundary"]["0x002176d0"]
)
assert "never calls 0x000233c0" in (
    report["query_helper_boundary"]["0x002178e0"]
)
assert report["renderer_boundary"]["render_dispatch"] == (
    "0x00021860 -> 0x000243d0 -> 0x00022c00"
)

expected_portmes = [
    "// PORTME: recover 0x0012F670 switch arms as structured C; the raw trace preserves every instruction.",
    "// PORTME: semantically recover and port every player-proportion adjustment in 0x00092140 and 0x00093850.",
    "// PORTME: model the inactive-coach guard without introducing portable-C uninitialized reads.",
    "// PORTME: prove which runtime object families exercise the direct full-pose builders during football gameplay.",
    "// PORTME: apply the proved XYZ/centimeter contract while preserving each builder's external-root and loop ownership.",
    "// PORTME: do not export player animation until 0x00092140/0x00093850 are value-equivalently ported; coach/referee local rotation export remains separately eligible.",
]
assert report["portme"] == expected_portmes

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
assert trace.count("\nFUNCTION 0x") == 41
assert pseudo.count("/* 0x") == 41
assert "// PORTME: could not decompile function at " not in pseudo
for required in (
    "RANGE 0x0012F670..0x0012FA1B",
    "0x0012F7BE JMP dword ptr [EDX*0x4 + 0x12f9f4]",
    "0x0012F888 CALL 0x003ca3d0",
    "0x0012F90E CALL 0x00031110",
    "0x0012F91F CALL 0x00031110",
    "0x0012F969 CALL 0x000233c0",
    "0x0013047F MOV dword ptr [EAX + 0x14],ECX",
    "0x00130943 CALL 0x00021960",
    "0x0013096E CALL 0x00021970",
    "0x00095FDC MOV dword ptr [EAX],0x3f800000",
    "0x00096AA2 MOV dword ptr [EAX],0x3f800000",
    "0x003432E4 CALL 0x00093800",
    "0x0035B5D8 CALL 0x003ca3d0",
    "0x0035B636 CALL 0x00093800",
    "0x00023460 CALL 0x00031110",
    "0x000246B1 CALL 0x00022c00",
):
    assert required in trace, required
for portme in expected_portmes:
    assert portme in pseudo

doc = doc_path.read_text(encoding="utf-8")
doc_lower = doc.lower()
assert "75 rows" in doc_lower
assert "0x0012f670" in doc_lower and "cutscene" in doc_lower
assert "logical slot `n` is" in doc_lower and "matrix slot `n`" in doc_lower
assert "y = sample(current).y" in doc_lower
assert "0x00092140" in doc_lower and "0x00093850" in doc_lower
assert "no animation was emitted" in doc_lower
for portme in expected_portmes:
    assert portme in doc

print("NFL_POSE_MATRIX_APPLY_JSON_TSV_XBE_GHIDRA_ASSERTIONS_PASS")
PY

if [[ ${NFL_POSE_MATRIX_APPLY_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflPoseMatrixApplyTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_pose_matrix_apply_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_pose_matrix_apply_focused_pseudo_c.c" "$pseudo"
  echo NFL_POSE_MATRIX_APPLY_GHIDRA_REGEN_PASS
fi

echo 'NFL_POSE_MATRIX_APPLY_VALIDATION_PASS functions=34 ghidra_functions=41 named_channels=75 witness_matrices=8'
