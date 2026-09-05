#!/usr/bin/env python3
"""Replace files inside a PS2 ISO9660 disc image, inside their existing extents.

A PS2 disc is a plain ISO9660 volume: 2048-byte logical blocks, a Primary
Volume Descriptor at block 16, and a directory tree whose records each carry an
extent LBA and a declared data length.  Replacing a file therefore needs three
things and nothing else::

    1. the new bytes written at   lba * sector_size + data_offset
    2. the rest of the old extent zero-filled, so no stale tail survives
    3. the record's 8-byte both-endian data length updated in place

This module does exactly that and refuses everything else.  **Allocation is
fixed**: a replacement must fit the extent the file already owns.  Nothing
moves, nothing is renumbered, no sector is reallocated, the path tables stay
valid because no directory changed size, and the image keeps its exact byte
length -- trailing slack included (the Madden 12 Deluxe rebuild carries 18,432
bytes past the declared volume; truncating that would corrupt a community
image that is otherwise perfectly good).

Because the change is bounded, it is also *provable*: every byte the writer
touches is declared in the returned report as a ``ByteRange``, and
``ps2_iso9660_verify.py`` re-derives from the two files alone that nothing
outside those ranges moved.  A report is a claim; the verifier is the evidence.

Deliberately **not** relaxed, and each refusal says so:

* **Growing a file.**  There is no relocation, no free-space search, no
  path-table rewrite, no image rebuild.  ``len(new) <= entry.length`` or the
  call fails.
* **Raw-CD (2352-byte) images.**  Their 2048-byte payload is interleaved with
  sync/header/EDC/ECC, so one linear write would spill into a sector's error
  correction and a correct write would have to recompute EDC/ECC per sector.
  Reading such an image is fine; writing one is out of scope for v1.
* **Joliet / supplementary volume descriptors.**  A second directory tree
  carries a second copy of every length field.  Patching one and not the other
  leaves a reader that follows the other tree seeing a stale tail, so an image
  with an SVD is refused rather than half-patched.
* **Multi-extent, interleaved, and extended-attribute records.**  Their data is
  not the single contiguous run this writer assumes, so they are refused by
  inspecting the record's own flag bytes -- not assumed absent.
* **Aliased extents.**  If two directory records point at the same bytes,
  rewriting "one" file silently rewrites another.  Refused.
* **Adding or deleting files**, Rock Ridge, UDF, and dual-layer break handling.

Usage::

    ps2_iso9660_writer.py --inspect <image.iso>
    ps2_iso9660_writer.py --source <in.iso> --destination <out.iso> \\
        --replace /DATA/FOO.BIN=new_foo.bin --report write-report.json
    ps2_iso9660_writer.py --source <in.iso> --dry-run \\
        --replace /DATA/FOO.BIN=new_foo.bin
    ps2_iso9660_writer.py --selftest
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

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ps2_iso9660  # noqa: E402  (repo-local reader; this module never writes it)


SCHEMA = "ps2_iso9660_write/v1"

# Logical geometry this writer is willing to touch.  Anything else is refused
# rather than approximated; see the module docstring.
SECTOR_USER_BYTES = 2048
SYSTEM_AREA_BLOCKS = 16          # blocks 0..15 are reserved; no file lives there
PVD_BLOCK = 16

# Directory-record field offsets (ECMA-119 9.1), all relative to the record.
REC_LENGTH = 0                   # u8: length of this record, 0 = end of sector
REC_EAR_LENGTH = 1               # u8: extended attribute record, in blocks
REC_EXTENT = 2                   # both-endian u32: extent LBA
REC_DATA_LENGTH = 10             # both-endian u32: declared data length
REC_FLAGS = 25                   # u8
REC_FILE_UNIT_SIZE = 26          # u8: nonzero only for interleaved files
REC_INTERLEAVE_GAP = 27          # u8: ditto
REC_VOLUME_SEQUENCE = 28         # both-endian u16
REC_IDENT_LENGTH = 32            # u8
REC_IDENT = 33
REC_MIN_LENGTH = 34
REC_MAX_LENGTH = 255             # the length field is a single byte

FLAG_DIRECTORY = 0x02
FLAG_ASSOCIATED = 0x04
FLAG_MULTI_EXTENT = 0x80

BOTH_ENDIAN_U32 = 8              # the data-length field: LE u32 then BE u32

CHUNK = 8 * 1024 * 1024
ZEROS = bytes(CHUNK)

# Guard rails against absurd inputs rather than against honest ones.
MAX_IMAGE_BYTES = 64 * 1024 * 1024 * 1024      # a dual-layer DVD is ~8.5 GB
MAX_REPLACEMENTS = 4096
MAX_VOLUME_DESCRIPTORS = 64


class IsoWriteError(ValueError):
    """A bounded replacement would have broken one of its own guarantees."""


def _require(condition: bool, message: str) -> None:
    """Fail closed with an actionable message; never a bare assert."""
    if not condition:
        raise IsoWriteError(message)


@dataclass(frozen=True)
class ByteRange:
    """One contiguous run of bytes the writer admits to having written.

    ``reason`` is the whole contract with the verifier: ``extent:<path>`` for a
    file's allocated extent (new content plus the zero-filled tail) and
    ``dirrec_length:<path>`` for the 8 both-endian bytes of that file's
    declared length.  A range the writer does not declare is, to the verifier,
    corruption.
    """

    start: int
    length: int
    reason: str

    @property
    def end(self) -> int:
        return self.start + self.length

    def overlaps(self, start: int, length: int) -> bool:
        return start < self.end and self.start < start + length

    def as_dict(self) -> dict:
        return {"start": self.start, "length": self.length, "reason": self.reason}


@dataclass(frozen=True)
class _Plan:
    """One fully validated replacement, resolved to absolute byte offsets."""

    path: str                  # the reader's canonical path, e.g. "/DATA/FOO.BIN"
    requested: str             # the key the caller used
    raw_name: str
    lba: int
    parent_lba: int
    record_offset: int
    record_offset_abs: int
    extent_offset: int
    previous_length: int       # the whole allocation we are allowed to write
    content: bytes
    content_source: str
    previous_sha256: str

    @property
    def new_length(self) -> int:
        return len(self.content)

    @property
    def zero_filled(self) -> int:
        return self.previous_length - self.new_length

    @property
    def length_field_offset(self) -> int:
        return self.record_offset_abs + REC_DATA_LENGTH

    def ranges(self) -> list[ByteRange]:
        return [
            ByteRange(self.extent_offset, self.previous_length, f"extent:{self.path}"),
            ByteRange(
                self.length_field_offset, BOTH_ENDIAN_U32, f"dirrec_length:{self.path}"
            ),
        ]


# --------------------------------------------------------------------------
# Positional I/O.  os.pwrite/os.pread are absent on Windows, where these tools
# are also run, so every access goes through a fallback that restores the file
# pointer -- the same shape tools/nfl_team_identity_xiso_verify.py uses.
# --------------------------------------------------------------------------

def _pread_exact(descriptor: int, offset: int, size: int) -> bytes:
    """Read exactly *size* bytes at *offset*, or fail loudly."""
    if size == 0:
        return b""
    out = bytearray()
    while len(out) < size:
        positional = getattr(os, "pread", None)
        if positional is not None:
            block = positional(descriptor, size - len(out), offset + len(out))
        else:
            saved = os.lseek(descriptor, 0, os.SEEK_CUR)
            try:
                os.lseek(descriptor, offset + len(out), os.SEEK_SET)
                block = os.read(descriptor, size - len(out))
            finally:
                os.lseek(descriptor, saved, os.SEEK_SET)
        _require(bool(block), f"short read at 0x{offset + len(out):x}")
        out.extend(block)
    return bytes(out)


def _pwrite_exact(descriptor: int, offset: int, data: bytes) -> None:
    """Write every byte of *data* at *offset*, or fail loudly."""
    view = memoryview(data)
    written = 0
    while written < len(view):
        positional = getattr(os, "pwrite", None)
        if positional is not None:
            count = positional(descriptor, view[written:], offset + written)
        else:
            saved = os.lseek(descriptor, 0, os.SEEK_CUR)
            try:
                os.lseek(descriptor, offset + written, os.SEEK_SET)
                count = os.write(descriptor, view[written:])
            finally:
                os.lseek(descriptor, saved, os.SEEK_SET)
        _require(count > 0, f"short write at 0x{offset + written:x}")
        written += count


def _write_exact(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        _require(count > 0, "short write while copying the image")
        written += count


# --------------------------------------------------------------------------
# Output reservation.  O_EXCL makes "the destination must not already exist"
# atomic instead of a check with a race behind it, and it is also what stops a
# destination from ever aliasing the source: the source exists, so the create
# fails.  Mirrors _reserve_new/_commit_reserved in tools/nfl2k5_ps2_save.py.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class _Reservation:
    descriptor: int
    identity: tuple


def _path_is_owned_inode(path: Path, identity: tuple) -> bool:
    try:
        metadata = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and (
        metadata.st_dev,
        metadata.st_ino,
    ) == identity


def _reserve_new(path: Path) -> _Reservation:
    """Atomically create the destination and remember the inode we own."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o644,
        )
    except FileExistsError as exc:
        raise IsoWriteError(
            f"Refusing to overwrite an existing file: {path}. "
            "Choose a destination that does not exist yet -- this writer never "
            "edits in place, so the destination is always a fresh file."
        ) from exc
    metadata = os.fstat(descriptor)
    return _Reservation(descriptor, (metadata.st_dev, metadata.st_ino))


def _unlink_owned_path(path: Path, identity: tuple) -> bool:
    if not _path_is_owned_inode(path, identity):
        return False
    try:
        os.unlink(path)
    except OSError:
        return False
    return True


def _abort_reserved(path: Path, reservation: _Reservation) -> None:
    """Discard a failed write, removing only the inode this call created.

    The unlink is attempted before the close (POSIX keeps the inode alive
    through the open descriptor, so there is no window in which the name could
    be swapped) and again after it (Windows refuses to unlink a file that a
    descriptor still holds open, which is how partial outputs used to survive).
    The identity check guards both attempts, so neither can remove a file this
    reservation does not own.
    """
    removed = _unlink_owned_path(path, reservation.identity)
    try:
        os.close(reservation.descriptor)
    except OSError:
        pass
    if not removed:
        _unlink_owned_path(path, reservation.identity)


# --------------------------------------------------------------------------
# Admission checks
# --------------------------------------------------------------------------

def _check_source(source: Path) -> int:
    """Refuse anything that is not a plain, sane, readable image file."""
    _require(
        not source.is_symlink(),
        f"Refusing to read through a symlink: {source}. Pass the real image path.",
    )
    _require(source.exists(), f"No such image: {source}")
    metadata = os.stat(source, follow_symlinks=False)
    _require(stat.S_ISREG(metadata.st_mode), f"{source} is not a regular file")
    size = metadata.st_size
    _require(
        size >= (PVD_BLOCK + 1) * SECTOR_USER_BYTES,
        f"{source} is {size} bytes, too small to hold an ISO9660 volume "
        f"descriptor at block {PVD_BLOCK}",
    )
    _require(
        size <= MAX_IMAGE_BYTES,
        f"{source} is {size} bytes, past this tool's {MAX_IMAGE_BYTES}-byte "
        "sanity cap; that is not a PS2 disc image",
    )
    return size


def _check_destination(destination: Path, source: Path) -> None:
    _require(
        not destination.is_symlink() and not os.path.lexists(destination),
        f"Refusing to write to an existing path: {destination}. "
        "The destination must not exist (a symlink counts as existing).",
    )
    try:
        same = source.resolve() == destination.resolve()
    except OSError:
        same = False
    _require(
        not same,
        f"Refusing to write the destination onto the source: {source}. "
        "The source image is never modified.",
    )


def _volume_descriptor_types(descriptor: int, size: int) -> list:
    """Independently list the volume descriptors, to catch a second tree.

    Read straight from the bytes rather than from the reader: the whole reason
    to look is to find a directory tree the reader may not have parsed.
    """
    types = []
    for index in range(MAX_VOLUME_DESCRIPTORS):
        offset = (PVD_BLOCK + index) * SECTOR_USER_BYTES
        if offset + SECTOR_USER_BYTES > size:
            break
        head = _pread_exact(descriptor, offset, 7)
        if head[1:6] != b"CD001":
            break
        kind = head[0]
        types.append(kind)
        if kind == 255:  # volume descriptor set terminator
            break
    return types


def _check_writable_geometry(image, source: Path, size: int) -> None:
    """Refuse every image whose geometry this writer cannot address exactly."""
    _require(
        image.sector_size == SECTOR_USER_BYTES and image.data_offset == 0,
        f"{source}: {image.sector_size}-byte sectors with a {image.data_offset}-byte "
        "payload offset is a raw-CD image. Its 2048-byte user data is interleaved "
        "with sync/header/EDC/ECC, so a linear write would land in a sector's error "
        "correction and a correct write would have to recompute EDC/ECC per sector. "
        "Writing raw-CD images is out of scope for v1; reading them is not.",
    )
    _require(
        image.block_size == SECTOR_USER_BYTES,
        f"{source}: the volume descriptor declares {image.block_size}-byte logical "
        f"blocks. This writer only addresses {SECTOR_USER_BYTES}-byte blocks, which "
        "is what every known PS2 image uses; refusing rather than guessing at the "
        "LBA arithmetic.",
    )
    _require(
        image.file_size == size,
        f"{source}: the reader reports {image.file_size} bytes but the file is "
        f"{size} bytes. Refusing to write against a disagreement about the image.",
    )
    declared = image.volume_blocks * image.sector_size
    _require(
        declared <= size,
        f"{source}: the volume declares {image.volume_blocks} blocks "
        f"({declared} bytes) but the file is only {size} bytes. The image is "
        "truncated; refusing to write into extents that may not exist.",
    )
    _require(
        image.slack_bytes == size - declared,
        f"{source}: the reader reports {image.slack_bytes} slack bytes but the file "
        f"carries {size - declared}. Refusing to write against a disagreement about "
        "the image.",
    )


def _check_no_second_tree(descriptor: int, source: Path, size: int) -> list:
    types = _volume_descriptor_types(descriptor, size)
    _require(
        bool(types) and types[0] == 1,
        f"{source}: block {PVD_BLOCK} does not begin a Primary Volume Descriptor "
        "(type 1). This is not an ISO9660 image this writer can address.",
    )
    supplementary = [kind for kind in types if kind == 2]
    _require(
        not supplementary,
        f"{source}: the image carries a supplementary volume descriptor "
        "(Joliet or similar), so every file's length is recorded twice -- once per "
        "directory tree. This writer patches one tree only, which would leave the "
        "other declaring a stale length. Joliet is out of scope for v1; refusing "
        "rather than half-patching.",
    )
    return types


# --------------------------------------------------------------------------
# Planning: everything is validated before the destination is created, so a
# refused replacement never leaves a file behind.
# --------------------------------------------------------------------------

def _normalize_for_compare(name: str) -> tuple:
    """Split an ISO identifier into (upper base, version or None).

    ISO9660 stores ``FOO.BIN;1``.  Comparing the base name case-insensitively
    and the version only when both sides carry one keeps the identity check
    strict about *which* file it is while tolerating a reader that presents the
    version suffix differently.
    """
    text = name.strip()
    base, sep, version = text.rpartition(";")
    if sep and version.isdigit():
        return base.upper(), int(version)
    return text.upper(), None


def _names_agree(stored: str, reported: str) -> bool:
    left, left_version = _normalize_for_compare(stored)
    right, right_version = _normalize_for_compare(reported)
    if left != right:
        return False
    if left_version is None or right_version is None:
        return True
    return left_version == right_version


def _read_record(descriptor: int, size: int, offset: int) -> bytes:
    """Read one directory record, bounded by its own length byte."""
    _require(
        0 <= offset and offset + REC_MIN_LENGTH <= size,
        f"directory record at 0x{offset:x} is outside the image",
    )
    head = _pread_exact(descriptor, offset, min(REC_MAX_LENGTH, size - offset))
    record_length = head[REC_LENGTH]
    _require(
        REC_MIN_LENGTH <= record_length <= len(head),
        f"directory record at 0x{offset:x} declares length {record_length}, which "
        f"is not a usable ISO9660 record; refusing to patch bytes we cannot identify",
    )
    return head[:record_length]


def _both_endian_u32(record: bytes, offset: int, what: str) -> int:
    little = struct.unpack_from("<I", record, offset)[0]
    big = struct.unpack_from(">I", record, offset + 4)[0]
    _require(
        little == big,
        f"{what}: the both-endian halves disagree (LE {little} vs BE {big}). "
        "That is corruption, not a convention difference; refusing to write.",
    )
    return little


def _validate_record(record: bytes, entry, offset: int) -> None:
    """Prove the bytes at *offset* really are this entry's directory record.

    This is the checkpoint that makes the length patch safe.  If the reader ever
    hands back the wrong ``parent_lba``/``record_offset``, the LBA and length
    stored in the record will not match the entry and the write is refused --
    instead of an 8-byte both-endian value being stamped over somebody else's
    file.
    """
    where = f"{entry.path}: the record at 0x{offset:x}"
    _require(
        record[REC_EAR_LENGTH] == 0,
        f"{where} carries an extended attribute record, so its data does not start "
        "at the extent LBA. Extended attribute records are out of scope for v1.",
    )
    stored_lba = _both_endian_u32(record, REC_EXTENT, f"{where} extent LBA")
    _require(
        stored_lba == entry.lba,
        f"{where} points at LBA {stored_lba}, but the reader reports LBA "
        f"{entry.lba} for {entry.path}. Refusing to patch a record we cannot "
        "confirm is the right one.",
    )
    stored_length = _both_endian_u32(record, REC_DATA_LENGTH, f"{where} data length")
    _require(
        stored_length == entry.length,
        f"{where} declares {stored_length} bytes, but the reader reports "
        f"{entry.length} for {entry.path}. Refusing to patch a record we cannot "
        "confirm is the right one.",
    )
    flags = record[REC_FLAGS]
    _require(
        not flags & FLAG_DIRECTORY,
        f"{where} has the directory flag set. Directories are not replaceable.",
    )
    _require(
        not flags & FLAG_MULTI_EXTENT,
        f"{where} is one section of a multi-extent file (flag 0x80). Its bytes "
        "continue in another record with its own length field, so patching this "
        "one alone would leave the file inconsistent. Multi-extent files are out "
        "of scope for v1.",
    )
    _require(
        not flags & FLAG_ASSOCIATED,
        f"{where} is an associated file (flag 0x04), which shares its name with "
        "another record. Refusing to write one of an ambiguous pair.",
    )
    _require(
        record[REC_FILE_UNIT_SIZE] == 0 and record[REC_INTERLEAVE_GAP] == 0,
        f"{where} describes an interleaved file (file unit size "
        f"{record[REC_FILE_UNIT_SIZE]}, gap {record[REC_INTERLEAVE_GAP]}), so its "
        "data is not one contiguous run. Interleaved files are out of scope for v1.",
    )
    little = struct.unpack_from("<H", record, REC_VOLUME_SEQUENCE)[0]
    big = struct.unpack_from(">H", record, REC_VOLUME_SEQUENCE + 2)[0]
    _require(
        little == big,
        f"{where} has a both-endian volume sequence number whose halves disagree "
        f"(LE {little} vs BE {big}). That is corruption; refusing to write.",
    )
    ident_length = record[REC_IDENT_LENGTH]
    _require(
        REC_IDENT + ident_length <= len(record),
        f"{where} declares a {ident_length}-byte identifier that does not fit the "
        "record",
    )
    ident = record[REC_IDENT : REC_IDENT + ident_length]
    _require(
        ident not in (b"\x00", b"\x01"),
        f"{where} is the '.' or '..' self/parent record, not a file record.",
    )
    _require(
        _names_agree(ident.decode("latin1"), entry.raw_name),
        f"{where} is named {ident.decode('latin1')!r}, but the reader reports "
        f"{entry.raw_name!r}. Refusing to patch a record whose identity the two "
        "parses do not agree on.",
    )


def _resolve_content(key: str, value, limit: int) -> tuple:
    """Turn a replacement value into bytes, refusing anything ambiguous."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        _require(
            len(data) <= limit,
            f"{key}: the replacement is {len(data)} bytes but the file's extent "
            f"holds {limit}. Fixed-allocation writes never relocate a file; growing "
            "one needs an image rebuild, which is out of scope for v1.",
        )
        return data, "<inline bytes>"
    if isinstance(value, str):
        raise IsoWriteError(
            f"{key}: a str replacement is ambiguous -- it could be content or a "
            "filename. Pass bytes for literal content, or pathlib.Path for a file."
        )
    if isinstance(value, os.PathLike):
        path = Path(value)
        _require(
            not path.is_symlink(),
            f"{key}: refusing to read replacement content through a symlink "
            f"({path}). Pass the real file path.",
        )
        _require(path.exists(), f"{key}: no such replacement file: {path}")
        metadata = os.stat(path, follow_symlinks=False)
        _require(
            stat.S_ISREG(metadata.st_mode),
            f"{key}: replacement {path} is not a regular file",
        )
        _require(
            metadata.st_size <= limit,
            f"{key}: {path} is {metadata.st_size} bytes but the file's extent holds "
            f"{limit}. Fixed-allocation writes never relocate a file; growing one "
            "needs an image rebuild, which is out of scope for v1.",
        )
        return path.read_bytes(), str(path)
    raise IsoWriteError(
        f"{key}: replacement must be bytes or a pathlib.Path, not "
        f"{type(value).__name__}"
    )


def _hash_extent(descriptor: int, offset: int, length: int) -> str:
    digest = hashlib.sha256()
    remaining = length
    position = offset
    while remaining:
        take = min(CHUNK, remaining)
        digest.update(_pread_exact(descriptor, position, take))
        position += take
        remaining -= take
    return digest.hexdigest()


def _plan_one(descriptor: int, image, size: int, key: str, value) -> _Plan:
    entry = ps2_iso9660.find(image, key)
    _require(
        entry is not None,
        f"{key}: no such file in the image. Paths are '/'-separated and matched "
        "case-insensitively; the ';1' version suffix is optional.",
    )
    _require(
        not entry.is_dir,
        f"{key} resolves to the directory {entry.path}. Directories have no "
        "replaceable content; name a file.",
    )
    _require(
        entry.length > 0,
        f"{entry.path} declares a zero-length extent, so there is no allocation to "
        "write into. Creating one would mean relocating the file, which is out of "
        "scope for v1.",
    )
    _require(
        entry.lba >= SYSTEM_AREA_BLOCKS,
        f"{entry.path} claims LBA {entry.lba}, inside the reserved system area "
        f"(blocks 0..{SYSTEM_AREA_BLOCKS - 1}, which hold the volume descriptors). "
        "Writing there would destroy the volume; refusing.",
    )
    extent_offset = entry.lba * image.sector_size + image.data_offset
    extent_end = extent_offset + entry.length
    volume_bytes = image.volume_blocks * image.sector_size
    _require(
        extent_end <= volume_bytes,
        f"{entry.path}: its extent ends at byte {extent_end}, past the declared "
        f"volume ({image.volume_blocks} blocks = {volume_bytes} bytes). The record "
        "is inconsistent with the volume; refusing to write outside it.",
    )
    _require(
        extent_end <= size,
        f"{entry.path}: its extent ends at byte {extent_end}, past the end of the "
        f"{size}-byte image file. Refusing to write past the image.",
    )
    _require(
        entry.parent_lba >= PVD_BLOCK,
        f"{entry.path}: its record is claimed to live in LBA {entry.parent_lba}, "
        "which is not a plausible directory extent.",
    )
    record_offset_abs = (
        entry.parent_lba * image.sector_size + image.data_offset + entry.record_offset
    )
    _require(
        record_offset_abs + REC_MIN_LENGTH <= min(size, volume_bytes),
        f"{entry.path}: its directory record at byte {record_offset_abs} is outside "
        "the volume",
    )
    record = _read_record(descriptor, size, record_offset_abs)
    _require(
        (entry.record_offset % image.block_size) + len(record) <= image.block_size,
        f"{entry.path}: its directory record straddles a logical-block boundary, "
        "which ISO9660 forbids. Refusing to patch a record we cannot trust.",
    )
    _validate_record(record, entry, record_offset_abs)

    content, content_source = _resolve_content(key, value, entry.length)
    return _Plan(
        path=entry.path,
        requested=key,
        raw_name=entry.raw_name,
        lba=entry.lba,
        parent_lba=entry.parent_lba,
        record_offset=entry.record_offset,
        record_offset_abs=record_offset_abs,
        extent_offset=extent_offset,
        previous_length=entry.length,
        content=content,
        content_source=content_source,
        previous_sha256=_hash_extent(descriptor, extent_offset, entry.length),
    )


def _check_aliasing(image, plans: list) -> int:
    """Refuse a write whose extent is shared with anything else in the tree.

    ISO9660 does not forbid two directory records pointing at the same LBA, and
    de-duplicating mastering tools do exactly that.  Replacing "one" of a pair
    silently rewrites the other, and no byte-range check can see the difference
    -- both files live in the declared range.  So the aliasing is refused here,
    where it is still visible.
    """
    entries = list(ps2_iso9660.iter_entries(image))
    _require(
        len(entries) > 0,
        "the image's directory tree is empty; refusing to write into it",
    )
    directories = [(image.root_lba, image.root_length, "/")]
    files = []
    for entry in entries:
        if entry.is_dir:
            directories.append((entry.lba, entry.length, entry.path))
        elif entry.length:
            files.append((entry.lba, entry.length, entry.path))

    def span(lba: int, length: int) -> tuple:
        start = lba * image.sector_size + image.data_offset
        return start, start + length

    for plan in plans:
        plan_start, plan_end = plan.extent_offset, plan.extent_offset + plan.previous_length
        for lba, length, path in files:
            if path == plan.path:
                continue
            start, end = span(lba, length)
            _require(
                not (start < plan_end and plan_start < end),
                f"{plan.path} shares disc bytes with {path} (both cover "
                f"0x{max(start, plan_start):x}). Replacing one would silently "
                "rewrite the other, so this image needs a rebuild rather than a "
                "bounded patch.",
            )
        for lba, length, path in directories:
            start, end = span(lba, length)
            _require(
                not (start < plan_end and plan_start < end),
                f"{plan.path}'s extent overlaps the directory extent of {path}. "
                "That is a malformed image; refusing to write.",
            )
    for index, first in enumerate(plans):
        for second in plans[index + 1 :]:
            _require(
                first.path != second.path,
                f"{first.path} was named twice in one call "
                f"({first.requested!r} and {second.requested!r}); "
                "one file, one replacement.",
            )
            first_end = first.extent_offset + first.previous_length
            second_end = second.extent_offset + second.previous_length
            _require(
                not (
                    second.extent_offset < first_end
                    and first.extent_offset < second_end
                ),
                f"{first.path} and {second.path} claim overlapping extents; "
                "refusing to write both.",
            )
            _require(
                first.record_offset_abs != second.record_offset_abs,
                f"{first.path} and {second.path} resolve to the same directory "
                "record; one file, one replacement.",
            )
    return len(entries)


# --------------------------------------------------------------------------
# The write itself
# --------------------------------------------------------------------------

def _copy_stream(source: Path, descriptor: int) -> int:
    total = 0
    with open(source, "rb", buffering=0) as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            _write_exact(descriptor, block)
            total += len(block)
    os.fsync(descriptor)
    return total


def _apply(descriptor: int, plan: _Plan) -> None:
    """Write the content, zero the rest of the extent, patch the length."""
    _pwrite_exact(descriptor, plan.extent_offset, plan.content)
    position = plan.extent_offset + plan.new_length
    remaining = plan.zero_filled
    while remaining:
        take = min(CHUNK, remaining)
        _pwrite_exact(descriptor, position, ZEROS[:take])
        position += take
        remaining -= take
    _pwrite_exact(
        descriptor,
        plan.length_field_offset,
        struct.pack("<I", plan.new_length) + struct.pack(">I", plan.new_length),
    )


def _read_back(descriptor: int, plan: _Plan) -> None:
    """Re-read every declared byte and prove it says what we meant it to say.

    This is the writer checking its own I/O, not a substitute for the
    independent verifier: a short write or a wrong offset should fail here,
    before a caller is handed a report claiming success.
    """
    position = plan.extent_offset
    for start in range(0, plan.new_length, CHUNK):
        expected = plan.content[start : start + CHUNK]
        actual = _pread_exact(descriptor, position + start, len(expected))
        if actual != expected:
            bad = next(
                index for index, pair in enumerate(zip(actual, expected))
                if pair[0] != pair[1]
            )
            raise IsoWriteError(
                f"{plan.path}: read-back mismatch at byte "
                f"0x{position + start + bad:x}; the write did not land"
            )
    position = plan.extent_offset + plan.new_length
    remaining = plan.zero_filled
    while remaining:
        take = min(CHUNK, remaining)
        actual = _pread_exact(descriptor, position, take)
        if actual != ZEROS[:take]:
            bad = next(index for index, value in enumerate(actual) if value)
            raise IsoWriteError(
                f"{plan.path}: the zero-filled tail is not zero at byte "
                f"0x{position + bad:x}; a stale tail would survive"
            )
        position += take
        remaining -= take
    field = _pread_exact(descriptor, plan.length_field_offset, BOTH_ENDIAN_U32)
    little = struct.unpack_from("<I", field, 0)[0]
    big = struct.unpack_from(">I", field, 4)[0]
    if not (little == big == plan.new_length):
        raise IsoWriteError(
            f"{plan.path}: the patched length field reads LE {little} / BE {big}, "
            f"expected {plan.new_length} in both halves"
        )


def replace_files(source, destination, replacements) -> dict:
    """Copy *source* to *destination*, replacing files inside their extents.

    ``replacements`` maps an ISO path (``/DATA/FOO.BIN``, case-insensitive,
    ``;1`` optional) to either ``bytes`` or a ``pathlib.Path`` holding the new
    content.  Every replacement must fit the extent its file already owns.

    The source is opened read-only and never written.  The destination must not
    exist; it is created with ``O_EXCL``, filled with an exact copy of the
    source -- trailing slack included, so the two files are the same size -- and
    only then patched.  Any refusal happens before the destination is created,
    and any failure after that removes it, so a failed call never leaves a
    half-written image behind.

    Returns a report whose ``declared_ranges`` list every byte written:
    one ``extent:<path>`` range per replaced file (its whole old allocation,
    new content plus the zero-filled tail) and one ``dirrec_length:<path>``
    range per patched record (the 8 both-endian length bytes).  Hand that
    report, with both files, to ``ps2_iso9660_verify.verify_replacement``.
    """
    source = Path(source)
    destination = Path(destination)
    _require(
        hasattr(replacements, "items"),
        "replacements must be a mapping of iso path -> bytes | Path",
    )
    items = list(replacements.items())
    _require(
        items,
        "no replacements were given. A bounded write with nothing to write is a "
        "plain copy, and the report it would produce declares nothing for the "
        "verifier to check; use shutil.copyfile if a copy is what you want.",
    )
    _require(
        len(items) <= MAX_REPLACEMENTS,
        f"{len(items)} replacements in one call is past the {MAX_REPLACEMENTS} "
        "sanity cap",
    )

    size = _check_source(source)
    _check_destination(destination, source)
    image = ps2_iso9660.open_image(source)
    _check_writable_geometry(image, source, size)

    read_only = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        descriptors = _check_no_second_tree(read_only, source, size)
        plans = [
            _plan_one(read_only, image, size, str(key), value)
            for key, value in sorted(items, key=lambda pair: str(pair[0]))
        ]
        entry_count = _check_aliasing(image, plans)
    finally:
        os.close(read_only)

    plans.sort(key=lambda plan: plan.extent_offset)

    reservation = _reserve_new(destination)
    try:
        copied = _copy_stream(source, reservation.descriptor)
        _require(
            copied == size,
            f"copied {copied} of {size} bytes from {source}; refusing a partial image",
        )
        for plan in plans:
            _apply(reservation.descriptor, plan)
        os.fsync(reservation.descriptor)
        for plan in plans:
            _read_back(reservation.descriptor, plan)
        written = os.fstat(reservation.descriptor).st_size
        _require(
            written == size,
            f"the destination is {written} bytes but the source is {size}; the "
            "image's trailing slack must survive byte-for-byte",
        )
    except BaseException:
        _abort_reserved(destination, reservation)
        raise
    else:
        os.close(reservation.descriptor)

    ranges = sorted(
        (rng for plan in plans for rng in plan.ranges()),
        key=lambda rng: (rng.start, rng.reason),
    )
    return {
        "schema": SCHEMA,
        "source": str(source),
        "destination": str(destination),
        "sector_size": image.sector_size,
        "data_offset": image.data_offset,
        "block_size": image.block_size,
        "volume_id": image.volume_id,
        "volume_blocks": image.volume_blocks,
        "root_lba": image.root_lba,
        "root_length": image.root_length,
        "file_size": size,
        "slack_bytes": image.slack_bytes,
        "entry_count": entry_count,
        "volume_descriptors": descriptors,
        "replacements": [
            {
                "path": plan.path,
                "requested": plan.requested,
                "raw_name": plan.raw_name,
                "lba": plan.lba,
                "parent_lba": plan.parent_lba,
                "record_offset": plan.record_offset,
                "record_offset_abs": plan.record_offset_abs,
                "extent_offset": plan.extent_offset,
                "length_field_offset": plan.length_field_offset,
                "allocated_bytes": plan.previous_length,
                "previous_length": plan.previous_length,
                "new_length": plan.new_length,
                "zero_filled_bytes": plan.zero_filled,
                "content_source": plan.content_source,
                "sha256": hashlib.sha256(plan.content).hexdigest(),
                "previous_sha256": plan.previous_sha256,
            }
            for plan in plans
        ],
        "declared_ranges": ranges,
        "bytes_declared": sum(rng.length for rng in ranges),
    }


def report_to_json(report: dict) -> dict:
    """A JSON-safe copy of a report, with every ByteRange flattened to a dict."""
    out = dict(report)
    out["declared_ranges"] = [
        rng.as_dict() if isinstance(rng, ByteRange) else dict(rng)
        for rng in report.get("declared_ranges", [])
    ]
    return out


def plan_report(source, replacements) -> dict:
    """Validate a replacement set without creating anything (a dry run)."""
    source = Path(source)
    size = _check_source(source)
    image = ps2_iso9660.open_image(source)
    _check_writable_geometry(image, source, size)
    read_only = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        descriptors = _check_no_second_tree(read_only, source, size)
        plans = [
            _plan_one(read_only, image, size, str(key), value)
            for key, value in sorted(replacements.items(), key=lambda p: str(p[0]))
        ]
        entry_count = _check_aliasing(image, plans)
    finally:
        os.close(read_only)
    plans.sort(key=lambda plan: plan.extent_offset)
    ranges = sorted(
        (rng for plan in plans for rng in plan.ranges()),
        key=lambda rng: (rng.start, rng.reason),
    )
    return {
        "schema": "ps2_iso9660_write_plan/v1",
        "source": str(source),
        "file_size": size,
        "slack_bytes": image.slack_bytes,
        "entry_count": entry_count,
        "volume_descriptors": descriptors,
        "replacements": [
            {
                "path": plan.path,
                "extent_offset": plan.extent_offset,
                "allocated_bytes": plan.previous_length,
                "new_length": plan.new_length,
                "zero_filled_bytes": plan.zero_filled,
                "length_field_offset": plan.length_field_offset,
            }
            for plan in plans
        ],
        "declared_ranges": ranges,
    }


def inspect(source) -> dict:
    """Summarise an image and say, per file, how much room a replacement has."""
    source = Path(source)
    size = _check_source(source)
    image = ps2_iso9660.open_image(source)
    entries = list(ps2_iso9660.iter_entries(image))
    writable = (
        image.sector_size == SECTOR_USER_BYTES
        and image.data_offset == 0
        and image.block_size == SECTOR_USER_BYTES
    )
    return {
        "schema": "ps2_iso9660_write_inspect/v1",
        "source": str(source),
        "sector_size": image.sector_size,
        "data_offset": image.data_offset,
        "block_size": image.block_size,
        "volume_id": image.volume_id,
        "volume_blocks": image.volume_blocks,
        "file_size": size,
        "slack_bytes": image.slack_bytes,
        "writable_geometry": writable,
        "entries": [
            {
                "path": entry.path,
                "lba": entry.lba,
                "length": entry.length,
                "is_dir": entry.is_dir,
                "extent_offset": entry.lba * image.sector_size + image.data_offset,
            }
            for entry in entries
        ],
    }


# --------------------------------------------------------------------------
# Self-test: a synthetic ISO9660 volume, no disc images required
# --------------------------------------------------------------------------

_SYNTHETIC_BOOT = b"BOOT2 = cdrom0:\\SLUS_217.70;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"


def _both_u32(value: int) -> bytes:
    return struct.pack("<I", value) + struct.pack(">I", value)


def _both_u16(value: int) -> bytes:
    return struct.pack("<H", value) + struct.pack(">H", value)


def _dirrec(ident: bytes, lba: int, length: int, is_dir: bool) -> bytes:
    body = bytearray()
    body += b"\x00\x00"                        # record length, EAR length
    body += _both_u32(lba)
    body += _both_u32(length)
    body += bytes((80, 1, 1, 0, 0, 0, 0))      # 1980-01-01 00:00:00 GMT
    body += bytes((FLAG_DIRECTORY if is_dir else 0,))
    body += b"\x00\x00"                        # file unit size, interleave gap
    body += _both_u16(1)                       # volume sequence number
    body += bytes((len(ident),)) + ident
    if len(body) % 2:
        body += b"\x00"
    body[0] = len(body)
    return bytes(body)


def _synthetic_image(path: Path, slack: int = 0) -> dict:
    """Write a small but structurally real ISO9660 image and describe it.

    Deliberately includes both path tables and a ``SYSTEM.CNF`` so the image
    looks like a PS2 disc to any reader, not just to this module.
    """
    block = SECTOR_USER_BYTES
    l_path_lba, m_path_lba = 18, 19
    root_lba, data_lba = 20, 21
    files = [
        ("SYSTEM.CNF;1", 22, _SYNTHETIC_BOOT, "/"),
        ("HELLO.TXT;1", 23, b"hello ps2\n", "/"),
        ("FOO.BIN;1", 24, bytes(range(256)) * 11 + b"tail", "/DATA"),  # 2 blocks
        ("BAR.BIN;1", 26, b"bar" * 100, "/DATA"),
    ]
    volume_blocks = 27

    root_records = [_dirrec(b"\x00", root_lba, block, True),
                    _dirrec(b"\x01", root_lba, block, True),
                    _dirrec(b"DATA", data_lba, block, True)]
    data_records = [_dirrec(b"\x00", data_lba, block, True),
                    _dirrec(b"\x01", root_lba, block, True)]
    for name, lba, content, parent in files:
        record = _dirrec(name.encode("ascii"), lba, len(content), False)
        (root_records if parent == "/" else data_records).append(record)

    def directory_extent(records) -> bytes:
        out = bytearray()
        for record in records:
            if len(out) % block + len(record) > block:
                out += bytes(block - len(out) % block)
            out += record
        assert len(out) <= block, "the synthetic directory must fit one block"
        return bytes(out).ljust(block, b"\x00")

    root_extent = directory_extent(root_records)
    data_extent = directory_extent(data_records)

    def path_table(little: bool) -> bytes:
        pack = "<I" if little else ">I"
        short = "<H" if little else ">H"
        out = bytearray()
        for ident, lba, parent in ((b"\x00", root_lba, 1), (b"DATA", data_lba, 1)):
            out += bytes((len(ident), 0))
            out += struct.pack(pack, lba)
            out += struct.pack(short, parent)
            out += ident
            if len(out) % 2:
                out += b"\x00"
        return bytes(out)

    l_table, m_table = path_table(True), path_table(False)

    pvd = bytearray(block)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[8:40] = b"PLAYSTATION".ljust(32, b" ")
    pvd[40:72] = b"SYNTHETIC_PS2".ljust(32, b" ")
    pvd[80:88] = _both_u32(volume_blocks)
    pvd[120:124] = _both_u16(1)
    pvd[124:128] = _both_u16(1)
    pvd[128:132] = _both_u16(block)
    pvd[132:140] = _both_u32(len(l_table))
    pvd[140:144] = struct.pack("<I", l_path_lba)
    pvd[148:152] = struct.pack(">I", m_path_lba)
    pvd[156:190] = _dirrec(b"\x00", root_lba, block, True)
    for start, end in ((190, 318), (318, 446), (446, 574), (574, 702)):
        pvd[start:end] = b" " * (end - start)
    for start in (702, 739, 776):
        pvd[start : start + 37] = b" " * 37
    for start in (813, 830, 847, 864):
        pvd[start : start + 17] = b"0" * 16 + b"\x00"
    pvd[881] = 1

    terminator = bytearray(block)
    terminator[0] = 255
    terminator[1:6] = b"CD001"
    terminator[6] = 1

    image = bytearray(volume_blocks * block)
    image[PVD_BLOCK * block : (PVD_BLOCK + 1) * block] = pvd
    image[17 * block : 18 * block] = terminator
    image[l_path_lba * block : l_path_lba * block + len(l_table)] = l_table
    image[m_path_lba * block : m_path_lba * block + len(m_table)] = m_table
    image[root_lba * block : (root_lba + 1) * block] = root_extent
    image[data_lba * block : (data_lba + 1) * block] = data_extent
    for name, lba, content, _parent in files:
        image[lba * block : lba * block + len(content)] = content
    image += b"\xa5" * slack

    path.write_bytes(bytes(image))
    return {
        "path": str(path),
        "volume_blocks": volume_blocks,
        "slack": slack,
        "files": {
            ("/" if parent == "/" else parent + "/") + name.split(";")[0]: content
            for name, _lba, content, parent in files
        },
    }


def selftest(tmp: Path | None = None) -> int:
    """Prove the writer accepts a bounded edit and refuses the unbounded ones."""
    import tempfile

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        room = Path(work)
        source = room / "synthetic.iso"
        built = _synthetic_image(source, slack=18_432)
        original = source.read_bytes()

        smaller = b"REPLACED"
        report = replace_files(
            source, room / "out.iso", {"/DATA/FOO.BIN": smaller}
        )
        destination = room / "out.iso"
        if source.read_bytes() != original:
            raise IsoWriteError("the source image was modified")
        if destination.stat().st_size != source.stat().st_size:
            raise IsoWriteError("the destination changed size; slack was not preserved")
        if destination.read_bytes()[-built["slack"] :] != b"\xa5" * built["slack"]:
            raise IsoWriteError("trailing slack was not preserved byte-for-byte")
        if len(report["declared_ranges"]) != 2:
            raise IsoWriteError(f"expected 2 declared ranges: {report['declared_ranges']}")
        reasons = sorted(rng.reason for rng in report["declared_ranges"])
        if reasons != ["dirrec_length:/DATA/FOO.BIN", "extent:/DATA/FOO.BIN"]:
            raise IsoWriteError(f"unexpected declared reasons: {reasons}")
        entry = report["replacements"][0]
        patched = destination.read_bytes()
        start = entry["extent_offset"]
        if patched[start : start + len(smaller)] != smaller:
            raise IsoWriteError("the replacement did not land at the extent")
        tail = patched[start + len(smaller) : start + entry["allocated_bytes"]]
        if tail.strip(b"\x00"):
            raise IsoWriteError("the extent tail was not zero-filled")
        field = patched[entry["length_field_offset"] : entry["length_field_offset"] + 8]
        if field != struct.pack("<I", len(smaller)) + struct.pack(">I", len(smaller)):
            raise IsoWriteError(f"the length field was not patched: {field!r}")

        # Every byte that differs must be inside a declared range.
        declared = report["declared_ranges"]
        for index, pair in enumerate(zip(original, patched)):
            if pair[0] != pair[1] and not any(
                rng.start <= index < rng.end for rng in declared
            ):
                raise IsoWriteError(f"undeclared change at 0x{index:x}")

        # Refusals.  Each must leave no destination behind.
        def refused(name: str, replacements, why: str) -> None:
            out = room / name
            try:
                replace_files(source, out, replacements)
            except IsoWriteError:
                pass
            else:  # pragma: no cover - guarded by the raise below
                raise AssertionError(f"{why} must be refused")
            if out.exists():
                raise IsoWriteError(f"{why}: a refused write left {out} behind")

        refused("grow.iso", {"/DATA/BAR.BIN": b"x" * 5000}, "an oversize replacement")
        refused("dir.iso", {"/DATA": b"x"}, "a directory target")
        refused("missing.iso", {"/NOPE.BIN": b"x"}, "an unknown path")
        refused("str.iso", {"/DATA/BAR.BIN": "not bytes"}, "a str replacement")

        try:
            replace_files(source, destination, {"/DATA/BAR.BIN": b"x"})
        except IsoWriteError:
            pass
        else:  # pragma: no cover
            raise AssertionError("an existing destination must be refused")

        # A same-size replacement leaves no tail and still declares both ranges.
        exact = b"Z" * built["files"]["/DATA/BAR.BIN"].__len__()
        exact_report = replace_files(source, room / "exact.iso", {"/DATA/BAR.BIN": exact})
        if exact_report["replacements"][0]["zero_filled_bytes"] != 0:
            raise IsoWriteError("a same-size replacement must zero-fill nothing")

        # Two files at once: four declared ranges, both extents patched.
        pair = replace_files(
            source,
            room / "pair.iso",
            {"/DATA/FOO.BIN": b"one", "/HELLO.TXT": b"two"},
        )
        if len(pair["declared_ranges"]) != 4:
            raise IsoWriteError("two replacements must declare four ranges")

    print(
        "PS2_ISO9660_WRITER_SELFTEST_PASS allocation=fixed slack=preserved "
        "ranges=extent+dirrec_length refuses=grow,dir,missing,str,dest-exists"
    )
    return 0


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", type=Path, help="the image to copy from; never written")
    parser.add_argument("--destination", type=Path, help="the image to create; must not exist")
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="ISOPATH=FILE",
        help="replace an ISO path with a local file, e.g. /DATA/FOO.BIN=new.bin",
    )
    parser.add_argument("--inspect", type=Path, help="summarise an image and its entries")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the replacements and print the plan without writing anything",
    )
    parser.add_argument("--report", type=Path, help="write the JSON report here")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="prove the writer against a synthetic image; no disc image needed",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.inspect:
        print(json.dumps(inspect(args.inspect), indent=2))
        return 0
    if not args.source:
        parser.error("--source is required unless --inspect or --selftest is given")

    replacements = {}
    for directive in args.replace:
        iso_path, sep, local = directive.partition("=")
        if not sep or not iso_path or not local:
            parser.error(f"malformed --replace {directive!r}; use ISOPATH=FILE")
        replacements[iso_path] = Path(local)

    if args.dry_run:
        print(json.dumps(report_to_json(plan_report(args.source, replacements)), indent=2))
        return 0
    if not args.destination:
        parser.error("--destination is required unless --dry-run is given")
    if not replacements:
        parser.error("give at least one --replace, or use --dry-run/--inspect")

    report = replace_files(args.source, args.destination, replacements)
    payload = report_to_json(report)
    if args.report:
        # Bytes, not write_text: the line ending has to be LF on every
        # platform because this report is hashed and size-checked, and
        # write_text's newline= argument is 3.10 and later only.
        args.report.write_bytes(json.dumps(payload, indent=2).encode("utf-8"))
    print(json.dumps(payload, indent=2))
    print(
        f"# now prove it: ps2_iso9660_verify.py --source {args.source} "
        f"--destination {args.destination} --report <this report>",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
