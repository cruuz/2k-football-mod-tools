#!/usr/bin/env python3
"""Import one RGBA PNG into NFL 2K5 Lions 09H0 jersey TSET chunk 1.

This deliberately bounded importer supports the exact two-reference layout
proved for ``jersey00``/``jersey00_mud``: six contiguous Xbox P8 mip levels
share one index chain and use two 256-entry BGRA palettes.  It writes only a
new 74,720-byte TSET span, validation PNGs, and a manifest.  It never edits an
archive or creates an XISO.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import zlib

from nfl_outer import parse_archive
from nfl_txtr import (
    HEADER,
    TxtrError,
    compress_vc_lz,
    decode_chunk,
    encode_rgba_png,
    rebuild_compressed_chunk_fixed_span,
    swizzle_2d,
    unswizzle_2d,
)
from nfl_uniform_inventory import (
    inventory_record,
    logical_name_candidates,
    parse_tset,
    read_and_validate_span,
)


SCHEMA = "nfl2k5_tset_png_import/v2"
INVENTORY_SCHEMA = "nfl2k5_resource_chunk_inventory/v1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 32 * 1024 * 1024
TARGET_OUTER = 3685
TARGET_CHUNK = 1
TARGET_ID = 0x9A4832D6
TARGET_NAME = "09H0.IFF"
TARGET_PACK_OFFSET = 0x055CA800
TARGET_SPAN_SHA256 = "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862"
TARGET_DECODED_SHA256 = "92a7e5ed6b8d0b468c4782509cf6335f88dfa06e189d7b624f80600ce727aa1e"
BASE_WIDTH = 512
BASE_HEIGHT = 256
MIP_LEVELS = 6
MIP_DIMENSIONS = tuple(
    (BASE_WIDTH >> level, BASE_HEIGHT >> level) for level in range(MIP_LEVELS)
)
INDEX_CHAIN_BYTES = sum(width * height for width, height in MIP_DIMENSIONS)
CLEAN_PALETTE_OFFSET = INDEX_CHAIN_BYTES
MUD_PALETTE_OFFSET = CLEAN_PALETTE_OFFSET + 1024
VIDEO_BYTES = MUD_PALETTE_OFFSET + 1024


class ImportError(ValueError):
    """Raised when a PNG, shared-index layout, or fixed span fails closed."""


@dataclass(frozen=True)
class MipLevel:
    level: int
    width: int
    height: int
    rgba: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImportError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def decode_rgba_png(
    payload: bytes,
    expected_dimensions: tuple[int, int] | None = (BASE_WIDTH, BASE_HEIGHT),
) -> tuple[int, int, bytes]:
    """Strict bounded decoder for non-interlaced 8-bit RGBA PNG."""

    require(len(payload) <= MAX_PNG_BYTES, "PNG exceeds the 32 MiB input bound")
    require(payload.startswith(PNG_SIGNATURE), "PNG signature mismatch")
    offset = len(PNG_SIGNATURE)
    ihdr: tuple[int, int, int, int, int, int, int] | None = None
    idat = bytearray()
    saw_iend = False
    saw_idat = False
    idat_closed = False
    while offset < len(payload):
        require(offset + 12 <= len(payload), "truncated PNG chunk header")
        length = struct.unpack_from(">I", payload, offset)[0]
        kind = payload[offset + 4:offset + 8]
        end = offset + 12 + length
        require(end <= len(payload), "PNG chunk exceeds input")
        data = payload[offset + 8:offset + 8 + length]
        stored_crc = struct.unpack_from(">I", payload, offset + 8 + length)[0]
        require(zlib.crc32(kind + data) & 0xFFFFFFFF == stored_crc,
                f"PNG {kind!r} CRC mismatch")
        if kind == b"IHDR":
            require(ihdr is None and offset == len(PNG_SIGNATURE) and length == 13,
                    "PNG IHDR placement/size mismatch")
            ihdr = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            require(ihdr is not None and not idat_closed,
                    "PNG IDAT placement mismatch")
            idat.extend(data)
            saw_idat = True
        elif kind == b"IEND":
            require(length == 0 and saw_idat, "PNG IEND placement/size mismatch")
            saw_iend = True
            offset = end
            break
        else:
            if saw_idat:
                idat_closed = True
            # Unknown critical chunks have an uppercase first byte.
            require(not (kind and 65 <= kind[0] <= 90),
                    f"unsupported critical PNG chunk {kind!r}")
        offset = end
    require(ihdr is not None and saw_iend and offset == len(payload),
            "PNG is missing IHDR/IEND or has trailing bytes")
    width, height, bit_depth, color_type, compression, filtering, interlace = ihdr
    if expected_dimensions is not None:
        require((width, height) == expected_dimensions,
                f"PNG must be exactly {expected_dimensions[0]}x{expected_dimensions[1]}")
    require((bit_depth, color_type, compression, filtering, interlace) ==
            (8, 6, 0, 0, 0),
            "PNG must be non-interlaced RGBA8 with standard compression/filtering")
    row_bytes = width * 4
    expected = (row_bytes + 1) * height
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(bytes(idat), expected + 1)
    require(len(raw) <= expected and not decompressor.unconsumed_tail,
            "PNG inflated data exceeds expected RGBA scanlines")
    raw += decompressor.flush()
    require(decompressor.eof and not decompressor.unused_data and len(raw) == expected,
            "PNG IDAT stream is truncated, trailing, or wrong-sized")

    rgba = bytearray(width * height * 4)
    previous = bytearray(row_bytes)
    for y in range(height):
        row_start = y * (row_bytes + 1)
        filter_type = raw[row_start]
        require(filter_type <= 4, f"unsupported PNG filter {filter_type}")
        encoded = raw[row_start + 1:row_start + 1 + row_bytes]
        row = bytearray(row_bytes)
        for x, value in enumerate(encoded):
            left = row[x - 4] if x >= 4 else 0
            up = previous[x]
            upper_left = previous[x - 4] if x >= 4 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            else:
                estimate = left + up - upper_left
                left_distance = abs(estimate - left)
                up_distance = abs(estimate - up)
                diagonal_distance = abs(estimate - upper_left)
                predictor = (
                    left if left_distance <= up_distance and left_distance <= diagonal_distance
                    else up if up_distance <= diagonal_distance
                    else upper_left
                )
            row[x] = (value + predictor) & 0xFF
        rgba[y * row_bytes:(y + 1) * row_bytes] = row
        previous = row
    return width, height, bytes(rgba)


def read_rgba_png(path: Path) -> tuple[int, int, bytes, str]:
    require(path.exists() and not path.is_symlink(),
            f"PNG must be a non-symlink file: {path}")
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), f"PNG is not a regular file: {path}")
    require(info.st_size <= MAX_PNG_BYTES, "PNG exceeds the 32 MiB file bound")
    payload = path.read_bytes()
    width, height, rgba = decode_rgba_png(payload)
    return width, height, rgba, sha256_bytes(payload)


def generate_mips(rgba: bytes, width: int, height: int,
                  levels: int = MIP_LEVELS) -> list[MipLevel]:
    require(len(rgba) == width * height * 4, "base RGBA size mismatch")
    result = [MipLevel(0, width, height, rgba)]
    current = rgba
    current_width = width
    current_height = height
    for level in range(1, levels):
        require(current_width % 2 == 0 and current_height % 2 == 0,
                "mip dimensions cannot be halved exactly")
        next_width = current_width // 2
        next_height = current_height // 2
        downsampled = bytearray(next_width * next_height * 4)
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
                    total = sum(current[source + channel] for source in sources)
                    downsampled[target + channel] = (total + 2) // 4
        current = bytes(downsampled)
        current_width = next_width
        current_height = next_height
        result.append(MipLevel(level, current_width, current_height, current))
    require(tuple((item.width, item.height) for item in result) == MIP_DIMENSIONS,
            "generated mip dimensions differ from the pinned chain")
    return result


def rgba_tuples(rgba: bytes) -> list[tuple[int, int, int, int]]:
    require(len(rgba) % 4 == 0, "RGBA byte stream is unaligned")
    return [tuple(rgba[offset:offset + 4]) for offset in range(0, len(rgba), 4)]  # type: ignore[misc]


def median_cut_palette(histogram: Counter[tuple[int, int, int, int]],
                       maximum: int = 256) -> list[tuple[int, int, int, int]]:
    require(histogram and maximum > 0, "quantizer input/maximum is invalid")
    colors = sorted(histogram)
    if len(colors) <= maximum:
        return colors
    boxes: list[list[tuple[int, int, int, int]]] = [colors]
    while len(boxes) < maximum:
        candidates: list[tuple[tuple[int, int, int, int], int, int]] = []
        for box_index, box in enumerate(boxes):
            if len(box) < 2:
                continue
            ranges = tuple(max(color[channel] for color in box) -
                           min(color[channel] for color in box)
                           for channel in range(4))
            channel = max(range(4), key=lambda item: (ranges[item], -item))
            population = sum(histogram[color] for color in box)
            candidates.append(((max(ranges), population, len(box), -box_index),
                               box_index, channel))
        if not candidates:
            break
        _, box_index, channel = max(candidates)
        box = sorted(boxes[box_index], key=lambda color: (color[channel], color))
        population = sum(histogram[color] for color in box)
        target = (population + 1) // 2
        accumulated = 0
        split = len(box) - 1
        for color_index, color in enumerate(box[:-1], start=1):
            accumulated += histogram[color]
            if accumulated >= target:
                split = color_index
                break
        boxes[box_index:box_index + 1] = [box[:split], box[split:]]

    representatives: list[tuple[int, int, int, int]] = []
    for box in boxes:
        population = sum(histogram[color] for color in box)
        representative = tuple(
            (sum(color[channel] * histogram[color] for color in box) + population // 2)
            // population
            for channel in range(4)
        )
        representatives.append(representative)  # type: ignore[arg-type]
    palette = sorted(set(representatives))
    require(len(palette) <= maximum, "quantizer produced too many palette entries")
    return palette


def quantize_levels(levels: list[MipLevel]) -> tuple[
    list[tuple[int, int, int, int]], list[bytes], dict[str, int]
]:
    histogram: Counter[tuple[int, int, int, int]] = Counter()
    level_colors: list[list[tuple[int, int, int, int]]] = []
    for level in levels:
        colors = rgba_tuples(level.rgba)
        level_colors.append(colors)
        histogram.update(colors)
    palette = median_cut_palette(histogram, 256)
    color_to_index: dict[tuple[int, int, int, int], int] = {}
    total_squared_error = 0
    maximum_channel_error = 0
    differing_pixels = 0
    for color in sorted(histogram):
        best_index = min(
            range(len(palette)),
            key=lambda index: (
                sum((color[channel] - palette[index][channel]) ** 2
                    for channel in range(4)),
                index,
            ),
        )
        color_to_index[color] = best_index
        mapped = palette[best_index]
        error = sum((color[channel] - mapped[channel]) ** 2 for channel in range(4))
        total_squared_error += error * histogram[color]
        maximum_channel_error = max(
            maximum_channel_error,
            *(abs(color[channel] - mapped[channel]) for channel in range(4)),
        )
        if color != mapped:
            differing_pixels += histogram[color]
    indices = [bytes(color_to_index[color] for color in colors) for colors in level_colors]
    return palette, indices, {
        "input_unique_rgba_colors": len(histogram),
        "palette_entries": len(palette),
        "total_squared_rgba_error": total_squared_error,
        "maximum_channel_error": maximum_channel_error,
        "differing_pixel_count": differing_pixels,
        "total_pixel_count": sum(histogram.values()),
    }


def palette_bytes(palette: list[tuple[int, int, int, int]]) -> bytes:
    require(len(palette) <= 256, "palette exceeds 256 entries")
    result = bytearray(1024)
    for index, (red, green, blue, alpha) in enumerate(palette):
        result[index * 4:index * 4 + 4] = bytes((blue, green, red, alpha))
    return bytes(result)


def rgba_from_indices(indices: bytes,
                      palette: list[tuple[int, int, int, int]]) -> bytes:
    require(all(index < len(palette) for index in indices),
            "index references an absent palette entry")
    return b"".join(bytes(palette[index]) for index in indices)


def derive_mud_palette(clean: list[tuple[int, int, int, int]], mode: str) \
        -> list[tuple[int, int, int, int]]:
    if mode == "identity":
        return list(clean)
    if mode == "darken_60":
        return [
            ((red * 3 + 2) // 5, (green * 3 + 2) // 5,
             (blue * 3 + 2) // 5, alpha)
            for red, green, blue, alpha in clean
        ]
    raise ImportError(f"unsupported mud palette mode {mode}")


def palette_for_shared_mud(indices: list[bytes], mud_levels: list[MipLevel]) \
        -> list[tuple[int, int, int, int]]:
    assignments: list[tuple[int, int, int, int] | None] = [None] * 256
    for index_bytes, level in zip(indices, mud_levels):
        colors = rgba_tuples(level.rgba)
        require(len(index_bytes) == len(colors), "mud/index level size mismatch")
        for palette_index, color in zip(index_bytes, colors):
            previous = assignments[palette_index]
            if previous is None:
                assignments[palette_index] = color
            elif previous != color:
                raise ImportError(
                    "clean and mud PNGs cannot share one exact P8 index chain: "
                    f"index {palette_index} maps to both {previous} and {color}"
                )
    return [value if value is not None else (0, 0, 0, 0) for value in assignments]


def parse_palette(video: bytes, offset: int) -> list[tuple[int, int, int, int]]:
    require(offset + 1024 <= len(video), "palette exceeds video buffer")
    result = []
    for index in range(256):
        blue, green, red, alpha = video[offset + index * 4:offset + index * 4 + 4]
        result.append((red, green, blue, alpha))
    return result


def decode_tset_levels(decoded: bytes) -> tuple[list[MipLevel], list[MipLevel]]:
    require(len(decoded) == 256 + VIDEO_BYTES, "decoded TSET size mismatch")
    video = decoded[256:]
    clean_palette = parse_palette(video, CLEAN_PALETTE_OFFSET)
    mud_palette = parse_palette(video, MUD_PALETTE_OFFSET)
    clean: list[MipLevel] = []
    mud: list[MipLevel] = []
    offset = 0
    for level, (width, height) in enumerate(MIP_DIMENSIONS):
        size = width * height
        swizzled = video[offset:offset + size]
        require(len(swizzled) == size, f"mip {level} index data truncated")
        indices = unswizzle_2d(swizzled, width, height, 1)
        clean.append(MipLevel(level, width, height,
                              rgba_from_indices(indices, clean_palette)))
        mud.append(MipLevel(level, width, height,
                            rgba_from_indices(indices, mud_palette)))
        offset += size
    require(offset == CLEAN_PALETTE_OFFSET, "mip chain does not end at clean palette")
    return clean, mud


def descriptor_projection(references: list[dict[str, object]]) -> list[dict[str, object]]:
    fields = (
        "tset_chunk_index", "reference_index", "record_offset", "name",
        "name_offset", "descriptor_offset", "root_offset", "unknown0",
        "pixel_offset", "palette_offset", "packed_format", "packed_size",
        "descriptor_flags", "dimensions", "format_code", "format_name",
        "mip_levels", "width", "height", "depth",
    )
    return [{field: reference[field] for field in fields} for reference in references]


def exclusive_write(path: Path, payload: bytes) -> tuple[int, int]:
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    descriptor = os.open(
        target,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o644,
    )
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    success = False
    try:
        position = 0
        while position < len(payload):
            written = os.write(descriptor, payload[position:])
            require(written > 0, f"short output write at 0x{position:x}")
            position += written
        os.fsync(descriptor)
        require(os.fstat(descriptor).st_size == len(payload), "output size mismatch")
        current = target.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino) == identity,
                "output pathname identity changed")
        success = True
        return identity
    finally:
        os.close(descriptor)
        if not success:
            try:
                current = target.stat(follow_symlinks=False)
                if (current.st_dev, current.st_ino) == identity:
                    target.unlink()
            except FileNotFoundError:
                pass


def import_png(index: Path, inventory_path: Path, clean_png: Path,
               mud_png: Path | None, mud_mode: str) \
        -> tuple[bytes, list[tuple[str, bytes]], dict[str, object]]:
    require(INDEX_CHAIN_BYTES == 174720 and VIDEO_BYTES == 176768,
            "pinned mip/palette layout arithmetic mismatch")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    require(inventory.get("schema") == INVENTORY_SCHEMA, "inventory schema mismatch")
    item = next(
        (row for row in inventory["chunks"]
         if int(row["outer_index"]) == TARGET_OUTER and
         int(row["chunk_index"]) == TARGET_CHUNK),
        None,
    )
    require(item is not None, "target TSET inventory row absent")
    assert item is not None
    archive = parse_archive(index)
    entry = archive.entries[TARGET_OUTER]
    require(entry.name_id == TARGET_ID and len(entry.segments) == 1 and
            entry.segments[0].pack_name == "A" and
            entry.segments[0].pack_offset == TARGET_PACK_OFFSET,
            "target outer identity/pack mapping mismatch")
    logical = logical_name_candidates().get(entry.name_id)
    require(logical is not None and logical.name == TARGET_NAME,
            "target logical name mismatch")
    assert logical is not None
    record, template_span, template_decoded, template_info = read_and_validate_span(
        archive, item
    )
    require(template_info is not None and record.stored_size == 74688 and
            len(template_span) == 74720,
            "target compressed span mismatch")
    require(sha256_bytes(template_span) == TARGET_SPAN_SHA256 and
            sha256_bytes(template_decoded) == TARGET_DECODED_SHA256,
            "target source hash mismatch")
    _, template_refs, _ = parse_tset(template_decoded, record, logical, None)
    require([ref["name"] for ref in template_refs] == ["jersey00", "jersey00_mud"],
            "target embedded texture names mismatch")
    require([ref["pixel_offset"] for ref in template_refs] == [0, 0] and
            [ref["palette_offset"] for ref in template_refs] ==
            [CLEAN_PALETTE_OFFSET, MUD_PALETTE_OFFSET] and
            all(ref["packed_format"] == "0x08960b29" for ref in template_refs),
            "target shared-index descriptors mismatch")

    clean_width, clean_height, clean_rgba, clean_png_sha = read_rgba_png(clean_png)
    clean_mips = generate_mips(clean_rgba, clean_width, clean_height)
    clean_palette, index_levels, quantization = quantize_levels(clean_mips)
    clean_quantized = [
        MipLevel(level.level, level.width, level.height,
                 rgba_from_indices(indices, clean_palette))
        for level, indices in zip(clean_mips, index_levels)
    ]

    if mud_png is not None:
        require(mud_mode == "identity",
                "--mud-png cannot be combined with a derived non-identity mud mode")
        mud_width, mud_height, mud_rgba, mud_png_sha = read_rgba_png(mud_png)
        mud_mips = generate_mips(mud_rgba, mud_width, mud_height)
        mud_palette_full = palette_for_shared_mud(index_levels, mud_mips)
        # Trim only trailing unused entries while retaining assigned indices.
        highest_used = max(index for level in index_levels for index in level)
        mud_palette = mud_palette_full[:highest_used + 1]
        mud_expected = mud_mips
        mud_source = {
            "kind": "second_png_exact_shared_indices",
            "file_name": mud_png.name,
            "sha256": mud_png_sha,
        }
    else:
        mud_palette = derive_mud_palette(clean_palette, mud_mode)
        mud_expected = [
            MipLevel(level.level, level.width, level.height,
                     rgba_from_indices(indices, mud_palette))
            for level, indices in zip(clean_mips, index_levels)
        ]
        mud_source = {"kind": "derived_palette", "mode": mud_mode}

    index_chain = b"".join(
        swizzle_2d(indices, level.width, level.height, 1)
        for level, indices in zip(clean_mips, index_levels)
    )
    require(len(index_chain) == INDEX_CHAIN_BYTES,
            "encoded mip index chain size mismatch")
    rebuilt_decoded = bytearray(template_decoded)
    rebuilt_decoded[256:256 + INDEX_CHAIN_BYTES] = index_chain
    rebuilt_decoded[256 + CLEAN_PALETTE_OFFSET:256 + CLEAN_PALETTE_OFFSET + 1024] = \
        palette_bytes(clean_palette)
    rebuilt_decoded[256 + MUD_PALETTE_OFFSET:256 + MUD_PALETTE_OFFSET + 1024] = \
        palette_bytes(mud_palette)
    rebuilt_decoded_bytes = bytes(rebuilt_decoded)
    _, rebuilt_refs, _ = parse_tset(rebuilt_decoded_bytes, record, logical, None)
    template_descriptors = descriptor_projection(template_refs)
    rebuilt_descriptors = descriptor_projection(rebuilt_refs)
    require(rebuilt_descriptors == template_descriptors,
            "texture descriptors/names changed during video-only rebuild")

    stream_tag = int.from_bytes(template_span[HEADER.size + 4:HEADER.size + 8], "little")
    offset_bits = template_span[HEADER.size + 8]
    compressed, compression_info = compress_vc_lz(
        rebuilt_decoded_bytes,
        stream_tag=stream_tag,
        offset_bits=offset_bits,
        max_encoded_size=record.stored_size,
    )
    rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        template_span, rebuilt_decoded_bytes
    )
    require(rebuild_info.recompressed_bytes == len(compressed) and
            rebuilt_span[HEADER.size:HEADER.size + len(compressed)] == compressed and
            rebuild_info.zero_padding_bytes == record.stored_size - len(compressed) and
            rebuild_info.loader_in_place_end_guard and
            rebuild_info.loader_in_place_alias_guard,
            "fixed-span compressor/rebuilder disagreement")
    decoded_roundtrip, roundtrip_info = decode_chunk(rebuilt_span, record.as_chunk())
    require(roundtrip_info is not None and decoded_roundtrip == rebuilt_decoded_bytes and
            roundtrip_info.consumed_bytes == len(compressed),
            "rebuilt span compressed decode mismatch")
    decoded_clean, decoded_mud = decode_tset_levels(decoded_roundtrip)
    require(decoded_clean == clean_quantized,
            "decoded clean mip chain differs from quantized input")
    require(decoded_mud == mud_expected,
            "decoded mud mip chain differs from requested/derived input")

    previews: list[tuple[str, bytes]] = []
    preview_rows: list[dict[str, object]] = []
    for role, levels in (("clean", decoded_clean), ("mud", decoded_mud)):
        for level in levels:
            name = f"{role}_mip{level.level}_{level.width}x{level.height}.png"
            payload = encode_rgba_png(level.width, level.height, level.rgba)
            parsed_width, parsed_height, parsed_rgba = decode_rgba_png(
                payload, (level.width, level.height)
            )
            require((parsed_width, parsed_height, parsed_rgba) ==
                    (level.width, level.height, level.rgba),
                    f"generated preview PNG failed strict reparse: {name}")
            previews.append((name, payload))
            preview_rows.append({
                "role": role,
                "level": level.level,
                "width": level.width,
                "height": level.height,
                "rgba_sha256": sha256_bytes(level.rgba),
                "png_file": name,
                "png_sha256": sha256_bytes(payload),
                "strictly_reparsed": True,
            })

    report: dict[str, object] = {
        "schema": SCHEMA,
        "source_index": str(index),
        "canonical_inventory": str(inventory_path),
        "target": {
            "logical_name": TARGET_NAME,
            "outer_index": TARGET_OUTER,
            "outer_id": f"0x{TARGET_ID:08x}",
            "chunk_index": TARGET_CHUNK,
            "chunk_offset": record.chunk_offset,
            "stored_size": record.stored_size,
            "complete_span_size": len(template_span),
            "template_overlap_scratch_bytes": record.word_14,
            "rebuilt_overlap_scratch_bytes":
                rebuild_info.rebuilt_overlap_scratch_bytes,
            "template_span_sha256": sha256_bytes(template_span),
            "template_decoded_sha256": sha256_bytes(template_decoded),
            "system_bytes_preserved": rebuilt_decoded_bytes[:256] == template_decoded[:256],
            "descriptor_records_preserved": rebuilt_descriptors == template_descriptors,
        },
        "input": {
            "clean": {
                "file_name": clean_png.name,
                "sha256": clean_png_sha,
                "width": clean_width,
                "height": clean_height,
                "format": "RGBA8_noninterlaced",
            },
            "mud": mud_source,
        },
        "mips": {
            "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
            "level_count": MIP_LEVELS,
            "dimensions": [list(item) for item in MIP_DIMENSIONS],
            "linear_index_bytes_by_level": [width * height for width, height in MIP_DIMENSIONS],
            "total_index_chain_bytes": len(index_chain),
            "each_level_swizzled_independently": True,
        },
        "quantization": {
            "algorithm": "weighted_median_cut_rgba_then_nearest_rgba_squared_error",
            "tie_breaks": "channel R,G,B,A; stable lexical colors; lowest palette index",
            **quantization,
            "clean_palette_entries": len(clean_palette),
            "mud_palette_entries": len(mud_palette),
            "shared_index_chain": True,
        },
        "layout": {
            "index_offset": 0,
            "clean_palette_offset": CLEAN_PALETTE_OFFSET,
            "mud_palette_offset": MUD_PALETTE_OFFSET,
            "palette_bytes_each": 1024,
            "video_bytes": VIDEO_BYTES,
            "unused_palette_entries_zero_filled": True,
        },
        "compression": asdict(compression_info),
        "rebuild": {
            **asdict(rebuild_info),
            "decoded_roundtrip_sha256": sha256_bytes(decoded_roundtrip),
            "complete_span_sha256": sha256_bytes(rebuilt_span),
            "complete_span_size": len(rebuilt_span),
            "fixed_span_fit": len(compressed) <= record.stored_size,
            "zero_padding_verified": rebuilt_span[HEADER.size + len(compressed):] ==
            bytes(record.stored_size - len(compressed)),
        },
        "previews": preview_rows,
        "claims": {
            "real_png_input_consumed": True,
            "all_clean_and_mud_mips_generated": True,
            "all_mips_swizzled_and_decoded": True,
            "all_preview_pngs_strictly_reparsed": True,
            "two_reference_shared_index_layout_preserved": True,
            "target_wrapper_preserved_except_loader_overlap_scratch": True,
            "loader_in_place_decode_guarded": True,
            "fixed_span_only": True,
            "output_exclusively_created": True,
            "originals_modified": False,
            "xiso_created": False,
            "title_executed": False,
            "runtime_visibility_proved": False,
            "general_tset_layout_support": False,
            "portme": (
                "PORTME: validate this span in a copied archive/XISO and runtime only "
                "after the offline artifact and manifest are frozen."
            ),
        },
    }
    return rebuilt_span, previews, report


def run(index: Path, inventory: Path, clean_png: Path, mud_png: Path | None,
        mud_mode: str, output_span: Path, output_manifest: Path,
        preview_dir: Path) -> dict[str, object]:
    output_parent = output_span.parent.resolve(strict=True)
    manifest_parent = output_manifest.parent.resolve(strict=True)
    preview_parent = preview_dir.parent.resolve(strict=True)
    output_span = output_parent / output_span.name
    output_manifest = manifest_parent / output_manifest.name
    preview_dir = preview_parent / preview_dir.name
    require(output_span != output_manifest, "output span and manifest paths collide")
    require(not output_span.exists() and not output_manifest.exists() and
            not preview_dir.exists(),
            "output span, manifest, or preview directory already exists")
    rebuilt_span, previews, report = import_png(
        index, inventory, clean_png, mud_png, mud_mode
    )
    created_files: list[tuple[Path, tuple[int, int]]] = []
    preview_identity: tuple[int, int] | None = None
    success = False
    try:
        os.mkdir(preview_dir, 0o755)
        preview_stat = preview_dir.stat(follow_symlinks=False)
        preview_identity = (preview_stat.st_dev, preview_stat.st_ino)
        for name, payload in previews:
            path = preview_dir / name
            identity = exclusive_write(path, payload)
            created_files.append((path, identity))
            width, height, rgba = decode_rgba_png(path.read_bytes(), None)
            require(width * height * 4 == len(rgba),
                    f"written preview PNG failed reparse: {name}")
        span_identity = exclusive_write(output_span, rebuilt_span)
        created_files.append((output_span, span_identity))
        report["outputs"] = {
            "span_file": output_span.name,
            "manifest_file": output_manifest.name,
            "preview_directory": preview_dir.name,
            "preview_file_count": len(previews),
        }
        manifest_payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        manifest_identity = exclusive_write(output_manifest, manifest_payload)
        created_files.append((output_manifest, manifest_identity))
        written_span = output_span.read_bytes()
        require(written_span == rebuilt_span,
                "written span readback differs")
        written_record_fields = HEADER.unpack_from(written_span)
        require(written_record_fields[0] == b"TSET" and
                written_record_fields[1] == len(written_span) - HEADER.size,
                "written span wrapper readback mismatch")
        # Decode and traverse the on-disk copy again, not only the in-memory
        # bytes used before O_EXCL creation.
        inventory_value = json.loads(inventory.read_text(encoding="utf-8"))
        disk_item = next(
            row for row in inventory_value["chunks"]
            if int(row["outer_index"]) == TARGET_OUTER and
            int(row["chunk_index"]) == TARGET_CHUNK
        )
        disk_record = inventory_record(disk_item)
        disk_decoded, disk_decode_info = decode_chunk(written_span, disk_record.as_chunk())
        require(disk_decode_info is not None and
                sha256_bytes(disk_decoded) == report["rebuild"]["decoded_sha256"],
                "written span decoded readback mismatch")
        disk_clean, disk_mud = decode_tset_levels(disk_decoded)
        require(len(disk_clean) == len(disk_mud) == MIP_LEVELS,
                "written span mip traversal mismatch")
        disk_rows = {
            (role, level.level): sha256_bytes(level.rgba)
            for role, levels in (("clean", disk_clean), ("mud", disk_mud))
            for level in levels
        }
        manifest_rows = {
            (str(row["role"]), int(row["level"])): str(row["rgba_sha256"])
            for row in report["previews"]
        }
        require(disk_rows == manifest_rows,
                "written span decoded mip hashes differ from manifest")
        require(json.loads(output_manifest.read_bytes()) == report,
                "written manifest readback differs")
        success = True
        return report
    finally:
        if not success:
            for path, identity in reversed(created_files):
                try:
                    current = path.stat(follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == identity:
                        path.unlink()
                except FileNotFoundError:
                    pass
            if preview_identity is not None:
                try:
                    current = preview_dir.stat(follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == preview_identity:
                        preview_dir.rmdir()
                except FileNotFoundError:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--mud-png", type=Path)
    parser.add_argument("--mud-mode", choices=("identity", "darken_60"),
                        default="identity")
    parser.add_argument("--output-span", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(
            args.index, args.inventory, args.clean_png, args.mud_png,
            args.mud_mode, args.output_span, args.manifest, args.preview_dir,
        )
    except (OSError, TxtrError, ImportError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_TSET_PNG_IMPORT_OK "
        f"target=09H0 chunk=1 colors={result['quantization']['clean_palette_entries']} "
        f"encoded={result['compression']['encoded_bytes']}/74688 "
        f"zero_pad={result['rebuild']['zero_padding_bytes']} mips=6 previews=12 "
        "shared_indices=true xiso=false runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
