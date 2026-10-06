#!/usr/bin/env python3
"""Read-only near-coplanar crowd/structure overlap candidates, with native IDs.

python3 tools/b765/s1_coplanar.py --files DIR --out pairs.json --names s07dd.iff
python3 tools/b765/s1_audit.py --files DIR --out DIR --near-coplanar-only --names s07dd.iff

Outputs geometry measurements, not a depth-buffer, alpha or gameplay verdict.
The standalone --summary JSON can link a compact report to the full pair list.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from tools.b765 import s1_audit as audit, s1_geometry as geometry
from mod_editor.core import nfl2k5_scne_builder as builder

DISTANCE_MAX_M = 0.002
NORMAL_ABS_DOT_MIN = 0.99999
OVERLAP_AREA_MIN_M2 = 1e-7
PROOF = ("Positive-area projected overlap of near-parallel native triangles; "
         "the second triangle's vertices lie within the stated distance of the first plane. "
         "Depth precision, alpha, culling, sorting and gameplay visibility are not simulated.")


def signed_area(points):
    """Signed convex-polygon area in 2D; translate to avoid coordinate cancellation."""
    points = np.asarray(points, dtype=float)
    if len(points) < 3:
        return 0.0
    local = points - points[0]
    return float(np.sum(local[:, 0] * np.roll(local[:, 1], -1)
                        - local[:, 1] * np.roll(local[:, 0], -1)) / 2)


def cross2(first, second):
    return first[0] * second[1] - first[1] * second[0]


def overlap_polygon(first, second, normal):
    """Clip one triangle by another in the dominant projection, returning first-plane points.

    The clipping half-planes include their boundaries. An edge or vertex contact
    consequently has zero area and is excluded by the measurement's area test.
    """
    first, second, normal = (np.asarray(value, dtype=float)
                             for value in (first, second, normal))
    if first.shape != (3, 3) or second.shape != (3, 3) or normal.shape != (3,):
        raise ValueError("overlap requires two FLOAT3 triangles and one normal")
    if not all(np.isfinite(value).all() for value in (first, second, normal)):
        raise ValueError("non-finite overlap coordinates")
    length = float(np.linalg.norm(normal))
    if length == 0:
        raise ValueError("overlap normal is zero")
    normal = normal / length
    drop = int(np.argmax(np.abs(normal)))
    first2, second2 = (np.delete(value, drop, axis=1) for value in (first, second))
    winding = 1 if signed_area(second2) > 0 else -1
    polygon = list(first2)
    for index in range(3):
        start = second2[index]
        edge = second2[(index + 1) % 3] - start
        if not polygon:
            return np.empty((0, 3))
        clipped = []
        previous = polygon[-1]
        previous_value = winding * cross2(edge, previous - start)
        for point in polygon:
            value = winding * cross2(edge, point - start)
            if (value >= 0) != (previous_value >= 0):
                clipped.append(previous + (point - previous)
                               * previous_value / (previous_value - value))
            if value >= 0:
                clipped.append(point)
            previous, previous_value = point, value
        polygon = clipped
    if len(polygon) < 3:
        return np.empty((0, 3))
    polygon = np.asarray(polygon)
    kept = [index for index in range(3) if index != drop]
    world = np.zeros((len(polygon), 3))
    world[:, kept] = polygon
    world[:, drop] = (normal @ first[0] - world[:, kept] @ normal[kept]) / normal[drop]
    return world


def overlap_area(first, second, normal):
    polygon = overlap_polygon(first, second, normal)
    if len(polygon) < 3:
        return 0.0
    normal = np.asarray(normal, dtype=float).copy()
    normal /= np.linalg.norm(normal)
    drop = int(np.argmax(np.abs(normal)))
    return abs(signed_area(np.delete(polygon, drop, axis=1))) / abs(float(normal[drop]))


def thresholds(distance_max_m, normal_abs_dot_min, overlap_area_min_m2):
    if not all(math.isfinite(value) for value in
               (distance_max_m, normal_abs_dot_min, overlap_area_min_m2)):
        raise ValueError("thresholds must be finite")
    if distance_max_m < 0 or overlap_area_min_m2 < 0 or not 0 <= normal_abs_dot_min <= 1:
        raise ValueError("distance/area thresholds must be nonnegative; cosine must be in [0,1]")


def native_faces(scene):
    """Float positions in metres, positive-area faces, and exact native shape/submesh/vertex IDs."""
    nodes = defaultdict(list)
    for index, node in enumerate(scene.nodes):
        nodes[node.shape_name].append((index, node))
    faces = []
    for shape_id, shape in enumerate(scene.shapes):
        selected = []
        for submesh_id, submesh in enumerate(shape.submeshes):
            material = scene.materials[submesh.material].name
            crowd = material == "crowd"
            if crowd or (not material.startswith("env_") and any(
                    word in material.lower() for word in
                    ("seat", "deck", "concrete", "rail", "portal", "stairs", "soffit"))):
                selected.append((submesh_id, submesh, material, crowd))
        if not selected:
            continue
        if shape.stride(0) != 12 or shape.streams[0] is None:
            raise ValueError(f"{shape.name}: selected geometry is not native FLOAT3")
        # Generated stadium shapes carry the retail template's single root
        # record. The native model decoder treats <=1 transform as unskinned;
        # reject multi-transform geometry whose positions need skin evaluation.
        if len(shape.transforms) > 1:
            raise ValueError(f"{shape.name}: selected geometry has multiple native shape transforms")
        if not nodes[shape.name]:
            raise ValueError(f"{shape.name}: selected geometry has no native node")
        for _, node in nodes[shape.name]:
            for matrix_name in ("matrix14", "matrix1c"):
                matrix = np.frombuffer(getattr(node, matrix_name), dtype="<f4").reshape(4, 4)
                if not np.array_equal(matrix, np.eye(4)):
                    raise ValueError(f"{node.name}: non-identity node {matrix_name}; local overlap is unsafe")
        points = np.frombuffer(shape.streams[0], dtype="<f4").reshape(-1, 3).astype(float) / 100
        if not np.isfinite(points).all():
            raise ValueError(f"{shape.name}: non-finite native position")
        for submesh_id, submesh, material, crowd in selected:
            for mode, indices in builder.decode_words(submesh.words):
                for triangle in audit.triangles(mode, indices):
                    if min(triangle) < 0 or max(triangle) >= len(points):
                        raise ValueError(f"{shape.name}: native triangle index out of range")
                    positions = points[list(triangle)]
                    normal = np.cross(positions[1] - positions[0], positions[2] - positions[0])
                    length = float(np.linalg.norm(normal))
                    if length < 1e-7:
                        continue  # no strip connector or zero-area face
                    identity = dict(shape=shape_id, name=shape.name, submesh=submesh_id,
                                    material=material, vertices=list(triangle),
                                    node_indices=[index for index, _ in nodes[shape.name]])
                    faces.append((positions, normal / length, identity, crowd))
    return faces


def measure_scene(scene, *, distance_max_m=DISTANCE_MAX_M,
                  normal_abs_dot_min=NORMAL_ABS_DOT_MIN,
                  overlap_area_min_m2=OVERLAP_AREA_MIN_M2):
    thresholds(distance_max_m, normal_abs_dot_min, overlap_area_min_m2)
    faces = native_faces(scene)
    candidates, compared = [], 0
    if faces:
        points = np.asarray([face[0] for face in faces])
        normals = np.asarray([face[1] for face in faces])
        centres = points.mean(1)
        radii = np.linalg.norm(points - centres[:, None, :], axis=2).max(1)
        tree, maximum_radius = audit._spatial_index(centres), float(radii.max())
        for first, face in enumerate(faces):
            if not face[3]:
                continue
            nearby = np.asarray(tree.query_ball_point(
                centres[first], radii[first] + maximum_radius + distance_max_m), dtype=int)
            nearby = nearby[np.linalg.norm(centres[nearby] - centres[first], axis=1)
                            <= radii[first] + radii[nearby] + distance_max_m]
            nearby = nearby[np.abs(normals[nearby] @ normals[first]) >= normal_abs_dot_min]
            for second in sorted(nearby.tolist()):
                if second == first or (faces[second][3] and second < first):
                    continue
                distances = (points[second] - points[first, 0]) @ normals[first]
                maximum_distance = float(np.max(np.abs(distances)))
                if maximum_distance > distance_max_m:
                    continue
                compared += 1
                area = overlap_area(points[first], points[second], normals[first])
                if area <= overlap_area_min_m2:
                    continue
                dot = float(normals[first] @ normals[second])
                candidates.append(dict(first=faces[first][2], second=faces[second][2],
                                       normal_abs_dot=abs(dot), normal_dot=dot,
                                       normal_relationship="same_facing" if dot >= 0 else "opposite_facing",
                                       plane_distance_max_m=maximum_distance,
                                       projected_overlap_area_m2=area))
    surface_pairs = Counter(pair["second"]["material"] for pair in candidates)
    return dict(geometry_sha256=audit.geometry_sha(scene), positive_faces=len(faces),
                crowd_faces=sum(face[3] for face in faces),
                parallel_near_plane_pairs_compared=compared, candidate_count=len(candidates),
                crowd_crowd_count=surface_pairs.get("crowd", 0),
                crowd_surface_count=sum(count for material, count in surface_pairs.items() if material != "crowd"),
                second_material_counts=dict(sorted(surface_pairs.items())),
                same_facing_count=sum(pair["normal_dot"] >= 0 for pair in candidates),
                opposite_facing_count=sum(pair["normal_dot"] < 0 for pair in candidates),
                candidates=candidates)


def measure(data, name, **options):
    _, _, _, scene = audit.scene_data(data)
    return dict(name=name, bundle_sha256=geometry.sha(data), **measure_scene(scene, **options))


def read_binary(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(descriptor, "rb") as source:
        return source.read()


def run(files, names, output, *, summary=None, **options):
    """Measure selected source files, then write diagnostic JSON only; never modify native resources."""
    files, output = Path(files), Path(output)
    if not names:
        raise ValueError("select at least one native resource with --names")
    if any(Path(name).name != name or not name.endswith(".iff") for name in names):
        raise ValueError("--names accepts native .iff basenames only")
    if len(set(names)) != len(names):
        raise ValueError("duplicate native resource name")
    inputs = {(files / name).resolve() for name in names}
    outputs = [output] + ([Path(summary)] if summary else [])
    if len({path.resolve() for path in outputs}) != len(outputs):
        raise ValueError("full diagnostic and summary output paths must differ")
    for path in outputs:
        if path.resolve() in inputs or path.suffix.lower() != ".json" or path.name == "stadium_audit.json":
            raise ValueError("diagnostic outputs must be separate JSON files, preserving native inputs and stadium_audit.json")
    document = dict(schema="b765_s1_near_coplanar_diagnostic/v1",
                    scope="Native local geometry; selected node matrices14/1c required exact identity. "
                          "Repeated identity nodes are listed and geometry is counted once per native shape.",
                    distance_max_m=options.get("distance_max_m", DISTANCE_MAX_M),
                    normal_abs_dot_min=options.get("normal_abs_dot_min", NORMAL_ABS_DOT_MIN),
                    overlap_area_min_m2=options.get("overlap_area_min_m2", OVERLAP_AREA_MIN_M2),
                    proof=PROOF, resources=[])
    thresholds(document["distance_max_m"], document["normal_abs_dot_min"], document["overlap_area_min_m2"])
    for name in names:
        document["resources"].append(measure(read_binary(files / name), name, **options))
    geometry.write_atomic(output, geometry.json_bytes(document))
    if summary:
        compact = dict(schema="b765_s1_near_coplanar_summary/v1", proof=PROOF,
                       diagnostic_file=str(output.resolve()), diagnostic_sha256=geometry.sha(read_binary(output)),
                       distance_max_m=document["distance_max_m"], normal_abs_dot_min=document["normal_abs_dot_min"],
                       overlap_area_min_m2=document["overlap_area_min_m2"],
                       resources=[{key: value for key, value in row.items() if key != "candidates"}
                                  for row in document["resources"]])
        geometry.write_atomic(Path(summary), geometry.json_bytes(compact))
    for row in document["resources"]:
        print(f"{row['name']}: {row['candidate_count']} near-coplanar overlaps; "
              f"{row['crowd_crowd_count']} crowd/crowd; {row['crowd_surface_count']} crowd/surface")
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=Path, required=True)
    parser.add_argument("--names", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True, help="Full diagnostic JSON file")
    parser.add_argument("--summary", type=Path, help="Optional compact JSON link and counts")
    parser.add_argument("--distance-max-m", type=float, default=DISTANCE_MAX_M)
    parser.add_argument("--normal-abs-dot-min", type=float, default=NORMAL_ABS_DOT_MIN)
    parser.add_argument("--overlap-area-min-m2", type=float, default=OVERLAP_AREA_MIN_M2)
    args = parser.parse_args(argv)
    try:
        run(args.files, args.names, args.out, summary=args.summary, distance_max_m=args.distance_max_m,
            normal_abs_dot_min=args.normal_abs_dot_min, overlap_area_min_m2=args.overlap_area_min_m2)
    except (ValueError, OSError) as error:
        print(f"s1_coplanar: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
