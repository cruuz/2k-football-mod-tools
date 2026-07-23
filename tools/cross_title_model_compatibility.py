#!/usr/bin/env python3
"""Analyze NFL 2K5 -> APF 2K8 model authoring compatibility without writing games.

This consumes only already-derived, SHA-pinned glTF/report evidence.  It does
not parse or mutate either retail archive and deliberately emits no APF SCNE.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "cross_title_model_compatibility/v1"
MATRIX_SCHEMA = "cross_title_model_compatibility_matrix/v1"
BONE_SCHEMA = "cross_title_model_bone_candidates/v1"

SOURCES = {
    "nfl_stadium": Path("reports/asset_samples/nfl_static_gltf/3161_0006_stadium.gltf"),
    "apf_stadium": Path("assets/intermediate/apf2k8/models/0290_0008_stadium.gltf"),
    "nfl_player": Path(
        "assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.gltf"
    ),
    "apf_player": Path(
        "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.gltf"
    ),
}

TABLES = {
    "nfl_hires": Path("reports/assets/nfl_hi_body_skin_transforms.tsv"),
    "apf_shadow": Path("reports/assets/apf_player_shadow_skin_joints.tsv"),
    "apf_player_hires": Path("reports/assets/apf_pose_bone_scene_join.tsv"),
}

EXPECTED_SHA256 = {
    "reports/asset_samples/nfl_static_gltf/3161_0006_stadium.gltf":
        "9dd367962fad9a974e1341746b1254f2efaf6d765fa68f41d0b31c10a37b10e8",
    "reports/asset_samples/nfl_static_gltf/3161_0006_stadium.bin":
        "ef1a7a3780e9397defe0a437085e0d064365a008ffa728e171905fc2ed2281e1",
    "assets/intermediate/apf2k8/models/0290_0008_stadium.gltf":
        "3b4969d212adac18ad013f01edcdef1b19157dcc47b831c3e8c7e89a0277a846",
    "assets/intermediate/apf2k8/models/0290_0008_stadium.bin":
        "84682243df160dce169e98daa6d12ba285985780907036ea78dbc4bda071ec0c",
    "assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.gltf":
        "15065af1aa5b8c39a168c0905815413cb17420697b480181922b85f668f6434a",
    "assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.bin":
        "3e53c4e335553f2ed4800c0664b563bec468abdca8ae162731f370c15686b75d",
    "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.gltf":
        "e245811657d4808053a244996b9850dcc607ee70ab6eafa87194e6917d2ae30f",
    "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.bin":
        "d72016179707c752979d8e079295b1e2ed28a33031b6c5d5ac7176f59aaf9029",
    "reports/assets/nfl_hi_body_skin_transforms.tsv":
        "ea8e74af7a64082f3dd18b37226e2a9503d415e02b517ffa6ecba410e87e7006",
    "reports/assets/apf_player_shadow_skin_joints.tsv":
        "5ba183e2d3609136c6a0acfb79f5e1f71f1163e977642c6c7bc760c6991cc87c",
    "reports/assets/apf_pose_bone_scene_join.tsv":
        "95d5488ffa38cbe39bebbac13a15e3d5e2c4db4d3b596d18411f886da3f4b03f",
}

COMPONENTS = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
TYPE_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class CompatibilityError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityError(message)


def relative(path: Path) -> str:
    return path.resolve(strict=True).relative_to(ROOT).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    full = ROOT / path
    supplied = full.lstat()
    require(full.is_file() and not full.is_symlink(), f"input must be regular/non-symlink: {path}")
    digest = sha256_file(full)
    require(EXPECTED_SHA256.get(path.as_posix()) == digest, f"input SHA changed: {path}")
    current = full.stat(follow_symlinks=False)
    require(
        (current.st_dev, current.st_ino, current.st_size)
        == (supplied.st_dev, supplied.st_ino, supplied.st_size),
        f"input identity changed: {path}",
    )
    return {"path": path.as_posix(), "size": supplied.st_size, "sha256": digest}


def load_gltf(path: Path) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    gltf_pin = pin(path)
    full = ROOT / path
    try:
        document = json.loads(full.read_bytes())
    except json.JSONDecodeError as exc:
        raise CompatibilityError(f"invalid glTF JSON: {path}") from exc
    require(isinstance(document, dict) and document.get("asset", {}).get("version") == "2.0",
            f"not glTF 2.0: {path}")
    buffers = document.get("buffers")
    require(isinstance(buffers, list) and len(buffers) == 1, f"expected one buffer: {path}")
    uri = buffers[0].get("uri")
    require(type(uri) is str and uri and ":" not in uri, f"external safe buffer required: {path}")
    uri_path = Path(uri)
    require(not uri_path.is_absolute() and ".." not in uri_path.parts,
            f"buffer traversal refused: {path}")
    binary_path = path.parent / uri_path
    binary_pin = pin(binary_path)
    binary = (ROOT / binary_path).read_bytes()
    require(buffers[0].get("byteLength") == len(binary), f"buffer length differs: {path}")
    validate_layout(document, binary, path)
    return document, binary, gltf_pin, binary_pin


def validate_layout(gltf: dict[str, Any], binary: bytes, path: Path) -> None:
    views = gltf.get("bufferViews", [])
    accessors = gltf.get("accessors", [])
    require(isinstance(views, list) and isinstance(accessors, list), f"layout arrays absent: {path}")
    for index, view in enumerate(views):
        require(isinstance(view, dict) and view.get("buffer") == 0,
                f"bufferView {index} invalid: {path}")
        start = int(view.get("byteOffset", 0))
        length = view.get("byteLength")
        require(type(length) is int and start >= 0 and length >= 0 and start + length <= len(binary),
                f"bufferView {index} out of bounds: {path}")
    for index, accessor in enumerate(accessors):
        require(isinstance(accessor, dict) and "sparse" not in accessor,
                f"accessor {index} sparse/invalid: {path}")
        view_index = accessor.get("bufferView")
        component = accessor.get("componentType")
        shape = accessor.get("type")
        count = accessor.get("count")
        require(type(view_index) is int and 0 <= view_index < len(views),
                f"accessor {index} view invalid: {path}")
        require(component in COMPONENTS and shape in TYPE_WIDTH and type(count) is int and count >= 0,
                f"accessor {index} type invalid: {path}")
        view = views[view_index]
        element = COMPONENTS[component][1] * TYPE_WIDTH[shape]
        stride = int(view.get("byteStride", element))
        offset = int(accessor.get("byteOffset", 0))
        require(stride >= element and offset >= 0, f"accessor {index} stride invalid: {path}")
        used = offset if count == 0 else offset + (count - 1) * stride + element
        require(used <= int(view["byteLength"]), f"accessor {index} exceeds view: {path}")
    for mesh_index, mesh in enumerate(gltf.get("meshes", [])):
        require(isinstance(mesh, dict) and isinstance(mesh.get("primitives"), list),
                f"mesh {mesh_index} invalid: {path}")
        for primitive in mesh["primitives"]:
            attributes = primitive.get("attributes")
            require(isinstance(attributes, dict) and type(attributes.get("POSITION")) is int,
                    f"mesh {mesh_index} lacks POSITION: {path}")
            refs = list(attributes.values())
            if "indices" in primitive:
                refs.append(primitive["indices"])
            require(all(type(value) is int and 0 <= value < len(accessors) for value in refs),
                    f"mesh {mesh_index} accessor reference invalid: {path}")
            require(primitive.get("mode", 4) in {4, 5}, f"mesh mode unsupported: {path}")


def decode_accessor(gltf: dict[str, Any], binary: bytes, index: int) -> list[tuple[Any, ...]]:
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    fmt, component_size = COMPONENTS[accessor["componentType"]]
    width = TYPE_WIDTH[accessor["type"]]
    element = component_size * width
    stride = int(view.get("byteStride", element))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    unpack = struct.Struct("<" + fmt * width)
    values = [unpack.unpack_from(binary, start + row * stride) for row in range(accessor["count"])]
    if accessor.get("normalized"):
        component = accessor["componentType"]

        def normalized(value: int) -> float:
            if component == 5120:
                return max(-1.0, value / 127.0)
            if component == 5121:
                return value / 255.0
            if component == 5122:
                return max(-1.0, value / 32767.0)
            if component == 5123:
                return value / 65535.0
            raise CompatibilityError("unsupported normalized component")

        return [tuple(normalized(value) for value in row) for row in values]
    return values


def normalized_bone_name(name: str) -> str:
    value = re.sub(r"^[^:]+:\d{2}:", "", name).lower()
    if value.startswith("def_"):
        value = value[4:]
    return re.sub(r"[^a-z0-9]", "", value)


def topology_counts(mode: int, indices: list[int]) -> tuple[int, int]:
    if mode == 4:
        require(len(indices) % 3 == 0, "triangle-list index count not divisible by three")
        triangles = 0
        for offset in range(0, len(indices), 3):
            if len(set(indices[offset:offset + 3])) == 3:
                triangles += 1
        return triangles, len(indices) // 3 - triangles
    triangles = 0
    degenerate = 0
    for offset in range(2, len(indices)):
        triangle = (indices[offset - 2], indices[offset - 1], indices[offset])
        if len(set(triangle)) == 3:
            triangles += 1
        else:
            degenerate += 1
    return triangles, degenerate


def analyze_gltf(role: str, path: Path) -> dict[str, Any]:
    gltf, binary, gltf_pin, buffer_pin = load_gltf(path)
    position_accessors: set[int] = set()
    attribute_sets: set[tuple[str, ...]] = set()
    modes: dict[int, int] = {}
    primitive_count = 0
    index_count = 0
    triangle_count = 0
    degenerate_count = 0
    formats: set[str] = set()
    influence_pairs: set[tuple[int, int]] = set()
    for mesh in gltf.get("meshes", []):
        extras = mesh.get("extras", {})
        if isinstance(extras, dict) and isinstance(extras.get("position_format"), str):
            formats.add(extras["position_format"])
        for primitive in mesh["primitives"]:
            primitive_count += 1
            attributes = primitive["attributes"]
            attribute_sets.add(tuple(sorted(attributes)))
            position_accessors.add(attributes["POSITION"])
            mode = int(primitive.get("mode", 4))
            modes[mode] = modes.get(mode, 0) + 1
            if "indices" in primitive:
                values = [int(row[0]) for row in decode_accessor(gltf, binary, primitive["indices"])]
            else:
                values = list(range(int(gltf["accessors"][attributes["POSITION"]]["count"])))
            vertex_count = int(gltf["accessors"][attributes["POSITION"]]["count"])
            require(all(0 <= value < vertex_count for value in values), f"{role} index out of range")
            triangles, degenerates = topology_counts(mode, values)
            triangle_count += triangles
            degenerate_count += degenerates
            index_count += len(values)
            if "JOINTS_0" in attributes or "WEIGHTS_0" in attributes:
                require("JOINTS_0" in attributes and "WEIGHTS_0" in attributes,
                        f"{role} has incomplete skin attributes")
                influence_pairs.add((attributes["JOINTS_0"], attributes["WEIGHTS_0"]))

    positions: list[tuple[float, float, float]] = []
    for accessor in sorted(position_accessors):
        rows = decode_accessor(gltf, binary, accessor)
        require(all(len(row) == 3 and all(math.isfinite(float(value)) for value in row) for row in rows),
                f"{role} position values invalid")
        positions.extend((float(row[0]), float(row[1]), float(row[2])) for row in rows)
    require(bool(positions), f"{role} has no positions")
    bounds_min = [min(row[axis] for row in positions) for axis in range(3)]
    bounds_max = [max(row[axis] for row in positions) for axis in range(3)]

    influence_distribution: dict[int, int] = {}
    maximum_sum_error = 0.0
    influence_vertex_count = 0
    for joints_index, weights_index in sorted(influence_pairs):
        joints = decode_accessor(gltf, binary, joints_index)
        weights = decode_accessor(gltf, binary, weights_index)
        require(len(joints) == len(weights), f"{role} joint/weight counts differ")
        influence_vertex_count += len(joints)
        for joint_row, weight_row in zip(joints, weights, strict=True):
            active = sum(float(weight) > 0.0 for weight in weight_row)
            require(1 <= active <= 4, f"{role} influence count invalid")
            influence_distribution[active] = influence_distribution.get(active, 0) + 1
            maximum_sum_error = max(maximum_sum_error, abs(sum(float(v) for v in weight_row) - 1.0))
            require(all(int(joint) >= 0 for joint in joint_row), f"{role} negative joint")

    joint_names: list[str] = []
    joint_parents: list[int] = []
    if gltf.get("skins"):
        require(len(gltf["skins"]) == 1, f"{role} expected one skin")
        joints = gltf["skins"][0].get("joints", [])
        require(isinstance(joints, list) and joints, f"{role} skin joints absent")
        nodes = gltf.get("nodes", [])
        parent_by_node: dict[int, int] = {}
        for parent, node in enumerate(nodes):
            for child in node.get("children", []):
                require(child not in parent_by_node, f"{role} node has multiple parents")
                parent_by_node[int(child)] = parent
        joint_to_local = {int(node): index for index, node in enumerate(joints)}
        for node in joints:
            require(type(node) is int and 0 <= node < len(nodes), f"{role} joint node invalid")
            name = nodes[node].get("name")
            require(type(name) is str and name, f"{role} joint name absent")
            joint_names.append(name)
            parent = parent_by_node.get(node)
            joint_parents.append(joint_to_local.get(parent, -1))

    return {
        "role": role,
        "gltf": gltf_pin,
        "buffer": buffer_pin,
        "generator": gltf.get("asset", {}).get("generator"),
        "mesh_count": len(gltf.get("meshes", [])),
        "node_count": len(gltf.get("nodes", [])),
        "primitive_count": primitive_count,
        "primitive_modes": {str(key): value for key, value in sorted(modes.items())},
        "unique_position_accessor_count": len(position_accessors),
        "unique_vertex_count": len(positions),
        "index_reference_count": index_count,
        "nondegenerate_triangle_count": triangle_count,
        "degenerate_triangle_count": degenerate_count,
        "bounds": {
            "min": bounds_min,
            "max": bounds_max,
            "extent": [bounds_max[index] - bounds_min[index] for index in range(3)],
        },
        "attributes": [list(value) for value in sorted(attribute_sets)],
        "source_position_formats": sorted(formats),
        "materials": len(gltf.get("materials", [])),
        "textures": len(gltf.get("textures", [])),
        "images": len(gltf.get("images", [])),
        "animations": len(gltf.get("animations", [])),
        "skins": len(gltf.get("skins", [])),
        "joint_count": len(joint_names),
        "joint_names": joint_names,
        "joint_parents": joint_parents,
        "influence_vertex_count": influence_vertex_count,
        "influence_count_distribution": {
            str(key): value for key, value in sorted(influence_distribution.items())
        },
        "maximum_weight_sum_error": maximum_sum_error,
        "extras": gltf.get("extras", {}),
    }


def read_tsv(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    source_pin = pin(path)
    with (ROOT / path).open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    require(bool(rows), f"TSV empty: {path}")
    return rows, source_pin


def table_skeletons() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nfl_rows, nfl_pin = read_tsv(TABLES["nfl_hires"])
    shadow_rows, shadow_pin = read_tsv(TABLES["apf_shadow"])
    apf_rows, apf_pin = read_tsv(TABLES["apf_player_hires"])
    apf_hires = [row for row in apf_rows if row["map_name"] == "hires"]
    require(len(nfl_rows) == 62 and len(shadow_rows) == 21 and len(apf_hires) == 92,
            "skeleton table counts changed")

    nfl = [
        {
            "index": int(row["transform_index"]),
            "name": row["transform_name"],
            "parent": int(row["parent_index"]),
        }
        for row in nfl_rows
    ]
    targets = {
        "apf_player_shadow_21": [
            {"index": int(row["joint"]), "name": row["name"], "parent": int(row["parent"])}
            for row in shadow_rows
        ],
        "apf_player_hires_92": [
            {
                "index": int(row["scene_hierarchy_index"]),
                "name": row["bone_name"],
                "parent": int(row["scene_parent_index"]),
            }
            for row in apf_hires
        ],
    }
    for target_name, target in targets.items():
        target.sort(key=lambda row: row["index"])
        require(
            [row["index"] for row in target] == list(range(len(target))),
            f"{target_name} hierarchy indices are not dense",
        )
    candidates: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    for target_name, target in targets.items():
        by_normalized: dict[str, list[dict[str, Any]]] = {}
        for row in target:
            by_normalized.setdefault(normalized_bone_name(row["name"]), []).append(row)
        counts = {"name_and_parent": 0, "name_only": 0, "unmatched": 0, "ambiguous": 0}
        for source in nfl:
            normalized = normalized_bone_name(source["name"])
            matches = by_normalized.get(normalized, [])
            target_row = matches[0] if len(matches) == 1 else None
            source_parent_name = ""
            if source["parent"] >= 0:
                source_parent_name = normalized_bone_name(nfl[source["parent"]]["name"])
            target_parent_name = ""
            if target_row and target_row["parent"] >= 0:
                target_parent_name = normalized_bone_name(target[target_row["parent"]]["name"])
            if len(matches) > 1:
                status = "ambiguous"
            elif target_row is None:
                status = "unmatched"
            elif source_parent_name == target_parent_name:
                status = "name_and_parent"
            else:
                status = "name_only"
            counts[status] += 1
            candidates.append(
                {
                    "schema": BONE_SCHEMA,
                    "target_skeleton": target_name,
                    "nfl_index": source["index"],
                    "nfl_name": source["name"],
                    "nfl_parent_index": source["parent"],
                    "normalized_name": normalized,
                    "apf_index": "" if target_row is None else target_row["index"],
                    "apf_name": "" if target_row is None else target_row["name"],
                    "apf_parent_index": "" if target_row is None else target_row["parent"],
                    "parent_name_agrees": status == "name_and_parent",
                    "status": status,
                    "claim": "authoring retarget candidate only; not an engine bone-index map",
                }
            )
        summaries[target_name] = {
            "target_joint_count": len(target),
            "nfl_joint_count": len(nfl),
            **counts,
            "direct_index_copy_safe": False,
        }
    return candidates, {
        "sources": {"nfl_hires": nfl_pin, "apf_shadow": shadow_pin, "apf_hires": apf_pin},
        "summaries": summaries,
    }


def matrix_rows() -> list[dict[str, str]]:
    rows = [
        ("coordinate_basis", "proved right-handed Y-up XYZ for player/motion", "proved right-handed Y-up XYZ for selected player/motion", "authoring-compatible", "Retain XYZ for the selected meter-space players; static-stadium application remains a bounded inference."),
        ("units", "stadium raw centimeters; selected player already meters", "selected player already meters; stadium magnitude is centimeter-like", "partial", "Use 1.0 for selected player glTFs and 0.01 only as a stadium comparison transform, not APF serialization proof."),
        ("positions", "FLOAT3/NORMSHORT3 decoded", "float32/snorm16/10:10:10 position paths decoded", "authoring-compatible", "Both representative glTFs expose standard float32 POSITION."),
        ("topology", "NV2A push streams; glTF triangles/strips", "Xenos strip/restart buffers expanded to glTF triangles", "intermediate-only", "glTF/Blender can bridge triangles; serialized command/index layouts are not interchangeable."),
        ("normals_uv", "withheld on selected stadium/player", "withheld on stadium; selected shadow surface has NORMAL and packed-UV derivative", "blocked", "NFL player/stadium surfaces lack proved normals/UVs needed for a faithful APF asset."),
        ("skeleton", "62-joint HI_res hierarchy", "21-joint shadow and separate 92-joint player hierarchy", "retarget-required", "Counts, names, and parent chains differ; direct joint-index copy is unsafe."),
        ("weights", "one/two/three-joint CPU-blend result", "selected shadow is one-hot; generic APF multi-influence export unproved", "retarget-required", "Weight transfer must target a proved APF player skin, which is not yet available."),
        ("inverse_bind", "current*T(-bind), column-vector", "transpose-equivalent T(-bind)*current, row-vector", "authoring-compatible", "Both selected meter glTFs use standard inverse binds; this does not make serialized palettes identical."),
        ("materials_shaders", "NV2A materials and embedded P8 links", "Xenos SM3 shaders and instance-owned material arrays", "incompatible", "Shader/material records cannot be copied; APF concrete player texture bindings remain unresolved."),
        ("textures", "embedded P8 plus Xbox sampler semantics", "separate tiled/endian Xenos TXTR, commonly BCn", "conversion-required", "Decode/edit/re-encode plus proven APF resource binding is required."),
        ("lod", "not represented by selected stadium glTF", "stadium split across stadium/sideline/exterior/sky and policy not exported", "unknown", "A full replacement needs every package component and title LOD selection."),
        ("collision", "no collision owner in selected SCNE proof", "no collision owner in selected SCNE proof", "unknown", "Do not infer collision from render triangles."),
        ("container_endian", "little-endian Xbox SCNE, VC-LZ/archive, NV2A", "big-endian SCNE in IFF/H7A/0A, Xenos", "incompatible", "Direct binary copy cannot load."),
        ("allocation_writeback", "no edited-glTF to NFL SCNE writer", "no edited-glTF to APF SCNE/IFF/H7A writer", "blocked", "Texture fixed-allocation writers do not prove model block growth/repacking."),
        ("runtime_routing", "source owners known only for selected extracts", "no replacement slot/material/LOD/collision route proved", "blocked", "No APF execution or runtime visibility test was performed."),
    ]
    return [
        {
            "schema": MATRIX_SCHEMA,
            "surface": surface,
            "nfl2k5": nfl,
            "apf2k8": apf,
            "status": status,
            "requirement": requirement,
        }
        for surface, nfl, apf, status, requirement in rows
    ]


def generate() -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
    assets = {name: analyze_gltf(name, path) for name, path in SOURCES.items()}
    bone_rows, bone_summary = table_skeletons()
    matrix = matrix_rows()
    report = {
        "schema": SCHEMA,
        "scope": "read-only derived glTF compatibility analysis; no retail archive opened or modified",
        "assets": assets,
        "bone_candidates": bone_summary,
        "compatibility_matrix": matrix,
        "blender_workflow": {
            "status": "safe authoring/reference workflow only",
            "items": [
                {
                    "role": "nfl_stadium",
                    "gltf": SOURCES["nfl_stadium"].as_posix(),
                    "preview_scale": [0.01, 0.01, 0.01],
                    "location": [-180.0, 0.0, 0.0],
                    "scale_claim": "NFL centimeter-to-meter conversion is proved",
                },
                {
                    "role": "apf_stadium",
                    "gltf": SOURCES["apf_stadium"].as_posix(),
                    "preview_scale": [0.01, 0.01, 0.01],
                    "location": [180.0, 0.0, 0.0],
                    "scale_claim": "comparison-only centimeter hypothesis; not a per-stadium writeback proof",
                },
                {
                    "role": "nfl_player",
                    "gltf": SOURCES["nfl_player"].as_posix(),
                    "preview_scale": [1.0, 1.0, 1.0],
                    "location": [-2.0, 0.0, 0.0],
                    "scale_claim": "already proved right-handed Y-up meters",
                },
                {
                    "role": "apf_player",
                    "gltf": SOURCES["apf_player"].as_posix(),
                    "preview_scale": [1.0, 1.0, 1.0],
                    "location": [2.0, 0.0, 0.0],
                    "scale_claim": "already proved right-handed Y-up meters",
                },
            ],
            "portme": "Comparison collections are not APF-importable assets and must not be packaged as a game mod.",
        },
        "claims": {
            "standard_gltf_blender_comparison_possible": True,
            "selected_player_coordinate_basis_compatible": True,
            "selected_player_inverse_bind_design_equivalent": True,
            "partial_name_based_retarget_candidates_emitted": True,
            "direct_joint_index_copy_safe": False,
            "direct_serialized_mesh_copy_safe": False,
            "nfl_stadium_direct_apf_import_possible": False,
            "nfl_player_direct_apf_import_possible": False,
            "edited_gltf_to_apf_scne_writer_available": False,
            "apf_model_archive_writeback_available": False,
            "runtime_visibility_tested": False,
            "emulator_started": False,
            "retail_original_modified": False,
        },
        "portme": [
            "PORTME: recover and encode complete APF vertex declarations, draw records, hierarchy transforms, and all required DRAM/VRAM parts.",
            "PORTME: produce a generic APF player skin with proved multi-influence weights before retargeting NFL HI_res.",
            "PORTME: bind APF player/stadium material slots to concrete TXTR resources and prove Xenos sampler/shader requirements.",
            "PORTME: identify full stadium LOD, sideline, exterior, sky, field, collision, and navigation ownership.",
            "PORTME: implement an edited-glTF to APF SCNE serializer plus IFF/H7A/fixed-allocation or repacking verifier.",
            "PORTME: prove a specific APF resource replacement route and runtime visibility before calling any conversion playable.",
        ],
    }
    return report, matrix, bone_rows


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--output", type=Path,
        default=ROOT / "reports/assets/cross_title_model_compatibility.json",
    )
    result.add_argument(
        "--matrix", type=Path,
        default=ROOT / "reports/assets/cross_title_model_compatibility.tsv",
    )
    result.add_argument(
        "--bones", type=Path,
        default=ROOT / "reports/assets/cross_title_model_bone_candidates.tsv",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    report, matrix, bones = generate()
    write_json(args.output, report)
    write_tsv(
        args.matrix,
        matrix,
        ["schema", "surface", "nfl2k5", "apf2k8", "status", "requirement"],
    )
    write_tsv(
        args.bones,
        bones,
        [
            "schema", "target_skeleton", "nfl_index", "nfl_name", "nfl_parent_index",
            "normalized_name", "apf_index", "apf_name", "apf_parent_index",
            "parent_name_agrees", "status", "claim",
        ],
    )
    summary = report["bone_candidates"]["summaries"]
    print(
        "CROSS_TITLE_MODEL_COMPATIBILITY_PASS "
        f"assets={len(report['assets'])} matrix={len(matrix)} bones={len(bones)} "
        f"hires_name_parent={summary['apf_player_hires_92']['name_and_parent']} "
        "direct_copy=false writeback=false runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
