#!/usr/bin/env python3
"""Insert any independently validated 09H0 PNG-import span into a retail XISO."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import struct
import sys

from nfl_tset_png_import_dynamic_validate import validate_dynamic_import
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_tset_png_import_xiso_generic_patch/v2"
PACK_A_PATH = "vc_53450030/A"
PACK_A_SECTOR = 2_403_082
PACK_A_SIZE = 310_294_528
PACK_A_SHA256 = "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b"
PACK_B_PATH = "vc_53450030/B"
PACK_B_SHA256 = "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614"
PACK0_PATH = "vc_53450030/0"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
TARGET_OUTER_PACK_OFFSET = 0x055CA800
TARGET_CHUNK_OFFSET = 0x70
TARGET_SPAN_PACK_OFFSET = TARGET_OUTER_PACK_OFFSET + TARGET_CHUNK_OFFSET
TARGET_ABSOLUTE = 5_011_470_448
SPAN_SIZE = 74720
SOURCE_SPAN_SHA256 = "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862"
MAX_SMALL_FILE = 32 * 1024 * 1024


@dataclass(frozen=True)
class PinnedFile:
    path: Path
    device: int
    inode: int
    size: int
    sha256: str
    payload: bytes


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_new_path(path: Path) -> Path:
    common.require(path.name not in {"", ".", ".."}, "invalid output filename")
    parent = path.parent.resolve(strict=True)
    common.require(parent.is_dir(), f"output parent is not a directory: {parent}")
    return parent / path.name


def pin_small_file(path: Path, label: str, expected_size: int | None = None) -> PinnedFile:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise common.PatchError(f"{label} does not exist: {path}") from exc
    common.require(not stat.S_ISLNK(supplied.st_mode), f"{label} must not be a symlink")
    supplied_identity = (supplied.st_dev, supplied.st_ino)
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        info = os.fstat(descriptor)
        common.require(stat.S_ISREG(info.st_mode), f"{label} is not a regular file")
        common.require(info.st_size <= MAX_SMALL_FILE, f"{label} exceeds 32 MiB")
        if expected_size is not None:
            common.require(info.st_size == expected_size, f"{label} size mismatch")
        identity = common.fd_identity(descriptor)
        common.require(identity == supplied_identity,
                       f"{label} pathname was swapped while opening")
        common.require(common.path_identity(resolved) == identity,
                       f"{label} pathname identity changed")
        payload = common.read_exact(descriptor, 0, info.st_size)
        return PinnedFile(
            resolved, identity[0], identity[1], info.st_size,
            sha256_bytes(payload), payload,
        )
    finally:
        os.close(descriptor)


def verify_pin(pin: PinnedFile, label: str) -> None:
    common.require(common.path_identity(pin.path) == (pin.device, pin.inode),
                   f"{label} pathname was swapped")
    descriptor = os.open(
        pin.path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        common.require(common.fd_identity(descriptor) == (pin.device, pin.inode),
                       f"{label} inode was swapped")
        common.require(common.sha256_fd(descriptor) == pin.sha256,
                       f"{label} content changed")
    finally:
        os.close(descriptor)


def pin_previews(directory: Path, expected_count: int = 12) \
        -> tuple[Path, tuple[int, int], dict[str, PinnedFile]]:
    try:
        supplied = directory.lstat()
    except FileNotFoundError as exc:
        raise common.PatchError(f"preview directory does not exist: {directory}") from exc
    common.require(not stat.S_ISLNK(supplied.st_mode) and stat.S_ISDIR(supplied.st_mode),
                   "preview path must be a non-symlink directory")
    resolved = directory.resolve(strict=True)
    directory_info = resolved.stat(follow_symlinks=False)
    identity = (directory_info.st_dev, directory_info.st_ino)
    common.require(identity == (supplied.st_dev, supplied.st_ino),
                   "preview directory was swapped while opening")
    pins: dict[str, PinnedFile] = {}
    for child in sorted(resolved.iterdir(), key=lambda value: value.name):
        common.require(child.name not in pins, "duplicate preview filename")
        pin = pin_small_file(child, f"preview {child.name}")
        pins[child.name] = pin
    common.require(expected_count > 0 and len(pins) == expected_count,
                   f"expected {expected_count} preview files, found {len(pins)}")
    return resolved, identity, pins


def verify_previews(directory: Path, identity: tuple[int, int],
                    pins: dict[str, PinnedFile]) -> None:
    info = directory.stat(follow_symlinks=False)
    common.require((info.st_dev, info.st_ino) == identity,
                   "preview directory pathname was swapped")
    common.require({path.name for path in directory.iterdir()} == set(pins),
                   "preview directory file set changed")
    for name, pin in pins.items():
        verify_pin(pin, f"preview {name}")


def pwrite_all(descriptor: int, offset: int, value: bytes) -> None:
    position = 0
    while position < len(value):
        written = os.pwrite(descriptor, value[position:], offset + position)
        common.require(written > 0, f"short span write at 0x{offset + position:x}")
        position += written


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


def run(
    source_path: Path,
    replacement_path: Path,
    import_manifest_path: Path,
    clean_png_path: Path,
    mud_png_path: Path | None,
    previews_path: Path,
    output_path: Path,
    writer_manifest_path: Path,
) -> dict[str, object]:
    try:
        supplied_source = source_path.lstat()
    except FileNotFoundError as exc:
        raise common.PatchError(f"retail source XISO absent: {source_path}") from exc
    common.require(not stat.S_ISLNK(supplied_source.st_mode),
                   "retail source XISO must not be a symlink")
    source = source_path.resolve(strict=True)
    output = canonical_new_path(output_path)
    writer_manifest = canonical_new_path(writer_manifest_path)
    common.require(source.is_file() and not source.is_symlink(),
                   "retail source XISO must be a regular file")
    common.require(not output.exists() and not writer_manifest.exists(),
                   "output XISO or writer manifest already exists")

    replacement = pin_small_file(replacement_path, "replacement TSET", SPAN_SIZE)
    import_manifest = pin_small_file(import_manifest_path, "import manifest")
    clean_png = pin_small_file(clean_png_path, "clean PNG")
    mud_png = pin_small_file(mud_png_path, "mud PNG") if mud_png_path else None
    preview_dir, preview_identity, preview_pins = pin_previews(previews_path)
    path_set = {source, output, writer_manifest, replacement.path,
                import_manifest.path, clean_png.path, preview_dir}
    if mud_png is not None:
        path_set.add(mud_png.path)
    common.require(len(path_set) == (8 if mud_png is not None else 7),
                   "an input/output path aliases another workflow path")

    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    success = False
    try:
        source_info = os.fstat(source_fd)
        common.require(stat.S_ISREG(source_info.st_mode) and
                       source_info.st_size == common.EXPECTED_XISO_SIZE,
                       "retail source XISO size/type mismatch")
        source_identity = common.fd_identity(source_fd)
        common.require(common.path_identity(source) == source_identity,
                       "retail source pathname changed")
        source_sha_before = common.sha256_fd(source_fd)
        common.require(source_sha_before == common.EXPECTED_XISO_SHA256,
                       "retail source XISO SHA-256 mismatch")
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
                       "required retail files absent")
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
        common.require(target_absolute == TARGET_ABSOLUTE,
                       "target absolute span arithmetic mismatch")
        source_span = common.read_exact(source_fd, target_absolute, SPAN_SIZE)
        common.require(sha256_bytes(source_span) == SOURCE_SPAN_SHA256,
                       "retail target span hash mismatch")

        validated, validation_evidence = validate_dynamic_import(
            source_span=source_span,
            replacement_span=replacement.payload,
            import_manifest_payload=import_manifest.payload,
            clean_png_name=clean_png.path.name,
            clean_png_payload=clean_png.payload,
            mud_png_name=mud_png.path.name if mud_png else None,
            mud_png_payload=mud_png.payload if mud_png else None,
            preview_payloads={name: pin.payload for name, pin in preview_pins.items()},
            replacement_span_name=replacement.path.name,
            import_manifest_name=import_manifest.path.name,
            preview_directory_name=preview_dir.name,
        )
        relative_differences = [
            index for index, (before, after) in enumerate(
                zip(source_span, replacement.payload)
            ) if before != after
        ]
        common.require(relative_differences, "replacement span equals retail")
        absolute_differences = [target_absolute + value for value in relative_differences]
        relative_runs = difference_runs(relative_differences)

        for pin, label in ((replacement, "replacement TSET"),
                           (import_manifest, "import manifest"),
                           (clean_png, "clean PNG")):
            verify_pin(pin, label)
        if mud_png is not None:
            verify_pin(mud_png, "mud PNG")
        verify_previews(preview_dir, preview_identity, preview_pins)

        output_owned = common.reserve_file(output)
        common.require(common.fd_identity(output_owned.descriptor) != source_identity,
                       "output XISO aliases retail source")
        copy_method = common.copy_fd_exact(source_fd, output_owned.descriptor,
                                           source_info.st_size)
        pwrite_all(output_owned.descriptor, target_absolute, replacement.payload)
        common.require(common.read_exact(output_owned.descriptor, target_absolute, SPAN_SIZE)
                       == replacement.payload, "replacement span readback mismatch")
        os.fsync(output_owned.descriptor)
        source_sha_after, output_sha, actual_differences = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size,
            set(absolute_differences)
        )
        common.require(source_sha_after == source_sha_before and
                       actual_differences == absolute_differences,
                       "source changed or full-image difference ledger mismatch")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        common.require(output_entries == entries and output_directory == directory,
                       "output XDVDFS tree/layout changed")
        output_pack_a_sha = common.sha256_fd(
            output_owned.descriptor, pack_a.byte_offset, pack_a.size
        )
        common.require(common.sha256_fd(output_owned.descriptor,
                                       pack_b.byte_offset, pack_b.size) == PACK_B_SHA256 and
                       common.sha256_fd(output_owned.descriptor,
                                       pack0.byte_offset, pack0.size) == PACK0_SHA256 and
                       common.sha256_fd(output_owned.descriptor,
                                       xbe.byte_offset, xbe.size)
                       == common.EXPECTED_XBE_SHA256,
                       "an unrelated pack/default.xbe changed")
        for pin, label in ((replacement, "replacement TSET"),
                           (import_manifest, "import manifest"),
                           (clean_png, "clean PNG")):
            verify_pin(pin, label)
        if mud_png is not None:
            verify_pin(mud_png, "mud PNG")
        verify_previews(preview_dir, preview_identity, preview_pins)
        common.require(common.path_identity(source) == source_identity,
                       "retail source pathname changed during run")

        result: dict[str, object] = {
            "schema": SCHEMA,
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
            "inputs": {
                "clean_png": {
                    "path": str(clean_png.path), "sha256": clean_png.sha256,
                    "device": clean_png.device, "inode": clean_png.inode,
                },
                "mud_png": None if mud_png is None else {
                    "path": str(mud_png.path), "sha256": mud_png.sha256,
                    "device": mud_png.device, "inode": mud_png.inode,
                },
                "replacement_span": {
                    "path": str(replacement.path), "sha256": replacement.sha256,
                    "size": replacement.size,
                },
                "import_manifest": {
                    "path": str(import_manifest.path), "sha256": import_manifest.sha256,
                },
                "preview_directory": str(preview_dir),
                "preview_sha256": {
                    name: pin.sha256 for name, pin in sorted(preview_pins.items())
                },
            },
            "dynamic_validation": validation_evidence,
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
                "target_resource": "09H0.IFF",
                "target_outer_index": 3685,
                "target_outer_id": "0x9a4832d6",
                "target_chunk_index": 1,
                "target_chunk_offset": TARGET_CHUNK_OFFSET,
                "absolute_span_offset": target_absolute,
                "span_size": SPAN_SIZE,
                "source_span_sha256": SOURCE_SPAN_SHA256,
                "replacement_span_sha256": validated.span_sha256,
                "relative_changed_byte_count": len(relative_differences),
                "relative_changed_offsets_u32le_sha256":
                    offset_digest(relative_differences, "<I"),
                "relative_changed_run_count": len(relative_runs),
                "relative_changed_runs_u32le_sha256": sha256_bytes(
                    b"".join(struct.pack("<II", start, end)
                             for start, end in relative_runs)
                ),
                "actual_changed_byte_count": len(actual_differences),
                "actual_changed_offsets_u64le_sha256":
                    offset_digest(actual_differences, "<Q"),
                "all_other_image_bytes_identical": True,
                "source_pack_a_sha256": PACK_A_SHA256,
                "output_pack_a_sha256": output_pack_a_sha,
                "unrelated_pack_b_sha256": PACK_B_SHA256,
                "unrelated_pack0_sha256": PACK0_SHA256,
            },
            "claims": {
                "bounded_target_only": "Detroit current HOME 09H0.IFF chunk 1",
                "dynamic_import_artifact_independently_validated": True,
                "loader_in_place_decode_guarded": True,
                "layout_identical_copy_only_xiso": True,
                "originals_modified": False,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "title_executed": False,
                "portme": "PORTME: add separately proved target-layout profiles for other teams.",
            },
        }
        manifest_owned = common.reserve_file(writer_manifest)
        common.write_owned_json(manifest_owned, result)
        common.require(common.owned_path_matches(output_owned) and
                       common.owned_path_matches(manifest_owned),
                       "output/writer-manifest pathname changed")
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
    def handle_sigterm(_signum: int, _frame: object) -> None:
        raise InterruptedError("generic XISO writer interrupted by SIGTERM")

    signal.signal(signal.SIGTERM, handle_sigterm)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--replacement-span", required=True, type=Path)
    parser.add_argument("--import-manifest", required=True, type=Path)
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--mud-png", type=Path)
    parser.add_argument("--previews", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--writer-manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(
            args.source_xiso, args.replacement_span, args.import_manifest,
            args.clean_png, args.mud_png, args.previews,
            args.output_xiso, args.writer_manifest,
        )
    except (OSError, common.PatchError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": result["schema"],
        "output": result["output"]["path"],
        "sha256": result["output"]["sha256"],
        "span_sha256": result["patch"]["replacement_span_sha256"],
        "changed_bytes": result["patch"]["actual_changed_byte_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
