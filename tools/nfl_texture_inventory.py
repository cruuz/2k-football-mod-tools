#!/usr/bin/env python3
"""Inventory and validate NFL 2K5 Xbox TXTR chunks directly from pack files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from nfl_outer import FormatError, parse_archive, read_entry_bytes
from nfl_txtr import (
    TxtrError,
    decode_chunk,
    parse_chunks,
    parse_texture,
    safe_texture_name,
    texture_to_rgba,
    write_png,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to vc_53450030/0")
    parser.add_argument("--json", type=Path, required=True, help="output manifest")
    parser.add_argument("--tsv", type=Path, help="optional flat texture table")
    parser.add_argument(
        "--png-dir",
        type=Path,
        help="write supported textures as stable, collision-free PNG paths",
    )
    parser.add_argument("--max-entry-mib", type=int, default=128)
    parser.add_argument(
        "--validate-conversion",
        action="store_true",
        help="unswizzle every currently supported texture and hash its RGBA pixels",
    )
    return parser.parse_args()


def conversion_blocker(texture: object) -> str | None:
    if texture.dimensions != 2 or texture.depth != 1:
        return f"dimensions={texture.dimensions}, depth={texture.depth}"
    if texture.format_code not in (0x02, 0x06, 0x0B, 0x0C, 0x7F):
        return f"Xbox format {texture.format_name}"
    return None


def main() -> int:
    args = parse_args()
    if args.max_entry_mib <= 0:
        raise SystemExit("--max-entry-mib must be positive")
    max_entry_size = args.max_entry_mib * 1024 * 1024
    archive = parse_archive(args.index)
    candidates = [entry for entry in archive.entries if entry.head_ascii == "TXTR"]

    textures: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    resource_chunk_count = 0
    for candidate_number, entry in enumerate(candidates, 1):
        if candidate_number == 1 or candidate_number % 100 == 0:
            print(
                f"scanning TXTR-headed entry {candidate_number}/{len(candidates)} "
                f"(outer index {entry.table_index})",
                file=sys.stderr,
            )
        try:
            data = read_entry_bytes(archive, entry, max_entry_size)
            chunks = parse_chunks(data, allow_trailing=True)
            resource_chunk_count += len(chunks)
            parsed_end = chunks[-1].end_offset
            if parsed_end != len(data):
                errors.append(
                    {
                        "outer_index": entry.table_index,
                        "outer_id": f"0x{entry.name_id:08x}",
                        "chunk_index": None,
                        "chunk_offset": parsed_end,
                        "trailing_bytes": len(data) - parsed_end,
                        "error": (
                            f"PORTME: 0x{len(data) - parsed_end:x} non-resource trailing "
                            f"bytes begin at 0x{parsed_end:x}; texture prefix remains usable"
                        ),
                    }
                )
        except (FormatError, OSError, TxtrError) as exc:
            errors.append(
                {
                    "outer_index": entry.table_index,
                    "outer_id": f"0x{entry.name_id:08x}",
                    "chunk_index": None,
                    "error": f"PORTME: {exc}",
                }
            )
            continue

        for chunk in chunks:
            if chunk.kind != "TXTR":
                continue
            try:
                output, decode = decode_chunk(data, chunk)
                texture = parse_texture(output, chunk)
                blocker = conversion_blocker(texture)
                record: dict[str, object] = {
                    "outer_index": entry.table_index,
                    "outer_id": f"0x{entry.name_id:08x}",
                    "outer_size": entry.size,
                    "chunk_index": chunk.index,
                    "chunk_offset": chunk.offset,
                    "stored_size": chunk.stored_size,
                    "system_bytes": chunk.system_bytes,
                    "video_bytes": chunk.video_bytes,
                    "name": texture.name,
                    "descriptor_offset": texture.descriptor_offset,
                    "pixel_offset": texture.pixel_offset,
                    "palette_offset": texture.palette_offset,
                    "packed_format": f"0x{texture.packed_format:08x}",
                    "packed_size": f"0x{texture.packed_size:08x}",
                    "format_code": f"0x{texture.format_code:02x}",
                    "format_name": texture.format_name,
                    "dimensions": texture.dimensions,
                    "mip_levels": texture.mip_levels,
                    "width": texture.width,
                    "height": texture.height,
                    "depth": texture.depth,
                    "decoded_sha256": hashlib.sha256(output).hexdigest(),
                    "conversion_status": "supported" if blocker is None else f"PORTME: {blocker}",
                }
                if decode is not None:
                    record["lz_offset_bits"] = decode.offset_bits
                    record["lz_length_bits"] = decode.length_bits
                    record["lz_consumed_bytes"] = decode.consumed_bytes
                    record["lz_unused_bytes"] = chunk.stored_size - decode.consumed_bytes
                rgba = None
                if (args.validate_conversion or args.png_dir is not None) and blocker is None:
                    rgba = texture_to_rgba(output, chunk, texture)
                if args.validate_conversion and rgba is not None:
                    record["rgba_sha256"] = hashlib.sha256(rgba).hexdigest()
                if args.png_dir is not None and rgba is not None:
                    entry_dir = (
                        args.png_dir
                        / f"outer_{entry.table_index:04d}_{entry.name_id:08x}"
                    )
                    filename = (
                        f"{chunk.index:04d}_"
                        f"{safe_texture_name(texture.name, 'unnamed')}.png"
                    )
                    target = entry_dir / filename
                    write_png(target, texture.width, texture.height, rgba)
                    record["png_path"] = str(target)
                textures.append(record)
            except (OSError, TxtrError) as exc:
                errors.append(
                    {
                        "outer_index": entry.table_index,
                        "outer_id": f"0x{entry.name_id:08x}",
                        "chunk_index": chunk.index,
                        "chunk_offset": chunk.offset,
                        "error": f"PORTME: {exc}",
                    }
                )

    format_counts = Counter(str(texture["format_name"]) for texture in textures)
    dimension_counts = Counter(
        f"{texture['width']}x{texture['height']}x{texture['depth']}"
        for texture in textures
    )
    supported = sum(texture["conversion_status"] == "supported" for texture in textures)
    result = {
        "schema": "nfl2k5_txtr_inventory/v1",
        "source_index": str(args.index),
        "selection": {
            "outer_head": "TXTR",
            "max_entry_size": max_entry_size,
            "validate_conversion": args.validate_conversion,
            "png_dir": str(args.png_dir) if args.png_dir is not None else None,
        },
        "summary": {
            "outer_entry_count": len(archive.entries),
            "candidate_entry_count": len(candidates),
            "resource_chunk_count": resource_chunk_count,
            "texture_count": len(textures),
            "supported_conversion_count": supported,
            "portme_texture_count": len(textures) - supported,
            "parse_error_count": len(errors),
            "format_counts": dict(sorted(format_counts.items())),
            "dimension_counts": dict(sorted(dimension_counts.items())),
        },
        "textures": textures,
        "errors": errors,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if args.tsv is not None:
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "outer_index",
            "outer_id",
            "chunk_index",
            "chunk_offset",
            "name",
            "format_name",
            "width",
            "height",
            "depth",
            "mip_levels",
            "pixel_offset",
            "palette_offset",
            "conversion_status",
            "decoded_sha256",
            "rgba_sha256",
            "png_path",
        ]
        with args.tsv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(textures)

    print(json.dumps(result["summary"], indent=2))
    for error in errors:
        print(
            f"{error['error']} outer={error['outer_index']} chunk={error.get('chunk_index')}",
            file=sys.stderr,
        )
    return 0 if not errors else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FormatError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc
