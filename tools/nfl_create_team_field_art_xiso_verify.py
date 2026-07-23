#!/usr/bin/env python3
"""Read-only verifier for a create-team field-art copy-only NFL 2K5 XISO."""

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

from nfl_create_team_field_art_png_import import build_import, canonical_json
from nfl_create_team_field_art_xiso_workflow import SCHEMA
import nfl_uniform_color_xiso_direct_patch as common


class VerifyError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def offset_hash(offsets: list[int], width: str) -> str:
    return digest(b"".join(struct.pack(width, value) for value in offsets))


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def regular(path: Path, label: str) -> Path:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    current = resolved.stat(follow_symlinks=False)
    require((current.st_dev, current.st_ino) == (supplied.st_dev, supplied.st_ino),
            f"{label} identity changed")
    return resolved


def load_manifest(path: Path) -> tuple[Path, bytes, dict[str, Any]]:
    resolved = regular(path, "manifest")
    payload = resolved.read_bytes()
    require(len(payload) <= 64 * 1024 * 1024, "manifest is too large")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise VerifyError("manifest is invalid JSON") from exc
    require(payload == canonical_json(value) and isinstance(value, dict) and
            value.get("schema") == SCHEMA and isinstance(value.get("edits"), list) and
            bool(value["edits"]), "manifest schema/canonical encoding mismatch")
    return resolved, payload, value


def run(source_path: Path, output_path: Path, manifest_path: Path) -> dict[str, object]:
    source = regular(source_path, "source XISO")
    output = regular(output_path, "output XISO")
    manifest_file, _payload, manifest = load_manifest(manifest_path)
    require(source != output and source.stat().st_size == common.EXPECTED_XISO_SIZE and
            output.stat().st_size == common.EXPECTED_XISO_SIZE,
            "source/output size or alias check failed")
    require(Path(manifest["source"]["path"]).resolve(strict=True) == source and
            Path(manifest["output"]["xiso_path"]).resolve(strict=True) == output and
            Path(manifest["output"]["manifest_path"]).resolve(strict=True) == manifest_file,
            "manifest paths do not identify supplied files")
    index = regular(Path(manifest["canonical_index"]["path"]), "canonical index")
    inventory = regular(Path(manifest["inventory"]["path"]), "inventory")
    require(file_digest(index) == manifest["canonical_index"]["sha256"] and
            file_digest(inventory) == manifest["inventory"]["sha256"],
            "canonical index/inventory hash changed")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    output_fd = os.open(output, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    try:
        require(common.sha256_fd(source_fd) == common.EXPECTED_XISO_SHA256 ==
                manifest["source"]["sha256_before"] == manifest["source"]["sha256_after"],
                "source XISO hash changed")
        source_entries, source_directory = common.parse_xdvdfs(
            source_fd, common.EXPECTED_XISO_SIZE)
        output_entries, output_directory = common.parse_xdvdfs(
            output_fd, common.EXPECTED_XISO_SIZE)
        require(source_entries == output_entries and source_directory == output_directory and
                manifest["xdvdfs"]["tree_identical_after_patch"] is True and
                manifest["xdvdfs"]["all_sector_extents_preserved"] is True,
                "XDVDFS tree/extents differ")
        pack = source_entries.get("vc_53450030/0")
        xbe = source_entries.get("default.xbe")
        require(pack is not None and pack.byte_offset == 1_631_188_992 and
                pack.size == 193_710_080 and xbe is not None and
                common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "pack-0/default.xbe mapping changed")

        allowed: set[int] = set()
        selectors: set[str] = set()
        rebuilt_count = 0
        for order, edit in enumerate(manifest["edits"]):
            require(type(edit) is dict and edit.get("order") == order and
                    type(edit.get("target")) is dict and
                    type(edit.get("input_png")) is dict,
                    "manifest edit shape/order changed")
            target = edit["target"]
            selector = str(target["selector"])
            require(selector == edit["selector"] and selector not in selectors,
                    "manifest repeats or mismatches a selector")
            selectors.add(selector)
            replacement, previews, import_value = build_import(
                index, inventory, int(target["logo_code"]),
                str(target["weather_suffix"]), str(target["name"]),
                Path(edit["input_png"]["path"]))
            require(digest(canonical_json(import_value)) ==
                    edit["import_manifest_sha256"] and
                    import_value == edit["import_manifest"] and
                    digest(replacement) == edit["replacement_span_sha256"] and
                    len(replacement) == edit["replacement_span_size"],
                    f"independent import rebuild differs for {selector}")
            absolute = (pack.byte_offset + int(target["pack_offset"]) +
                        int(target["chunk_offset"]))
            require(absolute == edit["absolute_span_offset"],
                    f"absolute target arithmetic differs for {selector}")
            source_span = common.read_exact(source_fd, absolute, len(replacement))
            output_span = common.read_exact(output_fd, absolute, len(replacement))
            require(digest(source_span) == target["span_sha256"] and
                    output_span == replacement,
                    f"source/output span identity differs for {selector}")
            relative = [position for position, (before, after) in enumerate(
                zip(source_span, replacement)) if before != after]
            require(len(relative) == edit["relative_changed_byte_count"] and
                    offset_hash(relative, "<I") ==
                    edit["relative_changed_offsets_u32le_sha256"],
                    f"relative changed-byte ledger differs for {selector}")
            absolute_changes = {absolute + position for position in relative}
            require(not (allowed & absolute_changes), "edit changed-byte sets overlap")
            allowed.update(absolute_changes)

            expected_previews = {name: digest(payload) for name, payload in previews}
            manifest_previews = {row["file_name"]: row["sha256"]
                                 for row in edit["previews"]}
            prefix = f"{order:03d}_{selector.replace(':', '_')}_"
            require({prefix + name: value for name, value in expected_previews.items()} ==
                    manifest_previews, f"preview manifest differs for {selector}")
            rebuilt_count += 1

        preview_dir = Path(manifest["output"]["preview_directory"]).resolve(strict=True)
        require(preview_dir.is_dir() and not preview_dir.is_symlink(),
                "preview directory changed")
        actual_previews = {}
        for child in preview_dir.iterdir():
            require(child.is_file() and not child.is_symlink(),
                    "preview contains a non-regular file")
            actual_previews[child.name] = file_digest(child)
        require(actual_previews == manifest["output"]["preview_sha256"],
                "preview directory hash set changed")

        source_sha_after, output_sha, actual = common.compare_and_hash(
            source_fd, output_fd, common.EXPECTED_XISO_SIZE, allowed)
        require(source_sha_after == common.EXPECTED_XISO_SHA256 and
                output_sha == manifest["output"]["xiso_sha256"] and
                actual == sorted(allowed) and
                len(actual) == manifest["patch"]["actual_changed_byte_count"] and
                offset_hash(actual, "<Q") ==
                manifest["patch"]["actual_changed_offsets_u64le_sha256"] and
                manifest["patch"]["all_other_xiso_bytes_identical"] is True,
                "full-XISO hash/difference ledger changed")
        require(manifest["claims"]["runtime_visibility_proved"] is False and
                manifest["claims"]["xemu_started"] is False and
                manifest["claims"]["title_executed"] is False and
                manifest["claims"]["originals_modified"] is False,
                "manifest overstates runtime/original status")
        return {"edit_count": rebuilt_count, "changed_byte_count": len(actual),
                "source_sha256": source_sha_after, "output_sha256": output_sha,
                "xdvdfs_identical": True, "runtime_visibility_proved": False}
    finally:
        os.close(source_fd)
        os.close(output_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", type=Path, required=True)
    parser.add_argument("--output-xiso", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest)
        print("NFL_CREATE_TEAM_FIELD_ART_XISO_VERIFY_PASS "
              f"edits={result['edit_count']} changed={result['changed_byte_count']} "
              f"output_sha={result['output_sha256']} xdvdfs_identical=true "
              "runtime=false xemu_started=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
