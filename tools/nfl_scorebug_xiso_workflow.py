#!/usr/bin/env python3
"""Create a layout-identical NFL 2K5 XISO copy with one scorebug PNG edit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

from nfl_scorebug_png_import import (DEFAULT_AUDIT, DEFAULT_INDEX, TARGET_NAMES,
                                      build_import, canonical_json)
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_scorebug_xiso_workflow/v1"
MAX_MANIFEST_BYTES = 64 * 1024 * 1024


class WorkflowError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_all(descriptor: int, offset: int, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        amount = os.pwrite(descriptor, payload[position:], offset + position)
        require(amount > 0, "short XISO target write")
        position += amount


def offset_hash(offsets: list[int], fmt: str) -> str:
    return digest(b"".join(struct.pack(fmt, value) for value in offsets))


def relative_runs(offsets: list[int]) -> list[list[int]]:
    result: list[list[int]] = []
    for value in offsets:
        if not result or value != result[-1][1] + 1:
            result.append([value, value])
        else:
            result[-1][1] = value
    return result


def create_file(path: Path, payload: bytes) -> common.OwnedFile:
    owned = common.reserve_file(path)
    success = False
    try:
        position = 0
        while position < len(payload):
            amount = os.write(owned.descriptor, payload[position:])
            require(amount > 0, "short sidecar write")
            position += amount
        os.fsync(owned.descriptor)
        require(common.owned_path_matches(owned) and
                os.fstat(owned.descriptor).st_size == len(payload),
                "sidecar pathname/size changed")
        success = True
        return owned
    finally:
        if not success:
            os.close(owned.descriptor)
            common.unlink_if_owned(owned)


def run(source_path: Path, output_path: Path, manifest_path: Path,
        preview_path: Path, target_name: str, png_path: Path,
        index_path: Path, audit_path: Path) -> dict[str, Any]:
    supplied_source = source_path.lstat()
    require(stat.S_ISREG(supplied_source.st_mode) and
            not stat.S_ISLNK(supplied_source.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    output = common.canonical_new_path(output_path)
    manifest = common.canonical_new_path(manifest_path)
    preview = common.canonical_new_path(preview_path)
    png = png_path.resolve(strict=True)
    index = index_path.resolve(strict=True)
    audit = audit_path.resolve(strict=True)
    fixed_paths = {source, output, manifest, preview, png, index, audit}
    require(len(fixed_paths) == 7 and not output.exists() and
            not manifest.exists() and not preview.exists(),
            "workflow paths alias or an output already exists")

    replacement, preview_payload, import_value = build_import(
        index, audit, target_name, png)
    target = import_value["target"]
    require(target_name == target["name"], "import target identity changed")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    preview_owned: common.OwnedFile | None = None
    success = False
    try:
        source_info = os.fstat(source_fd)
        source_identity = common.fd_identity(source_fd)
        require(stat.S_ISREG(source_info.st_mode) and
                source_info.st_size == common.EXPECTED_XISO_SIZE and
                source_identity == (supplied_source.st_dev, supplied_source.st_ino) and
                common.path_identity(source) == source_identity,
                "source XISO identity/size changed")
        source_sha_before = common.sha256_fd(source_fd)
        require(source_sha_before == common.EXPECTED_XISO_SHA256,
                "retail source XISO SHA-256 mismatch")
        entries, directory = common.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        xbe = entries.get("default.xbe")
        pack = entries.get(str(target["pack_path"]).casefold())
        require(len(files) == 19 and xbe is not None and
                xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                    common.EXPECTED_XBE_SHA256,
                "retail XDVDFS/default.xbe identity changed")
        require(pack is not None and pack.sector == int(target["xiso_pack_sector"]) and
                pack.byte_offset == int(target["xiso_pack_byte_offset"]) and
                pack.size == int(target["pack_size"]) and
                common.sha256_fd(source_fd, pack.byte_offset, pack.size) ==
                    target["pack_sha256"],
                "retail target pack identity changed")
        assert pack is not None
        absolute = pack.byte_offset + int(target["pack_offset"])
        require(absolute == int(target["xiso_absolute_span_offset"]),
                "XISO target arithmetic changed")
        source_span = common.read_exact(source_fd, absolute, len(replacement))
        require(digest(source_span) == target["span_sha256"],
                "retail XISO target span changed")
        relative = [index_ for index_, (before, after) in
                    enumerate(zip(source_span, replacement)) if before != after]
        require(relative, "replacement equals the retail target")
        allowed = {absolute + value for value in relative}

        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "output aliases source")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_info.st_size)
        require(common.owned_path_matches(output_owned),
                "output pathname changed during copy")
        write_all(output_owned.descriptor, absolute, replacement)
        require(common.read_exact(output_owned.descriptor, absolute,
                                  len(replacement)) == replacement,
                "replacement readback failed")
        os.fsync(output_owned.descriptor)
        source_sha_after, output_sha, actual = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size, allowed)
        require(source_sha_after == source_sha_before and
                actual == sorted(allowed),
                "source changed or full-XISO difference ledger mismatch")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size)
        require(output_entries == entries and output_directory == directory and
                common.sha256_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                    common.EXPECTED_XBE_SHA256,
                "output XDVDFS tree/default.xbe changed")
        patched_pack_sha = common.sha256_fd(
            output_owned.descriptor, pack.byte_offset, pack.size)

        preview_owned = create_file(preview, preview_payload)
        import_sha = digest(canonical_json(import_value))
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "source": {
                "path": str(source), "size": source_info.st_size,
                "sha256_before": source_sha_before,
                "sha256_after": source_sha_after,
                "device": source_identity[0], "inode": source_identity[1],
                "opened_read_only": True, "modified": False,
            },
            "input": {
                "target": target_name, "png_path": str(png),
                "png_sha256": file_digest(png), "index_path": str(index),
                "audit_path": str(audit),
                "import_manifest": import_value,
                "import_manifest_sha256": import_sha,
            },
            "output": {
                "xiso_path": str(output), "xiso_size": source_info.st_size,
                "xiso_sha256": output_sha, "device": output_owned.identity[0],
                "inode": output_owned.identity[1], "copy_method": copy_method,
                "manifest_path": str(manifest), "preview_path": str(preview),
                "preview_sha256": digest(preview_payload),
                "exclusively_created": True,
            },
            "xdvdfs": {
                **directory, "file_count": len(files),
                "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
            },
            "patch": {
                "target_pack_path": target["pack_path"],
                "target_pack_sector": pack.sector,
                "target_pack_byte_offset": pack.byte_offset,
                "source_pack_sha256": target["pack_sha256"],
                "patched_pack_sha256": patched_pack_sha,
                "absolute_span_offset": absolute,
                "replacement_span_size": len(replacement),
                "replacement_span_sha256": digest(replacement),
                "relative_changed_byte_count": len(relative),
                "relative_changed_offsets_u32le_sha256": offset_hash(relative, "<I"),
                "relative_changed_runs": relative_runs(relative),
                "actual_changed_byte_count": len(actual),
                "actual_changed_offsets_u64le_sha256": offset_hash(actual, "<Q"),
                "all_other_xiso_bytes_identical": True,
            },
            "claims": {
                "code_bound_field_scorebug_texture": target_name in {
                    "score_buga", "shield_espn"
                },
                "shared_global_font_texture": target_name == "digital_font",
                "layout_identical_copy_only_xiso": True,
                "loader_in_place_decode_guarded": True,
                "originals_modified": False, "xemu_started": False,
                "title_executed": False, "runtime_visibility_proved": False,
                "portme": "PORTME(runtime): boot this copied XISO in xemu and capture the modified field scorebug.",
            },
        }
        manifest_owned = create_file(manifest, canonical_json(result))
        require(common.path_identity(source) == source_identity and
                common.owned_path_matches(output_owned) and
                common.owned_path_matches(preview_owned) and
                common.owned_path_matches(manifest_owned),
                "workflow pathname changed during manifest write")
        success = True
        return result
    finally:
        os.close(source_fd)
        for owned in (output_owned, preview_owned, manifest_owned):
            if owned is not None:
                os.close(owned.descriptor)
        if not success:
            common.unlink_if_owned(manifest_owned)
            common.unlink_if_owned(preview_owned)
            common.unlink_if_owned(output_owned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", type=Path, required=True)
    parser.add_argument("--output-xiso", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--target", choices=TARGET_NAMES, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest,
                     args.preview, args.target, args.png, args.index, args.audit)
        print("NFL_SCOREBUG_XISO_WORKFLOW_OK "
              f"target={args.target} changed={result['patch']['actual_changed_byte_count']} "
              f"sha256={result['output']['xiso_sha256']} runtime=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
