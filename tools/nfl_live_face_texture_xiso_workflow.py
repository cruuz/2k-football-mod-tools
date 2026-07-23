#!/usr/bin/env python3
"""Build a copy-only NFL 2K5 XISO with live f/h/n texture edits."""

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

from nfl_live_face_texture_png_import import (DEFAULT_INDEX, build_import,
                                               canonical_json)
from nfl_live_face_texture_targets import DEFAULT_REPORT
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_live_face_texture_xiso_workflow/v1"
PLAN_SCHEMA = "nfl2k5_live_face_texture_plan/v1"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
MAX_EDITS = 1872
MAX_PLAN_BYTES = 16 * 1024 * 1024


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


def read_plan(path: Path) -> tuple[Path, bytes, list[dict[str, Any]]]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "plan must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        require((opened.st_dev, opened.st_ino) ==
                (supplied.st_dev, supplied.st_ino) and
                opened.st_size <= MAX_PLAN_BYTES, "plan identity/size changed")
        payload = common.read_exact(descriptor, 0, opened.st_size)
        require(not os.pread(descriptor, 1, opened.st_size), "plan grew while reading")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                "plan changed while reading")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WorkflowError("plan is invalid JSON") from exc
    require(payload == canonical_json(value) and isinstance(value, dict) and
            set(value) == {"schema", "purpose", "edits"} and
            value["schema"] == PLAN_SCHEMA and isinstance(value["purpose"], str) and
            bool(value["purpose"]) and isinstance(value["edits"], list) and
            1 <= len(value["edits"]) <= MAX_EDITS,
            "plan schema/canonical encoding mismatch")
    edits = []
    for record in value["edits"]:
        require(isinstance(record, dict) and
                set(record) == {"face_id", "family", "png"} and
                type(record["face_id"]) is str and type(record["family"]) is str and
                type(record["png"]) is str and bool(record["png"]),
                "plan edit fields/types mismatch")
        edits.append(record)
    return resolved, payload, edits


def write_all(descriptor: int, offset: int, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        amount = os.pwrite(descriptor, payload[position:], offset + position)
        require(amount > 0, "short XISO target write")
        position += amount


def offset_hash(offsets: list[int], width: str) -> str:
    return digest(b"".join(struct.pack(width, value) for value in offsets))


def relative_runs(offsets: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for value in offsets:
        if not runs or value != runs[-1][1] + 1:
            runs.append([value, value])
        else:
            runs[-1][1] = value
    return runs


def run(source_path: Path, output_path: Path, manifest_path: Path,
        preview_dir_path: Path, plan_path: Path, index_path: Path,
        compatibility_path: Path) -> dict[str, Any]:
    supplied_source = source_path.lstat()
    require(stat.S_ISREG(supplied_source.st_mode) and
            not stat.S_ISLNK(supplied_source.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    output = common.canonical_new_path(output_path)
    manifest = common.canonical_new_path(manifest_path)
    preview_dir = preview_dir_path.parent.resolve(strict=True) / preview_dir_path.name
    require(not output.exists() and not manifest.exists() and not preview_dir.exists(),
            "output XISO, manifest, or preview directory already exists")
    plan, plan_payload, edits = read_plan(plan_path)
    index = index_path.resolve(strict=True)
    compatibility = compatibility_path.resolve(strict=True)
    require(index.stat().st_size == INDEX_SIZE and file_digest(index) == INDEX_SHA256,
            "canonical extracted index hash/size mismatch")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    preview_owned = False
    success = False
    try:
        source_info = os.fstat(source_fd)
        source_identity = common.fd_identity(source_fd)
        require(stat.S_ISREG(source_info.st_mode) and
                source_info.st_size == common.EXPECTED_XISO_SIZE and
                common.path_identity(source) == source_identity and
                source_identity == (supplied_source.st_dev, supplied_source.st_ino),
                "source XISO identity/size changed")
        source_sha_before = common.sha256_fd(source_fd)
        require(source_sha_before == common.EXPECTED_XISO_SHA256,
                "retail source XISO SHA-256 mismatch")
        entries, directory = common.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        xbe = entries.get("default.xbe")
        require(len(files) == 19 and xbe is not None and
                xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "retail XDVDFS/default.xbe identity changed")

        prepared = []
        selectors: set[str] = set()
        span_ranges: list[tuple[int, int]] = []
        allowed_offsets: set[int] = set()
        verified_pack_hashes: dict[str, str] = {}
        for order, edit in enumerate(edits):
            replacement, previews, import_value = build_import(
                index, compatibility, str(edit["face_id"]),
                str(edit["family"]), Path(str(edit["png"])))
            target = import_value["target"]
            selector = f"{target['face_id']}:{target['family']}"
            require(selector not in selectors, "plan repeats one live face target")
            selectors.add(selector)
            pack_path = str(target["xiso_pack_path"])
            pack = entries.get(pack_path.casefold())
            if pack is not None and pack_path.casefold() not in verified_pack_hashes:
                verified_pack_hashes[pack_path.casefold()] = common.sha256_fd(
                    source_fd, pack.byte_offset, pack.size)
            require(pack is not None and pack.sector == int(target["xiso_pack_sector"]) and
                    pack.byte_offset == int(target["xiso_pack_byte_offset"]) and
                    pack.size == int(target["xiso_pack_size"]) and
                    verified_pack_hashes.get(pack_path.casefold()) ==
                    target["xiso_pack_sha256"],
                    f"source pack identity changed for {selector}")
            assert pack is not None
            absolute = int(target["xiso_absolute_span_offset"])
            require(absolute == pack.byte_offset + int(target["pack_offset"]),
                    f"XISO target arithmetic changed for {selector}")
            source_span = common.read_exact(source_fd, absolute, len(replacement))
            require(digest(source_span) == target["span_sha256"],
                    f"source span changed for {selector}")
            end = absolute + len(replacement)
            require(all(end <= first or absolute >= last for first, last in span_ranges),
                    "plan target spans overlap")
            span_ranges.append((absolute, end))
            relative = [position for position, (before, after) in enumerate(
                zip(source_span, replacement)) if before != after]
            require(relative, f"replacement equals retail for {selector}")
            absolute_changes = [absolute + position for position in relative]
            require(not (set(absolute_changes) & allowed_offsets),
                    "plan changed-byte sets overlap")
            allowed_offsets.update(absolute_changes)
            preview_records = [
                (f"{order:03d}_{selector.replace(':', '_')}_{name}", payload)
                for name, payload in previews
            ]
            prepared.append({
                "order": order, "selector": selector, "target": target,
                "replacement": replacement, "import_manifest": import_value,
                "import_manifest_sha256": digest(canonical_json(import_value)),
                "absolute_offset": absolute, "relative_changes": relative,
                "absolute_changes": absolute_changes, "previews": preview_records,
            })

        input_paths = {Path(str(edit["png"])).resolve(strict=True) for edit in edits}
        fixed_paths = {source, output, manifest, preview_dir, plan, index, compatibility}
        require(not (fixed_paths & input_paths) and len(fixed_paths) == 7,
                "workflow input/output paths alias")

        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "output XISO aliases source")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_info.st_size)
        for item in prepared:
            write_all(output_owned.descriptor, item["absolute_offset"], item["replacement"])
            require(common.read_exact(output_owned.descriptor, item["absolute_offset"],
                                      len(item["replacement"])) == item["replacement"],
                    f"replacement readback failed for {item['selector']}")
        os.fsync(output_owned.descriptor)
        source_sha_after, output_sha, actual = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size, allowed_offsets)
        require(source_sha_after == source_sha_before and actual == sorted(allowed_offsets),
                "source changed or full-XISO difference ledger mismatch")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size)
        require(output_entries == entries and output_directory == directory and
                common.sha256_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "output XDVDFS tree/default.xbe changed")

        os.mkdir(preview_dir, 0o755)
        preview_owned = True
        preview_hashes = {}
        for item in prepared:
            for name, payload in item["previews"]:
                descriptor = os.open(preview_dir / name,
                                     os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                                     getattr(os, "O_NOFOLLOW", 0) |
                                     getattr(os, "O_CLOEXEC", 0), 0o644)
                try:
                    position = 0
                    while position < len(payload):
                        amount = os.write(descriptor, payload[position:])
                        require(amount > 0, "short preview write")
                        position += amount
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                preview_hashes[name] = digest(payload)

        edit_records = []
        for item in prepared:
            relative = item["relative_changes"]
            edit_records.append({
                "order": item["order"], "selector": item["selector"],
                "target": item["target"],
                "input_png": item["import_manifest"]["input_png"],
                "import_manifest": item["import_manifest"],
                "import_manifest_sha256": item["import_manifest_sha256"],
                "replacement_span_sha256": digest(item["replacement"]),
                "replacement_span_size": len(item["replacement"]),
                "previews": [{"file_name": name, "sha256": digest(payload),
                              "size": len(payload)}
                             for name, payload in item["previews"]],
                "absolute_span_offset": item["absolute_offset"],
                "relative_changed_byte_count": len(relative),
                "relative_changed_offsets_u32le_sha256": offset_hash(relative, "<I"),
                "relative_changed_runs": relative_runs(relative),
            })
        result = {
            "schema": SCHEMA,
            "source": {
                "path": str(source), "size": source_info.st_size,
                "sha256_before": source_sha_before, "sha256_after": source_sha_after,
                "device": source_identity[0], "inode": source_identity[1],
                "opened_read_only": True, "modified": False,
            },
            "plan": {"path": str(plan), "sha256": digest(plan_payload),
                     "edit_count": len(edits)},
            "canonical_index": {"path": str(index), "size": INDEX_SIZE,
                                "sha256": INDEX_SHA256},
            "compatibility_report": {"path": str(compatibility),
                                     "sha256": file_digest(compatibility)},
            "edits": edit_records,
            "output": {
                "xiso_path": str(output), "xiso_size": source_info.st_size,
                "xiso_sha256": output_sha, "device": output_owned.identity[0],
                "inode": output_owned.identity[1], "copy_method": copy_method,
                "manifest_path": str(manifest),
                "preview_directory": str(preview_dir),
                "preview_sha256": dict(sorted(preview_hashes.items())),
                "exclusively_created": True,
            },
            "xdvdfs": {**directory, "file_count": len(files),
                       "tree_identical_after_patch": True,
                       "all_sector_extents_preserved": True,
                       "default_xbe_sha256": common.EXPECTED_XBE_SHA256},
            "patch": {
                "target_count": len(prepared),
                "target_pack_paths": sorted({
                    str(item["target"]["xiso_pack_path"]) for item in prepared}),
                "actual_changed_byte_count": len(actual),
                "actual_changed_offsets_u64le_sha256": offset_hash(actual, "<Q"),
                "all_other_xiso_bytes_identical": True,
            },
            "claims": {
                "actual_live_3d_face_head_resources": True,
                "portrait_or_menu_cards_modified": False,
                "layout_identical_copy_only_xiso": True,
                "loader_in_place_decode_guarded": True,
                "shape_geometry_modified": False,
                "originals_modified": False, "runtime_visibility_proved": False,
                "xemu_started": False, "title_executed": False,
                "portme": "PORTME(runtime): capture the selected players before claiming visibility.",
            },
        }
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, result)
        require(common.owned_path_matches(output_owned) and
                common.owned_path_matches(manifest_owned) and
                common.path_identity(source) == source_identity,
                "owned output or source pathname changed")
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
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest,
                     args.preview_dir, args.plan, args.index, args.compatibility)
        print(
            "NFL_LIVE_FACE_TEXTURE_XISO_WORKFLOW_OK "
            f"edits={len(result['edits'])} "
            f"changed={result['patch']['actual_changed_byte_count']} "
            f"output_sha={result['output']['xiso_sha256']} "
            "runtime=false xemu_started=false"
        )
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
