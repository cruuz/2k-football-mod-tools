#!/usr/bin/env python3
"""Independently verify the pinned 09H0 diagnostic PNG-import TSET span."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import zlib

from nfl_outer import parse_archive
from nfl_tset_fixed_span_verify import independent_decode


SCHEMA = "nfl2k5_tset_png_import/v1"
OUTER_INDEX = 3685
OUTER_ID = 0x9A4832D6
OUTER_PACK_OFFSET = 0x055CA800
CHUNK_OFFSET = 0x70
SPAN_SIZE = 74720
STORED_SIZE = 74688
SOURCE_SPAN_SHA256 = "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862"
OUTPUT_SPAN_SHA256 = "76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8"
OUTPUT_DECODED_SHA256 = "f5ed9101fa5c8bb742168b18fac698f57185c6b6a0190545ecafc1bb1b99c30e"
INPUT_PNG_SHA256 = "6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8"
MANIFEST_SHA256 = "3500f6e6a3fddc4680a43214dd8f283bb8d1a13b355dcb2e8bbb349417613d80"
MIP_DIMENSIONS = ((512, 256), (256, 128), (128, 64),
                  (64, 32), (32, 16), (16, 8))
INDEX_CHAIN_BYTES = 174720
CLEAN_PALETTE_OFFSET = 174720
MUD_PALETTE_OFFSET = 175744
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
HEADER = struct.Struct("<4s7I")


class VerifyError(ValueError):
    """Raised when the independent artifact proof fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_retail_span(index: Path) -> bytes:
    archive = parse_archive(index)
    entry = archive.entries[OUTER_INDEX]
    require(entry.name_id == OUTER_ID and len(entry.segments) == 1,
            "retail target outer mismatch")
    segment = entry.segments[0]
    require(segment.pack_name == "A" and segment.pack_offset == OUTER_PACK_OFFSET,
            "retail target pack mapping mismatch")
    with archive.packs[segment.pack_ordinal].path.open("rb") as stream:
        stream.seek(segment.pack_offset + CHUNK_OFFSET)
        value = stream.read(SPAN_SIZE)
    require(len(value) == SPAN_SIZE, "retail target span truncated")
    return value


def relative_pointer(data: bytes, field: int, label: str) -> int:
    relative = struct.unpack_from("<i", data, field)[0]
    require(relative != 0, f"{label} pointer null")
    target = field + relative - 1
    require(0 <= target < len(data), f"{label} pointer outside decoded data")
    return target


def utf16z(data: bytes, offset: int, limit: int, label: str) -> str:
    require(offset % 2 == 0 and 0 <= offset < limit, f"{label} bounds invalid")
    end = offset
    while end + 1 < limit and data[end:end + 2] != b"\0\0":
        end += 2
    require(end + 1 < limit, f"{label} unterminated")
    try:
        return data[offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise VerifyError(f"{label} invalid UTF-16LE") from exc


def validate_descriptors(decoded: bytes) -> None:
    require(struct.unpack_from("<II", decoded, 0) == (0x0D, 2),
            "TSET root mismatch")
    for index, name in enumerate(("jersey00", "jersey00_mud")):
        base = 0x18 + index * 0x24
        require(decoded[base:base + 4] == b"TXTR", "embedded TXTR marker missing")
        name_offset = relative_pointer(decoded, base + 4, "name")
        descriptor_offset = relative_pointer(decoded, base + 8, "descriptor")
        root_offset = relative_pointer(decoded, base + 0x14, "root")
        require(utf16z(decoded, name_offset, 256, "name") == name,
                f"embedded name {index} mismatch")
        require(root_offset == 0 and descriptor_offset == (0x80 if index == 0 else 0xA0),
                f"descriptor/root {index} mismatch")
        words = struct.unpack_from("<6I", decoded, descriptor_offset)
        require(words == (0, 0, CLEAN_PALETTE_OFFSET + index * 1024,
                          0x08960B29, 0, 0x80000000),
                f"descriptor words {index} mismatch")


def independent_unswizzle(source: bytes, width: int, height: int) -> bytes:
    require(len(source) == width * height, "swizzled mip size mismatch")
    mask_x = 0
    mask_y = 0
    interleaved = 1
    dimension = 1
    while dimension < width or dimension < height:
        if dimension < width:
            mask_x |= interleaved
            interleaved <<= 1
        if dimension < height:
            mask_y |= interleaved
            interleaved <<= 1
        dimension <<= 1
    result = bytearray(width * height)
    swizzled_y = 0
    for y in range(height):
        swizzled_x = 0
        for x in range(width):
            result[y * width + x] = source[swizzled_x | swizzled_y]
            swizzled_x = (swizzled_x - mask_x) & mask_x
        swizzled_y = (swizzled_y - mask_y) & mask_y
    return bytes(result)


def parse_palette(video: bytes, offset: int) -> list[tuple[int, int, int, int]]:
    result = []
    for index in range(256):
        blue, green, red, alpha = video[offset + index * 4:offset + index * 4 + 4]
        result.append((red, green, blue, alpha))
    return result


def expand(indices: bytes, palette: list[tuple[int, int, int, int]]) -> bytes:
    return b"".join(bytes(palette[index]) for index in indices)


def decode_mips(decoded: bytes) -> tuple[list[bytes], list[bytes], list[bytes]]:
    require(len(decoded) == 177024, "decoded TSET size mismatch")
    video = decoded[256:]
    require(len(video) == 176768, "decoded video size mismatch")
    clean_palette = parse_palette(video, CLEAN_PALETTE_OFFSET)
    mud_palette = parse_palette(video, MUD_PALETTE_OFFSET)
    index_levels: list[bytes] = []
    clean_levels: list[bytes] = []
    mud_levels: list[bytes] = []
    offset = 0
    for width, height in MIP_DIMENSIONS:
        size = width * height
        indices = independent_unswizzle(video[offset:offset + size], width, height)
        index_levels.append(indices)
        clean_levels.append(expand(indices, clean_palette))
        mud_levels.append(expand(indices, mud_palette))
        offset += size
    require(offset == INDEX_CHAIN_BYTES, "mip chain length mismatch")
    used = {index for level in index_levels for index in level}
    require(used == set(range(32)), "diagnostic index set is not exact 0..31")
    require(video[CLEAN_PALETTE_OFFSET + 32 * 4:CLEAN_PALETTE_OFFSET + 1024]
            == bytes(1024 - 32 * 4), "unused clean palette entries nonzero")
    require(video[MUD_PALETTE_OFFSET + 32 * 4:MUD_PALETTE_OFFSET + 1024]
            == bytes(1024 - 32 * 4), "unused mud palette entries nonzero")
    for index in used:
        clean = clean_palette[index]
        mud = mud_palette[index]
        require(mud == ((clean[0] * 3 + 2) // 5,
                        (clean[1] * 3 + 2) // 5,
                        (clean[2] * 3 + 2) // 5,
                        clean[3]),
                f"mud palette index {index} is not deterministic darken_60")
    return index_levels, clean_levels, mud_levels


def downsample(rgba: bytes, width: int, height: int) -> bytes:
    result = bytearray((width // 2) * (height // 2) * 4)
    target_width = width // 2
    for y in range(height // 2):
        for x in range(width // 2):
            sources = (
                ((y * 2) * width + x * 2) * 4,
                ((y * 2) * width + x * 2 + 1) * 4,
                (((y * 2) + 1) * width + x * 2) * 4,
                (((y * 2) + 1) * width + x * 2 + 1) * 4,
            )
            target = (y * target_width + x) * 4
            for channel in range(4):
                result[target + channel] = (
                    sum(rgba[source + channel] for source in sources) + 2
                ) // 4
    return bytes(result)


def parse_deterministic_png(payload: bytes, width: int, height: int) -> bytes:
    require(payload.startswith(PNG_SIGNATURE), "preview PNG signature mismatch")
    offset = len(PNG_SIGNATURE)
    idat = bytearray()
    ihdr = None
    while offset < len(payload):
        require(offset + 12 <= len(payload), "preview PNG chunk truncated")
        length = struct.unpack_from(">I", payload, offset)[0]
        kind = payload[offset + 4:offset + 8]
        end = offset + 12 + length
        require(end <= len(payload), "preview PNG chunk exceeds file")
        data = payload[offset + 8:offset + 8 + length]
        crc = struct.unpack_from(">I", payload, offset + 8 + length)[0]
        require(zlib.crc32(kind + data) & 0xFFFFFFFF == crc,
                "preview PNG CRC mismatch")
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            idat.extend(data)
        elif kind == b"IEND":
            require(length == 0 and end == len(payload), "preview PNG IEND mismatch")
            break
        offset = end
    require(ihdr == (width, height, 8, 6, 0, 0, 0),
            "preview PNG IHDR mismatch")
    raw = zlib.decompress(bytes(idat))
    row_bytes = width * 4
    require(len(raw) == (row_bytes + 1) * height,
            "preview PNG inflated size mismatch")
    rgba = bytearray(width * height * 4)
    for y in range(height):
        start = y * (row_bytes + 1)
        require(raw[start] == 0, "canonical preview PNG does not use filter zero")
        rgba[y * row_bytes:(y + 1) * row_bytes] = raw[start + 1:start + 1 + row_bytes]
    return bytes(rgba)


def validate_manifest(path: Path) -> dict[str, object]:
    require(path.exists() and not path.is_symlink(), "manifest must be non-symlink")
    require(sha256_file(path) == MANIFEST_SHA256, "manifest hash mismatch")
    value = json.loads(path.read_bytes())
    require(value.get("schema") == SCHEMA, "manifest schema mismatch")
    require(value["input"]["clean"]["sha256"] == INPUT_PNG_SHA256 and
            value["input"]["mud"] == {"kind": "derived_palette", "mode": "darken_60"},
            "manifest inputs mismatch")
    require(value["mips"]["dimensions"] == [list(item) for item in MIP_DIMENSIONS] and
            value["mips"]["total_index_chain_bytes"] == INDEX_CHAIN_BYTES and
            value["mips"]["each_level_swizzled_independently"] is True,
            "manifest mip layout mismatch")
    quantization = value["quantization"]
    require(quantization["input_unique_rgba_colors"] == 32 and
            quantization["clean_palette_entries"] == 32 and
            quantization["mud_palette_entries"] == 32 and
            quantization["differing_pixel_count"] == 0 and
            quantization["total_squared_rgba_error"] == 0 and
            quantization["shared_index_chain"] is True,
            "manifest quantization mismatch")
    compression = value["compression"]
    require(compression["encoded_bytes"] == 22285 and
            compression["literal_count"] == 609 and
            compression["match_count"] == 10160 and
            compression["candidate_comparisons"] == 474460 and
            compression["verified_roundtrip"] is True,
            "manifest compression mismatch")
    rebuild = value["rebuild"]
    require(rebuild["complete_span_sha256"] == OUTPUT_SPAN_SHA256 and
            rebuild["decoded_sha256"] == OUTPUT_DECODED_SHA256 and
            rebuild["recompressed_bytes"] == 22285 and
            rebuild["zero_padding_bytes"] == 52403 and
            rebuild["fixed_span_fit"] is True and
            rebuild["zero_padding_verified"] is True,
            "manifest rebuild mismatch")
    require(len(value["previews"]) == 12 and
            all(row["strictly_reparsed"] is True for row in value["previews"]),
            "manifest preview records mismatch")
    require(value["claims"]["real_png_input_consumed"] is True and
            value["claims"]["all_mips_swizzled_and_decoded"] is True and
            value["claims"]["fixed_span_only"] is True and
            value["claims"]["originals_modified"] is False and
            value["claims"]["xiso_created"] is False and
            value["claims"]["title_executed"] is False and
            value["claims"]["runtime_visibility_proved"] is False,
            "manifest scope mismatch")
    return value


def run(index: Path, input_png: Path, span_path: Path, manifest_path: Path,
        preview_dir: Path) -> None:
    for role, path in (("input PNG", input_png), ("span", span_path),
                       ("manifest", manifest_path)):
        require(path.exists() and not path.is_symlink(), f"{role} must be non-symlink")
        require(stat.S_ISREG(path.stat().st_mode), f"{role} is not regular")
    require(preview_dir.exists() and not preview_dir.is_symlink() and preview_dir.is_dir(),
            "preview directory invalid")
    source_span = read_retail_span(index)
    output_span = span_path.read_bytes()
    require(sha256_bytes(source_span) == SOURCE_SPAN_SHA256,
            "retail source span hash mismatch")
    require(len(output_span) == SPAN_SIZE and
            sha256_bytes(output_span) == OUTPUT_SPAN_SHA256,
            "diagnostic output span mismatch")
    expected_header = (b"TSET", STORED_SIZE, 256, 176768,
                       0xFEEDBEEF, 32, 0, 0)
    require(HEADER.unpack_from(source_span) == expected_header and
            HEADER.unpack_from(output_span) == expected_header,
            "source/output wrapper mismatch")
    source_decoded, source_metrics = independent_decode(source_span[HEADER.size:])
    output_decoded, output_metrics = independent_decode(output_span[HEADER.size:])
    require(source_decoded[:256] == output_decoded[:256],
            "TSET system/descriptor buffer changed")
    require(sha256_bytes(output_decoded) == OUTPUT_DECODED_SHA256,
            "output decoded hash mismatch")
    require(source_metrics["consumed_bytes"] == 74674 and
            output_metrics == {
                "consumed_bytes": 22285,
                "literal_count": 609,
                "match_count": 10160,
                "maximum_distance": 4056,
                "maximum_length": 18,
            }, "output independent token metrics mismatch")
    require(output_span[HEADER.size + 22285:] == bytes(52403),
            "output stored tail is not exact zero padding")
    validate_descriptors(output_decoded)
    _, clean_levels, mud_levels = decode_mips(output_decoded)

    require(sha256_file(input_png) == INPUT_PNG_SHA256, "diagnostic input PNG hash mismatch")
    input_rgba = parse_deterministic_png(input_png.read_bytes(), 512, 256)
    require(clean_levels[0] == input_rgba,
            "decoded base clean mip differs from diagnostic PNG")
    current = input_rgba
    for level in range(1, 6):
        width, height = MIP_DIMENSIONS[level - 1]
        current = downsample(current, width, height)
        require(clean_levels[level] == current,
                f"decoded clean mip {level} differs from independent box filter")

    manifest = validate_manifest(manifest_path)
    rows = {(row["role"], row["level"]): row for row in manifest["previews"]}
    expected_names = set()
    for role, levels in (("clean", clean_levels), ("mud", mud_levels)):
        for level, rgba in enumerate(levels):
            width, height = MIP_DIMENSIONS[level]
            name = f"{role}_mip{level}_{width}x{height}.png"
            expected_names.add(name)
            path = preview_dir / name
            require(path.exists() and not path.is_symlink() and path.is_file(),
                    f"preview missing/invalid: {name}")
            payload = path.read_bytes()
            decoded_png = parse_deterministic_png(payload, width, height)
            require(decoded_png == rgba, f"preview RGBA differs: {name}")
            row = rows[role, level]
            require(row["png_file"] == name and
                    row["png_sha256"] == sha256_bytes(payload) and
                    row["rgba_sha256"] == sha256_bytes(rgba),
                    f"preview manifest hash differs: {name}")
    actual_names = {path.name for path in preview_dir.iterdir() if path.is_file()}
    require(actual_names == expected_names, "preview directory file set mismatch")
    print(
        "NFL_TSET_PNG_IMPORT_INDEPENDENT_VERIFY_PASS "
        f"input_sha={INPUT_PNG_SHA256} span_sha={OUTPUT_SPAN_SHA256} "
        "target=09H0 chunk=1 decoded=177024 encoded=22285/74688 zero_pad=52403 "
        "colors=32 quantization_error=0 mips=6 previews=12 shared_indices=true "
        "mud=darken_60 descriptors=preserved xiso=false runtime=false"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--input-png", required=True, type=Path)
    parser.add_argument("--span", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.index, args.input_png, args.span, args.manifest, args.preview_dir)
    except (OSError, VerifyError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
