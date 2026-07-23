#!/usr/bin/env python3
"""Create a tiny redistributable glTF 2.0 skin/animation test fixture."""

from __future__ import annotations

import argparse
import base64
import json
import math
import struct
from pathlib import Path


def align4(data: bytearray) -> None:
    while len(data) & 3:
        data.append(0)


def append(data: bytearray, payload: bytes) -> tuple[int, int]:
    align4(data)
    offset = len(data)
    data.extend(payload)
    return offset, len(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    data = bytearray()
    views: list[dict[str, int]] = []

    def view(payload: bytes, target: int | None = None) -> int:
        offset, length = append(data, payload)
        row: dict[str, int] = {
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": length,
        }
        if target is not None:
            row["target"] = target
        views.append(row)
        return len(views) - 1

    positions = [(-0.6, -0.5, 0.0), (0.6, -0.5, 0.0), (0.0, 0.6, 0.0)]
    normals = [(0.0, 0.0, 1.0)] * 3
    joints = [(0, 0, 0, 0)] * 3
    weights = [(1.0, 0.0, 0.0, 0.0)] * 3
    indices = (0, 1, 2)
    identity = (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )
    times = (0.0, 1.0, 2.0)
    translations = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                    (0.0, 0.0, 0.0))

    position_view = view(b"".join(struct.pack("<3f", *v) for v in positions), 34962)
    normal_view = view(b"".join(struct.pack("<3f", *v) for v in normals), 34962)
    joint_view = view(b"".join(struct.pack("<4B", *v) for v in joints), 34962)
    weight_view = view(b"".join(struct.pack("<4f", *v) for v in weights), 34962)
    index_view = view(struct.pack("<3H", *indices), 34963)
    inverse_bind_view = view(struct.pack("<16f", *identity))
    time_view = view(struct.pack("<3f", *times))
    translation_view = view(
        b"".join(struct.pack("<3f", *v) for v in translations)
    )

    accessors = [
        {"bufferView": position_view, "componentType": 5126, "count": 3,
         "type": "VEC3", "min": [-0.6, -0.5, 0.0],
         "max": [0.6, 0.6, 0.0]},
        {"bufferView": normal_view, "componentType": 5126, "count": 3,
         "type": "VEC3"},
        {"bufferView": joint_view, "componentType": 5121, "count": 3,
         "type": "VEC4"},
        {"bufferView": weight_view, "componentType": 5126, "count": 3,
         "type": "VEC4"},
        {"bufferView": index_view, "componentType": 5123, "count": 3,
         "type": "SCALAR", "min": [0], "max": [2]},
        {"bufferView": inverse_bind_view, "componentType": 5126,
         "count": 1, "type": "MAT4"},
        {"bufferView": time_view, "componentType": 5126, "count": 3,
         "type": "SCALAR", "min": [0.0], "max": [2.0]},
        {"bufferView": translation_view, "componentType": 5126,
         "count": 3, "type": "VEC3"},
    ]

    encoded = base64.b64encode(data).decode("ascii")
    document = {
        "asset": {"version": "2.0", "generator": "vc-port deterministic test fixture"},
        "scene": 0,
        "scenes": [{"name": "animated_skin_fixture", "nodes": [0, 1]}],
        "nodes": [
            {"name": "mesh", "mesh": 0, "skin": 0},
            {"name": "joint"},
        ],
        "meshes": [{"name": "triangle", "primitives": [{
            "attributes": {
                "POSITION": 0,
                "NORMAL": 1,
                "JOINTS_0": 2,
                "WEIGHTS_0": 3,
            },
            "indices": 4,
            "mode": 4,
        }]}],
        "skins": [{"name": "one_joint_skin", "inverseBindMatrices": 5,
                   "skeleton": 1, "joints": [1]}],
        "animations": [{
            "name": "translate_joint",
            "samplers": [{"input": 6, "output": 7, "interpolation": "LINEAR"}],
            "channels": [{"sampler": 0, "target": {"node": 1,
                                                     "path": "translation"}}],
        }],
        "buffers": [{
            "byteLength": len(data),
            "uri": "data:application/octet-stream;base64," + encoded,
        }],
        "bufferViews": views,
        "accessors": accessors,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    decoded = json.loads(args.output.read_text(encoding="utf-8"))
    assert decoded["asset"]["version"] == "2.0"
    assert decoded["buffers"][0]["byteLength"] == len(data)
    assert math.isclose(translations[1][0], 1.0)
    print(f"ANIMATED_SKIN_FIXTURE_PASS bytes={len(data)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
