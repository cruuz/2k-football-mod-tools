#!/usr/bin/env python3
"""Stream the code-proven static NFL 2K5 SCNE geometry to glTF 2.0.

Register-0 ``FLOAT3`` positions are copied directly. Register-0
``NORMSHORT3`` positions are reconstructed with the executable-proved common
static-shader scale/offset MAD. Topology is decoded from the already bounded
NV2A push streams by ``nfl_scne_gltf``. No transform, material, texture,
normal, UV, skin, morph, or animation meaning is inferred.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import struct
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import ProbeError, decode_resource, parse_inventory
from nfl_scne_gltf import align4, decode_batches, gltf_topology
from nfl_scne_inventory import ScneError, parse_scene
from nfl_txtr import TxtrError


SCHEMA = "nfl2k5_static_gltf_manifest/v2"
DEFAULT_MINIMUM_FREE = 10 * 1024**3
POSITION_FORMATS = {"FLOAT3", "NORMSHORT3"}
PORTME = [
    "PORTME: map material records and embedded P8 textures to glTF materials without inventing sampler or shader semantics.",
    "PORTME: prove node hierarchy and transform ownership before applying matrices or changing the raw Xbox coordinate system.",
    "PORTME: map the remaining Xbox vertex registers to NORMAL/TEXCOORD/JOINTS/WEIGHTS semantics.",
    "PORTME: bind morph channels, skinning, skeletons, and animation to the exported static meshes.",
    "PORTME: implement a lossless edited-glTF to SCNE/archive writer.",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    result = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_value).strip("._-")
    return result[:80] or "scene"


def register_zero_format(compact: str) -> str:
    for item in compact.split("|"):
        parts = item.split(":")
        if parts and parts[0] == "r0" and len(parts) >= 2:
            return parts[1]
    return "MISSING"


def align_value(value: int, alignment: int = 4) -> int:
    return (value + alignment - 1) & -alignment


def float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def normshort(value: int) -> float:
    return value / (32767.0 if value >= 0 else 32768.0)


def topology_output_count(mode_counts: dict[str, int], raw_count: int) -> int:
    active = {name: count for name, count in mode_counts.items() if name != "END" and count}
    if sum(active.values()) != 1:
        raise ScneError(f"expected one bounded primitive batch, got {active}")
    mode = next(iter(active))
    if mode == "QUADS":
        if raw_count % 4:
            raise ScneError(f"QUADS count {raw_count} is not divisible by four")
        return raw_count // 4 * 6
    if mode in {
        "POINTS", "LINES", "LINE_STRIP", "TRIANGLES", "TRIANGLE_STRIP",
        "TRIANGLE_FAN",
    }:
        return raw_count
    if mode == "LINE_LOOP":
        return raw_count * 2 if raw_count >= 2 else 0
    if mode == "QUAD_STRIP":
        if raw_count < 4 or raw_count % 2:
            raise ScneError(f"QUAD_STRIP count {raw_count} is invalid")
        return (raw_count // 2 - 1) * 6
    if mode == "POLYGON":
        return max(0, raw_count - 2) * 3
    raise ScneError(f"PORTME: unsupported primitive mode {mode}")


def read_source_scenes(path: Path) -> tuple[dict[tuple[int, int], dict[str, object]], dict]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema") != "nfl2k5_scne_inventory/v1":
        raise ScneError(f"unexpected SCNE inventory schema in {path}")
    result: dict[tuple[int, int], dict[str, object]] = {}
    for scene in report["scenes"]:
        key = (int(scene["outer_index"]), int(scene["chunk_index"]))
        if key in result:
            raise ScneError(f"duplicate SCNE identity {key}")
        result[key] = scene
    return result, report


def estimate_reports(
    shapes_path: Path,
    submeshes_path: Path,
    selected_keys: set[tuple[int, int]] | None,
    source_scenes: dict[tuple[int, int], dict[str, object]],
) -> dict[str, object]:
    shapes: dict[tuple[int, int], dict[str, object]] = {}
    scene_shapes: dict[int, list[int]] = {
        int(scene["scene_index"]): []
        for key, scene in source_scenes.items()
        if selected_keys is None or key in selected_keys
    }
    summary: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    with shapes_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, dialect="excel-tab"):
            source_key = (int(row["outer_index"]), int(row["chunk_index"]))
            if selected_keys is not None and source_key not in selected_keys:
                continue
            scene_index = int(row["scene_index"])
            shape_index = int(row["index"])
            position_format = register_zero_format(row["attribute_descriptors"])
            vertex_count = int(row["vertex_count"])
            eligible = position_format in POSITION_FORMATS and vertex_count > 0
            key = (scene_index, shape_index)
            shapes[key] = {
                "eligible": eligible,
                "position_format": position_format,
                "vertex_count": vertex_count,
                "submesh_count": int(row["submesh_count"]),
            }
            scene_shapes[scene_index].append(shape_index)
            format_counts[position_format] += 1
            summary["shape_count"] += 1
            if eligible:
                summary["eligible_shape_count"] += 1
                summary[f"{position_format.lower()}_shape_count"] += 1
                summary["vertex_count"] += vertex_count
            else:
                summary["withheld_shape_count"] += 1

    submesh_counts: Counter[tuple[int, int]] = Counter()
    per_scene_submeshes: Counter[int] = Counter()
    per_scene_raw: Counter[int] = Counter()
    per_scene_output: Counter[int] = Counter()
    with submeshes_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, dialect="excel-tab"):
            source_key = (int(row["outer_index"]), int(row["chunk_index"]))
            if selected_keys is not None and source_key not in selected_keys:
                continue
            key = (int(row["scene_index"]), int(row["shape_index"]))
            if key not in shapes:
                raise ScneError(f"submesh references unknown shape {key}")
            if not shapes[key]["eligible"]:
                continue
            if row["all_vertex_references_in_bounds"] != "True":
                raise ScneError(f"unbounded topology in source reports for shape {key}")
            raw_count = int(row["index_element_count"]) + int(row["draw_array_vertex_count"])
            output_count = topology_output_count(
                json.loads(row["primitive_mode_counts"]), raw_count
            )
            if output_count <= 0:
                raise ScneError(f"eligible shape {key} has an empty topology batch")
            submesh_counts[key] += 1
            scene_index = key[0]
            per_scene_submeshes[scene_index] += 1
            per_scene_raw[scene_index] += raw_count
            per_scene_output[scene_index] += output_count
            summary["primitive_count"] += 1
            summary["raw_index_count"] += raw_count
            summary["gltf_index_count"] += output_count

    binary_bytes = 0
    exported_scenes = 0
    selected_scene_indices = sorted(scene_shapes)
    for scene_index in selected_scene_indices:
        cursor = 0
        eligible_in_scene = False
        for shape_index in sorted(scene_shapes[scene_index]):
            item = shapes[(scene_index, shape_index)]
            if not item["eligible"]:
                continue
            expected = int(item["submesh_count"])
            if submesh_counts[(scene_index, shape_index)] != expected:
                raise ScneError(
                    f"eligible shape {(scene_index, shape_index)} has "
                    f"{submesh_counts[(scene_index, shape_index)]}/{expected} bounded submeshes"
                )
            eligible_in_scene = True
            cursor = align_value(cursor)
            cursor += int(item["vertex_count"]) * 12
            # The corpus has one batch per submesh.  Account for each possible
            # u16 accessor alignment using report order in the exact exporter;
            # this estimate conservatively rounds the combined index span.
            cursor = align_value(cursor)
        if eligible_in_scene:
            # At most two alignment bytes are needed for each index accessor.
            cursor += per_scene_output[scene_index] * 2
            cursor += per_scene_submeshes[scene_index] * 2
            binary_bytes += align_value(cursor)
            exported_scenes += 1
    summary["scene_count"] = len(selected_scene_indices)
    summary["exported_scene_count"] = exported_scenes
    summary["withheld_scene_count"] = len(selected_scene_indices) - exported_scenes
    summary["estimated_binary_bytes_upper_bound"] = binary_bytes
    for key in (
        "shape_count", "eligible_shape_count", "withheld_shape_count",
        "float3_shape_count", "normshort3_shape_count",
        "vertex_count", "primitive_count", "raw_index_count", "gltf_index_count",
    ):
        summary.setdefault(key, 0)
    conservative = (
        binary_bytes
        + summary["eligible_shape_count"] * 8192
        + summary["primitive_count"] * 4096
        + len(selected_scene_indices) * 16384
        + 64 * 1024**2
    )
    return {
        "summary": dict(summary),
        "register_zero_format_counts": dict(sorted(format_counts.items())),
        "conservative_required_bytes": conservative,
    }


def position_descriptor(shape: dict[str, object]) -> dict[str, object] | None:
    return next(
        (
            item for item in shape["attribute_descriptors"]
            if int(item["register"]) == 0
        ),
        None,
    )


def export_scene(
    output: bytes,
    scene: dict[str, object],
    source: dict[str, object],
    bin_name: str,
) -> tuple[dict[str, object] | None, bytes, dict[str, object]]:
    binary = bytearray()
    buffer_views: list[dict[str, object]] = []
    accessors: list[dict[str, object]] = []
    meshes: list[dict[str, object]] = []
    nodes: list[dict[str, object]] = []
    eligible_indices: list[int] = []
    withheld: list[dict[str, object]] = []
    totals: Counter[str] = Counter()
    submeshes_by_shape: dict[int, list[dict[str, object]]] = defaultdict(list)
    for submesh in scene["submeshes"]:
        submeshes_by_shape[int(submesh["shape_index"])].append(submesh)

    for shape in scene["shapes"]:
        shape_index = int(shape["index"])
        position = position_descriptor(shape)
        position_format = str(position["format_name"]) if position else "MISSING"
        vertex_count = int(shape["vertex_count"])
        if position_format not in POSITION_FORMATS:
            withheld.append(
                {
                    "shape_index": shape_index,
                    "shape_name": shape["name"],
                    "position_format": position_format,
                    "reason": "PORTME: register-0 POSITION format has no executable-proved decoder",
                }
            )
            continue
        if vertex_count <= 0:
            withheld.append(
                {
                    "shape_index": shape_index,
                    "shape_name": shape["name"],
                    "position_format": position_format,
                    "reason": "PORTME: zero-vertex shape cannot form a glTF mesh",
                }
            )
            continue
        assert position is not None
        stream = next(
            (
                item for item in shape["vertex_streams"]
                if int(item["stream_index"]) == int(position["stream_index"])
            ),
            None,
        )
        if stream is None:
            raise ScneError(
                f"{position_format} shape {shape_index} has no source vertex stream"
            )

        decode_extras: dict[str, object]
        scale: float | None = None
        offset: tuple[float, float, float] | None = None
        if position_format == "NORMSHORT3":
            record_offset = int(shape["record_offset"])
            scale = struct.unpack_from("<f", output, record_offset + 0x10)[0]
            offset = struct.unpack_from("<3f", output, record_offset + 0x20)
            if not math.isfinite(scale) or not all(math.isfinite(value) for value in offset):
                raise ScneError(
                    f"scene {scene['scene_index']} shape {shape_index}: non-finite "
                    "NORMSHORT3 scale/offset"
                )
            decode_extras = {
                "equation": "position.xyz = normshort3(register0.xyz) * scale + offset.xyz",
                "xbox_signed_normalization": (
                    "value/32767 for nonnegative; value/32768 for negative"
                ),
                "serialized_scale_field": "+0x10",
                "serialized_offset_fields": ["+0x20", "+0x24", "+0x28"],
                "scale": scale,
                "offset": list(offset),
                "runtime_shader_constant_c_minus_88": [*offset, scale],
                "shader_instruction": (
                    "MAD r4.xyz, v0.xyzz, c[-88].wwww, c[-88].xyzz"
                ),
            }
        else:
            decode_extras = {
                "equation": "position.xyz = little_endian_FLOAT3(register0.xyz)",
                "identity_decode": True,
            }

        align4(binary)
        position_offset = len(binary)
        minima = [math.inf, math.inf, math.inf]
        maxima = [-math.inf, -math.inf, -math.inf]
        for vertex in range(vertex_count):
            source_offset = (
                int(stream["offset"])
                + vertex * int(stream["stride"])
                + int(position["byte_offset"])
            )
            if position_format == "FLOAT3":
                values = struct.unpack_from("<3f", output, source_offset)
                packed = struct.pack("<3f", *values)
            else:
                assert scale is not None and offset is not None
                packed_values = struct.unpack_from("<3h", output, source_offset)
                # Xbox vertex fetch converts each component to binary32; the
                # shader then applies the common scale/offset MAD. Round the
                # glTF values to binary32 before calculating accessor bounds.
                values = tuple(
                    float32(float32(normshort(value)) * scale + offset[axis])
                    for axis, value in enumerate(packed_values)
                )
                packed = struct.pack("<3f", *values)
            if not all(math.isfinite(value) for value in values):
                raise ScneError(
                    f"scene {scene['scene_index']} shape {shape_index}: non-finite "
                    f"{position_format} position at vertex {vertex}"
                )
            binary.extend(packed)
            for axis, value in enumerate(values):
                minima[axis] = min(minima[axis], value)
                maxima[axis] = max(maxima[axis], value)
        position_view = len(buffer_views)
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": position_offset,
                "byteLength": vertex_count * 12,
                "target": 34962,
            }
        )
        position_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": position_view,
                "byteOffset": 0,
                "componentType": 5126,
                "count": vertex_count,
                "type": "VEC3",
                "min": minima,
                "max": maxima,
            }
        )

        primitives: list[dict[str, object]] = []
        for submesh in submeshes_by_shape[shape_index]:
            if submesh["unknown_method_counts"]:
                raise ScneError(
                    f"scene {scene['scene_index']} shape {shape_index}: topology "
                    "contains an unproved NV2A method"
                )
            if not submesh["all_vertex_references_in_bounds"]:
                raise ScneError(
                    f"scene {scene['scene_index']} shape {shape_index}: unbounded topology"
                )
            batches = decode_batches(
                output,
                int(submesh["command_offset"]),
                int(submesh["primary_command_word_count"]),
            )
            if len(batches) != 1:
                raise ScneError(
                    f"scene {scene['scene_index']} shape {shape_index} submesh "
                    f"{submesh['submesh_index']}: expected one batch, got {len(batches)}"
                )
            xbox_mode, raw_indices = batches[0]
            gltf_mode, indices, conversion = gltf_topology(xbox_mode, raw_indices)
            if not indices:
                raise ScneError(
                    f"scene {scene['scene_index']} shape {shape_index}: empty glTF topology"
                )
            if min(indices) < 0 or max(indices) >= vertex_count:
                raise ScneError(
                    f"scene {scene['scene_index']} shape {shape_index}: index exceeds vertex range"
                )
            if max(indices) > 0xFFFF:
                raise ScneError("u16 Xbox topology cannot be represented as a glTF u16 accessor")
            align4(binary)
            index_offset = len(binary)
            binary.extend(struct.pack(f"<{len(indices)}H", *indices))
            index_view = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": index_offset,
                    "byteLength": len(indices) * 2,
                    "target": 34963,
                }
            )
            index_accessor = len(accessors)
            accessors.append(
                {
                    "bufferView": index_view,
                    "byteOffset": 0,
                    "componentType": 5123,
                    "count": len(indices),
                    "type": "SCALAR",
                    "min": [min(indices)],
                    "max": [max(indices)],
                }
            )
            primitives.append(
                {
                    "attributes": {"POSITION": position_accessor},
                    "indices": index_accessor,
                    "mode": gltf_mode,
                    "extras": {
                        "source_submesh_index": int(submesh["submesh_index"]),
                        "source_material_index": int(submesh["material_index"]),
                        "source_material_name": submesh["material_name"],
                        "source_auxiliary_index": int(submesh["auxiliary_index"]),
                        "xbox_primitive_mode": xbox_mode,
                        "topology_conversion": conversion,
                        "raw_index_count": len(raw_indices),
                        "gltf_index_count": len(indices),
                        "portme": "PORTME: material/texture binding withheld pending proved shader semantics",
                    },
                }
            )
            totals["primitive_count"] += 1
            totals["raw_index_count"] += len(raw_indices)
            totals["gltf_index_count"] += len(indices)

        if not primitives:
            raise ScneError(
                f"scene {scene['scene_index']} shape {shape_index}: "
                f"{position_format} shape has no topology"
            )
        mesh_index = len(meshes)
        mesh_name = str(shape["name"] or f"shape_{shape_index}")
        meshes.append(
            {
                "name": mesh_name,
                "primitives": primitives,
                "extras": {
                    "source_shape_index": shape_index,
                    "source_record_offset": int(shape["record_offset"]),
                    "position_format": position_format,
                    "position_decode": decode_extras,
                    "vertex_attribute_descriptors": shape["attribute_descriptors"],
                    "transform_record_count": int(shape["transform_count"]),
                    "morph_channel_record_count": int(shape["morph_channel_count"]),
                    "raw_coordinates": True,
                },
            }
        )
        nodes.append(
            {
                "name": mesh_name,
                "mesh": mesh_index,
                "extras": {
                    "source_shape_index": shape_index,
                    "raw_coordinates": True,
                    "portme": "PORTME: node transform and hierarchy intentionally not applied",
                },
            }
        )
        eligible_indices.append(shape_index)
        totals["mesh_count"] += 1
        totals[f"{position_format.lower()}_shape_count"] += 1
        totals["vertex_count"] += vertex_count

    if not meshes:
        return None, b"", {
            "eligible_shape_indices": [],
            "withheld_shapes": withheld,
            "mesh_count": 0,
            "primitive_count": 0,
            "vertex_count": 0,
            "raw_index_count": 0,
            "gltf_index_count": 0,
        }
    align4(binary)
    document = {
        "asset": {
            "version": "2.0",
            "generator": "nfl_static_gltf.py",
            "extras": {
                "proof_scope": (
                    "register-0 FLOAT3 identity and NORMSHORT3 executable-proved "
                    "scale/offset positions plus bounded NV2A topology only"
                ),
                "source": {
                    "scene_index": int(scene["scene_index"]),
                    "outer_index": int(scene["outer_index"]),
                    "chunk_index": int(scene["chunk_index"]),
                    "scene_name": scene["name"],
                    "decoded_sha256": source["decoded_sha256"],
                },
            },
        },
        "scene": 0,
        "scenes": [{"name": scene["name"], "nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "buffers": [{"uri": bin_name, "byteLength": len(binary)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
        "extras": {
            "raw_coordinates": True,
            "withheld_shapes": withheld,
            "portme": PORTME,
        },
    }
    detail = {
        "eligible_shape_indices": eligible_indices,
        "withheld_shapes": withheld,
        **dict(totals),
    }
    return document, bytes(binary), detail


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument(
        "--resource-scan", type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    parser.add_argument(
        "--scne-inventory", type=Path,
        default=Path("reports/assets/nfl2k5_scne_inventory.json"),
    )
    parser.add_argument(
        "--shapes-tsv", type=Path,
        default=Path("reports/assets/nfl2k5_scne_shapes.tsv"),
    )
    parser.add_argument(
        "--submeshes-tsv", type=Path,
        default=Path("reports/assets/nfl2k5_scne_submeshes.tsv"),
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("assets/intermediate/nfl2k5/models"),
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--only-outer", type=int)
    parser.add_argument("--only-chunk", type=int)
    parser.add_argument("--minimum-free-bytes", type=int, default=DEFAULT_MINIMUM_FREE)
    parser.add_argument("--estimate-only", action="store_true")
    return parser.parse_args()


def ensure_space(path: Path, required: int, reserve: int) -> int:
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free - required < reserve:
        raise ScneError(
            f"disk safety check failed: free={free}, required={required}, "
            f"reserve={reserve}"
        )
    return free


def main() -> int:
    args = parse_args()
    if (args.only_outer is None) != (args.only_chunk is None):
        raise ScneError("--only-outer and --only-chunk must be supplied together")
    if args.minimum_free_bytes < 0:
        raise ScneError("--minimum-free-bytes cannot be negative")

    source_scenes, source_report = read_source_scenes(args.scne_inventory)
    selected_keys = (
        {(args.only_outer, args.only_chunk)} if args.only_outer is not None else None
    )
    if selected_keys is not None and not selected_keys <= set(source_scenes):
        raise ScneError(f"requested SCNE identity is absent: {selected_keys}")
    estimate = estimate_reports(
        args.shapes_tsv, args.submeshes_tsv, selected_keys, source_scenes
    )
    free = shutil.disk_usage(args.output_dir.parent if args.output_dir.parent.exists() else ".").free
    print(
        "NFL2K5_STATIC_GLTF_PREFLIGHT "
        f"scenes={estimate['summary']['scene_count']} "
        f"eligible_shapes={estimate['summary']['eligible_shape_count']} "
        f"estimated_binary_upper={estimate['summary']['estimated_binary_bytes_upper_bound']} "
        f"conservative_required={estimate['conservative_required_bytes']} "
        f"free={free} reserve={args.minimum_free_bytes}",
        flush=True,
    )
    if args.estimate_only:
        return 0
    ensure_space(
        args.output_dir,
        int(estimate["conservative_required_bytes"]),
        args.minimum_free_bytes,
    )
    manifest_path = args.manifest or args.output_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    resource_inventory, resources = parse_inventory(args.resource_scan)
    scne_resources = [resource for resource in resources if resource.kind == "SCNE"]
    declared = int(resource_inventory["summary"]["resource_kind_counts"]["SCNE"])
    if len(scne_resources) != declared or len(source_scenes) != declared:
        raise ScneError(
            f"SCNE source count mismatch resources={len(scne_resources)} "
            f"inventory={len(source_scenes)} declared={declared}"
        )
    archive = parse_archive(args.index)
    exports: list[dict[str, object]] = []
    totals: Counter[str] = Counter()
    conversion_cache: dict[tuple[object, ...], dict[str, str]] = {}
    selected_count = int(estimate["summary"]["scene_count"])
    progress = 0

    for global_scene_index, resource in enumerate(scne_resources):
        key = (resource.outer_index, resource.chunk_index)
        if selected_keys is not None and key not in selected_keys:
            continue
        progress += 1
        source = source_scenes.get(key)
        if source is None or int(source["scene_index"]) != global_scene_index:
            raise ScneError(f"SCNE identity/order mismatch at {key}")
        span = read_entry_range(
            archive,
            archive.entries[resource.outer_index],
            resource.chunk_offset,
            0x20 + resource.stored_size,
        )
        output, decode_detail = decode_resource(span, resource)
        if decode_detail["decoded_sha256"] != source["decoded_sha256"]:
            raise ScneError(f"decoded SHA-256 mismatch for SCNE {key}")
        scene, _, _, _ = parse_scene(
            global_scene_index, resource, output, conversion_cache
        )
        scene["decoded_sha256"] = decode_detail["decoded_sha256"]
        base = (
            f"{resource.outer_index:04d}_{resource.chunk_index:04d}_"
            f"{safe_name(str(scene['name']))}"
        )
        gltf_name = f"{base}.gltf"
        bin_name = f"{base}.bin"
        document, binary, detail = export_scene(output, scene, source, bin_name)
        common = {
            "scene_index": global_scene_index,
            "outer_index": resource.outer_index,
            "chunk_index": resource.chunk_index,
            "scene_name": scene["name"],
            "decoded_sha256": source["decoded_sha256"],
            "source_shape_count": len(scene["shapes"]),
            "eligible_shape_indices": detail["eligible_shape_indices"],
            "withheld_shapes": detail["withheld_shapes"],
        }
        if document is None:
            exports.append(
                {
                    **common,
                    "status": "withheld",
                    "portme": (
                        "PORTME: scene has no shape with an executable-proved "
                        "nonempty register-0 position"
                    ),
                }
            )
            totals["withheld_scene_count"] += 1
        else:
            gltf_bytes = (
                json.dumps(document, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            ensure_space(
                args.output_dir,
                len(binary) + len(gltf_bytes) + 16 * 1024**2,
                args.minimum_free_bytes,
            )
            bin_path = args.output_dir / bin_name
            gltf_path = args.output_dir / gltf_name
            bin_path.write_bytes(binary)
            gltf_path.write_bytes(gltf_bytes)
            exports.append(
                {
                    **common,
                    "status": "exported",
                    "gltf": gltf_name,
                    "bin": bin_name,
                    "gltf_sha256": hashlib.sha256(gltf_bytes).hexdigest(),
                    "bin_sha256": hashlib.sha256(binary).hexdigest(),
                    "binary_bytes": len(binary),
                    "mesh_count": int(detail["mesh_count"]),
                    "primitive_count": int(detail["primitive_count"]),
                    "vertex_count": int(detail["vertex_count"]),
                    "raw_index_count": int(detail["raw_index_count"]),
                    "gltf_index_count": int(detail["gltf_index_count"]),
                    "float3_shape_count": int(detail.get("float3_shape_count", 0)),
                    "normshort3_shape_count": int(
                        detail.get("normshort3_shape_count", 0)
                    ),
                }
            )
            totals.update(
                exported_scene_count=1,
                binary_bytes=len(binary),
                mesh_count=int(detail["mesh_count"]),
                primitive_count=int(detail["primitive_count"]),
                vertex_count=int(detail["vertex_count"]),
                raw_index_count=int(detail["raw_index_count"]),
                gltf_index_count=int(detail["gltf_index_count"]),
                float3_shape_count=int(detail.get("float3_shape_count", 0)),
                normshort3_shape_count=int(detail.get("normshort3_shape_count", 0)),
            )
        totals["scene_count"] += 1
        totals["source_shape_count"] += len(scene["shapes"])
        totals["eligible_shape_count"] += len(detail["eligible_shape_indices"])
        totals["withheld_shape_count"] += len(detail["withheld_shapes"])
        if progress % 100 == 0 or progress == selected_count:
            print(
                f"exported/withheld {progress}/{selected_count} SCNE scenes",
                file=sys.stderr,
                flush=True,
            )

    expected = estimate["summary"]
    for key in (
        "scene_count", "exported_scene_count", "withheld_scene_count",
        "eligible_shape_count", "withheld_shape_count",
        "float3_shape_count", "normshort3_shape_count", "vertex_count",
        "primitive_count", "raw_index_count", "gltf_index_count",
    ):
        if int(totals[key]) != int(expected[key]):
            raise ScneError(
                f"export total {key}={totals[key]} disagrees with report estimate {expected[key]}"
            )
    summary = {key: int(value) for key, value in sorted(totals.items())}
    for key in (
        "exported_scene_count", "withheld_scene_count", "eligible_shape_count",
        "withheld_shape_count", "mesh_count", "primitive_count", "vertex_count",
        "float3_shape_count", "normshort3_shape_count",
        "raw_index_count", "gltf_index_count", "binary_bytes",
    ):
        summary.setdefault(key, 0)
    summary["all_exported_positions_executable_proved"] = True
    summary["all_exported_positions_float3_or_normshort3"] = True
    summary["all_exported_topology_bounded"] = True
    manifest = {
        "schema": SCHEMA,
        "source_index": str(args.index),
        "source_resource_scan": str(args.resource_scan),
        "source_scne_inventory": str(args.scne_inventory),
        "source_hashes": {
            "resource_scan_sha256": sha256_file(args.resource_scan),
            "scne_inventory_sha256": sha256_file(args.scne_inventory),
            "shapes_tsv_sha256": sha256_file(args.shapes_tsv),
            "submeshes_tsv_sha256": sha256_file(args.submeshes_tsv),
        },
        "selection": (
            {"outer_index": args.only_outer, "chunk_index": args.only_chunk}
            if args.only_outer is not None
            else "all"
        ),
        "safety_policy": {
            "minimum_free_bytes": args.minimum_free_bytes,
            "estimated_binary_bytes_upper_bound": expected[
                "estimated_binary_bytes_upper_bound"
            ],
            "conservative_required_bytes": estimate["conservative_required_bytes"],
        },
        "register_zero_format_counts": estimate["register_zero_format_counts"],
        "summary": summary,
        "portme": PORTME,
        "exports": exports,
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    ensure_space(
        manifest_path.parent,
        len(manifest_bytes) + 16 * 1024**2,
        args.minimum_free_bytes,
    )
    manifest_path.write_bytes(manifest_bytes)
    print(
        "NFL2K5_STATIC_GLTF_COMPLETE "
        f"scenes={summary['exported_scene_count']}/{summary['scene_count']} "
        f"meshes={summary['mesh_count']} primitives={summary['primitive_count']} "
        f"vertices={summary['vertex_count']} -> {manifest_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ScneError, ProbeError, TxtrError, struct.error, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
