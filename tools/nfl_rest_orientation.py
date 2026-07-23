#!/usr/bin/env python3
"""Prove NFL 2K5 rest orientation, twist helpers, and current-matrix space.

This is a bounded reverse-engineering validator, not a glTF exporter.  It
joins pinned default.xbe code/data with every serialized SCNE transform and a
deterministic numerical model of the recovered quaternion/matrix equations.
No coordinate-axis names or guessed skeletal assets are emitted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import BinaryIO, Iterable, Sequence

from nfl_outer import Archive, Entry, parse_archive
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_inventory import read_name, resolve_relative


SCHEMA = "nfl2k5_rest_orientation/v1"
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"

# End addresses are exclusive.  The whole executable is pinned first; these
# hashes keep each semantic claim tied to the exact code that implements it.
FUNCTION_RANGES = (
    ("build_current_hierarchy_generic", 0x000217F0, 0x00021851),
    ("render_object_dispatch", 0x00021860, 0x000218C3),
    ("build_skin_palette", 0x00022C00, 0x00022ECA),
    ("expand_local_hierarchy", 0x000233C0, 0x00023495),
    ("render_shape", 0x000243D0, 0x00024978),
    ("matrix_multiply_4x4", 0x00031110, 0x0003121C),
    ("player_twist_callback", 0x000901E0, 0x00090247),
    ("player_scene_setup", 0x00090570, 0x000911DE),
    ("player_twist_dispatch", 0x00091890, 0x000918AA),
    ("player_hierarchy_builder", 0x00093800, 0x00093849),
    ("coach_twist_callback", 0x00095B40, 0x00095BA9),
    ("coach_scene_setup", 0x00095D40, 0x00095F7E),
    ("coach_twist_dispatch", 0x00095FB0, 0x00096007),
    ("coach_hierarchy_builder", 0x00096050, 0x0009608B),
    ("referee_twist_callback", 0x00096590, 0x000965F9),
    ("referee_scene_setup", 0x00096600, 0x00096A15),
    ("referee_twist_dispatch", 0x00096A80, 0x00096ACC),
    ("referee_hierarchy_builder", 0x00096B20, 0x00096B4E),
    ("identity_matrix_array_a", 0x000DE760, 0x000DE7A7),
    ("identity_matrix_array_b", 0x001C0340, 0x001C0387),
    ("full_signed_twist", 0x001C2530, 0x001C2865),
    ("half_signed_twist", 0x001C2870, 0x001C2BC2),
    ("sample_and_compose_pose", 0x002176D0, 0x00217793),
    ("sample_pose_position", 0x002177A0, 0x002178D3),
    ("sample_pose_matrix", 0x002178E0, 0x00217A4F),
    ("quaternion_multiply", 0x003CA150, 0x003CA1DC),
    ("quaternion_rotate_vector", 0x003CA1E0, 0x003CA26E),
    ("quaternion_array_to_matrix", 0x003CA3D0, 0x003CA4D2),
)

CONSTANTS = {
    "zero": 0x004E4180,
    "half": 0x004E4184,
    "one": 0x004E419C,
    "negative_one": 0x004E5C7C,
}

TWIST_NAME_TABLES = {
    "player": (0x004EEAD4, 3),
    # The loop bounds are <0x004efe99 and <0x004eff41 respectively, so both
    # of these tables contain four entries (not three).
    "coach": (0x004EFE8C, 4),
    "referee": (0x004EFF34, 4),
}

SAMPLE_SHAPES = {
    (3, 113, "LO_res"): "player_LO_res",
    (346, 109, "ref_high"): "referee_high",
    (346, 109, "ref_low"): "referee_low",
    (348, 0, "coachBodyGrp1"): "coach_body",
    (348, 0, "coachLodGrp1"): "coach_lod",
}

TWIST_AXIS_SOURCES = {
    "player": ("player_LO_res", ("lhand", "rhand")),
    "coach": ("coach_body", ("ltwist", "rtwist")),
    "referee": ("referee_high", ("ltwist", "rtwist")),
}

PORTMES = [
    "// PORTME: prove the geometric source/target frames of 0x001C2530 and 0x001C2870.",
    "// PORTME: prove model-space versus world-space ownership at every 0x00022C00 caller.",
    "// PORTME: prove vector-lane axes, handedness, units, and root-motion composition.",
    "// PORTME: do not emit skeletal glTF from an incomplete rest-orientation contract.",
]


class RestOrientationError(ValueError):
    """A pinned executable, corpus, or numerical invariant failed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def xbe_reader(xbe: bytes, header: dict[str, object]):
    def read(va: int, size: int) -> bytes:
        for section in header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                return xbe[offset:offset + size]
        raise RestOrientationError(
            f"XBE VA range 0x{va:08x}+0x{size:x} is not raw-backed"
        )
    return read


def read_utf16le_z(read, va: int, limit: int = 256) -> str:
    units: list[int] = []
    for index in range(limit):
        unit = struct.unpack("<H", read(va + index * 2, 2))[0]
        if unit == 0:
            return bytes().join(struct.pack("<H", value) for value in units).decode(
                "utf-16le"
            )
        units.append(unit)
    raise RestOrientationError(f"unterminated UTF-16LE string at 0x{va:08x}")


def executable_evidence(xbe_path: Path, header_path: Path) -> dict[str, object]:
    xbe = xbe_path.read_bytes()
    md5 = hashlib.md5(xbe).hexdigest()
    if md5 != EXPECTED_XBE_MD5:
        raise RestOrientationError(f"unexpected NFL 2K5 XBE MD5 {md5}")
    header = json.loads(header_path.read_text(encoding="utf-8"))
    read = xbe_reader(xbe, header)

    functions = []
    for name, start, end in FUNCTION_RANGES:
        body = read(start, end - start)
        functions.append(
            {
                "name": name,
                "start": f"0x{start:08x}",
                "end_exclusive": f"0x{end:08x}",
                "size": len(body),
                "sha256": sha256(body),
            }
        )

    constants = {}
    for name, va in CONSTANTS.items():
        raw = read(va, 4)
        constants[name] = {
            "va": f"0x{va:08x}",
            "bits": f"0x{struct.unpack('<I', raw)[0]:08x}",
            "value": struct.unpack("<f", raw)[0],
        }
    expected_constants = {
        "zero": 0.0, "half": 0.5, "one": 1.0, "negative_one": -1.0,
    }
    if {name: item["value"] for name, item in constants.items()} != expected_constants:
        raise RestOrientationError("unexpected twist-helper constants")

    name_tables = {}
    for family, (table_va, count) in TWIST_NAME_TABLES.items():
        items = []
        for index in range(count):
            pointer = struct.unpack("<I", read(table_va + index * 4, 4))[0]
            items.append(
                {
                    "index": index,
                    "pointer_va": f"0x{pointer:08x}",
                    "name": read_utf16le_z(read, pointer),
                }
            )
        name_tables[family] = {
            "table_va": f"0x{table_va:08x}",
            "count": count,
            "items": items,
        }
    expected_names = {
        "player": ["head", "lhand", "rhand"],
        "coach": ["ltwist", "lwrist", "rtwist", "rwrist"],
        "referee": ["ltwist", "lwrist", "rtwist", "rwrist"],
    }
    for family, names in expected_names.items():
        actual = [item["name"] for item in name_tables[family]["items"]]
        if actual != names:
            raise RestOrientationError(f"{family} twist-name table is {actual}")

    return {
        "path": str(xbe_path),
        "md5": md5,
        "sha256": sha256(xbe),
        "header_path": str(header_path),
        "header_sha256": sha256_file(header_path),
        "function_ranges": functions,
        "constants": constants,
        "twist_name_tables": name_tables,
    }


class PersistentArchiveReader:
    """Read bounded entry ranges while keeping all pack files open."""

    def __init__(self, archive: Archive):
        self.archive = archive
        self.streams: list[BinaryIO] = []

    def __enter__(self) -> "PersistentArchiveReader":
        self.streams = [pack.path.open("rb") for pack in self.archive.packs]
        return self

    def __exit__(self, *_: object) -> None:
        for stream in self.streams:
            stream.close()
        self.streams = []

    def read(self, entry: Entry, relative_offset: int, size: int) -> bytes:
        if relative_offset < 0 or size < 0 or relative_offset + size > entry.size:
            raise RestOrientationError(
                f"entry {entry.table_index}: invalid range "
                f"0x{relative_offset:x}+0x{size:x}"
            )
        relative_end = relative_offset + size
        result = bytearray()
        entry_segment_start = 0
        for segment in entry.segments:
            entry_segment_end = entry_segment_start + segment.size
            part_start = max(relative_offset, entry_segment_start)
            part_end = min(relative_end, entry_segment_end)
            if part_start < part_end:
                stream = self.streams[segment.pack_ordinal]
                stream.seek(segment.pack_offset + part_start - entry_segment_start)
                part = stream.read(part_end - part_start)
                if len(part) != part_end - part_start:
                    raise RestOrientationError(
                        f"entry {entry.table_index}: short pack read"
                    )
                result.extend(part)
            entry_segment_start = entry_segment_end
            if part_end == relative_end:
                break
        if len(result) != size:
            raise RestOrientationError(
                f"entry {entry.table_index}: read {len(result)}/{size} bytes"
            )
        return bytes(result)


def pointer_name(data: bytes, field: int, limit: int, label: str) -> str:
    target = resolve_relative(data, field, limit, label)
    value = read_name(data, target, limit, label)
    if value is None:
        raise RestOrientationError(f"{label}: null name")
    return value


def identity_matrix() -> list[float]:
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def translated_matrix(x: float, y: float, z: float) -> list[float]:
    result = identity_matrix()
    result[12:15] = [f32(x), f32(y), f32(z)]
    return result


def matrix_multiply_f32(left: Sequence[float], right: Sequence[float]) -> list[float]:
    """Model 0x00031110's row-major MULPS/ADDPS order."""
    result = [0.0] * 16
    for row in range(4):
        for column in range(4):
            terms = [
                f32(left[row * 4 + inner] * right[inner * 4 + column])
                for inner in range(4)
            ]
            value = f32(terms[0] + terms[1])
            value = f32(value + terms[2])
            result[row * 4 + column] = f32(value + terms[3])
    return result


def matrix_max_error(left: Sequence[float], right: Sequence[float]) -> float:
    return max(abs(a - b) for a, b in zip(left, right))


def scan_hierarchy_corpus(
    index_path: Path,
    scan_path: Path,
    progress_every: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    archive = parse_archive(index_path)
    inventory, all_resources = parse_inventory(scan_path)
    resources = [record for record in all_resources if record.kind == "SCNE"]
    declared = int(inventory["summary"]["resource_kind_counts"]["SCNE"])
    if len(resources) != declared:
        raise RestOrientationError(
            f"SCNE inventory has {len(resources)}/{declared} records"
        )

    counts: Counter[str] = Counter()
    hierarchy_translation_error_max = 0.0
    inverse_bind_identity_error_max = 0.0
    local_rotation_identity_error_max = 0.0
    root_count_distribution: Counter[int] = Counter()
    sample_rows: list[dict[str, object]] = []

    with PersistentArchiveReader(archive) as source:
        for scene_index, resource in enumerate(resources):
            entry = archive.entries[resource.outer_index]
            span = source.read(entry, resource.chunk_offset, 0x20 + resource.stored_size)
            output, _ = decode_resource(span, resource)
            system_size = resource.word_08
            if len(output) != resource.word_08 + resource.word_0c:
                raise RestOrientationError(f"scene {scene_index}: decoded size differs")
            if output[0x0C:0x10] != b"SCNE":
                raise RestOrientationError(f"scene {scene_index}: missing SCNE marker")
            scene_name = pointer_name(
                output, 0x10, system_size, f"scene {scene_index} name"
            )
            descriptor = resolve_relative(
                output, 0x14, system_size, f"scene {scene_index} descriptor"
            )
            if descriptor is None or descriptor + 0x54 > system_size:
                raise RestOrientationError(f"scene {scene_index}: missing descriptor")
            shape_count = struct.unpack_from("<I", output, descriptor + 0x2C)[0]
            shape_start = resolve_relative(
                output, descriptor + 0x30, system_size,
                f"scene {scene_index} shape table",
            )
            if shape_count and shape_start is None:
                raise RestOrientationError(f"scene {scene_index}: null shape table")
            if shape_start is not None and shape_start + shape_count * 0x100 > system_size:
                raise RestOrientationError(
                    f"scene {scene_index}: shape table exceeds system part"
                )
            counts["scene_count"] += 1
            counts["shape_count"] += shape_count

            for shape_index in range(shape_count):
                assert shape_start is not None
                shape = shape_start + shape_index * 0x100
                shape_name = pointer_name(
                    output, shape + 0x40, system_size,
                    f"scene {scene_index} shape {shape_index} name",
                )
                transform_count = struct.unpack_from("<H", output, shape + 0x50)[0]
                transform_start = resolve_relative(
                    output, shape + 0x64, system_size,
                    f"scene {scene_index} shape {shape_index} transform table",
                )
                if transform_count and transform_start is None:
                    raise RestOrientationError(
                        f"scene {scene_index} shape {shape_index}: null transforms"
                    )
                if (
                    transform_start is not None
                    and transform_start + transform_count * 0x70 > system_size
                ):
                    raise RestOrientationError(
                        f"scene {scene_index} shape {shape_index}: transforms exceed system part"
                    )

                current: list[list[float]] = []
                root_count = 0
                sample = SAMPLE_SHAPES.get(
                    (resource.outer_index, resource.chunk_index, shape_name)
                )
                for transform_index in range(transform_count):
                    assert transform_start is not None
                    record = transform_start + transform_index * 0x70
                    absolute = struct.unpack_from("<4f", output, record + 0x40)
                    local = struct.unpack_from("<4f", output, record + 0x50)
                    parent = struct.unpack_from("<i", output, record + 0x64)[0]
                    if not all(math.isfinite(value) for value in absolute + local):
                        raise RestOrientationError(
                            f"scene {scene_index} shape {shape_index} transform "
                            f"{transform_index}: non-finite vector"
                        )
                    if absolute[3] != 1.0 or local[3] != 1.0:
                        raise RestOrientationError(
                            f"scene {scene_index} shape {shape_index} transform "
                            f"{transform_index}: non-homogeneous vector"
                        )
                    if parent == -1:
                        root_count += 1
                        parent_matrix = identity_matrix()
                    elif 0 <= parent < transform_index:
                        parent_matrix = current[parent]
                    else:
                        raise RestOrientationError(
                            f"scene {scene_index} shape {shape_index} transform "
                            f"{transform_index}: invalid parent {parent}"
                        )

                    # 0x003ca3d0([1,0,0,0]) is identity.  0x000233c0 then
                    # adds +0x50.xyz at m12..m14 and left-multiplies parent.
                    local_matrix = translated_matrix(*local[:3])
                    local_rotation_identity_error_max = max(
                        local_rotation_identity_error_max,
                        matrix_max_error(
                            [
                                local_matrix[0], local_matrix[1], local_matrix[2],
                                local_matrix[4], local_matrix[5], local_matrix[6],
                                local_matrix[8], local_matrix[9], local_matrix[10],
                            ],
                            [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
                        ),
                    )
                    expanded = matrix_multiply_f32(local_matrix, parent_matrix)
                    current.append(expanded)
                    translation_error = max(
                        abs(expanded[12 + axis] - absolute[axis])
                        for axis in range(3)
                    )
                    hierarchy_translation_error_max = max(
                        hierarchy_translation_error_max, translation_error
                    )
                    if translation_error > 0.00008:
                        raise RestOrientationError(
                            f"scene {scene_index} shape {shape_index} transform "
                            f"{transform_index}: identity hierarchy error {translation_error}"
                        )

                    inverse_bind = translated_matrix(
                        -absolute[0], -absolute[1], -absolute[2]
                    )
                    bind_palette = matrix_multiply_f32(inverse_bind, expanded)
                    bind_error = matrix_max_error(bind_palette, identity_matrix())
                    inverse_bind_identity_error_max = max(
                        inverse_bind_identity_error_max, bind_error
                    )
                    if bind_error > 0.00008:
                        raise RestOrientationError(
                            f"scene {scene_index} shape {shape_index} transform "
                            f"{transform_index}: bind palette error {bind_error}"
                        )

                    counts["transform_count"] += 1
                    counts["root_transform_count"] += int(parent == -1)
                    counts["nonroot_transform_count"] += int(parent != -1)
                    counts["hierarchy_translation_exact_component_count"] += sum(
                        expanded[12 + axis] == absolute[axis] for axis in range(3)
                    )
                    if sample is not None:
                        transform_name = pointer_name(
                            output, record + 0x60, system_size,
                            f"scene {scene_index} shape {shape_index} transform "
                            f"{transform_index} name",
                        )
                        sample_rows.append(
                            {
                                "sample": sample,
                                "outer_index": resource.outer_index,
                                "chunk_index": resource.chunk_index,
                                "scene_name": scene_name,
                                "shape_name": shape_name,
                                "transform_index": transform_index,
                                "transform_name": transform_name,
                                "parent_index": parent,
                                "local_x": local[0], "local_y": local[1],
                                "local_z": local[2],
                                "expanded_x": expanded[12],
                                "expanded_y": expanded[13],
                                "expanded_z": expanded[14],
                                "absolute_x": absolute[0],
                                "absolute_y": absolute[1],
                                "absolute_z": absolute[2],
                                "hierarchy_error": translation_error,
                                "inverse_bind_identity_error": bind_error,
                            }
                        )
                root_count_distribution[root_count] += 1
                if root_count != 1:
                    raise RestOrientationError(
                        f"scene {scene_index} shape {shape_index}: {root_count} roots"
                    )

            if progress_every and (scene_index + 1) % progress_every == 0:
                print(
                    f"validated {scene_index + 1}/{len(resources)} SCNE hierarchies",
                    file=sys.stderr, flush=True,
                )

    if len(sample_rows) != 125:
        raise RestOrientationError(f"found {len(sample_rows)}/125 sample transforms")
    return (
        {
            "source_index": str(index_path),
            "source_index_sha256": sha256_file(index_path),
            "resource_scan": str(scan_path),
            "resource_scan_sha256": sha256_file(scan_path),
            "counts": {key: counts[key] for key in sorted(counts)},
            "root_count_distribution": {
                str(key): root_count_distribution[key]
                for key in sorted(root_count_distribution)
            },
            "hierarchy_translation_error_max": hierarchy_translation_error_max,
            "inverse_bind_identity_error_max": inverse_bind_identity_error_max,
            "local_rotation_identity_error_max": local_rotation_identity_error_max,
        },
        sorted(
            sample_rows,
            key=lambda item: (str(item["sample"]), int(item["transform_index"])),
        ),
    )


def dot3(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(left[index] * right[index] for index in range(3))


def cross3(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def normalize3(value: Sequence[float]) -> tuple[float, float, float]:
    length = math.sqrt(dot3(value, value))
    if not math.isfinite(length) or length == 0.0:
        raise RestOrientationError(f"cannot normalize axis {tuple(value)}")
    return tuple(value[index] / length for index in range(3))


def quaternion_multiply(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float, float]:
    """0x003ca150 Hamilton product, scalar-first [w,x,y,z]."""
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return (
        lw * rw - (lx * rx + ly * ry + lz * rz),
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    )


def quaternion_conjugate(value: Sequence[float]) -> tuple[float, float, float, float]:
    return (value[0], -value[1], -value[2], -value[3])


def quaternion_normalize(value: Sequence[float]) -> tuple[float, float, float, float]:
    length = math.sqrt(sum(component * component for component in value))
    if length == 0.0:
        raise RestOrientationError("cannot normalize zero quaternion")
    return tuple(component / length for component in value)


def quaternion_rotate_vector(
    quaternion: Sequence[float], vector: Sequence[float]
) -> tuple[float, float, float]:
    pure = (0.0, vector[0], vector[1], vector[2])
    result = quaternion_multiply(
        quaternion_multiply(quaternion, pure), quaternion_conjugate(quaternion)
    )
    return (result[1], result[2], result[3])


def quaternion_from_axis_angle(
    axis: Sequence[float], angle_radians: float
) -> tuple[float, float, float, float]:
    unit = normalize3(axis)
    half = angle_radians * 0.5
    sine = math.sin(half)
    return (math.cos(half), unit[0] * sine, unit[1] * sine, unit[2] * sine)


def quaternion_to_row_matrix(value: Sequence[float]) -> list[float]:
    """Exact 0x003ca3d0 equation (binary64 semantic model)."""
    w, x, y, z = value
    return [
        1.0 - 2.0 * (y * y + z * z),
        2.0 * x * y + 2.0 * z * w,
        2.0 * x * z - 2.0 * y * w,
        0.0,
        2.0 * x * y - 2.0 * z * w,
        1.0 - 2.0 * (z * z + x * x),
        2.0 * w * x + 2.0 * y * z,
        0.0,
        2.0 * x * z + 2.0 * y * w,
        2.0 * y * z - 2.0 * w * x,
        1.0 - 2.0 * (y * y + x * x),
        0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def row_rotate(vector: Sequence[float], matrix: Sequence[float]) -> tuple[float, float, float]:
    return tuple(
        sum(vector[row] * matrix[row * 4 + column] for row in range(3))
        for column in range(3)
    )


def extract_signed_twist(
    bind_vector: Sequence[float], source: Sequence[float], half_angle: bool,
) -> tuple[float, float, float, float]:
    """Semantic model of 0x001c2530 / 0x001c2870.

    Runtime setup copies serialized +0x50.xyz and forcibly sets its fourth
    component to zero, so this model intentionally accepts only xyz.
    """
    bind = tuple(bind_vector[:3])
    norm_squared = dot3(bind, bind)
    if norm_squared == 0.0:
        raise RestOrientationError("twist helper received a zero bind vector")
    if bind[0] == 0.0 and bind[1] == 0.0:
        perpendicular = (1.0, 0.0, 0.0)
    else:
        perpendicular = (-bind[1], bind[0], 0.0)
    rotated = quaternion_rotate_vector(source, perpendicular)
    projection_scale = dot3(rotated, bind) / norm_squared
    projected = tuple(
        rotated[index] - bind[index] * projection_scale for index in range(3)
    )
    projected_length = math.sqrt(dot3(projected, projected))
    perpendicular_length = math.sqrt(dot3(perpendicular, perpendicular))
    if projected_length == 0.0 or perpendicular_length == 0.0:
        raise RestOrientationError("twist projection is degenerate")
    cosine = dot3(perpendicular, projected) / (
        perpendicular_length * projected_length
    )
    cosine = min(1.0, max(-1.0, cosine))
    signed_inverse_length = 1.0 / math.sqrt(norm_squared)
    if dot3(cross3(perpendicular, projected), bind) < 0.0:
        signed_inverse_length = -signed_inverse_length

    if half_angle:
        full_half_cosine = math.sqrt((1.0 + cosine) * 0.5)
        scalar = math.sqrt((1.0 + full_half_cosine) * 0.5)
        vector_scale = math.sqrt((1.0 - full_half_cosine) * 0.5)
    else:
        scalar = math.sqrt((1.0 + cosine) * 0.5)
        vector_scale = math.sqrt((1.0 - cosine) * 0.5)
    vector_scale *= signed_inverse_length
    return (
        scalar,
        bind[0] * vector_scale,
        bind[1] * vector_scale,
        bind[2] * vector_scale,
    )


def quaternion_error(left: Sequence[float], right: Sequence[float]) -> float:
    direct = max(abs(left[index] - right[index]) for index in range(4))
    negated = max(abs(left[index] + right[index]) for index in range(4))
    return min(direct, negated)


def vector_error(left: Sequence[float], right: Sequence[float]) -> float:
    return max(abs(left[index] - right[index]) for index in range(len(left)))


def active_twist_axes(
    hierarchy_rows: Sequence[dict[str, object]],
    executable: dict[str, object],
) -> list[dict[str, object]]:
    by_sample_name = {
        (str(row["sample"]), str(row["transform_name"])): row
        for row in hierarchy_rows
    }
    tables = executable["twist_name_tables"]
    result = []
    for family, (sample, active_names) in TWIST_AXIS_SOURCES.items():
        all_names = [item["name"] for item in tables[family]["items"]]
        active_indices = [all_names.index(name) for name in active_names]
        expected_active = [1, 2] if family == "player" else [0, 2]
        if active_indices != expected_active:
            raise RestOrientationError(
                f"{family}: active record indices {active_indices}, expected {expected_active}"
            )
        for name, record_index in zip(active_names, active_indices):
            row = by_sample_name.get((sample, name))
            if row is None:
                raise RestOrientationError(f"missing {sample}/{name} axis")
            axis = [float(row[f"local_{component}"]) for component in "xyz"]
            normalize3(axis)
            result.append(
                {
                    "family": family,
                    "record_index": record_index,
                    "transform_name": name,
                    "sample": sample,
                    "axis": axis,
                    "callback": (
                        "conjugate(full_twist) * child"
                        if family == "player"
                        else "child * conjugate(half_twist); parent=half_twist"
                    ),
                }
            )
    # Exercise the exact x==0 && y==0 branch even though the six selected
    # corpus axes need not do so.
    result.append(
        {
            "family": "synthetic",
            "record_index": -1,
            "transform_name": "exact_z_branch",
            "sample": "code_branch_witness",
            "axis": [0.0, 0.0, 3.0],
            "callback": "equation-only",
        }
    )
    return result


def quaternion_evidence(
    hierarchy_rows: Sequence[dict[str, object]],
    executable: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    axes = active_twist_axes(hierarchy_rows, executable)
    angles = (-150.0, -95.0, -25.0, 0.0, 15.0, 60.0, 135.0)
    rows: list[dict[str, object]] = []
    full_error_max = 0.0
    half_squared_error_max = 0.0
    player_removal_error_max = 0.0
    half_split_error_max = 0.0
    matrix_rotation_error_max = 0.0

    for axis_record in axes:
        axis = list(axis_record["axis"])
        for angle_degrees in angles:
            angle = math.radians(angle_degrees)
            source = quaternion_from_axis_angle(axis, angle)
            full = extract_signed_twist(axis, source, False)
            half = extract_signed_twist(axis, source, True)
            expected_half = quaternion_from_axis_angle(axis, angle * 0.5)
            full_error = quaternion_error(full, source)
            half_squared_error = quaternion_error(
                quaternion_multiply(half, half), full
            )
            player_removed = quaternion_multiply(
                quaternion_conjugate(full), source
            )
            player_error = quaternion_error(player_removed, (1.0, 0.0, 0.0, 0.0))
            child_after_half = quaternion_multiply(
                source, quaternion_conjugate(half)
            )
            split_recomposed = quaternion_multiply(half, child_after_half)
            half_split_error = quaternion_error(split_recomposed, source)

            probe_vector = normalize3((0.37, -0.59, 0.71))
            via_quaternion = quaternion_rotate_vector(source, probe_vector)
            via_matrix = row_rotate(probe_vector, quaternion_to_row_matrix(source))
            matrix_error = vector_error(via_quaternion, via_matrix)

            full_error_max = max(full_error_max, full_error)
            half_squared_error_max = max(
                half_squared_error_max, half_squared_error
            )
            player_removal_error_max = max(
                player_removal_error_max, player_error
            )
            half_split_error_max = max(half_split_error_max, half_split_error)
            matrix_rotation_error_max = max(
                matrix_rotation_error_max, matrix_error
            )
            rows.append(
                {
                    "family": axis_record["family"],
                    "record_index": axis_record["record_index"],
                    "transform_name": axis_record["transform_name"],
                    "sample": axis_record["sample"],
                    "axis_x": axis[0], "axis_y": axis[1], "axis_z": axis[2],
                    "angle_degrees": angle_degrees,
                    "source_w": source[0], "source_x": source[1],
                    "source_y": source[2], "source_z": source[3],
                    "full_w": full[0], "full_x": full[1],
                    "full_y": full[2], "full_z": full[3],
                    "half_w": half[0], "half_x": half[1],
                    "half_y": half[2], "half_z": half[3],
                    "full_expected_error": full_error,
                    "half_expected_error": quaternion_error(half, expected_half),
                    "half_squared_error": half_squared_error,
                    "player_full_removal_error": player_error,
                    "half_split_recompose_error": half_split_error,
                    "matrix_rotation_error": matrix_error,
                }
            )

    # Mixed rotations are not expected to equal their input twist.  They do
    # prove that both helpers stay normalized and that 0x1c2870 squares to
    # 0x1c2530 over nontrivial swing+twist inputs.
    mixed_count = 0
    mixed_unit_error_max = 0.0
    mixed_half_squared_error_max = 0.0
    for axis_index, axis_record in enumerate(axes):
        axis = list(axis_record["axis"])
        perpendicular = (
            (1.0, 0.0, 0.0)
            if axis[0] == 0.0 and axis[1] == 0.0
            else normalize3((-axis[1], axis[0], 0.0))
        )
        for case in range(1, 7):
            twist = quaternion_from_axis_angle(axis, math.radians(-80 + case * 23))
            swing = quaternion_from_axis_angle(
                perpendicular, math.radians(7 + axis_index * 2 + case * 5)
            )
            source = quaternion_normalize(quaternion_multiply(swing, twist))
            full = extract_signed_twist(axis, source, False)
            half = extract_signed_twist(axis, source, True)
            mixed_unit_error_max = max(
                mixed_unit_error_max,
                abs(sum(component * component for component in full) - 1.0),
                abs(sum(component * component for component in half) - 1.0),
            )
            mixed_half_squared_error_max = max(
                mixed_half_squared_error_max,
                quaternion_error(quaternion_multiply(half, half), full),
            )
            mixed_count += 1

    for label, error in (
        ("pure full twist", full_error_max),
        ("pure half square", half_squared_error_max),
        ("player full removal", player_removal_error_max),
        ("half split", half_split_error_max),
        ("quaternion/matrix rotation", matrix_rotation_error_max),
        ("mixed unit length", mixed_unit_error_max),
        ("mixed half square", mixed_half_squared_error_max),
    ):
        # The recovered helpers normalize through an approximate reciprocal
        # square root.  This binary64 equation model is semantic rather than
        # an x87/SSE bit emulator, so allow sub-float32 numerical noise.
        if error > 1.0e-7:
            raise RestOrientationError(f"{label} model error {error}")

    return (
        {
            "component_order": "scalar-first [w,x,y,z]",
            "multiply": "Hamilton product left * right",
            "vector_rotation": "q * [0,v] * conjugate(q)",
            "matrix_layout": "row-major affine; row vectors multiply on the left",
            "active_axis_count": len(axes) - 1,
            "exact_z_branch_witness_count": 1,
            "pure_twist_vector_count": len(rows),
            "pure_full_twist_error_max": full_error_max,
            "pure_half_squared_error_max": half_squared_error_max,
            "player_full_removal_error_max": player_removal_error_max,
            "coach_ref_half_split_recompose_error_max": half_split_error_max,
            "quaternion_matrix_rotation_error_max": matrix_rotation_error_max,
            "mixed_rotation_count": mixed_count,
            "mixed_unit_length_error_max": mixed_unit_error_max,
            "mixed_half_squared_error_max": mixed_half_squared_error_max,
            "active_axes": axes[:-1],
        },
        rows,
    )


def root_space_witness() -> dict[str, object]:
    local = translated_matrix(3.0, -5.0, 7.0)
    root_translation = translated_matrix(11.0, 13.0, -17.0)
    root_rotation = quaternion_to_row_matrix(
        quaternion_from_axis_angle((2.0, -3.0, 5.0), math.radians(37.0))
    )
    root_rotation[12:15] = [11.0, 13.0, -17.0]
    identity_output = matrix_multiply_f32(local, identity_matrix())
    translated_output = matrix_multiply_f32(local, root_translation)
    rotated_output = matrix_multiply_f32(local, root_rotation)
    if identity_output == translated_output or identity_output == rotated_output:
        raise RestOrientationError("external root did not affect hierarchy output")
    return {
        "equation": "expanded_current[i] = local[i] * (parent_current or external_root)",
        "local_translation": local[12:15],
        "identity_root_output_translation": identity_output[12:15],
        "translated_root_output_translation": translated_output[12:15],
        "rotated_translated_root_output_translation": rotated_output[12:15],
        "conclusion": (
            "0x00022c00 receives matrices in the coordinate space selected by "
            "the hierarchy caller's external root; they are not intrinsically "
            "always model-space or always world-space"
        ),
    }


def write_tsv(
    path: Path, rows: Iterable[dict[str, object]], fields: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def write_hierarchy_tsv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    write_tsv(
        path, rows,
        (
            "sample", "outer_index", "chunk_index", "scene_name", "shape_name",
            "transform_index", "transform_name", "parent_index",
            "local_x", "local_y", "local_z",
            "expanded_x", "expanded_y", "expanded_z",
            "absolute_x", "absolute_y", "absolute_z",
            "hierarchy_error", "inverse_bind_identity_error",
        ),
    )


def write_vectors_tsv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    write_tsv(
        path, rows,
        (
            "family", "record_index", "transform_name", "sample",
            "axis_x", "axis_y", "axis_z", "angle_degrees",
            "source_w", "source_x", "source_y", "source_z",
            "full_w", "full_x", "full_y", "full_z",
            "half_w", "half_x", "half_y", "half_z",
            "full_expected_error", "half_expected_error",
            "half_squared_error", "player_full_removal_error",
            "half_split_recompose_error", "matrix_rotation_error",
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to vc_53450030/0")
    parser.add_argument(
        "--resource-scan", type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    parser.add_argument(
        "--xbe", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    parser.add_argument(
        "--xbe-header", type=Path,
        default=Path("reports/headers/nfl2k5_xbe_header.json"),
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--hierarchy-tsv", type=Path, required=True)
    parser.add_argument("--vectors-tsv", type=Path, required=True)
    parser.add_argument("--progress-every", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    executable = executable_evidence(args.xbe, args.xbe_header)
    corpus, hierarchy_rows = scan_hierarchy_corpus(
        args.index, args.resource_scan, args.progress_every
    )
    quaternions, vector_rows = quaternion_evidence(hierarchy_rows, executable)
    report = {
        "schema": SCHEMA,
        "executable": executable,
        "corpus": corpus,
        "quaternions": quaternions,
        "root_space_witness": root_space_witness(),
        "proved_contract": {
            "serialized_absolute_bind_translation": "transform +0x40.xyz",
            "serialized_local_bind_translation": "transform +0x50.xyz",
            "serialized_local_w_runtime_use": (
                "ignored by 0x000233c0; twist setup copies the vector then "
                "forcibly replaces w with 0"
            ),
            "local_pose_matrix": (
                "0x003ca3d0 row-vector rotation matrix from scalar-first "
                "quaternion; 0x000233c0 adds +0x50.xyz to m12,m13,m14"
            ),
            "hierarchy_equation": (
                "current[i] = local[i] * (current[parent] if parent>=0 else external_root)"
            ),
            "rest_local_rotation": (
                "identity quaternion [1,0,0,0]; rest local node transform is "
                "identity rotation plus +0x50.xyz translation"
            ),
            "identity_root_rest_current": (
                "translation(+0x40.xyz), validated over every serialized transform"
            ),
            "row_vector_inverse_bind": "T(-transform[+0x40].xyz)",
            "row_vector_skin_equation": (
                "skin = T(-absolute_bind_translation) * current"
            ),
            "identity_root_bind_palette": (
                "identity within recorded float32 hierarchy tolerance"
            ),
            "current_matrix_space": (
                "external-root-parent space selected by each 0x000233c0 caller; "
                "not universally model-space or universally world-space"
            ),
            "full_twist_helper": (
                "0x001c2530 extracts the signed full twist about +0x50.xyz "
                "from the source quaternion's action on a perpendicular vector"
            ),
            "half_twist_helper": (
                "0x001c2870 returns the principal quaternion square root "
                "(half angle) of that same signed twist"
            ),
            "player_callback": (
                "records 1 and 2: parent=full_twist(child); "
                "child=conjugate(full_twist)*child"
            ),
            "coach_referee_callback": (
                "records 0 and 2: parent=half_twist(child); "
                "child=child*conjugate(half_twist); records 1 and 3 are set identity"
            ),
            "gltf_status": (
                "translation-only raw-coordinate bind/rest orientation is proved; "
                "no glTF emitted because axes/handedness/units, complete caller "
                "root ownership, mesh-node ownership, and animation export remain open"
            ),
        },
        "portme": PORTMES,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_hierarchy_tsv(args.hierarchy_tsv, hierarchy_rows)
    write_vectors_tsv(args.vectors_tsv, vector_rows)
    print(
        "NFL_REST_ORIENTATION_COMPLETE "
        f"scenes={corpus['counts']['scene_count']} "
        f"shapes={corpus['counts']['shape_count']} "
        f"transforms={corpus['counts']['transform_count']} "
        f"twist_vectors={len(vector_rows)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RestOrientationError, struct.error, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
