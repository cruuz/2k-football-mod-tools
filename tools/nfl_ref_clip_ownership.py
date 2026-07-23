#!/usr/bin/env python3
"""Prove one NFL 2K5 referee penalty clip's archive and runtime ownership.

This joins the fixed-slot SMCD body, the executable's 26-row left/right
penalty selector, the literal ``Referee`` resource namespace, the gameplay
controller path, and the independently recovered referee skeletal family.

It deliberately does not claim that the gameplay clip is stored in a
cutscene type-4 descriptor instance.  Type 4 is retained as a proved,
compatible referee skeletal ABI and the missing instance-level edge is an
explicit PORTME.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable

import nfl_outer


TARGET_NAME = "ANM_REF_PENALTY_DELAY_OF_GAME_R"
TARGET_OUTER_INDEX = 3107
TARGET_OUTER_ID = 0xDA37AA9D
TARGET_CHUNK_INDEX = 27
TARGET_SELECTOR_INDEX = 4
TARGET_SELECTOR_SIDE = "right"
SLOT_SIZE = 0x2C00
SLOT_COUNT = 36
WRAPPER = struct.Struct("<4s7I")
SELECTOR_BASE = 0x00513F28
SELECTOR_COUNT = 26
SELECTOR_STRIDE = 12
SELECTOR_END = SELECTOR_BASE + SELECTOR_COUNT * SELECTOR_STRIDE
ACTION_DESCRIPTOR = 0x00514060
NAMESPACE_VA = 0x00E887B0
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"


class OwnershipError(ValueError):
    """Raised when an ownership witness differs from its proved contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, schema: str) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != schema:
        raise OwnershipError(f"{path}: expected schema {schema!r}")
    return document


class XbeView:
    def __init__(self, xbe_path: Path, header_path: Path) -> None:
        self.path = xbe_path
        self.data = xbe_path.read_bytes()
        self.header = json.loads(header_path.read_text(encoding="utf-8"))
        actual = hashlib.md5(self.data).hexdigest()
        if actual != EXPECTED_XBE_MD5:
            raise OwnershipError(f"unexpected XBE MD5 {actual}")

    def file_offset(self, va: int, size: int = 1) -> int:
        for section in self.header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                return int(section["raw_address"]) + va - start
        raise OwnershipError(f"VA 0x{va:08x}+0x{size:x} is not file-backed")

    def at(self, va: int, size: int) -> bytes:
        offset = self.file_offset(va, size)
        result = self.data[offset : offset + size]
        if len(result) != size:
            raise OwnershipError(f"short XBE read at 0x{va:08x}")
        return result

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.at(va, 4))[0]

    def utf16z(self, va: int) -> str:
        offset = self.file_offset(va, 2)
        units = bytearray()
        for _ in range(512):
            unit = self.data[offset : offset + 2]
            if len(unit) != 2:
                break
            offset += 2
            if unit == b"\0\0":
                return units.decode("utf-16le")
            units.extend(unit)
        raise OwnershipError(f"unterminated UTF-16LE string at 0x{va:08x}")


def parse_sampler_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def parse_target_body(body: bytes) -> dict[str, object]:
    if len(body) < 0x94 or body[:12] != bytes(12) or body[12:16] != b"SMCD":
        raise OwnershipError("target body does not have the strict SMCD common prefix")
    name_stored, root_stored = struct.unpack_from("<II", body, 0x10)
    name_offset = 0x10 + name_stored - 1
    root_offset = 0x14 + root_stored - 1
    cursor = name_offset
    units = bytearray()
    while cursor + 2 <= len(body):
        unit = body[cursor : cursor + 2]
        cursor += 2
        if unit == b"\0\0":
            break
        units.extend(unit)
    else:
        raise OwnershipError("target SMCD name is unterminated")
    name = units.decode("utf-16le")
    words = struct.unpack_from("<13I", body, root_offset)
    word00, flags, runtime_mask, word0c = words[:4]
    duration = struct.unpack_from("<f", body, root_offset + 0x14)[0]
    return {
        "name": name,
        "name_offset": name_offset,
        "root_offset": root_offset,
        "packed_quaternion_dwords_per_frame": word00 & 0xFF,
        "opaque_header_byte_01": (word00 >> 8) & 0xFF,
        "frame_count": word00 >> 16,
        "flags": flags,
        "runtime_mask_word08": runtime_mask,
        "sample_rate_hz": word0c & 0xFF,
        "header_byte_0d": (word0c >> 8) & 0xFF,
        "header_byte_0e": (word0c >> 16) & 0xFF,
        "header_byte_0f": (word0c >> 24) & 0xFF,
        "duration_seconds": duration,
        "duration_raw": f"0x{words[5]:08x}",
        "root_header_words": [f"0x{word:08x}" for word in words],
    }


def single_resource_by_name(
    resources_by_name: dict[str, list[dict[str, object]]], name: str
) -> dict[str, object]:
    matches = resources_by_name.get(name, [])
    if len(matches) != 1:
        raise OwnershipError(f"{name!r}: expected one SMCD resource, found {len(matches)}")
    return matches[0]


def selector_rows(
    xbe: XbeView, resources_by_name: dict[str, list[dict[str, object]]]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for index in range(SELECTOR_COUNT):
        row_va = SELECTOR_BASE + index * SELECTOR_STRIDE
        left_pointer, right_pointer, opaque = struct.unpack("<III", xbe.at(row_va, 12))
        row: dict[str, object] = {
            "selector_index": index,
            "row_va": f"0x{row_va:08x}",
            "row_file_offset": xbe.file_offset(row_va, 12),
            "left_pointer_field_va": f"0x{row_va:08x}",
            "right_pointer_field_va": f"0x{row_va + 4:08x}",
            "opaque_word": f"0x{opaque:08x}",
        }
        for side, pointer in (("left", left_pointer), ("right", right_pointer)):
            row[f"{side}_name_string_va"] = "" if pointer == 0 else f"0x{pointer:08x}"
            row[f"{side}_name"] = ""
            row[f"{side}_match_count"] = 0
            row[f"{side}_outer_index"] = ""
            row[f"{side}_chunk_index"] = ""
            row[f"{side}_slot_offset"] = ""
            row[f"{side}_decoded_sha256"] = ""
            if pointer == 0:
                continue
            name = xbe.utf16z(pointer)
            resource = single_resource_by_name(resources_by_name, name)
            row[f"{side}_name"] = name
            row[f"{side}_match_count"] = 1
            row[f"{side}_outer_index"] = int(resource["outer_index"])
            row[f"{side}_chunk_index"] = int(resource["chunk_index"])
            row[f"{side}_slot_offset"] = int(resource["chunk_offset"])
            row[f"{side}_decoded_sha256"] = str(resource["decoded_sha256"])
        result.append(row)
    return result


def source_pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": file_sha256(path)}


def build_path_rows() -> list[dict[str, object]]:
    return [
        {
            "step": 1,
            "source": "outer3107/slot27",
            "target": "0x00e87fb8",
            "instruction_va": "0x00513f5c",
            "evidence": "selector row 4 right pointer equals target UTF-16 name VA",
            "meaning": "the unique archived SMCD name is an executable-selected penalty clip",
            "confidence": "exact_static_pointer_and_unique_corpus_join",
        },
        {
            "step": 2,
            "source": "0x001fb250",
            "target": "0x001fb1a0",
            "instruction_va": "0x001fb3bc",
            "evidence": "gameplay actor state callback calls penalty motion setup",
            "meaning": "the selector is reached by gameplay actor state",
            "confidence": "instruction_exact",
        },
        {
            "step": 3,
            "source": "0x001fb1a0",
            "target": "0x002407d0",
            "instruction_va": "0x001fb200",
            "evidence": "single-actor penalty setup calls selector using record +0x08",
            "meaning": "selector index reaches the 12-byte penalty table",
            "confidence": "instruction_exact",
        },
        {
            "step": 4,
            "source": "0x00513f28",
            "target": "0x00e887b0",
            "instruction_va": "0x0024083c/0x0024085b",
            "evidence": "index*12 table address followed by ECX = UTF-16 Referee",
            "meaning": "selected motion name is looked up in the Referee namespace",
            "confidence": "instruction_exact",
        },
        {
            "step": 5,
            "source": "0x002407d0",
            "target": "0x001685b0",
            "instruction_va": "0x00240866",
            "evidence": "prefetch helper embeds little-endian FourCC SMCD",
            "meaning": "the referee name is resolved as an SMCD motion resource",
            "confidence": "instruction_exact",
        },
        {
            "step": 6,
            "source": "0x001fb0b0",
            "target": "0x001685e0",
            "instruction_va": "0x001fb142 -> 0x00240764",
            "evidence": "deferred action calls acquire helper with Referee namespace/name",
            "meaning": "the prefetched SMCD root is acquired for playback",
            "confidence": "instruction_exact",
        },
        {
            "step": 7,
            "source": "0x002406e0",
            "target": "0x002d6b70",
            "instruction_va": "0x0024073c",
            "evidence": "play setup passes acquired root from global root array",
            "meaning": "the selected referee SMCD enters the motion controller",
            "confidence": "instruction_exact",
        },
        {
            "step": 8,
            "source": "0x002d6b70",
            "target": "0x0031c180",
            "instruction_va": "0x002d6c13",
            "evidence": "controller handoff calls recovered motion transition routine",
            "meaning": "the root becomes the active/scheduled controller motion",
            "confidence": "instruction_exact",
        },
        {
            "step": 9,
            "source": "0x00e60274",
            "target": "0x0051d010/0x00096a80",
            "instruction_va": "0x00217eb2/0x00217ef6/0x00217f04",
            "evidence": "seven-record pool initializer installs shared map and referee callback",
            "meaning": "the seven-entry gameplay pool is the exact referee skeletal family",
            "confidence": "instruction_exact_family_not_clip_instance",
        },
        {
            "step": 10,
            "source": "cutscene descriptor type 4",
            "target": "0x0051d010/0x00096a80/0x00096b20",
            "instruction_va": "0x0012f828/0x0012f872/0x0012f9ba",
            "evidence": "type-4 switch path uses the same referee map, twist callback, and hierarchy apply",
            "meaning": "type 4 is a compatible referee skeletal ABI, not a proved instance owner of this gameplay clip",
            "confidence": "instruction_exact_abi_relation_instance_unproved",
        },
    ]


def build_report(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    motion = load_json(args.motion_inventory, "nfl2k5_motion_inventory/v1")
    pose = load_json(args.pose_report, "nfl2k5_pose_matrix_apply/v2")
    pools = load_json(args.pool_report, "nfl2k5_motion_object_pools/v1")
    bone = load_json(args.bone_report, "nfl2k5_bone_binding/v1")
    sampler_document = load_json(args.sampler_report, "nfl2k5_motion_sampler_inventory/v1")
    del pose, pools, bone, sampler_document

    resources = [item for item in motion["resources"] if item["kind"] == "SMCD"]
    resources_by_name: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in resources:
        resources_by_name[str(item["name"])].append(item)
    target = single_resource_by_name(resources_by_name, TARGET_NAME)
    expected_identity = (
        int(target["outer_index"]), int(str(target["outer_id"]), 16),
        int(target["chunk_index"]), int(target["chunk_offset"]),
    )
    if expected_identity != (
        TARGET_OUTER_INDEX, TARGET_OUTER_ID, TARGET_CHUNK_INDEX,
        TARGET_CHUNK_INDEX * SLOT_SIZE,
    ):
        raise OwnershipError(f"target archive identity differs: {expected_identity}")

    bank = sorted(
        (item for item in resources if int(item["outer_index"]) == TARGET_OUTER_INDEX),
        key=lambda item: int(item["chunk_index"]),
    )
    if len(bank) != SLOT_COUNT or [int(item["chunk_index"]) for item in bank] != list(range(SLOT_COUNT)):
        raise OwnershipError("outer 3107 is not a dense 36-slot SMCD bank")
    for item in bank:
        if int(item["chunk_offset"]) != int(item["chunk_index"]) * SLOT_SIZE:
            raise OwnershipError("outer 3107 chunk offsets are not fixed 0x2c00 slots")

    archive = nfl_outer.parse_archive(args.index)
    entry = archive.entries[TARGET_OUTER_INDEX]
    if entry.name_id != TARGET_OUTER_ID or entry.size != SLOT_COUNT * SLOT_SIZE:
        raise OwnershipError("outer 3107 ID/size differs from fixed-slot contract")
    slot_tail_padding_bytes = 0
    target_slot_tail_padding = -1
    for item in bank:
        offset = int(item["chunk_offset"])
        slot_wrapper = nfl_outer.read_entry_range(archive, entry, offset, WRAPPER.size)
        fields = WRAPPER.unpack(slot_wrapper)
        slot_stored = int(item["stored_size"])
        if not (
            fields[0] == b"SMCD" and fields[1] == fields[2] == slot_stored
            and all(word == 0 for word in fields[3:])
        ):
            raise OwnershipError(f"outer 3107 slot {item['chunk_index']} wrapper differs")
        slot_body = nfl_outer.read_entry_range(
            archive, entry, offset + WRAPPER.size, slot_stored
        )
        if sha256(slot_body) != item["decoded_sha256"]:
            raise OwnershipError(f"outer 3107 slot {item['chunk_index']} body hash differs")
        tail_size = SLOT_SIZE - WRAPPER.size - slot_stored
        if tail_size < 0:
            raise OwnershipError(f"outer 3107 slot {item['chunk_index']} exceeds slot")
        tail = nfl_outer.read_entry_range(
            archive, entry, offset + WRAPPER.size + slot_stored, tail_size
        )
        if any(tail):
            raise OwnershipError(f"outer 3107 slot {item['chunk_index']} tail is nonzero")
        slot_tail_padding_bytes += tail_size
        if int(item["chunk_index"]) == TARGET_CHUNK_INDEX:
            target_slot_tail_padding = tail_size
    slot_offset = TARGET_CHUNK_INDEX * SLOT_SIZE
    wrapper_bytes = nfl_outer.read_entry_range(archive, entry, slot_offset, WRAPPER.size)
    kind, stored, decoded, word0c, word10, word14, reserved0, reserved1 = WRAPPER.unpack(wrapper_bytes)
    if not (
        kind == b"SMCD" and stored == decoded == int(target["stored_size"])
        and word0c == word10 == word14 == reserved0 == reserved1 == 0
    ):
        raise OwnershipError("target fixed-slot resource wrapper differs")
    body = nfl_outer.read_entry_range(archive, entry, slot_offset + WRAPPER.size, stored)
    if sha256(body) != target["decoded_sha256"]:
        raise OwnershipError("target body hash differs from canonical motion inventory")
    parsed_body = parse_target_body(body)
    if parsed_body["name"] != TARGET_NAME:
        raise OwnershipError("target body name differs")

    sampler_matches = [
        row for row in parse_sampler_rows(args.sampler_tsv)
        if row["name"] == TARGET_NAME and int(row["outer_index"]) == TARGET_OUTER_INDEX
        and int(row["chunk_index"]) == TARGET_CHUNK_INDEX
    ]
    if len(sampler_matches) != 1:
        raise OwnershipError(f"expected one target sampler row, found {len(sampler_matches)}")
    sampler = sampler_matches[0]
    exact_sampler = {
        "packed_quaternion_dwords_per_frame": int(sampler["packed_quaternion_dwords_per_frame"]),
        "frame_count": int(sampler["frame_count"]),
        "sample_rate_hz": int(sampler["sample_rate"]),
        "flags": int(sampler["flags"], 16),
        "duration_seconds": float(sampler["duration"]),
    }
    for key in ("packed_quaternion_dwords_per_frame", "frame_count", "sample_rate_hz", "flags"):
        if exact_sampler[key] != parsed_body[key]:
            raise OwnershipError(f"target sampler/body field {key} differs")
    if abs(exact_sampler["duration_seconds"] - float(parsed_body["duration_seconds"])) > 1e-8:
        raise OwnershipError("target sampler/body duration differs")

    xbe = XbeView(args.xbe, args.xbe_header)
    selectors = selector_rows(xbe, resources_by_name)
    selected_row = selectors[TARGET_SELECTOR_INDEX]
    if not (
        selected_row["right_name"] == TARGET_NAME
        and selected_row["right_pointer_field_va"] == "0x00513f5c"
        and selected_row["right_name_string_va"] == "0x00e87fb8"
        and int(selected_row["right_outer_index"]) == TARGET_OUTER_INDEX
        and int(selected_row["right_chunk_index"]) == TARGET_CHUNK_INDEX
    ):
        raise OwnershipError("selector row 4 right does not resolve uniquely to target")
    if SELECTOR_END != ACTION_DESCRIPTOR:
        raise OwnershipError("selector table is not immediately followed by action descriptor")
    if xbe.utf16z(NAMESPACE_VA) != "Referee":
        raise OwnershipError("runtime namespace string is not Referee")
    if (
        xbe.utf16z(0x00E65DD0) != "referee"
        or xbe.utf16z(0x00E65CBC) != "ref_low"
        or xbe.utf16z(0x00E65CCC) != "ref_high"
    ):
        raise OwnershipError("referee scene/shape strings differ")

    action_words = struct.unpack("<5I", xbe.at(ACTION_DESCRIPTOR, 20))
    if action_words != (0x20000000, 0, 0x00240670, 0x002405F0, 0x002FC250):
        raise OwnershipError("penalty action descriptor differs")
    channel_map = xbe.at(0x0051D010, 50)
    if sha256(channel_map) != "39a441532daab4cdbe4ff777641021bc179da9a5a69d43a94cdcb45fcc21e435":
        raise OwnershipError("referee/coach channel map differs")

    all_names = [
        str(row[f"{side}_name"])
        for row in selectors for side in ("left", "right")
        if row[f"{side}_name"]
    ]
    path_rows = build_path_rows()
    report = {
        "schema": "nfl2k5_ref_clip_ownership/v1",
        "source_index": str(args.index),
        "executable": {
            "path": str(args.xbe),
            "md5": EXPECTED_XBE_MD5,
        },
        "selected_clip": {
            "name": TARGET_NAME,
            "outer_index": TARGET_OUTER_INDEX,
            "outer_id": f"0x{TARGET_OUTER_ID:08x}",
            "chunk_index": TARGET_CHUNK_INDEX,
            "slot_index": TARGET_CHUNK_INDEX,
            "slot_offset": slot_offset,
            "slot_size": SLOT_SIZE,
            "wrapper_size": WRAPPER.size,
            "decoded_length": len(body),
            "decoded_sha256": sha256(body),
            **exact_sampler,
            "duration_raw": parsed_body["duration_raw"],
            "quaternion_bytes": int(sampler["quaternion_bytes"]),
            "trajectory_stride": int(sampler["trajectory_stride"]),
            "trajectory_bytes": int(sampler["trajectory_bytes"]),
            "event_count": int(sampler["event_count"]),
            "selector_index": TARGET_SELECTOR_INDEX,
            "selector_side": TARGET_SELECTOR_SIDE,
            "selector_row_va": "0x00513f58",
            "selector_name_pointer_va": "0x00513f5c",
            "selector_name_string_va": "0x00e87fb8",
            "exact_inventory_match_count": 1,
        },
        "fixed_slot_bank": {
            "outer_index": TARGET_OUTER_INDEX,
            "outer_id": f"0x{TARGET_OUTER_ID:08x}",
            "outer_size": entry.size,
            "slot_count": SLOT_COUNT,
            "slot_size": SLOT_SIZE,
            "all_slots_dense": True,
            "all_slot_offsets_equal_index_times_slot_size": True,
            "all_resources_kind": "SMCD",
            "all_wrapper_bodies_match_inventory": True,
            "all_slot_tail_padding_zero": True,
            "slot_tail_padding_bytes": slot_tail_padding_bytes,
            "target_slot_tail_padding_bytes": target_slot_tail_padding,
        },
        "selector_table": {
            "base_va": f"0x{SELECTOR_BASE:08x}",
            "end_exclusive_va": f"0x{SELECTOR_END:08x}",
            "row_count": SELECTOR_COUNT,
            "row_stride": SELECTOR_STRIDE,
            "left_pointer_offset": 0,
            "right_pointer_offset": 4,
            "opaque_pointer_offset": 8,
            "nonempty_name_pointer_count": len(all_names),
            "unique_name_count": len(set(all_names)),
            "reused_name_pointer_count": sum(count > 1 for count in Counter(all_names).values()),
            "all_nonempty_names_have_one_exact_smcd_match": True,
            "all_nonempty_names_resolve_to_outer_3107": all(
                int(row[f"{side}_outer_index"]) == TARGET_OUTER_INDEX
                for row in selectors for side in ("left", "right")
                if row[f"{side}_name"]
            ),
        },
        "runtime_ownership": {
            "namespace_name": "Referee",
            "namespace_string_va": f"0x{NAMESPACE_VA:08x}",
            "selector_table_base_va": f"0x{SELECTOR_BASE:08x}",
            "selector_function_va": "0x002407d0",
            "dual_selector_function_va": "0x002408a0",
            "smcd_fourcc_immediate": "0x44434d53",
            "prefetch_function_va": "0x001685b0",
            "acquire_function_va": "0x001685e0",
            "gameplay_actor_state_callback_va": "0x001fb250",
            "gameplay_selector_setup_va": "0x001fb1a0",
            "gameplay_deferred_action_va": "0x001fb0b0",
            "gameplay_play_setup_va": "0x002406e0",
            "action_descriptor_va": f"0x{ACTION_DESCRIPTOR:08x}",
            "action_descriptor_words": [f"0x{word:08x}" for word in action_words],
            "gameplay_actor_pool_head_va": "0x00e60274",
            "gameplay_actor_pool_max_count": 7,
            "gameplay_actor_initializer_va": "0x00217eb0",
            "referee_scene_loader_va": "0x00096600",
            "referee_scene_name": "referee",
            "referee_scene_name_va": "0x00e65dd0",
            "referee_shape_names": ["ref_low", "ref_high"],
            "referee_shape_name_vas": ["0x00e65cbc", "0x00e65ccc"],
            "channel_map_va": "0x0051d010",
            "channel_map_sha256": sha256(channel_map),
            "enabled_channel_count": 21,
            "twist_extract_function_va": "0x00096590",
            "twist_callback_va": "0x00096a80",
            "hierarchy_apply_va": "0x00096b20",
            "controller_apply_function_va": "0x002d6b70",
            "controller_transition_function_va": "0x0031c180",
            "confidence": "instruction_exact_referee_namespace_and_skeletal_family",
            "specific_pool_record_instance_link_proved": False,
        },
        "cutscene_type4_relation": {
            "descriptor_type": 4,
            "descriptor_constructor_va": "0x00130150",
            "descriptor_update_va": "0x0012f670",
            "channel_map_va": "0x0051d010",
            "twist_callback_va": "0x00096a80",
            "hierarchy_apply_va": "0x00096b20",
            "relation": "same_referee_skeletal_family_not_proved_same_descriptor_instance",
            "instance_level_link_proved": False,
            "confidence": "instruction_exact_abi_relation_instance_unproved",
            "portme": "// PORTME: no exact runtime edge proves this gameplay penalty clip enters a cutscene 0x28-byte type-4 descriptor instance; do not label the clip itself as a type-4 descriptor resource",
        },
        "ownership_claims": [
            {
                "claim": "archive body is the unique SMCD selected by row 4 right",
                "confidence": "exact",
                "evidence": "body/name hash + unique corpus join + XBE pointer at 0x00513f5c",
            },
            {
                "claim": "the selected name is prefetched and acquired in resource namespace Referee",
                "confidence": "instruction_exact",
                "evidence": "0x0024083c..0x00240866 and 0x00240759..0x00240764",
            },
            {
                "claim": "the acquired motion root reaches controller transition 0x0031c180",
                "confidence": "instruction_exact",
                "evidence": "0x001fb142 -> 0x00240750; 0x001fb14d -> 0x002406e0; 0x0024073c -> 0x002d6b70; 0x002d6c13 -> 0x0031c180",
            },
            {
                "claim": "map 0x0051d010 and callback 0x00096a80 are the referee skeletal family",
                "confidence": "instruction_exact_family",
                "evidence": "0x00096600 referee SCNE loader plus 0x00217ef6/0x00217f04 pool installation",
            },
            {
                "claim": "cutscene type 4 shares the same referee skeletal ABI",
                "confidence": "instruction_exact_abi_only",
                "evidence": "type-4 switch path 0x0012f828/0x0012f872/0x0012f9ba",
                "limitation": "no instance-level clip -> cutscene descriptor edge is proved",
            },
        ],
        "source_pins": {
            "motion_inventory": source_pin(args.motion_inventory),
            "sampler_report": source_pin(args.sampler_report),
            "sampler_tsv": source_pin(args.sampler_tsv),
            "pose_report": source_pin(args.pose_report),
            "pool_report": source_pin(args.pool_report),
            "bone_report": source_pin(args.bone_report),
            "xbe_header": source_pin(args.xbe_header),
        },
        "worked": [
            "re-read and hashed the exact fixed-slot wrapper/body from outer 3107 slot 27",
            "decoded all 26 executable selector rows and joined every nonempty name to one exact SMCD",
            "proved row 4 right selects the target and lookup namespace is the literal Referee",
            "preserved the gameplay acquire/play/controller instruction path",
            "joined the seven-entry pool and cutscene type 4 to the exact referee skeletal family",
        ],
        "failed": [
            "no exact instruction edge proves this clip occupies a cutscene type-4 descriptor instance",
            "no exact static edge chooses one particular record of the seven-entry referee pool for this clip",
        ],
        "portme": [
            "// PORTME: prove or reject an instance-level gameplay penalty clip -> cutscene type-4 descriptor edge",
            "// PORTME: recover the dynamic selector-index producer and penalty enum names for all 26 rows",
            "// PORTME: identify which of the seven runtime referee records receives row 4 in a concrete play",
        ],
    }
    return report, selectors, path_rows


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--motion-inventory", type=Path, required=True)
    parser.add_argument("--sampler-report", type=Path, required=True)
    parser.add_argument("--sampler-tsv", type=Path, required=True)
    parser.add_argument("--pose-report", type=Path, required=True)
    parser.add_argument("--pool-report", type=Path, required=True)
    parser.add_argument("--bone-report", type=Path, required=True)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--selectors-tsv", type=Path, required=True)
    parser.add_argument("--path-tsv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        report, selectors, path_rows = build_report(args)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        selector_fields = [
            "selector_index", "row_va", "row_file_offset",
            "left_pointer_field_va", "left_name_string_va", "left_name",
            "left_match_count", "left_outer_index", "left_chunk_index",
            "left_slot_offset", "left_decoded_sha256",
            "right_pointer_field_va", "right_name_string_va", "right_name",
            "right_match_count", "right_outer_index", "right_chunk_index",
            "right_slot_offset", "right_decoded_sha256", "opaque_word",
        ]
        write_tsv(args.selectors_tsv, selectors, selector_fields)
        write_tsv(
            args.path_tsv,
            path_rows,
            ["step", "source", "target", "instruction_va", "evidence", "meaning", "confidence"],
        )
    except (OwnershipError, nfl_outer.FormatError, OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_REF_CLIP_OWNERSHIP_COMPLETE "
        f"clip={TARGET_NAME} selector={TARGET_SELECTOR_INDEX}:{TARGET_SELECTOR_SIDE} "
        f"rows={SELECTOR_COUNT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
