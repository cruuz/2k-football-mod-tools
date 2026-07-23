#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
resource_scan='reports/assets/nfl2k5_resource_chunks_v2.json'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
report='reports/assets/nfl_rest_orientation.json'
hierarchy='reports/assets/nfl_rest_orientation_hierarchy.tsv'
vectors='reports/assets/nfl_rest_orientation_vectors.tsv'
trace='reports/assets/nfl_rest_orientation_ghidra/nfl_rest_orientation_trace.txt'
pseudo='reports/assets/nfl_rest_orientation_ghidra/nfl_rest_orientation_focused_pseudo_c.c'
doc='docs/research/nfl_rest_orientation.md'

report_sha256='c9218125664f53ee915a67dd2c252fd349ecbe9be9a48d9a20fd23b63bce0432'
hierarchy_sha256='aa6af39c22b0865ac77670775e26bba1b4fbecc7cf9a2d62dcbcba382cee6863'
vectors_sha256='a710311f2490bc9f4cdc30bf8301e7cc912590cb5a36d801181976d9f088b015'
trace_sha256='b991dfd902123b984c2083dfa368709b0da1158934e985c93dea38385f6ee951'
pseudo_sha256='67dd9ae586425001cc56dfb22d916599dbe1ba82f4a564d5ced3060dc1b8fa07'

for required in \
  "$index" "$resource_scan" "$xbe" "$xbe_header" \
  tools/nfl_rest_orientation.py tools/nfl_outer.py tools/nfl_scene_probe.py \
  tools/nfl_scne_inventory.py \
  tools/ghidra_scripts/NflRestOrientationTrace.java \
  "$report" "$hierarchy" "$vectors" "$trace" "$pseudo" "$doc"; do
  test -f "$required"
done

python3 -m py_compile \
  tools/nfl_rest_orientation.py tools/nfl_outer.py tools/nfl_scene_probe.py \
  tools/nfl_scne_inventory.py

temporary=$(mktemp -d /tmp/nfl-rest-orientation.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_rest_orientation.py "$index" \
  --resource-scan "$resource_scan" \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --json "$temporary/report.json" \
  --hierarchy-tsv "$temporary/hierarchy.tsv" \
  --vectors-tsv "$temporary/vectors.tsv" \
  --progress-every 0

cmp "$temporary/report.json" "$report"
cmp "$temporary/hierarchy.tsv" "$hierarchy"
cmp "$temporary/vectors.tsv" "$vectors"

test "$(sha256sum "$report" | cut -d' ' -f1)" = "$report_sha256"
test "$(sha256sum "$hierarchy" | cut -d' ' -f1)" = "$hierarchy_sha256"
test "$(sha256sum "$vectors" | cut -d' ' -f1)" = "$vectors_sha256"
test "$(sha256sum "$trace" | cut -d' ' -f1)" = "$trace_sha256"
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = "$pseudo_sha256"

python3 - "$report" "$hierarchy" "$vectors" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import json
import math
from collections import Counter
from pathlib import Path
import sys

report_path, hierarchy_path, vectors_path, trace_path, pseudo_path, doc_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_rest_orientation/v1"

executable = report["executable"]
assert executable["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert executable["sha256"] == "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
assert len(executable["function_ranges"]) == 28
assert {item["name"] for item in executable["function_ranges"]} >= {
    "build_skin_palette", "expand_local_hierarchy", "matrix_multiply_4x4",
    "full_signed_twist", "half_signed_twist", "quaternion_multiply",
    "quaternion_rotate_vector", "quaternion_array_to_matrix",
}
assert {name: item["value"] for name, item in executable["constants"].items()} == {
    "zero": 0.0, "half": 0.5, "one": 1.0, "negative_one": -1.0,
}
tables = executable["twist_name_tables"]
assert [item["name"] for item in tables["player"]["items"]] == [
    "head", "lhand", "rhand",
]
assert [item["name"] for item in tables["coach"]["items"]] == [
    "ltwist", "lwrist", "rtwist", "rwrist",
]
assert [item["name"] for item in tables["referee"]["items"]] == [
    "ltwist", "lwrist", "rtwist", "rwrist",
]
assert tables["player"]["count"] == 3
assert tables["coach"]["count"] == tables["referee"]["count"] == 4

corpus = report["corpus"]
assert corpus["counts"] == {
    "hierarchy_translation_exact_component_count": 330954,
    "nonroot_transform_count": 55352,
    "root_transform_count": 54966,
    "scene_count": 4616,
    "shape_count": 54966,
    "transform_count": 110318,
}
assert corpus["root_count_distribution"] == {"1": 54966}
assert corpus["hierarchy_translation_error_max"] == 0.0
assert corpus["inverse_bind_identity_error_max"] == 0.0
assert corpus["local_rotation_identity_error_max"] == 0.0

quaternions = report["quaternions"]
assert quaternions["component_order"] == "scalar-first [w,x,y,z]"
assert quaternions["multiply"] == "Hamilton product left * right"
assert quaternions["vector_rotation"] == "q * [0,v] * conjugate(q)"
assert quaternions["matrix_layout"].startswith("row-major affine")
assert quaternions["active_axis_count"] == 6
assert quaternions["exact_z_branch_witness_count"] == 1
assert quaternions["pure_twist_vector_count"] == 49
assert quaternions["mixed_rotation_count"] == 42
for key in (
    "pure_full_twist_error_max", "pure_half_squared_error_max",
    "player_full_removal_error_max",
    "coach_ref_half_split_recompose_error_max",
    "quaternion_matrix_rotation_error_max", "mixed_unit_length_error_max",
    "mixed_half_squared_error_max",
):
    assert quaternions[key] <= 1.0e-7, (key, quaternions[key])
assert [(item["family"], item["record_index"], item["transform_name"])
        for item in quaternions["active_axes"]] == [
    ("player", 1, "lhand"), ("player", 2, "rhand"),
    ("coach", 0, "ltwist"), ("coach", 2, "rtwist"),
    ("referee", 0, "ltwist"), ("referee", 2, "rtwist"),
]

root_witness = report["root_space_witness"]
assert root_witness["identity_root_output_translation"] == [3.0, -5.0, 7.0]
assert root_witness["translated_root_output_translation"] == [14.0, 8.0, -10.0]
assert "not intrinsically always model-space" in root_witness["conclusion"]

contract = report["proved_contract"]
assert contract["rest_local_rotation"].startswith("identity quaternion [1,0,0,0]")
assert contract["row_vector_inverse_bind"] == "T(-transform[+0x40].xyz)"
assert contract["row_vector_skin_equation"] == (
    "skin = T(-absolute_bind_translation) * current"
)
assert "external-root-parent space" in contract["current_matrix_space"]
assert "principal quaternion square root" in contract["half_twist_helper"]
assert "no glTF emitted" in contract["gltf_status"]
expected_portmes = [
    "// PORTME: prove the geometric source/target frames of 0x001C2530 and 0x001C2870.",
    "// PORTME: prove model-space versus world-space ownership at every 0x00022C00 caller.",
    "// PORTME: prove vector-lane axes, handedness, units, and root-motion composition.",
    "// PORTME: do not emit skeletal glTF from an incomplete rest-orientation contract.",
]
assert report["portme"] == expected_portmes

with hierarchy_path.open(encoding="utf-8", newline="") as stream:
    hierarchy = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(hierarchy) == 125
assert Counter(row["sample"] for row in hierarchy) == {
    "coach_body": 25, "coach_lod": 25, "player_LO_res": 25,
    "referee_high": 25, "referee_low": 25,
}
for row in hierarchy:
    assert float(row["hierarchy_error"]) == 0.0
    assert float(row["inverse_bind_identity_error"]) == 0.0
    for component in "xyz":
        assert float(row[f"expanded_{component}"]) == float(row[f"absolute_{component}"])

with vectors_path.open(encoding="utf-8", newline="") as stream:
    vectors = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(vectors) == 49
assert Counter(row["family"] for row in vectors) == {
    "player": 14, "coach": 14, "referee": 14, "synthetic": 7,
}
assert {float(row["angle_degrees"]) for row in vectors} == {
    -150.0, -95.0, -25.0, 0.0, 15.0, 60.0, 135.0,
}
for row in vectors:
    for key in (
        "full_expected_error", "half_expected_error", "half_squared_error",
        "player_full_removal_error", "half_split_recompose_error",
        "matrix_rotation_error",
    ):
        assert float(row[key]) <= 1.0e-7, (key, row[key])
    for prefix in ("source", "full", "half"):
        norm = sum(float(row[f"{prefix}_{component}"]) ** 2 for component in "wxyz")
        assert math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=2.0e-8)

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
assert trace.count("\nFUNCTION 0x") == 50
assert pseudo.count("/* 0x") == 50
assert "// PORTME: could not decompile function at " not in pseudo
for required in (
    "FUNCTION 0x000233C0:FUN_000233c0",
    "0x00023460 CALL 0x00031110",
    "0x000246B1 CALL 0x00022c00",
    "0x0009020F CALL 0x001c2530",
    "0x00095B6F CALL 0x001c2870",
    "0x000965BF CALL 0x001c2870",
    "FUNCTION 0x003CA3D0:FUN_003ca3d0",
):
    assert required in trace
for required in (
    "local_20 = (float)piVar3[-5] + local_20;",
    "local_1c = local_1c + (float)piVar3[-4];",
    "local_18 = local_18 + (float)piVar3[-3];",
    "local_140 = &PTR_u_head_004eead4;",
    "local_4 = &PTR_u_ltwist_004efe8c;",
    "local_34 = &PTR_u_ltwist_004eff34;",
    "FUN_003ca1e0(&local_40);",
    "param_3[0xc] = 0.0;",
    "param_3[0xf] = 1.0;",
):
    assert required in pseudo
for portme in expected_portmes:
    assert portme in pseudo

doc = doc_path.read_text(encoding="utf-8")
doc_lower = doc.lower()
assert "110,318" in doc and "330,954" in doc and "54,966" in doc
assert "no skeletal gltf is emitted" in doc_lower
assert "external-root-parent space" in doc_lower
assert "joint local bind rotation is identity" in doc_lower
assert "0x004efe99" in doc_lower and "0x004eff41" in doc_lower and "rwrist" in doc_lower
for portme in expected_portmes:
    assert portme in doc

print("NFL_REST_ORIENTATION_JSON_TSV_XBE_GHIDRA_ASSERTIONS_PASS")
PY

if [[ ${NFL_REST_ORIENTATION_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflRestOrientationTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_rest_orientation_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_rest_orientation_focused_pseudo_c.c" "$pseudo"
  echo NFL_REST_ORIENTATION_GHIDRA_REGEN_PASS
fi

echo 'NFL_REST_ORIENTATION_VALIDATION_PASS scenes=4616 shapes=54966 transforms=110318 vectors=49'
