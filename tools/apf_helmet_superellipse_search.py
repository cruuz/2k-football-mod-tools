#!/usr/bin/env python3
"""Search strictly-convex UV boundary alignments for the Eagles shell patch."""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_wrap_patch as p  # noqa: E402
import apf_helmet_grid_validate as validate  # noqa: E402
import apf_helmet_shell_patch_prototype as shell  # noqa: E402


SUPERELLIPSE_N = 16.0
SUPERELLIPSE_A = 0.5
# The continuous n=16 curve needs b>=.30315.  The extra chord margin keeps
# the 35-vertex low-LOD boundary outside every active pixel center too.
SUPERELLIPSE_B = 0.315
SAMPLE_STEP = 53
SHORTLIST_COUNT = 16


def quantize_uvs(
    values: dict[int, tuple[float, float]],
) -> dict[int, tuple[float, float]]:
    return {
        index: (
            round(uv[0] / 2.0 * 32767) * 2.0 / 32767,
            round(uv[1] / 2.0 * 32767) * 2.0 / 32767,
        )
        for index, uv in values.items()
    }


def harmonic_operator(
    faces: list[tuple[int, int, int]], boundary: list[int],
) -> tuple[list[int], np.ndarray]:
    boundary_set = set(boundary)
    vertices = sorted({index for triangle in faces for index in triangle})
    interior = [index for index in vertices if index not in boundary_set]
    neighbors: dict[int, set[int]] = defaultdict(set)
    for triangle in faces:
        for axis in range(3):
            first, second = triangle[axis], triangle[(axis + 1) % 3]
            neighbors[first].add(second)
            neighbors[second].add(first)
    interior_row = {vertex: number for number, vertex in enumerate(interior)}
    boundary_row = {vertex: number for number, vertex in enumerate(boundary)}
    matrix = np.zeros((len(interior), len(interior)), dtype=np.float64)
    right = np.zeros((len(interior), len(boundary)), dtype=np.float64)
    for vertex in interior:
        row = interior_row[vertex]
        matrix[row, row] = len(neighbors[vertex])
        for neighbor in neighbors[vertex]:
            if neighbor in interior_row:
                matrix[row, interior_row[neighbor]] -= 1.0
            else:
                right[row, boundary_row[neighbor]] += 1.0
    return interior, np.linalg.solve(matrix, right)


def superellipse_boundary(
    boundary: list[int],
    positions: list[tuple[float, float, float]],
    start: int,
    reverse: bool,
) -> dict[int, tuple[float, float]]:
    count = len(boundary)
    direction = -1 if reverse else 1
    ordered = [boundary[(start + direction * index) % count] for index in range(count)]
    distances = [0.0]
    for first, second in zip(ordered, ordered[1:] + ordered[:1]):
        distances.append(
            distances[-1] + p._length(p._sub(positions[second], positions[first]))
        )
    total = distances[-1]
    output: dict[int, tuple[float, float]] = {}
    power = 2.0 / SUPERELLIPSE_N
    for index, distance in zip(ordered, distances):
        angle = 2.0 * math.pi * distance / total
        cosine, sine = math.cos(angle), math.sin(angle)
        output[index] = (
            0.5 + SUPERELLIPSE_A * math.copysign(abs(cosine) ** power, cosine),
            0.5 + SUPERELLIPSE_B * math.copysign(abs(sine) ** power, sine),
        )
    return output


def solve_uvs(
    boundary: list[int],
    interior: list[int],
    operator: np.ndarray,
    boundary_uv: dict[int, tuple[float, float]],
) -> dict[int, tuple[float, float]]:
    boundary_values = np.array([boundary_uv[index] for index in boundary])
    solved = operator @ boundary_values
    output = dict(boundary_uv)
    output.update({
        index: (float(value[0]), float(value[1]))
        for index, value in zip(interior, solved)
    })
    return quantize_uvs(output)


def map_points(
    points: np.ndarray,
    faces: list[tuple[int, int, int]],
    uvs: dict[int, tuple[float, float]],
    world: dict[int, tuple[float, float, float]],
) -> np.ndarray:
    triangle_uv = np.array([[uvs[index] for index in face] for face in faces])
    denominator = (
        (triangle_uv[:, 1, 1] - triangle_uv[:, 2, 1])
        * (triangle_uv[:, 0, 0] - triangle_uv[:, 2, 0])
        + (triangle_uv[:, 2, 0] - triangle_uv[:, 1, 0])
        * (triangle_uv[:, 0, 1] - triangle_uv[:, 2, 1])
    )
    first = (
        (triangle_uv[None, :, 1, 1] - triangle_uv[None, :, 2, 1])
        * (points[:, None, 0] - triangle_uv[None, :, 2, 0])
        + (triangle_uv[None, :, 2, 0] - triangle_uv[None, :, 1, 0])
        * (points[:, None, 1] - triangle_uv[None, :, 2, 1])
    ) / denominator[None, :]
    second = (
        (triangle_uv[None, :, 2, 1] - triangle_uv[None, :, 0, 1])
        * (points[:, None, 0] - triangle_uv[None, :, 2, 0])
        + (triangle_uv[None, :, 0, 0] - triangle_uv[None, :, 2, 0])
        * (points[:, None, 1] - triangle_uv[None, :, 2, 1])
    ) / denominator[None, :]
    third = 1.0 - first - second
    inside = (first >= -1.0e-9) & (second >= -1.0e-9) & (third >= -1.0e-9)
    counts = inside.sum(axis=1)
    if np.any(counts == 0):
        raise validate.GateError(
            f"superellipse misses {int(np.count_nonzero(counts == 0))} sample points"
        )
    owners = np.argmax(inside, axis=1)
    rows = np.arange(len(points))
    weights = np.column_stack((
        first[rows, owners], second[rows, owners], third[rows, owners]
    ))
    triangle_world = np.array([[world[index] for index in face] for face in faces])
    return np.sum(weights[:, :, None] * triangle_world[owners], axis=1)


def alignment_metrics(
    faces: list[tuple[int, int, int]],
    uvs: dict[int, tuple[float, float]],
    world: dict[int, tuple[float, float, float]],
    sample: np.ndarray,
    seam_anchor: np.ndarray,
    rear_anchor: np.ndarray,
) -> dict[str, float] | None:
    determinants = []
    for face in faces:
        first, second, third = (uvs[index] for index in face)
        determinants.append(
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )
    if min(abs(value) for value in determinants) <= 1.0e-9:
        return None
    if min(determinants) < 0.0 < max(determinants):
        return None
    mapped = map_points(sample, faces, uvs, world)
    seam = map_points(seam_anchor, faces, uvs, world)[0]
    rear = map_points(rear_anchor, faces, uvs, world)[0]
    conditions = [validate.condition(world, uvs, face) for face in faces]
    return {
        "all_condition": max(conditions),
        "rear_anchor_z_cm": float(rear[2]),
        "sample_height_cm": float(np.ptp(mapped[:, 1])),
        "sample_length_cm": float(np.ptp(mapped[:, 2])),
        "sample_max_y_cm": float(mapped[:, 1].max()),
        "sample_min_y_cm": float(mapped[:, 1].min()),
        "sample_min_z_cm": float(mapped[:, 2].min()),
        "seam_anchor_x_cm": float(abs(seam[0])),
    }


def score(metrics: dict[str, float]) -> float:
    return (
        metrics["all_condition"]
        + 4.0 * metrics["seam_anchor_x_cm"]
        + 6.0 * max(0.0, metrics["rear_anchor_z_cm"] + 8.5)
        + 4.0 * max(0.0, 10.5 - metrics["sample_height_cm"])
        + 2.0 * max(0.0, 20.0 - metrics["sample_length_cm"])
    )


def nearest_active(active: np.ndarray, target: tuple[float, float]) -> np.ndarray:
    rows, columns = np.nonzero(active)
    points = np.column_stack(((columns + 0.5) / active.shape[1], (rows + 0.5) / active.shape[0]))
    number = int(np.argmin(np.sum((points - np.array(target)) ** 2, axis=1)))
    return points[number : number + 1]


def main() -> None:
    source = p._parse_outer(p.read_source_outer(shell.SOURCE), source=True).system
    with Image.open(validate.MASK) as image:
        active = np.any(np.asarray(image.convert("RGBA"))[:, :, :3] != 0, axis=2)
    rows, columns = np.nonzero(active)
    all_points = np.column_stack(((columns + 0.5) / 512, (rows + 0.5) / 512))
    sample = all_points[::SAMPLE_STEP]
    seam_anchor = nearest_active(active, (0.0, 0.63))
    rear_anchor = nearest_active(active, (1.0, 0.27))
    reports: list[dict[str, object]] = []
    for spec in p.LODS:
        positions, normals, right_outer = shell.shell_geometry(source, spec)
        physical_uv = shell.physical_uvs(positions, right_outer)
        faces = shell.select_patch(spec, right_outer, physical_uv)
        boundary, topology = shell.patch_topology(faces)
        interior, operator = harmonic_operator(faces, boundary)
        vertices = {index for face in faces for index in face}
        world = {
            index: p._add(positions[index], p._mul(normals[index], shell.BIAS_CM))
            for index in vertices
        }
        candidates: list[dict[str, object]] = []
        for reverse in (False, True):
            for start in range(len(boundary)):
                boundary_uv = superellipse_boundary(
                    boundary, positions, start, reverse
                )
                uvs = solve_uvs(boundary, interior, operator, boundary_uv)
                try:
                    metrics = alignment_metrics(
                        faces, uvs, world, sample, seam_anchor, rear_anchor
                    )
                except validate.GateError:
                    continue
                if metrics is None:
                    continue
                candidates.append({
                    **metrics,
                    "reverse": reverse,
                    "score": score(metrics),
                    "start": start,
                    "uvs": uvs,
                })
        candidates.sort(key=lambda item: float(item["score"]))
        finalists: list[dict[str, object]] = []
        for candidate in candidates:
            try:
                metrics = validate.raster_metrics(
                    world, candidate["uvs"], faces, active  # type: ignore[arg-type]
                )
            except validate.GateError:
                continue
            painted_score = (
                float(metrics["maximum_painted_triangle_condition"])
                + 4.0 * float(candidate["seam_anchor_x_cm"])
                + 6.0 * max(0.0, float(candidate["rear_anchor_z_cm"]) + 8.5)
                + 4.0 * max(0.0, 10.5 - float(metrics["side_projection_height_cm"]))
                + 2.0 * max(0.0, 20.0 - float(metrics["side_projection_length_cm"]))
            )
            finalists.append({
                key: value for key, value in candidate.items() if key != "uvs"
            } | {"painted_score": painted_score, "raster": metrics})
        finalists.sort(key=lambda item: float(item["painted_score"]))
        reports.append({
            "candidate_count": len(candidates),
            "finalists": finalists[:SHORTLIST_COUNT],
            "node": spec.node_name,
            "topology": topology,
        })
    print(json.dumps({
        "active_bounds": {
            "maximum": all_points.max(axis=0).tolist(),
            "minimum": all_points.min(axis=0).tolist(),
        },
        "lods": reports,
        "schema": "apf2k8_helmet_superellipse_search/v1",
        "superellipse": {
            "a": SUPERELLIPSE_A,
            "b": SUPERELLIPSE_B,
            "n": SUPERELLIPSE_N,
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
