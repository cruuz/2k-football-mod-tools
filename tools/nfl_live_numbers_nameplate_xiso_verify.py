#!/usr/bin/env python3
"""Independently verify a live number/nameplate copy-only NFL 2K5 XISO."""

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

from nfl_live_numbers_nameplate_png_import import build_import, canonical_json
from nfl_live_numbers_nameplate_targets import DEFAULT_REPORT
from nfl_live_numbers_nameplate_xiso_workflow import (INDEX_SHA256, INDEX_SIZE,
                                                       PLAN_SCHEMA, read_plan)
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_live_numbers_nameplate_xiso_verify/v1"
WORKFLOW_SCHEMA = "nfl2k5_live_numbers_nameplate_xiso_workflow/v1"
MAX_MANIFEST_BYTES = 512 * 1024 * 1024


class VerificationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
    info = os.fstat(descriptor)
    identity = (info.st_dev, info.st_ino)
    require(stat.S_ISREG(info.st_mode) and identity == (supplied.st_dev, supplied.st_ino) and
            common.path_identity(resolved) == identity,
            f"{label} pathname changed")
    return resolved, descriptor, identity, info.st_size


def offset_hash(offsets: list[int], width: str) -> str:
    return digest(b"".join(struct.pack(width, value) for value in offsets))


def verify(source_path: Path, output_path: Path, manifest_path: Path,
           preview_dir_path: Path, plan_path: Path, index_path: Path,
           compatibility_path: Path) -> dict[str, Any]:
    manifest, manifest_fd, manifest_identity, manifest_size = open_regular(
        manifest_path, "workflow manifest")
    require(manifest_size <= MAX_MANIFEST_BYTES, "workflow manifest exceeds bound")
    manifest_payload = common.read_exact(manifest_fd, 0, manifest_size)
    try:
        value = json.loads(manifest_payload)
    except json.JSONDecodeError as exc:
        os.close(manifest_fd)
        raise VerificationError("workflow manifest is invalid JSON") from exc
    require(isinstance(value, dict) and value.get("schema") == WORKFLOW_SCHEMA and
            manifest_payload == canonical_json(value),
            "workflow manifest schema/canonical encoding mismatch")
    plan, plan_payload, edits = read_plan(plan_path)
    require(json.loads(plan_payload).get("schema") == PLAN_SCHEMA,
            "plan schema mismatch")
    source, source_fd, source_identity, source_size = open_regular(
        source_path, "retail source XISO")
    output, output_fd, output_identity, output_size = open_regular(
        output_path, "output XISO")
    try:
        require(source_identity != output_identity and
                source_size == output_size == common.EXPECTED_XISO_SIZE,
                "source/output identity or size mismatch")
        source_sha = common.sha256_fd(source_fd)
        output_sha = common.sha256_fd(output_fd)
        require(source_sha == common.EXPECTED_XISO_SHA256 and
                source_sha == value["source"]["sha256_before"] ==
                value["source"]["sha256_after"] and
                output_sha == value["output"]["xiso_sha256"],
                "source/output SHA-256 differs from workflow")
        require(value["source"]["path"] == str(source) and
                value["output"]["xiso_path"] == str(output) and
                value["output"]["manifest_path"] == str(manifest) and
                value["plan"] == {"path": str(plan), "sha256": digest(plan_payload),
                                  "edit_count": len(edits)},
                "workflow path/plan record mismatch")
        index = index_path.resolve(strict=True)
        compatibility = compatibility_path.resolve(strict=True)
        require(index.stat().st_size == INDEX_SIZE and file_digest(index) == INDEX_SHA256 and
                value["canonical_index"] == {"path": str(index), "size": INDEX_SIZE,
                                             "sha256": INDEX_SHA256} and
                value["compatibility_report"] ==
                {"path": str(compatibility), "sha256": file_digest(compatibility)},
                "canonical index/compatibility identity mismatch")

        source_entries, source_directory = common.parse_xdvdfs(source_fd, source_size)
        output_entries, output_directory = common.parse_xdvdfs(output_fd, output_size)
        require(source_entries == output_entries and source_directory == output_directory and
                value["xdvdfs"]["tree_and_extents_identical"] is True,
                "output XDVDFS tree/extents differ")
        xbe = source_entries.get("default.xbe")
        require(xbe is not None and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256 and
                common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "source/output default.xbe differs")
        assert xbe is not None

        preview_info = preview_dir_path.lstat()
        require(stat.S_ISDIR(preview_info.st_mode) and not stat.S_ISLNK(preview_info.st_mode),
                "preview directory must be a non-symlink directory")
        preview_dir = preview_dir_path.resolve(strict=True)
        require(value["output"]["preview_directory"] == str(preview_dir),
                "preview directory path differs from workflow")
        require(isinstance(value.get("edits"), list) and len(value["edits"]) == len(edits),
                "workflow edit count differs from plan")

        allowed: set[int] = set()
        rebuilt_rows = []
        expected_previews: set[str] = set()
        selectors: set[str] = set()
        for order, (edit, record) in enumerate(zip(edits, value["edits"])):
            digit_value = edit["digit"]
            digit = None if digit_value is None else int(digit_value)
            preview_name = (
                f"{order:03d}_{edit['family']}_{edit['asset_code']}_{edit['side']}_"
                f"{edit['variant']}_{'atlas' if digit is None else digit}.png"
            )
            names = {"span_file": f"{order:03d}_replacement.txtr.bin",
                     "manifest_file": f"{order:03d}_import.json",
                     "preview_file": preview_name}
            replacement, preview, import_value = build_import(
                index, compatibility, str(edit["family"]), str(edit["asset_code"]),
                str(edit["side"]), int(edit["variant"]), digit,
                Path(str(edit["png"])), names)
            target = import_value["target"]
            selector = str(target["selector"])
            require(selector not in selectors, "plan repeats one target")
            selectors.add(selector)
            pack = source_entries.get(str(target["xiso_pack_path"]).casefold())
            require(pack is not None and pack.sector == int(target["xiso_pack_sector"]) and
                    pack.size == int(target["xiso_pack_size"]),
                    f"source pack extent differs for {selector}")
            assert pack is not None
            absolute = pack.byte_offset + int(target["pack_offset"])
            require(absolute == int(target["xiso_absolute_span_offset"]),
                    f"absolute target arithmetic differs for {selector}")
            source_span = common.read_exact(source_fd, absolute, len(replacement))
            output_span = common.read_exact(output_fd, absolute, len(replacement))
            require(digest(source_span) == target["span_sha256"] and
                    output_span == replacement,
                    f"source/output target span mismatch for {selector}")
            relative = [index for index, pair in enumerate(zip(source_span, replacement))
                        if pair[0] != pair[1]]
            absolute_changes = {absolute + item for item in relative}
            require(not (allowed & absolute_changes), "changed-byte sets overlap")
            allowed.update(absolute_changes)
            preview_path = preview_dir / preview_name
            preview_payload = preview_path.read_bytes()
            require(preview_payload == preview and digest(preview_payload) == digest(preview),
                    f"preview differs for {selector}")
            expected_previews.add(preview_name)
            require(record["order"] == order and record["selector"] == selector and
                    record["target"] == target and
                    record["input_png"] == import_value["input_png"] and
                    record["import_manifest"] == import_value and
                    record["import_manifest_sha256"] == digest(canonical_json(import_value)) and
                    record["absolute_span_offset"] == absolute and
                    record["replacement_span_size"] == len(replacement) and
                    record["replacement_span_sha256"] == digest(replacement) and
                    record["relative_changed_byte_count"] == len(relative) and
                    record["relative_changed_offsets_u32le_sha256"] ==
                    offset_hash(relative, "<I") and
                    record["preview_file"] == preview_name and
                    record["preview_sha256"] == digest(preview),
                    f"workflow edit record differs for {selector}")
            rebuilt_rows.append({"selector": selector, "absolute_offset": absolute,
                                 "span_size": len(replacement),
                                 "replacement_sha256": digest(replacement),
                                 "changed_byte_count": len(relative)})
        actual_preview_names = {
            path.name for path in preview_dir.iterdir()
            if path.is_file() and not path.is_symlink()
        }
        require(actual_preview_names == expected_previews,
                "preview directory file set differs")
        source_after, output_after, actual = common.compare_and_hash(
            source_fd, output_fd, source_size, allowed)
        require(source_after == source_sha and output_after == output_sha and
                actual == sorted(allowed) and
                value["patch"]["edit_count"] == len(edits) and
                value["patch"]["changed_byte_count"] == len(actual) and
                value["patch"]["changed_offsets_u64le_sha256"] ==
                offset_hash(actual, "<Q") and
                value["patch"]["all_changed_bytes_inside_selected_spans"] is True and
                value["patch"]["all_other_xiso_bytes_identical"] is True,
                "full-image difference ledger mismatch")
        require(common.path_identity(source) == source_identity and
                common.path_identity(output) == output_identity and
                common.path_identity(manifest) == manifest_identity,
                "verified pathname identity changed")
        return {
            "schema": SCHEMA,
            "source_xiso": {"path": str(source), "sha256": source_sha,
                            "size": source_size, "modified": False},
            "output_xiso": {"path": str(output), "sha256": output_sha,
                            "size": output_size},
            "manifest": {"path": str(manifest), "sha256": digest(manifest_payload)},
            "plan": {"path": str(plan), "sha256": digest(plan_payload)},
            "edits": rebuilt_rows,
            "verification": {"edit_count": len(edits),
                             "changed_byte_count": len(actual),
                             "all_other_bytes_identical": True,
                             "xdvdfs_tree_and_extents_identical": True,
                             "default_xbe_identical": True,
                             "all_imports_rebuilt_independently": True,
                             "all_previews_rebuilt_independently": True},
            "claims": {"offline_transport_proved": True,
                       "retail_source_modified": False,
                       "xemu_started": False, "title_executed": False,
                       "runtime_visibility_proved": False},
        }
    finally:
        os.close(manifest_fd)
        os.close(source_fd)
        os.close(output_fd)


def write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o644)
    try:
        offset = 0
        while offset < len(payload):
            amount = os.write(descriptor, payload[offset:])
            require(amount > 0, "short verifier-report write")
            offset += amount
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", type=Path, default=root / "ESPN NFL 2K5 (USA).xiso.iso")
    parser.add_argument("--output-xiso", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output_report.exists(), "output verifier report already exists")
        report = verify(args.source_xiso, args.output_xiso, args.manifest,
                        args.preview_dir, args.plan, args.index, args.compatibility)
        write_exclusive(args.output_report, canonical_json(report))
        print("NFL_LIVE_NUMBERS_NAMEPLATE_XISO_VERIFY_PASS "
              f"edits={report['verification']['edit_count']} "
              f"changed={report['verification']['changed_byte_count']} "
              f"sha256={report['output_xiso']['sha256']} runtime=false")
        return 0
    except (VerificationError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
