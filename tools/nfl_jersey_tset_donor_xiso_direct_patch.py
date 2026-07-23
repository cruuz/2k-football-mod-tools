#!/usr/bin/env python3
"""Create a layout-identical NFL 2K5 XISO with one retail jersey TSET donor.

The complete compressed TSET chunk 1 (wrapper plus stored stream) from Atlanta
current AWAY ``01A0.IFF`` is copied over the equal-sized chunk 1 in Detroit
current HOME ``09H0.IFF``.  The source image is opened read-only; output and
manifest are O_EXCL-created; every byte in both 6.30 GB images is compared.

This is deliberately a shipped-resource donor swap, not a PNG importer.  The
program never starts an emulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import struct
import sys

import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_jersey_tset_donor_xiso_direct_patch/v1"
PROBE_NAME = "lions_09H0_jersey_tset_from_falcons_01A0"

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
TARGET_TEAM = "Detroit Lions"
TARGET_SIDE = "HOME"
TARGET_OUTER_INDEX = 3685
TARGET_OUTER_ID = 0x9A4832D6
TARGET_OUTER_PACK_OFFSET = 0x055CA800
DONOR_RESOURCE = "01A0.IFF"
DONOR_TEAM = "Atlanta Falcons"
DONOR_SIDE = "AWAY"
DONOR_OUTER_INDEX = 3939
DONOR_OUTER_ID = 0x34B81671
DONOR_OUTER_PACK_OFFSET = 0x098C4800

TSET_CHUNK_INDEX = 1
TSET_CHUNK_OFFSET = 0x70
TSET_STORED_SIZE = 74688
TSET_SPAN_SIZE = 0x20 + TSET_STORED_SIZE
TARGET_TSET_PACK_OFFSET = TARGET_OUTER_PACK_OFFSET + TSET_CHUNK_OFFSET
DONOR_TSET_PACK_OFFSET = DONOR_OUTER_PACK_OFFSET + TSET_CHUNK_OFFSET
TARGET_TSET_ABSOLUTE = 5_011_470_448
DONOR_TSET_ABSOLUTE = 4_623_452_272

TARGET_HEADER = bytes.fromhex(
    "54534554c02301000001000080b20200efbeedfe200000000000000000000000"
)
DONOR_HEADER = bytes.fromhex(
    "54534554c02301000001000080b20200efbeedfe100000000000000000000000"
)
TARGET_HEADER_SHA256 = "c2f0c4cebb8802faa671d69bce4341a6c199ed1b105553b6364fa07d8d74e23f"
DONOR_HEADER_SHA256 = "e39654f6bf658ed9ba15877a22d85063f977801c2ad5d251dc71c0a4f073606d"
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
RELATIVE_RUN_COUNT = 903
RELATIVE_RUN_U32LE_SHA256 = (
    "e03d7d5dd1dcecc1ad2b9e0bd22edabb5a4a43616f53c7615c93acb4a65bb6f6"
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def offset_digest(offsets: list[int]) -> str:
    return sha256_bytes(b"".join(struct.pack("<I", offset) for offset in offsets))


def difference_runs(offsets: list[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for offset in offsets:
        if not result or offset != result[-1][1] + 1:
            result.append((offset, offset))
        else:
            result[-1] = (result[-1][0], offset)
    return result


def run_digest(runs: list[tuple[int, int]]) -> str:
    return sha256_bytes(
        b"".join(struct.pack("<II", start, end) for start, end in runs)
    )


def validate_span_pair(target: bytes, donor: bytes) -> tuple[list[int], list[tuple[int, int]]]:
    common.require(len(target) == len(donor) == TSET_SPAN_SIZE,
                   "TSET span size mismatch")
    common.require(target[:0x20] == TARGET_HEADER and donor[:0x20] == DONOR_HEADER,
                   "TSET wrapper bytes mismatch")
    common.require(sha256_bytes(target[:0x20]) == TARGET_HEADER_SHA256 and
                   sha256_bytes(donor[:0x20]) == DONOR_HEADER_SHA256,
                   "TSET wrapper hash mismatch")
    common.require(sha256_bytes(target) == TARGET_SPAN_SHA256 and
                   sha256_bytes(donor) == DONOR_SPAN_SHA256,
                   "complete TSET span hash mismatch")
    common.require(sha256_bytes(target[0x20:]) == TARGET_STORED_SHA256 and
                   sha256_bytes(donor[0x20:]) == DONOR_STORED_SHA256,
                   "stored TSET stream hash mismatch")
    offsets = [
        index for index, (before, after) in enumerate(zip(target, donor))
        if before != after
    ]
    common.require(len(offsets) == RELATIVE_DIFF_COUNT,
                   "retail TSET spans no longer have the pinned difference count")
    common.require(offset_digest(offsets) == RELATIVE_DIFF_U32LE_SHA256,
                   "retail TSET relative-difference ledger mismatch")
    runs = difference_runs(offsets)
    common.require(len(runs) == RELATIVE_RUN_COUNT and
                   run_digest(runs) == RELATIVE_RUN_U32LE_SHA256,
                   "retail TSET difference-run ledger mismatch")
    return offsets, runs


def canonical_new_path(path: Path) -> Path:
    common.require(path.name not in {"", ".", ".."}, "invalid output filename")
    parent = path.parent.resolve(strict=True)
    common.require(parent.is_dir(), f"output parent is not a directory: {parent}")
    return parent / path.name


def pwrite_all(descriptor: int, offset: int, value: bytes) -> None:
    written = 0
    while written < len(value):
        amount = os.pwrite(descriptor, value[written:], offset + written)
        common.require(amount > 0, f"short write at 0x{offset + written:x}")
        written += amount


def run(source_path: Path, output_path: Path, manifest_path: Path) -> dict[str, object]:
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
        pack_a = entries.get(PACK_A_PATH.casefold())
        pack_b = entries.get(PACK_B_PATH.casefold())
        pack0 = entries.get(PACK0_PATH.casefold())
        common.require(xbe is not None and xbe.size == common.EXPECTED_XBE_SIZE,
                       "default.xbe extent mismatch")
        common.require(pack_a is not None and
                       (pack_a.sector, pack_a.size) == (PACK_A_SECTOR, PACK_A_SIZE),
                       "pack A extent mismatch")
        common.require(pack_b is not None and
                       (pack_b.sector, pack_b.size) == (PACK_B_SECTOR, PACK_B_SIZE),
                       "pack B extent mismatch")
        common.require(pack0 is not None, "pack 0 missing")
        assert xbe is not None and pack_a is not None and pack_b is not None and pack0 is not None
        common.require(common.sha256_fd(source_fd, xbe.byte_offset, xbe.size)
                       == common.EXPECTED_XBE_SHA256, "default.xbe SHA-256 mismatch")
        common.require(common.sha256_fd(source_fd, pack_a.byte_offset, pack_a.size)
                       == PACK_A_SHA256, "retail pack A SHA-256 mismatch")
        common.require(common.sha256_fd(source_fd, pack_b.byte_offset, pack_b.size)
                       == PACK_B_SHA256, "retail pack B SHA-256 mismatch")
        common.require(common.sha256_fd(source_fd, pack0.byte_offset, pack0.size)
                       == PACK0_SHA256, "retail pack 0 SHA-256 mismatch")

        target_absolute = pack_a.byte_offset + TARGET_TSET_PACK_OFFSET
        donor_absolute = pack_b.byte_offset + DONOR_TSET_PACK_OFFSET
        common.require(target_absolute == TARGET_TSET_ABSOLUTE,
                       "target absolute TSET offset arithmetic mismatch")
        common.require(donor_absolute == DONOR_TSET_ABSOLUTE,
                       "donor absolute TSET offset arithmetic mismatch")
        target_span = common.read_exact(source_fd, target_absolute, TSET_SPAN_SIZE)
        donor_span = common.read_exact(source_fd, donor_absolute, TSET_SPAN_SIZE)
        relative_differences, relative_runs = validate_span_pair(target_span, donor_span)
        absolute_differences = [target_absolute + offset for offset in relative_differences]
        allowed_offsets = set(absolute_differences)

        output_owned = common.reserve_file(output)
        common.require(common.fd_identity(output_owned.descriptor) != source_identity,
                       "output unexpectedly aliases source inode")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_info.st_size
        )
        common.require(common.owned_path_matches(output_owned),
                       "output pathname changed during copy")
        pwrite_all(output_owned.descriptor, target_absolute, donor_span)
        common.require(common.read_exact(output_owned.descriptor,
                                         target_absolute, TSET_SPAN_SIZE) == donor_span,
                       "patched target TSET does not equal complete donor span")
        common.require(common.read_exact(output_owned.descriptor,
                                         donor_absolute, TSET_SPAN_SIZE) == donor_span,
                       "source donor TSET changed unexpectedly")
        os.fsync(output_owned.descriptor)
        common.require(common.path_identity(source) == source_identity,
                       "source pathname changed during patch")
        common.require(common.owned_path_matches(output_owned),
                       "output pathname changed during patch")

        source_sha_after, output_sha, actual_differences = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size, allowed_offsets
        )
        common.require(source_sha_after == source_sha_before,
                       "retail source XISO changed during run")
        common.require(actual_differences == absolute_differences,
                       "full-image difference ledger mismatch")
        common.require(common.path_identity(source) == source_identity,
                       "source pathname changed after full comparison")
        common.require(common.owned_path_matches(output_owned),
                       "output pathname changed after full comparison")

        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        common.require(output_entries == entries and output_directory == directory,
                       "XDVDFS tree or metadata changed")
        output_pack_a_sha = common.sha256_fd(
            output_owned.descriptor, pack_a.byte_offset, pack_a.size
        )
        common.require(common.sha256_fd(output_owned.descriptor,
                                       pack_b.byte_offset, pack_b.size) == PACK_B_SHA256,
                       "donor pack B changed")
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
                    "Replace the complete Lions current-HOME jersey00/jersey00_mud "
                    "compressed TSET with an equal-sized shipped Falcons AWAY donor."
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
                    "team": TARGET_TEAM,
                    "side": TARGET_SIDE,
                    "outer_index": TARGET_OUTER_INDEX,
                    "outer_id": f"0x{TARGET_OUTER_ID:08x}",
                    "pack_path": pack_a.path,
                    "pack_start_sector": pack_a.sector,
                    "outer_pack_offset": TARGET_OUTER_PACK_OFFSET,
                    "chunk_index": TSET_CHUNK_INDEX,
                    "chunk_offset": TSET_CHUNK_OFFSET,
                    "tset_pack_offset": TARGET_TSET_PACK_OFFSET,
                    "absolute_tset_offset": target_absolute,
                    "source_header_sha256": TARGET_HEADER_SHA256,
                    "source_span_sha256": TARGET_SPAN_SHA256,
                    "source_stored_sha256": TARGET_STORED_SHA256,
                    "source_decoded_sha256": TARGET_DECODED_SHA256,
                    "patched_header_sha256": DONOR_HEADER_SHA256,
                    "patched_span_sha256": DONOR_SPAN_SHA256,
                    "patched_stored_sha256": DONOR_STORED_SHA256,
                    "patched_decoded_sha256": DONOR_DECODED_SHA256,
                },
                "donor": {
                    "resource": DONOR_RESOURCE,
                    "team": DONOR_TEAM,
                    "side": DONOR_SIDE,
                    "outer_index": DONOR_OUTER_INDEX,
                    "outer_id": f"0x{DONOR_OUTER_ID:08x}",
                    "pack_path": pack_b.path,
                    "pack_start_sector": pack_b.sector,
                    "outer_pack_offset": DONOR_OUTER_PACK_OFFSET,
                    "chunk_index": TSET_CHUNK_INDEX,
                    "chunk_offset": TSET_CHUNK_OFFSET,
                    "tset_pack_offset": DONOR_TSET_PACK_OFFSET,
                    "absolute_tset_offset": donor_absolute,
                    "header_sha256": DONOR_HEADER_SHA256,
                    "span_sha256": DONOR_SPAN_SHA256,
                    "stored_sha256": DONOR_STORED_SHA256,
                    "decoded_sha256": DONOR_DECODED_SHA256,
                    "unchanged_in_output": True,
                },
                "complete_wrapper_and_stored_stream_copied": True,
                "target_complete_span_equals_pinned_donor": True,
                "target_complete_span_size": TSET_SPAN_SIZE,
                "relative_changed_byte_count": len(relative_differences),
                "relative_changed_offsets_u32le_sha256": offset_digest(relative_differences),
                "relative_changed_run_count": len(relative_runs),
                "relative_changed_runs_u32le_sha256": run_digest(relative_runs),
                "first_relative_changed_offsets": relative_differences[:16],
                "last_relative_changed_offsets": relative_differences[-16:],
                "absolute_patch_start": target_absolute,
                "absolute_patch_end_exclusive": target_absolute + TSET_SPAN_SIZE,
                "actual_changed_byte_count": len(actual_differences),
                "actual_changed_offsets_u64le_sha256": sha256_bytes(
                    b"".join(struct.pack("<Q", offset) for offset in actual_differences)
                ),
                "all_other_image_bytes_identical": True,
                "source_pack_a_sha256": PACK_A_SHA256,
                "output_pack_a_sha256": output_pack_a_sha,
                "donor_pack_b_sha256": PACK_B_SHA256,
                "unrelated_pack0_sha256": PACK0_SHA256,
            },
            "claims": {
                "layout_identical_copy_only_xiso": True,
                "known_retail_complete_tset_donor_only": True,
                "donor_texture_swap": True,
                "general_png_importer": False,
                "arbitrary_texture_recompression": False,
                "away_target_resource_edited": False,
                "runtime_visibility_proved": False,
                "portme": (
                    "PORTME: boot this exact artifact and capture Detroit HOME in game. "
                    "Implement a strict compressor/serializer before arbitrary PNG import."
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
    # Convert SIGTERM into an exception so ``run`` reaches its ownership-aware
    # cleanup path instead of leaving an unverified O_EXCL output behind.
    def handle_sigterm(_signum: int, _frame: object) -> None:
        raise InterruptedError("writer interrupted by SIGTERM")

    signal.signal(signal.SIGTERM, handle_sigterm)
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
        "target_tset_sha256": result["patch"]["target"]["patched_span_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
