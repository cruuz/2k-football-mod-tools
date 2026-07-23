#!/usr/bin/env python3
"""Create a sector-identical NFL 2K5 XISO with one retail HOME color pair.

This deliberately narrow probe changes only the two packed color words in
Lions current HOME resource ``09H0.IFF``.  The complete pair is copied from
San Francisco current HOME resource ``25H0.IFF``.  The resulting 0x50-byte
target body is byte-identical to that shipped donor; every other XISO byte
must compare identical to the pinned retail image.

The source is opened read-only and without symlink traversal.  Output and
manifest files are exclusively created and are deleted on any failed check.
No emulator is started by this program.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

# Reuse only the audited read/parse/hash/O_EXCL primitives.  This probe has its
# own copy loop, frozen resource bodies, patch policy, and manifest schema; it
# does not alter or relax the existing synthetic-magenta writer or validator.
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_uniform_home_pair_donor_xiso_direct_patch/v1"
PROBE_NAME = "lions_09H0_complete_color_pair_from_49ers_25H0"

PACK_A_PATH = "vc_53450030/A"
PACK_A_SECTOR = 2_403_082
PACK_A_SIZE = 310_294_528
PACK_A_SHA256 = "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b"
PACK_B_PATH = "vc_53450030/B"
PACK_B_SECTOR = 2_179_328
PACK_B_SIZE = 458_248_192
PACK_B_SHA256 = "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614"
PACK0_PATH = "vc_53450030/0"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"

TARGET_RESOURCE = "09H0.IFF"
TARGET_OUTER_ID = 0x9A4832D6
TARGET_OUTER_PACK_OFFSET = 0x055CA800
DONOR_RESOURCE = "25H0.IFF"
DONOR_OUTER_ID = 0x371D8698
DONOR_OUTER_PACK_OFFSET = 0x00560000

UNIF_WRAPPER_SIZE = 0x20
UNIF_BODY_SIZE = 0x50
UNIF_WRAPPER = b"Unif" + struct.pack("<I", UNIF_BODY_SIZE) + bytes(0x18)
COLOR_PAIR_BODY_OFFSET = 0x30
COLOR_PAIR_SIZE = 8
TARGET_PATCH_PACK_OFFSET = (
    TARGET_OUTER_PACK_OFFSET + UNIF_WRAPPER_SIZE + COLOR_PAIR_BODY_OFFSET
)
TARGET_ABSOLUTE_PATCH_OFFSET = 5_011_470_416

TARGET_COLOR_PAIR = struct.pack("<II", 0xFF000000, 0xFF385AAF)
DONOR_COLOR_PAIR = struct.pack("<II", 0xFF9C1622, 0xFF88172D)
TARGET_BODY = bytes.fromhex(
    "000000000000000000000000556e6966110000001d0000000000000000000000"
    "75006e00690066006f0072006d000000000000ffaf5a38ff0100000000000000"
    "0000803f010000000000000000000000"
)
DONOR_BODY = bytes.fromhex(
    "000000000000000000000000556e6966110000001d0000000000000000000000"
    "75006e00690066006f0072006d00000022169cff2d1788ff0100000000000000"
    "0000803f010000000000000000000000"
)
TARGET_BODY_SHA256 = "54a25776a10aac769cb3e299ff950b4dcb6f79e030be8fc0e68a8bfb19a56b53"
DONOR_BODY_SHA256 = "8d176356012bcb041035fa0b6eb992d67b701e2fab3a7e88d6547e3da195b74a"
EXPECTED_BODY_DIFFS = [0x30, 0x31, 0x32, 0x34, 0x35, 0x36]
EXPECTED_ABSOLUTE_DIFFS = [
    5_011_470_416,
    5_011_470_417,
    5_011_470_418,
    5_011_470_420,
    5_011_470_421,
    5_011_470_422,
]
COPY_CHUNK = 32 * 1024 * 1024


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_new_path(path: Path) -> Path:
    """Resolve an already-existing parent without following a final symlink."""
    common.require(path.name not in {"", ".", ".."}, "invalid output filename")
    parent = path.parent.resolve(strict=True)
    common.require(parent.is_dir(), f"output parent is not a directory: {parent}")
    return parent / path.name


def copy_fd_exact(source: int, output: int, size: int) -> str:
    """Copy every source byte once, falling back to positional I/O."""
    position = 0
    method = "copy_file_range"
    while position < size:
        request = min(COPY_CHUNK, size - position)
        try:
            copied = os.copy_file_range(source, output, request, position, position)
        except OSError as exc:
            if exc.errno not in {
                errno.EXDEV,
                errno.EINVAL,
                errno.ENOSYS,
                errno.EOPNOTSUPP,
            }:
                raise
            method = "pread_pwrite"
            break
        common.require(copied > 0, "short copy_file_range result")
        position += copied

    while position < size:
        chunk = os.pread(source, min(COPY_CHUNK, size - position), position)
        common.require(chunk, "short source read while copying XISO")
        written = 0
        while written < len(chunk):
            amount = os.pwrite(output, chunk[written:], position + written)
            common.require(amount > 0, "short destination write while copying XISO")
            written += amount
        position += len(chunk)
    common.require(os.fstat(output).st_size == size, "copied XISO size mismatch")
    return method


def validate_frozen_constants() -> None:
    common.require(len(TARGET_BODY) == UNIF_BODY_SIZE, "target body constant size mismatch")
    common.require(len(DONOR_BODY) == UNIF_BODY_SIZE, "donor body constant size mismatch")
    common.require(sha256_bytes(TARGET_BODY) == TARGET_BODY_SHA256,
                   "target body constant hash mismatch")
    common.require(sha256_bytes(DONOR_BODY) == DONOR_BODY_SHA256,
                   "donor body constant hash mismatch")
    body_diffs = [
        index for index, (before, after) in enumerate(zip(TARGET_BODY, DONOR_BODY))
        if before != after
    ]
    common.require(body_diffs == EXPECTED_BODY_DIFFS,
                   "frozen retail bodies no longer differ at exactly six RGB bytes")
    common.require(
        TARGET_BODY[COLOR_PAIR_BODY_OFFSET:COLOR_PAIR_BODY_OFFSET + COLOR_PAIR_SIZE]
        == TARGET_COLOR_PAIR,
        "target body color-pair constant mismatch",
    )
    common.require(
        DONOR_BODY[COLOR_PAIR_BODY_OFFSET:COLOR_PAIR_BODY_OFFSET + COLOR_PAIR_SIZE]
        == DONOR_COLOR_PAIR,
        "donor body color-pair constant mismatch",
    )


def run(source_path: Path, output_path: Path, manifest_path: Path) -> dict[str, object]:
    validate_frozen_constants()
    try:
        supplied_source_info = source_path.lstat()
    except FileNotFoundError as exc:
        raise common.PatchError(f"source does not exist: {source_path}") from exc
    common.require(not stat.S_ISLNK(supplied_source_info.st_mode),
                   "source pathname must not be a symbolic link")
    source = source_path.resolve(strict=True)
    output = canonical_new_path(output_path)
    manifest = canonical_new_path(manifest_path)
    common.require(source.is_file() and not source.is_symlink(),
                   "source must be a regular non-symlink file")
    common.require(not output.exists(), f"output already exists: {output}")
    common.require(not manifest.exists(), f"manifest already exists: {manifest}")
    common.require(output != source and manifest != source and output != manifest,
                   "source, output, and manifest paths must be distinct")

    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    success = False
    try:
        source_info = os.fstat(source_fd)
        common.require(stat.S_ISREG(source_info.st_mode), "source descriptor is not regular")
        common.require(source_info.st_size == common.EXPECTED_XISO_SIZE,
                       "retail XISO size mismatch")
        source_identity = common.fd_identity(source_fd)
        common.require(common.path_identity(source) == source_identity,
                       "source pathname changed before validation")
        source_sha_before = common.sha256_fd(source_fd)
        common.require(source_sha_before == common.EXPECTED_XISO_SHA256,
                       "retail XISO SHA-256 mismatch")

        entries, directory = common.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        common.require(len(files) == 19, f"expected 19 XDVDFS files, found {len(files)}")
        xbe = entries.get("default.xbe")
        common.require(xbe is not None and xbe.size == common.EXPECTED_XBE_SIZE,
                       "default.xbe extent mismatch")
        common.require(
            common.sha256_fd(source_fd, xbe.byte_offset, xbe.size)
            == common.EXPECTED_XBE_SHA256,
            "default.xbe SHA-256 mismatch",
        )

        pack_a = entries.get(PACK_A_PATH.casefold())
        pack_b = entries.get(PACK_B_PATH.casefold())
        pack0 = entries.get(PACK0_PATH.casefold())
        common.require(pack_a is not None and
                       (pack_a.sector, pack_a.size) == (PACK_A_SECTOR, PACK_A_SIZE),
                       "pack A extent mismatch")
        common.require(pack_b is not None and
                       (pack_b.sector, pack_b.size) == (PACK_B_SECTOR, PACK_B_SIZE),
                       "pack B extent mismatch")
        common.require(pack0 is not None, "pack 0 missing")
        common.require(common.sha256_fd(source_fd, pack_a.byte_offset, pack_a.size)
                       == PACK_A_SHA256, "retail pack A SHA-256 mismatch")
        common.require(common.sha256_fd(source_fd, pack_b.byte_offset, pack_b.size)
                       == PACK_B_SHA256, "retail pack B SHA-256 mismatch")
        common.require(common.sha256_fd(source_fd, pack0.byte_offset, pack0.size)
                       == PACK0_SHA256, "retail pack 0 SHA-256 mismatch")

        target_outer_absolute = pack_a.byte_offset + TARGET_OUTER_PACK_OFFSET
        donor_outer_absolute = pack_b.byte_offset + DONOR_OUTER_PACK_OFFSET
        target_body_absolute = target_outer_absolute + UNIF_WRAPPER_SIZE
        donor_body_absolute = donor_outer_absolute + UNIF_WRAPPER_SIZE
        patch_absolute = target_body_absolute + COLOR_PAIR_BODY_OFFSET
        common.require(patch_absolute == TARGET_ABSOLUTE_PATCH_OFFSET,
                       "target absolute patch offset arithmetic mismatch")
        common.require(
            common.read_exact(source_fd, target_outer_absolute, UNIF_WRAPPER_SIZE)
            == UNIF_WRAPPER,
            "target Unif wrapper mismatch",
        )
        common.require(
            common.read_exact(source_fd, donor_outer_absolute, UNIF_WRAPPER_SIZE)
            == UNIF_WRAPPER,
            "donor Unif wrapper mismatch",
        )
        source_target_body = common.read_exact(
            source_fd, target_body_absolute, UNIF_BODY_SIZE
        )
        source_donor_body = common.read_exact(
            source_fd, donor_body_absolute, UNIF_BODY_SIZE
        )
        common.require(source_target_body == TARGET_BODY and
                       sha256_bytes(source_target_body) == TARGET_BODY_SHA256,
                       "retail target 09H0 Unif body mismatch")
        common.require(source_donor_body == DONOR_BODY and
                       sha256_bytes(source_donor_body) == DONOR_BODY_SHA256,
                       "retail donor 25H0 Unif body mismatch")
        common.require(common.read_exact(source_fd, patch_absolute, COLOR_PAIR_SIZE)
                       == TARGET_COLOR_PAIR,
                       "retail target color-pair mismatch")

        expected_absolute_diffs = [
            patch_absolute + index
            for index, (before, after) in enumerate(
                zip(TARGET_COLOR_PAIR, DONOR_COLOR_PAIR)
            )
            if before != after
        ]
        common.require(expected_absolute_diffs == EXPECTED_ABSOLUTE_DIFFS,
                       "replacement no longer has the frozen six-byte delta")
        allowed_changed_offsets = set(expected_absolute_diffs)

        output_owned = common.reserve_file(output)
        common.require(common.fd_identity(output_owned.descriptor) != source_identity,
                       "output unexpectedly aliases source inode")
        copy_method = copy_fd_exact(source_fd, output_owned.descriptor, source_info.st_size)
        common.require(common.owned_path_matches(output_owned),
                       "output pathname changed during copy")
        written = os.pwrite(output_owned.descriptor, DONOR_COLOR_PAIR, patch_absolute)
        common.require(written == COLOR_PAIR_SIZE,
                       f"short donor-pair write at 0x{patch_absolute:x}")
        common.require(
            common.read_exact(output_owned.descriptor, patch_absolute, COLOR_PAIR_SIZE)
            == DONOR_COLOR_PAIR,
            "donor color-pair readback mismatch",
        )

        output_target_body = common.read_exact(
            output_owned.descriptor, target_body_absolute, UNIF_BODY_SIZE
        )
        output_donor_body = common.read_exact(
            output_owned.descriptor, donor_body_absolute, UNIF_BODY_SIZE
        )
        common.require(output_target_body == DONOR_BODY,
                       "patched target body does not exactly equal pinned donor body")
        common.require(sha256_bytes(output_target_body) == DONOR_BODY_SHA256,
                       "patched target donor-body SHA-256 mismatch")
        common.require(output_donor_body == DONOR_BODY,
                       "source donor body changed unexpectedly")
        os.fsync(output_owned.descriptor)
        common.require(common.owned_path_matches(output_owned),
                       "output pathname changed during patch")
        common.require(common.path_identity(source) == source_identity,
                       "source pathname changed during run")

        source_sha_after, output_sha, differences = common.compare_and_hash(
            source_fd,
            output_owned.descriptor,
            source_info.st_size,
            allowed_changed_offsets,
        )
        common.require(source_sha_after == source_sha_before,
                       "retail source XISO changed during run")
        common.require(differences == EXPECTED_ABSOLUTE_DIFFS,
                       "full-image difference ledger mismatch")
        common.require(common.path_identity(source) == source_identity,
                       "source pathname changed after full comparison")
        common.require(common.owned_path_matches(output_owned),
                       "output pathname changed after full comparison")

        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        common.require(output_directory == directory, "XDVDFS directory metadata changed")
        common.require(output_entries == entries, "XDVDFS directory tree changed")
        output_pack_a_sha = common.sha256_fd(
            output_owned.descriptor, pack_a.byte_offset, pack_a.size
        )
        common.require(common.sha256_fd(output_owned.descriptor,
                                       pack_b.byte_offset, pack_b.size) == PACK_B_SHA256,
                       "unrelated pack B changed")
        common.require(common.sha256_fd(output_owned.descriptor,
                                       pack0.byte_offset, pack0.size) == PACK0_SHA256,
                       "unrelated pack 0 changed")
        common.require(common.sha256_fd(output_owned.descriptor,
                                       xbe.byte_offset, xbe.size)
                       == common.EXPECTED_XBE_SHA256, "default.xbe changed")

        result: dict[str, object] = {
            "schema": SCHEMA,
            "probe": {
                "name": PROBE_NAME,
                "purpose": (
                    "Visible ownership probe: replace only the Lions current HOME "
                    "two-color pair with the complete known-retail 49ers current "
                    "HOME pair, yielding a donor-exact Unif body."
                ),
                "emulator_started": False,
                "runtime_result": None,
            },
            "source": {
                "path": str(source),
                "size": source_info.st_size,
                "sha256_before": source_sha_before,
                "sha256_after": source_sha_after,
                "device": source_identity[0],
                "inode": source_identity[1],
                "opened_read_only": True,
                "modified": False,
            },
            "output": {
                "path": str(output),
                "size": os.fstat(output_owned.descriptor).st_size,
                "sha256": output_sha,
                "copy_method": copy_method,
                "device": output_owned.identity[0],
                "inode": output_owned.identity[1],
                "exclusively_created": True,
                "distinct_from_source_inode": True,
            },
            "xdvdfs": {
                **directory,
                "file_count": len(files),
                "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
            },
            "patch": {
                "target": {
                    "resource": TARGET_RESOURCE,
                    "outer_id": f"0x{TARGET_OUTER_ID:08x}",
                    "pack_path": pack_a.path,
                    "pack_start_sector": pack_a.sector,
                    "outer_pack_offset": TARGET_OUTER_PACK_OFFSET,
                    "body_pack_offset": TARGET_OUTER_PACK_OFFSET + UNIF_WRAPPER_SIZE,
                    "color_pair_pack_offset": TARGET_PATCH_PACK_OFFSET,
                    "absolute_patch_offset": patch_absolute,
                    "source_body_sha256": TARGET_BODY_SHA256,
                    "patched_body_sha256": sha256_bytes(output_target_body),
                    "source_color_word_0": "0xff000000",
                    "source_color_word_1": "0xff385aaf",
                    "patched_color_word_0": "0xff9c1622",
                    "patched_color_word_1": "0xff88172d",
                    "source_color_pair_le_hex": TARGET_COLOR_PAIR.hex(),
                    "patched_color_pair_le_hex": DONOR_COLOR_PAIR.hex(),
                },
                "donor": {
                    "resource": DONOR_RESOURCE,
                    "outer_id": f"0x{DONOR_OUTER_ID:08x}",
                    "pack_path": pack_b.path,
                    "pack_start_sector": pack_b.sector,
                    "outer_pack_offset": DONOR_OUTER_PACK_OFFSET,
                    "body_pack_offset": DONOR_OUTER_PACK_OFFSET + UNIF_WRAPPER_SIZE,
                    "body_sha256": DONOR_BODY_SHA256,
                    "color_word_0": "0xff9c1622",
                    "color_word_1": "0xff88172d",
                    "color_pair_le_hex": DONOR_COLOR_PAIR.hex(),
                    "unchanged_in_output": True,
                },
                "target_complete_body_equals_pinned_donor": True,
                "target_complete_body_size": UNIF_BODY_SIZE,
                "target_complete_body_hex": output_target_body.hex(),
                "allowed_changed_byte_offsets": EXPECTED_ABSOLUTE_DIFFS,
                "actual_changed_byte_offsets": differences,
                "actual_changed_byte_count": len(differences),
                "all_other_image_bytes_identical": True,
                "source_pack_a_sha256": PACK_A_SHA256,
                "output_pack_a_sha256": output_pack_a_sha,
                "unrelated_pack_b_sha256": PACK_B_SHA256,
                "unrelated_pack0_sha256": PACK0_SHA256,
            },
            "claims": {
                "layout_identical_copy_only_xiso": True,
                "known_retail_donor_pair_only": True,
                "away_resource_edited": False,
                "runtime_visibility_proved": False,
                "reset_cause_proved": False,
                "portme": (
                    "Boot this exact artifact separately and capture the matched Lions "
                    "HOME facemask region; this writer does not execute the title."
                ),
            },
        }
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, result)
        common.require(common.path_identity(source) == source_identity,
                       "source pathname changed during manifest write")
        common.require(common.owned_path_matches(output_owned),
                       "output pathname changed during manifest write")
        common.require(common.owned_path_matches(manifest_owned),
                       "manifest pathname changed after write")
        success = True
        return result
    finally:
        os.close(source_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            common.unlink_if_owned(manifest_owned)
            common.unlink_if_owned(output_owned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest)
    except (OSError, common.PatchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": result["schema"],
        "output": result["output"]["path"],
        "sha256": result["output"]["sha256"],
        "changed_bytes": result["patch"]["actual_changed_byte_count"],
        "target_body_sha256": result["patch"]["target"]["patched_body_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
