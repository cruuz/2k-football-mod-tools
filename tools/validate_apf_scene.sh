#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}
inventory=reports/assets/apf_scene_inventory.json
canonical_probe=reports/assets/apf_scene_glowball_probe.json
canonical_gltf=reports/asset_samples/apf_scene/glowball/glowball.gltf
collection_probe=reports/assets/apf_scene_online_titlebar_probe.json
collection_dir=reports/asset_samples/apf_scene/online_titlebar
collection_gltf=$collection_dir/0899_0021_online_titlebar.gltf
collection_bin=$collection_dir/0899_0021_online_titlebar.bin
collection_manifest=$collection_dir/manifest.json
hi_head_probe=reports/assets/apf_scene_hi_head_probe.json
hi_head_gltf=reports/asset_samples/apf_scene/hi_head/hi_head_position.gltf

test -f "$index"
test -f "$inventory"
test -f "$canonical_probe"
test -f "$canonical_gltf"
test -f "$collection_probe"
test -f "$collection_gltf"
test -f "$collection_bin"
test -f "$collection_manifest"
test -f "$hi_head_probe"
test -f "$hi_head_gltf"
python3 -m py_compile tools/apf_scene.py

temporary=$(mktemp -d /tmp/apf-scene-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 tools/apf_scene.py "$index" \
  --select 137:1 \
  --output "$temporary/glowball.json" \
  --gltf "$temporary/glowball.gltf" \
  --max-decompressed 1048576

cmp "$temporary/glowball.json" "$canonical_probe"
cmp "$temporary/glowball.gltf" "$canonical_gltf"

python3 tools/apf_scene.py "$index" \
  --select 899:21 \
  --output "$temporary/online_titlebar.json" \
  --gltf-dir "$temporary/online_titlebar" \
  --max-decompressed 2097152

cmp "$temporary/online_titlebar.json" "$collection_probe"
cmp "$temporary/online_titlebar/0899_0021_online_titlebar.gltf" "$collection_gltf"
cmp "$temporary/online_titlebar/0899_0021_online_titlebar.bin" "$collection_bin"
cmp "$temporary/online_titlebar/manifest.json" "$collection_manifest"

python3 tools/apf_scene.py "$index" \
  --select 3:1 \
  --output "$temporary/hi_head.json" \
  --gltf "$temporary/hi_head_position.gltf" \
  --max-decompressed 67108864

cmp "$temporary/hi_head.json" "$hi_head_probe"
cmp "$temporary/hi_head_position.gltf" "$hi_head_gltf"

python3 - \
  "$inventory" "$canonical_probe" "$canonical_gltf" \
  "$collection_probe" "$collection_gltf" "$collection_bin" \
  "$collection_manifest" "$hi_head_probe" "$hi_head_gltf" <<'PY'
import base64
import json
from pathlib import Path
import struct
import sys

inventory = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
probe = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
gltf = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
collection_probe = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
collection_gltf = json.loads(Path(sys.argv[5]).read_text(encoding="utf-8"))
collection_blob = Path(sys.argv[6]).read_bytes()
collection_manifest = json.loads(Path(sys.argv[7]).read_text(encoding="utf-8"))
hi_head_probe = json.loads(Path(sys.argv[8]).read_text(encoding="utf-8"))
hi_head_gltf = json.loads(Path(sys.argv[9]).read_text(encoding="utf-8"))

unit_contract = {
    "source_linear_unit": "centimeter",
    "target_linear_unit": "meter",
    "linear_scale": 0.01,
    "applied_as": "root node scale; buffer bytes are unmodified",
    "buffer_space": "serialized_scne_object_space",
    "recipe_note": (
        "A position recipe must be in serialized_scne_object_space. "
        "Coordinates read out of a viewer are metres, so multiply them by "
        "1 / linear_scale before writing a recipe."
    ),
}

summary = inventory["summary"]
expected = {
    "scne_selected": 1303,
    "scne_parsed": 1303,
    "scne_failures": 0,
    "decoded_unique_record_blocks": 783,
    "decoded_block_bytes": 819738940,
    "scene_nodes": 13006,
    "hierarchy_records": 40991,
    "vertex_declarations": 43098,
}
for key, value in expected.items():
    assert summary[key] == value, (key, summary[key], value)
assert summary["position_format_counts"] == {
    "float32x3": 12416,
    "snorm16x4": 365,
    "snorm10_10_10": 225,
}
assert not inventory["failures"]
assert len(inventory["scenes"]) == 1303
assert inventory["constants"]["hierarchy_table_header"] == \
    "none; the table is count * 0x30 records"

nodes = [node for scene in inventory["scenes"] for node in scene["nodes"]]
assert len(nodes) == 13006
assert all(node["mesh_descriptor_count"] == 1 for node in nodes)
assert all(len(node["meshes"]) == 1 for node in nodes)
assert all(node["meshes"][0]["primitive_type"] == 5 for node in nodes)
assert all(node["meshes"][0]["position"]["status"] == "decoded" for node in nodes)
assert sum(node["meshes"][0]["vertex_count"] for node in nodes) == 16217141
assert sum(node["index_count"] for node in nodes) == 24519417
assert {node["index_component_bits"] for node in nodes} == {16, 32}

hierarchies = [node["hierarchy"] for node in nodes]
assert all(hierarchy is not None for hierarchy in hierarchies)
assert sum(hierarchy["count"] for hierarchy in hierarchies) == 40991
assert sum(hierarchy["topology_status"] == "variant" for hierarchy in hierarchies) == 8
assert sum(hierarchy["topology_status"] == "validated" for hierarchy in hierarchies) == 12998
assert all("header_words" not in hierarchy for hierarchy in hierarchies)
assert all(hierarchy["record_offset"] == hierarchy["offset"] for hierarchy in hierarchies)
assert all(hierarchy["byte_length"] == hierarchy["count"] * 0x30
           for hierarchy in hierarchies)
assert all(len(hierarchy["records"]) == hierarchy["count"]
           for hierarchy in hierarchies)
assert all(record["vector_a"] is not None and record["vector_b"] is not None
           for hierarchy in hierarchies for record in hierarchy["records"])

matrix_variants = [
    scene for scene in inventory["scenes"]
    if scene["matrix_nonfinite_component_count"]
]
assert len(matrix_variants) == 49
assert sum(scene["matrix_nonfinite_component_count"] for scene in matrix_variants) == 104
assert summary["scenes_with_portme"] == 57

probe_scene = probe["scenes"][0]
assert probe["summary"]["scne_parsed"] == 1
assert probe_scene["root_name"] == "glowball"
assert probe_scene["system_sha256"] == "20ecf528c6ed06d3dedb35318ff0c1d493e275fda139c4a95c319a0c47e57648"
assert probe_scene["nodes"][0]["name"] == "glowball_plane"
assert probe_scene["nodes"][0]["index_count"] == 4
assert probe_scene["nodes"][0]["meshes"][0]["vertex_count"] == 4

uri = gltf["buffers"][0]["uri"]
prefix = "data:application/octet-stream;base64,"
assert uri.startswith(prefix)
blob = base64.b64decode(uri[len(prefix):], validate=True)
assert len(blob) == gltf["buffers"][0]["byteLength"] == 72
positions = [struct.unpack_from("<3f", blob, i * 12) for i in range(4)]
indices = struct.unpack_from("<6I", blob, 48)
assert indices == (0, 1, 2, 2, 1, 3)
expected_xy = 16.000625610351562
assert positions == [
    (-expected_xy, -expected_xy, 0.0),
    (expected_xy, -expected_xy, 0.0),
    (-expected_xy, expected_xy, 0.0),
    (expected_xy, expected_xy, 0.0),
]
assert gltf["accessors"][0]["count"] == 4
assert gltf["accessors"][1]["count"] == 6
assert gltf["asset"]["extras"]["coordinate_contract"] == unit_contract
assert gltf["scenes"] == [{"nodes": [1]}]
assert len(gltf["nodes"]) == 2
assert gltf["nodes"][0]["extras"] == {
    "raw_coordinates": True, "source_raw_coordinates": True,
}
assert gltf["nodes"][1] == {
    "name": "glowball_plane__centimeters_to_meters",
    "scale": [0.01, 0.01, 0.01],
    "children": [0],
    "extras": {
        "purpose": "unit conversion only; adds no transform of its own",
        "linear_scale": 0.01,
    },
}

assert collection_probe["summary"]["scne_parsed"] == 1
collection_scene = collection_probe["scenes"][0]
assert collection_scene["root_name"] == "online_titlebar"
assert collection_scene["system_sha256"] == \
    "0995143dca153b4c92adb41518b1541a0c11eb913acdda0746238ee39bfd3737"
assert [node["name"] for node in collection_scene["nodes"]] == [
    "TXT_grp", "title_bar_faceButtons_TXT_grp",
]
assert [node["meshes"][0]["vertex_count"] for node in collection_scene["nodes"]] == [3, 3]
assert [node["index_count"] for node in collection_scene["nodes"]] == [3, 3]

assert collection_manifest["schema"] == "apf_static_gltf_manifest/v1"
assert collection_manifest["summary"] == {
    "binary_bytes": 96,
    "exported_scene_count": 1,
    "mesh_count": 2,
    "scene_count": 1,
    "skipped_mesh_count": 0,
    "triangle_count": 2,
    "vertex_count": 6,
    "withheld_scene_count": 0,
}
export = collection_manifest["exports"][0]
assert export["status"] == "exported"
assert export["mesh_count"] == 2 and export["triangle_count"] == 2
assert export["gltf_sha256"] == \
    "d33c3845f9c55c15acde0f12db4c41acf48741fbe96d9b8364c02519701ec97a"
assert export["bin_sha256"] == \
    "24525c2ae1177d2b5e0584cf7b8265d9254d022db1a7b7f7461fea7c22dd2312"
assert all(item.startswith("PORTME:") for item in collection_manifest["portme"])

assert collection_gltf["asset"]["version"] == "2.0"
assert collection_gltf["buffers"] == [
    {"byteLength": 96, "uri": "0899_0021_online_titlebar.bin"}
]
assert collection_gltf["asset"]["extras"]["coordinate_contract"] == unit_contract
assert [node["name"] for node in collection_gltf["nodes"]] == [
    "TXT_grp", "title_bar_faceButtons_TXT_grp",
    "online_titlebar__centimeters_to_meters",
]
assert collection_gltf["scenes"] == [
    {"name": "online_titlebar", "nodes": [2]}
]
assert collection_gltf["nodes"][2]["children"] == [0, 1]
assert collection_gltf["nodes"][2]["scale"] == [0.01, 0.01, 0.01]
assert all(node["extras"]["raw_coordinates"] is True and
           node["extras"]["source_raw_coordinates"] is True
           for node in collection_gltf["nodes"][:2])
assert len(collection_gltf["meshes"]) == 2
assert [accessor["count"] for accessor in collection_gltf["accessors"]] == [3, 3, 3, 3]
assert [accessor["componentType"] for accessor in collection_gltf["accessors"]] == [
    5126, 5125, 5126, 5125,
]
assert len(collection_blob) == 96
assert struct.unpack_from("<3I", collection_blob, 36) == (0, 1, 2)
assert struct.unpack_from("<3I", collection_blob, 84) == (0, 1, 2)
assert not collection_gltf["extras"]["skipped"]
assert all(item.startswith("PORTME:") for item in collection_gltf["extras"]["portme"])

hi_scene = hi_head_probe["scenes"][0]
assert (hi_scene["outer_table_index"], hi_scene["inner_file_index"],
        hi_scene["root_name"]) == (3, 1, "hi_head")
assert hi_scene["nodes"][0]["hierarchy"]["count"] == 61
assert hi_scene["nodes"][0]["hierarchy"]["records"][0]["name"] == "neckThorax"
assert hi_head_gltf["asset"]["extras"]["coordinate_contract"] == unit_contract
assert hi_head_gltf["scenes"] == [{"nodes": [1]}]
assert hi_head_gltf["nodes"][1]["scale"] == [0.01, 0.01, 0.01]
assert hi_head_gltf["nodes"][1]["children"] == [0]

print(
    "APF_SCENE_VALIDATION_PASS "
    "scenes=1303 nodes=13006 hierarchies=40991 "
    "matrix_variants=49 hierarchy_variants=8 collection_meshes=2 units=cm-to-m"
)
PY

if [[ ${APF_SCENE_FULL:-0} == 1 ]]; then
  python3 tools/apf_scene.py "$index" \
    --output "$temporary/full.json" \
    --tsv "$temporary/full.tsv" \
    --max-decompressed 67108864
  cmp "$temporary/full.json" "$inventory"
  cmp "$temporary/full.tsv" reports/assets/apf_scene_inventory.tsv
  echo APF_SCENE_FULL_REGEN_PASS
fi
