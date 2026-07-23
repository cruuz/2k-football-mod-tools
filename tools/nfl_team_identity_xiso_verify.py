#!/usr/bin/env python3
"""Independently verify the NFL 2K5 fixed-size team-identity XISO proof.

This module does not import the writer.  It parses both XDVDFS trees, scans
both 6.30 GB images, validates the four UTF-16 replacements and unchanged
team record, checks the retail XBE, and audits the writer manifest.
"""

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


SECTOR = 2048
VOLUME_OFFSET = 0x10000
MAGIC = b"MICROSOFT*XBOX*MEDIA"
IMAGE_SIZE = 6_300_499_968
SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
OUTPUT_SHA256 = "daae27a6e51d4ed126b4bc14c800c1c6090dc32efa00d18283e65c07d7660e45"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
WORKFLOW_SCHEMA = "nfl2k5_team_identity_xiso_workflow/v1"
AUDIT_SCHEMA = "nfl2k5_team_identity_audit/v1"
CHUNK = 16 * 1024 * 1024

PACK0_SECTOR = 796_479
PACK0_SIZE = 193_710_080
ROST_OUTER = 0x00392800
ROST_BODY = ROST_OUTER + 0x20
TEAM18 = ROST_BODY + 0x64F0


class VerifyError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


@dataclass(frozen=True)
class Entry:
    path: str
    sector: int
    size: int
    attributes: int

    @property
    def offset(self) -> int:
        return self.sector * SECTOR


@dataclass(frozen=True)
class Edit:
    field: str
    pointer_field: int
    body_offset: int
    before: str
    after: str

    @property
    def before_bytes(self) -> bytes:
        return (self.before + "\0").encode("utf-16le")

    @property
    def after_bytes(self) -> bytes:
        return (self.after + "\0").encode("utf-16le")


EDITS = (
    Edit("nickname", 0x104, 0x7976C, "Lions", "Codex"),
    Edit("abbreviation", 0x108, 0x79778, "DET", "CDX"),
    Edit("city", 0x138, 0x79786, "Detroit", "Codexia"),
    Edit("city_abbreviation", 0x13C, 0x79796, "DET", "CDX"),
)


def pread_exact(fd: int, offset: int, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = os.pread(fd, size - len(result), offset + len(result))
        require(bool(chunk), f"short read at 0x{offset + len(result):x}")
        result.extend(chunk)
    return bytes(result)


def hash_extent(fd: int, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    position = 0
    while position < size:
        chunk = os.pread(fd, min(CHUNK, size - position), offset + position)
        require(bool(chunk), f"short hash read at 0x{offset + position:x}")
        digest.update(chunk)
        position += len(chunk)
    return digest.hexdigest()


def open_regular(path: Path) -> tuple[Path, int]:
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode), f"symlink refused: {path}")
    resolved = path.resolve(strict=True)
    fd = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    opened = os.fstat(fd)
    require(stat.S_ISREG(opened.st_mode), f"not a regular file: {path}")
    require((opened.st_dev, opened.st_ino) ==
            (resolved.stat().st_dev, resolved.stat().st_ino),
            f"pathname changed after open: {path}")
    return resolved, fd


def read_regular_bytes(
    path: Path, label: str
) -> tuple[Path, bytes, tuple[int, int]]:
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode), f"{label} symlink refused: {path}")
    resolved = path.resolve(strict=True)
    fd = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        require(stat.S_ISREG(opened.st_mode), f"{label} is not a regular file")
        owned = (opened.st_dev, opened.st_ino)
        require(owned == (resolved.stat().st_dev, resolved.stat().st_ino),
                f"{label} pathname changed after open")
        raw = pread_exact(fd, 0, opened.st_size)
    finally:
        os.close(fd)
    return resolved, raw, owned


def parse_xdvdfs(fd: int) -> tuple[dict[str, Entry], tuple[int, int, int, int]]:
    volume = pread_exact(fd, VOLUME_OFFSET, 0x800)
    require(volume[:20] == MAGIC and volume[-20:] == MAGIC,
            "XDVDFS signature mismatch")
    root_sector, root_size = struct.unpack_from("<II", volume, 20)
    require((root_sector, root_size) == (33, 108), "root directory extent changed")
    entries: dict[str, Entry] = {}
    active: set[tuple[int, int]] = set()
    directory_count = 0
    node_count = 0

    def parse_directory(sector: int, size: int, prefix: str) -> None:
        nonlocal directory_count, node_count
        extent = (sector, size)
        require(extent not in active, "recursive directory extent")
        require(14 <= size and sector * SECTOR + size <= IMAGE_SIZE,
                f"directory outside image: {prefix or '/'}")
        active.add(extent)
        directory_count += 1
        table = pread_exact(fd, sector * SECTOR, size)
        visited: set[int] = set()

        def visit(offset: int) -> None:
            nonlocal node_count
            require(offset not in visited and 0 <= offset <= size - 14,
                    f"invalid directory node: {prefix or '/'}")
            visited.add(offset)
            node_count += 1
            require(node_count <= 64, "too many directory nodes")
            left, right, start, length = struct.unpack_from("<HHII", table, offset)
            attributes, name_size = struct.unpack_from("BB", table, offset + 12)
            require(name_size and offset + 14 + name_size <= size,
                    "invalid filename range")
            raw = table[offset + 14:offset + 14 + name_size]
            require(not any(value in raw for value in (0, 47, 92)),
                    "unsafe filename")
            try:
                name = raw.decode("ascii")
            except UnicodeDecodeError as exc:
                raise VerifyError("non-ASCII XDVDFS filename") from exc
            if left:
                visit(left * 4)
            path = f"{prefix}/{name}" if prefix else name
            key = path.casefold()
            require(key not in entries, f"duplicate path: {path}")
            require(start * SECTOR + length <= IMAGE_SIZE,
                    f"extent outside image: {path}")
            entry = Entry(path, start, length, attributes)
            entries[key] = entry
            if attributes & 0x10:
                parse_directory(start, length, path)
            else:
                require(attributes & 0x20, f"unsupported node type: {path}")
            if right:
                visit(right * 4)

        visit(0)
        active.remove(extent)

    parse_directory(root_sector, root_size, "")
    require(node_count == 20 and len(entries) == 20,
            "retail directory path count changed")
    return entries, (root_sector, root_size, directory_count, node_count)


def expected_offsets(pack_offset: int) -> tuple[list[dict[str, object]], set[int]]:
    result: list[dict[str, object]] = []
    allowed: set[int] = set()
    for edit in EDITS:
        absolute = pack_offset + ROST_BODY + edit.body_offset
        changed = [
            index for index, (old, new) in
            enumerate(zip(edit.before_bytes, edit.after_bytes)) if old != new
        ]
        allowed.update(absolute + value for value in changed)
        result.append({
            "field": edit.field,
            "absolute": absolute,
            "changed_relative": changed,
        })
    require(len(allowed) == 17, "expected changed-byte set changed")
    return result, allowed


def scan_images(
    source_fd: int, output_fd: int, allowed: set[int]
) -> tuple[str, str, list[int]]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    while position < IMAGE_SIZE:
        size = min(CHUNK, IMAGE_SIZE - position)
        before = pread_exact(source_fd, position, size)
        after = pread_exact(output_fd, position, size)
        source_hash.update(before)
        output_hash.update(after)
        if before != after:
            differences.extend(
                position + index
                for index, (old, new) in enumerate(zip(before, after))
                if old != new
            )
            require(len(differences) <= len(allowed),
                    "more bytes changed than expected")
        position += size
    require(set(differences) == allowed, "full-image difference set mismatch")
    return source_hash.hexdigest(), output_hash.hexdigest(), differences


def validate_structures(
    source_fd: int, output_fd: int, pack: Entry, edit_offsets: list[dict[str, object]]
) -> None:
    require(hash_extent(source_fd, pack.offset, pack.size) == PACK0_SHA256,
            "retail pack 0 hash mismatch")
    source_wrapper = pread_exact(source_fd, pack.offset + ROST_OUTER, 0x20)
    output_wrapper = pread_exact(output_fd, pack.offset + ROST_OUTER, 0x20)
    require(source_wrapper == output_wrapper, "ROST wrapper changed")
    require(struct.unpack_from("<4s7I", source_wrapper) ==
            (b"ROST", 593760, 593760, 0, 0, 0, 0, 0),
            "ROST wrapper values changed")
    require(pread_exact(source_fd, pack.offset + TEAM18, 0x1F4) ==
            pread_exact(output_fd, pack.offset + TEAM18, 0x1F4),
            "serialized team record changed")
    for edit, offset in zip(EDITS, edit_offsets):
        absolute = int(offset["absolute"])
        require(pread_exact(source_fd, absolute, len(edit.before_bytes)) == edit.before_bytes,
                f"source string mismatch: {edit.field}")
        require(pread_exact(output_fd, absolute, len(edit.after_bytes)) == edit.after_bytes,
                f"output string mismatch: {edit.field}")
        pointer = struct.unpack(
            "<i", pread_exact(source_fd, pack.offset + TEAM18 + edit.pointer_field, 4)
        )[0]
        target = 0x64F0 + edit.pointer_field + pointer - 1
        require(target == edit.body_offset,
                f"team pointer target mismatch: {edit.field}")
    asset_pointer = struct.unpack(
        "<i", pread_exact(source_fd, pack.offset + TEAM18 + 0x10C, 4)
    )[0]
    require(0x64F0 + 0x10C + asset_pointer - 1 == 0x79780,
            "asset-code pointer target changed")
    asset_source = pread_exact(source_fd, pack.offset + ROST_BODY + 0x79780, 6)
    asset_output = pread_exact(output_fd, pack.offset + ROST_BODY + 0x79780, 6)
    require(asset_source == asset_output == "09\0".encode("utf-16le"),
            "asset-code selector changed")
    require(pread_exact(source_fd, pack.offset + TEAM18 + 0x11C, 1) ==
            pread_exact(output_fd, pack.offset + TEAM18 + 0x11C, 1) == b"\x35",
            "roster count changed")


def validate_audit(raw: bytes) -> str:
    value = json.loads(raw)
    require(value.get("schema") == AUDIT_SCHEMA, "audit schema mismatch")
    require(value["claims"]["originals_modified"] is False,
            "audit original-mutation claim changed")
    require(value["summary"]["main_team_count"] == 52 and
            value["summary"]["uniform_and_team_select_asset_code_count"] == 85 and
            value["summary"]["compiled_color_record_count"] == 80,
            "audit summary changed")
    require(value["teams"][18]["asset_code"] == "09",
            "audit Detroit selector changed")
    return hashlib.sha256(raw).hexdigest()


def validate_manifest(
    raw: bytes, source: Path, output: Path, audit_sha: str,
    differences: list[int], edit_offsets: list[dict[str, object]],
) -> str:
    value = json.loads(raw)
    require(value.get("schema") == WORKFLOW_SCHEMA, "manifest schema mismatch")
    require(Path(value["source"]["path"]).resolve() == source,
            "manifest source path mismatch")
    require(Path(value["output"]["path"]).resolve() == output,
            "manifest output path mismatch")
    require(value["source"]["sha256_before"] == SOURCE_SHA256 and
            value["source"]["sha256_after"] == SOURCE_SHA256 and
            value["source"]["modified"] is False,
            "manifest source identity mismatch")
    require(value["output"]["sha256"] == OUTPUT_SHA256,
            "manifest output hash mismatch")
    require(value["audit"]["sha256"] == audit_sha,
            "manifest audit hash mismatch")
    proof = value["proof"]
    require(proof["team_index"] == 18 and
            proof["before_display"] == "Detroit Lions" and
            proof["after_display"] == "Codexia Codex" and
            proof["asset_code_before_after"] == "09" and
            proof["roster_count_before_after"] == 53,
            "manifest proof identity mismatch")
    require(proof["actual_changed_byte_count"] == 17 and
            proof["actual_changed_byte_offsets"] == differences and
            proof["allowed_changed_byte_offsets"] == differences,
            "manifest changed-byte ledger mismatch")
    require([item["xiso_absolute_offset"] for item in proof["edits"]] ==
            [item["absolute"] for item in edit_offsets],
            "manifest edit offsets mismatch")
    claims = value["claims"]
    require(claims == {
        "fixed_size_identity_edit_proved": True,
        "layout_identical_copy_only_xiso": True,
        "original_source_modified": False,
        "portme": "Boot this copied XISO and capture Team Select plus a gameplay overlay before claiming the renamed identity is visible in every UI context.",
        "roster_membership_changed": False,
        "runtime_visibility_proved": False,
        "title_executed": False,
        "uniform_or_logo_asset_changed": False,
        "xemu_started": False,
    }, "manifest claims changed")
    return hashlib.sha256(raw).hexdigest()


def run(source_path: Path, output_path: Path, manifest_path: Path, audit_path: Path) -> dict[str, object]:
    audit_resolved, audit_raw, audit_identity = read_regular_bytes(audit_path, "audit")
    manifest_resolved, manifest_raw, manifest_identity = read_regular_bytes(
        manifest_path, "manifest"
    )
    audit_sha = validate_audit(audit_raw)
    source, source_fd = open_regular(source_path)
    output, output_fd = open_regular(output_path)
    try:
        require(source != output, "source and output paths match")
        require(os.fstat(source_fd).st_size == os.fstat(output_fd).st_size == IMAGE_SIZE,
                "XISO size mismatch")
        source_entries, source_directory = parse_xdvdfs(source_fd)
        output_entries, output_directory = parse_xdvdfs(output_fd)
        require(source_entries == output_entries and source_directory == output_directory,
                "XDVDFS trees differ")
        pack = source_entries.get("vc_53450030/0")
        xbe = source_entries.get("default.xbe")
        require(pack is not None and xbe is not None, "required XDVDFS file missing")
        require((pack.sector, pack.size) == (PACK0_SECTOR, PACK0_SIZE),
                "pack 0 extent mismatch")
        require(hash_extent(source_fd, xbe.offset, xbe.size) ==
                hash_extent(output_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "default.xbe differs or has wrong hash")
        edit_offsets, allowed = expected_offsets(pack.offset)
        source_hash, output_hash, differences = scan_images(source_fd, output_fd, allowed)
        require(source_hash == SOURCE_SHA256, "retail XISO hash mismatch")
        require(output_hash == OUTPUT_SHA256, "proof XISO hash mismatch")
        validate_structures(source_fd, output_fd, pack, edit_offsets)
        manifest_sha = validate_manifest(
            manifest_raw, source, output, audit_sha, differences, edit_offsets
        )
        require((audit_resolved.stat().st_dev, audit_resolved.stat().st_ino) ==
                audit_identity, "audit pathname changed during verification")
        require((manifest_resolved.stat().st_dev, manifest_resolved.stat().st_ino) ==
                manifest_identity, "manifest pathname changed during verification")
        return {
            "source_sha256": source_hash,
            "output_sha256": output_hash,
            "manifest_sha256": manifest_sha,
            "changed_bytes": len(differences),
            "xdvdfs_identical": True,
            "default_xbe_unchanged": True,
            "asset_code": "09",
            "runtime_visibility": False,
        }
    finally:
        os.close(source_fd)
        os.close(output_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--audit", type=Path,
        default=Path("reports/assets/nfl2k5_team_identity_audit.json"),
    )
    args = parser.parse_args(argv)
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest, args.audit)
    except (OSError, VerifyError, json.JSONDecodeError) as exc:
        print(f"nfl_team_identity_xiso_verify: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_TEAM_IDENTITY_XISO_VERIFY_PASS "
        f"changed={result['changed_bytes']} "
        f"asset_code={result['asset_code']} "
        f"xdvdfs_identical={str(result['xdvdfs_identical']).lower()} "
        f"runtime={str(result['runtime_visibility']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
