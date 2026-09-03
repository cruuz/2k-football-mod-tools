#!/usr/bin/env python3
"""Create a layout-identical NFL 2K5 XISO copy with one identity-only edit.

The proof changes Detroit to ``Codexia Codex`` in the main disc ROST while
preserving the two-digit asset code, every serialized pointer, every roster
slot, every XDVDFS extent, and ``default.xbe``.  It never rewrites the source.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys


def _pread(fd: int, count: int, offset: int) -> bytes:
    """Positional read; Windows has no os.pread, so seek/read/restore there."""
    preader = getattr(os, "pread", None)
    if preader is not None:
        return preader(fd, count, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.lseek(fd, here, os.SEEK_SET)


def _pwrite(fd: int, data: bytes, offset: int) -> int:
    """Positional write; Windows has no os.pwrite, so seek/write/restore there."""
    pwriter = getattr(os, "pwrite", None)
    if pwriter is not None:
        return pwriter(fd, data, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.write(fd, data)
    finally:
        os.lseek(fd, here, os.SEEK_SET)


SCHEMA = "nfl2k5_team_identity_xiso_workflow/v1"
AUDIT_SCHEMA = "nfl2k5_team_identity_audit/v1"
SECTOR = 2048
VOLUME_OFFSET = 0x10000
VOLUME_MAGIC = b"MICROSOFT*XBOX*MEDIA"
IMAGE_SIZE = 6_300_499_968
SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
PACK0_SECTOR = 796_479
PACK0_SIZE = 193_710_080
ROST_OUTER_OFFSET = 0x00392800
ROST_WRAPPER_SIZE = 0x20
ROST_BODY_SIZE = 593_760
ROST_TEAM18_RECORD = 0x000064F0
ROST_TEAM_STRIDE = 0x1F4
HASH_CHUNK = 16 * 1024 * 1024
COPY_CHUNK = 32 * 1024 * 1024


class WorkflowError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


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

    def before_bytes(self) -> bytes:
        return (self.before + "\0").encode("utf-16le")

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
        chunk = _pread(fd, size - len(result), offset + len(result))
        require(bool(chunk), f"short read at 0x{offset + len(result):x}")
        result.extend(chunk)
    return bytes(result)


def pwrite_exact(fd: int, offset: int, data: bytes) -> None:
    written = 0
    while written < len(data):
        amount = _pwrite(fd, data[written:], offset + written)
        require(amount > 0, f"short write at 0x{offset + written:x}")
        written += amount


def hash_extent(fd: int, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    position = 0
    while position < size:
        chunk = _pread(fd, min(HASH_CHUNK, size - position), offset + position)
        require(bool(chunk), f"short hash read at 0x{offset + position:x}")
        digest.update(chunk)
        position += len(chunk)
    return digest.hexdigest()


def parse_xdvdfs(fd: int, image_size: int) -> tuple[dict[str, Entry], dict[str, int]]:
    volume = pread_exact(fd, VOLUME_OFFSET, 0x800)
    require(volume[:20] == VOLUME_MAGIC and volume[-20:] == VOLUME_MAGIC,
            "XDVDFS volume signature mismatch")
    root_sector, root_size = struct.unpack_from("<II", volume, 20)
    require((root_sector, root_size) == (33, 108), "retail root extent changed")
    entries: dict[str, Entry] = {}
    active: set[tuple[int, int]] = set()
    directory_count = 0
    node_count = 0

    def directory(sector: int, size: int, prefix: str) -> None:
        nonlocal directory_count, node_count
        extent = (sector, size)
        require(extent not in active, "recursive XDVDFS directory")
        require(14 <= size and sector * SECTOR + size <= image_size,
                f"directory outside image: {prefix or '/'}")
        active.add(extent)
        directory_count += 1
        table = pread_exact(fd, sector * SECTOR, size)
        visited: set[int] = set()

        def node(offset: int) -> None:
            nonlocal node_count
            require(offset not in visited and 0 <= offset <= size - 14,
                    f"invalid directory node in {prefix or '/'}")
            visited.add(offset)
            node_count += 1
            require(node_count <= 64, "unexpected XDVDFS node count")
            left, right, start, length = struct.unpack_from("<HHII", table, offset)
            attributes, name_size = struct.unpack_from("BB", table, offset + 12)
            require(name_size and offset + 14 + name_size <= size,
                    "invalid XDVDFS filename extent")
            raw_name = table[offset + 14:offset + 14 + name_size]
            require(not any(value in raw_name for value in (0, 47, 92)),
                    "unsafe XDVDFS filename")
            try:
                name = raw_name.decode("ascii")
            except UnicodeDecodeError as exc:
                raise WorkflowError("non-ASCII XDVDFS filename") from exc
            if left:
                node(left * 4)
            path = f"{prefix}/{name}" if prefix else name
            key = path.casefold()
            require(key not in entries, f"duplicate XDVDFS path: {path}")
            require(start * SECTOR + length <= image_size,
                    f"XDVDFS extent outside image: {path}")
            entry = Entry(path, start, length, attributes)
            entries[key] = entry
            if attributes & 0x10:
                directory(start, length, path)
            else:
                require(attributes & 0x20, f"unsupported XDVDFS entry: {path}")
            if right:
                node(right * 4)

        node(0)
        active.remove(extent)

    directory(root_sector, root_size, "")
    require(node_count == 20 and len(entries) == 20,
            "retail XDVDFS path count changed")
    return entries, {
        "root_sector": root_sector,
        "root_size": root_size,
        "directory_count": directory_count,
        "node_count": node_count,
    }


def copy_image(source_fd: int, output_fd: int, size: int) -> str:
    position = 0
    # Linux-only accelerated copy; Windows and macOS have no such member at all.
    copier = getattr(os, "copy_file_range", None)
    method = "copy_file_range" if copier is not None else "pread_pwrite"
    while position < size and copier is not None:
        request = min(COPY_CHUNK, size - position)
        try:
            amount = copier(source_fd, output_fd, request, position, position)
        except OSError as exc:
            if exc.errno not in {
                errno.EXDEV, errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP,
            }:
                raise
            method = "pread_pwrite"
            break
        require(amount > 0, "short copy_file_range result")
        position += amount
    while position < size:
        chunk = _pread(source_fd, min(COPY_CHUNK, size - position), position)
        require(bool(chunk), "short source read during XISO copy")
        pwrite_exact(output_fd, position, chunk)
        position += len(chunk)
    require(os.fstat(output_fd).st_size == size, "copied XISO size mismatch")
    return method


def compare_images(
    source_fd: int, output_fd: int, size: int, allowed: set[int]
) -> tuple[str, str, list[int]]:
    before_hash = hashlib.sha256()
    after_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    while position < size:
        request = min(HASH_CHUNK, size - position)
        before = pread_exact(source_fd, position, request)
        after = pread_exact(output_fd, position, request)
        before_hash.update(before)
        after_hash.update(after)
        if before != after:
            differences.extend(
                position + index
                for index, (old, new) in enumerate(zip(before, after))
                if old != new
            )
            require(len(differences) <= len(allowed),
                    "output contains more changes than the allowed set")
        position += request
    require(set(differences) == allowed, "output difference set is not exact")
    return before_hash.hexdigest(), after_hash.hexdigest(), differences


def safe_source(path: Path) -> tuple[Path, int, tuple[int, int]]:
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode), "source must not be a symlink")
    resolved = path.resolve(strict=True)
    fd = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    descriptor_info = os.fstat(fd)
    require(stat.S_ISREG(descriptor_info.st_mode), "source is not a regular file")
    require(descriptor_info.st_size == IMAGE_SIZE, "retail XISO size changed")
    require((resolved.stat().st_dev, resolved.stat().st_ino) ==
            (descriptor_info.st_dev, descriptor_info.st_ino),
            "source pathname changed after open")
    return resolved, fd, (descriptor_info.st_dev, descriptor_info.st_ino)


def reserve(path: Path) -> tuple[Path, int, tuple[int, int]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = path.parent.resolve(strict=True) / path.name
    fd = os.open(
        resolved,
        os.O_CREAT | os.O_EXCL | os.O_RDWR |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        0o644,
    )
    info = os.fstat(fd)
    return resolved, fd, (info.st_dev, info.st_ino)


def identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    return info.st_dev, info.st_ino


def validate_audit(path: Path) -> str:
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode), "audit report must not be a symlink")
    resolved = path.resolve(strict=True)
    fd = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(fd)
        require(stat.S_ISREG(opened.st_mode), "audit report is not a regular file")
        require((opened.st_dev, opened.st_ino) ==
                (resolved.stat().st_dev, resolved.stat().st_ino),
                "audit report pathname changed after open")
        data = pread_exact(fd, 0, opened.st_size)
    finally:
        os.close(fd)
    value = json.loads(data)
    require(value.get("schema") == AUDIT_SCHEMA, "team-identity audit schema mismatch")
    proof = value["safe_fixed_size_proof"]
    require(proof["target"] == "main ROST team 18 / Detroit",
            "team-identity proof target changed")
    require(proof["unchanged"]["asset_code"] == "09",
            "team-identity proof asset code changed")
    for edit in EDITS:
        require(proof["changes"][edit.field] == {
            "before": edit.before, "after": edit.after,
        }, f"audit proof edit changed: {edit.field}")
    team = value["teams"][18]
    require(team["team_index"] == 18 and team["asset_code"] == "09",
            "audit Detroit row changed")
    for edit in EDITS:
        field = team["fields"][edit.field]
        require(field["body_string_offset"] == edit.body_offset,
                f"audit string offset changed: {edit.field}")
        require(field["known_decoded_pointer_reference_count"] == 1,
                f"audit string is shared: {edit.field}")
    return hashlib.sha256(data).hexdigest()


def validate_roster_source(fd: int, pack: Entry) -> tuple[int, list[dict[str, object]], set[int]]:
    require((pack.sector, pack.size) == (PACK0_SECTOR, PACK0_SIZE),
            "pack 0 extent changed")
    require(hash_extent(fd, pack.offset, pack.size) == PACK0_SHA256,
            "retail pack 0 hash changed")
    outer = pack.offset + ROST_OUTER_OFFSET
    wrapper = pread_exact(fd, outer, ROST_WRAPPER_SIZE)
    require(wrapper[:4] == b"ROST", "main ROST wrapper magic changed")
    values = struct.unpack_from("<4s7I", wrapper)
    require(values[1:] == (
        ROST_BODY_SIZE, ROST_BODY_SIZE, 0, 0, 0, 0, 0,
    ), "main ROST wrapper layout changed")
    body = outer + ROST_WRAPPER_SIZE
    require(pread_exact(fd, body, 0x20) ==
            bytes(12) + b"ROST" + struct.pack("<I", 17) +
            struct.pack("<i", 45) + bytes(8),
            "main ROST preamble changed")
    record = body + ROST_TEAM18_RECORD
    require(pread_exact(fd, record + 0x10C, 4) != bytes(4),
            "Detroit asset-code pointer is null")
    records: list[dict[str, object]] = []
    allowed: set[int] = set()
    for edit in EDITS:
        before = edit.before_bytes()
        after = edit.after_bytes()
        require(len(before) == len(after), f"edit changes allocation: {edit.field}")
        pointer_raw = struct.unpack(
            "<i", pread_exact(fd, record + edit.pointer_field, 4)
        )[0]
        target_body = ROST_TEAM18_RECORD + edit.pointer_field + pointer_raw - 1
        require(target_body == edit.body_offset,
                f"serialized pointer no longer selects {edit.field}")
        absolute = body + edit.body_offset
        require(pread_exact(fd, absolute, len(before)) == before,
                f"retail text changed: {edit.field}")
        changed = [
            index for index, (old, new) in enumerate(zip(before, after)) if old != new
        ]
        allowed.update(absolute + index for index in changed)
        records.append({
            "field": edit.field,
            "team_record_pointer_field": f"0x{edit.pointer_field:x}",
            "body_string_offset": edit.body_offset,
            "xiso_absolute_offset": absolute,
            "before": edit.before,
            "after": edit.after,
            "before_hex": before.hex(),
            "after_hex": after.hex(),
            "allocation_bytes": len(before),
            "changed_relative_bytes": changed,
            "serialized_pointer_value": pointer_raw,
            "serialized_pointer_unchanged": True,
        })
    require(len(allowed) == 17, "identity proof changed-byte count changed")
    asset_pointer = struct.unpack("<i", pread_exact(fd, record + 0x10C, 4))[0]
    asset_target = ROST_TEAM18_RECORD + 0x10C + asset_pointer - 1
    require(asset_target == 0x79780 and
            pread_exact(fd, body + asset_target, 6) == "09\0".encode("utf-16le"),
            "Detroit asset-code selector changed")
    require(pread_exact(fd, record + 0x11C, 1) == b"\x35",
            "Detroit roster count changed")
    return body, records, allowed


def write_json_exclusive(path: Path, value: dict[str, object]) -> None:
    resolved, fd, owned = reserve(path)
    success = False
    try:
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        pwrite_exact(fd, 0, payload)
        os.ftruncate(fd, len(payload))
        os.fsync(fd)
        require(identity(resolved) == owned and pread_exact(fd, 0, len(payload)) == payload,
                "manifest ownership/readback mismatch")
        success = True
    finally:
        os.close(fd)
        if not success and identity(resolved) == owned:
            resolved.unlink()


def run(source_path: Path, output_path: Path, manifest_path: Path, audit_path: Path) -> dict[str, object]:
    source, source_fd, source_identity = safe_source(source_path)
    output: Path | None = None
    output_fd: int | None = None
    output_identity: tuple[int, int] | None = None
    success = False
    try:
        audit_sha = validate_audit(audit_path)
        source_sha = hash_extent(source_fd, 0, IMAGE_SIZE)
        require(source_sha == SOURCE_SHA256, "retail XISO hash changed")
        entries, directory = parse_xdvdfs(source_fd, IMAGE_SIZE)
        pack = entries.get("vc_53450030/0")
        xbe = entries.get("default.xbe")
        require(pack is not None and xbe is not None, "required XDVDFS file missing")
        require(hash_extent(source_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "retail default.xbe hash changed")
        body, edits, allowed = validate_roster_source(source_fd, pack)

        output, output_fd, output_identity = reserve(output_path)
        require(output != source and output_identity != source_identity,
                "output aliases retail source")
        method = copy_image(source_fd, output_fd, IMAGE_SIZE)
        for edit, record in zip(EDITS, edits):
            pwrite_exact(output_fd, int(record["xiso_absolute_offset"]), edit.after_bytes())
        os.fsync(output_fd)
        require(identity(output) == output_identity, "output pathname changed")

        source_after, output_sha, differences = compare_images(
            source_fd, output_fd, IMAGE_SIZE, allowed
        )
        require(source_after == SOURCE_SHA256, "retail source changed during workflow")
        output_entries, output_directory = parse_xdvdfs(output_fd, IMAGE_SIZE)
        require(output_entries == entries and output_directory == directory,
                "XDVDFS tree or extents changed")
        require(hash_extent(output_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "default.xbe changed")
        require(hash_extent(output_fd, pack.offset, pack.size) != PACK0_SHA256,
                "patched pack 0 hash unexpectedly unchanged")
        for edit, record in zip(EDITS, edits):
            absolute = int(record["xiso_absolute_offset"])
            require(pread_exact(output_fd, absolute, len(edit.after_bytes())) ==
                    edit.after_bytes(), f"patched text readback failed: {edit.field}")
        record = body + ROST_TEAM18_RECORD
        require(pread_exact(output_fd, record + 0x10C, 4) ==
                pread_exact(source_fd, record + 0x10C, 4),
                "asset-code pointer changed")
        require(pread_exact(output_fd, body + 0x79780, 6) == "09\0".encode("utf-16le"),
                "asset-code text changed")
        # The edit is intentionally confined to the separately allocated
        # UTF-16 strings.  The 0x1f4 team record itself contains only the
        # unchanged relative pointers and scalar/roster fields.
        require(pread_exact(output_fd, record, ROST_TEAM_STRIDE) ==
                pread_exact(source_fd, record, ROST_TEAM_STRIDE),
                "team record or one of its serialized pointers changed")

        result: dict[str, object] = {
            "schema": SCHEMA,
            "source": {
                "path": str(source),
                "size": IMAGE_SIZE,
                "sha256_before": source_sha,
                "sha256_after": source_after,
                "opened_read_only": True,
                "modified": False,
            },
            "output": {
                "path": str(output),
                "size": os.fstat(output_fd).st_size,
                "sha256": output_sha,
                "copy_method": method,
                "exclusively_created": True,
                "distinct_from_source_inode": True,
            },
            "audit": {"path": str(audit_path.resolve()), "sha256": audit_sha},
            "xdvdfs": {
                **directory,
                "tree_and_extents_identical": True,
                "pack0_sector": pack.sector,
                "pack0_size": pack.size,
                "default_xbe_sha256": XBE_SHA256,
            },
            "proof": {
                "team_index": 18,
                "before_display": "Detroit Lions",
                "after_display": "Codexia Codex",
                "edits": edits,
                "asset_code_before_after": "09",
                "roster_count_before_after": 53,
                "all_serialized_pointers_unchanged": True,
                "allowed_changed_byte_offsets": sorted(allowed),
                "actual_changed_byte_offsets": differences,
                "actual_changed_byte_count": len(differences),
                "all_other_xiso_bytes_identical": True,
            },
            "claims": {
                "fixed_size_identity_edit_proved": True,
                "layout_identical_copy_only_xiso": True,
                "uniform_or_logo_asset_changed": False,
                "roster_membership_changed": False,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "title_executed": False,
                "original_source_modified": False,
                "portme": "Boot this copied XISO and capture Team Select plus a gameplay overlay before claiming the renamed identity is visible in every UI context.",
            },
        }
        require(identity(source) == source_identity, "retail source pathname changed")
        require(identity(output) == output_identity, "output pathname changed at closeout")
        require(not manifest_path.exists(), "manifest already exists")
        # The manifest is the final mutation.  All source/output pathname
        # ownership checks precede it so a post-manifest failure cannot leave
        # a successful-looking report beside a removed proof image.
        write_json_exclusive(manifest_path, result)
        success = True
        return result
    finally:
        os.close(source_fd)
        if output_fd is not None:
            os.close(output_fd)
        if not success and output is not None and output_identity is not None and identity(output) == output_identity:
            output.unlink()


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
        value = run(args.source_xiso, args.output_xiso, args.manifest, args.audit)
    except (OSError, WorkflowError, json.JSONDecodeError) as exc:
        print(f"nfl_team_identity_xiso_workflow: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_TEAM_IDENTITY_XISO_WORKFLOW_OK "
        f"changed={value['proof']['actual_changed_byte_count']} "
        f"sha256={value['output']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
