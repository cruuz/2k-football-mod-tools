#!/usr/bin/env python3
"""Independently validate the bounded NFL 2K5 -> APF 2K8 model audit.

The validator does not import the report generator.  It re-reads the four
SHA-pinned glTF inputs, independently derives their geometry/skin counts, and
then checks the canonical JSON and both TSV products.  It never opens a retail
archive and has no write path.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import stat
import struct
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports/assets/cross_title_model_compatibility.json"
MATRIX_PATH = ROOT / "reports/assets/cross_title_model_compatibility.tsv"
BONES_PATH = ROOT / "reports/assets/cross_title_model_bone_candidates.tsv"

REPORT_SCHEMA = "cross_title_model_compatibility/v1"
MATRIX_SCHEMA = "cross_title_model_compatibility_matrix/v1"
BONE_SCHEMA = "cross_title_model_bone_candidates/v1"

EXPECTED_HASHES = {
    "reports/asset_samples/nfl_static_gltf/3161_0006_stadium.gltf":
        "9dd367962fad9a974e1341746b1254f2efaf6d765fa68f41d0b31c10a37b10e8",
    "reports/asset_samples/nfl_static_gltf/3161_0006_stadium.bin":
        "ef1a7a3780e9397defe0a437085e0d064365a008ffa728e171905fc2ed2281e1",
    "assets/intermediate/apf2k8/models/0290_0008_stadium.gltf":
        "dcb2705d0e40e0888d37a98eaccf12d09d90b909114b0867f04ed4158cac17be",
    "assets/intermediate/apf2k8/models/0290_0008_stadium.bin":
        "84682243df160dce169e98daa6d12ba285985780907036ea78dbc4bda071ec0c",
    "assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.gltf":
        "15065af1aa5b8c39a168c0905815413cb17420697b480181922b85f668f6434a",
    "assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.bin":
        "3e53c4e335553f2ed4800c0664b563bec468abdca8ae162731f370c15686b75d",
    "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.gltf":
        "ffc5570c6205ea3bbaa7714eba6bee0ba5f4df7196996ae5a9473e0c4525abfc",
    "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.bin":
        "d72016179707c752979d8e079295b1e2ed28a33031b6c5d5ac7176f59aaf9029",
    "reports/assets/nfl_hi_body_skin_transforms.tsv":
        "ea8e74af7a64082f3dd18b37226e2a9503d415e02b517ffa6ecba410e87e7006",
    "reports/assets/apf_player_shadow_skin_joints.tsv":
        "5ba183e2d3609136c6a0acfb79f5e1f71f1163e977642c6c7bc760c6991cc87c",
    "reports/assets/apf_pose_bone_scene_join.tsv":
        "95d5488ffa38cbe39bebbac13a15e3d5e2c4db4d3b596d18411f886da3f4b03f",
}

EXPECTED_ASSETS: dict[str, dict[str, Any]] = {
    "nfl_stadium": {
        "gltf": "reports/asset_samples/nfl_static_gltf/3161_0006_stadium.gltf",
        "buffer": "reports/asset_samples/nfl_static_gltf/3161_0006_stadium.bin",
        "mesh_count": 143,
        "node_count": 143,
        "primitive_count": 562,
        "primitive_modes": {"4": 2, "5": 560},
        "unique_position_accessor_count": 143,
        "unique_vertex_count": 17_819,
        "index_reference_count": 27_066,
        "nondegenerate_triangle_count": 9_514,
        "degenerate_triangle_count": 16_328,
        "attributes": [["POSITION"]],
        "source_position_formats": ["FLOAT3"],
        "joint_count": 0,
        "influence_vertex_count": 0,
        "influence_count_distribution": {},
        "materials": 0,
        "textures": 0,
        "images": 0,
        "animations": 0,
        "skins": 0,
    },
    "apf_stadium": {
        "gltf": "assets/intermediate/apf2k8/models/0290_0008_stadium.gltf",
        "buffer": "assets/intermediate/apf2k8/models/0290_0008_stadium.bin",
        "mesh_count": 115,
        "node_count": 116,
        "primitive_count": 115,
        "primitive_modes": {"4": 115},
        "unique_position_accessor_count": 115,
        "unique_vertex_count": 156_501,
        "index_reference_count": 288_240,
        "nondegenerate_triangle_count": 96_080,
        "degenerate_triangle_count": 0,
        "attributes": [["POSITION"]],
        "source_position_formats": ["float32x3"],
        "joint_count": 0,
        "influence_vertex_count": 0,
        "influence_count_distribution": {},
        "materials": 0,
        "textures": 0,
        "images": 0,
        "animations": 0,
        "skins": 0,
    },
    "nfl_player": {
        "gltf": "assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.gltf",
        "buffer": "assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.bin",
        "mesh_count": 1,
        "node_count": 63,
        "primitive_count": 86,
        "primitive_modes": {"5": 86},
        "unique_position_accessor_count": 1,
        "unique_vertex_count": 7_396,
        "index_reference_count": 18_721,
        "nondegenerate_triangle_count": 10_006,
        "degenerate_triangle_count": 8_543,
        "attributes": [["JOINTS_0", "POSITION", "WEIGHTS_0"]],
        "source_position_formats": ["NORMSHORT3"],
        "joint_count": 62,
        "influence_vertex_count": 7_396,
        "influence_count_distribution": {"1": 5_356, "2": 1_921, "3": 119},
        "materials": 0,
        "textures": 0,
        "images": 0,
        "animations": 0,
        "skins": 1,
    },
    "apf_player": {
        "gltf": "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.gltf",
        "buffer": "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.bin",
        "mesh_count": 1,
        "node_count": 23,
        "primitive_count": 1,
        "primitive_modes": {"4": 1},
        "unique_position_accessor_count": 1,
        "unique_vertex_count": 351,
        "index_reference_count": 918,
        "nondegenerate_triangle_count": 306,
        "degenerate_triangle_count": 0,
        "attributes": [["JOINTS_0", "NORMAL", "POSITION", "TEXCOORD_0", "WEIGHTS_0"]],
        "source_position_formats": ["snorm16x4"],
        "joint_count": 21,
        "influence_vertex_count": 351,
        "influence_count_distribution": {"1": 351},
        "materials": 0,
        "textures": 0,
        "images": 0,
        "animations": 0,
        "skins": 1,
    },
}

EXPECTED_MATRIX = [
    ("coordinate_basis", "authoring-compatible"),
    ("units", "partial"),
    ("positions", "authoring-compatible"),
    ("topology", "intermediate-only"),
    ("normals_uv", "blocked"),
    ("skeleton", "retarget-required"),
    ("weights", "retarget-required"),
    ("inverse_bind", "authoring-compatible"),
    ("materials_shaders", "incompatible"),
    ("textures", "conversion-required"),
    ("lod", "unknown"),
    ("collision", "unknown"),
    ("container_endian", "incompatible"),
    ("allocation_writeback", "blocked"),
    ("runtime_routing", "blocked"),
]

EXPECTED_CLAIMS = {
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
}

COMPONENTS = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular_bytes(path: Path) -> bytes:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"not a non-symlink regular file: {path}")
    payload = path.read_bytes()
    current = path.stat(follow_symlinks=False)
    require((info.st_dev, info.st_ino, info.st_size) ==
            (current.st_dev, current.st_ino, current.st_size),
            f"file changed during validation: {path}")
    return payload


def source_path(relative: str) -> Path:
    require(relative in EXPECTED_HASHES, f"unrecognized source path: {relative}")
    candidate = ROOT / relative
    resolved = candidate.resolve(strict=True)
    require(ROOT == resolved or ROOT in resolved.parents, f"source escapes workspace: {relative}")
    require(candidate == resolved, f"source path uses a symlink: {relative}")
    return resolved


def read_source(relative: str) -> bytes:
    payload = regular_bytes(source_path(relative))
    require(hashlib.sha256(payload).hexdigest() == EXPECTED_HASHES[relative],
            f"source SHA-256 differs: {relative}")
    return payload


def normalized(value: int, component: int) -> float:
    if component == 5120:
        return max(-1.0, value / 127.0)
    if component == 5121:
        return value / 255.0
    if component == 5122:
        return max(-1.0, value / 32767.0)
    if component == 5123:
        return value / 65535.0
    raise ValidationError(f"unsupported normalized component: {component}")


def accessor_rows(document: dict[str, Any], binary: bytes, index: int) -> list[tuple[Any, ...]]:
    accessors = document.get("accessors", [])
    views = document.get("bufferViews", [])
    require(type(index) is int and 0 <= index < len(accessors), f"accessor out of range: {index}")
    accessor = accessors[index]
    require(isinstance(accessor, dict) and "sparse" not in accessor,
            f"invalid/sparse accessor: {index}")
    view_index = accessor.get("bufferView")
    component = accessor.get("componentType")
    shape = accessor.get("type")
    count = accessor.get("count")
    require(type(view_index) is int and 0 <= view_index < len(views),
            f"invalid buffer view: {index}")
    require(component in COMPONENTS and shape in WIDTHS and type(count) is int and count >= 0,
            f"unsupported accessor: {index}")
    view = views[view_index]
    require(isinstance(view, dict) and view.get("buffer") == 0,
            f"accessor does not use buffer zero: {index}")
    code, component_size = COMPONENTS[component]
    width = WIDTHS[shape]
    element_size = component_size * width
    stride = int(view.get("byteStride", element_size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    length = int(view.get("byteLength", -1))
    relative_start = int(accessor.get("byteOffset", 0))
    used = relative_start if count == 0 else relative_start + (count - 1) * stride + element_size
    require(start >= 0 and stride >= element_size and length >= 0 and used <= length,
            f"accessor exceeds its buffer view: {index}")
    require(start + (0 if count == 0 else (count - 1) * stride + element_size) <= len(binary),
            f"accessor exceeds binary buffer: {index}")
    unpack = struct.Struct("<" + code * width)
    rows = [unpack.unpack_from(binary, start + row * stride) for row in range(count)]
    if accessor.get("normalized"):
        return [tuple(normalized(int(value), component) for value in row) for row in rows]
    return rows


def triangle_counts(mode: int, indices: list[int]) -> tuple[int, int]:
    if mode == 4:
        require(len(indices) % 3 == 0, "triangle-list index count is not divisible by three")
        valid = sum(
            len({indices[offset], indices[offset + 1], indices[offset + 2]}) == 3
            for offset in range(0, len(indices), 3)
        )
        return valid, len(indices) // 3 - valid
    require(mode == 5, f"unsupported primitive mode: {mode}")
    valid = sum(
        len({indices[offset - 2], indices[offset - 1], indices[offset]}) == 3
        for offset in range(2, len(indices))
    )
    return valid, max(0, len(indices) - 2) - valid


def derive_gltf(relative: str) -> tuple[dict[str, Any], str, str]:
    gltf_bytes = read_source(relative)
    try:
        document = json.loads(gltf_bytes)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid glTF JSON: {relative}") from exc
    require(isinstance(document, dict) and document.get("asset", {}).get("version") == "2.0",
            f"not glTF 2.0: {relative}")
    buffers = document.get("buffers")
    require(isinstance(buffers, list) and len(buffers) == 1, f"expected one glTF buffer: {relative}")
    uri = buffers[0].get("uri")
    require(type(uri) is str and uri and ":" not in uri, f"unsafe glTF URI: {relative}")
    uri_path = Path(uri)
    require(not uri_path.is_absolute() and ".." not in uri_path.parts, f"glTF URI escapes: {relative}")
    buffer_relative = (Path(relative).parent / uri_path).as_posix()
    binary = read_source(buffer_relative)
    require(buffers[0].get("byteLength") == len(binary), f"declared buffer length differs: {relative}")

    position_accessors: set[int] = set()
    influence_pairs: set[tuple[int, int]] = set()
    attributes: set[tuple[str, ...]] = set()
    modes: dict[int, int] = {}
    formats: set[str] = set()
    primitive_count = index_count = triangle_count = degenerate_count = 0

    meshes = document.get("meshes", [])
    require(isinstance(meshes, list), f"mesh array missing: {relative}")
    for mesh in meshes:
        require(isinstance(mesh, dict) and isinstance(mesh.get("primitives"), list),
                f"invalid mesh: {relative}")
        extras = mesh.get("extras", {})
        if isinstance(extras, dict) and isinstance(extras.get("position_format"), str):
            formats.add(extras["position_format"])
        for primitive in mesh["primitives"]:
            primitive_count += 1
            attrs = primitive.get("attributes")
            require(isinstance(attrs, dict) and type(attrs.get("POSITION")) is int,
                    f"primitive lacks POSITION: {relative}")
            attributes.add(tuple(sorted(attrs)))
            position_index = attrs["POSITION"]
            position_accessors.add(position_index)
            vertex_count = int(document["accessors"][position_index]["count"])
            mode = int(primitive.get("mode", 4))
            modes[mode] = modes.get(mode, 0) + 1
            if "indices" in primitive:
                indices = [int(row[0]) for row in accessor_rows(document, binary, primitive["indices"])]
            else:
                indices = list(range(vertex_count))
            require(all(0 <= value < vertex_count for value in indices),
                    f"primitive index out of range: {relative}")
            triangles, degenerates = triangle_counts(mode, indices)
            index_count += len(indices)
            triangle_count += triangles
            degenerate_count += degenerates
            if "JOINTS_0" in attrs or "WEIGHTS_0" in attrs:
                require("JOINTS_0" in attrs and "WEIGHTS_0" in attrs,
                        f"incomplete skin attributes: {relative}")
                influence_pairs.add((attrs["JOINTS_0"], attrs["WEIGHTS_0"]))

    positions: list[tuple[float, float, float]] = []
    for accessor in sorted(position_accessors):
        rows = accessor_rows(document, binary, accessor)
        require(all(len(row) == 3 and all(math.isfinite(float(value)) for value in row)
                    for row in rows), f"invalid positions: {relative}")
        positions.extend((float(row[0]), float(row[1]), float(row[2])) for row in rows)
    require(bool(positions), f"no positions: {relative}")

    influence_distribution: dict[str, int] = {}
    influence_vertex_count = 0
    maximum_weight_sum_error = 0.0
    for joints_accessor, weights_accessor in sorted(influence_pairs):
        joints = accessor_rows(document, binary, joints_accessor)
        weights = accessor_rows(document, binary, weights_accessor)
        require(len(joints) == len(weights), f"joint/weight count differs: {relative}")
        influence_vertex_count += len(joints)
        for joint_row, weight_row in zip(joints, weights, strict=True):
            require(all(int(value) >= 0 for value in joint_row), f"negative joint: {relative}")
            active = sum(float(value) > 0.0 for value in weight_row)
            require(1 <= active <= 4, f"invalid influence count: {relative}")
            key = str(active)
            influence_distribution[key] = influence_distribution.get(key, 0) + 1
            maximum_weight_sum_error = max(
                maximum_weight_sum_error,
                abs(sum(float(value) for value in weight_row) - 1.0),
            )

    skins = document.get("skins", [])
    require(isinstance(skins, list) and len(skins) <= 1, f"unexpected skin count: {relative}")
    joint_count = 0 if not skins else len(skins[0].get("joints", []))
    bounds_min = [min(row[axis] for row in positions) for axis in range(3)]
    bounds_max = [max(row[axis] for row in positions) for axis in range(3)]
    derived = {
        "mesh_count": len(meshes),
        "node_count": len(document.get("nodes", [])),
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
            "extent": [bounds_max[axis] - bounds_min[axis] for axis in range(3)],
        },
        "attributes": [list(value) for value in sorted(attributes)],
        "source_position_formats": sorted(formats),
        "materials": len(document.get("materials", [])),
        "textures": len(document.get("textures", [])),
        "images": len(document.get("images", [])),
        "animations": len(document.get("animations", [])),
        "skins": len(skins),
        "joint_count": joint_count,
        "influence_vertex_count": influence_vertex_count,
        "influence_count_distribution": dict(sorted(influence_distribution.items())),
        "maximum_weight_sum_error": maximum_weight_sum_error,
    }
    return derived, relative, buffer_relative


def read_canonical_report() -> dict[str, Any]:
    payload = regular_bytes(REPORT_PATH)
    try:
        report = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError("compatibility report is not JSON") from exc
    canonical = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    require(payload == canonical, "compatibility report is not canonical JSON")
    require(report.get("schema") == REPORT_SCHEMA, "report schema differs")
    require(report.get("scope") ==
            "read-only derived glTF compatibility analysis; no retail archive opened or modified",
            "report scope differs")
    return report


def validate_assets(report: dict[str, Any]) -> None:
    assets = report.get("assets")
    require(isinstance(assets, dict) and set(assets) == set(EXPECTED_ASSETS),
            "asset roles differ")
    for role, expected in EXPECTED_ASSETS.items():
        row = assets[role]
        require(row.get("role") == role, f"asset role differs: {role}")
        derived, gltf_relative, buffer_relative = derive_gltf(expected["gltf"])
        require(gltf_relative == expected["gltf"] and buffer_relative == expected["buffer"],
                f"source paths differ: {role}")
        for key, value in expected.items():
            if key in {"gltf", "buffer"}:
                continue
            require(row.get(key) == value, f"{role} expected metric differs: {key}")
        for key, value in derived.items():
            require(row.get(key) == value, f"{role} independent metric differs: {key}")
        for field, relative in (("gltf", gltf_relative), ("buffer", buffer_relative)):
            metadata = row.get(field)
            require(isinstance(metadata, dict) and metadata.get("path") == relative,
                    f"{role} {field} path differs")
            path = source_path(relative)
            require(metadata.get("size") == path.stat().st_size and
                    metadata.get("sha256") == EXPECTED_HASHES[relative],
                    f"{role} {field} identity differs")
        require(row["maximum_weight_sum_error"] <= 1e-6,
                f"{role} weights do not sum to one")


def read_tsv(path: Path, fields: list[str]) -> list[dict[str, str]]:
    payload = regular_bytes(path)
    require(payload.endswith(b"\n") and b"\r" not in payload,
            f"TSV newline convention differs: {path.name}")
    text = payload.decode("utf-8")
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    require(reader.fieldnames == fields, f"TSV fields differ: {path.name}")
    rows = list(reader)
    require(all(None not in row and all(value is not None for value in row.values()) for row in rows),
            f"TSV row shape differs: {path.name}")
    return rows


def validate_matrix(report: dict[str, Any]) -> None:
    fields = ["schema", "surface", "nfl2k5", "apf2k8", "status", "requirement"]
    rows = read_tsv(MATRIX_PATH, fields)
    matrix = report.get("compatibility_matrix")
    require(isinstance(matrix, list) and len(matrix) == 15, "matrix count differs")
    require(rows == matrix, "matrix TSV and JSON differ")
    require([(row["surface"], row["status"]) for row in rows] == EXPECTED_MATRIX,
            "matrix surface/status decisions differ")
    require(all(row["schema"] == MATRIX_SCHEMA and row["requirement"] for row in rows),
            "matrix schema/requirements differ")


def validate_bones(report: dict[str, Any]) -> None:
    fields = [
        "schema", "target_skeleton", "nfl_index", "nfl_name", "nfl_parent_index",
        "normalized_name", "apf_index", "apf_name", "apf_parent_index",
        "parent_name_agrees", "status", "claim",
    ]
    rows = read_tsv(BONES_PATH, fields)
    require(len(rows) == 124, "bone-candidate row count differs")
    expected_counts = {
        "apf_player_shadow_21": {
            "target_joint_count": 21,
            "nfl_joint_count": 62,
            "name_and_parent": 7,
            "name_only": 6,
            "unmatched": 49,
            "ambiguous": 0,
            "direct_index_copy_safe": False,
        },
        "apf_player_hires_92": {
            "target_joint_count": 92,
            "nfl_joint_count": 62,
            "name_and_parent": 3,
            "name_only": 11,
            "unmatched": 48,
            "ambiguous": 0,
            "direct_index_copy_safe": False,
        },
    }
    summaries = report.get("bone_candidates", {}).get("summaries")
    require(summaries == expected_counts, "bone-candidate summaries differ")
    for target, summary in expected_counts.items():
        selected = [row for row in rows if row["target_skeleton"] == target]
        require(len(selected) == 62, f"bone-candidate target count differs: {target}")
        require(sorted(int(row["nfl_index"]) for row in selected) == list(range(62)),
                f"NFL bone indices are not complete: {target}")
        observed = {status: sum(row["status"] == status for row in selected)
                    for status in ("name_and_parent", "name_only", "unmatched", "ambiguous")}
        require(all(observed[key] == summary[key] for key in observed),
                f"bone statuses differ: {target}")
        for row in selected:
            require(row["schema"] == BONE_SCHEMA, "bone schema differs")
            require(row["claim"] ==
                    "authoring retarget candidate only; not an engine bone-index map",
                    "bone-candidate claim differs")
            require((row["parent_name_agrees"] == "True") ==
                    (row["status"] == "name_and_parent"),
                    "bone parent agreement/status differs")
            if row["status"] == "unmatched":
                require(row["apf_index"] == row["apf_name"] == row["apf_parent_index"] == "",
                        "unmatched bone has an APF target")
            else:
                require(row["apf_index"].isdigit() and row["apf_name"],
                        "matched bone lacks an APF target")

    pins = report.get("bone_candidates", {}).get("sources")
    expected_pins = {
        "nfl_hires": "reports/assets/nfl_hi_body_skin_transforms.tsv",
        "apf_shadow": "reports/assets/apf_player_shadow_skin_joints.tsv",
        "apf_hires": "reports/assets/apf_pose_bone_scene_join.tsv",
    }
    require(isinstance(pins, dict) and set(pins) == set(expected_pins),
            "bone source pins differ")
    for key, relative in expected_pins.items():
        read_source(relative)
        require(pins[key].get("path") == relative and
                pins[key].get("sha256") == EXPECTED_HASHES[relative] and
                pins[key].get("size") == source_path(relative).stat().st_size,
                f"bone source identity differs: {key}")


def validate_claims_and_workflow(report: dict[str, Any]) -> None:
    require(report.get("claims") == EXPECTED_CLAIMS, "claim set differs")
    workflow = report.get("blender_workflow")
    require(isinstance(workflow, dict) and
            workflow.get("status") == "safe authoring/reference workflow only",
            "Blender workflow status differs")
    items = workflow.get("items")
    require(isinstance(items, list) and [item.get("role") for item in items] ==
            ["nfl_stadium", "apf_stadium", "nfl_player", "apf_player"],
            "Blender workflow roles differ")
    expected_scales = {
        "nfl_stadium": [0.01, 0.01, 0.01],
        "apf_stadium": [0.01, 0.01, 0.01],
        "nfl_player": [1.0, 1.0, 1.0],
        "apf_player": [1.0, 1.0, 1.0],
    }
    for item in items:
        role = item["role"]
        require(item.get("gltf") == EXPECTED_ASSETS[role]["gltf"],
                f"workflow glTF differs: {role}")
        require(item.get("preview_scale") == expected_scales[role],
                f"workflow scale differs: {role}")
        require(type(item.get("scale_claim")) is str and item["scale_claim"],
                f"workflow scale claim absent: {role}")
    require("not APF-importable" in workflow.get("portme", ""),
            "workflow APF-import boundary absent")
    portme = report.get("portme")
    require(isinstance(portme, list) and len(portme) == 6 and
            all(type(row) is str and row.startswith("PORTME:") for row in portme),
            "top-level PORTME list differs")


def main() -> int:
    report = read_canonical_report()
    validate_assets(report)
    validate_matrix(report)
    validate_bones(report)
    validate_claims_and_workflow(report)
    print(
        "CROSS_TITLE_MODEL_COMPATIBILITY_VALIDATION_PASS "
        "assets=4 matrix=15 bones=124 direct_copy=false writeback=false runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValidationError) as exc:
        print(f"error: {exc}")
        raise SystemExit(1)
