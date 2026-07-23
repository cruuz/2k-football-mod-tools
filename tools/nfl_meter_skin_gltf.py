#!/usr/bin/env python3
"""Convert proved raw-centimeter NFL skin witnesses to right-handed Y-up meters."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Any


SCHEMA = "nfl2k5_meter_skin_gltf_manifest/v1"
STEMS = (
    "0003_0113_lo_body_raw_skin",
    "0346_0109_referee_raw_skin",
    "0348_0000_coach_raw_skin",
)
PORTME = [
    "PORTME: bind decoded rotations only after proving sampled-pose application into exact local joint matrices.",
    "PORTME: attach root trajectories only after proving caller-specific external-parent ownership and loop-cycle accumulation.",
    "PORTME: represent the title's fixed-table quaternion interpolation without claiming ordinary glTF LINEAR is bit-equivalent.",
    "PORTME: recover materials, embedded textures, normals, UVs, and sampler/shader semantics.",
    "PORTME: implement a validated edited-glTF to SCNE/archive writer.",
]


class ConvertError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def accessor_layout(gltf: dict[str, Any], accessor_index: int,
                    components: int) -> tuple[dict[str, Any], int, int]:
    accessors = gltf.get("accessors")
    views = gltf.get("bufferViews")
    if not isinstance(accessors, list) or not isinstance(views, list) or not (
        0 <= accessor_index < len(accessors)
    ):
        raise ConvertError(f"invalid accessor {accessor_index}")
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict) or "sparse" in accessor:
        raise ConvertError(f"accessor {accessor_index} is malformed/sparse")
    view_index = int(accessor.get("bufferView", -1))
    if not 0 <= view_index < len(views):
        raise ConvertError(f"accessor {accessor_index} has invalid view")
    view = views[view_index]
    if not isinstance(view, dict) or int(view.get("buffer", -1)) != 0:
        raise ConvertError(f"accessor {accessor_index} is not in buffer zero")
    packed = components * 4
    stride = int(view.get("byteStride", packed))
    if stride < packed or stride & 3:
        raise ConvertError(f"accessor {accessor_index} has invalid stride")
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    return accessor, start, stride


def position_accessors(gltf: dict[str, Any]) -> set[int]:
    result: set[int] = set()
    meshes = gltf.get("meshes")
    if not isinstance(meshes, list):
        raise ConvertError("meshes are missing")
    for mesh in meshes:
        if not isinstance(mesh, dict) or not isinstance(mesh.get("primitives"), list):
            raise ConvertError("mesh is malformed")
        for primitive in mesh["primitives"]:
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict) or "POSITION" not in attributes:
                raise ConvertError("primitive has no POSITION")
            result.add(int(attributes["POSITION"]))
    return result


def scale_positions(gltf: dict[str, Any], binary: bytearray) -> tuple[int, int]:
    accessor_count = 0
    value_count = 0
    for index in sorted(position_accessors(gltf)):
        accessor, start, stride = accessor_layout(gltf, index, 3)
        if int(accessor.get("componentType", -1)) != 5126 or accessor.get("type") != "VEC3":
            raise ConvertError(f"POSITION accessor {index} is not FLOAT VEC3")
        count = int(accessor.get("count", -1))
        if count < 0 or start + (count - 1) * stride + 12 > len(binary):
            raise ConvertError(f"POSITION accessor {index} is out of bounds")
        for item in range(count):
            offset = start + item * stride
            values = struct.unpack_from("<3f", binary, offset)
            struct.pack_into("<3f", binary, offset,
                             *(f32(value * 0.01) for value in values))
        for key in ("min", "max"):
            if key in accessor:
                raw = accessor[key]
                if not isinstance(raw, list) or len(raw) != 3:
                    raise ConvertError(f"POSITION accessor {index} has bad {key}")
                accessor[key] = [f32(float(value) * 0.01) for value in raw]
        accessor_count += 1
        value_count += count
    return accessor_count, value_count


def scale_inverse_binds(gltf: dict[str, Any], binary: bytearray) -> tuple[int, int]:
    skins = gltf.get("skins")
    if not isinstance(skins, list):
        raise ConvertError("skins are missing")
    seen: set[int] = set()
    matrix_count = 0
    joint_count = 0
    for skin in skins:
        if not isinstance(skin, dict):
            raise ConvertError("skin is malformed")
        accessor_index = int(skin.get("inverseBindMatrices", -1))
        joints = skin.get("joints")
        if not isinstance(joints, list):
            raise ConvertError("skin joints are malformed")
        joint_count += len(joints)
        if accessor_index in seen:
            continue
        seen.add(accessor_index)
        accessor, start, stride = accessor_layout(gltf, accessor_index, 16)
        if int(accessor.get("componentType", -1)) != 5126 or accessor.get("type") != "MAT4":
            raise ConvertError("inverse bind is not FLOAT MAT4")
        count = int(accessor.get("count", -1))
        if count < 0 or start + (count - 1) * stride + 64 > len(binary):
            raise ConvertError("inverse-bind accessor is out of bounds")
        for item in range(count):
            offset = start + item * stride
            values = list(struct.unpack_from("<16f", binary, offset))
            for lane in (12, 13, 14):
                values[lane] = f32(values[lane] * 0.01)
            struct.pack_into("<16f", binary, offset, *values)
        matrix_count += count
    return matrix_count, joint_count


def scale_nodes(gltf: dict[str, Any]) -> int:
    nodes = gltf.get("nodes")
    if not isinstance(nodes, list):
        raise ConvertError("nodes are missing")
    translated = 0
    for node in nodes:
        if not isinstance(node, dict) or "matrix" in node:
            raise ConvertError("matrix nodes are outside the bounded witness contract")
        if "translation" in node:
            raw = node["translation"]
            if not isinstance(raw, list) or len(raw) != 3:
                raise ConvertError("node translation is malformed")
            node["translation"] = [f32(float(value) * 0.01) for value in raw]
            translated += 1
        extras = node.get("extras")
        if isinstance(extras, dict):
            if "serialized_absolute_bind_translation" in extras:
                raw_absolute = extras.pop("serialized_absolute_bind_translation")
                extras["source_absolute_bind_translation_centimeters"] = raw_absolute
                extras["gltf_absolute_bind_translation_meters"] = [
                    f32(float(value) * 0.01) for value in raw_absolute
                ]
            if extras.pop("raw_game_coordinates", False) is True:
                extras["source_game_coordinates"] = "right_handed_y_up_centimeters"
                extras["gltf_coordinates"] = "right_handed_y_up_meters"
            if "portme" in extras:
                extras["portme"] = (
                    "PORTME: meter-scaled skin attached; exact title animation, "
                    "external-root ownership, and materials remain unresolved"
                )
    return translated


def convert_one(source_gltf: Path, output_dir: Path) -> dict[str, Any]:
    gltf = json.loads(source_gltf.read_text(encoding="utf-8"))
    buffers = gltf.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], dict):
        raise ConvertError(f"{source_gltf}: expected one external buffer")
    source_bin = source_gltf.parent / str(buffers[0].get("uri", ""))
    binary = bytearray(source_bin.read_bytes())
    if int(buffers[0].get("byteLength", -1)) != len(binary):
        raise ConvertError(f"{source_gltf}: buffer length differs")

    accessor_count, position_count = scale_positions(gltf, binary)
    inverse_count, joint_count = scale_inverse_binds(gltf, binary)
    translated_nodes = scale_nodes(gltf)

    skins = gltf["skins"]
    for skin in skins:
        skin["name"] = str(skin.get("name", "skin")).replace(
            ":raw_translation_bind", ":meter_translation_bind"
        )
        skin.setdefault("extras", {})["proof_scope"] = (
            "identity rest rotations; local/cumulative translations and "
            "translation-only inverse binds scaled from centimeters to meters"
        )

    old_extras = gltf.get("extras", {})
    gltf["extras"] = {
        "raw_coordinates": False,
        "source_raw_coordinates": True,
        "coordinate_contract": {
            "source": "right_handed_y_up_centimeters",
            "target": "right_handed_y_up_meters",
            "axis_mapping": "XYZ_to_XYZ",
            "linear_scale": 0.01,
            "quaternion_storage_if_animated": "game_wxyz_to_gltf_xyzw",
        },
        "proof_scope": (
            "source raw skin plus instruction-proved retain-XYZ centimeter-to-meter conversion"
        ),
        "source_raw_skin_extras": old_extras,
        "portme": PORTME,
    }
    gltf["asset"]["generator"] = "nfl_meter_skin_gltf.py (source: nfl_raw_skin_gltf.py)"

    output_stem = source_gltf.stem.replace("_raw_skin", "_meter_skin")
    output_gltf = output_dir / f"{output_stem}.gltf"
    output_bin = output_dir / f"{output_stem}.bin"
    output_dir.mkdir(parents=True, exist_ok=True)
    buffers[0]["uri"] = output_bin.name
    output_bin.write_bytes(binary)
    output_gltf.write_text(json.dumps(gltf, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    return {
        "source_gltf": source_gltf.name,
        "source_bin": source_bin.name,
        "source_gltf_sha256": sha256_file(source_gltf),
        "source_bin_sha256": sha256_file(source_bin),
        "output_gltf": output_gltf.name,
        "output_bin": output_bin.name,
        "output_gltf_sha256": sha256_file(output_gltf),
        "output_bin_sha256": sha256_file(output_bin),
        "position_accessor_count": accessor_count,
        "position_value_count": position_count,
        "skin_count": len(skins),
        "joint_count": joint_count,
        "inverse_bind_count": inverse_count,
        "translated_node_count": translated_nodes,
        "animation_count": len(gltf.get("animations", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path,
                        default=Path("assets/intermediate/nfl2k5/raw_skin_samples"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("assets/intermediate/nfl2k5/meter_skin_samples"))
    parser.add_argument("--manifest", type=Path,
                        default=Path("reports/assets/nfl_meter_skin_gltf_manifest.json"))
    args = parser.parse_args()

    outputs = [convert_one(args.raw_dir / f"{stem}.gltf", args.output_dir)
               for stem in STEMS]
    report = {
        "schema": SCHEMA,
        "contract": {
            "source_basis": "right_handed_y_up",
            "target_basis": "right_handed_y_up",
            "axis_mapping": "XYZ_to_XYZ",
            "source_linear_unit": "centimeter",
            "target_linear_unit": "meter",
            "linear_scale": 0.01,
            "position_binary32_rule": "f32(raw_f32 * 0.01)",
            "animation_emitted": False,
        },
        "summary": {
            "scene_count": len(outputs),
            "skin_count": sum(row["skin_count"] for row in outputs),
            "joint_count": sum(row["joint_count"] for row in outputs),
            "position_value_count": sum(row["position_value_count"] for row in outputs),
            "inverse_bind_count": sum(row["inverse_bind_count"] for row in outputs),
            "animation_count": sum(row["animation_count"] for row in outputs),
        },
        "outputs": outputs,
        "portme": PORTME,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    print(
        "NFL_METER_SKIN_GLTF_COMPLETE "
        f"scenes={report['summary']['scene_count']} "
        f"skins={report['summary']['skin_count']} "
        f"joints={report['summary']['joint_count']} "
        f"positions={report['summary']['position_value_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
