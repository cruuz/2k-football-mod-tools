#!/usr/bin/env python3
"""Audit the live-player helmet00/helmet02 TXTRs in all NFL 2K5 uniforms."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

from nfl_outer import Entry, parse_archive
from nfl_txtr import (COMPRESSED_SENTINEL, HEADER,
                      minimum_vc_lz_overlap_scratch, parse_texture)
from nfl_uniform_inventory import read_and_validate_span
from xbe_info import Xbe
import nfl_uniform_color_xiso_direct_patch as xiso


SCHEMA = "nfl2k5_live_helmet_txtr_compatibility/v1"
FIRST_OUTER = 3613
LAST_OUTER = 4246
PACKAGE_COUNT = 634
FAMILIES = {11: "helmet00", 12: "helmet02"}
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
CHUNK_INVENTORY_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
UNIFORM_INVENTORY_SHA256 = "b9799b6f67b023f51b56695443fe2d5ff9e5ee3abc08a2c567f4c3c6cd5d04b8"
STANDALONE_TSV_SHA256 = "2775f97c840af6ddc7af6a5b705ed902518a6e912aca79603e78d47fd6f603b8"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
PACK_SHA256 = {
    "9": "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    "A": "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
    "B": "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
    "C": "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090",
}
SYSTEM_SHA256 = {
    "helmet00": "3204efb25d509873cffe3e0d17c2d43c9fe77010a34d023b4e608bccec70b133",
    "helmet02": "4fe527df8ae60c2139596ffd4a929c5a39358138709746cdf564f31f3d8edb0b",
}
MIP_DIMENSIONS = tuple((256 >> level, 256 >> level) for level in range(6))
INDEX_CHAIN_BYTES = sum(width * height for width, height in MIP_DIMENSIONS)
PALETTE_OFFSET = INDEX_CHAIN_BYTES
VIDEO_BYTES = INDEX_CHAIN_BYTES + 1024
PACKED_FORMAT = 0x08860B29


class CompatibilityError(ValueError):
    """Raised when the pinned live-helmet corpus changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


#: This report ships in the release archive, so an input is named by what it is
#: rather than by where it sat on the machine that produced it. ``str(path)``
#: recorded the operator's own directories, which the release gate refuses and
#: which nobody should be publishing. Fixed labels also make the report
#: reproducible: the same disc and checkout produce the same bytes anywhere.
#: ``user-source`` is what the reader supplied; ``generation-evidence`` is what
#: an earlier reviewed step produced. Identity is carried by the size and
#: SHA-256 beside each label, which is the part that means anything.
USER_SOURCE = "user-source"
GENERATION_EVIDENCE = "generation-evidence"


def pin(path: Path, label: str) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {
        "path": label, "size": resolved.stat().st_size,
        "sha256": file_digest(resolved),
    }


def canonical_digest(value: object) -> str:
    return digest(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode())


def locate_range(entry: Entry, offset: int, length: int) -> list[dict[str, Any]]:
    require(0 <= offset and 0 < length and offset + length <= entry.size,
            "target range exceeds uniform package")
    relative = offset
    remaining = length
    pieces: list[dict[str, Any]] = []
    for segment in entry.segments:
        if relative >= segment.size:
            relative -= segment.size
            continue
        take = min(remaining, segment.size - relative)
        pieces.append({
            "pack_ordinal": segment.pack_ordinal,
            "pack_name": segment.pack_name,
            "pack_offset": segment.pack_offset + relative,
            "size": take,
        })
        remaining -= take
        relative = 0
        if not remaining:
            break
    require(remaining == 0, "target range mapping is incomplete")
    return pieces


def read_utf16(xbe: Xbe, address: int) -> str:
    value = xbe.utf16z_va(address)
    require(value is not None, f"null XBE string at 0x{address:08x}")
    return value


def validate_xbe(path: Path) -> dict[str, Any]:
    require(file_digest(path) == XBE_SHA256, "default.xbe SHA-256 mismatch")
    image = Xbe(path)
    strings = {
        "helmet00": read_utf16(image, 0x00E63F50),
        "helmet01": read_utf16(image, 0x00E63F64),
        "helmet02": read_utf16(image, 0x00E63F78),
    }
    require(strings == {
        "helmet00": "helmet00", "helmet01": "helmet01", "helmet02": "helmet02",
    }, "live helmet cache strings changed")

    def read(address: int, size: int) -> bytes:
        offset = image.va_to_offset(address, size)
        return image.data[offset:offset + size]

    table = struct.unpack("<16I", read(0x004EF388, 64))
    expected_table = (
        1, 2, 0, 1,       # HI_HELMET_A/accessories -> helmet00 duplicate slots
        5, 6, 4, 5,       # HI_HELMET_C/accessories -> helmet02 duplicate slots
        11, 12, 13, 14,   # facemask path; outside this importer claim
        15, 16, 8, 9,     # mouthpiece path; outside this importer claim
    )
    require(table == expected_table, "helmet material/texture route table changed")
    texture_table: list[dict[str, Any]] = []
    for index in range(6):
        pointer, context_first = struct.unpack(
            "<II", read(0x004EEAF8 + index * 8, 8))
        texture_table.append({
            "cache_index": index,
            "name_pointer": f"0x{pointer:08x}",
            "name": read_utf16(image, pointer),
            "context_first": context_first,
        })
    require([row["name"] for row in texture_table] == [
        "helmet00", "helmet00", "helmet01", "helmet01", "helmet02", "helmet02",
    ] and all(row["context_first"] == 1 for row in texture_table),
        "helmet cache entries changed")
    material_names = [
        "HI_HELMET_A", "HELMET_A_accessories", "HI_HELMET_C",
        "HELMET_C_accessories",
    ]
    material_indices = [1, 2, 5, 6]
    material_pointer_table = 0x004EEE68
    resolved_materials = []
    for index in material_indices:
        pointer = struct.unpack("<I", read(material_pointer_table + index * 4, 4))[0]
        resolved_materials.append(read_utf16(image, pointer))
    require(resolved_materials == material_names,
            "helmet material-name table changed")

    ranges = {
        "material_texture_writer_0x0008E3F0_64": (0x0008E3F0, 64,
            "e1bc93ece080f679677f8608023d969dc7b14d6a6bb835b7e75bd222704ad908"),
        "context_first_lookup_0x0008E580_48": (0x0008E580, 48,
            "7807834b25f567f9a5cd1dcd64ea3b73eae27c991ec44297a2aae13fa86e4218"),
        "cache_builder_0x0008E620_272": (0x0008E620, 272,
            "d6856d010c805b6f6fc328d6219348e7aa553ba9bd35cfd2176a3d5aff2b5cb3"),
        "helmet_binder_0x0008E9E0_448": (0x0008E9E0, 448,
            "d290a541259c1b5a113adbb44db0f6320804966180b09ff9c854ed38c902031a"),
        "player_builder_0x0008EFA0_1456": (0x0008EFA0, 1456,
            "022f7f9abd0aaa3ce7b3470086e814bc02011610e985e6a8124d21bca0e0fc01"),
    }
    range_rows: dict[str, Any] = {}
    for name, (address, size, expected) in ranges.items():
        actual = digest(read(address, size))
        require(actual == expected, f"XBE binding range changed: {name}")
        range_rows[name] = {
            "address": f"0x{address:08x}", "size": size, "sha256": actual,
        }
    return {
        "sha256": XBE_SHA256,
        "cache_entries": texture_table,
        "route_table_address": "0x004EF388",
        "route_table_u32": list(table),
        "proved_routes": [
            {
                "player_record_selector": "+0x0c bits 6..7 == 0",
                "call_range": "0x0008F020..0x0008F029",
                "cache_indices": [0, 1], "resource": "helmet00",
                "materials": ["HI_HELMET_A", "HELMET_A_accessories"],
                "write_calls": ["0x0008EA5C", "0x0008EA78"],
            },
            {
                "player_record_selector": "+0x0c bits 6..7 == 1",
                "call_range": "0x0008F020..0x0008F029",
                "cache_indices": [4, 5], "resource": "helmet02",
                "materials": ["HI_HELMET_C", "HELMET_C_accessories"],
                "write_calls": ["0x0008EA5C", "0x0008EA78"],
            },
        ],
        "material_texture_pointer_field": "+0x30",
        "material_texture_writer_store": "0x0008E422",
        "function_ranges": range_rows,
        "helmet01_uniform_resource_count": 0,
        "helmet01_behavior": (
            "context-first lookup followed by global fallback; this audit found no "
            "helmet01 TXTR in any of the 634 uniform packages"
        ),
    }


def parse_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def validate_scene_materials(path: Path, submeshes_path: Path) -> dict[str, Any]:
    rows = parse_tsv(path)
    wanted = {
        ("lo_body", "HI_HELMET_A"), ("lo_body", "HELMET_A_accessories"),
        ("lo_body", "HI_HELMET_C"), ("lo_body", "HELMET_C_accessories"),
        ("hi_head", "HI_HELMET_A"), ("hi_head", "HELMET_A_accessories"),
        ("hi_head", "HI_HELMET_C"), ("hi_head", "HELMET_C_accessories"),
    }
    selected = [row for row in rows if (row["scene_name"], row["material_name"]) in wanted]
    found = Counter((row["scene_name"], row["material_name"]) for row in selected)
    require(set(found) == wanted and all(value == 1 for value in found.values()),
            "shared player helmet material inventory changed")
    submeshes = parse_tsv(submeshes_path)
    geometry = [row for row in submeshes
                if (row["scene_name"], row["material_name"]) in wanted]
    geometry_counts = Counter((row["scene_name"], row["material_name"])
                              for row in geometry)
    require(all(geometry_counts[key] > 0 for key in wanted),
            "a proved helmet material has no indexed submesh geometry")
    return {
        "material_rows": [{
            "scene_name": row["scene_name"],
            "scene_index": int(row["scene_index"]),
            "outer_index": int(row["outer_index"]),
            "chunk_index": int(row["chunk_index"]),
            "material_index": int(row["material_index"]),
            "material_name": row["material_name"],
            "on_disk_texture_pointer": row["conversion_status"],
        } for row in selected],
        "submesh_occurrence_counts": {
            f"{scene}/{material}": geometry_counts[(scene, material)]
            for scene, material in sorted(wanted)
        },
        "interpretation": (
            "lo_body and hi_head both contain indexed geometry for each proved live "
            "helmet material; on-disk texture pointers are unmapped and are filled by "
            "the player binder"
        ),
    }


def run(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_path = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
    chunks_path = root / "reports/assets/nfl2k5_resource_chunks_v2.json"
    uniforms_path = root / "reports/assets/nfl2k5_uniform_inventory.json"
    standalone_path = root / "reports/assets/nfl2k5_uniform_standalone_txtr.tsv"
    xbe_path = root / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
    source_xiso = root / "ESPN NFL 2K5 (USA).xiso.iso"
    material_path = root / "reports/assets/nfl2k5_scne_material_textures.tsv"
    submesh_path = root / "reports/assets/nfl2k5_scne_submeshes.tsv"

    require(file_digest(index_path) == INDEX_SHA256, "canonical index SHA-256 mismatch")
    require(file_digest(chunks_path) == CHUNK_INVENTORY_SHA256,
            "chunk inventory SHA-256 mismatch")
    require(file_digest(uniforms_path) == UNIFORM_INVENTORY_SHA256,
            "uniform inventory SHA-256 mismatch")
    require(file_digest(standalone_path) == STANDALONE_TSV_SHA256,
            "standalone texture TSV SHA-256 mismatch")
    xbe_evidence = validate_xbe(xbe_path)
    scene_evidence = validate_scene_materials(material_path, submesh_path)

    chunks_value = json.loads(chunks_path.read_bytes())
    uniforms_value = json.loads(uniforms_path.read_bytes())
    require(chunks_value.get("schema") == "nfl2k5_resource_chunk_inventory/v1",
            "chunk inventory schema mismatch")
    require(uniforms_value.get("schema") == "nfl2k5_uniform_inventory/v1",
            "uniform inventory schema mismatch")
    packages = {int(row["outer_index"]): row for row in uniforms_value["packages"]}
    require(len(packages) == PACKAGE_COUNT and
            set(packages) == set(range(FIRST_OUTER, LAST_OUTER + 1)),
            "uniform package coverage changed")
    chunk_rows = {
        (int(row["outer_index"]), int(row["chunk_index"])): row
        for row in chunks_value["chunks"]
        if FIRST_OUTER <= int(row["outer_index"]) <= LAST_OUTER and
        int(row["chunk_index"]) in {11, 12, 13}
    }
    require(len(chunk_rows) == PACKAGE_COUNT * 3,
            "helmet/next-resource chunk coverage changed")
    standalone = {
        (int(row["outer_index"]), int(row["chunk_index"])): row
        for row in parse_tsv(standalone_path)
        if row["name"] in {"helmet00", "helmet02"}
    }
    require(len(standalone) == PACKAGE_COUNT * 2,
            "canonical standalone helmet rows changed")

    archive = parse_archive(index_path)
    for name, expected_hash in PACK_SHA256.items():
        pack = next(item for item in archive.packs if item.name == name)
        require(file_digest(pack.path) == expected_hash,
                f"extracted pack {name} SHA-256 mismatch")

    source_info = source_xiso.lstat()
    require(stat.S_ISREG(source_info.st_mode) and not stat.S_ISLNK(source_info.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_xiso.resolve(strict=True)
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(source_fd)
        require((opened.st_dev, opened.st_ino) ==
                (source_info.st_dev, source_info.st_ino) and
                opened.st_size == xiso.EXPECTED_XISO_SIZE,
                "source XISO identity/size changed")
        xdvdfs, _ = xiso.parse_xdvdfs(source_fd, opened.st_size)
        pack_records: dict[str, dict[str, Any]] = {}
        for name, expected_hash in PACK_SHA256.items():
            path = f"vc_53450030/{name}"
            record = xdvdfs.get(path.casefold())
            require(record is not None, f"source XISO pack {name} absent")
            assert record is not None
            require(xiso.sha256_fd(source_fd, record.byte_offset, record.size) ==
                    expected_hash, f"source XISO pack {name} SHA-256 mismatch")
            pack_records[name] = {
                "path": path, "sector": record.sector,
                "byte_offset": record.byte_offset, "size": record.size,
                "sha256": expected_hash,
            }

        rows: list[dict[str, Any]] = []
        layout_signatures: Counter[str] = Counter()
        family_counts: Counter[str] = Counter()
        family_span_hashes: dict[str, Counter[str]] = {
            name: Counter() for name in FAMILIES.values()
        }
        family_decoded_hashes: dict[str, Counter[str]] = {
            name: Counter() for name in FAMILIES.values()
        }
        pack_counts: Counter[str] = Counter()
        for outer_index in range(FIRST_OUTER, LAST_OUTER + 1):
            package = packages[outer_index]
            entry = archive.entries[outer_index]
            require(entry.name_id == int(package["outer_id"], 0) and
                    entry.size == int(package["outer_size"]),
                    f"outer {outer_index} identity changed")
            for chunk_index, family in FAMILIES.items():
                item = chunk_rows[(outer_index, chunk_index)]
                record, span, decoded, info = read_and_validate_span(archive, item)
                require(info is not None and record.kind == "TXTR" and
                        record.word_10 == COMPRESSED_SENTINEL and
                        record.word_08 == 128 and record.word_0c == VIDEO_BYTES and
                        record.stored_size + HEADER.size == len(span),
                        f"{package['logical_name']} {family} wrapper changed")
                texture = parse_texture(decoded, record.as_chunk())
                require(texture.name == family and texture.name_offset == 32 and
                        texture.descriptor_offset == 52 and texture.pixel_offset == 0 and
                        texture.palette_offset == PALETTE_OFFSET and
                        texture.packed_format == PACKED_FORMAT and
                        texture.packed_size == 0 and
                        texture.descriptor_flags == 0x80000000 and
                        texture.dimensions == 2 and texture.format_name == "P8" and
                        texture.format_code == 11 and texture.mip_levels == 6 and
                        texture.width == 256 and texture.height == 256 and
                        texture.depth == 1 and len(decoded) == 128 + VIDEO_BYTES and
                        digest(decoded[:128]) == SYSTEM_SHA256[family],
                        f"{package['logical_name']} {family} layout changed")
                canonical = standalone[(outer_index, chunk_index)]
                decoded_sha = digest(decoded)
                span_sha = digest(span)
                require(decoded_sha == canonical["decoded_sha256"],
                        f"{package['logical_name']} {family} decoded hash changed")
                next_item = chunk_rows[(outer_index, chunk_index + 1)]
                require(record.chunk_offset + len(span) == int(next_item["chunk_offset"]) and
                        int(next_item.get("zero_padding_before", 0)) == 0,
                        f"{package['logical_name']} {family} is not a fixed contiguous span")
                exact_scratch = minimum_vc_lz_overlap_scratch(
                    span[HEADER.size:HEADER.size + info.consumed_bytes],
                    record.stored_size, record.word_08 + record.word_0c,
                )
                require(record.word_14 >= exact_scratch,
                        f"{package['logical_name']} {family} retail alias scratch is unsafe")
                pieces = locate_range(entry, record.chunk_offset, len(span))
                require(len(pieces) == 1, f"{package['logical_name']} {family} crosses packs")
                piece = pieces[0]
                pack = pack_records[piece["pack_name"]]
                absolute = int(pack["byte_offset"]) + int(piece["pack_offset"])
                require(os.pread(source_fd, len(span), absolute) == span,
                        f"{package['logical_name']} {family} XISO span differs")

                layout = {
                    "kind": "TXTR", "system_bytes": 128,
                    "video_bytes": VIDEO_BYTES,
                    "name_offset": 32, "descriptor_offset": 52,
                    "pixel_offset": 0, "palette_offset": PALETTE_OFFSET,
                    "packed_format": f"0x{PACKED_FORMAT:08x}",
                    "packed_size": 0, "descriptor_flags": "0x80000000",
                    "dimensions": 2, "format": "P8", "mip_levels": 6,
                    "width": 256, "height": 256, "depth": 1,
                    "mip_dimensions": [list(value) for value in MIP_DIMENSIONS],
                    "index_chain_bytes": INDEX_CHAIN_BYTES,
                    "palette_bytes": 1024,
                }
                layout_signature = canonical_digest(layout)
                layout_signatures[layout_signature] += 1
                family_counts[family] += 1
                family_span_hashes[family][span_sha] += 1
                family_decoded_hashes[family][decoded_sha] += 1
                pack_counts[str(piece["pack_name"])] += 1
                rows.append({
                    "selector": {
                        "asset_code": package["asset_code"],
                        "side": package["side_code"],
                        "side_context": package["side_context"],
                        "variant": int(package["variant_id"]),
                        "logical_name": package["logical_name"],
                    },
                    "family": family,
                    "live_player_mode": 0 if family == "helmet00" else 1,
                    "material_pair": [
                        "HI_HELMET_A", "HELMET_A_accessories"
                    ] if family == "helmet00" else [
                        "HI_HELMET_C", "HELMET_C_accessories"
                    ],
                    "outer_index": outer_index,
                    "outer_id": package["outer_id"],
                    "outer_size": entry.size,
                    "chunk_index": chunk_index,
                    "chunk_offset": record.chunk_offset,
                    "stored_size": record.stored_size,
                    "span_size": len(span),
                    "system_bytes": record.word_08,
                    "video_bytes": record.word_0c,
                    "decoded_size": len(decoded),
                    "compression_magic": "0xfeedbeef",
                    "overlap_scratch_bytes": record.word_14,
                    "retail_exact_minimum_overlap_scratch_bytes": exact_scratch,
                    "stream_tag": info.stream_tag,
                    "offset_bits": info.offset_bits,
                    "lz_consumed_bytes": info.consumed_bytes,
                    "lz_unused_bytes": record.stored_size - info.consumed_bytes,
                    "system_sha256": digest(decoded[:128]),
                    "decoded_sha256": decoded_sha,
                    "span_sha256": span_sha,
                    "rgba_sha256": canonical["rgba_sha256"],
                    "retail_png_path": canonical["png_path"],
                    "layout_signature_sha256": layout_signature,
                    "span_segments": pieces,
                    "xiso_pack_path": pack["path"],
                    "xiso_pack_sector": pack["sector"],
                    "xiso_pack_byte_offset": pack["byte_offset"],
                    "xiso_pack_size": pack["size"],
                    "xiso_pack_sha256": pack["sha256"],
                    "xiso_absolute_span_offset": absolute,
                    "source_xiso_span_matches": True,
                    "compatible_with_fixed_span_png_importer": True,
                    "incompatibility_reasons": [],
                })
    finally:
        os.close(source_fd)

    require(len(rows) == 1268 and family_counts == Counter({
        "helmet00": 634, "helmet02": 634,
    }) and len(layout_signatures) == 1,
        "live helmet resource/layout coverage changed")
    pair_equal: dict[str, dict[str, int]] = {}
    indexed = {(row["outer_index"], row["family"]): row for row in rows}
    for family in FAMILIES.values():
        home_away = [(indexed[(home, family)], indexed[(home + 317, family)])
                     for home in range(FIRST_OUTER, FIRST_OUTER + 317)]
        pair_equal[family] = {
            "same_span": sum(left["span_sha256"] == right["span_sha256"]
                             for left, right in home_away),
            "same_decoded": sum(left["decoded_sha256"] == right["decoded_sha256"]
                                for left, right in home_away),
            "same_rgba": sum(left["rgba_sha256"] == right["rgba_sha256"]
                             for left, right in home_away),
        }

    def distribution(field: str) -> dict[str, int]:
        return {str(key): value for key, value in sorted(
            Counter(int(row[field]) for row in rows).items())
        }

    layout_signature = next(iter(layout_signatures))
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "inputs": {
            "canonical_index": pin(
                index_path,
                f"{USER_SOURCE}/{index_path.parent.name}/{index_path.name}"),
            "chunk_inventory": pin(
                chunks_path, f"{GENERATION_EVIDENCE}/{chunks_path.name}"),
            "uniform_inventory": pin(
                uniforms_path, f"{GENERATION_EVIDENCE}/{uniforms_path.name}"),
            "standalone_texture_inventory": pin(
                standalone_path, f"{GENERATION_EVIDENCE}/{standalone_path.name}"),
            "default_xbe": {"path": f"{USER_SOURCE}/{xbe_path.name}",
                            "sha256": XBE_SHA256},
            "retail_xiso": {
                "path": f"{USER_SOURCE}/ESPN NFL 2K5.xiso.iso",
                "size": xiso.EXPECTED_XISO_SIZE,
                "expected_sha256": xiso.EXPECTED_XISO_SHA256,
                "opened_read_only": True,
            },
            "packs": pack_records,
        },
        "summary": {
            "uniform_key_count": 634,
            "resource_count": 1268,
            "helmet00_count": 634,
            "helmet02_count": 634,
            "helmet01_uniform_resource_count": 0,
            "home_resource_count": 634,
            "away_resource_count": 634,
            "compatible_resource_count": 1268,
            "incompatible_resource_count": 0,
            "common_layout_class_count": len(layout_signatures),
            "common_layout_signature_sha256": layout_signature,
            "allocation_class_count": len(set(
                (row["family"], row["stored_size"]) for row in rows)),
            "stored_size_minimum": min(row["stored_size"] for row in rows),
            "stored_size_maximum": max(row["stored_size"] for row in rows),
            "span_size_minimum": min(row["span_size"] for row in rows),
            "span_size_maximum": max(row["span_size"] for row in rows),
            "stream_tag_minimum": min(row["stream_tag"] for row in rows),
            "stream_tag_maximum": max(row["stream_tag"] for row in rows),
            "offset_bits_minimum": min(row["offset_bits"] for row in rows),
            "offset_bits_maximum": max(row["offset_bits"] for row in rows),
            "retail_exact_alias_scratch_minimum": min(
                row["retail_exact_minimum_overlap_scratch_bytes"] for row in rows),
            "retail_exact_alias_scratch_maximum": max(
                row["retail_exact_minimum_overlap_scratch_bytes"] for row in rows),
            "all_retail_wrappers_cover_exact_alias_requirement": True,
            "all_spans_contiguous_with_next_resource": True,
            "all_spans_single_pack_segment": True,
            "all_source_xiso_spans_match": True,
            "unique_span_count_by_family": {
                family: len(family_span_hashes[family]) for family in FAMILIES.values()
            },
            "unique_decoded_count_by_family": {
                family: len(family_decoded_hashes[family]) for family in FAMILIES.values()
            },
            "home_away_pair_equality": pair_equal,
            "pack_resource_counts": dict(sorted(pack_counts.items())),
            "stored_size_distribution": distribution("stored_size"),
            "overlap_scratch_distribution": distribution("overlap_scratch_bytes"),
            "stream_tag_distribution": distribution("stream_tag"),
            "offset_bits_distribution": distribution("offset_bits"),
        },
        "compatible_layout": {
            "layout_signature_sha256": layout_signature,
            "kind": "TXTR", "system_bytes": 128,
            "video_bytes": VIDEO_BYTES, "decoded_size": 128 + VIDEO_BYTES,
            "name_offsets": {"helmet00": 32, "helmet02": 32},
            "system_sha256": SYSTEM_SHA256,
            "descriptor_offset": 52, "pixel_offset": 0,
            "palette_offset": PALETTE_OFFSET,
            "packed_format": f"0x{PACKED_FORMAT:08x}",
            "descriptor_flags": "0x80000000",
            "format": "P8", "mip_levels": 6,
            "width": 256, "height": 256, "depth": 1,
            "mip_dimensions": [list(value) for value in MIP_DIMENSIONS],
            "mip_index_bytes": [width * height for width, height in MIP_DIMENSIONS],
            "index_chain_bytes": INDEX_CHAIN_BYTES,
            "palette_bytes": 1024,
            "each_mip_swizzled_independently": True,
            "compressed_fixed_span": True,
            "writer_may_only_raise_wrapper_overlap_scratch": True,
        },
        "xbe_live_binding": xbe_evidence,
        "shared_player_scene_binding": scene_evidence,
        "claims": {
            "actual_live_3d_path_not_team_select_cards": True,
            "all_uniform_keys_audited": True,
            "offline_fixed_span_importer_compatible": True,
            "team_select_helm_cards_are_a_separate_resource_family": True,
            "originals_modified": False,
            "xemu_started": False,
            "title_executed": False,
            "runtime_visibility_proved": False,
            "portme": [
                "PORTME(0x0008F020): recover the original source name for player "
                "record +0x0c bits 6..7; this report proves modes 0 and 1 routing only.",
                "PORTME(helmet01): identify the global-fallback helmet01 owner; no "
                "uniform package contains that resource.",
                "PORTME(runtime): capture a close-up only after the offline copy-only "
                "artifact is frozen; no runtime visibility is claimed here.",
            ],
        },
        "resources": rows,
    }
    return report, rows


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "logical_name", "asset_code", "side", "variant", "family",
        "live_player_mode", "outer_index", "outer_id", "outer_size",
        "chunk_index", "chunk_offset", "stored_size", "span_size",
        "system_bytes", "video_bytes", "overlap_scratch_bytes",
        "retail_exact_minimum_overlap_scratch_bytes", "stream_tag", "offset_bits",
        "lz_consumed_bytes", "lz_unused_bytes", "system_sha256",
        "decoded_sha256", "span_sha256", "rgba_sha256",
        "layout_signature_sha256", "pack_name", "pack_offset",
        "xiso_absolute_span_offset", "retail_png_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, delimiter="\t", fieldnames=fields)
        writer.writeheader()
        for row in rows:
            selector = row["selector"]
            piece = row["span_segments"][0]
            writer.writerow({
                "logical_name": selector["logical_name"],
                "asset_code": selector["asset_code"], "side": selector["side"],
                "variant": selector["variant"], "family": row["family"],
                "live_player_mode": row["live_player_mode"],
                "outer_index": row["outer_index"], "outer_id": row["outer_id"],
                "outer_size": row["outer_size"], "chunk_index": row["chunk_index"],
                "chunk_offset": row["chunk_offset"], "stored_size": row["stored_size"],
                "span_size": row["span_size"], "system_bytes": row["system_bytes"],
                "video_bytes": row["video_bytes"],
                "overlap_scratch_bytes": row["overlap_scratch_bytes"],
                "retail_exact_minimum_overlap_scratch_bytes":
                    row["retail_exact_minimum_overlap_scratch_bytes"],
                "stream_tag": row["stream_tag"], "offset_bits": row["offset_bits"],
                "lz_consumed_bytes": row["lz_consumed_bytes"],
                "lz_unused_bytes": row["lz_unused_bytes"],
                "system_sha256": row["system_sha256"],
                "decoded_sha256": row["decoded_sha256"],
                "span_sha256": row["span_sha256"], "rgba_sha256": row["rgba_sha256"],
                "layout_signature_sha256": row["layout_signature_sha256"],
                "pack_name": piece["pack_name"], "pack_offset": piece["pack_offset"],
                "xiso_absolute_span_offset": row["xiso_absolute_span_offset"],
                "retail_png_path": row["retail_png_path"],
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-json", type=Path,
                        default=Path("reports/assets/nfl2k5_live_helmet_txtr_compatibility.json"))
    parser.add_argument("--output-tsv", type=Path,
                        default=Path("reports/assets/nfl2k5_live_helmet_txtr_compatibility.tsv"))
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        report, rows = run(root)
        json_path = args.output_json if args.output_json.is_absolute() else root / args.output_json
        tsv_path = args.output_tsv if args.output_tsv.is_absolute() else root / args.output_tsv
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        write_tsv(tsv_path, rows)
        summary = report["summary"]
        print(
            "NFL_LIVE_HELMET_TXTR_COMPATIBILITY_OK "
            f"resources={summary['resource_count']} layouts="
            f"{summary['common_layout_class_count']} allocations="
            f"{summary['allocation_class_count']} stored="
            f"{summary['stored_size_minimum']}..{summary['stored_size_maximum']} "
            f"runtime=false xemu_started=false"
        )
        return 0
    except (CompatibilityError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
