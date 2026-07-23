#!/usr/bin/env python3
"""Recover APF 2K8 SingleMoCap structure without inventing its bone codec.

The executable proves a four-pointer SingleMoCap root, a bounded signed-int16
root-vector sampler, and a terminated event stream.  This tool applies those
contracts to all 68 resources, preserves every byte in deterministic corpus
files, and joins the separately registered BoneScaleMap resources to exact
SCNE hierarchy-name CRCs.  The packed per-bone motion region stays opaque.

// PORTME: recover packed per-bone channel IDs, widths, quantization, and time.
// PORTME: prove packed channels against SCNE bones before emitting glTF.
// PORTME: prove allocation and archive integrity rules before adding a writer.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable
import zlib

import apf_inner
import apf_outer


MOCAP_TYPE = "SingleMoCap"
BONE_SCALE_TYPE = "BoneScaleMap"
MOCAP_ROOT_SIZE = 0x30
MOCAP_POINTER_FIELDS = (0x20, 0x24, 0x28, 0x2C)
ROOT_SAMPLE_STRIDE = 6
EVENT_SENTINEL = 0xFFFFFFFF

EXPECTED_SOURCES = (
    {
        "outer_table_index": 659,
        "outer_name_id": 0x6CB47FC1,
        "outer_name": "gamedata.iff",
        "outer_stored_length": 16_445_440,
        "outer_stored_sha256": "7077a50912167a6c9ad06014277b9e838bb45e6d9d9dc10d5e0da5ec9f398177",
        "iff_file_count": 332,
        "block_count": 3,
        "block0_decoded_length": 2_682_036,
        "block0_decoded_sha256": "f0f60830c078c510fd39ec0ac3f58e5f7e16b758a3efec40413e0da3349eed56",
        "mocap_count": 8,
        "mocap_bytes": 583_176,
    },
    {
        "outer_table_index": 1310,
        "outer_name_id": 0xDB5E3E48,
        "outer_name": "global.iff",
        "outer_stored_length": 25_028_608,
        "outer_stored_sha256": "752bc94e99ae0bc1a3ec732c5b4912ef6ef234149183e76dc059973c714d792d",
        "iff_file_count": 442,
        "block_count": 3,
        "block0_decoded_length": 6_082_684,
        "block0_decoded_sha256": "a7ceb209338e0892cec168eecbc9fe4b0acd0ddf8c276a60fb4cb2547c613f58",
        "mocap_count": 2,
        "mocap_bytes": 5_520,
    },
    {
        "outer_table_index": 1493,
        "outer_name_id": 0xF69D21E4,
        "outer_name": "frontend_sync.iff",
        "outer_stored_length": 2_826_240,
        "outer_stored_sha256": "630c5baab6c4815f2bf45a06bf890b7b264cd159de267a4a655d06ff79eef7f2",
        "iff_file_count": 157,
        "block_count": 2,
        "block0_decoded_length": 2_687_952,
        "block0_decoded_sha256": "d8a44f3bc61f0d137e959c711bf5aa26d7d3730db8329063019313f239966f5b",
        "mocap_count": 58,
        "mocap_bytes": 712_384,
    },
)

EXPECTED_BONE_MAPS = {
    "lores": {
        "inner_index": 226,
        "length": 896,
        "sha256": "21ba51db97a33a523d7734985a7776dc43984a2bca251d95e5fa52cece7beab5",
        "bone_count": 52,
    },
    "hires": {
        "inner_index": 313,
        "length": 1152,
        "sha256": "af5fc4498005af7ecb83469a1ddb5c1ec6cf797ac7abc6f090085263085c0b4e",
        "bone_count": 92,
    },
}

EXPECTED_ALIAS_SHA256 = "4d419269ecb4fa37b14556fefe7bb365ec01f7fe7f8f86b7e026e8b75067b933"


class MoCapError(ValueError):
    """Raised when a corpus field violates an executable-proved invariant."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def hex32(value: int) -> str:
    return f"0x{value:08x}"


def signed32(value: int) -> int:
    return value if value < 0x80000000 else value - 0x1_0000_0000


def crc32_name(name: str) -> int:
    return zlib.crc32(name.lower().encode("utf-8")) & 0xFFFFFFFF


def resolve_pointer(data: bytes, field_offset: int, minimum: int) -> tuple[int, int] | None:
    if field_offset < 0 or field_offset + 4 > len(data):
        raise MoCapError(f"pointer field 0x{field_offset:x} is outside body")
    raw = struct.unpack_from(">I", data, field_offset)[0]
    if raw == 0:
        return None
    target = field_offset + signed32(raw) - 1
    if target < minimum or target > len(data):
        raise MoCapError(
            f"pointer at 0x{field_offset:x} resolves outside body: 0x{target:x}"
        )
    return raw, target


def region(index: int, role: str, data: bytes, start: int, end: int,
           semantic_status: str) -> dict[str, object]:
    if start < 0 or end < start or end > len(data):
        raise MoCapError(f"bad {role} region 0x{start:x}..0x{end:x}")
    body = data[start:end]
    return {
        "index": index,
        "role": role,
        "semantic_status": semantic_status,
        "offset": start,
        "end": end,
        "length": len(body),
        "sha256": sha256(body),
    }


def parse_mocap_body(
    outer_index: int,
    outer_name: str,
    inner_index: int,
    name: str,
    part_offset: int,
    data: bytes,
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    identity = f"outer {outer_index} inner {inner_index} {name!r}"
    if len(data) < MOCAP_ROOT_SIZE or len(data) % 8:
        raise MoCapError(f"{identity}: body length {len(data)} is not 8-byte aligned/minimal")

    words = struct.unpack_from(">12I", data, 0)
    flags = words[0]
    sample_count, unknown_06 = struct.unpack_from(">HH", data, 4)
    time_scale, duration, value_14, value_18, value_1c = struct.unpack_from(">5f", data, 0x0C)
    if unknown_06 != 100 or words[2] != 0:
        raise MoCapError(f"{identity}: root constants differ")
    if not all(math.isfinite(value) for value in (time_scale, duration, value_14, value_18, value_1c)):
        raise MoCapError(f"{identity}: non-finite root float")
    if time_scale != 1.0 or duration < 0.0:
        raise MoCapError(f"{identity}: unexpected time scale/duration")

    rate_hz = (flags >> 9) & 0xFF
    variable_pointer_count = (flags >> 17) & 0x1F
    mirror = bool(flags & 0x40)
    if rate_hz not in (15, 60) or variable_pointer_count != 0 or not (flags & 0x80):
        raise MoCapError(f"{identity}: unsupported packed flags {hex32(flags)}")

    common: dict[str, object] = {
        "outer_table_index": outer_index,
        "outer_name": outer_name,
        "inner_index": inner_index,
        "name": name,
        "name_crc32": hex32(crc32_name(name)),
        "part_block_index": 0,
        "part_offset": part_offset,
        "length": len(data),
        "sha256": sha256(data),
        "flags": hex32(flags),
        "mirror_flag": mirror,
        "sample_rate_hz": rate_hz,
        "sample_count": sample_count,
        "unknown_u16_06": unknown_06,
        "variable_pointer_count": variable_pointer_count,
        "time_scale": time_scale,
        "duration": duration,
        "root_float_14": value_14,
        "root_float_18": value_18,
        "root_float_1c": value_1c,
        "root_words": [hex32(value) for value in words],
    }

    if name == "hand_pose_mirror":
        if (
            outer_index != 1310
            or inner_index != 75
            or len(data) != MOCAP_ROOT_SIZE
            or sha256(data) != EXPECTED_ALIAS_SHA256
            or flags != 0x780078C1
            or words[8] != crc32_name("hand_pose")
            or any(words[index] != 0 for index in (9, 10, 11))
        ):
            raise MoCapError(f"{identity}: compact alias contract differs")
        common.update(
            {
                "kind": "compact_mirror_alias",
                "alias_target_name": "hand_pose",
                "alias_target_crc32": hex32(words[8]),
                "pointers": [],
                "regions": [region(0, "alias_root", data, 0, len(data), "decoded")],
                "event_count": 0,
                "event_sentinel_count": 0,
                "root_sample_stride": None,
                "root_sample_bytes": 0,
                "alignment_tail_hex": "",
            }
        )
        return common, [], []

    pointers = {
        offset: resolve_pointer(data, offset, MOCAP_ROOT_SIZE)
        for offset in MOCAP_POINTER_FIELDS
    }
    if any(pointers[offset] is None for offset in (0x20, 0x24, 0x28)):
        raise MoCapError(f"{identity}: a required pointer is null")
    main_target = pointers[0x20][1]  # type: ignore[index]
    sample_target = pointers[0x24][1]  # type: ignore[index]
    marker_target = pointers[0x28][1]  # type: ignore[index]
    optional_target = pointers[0x2C][1] if pointers[0x2C] is not None else None
    if main_target != MOCAP_ROOT_SIZE:
        raise MoCapError(f"{identity}: main target is 0x{main_target:x}, not 0x30")
    if optional_target is not None and not (main_target < optional_target < marker_target):
        raise MoCapError(f"{identity}: optional target order is invalid")
    if not (main_target < marker_target < sample_target <= len(data)):
        raise MoCapError(f"{identity}: required target order is invalid")

    marker_bytes = data[marker_target:sample_target]
    if len(marker_bytes) < 4 or len(marker_bytes) % 4:
        raise MoCapError(f"{identity}: marker stream length is invalid")
    marker_words = list(struct.unpack(f">{len(marker_bytes) // 4}I", marker_bytes))
    if marker_words[-1] != EVENT_SENTINEL or EVENT_SENTINEL in marker_words[:-1]:
        raise MoCapError(f"{identity}: marker sentinel is not unique/final")

    events: list[dict[str, object]] = []
    previous_time = -1.0
    for event_index, raw in enumerate(marker_words[:-1]):
        event_time_fixed = raw >> 8
        event_time = event_time_fixed / 65536.0 / time_scale
        if event_time < previous_time or event_time > duration + 1e-5:
            raise MoCapError(f"{identity}: marker times are unordered/outside duration")
        previous_time = event_time
        events.append(
            {
                "outer_table_index": outer_index,
                "inner_index": inner_index,
                "name": name,
                "event_index": event_index,
                "raw_word": hex32(raw),
                "event_id": raw & 0xFF,
                "time_fixed_high24": event_time_fixed,
                "time": event_time,
            }
        )

    sample_bytes = sample_count * ROOT_SAMPLE_STRIDE
    sample_end = sample_target + sample_bytes
    if sample_count == 0 or sample_end > len(data) or len(data) - sample_end >= 8:
        raise MoCapError(f"{identity}: root sample extent is invalid")
    samples: list[dict[str, object]] = []
    for sample_index in range(sample_count):
        offset = sample_target + sample_index * ROOT_SAMPLE_STRIDE
        raw_components = struct.unpack_from(">3h", data, offset)
        samples.append(
            {
                "outer_table_index": outer_index,
                "inner_index": inner_index,
                "name": name,
                "sample_index": sample_index,
                "time": sample_index / (rate_hz * time_scale),
                "raw_component_0": raw_components[0],
                "raw_component_1": raw_components[1],
                "raw_component_2": raw_components[2],
                "component_0": raw_components[0] * 0.125,
                "component_1": raw_components[1] * 0.125,
                "component_2": raw_components[2] * 0.125,
            }
        )

    main_end = optional_target if optional_target is not None else marker_target
    regions = [
        region(0, "serialized_root", data, 0, MOCAP_ROOT_SIZE, "decoded"),
        region(1, "packed_motion", data, main_target, main_end, "opaque"),
    ]
    if optional_target is not None:
        regions.append(region(2, "optional_packed_motion", data, optional_target,
                              marker_target, "opaque"))
    regions.extend(
        [
            region(len(regions), "event_stream", data, marker_target, sample_target, "decoded"),
            region(len(regions) + 1, "root_vector_samples", data, sample_target,
                   sample_end, "decoded"),
            region(len(regions) + 2, "alignment_tail", data, sample_end, len(data),
                   "opaque"),
        ]
    )
    rebuilt = b"".join(data[item["offset"]:item["end"]] for item in regions)
    if rebuilt != data:
        raise MoCapError(f"{identity}: root/region segmentation does not rebuild")

    common.update(
        {
            "kind": "full_clip",
            "pointers": [
                {
                    "field_offset": offset,
                    "stored_value": hex32(pointer[0]) if pointer is not None else "0x00000000",
                    "target": pointer[1] if pointer is not None else None,
                }
                for offset, pointer in pointers.items()
            ],
            "regions": regions,
            "event_count": len(events),
            "event_sentinel_count": 1,
            "root_sample_stride": ROOT_SAMPLE_STRIDE,
            "root_sample_bytes": sample_bytes,
            "alignment_tail_hex": data[sample_end:].hex(),
        }
    )
    return common, events, samples


def load_scene_names(path: Path) -> tuple[dict[int, dict[str, int]], dict[str, object]]:
    digest = file_sha256(path)
    with path.open("r", encoding="utf-8") as stream:
        report = json.load(stream)
    if report.get("schema") != "apf_scene_inventory/v1":
        raise MoCapError("SCNE inventory schema differs")
    summary = report.get("summary", {})
    expected = {
        "scne_parsed": 1303,
        "scne_failures": 0,
        "scene_nodes": 13006,
        "hierarchy_records": 40991,
    }
    if any(summary.get(key) != value for key, value in expected.items()):
        raise MoCapError("SCNE inventory summary anchor differs")

    names: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add(item: dict[str, object], kind: str) -> None:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise MoCapError(f"SCNE {kind} has no name")
        stored = item.get("name_crc32")
        exact_case_crc = zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF
        value = int(str(stored), 0) if stored is not None else exact_case_crc
        if value != exact_case_crc:
            raise MoCapError(f"SCNE name CRC differs for {name!r}")
        names[value][name] += 1

    for scene in report.get("scenes", []):
        for node in scene.get("nodes", []):
            add(node, "node")
            hierarchy = node.get("hierarchy")
            if isinstance(hierarchy, dict):
                for record in hierarchy.get("records", []):
                    add(record, "hierarchy record")
    return names, {
        "path": str(path),
        "sha256": digest,
        "schema": report["schema"],
        "scene_count": summary["scne_parsed"],
        "node_count": summary["scene_nodes"],
        "hierarchy_record_count": summary["hierarchy_records"],
        "distinct_name_crc_count": len(names),
    }


def scene_match(value: int, names: dict[int, dict[str, int]], required: bool) -> dict[str, object] | None:
    matches = names.get(value, {})
    if not matches:
        if required:
            raise MoCapError(f"required SCNE name hash {hex32(value)} has no match")
        return None
    if len(matches) != 1:
        raise MoCapError(
            f"SCNE CRC collision at {hex32(value)}: {sorted(matches)}"
        )
    name, occurrence_count = next(iter(matches.items()))
    return {"name": name, "occurrence_count": occurrence_count}


def parse_bone_scale_map(
    outer_index: int,
    inner_index: int,
    name: str,
    part_offset: int,
    data: bytes,
    scene_names: dict[int, dict[str, int]],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    identity = f"outer {outer_index} inner {inner_index} BoneScaleMap {name!r}"
    expected = EXPECTED_BONE_MAPS.get(name)
    if expected is None or inner_index != expected["inner_index"]:
        raise MoCapError(f"{identity}: unexpected resource identity")
    if len(data) != expected["length"] or sha256(data) != expected["sha256"]:
        raise MoCapError(f"{identity}: exact body anchor differs")
    if len(data) < 0x1C or len(data) % 16:
        raise MoCapError(f"{identity}: body length differs")

    zero, bone_count, raw_bones, raw_slots, slot_count, raw_drivers, raw_vectors = struct.unpack_from(
        ">7I", data, 0
    )
    if zero != 0 or bone_count != expected["bone_count"] or slot_count != 19:
        raise MoCapError(f"{identity}: root counts/constants differ")
    resolved = {
        offset: resolve_pointer(data, offset, 0x1C)
        for offset in (0x08, 0x0C, 0x14, 0x18)
    }
    if any(pointer is None for pointer in resolved.values()):
        raise MoCapError(f"{identity}: null array pointer")
    targets = [resolved[offset][1] for offset in (0x08, 0x0C, 0x14, 0x18)]  # type: ignore[index]
    expected_targets = [
        0x1C,
        0x1C + bone_count * 4,
        0x1C + bone_count * 8,
        0x1C + bone_count * 8 + slot_count * 4 + 8,
    ]
    if targets != expected_targets:
        raise MoCapError(f"{identity}: array targets differ: {targets}")
    bone_start, slot_start, driver_start, vector_start = targets
    vector_end = vector_start + slot_count * 16
    if vector_end > len(data):
        raise MoCapError(f"{identity}: vector array exceeds body")

    bone_hashes = struct.unpack_from(f">{bone_count}I", data, bone_start)
    scale_slots = struct.unpack_from(f">{bone_count}I", data, slot_start)
    driver_hashes = struct.unpack_from(f">{slot_count}I", data, driver_start)
    if any(value >= slot_count for value in scale_slots):
        raise MoCapError(f"{identity}: bone-to-scale slot index is out of range")
    vectors = [struct.unpack_from(">4f", data, vector_start + index * 16)
               for index in range(slot_count)]
    if any(not all(math.isfinite(component) for component in vector) for vector in vectors):
        raise MoCapError(f"{identity}: non-finite scale vector")
    if any(vector[3] != 0.0 for vector in vectors):
        raise MoCapError(f"{identity}: vector component 3 differs from zero")

    driver_rows: list[dict[str, object]] = []
    driver_names: list[dict[str, object] | None] = []
    for slot, (driver_hash, vector) in enumerate(zip(driver_hashes, vectors)):
        match = scene_match(driver_hash, scene_names, False)
        driver_names.append(match)
        driver_rows.append(
            {
                "map_name": name,
                "slot": slot,
                "driver_hash": hex32(driver_hash),
                "driver_name": match["name"] if match else None,
                "scene_occurrence_count": match["occurrence_count"] if match else 0,
                "component_0": vector[0],
                "component_1": vector[1],
                "component_2": vector[2],
                "component_3": vector[3],
            }
        )

    bone_rows: list[dict[str, object]] = []
    for bone_index, (bone_hash, slot) in enumerate(zip(bone_hashes, scale_slots)):
        match = scene_match(bone_hash, scene_names, True)
        assert match is not None
        driver = driver_rows[slot]
        bone_rows.append(
            {
                "map_name": name,
                "bone_index": bone_index,
                "bone_hash": hex32(bone_hash),
                "bone_name": match["name"],
                "scene_occurrence_count": match["occurrence_count"],
                "scale_slot": slot,
                "driver_hash": driver["driver_hash"],
                "driver_name": driver["driver_name"],
                "component_0": driver["component_0"],
                "component_1": driver["component_1"],
                "component_2": driver["component_2"],
                "component_3": driver["component_3"],
            }
        )

    regions = [
        region(0, "serialized_root", data, 0, 0x1C, "decoded"),
        region(1, "bone_name_hashes", data, bone_start, slot_start, "decoded"),
        region(2, "bone_to_scale_slots", data, slot_start, driver_start, "decoded"),
        region(3, "driver_name_hashes", data, driver_start,
               driver_start + slot_count * 4, "decoded"),
        region(4, "opaque_alignment_bytes", data, driver_start + slot_count * 4,
               vector_start, "opaque"),
        region(5, "scale_vectors", data, vector_start, vector_end, "decoded"),
        region(6, "trailing_zero_region", data, vector_end, len(data), "opaque"),
    ]
    if b"".join(data[item["offset"]:item["end"]] for item in regions) != data:
        raise MoCapError(f"{identity}: region segmentation does not rebuild")
    if any(data[vector_end:]):
        raise MoCapError(f"{identity}: trailing region is not zero")

    item = {
        "outer_table_index": outer_index,
        "inner_index": inner_index,
        "name": name,
        "part_block_index": 0,
        "part_offset": part_offset,
        "length": len(data),
        "sha256": sha256(data),
        "root_words": [hex32(value) for value in struct.unpack_from(">7I", data, 0)],
        "bone_count": bone_count,
        "scale_slot_count": slot_count,
        "pointer_targets": targets,
        "regions": regions,
        "resolved_bone_name_count": len(bone_rows),
        "resolved_driver_name_count": sum(match is not None for match in driver_names),
        "unresolved_driver_hashes": [
            hex32(value) for value, match in zip(driver_hashes, driver_names) if match is None
        ],
    }
    return item, bone_rows, driver_rows


def distribution(values: Iterable[int | float]) -> dict[str, object]:
    sequence = list(values)
    if not sequence:
        return {"minimum": None, "maximum": None, "unique_count": 0}
    return {
        "minimum": min(sequence),
        "maximum": max(sequence),
        "unique_count": len(set(sequence)),
    }


def load_apf(
    index_path: Path, scene_names: dict[int, dict[str, int]]
) -> tuple[
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]],
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]],
    list[bytes], list[bytes], list[dict[str, object]],
]:
    archive = apf_outer.parse_archive(index_path)
    resources: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    bone_maps: list[dict[str, object]] = []
    bone_rows: list[dict[str, object]] = []
    driver_rows: list[dict[str, object]] = []
    mocap_bodies: list[bytes] = []
    bone_bodies: list[bytes] = []
    source_rows: list[dict[str, object]] = []
    mocap_corpus_offset = 0
    bone_corpus_offset = 0

    with apf_inner.ArchiveReader(archive) as reader:
        for expected in EXPECTED_SOURCES:
            outer_index = expected["outer_table_index"]
            entry = archive.entries[outer_index]
            if entry.table_index != outer_index or entry.name_id != expected["outer_name_id"]:
                raise MoCapError(f"outer entry {outer_index} identity differs")
            stored = reader.read(entry, 0, entry.size)
            if len(stored) != expected["outer_stored_length"] or sha256(stored) != expected["outer_stored_sha256"]:
                raise MoCapError(f"outer entry {outer_index} stored anchor differs")
            record = apf_inner.parse_iff(reader, entry)
            if record.warnings or len(record.files) != expected["iff_file_count"] or len(record.blocks) != expected["block_count"]:
                raise MoCapError(f"outer entry {outer_index} IFF shape differs")
            decoded = apf_inner.decode_block(reader, record, 0, 16 * 1024 * 1024)
            if len(decoded) != expected["block0_decoded_length"] or sha256(decoded) != expected["block0_decoded_sha256"]:
                raise MoCapError(f"outer entry {outer_index} decoded block anchor differs")

            selected = sorted(
                (item for item in record.files if item.type_name == MOCAP_TYPE),
                key=lambda item: item.index,
            )
            if len(selected) != expected["mocap_count"]:
                raise MoCapError(f"outer entry {outer_index} mocap count differs")
            byte_count = 0
            ranges: list[tuple[int, int]] = []
            for item in selected:
                if item.name is None or len(item.parts) != 1 or item.parts[0].block_index != 0:
                    raise MoCapError(f"outer {outer_index} inner {item.index}: variant parts/name")
                part = item.parts[0]
                body = decoded[part.offset:part.offset + part.length]
                if len(body) != part.length:
                    raise MoCapError(f"outer {outer_index} inner {item.index}: truncated body")
                parsed, clip_events, clip_samples = parse_mocap_body(
                    outer_index, expected["outer_name"], item.index, item.name,
                    part.offset, body,
                )
                parsed["corpus_offset"] = mocap_corpus_offset
                mocap_corpus_offset += len(body)
                resources.append(parsed)
                events.extend(clip_events)
                samples.extend(clip_samples)
                mocap_bodies.append(body)
                ranges.append((part.offset, part.offset + part.length))
                byte_count += len(body)
            for (_, previous_end), (next_start, _) in zip(sorted(ranges), sorted(ranges)[1:]):
                if previous_end > next_start:
                    raise MoCapError(f"outer {outer_index}: overlapping mocap bodies")
            if byte_count != expected["mocap_bytes"]:
                raise MoCapError(f"outer entry {outer_index} mocap byte count differs")

            if outer_index == 1310:
                selected_bones = sorted(
                    (item for item in record.files if item.type_name == BONE_SCALE_TYPE),
                    key=lambda item: item.index,
                )
                if len(selected_bones) != 2:
                    raise MoCapError("global.iff BoneScaleMap count differs")
                for item in selected_bones:
                    if item.name is None or len(item.parts) != 1 or item.parts[0].block_index != 0:
                        raise MoCapError(f"BoneScaleMap inner {item.index}: variant parts/name")
                    part = item.parts[0]
                    body = decoded[part.offset:part.offset + part.length]
                    parsed, map_bones, map_drivers = parse_bone_scale_map(
                        outer_index, item.index, item.name, part.offset, body, scene_names
                    )
                    parsed["corpus_offset"] = bone_corpus_offset
                    bone_corpus_offset += len(body)
                    bone_maps.append(parsed)
                    bone_rows.extend(map_bones)
                    driver_rows.extend(map_drivers)
                    bone_bodies.append(body)

            source_rows.append(
                {
                    **{
                        key: (hex32(value) if key == "outer_name_id" else value)
                        for key, value in expected.items()
                    },
                    "iff_file_length": record.file_length,
                    "mocap_ranges_disjoint_and_bounded": True,
                }
            )

    if len(resources) != 68 or sum(item["length"] for item in resources) != 1_301_080:
        raise MoCapError("complete SingleMoCap corpus totals differ")
    if len({item["name"] for item in resources}) != 68:
        raise MoCapError("SingleMoCap names are not unique")
    if len(bone_maps) != 2 or len(bone_rows) != 144 or len(driver_rows) != 38:
        raise MoCapError("BoneScaleMap corpus totals differ")
    return (
        resources, events, samples, bone_maps, bone_rows, driver_rows,
        mocap_bodies, bone_bodies, source_rows,
    )


def load_nfl_lineage(path: Path, apf_names: set[str]) -> dict[str, object]:
    digest = file_sha256(path)
    with path.open("r", encoding="utf-8") as stream:
        report = json.load(stream)
    if report.get("schema") != "nfl2k5_motion_inventory/v1":
        raise MoCapError("NFL motion inventory schema differs")
    summary = report.get("summary", {})
    expected = {
        "motion_resource_count": 5198,
        "smcd_resource_count": 4559,
        "mmcd_resource_count": 639,
        "standalone_and_embedded_root_count": 6068,
        "standard_three_region_root_count": 5897,
        "alternate_four_region_root_count": 171,
    }
    if any(summary.get(key) != value for key, value in expected.items()):
        raise MoCapError("NFL motion inventory summary anchor differs")
    resources = report.get("resources", [])
    if len(resources) != 5198:
        raise MoCapError("NFL motion inventory resource list differs")
    matches = [
        {
            "apf_name": item["name"],
            "nfl_kind": item["kind"],
            "nfl_outer_index": item["outer_index"],
            "nfl_chunk_index": item["chunk_index"],
            "nfl_stored_size": item["stored_size"],
            "nfl_decoded_length": item["decoded_length"],
            "nfl_root_count": item["root_count"],
        }
        for item in resources if item.get("name") in apf_names
    ]
    matches.sort(key=lambda item: (item["apf_name"], item["nfl_outer_index"], item["nfl_chunk_index"]))
    matched_names = sorted({item["apf_name"] for item in matches})
    expected_names = ["es213bk", "es263bl", "es264bl", "es267bl", "es268bl", "es269bl", "es270bl"]
    if matched_names != expected_names or len(matches) != 7:
        raise MoCapError(f"APF/NFL exact-name intersection differs: {matched_names}")
    return {
        "path": str(path),
        "sha256": digest,
        "schema": report["schema"],
        "summary_anchor": expected,
        "proved_layout": report["proved_layout"],
        "executable_evidence": report["executable_evidence"],
        "exact_apf_name_match_count": len(matched_names),
        "exact_nfl_resource_match_count": len(matches),
        "matches": matches,
        "interpretation": (
            "exact names plus related one-based relative-pointer roots prove lineage; "
            "they do not prove byte-compatible packed motion codecs"
        ),
    }


def build_report(
    index_path: Path,
    scene_source: dict[str, object],
    nfl_lineage: dict[str, object],
    resources: list[dict[str, object]],
    events: list[dict[str, object]],
    samples: list[dict[str, object]],
    bone_maps: list[dict[str, object]],
    bone_rows: list[dict[str, object]],
    driver_rows: list[dict[str, object]],
    source_rows: list[dict[str, object]],
    mocap_bodies: list[bytes],
    bone_bodies: list[bytes],
) -> dict[str, object]:
    clips = [item for item in resources if item["kind"] == "full_clip"]
    aliases = [item for item in resources if item["kind"] == "compact_mirror_alias"]
    by_name = {item["name"]: item for item in resources}
    mirror_pairs = []
    for item in resources:
        if not item["mirror_flag"]:
            continue
        name = str(item["name"])
        if not name.endswith("_mirror") or name[:-7] not in by_name:
            raise MoCapError(f"mirror clip {name!r} has no exact base")
        mirror_pairs.append(
            {
                "base_name": name[:-7],
                "mirror_name": name,
                "mirror_kind": item["kind"],
            }
        )
    if len(mirror_pairs) != 30:
        raise MoCapError("mirror pair count differs")

    flag_counts = Counter(str(item["flags"]) for item in resources)
    event_id_counts = Counter(int(item["event_id"]) for item in events)
    optional_count = sum(
        any(pointer["field_offset"] == 0x2C and pointer["target"] is not None
            for pointer in item["pointers"])
        for item in clips
    )
    opaque_tail_lengths = [
        next(region["length"] for region in item["regions"] if region["role"] == "alignment_tail")
        for item in clips
    ]
    nonzero_tail_count = sum(bool(item["alignment_tail_hex"].strip("0")) for item in clips)
    main_bytes = sum(
        next(region["length"] for region in item["regions"] if region["role"] == "packed_motion")
        for item in clips
    )
    optional_bytes = sum(
        sum(region["length"] for region in item["regions"] if region["role"] == "optional_packed_motion")
        for item in clips
    )
    unresolved_drivers = sorted({
        row["driver_hash"] for row in driver_rows if row["driver_name"] is None
    })
    if len(unresolved_drivers) != 5:
        raise MoCapError("unresolved BoneScaleMap driver hash count differs")
    first_driver_table = [
        (row["driver_hash"], row["component_0"], row["component_1"],
         row["component_2"], row["component_3"])
        for row in driver_rows if row["map_name"] == "lores"
    ]
    second_driver_table = [
        (row["driver_hash"], row["component_0"], row["component_1"],
         row["component_2"], row["component_3"])
        for row in driver_rows if row["map_name"] == "hires"
    ]
    if first_driver_table != second_driver_table or len(first_driver_table) != 19:
        raise MoCapError("lores/hires BoneScaleMap driver tables differ")

    return {
        "schema": "apf_mocap_inventory/v1",
        "source_index": str(index_path),
        "sources": source_rows,
        "scene_inventory_source": scene_source,
        "pointer_rule": "target = field_offset + signed_be32(stored_value) - 1; zero means null",
        "proved_layout": {
            "serialized_root_size": MOCAP_ROOT_SIZE,
            "fixed_pointer_fields": list(MOCAP_POINTER_FIELDS),
            "variable_pointer_count_field": "(flags >> 17) & 0x1f; zero in all 68 shipped resources",
            "sample_rate_field": "(flags >> 9) & 0xff",
            "mirror_flag": "flags & 0x40",
            "root_vector_sample": {
                "pointer_field": 0x24,
                "count_field": 0x04,
                "record_stride": ROOT_SAMPLE_STRIDE,
                "record_encoding": "three signed big-endian int16 components, each multiplied by 0.125",
                "sample_time": "sample_index / (sample_rate * time_scale)",
                "interpolation": "linear in sampler 0x84638720",
                "component_meanings": "unproved; intentionally numbered 0..2",
            },
            "event_stream": {
                "pointer_field": 0x28,
                "terminator": hex32(EVENT_SENTINEL),
                "event_id": "raw_word & 0xff",
                "event_time": "(raw_word >> 8) / 65536 / time_scale",
            },
            "compact_alias": {
                "name": "hand_pose_mirror",
                "target_name": "hand_pose",
                "target_crc32_at_0x20": "0xfe2226ba",
                "xex_alias_record": "0x82005ee8: [SingleMoCap type, alias CRC32, target CRC32]",
            },
        },
        "summary": {
            "resource_count": len(resources),
            "full_clip_count": len(clips),
            "compact_alias_count": len(aliases),
            "unique_name_count": len({item["name"] for item in resources}),
            "unique_body_sha256_count": len({item["sha256"] for item in resources}),
            "decoded_body_bytes": sum(item["length"] for item in resources),
            "corpus_sha256": sha256(b"".join(mocap_bodies)),
            "mirror_flag_count": len(mirror_pairs),
            "mirror_pair_count": len(mirror_pairs),
            "optional_packed_region_count": optional_count,
            "packed_motion_bytes": main_bytes,
            "optional_packed_motion_bytes": optional_bytes,
            "root_sample_count": len(samples),
            "event_count": len(events),
            "clips_with_events": sum(item["event_count"] > 0 for item in clips),
            "event_id_counts": {str(key): value for key, value in sorted(event_id_counts.items())},
            "flags_counts": dict(sorted(flag_counts.items())),
            "sample_rate_counts": dict(sorted(Counter(str(item["sample_rate_hz"]) for item in clips).items())),
            "body_length": distribution(int(item["length"]) for item in resources),
            "duration": distribution(float(item["duration"]) for item in clips),
            "alignment_tail_length": distribution(opaque_tail_lengths),
            "alignment_tail_bytes": sum(opaque_tail_lengths),
            "nonzero_alignment_tail_count": nonzero_tail_count,
            "all_full_clip_regions_reconstruct": True,
            "all_event_streams_uniquely_terminated": True,
            "all_root_samples_bounded": True,
        },
        "bone_scale_map": {
            "type_crc32": "0x1bbfab40",
            "summary": {
                "resource_count": len(bone_maps),
                "bone_record_count": len(bone_rows),
                "scale_slot_count_per_map": 19,
                "scale_slot_record_count": len(driver_rows),
                "driver_tables_identical": True,
                "distinct_driver_hash_count": len({row["driver_hash"] for row in driver_rows}),
                "resolved_driver_hash_count": len({
                    row["driver_hash"] for row in driver_rows if row["driver_name"] is not None
                }),
                "resolved_bone_name_count": sum(item["resolved_bone_name_count"] for item in bone_maps),
                "resolved_driver_record_count": sum(row["driver_name"] is not None for row in driver_rows),
                "unresolved_driver_record_count": sum(row["driver_name"] is None for row in driver_rows),
                "distinct_unresolved_driver_hash_count": len(unresolved_drivers),
                "unresolved_driver_hashes": unresolved_drivers,
                "corpus_bytes": sum(len(body) for body in bone_bodies),
                "corpus_sha256": sha256(b"".join(bone_bodies)),
                "all_regions_reconstruct": True,
            },
            "root_layout": {
                "serialized_root_size": 0x1C,
                "bone_count_offset": 0x04,
                "bone_hash_pointer_offset": 0x08,
                "bone_to_scale_slot_pointer_offset": 0x0C,
                "scale_slot_count_offset": 0x10,
                "driver_hash_pointer_offset": 0x14,
                "vector_pointer_offset": 0x18,
                "vector_record": "four big-endian floats; component meanings remain unproved",
            },
            "binding_evidence": (
                "all 52 lores and 92 hires bone CRCs resolve uniquely to exact SCNE node/hierarchy names"
            ),
            "resources": bone_maps,
        },
        "cross_title_nfl2k5": nfl_lineage,
        "executable_evidence": {
            "single_mocap_type_crc32": "0x60900d71",
            "typed_lookup_constant": "0x82000c44",
            "runtime_registry_node": "0x84d11080",
            "load_relocator": "0x84636ce8",
            "inverse_relocator": "0x84636de8",
            "aggregate_load_body": "0x8463b010 (true pdata function starts at 0x8463b008)",
            "aggregate_inverse_body": "0x8463b098 (true pdata function starts at 0x8463b090)",
            "root_vector_sampler": "0x84638720",
            "mirrored_sample_wrapper": "0x84639260",
            "root_delta_wrapper": "0x846392c8",
            "event_consumers": ["0x846389a8", "0x84638c18", "0x84638cc8", "0x84638d68"],
            "typed_lookup_playback_caller": "0x84a619e8",
            "crowd_binding": (
                "0x84975e60 looks up SingleMoCap crowd_anm (CRC32 0x78ff0af5) and FSMR crowdren1"
            ),
            "bone_scale_descriptor": "0x82003854",
            "bone_scale_load_callback": "0x846597c0",
            "bone_scale_inverse_callback": "0x84659810",
            "bone_scale_pointer_helpers": ["0x846596b0", "0x84659638"],
            "negative_binding_evidence": {
                "CDAN": "distinct type 0xa7701f00 and distinct two-pointer callback 0x84979058",
                "MRKS": "distinct type 0xc6ed33a2; no direct binding to inline SingleMoCap events proved",
            },
        },
        "mirror_pairs": sorted(mirror_pairs, key=lambda item: item["mirror_name"]),
        "resources": resources,
        "worked": [
            "decoded and exactly hashed all 68 SingleMoCap bodies from three anchored IFF sources",
            "proved bounded reconstruction of every full root, opaque packed region, event stream, root-vector stream, and alignment tail",
            "decoded 6,782 executable-proved root-vector samples and 34 terminated events without naming unproved components",
            "resolved the compact hand_pose_mirror alias through its CRC and XEX alias record",
            "resolved every BoneScaleMap bone CRC to an exact SCNE hierarchy name and preserved all opaque bytes",
            "cross-referenced seven exact APF/NFL motion names against the complete NFL SMCD/MMCD inventory",
        ],
        "failed": [
            "the main and optional packed motion regions still lack proved per-bone channels, bit widths, quantization, timing, and interpolation",
            "five distinct BoneScaleMap driver CRCs do not resolve to names in the parsed SCNE corpus",
            "CDAN and MRKS remain separate resource types; no direct binding chain to SingleMoCap was proved",
            "no glTF skeletal animation or writer is emitted because bone-track binding, capacity, and serialization are unproved",
        ],
        "portme": [
            "// PORTME: recover packed SingleMoCap bone-channel IDs, element widths, value scales, and interpolation",
            "// PORTME: validate decoded poses against the exact lores/hires SCNE skeleton names before glTF export",
            "// PORTME: identify the five unresolved BoneScaleMap driver CRCs from runtime consumers or missing skeleton metadata",
            "// PORTME: determine whether CDAN or MRKS participates in any higher-level animation binding without conflating their formats",
            "// PORTME: implement writing only after fixed-slot capacities, H7A recompression, IFF tables, and outer archive integrity are proved",
        ],
    }


def write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})


def write_outputs(
    args: argparse.Namespace,
    report: dict[str, object],
    resources: list[dict[str, object]],
    events: list[dict[str, object]],
    samples: list[dict[str, object]],
    bone_rows: list[dict[str, object]],
    driver_rows: list[dict[str, object]],
    mocap_bodies: list[bytes],
    bone_bodies: list[bytes],
) -> None:
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    mocap_rows = []
    for item in resources:
        pointer_targets = {entry["field_offset"]: entry["target"] for entry in item["pointers"]}
        region_lengths = {entry["role"]: entry["length"] for entry in item["regions"]}
        mocap_rows.append(
            {
                **item,
                "pointer_20": pointer_targets.get(0x20),
                "pointer_24": pointer_targets.get(0x24),
                "pointer_28": pointer_targets.get(0x28),
                "pointer_2c": pointer_targets.get(0x2C),
                "packed_motion_length": region_lengths.get("packed_motion", 0),
                "optional_packed_motion_length": region_lengths.get("optional_packed_motion", 0),
                "event_stream_length": region_lengths.get("event_stream", 0),
                "alignment_tail_length": region_lengths.get("alignment_tail", 0),
            }
        )
    write_tsv(
        args.mocap_tsv,
        [
            "outer_table_index", "outer_name", "inner_index", "name", "name_crc32", "kind",
            "corpus_offset", "part_offset", "length", "sha256", "flags", "mirror_flag",
            "sample_rate_hz", "sample_count", "duration", "pointer_20", "pointer_24",
            "pointer_28", "pointer_2c", "packed_motion_length", "optional_packed_motion_length",
            "event_count", "event_stream_length", "root_sample_bytes", "alignment_tail_length",
            "alignment_tail_hex", "alias_target_name", "alias_target_crc32",
        ],
        mocap_rows,
    )
    write_tsv(
        args.event_tsv,
        ["outer_table_index", "inner_index", "name", "event_index", "raw_word",
         "event_id", "time_fixed_high24", "time"],
        events,
    )
    write_tsv(
        args.sample_tsv,
        ["outer_table_index", "inner_index", "name", "sample_index", "time",
         "raw_component_0", "raw_component_1", "raw_component_2",
         "component_0", "component_1", "component_2"],
        samples,
    )
    write_tsv(
        args.bone_tsv,
        ["map_name", "bone_index", "bone_hash", "bone_name", "scene_occurrence_count",
         "scale_slot", "driver_hash", "driver_name", "component_0", "component_1",
         "component_2", "component_3"],
        bone_rows,
    )
    write_tsv(
        args.driver_tsv,
        ["map_name", "slot", "driver_hash", "driver_name", "scene_occurrence_count",
         "component_0", "component_1", "component_2", "component_3"],
        driver_rows,
    )
    args.mocap_bin.parent.mkdir(parents=True, exist_ok=True)
    args.mocap_bin.write_bytes(b"".join(mocap_bodies))
    args.bone_bin.parent.mkdir(parents=True, exist_ok=True)
    args.bone_bin.write_bytes(b"".join(bone_bodies))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="APF 2K8 0A archive index")
    parser.add_argument("--scene-inventory", type=Path, required=True)
    parser.add_argument("--nfl-motion-inventory", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--mocap-tsv", type=Path, required=True)
    parser.add_argument("--event-tsv", type=Path, required=True)
    parser.add_argument("--sample-tsv", type=Path, required=True)
    parser.add_argument("--bone-tsv", type=Path, required=True)
    parser.add_argument("--driver-tsv", type=Path, required=True)
    parser.add_argument("--mocap-bin", type=Path, required=True)
    parser.add_argument("--bone-bin", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        scene_names, scene_source = load_scene_names(args.scene_inventory)
        (
            resources, events, samples, bone_maps, bone_rows, driver_rows,
            mocap_bodies, bone_bodies, source_rows,
        ) = load_apf(args.index, scene_names)
        nfl_lineage = load_nfl_lineage(
            args.nfl_motion_inventory, {str(item["name"]) for item in resources}
        )
        report = build_report(
            args.index, scene_source, nfl_lineage, resources, events, samples,
            bone_maps, bone_rows, driver_rows, source_rows, mocap_bodies,
            bone_bodies,
        )
        write_outputs(
            args, report, resources, events, samples, bone_rows, driver_rows,
            mocap_bodies, bone_bodies,
        )
    except (
        MoCapError, apf_inner.FormatError, apf_outer.FormatError,
        OSError, KeyError, TypeError, ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        "APF_MOCAP_INVENTORY_COMPLETE "
        f"resources={summary['resource_count']} samples={summary['root_sample_count']} "
        f"events={summary['event_count']} bones={len(bone_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
