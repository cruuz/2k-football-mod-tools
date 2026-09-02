#!/usr/bin/env python3
"""Fail-closed PNG importer for the live NFL 2K5 helmet00/helmet02 TXTRs."""

from __future__ import annotations

import argparse
from collections import OrderedDict
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
from nfl_txtr import (COMPRESSED_SENTINEL, HEADER, Chunk,
                      decode_chunk, encode_rgba_png,
                      minimum_vc_lz_overlap_scratch, parse_texture,
                      rebuild_compressed_chunk_fixed_span, swizzle_2d,
                      unswizzle_2d)
import nfl_tset_png_import as palette_tools
from nfl_live_helmet_txtr_targets import (DEFAULT_REPORT, HelmetTarget,
                                           select_target)


SCHEMA = "nfl2k5_live_helmet_txtr_png_import/v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INDEX_SIZE = 193_710_080
BASE_SIZE = 256
MIP_DIMENSIONS = tuple((BASE_SIZE >> level, BASE_SIZE >> level) for level in range(6))
INDEX_CHAIN_BYTES = sum(width * height for width, height in MIP_DIMENSIONS)
PALETTE_OFFSET = INDEX_CHAIN_BYTES
VIDEO_BYTES = INDEX_CHAIN_BYTES + 1024
MAX_PNG_BYTES = 32 * 1024 * 1024


class ImportError(ValueError):
    """Raised before output when any target, PNG, or allocation check fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImportError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    info = path.stat()
    key = (str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    cached = _FILE_DIGEST_CACHE.get(key)
    if cached is not None:
        _FILE_DIGEST_CACHE.move_to_end(key)
        return cached
    digest = _file_digest_uncached(path)
    _FILE_DIGEST_CACHE[key] = digest
    _FILE_DIGEST_CACHE.move_to_end(key)
    while len(_FILE_DIGEST_CACHE) > _FILE_DIGEST_CACHE_LIMIT:
        _FILE_DIGEST_CACHE.popitem(last=False)
    return digest


def _file_digest_uncached(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


# The canonical index volume is hash-pinned and image-constant, but a
# multi-edit build used to re-hash its ~193 MB once per edit.  The digest is
# memoized per file identity (path, device, inode, size, mtime); a rewrite
# moves size/mtime and re-hashes.
_FILE_DIGEST_CACHE_LIMIT = 8
_FILE_DIGEST_CACHE: "OrderedDict[tuple[object, ...], str]" = OrderedDict()


def clear_file_digest_cache() -> None:
    """Forget every memoized file digest (tests and fresh sessions)."""

    _FILE_DIGEST_CACHE.clear()


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


def open_read_regular(path: Path, maximum: int, label: str) \
        -> tuple[Path, bytes, tuple[int, int]]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        require(stat.S_ISREG(opened.st_mode) and identity ==
                (supplied.st_dev, supplied.st_ino) and opened.st_size <= maximum,
                f"{label} type/path/size changed")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), f"short {label} read")
            chunks.append(block)
            remaining -= len(block)
        require(not os.read(descriptor, 1), f"{label} grew while reading")
        payload = b"".join(chunks)
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], opened.st_size),
                f"{label} changed while reading")
        return resolved, payload, identity
    finally:
        os.close(descriptor)


def read_png(path: Path) -> tuple[Path, bytes, bytes]:
    resolved, payload, _ = open_read_regular(path, MAX_PNG_BYTES, "input PNG")
    width, height, rgba = palette_tools.decode_rgba_png(
        payload, (BASE_SIZE, BASE_SIZE))
    require((width, height) == (BASE_SIZE, BASE_SIZE) and
            len(rgba) == BASE_SIZE * BASE_SIZE * 4,
            "input PNG is not exact 256x256 RGBA8")
    return resolved, payload, rgba


def generate_mips(rgba: bytes) -> list[palette_tools.MipLevel]:
    require(len(rgba) == BASE_SIZE * BASE_SIZE * 4, "base RGBA size mismatch")
    result = [palette_tools.MipLevel(0, BASE_SIZE, BASE_SIZE, rgba)]
    current = rgba
    width = height = BASE_SIZE
    for level in range(1, 6):
        next_width, next_height = width // 2, height // 2
        downsampled = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                source_offsets = (
                    ((y * 2) * width + x * 2) * 4,
                    ((y * 2) * width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * width + x * 2) * 4,
                    (((y * 2) + 1) * width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    downsampled[target + channel] = (
                        sum(current[offset + channel] for offset in source_offsets) + 2
                    ) // 4
        current = bytes(downsampled)
        width, height = next_width, next_height
        result.append(palette_tools.MipLevel(level, width, height, current))
    require(tuple((item.width, item.height) for item in result) == MIP_DIMENSIONS,
            "generated mip dimensions differ from the proved chain")
    return result


def parse_palette(video: bytes) -> list[tuple[int, int, int, int]]:
    return palette_tools.parse_palette(video, PALETTE_OFFSET)


def decode_levels(decoded: bytes) -> list[palette_tools.MipLevel]:
    require(len(decoded) == 128 + VIDEO_BYTES, "decoded live helmet size mismatch")
    video = decoded[128:]
    palette = parse_palette(video)
    levels: list[palette_tools.MipLevel] = []
    offset = 0
    for level, (width, height) in enumerate(MIP_DIMENSIONS):
        size = width * height
        swizzled = video[offset:offset + size]
        require(len(swizzled) == size, f"mip {level} index bytes truncated")
        indices = unswizzle_2d(swizzled, width, height, 1)
        levels.append(palette_tools.MipLevel(
            level, width, height,
            palette_tools.rgba_from_indices(indices, palette),
        ))
        offset += size
    require(offset == PALETTE_OFFSET, "mip chain does not end at palette")
    return levels


def as_chunk(target: HelmetTarget, overlap_scratch: int | None = None) -> Chunk:
    return Chunk(
        index=0, offset=0, kind="TXTR", stored_size=target.stored_size,
        system_bytes=target.system_bytes, video_bytes=target.video_bytes,
        compression_magic=COMPRESSED_SENTINEL,
        overlap_scratch_bytes=(target.overlap_scratch_bytes if overlap_scratch is None
                               else overlap_scratch),
        reserved0=0, reserved1=0,
    )


def validate_texture(decoded: bytes, target: HelmetTarget) -> object:
    texture = parse_texture(decoded, as_chunk(target))
    require(texture.name == target.family and texture.name_offset == 32 and
            texture.descriptor_offset == 52 and texture.pixel_offset == 0 and
            texture.palette_offset == PALETTE_OFFSET and
            texture.packed_format == 0x08860B29 and texture.packed_size == 0 and
            texture.descriptor_flags == 0x80000000 and
            texture.format_name == "P8" and texture.mip_levels == 6 and
            texture.width == 256 and texture.height == 256 and texture.depth == 1,
            "live helmet TXTR descriptor changed")
    return texture


def load_template(index_path: Path, target: HelmetTarget) \
        -> tuple[Path, bytes, bytes, object]:
    supplied = index_path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "canonical index must be a non-symlink regular file")
    index = index_path.resolve(strict=True)
    info = index.stat(follow_symlinks=False)
    require((info.st_dev, info.st_ino, info.st_size) ==
            (supplied.st_dev, supplied.st_ino, INDEX_SIZE) and
            file_digest(index) == INDEX_SHA256,
            "canonical index size/path/hash changed")
    archive = parse_archive(index)
    entry = archive.entries[target.outer_index]
    require(entry.name_id == target.outer_id and entry.size == target.outer_size,
            "selected outer package changed")
    span = read_entry_range(
        archive, entry, target.chunk_offset, target.span_size)
    require(len(span) == target.span_size and digest(span) == target.span_sha256 and
            HEADER.unpack_from(span) == target.complete_header,
            "retail target span/header changed")
    decoded, decode_info = decode_chunk(span, as_chunk(target))
    require(decode_info is not None and
            decode_info.stream_tag == target.stream_tag and
            decode_info.offset_bits == target.offset_bits and
            decode_info.consumed_bytes == target.lz_consumed_bytes and
            target.stored_size - decode_info.consumed_bytes == target.lz_unused_bytes and
            len(decoded) == target.decoded_size and
            digest(decoded) == target.decoded_sha256 and
            digest(decoded[:128]) == target.system_sha256,
            "retail target decode identity changed")
    validate_texture(decoded, target)
    exact = minimum_vc_lz_overlap_scratch(
        span[HEADER.size:HEADER.size + decode_info.consumed_bytes],
        target.stored_size, target.decoded_size)
    require(exact == target.retail_exact_minimum_overlap_scratch_bytes and
            target.overlap_scratch_bytes >= exact,
            "retail target alias-scratch proof changed")
    return index, span, decoded, decode_info


def build_import(index_path: Path, compatibility_path: Path,
                 asset_code: str, side: str, variant: int, family: str,
                 png_path: Path) \
        -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any]]:
    compatibility, _, compatibility_payload, target = select_target(
        asset_code, side, variant, family, compatibility_path)
    index, template_span, template_decoded, template_info = load_template(
        index_path, target)
    png, png_payload, rgba = read_png(png_path)
    mips = generate_mips(rgba)
    def candidate_decoded(
        candidate_palette: list[tuple[int, int, int, int]],
        candidate_levels: list[bytes],
    ) -> bytes:
        chain = b"".join(
            swizzle_2d(indices, level.width, level.height, 1)
            for indices, level in zip(candidate_levels, mips)
        )
        return (
            template_decoded[:128]
            + chain
            + palette_tools.palette_bytes(candidate_palette)
        )

    # A perfectly valid P8 helmet can be impossible to encode with a 256-entry
    # palette even though a visually equivalent lower-colour version fits the
    # retail span. The tier ladder starts at 256, so art that already fit is
    # byte-for-byte unchanged; only art that used to fail outright now steps
    # down instead of refusing.
    bounded = palette_tools.quantize_levels_to_vc_lz_bound(
        mips,
        candidate_decoded,
        stream_tag=target.stream_tag,
        offset_bits=target.offset_bits,
        max_encoded_size=target.stored_size,
    )
    palette = bounded.palette
    linear_levels = bounded.index_levels
    quantization = bounded.quantization
    require(len(linear_levels) == 6 and
            sum(len(value) for value in linear_levels) == INDEX_CHAIN_BYTES,
            "quantized mip index chain has the wrong size")
    quantized_levels = [
        palette_tools.MipLevel(
            source.level, source.width, source.height,
            palette_tools.rgba_from_indices(indices, palette),
        ) for source, indices in zip(mips, linear_levels)
    ]
    index_chain = b"".join(
        swizzle_2d(indices, level.width, level.height, 1)
        for indices, level in zip(linear_levels, mips)
    )
    palette_bgra = palette_tools.palette_bytes(palette)
    require(len(index_chain) == INDEX_CHAIN_BYTES and len(palette_bgra) == 1024,
            "encoded index/palette allocation changed")
    rebuilt_decoded = bounded.decoded
    require(rebuilt_decoded == template_decoded[:128] + index_chain + palette_bgra,
            "bounded quantizer decoded layout disagrees with the rebuilt chain")
    require(len(rebuilt_decoded) == target.decoded_size and
            rebuilt_decoded[:128] == template_decoded[:128],
            "rebuilt system/decoded allocation changed")
    validate_texture(rebuilt_decoded, target)

    compressed, compression_info = bounded.compressed, bounded.compression
    rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        template_span, rebuilt_decoded)
    require(rebuild_info.recompressed_bytes == len(compressed) and
            rebuilt_span[HEADER.size:HEADER.size + len(compressed)] == compressed and
            rebuild_info.zero_padding_bytes == target.stored_size - len(compressed) and
            rebuild_info.loader_in_place_end_guard and
            rebuild_info.loader_in_place_alias_guard and
            len(rebuilt_span) == target.span_size,
            "fixed-span compressor/rebuilder disagreement")
    rebuilt_header = HEADER.unpack_from(rebuilt_span)
    require(rebuilt_header[:5] == target.complete_header[:5] and
            rebuilt_header[6:] == target.complete_header[6:] and
            rebuilt_header[5] >= target.overlap_scratch_bytes,
            "rebuilt wrapper changed outside overlap scratch")
    roundtrip, roundtrip_info = decode_chunk(
        rebuilt_span, as_chunk(target, rebuilt_header[5]))
    require(roundtrip_info is not None and roundtrip == rebuilt_decoded and
            roundtrip_info.consumed_bytes == len(compressed),
            "rebuilt compressed span failed independent round trip")
    decoded_levels = decode_levels(roundtrip)
    require(decoded_levels == quantized_levels,
            "decoded mip levels differ from quantized PNG")
    runs = difference_runs(template_span, rebuilt_span)
    require(runs, "input PNG produced a byte-identical retail target")
    changed = sum(end - start + 1 for start, end in runs)
    require(all(start >= 0x14 for start, _ in runs),
            "rebuilt differences escaped scratch/stream body")

    previews: list[tuple[str, bytes]] = []
    preview_rows: list[dict[str, Any]] = []
    for level in decoded_levels:
        name = f"mip{level.level}_{level.width}x{level.height}.png"
        payload = encode_rgba_png(level.width, level.height, level.rgba)
        require(palette_tools.decode_rgba_png(
            payload, (level.width, level.height)) ==
            (level.width, level.height, level.rgba),
            f"generated preview failed strict reparse: {name}")
        previews.append((name, payload))
        preview_rows.append({
            "level": level.level, "width": level.width, "height": level.height,
            "rgba_sha256": digest(level.rgba), "file_name": name,
            "png_sha256": digest(payload), "strictly_reparsed": True,
        })

    target_record = asdict(target)
    target_record["outer_id"] = f"0x{target.outer_id:08x}"
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "canonical_index": {
            "path": str(index), "size": index.stat().st_size,
            "sha256": INDEX_SHA256,
        },
        "compatibility_report": {
            "path": str(compatibility), "sha256": digest(compatibility_payload),
        },
        "target": target_record,
        "input_png": {
            "path": str(png), "file_name": png.name,
            "size": len(png_payload), "sha256": digest(png_payload),
            "width": BASE_SIZE, "height": BASE_SIZE,
            "rgba_sha256": digest(rgba), "strict_rgba8_noninterlaced": True,
        },
        "template": {
            "span_size": len(template_span), "span_sha256": digest(template_span),
            "decoded_sha256": digest(template_decoded),
            "system_sha256": digest(template_decoded[:128]),
            "stream_tag": template_info.stream_tag,
            "offset_bits": template_info.offset_bits,
            "lz_consumed_bytes": template_info.consumed_bytes,
            "lz_unused_bytes": target.stored_size - template_info.consumed_bytes,
            "overlap_scratch_bytes": target.overlap_scratch_bytes,
            "retail_exact_minimum_overlap_scratch_bytes":
                target.retail_exact_minimum_overlap_scratch_bytes,
        },
        "mips": {
            "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
            "level_count": 6,
            "dimensions": [list(value) for value in MIP_DIMENSIONS],
            "linear_index_bytes": [len(value) for value in linear_levels],
            "index_chain_bytes": len(index_chain),
            "each_level_swizzled_independently": True,
        },
        "quantization": {
            "algorithm": "weighted_median_cut_rgba_then_nearest_squared_error",
            # The bounded ladder can quantize a replacement down to fit its
            # fixed VC-LZ span. That is lossy, so it is recorded here and
            # reported to the user rather than applied silently.
            "palette_fit_attempts": list(bounded.attempts),
            "palette_was_reduced": len(bounded.attempts) > 1,
            **quantization, "palette_entries": len(palette),
            "unused_palette_entries_zero_filled": True,
        },
        "compression": asdict(compression_info),
        "rebuild": {
            **asdict(rebuild_info),
            "span_size": len(rebuilt_span), "span_sha256": digest(rebuilt_span),
            "decoded_roundtrip_sha256": digest(roundtrip),
            "index_chain_sha256": digest(index_chain),
            "palette_bgra_sha256": digest(palette_bgra),
            "changed_byte_count": changed,
            "changed_run_count": len(runs), "changed_runs": runs,
            "fixed_span_fit": len(compressed) <= target.stored_size,
            "zero_padding_verified": rebuilt_span[
                HEADER.size + len(compressed):] ==
                bytes(target.stored_size - len(compressed)),
            "system_bytes_preserved": roundtrip[:128] == template_decoded[:128],
            "wrapper_preserved_except_overlap_scratch": True,
        },
        "previews": preview_rows,
        "claims": {
            "actual_live_3d_helmet_resource": True,
            "standalone_team_select_helm_card_modified": False,
            "fixed_span_only": True,
            "loader_in_place_decode_guarded": True,
            "all_six_mips_generated_swizzled_and_verified": True,
            "originals_modified": False,
            "xiso_created": False,
            "xemu_started": False,
            "title_executed": False,
            "runtime_visibility_proved": False,
            "portme": "PORTME: runtime visibility remains a separate proof.",
        },
    }
    return rebuilt_span, previews, report


def create_file(path: Path, payload: bytes) -> tuple[int, int]:
    descriptor = os.open(
        path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0), 0o644)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    success = False
    try:
        offset = 0
        while offset < len(payload):
            amount = os.write(descriptor, payload[offset:])
            require(amount > 0, f"short output write at {offset}")
            offset += amount
        os.fsync(descriptor)
        info = path.stat(follow_symlinks=False)
        require((info.st_dev, info.st_ino, info.st_size) ==
                (identity[0], identity[1], len(payload)),
                "output pathname/size changed")
        success = True
        return identity
    finally:
        os.close(descriptor)
        if not success:
            try:
                current = path.stat(follow_symlinks=False)
                if (current.st_dev, current.st_ino) == identity:
                    path.unlink()
            except FileNotFoundError:
                pass


def write_outputs(output_dir: Path, span: bytes,
                  previews: list[tuple[str, bytes]], report: dict[str, Any]) -> None:
    parent = output_dir.parent.resolve(strict=True)
    target = parent / output_dir.name
    require(not target.exists() and not target.is_symlink(),
            "output directory already exists")
    os.mkdir(target, 0o755)
    success = False
    try:
        preview_dir = target / "previews"
        os.mkdir(preview_dir, 0o755)
        create_file(target / "replacement.txtr.bin", span)
        for name, payload in previews:
            require(Path(name).name == name, "unsafe preview filename")
            create_file(preview_dir / name, payload)
        create_file(target / "import.json", canonical_json(report))
        success = True
    finally:
        if not success:
            for child in (target / "previews").glob("*") if (target / "previews").exists() else []:
                child.unlink()
            for child in (target / "replacement.txtr.bin", target / "import.json"):
                try:
                    child.unlink()
                except FileNotFoundError:
                    pass
            try:
                (target / "previews").rmdir()
            except FileNotFoundError:
                pass
            target.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-code", required=True)
    parser.add_argument("--target-side", required=True)
    parser.add_argument("--target-variant", required=True, type=int)
    parser.add_argument("--family", required=True, choices=("helmet00", "helmet02"))
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        span, previews, report = build_import(
            args.index, args.compatibility, args.target_code, args.target_side,
            args.target_variant, args.family, args.png)
        write_outputs(args.output_dir, span, previews, report)
        print(
            "NFL_LIVE_HELMET_TXTR_PNG_IMPORT_OK "
            f"target={report['target']['logical_name']}:{report['target']['family']} "
            f"encoded={report['rebuild']['recompressed_bytes']} "
            f"stored={report['target']['stored_size']} "
            f"zero_pad={report['rebuild']['zero_padding_bytes']} "
            "mips=6 runtime=false xemu_started=false"
        )
        return 0
    except (ImportError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
