#!/usr/bin/env python3
"""Recover APF 2K8 uniform/logo packages and their on-disc team selectors.

The resource names are not guessed from visual similarity.  Canonical XEX
function 0x849D6BD0 supplies twelve UTF-16BE filename templates and maps eleven
selector slots to them.  Each candidate outer name is accepted only when its
uppercase ASCII CRC32 equals an actual archive name ID and its IFF inner-file
signature is exact.

The ROST side is equally strict.  Team field +0xBC must resolve to its matching
root-table-19 record (40 records, stride 0x98).  The first 0x70 bytes are two
14-pointer banks.  Every pointer must resolve to an aligned root-table-17
record (3,724 records, stride 8); the filename consumer reads byte zero.

// PORTME: name selector slots 0, 1, and 13 after direct consumers are found.
// PORTME: name bytes 1..7 of each eight-byte selector record only after exact
//         field consumers or controlled-difference saves prove their roles.
// PORTME: implement TXTR import, H7A recompression, IFF rebuilding, and archive
//         integrity handling before advertising in-place uniform replacement.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable
import zlib

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
import apf_roster


MAX_DECOMPRESSED = 256 * 1024 * 1024
TEAM_CONFIG_POINTER_OFFSET = 0xBC
TEAM_CONFIG_TABLE_INDEX = 19
TEAM_CONFIG_STRIDE = 0x98
SELECTOR_RECORD_TABLE_INDEX = 17
SELECTOR_RECORD_STRIDE = 0x08
SELECTOR_BANK_COUNT = 2
SELECTORS_PER_BANK = 14
SELECTOR_POINTER_BYTES = SELECTOR_BANK_COUNT * SELECTORS_PER_BANK * 4
LOGO_CACHE_OUTER_NAME = "uniform_logocache.iff"
LOGO_CACHE_NAME_ID = 0x1C247977
LOGO_CACHE_TABLE_INDEX = 171
LOGO_CACHE_MAGIC = 0xF0985030
LOGO_CACHE_FILE_COUNT = 236
LOGO_CACHE_DRAM_STRIDE = 0xE0
LOGO_CACHE_VRAM_STRIDE = 0xAC000


class UniformError(ValueError):
    """Raised when archive or roster bytes violate a proved invariant."""


@dataclass(frozen=True)
class FamilySpec:
    key: str
    template: str
    count: int
    selector_slot: int
    expected_files: tuple[tuple[str, str], ...]


FAMILY_SPECS = (
    FamilySpec(
        "font",
        "uniform_font_{0:D2}.iff",
        11,
        7,
        (("font_albedo", "TXTR"), ("font_metric", "NameFont"),
         ("font_normal", "TXTR")),
    ),
    FamilySpec(
        "number",
        "uniform_number_{0:D2}.iff",
        24,
        8,
        tuple(
            (f"number_{digit}_{kind}", "TXTR")
            for digit in range(10)
            for kind in ("color", "normal")
        ) + (("uniform", "NumberFont"),),
    ),
    FamilySpec(
        "sock",
        "uniform_sock_{0:D2}.iff",
        24,
        12,
        (("sock_color", "TXTR"), ("sock_normal", "TXTR")),
    ),
    FamilySpec(
        "shoe",
        "uniform_shoe_{0:D2}.iff",
        11,
        10,
        (("shoe_color", "TXTR"), ("shoe_normal", "TXTR")),
    ),
    FamilySpec(
        "glove",
        "uniform_glove_{0:D2}.iff",
        3,
        2,
        (("glove_color", "TXTR"), ("glove_normal", "TXTR")),
    ),
    FamilySpec(
        "textlogo",
        "uniform_textlogo_{0:D2}.iff",
        206,
        6,
        (("textlogo_color", "TXTR"),),
    ),
    FamilySpec(
        "logo",
        "uniform_logo_{0:D2}.iff",
        118,
        5,
        (("logo_l0", "TXTR"), ("logo_l1", "TXTR")),
    ),
    FamilySpec(
        "helmet",
        "uniform_helmet_{0:D2}.iff",
        24,
        3,
        (("helmet_color", "TXTR"), ("helmet_normal", "TXTR")),
    ),
    FamilySpec(
        "pants",
        "uniform_pants_{0:D2}.iff",
        24,
        9,
        (("pants_color", "TXTR"), ("pants_heavy_normal", "TXTR"),
         ("pants_light_normal", "TXTR"), ("pants_medium_normal", "TXTR")),
    ),
    FamilySpec(
        "jersey",
        "uniform_jersey_{0:D2}.iff",
        24,
        4,
        (("jersey_color", "TXTR"),),
    ),
    FamilySpec(
        "shoulder",
        "uniform_shoulder_{0:D2}.iff",
        24,
        11,
        (("jersey_regionmap", "TXTR"), ("shoulder_color", "TXTR"),
         ("sideline_player_l0", "TXTR"), ("sideline_player_l1", "TXTR")),
    ),
    FamilySpec(
        "shoulder_normal",
        "uniform_shoulder_normal_{0:D2}.iff",
        24,
        11,
        (("shoulder_normal_x", "TXTR"), ("shoulder_normal_y", "TXTR")),
    ),
)

FAMILY_BY_KEY = {spec.key: spec for spec in FAMILY_SPECS}
FAMILIES_BY_SELECTOR: dict[int, tuple[FamilySpec, ...]] = {
    slot: tuple(spec for spec in FAMILY_SPECS if spec.selector_slot == slot)
    for slot in range(SELECTORS_PER_BANK)
}

SELECTOR_SWITCH = {
    2: {"hash": "0x5a37fc45", "families": ["glove"]},
    3: {"hash": "0x7d06eb90", "families": ["helmet"]},
    4: {"hash": "0xe80198f0", "families": ["jersey"]},
    5: {"hash": "0x44bc352d", "families": ["logo"]},
    6: {"hash": "0xe31b6285", "families": ["textlogo"]},
    7: {"hash": "0x70a6a7ec", "families": ["font"]},
    8: {"hash": "0x913c1a62", "families": ["number"]},
    9: {"hash": "0xbdbdd2ee", "families": ["pants"]},
    10: {"hash": "0x61850777", "families": ["shoe"]},
    11: {
        "hashes": ["0x56ed5f4b", "0xb5d10480"],
        "families": ["shoulder", "shoulder_normal"],
    },
    12: {"hash": "0x2fc773f9", "families": ["sock"]},
}

SAMPLE_INNER_NAMES = {
    "logo": "logo_l0",
    "textlogo": "textlogo_color",
    "jersey": "jersey_color",
    "pants": "pants_color",
    "shoulder": "shoulder_color",
    "number": "number_0_color",
}


def _hex(value: int, width: int = 8) -> str:
    return f"0x{value:0{width}x}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _outer_name(spec: FamilySpec, index: int) -> str:
    # The XEX formatter's D2 token is a minimum width, not a two-digit cap.
    return spec.template.replace("{0:D2}", f"{index:02d}")


def _outer_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("ascii")) & 0xFFFFFFFF


def _relative_target(data: bytes, field: int, what: str) -> int:
    try:
        target = apf_roster.resolve_relative(data, field, what)
    except apf_roster.RosterError as exc:
        raise UniformError(str(exc)) from exc
    if target is None:
        raise UniformError(f"{what} unexpectedly resolves to null")
    return target


def _table_index(target: int, start: int, stride: int, count: int, what: str) -> int:
    delta = target - start
    if delta < 0 or delta >= count * stride or delta % stride:
        raise UniformError(
            f"{what} target {_hex(target, 6)} is not aligned within "
            f"{count} records at {_hex(start, 6)} stride {_hex(stride, 2)}"
        )
    return delta // stride


def _load_team_selectors(index_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    roster_data, roster_source = apf_roster.load_roster(index_path)
    tables, root = apf_roster.parse_root(roster_data)
    string_pool, _ = apf_roster.parse_string_pool(
        roster_data, root["string_pool_offset"]
    )
    stadiums = apf_roster.parse_stadiums(roster_data, tables[3], string_pool)
    teams, _ = apf_roster.parse_teams(
        roster_data, tables[4], tables[0], tables[3], string_pool, stadiums
    )

    config_table = tables[TEAM_CONFIG_TABLE_INDEX]
    selector_table = tables[SELECTOR_RECORD_TABLE_INDEX]
    if (
        config_table.count != 40
        or config_table.stride != TEAM_CONFIG_STRIDE
        or config_table.storage_length != 40 * TEAM_CONFIG_STRIDE
    ):
        raise UniformError("root table 19 is not the expected 40 x 0x98 config table")
    if (
        selector_table.count != 3724
        or selector_table.stride != SELECTOR_RECORD_STRIDE
        or selector_table.storage_length != 3724 * SELECTOR_RECORD_STRIDE
    ):
        raise UniformError("root table 17 is not the expected 3724 x 8 selector table")
    if SELECTOR_POINTER_BYTES != 0x70:
        raise AssertionError("selector-bank prefix size changed")

    target_set: set[int] = set()
    team_reports: list[dict[str, object]] = []
    for team in teams:
        team_index = int(team["team_index"])
        team_record = tables[4].offset + team_index * apf_roster.TEAM_STRIDE
        config_field = team_record + TEAM_CONFIG_POINTER_OFFSET
        config_target = _relative_target(
            roster_data, config_field, f"team {team_index} uniform-config pointer"
        )
        config_index = _table_index(
            config_target,
            config_table.offset,
            TEAM_CONFIG_STRIDE,
            config_table.count,
            f"team {team_index} uniform config",
        )
        if config_index != team_index:
            raise UniformError(
                f"team {team_index} points to uniform config {config_index}, expected one-to-one"
            )

        banks: list[dict[str, object]] = []
        for bank in range(SELECTOR_BANK_COUNT):
            selectors: list[dict[str, object]] = []
            for slot in range(SELECTORS_PER_BANK):
                pointer_field = config_target + (bank * SELECTORS_PER_BANK + slot) * 4
                target = _relative_target(
                    roster_data,
                    pointer_field,
                    f"team {team_index} bank {bank} selector {slot}",
                )
                record_index = _table_index(
                    target,
                    selector_table.offset,
                    SELECTOR_RECORD_STRIDE,
                    selector_table.count,
                    f"team {team_index} bank {bank} selector {slot}",
                )
                if target in target_set:
                    raise UniformError(
                        f"selector record {_hex(target, 6)} is referenced more than once"
                    )
                target_set.add(target)
                raw = roster_data[target : target + SELECTOR_RECORD_STRIDE]
                if len(raw) != SELECTOR_RECORD_STRIDE:
                    raise UniformError("short selector record")
                asset_index = raw[0]
                families = [spec.key for spec in FAMILIES_BY_SELECTOR.get(slot, ())]
                for family in families:
                    if asset_index >= FAMILY_BY_KEY[family].count:
                        raise UniformError(
                            f"team {team_index} bank {bank} selector {slot} value "
                            f"{asset_index} exceeds {family} catalog"
                        )
                selectors.append(
                    {
                        "slot": slot,
                        "semantic_status": (
                            "filename selector proved by XEX 0x849D6BD0"
                            if families
                            else "unknown; pointer and eight-byte record only are proved"
                        ),
                        "families": families,
                        "pointer_field_offset": _hex(pointer_field, 6),
                        "stored_pointer": _hex(
                            struct.unpack_from(">I", roster_data, pointer_field)[0]
                        ),
                        "selector_record_index": record_index,
                        "selector_record_offset": _hex(target, 6),
                        "asset_index_byte_0": asset_index,
                        "raw_record_hex": raw.hex(),
                        "opaque_bytes_1_7_hex": raw[1:].hex(),
                    }
                )
            banks.append({"bank": bank, "selectors": selectors})
        team_reports.append(
            {
                "team_index": team_index,
                "display_name": team["display_name"],
                "abbreviation": team["abbreviation"],
                "numeric_string_code": team["numeric_string_code"],
                "slot_kind": team["derived_slot_kind"],
                "team_record_offset": _hex(team_record, 6),
                "config_pointer_field_offset": _hex(config_field, 6),
                "config_record_index": config_index,
                "config_record_offset": _hex(config_target, 6),
                "config_raw_sha256": _sha256(
                    roster_data[config_target : config_target + TEAM_CONFIG_STRIDE]
                ),
                "opaque_config_tail_0x70_0x97_hex": roster_data[
                    config_target + 0x70 : config_target + TEAM_CONFIG_STRIDE
                ].hex(),
                "banks": banks,
            }
        )

    if len(target_set) != 40 * 2 * 14:
        raise UniformError("uniform selector pointers are not one-to-one across all teams")
    selector_raw = {
        roster_data[target : target + SELECTOR_RECORD_STRIDE] for target in target_set
    }
    source = {
        **roster_source,
        "team_table_index": 4,
        "team_count": len(teams),
        "team_record_stride": _hex(apf_roster.TEAM_STRIDE, 3),
        "team_config_pointer_offset": _hex(TEAM_CONFIG_POINTER_OFFSET, 2),
        "config_table_index": TEAM_CONFIG_TABLE_INDEX,
        "config_table_offset": _hex(config_table.offset, 6),
        "config_record_count": config_table.count,
        "config_record_stride": _hex(TEAM_CONFIG_STRIDE, 2),
        "selector_table_index": SELECTOR_RECORD_TABLE_INDEX,
        "selector_table_offset": _hex(selector_table.offset, 6),
        "selector_record_count": selector_table.count,
        "selector_record_stride": _hex(SELECTOR_RECORD_STRIDE, 2),
        "referenced_selector_record_count": len(target_set),
        "unique_referenced_selector_record_bytes": len(selector_raw),
    }
    return source, team_reports


def _expected_entries(
    archive: apf_outer.Archive,
) -> dict[tuple[str, int], tuple[FamilySpec, str, int, apf_outer.Entry]]:
    by_id: dict[int, list[apf_outer.Entry]] = defaultdict(list)
    for entry in archive.entries:
        by_id[entry.name_id].append(entry)
    result: dict[tuple[str, int], tuple[FamilySpec, str, int, apf_outer.Entry]] = {}
    seen_entries: set[int] = set()
    for spec in FAMILY_SPECS:
        for index in range(spec.count):
            name = _outer_name(spec, index)
            name_id = _outer_id(name)
            matches = by_id.get(name_id, [])
            if len(matches) != 1:
                raise UniformError(
                    f"{name} CRC32 {_hex(name_id)} has {len(matches)} archive matches"
                )
            entry = matches[0]
            if entry.table_index in seen_entries:
                raise UniformError(f"outer entry {entry.table_index} matches two uniform names")
            seen_entries.add(entry.table_index)
            result[(spec.key, index)] = (spec, name, name_id, entry)
    return result


def _decode_utf16be_z(data: bytes, offset: int, what: str) -> tuple[str, int]:
    if offset < 0 or offset >= len(data) or offset & 1:
        raise UniformError(f"{what} offset {_hex(offset)} is not aligned in bounds")
    end = offset
    while end + 1 < len(data) and data[end : end + 2] != b"\0\0":
        end += 2
    if end + 1 >= len(data):
        raise UniformError(f"unterminated UTF-16BE {what} at {_hex(offset)}")
    try:
        value = data[offset:end].decode("utf-16be")
    except UnicodeDecodeError as exc:
        raise UniformError(f"invalid UTF-16BE {what} at {_hex(offset)}") from exc
    return value, end + 2


def _parse_logo_cache(
    archive: apf_outer.Archive,
    reader: apf_inner.ArchiveReader,
    package_lookup: dict[tuple[str, int], dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    matches = [entry for entry in archive.entries if entry.name_id == LOGO_CACHE_NAME_ID]
    if len(matches) != 1:
        raise UniformError(
            f"{LOGO_CACHE_OUTER_NAME} has {len(matches)} outer archive matches"
        )
    entry = matches[0]
    if entry.table_index != LOGO_CACHE_TABLE_INDEX:
        raise UniformError(
            f"logo cache is outer table {entry.table_index}, expected {LOGO_CACHE_TABLE_INDEX}"
        )
    if _outer_id(LOGO_CACHE_OUTER_NAME) != entry.name_id:
        raise UniformError("logo-cache outer name does not reproduce its stored CRC32")
    raw = reader.read(entry, 0, entry.size)
    if len(raw) < 0x28:
        raise UniformError("logo cache is shorter than its custom header")
    (
        magic,
        header_size,
        file_length,
        zero,
        block_count,
        block_pointer_raw,
        file_count,
        file_pointer_raw,
        auxiliary_pointer_raw,
        cache_name_pointer_raw,
    ) = struct.unpack_from(">10I", raw, 0)
    if magic != LOGO_CACHE_MAGIC:
        raise UniformError(f"logo cache magic is {_hex(magic)}, expected F0985030")
    if header_size != file_length or header_size != 0x2924 or zero != 0:
        raise UniformError("logo cache header/file length or zero field changed")
    if block_count != 2 or file_count != LOGO_CACHE_FILE_COUNT:
        raise UniformError("logo cache does not contain two virtual blocks and 236 files")

    block_table = 0x14 + block_pointer_raw - 1
    file_pointer_table = 0x1C + file_pointer_raw - 1
    auxiliary_pointer_table = 0x20 + auxiliary_pointer_raw - 1
    cache_name_offset = 0x24 + cache_name_pointer_raw - 1
    if block_table != 0x28 or file_pointer_table != 0x68:
        raise UniformError("logo cache block/file pointer tables moved")
    if auxiliary_pointer_table != 0x1688 or cache_name_offset != 0x28F8:
        raise UniformError("logo cache auxiliary/name targets moved")

    virtual_blocks: list[dict[str, object]] = []
    for block_index in range(block_count):
        values = struct.unpack_from(">8I", raw, block_table + block_index * 0x20)
        virtual_blocks.append(
            {
                "block_index": block_index,
                "name_hash": _hex(values[0]),
                "type_hash": _hex(values[1]),
                "unknown_08": values[2],
                "per_texture_uncompressed_stride": values[3],
                "unknown_10": values[4],
                "template_data_offset": _hex(values[5]),
                "per_texture_stored_stride": values[6],
                "indexed": values[7],
            }
        )
    if [int(block["per_texture_uncompressed_stride"]) for block in virtual_blocks] != [
        LOGO_CACHE_DRAM_STRIDE,
        LOGO_CACHE_VRAM_STRIDE,
    ]:
        raise UniformError("logo cache virtual block strides changed")
    if [block["type_hash"] for block in virtual_blocks] != ["0xbb05a9c1", "0x411536d5"]:
        raise UniformError("logo cache virtual blocks are not DRAM/VRAM")

    descriptor_cursor = file_pointer_table + file_count * 4
    descriptors: list[tuple[int, int, int, int, int, int]] = []
    for index in range(file_count):
        pointer_field = file_pointer_table + index * 4
        descriptor = pointer_field + struct.unpack_from(">I", raw, pointer_field)[0] - 1
        if descriptor != descriptor_cursor:
            raise UniformError(f"logo cache file descriptor {index} is not packed")
        file_id, type_hash, offset_count, dram_offset, vram_offset = struct.unpack_from(
            ">5I", raw, descriptor
        )
        if type_hash != 0x5C369069 or offset_count != 2:
            raise UniformError(f"logo cache file descriptor {index} is not TXTR/2-part")
        if dram_offset % LOGO_CACHE_DRAM_STRIDE or vram_offset % LOGO_CACHE_VRAM_STRIDE:
            raise UniformError(f"logo cache file descriptor {index} has unaligned offsets")
        dram_slot = dram_offset // LOGO_CACHE_DRAM_STRIDE
        vram_slot = vram_offset // LOGO_CACHE_VRAM_STRIDE
        if dram_slot != vram_slot:
            raise UniformError(f"logo cache file descriptor {index} block slots disagree")
        descriptors.append(
            (descriptor, file_id, type_hash, offset_count, dram_offset, vram_offset)
        )
        descriptor_cursor += 0x14
    if descriptor_cursor != auxiliary_pointer_table:
        raise UniformError("logo cache file descriptors do not end at auxiliary table")
    aggregate_slots = {
        descriptor[4] // LOGO_CACHE_DRAM_STRIDE for descriptor in descriptors
    }
    if aggregate_slots != set(range(file_count)):
        raise UniformError("logo cache aggregate slots are not a 0..235 permutation")

    auxiliary_cursor = auxiliary_pointer_table + file_count * 4
    auxiliary: list[tuple[int, int, int, int, int]] = []
    previous_end = 0
    for index in range(file_count):
        pointer_field = auxiliary_pointer_table + index * 4
        descriptor = pointer_field + struct.unpack_from(">I", raw, pointer_field)[0] - 1
        if descriptor != auxiliary_cursor:
            raise UniformError(f"logo cache auxiliary descriptor {index} is not packed")
        stream_a, length_a, stream_b, length_b = struct.unpack_from(">4I", raw, descriptor)
        if stream_a != previous_end or stream_b != stream_a + length_a:
            raise UniformError(f"logo cache auxiliary stream {index} is not contiguous")
        if length_a != 0x71:
            raise UniformError(f"logo cache auxiliary DRAM length {index} is not 0x71")
        previous_end = stream_b + length_b
        auxiliary.append((descriptor, stream_a, length_a, stream_b, length_b))
        auxiliary_cursor += 0x10
    if auxiliary_cursor != cache_name_offset:
        raise UniformError("logo cache auxiliary descriptors do not end at cache name")
    cache_name, cache_name_end = _decode_utf16be_z(raw, cache_name_offset, "cache name")
    if cache_name != "uniform_logocache.cdf" or cache_name_end != header_size:
        raise UniformError("logo cache internal CDF name does not end at header boundary")

    if file_length + 8 > len(raw):
        raise UniformError("logo cache has no name footer")
    footer_magic = struct.unpack_from(">I", raw, file_length)[0]
    footer_size = struct.unpack_from("<I", raw, file_length + 4)[0]
    if footer_magic != apf_inner.NAME_FOOTER_MAGIC:
        raise UniformError("logo cache name footer magic changed")
    footer_end = file_length + 8 + footer_size
    if footer_end > len(raw):
        raise UniformError("logo cache name footer extends outside the outer entry")
    names = apf_inner._parse_footer_names(  # type: ignore[attr-defined]
        raw[file_length + 8 : footer_end], file_count
    )
    expected_names = {
        (f"{catalog_index:02d}_logo_l{level}", "TXTR")
        for catalog_index in range(118)
        for level in range(2)
    }
    if set(names) != expected_names or len(set(names)) != file_count:
        raise UniformError("logo cache footer is not the exact 118 x 2 logo catalog")
    if any(raw[footer_end:]):
        raise UniformError("logo cache alignment tail contains nonzero bytes")

    rows: list[dict[str, object]] = []
    for index, ((name, type_name), descriptor, auxiliary_record) in enumerate(
        zip(names, descriptors, auxiliary)
    ):
        descriptor_offset, file_id, type_hash, offset_count, dram_offset, vram_offset = descriptor
        auxiliary_offset, stream_a, length_a, stream_b, length_b = auxiliary_record
        if file_id != zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF:
            raise UniformError(f"logo cache file {index} ID does not match {name}")
        if type_hash != zlib.crc32(type_name.encode("ascii")) & 0xFFFFFFFF:
            raise UniformError(f"logo cache file {index} type hash does not match TXTR")
        if "_logo_l" not in name:
            raise UniformError(f"logo cache filename {name!r} has unknown syntax")
        index_text, level_text = name.split("_logo_l", 1)
        if not index_text.isdigit() or level_text not in ("0", "1"):
            raise UniformError(f"logo cache filename {name!r} has unknown syntax")
        catalog_index = int(index_text)
        level = int(level_text)
        package = package_lookup[("logo", catalog_index)]
        inner_name = f"logo_l{level}"
        inner_matches = [file for file in package["files"] if file["name"] == inner_name]
        if len(inner_matches) != 1:
            raise UniformError(
                f"logo cache {name} does not have one matching catalog package file"
            )
        inner = inner_matches[0]
        rows.append(
            {
                "cache_entry_index": index,
                "cache_name": name,
                "file_id": _hex(file_id),
                "type_name": type_name,
                "descriptor_offset": _hex(descriptor_offset, 4),
                "aggregate_slot": dram_offset // LOGO_CACHE_DRAM_STRIDE,
                "aggregate_dram_offset": _hex(dram_offset),
                "aggregate_vram_offset": _hex(vram_offset),
                "stream_part_a_offset": _hex(stream_a),
                "stream_part_a_length": length_a,
                "stream_part_b_offset": _hex(stream_b),
                "stream_part_b_length": length_b,
                "auxiliary_descriptor_offset": _hex(auxiliary_offset, 4),
                "catalog_index": catalog_index,
                "logo_level": level,
                "package_outer_name": package["outer_name"],
                "package_outer_table_index": package["outer_table_index"],
                "package_outer_sha256": package["outer_stored_sha256"],
                "package_inner_name": inner_name,
                "package_inner_sha256": inner["concatenated_parts_sha256"],
            }
        )

    report = {
        "outer_name": LOGO_CACHE_OUTER_NAME,
        "outer_name_id": _hex(entry.name_id),
        "outer_table_index": entry.table_index,
        "outer_stored_size": entry.size,
        "outer_stored_sha256": _sha256(raw),
        "magic": _hex(magic),
        "format_status": (
            "proved custom logo-cache directory; not a normal FF3BEF94 payload IFF"
        ),
        "header_size": header_size,
        "file_length": file_length,
        "virtual_blocks": virtual_blocks,
        "file_count": file_count,
        "file_pointer_table_offset": _hex(file_pointer_table, 4),
        "file_descriptor_start": _hex(file_pointer_table + file_count * 4, 4),
        "auxiliary_pointer_table_offset": _hex(auxiliary_pointer_table, 4),
        "auxiliary_descriptor_start": _hex(
            auxiliary_pointer_table + file_count * 4, 4
        ),
        "internal_cache_name": cache_name,
        "internal_cache_name_offset": _hex(cache_name_offset, 4),
        "footer_offset": _hex(file_length, 4),
        "footer_payload_size": footer_size,
        "footer_end": _hex(footer_end, 4),
        "zero_alignment_tail_bytes": len(raw) - footer_end,
        "aggregate_slot_count": len(aggregate_slots),
        "contiguous_auxiliary_stream_size": previous_end,
        "entries": rows,
        "portme": [
            "PORTME: identify the F0985030 format's official type name and loader/writer contract.",
            "PORTME: confirm whether the two contiguous auxiliary lengths are compressed DRAM/VRAM stream lengths before assigning codec semantics.",
            "PORTME: reproduce runtime cache construction and invalidation before writing uniform_logocache.iff.",
        ],
    }
    return report, rows


def _part_payloads(
    record: apf_inner.IFFRecord,
    inner: apf_inner.DataFile,
    block_cache: dict[int, bytes],
) -> list[tuple[apf_inner.FilePart, bytes]]:
    payloads: list[tuple[apf_inner.FilePart, bytes]] = []
    for part in inner.parts:
        block = block_cache[part.block_index]
        end = part.offset + part.length
        if end > len(block):
            raise UniformError(
                f"entry {record.entry.table_index} {inner.name}: part exceeds decoded block"
            )
        payloads.append((part, block[part.offset:end]))
    return payloads


def _write_sample_png(
    path: Path,
    metadata: dict[str, object],
    payloads: list[tuple[apf_inner.FilePart, bytes]],
) -> dict[str, object]:
    if len(payloads) >= 2:
        base_data = payloads[1][1]
        base_offset = 0
    else:
        combined = payloads[0][1]
        base_offset = (0xE0 + 0xFFF) // 0x1000 * 0x1000
        base_data = combined[base_offset:]
    try:
        width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, base_data)
    except apf_inner.FormatError:
        # APF's catalog logos use Xenos 4_4_4_4.  Xenia's primary format
        # implementation defines this as R in bits 0..3, G in 4..7, B in
        # 8..11, A in 12..15 (XePackR4G4B4A4UNorm).  Decode that one bounded
        # format locally without broadening apf_inner.py's advertised path.
        if int(metadata["format"]) != 15:
            raise
        if metadata["dimension"] != 1 or metadata["stacked"] or not metadata["tiled"]:
            raise UniformError("4_4_4_4 sample is not a tiled non-stacked 2D texture")
        width = int(metadata["width"])
        height = int(metadata["height"])
        linear = apf_inner._untile_2d(  # type: ignore[attr-defined]
            base_data,
            width,
            height,
            int(metadata["pitch_pixels"]),
            1,
            1,
            2,
        )
        linear = apf_inner._endian_swap(  # type: ignore[attr-defined]
            linear, int(metadata["endianness"])
        )
        selectors = list(metadata["swizzle_components"])
        output = bytearray(width * height * 4)
        for pixel_index in range(width * height):
            value = int.from_bytes(
                linear[pixel_index * 2 : pixel_index * 2 + 2], "little"
            )
            pixel = (
                (value & 0xF) * 17,
                ((value >> 4) & 0xF) * 17,
                ((value >> 8) & 0xF) * 17,
                ((value >> 12) & 0xF) * 17,
            )
            pixel = apf_inner._swizzle_pixel(  # type: ignore[attr-defined]
                pixel, selectors
            )
            output[pixel_index * 4 : pixel_index * 4 + 4] = bytes(pixel)
        rgba = bytes(output)
    apf_inner.write_rgba_png(path, width, height, rgba)
    data = path.read_bytes()
    return {
        "path": path.name,
        "width": width,
        "height": height,
        "base_data_offset_within_selected_part": base_offset,
        "scope": "base mip only; decoded loose PNG proof, not a writer",
        "sha256": _sha256(data),
        "size": len(data),
    }


def _build_inventory(
    index_path: Path,
    sample_dir: Path | None,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    roster_source, teams = _load_team_selectors(index_path)
    archive = apf_outer.parse_archive(index_path)
    expected = _expected_entries(archive)

    # Use team zero, bank zero as a reproducible representative loose-PNG set.
    team_zero_selectors = {
        int(item["slot"]): int(item["asset_index_byte_0"])
        for item in teams[0]["banks"][0]["selectors"]  # type: ignore[index]
    }
    sample_requests: dict[tuple[str, int, str], str] = {}
    if sample_dir is not None:
        for family, inner_name in SAMPLE_INNER_NAMES.items():
            spec = FAMILY_BY_KEY[family]
            asset_index = team_zero_selectors[spec.selector_slot]
            sample_requests[(family, asset_index, inner_name)] = (
                f"team00_bank0_{family}_{asset_index:02d}_{inner_name}.png"
            )

    packages: list[dict[str, object]] = []
    textures: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    total_stored = 0
    total_decoded = 0
    format_counts: Counter[str] = Counter()
    with apf_inner.ArchiveReader(archive) as reader:
        for spec in FAMILY_SPECS:
            expected_signature = sorted(spec.expected_files)
            for index in range(spec.count):
                _, name, name_id, entry = expected[(spec.key, index)]
                record = apf_inner.parse_iff(reader, entry)
                if record.warnings:
                    raise UniformError(
                        f"{name} has IFF warnings: {'; '.join(record.warnings)}"
                    )
                signature = sorted((inner.name or "", inner.type_name or "") for inner in record.files)
                if signature != expected_signature:
                    raise UniformError(
                        f"{name} inner signature differs: {signature!r}"
                    )

                raw_outer = reader.read(entry, 0, entry.size)
                total_stored += len(raw_outer)
                block_cache = {
                    block.descriptor_index: apf_inner.decode_block(
                        reader, record, block.descriptor_index, MAX_DECOMPRESSED
                    )
                    for block in record.blocks
                }
                total_decoded += sum(len(value) for value in block_cache.values())
                files: list[dict[str, object]] = []
                for inner in sorted(record.files, key=lambda item: item.index):
                    payloads = _part_payloads(record, inner, block_cache)
                    part_reports = [
                        {
                            "block_index": part.block_index,
                            "offset": _hex(part.offset),
                            "length": part.length,
                            "sha256": _sha256(payload),
                        }
                        for part, payload in payloads
                    ]
                    file_report: dict[str, object] = {
                        "inner_index": inner.index,
                        "name": inner.name,
                        "type_name": inner.type_name,
                        "file_id": _hex(inner.file_id),
                        "type_hash": _hex(inner.type_hash),
                        "parts": part_reports,
                        "concatenated_parts_sha256": _sha256(
                            b"".join(payload for _, payload in payloads)
                        ),
                    }
                    if inner.type_name == "TXTR":
                        if not payloads:
                            raise UniformError(f"{name}/{inner.name} has no TXTR payload")
                        txtr = apf_inner.parse_txtr_metadata(payloads[0][1])
                        # The embedded VC texture ID is a distinct identity
                        # domain in some packages (notably uniform fonts).
                        # Preserve both values and report equality instead of
                        # imposing a false global alias.
                        txtr["vc_file_id_matches_iff_file_id"] = (
                            int(str(txtr["vc_file_id"]), 16) == inner.file_id
                        )
                        file_report["txtr"] = txtr
                        format_counts[str(txtr["format_name"])] += 1
                        texture_row = {
                            "family": spec.key,
                            "asset_index": index,
                            "outer_name": name,
                            "outer_table_index": entry.table_index,
                            "inner_index": inner.index,
                            "inner_name": inner.name,
                            "file_id": _hex(inner.file_id),
                            "vc_file_id": txtr["vc_file_id"],
                            "vc_file_id_matches_iff_file_id": txtr[
                                "vc_file_id_matches_iff_file_id"
                            ],
                            "width": txtr["width"],
                            "height": txtr["height"],
                            "pitch_pixels": txtr["pitch_pixels"],
                            "format": txtr["format"],
                            "format_name": txtr["format_name"],
                            "endianness_name": txtr["endianness_name"],
                            "tiled": txtr["tiled"],
                            "stacked": txtr["stacked"],
                            "dimension_name": txtr["dimension_name"],
                            "base_data_length": txtr["vc_base_data_length"],
                            "mip_data_length": txtr["vc_mip_data_length"],
                            "concatenated_parts_sha256": file_report[
                                "concatenated_parts_sha256"
                            ],
                            "warnings": "; ".join(txtr["warnings"]),
                        }
                        textures.append(texture_row)
                        request = sample_requests.get((spec.key, index, str(inner.name)))
                        if request is not None and sample_dir is not None:
                            sample_path = sample_dir / request
                            sample = _write_sample_png(sample_path, txtr, payloads)
                            sample.update(
                                {
                                    "team_index": 0,
                                    "team_name": teams[0]["display_name"],
                                    "bank": 0,
                                    "family": spec.key,
                                    "asset_index": index,
                                    "outer_name": name,
                                    "outer_table_index": entry.table_index,
                                    "inner_name": inner.name,
                                }
                            )
                            samples.append(sample)
                    files.append(file_report)

                packages.append(
                    {
                        "family": spec.key,
                        "asset_index": index,
                        "selector_slot": spec.selector_slot,
                        "outer_name": name,
                        "outer_name_hash_rule": "CRC32(uppercase ASCII exact filename)",
                        "computed_name_id": _hex(name_id),
                        "stored_name_id": _hex(entry.name_id),
                        "outer_table_index": entry.table_index,
                        "outer_virtual_offset": _hex(entry.virtual_offset),
                        "outer_stored_size": entry.size,
                        "outer_stored_sha256": _sha256(raw_outer),
                        "segments": [
                            {
                                "pack_name": segment.pack_name,
                                "pack_offset": _hex(segment.pack_offset),
                                "size": segment.size,
                            }
                            for segment in entry.segments
                        ],
                        "iff_header_size": record.header_size,
                        "iff_file_length_excluding_name_footer": record.file_length,
                        "iff_block_count": record.block_count,
                        "iff_file_count": record.file_count,
                        "decoded_blocks": [
                            {
                                "block_index": block.descriptor_index,
                                "memory_type_hash": _hex(block.type_hash),
                                "uncompressed_length": len(
                                    block_cache[block.descriptor_index]
                                ),
                                "sha256": _sha256(
                                    block_cache[block.descriptor_index]
                                ),
                            }
                            for block in record.blocks
                        ],
                        "files": files,
                    }
                )

    if len(samples) != len(sample_requests):
        raise UniformError(
            f"wrote {len(samples)} sample PNGs, expected {len(sample_requests)}"
        )

    package_lookup = {
        (str(package["family"]), int(package["asset_index"])): package
        for package in packages
    }
    with apf_inner.ArchiveReader(archive) as reader:
        logo_cache, logo_cache_rows = _parse_logo_cache(
            archive, reader, package_lookup
        )
    usage: dict[str, Counter[int]] = {spec.key: Counter() for spec in FAMILY_SPECS}
    team_asset_rows: list[dict[str, object]] = []
    known_selector_uses = 0
    known_family_mappings = 0
    for team in teams:
        for bank in team["banks"]:  # type: ignore[assignment]
            for selector in bank["selectors"]:  # type: ignore[index]
                families = list(selector["families"])
                asset_index = int(selector["asset_index_byte_0"])
                package_names: list[str] = []
                package_table_indices: list[str] = []
                if families:
                    known_selector_uses += 1
                for family in families:
                    package = package_lookup[(str(family), asset_index)]
                    package_names.append(str(package["outer_name"]))
                    package_table_indices.append(str(package["outer_table_index"]))
                    usage[str(family)][asset_index] += 1
                    known_family_mappings += 1
                team_asset_rows.append(
                    {
                        "team_index": team["team_index"],
                        "team_name": team["display_name"],
                        "abbreviation": team["abbreviation"],
                        "slot_kind": team["slot_kind"],
                        "bank": bank["bank"],
                        "selector_slot": selector["slot"],
                        "semantic_status": selector["semantic_status"],
                        "families": ";".join(str(value) for value in families),
                        "asset_index_byte_0": asset_index,
                        "package_names": ";".join(package_names),
                        "package_outer_table_indices": ";".join(package_table_indices),
                        "selector_record_index": selector["selector_record_index"],
                        "selector_record_offset": selector["selector_record_offset"],
                        "raw_record_hex": selector["raw_record_hex"],
                        "opaque_bytes_1_7_hex": selector["opaque_bytes_1_7_hex"],
                    }
                )

    for package in packages:
        family = str(package["family"])
        asset_index = int(package["asset_index"])
        package["on_disc_team_bank_use_count"] = usage[family][asset_index]

    same_asset_index_bank_teams = 0
    identical_corresponding_selector_records = 0
    differing_selector_records_by_slot: Counter[int] = Counter()
    for team in teams:
        bank_zero = team["banks"][0]["selectors"]  # type: ignore[index]
        bank_one = team["banks"][1]["selectors"]  # type: ignore[index]
        if [item["asset_index_byte_0"] for item in bank_zero] == [
            item["asset_index_byte_0"] for item in bank_one
        ]:
            same_asset_index_bank_teams += 1
        for slot in range(SELECTORS_PER_BANK):
            if bank_zero[slot]["raw_record_hex"] == bank_one[slot]["raw_record_hex"]:
                identical_corresponding_selector_records += 1
            else:
                differing_selector_records_by_slot[slot] += 1

    summary = {
        "family_count": len(FAMILY_SPECS),
        "uniform_package_count": len(packages),
        "uniform_related_outer_resource_count": len(packages) + 1,
        "logo_cache_directory_count": 1,
        "logo_cache_entry_count": len(logo_cache_rows),
        "logo_cache_aggregate_slot_count": logo_cache["aggregate_slot_count"],
        "logo_cache_contiguous_auxiliary_stream_size": logo_cache[
            "contiguous_auxiliary_stream_size"
        ],
        "inner_file_count": sum(len(package["files"]) for package in packages),
        "txtr_count": len(textures),
        "txtr_vc_id_matches_iff_file_id": sum(
            bool(texture["vc_file_id_matches_iff_file_id"]) for texture in textures
        ),
        "txtr_vc_id_differs_from_iff_file_id": sum(
            not bool(texture["vc_file_id_matches_iff_file_id"])
            for texture in textures
        ),
        "non_txtr_inner_file_count": sum(
            sum(file["type_name"] != "TXTR" for file in package["files"])
            for package in packages
        ),
        "outer_stored_bytes": total_stored,
        "decoded_block_bytes": total_decoded,
        "texture_format_counts": dict(sorted(format_counts.items())),
        "team_count": len(teams),
        "built_in_team_count": sum(team["slot_kind"] == "built_in_team" for team in teams),
        "team_config_record_count": len(teams),
        "selector_bank_count": len(teams) * SELECTOR_BANK_COUNT,
        "selector_pointer_use_count": len(team_asset_rows),
        "teams_with_identical_bank_asset_index_vectors": same_asset_index_bank_teams,
        "corresponding_bank_selector_record_pair_count": (
            len(teams) * SELECTORS_PER_BANK
        ),
        "identical_corresponding_bank_selector_record_pairs": (
            identical_corresponding_selector_records
        ),
        "different_corresponding_bank_selector_record_pairs": (
            len(teams) * SELECTORS_PER_BANK
            - identical_corresponding_selector_records
        ),
        "different_corresponding_bank_records_by_slot": {
            str(slot): differing_selector_records_by_slot[slot]
            for slot in range(SELECTORS_PER_BANK)
            if differing_selector_records_by_slot[slot]
        },
        "known_filename_selector_use_count": known_selector_uses,
        "known_family_package_mapping_count": known_family_mappings,
        "unique_referenced_selector_record_count": roster_source[
            "referenced_selector_record_count"
        ],
        "unique_referenced_selector_record_bytes": roster_source[
            "unique_referenced_selector_record_bytes"
        ],
        "sample_png_count": len(samples),
    }

    report = {
        "schema": "apf_uniform_inventory/v1",
        "source": {
            "archive_index": str(index_path),
            "archive_volume_sizes": {
                pack.path.name: pack.path.stat().st_size for pack in archive.packs
            },
            "roster": roster_source,
        },
        "xex_evidence": {
            "filename_selector": "0x849D6BD0",
            "direct_bank_accessor": "0x84687D88: return config[slot]",
            "alternate_bank_accessor": "0x847080C8: return config[slot + 14]",
            "active_team_installers": ["0x846826E8", "0x84682750", "0x8470F6A0"],
            "roster_team_accessor": "0x84746F78: team_base + index * 0x180",
            "frontend_cache_registration": (
                "0x8467C978 registers uniform_logocache.iff with hash 0x6800C2FF"
            ),
            "selector_switch": {str(key): value for key, value in SELECTOR_SWITCH.items()},
        },
        "family_specs": [
            {
                "family": spec.key,
                "xex_template": spec.template,
                "catalog_count": spec.count,
                "selector_slot": spec.selector_slot,
                "expected_inner_signature": [
                    {"name": name, "type": type_name}
                    for name, type_name in sorted(spec.expected_files)
                ],
                "referenced_asset_indices": sorted(usage[spec.key]),
                "unreferenced_catalog_asset_indices": [
                    index for index in range(spec.count) if not usage[spec.key][index]
                ],
            }
            for spec in FAMILY_SPECS
        ],
        "team_selector_graph": {
            "pointer_rule": "target = pointer_field_offset + signed_be32(stored) - 1",
            "config_prefix_layout": (
                "bank 0: 14 rel32be pointers at +0x00; bank 1: 14 rel32be "
                "pointers at +0x38; opaque tail +0x70..+0x97"
            ),
            "selector_record_layout": (
                "8 bytes; byte 0 is filename asset index for slots 2..12; "
                "bytes 1..7 remain opaque"
            ),
            "teams": teams,
        },
        "packages": packages,
        "logo_cache": logo_cache,
        "representative_loose_pngs": sorted(samples, key=lambda value: str(value["path"])),
        "summary": summary,
        "portme": [
            "PORTME: identify direct consumers and meanings of selector slots 0, 1, and 13.",
            "PORTME: identify bytes 1..7 of each eight-byte selector record; preserve them unchanged meanwhile.",
            "PORTME: identify the 0x28-byte tail of each 0x98-byte config record.",
            "PORTME: map the two selector banks to user-facing home/away labels only after a direct game-state consumer proves orientation.",
            "PORTME: implement TXTR import, mip generation, Xenos tiling/endian/channel encoding, IFF rebuild, H7A compression, and outer-volume integrity handling.",
            "PORTME: determine uniform_logocache.iff runtime cache layout and write lifecycle before replacing it.",
        ],
    }
    return report, packages, textures, team_asset_rows, logo_cache_rows


def _write_json(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to extracted APF 0A volume")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--packages-tsv", type=Path, required=True)
    parser.add_argument("--textures-tsv", type=Path, required=True)
    parser.add_argument("--team-assets-tsv", type=Path, required=True)
    parser.add_argument("--logo-cache-tsv", type=Path, required=True)
    parser.add_argument(
        "--sample-dir",
        type=Path,
        help="optional destination for six proved base-mip loose PNG samples",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report, packages, textures, team_asset_rows, logo_cache_rows = _build_inventory(
            args.index, args.sample_dir
        )
        _write_json(args.report, report)
        _write_tsv(
            args.packages_tsv,
            packages,
            [
                "family", "asset_index", "selector_slot", "outer_name",
                "stored_name_id", "outer_table_index", "outer_virtual_offset",
                "outer_stored_size", "outer_stored_sha256", "iff_block_count",
                "iff_file_count", "on_disc_team_bank_use_count",
            ],
        )
        _write_tsv(
            args.textures_tsv,
            textures,
            [
                "family", "asset_index", "outer_name", "outer_table_index",
                "inner_index", "inner_name", "file_id", "vc_file_id",
                "vc_file_id_matches_iff_file_id", "width", "height",
                "pitch_pixels", "format", "format_name", "endianness_name",
                "tiled", "stacked", "dimension_name", "base_data_length",
                "mip_data_length", "concatenated_parts_sha256", "warnings",
            ],
        )
        _write_tsv(
            args.team_assets_tsv,
            team_asset_rows,
            [
                "team_index", "team_name", "abbreviation", "slot_kind", "bank",
                "selector_slot", "semantic_status", "families",
                "asset_index_byte_0", "package_names",
                "package_outer_table_indices", "selector_record_index",
                "selector_record_offset", "raw_record_hex", "opaque_bytes_1_7_hex",
            ],
        )
        _write_tsv(
            args.logo_cache_tsv,
            logo_cache_rows,
            [
                "cache_entry_index", "cache_name", "file_id", "type_name",
                "descriptor_offset", "aggregate_slot", "aggregate_dram_offset",
                "aggregate_vram_offset", "stream_part_a_offset",
                "stream_part_a_length", "stream_part_b_offset",
                "stream_part_b_length", "auxiliary_descriptor_offset",
                "catalog_index", "logo_level", "package_outer_name",
                "package_outer_table_index", "package_outer_sha256",
                "package_inner_name", "package_inner_sha256",
            ],
        )
    except (UniformError, apf_inner.FormatError, apf_outer.FormatError,
            apf_roster.RosterError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        "APF uniform inventory: "
        f"{summary['uniform_package_count']} packages + logo cache, "
        f"{summary['txtr_count']} TXTR, {summary['team_count']} teams, "
        f"{summary['selector_pointer_use_count']} selector pointers, "
        f"{summary['sample_png_count']} PNG samples"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
