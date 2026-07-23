#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

report=reports/assets/apf_player_shadow_skin_semantics.json
vertices=reports/assets/apf_player_shadow_skin_vertices.tsv
joints=reports/assets/apf_player_shadow_skin_joints.tsv
shader=reports/assets/apf_player_shadow_vertex_shader_contract.tsv
trace=reports/assets/apf_player_shadow_skin_semantics_ghidra/player_shadow_skin_palette_trace.txt
pseudo=reports/assets/apf_player_shadow_skin_semantics_ghidra/player_shadow_skin_palette_focused_pseudo_c.c
vmx=reports/assets/apf_player_shadow_skin_semantics_ghidra/player_shadow_skin_palette_vmx128.tsv
doc=docs/research/apf_player_shadow_skin_semantics.md

for required in \
  "$report" "$vertices" "$joints" "$shader" "$trace" "$pseudo" "$vmx" "$doc" \
  tools/apf_player_shadow_skin_semantics.py \
  tools/apf_packed_pose_vmx128_disasm.cpp \
  tools/ghidra_scripts/apf/ApfPlayerShadowSkinPaletteTrace.java \
  tools/apf_outer.py tools/apf_inner.py \
  extracted/'All-Pro Football 2K8 (USA)'/0A \
  extracted/'All-Pro Football 2K8 (USA)'/default.xex \
  reports/assets/apf_scene_inventory.json \
  reports/assets/apf_animation_transform_semantics.json \
  reports/assets/nfl_transform_semantics.json \
  tools/vendor/XenonRecomp/XenonUtils/disasm.cpp \
  tools/vendor/XenonRecomp/XenonUtils/disasm.h \
  tools/vendor/XenonRecomp/thirdparty/disasm/disasm.c \
  tools/vendor/XenonRecomp/thirdparty/disasm/ppc-dis.c; do
  test -f "$required"
done

python3 -m py_compile tools/apf_player_shadow_skin_semantics.py
temporary=$(mktemp -d /tmp/apf-player-shadow-skin.XXXXXX)
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

generate() {
  local seed=$1
  local suffix=$2
  PYTHONHASHSEED=$seed python3 tools/apf_player_shadow_skin_semantics.py \
    --json "$temporary/report-$suffix.json" \
    --vertices-tsv "$temporary/vertices-$suffix.tsv" \
    --joints-tsv "$temporary/joints-$suffix.tsv" \
    --shader-tsv "$temporary/shader-$suffix.tsv"
}

generate 1 one
generate 777 two
cmp "$temporary/report-one.json" "$temporary/report-two.json"
cmp "$temporary/vertices-one.tsv" "$temporary/vertices-two.tsv"
cmp "$temporary/joints-one.tsv" "$temporary/joints-two.tsv"
cmp "$temporary/shader-one.tsv" "$temporary/shader-two.tsv"
cmp "$temporary/report-one.json" "$report"
cmp "$temporary/vertices-one.tsv" "$vertices"
cmp "$temporary/joints-one.tsv" "$joints"
cmp "$temporary/shader-one.tsv" "$shader"

python3 - "$report" "$vertices" "$joints" "$shader" "$trace" "$pseudo" "$vmx" <<'PY'
import csv
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
vertices = list(csv.DictReader(open(sys.argv[2], encoding="utf-8"), delimiter="\t"))
joints = list(csv.DictReader(open(sys.argv[3], encoding="utf-8"), delimiter="\t"))
shader = list(csv.DictReader(open(sys.argv[4], encoding="utf-8"), delimiter="\t"))
trace = open(sys.argv[5], encoding="utf-8").read()
pseudo = open(sys.argv[6], encoding="utf-8").read()
vmx = open(sys.argv[7], encoding="utf-8").read()

assert report["schema"] == "apf_player_shadow_skin_semantics/v1"
assert report["selection"]["outer_table_index"] == 1310
assert report["selection"]["inner_file_index"] == 415
assert report["selection"]["system_size"] == 0x5B80
assert report["selection"]["system_sha256"] == \
    "2042ce844a84a3f4b311bd8554b81744555d3efd6f2e4b5cac6c28a2e0735819"

decision = report["decision"]
for proved in (
    "blendindices_blendweights_decoded_for_every_vertex",
    "palette_order_and_no_remap_proved",
    "bind_current_equation_proved",
    "renderer_descriptor_upload_proved",
    "inverse_bind_matrices_proved",
    "exact_selected_gltf_skin_contract_ready",
    "complete_selected_skinned_gltf_export_ready",
):
    assert decision[proved] is True
assert decision["serialized_stream_flag_to_xenos_endian_symbolized"] is False
assert decision["official_final_xdk_constant_helper_name_proved"] is False
assert len(report["portme"]) == 2
assert report["portme"][0].startswith("// PORTME before 0x84B27AD0")
assert report["portme"][1].startswith("// PORTME at 0x84B24C88 -> 0x84BA45B8")

hierarchy = report["corrected_hierarchy_layout"]
assert hierarchy["count"] == 21
assert hierarchy["table_offset"] == "0x1c00"
assert hierarchy["record_stride"] == "0x30"
assert hierarchy["recursive_global_max_error_cm"] == 0.0

influences = report["vertex_influences"]
assert influences["all_vertex_rows_validated"] == 351
assert influences["stream_flags"] == "0x40000000"
assert influences["used_joints"] == [0, 2, 3, 4, 6, 7, 8, 9, 12, 13, 14, 15, 18, 19, 20]
assert influences["unused_joints"] == [1, 5, 10, 11, 16, 17]
assert influences["palette_row_histogram"] == {
    "0": 28, "6": 23, "9": 21, "12": 37, "18": 23,
    "21": 21, "24": 37, "27": 49, "36": 8, "39": 8,
    "42": 17, "45": 46, "54": 8, "57": 8, "60": 17,
}

palette = report["xex_skin_palette"]
assert palette["palette_builder"]["address"] == "0x84B0E7F0"
assert palette["palette_builder"]["row_vector_equation"] == \
    "skin_row[j] = T(-bind_global[j]) * current_global[j]"
assert palette["palette_builder"]["order"].startswith("direct hierarchy order")
assert palette["descriptor_builder"]["payload_float4_count"] == 63
assert palette["renderer_consumer"]["generic_uploader"].startswith("0x84B27510")

gltf = report["gltf_contract"]
assert gltf["inverse_bind_matrix"] == \
    "column-major T(-bind_global_xyz_cm * 0.01)"
assert gltf["vertex_joints"] == "[palette_row/3,0,0,0]"
assert gltf["vertex_weights"] == "[1,0,0,0]"

assert len(vertices) == 351
assert all(row["raw_blendweights"] == "0,0,0,255" for row in vertices)
assert all(row["fetch_blendweights"] == "1,0,0,0" for row in vertices)
assert all(int(row["palette_row_offset"]) % 3 == 0 for row in vertices)
assert all(int(row["joint"]) == int(row["palette_row_offset"]) // 3 for row in vertices)
assert all(row["gltf_weights_0"] == "1.0,0.0,0.0,0.0" for row in vertices)

assert len(joints) == 21
assert joints[0]["name"] == "root" and joints[0]["parent"] == "-1"
assert joints[-1]["name"] == "r_hand" and joints[-1]["parent"] == "19"
assert all(float(row["recursive_error_cm"]) == 0.0 for row in joints)
assert [int(row["palette_float4_start"]) for row in joints] == list(range(0, 63, 3))

assert len(shader) == 13
assert any(row["source"] == "c40" and row["raw_or_expression"] == "__MATRIX_LIST[216]"
           for row in shader)
assert any(row["meaning"] == "BLENDINDICES0" for row in shader)
assert any(row["meaning"] == "BLENDWEIGHT0" for row in shader)

for needle in (
    "RAW32 0x84B0E7F4 0x81640064",
    "RAW32 0x84B0E880 0x15A069D0",
    "RAW32 0x84B104F4 0x4BFFE2FD",
    "RAW32 0x84B10714 0x93740028",
    "RAW32 0x84B2D4EC 0x808B0028",
    "RAW32 0x84B27548 0x81760004",
    "RAW32 0x84B27B34 0x80E90008",
):
    assert needle in trace
assert "Recovered contract from 0x84B0E7F0" in pseudo
assert "PORTME before 0x84B27AD0" in pseudo
assert "0x84B0E880\t0x15A069D0\tvmsum4fp128\tv13,v0,v13" in vmx
assert "0x84B0E890\t0x19416F10\tvrlimi128\tv10,v13,1,0" in vmx
PY

test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  e25381d9ecd5c9f9c1df5e630a1d34151834c35101ede73c1b990c8bfc2055c2
test "$(sha256sum "$vertices" | cut -d' ' -f1)" = \
  5dba11ffe43e310f84d7b827ba3834aa7e6b1341a3e7b5b1cd4dc7e320c7c222
test "$(sha256sum "$joints" | cut -d' ' -f1)" = \
  5ba183e2d3609136c6a0acfb79f5e1f71f1163e977642c6c7bc760c6991cc87c
test "$(sha256sum "$shader" | cut -d' ' -f1)" = \
  f976631dbc9f71cb3e428bf95037ee065e4b693984f29be95f21e1f9540e8420
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  2e3b301a085bbbfb1ff7f735a05358c222efe14807b540ad440885b07af120c2
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  bb847ca68a6caa6b54fc96995e209e80d0b8e8141af98af607424a3484d6d52d
test "$(sha256sum "$vmx" | cut -d' ' -f1)" = \
  2a95aa846366ef85cc49ade0e14b068ef452c10908d6f64702e4ebeafc45eb57
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  a8648cabe1344af7c5e543eb4f4cf9d005de67b52f60b8cc20bf2eecb6acf840
test "$(wc -l < "$vertices")" -eq 352
test "$(wc -l < "$joints")" -eq 22
test "$(wc -l < "$shader")" -eq 14
test "$(wc -l < "$trace")" -eq 3099
test "$(wc -l < "$pseudo")" -eq 261
test "$(wc -l < "$vmx")" -eq 1530

if [[ "${APF_PLAYER_SHADOW_SKIN_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfPlayerShadowSkinPaletteTrace.java \
        "$temporary/ghidra"
  cmp "$temporary/ghidra/player_shadow_skin_palette_trace.txt" "$trace"
  cmp "$temporary/ghidra/player_shadow_skin_palette_focused_pseudo_c.c" "$pseudo"
  "$temporary/vmx-gcc" \
    "$temporary/ghidra/player_shadow_skin_palette_trace.txt" \
    "$temporary/ghidra-vmx.tsv"
  cmp "$temporary/ghidra-vmx.tsv" "$vmx"
  echo APF_PLAYER_SHADOW_SKIN_GHIDRA_REGEN_PASS
fi

echo "APF_PLAYER_SHADOW_SKIN_SEMANTICS_VALIDATION_PASS compilers=$compiler_count joints=21 vertices=351 used=15 palette_rows=63 ibm=T(-bind) gltf_ready=true"
