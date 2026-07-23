#!/usr/bin/env python3
"""Independently verify the complete NFL 2K5 jersey-TSET donor XISO.

This verifier does not import the writer.  It reparses both XDVDFS trees,
scans every byte of both 6.30 GB images, independently decodes the retail and
patched TSET spans, validates both embedded texture descriptors, and compares
listings from the pinned extract-xiso build.
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

import nfl_uniform_color_xiso_direct_verify as independent
from nfl_txtr import Chunk, HEADER, TextureInfo, decode_chunk, texture_to_rgba


SCHEMA = "nfl2k5_jersey_tset_donor_xiso_direct_patch/v1"
OUTPUT_SHA256 = "502b41d2d7813549342861c92e17b9ff1bc83a8f0cb5995401e9abaeb2b288f5"
PACK_A_SHA256 = "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b"
OUTPUT_PACK_A_SHA256 = "6acfc00b3947524de64a96c29e362033c9ed339caf9853b5d066b5bc9766b1b9"
PACK_B_SHA256 = "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"

TARGET_OUTER_PACK_OFFSET = 0x055CA800
DONOR_OUTER_PACK_OFFSET = 0x098C4800
CHUNK_OFFSET = 0x70
STORED_SIZE = 74688
SPAN_SIZE = 74720
TARGET_ABSOLUTE = 5_011_470_448
DONOR_ABSOLUTE = 4_623_452_272
TARGET_HEADER = bytes.fromhex(
    "54534554c02301000001000080b20200efbeedfe200000000000000000000000"
)
DONOR_HEADER = bytes.fromhex(
    "54534554c02301000001000080b20200efbeedfe100000000000000000000000"
)
TARGET_SPAN_SHA256 = "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862"
DONOR_SPAN_SHA256 = "0d6bcfe1f48ff0158a6c29be98cce56800a90bbd4754282e8fc876dea517dbd9"
TARGET_STORED_SHA256 = "b7f57b05bba5278616486dde2f3680bd101f861fbb87e874fd661c33fa82d13c"
DONOR_STORED_SHA256 = "5d377f17cb054abc5b6d26955ebd4cc2153ce203514bd7b1a391ae74e67156b4"
TARGET_DECODED_SHA256 = "92a7e5ed6b8d0b468c4782509cf6335f88dfa06e189d7b624f80600ce727aa1e"
DONOR_DECODED_SHA256 = "de80718cf743f0a866b2d0381b5658a72bedd68644dc6a5bbf009cd2c523d95a"

RELATIVE_DIFF_COUNT = 73304
RELATIVE_DIFF_U32LE_SHA256 = (
    "55e87bb9c2bd982be5378ba4542e9e127989d9d2f0e87ead3617fff47e274360"
)
ABSOLUTE_DIFF_U64LE_SHA256 = (
    "a7a8d508beb8c42cfd69cd41b79c0611bb68cdcfcb1f9f8bf93c6d7ec91be24d"
)
RELATIVE_RUN_COUNT = 903
RELATIVE_RUN_U32LE_SHA256 = (
    "e03d7d5dd1dcecc1ad2b9e0bd22edabb5a4a43616f53c7615c93acb4a65bb6f6"
)

TEXTURE_PINS = {
    "target": {
        "decoded_sha256": TARGET_DECODED_SHA256,
        "consumed_bytes": 74674,
        "unused_bytes": 14,
        "pixel_sha256": "2e42b604477996b1aad6e41a33adf7af1d00f0703913902f22c8981cf2e7efa4",
        "textures": {
            "jersey00": {
                "palette_sha256": "f9738b74119ecc3c530561b637acf394bbed6b2c649f4c5757f644dcf12e3eca",
                "rgba_sha256": "d8da06e8634178d76153c133cc2b56356b62b41eb567ee269782a57b4d6eae51",
            },
            "jersey00_mud": {
                "palette_sha256": "9f54cba6507eb77c6624581beecf00ec88c696695f8d0f31292d8d2b37897101",
                "rgba_sha256": "857d2bfeedc8cac98167f76b1e195e7a932e6497c0d52626000299257c46b926",
            },
        },
    },
    "donor": {
        "decoded_sha256": DONOR_DECODED_SHA256,
        "consumed_bytes": 74679,
        "unused_bytes": 9,
        "pixel_sha256": "f3d7c5c70d4260539b9ff4affbe67a41a1053381969df02bf5582c43c90a3886",
        "textures": {
            "jersey00": {
                "palette_sha256": "3a3a732b6036a01404f3ed4657955e9cc22a55044c1ff1930c1b7fa5d8afc938",
                "rgba_sha256": "8f61aafc370a7e8856a41724e4078d7c4e8a31182085a89a907f3f3775a4e6e7",
            },
            "jersey00_mud": {
                "palette_sha256": "15e024110c87bdacc337fbd5e4dbbd6d8ae38c43384b8bb43ece2652b21667d5",
                "rgba_sha256": "8d9c9f5639934c9635874193d8d02c72bb3bb6728381cfc8ba0bc55aa5d254b2",
            },
        },
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise independent.VerifyError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def relative_pointer(data: bytes, field: int, label: str) -> int:
    require(field + 4 <= len(data), f"{label} pointer field is truncated")
    value = struct.unpack_from("<i", data, field)[0]
    require(value != 0, f"{label} pointer is null")
    target = field + value - 1
    require(0 <= target < len(data), f"{label} pointer is out of bounds")
    return target


def utf16z(data: bytes, offset: int, limit: int, label: str) -> str:
    require(offset % 2 == 0 and 0 <= offset < limit <= len(data),
            f"{label} bounds/alignment invalid")
    end = offset
    while end + 1 < limit and data[end:end + 2] != b"\0\0":
        end += 2
    require(end + 1 < limit, f"{label} is unterminated")
    try:
        return data[offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise independent.VerifyError(f"{label} is invalid UTF-16LE") from exc


def decode_and_validate_tset(span: bytes, role: str) -> dict[str, object]:
    pins = TEXTURE_PINS[role]
    require(len(span) == SPAN_SIZE, f"{role} TSET span size mismatch")
    fields = HEADER.unpack_from(span)
    expected_scratch = 32 if role == "target" else 16
    require(fields == (b"TSET", STORED_SIZE, 256, 176768,
                       0xFEEDBEEF, expected_scratch, 0, 0),
            f"{role} TSET wrapper fields mismatch")
    chunk = Chunk(
        index=1,
        offset=0,
        kind="TSET",
        stored_size=STORED_SIZE,
        system_bytes=256,
        video_bytes=176768,
        compression_magic=0xFEEDBEEF,
        overlap_scratch_bytes=expected_scratch,
        reserved0=0,
        reserved1=0,
    )
    decoded, info = decode_chunk(span, chunk)
    require(info is not None and len(decoded) == 177024,
            f"{role} TSET did not fully decode")
    require(sha256_bytes(decoded) == pins["decoded_sha256"] and
            info.consumed_bytes == pins["consumed_bytes"] and
            STORED_SIZE - info.consumed_bytes == pins["unused_bytes"],
            f"{role} decoded/LZ identity mismatch")
    version, count = struct.unpack_from("<II", decoded, 0)
    require((version, count) == (0x0D, 2), f"{role} TSET root mismatch")
    video = decoded[256:]
    names = ("jersey00", "jersey00_mud")
    rows: list[dict[str, object]] = []
    for index, expected_name in enumerate(names):
        base = 0x18 + index * 0x24
        require(decoded[base:base + 4] == b"TXTR",
                f"{role} ref {index} lacks TXTR marker")
        name_offset = relative_pointer(decoded, base + 4, f"{role} name")
        descriptor_offset = relative_pointer(decoded, base + 8, f"{role} descriptor")
        root_offset = relative_pointer(decoded, base + 0x14, f"{role} root")
        name = utf16z(decoded, name_offset, 256, f"{role} name")
        require(name == expected_name, f"{role} ref {index} name mismatch")
        require(root_offset == 0 and descriptor_offset == (0x80 if index == 0 else 0xA0),
                f"{role} ref {index} descriptor/root pointer mismatch")
        unknown0, pixel_offset, palette_offset, packed_format, packed_size, flags = \
            struct.unpack_from("<6I", decoded, descriptor_offset)
        dimensions = (packed_format >> 4) & 0xF
        format_code = (packed_format >> 8) & 0xFF
        mip_levels = (packed_format >> 16) & 0xF
        width = 1 << ((packed_format >> 20) & 0xF)
        height = 1 << ((packed_format >> 24) & 0xF)
        depth = 1 << ((packed_format >> 28) & 0xF)
        require((unknown0, pixel_offset, palette_offset, packed_format,
                 packed_size, flags) ==
                (0, 0, 174720 + index * 1024, 0x08960B29, 0, 0x80000000),
                f"{role} {name} raw descriptor mismatch")
        require((dimensions, format_code, mip_levels, width, height, depth) ==
                (2, 11, 6, 512, 256, 1),
                f"{role} {name} decoded descriptor mismatch")
        pixel = video[pixel_offset:pixel_offset + width * height]
        palette = video[palette_offset:palette_offset + 1024]
        require(len(pixel) == 131072 and len(palette) == 1024,
                f"{role} {name} video ranges truncated")
        texture = TextureInfo(
            name=name,
            name_offset=name_offset,
            descriptor_offset=descriptor_offset,
            pixel_offset=pixel_offset,
            palette_offset=palette_offset,
            packed_format=packed_format,
            packed_size=packed_size,
            descriptor_flags=flags,
            dimensions=dimensions,
            format_code=format_code,
            format_name="P8",
            mip_levels=mip_levels,
            width=width,
            height=height,
            depth=depth,
        )
        rgba = texture_to_rgba(decoded, chunk, texture)
        texture_pin = pins["textures"][name]
        require(sha256_bytes(pixel) == pins["pixel_sha256"] and
                sha256_bytes(palette) == texture_pin["palette_sha256"] and
                sha256_bytes(rgba) == texture_pin["rgba_sha256"],
                f"{role} {name} pixel/palette/RGBA identity mismatch")
        rows.append({
            "name": name,
            "width": width,
            "height": height,
            "format": "P8",
            "mip_levels": mip_levels,
            "rgba_sha256": sha256_bytes(rgba),
        })
    return {
        "decoded_sha256": sha256_bytes(decoded),
        "consumed_bytes": info.consumed_bytes,
        "textures": rows,
    }


def offset_digest(offsets: list[int], fmt: str) -> str:
    return sha256_bytes(b"".join(struct.pack(fmt, offset) for offset in offsets))


def difference_runs(offsets: list[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for offset in offsets:
        if not result or offset != result[-1][1] + 1:
            result.append((offset, offset))
        else:
            result[-1] = (result[-1][0], offset)
    return result


def scan_images(source_fd: int, output_fd: int) -> tuple[str, str, list[int]]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    while position < independent.IMAGE_SIZE:
        request = min(independent.CHUNK, independent.IMAGE_SIZE - position)
        before = independent.pread_exact(source_fd, position, request)
        after = independent.pread_exact(output_fd, position, request)
        source_hash.update(before)
        output_hash.update(after)
        if before != after:
            differences.extend(
                position + index
                for index, (old, new) in enumerate(zip(before, after))
                if old != new
            )
            require(len(differences) <= RELATIVE_DIFF_COUNT,
                    "output contains more changes than the donor-span ledger")
        position += request
    return source_hash.hexdigest(), output_hash.hexdigest(), differences


def validate_manifest(path: Path, source: Path, output: Path,
                      differences: list[int]) -> None:
    require(path.exists() and not path.is_symlink(), "manifest must be a non-symlink file")
    value = json.loads(path.read_bytes())
    require(value.get("schema") == SCHEMA, "manifest schema mismatch")
    require(Path(value["source"]["path"]).resolve() == source.resolve() and
            Path(value["output"]["path"]).resolve() == output.resolve(),
            "manifest source/output path mismatch")
    require(value["source"]["sha256_before"] == independent.SOURCE_SHA256 and
            value["source"]["sha256_after"] == independent.SOURCE_SHA256 and
            value["source"]["opened_read_only"] is True and
            value["source"]["modified"] is False,
            "manifest source-safety proof mismatch")
    require(value["output"]["sha256"] == OUTPUT_SHA256 and
            value["output"]["exclusively_created"] is True and
            value["output"]["distinct_from_source_inode"] is True,
            "manifest output identity/O_EXCL proof mismatch")
    require(value["source"]["device"] == source.stat().st_dev and
            value["source"]["inode"] == source.stat().st_ino and
            value["output"]["device"] == output.stat().st_dev and
            value["output"]["inode"] == output.stat().st_ino,
            "source/output identity changed since writer run")
    patch = value["patch"]
    require(patch["target"]["resource"] == "09H0.IFF" and
            patch["target"]["outer_index"] == 3685 and
            patch["target"]["absolute_tset_offset"] == TARGET_ABSOLUTE and
            patch["target"]["source_span_sha256"] == TARGET_SPAN_SHA256 and
            patch["target"]["patched_span_sha256"] == DONOR_SPAN_SHA256,
            "manifest target record mismatch")
    require(patch["donor"]["resource"] == "01A0.IFF" and
            patch["donor"]["outer_index"] == 3939 and
            patch["donor"]["absolute_tset_offset"] == DONOR_ABSOLUTE and
            patch["donor"]["span_sha256"] == DONOR_SPAN_SHA256 and
            patch["donor"]["unchanged_in_output"] is True,
            "manifest donor record mismatch")
    require(patch["complete_wrapper_and_stored_stream_copied"] is True and
            patch["target_complete_span_equals_pinned_donor"] is True and
            patch["target_complete_span_size"] == SPAN_SIZE,
            "manifest complete-span equality proof mismatch")
    require(patch["relative_changed_byte_count"] == RELATIVE_DIFF_COUNT and
            patch["relative_changed_offsets_u32le_sha256"] ==
            RELATIVE_DIFF_U32LE_SHA256 and
            patch["relative_changed_run_count"] == RELATIVE_RUN_COUNT and
            patch["relative_changed_runs_u32le_sha256"] ==
            RELATIVE_RUN_U32LE_SHA256 and
            patch["actual_changed_byte_count"] == len(differences) and
            patch["actual_changed_offsets_u64le_sha256"] ==
            ABSOLUTE_DIFF_U64LE_SHA256 and
            patch["all_other_image_bytes_identical"] is True,
            "manifest full-image difference proof mismatch")
    require(patch["source_pack_a_sha256"] == PACK_A_SHA256 and
            patch["output_pack_a_sha256"] == OUTPUT_PACK_A_SHA256 and
            patch["donor_pack_b_sha256"] == PACK_B_SHA256 and
            patch["unrelated_pack0_sha256"] == PACK0_SHA256,
            "manifest pack hash record mismatch")
    require(value["probe"]["emulator_started"] is False and
            value["probe"]["runtime_result"] is None and
            value["claims"]["donor_texture_swap"] is True and
            value["claims"]["general_png_importer"] is False and
            value["claims"]["runtime_visibility_proved"] is False,
            "manifest scope/runtime claim mismatch")


def run(source: Path, output: Path, manifest: Path, canonical_report: Path,
        extract_xiso: Path) -> None:
    for role, path in (("source", source), ("output", output)):
        require(path.exists() and not path.is_symlink(),
                f"{role} must be a non-symlink file")
        info = path.stat()
        require(stat.S_ISREG(info.st_mode), f"{role} is not regular")
        require(info.st_size == independent.IMAGE_SIZE, f"{role} size mismatch")
    require((source.stat().st_dev, source.stat().st_ino) !=
            (output.stat().st_dev, output.stat().st_ino),
            "source and output alias the same inode")
    require(extract_xiso.is_file() and os.access(extract_xiso, os.X_OK),
            "pinned extract-xiso binary missing")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    output_fd = os.open(output, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        source_entries, source_root, source_directories = independent.parse_xdvdfs(
            source_fd, independent.IMAGE_SIZE
        )
        output_entries, output_root, output_directories = independent.parse_xdvdfs(
            output_fd, independent.IMAGE_SIZE
        )
        independent.validate_expected_entries(source_entries)
        independent.validate_expected_entries(output_entries)
        require(source_entries == output_entries and source_root == output_root,
                "output XDVDFS tree differs")
        require(source_directories == output_directories == [(33, 108), (35_530, 2_048)],
                "directory extents differ")
        require(independent.pread_exact(source_fd, independent.VOLUME_OFFSET,
                                       independent.VOLUME_SIZE) ==
                independent.pread_exact(output_fd, independent.VOLUME_OFFSET,
                                        independent.VOLUME_SIZE),
                "XDVDFS volume descriptor changed")
        for sector, size in source_directories:
            require(independent.pread_exact(source_fd, sector * independent.SECTOR, size) ==
                    independent.pread_exact(output_fd, sector * independent.SECTOR, size),
                    f"directory bytes changed at sector {sector}")

        source_sha, output_sha, differences = scan_images(source_fd, output_fd)
        require(source_sha == independent.SOURCE_SHA256, "retail source hash mismatch")
        require(output_sha == OUTPUT_SHA256, "donor output hash mismatch")
        require(len(differences) == RELATIVE_DIFF_COUNT,
                "full-image changed-byte count mismatch")
        relative = [offset - TARGET_ABSOLUTE for offset in differences]
        require(all(0 <= offset < SPAN_SIZE for offset in relative),
                "a changed byte lies outside the target TSET span")
        require(offset_digest(relative, "<I") == RELATIVE_DIFF_U32LE_SHA256 and
                offset_digest(differences, "<Q") == ABSOLUTE_DIFF_U64LE_SHA256,
                "full-image exact difference ledger mismatch")
        runs = difference_runs(relative)
        require(len(runs) == RELATIVE_RUN_COUNT and
                sha256_bytes(b"".join(struct.pack("<II", start, end)
                                      for start, end in runs)) ==
                RELATIVE_RUN_U32LE_SHA256,
                "full-image difference-run ledger mismatch")

        pack_a = source_entries["vc_53450030/a"]
        pack_b = source_entries["vc_53450030/b"]
        pack0 = source_entries["vc_53450030/0"]
        xbe = source_entries["default.xbe"]
        require(pack_a.offset + TARGET_OUTER_PACK_OFFSET + CHUNK_OFFSET == TARGET_ABSOLUTE,
                "target absolute offset arithmetic mismatch")
        require(pack_b.offset + DONOR_OUTER_PACK_OFFSET + CHUNK_OFFSET == DONOR_ABSOLUTE,
                "donor absolute offset arithmetic mismatch")
        source_target = independent.pread_exact(source_fd, TARGET_ABSOLUTE, SPAN_SIZE)
        source_donor = independent.pread_exact(source_fd, DONOR_ABSOLUTE, SPAN_SIZE)
        output_target = independent.pread_exact(output_fd, TARGET_ABSOLUTE, SPAN_SIZE)
        output_donor = independent.pread_exact(output_fd, DONOR_ABSOLUTE, SPAN_SIZE)
        require(source_target[:32] == TARGET_HEADER and source_donor[:32] == DONOR_HEADER,
                "retail TSET wrapper mismatch")
        require(sha256_bytes(source_target) == TARGET_SPAN_SHA256 and
                sha256_bytes(source_target[32:]) == TARGET_STORED_SHA256,
                "retail target TSET mismatch")
        require(sha256_bytes(source_donor) == DONOR_SPAN_SHA256 and
                sha256_bytes(source_donor[32:]) == DONOR_STORED_SHA256,
                "retail donor TSET mismatch")
        require(output_target == source_donor and output_donor == source_donor,
                "patched target is not exact donor or donor changed")
        decode_and_validate_tset(source_target, "target")
        decode_and_validate_tset(source_donor, "donor")
        decode_and_validate_tset(output_target, "donor")

        require(independent.hash_extent(source_fd, pack_a.offset, pack_a.size)
                == PACK_A_SHA256 and
                independent.hash_extent(output_fd, pack_a.offset, pack_a.size)
                == OUTPUT_PACK_A_SHA256, "pack A hashes mismatch")
        require(independent.hash_extent(source_fd, pack_b.offset, pack_b.size)
                == PACK_B_SHA256 and
                independent.hash_extent(output_fd, pack_b.offset, pack_b.size)
                == PACK_B_SHA256, "donor pack B changed")
        require(independent.hash_extent(source_fd, pack0.offset, pack0.size)
                == PACK0_SHA256 and
                independent.hash_extent(output_fd, pack0.offset, pack0.size)
                == PACK0_SHA256, "unrelated pack 0 changed")
        require(independent.hash_extent(source_fd, xbe.offset, xbe.size)
                == independent.XBE_SHA256 and
                independent.hash_extent(output_fd, xbe.offset, xbe.size)
                == independent.XBE_SHA256, "default.xbe changed")
    finally:
        os.close(output_fd)
        os.close(source_fd)

    _, source_listing, source_total = independent.extract_listing(extract_xiso, source)
    banner, output_listing, output_total = independent.extract_listing(extract_xiso, output)
    require(source_listing == output_listing, "extract-xiso listings differ")
    require(len(source_listing) == 20, "extract-xiso listing count mismatch")
    require(source_total == output_total == independent.EXPECTED_TOTAL_FILE_BYTES,
            "extract-xiso total byte count mismatch")
    validate_manifest(manifest, source, output, differences)
    validate_manifest(canonical_report, source, output, differences)
    require(manifest.read_bytes() == canonical_report.read_bytes(),
            "canonical report is not byte-identical to writer manifest")

    print(
        "NFL_JERSEY_TSET_DONOR_XISO_DIRECT_VERIFY_PASS "
        f"source_sha={independent.SOURCE_SHA256} output_sha={OUTPUT_SHA256} "
        "target=09H0 donor=01A0 chunk=1 span=74720 changed_bytes=73304 "
        "textures=jersey00,jersey00_mud descriptors=512x256_P8 "
        f"files=19 layout=identical source=unchanged xbe=unchanged pack0=unchanged "
        f"runtime_visibility=false png_importer=false extract_xiso='{banner}'"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--canonical-report", required=True, type=Path)
    parser.add_argument("--extract-xiso", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.source, args.output, args.manifest, args.canonical_report,
            args.extract_xiso)
    except (OSError, independent.VerifyError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
