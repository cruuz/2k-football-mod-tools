#!/usr/bin/env python3
"""Independently validate the bounded NFL raw-skin glTF proof files."""

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
from typing import Iterable


SCHEMA = "nfl2k5_raw_skin_gltf_manifest/v2"
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
FORMATS = {5123: ("H", 2), 5126: ("f", 4)}


class ValidationError(ValueError):
    """A generated skin, buffer, or retained source invariant failed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def load_proofs(
    transforms_path: Path,
    influences_path: Path,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    transforms: dict[str, list[dict[str, object]]] = defaultdict(list)
    for raw in read_tsv(transforms_path):
        transforms[raw["sample"]].append(
            {
                "index": int(raw["transform_index"]),
                "name": raw["transform_name"],
                "parent": int(raw["parent_index"]),
                "absolute": tuple(float(raw[f"absolute_{axis}"]) for axis in "xyz"),
                "local": tuple(float(raw[f"local_{axis}"]) for axis in "xyz"),
            }
        )
    for rows in transforms.values():
        rows.sort(key=lambda item: int(item["index"]))

    influences: dict[str, list[dict[str, object]]] = defaultdict(list)
    for raw in read_tsv(influences_path):
        active = [
            (int(raw[f"joint{slot}_index"]), float(raw[f"weight{slot}"]))
            for slot in range(int(raw["influence_count"]))
        ]
        influences[raw["sample"]].append(
            {"vertex": int(raw["vertex_index"]), "active": active}
        )
    for rows in influences.values():
        rows.sort(key=lambda item: int(item["vertex"]))
    return dict(transforms), dict(influences)


def accessor_values(
    gltf: dict[str, object],
    binary: bytes,
    accessor_index: int,
) -> list[tuple[int | float, ...]]:
    accessors = gltf["accessors"]
    views = gltf["bufferViews"]
    accessor = accessors[accessor_index]
    if "sparse" in accessor:
        raise ValidationError("sparse accessors are outside this proof")
    component_type = int(accessor["componentType"])
    if component_type not in FORMATS:
        raise ValidationError(f"unsupported component type {component_type}")
    format_code, component_size = FORMATS[component_type]
    component_count = COMPONENTS[str(accessor["type"])]
    view = views[int(accessor["bufferView"])]
    if int(view.get("buffer", 0)) != 0:
        raise ValidationError("nonzero glTF buffer index")
    element_size = component_size * component_count
    stride = int(view.get("byteStride", element_size))
    if stride < element_size:
        raise ValidationError("accessor byteStride is too small")
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    count = int(accessor["count"])
    if count and start + (count - 1) * stride + element_size > len(binary):
        raise ValidationError("accessor exceeds binary buffer")
    unpack = struct.Struct("<" + format_code * component_count)
    return [unpack.unpack_from(binary, start + index * stride) for index in range(count)]


def validate_source_prefix(
    output: dict[str, object],
    gltf: dict[str, object],
    binary: bytes,
    workspace: Path,
) -> None:
    source_gltf_path = workspace / str(output["source_gltf"])
    source_bin_path = workspace / str(output["source_bin"])
    if sha256_file(source_gltf_path) != output["source_gltf_sha256"]:
        raise ValidationError("source glTF hash differs")
    if sha256_file(source_bin_path) != output["source_bin_sha256"]:
        raise ValidationError("source binary hash differs")
    source_gltf = json.loads(source_gltf_path.read_text(encoding="utf-8"))
    source_binary = source_bin_path.read_bytes()
    if not binary.startswith(source_binary):
        raise ValidationError("generated binary does not preserve the source prefix")
    if gltf["bufferViews"][:len(source_gltf["bufferViews"])] != source_gltf["bufferViews"]:
        raise ValidationError("source buffer views changed")
    if gltf["accessors"][:len(source_gltf["accessors"])] != source_gltf["accessors"]:
        raise ValidationError("source accessors changed")
    if len(gltf["meshes"]) != len(source_gltf["meshes"]):
        raise ValidationError("source mesh count changed")
    for generated_mesh, source_mesh in zip(
        gltf["meshes"], source_gltf["meshes"], strict=True
    ):
        if generated_mesh["name"] != source_mesh["name"]:
            raise ValidationError("source mesh name changed")
        if len(generated_mesh["primitives"]) != len(source_mesh["primitives"]):
            raise ValidationError("source primitive count changed")
        for generated, source in zip(
            generated_mesh["primitives"], source_mesh["primitives"], strict=True
        ):
            retained = {
                key: value for key, value in generated["attributes"].items()
                if key not in ("JOINTS_0", "WEIGHTS_0")
            }
            if retained != source["attributes"]:
                raise ValidationError("source primitive attributes changed")
            for field in ("indices", "mode"):
                if generated.get(field) != source.get(field):
                    raise ValidationError(f"source primitive {field} changed")


def validate_skin(
    gltf: dict[str, object],
    binary: bytes,
    detail: dict[str, object],
    transforms: list[dict[str, object]],
    influences: list[dict[str, object]],
) -> tuple[int, Counter[int], float]:
    sample = str(detail["sample"])
    mesh_node = gltf["nodes"][int(detail["mesh_node_index"])]
    skin = gltf["skins"][int(mesh_node["skin"])]
    joint_nodes = [int(value) for value in skin["joints"]]
    if len(joint_nodes) != 25 or len(transforms) != 25:
        raise ValidationError(f"{sample}: joint count differs")
    if int(skin["skeleton"]) != joint_nodes[0]:
        raise ValidationError(f"{sample}: skeleton root differs")

    child_parent: dict[int, int] = {}
    for node_index in joint_nodes:
        for child in gltf["nodes"][node_index].get("children", []):
            if int(child) in child_parent:
                raise ValidationError(f"{sample}: joint has two parents")
            child_parent[int(child)] = node_index

    global_translations: list[tuple[float, float, float]] = []
    for index, (node_index, proof) in enumerate(
        zip(joint_nodes, transforms, strict=True)
    ):
        node = gltf["nodes"][node_index]
        if node["name"] != f"{sample}:{proof['name']}":
            raise ValidationError(f"{sample}: joint {index} name differs")
        local = tuple(float(value) for value in node["translation"])
        if any(
            f32_bits(actual) != f32_bits(wanted)
            for actual, wanted in zip(local, proof["local"], strict=True)
        ):
            raise ValidationError(f"{sample}: joint {index} local translation differs")
        parent = int(proof["parent"])
        if parent == -1:
            if node_index in child_parent:
                raise ValidationError(f"{sample}: root unexpectedly has a parent")
            parent_global = (0.0, 0.0, 0.0)
        else:
            if child_parent.get(node_index) != joint_nodes[parent]:
                raise ValidationError(f"{sample}: joint {index} hierarchy differs")
            parent_global = global_translations[parent]
        current = tuple(
            f32(parent_global[axis] + local[axis]) for axis in range(3)
        )
        if any(
            f32_bits(actual) != f32_bits(wanted)
            for actual, wanted in zip(current, proof["absolute"], strict=True)
        ):
            raise ValidationError(f"{sample}: joint {index} rest hierarchy differs")
        global_translations.append(current)

    inverse = accessor_values(
        gltf, binary, int(skin["inverseBindMatrices"])
    )
    if len(inverse) != len(transforms):
        raise ValidationError(f"{sample}: inverse-bind count differs")
    for index, (matrix, proof) in enumerate(zip(inverse, transforms, strict=True)):
        x, y, z = (float(value) for value in proof["absolute"])
        expected = (
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            -x, -y, -z, 1.0,
        )
        if any(
            f32_bits(float(actual)) != f32_bits(wanted)
            for actual, wanted in zip(matrix, expected, strict=True)
        ):
            raise ValidationError(f"{sample}: inverse bind {index} differs")

    mesh = gltf["meshes"][int(mesh_node["mesh"])]
    joint_accessors = {
        int(primitive["attributes"]["JOINTS_0"])
        for primitive in mesh["primitives"]
    }
    weight_accessors = {
        int(primitive["attributes"]["WEIGHTS_0"])
        for primitive in mesh["primitives"]
    }
    if len(joint_accessors) != 1 or len(weight_accessors) != 1:
        raise ValidationError(f"{sample}: primitives do not share skin accessors")
    joint_values = accessor_values(gltf, binary, next(iter(joint_accessors)))
    weight_values = accessor_values(gltf, binary, next(iter(weight_accessors)))
    if len(joint_values) != len(influences) or len(weight_values) != len(influences):
        raise ValidationError(f"{sample}: skin accessor count differs")

    arities: Counter[int] = Counter()
    maximum_sum_error = 0.0
    for vertex, (joints, weights, proof) in enumerate(
        zip(joint_values, weight_values, influences, strict=True)
    ):
        if int(proof["vertex"]) != vertex:
            raise ValidationError(f"{sample}: vertex proof order differs")
        active = list(proof["active"])
        arities[len(active)] += 1
        expected_joints = [0, 0, 0, 0]
        expected_weights = [0.0, 0.0, 0.0, 0.0]
        for slot, (joint, weight) in enumerate(active):
            expected_joints[slot] = int(joint)
            expected_weights[slot] = float(weight)
        if tuple(int(value) for value in joints) != tuple(expected_joints):
            raise ValidationError(f"{sample}: vertex {vertex} joints differ")
        if any(
            f32_bits(float(actual)) != f32_bits(wanted)
            for actual, wanted in zip(weights, expected_weights, strict=True)
        ):
            raise ValidationError(f"{sample}: vertex {vertex} weights differ")
        maximum_sum_error = max(
            maximum_sum_error, abs(sum(float(value) for value in weights) - 1.0)
        )
    return len(transforms), arities, maximum_sum_error


def validate(
    manifest_path: Path,
    asset_dir: Path,
    transforms_path: Path,
    influences_path: Path,
    workspace: Path,
) -> dict[str, object]:
    report = json.loads(manifest_path.read_text(encoding="utf-8"))
    if report.get("schema") != SCHEMA:
        raise ValidationError("manifest schema differs")
    transforms, influences = load_proofs(transforms_path, influences_path)
    total_skins = 0
    total_joints = 0
    total_vertices = 0
    total_primitives = 0
    arities: Counter[int] = Counter()
    maximum_sum_error = 0.0

    for output in report["outputs"]:
        gltf_path = asset_dir / output["output_gltf"]
        bin_path = asset_dir / output["output_bin"]
        if sha256_file(gltf_path) != output["output_gltf_sha256"]:
            raise ValidationError(f"{gltf_path}: hash differs")
        if sha256_file(bin_path) != output["output_bin_sha256"]:
            raise ValidationError(f"{bin_path}: hash differs")
        gltf = json.loads(gltf_path.read_text(encoding="utf-8"))
        binary = bin_path.read_bytes()
        if not (
            gltf.get("asset", {}).get("version") == "2.0"
            and gltf.get("extras", {}).get("raw_coordinates") is True
            and gltf.get("animations") in (None, [])
            and len(gltf.get("buffers", [])) == 1
            and int(gltf["buffers"][0]["byteLength"]) == len(binary)
            and gltf["buffers"][0]["uri"] == bin_path.name
        ):
            raise ValidationError(f"{gltf_path}: top-level glTF contract differs")
        validate_source_prefix(output, gltf, binary, workspace)
        for detail in output["skins"]:
            sample = str(detail["sample"])
            joints, counts, error = validate_skin(
                gltf, binary, detail, transforms[sample], influences[sample]
            )
            total_skins += 1
            total_joints += joints
            total_vertices += len(influences[sample])
            total_primitives += int(detail["primitive_count"])
            arities.update(counts)
            maximum_sum_error = max(maximum_sum_error, error)

    summary = report["summary"]
    expected = {
        "output_scene_count": 3,
        "skin_count": 5,
        "joint_node_count": 125,
        "skinned_vertex_count": 11_730,
        "skinned_primitive_count": 157,
        "influence_arity_counts": {"1": 8_511, "2": 2_888, "3": 331},
        "maximum_weight_sum_error": 6.705522537231445e-08,
        "raw_coordinate_conversion_applied": False,
        "animation_count": 0,
    }
    if summary != expected:
        raise ValidationError("manifest summary differs")
    if not (
        total_skins == 5
        and total_joints == 125
        and total_vertices == 11_730
        and total_primitives == 157
        and arities == Counter({1: 8_511, 2: 2_888, 3: 331})
        and abs(maximum_sum_error - expected["maximum_weight_sum_error"]) < 1e-15
        and all(str(line).startswith("PORTME:") for line in report["portme"])
    ):
        raise ValidationError("decoded output totals differ")
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--asset-dir", type=Path, required=True)
    result.add_argument("--transforms", type=Path, required=True)
    result.add_argument("--influences", type=Path, required=True)
    result.add_argument("--workspace", type=Path, default=Path("."))
    return result


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = validate(
            args.manifest, args.asset_dir, args.transforms, args.influences,
            args.workspace,
        )
    except (OSError, ValueError, KeyError, IndexError, struct.error, json.JSONDecodeError) as exc:
        print(f"nfl_raw_skin_gltf_validate: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        "NFL_RAW_SKIN_GLTF_STRUCTURAL_PASS "
        f"scenes={summary['output_scene_count']} skins={summary['skin_count']} "
        f"joints={summary['joint_node_count']} vertices={summary['skinned_vertex_count']} "
        f"rest_cancellations={summary['joint_node_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
