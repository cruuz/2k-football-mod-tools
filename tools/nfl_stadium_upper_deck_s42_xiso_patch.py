#!/usr/bin/env python3
"""Add a verified ``upper_deck`` subset to the pinned ``s42nd`` diagnostic.

The source is the exact prior xemu-proved ``s42nd.iff`` control image. This
writer changes only its pinned SCNE span, preserving the diagnostic XBE and
ROST routing while transporting an independently verified 12-to-4 or 12-to-8
``upper_deck`` copied-volume result. It is diagnostic-only.
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

import nfl_stadium_upper_deck_subset_verify as subset_verify
import nfl_uniform_color_xiso_direct_patch as xiso


SCHEMA = "nfl2k5_upper_deck_s42_xiso_patch/v1"
PACK_PATH = "vc_53450030/9"
PACK_SECTOR = 35_531
INDEX_PATH = "vc_53450030/0"
INDEX_SECTOR = 796_479
FILE_COUNT = 19
SPAN_OFFSET = subset_verify.CHUNK_START
SPAN_SIZE = subset_verify.CHUNK_SPAN
EXPECTED_ABSOLUTE_SPAN = PACK_SECTOR * xiso.SECTOR_SIZE + SPAN_OFFSET
LEDGER_CHUNK = 16 * 1024 * 1024
SOURCE_XISO_SHA256 = "863ba00df855efdf54b85d568516b1ed0f7bbd33ddb77096ce3e16da4e702383"
SOURCE_PACK0_SHA256 = "57d5ea1703e952cfca9b0f5175b5c9f9bc0bda3eb6676db9f8b6b0e074bddae9"
SOURCE_XBE_SHA256 = "c6abdd77be89594ee19dbfd8dbfa300b592a5a2ed1af2276e5e132678e50cc27"
RUNTIME_SCHEMA = "nfl2k5_group36_xemu_runtime_result/v2"
RUNTIME_SIZE = 12_051
RUNTIME_SHA256 = "33d76b3bbc9d11b52af6cf2861cf2890574a6d5b6820df8972d8419a63459d60"


class UpperDeckS42XisoError(ValueError):
    """A supplied artifact violates the one-span XISO contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UpperDeckS42XisoError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def regular(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise UpperDeckS42XisoError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def load_runtime_authority(path: Path) -> tuple[Path, dict[str, object]]:
    selected = regular(path, "s42 runtime authority")
    payload = selected.read_bytes()
    require(len(payload) == RUNTIME_SIZE and hashlib.sha256(payload).hexdigest() == RUNTIME_SHA256,
            "s42 runtime authority size or SHA-256 mismatch")
    value = json.loads(payload)
    require(payload == canonical_json(value), "s42 runtime authority is not canonical JSON")
    require(isinstance(value, dict) and value.get("schema") == RUNTIME_SCHEMA,
            "s42 runtime authority schema mismatch")
    claims = value.get("claims", {})
    control = value.get("runs", {}).get("control", {}).get("artifacts", {}).get("xiso", {})
    require(claims.get("target_outer_loaded_proved") is True
            and claims.get("xemu_boot_acceptance_proved") is True
            and claims.get("retail_signed_executable_chain_preserved") is False
            and control.get("sha256") == SOURCE_XISO_SHA256,
            "s42 runtime authority does not pin the admitted control route")
    return selected, value


def digest_fd(fd: int, offset: int = 0, length: int | None = None) -> str:
    digest = hashlib.sha256()
    position = offset
    remaining = length
    while remaining is None or remaining:
        request = LEDGER_CHUNK if remaining is None else min(LEDGER_CHUNK, remaining)
        block = os.pread(fd, request, position)
        if not block:
            break
        digest.update(block)
        position += len(block)
        if remaining is not None:
            remaining -= len(block)
    if length is not None:
        require(remaining == 0, "short bounded read while hashing")
    return digest.hexdigest()


def _ledger(source: bytes, output: bytes) -> dict[str, object]:
    require(len(source) == len(output) == SPAN_SIZE, "span ledger size mismatch")
    offsets = [index for index, pair in enumerate(zip(source, output)) if pair[0] != pair[1]]
    offset_digest = hashlib.sha256()
    before_digest = hashlib.sha256()
    after_digest = hashlib.sha256()
    runs: list[tuple[int, int]] = []
    for offset in offsets:
        offset_digest.update(struct.pack("<I", offset))
        before_digest.update(source[offset:offset + 1])
        after_digest.update(output[offset:offset + 1])
        if not runs or offset != runs[-1][1]:
            runs.append((offset, offset + 1))
        else:
            runs[-1] = (runs[-1][0], offset + 1)
    run_digest = hashlib.sha256(
        b"".join(struct.pack("<II", start, end) for start, end in runs)
    ).hexdigest()
    return {
        "changed_byte_count": len(offsets),
        "changed_offset_u32le_sha256": offset_digest.hexdigest(),
        "changed_before_bytes_sha256": before_digest.hexdigest(),
        "changed_after_bytes_sha256": after_digest.hexdigest(),
        "changed_run_count": len(runs),
        "changed_run_pairs_u32le_sha256": run_digest,
    }


def _compare_complete_xisos(
    source_fd: int, output_fd: int, size: int, absolute: int, expected: dict[str, object],
) -> tuple[str, str]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    position = 0
    actual_changed = 0
    outside_exact = True
    end = absolute + SPAN_SIZE
    while position < size:
        request = min(LEDGER_CHUNK, size - position)
        left = os.pread(source_fd, request, position)
        right = os.pread(output_fd, request, position)
        require(len(left) == len(right) == request, "short full-XISO comparison read")
        source_hash.update(left)
        output_hash.update(right)
        if left != right:
            for index, (before, after) in enumerate(zip(left, right)):
                if before != after:
                    absolute_offset = position + index
                    actual_changed += 1
                    if not absolute <= absolute_offset < end:
                        outside_exact = False
        position += request
    require(outside_exact, "copied XISO changed outside the authorized SCNE span")
    require(actual_changed == expected["changed_byte_count"],
            "full-XISO changed-byte count differs from the target-span ledger")
    return source_hash.hexdigest(), output_hash.hexdigest()


def _write_manifest(owned: xiso.OwnedFile, value: dict[str, object]) -> None:
    payload = canonical_json(value)
    require(xiso.owned_path_matches(owned), "manifest pathname changed before write")
    position = 0
    while position < len(payload):
        written = os.pwrite(owned.descriptor, payload[position:], position)
        require(written > 0, "short manifest write")
        position += written
    os.ftruncate(owned.descriptor, len(payload))
    os.fsync(owned.descriptor)
    require(xiso.read_exact(owned.descriptor, 0, len(payload)) == payload,
            "manifest readback differs")
    require(xiso.owned_path_matches(owned), "manifest pathname changed during write")


def run(
    source_xiso_path: Path,
    runtime_authority_path: Path,
    index_path: Path,
    boundary_path: Path,
    catalog_path: Path,
    recipe_schema_path: Path,
    recipe_path: Path,
    subset_output_dir: Path,
    output_xiso_path: Path,
    manifest_path: Path,
) -> dict[str, object]:
    # First require the existing independent native-volume proof.  Reopening
    # and hashing the accepted volume below closes the verifier/open race.
    runtime_path, runtime = load_runtime_authority(runtime_authority_path)
    native = subset_verify.verify(
        index_path, boundary_path, catalog_path, recipe_schema_path,
        subset_output_dir, recipe_path,
    )
    require(native["mode"] in {"count_only_prefix", "source_subset_remap"},
            "XISO transport requires a changed upper_deck volume")

    source = regular(source_xiso_path, "pinned s42 control XISO")
    changed_volume = regular(subset_output_dir / "9",
                             "verified changed upper_deck volume 9")
    output = xiso.canonical_new_path(output_xiso_path)
    manifest = xiso.canonical_new_path(manifest_path)
    require(not output.exists() and not manifest.exists(),
            "output XISO and manifest must both be new paths")
    require(len({source, changed_volume, output, manifest}) == 4,
            "source, changed volume, output, and manifest must be distinct")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    changed_fd = os.open(changed_volume, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    output_owned: xiso.OwnedFile | None = None
    manifest_owned: xiso.OwnedFile | None = None
    success = False
    try:
        source_info = os.fstat(source_fd)
        changed_info = os.fstat(changed_fd)
        require(stat.S_ISREG(source_info.st_mode) and
                source_info.st_size == xiso.EXPECTED_XISO_SIZE,
                "retail XISO descriptor size/type mismatch")
        require(stat.S_ISREG(changed_info.st_mode) and
                changed_info.st_size == subset_verify.PACK_SIZE,
                "changed volume descriptor size/type mismatch")
        source_identity = xiso.fd_identity(source_fd)
        changed_identity = xiso.fd_identity(changed_fd)
        require(xiso.path_identity(source) == source_identity and
                xiso.path_identity(changed_volume) == changed_identity,
                "source or changed-volume pathname changed")

        source_sha_before = digest_fd(source_fd)
        require(source_sha_before == SOURCE_XISO_SHA256,
                "s42 control XISO SHA-256 mismatch")
        changed_sha = digest_fd(changed_fd)
        require(changed_sha == native["output"]["volume_sha256"],
                "changed volume no longer matches independent verification")

        entries, directory = xiso.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        require(len(files) == FILE_COUNT, "retail XDVDFS file count mismatch")
        pack = entries.get(PACK_PATH.casefold())
        index = entries.get(INDEX_PATH.casefold())
        xbe = entries.get("default.xbe")
        require(pack is not None and (pack.sector, pack.size) ==
                (PACK_SECTOR, subset_verify.PACK_SIZE), "volume 9 XDVDFS extent mismatch")
        require(index is not None and (index.sector, index.size) ==
                (INDEX_SECTOR, subset_verify.INDEX_SIZE), "volume 0 XDVDFS extent mismatch")
        require(xbe is not None and xbe.size == xiso.EXPECTED_XBE_SIZE,
                "default.xbe extent mismatch")
        require(digest_fd(source_fd, pack.byte_offset, pack.size) == subset_verify.PACK_SHA256,
                "retail XISO volume 9 hash mismatch")
        require(digest_fd(source_fd, index.byte_offset, index.size) == SOURCE_PACK0_SHA256,
                "s42 control volume 0 hash mismatch")
        require(digest_fd(source_fd, xbe.byte_offset, xbe.size) == SOURCE_XBE_SHA256,
                "s42 diagnostic default.xbe hash mismatch")

        absolute = pack.byte_offset + SPAN_OFFSET
        require(absolute == EXPECTED_ABSOLUTE_SPAN and SPAN_OFFSET + SPAN_SIZE <= pack.size,
                "authorized XISO span arithmetic changed")
        retail_span = xiso.read_exact(source_fd, absolute, SPAN_SIZE)
        replacement_span = xiso.read_exact(changed_fd, SPAN_OFFSET, SPAN_SIZE)
        require(hashlib.sha256(retail_span).hexdigest() == subset_verify.SOURCE_SPAN_SHA256,
                "retail XISO SCNE span mismatch")
        require(retail_span != replacement_span, "independent changed volume is a no-op")
        ledger = _ledger(retail_span, replacement_span)
        require(ledger["changed_byte_count"] > 0, "replacement span has no changed bytes")

        output_owned = xiso.reserve_file(output)
        require(output_owned.identity not in {source_identity, changed_identity},
                "output aliases a source inode")
        copy_method = xiso.copy_fd_exact(source_fd, output_owned.descriptor, source_info.st_size)
        require(xiso.owned_path_matches(output_owned), "output pathname changed during copy")
        require(os.pwrite(output_owned.descriptor, replacement_span, absolute) == SPAN_SIZE,
                "short authorized-span write")
        require(xiso.read_exact(output_owned.descriptor, absolute, SPAN_SIZE) == replacement_span,
                "authorized-span readback mismatch")
        os.fsync(output_owned.descriptor)

        source_sha_after, output_sha = _compare_complete_xisos(
            source_fd, output_owned.descriptor, source_info.st_size, absolute, ledger
        )
        require(source_sha_after == source_sha_before, "s42 control XISO changed during write")
        require(xiso.path_identity(source) == source_identity and
                xiso.path_identity(changed_volume) == changed_identity and
                xiso.owned_path_matches(output_owned), "an artifact pathname changed during write")

        output_entries, output_directory = xiso.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        require(output_directory == directory and output_entries == entries,
                "XDVDFS tree or extents changed")
        output_pack_sha = digest_fd(output_owned.descriptor, pack.byte_offset, pack.size)
        require(output_pack_sha == changed_sha,
                "XISO volume 9 does not equal the independently verified changed volume")
        require(digest_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                SOURCE_XBE_SHA256, "diagnostic default.xbe changed")

        result: dict[str, object] = {
            "schema": SCHEMA,
            "runtime_authority": {
                "path": str(runtime_path), "schema": runtime["schema"],
                "size": RUNTIME_SIZE, "sha256": RUNTIME_SHA256,
                "source_control_xiso_sha256": SOURCE_XISO_SHA256,
                "source_xemu_boot_proved": True,
                "source_target_outer_loaded_proved": True,
                "source_retail_signed_chain_preserved": False,
            },
            "source": {
                "path": str(source), "size": source_info.st_size,
                "sha256_before": source_sha_before, "sha256_after": source_sha_after,
                "opened_read_only": True, "modified": False,
            },
            "native_subset_proof": {
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
            },
            "xdvdfs": {
                **directory, "file_count": len(files), "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "default_xbe_sha256": SOURCE_XBE_SHA256,
            },
            "patch": {
                "path": PACK_PATH, "pack_sector": pack.sector,
                "pack_byte_offset": pack.byte_offset, "pack_size": pack.size,
                "pack_span_offset": SPAN_OFFSET, "span_size": SPAN_SIZE,
                "absolute_span_offset": absolute,
                "source_span_sha256": hashlib.sha256(retail_span).hexdigest(),
                "replacement_span_sha256": hashlib.sha256(replacement_span).hexdigest(),
                "source_pack_sha256": subset_verify.PACK_SHA256,
                "output_pack_sha256": output_pack_sha,
                **ledger,
                "all_xiso_bytes_outside_span_bit_exact": True,
            },
            "output": {
                "path": str(output), "size": source_info.st_size, "sha256": output_sha,
                "copy_method": copy_method, "exclusively_created": True,
                "distinct_from_source_and_changed_volume_inodes": True,
            },
            "claims": {
                "diagnostic_only": True,
                "layout_identical_copy_only_xiso": True,
                "offline_native_subset_transport_proved": True,
                "changed_vertex_count_transport_proved": True,
                "s42_routing_and_xbe_preserved": True,
                "source_s42_target_outer_loaded_proved": True,
                "xemu_boot_proved": False,
                "xemu_changed_count_visibility_proved": False,
                "retail_signed_executable_chain_preserved": False,
                "original_xbox_hardware_proved": False,
                "production_ready": False,
            },
        }
        manifest_owned = xiso.reserve_file(manifest)
        _write_manifest(manifest_owned, result)
        require(xiso.path_identity(source) == source_identity and
                xiso.path_identity(changed_volume) == changed_identity and
                xiso.owned_path_matches(output_owned) and
                xiso.owned_path_matches(manifest_owned),
                "artifact pathname changed during manifest publication")
        success = True
        return result
    finally:
        os.close(source_fd)
        os.close(changed_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            xiso.unlink_if_owned(manifest_owned)
            xiso.unlink_if_owned(output_owned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--runtime-authority", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--boundary", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--recipe-schema", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--subset-output-dir", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.runtime_authority, args.index,
                     args.boundary, args.catalog,
                     args.recipe_schema, args.recipe,
                     args.subset_output_dir, args.output_xiso, args.manifest)
    except (OSError, UpperDeckS42XisoError,
            subset_verify.UpperDeckSubsetVerifyError,
            xiso.PatchError, KeyError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_UPPER_DECK_S42_XISO_PATCH_COMPLETE "
        f"changed={result['patch']['changed_byte_count']} "
        f"output_sha256={result['output']['sha256']} runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
