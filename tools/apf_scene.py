#!/usr/bin/env python3
"""Inventory and conservatively decode APF 2K8 SCNE scene/model resources.

This parser proves the SCNE envelope, scene-node, matrix, hierarchy,
vertex-declaration, stream, and index relationships that are internally
self-consistent. It can emit a strict single-mesh proof or static multi-mesh
glTF 2.0 collections when POSITION and topology semantics pass every check;
unsupported layouts remain explicit PORTME records rather than guessed mesh
data.
"""

from __future__ import annotations

import argparse
from array import array
import base64
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable
import zlib

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner
import apf_outer


SCENE_HEADER_MIN = 0x64
SCENE_NODE_SIZE = 0xB0
MATRIX_SIZE = 0x40
JOINT_TABLE_HEADER_SIZE = 0x20
JOINT_RECORD_SIZE = 0x30
DRAW_RECORD_SIZE = 0x30
DECLARATION_RECORD_SIZE = 0x40
STREAM_RECORD_SIZE = 0x18
MAX_REASONABLE_COUNT = 1_000_000

POSITION0_HASH = zlib.crc32(b"POSITION0") & 0xFFFFFFFF
POSITION_HASH = zlib.crc32(b"POSITION") & 0xFFFFFFFF

FORMAT_NAMES = {
    0x002A2187: "snorm10_10_10",
    0x001A2286: "uint8x4",
    0x001A2086: "unorm8x4",
    0x00182886: "packed_color_84b8be00_helper",
    0x001A205A: "unorm16x4",
    0x001A215A: "snorm16x4",
    0x001A235A: "sint16x4",
    0x001A2360: "float16x4",
    0x001A23A6: "float32x4",
    0x002A2287: "uint10_10_10",
    0x002A23B9: "float32x3",
    0x002C2059: "unorm16x2",
    0x002C2159: "snorm16x2",
    0x002C2359: "sint16x2",
    0x002C235F: "float16x2",
    0x002C23A5: "float32x2",
    0x002C83A4: "float32",
}

FORMAT_SIZES = {
    0x002A2187: 4,
    0x001A2286: 4,
    0x001A2086: 4,
    0x00182886: 4,
    0x001A205A: 8,
    0x001A215A: 8,
    0x001A235A: 8,
    0x001A2360: 8,
    0x001A23A6: 16,
    0x002A2287: 4,
    0x002A23B9: 12,
    0x002C2059: 4,
    0x002C2159: 4,
    0x002C2359: 4,
    0x002C235F: 4,
    0x002C23A5: 8,
    0x002C83A4: 4,
}

SEMANTIC_LABELS = {
    zlib.crc32(label.encode("ascii")) & 0xFFFFFFFF: label
    for label in (
        "POSITION",
        "POSITION0",
        "NORMAL",
        "NORMAL0",
        "TANGENT",
        "TANGENT0",
        "BINORMAL",
        "BINORMAL0",
        "COLOR",
        "COLOR0",
        "COLOR1",
        "TEXCOORD",
        "TEXCOORD0",
        "TEXCOORD1",
        "TEXCOORD2",
        "BLENDINDICES",
        "BLENDINDICES0",
        "BLENDWEIGHT",
        "BLENDWEIGHT0",
    )
}
for _semantic_base in (
    "POSITION",
    "NORMAL",
    "TANGENT",
    "BINORMAL",
    "COLOR",
    "TEXCOORD",
    "BLENDINDICES",
    "BLENDWEIGHT",
):
    for _semantic_index in range(16):
        _label = f"{_semantic_base}{_semantic_index}"
        SEMANTIC_LABELS[zlib.crc32(_label.encode("ascii")) & 0xFFFFFFFF] = _label


class SceneError(ValueError):
    """A bounded SCNE relationship failed validation."""


def _u16be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise SceneError(f"{what}: u16 at 0x{offset:x} is out of bounds")
    return struct.unpack_from(">H", data, offset)[0]


def _i16be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise SceneError(f"{what}: i16 at 0x{offset:x} is out of bounds")
    return struct.unpack_from(">h", data, offset)[0]


def _u32be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise SceneError(f"{what}: u32 at 0x{offset:x} is out of bounds")
    return struct.unpack_from(">I", data, offset)[0]


def _f32be(data: bytes, offset: int, what: str) -> float:
    if offset < 0 or offset + 4 > len(data):
        raise SceneError(f"{what}: f32 at 0x{offset:x} is out of bounds")
    value = struct.unpack_from(">f", data, offset)[0]
    if not math.isfinite(value):
        raise SceneError(f"{what}: non-finite f32 at 0x{offset:x}")
    return value


def _hex(value: int) -> str:
    return f"0x{value:08x}"


def _relative_target(data: bytes, field_offset: int, what: str) -> int:
    raw = _u32be(data, field_offset, what)
    if raw == 0:
        raise SceneError(f"{what}: null relative pointer at 0x{field_offset:x}")
    target = field_offset + raw - 1
    if target < 0 or target >= len(data):
        raise SceneError(
            f"{what}: relative pointer 0x{raw:x} at 0x{field_offset:x} "
            f"resolves outside 0x{len(data):x} bytes"
        )
    return target


def _utf16be_z(data: bytes, offset: int, what: str, limit: int = 2048) -> str:
    chars: list[str] = []
    cursor = offset
    for _ in range(limit):
        value = _u16be(data, cursor, what)
        cursor += 2
        if value == 0:
            return "".join(chars)
        if 0xD800 <= value <= 0xDFFF:
            raise SceneError(f"{what}: unsupported surrogate at 0x{cursor - 2:x}")
        chars.append(chr(value))
    raise SceneError(f"{what}: UTF-16BE string exceeds {limit} code units")


def _named_pointer(data: bytes, field_offset: int, hash_offset: int, what: str) -> tuple[str, int]:
    target = _relative_target(data, field_offset, f"{what} name")
    name = _utf16be_z(data, target, f"{what} name")
    try:
        expected = zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF
    except UnicodeEncodeError as exc:
        raise SceneError(f"{what}: non-ASCII name {name!r} cannot validate CRC32") from exc
    actual = _u32be(data, hash_offset, f"{what} name hash")
    if actual != expected:
        raise SceneError(
            f"{what}: CRC32(name) {_hex(expected)} != stored {_hex(actual)}"
        )
    return name, target


def _bounded_array(
    data: bytes,
    count: int,
    pointer_field: int,
    stride: int,
    what: str,
) -> int | None:
    if count < 0 or count > MAX_REASONABLE_COUNT:
        raise SceneError(f"{what}: implausible count {count}")
    if count == 0:
        return None
    start = _relative_target(data, pointer_field, f"{what} table")
    if start + count * stride > len(data):
        raise SceneError(
            f"{what}: 0x{start:x} + {count} * 0x{stride:x} exceeds "
            f"0x{len(data):x} bytes"
        )
    return start


def _decode_snorm(value: int, bits: int) -> float:
    sign = 1 << (bits - 1)
    if value & sign:
        value -= 1 << bits
    minimum = -((1 << (bits - 1)) - 1)
    return max(value, minimum) / float((1 << (bits - 1)) - 1)


def _decode_position(data: bytes, offset: int, format_code: int) -> tuple[float, float, float]:
    if format_code == 0x002A2187:
        packed = _u32be(data, offset, "packed POSITION")
        return tuple(
            _decode_snorm((packed >> shift) & 0x3FF, 10)
            for shift in (0, 10, 20)
        )  # type: ignore[return-value]
    if format_code == 0x001A215A:
        return tuple(
            _decode_snorm(_u16be(data, offset + component * 2, "packed POSITION"), 16)
            for component in range(3)
        )  # type: ignore[return-value]
    if format_code == 0x002A23B9:
        values = struct.unpack_from(">3f", data, offset)
        if not all(math.isfinite(value) for value in values):
            raise SceneError("float32x3 POSITION contains a non-finite value")
        return values
    raise SceneError(
        f"PORTME: POSITION format {_hex(format_code)} is not decoded"
    )


def _parse_hierarchy_table(data: bytes, count: int, pointer_field: int, what: str) -> dict[str, object] | None:
    if count == 0:
        return None
    table = _relative_target(data, pointer_field, f"{what} hierarchy")
    records = table + JOINT_TABLE_HEADER_SIZE
    # The serializer omits the two float4 payloads from the terminal record.
    # This is exact in the one-record glowball table and in the 5/61-record
    # popup/face tables: 0x20 + (count - 1) * 0x30 + 0x10 bytes.
    table_length = JOINT_TABLE_HEADER_SIZE + (count - 1) * JOINT_RECORD_SIZE + 0x10
    if table + table_length > len(data):
        raise SceneError(f"{what}: hierarchy table exceeds SCNE system part")

    hierarchy_records: list[dict[str, object]] = []
    for index in range(count):
        offset = records + index * JOINT_RECORD_SIZE
        name, name_offset = _named_pointer(
            data, offset, offset + 4, f"{what} hierarchy record {index}"
        )
        parent = _i16be(data, offset + 8, "hierarchy parent")
        first_child = _i16be(data, offset + 10, "hierarchy first child")
        next_sibling = _i16be(data, offset + 12, "hierarchy next sibling")
        reserved = _u16be(data, offset + 14, "hierarchy reserved")
        for label, value in (
            ("parent", parent),
            ("first_child", first_child),
            ("next_sibling", next_sibling),
        ):
            if value != -1 and not 0 <= value < count:
                raise SceneError(
                    f"{what} hierarchy record {index}: {label} index {value} outside {count} records"
                )
        vector_a = None
        vector_b = None
        if index + 1 < count:
            vector_a = tuple(_f32be(data, offset + 0x10 + i * 4, "hierarchy vector A") for i in range(4))
            vector_b = tuple(_f32be(data, offset + 0x20 + i * 4, "hierarchy vector B") for i in range(4))
        hierarchy_records.append(
            {
                "index": index,
                "offset": offset,
                "name": name,
                "name_offset": name_offset,
                "name_crc32": _hex(_u32be(data, offset + 4, "hierarchy name hash")),
                "parent": parent,
                "first_child": first_child,
                "next_sibling": next_sibling,
                "reserved_u16": reserved,
                "vector_a": vector_a,
                "vector_b": vector_b,
            }
        )

    # Prove that the explicit child/sibling chains enumerate the same parent
    # relation.  This is what makes the three signed indices semantic rather
    # than merely plausible small integers.
    expected_children: dict[int, list[int]] = {}
    for record in hierarchy_records:
        parent = int(record["parent"])
        if parent >= 0:
            expected_children.setdefault(parent, []).append(int(record["index"]))
    topology_warnings: list[str] = []
    for parent_index, parent in enumerate(hierarchy_records):
        chain: list[int] = []
        cursor = int(parent["first_child"])
        seen: set[int] = set()
        while cursor != -1:
            if cursor in seen:
                topology_warnings.append(
                    f"PORTME: sibling cycle at record {cursor} while walking parent {parent_index}"
                )
                break
            seen.add(cursor)
            chain.append(cursor)
            cursor = int(hierarchy_records[cursor]["next_sibling"])
        if set(chain) != set(expected_children.get(parent_index, [])):
            topology_warnings.append(
                f"PORTME: child/sibling chain for record {parent_index} disagrees with parent indices"
            )

    return {
        "offset": table,
        "byte_length": table_length,
        "record_offset": records,
        "count": count,
        "header_words": [
            _hex(_u32be(data, table + i * 4, "hierarchy header"))
            for i in range(JOINT_TABLE_HEADER_SIZE // 4)
        ],
        "topology_status": "validated" if not topology_warnings else "variant",
        "topology_warnings": topology_warnings,
        "records": hierarchy_records,
    }


def _parse_declarations(data: bytes, node_offset: int, what: str) -> list[dict[str, object]]:
    count = _u32be(data, node_offset + 0x98, "vertex declaration count")
    start = _bounded_array(
        data, count, node_offset + 0x9C, DECLARATION_RECORD_SIZE, "vertex declarations"
    )
    if start is None:
        return []
    declarations: list[dict[str, object]] = []
    for index in range(count):
        offset = start + index * DECLARATION_RECORD_SIZE
        indexed_hash = _u32be(data, offset, "semantic indexed hash")
        semantic_hash = _u32be(data, offset + 4, "semantic hash")
        layout = _u32be(data, offset + 8, "semantic layout")
        format_code = _u32be(data, offset + 0xC, "semantic format")
        declarations.append(
            {
                "index": index,
                "offset": offset,
                "indexed_semantic_hash": _hex(indexed_hash),
                "indexed_semantic": SEMANTIC_LABELS.get(indexed_hash),
                "semantic_hash": _hex(semantic_hash),
                "semantic": SEMANTIC_LABELS.get(semantic_hash),
                "layout_word": _hex(layout),
                "stream_index": (layout >> 8) & 0xFF,
                "byte_offset": (layout >> 16) & 0xFF,
                "format_code": _hex(format_code),
                "format_name": FORMAT_NAMES.get(format_code),
                "vector_10": tuple(_f32be(data, offset + 0x10 + i * 4, "declaration vector 10") for i in range(4)),
                "vector_20": tuple(_f32be(data, offset + 0x20 + i * 4, "declaration vector 20") for i in range(4)),
                "vector_30": tuple(_f32be(data, offset + 0x30 + i * 4, "declaration vector 30") for i in range(4)),
            }
        )
    return declarations


def _parse_mesh_descriptor(
    data: bytes,
    descriptor: int,
    declarations: list[dict[str, object]],
    what: str,
    capture_geometry: bool,
) -> dict[str, object]:
    if descriptor + 0x14 > len(data):
        raise SceneError(f"{what}: mesh descriptor is truncated")
    vertex_count = _u32be(data, descriptor + 8, "vertex count")
    packed_stream_count = _u32be(data, descriptor + 0xC, "stream count word")
    stream_count = (packed_stream_count >> 16) & 0xFFFF
    primitive_type = _u32be(data, descriptor + 0x10, "primitive type")
    if vertex_count > MAX_REASONABLE_COUNT or not 1 <= stream_count <= 16:
        raise SceneError(
            f"{what}: implausible vertex/stream counts {vertex_count}/{stream_count}"
        )
    if descriptor + 0x14 + stream_count * STREAM_RECORD_SIZE > len(data):
        raise SceneError(f"{what}: stream descriptors are truncated")

    streams: list[dict[str, object]] = []
    stream_payloads: list[bytes] = []
    for index in range(stream_count):
        offset = descriptor + 0x14 + index * STREAM_RECORD_SIZE
        flags = _u32be(data, offset, "stream flags")
        enabled = _u32be(data, offset + 4, "stream enabled")
        stride = _u32be(data, offset + 8, "stream stride")
        byte_length = _u32be(data, offset + 0xC, "stream byte length")
        start = _relative_target(data, offset + 0x10, f"{what} stream {index} start")
        end = _relative_target(data, offset + 0x14, f"{what} stream {index} end")
        if end < start or end - start != byte_length:
            raise SceneError(
                f"{what} stream {index}: pointer span 0x{end - start:x} != "
                f"declared 0x{byte_length:x}"
            )
        if end > len(data):
            raise SceneError(f"{what} stream {index}: end exceeds SCNE system part")
        if stride == 0 or byte_length != vertex_count * stride:
            raise SceneError(
                f"{what} stream {index}: 0x{byte_length:x} bytes != "
                f"{vertex_count} * stride 0x{stride:x}"
            )
        payload = data[start:end]
        stream_payloads.append(payload)
        streams.append(
            {
                "index": index,
                "record_offset": offset,
                "flags": _hex(flags),
                "enabled": enabled,
                "stride": stride,
                "byte_length": byte_length,
                "start": start,
                "end": end,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    position_decl = next(
        (
            declaration
            for declaration in declarations
            if declaration["indexed_semantic_hash"] == _hex(POSITION0_HASH)
            and declaration["semantic_hash"] == _hex(POSITION_HASH)
        ),
        None,
    )
    position_result: dict[str, object] | None = None
    geometry: dict[str, object] | None = None
    if position_decl is not None:
        stream_index = int(position_decl["stream_index"])
        byte_offset = int(position_decl["byte_offset"])
        format_code = int(str(position_decl["format_code"]), 16)
        if stream_index >= len(streams):
            raise SceneError(f"{what}: POSITION refers to missing stream {stream_index}")
        format_size = FORMAT_SIZES.get(format_code)
        if format_size is None:
            position_result = {
                "status": "PORTME",
                "error": f"POSITION format {_hex(format_code)} has no byte-size mapping",
            }
        elif byte_offset + format_size > int(streams[stream_index]["stride"]):
            raise SceneError(f"{what}: POSITION exceeds its stream stride")
        else:
            center = tuple(float(v) for v in position_decl["vector_10"][:3])
            scale = tuple(float(v) for v in position_decl["vector_20"][:3])
            payload = stream_payloads[stream_index]
            stride = int(streams[stream_index]["stride"])
            positions: list[tuple[float, float, float]] = []
            for vertex in range(vertex_count):
                raw = _decode_position(
                    payload, vertex * stride + byte_offset, format_code
                )
                if format_code in (0x002A2187, 0x001A215A):
                    decoded = tuple(center[i] + raw[i] * scale[i] for i in range(3))
                else:
                    decoded = raw
                if not all(math.isfinite(value) for value in decoded):
                    raise SceneError(f"{what}: decoded POSITION {vertex} is non-finite")
                positions.append(decoded)
            minima = tuple(min(position[i] for position in positions) for i in range(3)) if positions else (0.0, 0.0, 0.0)
            maxima = tuple(max(position[i] for position in positions) for i in range(3)) if positions else (0.0, 0.0, 0.0)
            position_result = {
                "status": "decoded",
                "format": FORMAT_NAMES.get(format_code, _hex(format_code)),
                "stream_index": stream_index,
                "byte_offset": byte_offset,
                "center": center,
                "scale": scale,
                "minimum": minima,
                "maximum": maxima,
            }
            if capture_geometry:
                geometry = {"positions": positions}

    result: dict[str, object] = {
        "offset": descriptor,
        "optional_pointer_raw": _hex(_u32be(data, descriptor + 4, "optional mesh pointer")),
        "vertex_count": vertex_count,
        "packed_stream_count": _hex(packed_stream_count),
        "stream_count": stream_count,
        "primitive_type": primitive_type,
        "streams": streams,
        "position": position_result,
    }
    if geometry is not None:
        result["_geometry"] = geometry
    return result


def parse_scene_system_part(
    data: bytes,
    *,
    outer_index: int,
    inner_index: int,
    capture_geometry: bool = False,
) -> dict[str, object]:
    what = f"outer {outer_index} inner {inner_index}"
    if len(data) < SCENE_HEADER_MIN:
        raise SceneError(f"{what}: SCNE system part is only 0x{len(data):x} bytes")
    root_offset = _relative_target(data, 0, f"{what} root name")
    root_name = _utf16be_z(data, root_offset, f"{what} root name")

    matrix_count = _u32be(data, 0x3C, "matrix count")
    matrix_start = _bounded_array(data, matrix_count, 0x40, MATRIX_SIZE, "matrix")
    matrix_sha256 = None
    matrix_nonfinite_offsets: list[int] = []
    if matrix_start is not None:
        matrix_payload = data[matrix_start : matrix_start + matrix_count * MATRIX_SIZE]
        # Most records are finite 4x4 float matrices.  A bounded set of stadium,
        # sideline and UI variants contains NaN/Inf bit patterns; retain those
        # offsets as PORTME evidence instead of rejecting the entire SCNE.
        for i in range(matrix_count * 16):
            value = struct.unpack_from(">f", matrix_payload, i * 4)[0]
            if not math.isfinite(value):
                matrix_nonfinite_offsets.append(matrix_start + i * 4)
        matrix_sha256 = hashlib.sha256(matrix_payload).hexdigest()

    node_count = _u32be(data, 0x44, "scene-node count")
    node_start = _bounded_array(
        data, node_count, 0x48, SCENE_NODE_SIZE, "scene node"
    )
    nodes: list[dict[str, object]] = []
    position_format_counts: Counter[str] = Counter()
    semantic_counts: Counter[str] = Counter()
    portme: list[str] = []
    if matrix_nonfinite_offsets:
        portme.append(
            f"PORTME: {len(matrix_nonfinite_offsets)} non-finite component(s) in the "
            "0x40-byte matrix-like table; determine sentinel/variant semantics"
        )
    if node_start is not None:
        for node_index in range(node_count):
            offset = node_start + node_index * SCENE_NODE_SIZE
            name, name_offset = _named_pointer(
                data, offset, offset + 4, f"{what} node {node_index}"
            )
            hierarchy_count = _u32be(data, offset + 0x60, "hierarchy count")
            hierarchy = _parse_hierarchy_table(
                data, hierarchy_count, offset + 0x64, f"{what} node {node_index}"
            )
            if hierarchy is not None:
                portme.extend(
                    f"node {node_index} {name}: {warning}"
                    for warning in hierarchy["topology_warnings"]
                )
            draw_count = _u32be(data, offset + 0x7C, "draw-record count")
            draw_start = _bounded_array(
                data, draw_count, offset + 0x80, DRAW_RECORD_SIZE, "draw record"
            )
            declarations = _parse_declarations(data, offset, what)
            for declaration in declarations:
                semantic = declaration["indexed_semantic"] or declaration["indexed_semantic_hash"]
                semantic_counts[str(semantic)] += 1

            mesh_count = _u32be(data, offset + 0x84, "mesh descriptor count")
            mesh_start = None
            meshes: list[dict[str, object]] = []
            if mesh_count:
                mesh_start = _relative_target(data, offset + 0x88, "mesh descriptor")
                if mesh_count != 1:
                    portme.append(
                        f"node {node_index} {name}: PORTME mesh descriptor array count {mesh_count}"
                    )
                else:
                    try:
                        mesh = _parse_mesh_descriptor(
                            data,
                            mesh_start,
                            declarations,
                            f"{what} node {node_index}",
                            capture_geometry,
                        )
                        meshes.append(mesh)
                        position = mesh.get("position")
                        if isinstance(position, dict):
                            position_format_counts[str(position.get("format", position.get("status")))] += 1
                    except SceneError as exc:
                        portme.append(f"node {node_index} {name}: {exc}")

            index_component_bits = _u32be(data, offset + 0xA4, "index component bits")
            index_count = _u32be(data, offset + 0xA8, "index count")
            indices: list[int] | None = None
            index_start = None
            if index_count:
                index_start = _relative_target(data, offset + 0xAC, "index data")
                if index_component_bits in (16, 32):
                    component_bytes = index_component_bits // 8
                    if index_start + index_count * component_bytes > len(data):
                        raise SceneError(f"{what} node {node_index}: index data exceeds SCNE part")
                    if index_component_bits == 16:
                        indices = [
                            _u16be(data, index_start + i * 2, "index")
                            for i in range(index_count)
                        ]
                        restart_index = 0xFFFF
                    else:
                        indices = [
                            _u32be(data, index_start + i * 4, "index")
                            for i in range(index_count)
                        ]
                        restart_index = 0xFFFFFFFF
                    if meshes and max((index for index in indices if index != restart_index), default=-1) >= int(meshes[0]["vertex_count"]):
                        raise SceneError(f"{what} node {node_index}: index exceeds vertex count")
                    if capture_geometry and meshes and "_geometry" in meshes[0]:
                        meshes[0]["_geometry"]["indices"] = indices  # type: ignore[index]
                else:
                    portme.append(
                        f"node {node_index} {name}: PORTME index width field {_hex(index_component_bits)}"
                    )

            nodes.append(
                {
                    "index": node_index,
                    "offset": offset,
                    "name": name,
                    "name_offset": name_offset,
                    "name_crc32": _hex(_u32be(data, offset + 4, "node hash")),
                    "type_or_flags_0c": _hex(_u32be(data, offset + 0x0C, "node field 0c")),
                    "hash_10": _hex(_u32be(data, offset + 0x10, "node field 10")),
                    "hierarchy": hierarchy,
                    "draw_record_count": draw_count,
                    "draw_record_offset": draw_start,
                    "mesh_descriptor_count": mesh_count,
                    "mesh_descriptor_offset": mesh_start,
                    "vertex_declarations": declarations,
                    "meshes": meshes,
                    "index_component_bits": index_component_bits,
                    "index_count": index_count,
                    "index_offset": index_start,
                    "index_sha256": None
                    if indices is None
                    else hashlib.sha256(
                        b"".join(
                            struct.pack(">H" if index_component_bits == 16 else ">I", index)
                            for index in indices
                        )
                    ).hexdigest(),
                }
            )

    return {
        "root_name": root_name,
        "root_name_offset": root_offset,
        "system_length": len(data),
        "system_sha256": hashlib.sha256(data).hexdigest(),
        "header_words_00_60": [
            _hex(_u32be(data, offset, "scene header"))
            for offset in range(0, SCENE_HEADER_MIN, 4)
        ],
        "matrix_count": matrix_count,
        "matrix_offset": matrix_start,
        "matrix_sha256": matrix_sha256,
        "matrix_nonfinite_component_count": len(matrix_nonfinite_offsets),
        "matrix_nonfinite_offsets": matrix_nonfinite_offsets[:64],
        "scene_node_count": node_count,
        "scene_node_offset": node_start,
        "nodes": nodes,
        "semantic_counts": dict(semantic_counts.most_common()),
        "position_format_counts": dict(position_format_counts.most_common()),
        "portme": portme,
    }


def _expand_triangle_strip(indices: Iterable[int]) -> list[int]:
    output: list[int] = []
    strip: list[int] = []
    for index in indices:
        if index in (0xFFFF, 0xFFFFFFFF):
            strip.clear()
            continue
        strip.append(index)
        if len(strip) < 3:
            continue
        triangle_number = len(strip) - 3
        a, b, c = strip[-3:]
        triangle = (a, b, c) if triangle_number % 2 == 0 else (b, a, c)
        if len(set(triangle)) == 3:
            output.extend(triangle)
    return output


def write_gltf(path: Path, scene: dict[str, object], outer_index: int, inner_index: int) -> None:
    candidates: list[tuple[dict[str, object], dict[str, object]]] = []
    for node in scene["nodes"]:  # type: ignore[assignment]
        for mesh in node["meshes"]:
            geometry = mesh.get("_geometry")
            if isinstance(geometry, dict) and geometry.get("positions") and geometry.get("indices"):
                candidates.append((node, mesh))
    if len(candidates) != 1:
        raise SceneError(
            f"PORTME: glTF proof requires exactly one decoded indexed mesh, found {len(candidates)}"
        )
    node, mesh = candidates[0]
    if int(mesh["primitive_type"]) != 5:
        raise SceneError(
            f"PORTME: glTF proof supports serialized D3DPT_TRIANGLESTRIP (5), got {mesh['primitive_type']}"
        )
    geometry = mesh["_geometry"]
    positions = geometry["positions"]
    triangles = _expand_triangle_strip(geometry["indices"])
    if not triangles:
        raise SceneError("PORTME: triangle-strip expansion produced no triangles")
    if max(triangles) >= len(positions):
        raise SceneError("triangle index exceeds decoded POSITION count")

    position_bytes = b"".join(struct.pack("<3f", *position) for position in positions)
    index_offset = (len(position_bytes) + 3) & ~3
    padding = b"\0" * (index_offset - len(position_bytes))
    index_bytes = b"".join(struct.pack("<I", index) for index in triangles)
    blob = position_bytes + padding + index_bytes
    minima = [min(position[i] for position in positions) for i in range(3)]
    maxima = [max(position[i] for position in positions) for i in range(3)]
    document = {
        "asset": {
            "version": "2.0",
            "generator": "apf_scene.py evidence-checked SCNE proof exporter",
            "extras": {
                "scope": "POSITION plus 16-bit D3D triangle-strip indices; materials, UVs, normals, skinning and animation are intentionally omitted",
                "outer_table_index": outer_index,
                "inner_file_index": inner_index,
                "scne_root_name": scene["root_name"],
                "system_sha256": scene["system_sha256"],
            },
        },
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": node["name"], "mesh": 0}],
        "meshes": [
            {
                "name": node["name"],
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "mode": 4,
                    }
                ],
            }
        ],
        "buffers": [
            {
                "byteLength": len(blob),
                "uri": "data:application/octet-stream;base64," + base64.b64encode(blob).decode("ascii"),
            }
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": len(index_bytes), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(positions),
                "type": "VEC3",
                "min": minima,
                "max": maxima,
            },
            {
                "bufferView": 1,
                "componentType": 5125,
                "count": len(triangles),
                "type": "SCALAR",
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _little_endian_array(typecode: str, values: Iterable[float | int]) -> bytes:
    packed = array(typecode, values)
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def _safe_scene_stem(outer_index: int, inner_index: int, root_name: str) -> str:
    safe = "".join(
        character
        if character.isascii() and (character.isalnum() or character in "-_")
        else "_"
        for character in root_name
    ).strip("_")
    return f"{outer_index:04d}_{inner_index:04d}_{(safe or 'scene')[:80]}"


def write_gltf_collection(
    path: Path,
    bin_path: Path,
    scene: dict[str, object],
    outer_index: int,
    inner_index: int,
) -> dict[str, object]:
    """Write every proved static mesh in one SCNE without inferred transforms."""

    binary = bytearray()
    buffer_views: list[dict[str, object]] = []
    accessors: list[dict[str, object]] = []
    nodes: list[dict[str, object]] = []
    meshes: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    vertex_total = 0
    triangle_total = 0

    def align4() -> None:
        binary.extend(bytes((-len(binary)) & 3))

    for node in scene["nodes"]:  # type: ignore[assignment]
        for source_mesh_index, mesh in enumerate(node["meshes"]):
            geometry = mesh.get("_geometry")
            if not isinstance(geometry, dict):
                skipped.append(
                    {
                        "node_index": node["index"],
                        "node_name": node["name"],
                        "mesh_index": source_mesh_index,
                        "portme": "PORTME: mesh has no evidence-checked POSITION geometry",
                    }
                )
                continue
            positions = geometry.get("positions")
            indices = geometry.get("indices")
            if not isinstance(positions, list) or not isinstance(indices, list):
                skipped.append(
                    {
                        "node_index": node["index"],
                        "node_name": node["name"],
                        "mesh_index": source_mesh_index,
                        "portme": "PORTME: mesh is missing decoded positions or bounded indices",
                    }
                )
                continue
            if int(mesh["primitive_type"]) != 5:
                skipped.append(
                    {
                        "node_index": node["index"],
                        "node_name": node["name"],
                        "mesh_index": source_mesh_index,
                        "portme": (
                            "PORTME: static collection supports serialized "
                            f"D3DPT_TRIANGLESTRIP (5), got {mesh['primitive_type']}"
                        ),
                    }
                )
                continue
            triangles = _expand_triangle_strip(indices)
            if not triangles:
                skipped.append(
                    {
                        "node_index": node["index"],
                        "node_name": node["name"],
                        "mesh_index": source_mesh_index,
                        "portme": "PORTME: bounded strip contains no non-degenerate triangles",
                    }
                )
                continue
            if max(triangles) >= len(positions):
                raise SceneError(
                    f"node {node['index']} {node['name']}: triangle index exceeds POSITION count"
                )

            align4()
            position_offset = len(binary)
            position_bytes = _little_endian_array(
                "f", (component for position in positions for component in position)
            )
            binary.extend(position_bytes)
            position_view = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": position_offset,
                    "byteLength": len(position_bytes),
                    "target": 34962,
                }
            )
            position_accessor = len(accessors)
            accessors.append(
                {
                    "bufferView": position_view,
                    "componentType": 5126,
                    "count": len(positions),
                    "type": "VEC3",
                    "min": [min(position[axis] for position in positions) for axis in range(3)],
                    "max": [max(position[axis] for position in positions) for axis in range(3)],
                }
            )

            align4()
            index_offset = len(binary)
            index_bytes = _little_endian_array("I", triangles)
            binary.extend(index_bytes)
            index_view = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": index_offset,
                    "byteLength": len(index_bytes),
                    "target": 34963,
                }
            )
            index_accessor = len(accessors)
            accessors.append(
                {
                    "bufferView": index_view,
                    "componentType": 5125,
                    "count": len(triangles),
                    "type": "SCALAR",
                    "min": [min(triangles)],
                    "max": [max(triangles)],
                }
            )

            output_mesh = len(meshes)
            meshes.append(
                {
                    "name": node["name"],
                    "primitives": [
                        {
                            "attributes": {"POSITION": position_accessor},
                            "indices": index_accessor,
                            "mode": 4,
                        }
                    ],
                    "extras": {
                        "apf_scene_node_index": node["index"],
                        "apf_source_mesh_index": source_mesh_index,
                        "position_format": mesh["position"]["format"],
                        "source_primitive": "D3DPT_TRIANGLESTRIP",
                        "topology_conversion": "non-degenerate strip triangles",
                    },
                }
            )
            nodes.append(
                {
                    "name": node["name"],
                    "mesh": output_mesh,
                    "extras": {
                        "apf_scene_node_index": node["index"],
                        "raw_coordinates": True,
                    },
                }
            )
            vertex_total += len(positions)
            triangle_total += len(triangles) // 3

    if not meshes:
        raise SceneError(
            "PORTME: SCNE contains no non-degenerate static mesh with proved POSITION/topology"
        )

    align4()
    document = {
        "asset": {
            "version": "2.0",
            "generator": "apf_scene.py evidence-checked static collection exporter",
            "extras": {
                "scope": (
                    "decoded POSITION plus bounded D3D triangle-strip topology; "
                    "raw coordinates with materials, transforms, UVs, normals, skinning, "
                    "morphs and animation intentionally omitted"
                ),
                "outer_table_index": outer_index,
                "inner_file_index": inner_index,
                "scne_root_name": scene["root_name"],
                "system_sha256": scene["system_sha256"],
            },
        },
        "scene": 0,
        "scenes": [{"name": scene["root_name"], "nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "buffers": [{"byteLength": len(binary), "uri": bin_path.name}],
        "bufferViews": buffer_views,
        "accessors": accessors,
        "extras": {
            "skipped": skipped,
            "portme": [
                "PORTME: map draw/material records and recovered TXTRs to glTF materials.",
                "PORTME: prove matrix ownership before applying scene-node transforms.",
                "PORTME: export NORMAL/TEXCOORD/JOINTS/WEIGHTS only after declaration semantics are validated end to end.",
                "PORTME: bind skeletons, morph channels, and animation only after runtime consumers are recovered.",
            ],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(binary)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "status": "exported",
        "gltf": path.name,
        "bin": bin_path.name,
        "mesh_count": len(meshes),
        "skipped_mesh_count": len(skipped),
        "vertex_count": vertex_total,
        "triangle_count": triangle_total,
        "binary_bytes": len(binary),
        "gltf_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bin_sha256": hashlib.sha256(binary).hexdigest(),
    }


def _strip_private_geometry(scene: dict[str, object]) -> None:
    for node in scene.get("nodes", []):
        for mesh in node.get("meshes", []):
            mesh.pop("_geometry", None)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to APF first archive volume (0A)")
    parser.add_argument("--output", type=Path, required=True, help="deterministic JSON report")
    parser.add_argument("--tsv", type=Path, help="one-row-per-scene-node TSV")
    parser.add_argument(
        "--select",
        metavar="OUTER:INNER",
        help="decode only one SCNE (required for --gltf; optional with --gltf-dir)",
    )
    parser.add_argument("--gltf", type=Path, help="write one strict proof glTF")
    parser.add_argument(
        "--gltf-dir",
        type=Path,
        help=(
            "write one external-buffer static glTF collection per parsed SCNE and a "
            "manifest; unresolved materials/transforms/skinning remain PORTME"
        ),
    )
    parser.add_argument(
        "--max-decompressed",
        type=int,
        default=64 * 1024 * 1024,
        help="per-IFF-block H7A output ceiling (default: 64 MiB)",
    )
    return parser


def _selection(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    try:
        outer, inner = value.split(":", 1)
        return int(outer, 0), int(inner, 0)
    except (ValueError, TypeError) as exc:
        raise SceneError("--select must be OUTER:INNER") from exc


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        selected = _selection(args.select)
        if args.gltf is not None and args.gltf_dir is not None:
            raise SceneError("--gltf and --gltf-dir are mutually exclusive")
        if args.gltf is not None and selected is None:
            raise SceneError("--gltf requires --select OUTER:INNER")
        archive = apf_outer.parse_archive(args.index)
        scenes: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        total_scne = 0
        decoded_block_count = 0
        decoded_block_bytes = 0
        format_counts: Counter[str] = Counter()
        semantic_counts: Counter[str] = Counter()
        selected_scene: dict[str, object] | None = None
        gltf_exports: list[dict[str, object]] = []

        with apf_inner.ArchiveReader(archive) as reader:
            for entry in archive.entries:
                if entry.head_hex != "ff3bef94":
                    continue
                if selected is not None and entry.table_index != selected[0]:
                    continue
                record = apf_inner.parse_iff(reader, entry)
                targets = [
                    file
                    for file in record.files
                    if file.type_name == "SCNE"
                    and (selected is None or file.index == selected[1])
                ]
                total_scne += len(targets)
                block_cache: dict[int, bytes] = {}
                for file in targets:
                    if not file.parts:
                        failures.append(
                            {
                                "outer_table_index": entry.table_index,
                                "inner_file_index": file.index,
                                "name": file.name,
                                "error": "PORTME: SCNE has no present system part",
                            }
                        )
                        continue
                    part = file.parts[0]
                    try:
                        if part.block_index not in block_cache:
                            block_cache[part.block_index] = apf_inner.decode_block(
                                reader,
                                record,
                                part.block_index,
                                args.max_decompressed,
                            )
                            decoded_block_count += 1
                            decoded_block_bytes += len(block_cache[part.block_index])
                        block_data = block_cache[part.block_index]
                        system = block_data[part.offset : part.offset + part.length]
                        scene = parse_scene_system_part(
                            system,
                            outer_index=entry.table_index,
                            inner_index=file.index,
                            capture_geometry=(
                                args.gltf is not None or args.gltf_dir is not None
                            ),
                        )
                        scene.update(
                            {
                                "outer_table_index": entry.table_index,
                                "outer_name_id": _hex(entry.name_id),
                                "inner_file_index": file.index,
                                "inner_name": file.name,
                                "parts": [
                                    {
                                        "block_index": item.block_index,
                                        "offset": item.offset,
                                        "length": item.length,
                                    }
                                    for item in file.parts
                                ],
                            }
                        )
                        scenes.append(scene)
                        format_counts.update(scene["position_format_counts"])
                        semantic_counts.update(scene["semantic_counts"])
                        if args.gltf_dir is not None:
                            stem = _safe_scene_stem(
                                entry.table_index, file.index, str(scene["root_name"])
                            )
                            gltf_path = args.gltf_dir / f"{stem}.gltf"
                            bin_path = args.gltf_dir / f"{stem}.bin"
                            export_identity = {
                                "outer_table_index": entry.table_index,
                                "inner_file_index": file.index,
                                "root_name": scene["root_name"],
                                "system_sha256": scene["system_sha256"],
                            }
                            try:
                                gltf_exports.append(
                                    {
                                        **export_identity,
                                        **write_gltf_collection(
                                            gltf_path,
                                            bin_path,
                                            scene,
                                            entry.table_index,
                                            file.index,
                                        ),
                                    }
                                )
                            except SceneError as exc:
                                gltf_exports.append(
                                    {
                                        **export_identity,
                                        "status": "withheld",
                                        "portme": str(exc),
                                    }
                                )
                            _strip_private_geometry(scene)
                        if selected is not None:
                            selected_scene = scene
                    except (SceneError, apf_inner.FormatError) as exc:
                        failures.append(
                            {
                                "outer_table_index": entry.table_index,
                                "inner_file_index": file.index,
                                "name": file.name,
                                "system_part": {
                                    "block_index": part.block_index,
                                    "offset": part.offset,
                                    "length": part.length,
                                },
                                "error": str(exc),
                                "portme": "trace this SCNE variant in the loader before interpreting it",
                            }
                        )

        if selected is not None and total_scne == 0:
            raise SceneError(f"selected SCNE {selected[0]}:{selected[1]} was not found")
        if args.gltf is not None:
            if selected_scene is None:
                raise SceneError("selected SCNE did not pass structural parsing; glTF withheld")
            write_gltf(args.gltf, selected_scene, selected[0], selected[1])
        if args.gltf_dir is not None:
            args.gltf_dir.mkdir(parents=True, exist_ok=True)
            exported = [item for item in gltf_exports if item["status"] == "exported"]
            withheld = [item for item in gltf_exports if item["status"] == "withheld"]
            manifest = {
                "schema": "apf_static_gltf_manifest/v1",
                "source_index": str(archive.index_path),
                "scope": (
                    "static raw-coordinate POSITION/topology collections only; "
                    "materials, transforms, UVs, normals, skinning, morphs and animation are PORTME"
                ),
                "summary": {
                    "scene_count": len(gltf_exports),
                    "exported_scene_count": len(exported),
                    "withheld_scene_count": len(withheld),
                    "mesh_count": sum(int(item["mesh_count"]) for item in exported),
                    "skipped_mesh_count": sum(
                        int(item["skipped_mesh_count"]) for item in exported
                    ),
                    "vertex_count": sum(int(item["vertex_count"]) for item in exported),
                    "triangle_count": sum(
                        int(item["triangle_count"]) for item in exported
                    ),
                    "binary_bytes": sum(int(item["binary_bytes"]) for item in exported),
                },
                "exports": gltf_exports,
                "portme": [
                    "PORTME: reconstruct materials and texture assignments.",
                    "PORTME: prove and apply node transforms/hierarchy.",
                    "PORTME: recover normals, UVs, skinning, morph targets, and animation.",
                    "PORTME: implement a validated reverse path from edited glTF to SCNE/IFF/H7A/archive data.",
                ],
            }
            (args.gltf_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        for scene in scenes:
            _strip_private_geometry(scene)

        document = {
            "schema": "apf_scene_inventory/v1",
            "source_index": str(archive.index_path),
            "selection": None if selected is None else {"outer": selected[0], "inner": selected[1]},
            "constants": {
                "endianness": "big-endian fields and float payloads; UTF-16BE names",
                "self_relative_pointer": "target = pointer_field_offset + stored_u32 - 1",
                "scene_node_size": SCENE_NODE_SIZE,
                "matrix_size": MATRIX_SIZE,
                "hierarchy_table_header_size": JOINT_TABLE_HEADER_SIZE,
                "hierarchy_record_size": JOINT_RECORD_SIZE,
                "draw_record_size": DRAW_RECORD_SIZE,
                "vertex_declaration_record_size": DECLARATION_RECORD_SIZE,
                "stream_record_size": STREAM_RECORD_SIZE,
                "format_encoder_function": "APF XEX 0x84B8BE00",
                "primitive_code_5": "D3DPT_TRIANGLESTRIP",
            },
            "summary": {
                "scne_selected": total_scne,
                "scne_parsed": len(scenes),
                "scne_failures": len(failures),
                "decoded_unique_record_blocks": decoded_block_count,
                "decoded_block_bytes": decoded_block_bytes,
                "scene_nodes": sum(int(scene["scene_node_count"]) for scene in scenes),
                "hierarchy_records": sum(
                    int(node["hierarchy"]["count"])
                    for scene in scenes
                    for node in scene["nodes"]
                    if node["hierarchy"] is not None
                ),
                "vertex_declarations": sum(
                    len(node["vertex_declarations"])
                    for scene in scenes
                    for node in scene["nodes"]
                ),
                "position_format_counts": dict(format_counts.most_common()),
                "semantic_counts": dict(semantic_counts.most_common()),
                "scenes_with_portme": sum(bool(scene["portme"]) for scene in scenes),
            },
            "failures": failures,
            "scenes": scenes,
            "portme": [
                "name remaining SCNE header and scene-node fields from loader call sites",
                "map draw records to material slots and prove every primitive/topology variant",
                "decode every observed vertex format and declaration transform, not only POSITION proof formats",
                "identify matrix ownership, bind/inverse-bind matrices, skin weights, and animation bindings before skinned glTF export",
                "map SCNE shader/material references to TXTR resources and preserve round-trip alignment",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

        if args.tsv is not None:
            args.tsv.parent.mkdir(parents=True, exist_ok=True)
            with args.tsv.open("w", encoding="utf-8", newline="") as output:
                output.write(
                    "outer_table_index\tinner_file_index\troot_name\tnode_index\tnode_name\t"
                    "hierarchy_count\tvertex_decl_count\tvertex_count\tindex_count\tprimitive\tportme\n"
                )
                for scene in scenes:
                    for node in scene["nodes"]:
                        meshes = node["meshes"]
                        mesh = meshes[0] if meshes else {}
                        hierarchy = node["hierarchy"]
                        values = (
                            scene["outer_table_index"],
                            scene["inner_file_index"],
                            scene["root_name"],
                            node["index"],
                            node["name"],
                            0 if hierarchy is None else hierarchy["count"],
                            len(node["vertex_declarations"]),
                            mesh.get("vertex_count", ""),
                            node["index_count"],
                            mesh.get("primitive_type", ""),
                            " | ".join(scene["portme"]),
                        )
                        output.write("\t".join(str(value).replace("\t", " ") for value in values) + "\n")

        print(
            f"APF SCNE: parsed {len(scenes)}/{total_scne}; failures {len(failures)}; "
            f"nodes {document['summary']['scene_nodes']}; hierarchies "
            f"{document['summary']['hierarchy_records']}"
        )
        if args.gltf is not None:
            print(f"wrote proof glTF: {args.gltf}")
        if args.gltf_dir is not None:
            summary = manifest["summary"]
            print(
                "APF_STATIC_GLTF_EXPORT_COMPLETE "
                f"scenes={summary['exported_scene_count']}/{summary['scene_count']} "
                f"meshes={summary['mesh_count']} vertices={summary['vertex_count']} "
                f"triangles={summary['triangle_count']} -> {args.gltf_dir}"
            )
        return 1 if failures else 0
    except (SceneError, apf_inner.FormatError, apf_outer.FormatError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
