#!/usr/bin/env python3
"""Independently verify an NFL ``upper_deck`` source-subset XISO transport.

This module imports neither the native subset writer nor the XISO transport
writer. It reruns the standard-library-only copied-volume verifier, reparses
both disc trees, and re-derives the complete disc difference ledger from
read-only file descriptors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

import nfl_stadium_upper_deck_subset_verify as subset_verify
import nfl_uniform_color_xiso_direct_patch as xiso_format


MANIFEST_SCHEMA = "nfl2k5_upper_deck_subset_xiso_patch/v1"
VERIFY_SCHEMA = "nfl2k5_upper_deck_subset_xiso_verify/v1"
PACK_PATH = "vc_53450030/9"
PACK_SECTOR = 35_531
INDEX_PATH = "vc_53450030/0"
INDEX_SECTOR = 796_479
FILE_COUNT = 19
SPAN_OFFSET = subset_verify.CHUNK_START
SPAN_SIZE = subset_verify.CHUNK_SPAN
# Retail-rip provenance only (pack 9 at sector 35,531 of an extracted .xiso); the verifier
# addresses the span through the images' own XDVDFS directory.
ABSOLUTE_SPAN = PACK_SECTOR * xiso_format.SECTOR_SIZE + SPAN_OFFSET
MAX_MANIFEST = 64 * 1024
BLOCK = 16 * 1024 * 1024


class UpperDeckSubsetXisoVerifyError(ValueError):
    """The copied XISO or its evidence violates the pinned contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UpperDeckSubsetXisoVerifyError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def regular(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise UpperDeckSubsetXisoVerifyError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def digest_fd(fd: int, offset: int = 0, length: int | None = None) -> str:
    digest = hashlib.sha256()
    position = offset
    remaining = length
    while remaining is None or remaining:
        request = BLOCK if remaining is None else min(BLOCK, remaining)
        payload = os.pread(fd, request, position)
        if not payload:
            break
        digest.update(payload)
        position += len(payload)
        if remaining is not None:
            remaining -= len(payload)
    if length is not None:
        require(remaining == 0, "short bounded hash read")
    return digest.hexdigest()


def ledger(before: bytes, after: bytes) -> dict[str, object]:
    require(len(before) == len(after) == SPAN_SIZE, "ledger span size mismatch")
    offsets = [index for index, values in enumerate(zip(before, after))
               if values[0] != values[1]]
    offset_hash = hashlib.sha256()
    before_hash = hashlib.sha256()
    after_hash = hashlib.sha256()
    runs: list[tuple[int, int]] = []
    for offset in offsets:
        offset_hash.update(struct.pack("<I", offset))
        before_hash.update(before[offset:offset + 1])
        after_hash.update(after[offset:offset + 1])
        if not runs or runs[-1][1] != offset:
            runs.append((offset, offset + 1))
        else:
            runs[-1] = (runs[-1][0], offset + 1)
    return {
        "changed_byte_count": len(offsets),
        "changed_offset_u32le_sha256": offset_hash.hexdigest(),
        "changed_before_bytes_sha256": before_hash.hexdigest(),
        "changed_after_bytes_sha256": after_hash.hexdigest(),
        "changed_run_count": len(runs),
        "changed_run_pairs_u32le_sha256": hashlib.sha256(
            b"".join(struct.pack("<II", start, end) for start, end in runs)
        ).hexdigest(),
    }


def compare_full(source_fd: int, output_fd: int, size: int, absolute: int) -> int:
    position = 0
    changed = 0
    end = absolute + SPAN_SIZE
    while position < size:
        request = min(BLOCK, size - position)
        left = os.pread(source_fd, request, position)
        right = os.pread(output_fd, request, position)
        require(len(left) == len(right) == request, "short full-disc comparison read")
        if left != right:
            for index, values in enumerate(zip(left, right)):
                if values[0] != values[1]:
                    require(absolute <= position + index < end,
                            f"unauthorized XISO difference at 0x{position + index:x}")
                    changed += 1
        position += request
    return changed


def verify(
    source_xiso_path: Path,
    index_path: Path,
    boundary_path: Path,
    catalog_path: Path,
    recipe_schema_path: Path,
    recipe_path: Path,
    subset_output_dir: Path,
    output_xiso_path: Path,
    manifest_path: Path,
) -> dict[str, object]:
    native = subset_verify.verify(
        index_path, boundary_path, catalog_path, recipe_schema_path,
        subset_output_dir, recipe_path,
    )
    require(native["mode"] in {"count_only_prefix", "source_subset_remap"},
            "native subset input is not changed")

    source = regular(source_xiso_path, "retail source XISO")
    output = regular(output_xiso_path, "copied upper_deck XISO")
    changed_volume = regular(subset_output_dir / "9", "verified changed upper_deck volume 9")
    manifest_file = regular(manifest_path, "XISO writer manifest")
    raw = manifest_file.read_bytes()
    require(0 < len(raw) <= MAX_MANIFEST, "XISO manifest size is outside the v1 limit")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UpperDeckSubsetXisoVerifyError(f"XISO manifest is invalid JSON: {exc}") from exc
    require(raw == canonical_json(manifest), "XISO manifest is not canonical JSON")
    require(isinstance(manifest, dict) and set(manifest) == {
        "schema", "source", "native_subset_proof", "xdvdfs", "patch",
        "output", "claims",
    }, "XISO manifest root differs from v1")
    require(manifest["schema"] == MANIFEST_SCHEMA, "XISO manifest schema mismatch")

    descriptors = [
        os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                getattr(os, "O_CLOEXEC", 0))
        for path in (source, output, changed_volume)
    ]
    source_fd, output_fd, changed_fd = descriptors
    try:
        source_info, output_info, changed_info = map(os.fstat, descriptors)
        require(all(stat.S_ISREG(info.st_mode) for info in
                    (source_info, output_info, changed_info)), "an artifact descriptor is not regular")
        require(source_info.st_size == output_info.st_size == xiso_format.EXPECTED_XISO_SIZE,
                "source/output XISO size mismatch")
        require(changed_info.st_size == subset_verify.PACK_SIZE,
                "changed volume size mismatch")
        identities = [xiso_format.fd_identity(fd) for fd in descriptors]
        require(len(set(identities)) == 3, "source, output, and changed volume alias an inode")
        require(all(xiso_format.path_identity(path) == identity for path, identity in
                    zip((source, output, changed_volume), identities)),
                "an artifact pathname changed after open")

        source_sha = digest_fd(source_fd)
        output_sha = digest_fd(output_fd)
        changed_sha = digest_fd(changed_fd)
        require(source_sha == xiso_format.EXPECTED_XISO_SHA256,
                "retail XISO SHA-256 mismatch")
        require(changed_sha == native["output"]["volume_sha256"],
                "changed volume hash differs from native verification")

        source_entries, source_directory = xiso_format.parse_xdvdfs(
            source_fd, source_info.st_size
        )
        output_entries, output_directory = xiso_format.parse_xdvdfs(
            output_fd, output_info.st_size
        )
        require(output_directory == source_directory and output_entries == source_entries,
                "output XDVDFS tree/extents differ")
        files = [entry for entry in source_entries.values() if not (entry.attributes & 0x10)]
        require(len(files) == FILE_COUNT, "XDVDFS file count mismatch")
        pack = source_entries.get(PACK_PATH.casefold())
        index = source_entries.get(INDEX_PATH.casefold())
        xbe = source_entries.get("default.xbe")
        require(pack is not None and pack.size == subset_verify.PACK_SIZE,
                "volume 9 extent mismatch")
        require(index is not None and index.size == subset_verify.INDEX_SIZE,
                "volume 0 extent mismatch")
        require(xbe is not None and xbe.size == xiso_format.EXPECTED_XBE_SIZE,
                "default.xbe extent mismatch")
        span_absolute = pack.byte_offset + SPAN_OFFSET
        require(SPAN_OFFSET + SPAN_SIZE <= pack.size,
                "authorized absolute span arithmetic mismatch")
        require(digest_fd(source_fd, pack.byte_offset, pack.size) == subset_verify.PACK_SHA256,
                "retail XISO volume 9 hash mismatch")
        require(digest_fd(source_fd, index.byte_offset, index.size) == subset_verify.INDEX_SHA256,
                "retail XISO volume 0 hash mismatch")
        require(digest_fd(source_fd, xbe.byte_offset, xbe.size) ==
                digest_fd(output_fd, xbe.byte_offset, xbe.size) ==
                xiso_format.EXPECTED_XBE_SHA256, "default.xbe differs")

        retail_span = xiso_format.read_exact(source_fd, span_absolute, SPAN_SIZE)
        output_span = xiso_format.read_exact(output_fd, span_absolute, SPAN_SIZE)
        changed_span = xiso_format.read_exact(changed_fd, SPAN_OFFSET, SPAN_SIZE)
        require(hashlib.sha256(retail_span).hexdigest() == subset_verify.SOURCE_SPAN_SHA256,
                "retail SCNE span hash mismatch")
        require(output_span == changed_span and output_span != retail_span,
                "output XISO does not contain the verified changed SCNE span")
        derived_ledger = ledger(retail_span, output_span)
        require(derived_ledger["changed_byte_count"] > 0, "XISO subset span is a no-op")
        require(compare_full(source_fd, output_fd, source_info.st_size, span_absolute) ==
                derived_ledger["changed_byte_count"], "full-disc difference count mismatch")
        output_pack_sha = digest_fd(output_fd, pack.byte_offset, pack.size)
        require(output_pack_sha == changed_sha,
                "output XISO volume 9 differs from the verified copied volume")

        expected_native = {
            "schema": native["schema"], "mode": native["mode"],
            "recipe_sha256": native["request"]["sha256"],
            "subset_manifest_sha256": native["manifest_sha256"],
            "changed_volume_sha256": changed_sha,
            "source_vertex_count": 12,
            "output_vertex_count": native["request"]["new_vertex_count"],
            "decoded_changed_byte_count": native["decoded"]["decoded_changed_byte_count"],
            "outside_authorized_subset_bit_exact": True,
            "physical_stream_tails_bit_exact": True,
            "fixed_tail_exact": True,
        }
        expected_xdvdfs = {
            **source_directory, "file_count": len(files),
            "tree_identical_after_patch": True, "all_sector_extents_preserved": True,
            "default_xbe_sha256": xiso_format.EXPECTED_XBE_SHA256,
        }
        expected_patch = {
            "path": PACK_PATH, "pack_sector": pack.sector,
            "pack_byte_offset": pack.byte_offset, "pack_size": pack.size,
            "pack_span_offset": SPAN_OFFSET, "span_size": SPAN_SIZE,
            "absolute_span_offset": span_absolute,
            "source_span_sha256": hashlib.sha256(retail_span).hexdigest(),
            "replacement_span_sha256": hashlib.sha256(output_span).hexdigest(),
            "source_pack_sha256": subset_verify.PACK_SHA256,
            "output_pack_sha256": output_pack_sha,
            **derived_ledger, "all_xiso_bytes_outside_span_bit_exact": True,
        }
        require(manifest["source"] == {
            "path": str(source), "size": source_info.st_size,
            "sha256_before": source_sha, "sha256_after": source_sha,
            "opened_read_only": True, "modified": False,
        }, "manifest source record mismatch")
        require(manifest["native_subset_proof"] == expected_native,
                "manifest native proof record mismatch")
        require(manifest["xdvdfs"] == expected_xdvdfs, "manifest XDVDFS record mismatch")
        require(manifest["patch"] == expected_patch, "manifest patch ledger mismatch")
        output_record = manifest["output"]
        require(isinstance(output_record, dict) and output_record == {
            "path": str(output), "size": output_info.st_size, "sha256": output_sha,
            "copy_method": output_record.get("copy_method"), "exclusively_created": True,
            "distinct_from_source_and_changed_volume_inodes": True,
        } and output_record.get("copy_method") in {"copy_file_range", "pread_pwrite"},
                "manifest output record mismatch")
        require(manifest["claims"] == {
            "layout_identical_copy_only_xiso": True,
            "offline_native_subset_transport_proved": True,
            "changed_vertex_count_transport_proved": True,
            "xemu_boot_proved": False,
            "xemu_changed_count_visibility_proved": False,
            "original_xbox_hardware_proved": False,
            "production_ready": False,
        }, "manifest claim boundary mismatch")
        require(digest_fd(source_fd) == source_sha and
                xiso_format.path_identity(source) == identities[0] and
                xiso_format.path_identity(output) == identities[1] and
                xiso_format.path_identity(changed_volume) == identities[2],
                "an input changed during independent verification")
    finally:
        for descriptor in descriptors:
            os.close(descriptor)

    return {
        "schema": VERIFY_SCHEMA,
        "output_xiso_sha256": output_sha,
        "changed_volume_sha256": changed_sha,
        "changed_byte_count": derived_ledger["changed_byte_count"],
        "changed_run_count": derived_ledger["changed_run_count"],
        "absolute_span_offset": span_absolute,
        "span_size": SPAN_SIZE,
        "xdvdfs_tree_exact": True,
        "outside_authorized_span_exact": True,
        "default_xbe_exact": True,
        "source_unchanged": True,
        "xemu_boot_proved": False,
        "xemu_changed_count_visibility_proved": False,
        "hardware_proved": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--boundary", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--recipe-schema", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--subset-output-dir", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.source_xiso, args.index, args.boundary, args.catalog,
                    args.recipe_schema, args.recipe,
                    args.subset_output_dir, args.output_xiso, args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UpperDeckSubsetXisoVerifyError,
            subset_verify.UpperDeckSubsetVerifyError,
            xiso_format.PatchError, KeyError,
            json.JSONDecodeError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
