#!/usr/bin/env python3
"""Fail-closed audit for the shared affine Eagles shell-disk selector.

This diagnostic reads the pinned retail helmet and v3 Eagles mask.  It never
builds an APF/XISO.  It proves the exact high/low face selectors, exact source
seam weld, physical disk topology, YZ injectivity, post-SNORM16 exact-once
coverage, geometric bounds, and fixed carrier strip/index capacity.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Sequence

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


REPORT = ROOT / "tools/apf_helmet_affine_disk_audit_report.json"
MASK_V3 = affine.MASK
MASK_V4 = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-clean-source-region-mask-v4-guarded.png"
)
EXPECTED_V3_MASK_PNG_SHA256 = (
    "3d7e10828af458c9ad13663f8031311b364fa56be5c852f6aa8f38574d9c3597"
)
EXPECTED_V3_MASK_RGBA_SHA256 = (
    "c9a915df7f66dae85a5f620ad4907aadc2cf3f4941fcfc86a074c68a34362d6c"
)
EXPECTED_V3_ACTIVE_TEXELS = 57_066
EXPECTED_V4_MASK_PNG_SHA256 = (
    "4913aa6cf62fe6f96a913001ed5ad9d0356a109412e3f1b432fc0fd81eb5750a"
)
EXPECTED_V4_MASK_RGBA_SHA256 = (
    "cf937ff797e4e5ae94b5c456babf298fa20436716b6ef2b708faac70b293d40e"
)
EXPECTED_V4_ACTIVE_TEXELS = 42_800
GUARD_U_SCALE = 0.75
GUARD_U_OFFSET = 0.125
BIAS_CM = 0.14
PARAMETERS = {
    "length": 18.9,
    "height": 10.0,
    "front_z": 10.07,
    "top_y": 16.35,
    "slope": -4.4,
    "z_v_slope": 3.16,
    "selection_margin": 1.0,
}
EXPECTED_TOPOLOGY = {
    "helmet_hi": {"triangles": 258, "vertices": 161, "boundary_edges": 62},
    "helmet_lo": {"triangles": 78, "vertices": 56, "boundary_edges": 32},
}
FACE_LIMIT = {"helmet_hi": 266, "helmet_lo": 91}
VERTEX_LIMIT = {"helmet_hi": 161, "helmet_lo": 64}


class AuditError(RuntimeError):
    pass


def require(value: object, message: str) -> None:
    if not value:
        raise AuditError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def edge_pairs(face: Sequence[int]) -> tuple[tuple[int, int], ...]:
    return tuple(
        tuple(sorted((int(first), int(second))))
        for first, second in zip(face, (face[1], face[2], face[0]))
    )


def disk_topology(faces: Sequence[tuple[int, int, int]]) -> dict[str, int | bool]:
    vertices = {vertex for face in faces for vertex in face}
    edge_owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for edge in edge_pairs(face):
            edge_owners[edge].append(face_index)
    require(all(len(owners) in (1, 2) for owners in edge_owners.values()),
            "selected face set is edge-nonmanifold")
    face_adjacency = [set() for _face in faces]
    for owners in edge_owners.values():
        if len(owners) == 2:
            first, second = owners
            face_adjacency[first].add(second)
            face_adjacency[second].add(first)
    remaining = set(range(len(faces)))
    face_components = 0
    while remaining:
        face_components += 1
        queue = [remaining.pop()]
        while queue:
            for neighbor in face_adjacency[queue.pop()]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
    boundary = [edge for edge, owners in edge_owners.items() if len(owners) == 1]
    boundary_graph: dict[int, set[int]] = defaultdict(set)
    for first, second in boundary:
        boundary_graph[first].add(second)
        boundary_graph[second].add(first)
    boundary_is_simple = bool(boundary_graph) and all(
        len(neighbors) == 2 for neighbors in boundary_graph.values()
    )
    remaining_vertices = set(boundary_graph)
    boundary_components = 0
    while remaining_vertices:
        boundary_components += 1
        queue = [remaining_vertices.pop()]
        while queue:
            for neighbor in boundary_graph[queue.pop()]:
                if neighbor in remaining_vertices:
                    remaining_vertices.remove(neighbor)
                    queue.append(neighbor)
    euler = len(vertices) - len(edge_owners) + len(faces)
    disk = (
        face_components == 1 and boundary_components == 1
        and boundary_is_simple and euler == 1
    )
    return {
        "triangles": len(faces),
        "vertices": len(vertices),
        "edges": len(edge_owners),
        "boundary_edges": len(boundary),
        "face_components": face_components,
        "boundary_components": boundary_components,
        "boundary_is_simple": boundary_is_simple,
        "euler_characteristic": euler,
        "manifold_disk": disk,
    }


def cross2(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1])
                 - (b[1] - a[1]) * (c[0] - a[0]))


def proper_segments_cross(
    first: np.ndarray, second: np.ndarray,
    third: np.ndarray, fourth: np.ndarray,
) -> bool:
    values = (
        cross2(first, second, third), cross2(first, second, fourth),
        cross2(third, fourth, first), cross2(third, fourth, second),
    )
    return values[0] * values[1] < -1.0e-14 and values[2] * values[3] < -1.0e-14


def point_strictly_inside(point: np.ndarray, triangle: np.ndarray) -> bool:
    signs = [
        cross2(triangle[index], triangle[(index + 1) % 3], point)
        for index in range(3)
    ]
    return min(signs) > 1.0e-9 or max(signs) < -1.0e-9


def projected_overlap_count(
    faces: Sequence[tuple[int, int, int]],
    points: dict[int, tuple[float, float, float]],
) -> int:
    triangles = [
        np.asarray([[points[index][2], points[index][1]] for index in face])
        for face in faces
    ]
    overlaps = 0
    for first_index, first in enumerate(triangles):
        first_minimum, first_maximum = first.min(axis=0), first.max(axis=0)
        for second in triangles[first_index + 1:]:
            if np.any(first_maximum < second.min(axis=0) - 1.0e-9) or np.any(
                second.max(axis=0) < first_minimum - 1.0e-9
            ):
                continue
            if any(
                proper_segments_cross(a, b, c, d)
                for a, b in zip(first, np.roll(first, -1, axis=0))
                for c, d in zip(second, np.roll(second, -1, axis=0))
            ) or any(point_strictly_inside(point, second) for point in first) or any(
                point_strictly_inside(point, first) for point in second
            ):
                overlaps += 1
    return overlaps


def read_mask(
    path: Path, expected_png: str, expected_rgba: str, expected_active: int,
) -> tuple[np.ndarray, np.ndarray]:
    payload = path.read_bytes()
    require(sha256_bytes(payload) == expected_png, f"mask PNG hash drifted: {path}")
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    require(sha256_bytes(rgba.tobytes()) == expected_rgba,
            f"mask RGBA hash drifted: {path}")
    active = np.any(rgba[:, :, :3] != 0, axis=2)
    require(int(active.sum()) == expected_active, f"active mask census drifted: {path}")
    return active, rgba


def source_and_masks() -> tuple[
    bytes, np.ndarray, np.ndarray, float, float,
    np.ndarray, np.ndarray, np.ndarray,
]:
    source = p._parse_outer(p.read_source_outer(shell.SOURCE), source=True).system
    active_v3, _rgba_v3 = read_mask(
        MASK_V3, EXPECTED_V3_MASK_PNG_SHA256, EXPECTED_V3_MASK_RGBA_SHA256,
        EXPECTED_V3_ACTIVE_TEXELS,
    )
    rows_v3, columns_v3 = np.nonzero(active_v3)
    points_v3 = np.column_stack(
        ((columns_v3 + 0.5) / 512, (rows_v3 + 0.5) / 512)
    )
    active_v4, _rgba_v4 = read_mask(
        MASK_V4, EXPECTED_V4_MASK_PNG_SHA256, EXPECTED_V4_MASK_RGBA_SHA256,
        EXPECTED_V4_ACTIVE_TEXELS,
    )
    rows_v4, columns_v4 = np.nonzero(active_v4)
    points_v4 = np.column_stack(
        ((columns_v4 + 0.5) / 512, (rows_v4 + 0.5) / 512)
    )
    raw_design_points_v4 = np.column_stack((
        (points_v4[:, 0] - GUARD_U_OFFSET) / GUARD_U_SCALE,
        points_v4[:, 1],
    ))
    return (
        source, active_v3, points_v3,
        float(points_v3[:, 1].min()), float(points_v3[:, 1].max()),
        active_v4, points_v4, raw_design_points_v4,
    )


def select_faces(
    right_outer: Sequence[tuple[int, int, int]],
    positions: Sequence[tuple[float, float, float]],
    source_points: np.ndarray,
    minimum_v: float,
    maximum_v: float,
    lod: str,
) -> list[int]:
    hull = affine.convex_hull([tuple(row) for row in source_points.tolist()])
    center = hull.mean(axis=0)
    selection_hull = center + PARAMETERS["selection_margin"] * (hull - center)
    normalized_v = (selection_hull[:, 1] - minimum_v) / (maximum_v - minimum_v)
    target_hull = np.column_stack((
        PARAMETERS["front_z"] - PARAMETERS["length"] * selection_hull[:, 0]
        + PARAMETERS["z_v_slope"] * normalized_v,
        PARAMETERS["top_y"] + PARAMETERS["slope"] * (selection_hull[:, 0] - 0.5)
        - PARAMETERS["height"] * normalized_v,
    ))
    selected = [
        index for index, face in enumerate(right_outer)
        if affine.polygons_intersect(
            target_hull,
            np.asarray([(positions[vertex][2], positions[vertex][1]) for vertex in face]),
        )
    ]
    if lod == "helmet_hi":
        # The hull-intersection guard selects this one external boundary ear.
        # It owns zero active texel centers.  Removing it preserves the welded
        # disk and is the only change needed to meet the 161-vertex allocation.
        require(132 in selected, "proved unused high boundary ear is absent")
        selected.remove(132)
    return selected


def welded_faces(
    selected_ids: Sequence[int],
    right_outer: Sequence[tuple[int, int, int]],
    positions: Sequence[tuple[float, float, float]],
    normals: Sequence[tuple[float, float, float]],
) -> tuple[list[tuple[int, int, int]], dict[int, int], int]:
    original_vertices = sorted({
        vertex for face_id in selected_ids for vertex in right_outer[face_id]
    })
    canonical: dict[
        tuple[tuple[float, float, float], tuple[float, float, float]], int
    ] = {}
    replacement: dict[int, int] = {}
    for vertex in original_vertices:
        replacement[vertex] = canonical.setdefault(
            (positions[vertex], normals[vertex]), vertex
        )
    faces = [
        tuple(replacement[vertex] for vertex in right_outer[face_id])
        for face_id in selected_ids
    ]
    return faces, replacement, len(original_vertices) - len(canonical)


def affine_uvs(
    vertices: Sequence[int],
    positions: Sequence[tuple[float, float, float]],
    minimum_v: float,
    maximum_v: float,
) -> tuple[
    dict[int, tuple[float, float]],
    dict[int, tuple[float, float]],
    np.ndarray,
    np.ndarray,
]:
    transform = np.asarray((
        (-PARAMETERS["length"], PARAMETERS["z_v_slope"]),
        (PARAMETERS["slope"], -PARAMETERS["height"]),
    ))
    inverse = np.linalg.inv(transform)
    unquantized: dict[int, tuple[float, float]] = {}
    for vertex in vertices:
        u_value, normalized_v = inverse @ np.asarray((
            positions[vertex][2] - PARAMETERS["front_z"],
            positions[vertex][1] - PARAMETERS["top_y"] + 0.5 * PARAMETERS["slope"],
        ))
        unquantized[vertex] = (
            float(u_value),
            minimum_v + (maximum_v - minimum_v) * float(normalized_v),
        )
    raw_quantized = search.quantize_uvs(unquantized)
    guarded_quantized = search.quantize_uvs({
        vertex: (
            GUARD_U_OFFSET + GUARD_U_SCALE * value[0], value[1]
        )
        for vertex, value in unquantized.items()
    })
    return guarded_quantized, raw_quantized, transform, inverse


def uv_formula(
    transform: np.ndarray, inverse: np.ndarray, minimum_v: float, maximum_v: float,
) -> dict[str, object]:
    span = maximum_v - minimum_v
    input_offset = np.asarray((
        -PARAMETERS["front_z"],
        -PARAMETERS["top_y"] + 0.5 * PARAMETERS["slope"],
    ))
    uv_matrix = np.vstack((inverse[0], span * inverse[1]))
    inverse_offset = inverse @ input_offset
    uv_offset = np.asarray((inverse_offset[0], minimum_v + span * inverse_offset[1]))
    world_matrix = np.asarray((
        (-PARAMETERS["length"], PARAMETERS["z_v_slope"] / span),
        (PARAMETERS["slope"], -PARAMETERS["height"] / span),
    ))
    world_offset = np.asarray((
        PARAMETERS["front_z"] - PARAMETERS["z_v_slope"] * minimum_v / span,
        PARAMETERS["top_y"] - 0.5 * PARAMETERS["slope"]
        + PARAMETERS["height"] * minimum_v / span,
    ))
    require(np.max(np.abs(np.linalg.inv(world_matrix) - uv_matrix)) < 1.0e-12,
            "expanded affine inverse drifted")
    require(np.max(np.abs(-uv_matrix @ world_offset - uv_offset)) < 1.0e-12,
            "expanded affine offset drifted")
    guard_matrix = np.asarray(((GUARD_U_SCALE, 0.0), (0.0, 1.0)))
    guard_offset = np.asarray((GUARD_U_OFFSET, 0.0))
    guarded_uv_matrix = guard_matrix @ uv_matrix
    guarded_uv_offset = guard_matrix @ uv_offset + guard_offset
    guarded_world_matrix = world_matrix @ np.linalg.inv(guard_matrix)
    guarded_world_offset = (
        world_offset - guarded_world_matrix @ guard_offset
    )
    require(np.max(np.abs(np.linalg.inv(guarded_world_matrix) - guarded_uv_matrix)) < 1.0e-12,
            "guarded affine inverse drifted")
    require(np.max(np.abs(-guarded_uv_matrix @ guarded_world_offset - guarded_uv_offset)) < 1.0e-12,
            "guarded affine offset drifted")
    return {
        "guard": {
            "formula": "u_guarded = 0.125 + 0.75 * u_raw; v_guarded = v_raw",
            "u_offset": GUARD_U_OFFSET,
            "u_scale": GUARD_U_SCALE,
        },
        "guarded_texture_uv_to_world_zy_matrix": guarded_world_matrix.tolist(),
        "guarded_texture_uv_to_world_zy_offset": guarded_world_offset.tolist(),
        "world_zy_to_guarded_texture_uv_matrix": guarded_uv_matrix.tolist(),
        "world_zy_to_guarded_texture_uv_offset": guarded_uv_offset.tolist(),
        "world_to_texture_formula": (
            "guarded_uv = matrix @ [z_cm,y_cm] + offset, then SNORM16 "
            "quantize each carrier vertex"
        ),
        "guarded_global_affine_condition": float(np.linalg.cond(guarded_world_matrix)),
        "raw_texture_uv_to_world_zy_matrix": world_matrix.tolist(),
        "raw_texture_uv_to_world_zy_offset": world_offset.tolist(),
        "world_zy_to_raw_texture_uv_matrix": uv_matrix.tolist(),
        "world_zy_to_raw_texture_uv_offset": uv_offset.tolist(),
    }


def strip_audit(
    faces: Sequence[tuple[int, int, int]], spec: p.LodSpec,
) -> dict[str, object]:
    vertices = sorted({vertex for face in faces for vertex in face})
    right_map = {vertex: number for number, vertex in enumerate(vertices)}
    left_map = {vertex: number + len(vertices) for number, vertex in enumerate(vertices)}
    right_faces = [tuple(right_map[vertex] for vertex in face) for face in faces]
    left_faces = [
        (left_map[first], left_map[third], left_map[second])
        for first, second, third in faces
    ]
    right_strips = shell.stripify(right_faces)
    left_strips = shell.stripify(left_faces)
    stream: list[int] = []
    for strip in [*right_strips, *left_strips]:
        if stream:
            stream.append(0xFFFF)
        stream.extend(strip)
    unpadded_words = len(stream)
    require(unpadded_words <= spec.carrier_index_count,
            f"{spec.node_name} strip stream exceeds allocation")
    stream.extend([stream[-1]] * (spec.carrier_index_count - len(stream)))
    decoded = p._triangles(stream)
    wanted = {frozenset(face): face for face in [*right_faces, *left_faces]}
    require(len(decoded) == len(wanted), f"{spec.node_name} strip face count differs")
    require({frozenset(face) for face in decoded} == set(wanted),
            f"{spec.node_name} strip face set differs")
    require(all(shell.is_cyclic(wanted[frozenset(face)], face) for face in decoded),
            f"{spec.node_name} strip winding differs")
    payload = b"".join(int(word).to_bytes(2, "big") for word in stream)
    return {
        "right_strip_count": len(right_strips),
        "left_strip_count": len(left_strips),
        "restart_count": len(right_strips) + len(left_strips) - 1,
        "unpadded_index_words": unpadded_words,
        "fixed_index_word_capacity": spec.carrier_index_count,
        "padding_words": spec.carrier_index_count - unpadded_words,
        "decoded_non_degenerate_triangles": len(decoded),
        "decoded_exact_oriented_mirrored_face_set": True,
        "padded_index_stream_sha256": sha256_bytes(payload),
    }


def lod_report(
    lod: str,
    source: bytes,
    selection_points_v3: np.ndarray,
    minimum_v: float,
    maximum_v: float,
    active_v4: np.ndarray,
    guarded_points_v4: np.ndarray,
    raw_design_points_v4: np.ndarray,
) -> dict[str, object]:
    spec = next(item for item in p.LODS if item.node_name == lod)
    positions, normals, right_outer = shell.shell_geometry(source, spec)
    selected_ids = select_faces(
        right_outer, positions, selection_points_v3, minimum_v, maximum_v, lod
    )
    faces, replacement, welded_duplicate_count = welded_faces(
        selected_ids, right_outer, positions, normals
    )
    topo = disk_topology(faces)
    expected = EXPECTED_TOPOLOGY[lod]
    require(bool(topo["manifold_disk"]), f"{lod} is not a welded physical disk")
    require(all(int(topo[key]) == value for key, value in expected.items()),
            f"{lod} topology metrics drifted: {topo}")
    require(int(topo["triangles"]) <= FACE_LIMIT[lod], f"{lod} face limit exceeded")
    require(int(topo["vertices"]) <= VERTEX_LIMIT[lod], f"{lod} vertex limit exceeded")

    vertices = sorted({vertex for face in faces for vertex in face})
    uvs, raw_uvs, transform, inverse = affine_uvs(
        vertices, positions, minimum_v, maximum_v
    )
    guarded_domain = np.asarray([uvs[vertex] for vertex in vertices])
    raw_domain = np.asarray([raw_uvs[vertex] for vertex in vertices])
    require(np.all(guarded_domain >= 0.0) and np.all(guarded_domain <= 1.0),
            f"{lod} guarded UV vertex escaped [0,1]")
    missing, multiple, first_missing = affine.coverage_counts(
        faces, uvs, active_v4
    )
    require((missing, multiple) == (0, 0),
            f"{lod} active coverage differs: {missing} missing, {multiple} multiple")
    world = {
        vertex: p._add(positions[vertex], p._mul(normals[vertex], BIAS_CM))
        for vertex in vertices
    }
    painted = validate.raster_metrics(world, uvs, list(faces), active_v4)
    require(painted["painted_texels_mapped_exactly_once"] == EXPECTED_V4_ACTIVE_TEXELS,
            f"{lod} exact-once raster census drifted")
    require(painted["side_projection_length_cm"] >= 19.5,
            f"{lod} painted length is short")
    require(8.5 <= painted["side_projection_height_cm"] <= 10.5,
            f"{lod} painted height is outside contract")
    require(painted["bounds_cm"]["maximum"][2] >= 11.5,
            f"{lod} painted front does not reach z=11.5")
    require(painted["bounds_cm"]["minimum"][2] <= -8.5,
            f"{lod} painted rear does not reach z=-8.5")

    mapped = np.concatenate([
        search.map_points(guarded_points_v4[start : start + 2_000], faces, uvs, world)
        for start in range(0, len(guarded_points_v4), 2_000)
    ])
    root = mapped[raw_design_points_v4[:, 0] < 0.01]
    root_metrics = {
        "minimum_all_active_abs_x_cm": float(np.min(np.abs(mapped[:, 0]))),
        "minimum_abs_x_cm": float(np.min(np.abs(root[:, 0]))),
        "median_abs_x_cm": float(np.median(np.abs(root[:, 0]))),
        "maximum_abs_x_cm": float(np.max(np.abs(root[:, 0]))),
    }
    require(root_metrics["minimum_all_active_abs_x_cm"] <= 1.0,
            f"{lod} active art does not reach x<=1 cm")
    if lod == "helmet_hi":
        require(root_metrics["minimum_abs_x_cm"] <= 1.0,
                "high crown/root does not reach x<=1 cm")

    source_determinants = []
    carrier_determinants = []
    uv_determinants = []
    for face_id, face in zip(selected_ids, faces):
        source_face = right_outer[face_id]
        a, b, c = (positions[index] for index in source_face)
        source_determinants.append(
            (b[2] - a[2]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[2] - a[2])
        )
        a, b, c = (world[index] for index in face)
        carrier_determinants.append(
            (b[2] - a[2]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[2] - a[2])
        )
        first, second, third = (uvs[index] for index in face)
        uv_determinants.append(
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )
    require(max(source_determinants) < -1.0e-6,
            f"{lod} source YZ determinant orientation differs")
    require(max(carrier_determinants) < -1.0e-6,
            f"{lod} biased carrier YZ determinant orientation differs")
    require(max(uv_determinants) < -1.0e-8,
            f"{lod} post-quantized UV orientation differs")
    source_points_by_vertex = {vertex: positions[vertex] for vertex in vertices}
    source_overlaps = projected_overlap_count(faces, source_points_by_vertex)
    carrier_overlaps = projected_overlap_count(faces, world)
    require(source_overlaps == carrier_overlaps == 0,
            f"{lod} projected triangle interiors overlap")

    design = np.column_stack((
        raw_design_points_v4, np.ones(len(raw_design_points_v4))
    ))
    target = mapped[:, (2, 1)]
    coefficients = np.linalg.lstsq(design, target, rcond=None)[0]
    residual = target - design @ coefficients
    total = np.sum((target - target.mean(axis=0)) ** 2, axis=0)
    squared = np.sum(residual**2, axis=0)
    span = np.ptp(target, axis=0)
    affine_fit = {
        "r_squared_z_y": (1.0 - squared / total).tolist(),
        "normalized_rmse_z_y": (
            np.sqrt(np.mean(residual**2, axis=0)) / span
        ).tolist(),
        "maximum_normalized_error_z_y": (
            np.max(np.abs(residual), axis=0) / span
        ).tolist(),
    }
    require(min(affine_fit["r_squared_z_y"]) > 0.99999,
            f"{lod} post-quantized affine fit is too low")

    selector_csv = ",".join(map(str, selected_ids)).encode("ascii")
    selector: dict[str, object] = {
        "right_outer_face_ids": selected_ids,
        "face_id_csv_sha256": sha256_bytes(selector_csv),
        "face_id_basis": (
            "shell strip order; outward radial about LodSpec.center; all three "
            "source vertices x>=-1e-6; includes leading diagnostic face"
        ),
        "right_outer_face_count": len(right_outer),
        "exact_position_and_normal_welded_duplicate_vertices": welded_duplicate_count,
    }
    if lod == "helmet_hi":
        old = set(shell.HIGH_RIGHT_OUTER_FACE_IDS)
        new = set(selected_ids)
        require(old != new, "high selector accidentally equals rejected harmonic topology")
        selector["rejected_harmonic_selector_comparison"] = {
            "equal": False,
            "intersection_faces": len(old & new),
            "symmetric_difference_faces": len(old ^ new),
            "jaccard": len(old & new) / len(old | new),
            "removed_unused_guard_face_id": 132,
        }

    return {
        "selector": selector,
        "topology": topo,
        "strip_allocation": strip_audit(faces, spec),
        "projection_injectivity": {
            "source_yz_area2_minimum": min(source_determinants),
            "source_yz_area2_maximum": max(source_determinants),
            "biased_carrier_yz_area2_minimum": min(carrier_determinants),
            "biased_carrier_yz_area2_maximum": max(carrier_determinants),
            "post_quantized_uv_determinant_minimum": min(uv_determinants),
            "post_quantized_uv_determinant_maximum": max(uv_determinants),
            "source_projected_interior_overlap_pairs": source_overlaps,
            "biased_carrier_projected_interior_overlap_pairs": carrier_overlaps,
            "same_negative_orientation_no_collapse": True,
        },
        "active_coverage": {
            "guarded_v4_active_texels": EXPECTED_V4_ACTIVE_TEXELS,
            "guarded_v4_active_bbox": [64, 122, 447, 389],
            "missing": missing,
            "multiple": multiple,
            "first_missing_xy": first_missing,
            "mapped_exactly_once": EXPECTED_V4_ACTIVE_TEXELS,
        },
        "uv_domain": {
            "guarded_post_snorm16_minimum": guarded_domain.min(axis=0).tolist(),
            "guarded_post_snorm16_maximum": guarded_domain.max(axis=0).tolist(),
            "all_used_guarded_vertices_inside_closed_unit_square": True,
            "counterfactual_raw_post_snorm16_minimum": raw_domain.min(axis=0).tolist(),
            "counterfactual_raw_post_snorm16_maximum": raw_domain.max(axis=0).tolist(),
            "sampler_wrap_or_clamp_assumption": False,
        },
        "painted": painted,
        "root": root_metrics,
        "post_quantized_affine_fit": affine_fit,
    }


def build_report() -> dict[str, object]:
    (
        source, _active_v3, selection_points_v3, minimum_v, maximum_v,
        active_v4, guarded_points_v4, raw_design_points_v4,
    ) = source_and_masks()
    # The shared validator is intentionally pinned to v3 by default.  This
    # audit substitutes only the guarded mask census before calling its pure
    # raster metric routine.
    validate.EXPECTED_ACTIVE_TEXELS = EXPECTED_V4_ACTIVE_TEXELS
    transform = np.asarray((
        (-PARAMETERS["length"], PARAMETERS["z_v_slope"]),
        (PARAMETERS["slope"], -PARAMETERS["height"]),
    ))
    inverse = np.linalg.inv(transform)
    report = {
        "schema": "apf2k8_helmet_affine_disk_audit/v1",
        "claim": (
            "headless fixed-allocation guarded shared-affine high/low shell-disk proof; "
            "no Blender, GUI, emulator, Xenia, or APF/XISO write"
        ),
        "inputs": {
            "source_outer": str(shell.SOURCE),
            "selection_mask_v3": {
                "path": str(MASK_V3),
                "png_sha256": EXPECTED_V3_MASK_PNG_SHA256,
                "rgba_sha256": EXPECTED_V3_MASK_RGBA_SHA256,
                "active_texels": EXPECTED_V3_ACTIVE_TEXELS,
            },
            "guarded_runtime_mask_v4": {
                "path": str(MASK_V4),
                "png_sha256": EXPECTED_V4_MASK_PNG_SHA256,
                "rgba_sha256": EXPECTED_V4_MASK_RGBA_SHA256,
                "active_texels": EXPECTED_V4_ACTIVE_TEXELS,
                "active_bbox": [64, 122, 447, 389],
            },
        },
        "parameters": PARAMETERS,
        "affine": uv_formula(transform, inverse, minimum_v, maximum_v),
        "lods": {
            lod: lod_report(
                lod, source, selection_points_v3, minimum_v, maximum_v,
                active_v4, guarded_points_v4, raw_design_points_v4,
            )
            for lod in ("helmet_hi", "helmet_lo")
        },
        "all_hard_constraints_passed": True,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.write_report:
        REPORT.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
