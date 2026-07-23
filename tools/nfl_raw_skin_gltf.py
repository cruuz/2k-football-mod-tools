#!/usr/bin/env python3
"""Attach executable-proved raw NFL 2K5 skins to five static glTF meshes.

This is a bounded proof exporter, not a coordinate-converted final model.  It
combines the complete static position/topology glTFs with the independently
validated sample transform and influence TSVs.  Joint local rotations remain
identity, local translations are serialized transform +0x50, and inverse bind
matrices are T(-serialized +0x40), exactly as proved by the rest-orientation
corpus. The later axis/root proof establishes right-handed centimeter XYZ;
this tool deliberately preserves those raw units and invents no animation or
external-root policy.
"""

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
REST_SCHEMA = "nfl2k5_rest_orientation/v1"
EXPECTED_REST_COUNTS = {
    "scene_count": 4_616,
    "shape_count": 54_966,
    "transform_count": 110_318,
    "root_transform_count": 54_966,
    "nonroot_transform_count": 55_352,
    "hierarchy_translation_exact_component_count": 330_954,
}

GROUPS = (
    {
        "source_stem": "0003_0113_lo_body",
        "shape_samples": {0: "player_LO_res"},
    },
    {
        "source_stem": "0346_0109_referee",
        "shape_samples": {0: "referee_high", 1: "referee_low"},
    },
    {
        "source_stem": "0348_0000_coach",
        "shape_samples": {0: "coach_body", 1: "coach_lod"},
    },
)

PORTME = [
    "PORTME: emit a separately validated meter-scaled variant using the proved retain-XYZ and scale-0.01 contract; this proof intentionally preserves raw centimeters.",
    "PORTME: bind decoded motion rotations only after proving exact sampled-pose application into local joint matrices.",
    "PORTME: attach root trajectories only after proving caller-specific external-parent ownership and loop-cycle accumulation.",
    "PORTME: select each hierarchy's external root parent from the original render-object call path.",
    "PORTME: map materials, embedded textures, normals, and UV sets without inventing shader/sampler semantics.",
    "PORTME: implement a validated edited-glTF to SCNE/archive writer.",
]


class SkinError(ValueError):
    """A source proof or glTF invariant failed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def align4(data: bytearray) -> None:
    data.extend(bytes((-len(data)) & 3))


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def load_transforms(path: Path) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for raw in read_tsv(path):
        row = {
            "sample": raw["sample"],
            "outer_index": int(raw["outer_index"]),
            "chunk_index": int(raw["chunk_index"]),
            "scene_name": raw["scene_name"],
            "shape_name": raw["shape_name"],
            "index": int(raw["transform_index"]),
            "name": raw["transform_name"],
            "parent": int(raw["parent_index"]),
            "absolute": tuple(float(raw[f"absolute_{axis}"]) for axis in "xyz"),
            "local": tuple(float(raw[f"local_{axis}"]) for axis in "xyz"),
        }
        grouped[raw["sample"]].append(row)

    for sample, rows in grouped.items():
        rows.sort(key=lambda item: int(item["index"]))
        if [int(item["index"]) for item in rows] != list(range(len(rows))):
            raise SkinError(f"{sample}: transform indices are not dense")
        if len(rows) != 25:
            raise SkinError(f"{sample}: expected 25 transforms, found {len(rows)}")
        roots = 0
        names: set[str] = set()
        for item in rows:
            index = int(item["index"])
            parent = int(item["parent"])
            name = str(item["name"])
            if name in names:
                raise SkinError(f"{sample}: duplicate transform name {name}")
            names.add(name)
            if parent == -1:
                roots += 1
            elif not 0 <= parent < index:
                raise SkinError(f"{sample}: transform {index} has parent {parent}")
            values = tuple(item["absolute"]) + tuple(item["local"])
            if not all(math.isfinite(float(value)) for value in values):
                raise SkinError(f"{sample}: transform {index} is non-finite")
        if roots != 1:
            raise SkinError(f"{sample}: expected one root, found {roots}")
    return dict(grouped)


def load_influences(path: Path) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for raw in read_tsv(path):
        count = int(raw["influence_count"])
        if count not in (1, 2, 3):
            raise SkinError(f"{raw['sample']}: invalid influence count {count}")
        influences = []
        for index in range(count):
            influences.append(
                (
                    int(raw[f"joint{index}_index"]),
                    raw[f"joint{index}_name"],
                    float(raw[f"weight{index}"]),
                )
            )
        grouped[raw["sample"]].append(
            {
                "vertex": int(raw["vertex_index"]),
                "influences": influences,
            }
        )
    for sample, rows in grouped.items():
        rows.sort(key=lambda item: int(item["vertex"]))
        if [int(item["vertex"]) for item in rows] != list(range(len(rows))):
            raise SkinError(f"{sample}: influenced vertices are not dense")
    return dict(grouped)


def append_view(
    gltf: dict[str, object],
    binary: bytearray,
    payload: bytes,
    *,
    target: int | None = None,
) -> int:
    align4(binary)
    offset = len(binary)
    binary.extend(payload)
    view: dict[str, object] = {
        "buffer": 0,
        "byteOffset": offset,
        "byteLength": len(payload),
    }
    if target is not None:
        view["target"] = target
    views = gltf.setdefault("bufferViews", [])
    assert isinstance(views, list)
    result = len(views)
    views.append(view)
    return result


def append_accessor(
    gltf: dict[str, object],
    view: int,
    component_type: int,
    count: int,
    type_name: str,
) -> int:
    accessors = gltf.setdefault("accessors", [])
    assert isinstance(accessors, list)
    result = len(accessors)
    accessors.append(
        {
            "bufferView": view,
            "byteOffset": 0,
            "componentType": component_type,
            "count": count,
            "type": type_name,
        }
    )
    return result


def encode_vertex_influences(
    sample: str,
    transforms: list[dict[str, object]],
    influences: list[dict[str, object]],
) -> tuple[bytes, bytes, Counter[int], float]:
    joints = bytearray()
    weights = bytearray()
    arities: Counter[int] = Counter()
    maximum_sum_error = 0.0
    for row in influences:
        active = list(row["influences"])
        arities[len(active)] += 1
        joint_values = [0, 0, 0, 0]
        weight_values = [0.0, 0.0, 0.0, 0.0]
        for slot, (joint, name, weight) in enumerate(active):
            if not 0 <= int(joint) < len(transforms):
                raise SkinError(f"{sample}: joint {joint} is out of range")
            if str(transforms[int(joint)]["name"]) != str(name):
                raise SkinError(
                    f"{sample}: joint {joint} name {name!r} differs from transform"
                )
            if not math.isfinite(float(weight)) or not 0.0 <= float(weight) <= 1.0:
                raise SkinError(f"{sample}: invalid weight {weight}")
            joint_values[slot] = int(joint)
            weight_values[slot] = float(weight)
        sum_error = abs(sum(weight_values) - 1.0)
        maximum_sum_error = max(maximum_sum_error, sum_error)
        if sum_error > 0.000001:
            raise SkinError(f"{sample}: weight sum error {sum_error}")
        joints.extend(struct.pack("<4H", *joint_values))
        weights.extend(struct.pack("<4f", *weight_values))
    return bytes(joints), bytes(weights), arities, maximum_sum_error


def encode_inverse_binds(transforms: list[dict[str, object]]) -> bytes:
    result = bytearray()
    for item in transforms:
        x, y, z = (float(value) for value in item["absolute"])
        # glTF stores column-major matrices for column-vector transforms.
        result.extend(
            struct.pack(
                "<16f",
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                -x, -y, -z, 1.0,
            )
        )
    return bytes(result)


def attach_sample(
    gltf: dict[str, object],
    binary: bytearray,
    sample: str,
    shape_index: int,
    transforms: list[dict[str, object]],
    influences: list[dict[str, object]],
) -> dict[str, object]:
    nodes = gltf.get("nodes")
    meshes = gltf.get("meshes")
    accessors = gltf.get("accessors")
    if not isinstance(nodes, list) or not isinstance(meshes, list) or not isinstance(accessors, list):
        raise SkinError("source glTF omits nodes, meshes, or accessors")
    candidates = [
        (index, node) for index, node in enumerate(nodes)
        if isinstance(node, dict)
        and isinstance(node.get("extras"), dict)
        and int(node["extras"].get("source_shape_index", -1)) == shape_index
    ]
    if len(candidates) != 1:
        raise SkinError(f"{sample}: found {len(candidates)} source shape nodes")
    mesh_node_index, mesh_node = candidates[0]
    mesh_index = int(mesh_node["mesh"])
    mesh = meshes[mesh_index]
    if not isinstance(mesh, dict) or not isinstance(mesh.get("primitives"), list):
        raise SkinError(f"{sample}: source mesh is malformed")
    if str(mesh.get("name")) != str(transforms[0]["shape_name"]):
        raise SkinError(
            f"{sample}: mesh name {mesh.get('name')!r} differs from transform sample"
        )
    vertex_counts = {
        int(accessors[int(primitive["attributes"]["POSITION"])]["count"])
        for primitive in mesh["primitives"]
    }
    if vertex_counts != {len(influences)}:
        raise SkinError(
            f"{sample}: position counts {vertex_counts} differ from {len(influences)} influences"
        )

    joint_bytes, weight_bytes, arities, maximum_sum_error = (
        encode_vertex_influences(sample, transforms, influences)
    )
    joint_view = append_view(gltf, binary, joint_bytes, target=34962)
    weight_view = append_view(gltf, binary, weight_bytes, target=34962)
    inverse_view = append_view(
        gltf, binary, encode_inverse_binds(transforms), target=None
    )
    joint_accessor = append_accessor(
        gltf, joint_view, 5123, len(influences), "VEC4"
    )
    weight_accessor = append_accessor(
        gltf, weight_view, 5126, len(influences), "VEC4"
    )
    inverse_accessor = append_accessor(
        gltf, inverse_view, 5126, len(transforms), "MAT4"
    )
    for primitive in mesh["primitives"]:
        primitive["attributes"]["JOINTS_0"] = joint_accessor
        primitive["attributes"]["WEIGHTS_0"] = weight_accessor

    joint_node_base = len(nodes)
    for item in transforms:
        nodes.append(
            {
                "name": f"{sample}:{item['name']}",
                "translation": [float(value) for value in item["local"]],
                "extras": {
                    "raw_game_coordinates": True,
                    "source_transform_index": int(item["index"]),
                    "source_transform_name": item["name"],
                    "serialized_absolute_bind_translation": [
                        float(value) for value in item["absolute"]
                    ],
                    "rest_rotation": [0.0, 0.0, 0.0, 1.0],
                },
            }
        )
    root_nodes = []
    for item in transforms:
        index = int(item["index"])
        parent = int(item["parent"])
        node_index = joint_node_base + index
        if parent == -1:
            root_nodes.append(node_index)
        else:
            parent_node = nodes[joint_node_base + parent]
            parent_node.setdefault("children", []).append(node_index)
    if len(root_nodes) != 1:
        raise SkinError(f"{sample}: generated {len(root_nodes)} skeleton roots")

    skins = gltf.setdefault("skins", [])
    assert isinstance(skins, list)
    skin_index = len(skins)
    skins.append(
        {
            "name": f"{sample}:raw_translation_bind",
            "inverseBindMatrices": inverse_accessor,
            "skeleton": root_nodes[0],
            "joints": [joint_node_base + index for index in range(len(transforms))],
            "extras": {
                "proof_scope": (
                    "identity rest rotations; +0x50 local translations; "
                    "T(-+0x40) inverse binds; raw game coordinate lanes"
                ),
            },
        }
    )
    mesh_node["skin"] = skin_index
    mesh_node["extras"]["portme"] = (
        "PORTME: raw-centimeter skin attached; proved 0.01-meter conversion is intentionally unapplied; external root and animation remain unresolved"
    )
    scene_index = int(gltf.get("scene", 0))
    scenes = gltf.get("scenes")
    if not isinstance(scenes, list) or not isinstance(scenes[scene_index], dict):
        raise SkinError(f"{sample}: source scene is malformed")
    scenes[scene_index].setdefault("nodes", []).append(root_nodes[0])

    return {
        "sample": sample,
        "shape_index": shape_index,
        "mesh_node_index": mesh_node_index,
        "mesh_name": mesh["name"],
        "primitive_count": len(mesh["primitives"]),
        "vertex_count": len(influences),
        "joint_count": len(transforms),
        "influence_arity_counts": {
            str(key): arities[key] for key in sorted(arities)
        },
        "maximum_weight_sum_error": maximum_sum_error,
    }


def export_group(
    group: dict[str, object],
    model_dir: Path,
    output_dir: Path,
    transforms: dict[str, list[dict[str, object]]],
    influences: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    stem = str(group["source_stem"])
    source_gltf = model_dir / f"{stem}.gltf"
    if not source_gltf.is_file():
        raise SkinError(f"missing source glTF {source_gltf}")
    gltf = json.loads(source_gltf.read_text(encoding="utf-8"))
    if gltf.get("asset", {}).get("generator") != "nfl_static_gltf.py":
        raise SkinError(f"{source_gltf}: unexpected source generator")
    buffers = gltf.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1:
        raise SkinError(f"{source_gltf}: expected one external buffer")
    source_bin = source_gltf.parent / str(buffers[0]["uri"])
    binary = bytearray(source_bin.read_bytes())
    if len(binary) != int(buffers[0]["byteLength"]):
        raise SkinError(f"{source_bin}: byteLength differs")
    if gltf.get("skins") or gltf.get("animations"):
        raise SkinError(f"{source_gltf}: source unexpectedly has skins/animations")

    details = []
    shape_samples = dict(group["shape_samples"])
    for shape_index, sample in sorted(shape_samples.items()):
        if sample not in transforms or sample not in influences:
            raise SkinError(f"{sample}: proof rows are missing")
        details.append(
            attach_sample(
                gltf, binary, str(sample), int(shape_index),
                transforms[str(sample)], influences[str(sample)],
            )
        )

    source_portme = gltf.get("extras", {}).get("portme", [])
    gltf["extras"] = {
        "raw_coordinates": True,
        "proof_scope": (
            "static position/topology plus executable/corpus-proved raw skin "
            "hierarchy, JOINTS_0/WEIGHTS_0, and translation-only inverse binds"
        ),
        "source_static_portme": source_portme,
        "portme": PORTME,
    }
    gltf["asset"]["generator"] = "nfl_raw_skin_gltf.py (source: nfl_static_gltf.py)"
    output_stem = f"{stem}_raw_skin"
    output_bin = output_dir / f"{output_stem}.bin"
    output_gltf = output_dir / f"{output_stem}.gltf"
    buffers[0]["uri"] = output_bin.name
    buffers[0]["byteLength"] = len(binary)
    gltf_bytes = (
        json.dumps(gltf, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    output_bin.write_bytes(binary)
    output_gltf.write_bytes(gltf_bytes)

    skinned_mesh_nodes = {int(item["mesh_node_index"]) for item in details}
    unskinned_nodes = [
        str(node.get("name", "")) for index, node in enumerate(gltf["nodes"])
        if index not in skinned_mesh_nodes and isinstance(node, dict) and "mesh" in node
    ]
    return {
        "source_gltf": str(source_gltf),
        "source_gltf_sha256": sha256_file(source_gltf),
        "source_bin": str(source_bin),
        "source_bin_sha256": sha256_file(source_bin),
        "output_gltf": output_gltf.name,
        "output_gltf_sha256": sha256(gltf_bytes),
        "output_bin": output_bin.name,
        "output_bin_sha256": sha256(bytes(binary)),
        "output_bin_bytes": len(binary),
        "skins": details,
        "unskinned_mesh_nodes": unskinned_nodes,
    }


def generate(
    model_dir: Path,
    transforms_path: Path,
    influences_path: Path,
    rest_report_path: Path,
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, object]:
    rest = json.loads(rest_report_path.read_text(encoding="utf-8"))
    if rest.get("schema") != REST_SCHEMA:
        raise SkinError("rest-orientation report schema differs")
    if rest.get("corpus", {}).get("counts") != EXPECTED_REST_COUNTS:
        raise SkinError("rest-orientation corpus counts differ")
    contract = rest.get("proved_contract", {})
    if not (
        contract.get("rest_local_rotation")
        == "identity quaternion [1,0,0,0]; rest local node transform is identity rotation plus +0x50.xyz translation"
        and contract.get("row_vector_inverse_bind")
        == "T(-transform[+0x40].xyz)"
    ):
        raise SkinError("rest-orientation contract differs")

    transforms = load_transforms(transforms_path)
    influences = load_influences(influences_path)
    expected_samples = {
        str(sample)
        for group in GROUPS
        for sample in dict(group["shape_samples"]).values()
    }
    if set(transforms) != expected_samples or set(influences) != expected_samples:
        raise SkinError("sample proof domains differ")

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        export_group(group, model_dir, output_dir, transforms, influences)
        for group in GROUPS
    ]
    all_skins = [skin for output in outputs for skin in output["skins"]]
    arities: Counter[int] = Counter()
    for skin in all_skins:
        arities.update(
            {
                int(key): int(value)
                for key, value in skin["influence_arity_counts"].items()
            }
        )
    report = {
        "schema": SCHEMA,
        "inputs": {
            "model_dir": str(model_dir),
            "transforms": str(transforms_path),
            "transforms_sha256": sha256_file(transforms_path),
            "influences": str(influences_path),
            "influences_sha256": sha256_file(influences_path),
            "rest_report": str(rest_report_path),
            "rest_report_sha256": sha256_file(rest_report_path),
        },
        "summary": {
            "output_scene_count": len(outputs),
            "skin_count": len(all_skins),
            "joint_node_count": sum(int(item["joint_count"]) for item in all_skins),
            "skinned_vertex_count": sum(int(item["vertex_count"]) for item in all_skins),
            "skinned_primitive_count": sum(int(item["primitive_count"]) for item in all_skins),
            "influence_arity_counts": {
                str(key): arities[key] for key in sorted(arities)
            },
            "maximum_weight_sum_error": max(
                float(item["maximum_weight_sum_error"]) for item in all_skins
            ),
            "raw_coordinate_conversion_applied": False,
            "animation_count": 0,
        },
        "outputs": outputs,
        "worked": [
            "attached dense JOINTS_0 and WEIGHTS_0 attributes for every vertex in five fully proved sample meshes",
            "emitted identity-rest joint hierarchies from serialized +0x50 local translations",
            "emitted translation-only inverse binds from serialized +0x40 cumulative bind translations",
            "preserved every source static primitive and external buffer payload",
        ],
        "failed": [
            "coachHeadGrp1 has no canonical transform/influence sample and remains an explicitly unskinned mesh node",
            "the proved meter conversion is intentionally unapplied; no animation, root motion, materials, normals, UVs, or reverse writer is claimed",
        ],
        "portme": PORTME,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--model-dir", type=Path,
        default=Path("assets/intermediate/nfl2k5/models"),
    )
    result.add_argument(
        "--transforms", type=Path,
        default=Path("reports/assets/nfl_transform_semantics_samples.tsv"),
    )
    result.add_argument(
        "--influences", type=Path,
        default=Path("reports/assets/nfl_transform_semantics_influences.tsv"),
    )
    result.add_argument(
        "--rest-report", type=Path,
        default=Path("reports/assets/nfl_rest_orientation.json"),
    )
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--manifest", type=Path, required=True)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = generate(
            args.model_dir, args.transforms, args.influences, args.rest_report,
            args.output_dir, args.manifest,
        )
    except (OSError, ValueError, KeyError, IndexError, struct.error, json.JSONDecodeError) as exc:
        print(f"nfl_raw_skin_gltf: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        "NFL_RAW_SKIN_GLTF_COMPLETE "
        f"scenes={summary['output_scene_count']} skins={summary['skin_count']} "
        f"joints={summary['joint_node_count']} vertices={summary['skinned_vertex_count']} "
        f"primitives={summary['skinned_primitive_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
