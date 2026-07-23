#!/usr/bin/env python3
"""Enumerate every standalone NFL 2K5 Team Select uniform/helmet card."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import struct
from typing import Any

from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import HEADER, decode_chunk, parse_chunks, parse_texture, unswizzle_2d
import nfl_uniform_color_xiso_direct_patch as xiso


SCHEMA = "nfl2k5_team_select_card_inventory/v1"
NAME = re.compile(r"^(unif|helm)_([ha])([0-9]{2})_([0-9]+)$")
OUTER_CLASSES = {
    3102: {
        "outer_id": 0x823E3053,
        "outer_size": 105_903_360,
        "slot_count": 1_585,
        "slot_size": 66_816,
        "span_size": 66_720,
        "stored_size": 66_688,
        "system_bytes": 128,
        "video_bytes": 66_560,
        "width": 256,
        "height": 256,
        "palette_offset": 65_536,
        "packed_format": 0x08810B29,
    },
    3105: {
        "outer_id": 0x35CB8D72,
        "outer_size": 87_207_168,
        "slot_count": 4_937,
        "slot_size": 17_664,
        "span_size": 17_568,
        "stored_size": 17_536,
        "system_bytes": 128,
        "video_bytes": 17_408,
        "width": 128,
        "height": 128,
        "palette_offset": 16_384,
        "packed_format": 0x07710B29,
    },
}


class InventoryError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "size": path.stat().st_size,
            "sha256": file_digest(path)}


def tsv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def segment_for(entry: object, relative: int, size: int) -> tuple[str, int]:
    cursor = 0
    for segment in entry.segments:
        after = cursor + segment.size
        if cursor <= relative and relative + size <= after:
            return segment.pack_name, segment.pack_offset + relative - cursor
        cursor = after
    raise InventoryError(
        f"outer {entry.table_index} range 0x{relative:x}+0x{size:x} crosses pack segments")


def build(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_path = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
    texture_path = root / "reports/assets/nfl2k5_all_txtr_inventory_v2.tsv"
    packages_path = root / "reports/assets/nfl2k5_uniform_packages.tsv"
    owner_path = root / "reports/assets/nfl2k5_team_select_preview_owner.json"
    source_xiso = root / "ESPN NFL 2K5 (USA).xiso.iso"

    with texture_path.open(newline="", encoding="utf-8") as stream:
        textures = [item for item in csv.DictReader(stream, delimiter="\t")
                    if NAME.fullmatch(item["name"])]
    require(len(textures) == 1_902, "Team Select card count changed")
    require(Counter(int(item["outer_index"]) for item in textures) ==
            Counter({3102: 1_268, 3105: 634}), "card outer distribution changed")

    packages = tsv_rows(packages_path)
    require(len(packages) == 634, "uniform package selector count changed")
    package_by_key = {
        (row["asset_code"], row["side_code"], int(row["variant_id"])): row
        for row in packages
    }
    require(len(package_by_key) == 634, "uniform package selectors are ambiguous")

    archive = parse_archive(index_path)
    for outer_index, profile in OUTER_CLASSES.items():
        entry = archive.entries[outer_index]
        require(entry.name_id == profile["outer_id"] and
                entry.size == profile["outer_size"] and
                entry.size == profile["slot_count"] * profile["slot_size"],
                f"outer {outer_index} identity/fixed-slot geometry changed")

    source_fd = os.open(source_xiso, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        source_info = os.fstat(source_fd)
        require(source_info.st_size == xiso.EXPECTED_XISO_SIZE,
                "retail XISO size changed")
        xdvdfs, directory = xiso.parse_xdvdfs(source_fd, source_info.st_size)
        pack_records: dict[str, dict[str, Any]] = {}
        for pack_name in ("3", "4"):
            path = f"vc_53450030/{pack_name}"
            item = xdvdfs.get(path.casefold())
            require(item is not None, f"XISO lacks {path}")
            assert item is not None
            extracted = index_path.parent / pack_name
            require(item.size == extracted.stat().st_size,
                    f"XISO/extracted pack {pack_name} size mismatch")
            extracted_sha = file_digest(extracted)
            xiso_sha = xiso.sha256_fd(source_fd, item.byte_offset, item.size)
            require(xiso_sha == extracted_sha, f"XISO/extracted pack {pack_name} differs")
            pack_records[pack_name] = {
                "path": path, "sector": item.sector,
                "byte_offset": item.byte_offset, "size": item.size,
                "sha256": xiso_sha,
            }

        name_counts = Counter(item["name"] for item in textures)
        rgba_counts = Counter(item["rgba_sha256"] for item in textures)
        targets: list[dict[str, Any]] = []
        selector_keys: Counter[tuple[str, str, int]] = Counter()
        pack_target_counts: Counter[str] = Counter()
        class_counts: Counter[str] = Counter()

        active_outer = -1
        data = b""
        for item in sorted(textures, key=lambda value: (
                int(value["outer_index"]), value["name"], int(value["width"]))):
            match = NAME.fullmatch(item["name"])
            assert match is not None
            family, context, asset_code, style_text = match.groups()
            style = int(style_text)
            side_code = context.upper()
            package = package_by_key.get((asset_code, side_code, style))
            require(package is not None,
                    f"{item['name']} has no exact uniform selector mapping")
            selector_keys[(asset_code, side_code, style)] += 1

            outer_index = int(item["outer_index"])
            profile = OUTER_CLASSES[outer_index]
            if outer_index != active_outer:
                data = read_entry_bytes(
                    archive, archive.entries[outer_index],
                    archive.entries[outer_index].size)
                active_outer = outer_index
            chunk_index = int(item["chunk_index"])
            chunk_offset = int(item["chunk_offset"])
            require(chunk_offset == chunk_index * profile["slot_size"],
                    f"{item['name']} fixed-slot offset changed")
            span = data[chunk_offset:chunk_offset + profile["span_size"]]
            padding = data[
                chunk_offset + profile["span_size"]:
                chunk_offset + profile["slot_size"]
            ]
            require(len(span) == profile["span_size"] and padding == bytes(96),
                    f"{item['name']} span/padding changed")
            chunks = parse_chunks(span)
            require(len(chunks) == 1, f"{item['name']} isolated span is not one chunk")
            chunk = chunks[0]
            decoded, decode_info = decode_chunk(span, chunk)
            texture = parse_texture(decoded, chunk)
            require(decode_info is None and not chunk.compressed and
                    chunk.kind == "TXTR" and chunk.stored_size == profile["stored_size"] and
                    chunk.system_bytes == profile["system_bytes"] and
                    chunk.video_bytes == profile["video_bytes"] and
                    chunk.compression_magic == 0 and
                    chunk.overlap_scratch_bytes == 0 and
                    chunk.reserved0 == 0 and chunk.reserved1 == 0 and
                    chunk.stored_size == chunk.system_bytes + chunk.video_bytes,
                    f"{item['name']} raw wrapper changed")
            require(texture.name == item["name"] and texture.name_offset == 32 and
                    texture.descriptor_offset == 56 and texture.pixel_offset == 0 and
                    texture.palette_offset == profile["palette_offset"] and
                    texture.packed_format == profile["packed_format"] and
                    texture.packed_size == 0 and
                    texture.descriptor_flags == 0x80000000 and
                    texture.format_name == "P8" and texture.format_code == 0x0B and
                    texture.dimensions == 2 and texture.mip_levels == 1 and
                    texture.width == profile["width"] and
                    texture.height == profile["height"] and texture.depth == 1,
                    f"{item['name']} TXTR descriptor changed")
            require(digest(decoded) == item["decoded_sha256"],
                    f"{item['name']} decoded hash differs from canonical inventory")
            video = decoded[chunk.system_bytes:]
            pixel_count = texture.width * texture.height
            swizzled = video[:pixel_count]
            palette = video[texture.palette_offset:texture.palette_offset + 1024]
            require(len(video) == pixel_count + 1024 and len(palette) == 1024,
                    f"{item['name']} video allocation changed")
            linear = unswizzle_2d(swizzled, texture.width, texture.height, 1)
            used = sorted(set(linear))
            used_alpha = [palette[index * 4 + 3] for index in used]

            pack_name, pack_offset = segment_for(
                archive.entries[outer_index], chunk_offset, profile["span_size"])
            pack = pack_records[pack_name]
            xiso_absolute = pack["byte_offset"] + pack_offset
            require(os.pread(source_fd, len(span), xiso_absolute) == span,
                    f"{item['name']} extracted/XISO target span mismatch")
            pack_target_counts[pack_name] += 1

            layout_class = (
                "raw_p8_256x256_base1" if texture.width == 256
                else "raw_p8_128x128_base1"
            )
            class_counts[layout_class] += 1
            target = {
                "selector": f"{family}:{asset_code}:{'home' if context == 'h' else 'away'}:{style}:{texture.width}",
                "family": family,
                "name": item["name"],
                "asset_code": asset_code,
                "side_code": side_code,
                "side_context": "HOME" if context == "h" else "AWAY",
                "style": style,
                "uniform_package": package["logical_name"],
                "team_names": package["roster_current_names"],
                "team_abbreviations": package["roster_current_abbreviations"],
                "historic_abbreviations": package["roster_historic_abbreviations"],
                "style_display": package["style_display"],
                "layout_class": layout_class,
                "outer_index": outer_index,
                "outer_id": item["outer_id"],
                "outer_size": archive.entries[outer_index].size,
                "chunk_index": chunk_index,
                "chunk_offset": chunk_offset,
                "slot_size": profile["slot_size"],
                "span_size": profile["span_size"],
                "post_span_padding_bytes": 96,
                "post_span_padding_all_zero": True,
                "stored_size": chunk.stored_size,
                "system_bytes": chunk.system_bytes,
                "video_bytes": chunk.video_bytes,
                "compression_magic": "0x00000000",
                "compressed": False,
                "vc_lz_stream_tag": None,
                "overlap_scratch_bytes": 0,
                "vc_lz_alias_constraint": "not_applicable_raw_resource",
                "descriptor_offset": texture.descriptor_offset,
                "pixel_offset": texture.pixel_offset,
                "palette_offset": texture.palette_offset,
                "packed_format": f"0x{texture.packed_format:08x}",
                "packed_size": f"0x{texture.packed_size:08x}",
                "descriptor_flags": f"0x{texture.descriptor_flags:08x}",
                "format_name": texture.format_name,
                "mip_levels": texture.mip_levels,
                "width": texture.width,
                "height": texture.height,
                "depth": texture.depth,
                "palette_entries": 256,
                "used_palette_indices": len(used),
                "minimum_used_alpha": min(used_alpha),
                "maximum_used_alpha": max(used_alpha),
                "system_sha256": digest(decoded[:chunk.system_bytes]),
                "swizzled_indices_sha256": digest(swizzled),
                "linear_indices_sha256": digest(linear),
                "palette_bgra_sha256": digest(palette),
                "decoded_sha256": item["decoded_sha256"],
                "rgba_sha256": item["rgba_sha256"],
                "span_sha256": digest(span),
                "retail_png_path": item["png_path"],
                "same_name_resource_count": name_counts[item["name"]],
                "same_rgba_resource_count": rgba_counts[item["rgba_sha256"]],
                "pack_path": pack["path"],
                "pack_sector": pack["sector"],
                "pack_size": pack["size"],
                "pack_sha256": pack["sha256"],
                "span_pack_offset": pack_offset,
                "xiso_absolute_span_offset": xiso_absolute,
            }
            targets.append(target)

        targets.sort(key=lambda value: (
            value["name"], value["width"], value["outer_index"]))

        require(len(targets) == 1_902 and len(selector_keys) == 634 and
                set(selector_keys.values()) == {3},
                "selector key must map to unif256/helm256/helm128 exactly")
        require(pack_target_counts == Counter({"3": 1_787, "4": 115}),
                "card pack distribution changed")
        require(class_counts == Counter({
            "raw_p8_256x256_base1": 1_268,
            "raw_p8_128x128_base1": 634,
        }), "layout class counts changed")

        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        require(owner["conclusion"]["selected_detroit_uniform_card"] == "unif_a09_0" and
                owner["conclusion"]["selected_detroit_helmet_card"] == "helm_a09_0" and
                owner["conclusion"]["selected_card_outer_index"] == 3102,
                "Team Select owner proof changed")
        selected = [item for item in targets if item["selector"] in {
            "unif:09:away:0:256", "helm:09:away:0:256"
        }]
        require(len(selected) == 2, "Detroit proof targets missing")

        duplicate_names = Counter(name_counts.values())
        duplicate_rgba = Counter(rgba_counts.values())
        report: dict[str, Any] = {
            "schema": SCHEMA,
            "inputs": {
                "canonical_index": pin(index_path),
                "canonical_txtr_inventory": pin(texture_path),
                "uniform_selector_inventory": pin(packages_path),
                "team_select_owner_proof": pin(owner_path),
                "retail_xiso": {
                    "path": str(source_xiso.resolve()),
                    "size": source_info.st_size,
                    "expected_sha256": xiso.EXPECTED_XISO_SHA256,
                    "opened_read_only": True,
                },
            },
            "summary": {
                "selector_key_count": 634,
                "concrete_resource_count": 1_902,
                "unif_256_count": 634,
                "helm_256_count": 634,
                "helm_128_count": 634,
                "name_multiplicity_counts": {
                    str(key): value for key, value in sorted(duplicate_names.items())
                },
                "unique_rgba_count": len(rgba_counts),
                "rgba_multiplicity_counts": {
                    str(key): value for key, value in sorted(duplicate_rgba.items())
                },
                "layout_class_counts": dict(sorted(class_counts.items())),
                "target_pack_counts": dict(sorted(pack_target_counts.items())),
            },
            "formatter_contract": {
                "uniform": "unif_%s%s_%1d",
                "helmet": "helm_%s%s_%1d",
                "argument_0": "h or a side context",
                "argument_1": "team record +0x10c two-digit asset code",
                "argument_2": "selected style index",
                "same_style_argument_for_both_families": True,
                "state_slots": {
                    "side_0_team": "0x00AE2B34", "side_0_style": "0x00AE2B3C",
                    "side_1_team": "0x00AE2B38", "side_1_style": "0x00AE2B40",
                },
            },
            "layout_classes": {
                "raw_p8_256x256_base1": {
                    **OUTER_CLASSES[3102],
                    "family_support": ["unif", "helm"],
                    "format": "P8", "mip_levels": 1,
                    "palette_entries": 256, "post_span_padding_bytes": 96,
                    "compression_magic": "0x00000000",
                    "vc_lz": "not_applicable_raw_resource",
                },
                "raw_p8_128x128_base1": {
                    **OUTER_CLASSES[3105],
                    "family_support": ["helm"],
                    "format": "P8", "mip_levels": 1,
                    "palette_entries": 256, "post_span_padding_bytes": 96,
                    "compression_magic": "0x00000000",
                    "vc_lz": "not_applicable_raw_resource",
                },
            },
            "xiso_packs": pack_records,
            "selected_proof_targets": selected,
            "claims": {
                "all_concrete_formatter_resources_enumerated": True,
                "all_target_spans_equal_extracted_and_xiso_bytes": True,
                "all_wrappers_raw_uncompressed": True,
                "all_target_post_span_padding_zero": True,
                "vc_lz_tags_scratch_alias_constraints_not_applicable": True,
                "retail_assets_exported_by_this_report": False,
                "runtime_visibility_proved_by_this_report": False,
            },
            "portmes": [
                "PORTME(runtime): a card import or XISO patch does not prove menu visibility; capture remains separate.",
                "PORTME(lookup): the owner proof still requires a live hook to distinguish global versus LOGOS lookup context and duplicate double_team_select SCNE returns.",
            ],
            "targets": targets,
            "xdvdfs": {**directory, "card_pack_count": 2},
        }
        return report, targets
    finally:
        os.close(source_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--tsv", required=True, type=Path)
    args = parser.parse_args()
    report, targets = build(args.root.resolve())
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_bytes(json.dumps(report, indent=2, sort_keys=True).encode() + b"\n")
    fields = list(targets[0])
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", extrasaction="raise")
        writer.writeheader()
        writer.writerows(targets)
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
