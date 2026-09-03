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


SCHEMA = "nfl2k5_uniform_color_xiso_direct_patch/v1"
SECTOR_SIZE = 2048
XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"
XDVDFS_HEADER_OFFSET = 0x10000
# Byte at which the game partition can begin, most common first. 0 is an
# extracted .xiso; the others are raw reads that keep the video partition in
# front. See locate_xdvdfs_base for why this is probed rather than assumed.
XDVDFS_BASE_OFFSETS: tuple[int, ...] = (
    0x00000000,   # extracted .xiso -- the game partition is the whole file
    0x18300000,   # XGD1 raw dump (405,798,912)
    0x0FD90000,   # XGD2 raw dump (265,879,552)
    0x02080000,   # XGD3 raw dump (34,078,720)
)
EXPECTED_XISO_SIZE = 6_300_499_968
EXPECTED_XISO_SHA256 = (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
EXPECTED_XBE_SIZE = 11_948_032
MAGENTA_PAIR = struct.pack("<II", 0xFFFF00FF, 0xFFFF00FF)


def pack_colors(facemask: int, turtleneck: int) -> bytes:
    """The eight bytes this writer replaces, from two ARGB colours.

    Word 0 is the facemask/faceshield tint and word 1 is HI_turtleneck, both
    established by executable trace. Passing the same magenta for both
    reproduces the original visibility proof exactly, which is why that stays
    the default.
    """
    for value, name in ((facemask, "facemask"), (turtleneck, "turtleneck")):
        require(type(value) is int and 0 <= value <= 0xFFFFFFFF,
                f"{name} colour must be a 32-bit ARGB integer")
    return struct.pack("<II", facemask, turtleneck)
COPY_CHUNK = 32 * 1024 * 1024
HASH_CHUNK = 16 * 1024 * 1024
MAX_DIRECTORY_NODES = 4096
#: Real discs nest a handful of levels; this only has to stop a
#: degenerate tree before the interpreter stack does.
MAX_DIRECTORY_DEPTH = 64
#: Every recursive step of the parse, directory descent and AVL walk alike,
#: counted together. CPython allows about 1000 frames; a real disc uses well
#: under a hundred here, so this refuses long before the stack runs out and
#: leaves generous room for the caller's own frames.
MAX_PARSE_RECURSION = 400


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
    base_offset: int = 0

    @property
    def byte_offset(self) -> int:
        """Absolute byte offset in the image file, not in the game partition.

        XDVDFS sector numbers are relative to the start of the game partition.
        In the extracted ``.xiso`` layout that partition begins at byte 0 and
        the two are the same number, which is why this used to ignore the base.
        A raw disc dump keeps the video partition in front of it, so the same
        sector lives ``base_offset`` bytes further into the file.
        """
        return self.base_offset + self.sector * SECTOR_SIZE


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


def pread(descriptor: int, count: int, offset: int) -> bytes:
    """Positional read that never disturbs the descriptor's shared offset.

    ``os.pread`` is a POSIX-only single syscall: Windows CPython does not
    define it at all, so every positional read below raised ``AttributeError``
    there.  This module is executed as a pinned, self-contained import closure
    (hashed bytes, ``-I -S``, staged tree), so it may not import the editor's
    platform layer; the fallback is therefore inline and uses nothing but
    :mod:`os`.  Where ``os.pread`` exists it still runs, unchanged -- POSIX
    executes exactly the same syscall it always did.

    The fallback remembers the descriptor's current offset, seeks, reads, and
    restores that offset in ``finally``, so a caller that also uses sequential
    reads on the same descriptor sees the position it left behind.  It returns
    fewer than ``count`` bytes only at end-of-file, exactly like ``os.pread``
    on a regular file, so every fail-closed short-read/EOF check in this module
    keeps its behaviour and its message.

    Non-atomicity caveat: unlike the syscall, seek/read/restore can interleave
    with a concurrent seek on a *shared* descriptor.  Every descriptor here is
    opened and driven by this single synchronous owner, which is what makes the
    fallback equivalent; it is not a general-purpose positional primitive.
    """

    positional = getattr(os, "pread", None)
    if positional is not None:
        return positional(descriptor, count, offset)
    if count <= 0:
        return b""
    saved = os.lseek(descriptor, 0, os.SEEK_CUR)
    try:
        os.lseek(descriptor, offset, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.lseek(descriptor, saved, os.SEEK_SET)


def pwrite(descriptor: int, data: bytes, offset: int) -> int:
    """Positional write with the same offset discipline as :func:`pread`.

    ``os.pwrite`` is absent on Windows for the same reason ``os.pread`` is.
    The inline fallback saves the descriptor's offset, seeks, writes every
    supplied byte at ``offset``, and restores the saved offset in ``finally``.
    It returns the number of bytes written, so the short-write guards below
    fail closed identically on both paths.
    """

    positional = getattr(os, "pwrite", None)
    if positional is not None:
        return positional(descriptor, data, offset)
    if not data:
        return 0
    saved = os.lseek(descriptor, 0, os.SEEK_CUR)
    try:
        os.lseek(descriptor, offset, os.SEEK_SET)
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count == 0:
                break
            written += count
        return written
    finally:
        os.lseek(descriptor, saved, os.SEEK_SET)


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
            getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) |
            getattr(os, "O_BINARY", 0),
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
        chunk = pread(descriptor, request, position)
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
        chunk = pread(descriptor, remaining, position)
        require(chunk, f"short read at 0x{position:x}")
        chunks.append(chunk)
        position += len(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def iter_xdvdfs_bases(
    descriptor: int, image_size: int, *, require_entry: str | None = None
) -> "Iterable[int]":
    """Yield every game-partition base in this image, best candidate first.

    A raw disc read contains TWO filesystems. The video partition sits at
    byte 0 and holds only the "this disc requires an Xbox" placeholder; the
    game is in a second partition further in. Stopping at the first valid
    header therefore finds the wrong one and concludes the disc is not the
    game -- which is precisely how a real raw dump was rejected even after
    the reader learned to search. So candidates are ENUMERATED, and when
    ``require_entry`` is given only a partition actually containing that
    file is yielded.
    """
    seen: set[int] = set()

    def candidate(base: int) -> bool:
        if base in seen:
            return False
        seen.add(base)
        start = base + XDVDFS_HEADER_OFFSET
        if start + 0x800 > image_size:
            return False
        try:
            header = read_exact(descriptor, start, 0x800)
        except PatchError:
            return False
        if header[:20] != XDVDFS_MAGIC or header[-20:] != XDVDFS_MAGIC:
            return False
        if require_entry is None:
            return True
        try:
            entries, _ = parse_xdvdfs(descriptor, image_size, base)
        except PatchError:
            return False
        return require_entry.casefold() in entries

    for base in XDVDFS_BASE_OFFSETS:
        if candidate(base):
            yield base
    for base in _scan_xdvdfs_candidates(descriptor, image_size):
        if candidate(base):
            yield base


def locate_xdvdfs_base(
    descriptor: int, image_size: int, *, require_entry: str | None = "default.xbe"
) -> int:
    """Find the byte where this image's game partition starts.

    A dump of an Xbox disc is not one canonical file. Which byte the game
    partition begins at depends on how the disc was read, and every one of
    these is a legitimate dump of the same game:

    * ``0`` -- an extracted ``.xiso``; the game partition *is* the file.
    * ``0x18300000`` -- a raw XGD1 read that keeps the video partition.
    * ``0x0FD90000`` / ``0x02080000`` -- the XGD2 and XGD3 equivalents.

    Assuming ``0`` is what made the editor reject other people's dumps with a
    magic-mismatch, so the base is discovered rather than assumed. Only offsets
    carrying the magic at both ends of the header sector are accepted, which is
    a 40-byte agreement at a 2,048-aligned position -- not something arbitrary
    data supplies by accident.
    """
    for base in iter_xdvdfs_bases(descriptor, image_size, require_entry=require_entry):
        return base
    # The known offsets are only a fast path. Rippers exist that we have never
    # seen and cannot enumerate, and guessing from a list is exactly what made
    # this reject legal dumps in the first place, so fall back to FINDING the
    # filesystem: search sector-aligned positions for the 20-byte magic and
    # confirm the candidate really is a header by requiring the magic at BOTH
    # ends of its sector and a root directory that fits inside the image.
    # Nothing carried the required file; fall back to any real filesystem so
    # a non-game Xbox image still parses rather than being called corrupt.
    if require_entry is not None:
        for base in iter_xdvdfs_bases(descriptor, image_size):
            return base
    identified = identify_non_xdvdfs_image(descriptor, image_size)
    raise PatchError(
        "No Xbox XDVDFS filesystem was found in this image. The known "
        "game-partition offsets ("
        + ", ".join(f"0x{value:X}" for value in XDVDFS_BASE_OFFSETS)
        + f") were checked and then the first {_XDVDFS_SCAN_LIMIT >> 20} MiB "
        "were searched sector by sector. "
        + (identified or "This does not look like an Xbox disc image.")
    )


# Containers people actually hand these editors instead of an Xbox disc image.
# Saying which one it is turns a dead end into an answer: the first report of
# this sent someone off to re-dump a disc that was fine, because "not a valid
# xbox iso image" cannot tell a bad dump apart from a different console.
def identify_non_xdvdfs_image(descriptor: int, image_size: int) -> str | None:
    """Name the container, when it is one we recognise but cannot read.

    Returns a sentence for the user, or ``None`` when nothing is recognised.
    Recognition is by on-disc structure, never by file name or extension --
    the reported case arrived named ``.iso`` and was a PlayStation 3 disc.
    """
    try:
        head = pread(descriptor, 4, 0)
    except (OSError, PatchError, ValueError):
        return None
    if head in (b"CON ", b"LIVE", b"PIRS"):
        return (
            "This is an Xbox 360 STFS package, not a disc image. Installed "
            "titles and downloads are packaged; the editor needs the disc."
        )
    for magic, name in (
        (b"PK\x03\x04", "ZIP archive"),
        (b"Rar!", "RAR archive"),
        (b"7z\xbc\xaf", "7-Zip archive"),
        (b"\x1f\x8b", "gzip file"),
    ):
        if head.startswith(magic):
            return f"This is a {name}. Extract the disc image from it first."

    # ISO 9660: primary volume descriptor at sector 16, "\x01CD001".
    if image_size < 0x8000 + 2048:
        return None
    try:
        volume = pread(descriptor, 2048, 0x8000)
        front = pread(descriptor, min(image_size, 4 << 20), 0)
    except (OSError, PatchError, ValueError):
        return None
    if volume[:6] != b"\x01CD001":
        return None
    label = volume[40:72].decode("ascii", "replace").strip()
    named = f" (volume label {label})" if label else ""
    if b"PS3_GAME" in front or b"PS3_DISC" in front:
        return (
            "This is a PlayStation 3 disc image" + named + ", not an Xbox one. "
            "It holds PS3_GAME/USRDIR and an EBOOT.BIN where an Xbox disc holds "
            "default.xex, and the two releases split their game archives "
            "differently, so the PS3 disc cannot stand in for the Xbox one."
        )
    if b"SYSTEM.CNF" in front:
        return "This is a PlayStation disc image" + named + ", not an Xbox one."
    return (
        "This is an ISO 9660 disc image" + named + ". Xbox discs use XDVDFS "
        "instead, so this is a disc for another system."
    )


# How far in to search for a game partition. Video partitions sit at the front
# of a disc and the largest we know of ends at 0x18300000 (387 MiB), so a 1 GiB
# window covers every real layout with a wide margin while staying quick.
_XDVDFS_SCAN_LIMIT = 1 << 30


def _scan_xdvdfs_candidates(descriptor: int, image_size: int) -> "Iterable[int]":
    """Yield every sector-aligned position that looks like a real header."""
    window = min(image_size, _XDVDFS_SCAN_LIMIT)
    chunk_size = 8 << 20
    overlap = len(XDVDFS_MAGIC)
    position = 0
    while position < window:
        length = min(chunk_size, window - position)
        try:
            chunk = read_exact(descriptor, position, length)
        except PatchError:
            return
        start = 0
        while True:
            hit = chunk.find(XDVDFS_MAGIC, start)
            if hit < 0:
                break
            start = hit + 1
            absolute = position + hit
            # The magic opens the header sector, and that sector must be the
            # 0x10000th byte of its partition.
            if absolute % SECTOR_SIZE or absolute < XDVDFS_HEADER_OFFSET:
                continue
            base = absolute - XDVDFS_HEADER_OFFSET
            try:
                header = read_exact(descriptor, absolute, 0x800)
            except PatchError:
                continue
            if header[-20:] != XDVDFS_MAGIC:
                continue
            root_sector, root_size = struct.unpack_from("<II", header, 20)
            if root_sector <= 0 or root_size < 14:
                continue
            if base + root_sector * SECTOR_SIZE + root_size > image_size:
                continue
            yield base
        position += max(length - overlap, 1)


def parse_xdvdfs(
    descriptor: int, image_size: int, base_offset: int | None = None
) -> tuple[dict[str, XdvdfsEntry], dict[str, int]]:
    if base_offset is None:
        base_offset = locate_xdvdfs_base(descriptor, image_size)
    header = read_exact(descriptor, base_offset + XDVDFS_HEADER_OFFSET, 0x800)
    require(header[:20] == XDVDFS_MAGIC, "retail XDVDFS header magic mismatch")
    require(header[-20:] == XDVDFS_MAGIC, "retail XDVDFS tail magic mismatch")
    root_sector, root_size = struct.unpack_from("<II", header, 20)
    require(root_sector > 0 and root_size >= 14, "invalid XDVDFS root directory")
    require(base_offset + root_sector * SECTOR_SIZE + root_size <= image_size,
            "XDVDFS root directory exceeds image")

    entries: dict[str, XdvdfsEntry] = {}
    visited_directories: set[tuple[int, int]] = set()
    total_nodes = 0

    def walk_directory(sector: int, size: int, prefix: str, depth: int = 0,
                       stack: int = 0) -> None:
        nonlocal total_nodes
        # Both walks below recurse. Without a bound, a deep or hostile tree
        # exhausts the interpreter stack and surfaces as RecursionError, which
        # escapes every caller's `except PatchError` and reads like a crash
        # rather than a rejected image.
        require(depth <= MAX_DIRECTORY_DEPTH,
                f"XDVDFS directory nesting is too deep at {prefix or '/'}")
        # `depth` counts nested directories only. The AVL walk inside one
        # directory recurses too, and the two interleave, so neither bound alone
        # describes the interpreter stack: 4096 nodes chained left is 4096 frames
        # deep inside a single directory nested zero deep. `stack` counts every
        # recursive call of either kind, which is the thing that actually runs
        # out.
        require(stack <= MAX_PARSE_RECURSION,
                f"XDVDFS structure is nested too deeply at {prefix or '/'}")
        key = (sector, size)
        require(key not in visited_directories, "cyclic XDVDFS directory extent")
        visited_directories.add(key)
        base = base_offset + sector * SECTOR_SIZE
        require(size >= 14 and base + size <= image_size,
                f"directory extent outside image: {prefix or '/'}")
        directory = read_exact(descriptor, base, size)
        visited_offsets: set[int] = set()

        def walk_node(offset: int, depth: int = 0, stack: int = 0) -> None:
            nonlocal total_nodes
            require(stack <= MAX_PARSE_RECURSION,
                    f"XDVDFS directory tree is unbalanced past the safe depth "
                    f"in {prefix or '/'}")
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
            except UnicodeDecodeError:
                # One oddly-named file used to abort the entire listing, so a
                # disc with a single accented filename could not be read at all.
                # latin-1 maps every byte to exactly one codepoint and back, so
                # the name stays usable and byte-reversible rather than being
                # guessed at or replaced.
                name = name_bytes.decode("latin-1")

            if left:
                walk_node(left * 4, depth, stack + 1)
            path = f"{prefix}/{name}" if prefix else name
            normalized = path.casefold()
            require(normalized not in entries, f"duplicate XDVDFS path: {path}")
            extent_end = base_offset + start_sector * SECTOR_SIZE + file_size
            require(extent_end <= image_size, f"XDVDFS extent outside image: {path}")
            entry = XdvdfsEntry(path, start_sector, file_size, attributes, base_offset)
            entries[normalized] = entry
            if attributes & 0x10:
                # An empty directory is legal and carries no extent. Demanding
                # one used to abort the whole parse over a folder with nothing
                # in it, so the directory is recorded and simply not descended.
                if file_size >= 14:
                    walk_directory(start_sector, file_size, path, depth + 1,
                                   stack + 1)
            # Anything that is not a directory is a file. The old rule demanded
            # the ARCHIVE bit (0x20), which extract-xiso happens to set on
            # everything it rebuilds -- but a pressed disc carries the original
            # attributes, and this game's files are 0x80 (FILE_ATTRIBUTE_NORMAL)
            # there. That single bit rejected every file on a genuine disc read,
            # default.xbe included, so the image could not even be identified.
            # The attribute was never a safety property: extents are bounds
            # checked against the image independently, just above.
            if right:
                walk_node(right * 4, depth, stack + 1)

        walk_node(0, depth, stack + 1)

    walk_directory(root_sector, root_size, "")
    return entries, {
        "root_sector": root_sector,
        "root_size": root_size,
        "directory_extents": len(visited_directories),
        "directory_nodes": total_nodes,
    }


# ---------------------------------------------------------------------------
# Where a game file is in THIS image.
#
# Every archive pack of NFL 2K5 lives under one folder on the disc. The retail
# rip these editors were developed against places pack 0 at sector 796,479,
# which is byte 1,631,188,992 of an extracted .xiso -- and for a long time
# that number was simply typed into writers as "where pack 0 is". It is not.
# A raw dump keeps the video partition in front (the whole game partition
# moves), and an extract-xiso rebuild or a different ripper lays the same 19
# files out at completely different sectors while every file stays
# byte-identical. The first public report of this was a legal USA retail .iso
# on which the executable-only patches worked (default.xbe is located through
# the directory) and the pack-0 schedule patch reported the pack as "foreign"
# because it had read 193 MB from the wrong place.
#
# So the pack's location is RESOLVED through the XDVDFS directory of the image
# actually being read or written, exactly as default.xbe already was. The
# retail sectors survive only as provenance for build receipts (see
# RETAIL_PACK_SECTORS) and are never used to address an image.
PACK_FOLDER = "vc_53450030"
PACK_NAMES = "0123456789ABCDEF"

#: Sector of each archive pack in the pinned retail rip, recorded in receipts
#: so a build can be traced back to the rebuild its audits came from. NEVER
#: use these to address an image: resolve through pack_extent() instead.
RETAIL_PACK_SECTORS: dict[str, int] = {
    "0": 796_479, "1": 649_995, "2": 891_064, "3": 495_938,
    "4": 1_042_066, "5": 345_561, "6": 1_350_843, "7": 1_194_985,
    "8": 1_574_589, "9": 35_531, "A": 2_403_082, "B": 2_179_328,
    "C": 2_554_593, "D": 2_028_383, "E": 2_708_466, "F": 2_855_836,
}


def pack_path(pack: "int | str") -> str:
    """Directory path of an archive pack: ``vc_53450030/<hex digit>``.

    Accepts the pack's index (``0``..``15``), its hex name in either case
    (``"c"``/``"C"``), or an already-qualified ``vc_53450030/C``.
    """
    if isinstance(pack, bool) or not isinstance(pack, (int, str)):
        raise PatchError(f"archive pack must be an index or a name, not {pack!r}")
    if isinstance(pack, int):
        require(0 <= pack < len(PACK_NAMES), f"archive pack index {pack} is out of range")
        return f"{PACK_FOLDER}/{PACK_NAMES[pack]}"
    text = pack.strip().replace("\\", "/")
    if "/" in text:
        folder, _, name = text.rpartition("/")
        require(folder.casefold() == PACK_FOLDER.casefold(),
                f"{pack!r} is not a path under {PACK_FOLDER}/")
        text = name
    require(len(text) == 1 and text.upper() in PACK_NAMES,
            f"{pack!r} is not an archive pack name (expected one hex digit)")
    return f"{PACK_FOLDER}/{text.upper()}"


def file_extent(
    descriptor: int, image_size: int, path: str,
    *, entries: "dict[str, XdvdfsEntry] | None" = None,
) -> XdvdfsEntry:
    """The directory entry of one file in this image, or a clear failure.

    ``path`` is looked up case-insensitively (XDVDFS names are). The image's
    game partition is located and its directory parsed unless the caller
    already holds ``entries`` from :func:`parse_xdvdfs`. A missing file or a
    directory where a file was expected raises :class:`PatchError` naming the
    path -- there is deliberately no fallback to a remembered offset.
    """
    if entries is None:
        entries, _directory = parse_xdvdfs(descriptor, image_size)
    entry = entries.get(path.casefold())
    require(entry is not None,
            f"this disc image has no {path} in its XDVDFS directory")
    assert entry is not None
    require(not (entry.attributes & 0x10), f"{path} is a directory, not a file")
    require(entry.byte_offset + entry.size <= image_size,
            f"{path} extends past the end of the image")
    return entry


def pack_extent(
    descriptor: int, image_size: int, pack: "int | str",
    *, entries: "dict[str, XdvdfsEntry] | None" = None,
) -> tuple[int, int]:
    """``(absolute byte offset, size)`` of archive pack ``pack`` in THIS image.

    The offset already includes the game partition's base, so it can be
    handed straight to a positional read or write on ``descriptor``.
    """
    entry = file_extent(descriptor, image_size, pack_path(pack), entries=entries)
    return int(entry.byte_offset), int(entry.size)


def xbe_extent(
    descriptor: int, image_size: int,
    *, entries: "dict[str, XdvdfsEntry] | None" = None,
) -> tuple[int, int]:
    """``(absolute byte offset, size)`` of ``default.xbe`` in THIS image."""
    entry = file_extent(descriptor, image_size, "default.xbe", entries=entries)
    return int(entry.byte_offset), int(entry.size)


def copy_fd_exact(source: int, output: int, size: int) -> str:
    """Copy the complete source using copy_file_range, with a safe fallback."""
    position = 0
    # copy_file_range is Linux-only; Windows and macOS do not have it at all.
    # Its absence is an AttributeError, not one of the OSError errnos handled
    # below, so the method has to be chosen *before* the loop -- caught inside
    # it, the documented fallback would never run and the copy would abort.
    accelerated = getattr(os, "copy_file_range", None)
    method = "copy_file_range" if accelerated is not None else "pread_pwrite"
    while accelerated is not None and position < size:
        request = min(COPY_CHUNK, size - position)
        try:
            copied = accelerated(source, output, request, position, position)
        except OSError as exc:
            if exc.errno not in {errno.EXDEV, errno.EINVAL, errno.ENOSYS,
                                 errno.EOPNOTSUPP}:
                raise
            method = "pread_pwrite"
            break
        require(copied > 0, "short copy_file_range result")
        position += copied

    while position < size:
        chunk = pread(source, min(COPY_CHUNK, size - position), position)
        require(chunk, "short source read while copying XISO")
        written = 0
        while written < len(chunk):
            amount = pwrite(output, chunk[written:], position + written)
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
        source_bytes = pread(source, request, position)
        output_bytes = pread(output, request, position)
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
        written = pwrite(owned.descriptor, payload[offset:], offset)
        require(written > 0, "short manifest write")
        offset += written
    os.ftruncate(owned.descriptor, len(payload))
    os.fsync(owned.descriptor)
    require(read_exact(owned.descriptor, 0, len(payload)) == payload,
            "manifest readback mismatch")
    require(owned_path_matches(owned), "manifest pathname changed during write")


def run(source_path: Path, output_path: Path, manifest_path: Path,
        colors: bytes = MAGENTA_PAIR) -> dict[str, object]:
    require(isinstance(colors, (bytes, bytearray)) and len(colors) == 8,
            "replacement colour pair must be exactly eight bytes")
    colors = bytes(colors)
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
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) |
        getattr(os, "O_BINARY", 0),
    )
    output_owned: OwnedFile | None = None
    manifest_owned: OwnedFile | None = None
    success = False
    try:
        source_info = os.fstat(source_fd)
        require(stat.S_ISREG(source_info.st_mode), "source descriptor is not regular")
        # Identity is per-extent, never the whole container. Image size, sector
        # numbers and absolute offsets describe how a disc was dumped, not which
        # game it is; extract-xiso relocates every file. The exact per-extent
        # size + SHA-256 checks below are the real identity, and gating on the
        # container refused legal dumps before they could run.
        source_size = source_info.st_size
        source_identity = fd_identity(source_fd)
        require(path_identity(source) == source_identity, "source pathname changed")
        source_sha_before = sha256_fd(source_fd)
        entries, directory = parse_xdvdfs(source_fd, source_size)

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
            require(entry.size == target.expected_size, f"target size mismatch: {target.path}")
            require(sha256_fd(source_fd, entry.byte_offset, entry.size) == target.expected_sha256,
                    f"target SHA-256 mismatch: {target.path}")
            absolute = entry.byte_offset + target.pack_offset
            require(target.pack_offset + len(target.expected_bytes) <= entry.size,
                    f"patch outside target extent: {target.path}")
            require(read_exact(source_fd, absolute, 8) == target.expected_bytes,
                    f"retail color words mismatch: {target.path}")
            patch_offsets.append(absolute)
            changed_relative = [
                index for index, (before, after) in
                enumerate(zip(target.expected_bytes, colors)) if before != after
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
                "after_hex": colors.hex(),
                "changed_relative_bytes": changed_relative,
                "source_file_sha256": target.expected_sha256,
            })

        require(len(patch_offsets) == len(set(patch_offsets)) == 2,
                "target patch windows overlap or are missing")
        # The original proof wrote magenta over both words and happened to
        # differ in exactly ten bytes. That count is a property of *that*
        # colour, not of the writer, so pinning it made every other colour
        # impossible. What has to hold is that nothing outside the two eight-
        # byte colour words can change, which is what the offsets are checked
        # against here and independently re-verified against the built image.
        require(allowed_changed_offsets, "replacement is identical to retail")
        window = {
            offset + index for offset in patch_offsets for index in range(8)
        }
        require(allowed_changed_offsets <= window,
                "replacement would change a byte outside the two colour words")

        output_owned = reserve_file(output)
        require(fd_identity(output_owned.descriptor) != source_identity,
                "output unexpectedly aliases source inode")
        copy_method = copy_fd_exact(source_fd, output_owned.descriptor, source_info.st_size)
        require(owned_path_matches(output_owned), "output pathname changed during copy")
        for absolute in patch_offsets:
            require(pwrite(output_owned.descriptor, colors, absolute) == 8,
                    f"short patch write at 0x{absolute:x}")
            require(read_exact(output_owned.descriptor, absolute, 8) == colors,
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
    parser.add_argument(
        "--facemask", default=None,
        help="facemask/faceshield colour as AARRGGBB hex, e.g. FF1A1A1A",
    )
    parser.add_argument(
        "--turtleneck", default=None,
        help="HI_turtleneck colour as AARRGGBB hex; defaults to --facemask",
    )
    args = parser.parse_args()
    if args.facemask is None and args.turtleneck is None:
        colors = MAGENTA_PAIR
    else:
        facemask_text = args.facemask or args.turtleneck
        turtleneck_text = args.turtleneck or args.facemask
        try:
            colors = pack_colors(int(facemask_text, 16), int(turtleneck_text, 16))
        except ValueError as exc:
            print(f"ERROR: colours must be AARRGGBB hex: {exc}", file=sys.stderr)
            return 1
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest, colors)
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
