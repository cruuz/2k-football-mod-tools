#!/usr/bin/env python3
"""Independently verify a copied NFL 2K5 numeric-portrait XISO."""

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

from nfl_player_portrait_png_import import build_import, canonical_json
from nfl_player_portrait_targets import DEFAULT_REPORT
from nfl_player_portrait_xiso_workflow import (PLAN_SCHEMA, SCHEMA as WORKFLOW_SCHEMA,
                                               absolute_for_relative, read_plan,
                                               relative_runs)
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_player_portrait_xiso_verify/v1"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
MAX_MANIFEST_BYTES = 512 * 1024 * 1024


class VerificationError(ValueError):
    pass


@dataclass(frozen=True)
class OpenRegular:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    size: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def offset_hash(offsets: list[int], width: str) -> str:
    return digest(b"".join(struct.pack(width, value) for value in offsets))


def open_regular(path: Path, label: str) -> OpenRegular:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
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


def verify_pin(opened: OpenRegular, label: str) -> None:
    info = os.fstat(opened.descriptor)
    require(stat.S_ISREG(info.st_mode) and info.st_size == opened.size and
            common.fd_identity(opened.descriptor) == opened.identity and
            common.path_identity(opened.path) == opened.identity,
            f"{label} pathname/inode/size changed")


def canonical_object(opened: OpenRegular, label: str) -> tuple[bytes, dict[str, Any]]:
    require(opened.size <= MAX_MANIFEST_BYTES, f"{label} exceeds bounded input size")
    payload = common.read_exact(opened.descriptor, 0, opened.size)
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"{label} is invalid JSON") from exc
    require(isinstance(value, dict) and payload == canonical_json(value),
            f"{label} is not canonical JSON")
    return payload, value


def read_preview(path: Path, expected: bytes) -> str:
    opened = open_regular(path, f"preview {path.name}")
    try:
        require(opened.size == len(expected) and
                common.read_exact(opened.descriptor, 0, opened.size) == expected,
                f"preview {path.name} content changed")
        verify_pin(opened, f"preview {path.name}")
        return digest(expected)
    finally:
        os.close(opened.descriptor)


def verify(source_path: Path, output_path: Path, manifest_path: Path,
           preview_dir_path: Path, plan_path: Path, index_path: Path,
           compatibility_path: Path) -> dict[str, Any]:
    source = open_regular(source_path, "retail source XISO")
    output = open_regular(output_path, "portrait output XISO")
    manifest = open_regular(manifest_path, "portrait workflow manifest")
    index = open_regular(index_path, "canonical extracted index")
    compatibility = open_regular(compatibility_path, "portrait compatibility report")
    try:
        manifest_payload, recorded = canonical_object(manifest, "portrait workflow manifest")
        require(recorded.get("schema") == WORKFLOW_SCHEMA and
                set(recorded) == {"schema", "source", "plan", "canonical_index",
                                  "compatibility_report", "edits", "output", "xdvdfs",
                                  "patch", "claims"},
                "portrait workflow manifest schema/fields changed")
        plan, plan_payload, edits = read_plan(plan_path)
        require(source.size == output.size == common.EXPECTED_XISO_SIZE and
                source.identity != output.identity and index.size == INDEX_SIZE and
                common.sha256_fd(index.descriptor) == INDEX_SHA256,
                "portrait source/output/index identity changed")
        source_sha = common.sha256_fd(source.descriptor)
        require(source_sha == common.EXPECTED_XISO_SHA256,
                "retail source XISO SHA-256 changed")
        compatibility_sha = common.sha256_fd(compatibility.descriptor)

        preview_info = preview_dir_path.lstat()
        require(stat.S_ISDIR(preview_info.st_mode) and
                not stat.S_ISLNK(preview_info.st_mode),
                "portrait preview directory must be a non-symlink directory")
        preview_dir = preview_dir_path.resolve(strict=True)
        path_set = {source.path, output.path, manifest.path, index.path,
                    compatibility.path, plan, preview_dir}
        png_paths: list[Path] = []
        for edit in edits:
            png = Path(edit["png"])
            supplied = png.lstat()
            require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
                    "portrait plan PNG must be a non-symlink regular file")
            png_paths.append(png.resolve(strict=True))
        path_set.update(png_paths)
        require(len(path_set) == 7 + len(edits), "portrait verifier paths alias")

        source_entries, source_directory = common.parse_xdvdfs(source.descriptor, source.size)
        output_entries, output_directory = common.parse_xdvdfs(output.descriptor, output.size)
        require(source_entries == output_entries and source_directory == output_directory,
                "portrait output XDVDFS tree/layout changed")
        files = [entry for entry in source_entries.values() if not (entry.attributes & 0x10)]
        xbe = source_entries.get("default.xbe")
        require(len(files) == 19 and xbe is not None and
                xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256 and
                common.sha256_fd(output.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "portrait source/output default.xbe changed")

        selectors: set[str] = set()
        logical_ranges: list[tuple[int, int]] = []
        allowed_offsets: set[int] = set()
        expected_edits: list[dict[str, Any]] = []
        expected_previews: dict[str, bytes] = {}
        pack_hashes: dict[str, str] = {}
        for order, (edit, png_path) in enumerate(zip(edits, png_paths)):
            portrait_id = edit["portrait_id"]
            preview_name = f"{order:04d}_portrait_{portrait_id}.png"
            names = {"span_file": f"{order:04d}_replacement.txtr.bin",
                     "manifest_file": f"{order:04d}_import.json",
                     "preview_file": preview_name}
            replacement, preview, import_value = build_import(
                index.path, compatibility.path, portrait_id, Path(edit["png"]), names)
            target = import_value["target"]
            selector = str(target["selector"])
            require(selector not in selectors, "portrait plan repeats one selector")
            selectors.add(selector)
            segments = list(target["span_segments"])
            source_pieces: list[bytes] = []
            output_pieces: list[bytes] = []
            normalized: list[dict[str, Any]] = []
            for segment in segments:
                pack_path = str(segment["pack_path"])
                pack = source_entries.get(pack_path.casefold())
                require(pack is not None and pack.sector == int(segment["pack_sector"]) and
                        pack.size == int(segment["pack_size"]),
                        f"portrait source pack extent changed for {selector}")
                assert pack is not None
                if pack_path not in pack_hashes:
                    pack_hashes[pack_path] = common.sha256_fd(
                        source.descriptor, pack.byte_offset, pack.size)
                require(pack_hashes[pack_path] == segment["pack_sha256"],
                        f"portrait source pack hash changed for {selector}")
                absolute = pack.byte_offset + int(segment["pack_offset"])
                require(absolute == int(segment["xiso_absolute_offset"]),
                        f"portrait segment arithmetic changed for {selector}")
                size = int(segment["size"])
                source_pieces.append(common.read_exact(source.descriptor, absolute, size))
                output_pieces.append(common.read_exact(output.descriptor, absolute, size))
                normalized.append({**segment, "xiso_absolute_offset": absolute})
            source_span = b"".join(source_pieces)
            output_span = b"".join(output_pieces)
            require(digest(source_span) == target["span_sha256"] and
                    output_span == replacement,
                    f"portrait source/replacement span changed for {selector}")
            logical_start = int(target["chunk_offset"])
            logical_end = logical_start + len(replacement)
            require(all(logical_end <= first or logical_start >= last
                        for first, last in logical_ranges),
                    "portrait target spans overlap")
            logical_ranges.append((logical_start, logical_end))
            relative = [i for i, (before, after) in
                        enumerate(zip(source_span, replacement)) if before != after]
            require(relative, f"portrait replacement equals retail for {selector}")
            absolute_changes = [absolute_for_relative(normalized, value)
                                for value in relative]
            require(not (set(absolute_changes) & allowed_offsets),
                    "portrait changed-byte sets overlap")
            allowed_offsets.update(absolute_changes)
            expected_previews[preview_name] = preview
            expected_edits.append({
                "order": order, "selector": selector, "target": target,
                "input_png": import_value["input_png"],
                "import_manifest": import_value,
                "import_manifest_sha256": digest(canonical_json(import_value)),
                "replacement_span_sha256": digest(replacement),
                "replacement_span_size": len(replacement),
                "preview_file": preview_name, "preview_sha256": digest(preview),
                "absolute_span_segments": normalized,
                "relative_changed_byte_count": len(relative),
                "relative_changed_offsets_u32le_sha256": offset_hash(relative, "<I"),
                "relative_changed_runs": relative_runs(relative),
            })
            png_open = open_regular(png_path, f"portrait PNG {png_path.name}")
            try:
                require(png_open.size == import_value["input_png"]["size"] and
                        common.sha256_fd(png_open.descriptor) ==
                        import_value["input_png"]["sha256"],
                        f"portrait PNG changed for {selector}")
                verify_pin(png_open, f"portrait PNG {png_path.name}")
            finally:
                os.close(png_open.descriptor)

        actual_names = set(os.listdir(preview_dir))
        require(actual_names == set(expected_previews),
                "portrait preview directory members changed")
        preview_hashes = {name: read_preview(preview_dir / name, payload)
                          for name, payload in expected_previews.items()}
        source_sha_after, output_sha, actual = common.compare_and_hash(
            source.descriptor, output.descriptor, source.size, allowed_offsets)
        require(source_sha_after == source_sha and actual == sorted(allowed_offsets),
                "portrait output difference ledger changed")

        require(recorded["edits"] == expected_edits,
                "portrait manifest edit records differ from reconstruction")
        require(recorded["source"] == {
                    "path": str(source.path), "size": source.size,
                    "sha256_before": source_sha, "sha256_after": source_sha_after,
                    "device": source.identity[0], "inode": source.identity[1],
                    "opened_read_only": True, "modified": False},
                "portrait manifest source record changed")
        require(recorded["plan"] == {"path": str(plan), "sha256": digest(plan_payload),
                                      "edit_count": len(edits)} and
                recorded["canonical_index"] == {"path": str(index.path),
                                                  "size": INDEX_SIZE,
                                                  "sha256": INDEX_SHA256} and
                recorded["compatibility_report"] == {"path": str(compatibility.path),
                                                       "sha256": compatibility_sha},
                "portrait manifest input pins changed")
        output_record = recorded["output"]
        require(output_record["xiso_path"] == str(output.path) and
                output_record["xiso_size"] == output.size and
                output_record["xiso_sha256"] == output_sha and
                output_record["device"] == output.identity[0] and
                output_record["inode"] == output.identity[1] and
                output_record["manifest_path"] == str(manifest.path) and
                output_record["preview_directory"] == str(preview_dir) and
                output_record["preview_sha256"] == preview_hashes and
                output_record["exclusively_created"] is True and
                output_record["copy_method"] in {"copy_file_range", "pread_pwrite"},
                "portrait manifest output record changed")
        require(recorded["patch"] == {
                    "target_count": len(edits),
                    "target_pack_paths": sorted(pack_hashes),
                    "actual_changed_byte_count": len(actual),
                    "actual_changed_offsets_u64le_sha256": offset_hash(actual, "<Q"),
                    "all_other_xiso_bytes_identical": True},
                "portrait manifest patch ledger changed")
        require(recorded["claims"].get("numeric_roster_portraits_only") is True and
                recorded["claims"].get("action_photo_family_modified") is False and
                recorded["claims"].get("live_3d_face_family_modified") is False and
                recorded["claims"].get("layout_identical_copy_only_xiso") is True and
                recorded["claims"].get("originals_modified") is False and
                recorded["claims"].get("runtime_visibility_proved") is False and
                recorded["claims"].get("xemu_started") is False and
                recorded["claims"].get("title_executed") is False,
                "portrait manifest claims changed")
        verify_pin(source, "retail source XISO")
        verify_pin(output, "portrait output XISO")
        verify_pin(manifest, "portrait workflow manifest")
        verify_pin(index, "canonical extracted index")
        verify_pin(compatibility, "portrait compatibility report")
        return {
            "schema": SCHEMA, "edit_count": len(edits),
            "changed_byte_count": len(actual), "source_sha256": source_sha,
            "output_sha256": output_sha, "xdvdfs_identical": True,
            "default_xbe_unchanged": True, "all_other_xiso_bytes_identical": True,
            "runtime_visibility_proved": False,
        }
    finally:
        for opened in [compatibility, index, manifest, output, source]:
            os.close(opened.descriptor)


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
        result = verify(args.source_xiso, args.output_xiso, args.manifest,
                        args.preview_dir, args.plan, args.index, args.compatibility)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
