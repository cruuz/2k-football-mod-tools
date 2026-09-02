#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

report=reports/assets/apf_animation_transform_semantics.json
root_tsv=reports/assets/apf_animation_transform_root_samples.tsv
trace=reports/assets/apf_animation_transform_semantics_ghidra/animation_transform_semantics_trace.txt
pseudo=reports/assets/apf_animation_transform_semantics_ghidra/animation_transform_semantics_focused_pseudo_c.c
vmx=reports/assets/apf_animation_transform_semantics_ghidra/animation_transform_semantics_vmx128.tsv
doc=docs/research/apf_animation_transform_semantics.md

for required in \
  "$report" "$root_tsv" "$trace" "$pseudo" "$vmx" "$doc" \
  tools/apf_animation_transform_semantics.py \
  tools/apf_packed_pose_vmx128_disasm.cpp \
  tools/ghidra_scripts/apf/ApfAnimationTransformSemanticsTrace.java \
  reports/assets/apf_animation_export_readiness.json \
  reports/assets/apf_packed_pose_decoder_inventory.json \
  reports/assets/apf_mocap_inventory.json \
  reports/assets/apf_mocap_corpus.bin \
  reports/assets/apf_scene_inventory.json \
  reports/assets/motion_lineage_inventory.json \
  reports/assets/nfl_axis_root_motion.json \
  assets/intermediate/nfl2k5/models/0346_0060_shadow_low.gltf \
  tools/vendor/XenonRecomp/XenonRecomp/recompiler.cpp \
  tools/vendor/XenonRecomp/XenonUtils/disasm.cpp \
  tools/vendor/XenonRecomp/thirdparty/disasm/disasm.c \
  tools/vendor/XenonRecomp/thirdparty/disasm/ppc-dis.c; do
  test -f "$required"
done

python3 -m py_compile tools/apf_animation_transform_semantics.py
temporary=$(mktemp -d /tmp/apf-animation-transform-semantics.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

build_vmx_disassembler() {
  local cc=$1
  local cxx=$2
  local label=$3
  "$cc" -std=c11 -O2 -w \
    -Itools/vendor/XenonRecomp/thirdparty/disasm \
    -c tools/vendor/XenonRecomp/thirdparty/disasm/disasm.c \
    -o "$temporary/disasm-$label.o"
  "$cc" -std=c11 -O2 -w \
    -Itools/vendor/XenonRecomp/thirdparty/disasm \
    -c tools/vendor/XenonRecomp/thirdparty/disasm/ppc-dis.c \
    -o "$temporary/ppc-dis-$label.o"
  "$cxx" -std=c++20 -O2 -Wall -Wextra -Wno-unused-function \
    -Itools/vendor/XenonRecomp/XenonUtils \
    -Itools/vendor/XenonRecomp/thirdparty/disasm \
    tools/apf_packed_pose_vmx128_disasm.cpp \
    tools/vendor/XenonRecomp/XenonUtils/disasm.cpp \
    "$temporary/disasm-$label.o" "$temporary/ppc-dis-$label.o" \
    -o "$temporary/vmx-$label"
  "$temporary/vmx-$label" "$trace" "$temporary/vmx-$label.tsv"
  cmp "$temporary/vmx-$label.tsv" "$vmx"
}

build_vmx_disassembler cc c++ gcc
compiler_count=1
if command -v clang-18 >/dev/null 2>&1 && command -v clang++-18 >/dev/null 2>&1; then
  build_vmx_disassembler clang-18 clang++-18 clang
  compiler_count=2
fi

PYTHONHASHSEED=1 python3 tools/apf_animation_transform_semantics.py \
  --json "$temporary/report-1.json" \
  --root-tsv "$temporary/root-1.tsv"
PYTHONHASHSEED=777 python3 tools/apf_animation_transform_semantics.py \
  --json "$temporary/report-2.json" \
  --root-tsv "$temporary/root-2.tsv"
cmp "$temporary/report-1.json" "$temporary/report-2.json"
cmp "$temporary/root-1.tsv" "$temporary/root-2.tsv"
cmp "$temporary/report-1.json" "$report"
cmp "$temporary/root-1.tsv" "$root_tsv"

python3 - "$report" "$root_tsv" "$trace" "$vmx" <<'PY'
import csv
import json
import math
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
rows = list(csv.DictReader(open(sys.argv[2], encoding="utf-8"), delimiter="\t"))
trace = open(sys.argv[3], encoding="utf-8").read()
vmx = open(sys.argv[4], encoding="utf-8").read()

assert report["schema"] == "apf_animation_transform_semantics/v1"
decision = report["decision"]
assert decision["quaternion_lanes_to_gltf_xyzw_proved"] is True
assert decision["apf_axes_handedness_units_proved"] is True
assert decision["selected_root_motion_placement_proved"] is True
assert decision["transform_export_contract_ready"] is True
assert decision["complete_skinned_gltf_export_ready"] is False

quaternion = report["quaternion_to_gltf"]
assert quaternion["gltf_xyzw_equation"] == \
    "rotation = [apf_lane1, apf_lane2, apf_lane3, apf_lane0]"
coverage = quaternion["corpus_validation"]
assert coverage["standard_clip_count"] == 66
assert coverage["mode0_record_count"] == 114563
assert coverage["selected_clip_mode0_record_count"] == 1989
assert coverage["maximum_matrix_equation_absolute_error"] < 1e-12
assert coverage["maximum_mirror_matrix_absolute_error"] == 0.0
assert coverage["maximum_rotation_determinant_error"] < 1e-12

coordinates = report["coordinate_and_unit_contract"]
assert coordinates["handedness"] == "right-handed"
assert coordinates["raw_position_unit"] == "centimeter"
assert coordinates["axes"] == {
    "X": "character lateral; positive X is character-left",
    "Y": "vertical/up",
    "Z": "character/field longitudinal; positive Z is the retained asset-forward side",
}
assert coordinates["gltf_conversion"]["translation"] == \
    "retain XYZ and multiply by 0.01"

root = report["selected_root_trajectory"]
assert root["clip"] == "mnu_stn_01_070130_01_lg"
assert root["sample_count"] == 117 and root["record_stride"] == 6
assert root["mirror"] is False
assert root["raw_minimum"] == [-2, 825, 0]
assert root["raw_maximum"] == [22, 826, 18]
assert root["first_raw"] == [0, 826, 0]
assert root["last_raw"] == [0, 826, 0]
assert root["runtime_duration_interval_cm"] == [-0.03125, 103.25, 0.0]
assert root["external_root_formula"]["translation"] == \
    "external_root.T = float3(slot+0x40) + S * D.xyz"

assert len(rows) == 117
assert rows[0]["raw_x"] == "0" and rows[0]["sample_y_cm"] == "103.25"
assert rows[-1]["frame"] == "116" and rows[-1]["raw_x"] == "0"
assert "RAW32 0x846395C0 0x180867D0" in trace
assert "RAW32 0x84A11CC8 0x4BC27601" in trace
assert "RAW32 0x84A11D00 0x101F58C3" in trace
assert "RAW32 0x84B44E8C 0x4E800020" in trace
assert "0x846395C0\t0x180867D0\tvrlimi128\tv0,v12,8,3" in vmx
assert "0x84A11D00\t0x101F58C3\tlvx128\tv0,r31,r11" in vmx
PY

test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  56be23ac9fef5fcc0c62848a896cd3e9becd8dbd46897e34e7fbeed621ebaa2a
test "$(sha256sum "$root_tsv" | cut -d' ' -f1)" = \
  f47fe3225fcc0d0dff2e5cb17e75d84e76a1ff532d2ea9a3cfc946c5cf6e32c8
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  0a63913f5bf84d383c47e15caa7bba7c4fcd0a20dd00c413f7c18e484b7a1968
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  aafcef939861b0626491543b32a2a06d43002f692e917324fe281b62ab211028
test "$(sha256sum "$vmx" | cut -d' ' -f1)" = \
  004913fa5e0a26016dc6f9e80033dfd1979ad40f057b066b85069d5a455c51ad
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  fa51e9ca658536aa3562c3775d7822bbb37f9131bf654da0e6969b98803470b6
test "$(wc -l < "$root_tsv")" -eq 118
test "$(wc -l < "$vmx")" -eq 780

if [[ "${APF_ANIMATION_TRANSFORM_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfAnimationTransformSemanticsTrace.java \
        "$temporary/ghidra"
  cmp "$temporary/ghidra/animation_transform_semantics_trace.txt" "$trace"
  cmp "$temporary/ghidra/animation_transform_semantics_focused_pseudo_c.c" "$pseudo"
  "$temporary/vmx-gcc" \
    "$temporary/ghidra/animation_transform_semantics_trace.txt" \
    "$temporary/ghidra-vmx.tsv"
  cmp "$temporary/ghidra-vmx.tsv" "$vmx"
  echo APF_ANIMATION_TRANSFORM_GHIDRA_REGEN_PASS
fi

echo "APF_ANIMATION_TRANSFORM_SEMANTICS_VALIDATION_PASS compilers=$compiler_count mode0=114563 selected=1989 root_samples=117 quaternion=lane1,2,3,0 basis=right-handed-Y-up units=cm root=external-parent skin_ready=false"
