#!/usr/bin/env python3
"""Build a bounded APF helmet crest grid prototype for offline validation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_wrap_patch as p  # noqa: E402


SOURCE = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-editor-proof-v17-full-u-pregeometry/0A"
)
DESTINATION = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-v20-c12-yzgrid-candidate-1"
)
BIAS_CM = 0.14
FRONT_MARGIN = 0.003
REAR_MARGIN = 0.065
PROGRESS_EXPONENT = 2.0


def ymap(value: float) -> float:
    knots = ((0.0, 18.0), (122 / 512, 17.5), (390 / 512, 6.0), (1.0, 4.5))
    for (first_v, first_y), (second_v, second_y) in zip(knots, knots[1:]):
        if value <= second_v:
            return first_y + (second_y - first_y) * (
                (value - first_v) / (second_v - first_v)
            )
    return knots[-1][1]


def barycentric_yz(
    y: float,
    z: float,
    triangle: tuple[int, int, int],
    positions: list[tuple[float, float, float]],
) -> tuple[float, float, float] | None:
    a, b, c = (positions[index] for index in triangle)
    denominator = (
        (b[1] - c[1]) * (a[2] - c[2])
        + (c[2] - b[2]) * (a[1] - c[1])
    )
    if abs(denominator) < 1.0e-10:
        return None
    first = (
        (b[1] - c[1]) * (z - c[2])
        + (c[2] - b[2]) * (y - c[1])
    ) / denominator
    second = (
        (c[1] - a[1]) * (z - c[2])
        + (a[2] - c[2]) * (y - c[1])
    ) / denominator
    third = 1.0 - first - second
    if min(first, second, third) < -1.0e-7:
        return None
    return first, second, third


def z_limits(
    y: float,
    triangles: list[tuple[int, int, int]],
    positions: list[tuple[float, float, float]],
) -> tuple[float, float]:
    values: list[float] = []
    for triangle in triangles:
        points = [positions[index] for index in triangle]
        for first, second in (
            (points[0], points[1]),
            (points[1], points[2]),
            (points[2], points[0]),
        ):
            if abs(first[1] - second[1]) < 1.0e-9:
                if abs(y - first[1]) < 1.0e-7:
                    values.extend((first[2], second[2]))
            elif min(first[1], second[1]) - 1.0e-8 <= y <= max(
                first[1], second[1]
            ) + 1.0e-8:
                factor = (y - first[1]) / (second[1] - first[1])
                if -1.0e-7 <= factor <= 1.0 + 1.0e-7:
                    values.append(first[2] + factor * (second[2] - first[2]))
    if not values:
        raise p.PatchError(f"no exterior shell cross-section at y={y}")
    return min(values), max(values)


def solve_surface(
    y: float,
    z: float,
    side: int,
    triangles: list[tuple[int, int, int]],
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
) -> tuple[p.Projection, int]:
    candidates: list[
        tuple[float, tuple[float, float, float], tuple[float, float, float]]
    ] = []
    for triangle in triangles:
        points = [positions[index] for index in triangle]
        if not (
            min(point[1] for point in points) - 1.0e-7
            <= y
            <= max(point[1] for point in points) + 1.0e-7
            and min(point[2] for point in points) - 1.0e-7
            <= z
            <= max(point[2] for point in points) + 1.0e-7
        ):
            continue
        barycentric = barycentric_yz(y, z, triangle, positions)
        if barycentric is None:
            continue
        point = tuple(
            sum(barycentric[item] * points[item][axis] for item in range(3))
            for axis in range(3)
        )
        normal = p._unit(tuple(
            sum(
                barycentric[item] * normals[triangle[item]][axis]
                for item in range(3)
            )
            for axis in range(3)
        ))
        radial = (point[0], point[1], point[2])
        if p._dot(normal, radial) < 0.0:
            normal = p._mul(normal, -1.0)
        candidates.append((side * point[0], point, normal))
    if not candidates:
        raise p.PatchError(f"no exterior YZ solution at y={y}, z={z}, side={side}")
    _signed_x, point, normal = max(candidates, key=lambda item: item[0])
    return p.Projection(p._add(point, p._mul(normal, BIAS_CM)), normal), len(candidates)


def encode_uv(value: float) -> bytes:
    word = max(-32767, min(32767, round(value / 2.0 * 32767)))
    return struct.pack(">h", word)


def cell_strip(
    grid: list[list[int]], row: int, first_cell: int, cell_count: int, side: int,
) -> list[int]:
    """Return a native-winding strip spanning a contiguous run of grid cells."""

    strip: list[int] = []
    for column in range(first_cell, first_cell + cell_count + 1):
        pair = (
            (grid[row][column], grid[row + 1][column])
            if side > 0
            else (grid[row + 1][column], grid[row][column])
        )
        strip.extend(pair)
    return strip


def grid_strips(grid: list[list[int]], rows: int, columns: int, side: int) -> list[list[int]]:
    """Use the audited strip budget while omitting only transparent v3 cells."""

    strips: list[list[int]] = []
    if (rows, columns) == (9, 18):
        # Seven full 17-cell bands are split into the source allocation's safe
        # 10-strip shape.  Band 1 omits its two transparent endpoint cells and
        # uses one-cell strips so both sides fit the fixed 1,046-word window.
        segment_lengths = (2, 2, 2, 2, 2, 2, 2, 1, 1, 1)
        for row in (0, 2, 3, 4, 5, 6, 7):
            first_cell = 0
            for cell_count in segment_lengths:
                strips.append(cell_strip(grid, row, first_cell, cell_count, side))
                first_cell += cell_count
        for first_cell in range(2, 17):
            strips.append(cell_strip(grid, 1, first_cell, 1, side))
        if len(strips) != 85:
            raise AssertionError(f"high grid produced {len(strips)} strips")
        return strips

    if (rows, columns) == (8, 8):
        # Keep all seven cells in band 0 as two strips, retain bands 2..6,
        # then place the four-cell transparent-endpoint-trimmed band 1 last.
        strips.append(cell_strip(grid, 0, 0, 4, side))
        strips.append(cell_strip(grid, 0, 4, 3, side))
        for row in range(2, 7):
            strips.append(cell_strip(grid, row, 0, 7, side))
        strips.append(cell_strip(grid, 1, 3, 4, side))
        if len(strips) != 8:
            raise AssertionError(f"low grid produced {len(strips)} strips")
        return strips

    raise AssertionError(f"unsupported carrier grid {rows}x{columns}")


def carrier_grids(spec: p.LodSpec, rows: int, columns: int) -> dict[int, list[list[int]]]:
    """Return the audited fixed vertex assignment without touching reserved IDs."""

    per_side = rows * columns
    if spec.node_name == "helmet_hi":
        bases = {1: spec.carrier_vertex_start, -1: spec.carrier_vertex_start + 164}
        reserved = {spec.carrier_vertex_start + 162, spec.carrier_vertex_start + 163}
    else:
        bases = {1: spec.carrier_vertex_start, -1: spec.carrier_vertex_start + per_side}
        reserved = set()
    grids: dict[int, list[list[int]]] = {}
    for side, base in bases.items():
        ids = list(range(base, base + per_side))
        if reserved.intersection(ids):
            raise AssertionError(f"{spec.node_name} grid consumed a reserved vertex")
        grids[side] = [
            ids[row * columns : (row + 1) * columns]
            for row in range(rows)
        ]
    return grids


def build() -> tuple[bytes, dict[str, object]]:
    source = p._parse_outer(p.read_source_outer(SOURCE), source=True).system
    output = bytearray(source)
    nodes = p._scene_nodes(source)
    reports: list[dict[str, object]] = []
    for spec in p.LODS:
        p._validate_layout(source, spec, nodes[spec.node_index])
        source_indices = p._indices(source, spec)
        shell_triangles = p._triangles(source_indices[
            spec.shell_index_start : spec.shell_index_start + spec.shell_index_count
        ])
        positions = [
            p._decode_position(source, spec, index)
            for index in range(spec.vertex_count)
        ]
        normals = [
            p._unit(p._decode_vec3(source, spec.stream_start + index * p.STRIDE + 8))
            for index in range(spec.vertex_count)
        ]
        outer_triangles = []
        for triangle in shell_triangles:
            center = tuple(
                sum(positions[index][axis] for index in triangle) / 3.0
                for axis in range(3)
            )
            average = tuple(
                sum(normals[index][axis] for index in triangle)
                for axis in range(3)
            )
            radial = (
                center[0], center[1] - spec.center[1], center[2] - spec.center[2]
            )
            if p._dot(average, radial) > 0.0:
                outer_triangles.append(triangle)

        rows, columns = (9, 18) if spec.node_name == "helmet_hi" else (8, 8)
        grids = carrier_grids(spec, rows, columns)

        projections: dict[int, p.Projection] = {}
        uvs: dict[int, tuple[float, float]] = {}
        index_stream: list[int] = []
        cross_sections: list[dict[str, float | int]] = []
        ambiguous_solution_maximum = 0
        for side in (1, -1):
            same_side = [
                triangle for triangle in outer_triangles
                if all(positions[index][0] * side >= -1.0e-6 for index in triangle)
            ]
            grid = grids[side]
            for row in range(rows):
                v_value = row / (rows - 1)
                y_value = ymap(v_value)
                rear_z, front_z = z_limits(y_value, same_side, positions)
                cross_sections.append({
                    "front_z": front_z,
                    "rear_z": rear_z,
                    "row": row,
                    "side": side,
                    "y": y_value,
                })
                for column in range(columns):
                    u_value = column / (columns - 1)
                    progress = FRONT_MARGIN + (
                        1.0 - FRONT_MARGIN - REAR_MARGIN
                    ) * u_value ** PROGRESS_EXPONENT
                    z_value = front_z + (rear_z - front_z) * progress
                    index = grid[row][column]
                    if side > 0:
                        projection, solution_count = solve_surface(
                            y_value, z_value, side, same_side, positions, normals
                        )
                    else:
                        right = projections[grids[1][row][column]]
                        projection = p.Projection(
                            (-right.position[0], right.position[1], right.position[2]),
                            (-right.normal[0], right.normal[1], right.normal[2]),
                        )
                        solution_count = 1
                    ambiguous_solution_maximum = max(
                        ambiguous_solution_maximum, solution_count
                    )
                    projections[index] = projection
                    uvs[index] = (u_value, v_value)
                    start = spec.stream_start + index * p.STRIDE
                    output[start + 14 : start + 16] = encode_uv(u_value)
                    output[start + 22 : start + 24] = encode_uv(v_value)
            side_strips = grid_strips(grid, rows, columns, side)
            for strip in side_strips:
                if index_stream:
                    index_stream.append(0xFFFF)
                index_stream.extend(strip)

        # High has one otherwise-unused word; mirror the native terminal
        # degenerate instead of inventing padding/restart topology.
        if spec.node_name == "helmet_hi":
            index_stream.append(index_stream[-1])
        if len(index_stream) != spec.carrier_index_count:
            raise p.PatchError(
                f"{spec.node_name} carrier index stream has {len(index_stream)} "
                f"words, expected {spec.carrier_index_count}"
            )
        triangles = p._triangles(index_stream)
        expected = 536 if rows == 9 else 184
        if len(triangles) != expected:
            raise p.PatchError(
                f"{spec.node_name} grid triangle count {len(triangles)} != {expected}"
            )
        windings: list[float] = []
        areas: list[float] = []
        for triangle in triangles:
            a, b, c = (projections[index].position for index in triangle)
            geometric = p._cross(p._sub(b, a), p._sub(c, a))
            average = p._unit(tuple(
                sum(projections[index].normal[axis] for index in triangle)
                for axis in range(3)
            ))
            windings.append(p._dot(geometric, average))
            areas.append(0.5 * p._length(geometric))
        bad = sum(
            area <= p.MIN_TRIANGLE_AREA or winding <= p.MIN_WINDING_DOT
            for area, winding in zip(areas, windings)
        )
        if bad:
            raise p.PatchError(
                f"{spec.node_name} YZ grid has {bad} folded/degenerate triangles; "
                f"minimum winding {min(windings)}"
            )
        tangents = p._tangents(bytes(output), spec, projections, triangles)
        for index, projection in projections.items():
            start = spec.stream_start + index * p.STRIDE
            output[start : start + 6] = p._encode_position(projection.position, spec)
            output[start + 8 : start + 14] = p._encode_vec3(projection.normal)
            output[start + 16 : start + 22] = p._encode_vec3(tangents[index])
        index_start = spec.index_offset + spec.carrier_index_start * 2
        output[
            index_start : index_start + spec.carrier_index_count * 2
        ] = struct.pack(f">{spec.carrier_index_count}H", *index_stream)
        reports.append({
            "ambiguous_yz_solution_maximum": ambiguous_solution_maximum,
            "bounds_before_quantization": p._bounds(
                projection.position for projection in projections.values()
            ),
            "grid": [rows, columns],
            "minimum_area_before_quantization": min(areas),
            "minimum_winding_before_quantization": min(windings),
            "node": spec.node_name,
            "reserved_vertices": spec.carrier_vertex_count - len(projections),
            "row_cross_sections": cross_sections,
            "triangle_count": len(triangles),
            "used_vertices": len(projections),
        })
    payload = bytes(output)
    return payload, {
        "changed_bytes": sum(a != b for a, b in zip(source, payload)),
        "contract": {
            "actual_clearance_cm": BIAS_CM,
            "front_margin": FRONT_MARGIN,
            "rear_margin": REAR_MARGIN,
            "shell_progress_exponent": PROGRESS_EXPONENT,
            "v3_uv_unit_square": True,
            "yz_outermost_surface": True,
        },
        "lods": reports,
        "output_scne_sha256": hashlib.sha256(payload).hexdigest(),
        "schema": "candidate-c12-yzgrid-1",
        "source_scne_sha256": hashlib.sha256(source).hexdigest(),
    }


def main() -> None:
    payload, report = build()
    DESTINATION.mkdir(mode=0o700, exist_ok=True)
    (DESTINATION / "helmet00.scne").write_bytes(payload)
    (DESTINATION / "candidate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
