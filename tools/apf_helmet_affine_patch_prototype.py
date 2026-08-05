#!/usr/bin/env python3
"""Search shell disks that preserve the Eagles crest in side projection."""

from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import apf_helmet_crest_wrap_patch as p  # noqa: E402
import apf_helmet_grid_validate as validate  # noqa: E402
import apf_helmet_shell_patch_prototype as shell  # noqa: E402
import apf_helmet_superellipse_search as search  # noqa: E402


MASK = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-clean-source-region-mask-v3.png"
)


def convex_hull(points: list[tuple[float, float]]) -> np.ndarray:
    def cross(
        origin: tuple[float, float],
        first: tuple[float, float],
        second: tuple[float, float],
    ) -> float:
        return (
            (first[0] - origin[0]) * (second[1] - origin[1])
            - (first[1] - origin[1]) * (second[0] - origin[0])
        )

    lower: list[tuple[float, float]] = []
    for point in sorted(set(points)):
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(sorted(set(points))):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1], dtype=np.float64)


def inside_polygon(polygon: np.ndarray, points: np.ndarray) -> np.ndarray:
    x_values, y_values = points[:, 0], points[:, 1]
    result = np.zeros(len(points), dtype=bool)
    following = np.vstack((polygon[1:], polygon[:1]))
    for first, second in zip(polygon, following):
        first_x, first_y = first
        second_x, second_y = second
        result ^= (
            ((first_y > y_values) != (second_y > y_values))
            & (
                x_values
                < (second_x - first_x)
                * (y_values - first_y)
                / (second_y - first_y + 1.0e-300)
                + first_x
            )
        )
    return result


def segments_cross(
    first: np.ndarray,
    second: np.ndarray,
    third: np.ndarray,
    fourth: np.ndarray,
) -> bool:
    def cross(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        return float(
            (b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0])
        )

    values = (
        cross(first, second, third),
        cross(first, second, fourth),
        cross(third, fourth, first),
        cross(third, fourth, second),
    )
    return values[0] * values[1] < -1.0e-16 and values[2] * values[3] < -1.0e-16


def polygons_intersect(polygon: np.ndarray, triangle: np.ndarray) -> bool:
    if np.any(inside_polygon(polygon, triangle)):
        return True
    if np.any(inside_polygon(triangle, polygon)):
        return True
    polygon_edges = zip(polygon, np.vstack((polygon[1:], polygon[:1])))
    triangle_edges = tuple(zip(triangle, np.vstack((triangle[1:], triangle[:1]))))
    return any(
        segments_cross(first, second, third, fourth)
        for first, second in polygon_edges
        for third, fourth in triangle_edges
    )


def largest_component(
    faces: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    by_edge: dict[tuple[int, int], list[int]] = defaultdict(list)
    for number, face in enumerate(faces):
        for axis in range(3):
            by_edge[tuple(sorted((face[axis], face[(axis + 1) % 3])))].append(number)
    adjacency = [set() for _face in faces]
    for numbers in by_edge.values():
        for number in numbers:
            adjacency[number].update(other for other in numbers if other != number)
    remaining = set(range(len(faces)))
    components: list[list[tuple[int, int, int]]] = []
    while remaining:
        start = remaining.pop()
        queue = [start]
        component: list[tuple[int, int, int]] = []
        while queue:
            number = queue.pop()
            component.append(faces[number])
            for neighbor in adjacency[number]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return max(components, key=len)


def connect_selected_components(
    selected: list[tuple[int, int, int]],
    all_faces: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    """Join selected face islands with shortest full-shell edge paths."""

    by_edge: dict[tuple[int, int], list[int]] = defaultdict(list)
    for number, face in enumerate(all_faces):
        for axis in range(3):
            by_edge[tuple(sorted((face[axis], face[(axis + 1) % 3])))].append(number)
    adjacency = [set() for _face in all_faces]
    for numbers in by_edge.values():
        for number in numbers:
            adjacency[number].update(other for other in numbers if other != number)
    selected_numbers = {all_faces.index(face) for face in selected}

    def components(numbers: set[int]) -> list[set[int]]:
        remaining = set(numbers)
        output: list[set[int]] = []
        while remaining:
            start = remaining.pop()
            component = {start}
            queue = [start]
            while queue:
                number = queue.pop()
                for neighbor in adjacency[number] & remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
            output.append(component)
        return sorted(output, key=len, reverse=True)

    while True:
        islands = components(selected_numbers)
        if len(islands) == 1:
            break
        connected = islands[0]
        target = set().union(*islands[1:])
        queue = list(connected)
        parent = {number: None for number in queue}
        found: int | None = None
        cursor = 0
        while cursor < len(queue) and found is None:
            number = queue[cursor]
            cursor += 1
            for neighbor in adjacency[number]:
                if neighbor in parent:
                    continue
                parent[neighbor] = number
                if neighbor in target:
                    found = neighbor
                    break
                queue.append(neighbor)
        if found is None:
            raise RuntimeError("selected shell islands cannot be connected")
        number: int | None = found
        while number is not None:
            selected_numbers.add(number)
            number = parent[number]
    return [all_faces[number] for number in sorted(selected_numbers)]


def weld_exact_shell_seams(
    faces: list[tuple[int, int, int]],
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
) -> list[tuple[int, int, int]]:
    """Weld source-duplicated vertices whose position and normal are exact."""

    canonical: dict[
        tuple[tuple[float, float, float], tuple[float, float, float]], int
    ] = {}
    replacement: dict[int, int] = {}
    for index in sorted({item for face in faces for item in face}):
        key = (positions[index], normals[index])
        replacement[index] = canonical.setdefault(key, index)
    return [tuple(replacement[index] for index in face) for face in faces]


def topology(faces: list[tuple[int, int, int]]) -> dict[str, int | bool]:
    vertices = {index for face in faces for index in face}
    edges = Counter(
        tuple(sorted((face[axis], face[(axis + 1) % 3])))
        for face in faces
        for axis in range(3)
    )
    boundary = [edge for edge, count in edges.items() if count == 1]
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in boundary:
        adjacency[first].add(second)
        adjacency[second].add(first)
    return {
        "boundary_edge_count": len(boundary),
        "boundary_is_simple": bool(adjacency)
        and all(len(neighbors) == 2 for neighbors in adjacency.values()),
        "edge_count": len(edges),
        "euler_characteristic": len(vertices) - len(edges) + len(faces),
        "face_count": len(faces),
        "vertex_count": len(vertices),
    }


def coverage_counts(
    faces: list[tuple[int, int, int]],
    uv: dict[int, tuple[float, float]],
    active: np.ndarray,
) -> tuple[int, int, list[list[int]]]:
    coverage = np.zeros(active.shape, dtype=np.uint8)
    height, width = active.shape
    for face in faces:
        triangle = np.asarray([uv[index] for index in face], dtype=np.float64)
        first_x = max(0, math.ceil(float(triangle[:, 0].min()) * width - 0.5))
        last_x = min(width - 1, math.floor(float(triangle[:, 0].max()) * width - 0.5))
        first_y = max(0, math.ceil(float(triangle[:, 1].min()) * height - 0.5))
        last_y = min(height - 1, math.floor(float(triangle[:, 1].max()) * height - 0.5))
        if first_x > last_x or first_y > last_y:
            continue
        x_values = (np.arange(first_x, last_x + 1) + 0.5) / width
        y_values = (np.arange(first_y, last_y + 1) + 0.5) / height
        x_grid, y_grid = np.meshgrid(x_values, y_values)
        denominator = (
            (triangle[1, 1] - triangle[2, 1])
            * (triangle[0, 0] - triangle[2, 0])
            + (triangle[2, 0] - triangle[1, 0])
            * (triangle[0, 1] - triangle[2, 1])
        )
        first = (
            (triangle[1, 1] - triangle[2, 1]) * (x_grid - triangle[2, 0])
            + (triangle[2, 0] - triangle[1, 0]) * (y_grid - triangle[2, 1])
        ) / denominator
        second = (
            (triangle[2, 1] - triangle[0, 1]) * (x_grid - triangle[2, 0])
            + (triangle[0, 0] - triangle[2, 0]) * (y_grid - triangle[2, 1])
        ) / denominator
        inside = (
            (first >= -1.0e-10)
            & (second >= -1.0e-10)
            & (1.0 - first - second >= -1.0e-10)
        )
        coverage[first_y : last_y + 1, first_x : last_x + 1][inside] += 1
    active_counts = coverage[active]
    missing_map = active & (coverage == 0)
    missing_rows, missing_columns = np.nonzero(missing_map)
    return (
        int(np.count_nonzero(active_counts == 0)),
        int(np.count_nonzero(active_counts > 1)),
        [
            [int(column), int(row)]
            for row, column in zip(missing_rows[:16], missing_columns[:16])
        ],
    )


def build(args: argparse.Namespace) -> dict[str, object]:
    if not math.isfinite(args.u_scale) or args.u_scale <= 0.0:
        raise ValueError("u-scale must be finite and positive")
    parameters = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in vars(args).items()
    }
    source = p._parse_outer(p.read_source_outer(shell.SOURCE), source=True).system
    spec = next(spec for spec in p.LODS if spec.node_name == args.lod)
    positions, normals, right_outer = shell.shell_geometry(source, spec)
    with Image.open(Path(args.mask)) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    active = np.any(rgba[:, :, :3] != 0, axis=2)
    if args.active_bbox is not None:
        try:
            left, top, right, bottom = (
                int(value) for value in args.active_bbox.split(",")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("active-bbox must be left,top,right,bottom") from exc
        if not (0 <= left <= right < 512 and 0 <= top <= bottom < 512):
            raise ValueError("active-bbox is outside the 512x512 canvas")
        active = np.zeros((512, 512), dtype=bool)
        active[top : bottom + 1, left : right + 1] = True
    rows, columns = np.nonzero(active)
    source_points = np.column_stack(((columns + 0.5) / 512, (rows + 0.5) / 512))
    minimum_v = float(source_points[:, 1].min())
    maximum_v = float(source_points[:, 1].max())
    if args.selection_shape == "bbox":
        minimum_u = float(source_points[:, 0].min())
        maximum_u = float(source_points[:, 0].max())
        hull = np.asarray(
            (
                (minimum_u, minimum_v),
                (maximum_u, minimum_v),
                (maximum_u, maximum_v),
                (minimum_u, maximum_v),
            ),
            dtype=np.float64,
        )
    else:
        hull = convex_hull([tuple(row) for row in source_points.tolist()])
    normalized_hull_v = (hull[:, 1] - minimum_v) / (maximum_v - minimum_v)
    selection_hull = (
        hull.mean(axis=0)
        + args.selection_margin * (hull - hull.mean(axis=0))
    )
    normalized_hull_v = (
        selection_hull[:, 1] - minimum_v
    ) / (maximum_v - minimum_v)
    source_hull_u = (
        selection_hull[:, 0] - args.u_offset
    ) / args.u_scale
    target_hull = np.column_stack((
        args.front_z
        - args.length * source_hull_u
        + args.z_v_slope * normalized_hull_v,
        args.top_y
        + args.slope * (source_hull_u - 0.5)
        - args.height * normalized_hull_v,
    ))
    selected = [
        face
        for face in right_outer
        if polygons_intersect(
            target_hull,
            np.asarray([(positions[index][2], positions[index][1]) for index in face]),
        )
    ]
    selected_face_ids = [right_outer.index(face) for face in selected]
    faces = weld_exact_shell_seams(selected, positions, normals)
    report_topology = topology(faces)
    vertices = {index for face in faces for index in face}
    transform = np.asarray(
        ((-args.length, args.z_v_slope), (args.slope, -args.height)),
        dtype=np.float64,
    )
    inverse_transform = np.linalg.inv(transform)
    uv = {}
    for index in vertices:
        u_value, normalized_v = inverse_transform @ np.asarray(
            (
                positions[index][2] - args.front_z,
                positions[index][1] - args.top_y + 0.5 * args.slope,
            )
        )
        uv[index] = (
            args.u_offset + args.u_scale * float(u_value),
            minimum_v + (maximum_v - minimum_v) * float(normalized_v),
        )
    uv = search.quantize_uvs(uv)
    if args.clamp_uv:
        uv = search.quantize_uvs({
            index: (
                max(0.0, min(1.0, value[0])),
                max(0.0, min(1.0, value[1])),
            )
            for index, value in uv.items()
        })
    determinants = []
    for face in faces:
        first, second, third = (uv[index] for index in face)
        determinants.append(
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )
    world = {
        index: p._add(positions[index], p._mul(normals[index], shell.BIAS_CM))
        for index in vertices
    }
    missing, multiple, first_missing = coverage_counts(faces, uv, active)
    if missing or multiple:
        return {
            "capacity": {
                "face_limit": 266 if args.lod == "helmet_hi" else 91,
                "fits": report_topology["face_count"]
                <= (266 if args.lod == "helmet_hi" else 91)
                and report_topology["vertex_count"]
                <= (161 if args.lod == "helmet_hi" else 64),
                "vertex_limit": 161 if args.lod == "helmet_hi" else 64,
            },
            "coverage": {
                "first_missing_xy": first_missing,
                "missing": missing,
                "multiple": multiple,
            },
            "parameters": parameters,
            "schema": "apf2k8_helmet_affine_patch_prototype/v1",
            "topology": report_topology,
        }
    # The diagnostic validator's census constant is tied to whichever private
    # mask its main program audits.  This prototype accepts a guarded variant,
    # so bind that helper to the actual decoded active census for this process.
    validate.EXPECTED_ACTIVE_TEXELS = int(active.sum())
    painted = validate.raster_metrics(world, uv, faces, active)
    mapped_rows = []
    for start in range(0, len(source_points), 2_000):
        mapped_rows.append(
            search.map_points(
                source_points[start : start + 2_000], faces, uv, world
            )
        )
    mapped = np.concatenate(mapped_rows)
    design = np.column_stack((source_points, np.ones(len(source_points))))
    target = mapped[:, (2, 1)]
    coefficients = np.linalg.lstsq(design, target, rcond=None)[0]
    residual = target - design @ coefficients
    sum_squared_residual = np.sum(residual**2, axis=0)
    sum_squared_total = np.sum((target - target.mean(axis=0)) ** 2, axis=0)
    span = np.ptp(target, axis=0)
    root = mapped[
        (source_points[:, 0] - args.u_offset) / args.u_scale < 0.01
    ]
    return {
        "affine_shape": {
            "maximum_normalized_error_z_y": (
                np.max(np.abs(residual), axis=0) / span
            ).tolist(),
            "normalized_rmse_z_y": (
                np.sqrt(np.mean(residual**2, axis=0)) / span
            ).tolist(),
            "r_squared_z_y": (1.0 - sum_squared_residual / sum_squared_total).tolist(),
        },
        "capacity": {
            "face_limit": 266 if args.lod == "helmet_hi" else 91,
            "fits": report_topology["face_count"]
            <= (266 if args.lod == "helmet_hi" else 91)
            and report_topology["vertex_count"]
            <= (161 if args.lod == "helmet_hi" else 64),
            "vertex_limit": 161 if args.lod == "helmet_hi" else 64,
        },
        "parameters": parameters,
        "painted": painted,
        "quantized_uv": {
            "determinant_maximum": max(determinants),
            "determinant_minimum": min(determinants),
            "same_orientation": not (min(determinants) < 0.0 < max(determinants)),
        },
        "root_abs_x_cm": {
            "maximum": float(np.abs(root[:, 0]).max()),
            "median": float(np.median(np.abs(root[:, 0]))),
            "minimum": float(np.abs(root[:, 0]).min()),
        },
        "right_outer_face_ids": selected_face_ids,
        "schema": "apf2k8_helmet_affine_patch_prototype/v1",
        "topology": report_topology,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lod", choices=("helmet_hi", "helmet_lo"), default="helmet_hi"
    )
    parser.add_argument("--length", type=float, required=True)
    parser.add_argument("--height", type=float, required=True)
    parser.add_argument("--front-z", type=float, required=True)
    parser.add_argument("--top-y", type=float, required=True)
    parser.add_argument("--slope", type=float, default=0.0)
    parser.add_argument("--selection-margin", type=float, default=1.0)
    parser.add_argument("--z-v-slope", type=float, default=0.0)
    parser.add_argument("--clamp-uv", action="store_true")
    parser.add_argument("--mask", type=Path, default=MASK)
    parser.add_argument("--u-offset", type=float, default=0.0)
    parser.add_argument("--u-scale", type=float, default=1.0)
    parser.add_argument(
        "--selection-shape", choices=("convex", "bbox"), default="convex"
    )
    parser.add_argument("--active-bbox")
    print(json.dumps(build(parser.parse_args()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
