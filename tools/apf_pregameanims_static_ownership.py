#!/usr/bin/env python3
"""Audit APF/NFL ``pregameanims.iff`` lineage and static ownership.

This tool is read-only.  It validates the exact dual-hash package pair,
decodes only the selected MRKS resources, scans all four retail APF pack files
for exact serialized owner edges, and joins two focused read-only Ghidra
traces.  Static absence is reported as a boundary, never as proof that an
unobserved dynamic/index-based path cannot execute the archive.
"""

from __future__ import annotations

import argparse
import bisect
from collections import Counter
import csv
import hashlib
import json
import mmap
from pathlib import Path
import re
import struct
import sys
import zlib

import apf_inner
import apf_outer
import nfl_outer
from nfl_scene_probe import (
    decode_resource,
    named_inner,
    parse_inventory,
    read_entry_range,
)


SCHEMA = "vc_apf_pregameanims_static_ownership/v1"
APF_OUTER_INDEX = 239
APF_OUTER_ID = 0x27B28292
NFL_OUTER_INDEX = 1193
NFL_OUTER_ID = 0x0205429D
MRKS_HASH = 0xC6ED33A2
SCNE_HASH = 0xE26C9B5D
MAX_DECOMPRESSED = 32 * 1024 * 1024

APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
APF_INDEX_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
NFL_INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"

RESOURCE_IDS = {
    "bigfigureafc": 0x73DEC7A1,
    "bigfigurenfc": 0x7882809C,
    "bighelmet": 0xDE413B72,
    "big_team_matchup": 0xF0BD9799,
}


class EvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path, label: str) -> dict[str, object]:
    return {"path": label, "size": path.stat().st_size, "sha256": sha256_file(path)}


def hx(value: int) -> str:
    return f"0x{value:08x}"


def crc_ascii(value: str) -> int:
    return zlib.crc32(value.encode("ascii")) & 0xFFFFFFFF


def crc_upper_ascii(value: str) -> int:
    return crc_ascii(value.upper())


def crc_upper_utf16le(value: str) -> int:
    return zlib.crc32(value.upper().encode("utf-16le")) & 0xFFFFFFFF


def u32(data: bytes, offset: int, endian: str) -> int:
    require(0 <= offset <= len(data) - 4, f"u32 at 0x{offset:x} is out of bounds")
    return int.from_bytes(data[offset : offset + 4], endian)


def relative_target(data: bytes, field: int, endian: str) -> tuple[int, int]:
    raw = u32(data, field, endian)
    require(raw != 0, f"relative pointer at 0x{field:x} is null")
    target = field + raw - 1
    require(0 <= target < len(data), f"relative pointer at 0x{field:x} escapes body")
    return raw, target


def utf16_z(data: bytes, offset: int, endian: str) -> str:
    encoding = "utf-16be" if endian == "big" else "utf-16le"
    cursor = offset
    while cursor + 1 < len(data) and data[cursor : cursor + 2] != b"\0\0":
        cursor += 2
    require(cursor + 1 < len(data), f"unterminated UTF-16 string at 0x{offset:x}")
    return data[offset:cursor].decode(encoding)


def identifier_runs(data: bytes, endian: str) -> list[tuple[int, str]]:
    pattern = (
        re.compile(rb"(?:\x00[\x20-\x7e]){2,}\x00\x00")
        if endian == "big"
        else re.compile(rb"(?:[\x20-\x7e]\x00){2,}\x00\x00")
    )
    encoding = "utf-16be" if endian == "big" else "utf-16le"
    result: list[tuple[int, str]] = []
    for match in pattern.finditer(data):
        text = match.group()[:-2].decode(encoding)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text):
            result.append((match.start(), text))
    return result


def identity_matrix(data: bytes, offset: int, endian: str) -> list[float]:
    prefix = ">" if endian == "big" else "<"
    values = list(struct.unpack_from(prefix + "16f", data, offset))
    expected = [1.0 if row == column else 0.0 for row in range(4) for column in range(4)]
    require(values == expected, f"identity matrix at 0x{offset:x} changed")
    return values


def read_apf_package(index: Path) -> tuple[dict[str, object], bytes]:
    archive = apf_outer.parse_archive(index)
    entry = archive.entries[APF_OUTER_INDEX]
    require(entry.name_id == APF_OUTER_ID, "APF pregameanims.iff outer ID changed")
    require(crc_upper_ascii("pregameanims.iff") == entry.name_id,
            "APF filename hash rule changed")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        blocks = [
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        ]
    resources: list[dict[str, object]] = []
    mrks_body = b""
    for item in record.files:
        require(item.name is not None and item.type_name is not None,
                "APF pregame resource lost its name")
        parts: list[bytes] = []
        for part in item.parts:
            block = blocks[part.block_index]
            require(part.offset + part.length <= len(block), "APF inner part escapes block")
            parts.append(block[part.offset : part.offset + part.length])
        body = b"".join(parts)
        resources.append({
            "index": item.index,
            "name": item.name,
            "type": item.type_name,
            "id": hx(item.file_id),
            "part_sizes": [len(part) for part in parts],
            "decoded_size": len(body),
            "decoded_sha256": sha256_bytes(body),
        })
        if item.name == "big_team_matchup" and item.type_name == "MRKS":
            mrks_body = body
    expected = [
        ("bigfigureafc", "SCNE"), ("bigfigurenfc", "SCNE"),
        ("bighelmet", "SCNE"), ("big_team_matchup", "MRKS"),
    ]
    require([(row["name"], row["type"]) for row in resources] == expected,
            "APF pregame resource composition/order changed")
    require(len(mrks_body) == 105_738, "APF big_team_matchup MRKS size changed")
    return {
        "outer_index": APF_OUTER_INDEX,
        "outer_id": hx(entry.name_id),
        "outer_stored_size": entry.size,
        "filename": "pregameanims.iff",
        "filename_hash_rule": "CRC32 uppercase ASCII",
        "resource_count": len(resources),
        "resources": resources,
    }, mrks_body


def read_nfl_package(root: Path, index: Path) -> tuple[dict[str, object], bytes]:
    archive = nfl_outer.parse_archive(index)
    entry = archive.entries[NFL_OUTER_INDEX]
    require(entry.name_id == NFL_OUTER_ID, "NFL pregameanims.iff outer ID changed")
    require(crc_upper_utf16le("pregameanims.iff") == entry.name_id,
            "NFL filename hash rule changed")
    _, inventory = parse_inventory(root / "reports/assets/nfl2k5_resource_chunks_v2.json")
    resources: list[dict[str, object]] = []
    mrks_body = b""
    for record in inventory:
        if record.outer_index != NFL_OUTER_INDEX:
            continue
        span = read_entry_range(
            archive, entry, record.chunk_offset, 0x20 + record.stored_size)
        decoded, _ = decode_resource(span, record)
        name, _, _ = named_inner(decoded, record.kind)
        resources.append({
            "index": record.chunk_index,
            "name": name,
            "type": record.kind,
            "decoded_size": len(decoded),
            "decoded_sha256": sha256_bytes(decoded),
        })
        if name == "big_team_matchup" and record.kind == "MRKS":
            require(decoded[:4] == b"\0\0\0\0" and decoded[0x0C:0x10] == b"MRKS",
                    "NFL MRKS common header changed")
            mrks_body = decoded[0x20:]
    expected = [
        ("big_team_matchup", "MRKS"), ("bighelmet", "SCNE"),
        ("bigfigurenfc", "SCNE"), ("bigfigureafc", "SCNE"),
    ]
    require([(row["name"], row["type"]) for row in resources] == expected,
            "NFL pregame resource composition/order changed")
    require(len(mrks_body) == 81_760, "NFL big_team_matchup MRKS body size changed")
    return {
        "outer_index": NFL_OUTER_INDEX,
        "outer_id": hx(entry.name_id),
        "outer_stored_size": entry.size,
        "filename": "pregameanims.iff",
        "filename_hash_rule": "CRC32 uppercase UTF-16LE",
        "resource_count": len(resources),
        "resources": resources,
    }, mrks_body


def mrks_lineage(apf: bytes, nfl: bytes) -> tuple[dict[str, object], list[dict[str, object]]]:
    apf_root_raw, apf_descriptor = relative_target(apf, 0, "big")
    nfl_root_raw, nfl_descriptor = relative_target(nfl, 0, "little")
    require((apf_root_raw, apf_descriptor) == (0xFE1, 0xFE0),
            "APF MRKS root pointer changed")
    require((nfl_root_raw, nfl_descriptor) == (0x3E1, 0x3E0),
            "NFL MRKS root pointer changed")
    apf_name_raw, apf_name_target = relative_target(apf, apf_descriptor, "big")
    nfl_name_raw, nfl_name_target = relative_target(nfl, nfl_descriptor, "little")
    require(utf16_z(apf, apf_name_target, "big") == "big_team_matchup",
            "APF MRKS root descriptor name changed")
    require(utf16_z(nfl, nfl_name_target, "little") == "big_team_matchup",
            "NFL MRKS root descriptor name changed")
    require((apf_name_raw, apf_name_target) == (0x18D09, 0x19CE8),
            "APF MRKS descriptor-name pointer changed")
    require((nfl_name_raw, nfl_name_target) == (0x13A61, 0x13E40),
            "NFL MRKS descriptor-name pointer changed")

    apf_aliases = []
    for field in (0x10, 0x18):
        raw, target = relative_target(apf, field, "big")
        apf_aliases.append({
            "field": hx(field), "raw": hx(raw), "target": hx(target),
            "text": utf16_z(apf, target, "big"),
        })
    require([row["target"] for row in apf_aliases] == ["0x00000440"] * 2 and
            [row["text"] for row in apf_aliases] == ["big_team_matchup"] * 2,
            "APF MRKS root name aliases changed")
    nfl_aliases = []
    for field in (0x10, 0x18, 0x20):
        raw, target = relative_target(nfl, field, "little")
        nfl_aliases.append({
            "field": hx(field), "raw": hx(raw), "target": hx(target),
        })
    require([row["target"] for row in nfl_aliases] == ["0x00000390"] * 3,
            "NFL MRKS root shared-pointer targets changed")

    identity_matrix(apf, 0x20, "big")
    identity_matrix(nfl, 0x30, "little")
    require(u32(apf, 4, "big") == u32(nfl, 4, "little") == 6,
            "MRKS shared header word +4 changed")
    require((u32(apf, 8, "big"), u32(nfl, 8, "little")) == (25, 41),
            "MRKS header word +8 changed")

    nfl_names = [
        value for value in nfl[0x13760:0x13E60].decode("utf-16le").split("\0")
        if value
    ]
    require(len(nfl_names) == len(set(nfl_names)) == 79,
            "NFL MRKS compact identifier table changed")
    require(nfl_names[0] == "longdark0010" and nfl_names[-1] == "big_team_matchup",
            "NFL MRKS identifier table boundaries changed")
    apf_runs = identifier_runs(apf, "big")
    by_name: dict[str, list[int]] = {}
    for offset, name in apf_runs:
        by_name.setdefault(name, []).append(offset)
    rows = [{
        "nfl_table_index": index,
        "name": name,
        "apf_exact_identifier_present": name in by_name,
        "apf_occurrence_count": len(by_name.get(name, [])),
        "apf_offsets": ";".join(hx(value) for value in by_name.get(name, [])),
    } for index, name in enumerate(nfl_names)]
    missing = [row["name"] for row in rows if not row["apf_exact_identifier_present"]]
    require(missing == ["opaque"], "APF MRKS missing-name set changed")

    return {
        "classification": "structurally_converted_same_named_resource",
        "byte_identical": False,
        "apf_body_size": len(apf),
        "nfl_body_size_after_common_header": len(nfl),
        "apf_body_sha256": sha256_bytes(apf),
        "nfl_body_sha256": sha256_bytes(nfl),
        "common_pointer_rule": "one-based field-relative pointer",
        "apf_endian": "big",
        "nfl_endian": "little",
        "root_descriptor": {
            "apf": {"field": "0x00000000", "raw": hx(apf_root_raw),
                    "target": hx(apf_descriptor)},
            "nfl": {"field": "0x00000000", "raw": hx(nfl_root_raw),
                    "target": hx(nfl_descriptor)},
        },
        "descriptor_name": {
            "apf": {"field": hx(apf_descriptor), "raw": hx(apf_name_raw),
                    "target": hx(apf_name_target), "text": "big_team_matchup"},
            "nfl": {"field": hx(nfl_descriptor), "raw": hx(nfl_name_raw),
                    "target": hx(nfl_name_target), "text": "big_team_matchup"},
        },
        "apf_root_name_aliases": apf_aliases,
        "nfl_root_shared_pointer_fields": nfl_aliases,
        "shared_header_word_04": 6,
        "header_word_08": {"apf": 25, "nfl": 41},
        "identity_matrix_offset": {"apf": "0x00000020", "nfl": "0x00000030"},
        "nfl_compact_identifier_count": len(nfl_names),
        "apf_exact_retained_identifier_count": sum(
            bool(row["apf_exact_identifier_present"]) for row in rows),
        "apf_missing_identifiers": missing,
        "boundary": (
            "Pointer topology and 78 exact identifiers prove format/name lineage; "
            "different sizes, endian, counts, and field placement preclude byte compatibility."
        ),
    }, rows


def all_hits(view: mmap.mmap, needle: bytes) -> list[int]:
    result: list[int] = []
    cursor = 0
    while True:
        cursor = view.find(needle, cursor)
        if cursor < 0:
            return result
        result.append(cursor)
        cursor += 1


def scan_apf_packs(root: Path) -> dict[str, object]:
    manifest_path = root / "reports/manifests/apf_outer.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    packs = manifest["packs"]
    entries = manifest["entries"]
    require([row["name"] for row in packs] == ["0A", "0B", "1A", "1B"],
            "APF pack order changed")
    ranges = sorted((row["virtual_offset"], row["virtual_end"], row["table_index"],
                     row["name_id"]) for row in entries)
    starts = [row[0] for row in ranges]

    def occurrence(pack: dict[str, object], offset: int) -> dict[str, object]:
        virtual = int(pack["virtual_start"]) + offset
        index = bisect.bisect_right(starts, virtual) - 1
        owner = None
        if index >= 0:
            first, after, ordinal, name_id = ranges[index]
            if first <= virtual < after:
                owner = {
                    "outer_index": ordinal,
                    "outer_name_id": name_id,
                    "relative_offset": hx(virtual - first),
                }
        return {
            "pack": pack["name"], "pack_offset": hx(offset),
            "virtual_offset": hx(virtual), "owner": owner,
        }

    hashes = {"pregameanims_iff": APF_OUTER_ID, **{
        f"{name}_resource_id": value for name, value in RESOURCE_IDS.items()
    }}
    literals = {
        "pregameanims_iff": "pregameanims.iff",
        **{f"{name}_resource_name": name for name in RESOURCE_IDS},
    }
    hash_hits = {name: {"big_endian_aligned": [], "little_endian_aligned": []}
                 for name in hashes}
    literal_hits = {name: [] for name in literals}
    game = root / "extracted/All-Pro Football 2K8 (USA)"
    for pack in packs:
        path = game / str(pack["name"])
        require(path.stat().st_size == pack["actual_size"], f"APF pack {path} size changed")
        with path.open("rb") as source, mmap.mmap(
                source.fileno(), 0, access=mmap.ACCESS_READ) as view:
            for label, value in hashes.items():
                for order, key in (("big", "big_endian_aligned"),
                                   ("little", "little_endian_aligned")):
                    for offset in all_hits(view, value.to_bytes(4, order)):
                        if offset & 3 == 0:
                            hash_hits[label][key].append(occurrence(pack, offset))
            for label, value in literals.items():
                needle = value.encode("utf-16be") + b"\0\0"
                for offset in all_hits(view, needle):
                    literal_hits[label].append(occurrence(pack, offset))

    package_hash = hash_hits["pregameanims_iff"]
    require(len(package_hash["big_endian_aligned"]) == 1 and
            not package_hash["little_endian_aligned"],
            "APF pregameanims filename-hash occurrences changed")
    require(package_hash["big_endian_aligned"][0]["pack_offset"] == "0x00000b8c" and
            package_hash["big_endian_aligned"][0]["owner"] is None,
            "APF pregameanims hash escaped its outer-table row")
    require(not literal_hits["pregameanims_iff"],
            "APF serialized pregameanims.iff literal appeared")
    for name in RESOURCE_IDS:
        hits = literal_hits[f"{name}_resource_name"]
        require(len(hits) == 1 and hits[0]["owner"] is not None and
                hits[0]["owner"]["outer_index"] == APF_OUTER_INDEX,
                f"APF exact resource name {name} escaped its own footer")

    return {
        "pack_count": len(packs),
        "total_bytes_scanned": sum(int(row["actual_size"]) for row in packs),
        "hash_occurrences": hash_hits,
        "exact_utf16be_literal_occurrences": literal_hits,
        "exact_name_external_owner_count": 0,
        "interpretation": (
            "The package filename hash is confined to its outer-table row. Each exact "
            "resource-name literal is confined to outer 239's own footer; no exact-name "
            "serialized owner exists elsewhere. Repeated bigfigurenfc numeric-word hits "
            "are non-name byte collisions and are not treated as ownership."
        ),
    }


def xbe_mapper(header: dict[str, object]):
    sections = header["sections"]

    def va_to_offset(va: int, size: int = 1) -> int:
        for section in sections:
            first = int(section["virtual_address"])
            after = first + int(section["raw_size"])
            if first <= va and va + size <= after:
                return int(section["raw_address"]) + va - first
        raise EvidenceError(f"XBE VA {hx(va)} has no raw mapping")

    return va_to_offset


def nfl_compiled_owner(xbe_path: Path, header_path: Path, trace: str) -> dict[str, object]:
    data = xbe_path.read_bytes()
    header = json.loads(header_path.read_text(encoding="utf-8"))
    va_to_offset = xbe_mapper(header)

    def text(va: int) -> str:
        return utf16_z(data, va_to_offset(va), "little")

    strings = {
        "group": (0x00E73A70, "PREGAME"),
        "bighelmet": (0x00E73A80, "bighelmet"),
        "bigfigureafc": (0x00E73A94, "bigfigureafc"),
        "bigfigurenfc": (0x00E73AB0, "bigfigurenfc"),
        "package": (0x00E73AF4, "pregameanims.iff"),
        "descriptor_name": (0x00E86328, "big_team_matchup"),
        "descriptor_category": (0x00E8634C, "PREGAME"),
    }
    for address, expected in strings.values():
        require(text(address) == expected, f"NFL compiled string {expected} changed")

    base = 0x00AAD1EC
    stride = 0x6C
    count = 31
    records = []
    for index in range(count):
        address = base + index * stride
        offset = va_to_offset(address, stride)
        words = list(struct.unpack_from("<27I", data, offset))
        records.append({
            "index": index,
            "address": hx(address),
            "name_pointer": hx(words[0]),
            "name": text(words[0]),
            "category_pointer": hx(words[1]),
            "category": text(words[1]),
            "raw_words": [hx(value) for value in words],
        })
    target = records[12]
    require((target["address"], target["name"], target["category"]) ==
            ("0x00aad6fc", "big_team_matchup", "PREGAME"),
            "NFL big_team_matchup compiled descriptor changed")
    require(records[0]["name"] == "1-p_flip-chip_stats-few" and
            records[-1]["name"] == "gamesound_prologicII",
            "NFL presentation descriptor table boundaries changed")

    required_trace = [
        "NFL_PREGAMEANIMS_OWNER_TRACE_V1",
        "LITERAL pregameanims.iff encoding=UTF16LE hits=1 0x00E73AF4",
        "LITERAL big_team_matchup encoding=UTF16LE hits=1 0x00E86328[0x00AAD6FC",
        "FUNCTION 0x00125660:", "FUNCTION 0x00125700:",
        "0x0012581E PUSH 0x125660", "0x0012582D MOV EDX,0xe73af4",
        "0x00125832 MOV ECX,0xe73a70", "0x00125841 CALL 0x00043f50",
        "FUNCTION 0x00125C50:", "0x00125C97 MOV ECX,0xe73a70",
        "0x00125C9C CALL 0x000432f0", "FUNCTION 0x00125CD0:",
    ]
    for value in required_trace:
        require(value in trace, f"NFL Ghidra trace lost {value}")

    return {
        "classification": "compiled_package_lifecycle_owner",
        "initializer": "0x00125700",
        "initializer_direct_callers": ["0x00064b10", "0x00064c70"],
        "package_dispatch": "0x00043f50",
        "package_string": {"address": "0x00e73af4", "text": "pregameanims.iff"},
        "group_string": {"address": "0x00e73a70", "text": "PREGAME"},
        "resource_resolution_callback": "0x00125660",
        "resolved_scene_names": ["bighelmet", "bigfigureafc", "bigfigurenfc"],
        "resolved_scene_globals": ["0x00bb75e4", "0x00bb75e8", "0x00bb75ec"],
        "teardown_owner": "0x00125c50",
        "transition_release_owner": "0x00125cd0",
        "presentation_descriptor_table": {
            "base": hx(base), "record_stride": hx(stride), "record_count": count,
            "category_counts": dict(sorted(Counter(row["category"] for row in records).items())),
            "big_team_matchup_record": target,
        },
        "big_team_matchup_compiled_category_association": True,
        "individual_descriptor_code_traversal_proved": False,
        "boundary": (
            "The package lifecycle and PREGAME descriptor association are compiled and exact. "
            "No direct code traversal of record 12 or concrete MRKS playback call was recovered."
        ),
    }


def apf_executable_boundary(trace: str) -> dict[str, object]:
    required = [
        "APF_PREGAMEANIMS_OWNER_TRACE_V1",
        "LITERAL pregameanims.iff encoding=UTF16BE hits=0",
        "LITERAL bigfigureafc encoding=UTF16BE hits=0",
        "LITERAL bigfigurenfc encoding=UTF16BE hits=0",
        "LITERAL bighelmet encoding=UTF16BE hits=0",
        "LITERAL big_team_matchup encoding=UTF16BE hits=0",
        "HASH pregameanims_iff value=0x27B28292 aligned_hits=0 materializations=",
        "HASH bigfigureafc_resource_id value=0x73DEC7A1 aligned_hits=0 materializations=",
        "HASH bigfigurenfc_resource_id value=0x7882809C aligned_hits=0 materializations=",
        "HASH bighelmet_resource_id value=0xDE413B72 aligned_hits=0 materializations=",
        "HASH big_team_matchup_resource_id value=0xF0BD9799 aligned_hits=0 materializations=",
        "0x84D22EB0 raw=0x82006388",
        "0x84D22EB4 raw=0xC6ED33A2",
        "0x82006388 raw=0x84692560",
        "0x8200638C raw=0x846925C0",
        "0x82006390 raw=0x84692640",
        "0x846924C8 lis r11,-0x7e00",
        "0x846924D8 ori r9,r9,0x33a2",
        "0x84692530 lis r11,-0x7b2e refs=0x84691154",
        "0x84692560 mfspr r12,LR refs=0x82006388",
        "0x84692580 bl 0x8463b218",
        "0x84692598 lis r5,0x4115",
        "0x846925B4 bl 0x84692250",
    ]
    for value in required:
        require(value in trace, f"APF Ghidra trace lost {value}")
    return {
        "classification": "no_package_specific_static_owner_found",
        "exact_package_literal_count": 0,
        "exact_resource_literal_count": 0,
        "package_hash_fullword_or_materialization_count": 0,
        "resource_hash_fullword_or_materialization_count": 0,
        "generic_mrks_handler": {
            "runtime_node": "0x84d22eb0",
            "type_hash": "0xc6ed33a2",
            "callback_table": "0x82006388",
            "dram_vram_load_callback": "0x84692560",
            "dram_destructor_callback": "0x846925c0",
            "node_destructor": "0x84692640",
            "normal_teardown_unlink": "0x84692530",
            "registered_type_support_present": True,
        },
        "package_specific_runtime_route_proved": False,
        "boundary": (
            "This exhaustive exact-name/hash static audit found no package-specific owner. "
            "It does not exclude dynamic string construction, ordinal enumeration, or an "
            "unrecovered indirect/index-based request."
        ),
    }


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apf-trace", type=Path, required=True)
    parser.add_argument("--nfl-trace", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--names-tsv-out", type=Path, required=True)
    parser.add_argument("--claims-tsv-out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    apf_index = root / "extracted/All-Pro Football 2K8 (USA)/0A"
    apf_xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
    nfl_index = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
    nfl_xbe = root / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
    xbe_header = root / "reports/headers/nfl2k5_xbe_header.json"
    require(sha256_file(apf_index) == APF_INDEX_SHA256, "APF index hash changed")
    require(sha256_file(apf_xex) == APF_XEX_SHA256, "APF XEX hash changed")
    require(sha256_file(nfl_index) == NFL_INDEX_SHA256, "NFL index hash changed")
    require(sha256_file(nfl_xbe) == NFL_XBE_SHA256, "NFL XBE hash changed")

    apf_trace = args.apf_trace.read_text(encoding="utf-8")
    nfl_trace = args.nfl_trace.read_text(encoding="utf-8")
    apf_package, apf_mrks = read_apf_package(apf_index)
    nfl_package, nfl_mrks = read_nfl_package(root, nfl_index)
    lineage, name_rows = mrks_lineage(apf_mrks, nfl_mrks)
    serialized = scan_apf_packs(root)
    apf_exec = apf_executable_boundary(apf_trace)
    nfl_exec = nfl_compiled_owner(nfl_xbe, xbe_header, nfl_trace)

    report = {
        "schema": SCHEMA,
        "scope": {
            "read_only": True,
            "games_launched": False,
            "game_images_modified": False,
            "question": (
                "Does APF retain a static owner for pregameanims.iff, and how does "
                "big_team_matchup MRKS descend from NFL 2K5?"
            ),
        },
        "sources": {
            "apf_index": pin(apf_index, "extracted/All-Pro Football 2K8 (USA)/0A"),
            "apf_xex": pin(apf_xex, "extracted/All-Pro Football 2K8 (USA)/default.xex"),
            "nfl_index": pin(nfl_index, "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"),
            "nfl_xbe": pin(nfl_xbe, "extracted/ESPN NFL 2K5 (USA)/default.xbe"),
            "apf_ghidra_trace": {
                "path": "reports/cut_content/apf_nfl_lineage/pregameanims_owner/apf_trace.txt",
                "size": args.apf_trace.stat().st_size,
                "sha256": sha256_file(args.apf_trace),
            },
            "nfl_ghidra_trace": {
                "path": "reports/cut_content/apf_nfl_lineage/pregameanims_owner/nfl_trace.txt",
                "size": args.nfl_trace.stat().st_size,
                "sha256": sha256_file(args.nfl_trace),
            },
        },
        "exact_package_pair": {
            "filename": "pregameanims.iff",
            "apf": apf_package,
            "nfl": nfl_package,
            "same_four_named_resources": True,
            "physical_order_changed": True,
        },
        "mrks_lineage": lineage,
        "apf_serialized_owner_scan": serialized,
        "apf_executable": apf_exec,
        "nfl_executable": nfl_exec,
        "conclusion": {
            "apf_classification": "static_orphan_candidate_with_generic_mrks_support",
            "nfl_classification": "compiled_pregame_package_lifecycle_owner",
            "runtime_reachability_proved_in_apf": False,
            "runtime_reachability_disproved_in_apf": False,
            "formal_nfl_2k6_build_proved": False,
            "safe_statement": (
                "APF ships a structurally converted NFL 2K5 pregame MRKS/package and "
                "retains generic MRKS loading support, but no package-specific static owner "
                "was found. NFL 2K5 explicitly loads and releases the PREGAME package and "
                "compiles big_team_matchup into its PREGAME presentation descriptors."
            ),
        },
        "portme": [
            "// PORTME: trace APF ordinal/enumeration-based package requests before declaring runtime non-use.",
            "// PORTME: recover the generic NFL presentation-descriptor traversal and concrete MRKS playback call.",
            "// PORTME: map the remaining MRKS record fields before implementing a reversible editor.",
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.names_tsv_out, name_rows, [
        "nfl_table_index", "name", "apf_exact_identifier_present",
        "apf_occurrence_count", "apf_offsets",
    ])
    claims = [
        {
            "grade": "A_proven",
            "claim": "APF outer 239 and NFL outer 1193 are the exact pregameanims.iff package pair.",
            "evidence": "dual filename hashes and identical four-resource name/type set",
            "boundary": "resource order and serialized bodies differ",
        },
        {
            "grade": "A_proven",
            "claim": "big_team_matchup is a structurally converted cross-title MRKS resource.",
            "evidence": "shared one-based relative-pointer topology, descriptor name, header word 6, identity root, and 78/79 exact NFL identifiers",
            "boundary": "not byte-compatible; opaque is absent and counts/field placement changed",
        },
        {
            "grade": "A_proven",
            "claim": "NFL 2K5 has a compiled PREGAME package lifecycle owner.",
            "evidence": "0x00125700 load, 0x00125660 three-SCNE resolver, 0x00125C50/0x00125CD0 release paths",
            "boundary": "individual big_team_matchup record traversal is not yet recovered",
        },
        {
            "grade": "boundary",
            "claim": "APF pregameanims.iff is a static-orphan candidate, not proven runtime-dead content.",
            "evidence": "zero XEX exact names/hashes and zero external exact-name serialized owners; generic MRKS node remains registered",
            "boundary": "dynamic construction, enumeration, or indirect/index access is not excluded",
        },
    ]
    write_tsv(args.claims_tsv_out, claims, ["grade", "claim", "evidence", "boundary"])
    print(
        "APF_PREGAMEANIMS_STATIC_OWNERSHIP_COMPLETE package_pair=true "
        "mrks_names=78/79 apf_static_owner=false nfl_lifecycle=true runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, apf_inner.FormatError, apf_outer.FormatError,
            nfl_outer.FormatError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
