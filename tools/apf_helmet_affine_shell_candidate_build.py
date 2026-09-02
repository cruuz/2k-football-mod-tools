#!/usr/bin/env python3
"""Build the shared-LOD, shell-native Eagles affine carrier candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import apf_helmet_affine_patch_prototype as affine  # noqa: E402
import apf_helmet_crest_wrap_patch as p  # noqa: E402
import apf_helmet_shell_patch_prototype as shell  # noqa: E402
import apf_helmet_superellipse_search as search  # noqa: E402


DESTINATION = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-v22-guarded-affine-shell-candidate-4"
)
SOURCE_MASK = affine.MASK
GUARDED_MASK = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-clean-source-region-mask-v4-guarded.png"
)
SOURCE_MASK_PNG_SHA256 = "3d7e10828af458c9ad13663f8031311b364fa56be5c852f6aa8f38574d9c3597"
SOURCE_MASK_RGBA_SHA256 = "c9a915df7f66dae85a5f620ad4907aadc2cf3f4941fcfc86a074c68a34362d6c"
GUARDED_MASK_PNG_SHA256 = "4913aa6cf62fe6f96a913001ed5ad9d0356a109412e3f1b432fc0fd81eb5750a"
GUARDED_MASK_RGBA_SHA256 = "cf937ff797e4e5ae94b5c456babf298fa20436716b6ef2b708faac70b293d40e"
EXPECTED_SOURCE_ACTIVE_TEXELS = 57_066
EXPECTED_GUARDED_ACTIVE_TEXELS = 42_800
GUARD_U_OFFSET = 0.125
GUARD_U_SCALE = 0.75

# Audited general-affine source-(u, normalized-v) -> side-(z, y) placement.
LENGTH = 18.9
HEIGHT = 10.0
FRONT_Z = 10.07
TOP_Y = 16.35
U_Y_SLOPE = -4.4
V_Z_SLOPE = 3.16

EXPECTED_PATCH = {
    "helmet_hi": {"faces": 258, "vertices": 161, "boundary": 62},
    "helmet_lo": {"faces": 78, "vertices": 56, "boundary": 32},
}
SIDE_CAPACITY = {"helmet_hi": 161, "helmet_lo": 64}
LEFT_START_OFFSET = {"helmet_hi": 163, "helmet_lo": 64}


def load_mask(
    path: Path, png_sha256: str, rgba_sha256: str, expected_active: int,
) -> tuple[np.ndarray, np.ndarray]:
    png = path.read_bytes()
    if hashlib.sha256(png).hexdigest() != png_sha256:
        raise p.PatchError(f"Eagles mask PNG hash drifted: {path}")
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    if hashlib.sha256(rgba.tobytes()).hexdigest() != rgba_sha256:
        raise p.PatchError(f"Eagles mask RGBA hash drifted: {path}")
    active = np.any(rgba[:, :, :3] != 0, axis=2)
    if int(active.sum()) != expected_active:
        raise p.PatchError(f"Eagles mask active-texel census drifted: {path}")
    rows, columns = np.nonzero(active)
    points = np.column_stack(((columns + 0.5) / 512, (rows + 0.5) / 512))
    return active, points


def affine_patch(
    spec: p.LodSpec,
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    right_outer: list[tuple[int, int, int]],
    guarded_active: np.ndarray,
    source_points: np.ndarray,
    minimum_v: float,
    maximum_v: float,
) -> tuple[
    list[tuple[int, int, int]],
    dict[int, tuple[float, float]],
    list[int],
    dict[str, int | bool],
]:
    hull = affine.convex_hull([tuple(row) for row in source_points.tolist()])
    normalized_v = (hull[:, 1] - minimum_v) / (maximum_v - minimum_v)
    target_hull = np.column_stack((
        FRONT_Z - LENGTH * hull[:, 0] + V_Z_SLOPE * normalized_v,
        TOP_Y + U_Y_SLOPE * (hull[:, 0] - 0.5) - HEIGHT * normalized_v,
    ))
    selected_face_ids = [
        number
        for number, face in enumerate(right_outer)
        if affine.polygons_intersect(
            target_hull,
            np.asarray(
                [(positions[index][2], positions[index][1]) for index in face],
                dtype=np.float64,
            ),
        )
    ]
    if spec.node_name == "helmet_hi":
        if 132 not in selected_face_ids or right_outer[132] != (1669, 1663, 1664):
            raise p.PatchError("high unused guard-face basis drifted")
        selected_face_ids.remove(132)
    selected = [right_outer[number] for number in selected_face_ids]
    faces = affine.weld_exact_shell_seams(selected, positions, normals)
    report_topology = affine.topology(faces)
    expected = EXPECTED_PATCH[spec.node_name]
    wanted_topology = {
        "boundary_edge_count": expected["boundary"],
        "boundary_is_simple": True,
        "euler_characteristic": 1,
        "face_count": expected["faces"],
        "vertex_count": expected["vertices"],
    }
    for field, wanted in wanted_topology.items():
        if report_topology[field] != wanted:
            raise p.PatchError(
                f"{spec.node_name} affine topology {field}="
                f"{report_topology[field]!r}, expected {wanted!r}"
            )

    transform = np.asarray(
        ((-LENGTH, V_Z_SLOPE), (U_Y_SLOPE, -HEIGHT)), dtype=np.float64
    )
    inverse = np.linalg.inv(transform)
    vertices = {index for face in faces for index in face}
    uvs: dict[int, tuple[float, float]] = {}
    for index in vertices:
        u_value, normalized = inverse @ np.asarray((
            positions[index][2] - FRONT_Z,
            positions[index][1] - TOP_Y + 0.5 * U_Y_SLOPE,
        ))
        uvs[index] = (
            float(GUARD_U_OFFSET + GUARD_U_SCALE * u_value),
            float(minimum_v + (maximum_v - minimum_v) * normalized),
        )
    uvs = search.quantize_uvs(uvs)
    uv_values = np.asarray(list(uvs.values()), dtype=np.float64)
    if float(uv_values.min()) < 0.0 or float(uv_values.max()) > 1.0:
        raise p.PatchError(
            f"{spec.node_name} guarded UV escaped [0,1]: "
            f"{uv_values.min(axis=0)}..{uv_values.max(axis=0)}"
        )
    missing, multiple, first_missing = affine.coverage_counts(
        faces, uvs, guarded_active
    )
    if missing or multiple:
        raise p.PatchError(
            f"{spec.node_name} affine coverage missing={missing}, multiple={multiple}, "
            f"first_missing={first_missing}"
        )
    determinants = []
    for face in faces:
        first, second, third = (uvs[index] for index in face)
        determinants.append(
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )
    if min(determinants) < 0.0 < max(determinants):
        raise p.PatchError(f"{spec.node_name} affine UV orientation is mixed")
    if min(abs(value) for value in determinants) <= 1.0e-9:
        raise p.PatchError(f"{spec.node_name} affine UV triangle collapsed")
    return faces, uvs, selected_face_ids, report_topology


def build() -> tuple[bytes, dict[str, object]]:
    source = p._parse_outer(p.read_source_outer(shell.SOURCE), source=True).system
    output = bytearray(source)
    nodes = p._scene_nodes(source)
    _source_active, source_points = load_mask(
        SOURCE_MASK,
        SOURCE_MASK_PNG_SHA256,
        SOURCE_MASK_RGBA_SHA256,
        EXPECTED_SOURCE_ACTIVE_TEXELS,
    )
    guarded_active, _guarded_points = load_mask(
        GUARDED_MASK,
        GUARDED_MASK_PNG_SHA256,
        GUARDED_MASK_RGBA_SHA256,
        EXPECTED_GUARDED_ACTIVE_TEXELS,
    )
    minimum_v = float(source_points[:, 1].min())
    maximum_v = float(source_points[:, 1].max())
    reports: list[dict[str, object]] = []
    for spec in p.LODS:
        p._validate_layout(source, spec, nodes[spec.node_index])
        positions, normals, right_outer = shell.shell_geometry(source, spec)
        right_faces, source_uvs, selected_face_ids, report_topology = affine_patch(
            spec,
            positions,
            normals,
            right_outer,
            guarded_active,
            source_points,
            minimum_v,
            maximum_v,
        )
        source_vertices = sorted({index for face in right_faces for index in face})
        per_side = len(source_vertices)
        capacity = SIDE_CAPACITY[spec.node_name]
        if per_side > capacity:
            raise p.PatchError(
                f"{spec.node_name} affine patch uses {per_side}/{capacity} side vertices"
            )
        right_ids = list(
            range(spec.carrier_vertex_start, spec.carrier_vertex_start + per_side)
        )
        left_start = spec.carrier_vertex_start + LEFT_START_OFFSET[spec.node_name]
        left_ids = list(range(left_start, left_start + per_side))
        right_map = dict(zip(source_vertices, right_ids))
        left_map = dict(zip(source_vertices, left_ids))
        projections: dict[int, p.Projection] = {}
        uvs: dict[int, tuple[float, float]] = {}
        for source_index in source_vertices:
            base = positions[source_index]
            normal = normals[source_index]
            point = p._add(base, p._mul(normal, shell.BIAS_CM))
            right, left = right_map[source_index], left_map[source_index]
            projections[right] = p.Projection(point, normal)
            projections[left] = p.Projection(
                (-point[0], point[1], point[2]),
                (-normal[0], normal[1], normal[2]),
            )
            uvs[right] = source_uvs[source_index]
            uvs[left] = source_uvs[source_index]
        right_carrier_faces = [
            tuple(right_map[index] for index in face) for face in right_faces
        ]
        left_carrier_faces = [
            (left_map[first], left_map[third], left_map[second])
            for first, second, third in right_faces
        ]
        right_strips = shell.stripify(right_carrier_faces)
        left_strips = shell.mirror_strips(
            right_strips,
            {right_map[index]: left_map[index] for index in source_vertices},
        )
        index_stream: list[int] = []
        for strip in (*right_strips, *left_strips):
            if index_stream:
                index_stream.append(0xFFFF)
            index_stream.extend(strip)
        encoded_word_count = len(index_stream)
        if encoded_word_count > spec.carrier_index_count:
            raise p.PatchError(
                f"{spec.node_name} affine strips use {encoded_word_count}/"
                f"{spec.carrier_index_count} words"
            )
        index_stream.extend(
            [index_stream[-1]] * (spec.carrier_index_count - len(index_stream))
        )
        triangles = p._triangles(index_stream)
        if len(triangles) != 2 * len(right_faces):
            raise p.PatchError(
                f"{spec.node_name} serialized {len(triangles)} triangles, expected "
                f"{2 * len(right_faces)}"
            )
        for index, uv in uvs.items():
            start = spec.stream_start + index * p.STRIDE
            output[start + 14 : start + 16] = shell.encode_uv(uv[0])
            output[start + 22 : start + 24] = shell.encode_uv(uv[1])
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
            "bounds_before_quantization": p._bounds(
                projection.position for projection in projections.values()
            ),
            "carrier_triangle_count": len(triangles),
            "encoded_index_word_count": encoded_word_count,
            "fixed_index_word_count": len(index_stream),
            "left_strip_count": len(left_strips),
            "node": spec.node_name,
            "right_outer_face_ids": selected_face_ids,
            "right_patch_topology": report_topology,
            "right_strip_count": len(right_strips),
            "terminal_degenerate_word_count": len(index_stream) - encoded_word_count,
            "used_vertex_count": len(projections),
        })
    payload = bytes(output)
    return payload, {
        "actual_clearance_cm": shell.BIAS_CM,
        "affine": {
            "front_z": FRONT_Z,
            "height": HEIGHT,
            "length": LENGTH,
            "top_y": TOP_Y,
            "u_y_slope": U_Y_SLOPE,
            "v_z_slope": V_Z_SLOPE,
        },
        "changed_byte_count": sum(a != b for a, b in zip(source, payload)),
        "lods": reports,
        "guarded_mask_png_sha256": GUARDED_MASK_PNG_SHA256,
        "guarded_mask_rgba_sha256": GUARDED_MASK_RGBA_SHA256,
        "guarded_u_offset": GUARD_U_OFFSET,
        "guarded_u_scale": GUARD_U_SCALE,
        "source_mask_png_sha256": SOURCE_MASK_PNG_SHA256,
        "source_mask_rgba_sha256": SOURCE_MASK_RGBA_SHA256,
        "output_scne_sha256": hashlib.sha256(payload).hexdigest(),
        "schema": "apf2k8_helmet_affine_shell_candidate/v1",
        "source_scne_sha256": hashlib.sha256(source).hexdigest(),
    }


def main() -> None:
    payload, report = build()
    DESTINATION.mkdir(mode=0o700, parents=True, exist_ok=True)
    (DESTINATION / "helmet00.scne").write_bytes(payload)
    (DESTINATION / "candidate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
