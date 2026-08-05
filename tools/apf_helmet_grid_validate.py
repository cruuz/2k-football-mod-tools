#!/usr/bin/env python3
"""Fail-closed gates for the shared-LOD affine helmet shell candidate."""

from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_wrap_patch as p  # noqa: E402
import apf_helmet_superellipse_search as search  # noqa: E402


SOURCE = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-editor-proof-v17-full-u-pregeometry/0A"
)
CANDIDATE = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-v22-guarded-affine-shell-candidate-4/helmet00.scne"
)
MASK = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-clean-source-region-mask-v4-guarded.png"
)
EXPECTED_MASK_PNG_SHA256 = (
    "4913aa6cf62fe6f96a913001ed5ad9d0356a109412e3f1b432fc0fd81eb5750a"
)
EXPECTED_MASK_RGBA_SHA256 = (
    "cf937ff797e4e5ae94b5c456babf298fa20436716b6ef2b708faac70b293d40e"
)
EXPECTED_ACTIVE_TEXELS = 42_800
EXPECTED_SCNE_SHA256 = "ef04ef4418e4df555d9418db2f6083c7852802428aae0a15dbf81518bff3b5ef"
EXPECTED_SIDE_VERTICES = {"helmet_hi": 161, "helmet_lo": 56}
EXPECTED_SIDE_TRIANGLES = {"helmet_hi": 258, "helmet_lo": 78}
LEFT_START_OFFSET = {"helmet_hi": 163, "helmet_lo": 64}
GUARD_U_OFFSET = 0.125
GUARD_U_SCALE = 0.75


class GateError(RuntimeError):
    pass


def require(value: object, message: str) -> None:
    if not value:
        raise GateError(message)


def dot(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return sum(a * b for a, b in zip(first, second))


def sub(first: tuple[float, float, float], second: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(first[axis] - second[axis] for axis in range(3))  # type: ignore[return-value]


def cross(first: tuple[float, float, float], second: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def length(vector: tuple[float, float, float]) -> float:
    return math.sqrt(dot(vector, vector))


def unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = length(vector)
    require(math.isfinite(magnitude) and magnitude > 1.0e-12, "zero/non-finite vector")
    return tuple(value / magnitude for value in vector)  # type: ignore[return-value]


def closest_point(
    point: tuple[float, float, float],
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    third: tuple[float, float, float],
) -> tuple[float, float, float]:
    ab, ac, ap = sub(second, first), sub(third, first), sub(point, first)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return first
    bp = sub(point, second)
    d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return second
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        factor = d1 / (d1 - d3)
        return tuple(first[i] + factor * ab[i] for i in range(3))  # type: ignore[return-value]
    cp = sub(point, third)
    d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return third
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        factor = d2 / (d2 - d6)
        return tuple(first[i] + factor * ac[i] for i in range(3))  # type: ignore[return-value]
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and d4 - d3 >= 0.0 and d5 - d6 >= 0.0:
        factor = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return tuple(second[i] + factor * (third[i] - second[i]) for i in range(3))  # type: ignore[return-value]
    denominator = 1.0 / (va + vb + vc)
    v_value, w_value = vb * denominator, vc * denominator
    return tuple(first[i] + ab[i] * v_value + ac[i] * w_value for i in range(3))  # type: ignore[return-value]


def condition(
    positions: dict[int, tuple[float, float, float]],
    uvs: dict[int, tuple[float, float]],
    triangle: tuple[int, int, int],
) -> float:
    a, b, c = triangle
    pa, pb, pc = positions[a], positions[b], positions[c]
    ua, ub, uc = uvs[a], uvs[b], uvs[c]
    du1, dv1 = ub[0] - ua[0], ub[1] - ua[1]
    du2, dv2 = uc[0] - ua[0], uc[1] - ua[1]
    determinant = du1 * dv2 - du2 * dv1
    require(abs(determinant) > 1.0e-12, "collapsed UV triangle")
    xu = tuple(
        ((pb[i] - pa[i]) * dv2 - (pc[i] - pa[i]) * dv1) / determinant
        for i in range(3)
    )
    xv = tuple(
        (-(pb[i] - pa[i]) * du2 + (pc[i] - pa[i]) * du1) / determinant
        for i in range(3)
    )
    g11, g22, g12 = dot(xu, xu), dot(xv, xv), dot(xu, xv)
    trace = g11 + g22
    discriminant = max(0.0, trace * trace - 4.0 * (g11 * g22 - g12 * g12))
    largest = (trace + math.sqrt(discriminant)) / 2.0
    smallest = (trace - math.sqrt(discriminant)) / 2.0
    require(smallest > 1.0e-12, "collapsed world Jacobian")
    return math.sqrt(largest / smallest)


def aabb(triangle: tuple[tuple[float, float, float], ...]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    return (
        tuple(min(point[i] for point in triangle) for i in range(3)),
        tuple(max(point[i] for point in triangle) for i in range(3)),
    )


def boxes_overlap(first: tuple[tuple[float, ...], tuple[float, ...]], second: tuple[tuple[float, ...], tuple[float, ...]]) -> bool:
    epsilon = 1.0e-7
    return all(first[0][i] <= second[1][i] + epsilon and second[0][i] <= first[1][i] + epsilon for i in range(3))


def segment_triangle(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    triangle: tuple[tuple[float, float, float], ...],
) -> bool:
    """Moller-Trumbore segment/triangle test; coplanar cases are handled by separation gates."""

    epsilon = 1.0e-8
    direction = sub(end, start)
    edge1, edge2 = sub(triangle[1], triangle[0]), sub(triangle[2], triangle[0])
    h = cross(direction, edge2)
    determinant = dot(edge1, h)
    if abs(determinant) <= epsilon:
        return False
    inverse = 1.0 / determinant
    s = sub(start, triangle[0])
    u_value = inverse * dot(s, h)
    if u_value < -epsilon or u_value > 1.0 + epsilon:
        return False
    q = cross(s, edge1)
    v_value = inverse * dot(direction, q)
    if v_value < -epsilon or u_value + v_value > 1.0 + epsilon:
        return False
    distance = inverse * dot(edge2, q)
    return epsilon < distance < 1.0 - epsilon


def triangles_intersect(
    first: tuple[tuple[float, float, float], ...],
    second: tuple[tuple[float, float, float], ...],
) -> bool:
    if not boxes_overlap(aabb(first), aabb(second)):
        return False
    edges = ((0, 1), (1, 2), (2, 0))
    return any(segment_triangle(first[a], first[b], second) for a, b in edges) or any(
        segment_triangle(second[a], second[b], first) for a, b in edges
    )


def projected_components(
    painted_triangles: set[tuple[int, int, int]],
) -> list[int]:
    by_vertex: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for triangle in painted_triangles:
        for vertex in triangle:
            by_vertex[vertex].append(triangle)
    remaining = set(painted_triangles)
    sizes: list[int] = []
    while remaining:
        seed = remaining.pop()
        queue = deque((seed,))
        size = 0
        while queue:
            triangle = queue.popleft()
            size += 1
            for vertex in triangle:
                for neighbor in by_vertex[vertex]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        queue.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def raster_metrics(
    positions: dict[int, tuple[float, float, float]],
    uvs: dict[int, tuple[float, float]],
    triangles: list[tuple[int, int, int]],
    active: np.ndarray,
) -> dict[str, object]:
    height, width = active.shape
    coverage = np.zeros((height, width), dtype=np.uint8)
    owner = np.full((height, width), -1, dtype=np.int32)
    barycentric_owner: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    for number, triangle in enumerate(triangles):
        uv = np.array([uvs[index] for index in triangle], dtype=np.float64)
        first_x = max(0, math.ceil(float(uv[:, 0].min()) * width - 0.5))
        last_x = min(width - 1, math.floor(float(uv[:, 0].max()) * width - 0.5))
        first_y = max(0, math.ceil(float(uv[:, 1].min()) * height - 0.5))
        last_y = min(height - 1, math.floor(float(uv[:, 1].max()) * height - 0.5))
        if first_x > last_x or first_y > last_y:
            continue
        xs = (np.arange(first_x, last_x + 1, dtype=np.float64) + 0.5) / width
        ys = (np.arange(first_y, last_y + 1, dtype=np.float64) + 0.5) / height
        x_grid, y_grid = np.meshgrid(xs, ys)
        denominator = (
            (uv[1, 1] - uv[2, 1]) * (uv[0, 0] - uv[2, 0])
            + (uv[2, 0] - uv[1, 0]) * (uv[0, 1] - uv[2, 1])
        )
        require(abs(float(denominator)) > 1.0e-12, "raster UV triangle collapsed")
        first = (
            (uv[1, 1] - uv[2, 1]) * (x_grid - uv[2, 0])
            + (uv[2, 0] - uv[1, 0]) * (y_grid - uv[2, 1])
        ) / denominator
        second = (
            (uv[2, 1] - uv[0, 1]) * (x_grid - uv[2, 0])
            + (uv[0, 0] - uv[2, 0]) * (y_grid - uv[2, 1])
        ) / denominator
        third = 1.0 - first - second
        inside = (first >= -1.0e-10) & (second >= -1.0e-10) & (third >= -1.0e-10)
        if not inside.any():
            continue
        target = np.s_[first_y : last_y + 1, first_x : last_x + 1]
        coverage[target][inside] += 1
        owner[target][inside] = number
        barycentric_owner[number] = (inside, first, second, third, np.array((first_y, first_x)))

    active_counts = coverage[active]
    require(active_counts.size == EXPECTED_ACTIVE_TEXELS, "active texel census differs")
    missing = int(np.count_nonzero(active_counts == 0))
    duplicate = int(np.count_nonzero(active_counts > 1))
    require(missing == 0 and duplicate == 0, f"painted texels map missing={missing}, duplicate={duplicate}")

    painted_numbers = set(int(value) for value in np.unique(owner[active]))
    require(-1 not in painted_numbers, "active texel lacks triangle owner")
    painted_triangles = {triangles[number] for number in painted_numbers}
    world_rows: list[np.ndarray] = []
    for number in sorted(painted_numbers):
        ys, xs = np.nonzero(active & (owner == number))
        if not len(xs):
            continue
        uv = np.column_stack(((xs + 0.5) / width, (ys + 0.5) / height))
        triangle = triangles[number]
        tri_uv = np.array([uvs[index] for index in triangle], dtype=np.float64)
        denominator = (
            (tri_uv[1, 1] - tri_uv[2, 1]) * (tri_uv[0, 0] - tri_uv[2, 0])
            + (tri_uv[2, 0] - tri_uv[1, 0]) * (tri_uv[0, 1] - tri_uv[2, 1])
        )
        first = (
            (tri_uv[1, 1] - tri_uv[2, 1]) * (uv[:, 0] - tri_uv[2, 0])
            + (tri_uv[2, 0] - tri_uv[1, 0]) * (uv[:, 1] - tri_uv[2, 1])
        ) / denominator
        second = (
            (tri_uv[2, 1] - tri_uv[0, 1]) * (uv[:, 0] - tri_uv[2, 0])
            + (tri_uv[0, 0] - tri_uv[2, 0]) * (uv[:, 1] - tri_uv[2, 1])
        ) / denominator
        third = 1.0 - first - second
        tri_world = np.array([positions[index] for index in triangle], dtype=np.float64)
        world_rows.append(first[:, None] * tri_world[0] + second[:, None] * tri_world[1] + third[:, None] * tri_world[2])
    world = np.concatenate(world_rows, axis=0)
    require(len(world) == EXPECTED_ACTIVE_TEXELS, "world-painted texel census differs")
    components = projected_components(painted_triangles)
    require(len(components) == 1, f"painted carrier is fragmented into {components}")
    all_conditions = [condition(positions, uvs, triangle) for triangle in triangles]
    painted_conditions = [condition(positions, uvs, triangle) for triangle in painted_triangles]
    return {
        "bounds_cm": {
            "minimum": world.min(axis=0).tolist(),
            "maximum": world.max(axis=0).tolist(),
        },
        "dominant_component_triangle_fraction": components[0] / len(painted_triangles),
        "maximum_all_triangle_condition": max(all_conditions),
        "maximum_painted_triangle_condition": max(painted_conditions),
        "painted_triangle_count": len(painted_triangles),
        "painted_texels_mapped_exactly_once": int(len(world)),
        "rear_percentile_z_cm": float(np.quantile(world[:, 2], 0.01)),
        "seam_percentile_abs_x_cm": float(np.quantile(np.abs(world[:, 0]), 0.01)),
        "side_projection_height_cm": float(np.ptp(world[:, 1])),
        "side_projection_length_cm": float(np.ptp(world[:, 2])),
    }


def affine_shape_metrics(
    positions: dict[int, tuple[float, float, float]],
    uvs: dict[int, tuple[float, float]],
    triangles: list[tuple[int, int, int]],
    sampling_points: np.ndarray,
    design_points: np.ndarray,
) -> dict[str, object]:
    """Prove the painted wing remains affine in side projection after encoding."""

    mapped_rows = [
        search.map_points(sampling_points[start : start + 2_000], triangles, uvs, positions)
        for start in range(0, len(sampling_points), 2_000)
    ]
    mapped = np.concatenate(mapped_rows)
    require(len(mapped) == EXPECTED_ACTIVE_TEXELS, "affine map census differs")
    design = np.column_stack((design_points, np.ones(len(design_points))))
    target = mapped[:, (2, 1)]
    coefficients = np.linalg.lstsq(design, target, rcond=None)[0]
    residual = target - design @ coefficients
    sum_squared_residual = np.sum(residual**2, axis=0)
    sum_squared_total = np.sum((target - target.mean(axis=0)) ** 2, axis=0)
    span = np.ptp(target, axis=0)
    normalized_rmse = np.sqrt(np.mean(residual**2, axis=0)) / span
    normalized_maximum = np.max(np.abs(residual), axis=0) / span
    r_squared = 1.0 - sum_squared_residual / sum_squared_total
    root = np.abs(mapped[design_points[:, 0] < 0.01, 0])
    require(len(root) > 0, "affine root sample is empty")
    require(bool(np.all(r_squared > 0.95)), f"affine R-squared gate failed: {r_squared}")
    require(
        bool(np.all(normalized_rmse < 0.05)),
        f"affine normalized-RMSE gate failed: {normalized_rmse}",
    )
    require(
        float(np.median(root)) < 2.6,
        f"painted root misses crown stripe: median={np.median(root):.9f}",
    )
    require(
        float(root.max()) < 3.2,
        f"painted root does not stay near crown stripe: max={root.max():.9f}",
    )
    return {
        "maximum_normalized_error_z_y": normalized_maximum.tolist(),
        "normalized_rmse_z_y": normalized_rmse.tolist(),
        "r_squared_z_y": r_squared.tolist(),
        "root_abs_x_cm": {
            "maximum": float(root.max()),
            "median": float(np.median(root)),
            "minimum": float(root.min()),
            "percentile_10": float(np.quantile(root, 0.10)),
        },
    }


def build_report() -> dict[str, object]:
    source = p._parse_outer(p.read_source_outer(SOURCE), source=True).system
    output = CANDIDATE.read_bytes()
    require(len(source) == len(output), "SCNE length drift")
    require(
        hashlib.sha256(output).hexdigest() == EXPECTED_SCNE_SHA256,
        "candidate SCNE hash drift",
    )
    mask_png = MASK.read_bytes()
    require(hashlib.sha256(mask_png).hexdigest() == EXPECTED_MASK_PNG_SHA256, "mask PNG hash drift")
    with Image.open(MASK) as image:
        rgba = image.convert("RGBA")
        require(rgba.size == (512, 512), "mask dimensions differ")
        rgba_bytes = rgba.tobytes()
        active = np.any(np.asarray(rgba, dtype=np.uint8)[:, :, :3] != 0, axis=2)
    require(hashlib.sha256(rgba_bytes).hexdigest() == EXPECTED_MASK_RGBA_SHA256, "mask RGBA hash drift")
    require(int(active.sum()) == EXPECTED_ACTIVE_TEXELS, "mask active count drift")
    active_rows, active_columns = np.nonzero(active)
    guarded_points = np.column_stack(
        ((active_columns + 0.5) / 512, (active_rows + 0.5) / 512)
    )
    source_points = guarded_points.copy()
    source_points[:, 0] = (
        source_points[:, 0] - GUARD_U_OFFSET
    ) / GUARD_U_SCALE

    nodes = p._scene_nodes(source)
    allowed: set[int] = set()
    lod_reports: list[dict[str, object]] = []
    high_low_projection: dict[str, dict[str, object]] = {}
    for spec in p.LODS:
        p._validate_layout(source, spec, nodes[spec.node_index])
        per_side = EXPECTED_SIDE_VERTICES[spec.node_name]
        left_start = spec.carrier_vertex_start + LEFT_START_OFFSET[spec.node_name]
        side_ids = {
            1: list(range(spec.carrier_vertex_start, spec.carrier_vertex_start + per_side)),
            -1: list(range(left_start, left_start + per_side)),
        }
        reserved = set(
            range(
                spec.carrier_vertex_start,
                spec.carrier_vertex_start + spec.carrier_vertex_count,
            )
        ) - set(side_ids[1]) - set(side_ids[-1])
        used = set(side_ids[1]) | set(side_ids[-1])
        require(len(used) == per_side * 2, f"{spec.node_name} used-ID count differs")
        for index in used:
            start = spec.stream_start + index * p.STRIDE
            allowed.update(range(start, start + 6))
            allowed.update(range(start + 8, start + 24))
        index_start = spec.index_offset + spec.carrier_index_start * 2
        index_end = index_start + spec.carrier_index_count * 2
        allowed.update(range(index_start, index_end))

        require(source[spec.draw_record_offset : spec.draw_record_offset + 0x90] == output[spec.draw_record_offset : spec.draw_record_offset + 0x90], f"{spec.node_name} draw records changed")
        require(source[spec.index_offset:index_start] == output[spec.index_offset:index_start], f"{spec.node_name} pre-carrier indices changed")
        require(source[index_end : spec.index_offset + spec.index_count * 2] == output[index_end : spec.index_offset + spec.index_count * 2], f"{spec.node_name} post-carrier indices changed")
        for index in reserved:
            start = spec.stream_start + index * p.STRIDE
            require(source[start:start + p.STRIDE] == output[start:start + p.STRIDE], f"{spec.node_name} reserved vertex changed")
        for index in used:
            start = spec.stream_start + index * p.STRIDE
            require(source[start + 6:start + 8] == output[start + 6:start + 8], f"{spec.node_name} POSITION.w changed")
            require(source[start + 24:start + 32] == output[start + 24:start + 32], f"{spec.node_name} blend lanes changed")

        indices = list(struct.unpack_from(f">{spec.carrier_index_count}H", output, index_start))
        triangles = p._triangles(indices)
        expected_side_triangles = EXPECTED_SIDE_TRIANGLES[spec.node_name]
        expected_triangles = expected_side_triangles * 2
        require(len(triangles) == expected_triangles, f"{spec.node_name} triangle count differs")
        require(all(set(triangle) <= used for triangle in triangles), f"{spec.node_name} triangle escaped used IDs")
        require(not any(set(triangle) & reserved for triangle in triangles), f"{spec.node_name} reserved vertex referenced")
        restart_count = indices.count(0xFFFF)
        expected_restarts = 125 if spec.node_name == "helmet_hi" else 19
        require(restart_count == expected_restarts, f"{spec.node_name} restart count differs")
        require(
            indices[-1] == indices[-2] == indices[-3] != 0xFFFF,
            f"{spec.node_name} terminal native degenerates differ",
        )

        positions = {index: p._decode_position(output, spec, index) for index in used}
        normals = {index: unit(p._decode_vec3(output, spec.stream_start + index * p.STRIDE + 8)) for index in used}
        tangents = {index: unit(p._decode_vec3(output, spec.stream_start + index * p.STRIDE + 16)) for index in used}
        uvs = {index: p._uv(output, spec, index) for index in used}
        uv_rows = np.asarray(list(uvs.values()), dtype=np.float64)
        require(
            float(uv_rows.min()) >= 0.0 and float(uv_rows.max()) <= 1.0,
            f"{spec.node_name} guarded UV escaped [0,1]: "
            f"{uv_rows.min(axis=0)}..{uv_rows.max(axis=0)}",
        )
        areas: list[float] = []
        windings: list[float] = []
        for triangle in triangles:
            a, b, c = (positions[index] for index in triangle)
            geometric = cross(sub(b, a), sub(c, a))
            average = unit(tuple(sum(normals[index][axis] for index in triangle) for axis in range(3)))
            areas.append(length(geometric) / 2.0)
            windings.append(dot(geometric, average))
        require(min(areas) > 1.0e-4, f"{spec.node_name} quantized degenerate triangle")
        require(min(windings) > 1.0e-4, f"{spec.node_name} quantized flipped triangle")
        orthogonality = max(abs(dot(normals[index], tangents[index])) for index in used)
        require(orthogonality <= 2.0e-3, f"{spec.node_name} tangent is not orthogonal")

        # Both shell-native side patches must be exact mirrors after quantization.
        symmetry_errors: list[float] = []
        normal_errors: list[float] = []
        uv_errors: list[float] = []
        for right, left in zip(side_ids[1], side_ids[-1]):
            symmetry_errors.append(max(abs(positions[right][0] + positions[left][0]), abs(positions[right][1] - positions[left][1]), abs(positions[right][2] - positions[left][2])))
            normal_errors.append(max(abs(normals[right][0] + normals[left][0]), abs(normals[right][1] - normals[left][1]), abs(normals[right][2] - normals[left][2])))
            uv_errors.append(max(abs(uvs[right][axis] - uvs[left][axis]) for axis in range(2)))
        require(max(symmetry_errors) <= 1.0e-9, f"{spec.node_name} position symmetry drift")
        require(max(normal_errors) <= 1.0e-9, f"{spec.node_name} normal symmetry drift")
        require(max(uv_errors) <= 1.0e-9, f"{spec.node_name} UV symmetry drift")

        source_positions = [p._decode_position(source, spec, index) for index in range(spec.vertex_count)]
        source_normals = [unit(p._decode_vec3(source, spec.stream_start + index * p.STRIDE + 8)) for index in range(spec.vertex_count)]
        source_indices = p._indices(source, spec)
        shell_indices = source_indices[spec.shell_index_start : spec.shell_index_start + spec.shell_index_count]
        shell_triangles_all = p._triangles(shell_indices)
        shell_triangles = []
        for triangle in shell_triangles_all:
            center = tuple(sum(source_positions[index][axis] for index in triangle) / 3.0 for axis in range(3))
            average = tuple(sum(source_normals[index][axis] for index in triangle) for axis in range(3))
            radial = (center[0], center[1] - spec.center[1], center[2] - spec.center[2])
            if dot(average, radial) > 0.0:
                shell_triangles.append(triangle)
        shell_world = [tuple(source_positions[index] for index in triangle) for triangle in shell_triangles]
        clearance: list[float] = []
        clearance_sign: list[float] = []
        for index in used:
            point = positions[index]
            closest = min(
                (closest_point(point, *triangle) for triangle in shell_world),
                key=lambda candidate: length(sub(point, candidate)),
            )
            delta = sub(point, closest)
            clearance.append(length(delta))
            clearance_sign.append(dot(delta, normals[index]))
        require(
            min(clearance) >= 0.115,
            f"{spec.node_name} shell clearance too small: {min(clearance):.9f}",
        )
        require(
            max(clearance) <= 0.165,
            f"{spec.node_name} shell clearance too large: {max(clearance):.9f}",
        )
        require(
            min(clearance_sign) > 0.11,
            f"{spec.node_name} carrier is not uniformly outward: "
            f"{min(clearance_sign):.9f}",
        )

        carrier_world = [tuple(positions[index] for index in triangle) for triangle in triangles]
        shell_boxes = [aabb(triangle) for triangle in shell_world]
        carrier_shell_intersections = 0
        first_carrier_shell_intersections: list[dict[str, object]] = []
        for carrier_number, carrier_triangle in enumerate(carrier_world):
            carrier_box = aabb(carrier_triangle)
            for shell_number, (shell_triangle, shell_box) in enumerate(zip(shell_world, shell_boxes)):
                if boxes_overlap(carrier_box, shell_box) and triangles_intersect(carrier_triangle, shell_triangle):
                    carrier_shell_intersections += 1
                    if len(first_carrier_shell_intersections) < 12:
                        first_carrier_shell_intersections.append({
                            "carrier_triangle": list(triangles[carrier_number]),
                            "shell_triangle": list(shell_triangles[shell_number]),
                        })
        require(
            carrier_shell_intersections == 0,
            f"{spec.node_name} intersects shell {carrier_shell_intersections} times: "
            f"{first_carrier_shell_intersections}",
        )
        self_intersections = 0
        for first_number, first_triangle in enumerate(triangles):
            first_world = carrier_world[first_number]
            for second_number in range(first_number + 1, len(triangles)):
                second_triangle = triangles[second_number]
                if set(first_triangle) & set(second_triangle):
                    continue
                if triangles_intersect(first_world, carrier_world[second_number]):
                    self_intersections += 1
        require(self_intersections == 0, f"{spec.node_name} self-intersects")

        side_reports: dict[str, object] = {}
        for side in (1, -1):
            side_set = set(side_ids[side])
            side_triangles = [triangle for triangle in triangles if set(triangle) <= side_set]
            require(len(side_triangles) == expected_side_triangles, f"{spec.node_name} side triangle count differs")
            metrics = raster_metrics(positions, uvs, side_triangles, active)
            shape = affine_shape_metrics(
                positions, uvs, side_triangles, guarded_points, source_points
            )
            require(metrics["dominant_component_triangle_fraction"] == 1.0, f"{spec.node_name} painted component is fragmented")
            require(
                float(metrics["bounds_cm"]["minimum"][2]) < -8.75,  # type: ignore[index]
                f"{spec.node_name} dominant art misses rear shell",
            )
            require(
                float(metrics["bounds_cm"]["maximum"][2]) > 12.8,  # type: ignore[index]
                f"{spec.node_name} dominant art misses front crown stripe",
            )
            require(
                float(metrics["seam_percentile_abs_x_cm"]) < 3.2,
                f"{spec.node_name} dominant art misses crown seam",
            )
            require(
                float(metrics["side_projection_length_cm"]) > 21.7,
                f"{spec.node_name} side projection is too short",
            )
            require(
                float(metrics["side_projection_height_cm"]) > 8.0,
                f"{spec.node_name} side projection is too shallow",
            )
            metrics["affine_shape"] = shape
            side_reports["right" if side > 0 else "left"] = metrics
        high_low_projection[spec.node_name] = side_reports["right"]  # type: ignore[assignment]

        lod_reports.append({
            "carrier_index_sha256": hashlib.sha256(output[index_start:index_end]).hexdigest(),
            "carrier_shell_intersection_count": carrier_shell_intersections,
            "carrier_triangle_count": len(triangles),
            "maximum_normal_tangent_dot": orthogonality,
            "maximum_shell_clearance_cm": max(clearance),
            "minimum_shell_clearance_cm": min(clearance),
            "minimum_triangle_area": min(areas),
            "minimum_winding_dot": min(windings),
            "node": spec.node_name,
            "painted": side_reports,
            "restart_count": restart_count,
            "self_intersection_count": self_intersections,
            "guarded_uv_domain": {
                "maximum": uv_rows.max(axis=0).tolist(),
                "minimum": uv_rows.min(axis=0).tolist(),
            },
            "used_vertex_count": len(used),
        })

    changed = {index for index, pair in enumerate(zip(source, output)) if pair[0] != pair[1]}
    require(bool(changed), "candidate made no changes")
    require(changed <= allowed, f"{len(changed - allowed)} changed bytes escape authorized spans")
    high = high_low_projection["helmet_hi"]
    low = high_low_projection["helmet_lo"]
    for field in ("side_projection_length_cm", "side_projection_height_cm"):
        first, second = float(high[field]), float(low[field])
        denominator = max(abs(first), abs(second), 1.0e-9)
        require(abs(first - second) / denominator < 0.02, f"high/low painted projection differs at {field}")
    return {
        "authorized_changed_byte_count": len(changed),
        "candidate_scne_sha256": hashlib.sha256(output).hexdigest(),
        "exact_once_active_texels_per_side_per_lod": EXPECTED_ACTIVE_TEXELS,
        "lods": lod_reports,
        "mask_png_sha256": EXPECTED_MASK_PNG_SHA256,
        "mask_rgba_sha256": EXPECTED_MASK_RGBA_SHA256,
        "schema": "apf2k8_helmet_shell_candidate_validate/v1",
        "verified": True,
    }


def main() -> None:
    report = build_report()
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (CANDIDATE.parent / "validation.json").write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
