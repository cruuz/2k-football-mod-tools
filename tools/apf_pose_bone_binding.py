#!/usr/bin/env python3
"""Build the exact partial APF 2K8 packed-pose/bone-binding inventory.

The executable proves how a 3-byte logical sampler map feeds 16-byte pose
records and how a 2-byte signed map expands those records into matrices. A
nearby static block contains one 25-record sampler-shaped map, one
matrix-map-shaped byte extent, three exact copies of 15 left/right finger
hash pairs, and player_lo/player hashes. The runtime config that would bind
the body rows to named SCNE bones is still built dynamically.

This tool records exact byte contracts and exact hash/name joins without
assigning plausible body names to unproved logical or matrix rows.

// PORTME at 0x847C1470/0x847C14A4: recover the runtime builder that installs
//         config +0x24 and +0x28, then prove its skeleton row order.
// PORTME at 0x820FC584: prove whether the final 00 00 is matrix row 21 or
//         two-byte alignment before the float table at 0x820FC588.
// PORTME at 0x8463A4F0 and 0x8463A52C: recover sampler modes 2 and 1.
// PORTME at 0x820FC628: identify the consumer before calling the finger hash
//         table a SingleMoCap channel-to-bone binding.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any, Iterable
import zlib


SCHEMA = "apf_pose_bone_binding/v1"
EXPECTED_XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"
EXPECTED_LANGUAGE = "PowerPC:BE:64:A2ALT-32addr"
EXPECTED_PACKED_POSE_SHA256 = (
    "6eba188581d32a565fa5b9757fb0865ef20677eef7fdbe0ab8a1d21d2e8b15b7"
)
EXPECTED_SCENE_SHA256 = (
    "93269dbc2fbace97890af389cd97a35e5291fec39bdfd1ed411639550e4dac36"
)
EXPECTED_BONE_SCALE_TSV_SHA256 = (
    "9eaf7ec474660426dc4f8690b0e3d8fdd18be4ac4c85883462a1314ee2bc613c"
)

MAP3_ADDRESS = 0x820FC510
MAP2_ADDRESS = 0x820FC55C
FLOAT_TABLE_ADDRESS = 0x820FC588
FINGER_TABLE_ADDRESS = 0x820FC628
SKELETON_HASH_ADDRESS = 0x820FC6A0
MAP3_GETTER = 0x84AA4190
MAP2_GETTER = 0x84AA41A0
FLOAT_GETTER = 0x84AA41B0

EXPECTED_MAP3 = [
    (0, 0, 0),
    (0, 1, 4),
    (0, 2, 5),
    (0, 3, 6),
    (0, 4, 1),
    (0, 5, 2),
    (0, 6, 3),
    (0, 7, 7),
    (0, 8, 13),
    (0, 9, 14),
    (0, 10, 15),
    (0, 11, 16),
    (0, 12, 12),
    (0, 13, 8),
    (0, 14, 9),
    (0, 15, 10),
    (0, 16, 11),
    (1, 17, 18),
    (1, 18, 17),
    (1, 19, 19),
    (1, 20, 22),
    (1, 21, 21),
    (1, 22, 20),
    (2, 23, 24),
    (2, 24, 23),
]

# Exact 44-byte extent between pointer-returning getters. Rows 0..20 obey the
# independently proved rotation/translation grammar. Final 00 00 may be a
# 22nd record or two bytes of float-table alignment.
EXPECTED_MAP2_BYTES = [
    (0, -1),
    (-1, -1),
    (1, 17),
    (2, -1),
    (3, -1),
    (-1, -1),
    (4, 18),
    (5, -1),
    (6, -1),
    (7, 19),
    (8, -1),
    (-1, -1),
    (9, 20),
    (10, -1),
    (11, -1),
    (12, 21),
    (13, -1),
    (-1, -1),
    (14, 22),
    (15, -1),
    (16, -1),
    (0, 0),
]

LEFT_FINGER_INDICES = tuple(range(14, 29))
RIGHT_FINGER_INDICES = tuple(range(34, 49))
FINGER_TABLE_COPIES = (0x820D2638, 0x820FC628, 0x820FE600)

RAW_ANCHORS = {
    # Matrix expansion: fallback, signed pair loads, logical indexing, map
    # stride, and output stride.
    0x846394D4: 0x2B060000,
    0x846394E8: 0x38CB0B90,
    0x84639520: 0x89460000,
    0x8463952C: 0x7D4A0774,
    0x84639548: 0x554A2036,
    0x84639550: 0x894B0000,
    0x8463955C: 0x7D4A0774,
    0x84639570: 0x554A2036,
    0x84639574: 0x38C60002,
    0x846395F0: 0x38630040,
    0x84639614: 0x4E800020,
    # Concrete sampler -> callback -> matrix-expansion caller.
    0x847C1460: 0x814B0008,
    0x847C1464: 0x812B0004,
    0x847C1468: 0x810B000C,
    0x847C1470: 0x80CB0024,
    0x847C1478: 0x4BE78EA9,
    0x847C1480: 0x816B0044,
    0x847C14A4: 0x80CB0028,
    0x847C14A8: 0x80AB001C,
    0x847C14AC: 0x4BE78025,
    # Static table getters.
    0x84AA4190: 0x3D608210,
    0x84AA4194: 0x386BC510,
    0x84AA4198: 0x4E800020,
    0x84AA41A0: 0x3D608210,
    0x84AA41A4: 0x386BC55C,
    0x84AA41A8: 0x4E800020,
    0x84AA41B0: 0x3D608210,
    0x84AA41B4: 0x386BC588,
    0x84AA41B8: 0x4E800020,
    # Static-map consumer: reject negative byte0, sign extend, multiply by 16.
    0x8487770C: 0x4822CA95,
    0x8487771C: 0x7D6B18AE,
    0x84877720: 0x2B0B0080,
    0x84877740: 0x57EA083C,
    0x84877744: 0x7D4A18AE,
    0x84877748: 0x7D4A0774,
    0x8487774C: 0x554A2036,
    # Second static-map consumer and later config-driven matrix call.
    0x84925BDC: 0x4817E5C5,
    0x84925CF0: 0x89710012,
    0x84925CF4: 0x7D6B0774,
    0x84925CF8: 0x556B2036,
    0x84926068: 0x80CB0028,
    0x8492606C: 0x80AB001C,
    0x84926070: 0x808B0040,
    0x84926074: 0x4BD1345D,
}

RAW_SPANS = (
    ("matrix_expansion", 0x846394D0, 0x84639618),
    ("sampler_matrix_caller_a", 0x847C1438, 0x847C14E0),
    ("sampler_matrix_caller_b", 0x847C9428, 0x847C94BC),
    ("static_matrix_row_lookup", 0x84877698, 0x84877838),
    ("static_map_matrix_consumer", 0x849259F0, 0x84926140),
    ("static_table_getter_region", 0x84AA4140, 0x84AA41E0),
)


class BindingError(ValueError):
    """An exact executable or corpus invariant did not hold."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def hex32(value: int) -> str:
    return f"0x{value:08X}"


def crc32_name(value: str) -> int:
    return zlib.crc32(value.encode("ascii")) & 0xFFFFFFFF


def put_unique(mapping: dict[int, int], address: int, value: int, label: str) -> None:
    old = mapping.get(address)
    if old is not None and old != value:
        raise BindingError(
            f"{label} {hex32(address)} changed within one trace: "
            f"{hex32(old)} != {hex32(value)}"
        )
    mapping[address] = value


def parse_trace(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if f"Program MD5: {EXPECTED_XEX_MD5}" not in text:
        raise BindingError("focused trace has the wrong APF XEX MD5")
    if f"Program language: {EXPECTED_LANGUAGE}" not in text:
        raise BindingError("focused trace has the wrong processor language")

    default_map: list[tuple[int, int]] = []
    map3: list[tuple[int, int, int]] = []
    map2: list[tuple[int, int]] = []
    finger_pairs: list[tuple[int, int]] = []
    raw_words: dict[int, int] = {}
    binding_words: dict[int, int] = {}
    bone_hits: dict[int, list[int]] = {}
    current_bone_hash: int | None = None
    static_config_count: int | None = None
    binding_pointer_count: int | None = None
    skeleton_hashes: tuple[int, int] | None = None
    getter_lines: list[str] = []
    map2_extent_line: str | None = None

    for line in text.splitlines():
        if match := re.fullmatch(r"MATRIX_MAP (\d+) (-?\d+) (-?\d+)", line):
            index, first, second = map(int, match.groups())
            if index != len(default_map):
                raise BindingError("default matrix map indices are not contiguous")
            default_map.append((first, second))
        elif match := re.fullmatch(r"STATIC_MAP3 (\d+) (\d+) (-?\d+) (-?\d+)", line):
            index, mode, normal, mirrored = map(int, match.groups())
            if index != len(map3):
                raise BindingError("static map3 indices are not contiguous")
            map3.append((mode, normal, mirrored))
        elif match := re.fullmatch(r"STATIC_MAP2_BYTES (\d+) (-?\d+) (-?\d+)", line):
            index, rotation, translation = map(int, match.groups())
            if index != len(map2):
                raise BindingError("static map2 byte indices are not contiguous")
            map2.append((rotation, translation))
        elif match := re.fullmatch(
            r"STATIC_FINGER_PAIR (\d+) (0x[0-9A-F]{8}) (0x[0-9A-F]{8})", line
        ):
            index = int(match.group(1))
            if index != len(finger_pairs):
                raise BindingError("static finger-pair indices are not contiguous")
            finger_pairs.append((int(match.group(2), 16), int(match.group(3), 16)))
        elif match := re.fullmatch(
            r"STATIC_SKELETON_HASH player_lo=(0x[0-9A-F]{8}) "
            r"player=(0x[0-9A-F]{8})",
            line,
        ):
            skeleton_hashes = (int(match.group(1), 16), int(match.group(2), 16))
        elif match := re.fullmatch(
            r"RAW32 (0x[0-9A-F]{8}) (0x[0-9A-F]{8})", line
        ):
            put_unique(
                raw_words, int(match.group(1), 16), int(match.group(2), 16), "RAW32"
            )
        elif match := re.fullmatch(
            r"BINDING_WORD (0x[0-9A-F]{8}) (0x[0-9A-F]{8})", line
        ):
            put_unique(
                binding_words,
                int(match.group(1), 16),
                int(match.group(2), 16),
                "BINDING_WORD",
            )
        elif match := re.fullmatch(
            r"BONE_HASH lores_index=\d+ hash=(0x[0-9A-F]{8}) hits=(\d+)", line
        ):
            current_bone_hash = int(match.group(1), 16)
            bone_hits[current_bone_hash] = []
        elif match := re.match(r"BONE_HASH_HIT (0x[0-9A-F]{8}) ", line):
            if current_bone_hash is None:
                raise BindingError("BONE_HASH_HIT appeared without BONE_HASH")
            bone_hits[current_bone_hash].append(int(match.group(1), 16))
        elif match := re.fullmatch(r"STATIC_CONFIG_COUNT (\d+)", line):
            static_config_count = int(match.group(1))
        elif match := re.fullmatch(r"BINDING_POINTER_COUNT (\d+)", line):
            binding_pointer_count = int(match.group(1))
        elif line.startswith("STATIC_GETTER "):
            getter_lines.append(line)
        elif line.startswith("STATIC_MAP2_EXTENT "):
            map2_extent_line = line

    if default_map != [(index, -1) for index in range(32)]:
        raise BindingError("default matrix map at 0x82000B90 changed")
    if map3 != EXPECTED_MAP3:
        raise BindingError("static 25-record map3 bytes changed")
    if map2 != EXPECTED_MAP2_BYTES:
        raise BindingError("static map2 byte extent changed")
    if len(finger_pairs) != 15:
        raise BindingError(f"expected 15 static finger pairs, got {len(finger_pairs)}")
    if skeleton_hashes != (crc32_name("player_lo"), crc32_name("player")):
        raise BindingError("static player_lo/player hashes changed")
    if static_config_count != 0:
        raise BindingError(
            f"initialized non-executable scan found {static_config_count} static configs"
        )
    if binding_pointer_count != 0:
        raise BindingError(
            f"aligned image scan found {binding_pointer_count} direct block pointers"
        )
    if map2_extent_line != (
        "STATIC_MAP2_EXTENT 0x820FC55C 0x820FC588 bytes=44 "
        "record21_status=record_or_alignment_unproved"
    ):
        raise BindingError("static map2 extent marker changed")
    expected_getters = {
        "STATIC_GETTER 0x84AA4190 target=0x820FC510 refs=",
        (
            "STATIC_GETTER 0x84AA41A0 target=0x820FC55C refs="
            "0x8487770C(none,UNCONDITIONAL_CALL);"
            "0x84925BDC(none,UNCONDITIONAL_CALL)"
        ),
        "STATIC_GETTER 0x84AA41B0 target=0x820FC588 refs=",
    }
    if set(getter_lines) != expected_getters:
        raise BindingError(f"static getter evidence changed: {getter_lines!r}")

    for address, expected in RAW_ANCHORS.items():
        actual = raw_words.get(address)
        if actual != expected:
            raise BindingError(
                f"instruction anchor {hex32(address)}: expected {hex32(expected)}, "
                f"got {None if actual is None else hex32(actual)}"
            )

    for address in range(0x820FC500, 0x820FC700, 4):
        if address not in binding_words:
            raise BindingError(f"static block dump lacks {hex32(address)}")
    binding_blob = b"".join(
        struct.pack(">I", binding_words[address])
        for address in range(0x820FC500, 0x820FC700, 4)
    )
    map3_start = MAP3_ADDRESS - 0x820FC500
    map2_start = MAP2_ADDRESS - 0x820FC500
    float_start = FLOAT_TABLE_ADDRESS - 0x820FC500
    expected_map3_bytes = b"".join(
        struct.pack("Bbb", *item) for item in EXPECTED_MAP3
    )
    if binding_blob[map3_start : map3_start + len(expected_map3_bytes)] != expected_map3_bytes:
        raise BindingError("map3 bytes do not reconstruct at 0x820FC510")
    expected_map2_bytes = b"".join(
        struct.pack("bb", *item) for item in EXPECTED_MAP2_BYTES
    )
    if binding_blob[map2_start:float_start] != expected_map2_bytes:
        raise BindingError("map2 byte extent does not reconstruct at 0x820FC55C")

    return {
        "text": text,
        "default_map": default_map,
        "map3": map3,
        "map2": map2,
        "finger_pairs": finger_pairs,
        "skeleton_hashes": skeleton_hashes,
        "raw_words": raw_words,
        "binding_words": binding_words,
        "binding_blob": binding_blob,
        "bone_hits": bone_hits,
        "static_config_count": static_config_count,
        "binding_pointer_count": binding_pointer_count,
    }


def read_bone_scale_rows(path: Path) -> dict[str, list[dict[str, Any]]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, dialect="excel-tab"))
    result: dict[str, list[dict[str, Any]]] = {}
    for label, expected_count in (("lores", 52), ("hires", 92)):
        selected = [row for row in rows if row["map_name"] == label]
        selected.sort(key=lambda row: int(row["bone_index"]))
        if [int(row["bone_index"]) for row in selected] != list(range(expected_count)):
            raise BindingError(f"{label} BoneScaleMap indices changed")
        parsed = [
            {
                "map_name": label,
                "bone_index": int(row["bone_index"]),
                "bone_hash": int(row["bone_hash"], 16),
                "bone_name": row["bone_name"],
                "scene_occurrence_count": int(row["scene_occurrence_count"]),
            }
            for row in selected
        ]
        if any(crc32_name(item["bone_name"]) != item["bone_hash"] for item in parsed):
            raise BindingError(f"{label} BoneScaleMap contains a hash/name mismatch")
        result[label] = parsed
    if sum(len(value) for value in result.values()) != len(rows):
        raise BindingError("BoneScaleMap TSV contains unexpected map families")
    return result


def select_scene_hierarchy(
    inventory: dict[str, Any],
    *,
    root_name: str,
    inner_file_index: int,
    node_name: str,
    count: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    matches: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for scene in inventory["scenes"]:
        if (
            scene["outer_table_index"] != 1310
            or scene["inner_file_index"] != inner_file_index
            or scene["root_name"] != root_name
        ):
            continue
        for node in scene["nodes"]:
            hierarchy = node.get("hierarchy")
            if (
                node["name"] == node_name
                and hierarchy is not None
                and hierarchy["count"] == count
            ):
                matches.append((scene, node, hierarchy))
    if len(matches) != 1:
        raise BindingError(
            f"expected one outer 1310 inner {inner_file_index} "
            f"{root_name}/{node_name} hierarchy, got {len(matches)}"
        )
    return matches[0]


def build_scene_joins(
    bone_rows: dict[str, list[dict[str, Any]]],
    inventory: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    families: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    selections = (
        ("lores", "player_lo", 204, "player", 52),
        ("hires", "player", 273, "player", 92),
    )
    for map_name, root_name, inner, node_name, count in selections:
        scene, node, hierarchy = select_scene_hierarchy(
            inventory,
            root_name=root_name,
            inner_file_index=inner,
            node_name=node_name,
            count=count,
        )
        records = hierarchy["records"]
        by_name = {record["name"]: record for record in records}
        if len(by_name) != count:
            raise BindingError(f"{root_name} hierarchy names are not unique")
        if {row["bone_name"] for row in bone_rows[map_name]} != set(by_name):
            raise BindingError(
                f"{map_name} BoneScaleMap names do not exactly cover {root_name}"
            )

        same_position_count = 0
        for row in bone_rows[map_name]:
            scene_record = by_name[row["bone_name"]]
            scene_hash = int(scene_record["name_crc32"], 16)
            if scene_hash != row["bone_hash"]:
                raise BindingError(
                    f"{map_name} {row['bone_name']}: scene/BoneScale hash mismatch"
                )
            same_position = int(scene_record["index"]) == row["bone_index"]
            same_position_count += int(same_position)
            joins.append(
                {
                    "map_name": map_name,
                    "bone_scale_index": row["bone_index"],
                    "bone_hash": row["bone_hash"],
                    "bone_name": row["bone_name"],
                    "scene_hierarchy_index": int(scene_record["index"]),
                    "scene_parent_index": int(scene_record["parent"]),
                    "same_position": same_position,
                    "scene_occurrence_count": row["scene_occurrence_count"],
                }
            )
        families.append(
            {
                "map_name": map_name,
                "bone_count": count,
                "outer_table_index": scene["outer_table_index"],
                "inner_file_index": scene["inner_file_index"],
                "inner_name": scene["inner_name"],
                "root_name": scene["root_name"],
                "node_name": node["name"],
                "hierarchy_offset": hierarchy["offset"],
                "hierarchy_record_offset": hierarchy["record_offset"],
                "hierarchy_record_size": 48,
                "exact_name_hash_join_count": count,
                "same_position_count": same_position_count,
                "order_identical": same_position_count == count,
            }
        )
    return families, joins


def validate_finger_tables(
    trace: dict[str, Any],
    joins: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lores_by_index = {
        item["scene_hierarchy_index"]: item
        for item in joins
        if item["map_name"] == "lores"
    }
    hires_by_name = {
        item["bone_name"]: item for item in joins if item["map_name"] == "hires"
    }
    result: list[dict[str, Any]] = []
    for pair_index, (left_index, right_index) in enumerate(
        zip(LEFT_FINGER_INDICES, RIGHT_FINGER_INDICES)
    ):
        left = lores_by_index[left_index]
        right = lores_by_index[right_index]
        expected_hashes = (left["bone_hash"], right["bone_hash"])
        if trace["finger_pairs"][pair_index] != expected_hashes:
            raise BindingError(
                f"static finger pair {pair_index} does not match player_lo names"
            )
        word_positions = (pair_index * 2, pair_index * 2 + 1)
        for hash_value, word_position in zip(expected_hashes, word_positions):
            expected_hits = sorted(
                address + word_position * 4 for address in FINGER_TABLE_COPIES
            )
            actual_hits = sorted(trace["bone_hits"].get(hash_value, []))
            if actual_hits != expected_hits:
                raise BindingError(
                    f"{hex32(hash_value)} table copies changed: "
                    f"{[hex32(value) for value in actual_hits]}"
                )
        result.append(
            {
                "pair_index": pair_index,
                "left_hash": left["bone_hash"],
                "left_name": left["bone_name"],
                "left_lores_index": left_index,
                "left_hires_index": hires_by_name[left["bone_name"]][
                    "scene_hierarchy_index"
                ],
                "right_hash": right["bone_hash"],
                "right_name": right["bone_name"],
                "right_lores_index": right_index,
                "right_hires_index": hires_by_name[right["bone_name"]][
                    "scene_hierarchy_index"
                ],
                "binding_status": (
                    "exact_hash_to_scene_name; pose-channel consumer_unproved"
                ),
            }
        )
    return result


def raw_span_report(raw_words: dict[int, int]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, start, end in RAW_SPANS:
        missing = [
            address for address in range(start, end, 4) if address not in raw_words
        ]
        if missing:
            raise BindingError(
                f"{name} raw span lacks {len(missing)} words, first {hex32(missing[0])}"
            )
        body = b"".join(
            struct.pack(">I", raw_words[address]) for address in range(start, end, 4)
        )
        result.append(
            {
                "name": name,
                "start": hex32(start),
                "end_exclusive": hex32(end),
                "size": len(body),
                "sha256": sha256(body),
            }
        )
    return result


def logical_rows(map3: Iterable[tuple[int, int, int]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, (mode, normal, mirrored) in enumerate(map3):
        if normal != index:
            raise BindingError("static map3 normal indices are not identity ordered")
        result.append(
            {
                "logical_channel": index,
                "mode": mode,
                "normal_packed_index": normal,
                "mirrored_packed_index": mirrored,
                "mirror_partner_logical_channel": mirrored,
                "mode_semantics": (
                    "proved_mode0_quaternion"
                    if mode == 0
                    else f"mode{mode}_unresolved"
                ),
                "bone_name": None,
                "named_binding_status": (
                    "unresolved: no runtime config-to-SCNE row identity"
                ),
            }
        )
    for row in result:
        partner = row["mirror_partner_logical_channel"]
        if result[partner]["mirror_partner_logical_channel"] != row["logical_channel"]:
            raise BindingError("static map3 mirrored indices are not an involution")
    return result


def matrix_rows(
    map2: Iterable[tuple[int, int]],
    logical: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, (rotation, translation) in enumerate(map2):
        rotation_mode = None if rotation < 0 else logical[rotation]["mode"]
        translation_mode = None if translation < 0 else logical[translation]["mode"]
        if index < 21:
            if rotation >= 0 and rotation_mode != 0:
                raise BindingError(f"matrix row {index} rotation is not mode 0")
            if translation >= 0 and translation_mode != 1:
                raise BindingError(f"matrix row {index} translation is not mode 1")
            grammar = "proved_rotation_mode0_translation_mode1_or_absent"
            extent_status = "semantic_pair"
        else:
            grammar = "incompatible_with_translation_mode1_grammar"
            extent_status = "record_or_two_byte_alignment_unproved"
        result.append(
            {
                "matrix_row": index,
                "rotation_logical_index": None if rotation < 0 else rotation,
                "translation_logical_index": None if translation < 0 else translation,
                "rotation_mode": rotation_mode,
                "translation_mode": translation_mode,
                "grammar_status": grammar,
                "extent_status": extent_status,
                "bone_name": None,
                "named_binding_status": (
                    "unresolved: matrix row-to-SCNE hierarchy identity unproved"
                ),
            }
        )
    return result


def validate_pseudo(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = (
        "/* 0x847C1438:",
        "(*(uint *)(iVar1 + 8) | *(uint *)(iVar1 + 4)) & ~*(uint *)(iVar1 + 0xc)",
        "*(undefined4 *)(iVar1 + 0x24),auStack_220",
        "*(int *)(param_1 + 0x18) + 0x44",
        "*(int *)(param_1 + 0x18) + 0x1c",
        "*(int *)(param_1 + 0x18) + 0x28",
        "/* 0x847C9428:",
        "return 0xffffffff820fc510;",
        "return 0xffffffff820fc55c;",
        "return 0xffffffff820fc588;",
    )
    for marker in required:
        if marker not in text:
            raise BindingError(f"focused pseudo-C lacks {marker!r}")


def build_report(
    *,
    trace_path: Path,
    pseudo_path: Path,
    packed_pose_path: Path,
    bone_scale_path: Path,
    scene_path: Path,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if file_sha256(packed_pose_path) != EXPECTED_PACKED_POSE_SHA256:
        raise BindingError("upstream packed-pose report hash changed")
    if file_sha256(scene_path) != EXPECTED_SCENE_SHA256:
        raise BindingError("upstream APF scene inventory hash changed")
    if file_sha256(bone_scale_path) != EXPECTED_BONE_SCALE_TSV_SHA256:
        raise BindingError("upstream BoneScaleMap TSV hash changed")

    packed_pose = json.loads(packed_pose_path.read_text(encoding="utf-8"))
    if packed_pose["schema"] != "apf_packed_pose_decoder/v1":
        raise BindingError("upstream packed-pose schema changed")
    if packed_pose["proved_frame_and_output_mapping"]["map_record"] != (
        "three bytes [mode, normal_signed_index, mirrored_signed_index]"
    ):
        raise BindingError("upstream sampler map contract changed")
    trace = parse_trace(trace_path)
    validate_pseudo(pseudo_path)
    bone_rows = read_bone_scale_rows(bone_scale_path)
    scene_inventory = json.loads(scene_path.read_text(encoding="utf-8"))
    if scene_inventory["schema"] != "apf_scene_inventory/v1":
        raise BindingError("upstream scene inventory schema changed")
    skeleton_families, joins = build_scene_joins(bone_rows, scene_inventory)
    fingers = validate_finger_tables(trace, joins)
    logical = logical_rows(trace["map3"])
    matrices = matrix_rows(trace["map2"], logical)

    map3_bytes = b"".join(struct.pack("Bbb", *item) for item in trace["map3"])
    map2_bytes = b"".join(struct.pack("bb", *item) for item in trace["map2"])
    finger_bytes = b"".join(
        struct.pack(">II", left, right) for left, right in trace["finger_pairs"]
    )
    skeleton_bytes = struct.pack(">II", *trace["skeleton_hashes"])

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "inputs": {
            "trace": {"path": str(trace_path), "sha256": file_sha256(trace_path)},
            "focused_pseudo_c": {
                "path": str(pseudo_path),
                "sha256": file_sha256(pseudo_path),
            },
            "packed_pose_decoder": {
                "path": str(packed_pose_path),
                "sha256": EXPECTED_PACKED_POSE_SHA256,
            },
            "bone_scale_map_tsv": {
                "path": str(bone_scale_path),
                "sha256": EXPECTED_BONE_SCALE_TSV_SHA256,
            },
            "scene_inventory": {
                "path": str(scene_path),
                "sha256": EXPECTED_SCENE_SHA256,
            },
        },
        "summary": {
            "logical_map_record_count": len(logical),
            "logical_named_body_binding_count": 0,
            "matrix_byte_pair_count": len(matrices),
            "matrix_semantic_pair_count": 21,
            "matrix_ambiguous_trailing_pair_count": 1,
            "matrix_named_body_binding_count": 0,
            "exact_named_finger_pair_count": len(fingers),
            "exact_named_finger_bone_count": len(fingers) * 2,
            "static_finger_table_copy_count": len(FINGER_TABLE_COPIES),
            "bone_scale_scene_join_count": len(joins),
            "lores_exact_order_join_count": skeleton_families[0][
                "same_position_count"
            ],
            "hires_exact_name_hash_join_count": skeleton_families[1][
                "exact_name_hash_join_count"
            ],
            "hires_same_position_count": skeleton_families[1][
                "same_position_count"
            ],
            "initialized_static_config_candidate_count": trace[
                "static_config_count"
            ],
            "aligned_direct_binding_pointer_word_count": trace[
                "binding_pointer_count"
            ],
        },
        "sampler_to_matrix_contract": {
            "concrete_callers": [hex32(0x847C1438), hex32(0x847C9428)],
            "config_pointer": "object +0x18",
            "active_logical_mask": (
                "(config[+0x08] | config[+0x04]) & ~config[+0x0C]"
            ),
            "sampler": hex32(0x8463A320),
            "sampler_map": (
                "config +0x24; records are [mode, normal signed packed index, "
                "mirrored signed packed index]"
            ),
            "logical_pose_record_size": 16,
            "optional_pose_callback": "config +0x44",
            "matrix_expander": hex32(0x846394D0),
            "matrix_count": "config +0x1C",
            "matrix_map": "config +0x28",
            "matrix_map_record": (
                "[signed rotation logical index, signed translation logical index]"
            ),
            "matrix_map_record_size": 2,
            "matrix_output_stride": 64,
            "negative_one_semantics": (
                "select identity/default instead of indexing a logical pose record"
            ),
            "default_matrix_map": {
                "address": hex32(0x82000B90),
                "record_count": 32,
                "records": [list(item) for item in trace["default_map"]],
                "interpretation": "[i,-1] for i=0..31",
            },
            "stack_pose_buffer_bytes": 520,
        },
        "static_pose_block": {
            "classification": (
                "exact internally typed byte block; runtime config installation "
                "and body row-to-name identity remain unproved"
            ),
            "range_dumped": {
                "start": hex32(0x820FC500),
                "end_exclusive": hex32(0x820FC700),
                "size": len(trace["binding_blob"]),
                "sha256": sha256(trace["binding_blob"]),
            },
            "prefix_type_hashes": [
                {
                    "address": hex32(0x820FC500),
                    "value": hex32(crc32_name("BoneScaleMap")),
                    "name": "BoneScaleMap",
                },
                {
                    "address": hex32(0x820FC504),
                    "value": hex32(crc32_name("CurveAnim")),
                    "name": "CurveAnim",
                },
            ],
            "unresolved_prefix_words": [
                {
                    "address": hex32(0x820FC508),
                    "value": hex32(trace["binding_words"][0x820FC508]),
                },
                {
                    "address": hex32(0x820FC50C),
                    "value": hex32(trace["binding_words"][0x820FC50C]),
                },
            ],
            "map3": {
                "address": hex32(MAP3_ADDRESS),
                "getter": hex32(MAP3_GETTER),
                "size": len(map3_bytes),
                "sha256": sha256(map3_bytes),
                "record_count": len(logical),
                "record_size": 3,
                "grammar": (
                    "[mode, normal signed packed index, mirrored signed packed index]"
                ),
                "consumption_status": (
                    "sampler grammar exact; no direct call/reference from the "
                    "runtime config path to this getter was recovered"
                ),
            },
            "map2_byte_extent": {
                "address": hex32(MAP2_ADDRESS),
                "next_getter_target": hex32(FLOAT_TABLE_ADDRESS),
                "getter": hex32(MAP2_GETTER),
                "size": len(map2_bytes),
                "sha256": sha256(map2_bytes),
                "byte_pair_count": len(matrices),
                "proved_semantic_pair_count": 21,
                "trailing_pair_status": (
                    "00 00 at 0x820FC584: record 21 or two-byte alignment unproved"
                ),
                "direct_callers": [hex32(0x8487770C), hex32(0x84925BDC)],
            },
            "next_float_table": {
                "address": hex32(FLOAT_TABLE_ADDRESS),
                "getter": hex32(FLOAT_GETTER),
            },
            "finger_table": {
                "primary_address": hex32(FINGER_TABLE_ADDRESS),
                "size": len(finger_bytes),
                "sha256": sha256(finger_bytes),
                "pair_count": len(fingers),
                "exact_copy_addresses": [
                    hex32(address) for address in FINGER_TABLE_COPIES
                ],
                "consumer_status": (
                    "no direct pointer/reference to the three table starts was "
                    "recovered; adjacency is not a pose-channel binding"
                ),
            },
            "skeleton_name_hashes": {
                "address": hex32(SKELETON_HASH_ADDRESS),
                "size": len(skeleton_bytes),
                "sha256": sha256(skeleton_bytes),
                "entries": [
                    {
                        "name": "player_lo",
                        "hash": hex32(trace["skeleton_hashes"][0]),
                    },
                    {
                        "name": "player",
                        "hash": hex32(trace["skeleton_hashes"][1]),
                    },
                ],
                "association_status": (
                    "exact names immediately follow the finger table; consumer "
                    "link to sampler/map rows remains unproved"
                ),
            },
            "static_config_scan": {
                "scope": "initialized non-executable memory in the loaded XEX",
                "candidate_count": trace["static_config_count"],
                "interpretation": (
                    "caller configs appear dynamically built; absence is limited "
                    "to this initialized static scan"
                ),
            },
            "direct_pointer_word_scan": {
                "scope": (
                    "aligned initialized words pointing into the focused static "
                    "binding ranges"
                ),
                "count": trace["binding_pointer_count"],
                "note": (
                    "table getters synthesize addresses with lis/addi, so zero "
                    "pointer words does not mean zero code references"
                ),
            },
        },
        "logical_channels": logical,
        "matrix_rows": matrices,
        "finger_pairs": fingers,
        "skeleton_families": skeleton_families,
        "bone_scale_scene_joins": joins,
        "executable_evidence": {
            "xex_md5": EXPECTED_XEX_MD5,
            "language": EXPECTED_LANGUAGE,
            "instruction_anchors": [
                {"address": hex32(address), "raw": hex32(raw)}
                for address, raw in sorted(RAW_ANCHORS.items())
            ],
            "raw_spans": raw_span_report(trace["raw_words"]),
            "static_map_lookup": (
                "0x8487770C calls the 0x820FC55C getter; "
                "0x8487771C/0x84877720 reject a negative first byte; "
                "0x84877744..0x8487774C sign-extend it and multiply by 16 "
                "to index config +0x40"
            ),
            "static_map_matrix_join": (
                "0x84925CF0 reads byte +0x12 (row 9 rotation index) from "
                "the same getter result; 0x84926068..0x84926074 later call "
                "0x846394D0 with config +0x28/+0x1C/+0x40"
            ),
        },
        "worked": [
            "proved the signed two-byte matrix-map contract and every caller config offset",
            "recovered an exact 25-record sampler-shaped static map and mirror involution",
            "validated 21 matrix byte pairs against mode-0 rotation/mode-1 translation roles",
            "joined 30 alternating finger hashes to exact player_lo/player names at three copies",
            "joined all 52 lores and 92 hires BoneScaleMap names/hashes to SCNE records",
        ],
        "failed": [
            "no static config links 0x820FC510/0x820FC55C to caller config +0x24/+0x28",
            "no exact body logical-channel or matrix-row to SCNE bone-name identity was recovered",
            "final 00 00 before 0x820FC588 is not distinguished from pair 21 versus alignment",
            "no direct consumer of the three 30-word finger-table starts was recovered",
            "sampler modes 1 and 2 remain semantically unresolved",
        ],
        "portme": [
            "// PORTME at 0x847C1470/0x847C14A4: recover the runtime builder of config +0x24/+0x28 and prove its SCNE row order.",
            "// PORTME at 0x820FC584: prove whether 00 00 is matrix row 21 or alignment before the 0x820FC588 float table.",
            "// PORTME at 0x8463A4F0 and 0x8463A52C: recover sampler modes 2 and 1 before naming their channels.",
            "// PORTME at 0x820FC628: recover a consumer of the finger hash array before assigning it to SingleMoCap channels.",
            "// PORTME at 0x846394D0: prove axes, handedness, matrix convention, and bind/inverse-bind roles before glTF animation export.",
        ],
    }
    return report, logical, matrices, fingers, joins


def write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            dialect="excel-tab",
            extrasaction="ignore",
        )
        writer.writeheader()
        for source in rows:
            row = dict(source)
            for key, value in row.items():
                if value is None:
                    row[key] = ""
                elif isinstance(value, bool):
                    row[key] = "1" if value else "0"
                elif key.endswith("_hash") and isinstance(value, int):
                    row[key] = hex32(value)
            writer.writerow(row)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path(
            "reports/assets/apf_pose_bone_binding_ghidra/"
            "pose_bone_binding_trace.txt"
        ),
    )
    parser.add_argument(
        "--pseudo",
        type=Path,
        default=Path(
            "reports/assets/apf_pose_bone_binding_ghidra/"
            "pose_bone_binding_focused_pseudo_c.c"
        ),
    )
    parser.add_argument(
        "--packed-pose",
        type=Path,
        default=Path("reports/assets/apf_packed_pose_decoder_inventory.json"),
    )
    parser.add_argument(
        "--bone-scale-map",
        type=Path,
        default=Path("reports/assets/apf_bone_scale_map.tsv"),
    )
    parser.add_argument(
        "--scene-inventory",
        type=Path,
        default=Path("reports/assets/apf_scene_inventory.json"),
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=Path("reports/assets/apf_pose_bone_binding_inventory.json"),
    )
    parser.add_argument(
        "--logical-tsv",
        type=Path,
        default=Path("reports/assets/apf_pose_bone_binding_logical.tsv"),
    )
    parser.add_argument(
        "--matrix-tsv",
        type=Path,
        default=Path("reports/assets/apf_pose_bone_binding_matrix.tsv"),
    )
    parser.add_argument(
        "--finger-tsv",
        type=Path,
        default=Path("reports/assets/apf_pose_bone_finger_pairs.tsv"),
    )
    parser.add_argument(
        "--scene-join-tsv",
        type=Path,
        default=Path("reports/assets/apf_pose_bone_scene_join.tsv"),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        report, logical, matrices, fingers, joins = build_report(
            trace_path=args.trace,
            pseudo_path=args.pseudo,
            packed_pose_path=args.packed_pose,
            bone_scale_path=args.bone_scale_map,
            scene_path=args.scene_inventory,
        )
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_tsv(
            args.logical_tsv,
            [
                "logical_channel",
                "mode",
                "normal_packed_index",
                "mirrored_packed_index",
                "mirror_partner_logical_channel",
                "mode_semantics",
                "bone_name",
                "named_binding_status",
            ],
            logical,
        )
        write_tsv(
            args.matrix_tsv,
            [
                "matrix_row",
                "rotation_logical_index",
                "translation_logical_index",
                "rotation_mode",
                "translation_mode",
                "grammar_status",
                "extent_status",
                "bone_name",
                "named_binding_status",
            ],
            matrices,
        )
        write_tsv(
            args.finger_tsv,
            [
                "pair_index",
                "left_hash",
                "left_name",
                "left_lores_index",
                "left_hires_index",
                "right_hash",
                "right_name",
                "right_lores_index",
                "right_hires_index",
                "binding_status",
            ],
            fingers,
        )
        write_tsv(
            args.scene_join_tsv,
            [
                "map_name",
                "bone_scale_index",
                "bone_hash",
                "bone_name",
                "scene_hierarchy_index",
                "scene_parent_index",
                "same_position",
                "scene_occurrence_count",
            ],
            joins,
        )
    except (BindingError, KeyError, OSError, json.JSONDecodeError) as error:
        print(f"apf_pose_bone_binding: {error}", file=sys.stderr)
        return 1
    print(
        "APF_POSE_BONE_BINDING_COMPLETE "
        f"logical={len(logical)} matrix_pairs={len(matrices)} "
        f"finger_pairs={len(fingers)} scene_joins={len(joins)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
