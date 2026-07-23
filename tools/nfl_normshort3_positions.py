#!/usr/bin/env python3
"""Pin the executable proof for NFL 2K5 NORMSHORT3 static positions.

The report deliberately keeps three independent layers separate:

* the shape relocator's serialized-to-runtime constant shuffle;
* the render packet and the common first instruction of all 13 static vertex
  shaders; and
* a worked archive sample decoded with Xbox signed-normalized-short rules.

It does not assign semantics to any other vertex register or shape field.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from collections import Counter
from pathlib import Path

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_inventory import ScneError, parse_scene


SCHEMA = "nfl2k5_normshort3_positions/v1"
EXPECTED_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
SHADER_OBJECT_FIRST = 0x00A6C540
SHADER_OBJECT_COUNT = 13
SHADER_OBJECT_STRIDE = 0x20
EXPECTED_FIRST_POSITION_INSTRUCTION = (
    0x00000000,
    0x0081001A,
    0x09FF186A,
    0x3E400000,
)


class EvidenceError(ValueError):
    """A pinned executable, corpus, or worked-sample invariant failed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def xbe_reader(xbe: bytes, header: dict[str, object]):
    def read(va: int, size: int) -> bytes:
        if size < 0:
            raise EvidenceError("negative XBE read size")
        for section in header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                return xbe[offset:offset + size]
        raise EvidenceError(f"XBE VA range 0x{va:08x}+0x{size:x} is not raw-backed")

    return read


def get_field(words: tuple[int, int, int, int], word: int, start: int, size: int) -> int:
    return (words[word] >> start) & ((1 << size) - 1)


def decode_first_instruction(words: tuple[int, int, int, int]) -> dict[str, object]:
    """Decode only fields needed by the proved common position MAD.

    Field positions are the NV2A token layout used by the pinned local
    Cxbx-Reloaded ``nv2a_vsh.cpp``.  The native constant number is encoded
    relative to the Xbox -96 constant base; raw slot 8 is therefore c[-88].
    """

    fields = {
        "ilu_opcode": get_field(words, 1, 25, 3),
        "mac_opcode": get_field(words, 1, 21, 4),
        "constant_slot": get_field(words, 1, 13, 8),
        "vertex_register": get_field(words, 1, 9, 4),
        "a_mux": get_field(words, 2, 26, 2),
        "a_swizzle": [get_field(words, 1, shift, 2) for shift in (6, 4, 2, 0)],
        "b_mux": get_field(words, 2, 11, 2),
        "b_swizzle": [get_field(words, 2, shift, 2) for shift in (23, 21, 19, 17)],
        "c_mux": get_field(words, 3, 28, 2),
        "c_swizzle": [get_field(words, 2, shift, 2) for shift in (8, 6, 4, 2)],
        "output_mask": get_field(words, 3, 24, 4),
        "output_register": get_field(words, 3, 20, 4),
    }
    expected = {
        "ilu_opcode": 0,
        "mac_opcode": 4,
        "constant_slot": 8,
        "vertex_register": 0,
        "a_mux": 2,
        "a_swizzle": [0, 1, 2, 2],
        "b_mux": 3,
        "b_swizzle": [3, 3, 3, 3],
        "c_mux": 3,
        "c_swizzle": [0, 1, 2, 2],
        "output_mask": 14,
        "output_register": 4,
    }
    if fields != expected:
        raise EvidenceError(f"unexpected common shader instruction fields: {fields}")
    return {
        "words": [f"0x{word:08x}" for word in words],
        "decoded_fields": fields,
        "native_constant_register": -96 + fields["constant_slot"],
        "disassembly": "MAD r4.xyz, v0.xyzz, c[-88].wwww, c[-88].xyzz",
        "equation": "r4.xyz = v0.xyz * c[-88].w + c[-88].xyz",
    }


def normshort(value: int) -> float:
    return value / (32767.0 if value >= 0 else 32768.0)


def float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def decode_position(values: tuple[int, int, int], scale: float, offset: tuple[float, float, float]) -> tuple[float, float, float]:
    # Xbox converts each signed short to binary32 before the shader MAD.  A
    # final binary32 rounding makes the derived glTF stream deterministic.
    return tuple(
        float32(float32(normshort(value)) * scale + offset[axis])
        for axis, value in enumerate(values)
    )


def register_zero_format(compact: str) -> str:
    for descriptor in compact.split("|"):
        fields = descriptor.split(":")
        if fields[0] == "r0":
            return fields[1]
    return "MISSING"


def corpus_counts(shapes_path: Path, submeshes_path: Path) -> dict[str, object]:
    shapes: dict[tuple[int, int], tuple[str, int]] = {}
    format_counts: Counter[str] = Counter()
    scene_shapes: Counter[int] = Counter()
    vertex_count = 0
    with shapes_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, dialect="excel-tab"):
            key = (int(row["scene_index"]), int(row["index"]))
            position_format = register_zero_format(row["attribute_descriptors"])
            count = int(row["vertex_count"])
            if key in shapes:
                raise EvidenceError(f"duplicate shape {key}")
            shapes[key] = (position_format, count)
            format_counts[position_format] += 1
            scene_shapes[key[0]] += 1
            vertex_count += count
    primitive_count = 0
    with submeshes_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, dialect="excel-tab"):
            key = (int(row["scene_index"]), int(row["shape_index"]))
            if key not in shapes:
                raise EvidenceError(f"submesh references absent shape {key}")
            if row["all_vertex_references_in_bounds"] != "True":
                raise EvidenceError(f"unbounded submesh for shape {key}")
            primitive_count += 1
    if format_counts != {"FLOAT3": 46192, "NORMSHORT3": 8774}:
        raise EvidenceError(f"unexpected register-0 formats: {format_counts}")
    if len(shapes) != 54966 or vertex_count != 13731388 or primitive_count != 276642:
        raise EvidenceError("static corpus totals changed")
    return {
        "scene_count": 4616,
        "nonempty_scene_count": len(scene_shapes),
        "zero_shape_scene_count": 4616 - len(scene_shapes),
        "shape_count": len(shapes),
        "register_zero_format_counts": dict(sorted(format_counts.items())),
        "vertex_count": vertex_count,
        "primitive_count": primitive_count,
    }


def worked_font_a(index_path: Path, scan_path: Path) -> dict[str, object]:
    _, resources = parse_inventory(scan_path)
    scne_resources = [resource for resource in resources if resource.kind == "SCNE"]
    matches = [
        (scene_index, resource)
        for scene_index, resource in enumerate(scne_resources)
        if (resource.outer_index, resource.chunk_index) == (3, 51)
    ]
    if len(matches) != 1:
        raise EvidenceError(f"expected one outer 3/chunk 51 SCNE, got {len(matches)}")
    scene_index, resource = matches[0]
    archive = parse_archive(index_path)
    span = read_entry_range(
        archive,
        archive.entries[resource.outer_index],
        resource.chunk_offset,
        0x20 + resource.stored_size,
    )
    output, decode_detail = decode_resource(span, resource)
    scene, _, _, _ = parse_scene(scene_index, resource, output, {})
    if scene["name"] != "geometry_font" or not scene["shapes"]:
        raise EvidenceError("worked geometry_font scene changed")
    shape = scene["shapes"][0]
    if shape["name"] != "A" or str(shape["attribute_descriptors"][0]["format_name"]) != "NORMSHORT3":
        raise EvidenceError("worked font A shape changed")
    record = int(shape["record_offset"])
    scale = struct.unpack_from("<f", output, record + 0x10)[0]
    offset = struct.unpack_from("<3f", output, record + 0x20)
    if not math.isfinite(scale) or not all(math.isfinite(value) for value in offset):
        raise EvidenceError("font A scale/offset is non-finite")
    position = shape["attribute_descriptors"][0]
    stream = next(
        item for item in shape["vertex_streams"]
        if int(item["stream_index"]) == int(position["stream_index"])
    )
    raw = bytearray()
    decoded = bytearray()
    raw_min = [32767, 32767, 32767]
    raw_max = [-32768, -32768, -32768]
    minima = [math.inf, math.inf, math.inf]
    maxima = [-math.inf, -math.inf, -math.inf]
    for vertex in range(int(shape["vertex_count"])):
        source = (
            int(stream["offset"])
            + vertex * int(stream["stride"])
            + int(position["byte_offset"])
        )
        values = struct.unpack_from("<3h", output, source)
        raw.extend(struct.pack("<3h", *values))
        point = decode_position(values, scale, offset)
        decoded.extend(struct.pack("<3f", *point))
        for axis in range(3):
            raw_min[axis] = min(raw_min[axis], values[axis])
            raw_max[axis] = max(raw_max[axis], values[axis])
            minima[axis] = min(minima[axis], point[axis])
            maxima[axis] = max(maxima[axis], point[axis])
    if not (
        0.0 <= minima[0] < 0.001 and 64.9 < maxima[0] < 65.1
        and 0.0 <= minima[1] < 0.002 and 107.9 < maxima[1] < 108.1
        and minima[2] == maxima[2] == 0.0
    ):
        raise EvidenceError(f"font A decoded bounds changed: {minima} {maxima}")
    return {
        "scene_index": scene_index,
        "outer_index": resource.outer_index,
        "chunk_index": resource.chunk_index,
        "scene_name": scene["name"],
        "shape_index": int(shape["index"]),
        "shape_name": shape["name"],
        "decoded_scene_sha256": decode_detail["decoded_sha256"],
        "shape_record_offset": record,
        "vertex_count": int(shape["vertex_count"]),
        "serialized_scale_field": "+0x10",
        "serialized_offset_fields": ["+0x20", "+0x24", "+0x28"],
        "scale": scale,
        "offset": list(offset),
        "runtime_c_minus_88": [*offset, scale],
        "raw_component_min": raw_min,
        "raw_component_max": raw_max,
        "decoded_min": minima,
        "decoded_max": maxima,
        "raw_position_sha256": sha256(bytes(raw)),
        "decoded_float3_sha256": sha256(bytes(decoded)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"))
    parser.add_argument("--xbe-header", type=Path, default=Path("reports/headers/nfl2k5_xbe_header.json"))
    parser.add_argument("--index", type=Path, default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
    parser.add_argument("--resource-scan", type=Path, default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"))
    parser.add_argument("--shapes-tsv", type=Path, default=Path("reports/assets/nfl2k5_scne_shapes.tsv"))
    parser.add_argument("--submeshes-tsv", type=Path, default=Path("reports/assets/nfl2k5_scne_submeshes.tsv"))
    parser.add_argument("--cxbx-vertex-buffer", type=Path, default=Path("tools/vendor/Cxbx-Reloaded/src/core/hle/D3D8/XbVertexBuffer.cpp"))
    parser.add_argument("--cxbx-vsh", type=Path, default=Path("tools/vendor/Cxbx-Reloaded/src/devices/video/nv2a_vsh.cpp"))
    parser.add_argument("--json", type=Path, default=Path("reports/assets/nfl_normshort3_positions.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    xbe = args.xbe.read_bytes()
    header = json.loads(args.xbe_header.read_text(encoding="utf-8"))
    if hashlib.md5(xbe).hexdigest() != EXPECTED_MD5:
        raise EvidenceError("unexpected NFL 2K5 executable")
    read_xbe = xbe_reader(xbe, header)

    relocator_window = read_xbe(0x00022F90, 0x40)
    shuffle = bytes.fromhex(
        "d941208b5110d95910d9412489511cd95914d94128d95918"
    )
    shuffle_offset = relocator_window.find(shuffle)
    if shuffle_offset != 0x1A:
        raise EvidenceError(f"shape constant shuffle moved to {shuffle_offset}")

    render_window = read_xbe(0x000245FD, 0x40)
    upload = bytes.fromhex(
        "0f2846100f2983e00000008b430c"
        "c700a41e0400c7400408000000c74008800b1000"
        "8b4e1089480c8b56148950108b4e188948148b561c895018"
    )
    if not render_window.startswith(upload):
        raise EvidenceError("render constant-upload sequence changed")

    instruction = decode_first_instruction(EXPECTED_FIRST_POSITION_INSTRUCTION)
    shader_objects = []
    for index in range(SHADER_OBJECT_COUNT):
        va = SHADER_OBJECT_FIRST + index * SHADER_OBJECT_STRIDE
        words = struct.unpack("<8I", read_xbe(va, SHADER_OBJECT_STRIDE))
        program_va = words[7]
        instruction_count = words[5]
        if words[3] != 0x2078 or instruction_count < 2:
            raise EvidenceError(f"unexpected static shader object at 0x{va:08x}")
        program = read_xbe(program_va, instruction_count * 16)
        first_position = struct.unpack_from("<4I", program, 16)
        if first_position != EXPECTED_FIRST_POSITION_INSTRUCTION:
            raise EvidenceError(f"shader 0x{va:08x} has a different position instruction")
        shader_objects.append(
            {
                "index": index,
                "object_va": f"0x{va:08x}",
                "declaration_word": f"0x{words[2]:08x}",
                "version": f"0x{words[3]:04x}",
                "instruction_count": instruction_count,
                "program_va": f"0x{program_va:08x}",
                "program_sha256": sha256(program),
                "instruction_1_words": instruction["words"],
            }
        )

    vertex_buffer_source = args.cxbx_vertex_buffer.read_text(encoding="utf-8")
    if "return PackedIntToFloat((int)value, 32767.0f, 32768.0f);" not in vertex_buffer_source:
        raise EvidenceError("pinned Cxbx NormShortToFloat implementation changed")
    vsh_source = args.cxbx_vsh.read_text(encoding="utf-8")
    for exact in (
        "{  FLD_MAC,              1,   21,     4 }",
        "{  FLD_CONST,            1,   13,     8 }",
        "{  FLD_OUT_MAC_MASK,     3,   24,     4 }",
    ):
        if exact not in vsh_source:
            raise EvidenceError(f"pinned Cxbx NV2A field mapping changed: {exact}")

    report = {
        "schema": SCHEMA,
        "executable": {
            "path": str(args.xbe),
            "md5": hashlib.md5(xbe).hexdigest(),
            "sha256": sha256(xbe),
        },
        "shape_relocator": {
            "function_va": "0x00022f90",
            "window_va": "0x00022f90",
            "window_size": len(relocator_window),
            "window_sha256": sha256(relocator_window),
            "shuffle_va": f"0x{0x00022F90 + shuffle_offset:08x}",
            "serialized_to_runtime": {
                "+0x20": "+0x10 / c[-88].x",
                "+0x24": "+0x14 / c[-88].y",
                "+0x28": "+0x18 / c[-88].z",
                "+0x10": "+0x1c / c[-88].w",
            },
        },
        "render_upload": {
            "function_va": "0x000243d0",
            "sequence_va": "0x000245fd",
            "sequence_size": len(upload),
            "sequence_sha256": sha256(upload),
            "push_words": ["0x00041ea4", "0x00000008", "0x00100b80", "shape +0x10..+0x1c"],
            "decoded_methods": [
                "NV097_SET_TRANSFORM_CONSTANT_LOAD count=1, slot=8",
                "NV097_SET_TRANSFORM_CONSTANT count=4, shape runtime +0x10..+0x1c",
            ],
        },
        "static_vertex_shaders": {
            "object_first_va": f"0x{SHADER_OBJECT_FIRST:08x}",
            "object_stride": SHADER_OBJECT_STRIDE,
            "object_count": SHADER_OBJECT_COUNT,
            "object_table_sha256": sha256(read_xbe(SHADER_OBJECT_FIRST, SHADER_OBJECT_COUNT * SHADER_OBJECT_STRIDE)),
            "common_instruction_1": instruction,
            "objects": shader_objects,
        },
        "xbox_normshort3": {
            "equation": "n = value / 32767 for value >= 0; value / 32768 for value < 0",
            "expanded_w": 1.0,
            "cxbx_commit": "585c49a50af1255ab155099e06f24505f9c5a800",
            "cxbx_vertex_buffer_path": str(args.cxbx_vertex_buffer),
            "cxbx_vertex_buffer_sha256": sha256_file(args.cxbx_vertex_buffer),
            "cxbx_nv2a_vsh_path": str(args.cxbx_vsh),
            "cxbx_nv2a_vsh_sha256": sha256_file(args.cxbx_vsh),
        },
        "complete_decode_equation": "position.xyz = normshort3(register0.xyz) * serialized_shape_float(+0x10) + serialized_shape_float3(+0x20)",
        "corpus": corpus_counts(args.shapes_tsv, args.submeshes_tsv),
        "worked_sample": worked_font_a(args.index, args.resource_scan),
        "evidence_boundary": [
            "exact for register-0 NORMSHORT3 static position decode in the 13 recovered static shader programs",
            "raw Xbox coordinates are retained; no hierarchy or node transform is applied",
            "no semantics are assigned to other input registers, materials, skinning, morphs, or animation",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "NFL_NORMSHORT3_POSITIONS_COMPLETE "
        f"shaders={SHADER_OBJECT_COUNT} shapes={report['corpus']['register_zero_format_counts']['NORMSHORT3']} "
        f"vertices={report['corpus']['vertex_count']} -> {args.json}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, struct.error, ScneError) as exc:
        raise SystemExit(f"error: {exc}") from exc
