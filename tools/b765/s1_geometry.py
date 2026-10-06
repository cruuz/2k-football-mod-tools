#!/usr/bin/env python3
"""Export and strictly reimport fixed-topology SOFTDRINK stadium geometry.

This tool does not author geometry. The coordinator edits the exported glTF.
Native vertex IDs, submesh IDs and material IDs must survive the edit. Import
patches only explicitly authorized position/UV lanes in the original decoded
SCNE and refits that scene into its exact existing compressed allocation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "tools"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from mod_editor.core import nfl2k5_modern_metlife as ml  # noqa: E402
from mod_editor.core import nfl2k5_models as models  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as builder  # noqa: E402

SCHEMA = "b765_s1_geometry_export/v1"
RECEIPT_SCHEMA = "b765_s1_geometry_receipt/v1"


class GeometryError(ValueError):
    """An edit or its source does not satisfy the exact geometry contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometryError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def stadium(data: bytes):
    """Find the actual named stadium SCNE, never the field SCNE."""
    tx = ml._tools()[0]
    matches = []
    for chunk in tx.parse_chunks(data, allow_trailing=True):
        if chunk.kind == "SCNE":
            scene, decoded = ml._scene(data, chunk)
            if scene["name"] == "stadium":
                matches.append((chunk, scene, decoded))
    require(len(matches) == 1, "bundle must contain exactly one named stadium SCNE")
    return matches[0]


def span_bytes(data: bytes, chunk) -> bytes:
    return data[chunk.offset:chunk.offset + 32 + chunk.stored_size]


def _safe_file(base: Path, relative: str) -> Path:
    path = (base / relative).resolve()
    require(path.is_relative_to(base.resolve()) and path.is_file(),
            f"export artifact is missing or escapes its folder: {relative}")
    return path


def _triangles(mode: int, indices: list[int]) -> Counter:
    if mode == 4:
        require(len(indices) % 3 == 0, "triangle list count is not divisible by three")
        tris = [tuple(indices[i:i + 3]) for i in range(0, len(indices), 3)]
    elif mode == 5:
        tris = [(indices[i], indices[i + 1], indices[i + 2]) if i % 2 == 0
                else (indices[i + 1], indices[i], indices[i + 2])
                for i in range(len(indices) - 2)]
    elif mode == 6:
        tris = [(indices[0], indices[i], indices[i + 1])
                for i in range(1, len(indices) - 1)]
    else:
        # Stadium geometry is triangles. Preserve any unusual point/line
        # primitive exactly rather than inventing an equivalence rule.
        return Counter({("raw", mode, tuple(indices)): 1})
    return Counter(min((a, b, c), (b, c, a), (c, a, b))
                   for a, b, c in tris if len({a, b, c}) == 3)


def _primitive_key(primitive: dict) -> tuple[int, int]:
    extras = primitive.get("extras", {})
    if (primitive.get("mode") == 0 and "indices" not in primitive
            and "material" not in primitive and not extras):
        # Studio's explicitly documented fallback for native shapes which
        # retain vertex arrays but have no drawable submesh. No native draw
        # words or material are synthesized for this read-only point preview.
        return -1, -1
    submesh = extras.get("source_submesh_index")
    material = extras.get("source_material_index")
    require(type(submesh) is int and type(material) is int,
            "primitive lost original submesh/material IDs")
    return submesh, material


def _id_rows(gltf, primitive: dict) -> tuple[list[int], dict[str, list[tuple]]]:
    attrs = primitive.get("attributes", {})
    require(models.VERTEX_INDEX_ATTRIBUTE in attrs,
            f"missing {models.VERTEX_INDEX_ATTRIBUTE}; export custom mesh attributes")
    rows = {key: gltf.accessor(int(accessor)) for key, accessor in attrs.items()}
    ids = []
    for row in rows[models.VERTEX_INDEX_ATTRIBUTE]:
        require(len(row) == 1 and math.isfinite(row[0]) and row[0] == int(row[0]),
                "vertex IDs must be exact finite integers")
        ids.append(int(row[0]))
    require(all(len(values) == len(ids) for values in rows.values()),
            "primitive attribute counts differ")
    require(all(math.isfinite(value) for values in rows.values()
                for row in values for value in row), "non-finite vertex attribute")
    return ids, rows


def _mesh_rows(gltf, mesh: dict, count: int):
    values: dict[int, dict[str, tuple]] = {}
    topology: dict[tuple[int, int], Counter] = {}
    materials: dict[tuple[int, int], int | None] = {}
    for primitive in mesh["primitives"]:
        key = _primitive_key(primitive)
        ids, attrs = _id_rows(gltf, primitive)
        require(all(0 <= vertex < count for vertex in ids), "vertex ID outside native shape")
        for index, vertex in enumerate(ids):
            row = {name: vals[index] for name, vals in attrs.items()}
            require(vertex not in values or values[vertex] == row,
                    f"split copies of native vertex {vertex} disagree")
            values[vertex] = row
        if "indices" in primitive:
            accessor = gltf.document["accessors"][int(primitive["indices"])]
            require(accessor.get("type") == "SCALAR"
                    and accessor.get("componentType") in (5121, 5123, 5125)
                    and not accessor.get("normalized", False),
                    "primitive indices must be unsigned native integers")
            index_rows = gltf.accessor(int(primitive["indices"]))
            require(all(len(row) == 1 and math.isfinite(row[0]) and row[0] == int(row[0])
                        for row in index_rows), "primitive indices must be exact integers")
            raw_indices = [int(row[0]) for row in index_rows]
        else:
            raw_indices = list(range(len(ids)))
        require(all(0 <= index < len(ids) for index in raw_indices),
                "primitive index outside its attribute accessor")
        native_indices = [ids[index] for index in raw_indices]
        topology.setdefault(key, Counter()).update(
            _triangles(int(primitive.get("mode", 4)), native_indices))
        material = primitive.get("material")
        require(key not in materials or materials[key] == material,
                "native submesh has inconsistent glTF materials")
        materials[key] = material
    require(set(values) == set(range(count)),
            "every native vertex ID must be present, including unreferenced vertices")
    return values, topology, materials


def strict_edits(baseline, edited) -> dict[int, dict[int, dict[str, tuple]]]:
    """Map positions/UVs by exact native IDs; refuse every other edit."""
    before, after = baseline.document, edited.document
    for field in ("nodes", "scenes", "scene", "materials", "textures", "images", "samplers", "skins"):
        require(before.get(field) == after.get(field),
                f"{field} changed; this import accepts local position/UV edits only")
    for image in before.get("images", []):
        require("bufferView" in image, "strict source images must be embedded")
        def image_bytes(gltf):
            view = gltf.document["bufferViews"][image["bufferView"]]
            begin = int(view.get("byteOffset", 0))
            return gltf.buffers[int(view.get("buffer", 0))][begin:begin + view["byteLength"]]
        require(image_bytes(baseline) == image_bytes(edited), "embedded image bytes changed")
    source_meshes = {m["extras"]["source_shape_index"]: m for m in before["meshes"]}
    edited_meshes = {}
    for mesh in after.get("meshes", []):
        shape = mesh.get("extras", {}).get("source_shape_index")
        require(type(shape) is int and shape in source_meshes and shape not in edited_meshes,
                "mesh lost, duplicated or changed its native shape ID")
        edited_meshes[shape] = mesh
    require(set(source_meshes) == set(edited_meshes), "native shape set changed")
    changes = {}
    for shape, original in source_meshes.items():
        candidate = edited_meshes[shape]
        require(original["name"] == candidate.get("name")
                and original["extras"] == candidate.get("extras"),
                f"shape {shape}: name/identity/decode metadata changed")
        count = int(original["extras"]["nfl2k5_vertex_count"])
        old_values, old_topology, old_materials = _mesh_rows(baseline, original, count)
        new_values, new_topology, new_materials = _mesh_rows(edited, candidate, count)
        require(old_topology == new_topology, f"shape {shape}: native topology changed")
        require(old_materials == new_materials, f"shape {shape}: native material assignment changed")
        moved = {}
        for vertex in range(count):
            old, new = old_values[vertex], new_values[vertex]
            require(set(old) == set(new), f"shape {shape}: vertex attributes changed")
            for attribute in old:
                require(attribute in ("POSITION", "TEXCOORD_0") or old[attribute] == new[attribute],
                        f"shape {shape} vertex {vertex}: {attribute} changed")
            delta = {key: new[key] for key in ("POSITION", "TEXCOORD_0")
                     if key in old and old[key] != new[key]}
            if delta:
                moved[vertex] = delta
        if moved:
            changes[shape] = moved
    return changes


def _obj(gltf, path: Path) -> None:
    """Read-only full-stadium reference, in metres, with native vertex IDs."""
    lines = ["# Read-only SCNE reference. Native IDs are zero-based; positions are metres.",
             "# Import uses stadium.gltf, not this triangulated reference."]
    start = 1
    for mesh in gltf.document["meshes"]:
        shape = mesh["extras"]["source_shape_index"]
        count = mesh["extras"]["nfl2k5_vertex_count"]
        values, _, _ = _mesh_rows(gltf, mesh, count)
        lines.append(f"o shape_{shape:04d}_{mesh['name']}")
        for vertex in range(count):
            lines.append(f"# SCNE_VERTEX_ID {shape} {vertex}")
            lines.append("v " + " ".join(format(v / 100, ".17g") for v in values[vertex]["POSITION"]))
        for primitive in mesh["primitives"]:
            ids, _ = _id_rows(gltf, primitive)
            raw = ([int(v[0]) for v in gltf.accessor(primitive["indices"])]
                   if "indices" in primitive else list(range(len(ids))))
            mode = int(primitive.get("mode", 4))
            key = _primitive_key(primitive)
            lines.append(f"g shape_{shape}_submesh_{key[0]}_material_{key[1]}")
            if mode in (4, 5, 6):
                for tri, repeats in _triangles(mode, [ids[i] for i in raw]).items():
                    lines.extend("f " + " ".join(str(start + i) for i in tri) for _ in range(repeats))
        start += count
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def export_bundle(data: bytes, name: str, output: Path, *, outer_index: int = 0) -> dict:
    require(Path(name).name == name and name.endswith(".iff"), "disc-file name must be a simple .iff name")
    output = Path(output)
    require(not output.exists(), f"export folder already exists: {output}")
    chunk, scene, decoded = stadium(data)
    span = span_bytes(data, chunk)
    key = models.model_key(outer_index, chunk.index)
    output.mkdir(parents=True)
    (output / "source.scne").write_bytes(span)
    source = models.ModelSpanSource({key: span})
    models.export_model(source, key, output / "baseline.gltf", include_skins=False)
    baseline = models.GltfFile(output / "baseline.gltf")
    editable_document = dict(baseline.document)
    editable_document["buffers"] = [{**buffer, "uri": "stadium.bin"}
                                    for buffer in baseline.document["buffers"]]
    (output / "stadium.gltf").write_bytes(json_bytes(editable_document))
    shutil.copyfile(output / "baseline.bin", output / "stadium.bin")
    _obj(baseline, output / "stadium_reference.obj")
    submeshes: dict[int, list] = {}
    for submesh in scene["submeshes"]:
        submeshes.setdefault(submesh["shape_index"], []).append({
            "submesh_id": submesh["submesh_index"], "material_id": submesh["material_index"],
            "material_name": submesh["material_name"],
            "primary_words": submesh["primary_command_word_count"],
            "secondary_words": submesh["secondary_command_word_count"],
        })
    manifest = {
        "schema": SCHEMA, "disc_file": name, "bundle_sha256": sha(data), "outer_index": outer_index,
        "source_span_sha256": sha(span), "source_decoded_sha256": sha(decoded),
        "model_key": key, "chunk_index": chunk.index, "chunk_offset": chunk.offset,
        "chunk_length": len(span), "system_bytes": chunk.system_bytes, "video_bytes": chunk.video_bytes,
        "baseline_gltf_sha256": sha((output / "baseline.gltf").read_bytes()),
        "baseline_bin_sha256": sha((output / "baseline.bin").read_bytes()),
        "shapes": [{"shape_id": shape["index"], "name": shape["name"],
                    "vertex_count": shape["vertex_count"], "record_offset": shape["record_offset"],
                    "submeshes": submeshes.get(shape["index"], [])} for shape in scene["shapes"]],
        "units": "glTF buffer positions are centimetres; its fixed root scale is 0.01; OBJ reference is metres",
        "editing": "Edit local POSITION/TEXCOORD_0 only. Keep all custom attributes, native IDs, metadata and nodes.",
        "geometry_authored_by_tool": False, "gameplay_witness": False,
    }
    (output / "manifest.json").write_bytes(json_bytes(manifest))
    return manifest


def _merged_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def scope_proof(before: bytes, after: bytes, ranges: list[tuple[int, int]]) -> dict:
    require(len(before) == len(after), "decoded SCNE length changed")
    outside_before, outside_after = hashlib.sha256(), hashlib.sha256()
    cursor = 0
    merged = _merged_ranges(ranges)
    for start, end in merged + [(len(before), len(before))]:
        require(cursor <= start <= end <= len(before), "scope exceeds decoded SCNE")
        require(before[cursor:start] == after[cursor:start], "decoded bytes changed outside authorized geometry lanes")
        outside_before.update(before[cursor:start])
        outside_after.update(after[cursor:start])
        cursor = end
    return {"outside_sha256_before": outside_before.hexdigest(),
            "outside_sha256_after": outside_after.hexdigest(),
            "authorized_ranges": [[start, end - start] for start, end in merged],
            "changed_decoded_bytes": sum(a != b for a, b in zip(before, after)),
            "outside_identical": True}


def compile_bundle(data: bytes, manifest_path: Path, edited_path: Path, *,
                   positions: set[int] | None = None, uvs: set[int] | None = None,
                   rescale_uvs: set[int] | None = None, bounds: set[int] | None = None,
                   uv_constants: dict[int, list[float]] | None = None) -> tuple[bytes, dict]:
    """Compile a coordinator's edit, accepting only original or exact idempotent output spans.

    Changes to other bundle chunks compose automatically. Changes inside the
    stadium chunk require a fresh pinned export of that intermediate input.
    """
    positions, uvs = positions or set(), uvs or set()
    rescale_uvs, bounds = rescale_uvs or set(), bounds or set()
    require(rescale_uvs <= uvs and bounds <= positions,
            "UV rescaling requires UV scope; bounds updating requires position scope")
    uv_constants = uv_constants or {}
    require(set(uv_constants) <= rescale_uvs,
            "explicit UV constants require UV and rescale-uvs scope")
    for constant in uv_constants.values():
        require(len(constant) == 4 and all(math.isfinite(x) for x in constant)
                and all(x != 0 for x in constant[:2]), "invalid explicit UV constant")
    manifest_path, edited_path = Path(manifest_path), Path(edited_path)
    directory = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == SCHEMA, "unexpected geometry export schema")
    source_span = _safe_file(directory, "source.scne").read_bytes()
    require(sha(source_span) == manifest["source_span_sha256"], "unexpected source SCNE hash")
    for file, key in (("baseline.gltf", "baseline_gltf_sha256"), ("baseline.bin", "baseline_bin_sha256")):
        require(sha(_safe_file(directory, file).read_bytes()) == manifest[key], f"unexpected {file} hash")
    baseline = models.GltfFile(directory / "baseline.gltf")
    edited = models.GltfFile(edited_path)
    changes = strict_edits(baseline, edited)
    for shape_id in uv_constants:
        changes.setdefault(shape_id, {})
    key = manifest["model_key"]
    source = models.ModelSpanSource({key: source_span})
    resource, decoded, scene = source.parse(key)
    require(sha(decoded) == manifest["source_decoded_sha256"], "unexpected decoded source hash")
    shapes = {shape["index"]: shape for shape in scene["shapes"]}
    require(positions | uvs <= set(shapes), "authorized shape ID is absent from source")
    result = bytearray(decoded)
    ranges = []
    edit_receipts = []
    for shape_id, vertices in changes.items():
        shape = shapes[shape_id]
        lanes = models._shape_lanes(scene, shape, decoded)
        original_positions = models.read_positions(decoded, shape, lanes)
        wanted_positions = list(original_positions)
        uv_targets = None
        original_uvs = None
        if lanes.texcoord is not None:
            original_uvs = models.read_lane_2h(decoded, shape, lanes.texcoord, lanes.vertex_count)
            uv_targets = [models.uv_to_gltf(u, v, lanes.uv_scale, lanes.uv_offset) for u, v in original_uvs]
        for vertex, attributes in vertices.items():
            if "POSITION" in attributes:
                require(shape_id in positions, f"shape {shape_id}: position edit has no explicit scope")
                require(lanes.position_format == "FLOAT3", "this strict stadium writer accepts FLOAT3 positions only")
                require(len(attributes["POSITION"]) == 3, "position must be FLOAT3")
                wanted_positions[vertex] = attributes["POSITION"]
                at = models._stream_base(scene, shape, lanes.position_stream) + vertex * lanes.position_stride + lanes.position_offset
                struct.pack_into("<3f", result, at, *wanted_positions[vertex])
                ranges.append((at, at + 12))
                edit_receipts.append({"shape_id": shape_id, "vertex_id": vertex, "lane": "position", "offset": at, "length": 12})
            if "TEXCOORD_0" in attributes:
                require(shape_id in uvs, f"shape {shape_id}: UV edit has no explicit scope")
                require(uv_targets is not None and len(attributes["TEXCOORD_0"]) == 2, "source has no proved UV lane")
                uv_targets[vertex] = attributes["TEXCOORD_0"]
        if any("POSITION" in row for row in vertices.values()):
            centre = struct.unpack_from("<3f", decoded, lanes.record_offset)
            radius = struct.unpack_from("<f", decoded, lanes.record_offset + 0x48)[0]
            if shape_id in bounds:
                centre, radius = builder.bounding_sphere(wanted_positions)
                struct.pack_into("<3f", result, lanes.record_offset, *centre)
                struct.pack_into("<f", result, lanes.record_offset + 0x48, radius)
                ranges.extend([(lanes.record_offset, lanes.record_offset + 12),
                               (lanes.record_offset + 0x48, lanes.record_offset + 0x4C)])
                edit_receipts.append({"shape_id": shape_id, "lane": "bounding_sphere", "centre_cm": centre, "radius_cm": radius})
            else:
                # Ignore baseline bound defects; reject only a new outside-sphere movement.
                for vertex, row in vertices.items():
                    if "POSITION" in row:
                        old_distance = math.dist(original_positions[vertex], centre)
                        require(math.dist(wanted_positions[vertex], centre) <= max(radius, old_distance) + 0.01,
                                f"shape {shape_id}: vertex exceeds its culling sphere; explicitly authorize --bounds")
        if shape_id in uv_constants or any("TEXCOORD_0" in row for row in vertices.values()):
            scale, offset = lanes.uv_scale, lanes.uv_offset
            widened = [False, False]
            require(uv_targets is not None, "source has no proved UV lane")
            if shape_id in uv_constants:
                stored = struct.pack("<4f", *uv_constants[shape_id])
                result[lanes.record_offset + 0x30:lanes.record_offset + 0x40] = stored
                new_scale, new_offset = models.read_uv_constant(result, lanes.record_offset)
                widened = [new_scale[a] != scale[a] or new_offset[a] != offset[a] for a in range(2)]
                scale, offset = new_scale, new_offset
                ranges.append((lanes.record_offset + 0x30, lanes.record_offset + 0x40))
                edit_receipts.append({"shape_id": shape_id, "lane": "uv_constant", "scale": scale,
                                      "offset": offset, "explicit": True})
            elif shape_id in rescale_uvs:
                scale, offset, widened = models.fit_uv_range(uv_targets, scale, offset)
                if any(widened):
                    struct.pack_into("<4f", result, lanes.record_offset + 0x30, *scale, *offset)
                    # Encode against the actually stored binary32 constants.
                    scale, offset = models.read_uv_constant(result, lanes.record_offset)
                    ranges.append((lanes.record_offset + 0x30, lanes.record_offset + 0x40))
                    edit_receipts.append({"shape_id": shape_id, "lane": "uv_constant", "scale": scale, "offset": offset})
            for vertex, target in enumerate(uv_targets):
                is_edited = "TEXCOORD_0" in vertices.get(vertex, {})
                if not is_edited and not any(widened):
                    continue
                require(all(models.uv_in_range(target[axis], scale[axis], offset[axis]) for axis in range(2)),
                        f"shape {shape_id}: UV exceeds stored range; explicitly authorize --rescale-uvs")
                encoded = list(models.uv_from_gltf(*target, scale, offset))
                for axis in range(2):
                    if not is_edited and not widened[axis]:
                        encoded[axis] = original_uvs[vertex][axis]
                at = models._stream_base(scene, shape, lanes.texcoord[0]) + vertex * lanes.texcoord[2] + lanes.texcoord[1]
                struct.pack_into("<2h", result, at, *encoded)
                ranges.append((at, at + 4))
                edit_receipts.append({"shape_id": shape_id, "vertex_id": vertex, "lane": "uv", "offset": at, "length": 4})
    proof = scope_proof(decoded, bytes(result), ranges)
    if bytes(result) == decoded:
        target_span, compression = source_span, {"unchanged": True, "stored": len(source_span) - 32}
    else:
        target_span, compression = builder.fixed_span_chunk(
            "SCNE", bytes(result), resource.word_08, resource.word_0c, source_span)
    require(len(target_span) == len(source_span), "stored SCNE allocation moved")
    chunk, _, current_decoded = stadium(data)
    current_span = span_bytes(data, chunk)
    require(chunk.offset == manifest["chunk_offset"] and len(current_span) == manifest["chunk_length"],
            "stadium stored span moved since export")
    require(sha(current_span) in {sha(source_span), sha(target_span)},
            "unexpected input stadium hash; export the composed intermediate input before geometry import")
    already_applied = current_span == target_span
    output = data[:chunk.offset] + target_span + data[chunk.offset + len(current_span):]
    require(len(output) == len(data) and output[:chunk.offset] == data[:chunk.offset]
            and output[chunk.offset + len(current_span):] == data[chunk.offset + len(current_span):],
            "bundle bytes changed outside the exact stored stadium SCNE span")
    back_chunk, _, readback = stadium(output)
    require(readback == bytes(result) and back_chunk.stored_size == chunk.stored_size,
            "native compressed SCNE readback differs from intended decoded geometry")
    actual_proof = scope_proof(current_decoded, readback, ranges)
    receipt = {
        "schema": RECEIPT_SCHEMA, "disc_file": manifest["disc_file"], "outer_index": manifest["outer_index"],
        "before_sha256": sha(data), "after_sha256": sha(output), "already_applied": already_applied,
        "source_span_sha256": sha(source_span), "before_span_sha256": sha(current_span), "after_span_sha256": sha(target_span),
        "offset": chunk.offset, "length": len(target_span), "compression": compression,
        "decoded_before_sha256": sha(current_decoded), "decoded_after_sha256": sha(readback),
        "prefix_sha256": sha(data[:chunk.offset]), "suffix_sha256": sha(data[chunk.offset + len(current_span):]),
        "outside_stored_span_identical": True, "readback_exact": True, "decoded_scope": actual_proof,
        "compiled_source_scope": proof,
        "position_shapes": sorted(positions), "uv_shapes": sorted(uvs),
        "rescale_uv_shapes": sorted(rescale_uvs), "bounds_shapes": sorted(bounds),
        "explicit_uv_constants": uv_constants,
        "edits": edit_receipts, "geometry_authored_by_tool": False, "gameplay_witness": False,
    }
    return output, receipt


def write_atomic(path: Path, payload: bytes) -> None:
    path = Path(path)
    require(not path.is_symlink(), f"refusing symlink destination: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates binary descriptors; add O_BINARY/O_NOFOLLOW on explicit
    # opens as required by the shared Windows binary-data guard.
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.close(descriptor)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_TRUNC
                             | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        require(path.read_bytes() == payload, "filesystem readback failed")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ids(value: str) -> set[int]:
    try:
        return {int(item) for item in value.split(",") if item}
    except ValueError as exc:
        raise argparse.ArgumentTypeError("shape IDs must be comma-separated integers") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    actions = parser.add_subparsers(dest="action", required=True)
    export = actions.add_parser("export")
    export.add_argument("--input", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--outer-index", type=int, default=0)
    export.add_argument("--expected-sha256")
    apply = actions.add_parser("import", aliases=["apply"])
    apply.add_argument("--input", type=Path, required=True)
    apply.add_argument("--manifest", type=Path, required=True)
    apply.add_argument("--edited", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--receipt", type=Path, required=True)
    for scope in ("positions", "uvs", "rescale-uvs", "bounds"):
        apply.add_argument(f"--{scope}", type=ids, default=set(), metavar="SHAPE_IDS")
    args = parser.parse_args(argv)
    try:
        data = args.input.read_bytes()
        if args.action == "export":
            if args.expected_sha256:
                require(sha(data) == args.expected_sha256, "unexpected input bundle hash")
            document = export_bundle(data, args.input.name, args.out, outer_index=args.outer_index)
            print(json.dumps({"manifest": str(args.out / "manifest.json"), "disc_file": args.input.name,
                              "shapes": len(document["shapes"]), "sha256": document["bundle_sha256"]}))
        else:
            require(args.input.resolve() != args.output.resolve(), "write to a new scratch file, preserving the input")
            require(args.receipt.resolve() != args.output.resolve(), "receipt and game output must differ")
            protected = {args.input.resolve(), args.manifest.resolve(), args.edited.resolve()}
            protected.update((args.manifest.parent / name).resolve()
                             for name in ("source.scne", "baseline.gltf", "baseline.bin"))
            # glTF positions and embedded images may use an external .bin.
            # Protect that coordinator-authored source as well as its JSON.
            from urllib.parse import unquote
            for gltf_path in (args.edited, args.manifest.parent / "baseline.gltf"):
                doc = json.loads(gltf_path.read_text(encoding="utf-8"))
                for buffer in doc.get("buffers", []):
                    uri = buffer.get("uri")
                    if isinstance(uri, str) and not uri.startswith("data:"):
                        protected.add((gltf_path.parent / unquote(uri)).resolve())
            require(args.output.resolve() not in protected and args.receipt.resolve() not in protected,
                    "output/receipt must preserve every input and pinned geometry source artifact")
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            require(args.input.name == manifest.get("disc_file"), "input disc-file name differs from export identity")
            output, receipt = compile_bundle(data, args.manifest, args.edited, positions=args.positions,
                                            uvs=args.uvs, rescale_uvs=args.rescale_uvs, bounds=args.bounds)
            write_atomic(args.output, output)
            write_atomic(args.receipt, json_bytes(receipt))
            print(json.dumps({"output": str(args.output), "receipt": str(args.receipt),
                              "sha256": receipt["after_sha256"], "already_applied": receipt["already_applied"]}))
    except (ValueError, OSError, KeyError, struct.error) as exc:
        print(f"s1_geometry: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
