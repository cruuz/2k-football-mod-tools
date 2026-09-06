#!/usr/bin/env python3
"""Independently verify a bounded file replacement in a PS2 ISO9660 image.

This is the evidence behind ``ps2_iso9660_writer.py``.  Given the source image,
the written destination, and the writer's report, it re-derives from the bytes
alone that

  1. the two images are the same size, so the trailing slack a community
     rebuild carries past the declared volume survived byte-for-byte -- unless
     the report declares a ``growth`` block, in which case the destination is
     exactly the length that block names and every byte past the old end of
     file is inside a declared appended extent;
  2. **outside the declared ranges the two files are byte-identical**, compared
     by streaming the gaps between those ranges rather than by loading 1.6 GB;
  3. every declared range is *explained*: a file extent holds exactly the
     intended content followed by zeros, and a length field holds the new
     length in both endiannesses -- nothing is merely "allowed" to differ;
  4. each replaced file re-reads, from the destination's own directory record,
     to exactly the intended bytes, at the same LBA, from a record that did not
     move or resize;
  5. the rest of the entry tree is identical -- same paths, same LBAs, same
     ``is_dir``, same lengths -- and the PVD's volume size, block size, root
     LBA and volume id are unchanged.  Under a ``growth`` block exactly two
     things may move: a **relocated file's** extent LBA, to the block the
     report names past the old end of file, and the PVD's volume space, to
     cover the appended sectors.  No directory relocates, so the path tables
     are untouched and every directory record stays where it was;
  6. no untouched file's extent, and no directory's extent, lies inside a range
     the writer wrote, so a de-duplicated image cannot have had a second file
     rewritten behind the report's back;
  7. the source still holds the content it held before, so the write did not
     reach back into it.

**Everything here is decoded by this module's own ISO9660 walker.**  It does not
import ``ps2_iso9660``: a verifier that reuses the reader cannot see a bug in
the reader, because both sides would compute the same wrong offset and agree
with each other.  The volume-descriptor and directory-record layout is spelled
out below rather than imported, and both-endian fields are checked for
agreement everywhere they are read -- a disagreement is corruption, not a
convention difference, and it raises.

The writer's report is an input to be checked, never evidence.  Its declared
ranges are compared against ranges this module derives for itself; if they
differ, verification fails rather than adopting the writer's arithmetic.

Every violation raises ``IsoVerifyError`` naming the offending offset or path,
and the CLI exits nonzero.  Passing a corrupted image would be the worst
possible outcome here, so every check is biased toward refusing.

Usage::

    ps2_iso9660_verify.py --source <in.iso> --destination <out.iso> \\
        --report <write-report.json>
    ps2_iso9660_verify.py --inspect <image.iso>
    ps2_iso9660_verify.py --selftest
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


SCHEMA = "ps2_iso9660_verify/v1"

CHUNK = 8 * 1024 * 1024

# ISO9660 (ECMA-119) constants, restated here rather than imported from the
# reader or the writer; see the module docstring.
ISO_MAGIC = b"CD001"
PVD_BLOCK = 16
VD_PRIMARY = 1
VD_SUPPLEMENTARY = 2
VD_TERMINATOR = 255
SECTOR_USER_BYTES = 2048
SYSTEM_AREA_BLOCKS = 16
MAX_VOLUME_DESCRIPTORS = 64

PVD_VOLUME_ID = 40
PVD_VOLUME_SPACE = 80            # both-endian u32
PVD_BLOCK_SIZE = 128             # both-endian u16
PVD_ROOT_RECORD = 156            # a 34-byte directory record

REC_LENGTH = 0
REC_EAR_LENGTH = 1
REC_EXTENT = 2                   # both-endian u32
REC_DATA_LENGTH = 10             # both-endian u32
REC_FLAGS = 25
REC_VOLUME_SEQUENCE = 28         # both-endian u16
REC_IDENT_LENGTH = 32
REC_IDENT = 33
REC_MIN_LENGTH = 34

FLAG_DIRECTORY = 0x02
FLAG_MULTI_EXTENT = 0x80

BOTH_ENDIAN_U32 = 8

# Guard rails, so a malformed image fails instead of spinning.
MAX_ENTRIES = 200_000
MAX_DEPTH = 32
MAX_DIRECTORY_BYTES = 16 * 1024 * 1024


class IsoVerifyError(AssertionError):
    """A verification contract was violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IsoVerifyError(message)


# --------------------------------------------------------------------------
# Positional I/O (os.pread is absent on Windows, where these tools also run)
# --------------------------------------------------------------------------

def _pread_exact(descriptor: int, offset: int, size: int) -> bytes:
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


# --------------------------------------------------------------------------
# Independent ISO9660 decode
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Volume:
    """A volume as this module decoded it, without the reader's help."""

    path: str
    sector_size: int
    data_offset: int
    volume_id: str
    volume_blocks: int
    block_size: int
    root_lba: int
    root_length: int
    file_size: int
    slack_bytes: int
    descriptor_types: tuple


@dataclass(frozen=True)
class Entry:
    """One directory record, located precisely enough to re-find its bytes."""

    path: str
    raw_name: str
    lba: int
    length: int
    is_dir: bool
    parent_lba: int
    record_offset: int


def _both_u32(buffer: bytes, offset: int, what: str) -> int:
    little = struct.unpack_from("<I", buffer, offset)[0]
    big = struct.unpack_from(">I", buffer, offset + 4)[0]
    _require(
        little == big,
        f"{what}: both-endian halves disagree (LE {little} vs BE {big}); "
        "that is corruption, not a convention difference",
    )
    return little


def _both_u16(buffer: bytes, offset: int, what: str) -> int:
    little = struct.unpack_from("<H", buffer, offset)[0]
    big = struct.unpack_from(">H", buffer, offset + 2)[0]
    _require(
        little == big,
        f"{what}: both-endian halves disagree (LE {little} vs BE {big}); "
        "that is corruption, not a convention difference",
    )
    return little


def _probe_layout(descriptor: int, size: int, path: str) -> tuple:
    """Find the sector size and payload offset by looking for the descriptor."""
    for sector_size, data_offset in ((2048, 0), (2352, 24), (2352, 16)):
        offset = PVD_BLOCK * sector_size + data_offset
        if offset + 7 > size:
            continue
        head = _pread_exact(descriptor, offset, 7)
        if head[1:6] == ISO_MAGIC and head[0] in (0, 1, 2, 255):
            return sector_size, data_offset
    raise IsoVerifyError(
        f"{path}: no ISO9660 volume descriptor at block {PVD_BLOCK} for any known "
        "sector layout (2048/0, 2352/24, 2352/16); this is not an ISO9660 image"
    )


def _read_block(descriptor: int, sector_size: int, data_offset: int, lba: int) -> bytes:
    return _pread_exact(
        descriptor, lba * sector_size + data_offset, SECTOR_USER_BYTES
    )


def open_volume(path) -> tuple:
    """Open an image and decode its PVD independently.  Returns (fd, Volume)."""
    path = Path(path)
    _require(
        not path.is_symlink(),
        f"Refusing to verify through a symlink: {path}. Pass the real image path.",
    )
    _require(path.exists(), f"No such image: {path}")
    metadata = os.stat(path, follow_symlinks=False)
    _require(stat.S_ISREG(metadata.st_mode), f"{path} is not a regular file")
    size = metadata.st_size
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        sector_size, data_offset = _probe_layout(descriptor, size, str(path))
        types = []
        primary = None
        for index in range(MAX_VOLUME_DESCRIPTORS):
            lba = PVD_BLOCK + index
            if lba * sector_size + data_offset + SECTOR_USER_BYTES > size:
                break
            block = _read_block(descriptor, sector_size, data_offset, lba)
            if block[1:6] != ISO_MAGIC:
                break
            types.append(block[0])
            if block[0] == VD_PRIMARY and primary is None:
                primary = block
            if block[0] == VD_TERMINATOR:
                break
        _require(
            primary is not None,
            f"{path}: no Primary Volume Descriptor found at or after block "
            f"{PVD_BLOCK}",
        )
        _require(
            primary[6] == 1,
            f"{path}: the Primary Volume Descriptor declares version "
            f"{primary[6]}, not 1",
        )
        volume_blocks = _both_u32(primary, PVD_VOLUME_SPACE, f"{path}: volume space size")
        block_size = _both_u16(primary, PVD_BLOCK_SIZE, f"{path}: logical block size")
        volume_id = primary[PVD_VOLUME_ID : PVD_VOLUME_ID + 32].decode(
            "latin1"
        ).rstrip(" \x00")
        root = primary[PVD_ROOT_RECORD : PVD_ROOT_RECORD + REC_MIN_LENGTH]
        _require(
            root[REC_LENGTH] >= REC_MIN_LENGTH,
            f"{path}: the PVD's root directory record is malformed",
        )
        root_lba = _both_u32(root, REC_EXTENT, f"{path}: root extent")
        root_length = _both_u32(root, REC_DATA_LENGTH, f"{path}: root data length")
        declared = volume_blocks * sector_size
        _require(
            declared <= size,
            f"{path}: the volume declares {volume_blocks} blocks ({declared} bytes) "
            f"but the file holds only {size}; the image is truncated",
        )
        volume = Volume(
            path=str(path),
            sector_size=sector_size,
            data_offset=data_offset,
            volume_id=volume_id,
            volume_blocks=volume_blocks,
            block_size=block_size,
            root_lba=root_lba,
            root_length=root_length,
            file_size=size,
            slack_bytes=size - declared,
            descriptor_types=tuple(types),
        )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, volume


def _extent_offset(volume: Volume, lba: int) -> int:
    return lba * volume.sector_size + volume.data_offset


def _read_extent(descriptor: int, volume: Volume, lba: int, length: int) -> bytes:
    """Read a whole extent.  Only used for directories, which are small."""
    _require(
        length <= MAX_DIRECTORY_BYTES,
        f"{volume.path}: a {length}-byte directory extent at LBA {lba} is past the "
        f"{MAX_DIRECTORY_BYTES}-byte sanity cap",
    )
    if volume.data_offset == 0 and volume.sector_size == volume.block_size:
        return _pread_exact(descriptor, _extent_offset(volume, lba), length)
    out = bytearray()
    block = 0
    while len(out) < length:
        chunk = _read_block(descriptor, volume.sector_size, volume.data_offset, lba + block)
        out += chunk[: length - len(out)]
        block += 1
    return bytes(out)


def _hash_file_extent(descriptor: int, volume: Volume, lba: int, length: int) -> str:
    """Stream-hash a file's data without loading it."""
    digest = hashlib.sha256()
    if volume.data_offset == 0 and volume.sector_size == volume.block_size:
        position = _extent_offset(volume, lba)
        remaining = length
        while remaining:
            take = min(CHUNK, remaining)
            digest.update(_pread_exact(descriptor, position, take))
            position += take
            remaining -= take
        return digest.hexdigest()
    remaining = length
    block = 0
    while remaining:
        chunk = _read_block(descriptor, volume.sector_size, volume.data_offset, lba + block)
        digest.update(chunk[: min(len(chunk), remaining)])
        remaining -= min(len(chunk), remaining)
        block += 1
    return digest.hexdigest()


def _identifier_to_name(ident: bytes) -> str:
    return ident.decode("latin1")


def _strip_version(name: str) -> str:
    base, sep, version = name.rpartition(";")
    if sep and version.isdigit():
        return base
    return name


def normalize_path(text: str) -> str:
    """Canonicalise an ISO path: absolute, upper case, no ';1' version suffix."""
    text = str(text).replace("\\", "/").strip()
    parts = [part for part in text.split("/") if part]
    return "/" + "/".join(_strip_version(part).upper() for part in parts)


def walk(descriptor: int, volume: Volume) -> list:
    """Recursively decode the directory tree, in on-disc record order."""
    entries = [
        Entry(
            path="/",
            raw_name="",
            lba=volume.root_lba,
            length=volume.root_length,
            is_dir=True,
            parent_lba=-1,
            record_offset=-1,
        )
    ]
    visited = {volume.root_lba}

    def descend(lba: int, length: int, prefix: str, depth: int) -> None:
        _require(
            depth <= MAX_DEPTH,
            f"{volume.path}: directory nesting past {MAX_DEPTH} levels at {prefix}",
        )
        _require(
            lba >= SYSTEM_AREA_BLOCKS
            and _extent_offset(volume, lba) + length
            <= volume.volume_blocks * volume.sector_size,
            f"{volume.path}: directory {prefix or '/'} claims an extent at LBA "
            f"{lba} of {length} bytes, which is outside the volume",
        )
        data = _read_extent(descriptor, volume, lba, length)
        children = []
        offset = 0
        while offset < length:
            within = offset % volume.block_size
            record_length = data[offset]
            if record_length == 0:
                offset += volume.block_size - within
                continue
            _require(
                record_length >= REC_MIN_LENGTH
                and within + record_length <= volume.block_size
                and offset + record_length <= length,
                f"{volume.path}: malformed directory record at LBA {lba} offset "
                f"{offset} (declared length {record_length})",
            )
            record = data[offset : offset + record_length]
            where = f"{volume.path}: record at LBA {lba} offset {offset}"
            child_lba = _both_u32(record, REC_EXTENT, f"{where} extent")
            child_length = _both_u32(record, REC_DATA_LENGTH, f"{where} data length")
            _both_u16(record, REC_VOLUME_SEQUENCE, f"{where} volume sequence")
            flags = record[REC_FLAGS]
            ident_length = record[REC_IDENT_LENGTH]
            _require(
                REC_IDENT + ident_length <= record_length,
                f"{where}: a {ident_length}-byte identifier does not fit the record",
            )
            ident = record[REC_IDENT : REC_IDENT + ident_length]
            offset += record_length
            if ident in (b"\x00", b"\x01"):
                continue  # '.' and '..'
            raw_name = _identifier_to_name(ident)
            path = prefix + "/" + _strip_version(raw_name).upper()
            is_dir = bool(flags & FLAG_DIRECTORY)
            entries.append(
                Entry(
                    path=path,
                    raw_name=raw_name,
                    lba=child_lba,
                    length=child_length,
                    is_dir=is_dir,
                    parent_lba=lba,
                    record_offset=offset - record_length,
                )
            )
            _require(
                len(entries) <= MAX_ENTRIES,
                f"{volume.path}: more than {MAX_ENTRIES} directory entries",
            )
            _require(
                not flags & FLAG_MULTI_EXTENT,
                f"{where}: {path} is a multi-extent file, which this tool does not "
                "model; refusing to claim its content was verified",
            )
            if is_dir:
                children.append((child_lba, child_length, path))
        for child_lba, child_length, path in children:
            _require(
                child_lba not in visited,
                f"{volume.path}: directory {path} points back at LBA {child_lba}, "
                "which is already in the tree; refusing to follow a cycle",
            )
            visited.add(child_lba)
            descend(child_lba, child_length, path, depth + 1)

    descend(volume.root_lba, volume.root_length, "", 1)
    return entries


def inspect(path) -> dict:
    """Decode an image with this module's own parser and summarise it."""
    descriptor, volume = open_volume(path)
    try:
        entries = walk(descriptor, volume)
    finally:
        os.close(descriptor)
    return {
        "schema": "ps2_iso9660_verify_inspect/v1",
        "path": volume.path,
        "sector_size": volume.sector_size,
        "data_offset": volume.data_offset,
        "volume_id": volume.volume_id,
        "volume_blocks": volume.volume_blocks,
        "block_size": volume.block_size,
        "root_lba": volume.root_lba,
        "file_size": volume.file_size,
        "slack_bytes": volume.slack_bytes,
        "descriptor_types": list(volume.descriptor_types),
        "entries": len(entries),
        "paths": [entry.path for entry in entries],
    }


# --------------------------------------------------------------------------
# Declared ranges
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Declared:
    start: int
    length: int
    reason: str

    @property
    def end(self) -> int:
        return self.start + self.length

    def as_dict(self) -> dict:
        return {"start": self.start, "length": self.length, "reason": self.reason}


def _as_declared(item) -> Declared:
    """Accept a ByteRange, a JSON dict, or a (start, length, reason) triple."""
    if isinstance(item, Declared):
        return item
    if isinstance(item, dict):
        missing = {"start", "length", "reason"} - set(item)
        _require(not missing, f"a declared range is missing {sorted(missing)}: {item}")
        start, length, reason = item["start"], item["length"], item["reason"]
    elif isinstance(item, (list, tuple)) and len(item) == 3:
        start, length, reason = item
    else:
        start = getattr(item, "start", None)
        length = getattr(item, "length", None)
        reason = getattr(item, "reason", None)
        _require(
            start is not None and length is not None and reason is not None,
            f"a declared range is not a ByteRange, dict or triple: {item!r}",
        )
    _require(
        isinstance(start, int) and isinstance(length, int) and not isinstance(start, bool),
        f"a declared range has non-integer bounds: {item!r}",
    )
    return Declared(int(start), int(length), str(reason))


def _range_key(rng: Declared) -> tuple:
    """(start, length, kind, canonical path) -- a reason compared on identity.

    ``extent:/DATA/FOO.BIN;1`` and ``extent:/data/foo.bin`` name the same file
    and must compare equal; ``extent:/DATA/BAR.BIN`` must not.
    """
    kind, sep, path = rng.reason.partition(":")
    return (rng.start, rng.length, kind, normalize_path(path) if sep else rng.reason)


def _merge_ranges(ranges: list, size: int) -> list:
    """Sort, bounds-check, and refuse overlap; return merged (start, end) spans."""
    ordered = sorted(ranges, key=lambda rng: (rng.start, rng.length))
    merged = []
    previous = None
    for rng in ordered:
        _require(
            rng.length >= 0,
            f"declared range {rng.reason} has a negative length ({rng.length})",
        )
        _require(
            0 <= rng.start and rng.end <= size,
            f"declared range {rng.reason} covers bytes {rng.start}..{rng.end}, "
            f"outside the {size}-byte image",
        )
        _require(
            rng.start >= SYSTEM_AREA_BLOCKS * SECTOR_USER_BYTES,
            f"declared range {rng.reason} starts at byte {rng.start}, inside the "
            "reserved system area; nothing legitimate is written there",
        )
        if previous is not None:
            _require(
                rng.start >= previous.end,
                f"declared ranges {previous.reason} and {rng.reason} overlap at byte "
                f"{rng.start}; each written byte must be declared exactly once",
            )
        if merged and merged[-1][1] >= rng.start:
            merged[-1] = (merged[-1][0], max(merged[-1][1], rng.end))
        else:
            merged.append((rng.start, rng.end))
        previous = rng
    return merged


def _gaps(merged: list, size: int) -> list:
    """The complement of the declared ranges: everything that must not change."""
    gaps = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < size:
        gaps.append((cursor, size))
    return gaps


def _compare_gaps(source_fd: int, destination_fd: int, gaps: list) -> int:
    """Stream every undeclared byte through a chunked comparison.

    Only the gaps are read, so the declared ranges are never enumerated
    byte-by-byte and a 1.6 GB image never lands in memory.  A mismatch is
    localised inside the offending chunk so the message can name the offset.
    """
    compared = 0
    for start, end in gaps:
        position = start
        while position < end:
            take = min(CHUNK, end - position)
            before = _pread_exact(source_fd, position, take)
            after = _pread_exact(destination_fd, position, take)
            if before != after:
                index = next(
                    offset
                    for offset, pair in enumerate(zip(before, after))
                    if pair[0] != pair[1]
                )
                raise IsoVerifyError(
                    f"byte 0x{position + index:x} changed "
                    f"(0x{before[index]:02x} -> 0x{after[index]:02x}) but no declared "
                    "range covers it; the destination holds an undeclared edit"
                )
            position += take
            compared += take
    return compared


def _require_zero(descriptor: int, start: int, length: int, what: str) -> None:
    position = start
    remaining = length
    while remaining:
        take = min(CHUNK, remaining)
        block = _pread_exact(descriptor, position, take)
        if block.strip(b"\x00"):
            index = next(offset for offset, value in enumerate(block) if value)
            raise IsoVerifyError(
                f"{what}: byte 0x{position + index:x} is 0x{block[index]:02x}, not "
                "zero; a stale tail survived inside the extent"
            )
        position += take
        remaining -= take


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

_REQUIRED_REPLACEMENT_KEYS = (
    "path",
    "lba",
    "extent_offset",
    "length_field_offset",
    "previous_length",
    "new_length",
    "sha256",
)


def _replacements_from(report: dict) -> list:
    _require(
        isinstance(report, dict),
        f"the report must be a dict, not {type(report).__name__}",
    )
    items = report.get("replacements")
    _require(
        isinstance(items, list),
        "the report has no 'replacements' list; there is nothing to verify against",
    )
    out = []
    for item in items:
        _require(isinstance(item, dict), f"a replacement entry is not a dict: {item!r}")
        missing = [key for key in _REQUIRED_REPLACEMENT_KEYS if key not in item]
        _require(
            not missing,
            f"replacement {item.get('path', '?')!r} is missing {missing}; the report "
            "does not say enough to be checked",
        )
        out.append(item)
    _require(out, "the report declares no replacements")
    return out


_REQUIRED_GROWTH_KEYS = (
    "append_lba",
    "appended_sectors",
    "previous_volume_blocks",
    "volume_blocks",
    "previous_file_size",
    "file_size",
    "slack_bytes",
    "volume_space_offset",
)


def _growth_from(report: dict) -> dict:
    """The report's growth block, checked for shape, or ``{}``.

    A report without one is a bounded write and every original guarantee
    applies to it unchanged; this function is the only place the two paths
    diverge.
    """
    growth = report.get("growth")
    if growth is None:
        return {}
    _require(isinstance(growth, dict), f"the report's growth block is not a dict: {growth!r}")
    missing = [key for key in _REQUIRED_GROWTH_KEYS if key not in growth]
    _require(
        not missing,
        f"the report's growth block is missing {missing}; it does not say enough "
        "to be checked",
    )
    _require(
        int(growth["volume_blocks"]) > int(growth["previous_volume_blocks"]),
        "the report declares growth but its volume did not grow; a bounded write "
        "must not carry a growth block",
    )
    return growth


def verify_replacement(source, destination, report: dict, *, expected=None) -> dict:
    """Prove the destination is the source with only the declared edits.

    ``report`` is the dict ``ps2_iso9660_writer.replace_files`` returned, or the
    same thing round-tripped through JSON.  ``expected`` optionally maps an ISO
    path to the bytes it should now hold, which pins the content to the caller's
    intent rather than to the writer's claim about it.

    Raises ``IsoVerifyError`` on any violation.  Returns a report of what was
    checked.
    """
    source, destination = Path(source), Path(destination)
    declared = [_as_declared(item) for item in report.get("declared_ranges", [])]
    replacements = _replacements_from(report)
    _growth_from(report)   # shape-checked before either image is opened

    source_fd, source_volume = open_volume(source)
    try:
        destination_fd, destination_volume = open_volume(destination)
    except BaseException:
        os.close(source_fd)
        raise
    try:
        out = _verify(
            source_fd,
            source_volume,
            destination_fd,
            destination_volume,
            declared,
            replacements,
            report,
            expected,
        )
    finally:
        os.close(source_fd)
        os.close(destination_fd)
    return out


def _verify(
    source_fd,
    source_volume,
    destination_fd,
    destination_volume,
    declared,
    replacements,
    report,
    expected,
) -> dict:
    size = source_volume.file_size
    growth = _growth_from(report)

    # 1. Size.  Bounded: identical, which is where truncated slack is caught.
    #    Grown: exactly the length the report names, and not a byte more.
    if growth:
        _require(
            size == int(growth["previous_file_size"]),
            f"the source is {size} bytes but the report's growth block describes a "
            f"{growth['previous_file_size']}-byte one; this report is not about "
            "these files",
        )
        _require(
            destination_volume.file_size == int(growth["file_size"]),
            f"the destination is {destination_volume.file_size} bytes and the report "
            f"says a grown image is {growth['file_size']}",
        )
        _require(
            destination_volume.file_size > size,
            "the report declares growth but the destination is no longer than the "
            "source",
        )
        _require(
            int(growth["append_lba"]) * source_volume.sector_size == size,
            f"the report appends at LBA {growth['append_lba']}, which is not the "
            f"first block past the {size}-byte source; a relocated file must land "
            "after every byte the source had",
        )
    else:
        _require(
            destination_volume.file_size == size,
            f"the destination is {destination_volume.file_size} bytes but the source "
            f"is {size}; the image's trailing slack must survive byte-for-byte",
        )

    # 2. Geometry this tool can address exactly, and one directory tree only.
    for volume in (source_volume, destination_volume):
        _require(
            volume.sector_size == SECTOR_USER_BYTES and volume.data_offset == 0,
            f"{volume.path}: {volume.sector_size}-byte sectors at payload offset "
            f"{volume.data_offset} is a raw-CD image, whose user data is interleaved "
            "with EDC/ECC. The writer refuses to produce one, so a report claiming "
            "otherwise cannot be verified.",
        )
        _require(
            volume.block_size == SECTOR_USER_BYTES,
            f"{volume.path}: the volume declares {volume.block_size}-byte logical "
            f"blocks; only {SECTOR_USER_BYTES} is addressable here",
        )
        _require(
            VD_SUPPLEMENTARY not in volume.descriptor_types,
            f"{volume.path}: the image carries a supplementary volume descriptor, so "
            "a second directory tree holds a second copy of every length field. This "
            "tool checks one tree, so it cannot prove the other is consistent.",
        )

    # 5. PVD fields and slack are unchanged -- except the two a growth block
    #    is allowed to move, each to the value it names.
    moved = {"volume_blocks", "slack_bytes"} if growth else set()
    for field in ("volume_blocks", "block_size", "root_lba", "root_length",
                  "volume_id", "sector_size", "data_offset", "slack_bytes"):
        before = getattr(source_volume, field)
        after = getattr(destination_volume, field)
        if field in moved:
            _require(
                before == int(growth["previous_%s" % field])
                if ("previous_%s" % field) in growth else True,
                f"the source's {field} is {before!r} but the report's growth block "
                f"says {growth.get('previous_%s' % field)!r}",
            )
            _require(
                after == int(growth[field]),
                f"the destination's {field} is {after!r} and the report's growth "
                f"block says {growth[field]!r}",
            )
            continue
        _require(
            before == after,
            f"the PVD's {field} changed: {before!r} -> {after!r}; a bounded "
            "replacement never touches the volume descriptor",
        )
    for field, value in (
        ("volume_blocks", source_volume.volume_blocks),
        ("block_size", source_volume.block_size),
        ("root_lba", source_volume.root_lba),
        ("volume_id", source_volume.volume_id),
        ("sector_size", source_volume.sector_size),
        ("data_offset", source_volume.data_offset),
        ("slack_bytes", source_volume.slack_bytes),
        ("file_size", size),
    ):
        # A report's top-level fields always describe the SOURCE, growth or no
        # growth; the destination's own numbers are checked against the growth
        # block above.
        if field in report:
            _require(
                report[field] == value,
                f"the report claims {field}={report[field]!r} but the images say "
                f"{value!r}; the report does not describe these files",
            )

    volume_bytes = source_volume.volume_blocks * source_volume.sector_size
    grown_bytes = destination_volume.volume_blocks * destination_volume.sector_size
    for rng in declared:
        if growth and rng.reason.startswith("newextent:"):
            _require(
                size <= rng.start and rng.end <= grown_bytes,
                f"declared range {rng.reason} covers bytes {rng.start}..{rng.end}, "
                f"which is not inside the appended region "
                f"({size}..{grown_bytes}); a relocated file lands past the source",
            )
            continue
        _require(
            rng.end <= volume_bytes,
            f"declared range {rng.reason} ends at byte {rng.end}, past the declared "
            f"volume ({volume_bytes} bytes); the writer must not write into slack",
        )

    # 4/5. Both trees, decoded here rather than by the reader.
    source_entries = walk(source_fd, source_volume)
    destination_entries = walk(destination_fd, destination_volume)
    _require(
        len(source_entries) == len(destination_entries),
        f"the entry count changed: {len(source_entries)} -> "
        f"{len(destination_entries)}; a bounded replacement never adds or removes a "
        "directory record",
    )

    replaced = {}
    for item in replacements:
        path = normalize_path(item["path"])
        _require(
            path not in replaced,
            f"the report names {path} twice; one file, one replacement",
        )
        replaced[path] = item

    source_by_path = {}
    for entry in source_entries:
        _require(
            entry.path not in source_by_path,
            f"{source_volume.path}: two directory records both claim {entry.path}; "
            "this tool cannot tell which one the report means",
        )
        source_by_path[entry.path] = entry
    destination_by_path = {}
    for entry in destination_entries:
        _require(
            entry.path not in destination_by_path,
            f"{destination_volume.path}: two directory records both claim "
            f"{entry.path}",
        )
        destination_by_path[entry.path] = entry

    relocated_paths = {normalize_path(path)
                       for path in (growth.get("relocated") or [])} if growth else set()
    for before, after in zip(source_entries, destination_entries):
        _require(
            before.path == after.path,
            f"the entry tree changed shape: {before.path} became {after.path}",
        )
        if before.path in relocated_paths:
            _require(
                not before.is_dir and not after.is_dir,
                f"{before.path} is a directory and the report says it was relocated; "
                "relocating a directory would move its records and invalidate the "
                "path tables",
            )
            _require(
                after.lba >= int(growth["append_lba"]),
                f"{before.path} was relocated to LBA {after.lba}, which is not past "
                f"the end of the source image (LBA {growth['append_lba']})",
            )
            _require(
                after.lba != before.lba,
                f"{before.path} is named as relocated but still sits at LBA "
                f"{after.lba}",
            )
        else:
            _require(
                before.lba == after.lba,
                f"{before.path} moved from LBA {before.lba} to {after.lba}; only a "
                "file the report names as relocated may move",
            )
        _require(
            before.is_dir == after.is_dir,
            f"{before.path} changed between file and directory",
        )
        _require(
            (before.parent_lba, before.record_offset)
            == (after.parent_lba, after.record_offset),
            f"{before.path}'s directory record moved from LBA {before.parent_lba} "
            f"offset {before.record_offset} to LBA {after.parent_lba} offset "
            f"{after.record_offset}; records must not move or renumber",
        )
        if before.path in replaced:
            continue
        _require(
            before.length == after.length,
            f"{before.path} was not replaced but its declared length changed "
            f"{before.length} -> {after.length}",
        )

    # 3. Every declared range is one this module derived for itself.
    derived = []
    checked = []
    for path, item in sorted(replaced.items()):
        before = source_by_path.get(path)
        after = destination_by_path.get(path)
        _require(
            before is not None and after is not None,
            f"the report names {path}, which is not in "
            f"{'the source' if before is None else 'the destination'} tree",
        )
        _require(
            not after.is_dir,
            f"{path} is a directory in the destination; directories are not "
            "replaceable content",
        )
        new_length = int(item["new_length"])
        previous_length = int(item["previous_length"])
        relocated = path in relocated_paths
        _require(
            bool(item.get("relocated")) == relocated,
            f"{path}: the report's replacement entry and its growth block disagree "
            "about whether this file moved",
        )
        _require(
            before.length == previous_length,
            f"{path}: the report says it held {previous_length} bytes but the source "
            f"record declares {before.length}",
        )
        _require(
            after.length == new_length,
            f"{path}: the report says it now holds {new_length} bytes but the "
            f"destination record declares {after.length}",
        )
        if not relocated:
            _require(
                new_length <= previous_length,
                f"{path}: {new_length} bytes cannot fit the {previous_length}-byte "
                "extent it claims to occupy, and the report does not say it moved",
            )
        _require(
            int(item["lba"]) == after.lba,
            f"{path}: the report claims LBA {item['lba']} but the destination record "
            f"says {after.lba}",
        )

        old_extent_offset = _extent_offset(source_volume, before.lba)
        extent_offset = _extent_offset(destination_volume, after.lba)
        length_field = (
            _extent_offset(destination_volume, after.parent_lba)
            + after.record_offset
            + REC_DATA_LENGTH
        )
        _require(
            int(item["extent_offset"]) == (old_extent_offset if relocated
                                           else extent_offset),
            f"{path}: the report puts its {'abandoned ' if relocated else ''}extent "
            f"at byte {item['extent_offset']} but the records put it at "
            f"{old_extent_offset if relocated else extent_offset}",
        )
        _require(
            int(item["length_field_offset"]) == length_field,
            f"{path}: the report puts its length field at byte "
            f"{item['length_field_offset']} but the destination's own record puts it "
            f"at {length_field}",
        )
        derived.append(Declared(old_extent_offset, previous_length, f"extent:{path}"))
        derived.append(Declared(length_field, BOTH_ENDIAN_U32, f"dirrec_length:{path}"))
        if relocated:
            extent_field = (
                _extent_offset(destination_volume, after.parent_lba)
                + after.record_offset
                + REC_EXTENT
            )
            sector = destination_volume.sector_size
            appended = ((new_length + sector - 1) // sector) * sector
            derived.append(Declared(extent_field, BOTH_ENDIAN_U32,
                                    f"dirrec_extent:{path}"))
            derived.append(Declared(extent_offset, appended, f"newextent:{path}"))
            field = _pread_exact(destination_fd, extent_field, BOTH_ENDIAN_U32)
            little = struct.unpack_from("<I", field, 0)[0]
            big = struct.unpack_from(">I", field, 4)[0]
            _require(
                little == big == after.lba,
                f"{path}: the destination's extent LBA reads LE {little} / BE {big} "
                f"at byte 0x{extent_field:x}, expected {after.lba} in both halves",
            )
            source_field = _pread_exact(source_fd, extent_field, BOTH_ENDIAN_U32)
            _require(
                struct.unpack_from("<I", source_field, 0)[0] == before.lba
                and struct.unpack_from(">I", source_field, 4)[0] == before.lba,
                f"{path}: the source's extent LBA is not {before.lba} in both halves; "
                "the source is not the baseline this report describes",
            )
            _require_zero(destination_fd, extent_offset + new_length,
                          appended - new_length,
                          f"{path}: the pad after its relocated extent")
            _require_zero(destination_fd, old_extent_offset, previous_length,
                          f"{path}: the extent it moved out of")

        # The 8 both-endian bytes really do say the new length, in both halves,
        # and the source's own copy still says the old one.
        field = _pread_exact(destination_fd, length_field, BOTH_ENDIAN_U32)
        little = struct.unpack_from("<I", field, 0)[0]
        big = struct.unpack_from(">I", field, 4)[0]
        _require(
            little == big == new_length,
            f"{path}: the destination's length field reads LE {little} / BE {big} at "
            f"byte 0x{length_field:x}, expected {new_length} in both halves",
        )
        source_field = _pread_exact(source_fd, length_field, BOTH_ENDIAN_U32)
        source_little = struct.unpack_from("<I", source_field, 0)[0]
        source_big = struct.unpack_from(">I", source_field, 4)[0]
        _require(
            source_little == source_big == previous_length,
            f"{path}: the source's length field reads LE {source_little} / BE "
            f"{source_big}, expected {previous_length} in both halves; the source is "
            "not the baseline this report describes",
        )

        # The extent holds exactly the intended bytes, then zeros.
        digest = _hash_file_extent(destination_fd, destination_volume, after.lba, new_length)
        _require(
            digest == item["sha256"],
            f"{path}: the destination's {new_length} bytes hash to {digest}, but the "
            f"report claims {item['sha256']}",
        )
        if expected is not None and path in {normalize_path(k) for k in expected}:
            wanted = next(
                value for key, value in expected.items() if normalize_path(key) == path
            )
            wanted = bytes(wanted)
            _require(
                len(wanted) == new_length,
                f"{path}: the caller expected {len(wanted)} bytes but the record "
                f"declares {new_length}",
            )
            _require(
                hashlib.sha256(wanted).hexdigest() == digest,
                f"{path}: the destination's content is not the bytes the caller "
                "asked for",
            )
        if not relocated:
            _require_zero(
                destination_fd,
                extent_offset + new_length,
                previous_length - new_length,
                f"{path}: the tail of its extent",
            )

        # 7. The source still holds what it held; the write never reached back.
        if "previous_sha256" in item:
            before_digest = _hash_file_extent(
                source_fd, source_volume, before.lba, previous_length
            )
            _require(
                before_digest == item["previous_sha256"],
                f"{path}: the source now hashes to {before_digest} but the report "
                f"recorded {item['previous_sha256']}; the source image was modified",
            )
        checked.append(
            {
                "path": path,
                "lba": after.lba,
                "relocated": relocated,
                "previous_lba": before.lba,
                "extent_offset": extent_offset,
                "length_field_offset": length_field,
                "previous_length": previous_length,
                "new_length": new_length,
                "zero_filled_bytes": previous_length - new_length,
                "sha256": digest,
            }
        )

    if growth:
        volume_space = (PVD_BLOCK * destination_volume.sector_size
                        + destination_volume.data_offset + PVD_VOLUME_SPACE)
        _require(
            int(growth["volume_space_offset"]) == volume_space,
            f"the report puts the PVD's volume space at byte "
            f"{growth['volume_space_offset']} and this image puts it at "
            f"{volume_space}",
        )
        derived.append(Declared(volume_space, BOTH_ENDIAN_U32, "pvd_volume_space"))
        # Every appended byte is inside one of the newextent ranges: the writer
        # may lengthen the image only by the extents it declared.
        appended = sorted((rng for rng in derived
                           if rng.reason.startswith("newextent:")),
                          key=lambda rng: rng.start)
        cursor = size
        for rng in appended:
            _require(
                rng.start == cursor,
                f"the appended region has a {rng.start - cursor}-byte hole before "
                f"{rng.reason}; every byte past the source's end must belong to a "
                "relocated file",
            )
            cursor = rng.end
        _require(
            cursor == destination_volume.file_size,
            f"the destination ends at byte {destination_volume.file_size} and the "
            f"declared appended extents end at {cursor}; the tail belongs to nothing",
        )
        _require(
            int(growth["appended_sectors"]) * destination_volume.sector_size
            == destination_volume.file_size - size,
            "the growth block's appended-sector count does not match the two files",
        )

    # Compare on a normalised reason so a reader that spells a path with ';1'
    # or in a different case cannot turn an honest write into a failure -- while
    # a reason naming a *different* file still fails, as it must.
    declared_key = sorted(_range_key(rng) for rng in declared)
    derived_key = sorted(_range_key(rng) for rng in derived)
    _require(
        declared_key == derived_key,
        "the declared ranges are not the ranges these two images imply -- the "
        "report's arithmetic disagrees with the records on disc.\n"
        f"  declared: {declared_key}\n"
        f"  derived:  {derived_key}",
    )

    # 6. Nothing else lives inside a range the writer wrote.
    extent_ranges = [rng for rng in derived
                     if rng.reason.startswith("extent:")
                     or rng.reason.startswith("newextent:")]
    directories = {}
    for entry in destination_entries:
        if entry.is_dir:
            directories[entry.lba] = entry
    for entry in destination_entries:
        start = _extent_offset(destination_volume, entry.lba)
        end = start + entry.length
        if entry.length == 0:
            continue
        for rng in extent_ranges:
            if rng.reason in (f"extent:{entry.path}", f"newextent:{entry.path}"):
                continue
            _require(
                not (start < rng.end and rng.start < end),
                f"{entry.path} occupies bytes 0x{start:x}..0x{end:x}, which overlap "
                f"the range written for {rng.reason.split(':', 1)[1]}. Two records "
                "share these bytes, so the replacement was not bounded to one file.",
            )
    for rng in derived:
        if not rng.reason.startswith("dirrec_length:"):
            continue
        path = rng.reason.split(":", 1)[1]
        entry = destination_by_path[path]
        owner = directories.get(entry.parent_lba)
        _require(
            owner is not None,
            f"{path}: its record claims to live in LBA {entry.parent_lba}, which is "
            "not a directory in this image",
        )
        owner_start = _extent_offset(destination_volume, owner.lba)
        _require(
            owner_start <= rng.start and rng.end <= owner_start + owner.length,
            f"{path}: its patched length field at byte 0x{rng.start:x} is outside "
            f"the extent of its parent directory {owner.path}",
        )

    # 2. Everything else is byte-identical, compared by streaming the gaps.
    #    Under growth the comparison runs over the source's length -- every
    #    byte past it was proved above to belong to a declared appended extent.
    merged = _merge_ranges(declared, destination_volume.file_size)
    gaps = [gap for gap in _gaps(merged, destination_volume.file_size) if gap[0] < size]
    gaps = [(start, min(end, size)) for start, end in gaps]
    compared = _compare_gaps(source_fd, destination_fd, gaps)
    slack = source_volume.slack_bytes
    if growth:
        _require(
            destination_volume.slack_bytes == int(growth["slack_bytes"]),
            f"the destination's trailing slack is "
            f"{destination_volume.slack_bytes} and the report says "
            f"{growth['slack_bytes']}",
        )
    else:
        _require(
            destination_volume.slack_bytes == slack,
            f"the trailing slack changed: {slack} -> {destination_volume.slack_bytes}",
        )

    return {
        "schema": SCHEMA,
        "source": source_volume.path,
        "destination": destination_volume.path,
        "file_size": size,
        "volume_blocks": source_volume.volume_blocks,
        "volume_id": source_volume.volume_id,
        "slack_bytes": slack,
        "entries_compared": len(source_entries),
        "declared_ranges": [rng.as_dict() for rng in sorted(declared, key=lambda r: r.start)],
        "declared_bytes": sum(rng.length for rng in declared),
        "unchanged_bytes_compared": compared,
        "replacements_checked": checked,
        "grew": bool(growth),
        "destination_file_size": destination_volume.file_size,
        "destination_volume_blocks": destination_volume.volume_blocks,
        "result": "PASS",
    }


# --------------------------------------------------------------------------
# Self-test: accepts one correct write, rejects five corrupted ones
# --------------------------------------------------------------------------

def _corrupt(path: Path, offset: int, value: bytes) -> None:
    with open(path, "r+b") as handle:
        handle.seek(offset)
        handle.write(value)


def selftest(tmp: Path | None = None) -> int:
    """Prove the checks accept a correct write and reject the ways it can rot.

    The writer is used only to *manufacture* fixtures; every assertion below
    runs through this module's own ISO9660 decode, so the writer is the subject
    of the test rather than a participant in it.
    """
    import tempfile

    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ps2_iso9660_writer as writer  # fixture generator only

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        room = Path(work)
        source = room / "synthetic.iso"
        writer._synthetic_image(source, slack=18_432)

        content = b"verified"
        report = writer.replace_files(
            source, room / "good.iso", {"/DATA/FOO.BIN": content}
        )
        good = room / "good.iso"
        result = verify_replacement(source, good, report, expected={"/DATA/FOO.BIN": content})
        if result["result"] != "PASS":
            raise IsoVerifyError(result)
        if result["unchanged_bytes_compared"] <= 0:
            raise IsoVerifyError("the gap comparison read nothing")

        # A JSON round-trip of the report must verify identically: the CLI hands
        # over dicts, not ByteRange objects.
        as_json = json.loads(json.dumps(writer.report_to_json(report)))
        verify_replacement(source, good, as_json)

        entry = report["replacements"][0]

        def rejected(name: str, mutate, why: str, report_override=None) -> None:
            candidate = room / name
            candidate.write_bytes(good.read_bytes())
            mutate(candidate)
            try:
                verify_replacement(source, candidate, report_override or report)
            except IsoVerifyError:
                return
            raise AssertionError(f"{why} must fail verification")

        # An undeclared byte anywhere outside the declared ranges.
        rejected(
            "undeclared.iso",
            lambda path: _corrupt(path, 23 * 2048 + 4, b"\xff"),
            "an undeclared byte change",
        )
        # A byte inside the replaced content: declared, but not what was claimed.
        rejected(
            "content.iso",
            lambda path: _corrupt(path, entry["extent_offset"] + 1, b"\x00"),
            "a corrupted replacement body",
        )
        # A non-zero byte in the zero-filled tail.
        rejected(
            "tail.iso",
            lambda path: _corrupt(
                path, entry["extent_offset"] + entry["new_length"] + 3, b"\x01"
            ),
            "a stale tail byte",
        )
        # A big-endian length half that disagrees with the little-endian one.
        rejected(
            "endian.iso",
            lambda path: _corrupt(path, entry["length_field_offset"] + 4, b"\x00\x00\x00\x00"),
            "a both-endian length disagreement",
        )
        # Truncated slack: same volume, different file size.
        def truncate(path: Path) -> None:
            data = path.read_bytes()
            path.write_bytes(data[:-18_432])

        rejected("truncated.iso", truncate, "a truncated image")

        # A report that under-declares its own edit must fail even though the
        # image is exactly what the writer produced.
        thin = dict(report)
        thin["declared_ranges"] = [
            rng for rng in report["declared_ranges"] if rng.reason.startswith("extent:")
        ]
        try:
            verify_replacement(source, good, thin)
        except IsoVerifyError:
            pass
        else:  # pragma: no cover
            raise AssertionError("an under-declared report must fail verification")

        # A report that over-declares (claims a range the images do not imply).
        wide = dict(report)
        wide["declared_ranges"] = list(report["declared_ranges"]) + [
            writer.ByteRange(23 * 2048, 16, "extent:/HELLO.TXT")
        ]
        try:
            verify_replacement(source, good, wide)
        except IsoVerifyError:
            pass
        else:  # pragma: no cover
            raise AssertionError("an over-declared report must fail verification")

        # -- a relocated file, and the ways a grown image can rot -----------
        grown_content = b"G" * 7000
        grown = room / "grown.iso"
        grown_report = writer.replace_files(
            source, grown, {"/DATA/BAR.BIN": grown_content}, allow_growth=True)
        grown_json = json.loads(json.dumps(writer.report_to_json(grown_report)))
        grown_result = verify_replacement(source, grown, grown_json,
                                          expected={"/DATA/BAR.BIN": grown_content})
        if grown_result["result"] != "PASS" or not grown_result["grew"]:
            raise IsoVerifyError(grown_result)
        moved = next(item for item in grown_json["replacements"]
                     if item["path"] == "/DATA/BAR.BIN")
        if not moved["relocated"] or moved["new_lba"] <= moved["previous_lba"]:
            raise IsoVerifyError("the fixture did not actually relocate anything")

        def grown_rejected(name: str, mutate, why: str, report_override=None) -> None:
            candidate = room / name
            candidate.write_bytes(grown.read_bytes())
            mutate(candidate)
            try:
                verify_replacement(source, candidate, report_override or grown_json)
            except IsoVerifyError:
                return
            raise AssertionError(f"{why} must fail verification")

        grown_rejected(
            "grown-content.iso",
            lambda path: _corrupt(path, moved["appended_offset"] + 5, b"\x00"),
            "a corrupted relocated body",
        )
        grown_rejected(
            "grown-pad.iso",
            lambda path: _corrupt(
                path, moved["appended_offset"] + moved["new_length"] + 2, b"\x01"),
            "a non-zero pad after a relocated extent",
        )
        grown_rejected(
            "grown-stale.iso",
            lambda path: _corrupt(path, moved["extent_offset"] + 4, b"\x7f"),
            "a stale byte left in the extent the file moved out of",
        )
        grown_rejected(
            "grown-pvd.iso",
            lambda path: _corrupt(
                path, grown_json["growth"]["volume_space_offset"],
                struct.pack("<I", grown_json["growth"]["previous_volume_blocks"])),
            "a PVD volume space that no longer covers the appended sectors",
        )
        grown_rejected(
            "grown-lba.iso",
            lambda path: _corrupt(
                path, moved["extent_field_offset"],
                struct.pack("<I", moved["previous_lba"])),
            "a directory record whose two LBA halves disagree",
        )

        # A grown image described as a bounded write, and a bounded image
        # described as a grown one: both are the report lying about the files.
        stripped = {key: value for key, value in grown_json.items() if key != "growth"}
        try:
            verify_replacement(source, grown, stripped)
        except IsoVerifyError:
            pass
        else:  # pragma: no cover
            raise AssertionError("a grown image with no growth block must fail")
        borrowed = dict(as_json)
        borrowed["growth"] = grown_json["growth"]
        try:
            verify_replacement(source, good, borrowed)
        except IsoVerifyError:
            pass
        else:  # pragma: no cover
            raise AssertionError("a bounded image with a growth block must fail")

        # A growth block that miscounts its own appended sectors.
        miscounted = json.loads(json.dumps(grown_json))
        miscounted["growth"]["appended_sectors"] += 1
        try:
            verify_replacement(source, grown, miscounted)
        except IsoVerifyError:
            pass
        else:  # pragma: no cover
            raise AssertionError("a miscounted growth block must fail verification")

    print(
        "PS2_ISO9660_VERIFY_SELFTEST_PASS decoder=independent stream=gaps "
        "accepts=declared+relocated rejects=undeclared,content,tail,endian,"
        "truncation,under-declared,over-declared,relocated-content,relocated-pad,"
        "stale-extent,pvd,lba,growth-mismatch"
    )
    return 0


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", type=Path, help="the image before the write")
    parser.add_argument("--destination", type=Path, help="the image after the write")
    parser.add_argument(
        "--report", type=Path, help="the writer's JSON report, whose ranges are checked"
    )
    parser.add_argument(
        "--inspect", type=Path, help="decode an image with this module's own parser"
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="prove the checks against synthetic images; no disc image needed",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.inspect:
        print(json.dumps(inspect(args.inspect), indent=2))
        return 0
    if not args.source or not args.destination or not args.report:
        parser.error(
            "--source, --destination and --report are required unless --inspect or "
            "--selftest is given"
        )

    report = json.loads(args.report.read_text(encoding="utf-8"))
    print(json.dumps(verify_replacement(args.source, args.destination, report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
