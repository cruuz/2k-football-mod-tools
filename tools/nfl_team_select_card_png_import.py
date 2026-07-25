#!/usr/bin/env python3
"""Fail-closed PNG importer for proved standalone NFL 2K5 Team Select cards."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from nfl_outer import parse_archive, read_entry_range
from nfl_txtr import (HEADER, decode_chunk, encode_rgba_png, parse_chunks,
                      parse_texture, swizzle_2d, texture_to_rgba)
import nfl_tset_png_import as palette_tools
from nfl_team_select_card_targets import (DEFAULT_REPORT, CardTarget, TargetError,
                                           select_target)


SCHEMA = "nfl2k5_team_select_card_png_import/v1"
MAX_PNG_BYTES = 32 * 1024 * 1024


class CardImportError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CardImportError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def difference_runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "difference inputs have unequal size")
    runs: list[list[int]] = []
    for index, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        if not runs or index != runs[-1][1] + 1:
            runs.append([index, index])
        else:
            runs[-1][1] = index
    return runs


def read_png(path: Path, dimensions: tuple[int, int]) -> tuple[Path, bytes, bytes]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "input PNG must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and
                (opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino),
                "input PNG pathname changed")
        require(opened.st_size <= MAX_PNG_BYTES, "input PNG exceeds 32 MiB")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(chunk), "short input PNG read")
            chunks.append(chunk)
            remaining -= len(chunk)
        require(not os.read(descriptor, 1), "input PNG grew while reading")
        payload = b"".join(chunks)
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                "input PNG changed while reading")
    finally:
        os.close(descriptor)
    width, height, rgba = palette_tools.decode_rgba_png(
        payload, expected_dimensions=dimensions)
    require((width, height) == dimensions, "input PNG dimensions changed")
    return resolved, payload, rgba


def validate_template(span: bytes, target: CardTarget) -> tuple[object, bytes, object]:
    require(len(span) == target.span_size and digest(span) == target.span_sha256,
            "retail target span hash/size mismatch")
    chunks = parse_chunks(span)
    require(len(chunks) == 1, "isolated target span is not exactly one resource")
    chunk = chunks[0]
    decoded, decode_info = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    require(decode_info is None and not chunk.compressed and chunk.kind == "TXTR" and
            chunk.stored_size == target.stored_size and
            chunk.system_bytes == target.system_bytes and
            chunk.video_bytes == target.video_bytes and
            chunk.compression_magic == 0 and chunk.overlap_scratch_bytes == 0 and
            chunk.reserved0 == 0 and chunk.reserved1 == 0 and
            HEADER.pack(*HEADER.unpack_from(span)) == span[:HEADER.size],
            "target is not the proved raw TXTR wrapper")
    require(texture.name == target.name and texture.name_offset == 32 and
            texture.descriptor_offset == 56 and texture.pixel_offset == 0 and
            texture.palette_offset == target.palette_offset and
            texture.packed_format == target.packed_format and
            texture.packed_size == 0 and texture.descriptor_flags == 0x80000000 and
            texture.format_name == "P8" and texture.mip_levels == 1 and
            texture.width == target.resolution and texture.height == target.resolution and
            texture.depth == 1 and digest(decoded) == target.decoded_sha256,
            "target descriptor/decoded identity mismatch")
    return chunk, decoded, texture


def build_import(index_path: Path, compatibility_path: Path, family: str,
                 asset_code: str, side: str, style: int, resolution: int,
                 png_path: Path, output_names: dict[str, str] | None = None) \
        -> tuple[bytes, bytes, dict[str, Any]]:
    compatibility, compatibility_payload, target = select_target(
        family, asset_code, side, style, resolution, compatibility_path)
    compatibility_value = json.loads(compatibility_payload)
    expected_index = compatibility_value["inputs"]["canonical_index"]
    supplied_index = index_path.lstat()
    require(stat.S_ISREG(supplied_index.st_mode) and
            not stat.S_ISLNK(supplied_index.st_mode),
            "canonical index must be a non-symlink regular file")
    index = index_path.resolve(strict=True)
    index_info = index.stat(follow_symlinks=False)
    index_identity = (index_info.st_dev, index_info.st_ino)
    require(stat.S_ISREG(index_info.st_mode) and
            index_identity == (supplied_index.st_dev, supplied_index.st_ino) and
            index_info.st_size == int(expected_index["size"]),
            "canonical index size/pathname mismatch")
    index_sha256 = file_sha256(index)
    require(index_sha256 == expected_index["sha256"],
            "canonical index SHA-256 mismatch")
    archive = parse_archive(index)
    entry = archive.entries[target.outer_index]
    require(entry.name_id == target.outer_id and entry.size == target.outer_size,
            "target outer identity changed")
    span = read_entry_range(
        archive, entry, target.chunk_offset, target.span_size)
    padding = read_entry_range(
        archive, entry, target.chunk_offset + target.span_size,
        target.slot_size - target.span_size)
    current_index = index.stat(follow_symlinks=False)
    require((current_index.st_dev, current_index.st_ino, current_index.st_size) ==
            (index_identity[0], index_identity[1], index_info.st_size),
            "canonical index pathname changed while reading target")
    require(padding == bytes(96), "target post-span fixed-slot padding changed")
    chunk, decoded, texture = validate_template(span, target)

    png, png_payload, rgba = read_png(
        png_path, (target.resolution, target.resolution))
    level = palette_tools.MipLevel(0, target.resolution, target.resolution, rgba)
    palette, index_levels, quantization = palette_tools.quantize_levels([level])
    require(len(index_levels) == 1 and len(index_levels[0]) == target.palette_offset,
            "quantized index count differs from target allocation")
    linear_indices = index_levels[0]
    swizzled_indices = swizzle_2d(
        linear_indices, target.resolution, target.resolution, 1)
    palette_bgra = palette_tools.palette_bytes(palette)
    require(len(palette_bgra) == 1024 and
            len(swizzled_indices) + len(palette_bgra) == target.video_bytes,
            "encoded P8 video bytes differ from fixed allocation")

    rebuilt_decoded = (
        decoded[:target.system_bytes] + swizzled_indices + palette_bgra
    )
    require(len(rebuilt_decoded) == len(decoded), "rebuilt decoded size changed")
    rebuilt_span = span[:HEADER.size] + rebuilt_decoded
    require(len(rebuilt_span) == target.span_size and
            rebuilt_span[:HEADER.size] == span[:HEADER.size] and
            rebuilt_decoded[:target.system_bytes] == decoded[:target.system_bytes],
            "wrapper/system bytes changed")
    rebuilt_chunk, roundtrip, rebuilt_texture = validate_rebuilt(
        rebuilt_span, target, span[:HEADER.size], decoded[:target.system_bytes])
    expected_rgba = palette_tools.rgba_from_indices(linear_indices, palette)
    actual_rgba = texture_to_rgba(roundtrip, rebuilt_chunk, rebuilt_texture)
    require(actual_rgba == expected_rgba,
            "rebuilt card decode differs from deterministic quantization")
    preview = encode_rgba_png(target.resolution, target.resolution, actual_rgba)
    require(palette_tools.decode_rgba_png(
        preview, (target.resolution, target.resolution)) ==
        (target.resolution, target.resolution, actual_rgba),
        "generated preview failed strict PNG reparse")
    runs = difference_runs(span, rebuilt_span)
    require(runs, "input PNG quantized to the retail target unchanged")
    changed = sum(end - start + 1 for start, end in runs)
    require(all(start >= HEADER.size + target.system_bytes for start, _ in runs),
            "rebuilt differences escape video bytes")

    names = output_names or {
        "span_file": "replacement.txtr.bin",
        "manifest_file": "import.json",
        "preview_file": "preview.png",
    }
    require(set(names) == {"span_file", "manifest_file", "preview_file"} and
            all(Path(value).name == value and value not in {"", ".", ".."}
                for value in names.values()), "invalid output filenames")
    target_record = asdict(target)
    target_record["outer_id"] = f"0x{target.outer_id:08x}"
    target_record["packed_format"] = f"0x{target.packed_format:08x}"
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "canonical_index": {
            "path": str(index), "size": index.stat().st_size,
            "sha256": index_sha256,
        },
        "compatibility_report": {
            "path": str(compatibility),
            "sha256": digest(compatibility_payload),
        },
        "target": target_record,
        "input_png": {
            "path": str(png), "file_name": png.name,
            "size": len(png_payload), "sha256": digest(png_payload),
            "dimensions": [target.resolution, target.resolution],
            "rgba_sha256": digest(rgba), "strict_rgba8_noninterlaced": True,
        },
        "template": {
            "span_sha256": digest(span), "span_size": len(span),
            "header_hex": span[:HEADER.size].hex(),
            "system_sha256": digest(decoded[:target.system_bytes]),
            "post_span_padding_bytes": len(padding),
            "post_span_padding_all_zero": True,
            "compressed": False, "compression_magic": "0x00000000",
            "vc_lz_stream_tag": None, "overlap_scratch_bytes": 0,
            "vc_lz_alias_constraint": "not_applicable_raw_resource",
        },
        "quantization": quantization,
        "replacement": {
            "span_sha256": digest(rebuilt_span), "span_size": len(rebuilt_span),
            "decoded_sha256": digest(rebuilt_decoded),
            "rgba_sha256": digest(actual_rgba),
            "linear_indices_sha256": digest(linear_indices),
            "swizzled_indices_sha256": digest(swizzled_indices),
            "palette_bgra_sha256": digest(palette_bgra),
            "palette_entries_used": len(palette),
            "changed_byte_count": changed,
            "changed_run_count": len(runs),
            "changed_runs": runs,
            "wrapper_identical": True, "system_bytes_identical": True,
            "fixed_span_identical_size": True,
        },
        "preview": {
            "file_name": names["preview_file"], "sha256": digest(preview),
            "size": len(preview), "rgba_sha256": digest(actual_rgba),
            "strictly_reparsed": True,
        },
        "outputs": names,
        "claims": {
            "bounded_standalone_team_select_card_only": True,
            "raw_uncompressed_fixed_span": True,
            "wrapper_descriptor_and_system_bytes_preserved": True,
            "post_span_padding_not_in_output": True,
            "retail_artwork_exported_or_bundled": False,
            "runtime_visibility_proved": False,
            "portme": "PORTME(runtime): capture the edited card in Team Select before claiming visibility.",
        },
    }
    return rebuilt_span, preview, report


def validate_rebuilt(span: bytes, target: CardTarget, expected_header: bytes,
                     expected_system: bytes) -> tuple[object, bytes, object]:
    require(len(span) == target.span_size and span[:HEADER.size] == expected_header,
            "rebuilt wrapper changed")
    chunks = parse_chunks(span)
    require(len(chunks) == 1, "rebuilt span is not one resource")
    chunk = chunks[0]
    decoded, info = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    require(info is None and not chunk.compressed and
            decoded[:target.system_bytes] == expected_system and
            texture.name == target.name and texture.descriptor_offset == 56 and
            texture.pixel_offset == 0 and texture.palette_offset == target.palette_offset and
            texture.packed_format == target.packed_format and texture.packed_size == 0 and
            texture.descriptor_flags == 0x80000000 and texture.format_name == "P8" and
            texture.mip_levels == 1 and texture.width == target.resolution and
            texture.height == target.resolution and texture.depth == 1,
            "rebuilt descriptor/system contract changed")
    return chunk, decoded, texture


def file_sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def exclusive_write(path: Path, payload: bytes) -> tuple[Path, tuple[int, int]]:
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    descriptor = os.open(
        target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0), 0o644)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    success = False
    try:
        position = 0
        while position < len(payload):
            written = os.write(descriptor, payload[position:])
            require(written > 0, "short output write")
            position += written
        os.fsync(descriptor)
        current = target.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino) == identity and
                current.st_size == len(payload), "output pathname/size changed")
        success = True
        return target, identity
    finally:
        os.close(descriptor)
        if not success:
            try:
                current = target.stat(follow_symlinks=False)
                if (current.st_dev, current.st_ino) == identity:
                    target.unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path,
                        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--family", required=True)
    parser.add_argument("--asset-code", required=True)
    parser.add_argument("--side", required=True)
    parser.add_argument("--style", required=True, type=int)
    parser.add_argument("--resolution", required=True, type=int)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--output-span", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        names = {
            "span_file": args.output_span.name,
            "manifest_file": args.manifest.name,
            "preview_file": args.preview.name,
        }
        span, preview, report = build_import(
            args.index, args.compatibility, args.family, args.asset_code,
            args.side, args.style, args.resolution, args.png, names)
        manifest = canonical_json(report)
        paths = [args.output_span.resolve(strict=False),
                 args.preview.resolve(strict=False), args.manifest.resolve(strict=False)]
        require(len(set(paths)) == 3 and all(not path.exists() for path in paths),
                "outputs alias or already exist")
        written: list[tuple[Path, tuple[int, int]]] = []
        try:
            written.append(exclusive_write(args.output_span, span))
            written.append(exclusive_write(args.preview, preview))
            written.append(exclusive_write(args.manifest, manifest))
        except Exception:
            for path, identity in reversed(written):
                try:
                    current = path.stat(follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == identity:
                        path.unlink()
                except FileNotFoundError:
                    pass
            raise
    except (OSError, CardImportError, TargetError,
            palette_tools.ImportError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "selector": report["target"]["selector"],
        "replacement_sha256": report["replacement"]["span_sha256"],
        "preview_sha256": report["preview"]["sha256"],
        "runtime_visibility_proved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
