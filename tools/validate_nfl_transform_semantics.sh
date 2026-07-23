#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
resource_scan='reports/assets/nfl2k5_resource_chunks_v2.json'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
report='reports/assets/nfl_transform_semantics.json'
samples='reports/assets/nfl_transform_semantics_samples.tsv'
influences='reports/assets/nfl_transform_semantics_influences.tsv'
trace='reports/assets/nfl_transform_semantics_ghidra/nfl_transform_semantics_trace.txt'
pseudo='reports/assets/nfl_transform_semantics_ghidra/nfl_transform_semantics_focused_pseudo_c.c'
doc='docs/research/nfl_transform_semantics.md'
cxbx='tools/vendor/Cxbx-Reloaded/src/devices/video/nv2a_vsh.cpp'

report_sha256='9aad54b0215ae84cbc07b178b98b8ae85e15fc7e2d08f389353889f54594ba01'
samples_sha256='863220ed9f6c0d4071af9ecab951d0353207ab4db57a005d37d8f6f2d8fe001a'
influences_sha256='281556c433bb93f03cc1895d5b3eff928d760a42cedbc7dea18ea33802aac63f'
trace_sha256='88d1a591a314e51fd17f7aff952257efe2443db4fea9f6d1ef2f248dc7e0b17f'
pseudo_sha256='8dec09544d3d8b182f8028f37f8d0641f4cc60c6521ca7e852f27d75fbe05e5e'

for required in \
  "$index" "$resource_scan" "$xbe" "$xbe_header" "$cxbx" \
  tools/nfl_transform_semantics.py tools/nfl_outer.py \
  tools/nfl_scene_probe.py tools/nfl_scne_inventory.py tools/nfl_scne_gltf.py \
  tools/ghidra_scripts/NflTransformSemanticsTrace.java \
  "$report" "$samples" "$influences" "$trace" "$pseudo" "$doc"; do
  test -f "$required"
done

python3 -m py_compile \
  tools/nfl_transform_semantics.py tools/nfl_outer.py \
  tools/nfl_scene_probe.py tools/nfl_scne_inventory.py tools/nfl_scne_gltf.py

temporary=$(mktemp -d /tmp/nfl-transform-semantics.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_transform_semantics.py "$index" \
  --resource-scan "$resource_scan" \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --cxbx-vsh "$cxbx" \
  --json "$temporary/report.json" \
  --samples-tsv "$temporary/samples.tsv" \
  --influences-tsv "$temporary/influences.tsv" \
  --progress-every 0

cmp "$temporary/report.json" "$report"
cmp "$temporary/samples.tsv" "$samples"
cmp "$temporary/influences.tsv" "$influences"

test "$(sha256sum "$report" | cut -d' ' -f1)" = "$report_sha256"
test "$(sha256sum "$samples" | cut -d' ' -f1)" = "$samples_sha256"
test "$(sha256sum "$influences" | cut -d' ' -f1)" = "$influences_sha256"
test "$(sha256sum "$trace" | cut -d' ' -f1)" = "$trace_sha256"
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = "$pseudo_sha256"

python3 - "$report" "$samples" "$influences" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import sys

report_path, samples_path, influences_path, trace_path, pseudo_path, doc_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_transform_semantics/v1"
executable = report["executable"]
assert executable["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert len(executable["function_ranges"]) == 27
assert executable["shader_object_count"] == 13
assert executable["shader_arl_a0x_v1x_count"] == 13
for shader in executable["shader_objects"]:
    assert shader["vertex_register_read_counts"]["1"] == 1
    assert set(shader["position_palette_dph_instructions"]) == {"-69", "-68", "-67"}
    assert len(shader["tokens"]) == shader["instruction_count"]

corpus = report["corpus"]
assert corpus["counts"] == {
    "base_transform_count": 110318,
    "coach_transform_copy_count": 72,
    "cpu_blend_record_count": 73803,
    "cross_submesh_mapping_conflict_count": 0,
    "full_palette_shape_count": 54220,
    "ignored_two_source_tail_nonzero_count": 31104,
    "local_delta_bit_exact_component_count": 273490,
    "local_delta_component_count": 330954,
    "local_delta_tolerance_component_count": 57464,
    "nonroot_transform_count": 55352,
    "player_transform_copy_count": 1,
    "referee_transform_copy_count": 2,
    "remapped_palette_shape_count": 746,
    "remapped_submesh_count": 6744,
    "remapped_submesh_unique_vertex_reference_count": 910737,
    "remapped_unreferenced_vertex_count": 0,
    "resolved_selector_vertex_count": 13731388,
    "root_transform_count": 54966,
    "scene_count": 4616,
    "selector_vertex_count": 13731388,
    "serialized_runtime_matrix_prefix_nonzero_count": 34521,
    "serialized_runtime_matrix_prefix_zero_count": 75797,
    "shape_count": 54966,
    "shape_with_cpu_blends_count": 3005,
    "short1_selector_shape_count": 54966,
    "vertex_count": 13731388,
}
assert corpus["cpu_blend_type_counts"] == {"2": 64335, "3": 9468}
assert corpus["resolved_influence_arity_counts"] == {
    "1": 13372190, "2": 328001, "3": 31197,
}
assert sum(corpus["resolved_influence_arity_counts"].values()) == 13731388
assert corpus["active_weight_sum_error_max"] == 8.940696716308594e-08
assert corpus["local_parent_delta_error_max"] == 3.0517578125e-05
assert corpus["selector_min"] == 0 and corpus["selector_max"] == 162
assert corpus["selector_unique_value_count"] == 55
selector_values = {int(value): count for value, count in corpus["selector_value_counts"].items()}
assert set(selector_values) == set(range(0, 163, 3))
assert sum(selector_values.values()) == 13731388
assert corpus["cross_submesh_mapping_conflict_samples"] == []
assert corpus["remapped_unreferenced_vertex_samples"] == []

with samples_path.open(encoding="utf-8", newline="") as stream:
    transforms = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(transforms) == 125
transform_groups = Counter(row["sample"] for row in transforms)
assert transform_groups == {
    "coach_body": 25, "coach_lod": 25, "player_LO_res": 25,
    "referee_high": 25, "referee_low": 25,
}
for row in transforms:
    assert float(row["absolute_w"]) == 1.0
    assert float(row["local_w"]) == 1.0
    assert float(row["maximum_delta_error"]) <= 0.00004

with influences_path.open(encoding="utf-8", newline="") as stream:
    influence_rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(influence_rows) == 11730
influence_groups = Counter(row["sample"] for row in influence_rows)
assert influence_groups == {
    "coach_body": 4151, "coach_lod": 637, "player_LO_res": 5065,
    "referee_high": 1451, "referee_low": 426,
}
seen_vertices = defaultdict(set)
for row in influence_rows:
    selector = int(row["selector_short1"])
    assert selector % 3 == 0
    assert int(row["local_palette_slot"]) == selector // 3
    count = int(row["influence_count"])
    assert count in (1, 2, 3)
    weights = [float(row[f"weight{index}"]) for index in range(count)]
    assert math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=0.000001)
    for index in range(count):
        assert row[f"joint{index}_name"]
        assert 0 <= int(row[f"joint{index}_index"]) < 25
    key = row["sample"]
    vertex = int(row["vertex_index"])
    assert vertex not in seen_vertices[key]
    seen_vertices[key].add(vertex)

contract = report["proved_contract"]
assert contract["absolute_bind_translation_offset"] == "0x40"
assert contract["parent_local_bind_translation_offset"] == "0x50"
assert contract["vertex_selector_equation"] == "local_matrix_slot = v1.x / 3"
assert contract["shader_palette_rows"] == [
    "c[a0.x-69]", "c[a0.x-68]", "c[a0.x-67]",
]
assert len(report["portme"]) == 4

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
assert trace.count("\nFUNCTION 0x") == 28
assert trace.count("\nobject=") == 13
assert "SHADER_OBJECT_TABLE=" in trace
assert pseudo.count("/* 0x") == 28
assert "// PORTME: could not decompile function at " not in pseudo
for required in (
    "/* 0x00021E40:FUN_00021e40 */",
    "/* 0x00021EB0:FUN_00021eb0 */",
    "/* 0x00022A70:FUN_00022a70 */",
    "/* 0x00022C00:FUN_00022c00 */",
    "/* 0x00022F90:FUN_00022f90 */",
    "/* 0x00023690:FUN_00023690 */",
    "/* 0x000236B0:FUN_000236b0 */",
    "/* 0x00023710:FUN_00023710 */",
    "/* 0x00023730:FUN_00023730 */",
    "/* 0x000243D0:FUN_000243d0 */",
    "/* 0x000901E0:FUN_000901e0 */",
    "/* 0x00095B40:FUN_00095b40 */",
    "/* 0x00096590:FUN_00096590 */",
    "/* 0x002176D0:FUN_002176d0 */",
):
    assert required in pseudo
for required in (
    "param_1[0xb] = fVar3 * fVar14 + fVar15 * fVar26;",
    "param_1[0xb] = fVar4 * fVar15 + fVar16 * fVar27 + fVar28 * fVar39;",
    "pfVar10[1] = pfVar1[0xc] - _DAT_00afa360;",
    "iVar9 = iVar9 + 0x1c;",
    "puVar5[3] = -*(float *)(iVar3 + 0x40",
    "return param_1 + 0x50;",
    "(uint)uVar2 + (uint)uVar1 < 0x38",
    "FUN_00022a70(&DAT_00afa710",
):
    assert required in pseudo

doc = doc_path.read_text(encoding="utf-8")
assert "no skeletal gltf is emitted" in doc.lower()
assert "// PORTME: 0x00022c00" in doc
assert "13,731,388" in doc and "73,803" in doc
print("NFL_TRANSFORM_SEMANTICS_JSON_TSV_XBE_SHADER_GHIDRA_ASSERTIONS_PASS")
PY

if [[ ${NFL_TRANSFORM_SEMANTICS_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflTransformSemanticsTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_transform_semantics_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_transform_semantics_focused_pseudo_c.c" "$pseudo"
  echo NFL_TRANSFORM_SEMANTICS_GHIDRA_REGEN_PASS
fi

echo 'NFL_TRANSFORM_SEMANTICS_VALIDATION_PASS scenes=4616 shapes=54966 transforms=110318 blends=73803 vertices=13731388'
