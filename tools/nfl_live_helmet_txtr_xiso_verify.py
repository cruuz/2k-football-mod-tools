#!/usr/bin/env python3
"""Independently verify a copy-only NFL 2K5 live-helmet XISO workflow."""

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

from nfl_live_helmet_txtr_png_import import (DEFAULT_INDEX, build_import,
                                              canonical_json)
from nfl_live_helmet_txtr_targets import DEFAULT_REPORT
from nfl_live_helmet_txtr_xiso_workflow import (PLAN_SCHEMA, SCHEMA as WORKFLOW_SCHEMA,
                                                 offset_hash, read_plan,
                                                 relative_runs)
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_live_helmet_txtr_xiso_verify/v1"
MAX_MANIFEST_BYTES = 512 * 1024 * 1024
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"


class VerificationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def open_regular(path: Path, label: str) -> tuple[Path, int, tuple[int, int], int]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        require(stat.S_ISREG(info.st_mode) and identity ==
                (supplied.st_dev, supplied.st_ino) and
                common.path_identity(resolved) == identity,
                f"{label} pathname changed while opening")
        return resolved, descriptor, identity, info.st_size
    except Exception:
        os.close(descriptor)
        raise


def read_manifest(path: Path) -> tuple[Path, bytes, dict[str, Any]]:
    resolved, descriptor, identity, size = open_regular(path, "workflow manifest")
    try:
        require(size <= MAX_MANIFEST_BYTES, "workflow manifest exceeds size bound")
        payload = common.read_exact(descriptor, 0, size)
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], size), "workflow manifest changed")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise VerificationError("workflow manifest is invalid JSON") from exc
    require(payload == canonical_json(value) and value.get("schema") == WORKFLOW_SCHEMA,
            "workflow manifest schema/canonical encoding changed")
    return resolved, payload, value


def preview_directory(path: Path) -> Path:
    supplied = path.lstat()
    require(stat.S_ISDIR(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "preview directory must be a non-symlink directory")
    resolved = path.resolve(strict=True)
    info = resolved.stat(follow_symlinks=False)
    require((info.st_dev, info.st_ino) == (supplied.st_dev, supplied.st_ino),
            "preview directory pathname changed")
    return resolved


def read_preview(path: Path, expected: bytes) -> str:
    resolved, descriptor, identity, size = open_regular(path, f"preview {path.name}")
    try:
        require(size == len(expected), f"preview {path.name} size changed")
        payload = common.read_exact(descriptor, 0, size)
        require(payload == expected, f"preview {path.name} differs from reconstruction")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], size), f"preview {path.name} changed")
        return digest(payload)
    finally:
        os.close(descriptor)


def verify(source_path: Path, output_path: Path, manifest_path: Path,
           preview_dir_path: Path, plan_path: Path, index_path: Path,
           compatibility_path: Path) -> dict[str, Any]:
    manifest, manifest_payload, value = read_manifest(manifest_path)
    require(set(value) == {
        "schema", "source", "plan", "canonical_index",
        "compatibility_report", "edits", "output", "xdvdfs", "patch",
        "claims",
    }, "workflow manifest top-level fields changed")
    plan, plan_payload, edits = read_plan(plan_path)
    source, source_fd, source_identity, source_size = open_regular(
        source_path, "retail source XISO")
    output, output_fd, output_identity, output_size = open_regular(
        output_path, "workflow output XISO")
    try:
        index = index_path.resolve(strict=True)
        compatibility = compatibility_path.resolve(strict=True)
        previews_root = preview_directory(preview_dir_path)
        require(source_size == output_size == common.EXPECTED_XISO_SIZE and
                source_identity != output_identity,
                "source/output XISO size or inode relationship changed")
        require(index.stat().st_size == INDEX_SIZE and
                file_digest(index) == INDEX_SHA256,
                "canonical extracted index hash/size mismatch")
        fixed_paths = {source, output, manifest, previews_root, plan, index, compatibility}
        png_paths = {Path(str(edit["png"])).resolve(strict=True) for edit in edits}
        require(len(fixed_paths) == 7 and not (fixed_paths & png_paths),
                "workflow input/output paths alias")

        source_sha = common.sha256_fd(source_fd)
        require(source_sha == common.EXPECTED_XISO_SHA256,
                "retail source XISO SHA-256 mismatch")
        source_entries, source_directory = common.parse_xdvdfs(source_fd, source_size)
        output_entries, output_directory = common.parse_xdvdfs(output_fd, output_size)
        require(source_entries == output_entries and
                source_directory == output_directory,
                "output XDVDFS tree/layout differs from retail")
        files = [entry for entry in source_entries.values()
                 if not (entry.attributes & 0x10)]
        xbe = source_entries.get("default.xbe")
        require(len(files) == 19 and xbe is not None and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256 and
                common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "source/output default.xbe changed")

        expected_edits: list[dict[str, Any]] = []
        allowed_offsets: set[int] = set()
        selectors: set[str] = set()
        span_ranges: list[tuple[int, int]] = []
        expected_previews: dict[str, bytes] = {}
        verified_pack_hashes: dict[str, str] = {}
        for order, edit in enumerate(edits):
            replacement, previews, import_value = build_import(
                index, compatibility, str(edit["asset_code"]), str(edit["side"]),
                int(edit["variant"]), str(edit["family"]), Path(str(edit["png"])))
            target = import_value["target"]
            selector = (
                f"{target['asset_code']}{target['side']}{target['variant']}:"
                f"{target['family']}"
            )
            require(selector not in selectors, "plan repeats one target")
            selectors.add(selector)
            pack_path = str(target["xiso_pack_path"])
            pack = source_entries.get(pack_path.casefold())
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
                    f"target arithmetic changed for {selector}")
            source_span = common.read_exact(source_fd, absolute, len(replacement))
            output_span = common.read_exact(output_fd, absolute, len(replacement))
            require(digest(source_span) == target["span_sha256"] and
                    output_span == replacement,
                    f"source/replacement span mismatch for {selector}")
            end = absolute + len(replacement)
            require(all(end <= first or absolute >= last for first, last in span_ranges),
                    "target spans overlap")
            span_ranges.append((absolute, end))
            relative = [index_ for index_, (before, after) in enumerate(
                zip(source_span, replacement)) if before != after]
            require(relative, f"replacement equals retail for {selector}")
            absolute_changes = [absolute + offset for offset in relative]
            require(not (allowed_offsets & set(absolute_changes)),
                    "target changed-byte sets overlap")
            allowed_offsets.update(absolute_changes)
            preview_records = []
            for name, payload in previews:
                file_name = f"{order:03d}_{selector.replace(':', '_')}_{name}"
                require(file_name not in expected_previews,
                        "reconstructed preview filename collision")
                expected_previews[file_name] = payload
                preview_records.append({
                    "file_name": file_name, "sha256": digest(payload),
                    "size": len(payload),
                })
            expected_edits.append({
                "order": order, "selector": selector, "target": target,
                "input_png": import_value["input_png"],
                "import_manifest": import_value,
                "import_manifest_sha256": digest(canonical_json(import_value)),
                "replacement_span_sha256": digest(replacement),
                "replacement_span_size": len(replacement),
                "previews": preview_records,
                "absolute_span_offset": absolute,
                "relative_changed_byte_count": len(relative),
                "relative_changed_offsets_u32le_sha256": offset_hash(relative, "<I"),
                "relative_changed_runs": relative_runs(relative),
            })

        require({item.name for item in previews_root.iterdir()} ==
                set(expected_previews),
                "preview directory has missing or extra files")
        preview_hashes = {
            name: read_preview(previews_root / name, payload)
            for name, payload in sorted(expected_previews.items())
        }
        source_sha_after, output_sha, actual = common.compare_and_hash(
            source_fd, output_fd, source_size, allowed_offsets)
        require(source_sha_after == source_sha and actual == sorted(allowed_offsets),
                "full-XISO difference ledger mismatch")

        require(value.get("source") == {
            "path": str(source), "size": source_size,
            "sha256_before": source_sha, "sha256_after": source_sha_after,
            "device": source_identity[0], "inode": source_identity[1],
            "opened_read_only": True, "modified": False,
        }, "manifest source record changed")
        require(value.get("plan") == {
            "path": str(plan), "sha256": digest(plan_payload),
            "edit_count": len(edits),
        } and value.get("canonical_index") == {
            "path": str(index), "size": INDEX_SIZE, "sha256": INDEX_SHA256,
        } and value.get("compatibility_report") == {
            "path": str(compatibility), "sha256": file_digest(compatibility),
        }, "manifest plan/index/compatibility record changed")
        require(value.get("edits") == expected_edits,
                "manifest edit records differ from independent reconstruction")
        output_record = value.get("output", {})
        require(output_record.get("xiso_path") == str(output) and
                output_record.get("xiso_size") == output_size and
                output_record.get("xiso_sha256") == output_sha and
                output_record.get("device") == output_identity[0] and
                output_record.get("inode") == output_identity[1] and
                output_record.get("manifest_path") == str(manifest) and
                output_record.get("preview_directory") == str(previews_root) and
                output_record.get("preview_sha256") == preview_hashes and
                output_record.get("copy_method") in {
                    "copy_file_range", "sendfile", "read_write",
                } and
                output_record.get("exclusively_created") is True,
                "manifest output record changed")
        require(value.get("xdvdfs") == {
            **source_directory, "file_count": len(files),
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
        }, "manifest XDVDFS record changed")
        patch = value.get("patch", {})
        require(patch.get("target_count") == len(edits) and
                patch.get("target_pack_paths") == sorted({
                    str(item["target"]["xiso_pack_path"]) for item in expected_edits}) and
                patch.get("actual_changed_byte_count") == len(actual) and
                patch.get("actual_changed_offsets_u64le_sha256") ==
                    offset_hash(actual, "<Q") and
                patch.get("all_other_xiso_bytes_identical") is True,
                "manifest patch ledger changed")
        claims = value.get("claims", {})
        require(claims.get("actual_live_3d_helmet_resources") is True and
                claims.get("standalone_team_select_helm_cards_modified") is False and
                claims.get("layout_identical_copy_only_xiso") is True and
                claims.get("loader_in_place_decode_guarded") is True and
                claims.get("originals_modified") is False and
                claims.get("runtime_visibility_proved") is False and
                claims.get("xemu_started") is False and
                claims.get("title_executed") is False,
                "manifest claims changed")
        require(common.path_identity(source) == source_identity and
                common.path_identity(output) == output_identity,
                "source/output pathname changed during verification")
        return {
            "schema": SCHEMA,
            "plan_schema": PLAN_SCHEMA,
            "edit_count": len(edits),
            "changed_byte_count": len(actual),
            "output_sha256": output_sha,
            "preview_count": len(preview_hashes),
            "full_difference_ledger_verified": True,
            "source_unchanged": True,
            "runtime_visibility_proved": False,
            "xemu_started": False, "title_executed": False,
        }
    finally:
        os.close(source_fd)
        os.close(output_fd)


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
        result = verify(args.source_xiso, args.output_xiso, args.manifest,
                        args.preview_dir, args.plan, args.index, args.compatibility)
        print(
            "NFL_LIVE_HELMET_TXTR_XISO_VERIFY_PASS "
            f"edits={result['edit_count']} changed={result['changed_byte_count']} "
            f"previews={result['preview_count']} output_sha={result['output_sha256']} "
            "source_unchanged=true runtime=false xemu_started=false"
        )
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
