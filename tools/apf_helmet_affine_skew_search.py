#!/usr/bin/env python3
"""Audit a full 2-D affine Eagles crest map on the retail high helmet shell."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import apf_helmet_affine_patch_prototype as affine  # noqa: E402
import apf_helmet_crest_wrap_patch as p  # noqa: E402
import apf_helmet_grid_validate as validate  # noqa: E402
import apf_helmet_shell_patch_prototype as shell  # noqa: E402
import apf_helmet_superellipse_search as search  # noqa: E402


def build(args: argparse.Namespace) -> dict[str, object]:
    source = p._parse_outer(p.read_source_outer(shell.SOURCE), source=True).system
    spec = p.LODS[0]
    positions, normals, right_outer = shell.shell_geometry(source, spec)
    with Image.open(affine.MASK) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    active = np.any(rgba[:, :, :3] != 0, axis=2)
    rows, columns = np.nonzero(active)
    source_points = np.column_stack(((columns + 0.5) / 512, (rows + 0.5) / 512))
    hull = affine.convex_hull([tuple(row) for row in source_points.tolist()])
    minimum_v = float(source_points[:, 1].min())
    maximum_v = float(source_points[:, 1].max())
    v_span = maximum_v - minimum_v
    normalized_hull_v = (hull[:, 1] - minimum_v) / v_span

    # General affine source-(u, normalized-v) -> side-projection-(z, y).
    # The extra v_z_slope lane lets the vertical root follow the diagonal
    # crown seam while remaining exactly affine over all painted texels.
    origin = np.asarray(
        (args.front_z, args.top_y - 0.5 * args.u_y_slope), dtype=np.float64
    )
    matrix = np.asarray(
        (
            (-args.length, args.v_z_slope),
            (args.u_y_slope, -args.height),
        ),
        dtype=np.float64,
    )
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) <= 1.0e-9:
        raise RuntimeError("source-to-side affine matrix is singular")
    normalized_hull = np.column_stack((hull[:, 0], normalized_hull_v))
    target_hull = origin + normalized_hull @ matrix.T
    selected = [
        face
        for face in right_outer
        if affine.polygons_intersect(
            target_hull,
            np.asarray(
                [(positions[index][2], positions[index][1]) for index in face],
                dtype=np.float64,
            ),
        )
    ]
    selected_face_ids = [right_outer.index(face) for face in selected]
    faces = affine.weld_exact_shell_seams(selected, positions, normals)
    report_topology = affine.topology(faces)
    vertices = {index for face in faces for index in face}
    inverse = np.linalg.inv(matrix)
    uv: dict[int, tuple[float, float]] = {}
    for index in vertices:
        z_value, y_value = positions[index][2], positions[index][1]
        source_u, normalized_v = inverse @ (np.asarray((z_value, y_value)) - origin)
        uv[index] = (
            float(source_u),
            float(minimum_v + v_span * normalized_v),
        )
    uv = search.quantize_uvs(uv)

    missing, multiple, first_missing = affine.coverage_counts(faces, uv, active)
    common: dict[str, object] = {
        "affine_matrix_z_y_from_u_v": matrix.tolist(),
        "affine_origin_z_y": origin.tolist(),
        "capacity": {
            "face_limit": 266,
            "fits": report_topology["face_count"] <= 266
            and report_topology["vertex_count"] <= 161,
            "vertex_limit": 161,
        },
        "coverage": {
            "first_missing_xy": first_missing,
            "missing": missing,
            "multiple": multiple,
        },
        "parameters": vars(args),
        "right_outer_face_ids": selected_face_ids,
        "schema": "apf2k8_helmet_affine_skew_search/v1",
        "topology": report_topology,
    }
    if missing or multiple:
        return common

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
    painted = validate.raster_metrics(world, uv, faces, active)
    mapped_rows = [
        search.map_points(source_points[start : start + 2_000], faces, uv, world)
        for start in range(0, len(source_points), 2_000)
    ]
    mapped = np.concatenate(mapped_rows)
    design = np.column_stack((source_points, np.ones(len(source_points))))
    target = mapped[:, (2, 1)]
    coefficients = np.linalg.lstsq(design, target, rcond=None)[0]
    residual = target - design @ coefficients
    sum_squared_residual = np.sum(residual**2, axis=0)
    sum_squared_total = np.sum((target - target.mean(axis=0)) ** 2, axis=0)
    span = np.ptp(target, axis=0)
    root = mapped[source_points[:, 0] < 0.01]
    common.update({
        "affine_shape": {
            "maximum_normalized_error_z_y": (
                np.max(np.abs(residual), axis=0) / span
            ).tolist(),
            "normalized_rmse_z_y": (
                np.sqrt(np.mean(residual**2, axis=0)) / span
            ).tolist(),
            "r_squared_z_y": (
                1.0 - sum_squared_residual / sum_squared_total
            ).tolist(),
        },
        "painted": painted,
        "quantized_uv": {
            "determinant_maximum": max(determinants),
            "determinant_minimum": min(determinants),
            "same_orientation": not (
                min(determinants) < 0.0 < max(determinants)
            ),
        },
        "root_abs_x_cm": {
            "maximum": float(np.abs(root[:, 0]).max()),
            "median": float(np.median(np.abs(root[:, 0]))),
            "minimum": float(np.abs(root[:, 0]).min()),
            "percentile_10": float(np.quantile(np.abs(root[:, 0]), 0.10)),
        },
    })
    return common


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--length", type=float, required=True)
    parser.add_argument("--height", type=float, required=True)
    parser.add_argument("--front-z", type=float, required=True)
    parser.add_argument("--top-y", type=float, required=True)
    parser.add_argument("--u-y-slope", type=float, required=True)
    parser.add_argument("--v-z-slope", type=float, required=True)
    print(json.dumps(build(parser.parse_args()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
