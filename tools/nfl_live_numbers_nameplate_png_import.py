#!/usr/bin/env python3
"""Fail-closed PNG importer for NFL 2K5 live number/nameplate art."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from nfl_outer import parse_archive, read_entry_range
from nfl_txtr import (HEADER, decode_chunk, encode_rgba_png, parse_chunks,
                      parse_texture, rebuild_compressed_chunk_fixed_span,
                      swizzle_2d, unswizzle_2d)
from nfl_tset_png_import import (MipLevel, decode_rgba_png, palette_bytes,
                                 quantize_levels, rgba_from_indices)
from nfl_live_numbers_nameplate_targets import (DEFAULT_REPORT, LiveArtTarget,
                                                  select_target)


SCHEMA = "nfl2k5_live_numbers_nameplate_png_import/v1"
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INDEX_SIZE = 193_710_080
MAX_PNG_BYTES = 32 * 1024 * 1024


class ImportError(ValueError):
    """Raised when an input or fixed-span rebuild fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImportError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def difference_runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "difference inputs have unequal lengths")
    result: list[list[int]] = []
    for index, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        if not result or index != result[-1][1] + 1:
            result.append([index, index])
        else:
            result[-1][1] = index
    return result


def read_png(path: Path, dimensions: tuple[int, int]) -> tuple[Path, bytes, bytes]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "input PNG must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and
                (opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino) and
                opened.st_size <= MAX_PNG_BYTES,
                "input PNG identity/type/size mismatch")
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
    width, height, rgba = decode_rgba_png(payload, dimensions)
    require((width, height) == dimensions, "input PNG dimensions changed")
    return resolved, payload, rgba


def make_mips(rgba: bytes, width: int, height: int, count: int) -> list[MipLevel]:
    require(len(rgba) == width * height * 4 and count > 0,
            "base image/mip count mismatch")
    result = [MipLevel(0, width, height, rgba)]
    current = rgba
    current_width = width
    current_height = height
    for level in range(1, count):
        require(current_width % 2 == 0 and current_height % 2 == 0,
                "mip dimensions cannot be halved exactly")
        next_width = current_width // 2
        next_height = current_height // 2
        down = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                sources = (
                    ((y * 2) * current_width + x * 2) * 4,
                    ((y * 2) * current_width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * current_width + x * 2) * 4,
                    (((y * 2) + 1) * current_width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    down[target + channel] = (
                        sum(current[source + channel] for source in sources) + 2
                    ) // 4
        current = bytes(down)
        current_width = next_width
        current_height = next_height
        result.append(MipLevel(level, current_width, current_height, current))
    return result


def parse_palette(video: bytes, offset: int) -> list[tuple[int, int, int, int]]:
    require(offset + 1024 <= len(video), "palette exceeds video allocation")
    result = []
    for index in range(256):
        blue, green, red, alpha = video[offset + index * 4:offset + index * 4 + 4]
        result.append((red, green, blue, alpha))
    return result


def decode_levels(decoded: bytes, chunk: Any, texture: Any) -> list[MipLevel]:
    video = decoded[chunk.system_bytes:chunk.system_bytes + chunk.video_bytes]
    palette = parse_palette(video, texture.palette_offset)
    result: list[MipLevel] = []
    offset = texture.pixel_offset
    width = texture.width
    height = texture.height
    for level in range(texture.mip_levels):
        count = width * height
        encoded = video[offset:offset + count]
        require(len(encoded) == count, f"mip {level} is truncated")
        if texture.format_name == "P8":
            indices = unswizzle_2d(encoded, width, height, 1)
        else:
            require(texture.format_name == "VC_P8_LINEAR",
                    "unexpected texture format in mip decoder")
            indices = encoded
        result.append(MipLevel(level, width, height,
                               rgba_from_indices(indices, palette)))
        offset += count
        if level + 1 != texture.mip_levels:
            require(width % 2 == 0 and height % 2 == 0,
                    "decoded mip chain cannot halve")
            width //= 2
            height //= 2
    require(offset <= texture.palette_offset,
            "decoded mip chain overlaps palette")
    return result


def validate_template(span: bytes, target: LiveArtTarget) -> tuple[Any, bytes, Any]:
    require(len(span) == target.span_size and digest(span) == target.span_sha256,
            "retail target span hash/size mismatch")
    chunks = parse_chunks(span)
    require(len(chunks) == 1, "isolated span is not exactly one resource")
    chunk = chunks[0]
    decoded, info = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    require(info is not None and chunk.compressed and chunk.kind == "TXTR" and
            chunk.stored_size == target.stored_size and
            chunk.system_bytes == target.system_bytes and
            chunk.video_bytes == target.video_bytes and
            chunk.compression_magic == target.compression_magic and
            chunk.overlap_scratch_bytes == target.overlap_scratch_bytes and
            chunk.reserved0 == chunk.reserved1 == 0 and
            info.consumed_bytes == target.lz_consumed_bytes and
            digest(decoded) == target.decoded_sha256,
            "target wrapper/decode identity mismatch")
    require(texture.name == target.resource_name and
            texture.name_offset == target.name_offset and
            texture.descriptor_offset == target.descriptor_offset and
            texture.pixel_offset == 0 and
            texture.palette_offset == target.palette_offset and
            texture.packed_format == target.packed_format and
            texture.packed_size == target.packed_size and
            texture.descriptor_flags == target.descriptor_flags and
            texture.format_name == target.format_name and
            texture.mip_levels == target.mip_levels and
            texture.width == target.width and texture.height == target.height and
            texture.depth == 1,
            "target descriptor identity mismatch")
    return chunk, decoded, texture


def build_import(index_path: Path, compatibility_path: Path, family: str,
                 asset_code: str, side: str, variant: int, digit: int | None,
                 png_path: Path, output_names: dict[str, str] | None = None) \
        -> tuple[bytes, bytes, dict[str, Any]]:
    compatibility, compatibility_payload, target = select_target(
        family, asset_code, side, variant, digit, compatibility_path)
    supplied_index = index_path.lstat()
    require(stat.S_ISREG(supplied_index.st_mode) and
            not stat.S_ISLNK(supplied_index.st_mode),
            "canonical index must be a non-symlink regular file")
    index = index_path.resolve(strict=True)
    index_info = index.stat(follow_symlinks=False)
    require((index_info.st_dev, index_info.st_ino, index_info.st_size) ==
            (supplied_index.st_dev, supplied_index.st_ino, INDEX_SIZE) and
            file_digest(index) == INDEX_SHA256,
            "canonical index identity/size/hash mismatch")
    archive = parse_archive(index)
    entry = archive.entries[target.outer_index]
    require(entry.name_id == target.outer_id and entry.size == target.outer_size,
            "target outer identity changed")
    span = read_entry_range(archive, entry, target.chunk_offset, target.span_size)
    chunk, decoded, texture = validate_template(span, target)
    current_index = index.stat(follow_symlinks=False)
    require((current_index.st_dev, current_index.st_ino, current_index.st_size) ==
            (index_info.st_dev, index_info.st_ino, index_info.st_size),
            "canonical index changed while reading target")

    png, png_payload, rgba = read_png(png_path, (target.width, target.height))
    input_mips = make_mips(rgba, target.width, target.height, target.mip_levels)
    palette, index_levels, quantization = quantize_levels(input_mips)
    require(len(index_levels) == target.mip_levels and
            sum(len(level) for level in index_levels) == target.index_chain_bytes,
            "quantized mip chain differs from target allocation")
    encoded_levels = []
    for level, indices in zip(input_mips, index_levels):
        if target.mip_storage == "xbox_morton_swizzled":
            encoded_levels.append(swizzle_2d(indices, level.width, level.height, 1))
        else:
            require(target.mip_storage == "linear", "unknown mip storage class")
            encoded_levels.append(indices)
    index_chain = b"".join(encoded_levels)
    require(len(index_chain) == target.index_chain_bytes,
            "encoded index chain size mismatch")
    template_video = decoded[target.system_bytes:]
    gap_first = target.index_chain_bytes
    gap_after = gap_first + target.pre_palette_gap_bytes
    gap = template_video[gap_first:gap_after]
    require(gap_after == target.palette_offset and len(gap) == target.pre_palette_gap_bytes,
            "template pre-palette gap differs from report")
    rebuilt_video = index_chain + gap + palette_bytes(palette)
    require(len(rebuilt_video) == target.video_bytes,
            "rebuilt video allocation size mismatch")
    rebuilt_decoded = decoded[:target.system_bytes] + rebuilt_video
    rebuilt_span, rebuild = rebuild_compressed_chunk_fixed_span(span, rebuilt_decoded)
    require(len(rebuilt_span) == len(span) and
            rebuilt_span[:20] == span[:20] and rebuilt_span[24:32] == span[24:32] and
            rebuild.loader_in_place_end_guard and rebuild.loader_in_place_alias_guard and
            rebuild.recompressed_bytes <= target.stored_size,
            "fixed-span rebuild contract failed")
    rebuilt_chunks = parse_chunks(rebuilt_span)
    require(len(rebuilt_chunks) == 1, "rebuilt span is not one TXTR")
    rebuilt_chunk = rebuilt_chunks[0]
    roundtrip, info = decode_chunk(rebuilt_span, rebuilt_chunk)
    rebuilt_texture = parse_texture(roundtrip, rebuilt_chunk)
    require(info is not None and roundtrip == rebuilt_decoded and
            roundtrip[:target.system_bytes] == decoded[:target.system_bytes] and
            rebuilt_texture == texture and
            roundtrip[target.system_bytes + gap_first:
                      target.system_bytes + gap_after] == gap,
            "rebuilt descriptor/system/gap round trip mismatch")
    decoded_levels = decode_levels(roundtrip, rebuilt_chunk, rebuilt_texture)
    expected_levels = [
        MipLevel(source.level, source.width, source.height,
                 rgba_from_indices(indices, palette))
        for source, indices in zip(input_mips, index_levels)
    ]
    require(decoded_levels == expected_levels,
            "rebuilt mip chain differs from deterministic quantization")
    preview = encode_rgba_png(
        decoded_levels[0].width, decoded_levels[0].height, decoded_levels[0].rgba)
    require(decode_rgba_png(preview, (target.width, target.height)) ==
            (target.width, target.height, decoded_levels[0].rgba),
            "generated preview failed strict PNG reparse")
    runs = difference_runs(span, rebuilt_span)
    require(runs, "input PNG quantized to the retail target unchanged")
    changed = sum(after - before + 1 for before, after in runs)

    names = output_names or {
        "span_file": "replacement.txtr.bin",
        "manifest_file": "import.json",
        "preview_file": "preview.png",
    }
    require(set(names) == {"span_file", "manifest_file", "preview_file"} and
            all(Path(value).name == value and value not in {"", ".", ".."}
                for value in names.values()), "invalid output filenames")
    target_record = asdict(target)
    target_record["selector"] = target.selector
    target_record["package_selector"] = target.package_selector
    target_record["outer_id"] = f"0x{target.outer_id:08x}"
    target_record["compression_magic"] = f"0x{target.compression_magic:08x}"
    target_record["packed_format"] = f"0x{target.packed_format:08x}"
    target_record["descriptor_flags"] = f"0x{target.descriptor_flags:08x}"
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "canonical_index": {"path": str(index), "size": INDEX_SIZE,
                            "sha256": INDEX_SHA256},
        "compatibility_report": {"path": str(compatibility),
                                 "sha256": digest(compatibility_payload)},
        "target": target_record,
        "input_png": {"path": str(png), "file_name": png.name,
                      "size": len(png_payload), "sha256": digest(png_payload),
                      "dimensions": [target.width, target.height],
                      "rgba_sha256": digest(rgba),
                      "strict_rgba8_noninterlaced": True},
        "mips": {"level_count": target.mip_levels,
                 "dimensions": [[level.width, level.height] for level in input_mips],
                 "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
                 "storage": target.mip_storage,
                 "index_bytes": [len(level) for level in index_levels]},
        "quantization": quantization,
        "template": {"span_sha256": digest(span), "decoded_sha256": digest(decoded),
                     "system_sha256": digest(decoded[:target.system_bytes]),
                     "pre_palette_gap_sha256": digest(gap),
                     "pre_palette_gap_bytes": len(gap),
                     "pre_palette_gap_preserved": True},
        "replacement": {"span_sha256": digest(rebuilt_span),
                        "decoded_sha256": digest(roundtrip),
                        "base_rgba_sha256": digest(decoded_levels[0].rgba),
                        "index_chain_sha256": digest(index_chain),
                        "palette_bgra_sha256": digest(palette_bytes(palette)),
                        "palette_entries_used": len(palette),
                        "changed_byte_count": changed,
                        "changed_run_count": len(runs), "changed_runs": runs,
                        "fixed_span_identical_size": True,
                        "system_and_descriptor_bytes_identical": True,
                        "wrapper_identical_except_overlap_scratch": True},
        "rebuild": asdict(rebuild),
        "preview": {"file_name": names["preview_file"], "size": len(preview),
                    "sha256": digest(preview),
                    "rgba_sha256": digest(decoded_levels[0].rgba),
                    "strictly_reparsed": True},
        "outputs": names,
        "claims": {"bounded_live_uniform_art_only": True,
                   "all_declared_mips_rebuilt": True,
                   "fixed_compressed_span": True,
                   "loader_alias_guarded": True,
                   "name_metrics_modified": False,
                   "retail_artwork_exported_or_bundled": False,
                   "runtime_visibility_proved": False,
                   "portme": (
                       "PORTME(runtime): capture the edited live jersey/helmet/arm/nameplate "
                       "before claiming in-title visibility."
                   )},
    }
    return rebuilt_span, preview, report


def write_exclusive(path: Path, payload: bytes) -> None:
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o644)
    success = False
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    try:
        offset = 0
        while offset < len(payload):
            amount = os.write(descriptor, payload[offset:])
            require(amount > 0, "short output write")
            offset += amount
        os.fsync(descriptor)
        current = target.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], len(payload)),
                "output pathname/size changed")
        success = True
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
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--family", required=True)
    parser.add_argument("--asset-code", required=True)
    parser.add_argument("--side", required=True)
    parser.add_argument("--variant", type=int, required=True)
    parser.add_argument("--digit", type=int)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--output-span", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-preview", type=Path, required=True)
    args = parser.parse_args()
    try:
        paths = [args.output_span, args.output_manifest, args.output_preview]
        require(len({path.resolve(strict=False) for path in paths}) == 3 and
                all(not path.exists() for path in paths),
                "outputs collide or already exist")
        span, preview, report = build_import(
            args.index, args.compatibility, args.family, args.asset_code,
            args.side, args.variant, args.digit, args.png,
            {"span_file": args.output_span.name,
             "manifest_file": args.output_manifest.name,
             "preview_file": args.output_preview.name})
        write_exclusive(args.output_span, span)
        write_exclusive(args.output_preview, preview)
        write_exclusive(args.output_manifest, canonical_json(report))
        print("NFL_LIVE_NUMBERS_NAMEPLATE_IMPORT_COMPLETE "
              f"selector={report['target']['asset_code']}{report['target']['side']}"
              f"{report['target']['variant']}:{report['target']['family']} "
              f"span={len(span)} runtime=false")
        return 0
    except (ImportError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
