#!/usr/bin/env python3
"""Independently verify a copy-only NFL 2K5 Team Select card XISO."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

from nfl_team_select_card_png_import import build_import, canonical_json
from nfl_team_select_card_targets import DEFAULT_REPORT
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_team_select_card_xiso_verify/v1"
WORKFLOW_SCHEMA = "nfl2k5_team_select_card_xiso_workflow/v1"
PLAN_SCHEMA = "nfl2k5_team_select_card_plan/v1"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
MAX_MANIFEST_BYTES = 512 * 1024 * 1024
MAX_PLAN_BYTES = 64 * 1024 * 1024
MAX_EDITS = 1_902

TOP_LEVEL_FIELDS = {
    "schema", "source", "plan", "canonical_index",
    "compatibility_report", "edits", "output", "xdvdfs", "patch",
    "claims",
}
PLAN_FIELDS = {"schema", "purpose", "edits"}
PLAN_EDIT_FIELDS = {
    "family", "asset_code", "side", "style", "resolution", "png",
}
OUTPUT_FIELDS = {
    "xiso_path", "xiso_size", "xiso_sha256", "device", "inode",
    "copy_method", "manifest_path", "preview_directory", "preview_sha256",
    "exclusively_created",
}


class VerificationError(ValueError):
    """Raised when any supplied artifact fails the proved workflow contract."""


@dataclass(frozen=True)
class OpenRegular:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    size: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def open_regular(path: Path, label: str) -> OpenRegular:
    """Open a final-component non-symlink regular file and pin its inode."""
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise VerificationError(f"{label} does not exist") from exc
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        require(stat.S_ISREG(info.st_mode) and
                identity == (supplied.st_dev, supplied.st_ino) and
                common.path_identity(resolved) == identity,
                f"{label} pathname changed while opening")
        return OpenRegular(resolved, descriptor, identity, info.st_size)
    except Exception:
        os.close(descriptor)
        raise


def read_pinned(opened: OpenRegular, maximum: int, label: str) -> bytes:
    require(opened.size <= maximum, f"{label} exceeds bounded input size")
    return common.read_exact(opened.descriptor, 0, opened.size)


def verify_pin(opened: OpenRegular, label: str, expected_sha256: str | None = None,
               expected_payload: bytes | None = None) -> None:
    info = os.fstat(opened.descriptor)
    require(stat.S_ISREG(info.st_mode) and info.st_size == opened.size and
            common.fd_identity(opened.descriptor) == opened.identity and
            common.path_identity(opened.path) == opened.identity,
            f"{label} pathname, inode, or size changed")
    if expected_payload is not None:
        require(common.read_exact(opened.descriptor, 0, opened.size) ==
                expected_payload, f"{label} content changed")
    if expected_sha256 is not None:
        require(common.sha256_fd(opened.descriptor) == expected_sha256,
                f"{label} SHA-256 changed")


def parse_canonical_json(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"{label} is invalid JSON") from exc
    require(isinstance(value, dict) and payload == canonical_json(value),
            f"{label} is not a canonical JSON object")
    return value


def validate_plan(value: dict[str, Any]) -> list[dict[str, Any]]:
    require(set(value) == PLAN_FIELDS and value.get("schema") == PLAN_SCHEMA and
            isinstance(value.get("purpose"), str) and value["purpose"] != "" and
            isinstance(value.get("edits"), list) and
            1 <= len(value["edits"]) <= MAX_EDITS,
            "plan schema/count mismatch")
    result: list[dict[str, Any]] = []
    for record in value["edits"]:
        require(isinstance(record, dict) and set(record) == PLAN_EDIT_FIELDS,
                "plan edit fields mismatch")
        require(isinstance(record["family"], str) and
                isinstance(record["asset_code"], str) and
                isinstance(record["side"], str) and
                isinstance(record["png"], str) and record["png"] != "" and
                isinstance(record["style"], int) and
                not isinstance(record["style"], bool) and
                isinstance(record["resolution"], int) and
                not isinstance(record["resolution"], bool),
                "plan edit value types mismatch")
        result.append(record)
    return result


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


def pin_preview_directory(path: Path) -> tuple[Path, tuple[int, int]]:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise VerificationError("preview directory does not exist") from exc
    require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "preview directory must be a non-symlink directory")
    resolved = path.resolve(strict=True)
    current = resolved.stat(follow_symlinks=False)
    identity = (current.st_dev, current.st_ino)
    require(stat.S_ISDIR(current.st_mode), "preview path is not a directory")
    return resolved, identity


def read_exact_preview(path: Path, expected: bytes) -> str:
    opened = open_regular(path, f"preview {path.name}")
    try:
        require(opened.size == len(expected),
                f"preview {path.name} size mismatch")
        payload = common.read_exact(opened.descriptor, 0, opened.size)
        require(payload == expected, f"preview {path.name} content mismatch")
        verify_pin(opened, f"preview {path.name}", expected_payload=payload)
        return digest(payload)
    finally:
        os.close(opened.descriptor)


def verify_png_record(plan_path: Path, input_record: dict[str, Any]) -> None:
    resolved = plan_path.resolve(strict=True)
    require(str(resolved) == input_record.get("path"),
            "rebuilt import PNG path differs from plan")
    opened = open_regular(resolved, f"input PNG {resolved.name}")
    try:
        require(opened.size == input_record.get("size") and
                common.sha256_fd(opened.descriptor) == input_record.get("sha256"),
                f"input PNG {resolved.name} identity changed")
        verify_pin(opened, f"input PNG {resolved.name}",
                   expected_sha256=str(input_record["sha256"]))
    finally:
        os.close(opened.descriptor)


def verify(source_path: Path, output_path: Path, manifest_path: Path,
           preview_dir_path: Path, plan_path: Path, index_path: Path,
           compatibility_path: Path) -> dict[str, Any]:
    manifest_pin = open_regular(manifest_path, "workflow manifest")
    plan_pin: OpenRegular | None = None
    source_pin: OpenRegular | None = None
    output_pin: OpenRegular | None = None
    index_pin: OpenRegular | None = None
    compatibility_pin: OpenRegular | None = None
    png_pins: list[OpenRegular] = []
    try:
        manifest_payload = read_pinned(
            manifest_pin, MAX_MANIFEST_BYTES, "workflow manifest")
        manifest_value = parse_canonical_json(
            manifest_payload, "workflow manifest")
        require(set(manifest_value) == TOP_LEVEL_FIELDS and
                manifest_value.get("schema") == WORKFLOW_SCHEMA,
                "workflow manifest schema/fields mismatch")

        plan_pin = open_regular(plan_path, "edit plan")
        plan_payload = read_pinned(plan_pin, MAX_PLAN_BYTES, "edit plan")
        plan_value = parse_canonical_json(plan_payload, "edit plan")
        edits = validate_plan(plan_value)

        source_pin = open_regular(source_path, "retail source XISO")
        output_pin = open_regular(output_path, "workflow output XISO")
        require(source_pin.size == common.EXPECTED_XISO_SIZE and
                output_pin.size == common.EXPECTED_XISO_SIZE,
                "source/output XISO size mismatch")
        require(source_pin.identity != output_pin.identity,
                "source and output XISOs alias one inode")

        index_pin = open_regular(index_path, "canonical extracted index")
        compatibility_pin = open_regular(
            compatibility_path, "compatibility report")
        require(index_pin.size == INDEX_SIZE and
                common.sha256_fd(index_pin.descriptor) == INDEX_SHA256,
                "canonical extracted index hash/size mismatch")
        compatibility_sha = common.sha256_fd(compatibility_pin.descriptor)

        preview_dir, preview_identity = pin_preview_directory(preview_dir_path)
        plan_pngs = [Path(str(edit["png"])) for edit in edits]
        # Reproduce the writer/importer's final-component symlink rejection;
        # resolving first would otherwise accidentally weaken that contract.
        resolved_pngs: list[Path] = []
        for path in plan_pngs:
            opened = open_regular(path, f"input PNG {path.name}")
            png_pins.append(opened)
            resolved_pngs.append(opened.path)
        path_set = {
            source_pin.path, output_pin.path, manifest_pin.path, preview_dir,
            plan_pin.path, index_pin.path, compatibility_pin.path, *resolved_pngs,
        }
        require(len(path_set) == 7 + len(edits),
                "workflow paths alias")

        source_sha_before = common.sha256_fd(source_pin.descriptor)
        require(source_sha_before == common.EXPECTED_XISO_SHA256,
                "retail source XISO SHA-256 mismatch")
        source_entries, source_directory = common.parse_xdvdfs(
            source_pin.descriptor, source_pin.size)
        output_entries, output_directory = common.parse_xdvdfs(
            output_pin.descriptor, output_pin.size)
        require(source_entries == output_entries and
                source_directory == output_directory,
                "output XDVDFS tree/layout differs from retail source")
        files = [entry for entry in source_entries.values()
                 if not (entry.attributes & 0x10)]
        require(len(files) == 19, "retail XDVDFS file count changed")
        xbe = source_entries.get("default.xbe")
        require(xbe is not None and xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source_pin.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256 and
                common.sha256_fd(output_pin.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "source/output default.xbe identity changed")

        expected_edits: list[dict[str, Any]] = []
        selectors: set[str] = set()
        span_ranges: list[tuple[int, int]] = []
        allowed_offsets: set[int] = set()
        target_pack_paths: set[str] = set()
        preview_payloads: dict[str, bytes] = {}
        pack_hashes: dict[str, str] = {}

        for order, (edit, png_path, png_resolved, png_pin) in enumerate(
                zip(edits, plan_pngs, resolved_pngs, png_pins)):
            family = edit["family"]
            asset_code = edit["asset_code"]
            side = edit["side"]
            style = edit["style"]
            resolution = edit["resolution"]
            preview_name = (
                f"{order:03d}_{family}_{asset_code}_{side}_{style}_{resolution}.png"
            )
            output_names = {
                "span_file": f"{order:03d}_replacement.txtr.bin",
                "manifest_file": f"{order:03d}_import.json",
                "preview_file": preview_name,
            }
            replacement, preview, import_value = build_import(
                index_pin.path, compatibility_pin.path, family, asset_code, side,
                style, resolution, png_path, output_names)
            target = import_value["target"]
            require(isinstance(target, dict), "rebuilt import target is invalid")
            selector = str(target["selector"])
            require(selector not in selectors,
                    "plan repeats one target selector")
            selectors.add(selector)

            pack_path = str(target["pack_path"])
            pack = source_entries.get(pack_path.casefold())
            require(pack is not None and
                    pack.sector == int(target["pack_sector"]) and
                    pack.size == int(target["pack_size"]),
                    f"source pack extent changed for {selector}")
            assert pack is not None
            if pack_path not in pack_hashes:
                pack_hashes[pack_path] = common.sha256_fd(
                    source_pin.descriptor, pack.byte_offset, pack.size)
            require(pack_hashes[pack_path] == target["pack_sha256"],
                    f"source pack identity changed for {selector}")
            absolute = pack.byte_offset + int(target["span_pack_offset"])
            require(absolute == int(target["xiso_absolute_span_offset"]) and
                    absolute >= pack.byte_offset and
                    absolute + len(replacement) <= pack.byte_offset + pack.size,
                    f"XISO target arithmetic changed for {selector}")
            source_span = common.read_exact(
                source_pin.descriptor, absolute, len(replacement))
            output_span = common.read_exact(
                output_pin.descriptor, absolute, len(replacement))
            require(digest(source_span) == target["span_sha256"],
                    f"retail source span changed for {selector}")
            require(output_span == replacement,
                    f"output replacement differs from deterministic import for {selector}")
            after = absolute + len(replacement)
            require(all(after <= first or absolute >= last
                        for first, last in span_ranges),
                    "plan target spans overlap")
            span_ranges.append((absolute, after))

            relative = [
                index for index, (before, changed) in enumerate(
                    zip(source_span, replacement)) if before != changed
            ]
            require(relative, f"replacement equals retail for {selector}")
            absolute_changes = [absolute + value for value in relative]
            require(not (set(absolute_changes) & allowed_offsets),
                    "plan changed-byte sets overlap")
            allowed_offsets.update(absolute_changes)
            runs = relative_runs(relative)
            preview_payloads[preview_name] = preview
            target_pack_paths.add(pack_path)
            verify_png_record(png_path, import_value["input_png"])
            require(str(png_resolved) == import_value["input_png"]["path"] and
                    png_pin.size == import_value["input_png"]["size"] and
                    common.sha256_fd(png_pin.descriptor) ==
                    import_value["input_png"]["sha256"],
                    f"pinned input PNG changed for {selector}")
            expected_edits.append({
                "order": order,
                "selector": selector,
                "target": target,
                "input_png": import_value["input_png"],
                "import_manifest": import_value,
                "import_manifest_sha256": digest(canonical_json(import_value)),
                "replacement_span_sha256": digest(replacement),
                "replacement_span_size": len(replacement),
                "preview_file": preview_name,
                "preview_sha256": digest(preview),
                "absolute_span_offset": absolute,
                "relative_changed_byte_count": len(relative),
                "relative_changed_offsets_u32le_sha256":
                    offset_hash(relative, "<I"),
                "relative_changed_runs": runs,
            })

        actual_preview_names = set(os.listdir(preview_dir))
        require(actual_preview_names == set(preview_payloads),
                "preview directory file set mismatch")
        preview_hashes = {
            name: read_exact_preview(preview_dir / name, payload)
            for name, payload in sorted(preview_payloads.items())
        }

        source_sha_after, output_sha, actual = common.compare_and_hash(
            source_pin.descriptor, output_pin.descriptor, source_pin.size,
            allowed_offsets)
        require(source_sha_after == source_sha_before and
                actual == sorted(allowed_offsets),
                "source hash or full-image difference ledger mismatch")

        output_record = manifest_value.get("output")
        require(isinstance(output_record, dict) and
                set(output_record) == OUTPUT_FIELDS and
                output_record.get("copy_method") in
                {"copy_file_range", "pread_pwrite"},
                "workflow output record fields/copy method mismatch")
        expected_manifest: dict[str, Any] = {
            "schema": WORKFLOW_SCHEMA,
            "source": {
                "path": str(source_pin.path), "size": source_pin.size,
                "sha256_before": source_sha_before,
                "sha256_after": source_sha_after,
                "device": source_pin.identity[0],
                "inode": source_pin.identity[1],
                "opened_read_only": True, "modified": False,
            },
            "plan": {
                "path": str(plan_pin.path), "sha256": digest(plan_payload),
                "edit_count": len(edits),
            },
            "canonical_index": {
                "path": str(index_pin.path), "size": INDEX_SIZE,
                "sha256": INDEX_SHA256,
            },
            "compatibility_report": {
                "path": str(compatibility_pin.path),
                "sha256": compatibility_sha,
            },
            "edits": expected_edits,
            "output": {
                "xiso_path": str(output_pin.path),
                "xiso_size": output_pin.size,
                "xiso_sha256": output_sha,
                "device": output_pin.identity[0],
                "inode": output_pin.identity[1],
                "copy_method": output_record["copy_method"],
                "manifest_path": str(manifest_pin.path),
                "preview_directory": str(preview_dir),
                "preview_sha256": preview_hashes,
                "exclusively_created": True,
            },
            "xdvdfs": {
                **source_directory, "file_count": len(files),
                "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
            },
            "patch": {
                "target_count": len(expected_edits),
                "target_pack_paths": sorted(target_pack_paths),
                "actual_changed_byte_count": len(actual),
                "actual_changed_offsets_u64le_sha256": offset_hash(actual, "<Q"),
                "all_other_xiso_bytes_identical": True,
            },
            "claims": {
                "standalone_team_select_cards_only": True,
                "layout_identical_copy_only_xiso": True,
                "originals_modified": False,
                "retail_artwork_exported_or_bundled": False,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "title_executed": False,
                "portme": (
                    "PORTME(runtime): capture each edited card in Team Select "
                    "before claiming visibility."
                ),
            },
        }
        require(manifest_payload == canonical_json(expected_manifest),
                "workflow manifest differs from independent reconstruction")

        verify_pin(manifest_pin, "workflow manifest",
                   expected_payload=manifest_payload)
        verify_pin(plan_pin, "edit plan", expected_payload=plan_payload)
        verify_pin(index_pin, "canonical extracted index",
                   expected_sha256=INDEX_SHA256)
        verify_pin(compatibility_pin, "compatibility report",
                   expected_sha256=compatibility_sha)
        verify_pin(source_pin, "retail source XISO")
        verify_pin(output_pin, "workflow output XISO")
        for opened, record in zip(png_pins, expected_edits):
            verify_pin(
                opened, f"input PNG {opened.path.name}",
                expected_sha256=str(record["input_png"]["sha256"]))
        current_preview = preview_dir.stat(follow_symlinks=False)
        require((current_preview.st_dev, current_preview.st_ino) ==
                preview_identity and
                set(os.listdir(preview_dir)) == set(preview_payloads),
                "preview directory changed during verification")

        return {
            "schema": SCHEMA,
            "verified_workflow_schema": WORKFLOW_SCHEMA,
            "edit_count": len(expected_edits),
            "selectors": [record["selector"] for record in expected_edits],
            "source_sha256": source_sha_after,
            "output_sha256": output_sha,
            "changed_bytes": len(actual),
            "xdvdfs_file_count": len(files),
            "runtime_visibility_proved": False,
        }
    finally:
        for opened in png_pins:
            os.close(opened.descriptor)
        for opened in (
            compatibility_pin, index_pin, output_pin, source_pin, plan_pin,
            manifest_pin,
        ):
            if opened is not None:
                os.close(opened.descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument(
        "--index", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        result = verify(
            args.source_xiso, args.output_xiso, args.manifest,
            args.preview_dir, args.plan, args.index, args.compatibility)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
