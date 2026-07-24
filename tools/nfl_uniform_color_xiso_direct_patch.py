#!/usr/bin/env python3
"""Patch the proved NFL 2K5 Lions color words in a layout-identical XISO copy.

Unlike a filesystem rebuild, this writer preserves every XDVDFS sector and
file extent from the retail image.  It exclusively creates a complete copy,
locates ``vc_53450030/A`` and ``B`` through the on-disc directory tree, and
changes only the two validated eight-byte ``Unif`` ranges.
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

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import platform_compat  # noqa: E402


SCHEMA = "nfl2k5_uniform_color_xiso_direct_patch/v1"
SECTOR_SIZE = 2048
XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"
XDVDFS_HEADER_OFFSET = 0x10000
EXPECTED_XISO_SIZE = 6_300_499_968
EXPECTED_XISO_SHA256 = (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
EXPECTED_XBE_SIZE = 11_948_032
MAGENTA_PAIR = struct.pack("<II", 0xFFFF00FF, 0xFFFF00FF)
COPY_CHUNK = 32 * 1024 * 1024
HASH_CHUNK = 16 * 1024 * 1024
MAX_DIRECTORY_NODES = 4096


class PatchError(ValueError):
    """Raised when an input, directory tree, or output fails closed."""


@dataclass(frozen=True)
class OwnedFile:
    path: Path
    descriptor: int
    identity: tuple[int, int]


@dataclass(frozen=True)
class XdvdfsEntry:
    path: str
    sector: int
    size: int
    attributes: int

    @property
    def byte_offset(self) -> int:
        return self.sector * SECTOR_SIZE


@dataclass(frozen=True)
class Target:
    path: str
    expected_sector: int
    pack_offset: int
    expected_absolute_patch_offset: int
    expected_size: int
    expected_sha256: str
    expected_bytes: bytes


TARGETS = (
    Target(
        "vc_53450030/A",
        2_403_082,
        0x055CA850,
        5_011_470_416,
        310_294_528,
        "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
        struct.pack("<II", 0xFF000000, 0xFF385AAF),
    ),
    Target(
        "vc_53450030/B",
        2_179_328,
        0x0F3C7850,
        4_718_884_944,
        458_248_192,
        "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
        struct.pack("<II", 0xFF000000, 0xFF385AAF),
    ),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PatchError(message)


def fd_identity(descriptor: int) -> tuple[int, int]:
    info = os.fstat(descriptor)
    return info.st_dev, info.st_ino


def path_identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    return info.st_dev, info.st_ino


def reserve_file(path: Path, mode: int = 0o644) -> OwnedFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_RDWR |
            getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            mode,
        )
    except FileExistsError as exc:
        raise PatchError(f"output already exists: {path}") from exc
    return OwnedFile(path, descriptor, fd_identity(descriptor))


def owned_path_matches(owned: OwnedFile) -> bool:
    return path_identity(owned.path) == owned.identity


def unlink_if_owned(owned: OwnedFile | None) -> None:
    if owned is not None and owned_path_matches(owned):
        owned.path.unlink()


def canonical_new_path(path: Path) -> Path:
    parent = path.parent.resolve(strict=True)
    return parent / path.name


def sha256_fd(descriptor: int, offset: int = 0, length: int | None = None) -> str:
    digest = hashlib.sha256()
    position = offset
    remaining = length
    while remaining is None or remaining > 0:
        request = HASH_CHUNK if remaining is None else min(HASH_CHUNK, remaining)
        chunk = platform_compat.pread(descriptor, request, position)
        if not chunk:
            break
        digest.update(chunk)
        position += len(chunk)
        if remaining is not None:
            remaining -= len(chunk)
    if length is not None:
        require(remaining == 0, "short read while hashing bounded extent")
    return digest.hexdigest()


def read_exact(descriptor: int, offset: int, length: int) -> bytes:
    chunks: list[bytes] = []
    position = offset
    remaining = length
    while remaining:
        chunk = platform_compat.pread(descriptor, remaining, position)
        require(chunk, f"short read at 0x{position:x}")
        chunks.append(chunk)
        position += len(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def parse_xdvdfs(descriptor: int, image_size: int) -> tuple[dict[str, XdvdfsEntry], dict[str, int]]:
    header = read_exact(descriptor, XDVDFS_HEADER_OFFSET, 0x800)
    require(header[:20] == XDVDFS_MAGIC, "retail XDVDFS header magic mismatch")
    require(header[-20:] == XDVDFS_MAGIC, "retail XDVDFS tail magic mismatch")
    root_sector, root_size = struct.unpack_from("<II", header, 20)
    require(root_sector > 0 and root_size >= 14, "invalid XDVDFS root directory")
    require(root_sector * SECTOR_SIZE + root_size <= image_size,
            "XDVDFS root directory exceeds image")

    entries: dict[str, XdvdfsEntry] = {}
    visited_directories: set[tuple[int, int]] = set()
    total_nodes = 0

    def walk_directory(sector: int, size: int, prefix: str) -> None:
        nonlocal total_nodes
        key = (sector, size)
        require(key not in visited_directories, "cyclic XDVDFS directory extent")
        visited_directories.add(key)
        base = sector * SECTOR_SIZE
        require(size >= 14 and base + size <= image_size,
                f"directory extent outside image: {prefix or '/'}")
        directory = read_exact(descriptor, base, size)
        visited_offsets: set[int] = set()

        def walk_node(offset: int) -> None:
            nonlocal total_nodes
            require(offset not in visited_offsets,
                    f"cyclic XDVDFS AVL offset in {prefix or '/'}")
            require(offset >= 0 and offset + 14 <= size,
                    f"XDVDFS node outside directory {prefix or '/'}")
            visited_offsets.add(offset)
            total_nodes += 1
            require(total_nodes <= MAX_DIRECTORY_NODES,
                    "XDVDFS directory node limit exceeded")
            left, right, start_sector, file_size = struct.unpack_from(
                "<HHII", directory, offset
            )
            attributes = directory[offset + 12]
            name_length = directory[offset + 13]
            require(name_length > 0 and offset + 14 + name_length <= size,
                    f"invalid XDVDFS name length in {prefix or '/'}")
            name_bytes = directory[offset + 14 : offset + 14 + name_length]
            require(b"/" not in name_bytes and b"\\" not in name_bytes and
                    b"\0" not in name_bytes,
                    "invalid character in XDVDFS filename")
            try:
                name = name_bytes.decode("ascii")
            except UnicodeDecodeError as exc:
                raise PatchError("non-ASCII XDVDFS filename") from exc

            if left:
                walk_node(left * 4)
            path = f"{prefix}/{name}" if prefix else name
            normalized = path.casefold()
            require(normalized not in entries, f"duplicate XDVDFS path: {path}")
            extent_end = start_sector * SECTOR_SIZE + file_size
            require(extent_end <= image_size, f"XDVDFS extent outside image: {path}")
            entry = XdvdfsEntry(path, start_sector, file_size, attributes)
            entries[normalized] = entry
            if attributes & 0x10:
                require(file_size >= 14, f"empty/invalid XDVDFS directory: {path}")
                walk_directory(start_sector, file_size, path)
            else:
                require(attributes & 0x20, f"unsupported XDVDFS node type: {path}")
            if right:
                walk_node(right * 4)

        walk_node(0)

    walk_directory(root_sector, root_size, "")
    return entries, {
        "root_sector": root_sector,
        "root_size": root_size,
        "directory_extents": len(visited_directories),
        "directory_nodes": total_nodes,
    }


def copy_fd_exact(source: int, output: int, size: int) -> str:
    """Copy the complete source using copy_file_range, with a safe fallback."""
    position = 0
    method = "copy_file_range"
    while position < size:
        request = min(COPY_CHUNK, size - position)
        try:
            copied = os.copy_file_range(source, output, request, position, position)
        except OSError as exc:
            if exc.errno not in {errno.EXDEV, errno.EINVAL, errno.ENOSYS,
                                 errno.EOPNOTSUPP}:
                raise
            method = "pread_pwrite"
            break
        require(copied > 0, "short copy_file_range result")
        position += copied

    while position < size:
        chunk = platform_compat.pread(source, min(COPY_CHUNK, size - position), position)
        require(chunk, "short source read while copying XISO")
        written = 0
        while written < len(chunk):
            amount = os.pwrite(output, chunk[written:], position + written)
            require(amount > 0, "short destination write while copying XISO")
            written += amount
        position += len(chunk)
    require(os.fstat(output).st_size == size, "copied XISO size mismatch")
    return method


def compare_and_hash(
    source: int,
    output: int,
    size: int,
    allowed_offsets: set[int],
) -> tuple[str, str, list[int]]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    while position < size:
        request = min(HASH_CHUNK, size - position)
        source_bytes = platform_compat.pread(source, request, position)
        output_bytes = platform_compat.pread(output, request, position)
        require(len(source_bytes) == request and len(output_bytes) == request,
                "short read during final XISO comparison")
        source_hash.update(source_bytes)
        output_hash.update(output_bytes)
        if source_bytes != output_bytes:
            differences.extend(
                position + index
                for index, (before, after) in enumerate(zip(source_bytes, output_bytes))
                if before != after
            )
            require(len(differences) <= len(allowed_offsets),
                    "XISO contains more changes than the allowed byte set")
        position += request
    require(set(differences) == allowed_offsets,
            "XISO differences do not equal the proved patch byte set")
    return source_hash.hexdigest(), output_hash.hexdigest(), differences


def write_owned_json(owned: OwnedFile, value: dict[str, object]) -> None:
    require(owned_path_matches(owned), "manifest pathname no longer owns descriptor")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    offset = 0
    while offset < len(payload):
        written = os.pwrite(owned.descriptor, payload[offset:], offset)
        require(written > 0, "short manifest write")
        offset += written
    os.ftruncate(owned.descriptor, len(payload))
    os.fsync(owned.descriptor)
    require(read_exact(owned.descriptor, 0, len(payload)) == payload,
            "manifest readback mismatch")
    require(owned_path_matches(owned), "manifest pathname changed during write")


def run(source_path: Path, output_path: Path, manifest_path: Path) -> dict[str, object]:
    try:
        supplied_source_info = source_path.lstat()
    except FileNotFoundError as exc:
        raise PatchError(f"source does not exist: {source_path}") from exc
    require(not stat.S_ISLNK(supplied_source_info.st_mode),
            "source pathname must not be a symbolic link")
    source = source_path.resolve(strict=True)
    output = canonical_new_path(output_path)
    manifest = canonical_new_path(manifest_path)
    require(source.is_file() and not source.is_symlink(), "source must be a regular file")
    require(not output.exists(), f"output already exists: {output}")
    require(not manifest.exists(), f"manifest already exists: {manifest}")
    require(output != source and manifest != source and output != manifest,
            "source, output, and manifest paths must be distinct")

    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    output_owned: OwnedFile | None = None
    manifest_owned: OwnedFile | None = None
    success = False
    try:
        source_info = os.fstat(source_fd)
        require(stat.S_ISREG(source_info.st_mode), "source descriptor is not regular")
        require(source_info.st_size == EXPECTED_XISO_SIZE, "retail XISO size mismatch")
        source_identity = fd_identity(source_fd)
        require(path_identity(source) == source_identity, "source pathname changed")
        source_sha_before = sha256_fd(source_fd)
        require(source_sha_before == EXPECTED_XISO_SHA256, "retail XISO SHA-256 mismatch")
        entries, directory = parse_xdvdfs(source_fd, source_info.st_size)

        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        require(len(files) == 19, f"expected 19 XDVDFS files, found {len(files)}")
        xbe = entries.get("default.xbe")
        require(xbe is not None and xbe.size == EXPECTED_XBE_SIZE,
                "default.xbe extent mismatch")
        require(sha256_fd(source_fd, xbe.byte_offset, xbe.size) == EXPECTED_XBE_SHA256,
                "default.xbe SHA-256 mismatch")

        target_records: list[dict[str, object]] = []
        patch_offsets: list[int] = []
        allowed_changed_offsets: set[int] = set()
        for target in TARGETS:
            entry = entries.get(target.path.casefold())
            require(entry is not None, f"missing XDVDFS target: {target.path}")
            require(entry.sector == target.expected_sector,
                    f"target start sector mismatch: {target.path}")
            require(entry.size == target.expected_size, f"target size mismatch: {target.path}")
            require(sha256_fd(source_fd, entry.byte_offset, entry.size) == target.expected_sha256,
                    f"target SHA-256 mismatch: {target.path}")
            absolute = entry.byte_offset + target.pack_offset
            require(absolute == target.expected_absolute_patch_offset,
                    f"target absolute patch offset mismatch: {target.path}")
            require(target.pack_offset + len(target.expected_bytes) <= entry.size,
                    f"patch outside target extent: {target.path}")
            require(read_exact(source_fd, absolute, 8) == target.expected_bytes,
                    f"retail color words mismatch: {target.path}")
            patch_offsets.append(absolute)
            changed_relative = [
                index for index, (before, after) in
                enumerate(zip(target.expected_bytes, MAGENTA_PAIR)) if before != after
            ]
            allowed_changed_offsets.update(absolute + index for index in changed_relative)
            target_records.append({
                "path": entry.path,
                "start_sector": entry.sector,
                "expected_start_sector": target.expected_sector,
                "file_byte_offset": entry.byte_offset,
                "file_size": entry.size,
                "pack_patch_offset": target.pack_offset,
                "absolute_patch_offset": absolute,
                "expected_absolute_patch_offset": target.expected_absolute_patch_offset,
                "before_hex": target.expected_bytes.hex(),
                "after_hex": MAGENTA_PAIR.hex(),
                "changed_relative_bytes": changed_relative,
                "source_file_sha256": target.expected_sha256,
            })

        require(len(patch_offsets) == len(set(patch_offsets)) == 2,
                "target patch windows overlap or are missing")
        require(len(allowed_changed_offsets) == 10,
                "replacement no longer has the proved ten-byte delta")

        output_owned = reserve_file(output)
        require(fd_identity(output_owned.descriptor) != source_identity,
                "output unexpectedly aliases source inode")
        copy_method = copy_fd_exact(source_fd, output_owned.descriptor, source_info.st_size)
        require(owned_path_matches(output_owned), "output pathname changed during copy")
        for absolute in patch_offsets:
            require(os.pwrite(output_owned.descriptor, MAGENTA_PAIR, absolute) == 8,
                    f"short patch write at 0x{absolute:x}")
            require(read_exact(output_owned.descriptor, absolute, 8) == MAGENTA_PAIR,
                    f"patch readback mismatch at 0x{absolute:x}")
        os.fsync(output_owned.descriptor)
        require(owned_path_matches(output_owned), "output pathname changed during patch")
        require(path_identity(source) == source_identity, "source pathname changed during run")

        source_sha_after, output_sha, differences = compare_and_hash(
            source_fd,
            output_owned.descriptor,
            source_info.st_size,
            allowed_changed_offsets,
        )
        require(source_sha_after == source_sha_before, "retail XISO changed during run")
        require(path_identity(source) == source_identity, "source pathname changed after verify")
        require(owned_path_matches(output_owned), "output pathname changed after verify")

        output_entries, output_directory = parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        require(output_directory == directory, "XDVDFS directory metadata changed")
        require(output_entries == entries, "XDVDFS directory tree changed")
        for target, record in zip(TARGETS, target_records):
            entry = output_entries[target.path.casefold()]
            record["patched_file_sha256"] = sha256_fd(
                output_owned.descriptor, entry.byte_offset, entry.size
            )

        result: dict[str, object] = {
            "schema": SCHEMA,
            "source": {
                "path": str(source),
                "size": source_info.st_size,
                "sha256_before": source_sha_before,
                "sha256_after": source_sha_after,
                "device": source_identity[0],
                "inode": source_identity[1],
                "opened_read_only": True,
                "modified": False,
            },
            "output": {
                "path": str(output),
                "size": os.fstat(output_owned.descriptor).st_size,
                "sha256": output_sha,
                "copy_method": copy_method,
                "device": output_owned.identity[0],
                "inode": output_owned.identity[1],
                "exclusively_created": True,
                "distinct_from_source_inode": True,
            },
            "xdvdfs": {
                **directory,
                "file_count": len(files),
                "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "default_xbe_sha256": EXPECTED_XBE_SHA256,
            },
            "patch": {
                "targets": target_records,
                "replacement_words": ["0xffff00ff", "0xffff00ff"],
                "allowed_changed_byte_offsets": sorted(allowed_changed_offsets),
                "actual_changed_byte_offsets": differences,
                "actual_changed_byte_count": len(differences),
                "all_other_image_bytes_identical": True,
            },
            "claims": {
                "layout_identical_copy_only_xiso": True,
                "runtime_visibility_proved": False,
                "portme": "Boot this exact-layout copy in xemu and capture a matched Lions uniform target before claiming visible material semantics.",
            },
        }
        manifest_owned = reserve_file(manifest)
        write_owned_json(manifest_owned, result)
        require(path_identity(source) == source_identity,
                "source pathname changed during manifest write")
        require(owned_path_matches(output_owned),
                "output pathname changed during manifest write")
        require(owned_path_matches(manifest_owned),
                "manifest pathname changed after write")
        success = True
        return result
    finally:
        os.close(source_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            unlink_if_owned(manifest_owned)
            unlink_if_owned(output_owned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest)
    except (OSError, PatchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": result["schema"],
        "output": result["output"]["path"],
        "sha256": result["output"]["sha256"],
        "changed_bytes": result["patch"]["actual_changed_byte_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
