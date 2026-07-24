#!/usr/bin/env python3
"""Compile one user PNG into a proved NFL 2K5 Crib Team Photo span.

The importer is deliberately bounded to the 128 ``##_photo_0#`` resources in
the pinned compact Crib catalog.  It regenerates one shared P8 palette
and all five independently swizzled mip levels while preserving the retail
wrapper, descriptor, system bytes, fixed span, and following slot padding.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping

from nfl_crib_team_photo_targets import (
    DEFAULT_REPORT,
    CribTeamPhotoTarget,
    TargetError,
    select_target,
)
from nfl_outer import parse_archive, read_entry_range
import nfl_tset_png_import as palette_tools
from nfl_txtr import (
    HEADER,
    decode_chunk,
    encode_rgba_png,
    parse_chunks,
    parse_texture,
    swizzle_2d,
    texture_to_rgba,
    unswizzle_2d,
)


SCHEMA = "nfl2k5_crib_team_photo_png_import/v1"
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INDEX_SIZE = 193_710_080
MAX_PNG_BYTES = 32 * 1024 * 1024


class CribPhotoImportError(ValueError):
    """The selected source, target, PNG, or rebuilt span failed closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CribPhotoImportError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def difference_runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "Crib Team Photo difference size changed")
    runs: list[list[int]] = []
    for index, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        if not runs or index != runs[-1][1] + 1:
            runs.append([index, index])
        else:
            runs[-1][1] = index
    return runs


def read_png(path: Path) -> tuple[Path, bytes, bytes]:
    supplied = path.lstat()
    require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        "Crib Team Photo PNG must be a non-symlink regular file",
    )
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        require(
            stat.S_ISREG(opened.st_mode)
            and (opened.st_dev, opened.st_ino)
            == (supplied.st_dev, supplied.st_ino)
            and 0 < opened.st_size <= MAX_PNG_BYTES,
            "Crib Team Photo PNG pathname/type/size changed",
        )
        pieces: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), "short Crib Team Photo PNG read")
            pieces.append(block)
            remaining -= len(block)
        require(not os.read(descriptor, 1), "Crib Team Photo PNG grew while reading")
        payload = b"".join(pieces)
        current = resolved.stat(follow_symlinks=False)
        require(
            (current.st_dev, current.st_ino, current.st_size)
            == (opened.st_dev, opened.st_ino, opened.st_size),
            "Crib Team Photo PNG changed while reading",
        )
    finally:
        os.close(descriptor)
    try:
        width, height, rgba = palette_tools.decode_rgba_png(payload, (128, 128))
    except palette_tools.ImportError as exc:
        raise CribPhotoImportError(
            "Crib Team Photos require an exact 128x128 non-interlaced RGBA8 PNG: "
            f"{exc}"
        ) from exc
    require((width, height) == (128, 128), "Crib Team Photo PNG dimensions changed")
    return resolved, payload, rgba


def generate_mips(rgba: bytes) -> list[palette_tools.MipLevel]:
    """Use the provider's established unpremultiplied 2x2 RGBA box filter."""

    require(len(rgba) == 128 * 128 * 4, "Crib Team Photo base RGBA size changed")
    result = [palette_tools.MipLevel(0, 128, 128, rgba)]
    current = rgba
    width = 128
    height = 128
    for level in range(1, 5):
        next_width = width // 2
        next_height = height // 2
        downsampled = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                sources = (
                    ((y * 2) * width + x * 2) * 4,
                    ((y * 2) * width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * width + x * 2) * 4,
                    (((y * 2) + 1) * width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    total = sum(current[source + channel] for source in sources)
                    downsampled[target + channel] = (total + 2) // 4
        current = bytes(downsampled)
        width = next_width
        height = next_height
        result.append(palette_tools.MipLevel(level, width, height, current))
    require(
        tuple((level.width, level.height) for level in result)
        == ((128, 128), (64, 64), (32, 32), (16, 16), (8, 8)),
        "Crib Team Photo mip dimensions changed",
    )
    return result


def _validate_span(
    span: bytes,
    target: CribTeamPhotoTarget,
    *,
    expected_header: bytes | None = None,
    expected_system: bytes | None = None,
) -> tuple[object, bytes, object]:
    require(len(span) == target.span_size, "Crib Team Photo span size changed")
    chunks = parse_chunks(span)
    require(len(chunks) == 1, "Crib Team Photo span is not exactly one resource")
    chunk = chunks[0]
    decoded, decode_info = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    require(
        decode_info is None
        and chunk.kind == "TXTR"
        and not chunk.compressed
        and chunk.stored_size == target.stored_size
        and chunk.system_bytes == target.system_bytes
        and chunk.video_bytes == target.video_bytes
        and chunk.compression_magic == 0
        and chunk.overlap_scratch_bytes == 0
        and chunk.reserved0 == 0
        and chunk.reserved1 == 0
        and HEADER.pack(*HEADER.unpack_from(span)) == span[:HEADER.size]
        and texture.name == target.name
        and texture.name_offset == target.name_offset
        and texture.descriptor_offset == target.descriptor_offset
        and texture.pixel_offset == target.pixel_offset
        and texture.palette_offset == target.palette_offset
        and texture.packed_format == target.packed_format
        and texture.packed_size == 0
        and texture.descriptor_flags == 0x80000000
        and texture.format_name == "P8"
        and texture.mip_levels == target.mip_levels
        and texture.width == texture.height == 128
        and texture.depth == 1,
        "Crib Team Photo wrapper/descriptor contract changed",
    )
    if expected_header is not None:
        require(span[:HEADER.size] == expected_header,
                "rebuilt Crib Team Photo wrapper changed")
    if expected_system is not None:
        require(decoded[:target.system_bytes] == expected_system,
                "rebuilt Crib Team Photo system bytes changed")
    return chunk, decoded, texture


def _record_int(target: Mapping[str, Any], name: str) -> int:
    value = target[name]
    return int(value, 0) if isinstance(value, str) else int(value)


def validate_source_binding(
    span: bytes, padding: bytes, target: Mapping[str, Any]
) -> None:
    """Independently bind a unified build target to the live source XISO."""

    selected = CribTeamPhotoTarget(
        selector=str(target["selector"]),
        asset_code=str(target["asset_code"]),
        variant=_record_int(target, "variant"),
        name=str(target["name"]),
        outer_index=_record_int(target, "outer_index"),
        outer_id=_record_int(target, "outer_id"),
        outer_size=_record_int(target, "outer_size"),
        chunk_index=_record_int(target, "chunk_index"),
        chunk_offset=_record_int(target, "chunk_offset"),
        slot_size=_record_int(target, "slot_size"),
        span_size=_record_int(target, "span_size"),
        stored_size=_record_int(target, "stored_size"),
        system_bytes=_record_int(target, "system_bytes"),
        video_bytes=_record_int(target, "video_bytes"),
        name_offset=_record_int(target, "name_offset"),
        descriptor_offset=_record_int(target, "descriptor_offset"),
        pixel_offset=_record_int(target, "pixel_offset"),
        palette_offset=_record_int(target, "palette_offset"),
        palette_bytes=_record_int(target, "palette_bytes"),
        packed_format=_record_int(target, "packed_format"),
        mip_levels=_record_int(target, "mip_levels"),
        mip_dimensions=tuple(_record_int({"v": value}, "v")
                             for value in target["mip_dimensions"]),
        mip_index_bytes=tuple(_record_int({"v": value}, "v")
                              for value in target["mip_index_bytes"]),
        post_span_zero_padding=_record_int(target, "post_span_zero_padding"),
        span_sha256=str(target["span_sha256"]),
        decoded_sha256=str(target["decoded_sha256"]),
        rgba_sha256=str(target["rgba_sha256"]),
        xiso_pack_path=str(target["xiso_pack_path"]),
        xiso_pack_sector=_record_int(target, "xiso_pack_sector"),
        xiso_pack_size=_record_int(target, "xiso_pack_size"),
        xiso_pack_sha256=str(target["xiso_pack_sha256"]),
        pack_offset=_record_int(target, "pack_offset"),
        xiso_absolute_span_offset=_record_int(target, "xiso_absolute_span_offset"),
    )
    require(
        digest(span) == selected.span_sha256
        and len(padding) == selected.post_span_zero_padding
        and padding == bytes(selected.post_span_zero_padding)
        and digest(span[:HEADER.size]) == target["wrapper_header_sha256"]
        and digest(padding) == target["post_span_padding_sha256"],
        "live source Crib Team Photo span/wrapper padding changed",
    )
    chunk, decoded, texture = _validate_span(span, selected)
    require(
        digest(decoded) == selected.decoded_sha256
        and digest(decoded[:selected.system_bytes]) == target["system_sha256"]
        and digest(texture_to_rgba(decoded, chunk, texture)) == selected.rgba_sha256,
        "live source Crib Team Photo decoded/system/RGBA identity changed",
    )


def build_import(
    index_path: Path,
    catalog_path: Path,
    selector: str,
    png_path: Path,
    output_names: dict[str, str] | None = None,
) -> tuple[bytes, bytes, dict[str, Any]]:
    catalog, catalog_payload, target = select_target(selector, catalog_path)
    supplied_index = index_path.lstat()
    require(
        stat.S_ISREG(supplied_index.st_mode)
        and not stat.S_ISLNK(supplied_index.st_mode),
        "canonical index must be a non-symlink regular file",
    )
    index = index_path.resolve(strict=True)
    index_info = index.stat(follow_symlinks=False)
    identity = (index_info.st_dev, index_info.st_ino)
    require(
        stat.S_ISREG(index_info.st_mode)
        and identity == (supplied_index.st_dev, supplied_index.st_ino)
        and index_info.st_size == INDEX_SIZE
        and file_digest(index) == INDEX_SHA256,
        "canonical index identity/size/hash changed",
    )
    archive = parse_archive(index)
    entry = archive.entries[target.outer_index]
    require(
        entry.name_id == target.outer_id and entry.size == target.outer_size,
        "Crib Team Photo aggregate identity changed",
    )
    span = read_entry_range(archive, entry, target.chunk_offset, target.span_size)
    padding = read_entry_range(
        archive,
        entry,
        target.chunk_offset + target.span_size,
        target.post_span_zero_padding,
    )
    current = index.stat(follow_symlinks=False)
    require(
        (current.st_dev, current.st_ino, current.st_size)
        == (identity[0], identity[1], index_info.st_size)
        and digest(span) == target.span_sha256
        and padding == bytes(target.post_span_zero_padding),
        "canonical Crib Team Photo span/padding changed",
    )
    chunk, decoded, texture = _validate_span(span, target)
    require(
        digest(decoded) == target.decoded_sha256
        and digest(texture_to_rgba(decoded, chunk, texture)) == target.rgba_sha256,
        "canonical Crib Team Photo decoded/RGBA identity changed",
    )

    png, png_payload, rgba = read_png(png_path)
    levels = generate_mips(rgba)
    palette, linear_levels, quantization = palette_tools.quantize_levels(levels)
    require(
        tuple(len(indices) for indices in linear_levels) == target.mip_index_bytes,
        "Crib Team Photo quantized mip sizes changed",
    )
    swizzled_levels = [
        swizzle_2d(indices, level.width, level.height, 1)
        for indices, level in zip(linear_levels, levels)
    ]
    index_chain = b"".join(swizzled_levels)
    palette_bgra = palette_tools.palette_bytes(palette)
    require(
        len(index_chain) == target.palette_offset
        and len(palette_bgra) == target.palette_bytes
        and len(index_chain) + len(palette_bgra) == target.video_bytes,
        "Crib Team Photo P8 video allocation changed",
    )
    rebuilt_decoded = decoded[:target.system_bytes] + index_chain + palette_bgra
    rebuilt_span = span[:HEADER.size] + rebuilt_decoded
    rebuilt_chunk, roundtrip, rebuilt_texture = _validate_span(
        rebuilt_span,
        target,
        expected_header=span[:HEADER.size],
        expected_system=decoded[:target.system_bytes],
    )
    require(len(roundtrip) == len(decoded), "Crib Team Photo decoded allocation changed")

    palette_rgba = [
        (
            palette_bgra[index * 4 + 2],
            palette_bgra[index * 4 + 1],
            palette_bgra[index * 4],
            palette_bgra[index * 4 + 3],
        )
        for index in range(256)
    ]
    cursor = 0
    decoded_levels: list[bytes] = []
    for level, expected_indices in zip(levels, linear_levels):
        size = level.width * level.height
        actual_indices = unswizzle_2d(
            index_chain[cursor:cursor + size], level.width, level.height, 1
        )
        require(actual_indices == expected_indices,
                "Crib Team Photo mip swizzle round-trip changed")
        actual_rgba = b"".join(bytes(palette_rgba[index]) for index in actual_indices)
        require(
            actual_rgba == palette_tools.rgba_from_indices(expected_indices, palette),
            "Crib Team Photo mip palette decode changed",
        )
        decoded_levels.append(actual_rgba)
        cursor += size
    require(cursor == target.palette_offset, "Crib Team Photo mip traversal changed")
    base_rgba = texture_to_rgba(roundtrip, rebuilt_chunk, rebuilt_texture)
    require(base_rgba == decoded_levels[0], "Crib Team Photo base decode changed")
    preview = encode_rgba_png(128, 128, base_rgba)
    require(
        palette_tools.decode_rgba_png(preview, (128, 128))
        == (128, 128, base_rgba),
        "Crib Team Photo preview failed strict reparse",
    )
    runs = difference_runs(span, rebuilt_span)
    require(
        bool(runs)
        and all(start >= HEADER.size + target.system_bytes for start, _ in runs),
        "Crib Team Photo replacement is unchanged or escapes video bytes",
    )
    changed = sum(end - start + 1 for start, end in runs)

    names = output_names or {
        "span_file": "replacement.txtr.bin",
        "manifest_file": "import.json",
        "preview_file": "preview.png",
    }
    require(
        set(names) == {"span_file", "manifest_file", "preview_file"}
        and all(
            Path(value).name == value and value not in {"", ".", ".."}
            for value in names.values()
        ),
        "invalid Crib Team Photo output filenames",
    )
    target_record = asdict(target)
    target_record["outer_id"] = f"0x{target.outer_id:08x}"
    target_record["packed_format"] = f"0x{target.packed_format:08x}"
    target_record["mip_dimensions"] = list(target.mip_dimensions)
    target_record["mip_index_bytes"] = list(target.mip_index_bytes)
    target_record.update(
        {
            "wrapper_header_sha256": digest(span[:HEADER.size]),
            "system_sha256": digest(decoded[:target.system_bytes]),
            "post_span_padding_sha256": digest(padding),
        }
    )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "canonical_index": {
            "path": str(index),
            "size": INDEX_SIZE,
            "sha256": INDEX_SHA256,
        },
        "catalog": {
            "path": str(catalog),
            "size": len(catalog_payload),
            "sha256": digest(catalog_payload),
            "payload_policy": "metadata-only-no-retail-bytes",
        },
        "target": target_record,
        "input_png": {
            "path": str(png),
            "file_name": png.name,
            "size": len(png_payload),
            "sha256": digest(png_payload),
            "dimensions": [128, 128],
            "rgba_sha256": digest(rgba),
            "strict_rgba8_noninterlaced": True,
        },
        "template": {
            "span_size": len(span),
            "span_sha256": digest(span),
            "wrapper_header_sha256": digest(span[:HEADER.size]),
            "system_sha256": digest(decoded[:target.system_bytes]),
            "decoded_sha256": digest(decoded),
            "post_span_padding_bytes": len(padding),
            "post_span_padding_sha256": digest(padding),
            "post_span_padding_all_zero": True,
            "compressed": False,
        },
        "mips": {
            "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
            "dimensions": [list((level.width, level.height)) for level in levels],
            "index_bytes": [len(indices) for indices in linear_levels],
            "each_level_swizzled_independently": True,
            "shared_palette_across_all_levels": True,
        },
        "quantization": quantization,
        "replacement": {
            "span_size": len(rebuilt_span),
            "span_sha256": digest(rebuilt_span),
            "decoded_sha256": digest(rebuilt_decoded),
            "rgba_sha256": digest(base_rgba),
            "index_chain_sha256": digest(index_chain),
            "palette_bgra_sha256": digest(palette_bgra),
            "palette_entries_used": len(palette),
            "changed_byte_count": changed,
            "changed_run_count": len(runs),
            "changed_runs": runs,
            "wrapper_identical": True,
            "system_bytes_identical": True,
            "fixed_span_identical_size": True,
        },
        "preview": {
            "file_name": names["preview_file"],
            "size": len(preview),
            "sha256": digest(preview),
            "rgba_sha256": digest(base_rgba),
            "strictly_reparsed": True,
        },
        "outputs": names,
        "claims": {
            "bounded_crib_team_photo_only": True,
            "all_five_p8_mips_regenerated": True,
            "wrapper_descriptor_and_system_bytes_preserved": True,
            "post_span_padding_not_modified": True,
            "roster_portrait_or_live_face_modified": False,
            "retail_artwork_exported_or_bundled": False,
            "runtime_visibility_proved": False,
        },
    }
    return rebuilt_span, preview, report


def _exclusive_write(path: Path, payload: bytes) -> tuple[Path, tuple[int, int]]:
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    descriptor = os.open(
        target,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        0o600,
    )
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    success = False
    try:
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            require(written > 0, "short Crib Team Photo output write")
            cursor += written
        os.fsync(descriptor)
        current = target.stat(follow_symlinks=False)
        require(
            (current.st_dev, current.st_ino, current.st_size)
            == (identity[0], identity[1], len(payload)),
            "Crib Team Photo output pathname/size changed",
        )
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
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"),
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--selector", required=True)
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
            args.index, args.catalog, args.selector, args.png, names
        )
        manifest = canonical_json(report)
        paths = [
            args.output_span.resolve(strict=False),
            args.preview.resolve(strict=False),
            args.manifest.resolve(strict=False),
        ]
        require(
            len(set(paths)) == 3 and all(not path.exists() for path in paths),
            "Crib Team Photo outputs alias or already exist",
        )
        written: list[tuple[Path, tuple[int, int]]] = []
        try:
            written.append(_exclusive_write(args.output_span, span))
            written.append(_exclusive_write(args.preview, preview))
            written.append(_exclusive_write(args.manifest, manifest))
        except Exception:
            for path, identity in reversed(written):
                try:
                    current = path.stat(follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == identity:
                        path.unlink()
                except FileNotFoundError:
                    pass
            raise
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            TargetError, palette_tools.ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "selector": report["target"]["selector"],
                "replacement_sha256": report["replacement"]["span_sha256"],
                "preview_sha256": report["preview"]["sha256"],
                "runtime_visibility_proved": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CribPhotoImportError",
    "SCHEMA",
    "build_import",
    "generate_mips",
    "read_png",
    "validate_source_binding",
]
