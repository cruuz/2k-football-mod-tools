#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${NFL2K5_INDEX:-'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'}
models='assets/intermediate/nfl2k5/models'
manifest="$models/manifest.json"
sample='reports/asset_samples/nfl_static_gltf'

for required in \
  "$index" "$manifest" \
  reports/assets/nfl2k5_resource_chunks_v2.json \
  reports/assets/nfl2k5_scne_inventory.json \
  reports/assets/nfl2k5_scne_shapes.tsv \
  reports/assets/nfl2k5_scne_submeshes.tsv \
  reports/assets/nfl_normshort3_positions.json \
  reports/assets/nfl2k5_static_gltf.sha256 \
  "$sample/3161_0006_stadium.gltf" \
  "$sample/3161_0006_stadium.bin" \
  "$sample/stadium_collection_manifest.json" \
  tools/nfl_static_gltf.py tools/nfl_scne_inventory.py tools/nfl_scne_gltf.py \
  tools/nfl_normshort3_positions.py tools/validate_nfl_normshort3_positions.sh \
  docs/research/nfl_normshort3_positions.md \
  docs/research/nfl_static_gltf.md; do
  test -f "$required"
done

python3 -m py_compile \
  tools/nfl_static_gltf.py tools/nfl_scne_inventory.py tools/nfl_scne_gltf.py \
  tools/nfl_normshort3_positions.py
bash tools/validate_nfl_normshort3_positions.sh >/dev/null
sha256sum --check reports/assets/nfl2k5_static_gltf.sha256 >/dev/null

python3 - \
  reports/assets/nfl2k5_resource_chunks_v2.json \
  reports/assets/nfl2k5_scne_inventory.json \
  reports/assets/nfl2k5_scne_shapes.tsv \
  reports/assets/nfl2k5_scne_submeshes.tsv \
  "$manifest" "$models" "$sample/stadium_collection_manifest.json" <<'PY'
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

(
    resource_scan_path, inventory_path, shapes_path, submeshes_path,
    manifest_path, models, sample_manifest_path,
) = map(Path, sys.argv[1:])


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def register_zero(compact: str) -> str:
    for item in compact.split("|"):
        if item.startswith("r0:"):
            return item.split(":")[1]
    return "MISSING"


def active_topology(row: dict[str, str]) -> tuple[str, int, int, int, str]:
    modes = json.loads(row["primitive_mode_counts"])
    modes.pop("END", None)
    assert sum(modes.values()) == 1 and len(modes) == 1
    name = next(iter(modes))
    raw = int(row["index_element_count"]) + int(row["draw_array_vertex_count"])
    if name == "TRIANGLE_STRIP":
        return name, 6, raw, raw, "TRIANGLE_STRIP"
    assert name == "QUADS" and raw % 4 == 0
    return name, 8, raw, raw // 4 * 6, "QUADS_AS_TRIANGLES"


source_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
assert source_inventory["schema"] == "nfl2k5_scne_inventory/v1"
source_scenes = source_inventory["scenes"]
assert len(source_scenes) == 4616
source_by_index = {int(item["scene_index"]): item for item in source_scenes}
assert set(source_by_index) == set(range(4616))

shapes: dict[int, list[dict[str, object]]] = defaultdict(list)
format_counts: Counter[str] = Counter()
with shapes_path.open(encoding="utf-8", newline="") as stream:
    for row in csv.DictReader(stream, dialect="excel-tab"):
        item: dict[str, object] = dict(row)
        item["scene_index"] = int(row["scene_index"])
        item["index"] = int(row["index"])
        item["vertex_count"] = int(row["vertex_count"])
        item["submesh_count"] = int(row["submesh_count"])
        item["position_format"] = register_zero(row["attribute_descriptors"])
        shapes[int(item["scene_index"])].append(item)
        format_counts[str(item["position_format"])] += 1
for scene_index in range(4616):
    rows = shapes[scene_index]
    rows.sort(key=lambda item: int(item["index"]))
    assert [int(item["index"]) for item in rows] == list(range(len(rows)))
    assert len(rows) == int(source_by_index[scene_index]["shape_count"])
assert format_counts == {"FLOAT3": 46192, "NORMSHORT3": 8774}

submeshes: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
with submeshes_path.open(encoding="utf-8", newline="") as stream:
    for row in csv.DictReader(stream, dialect="excel-tab"):
        assert row["all_vertex_references_in_bounds"] == "True"
        assert json.loads(row["unknown_method_counts"]) == {}
        key = (int(row["scene_index"]), int(row["shape_index"]))
        submeshes[key].append(row)
for rows in submeshes.values():
    rows.sort(key=lambda row: int(row["submesh_index"]))

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest["schema"] == "nfl2k5_static_gltf_manifest/v2"
assert manifest["selection"] == "all"
assert manifest["register_zero_format_counts"] == {
    "FLOAT3": 46192, "NORMSHORT3": 8774,
}
assert manifest["summary"] == {
    "all_exported_positions_executable_proved": True,
    "all_exported_positions_float3_or_normshort3": True,
    "all_exported_topology_bounded": True,
    "binary_bytes": 213093096,
    "eligible_shape_count": 54966,
    "exported_scene_count": 4007,
    "float3_shape_count": 46192,
    "gltf_index_count": 24139104,
    "mesh_count": 54966,
    "normshort3_shape_count": 8774,
    "primitive_count": 276642,
    "raw_index_count": 24096812,
    "scene_count": 4616,
    "source_shape_count": 54966,
    "vertex_count": 13731388,
    "withheld_scene_count": 609,
    "withheld_shape_count": 0,
}
assert manifest["safety_policy"] == {
    "conservative_required_bytes": 1939757296,
    "estimated_binary_bytes_upper_bound": 213612784,
    "minimum_free_bytes": 10737418240,
}
assert manifest["source_hashes"] == {
    "resource_scan_sha256": digest(resource_scan_path),
    "scne_inventory_sha256": digest(inventory_path),
    "shapes_tsv_sha256": digest(shapes_path),
    "submeshes_tsv_sha256": digest(submeshes_path),
}
assert all(item.startswith("PORTME:") for item in manifest["portme"])
assert len(manifest["exports"]) == 4616
assert Counter(item["status"] for item in manifest["exports"]) == {
    "exported": 4007, "withheld": 609,
}

expected_files = {"manifest.json"}
totals: Counter[str] = Counter()
scene_categories: Counter[str] = Counter()
for scene_index, export in enumerate(manifest["exports"]):
    source = source_by_index[scene_index]
    assert int(export["scene_index"]) == scene_index
    assert (
        int(export["outer_index"]), int(export["chunk_index"]),
        str(export["scene_name"]), str(export["decoded_sha256"]),
    ) == (
        int(source["outer_index"]), int(source["chunk_index"]),
        str(source["name"]), str(source["decoded_sha256"]),
    )
    source_shapes = shapes[scene_index]
    eligible = [
        item for item in source_shapes
        if item["position_format"] in {"FLOAT3", "NORMSHORT3"}
        and int(item["vertex_count"]) > 0
    ]
    withheld = [item for item in source_shapes if item not in eligible]
    eligible_indices = [int(item["index"]) for item in eligible]
    assert export["eligible_shape_indices"] == eligible_indices
    assert int(export["source_shape_count"]) == len(source_shapes)
    assert [int(item["shape_index"]) for item in export["withheld_shapes"]] == [
        int(item["index"]) for item in withheld
    ]
    assert not export["withheld_shapes"]

    if not source_shapes:
        scene_categories["zero_shape"] += 1
    elif len({str(item["position_format"]) for item in eligible}) > 1:
        scene_categories["mixed"] += 1
    elif eligible[0]["position_format"] == "NORMSHORT3":
        scene_categories["normshort3_only"] += 1
    else:
        scene_categories["float3_only"] += 1

    if not source_shapes:
        assert export["status"] == "withheld"
        assert export["portme"].startswith("PORTME:")
        assert set(export) == {
            "scene_index", "outer_index", "chunk_index", "scene_name",
            "decoded_sha256", "source_shape_count", "eligible_shape_indices",
            "withheld_shapes", "status", "portme",
        }
        totals.update(
            scene_count=1, withheld_scene_count=1,
            source_shape_count=len(source_shapes),
            withheld_shape_count=len(withheld),
        )
        continue

    assert export["status"] == "exported"
    gltf_name = str(export["gltf"])
    bin_name = str(export["bin"])
    assert Path(gltf_name).name == gltf_name and Path(bin_name).name == bin_name
    expected_files.update((gltf_name, bin_name))
    gltf_path = models / gltf_name
    bin_path = models / bin_name
    gltf_bytes = gltf_path.read_bytes()
    binary = bin_path.read_bytes()
    assert hashlib.sha256(gltf_bytes).hexdigest() == export["gltf_sha256"]
    assert hashlib.sha256(binary).hexdigest() == export["bin_sha256"]
    assert len(binary) == int(export["binary_bytes"])
    document = json.loads(gltf_bytes)
    assert document["asset"]["version"] == "2.0"
    assert document["asset"]["generator"] == "nfl_static_gltf.py"
    asset_source = document["asset"]["extras"]["source"]
    assert (
        int(asset_source["scene_index"]), int(asset_source["outer_index"]),
        int(asset_source["chunk_index"]), str(asset_source["scene_name"]),
        str(asset_source["decoded_sha256"]),
    ) == (
        scene_index, int(source["outer_index"]), int(source["chunk_index"]),
        str(source["name"]), str(source["decoded_sha256"]),
    )
    assert document["buffers"] == [{"uri": bin_name, "byteLength": len(binary)}]
    assert document["scene"] == 0
    assert document["scenes"] == [
        {"name": source["name"], "nodes": list(range(len(eligible)))}
    ]
    assert not ({"materials", "textures", "images", "samplers", "skins", "animations"} & set(document))
    assert document["extras"]["raw_coordinates"] is True
    assert all(item.startswith("PORTME:") for item in document["extras"]["portme"])
    assert document["extras"]["withheld_shapes"] == export["withheld_shapes"]
    nodes = document["nodes"]
    meshes = document["meshes"]
    accessors = document["accessors"]
    views = document["bufferViews"]
    assert len(nodes) == len(meshes) == len(eligible)
    expected_primitive_count = sum(
        len(submeshes[(scene_index, int(shape["index"]))]) for shape in eligible
    )
    assert len(accessors) == len(views) == len(eligible) + expected_primitive_count

    seen_accessors: set[int] = set()
    intervals: list[tuple[int, int]] = []
    scene_raw = 0
    scene_output = 0
    scene_vertices = 0
    scene_primitives = 0
    for mesh_index, (node, mesh, shape) in enumerate(zip(nodes, meshes, eligible)):
        shape_index = int(shape["index"])
        assert node["mesh"] == mesh_index
        assert int(node["extras"]["source_shape_index"]) == shape_index
        assert node["extras"]["raw_coordinates"] is True
        assert node["extras"]["portme"].startswith("PORTME:")
        assert int(mesh["extras"]["source_shape_index"]) == shape_index
        position_format = str(shape["position_format"])
        assert position_format in {"FLOAT3", "NORMSHORT3"}
        assert mesh["extras"]["position_format"] == position_format
        assert mesh["extras"]["raw_coordinates"] is True
        decode = mesh["extras"]["position_decode"]
        if position_format == "FLOAT3":
            assert decode == {
                "equation": "position.xyz = little_endian_FLOAT3(register0.xyz)",
                "identity_decode": True,
            }
        else:
            assert decode["equation"] == (
                "position.xyz = normshort3(register0.xyz) * scale + offset.xyz"
            )
            assert decode["xbox_signed_normalization"] == (
                "value/32767 for nonnegative; value/32768 for negative"
            )
            assert decode["serialized_scale_field"] == "+0x10"
            assert decode["serialized_offset_fields"] == ["+0x20", "+0x24", "+0x28"]
            assert math.isfinite(float(decode["scale"]))
            assert len(decode["offset"]) == 3
            assert all(math.isfinite(float(value)) for value in decode["offset"])
            assert decode["runtime_shader_constant_c_minus_88"] == [
                *decode["offset"], decode["scale"],
            ]
            assert decode["shader_instruction"] == (
                "MAD r4.xyz, v0.xyzz, c[-88].wwww, c[-88].xyzz"
            )
        expected_submeshes = submeshes[(scene_index, shape_index)]
        assert len(expected_submeshes) == int(shape["submesh_count"])
        assert len(mesh["primitives"]) == len(expected_submeshes)
        position_indices = {
            int(primitive["attributes"]["POSITION"])
            for primitive in mesh["primitives"]
        }
        assert len(position_indices) == 1
        position_index = next(iter(position_indices))
        assert position_index not in seen_accessors
        seen_accessors.add(position_index)
        position = accessors[position_index]
        assert (
            int(position["componentType"]), position["type"], int(position["count"])
        ) == (5126, "VEC3", int(shape["vertex_count"]))
        position_view = views[int(position["bufferView"])]
        start = int(position_view.get("byteOffset", 0)) + int(position.get("byteOffset", 0))
        length = int(position["count"]) * 12
        assert position_view == {
            "buffer": 0, "byteOffset": start,
            "byteLength": length, "target": 34962,
        }
        assert start % 4 == 0 and start + length <= len(binary)
        intervals.append((start, start + length))
        minima = [math.inf, math.inf, math.inf]
        maxima = [-math.inf, -math.inf, -math.inf]
        for values in struct.iter_unpack("<3f", binary[start:start + length]):
            assert all(math.isfinite(value) for value in values)
            for axis, value in enumerate(values):
                minima[axis] = min(minima[axis], value)
                maxima[axis] = max(maxima[axis], value)
        assert position["min"] == minima and position["max"] == maxima
        scene_vertices += int(position["count"])

        for primitive, row in zip(mesh["primitives"], expected_submeshes):
            mode_name, xbox_mode, raw_count, output_count, conversion = active_topology(row)
            expected_gltf_mode = 5 if mode_name == "TRIANGLE_STRIP" else 4
            assert int(primitive["mode"]) == expected_gltf_mode
            extras = primitive["extras"]
            assert (
                int(extras["source_submesh_index"]),
                int(extras["source_material_index"]),
                int(extras["source_auxiliary_index"]),
                int(extras["xbox_primitive_mode"]),
                extras["topology_conversion"],
                int(extras["raw_index_count"]),
                int(extras["gltf_index_count"]),
            ) == (
                int(row["submesh_index"]), int(row["material_index"]),
                int(row["auxiliary_index"]), xbox_mode, conversion,
                raw_count, output_count,
            )
            assert extras["portme"].startswith("PORTME:")
            index_index = int(primitive["indices"])
            assert index_index not in seen_accessors
            seen_accessors.add(index_index)
            indices = accessors[index_index]
            assert (
                int(indices["componentType"]), indices["type"], int(indices["count"])
            ) == (5123, "SCALAR", output_count)
            index_view = views[int(indices["bufferView"])]
            index_start = int(index_view.get("byteOffset", 0)) + int(indices.get("byteOffset", 0))
            index_length = output_count * 2
            assert index_view == {
                "buffer": 0, "byteOffset": index_start,
                "byteLength": index_length, "target": 34963,
            }
            assert index_start % 4 == 0 and index_start + index_length <= len(binary)
            intervals.append((index_start, index_start + index_length))
            values = memoryview(binary)[index_start:index_start + index_length].cast("H")
            assert min(values) == int(indices["min"][0])
            assert max(values) == int(indices["max"][0]) < int(shape["vertex_count"])
            scene_raw += raw_count
            scene_output += output_count
            scene_primitives += 1

    assert seen_accessors == set(range(len(accessors)))
    intervals.sort()
    cursor = 0
    for start, end in intervals:
        assert cursor <= start and not any(binary[cursor:start])
        cursor = end
    assert not any(binary[cursor:])
    assert scene_vertices == int(export["vertex_count"])
    assert scene_primitives == int(export["primitive_count"])
    assert scene_raw == int(export["raw_index_count"])
    assert scene_output == int(export["gltf_index_count"])
    totals.update(
        scene_count=1, exported_scene_count=1,
        source_shape_count=len(source_shapes),
        eligible_shape_count=len(eligible), withheld_shape_count=len(withheld),
        float3_shape_count=sum(
            item["position_format"] == "FLOAT3" for item in eligible
        ),
        normshort3_shape_count=sum(
            item["position_format"] == "NORMSHORT3" for item in eligible
        ),
        mesh_count=len(meshes), primitive_count=scene_primitives,
        vertex_count=scene_vertices, raw_index_count=scene_raw,
        gltf_index_count=scene_output, binary_bytes=len(binary),
    )

assert scene_categories == {
    "zero_shape": 609, "normshort3_only": 2199,
    "float3_only": 1772, "mixed": 36,
}
assert totals == Counter({
    "scene_count": 4616, "exported_scene_count": 4007,
    "withheld_scene_count": 609, "source_shape_count": 54966,
    "eligible_shape_count": 54966, "withheld_shape_count": 0,
    "float3_shape_count": 46192, "normshort3_shape_count": 8774,
    "mesh_count": 54966, "primitive_count": 276642,
    "vertex_count": 13731388, "raw_index_count": 24096812,
    "gltf_index_count": 24139104, "binary_bytes": 213093096,
})
actual_files = {path.name for path in models.iterdir() if path.is_file()}
assert actual_files == expected_files and len(actual_files) == 8015

sample = json.loads(sample_manifest_path.read_text(encoding="utf-8"))
assert sample["schema"] == "nfl2k5_static_gltf_manifest/v2"
assert sample["selection"] == {"outer_index": 3161, "chunk_index": 6}
assert sample["summary"] == {
    "all_exported_positions_executable_proved": True,
    "all_exported_positions_float3_or_normshort3": True,
    "all_exported_topology_bounded": True,
    "binary_bytes": 268004,
    "eligible_shape_count": 143,
    "exported_scene_count": 1,
    "float3_shape_count": 143,
    "gltf_index_count": 27066,
    "mesh_count": 143,
    "normshort3_shape_count": 0,
    "primitive_count": 562,
    "raw_index_count": 27014,
    "scene_count": 1,
    "source_shape_count": 143,
    "vertex_count": 17819,
    "withheld_scene_count": 0,
    "withheld_shape_count": 0,
}
sample_export = sample["exports"][0]
assert sample_export["gltf"] == "3161_0006_stadium.gltf"
assert sample_export["bin"] == "3161_0006_stadium.bin"
assert digest(sample_manifest_path.parent / sample_export["gltf"]) == sample_export["gltf_sha256"]
assert digest(sample_manifest_path.parent / sample_export["bin"]) == sample_export["bin_sha256"]
assert (sample_manifest_path.parent / sample_export["gltf"]).read_bytes() == (
    models / sample_export["gltf"]
).read_bytes()
assert (sample_manifest_path.parent / sample_export["bin"]).read_bytes() == (
    models / sample_export["bin"]
).read_bytes()

print(
    "NFL2K5_STATIC_GLTF_INVARIANTS_PASS "
    "scenes=4007/4616 meshes=54966 primitives=276642 vertices=13731388"
)
PY

temporary=$(mktemp -d /tmp/nfl-static-gltf.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
python3 tools/nfl_static_gltf.py "$index" \
  --output-dir "$temporary/sample" \
  --manifest "$temporary/sample/stadium_collection_manifest.json" \
  --only-outer 3161 --only-chunk 6 >/dev/null
cmp "$sample/3161_0006_stadium.gltf" "$temporary/sample/3161_0006_stadium.gltf"
cmp "$sample/3161_0006_stadium.bin" "$temporary/sample/3161_0006_stadium.bin"
cmp "$sample/stadium_collection_manifest.json" \
  "$temporary/sample/stadium_collection_manifest.json"
echo NFL2K5_STATIC_GLTF_SAMPLE_REGEN_PASS

if [[ ${NFL_STATIC_GLTF_REGEN:-0} == 1 ]]; then
  python3 tools/nfl_static_gltf.py "$index" --output-dir "$temporary/models"
  cmp "$manifest" "$temporary/models/manifest.json"
  while IFS= read -r name; do
    cmp "$models/$name" "$temporary/models/$name"
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
  echo NFL2K5_STATIC_GLTF_FULL_REGEN_PASS
fi

echo 'NFL2K5_STATIC_GLTF_VALIDATION_PASS scenes=4007/4616 meshes=54966 primitives=276642 vertices=13731388'
