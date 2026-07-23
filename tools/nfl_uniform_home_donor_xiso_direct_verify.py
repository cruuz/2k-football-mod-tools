#!/usr/bin/env python3
"""Independently verify the one-word NFL 2K5 retail-donor XISO probe.

This verifier does not import the donor writer.  It reuses the separately
implemented XDVDFS parser from the independent magenta-artifact verifier,
rescans both complete 6.30 GB images, validates the exact ``Unif`` bodies,
and compares pinned extract-xiso listings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

import nfl_uniform_color_xiso_direct_verify as independent


SCHEMA = "nfl2k5_uniform_home_donor_xiso_direct_patch/v1"
OUTPUT_SHA256 = "2f0ce4d4ac26c864a274c47f7147c45df1ecbf22d05d169f3940706eb64f3702"
OUTPUT_PACK_A_SHA256 = "7fcd465e60408a88d5a6c42739ceb7d2b8aa54143e9833bc72b80c0ee0b9efbe"
PACK_A_SHA256 = "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b"
PACK_B_SHA256 = "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
TARGET_OUTER_PACK_OFFSET = 0x055CA800
DONOR_OUTER_PACK_OFFSET = 0x00E0A800
WRAPPER = b"Unif" + (0x50).to_bytes(4, "little") + bytes(0x18)
TARGET_BODY = bytes.fromhex(
    "000000000000000000000000556e6966110000001d0000000000000000000000"
    "75006e00690066006f0072006d000000000000ffaf5a38ff0100000000000000"
    "0000803f010000000000000000000000"
)
DONOR_BODY = bytes.fromhex(
    "000000000000000000000000556e6966110000001d0000000000000000000000"
    "75006e00690066006f0072006d000000000000ff1c1a88ff0100000000000000"
    "0000803f010000000000000000000000"
)
TARGET_BODY_SHA256 = "54a25776a10aac769cb3e299ff950b4dcb6f79e030be8fc0e68a8bfb19a56b53"
DONOR_BODY_SHA256 = "c6841e43cbe253347ceab9043edade498821a4cea080a97e3e8f0522b1285d37"
PATCH_ABSOLUTE = 5_011_470_420
DIFFERENCES = [5_011_470_420, 5_011_470_421, 5_011_470_422]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise independent.VerifyError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_manifest(
    path: Path,
    source: Path,
    output: Path,
    differences: list[int],
) -> None:
    require(path.exists() and not path.is_symlink(), "manifest must be a non-symlink file")
    value = json.loads(path.read_bytes())
    require(value.get("schema") == SCHEMA, "manifest schema mismatch")
    require(Path(value["source"]["path"]).resolve() == source.resolve(),
            "manifest source path mismatch")
    require(Path(value["output"]["path"]).resolve() == output.resolve(),
            "manifest output path mismatch")
    require(value["source"]["sha256_before"] == independent.SOURCE_SHA256 and
            value["source"]["sha256_after"] == independent.SOURCE_SHA256,
            "manifest retail hash mismatch")
    require(value["source"]["opened_read_only"] is True and
            value["source"]["modified"] is False,
            "manifest source-safety claim mismatch")
    require(value["output"]["sha256"] == OUTPUT_SHA256,
            "manifest output hash mismatch")
    require(value["source"]["device"] == source.stat().st_dev and
            value["source"]["inode"] == source.stat().st_ino,
            "source identity changed since writer run")
    require(value["output"]["device"] == output.stat().st_dev and
            value["output"]["inode"] == output.stat().st_ino,
            "output identity changed since writer run")
    require(value["output"]["exclusively_created"] is True and
            value["output"]["distinct_from_source_inode"] is True,
            "manifest O_EXCL/inode claim missing")

    patch = value["patch"]
    require(patch["actual_changed_byte_count"] == 3 and
            patch["actual_changed_byte_offsets"] == differences and
            patch["allowed_changed_byte_offsets"] == differences,
            "manifest difference ledger mismatch")
    require(patch["all_other_image_bytes_identical"] is True,
            "manifest image-identity claim missing")
    require(patch["target_complete_body_equals_pinned_donor"] is True and
            patch["target_complete_body_size"] == 0x50 and
            bytes.fromhex(patch["target_complete_body_hex"]) == DONOR_BODY,
            "manifest donor-body equality proof mismatch")
    require(patch["target"]["resource"] == "09H0.IFF" and
            patch["target"]["absolute_patch_offset"] == PATCH_ABSOLUTE and
            patch["target"]["source_body_sha256"] == TARGET_BODY_SHA256 and
            patch["target"]["patched_body_sha256"] == DONOR_BODY_SHA256 and
            patch["target"]["source_color_word_1"] == "0xff385aaf" and
            patch["target"]["patched_color_word_1"] == "0xff881a1c",
            "manifest target record mismatch")
    require(patch["donor"]["resource"] == "27H0.IFF" and
            patch["donor"]["body_sha256"] == DONOR_BODY_SHA256 and
            patch["donor"]["color_word_1"] == "0xff881a1c" and
            patch["donor"]["unchanged_in_output"] is True,
            "manifest donor record mismatch")
    require(patch["source_pack_a_sha256"] == PACK_A_SHA256 and
            patch["output_pack_a_sha256"] == OUTPUT_PACK_A_SHA256 and
            patch["unrelated_pack_b_sha256"] == PACK_B_SHA256 and
            patch["unrelated_pack0_sha256"] == PACK0_SHA256,
            "manifest package hashes mismatch")
    require(value["probe"]["emulator_started"] is False and
            value["probe"]["runtime_result"] is None and
            value["claims"]["runtime_visibility_proved"] is False and
            value["claims"]["reset_cause_proved"] is False,
            "manifest overclaims a runtime result")


def run(source: Path, output: Path, manifest: Path, extract_xiso: Path) -> None:
    for role, path in (("source", source), ("output", output)):
        require(path.exists() and not path.is_symlink(),
                f"{role} must be a non-symlink file")
        info = path.stat()
        require(stat.S_ISREG(info.st_mode), f"{role} is not a regular file")
        require(info.st_size == independent.IMAGE_SIZE, f"{role} size mismatch")
    require((source.stat().st_dev, source.stat().st_ino) !=
            (output.stat().st_dev, output.stat().st_ino),
            "source and output alias the same inode")
    require(extract_xiso.is_file() and os.access(extract_xiso, os.X_OK),
            "pinned extract-xiso binary missing")
    require(sha256_bytes(TARGET_BODY) == TARGET_BODY_SHA256 and
            sha256_bytes(DONOR_BODY) == DONOR_BODY_SHA256,
            "frozen body constants fail their SHA-256 pins")
    require([i for i, pair in enumerate(zip(TARGET_BODY, DONOR_BODY))
             if pair[0] != pair[1]] == [0x34, 0x35, 0x36],
            "frozen bodies do not differ at exactly the donor RGB bytes")

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

        source_sha, output_sha, differences = independent.scan_images(source_fd, output_fd)
        require(source_sha == independent.SOURCE_SHA256, "retail source SHA-256 mismatch")
        require(output_sha == OUTPUT_SHA256, "donor-probe output SHA-256 mismatch")
        require(differences == DIFFERENCES,
                "full-image differences are not the exact three-byte donor patch")

        pack_a = source_entries["vc_53450030/a"]
        pack_b = source_entries["vc_53450030/b"]
        pack0 = source_entries["vc_53450030/0"]
        xbe = source_entries["default.xbe"]
        target_outer = pack_a.offset + TARGET_OUTER_PACK_OFFSET
        donor_outer = pack_b.offset + DONOR_OUTER_PACK_OFFSET
        target_body = target_outer + 0x20
        donor_body = donor_outer + 0x20
        require(target_body + 0x34 == PATCH_ABSOLUTE,
                "target absolute patch arithmetic mismatch")
        require(independent.pread_exact(source_fd, target_outer, 0x20) == WRAPPER and
                independent.pread_exact(output_fd, target_outer, 0x20) == WRAPPER,
                "target Unif wrapper changed")
        require(independent.pread_exact(source_fd, donor_outer, 0x20) == WRAPPER and
                independent.pread_exact(output_fd, donor_outer, 0x20) == WRAPPER,
                "donor Unif wrapper changed")
        require(independent.pread_exact(source_fd, target_body, 0x50) == TARGET_BODY,
                "source target 09H0 body mismatch")
        require(independent.pread_exact(output_fd, target_body, 0x50) == DONOR_BODY,
                "output target body is not exactly the pinned 27H0 donor body")
        require(independent.pread_exact(source_fd, donor_body, 0x50) == DONOR_BODY and
                independent.pread_exact(output_fd, donor_body, 0x50) == DONOR_BODY,
                "27H0 donor body changed")
        require(independent.pread_exact(source_fd, PATCH_ABSOLUTE, 4)
                == bytes.fromhex("af5a38ff") and
                independent.pread_exact(output_fd, PATCH_ABSOLUTE, 4)
                == bytes.fromhex("1c1a88ff"),
                "color_word_1 before/after bytes mismatch")

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
    require(source_listing == output_listing, "extract-xiso listings differ")
    require(len(source_listing) == 20, "extract-xiso did not list 19 files plus directory")
    require(source_total == output_total == independent.EXPECTED_TOTAL_FILE_BYTES,
            "extract-xiso total byte count mismatch")
    validate_manifest(manifest, source, output, DIFFERENCES)

    print(
        "NFL_UNIFORM_HOME_DONOR_XISO_DIRECT_VERIFY_PASS "
        f"source_sha={independent.SOURCE_SHA256} output_sha={OUTPUT_SHA256} "
        "files=19 entries=20 root_sector=33 target=09H0 donor=27H0 "
        f"target_body_sha={DONOR_BODY_SHA256} changed_bytes=3 "
        f"layout=identical source=unchanged xbe=unchanged pack0=unchanged "
        f"packB=unchanged runtime_visibility=false extract_xiso='{banner}'"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--extract-xiso", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.source, args.output, args.manifest, args.extract_xiso)
    except (OSError, independent.VerifyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
