#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/All-Pro Football 2K8 (USA)/0A'
inventory='reports/assets/apf_scene_inventory.json'
models='assets/intermediate/apf2k8/models'
manifest="$models/manifest.json"

for required in \
  "$index" "$inventory" "$manifest" tools/apf_scene.py \
  docs/research/apf_static_gltf.md; do
  test -f "$required"
done

python3 -m py_compile \
  tools/apf_scene.py \
  mod_editor/apf_studio/model_export.py \
  mod_editor/apf_studio/model_import.py
test "$(sha256sum "$manifest" | cut -d' ' -f1)" = \
  057a178e93b1dc37e1b6ce94ed8911f339fdf6ed845af58a0ed36dc5abb699f4

python3 - "$inventory" "$manifest" "$models" <<'PY'
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

inventory_path, manifest_path, models = map(Path, sys.argv[1:])
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

assert inventory["schema"] == "apf_scene_inventory/v1"
assert manifest["schema"] == "apf_static_gltf_manifest/v1"
assert manifest["summary"] == {
    "binary_bytes": 333665556,
    "exported_scene_count": 1208,
    "mesh_count": 13006,
    "scene_count": 1303,
    "skipped_mesh_count": 0,
    "triangle_count": 11588322,
    "vertex_count": 16217141,
    "withheld_scene_count": 95,
}
assert all(item.startswith("PORTME:") for item in manifest["portme"])

source_scenes = {
    (
        int(scene["outer_table_index"]),
        int(scene["inner_file_index"]),
        str(scene["root_name"]),
        str(scene["system_sha256"]),
    ): scene
    for scene in inventory["scenes"]
}
assert len(source_scenes) == 1303
exports = manifest["exports"]
assert len(exports) == 1303
assert Counter(item["status"] for item in exports) == {"exported": 1208, "withheld": 95}

actual_files = {path.name for path in models.iterdir() if path.is_file()}
expected_files = {"manifest.json"}
totals = Counter()
seen = set()
for item in exports:
    identity = (
        int(item["outer_table_index"]),
        int(item["inner_file_index"]),
        str(item["root_name"]),
        str(item["system_sha256"]),
    )
    assert identity in source_scenes and identity not in seen
    seen.add(identity)
    source = source_scenes[identity]
    if item["status"] == "withheld":
        assert source["scene_node_count"] == 0
        assert item["portme"] == (
            "PORTME: SCNE contains no non-degenerate static mesh with proved "
            "POSITION/topology"
        )
        assert set(item) == {
            "outer_table_index", "inner_file_index", "root_name",
            "system_sha256", "status", "portme",
        }
        continue

    assert source["scene_node_count"] == item["mesh_count"] > 0
    assert item["skipped_mesh_count"] == 0
    gltf_name = str(item["gltf"])
    bin_name = str(item["bin"])
    assert Path(gltf_name).name == gltf_name and Path(bin_name).name == bin_name
    expected_files.update((gltf_name, bin_name))
    gltf_path = models / gltf_name
    bin_path = models / bin_name
    gltf_bytes = gltf_path.read_bytes()
    binary = bin_path.read_bytes()
    assert hashlib.sha256(gltf_bytes).hexdigest() == item["gltf_sha256"]
    assert hashlib.sha256(binary).hexdigest() == item["bin_sha256"]
    assert len(binary) == item["binary_bytes"]

    document = json.loads(gltf_bytes)
    assert document["asset"]["version"] == "2.0"
    extras = document["asset"]["extras"]
    assert (
        extras["outer_table_index"], extras["inner_file_index"],
        extras["scne_root_name"], extras["system_sha256"],
    ) == identity
    assert document["buffers"] == [{"byteLength": len(binary), "uri": bin_name}]
    assert document["scene"] == 0
    unit_root_index = item["mesh_count"]
    assert document["scenes"] == [
        {"name": identity[2], "nodes": [unit_root_index]}
    ]
    assert len(document["nodes"]) == item["mesh_count"] + 1
    assert len(document["meshes"]) == item["mesh_count"]
    assert len(document["accessors"]) == len(document["bufferViews"]) == 2 * item["mesh_count"]
    assert not document["extras"]["skipped"]
    assert all(value.startswith("PORTME:") for value in document["extras"]["portme"])
    contract = document["asset"]["extras"]["coordinate_contract"]
    assert contract["source_linear_unit"] == "centimeter"
    assert contract["target_linear_unit"] == "meter"
    assert contract["linear_scale"] == 0.01
    assert contract["buffer_space"] == "serialized_scne_object_space"
    unit_root = document["nodes"][unit_root_index]
    assert unit_root == {
        "children": list(range(item["mesh_count"])),
        "extras": {
            "linear_scale": 0.01,
            "purpose": "unit conversion only; adds no transform of its own",
        },
        "name": f"{identity[2]}__centimeters_to_meters",
        "scale": [0.01, 0.01, 0.01],
    }

    cursor = 0
    vertices = 0
    triangles = 0
    for mesh_index, (node, mesh) in enumerate(zip(document["nodes"][:-1], document["meshes"])):
        assert node["mesh"] == mesh_index
        assert node["extras"]["raw_coordinates"] is True
        assert node["extras"]["source_raw_coordinates"] is True
        assert mesh["name"] == node["name"]
        assert mesh["extras"]["source_primitive"] == "D3DPT_TRIANGLESTRIP"
        primitive = mesh["primitives"]
        assert len(primitive) == 1 and primitive[0]["mode"] == 4
        position_index = primitive[0]["attributes"]["POSITION"]
        index_index = primitive[0]["indices"]
        assert (position_index, index_index) == (2 * mesh_index, 2 * mesh_index + 1)
        position = document["accessors"][position_index]
        indices = document["accessors"][index_index]
        assert (position["componentType"], position["type"]) == (5126, "VEC3")
        assert (indices["componentType"], indices["type"]) == (5125, "SCALAR")
        assert indices["count"] % 3 == 0
        assert all(math.isfinite(value) for bounds in (position["min"], position["max"])
                   for value in bounds)
        assert all(low <= high for low, high in zip(position["min"], position["max"]))
        position_view = document["bufferViews"][position["bufferView"]]
        index_view = document["bufferViews"][indices["bufferView"]]
        assert position_view == {
            "buffer": 0, "byteOffset": cursor,
            "byteLength": position["count"] * 12, "target": 34962,
        }
        cursor += position_view["byteLength"]
        assert index_view == {
            "buffer": 0, "byteOffset": cursor,
            "byteLength": indices["count"] * 4, "target": 34963,
        }
        cursor += index_view["byteLength"]
        vertices += position["count"]
        triangles += indices["count"] // 3
    assert cursor == len(binary)
    assert vertices == item["vertex_count"]
    assert triangles == item["triangle_count"]
    totals.update(
        scene_count=1,
        mesh_count=item["mesh_count"],
        vertex_count=vertices,
        triangle_count=triangles,
        binary_bytes=len(binary),
    )

assert seen == set(source_scenes)
assert actual_files == expected_files
assert totals == Counter({
    "scene_count": 1208,
    "mesh_count": 13006,
    "vertex_count": 16217141,
    "triangle_count": 11588322,
    "binary_bytes": 333665556,
})
print(
    "APF_STATIC_GLTF_INVARIANTS_PASS "
    "scenes=1208/1303 meshes=13006 vertices=16217141 triangles=11588322"
)
PY

if [[ ${APF_STATIC_GLTF_REGEN:-0} == 1 ]]; then
  temporary=$(mktemp -d /tmp/apf-static-gltf.XXXXXX)
  trap 'rm -rf "$temporary"' EXIT
  python3 tools/apf_scene.py "$index" \
    --output "$temporary/inventory.json" \
    --gltf-dir "$temporary/models" \
    --max-decompressed 67108864
  cmp "$temporary/inventory.json" "$inventory"
  cmp "$temporary/models/manifest.json" "$manifest"
  while IFS= read -r name; do
    cmp "$temporary/models/$name" "$models/$name"
  done < <(python3 - "$manifest" <<'PY'
import json
from pathlib import Path
import sys
report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for item in report["exports"]:
    if item["status"] == "exported":
        print(item["gltf"])
        print(item["bin"])
PY
  )
  echo APF_STATIC_GLTF_REGEN_PASS
fi

QT_QPA_PLATFORM=offscreen python3 -m unittest -q \
  tests.mod_editor.test_apf_model_export_gui \
  tests.mod_editor.test_apf_model_import

echo 'APF_STATIC_GLTF_VALIDATION_PASS scenes=1208/1303 meshes=13006 vertices=16217141 triangles=11588322 pinned_model_position_import=true'
