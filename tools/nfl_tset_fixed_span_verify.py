#!/usr/bin/env python3
"""Independently verify the Lions identity fixed-span VC-LZ rebuild.

This verifier does not import ``nfl_txtr`` or the rebuild tool.  It reads the
retail span directly from pack A, implements the token decoder independently,
validates embedded TSET names/descriptors, and proves that only the old
14-byte padding changed to zeros.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import parse_archive


SCHEMA = "nfl2k5_tset_fixed_span_rebuild/v1"
OUTER_INDEX = 3685
OUTER_ID = 0x9A4832D6
OUTER_PACK_OFFSET = 0x055CA800
CHUNK_OFFSET = 0x70
STORED_SIZE = 74688
SPAN_SIZE = 74720
SOURCE_SPAN_SHA256 = "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862"
REBUILT_SPAN_SHA256 = "a802389334ad0e895557a9047f24381eb0f3ed9eefc77a7572a87ac64f56c9a9"
DECODED_SHA256 = "92a7e5ed6b8d0b468c4782509cf6335f88dfa06e189d7b624f80600ce727aa1e"
STREAM_SHA256 = "f83c0b59a59a744fdbd1f8b91172ec882203b70a5bc76e2b888b239f3b724706"
REPORT_SHA256 = "a70fe44b9bc02c998c0b8d71ca25144b066ebcab7223a964d00e8bdff3b3aa2d"
MUTATION_SPAN_SHA256 = "1a1ae6f6612563e0cf7736186cb5a10619c01e70eea405dab374e9d1e842a97a"
HEADER = struct.Struct("<4s7I")


class VerifyError(ValueError):
    """Raised when independent source/decode/report verification fails."""


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
            "retail target outer identity/segmentation mismatch")
    segment = entry.segments[0]
    require(segment.pack_name == "A" and segment.pack_offset == OUTER_PACK_OFFSET,
            "retail target pack mapping mismatch")
    with archive.packs[segment.pack_ordinal].path.open("rb") as stream:
        stream.seek(segment.pack_offset + CHUNK_OFFSET)
        value = stream.read(SPAN_SIZE)
    require(len(value) == SPAN_SIZE, "retail target span is truncated")
    return value


def independent_decode(stream: bytes) -> tuple[bytes, dict[str, int]]:
    require(len(stream) >= 10, "VC-LZ stream prefix is truncated")
    output_size, stream_tag = struct.unpack_from("<II", stream, 0)
    offset_bits = stream[8]
    require(output_size == 177024 and stream_tag == 3 and offset_bits == 12,
            "VC-LZ prefix mismatch")
    length_bits = 16 - offset_bits
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << length_bits) - 1
    output = bytearray(output_size)
    source_offset = 9
    flags = stream[source_offset]
    source_offset += 1
    flag_mask = 1
    output_offset = 0
    literal_count = 0
    match_count = 0
    maximum_distance = 0
    maximum_length = 0
    while output_offset < output_size:
        if flags & flag_mask:
            require(source_offset + 2 <= len(stream), "truncated VC-LZ match")
            code = struct.unpack_from("<H", stream, source_offset)[0]
            source_offset += 2
            distance = code & distance_mask
            length = ((code >> offset_bits) & length_mask) + 3
            require(0 < distance <= output_offset, "invalid VC-LZ match distance")
            require(output_offset + length <= output_size,
                    "VC-LZ match exceeds output")
            for index in range(length - 1, -1, -1):
                output[output_offset + index] = output[
                    output_offset - distance + index
                ]
            output_offset += length
            match_count += 1
            maximum_distance = max(maximum_distance, distance)
            maximum_length = max(maximum_length, length)
        else:
            require(source_offset < len(stream), "truncated VC-LZ literal")
            output[output_offset] = stream[source_offset]
            source_offset += 1
            output_offset += 1
            literal_count += 1
        flag_mask = (flag_mask << 1) & 0xFF
        if flag_mask == 0 and output_offset < output_size:
            require(source_offset < len(stream), "missing VC-LZ flag byte")
            flags = stream[source_offset]
            source_offset += 1
            flag_mask = 1
    return bytes(output), {
        "consumed_bytes": source_offset,
        "literal_count": literal_count,
        "match_count": match_count,
        "maximum_distance": maximum_distance,
        "maximum_length": maximum_length,
    }


def relative_pointer(data: bytes, field: int, label: str) -> int:
    require(field + 4 <= len(data), f"{label} pointer field truncated")
    relative = struct.unpack_from("<i", data, field)[0]
    require(relative != 0, f"{label} pointer is null")
    target = field + relative - 1
    require(0 <= target < len(data), f"{label} pointer outside decoded data")
    return target


def utf16z(data: bytes, offset: int, limit: int, label: str) -> str:
    require(offset % 2 == 0 and 0 <= offset < limit <= len(data),
            f"{label} bounds/alignment invalid")
    end = offset
    while end + 1 < limit and data[end:end + 2] != b"\0\0":
        end += 2
    require(end + 1 < limit, f"{label} unterminated")
    try:
        return data[offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise VerifyError(f"{label} invalid UTF-16LE") from exc


def validate_decoded(decoded: bytes) -> None:
    require(len(decoded) == 177024 and sha256_bytes(decoded) == DECODED_SHA256,
            "decoded TSET identity mismatch")
    require(struct.unpack_from("<II", decoded, 0) == (0x0D, 2),
            "decoded TSET root mismatch")
    for index, expected_name in enumerate(("jersey00", "jersey00_mud")):
        base = 0x18 + index * 0x24
        require(decoded[base:base + 4] == b"TXTR",
                f"TSET reference {index} lacks TXTR marker")
        name_offset = relative_pointer(decoded, base + 4, "texture name")
        descriptor_offset = relative_pointer(decoded, base + 8, "descriptor")
        root_offset = relative_pointer(decoded, base + 0x14, "root")
        require(utf16z(decoded, name_offset, 256, "texture name") == expected_name,
                f"TSET reference {index} name mismatch")
        require(root_offset == 0 and descriptor_offset == (0x80 if index == 0 else 0xA0),
                f"TSET reference {index} descriptor/root mismatch")
        descriptor = struct.unpack_from("<6I", decoded, descriptor_offset)
        require(descriptor ==
                (0, 0, 174720 + index * 1024, 0x08960B29, 0, 0x80000000),
                f"TSET reference {index} descriptor words mismatch")
        packed_format = descriptor[3]
        dimensions = (packed_format >> 4) & 0xF
        format_code = (packed_format >> 8) & 0xFF
        mip_levels = (packed_format >> 16) & 0xF
        width = 1 << ((packed_format >> 20) & 0xF)
        height = 1 << ((packed_format >> 24) & 0xF)
        depth = 1 << ((packed_format >> 28) & 0xF)
        require((dimensions, format_code, mip_levels, width, height, depth) ==
                (2, 11, 6, 512, 256, 1),
                f"TSET reference {index} decoded descriptor mismatch")


def validate_report(path: Path) -> None:
    require(path.exists() and not path.is_symlink(),
            "canonical report must be a non-symlink file")
    require(sha256_file(path) == REPORT_SHA256, "canonical report hash mismatch")
    value = json.loads(path.read_bytes())
    require(value.get("schema") == SCHEMA, "canonical report schema mismatch")
    require(value["target"]["logical_name"] == "09H0.IFF" and
            value["target"]["outer_index"] == OUTER_INDEX and
            value["target"]["chunk_index"] == 1 and
            value["target"]["stored_size"] == STORED_SIZE and
            value["target"]["complete_span_size"] == SPAN_SIZE and
            value["target"]["source_span_sha256"] == SOURCE_SPAN_SHA256 and
            value["target"]["decoded_sha256"] == DECODED_SHA256,
            "canonical report target mismatch")
    compression = value["compression"]
    require(compression["encoded_bytes"] == 74674 and
            compression["stream_tag"] == 3 and
            compression["offset_bits"] == 12 and
            compression["literal_count"] == 25215 and
            compression["match_count"] == 21787 and
            compression["candidate_comparisons"] == 1118132 and
            compression["verified_roundtrip"] is True,
            "canonical compression metrics mismatch")
    identity = value["identity_rebuild"]
    require(identity["rebuilt_span_sha256"] == REBUILT_SPAN_SHA256 and
            identity["recompressed_bytes"] == 74674 and
            identity["zero_padding_bytes"] == 14 and
            identity["compressed_stream_matches_template"] is True and
            identity["decoded_bytes_equal"] is True and
            identity["only_original_padding_changed"] is True,
            "canonical identity rebuild mismatch")
    mutation = value["one_byte_palette_probe"]
    require(mutation["decoded_offset"] == 174976 and
            mutation["before_byte"] == 0xFE and mutation["after_byte"] == 0xAB and
            mutation["recompressed_bytes"] == 74675 and
            mutation["zero_padding_bytes"] == 13 and
            mutation["rebuilt_span_sha256"] == MUTATION_SPAN_SHA256 and
            mutation["decoded_bytes_equal"] is True and
            mutation["fits_original_stored_body"] is True and
            mutation["artifact_written"] is False,
            "canonical mutation probe mismatch")
    require(value["claims"]["retail_stream_reproduced_exactly"] is True and
            value["claims"]["identity_fixed_span_rebuild_proved"] is True and
            value["claims"]["nonidentity_fixed_span_rebuild_proved"] is True and
            value["claims"]["general_png_importer"] is False and
            value["claims"]["xiso_created"] is False and
            value["claims"]["title_executed"] is False,
            "canonical report scope mismatch")


def run(index: Path, rebuilt_path: Path, report_path: Path) -> None:
    require(rebuilt_path.exists() and not rebuilt_path.is_symlink(),
            "rebuilt span must be a non-symlink file")
    info = rebuilt_path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_size == SPAN_SIZE,
            "rebuilt span file size/type mismatch")
    source = read_retail_span(index)
    rebuilt = rebuilt_path.read_bytes()
    require(sha256_bytes(source) == SOURCE_SPAN_SHA256,
            "retail source span hash mismatch")
    require(sha256_bytes(rebuilt) == REBUILT_SPAN_SHA256,
            "rebuilt span hash mismatch")
    expected_header = (b"TSET", STORED_SIZE, 256, 176768,
                       0xFEEDBEEF, 32, 0, 0)
    require(HEADER.unpack_from(source) == expected_header and
            HEADER.unpack_from(rebuilt) == expected_header,
            "source/rebuilt wrapper mismatch")

    source_decoded, source_metrics = independent_decode(source[HEADER.size:])
    rebuilt_decoded, rebuilt_metrics = independent_decode(rebuilt[HEADER.size:])
    require(source_decoded == rebuilt_decoded,
            "source/rebuilt independent decoded bytes differ")
    validate_decoded(source_decoded)
    require(source_metrics == rebuilt_metrics == {
        "consumed_bytes": 74674,
        "literal_count": 25215,
        "match_count": 21787,
        "maximum_distance": 4095,
        "maximum_length": 18,
    }, "independent token metrics mismatch")
    source_stream = source[HEADER.size:HEADER.size + 74674]
    rebuilt_stream = rebuilt[HEADER.size:HEADER.size + 74674]
    require(source_stream == rebuilt_stream and
            sha256_bytes(source_stream) == STREAM_SHA256,
            "rebuilt compressed stream differs from retail")
    require(source[74706:] == b"\x3c" * 14 and rebuilt[74706:] == bytes(14),
            "source/rebuilt padding mismatch")
    differences = [
        index for index, (before, after) in enumerate(zip(source, rebuilt))
        if before != after
    ]
    require(differences == list(range(74706, 74720)),
            "rebuilt span changed bytes outside retail padding")
    validate_report(report_path)
    print(
        "NFL_TSET_FIXED_SPAN_INDEPENDENT_VERIFY_PASS "
        "target=09H0 chunk=1 span=74720 encoded=74674 stored=74688 "
        "zero_pad=14 exact_stream=true decoded_sha=" + DECODED_SHA256 + " "
        "names=jersey00,jersey00_mud descriptors=512x256_P8 "
        "palette_probe=74675/74688 png_importer=false xiso=false title_executed=false"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--rebuilt-span", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.index, args.rebuilt_span, args.report)
    except (OSError, VerifyError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
