#!/usr/bin/env python3
"""Validate NFL 2K5's native 25-slot player local-pose sampler.

The C implementation is compared with an independent Python equation model
over the exact packed frames of shipped SMCD ``ANM_CELEBRATE_USER_34``. The
validator pins the XBE map/callback/helper bytes and obtains the two twist axes
directly from the shipped ``lo_body/LO_res`` SCNE rather than trusting C data.
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
from nfl_coach_ref_pose_native_validate import (
    NativeClip,
    NativeGltfPose,
    NativePose,
    NativePoseInfo,
    ReferenceModel,
    ValidationError,
    c_add,
    c_mul,
    conjugate,
    cross3,
    dot3,
    f32,
    f32_from_raw,
    hamilton,
    pointer_name,
    raw_f32,
    rotate_vector,
    sha256,
    sha256_file,
)
from nfl_quaternion_interpolation import XbeImage
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_inventory import resolve_relative


EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
PLAYER_MAP_VA = 0x0051CD70
PLAYER_MAP_BYTES = 64
PACKED_CHANNELS = 23
LOGICAL_CHANNELS = 25
PACKED_SCALE_VA = 0x004EEA18
WRAPPER_SIZE = 0x20

PLAYER_SCNE_OUTER = 3
PLAYER_SCNE_CHUNK = 113
PLAYER_SCENE = "lo_body"
PLAYER_SHAPE = "LO_res"
EXPECTED_AXIS_BITS = (
    (0x410FACE0, 0xBEB8A406, 0x40D16DA0),
    (0xC10F9F2E, 0xBEB8B701, 0x40D190E9),
)

WITNESS_OUTER = 3092
WITNESS_OUTER_ID = "0xdaddb151"
WITNESS_CHUNK = 163
WITNESS_NAME = "ANM_CELEBRATE_USER_34"
WITNESS_RESOURCE_SHA256 = (
    "a86c827b09db69990c4070cbb59d5c989db420a9d03427acd814823361a82e52"
)
WITNESS_REGION_SHA256 = (
    "084f73d9a217c9d56dbf0c6ef7f32e46d4c3a6f752ef0509d5c653c90623a813"
)
WITNESS_PACKED_SHA256 = (
    "2b2415e137717e9d34b578713274994876d53a3d09c15fd8b7fbd92c457f9efc"
)

FUNCTION_HASHES = {
    (0x000901E0, 103):
        "5e74fa8a692df69e4890c6c47e103601c1d610d92ff96472e3b332e08cbbe7f4",
    (0x00091890, 26):
        "b4e5af75639cfb7ee5e2717e77d0617a9e355aa471b56473c0c93c7d2b9e9b81",
    (0x000DF700, 421):
        "5dce74744c2ede4ab231d61753c73909c634c8c85f9474699b5f6588bedc48d9",
    (0x001C2530, 821):
        "fda9f3e7aced9ba164c16b6fe26d2a34609673b6ae4161955338a424b3177072",
    (0x003CA150, 140):
        "76343d475ba9c89963bf42f9a1951e8b20183759dd8e05e72ab4b288ec06f945",
}


def validate_xbe(image: XbeImage) -> bytes:
    if image.md5 != EXPECTED_XBE_MD5:
        raise ValidationError(f"unexpected XBE MD5 {image.md5}")
    for (va, size), expected in FUNCTION_HASHES.items():
        if sha256(image.at(va, size)) != expected:
            raise ValidationError(f"XBE function hash differs at {va:#x}")
    map_bytes = image.at(PLAYER_MAP_VA, PLAYER_MAP_BYTES)
    expected = bytes.fromhex(
        "00000105020603070408050106020703080409090a0a0b0b0c0c"
        "0d110e120f13ffff1014110d120e130fffff141015161615"
        "0000000000000000000000000000"
    )
    if map_bytes != expected:
        raise ValidationError("XBE player signed channel map differs")
    if [index for index in range(LOGICAL_CHANNELS)
            if map_bytes[index * 2] == 0xFF] != [16, 21]:
        raise ValidationError("XBE player disabled-channel set differs")
    return map_bytes


def extract_player_axes(index_path: Path, scan_path: Path) -> list[dict[str, object]]:
    archive = nfl_outer.parse_archive(index_path)
    _, resources = parse_inventory(scan_path)
    resource = next(
        (
            item for item in resources
            if item.outer_index == PLAYER_SCNE_OUTER
            and item.chunk_index == PLAYER_SCNE_CHUNK
            and item.kind == "SCNE"
        ),
        None,
    )
    if resource is None:
        raise ValidationError("missing player LO_res SCNE axis source")
    entry = archive.entries[PLAYER_SCNE_OUTER]
    span = nfl_outer.read_entry_range(
        archive, entry, resource.chunk_offset,
        WRAPPER_SIZE + resource.stored_size,
    )
    decoded, _ = decode_resource(span, resource)
    limit = resource.word_08
    scene_name = pointer_name(decoded, 0x10, limit, "player axis scene")
    if scene_name != PLAYER_SCENE:
        raise ValidationError(f"player axis scene is {scene_name!r}")
    descriptor = resolve_relative(decoded, 0x14, limit, "player descriptor")
    if descriptor is None:
        raise ValidationError("player SCNE descriptor is null")
    shape_count = struct.unpack_from("<I", decoded, descriptor + 0x2C)[0]
    shape_start = resolve_relative(decoded, descriptor + 0x30, limit, "player shapes")
    if shape_start is None:
        raise ValidationError("player SCNE shape table is null")

    result: list[dict[str, object]] = []
    for shape_index in range(shape_count):
        shape = shape_start + shape_index * 0x100
        shape_name = pointer_name(decoded, shape + 0x40, limit, "player shape")
        if shape_name != PLAYER_SHAPE:
            continue
        transform_count = struct.unpack_from("<H", decoded, shape + 0x50)[0]
        transform_start = resolve_relative(
            decoded, shape + 0x64, limit, "LO_res transforms"
        )
        if transform_count != LOGICAL_CHANNELS or transform_start is None:
            raise ValidationError("LO_res does not contain 25 transforms")
        found: dict[str, tuple[int, int, tuple[int, ...]]] = {}
        for transform_index in range(transform_count):
            record = transform_start + transform_index * 0x70
            name = pointer_name(
                decoded, record + 0x60, limit,
                f"LO_res transform {transform_index}",
            )
            if name in ("lhand", "rhand"):
                parent = struct.unpack_from("<i", decoded, record + 0x64)[0]
                bits = struct.unpack_from("<4I", decoded, record + 0x50)
                found[name] = (transform_index, parent, bits)
        expected = {
            "lhand": (17, 16, EXPECTED_AXIS_BITS[0]),
            "rhand": (22, 21, EXPECTED_AXIS_BITS[1]),
        }
        for side, (name, wanted) in enumerate(expected.items()):
            if name not in found:
                raise ValidationError(f"LO_res is missing {name}")
            transform_index, parent, bits = found[name]
            if ((transform_index, parent, bits[:3]) != wanted or
                    bits[3] != 0x3F800000):
                raise ValidationError(f"LO_res/{name} bind vector differs")
            result.append(
                {
                    "outer_index": PLAYER_SCNE_OUTER,
                    "chunk_index": PLAYER_SCNE_CHUNK,
                    "scene_name": scene_name,
                    "shape_name": shape_name,
                    "transform_name": name,
                    "transform_index": transform_index,
                    "parent_index": parent,
                    "side": side,
                    "axis_bits": bits[:3],
                }
            )
    if len(result) != 2:
        raise ValidationError(f"found {len(result)}/2 player hand axes")
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
        raise ValidationError("missing player SMCD witness")
    if not (
        resource["kind"] == "SMCD"
        and resource["name"] == WITNESS_NAME
        and resource["outer_id"] == WITNESS_OUTER_ID
        and int(resource["root_count"]) == 1
        and resource["decoded_sha256"] == WITNESS_RESOURCE_SHA256
    ):
        raise ValidationError("player SMCD witness identity differs")

    root = resource["roots"][0]
    words = tuple(int(value, 16) for value in root["header_words"])
    fields = {
        "frame_count": words[0] >> 16,
        "channel_count": words[0] & 0xFF,
        "flags": words[1] & 0xFF,
        "sample_rate": words[3] & 0xFF,
        "time_scale": f32_from_raw(words[4]),
        "duration": f32_from_raw(words[5]),
    }
    if not (
        root["offset"] == 76
        and fields["frame_count"] == 93
        and fields["channel_count"] == PACKED_CHANNELS
        and fields["flags"] == 2
        and fields["sample_rate"] == 15
        and fields["time_scale"] == 1.0
        and raw_f32(float(fields["duration"])) == 0x40C2AAAB
    ):
        raise ValidationError("player SMCD root fields differ")
    region = next(
        (
            item for item in resource["packed_regions"]
            if int(item["owner_root_index"]) == 0
            and int(item["owner_pointer_field_relative"]) == 0x24
        ),
        None,
    )
    if region is None or int(region["offset"]) != 888:
        raise ValidationError("player SMCD quaternion pointer differs")
    archive = nfl_outer.parse_archive(index_path)
    entry = archive.entries[WITNESS_OUTER]
    body = nfl_outer.read_entry_range(
        archive, entry, int(resource["chunk_offset"]) + WRAPPER_SIZE,
        int(resource["stored_size"]),
    )
    if sha256(body) != WITNESS_RESOURCE_SHA256:
        raise ValidationError("player SMCD archive bytes differ")
    start = int(region["offset"])
    end = int(region["end"])
    full_region = body[start:end]
    addressed = int(fields["frame_count"]) * PACKED_CHANNELS * 4
    packed = full_region[:addressed]
    slack = full_region[addressed:]
    if not (
        len(full_region) == 8568
        and region["sha256"] == WITNESS_REGION_SHA256
        and sha256(full_region) == WITNESS_REGION_SHA256
        and len(packed) == 8556
        and sha256(packed) == WITNESS_PACKED_SHA256
        and slack == bytes(12)
    ):
        raise ValidationError("player SMCD quaternion region differs")
    fields["packed_slack_bytes"] = len(slack)
    return packed, fields


def full_twist(
    axis: Sequence[float], source: Sequence[float],
) -> tuple[float, ...]:
    """Independent semantic model of XBE 0x001C2530."""
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
        rotated[index] - bind[index] * projection_scale
        for index in range(3)
    )
    cosine = dot3(perpendicular, projected) / math.sqrt(
        dot3(perpendicular, perpendicular) * dot3(projected, projected)
    )
    cosine = min(1.0, max(-1.0, cosine))
    signed_inverse_length = 1.0 / math.sqrt(norm_squared)
    if dot3(cross3(perpendicular, projected), bind) < 0.0:
        signed_inverse_length = -signed_inverse_length
    scalar = math.sqrt((1.0 + cosine) * 0.5)
    vector_scale = math.sqrt((1.0 - cosine) * 0.5) * signed_inverse_length
    return tuple(
        f32(value) for value in (
            scalar,
            bind[0] * vector_scale,
            bind[1] * vector_scale,
            bind[2] * vector_scale,
        )
    )


class PlayerReferenceModel(ReferenceModel):
    def __init__(self, image: XbeImage, packed: bytes, fields: dict[str, object]):
        super().__init__(image, packed, fields)
        self.map = image.at(PLAYER_MAP_VA, PLAYER_MAP_BYTES)
        self.axes = tuple(
            tuple(f32_from_raw(value) for value in side)
            for side in EXPECTED_AXIS_BITS
        )

    def pose(self, seconds: float, mirrored: bool) -> list[tuple[float, ...]]:
        output: list[tuple[float, ...]] = [
            (0.0, 0.0, 0.0, 0.0)
        ] * LOGICAL_CHANNELS
        for logical in range(LOGICAL_CHANNELS):
            if self.map[logical * 2 + int(mirrored)] == 0xFF:
                continue
            output[logical] = self.sample_channel(seconds, logical, mirrored)
        for side, (wrist, hand) in enumerate(((16, 17), (21, 22))):
            twist = full_twist(self.axes[side], output[hand])
            adjusted = tuple(
                f32(value)
                for value in hamilton(conjugate(twist), output[hand])
            )
            output[wrist] = twist
            output[hand] = adjusted
        return output


class PlayerNativeComparator:
    def __init__(
        self,
        library_path: Path,
        label: str,
        map_bytes: bytes,
        packed: bytes,
        fields: dict[str, object],
        reference: PlayerReferenceModel,
    ) -> None:
        self.label = label
        self.library = ctypes.CDLL(str(library_path.resolve()))
        self.sample = self.library.vc_nfl_player_pose_sample_clamped
        self.sample.argtypes = [
            ctypes.POINTER(NativeClip), ctypes.c_float, ctypes.c_bool,
            ctypes.POINTER(NativePose), ctypes.POINTER(NativePoseInfo),
        ]
        self.sample.restype = ctypes.c_int
        self.sample_title = self.library.vc_nfl_player_pose_sample_title_policy
        self.sample_title.argtypes = [
            ctypes.POINTER(NativeClip), ctypes.c_float,
            ctypes.POINTER(NativePose), ctypes.POINTER(NativePoseInfo),
        ]
        self.sample_title.restype = ctypes.c_int
        self.to_gltf = self.library.vc_nfl_player_pose_to_gltf_xyzw
        self.to_gltf.argtypes = [
            ctypes.POINTER(NativePose), ctypes.POINTER(NativeGltfPose),
        ]
        self.to_gltf.restype = None
        self.bit_exact = self.library.vc_nfl_player_pose_twist_is_xbox_bit_exact
        self.bit_exact.argtypes = []
        self.bit_exact.restype = ctypes.c_bool

        native_map = (ctypes.c_int8 * PLAYER_MAP_BYTES).in_dll(
            self.library, "vc_nfl_player_pose_channel_map"
        )
        if bytes(int(value) & 0xFF for value in native_map) != map_bytes:
            raise ValidationError(f"{label}: native player map differs from XBE")
        native_axes = (ctypes.c_float * 6).in_dll(
            self.library, "vc_nfl_player_pose_hand_bind_axes"
        )
        if tuple(raw_f32(value) for value in native_axes) != (
            EXPECTED_AXIS_BITS[0] + EXPECTED_AXIS_BITS[1]
        ):
            raise ValidationError(f"{label}: native player axes differ from SCNE")
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
        self.gltf_reorders = 0
        self.max_lane_error = 0.0

    def compare_pose(
        self,
        seconds_source: float,
        mirrored: bool,
        *,
        title: bool = False,
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
                if expected_normalized is None
                else f32(expected_normalized)
            )
        else:
            status = self.sample(
                ctypes.byref(self.clip), seconds, mirrored,
                ctypes.byref(output), ctypes.byref(info),
            )
            normalized = seconds
        if status != 0:
            raise ValidationError(f"{self.label}: native player status {status}")
        if not (
            info.sample_status == 0
            and info.failed_logical_channel == 0xFF
            and bool(info.mirrored) == mirrored
            and raw_f32(info.normalized_seconds) == raw_f32(normalized)
            and info.completed_loops == expected_loops
        ):
            raise ValidationError(f"{self.label}: player pose metadata differs")

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
        for wrist in (16, 21):
            norm_error = abs(
                sum(float(value) ** 2 for value in output.scalar_first[wrist])
                - 1.0
            )
            if norm_error > 2.0e-6:
                raise ValidationError(
                    f"{self.label}: synthesized wrist {wrist} is not unit"
                )

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
        coordinates = (
            0.0, 0.25, 1.5, 10.125, 24.5, 47.75, 70.375, 91.25,
            92.0, 100.0,
        )
        denominator = c_mul(float(self.clip.sample_rate), self.clip.time_scale)
        for coordinate in coordinates:
            seconds = f32(f32(coordinate) / denominator)
            self.compare_pose(seconds, False)
            self.compare_pose(seconds, True)

        title_seconds = c_add(self.clip.duration_seconds, 1.0)
        self.compare_pose(title_seconds, False, title=True)

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
    comparator: PlayerNativeComparator,
    reference: PlayerReferenceModel,
) -> dict[str, object]:
    source_paths = (
        Path("include/recovered/nfl2k5/player_pose.h"),
        Path("src/recovered/nfl2k5/player_pose.c"),
        Path("tests/nfl_player_pose_test.c"),
        Path("tools/nfl_player_pose_native_validate.py"),
        Path("tools/nfl_coach_ref_pose_native_validate.py"),
        Path("tools/nfl_quaternion_interpolation.py"),
        Path("tools/nfl_outer.py"),
        Path("tools/nfl_scene_probe.py"),
        Path("tools/nfl_scne_inventory.py"),
    )
    input_paths = (
        args.index, args.resource_scan, args.motion_inventory, args.xbe_header,
    )
    return {
        "schema": "nfl2k5_player_pose_native/v1",
        "executable": {
            "path": str(args.xbe),
            "md5": image.md5,
            "sha256": sha256(image.data),
            "function_hashes": {
                f"0x{va:08x}+0x{size:x}": digest
                for (va, size), digest in FUNCTION_HASHES.items()
            },
            "player_map": {
                "va": f"0x{PLAYER_MAP_VA:08x}",
                "length": len(map_bytes),
                "raw_hex": map_bytes.hex(),
                "sha256": sha256(map_bytes),
                "disabled_logical_channels": [16, 21],
            },
        },
        "corpus_axes": {
            "source": "SCNE lo_body/LO_res transform +0x50.xyz",
            "copy_count": len(axes),
            "copies": [
                {
                    **{
                        key: item[key] for key in (
                            "outer_index", "chunk_index", "scene_name",
                            "shape_name", "transform_name", "transform_index",
                            "parent_index", "side",
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
            "outer_id": WITNESS_OUTER_ID,
            "chunk_index": WITNESS_CHUNK,
            "kind": "SMCD",
            "name": WITNESS_NAME,
            "decoded_sha256": WITNESS_RESOURCE_SHA256,
            "full_quaternion_region_sha256": WITNESS_REGION_SHA256,
            "addressed_packed_sha256": WITNESS_PACKED_SHA256,
            "addressed_packed_bytes": 8556,
            "zero_slack_bytes": int(fields["packed_slack_bytes"]),
            "frame_count": int(fields["frame_count"]),
            "packed_channels_per_frame": int(fields["channel_count"]),
            "sample_rate": int(fields["sample_rate"]),
            "time_scale_bits": f"0x{raw_f32(float(fields['time_scale'])):08x}",
            "duration_bits": f"0x{raw_f32(float(fields['duration'])):08x}",
            "flags": f"0x{int(fields['flags']):02x}",
            "ownership_boundary": (
                "the shipped bytes are canonical here; selector-to-controller "
                "ownership is proved by the separate player clip-path report"
            ),
        },
        "native_contract": {
            "logical_channel_count": LOGICAL_CHANNELS,
            "packed_channel_count": PACKED_CHANNELS,
            "input_quaternion_order": "scalar-first [w,x,y,z]",
            "gltf_quaternion_order": "[x,y,z,w] with XYZ retained",
            "callback": (
                "slots 16/21 receive full signed twist extracted from sampled "
                "slots 17/22; each hand becomes conjugate(twist)*sampled_hand"
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
            "expected_compilers": ["gcc", "clang-18"],
        },
        "source_files": {str(path): sha256_file(path) for path in source_paths},
        "input_files": {str(path): sha256_file(path) for path in input_paths},
        "portme": [
            "// PORTME: attach the proved local pose to the exact live player controller/root state for every gameplay family.",
            "// PORTME: retain caller-specific trajectory and external-root ownership when emitting player glTF animation.",
            "// PORTME: emulate 0x001C2530 x87/SSE rounding only if bit-exact Xbox replay is required.",
        ],
    }


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        image = XbeImage(args.xbe, args.xbe_header)
        map_bytes = validate_xbe(image)
        axes = extract_player_axes(args.index, args.resource_scan)
        packed, fields = extract_witness(args.index, args.motion_inventory)
        reference = PlayerReferenceModel(image, packed, fields)
        comparator = PlayerNativeComparator(
            args.library, args.label, map_bytes, packed, fields, reference
        )
        comparator.run()
        if not (
            comparator.poses == 22
            and comparator.channels == 550
            and comparator.gltf_reorders == 550
            and reference.linear > 0
            and reference.fixed_slerp > 0
            # This exact witness contains no negative-dot adjacent pair. The
            # leaf interpolation gate separately covers shortest-path slerp.
            and reference.shortest_path == 0
        ):
            raise ValidationError("player semantic branch/coverage counts differ")
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
        print(f"nfl_player_pose_native_validate: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_PLAYER_POSE_NATIVE_CORPUS_PASS "
        f"compiler={args.label} witness={WITNESS_NAME} axes={len(axes)} "
        f"poses={comparator.poses} channels={comparator.channels} "
        f"linear={reference.linear} fixed_slerp={reference.fixed_slerp} "
        f"shortest_path={reference.shortest_path} "
        f"max_lane_error={comparator.max_lane_error:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
