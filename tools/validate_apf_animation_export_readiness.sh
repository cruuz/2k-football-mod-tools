#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

report=reports/assets/apf_animation_export_readiness.json
bindings=reports/assets/apf_animation_export_candidate_bindings.tsv
trace=reports/assets/apf_animation_binding_gap_ghidra/animation_binding_gap_trace.txt
pseudo=reports/assets/apf_animation_binding_gap_ghidra/animation_binding_gap_focused_pseudo_c.c
vmx=reports/assets/apf_animation_binding_gap_ghidra/animation_binding_gap_vmx128.tsv
doc=docs/research/apf_animation_export_readiness.md

for required in \
  "$report" "$bindings" "$trace" "$pseudo" "$vmx" "$doc" \
  tools/apf_animation_export_readiness.py \
  reports/assets/apf_mocap.tsv \
  tools/apf_packed_pose_vmx128_disasm.cpp \
  tools/ghidra_scripts/apf/ApfAnimationBindingGapTrace.java \
  include/recovered/apf2k8/packed_pose.h \
  include/recovered/apf2k8/translation_pose.h \
  src/recovered/apf2k8/translation_pose.c \
  tests/apf_translation_pose_test.c \
  tools/vendor/XenonRecomp/XenonUtils/disasm.cpp \
  tools/vendor/XenonRecomp/thirdparty/disasm/disasm.c \
  tools/vendor/XenonRecomp/thirdparty/disasm/ppc-dis.c; do
  test -f "$required"
done

python3 -m py_compile tools/apf_animation_export_readiness.py
temporary=$(mktemp -d /tmp/apf-animation-export-readiness.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  -Iinclude tests/apf_translation_pose_test.c \
  src/recovered/apf2k8/translation_pose.c -lm \
  -o "$temporary/translation-gcc"
"$temporary/translation-gcc"

if command -v clang-18 >/dev/null 2>&1; then
  clang-18 -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
    -Iinclude tests/apf_translation_pose_test.c \
    src/recovered/apf2k8/translation_pose.c -lm \
    -o "$temporary/translation-clang"
  "$temporary/translation-clang"
fi

cc -std=c11 -O1 -g -Wall -Wextra -Wpedantic -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -Iinclude tests/apf_translation_pose_test.c \
  src/recovered/apf2k8/translation_pose.c -lm \
  -o "$temporary/translation-sanitize"
ASAN_OPTIONS=detect_leaks=1 "$temporary/translation-sanitize"

cc -std=c11 -O2 -w \
  -Itools/vendor/XenonRecomp/thirdparty/disasm \
  -c tools/vendor/XenonRecomp/thirdparty/disasm/disasm.c \
  -o "$temporary/disasm.o"
cc -std=c11 -O2 -w \
  -Itools/vendor/XenonRecomp/thirdparty/disasm \
  -c tools/vendor/XenonRecomp/thirdparty/disasm/ppc-dis.c \
  -o "$temporary/ppc-dis.o"
c++ -std=c++20 -O2 -Wall -Wextra -Wno-unused-function \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/disasm \
  tools/apf_packed_pose_vmx128_disasm.cpp \
  tools/vendor/XenonRecomp/XenonUtils/disasm.cpp \
  "$temporary/disasm.o" "$temporary/ppc-dis.o" \
  -o "$temporary/vmx-disasm"
"$temporary/vmx-disasm" "$trace" "$temporary/vmx.tsv"
cmp "$temporary/vmx.tsv" "$vmx"

python3 tools/apf_animation_export_readiness.py \
  --json "$temporary/report.json" \
  --bindings-tsv "$temporary/bindings.tsv"
cmp "$temporary/report.json" "$report"
cmp "$temporary/bindings.tsv" "$bindings"

python3 - "$report" "$bindings" "$trace" "$vmx" <<'PY'
import csv
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
rows = list(csv.DictReader(open(sys.argv[2], encoding="utf-8"), delimiter="\t"))
trace = open(sys.argv[3], encoding="utf-8").read()
vmx = open(sys.argv[4], encoding="utf-8").read()

assert report["schema"] == "apf_animation_export_readiness/v1"
assert report["program"]["md5"] == "217eea6084c3d03f0f1143802b1f5636"
assert report["selected_clip_candidate"]["name"] == "mnu_stn_01_070130_01_lg"
assert report["selected_clip_candidate"]["packed_motion_length"] == 21528
mode1 = report["mode1_translation_recovery"]
assert mode1["record_count"] == 40434
assert mode1["record_bytes"] == 323472
assert mode1["high_nibble_counts"] == {"0": 40434}
assert mode1["record_stream_sha256"] == "174085f6362345fb659add20d823d7758d8f1c198fbae1849c11af8592307ee4"
assert report["player_shadow_candidate_hierarchy"]["hierarchy_count"] == 21
assert report["player_shadow_candidate_hierarchy"]["mesh_vertex_count"] == 351
assert report["player_shadow_candidate_hierarchy"]["exact_same_named_parent_schema_occurrence_count"] == 52
join = report["conditional_row_join"]
assert join["candidate_named_row_count"] == 21
assert join["active_main_exact_named_binding_count"] == 21
assert len(rows) == 21
assert rows[0]["bone_name"] == "root"
assert rows[20]["bone_name"] == "r_hand"
assert report["decision"]["standard_gltf_animation_export_ready"] is False
assert report["decision"]["export_emitted"] is False
assert report["decision"]["exact_clip_to_named_hierarchy_binding_proved"] is True
assert sum(item["passed"] for item in report["readiness_checks"]) == 8
assert sum(not item["passed"] for item in report["readiness_checks"]) == 4
assert "MAIN_SECONDARY_MAP3_FIRST23_EQUAL true" in trace
assert "MAIN_SECONDARY_MAP2_FIRST21_EQUAL true" in trace
assert "RAW32 0x84AA4768 0x937E0C20" in trace
assert "RAW32 0x820DBD00 0x60900D71" in trace
assert "RAW32 0x84A1234C 0x60C61BF8" in trace
assert "RAW32 0x84A11B8C 0x7F5F582E" in trace
assert "RAW32 0x84A11C24 0x38A00015" in trace
assert "RAW32 0x84A11D60 0x48092529" in trace
assert "0x8463A57C\t0x10166B4A\tvcfsx\tv0,v13,22" in vmx
assert "0x8463A594\t0x1400DB13\tvxor128\tv0,v0,v123" in vmx
PY

test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  57d91d88da33efa10e953de8fba77411951c74076ca1e401d93b462f730f2594
test "$(sha256sum "$bindings" | cut -d' ' -f1)" = \
  14e8850139cf3c7ddddad83a749fe5eae25400c819bc52fbffdc0bf1c48d6d13
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  2a96e86a1f4a80844c7c1105e8d4b1bed37c4959fe8c5a9e472c2d622db1f08a
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  696a5f2cf664c6b3bbc88a519f67370a269ea3c3119c7a1d456e732e514f8b95
test "$(sha256sum "$vmx" | cut -d' ' -f1)" = \
  74d9c3e8a65ade52b2a9ab2816a7b454aaf5e9dc568d716467d9eef356c351dc
test "$(wc -l < "$bindings")" -eq 22
test "$(wc -l < "$vmx")" -eq 1027

if [[ "${APF_ANIMATION_BINDING_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfAnimationBindingGapTrace.java \
        "$temporary/ghidra" "$root/reports/assets/apf_mocap.tsv"
  cmp "$temporary/ghidra/animation_binding_gap_trace.txt" "$trace"
  cmp "$temporary/ghidra/animation_binding_gap_focused_pseudo_c.c" "$pseudo"
  "$temporary/vmx-disasm" \
    "$temporary/ghidra/animation_binding_gap_trace.txt" \
    "$temporary/ghidra-vmx.tsv"
  cmp "$temporary/ghidra-vmx.tsv" "$vmx"
  echo APF_ANIMATION_BINDING_GHIDRA_REGEN_PASS
fi

echo 'APF_ANIMATION_EXPORT_READINESS_VALIDATION_PASS clip=mnu_stn_01_070130_01_lg hierarchy=player_shadow mode1=40434 rows=21 binding_exact=true export_ready=false'
