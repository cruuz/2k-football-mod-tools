#!/usr/bin/env python3
"""Prototype a shell-native, harmonic-UV full-shell Eagles crest carrier."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_wrap_patch as p  # noqa: E402
import apf_helmet_grid_prototype as grid  # noqa: E402


SOURCE = grid.SOURCE
DESTINATION = Path(
    "/media/noah/Storage/.codex-tmp/"
    "apf-eagles-v20-c13-shell-patch-candidate-1"
)
BIAS_CM = 0.14
ACTIVE_V_MIN = 122 / 512
ACTIVE_V_MAX = 390 / 512
LOW_SUPERELLIPSE_SCALE = 1.207176598403988
LOW_SUPERELLIPSE_PHASE = 13 / 35
LOW_SUPERELLIPSE_SAMPLES = 65_536

# Deterministic connected-disk selectors proved by the bounded searches.
HIGH_SELECTOR = (
    0.44248532650908373,
    0.5400921083059264,
    1.8706409837897826,
    1.035254844501033,
    0.3410482089217741,
)
HIGH_RIGHT_OUTER_FACE_IDS = (
    137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150,
    151, 152, 153, 154, 155, 156, 157, 158, 160, 161, 162, 163, 164, 165,
    166, 167, 168, 169, 172, 173, 174, 176, 177, 178, 179, 180, 184, 195,
    196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209,
    210, 211, 212, 213, 214, 222, 223, 224, 225, 226, 227, 228, 229, 230,
    231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244,
    245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 258, 259, 260,
    261, 262, 263, 264, 277, 278, 279, 330, 334, 344, 346, 347, 352, 353,
    354, 355, 356, 357, 358, 359, 360, 361, 362, 363, 364, 365, 366, 377,
    378, 379, 380, 381, 382, 388, 389, 390, 391, 392, 393, 394, 395, 396,
    397, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410,
    411, 412, 413, 414, 415, 416, 417, 418, 419, 420, 421, 422, 423, 424,
    425, 426, 427, 428, 429, 430, 431, 432, 433, 434, 435, 436, 437, 438,
    439, 440, 441, 442, 443, 444, 445, 446, 447, 448, 449, 450, 451, 452,
    453, 454, 455, 456, 457, 458, 459, 460, 461, 462, 463, 464, 465, 466,
    477, 478, 479, 480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490,
    491, 495, 636, 642, 643, 644, 645, 650, 651, 652, 653, 663, 664, 665,
    667, 668, 669, 671, 681, 682, 683, 684, 685, 686, 687, 688, 689, 690,
    691, 692, 693, 694, 719, 720, 721, 722, 723, 724, 725, 726, 727, 728,
    729, 730,
)
LOW_SELECTOR = (
    0.4471653394174435,
    0.47645453271438704,
    0.8603945015166623,
    0.7165739860211477,
    0.02867448207070411,
    0.2124931401657043,
)


def inverse_y(value: float) -> float:
    knots = ((0.0, 18.0), (122 / 512, 17.5), (390 / 512, 6.0), (1.0, 4.5))
    if value >= knots[0][1]:
        return 0.0
    if value <= knots[-1][1]:
        return 1.0
    for (first_v, first_y), (second_v, second_y) in zip(knots, knots[1:]):
        if value >= second_y:
            return first_v + (second_v - first_v) * (
                (value - first_y) / (second_y - first_y)
            )
    raise AssertionError("unreachable inverse-y interval")


def shell_geometry(
    source: bytes, spec: p.LodSpec,
) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[float, float, float]],
    list[tuple[int, int, int]],
]:
    positions = [p._decode_position(source, spec, index) for index in range(spec.vertex_count)]
    normals = [
        p._unit(p._decode_vec3(source, spec.stream_start + index * p.STRIDE + 8))
        for index in range(spec.vertex_count)
    ]
    source_indices = p._indices(source, spec)
    shell_triangles = p._triangles(source_indices[
        spec.shell_index_start : spec.shell_index_start + spec.shell_index_count
    ])
    right_outer: list[tuple[int, int, int]] = []
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
        if p._dot(average, radial) > 0.0 and all(
            positions[index][0] >= -1.0e-6 for index in triangle
        ):
            right_outer.append(triangle)
    return positions, normals, right_outer


def physical_uvs(
    positions: list[tuple[float, float, float]],
    right_outer: list[tuple[int, int, int]],
) -> dict[int, tuple[float, float]]:
    output: dict[int, tuple[float, float]] = {}
    for index in {item for triangle in right_outer for item in triangle}:
        _x, y_value, z_value = positions[index]
        rear_z, front_z = grid.z_limits(y_value, right_outer, positions)
        denominator = rear_z - front_z
        progress = 0.5 if abs(denominator) < 1.0e-8 else (
            (z_value - front_z) / denominator
        )
        output[index] = (progress, inverse_y(y_value))
    return output


def select_patch(
    spec: p.LodSpec,
    right_outer: list[tuple[int, int, int]],
    physical_uv: dict[int, tuple[float, float]],
) -> list[tuple[int, int, int]]:
    vertices = sorted({index for triangle in right_outer for index in triangle})
    if spec.node_name == "helmet_hi":
        if len(HIGH_RIGHT_OUTER_FACE_IDS) != 268:
            raise p.PatchError("high audited face-ID count differs")
        # Audit IDs are based on the exterior list with its leading diagnostic
        # face omitted; this parser retains that face, hence the proved +1.
        seed_position = HIGH_RIGHT_OUTER_FACE_IDS.index(334)
        if right_outer[HIGH_RIGHT_OUTER_FACE_IDS[seed_position] + 1] != (1833, 1831, 1835):
            raise p.PatchError("high audited local face-ID basis drifted")
        faces = [right_outer[index + 1] for index in HIGH_RIGHT_OUTER_FACE_IDS]
        # These are the only two boundary ears collapsed by the audited
        # physical-corner atlas.  Removing them preserves a connected disk and
        # avoids spending carrier triangles on zero-area UV slivers.
        collapsed_ears = {
            (1687, 1711, 1689),
            (1857, 1855, 1859),
        }
        missing = collapsed_ears - set(faces)
        if missing:
            raise p.PatchError(f"high collapsed-ear basis drifted: {sorted(missing)}")
        faces = [triangle for triangle in faces if triangle not in collapsed_ears]
        if len(faces) != 266:
            raise p.PatchError(f"high pruned patch produced {len(faces)} faces")
        return faces

    center_u, center_v, scale_u, scale_v, tilt, linear = LOW_SELECTOR

    def score(index: int) -> float:
        u_value, v_value = physical_uv[index]
        du, dv = u_value - center_u, v_value - center_v
        return (
            (du / scale_u) ** 2
            + (dv / scale_v) ** 2
            + tilt * du * dv / (scale_u * scale_v)
            + linear * du
        )

    order = sorted(vertices, key=score)
    rank = {vertex: number for number, vertex in enumerate(order)}
    faces = [
        triangle for triangle in right_outer
        if max(rank[index] for index in triangle) <= 70
    ]
    if len(faces) != 91:
        raise p.PatchError(f"low selector produced {len(faces)} faces")
    return faces


def patch_topology(
    faces: list[tuple[int, int, int]],
) -> tuple[list[int], dict[str, int]]:
    vertices = {index for triangle in faces for index in triangle}
    edges = Counter(
        tuple(sorted((triangle[axis], triangle[(axis + 1) % 3])))
        for triangle in faces
        for axis in range(3)
    )
    if any(count not in (1, 2) for count in edges.values()):
        raise p.PatchError("selected shell patch is non-manifold")
    boundary_edges = [edge for edge, count in edges.items() if count == 1]
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in boundary_edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    if not adjacency or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise p.PatchError("selected shell patch boundary is not a simple loop")
    start = min(adjacency)
    boundary = [start]
    previous: int | None = None
    current = start
    while True:
        options = sorted(adjacency[current] - ({previous} if previous is not None else set()))
        following = options[0]
        if following == start:
            break
        if following in boundary:
            raise p.PatchError("selected shell patch boundary self-closes early")
        boundary.append(following)
        previous, current = current, following
    if len(boundary) != len(adjacency):
        raise p.PatchError("selected shell patch has multiple boundary loops")
    euler = len(vertices) - len(edges) + len(faces)
    if euler != 1:
        raise p.PatchError(f"selected shell patch Euler characteristic is {euler}")
    return boundary, {
        "boundary_edge_count": len(boundary_edges),
        "edge_count": len(edges),
        "euler_characteristic": euler,
        "face_count": len(faces),
        "vertex_count": len(vertices),
    }


def boundary_square(
    spec: p.LodSpec,
    boundary: list[int],
    faces: list[tuple[int, int, int]],
    positions: list[tuple[float, float, float]],
    physical_uv: dict[int, tuple[float, float]],
) -> dict[int, tuple[float, float]]:
    if spec.node_name == "helmet_hi":
        if len(boundary) != 54:
            raise p.PatchError(
                f"high physical atlas expected 54 boundary vertices, found {len(boundary)}"
            )
        # Homologous to the low-LOD atlas: seam/lower -> outer/lower ->
        # outer/upper -> seam/upper.  The audited reverse walk makes the v3
        # root meet the crown seam and sends its feathers to the posterior.
        ordered = [boundary[52], *reversed(boundary[:52]), boundary[53]]
        corners = [0, 31, 42, 53]
        corner_vertices = [ordered[index] for index in corners]
        if corner_vertices != [1835, 1849, 1897, 1831]:
            raise p.PatchError(
                f"high homologous corner basis drifted: {corner_vertices}"
            )
    else:
        if len(boundary) != 35:
            raise p.PatchError(
                f"low superellipse expected 35 boundary vertices, found {len(boundary)}"
            )
        # A strict convex n=4 envelope fitted to every active v3 texel center.
        # Its phase was exhaustively chosen on the native low shell boundary;
        # uniform harmonic interiors then remain positive and exceptionally
        # well conditioned without collapsing the four boundary-ear faces.
        theta = (
            np.arange(LOW_SUPERELLIPSE_SAMPLES, dtype=np.float64)
            * (2.0 * math.pi / LOW_SUPERELLIPSE_SAMPLES)
        )
        cosine, sine = np.cos(theta), np.sin(theta)
        power = 0.5  # 2 / n for n=4.
        target = np.column_stack((
            0.5 + 0.5 * LOW_SUPERELLIPSE_SCALE
            * np.sign(cosine) * np.abs(cosine) ** power,
            0.5 + (134 / 512) * LOW_SUPERELLIPSE_SCALE
            * np.sign(sine) * np.abs(sine) ** power,
        ))
        target_edges = np.linalg.norm(np.roll(target, -1, axis=0) - target, axis=1)
        target_cumulative = np.concatenate(((0.0,), np.cumsum(target_edges)))
        target_total = float(target_cumulative[-1])
        physical_edges = [
            p._length(p._sub(
                positions[boundary[(index + 1) % len(boundary)]],
                positions[boundary[index]],
            ))
            for index in range(len(boundary))
        ]
        physical_total = sum(physical_edges)
        if physical_total <= 1.0e-12 or target_total <= 1.0e-12:
            raise p.PatchError("low superellipse perimeter collapsed")
        output: dict[int, tuple[float, float]] = {}
        physical_distance = 0.0
        for vertex, edge_length in zip(boundary, physical_edges):
            progress = (LOW_SUPERELLIPSE_PHASE + physical_distance / physical_total) % 1.0
            wanted = progress * target_total
            sample = min(
                LOW_SUPERELLIPSE_SAMPLES - 1,
                max(0, int(np.searchsorted(target_cumulative, wanted, side="right") - 1)),
            )
            denominator = target_cumulative[sample + 1] - target_cumulative[sample]
            factor = (
                0.0 if denominator <= 1.0e-15
                else (wanted - target_cumulative[sample]) / denominator
            )
            following = (sample + 1) % LOW_SUPERELLIPSE_SAMPLES
            value = target[sample] + factor * (target[following] - target[sample])
            output[vertex] = (float(value[0]), float(value[1]))
            physical_distance += edge_length
        return output
    count = len(boundary)
    ordered = ordered + ordered
    corners = corners + [corners[0] + count]
    square = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0))
    output: dict[int, tuple[float, float]] = {}
    for side in range(4):
        first, last = corners[side], corners[side + 1]
        arc = ordered[first : last + 1]
        distances = [0.0]
        for before, after in zip(arc, arc[1:]):
            distances.append(
                distances[-1] + p._length(p._sub(positions[after], positions[before]))
            )
        denominator = distances[-1]
        if denominator <= 1.0e-12:
            raise p.PatchError("zero-length harmonic boundary arc")
        for index, distance in zip(arc, distances):
            factor = distance / denominator
            output[index] = (
                square[side][0] + factor * (square[side + 1][0] - square[side][0]),
                square[side][1] + factor * (square[side + 1][1] - square[side][1]),
            )
    if set(output) != set(boundary):
        raise p.PatchError("harmonic boundary assignment is incomplete")
    return output


def harmonic_uvs(
    faces: list[tuple[int, int, int]],
    boundary_uv: dict[int, tuple[float, float]],
) -> dict[int, tuple[float, float]]:
    vertices = sorted({index for triangle in faces for index in triangle})
    interior = [index for index in vertices if index not in boundary_uv]
    neighbors: dict[int, set[int]] = defaultdict(set)
    for triangle in faces:
        for axis in range(3):
            first, second = triangle[axis], triangle[(axis + 1) % 3]
            neighbors[first].add(second)
            neighbors[second].add(first)
    row = {vertex: number for number, vertex in enumerate(interior)}
    matrix = np.zeros((len(interior), len(interior)), dtype=np.float64)
    right = np.zeros((len(interior), 2), dtype=np.float64)
    for vertex in interior:
        number = row[vertex]
        matrix[number, number] = len(neighbors[vertex])
        for neighbor in neighbors[vertex]:
            if neighbor in row:
                matrix[number, row[neighbor]] -= 1.0
            else:
                right[number] += np.array(boundary_uv[neighbor])
    solved = np.linalg.solve(matrix, right) if interior else np.empty((0, 2))
    output = dict(boundary_uv)
    for vertex, value in zip(interior, solved):
        output[vertex] = (float(value[0]), float(value[1]))
    determinants = []
    for triangle in faces:
        first, second, third = (output[index] for index in triangle)
        determinants.append(
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )
    if min(abs(value) for value in determinants) <= 1.0e-9:
        raise p.PatchError("harmonic atlas contains a collapsed triangle")
    if min(determinants) < 0.0 < max(determinants):
        raise p.PatchError("harmonic atlas contains a flipped triangle")
    return output


def is_cyclic(
    wanted: tuple[int, int, int], actual: tuple[int, int, int],
) -> bool:
    return actual in (
        wanted,
        (wanted[1], wanted[2], wanted[0]),
        (wanted[2], wanted[0], wanted[1]),
    )


def stripify(faces: list[tuple[int, int, int]]) -> list[list[int]]:
    lookup = {frozenset(triangle): triangle for triangle in faces}
    if len(lookup) != len(faces):
        raise p.PatchError("selected shell patch contains duplicate faces")
    remaining = set(lookup)
    strips: list[list[int]] = []
    randomizer = random.Random(0)
    while remaining:
        candidates: list[tuple[int, float, list[int], set[frozenset[int]]]] = []
        sample = list(remaining)
        if len(sample) > 300:
            sample = randomizer.sample(sample, 300)
        for key in sample:
            face = lookup[key]
            for initial in (
                face,
                (face[1], face[2], face[0]),
                (face[2], face[0], face[1]),
            ):
                sequence = list(initial)
                used = {key}
                while True:
                    edge = {sequence[-2], sequence[-1]}
                    options = []
                    for other in remaining - used:
                        if edge <= other:
                            new = next(iter(other - edge))
                            triangle = (sequence[-2], sequence[-1], new)
                            if (len(sequence) - 2) & 1:
                                triangle = (triangle[1], triangle[0], triangle[2])
                            if is_cyclic(lookup[other], triangle):
                                options.append((other, new))
                    if not options:
                        break
                    other, new = randomizer.choice(options)
                    sequence.append(new)
                    used.add(other)
                candidates.append((len(used), randomizer.random(), sequence, used))
        _length, _tie, sequence, used = max(candidates)
        strips.append(sequence)
        remaining -= used
    return strips


def split_to_count(
    strips: list[list[int]], wanted: int, oriented_faces: set[tuple[int, int, int]],
) -> list[list[int]]:
    output = [list(strip) for strip in strips]
    while len(output) < wanted:
        number = max(range(len(output)), key=lambda item: len(output[item]))
        strip = output[number]
        if len(strip) <= 3:
            raise p.PatchError("cannot split strips to audited count")
        triangles = p._triangles(strip)
        prefix = strip[:-1]
        terminal = triangles[-1]
        wanted_face = next(
            (face for face in oriented_faces if set(face) == set(terminal)),
            None,
        )
        if wanted_face is None or not is_cyclic(wanted_face, terminal):
            raise p.PatchError("terminal strip face orientation drift")
        output[number] = prefix
        output.append(list(terminal))
    return output


def split_to_odd_count(
    strips: list[list[int]], wanted: int,
) -> list[list[int]]:
    """Split without changing faces until every strip is odd and count is exact."""

    output: list[list[int]] = []
    for strip in strips:
        triangles = p._triangles(strip)
        if len(triangles) % 2:
            output.append(list(strip))
        else:
            output.append(list(strip[:-1]))
            output.append(list(triangles[-1]))
    while len(output) < wanted:
        number = max(
            (item for item in range(len(output)) if len(p._triangles(output[item])) >= 3),
            key=lambda item: len(output[item]),
        )
        strip = output.pop(number)
        triangles = p._triangles(strip)
        output.extend((list(strip[:-2]), list(triangles[-2]), list(triangles[-1])))
    if len(output) != wanted or any(len(p._triangles(strip)) % 2 == 0 for strip in output):
        raise p.PatchError("could not reach audited odd strip count")
    return output


def oriented_face_path(faces: list[tuple[int, int, int]]) -> list[int]:
    """Encode one fixed adjacent face path with the requested winding."""

    for path in (faces, list(reversed(faces))):
        first = path[0]
        for initial in (
            first,
            (first[1], first[2], first[0]),
            (first[2], first[0], first[1]),
        ):
            sequence = list(initial)
            valid = True
            for wanted in path[1:]:
                edge = {sequence[-2], sequence[-1]}
                if not edge <= set(wanted):
                    valid = False
                    break
                new = next(iter(set(wanted) - edge))
                actual = (sequence[-2], sequence[-1], new)
                if (len(sequence) - 2) & 1:
                    actual = (actual[1], actual[0], actual[2])
                if not is_cyclic(wanted, actual):
                    valid = False
                    break
                sequence.append(new)
            if valid:
                return sequence
    raise p.PatchError("could not mirror fixed strip face path with outward winding")


def mirror_strips(
    right_strips: list[list[int]], mirror: dict[int, int],
) -> list[list[int]]:
    output: list[list[int]] = []
    for strip in right_strips:
        wanted_faces = [
            (mirror[first], mirror[third], mirror[second])
            for first, second, third in p._triangles(strip)
        ]
        mapped = [mirror[index] for index in strip]
        if len(wanted_faces) % 2:
            candidate = list(reversed(mapped))
        else:
            candidate = [mapped[0], *mapped]
        actual = p._triangles(candidate)
        if len(actual) != len(wanted_faces) or any(
            not is_cyclic(wanted, seen)
            for wanted, seen in zip(
                wanted_faces if len(wanted_faces) % 2 == 0 else reversed(wanted_faces),
                actual,
            )
        ):
            raise p.PatchError("mirrored strip winding proof failed")
        output.append(candidate)
    return output


def encode_uv(value: float) -> bytes:
    word = max(-32767, min(32767, round(value / 2.0 * 32767)))
    return struct.pack(">h", word)


def build() -> tuple[bytes, dict[str, object]]:
    source = p._parse_outer(p.read_source_outer(SOURCE), source=True).system
    output = bytearray(source)
    nodes = p._scene_nodes(source)
    reports: list[dict[str, object]] = []
    for spec in p.LODS:
        p._validate_layout(source, spec, nodes[spec.node_index])
        positions, normals, right_outer = shell_geometry(source, spec)
        physical_uv = physical_uvs(positions, right_outer)
        right_faces = select_patch(spec, right_outer, physical_uv)
        boundary, topology = patch_topology(right_faces)
        boundary_uv = boundary_square(
            spec, boundary, right_faces, positions, physical_uv
        )
        source_uv = harmonic_uvs(right_faces, boundary_uv)
        # The v3 artwork only occupies this vertical source interval.  Affinely
        # fitting the atlas to it lets those painted texels use the whole shell
        # patch without changing topology, winding, or overlap behavior.
        if spec.node_name == "helmet_hi":
            source_uv = {
                index: (
                    uv[0],
                    ACTIVE_V_MIN + (ACTIVE_V_MAX - ACTIVE_V_MIN) * uv[1],
                )
                for index, uv in source_uv.items()
            }
        source_vertices = sorted({index for triangle in right_faces for index in triangle})
        per_side = len(source_vertices)
        expected_vertices = 161 if spec.node_name == "helmet_hi" else 64
        if per_side != expected_vertices:
            raise p.PatchError(
                f"{spec.node_name} patch uses {per_side}, expected {expected_vertices} vertices"
            )
        right_ids = list(range(spec.carrier_vertex_start, spec.carrier_vertex_start + per_side))
        # High draw-2 has two unmodified W=+ reserve lanes between the sides;
        # left must start at the native W=- half, not immediately after right.
        left_start = (
            spec.carrier_vertex_start + 163
            if spec.node_name == "helmet_hi"
            else spec.carrier_vertex_start + per_side
        )
        left_ids = list(range(
            left_start,
            left_start + per_side,
        ))
        right_map = dict(zip(source_vertices, right_ids))
        left_map = dict(zip(source_vertices, left_ids))
        projections: dict[int, p.Projection] = {}
        uvs: dict[int, tuple[float, float]] = {}
        right_carrier_faces: list[tuple[int, int, int]] = []
        left_carrier_faces: list[tuple[int, int, int]] = []
        for source_index in source_vertices:
            base = positions[source_index]
            normal = normals[source_index]
            point = p._add(base, p._mul(normal, BIAS_CM))
            right = right_map[source_index]
            left = left_map[source_index]
            projections[right] = p.Projection(point, normal)
            projections[left] = p.Projection(
                (-point[0], point[1], point[2]),
                (-normal[0], normal[1], normal[2]),
            )
            uvs[right] = source_uv[source_index]
            uvs[left] = source_uv[source_index]
            for index in (right, left):
                start = spec.stream_start + index * p.STRIDE
                output[start + 14 : start + 16] = encode_uv(uvs[index][0])
                output[start + 22 : start + 24] = encode_uv(uvs[index][1])
        for first, second, third in right_faces:
            right_carrier_faces.append((right_map[first], right_map[second], right_map[third]))
            left_carrier_faces.append((left_map[first], left_map[third], left_map[second]))
        right_strips = stripify(right_carrier_faces)
        if spec.node_name == "helmet_hi":
            right_strips = split_to_count(right_strips, 85, set(right_carrier_faces))
            left_strips = split_to_count(
                stripify(left_carrier_faces), 86, set(left_carrier_faces)
            )
        else:
            left_strips = mirror_strips(
                right_strips,
                {right_map[index]: left_map[index] for index in source_vertices},
            )
        index_stream: list[int] = []
        for strip in [*right_strips, *left_strips]:
            if index_stream:
                index_stream.append(0xFFFF)
            index_stream.extend(strip)
        if len(index_stream) > spec.carrier_index_count:
            raise p.PatchError(f"{spec.node_name} strip stream exceeds fixed allocation")
        index_stream.extend([index_stream[-1]] * (spec.carrier_index_count - len(index_stream)))
        triangles = p._triangles(index_stream)
        expected_triangles = len(right_faces) * 2
        if len(triangles) != expected_triangles:
            raise p.PatchError(
                f"{spec.node_name} serialized {len(triangles)} != {expected_triangles} faces"
            )
        for index, uv in uvs.items():
            start = spec.stream_start + index * p.STRIDE
            output[start + 14 : start + 16] = encode_uv(uv[0])
            output[start + 22 : start + 24] = encode_uv(uv[1])
        tangents = p._tangents(bytes(output), spec, projections, triangles)
        for index, projection in projections.items():
            start = spec.stream_start + index * p.STRIDE
            output[start : start + 6] = p._encode_position(projection.position, spec)
            output[start + 8 : start + 14] = p._encode_vec3(projection.normal)
            output[start + 16 : start + 22] = p._encode_vec3(tangents[index])
        index_start = spec.index_offset + spec.carrier_index_start * 2
        output[index_start : index_start + spec.carrier_index_count * 2] = struct.pack(
            f">{spec.carrier_index_count}H", *index_stream
        )
        reports.append({
            "bounds_before_quantization": p._bounds(
                projection.position for projection in projections.values()
            ),
            "carrier_triangle_count": len(triangles),
            "index_word_count": len(index_stream),
            "left_strip_count": len(left_strips),
            "node": spec.node_name,
            "right_patch_topology": topology,
            "right_strip_count": len(right_strips),
            "terminal_degenerate_word_count": (
                2
            ),
            "used_vertex_count": len(projections),
        })
    payload = bytes(output)
    return payload, {
        "actual_clearance_cm": BIAS_CM,
        "changed_byte_count": sum(a != b for a, b in zip(source, payload)),
        "lods": reports,
        "output_scne_sha256": hashlib.sha256(payload).hexdigest(),
        "schema": "apf2k8_helmet_shell_patch_candidate/v1",
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
