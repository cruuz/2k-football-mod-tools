#!/usr/bin/env python3
"""Validate the native NFL 2K5 coach/referee 25-slot local-pose path.

The native module is compared with an independent Python equation model over
real packed frames from a safely referee-named 21-channel SMCD. The validator
also reads the installed signed map directly from default.xbe and the twist
axes directly from four decoded referee/coach SCNE shapes.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable, Sequence

import nfl_outer
from nfl_quaternion_interpolation import (
    ANGLE_CONSTANT_VAS,
    THRESHOLD_VA,
    XbeImage,
    f32,
    interpolate_reference,
    table_rows,
)
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_inventory import read_name, resolve_relative


EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
SHARED_MAP_VA = 0x0051D010
SHARED_MAP_BYTES = 64
PACKED_SCALE_VA = 0x004EEA18
PACKED_CHANNELS = 21
LOGICAL_CHANNELS = 25
WRAPPER_SIZE = 0x20
WITNESS_OUTER = 3107
WITNESS_CHUNK = 0
WITNESS_NAME = "ANM_REF_PENALTY_INTENTIONAL_GROUNDING_R"
WITNESS_RESOURCE_SHA256 = (
    "a45fbf26f355517ee6774abc39e8b1872dd05c7c9b107c005aff940f04925323"
)
WITNESS_PACKED_SHA256 = (
    "28c057c83ca55b28e19954b309183ad82f442a3eaa7dcd737cfe57f06b17e8f4"
)
EXPECTED_AXIS_BITS = (
    (0x414CB368, 0xC03EDD23, 0x40D47D20),
    (0xC14CC750, 0xC03EE782, 0x40D43C2A),
)
AXIS_SCNE_SHAPES = {
    (346, 109): ("referee", ("ref_high", "ref_low")),
    (348, 0): ("coach", ("coachBodyGrp1", "coachLodGrp1")),
}
FUNCTION_HASHES = {
    (0x00095B40, 105):
        "2a4f32a92673b5ab4a89295daeed0180b8b610acfee8568551af267205740483",
    (0x00095FB0, 87):
        "f5c64113fb11905e4ec2e40ba068d53e6e78608f726b49ca704ea7f4f5ada86d",
    (0x00096590, 105):
        "706352162195a2010e200a6daad38054983bfc04b248253b8368342b663fc645",
    (0x00096A80, 76):
        "22c79b223bd234a8f51a1f50dfcf23ec79f2ae2c601fd4fd6476e97003f93c70",
    (0x000DF700, 421):
        "5dce74744c2ede4ab231d61753c73909c634c8c85f9474699b5f6588bedc48d9",
    (0x001C2870, 850):
        "419eb67b0e3e2ba3ebadb8e5075fa26d1616a82f47d1b8a5ea81262218e54403",
    (0x003CA150, 140):
        "76343d475ba9c89963bf42f9a1951e8b20183759dd8e05e72ab4b288ec06f945",
}


class ValidationError(ValueError):
    """A pinned executable, corpus, ABI, or equation invariant failed."""


class NativeInterpolationInfo(ctypes.Structure):
    _fields_ = [
        ("branch", ctypes.c_int),
        ("shortest_path_negated", ctypes.c_bool),
        ("theta_units", ctypes.c_int32),
        ("step_units", ctypes.c_int32),
        ("left_weight", ctypes.c_float),
        ("right_weight", ctypes.c_float),
    ]


class NativeClip(ctypes.Structure):
    _fields_ = [
        ("packed_frames", ctypes.POINTER(ctypes.c_uint8)),
        ("packed_frame_bytes", ctypes.c_size_t),
        ("frame_count", ctypes.c_uint16),
        ("packed_poses_per_frame", ctypes.c_uint8),
        ("sample_rate", ctypes.c_uint8),
        ("time_scale", ctypes.c_float),
        ("flags", ctypes.c_uint8),
        ("duration_seconds", ctypes.c_float),
    ]


Float4 = ctypes.c_float * 4
NativePoseRows = Float4 * LOGICAL_CHANNELS


class NativePose(ctypes.Structure):
    _fields_ = [("scalar_first", NativePoseRows)]


class NativeGltfPose(ctypes.Structure):
    _fields_ = [("xyzw", NativePoseRows)]


class NativePoseInfo(ctypes.Structure):
    _fields_ = [
        ("sample_status", ctypes.c_int),
        ("failed_logical_channel", ctypes.c_uint8),
        ("mirrored", ctypes.c_bool),
        ("normalized_seconds", ctypes.c_float),
        ("completed_loops", ctypes.c_uint32),
    ]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def raw_f32(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def f32_from_raw(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value))[0]


def c_mul(left: float, right: float) -> float:
    return f32(f32(left) * f32(right))


def c_add(left: float, right: float) -> float:
    return f32(f32(left) + f32(right))


def flip_sign(value: float) -> float:
    return f32_from_raw(raw_f32(value) ^ 0x8000_0000)


def pointer_name(data: bytes, field: int, limit: int, label: str) -> str:
    target = resolve_relative(data, field, limit, label)
    if target is None:
        raise ValidationError(f"{label}: null name pointer")
    value = read_name(data, target, limit, label)
    if value is None:
        raise ValidationError(f"{label}: null name")
    return value


def validate_xbe(image: XbeImage) -> bytes:
    if image.md5 != EXPECTED_XBE_MD5:
        raise ValidationError(f"unexpected XBE MD5 {image.md5}")
    for (va, size), expected in FUNCTION_HASHES.items():
        actual = sha256(image.at(va, size))
        if actual != expected:
            raise ValidationError(f"XBE function hash differs at {va:#x}")
    map_bytes = image.at(SHARED_MAP_VA, SHARED_MAP_BYTES)
    expected_first_50 = bytes.fromhex(
        "00000105020603070408050106020703080409090a0a0b0b0c0c"
        "0d110e12ffff0f13ffff1014110d120effff130fffff1410"
    )
    if map_bytes[:50] != expected_first_50 or map_bytes[50:] != bytes(14):
        raise ValidationError("XBE shared coach/referee signed map differs")
    return map_bytes


def extract_axis_copies(
    index_path: Path, scan_path: Path,
) -> list[dict[str, object]]:
    archive = nfl_outer.parse_archive(index_path)
    _, resources = parse_inventory(scan_path)
    result: list[dict[str, object]] = []
    for (outer_index, chunk_index), (scene_expected, shape_names) in (
        AXIS_SCNE_SHAPES.items()
    ):
        resource = next(
            (
                item for item in resources
                if item.outer_index == outer_index
                and item.chunk_index == chunk_index
                and item.kind == "SCNE"
            ),
            None,
        )
        if resource is None:
            raise ValidationError(
                f"missing SCNE {outer_index}/{chunk_index} axis source"
            )
        entry = archive.entries[outer_index]
        span = nfl_outer.read_entry_range(
            archive, entry, resource.chunk_offset,
            WRAPPER_SIZE + resource.stored_size,
        )
        decoded, _ = decode_resource(span, resource)
        limit = resource.word_08
        scene_name = pointer_name(decoded, 0x10, limit, "axis scene name")
        if scene_name != scene_expected:
            raise ValidationError(
                f"axis scene {outer_index}/{chunk_index} is {scene_name!r}"
            )
        descriptor = resolve_relative(
            decoded, 0x14, limit, f"{scene_name} descriptor"
        )
        if descriptor is None:
            raise ValidationError(f"{scene_name}: null descriptor")
        shape_count = struct.unpack_from("<I", decoded, descriptor + 0x2C)[0]
        shape_start = resolve_relative(
            decoded, descriptor + 0x30, limit, f"{scene_name} shapes"
        )
        if shape_start is None:
            raise ValidationError(f"{scene_name}: null shape table")
        found: set[str] = set()
        for shape_index in range(shape_count):
            shape = shape_start + shape_index * 0x100
            shape_name = pointer_name(
                decoded, shape + 0x40, limit, f"{scene_name} shape name"
            )
            if shape_name not in shape_names:
                continue
            found.add(shape_name)
            transform_count = struct.unpack_from("<H", decoded, shape + 0x50)[0]
            transform_start = resolve_relative(
                decoded, shape + 0x64, limit, f"{shape_name} transforms"
            )
            if transform_count != LOGICAL_CHANNELS or transform_start is None:
                raise ValidationError(
                    f"{shape_name}: expected 25 serialized transforms"
                )
            by_name: dict[str, tuple[int, int, tuple[int, ...]]] = {}
            for transform_index in range(transform_count):
                record = transform_start + transform_index * 0x70
                transform_name = pointer_name(
                    decoded, record + 0x60, limit,
                    f"{shape_name} transform {transform_index}",
                )
                if transform_name in ("ltwist", "rtwist"):
                    parent = struct.unpack_from("<i", decoded, record + 0x64)[0]
                    bits = struct.unpack_from("<4I", decoded, record + 0x50)
                    by_name[transform_name] = (transform_index, parent, bits)
            expected = {
                "ltwist": (15, 14, EXPECTED_AXIS_BITS[0]),
                "rtwist": (21, 20, EXPECTED_AXIS_BITS[1]),
            }
            for side, (name, wanted) in enumerate(expected.items()):
                if name not in by_name:
                    raise ValidationError(f"{shape_name}: missing {name}")
                index, parent, bits = by_name[name]
                if (index, parent, bits[:3]) != wanted or bits[3] != 0x3F800000:
                    raise ValidationError(f"{shape_name}/{name}: axis differs")
                result.append(
                    {
                        "outer_index": outer_index,
                        "chunk_index": chunk_index,
                        "scene_name": scene_name,
                        "shape_name": shape_name,
                        "transform_name": name,
                        "side": side,
                        "axis_bits": bits[:3],
                    }
                )
        if found != set(shape_names):
            raise ValidationError(
                f"{scene_name}: found axis shapes {sorted(found)}, "
                f"expected {sorted(shape_names)}"
            )
    if len(result) != 8:
        raise ValidationError(f"found {len(result)}/8 SCNE axis copies")
    return result


def extract_witness(
    index_path: Path, inventory_path: Path,
) -> tuple[bytes, dict[str, object]]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("schema") != "nfl2k5_motion_inventory/v1":
        raise ValidationError("unsupported motion inventory schema")
    resource = next(
        (
            item for item in inventory["resources"]
            if int(item["outer_index"]) == WITNESS_OUTER
            and int(item["chunk_index"]) == WITNESS_CHUNK
        ),
        None,
    )
    if resource is None:
        raise ValidationError("missing referee SMCD witness")
    if not (
        resource["kind"] == "SMCD"
        and resource["name"] == WITNESS_NAME
        and int(resource["root_count"]) == 1
        and resource["decoded_sha256"] == WITNESS_RESOURCE_SHA256
    ):
        raise ValidationError("referee SMCD witness identity differs")

    root = resource["roots"][0]
    words = tuple(int(value, 16) for value in root["header_words"])
    channel_count = words[0] & 0xFF
    frame_count = words[0] >> 16
    flags = words[1] & 0xFF
    sample_rate = words[3] & 0xFF
    time_scale = f32_from_raw(words[4])
    duration = f32_from_raw(words[5])
    if not (
        channel_count == PACKED_CHANNELS
        and frame_count == 73
        and flags == 2
        and sample_rate == 15
        and time_scale == 1.0
        and raw_f32(duration) == 0x40980001
    ):
        raise ValidationError("referee SMCD root fields differ")

    packed_region = next(
        (
            item for item in resource["packed_regions"]
            if int(item["owner_root_index"]) == 0
            and int(item["owner_pointer_field_relative"]) == 0x24
        ),
        None,
    )
    if packed_region is None:
        raise ValidationError("referee SMCD has no quaternion region")
    archive = nfl_outer.parse_archive(index_path)
    entry = archive.entries[WITNESS_OUTER]
    body = nfl_outer.read_entry_range(
        archive, entry, int(resource["chunk_offset"]) + WRAPPER_SIZE,
        int(resource["stored_size"]),
    )
    if sha256(body) != WITNESS_RESOURCE_SHA256:
        raise ValidationError("referee SMCD archive bytes differ")
    start = int(packed_region["offset"])
    end = int(packed_region["end"])
    packed = body[start:end]
    if not (
        len(packed) == frame_count * channel_count * 4
        and sha256(packed) == WITNESS_PACKED_SHA256
        and packed_region["sha256"] == WITNESS_PACKED_SHA256
    ):
        raise ValidationError("referee SMCD quaternion bytes differ")
    return packed, {
        "frame_count": frame_count,
        "channel_count": channel_count,
        "flags": flags,
        "sample_rate": sample_rate,
        "time_scale": time_scale,
        "duration": duration,
    }


def decode_packed(encoded: bytes, scale: float) -> tuple[float, ...]:
    if len(encoded) != 4:
        raise ValidationError("packed quaternion is not four bytes")
    (word,) = struct.unpack("<I", encoded)
    packed = (
        ((word >> 20) & 0x3FF) - 0x200,
        ((word >> 10) & 0x3FF) - 0x200,
        (word & 0x3FF) - 0x200,
    )
    stored = tuple(c_mul(float(value), scale) for value in packed)
    square01 = c_add(c_mul(stored[0], stored[0]), c_mul(stored[1], stored[1]))
    square_sum = c_add(square01, c_mul(stored[2], stored[2]))
    radicand = c_add(1.0, -square_sum)
    if not math.isfinite(radicand) or radicand < 0.0:
        raise ValidationError("negative packed-quaternion radicand")
    missing = f32(math.sqrt(radicand))
    lanes = list(stored)
    lanes.insert(word >> 30, missing)
    return tuple(lanes)


def hamilton(left: Sequence[float], right: Sequence[float]) -> tuple[float, ...]:
    lw, lx, ly, lz = (float(value) for value in left)
    rw, rx, ry, rz = (float(value) for value in right)
    return (
        lw * rw - (lx * rx + ly * ry + lz * rz),
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    )


def conjugate(value: Sequence[float]) -> tuple[float, ...]:
    return (value[0], -value[1], -value[2], -value[3])


def dot3(left: Sequence[float], right: Sequence[float]) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def cross3(left: Sequence[float], right: Sequence[float]) -> tuple[float, ...]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def rotate_vector(quaternion: Sequence[float], vector: Sequence[float]) -> tuple[float, ...]:
    rotated = hamilton(
        hamilton(quaternion, (0.0, vector[0], vector[1], vector[2])),
        conjugate(quaternion),
    )
    return rotated[1:]


def half_twist(axis: Sequence[float], source: Sequence[float]) -> tuple[float, ...]:
    bind = tuple(float(value) for value in axis)
    norm_squared = dot3(bind, bind)
    perpendicular = (
        (1.0, 0.0, 0.0)
        if bind[0] == 0.0 and bind[1] == 0.0
        else (-bind[1], bind[0], 0.0)
    )
    rotated = rotate_vector(source, perpendicular)
    projection_scale = dot3(rotated, bind) / norm_squared
    projected = tuple(
        rotated[index] - bind[index] * projection_scale for index in range(3)
    )
    projected_squared = dot3(projected, projected)
    perpendicular_squared = dot3(perpendicular, perpendicular)
    cosine = dot3(perpendicular, projected) / math.sqrt(
        projected_squared * perpendicular_squared
    )
    cosine = min(1.0, max(-1.0, cosine))
    signed_inverse_axis_length = 1.0 / math.sqrt(norm_squared)
    if dot3(cross3(perpendicular, projected), bind) < 0.0:
        signed_inverse_axis_length = -signed_inverse_axis_length
    full_half_cosine = math.sqrt((1.0 + cosine) * 0.5)
    scalar = math.sqrt((1.0 + full_half_cosine) * 0.5)
    vector_scale = (
        math.sqrt((1.0 - full_half_cosine) * 0.5)
        * signed_inverse_axis_length
    )
    return tuple(
        f32(value) for value in (
            scalar,
            bind[0] * vector_scale,
            bind[1] * vector_scale,
            bind[2] * vector_scale,
        )
    )


class ReferenceModel:
    def __init__(self, image: XbeImage, packed: bytes, fields: dict[str, object]):
        self.packed = packed
        self.frame_count = int(fields["frame_count"])
        self.channel_count = int(fields["channel_count"])
        self.sample_rate = int(fields["sample_rate"])
        self.time_scale = float(fields["time_scale"])
        self.duration = float(fields["duration"])
        self.flags = int(fields["flags"])
        self.map = image.at(SHARED_MAP_VA, SHARED_MAP_BYTES)
        self.scale = image.float(PACKED_SCALE_VA)
        self.table = table_rows(image)
        self.constants = {va: image.float(va) for _, va in ANGLE_CONSTANT_VAS}
        self.threshold = self.constants[THRESHOLD_VA]
        self.axes = tuple(
            tuple(f32_from_raw(value) for value in side)
            for side in EXPECTED_AXIS_BITS
        )
        self.linear = 0
        self.fixed_slerp = 0
        self.shortest_path = 0

    def sample_channel(
        self, seconds_source: float, logical: int, mirrored: bool,
    ) -> tuple[float, ...]:
        seconds = f32(seconds_source)
        coordinate = c_mul(c_mul(float(self.sample_rate), seconds), self.time_scale)
        final_frame = self.frame_count - 1
        if coordinate < float(final_frame):
            left_frame = math.floor(coordinate)
            right_frame = left_frame + 1
            interpolation_t = f32(coordinate - float(left_frame))
        else:
            left_frame = final_frame
            right_frame = final_frame
            interpolation_t = 0.0
        map_raw = self.map[logical * 2 + int(mirrored)]
        packed_index = map_raw if map_raw < 128 else map_raw - 256
        if packed_index < 0:
            raise ValidationError("reference attempted a disabled channel")
        left_offset = (left_frame * self.channel_count + packed_index) * 4
        right_offset = (right_frame * self.channel_count + packed_index) * 4
        left = decode_packed(self.packed[left_offset:left_offset + 4], self.scale)
        if left_frame == right_frame:
            output = left
        else:
            right = decode_packed(
                self.packed[right_offset:right_offset + 4], self.scale
            )
            interpolation = interpolate_reference(
                left, right, interpolation_t, self.threshold,
                self.constants, self.table,
            )
            output = interpolation["output"]
            self.linear += interpolation["branch"] == "linear"
            self.fixed_slerp += interpolation["branch"] == "fixed_slerp"
            self.shortest_path += bool(interpolation["shortest_path_negated"])
        if mirrored:
            output = (output[0], output[1], flip_sign(output[2]), flip_sign(output[3]))
        return tuple(f32(value) for value in output)

    def pose(self, seconds: float, mirrored: bool) -> list[tuple[float, ...]]:
        output: list[tuple[float, ...]] = [(0.0, 0.0, 0.0, 0.0)] * LOGICAL_CHANNELS
        for logical in range(LOGICAL_CHANNELS):
            raw = self.map[logical * 2 + int(mirrored)]
            if raw == 0xFF:
                continue
            output[logical] = self.sample_channel(seconds, logical, mirrored)
        for side, (humerus, twist, wrist) in enumerate(
            ((14, 15, 17), (20, 21, 23))
        ):
            half = half_twist(self.axes[side], output[humerus])
            adjusted = tuple(
                f32(value) for value in hamilton(output[humerus], conjugate(half))
            )
            output[humerus] = adjusted
            output[twist] = half
            output[wrist] = (1.0, 0.0, 0.0, 0.0)
        return output


class NativeComparator:
    def __init__(
        self, library_path: Path, label: str, map_bytes: bytes,
        packed: bytes, fields: dict[str, object], reference: ReferenceModel,
    ) -> None:
        self.label = label
        self.library = ctypes.CDLL(str(library_path.resolve()))
        self.sample = self.library.vc_nfl_coach_ref_pose_sample_clamped
        self.sample.argtypes = [
            ctypes.POINTER(NativeClip), ctypes.c_float, ctypes.c_bool,
            ctypes.POINTER(NativePose), ctypes.POINTER(NativePoseInfo),
        ]
        self.sample.restype = ctypes.c_int
        self.sample_title = (
            self.library.vc_nfl_coach_ref_pose_sample_title_policy
        )
        self.sample_title.argtypes = [
            ctypes.POINTER(NativeClip), ctypes.c_float,
            ctypes.POINTER(NativePose), ctypes.POINTER(NativePoseInfo),
        ]
        self.sample_title.restype = ctypes.c_int
        self.to_gltf = self.library.vc_nfl_coach_ref_pose_to_gltf_xyzw
        self.to_gltf.argtypes = [
            ctypes.POINTER(NativePose), ctypes.POINTER(NativeGltfPose),
        ]
        self.to_gltf.restype = None
        self.bit_exact = (
            self.library.vc_nfl_coach_ref_pose_twist_is_xbox_bit_exact
        )
        self.bit_exact.argtypes = []
        self.bit_exact.restype = ctypes.c_bool

        native_map = (ctypes.c_int8 * SHARED_MAP_BYTES).in_dll(
            self.library, "vc_nfl_coach_ref_pose_shared_channel_map"
        )
        native_map_bytes = bytes(int(value) & 0xFF for value in native_map)
        if native_map_bytes != map_bytes:
            raise ValidationError(f"{label}: native map differs from XBE")
        native_axes = (ctypes.c_float * 6).in_dll(
            self.library, "vc_nfl_coach_ref_pose_twist_bind_axes"
        )
        native_axis_bits = tuple(raw_f32(value) for value in native_axes)
        if native_axis_bits != EXPECTED_AXIS_BITS[0] + EXPECTED_AXIS_BITS[1]:
            raise ValidationError(f"{label}: native bind axes differ from SCNE")
        if self.bit_exact():
            raise ValidationError(f"{label}: portable path claims Xbox bit identity")

        self.source = (ctypes.c_uint8 * len(packed)).from_buffer_copy(packed)
        self.clip = NativeClip(
            ctypes.cast(self.source, ctypes.POINTER(ctypes.c_uint8)),
            len(packed), int(fields["frame_count"]), int(fields["channel_count"]),
            int(fields["sample_rate"]), float(fields["time_scale"]),
            int(fields["flags"]), float(fields["duration"]),
        )
        self.reference = reference
        self.poses = 0
        self.channels = 0
        self.max_lane_error = 0.0
        self.gltf_reorders = 0

    def compare_pose(
        self, seconds_source: float, mirrored: bool, *, title: bool = False,
        expected_normalized: float | None = None,
        expected_loops: int = 0,
    ) -> None:
        seconds = f32(seconds_source)
        output = NativePose()
        info = NativePoseInfo()
        if title:
            status = self.sample_title(
                ctypes.byref(self.clip), seconds, ctypes.byref(output),
                ctypes.byref(info),
            )
            normalized = (
                float(info.normalized_seconds)
                if expected_normalized is None else f32(expected_normalized)
            )
        else:
            status = self.sample(
                ctypes.byref(self.clip), seconds, mirrored,
                ctypes.byref(output), ctypes.byref(info),
            )
            normalized = seconds
        if status != 0:
            raise ValidationError(f"{self.label}: native pose status {status}")
        if not (
            info.sample_status == 0
            and info.failed_logical_channel == 0xFF
            and bool(info.mirrored) == mirrored
            and raw_f32(info.normalized_seconds) == raw_f32(normalized)
            and info.completed_loops == expected_loops
        ):
            raise ValidationError(f"{self.label}: native pose metadata differs")

        wanted = self.reference.pose(normalized, mirrored)
        for channel in range(LOGICAL_CHANNELS):
            for lane in range(4):
                difference = abs(
                    float(output.scalar_first[channel][lane])
                    - float(wanted[channel][lane])
                )
                self.max_lane_error = max(self.max_lane_error, difference)
                if difference > 3.0e-6:
                    raise ValidationError(
                        f"{self.label}: channel {channel} lane {lane} "
                        f"error {difference}"
                    )
            self.channels += 1
        for wrist in (17, 23):
            bits = tuple(raw_f32(value) for value in output.scalar_first[wrist])
            if bits != (0x3F800000, 0, 0, 0):
                raise ValidationError(f"{self.label}: wrist {wrist} is not identity")

        gltf = NativeGltfPose()
        self.to_gltf(ctypes.byref(output), ctypes.byref(gltf))
        for channel in range(LOGICAL_CHANNELS):
            source_bits = tuple(
                raw_f32(value) for value in output.scalar_first[channel]
            )
            output_bits = tuple(raw_f32(value) for value in gltf.xyzw[channel])
            if output_bits != (
                source_bits[1], source_bits[2], source_bits[3], source_bits[0]
            ):
                raise ValidationError(
                    f"{self.label}: glTF reorder differs at channel {channel}"
                )
            self.gltf_reorders += 1
        self.poses += 1

    def run(self) -> None:
        # Real witness samples cover both map variants and final-frame clamp.
        coordinates = (
            0.0, 0.25, 1.5, 10.125, 19.5, 37.75, 60.375, 72.0, 77.0,
        )
        denominator = c_mul(float(self.clip.sample_rate), self.clip.time_scale)
        for coordinate in coordinates:
            seconds = f32(f32(coordinate) / denominator)
            self.compare_pose(seconds, False)
            self.compare_pose(seconds, True)

        # The shipped witness is non-looping and non-mirrored (flags 0x02).
        title_seconds = c_add(self.clip.duration_seconds, 1.0)
        self.compare_pose(
            title_seconds, False, title=True,
            expected_normalized=title_seconds,
        )

        # Exercise the already-proved title loop/mirror policy with the same
        # real packed frames. This flag combination is a deterministic policy
        # vector, not a claim about the witness's shipped flags.
        shipped_flags = self.clip.flags
        self.clip.flags = 5
        synthetic_seconds = c_add(self.clip.duration_seconds, 0.5)
        expected_normalized = c_add(
            synthetic_seconds, -self.clip.duration_seconds
        )
        self.compare_pose(
            synthetic_seconds, True, title=True,
            expected_normalized=expected_normalized, expected_loops=1,
        )
        self.clip.flags = shipped_flags


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--index", type=Path, required=True)
    result.add_argument("--resource-scan", type=Path, required=True)
    result.add_argument("--motion-inventory", type=Path, required=True)
    result.add_argument("--xbe", type=Path, required=True)
    result.add_argument("--xbe-header", type=Path, required=True)
    result.add_argument("--library", type=Path, required=True)
    result.add_argument("--label", required=True)
    result.add_argument("--json", type=Path)
    return result


def report_data(
    args: argparse.Namespace,
    image: XbeImage,
    map_bytes: bytes,
    axes: Sequence[dict[str, object]],
    fields: dict[str, object],
    comparator: NativeComparator,
    reference: ReferenceModel,
) -> dict[str, object]:
    source_paths = (
        Path("include/recovered/nfl2k5/coach_ref_pose.h"),
        Path("src/recovered/nfl2k5/coach_ref_pose.c"),
        Path("tests/nfl_coach_ref_pose_test.c"),
        Path("tools/nfl_coach_ref_pose_native_validate.py"),
    )
    input_paths = (
        args.index,
        args.resource_scan,
        args.motion_inventory,
        args.xbe_header,
    )
    return {
        "schema": "nfl2k5_coach_ref_pose_native/v1",
        "executable": {
            "path": str(args.xbe),
            "md5": image.md5,
            "sha256": sha256(image.data),
            "function_hashes": {
                f"0x{va:08x}+0x{size:x}": digest
                for (va, size), digest in FUNCTION_HASHES.items()
            },
            "shared_map": {
                "va": f"0x{SHARED_MAP_VA:08x}",
                "length": len(map_bytes),
                "raw_hex": map_bytes.hex(),
                "sha256": sha256(map_bytes),
                "active_pair_count": LOGICAL_CHANNELS,
                "disabled_logical_channels": [15, 17, 21, 23],
            },
        },
        "corpus_axes": {
            "copy_count": len(axes),
            "left_bits": [f"0x{value:08x}" for value in EXPECTED_AXIS_BITS[0]],
            "right_bits": [f"0x{value:08x}" for value in EXPECTED_AXIS_BITS[1]],
            "copies": [
                {
                    **{
                        key: item[key]
                        for key in (
                            "outer_index", "chunk_index", "scene_name",
                            "shape_name", "transform_name", "side",
                        )
                    },
                    "axis_bits": [
                        f"0x{int(value):08x}" for value in item["axis_bits"]
                    ],
                }
                for item in axes
            ],
        },
        "motion_witness": {
            "outer_index": WITNESS_OUTER,
            "chunk_index": WITNESS_CHUNK,
            "kind": "SMCD",
            "name": WITNESS_NAME,
            "decoded_sha256": WITNESS_RESOURCE_SHA256,
            "packed_region_sha256": WITNESS_PACKED_SHA256,
            "packed_region_bytes": int(fields["frame_count"])
                * int(fields["channel_count"]) * 4,
            "frame_count": int(fields["frame_count"]),
            "packed_channels_per_frame": int(fields["channel_count"]),
            "sample_rate": int(fields["sample_rate"]),
            "time_scale_bits": f"0x{raw_f32(float(fields['time_scale'])):08x}",
            "duration_bits": f"0x{raw_f32(float(fields['duration'])):08x}",
            "flags": f"0x{int(fields['flags']):02x}",
            "ownership_boundary": (
                "canonical resource name safely identifies a referee penalty "
                "motion; live controller/state-machine selection remains PORTME"
            ),
        },
        "native_contract": {
            "logical_channel_count": LOGICAL_CHANNELS,
            "packed_channel_count": PACKED_CHANNELS,
            "input_quaternion_order": "scalar-first [w,x,y,z]",
            "gltf_quaternion_order": "[x,y,z,w] with XYZ retained",
            "callback": (
                "slots 15/21 receive principal half twist from slots 14/20; "
                "14/20 become source*conjugate(half); 17/23 become identity"
            ),
            "destination_update": "transactional",
            "twist_xbox_bit_exact": False,
        },
        "validation": {
            "poses": comparator.poses,
            "channels": comparator.channels,
            "gltf_reorders": comparator.gltf_reorders,
            "linear_interpolations": reference.linear,
            "fixed_slerp_interpolations": reference.fixed_slerp,
            "shortest_path_interpolations": reference.shortest_path,
            "maximum_lane_error": comparator.max_lane_error,
            "expected_compilers": ["gcc-13.3", "clang-18.1"],
        },
        "source_files": {
            str(path): sha256_file(path) for path in source_paths
        },
        "input_files": {
            str(path): sha256_file(path) for path in input_paths
        },
        "portme": [
            "// PORTME: prove the live gameplay controller/state-machine selection for every referee/coach SMCD.",
            "// PORTME: retain caller-specific external-root and loop ownership when attaching local rotations.",
            "// PORTME: define the inactive-coach guard without portable-C uninitialized reads.",
            "// PORTME: emulate 0x001C2870 x87/SSE rounding only if bit-exact Xbox replay is required.",
        ],
    }


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        image = XbeImage(args.xbe, args.xbe_header)
        map_bytes = validate_xbe(image)
        axes = extract_axis_copies(args.index, args.resource_scan)
        packed, fields = extract_witness(args.index, args.motion_inventory)
        reference = ReferenceModel(image, packed, fields)
        comparator = NativeComparator(
            args.library, args.label, map_bytes, packed, fields, reference
        )
        comparator.run()
        if not (
            comparator.poses == 20
            and comparator.channels == 500
            and comparator.gltf_reorders == 500
            and reference.linear > 0
            and reference.fixed_slerp > 0
            and reference.shortest_path > 0
        ):
            raise ValidationError("semantic branch/coverage counts differ")
        if args.json is not None:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(
                json.dumps(
                    report_data(
                        args, image, map_bytes, axes, fields, comparator,
                        reference,
                    ),
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )
    except (
        AssertionError,
        ctypes.ArgumentError,
        KeyError,
        IndexError,
        OSError,
        StopIteration,
        struct.error,
        ValidationError,
        ValueError,
        nfl_outer.FormatError,
    ) as exc:
        print(f"nfl_coach_ref_pose_native_validate: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_COACH_REF_POSE_NATIVE_CORPUS_PASS "
        f"compiler={args.label} witness={WITNESS_NAME} "
        f"axis_copies={len(axes)} poses={comparator.poses} "
        f"channels={comparator.channels} linear={reference.linear} "
        f"fixed_slerp={reference.fixed_slerp} "
        f"shortest_path={reference.shortest_path} "
        f"max_lane_error={comparator.max_lane_error:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
