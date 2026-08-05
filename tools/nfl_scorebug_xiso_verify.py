#!/usr/bin/env python3
"""Independently verify a copy-only NFL 2K5 scorebug XISO workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from nfl_scorebug_png_import import (DEFAULT_AUDIT, DEFAULT_INDEX, TARGET_NAMES,
                                      build_import, canonical_json)
from nfl_scorebug_xiso_workflow import (SCHEMA as WORKFLOW_SCHEMA, offset_hash,
                                        relative_runs)
import nfl_uniform_color_xiso_direct_patch as common


MAX_MANIFEST_BYTES = 64 * 1024 * 1024


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
        require(identity == (supplied.st_dev, supplied.st_ino) and
                common.path_identity(resolved) == identity,
                f"{label} pathname changed")
        return resolved, descriptor, identity, info.st_size
    except Exception:
        os.close(descriptor)
        raise


def read_manifest(path: Path) -> tuple[Path, bytes, dict[str, object]]:
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
    require(payload == canonical_json(value) and isinstance(value, dict) and
            value.get("schema") == WORKFLOW_SCHEMA,
            "workflow manifest schema/canonical encoding changed")
    return resolved, payload, value


def verify(source_path: Path, output_path: Path, manifest_path: Path,
           preview_path: Path, target_name: str, png_path: Path,
           index_path: Path, audit_path: Path) -> dict[str, object]:
    manifest, _, value = read_manifest(manifest_path)
    replacement, preview_expected, import_value = build_import(
        index_path, audit_path, target_name, png_path)
    target = import_value["target"]
    source, source_fd, source_identity, source_size = open_regular(
        source_path, "retail source XISO")
    output, output_fd, output_identity, output_size = open_regular(
        output_path, "workflow output XISO")
    preview, preview_fd, preview_identity, preview_size = open_regular(
        preview_path, "workflow preview")
    try:
        index = index_path.resolve(strict=True)
        audit = audit_path.resolve(strict=True)
        png = png_path.resolve(strict=True)
        require(len({source, output, manifest, preview, index, audit, png}) == 7 and
                source_identity != output_identity and
                source_size == output_size == common.EXPECTED_XISO_SIZE,
                "workflow paths alias or XISO size relationship changed")
        require(preview_size == len(preview_expected) and
                common.read_exact(preview_fd, 0, preview_size) == preview_expected and
                common.path_identity(preview) == preview_identity,
                "workflow preview differs from reconstruction")
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
        pack = source_entries.get(str(target["pack_path"]).casefold())
        require(len(files) == 19 and xbe is not None and pack is not None and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                    common.EXPECTED_XBE_SHA256 and
                common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                    common.EXPECTED_XBE_SHA256,
                "source/output default.xbe changed")
        assert pack is not None
        require(pack.sector == int(target["xiso_pack_sector"]) and
                pack.byte_offset == int(target["xiso_pack_byte_offset"]) and
                pack.size == int(target["pack_size"]) and
                common.sha256_fd(source_fd, pack.byte_offset, pack.size) ==
                    target["pack_sha256"],
                "retail target pack identity changed")
        absolute = pack.byte_offset + int(target["pack_offset"])
        require(absolute == int(target["xiso_absolute_span_offset"]),
                "XISO target arithmetic changed")
        source_span = common.read_exact(source_fd, absolute, len(replacement))
        output_span = common.read_exact(output_fd, absolute, len(replacement))
        require(digest(source_span) == target["span_sha256"] and
                output_span == replacement,
                "source/output target span mismatch")
        relative = [index_ for index_, (before, after) in
                    enumerate(zip(source_span, replacement)) if before != after]
        require(relative, "replacement equals retail")
        allowed = {absolute + value for value in relative}
        source_sha_after, output_sha, actual = common.compare_and_hash(
            source_fd, output_fd, source_size, allowed)
        require(source_sha_after == source_sha and actual == sorted(allowed),
                "full-XISO difference ledger mismatch")

        source_record = value.get("source", {})
        require(source_record.get("path") == str(source) and
                source_record.get("size") == source_size and
                source_record.get("sha256_before") == source_sha and
                source_record.get("sha256_after") == source_sha_after and
                source_record.get("device") == source_identity[0] and
                source_record.get("inode") == source_identity[1] and
                source_record.get("opened_read_only") is True and
                source_record.get("modified") is False,
                "manifest source record changed")
        input_record = value.get("input", {})
        require(input_record.get("target") == target_name and
                input_record.get("png_path") == str(png) and
                input_record.get("png_sha256") == file_digest(png) and
                input_record.get("index_path") == str(index) and
                input_record.get("audit_path") == str(audit) and
                input_record.get("import_manifest") == import_value and
                input_record.get("import_manifest_sha256") ==
                    digest(canonical_json(import_value)),
                "manifest input/import record changed")
        output_record = value.get("output", {})
        require(output_record.get("xiso_path") == str(output) and
                output_record.get("xiso_size") == output_size and
                output_record.get("xiso_sha256") == output_sha and
                output_record.get("device") == output_identity[0] and
                output_record.get("inode") == output_identity[1] and
                output_record.get("manifest_path") == str(manifest) and
                output_record.get("preview_path") == str(preview) and
                output_record.get("preview_sha256") == digest(preview_expected) and
                output_record.get("copy_method") in {
                    "copy_file_range", "pread_pwrite"
                } and output_record.get("exclusively_created") is True,
                "manifest output record changed")
        require(value.get("xdvdfs") == {
            **source_directory, "file_count": len(files),
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
        }, "manifest XDVDFS record changed")
        patch = value.get("patch", {})
        require(patch.get("target_pack_path") == target["pack_path"] and
                patch.get("target_pack_sector") == pack.sector and
                patch.get("target_pack_byte_offset") == pack.byte_offset and
                patch.get("source_pack_sha256") == target["pack_sha256"] and
                patch.get("patched_pack_sha256") ==
                    common.sha256_fd(output_fd, pack.byte_offset, pack.size) and
                patch.get("absolute_span_offset") == absolute and
                patch.get("replacement_span_size") == len(replacement) and
                patch.get("replacement_span_sha256") == digest(replacement) and
                patch.get("relative_changed_byte_count") == len(relative) and
                patch.get("relative_changed_offsets_u32le_sha256") ==
                    offset_hash(relative, "<I") and
                patch.get("relative_changed_runs") == relative_runs(relative) and
                patch.get("actual_changed_byte_count") == len(actual) and
                patch.get("actual_changed_offsets_u64le_sha256") ==
                    offset_hash(actual, "<Q") and
                patch.get("all_other_xiso_bytes_identical") is True,
                "manifest patch record changed")
        claims = value.get("claims", {})
        require(claims.get("code_bound_field_scorebug_texture") is
                    (target_name in {"score_buga", "shield_espn"}) and
                claims.get("shared_global_font_texture") is
                    (target_name == "digital_font") and
                claims.get("layout_identical_copy_only_xiso") is True and
                claims.get("loader_in_place_decode_guarded") is True and
                claims.get("originals_modified") is False and
                claims.get("xemu_started") is False and
                claims.get("title_executed") is False and
                claims.get("runtime_visibility_proved") is False,
                "manifest safety claims changed")
        return {"target": target_name, "output_sha256": output_sha,
                "changed_bytes": len(actual), "tree_identical": True,
                "runtime_visibility_proved": False}
    finally:
        os.close(source_fd)
        os.close(output_fd)
        os.close(preview_fd)


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
        result = verify(args.source_xiso, args.output_xiso, args.manifest,
                        args.preview, args.target, args.png,
                        args.index, args.audit)
        print("NFL_SCOREBUG_XISO_VERIFY_PASS "
              f"target={result['target']} changed={result['changed_bytes']} "
              f"sha256={result['output_sha256']} runtime=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
