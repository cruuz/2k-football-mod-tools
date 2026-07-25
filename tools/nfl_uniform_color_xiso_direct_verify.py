#!/usr/bin/env python3
"""Independently verify the layout-preserving NFL 2K5 Lions XISO proof.

This verifier deliberately does not import the writer.  It parses the retail
XDVDFS tree itself, pins every retail extent, scans both 6.30 GB images, and
asks the pinned XboxDev extract-xiso build to list both trees.

Kernel write-seals are reached through :mod:`mod_editor.core.platform_compat`
rather than a module-scope ``import fcntl``.  That import does not exist on
Windows, so it made this module -- which five sibling verifiers import purely
for its XDVDFS parser -- impossible to even load there.  The seal contract
itself is unchanged: sealing is still required before the pinned extract-xiso
copy is executed, and it still fails closed where seals are unavailable.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import platform_compat  # noqa: E402


SECTOR = 2048
VOLUME_OFFSET = 0x10000
VOLUME_SIZE = 0x800
MAGIC = b"MICROSOFT*XBOX*MEDIA"
IMAGE_SIZE = 6_300_499_968
SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
OUTPUT_SHA256 = "4d7474e1994d08fc9c4eefec2f3eaa1ec7d4ea4fbf94e5370b2532060c26b7b4"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
BEFORE = bytes.fromhex("000000ffaf5a38ff")
AFTER = bytes.fromhex("ff00ffffff00ffff")
CHUNK = 16 * 1024 * 1024
EXPECTED_TOTAL_FILE_BYTES = 6_300_413_952
MANIFEST_SIZE = 3_326
MANIFEST_SHA256 = "c6e69f559e73fc9d9096d0ce41de261d3990da11e80e37689e01beeed1928ec8"
EXTRACT_XISO_SIZE = 56_584
EXTRACT_XISO_SHA256 = "96e6286d371e47e24474a3b7c89ef5c204ddca9c93c95d5ebcb7bcf1d6eb530f"


class VerifyError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


@dataclass(frozen=True)
class Entry:
    name: str
    sector: int
    size: int
    attributes: int

    @property
    def offset(self) -> int:
        return self.sector * SECTOR


# These values are independently frozen from the exact retail image.  They
# make a layout change visible even though the whole-source hash already pins
# it cryptographically.
EXPECTED_ENTRIES: dict[str, tuple[str, int, int, int]] = {
    "dashupdate.xbe": ("dashupdate.xbe", 7_004, 58_421_248, 0x20),
    "default.xbe": ("default.xbe", 1_170, 11_948_032, 0x20),
    "update.xbe": ("update.xbe", 34, 2_326_528, 0x20),
    "vc_53450030": ("vc_53450030", 35_530, 2_048, 0x10),
    "vc_53450030/0": ("vc_53450030/0", 796_479, 193_710_080, 0x20),
    "vc_53450030/1": ("vc_53450030/1", 649_995, 299_999_232, 0x20),
    "vc_53450030/2": ("vc_53450030/2", 891_064, 309_252_096, 0x20),
    "vc_53450030/3": ("vc_53450030/3", 495_938, 315_508_736, 0x20),
    "vc_53450030/4": ("vc_53450030/4", 1_042_066, 313_178_112, 0x20),
    "vc_53450030/5": ("vc_53450030/5", 345_561, 307_972_096, 0x20),
    "vc_53450030/6": ("vc_53450030/6", 1_350_843, 458_231_808, 0x20),
    "vc_53450030/7": ("vc_53450030/7", 1_194_985, 319_197_184, 0x20),
    "vc_53450030/8": ("vc_53450030/8", 1_574_589, 929_370_112, 0x20),
    "vc_53450030/9": ("vc_53450030/9", 35_531, 634_941_440, 0x20),
    "vc_53450030/a": ("vc_53450030/A", 2_403_082, 310_294_528, 0x20),
    "vc_53450030/b": ("vc_53450030/B", 2_179_328, 458_248_192, 0x20),
    "vc_53450030/c": ("vc_53450030/C", 2_554_593, 315_131_904, 0x20),
    "vc_53450030/d": ("vc_53450030/D", 2_028_383, 309_135_360, 0x20),
    "vc_53450030/e": ("vc_53450030/E", 2_708_466, 301_813_760, 0x20),
    "vc_53450030/f": ("vc_53450030/F", 2_855_836, 451_733_504, 0x20),
}

TARGETS = {
    "vc_53450030/a": {
        "sector": 2_403_082,
        "size": 310_294_528,
        "relative": 0x055CA850,
        "absolute": 5_011_470_416,
        "source_sha256": "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
        "output_sha256": "40faed4a93fbb81065035e8f296cea701778fb65c4361a47573e4f155f3df39e",
    },
    "vc_53450030/b": {
        "sector": 2_179_328,
        "size": 458_248_192,
        "relative": 0x0F3C7850,
        "absolute": 4_718_884_944,
        "source_sha256": "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
        "output_sha256": "81f681923c89c1a5c9460de9e70450fa29cc75ac4e9e0779a2f878060942e614",
    },
}

VIRTUAL_PATCHES = tuple(
    (target["absolute"], BEFORE, AFTER)
    for target in TARGETS.values()
)

FileIdentity = tuple[int, ...]


def required_executable_seals() -> int:
    """The write-seal set the pinned extract-xiso copy must carry.

    Resolved on demand instead of at import time: the seal names live in
    :mod:`fcntl`, and evaluating them at module scope is what stopped this file
    importing at all on a platform without that module.  The value is identical
    to the constant it replaces (``WRITE | GROW | SHRINK | SEAL``).
    """

    return platform_compat.write_seal_mask()


def file_identity(info: os.stat_result) -> FileIdentity:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_size, info.st_mtime_ns,
        *platform_compat.change_time_identity(info),
    )


def require_no_symlink_components(path: Path, *, missing_tail_ok: bool = False) \
        -> None:
    require(".." not in path.parts, f"pinned path contains '..': {path}")
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for index, component in enumerate(parts):
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            require(missing_tail_ok,
                    f"pinned path component is unavailable: {current}")
            return
        require(not stat.S_ISLNK(info.st_mode),
                f"pinned path component is a symlink: {current}")


def open_pinned(path: Path, expected_size: int,
                expected_sha256: str | None = None) \
        -> tuple[int, FileIdentity]:
    require_no_symlink_components(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            f"pinned path is not a non-symlink regular file: {path}")
    require(before.st_nlink == 1, f"pinned path is hard-linked: {path}")
    require(before.st_size == expected_size, f"pinned path size mismatch: {path}")
    identity = file_identity(before)
    descriptor = -1
    try:
        # Keep descriptor acquisition inside its cleanup region so an
        # asynchronous BaseException cannot strand the newly opened fd.
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
            getattr(os, "O_CLOEXEC", 0),
        )
        opened = os.fstat(descriptor)
        require(file_identity(opened) == identity,
                f"pinned path changed while opening: {path}")
        if expected_sha256 is not None:
            require(hash_extent(descriptor, 0, expected_size) == expected_sha256,
                    f"pinned path SHA-256 mismatch: {path}")
        require(file_identity(os.fstat(descriptor)) ==
                file_identity(path.lstat()) == identity,
                f"pinned path changed while hashing: {path}")
        return descriptor, identity
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                pass
        raise


def require_stable(path: Path, descriptor: int,
                   identity: FileIdentity,
                   expected_sha256: str | None = None) -> None:
    require(file_identity(os.fstat(descriptor)) ==
            file_identity(path.lstat()) == identity,
            f"pinned path changed during verification: {path}")
    if expected_sha256 is not None:
        require(hash_extent(descriptor, 0, identity[4]) == expected_sha256,
                f"pinned path bytes changed during verification: {path}")
        require(file_identity(os.fstat(descriptor)) ==
                file_identity(path.lstat()) == identity,
                f"pinned path changed while rehashing: {path}")


def pinned_manifest_payload(path: Path) -> bytes:
    descriptor = -1
    try:
        descriptor, identity = open_pinned(
            path, MANIFEST_SIZE, MANIFEST_SHA256
        )
        payload = pread_exact(descriptor, 0, MANIFEST_SIZE)
        require_stable(path, descriptor, identity)
        return payload
    finally:
        active_exception = sys.exc_info()[0] is not None
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                if not active_exception:
                    raise


def pread_exact(fd: int, offset: int, length: int) -> bytes:
    result = bytearray()
    while len(result) < length:
        chunk = os.pread(fd, length - len(result), offset + len(result))
        require(bool(chunk), f"short read at 0x{offset + len(result):x}")
        result.extend(chunk)
    return bytes(result)


def hash_extent(fd: int, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    position = 0
    while position < size:
        data = os.pread(fd, min(CHUNK, size - position), offset + position)
        require(bool(data), f"short extent read at 0x{offset + position:x}")
        digest.update(data)
        position += len(data)
    return digest.hexdigest()


def require_sealed_executable(descriptor: int, expected_size: int,
                              expected_sha256: str) -> None:
    info = os.fstat(descriptor)
    require(stat.S_ISREG(info.st_mode) and info.st_size == expected_size and
            stat.S_IMODE(info.st_mode) == 0o500,
            "sealed executable mode/type/size differs")
    # The kernel write-seal read-back is Linux-only (memfd F_*_SEALS). On a host
    # without it the immutability guarantee is provided instead by the SHA-256
    # extent check below plus the read-only (0o500) mode already asserted; asking
    # for the seal constants there would raise the opaque "requires the Linux
    # memfd write-seal constants" error. So verify the seals only where they can
    # exist, and never weaken the hash check, which runs on every platform.
    if platform_compat.supports_sealed_memfd():
        required = required_executable_seals()
        seals = platform_compat.read_seals(descriptor)
        require(seals & required == required,
                "sealed executable is not immutable")
    require(hash_extent(descriptor, 0, expected_size) == expected_sha256,
            "sealed executable SHA-256 differs")


def sealed_executable_copy(source_fd: int, expected_size: int,
                           expected_sha256: str) -> int:
    """Copy exact executable bytes to a write-sealed anonymous Linux inode."""
    # Same capability question as before -- memfd plus the F_*_SEALS commands --
    # asked through the one module allowed to know about fcntl, so a platform
    # that has neither is refused here instead of at import time.
    require(hasattr(os, "memfd_create") and
            hasattr(os, "MFD_ALLOW_SEALING") and
            platform_compat.supports_sealed_memfd(),
            "sealed memfd execution is unavailable")
    descriptor = -1
    try:
        descriptor = os.memfd_create(
            "nfl2k5-extract-xiso-verified",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
        digest = hashlib.sha256()
        position = 0
        while position < expected_size:
            payload = os.pread(
                source_fd, min(CHUNK, expected_size - position), position
            )
            require(bool(payload),
                    f"short executable source read at 0x{position:x}")
            digest.update(payload)
            written = 0
            while written < len(payload):
                count = os.write(descriptor, payload[written:])
                require(count > 0, "short sealed executable write")
                written += count
            position += len(payload)
        require(digest.hexdigest() == expected_sha256,
                "executable changed while making sealed copy")
        os.fchmod(descriptor, 0o500)
        os.fsync(descriptor)
        platform_compat.add_seals(descriptor, required_executable_seals())
        require_sealed_executable(
            descriptor, expected_size, expected_sha256
        )
        return descriptor
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException:
                pass
        raise


def parse_xdvdfs(fd: int, image_size: int) -> tuple[dict[str, Entry], tuple[int, int], list[tuple[int, int]]]:
    volume = pread_exact(fd, VOLUME_OFFSET, VOLUME_SIZE)
    require(volume[:20] == MAGIC and volume[-20:] == MAGIC,
            "XDVDFS volume signatures mismatch")
    root_sector, root_size = struct.unpack_from("<II", volume, 20)
    require((root_sector, root_size) == (33, 108), "retail root extent mismatch")

    entries: dict[str, Entry] = {}
    directory_extents: list[tuple[int, int]] = []
    active_directories: set[tuple[int, int]] = set()
    total_nodes = 0

    def parse_directory(sector: int, size: int, prefix: str) -> None:
        nonlocal total_nodes
        extent = (sector, size)
        require(extent not in active_directories, "recursive directory extent")
        require(14 <= size and sector * SECTOR + size <= image_size,
                f"directory outside image: {prefix or '/'}")
        active_directories.add(extent)
        directory_extents.append(extent)
        table = pread_exact(fd, sector * SECTOR, size)
        node_offsets: set[int] = set()

        def visit(offset: int) -> None:
            nonlocal total_nodes
            require(offset not in node_offsets, f"directory pointer cycle: {prefix or '/'}")
            require(0 <= offset <= size - 14, f"node outside directory: {prefix or '/'}")
            node_offsets.add(offset)
            total_nodes += 1
            require(total_nodes <= 64, "unexpectedly large retail tree")
            left, right, start_sector, file_size = struct.unpack_from("<HHII", table, offset)
            attributes, name_size = struct.unpack_from("BB", table, offset + 12)
            require(name_size and offset + 14 + name_size <= size, "invalid filename extent")
            raw_name = table[offset + 14:offset + 14 + name_size]
            require(not any(char in raw_name for char in (0, 47, 92)), "unsafe filename")
            try:
                name = raw_name.decode("ascii")
            except UnicodeDecodeError as exc:
                raise VerifyError("non-ASCII retail filename") from exc
            if left:
                visit(left * 4)
            full_name = f"{prefix}/{name}" if prefix else name
            key = full_name.casefold()
            require(key not in entries, f"duplicate path: {full_name}")
            require(start_sector * SECTOR + file_size <= image_size,
                    f"file extent outside image: {full_name}")
            entry = Entry(full_name, start_sector, file_size, attributes)
            entries[key] = entry
            if attributes & 0x10:
                parse_directory(start_sector, file_size, full_name)
            if right:
                visit(right * 4)

        visit(0)
        active_directories.remove(extent)

    parse_directory(root_sector, root_size, "")
    require(total_nodes == 20, f"expected 20 directory nodes, got {total_nodes}")
    return entries, (root_sector, root_size), directory_extents


def validate_expected_entries(entries: dict[str, Entry]) -> None:
    require(set(entries) == set(EXPECTED_ENTRIES), "XDVDFS path set differs from retail")
    for key, expected in EXPECTED_ENTRIES.items():
        actual = entries[key]
        require(
            (actual.name, actual.sector, actual.size, actual.attributes) == expected,
            f"XDVDFS extent/metadata mismatch: {expected[0]}",
        )


def scan_images(source_fd: int, output_fd: int) -> tuple[str, str, list[int]]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    while position < IMAGE_SIZE:
        request = min(CHUNK, IMAGE_SIZE - position)
        before = pread_exact(source_fd, position, request)
        after = pread_exact(output_fd, position, request)
        source_hash.update(before)
        output_hash.update(after)
        if before != after:
            for index, (old, new) in enumerate(zip(before, after)):
                if old != new:
                    differences.append(position + index)
                    require(len(differences) <= 10, "more than ten output bytes differ")
        position += request
    return source_hash.hexdigest(), output_hash.hexdigest(), differences


def validate_virtual_patches(image_size: int, patches=VIRTUAL_PATCHES) -> None:
    previous_end = 0
    for offset, before, after in sorted(patches):
        require(type(offset) is int and offset >= previous_end,
                "virtual patch ranges overlap or are unordered")
        require(isinstance(before, bytes) and isinstance(after, bytes) and
                len(before) == len(after) > 0,
                "virtual patch before/after shapes differ")
        require(offset + len(before) <= image_size,
                "virtual patch exceeds image size")
        previous_end = offset + len(before)


def virtualize_chunk(payload: bytes, position: int,
                     patches=VIRTUAL_PATCHES) -> bytes:
    """Return one source chunk with only the proved replacement windows overlaid."""
    validate_virtual_patches(IMAGE_SIZE, patches)
    result = bytearray(payload)
    chunk_end = position + len(payload)
    for offset, before, after in patches:
        overlap_start = max(position, offset)
        overlap_end = min(chunk_end, offset + len(before))
        if overlap_start >= overlap_end:
            continue
        source_start = overlap_start - position
        patch_start = overlap_start - offset
        length = overlap_end - overlap_start
        require(
            payload[source_start:source_start + length]
            == before[patch_start:patch_start + length],
            f"retail bytes differ at virtual patch 0x{offset:x}",
        )
        result[source_start:source_start + length] = \
            after[patch_start:patch_start + length]
    return bytes(result)


def scan_virtual_image(source_fd: int) -> tuple[str, str, list[int]]:
    """Hash the retail image and its deterministic non-materialized patched view."""
    validate_virtual_patches(IMAGE_SIZE)
    for offset, before, _after in VIRTUAL_PATCHES:
        require(pread_exact(source_fd, offset, len(before)) == before,
                f"retail virtual-patch source bytes differ at 0x{offset:x}")
    source_hash = hashlib.sha256()
    virtual_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    while position < IMAGE_SIZE:
        request = min(CHUNK, IMAGE_SIZE - position)
        before = pread_exact(source_fd, position, request)
        after = virtualize_chunk(before, position)
        source_hash.update(before)
        virtual_hash.update(after)
        if before != after:
            differences.extend(
                position + index
                for index, (old, new) in enumerate(zip(before, after))
                if old != new
            )
        position += request
    return source_hash.hexdigest(), virtual_hash.hexdigest(), differences


def hash_virtual_extent(source_fd: int, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    position = 0
    while position < size:
        request = min(CHUNK, size - position)
        absolute = offset + position
        source = pread_exact(source_fd, absolute, request)
        digest.update(virtualize_chunk(source, absolute))
        position += request
    return digest.hexdigest()


def extract_listing(tool_fd: int, image_fd: int) \
        -> tuple[str, list[tuple[str, int]], int]:
    completed = subprocess.run(
        [f"/proc/self/fd/{tool_fd}", "-l", f"/proc/self/fd/{image_fd}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        pass_fds=(tool_fd, image_fd),
    )
    require(completed.returncode == 0, f"extract-xiso list failed: {completed.stderr.strip()}")
    lines = completed.stdout.splitlines()
    require(lines and lines[0].startswith("extract-xiso v2.7.1 (01.11.14)"),
            "extract-xiso version banner mismatch")
    listing: list[tuple[str, int]] = []
    for line in lines:
        match = re.fullmatch(r"(/.+) \(([0-9]+) bytes\)", line)
        if match:
            listing.append((match.group(1), int(match.group(2))))
    summary = next((line for line in lines if line.startswith("19 files in ")), "")
    match = re.search(r" total ([0-9]+) bytes$", summary)
    require(match is not None, "extract-xiso summary missing")
    return lines[0], listing, int(match.group(1))


def validate_manifest(manifest_path: Path, canonical_path: Path, source: Path, output: Path,
                      differences: list[int]) -> None:
    live_bytes = pinned_manifest_payload(manifest_path)
    canonical_bytes = pinned_manifest_payload(canonical_path)
    require(live_bytes == canonical_bytes, "canonical report differs from writer manifest")
    value = json.loads(live_bytes)
    require(value.get("schema") == "nfl2k5_uniform_color_xiso_direct_patch/v1",
            "writer manifest schema mismatch")
    require(Path(value["source"]["path"]).resolve() == source.resolve(),
            "manifest source path mismatch")
    require(Path(value["output"]["path"]).resolve() == output.resolve(),
            "manifest output path mismatch")
    require(value["source"]["sha256_before"] == SOURCE_SHA256 and
            value["source"]["sha256_after"] == SOURCE_SHA256,
            "manifest source hash mismatch")
    require(value["output"]["sha256"] == OUTPUT_SHA256, "manifest output hash mismatch")
    require(value["patch"]["actual_changed_byte_count"] == 10,
            "manifest changed-byte count mismatch")
    require(value["patch"]["actual_changed_byte_offsets"] == differences and
            value["patch"]["allowed_changed_byte_offsets"] == differences,
            "manifest difference ledger mismatch")
    require(value["patch"]["all_other_image_bytes_identical"] is True,
            "manifest identity claim missing")
    require(value["xdvdfs"]["all_sector_extents_preserved"] is True and
            value["xdvdfs"]["tree_identical_after_patch"] is True,
            "manifest layout claim missing")
    require(value["claims"]["runtime_visibility_proved"] is False,
            "writer manifest overclaims runtime visibility")
    require(value["source"]["inode"] == source.stat().st_ino and
            value["source"]["device"] == source.stat().st_dev,
            "source identity changed since writer run")
    require(value["output"]["inode"] == output.stat().st_ino and
            value["output"]["device"] == output.stat().st_dev,
            "output identity changed since writer run")
    records = {record["path"].casefold(): record for record in value["patch"]["targets"]}
    require(set(records) == set(TARGETS), "manifest target set mismatch")
    for key, target in TARGETS.items():
        record = records[key]
        require(record["start_sector"] == target["sector"] and
                record["file_size"] == target["size"] and
                record["pack_patch_offset"] == target["relative"] and
                record["absolute_patch_offset"] == target["absolute"],
                f"manifest target extent mismatch: {key}")


def validate_virtual_manifest(
    manifest_path: Path,
    canonical_path: Path,
    source: Path,
    historical_output: Path,
    differences: list[int],
) -> None:
    """Validate frozen writer provenance without requiring its deleted output inode."""
    live_bytes = pinned_manifest_payload(manifest_path)
    canonical_bytes = pinned_manifest_payload(canonical_path)
    require(live_bytes == canonical_bytes,
            "canonical report differs from writer manifest")
    value = json.loads(live_bytes)
    require(value.get("schema") == "nfl2k5_uniform_color_xiso_direct_patch/v1",
            "writer manifest schema mismatch")
    require(Path(value["source"]["path"]).resolve() == source.resolve(),
            "manifest source path mismatch")
    require(Path(value["output"]["path"]).resolve() == historical_output.resolve(),
            "manifest historical output path mismatch")
    require(value["source"]["sha256_before"] == SOURCE_SHA256 and
            value["source"]["sha256_after"] == SOURCE_SHA256 and
            value["source"]["size"] == IMAGE_SIZE and
            value["source"]["opened_read_only"] is True and
            value["source"]["modified"] is False,
            "manifest source identity/claims differ")
    require(value["source"]["inode"] == source.stat().st_ino and
            value["source"]["device"] == source.stat().st_dev,
            "source identity changed since writer run")
    output = value["output"]
    require(output == {
        "copy_method": "copy_file_range",
        "device": 2049,
        "distinct_from_source_inode": True,
        "exclusively_created": True,
        "inode": 98_844_854,
        "path": str(historical_output),
        "sha256": OUTPUT_SHA256,
        "size": IMAGE_SIZE,
    }, "frozen historical output record differs")
    require(value["patch"]["actual_changed_byte_count"] == 10 and
            value["patch"]["actual_changed_byte_offsets"] == differences and
            value["patch"]["allowed_changed_byte_offsets"] == differences and
            value["patch"]["replacement_words"] ==
            ["0xffff00ff", "0xffff00ff"] and
            value["patch"]["all_other_image_bytes_identical"] is True,
            "manifest virtual difference ledger differs")
    require(value["xdvdfs"] == {
        "all_sector_extents_preserved": True,
        "default_xbe_sha256": XBE_SHA256,
        "directory_extents": 2,
        "directory_nodes": 20,
        "file_count": 19,
        "root_sector": 33,
        "root_size": 108,
        "tree_identical_after_patch": True,
    }, "manifest XDVDFS record differs")
    require(value["claims"]["layout_identical_copy_only_xiso"] is True and
            value["claims"]["runtime_visibility_proved"] is False,
            "writer manifest claims differ")
    records = {record["path"].casefold(): record
               for record in value["patch"]["targets"]}
    require(set(records) == set(TARGETS), "manifest target set mismatch")
    for key, target in TARGETS.items():
        record = records[key]
        require(record["start_sector"] == target["sector"] and
                record["file_size"] == target["size"] and
                record["pack_patch_offset"] == target["relative"] and
                record["absolute_patch_offset"] == target["absolute"] and
                record["before_hex"] == BEFORE.hex() and
                record["after_hex"] == AFTER.hex() and
                record["source_file_sha256"] == target["source_sha256"] and
                record["patched_file_sha256"] == target["output_sha256"],
                f"manifest virtual target differs: {key}")


def run(source: Path, output: Path, manifest: Path, canonical: Path,
        extract_xiso: Path) -> None:
    for role, path in (("source", source), ("output", output)):
        require_no_symlink_components(path)
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                f"{role} must be a non-symlink regular file")
        require(info.st_nlink == 1, f"{role} is hard-linked")
        require(info.st_size == IMAGE_SIZE, f"{role} size mismatch")
    require((source.stat().st_dev, source.stat().st_ino) !=
            (output.stat().st_dev, output.stat().st_ino),
            "source and output alias the same inode")
    extract_fd = -1
    extract_identity: FileIdentity | None = None
    sealed_extract_fd = -1
    source_fd = -1
    source_identity: FileIdentity | None = None
    output_fd = -1
    output_identity: FileIdentity | None = None
    try:
        extract_fd, extract_identity = open_pinned(
            extract_xiso, EXTRACT_XISO_SIZE, EXTRACT_XISO_SHA256
        )
        require(os.fstat(extract_fd).st_mode & 0o111,
                "pinned extract-xiso descriptor is not executable")
        sealed_extract_fd = sealed_executable_copy(
            extract_fd, EXTRACT_XISO_SIZE, EXTRACT_XISO_SHA256
        )
        source_fd, source_identity = open_pinned(source, IMAGE_SIZE)
        output_fd, output_identity = open_pinned(output, IMAGE_SIZE)
        source_opened = os.fstat(source_fd)
        output_opened = os.fstat(output_fd)
        require((source_opened.st_dev, source_opened.st_ino) !=
                (output_opened.st_dev, output_opened.st_ino),
                "pinned source and output descriptors alias the same inode")
        source_entries, source_root, source_directories = parse_xdvdfs(source_fd, IMAGE_SIZE)
        output_entries, output_root, output_directories = parse_xdvdfs(output_fd, IMAGE_SIZE)
        validate_expected_entries(source_entries)
        validate_expected_entries(output_entries)
        require(source_entries == output_entries and source_root == output_root,
                "output XDVDFS tree differs")
        require(source_directories == output_directories == [(33, 108), (35_530, 2_048)],
                "directory extents differ")
        require(pread_exact(source_fd, VOLUME_OFFSET, VOLUME_SIZE) ==
                pread_exact(output_fd, VOLUME_OFFSET, VOLUME_SIZE),
                "XDVDFS volume descriptor changed")
        for sector, size in source_directories:
            require(pread_exact(source_fd, sector * SECTOR, size) ==
                    pread_exact(output_fd, sector * SECTOR, size),
                    f"directory bytes changed at sector {sector}")

        source_sha, output_sha, differences = scan_images(source_fd, output_fd)
        require(source_sha == SOURCE_SHA256, "retail source SHA-256 mismatch")
        require(output_sha == OUTPUT_SHA256, "direct output SHA-256 mismatch")

        allowed = sorted(
            target["absolute"] + index
            for target in TARGETS.values()
            for index, (old, new) in enumerate(zip(BEFORE, AFTER))
            if old != new
        )
        require(len(allowed) == 10 and differences == allowed,
                "full-image differences are not the exact ten-byte patch")
        for key, target in TARGETS.items():
            entry = source_entries[key]
            require(entry.offset + target["relative"] == target["absolute"],
                    f"target absolute offset arithmetic mismatch: {key}")
            require(pread_exact(source_fd, target["absolute"], 8) == BEFORE,
                    f"retail target bytes mismatch: {key}")
            require(pread_exact(output_fd, target["absolute"], 8) == AFTER,
                    f"patched target bytes mismatch: {key}")
            require(hash_extent(source_fd, entry.offset, entry.size) == target["source_sha256"],
                    f"retail target hash mismatch: {key}")
            require(hash_extent(output_fd, entry.offset, entry.size) == target["output_sha256"],
                    f"patched target hash mismatch: {key}")

        xbe = source_entries["default.xbe"]
        require(hash_extent(source_fd, xbe.offset, xbe.size) == XBE_SHA256 and
                hash_extent(output_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "default.xbe changed")
        pack0 = source_entries["vc_53450030/0"]
        require(hash_extent(source_fd, pack0.offset, pack0.size) == PACK0_SHA256 and
                hash_extent(output_fd, pack0.offset, pack0.size) == PACK0_SHA256,
                "unrelated pack 0 changed")
        _, source_listing, source_total = extract_listing(
            sealed_extract_fd, source_fd
        )
        banner, output_listing, output_total = extract_listing(
            sealed_extract_fd, output_fd
        )
        require(source_listing == output_listing, "extract-xiso listings differ")
        require(len(source_listing) == 20,
                "extract-xiso did not list 19 files plus directory")
        require(source_total == output_total == EXPECTED_TOTAL_FILE_BYTES,
                "extract-xiso total byte count mismatch")
        validate_manifest(manifest, canonical, source, output, differences)
        require_sealed_executable(
            sealed_extract_fd, EXTRACT_XISO_SIZE, EXTRACT_XISO_SHA256
        )
        # The child consumed the image descriptors after the first full scan.
        # Rehash them now, and include mode/ctime in both identity checks, so an
        # in-place mutate/restore cannot be hidden by resetting mtime.
        assert (source_identity is not None and output_identity is not None and
                extract_identity is not None)
        require_stable(
            source, source_fd, source_identity, SOURCE_SHA256
        )
        require_stable(
            output, output_fd, output_identity, OUTPUT_SHA256
        )
        require_stable(
            extract_xiso, extract_fd, extract_identity, EXTRACT_XISO_SHA256
        )
    finally:
        active_exception = sys.exc_info()[0] is not None
        cleanup_errors: list[BaseException] = []
        for descriptor in (
            output_fd, source_fd, sealed_extract_fd, extract_fd,
        ):
            if descriptor < 0:
                continue
            try:
                os.close(descriptor)
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors and not active_exception:
            raise cleanup_errors[0]

    print(
        "NFL_UNIFORM_COLOR_XISO_DIRECT_VERIFY_PASS "
        f"source_sha={SOURCE_SHA256} output_sha={OUTPUT_SHA256} "
        "files=19 entries=20 root_sector=33 target_lbas=2403082,2179328 "
        f"changed_bytes=10 header=identical layout=identical extract_xiso='{banner}' "
        "default_xbe=unchanged pack0=unchanged runtime_visibility=false"
    )


def run_virtual(source: Path, historical_output: Path, manifest: Path,
                canonical: Path, extract_xiso: Path) -> None:
    """Verify the exact output as a streamed virtual view of the retail XISO."""
    del extract_xiso  # The independent XDVDFS parser is the virtual-mode authority.
    require_no_symlink_components(source)
    source_info = source.lstat()
    require(stat.S_ISREG(source_info.st_mode) and
            not stat.S_ISLNK(source_info.st_mode) and
            source_info.st_nlink == 1 and source_info.st_size == IMAGE_SIZE,
            "source size/type/link-count mismatch")
    require_no_symlink_components(historical_output, missing_tail_ok=True)
    require(not historical_output.exists() and not historical_output.is_symlink(),
            "virtual mode is only for the absent historical output")

    source_fd = -1
    source_identity: FileIdentity | None = None
    try:
        source_fd, source_identity = open_pinned(source, IMAGE_SIZE)
        entries, root, directories = parse_xdvdfs(source_fd, IMAGE_SIZE)
        validate_expected_entries(entries)
        require(root == (33, 108) and directories == [(33, 108), (35_530, 2_048)],
                "retail directory extents differ")
        source_sha, virtual_sha, differences = scan_virtual_image(source_fd)
        require(source_sha == SOURCE_SHA256, "retail source SHA-256 mismatch")
        require(virtual_sha == OUTPUT_SHA256,
                "virtual direct-output SHA-256 mismatch")
        allowed = sorted(
            target["absolute"] + index
            for target in TARGETS.values()
            for index, (old, new) in enumerate(zip(BEFORE, AFTER))
            if old != new
        )
        require(differences == allowed and len(differences) == 10,
                "virtual full-image differences are not the exact ten-byte patch")
        for key, target in TARGETS.items():
            entry = entries[key]
            require(entry.offset + target["relative"] == target["absolute"],
                    f"target absolute offset arithmetic mismatch: {key}")
            before = pread_exact(source_fd, target["absolute"], len(BEFORE))
            require(before == BEFORE and
                    virtualize_chunk(before, target["absolute"]) == AFTER,
                    f"virtual target bytes mismatch: {key}")
            require(hash_extent(source_fd, entry.offset, entry.size) ==
                    target["source_sha256"],
                    f"retail target hash mismatch: {key}")
            require(hash_virtual_extent(source_fd, entry.offset, entry.size) ==
                    target["output_sha256"],
                    f"virtual patched target hash mismatch: {key}")
        xbe = entries["default.xbe"]
        pack0 = entries["vc_53450030/0"]
        require(hash_extent(source_fd, xbe.offset, xbe.size) == XBE_SHA256 and
                hash_virtual_extent(source_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "virtual default.xbe identity differs")
        require(hash_extent(source_fd, pack0.offset, pack0.size) == PACK0_SHA256 and
                hash_virtual_extent(source_fd, pack0.offset, pack0.size) == PACK0_SHA256,
                "virtual unrelated pack 0 identity differs")
        validate_virtual_manifest(
            manifest, canonical, source, historical_output, differences
        )
        assert source_identity is not None
        require_stable(source, source_fd, source_identity)
    finally:
        active_exception = sys.exc_info()[0] is not None
        if source_fd >= 0:
            try:
                os.close(source_fd)
            except BaseException:
                if not active_exception:
                    raise
    print(
        "NFL_UNIFORM_COLOR_XISO_DIRECT_VIRTUAL_VERIFY_PASS "
        f"source_sha={SOURCE_SHA256} virtual_output_sha={OUTPUT_SHA256} "
        "files=19 entries=20 root_sector=33 target_lbas=2403082,2179328 "
        "changed_bytes=10 layout=identical xdvdfs_parser=independent "
        "default_xbe=unchanged pack0=unchanged output_materialized=false "
        "runtime_visibility=false"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--canonical-report", required=True, type=Path)
    parser.add_argument("--extract-xiso", required=True, type=Path)
    parser.add_argument("--virtual-output", action="store_true")
    args = parser.parse_args()
    try:
        if args.virtual_output:
            run_virtual(
                args.source, args.output, args.manifest,
                args.canonical_report, args.extract_xiso,
            )
        else:
            run(args.source, args.output, args.manifest, args.canonical_report,
                args.extract_xiso)
    except (OSError, VerifyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
