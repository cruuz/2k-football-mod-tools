#!/usr/bin/env python3
"""Export one code-proven NFL 2K5 SCNE shape as glTF 2.0.

The exporter is intentionally bounded.  It accepts positions only when Xbox
input register 0 is an uncompressed FLOAT3, decodes the per-submesh NV2A push
streams, and emits standard glTF primitive topology.  Other recovered Xbox
input registers remain in ``extras`` until their shader semantics are proven.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
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
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_inventory import ScneError, parse_scene, u32


def align4(data: bytearray) -> None:
    data.extend(b"\0" * ((-len(data)) & 3))


def decode_batches(data: bytes, offset: int, word_count: int) -> list[tuple[int, list[int]]]:
    end = offset + word_count * 4
    cursor = offset
    active_mode: int | None = None
    active_indices: list[int] = []
    batches: list[tuple[int, list[int]]] = []

    def flush() -> None:
        nonlocal active_mode, active_indices
        if active_mode is not None and active_indices:
            batches.append((active_mode, active_indices))
        active_mode = None
        active_indices = []

    while cursor < end:
        header = u32(data, cursor)
        cursor += 4
        signature = header & 0xE0030003
        if signature not in (0, 0x40000000):
            raise ScneError(f"unsupported push word 0x{header:08x} at 0x{cursor - 4:x}")
        method = header & 0x1FFC
        count = (header >> 18) & 0x7FF
        if cursor + count * 4 > end:
            raise ScneError("push method parameters exceed declared command word count")
        parameters = struct.unpack_from(f"<{count}I", data, cursor)
        cursor += count * 4
        if method == 0x17FC:
            for parameter in parameters:
                if parameter == 0:
                    flush()
                else:
                    flush()
                    active_mode = parameter
        elif method == 0x1800:
            if active_mode is None:
                raise ScneError("ARRAY_ELEMENT16 outside SET_BEGIN_END")
            for parameter in parameters:
                active_indices.extend((parameter & 0xFFFF, parameter >> 16))
        elif method == 0x1808:
            if active_mode is None:
                raise ScneError("ARRAY_ELEMENT32 outside SET_BEGIN_END")
            active_indices.extend(parameters)
        elif method == 0x1810:
            if active_mode is None:
                raise ScneError("DRAW_ARRAYS outside SET_BEGIN_END")
            for parameter in parameters:
                start = parameter & 0x00FFFFFF
                count = (parameter >> 24) + 1
                active_indices.extend(range(start, start + count))
        else:
            # State methods do not contribute topology, but preserving them in
            # the inventory remains useful.  No unrecognized method may alter
            # the index list in this proof exporter.
            continue
    flush()
    if cursor != end:
        raise ScneError("push parser did not stop at its declared boundary")
    return batches


def gltf_topology(xbox_mode: int, indices: list[int]) -> tuple[int, list[int], str]:
    if xbox_mode == 1:  # points
        return 0, indices, "POINTS"
    if xbox_mode == 2:  # lines
        if len(indices) % 2:
            raise ScneError("LINES batch has an odd index count")
        return 1, indices, "LINES"
    if xbox_mode == 3:  # line loop -> explicit lines
        if len(indices) < 2:
            return 1, [], "LINE_LOOP_AS_LINES"
        expanded: list[int] = []
        for first, second in zip(indices, indices[1:] + indices[:1]):
            expanded.extend((first, second))
        return 1, expanded, "LINE_LOOP_AS_LINES"
    if xbox_mode == 4:
        return 3, indices, "LINE_STRIP"
    if xbox_mode == 5:
        if len(indices) % 3:
            raise ScneError("TRIANGLES batch is not divisible by three")
        return 4, indices, "TRIANGLES"
    if xbox_mode == 6:
        return 5, indices, "TRIANGLE_STRIP"
    if xbox_mode == 7:
        return 6, indices, "TRIANGLE_FAN"
    if xbox_mode == 8:  # quads -> triangles
        if len(indices) % 4:
            raise ScneError("QUADS batch is not divisible by four")
        expanded = []
        for index in range(0, len(indices), 4):
            a, b, c, d = indices[index:index + 4]
            expanded.extend((a, b, c, a, c, d))
        return 4, expanded, "QUADS_AS_TRIANGLES"
    if xbox_mode == 9:  # quad strip -> triangles
        if len(indices) < 4 or len(indices) % 2:
            raise ScneError("QUAD_STRIP batch has an invalid index count")
        expanded = []
        for index in range(0, len(indices) - 2, 2):
            a, b, c, d = indices[index:index + 4]
            expanded.extend((a, b, c, b, d, c))
        return 4, expanded, "QUAD_STRIP_AS_TRIANGLES"
    if xbox_mode == 10:  # polygon -> triangle fan
        if len(indices) < 3:
            return 4, [], "POLYGON_AS_TRIANGLES"
        expanded = []
        for index in range(1, len(indices) - 1):
            expanded.extend((indices[0], indices[index], indices[index + 1]))
        return 4, expanded, "POLYGON_AS_TRIANGLES"
    raise ScneError(f"PORTME: unsupported Xbox primitive mode {xbox_mode}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument(
        "--resource-scan", type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    parser.add_argument("--outer", type=int, required=True)
    parser.add_argument("--chunk", type=int, required=True)
    parser.add_argument("--shape", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bin", type=Path, dest="bin_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _, resources = parse_inventory(args.resource_scan)
    resource = next(
        (
            item for item in resources
            if item.kind == "SCNE"
            and item.outer_index == args.outer
            and item.chunk_index == args.chunk
        ),
        None,
    )
    if resource is None:
        raise ScneError(f"SCNE outer {args.outer}/chunk {args.chunk} is not in the inventory")
    archive = parse_archive(args.index)
    span = read_entry_range(
        archive, archive.entries[resource.outer_index], resource.chunk_offset,
        0x20 + resource.stored_size,
    )
    output, _ = decode_resource(span, resource)
    scene, _, _, _ = parse_scene(0, resource, output, {})
    if not 0 <= args.shape < len(scene["shapes"]):
        raise ScneError(f"shape must be between 0 and {len(scene['shapes']) - 1}")
    shape = scene["shapes"][args.shape]
    position = next(
        (item for item in shape["attribute_descriptors"] if item["register"] == 0),
        None,
    )
    if position is None or position["format_name"] != "FLOAT3":
        found = position["format_name"] if position else "missing"
        raise ScneError(
            f"PORTME: proof exporter requires register 0 FLOAT3; shape uses {found}. "
            "Compressed position bias/scale reconstruction remains an inference."
        )
    stream = next(
        item for item in shape["vertex_streams"]
        if item["stream_index"] == position["stream_index"]
    )
    vertex_count = int(shape["vertex_count"])
    positions: list[tuple[float, float, float]] = []
    for vertex in range(vertex_count):
        offset = (
            int(stream["offset"])
            + vertex * int(stream["stride"])
            + int(position["byte_offset"])
        )
        value = struct.unpack_from("<3f", output, offset)
        if not all(math.isfinite(component) for component in value):
            raise ScneError(f"non-finite FLOAT3 position at vertex {vertex}")
        positions.append(value)

    binary = bytearray()
    buffer_views: list[dict[str, object]] = []
    accessors: list[dict[str, object]] = []

    position_offset = len(binary)
    for value in positions:
        binary.extend(struct.pack("<3f", *value))
    buffer_views.append(
        {"buffer": 0, "byteOffset": position_offset, "byteLength": len(positions) * 12, "target": 34962}
    )
    accessors.append(
        {
            "bufferView": 0,
            "byteOffset": 0,
            "componentType": 5126,
            "count": vertex_count,
            "type": "VEC3",
            "min": [min(value[axis] for value in positions) for axis in range(3)],
            "max": [max(value[axis] for value in positions) for axis in range(3)],
        }
    )
    align4(binary)

    materials: list[dict[str, object]] = []
    material_map: dict[int, int] = {}
    primitives: list[dict[str, object]] = []
    topology_proof: list[dict[str, object]] = []
    selected_submeshes = [
        item for item in scene["submeshes"] if item["shape_index"] == args.shape
    ]
    for submesh in selected_submeshes:
        material_index = int(submesh["material_index"])
        if material_index not in material_map:
            material_map[material_index] = len(materials)
            materials.append(
                {
                    "name": str(submesh["material_name"] or f"material_{material_index}"),
                    "doubleSided": True,
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [0.8, 0.8, 0.8, 1.0],
                        "metallicFactor": 0.0,
                        "roughnessFactor": 1.0,
                    },
                    "extras": {"nfl2k5_material_table_index": material_index},
                }
            )
        for batch_index, (xbox_mode, raw_indices) in enumerate(
            decode_batches(
                output,
                int(submesh["command_offset"]),
                int(submesh["primary_command_word_count"]),
            )
        ):
            gltf_mode, indices, conversion = gltf_topology(xbox_mode, raw_indices)
            if not indices:
                continue
            if max(indices) >= vertex_count:
                raise ScneError("exported topology references a vertex outside the shape")
            align4(binary)
            index_offset = len(binary)
            binary.extend(struct.pack(f"<{len(indices)}H", *indices))
            buffer_view_index = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": index_offset,
                    "byteLength": len(indices) * 2,
                    "target": 34963,
                }
            )
            accessor_index = len(accessors)
            accessors.append(
                {
                    "bufferView": buffer_view_index,
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
                    "attributes": {"POSITION": 0},
                    "indices": accessor_index,
                    "material": material_map[material_index],
                    "mode": gltf_mode,
                    "extras": {
                        "nfl2k5_submesh_index": submesh["submesh_index"],
                        "nfl2k5_batch_index": batch_index,
                        "xbox_primitive_mode": xbox_mode,
                        "topology_conversion": conversion,
                    },
                }
            )
            topology_proof.append(
                {
                    "submesh_index": submesh["submesh_index"],
                    "batch_index": batch_index,
                    "xbox_mode": xbox_mode,
                    "raw_index_count": len(raw_indices),
                    "gltf_index_count": len(indices),
                    "conversion": conversion,
                    "maximum_index": max(indices),
                }
            )

    if not primitives:
        raise ScneError("selected shape produced no glTF primitives")
    align4(binary)
    bin_path = args.bin_path or args.output.with_suffix(".bin")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(binary)
    gltf = {
        "asset": {"version": "2.0", "generator": "nfl_scne_gltf.py"},
        "scene": 0,
        "scenes": [{"name": scene["name"], "nodes": [0]}],
        "nodes": [{"name": shape["name"], "mesh": 0}],
        "meshes": [
            {
                "name": shape["name"],
                "primitives": primitives,
                "extras": {
                    "nfl2k5_shape_index": args.shape,
                    "vertex_attribute_descriptors": shape["attribute_descriptors"],
                    "coordinate_system": "raw Xbox coordinates; no inferred axis conversion",
                },
            }
        ],
        "materials": materials,
        "buffers": [{"uri": bin_path.name, "byteLength": len(binary)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
        "extras": {
            "source": {
                "outer_index": args.outer,
                "chunk_index": args.chunk,
                "scene_name": scene["name"],
                "shape_index": args.shape,
                "shape_name": shape["name"],
            },
            "proof_scope": "register 0 FLOAT3 positions and decoded NV2A push topology",
            "topology": topology_proof,
            "portme": [
                "PORTME: map shader-specific Xbox input registers to glTF NORMAL/TEXCOORD/JOINTS/WEIGHTS semantics.",
                "PORTME: bind recovered embedded texture descriptors to glTF materials.",
                "PORTME: reconstruct transforms, hierarchy, morph channels, and skinning.",
            ],
        },
    }
    args.output.write_text(json.dumps(gltf, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(
        f"NFL2K5_GLTF_EXPORT_COMPLETE scene={scene['name']!r} shape={shape['name']!r} "
        f"vertices={vertex_count} primitives={len(primitives)} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ScneError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
