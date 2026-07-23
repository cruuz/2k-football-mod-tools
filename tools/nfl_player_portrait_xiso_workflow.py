#!/usr/bin/env python3
"""Create a copy-only NFL 2K5 XISO with numeric roster-portrait edits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
from typing import Any

from nfl_player_portrait_png_import import build_import, canonical_json
from nfl_player_portrait_targets import DEFAULT_REPORT
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_player_portrait_xiso_workflow/v1"
PLAN_SCHEMA = "nfl2k5_player_portrait_plan/v1"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
MAX_EDITS = 4303
MAX_PLAN_BYTES = 64 * 1024 * 1024


class WorkflowError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_plan(path: Path) -> tuple[Path, bytes, list[dict[str, str]]]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "portrait plan must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and
                (opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino) and
                opened.st_size <= MAX_PLAN_BYTES,
                "portrait plan pathname/type/size changed")
        payload = common.read_exact(descriptor, 0, opened.st_size)
        require(not os.pread(descriptor, 1, opened.st_size), "portrait plan grew")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                "portrait plan changed while reading")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WorkflowError("portrait plan is invalid JSON") from exc
    require(payload == canonical_json(value) and
            set(value) == {"schema", "purpose", "edits"} and
            value["schema"] == PLAN_SCHEMA and isinstance(value["purpose"], str) and
            bool(value["purpose"]) and isinstance(value["edits"], list) and
            1 <= len(value["edits"]) <= MAX_EDITS,
            "portrait plan schema/canonical encoding changed")
    edits: list[dict[str, str]] = []
    for record in value["edits"]:
        require(isinstance(record, dict) and set(record) == {"portrait_id", "png"} and
                type(record["portrait_id"]) is str and
                len(record["portrait_id"]) == 4 and record["portrait_id"].isascii() and
                record["portrait_id"].isdecimal() and type(record["png"]) is str and
                bool(record["png"]), "portrait plan edit fields/types changed")
        edits.append(record)
    return resolved, payload, edits


def write_all(descriptor: int, offset: int, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        written = os.pwrite(descriptor, payload[position:], offset + position)
        require(written > 0, "short portrait XISO target write")
        position += written


def offset_hash(offsets: list[int], width: str) -> str:
    return digest(b"".join(struct.pack(width, value) for value in offsets))


def relative_runs(offsets: list[int]) -> list[list[int]]:
    result: list[list[int]] = []
    for value in offsets:
        if not result or value != result[-1][1] + 1:
            result.append([value, value])
        else:
            result[-1][1] = value
    return result


def absolute_for_relative(segments: list[dict[str, Any]], relative: int) -> int:
    for segment in segments:
        start = int(segment["span_relative_offset"])
        size = int(segment["size"])
        if start <= relative < start + size:
            return int(segment["xiso_absolute_offset"]) + relative - start
    raise WorkflowError("changed byte is outside target span segments")


def run(source_path: Path, output_path: Path, manifest_path: Path,
        preview_dir_path: Path, plan_path: Path, index_path: Path,
        compatibility_path: Path) -> dict[str, Any]:
    source_lstat = source_path.lstat()
    require(stat.S_ISREG(source_lstat.st_mode) and not stat.S_ISLNK(source_lstat.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    output = common.canonical_new_path(output_path)
    manifest = common.canonical_new_path(manifest_path)
    preview_dir = preview_dir_path.parent.resolve(strict=True) / preview_dir_path.name
    require(not output.exists() and not manifest.exists() and not preview_dir.exists(),
            "portrait output, manifest, or preview directory already exists")
    plan, plan_payload, edits = read_plan(plan_path)
    index = index_path.resolve(strict=True)
    compatibility = compatibility_path.resolve(strict=True)
    require(index.stat().st_size == INDEX_SIZE and file_digest(index) == INDEX_SHA256,
            "canonical extracted index hash/size changed")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    preview_owned = False
    success = False
    try:
        source_info = os.fstat(source_fd)
        require(stat.S_ISREG(source_info.st_mode) and
                source_info.st_size == common.EXPECTED_XISO_SIZE,
                "retail source XISO type/size changed")
        source_identity = common.fd_identity(source_fd)
        require(common.path_identity(source) == source_identity and
                common.sha256_fd(source_fd) == common.EXPECTED_XISO_SHA256,
                "retail source XISO identity/hash changed")
        source_sha = common.EXPECTED_XISO_SHA256
        entries, directory = common.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        xbe = entries.get("default.xbe")
        require(len(files) == 19 and xbe is not None and
                xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "retail XDVDFS/default.xbe identity changed")

        prepared: list[dict[str, Any]] = []
        selectors: set[str] = set()
        logical_ranges: list[tuple[int, int]] = []
        allowed_offsets: set[int] = set()
        pack_hashes: dict[str, str] = {}
        for order, edit in enumerate(edits):
            portrait_id = edit["portrait_id"]
            png_path = Path(edit["png"])
            preview_name = f"{order:04d}_portrait_{portrait_id}.png"
            names = {"span_file": f"{order:04d}_replacement.txtr.bin",
                     "manifest_file": f"{order:04d}_import.json",
                     "preview_file": preview_name}
            replacement, preview, import_value = build_import(
                index, compatibility, portrait_id, png_path, names)
            target = import_value["target"]
            selector = str(target["selector"])
            require(selector not in selectors, "portrait plan repeats one selector")
            selectors.add(selector)
            segments = list(target["span_segments"])
            source_pieces: list[bytes] = []
            normalized_segments: list[dict[str, Any]] = []
            for segment in segments:
                pack_path = str(segment["pack_path"])
                pack = entries.get(pack_path.casefold())
                require(pack is not None and pack.sector == int(segment["pack_sector"]) and
                        pack.size == int(segment["pack_size"]),
                        f"source pack extent changed for {selector}")
                assert pack is not None
                if pack_path not in pack_hashes:
                    pack_hashes[pack_path] = common.sha256_fd(
                        source_fd, pack.byte_offset, pack.size)
                require(pack_hashes[pack_path] == segment["pack_sha256"],
                        f"source pack hash changed for {selector}")
                absolute = pack.byte_offset + int(segment["pack_offset"])
                require(absolute == int(segment["xiso_absolute_offset"]),
                        f"portrait XISO arithmetic changed for {selector}")
                piece = common.read_exact(source_fd, absolute, int(segment["size"]))
                source_pieces.append(piece)
                normalized_segments.append({**segment, "xiso_absolute_offset": absolute})
            source_span = b"".join(source_pieces)
            require(len(source_span) == len(replacement) and
                    digest(source_span) == target["span_sha256"],
                    f"retail portrait source span changed for {selector}")
            logical_start = int(target["chunk_offset"])
            logical_end = logical_start + len(replacement)
            require(all(logical_end <= first or logical_start >= last
                        for first, last in logical_ranges),
                    "portrait plan target spans overlap")
            logical_ranges.append((logical_start, logical_end))
            relative = [index for index, (before, after) in
                        enumerate(zip(source_span, replacement)) if before != after]
            require(relative, f"portrait replacement equals retail for {selector}")
            absolute_changes = [absolute_for_relative(normalized_segments, value)
                                for value in relative]
            require(not (set(absolute_changes) & allowed_offsets),
                    "portrait changed-byte sets overlap")
            allowed_offsets.update(absolute_changes)
            prepared.append({
                "order": order, "selector": selector, "target": target,
                "replacement": replacement, "preview": preview,
                "preview_name": preview_name, "import_manifest": import_value,
                "segments": normalized_segments, "source_span": source_span,
                "relative_changes": relative, "absolute_changes": absolute_changes,
            })

        path_set = {source, output, manifest, preview_dir, plan, index, compatibility}
        path_set.update(Path(edit["png"]).resolve(strict=True) for edit in edits)
        require(len(path_set) == 7 + len(edits), "portrait workflow paths alias")

        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "portrait output aliases source")
        copy_method = common.copy_fd_exact(source_fd, output_owned.descriptor,
                                           source_info.st_size)
        for item in prepared:
            for segment in item["segments"]:
                relative = int(segment["span_relative_offset"])
                size = int(segment["size"])
                payload = item["replacement"][relative:relative + size]
                write_all(output_owned.descriptor,
                          int(segment["xiso_absolute_offset"]), payload)
                require(common.read_exact(output_owned.descriptor,
                        int(segment["xiso_absolute_offset"]), size) == payload,
                        f"portrait replacement readback failed for {item['selector']}")
        os.fsync(output_owned.descriptor)
        source_sha_after, output_sha, actual = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size, allowed_offsets)
        require(source_sha_after == source_sha and actual == sorted(allowed_offsets) and
                common.path_identity(source) == source_identity and
                common.owned_path_matches(output_owned),
                "portrait source/output changed outside proved ledger")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size)
        require(output_entries == entries and output_directory == directory and
                common.sha256_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "portrait output XDVDFS/default.xbe changed")

        os.mkdir(preview_dir, 0o755)
        preview_owned = True
        preview_hashes: dict[str, str] = {}
        for item in prepared:
            destination = preview_dir / item["preview_name"]
            descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                                 getattr(os, "O_NOFOLLOW", 0) |
                                 getattr(os, "O_CLOEXEC", 0), 0o644)
            try:
                write_all(descriptor, 0, item["preview"])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            preview_hashes[item["preview_name"]] = digest(item["preview"])

        edit_records: list[dict[str, Any]] = []
        for item in prepared:
            relative = item["relative_changes"]
            edit_records.append({
                "order": item["order"], "selector": item["selector"],
                "target": item["target"],
                "input_png": item["import_manifest"]["input_png"],
                "import_manifest": item["import_manifest"],
                "import_manifest_sha256": digest(canonical_json(item["import_manifest"])),
                "replacement_span_sha256": digest(item["replacement"]),
                "replacement_span_size": len(item["replacement"]),
                "preview_file": item["preview_name"],
                "preview_sha256": digest(item["preview"]),
                "absolute_span_segments": item["segments"],
                "relative_changed_byte_count": len(relative),
                "relative_changed_offsets_u32le_sha256": offset_hash(relative, "<I"),
                "relative_changed_runs": relative_runs(relative),
            })
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "source": {"path": str(source), "size": source_info.st_size,
                       "sha256_before": source_sha, "sha256_after": source_sha_after,
                       "device": source_identity[0], "inode": source_identity[1],
                       "opened_read_only": True, "modified": False},
            "plan": {"path": str(plan), "sha256": digest(plan_payload),
                     "edit_count": len(edits)},
            "canonical_index": {"path": str(index), "size": INDEX_SIZE,
                                "sha256": INDEX_SHA256},
            "compatibility_report": {"path": str(compatibility),
                                     "sha256": file_digest(compatibility)},
            "edits": edit_records,
            "output": {"xiso_path": str(output), "xiso_size": source_info.st_size,
                       "xiso_sha256": output_sha, "device": output_owned.identity[0],
                       "inode": output_owned.identity[1], "copy_method": copy_method,
                       "manifest_path": str(manifest),
                       "preview_directory": str(preview_dir),
                       "preview_sha256": preview_hashes, "exclusively_created": True},
            "xdvdfs": {**directory, "file_count": len(files),
                       "tree_identical_after_patch": True,
                       "all_sector_extents_preserved": True,
                       "default_xbe_sha256": common.EXPECTED_XBE_SHA256},
            "patch": {"target_count": len(prepared),
                      "target_pack_paths": sorted(pack_hashes),
                      "actual_changed_byte_count": len(actual),
                      "actual_changed_offsets_u64le_sha256": offset_hash(actual, "<Q"),
                      "all_other_xiso_bytes_identical": True},
            "claims": {"numeric_roster_portraits_only": True,
                       "action_photo_family_modified": False,
                       "live_3d_face_family_modified": False,
                       "layout_identical_copy_only_xiso": True,
                       "originals_modified": False,
                       "retail_artwork_exported_or_bundled": False,
                       "runtime_visibility_proved": False,
                       "xemu_started": False, "title_executed": False,
                       "portme": "PORTME(runtime): capture the edited portrait in a roster/wrap-up UI before claiming visibility."},
        }
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, result)
        require(common.owned_path_matches(output_owned) and
                common.owned_path_matches(manifest_owned),
                "portrait owned output pathname changed")
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
            if preview_owned and preview_dir.exists():
                shutil.rmtree(preview_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--index", type=Path,
                        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest,
                     args.preview_dir, args.plan, args.index, args.compatibility)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"schema": result["schema"], "edits": len(result["edits"]),
                      "changed_bytes": result["patch"]["actual_changed_byte_count"],
                      "output_sha256": result["output"]["xiso_sha256"],
                      "runtime_visibility_proved": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
