#!/usr/bin/env python3
"""Strict read-only parser for NFL 2K5 disc ``ROST`` resources.

The parser deliberately separates facts proved by the XBE relocators from
still-opaque record fields.  It never writes a roster back to the game.  The
shared 0x20-byte resource wrapper is read through ``nfl_outer`` and
``nfl_txtr``; every relative pointer is then checked against the decoded body
before any text or relationship is exported.

An optional decoded APF 2K8 ``ROST/roster`` block can be supplied to validate
the cross-title root/table-0 lineage without pretending the two player record
layouts are interchangeable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from collections import Counter, defaultdict
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

from nfl_outer import Archive, Entry, parse_archive
from nfl_scene_probe import read_entry_range
from nfl_txtr import HEADER, Chunk, decode_chunk


INVENTORY_SCHEMA = "nfl2k5_resource_chunk_inventory/v1"
OUTPUT_SCHEMA = "nfl2k5_roster_inventory/v1"
CROSS_TITLE_SCHEMA = "vc_roster_cross_title_probe/v1"
ROST_MAGIC = b"ROST"
NFL_ROOT_SIZE = 0x70
NFL_PLAYER_STRIDE = 0x54
NFL_TEAM_STRIDE = 0x1F4
NFL_TEAM_SLOT_COUNT = 65
APF_PLAYER_STRIDE = 0x14C
MAX_UTF16_BYTES = 4096


class RosterError(ValueError):
    """Raised for a structural or bounds validation failure."""


@dataclass(frozen=True)
class InventoryRecord:
    outer_index: int
    outer_id: str
    outer_size: int
    chunk_index: int
    chunk_offset: int
    stored_size: int
    word_08: int
    word_0c: int
    word_10: int
    word_14: int


@dataclass(frozen=True)
class TableSpec:
    name: str
    count_offset: int
    pointer_offset: int
    stride: int
    evidence: str


TABLE_SPECS = (
    TableSpec("primary_players", 0x00, 0x04, 0x54, "0x000C0500 -> 0x000E5E70"),
    TableSpec("secondary_players", 0x08, 0x0C, 0x54, "0x000C0500 -> 0x000E5E70"),
    TableSpec("stadiums", 0x10, 0x14, 0x80, "0x000C0500 -> 0x00241E60"),
    TableSpec("teams", 0x18, 0x1C, 0x1F4, "0x000C0500 -> 0x002418C0"),
    TableSpec("colleges", 0x20, 0x24, 0x08, "0x000C0500 -> 0x002421D0"),
    TableSpec("coaches", 0x30, 0x34, 0xA8, "0x000C0500 -> 0x002415C0"),
    TableSpec("player_pointer_vector", 0x38, 0x3C, 0x04, "0x000C0500 -> 0x002425F0"),
    TableSpec("team_labels", 0x48, 0x4C, 0x08, "0x000C0500 -> 0x00196FE0"),
    TableSpec("generated_names", 0x50, 0x54, 0x08, "0x000C0500 -> 0x00242340"),
    TableSpec("historic_descriptors", 0x58, 0x5C, 0x10, "0x000C0500 inline 0x10 loop"),
)


def parse_int(value: str | int) -> int:
    return int(value, 0) if isinstance(value, str) else int(value)


def u16(data: bytes, offset: int) -> int:
    require_range(data, offset, 2, "u16")
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    require_range(data, offset, 4, "u32")
    return struct.unpack_from("<I", data, offset)[0]


def s32(data: bytes, offset: int) -> int:
    require_range(data, offset, 4, "s32")
    return struct.unpack_from("<i", data, offset)[0]


def be_u32(data: bytes, offset: int) -> int:
    require_range(data, offset, 4, "big-endian u32")
    return struct.unpack_from(">I", data, offset)[0]


def be_s32(data: bytes, offset: int) -> int:
    require_range(data, offset, 4, "big-endian s32")
    return struct.unpack_from(">i", data, offset)[0]


def require_range(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise RosterError(
            f"{label}: range 0x{offset:x}+0x{size:x} exceeds 0x{len(data):x} bytes"
        )


def relative_pointer(
    data: bytes, field_offset: int, label: str, *, byte_order: str = "little"
) -> int | None:
    """Resolve Visual Concepts' field-local biased signed relative pointer.

    On disk, nonzero fields use ``target = field + signed_value - 1``.  This is
    the inverse of the XBE serializer at 0x000C0730/record helpers and is also
    observed in the APF big-endian root.
    """
    value = s32(data, field_offset) if byte_order == "little" else be_s32(data, field_offset)
    if value == 0:
        return None
    target = field_offset + value - 1
    if not 0 <= target < len(data):
        raise RosterError(
            f"{label}: field 0x{field_offset:x} relative {value:+d} "
            f"resolves outside body at 0x{target:x}"
        )
    return target


def utf16z(data: bytes, offset: int | None, label: str) -> str | None:
    if offset is None:
        return None
    if offset & 1:
        raise RosterError(f"{label}: UTF-16 pointer 0x{offset:x} is not 2-byte aligned")
    require_range(data, offset, 2, label)
    limit = min(len(data), offset + MAX_UTF16_BYTES)
    end = offset
    while end + 1 < limit and data[end : end + 2] != b"\0\0":
        end += 2
    if end + 1 >= limit or data[end : end + 2] != b"\0\0":
        raise RosterError(f"{label}: no UTF-16 terminator within {MAX_UTF16_BYTES} bytes")
    try:
        value = data[offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise RosterError(f"{label}: invalid UTF-16LE at 0x{offset:x}") from exc
    if any(not (character.isprintable() or character in "\t\r\n") for character in value):
        raise RosterError(f"{label}: non-printable UTF-16 text at 0x{offset:x}")
    return value


def string_pointer(data: bytes, field: int, label: str) -> tuple[int | None, str | None]:
    pointer = relative_pointer(data, field, label)
    return pointer, utf16z(data, pointer, label)


def index_for(pointer: int | None, table: dict[str, object]) -> int | None:
    if pointer is None:
        return None
    start = int(table["offset"])
    count = int(table["count"])
    stride = int(table["stride"])
    end = start + count * stride
    if start <= pointer < end and (pointer - start) % stride == 0:
        return (pointer - start) // stride
    return None


def parse_inventory(path: Path) -> list[InventoryRecord]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != INVENTORY_SCHEMA:
        raise RosterError(f"unsupported inventory schema in {path}")
    records: list[InventoryRecord] = []
    for item in raw.get("chunks", []):
        if item.get("kind") != "ROST":
            continue
        records.append(
            InventoryRecord(
                outer_index=int(item["outer_index"]),
                outer_id=str(item["outer_id"]),
                outer_size=int(item["outer_size"]),
                chunk_index=int(item["chunk_index"]),
                chunk_offset=int(item["chunk_offset"]),
                stored_size=int(item["stored_size"]),
                word_08=int(item["word_08"]),
                word_0c=int(item["word_0c"]),
                word_10=parse_int(item["word_10"]),
                word_14=int(item["word_14"]),
            )
        )
    if not records:
        raise RosterError(f"inventory contains no ROST chunks: {path}")
    return records


def load_body(archive: Archive, record: InventoryRecord) -> tuple[bytes, bytes]:
    entry = archive.entries[record.outer_index]
    if entry.size != record.outer_size:
        raise RosterError(f"outer {record.outer_index}: inventory size changed")
    size = HEADER.size + record.stored_size
    raw = read_entry_range(archive, entry, record.chunk_offset, size)
    values = HEADER.unpack_from(raw, 0)
    kind = values[0]
    if kind != ROST_MAGIC:
        raise RosterError(f"outer {record.outer_index}: wrapper is {kind!r}, not ROST")
    if values[1:6] != (
        record.stored_size,
        record.word_08,
        record.word_0c,
        record.word_10,
        record.word_14,
    ):
        raise RosterError(f"outer {record.outer_index}: wrapper differs from inventory")
    if values[6:] != (0, 0):
        raise RosterError(f"outer {record.outer_index}: reserved wrapper words are nonzero")
    if record.chunk_offset != 0 or size != entry.size:
        raise RosterError(
            f"outer {record.outer_index}: expected one exact ROST wrapper, got "
            f"offset 0x{record.chunk_offset:x}, span 0x{size:x}, entry 0x{entry.size:x}"
        )
    chunk = Chunk(
        index=record.chunk_index,
        offset=0,
        kind="ROST",
        stored_size=record.stored_size,
        system_bytes=record.word_08,
        video_bytes=record.word_0c,
        compression_magic=record.word_10,
        overlap_scratch_bytes=record.word_14,
        reserved0=0,
        reserved1=0,
    )
    body, decode_info = decode_chunk(raw, chunk)
    if decode_info is not None:
        raise RosterError(f"outer {record.outer_index}: unexpected compressed ROST")
    if record.word_10 != 0 or record.word_08 != record.stored_size or record.word_0c != 0:
        raise RosterError(f"outer {record.outer_index}: unsupported ROST wrapper variant")
    return raw, body


def parse_tables(body: bytes, root: int, outer_index: int) -> dict[str, dict[str, object]]:
    tables: dict[str, dict[str, object]] = {}
    for spec in TABLE_SPECS:
        count = u32(body, root + spec.count_offset)
        pointer = relative_pointer(
            body, root + spec.pointer_offset, f"outer {outer_index} {spec.name}"
        )
        if pointer is None:
            if count:
                raise RosterError(f"outer {outer_index}: {spec.name} has count {count} and null pointer")
            # Canonical files still use a nonnull empty-boundary pointer, but
            # tolerate null for a structurally valid empty future variant.
            pointer = root + NFL_ROOT_SIZE
        byte_size = count * spec.stride
        require_range(body, pointer, byte_size, f"outer {outer_index} {spec.name}")
        tables[spec.name] = {
            "count": count,
            "offset": pointer,
            "stride": spec.stride,
            "end": pointer + byte_size,
            "relocator_evidence": spec.evidence,
        }
    return tables


def parse_resource(archive: Archive, record: InventoryRecord) -> dict[str, object]:
    raw, body = load_body(archive, record)
    label_prefix = f"outer {record.outer_index}"
    require_range(body, 0, 0x40, f"{label_prefix} preamble")
    if body[:0x0C] != bytes(0x0C) or body[0x0C:0x10] != ROST_MAGIC:
        raise RosterError(f"{label_prefix}: invalid decoded ROST preamble")
    version = u32(body, 0x10)
    if version != 17:
        raise RosterError(f"{label_prefix}: ROST version {version}, expected 17")
    root = relative_pointer(body, 0x14, f"{label_prefix} root")
    if root != 0x40:
        raise RosterError(f"{label_prefix}: root is 0x{root:x}, expected 0x40")
    if body[0x18:0x20] != bytes(8):
        raise RosterError(f"{label_prefix}: nonzero reserved preamble bytes")
    label = utf16z(body, 0x20, f"{label_prefix} label")
    if label not in ("roster", "historic"):
        raise RosterError(f"{label_prefix}: unexpected label {label!r}")
    require_range(body, root, NFL_ROOT_SIZE, f"{label_prefix} root header")
    root_words = [u32(body, root + index * 4) for index in range(NFL_ROOT_SIZE // 4)]
    tables = parse_tables(body, root, record.outer_index)

    colleges: list[dict[str, object]] = []
    table = tables["colleges"]
    for index in range(int(table["count"])):
        offset = int(table["offset"]) + index * 8
        pointer, name = string_pointer(body, offset, f"{label_prefix} college {index}")
        colleges.append(
            {"index": index, "offset": offset, "name": name, "name_offset": pointer,
             "code": u32(body, offset + 4), "raw_hex": body[offset : offset + 8].hex()}
        )

    stadiums: list[dict[str, object]] = []
    table = tables["stadiums"]
    stadium_string_fields = (
        (0x00, "name"), (0x08, "location"), (0x0C, "asset_code"),
        (0x10, "display_name"), (0x14, "secondary_label"),
    )
    for index in range(int(table["count"])):
        offset = int(table["offset"]) + index * 0x80
        item: dict[str, object] = {"index": index, "offset": offset}
        for field, name in stadium_string_fields:
            pointer, value = string_pointer(body, offset + field, f"{label_prefix} stadium {index} {name}")
            item[name] = value
            item[f"{name}_offset"] = pointer
        item["raw_hex"] = body[offset : offset + 0x80].hex()
        stadiums.append(item)

    coaches: list[dict[str, object]] = []
    table = tables["coaches"]
    coach_fields = (
        (0x00, "first_name"), (0x04, "last_name"),
        (0x08, "description_1"), (0x0C, "description_2"), (0x10, "description_3"),
    )
    for index in range(int(table["count"])):
        offset = int(table["offset"]) + index * 0xA8
        item = {"index": index, "offset": offset, "identity_code_u16_40": u16(body, offset + 0x40)}
        for field, name in coach_fields:
            pointer, value = string_pointer(body, offset + field, f"{label_prefix} coach {index} {name}")
            item[name] = value
            item[f"{name}_offset"] = pointer
        item["raw_hex"] = body[offset : offset + 0xA8].hex()
        coaches.append(item)

    team_labels: list[dict[str, object]] = []
    table = tables["team_labels"]
    for index in range(int(table["count"])):
        offset = int(table["offset"]) + index * 8
        _, nickname = string_pointer(body, offset, f"{label_prefix} team label {index} nickname")
        _, abbreviation = string_pointer(body, offset + 4, f"{label_prefix} team label {index} abbreviation")
        team_labels.append(
            {"index": index, "offset": offset, "nickname": nickname,
             "abbreviation": abbreviation, "raw_hex": body[offset : offset + 8].hex()}
        )

    generated_names: list[dict[str, object]] = []
    table = tables["generated_names"]
    for index in range(int(table["count"])):
        offset = int(table["offset"]) + index * 8
        _, first = string_pointer(body, offset, f"{label_prefix} generated name {index} first")
        _, last = string_pointer(body, offset + 4, f"{label_prefix} generated name {index} last")
        generated_names.append(
            {"index": index, "offset": offset, "first_name": first, "last_name": last,
             "raw_hex": body[offset : offset + 8].hex()}
        )

    historic_descriptors: list[dict[str, object]] = []
    table = tables["historic_descriptors"]
    for index in range(int(table["count"])):
        offset = int(table["offset"]) + index * 0x10
        pointer, slug = string_pointer(body, offset + 0x0C, f"{label_prefix} historic descriptor {index}")
        historic_descriptors.append(
            {"index": index, "offset": offset, "slug": slug, "slug_offset": pointer,
             "raw_hex": body[offset : offset + 0x10].hex()}
        )

    players: list[dict[str, object]] = []
    player_by_offset: dict[int, tuple[str, int]] = {}
    for pool_name in ("primary_players", "secondary_players"):
        table = tables[pool_name]
        for index in range(int(table["count"])):
            offset = int(table["offset"]) + index * NFL_PLAYER_STRIDE
            college_pointer = relative_pointer(body, offset, f"{label_prefix} {pool_name} {index} college")
            college_index = index_for(college_pointer, tables["colleges"])
            if college_index is None and college_pointer is not None:
                raise RosterError(
                    f"{label_prefix} {pool_name} {index}: college pointer 0x{college_pointer:x} "
                    "does not select an 0x08-byte college record"
                )
            first_pointer, first_name = string_pointer(
                body, offset + 0x10, f"{label_prefix} {pool_name} {index} first name"
            )
            last_pointer, last_name = string_pointer(
                body, offset + 0x14, f"{label_prefix} {pool_name} {index} last name"
            )
            if first_name is None or last_name is None:
                raise RosterError(f"{label_prefix} {pool_name} {index}: null player name")
            auxiliary_pointer = relative_pointer(
                body, offset + 0x2C, f"{label_prefix} {pool_name} {index} auxiliary pointer"
            )
            item = {
                "pool": pool_name,
                "index": index,
                "offset": offset,
                "first_name": first_name,
                "last_name": last_name,
                "first_name_offset": first_pointer,
                "last_name_offset": last_pointer,
                "college_index": college_index,
                "college_name": colleges[college_index]["name"] if college_index is not None else None,
                "auxiliary_pointer_offset": auxiliary_pointer,
                "raw_hex": body[offset : offset + NFL_PLAYER_STRIDE].hex(),
                "team_refs": [],
            }
            players.append(item)
            player_by_offset[offset] = (pool_name, index)

    player_pointer_vector: list[dict[str, object]] = []
    table = tables["player_pointer_vector"]
    for index in range(int(table["count"])):
        field = int(table["offset"]) + index * 4
        pointer = relative_pointer(body, field, f"{label_prefix} player pointer vector {index}")
        if pointer not in player_by_offset:
            raise RosterError(
                f"{label_prefix} player pointer vector {index}: 0x{pointer:x} is not a player record"
            )
        pool_name, player_index = player_by_offset[pointer]
        player_pointer_vector.append(
            {"index": index, "field_offset": field, "pool": pool_name,
             "player_index": player_index, "player_offset": pointer}
        )

    teams: list[dict[str, object]] = []
    team_table = tables["teams"]
    for index in range(int(team_table["count"])):
        offset = int(team_table["offset"]) + index * NFL_TEAM_STRIDE
        roster_size = body[offset + 0x11C]
        if roster_size > NFL_TEAM_SLOT_COUNT:
            raise RosterError(f"{label_prefix} team {index}: roster size {roster_size} exceeds 65")
        roster: list[dict[str, object]] = []
        for slot in range(NFL_TEAM_SLOT_COUNT):
            pointer = relative_pointer(body, offset + slot * 4, f"{label_prefix} team {index} slot {slot}")
            if slot < roster_size:
                if pointer not in player_by_offset:
                    raise RosterError(
                        f"{label_prefix} team {index} slot {slot}: 0x{pointer:x} is not a player record"
                    )
                pool_name, player_index = player_by_offset[pointer]
                roster.append({"slot": slot, "pool": pool_name, "player_index": player_index})
            elif pointer is not None:
                raise RosterError(f"{label_prefix} team {index}: nonnull unused roster slot {slot}")

        text_values: dict[str, object] = {}
        for field, name in (
            (0x104, "nickname"), (0x108, "abbreviation"), (0x10C, "asset_code"),
            (0x138, "city"), (0x13C, "city_abbreviation"),
        ):
            pointer, value = string_pointer(body, offset + field, f"{label_prefix} team {index} {name}")
            if value is None:
                raise RosterError(f"{label_prefix} team {index}: null {name}")
            text_values[name] = value
            text_values[f"{name}_offset"] = pointer

        stadium_pointer = relative_pointer(body, offset + 0x114, f"{label_prefix} team {index} stadium")
        stadium_index = index_for(stadium_pointer, tables["stadiums"])
        if stadium_pointer is not None and stadium_index is None:
            raise RosterError(f"{label_prefix} team {index}: invalid stadium reference")
        coach_pointer = relative_pointer(body, offset + 0x14C, f"{label_prefix} team {index} coach")
        coach_index = index_for(coach_pointer, tables["coaches"])
        if coach_pointer is not None and coach_index is None:
            raise RosterError(f"{label_prefix} team {index}: invalid coach reference")
        label_pointer = relative_pointer(body, offset + 0x110, f"{label_prefix} team {index} label pair")
        label_index = index_for(label_pointer, tables["team_labels"])
        related: list[int | None] = []
        for field in (0x140, 0x144, 0x148):
            pointer = relative_pointer(body, offset + field, f"{label_prefix} team {index} related +0x{field:x}")
            related_index = index_for(pointer, tables["teams"])
            if pointer is not None and related_index is None:
                raise RosterError(f"{label_prefix} team {index}: invalid related-team reference")
            related.append(related_index)
        item = {
            "index": index,
            "offset": offset,
            **text_values,
            "roster_size": roster_size,
            "roster": roster,
            "team_kind_code": u32(body, offset + 0x128),
            "stadium_index": stadium_index,
            "coach_index": coach_index,
            "team_label_index": label_index,
            "team_label_raw_pointer": label_pointer,
            "related_team_indices": related,
            "raw_hex": body[offset : offset + NFL_TEAM_STRIDE].hex(),
        }
        teams.append(item)
        for reference in roster:
            player_offset = int(tables[str(reference["pool"])]["offset"]) + int(reference["player_index"]) * NFL_PLAYER_STRIDE
            pool_name, player_index = player_by_offset[player_offset]
            # Find the stable item without assuming the two pools have the same base index.
            for player in players:
                if player["pool"] == pool_name and player["index"] == player_index:
                    player["team_refs"].append(index)
                    break

    # These fields are pointer-like in the corpus but are not all consumed by
    # an identified fixed-stride relocator.  Preserve exact values and resolved
    # in-bounds targets without assigning a speculative schema.
    opaque_root_fields: list[dict[str, object]] = []
    for field in (0x2C, 0x44, 0x64, 0x68, 0x6C):
        target = relative_pointer(body, root + field, f"{label_prefix} opaque root +0x{field:x}")
        opaque_root_fields.append(
            {"field_offset": field, "stored_value": u32(body, root + field), "target": target}
        )

    return {
        "outer_index": record.outer_index,
        "outer_id": record.outer_id,
        "outer_size": record.outer_size,
        "wrapper_sha256": hashlib.sha256(raw).hexdigest(),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "body_size": len(body),
        "label": label,
        "version": version,
        "root_offset": root,
        "root_words": root_words,
        "tables": tables,
        "opaque_root_pointer_fields": opaque_root_fields,
        "colleges": colleges,
        "stadiums": stadiums,
        "coaches": coaches,
        "team_labels": team_labels,
        "generated_names": generated_names,
        "historic_descriptors": historic_descriptors,
        "player_pointer_vector": player_pointer_vector,
        "players": players,
        "teams": teams,
        "validation": {
            "wrapper_exact_single_chunk": True,
            "raw_uncompressed_body": True,
            "inner_magic_and_version": True,
            "all_fixed_tables_in_bounds": True,
            "all_relocated_record_pointers_in_bounds": True,
            "all_exported_utf16_valid": True,
            "all_roster_slots_select_exact_player_records": True,
        },
    }


def parse_apf_cross_title(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    require_range(data, 0, APF_PLAYER_STRIDE, "APF roster root")
    count = be_u32(data, 0)
    player_table = relative_pointer(data, 4, "APF primary player table", byte_order="big")
    if player_table != APF_PLAYER_STRIDE:
        raise RosterError(
            f"APF primary player table is 0x{player_table:x}, expected root-size/stride 0x14c"
        )
    player_end = player_table + count * APF_PLAYER_STRIDE
    require_range(data, player_table, count * APF_PLAYER_STRIDE, "APF primary player table")
    secondary_count = be_u32(data, 8)
    secondary_pointer = relative_pointer(data, 0x0C, "APF secondary player table", byte_order="big")
    if secondary_pointer != player_end:
        raise RosterError(
            f"APF secondary boundary 0x{secondary_pointer:x} != player end 0x{player_end:x}"
        )
    next_pointer = relative_pointer(data, 0x14, "APF next root table", byte_order="big")
    if next_pointer != player_end:
        raise RosterError(f"APF next table does not share the primary-player end boundary")
    return {
        "schema": CROSS_TITLE_SCHEMA,
        "source": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_order": "big",
        "root_offset": 0,
        "root_size": APF_PLAYER_STRIDE,
        "primary_player_count": count,
        "primary_player_pointer_field": 4,
        "primary_player_offset": player_table,
        "primary_player_stride": APF_PLAYER_STRIDE,
        "primary_player_end": player_end,
        "secondary_player_count": secondary_count,
        "secondary_player_offset": secondary_pointer,
        "validation": {
            "same_biased_field_local_relative_pointer_formula": True,
            "player_table_starts_at_root_end": True,
            "player_table_exactly_bounded_by_next_table": True,
        },
        "scope_note": (
            "This proves a shared root/count/pointer design and the documented 0x54->0x14c "
            "player-record evolution. It does not prove field-for-field record compatibility."
        ),
    }


def corpus_summary(resources: list[dict[str, object]]) -> dict[str, object]:
    labels = Counter(str(resource["label"]) for resource in resources)
    totals = Counter()
    team_kinds = Counter()
    roster_sizes = Counter()
    unique_bodies = set()
    for resource in resources:
        unique_bodies.add(resource["body_sha256"])
        tables = resource["tables"]
        for name, table in tables.items():
            totals[name] += int(table["count"])
        for team in resource["teams"]:
            team_kinds[str(team["team_kind_code"])] += 1
            roster_sizes[str(team["roster_size"])] += 1
    if labels != Counter({"roster": 1, "historic": 75}):
        raise RosterError(f"unexpected ROST label distribution: {dict(labels)}")
    if len(resources) != 76 or len(unique_bodies) != 76:
        raise RosterError("canonical corpus must contain 76 distinct ROST bodies")
    expected_totals = {
        "primary_players": 6454,
        "secondary_players": 68,
        "stadiums": 157,
        "teams": 127,
        "colleges": 266,
        "player_pointer_vector": 241,
        "coaches": 110,
        "team_labels": 36,
        "generated_names": 485,
        "historic_descriptors": 75,
    }
    if dict(totals) != expected_totals:
        raise RosterError(f"unexpected canonical table totals: {dict(totals)}")
    return {
        "resource_count": len(resources),
        "labels": dict(sorted(labels.items())),
        "unique_body_sha256_count": len(unique_bodies),
        "table_totals": dict(totals),
        "player_total": totals["primary_players"] + totals["secondary_players"],
        "team_kind_codes": dict(sorted(team_kinds.items(), key=lambda item: int(item[0]))),
        "team_roster_sizes": dict(sorted(roster_sizes.items(), key=lambda item: int(item[0]))),
    }


def write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def resource_rows(resources: list[dict[str, object]]) -> Iterable[dict[str, object]]:
    for resource in resources:
        tables = resource["tables"]
        yield {
            "outer_index": resource["outer_index"], "outer_id": resource["outer_id"],
            "label": resource["label"], "body_size": resource["body_size"],
            "body_sha256": resource["body_sha256"],
            **{f"{name}_count": tables[name]["count"] for name in (
                "primary_players", "secondary_players", "stadiums", "teams", "colleges",
                "player_pointer_vector", "coaches", "team_labels", "generated_names", "historic_descriptors"
            )},
            "team_names": ";".join(str(team["nickname"]) for team in resource["teams"]),
        }


def team_rows(resources: list[dict[str, object]]) -> Iterable[dict[str, object]]:
    for resource in resources:
        for team in resource["teams"]:
            roster = team["roster"]
            yield {
                "outer_index": resource["outer_index"], "outer_id": resource["outer_id"],
                "resource_label": resource["label"], "team_index": team["index"],
                "nickname": team["nickname"], "abbreviation": team["abbreviation"],
                "asset_code": team["asset_code"], "city": team["city"],
                "city_abbreviation": team["city_abbreviation"],
                "team_kind_code": team["team_kind_code"], "roster_size": team["roster_size"],
                "stadium_index": "" if team["stadium_index"] is None else team["stadium_index"],
                "coach_index": "" if team["coach_index"] is None else team["coach_index"],
                "roster_refs": ";".join(f"{item['pool']}:{item['player_index']}" for item in roster),
                "raw_hex": team["raw_hex"],
            }


def player_rows(resources: list[dict[str, object]]) -> Iterable[dict[str, object]]:
    for resource in resources:
        team_names = {int(team["index"]): str(team["nickname"]) for team in resource["teams"]}
        for player in resource["players"]:
            refs = [int(value) for value in player["team_refs"]]
            yield {
                "outer_index": resource["outer_index"], "outer_id": resource["outer_id"],
                "resource_label": resource["label"], "pool": player["pool"],
                "player_index": player["index"], "record_offset": f"0x{int(player['offset']):x}",
                "first_name": player["first_name"], "last_name": player["last_name"],
                "college_index": "" if player["college_index"] is None else player["college_index"],
                "college_name": "" if player["college_name"] is None else player["college_name"],
                "team_indices": ";".join(str(value) for value in refs),
                "team_names": ";".join(team_names[value] for value in refs),
                "auxiliary_pointer_offset": (
                    "" if player["auxiliary_pointer_offset"] is None
                    else f"0x{int(player['auxiliary_pointer_offset']):x}"
                ),
                "raw_hex": player["raw_hex"],
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to vc_53450030/0")
    parser.add_argument(
        "--inventory", type=Path, default=Path("reports/assets/nfl2k5_resource_chunks_v2.json")
    )
    parser.add_argument("--apf-block", type=Path, help="decoded APF roster.block0.bin for lineage check")
    parser.add_argument("--output", type=Path, help="write canonical JSON report")
    parser.add_argument("--resources-tsv", type=Path)
    parser.add_argument("--teams-tsv", type=Path)
    parser.add_argument("--players-tsv", type=Path)
    args = parser.parse_args(argv)

    archive = parse_archive(args.index)
    records = parse_inventory(args.inventory)
    resources = [parse_resource(archive, record) for record in records]
    summary = corpus_summary(resources)
    report: dict[str, object] = {
        "schema": OUTPUT_SCHEMA,
        "source_index": str(args.index),
        "source_inventory": str(args.inventory),
        "summary": summary,
        "format": {
            "byte_order": "little",
            "wrapper_size": HEADER.size,
            "inner_version": 17,
            "root_offset": 0x40,
            "root_size": NFL_ROOT_SIZE,
            "relative_pointer_formula": "field_offset + signed_stored_value - 1",
            "player_stride": NFL_PLAYER_STRIDE,
            "team_stride": NFL_TEAM_STRIDE,
            "team_roster_pointer_slots": NFL_TEAM_SLOT_COUNT,
        },
        "xex_cross_title": parse_apf_cross_title(args.apf_block) if args.apf_block else None,
        "resources": resources,
        "portme": [
            "PORTME: name and decode the opaque root fields +0x38/+0x3c, +0x40/+0x44, and arenas at +0x64/+0x68/+0x6c.",
            "PORTME: decode the packed gameplay/appearance/ratings fields in each 0x54-byte NFL player record; raw bytes are exported losslessly.",
            "PORTME: prove the semantic roles of player +0x2c and the opaque root +0x28/+0x2c region before exposing a writer.",
            "PORTME: decode remaining stadium, coach, team, and historic-descriptor scalar/bit fields.",
            "PORTME: no roster writer is implemented; safe mutation needs round-trip relocation, allocation, archive hashing, and game validation.",
            "PORTME: APF shares the root/count/relative-pointer design but its 0x14c player fields are not yet mapped field-for-field to NFL's 0x54 layout.",
        ],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")

    resource_fields = [
        "outer_index", "outer_id", "label", "body_size", "body_sha256",
        "primary_players_count", "secondary_players_count", "stadiums_count", "teams_count",
        "colleges_count", "player_pointer_vector_count", "coaches_count", "team_labels_count",
        "generated_names_count", "historic_descriptors_count", "team_names",
    ]
    if args.resources_tsv:
        write_tsv(args.resources_tsv, resource_fields, resource_rows(resources))
    if args.teams_tsv:
        write_tsv(
            args.teams_tsv,
            ["outer_index", "outer_id", "resource_label", "team_index", "nickname",
             "abbreviation", "asset_code", "city", "city_abbreviation", "team_kind_code",
             "roster_size", "stadium_index", "coach_index", "roster_refs", "raw_hex"],
            team_rows(resources),
        )
    if args.players_tsv:
        write_tsv(
            args.players_tsv,
            ["outer_index", "outer_id", "resource_label", "pool", "player_index",
             "record_offset", "first_name", "last_name", "college_index", "college_name",
             "team_indices", "team_names", "auxiliary_pointer_offset", "raw_hex"],
            player_rows(resources),
        )
    print(
        "NFL2K5_ROSTER_PARSE_PASS "
        f"resources={summary['resource_count']} players={summary['player_total']} "
        f"teams={summary['table_totals']['teams']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RosterError, json.JSONDecodeError) as exc:
        print(f"nfl_roster: {exc}", file=sys.stderr)
        raise SystemExit(1)
