#!/usr/bin/env python3
"""Generate the retail-free bounded Crib position-lane catalog.

This research/build helper reads the user's private indexed source and the
existing static glTF export.  Its output contains only layout identities,
hashes, and proved decode metadata; it never serializes source vertex bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from mod_editor.core.nfl2k5_crib_scene_texture_writer import _Resolver
from mod_editor.core import nfl2k5_stadium_texture_writer as stadium
from nfl_scne_inventory import parse_scene


SCHEMA = "nfl2k5_crib_static_position_targets/v1"
DEFAULT_OWNERSHIP = ROOT / "reports/experiments/nfl2k5_crib_electronics_ownership.json"
DEFAULT_MODELS = ROOT / "assets/intermediate/nfl2k5/models"
DEFAULT_OUTPUT = ROOT / "reports/specs/nfl2k5_crib_static_position_targets.v1.json"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _topology_hash(document: dict, buffers: tuple[bytes, ...], mesh: dict) -> str:
    triangles = stadium._mesh_triangles(document, buffers, mesh)
    return _sha(stadium._canonical_json(
        sorted((list(key), count) for key, count in triangles.items())
    ))


def build(index: Path, inventory: Path, ownership: Path, models: Path) -> dict:
    report = json.loads(ownership.read_text(encoding="utf-8"))
    selected: dict[tuple[str, int, int, str], set[str]] = {}
    for texture in report["textures"]:
        for consumer in texture["consumers"]:
            key = (
                str(texture["scene_name"]), int(texture["chunk_index"]),
                int(consumer["shape_index"]), str(consumer["shape_name"]),
            )
            selected.setdefault(key, set()).add(str(texture["selector"]))

    resolver = _Resolver(index, inventory)
    rows = []
    for (scene_name, chunk_index, shape_index, shape_name), selectors in sorted(selected.items()):
        resolved = resolver.resolve_many([sorted(selectors)[0]])[0]
        scene, _names, _mappings, _sample = parse_scene(
            resolved.contract.scene_index, resolved.resource, resolved.decoded, {}
        )
        shape = next(row for row in scene["shapes"] if int(row["index"]) == shape_index)
        if shape["name"] != shape_name:
            raise ValueError(f"shape name changed for {scene_name}:{shape_index}")
        position = next(
            row for row in shape["attribute_descriptors"] if int(row["register"]) == 0
        )
        format_name = str(position["format_name"])
        if format_name not in {"FLOAT3", "NORMSHORT3"}:
            raise ValueError(f"unsupported position format {format_name}")
        stream = next(
            row for row in shape["vertex_streams"]
            if int(row["stream_index"]) == int(position["stream_index"])
        )
        component_size = int(position["byte_size"])
        vertex_count = int(shape["vertex_count"])
        stream_offset = int(stream["offset"])
        stride = int(stream["stride"])
        byte_offset = int(position["byte_offset"])
        lane = b"".join(
            resolved.decoded[
                stream_offset + vertex * stride + byte_offset:
                stream_offset + vertex * stride + byte_offset + component_size
            ]
            for vertex in range(vertex_count)
        )

        gltf_path = models / f"4248_{chunk_index:04d}_{scene_name}.gltf"
        source_document, source_buffers = stadium._read_gltf_bundle(gltf_path)
        mesh = stadium._mesh_by_shape(source_document, shape_index, shape_name)
        gltf_positions = stadium._mesh_positions(source_document, source_buffers, mesh)
        position_bytes = b"".join(struct.pack("<3f", *xyz) for xyz in gltf_positions)
        decode: dict[str, object] = {"format": format_name}
        if format_name == "NORMSHORT3":
            record_offset = int(shape["record_offset"])
            decode.update({
                "scale": struct.unpack_from("<f", resolved.decoded, record_offset + 0x10)[0],
                "offset": list(struct.unpack_from("<3f", resolved.decoded, record_offset + 0x20)),
                "shape_decode_fields_sha256": _sha(
                    resolved.decoded[record_offset + 0x10:record_offset + 0x14]
                    + resolved.decoded[record_offset + 0x20:record_offset + 0x2C]
                ),
            })
        scene_id = (
            f"nfl2k5.crib.o4248.c{chunk_index:04d}."
            f"scene{resolved.contract.scene_index:04d}"
        )
        rows.append({
            "decode": decode,
            "eligibility": {
                "same_count_position_only": True,
                "source_topology_required": True,
            },
            "position": {
                "byte_offset": byte_offset,
                "component_size": component_size,
                "source_lane_sha256": _sha(lane),
                "source_gltf_float3_sha256": _sha(position_bytes),
                "stream_offset": stream_offset,
                "stride": stride,
            },
            "scene_id": scene_id,
            "shape": {
                "index": shape_index,
                "name": shape_name,
                "vertex_count": vertex_count,
            },
            "source_identity": {
                "outer_index": 4248,
                "chunk_index": chunk_index,
                "scene_index": resolved.contract.scene_index,
                "scene_name": scene_name,
                "decoded_sha256": resolved.contract.decoded_sha256,
            },
            "target_id": f"{scene_id}.shape{shape_index:04d}",
            "texture_selectors": sorted(selectors),
            "topology_sha256": _topology_hash(source_document, source_buffers, mesh),
        })
    return {
        "claims": {
            "contains_retail_bytes": False,
            "position_formats": ["FLOAT3", "NORMSHORT3"],
            "source_topology_uv_material_collision_preserved": True,
        },
        "schema": SCHEMA,
        "targets": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--ownership", type=Path, default=DEFAULT_OWNERSHIP)
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = _canonical(build(args.index, args.inventory, args.ownership, args.models))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"CRIB_POSITION_CATALOG_PASS targets=10 sha256={_sha(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
