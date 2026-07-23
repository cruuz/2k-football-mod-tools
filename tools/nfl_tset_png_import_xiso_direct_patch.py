#!/usr/bin/env python3
"""Place the pinned CODEX MOD jersey TSET into a layout-identical NFL XISO.

The source retail image and imported TSET are opened read-only.  A complete
XISO copy and manifest are O_EXCL-created, one 74,720-byte span is replaced,
and every byte of source/output is compared.  No emulator is started.
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


SCHEMA = "nfl2k5_tset_png_import_xiso_direct_patch/v1"
PROBE_NAME = "lions_09H0_codex_mod_png_import_tset"
PACK_A_PATH = "vc_53450030/A"
PACK_A_SECTOR = 2_403_082
PACK_A_SIZE = 310_294_528
PACK_A_SHA256 = "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b"
PACK_B_PATH = "vc_53450030/B"
PACK_B_SHA256 = "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614"
PACK0_PATH = "vc_53450030/0"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
TARGET_RESOURCE = "09H0.IFF"
TARGET_OUTER_INDEX = 3685
TARGET_OUTER_ID = 0x9A4832D6
TARGET_OUTER_PACK_OFFSET = 0x055CA800
TARGET_CHUNK_INDEX = 1
TARGET_CHUNK_OFFSET = 0x70
TARGET_SPAN_PACK_OFFSET = TARGET_OUTER_PACK_OFFSET + TARGET_CHUNK_OFFSET
TARGET_SPAN_ABSOLUTE = 5_011_470_448
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_offsets(offsets: list[int], fmt: str) -> str:
    return sha256_bytes(b"".join(struct.pack(fmt, value) for value in offsets))


def difference_runs(offsets: list[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for value in offsets:
        if not result or value != result[-1][1] + 1:
            result.append((value, value))
        else:
            result[-1] = (result[-1][0], value)
    return result


def run_digest(runs: list[tuple[int, int]]) -> str:
    return sha256_bytes(
        b"".join(struct.pack("<II", start, end) for start, end in runs)
    )


def canonical_new_path(path: Path) -> Path:
    common.require(path.name not in {"", ".", ".."}, "invalid output filename")
    parent = path.parent.resolve(strict=True)
    common.require(parent.is_dir(), f"output parent is not a directory: {parent}")
    return parent / path.name


def pwrite_all(descriptor: int, offset: int, value: bytes) -> None:
    position = 0
    while position < len(value):
        written = os.pwrite(descriptor, value[position:], offset + position)
        common.require(written > 0, f"short replacement write at 0x{offset + position:x}")
        position += written


def read_pinned_file(path: Path, expected_size: int, expected_sha: str,
                     label: str) -> tuple[int, tuple[int, int], bytes]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise common.PatchError(f"{label} does not exist: {path}") from exc
    common.require(not stat.S_ISLNK(supplied.st_mode), f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    identity = common.fd_identity(descriptor)
    try:
        info = os.fstat(descriptor)
        common.require(stat.S_ISREG(info.st_mode) and info.st_size == expected_size,
                       f"{label} size/type mismatch")
        common.require(common.path_identity(resolved) == identity,
                       f"{label} pathname identity changed")
        payload = common.read_exact(descriptor, 0, expected_size)
        common.require(sha256_bytes(payload) == expected_sha, f"{label} SHA-256 mismatch")
        return descriptor, identity, payload
    except Exception:
        os.close(descriptor)
        raise


def run(source_path: Path, replacement_path: Path, import_manifest_path: Path,
        output_path: Path, writer_manifest_path: Path) -> dict[str, object]:
    try:
        supplied_source = source_path.lstat()
    except FileNotFoundError as exc:
        raise common.PatchError(f"source does not exist: {source_path}") from exc
    common.require(not stat.S_ISLNK(supplied_source.st_mode),
                   "source pathname must not be a symlink")
    source = source_path.resolve(strict=True)
    replacement = replacement_path.resolve(strict=True)
    import_manifest = import_manifest_path.resolve(strict=True)
    output = canonical_new_path(output_path)
    writer_manifest = canonical_new_path(writer_manifest_path)
    common.require(source.is_file() and not source.is_symlink(),
                   "source must be a regular non-symlink file")
    common.require(not output.exists() and not writer_manifest.exists(),
                   "output XISO or writer manifest already exists")
    common.require(len({source, replacement, import_manifest, output, writer_manifest}) == 5,
                   "source/replacement/manifests/output paths must be distinct")

    replacement_fd, replacement_identity, replacement_span = read_pinned_file(
        replacement_path, SPAN_SIZE, REPLACEMENT_SPAN_SHA256, "replacement TSET span"
    )
    import_fd, import_identity, import_payload = read_pinned_file(
        import_manifest_path, import_manifest_path.stat().st_size,
        IMPORT_MANIFEST_SHA256, "PNG-import manifest"
    )
    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    success = False
    try:
        import_value = json.loads(import_payload)
        common.require(import_value.get("schema") == "nfl2k5_tset_png_import/v1" and
                       import_value["input"]["clean"]["sha256"] == INPUT_PNG_SHA256 and
                       import_value["rebuild"]["complete_span_sha256"] ==
                       REPLACEMENT_SPAN_SHA256 and
                       import_value["rebuild"]["decoded_sha256"] ==
                       REPLACEMENT_DECODED_SHA256 and
                       import_value["compression"]["encoded_bytes"] == 22285,
                       "PNG-import manifest provenance mismatch")
        common.require(replacement_span[:0x20] == bytes.fromhex(
            "54534554c02301000001000080b20200efbeedfe200000000000000000000000"
        ), "replacement TSET wrapper mismatch")

        source_info = os.fstat(source_fd)
        common.require(stat.S_ISREG(source_info.st_mode) and
                       source_info.st_size == common.EXPECTED_XISO_SIZE,
                       "retail XISO size/type mismatch")
        source_identity = common.fd_identity(source_fd)
        common.require(common.path_identity(source) == source_identity,
                       "source pathname changed before validation")
        source_sha_before = common.sha256_fd(source_fd)
        common.require(source_sha_before == common.EXPECTED_XISO_SHA256,
                       "retail XISO SHA-256 mismatch")
        entries, directory = common.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        common.require(len(files) == 19, "retail XDVDFS file count mismatch")
        pack_a = entries.get(PACK_A_PATH.casefold())
        pack_b = entries.get(PACK_B_PATH.casefold())
        pack0 = entries.get(PACK0_PATH.casefold())
        xbe = entries.get("default.xbe")
        common.require(pack_a is not None and
                       (pack_a.sector, pack_a.size) == (PACK_A_SECTOR, PACK_A_SIZE),
                       "pack A extent mismatch")
        common.require(pack_b is not None and pack0 is not None and xbe is not None,
                       "required XDVDFS files absent")
        assert pack_a is not None and pack_b is not None and pack0 is not None and xbe is not None
        common.require(common.sha256_fd(source_fd, pack_a.byte_offset, pack_a.size)
                       == PACK_A_SHA256, "retail pack A hash mismatch")
        common.require(common.sha256_fd(source_fd, pack_b.byte_offset, pack_b.size)
                       == PACK_B_SHA256, "retail pack B hash mismatch")
        common.require(common.sha256_fd(source_fd, pack0.byte_offset, pack0.size)
                       == PACK0_SHA256, "retail pack 0 hash mismatch")
        common.require(common.sha256_fd(source_fd, xbe.byte_offset, xbe.size)
                       == common.EXPECTED_XBE_SHA256, "retail default.xbe hash mismatch")
        target_absolute = pack_a.byte_offset + TARGET_SPAN_PACK_OFFSET
        common.require(target_absolute == TARGET_SPAN_ABSOLUTE,
                       "target absolute offset arithmetic mismatch")
        source_span = common.read_exact(source_fd, target_absolute, SPAN_SIZE)
        common.require(sha256_bytes(source_span) == SOURCE_SPAN_SHA256,
                       "retail target span hash mismatch")
        common.require(source_span[:0x20] == replacement_span[:0x20],
                       "replacement changes the TSET wrapper")
        relative_differences = [
            index for index, (before, after) in enumerate(zip(source_span, replacement_span))
            if before != after
        ]
        relative_runs = difference_runs(relative_differences)
        common.require(len(relative_differences) == RELATIVE_DIFF_COUNT and
                       digest_offsets(relative_differences, "<I") ==
                       RELATIVE_DIFF_U32LE_SHA256 and
                       len(relative_runs) == RELATIVE_RUN_COUNT and
                       run_digest(relative_runs) == RELATIVE_RUN_U32LE_SHA256,
                       "replacement relative difference ledger mismatch")
        absolute_differences = [target_absolute + value for value in relative_differences]
        common.require(digest_offsets(absolute_differences, "<Q") ==
                       ABSOLUTE_DIFF_U64LE_SHA256,
                       "replacement absolute difference ledger mismatch")

        output_owned = common.reserve_file(output)
        common.require(common.fd_identity(output_owned.descriptor) != source_identity,
                       "output aliases source inode")
        copy_method = common.copy_fd_exact(source_fd, output_owned.descriptor,
                                           source_info.st_size)
        pwrite_all(output_owned.descriptor, target_absolute, replacement_span)
        common.require(common.read_exact(output_owned.descriptor, target_absolute, SPAN_SIZE)
                       == replacement_span, "replacement span readback mismatch")
        os.fsync(output_owned.descriptor)
        common.require(common.owned_path_matches(output_owned),
                       "output pathname changed during write")
        common.require(common.path_identity(source) == source_identity,
                       "source pathname changed during write")
        common.require(common.path_identity(replacement) == replacement_identity and
                       common.path_identity(import_manifest) == import_identity,
                       "replacement/import manifest pathname changed")

        source_sha_after, output_sha, actual_differences = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size,
            set(absolute_differences)
        )
        common.require(source_sha_after == source_sha_before,
                       "retail source changed during full comparison")
        common.require(actual_differences == absolute_differences,
                       "full-image difference ledger mismatch")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        common.require(output_entries == entries and output_directory == directory,
                       "output XDVDFS tree/layout changed")
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
                    "Place the SHA-pinned PNG-derived CODEX MOD jersey TSET into "
                    "Detroit current HOME 09H0 chunk 1 without relayout."
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
            "replacement": {
                "path": str(replacement),
                "size": len(replacement_span),
                "sha256": REPLACEMENT_SPAN_SHA256,
                "decoded_sha256": REPLACEMENT_DECODED_SHA256,
                "device": replacement_identity[0],
                "inode": replacement_identity[1],
                "opened_read_only": True,
                "modified": False,
                "import_manifest_path": str(import_manifest),
                "import_manifest_sha256": IMPORT_MANIFEST_SHA256,
                "input_png_sha256": INPUT_PNG_SHA256,
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
                "target_resource": TARGET_RESOURCE,
                "target_outer_index": TARGET_OUTER_INDEX,
                "target_outer_id": f"0x{TARGET_OUTER_ID:08x}",
                "target_chunk_index": TARGET_CHUNK_INDEX,
                "target_chunk_offset": TARGET_CHUNK_OFFSET,
                "pack_path": pack_a.path,
                "pack_start_sector": pack_a.sector,
                "outer_pack_offset": TARGET_OUTER_PACK_OFFSET,
                "span_pack_offset": TARGET_SPAN_PACK_OFFSET,
                "absolute_span_offset": target_absolute,
                "span_size": SPAN_SIZE,
                "source_span_sha256": SOURCE_SPAN_SHA256,
                "replacement_span_sha256": REPLACEMENT_SPAN_SHA256,
                "complete_wrapper_preserved": source_span[:0x20] == replacement_span[:0x20],
                "relative_changed_byte_count": len(relative_differences),
                "relative_changed_offsets_u32le_sha256":
                    digest_offsets(relative_differences, "<I"),
                "relative_changed_run_count": len(relative_runs),
                "relative_changed_runs_u32le_sha256": run_digest(relative_runs),
                "actual_changed_byte_count": len(actual_differences),
                "actual_changed_offsets_u64le_sha256":
                    digest_offsets(actual_differences, "<Q"),
                "all_other_image_bytes_identical": True,
                "source_pack_a_sha256": PACK_A_SHA256,
                "output_pack_a_sha256": output_pack_a_sha,
                "unrelated_pack_b_sha256": PACK_B_SHA256,
                "unrelated_pack0_sha256": PACK0_SHA256,
            },
            "claims": {
                "layout_identical_copy_only_xiso": True,
                "png_derived_tset_inserted": True,
                "only_one_complete_tset_span_replaced": True,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "title_executed": False,
                "portme": (
                    "PORTME: runtime agent may boot only this exact SHA-pinned output "
                    "and capture matched Detroit HOME control/patched frames."
                ),
            },
        }
        manifest_owned = common.reserve_file(writer_manifest)
        common.write_owned_json(manifest_owned, result)
        common.require(common.owned_path_matches(output_owned) and
                       common.owned_path_matches(manifest_owned),
                       "output/manifest pathname identity changed")
        success = True
        return result
    finally:
        os.close(source_fd)
        os.close(import_fd)
        os.close(replacement_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            common.unlink_if_owned(manifest_owned)
            common.unlink_if_owned(output_owned)


def main() -> int:
    def handle_sigterm(_signum: int, _frame: object) -> None:
        raise InterruptedError("writer interrupted by SIGTERM")

    signal.signal(signal.SIGTERM, handle_sigterm)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--replacement-span", required=True, type=Path)
    parser.add_argument("--import-manifest", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--writer-manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(
            args.source_xiso, args.replacement_span, args.import_manifest,
            args.output_xiso, args.writer_manifest,
        )
    except (OSError, common.PatchError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": result["schema"],
        "output": result["output"]["path"],
        "sha256": result["output"]["sha256"],
        "changed_bytes": result["patch"]["actual_changed_byte_count"],
        "replacement_span_sha256": result["patch"]["replacement_span_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
