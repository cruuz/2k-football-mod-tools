#!/usr/bin/env python3
"""Fail-closed PNG importer for proved NFL 2K5 numeric roster portraits."""

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

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import parse_archive, read_entry_range
from nfl_player_portrait_targets import (DEFAULT_REPORT, PortraitTarget,
                                         TargetError, select_target)
from nfl_txtr import (HEADER, decode_chunk, encode_rgba_png, parse_chunks,
                      parse_texture, swizzle_2d, texture_to_rgba)
import nfl_tset_png_import as palette_tools


SCHEMA = "nfl2k5_player_portrait_png_import/v1"
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INDEX_SIZE = 193_710_080
MAX_PNG_BYTES = 32 * 1024 * 1024


class PortraitImportError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PortraitImportError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def difference_runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "difference inputs have unequal size")
    result: list[list[int]] = []
    for index, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        if not result or index != result[-1][1] + 1:
            result.append([index, index])
        else:
            result[-1][1] = index
    return result


def read_png(path: Path) -> tuple[Path, bytes, bytes]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "input PNG must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and
                (opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino) and
                opened.st_size <= MAX_PNG_BYTES,
                "input PNG pathname/type/size changed")
        pieces: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), "short input PNG read")
            pieces.append(block)
            remaining -= len(block)
        require(not os.read(descriptor, 1), "input PNG grew while reading")
        payload = b"".join(pieces)
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                "input PNG changed while reading")
    finally:
        os.close(descriptor)
    width, height, rgba = palette_tools.decode_rgba_png(payload, (128, 128))
    require((width, height) == (128, 128), "portrait PNG dimensions changed")
    return resolved, payload, rgba


def validate_span(span: bytes, target: PortraitTarget,
                  expected_header: bytes | None = None,
                  expected_system: bytes | None = None) -> tuple[object, bytes, object]:
    require(len(span) == target.span_size, "portrait span size changed")
    chunks = parse_chunks(span)
    require(len(chunks) == 1, "portrait span is not exactly one resource")
    chunk = chunks[0]
    decoded, decode_info = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    require(decode_info is None and chunk.kind == "TXTR" and not chunk.compressed and
            chunk.stored_size == target.stored_size and
            chunk.system_bytes == target.system_bytes and
            chunk.video_bytes == target.video_bytes and
            chunk.compression_magic == 0 and chunk.overlap_scratch_bytes == 0 and
            chunk.reserved0 == 0 and chunk.reserved1 == 0 and
            HEADER.pack(*HEADER.unpack_from(span)) == span[:HEADER.size] and
            texture.name == target.name and texture.name_offset == target.name_offset and
            texture.descriptor_offset == target.descriptor_offset and
            texture.pixel_offset == target.pixel_offset and
            texture.palette_offset == target.palette_offset and
            texture.packed_format == target.packed_format and texture.packed_size == 0 and
            texture.descriptor_flags == 0x80000000 and texture.format_name == "P8" and
            texture.mip_levels == 1 and texture.width == texture.height == 128 and
            texture.depth == 1,
            "portrait wrapper/descriptor contract changed")
    if expected_header is not None:
        require(span[:HEADER.size] == expected_header, "rebuilt portrait wrapper changed")
    if expected_system is not None:
        require(decoded[:target.system_bytes] == expected_system,
                "rebuilt portrait system bytes changed")
    return chunk, decoded, texture


def build_import(index_path: Path, compatibility_path: Path,
                 portrait_id: str | int, png_path: Path,
                 output_names: dict[str, str] | None = None) \
        -> tuple[bytes, bytes, dict[str, Any]]:
    compatibility, compatibility_payload, target = select_target(
        portrait_id, compatibility_path)
    supplied_index = index_path.lstat()
    require(stat.S_ISREG(supplied_index.st_mode) and
            not stat.S_ISLNK(supplied_index.st_mode),
            "canonical index must be a non-symlink regular file")
    index = index_path.resolve(strict=True)
    index_info = index.stat(follow_symlinks=False)
    require((index_info.st_dev, index_info.st_ino, index_info.st_size) ==
            (supplied_index.st_dev, supplied_index.st_ino, INDEX_SIZE) and
            file_digest(index) == INDEX_SHA256,
            "canonical index identity/hash changed")
    archive = parse_archive(index)
    entry = archive.entries[target.outer_index]
    require(entry.name_id == target.outer_id and entry.size == target.outer_size,
            "portrait aggregate identity changed")
    span = read_entry_range(archive, entry, target.chunk_offset, target.span_size)
    padding = read_entry_range(archive, entry,
                               target.chunk_offset + target.span_size,
                               target.post_span_padding_bytes)
    require(digest(span) == target.span_sha256 and
            digest(padding) == target.post_span_padding_sha256 and
            padding == bytes(target.post_span_padding_bytes),
            "retail portrait span/padding changed")
    chunk, decoded, texture = validate_span(span, target)
    require(digest(decoded) == target.decoded_sha256 and
            digest(texture_to_rgba(decoded, chunk, texture)) == target.rgba_sha256,
            "retail portrait decoded/RGBA identity changed")

    png, png_payload, rgba = read_png(png_path)
    level = palette_tools.MipLevel(0, 128, 128, rgba)
    palette, index_levels, quantization = palette_tools.quantize_levels([level])
    require(len(index_levels) == 1 and len(index_levels[0]) == target.palette_offset,
            "portrait quantized index count changed")
    linear_indices = index_levels[0]
    swizzled_indices = swizzle_2d(linear_indices, 128, 128, 1)
    palette_bgra = palette_tools.palette_bytes(palette)
    require(len(swizzled_indices) == 16_384 and len(palette_bgra) == 1024 and
            len(swizzled_indices) + len(palette_bgra) == target.video_bytes,
            "portrait P8 video allocation changed")
    rebuilt_decoded = decoded[:target.system_bytes] + swizzled_indices + palette_bgra
    rebuilt_span = span[:HEADER.size] + rebuilt_decoded
    rebuilt_chunk, roundtrip, rebuilt_texture = validate_span(
        rebuilt_span, target, span[:HEADER.size], decoded[:target.system_bytes])
    expected_rgba = palette_tools.rgba_from_indices(linear_indices, palette)
    actual_rgba = texture_to_rgba(roundtrip, rebuilt_chunk, rebuilt_texture)
    require(actual_rgba == expected_rgba,
            "rebuilt portrait differs from deterministic quantization")
    preview = encode_rgba_png(128, 128, actual_rgba)
    require(palette_tools.decode_rgba_png(preview, (128, 128)) ==
            (128, 128, actual_rgba), "portrait preview failed strict reparse")
    runs = difference_runs(span, rebuilt_span)
    require(runs and all(start >= HEADER.size + target.system_bytes for start, _ in runs),
            "portrait replacement is unchanged or escapes video bytes")
    changed = sum(end - start + 1 for start, end in runs)

    names = output_names or {
        "span_file": "replacement.txtr.bin",
        "manifest_file": "import.json",
        "preview_file": "preview.png",
    }
    require(set(names) == {"span_file", "manifest_file", "preview_file"} and
            all(Path(value).name == value and value not in {"", ".", ".."}
                for value in names.values()), "invalid portrait output filenames")
    record = asdict(target)
    record["outer_id"] = f"0x{target.outer_id:08x}"
    record["packed_format"] = f"0x{target.packed_format:08x}"
    record["span_segments"] = list(target.span_segments)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "canonical_index": {"path": str(index), "size": INDEX_SIZE,
                            "sha256": INDEX_SHA256},
        "compatibility_report": {"path": str(compatibility),
                                 "sha256": digest(compatibility_payload)},
        "target": record,
        "input_png": {"path": str(png), "file_name": png.name,
                      "size": len(png_payload), "sha256": digest(png_payload),
                      "dimensions": [128, 128], "rgba_sha256": digest(rgba),
                      "strict_rgba8_noninterlaced": True},
        "template": {"span_sha256": digest(span), "span_size": len(span),
                     "header_hex": span[:HEADER.size].hex(),
                     "system_sha256": digest(decoded[:target.system_bytes]),
                     "post_span_padding_bytes": len(padding),
                     "post_span_padding_all_zero": True,
                     "compressed": False, "compression_magic": "0x00000000",
                     "vc_lz_stream_tag": None},
        "quantization": quantization,
        "replacement": {"span_sha256": digest(rebuilt_span),
                        "span_size": len(rebuilt_span),
                        "decoded_sha256": digest(rebuilt_decoded),
                        "rgba_sha256": digest(actual_rgba),
                        "linear_indices_sha256": digest(linear_indices),
                        "swizzled_indices_sha256": digest(swizzled_indices),
                        "palette_bgra_sha256": digest(palette_bgra),
                        "palette_entries_used": len(palette),
                        "changed_byte_count": changed,
                        "changed_run_count": len(runs), "changed_runs": runs,
                        "wrapper_identical": True, "system_bytes_identical": True,
                        "fixed_span_identical_size": True},
        "preview": {"file_name": names["preview_file"],
                    "sha256": digest(preview), "size": len(preview),
                    "rgba_sha256": digest(actual_rgba), "strictly_reparsed": True},
        "outputs": names,
        "claims": {"bounded_numeric_roster_portrait_only": True,
                   "raw_uncompressed_fixed_span": True,
                   "wrapper_descriptor_and_system_bytes_preserved": True,
                   "action_photo_family_modified": False,
                   "live_3d_face_family_modified": False,
                   "retail_artwork_exported_or_bundled": False,
                   "runtime_visibility_proved": False,
                   "portme": "PORTME(runtime): capture the edited portrait in a roster/wrap-up UI before claiming visibility."},
    }
    return rebuilt_span, preview, report


def exclusive_write(path: Path, payload: bytes) -> tuple[Path, tuple[int, int]]:
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0), 0o644)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    success = False
    try:
        position = 0
        while position < len(payload):
            written = os.write(descriptor, payload[position:])
            require(written > 0, "short portrait output write")
            position += written
        os.fsync(descriptor)
        current = target.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], len(payload)),
                "portrait output pathname/size changed")
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
    parser.add_argument("--portrait-id", required=True)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--output-span", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        names = {"span_file": args.output_span.name,
                 "manifest_file": args.manifest.name,
                 "preview_file": args.preview.name}
        span, preview, report = build_import(
            args.index, args.compatibility, args.portrait_id, args.png, names)
        manifest = canonical_json(report)
        paths = [args.output_span.resolve(strict=False), args.preview.resolve(strict=False),
                 args.manifest.resolve(strict=False)]
        require(len(set(paths)) == 3 and all(not path.exists() for path in paths),
                "portrait outputs alias or already exist")
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
    except (OSError, ValueError, KeyError, json.JSONDecodeError,
            palette_tools.ImportError, TargetError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"selector": report["target"]["selector"],
                      "replacement_sha256": report["replacement"]["span_sha256"],
                      "preview_sha256": report["preview"]["sha256"],
                      "runtime_visibility_proved": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
