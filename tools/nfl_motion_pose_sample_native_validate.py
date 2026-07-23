#!/usr/bin/env python3
"""Corpus-check the native composed NFL 2K5 pose-channel sampler.

The raw packed decoder already has an exhaustive 14-million-record verifier.
This verifier instead exercises the higher-level composition over every shipped
SMCD/MMCD root: time-to-frame addressing, the executable identity channel map,
packed decode, fixed-table quaternion interpolation, mirroring, and clamp.

It deliberately does not bind logical channels to skeleton nodes.  That
association is a separate executable-evidence problem and remains a PORTME.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable

import nfl_outer
from nfl_quaternion_interpolation import (
    ANGLE_CONSTANT_VAS,
    THRESHOLD_VA,
    XbeImage,
    f32,
    interpolate_reference,
    table_rows,
)


WRAPPER_SIZE = 0x20
IDENTITY_CHANNEL_MAP_VA = 0x004F24A0
PACKED_SCALE_RAW = 0x3AB55FA3
EXPECTED_RESOURCES = 5_198
EXPECTED_ROOTS = 6_068
SAMPLES_PER_ROOT = 3


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


class NativeSampleInfo(ctypes.Structure):
    _fields_ = [
        ("frame_coordinate", ctypes.c_float),
        ("interpolation_t", ctypes.c_float),
        ("left_frame", ctypes.c_uint16),
        ("right_frame", ctypes.c_uint16),
        ("logical_channel", ctypes.c_uint8),
        ("packed_index", ctypes.c_int8),
        ("mirrored", ctypes.c_bool),
        ("interpolation", NativeInterpolationInfo),
    ]


class NativeTitleSampleInfo(ctypes.Structure):
    _fields_ = [
        ("pose", NativeSampleInfo),
        ("normalized_seconds", ctypes.c_float),
        ("completed_loops", ctypes.c_uint32),
    ]


Float4 = ctypes.c_float * 4
Int8Map = ctypes.c_int8 * 64


def float_raw(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def flip_sign(value: float) -> float:
    return struct.unpack(
        "<f", struct.pack("<I", float_raw(value) ^ 0x8000_0000)
    )[0]


def c_mul(left: float, right: float) -> float:
    """One ISO-C binary32 multiplication on the supported Linux hosts."""
    return f32(f32(left) * f32(right))


def c_add(left: float, right: float) -> float:
    """One ISO-C binary32 addition on the supported Linux hosts."""
    return f32(f32(left) + f32(right))


def decode_reference(encoded: bytes) -> tuple[float, float, float, float]:
    if len(encoded) != 4:
        raise ValueError("packed pose reference requires exactly four bytes")
    (word,) = struct.unpack("<I", encoded)
    packed = (
        ((word >> 20) & 0x3FF) - 0x200,
        ((word >> 10) & 0x3FF) - 0x200,
        (word & 0x3FF) - 0x200,
    )
    scale = struct.unpack("<f", struct.pack("<I", PACKED_SCALE_RAW))[0]
    stored = tuple(c_mul(float(value), scale) for value in packed)
    square01 = c_add(c_mul(stored[0], stored[0]), c_mul(stored[1], stored[1]))
    square_sum = c_add(square01, c_mul(stored[2], stored[2]))
    radicand = c_add(1.0, -square_sum)
    if not math.isfinite(radicand) or radicand < 0.0:
        raise ValueError("reference packed pose has a negative radicand")
    missing = f32(math.sqrt(radicand))
    omitted = word >> 30
    lanes = list(stored)
    lanes.insert(omitted, missing)
    return tuple(lanes)  # type: ignore[return-value]


def region_bytes(
    body: bytes,
    regions: dict[tuple[int, int], dict[str, object]],
    root_index: int,
    pointer_relative: int,
) -> bytes:
    region = regions[(root_index, pointer_relative)]
    start = int(region["offset"])
    end = int(region["end"])
    return body[start:end]


class Comparator:
    def __init__(
        self,
        library_path: Path,
        image: XbeImage,
    ) -> None:
        library = ctypes.CDLL(str(library_path.resolve()))
        self.sample = library.vc_nfl_motion_pose_sample_channel_clamped
        self.sample.argtypes = [
            ctypes.POINTER(NativeClip),
            ctypes.c_float,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int8),
            ctypes.c_bool,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(NativeSampleInfo),
        ]
        self.sample.restype = ctypes.c_int
        self.sample_title = (
            library.vc_nfl_motion_pose_sample_channel_title_policy
        )
        self.sample_title.argtypes = [
            ctypes.POINTER(NativeClip),
            ctypes.c_float,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_int8),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(NativeTitleSampleInfo),
        ]
        self.sample_title.restype = ctypes.c_int

        identity = image.at(IDENTITY_CHANNEL_MAP_VA, 64)
        expected = bytes(value for index in range(32) for value in (index, index))
        if identity != expected:
            raise ValueError("XBE identity channel map differs")
        self.identity_map = Int8Map(*identity)
        self.table = table_rows(image)
        self.constants = {va: image.float(va) for _, va in ANGLE_CONSTANT_VAS}
        self.threshold = self.constants[THRESHOLD_VA]

        self.roots = 0
        self.samples = 0
        self.mirrored_samples = 0
        self.explicit_map_samples = 0
        self.clamped_samples = 0
        self.interpolated_samples = 0
        self.linear_samples = 0
        self.fixed_slerp_samples = 0
        self.shortest_path_samples = 0
        self.title_policy_samples = 0
        self.title_loop_samples = 0
        self.title_mirror_samples = 0
        self.title_completed_loops = 0
        self.unique_packed_words: set[int] = set()
        self.maximum_lane_error = 0.0
        self.maximum_weight_error = 0.0

    def expected_coordinate(self, sample_rate: int, seconds: float,
                            time_scale: float) -> float:
        return c_mul(c_mul(float(sample_rate), seconds), time_scale)

    def check_sample(
        self,
        source: ctypes.Array[ctypes.c_uint8],
        encoded: bytes,
        frame_count: int,
        channel_count: int,
        sample_rate: int,
        time_scale: float,
        seconds_source: float,
        logical_channel: int,
        explicit_map: bool,
        mirrored: bool,
    ) -> None:
        seconds = f32(seconds_source)
        clip = NativeClip(
            ctypes.cast(source, ctypes.POINTER(ctypes.c_uint8)),
            len(encoded),
            frame_count,
            channel_count,
            sample_rate,
            time_scale,
            0,
            0.0,
        )
        output = Float4()
        info = NativeSampleInfo()
        map_pointer = self.identity_map if explicit_map else None
        status = self.sample(
            ctypes.byref(clip),
            seconds,
            logical_channel,
            map_pointer,
            mirrored,
            output,
            ctypes.byref(info),
        )
        if status != 0:
            raise ValueError(f"native composed sampler returned status {status}")

        coordinate = self.expected_coordinate(sample_rate, seconds, time_scale)
        final_frame = frame_count - 1
        if coordinate < float(final_frame):
            left_frame = math.floor(coordinate)
            right_frame = left_frame + 1
            interpolation_t = f32(coordinate - float(left_frame))
        else:
            left_frame = final_frame
            right_frame = final_frame
            interpolation_t = 0.0

        packed_index = logical_channel
        left_offset = (left_frame * channel_count + packed_index) * 4
        right_offset = (right_frame * channel_count + packed_index) * 4
        left_encoded = encoded[left_offset : left_offset + 4]
        right_encoded = encoded[right_offset : right_offset + 4]
        self.unique_packed_words.add(struct.unpack("<I", left_encoded)[0])
        self.unique_packed_words.add(struct.unpack("<I", right_encoded)[0])
        left = decode_reference(left_encoded)
        right = decode_reference(right_encoded)

        if left_frame == right_frame:
            expected_output = left
            expected_interpolation = {
                "branch": "linear",
                "shortest_path_negated": False,
                "theta_units": -1,
                "step_units": -1,
                "weight0": 1.0,
                "weight1": 0.0,
            }
            self.clamped_samples += 1
        else:
            expected_interpolation = interpolate_reference(
                left,
                right,
                interpolation_t,
                self.threshold,
                self.constants,
                self.table,
            )
            expected_output = expected_interpolation["output"]
            self.interpolated_samples += 1
            if expected_interpolation["branch"] == "linear":
                self.linear_samples += 1
            else:
                self.fixed_slerp_samples += 1
            self.shortest_path_samples += bool(
                expected_interpolation["shortest_path_negated"]
            )

        if mirrored:
            expected_output = (
                expected_output[0],
                expected_output[1],
                flip_sign(expected_output[2]),
                flip_sign(expected_output[3]),
            )
            self.mirrored_samples += 1
        self.explicit_map_samples += explicit_map

        expected_branch = (
            0 if expected_interpolation["branch"] == "linear" else 1
        )
        if not (
            float_raw(info.frame_coordinate) == float_raw(coordinate)
            and float_raw(info.interpolation_t) == float_raw(interpolation_t)
            and info.left_frame == left_frame
            and info.right_frame == right_frame
            and info.logical_channel == logical_channel
            and info.packed_index == packed_index
            and bool(info.mirrored) == mirrored
            and info.interpolation.branch == expected_branch
            and bool(info.interpolation.shortest_path_negated)
                == bool(expected_interpolation["shortest_path_negated"])
            and info.interpolation.theta_units
                == expected_interpolation["theta_units"]
            and info.interpolation.step_units
                == expected_interpolation["step_units"]
        ):
            raise ValueError("native composed sampler metadata differs")

        for actual, wanted in zip(output, expected_output, strict=True):
            difference = abs(float(actual) - float(wanted))
            self.maximum_lane_error = max(self.maximum_lane_error, difference)
            if difference > 2.0e-6:
                raise ValueError(
                    f"native composed sampler lane error {difference} exceeds tolerance"
                )
        for actual, wanted in (
            (info.interpolation.left_weight, expected_interpolation["weight0"]),
            (info.interpolation.right_weight, expected_interpolation["weight1"]),
        ):
            difference = abs(float(actual) - float(wanted))
            self.maximum_weight_error = max(self.maximum_weight_error, difference)
            if difference > 2.0e-6:
                raise ValueError(
                    "native composed sampler interpolation-weight error "
                    f"{difference} exceeds tolerance"
                )
        self.samples += 1

    @staticmethod
    def sample_info_equal(left: NativeSampleInfo,
                          right: NativeSampleInfo) -> bool:
        return (
            float_raw(left.frame_coordinate) == float_raw(right.frame_coordinate)
            and float_raw(left.interpolation_t) == float_raw(right.interpolation_t)
            and left.left_frame == right.left_frame
            and left.right_frame == right.right_frame
            and left.logical_channel == right.logical_channel
            and left.packed_index == right.packed_index
            and bool(left.mirrored) == bool(right.mirrored)
            and left.interpolation.branch == right.interpolation.branch
            and bool(left.interpolation.shortest_path_negated)
                == bool(right.interpolation.shortest_path_negated)
            and left.interpolation.theta_units
                == right.interpolation.theta_units
            and left.interpolation.step_units == right.interpolation.step_units
            and float_raw(left.interpolation.left_weight)
                == float_raw(right.interpolation.left_weight)
            and float_raw(left.interpolation.right_weight)
                == float_raw(right.interpolation.right_weight)
        )

    def check_title_policy(
        self,
        source: ctypes.Array[ctypes.c_uint8],
        encoded: bytes,
        frame_count: int,
        channel_count: int,
        sample_rate: int,
        time_scale: float,
        flags: int,
        duration_seconds: float,
        seconds_source: float,
        logical_channel: int,
    ) -> None:
        seconds = f32(seconds_source)
        duration = f32(duration_seconds)
        clip = NativeClip(
            ctypes.cast(source, ctypes.POINTER(ctypes.c_uint8)),
            len(encoded),
            frame_count,
            channel_count,
            sample_rate,
            time_scale,
            flags,
            duration,
        )
        output = Float4()
        info = NativeTitleSampleInfo()
        status = self.sample_title(
            ctypes.byref(clip),
            seconds,
            logical_channel,
            self.identity_map,
            output,
            ctypes.byref(info),
        )
        if status != 0:
            raise ValueError(f"native title-policy sampler returned status {status}")

        normalized = seconds
        completed_loops = 0
        if flags & 1:
            while duration <= normalized:
                normalized = c_add(normalized, -duration)
                completed_loops += 1
        mirrored = bool(flags & 4)

        reference_output = Float4()
        reference_info = NativeSampleInfo()
        reference_status = self.sample(
            ctypes.byref(clip),
            normalized,
            logical_channel,
            self.identity_map,
            mirrored,
            reference_output,
            ctypes.byref(reference_info),
        )
        if reference_status != 0:
            raise ValueError(
                f"native low-level reference returned status {reference_status}"
            )
        if not (
            float_raw(info.normalized_seconds) == float_raw(normalized)
            and info.completed_loops == completed_loops
            and self.sample_info_equal(info.pose, reference_info)
            and all(
                float_raw(actual) == float_raw(wanted)
                for actual, wanted in zip(output, reference_output, strict=True)
            )
        ):
            raise ValueError("native title-policy composition differs")

        self.title_policy_samples += 1
        self.title_loop_samples += bool(flags & 1)
        self.title_mirror_samples += mirrored
        self.title_completed_loops += completed_loops

    def check_root(
        self,
        encoded: bytes,
        frame_count: int,
        channel_count: int,
        sample_rate: int,
        time_scale: float,
        flags: int,
        duration_seconds: float,
        global_root_index: int,
    ) -> None:
        expected_bytes = frame_count * channel_count * 4
        if len(encoded) != expected_bytes:
            raise ValueError("composed-sampler source span differs")
        source = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)

        # The first call exercises the API's null-map identity contract.
        self.check_sample(
            source, encoded, frame_count, channel_count, sample_rate,
            time_scale, 0.0, 0, False, False,
        )

        # Spread an explicit-XBE-map sample over the interior frame range.
        final_frame = frame_count - 1
        interior_frame = (global_root_index * 37) % final_frame
        fraction = ((global_root_index % 7) + 1) / 8.0
        target_coordinate = f32(float(interior_frame) + fraction)
        denominator = c_mul(float(sample_rate), time_scale)
        interior_seconds = f32(target_coordinate / denominator)
        self.check_sample(
            source, encoded, frame_count, channel_count, sample_rate,
            time_scale, interior_seconds, channel_count // 2, True, False,
        )

        # Move at least two frame intervals past duration to force final clamp;
        # mirror the final logical channel through the XBE identity map.
        final_seconds = f32(float(final_frame) / denominator)
        clamped_seconds = c_add(final_seconds, f32(2.0 / denominator))
        self.check_sample(
            source, encoded, frame_count, channel_count, sample_rate,
            time_scale, clamped_seconds, channel_count - 1, True, True,
        )

        # Exercise the controller policy with the real root flags. Looping
        # clips wrap once; non-looping clips reach the low-level final clamp.
        title_seconds = c_add(
            duration_seconds,
            f32(2.0 / denominator),
        )
        self.check_title_policy(
            source, encoded, frame_count, channel_count, sample_rate,
            time_scale, flags, duration_seconds, title_seconds,
            global_root_index % channel_count,
        )
        self.roots += 1


def validate(
    index_path: Path,
    inventory_path: Path,
    xbe_path: Path,
    xbe_header_path: Path,
    library_path: Path,
) -> Comparator:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("schema") != "nfl2k5_motion_inventory/v1":
        raise ValueError("unsupported motion inventory schema")
    resources = inventory.get("resources", [])
    if len(resources) != EXPECTED_RESOURCES:
        raise ValueError("motion inventory resource count differs")

    image = XbeImage(xbe_path, xbe_header_path)
    comparator = Comparator(library_path, image)
    archive = nfl_outer.parse_archive(index_path)

    global_root_index = 0
    for resource in resources:
        entry = archive.entries[int(resource["outer_index"])]
        body = nfl_outer.read_entry_range(
            archive,
            entry,
            int(resource["chunk_offset"]) + WRAPPER_SIZE,
            int(resource["stored_size"]),
        )
        regions = {
            (
                int(region["owner_root_index"]),
                int(region["owner_pointer_field_relative"]),
            ): region
            for region in resource["packed_regions"]
        }
        for root_index, root in enumerate(resource["roots"]):
            words = tuple(int(value, 16) for value in root["header_words"])
            channel_count = words[0] & 0xFF
            frame_count = words[0] >> 16
            sample_rate = words[3] & 0xFF
            time_scale = struct.unpack("<f", struct.pack("<I", words[4]))[0]
            flags = words[1] & 0xFF
            duration_seconds = struct.unpack(
                "<f", struct.pack("<I", words[5])
            )[0]
            region = region_bytes(body, regions, root_index, 0x24)
            payload_bytes = channel_count * frame_count * 4
            comparator.check_root(
                region[:payload_bytes],
                frame_count,
                channel_count,
                sample_rate,
                time_scale,
                flags,
                duration_seconds,
                global_root_index,
            )
            global_root_index += 1

    if comparator.roots != EXPECTED_ROOTS:
        raise ValueError(f"root count differs: {comparator.roots}")
    expected_samples = EXPECTED_ROOTS * SAMPLES_PER_ROOT
    if comparator.samples != expected_samples:
        raise ValueError(f"sample count differs: {comparator.samples}")
    if comparator.clamped_samples != EXPECTED_ROOTS:
        raise ValueError("not every root exercised final-frame clamp")
    if comparator.mirrored_samples != EXPECTED_ROOTS:
        raise ValueError("not every root exercised mirrored output")
    if comparator.explicit_map_samples != EXPECTED_ROOTS * 2:
        raise ValueError("explicit XBE identity-map coverage differs")
    if comparator.interpolated_samples != EXPECTED_ROOTS * 2:
        raise ValueError("interpolated sample coverage differs")
    if comparator.linear_samples == 0 or comparator.fixed_slerp_samples == 0:
        raise ValueError("corpus sample did not exercise both interpolation branches")
    if comparator.shortest_path_samples == 0:
        raise ValueError("corpus sample did not exercise shortest-path negation")
    if comparator.title_policy_samples != EXPECTED_ROOTS:
        raise ValueError("title-policy root coverage differs")
    if comparator.title_loop_samples != 8:
        raise ValueError("title-policy looping-root coverage differs")
    if comparator.title_completed_loops != 8:
        raise ValueError("title-policy completed-loop count differs")
    if comparator.title_mirror_samples != 696:
        raise ValueError("title-policy mirrored-root coverage differs")
    return comparator


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--index", type=Path, required=True)
    result.add_argument("--inventory", type=Path, required=True)
    result.add_argument("--xbe", type=Path, required=True)
    result.add_argument("--xbe-header", type=Path, required=True)
    result.add_argument("--library", type=Path, required=True)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = validate(
            args.index,
            args.inventory,
            args.xbe,
            args.xbe_header,
            args.library,
        )
    except (
        AssertionError,
        OSError,
        ValueError,
        KeyError,
        IndexError,
        struct.error,
        nfl_outer.OuterError,
    ) as exc:
        print(f"nfl_motion_pose_sample_native_validate: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_MOTION_POSE_SAMPLE_NATIVE_FULL_CORPUS_PASS "
        f"roots={result.roots} samples={result.samples} "
        f"unique_words={len(result.unique_packed_words)} "
        f"linear={result.linear_samples} fixed_slerp={result.fixed_slerp_samples} "
        f"shortest_path={result.shortest_path_samples} "
        f"title_policy={result.title_policy_samples} "
        f"looping={result.title_loop_samples} mirrored={result.title_mirror_samples} "
        f"max_lane_error={result.maximum_lane_error:.9g} "
        f"max_weight_error={result.maximum_weight_error:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
