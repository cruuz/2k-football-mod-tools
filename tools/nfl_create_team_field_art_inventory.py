#!/usr/bin/env python3
"""Prove NFL 2K5's create-team live field-art TXTR package family.

The bounded corpus is the exact 126-entry ``ct%s%c.iff`` family selected by
the retail XBE for a created team.  This tool intentionally does not scan for
lookalikes: expected filenames, archive hashes, package order, TXTR layouts,
and the XBE owner path all have to match before it writes a report.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import HEADER, decode_chunk, parse_chunks, parse_texture
from xbe_info import Xbe


SCHEMA = "nfl2k5_create_team_field_art_inventory/v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
DEFAULT_XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
DEFAULT_JSON = ROOT / "reports/assets/nfl2k5_create_team_field_art_inventory.json"
DEFAULT_TSV = ROOT / "reports/assets/nfl2k5_create_team_field_art_inventory.tsv"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
XBE_SIZE = 11_948_032
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
PACK0_SIZE = 193_710_080
PACK0_SHA256 = INDEX_SHA256
FIRST_OUTER = 384
LAST_OUTER = 509
LOGO_CODES = (33, *range(50, 86), *range(95, 100))
WEATHERS = (("D", "dry"), ("R", "rain"), ("S", "snow"))
TEXTURES = (
    ("center_logo", 256, 256, 6, 0x15540, 88384),
    ("endzone_north_left", 256, 128, 5, 0xAA80, 44672),
    ("endzone_north_middle", 256, 128, 5, 0xAA80, 44672),
    ("endzone_north_right", 256, 128, 5, 0xAA80, 44672),
    ("endzone_south_left", 256, 128, 5, 0xAA80, 44672),
    ("endzone_south_middle", 256, 128, 5, 0xAA80, 44672),
    ("endzone_south_right", 256, 128, 5, 0xAA80, 44672),
    ("pad_north", 128, 128, 5, 0x5540, 22848),
    ("pad_south", 128, 128, 5, 0x5540, 22848),
)


class FieldArtError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FieldArtError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def resource_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF


def read_va(xbe: Xbe, address: int, size: int) -> bytes:
    offset = xbe.va_to_offset(address, size)
    return xbe.data[offset:offset + size]


def xbe_evidence(path: Path) -> dict[str, object]:
    require(path.is_file() and path.stat().st_size == XBE_SIZE and
            file_digest(path) == XBE_SHA256, "retail default.xbe identity changed")
    xbe = Xbe(path)
    expected_strings = {
        0x00E610B8: "ct%s%c.iff",
        0x00E61548: "CTGRAPHIC",
        0x00E66350: "center_logo",
        0x00E66368: "endzone_N_L",
        0x00E66380: "endzone_north_left",
        0x00E663A8: "endzone_N_M",
        0x00E663C0: "endzone_north_middle",
        0x00E663EC: "endzone_N_R",
        0x00E66404: "endzone_north_right",
        0x00E6642C: "endzone_S_L",
        0x00E66444: "endzone_south_left",
        0x00E6646C: "endzone_S_M",
        0x00E66484: "endzone_south_middle",
        0x00E664B0: "endzone_S_R",
        0x00E664C8: "endzone_south_right",
        0x00E66174: "pad_north",
        0x00E66188: "pad_south",
        0x00E6619C: "goal1_north",
        0x00E661B4: "goal2_south",
        0x00E661CC: "goalpost",
        0x00E661E0: "pad",
        0x00E664F0: "field",
        0x00E665F8: "snow_layer",
        0x00E63680: "divot_snow1",
        0x00E63698: "divot_dry1",
    }
    actual_strings = {address: xbe.utf16z_va(address)
                      for address in expected_strings}
    require(actual_strings == expected_strings, "XBE field-art strings changed")

    anchors = {
        # default 'd', rain predicate -> 'r', snow predicate -> 's'
        0x00062C25: "be64000000e8b14f010085c07405be72000000",
        0x00062C38: "e8734f010085c07405be73000000",
        # active-team +0x14, ct format, destination b306f0
        0x00062C96: "668974240ce8c04701008b48148d54240852894c240c68b810e600ba10000000b9f006b300e85077feff",
        # CTGRAPHIC registration consumes b306f0
        0x0006318F: "6a006a00e8185efdff50687c3eb300baf006b300b94815e600e8a30dfeff",
        # field object and snow-layer TXTR lookups
        0x0009C443: "68f064e600ba466c646433c9e88c85faff",
        0x0009C461: "68f865e600ba5458545233c9e86e85faff",
        # the snow predicate selects divot_snow1 over divot_dry1
        0x00086430: "e87b17ffff33c985c0ba545854527407688036e600eb05689836e600e88fe5fbff",
    }
    anchor_rows = []
    for address, expected_hex in anchors.items():
        expected = bytes.fromhex(expected_hex)
        actual = read_va(xbe, address, len(expected))
        require(actual == expected, f"XBE owner anchor changed at 0x{address:08x}")
        anchor_rows.append({"va": f"0x{address:08x}", "size": len(actual),
                            "sha256": digest(actual), "hex": actual.hex()})

    pointer_table = []
    expected_pairs = [
        ("center_logo", "center_logo"),
        ("endzone_N_L", "endzone_north_left"),
        ("endzone_N_M", "endzone_north_middle"),
        ("endzone_N_R", "endzone_north_right"),
        ("endzone_S_L", "endzone_south_left"),
        ("endzone_S_M", "endzone_south_middle"),
        ("endzone_S_R", "endzone_south_right"),
    ]
    for index, (short_name, resource_name) in enumerate(expected_pairs):
        address = 0x004F0090 + index * 8
        values = struct.unpack("<II", read_va(xbe, address, 8))
        recovered = (xbe.utf16z_va(values[0]), xbe.utf16z_va(values[1]))
        require(recovered == (short_name, resource_name),
                f"field material table pair {index} changed")
        pointer_table.append({"pair_index": index, "table_va": f"0x{address:08x}",
                              "material_slot": short_name,
                              "txtr_resource": resource_name,
                              "pointer_vas": [f"0x{value:08x}" for value in values]})

    pad_resource_values = struct.unpack("<II", read_va(xbe, 0x004EFFE8, 8))
    pad_resources = [xbe.utf16z_va(value) for value in pad_resource_values]
    require(pad_resources == ["pad_north", "pad_south"],
            "goalpost pad resource table changed")
    goal_anchor_values = struct.unpack("<II", read_va(xbe, 0x004EFFF0, 8))
    goal_anchors = [xbe.utf16z_va(value) for value in goal_anchor_values]
    require(goal_anchors == ["goal1_north", "goal2_south"],
            "goalpost anchor table changed")

    ranges = []
    for name, start, end in (
        ("field_resource_selector_and_registration", 0x00062BE0, 0x000632A4),
        ("active_team_getter", 0x00077460, 0x00077466),
        ("snow_predicate", 0x00077BB0, 0x00077BDF),
        ("rain_predicate", 0x00077BE0, 0x00077C0F),
        ("goalpost_pad_texture_binder", 0x00098220, 0x0009856D),
        ("field_geometry_builder", 0x0009B880, 0x0009B949),
        ("field_material_texture_binder", 0x0009C5DE, 0x0009C66B),
    ):
        body = read_va(xbe, start, end - start)
        ranges.append({"name": name, "start": f"0x{start:08x}",
                       "end_exclusive": f"0x{end:08x}", "size": len(body),
                       "sha256": digest(body)})

    return {
        "path": str(path.resolve()), "size": path.stat().st_size,
        "sha256": XBE_SHA256, "anchors": anchor_rows,
        "function_ranges": ranges,
        "selector": {
            "builder_function_start": "0x00062be0",
            "active_team_getter": "0x00077460",
            "active_team_logo_code_field_offset": "0x14",
            "filename_format_va": "0x00e610b8",
            "filename_format": "ct%s%c.iff",
            "weather_default_instruction": "0x00062c25",
            "weather_default_suffix": "d",
            "rain_predicate": "0x00077be0",
            "rain_suffix_write": "0x00062c33",
            "rain_suffix": "r",
            "snow_predicate": "0x00077bb0",
            "snow_suffix_write": "0x00062c41",
            "snow_suffix": "s",
            "snow_predicate_semantic_witness": {
                "site": "0x00086430", "true_texture": "divot_snow1",
                "false_texture": "divot_dry1",
            },
            "destination_buffer": "0x00b306f0",
        },
        "resource_registration": {
            "site": "0x0006318f", "resource_label_va": "0x00e61548",
            "resource_label": "CTGRAPHIC", "filename_buffer": "0x00b306f0",
            "registration_call": "0x00043f50",
        },
        "live_field_owner": {
            "field_object_lookup_site": "0x0009c443",
            "field_object_name": "field", "field_object_fourcc": "Fldd",
            "snow_layer_txtr_lookup_site": "0x0009c461",
            "field_material_binding_table": pointer_table,
            "field_material_binding_loop": {
                "start": "0x0009c5de", "end_exclusive": "0x0009c66b",
                "table_start": "0x004f0090", "table_end_exclusive": "0x004f00c8",
                "texture_lookup_fourcc": "TXTR", "texture_pointer_store": "0x0009c659",
                "material_texture_pointer_field": "+0x30",
            },
            "goalpost_pad_owner": {
                "function_start": "0x00098220",
                "scene_name": "goalpost", "material_name": "pad",
                "resource_table_va": "0x004effe8",
                "resources": pad_resources,
                "resource_pointer_vas": [f"0x{value:08x}" for value in pad_resource_values],
                "goal_anchor_table_va": "0x004efff0",
                "goal_anchors": goal_anchors,
                "goal_anchor_pointer_vas": [f"0x{value:08x}" for value in goal_anchor_values],
                "texture_lookup_site": "0x000983ed",
                "texture_pointer_store": "0x00098409",
                "material_texture_pointer_field": "+0x30",
            },
            "classification": (
                "gameplay field geometry/material TXTRs; not menu or Team Select art"
            ),
        },
    }


def build(index_path: Path, xbe_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    require(index_path.is_file() and index_path.stat().st_size == INDEX_SIZE and
            file_digest(index_path) == INDEX_SHA256, "retail pack 0 identity changed")
    archive = parse_archive(index_path)
    expected_names = [f"ct{code}{suffix}.iff"
                      for suffix, _ in WEATHERS for code in LOGO_CODES]
    require(len(expected_names) == 126, "internal expected-name count changed")

    rows: list[dict[str, object]] = []
    packages = []
    for ordinal, (outer_index, logical_name) in enumerate(
            zip(range(FIRST_OUTER, LAST_OUTER + 1), expected_names)):
        entry = archive.entries[outer_index]
        expected_id = resource_id(logical_name)
        require(entry.name_id == expected_id and len(entry.segments) == 1 and
                entry.segments[0].pack_name == "0" and
                entry.segments[0].pack_offset == entry.virtual_offset,
                f"outer {outer_index}: filename/hash/pack mapping changed")
        suffix = logical_name[-5].upper()
        weather = dict(WEATHERS)[suffix]
        logo_code = int(logical_name[2:-5])
        data = read_entry_bytes(archive, entry)
        chunks = parse_chunks(data)
        require(len(chunks) == len(TEXTURES),
                f"outer {outer_index}: chunk count changed")
        cursor = 0
        package_rows = []
        for chunk, expected in zip(chunks, TEXTURES):
            name, width, height, mip_levels, palette_offset, video_bytes = expected
            require(chunk.index == len(package_rows) and chunk.offset == cursor and
                    chunk.kind == "TXTR" and
                    chunk.system_bytes == 128 and chunk.video_bytes == video_bytes and
                    chunk.reserved0 == chunk.reserved1 == 0 and
                    ((chunk.compressed and chunk.overlap_scratch_bytes > 0) or
                     (not chunk.compressed and chunk.compression_magic == 0 and
                      chunk.overlap_scratch_bytes == 0 and
                      chunk.stored_size == 128 + video_bytes)),
                    f"outer {outer_index} chunk {chunk.index}: wrapper changed")
            span = data[chunk.offset:chunk.end_offset]
            decoded, info = decode_chunk(data, chunk)
            require(len(decoded) == 128 + video_bytes,
                    f"outer {outer_index} chunk {chunk.index}: decode failed")
            texture = parse_texture(decoded, chunk)
            require(texture.name == name and texture.name_offset == 32 and
                    texture.pixel_offset == 0 and texture.palette_offset == palette_offset and
                    texture.format_code == 0x0B and texture.format_name == "P8" and
                    texture.mip_levels == mip_levels and texture.width == width and
                    texture.height == height and texture.depth == 1 and
                    texture.dimensions == 2 and texture.packed_size == 0 and
                    texture.descriptor_flags == 0x80000000,
                    f"outer {outer_index} chunk {chunk.index}: TXTR layout changed")
            row = {
                "selector": f"{logo_code}:{suffix}:{name}",
                "logical_name": logical_name, "logo_code": logo_code,
                "weather_suffix": suffix, "weather": weather,
                "outer_index": outer_index, "outer_id": f"0x{entry.name_id:08x}",
                "outer_size": entry.size, "pack_path": "vc_53450030/0",
                "pack_offset": entry.virtual_offset,
                "chunk_index": chunk.index, "chunk_offset": chunk.offset,
                "span_size": len(span), "stored_size": chunk.stored_size,
                "system_bytes": chunk.system_bytes, "video_bytes": chunk.video_bytes,
                "compressed": chunk.compressed,
                "overlap_scratch_bytes": chunk.overlap_scratch_bytes,
                "stream_tag": info.stream_tag if info is not None else None,
                "offset_bits": info.offset_bits if info is not None else None,
                "length_bits": info.length_bits if info is not None else None,
                "lz_consumed_bytes": info.consumed_bytes if info is not None else None,
                "lz_unused_bytes": (chunk.stored_size - info.consumed_bytes
                                    if info is not None else None),
                "name": texture.name, "descriptor_offset": texture.descriptor_offset,
                "pixel_offset": texture.pixel_offset,
                "palette_offset": texture.palette_offset,
                "packed_format": f"0x{texture.packed_format:08x}",
                "packed_size": f"0x{texture.packed_size:08x}",
                "format_name": texture.format_name, "width": width, "height": height,
                "depth": texture.depth, "mip_levels": mip_levels,
                "index_chain_bytes": palette_offset, "palette_bytes": 1024,
                "span_sha256": digest(span), "decoded_sha256": digest(decoded),
                "system_sha256": digest(decoded[:128]),
                "video_sha256": digest(decoded[128:]),
                "complete_header": ["TXTR", *HEADER.unpack_from(span)[1:]],
            }
            rows.append(row)
            package_rows.append(row)
            cursor = chunk.end_offset
        require(cursor == entry.size, f"outer {outer_index}: package has trailing data")
        packages.append({
            "ordinal": ordinal, "logical_name": logical_name,
            "logo_code": logo_code, "weather_suffix": suffix, "weather": weather,
            "outer_index": outer_index, "outer_id": f"0x{entry.name_id:08x}",
            "expected_outer_id": f"0x{expected_id:08x}", "outer_size": entry.size,
            "pack_offset": entry.virtual_offset, "package_sha256": digest(data),
            "texture_selectors": [row["selector"] for row in package_rows],
        })

    require(len(rows) == 126 * 9 and
            {row["selector"] for row in rows} == {f"{code}:{suffix}:{name}"
                for suffix, _ in WEATHERS for code in LOGO_CODES
                for name, *_ in TEXTURES}, "field-art selector set changed")

    by_name = {}
    for name, *_ in TEXTURES:
        selected = [row for row in rows if row["name"] == name]
        by_name[name] = {
            "count": len(selected), "width": selected[0]["width"],
            "height": selected[0]["height"], "mip_levels": selected[0]["mip_levels"],
            "index_chain_bytes": selected[0]["index_chain_bytes"],
            "video_bytes": selected[0]["video_bytes"],
            "stored_size_min": min(int(row["stored_size"]) for row in selected),
            "stored_size_max": max(int(row["stored_size"]) for row in selected),
            "compressed_count": sum(bool(row["compressed"]) for row in selected),
            "raw_count": sum(not bool(row["compressed"]) for row in selected),
            "lz_unused_bytes_min": min((int(row["lz_unused_bytes"]) for row in selected
                                         if row["lz_unused_bytes"] is not None), default=None),
            "lz_unused_bytes_max": max((int(row["lz_unused_bytes"]) for row in selected
                                         if row["lz_unused_bytes"] is not None), default=None),
        }
    summary = {
        "package_count": len(packages), "logo_code_count": len(LOGO_CODES),
        "weather_variant_count": len(WEATHERS), "texture_count": len(rows),
        "textures_per_package": len(TEXTURES), "format_counts": dict(Counter(
            str(row["format_name"]) for row in rows)),
        "compressed_texture_count": sum(bool(row["compressed"]) for row in rows),
        "raw_texture_count": sum(not bool(row["compressed"]) for row in rows),
        "texture_family_counts": dict(Counter(str(row["name"]) for row in rows)),
        "stream_tag_counts": {str(key): value for key, value in Counter(
            int(row["stream_tag"]) for row in rows
            if row["stream_tag"] is not None).items()},
        "offset_bits_counts": {str(key): value for key, value in Counter(
            int(row["offset_bits"]) for row in rows
            if row["offset_bits"] is not None).items()},
    }
    result = {
        "schema": SCHEMA,
        "source": {"index_path": str(index_path.resolve()), "index_size": INDEX_SIZE,
                   "index_sha256": INDEX_SHA256, "pack_path": "vc_53450030/0",
                   "pack_size": PACK0_SIZE, "pack_sha256": PACK0_SHA256},
        "name_id_algorithm": "CRC32(uppercase UTF-16LE filename)",
        "selector_space": {
            "filename_format": "ct{logo_code}{weather_suffix}.iff",
            "logo_codes": list(LOGO_CODES),
            "weather_suffixes": {suffix: weather for suffix, weather in WEATHERS},
            "outer_range_inclusive": [FIRST_OUTER, LAST_OUTER],
        },
        "summary": summary, "layout_profiles": by_name,
        "xbe_runtime_owner": xbe_evidence(xbe_path),
        "packages": packages, "textures": rows,
        "claims": {
            "static_live_field_owner_proved": True,
            "menu_or_team_select_imagery": False,
            "fixed_allocations_enumerated": True,
            "all_mips_enumerated": True,
            "originals_modified": False, "xemu_started": False,
            "title_executed": False, "runtime_visibility_proved": False,
            "portme": (
                "PORTME(runtime): capture a created-team game before claiming the "
                "patched field art is visible on-screen."
            ),
        },
    }
    return result, rows


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "selector", "logical_name", "logo_code", "weather_suffix", "weather",
        "outer_index", "outer_id", "outer_size", "pack_path", "pack_offset",
        "chunk_index", "chunk_offset", "span_size", "stored_size", "system_bytes",
        "video_bytes", "compressed", "overlap_scratch_bytes", "stream_tag", "offset_bits",
        "length_bits", "lz_consumed_bytes", "lz_unused_bytes", "name",
        "descriptor_offset", "pixel_offset", "palette_offset", "packed_format",
        "format_name", "width", "height", "depth", "mip_levels",
        "index_chain_bytes", "palette_bytes", "span_sha256", "decoded_sha256",
        "system_sha256", "video_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--xbe", type=Path, default=DEFAULT_XBE)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--tsv", type=Path, default=DEFAULT_TSV)
    args = parser.parse_args()
    try:
        report, rows = build(args.index, args.xbe)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        write_tsv(args.tsv, rows)
        print("NFL_CREATE_TEAM_FIELD_ART_INVENTORY_OK "
              f"packages={report['summary']['package_count']} "
              f"textures={report['summary']['texture_count']} "
              "live_static=true runtime=false xemu_started=false")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
