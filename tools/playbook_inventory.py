#!/usr/bin/env python3
"""Strict cross-title inventory for Visual Concepts PLAY playbook resources.

NFL 2K5 contains 37 fixed-capacity little-endian team/reference playbooks.
APF 2K8 contains one big-endian master playbook in an IFF system part.  This
tool parses only relationships established by the complete corpora and the
NFL executable relocator/accessors: named categories, formations, plays, the
eleven assignment pointers per play, and their bounded eight-byte node pool.

Opaque record words are retained as raw bytes.  This inventory tool provides no
general writer because route-node opcodes, formation fields, and count-changing
capacity consumers are not recovered.  The product's separate bounded route
writer may copy an exact stock assignment descriptor and existing same-resource
chain pointer; it never edits or interprets a route node.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner
import apf_outer
from nfl_outer import parse_archive as parse_nfl_archive
from nfl_outer import read_entry_range
from nfl_scene_probe import ProbeError, ResourceRecord, decode_resource, parse_inventory


SCHEMA = "vc_cross_title_playbook_inventory/v1"
SLOT_COUNT = 11
ROUTE_NODE_SIZE = 8

# XBE-proven NFL layout.
NFL_BODY_SIZE = 0x13390
NFL_FORMATION_BASE = 0x0134
NFL_FORMATION_SIZE = 0x00B4
NFL_FORMATION_CAPACITY = 50
NFL_FORMATION_AUX_BASE = 0x245C
NFL_FORMATION_AUX_SIZE = 0x0050
NFL_PLAY_BASE = 0x33FC
NFL_PLAY_SIZE = 0x0060
NFL_PLAY_CAPACITY = 270
NFL_CATEGORY_BASE = 0x993C
NFL_CATEGORY_SIZE = 0x0010
NFL_CATEGORY_CAPACITY = 26
NFL_ROUTE_BASE = 0x9ADC
NFL_STRING_BASE = 0x10840

# Complete APF master corpus layout.  Counts and the same field-local pointer
# rule prove each table.  The evolved strides are also independently visible
# as uninterrupted name-pointer series spanning every declared record.
APF_BODY_SIZE = 0x2C750
APF_CATEGORY_BASE = 0x0044
APF_CATEGORY_SIZE = 0x0010
APF_FORMATION_BASE = 0x0244
APF_FORMATION_SIZE = 0x00B8
APF_PLAY_BASE = 0x80C4
APF_PLAY_SIZE = 0x0064
APF_ROUTE_BASE = 0x17AC4
APF_STRING_BASE = 0x22384
# The MASTER body ends with a fixed-capacity, MSB-first formation-to-play
# membership bitmap table.  Every active formation owns one 0x54-byte row:
# 586 play bits (74 bytes, with the final six padding bits zero) followed by a
# still-opaque ten-byte tail.  Thirteen unused rows and twelve final alignment
# bytes are zero in the complete retail corpus.
APF_FORMATION_MEMBERSHIP_BASE = 0x28D84
APF_FORMATION_MEMBERSHIP_SIZE = 0x0054
APF_FORMATION_MEMBERSHIP_CAPACITY = 176
APF_FORMATION_MEMBERSHIP_MASK_SIZE = 74
APF_FORMATION_MEMBERSHIP_TAIL_SIZE = 10
APF_FORMATION_MEMBERSHIP_FINAL_PADDING = 12
MAX_COUNT = 1_000_000


class PlaybookError(ValueError):
    """A declared playbook relationship is malformed or out of bounds."""


@dataclass(frozen=True)
class NameEntry:
    index: int
    offset: int
    end_offset: int
    text: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_range(data: bytes, offset: int, size: int, what: str) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise PlaybookError(
            f"{what}: range 0x{offset:x}+0x{size:x} exceeds 0x{len(data):x}"
        )
    return data[offset : offset + size]


def u32(data: bytes, offset: int, endian: str, what: str) -> int:
    checked_range(data, offset, 4, what)
    return struct.unpack_from(endian + "I", data, offset)[0]


def i32(data: bytes, offset: int, endian: str, what: str) -> int:
    checked_range(data, offset, 4, what)
    return struct.unpack_from(endian + "i", data, offset)[0]


def relative(data: bytes, field: int, endian: str, what: str) -> int:
    stored = i32(data, field, endian, what)
    target = field - 1 + stored
    if not 0 <= target < len(data):
        raise PlaybookError(
            f"{what}: relative {stored:+#x} at 0x{field:x} resolves to "
            f"0x{target:x}, outside 0x{len(data):x} bytes"
        )
    return target


def utf16z(data: bytes, offset: int, encoding: str, what: str) -> tuple[str, int]:
    if offset < 0 or offset + 2 > len(data) or offset & 1:
        raise PlaybookError(f"{what}: invalid UTF-16 offset 0x{offset:x}")
    cursor = offset
    while cursor + 2 <= len(data):
        if data[cursor : cursor + 2] == b"\0\0":
            try:
                return data[offset:cursor].decode(encoding), cursor + 2
            except UnicodeDecodeError as exc:
                raise PlaybookError(
                    f"{what}: invalid {encoding} at 0x{offset:x}"
                ) from exc
        cursor += 2
    raise PlaybookError(f"{what}: unterminated UTF-16 string at 0x{offset:x}")


def parse_name_pool(
    data: bytes,
    pool_offset: int,
    encoding: str,
    declared_targets: list[int],
    what: str,
) -> tuple[list[NameEntry], int]:
    if len(declared_targets) != len(set(declared_targets)):
        raise PlaybookError(f"{what}: two declared records share a name pointer")
    entries: list[NameEntry] = []
    cursor = pool_offset
    while cursor + 2 <= len(data) and data[cursor : cursor + 2] != b"\0\0":
        text, end = utf16z(data, cursor, encoding, f"{what} name pool")
        if not text:
            raise PlaybookError(f"{what}: empty declared name at 0x{cursor:x}")
        entries.append(NameEntry(len(entries), cursor, end, text))
        cursor = end
    starts = {entry.offset for entry in entries}
    if starts != set(declared_targets):
        raise PlaybookError(
            f"{what}: sequential pool has {len(starts)} starts but declared "
            f"records reference {len(set(declared_targets))}"
        )
    if len(entries) != len(declared_targets):
        raise PlaybookError(f"{what}: name pool count mismatch")
    return entries, cursor


def raw_metadata(data: bytes, offset: int, size: int) -> dict[str, object]:
    raw = checked_range(data, offset, size, "record")
    return {
        "raw_hex": raw.hex(),
        "raw_sha256": sha256_bytes(raw),
    }


def zero_region(data: bytes, start: int, end: int, what: str) -> dict[str, object]:
    raw = checked_range(data, start, end - start, what)
    if any(raw):
        raise PlaybookError(
            f"{what}: expected zero padding at 0x{start:x}..0x{end:x}"
        )
    return {"offset": start, "size": len(raw), "all_zero": True}


def parse_slots(
    data: bytes,
    record_offset: int,
    descriptor_start: int,
    pointer_start: int,
    endian: str,
    route_base: int,
    route_count: int,
    what: str,
) -> list[dict[str, object]]:
    route_end = route_base + route_count * ROUTE_NODE_SIZE
    slots: list[dict[str, object]] = []
    for index in range(SLOT_COUNT):
        descriptor_field = record_offset + descriptor_start + index * 8
        pointer_field = record_offset + pointer_start + index * 8
        descriptor = u32(data, descriptor_field, endian, f"{what} descriptor")
        stored = u32(data, pointer_field, endian, f"{what} route reference")
        if stored == 0:
            raise PlaybookError(f"{what}: null route reference in slot {index}")
        target = relative(data, pointer_field, endian, f"{what} route reference")
        if not route_base <= target < route_end:
            raise PlaybookError(
                f"{what}: slot {index} target 0x{target:x} is outside "
                f"0x{route_base:x}..0x{route_end:x}"
            )
        if (target - route_base) % ROUTE_NODE_SIZE:
            raise PlaybookError(
                f"{what}: slot {index} target 0x{target:x} is not node-aligned"
            )
        slots.append(
            {
                "slot_index": index,
                "descriptor_field_offset": descriptor_field,
                "descriptor_word": f"0x{descriptor:08x}",
                "route_pointer_field_offset": pointer_field,
                "stored_route_reference": f"0x{stored:08x}",
                "route_node_offset": target,
                "route_node_index": (target - route_base) // ROUTE_NODE_SIZE,
            }
        )
    return slots


def parse_apf_formation_memberships(
    data: bytes,
    *,
    formation_count: int,
    play_count: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Parse APF MASTER's fixed 0x54-stride bitmap table.

    The bit order is MSB first within each byte: bit ``n`` of a row is
    ``row[n // 8] & (0x80 >> (n % 8))``.

    WHAT THIS TABLE IS HAS NOT BEEN ESTABLISHED, and the previous name for it
    -- "formation/play membership" -- is now known to be wrong.  The stock CPU
    playbooks (``SPLB``, see ``mod_editor/core/apf2k8_splb_writer.py``) name a
    formation and list its plays outright, and cross-checking them against this
    table refutes the membership reading: for MASTER row 147 the SPLB books
    give the 3-4 defence "Base, Fan, Razor Left, ...", while row 147 here
    yields "Big Pinch, Big Fan, Big 2 Hard, ..." -- only 31 of 51 overlap, and
    rows 147/148/149 are identical to each other.  Coverage across all
    populated SPLB records is 24-25%, with 0 of 209 records fully covered, so
    it is not an off-by-one or a bit-order error either.

    The row index is therefore NOT the formation index, or the relation is not
    formation-to-play.  Callers must treat ``play_membership_*`` as an
    unidentified relation and must not present it to a user as "the plays this
    formation offers".  The ten-byte row tail also remains raw.
    """

    if not 0 < formation_count <= APF_FORMATION_MEMBERSHIP_CAPACITY:
        raise PlaybookError(
            f"APF formation membership count {formation_count} is outside "
            f"1..{APF_FORMATION_MEMBERSHIP_CAPACITY}"
        )
    maximum_play_bits = APF_FORMATION_MEMBERSHIP_MASK_SIZE * 8
    if not 0 < play_count <= maximum_play_bits:
        raise PlaybookError(
            f"APF play count {play_count} exceeds the {maximum_play_bits}-bit "
            "formation membership mask"
        )
    table_size = (
        APF_FORMATION_MEMBERSHIP_CAPACITY * APF_FORMATION_MEMBERSHIP_SIZE
    )
    table_end = APF_FORMATION_MEMBERSHIP_BASE + table_size
    if table_end + APF_FORMATION_MEMBERSHIP_FINAL_PADDING != len(data):
        raise PlaybookError(
            "APF formation membership table no longer ends at the fixed body "
            "boundary"
        )

    rows: list[dict[str, object]] = []
    for formation_index in range(formation_count):
        offset = (
            APF_FORMATION_MEMBERSHIP_BASE
            + formation_index * APF_FORMATION_MEMBERSHIP_SIZE
        )
        raw = checked_range(
            data,
            offset,
            APF_FORMATION_MEMBERSHIP_SIZE,
            f"APF formation {formation_index} membership",
        )
        mask = raw[:APF_FORMATION_MEMBERSHIP_MASK_SIZE]
        tail = raw[APF_FORMATION_MEMBERSHIP_MASK_SIZE:]
        if len(tail) != APF_FORMATION_MEMBERSHIP_TAIL_SIZE:
            raise PlaybookError("APF formation membership tail size changed")
        indices = [
            play_index
            for play_index in range(play_count)
            if mask[play_index // 8] & (0x80 >> (play_index % 8))
        ]
        for bit_index in range(play_count, maximum_play_bits):
            if mask[bit_index // 8] & (0x80 >> (bit_index % 8)):
                raise PlaybookError(
                    f"APF formation {formation_index} sets unused membership "
                    f"bit {bit_index}"
                )
        rows.append(
            {
                "formation_index": formation_index,
                "offset": offset,
                "size": len(raw),
                "raw_hex": raw.hex(),
                "raw_sha256": sha256_bytes(raw),
                "play_indices": indices,
                "play_count": len(indices),
                "opaque_tail_hex": tail.hex(),
            }
        )

    unused_start = (
        APF_FORMATION_MEMBERSHIP_BASE
        + formation_count * APF_FORMATION_MEMBERSHIP_SIZE
    )
    unused = checked_range(
        data,
        unused_start,
        table_end - unused_start,
        "APF unused formation-membership capacity",
    )
    if any(unused):
        raise PlaybookError("APF unused formation-membership rows are nonzero")
    final_padding = checked_range(
        data,
        table_end,
        APF_FORMATION_MEMBERSHIP_FINAL_PADDING,
        "APF formation-membership final padding",
    )
    if any(final_padding):
        raise PlaybookError("APF formation-membership final padding is nonzero")
    return rows, {
        "base": APF_FORMATION_MEMBERSHIP_BASE,
        "row_size": APF_FORMATION_MEMBERSHIP_SIZE,
        "capacity": APF_FORMATION_MEMBERSHIP_CAPACITY,
        "active_count": formation_count,
        "mask_size": APF_FORMATION_MEMBERSHIP_MASK_SIZE,
        "mask_bit_order": "MSB-first within each byte",
        "opaque_tail_size": APF_FORMATION_MEMBERSHIP_TAIL_SIZE,
        "unused_capacity_offset": unused_start,
        "unused_capacity_size": len(unused),
        "unused_capacity_all_zero": True,
        "final_padding_offset": table_end,
        "final_padding_size": len(final_padding),
        "final_padding_all_zero": True,
    }


def named_record(
    data: bytes,
    platform: str,
    book_name: str,
    outer_index: int,
    kind: str,
    index: int,
    offset: int,
    size: int,
    endian: str,
    encoding: str,
) -> dict[str, object]:
    name_offset = relative(data, offset, endian, f"{platform} {kind} {index} name")
    name, _end = utf16z(
        data, name_offset, encoding, f"{platform} {kind} {index} name"
    )
    if not name:
        raise PlaybookError(f"{platform} {kind} {index}: empty name")
    return {
        "platform": platform,
        "book_name": book_name,
        "outer_index": outer_index,
        "kind": kind,
        "index": index,
        "offset": offset,
        "size": size,
        "name_pointer_field_offset": offset,
        "stored_name_reference": f"0x{u32(data, offset, endian, 'name reference'):08x}",
        "name_offset": name_offset,
        "name": name,
        **raw_metadata(data, offset, size),
    }


def parse_nfl_body(data: bytes, resource: ResourceRecord) -> dict[str, object]:
    identity = f"NFL outer {resource.outer_index}"
    if len(data) != NFL_BODY_SIZE:
        raise PlaybookError(
            f"{identity}: body 0x{len(data):x}, expected 0x{NFL_BODY_SIZE:x}"
        )
    expected_header = bytearray(0x30)
    expected_header[0x0C:0x10] = b"PLAY"
    struct.pack_into("<i", expected_header, 0x10, 0x20 - (0x10 - 1))
    struct.pack_into("<i", expected_header, 0x14, 0 - (0x14 - 1))
    expected_header[0x20:0x28] = "plb".encode("utf-16le") + b"\0\0"
    if data[:0x30] != expected_header:
        raise PlaybookError(f"{identity}: common PLAY header differs")

    formation_count, play_count, category_count, route_count = struct.unpack_from(
        "<IIII", data, 0x34
    )
    for count, capacity, label in (
        (formation_count, NFL_FORMATION_CAPACITY, "formations"),
        (play_count, NFL_PLAY_CAPACITY, "plays"),
        (category_count, NFL_CATEGORY_CAPACITY, "categories"),
    ):
        if not 0 < count <= capacity:
            raise PlaybookError(
                f"{identity}: {label} count {count} outside 1..{capacity}"
            )
    if not 0 < route_count <= MAX_COUNT:
        raise PlaybookError(f"{identity}: invalid route-node count {route_count}")

    root_targets = {
        "book_name": relative(data, 0x30, "<", f"{identity} book name"),
        "formations": relative(data, 0x44, "<", f"{identity} formations"),
        "formation_aux": relative(data, 0x48, "<", f"{identity} formation aux"),
        "plays": relative(data, 0x60, "<", f"{identity} plays"),
        "categories": relative(data, 0x64, "<", f"{identity} categories"),
        "route_nodes": relative(data, 0x68, "<", f"{identity} route nodes"),
    }
    expected_targets = {
        "book_name": NFL_STRING_BASE,
        "formations": NFL_FORMATION_BASE,
        "formation_aux": NFL_FORMATION_AUX_BASE,
        "plays": NFL_PLAY_BASE,
        "categories": NFL_CATEGORY_BASE,
        "route_nodes": NFL_ROUTE_BASE,
    }
    if root_targets != expected_targets:
        raise PlaybookError(
            f"{identity}: fixed-capacity root targets differ: {root_targets}"
        )
    book_name, _ = utf16z(data, NFL_STRING_BASE, "utf-16le", f"{identity} book")

    formations: list[dict[str, object]] = []
    for index in range(formation_count):
        offset = NFL_FORMATION_BASE + index * NFL_FORMATION_SIZE
        record = named_record(
            data, "nfl2k5", book_name, resource.outer_index, "formation",
            index, offset, NFL_FORMATION_SIZE, "<", "utf-16le",
        )
        aux_offset = NFL_FORMATION_AUX_BASE + index * NFL_FORMATION_AUX_SIZE
        record["aux_offset"] = aux_offset
        record["aux_size"] = NFL_FORMATION_AUX_SIZE
        record["aux_raw_hex"] = checked_range(
            data, aux_offset, NFL_FORMATION_AUX_SIZE, "NFL formation aux"
        ).hex()
        record["aux_raw_sha256"] = sha256_bytes(
            checked_range(data, aux_offset, NFL_FORMATION_AUX_SIZE, "NFL formation aux")
        )
        formations.append(record)

    plays: list[dict[str, object]] = []
    for index in range(play_count):
        offset = NFL_PLAY_BASE + index * NFL_PLAY_SIZE
        record = named_record(
            data, "nfl2k5", book_name, resource.outer_index, "play",
            index, offset, NFL_PLAY_SIZE, "<", "utf-16le",
        )
        record["flags_or_id_04"] = f"0x{u32(data, offset + 4, '<', 'play +4'):08x}"
        record["slots"] = parse_slots(
            data, offset, 0x08, 0x0C, "<", NFL_ROUTE_BASE, route_count,
            f"{identity} play {index}",
        )
        plays.append(record)

    categories = [
        named_record(
            data, "nfl2k5", book_name, resource.outer_index, "category",
            index, NFL_CATEGORY_BASE + index * NFL_CATEGORY_SIZE,
            NFL_CATEGORY_SIZE, "<", "utf-16le",
        )
        for index in range(category_count)
    ]
    route_end = NFL_ROUTE_BASE + route_count * ROUTE_NODE_SIZE
    if route_end > NFL_STRING_BASE:
        raise PlaybookError(f"{identity}: route-node array overlaps strings")

    declared_name_targets = [NFL_STRING_BASE]
    declared_name_targets.extend(int(row["name_offset"]) for row in formations)
    declared_name_targets.extend(int(row["name_offset"]) for row in plays)
    declared_name_targets.extend(int(row["name_offset"]) for row in categories)
    name_pool, pool_end = parse_name_pool(
        data, NFL_STRING_BASE, "utf-16le", declared_name_targets, identity
    )
    if any(data[pool_end:]):
        raise PlaybookError(f"{identity}: nonzero bytes follow name pool")

    padding = [
        zero_region(
            data,
            NFL_FORMATION_BASE + formation_count * NFL_FORMATION_SIZE,
            NFL_FORMATION_AUX_BASE,
            f"{identity} formation capacity padding",
        ),
        zero_region(
            data,
            NFL_FORMATION_AUX_BASE + formation_count * NFL_FORMATION_AUX_SIZE,
            NFL_PLAY_BASE,
            f"{identity} formation-aux capacity padding",
        ),
        zero_region(
            data,
            NFL_PLAY_BASE + play_count * NFL_PLAY_SIZE,
            NFL_CATEGORY_BASE,
            f"{identity} play capacity padding",
        ),
        zero_region(
            data,
            NFL_CATEGORY_BASE + category_count * NFL_CATEGORY_SIZE,
            NFL_ROUTE_BASE,
            f"{identity} category capacity padding",
        ),
        zero_region(data, pool_end, len(data), f"{identity} trailing padding"),
    ]
    route_blob = data[NFL_ROUTE_BASE:route_end]
    post_route_opaque = data[route_end:NFL_STRING_BASE]
    return {
        "platform": "nfl2k5",
        "outer_index": resource.outer_index,
        "inner_index": resource.chunk_index,
        "outer_id": resource.outer_id,
        "resource_name": "plb",
        "book_name": book_name,
        "byte_size": len(data),
        "sha256": sha256_bytes(data),
        "endianness": "little",
        "encoding": "UTF-16LE",
        "header_raw_hex": data[:0x30].hex(),
        "root_counts": {
            "formation_count": formation_count,
            "play_count": play_count,
            "category_count": category_count,
            "route_node_count": route_count,
        },
        "root_targets": root_targets,
        "root_opaque_4c_60_hex": data[0x4C:0x60].hex(),
        "root_opaque_6c_134_hex": data[0x6C:0x134].hex(),
        "root_opaque_sha256": sha256_bytes(data[0x4C:0x60] + data[0x6C:0x134]),
        "regions": {
            "formation_base": NFL_FORMATION_BASE,
            "formation_size": NFL_FORMATION_SIZE,
            "formation_aux_base": NFL_FORMATION_AUX_BASE,
            "formation_aux_size": NFL_FORMATION_AUX_SIZE,
            "play_base": NFL_PLAY_BASE,
            "play_size": NFL_PLAY_SIZE,
            "category_base": NFL_CATEGORY_BASE,
            "category_size": NFL_CATEGORY_SIZE,
            "route_node_base": NFL_ROUTE_BASE,
            "route_node_size": ROUTE_NODE_SIZE,
            "route_node_end": route_end,
            "string_pool_base": NFL_STRING_BASE,
            "string_pool_end": pool_end,
        },
        "padding": padding,
        "route_node_blob_sha256": sha256_bytes(route_blob),
        "route_node_blob_hex": route_blob.hex(),
        "post_route_opaque_offset": route_end,
        "post_route_opaque_size": len(post_route_opaque),
        "post_route_opaque_sha256": sha256_bytes(post_route_opaque),
        "post_route_opaque_hex": post_route_opaque.hex(),
        "name_pool": [entry.__dict__ for entry in name_pool],
        "formations": formations,
        "plays": plays,
        "categories": categories,
    }


def parse_apf_body(data: bytes, outer_index: int, inner_index: int) -> dict[str, object]:
    identity = f"APF {outer_index}:{inner_index}"
    if len(data) != APF_BODY_SIZE:
        raise PlaybookError(
            f"{identity}: body 0x{len(data):x}, expected 0x{APF_BODY_SIZE:x}"
        )
    if data[:0x0C] != b"\0" * 0x0C or data[0x0C:0x10] != b"YALP":
        raise PlaybookError(f"{identity}: mixed-endian common header differs")
    if data[0x18:0x20] != b"\0" * 8:
        raise PlaybookError(f"{identity}: common header reserved bytes are nonzero")
    resource_name, resource_name_end = utf16z(
        data, 0x20, "utf-16be", f"{identity} resource name"
    )
    if resource_name != "mpb" or any(data[resource_name_end:0x30]):
        raise PlaybookError(f"{identity}: resource name/padding differs")
    header_name_token = u32(data, 0x10, "<", "APF header name token")
    header_root_token = u32(data, 0x14, "<", "APF header root token")
    if header_name_token - header_root_token != 0x20:
        raise PlaybookError(f"{identity}: opaque header tokens do not differ by +0x20")

    formation_count, play_count, category_count, route_count = struct.unpack_from(
        ">IIII", data, 0x34
    )
    for count, label in (
        (formation_count, "formations"),
        (play_count, "plays"),
        (category_count, "categories"),
        (route_count, "route nodes"),
    ):
        if not 0 < count <= MAX_COUNT:
            raise PlaybookError(f"{identity}: invalid {label} count {count}")

    book_name_offset = relative(data, 0x30, ">", f"{identity} book name")
    if book_name_offset != APF_STRING_BASE:
        raise PlaybookError(
            f"{identity}: book name target 0x{book_name_offset:x}, "
            f"expected 0x{APF_STRING_BASE:x}"
        )
    book_name, _ = utf16z(data, book_name_offset, "utf-16be", f"{identity} book")
    if book_name != "MASTER":
        raise PlaybookError(f"{identity}: expected MASTER, found {book_name!r}")

    category_end = APF_CATEGORY_BASE + category_count * APF_CATEGORY_SIZE
    formation_end = APF_FORMATION_BASE + formation_count * APF_FORMATION_SIZE
    play_end = APF_PLAY_BASE + play_count * APF_PLAY_SIZE
    route_end = APF_ROUTE_BASE + route_count * ROUTE_NODE_SIZE
    if category_end > APF_FORMATION_BASE:
        raise PlaybookError(f"{identity}: categories overlap formations")
    if formation_end > APF_PLAY_BASE:
        raise PlaybookError(f"{identity}: formations overlap plays")
    if play_end > APF_ROUTE_BASE:
        raise PlaybookError(f"{identity}: plays overlap route nodes")
    if route_end > APF_STRING_BASE:
        raise PlaybookError(f"{identity}: route nodes overlap strings")

    categories = [
        named_record(
            data, "apf2k8", book_name, outer_index, "category", index,
            APF_CATEGORY_BASE + index * APF_CATEGORY_SIZE,
            APF_CATEGORY_SIZE, ">", "utf-16be",
        )
        for index in range(category_count)
    ]
    formations = [
        named_record(
            data, "apf2k8", book_name, outer_index, "formation", index,
            APF_FORMATION_BASE + index * APF_FORMATION_SIZE,
            APF_FORMATION_SIZE, ">", "utf-16be",
        )
        for index in range(formation_count)
    ]
    plays: list[dict[str, object]] = []
    for index in range(play_count):
        offset = APF_PLAY_BASE + index * APF_PLAY_SIZE
        record = named_record(
            data, "apf2k8", book_name, outer_index, "play", index,
            offset, APF_PLAY_SIZE, ">", "utf-16be",
        )
        record["flags_or_id_04"] = f"0x{u32(data, offset + 4, '>', 'play +4'):08x}"
        record["unknown_word_08"] = f"0x{u32(data, offset + 8, '>', 'play +8'):08x}"
        record["slots"] = parse_slots(
            data, offset, 0x0C, 0x10, ">", APF_ROUTE_BASE, route_count,
            f"{identity} play {index}",
        )
        plays.append(record)

    declared_name_targets = [book_name_offset]
    declared_name_targets.extend(int(row["name_offset"]) for row in formations)
    declared_name_targets.extend(int(row["name_offset"]) for row in plays)
    declared_name_targets.extend(int(row["name_offset"]) for row in categories)
    name_pool, pool_end = parse_name_pool(
        data, APF_STRING_BASE, "utf-16be", declared_name_targets, identity
    )
    memberships, membership_table = parse_apf_formation_memberships(
        data,
        formation_count=formation_count,
        play_count=play_count,
    )
    if len(memberships) != len(formations):
        raise PlaybookError(f"{identity}: formation membership count differs")
    for formation, membership in zip(formations, memberships, strict=True):
        indices = [int(value) for value in membership["play_indices"]]
        formation["play_membership_offset"] = membership["offset"]
        formation["play_membership_size"] = membership["size"]
        formation["play_membership_raw_hex"] = membership["raw_hex"]
        formation["play_membership_raw_sha256"] = membership["raw_sha256"]
        formation["play_membership_indices"] = indices
        formation["play_membership_names"] = [
            str(plays[index]["name"]) for index in indices
        ]
        formation["play_membership_count"] = membership["play_count"]
        formation["play_membership_opaque_tail_hex"] = membership[
            "opaque_tail_hex"
        ]
    route_blob = data[APF_ROUTE_BASE:route_end]
    post_pool = data[pool_end:]
    padding = [
        zero_region(
            data, category_end, APF_FORMATION_BASE,
            f"{identity} category/formation padding",
        ),
        zero_region(
            data, formation_end, APF_PLAY_BASE,
            f"{identity} formation/play padding",
        ),
        zero_region(
            data, play_end, APF_ROUTE_BASE, f"{identity} play/route padding",
        ),
        zero_region(
            data, route_end, APF_STRING_BASE, f"{identity} route/string padding",
        ),
        zero_region(
            data,
            pool_end,
            APF_FORMATION_MEMBERSHIP_BASE,
            f"{identity} string/membership padding",
        ),
    ]
    return {
        "platform": "apf2k8",
        "outer_index": outer_index,
        "inner_index": inner_index,
        "resource_name": resource_name,
        "book_name": book_name,
        "byte_size": len(data),
        "sha256": sha256_bytes(data),
        "endianness": "big payload with mixed-endian common header",
        "encoding": "UTF-16BE",
        "header_raw_hex": data[:0x30].hex(),
        "header_opaque_name_token_le": f"0x{header_name_token:08x}",
        "header_opaque_root_token_le": f"0x{header_root_token:08x}",
        "root_counts": {
            "formation_count": formation_count,
            "play_count": play_count,
            "category_count": category_count,
            "route_node_count": route_count,
        },
        "regions": {
            "category_base": APF_CATEGORY_BASE,
            "category_size": APF_CATEGORY_SIZE,
            "formation_base": APF_FORMATION_BASE,
            "formation_size": APF_FORMATION_SIZE,
            "play_base": APF_PLAY_BASE,
            "play_size": APF_PLAY_SIZE,
            "route_node_base": APF_ROUTE_BASE,
            "route_node_size": ROUTE_NODE_SIZE,
            "route_node_end": route_end,
            "string_pool_base": APF_STRING_BASE,
            "string_pool_end": pool_end,
            "formation_play_membership_base": APF_FORMATION_MEMBERSHIP_BASE,
            "formation_play_membership_size": APF_FORMATION_MEMBERSHIP_SIZE,
            "formation_play_membership_capacity": APF_FORMATION_MEMBERSHIP_CAPACITY,
            "formation_play_membership_mask_size": APF_FORMATION_MEMBERSHIP_MASK_SIZE,
            "post_string_opaque_offset": pool_end,
            "post_string_opaque_size": len(post_pool),
        },
        "padding": padding,
        "route_node_blob_sha256": sha256_bytes(route_blob),
        "route_node_blob_hex": route_blob.hex(),
        "post_string_opaque_sha256": sha256_bytes(post_pool),
        "post_string_opaque_hex": post_pool.hex(),
        "formation_play_membership_table": membership_table,
        "formation_play_membership_count": sum(
            int(row["play_count"]) for row in memberships
        ),
        "name_pool": [entry.__dict__ for entry in name_pool],
        "formations": formations,
        "plays": plays,
        "categories": categories,
    }


def read_apf_part(
    reader: apf_inner.ArchiveReader,
    record: apf_inner.IFFRecord,
    part: apf_inner.FilePart,
    cache: dict[int, bytes],
    maximum: int,
) -> bytes:
    block = record.blocks[part.block_index]
    if not block.is_compressed:
        return reader.read(record.entry, block.start_offset + part.offset, part.length)
    if part.block_index not in cache:
        cache[part.block_index] = apf_inner.decode_block(
            reader, record, part.block_index, maximum
        )
    decoded = cache[part.block_index]
    end = part.offset + part.length
    if end > len(decoded):
        raise PlaybookError("APF PLAY part exceeds decoded block")
    return decoded[part.offset:end]


def parse_apf(index: Path, maximum: int) -> list[dict[str, object]]:
    archive = apf_outer.parse_archive(index)
    playbooks: list[dict[str, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for entry in archive.entries:
            if entry.head_hex != "ff3bef94":
                continue
            iff = apf_inner.parse_iff(reader, entry)
            cache: dict[int, bytes] = {}
            for item in iff.files:
                if item.type_name != "PLAY":
                    continue
                if len(item.parts) != 1:
                    raise PlaybookError(
                        f"APF {entry.table_index}:{item.index}: expected one PLAY "
                        f"part, found {len(item.parts)}"
                    )
                data = read_apf_part(reader, iff, item.parts[0], cache, maximum)
                playbook = parse_apf_body(data, entry.table_index, item.index)
                playbook["inner_name"] = item.name
                playbook["inner_id"] = f"0x{item.file_id:08x}"
                playbook["type_hash"] = f"0x{item.type_hash:08x}"
                playbooks.append(playbook)
    return playbooks


def parse_nfl(index: Path, scan: Path) -> list[dict[str, object]]:
    inventory, resources = parse_inventory(scan)
    selected = [item for item in resources if item.kind == "PLAY"]
    declared = int(inventory["summary"]["resource_kind_counts"]["PLAY"])
    if len(selected) != declared:
        raise PlaybookError(
            f"NFL inventory selected {len(selected)} PLAY, declares {declared}"
        )
    archive = parse_nfl_archive(index)
    playbooks: list[dict[str, object]] = []
    for item in selected:
        entry = archive.entries[item.outer_index]
        span = read_entry_range(
            archive, entry, item.chunk_offset, 0x20 + item.stored_size
        )
        data, _detail = decode_resource(span, item)
        playbooks.append(parse_nfl_body(data, item))
    return playbooks


def records(playbooks: Iterable[dict[str, object]], kind: str) -> list[dict[str, object]]:
    key = "categories" if kind == "category" else kind + "s"
    return [record for book in playbooks for record in book[key]]


def casefold_names(items: Iterable[dict[str, object]]) -> set[str]:
    return {str(item["name"]).casefold() for item in items}


def write_tsv(
    path: Path,
    playbooks: list[dict[str, object]],
    shared: dict[str, set[str]],
) -> None:
    fields = [
        "platform", "outer_index", "book_name", "kind", "index", "offset",
        "size", "name_offset", "name", "shared_casefolded_name", "raw_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, dialect="excel-tab", extrasaction="ignore"
        )
        writer.writeheader()
        for book in playbooks:
            for kind in ("category", "formation", "play"):
                key = "categories" if kind == "category" else kind + "s"
                for record in book[key]:
                    writer.writerow(
                        {
                            **record,
                            "shared_casefolded_name": (
                                str(record["name"]).casefold() in shared[kind]
                            ),
                        }
                    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--apf-index", type=Path, required=True)
    result.add_argument("--nfl-index", type=Path, required=True)
    result.add_argument(
        "--nfl-resource-scan", type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    result.add_argument(
        "--nfl-xbe", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    result.add_argument(
        "--apf-xex", type=Path,
        default=Path("extracted/All-Pro Football 2K8 (USA)/default.xex"),
    )
    result.add_argument(
        "--apf-pseudo", type=Path,
        default=Path(
            "research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_16384_16639.c"
        ),
    )
    result.add_argument("--json", type=Path, required=True)
    result.add_argument("--tsv", type=Path, required=True)
    result.add_argument("--max-decompressed", type=int, default=64 * 1024 * 1024)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.max_decompressed <= 0:
        raise PlaybookError("--max-decompressed must be positive")
    apf_books = parse_apf(args.apf_index, args.max_decompressed)
    nfl_books = parse_nfl(args.nfl_index, args.nfl_resource_scan)
    if len(apf_books) != 1 or len(nfl_books) != 37:
        raise PlaybookError(
            f"expected APF=1 and NFL=37 PLAY resources, found "
            f"APF={len(apf_books)} NFL={len(nfl_books)}"
        )

    apf_records = {
        kind: records(apf_books, kind) for kind in ("category", "formation", "play")
    }
    nfl_records = {
        kind: records(nfl_books, kind) for kind in ("category", "formation", "play")
    }
    shared = {
        kind: casefold_names(apf_records[kind]) & casefold_names(nfl_records[kind])
        for kind in ("category", "formation", "play")
    }
    summary = {
        "apf_playbook_count": len(apf_books),
        "nfl_playbook_count": len(nfl_books),
        "apf_category_count": len(apf_records["category"]),
        "apf_formation_count": len(apf_records["formation"]),
        "apf_play_count": len(apf_records["play"]),
        "apf_route_node_count": sum(
            int(book["root_counts"]["route_node_count"]) for book in apf_books
        ),
        "apf_formation_play_membership_count": sum(
            int(book["formation_play_membership_count"]) for book in apf_books
        ),
        "nfl_category_count": len(nfl_records["category"]),
        "nfl_formation_count": len(nfl_records["formation"]),
        "nfl_play_count": len(nfl_records["play"]),
        "nfl_route_node_count": sum(
            int(book["root_counts"]["route_node_count"]) for book in nfl_books
        ),
        "apf_distinct_category_name_count": len(casefold_names(apf_records["category"])),
        "apf_distinct_formation_name_count": len(casefold_names(apf_records["formation"])),
        "apf_distinct_play_name_count": len(casefold_names(apf_records["play"])),
        "nfl_distinct_category_name_count": len(casefold_names(nfl_records["category"])),
        "nfl_distinct_formation_name_count": len(casefold_names(nfl_records["formation"])),
        "nfl_distinct_play_name_count": len(casefold_names(nfl_records["play"])),
        "shared_casefolded_category_name_count": len(shared["category"]),
        "shared_casefolded_formation_name_count": len(shared["formation"]),
        "shared_casefolded_play_name_count": len(shared["play"]),
        "all_name_pointers_bounded": True,
        "all_name_pools_exact_and_fully_referenced": True,
        "all_play_slot_counts_equal_eleven": True,
        "all_route_references_bounded_and_node_aligned": True,
        "all_apf_formation_play_membership_masks_bounded": True,
        "all_apf_unused_formation_membership_capacity_zero": True,
        "all_unused_named_record_capacity_padding_zero": True,
    }
    report = {
        "schema": SCHEMA,
        "sources": {
            "apf_index": str(args.apf_index),
            "apf_index_sha256": sha256_file(args.apf_index),
            "apf_xex": str(args.apf_xex),
            "apf_xex_sha256": sha256_file(args.apf_xex),
            "apf_pseudo": str(args.apf_pseudo),
            "apf_pseudo_sha256": sha256_file(args.apf_pseudo),
            "nfl_index": str(args.nfl_index),
            "nfl_index_sha256": sha256_file(args.nfl_index),
            "nfl_resource_scan": str(args.nfl_resource_scan),
            "nfl_resource_scan_sha256": sha256_file(args.nfl_resource_scan),
            "nfl_xbe": str(args.nfl_xbe),
            "nfl_xbe_sha256": sha256_file(args.nfl_xbe),
        },
        "constants": {
            "relative_pointer_rule": (
                "target = pointer_field_offset - 1 + signed_stored_value"
            ),
            "play_assignment_slot_count": SLOT_COUNT,
            "route_node_size": ROUTE_NODE_SIZE,
            "nfl_formation_size": NFL_FORMATION_SIZE,
            "nfl_formation_aux_size": NFL_FORMATION_AUX_SIZE,
            "nfl_play_size": NFL_PLAY_SIZE,
            "nfl_category_size": NFL_CATEGORY_SIZE,
            "apf_formation_size": APF_FORMATION_SIZE,
            "apf_play_size": APF_PLAY_SIZE,
            "apf_category_size": APF_CATEGORY_SIZE,
            "apf_formation_play_membership_base": APF_FORMATION_MEMBERSHIP_BASE,
            "apf_formation_play_membership_size": APF_FORMATION_MEMBERSHIP_SIZE,
            "apf_formation_play_membership_capacity": APF_FORMATION_MEMBERSHIP_CAPACITY,
            "apf_formation_play_membership_mask_size": APF_FORMATION_MEMBERSHIP_MASK_SIZE,
        },
        "executable_evidence": {
            "nfl_registration": (
                "default.xbe:0x00166690 registers FourCC PLAY with loader "
                "callback 0x00166610"
            ),
            "nfl_relocator": (
                "default.xbe:0x000E0D90 fixes root +0x30/+0x44/+0x48/"
                "+0x60/+0x64/+0x68, every play name and eleven assignment "
                "pointers, every formation name, and every category name"
            ),
            "nfl_accessors": (
                "default.xbe:0x000E05E0/0x000E0660/0x000E06E0/0x000E0830 "
                "prove category 0x10, formation 0xb4, play 0x60, and "
                "formation-aux 0x50 strides and associated root fields"
            ),
            "apf_asset_lookup": (
                "default.xex:0x84AE8C40 calls Function_84B16398 with DRAM "
                "hash 0xbb05a9c1, logical ID 0x33cdf8e3 for mpb, and "
                "CRC32('PLAY') 0x681c330e"
            ),
        },
        "summary": summary,
        "shared_casefolded_names": {
            ("categories" if kind == "category" else kind + "s"): sorted(shared[kind])
            for kind in ("category", "formation", "play")
        },
        "portme": [
            "PORTME: name remaining root, formation, category, play, and assignment descriptor fields from consumers.",
            "PORTME: recover eight-byte route-node opcodes, chain termination, coordinate units, and branching semantics.",
            "PORTME: name the ten-byte tail on each proved APF formation/play-membership bitmap row from executable consumers.",
            "PORTME: trace every fixed-capacity/count consumer before allowing added formations, plays, categories, or route nodes.",
            "PORTME: implement a writer and archive repacker only after pointer ownership, hashing, and capacity invariants are complete.",
        ],
        "playbooks": apf_books + nfl_books,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    newline="\n",
)
    write_tsv(args.tsv, apf_books + nfl_books, shared)
    print(
        "PLAYBOOK_INVENTORY_COMPLETE "
        f"apf={len(apf_books)}/{len(apf_records['formation'])}/"
        f"{len(apf_records['play'])} "
        f"nfl={len(nfl_books)}/{len(nfl_records['formation'])}/"
        f"{len(nfl_records['play'])} "
        f"shared={len(shared['formation'])}/{len(shared['play'])}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        PlaybookError,
        ProbeError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        struct.error,
    ) as exc:
        raise SystemExit(f"error: {exc}") from exc
