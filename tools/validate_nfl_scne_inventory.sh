#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

INDEX=${NFL2K5_INDEX:-'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'}
TMP=/tmp/nfl2k5-scne-validation
mkdir -p "$TMP/gltf"

python3 -m py_compile tools/nfl_scne_inventory.py tools/nfl_scne_gltf.py
sha256sum --check reports/assets/nfl2k5_scne.sha256 >/dev/null

jq -e '
  .schema == "nfl2k5_scne_inventory/v1" and
  .summary.scene_count == 4616 and
  .summary.all_descriptors_valid == true and
  .summary.all_eight_table_ranges_bounded == true and
  .summary.all_vertex_stream_ranges_bounded == true and
  .summary.all_push_streams_bounded == true and
  .summary.all_push_vertex_references_in_bounds == true and
  .summary.table_record_totals == {
    "aux_14":8732,"aux_50":145,"aux_60":3744,"markers":101437,
    "materials":55905,"nodes":70555,"shapes":54966,"textures":37389
  } and
  .summary.name_row_count == 404512 and
  .summary.material_mapping_count == 55905 and
  .summary.mapped_material_count == 45413 and
  .summary.unmapped_material_count == 10492 and
  .summary.embedded_texture_count == 37389 and
  .summary.embedded_texture_format_counts == {"P8":37389} and
  .summary.embedded_texture_conversion_status_counts == {"base_level_supported":37389} and
  .summary.conversion_failure_count == 0 and
  .summary.shape_count == 54966 and
  .summary.submesh_count == 276642 and
  .summary.node_shape_name_match_counts == {"1":70555} and
  .summary.vertex_stream_index_counts == {"0":54966,"1":54966,"2":482} and
  .summary.vertex_attribute_format_counts == {
    "D3DCOLOR":46343,"FLOAT3":46192,"NONE":658628,
    "NORMPACKED3":9587,"NORMSHORT2":54966,"NORMSHORT3":8774,"SHORT1":54966
  } and
  .summary.primitive_mode_counts == {
    "END":276642,"QUADS":1429,"TRIANGLE_STRIP":275213
  } and
  .sample_png == {
    "chunk_index":6,"format_name":"P8","height":32,"material_name":"flags",
    "outer_index":3161,
    "png_sha256":"b437b63f9eabeeb2e315f67851686e29a51628744a5cbc1ee84f5874ff55a955",
    "rgba_sha256":"0b02e528dd1ffaed487611ec308c44a3fc7a4107af2fe76007f395b4c332682a",
    "texture_index":2,"width":32
  }
' reports/assets/nfl2k5_scne_inventory.json >/dev/null

test "$(wc -l < reports/assets/nfl2k5_scne_scenes.tsv)" -eq 4617
test "$(wc -l < reports/assets/nfl2k5_scne_names.tsv)" -eq 404513
test "$(wc -l < reports/assets/nfl2k5_scne_material_textures.tsv)" -eq 55906
test "$(wc -l < reports/assets/nfl2k5_scne_embedded_textures.tsv)" -eq 37390
test "$(wc -l < reports/assets/nfl2k5_scne_shapes.tsv)" -eq 54967
test "$(wc -l < reports/assets/nfl2k5_scne_submeshes.tsv)" -eq 276643

python3 - <<'PY'
import collections
import csv
import json
import struct
from pathlib import Path

roles = collections.Counter()
with Path("reports/assets/nfl2k5_scne_names.tsv").open(encoding="utf-8", newline="") as stream:
    for row in csv.DictReader(stream, dialect="excel-tab"):
        roles[row["role"]] += 1
assert roles == {
    "scene": 4616,
    "material_candidate": 55905,
    "node_candidate": 70555,
    "node_secondary": 15596,
    "shape_candidate": 54966,
    "marker_candidate": 101437,
    "marker_link": 101437,
}

modes = collections.Counter()
methods = collections.Counter()
unknown = collections.Counter()
inline_indices = 0
draw_vertices = 0
with Path("reports/assets/nfl2k5_scne_submeshes.tsv").open(encoding="utf-8", newline="") as stream:
    for row in csv.DictReader(stream, dialect="excel-tab"):
        modes.update(json.loads(row["primitive_mode_counts"]))
        methods.update(json.loads(row["method_counts"]))
        unknown.update(json.loads(row["unknown_method_counts"]))
        inline_indices += int(row["index_element_count"])
        draw_vertices += int(row["draw_array_vertex_count"])
        assert row["all_vertex_references_in_bounds"] == "True"
assert modes == {"END": 276642, "TRIANGLE_STRIP": 275213, "QUADS": 1429}
assert methods == {"0x17fc": 553284, "0x1800": 376252, "0x1810": 136493}
assert not unknown
assert inline_indices == 22_521_444
assert draw_vertices == 1_575_368

def validate_gltf(path: Path, vertices: int, primitive_count: int) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["asset"]["version"] == "2.0"
    assert doc["accessors"][0]["count"] == vertices
    assert len(doc["meshes"][0]["primitives"]) == primitive_count
    blob = path.with_name(doc["buffers"][0]["uri"]).read_bytes()
    assert len(blob) == doc["buffers"][0]["byteLength"]
    for view in doc["bufferViews"]:
        assert view.get("byteOffset", 0) + view["byteLength"] <= len(blob)
    for primitive in doc["meshes"][0]["primitives"]:
        accessor = doc["accessors"][primitive["indices"]]
        view = doc["bufferViews"][accessor["bufferView"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        indices = struct.unpack_from(f"<{accessor['count']}H", blob, start)
        assert max(indices) < vertices
    return doc

large = validate_gltf(Path("reports/asset_samples/nfl_scne/stadium_group292.gltf"), 188, 4)
assert [item["raw_index_count"] for item in large["extras"]["topology"]] == [24, 18, 175, 54]
small = validate_gltf(Path("reports/asset_samples/nfl_scne/stadium_group318.gltf"), 8, 1)
assert small["extras"]["topology"][0]["conversion"] == "QUADS_AS_TRIANGLES"
assert small["accessors"][1]["count"] == 12

png = Path("reports/asset_samples/nfl_scne/stadium_flags.png").read_bytes()
assert png[:8] == b"\x89PNG\r\n\x1a\n"
assert struct.unpack(">II", png[16:24]) == (32, 32)
smoke = Path("reports/host_menu_extracted_nfl_stadium_mesh.png").read_bytes()
assert smoke[:8] == b"\x89PNG\r\n\x1a\n"
assert struct.unpack(">II", smoke[16:24]) == (1280, 720)
PY

python3 tools/nfl_scne_gltf.py "$INDEX" \
  --resource-scan reports/assets/nfl2k5_resource_chunks_v2.json \
  --outer 3161 --chunk 6 --shape 0 \
  --output "$TMP/gltf/stadium_group292.gltf"
python3 tools/nfl_scne_gltf.py "$INDEX" \
  --resource-scan reports/assets/nfl2k5_resource_chunks_v2.json \
  --outer 3161 --chunk 6 --shape 2 \
  --output "$TMP/gltf/stadium_group318.gltf"
cmp reports/asset_samples/nfl_scne/stadium_group292.gltf "$TMP/gltf/stadium_group292.gltf"
cmp reports/asset_samples/nfl_scne/stadium_group292.bin "$TMP/gltf/stadium_group292.bin"
cmp reports/asset_samples/nfl_scne/stadium_group318.gltf "$TMP/gltf/stadium_group318.gltf"
cmp reports/asset_samples/nfl_scne/stadium_group318.bin "$TMP/gltf/stadium_group318.bin"

# A full rebuild is deliberately the default: it re-decodes all 4,616 SCNE
# wrappers and compares every deterministic corpus output byte-for-byte.
python3 tools/nfl_scne_inventory.py "$INDEX" \
  --resource-scan reports/assets/nfl2k5_resource_chunks_v2.json \
  --json "$TMP/inventory.json" \
  --scenes-tsv "$TMP/scenes.tsv" \
  --names-tsv "$TMP/names.tsv" \
  --mappings-tsv "$TMP/material_textures.tsv" \
  --textures-tsv "$TMP/embedded_textures.tsv" \
  --shapes-tsv "$TMP/shapes.tsv" \
  --submeshes-tsv "$TMP/submeshes.tsv" \
  --sample-png "$TMP/stadium_flags.png"

cmp reports/assets/nfl2k5_scne_inventory.json "$TMP/inventory.json"
cmp reports/assets/nfl2k5_scne_scenes.tsv "$TMP/scenes.tsv"
cmp reports/assets/nfl2k5_scne_names.tsv "$TMP/names.tsv"
cmp reports/assets/nfl2k5_scne_material_textures.tsv "$TMP/material_textures.tsv"
cmp reports/assets/nfl2k5_scne_embedded_textures.tsv "$TMP/embedded_textures.tsv"
cmp reports/assets/nfl2k5_scne_shapes.tsv "$TMP/shapes.tsv"
cmp reports/assets/nfl2k5_scne_submeshes.tsv "$TMP/submeshes.tsv"
cmp reports/asset_samples/nfl_scne/stadium_flags.png "$TMP/stadium_flags.png"

echo 'NFL2K5_SCNE_VALIDATION_PASS scenes=4616 shapes=54966 submeshes=276642 textures=37389'
