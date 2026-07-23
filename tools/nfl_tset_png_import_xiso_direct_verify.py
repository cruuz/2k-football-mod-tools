#!/usr/bin/env python3
"""Independently verify the layout-identical CODEX MOD NFL 2K5 XISO."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile

import nfl_tset_png_import_verify as png_verify
import nfl_uniform_color_xiso_direct_verify as independent
from nfl_tset_fixed_span_verify import independent_decode


SCHEMA = "nfl2k5_tset_png_import_xiso_direct_patch/v1"
OUTPUT_SHA256 = "b9f47fcec3e284a12ea30f390035dd29f97fa62507330ba3ff30391cf4e10ae6"
PACK_A_SHA256 = "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b"
OUTPUT_PACK_A_SHA256 = "25b8557c7dd10e6a1d35e002df544628c226d348ca77314835c0ce762aa8714d"
PACK_B_SHA256 = "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
TARGET_OUTER_PACK_OFFSET = 0x055CA800
TARGET_CHUNK_OFFSET = 0x70
TARGET_ABSOLUTE = 5_011_470_448
SPAN_SIZE = 74720
SOURCE_SPAN_SHA256 = "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862"
REPLACEMENT_SPAN_SHA256 = "76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8"
REPLACEMENT_DECODED_SHA256 = "f5ed9101fa5c8bb742168b18fac698f57185c6b6a0190545ecafc1bb1b99c30e"
IMPORT_MANIFEST_SHA256 = "3500f6e6a3fddc4680a43214dd8f283bb8d1a13b355dcb2e8bbb349417613d80"
INPUT_PNG_SHA256 = "6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8"
RELATIVE_DIFF_COUNT = 70333
RELATIVE_DIFF_U32LE_SHA256 = "d000207712b34af5ab409c1fb512f1cb605632da28d185375afe477993cca4f5"
RELATIVE_RUN_COUNT = 3265
RELATIVE_RUN_U32LE_SHA256 = "50dda23eee5735a6c406b496bc329507743baf55d6905d289b1292c3c9e7e569"
ABSOLUTE_DIFF_U64LE_SHA256 = "299067b59b6fa1411bae613281c76b9bd95ae3862e7b07c50cb784e871cd1976"
HEADER = struct.Struct("<4s7I")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise independent.VerifyError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def offset_digest(offsets: list[int], fmt: str) -> str:
    return sha256_bytes(b"".join(struct.pack(fmt, value) for value in offsets))


def difference_runs(offsets: list[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for value in offsets:
        if not result or value != result[-1][1] + 1:
            result.append((value, value))
        else:
            result[-1] = (result[-1][0], value)
    return result


def scan_images(source_fd: int, output_fd: int) -> tuple[str, str, list[int]]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    while position < independent.IMAGE_SIZE:
        size = min(independent.CHUNK, independent.IMAGE_SIZE - position)
        before = independent.pread_exact(source_fd, position, size)
        after = independent.pread_exact(output_fd, position, size)
        source_hash.update(before)
        output_hash.update(after)
        if before != after:
            differences.extend(
                position + index
                for index, (old, new) in enumerate(zip(before, after))
                if old != new
            )
            require(len(differences) <= RELATIVE_DIFF_COUNT,
                    "output has more changes than the pinned span ledger")
        position += size
    return source_hash.hexdigest(), output_hash.hexdigest(), differences


def validate_writer_manifest(path: Path, source: Path, output: Path,
                             replacement: Path, import_manifest: Path) -> None:
    require(path.exists() and not path.is_symlink(), "writer manifest invalid")
    value = json.loads(path.read_bytes())
    require(value.get("schema") == SCHEMA, "writer manifest schema mismatch")
    require(Path(value["source"]["path"]).resolve() == source.resolve() and
            Path(value["output"]["path"]).resolve() == output.resolve() and
            Path(value["replacement"]["path"]).resolve() == replacement.resolve(),
            "writer manifest path mismatch")
    require(value["source"]["sha256_before"] == independent.SOURCE_SHA256 and
            value["source"]["sha256_after"] == independent.SOURCE_SHA256 and
            value["source"]["opened_read_only"] is True and
            value["source"]["modified"] is False,
            "writer manifest source safety mismatch")
    require(value["output"]["sha256"] == OUTPUT_SHA256 and
            value["output"]["exclusively_created"] is True and
            value["output"]["distinct_from_source_inode"] is True,
            "writer manifest output identity mismatch")
    require(value["source"]["device"] == source.stat().st_dev and
            value["source"]["inode"] == source.stat().st_ino and
            value["output"]["device"] == output.stat().st_dev and
            value["output"]["inode"] == output.stat().st_ino and
            value["replacement"]["device"] == replacement.stat().st_dev and
            value["replacement"]["inode"] == replacement.stat().st_ino,
            "writer manifest inode identity changed")
    require(value["replacement"]["sha256"] == REPLACEMENT_SPAN_SHA256 and
            value["replacement"]["decoded_sha256"] == REPLACEMENT_DECODED_SHA256 and
            value["replacement"]["import_manifest_sha256"] == IMPORT_MANIFEST_SHA256 and
            Path(value["replacement"]["import_manifest_path"]).resolve() ==
            import_manifest.resolve() and
            value["replacement"]["input_png_sha256"] == INPUT_PNG_SHA256,
            "writer replacement provenance mismatch")
    patch = value["patch"]
    require(patch["target_resource"] == "09H0.IFF" and
            patch["target_outer_index"] == 3685 and
            patch["target_chunk_index"] == 1 and
            patch["absolute_span_offset"] == TARGET_ABSOLUTE and
            patch["span_size"] == SPAN_SIZE and
            patch["source_span_sha256"] == SOURCE_SPAN_SHA256 and
            patch["replacement_span_sha256"] == REPLACEMENT_SPAN_SHA256 and
            patch["complete_wrapper_preserved"] is True,
            "writer patch target mismatch")
    require(patch["relative_changed_byte_count"] == RELATIVE_DIFF_COUNT and
            patch["relative_changed_offsets_u32le_sha256"] ==
            RELATIVE_DIFF_U32LE_SHA256 and
            patch["relative_changed_run_count"] == RELATIVE_RUN_COUNT and
            patch["relative_changed_runs_u32le_sha256"] ==
            RELATIVE_RUN_U32LE_SHA256 and
            patch["actual_changed_byte_count"] == RELATIVE_DIFF_COUNT and
            patch["actual_changed_offsets_u64le_sha256"] ==
            ABSOLUTE_DIFF_U64LE_SHA256 and
            patch["all_other_image_bytes_identical"] is True,
            "writer full-image difference proof mismatch")
    require(patch["source_pack_a_sha256"] == PACK_A_SHA256 and
            patch["output_pack_a_sha256"] == OUTPUT_PACK_A_SHA256 and
            patch["unrelated_pack_b_sha256"] == PACK_B_SHA256 and
            patch["unrelated_pack0_sha256"] == PACK0_SHA256,
            "writer pack hashes mismatch")
    require(value["probe"]["emulator_started"] is False and
            value["probe"]["runtime_result"] is None and
            value["claims"]["png_derived_tset_inserted"] is True and
            value["claims"]["runtime_visibility_proved"] is False and
            value["claims"]["xemu_started"] is False and
            value["claims"]["title_executed"] is False,
            "writer runtime/scope mismatch")


def validate_imported_mips(decoded: bytes, import_manifest: Path,
                           input_png: Path, previews: Path) -> None:
    require(sha256_bytes(decoded) == REPLACEMENT_DECODED_SHA256,
            "XISO target decoded hash mismatch")
    png_verify.validate_descriptors(decoded)
    _, clean_levels, mud_levels = png_verify.decode_mips(decoded)
    manifest = png_verify.validate_manifest(import_manifest)
    require(png_verify.sha256_file(input_png) == INPUT_PNG_SHA256,
            "input diagnostic PNG hash mismatch")
    input_rgba = png_verify.parse_deterministic_png(input_png.read_bytes(), 512, 256)
    require(clean_levels[0] == input_rgba,
            "XISO-extracted clean base differs from input PNG")
    current = input_rgba
    for level in range(1, 6):
        width, height = png_verify.MIP_DIMENSIONS[level - 1]
        current = png_verify.downsample(current, width, height)
        require(clean_levels[level] == current,
                f"XISO-extracted clean mip {level} mismatch")
    rows = {(row["role"], row["level"]): row for row in manifest["previews"]}
    for role, levels in (("clean", clean_levels), ("mud", mud_levels)):
        for level, rgba in enumerate(levels):
            width, height = png_verify.MIP_DIMENSIONS[level]
            name = f"{role}_mip{level}_{width}x{height}.png"
            path = previews / name
            require(path.exists() and path.is_file() and not path.is_symlink(),
                    f"canonical preview absent: {name}")
            payload = path.read_bytes()
            require(png_verify.parse_deterministic_png(payload, width, height) == rgba,
                    f"XISO-extracted mip differs from preview: {name}")
            row = rows[role, level]
            require(row["png_sha256"] == sha256_bytes(payload) and
                    row["rgba_sha256"] == sha256_bytes(rgba),
                    f"preview manifest hash mismatch: {name}")


def run(source: Path, output: Path, writer_manifest: Path, canonical_report: Path,
        replacement: Path, import_manifest: Path, input_png: Path, previews: Path,
        index: Path, extract_xiso: Path) -> None:
    for role, path in (("source", source), ("output", output),
                       ("replacement", replacement), ("import manifest", import_manifest),
                       ("writer manifest", writer_manifest),
                       ("canonical report", canonical_report)):
        require(path.exists() and not path.is_symlink(), f"{role} invalid")
        require(stat.S_ISREG(path.stat().st_mode), f"{role} is not regular")
    require(source.stat().st_size == output.stat().st_size == independent.IMAGE_SIZE,
            "source/output image size mismatch")
    require((source.stat().st_dev, source.stat().st_ino) !=
            (output.stat().st_dev, output.stat().st_ino),
            "source/output inode alias")
    require(extract_xiso.is_file() and os.access(extract_xiso, os.X_OK),
            "pinned extract-xiso binary missing")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    output_fd = os.open(output, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        source_entries, source_root, source_dirs = independent.parse_xdvdfs(
            source_fd, independent.IMAGE_SIZE
        )
        output_entries, output_root, output_dirs = independent.parse_xdvdfs(
            output_fd, independent.IMAGE_SIZE
        )
        independent.validate_expected_entries(source_entries)
        independent.validate_expected_entries(output_entries)
        require(source_entries == output_entries and source_root == output_root and
                source_dirs == output_dirs == [(33, 108), (35_530, 2_048)],
                "XDVDFS tree/extent metadata changed")
        require(independent.pread_exact(source_fd, independent.VOLUME_OFFSET,
                                       independent.VOLUME_SIZE) ==
                independent.pread_exact(output_fd, independent.VOLUME_OFFSET,
                                        independent.VOLUME_SIZE),
                "XDVDFS volume descriptor changed")
        for sector, size in source_dirs:
            require(independent.pread_exact(source_fd, sector * independent.SECTOR, size) ==
                    independent.pread_exact(output_fd, sector * independent.SECTOR, size),
                    f"XDVDFS directory bytes changed at sector {sector}")

        source_sha, output_sha, differences = scan_images(source_fd, output_fd)
        require(source_sha == independent.SOURCE_SHA256 and output_sha == OUTPUT_SHA256,
                "full-image source/output hash mismatch")
        require(len(differences) == RELATIVE_DIFF_COUNT,
                "full-image changed-byte count mismatch")
        relative = [value - TARGET_ABSOLUTE for value in differences]
        require(all(0 <= value < SPAN_SIZE for value in relative),
                "changed byte outside target span")
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
        require(pack_a.offset + TARGET_OUTER_PACK_OFFSET + TARGET_CHUNK_OFFSET
                == TARGET_ABSOLUTE, "target absolute arithmetic mismatch")
        source_span = independent.pread_exact(source_fd, TARGET_ABSOLUTE, SPAN_SIZE)
        output_span = independent.pread_exact(output_fd, TARGET_ABSOLUTE, SPAN_SIZE)
        require(sha256_bytes(source_span) == SOURCE_SPAN_SHA256 and
                sha256_bytes(output_span) == REPLACEMENT_SPAN_SHA256 and
                output_span == replacement.read_bytes(),
                "source/output/replacement span mismatch")
        require(png_verify.read_retail_span(index) == source_span,
                "extracted retail archive/XISO target disagreement")
        require(source_span[:HEADER.size] == output_span[:HEADER.size],
                "TSET wrapper changed")
        decoded, metrics = independent_decode(output_span[HEADER.size:])
        require(metrics == {
            "consumed_bytes": 22285,
            "literal_count": 609,
            "match_count": 10160,
            "maximum_distance": 4056,
            "maximum_length": 18,
        }, "XISO target independent decode metrics mismatch")
        require(output_span[HEADER.size + 22285:] == bytes(52403),
                "XISO target unused stored tail is not zero")
        validate_imported_mips(decoded, import_manifest, input_png, previews)

        # Re-extract the exact target span through an O_EXCL scratch file, then
        # re-read it before accepting the direct pread result.
        with tempfile.TemporaryDirectory(prefix="nfl-png-xiso-extract-") as temp:
            extracted = Path(temp) / "vc_53450030_A_09H0_chunk1.tset.bin"
            descriptor = os.open(extracted, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                position = 0
                while position < len(output_span):
                    written = os.write(descriptor, output_span[position:])
                    require(written > 0, "short extracted-span write")
                    position += written
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            require(extracted.read_bytes() == output_span and
                    sha256_bytes(extracted.read_bytes()) == REPLACEMENT_SPAN_SHA256,
                    "re-extracted output span mismatch")

        require(independent.hash_extent(source_fd, pack_a.offset, pack_a.size)
                == PACK_A_SHA256 and
                independent.hash_extent(output_fd, pack_a.offset, pack_a.size)
                == OUTPUT_PACK_A_SHA256, "pack A hashes mismatch")
        require(independent.hash_extent(source_fd, pack_b.offset, pack_b.size)
                == PACK_B_SHA256 and
                independent.hash_extent(output_fd, pack_b.offset, pack_b.size)
                == PACK_B_SHA256, "unrelated pack B changed")
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
    require(source_listing == output_listing and len(source_listing) == 20 and
            source_total == output_total == independent.EXPECTED_TOTAL_FILE_BYTES,
            "extract-xiso listing/layout mismatch")
    validate_writer_manifest(writer_manifest, source, output, replacement, import_manifest)
    validate_writer_manifest(canonical_report, source, output, replacement, import_manifest)
    require(writer_manifest.read_bytes() == canonical_report.read_bytes(),
            "canonical report differs from O_EXCL writer manifest")
    print(
        "NFL_TSET_PNG_IMPORT_XISO_DIRECT_VERIFY_PASS "
        f"source_sha={independent.SOURCE_SHA256} output_sha={OUTPUT_SHA256} "
        f"span_sha={REPLACEMENT_SPAN_SHA256} target=09H0 chunk=1 "
        "changed_bytes=70333 runs=3265 files=19 root_sector=33 layout=identical "
        "decoded=177024 encoded=22285/74688 zero_pad=52403 colors=32 mips=6 "
        f"previews=12 xbe=unchanged pack0=unchanged runtime=false "
        f"extract_xiso='{banner}'"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--writer-manifest", required=True, type=Path)
    parser.add_argument("--canonical-report", required=True, type=Path)
    parser.add_argument("--replacement-span", required=True, type=Path)
    parser.add_argument("--import-manifest", required=True, type=Path)
    parser.add_argument("--input-png", required=True, type=Path)
    parser.add_argument("--previews", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--extract-xiso", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.source, args.output, args.writer_manifest, args.canonical_report,
            args.replacement_span, args.import_manifest, args.input_png,
            args.previews, args.index, args.extract_xiso)
    except (OSError, independent.VerifyError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
