#!/usr/bin/env python3
"""Validate executable-proved NFL 2K5 SMCD sampler semantics over every root.

This deliberately stops short of naming bones or exporting glTF.  The XBE
proves frame addressing, packed-quaternion reconstruction, trajectory/event
sampling, and several root header fields.  It does not prove the mapping from
logical sampler channels to a particular skeleton.

// PORTME: recover per-skeleton signed-byte channel maps and bind them to bones.
// PORTME: name event IDs from the callback table and gameplay consumers.
// PORTME: identify opaque root header bits and the fourth +0x30 record short.
// PORTME: prove coordinate-system/unit conventions before glTF animation export.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable

import nfl_outer


WRAPPER_SIZE = 0x20
ROOT_SIZE = 0x34
QUATERNION_SCALE_VA = 0x004EEA18
IDENTITY_CHANNEL_MAP_VA = 0x004F24A0
EVENT_TICK_SCALE_VA = 0x004F24E0
TRAJECTORY_SCALE_VA = 0x004F24E4
STATIC_ROOT_VA = 0x007B2CFC
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"


class SamplerError(ValueError):
    """Raised when a corpus root violates an executable-proved invariant."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def f32(raw: int) -> float:
    return struct.unpack("<f", struct.pack("<I", raw))[0]


def float_text(value: float) -> str:
    return format(value, ".9g")


def int_distribution(counter: Counter[int]) -> dict[str, int]:
    return {str(key): counter[key] for key in sorted(counter)}


def hex_distribution(counter: Counter[int], width: int = 2) -> dict[str, int]:
    return {f"0x{key:0{width}x}": counter[key] for key in sorted(counter)}


class XbeImage:
    def __init__(self, xbe_path: Path, header_path: Path) -> None:
        self.data = xbe_path.read_bytes()
        self.header = json.loads(header_path.read_text(encoding="utf-8"))
        digest = hashlib.md5(self.data).hexdigest()
        if digest != EXPECTED_XBE_MD5 or self.header.get("md5") != digest:
            raise SamplerError(f"unexpected XBE MD5 {digest}")
        self.sections = self.header["sections"]

    def at(self, va: int, size: int) -> bytes:
        for section in self.sections:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                return self.data[offset : offset + size]
        raise SamplerError(f"VA 0x{va:08x}+0x{size:x} is outside raw XBE sections")


def load_motion_inventory(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema") != "nfl2k5_motion_inventory/v1":
        raise SamplerError("unsupported motion inventory schema")
    if len(report.get("resources", [])) != 5198:
        raise SamplerError("motion inventory is incomplete")
    return report


def region_map(resource: dict[str, object]) -> dict[tuple[int, int], dict[str, object]]:
    result: dict[tuple[int, int], dict[str, object]] = {}
    for region in resource["packed_regions"]:
        key = (
            int(region["owner_root_index"]),
            int(region["owner_pointer_field_relative"]),
        )
        if key in result:
            raise SamplerError(f"duplicate region owner {key}")
        result[key] = region
    return result


def body_region(body: bytes, region: dict[str, object]) -> bytes:
    start = int(region["offset"])
    end = int(region["end"])
    raw = body[start:end]
    if len(raw) != int(region["length"]) or sha256(raw) != region["sha256"]:
        raise SamplerError("motion region differs from the canonical inventory")
    return raw


def scan(
    index_path: Path,
    motion_inventory_path: Path,
    xbe_path: Path,
    xbe_header_path: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    canonical = load_motion_inventory(motion_inventory_path)
    archive = nfl_outer.parse_archive(index_path)
    image = XbeImage(xbe_path, xbe_header_path)

    quaternion_scale_raw = struct.unpack("<I", image.at(QUATERNION_SCALE_VA, 4))[0]
    event_scale_raw = struct.unpack("<I", image.at(EVENT_TICK_SCALE_VA, 4))[0]
    trajectory_scale_raw = struct.unpack("<I", image.at(TRAJECTORY_SCALE_VA, 4))[0]
    quaternion_scale = f32(quaternion_scale_raw)
    event_scale = f32(event_scale_raw)
    trajectory_scale = f32(trajectory_scale_raw)
    if not (
        quaternion_scale_raw == 0x3AB55FA3
        and event_scale_raw == 0x37800000
        and trajectory_scale_raw == 0x3E000000
        and event_scale == 1.0 / 65536.0
        and trajectory_scale == 0.125
    ):
        raise SamplerError("sampler constants differ from the focused XBE trace")

    identity_map = image.at(IDENTITY_CHANNEL_MAP_VA, 64)
    expected_identity = bytes(value for index in range(32) for value in (index, index))
    if identity_map != expected_identity:
        raise SamplerError("the executable identity channel map differs")

    static_words = struct.unpack("<13I", image.at(STATIC_ROOT_VA, ROOT_SIZE))
    static_count = static_words[0] & 0xFF
    static_frames = static_words[0] >> 16
    static_flags = static_words[1] & 0xFF
    static_rate = static_words[3] & 0xFF
    static_pointers = static_words[9:13]
    if not (
        static_count == 21
        and static_frames == 35
        and static_flags == 2
        and static_words[2] == 1
        and static_rate == 15
        and static_words[4] == 0x3F800000
        and static_words[5] == 0x40100000
        and static_pointers == (0x007B2180, 0x007B2068, 0x007B2060, 0)
        and STATIC_ROOT_VA - static_pointers[0] == static_count * static_frames * 4
        and static_pointers[0] - static_pointers[1] == static_frames * 8
        and static_pointers[1] - static_pointers[2] == 8
        and image.at(static_pointers[2], 8)[4:] == b"\xff\xff\xff\xff"
    ):
        raise SamplerError("the executable static default root differs")

    roots: list[dict[str, object]] = []
    channel_counts: Counter[int] = Counter()
    opaque_header_bytes_01: Counter[int] = Counter()
    frame_counts: Counter[int] = Counter()
    flags: Counter[int] = Counter()
    opaque_word04_highs: Counter[int] = Counter()
    sample_rates: Counter[int] = Counter()
    header_bytes_0d: Counter[int] = Counter()
    header_bytes_0e: Counter[int] = Counter()
    header_bytes_0f: Counter[int] = Counter()
    time_scale_raws: Counter[int] = Counter()
    runtime_mask_raws: Counter[int] = Counter()
    event_ids: Counter[int] = Counter()
    event_counts: Counter[int] = Counter()
    omitted_components: Counter[int] = Counter()
    quaternion_slack_lengths: Counter[int] = Counter()
    trajectory_slack_lengths: Counter[int] = Counter()
    trajectory_strides: Counter[int] = Counter()

    main_quaternion_count = 0
    auxiliary_quaternion_count = 0
    maximum_quantized_three_square_sum = 0
    quaternion_slack_bytes = 0
    quaternion_slack_nonzero_bytes = 0
    quaternion_slack_all_zero_roots = 0
    trajectory_record_count = 0
    trajectory_slack_bytes = 0
    trajectory_slack_nonzero_bytes = 0
    trajectory_slack_all_zero_roots = 0
    event_count = 0
    event_roots = 0
    events_after_clip_duration = 0
    roots_with_events_after_clip_duration = 0
    auxiliary_root_count = 0
    duration_window_pass_count = 0
    duration_gap_minimum = math.inf
    duration_gap_maximum = -math.inf
    trajectory_minimum = [32767, 32767, 32767, 32767]
    trajectory_maximum = [-32768, -32768, -32768, -32768]
    auxiliary_minimum = [32767, 32767, 32767, 32767]
    auxiliary_maximum = [-32768, -32768, -32768, -32768]

    for resource in canonical["resources"]:
        outer_index = int(resource["outer_index"])
        entry = archive.entries[outer_index]
        body = nfl_outer.read_entry_range(
            archive,
            entry,
            int(resource["chunk_offset"]) + WRAPPER_SIZE,
            int(resource["stored_size"]),
        )
        if sha256(body) != resource["decoded_sha256"]:
            raise SamplerError(f"{resource['kind']}/{resource['name']}: body SHA differs")
        regions = region_map(resource)

        for root_index, root in enumerate(resource["roots"]):
            root_offset = int(root["offset"])
            words = struct.unpack_from("<13I", body, root_offset)
            expected_words = tuple(int(value, 16) for value in root["header_words"])
            if words != expected_words:
                raise SamplerError(f"{resource['name']} root {root_index}: header differs")

            channel_count = words[0] & 0xFF
            opaque_byte_01 = (words[0] >> 8) & 0xFF
            frame_count = words[0] >> 16
            flag_byte = words[1] & 0xFF
            opaque_word04_high = words[1] >> 8
            runtime_mask = words[2]
            sample_rate = words[3] & 0xFF
            header_byte_0d = (words[3] >> 8) & 0xFF
            header_byte_0e = (words[3] >> 16) & 0xFF
            header_byte_0f = words[3] >> 24
            time_scale = f32(words[4])
            duration = f32(words[5])
            vector = (f32(words[6]), f32(words[7]), f32(words[8]))

            if not (
                1 <= channel_count <= 32
                and frame_count >= 2
                and sample_rate > 0
                and math.isfinite(time_scale)
                and time_scale > 0.0
                and math.isfinite(duration)
                and duration > 0.0
            ):
                raise SamplerError(f"{resource['name']} root {root_index}: invalid header domain")

            duration_coordinate = duration * sample_rate * time_scale
            duration_gap = (frame_count - 1) - duration_coordinate
            if -0.00005 <= duration_gap < 1.0:
                duration_window_pass_count += 1
            else:
                raise SamplerError(
                    f"{resource['name']} root {root_index}: duration lies outside final frame"
                )
            duration_gap_minimum = min(duration_gap_minimum, duration_gap)
            duration_gap_maximum = max(duration_gap_maximum, duration_gap)

            quaternion_region = body_region(body, regions[(root_index, 0x24)])
            quaternion_bytes = channel_count * frame_count * 4
            if len(quaternion_region) < quaternion_bytes:
                raise SamplerError(f"{resource['name']}: quaternion table is truncated")
            quaternion_slack = quaternion_region[quaternion_bytes:]
            if len(quaternion_slack) not in (0, 4, 8, 12):
                raise SamplerError(f"{resource['name']}: quaternion slack is outside domain")
            quaternion_slack_lengths[len(quaternion_slack)] += 1
            quaternion_slack_bytes += len(quaternion_slack)
            quaternion_slack_nonzero_bytes += sum(value != 0 for value in quaternion_slack)
            quaternion_slack_all_zero_roots += not any(quaternion_slack)
            for (packed,) in struct.iter_unpack(
                "<I", quaternion_region[:quaternion_bytes]
            ):
                components = (
                    ((packed >> 20) & 0x3FF) - 0x200,
                    ((packed >> 10) & 0x3FF) - 0x200,
                    (packed & 0x3FF) - 0x200,
                )
                square_sum = sum(value * value for value in components)
                maximum_quantized_three_square_sum = max(
                    maximum_quantized_three_square_sum, square_sum
                )
                if square_sum * quaternion_scale * quaternion_scale > 1.0:
                    raise SamplerError(f"{resource['name']}: invalid packed quaternion")
                omitted_components[packed >> 30] += 1
            main_quaternion_count += channel_count * frame_count

            trajectory_region = body_region(body, regions[(root_index, 0x28)])
            trajectory_stride = 6 if flag_byte & 8 else 8
            trajectory_bytes = frame_count * trajectory_stride
            if len(trajectory_region) < trajectory_bytes:
                raise SamplerError(f"{resource['name']}: trajectory table is truncated")
            trajectory_slack = trajectory_region[trajectory_bytes:]
            if len(trajectory_slack) not in (0, 2):
                raise SamplerError(f"{resource['name']}: trajectory slack is outside domain")
            trajectory_slack_lengths[len(trajectory_slack)] += 1
            trajectory_slack_bytes += len(trajectory_slack)
            trajectory_slack_nonzero_bytes += sum(value != 0 for value in trajectory_slack)
            trajectory_slack_all_zero_roots += not any(trajectory_slack)
            trajectory_strides[trajectory_stride] += 1
            trajectory_record_count += frame_count
            format_string = "<hhhh" if trajectory_stride == 8 else "<hhh"
            for offset in range(0, trajectory_bytes, trajectory_stride):
                values = struct.unpack_from(format_string, trajectory_region, offset)
                for index, value in enumerate(values):
                    trajectory_minimum[index] = min(trajectory_minimum[index], value)
                    trajectory_maximum[index] = max(trajectory_maximum[index], value)

            event_region = body_region(body, regions[(root_index, 0x2C)])
            if not event_region or len(event_region) % 4:
                raise SamplerError(f"{resource['name']}: event stream alignment differs")
            event_words = [value[0] for value in struct.iter_unpack("<I", event_region)]
            if event_words[-1] != 0xFFFFFFFF or 0xFFFFFFFF in event_words[:-1]:
                raise SamplerError(f"{resource['name']}: event sentinel differs")
            events = event_words[:-1]
            ticks = [value >> 8 for value in events]
            if ticks != sorted(ticks):
                raise SamplerError(f"{resource['name']}: event ticks are not monotonic")
            root_after_duration = 0
            for value, tick in zip(events, ticks):
                event_ids[value & 0xFF] += 1
                event_time = tick * event_scale / time_scale
                if event_time > duration + 0.00002:
                    events_after_clip_duration += 1
                    root_after_duration += 1
            roots_with_events_after_clip_duration += root_after_duration != 0
            event_count += len(events)
            event_counts[len(events)] += 1
            event_roots += bool(events)

            auxiliary_records = 0
            if (root_index, 0x30) in regions:
                auxiliary_root_count += 1
                auxiliary_region = body_region(body, regions[(root_index, 0x30)])
                if len(auxiliary_region) != frame_count * 12:
                    raise SamplerError(f"{resource['name']}: +0x30 table size differs")
                auxiliary_records = frame_count
                for offset in range(0, len(auxiliary_region), 12):
                    packed, a, b, c, d = struct.unpack_from(
                        "<Ihhhh", auxiliary_region, offset
                    )
                    components = (
                        ((packed >> 20) & 0x3FF) - 0x200,
                        ((packed >> 10) & 0x3FF) - 0x200,
                        (packed & 0x3FF) - 0x200,
                    )
                    square_sum = sum(value * value for value in components)
                    maximum_quantized_three_square_sum = max(
                        maximum_quantized_three_square_sum, square_sum
                    )
                    if square_sum * quaternion_scale * quaternion_scale > 1.0:
                        raise SamplerError(f"{resource['name']}: invalid auxiliary quaternion")
                    omitted_components[packed >> 30] += 1
                    for index, value in enumerate((a, b, c, d)):
                        auxiliary_minimum[index] = min(auxiliary_minimum[index], value)
                        auxiliary_maximum[index] = max(auxiliary_maximum[index], value)
                auxiliary_quaternion_count += frame_count

            channel_counts[channel_count] += 1
            opaque_header_bytes_01[opaque_byte_01] += 1
            frame_counts[frame_count] += 1
            flags[flag_byte] += 1
            opaque_word04_highs[opaque_word04_high] += 1
            sample_rates[sample_rate] += 1
            header_bytes_0d[header_byte_0d] += 1
            header_bytes_0e[header_byte_0e] += 1
            header_bytes_0f[header_byte_0f] += 1
            time_scale_raws[words[4]] += 1
            runtime_mask_raws[runtime_mask] += 1
            roots.append(
                {
                    "outer_index": outer_index,
                    "outer_id": resource["outer_id"],
                    "chunk_index": int(resource["chunk_index"]),
                    "kind": resource["kind"],
                    "name": resource["name"],
                    "root_index": root_index,
                    "root_offset": root_offset,
                    "packed_quaternion_dwords_per_frame": channel_count,
                    "opaque_header_byte_01": opaque_byte_01,
                    "frame_count": frame_count,
                    "flags": flag_byte,
                    "opaque_word04_bits_08_31": opaque_word04_high,
                    "runtime_mask_word08": runtime_mask,
                    "sample_rate": sample_rate,
                    "header_byte_0d": header_byte_0d,
                    "header_byte_0e": header_byte_0e,
                    "header_byte_0f": header_byte_0f,
                    "time_scale_raw": words[4],
                    "time_scale": float_text(time_scale),
                    "duration_raw": words[5],
                    "duration": float_text(duration),
                    "duration_coordinate": float_text(duration_coordinate),
                    "last_sample_coordinate": frame_count - 1,
                    "duration_gap": float_text(duration_gap),
                    "opaque_vector_raw": [words[6], words[7], words[8]],
                    "opaque_vector": [float_text(value) for value in vector],
                    "quaternion_bytes": quaternion_bytes,
                    "quaternion_region_length": len(quaternion_region),
                    "quaternion_slack_length": len(quaternion_slack),
                    "quaternion_slack_sha256": sha256(quaternion_slack),
                    "trajectory_stride": trajectory_stride,
                    "trajectory_bytes": trajectory_bytes,
                    "trajectory_region_length": len(trajectory_region),
                    "trajectory_slack_length": len(trajectory_slack),
                    "trajectory_slack_sha256": sha256(trajectory_slack),
                    "event_count": len(events),
                    "event_first_tick": ticks[0] if ticks else "",
                    "event_last_tick": ticks[-1] if ticks else "",
                    "events_after_clip_duration": root_after_duration,
                    "auxiliary_record_count": auxiliary_records,
                }
            )

    root_count = len(roots)
    if root_count != 6068:
        raise SamplerError(f"expected 6068 roots, found {root_count}")

    report: dict[str, object] = {
        "schema": "nfl2k5_motion_sampler_inventory/v1",
        "source_index": str(index_path),
        "source_motion_inventory": str(motion_inventory_path),
        "source_xbe": str(xbe_path),
        "source_xbe_header": str(xbe_header_path),
        "executable_evidence": {
            "md5": EXPECTED_XBE_MD5,
            "prefetch_lookup": "0x001685b0",
            "root_acquire": "0x001685e0",
            "celebration_prefetch_caller": "0x001b6b50",
            "paired_motion_prefetch_callers": ["0x002407d0", "0x002408a0"],
            "frame_cursor": "0x000df8b0",
            "packed_quaternion_decoder": "0x000ded10",
            "trajectory_sampler": "0x000dee30",
            "event_iterator": "0x000df030",
            "channel_map_iterator": "0x000df9b0",
            "sample_blend_driver": "0x0031b910",
            "root_mask_combiner": "0x0031b190",
            "auxiliary_sampler": "0x000df450",
        },
        "proved_root_fields": {
            "0x00_byte": "packed quaternion dwords per frame",
            "0x01_byte": "opaque",
            "0x02_u16": "frame count",
            "0x04_byte": "flags consumed at least at bits 0, 2, and 3",
            "0x04_bits_08_31": "opaque",
            "0x08_u32": "runtime mask/flags operand; bit 31 is set by acquire",
            "0x0c_byte": "sample rate used in frame addressing",
            "0x0d_0x0f": "opaque; observed bytes are retained",
            "0x10_f32": "time scale used in frame and event addressing",
            "0x14_f32": "clip duration used by controller clamp/wrap",
            "0x18_0x20": "opaque finite float triplet",
            "0x24_pointer": "frame-major packed quaternion dwords",
            "0x28_pointer": "frame-major signed-short trajectory records",
            "0x2c_pointer": "monotonic event words terminated by 0xffffffff",
            "0x30_pointer": "optional frame-major 12-byte auxiliary records",
        },
        "proved_algorithms": {
            "frame_coordinate": "sample_rate * time_seconds * time_scale",
            "packed_quaternion": (
                "three signed 10-bit components use (q-512)*0.00138377060648; "
                "bits 30..31 select the reconstructed positive sqrt component"
            ),
            "trajectory": (
                "flags bit 3 selects 6-byte xyz records; otherwise 8-byte "
                "xyz+yaw records; xyz signed shorts scale by 0.125 and yaw shifts left 3"
            ),
            "events": (
                "low 8 bits are event ID; high 24 bits are ticks; "
                "seconds=ticks*(1/65536)/time_scale"
            ),
            "channel_iteration": (
                "a 32-bit logical mask is shifted once per channel; a signed-byte "
                "map selects the packed quaternion index, with negative entries skipped"
            ),
        },
        "executable_constants": {
            "quaternion_scale": {
                "va": f"0x{QUATERNION_SCALE_VA:08x}",
                "raw": f"0x{quaternion_scale_raw:08x}",
                "value": float_text(quaternion_scale),
            },
            "event_tick_scale": {
                "va": f"0x{EVENT_TICK_SCALE_VA:08x}",
                "raw": f"0x{event_scale_raw:08x}",
                "value": float_text(event_scale),
            },
            "trajectory_scale": {
                "va": f"0x{TRAJECTORY_SCALE_VA:08x}",
                "raw": f"0x{trajectory_scale_raw:08x}",
                "value": float_text(trajectory_scale),
            },
            "identity_channel_map": {
                "va": f"0x{IDENTITY_CHANNEL_MAP_VA:08x}",
                "sha256": sha256(identity_map),
                "contract": "32 adjacent [index,index] signed-byte pairs",
            },
        },
        "static_default_root": {
            "va": f"0x{STATIC_ROOT_VA:08x}",
            "header_words": [f"0x{value:08x}" for value in static_words],
            "packed_quaternion_dwords_per_frame": static_count,
            "frame_count": static_frames,
            "flags": static_flags,
            "sample_rate": static_rate,
            "time_scale": float_text(f32(static_words[4])),
            "duration": float_text(f32(static_words[5])),
            "pointer_targets": [f"0x{value:08x}" for value in static_pointers],
            "quaternion_bytes": STATIC_ROOT_VA - static_pointers[0],
            "trajectory_bytes": static_pointers[0] - static_pointers[1],
            "event_bytes": static_pointers[1] - static_pointers[2],
        },
        "summary": {
            "resource_count": len(canonical["resources"]),
            "root_count": root_count,
            "all_body_hashes_match": True,
            "duration_within_final_sample_window_count": duration_window_pass_count,
            "duration_gap_coordinate_minimum": float_text(duration_gap_minimum),
            "duration_gap_coordinate_maximum": float_text(duration_gap_maximum),
            "main_packed_quaternion_count": main_quaternion_count,
            "auxiliary_packed_quaternion_count": auxiliary_quaternion_count,
            "maximum_quantized_three_square_sum": maximum_quantized_three_square_sum,
            "all_packed_quaternion_radicands_nonnegative": True,
            "trajectory_record_count": trajectory_record_count,
            "event_count": event_count,
            "event_root_count": event_roots,
            "events_after_clip_duration": events_after_clip_duration,
            "roots_with_events_after_clip_duration": roots_with_events_after_clip_duration,
            "all_event_streams_sentinel_terminated": True,
            "all_event_ticks_monotonic": True,
            "auxiliary_root_count": auxiliary_root_count,
            "quaternion_slack_bytes": quaternion_slack_bytes,
            "quaternion_slack_nonzero_bytes": quaternion_slack_nonzero_bytes,
            "quaternion_slack_all_zero_root_count": quaternion_slack_all_zero_roots,
            "trajectory_slack_bytes": trajectory_slack_bytes,
            "trajectory_slack_nonzero_bytes": trajectory_slack_nonzero_bytes,
            "trajectory_slack_all_zero_root_count": trajectory_slack_all_zero_roots,
        },
        "domains": {
            "packed_quaternion_dwords_per_frame": int_distribution(channel_counts),
            "opaque_header_byte_01": {
                "minimum": min(opaque_header_bytes_01),
                "maximum": max(opaque_header_bytes_01),
                "unique_count": len(opaque_header_bytes_01),
            },
            "frame_count": {
                "minimum": min(frame_counts),
                "maximum": max(frame_counts),
                "unique_count": len(frame_counts),
            },
            "flags": hex_distribution(flags),
            "opaque_word04_bits_08_31_unique_count": len(opaque_word04_highs),
            "sample_rate": int_distribution(sample_rates),
            "header_byte_0d": int_distribution(header_bytes_0d),
            "header_byte_0e": int_distribution(header_bytes_0e),
            "header_byte_0f": int_distribution(header_bytes_0f),
            "time_scale_raw": hex_distribution(time_scale_raws, 8),
            "runtime_mask_word08_unique_count": len(runtime_mask_raws),
            "runtime_mask_word08_nonzero_count": sum(
                count for raw, count in runtime_mask_raws.items() if raw != 0
            ),
            "event_count_per_root": int_distribution(event_counts),
            "event_id": int_distribution(event_ids),
            "trajectory_stride": int_distribution(trajectory_strides),
            "quaternion_slack_length": int_distribution(quaternion_slack_lengths),
            "trajectory_slack_length": int_distribution(trajectory_slack_lengths),
            "packed_quaternion_omitted_component": int_distribution(omitted_components),
            "trajectory_signed_short_minimum": trajectory_minimum,
            "trajectory_signed_short_maximum": trajectory_maximum,
            "auxiliary_signed_short_minimum": auxiliary_minimum,
            "auxiliary_signed_short_maximum": auxiliary_maximum,
        },
        "worked": [
            "followed three preload callers through later root acquisition into the shared sampler",
            "recovered exact frame-major quaternion and trajectory capacities for every root",
            "recovered the packed smallest-three quaternion reconstruction and constants",
            "recovered event sentinel/tick/ID iteration and verified all streams",
            "recovered signed-byte logical channel iteration and the executable identity map",
            "validated every inference over 5,198 resources and 6,068 roots",
        ],
        "failed": [
            "preload callers do not directly invoke the sampler; resource acquisition and controller setup occur later",
            "event timestamps are not universally bounded by clip duration; 69 retained events occur later",
            "alignment slack after +0x24/+0x28 payload capacity is not universally zero",
        ],
        "portme": [
            "PORTME: recover per-skeleton signed-byte channel maps and bind logical channels to bones",
            "PORTME: name event IDs and callback semantics from the handler table and gameplay consumers",
            "PORTME: identify opaque header byte/bits, word +0x08 bit roles, and +0x18..+0x20 semantics",
            "PORTME: identify the fourth signed short in optional +0x30 records",
            "PORTME: prove axes, handedness, units, root motion, and skeleton binding before glTF export",
        ],
    }
    return report, roots


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "outer_index", "outer_id", "chunk_index", "kind", "name", "root_index",
        "root_offset", "packed_quaternion_dwords_per_frame", "opaque_header_byte_01",
        "frame_count", "flags", "opaque_word04_bits_08_31", "runtime_mask_word08",
        "sample_rate", "header_byte_0d", "header_byte_0e", "header_byte_0f",
        "time_scale_raw", "time_scale", "duration_raw", "duration",
        "duration_coordinate", "last_sample_coordinate", "duration_gap",
        "opaque_vector_raw", "opaque_vector", "quaternion_bytes",
        "quaternion_region_length", "quaternion_slack_length",
        "quaternion_slack_sha256", "trajectory_stride", "trajectory_bytes",
        "trajectory_region_length", "trajectory_slack_length",
        "trajectory_slack_sha256", "event_count", "event_first_tick",
        "event_last_tick", "events_after_clip_duration", "auxiliary_record_count",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        for row in rows:
            encoded = dict(row)
            encoded["root_offset"] = f"0x{int(row['root_offset']):x}"
            encoded["flags"] = f"0x{int(row['flags']):02x}"
            encoded["opaque_word04_bits_08_31"] = (
                f"0x{int(row['opaque_word04_bits_08_31']):06x}"
            )
            encoded["runtime_mask_word08"] = f"0x{int(row['runtime_mask_word08']):08x}"
            encoded["time_scale_raw"] = f"0x{int(row['time_scale_raw']):08x}"
            encoded["duration_raw"] = f"0x{int(row['duration_raw']):08x}"
            encoded["opaque_vector_raw"] = ",".join(
                f"0x{int(value):08x}" for value in row["opaque_vector_raw"]
            )
            encoded["opaque_vector"] = ",".join(row["opaque_vector"])
            writer.writerow(encoded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="NFL 2K5 outer archive index file")
    parser.add_argument(
        "--motion-inventory",
        type=Path,
        default=Path("reports/assets/nfl2k5_motion_inventory.json"),
    )
    parser.add_argument(
        "--xbe",
        type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    parser.add_argument(
        "--xbe-header",
        type=Path,
        default=Path("reports/headers/nfl2k5_xbe_header.json"),
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report, roots = scan(
            args.index, args.motion_inventory, args.xbe, args.xbe_header
        )
    except (OSError, ValueError, KeyError, struct.error, nfl_outer.OuterError) as exc:
        print(f"nfl_motion_sampler_inventory: {exc}", file=sys.stderr)
        return 1
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_tsv(args.tsv, roots)
    print(
        "NFL_MOTION_SAMPLER_INVENTORY_COMPLETE "
        f"resources={report['summary']['resource_count']} "
        f"roots={report['summary']['root_count']} "
        f"quaternions={report['summary']['main_packed_quaternion_count']} "
        f"events={report['summary']['event_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
