#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
report='reports/assets/nfl_normshort3_positions.json'
trace='reports/assets/nfl_normshort3_positions_ghidra/normshort3_trace.txt'
pseudo='reports/assets/nfl_normshort3_positions_ghidra/normshort3_focused_pseudo_c.c'

for required in \
  "$xbe" reports/headers/nfl2k5_xbe_header.json \
  'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  reports/assets/nfl2k5_resource_chunks_v2.json \
  reports/assets/nfl2k5_scne_shapes.tsv \
  reports/assets/nfl2k5_scne_submeshes.tsv \
  tools/vendor/Cxbx-Reloaded/src/core/hle/D3D8/XbVertexBuffer.cpp \
  tools/vendor/Cxbx-Reloaded/src/devices/video/nv2a_vsh.cpp \
  tools/nfl_normshort3_positions.py \
  tools/ghidra_scripts/NflNormshort3Trace.java \
  docs/research/nfl_normshort3_positions.md \
  "$report" "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_normshort3_positions.py
temporary=$(mktemp -d /tmp/nfl-normshort3-positions.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_normshort3_positions.py \
  --json "$temporary/nfl_normshort3_positions.json" >/dev/null
cmp "$temporary/nfl_normshort3_positions.json" "$report"

test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  50a60ebf8ac8bc6d70a4239356f08851bfa444b224607e1b1dd411e3a7208068
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  906698aed8a2d6956db0837334235548d68be39dea7db33a5e6023e9402a3fa3
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  c7575dfe7a8245a4c922a20a4baf1e7fb26e801aa18d584f4d9117b69eca1357

python3 - "$report" "$trace" "$pseudo" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

report_path, trace_path, pseudo_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_normshort3_positions/v1"
assert report["executable"] == {
    "md5": "444064a9ec984dd29d2c05a43f5c96e8",
    "path": "extracted/ESPN NFL 2K5 (USA)/default.xbe",
    "sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
}
assert report["shape_relocator"] == {
    "function_va": "0x00022f90",
    "serialized_to_runtime": {
        "+0x10": "+0x1c / c[-88].w",
        "+0x20": "+0x10 / c[-88].x",
        "+0x24": "+0x14 / c[-88].y",
        "+0x28": "+0x18 / c[-88].z",
    },
    "shuffle_va": "0x00022faa",
    "window_sha256": "218c230b483e3fe1134cfe58e37a655f9ec4463d0b20de27a634768ffc9a4668",
    "window_size": 64,
    "window_va": "0x00022f90",
}
upload = report["render_upload"]
assert upload["function_va"] == "0x000243d0"
assert upload["sequence_va"] == "0x000245fd"
assert upload["sequence_size"] == 58
assert upload["sequence_sha256"] == "a5702bec9be4d48103e9f266cde325565369219f1a28ed6523d7dfd18fe17ac7"
assert upload["push_words"] == [
    "0x00041ea4", "0x00000008", "0x00100b80", "shape +0x10..+0x1c",
]

shaders = report["static_vertex_shaders"]
assert shaders["object_first_va"] == "0x00a6c540"
assert shaders["object_stride"] == 32 and shaders["object_count"] == 13
assert shaders["object_table_sha256"] == "4fb91f389ca0d6b3f33121d383dd52353d18f051cc5e26dc9c2d082e126b03cd"
common = shaders["common_instruction_1"]
assert common["words"] == [
    "0x00000000", "0x0081001a", "0x09ff186a", "0x3e400000",
]
assert common["native_constant_register"] == -88
assert common["disassembly"] == "MAD r4.xyz, v0.xyzz, c[-88].wwww, c[-88].xyzz"
assert common["equation"] == "r4.xyz = v0.xyz * c[-88].w + c[-88].xyz"
assert [item["index"] for item in shaders["objects"]] == list(range(13))
assert [item["object_va"] for item in shaders["objects"]] == [
    f"0x{0x00A6C540 + index * 0x20:08x}" for index in range(13)
]
assert all(item["version"] == "0x2078" for item in shaders["objects"])
assert all(item["instruction_1_words"] == common["words"] for item in shaders["objects"])

assert report["xbox_normshort3"]["equation"] == (
    "n = value / 32767 for value >= 0; value / 32768 for value < 0"
)
assert report["xbox_normshort3"]["cxbx_commit"] == (
    "585c49a50af1255ab155099e06f24505f9c5a800"
)
assert report["corpus"] == {
    "nonempty_scene_count": 4007,
    "primitive_count": 276642,
    "register_zero_format_counts": {"FLOAT3": 46192, "NORMSHORT3": 8774},
    "scene_count": 4616,
    "shape_count": 54966,
    "vertex_count": 13731388,
    "zero_shape_scene_count": 609,
}
sample = report["worked_sample"]
assert (
    sample["scene_index"], sample["outer_index"], sample["chunk_index"],
    sample["scene_name"], sample["shape_index"], sample["shape_name"],
) == (0, 3, 51, "geometry_font", 0, "A")
assert sample["vertex_count"] == 74
assert sample["scale"] == 54.10799789428711
assert sample["offset"] == [32.485633850097656, 54.0, 0.0]
assert sample["runtime_c_minus_88"] == [
    32.485633850097656, 54.0, 0.0, 54.10799789428711,
]
assert sample["raw_component_min"] == [-19673, -32702, 0]
assert sample["raw_component_max"] == [19673, 32702, 0]
assert sample["decoded_float3_sha256"] == (
    "ca048a5cb2cc328ebe04a1b273f02107054d7af81dc800b33b30400b9859ca35"
)
assert sample["decoded_min"] == [0.0006899238796904683, 0.0009842792060226202, 0.0]
assert sample["decoded_max"] == [64.97156524658203, 108.00066375732422, 0.0]

trace = trace_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "0x00022FAA FLD float ptr [ECX + 0x20] owner=0x00022F90:FUN_00022f90",
    "0x00022FAD MOV EDX,dword ptr [ECX + 0x10] owner=0x00022F90:FUN_00022f90",
    "0x00022FB0 FSTP float ptr [ECX + 0x10] owner=0x00022F90:FUN_00022f90",
    "0x00022FB6 MOV dword ptr [ECX + 0x1c],EDX owner=0x00022F90:FUN_00022f90",
    "0x0002460B MOV dword ptr [EAX],0x41ea4 owner=0x000243D0:FUN_000243d0",
    "0x00024611 MOV dword ptr [EAX + 0x4],0x8 owner=0x000243D0:FUN_000243d0",
    "0x00024618 MOV dword ptr [EAX + 0x8],0x100b80 owner=0x000243D0:FUN_000243d0",
    "object=12 va=0x00A6C6C0 declaration=0x03F00077 version=0x2078 instruction_count=26 program=0x00A6B3A0 instruction_1=00000000 0081001A 09FF186A 3E400000",
    "MAD r4.xyz, v0.xyzz, c[-88].wwww, c[-88].xyzz",
):
    assert exact in trace, exact
assert trace.count(" instruction_1=00000000 0081001A 09FF186A 3E400000") == 13

pseudo = pseudo_path.read_text(encoding="utf-8")
assert pseudo.count("/* 0x") == 2
assert "// PORTME: could not decompile function at " not in pseudo
for exact in (
    "*(undefined4 *)(param_1 + 0x10) = *(undefined4 *)(param_1 + 0x20);",
    "*(undefined4 *)(param_1 + 0x1c) = uVar1;",
    "*(undefined4 *)(param_1 + 0x14) = *(undefined4 *)(param_1 + 0x24);",
    "*(undefined4 *)(param_1 + 0x18) = *(undefined4 *)(param_1 + 0x28);",
    "*puVar9 = 0x41ea4;",
    "puVar9[1] = 8;",
    "puVar9[2] = 0x100b80;",
    "puVar9[6] = *(undefined4 *)(param_1 + 0x1c);",
):
    assert exact in pseudo, exact

print("NFL_NORMSHORT3_POSITIONS_JSON_XBE_GHIDRA_ASSERTIONS_PASS")
PY

if [[ ${NFL_NORMSHORT3_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflNormshort3Trace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/normshort3_trace.txt" "$trace"
  cmp "$temporary/ghidra/normshort3_focused_pseudo_c.c" "$pseudo"
  echo NFL_NORMSHORT3_POSITIONS_GHIDRA_REGEN_PASS
fi

echo 'NFL_NORMSHORT3_POSITIONS_VALIDATION_PASS shaders=13 shapes=8774 sample=A:74'
