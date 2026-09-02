#!/usr/bin/env python3
"""Strict cross-title inventory for Visual Concepts DRCT director resources.

The NFL 2K5 executable proves a relocated graph containing a fixed slot table,
counted record packages, an indexed opaque instruction directory, and a UTF-16
string directory.  APF 2K8 preserves that graph in big-endian form, widens the
fixed table, and adds one opaque auxiliary directory/tail.  This tool preserves
all decoded bytes and parses only those relationships; it deliberately provides
no writer and does not assign meanings to instruction opcodes or record fields.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct
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
from nfl_outer import parse_archive as parse_nfl_archive
from nfl_outer import read_entry_range
from nfl_scene_probe import ProbeError, ResourceRecord, decode_resource, parse_inventory


SCHEMA = "vc_cross_title_director_inventory/v1"
NFL_FIXED_SLOT_COUNT = 193
APF_FIXED_SLOT_COUNT = 217
MAX_COUNT = 1_000_000
DRCT_HASH = zlib.crc32(b"DRCT") & 0xFFFFFFFF
DIRECTOR_HASH = zlib.crc32(b"director") & 0xFFFFFFFF

ROLE_ORDER = ("ingame", "wrapup", "tutorial", "intro", "halftime")
NFL_ROLES = {
    4: "ingame",
    19: "wrapup",
    345: "tutorial",
    1194: "intro",
    1195: "halftime",
}
APF_ROLES = {
    153: ("ingame", "dir_ingame.iff"),
    265: ("wrapup", "dir_wrapup.iff"),
    553: ("tutorial", "dir_tutorial.iff"),
    681: ("halftime", "dir_halftime.iff"),
    1071: ("intro", "dir_intro.iff"),
}
APF_BODY_LENGTHS = {
    153: 402080,
    265: 36912,
    553: 38752,
    681: 33920,
    1071: 50272,
}
NFL_BODY_LENGTHS = {
    4: 505568,
    19: 36160,
    345: 38736,
    1194: 73680,
    1195: 29168,
}


class DirectorError(ValueError):
    """A declared DRCT relationship is malformed or out of bounds."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked(data: bytes, offset: int, size: int, what: str) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise DirectorError(
            f"{what}: range 0x{offset:x}+0x{size:x} exceeds 0x{len(data):x}"
        )
    return data[offset : offset + size]


def u16(data: bytes, offset: int, endian: str, what: str) -> int:
    checked(data, offset, 2, what)
    return struct.unpack_from(endian + "H", data, offset)[0]


def u32(data: bytes, offset: int, endian: str, what: str) -> int:
    checked(data, offset, 4, what)
    return struct.unpack_from(endian + "I", data, offset)[0]


def i32(data: bytes, offset: int, endian: str, what: str) -> int:
    checked(data, offset, 4, what)
    return struct.unpack_from(endian + "i", data, offset)[0]


def resolve_relative(
    data: bytes,
    field_offset: int,
    endian: str,
    what: str,
    *,
    nullable: bool = True,
) -> int | None:
    stored = i32(data, field_offset, endian, what)
    if stored == 0 and nullable:
        return None
    target = field_offset - 1 + stored
    if not 0 <= target < len(data):
        raise DirectorError(
            f"{what}: reference {stored:+#x} at 0x{field_offset:x} resolves "
            f"to 0x{target:x}, outside 0x{len(data):x} bytes"
        )
    return target


def pointer_document(
    data: bytes,
    field_offset: int,
    endian: str,
    what: str,
    *,
    nullable: bool = True,
) -> dict[str, object]:
    stored = u32(data, field_offset, endian, what)
    target = resolve_relative(
        data, field_offset, endian, what, nullable=nullable
    )
    return {
        "field_offset": field_offset,
        "stored_reference": f"0x{stored:08x}",
        "target_offset": target,
    }


def utf16z(
    data: bytes, offset: int, encoding: str, what: str
) -> tuple[str, int]:
    if offset < 0 or offset + 2 > len(data):
        raise DirectorError(f"{what}: invalid UTF-16 offset 0x{offset:x}")
    cursor = offset
    while cursor + 2 <= len(data):
        if data[cursor : cursor + 2] == b"\0\0":
            try:
                value = data[offset:cursor].decode(encoding)
            except UnicodeDecodeError as exc:
                raise DirectorError(
                    f"{what}: invalid {encoding} at 0x{offset:x}"
                ) from exc
            if any(ord(character) < 9 or 13 < ord(character) < 32 for character in value):
                raise DirectorError(f"{what}: contains unsupported control characters")
            return value, cursor + 2
        cursor += 2
    raise DirectorError(f"{what}: unterminated UTF-16 string at 0x{offset:x}")


def raw_document(data: bytes, offset: int, size: int) -> dict[str, object]:
    raw = checked(data, offset, size, "raw region")
    return {
        "offset": offset,
        "size": size,
        "sha256": sha256_bytes(raw),
        "raw_hex": raw.hex(),
    }


def raw_region(
    data: bytes, start: int, end: int, kind: str
) -> dict[str, object]:
    if end < start:
        raise DirectorError(f"{kind}: inverted region 0x{start:x}..0x{end:x}")
    result = {"kind": kind, **raw_document(data, start, end - start)}
    result["all_zero"] = not any(data[start:end])
    return result


def parse_graph(
    data: bytes,
    *,
    platform: str,
    role: str,
    endian: str,
    encoding: str,
    instruction_count: int,
    instruction_pointer_fields_offset: int,
    fixed_table_offset: int,
    fixed_slot_count: int,
    string_count: int,
    string_directory_offset: int,
    primary_region_end: int | None,
) -> dict[str, object]:
    identity = f"{platform} {role}"
    if not 0 < instruction_count <= MAX_COUNT:
        raise DirectorError(
            f"{identity}: invalid instruction-record count {instruction_count}"
        )
    if not 0 <= string_count <= MAX_COUNT:
        raise DirectorError(f"{identity}: invalid string count {string_count}")
    instruction_pointer_fields_end = (
        instruction_pointer_fields_offset + instruction_count * 4
    )
    if instruction_pointer_fields_end != fixed_table_offset:
        raise DirectorError(
            f"{identity}: instruction directory ends at "
            f"0x{instruction_pointer_fields_end:x}, fixed table begins at "
            f"0x{fixed_table_offset:x}"
        )

    fixed_table_end = fixed_table_offset + fixed_slot_count * 4
    checked(data, fixed_table_offset, fixed_slot_count * 4, "fixed slot table")
    fixed_slots: list[dict[str, object]] = []
    fixed_nonnull: list[tuple[int, int]] = []
    for slot_index in range(fixed_slot_count):
        field = fixed_table_offset + slot_index * 4
        pointer = pointer_document(
            data, field, endian, f"{identity} fixed slot {slot_index}"
        )
        pointer["slot_index"] = slot_index
        fixed_slots.append(pointer)
        target = pointer["target_offset"]
        if target is not None:
            fixed_nonnull.append((slot_index, int(target)))
    fixed_targets = [target for _slot, target in fixed_nonnull]
    if not fixed_targets:
        raise DirectorError(f"{identity}: fixed table has no records")
    if len(fixed_targets) != len(set(fixed_targets)):
        raise DirectorError(f"{identity}: fixed table aliases a record target")
    if fixed_targets != sorted(fixed_targets):
        raise DirectorError(f"{identity}: fixed record targets are not monotonic")
    if fixed_targets[0] != fixed_table_end:
        raise DirectorError(
            f"{identity}: first record is 0x{fixed_targets[0]:x}, expected "
            f"fixed-table end 0x{fixed_table_end:x}"
        )

    instruction_pointers: list[dict[str, object]] = []
    instruction_targets: list[int] = []
    for index in range(instruction_count):
        field = instruction_pointer_fields_offset + index * 4
        pointer = pointer_document(
            data,
            field,
            endian,
            f"{identity} instruction pointer {index}",
            nullable=False,
        )
        pointer["index"] = index
        instruction_pointers.append(pointer)
        instruction_targets.append(int(pointer["target_offset"]))
    if len(instruction_targets) != len(set(instruction_targets)):
        raise DirectorError(f"{identity}: instruction targets are not unique")
    if instruction_targets != sorted(instruction_targets):
        raise DirectorError(f"{identity}: instruction targets are not monotonic")
    if instruction_targets[0] <= fixed_targets[-1]:
        raise DirectorError(f"{identity}: instruction records overlap fixed records")
    if instruction_targets[-1] >= string_directory_offset:
        raise DirectorError(f"{identity}: instruction records overlap strings")

    fixed_records: list[dict[str, object]] = []
    for ordinal, (slot_index, offset) in enumerate(fixed_nonnull):
        package_end = (
            fixed_nonnull[ordinal + 1][1]
            if ordinal + 1 < len(fixed_nonnull)
            else instruction_targets[0]
        )
        if offset + 0x1C > package_end:
            raise DirectorError(f"{identity}: fixed record {slot_index} is truncated")
        child_count = u32(data, offset, endian, "fixed-record child count")
        if child_count > MAX_COUNT:
            raise DirectorError(
                f"{identity}: fixed record {slot_index} child count {child_count}"
            )
        child_fields_end = offset + 0x1C + child_count * 4
        if child_fields_end > package_end:
            raise DirectorError(
                f"{identity}: fixed record {slot_index} child directory exceeds package"
            )
        pointers: list[dict[str, object]] = []
        for relative_offset in (0x08, 0x0C, 0x10, 0x14, 0x18):
            pointer = pointer_document(
                data,
                offset + relative_offset,
                endian,
                f"{identity} fixed record {slot_index} +0x{relative_offset:x}",
            )
            pointer["record_relative_offset"] = relative_offset
            pointers.append(pointer)
        children: list[dict[str, object]] = []
        for child_index in range(child_count):
            field = offset + 0x1C + child_index * 4
            pointer = pointer_document(
                data,
                field,
                endian,
                f"{identity} fixed record {slot_index} child {child_index}",
            )
            pointer["child_index"] = child_index
            children.append(pointer)
        for pointer in pointers + children:
            target = pointer["target_offset"]
            if target is not None and not offset <= int(target) < package_end:
                raise DirectorError(
                    f"{identity}: fixed record {slot_index} target "
                    f"0x{int(target):x} leaves package "
                    f"0x{offset:x}..0x{package_end:x}"
                )
        fixed_records.append(
            {
                "ordinal": ordinal,
                "slot_index": slot_index,
                "offset": offset,
                "package_end": package_end,
                "package_size": package_end - offset,
                "child_count": child_count,
                "unknown_u16_04": u16(data, offset + 4, endian, "record +4"),
                "unknown_u16_06": u16(data, offset + 6, endian, "record +6"),
                "pointer_fields": pointers,
                "child_references": children,
                "raw_header_hex": data[offset : offset + 0x1C].hex(),
                "raw_child_directory_hex": data[
                    offset + 0x1C : child_fields_end
                ].hex(),
                "package_sha256": sha256_bytes(data[offset:package_end]),
                "package_raw_hex": data[offset:package_end].hex(),
            }
        )

    instructions: list[dict[str, object]] = []
    for index, offset in enumerate(instruction_targets):
        end = (
            instruction_targets[index + 1]
            if index + 1 < len(instruction_targets)
            else string_directory_offset
        )
        if end <= offset:
            raise DirectorError(f"{identity}: empty instruction record {index}")
        raw = data[offset:end]
        instructions.append(
            {
                "index": index,
                "pointer_field_offset": instruction_pointer_fields_offset + index * 4,
                "stored_reference": instruction_pointers[index]["stored_reference"],
                "offset": offset,
                "end_offset": end,
                "size": len(raw),
                "first_byte": raw[0],
                "head_hex": raw[:16].hex(),
                "sha256": sha256_bytes(raw),
                "raw_hex": raw.hex(),
            }
        )

    string_directory_end = string_directory_offset + string_count * 4
    checked(data, string_directory_offset, string_count * 4, "string directory")
    strings: list[dict[str, object]] = []
    expected_target = string_directory_end
    for index in range(string_count):
        field = string_directory_offset + index * 4
        pointer = pointer_document(
            data,
            field,
            endian,
            f"{identity} string pointer {index}",
            nullable=False,
        )
        target = int(pointer["target_offset"])
        if target != expected_target:
            raise DirectorError(
                f"{identity}: string {index} starts at 0x{target:x}, expected "
                f"sequential target 0x{expected_target:x}"
            )
        text, end = utf16z(data, target, encoding, f"{identity} string {index}")
        raw = data[target:end]
        strings.append(
            {
                "index": index,
                "pointer_field_offset": field,
                "stored_reference": pointer["stored_reference"],
                "offset": target,
                "end_offset": end,
                "size": len(raw),
                "text": text,
                "sha256": sha256_bytes(raw),
                "raw_hex": raw.hex(),
            }
        )
        expected_target = end
    string_pool_end = expected_target
    if primary_region_end is not None and string_pool_end != primary_region_end:
        raise DirectorError(
            f"{identity}: primary string region ends at 0x{string_pool_end:x}, "
            f"expected 0x{primary_region_end:x}"
        )

    return {
        "fixed_table_offset": fixed_table_offset,
        "fixed_slot_count": fixed_slot_count,
        "fixed_table_end": fixed_table_end,
        "nonnull_fixed_record_count": len(fixed_records),
        "fixed_slots": fixed_slots,
        "fixed_records": fixed_records,
        "instruction_pointer_fields_offset": instruction_pointer_fields_offset,
        "instruction_pointer_fields_end": instruction_pointer_fields_end,
        "instruction_count": instruction_count,
        "instruction_records_offset": instruction_targets[0],
        "instruction_records_end": string_directory_offset,
        "instructions": instructions,
        "string_directory_offset": string_directory_offset,
        "string_directory_end": string_directory_end,
        "string_count": string_count,
        "string_pool_offset": string_directory_end,
        "string_pool_end": string_pool_end,
        "strings": strings,
    }


def validate_partition(data: bytes, regions: list[dict[str, object]], what: str) -> None:
    cursor = 0
    for region in regions:
        if int(region["offset"]) != cursor:
            raise DirectorError(
                f"{what}: raw partition gap/overlap at 0x{cursor:x} before "
                f"{region['kind']}"
            )
        cursor += int(region["size"])
    if cursor != len(data):
        raise DirectorError(
            f"{what}: raw partition ends at 0x{cursor:x}, body is 0x{len(data):x}"
        )


def parse_nfl_body(data: bytes, resource: ResourceRecord) -> dict[str, object]:
    role = NFL_ROLES.get(resource.outer_index)
    if role is None:
        raise DirectorError(f"unexpected NFL DRCT outer index {resource.outer_index}")
    identity = f"NFL outer {resource.outer_index} ({role})"
    if len(data) != NFL_BODY_LENGTHS[resource.outer_index]:
        raise DirectorError(
            f"{identity}: body 0x{len(data):x}, expected "
            f"0x{NFL_BODY_LENGTHS[resource.outer_index]:x}"
        )
    if data[:0x0C] != b"\0" * 0x0C or data[0x0C:0x10] != b"DRCT":
        raise DirectorError(f"{identity}: common header marker differs")
    name_pointer = pointer_document(
        data, 0x10, "<", f"{identity} name", nullable=False
    )
    root_pointer = pointer_document(
        data, 0x14, "<", f"{identity} root", nullable=False
    )
    if name_pointer["target_offset"] != 0x20 or root_pointer["target_offset"] != 0x40:
        raise DirectorError(f"{identity}: common name/root targets differ")
    name, name_end = utf16z(data, 0x20, "utf-16le", f"{identity} name")
    if name != "director" or any(data[name_end:0x40]):
        raise DirectorError(f"{identity}: expected director name and zero padding")
    if any(data[0x18:0x20]):
        raise DirectorError(f"{identity}: common header reserved words are nonzero")

    root = 0x40
    instruction_count = u16(data, root + 2, "<", "NFL instruction count")
    string_count = u32(data, root + 8, "<", "NFL string count")
    string_directory = pointer_document(
        data, root + 0x0C, "<", f"{identity} string directory", nullable=False
    )
    fixed_table = pointer_document(
        data, root + 0x10, "<", f"{identity} fixed table", nullable=False
    )
    graph = parse_graph(
        data,
        platform="nfl2k5",
        role=role,
        endian="<",
        encoding="utf-16le",
        instruction_count=instruction_count,
        instruction_pointer_fields_offset=root + 0x14,
        fixed_table_offset=int(fixed_table["target_offset"]),
        fixed_slot_count=NFL_FIXED_SLOT_COUNT,
        string_count=string_count,
        string_directory_offset=int(string_directory["target_offset"]),
        primary_region_end=None,
    )
    regions = [
        raw_region(data, 0, root, "common_header"),
        raw_region(data, root, int(graph["fixed_table_end"]), "root_and_pointer_directories"),
        raw_region(
            data,
            int(graph["fixed_table_end"]),
            int(graph["instruction_records_offset"]),
            "fixed_record_packages",
        ),
        raw_region(
            data,
            int(graph["instruction_records_offset"]),
            int(graph["instruction_records_end"]),
            "opaque_instruction_records",
        ),
        raw_region(
            data,
            int(graph["string_directory_offset"]),
            int(graph["string_pool_end"]),
            "primary_string_directory_and_pool",
        ),
        raw_region(
            data,
            int(graph["string_pool_end"]),
            len(data),
            "trailing_padding",
        ),
    ]
    validate_partition(data, regions, identity)
    if not regions[-1]["all_zero"]:
        raise DirectorError(f"{identity}: trailing padding is nonzero")
    return {
        "platform": "nfl2k5",
        "role": role,
        "outer_index": resource.outer_index,
        "inner_index": resource.chunk_index,
        "outer_id": resource.outer_id,
        "resource_name": name,
        "byte_size": len(data),
        "sha256": sha256_bytes(data),
        "endianness": "little",
        "encoding": "UTF-16LE",
        "common_header": {
            "offset": 0,
            "size": root,
            "raw_hex": data[:root].hex(),
            "name_pointer": name_pointer,
            "root_pointer": root_pointer,
        },
        "root": {
            "offset": root,
            "raw_prefix_hex": data[root : root + 0x14].hex(),
            "unknown_u8_00": data[root],
            "unknown_u8_01": data[root + 1],
            "instruction_count_u16_02": instruction_count,
            "unknown_u16_04": u16(data, root + 4, "<", "root +4"),
            "unknown_u16_06": u16(data, root + 6, "<", "root +6"),
            "primary_string_count_u32_08": string_count,
            "primary_string_directory_pointer_0c": string_directory,
            "fixed_slot_table_pointer_10": fixed_table,
            "instruction_pointer_fields_offset_14": root + 0x14,
        },
        "graph": graph,
        "raw_partition": regions,
    }


def parse_apf_body(
    data: bytes,
    outer_index: int,
    inner_index: int,
    outer_id: int,
) -> dict[str, object]:
    if outer_index not in APF_ROLES:
        raise DirectorError(f"unexpected APF DRCT outer index {outer_index}")
    role, outer_name = APF_ROLES[outer_index]
    identity = f"APF {outer_index}:{inner_index} ({role})"
    if len(data) != APF_BODY_LENGTHS[outer_index]:
        raise DirectorError(
            f"{identity}: body 0x{len(data):x}, expected "
            f"0x{APF_BODY_LENGTHS[outer_index]:x}"
        )
    expected_outer_id = zlib.crc32(outer_name.upper().encode("ascii")) & 0xFFFFFFFF
    if outer_id != expected_outer_id:
        raise DirectorError(
            f"{identity}: outer ID 0x{outer_id:08x}, expected uppercase-name "
            f"CRC32 0x{expected_outer_id:08x}"
        )

    instruction_count = u16(data, 6, ">", "APF instruction count")
    string_count = u32(data, 0x0C, ">", "APF primary string count")
    auxiliary_count = u32(data, 0x10, ">", "APF auxiliary count")
    primary_directory = pointer_document(
        data, 0x14, ">", f"{identity} primary string directory", nullable=False
    )
    fixed_table = pointer_document(
        data, 0x18, ">", f"{identity} fixed table", nullable=False
    )
    auxiliary_directory = pointer_document(
        data, 0x1C, ">", f"{identity} auxiliary directory", nullable=False
    )
    auxiliary_offset = int(auxiliary_directory["target_offset"])
    if auxiliary_count != 1:
        raise DirectorError(
            f"{identity}: observed corpus requires one opaque auxiliary entry, "
            f"found {auxiliary_count}"
        )
    checked(data, auxiliary_offset, auxiliary_count * 4, "APF auxiliary directory")
    graph = parse_graph(
        data,
        platform="apf2k8",
        role=role,
        endian=">",
        encoding="utf-16be",
        instruction_count=instruction_count,
        instruction_pointer_fields_offset=0x20,
        fixed_table_offset=int(fixed_table["target_offset"]),
        fixed_slot_count=APF_FIXED_SLOT_COUNT,
        string_count=string_count,
        string_directory_offset=int(primary_directory["target_offset"]),
        primary_region_end=auxiliary_offset,
    )
    regions = [
        raw_region(data, 0, int(graph["fixed_table_end"]), "root_and_pointer_directories"),
        raw_region(
            data,
            int(graph["fixed_table_end"]),
            int(graph["instruction_records_offset"]),
            "fixed_record_packages",
        ),
        raw_region(
            data,
            int(graph["instruction_records_offset"]),
            int(graph["instruction_records_end"]),
            "opaque_instruction_records",
        ),
        raw_region(
            data,
            int(graph["string_directory_offset"]),
            auxiliary_offset,
            "primary_string_directory_and_pool",
        ),
        raw_region(data, auxiliary_offset, len(data), "opaque_auxiliary_tail"),
    ]
    validate_partition(data, regions, identity)
    auxiliary_entries = [
        {
            "index": index,
            "field_offset": auxiliary_offset + index * 4,
            "raw_word": f"0x{u32(data, auxiliary_offset + index * 4, '>', 'aux word'):08x}",
            "portme": "opaque APF-only value; not interpreted as a relative pointer",
        }
        for index in range(auxiliary_count)
    ]
    return {
        "platform": "apf2k8",
        "role": role,
        "outer_name": outer_name,
        "outer_index": outer_index,
        "inner_index": inner_index,
        "outer_id": f"0x{outer_id:08x}",
        "resource_name": "director",
        "byte_size": len(data),
        "sha256": sha256_bytes(data),
        "endianness": "big",
        "encoding": "UTF-16BE",
        "root": {
            "offset": 0,
            "raw_prefix_hex": data[:0x20].hex(),
            "opaque_token_u32_00": f"0x{u32(data, 0, '>', 'APF token'):08x}",
            "unknown_u8_04": data[4],
            "unknown_u8_05": data[5],
            "instruction_count_u16_06": instruction_count,
            "unknown_u16_08": u16(data, 8, ">", "root +8"),
            "unknown_u16_0a": u16(data, 0x0A, ">", "root +a"),
            "primary_string_count_u32_0c": string_count,
            "opaque_auxiliary_count_u32_10": auxiliary_count,
            "primary_string_directory_pointer_14": primary_directory,
            "fixed_slot_table_pointer_18": fixed_table,
            "opaque_auxiliary_directory_pointer_1c": auxiliary_directory,
            "instruction_pointer_fields_offset_20": 0x20,
        },
        "graph": graph,
        "opaque_auxiliary_directory": {
            "offset": auxiliary_offset,
            "count": auxiliary_count,
            "entries": auxiliary_entries,
            "tail_sha256": sha256_bytes(data[auxiliary_offset:]),
            "tail_raw_hex": data[auxiliary_offset:].hex(),
        },
        "raw_partition": regions,
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
        raise DirectorError("APF DRCT part exceeds decoded block")
    return decoded[part.offset:end]


def parse_apf(index: Path, maximum: int) -> list[dict[str, object]]:
    archive = apf_outer.parse_archive(index)
    wanted = set(APF_ROLES)
    resources: list[dict[str, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for outer_index in sorted(wanted):
            entry = archive.entries[outer_index]
            if entry.head_hex != "ff3bef94":
                raise DirectorError(f"APF outer {outer_index} is not an IFF")
            iff = apf_inner.parse_iff(reader, entry)
            selected = [item for item in iff.files if item.type_name == "DRCT"]
            if len(selected) != 1:
                raise DirectorError(
                    f"APF outer {outer_index}: expected one DRCT, found {len(selected)}"
                )
            item = selected[0]
            if (
                item.index != 0
                or item.name != "director"
                or item.file_id != DIRECTOR_HASH
                or item.type_hash != DRCT_HASH
                or len(item.parts) != 1
            ):
                raise DirectorError(f"APF outer {outer_index}: DRCT identity differs")
            cache: dict[int, bytes] = {}
            data = read_apf_part(reader, iff, item.parts[0], cache, maximum)
            parsed = parse_apf_body(
                data, outer_index, item.index, entry.name_id
            )
            parsed["inner_id"] = f"0x{item.file_id:08x}"
            parsed["type_hash"] = f"0x{item.type_hash:08x}"
            resources.append(parsed)
    return resources


def parse_nfl(index: Path, scan: Path) -> list[dict[str, object]]:
    inventory, records = parse_inventory(scan)
    selected = [item for item in records if item.kind == "DRCT"]
    declared = int(inventory["summary"]["resource_kind_counts"]["DRCT"])
    if len(selected) != declared or declared != len(NFL_ROLES):
        raise DirectorError(
            f"NFL inventory selected {len(selected)} DRCT, declares {declared}"
        )
    if {item.outer_index for item in selected} != set(NFL_ROLES):
        raise DirectorError("NFL DRCT outer-index set differs")
    archive = parse_nfl_archive(index)
    resources: list[dict[str, object]] = []
    for item in sorted(selected, key=lambda value: value.outer_index):
        entry = archive.entries[item.outer_index]
        span = read_entry_range(
            archive, entry, item.chunk_offset, 0x20 + item.stored_size
        )
        data, detail = decode_resource(span, item)
        parsed = parse_nfl_body(data, item)
        parsed["wrapper"] = {
            "stored_size": item.stored_size,
            "system_bytes": item.word_08,
            "video_bytes": item.word_0c,
            "compression_word": f"0x{item.word_10:08x}",
            "scratch_bytes": item.word_14,
            "decode": detail,
        }
        resources.append(parsed)
    return resources


def record_signature(record: dict[str, object]) -> tuple[object, ...]:
    pointer_nulls = tuple(
        pointer["target_offset"] is None for pointer in record["pointer_fields"]
    )
    child_null_count = sum(
        pointer["target_offset"] is None for pointer in record["child_references"]
    )
    return (
        record["child_count"],
        record["unknown_u16_04"],
        record["unknown_u16_06"],
        pointer_nulls,
        child_null_count,
    )


def role_cross_reference(
    role: str,
    nfl: dict[str, object],
    apf: dict[str, object],
) -> dict[str, object]:
    nfl_records = nfl["graph"]["fixed_records"]
    apf_records = apf["graph"]["fixed_records"]
    nfl_signatures = [record_signature(item) for item in nfl_records]
    apf_signatures = [record_signature(item) for item in apf_records]
    signature_overlap = sum((Counter(nfl_signatures) & Counter(apf_signatures)).values())
    ordered_pairs = []
    for ordinal, (nfl_record, apf_record) in enumerate(zip(nfl_records, apf_records)):
        ordered_pairs.append(
            {
                "ordinal": ordinal,
                "nfl_slot_index": nfl_record["slot_index"],
                "apf_slot_index": apf_record["slot_index"],
                "nfl_child_count": nfl_record["child_count"],
                "apf_child_count": apf_record["child_count"],
                "nfl_unknown_u16_04": nfl_record["unknown_u16_04"],
                "apf_unknown_u16_04": apf_record["unknown_u16_04"],
                "nfl_unknown_u16_06": nfl_record["unknown_u16_06"],
                "apf_unknown_u16_06": apf_record["unknown_u16_06"],
                "structural_signature_equal": (
                    record_signature(nfl_record) == record_signature(apf_record)
                ),
            }
        )

    nfl_lengths = [int(item["size"]) for item in nfl["graph"]["instructions"]]
    apf_lengths = [int(item["size"]) for item in apf["graph"]["instructions"]]
    nfl_strings: dict[str, list[int]] = {}
    apf_strings: dict[str, list[int]] = {}
    for item in nfl["graph"]["strings"]:
        nfl_strings.setdefault(str(item["text"]), []).append(int(item["index"]))
    for item in apf["graph"]["strings"]:
        apf_strings.setdefault(str(item["text"]), []).append(int(item["index"]))
    shared_texts = sorted(set(nfl_strings) & set(apf_strings))

    if role == "wrapup":
        lineage = (
            "ordered fixed-record lineage: 20 records in both corpora; "
            "19 structural signatures retained and one evolved"
        )
        pairing_scope = "all ordered fixed records"
    elif role == "tutorial":
        lineage = "single fixed-record lineage with retained structural signature"
        pairing_scope = "single fixed record"
    elif role == "halftime":
        lineage = "single fixed-record lineage with evolved counts"
        pairing_scope = "single fixed record"
    elif role == "intro":
        lineage = "three ordered fixed records retained; record contents/counts evolved"
        pairing_scope = "three ordered records; semantic field names withheld"
    else:
        lineage = (
            "role-level lineage only; dense ingame edits make individual record "
            "pairing ambiguous"
        )
        pairing_scope = "no per-record identity claim"

    return {
        "role": role,
        "nfl_outer_index": nfl["outer_index"],
        "apf_outer_index": apf["outer_index"],
        "apf_outer_name": apf["outer_name"],
        "lineage_statement": lineage,
        "ordered_pairing_scope": pairing_scope,
        "fixed_slot_count": {
            "nfl": nfl["graph"]["fixed_slot_count"],
            "apf": apf["graph"]["fixed_slot_count"],
        },
        "nonnull_fixed_record_count": {
            "nfl": len(nfl_records),
            "apf": len(apf_records),
        },
        "shared_structural_signature_multiset_count": signature_overlap,
        "ordered_structural_signature_match_count": sum(
            bool(item["structural_signature_equal"]) for item in ordered_pairs
        ),
        "ordered_record_pairs": ordered_pairs,
        "instruction_record_count": {
            "nfl": len(nfl_lengths),
            "apf": len(apf_lengths),
        },
        "instruction_length_multiset_overlap_count": sum(
            (Counter(nfl_lengths) & Counter(apf_lengths)).values()
        ),
        "same_position_instruction_length_count": sum(
            left == right for left, right in zip(nfl_lengths, apf_lengths)
        ),
        "primary_string_count": {
            "nfl": len(nfl["graph"]["strings"]),
            "apf": len(apf["graph"]["strings"]),
        },
        "shared_exact_primary_string_count": len(shared_texts),
        "shared_exact_primary_strings": [
            {
                "text": text,
                "nfl_indices": nfl_strings[text],
                "apf_indices": apf_strings[text],
            }
            for text in shared_texts
        ],
    }


def write_tsv(
    path: Path,
    resources: Iterable[dict[str, object]],
    shared_by_role: dict[str, set[str]],
) -> None:
    fields = [
        "platform",
        "role",
        "outer_index",
        "kind",
        "index",
        "slot_index",
        "offset",
        "size",
        "child_count",
        "unknown_u16_04",
        "unknown_u16_06",
        "first_byte",
        "text",
        "shared_exact_text",
        "raw_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, dialect="excel-tab", extrasaction="ignore"
        )
        writer.writeheader()
        for resource in resources:
            graph = resource["graph"]
            common = {
                "platform": resource["platform"],
                "role": resource["role"],
                "outer_index": resource["outer_index"],
            }
            for record in graph["fixed_records"]:
                writer.writerow(
                    {
                        **common,
                        "kind": "fixed_record_package",
                        "index": record["ordinal"],
                        "slot_index": record["slot_index"],
                        "offset": record["offset"],
                        "size": record["package_size"],
                        "child_count": record["child_count"],
                        "unknown_u16_04": record["unknown_u16_04"],
                        "unknown_u16_06": record["unknown_u16_06"],
                        "raw_sha256": record["package_sha256"],
                    }
                )
            for record in graph["instructions"]:
                writer.writerow(
                    {
                        **common,
                        "kind": "opaque_instruction_record",
                        "index": record["index"],
                        "offset": record["offset"],
                        "size": record["size"],
                        "first_byte": record["first_byte"],
                        "raw_sha256": record["sha256"],
                    }
                )
            for record in graph["strings"]:
                text = str(record["text"])
                writer.writerow(
                    {
                        **common,
                        "kind": "primary_string",
                        "index": record["index"],
                        "offset": record["offset"],
                        "size": record["size"],
                        "text": text,
                        "shared_exact_text": text in shared_by_role[resource["role"]],
                        "raw_sha256": record["sha256"],
                    }
                )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--apf-index", type=Path, required=True)
    result.add_argument("--nfl-index", type=Path, required=True)
    result.add_argument(
        "--nfl-resource-scan",
        type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    result.add_argument(
        "--nfl-xbe",
        type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    result.add_argument(
        "--apf-xex",
        type=Path,
        default=Path("extracted/All-Pro Football 2K8 (USA)/default.xex"),
    )
    result.add_argument(
        "--apf-trace",
        type=Path,
        default=Path(
            "reports/assets/cross_title_director_ghidra/director_trace.txt"
        ),
    )
    result.add_argument(
        "--apf-pseudo",
        type=Path,
        default=Path(
            "reports/assets/cross_title_director_ghidra/director_focused_pseudo_c.c"
        ),
    )
    result.add_argument("--json", type=Path, required=True)
    result.add_argument("--tsv", type=Path, required=True)
    result.add_argument("--max-decompressed", type=int, default=64 * 1024 * 1024)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.max_decompressed <= 0:
        raise DirectorError("--max-decompressed must be positive")
    for source in (
        args.apf_index,
        args.nfl_index,
        args.nfl_resource_scan,
        args.nfl_xbe,
        args.apf_xex,
        args.apf_trace,
        args.apf_pseudo,
    ):
        if not source.is_file():
            raise DirectorError(f"missing required source {source}")

    apf_resources = parse_apf(args.apf_index, args.max_decompressed)
    nfl_resources = parse_nfl(args.nfl_index, args.nfl_resource_scan)
    if len(apf_resources) != 5 or len(nfl_resources) != 5:
        raise DirectorError(
            f"expected APF=5 NFL=5 DRCT resources, found "
            f"APF={len(apf_resources)} NFL={len(nfl_resources)}"
        )
    apf_by_role = {str(item["role"]): item for item in apf_resources}
    nfl_by_role = {str(item["role"]): item for item in nfl_resources}
    if set(apf_by_role) != set(ROLE_ORDER) or set(nfl_by_role) != set(ROLE_ORDER):
        raise DirectorError("cross-title DRCT role sets differ")
    cross_reference = [
        role_cross_reference(role, nfl_by_role[role], apf_by_role[role])
        for role in ROLE_ORDER
    ]
    shared_by_role = {
        role: {
            str(item["text"])
            for item in next(
                value for value in cross_reference if value["role"] == role
            )["shared_exact_primary_strings"]
        }
        for role in ROLE_ORDER
    }

    all_resources = [
        apf_by_role[role] for role in ROLE_ORDER
    ] + [nfl_by_role[role] for role in ROLE_ORDER]
    apf_fixed = sum(
        len(item["graph"]["fixed_records"]) for item in apf_resources
    )
    nfl_fixed = sum(
        len(item["graph"]["fixed_records"]) for item in nfl_resources
    )
    apf_instructions = sum(
        len(item["graph"]["instructions"]) for item in apf_resources
    )
    nfl_instructions = sum(
        len(item["graph"]["instructions"]) for item in nfl_resources
    )
    apf_strings = sum(len(item["graph"]["strings"]) for item in apf_resources)
    nfl_strings = sum(len(item["graph"]["strings"]) for item in nfl_resources)
    report = {
        "schema": SCHEMA,
        "sources": {
            "apf_index": str(args.apf_index),
            "apf_index_sha256": sha256_file(args.apf_index),
            "apf_xex": str(args.apf_xex),
            "apf_xex_sha256": sha256_file(args.apf_xex),
            "apf_trace": str(args.apf_trace),
            "apf_trace_sha256": sha256_file(args.apf_trace),
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
            "nfl_fixed_slot_count": NFL_FIXED_SLOT_COUNT,
            "apf_fixed_slot_count": APF_FIXED_SLOT_COUNT,
            "fixed_record_header_size": 0x1C,
            "drct_crc32": f"0x{DRCT_HASH:08x}",
            "director_crc32": f"0x{DIRECTOR_HASH:08x}",
        },
        "executable_evidence": {
            "nfl_registration": (
                "default.xbe:0x00166760 registers FourCC DRCT with loader "
                "0x00166730; selector 0x00166700 supplies load/unload callbacks "
                "0x001666c0/0x001666e0"
            ),
            "nfl_relocator": (
                "default.xbe:0x000dc700 fixes root +0x10, 193 fixed slots, "
                "record +0x08..+0x18 and child arrays, root +0x14 instruction "
                "pointers, and root +0x0c UTF-16 string pointers"
            ),
            "nfl_consumers": (
                "default.xbe:0x000dc8e0 indexes fixed record children; "
                "0x000dca40 consumes root +0x14 instruction entries; "
                "0x000dcba0 indexes root +0x0c strings; 0x000dcb20 walks all "
                "0x304 fixed-slot bytes"
            ),
            "apf_registry": (
                "default.xex data 0x84d1b830..0x84d1b83c contains a linked "
                "registry node whose +0x04 word is CRC32('DRCT')=0xed586383; "
                "Function_8466AF70 passes the owning table at 0x84d1b7d0 to "
                "Function_8468DA70 for dir_ingame.iff"
            ),
        },
        "summary": {
            "apf_resource_count": len(apf_resources),
            "nfl_resource_count": len(nfl_resources),
            "apf_fixed_record_count": apf_fixed,
            "nfl_fixed_record_count": nfl_fixed,
            "apf_instruction_record_count": apf_instructions,
            "nfl_instruction_record_count": nfl_instructions,
            "apf_primary_string_count": apf_strings,
            "nfl_primary_string_count": nfl_strings,
            "shared_exact_primary_string_count": sum(
                len(item["shared_exact_primary_strings"])
                for item in cross_reference
            ),
            "all_relative_pointers_bounded": True,
            "all_fixed_record_packages_bounded": True,
            "all_instruction_records_exactly_partitioned": True,
            "all_primary_strings_exactly_partitioned": True,
            "all_decoded_bytes_preserved_in_raw_partitions": True,
            "writer_implemented": False,
        },
        "cross_title_roles": cross_reference,
        "portme": [
            "PORTME: name the root +0x00/+0x01/+0x04/+0x06 and fixed-record +0x04/+0x06 fields from direct semantic consumers.",
            "PORTME: recover opaque instruction opcodes, operand widths, control flow, and termination before translating director scripts.",
            "PORTME: identify the five fixed-record pointers at +0x08..+0x18 and the child-target payload layouts.",
            "PORTME: trace APF's one-entry auxiliary directory and tail; its entry is intentionally not treated as a self-relative pointer.",
            "PORTME: prove APF's 217-slot relocator/consumer code directly; current APF layout evidence is complete-corpus structural continuity from the XBE-proven graph.",
            "PORTME: implement a writer/repacker only after opcode semantics, capacity rules, auxiliary ownership, and archive hashing are complete.",
        ],
        "resources": all_resources,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    newline="\n",
)
    write_tsv(args.tsv, all_resources, shared_by_role)
    print(
        "DIRECTOR_INVENTORY_COMPLETE "
        f"apf=5/{apf_fixed}/{apf_instructions}/{apf_strings} "
        f"nfl=5/{nfl_fixed}/{nfl_instructions}/{nfl_strings} "
        f"shared={report['summary']['shared_exact_primary_string_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        DirectorError,
        ProbeError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        struct.error,
    ) as exc:
        raise SystemExit(f"error: {exc}") from exc
