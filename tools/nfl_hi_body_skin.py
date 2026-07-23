#!/usr/bin/env python3
"""Extract and attach the exact NFL 2K5 hi_body/HI_res 62-joint skin.

This bounded exporter reopens outer 3 chunk 114, resolves every SHORT1
selector through the executable-proved per-submesh palette contract, expands
all 2/3-source CPU blend records, attaches dense glTF JOINTS_0/WEIGHTS_0 and
translation-only inverse binds to the existing static HI_res glTF, and emits
separate raw-centimeter and meter-space derivatives.  It emits no animation
and invents no gameplay external root or player profile.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_gltf import decode_batches
from nfl_scne_inventory import read_name, resolve_relative


SCHEMA = "nfl2k5_hi_body_skin/v1"
TARGET_OUTER = 3
TARGET_CHUNK = 114
TARGET_OUTER_ID = "0x8ee9eeed"
TARGET_DECODED_SHA256 = "43c95e150c72805b419e05db3cff6cacc69c56791c349caa2f0456782775893b"
TARGET_SCENE = "hi_body"
TARGET_SHAPE = "HI_res"
TARGET_VERTICES = 7396
TARGET_TRANSFORMS = 62
TARGET_BLENDS = 139
TARGET_SUBMESHES = 86
PALETTE_SLOTS = 56
REMAP_SENTINEL = 0x7F7F


class HiSkinError(ValueError):
    """A source proof, serialized record, or output invariant differs."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": file_sha256(path)}


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def align4(binary: bytearray) -> None:
    binary.extend(bytes((-len(binary)) & 3))


def load_json(path: Path, schema: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != schema:
        raise HiSkinError(f"{path}: expected schema {schema!r}")
    return value


def pointer(data: bytes, field: int, limit: int, label: str) -> int:
    target = resolve_relative(data, field, limit, label)
    if target is None:
        raise HiSkinError(f"{label}: null relative pointer")
    return target


def pointer_name(data: bytes, field: int, limit: int, label: str) -> str:
    target = pointer(data, field, limit, label)
    value = read_name(data, target, limit, label)
    if value is None:
        raise HiSkinError(f"{label}: null name")
    return value


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def validate_upstream_contracts(args: argparse.Namespace) -> dict[str, object]:
    semantics = load_json(args.transform_semantics, "nfl2k5_transform_semantics/v1")
    contract = semantics["proved_contract"]
    expected = {
        "transform_record_stride": 112,
        "absolute_bind_translation_offset": "0x40",
        "parent_local_bind_translation_offset": "0x50",
        "name_pointer_offset": "0x60",
        "parent_index_offset": "0x64",
        "cpu_blend_record_stride": "0x1c",
        "full_palette_condition": "base_count + cpu_blend_count < 56",
        "remap_table_offset": "submesh +0x08, 56 u16 global palette indices",
        "remap_sentinel": "0x7f7f",
        "vertex_selector_format": "SHORT1",
        "vertex_selector_equation": "local_matrix_slot = v1.x / 3",
        "global_palette_contract": "indices below base_count select one transform; later indices select a CPU blend record",
        "row_vector_inverse_bind": None,
    }
    for key, wanted in expected.items():
        if wanted is not None and contract.get(key) != wanted:
            raise HiSkinError(f"transform-semantics contract {key} differs")
    corpus = semantics["corpus"]
    if not (
        corpus["base_transform_count_distribution"].get("62") == 1
        and corpus["cpu_blend_count_distribution"].get("139") == 1
        and corpus["counts"]["cross_submesh_mapping_conflict_count"] == 0
        and corpus["counts"]["remapped_unreferenced_vertex_count"] == 0
    ):
        raise HiSkinError("transform-semantics corpus uniqueness/conflict contract differs")

    rest = load_json(args.rest_orientation, "nfl2k5_rest_orientation/v1")
    if not (
        rest["proved_contract"]["rest_local_rotation"]
        == "identity quaternion [1,0,0,0]; rest local node transform is identity rotation plus +0x50.xyz translation"
        and rest["proved_contract"]["row_vector_inverse_bind"]
        == "T(-transform[+0x40].xyz)"
        and rest["corpus"]["counts"]["transform_count"] == 110318
    ):
        raise HiSkinError("rest-orientation contract differs")

    axis = load_json(args.axis_report, "nfl2k5_axis_root_motion/v1")
    if axis["proved_contract"]["gltf_basis"] != (
        "game and glTF are both right-handed and Y-up; retain XYZ/quaternion lanes "
        "and multiply all position translations by 0.01 for meters"
    ):
        raise HiSkinError("axis/unit contract differs")

    post = load_json(args.player_postprocess, "nfl2k5_player_postprocess/v1")
    high = post["asset_sources"]["hi_body"]
    if not (
        high["resource"] == [3, 114]
        and high["shape_name"] == TARGET_SHAPE
        and high["decoded_sha256"] == TARGET_DECODED_SHA256
        and post["counts"]["high_transforms"] == TARGET_TRANSFORMS
        and post["matrix_contract"]["all_high_matrices_have_a_local_writer"] is True
        and post["matrix_contract"]["all_high_matrices_have_a_current_scale_source"] is True
    ):
        raise HiSkinError("player high-matrix ownership contract differs")
    high_names = [row["high_name"] for row in read_tsv(args.player_transforms)]
    if len(high_names) != TARGET_TRANSFORMS:
        raise HiSkinError("player high-transform TSV count differs")
    return {
        "transform_semantics": semantics,
        "rest_orientation": rest,
        "axis": axis,
        "player_postprocess": post,
        "high_names": high_names,
    }


def decode_target(args: argparse.Namespace) -> tuple[bytes, dict[str, object], object]:
    archive = parse_archive(args.index)
    inventory, resources = parse_inventory(args.resource_inventory)
    del inventory
    matches = [
        item for item in resources
        if item.kind == "SCNE" and item.outer_index == TARGET_OUTER
        and item.chunk_index == TARGET_CHUNK
    ]
    if len(matches) != 1:
        raise HiSkinError(f"expected one target SCNE resource, found {len(matches)}")
    resource = matches[0]
    if resource.outer_id != TARGET_OUTER_ID:
        raise HiSkinError("target outer ID differs")
    entry = archive.entries[TARGET_OUTER]
    span = read_entry_range(
        archive, entry, resource.chunk_offset, 0x20 + resource.stored_size
    )
    output, detail = decode_resource(span, resource)
    if detail["decoded_sha256"] != TARGET_DECODED_SHA256 or len(output) != 312064:
        raise HiSkinError("target decoded identity differs")
    return output, detail, resource


def parse_target(
    output: bytes,
    detail: dict[str, object],
    resource: object,
    high_names: list[str],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]],
           list[dict[str, object]], list[dict[str, object]]]:
    limit = len(output)
    if output[0x0C:0x10] != b"SCNE":
        raise HiSkinError("decoded target lacks SCNE marker")
    scene_name = pointer_name(output, 0x10, limit, "scene name")
    descriptor = pointer(output, 0x14, limit, "scene descriptor")
    shape_count = struct.unpack_from("<I", output, descriptor + 0x2C)[0]
    shape_table = pointer(output, descriptor + 0x30, limit, "shape table")
    if scene_name != TARGET_SCENE or shape_count != 1:
        raise HiSkinError("target scene name/shape count differs")
    shape = shape_table
    shape_name = pointer_name(output, shape + 0x40, limit, "shape name")
    version = struct.unpack_from("<I", output, shape + 0x44)[0]
    vertex_count = struct.unpack_from("<H", output, shape + 0x4C)[0]
    base_count, blend_count, submesh_count = struct.unpack_from("<HHH", output, shape + 0x50)
    if (shape_name, version, vertex_count, base_count, blend_count, submesh_count) != (
        TARGET_SHAPE, 2, TARGET_VERTICES, TARGET_TRANSFORMS,
        TARGET_BLENDS, TARGET_SUBMESHES,
    ):
        raise HiSkinError("target shape/count contract differs")
    transform_start = pointer(output, shape + 0x64, limit, "transform table")
    blend_start = pointer(output, shape + 0x60, limit, "blend table")
    submesh_start = pointer(output, shape + 0x70, limit, "submesh table")
    if (shape, transform_start, blend_start, submesh_start) != (0x5940, 0x6A00, 0x8520, 0x9454):
        raise HiSkinError("target serialized table offsets differ")

    transforms: list[dict[str, object]] = []
    root_count = 0
    maximum_local_error = 0.0
    for index in range(base_count):
        record = transform_start + index * 0x70
        raw = output[record:record + 0x70]
        absolute = struct.unpack_from("<4f", raw, 0x40)
        local = struct.unpack_from("<4f", raw, 0x50)
        parent = struct.unpack_from("<i", raw, 0x64)[0]
        name = pointer_name(output, record + 0x60, limit, f"transform {index} name")
        if name != high_names[index]:
            raise HiSkinError(f"transform {index} name {name!r} differs from high graph")
        if absolute[3] != 1.0 or local[3] != 1.0:
            raise HiSkinError(f"transform {index} has non-homogeneous bind vector")
        if not all(math.isfinite(value) for value in absolute + local):
            raise HiSkinError(f"transform {index} has non-finite bind vector")
        if parent == -1:
            root_count += 1
            parent_absolute = (0.0, 0.0, 0.0)
        elif not 0 <= parent < index:
            raise HiSkinError(f"transform {index} has invalid parent {parent}")
        else:
            parent_absolute = tuple(transforms[parent][f"absolute_{axis}"] for axis in "xyz")
        expected = tuple(f32(absolute[i] - float(parent_absolute[i])) for i in range(3))
        error = max(abs(local[i] - expected[i]) for i in range(3))
        maximum_local_error = max(maximum_local_error, error)
        if error > 0.00004:
            raise HiSkinError(f"transform {index} local delta error {error}")
        transforms.append({
            "transform_index": index,
            "transform_name": name,
            "parent_index": parent,
            "record_offset": record,
            "record_sha256": sha256(raw),
            "runtime_prefix_sha256": sha256(raw[:0x40]),
            **{f"absolute_{axis}": absolute[i] for i, axis in enumerate("xyzw")},
            **{f"local_{axis}": local[i] for i, axis in enumerate("xyzw")},
            **{f"expected_local_{axis}": expected[i] for i, axis in enumerate("xyz")},
            "maximum_local_delta_error": error,
        })
    if root_count != 1:
        raise HiSkinError(f"target transform roots differ: {root_count}")

    blends: list[dict[str, object]] = []
    blend_values: list[list[tuple[int, float]]] = []
    blend_type_counts: Counter[int] = Counter()
    maximum_blend_error = 0.0
    for index in range(blend_count):
        record = blend_start + index * 0x1C
        raw = output[record:record + 0x1C]
        blend_type = struct.unpack_from("<I", raw)[0]
        if blend_type not in (2, 3):
            raise HiSkinError(f"blend {index} has type {blend_type}")
        active: list[tuple[int, float]] = []
        for source in range(blend_type):
            joint, weight = struct.unpack_from("<If", raw, 4 + source * 8)
            if joint >= base_count or not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
                raise HiSkinError(f"blend {index} source {source} differs")
            active.append((joint, weight))
        if len({joint for joint, _ in active}) != blend_type:
            raise HiSkinError(f"blend {index} repeats a joint")
        sum_error = abs(sum(weight for _, weight in active) - 1.0)
        maximum_blend_error = max(maximum_blend_error, sum_error)
        if sum_error > 0.000001:
            raise HiSkinError(f"blend {index} weight sum error {sum_error}")
        blend_type_counts[blend_type] += 1
        blend_values.append(active)
        row: dict[str, object] = {
            "blend_index": index,
            "global_palette_index": base_count + index,
            "record_offset": record,
            "record_sha256": sha256(raw),
            "blend_type": blend_type,
            "active_weight_sum_error": sum_error,
            "ignored_two_source_tail_hex": raw[0x14:0x1C].hex() if blend_type == 2 else "",
        }
        for slot in range(3):
            if slot < len(active):
                joint, weight = active[slot]
                row[f"joint{slot}_index"] = joint
                row[f"joint{slot}_name"] = transforms[joint]["transform_name"]
                row[f"weight{slot}"] = weight
            else:
                row[f"joint{slot}_index"] = ""
                row[f"joint{slot}_name"] = ""
                row[f"weight{slot}"] = ""
        blends.append(row)
    if blend_type_counts != Counter({2: 113, 3: 26}):
        raise HiSkinError(f"blend type counts differ: {blend_type_counts}")

    encoded_r1 = struct.unpack_from("<I", output, shape + 0x88)[0]
    format_code = encoded_r1 & 0xFF
    stream_index = (encoded_r1 >> 8) & 0xFF
    byte_offset = encoded_r1 >> 16
    stride = struct.unpack_from("<H", output, shape + 0xC4 + stream_index * 2)[0]
    stream_start = pointer(output, shape + 0xD4 + stream_index * 4, limit, "SHORT1 stream")
    if (encoded_r1, format_code, stream_index, byte_offset, stride) != (0x00040115, 0x15, 1, 4, 6):
        raise HiSkinError("SHORT1 descriptor differs")
    selectors = [
        struct.unpack_from("<h", output, stream_start + vertex * stride + byte_offset)[0]
        for vertex in range(vertex_count)
    ]
    if min(selectors) != 0 or max(selectors) != 162 or len(set(selectors)) != 55:
        raise HiSkinError("SHORT1 selector domain differs")
    if any(value < 0 or value % 3 or value // 3 >= PALETTE_SLOTS for value in selectors):
        raise HiSkinError("SHORT1 selector encoding differs")

    resolved: dict[int, int] = {}
    owners: dict[int, list[int]] = defaultdict(list)
    palette_rows: list[dict[str, object]] = []
    repeated_reference_count = 0
    for submesh_index in range(submesh_count):
        submesh = submesh_start + submesh_index * 0x80
        first_slot, last_slot = struct.unpack_from("<HH", output, submesh + 4)
        mappings = struct.unpack_from(f"<{PALETTE_SLOTS}H", output, submesh + 8)
        command_start = pointer(output, submesh + 0x78, limit, f"submesh {submesh_index} commands")
        primary_words = struct.unpack_from("<H", output, submesh + 0x7C)[0]
        if first_slot > last_slot or last_slot >= PALETTE_SLOTS:
            raise HiSkinError(f"submesh {submesh_index} range differs")
        batches = decode_batches(output, command_start, primary_words)
        referenced = {vertex for _, indices in batches for vertex in indices}
        slot_reference_counts: Counter[int] = Counter(selectors[v] // 3 for v in referenced)
        for vertex in sorted(referenced):
            if vertex >= vertex_count:
                raise HiSkinError(f"submesh {submesh_index} vertex {vertex} exceeds shape")
            slot = selectors[vertex] // 3
            global_index = mappings[slot]
            if not first_slot <= slot <= last_slot:
                raise HiSkinError(f"submesh {submesh_index} vertex {vertex} slot outside upload range")
            if global_index == REMAP_SENTINEL or global_index >= base_count + blend_count:
                raise HiSkinError(f"submesh {submesh_index} vertex {vertex} has invalid mapping")
            previous = resolved.get(vertex)
            if previous is not None and previous != global_index:
                raise HiSkinError(f"vertex {vertex} has cross-submesh mapping conflict")
            if previous is not None:
                repeated_reference_count += 1
            resolved[vertex] = global_index
            owners[vertex].append(submesh_index)
        for slot, global_index in enumerate(mappings):
            if global_index == REMAP_SENTINEL:
                kind = "sentinel"
            elif global_index < base_count:
                kind = "base_transform"
            elif global_index < base_count + blend_count:
                kind = "cpu_blend"
            else:
                kind = "opaque_out_of_palette"
            palette_rows.append({
                "submesh_index": submesh_index,
                "submesh_record_offset": submesh,
                "first_uploaded_slot": first_slot,
                "last_uploaded_slot": last_slot,
                "local_palette_slot": slot,
                "inside_uploaded_range": int(first_slot <= slot <= last_slot),
                "global_palette_index": global_index,
                "global_palette_kind": kind,
                "referenced_vertex_count": slot_reference_counts[slot],
            })
    if len(resolved) != vertex_count or set(resolved) != set(range(vertex_count)):
        raise HiSkinError(f"resolved {len(resolved)}/{vertex_count} vertices")
    if repeated_reference_count != 14 or Counter(len(value) for value in owners.values()) != Counter({1: 7382, 2: 14}):
        raise HiSkinError("cross-submesh vertex ownership counts differ")

    influence_rows: list[dict[str, object]] = []
    arities: Counter[int] = Counter()
    used_global: set[int] = set()
    for vertex in range(vertex_count):
        global_index = resolved[vertex]
        used_global.add(global_index)
        if global_index < base_count:
            active = [(global_index, 1.0)]
            kind = "base_transform"
            blend_index: int | str = ""
        else:
            blend_index = global_index - base_count
            active = blend_values[int(blend_index)]
            kind = "cpu_blend"
        arities[len(active)] += 1
        row = {
            "vertex_index": vertex,
            "selector_short1": selectors[vertex],
            "local_palette_slot": selectors[vertex] // 3,
            "owner_submesh_count": len(owners[vertex]),
            "owner_submesh_indices": ",".join(str(value) for value in owners[vertex]),
            "global_palette_index": global_index,
            "global_palette_kind": kind,
            "blend_index": blend_index,
            "influence_count": len(active),
        }
        for slot in range(3):
            if slot < len(active):
                joint, weight = active[slot]
                row[f"joint{slot}_index"] = joint
                row[f"joint{slot}_name"] = transforms[joint]["transform_name"]
                row[f"weight{slot}"] = weight
            else:
                row[f"joint{slot}_index"] = ""
                row[f"joint{slot}_name"] = ""
                row[f"weight{slot}"] = ""
        influence_rows.append(row)
    if arities != Counter({1: 5356, 2: 1921, 3: 119}):
        raise HiSkinError(f"resolved influence counts differ: {arities}")
    if len(used_global) != 181 or min(used_global) != 0 or max(used_global) != 200:
        raise HiSkinError("used global-palette domain differs")

    summary = {
        "scene_name": scene_name,
        "shape_name": shape_name,
        "shape_record_offset": shape,
        "shape_version": version,
        "vertex_count": vertex_count,
        "base_transform_count": base_count,
        "cpu_blend_record_count": blend_count,
        "global_palette_count": base_count + blend_count,
        "submesh_count": submesh_count,
        "palette_upload_mode": "per_submesh_remap",
        "palette_slot_limit": PALETTE_SLOTS,
        "selector_descriptor": f"0x{encoded_r1:08x}",
        "selector_stream_offset": stream_start,
        "selector_stream_stride": stride,
        "selector_byte_offset": byte_offset,
        "selector_min": min(selectors),
        "selector_max": max(selectors),
        "selector_unique_count": len(set(selectors)),
        "resolved_vertex_count": len(resolved),
        "unresolved_vertex_count": vertex_count - len(resolved),
        "cross_submesh_conflict_count": 0,
        "vertices_referenced_by_two_submeshes": 14,
        "used_global_palette_entry_count": len(used_global),
        "influence_arity_counts": {str(key): arities[key] for key in sorted(arities)},
        "blend_type_counts": {str(key): blend_type_counts[key] for key in sorted(blend_type_counts)},
        "maximum_blend_weight_sum_error": maximum_blend_error,
        "maximum_local_parent_delta_error": maximum_local_error,
        "decoded_sha256": detail["decoded_sha256"],
        "decoded_size": detail["decoded_size"],
        "resource_stored_size": resource.stored_size,
        "resource_chunk_offset": resource.chunk_offset,
        "transform_table_offset": transform_start,
        "blend_table_offset": blend_start,
        "submesh_table_offset": submesh_start,
    }
    return summary, transforms, blends, palette_rows, influence_rows


def append_view(gltf: dict[str, object], binary: bytearray, payload: bytes,
                target: int | None = None) -> int:
    align4(binary)
    offset = len(binary)
    binary.extend(payload)
    view: dict[str, object] = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
    if target is not None:
        view["target"] = target
    views = gltf.setdefault("bufferViews", [])
    assert isinstance(views, list)
    result = len(views)
    views.append(view)
    return result


def append_accessor(gltf: dict[str, object], view: int, component_type: int,
                    count: int, type_name: str) -> int:
    accessors = gltf.setdefault("accessors", [])
    assert isinstance(accessors, list)
    result = len(accessors)
    accessors.append({
        "bufferView": view, "byteOffset": 0, "componentType": component_type,
        "count": count, "type": type_name,
    })
    return result


def encode_influences(rows: list[dict[str, object]]) -> tuple[bytes, bytes]:
    joints = bytearray()
    weights = bytearray()
    for row in rows:
        joint_values = [0, 0, 0, 0]
        weight_values = [0.0, 0.0, 0.0, 0.0]
        count = int(row["influence_count"])
        for slot in range(count):
            joint_values[slot] = int(row[f"joint{slot}_index"])
            weight_values[slot] = float(row[f"weight{slot}"])
        joints.extend(struct.pack("<4H", *joint_values))
        weights.extend(struct.pack("<4f", *weight_values))
    return bytes(joints), bytes(weights)


def encode_inverse_binds(transforms: list[dict[str, object]]) -> bytes:
    result = bytearray()
    for item in transforms:
        x, y, z = (float(item[f"absolute_{axis}"]) for axis in "xyz")
        result.extend(struct.pack(
            "<16f",
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            -x, -y, -z, 1.0,
        ))
    return bytes(result)


def accessor_layout(gltf: dict[str, object], accessor_index: int,
                    lane_count: int) -> tuple[dict[str, object], int, int]:
    accessor = gltf["accessors"][accessor_index]
    view = gltf["bufferViews"][int(accessor["bufferView"])]
    component_size = {5123: 2, 5126: 4}[int(accessor["componentType"])]
    stride = int(view.get("byteStride", lane_count * component_size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    return accessor, start, stride


def build_raw_gltf(
    source_gltf_path: Path,
    transforms: list[dict[str, object]],
    influence_rows: list[dict[str, object]],
) -> tuple[dict[str, object], bytes, dict[str, object]]:
    gltf = json.loads(source_gltf_path.read_text(encoding="utf-8"))
    if not (
        gltf.get("asset", {}).get("generator") == "nfl_static_gltf.py"
        and gltf.get("asset", {}).get("extras", {}).get("source", {}).get("outer_index") == 3
        and gltf["asset"]["extras"]["source"]["chunk_index"] == 114
        and gltf["asset"]["extras"]["source"]["decoded_sha256"] == TARGET_DECODED_SHA256
        and not gltf.get("skins") and not gltf.get("animations")
    ):
        raise HiSkinError("source static glTF identity differs")
    buffers = gltf.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1:
        raise HiSkinError("source static glTF buffer contract differs")
    source_bin_path = source_gltf_path.parent / str(buffers[0]["uri"])
    source_binary = source_bin_path.read_bytes()
    if len(source_binary) != int(buffers[0]["byteLength"]):
        raise HiSkinError("source static binary length differs")
    binary = bytearray(source_binary)
    if len(gltf.get("nodes", [])) != 1 or len(gltf.get("meshes", [])) != 1:
        raise HiSkinError("source static HI_res node/mesh count differs")
    mesh_node = gltf["nodes"][0]
    mesh = gltf["meshes"][int(mesh_node["mesh"])]
    if mesh.get("name") != TARGET_SHAPE or len(mesh.get("primitives", [])) != TARGET_SUBMESHES:
        raise HiSkinError("source static HI_res mesh contract differs")
    position_accessors = {int(p["attributes"]["POSITION"]) for p in mesh["primitives"]}
    if len(position_accessors) != 1:
        raise HiSkinError("HI_res primitives do not share one POSITION accessor")
    position_accessor = position_accessors.pop()
    if int(gltf["accessors"][position_accessor]["count"]) != TARGET_VERTICES:
        raise HiSkinError("HI_res POSITION count differs")

    joint_bytes, weight_bytes = encode_influences(influence_rows)
    joint_view = append_view(gltf, binary, joint_bytes, 34962)
    weight_view = append_view(gltf, binary, weight_bytes, 34962)
    inverse_view = append_view(gltf, binary, encode_inverse_binds(transforms))
    joint_accessor = append_accessor(gltf, joint_view, 5123, TARGET_VERTICES, "VEC4")
    weight_accessor = append_accessor(gltf, weight_view, 5126, TARGET_VERTICES, "VEC4")
    inverse_accessor = append_accessor(gltf, inverse_view, 5126, TARGET_TRANSFORMS, "MAT4")
    for primitive in mesh["primitives"]:
        primitive["attributes"]["JOINTS_0"] = joint_accessor
        primitive["attributes"]["WEIGHTS_0"] = weight_accessor

    nodes = gltf["nodes"]
    joint_base = len(nodes)
    roots: list[int] = []
    for item in transforms:
        nodes.append({
            "name": f"HI_res:{int(item['transform_index']):02d}:{item['transform_name']}",
            "translation": [float(item[f"local_{axis}"]) for axis in "xyz"],
            "rotation": [0.0, 0.0, 0.0, 1.0],
            "extras": {
                "source_transform_index": int(item["transform_index"]),
                "source_transform_name": item["transform_name"],
                "source_parent_index": int(item["parent_index"]),
                "serialized_absolute_bind_translation": [
                    float(item[f"absolute_{axis}"]) for axis in "xyz"
                ],
                "raw_game_coordinates": True,
            },
        })
    for item in transforms:
        index = int(item["transform_index"])
        parent = int(item["parent_index"])
        if parent == -1:
            roots.append(joint_base + index)
        else:
            nodes[joint_base + parent].setdefault("children", []).append(joint_base + index)
    if len(roots) != 1:
        raise HiSkinError("generated HI_res skeleton root count differs")
    gltf["skins"] = [{
        "name": "HI_res:62_joint_translation_bind",
        "inverseBindMatrices": inverse_accessor,
        "skeleton": roots[0],
        "joints": [joint_base + index for index in range(TARGET_TRANSFORMS)],
        "extras": {
            "proof_scope": "identity rest rotations, serialized +0x50 local translations, T(-serialized +0x40) inverse binds",
            "external_root_applied": False,
            "animation_count": 0,
        },
    }]
    mesh_node["skin"] = 0
    mesh_node.setdefault("extras", {})["skin_proof"] = (
        "all 7396 SHORT1 selectors resolved through 86 shipped remap tables"
    )
    gltf["scenes"][int(gltf.get("scene", 0))].setdefault("nodes", []).append(roots[0])
    gltf["extras"] = {
        "raw_coordinates": True,
        "proof_scope": "exact outer 3 chunk 114 HI_res static 62-joint skin",
        "animation_emitted": False,
        "external_root_or_live_profile_defaulted": False,
        "portme": [
            "PORTME: attach player animation only through a separately proved concrete controller/external-root/profile path.",
            "PORTME: map materials, textures, normals, and UVs without inventing shader semantics.",
            "PORTME: implement a validated edited-glTF to SCNE/archive writer.",
        ],
    }
    gltf["asset"]["generator"] = "nfl_hi_body_skin.py (source: nfl_static_gltf.py)"
    buffers[0]["byteLength"] = len(binary)
    detail = {
        "source_gltf": str(source_gltf_path),
        "source_gltf_sha256": file_sha256(source_gltf_path),
        "source_bin": str(source_bin_path),
        "source_bin_sha256": file_sha256(source_bin_path),
        "source_binary_prefix_bytes": len(source_binary),
        "position_accessor": position_accessor,
        "joint_accessor": joint_accessor,
        "weight_accessor": weight_accessor,
        "inverse_bind_accessor": inverse_accessor,
        "mesh_node_index": 0,
        "skeleton_root_node_index": roots[0],
    }
    return gltf, bytes(binary), detail


def write_gltf_pair(gltf: dict[str, object], binary: bytes, output_dir: Path,
                    stem: str) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    bin_path = output_dir / f"{stem}.bin"
    gltf_path = output_dir / f"{stem}.gltf"
    gltf["buffers"][0]["uri"] = bin_path.name
    gltf["buffers"][0]["byteLength"] = len(binary)
    gltf_bytes = (json.dumps(gltf, indent=2, sort_keys=True) + "\n").encode("utf-8")
    bin_path.write_bytes(binary)
    gltf_path.write_bytes(gltf_bytes)
    return {
        "gltf": gltf_path.name,
        "gltf_sha256": sha256(gltf_bytes),
        "gltf_bytes": len(gltf_bytes),
        "bin": bin_path.name,
        "bin_sha256": sha256(binary),
        "bin_bytes": len(binary),
    }


def meter_derivative(raw: dict[str, object], raw_binary: bytes,
                     position_accessor: int, inverse_accessor: int) -> tuple[dict[str, object], bytes]:
    meter = copy.deepcopy(raw)
    binary = bytearray(raw_binary)
    accessor, start, stride = accessor_layout(meter, position_accessor, 3)
    for index in range(int(accessor["count"])):
        offset = start + index * stride
        values = struct.unpack_from("<3f", binary, offset)
        struct.pack_into("<3f", binary, offset, *(f32(value * 0.01) for value in values))
    for key in ("min", "max"):
        if key in accessor:
            accessor[key] = [f32(float(value) * 0.01) for value in accessor[key]]

    inverse, start, stride = accessor_layout(meter, inverse_accessor, 16)
    for index in range(int(inverse["count"])):
        offset = start + index * stride
        values = list(struct.unpack_from("<16f", binary, offset))
        for lane in (12, 13, 14):
            values[lane] = f32(values[lane] * 0.01)
        struct.pack_into("<16f", binary, offset, *values)

    for node in meter["nodes"]:
        if "translation" in node:
            node["translation"] = [f32(float(value) * 0.01) for value in node["translation"]]
            extras = node.get("extras", {})
            if "serialized_absolute_bind_translation" in extras:
                extras["serialized_absolute_bind_translation"] = [
                    f32(float(value) * 0.01)
                    for value in extras["serialized_absolute_bind_translation"]
                ]
                extras["raw_game_coordinates"] = False
    meter["asset"]["generator"] = "nfl_hi_body_skin.py meter derivative"
    meter["extras"] = {
        **meter["extras"],
        "raw_coordinates": False,
        "coordinate_contract": {
            "source": "right_handed_y_up_centimeters",
            "target": "right_handed_y_up_meters",
            "axis_mapping": "XYZ_to_XYZ",
            "linear_scale": 0.01,
        },
    }
    return meter, bytes(binary)


def generate(args: argparse.Namespace) -> dict[str, object]:
    upstream = validate_upstream_contracts(args)
    output, decode_detail, resource = decode_target(args)
    summary, transforms, blends, palettes, influences = parse_target(
        output, decode_detail, resource, upstream["high_names"]
    )
    write_tsv(args.transforms_tsv, transforms, [
        "transform_index", "transform_name", "parent_index", "record_offset",
        "record_sha256", "runtime_prefix_sha256",
        "absolute_x", "absolute_y", "absolute_z", "absolute_w",
        "local_x", "local_y", "local_z", "local_w",
        "expected_local_x", "expected_local_y", "expected_local_z",
        "maximum_local_delta_error",
    ])
    write_tsv(args.blends_tsv, blends, [
        "blend_index", "global_palette_index", "record_offset", "record_sha256",
        "blend_type", "active_weight_sum_error", "ignored_two_source_tail_hex",
        "joint0_index", "joint0_name", "weight0",
        "joint1_index", "joint1_name", "weight1",
        "joint2_index", "joint2_name", "weight2",
    ])
    write_tsv(args.palettes_tsv, palettes, [
        "submesh_index", "submesh_record_offset", "first_uploaded_slot",
        "last_uploaded_slot", "local_palette_slot", "inside_uploaded_range",
        "global_palette_index", "global_palette_kind", "referenced_vertex_count",
    ])
    write_tsv(args.influences_tsv, influences, [
        "vertex_index", "selector_short1", "local_palette_slot",
        "owner_submesh_count", "owner_submesh_indices", "global_palette_index",
        "global_palette_kind", "blend_index", "influence_count",
        "joint0_index", "joint0_name", "weight0",
        "joint1_index", "joint1_name", "weight1",
        "joint2_index", "joint2_name", "weight2",
    ])

    raw_gltf, raw_binary, gltf_detail = build_raw_gltf(
        args.source_gltf, transforms, influences
    )
    raw_output = write_gltf_pair(raw_gltf, raw_binary, args.output_dir,
                                 "0003_0114_hi_body_raw_skin")
    meter_gltf, meter_binary = meter_derivative(
        raw_gltf, raw_binary, int(gltf_detail["position_accessor"]),
        int(gltf_detail["inverse_bind_accessor"]),
    )
    meter_output = write_gltf_pair(meter_gltf, meter_binary, args.output_dir,
                                   "0003_0114_hi_body_meter_skin")

    report = {
        "schema": SCHEMA,
        "source": {
            "index": str(args.index),
            "outer_index": TARGET_OUTER,
            "outer_id": TARGET_OUTER_ID,
            "chunk_index": TARGET_CHUNK,
            "resource_chunk_offset": resource.chunk_offset,
            "resource_stored_size": resource.stored_size,
            "decoded_size": decode_detail["decoded_size"],
            "decoded_sha256": decode_detail["decoded_sha256"],
            "decode_detail": decode_detail,
        },
        "serialized_skin": summary,
        "xbox_semantics": {
            "executable_md5": upstream["transform_semantics"]["executable"]["md5"],
            "executable_sha256": upstream["transform_semantics"]["executable"]["sha256"],
            "function_ranges": [
                item for item in upstream["transform_semantics"]["executable"]["function_ranges"]
                if item["name"] in {
                    "blend_two_matrices", "blend_three_matrices",
                    "upload_full_palette", "upload_remapped_palette",
                    "build_skin_palette", "render_shape",
                }
            ],
            "shader_object_count": upstream["transform_semantics"]["executable"]["shader_object_count"],
            "shader_arl_a0x_v1x_count": upstream["transform_semantics"]["executable"]["shader_arl_a0x_v1x_count"],
            "vertex_selector_equation": upstream["transform_semantics"]["proved_contract"]["vertex_selector_equation"],
            "full_palette_condition": upstream["transform_semantics"]["proved_contract"]["full_palette_condition"],
            "global_palette_contract": upstream["transform_semantics"]["proved_contract"]["global_palette_contract"],
            "cpu_blend_record_equation": upstream["transform_semantics"]["proved_contract"]["cpu_blend_record_equation"],
            "base_skin_palette_equation": upstream["transform_semantics"]["proved_contract"]["base_skin_palette_equation"],
        },
        "gltf_contract": {
            **gltf_detail,
            "joint_component_type": "UNSIGNED_SHORT",
            "weight_component_type": "FLOAT",
            "joint_weight_accessor_count": TARGET_VERTICES,
            "inverse_bind_count": TARGET_TRANSFORMS,
            "inverse_bind_equation": "T(-serialized_absolute_bind_translation)",
            "rest_rotation": "identity xyzw [0,0,0,1]",
            "raw_coordinate_basis": "right_handed_y_up_centimeters",
            "meter_coordinate_basis": "right_handed_y_up_meters",
            "axis_mapping": "XYZ_to_XYZ",
            "meter_scale": 0.01,
            "animation_count": 0,
            "live_profile_or_external_root_defaulted": False,
        },
        "outputs": {
            "raw": raw_output,
            "meter": meter_output,
        },
        "proof_tsvs": {
            "transforms": {"path": args.transforms_tsv.name, "sha256": file_sha256(args.transforms_tsv)},
            "blends": {"path": args.blends_tsv.name, "sha256": file_sha256(args.blends_tsv)},
            "palettes": {"path": args.palettes_tsv.name, "sha256": file_sha256(args.palettes_tsv)},
            "influences": {"path": args.influences_tsv.name, "sha256": file_sha256(args.influences_tsv)},
        },
        "source_pins": {
            "source_index": pin(args.index),
            "resource_inventory": pin(args.resource_inventory),
            "transform_semantics": pin(args.transform_semantics),
            "rest_orientation": pin(args.rest_orientation),
            "axis_report": pin(args.axis_report),
            "player_postprocess": pin(args.player_postprocess),
            "player_transforms": pin(args.player_transforms),
            "source_gltf": pin(args.source_gltf),
            "source_bin": pin(args.source_gltf.parent / json.loads(args.source_gltf.read_text(encoding="utf-8"))["buffers"][0]["uri"]),
        },
        "ownership_result": {
            "hi_body_HI_res_static_skin_attachment_proved": True,
            "all_62_serialized_joints_attached": True,
            "all_7396_vertices_resolved": True,
            "all_86_submesh_remap_tables_applied": True,
            "all_139_cpu_blend_records_bounded": True,
            "static_skin_blockers": [],
            "animation_or_live_root_claimed": False,
        },
        "worked": [
            "decoded the unique shipped 62-transform/139-blend HI_res SCNE shape",
            "resolved all 7396 SHORT1 selectors through 86 per-submesh remap tables with zero conflicts",
            "expanded every referenced base or two/three-source CPU blend entry into dense glTF influences",
            "attached all 62 serialized transforms, parents, local binds, and inverse binds without modifying the canonical static source",
            "emitted raw-centimeter and right-handed Y-up meter-space Blender-readable derivatives",
        ],
        "failed": [],
        "blockers": {
            "static_hi_body_skin": [],
            "outside_this_static_scope": [
                "concrete gameplay selector/playback mode and live external-root values",
                "concrete player profile/scalar values consumed by 0x00093850",
                "animation interpolation and root-motion attachment",
                "materials, textures, normals, UVs, and edited-asset archive writing",
            ],
        },
        "portme": [
            "// PORTME: do not attach animation until a concrete player controller/external-root/profile path is proved.",
            "// PORTME: map materials, textures, normals, UVs, and shader/sampler behavior.",
            "// PORTME: implement and validate edited glTF to SCNE/archive writing.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--resource-inventory", type=Path, required=True)
    parser.add_argument("--transform-semantics", type=Path, required=True)
    parser.add_argument("--rest-orientation", type=Path, required=True)
    parser.add_argument("--axis-report", type=Path, required=True)
    parser.add_argument("--player-postprocess", type=Path, required=True)
    parser.add_argument("--player-transforms", type=Path, required=True)
    parser.add_argument("--source-gltf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--transforms-tsv", type=Path, required=True)
    parser.add_argument("--blends-tsv", type=Path, required=True)
    parser.add_argument("--palettes-tsv", type=Path, required=True)
    parser.add_argument("--influences-tsv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        report = generate(args)
    except (HiSkinError, OSError, ValueError, KeyError, IndexError, struct.error,
            json.JSONDecodeError) as exc:
        print(f"nfl_hi_body_skin: {exc}", file=sys.stderr)
        return 1
    summary = report["serialized_skin"]
    print(
        "NFL_HI_BODY_SKIN_COMPLETE "
        f"joints={summary['base_transform_count']} vertices={summary['vertex_count']} "
        f"blends={summary['cpu_blend_record_count']} submeshes={summary['submesh_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
