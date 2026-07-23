#!/usr/bin/env python3
"""Decode every TXTR located by the NFL 2K5 resource-prefix scan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from nfl_outer import FormatError, parse_archive, read_entry_range
from nfl_txtr import (
    TxtrError,
    decode_chunk,
    parse_chunks,
    parse_texture,
    safe_texture_name,
    texture_to_rgba,
    write_png,
)


_worker_archive = None
_worker_entries = None
_worker_validate = False
_worker_png_dir = None


def blocker(texture: object) -> str | None:
    if texture.dimensions != 2 or texture.depth != 1:
        return f"dimensions={texture.dimensions}, depth={texture.depth}"
    if texture.format_code not in (0x02, 0x06, 0x0B, 0x0C, 0x7F):
        return f"Xbox format {texture.format_name}"
    return None


def initialize_worker(archive: object, validate: bool, png_dir: Path | None) -> None:
    global _worker_archive, _worker_entries, _worker_validate, _worker_png_dir
    _worker_archive = archive
    _worker_entries = {entry.table_index: entry for entry in archive.entries}
    _worker_validate = validate
    _worker_png_dir = png_dir


def process_location(
    location: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if _worker_archive is None or _worker_entries is None:
        raise RuntimeError("texture worker was not initialized")
    outer_index = int(location["outer_index"])
    outer_chunk_index = int(location["chunk_index"])
    outer_chunk_offset = int(location["chunk_offset"])
    stored_size = int(location["stored_size"])
    entry = _worker_entries[outer_index]
    try:
        chunk_data = read_entry_range(
            _worker_archive, entry, outer_chunk_offset, 0x20 + stored_size
        )
        parsed = parse_chunks(chunk_data)
        if len(parsed) != 1:
            raise TxtrError(f"isolated range produced {len(parsed)} chunks, expected one")
        chunk = parsed[0]
        output, decode = decode_chunk(chunk_data, chunk)
        texture = parse_texture(output, chunk)
        why = blocker(texture)
        record: dict[str, object] = {
            "outer_index": outer_index,
            "outer_id": f"0x{entry.name_id:08x}",
            "outer_head": entry.head_ascii,
            "outer_size": entry.size,
            "chunk_index": outer_chunk_index,
            "chunk_offset": outer_chunk_offset,
            "stored_size": chunk.stored_size,
            "system_bytes": chunk.system_bytes,
            "video_bytes": chunk.video_bytes,
            "compressed": chunk.compressed,
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
            "exported_mip_levels": 1,
            "width": texture.width,
            "height": texture.height,
            "depth": texture.depth,
            "decoded_sha256": hashlib.sha256(output).hexdigest(),
            "conversion_status": "base_level_supported" if why is None else f"PORTME: {why}",
        }
        if decode is not None:
            record["lz_offset_bits"] = decode.offset_bits
            record["lz_length_bits"] = decode.length_bits
            record["lz_consumed_bytes"] = decode.consumed_bytes
            record["lz_unused_bytes"] = chunk.stored_size - decode.consumed_bytes

        rgba = None
        if (_worker_validate or _worker_png_dir is not None) and why is None:
            rgba = texture_to_rgba(output, chunk, texture)
        if _worker_validate and rgba is not None:
            record["rgba_sha256"] = hashlib.sha256(rgba).hexdigest()
        if _worker_png_dir is not None and rgba is not None:
            target = (
                _worker_png_dir
                / f"outer_{outer_index:04d}_{entry.name_id:08x}"
                / (
                    f"{outer_chunk_index:04d}_"
                    f"{safe_texture_name(texture.name, 'unnamed')}.png"
                )
            )
            write_png(target, texture.width, texture.height, rgba)
            record["png_path"] = str(target)
        return record, None
    except (FormatError, OSError, TxtrError) as exc:
        return None, {
            "outer_index": outer_index,
            "outer_id": f"0x{entry.name_id:08x}",
            "chunk_index": outer_chunk_index,
            "chunk_offset": outer_chunk_offset,
            "error": f"PORTME: {exc}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to vc_53450030/0")
    parser.add_argument("--resource-scan", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path)
    parser.add_argument("--validate-conversion", action="store_true")
    parser.add_argument("--png-dir", type=Path)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        raise SystemExit("--jobs must be between 1 and 32")

    archive = parse_archive(args.index)
    scan = json.loads(args.resource_scan.read_text(encoding="utf-8"))
    locations = [record for record in scan["chunks"] if record["kind"] == "TXTR"]

    textures: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    if args.jobs == 1:
        initialize_worker(archive, args.validate_conversion, args.png_dir)
        results = map(process_location, locations)
        executor = None
    else:
        executor = ProcessPoolExecutor(
            max_workers=args.jobs,
            initializer=initialize_worker,
            initargs=(archive, args.validate_conversion, args.png_dir),
        )
        results = executor.map(process_location, locations, chunksize=16)
    try:
        for position, (record, error) in enumerate(results, 1):
            if position == 1 or position % 1000 == 0:
                print(f"decoding TXTR {position}/{len(locations)}", file=sys.stderr)
            if record is not None:
                textures.append(record)
            if error is not None:
                errors.append(error)
    finally:
        if executor is not None:
            executor.shutdown()

    formats = Counter(str(texture["format_name"]) for texture in textures)
    dimensions = Counter(
        f"{texture['width']}x{texture['height']}x{texture['depth']}"
        for texture in textures
    )
    status_counts = Counter(str(texture["conversion_status"]) for texture in textures)
    result = {
        "schema": "nfl2k5_all_txtr_inventory/v1",
        "source_index": str(args.index),
        "resource_scan": str(args.resource_scan),
        "selection": {
            "located_txtr_count": len(locations),
            "validate_conversion": args.validate_conversion,
            "png_dir": str(args.png_dir) if args.png_dir is not None else None,
            "png_exports_base_mip_only": True,
            "jobs": args.jobs,
        },
        "summary": {
            "located_texture_count": len(locations),
            "decoded_texture_count": len(textures),
            "error_count": len(errors),
            "format_counts": dict(sorted(formats.items())),
            "dimension_counts": dict(sorted(dimensions.items())),
            "conversion_status_counts": dict(sorted(status_counts.items())),
        },
        "textures": textures,
        "errors": errors,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if args.tsv is not None:
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "outer_index", "outer_id", "outer_head", "chunk_index",
            "chunk_offset", "name", "format_name", "width", "height",
            "depth", "mip_levels", "exported_mip_levels", "pixel_offset",
            "palette_offset", "conversion_status", "decoded_sha256",
            "rgba_sha256", "png_path",
        ]
        with args.tsv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fields, delimiter="\t", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(textures)

    print(json.dumps(result["summary"], indent=2))
    for error in errors:
        print(
            f"{error['error']} outer={error['outer_index']} chunk={error['chunk_index']}",
            file=sys.stderr,
        )
    return 0 if not errors else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FormatError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: {exc}") from exc
