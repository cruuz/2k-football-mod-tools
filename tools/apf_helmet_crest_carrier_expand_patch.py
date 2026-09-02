#!/usr/bin/env python3
"""Build a private APF 2K8 dual-LOD expanded crest-carrier diagnostic.

This is deliberately source-bound and copy-only.  It changes only POSITION0.xyz,
NORMAL0.xyz, and TANGENT0.xyz for draw 2 of ``helmet_hi`` and ``helmet_lo`` in
retail ``helmet_00``.  The existing NORMAL0.w/TANGENT0.w logo UVs, POSITION0.w,
blend lanes, index topology, draw records, and all sibling data are preserved.

The result is an experimental runtime witness, not a public editor feature.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_shell_material_route_patch as base  # noqa: E402
import apf_inner  # noqa: E402
import apf_scene  # noqa: E402
from mod_editor.core import platform_compat  # noqa: E402


SCHEMA = "apf2k8_helmet_crest_carrier_expand_patch/v1"
OPERATION = "expand_helmet_hi_and_lo_draw_2_crest_carrier"
RECEIPT_SUFFIX = ".apf-helmet-crest-carrier-expand.json"


@dataclass(frozen=True)
class LodSpec:
    node_index: int
    node_name: str
    draw_record_offset: int
    index_offset: int
    index_count: int
    shell_index_start: int
    shell_index_count: int
    shell_vertex_start: int
    shell_vertex_count: int
    carrier_index_start: int
    carrier_index_count: int
    carrier_vertex_start: int
    carrier_vertex_count: int
    stream_start: int
    vertex_count: int
    center: tuple[float, float, float]
    scale: tuple[float, float, float]


LODS = (
    LodSpec(
        0, "helmet_hi", 0x000099C0, 0x00009C30, 9773,
        2623, 4800, 1312, 1427, 7423, 1046, 2739, 326,
        0x0000EA1C, 3856,
        (0.0, 4.927330017089844, 1.7508296966552734),
        (13.967263221740723,) * 3,
    ),
    LodSpec(
        32, "helmet_lo", 0x000CCA80, 0x000CCCF0, 1552,
        359, 659, 193, 283, 1018, 231, 476, 128,
        0x000CDA9C, 799,
        (0.0, 2.8593978881835938, 2.8941473960876465),
        (16.119155883789062,) * 3,
    ),
)

STRIDE = 32
AUTHORIZED_COMPONENTS = ((0, 6), (8, 14), (16, 22))
MIN_TRIANGLE_AREA = 1.0e-4
MIN_WINDING_DOT = 1.0e-4
MAX_REPAIR_ROUNDS = 36


class PatchError(base.PatchError):
    """The fixed carrier diagnostic failed closed."""


@dataclass(frozen=True)
class Projection:
    position: tuple[float, float, float]
    normal: tuple[float, float, float]


@dataclass(frozen=True)
class BuiltPatch:
    source: base.SourceEntry
    rebuilt_entry: bytes
    output_system: bytes
    file_length_after: int
    h7a_metrics: dict[str, int]
    metrics: dict[str, Any]


def _dot(a: Iterable[float], b: Iterable[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(a[i] - b[i] for i in range(3))  # type: ignore[return-value]


def _add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(a[i] + b[i] for i in range(3))  # type: ignore[return-value]


def _mul(a: tuple[float, float, float], value: float) -> tuple[float, float, float]:
    return tuple(component * value for component in a)  # type: ignore[return-value]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(a: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: tuple[float, float, float]) -> tuple[float, float, float]:
    length = _length(a)
    if not math.isfinite(length) or length <= 1.0e-12:
        raise PatchError("could not normalize a carrier vector")
    return _mul(a, 1.0 / length)


def _snorm(word: int) -> float:
    return max(word / 32767.0, -1.0)


def _decode_vec3(payload: bytes, offset: int) -> tuple[float, float, float]:
    return tuple(_snorm(word) for word in struct.unpack_from(">3h", payload, offset))  # type: ignore[return-value]


def _encode_vec3(value: tuple[float, float, float]) -> bytes:
    if not all(math.isfinite(component) and -1.0 <= component <= 1.0 for component in value):
        raise PatchError("carrier vector is outside signed-normalized bounds")
    words = [max(-32767, min(32767, round(component * 32767.0))) for component in value]
    return struct.pack(">3h", *words)


def _decode_position(payload: bytes, spec: LodSpec, vertex: int) -> tuple[float, float, float]:
    raw = _decode_vec3(payload, spec.stream_start + vertex * STRIDE)
    return tuple(spec.center[i] + raw[i] * spec.scale[i] for i in range(3))  # type: ignore[return-value]


def _encode_position(value: tuple[float, float, float], spec: LodSpec) -> bytes:
    normalized = tuple((value[i] - spec.center[i]) / spec.scale[i] for i in range(3))
    return _encode_vec3(normalized)  # type: ignore[arg-type]


def _uv(payload: bytes, spec: LodSpec, vertex: int) -> tuple[float, float]:
    start = spec.stream_start + vertex * STRIDE
    # The crest carrier uses the two W lanes as 2*SNORM UV coordinates.
    return (
        2.0 * _snorm(struct.unpack_from(">h", payload, start + 14)[0]),
        2.0 * _snorm(struct.unpack_from(">h", payload, start + 22)[0]),
    )


def _indices(payload: bytes, spec: LodSpec) -> list[int]:
    end = spec.index_offset + spec.index_count * 2
    if end > len(payload):
        raise PatchError(f"{spec.node_name} index table is truncated")
    return list(struct.unpack_from(f">{spec.index_count}H", payload, spec.index_offset))


def _triangles(indices: list[int]) -> list[tuple[int, int, int]]:
    output: list[tuple[int, int, int]] = []
    strip: list[int] = []
    for index in indices:
        if index == 0xFFFF:
            strip.clear()
            continue
        strip.append(index)
        if len(strip) < 3:
            continue
        number = len(strip) - 3
        a, b, c = strip[-3:]
        if number & 1:
            a, b = b, a
        if len({a, b, c}) == 3:
            output.append((a, b, c))
    return output


def _closest_point(
    point: tuple[float, float, float],
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return closest point and barycentric coordinates (Ericson)."""

    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a, (1.0, 0.0, 0.0)
    bp = _sub(point, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return _add(a, _mul(ab, v)), (1.0 - v, v, 0.0)
    cp = _sub(point, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return _add(a, _mul(ac, w)), (1.0 - w, 0.0, w)
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and d4 - d3 >= 0.0 and d5 - d6 >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return _add(b, _mul(_sub(c, b), w)), (0.0, 1.0 - w, w)
    denominator = 1.0 / (va + vb + vc)
    v, w = vb * denominator, vc * denominator
    return _add(a, _add(_mul(ab, v), _mul(ac, w))), (1.0 - v - w, v, w)


def _validate_layout(payload: bytes, spec: LodSpec, node: dict[str, Any]) -> None:
    if (
        node.get("name") != spec.node_name
        or node.get("draw_record_offset") != spec.draw_record_offset
        or node.get("index_offset") != spec.index_offset
        or node.get("index_count") != spec.index_count
        or node.get("index_component_bits") != 16
    ):
        raise PatchError(f"{spec.node_name} scene identity drift")
    meshes = node.get("meshes")
    if not isinstance(meshes, list) or len(meshes) != 1:
        raise PatchError(f"{spec.node_name} mesh inventory drift")
    mesh = meshes[0]
    streams = mesh.get("streams")
    if (
        mesh.get("vertex_count") != spec.vertex_count
        or not isinstance(streams, list)
        or len(streams) != 1
        or streams[0].get("start") != spec.stream_start
        or streams[0].get("stride") != STRIDE
    ):
        raise PatchError(f"{spec.node_name} vertex stream drift")
    declarations = node.get("vertex_declarations")
    wanted = [
        ("POSITION0", 0, "snorm16x4"),
        ("NORMAL0", 8, "snorm16x4"),
        ("TANGENT0", 16, "snorm16x4"),
        ("BLENDINDICES0", 24, "uint8x4"),
        ("BLENDWEIGHT0", 28, "unorm8x4"),
    ]
    actual = [
        (item.get("indexed_semantic"), item.get("byte_offset"), item.get("format_name"))
        for item in declarations
    ] if isinstance(declarations, list) else []
    if actual != wanted:
        raise PatchError(f"{spec.node_name} declaration layout drift")
    draws = [struct.unpack_from(">12I", payload, spec.draw_record_offset + i * 0x30) for i in range(3)]
    expected = (
        (spec.shell_index_start, spec.shell_index_count, spec.shell_vertex_start, spec.shell_vertex_count, 1),
        (spec.carrier_index_start, spec.carrier_index_count, spec.carrier_vertex_start, spec.carrier_vertex_count, 2),
    )
    for record, wanted_draw in zip(draws[1:3], expected):
        if (record[1], record[2], record[5], record[6], record[8]) != wanted_draw:
            raise PatchError(f"{spec.node_name} shell/carrier draw window drift")


def _project_to_shell(
    wanted: tuple[float, float, float],
    side: int,
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    shell_triangles: list[tuple[int, int, int]],
) -> Projection:
    best: tuple[float, tuple[float, float, float], tuple[int, int, int], tuple[float, float, float]] | None = None
    for triangle in shell_triangles:
        if not all(positions[index][0] * side >= -1.0e-6 for index in triangle):
            continue
        point, barycentric = _closest_point(
            wanted,
            positions[triangle[0]], positions[triangle[1]], positions[triangle[2]],
        )
        distance = _dot(_sub(wanted, point), _sub(wanted, point))
        candidate = (distance, point, triangle, barycentric)
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        raise PatchError("could not project carrier vertex onto same-side shell")
    _, point, triangle, barycentric = best
    normal = _unit(tuple(
        sum(barycentric[j] * normals[triangle[j]][axis] for j in range(3))
        for axis in range(3)
    ))
    return Projection(point, normal)


def _bad_triangles(
    projections: dict[int, Projection],
    triangles: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    bad: list[tuple[int, int, int]] = []
    for triangle in triangles:
        a, b, c = (projections[index].position for index in triangle)
        geometric = _cross(_sub(b, a), _sub(c, a))
        area = 0.5 * _length(geometric)
        average = _unit(tuple(
            sum(projections[index].normal[axis] for index in triangle)
            for axis in range(3)
        ))
        if area <= MIN_TRIANGLE_AREA or _dot(geometric, average) <= MIN_WINDING_DOT:
            bad.append(triangle)
    return bad


def _expanded_geometry(
    payload: bytes,
    spec: LodSpec,
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    shell_triangles: list[tuple[int, int, int]],
    carrier_triangles: list[tuple[int, int, int]],
) -> tuple[dict[int, Projection], int]:
    carrier = list(range(spec.carrier_vertex_start, spec.carrier_vertex_start + spec.carrier_vertex_count))
    x0 = min(abs(positions[index][0]) for index in carrier)
    x1 = max(abs(positions[index][0]) for index in carrier)
    y0 = min(positions[index][1] for index in carrier)
    y1 = max(positions[index][1] for index in carrier)
    z0 = min(positions[index][2] for index in carrier)
    z1 = max(positions[index][2] for index in carrier)
    aggressive: dict[int, tuple[float, float, float]] = {}
    for index in carrier:
        side = 1 if positions[index][0] > 0.0 else -1
        tx = (abs(positions[index][0]) - x0) / (x1 - x0)
        ty = (positions[index][1] - y0) / (y1 - y0)
        tz = (positions[index][2] - z0) / (z1 - z0)
        if spec.node_name == "helmet_hi":
            # A smooth two-axis shell arc.  Power < 1 keeps the central side full
            # while sending the rear/front and crown edges toward the center seam.
            arc = max(0.0, math.sin(math.pi * tz) * math.sin(math.pi * ty)) ** 0.7
            wanted = (
                side * (0.35 + 10.65 * arc),
                2.0 + ty * 16.0,
                -10.8 + tz * 23.8,
            )
        else:
            # The coarse carrier is already vertically broad.  A direct x/z
            # expansion is less distorted for its 64 vertices per side.
            wanted = (
                side * (0.5 + tx * 10.5),
                positions[index][1],
                -10.8 + tz * 21.8,
            )
        aggressive[index] = wanted

    alpha = {index: 1.0 for index in carrier}
    projections: dict[int, Projection] = {}
    repair_round = 0
    while True:
        projections.clear()
        for index in carrier:
            wanted = _add(
                positions[index],
                _mul(_sub(aggressive[index], positions[index]), alpha[index]),
            )
            side = 1 if positions[index][0] > 0.0 else -1
            projections[index] = _project_to_shell(
                wanted, side, positions, normals, shell_triangles
            )
        bad = _bad_triangles(projections, carrier_triangles)
        if not bad:
            return dict(projections), repair_round
        if repair_round >= MAX_REPAIR_ROUNDS:
            raise PatchError(
                f"{spec.node_name} projection retained {len(bad)} folded/degenerate triangles"
            )
        affected = {index for triangle in bad for index in triangle}
        for index in affected:
            alpha[index] *= 0.78
        repair_round += 1


def _tangents(
    payload: bytes,
    spec: LodSpec,
    projections: dict[int, Projection],
    triangles: list[tuple[int, int, int]],
) -> dict[int, tuple[float, float, float]]:
    accumulated = {index: (0.0, 0.0, 0.0) for index in projections}
    for a, b, c in triangles:
        p0, p1, p2 = projections[a].position, projections[b].position, projections[c].position
        uv0, uv1, uv2 = _uv(payload, spec, a), _uv(payload, spec, b), _uv(payload, spec, c)
        du1, dv1 = uv1[0] - uv0[0], uv1[1] - uv0[1]
        du2, dv2 = uv2[0] - uv0[0], uv2[1] - uv0[1]
        determinant = du1 * dv2 - du2 * dv1
        if abs(determinant) <= 1.0e-10:
            continue
        tangent = _mul(
            _sub(_mul(_sub(p1, p0), dv2), _mul(_sub(p2, p0), dv1)),
            1.0 / determinant,
        )
        for index in (a, b, c):
            accumulated[index] = _add(accumulated[index], tangent)
    output: dict[int, tuple[float, float, float]] = {}
    for index, projection in projections.items():
        tangent = _sub(
            accumulated[index],
            _mul(projection.normal, _dot(accumulated[index], projection.normal)),
        )
        if _length(tangent) <= 1.0e-10:
            start = spec.stream_start + index * STRIDE
            source = _decode_vec3(payload, start + 16)
            tangent = _sub(source, _mul(projection.normal, _dot(source, projection.normal)))
        output[index] = _unit(tangent)
    return output


def _bounds(points: Iterable[tuple[float, float, float]]) -> dict[str, list[float]]:
    values = list(points)
    return {
        "minimum": [min(point[axis] for point in values) for axis in range(3)],
        "maximum": [max(point[axis] for point in values) for axis in range(3)],
        "minimum_absolute_x": min(abs(point[0]) for point in values),
    }


GeometryBuilder = Callable[
    [
        bytes,
        LodSpec,
        list[tuple[float, float, float]],
        list[tuple[float, float, float]],
        list[tuple[int, int, int]],
        list[tuple[int, int, int]],
    ],
    tuple[dict[int, Projection], int],
]


def expand_system(
    payload: bytes,
    *,
    geometry_builder: GeometryBuilder = _expanded_geometry,
) -> tuple[bytes, dict[str, Any]]:
    if len(payload) != base.SYSTEM_LENGTH or base.sha256_bytes(payload) != base.SOURCE_SYSTEM_SHA256:
        raise PatchError("helmet_00 SCNE is not the pinned retail source")
    try:
        scene = apf_scene.parse_scene_system_part(
            payload, outer_index=base.OUTER_INDEX, inner_index=base.INNER_INDEX,
            capture_geometry=True,
        )
    except apf_scene.SceneError as exc:
        raise PatchError(f"helmet_00 geometry parse failed: {exc}") from exc
    nodes = scene.get("nodes")
    if not isinstance(nodes, list):
        raise PatchError("helmet node inventory is missing")
    output = bytearray(payload)
    lod_metrics: list[dict[str, Any]] = []
    allowed: set[int] = set()
    preserved: set[int] = set()
    for spec in LODS:
        if len(nodes) <= spec.node_index:
            raise PatchError(f"{spec.node_name} node is missing")
        node = nodes[spec.node_index]
        _validate_layout(payload, spec, node)
        indices = _indices(payload, spec)
        shell_triangles = _triangles(indices[spec.shell_index_start : spec.shell_index_start + spec.shell_index_count])
        carrier_triangles = _triangles(indices[spec.carrier_index_start : spec.carrier_index_start + spec.carrier_index_count])
        if len(shell_triangles) != (2464 if spec.node_name == "helmet_hi" else 432):
            raise PatchError(f"{spec.node_name} shell topology drift")
        if len(carrier_triangles) != (536 if spec.node_name == "helmet_hi" else 184):
            raise PatchError(f"{spec.node_name} carrier topology drift")
        positions = [_decode_position(payload, spec, index) for index in range(spec.vertex_count)]
        normals = [
            _unit(_decode_vec3(payload, spec.stream_start + index * STRIDE + 8))
            for index in range(spec.vertex_count)
        ]
        projections, repair_rounds = geometry_builder(
            payload, spec, positions, normals, shell_triangles, carrier_triangles
        )
        tangents = _tangents(payload, spec, projections, carrier_triangles)
        for index, projection in projections.items():
            start = spec.stream_start + index * STRIDE
            output[start : start + 6] = _encode_position(projection.position, spec)
            output[start + 8 : start + 14] = _encode_vec3(projection.normal)
            output[start + 16 : start + 22] = _encode_vec3(tangents[index])
            for begin, end in AUTHORIZED_COMPONENTS:
                allowed.update(range(start + begin, start + end))
            preserved.update(range(start + 6, start + 8))
            preserved.update(range(start + 14, start + 16))
            preserved.update(range(start + 22, start + 32))
        lod_metrics.append({
            "carrier_triangle_count": len(carrier_triangles),
            "carrier_vertex_count": spec.carrier_vertex_count,
            "node_index": spec.node_index,
            "node_name": spec.node_name,
            "projected_bounds_before_quantization": _bounds(
                projection.position for projection in projections.values()
            ),
            "repair_rounds": repair_rounds,
        })
    changed = set(base.difference_offsets(payload, output))
    if not changed or not changed <= allowed or changed & preserved:
        raise PatchError("SCNE changed outside authorized carrier xyz lanes")
    metrics = {
        "authorized_byte_count": len(allowed),
        "changed_byte_count": len(changed),
        "lods": lod_metrics,
        "preserved_logo_uv_and_skin_byte_count": len(preserved),
    }
    _verify_quantized(payload, bytes(output), metrics)
    return bytes(output), metrics


def _verify_quantized(source: bytes, output: bytes, metrics: dict[str, Any]) -> None:
    quantized_rows: list[dict[str, Any]] = []
    for spec in LODS:
        indices = _indices(source, spec)
        triangles = _triangles(indices[spec.carrier_index_start : spec.carrier_index_start + spec.carrier_index_count])
        points = {
            index: _decode_position(output, spec, index)
            for index in range(spec.carrier_vertex_start, spec.carrier_vertex_start + spec.carrier_vertex_count)
        }
        normals = {
            index: _unit(_decode_vec3(output, spec.stream_start + index * STRIDE + 8))
            for index in points
        }
        minimum_area = math.inf
        minimum_dot = math.inf
        for triangle in triangles:
            a, b, c = (points[index] for index in triangle)
            geometric = _cross(_sub(b, a), _sub(c, a))
            area = 0.5 * _length(geometric)
            average = _unit(tuple(
                sum(normals[index][axis] for index in triangle) for axis in range(3)
            ))
            winding = _dot(geometric, average)
            minimum_area = min(minimum_area, area)
            minimum_dot = min(minimum_dot, winding)
        if minimum_area <= MIN_TRIANGLE_AREA or minimum_dot <= MIN_WINDING_DOT:
            raise PatchError(
                f"{spec.node_name} quantized topology folded or degenerated "
                f"(area={minimum_area}, winding={minimum_dot})"
            )
        for index in points:
            start = spec.stream_start + index * STRIDE
            if source[start + 6 : start + 8] != output[start + 6 : start + 8]:
                raise PatchError(f"{spec.node_name} POSITION0.w changed")
            if source[start + 14 : start + 16] != output[start + 14 : start + 16]:
                raise PatchError(f"{spec.node_name} NORMAL0.w logo U changed")
            if source[start + 22 : start + 24] != output[start + 22 : start + 24]:
                raise PatchError(f"{spec.node_name} TANGENT0.w logo V changed")
            if source[start + 24 : start + 32] != output[start + 24 : start + 32]:
                raise PatchError(f"{spec.node_name} blend lanes changed")
            normal = normals[index]
            tangent = _unit(_decode_vec3(output, start + 16))
            if abs(_dot(normal, tangent)) > 2.0e-3:
                raise PatchError(f"{spec.node_name} quantized tangent is not orthogonal")
        quantized_rows.append({
            "minimum_triangle_area": minimum_area,
            "minimum_winding_dot": minimum_dot,
            "node_name": spec.node_name,
            "position_bounds": _bounds(points.values()),
            "zero_degenerate_triangles": True,
            "zero_flipped_triangles": True,
        })
    metrics["quantized"] = quantized_rows


def build_patch(
    source_0a: Path,
    *,
    geometry_builder: GeometryBuilder = _expanded_geometry,
) -> BuiltPatch:
    source = base.read_source_entry(Path(source_0a))
    output_system, metrics = expand_system(
        source.system, geometry_builder=geometry_builder,
    )
    new_block0 = bytearray(source.blocks[0])
    new_block0[base.SYSTEM_PART_OFFSET : base.SYSTEM_PART_OFFSET + base.SYSTEM_LENGTH] = output_system
    rebuilt, h7a_metrics, file_length = base._rebuild_entry(source, bytes(new_block0))
    reader = base.BytesReader(rebuilt)
    try:
        record = apf_inner.parse_iff(reader, source.entry)
        blocks = tuple(
            apf_inner.decode_block(reader, record, index, base.MAX_DECOMPRESSED)
            for index in range(record.block_count)
        )
    except apf_inner.FormatError as exc:
        raise PatchError(f"rebuilt global.iff failed reopen: {exc}") from exc
    part = record.files[base.INNER_INDEX].parts[0]
    reopened = blocks[part.block_index][part.offset : part.offset + part.length]
    if reopened != output_system:
        raise PatchError("reopened carrier-expanded SCNE differs")
    if blocks[1:] != source.blocks[1:]:
        raise PatchError("decoded sibling blocks changed")
    stored = tuple(
        reader.read(source.entry, block.start_offset, block.stored_length)
        for block in record.blocks
    )
    if stored[1:] != source.stored[1:]:
        raise PatchError("stored sibling blocks changed")
    if len(rebuilt) != base.OUTER_SIZE:
        raise PatchError("rebuilt outer allocation length changed")
    _verify_quantized(source.system, reopened, metrics)
    return BuiltPatch(source, rebuilt, output_system, file_length, h7a_metrics, metrics)


def _receipt(
    built: BuiltPatch,
    *, source_sha: str, output_sha: str, prefix_sha: str, suffix_sha: str,
    copy_method: str, output_name: str,
) -> dict[str, Any]:
    return {
        "claim_flags": {
            "editor_gui_integrated": False,
            "emulator_runtime_visibility_proved": False,
            "private_diagnostic_only": True,
            "visual_eagles_match_proved": False,
        },
        "compression": dict(sorted(built.h7a_metrics.items())),
        "metrics": built.metrics,
        "operation": OPERATION,
        "preservation": {
            "allowed_vertex_lanes": ["POSITION0.xyz", "NORMAL0.xyz", "TANGENT0.xyz"],
            "draw_records_exact": True,
            "indices_exact": True,
            "logo_uv_w_lanes_exact": True,
            "position_w_exact": True,
            "blend_lanes_exact": True,
            "sibling_blocks_decoded_exact": True,
            "sibling_blocks_stored_exact": True,
            "whole_volume_outside_outer_1310_exact": True,
            "outside_outer_1310_prefix_sha256": prefix_sha,
            "outside_outer_1310_suffix_sha256": suffix_sha,
        },
        "result": {
            "copy_method": copy_method,
            "file_length_after": built.file_length_after,
            "outer_entry_sha256": base.sha256_bytes(built.rebuilt_entry),
            "output_name": output_name,
            "output_scne_sha256": base.sha256_bytes(built.output_system),
            "output_volume_sha256": output_sha,
            "output_volume_size_bytes": base.VOLUME_SIZE,
        },
        "schema": SCHEMA,
        "source": {
            "outer_entry_sha256": base.SOURCE_OUTER_SHA256,
            "source_scne_sha256": base.SOURCE_SYSTEM_SHA256,
            "source_volume_sha256": source_sha,
            "source_volume_size_bytes": base.VOLUME_SIZE,
        },
        "target": {
            "inner_file_index": base.INNER_INDEX,
            "inner_name": base.INNER_NAME,
            "lods": [
                {"draw_record_index": 2, "node_index": spec.node_index, "node_name": spec.node_name}
                for spec in LODS
            ],
            "outer_entry_index": base.OUTER_INDEX,
        },
    }


def publish(
    source_0a: Path,
    output_0a: Path,
    receipt_path: Path | None = None,
    *,
    build_fn: Callable[[Path], BuiltPatch] = build_patch,
    receipt_fn: Callable[..., dict[str, Any]] = _receipt,
    receipt_suffix: str = RECEIPT_SUFFIX,
) -> tuple[Path, Path, dict[str, Any]]:
    source_path, output_path = Path(source_0a), Path(output_0a)
    receipt_path = Path(receipt_path) if receipt_path else output_path.with_name(output_path.name + receipt_suffix)
    source_meta = base._regular_source(source_path)
    if output_path.name != base.VOLUME_NAME or not output_path.parent.is_dir():
        raise PatchError("output must be a new file named 0A in an existing directory")
    if not receipt_path.parent.is_dir():
        raise PatchError("receipt parent directory does not exist")
    for path, label in ((output_path, "output 0A"), (receipt_path, "receipt")):
        if path.exists() or path.is_symlink():
            raise PatchError(f"refusing to overwrite {label}: {path}")
    if source_path.resolve(strict=True) == output_path.resolve(strict=False):
        raise PatchError("source and output paths alias")
    built = build_fn(source_path)
    read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    write_flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    source_fd = os.open(source_path, read_flags)
    output_fd: int | None = None
    keep = False
    try:
        opened = os.fstat(source_fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (source_meta.st_dev, source_meta.st_ino, source_meta.st_size):
            raise PatchError("source changed before publication")
        if base.sha256_bytes(os.pread(source_fd, base.OUTER_SIZE, base.OUTER_OFFSET)) != base.SOURCE_OUTER_SHA256:
            raise PatchError("source outer 1310 changed before publication")
        output_fd = os.open(output_path, write_flags, stat.S_IMODE(source_meta.st_mode))
        copy_method = base._copy_fd(source_fd, output_fd, base.VOLUME_SIZE)
        if os.fstat(output_fd).st_size != base.VOLUME_SIZE:
            raise PatchError("copied output 0A has the wrong size")
        if platform_compat.pwrite(output_fd, built.rebuilt_entry, base.OUTER_OFFSET) != base.OUTER_SIZE:
            raise PatchError("short write installing rebuilt global.iff")
        os.fsync(output_fd)
        if os.pread(output_fd, base.OUTER_SIZE, base.OUTER_OFFSET) != built.rebuilt_entry:
            raise PatchError("published outer 1310 failed exact reread")
        prefix_sha = base._hash_fd_range(source_fd, 0, base.OUTER_OFFSET)
        suffix_offset = base.OUTER_OFFSET + base.OUTER_SIZE
        suffix_sha = base._hash_fd_range(source_fd, suffix_offset, base.VOLUME_SIZE - suffix_offset)
        if prefix_sha != base._hash_fd_range(output_fd, 0, base.OUTER_OFFSET):
            raise PatchError("published prefix changed")
        if suffix_sha != base._hash_fd_range(output_fd, suffix_offset, base.VOLUME_SIZE - suffix_offset):
            raise PatchError("published suffix changed")
        document = receipt_fn(
            built,
            source_sha=base._hash_fd(source_fd), output_sha=base._hash_fd(output_fd),
            prefix_sha=prefix_sha, suffix_sha=suffix_sha,
            copy_method=copy_method, output_name=output_path.name,
        )
        base._write_json_new(receipt_path, document)
        keep = True
        return output_path, receipt_path, document
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(source_fd)
        if not keep:
            output_path.unlink(missing_ok=True)
            receipt_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        output, receipt, document = publish(args.source, args.output, args.receipt)
    except (OSError, PatchError) as exc:
        parser.exit(2, f"crest-carrier expansion failed: {exc}\n")
    print(json.dumps({
        "output": str(output),
        "output_sha256": document["result"]["output_volume_sha256"],
        "outer_entry_sha256": document["result"]["outer_entry_sha256"],
        "receipt": str(receipt),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
