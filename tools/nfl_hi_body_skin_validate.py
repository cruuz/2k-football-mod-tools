#!/usr/bin/env python3
"""Independently validate the exact NFL 2K5 HI_res 62-joint glTF skin."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_gltf import decode_batches
from nfl_scne_inventory import read_name, resolve_relative


SCHEMA = "nfl2k5_hi_body_skin/v1"
DECODED_SHA = "43c95e150c72805b419e05db3cff6cacc69c56791c349caa2f0456782775893b"
VERTICES = 7396
JOINTS = 62
BLENDS = 139
SUBMESHES = 86
SLOTS = 56
SENTINEL = 0x7F7F


class ValidationError(ValueError):
    """An independently decoded source or output differs."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def pointer(data: bytes, field: int, limit: int, label: str) -> int:
    value = resolve_relative(data, field, limit, label)
    if value is None:
        raise ValidationError(f"{label}: null pointer")
    return value


def name_at(data: bytes, field: int, limit: int, label: str) -> str:
    value = read_name(data, pointer(data, field, limit, label), limit, label)
    if value is None:
        raise ValidationError(f"{label}: null name")
    return value


def decode_source(index: Path, inventory: Path) -> tuple[bytes, object]:
    archive = parse_archive(index)
    _, resources = parse_inventory(inventory)
    matches = [r for r in resources if r.kind == "SCNE" and r.outer_index == 3 and r.chunk_index == 114]
    if len(matches) != 1:
        raise ValidationError("target resource count differs")
    resource = matches[0]
    span = read_entry_range(
        archive, archive.entries[3], resource.chunk_offset,
        0x20 + resource.stored_size,
    )
    output, detail = decode_resource(span, resource)
    if detail["decoded_sha256"] != DECODED_SHA or len(output) != 312064:
        raise ValidationError("target decoded identity differs")
    return output, resource


def same_float(raw: str, value: float) -> bool:
    return bits(float(raw)) == bits(value)


def independently_decode(
    output: bytes,
    transforms_tsv: list[dict[str, str]],
    blends_tsv: list[dict[str, str]],
    palettes_tsv: list[dict[str, str]],
    influences_tsv: list[dict[str, str]],
) -> dict[str, object]:
    limit = len(output)
    descriptor = pointer(output, 0x14, limit, "descriptor")
    shape = pointer(output, descriptor + 0x30, limit, "shape table")
    if name_at(output, 0x10, limit, "scene") != "hi_body" or name_at(output, shape + 0x40, limit, "shape") != "HI_res":
        raise ValidationError("target scene/shape names differ")
    vertex_count = struct.unpack_from("<H", output, shape + 0x4C)[0]
    base_count, blend_count, submesh_count = struct.unpack_from("<HHH", output, shape + 0x50)
    if (vertex_count, base_count, blend_count, submesh_count) != (VERTICES, JOINTS, BLENDS, SUBMESHES):
        raise ValidationError("target shape counts differ")
    transform_start = pointer(output, shape + 0x64, limit, "transforms")
    blend_start = pointer(output, shape + 0x60, limit, "blends")
    submesh_start = pointer(output, shape + 0x70, limit, "submeshes")
    if len(transforms_tsv) != JOINTS or len(blends_tsv) != BLENDS:
        raise ValidationError("transform/blend TSV row count differs")

    transforms: list[dict[str, object]] = []
    max_local_error = 0.0
    for index, row in enumerate(transforms_tsv):
        record = transform_start + index * 0x70
        raw = output[record:record + 0x70]
        absolute = struct.unpack_from("<4f", raw, 0x40)
        local = struct.unpack_from("<4f", raw, 0x50)
        parent = struct.unpack_from("<i", raw, 0x64)[0]
        name = name_at(output, record + 0x60, limit, f"transform {index}")
        if not (
            int(row["transform_index"]) == index
            and int(row["parent_index"]) == parent
            and row["transform_name"] == name
            and int(row["record_offset"]) == record
            and row["record_sha256"] == sha256(raw)
            and row["runtime_prefix_sha256"] == sha256(raw[:0x40])
        ):
            raise ValidationError(f"transform TSV identity differs at {index}")
        for lane, axis in enumerate("xyzw"):
            if not same_float(row[f"absolute_{axis}"], absolute[lane]) or not same_float(row[f"local_{axis}"], local[lane]):
                raise ValidationError(f"transform TSV vector differs at {index}:{axis}")
        parent_absolute = (0.0, 0.0, 0.0) if parent == -1 else tuple(
            float(transforms[parent][f"absolute_{axis}"]) for axis in "xyz"
        )
        expected = tuple(f32(absolute[i] - parent_absolute[i]) for i in range(3))
        error = max(abs(local[i] - expected[i]) for i in range(3))
        max_local_error = max(max_local_error, error)
        if error > 0.00004:
            raise ValidationError(f"transform local-parent error at {index}")
        transforms.append({
            "name": name, "parent": parent,
            **{f"absolute_{axis}": absolute[i] for i, axis in enumerate("xyz")},
            **{f"local_{axis}": local[i] for i, axis in enumerate("xyz")},
        })

    blend_values: list[list[tuple[int, float]]] = []
    blend_types: Counter[int] = Counter()
    max_weight_error = 0.0
    for index, row in enumerate(blends_tsv):
        record = blend_start + index * 0x1C
        raw = output[record:record + 0x1C]
        arity = struct.unpack_from("<I", raw)[0]
        active = [struct.unpack_from("<If", raw, 4 + slot * 8) for slot in range(arity)]
        if not (
            int(row["blend_index"]) == index
            and int(row["global_palette_index"]) == JOINTS + index
            and int(row["record_offset"]) == record
            and row["record_sha256"] == sha256(raw)
            and int(row["blend_type"]) == arity
        ):
            raise ValidationError(f"blend TSV identity differs at {index}")
        for slot, (joint, weight) in enumerate(active):
            if int(row[f"joint{slot}_index"]) != joint or row[f"joint{slot}_name"] != transforms[joint]["name"] or not same_float(row[f"weight{slot}"], weight):
                raise ValidationError(f"blend TSV source differs at {index}:{slot}")
        tail = raw[0x14:0x1C].hex() if arity == 2 else ""
        if row["ignored_two_source_tail_hex"] != tail:
            raise ValidationError(f"blend TSV ignored tail differs at {index}")
        error = abs(sum(weight for _, weight in active) - 1.0)
        max_weight_error = max(max_weight_error, error)
        if error > 0.000001:
            raise ValidationError(f"blend weight sum differs at {index}")
        blend_types[arity] += 1
        blend_values.append(active)
    if blend_types != Counter({2: 113, 3: 26}):
        raise ValidationError("blend type distribution differs")

    encoded = struct.unpack_from("<I", output, shape + 0x88)[0]
    stream = (encoded >> 8) & 0xFF
    byte_offset = encoded >> 16
    stride = struct.unpack_from("<H", output, shape + 0xC4 + stream * 2)[0]
    stream_start = pointer(output, shape + 0xD4 + stream * 4, limit, "selector stream")
    selectors = [struct.unpack_from("<h", output, stream_start + i * stride + byte_offset)[0] for i in range(VERTICES)]

    expected_palette_rows: list[dict[str, object]] = []
    resolved: dict[int, int] = {}
    owners: dict[int, list[int]] = defaultdict(list)
    for submesh_index in range(SUBMESHES):
        record = submesh_start + submesh_index * 0x80
        first, last = struct.unpack_from("<HH", output, record + 4)
        mappings = struct.unpack_from(f"<{SLOTS}H", output, record + 8)
        command = pointer(output, record + 0x78, limit, f"submesh {submesh_index} commands")
        words = struct.unpack_from("<H", output, record + 0x7C)[0]
        referenced = {v for _, indices in decode_batches(output, command, words) for v in indices}
        slot_counts: Counter[int] = Counter(selectors[v] // 3 for v in referenced)
        for vertex in sorted(referenced):
            slot = selectors[vertex] // 3
            global_index = mappings[slot]
            if not first <= slot <= last or global_index == SENTINEL or global_index >= JOINTS + BLENDS:
                raise ValidationError(f"invalid submesh mapping at {submesh_index}:{vertex}")
            if vertex in resolved and resolved[vertex] != global_index:
                raise ValidationError(f"mapping conflict at vertex {vertex}")
            resolved[vertex] = global_index
            owners[vertex].append(submesh_index)
        for slot, global_index in enumerate(mappings):
            if global_index == SENTINEL:
                kind = "sentinel"
            elif global_index < JOINTS:
                kind = "base_transform"
            elif global_index < JOINTS + BLENDS:
                kind = "cpu_blend"
            else:
                kind = "opaque_out_of_palette"
            expected_palette_rows.append({
                "submesh_index": submesh_index,
                "submesh_record_offset": record,
                "first_uploaded_slot": first,
                "last_uploaded_slot": last,
                "local_palette_slot": slot,
                "inside_uploaded_range": int(first <= slot <= last),
                "global_palette_index": global_index,
                "global_palette_kind": kind,
                "referenced_vertex_count": slot_counts[slot],
            })
    if len(expected_palette_rows) != SUBMESHES * SLOTS or len(palettes_tsv) != len(expected_palette_rows):
        raise ValidationError("palette TSV row count differs")
    for expected, row in zip(expected_palette_rows, palettes_tsv, strict=True):
        for key, value in expected.items():
            if row[key] != str(value):
                raise ValidationError(f"palette TSV differs at {expected['submesh_index']}:{expected['local_palette_slot']}:{key}")
    if len(resolved) != VERTICES or Counter(len(v) for v in owners.values()) != Counter({1: 7382, 2: 14}):
        raise ValidationError("resolved vertex ownership differs")

    if len(influences_tsv) != VERTICES:
        raise ValidationError("influence TSV row count differs")
    arities: Counter[int] = Counter()
    for vertex, row in enumerate(influences_tsv):
        global_index = resolved[vertex]
        active = [(global_index, 1.0)] if global_index < JOINTS else blend_values[global_index - JOINTS]
        expected_identity = {
            "vertex_index": vertex,
            "selector_short1": selectors[vertex],
            "local_palette_slot": selectors[vertex] // 3,
            "owner_submesh_count": len(owners[vertex]),
            "owner_submesh_indices": ",".join(str(v) for v in owners[vertex]),
            "global_palette_index": global_index,
            "global_palette_kind": "base_transform" if global_index < JOINTS else "cpu_blend",
            "blend_index": "" if global_index < JOINTS else global_index - JOINTS,
            "influence_count": len(active),
        }
        for key, value in expected_identity.items():
            if row[key] != str(value):
                raise ValidationError(f"influence TSV differs at vertex {vertex}:{key}")
        for slot, (joint, weight) in enumerate(active):
            if int(row[f"joint{slot}_index"]) != joint or row[f"joint{slot}_name"] != transforms[joint]["name"] or not same_float(row[f"weight{slot}"], weight):
                raise ValidationError(f"influence TSV source differs at vertex {vertex}:{slot}")
        arities[len(active)] += 1
    if arities != Counter({1: 5356, 2: 1921, 3: 119}):
        raise ValidationError("influence arity distribution differs")
    return {
        "transforms": transforms,
        "influences": influences_tsv,
        "max_local_error": max_local_error,
        "max_weight_error": max_weight_error,
        "arities": arities,
    }


def accessor_layout(gltf: dict[str, object], index: int, lanes: int) -> tuple[dict[str, object], int, int]:
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][int(accessor["bufferView"])]
    component_size = {5123: 2, 5126: 4}[int(accessor["componentType"])]
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    stride = int(view.get("byteStride", lanes * component_size))
    return accessor, start, stride


def read_vec(binary: bytes, gltf: dict[str, object], accessor_index: int,
             item: int, fmt: str, lanes: int) -> tuple[float | int, ...]:
    _, start, stride = accessor_layout(gltf, accessor_index, lanes)
    return struct.unpack_from(fmt, binary, start + item * stride)


def node_parents(nodes: list[dict[str, object]]) -> list[int]:
    parents = [-1] * len(nodes)
    for parent, node in enumerate(nodes):
        for child in node.get("children", []):
            child = int(child)
            if parents[child] != -1:
                raise ValidationError("node has multiple parents")
            parents[child] = parent
    return parents


def global_translation(nodes: list[dict[str, object]], parents: list[int], index: int,
                       cache: dict[int, tuple[float, float, float]]) -> tuple[float, float, float]:
    if index in cache:
        return cache[index]
    local = tuple(float(v) for v in nodes[index].get("translation", [0.0, 0.0, 0.0]))
    parent = parents[index]
    if parent == -1:
        result = local
    else:
        above = global_translation(nodes, parents, parent, cache)
        result = tuple(above[i] + local[i] for i in range(3))
    cache[index] = result
    return result


def validate_gltf(
    gltf_path: Path,
    bin_path: Path,
    output_row: dict[str, object],
    proof: dict[str, object],
    meter: bool,
) -> dict[str, object]:
    if sha256_file(gltf_path) != output_row["gltf_sha256"] or sha256_file(bin_path) != output_row["bin_sha256"]:
        raise ValidationError(f"output hash differs: {gltf_path}")
    gltf = json.loads(gltf_path.read_text(encoding="utf-8"))
    binary = bin_path.read_bytes()
    if not (
        gltf.get("asset", {}).get("version") == "2.0"
        and len(gltf.get("skins", [])) == 1
        and gltf.get("animations") in (None, [])
        and gltf["buffers"][0]["uri"] == bin_path.name
        and int(gltf["buffers"][0]["byteLength"]) == len(binary)
        and len(gltf["nodes"]) == 63
        and len(gltf["meshes"]) == 1
    ):
        raise ValidationError(f"top-level glTF contract differs: {gltf_path}")
    mesh_node = gltf["nodes"][0]
    if int(mesh_node["skin"]) != 0:
        raise ValidationError("HI_res mesh node skin differs")
    mesh = gltf["meshes"][int(mesh_node["mesh"])]
    if mesh["name"] != "HI_res" or len(mesh["primitives"]) != SUBMESHES:
        raise ValidationError("HI_res mesh/primitive count differs")
    joint_accessors = {int(p["attributes"]["JOINTS_0"]) for p in mesh["primitives"]}
    weight_accessors = {int(p["attributes"]["WEIGHTS_0"]) for p in mesh["primitives"]}
    position_accessors = {int(p["attributes"]["POSITION"]) for p in mesh["primitives"]}
    if len(joint_accessors) != 1 or len(weight_accessors) != 1 or len(position_accessors) != 1:
        raise ValidationError("shared skin accessor ownership differs")
    joint_accessor = joint_accessors.pop()
    weight_accessor = weight_accessors.pop()
    position_accessor = position_accessors.pop()
    if not (
        gltf["accessors"][joint_accessor]["componentType"] == 5123
        and gltf["accessors"][joint_accessor]["type"] == "VEC4"
        and gltf["accessors"][weight_accessor]["componentType"] == 5126
        and gltf["accessors"][weight_accessor]["type"] == "VEC4"
        and int(gltf["accessors"][joint_accessor]["count"]) == VERTICES
        and int(gltf["accessors"][weight_accessor]["count"]) == VERTICES
    ):
        raise ValidationError("JOINTS_0/WEIGHTS_0 accessor contract differs")
    skin = gltf["skins"][0]
    joint_nodes = [int(value) for value in skin["joints"]]
    inverse_accessor = int(skin["inverseBindMatrices"])
    if len(joint_nodes) != JOINTS or int(gltf["accessors"][inverse_accessor]["count"]) != JOINTS or int(skin["skeleton"]) != joint_nodes[0]:
        raise ValidationError("skin joint/inverse count differs")

    transforms = proof["transforms"]
    nodes = gltf["nodes"]
    parents = node_parents(nodes)
    cache: dict[int, tuple[float, float, float]] = {}
    residuals: list[tuple[float, float, float]] = []
    max_cancellation = 0.0
    scale = 0.01 if meter else 1.0
    for index, node_index in enumerate(joint_nodes):
        node = nodes[node_index]
        expected_parent_node = -1 if int(transforms[index]["parent"]) == -1 else joint_nodes[int(transforms[index]["parent"])]
        if (
            node["extras"]["source_transform_index"] != index
            or node["extras"]["source_transform_name"] != transforms[index]["name"]
            or int(node["extras"]["source_parent_index"]) != int(transforms[index]["parent"])
            or parents[node_index] != expected_parent_node
            or [float(value) for value in node.get("rotation", [])] != [0.0, 0.0, 0.0, 1.0]
        ):
            raise ValidationError(f"joint node identity differs at {index}")
        wanted_local = [f32(float(transforms[index][f"local_{axis}"]) * scale) if meter else float(transforms[index][f"local_{axis}"]) for axis in "xyz"]
        if any(bits(float(a)) != bits(float(b)) for a, b in zip(node["translation"], wanted_local, strict=True)):
            raise ValidationError(f"joint local translation differs at {index}")
        global_value = global_translation(nodes, parents, node_index, cache)
        inverse = read_vec(binary, gltf, inverse_accessor, index, "<16f", 16)
        absolute = [
            f32(float(transforms[index][f"absolute_{axis}"]) * scale)
            if meter else float(transforms[index][f"absolute_{axis}"])
            for axis in "xyz"
        ]
        expected_inverse = (
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            -absolute[0], -absolute[1], -absolute[2], 1.0,
        )
        if any(bits(float(actual)) != bits(float(wanted))
               for actual, wanted in zip(inverse, expected_inverse, strict=True)):
            raise ValidationError(f"inverse-bind matrix differs at {index}")
        residual = tuple(global_value[lane] + float(inverse[12 + lane]) for lane in range(3))
        max_cancellation = max(max_cancellation, *(abs(v) for v in residual))
        residuals.append(residual)
    tolerance = 5.0e-5 if not meter else 7.0e-7
    if max_cancellation > tolerance:
        raise ValidationError(f"rest cancellation {max_cancellation} exceeds {tolerance}")

    max_weight_sum_error = 0.0
    max_rest_vertex_error = 0.0
    for vertex, row in enumerate(proof["influences"]):
        joints = read_vec(binary, gltf, joint_accessor, vertex, "<4H", 4)
        weights = read_vec(binary, gltf, weight_accessor, vertex, "<4f", 4)
        count = int(row["influence_count"])
        expected_joints = [0, 0, 0, 0]
        expected_weights = [0.0, 0.0, 0.0, 0.0]
        for slot in range(count):
            expected_joints[slot] = int(row[f"joint{slot}_index"])
            expected_weights[slot] = float(row[f"weight{slot}"])
        if tuple(expected_joints) != joints or any(bits(expected_weights[i]) != bits(float(weights[i])) for i in range(4)):
            raise ValidationError(f"glTF influences differ at vertex {vertex}")
        max_weight_sum_error = max(max_weight_sum_error, abs(sum(float(w) for w in weights) - 1.0))
        position = read_vec(binary, gltf, position_accessor, vertex, "<3f", 3)
        deformed = [0.0, 0.0, 0.0]
        for slot in range(count):
            joint = int(joints[slot])
            weight = float(weights[slot])
            for lane in range(3):
                deformed[lane] += weight * (float(position[lane]) + residuals[joint][lane])
        max_rest_vertex_error = max(
            max_rest_vertex_error,
            *(abs(deformed[lane] - float(position[lane])) for lane in range(3)),
        )
    if max_weight_sum_error > 1.0e-6 or max_rest_vertex_error > tolerance:
        raise ValidationError("weighted rest deformation differs")
    return {
        "gltf": gltf,
        "binary": binary,
        "position_accessor": position_accessor,
        "inverse_accessor": inverse_accessor,
        "joint_accessor": joint_accessor,
        "weight_accessor": weight_accessor,
        "max_cancellation": max_cancellation,
        "max_rest_vertex_error": max_rest_vertex_error,
        "max_weight_sum_error": max_weight_sum_error,
    }


def validate_static_attachment(source_path: Path, raw: dict[str, object]) -> None:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    generated = raw["gltf"]
    if source["accessors"] != generated["accessors"][:len(source["accessors"])]:
        raise ValidationError("static source accessor prefix changed")
    if source["bufferViews"] != generated["bufferViews"][:len(source["bufferViews"])]:
        raise ValidationError("static source buffer-view prefix changed")
    if len(source["meshes"]) != len(generated["meshes"]):
        raise ValidationError("static source mesh count changed")
    for source_mesh, generated_mesh in zip(source["meshes"], generated["meshes"], strict=True):
        candidate = json.loads(json.dumps(generated_mesh))
        for primitive in candidate["primitives"]:
            primitive["attributes"].pop("JOINTS_0", None)
            primitive["attributes"].pop("WEIGHTS_0", None)
        if candidate != source_mesh:
            raise ValidationError("static source mesh/topology metadata changed")
    source_node = source["nodes"][0]
    generated_node = generated["nodes"][0]
    if source_node["name"] != generated_node["name"] or source_node["mesh"] != generated_node["mesh"]:
        raise ValidationError("static source mesh node identity changed")
    for key, value in source_node.get("extras", {}).items():
        if generated_node.get("extras", {}).get(key) != value:
            raise ValidationError(f"static source node extra changed: {key}")
    source_roots = source["scenes"][int(source.get("scene", 0))]["nodes"]
    generated_roots = generated["scenes"][int(generated.get("scene", 0))]["nodes"]
    if generated_roots[:len(source_roots)] != source_roots:
        raise ValidationError("static source scene roots changed")


def validate_meter_conversion(raw: dict[str, object], meter: dict[str, object]) -> None:
    raw_gltf = raw["gltf"]
    meter_gltf = meter["gltf"]
    raw_binary = raw["binary"]
    meter_binary = meter["binary"]
    if len(raw_binary) != len(meter_binary):
        raise ValidationError("meter binary size changed")
    allowed: set[int] = set()
    raw_position = int(raw["position_accessor"])
    meter_position = int(meter["position_accessor"])
    raw_accessor, raw_start, raw_stride = accessor_layout(raw_gltf, raw_position, 3)
    meter_accessor, meter_start, meter_stride = accessor_layout(meter_gltf, meter_position, 3)
    if (raw_start, raw_stride, raw_accessor["count"]) != (meter_start, meter_stride, meter_accessor["count"]):
        raise ValidationError("meter POSITION layout changed")
    for item in range(VERTICES):
        ro = raw_start + item * raw_stride
        mo = meter_start + item * meter_stride
        before = struct.unpack_from("<3f", raw_binary, ro)
        after = struct.unpack_from("<3f", meter_binary, mo)
        for lane in range(3):
            if bits(float(after[lane])) != bits(f32(float(before[lane]) * 0.01)):
                raise ValidationError(f"meter position differs at {item}:{lane}")
            allowed.update(range(ro + lane * 4, ro + lane * 4 + 4))
    for key in ("min", "max"):
        expected = [f32(float(v) * 0.01) for v in raw_accessor[key]]
        if any(bits(float(a)) != bits(float(b)) for a, b in zip(meter_accessor[key], expected, strict=True)):
            raise ValidationError(f"meter POSITION {key} differs")

    raw_inverse = int(raw["inverse_accessor"])
    meter_inverse = int(meter["inverse_accessor"])
    _, raw_start, raw_stride = accessor_layout(raw_gltf, raw_inverse, 16)
    _, meter_start, meter_stride = accessor_layout(meter_gltf, meter_inverse, 16)
    if (raw_start, raw_stride) != (meter_start, meter_stride):
        raise ValidationError("meter inverse-bind layout changed")
    for item in range(JOINTS):
        ro = raw_start + item * raw_stride
        before = struct.unpack_from("<16f", raw_binary, ro)
        after = struct.unpack_from("<16f", meter_binary, ro)
        for lane in range(16):
            wanted = f32(float(before[lane]) * 0.01) if lane in (12, 13, 14) else float(before[lane])
            if bits(float(after[lane])) != bits(wanted):
                raise ValidationError(f"meter inverse bind differs at {item}:{lane}")
            if lane in (12, 13, 14):
                allowed.update(range(ro + lane * 4, ro + lane * 4 + 4))
    for offset, (before, after) in enumerate(zip(raw_binary, meter_binary, strict=True)):
        if offset not in allowed and before != after:
            raise ValidationError(f"unapproved meter binary change at {offset}")
    if raw_binary[126252:] == b"" or raw_binary[126252:] == meter_binary[126252:]:
        # Inverse binds must change; joints and weights remain equal.
        raise ValidationError("meter appended payload change boundary differs")


def validate(args: argparse.Namespace) -> dict[str, object]:
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("schema") != SCHEMA:
        raise ValidationError("report schema differs")
    for value in report["source_pins"].values():
        path = Path(value["path"])
        if sha256_file(path) != value["sha256"]:
            raise ValidationError(f"source pin differs: {path}")
    proof_paths = {
        "transforms": args.transforms_tsv,
        "blends": args.blends_tsv,
        "palettes": args.palettes_tsv,
        "influences": args.influences_tsv,
    }
    for key, path in proof_paths.items():
        if sha256_file(path) != report["proof_tsvs"][key]["sha256"]:
            raise ValidationError(f"proof TSV hash differs: {key}")
    transforms = read_tsv(args.transforms_tsv)
    blends = read_tsv(args.blends_tsv)
    palettes = read_tsv(args.palettes_tsv)
    influences = read_tsv(args.influences_tsv)
    output, _ = decode_source(args.index, args.resource_inventory)
    proof = independently_decode(output, transforms, blends, palettes, influences)

    source_bin = Path(report["gltf_contract"]["source_bin"])
    raw_row = report["outputs"]["raw"]
    meter_row = report["outputs"]["meter"]
    raw_gltf = args.asset_dir / raw_row["gltf"]
    raw_bin = args.asset_dir / raw_row["bin"]
    meter_gltf = args.asset_dir / meter_row["gltf"]
    meter_bin = args.asset_dir / meter_row["bin"]
    if raw_bin.read_bytes()[: source_bin.stat().st_size] != source_bin.read_bytes():
        raise ValidationError("raw output does not retain static binary as exact prefix")
    raw = validate_gltf(raw_gltf, raw_bin, raw_row, proof, False)
    validate_static_attachment(Path(report["gltf_contract"]["source_gltf"]), raw)
    meter = validate_gltf(meter_gltf, meter_bin, meter_row, proof, True)
    validate_meter_conversion(raw, meter)

    ownership = report["ownership_result"]
    if ownership != {
        "all_139_cpu_blend_records_bounded": True,
        "all_62_serialized_joints_attached": True,
        "all_7396_vertices_resolved": True,
        "all_86_submesh_remap_tables_applied": True,
        "animation_or_live_root_claimed": False,
        "hi_body_HI_res_static_skin_attachment_proved": True,
        "static_skin_blockers": [],
    }:
        raise ValidationError("ownership result differs")
    return {
        "max_local_parent_error": proof["max_local_error"],
        "max_blend_weight_error": proof["max_weight_error"],
        "raw_max_rest_cancellation": raw["max_cancellation"],
        "meter_max_rest_cancellation": meter["max_cancellation"],
        "raw_max_rest_vertex_error": raw["max_rest_vertex_error"],
        "meter_max_rest_vertex_error": meter["max_rest_vertex_error"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--transforms-tsv", type=Path, required=True)
    parser.add_argument("--blends-tsv", type=Path, required=True)
    parser.add_argument("--palettes-tsv", type=Path, required=True)
    parser.add_argument("--influences-tsv", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--resource-inventory", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(args)
    except (ValidationError, OSError, ValueError, KeyError, IndexError,
            struct.error, json.JSONDecodeError) as exc:
        print(f"nfl_hi_body_skin_validate: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_HI_BODY_SKIN_STRUCTURAL_PASS "
        f"joints={JOINTS} vertices={VERTICES} blends={BLENDS} submeshes={SUBMESHES} "
        f"raw_rest_error={result['raw_max_rest_vertex_error']:.9g} "
        f"meter_rest_error={result['meter_max_rest_vertex_error']:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
