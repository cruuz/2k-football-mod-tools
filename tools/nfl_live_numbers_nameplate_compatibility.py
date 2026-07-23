#!/usr/bin/env python3
"""Audit live NFL 2K5 number glyphs and player-name art across 634 uniforms.

This is a read-only, fail-closed corpus audit.  It joins the uniform selector
inventory, every standalone digit/name TXTR, the paired NAME metrics object,
the source XISO extents, and the focused executable trace.  It does not start
the title or modify any retail input.
"""

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
from nfl_txtr import (COMPRESSED_SENTINEL, HEADER, minimum_vc_lz_overlap_scratch,
                      parse_texture)
from nfl_uniform_inventory import (logical_name_candidates, parse_name,
                                   read_and_validate_span)
import nfl_uniform_color_xiso_direct_patch as xiso


SCHEMA = "nfl2k5_live_numbers_nameplate_compatibility/v1"
FIRST_OUTER = 3613
LAST_OUTER = 4246
PACKAGE_COUNT = 634
DIGIT_CHUNKS = tuple(range(13, 43))
NAME_ATLAS_CHUNK = 43
NAME_METRICS_CHUNK = 44
ART_CHUNKS = DIGIT_CHUNKS + (NAME_ATLAS_CHUNK,)
PACK_SHA256 = {
    "9": "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    "A": "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
    "B": "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
    "C": "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090",
}


class CompatibilityError(ValueError):
    """Raised when any corpus or report invariant fails."""


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


def canonical_digest(value: object) -> str:
    return digest(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8"))


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def locate_range(entry: Entry, offset: int, length: int) -> list[dict[str, int | str]]:
    require(0 <= offset and 0 < length and offset + length <= entry.size,
            "resource range exceeds outer entry")
    skip = offset
    remaining = length
    result: list[dict[str, int | str]] = []
    entry_cursor = 0
    for segment in entry.segments:
        if skip >= segment.size:
            skip -= segment.size
            entry_cursor += segment.size
            continue
        amount = min(remaining, segment.size - skip)
        result.append({
            "pack_ordinal": segment.pack_ordinal,
            "pack_name": segment.pack_name,
            "pack_offset": segment.pack_offset + skip,
            "entry_offset": entry_cursor + skip,
            "size": amount,
        })
        remaining -= amount
        skip = 0
        entry_cursor += segment.size
        if remaining == 0:
            break
    require(remaining == 0, "resource range mapping is incomplete")
    return result


def mip_dimensions(width: int, height: int, levels: int) -> list[list[int]]:
    result: list[list[int]] = []
    for level in range(levels):
        require(width > 0 and height > 0, "mip chain reaches zero")
        result.append([width, height])
        if level + 1 != levels:
            require(width % 2 == 0 and height % 2 == 0,
                    "mip chain cannot be halved exactly")
            width //= 2
            height //= 2
    return result


def family_for_name(name: str) -> tuple[str, int | None]:
    if name == "names":
        return "nameplate_atlas", None
    if name.isdigit() and 48 <= int(name) <= 57:
        return "jersey_digit", int(name) - 48
    if name.startswith("hn") and name[2:].isdigit() and 48 <= int(name[2:]) <= 57:
        return "helmet_digit", int(name[2:]) - 48
    if name.startswith("an") and name[2:].isdigit() and 48 <= int(name[2:]) <= 57:
        return "arm_digit", int(name[2:]) - 48
    raise CompatibilityError(f"unexpected live-art texture name {name!r}")


def expected_chunk(family: str, digit: int | None) -> int:
    if family == "jersey_digit":
        assert digit is not None
        return 13 + digit
    if family == "helmet_digit":
        assert digit is not None
        return 23 + digit
    if family == "arm_digit":
        assert digit is not None
        return 33 + digit
    require(family == "nameplate_atlas" and digit is None,
            "unknown family/chunk mapping")
    return NAME_ATLAS_CHUNK


def layout_projection(record: Any, texture: Any) -> dict[str, object]:
    dimensions = mip_dimensions(texture.width, texture.height, texture.mip_levels)
    chain_bytes = sum(width * height for width, height in dimensions)
    gap_bytes = texture.palette_offset - chain_bytes
    storage = "linear" if texture.format_name == "VC_P8_LINEAR" else "xbox_morton_swizzled"
    return {
        "kind": record.kind,
        "system_bytes": record.word_08,
        "video_bytes": record.word_0c,
        "name_offset": texture.name_offset,
        "descriptor_offset": texture.descriptor_offset,
        "dimensions_field": texture.dimensions,
        "format_code": texture.format_code,
        "format_name": texture.format_name,
        "mip_levels": texture.mip_levels,
        "width": texture.width,
        "height": texture.height,
        "depth": texture.depth,
        "pixel_offset": texture.pixel_offset,
        "palette_offset": texture.palette_offset,
        "packed_format": f"0x{texture.packed_format:08x}",
        "packed_size": texture.packed_size,
        "descriptor_flags": f"0x{texture.descriptor_flags:08x}",
        "mip_dimensions": dimensions,
        "index_chain_bytes": chain_bytes,
        "pre_palette_gap_offset": chain_bytes,
        "pre_palette_gap_bytes": gap_bytes,
        "palette_bytes": 1024,
        "mip_storage": storage,
        "video_is_exact_index_chain_gap_palette":
            texture.pixel_offset == 0 and gap_bytes >= 0 and
            record.word_0c == texture.palette_offset + 1024,
    }


def compatible_layout(family: str, projection: dict[str, object]) -> bool:
    shared = (
        projection["kind"] == "TXTR" and
        projection["system_bytes"] == 128 and
        projection["dimensions_field"] == 2 and
        projection["depth"] == 1 and
        projection["pixel_offset"] == 0 and
        projection["palette_bytes"] == 1024 and
        projection["video_is_exact_index_chain_gap_palette"] is True
    )
    if not shared:
        return False
    if family == "nameplate_atlas":
        return (
            projection["format_name"] == "VC_P8_LINEAR" and
            projection["format_code"] == 0x7F and
            projection["width"] == 32 and projection["height"] == 1024 and
            projection["mip_levels"] == 6 and
            projection["palette_offset"] == 43712 and
            projection["pre_palette_gap_bytes"] == 32 and
            projection["packed_format"] == "0x00067f29" and
            projection["packed_size"] == 0x04000020 and
            projection["descriptor_flags"] == "0x00000400" and
            projection["mip_storage"] == "linear"
        )
    if family == "jersey_digit":
        allowed = {(64, 64, 4, 5440, "0x06640b29")}
    else:
        allowed = {
            (32, 32, 3, 1344, "0x05530b29"),
            (64, 64, 4, 5440, "0x06640b29"),
        }
    return (
        projection["format_name"] == "P8" and
        projection["format_code"] == 0x0B and
        projection["packed_size"] == 0 and
        projection["descriptor_flags"] == "0x80000000" and
        projection["pre_palette_gap_bytes"] == 0 and
        projection["mip_storage"] == "xbox_morton_swizzled" and
        (projection["width"], projection["height"], projection["mip_levels"],
         projection["palette_offset"], projection["packed_format"]) in allowed
    )


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def run(args: argparse.Namespace) -> dict[str, object]:
    index = args.index.resolve(strict=True)
    source_xiso = args.xiso.resolve(strict=True)
    inventory_path = args.inventory.resolve(strict=True)
    uniform_path = args.uniform_inventory.resolve(strict=True)
    trace_path = args.ghidra_trace.resolve(strict=True)
    pseudo_path = args.ghidra_pseudo.resolve(strict=True)
    require(index.name == "0", "canonical archive index must be named 0")
    inventory = read_json(inventory_path)
    uniforms = read_json(uniform_path)
    require(inventory.get("schema") == "nfl2k5_resource_chunk_inventory/v1",
            "chunk inventory schema mismatch")
    require(uniforms.get("schema") == "nfl2k5_uniform_inventory/v1" and
            len(uniforms.get("packages", [])) == PACKAGE_COUNT,
            "uniform inventory schema/count mismatch")
    package_by_outer = {
        int(row["outer_index"]): row for row in uniforms["packages"]
    }
    chunk_by_key = {
        (int(row["outer_index"]), int(row["chunk_index"])): row
        for row in inventory["chunks"]
        if FIRST_OUTER <= int(row["outer_index"]) <= LAST_OUTER and
        int(row["chunk_index"]) in ART_CHUNKS + (NAME_METRICS_CHUNK,)
    }
    require(len(chunk_by_key) == PACKAGE_COUNT * 32,
            "live-art and metrics chunk coverage mismatch")

    archive = parse_archive(index)
    logical_names = logical_name_candidates()
    for pack_name, expected in PACK_SHA256.items():
        pack = next(pack for pack in archive.packs if pack.name == pack_name)
        require(file_digest(pack.path) == expected,
                f"extracted pack {pack_name} SHA-256 mismatch")

    supplied = args.xiso.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "retail XISO must be a non-symlink regular file")
    descriptor = os.open(source_xiso, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        identity = xiso.fd_identity(descriptor)
        require(identity == (supplied.st_dev, supplied.st_ino) and
                xiso.path_identity(source_xiso) == identity and
                os.fstat(descriptor).st_size == xiso.EXPECTED_XISO_SIZE and
                xiso.sha256_fd(descriptor) == xiso.EXPECTED_XISO_SHA256,
                "retail XISO identity/size/hash mismatch")
        xdvdfs_entries, directory = xiso.parse_xdvdfs(
            descriptor, xiso.EXPECTED_XISO_SIZE)
        pack_extents: dict[str, dict[str, object]] = {}
        for pack_name, expected_hash in PACK_SHA256.items():
            path = f"vc_53450030/{pack_name}"
            item = xdvdfs_entries.get(path.casefold())
            require(item is not None, f"XDVDFS pack {path} is absent")
            assert item is not None
            archive_pack = next(pack for pack in archive.packs if pack.name == pack_name)
            require(item.size == archive_pack.size and
                    xiso.sha256_fd(descriptor, item.byte_offset, item.size) == expected_hash,
                    f"XDVDFS pack {path} differs from extracted input")
            pack_extents[pack_name] = {
                "path": path,
                "sector": item.sector,
                "byte_offset": item.byte_offset,
                "size": item.size,
                "sha256": expected_hash,
            }

        resources: list[dict[str, object]] = []
        name_objects: list[dict[str, object]] = []
        layout_counts: Counter[str] = Counter()
        allocation_counts: Counter[tuple[str, int, int]] = Counter()
        exact_scratch_counts: Counter[tuple[str, int]] = Counter()
        family_counts: Counter[str] = Counter()
        side_counts: Counter[str] = Counter()
        metric_body_counts: Counter[str] = Counter()
        metric_offset_patterns: Counter[tuple[int, ...]] = Counter()

        for outer_index in range(FIRST_OUTER, LAST_OUTER + 1):
            package = package_by_outer[outer_index]
            entry = archive.entries[outer_index]
            logical = logical_names.get(entry.name_id)
            require(logical is not None and logical.name == package["logical_name"],
                    f"outer {outer_index}: selector identity mismatch")
            assert logical is not None
            selector = {
                "asset_code": logical.asset_code,
                "side": logical.side_code,
                "variant": logical.variant_id,
                "logical_name": logical.name,
            }
            side_counts[logical.side_code] += 1

            metric_item = chunk_by_key[(outer_index, NAME_METRICS_CHUNK)]
            metric_record, metric_span, metric_body, metric_info = \
                read_and_validate_span(archive, metric_item)
            metric_summary, metrics = parse_name(metric_body, metric_record)
            require(metric_info is None and metric_record.kind == "NAME" and
                    metric_record.stored_size == 160 and
                    metric_record.word_08 == metric_record.word_0c ==
                    metric_record.word_10 == metric_record.word_14 == 0 and
                    HEADER.unpack_from(metric_span)[6:] == (0, 0),
                    f"outer {outer_index}: NAME metrics wrapper differs")
            metric_offsets = tuple(int(row["atlas_offset_u16"]) for row in metrics)
            metric_body_counts[str(metric_summary["body_sha256"])] += 1
            metric_offset_patterns[metric_offsets] += 1
            name_objects.append({
                "selector": selector,
                "outer_index": outer_index,
                "outer_id": f"0x{entry.name_id:08x}",
                "chunk_index": NAME_METRICS_CHUNK,
                "chunk_offset": metric_record.chunk_offset,
                "span_size": len(metric_span),
                "span_sha256": digest(metric_span),
                "body_sha256": metric_summary["body_sha256"],
                "metric_count": len(metrics),
                "metrics": metrics,
                "writer_status": (
                    "preserved_read_only; atlas_offset physical unit and index 28 "
                    "mapping remain PORTME"
                ),
            })

            for chunk_index in ART_CHUNKS:
                item = chunk_by_key[(outer_index, chunk_index)]
                record, span, decoded, info = read_and_validate_span(archive, item)
                require(info is not None and record.kind == "TXTR" and
                        record.word_10 == COMPRESSED_SENTINEL and
                        HEADER.unpack_from(span)[6:] == (0, 0),
                        f"outer {outer_index} chunk {chunk_index}: not proved compressed TXTR")
                texture = parse_texture(decoded, record.as_chunk())
                family, digit = family_for_name(texture.name)
                require(expected_chunk(family, digit) == chunk_index,
                        f"outer {outer_index}: name/chunk mapping differs")
                projection = layout_projection(record, texture)
                video = decoded[record.word_08:]
                gap_first = int(projection["pre_palette_gap_offset"])
                gap_after = gap_first + int(projection["pre_palette_gap_bytes"])
                gap = video[gap_first:gap_after]
                signature = canonical_digest(projection)
                layout_counts[signature] += 1
                family_counts[family] += 1
                allocation_counts[(family, record.stored_size, record.word_14)] += 1
                stream = span[HEADER.size:HEADER.size + info.consumed_bytes]
                exact_scratch = minimum_vc_lz_overlap_scratch(
                    stream, record.stored_size, len(decoded))
                exact_scratch_counts[(family, exact_scratch)] += 1
                pieces = locate_range(entry, record.chunk_offset, len(span))
                reasons: list[str] = []
                if not compatible_layout(family, projection):
                    reasons.append("descriptor_or_mip_layout_differs")
                if len(pieces) != 1:
                    reasons.append("resource_crosses_pack_boundary")
                absolute: int | None = None
                source_match = False
                pack_name = "+".join(str(piece["pack_name"]) for piece in pieces)
                if len(pieces) == 1:
                    pack_name = str(pieces[0]["pack_name"])
                    extent = pack_extents[pack_name]
                    absolute = int(extent["byte_offset"]) + int(pieces[0]["pack_offset"])
                    source_match = xiso.read_exact(descriptor, absolute, len(span)) == span
                    if not source_match:
                        reasons.append("source_xiso_span_differs")
                if record.word_14 < exact_scratch:
                    reasons.append("retail_wrapper_understates_alias_scratch")
                resources.append({
                    "selector": selector,
                    "resource_selector": (
                        f"{logical.asset_code}{logical.side_code}{logical.variant_id}:"
                        f"{family}" + ("" if digit is None else f":{digit}")
                    ),
                    "family": family,
                    "digit": digit,
                    "resource_name": texture.name,
                    "outer_index": outer_index,
                    "outer_id": f"0x{entry.name_id:08x}",
                    "outer_size": entry.size,
                    "chunk_index": chunk_index,
                    "chunk_offset": record.chunk_offset,
                    "stored_size": record.stored_size,
                    "span_size": len(span),
                    "system_bytes": record.word_08,
                    "video_bytes": record.word_0c,
                    "decoded_size": len(decoded),
                    "compression_magic": f"0x{record.word_10:08x}",
                    "overlap_scratch_bytes": record.word_14,
                    "retail_exact_minimum_overlap_scratch_bytes": exact_scratch,
                    "retail_wrapper_covers_exact_alias_requirement":
                        record.word_14 >= exact_scratch,
                    "stream_tag": int.from_bytes(span[HEADER.size + 4:HEADER.size + 8], "little"),
                    "offset_bits": span[HEADER.size + 8],
                    "lz_consumed_bytes": info.consumed_bytes,
                    "lz_unused_bytes": record.stored_size - info.consumed_bytes,
                    "span_sha256": digest(span),
                    "decoded_sha256": digest(decoded),
                    "system_sha256": digest(decoded[:record.word_08]),
                    "video_sha256": digest(decoded[record.word_08:]),
                    "pre_palette_gap_sha256": digest(gap),
                    "pre_palette_gap_nonzero_bytes": sum(value != 0 for value in gap),
                    "layout": projection,
                    "layout_signature_sha256": signature,
                    "span_segments": pieces,
                    "xiso_pack": pack_name,
                    "xiso_absolute_span_offset": absolute,
                    "source_xiso_span_matches": source_match,
                    "compatible_with_fail_closed_png_importer": not reasons,
                    "incompatibility_reasons": reasons,
                    "fixed_allocation_policy": (
                        "replacement VC-LZ stream must fit this stored_size; complete "
                        "span/descriptor stay fixed and +0x14 scratch may only be raised"
                    ),
                })

        require(len(resources) == PACKAGE_COUNT * 31 and
                len(name_objects) == PACKAGE_COUNT,
                "resource/name-object count mismatch")
        require(len({row["resource_selector"] for row in resources}) == len(resources),
                "resource selectors are not unique")
        compatible = [row for row in resources
                      if row["compatible_with_fail_closed_png_importer"]]
        layout_classes = []
        for signature, count in sorted(layout_counts.items()):
            example = next(row for row in resources
                           if row["layout_signature_sha256"] == signature)
            layout_classes.append({
                "layout_signature_sha256": signature,
                "resource_count": count,
                "family": example["family"],
                "layout": example["layout"],
                "compatible": example["compatible_with_fail_closed_png_importer"],
            })

        family_summary: dict[str, dict[str, object]] = {}
        for family in ("jersey_digit", "helmet_digit", "arm_digit", "nameplate_atlas"):
            rows = [row for row in resources if row["family"] == family]
            family_summary[family] = {
                "resource_count": len(rows),
                "package_count": len({row["outer_index"] for row in rows}),
                "resources_per_package": len(rows) // PACKAGE_COUNT,
                "layout_class_count": len({row["layout_signature_sha256"] for row in rows}),
                "allocation_class_count": len({
                    (row["stored_size"], row["overlap_scratch_bytes"]) for row in rows
                }),
                "stored_size_minimum": min(int(row["stored_size"]) for row in rows),
                "stored_size_maximum": max(int(row["stored_size"]) for row in rows),
                "retail_overlap_scratch_minimum": min(
                    int(row["overlap_scratch_bytes"]) for row in rows),
                "retail_overlap_scratch_maximum": max(
                    int(row["overlap_scratch_bytes"]) for row in rows),
                "exact_alias_scratch_minimum": min(
                    int(row["retail_exact_minimum_overlap_scratch_bytes"]) for row in rows),
                "exact_alias_scratch_maximum": max(
                    int(row["retail_exact_minimum_overlap_scratch_bytes"]) for row in rows),
                "all_retail_wrappers_cover_alias_scratch": all(
                    row["retail_wrapper_covers_exact_alias_requirement"] for row in rows),
                "all_source_xiso_spans_match": all(
                    row["source_xiso_span_matches"] for row in rows),
                "compatible_resource_count": sum(
                    row["compatible_with_fail_closed_png_importer"] for row in rows),
            }

        return {
            "schema": SCHEMA,
            "sources": {
                "index": {"path": str(index), "size": index.stat().st_size,
                          "sha256": file_digest(index)},
                "chunk_inventory": {"path": str(inventory_path),
                                    "sha256": file_digest(inventory_path)},
                "uniform_inventory": {"path": str(uniform_path),
                                      "sha256": file_digest(uniform_path)},
                "retail_xiso": {"path": str(source_xiso),
                                "size": xiso.EXPECTED_XISO_SIZE,
                                "sha256": xiso.EXPECTED_XISO_SHA256,
                                "opened_read_only": True},
                "ghidra_trace": {"path": str(trace_path),
                                 "sha256": file_digest(trace_path)},
                "ghidra_pseudo_c": {"path": str(pseudo_path),
                                    "sha256": file_digest(pseudo_path)},
                "packs": pack_extents,
                "xdvdfs": {**directory, "file_count": len([
                    item for item in xdvdfs_entries.values()
                    if not (item.attributes & 0x10)
                ])},
            },
            "summary": {
                "package_count": PACKAGE_COUNT,
                "home_count": side_counts["H"],
                "away_count": side_counts["A"],
                "pair_count": PACKAGE_COUNT // 2,
                "digit_texture_count": family_counts["jersey_digit"] +
                    family_counts["helmet_digit"] + family_counts["arm_digit"],
                "nameplate_atlas_count": family_counts["nameplate_atlas"],
                "name_metrics_object_count": len(name_objects),
                "name_metric_record_count": sum(
                    int(row["metric_count"]) for row in name_objects),
                "art_resource_count": len(resources),
                "compatible_art_resource_count": len(compatible),
                "incompatible_art_resource_count": len(resources) - len(compatible),
                "layout_class_count": len(layout_classes),
                "all_spans_single_pack_segment": all(
                    len(row["span_segments"]) == 1 for row in resources),
                "all_source_xiso_spans_match": all(
                    row["source_xiso_span_matches"] for row in resources),
                "all_retail_wrappers_cover_alias_scratch": all(
                    row["retail_wrapper_covers_exact_alias_requirement"]
                    for row in resources),
                "unique_name_metrics_bodies": len(metric_body_counts),
                "name_metric_offset_pattern_count": len(metric_offset_patterns),
            },
            "family_summary": family_summary,
            "layout_classes": layout_classes,
            "allocation_classes": [
                {"family": family, "stored_size": stored,
                 "overlap_scratch_bytes": scratch, "resource_count": count}
                for (family, stored, scratch), count in sorted(allocation_counts.items())
            ],
            "retail_exact_alias_scratch_classes": [
                {"family": family,
                 "exact_minimum_overlap_scratch_bytes": scratch,
                 "resource_count": count}
                for (family, scratch), count in sorted(exact_scratch_counts.items())
            ],
            "composition": {
                "cache_initializer": "0x0008E620",
                "digit_binder": "0x0008E910",
                "digit_material_writer": "0x0008E8D0",
                "jersey_digit_family_id": "0x0C",
                "helmet_digit_family_id": "0x0D",
                "arm_digit_family_id": "0x0E",
                "digit_rule": (
                    "0..9 binds one glyph; 10..99 binds tens and ones; values over "
                    "99 clamp to 0"
                ),
                "digit_material_effect": (
                    "writes TXTR pointer at material +0x30, clears flag bit 0, and "
                    "sets scale words to 4.0 and 2.0"
                ),
                "name_resource_lookup": (
                    "0x00090570 resolves TXTR/names and NAME/names independently in "
                    "HOME and AWAY contexts"
                ),
                "name_character_mapper": "0x001C20B0",
                "name_width_accumulator": "0x001C20F0",
                "name_atlas_compositor": "0x001C2140",
                "player_name_owner": (
                    "0x0008F800 passes the selected name string, names TXTR, names "
                    "NAME metrics, and generated target to 0x001C2140"
                ),
                "name_material_binding": (
                    "0x0008F800 -> 0x0008EFA0 -> 0x0008EBB0; route table "
                    "0x004EF3E0/0x004EF3E4 selects PLAYERNAME/PLAYERNAME_long and "
                    "0x0008EC74 writes the generated name texture"
                ),
                "mapped_name_characters": "apostrophe, hyphen, A-Z, a-z",
                "space_rule": "uses NAME metric index 1 advance without drawing a glyph",
                "unmapped_metric_index": 28,
            },
            "name_metric_patterns": [
                {"atlas_offsets_u16": list(pattern), "package_count": count}
                for pattern, count in sorted(metric_offset_patterns.items())
            ],
            "name_metric_body_classes": [
                {"body_sha256": body_hash, "package_count": count}
                for body_hash, count in sorted(metric_body_counts.items())
            ],
            "resources": resources,
            "name_objects": name_objects,
            "claims": {
                "all_634_selectors_audited": True,
                "all_19020_digit_textures_audited": True,
                "all_634_nameplate_atlases_audited": True,
                "all_634_name_metrics_objects_audited": True,
                "compatible_means_static_fixed_span_layout_only": True,
                "per_import_vc_lz_fit_still_required": True,
                "name_metrics_writer_enabled": False,
                "retail_files_modified": False,
                "xemu_started": False,
                "title_executed": False,
                "runtime_visibility_proved_for_new_replacements": False,
                "portme": [
                    "PORTME(0x001C2140): prove the physical unit of NAME metric word 0.",
                    "PORTME(0x001C20B0): identify metric index 28 before exposing a metrics writer.",
                    "PORTME(runtime): capture representative jersey, helmet, arm, and nameplate edits before claiming visibility.",
                ],
            },
        }
    finally:
        os.close(descriptor)


def tsv_payload(report: dict[str, object]) -> bytes:
    fields = [
        "asset_code", "side", "variant", "logical_name", "family", "digit",
        "resource_name", "outer_index", "outer_id", "chunk_index", "chunk_offset",
        "stored_size", "span_size", "system_bytes", "video_bytes", "width",
        "height", "mip_levels", "format_name", "mip_storage", "palette_offset",
        "overlap_scratch_bytes", "retail_exact_minimum_overlap_scratch_bytes",
        "lz_consumed_bytes", "lz_unused_bytes", "xiso_pack",
        "xiso_absolute_span_offset", "span_sha256", "decoded_sha256",
        "layout_signature_sha256", "compatible", "incompatibility_reasons",
    ]
    from io import StringIO
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                            lineterminator="\n")
    writer.writeheader()
    for row in report["resources"]:
        selector = row["selector"]
        layout = row["layout"]
        writer.writerow({
            "asset_code": selector["asset_code"], "side": selector["side"],
            "variant": selector["variant"], "logical_name": selector["logical_name"],
            "family": row["family"], "digit": "" if row["digit"] is None else row["digit"],
            "resource_name": row["resource_name"], "outer_index": row["outer_index"],
            "outer_id": row["outer_id"], "chunk_index": row["chunk_index"],
            "chunk_offset": row["chunk_offset"], "stored_size": row["stored_size"],
            "span_size": row["span_size"], "system_bytes": row["system_bytes"],
            "video_bytes": row["video_bytes"], "width": layout["width"],
            "height": layout["height"], "mip_levels": layout["mip_levels"],
            "format_name": layout["format_name"], "mip_storage": layout["mip_storage"],
            "palette_offset": layout["palette_offset"],
            "overlap_scratch_bytes": row["overlap_scratch_bytes"],
            "retail_exact_minimum_overlap_scratch_bytes":
                row["retail_exact_minimum_overlap_scratch_bytes"],
            "lz_consumed_bytes": row["lz_consumed_bytes"],
            "lz_unused_bytes": row["lz_unused_bytes"], "xiso_pack": row["xiso_pack"],
            "xiso_absolute_span_offset": row["xiso_absolute_span_offset"],
            "span_sha256": row["span_sha256"], "decoded_sha256": row["decoded_sha256"],
            "layout_signature_sha256": row["layout_signature_sha256"],
            "compatible": str(row["compatible_with_fail_closed_png_importer"]).lower(),
            "incompatibility_reasons": ";".join(row["incompatibility_reasons"]),
        })
    return stream.getvalue().encode("utf-8")


def write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o644)
    try:
        offset = 0
        while offset < len(payload):
            amount = os.write(descriptor, payload[offset:])
            require(amount > 0, "short report write")
            offset += amount
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    parser.add_argument("--inventory", type=Path, default=root / "reports/assets/nfl2k5_resource_chunks_v2.json")
    parser.add_argument("--uniform-inventory", type=Path, default=root / "reports/assets/nfl2k5_uniform_inventory.json")
    parser.add_argument("--xiso", type=Path, default=root / "ESPN NFL 2K5 (USA).xiso.iso")
    parser.add_argument("--ghidra-trace", type=Path, default=root / "reports/assets/nfl2k5_live_numbers_nameplate_ghidra/nfl_live_numbers_nameplate_trace.txt")
    parser.add_argument("--ghidra-pseudo", type=Path, default=root / "reports/assets/nfl2k5_live_numbers_nameplate_ghidra/nfl_live_numbers_nameplate_pseudo_c.c")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args)
        write_exclusive(args.output, canonical_json(report))
        write_exclusive(args.tsv, tsv_payload(report))
        print("NFL_LIVE_NUMBERS_NAMEPLATE_COMPATIBILITY_COMPLETE "
              f"resources={report['summary']['art_resource_count']} "
              f"compatible={report['summary']['compatible_art_resource_count']} "
              f"layouts={report['summary']['layout_class_count']} runtime=false")
        return 0
    except (CompatibilityError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
