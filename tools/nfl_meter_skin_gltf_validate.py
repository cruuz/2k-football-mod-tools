#!/usr/bin/env python3
"""Independently validate the NFL raw-centimeter to glTF-meter skin conversion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Any


SCHEMA = "nfl2k5_meter_skin_gltf_manifest/v1"


class ValidationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def same_f32(left: float, right: float) -> bool:
    return struct.pack("<f", left) == struct.pack("<f", right)


def layout(gltf: dict[str, Any], index: int, components: int) -> tuple[dict[str, Any], int, int]:
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][int(accessor["bufferView"])]
    if int(view.get("buffer", 0)) != 0 or "sparse" in accessor:
        raise ValidationError("unsupported accessor layout")
    stride = int(view.get("byteStride", components * 4))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    return accessor, start, stride


def positions(gltf: dict[str, Any]) -> set[int]:
    return {
        int(primitive["attributes"]["POSITION"])
        for mesh in gltf["meshes"]
        for primitive in mesh["primitives"]
    }


def inverse_accessors(gltf: dict[str, Any]) -> set[int]:
    return {int(skin["inverseBindMatrices"]) for skin in gltf["skins"]}


def read_matrix(binary: bytes, gltf: dict[str, Any], accessor_index: int,
                item: int) -> tuple[float, ...]:
    accessor, start, stride = layout(gltf, accessor_index, 16)
    if accessor["type"] != "MAT4" or int(accessor["componentType"]) != 5126:
        raise ValidationError("inverse bind is not FLOAT MAT4")
    return struct.unpack_from("<16f", binary, start + item * stride)


def parent_indices(nodes: list[dict[str, Any]]) -> list[int]:
    parents = [-1] * len(nodes)
    for parent, node in enumerate(nodes):
        for child_raw in node.get("children", []):
            child = int(child_raw)
            if not 0 <= child < len(nodes) or parents[child] != -1:
                raise ValidationError("node has invalid/multiple parent")
            parents[child] = parent
    return parents


def global_translation(nodes: list[dict[str, Any]], parents: list[int],
                       node_index: int, cache: dict[int, tuple[float, float, float]],
                       visiting: set[int]) -> tuple[float, float, float]:
    if node_index in cache:
        return cache[node_index]
    if node_index in visiting:
        raise ValidationError("node hierarchy cycle")
    visiting.add(node_index)
    local_raw = nodes[node_index].get("translation", [0.0, 0.0, 0.0])
    local = tuple(float(value) for value in local_raw)
    parent = parents[node_index]
    if parent == -1:
        result = local
    else:
        above = global_translation(nodes, parents, parent, cache, visiting)
        result = tuple(f32(above[axis] + local[axis]) for axis in range(3))
    visiting.remove(node_index)
    cache[node_index] = result
    return result


def validate_pair(row: dict[str, Any], raw_dir: Path,
                  meter_dir: Path) -> dict[str, int]:
    raw_gltf_path = raw_dir / row["source_gltf"]
    raw_bin_path = raw_dir / row["source_bin"]
    meter_gltf_path = meter_dir / row["output_gltf"]
    meter_bin_path = meter_dir / row["output_bin"]
    expected_hashes = {
        raw_gltf_path: row["source_gltf_sha256"],
        raw_bin_path: row["source_bin_sha256"],
        meter_gltf_path: row["output_gltf_sha256"],
        meter_bin_path: row["output_bin_sha256"],
    }
    for path, expected in expected_hashes.items():
        if sha256_file(path) != expected:
            raise ValidationError(f"hash mismatch: {path}")

    raw = json.loads(raw_gltf_path.read_text(encoding="utf-8"))
    meter = json.loads(meter_gltf_path.read_text(encoding="utf-8"))
    raw_binary = raw_bin_path.read_bytes()
    meter_binary = meter_bin_path.read_bytes()
    if len(raw_binary) != len(meter_binary):
        raise ValidationError("buffer size changed")
    if raw["scene"] != meter["scene"] or raw["scenes"] != meter["scenes"]:
        raise ValidationError("scene roots changed")
    if len(raw["nodes"]) != len(meter["nodes"]) or len(raw["meshes"]) != len(meter["meshes"]):
        raise ValidationError("node/mesh count changed")
    if positions(raw) != positions(meter) or inverse_accessors(raw) != inverse_accessors(meter):
        raise ValidationError("accessor ownership changed")
    if meter.get("animations", []) != []:
        raise ValidationError("conversion invented animation")
    contract = meter.get("extras", {}).get("coordinate_contract", {})
    if contract != {
        "source": "right_handed_y_up_centimeters",
        "target": "right_handed_y_up_meters",
        "axis_mapping": "XYZ_to_XYZ",
        "linear_scale": 0.01,
        "quaternion_storage_if_animated": "game_wxyz_to_gltf_xyzw",
    }:
        raise ValidationError("meter coordinate contract differs")

    allowed: set[int] = set()
    position_values = 0
    for index in sorted(positions(raw)):
        raw_accessor, raw_start, raw_stride = layout(raw, index, 3)
        meter_accessor, meter_start, meter_stride = layout(meter, index, 3)
        if raw_start != meter_start or raw_stride != meter_stride or raw_accessor["count"] != meter_accessor["count"]:
            raise ValidationError("POSITION layout changed")
        count = int(raw_accessor["count"])
        for item in range(count):
            offset = raw_start + item * raw_stride
            raw_values = struct.unpack_from("<3f", raw_binary, offset)
            meter_values = struct.unpack_from("<3f", meter_binary, offset)
            for lane in range(3):
                if not same_f32(meter_values[lane], f32(raw_values[lane] * 0.01)):
                    raise ValidationError("POSITION scale mismatch")
                allowed.update(range(offset + lane * 4, offset + lane * 4 + 4))
        for key in ("min", "max"):
            if key in raw_accessor:
                expected = [f32(float(value) * 0.01) for value in raw_accessor[key]]
                if len(expected) != len(meter_accessor.get(key, [])) or any(
                    not same_f32(float(actual), wanted)
                    for actual, wanted in zip(meter_accessor[key], expected)
                ):
                    raise ValidationError(f"POSITION {key} scale mismatch")
        position_values += count

    inverse_count = 0
    for index in sorted(inverse_accessors(raw)):
        raw_accessor, raw_start, raw_stride = layout(raw, index, 16)
        meter_accessor, meter_start, meter_stride = layout(meter, index, 16)
        if raw_start != meter_start or raw_stride != meter_stride or raw_accessor["count"] != meter_accessor["count"]:
            raise ValidationError("inverse-bind layout changed")
        count = int(raw_accessor["count"])
        for item in range(count):
            offset = raw_start + item * raw_stride
            raw_values = struct.unpack_from("<16f", raw_binary, offset)
            meter_values = struct.unpack_from("<16f", meter_binary, offset)
            for lane in range(16):
                expected = f32(raw_values[lane] * 0.01) if lane in (12, 13, 14) else raw_values[lane]
                if not same_f32(meter_values[lane], expected):
                    raise ValidationError("inverse-bind conversion mismatch")
                if lane in (12, 13, 14):
                    allowed.update(range(offset + lane * 4, offset + lane * 4 + 4))
        inverse_count += count

    for offset, (before, after) in enumerate(zip(raw_binary, meter_binary)):
        if offset not in allowed and before != after:
            raise ValidationError(f"unapproved binary change at {offset}")

    translated = 0
    for raw_node, meter_node in zip(raw["nodes"], meter["nodes"]):
        if raw_node.get("name") != meter_node.get("name") or raw_node.get("children", []) != meter_node.get("children", []):
            raise ValidationError("node identity/hierarchy changed")
        if "translation" in raw_node:
            translated += 1
            expected = [f32(float(value) * 0.01) for value in raw_node["translation"]]
            if any(not same_f32(float(actual), wanted)
                   for actual, wanted in zip(meter_node["translation"], expected)):
                raise ValidationError("node translation scale mismatch")

    meter_nodes = meter["nodes"]
    parents = parent_indices(meter_nodes)
    cache: dict[int, tuple[float, float, float]] = {}
    cancellations = 0
    for skin in meter["skins"]:
        joints = [int(value) for value in skin["joints"]]
        accessor_index = int(skin["inverseBindMatrices"])
        accessor = meter["accessors"][accessor_index]
        if int(accessor["count"]) != len(joints):
            raise ValidationError("joint/inverse-bind count differs")
        for item, joint in enumerate(joints):
            global_value = global_translation(meter_nodes, parents, joint, cache, set())
            matrix = read_matrix(meter_binary, meter, accessor_index, item)
            for lane in range(3):
                if abs(global_value[lane] + matrix[12 + lane]) > 2.0e-6:
                    raise ValidationError("meter rest cancellation failed")
            cancellations += 1

    expected_counts = {
        "position_value_count": position_values,
        "inverse_bind_count": inverse_count,
        "translated_node_count": translated,
        "skin_count": len(meter["skins"]),
        "joint_count": sum(len(skin["joints"]) for skin in meter["skins"]),
        "animation_count": 0,
    }
    for key, expected in expected_counts.items():
        if int(row[key]) != expected:
            raise ValidationError(f"manifest {key} differs")
    return {**expected_counts, "rest_cancellations": cancellations}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--meter-dir", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.manifest.read_text(encoding="utf-8"))
    if report.get("schema") != SCHEMA:
        raise ValidationError("manifest schema differs")
    contract = report.get("contract", {})
    if not (
        contract.get("source_basis") == "right_handed_y_up"
        and contract.get("target_basis") == "right_handed_y_up"
        and contract.get("axis_mapping") == "XYZ_to_XYZ"
        and contract.get("source_linear_unit") == "centimeter"
        and contract.get("target_linear_unit") == "meter"
        and contract.get("linear_scale") == 0.01
        and contract.get("animation_emitted") is False
    ):
        raise ValidationError("manifest conversion contract differs")
    outputs = report.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 3:
        raise ValidationError("expected three outputs")
    totals = {key: 0 for key in (
        "skin_count", "joint_count", "position_value_count",
        "inverse_bind_count", "animation_count", "rest_cancellations"
    )}
    for row in outputs:
        result = validate_pair(row, args.raw_dir, args.meter_dir)
        for key in totals:
            totals[key] += result[key]
    summary = report.get("summary", {})
    for key in ("skin_count", "joint_count", "position_value_count",
                "inverse_bind_count", "animation_count"):
        if int(summary.get(key, -1)) != totals[key]:
            raise ValidationError(f"summary {key} differs")
    if int(summary.get("scene_count", -1)) != 3:
        raise ValidationError("summary scene count differs")
    if not isinstance(report.get("portme"), list) or not all(
        str(line).startswith("PORTME:") for line in report["portme"]
    ):
        raise ValidationError("PORTME list is missing")
    print(
        "NFL_METER_SKIN_GLTF_STRUCTURAL_PASS "
        f"scenes=3 skins={totals['skin_count']} joints={totals['joint_count']} "
        f"positions={totals['position_value_count']} "
        f"rest_cancellations={totals['rest_cancellations']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
