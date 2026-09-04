#!/usr/bin/env python3
"""Read PlayStation 2 disc images: ISO9660 volume, entry tree and boot identity.

This is the *reader* half of the PS2 disc lane -- the PS2 analogue of the Xbox
side's XISO support.  It parses an ISO9660 primary volume descriptor and walks
the directory tree straight out of the bytes, so a caller can enumerate every
file on a disc, read one out, hash it, and recover the disc's identity from
``SYSTEM.CNF``.  Nothing here writes; the bounded replacement writer lives in
``tools/ps2_iso9660_writer.py`` and its independent verifier in
``tools/ps2_iso9660_verify.py``.

Two sector layouts are recognised, both detected from content rather than from
the file extension:

``2048``-byte logical sectors
    Every DVD-based PS2 title.  The volume descriptors start at byte
    ``16 * 2048 = 0x8000`` and logical block *n* is simply byte ``n * 2048``.

``2352``-byte raw CD sectors  (**supported, read-only**)
    CD-based PS2 titles ripped as ``.bin``/``.cue``.  Each sector carries a
    12-byte sync pattern, a 4-byte header, and -- for Mode 2 Form 1 -- an
    8-byte subheader ahead of the 2048 user bytes, so ``data_offset`` is 24
    (Mode 2 Form 1) or 16 (Mode 1).  The reader treats the layout as pure
    addressing: it seeks per sector and never validates EDC/ECC, because it
    never changes a sector.  A *writer* must not touch a raw-CD image without
    recomputing EDC/ECC, which is out of scope for v1.

Load-bearing facts this module refuses to get wrong:

* **ISO9660 stores multi-byte numbers twice**, a little-endian copy followed by
  a big-endian copy.  The little-endian copy is the one read, but the
  big-endian copy is *verified* against it and a disagreement raises
  ``Iso9660Error``.  Silent divergence there is corruption, and a reader that
  ignores it hands a writer a wrong offset.
* **Trailing slack past the declared volume is legal.**  A retail rip may end
  exactly on the last declared block while a community rebuild carries
  kilobytes of padding after it.  ``IsoImage.slack_bytes`` records the
  difference so a writer can preserve it byte-for-byte; it is never treated as
  corruption and never trimmed.  Conversely a ripper that *trimmed* padding
  yields a negative ``slack_bytes``: that too is reported rather than refused,
  and any extent that actually runs past the end of the file is caught at read
  time with a specific error instead of silently returning short data.
* **The volume identifier means nothing.**  Retail images ship it blank and
  mods overwrite it; admission is never gated on it.
* **``SYSTEM.CNF`` -> ``BOOT2`` is the identity anchor**, the PS2 counterpart of
  ``default.xbe``.  ``boot_identity()`` parses it and reports the boot ELF's
  path, serial, size and SHA-256.

Everything streams.  These images run past 1.6 GB and no function here ever
holds more than a bounded window of one in memory.

Deliberate v1 exclusions (all out of scope, and refused rather than guessed at):
image rebuilding or growing a file, path-table rewriting, the Joliet and Rock
Ridge extensions, UDF, multi-extent files, dual-layer break handling, and
adding or deleting files.  A multi-extent directory record or an extended
attribute record raises ``Iso9660Error`` naming the path, so an image that
needs one of those fails loudly instead of being misread.

Usage::

    ps2_iso9660.py --inspect "Madden NFL 09 (USA).iso"
    ps2_iso9660.py --inspect "Madden NFL 09 (USA).iso" --json
    ps2_iso9660.py --image disc.iso --list
    ps2_iso9660.py --image disc.iso --extract /SYSTEM.CNF --output SYSTEM.CNF
    ps2_iso9660.py --selftest        # synthetic images only; needs no disc
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple

__all__ = [
    "SECTOR_USER_BYTES",
    "Iso9660Error",
    "IsoEntry",
    "IsoImage",
    "open_image",
    "iter_entries",
    "find",
    "read_file",
    "sha256_of",
    "boot_identity",
    # Additive helpers (not part of the frozen interface, but stable):
    "extent_byte_offset",
    "check_extent",
    "iter_file_chunks",
    "extract_file",
]


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

SECTOR_USER_BYTES = 2048        # logical block size in every known PS2 image

RAW_SECTOR_BYTES = 2352         # a raw CD sector: sync + header + user + EDC/ECC
RAW_MODE2_FORM1_OFFSET = 24     # 12 sync + 4 header + 8 subheader
RAW_MODE1_OFFSET = 16           # 12 sync + 4 header

# Candidate (sector_size, data_offset) layouts, probed in this order.  2048
# first because every DVD-based PS2 title uses it; Mode 2 Form 1 before Mode 1
# because PS2 CD titles are Mode 2.  The probes cannot collide: a Mode 2
# sector holds its subheader where Mode 1 holds "CD001", and vice versa.
_LAYOUT_CANDIDATES = (
    (SECTOR_USER_BYTES, 0),
    (RAW_SECTOR_BYTES, RAW_MODE2_FORM1_OFFSET),
    (RAW_SECTOR_BYTES, RAW_MODE1_OFFSET),
)

STANDARD_IDENTIFIER = b"CD001"
VOLUME_DESCRIPTOR_LBA = 16      # where the descriptor set starts, always

DESC_BOOT_RECORD = 0
DESC_PRIMARY = 1
DESC_SUPPLEMENTARY = 2          # Joliet lives here; deliberately ignored
DESC_PARTITION = 3
DESC_TERMINATOR = 255

# Directory record file flags (ECMA-119 9.1.6).
FLAG_HIDDEN = 0x01
FLAG_DIRECTORY = 0x02
FLAG_ASSOCIATED = 0x04
FLAG_MULTI_EXTENT = 0x80

DIRECTORY_RECORD_MIN = 33       # fixed part, before the identifier
ROOT_RECORD_SIZE = 34           # the copy embedded in the PVD

# Caps.  Every one of these is far above anything a real PS2 disc reaches;
# they exist so a corrupt or hostile image fails fast instead of allocating.
MAX_VOLUME_DESCRIPTORS = 64
MAX_DIRECTORY_DEPTH = 64
MAX_ENTRIES = 200_000
MAX_DIRECTORY_BYTES = 16 * 1024 * 1024
MAX_READ_FILE_BYTES = 512 * 1024 * 1024
MAX_SYSTEM_CNF_BYTES = 64 * 1024

# Sectors pulled per seek while streaming an extent: 1 MiB of user data.
STREAM_CHUNK_SECTORS = 512

_VERSION_SUFFIX = re.compile(r";\d+$")
_DEVICE_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9_]*:")


class Iso9660Error(ValueError):
    """Raised when an image fails bounded parsing or a fail-closed read rule."""


def _require(condition: object, message: str) -> None:
    """Fail closed with an actionable message rather than misparsing."""
    if not condition:
        raise Iso9660Error(message)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class IsoEntry:
    """One file or directory, plus where its *directory record* lives.

    ``parent_lba`` and ``record_offset`` locate the record itself, not the
    data: they are what a writer needs to patch the declared data length in
    place.  ``record_offset`` is measured from the start of the parent's
    directory *extent*, so on a multi-block directory it can exceed 2048.  Use
    ``extent_byte_offset(image, entry.parent_lba, entry.record_offset)`` to turn
    the pair into an absolute byte offset under either sector layout.
    """

    path: str            # "/DATA/FOO.BIN" -- upper case, '/'-separated, no ';1'
    raw_name: str        # "FOO.BIN;1" exactly as stored
    lba: int             # extent start, in logical blocks
    length: int          # declared data length in bytes
    is_dir: bool
    parent_lba: int      # LBA of the directory extent holding this record
    record_offset: int   # byte offset of this record within that extent


@dataclass(frozen=True)
class IsoImage:
    """A parsed volume header.  Holds no file handle; every call reopens.

    ``slack_bytes`` is ``file_size - volume_blocks * sector_size``.  It is
    normally 0 (retail) or positive (a rebuild that kept trailing padding), and
    is preserved rather than judged.  A negative value means the ripper trimmed
    padding the volume still declares; reads are bounds-checked against the
    real file size regardless, so a trimmed image degrades to a precise error
    on the affected file instead of silent truncation.
    """

    path: Path
    sector_size: int     # 2048, or 2352 for raw CD
    data_offset: int     # 0, or 24 for raw CD (Mode 1 / Mode 2 Form 1 payload)
    volume_id: str
    volume_blocks: int   # PVD volume space size
    block_size: int      # PVD logical block size (2048)
    root_lba: int
    root_length: int
    file_size: int
    slack_bytes: int     # file_size - volume_blocks * sector_size ; may be > 0


@dataclass(frozen=True)
class _Record:
    """A directory record as stored, before it becomes a public IsoEntry."""

    record_length: int
    lba: int
    data_length: int
    flags: int
    name: str
    offset: int          # within the parent directory extent

    @property
    def is_dir(self) -> bool:
        return bool(self.flags & FLAG_DIRECTORY)

    @property
    def is_self_or_parent(self) -> bool:
        """True for the '.' (0x00) and '..' (0x01) records every directory has."""
        return self.name in ("\x00", "\x01")


# --------------------------------------------------------------------------
# Byte helpers: both-endian fields, names, paths
# --------------------------------------------------------------------------

def _both_u32(buf: bytes, offset: int, what: str) -> int:
    """Read an 8-byte both-endian u32, proving the two copies agree."""
    little = struct.unpack_from("<I", buf, offset)[0]
    big = struct.unpack_from(">I", buf, offset + 4)[0]
    _require(
        little == big,
        f"{what}: both-endian u32 disagrees (little-endian {little}, "
        f"big-endian {big}). The image is corrupt at this field; refusing to "
        f"guess which copy is right.",
    )
    return little


def _both_u16(buf: bytes, offset: int, what: str) -> int:
    """Read a 4-byte both-endian u16, proving the two copies agree."""
    little = struct.unpack_from("<H", buf, offset)[0]
    big = struct.unpack_from(">H", buf, offset + 2)[0]
    _require(
        little == big,
        f"{what}: both-endian u16 disagrees (little-endian {little}, "
        f"big-endian {big}). The image is corrupt at this field; refusing to "
        f"guess which copy is right.",
    )
    return little


def _strip_version(name: str) -> str:
    """'FOO.BIN;1' -> 'FOO.BIN'.  Directories usually carry no version."""
    return _VERSION_SUFFIX.sub("", name)


def _component_key(name: str) -> str:
    """Fold one path component for case- and version-insensitive matching.

    ISO9660 stores a bare 'FOO' with no extension as 'FOO.' on some masters, so
    a single trailing dot is folded away too; a caller asking for 'FOO' finds
    it either way.
    """
    key = _strip_version(name).upper()
    if len(key) > 1 and key.endswith("."):
        key = key[:-1]
    return key


def _normalise_query(path: str) -> List[str]:
    """Turn a user path into folded components.

    Accepts '/DATA/FOO.BIN', 'data\\foo.bin;1', and the SYSTEM.CNF form
    'cdrom0:\\SLUS_217.70;1' alike.
    """
    text = str(path).strip()
    _require(text != "", "find() needs a path inside the image, e.g. '/SYSTEM.CNF'")
    text = text.replace("\\", "/")
    device = _DEVICE_PREFIX.match(text)
    if device is not None:
        # 'cdrom0:' / 'host:' / a stray drive letter. ':' is not a legal
        # ISO9660 identifier character, so this can never eat a real name.
        text = text[device.end():]
    parts = [part for part in text.split("/") if part not in ("", ".")]
    _require(
        ".." not in parts,
        f"'{path}': '..' is not meaningful inside an image; give a path from "
        f"the volume root, e.g. '/DATA/FOO.BIN'.",
    )
    _require(parts, f"'{path}' names the volume root, not an entry inside it.")
    return [_component_key(part) for part in parts]


# --------------------------------------------------------------------------
# Addressing and bounds
# --------------------------------------------------------------------------

def extent_byte_offset(image: IsoImage, lba: int, offset_in_extent: int = 0) -> int:
    """Absolute byte offset of ``offset_in_extent`` bytes into the extent at ``lba``.

    Under the 2048-byte layout this is plain arithmetic.  Under a raw CD layout
    the user bytes of consecutive logical blocks are *not* contiguous in the
    file, so the offset has to be split into a block index and a position
    inside that block.  Callers that patch a directory record must go through
    here rather than multiplying by ``sector_size`` themselves.
    """
    _require(lba >= 0, f"negative LBA {lba}")
    _require(offset_in_extent >= 0, f"negative extent offset {offset_in_extent}")
    block, within = divmod(offset_in_extent, SECTOR_USER_BYTES)
    return (lba + block) * image.sector_size + image.data_offset + within


def check_extent(image: IsoImage, lba: int, length: int, what: str) -> None:
    """Refuse an extent that leaves the volume or the file before any seek.

    Both bounds matter and fail differently: past ``volume_blocks`` means the
    directory record disagrees with the volume descriptor, past the end of the
    file means the image is short (a trimmed rip, or a truncated download).
    """
    _require(lba >= 0, f"{what}: negative extent LBA {lba}")
    _require(length >= 0, f"{what}: negative data length {length}")
    if length == 0:
        return
    blocks = (length + SECTOR_USER_BYTES - 1) // SECTOR_USER_BYTES
    end_block = lba + blocks
    _require(
        end_block <= image.volume_blocks,
        f"{what}: extent at LBA {lba} spanning {blocks} block(s) ends at block "
        f"{end_block}, past the {image.volume_blocks} blocks the volume "
        f"declares. Refusing to read outside the volume.",
    )
    last_byte = extent_byte_offset(image, lba, length - 1) + 1
    _require(
        last_byte <= image.file_size,
        f"{what}: extent at LBA {lba} needs bytes up to {last_byte} but "
        f"{image.path} is only {image.file_size} bytes. The image is short "
        f"(trimmed or truncated) -- this file is not fully present.",
    )


# --------------------------------------------------------------------------
# File access
# --------------------------------------------------------------------------

def _open_regular(path: Path):
    """Open a real, regular file read-only.  Symlinks and devices are refused."""
    _require(
        not path.is_symlink(),
        f"Refusing to read through a symlink: {path}. Pass the real image file.",
    )
    try:
        metadata = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        raise Iso9660Error(f"No such image: {path}") from None
    except OSError as exc:
        raise Iso9660Error(f"Cannot stat {path}: {exc}") from None
    _require(
        stat.S_ISREG(metadata.st_mode),
        f"{path} is not a regular file. Pass a disc image, not a directory, "
        f"device or pipe.",
    )
    try:
        return open(path, "rb")
    except OSError as exc:
        raise Iso9660Error(f"Cannot open {path}: {exc}") from None


def _read_at(handle, offset: int, size: int, what: str) -> bytes:
    """Read exactly ``size`` bytes at ``offset`` or say precisely what is missing."""
    handle.seek(offset)
    data = handle.read(size)
    _require(
        len(data) == size,
        f"{what}: wanted {size} bytes at offset {offset} but the file ended "
        f"after {len(data)}.",
    )
    return data


def _read_block(image: IsoImage, handle, lba: int, count: int, what: str) -> bytes:
    """Read ``count`` logical blocks of *user* data starting at ``lba``."""
    if image.sector_size == SECTOR_USER_BYTES and image.data_offset == 0:
        return _read_at(handle, lba * SECTOR_USER_BYTES,
                        count * SECTOR_USER_BYTES, what)
    parts = []
    for index in range(count):
        offset = (lba + index) * image.sector_size + image.data_offset
        parts.append(_read_at(handle, offset, SECTOR_USER_BYTES, what))
    return b"".join(parts)


def _iter_extent(image: IsoImage, handle, lba: int, length: int,
                 what: str) -> Iterator[bytes]:
    """Yield an extent's bytes in bounded chunks.  Never materialises the whole."""
    remaining = length
    block = lba
    while remaining > 0:
        wanted_blocks = (remaining + SECTOR_USER_BYTES - 1) // SECTOR_USER_BYTES
        count = min(STREAM_CHUNK_SECTORS, wanted_blocks)
        buffer = _read_block(image, handle, block, count, what)
        take = min(remaining, len(buffer))
        yield buffer[:take]
        remaining -= take
        block += count


# --------------------------------------------------------------------------
# Volume descriptor
# --------------------------------------------------------------------------

def _detect_layout(handle, file_size: int, path: Path) -> Tuple[int, int]:
    """Find the sector layout by looking for 'CD001' where each one puts it."""
    probed = []
    for sector_size, data_offset in _LAYOUT_CANDIDATES:
        offset = VOLUME_DESCRIPTOR_LBA * sector_size + data_offset
        probed.append(f"{sector_size}/{data_offset} at byte {offset}")
        if offset + SECTOR_USER_BYTES > file_size:
            continue
        handle.seek(offset)
        head = handle.read(7)
        if len(head) < 7:
            continue
        if head[1:6] == STANDARD_IDENTIFIER and head[6] == 1:
            return sector_size, data_offset
    raise Iso9660Error(
        f"{path}: no ISO9660 volume descriptor found. Probed "
        + "; ".join(probed)
        + ". Supported layouts are 2048-byte logical sectors (DVD images) and "
          "2352-byte raw CD sectors in Mode 1 or Mode 2 Form 1. A 2336-byte "
          "Mode 2 rip, a compressed image (.7z/.zip/.chd), or a cue sheet "
          "instead of the .bin itself would all land here."
    )


def _find_primary_descriptor(handle, path: Path, sector_size: int,
                             data_offset: int, file_size: int) -> bytes:
    """Walk the descriptor set from LBA 16 and return the primary descriptor."""
    for index in range(MAX_VOLUME_DESCRIPTORS):
        lba = VOLUME_DESCRIPTOR_LBA + index
        offset = lba * sector_size + data_offset
        if offset + SECTOR_USER_BYTES > file_size:
            break
        handle.seek(offset)
        block = handle.read(SECTOR_USER_BYTES)
        if len(block) < SECTOR_USER_BYTES:
            break
        if block[1:6] != STANDARD_IDENTIFIER:
            break
        kind = block[0]
        if kind == DESC_PRIMARY:
            return block
        if kind == DESC_TERMINATOR:
            break
        # Boot records, supplementary (Joliet) and partition descriptors are
        # skipped: v1 reads the primary ISO9660 tree only.
    raise Iso9660Error(
        f"{path}: the volume descriptor set has no primary descriptor "
        f"(type {DESC_PRIMARY}). Only a supplementary/Joliet or boot descriptor "
        f"was found, and v1 does not read those."
    )


def _parse_root_record(block: bytes, path: Path) -> Tuple[int, int]:
    """Pull the root directory's LBA and length out of the PVD's embedded record."""
    record = block[156:156 + ROOT_RECORD_SIZE]
    _require(
        record[0] == ROOT_RECORD_SIZE,
        f"{path}: the root directory record in the volume descriptor declares "
        f"{record[0]} bytes, but ECMA-119 fixes it at {ROOT_RECORD_SIZE}.",
    )
    _require(
        record[1] == 0,
        f"{path}: the root directory carries an extended attribute record "
        f"({record[1]} block(s)). Extended attributes are out of scope for v1.",
    )
    root_lba = _both_u32(record, 2, f"{path}: root directory extent")
    root_length = _both_u32(record, 10, f"{path}: root directory length")
    _require(
        record[25] & FLAG_DIRECTORY,
        f"{path}: the root directory record is not flagged as a directory "
        f"(flags 0x{record[25]:02x}).",
    )
    _require(
        root_length > 0,
        f"{path}: the root directory declares zero length, so the volume has "
        f"no readable tree.",
    )
    return root_lba, root_length


def open_image(path: "str | Path") -> IsoImage:
    """Parse a PS2 disc image's volume header.  Reads a few kilobytes, no more."""
    image_path = Path(path)
    with _open_regular(image_path) as handle:
        file_size = os.fstat(handle.fileno()).st_size
        _require(
            file_size > 0,
            f"{image_path} is empty; there is no volume to read.",
        )
        sector_size, data_offset = _detect_layout(handle, file_size, image_path)
        block = _find_primary_descriptor(
            handle, image_path, sector_size, data_offset, file_size)

        volume_id = block[40:72].decode("latin-1").replace("\x00", " ").strip()
        volume_blocks = _both_u32(block, 80, f"{image_path}: volume space size")
        block_size = _both_u16(block, 128, f"{image_path}: logical block size")
        _require(
            block_size == SECTOR_USER_BYTES,
            f"{image_path}: logical block size is {block_size}, not "
            f"{SECTOR_USER_BYTES}. Every known PS2 image uses "
            f"{SECTOR_USER_BYTES}-byte blocks; refusing to guess the addressing.",
        )
        _require(
            block[881] in (1, 2),
            f"{image_path}: file structure version {block[881]} is not 1 "
            f"(ECMA-119) or 2; refusing to parse an unknown structure.",
        )
        _require(
            volume_blocks >= 1,
            f"{image_path}: the volume declares {volume_blocks} blocks.",
        )
        root_lba, root_length = _parse_root_record(block, image_path)

        image = IsoImage(
            path=image_path,
            sector_size=sector_size,
            data_offset=data_offset,
            volume_id=volume_id,
            volume_blocks=volume_blocks,
            block_size=block_size,
            root_lba=root_lba,
            root_length=root_length,
            file_size=file_size,
            slack_bytes=file_size - volume_blocks * sector_size,
        )
        check_extent(image, root_lba, root_length, f"{image_path}: root directory")
        return image


# --------------------------------------------------------------------------
# Directory records
# --------------------------------------------------------------------------

def _parse_directory(image: IsoImage, handle, lba: int, length: int,
                     where: str) -> List[_Record]:
    """Parse one directory extent into its records, in stored order.

    ISO9660 forbids a directory record from straddling a logical block
    boundary; the tail of a block is zero-padded and a zero length byte means
    "skip to the next block".  Getting that wrong shifts every subsequent
    ``record_offset``, which is exactly the off-by-one that would make a writer
    patch the wrong field, so a record that *does* straddle is treated as
    corruption rather than parsed through.
    """
    check_extent(image, lba, length, f"{where}: directory extent")
    _require(
        length <= MAX_DIRECTORY_BYTES,
        f"{where}: directory extent declares {length} bytes, above the "
        f"{MAX_DIRECTORY_BYTES}-byte sanity cap. Refusing to read it.",
    )
    blocks = (length + SECTOR_USER_BYTES - 1) // SECTOR_USER_BYTES
    data = _read_block(image, handle, lba, blocks, f"{where}: directory extent")

    records: List[_Record] = []
    offset = 0
    while offset < length:
        block_remaining = SECTOR_USER_BYTES - (offset % SECTOR_USER_BYTES)
        record_length = data[offset]
        if record_length == 0:
            # Padding to the next logical block.
            offset += block_remaining
            continue
        _require(
            record_length >= DIRECTORY_RECORD_MIN,
            f"{where}: directory record at offset {offset} declares "
            f"{record_length} bytes, below the {DIRECTORY_RECORD_MIN}-byte "
            f"minimum. The directory extent is corrupt.",
        )
        _require(
            record_length <= block_remaining,
            f"{where}: directory record at offset {offset} declares "
            f"{record_length} bytes but only {block_remaining} remain in its "
            f"logical block. ISO9660 forbids a record straddling a block "
            f"boundary; the directory extent is corrupt.",
        )
        record = data[offset:offset + record_length]

        extended_attribute_blocks = record[1]
        name_length = record[32]
        _require(
            DIRECTORY_RECORD_MIN + name_length <= record_length,
            f"{where}: directory record at offset {offset} declares a "
            f"{name_length}-byte name that does not fit its {record_length}-byte "
            f"record.",
        )
        name = record[33:33 + name_length].decode("latin-1")
        label = f"{where.rstrip('/')}/{_strip_version(name).upper()}"

        flags = record[25]
        _require(
            not flags & FLAG_MULTI_EXTENT,
            f"{label}: this file is stored as multiple extents (file flags "
            f"0x{flags:02x}). Multi-extent files are out of scope for v1; "
            f"refusing to report a partial extent as the whole file.",
        )
        _require(
            extended_attribute_blocks == 0,
            f"{label}: the record carries a {extended_attribute_blocks}-block "
            f"extended attribute record, which would shift the data start. "
            f"Extended attributes are out of scope for v1.",
        )

        record_lba = _both_u32(record, 2, f"{label}: extent location")
        data_length = _both_u32(record, 10, f"{label}: data length")
        records.append(
            _Record(
                record_length=record_length,
                lba=record_lba,
                data_length=data_length,
                flags=flags,
                name=name,
                offset=offset,
            )
        )
        offset += record_length
    return records


def _to_entry(record: _Record, parent_lba: int, prefix: str) -> IsoEntry:
    return IsoEntry(
        path=prefix + "/" + _strip_version(record.name).upper(),
        raw_name=record.name,
        lba=record.lba,
        length=record.data_length,
        is_dir=record.is_dir,
        parent_lba=parent_lba,
        record_offset=record.offset,
    )


def _walk(image: IsoImage, handle, lba: int, length: int, prefix: str,
          depth: int, seen: set, counter: List[int]) -> Iterator[IsoEntry]:
    """Depth-first pre-order walk in stored (on-disc) record order."""
    _require(
        depth <= MAX_DIRECTORY_DEPTH,
        f"{prefix or '/'}: directory nesting passed {MAX_DIRECTORY_DEPTH} "
        f"levels. The tree is cyclic or corrupt.",
    )
    key = (lba, length)
    _require(
        key not in seen,
        f"{prefix or '/'}: directory extent at LBA {lba} is reached twice. "
        f"The tree is cyclic; refusing to loop.",
    )
    seen.add(key)

    for record in _parse_directory(image, handle, lba, length, prefix or "/"):
        if record.is_self_or_parent:
            continue
        counter[0] += 1
        _require(
            counter[0] <= MAX_ENTRIES,
            f"the image declares more than {MAX_ENTRIES} entries; refusing to "
            f"enumerate what is almost certainly a corrupt tree.",
        )
        entry = _to_entry(record, lba, prefix)
        yield entry
        if record.is_dir:
            for child in _walk(image, handle, record.lba, record.data_length,
                               entry.path, depth + 1, seen, counter):
                yield child


def iter_entries(image: IsoImage) -> Iterator[IsoEntry]:
    """Yield every file and directory below the root, recursively.

    Order is deterministic: records come out in the order the directory extent
    stores them (which on real masters is *not* alphabetical), and a directory's
    children immediately follow it.  The volume root itself is not yielded.
    """
    with _open_regular(image.path) as handle:
        for entry in _walk(image, handle, image.root_lba, image.root_length,
                           "", 1, set(), [0]):
            yield entry


def find(image: IsoImage, path: str) -> "IsoEntry | None":
    """Look one entry up by path, case-insensitively, with ';1' optional.

    Descends component by component instead of walking the whole tree, so it
    costs one directory read per level.  Returns ``None`` when the path is not
    present, or when a non-final component turns out to be a file.
    """
    components = _normalise_query(path)
    with _open_regular(image.path) as handle:
        lba, length, prefix = image.root_lba, image.root_length, ""
        for index, wanted in enumerate(components):
            match = None
            for record in _parse_directory(image, handle, lba, length,
                                           prefix or "/"):
                if record.is_self_or_parent:
                    continue
                if _component_key(record.name) == wanted:
                    match = record
                    break
            if match is None:
                return None
            entry = _to_entry(match, lba, prefix)
            if index == len(components) - 1:
                return entry
            if not match.is_dir:
                return None
            lba, length, prefix = match.lba, match.data_length, entry.path
    return None


# --------------------------------------------------------------------------
# File content
# --------------------------------------------------------------------------

def _require_readable_file(entry: IsoEntry) -> None:
    _require(
        not entry.is_dir,
        f"{entry.path} is a directory; it has no file content to read.",
    )


def iter_file_chunks(image: IsoImage, entry: IsoEntry,
                     handle=None) -> Iterator[bytes]:
    """Stream one file's bytes in bounded chunks.

    Pass ``handle`` to reuse an already-open image; otherwise one is opened and
    closed around the iteration.
    """
    _require_readable_file(entry)
    check_extent(image, entry.lba, entry.length, entry.path)
    if entry.length == 0:
        return
    if handle is not None:
        for chunk in _iter_extent(image, handle, entry.lba, entry.length,
                                  entry.path):
            yield chunk
        return
    with _open_regular(image.path) as own:
        for chunk in _iter_extent(image, own, entry.lba, entry.length,
                                  entry.path):
            yield chunk


def read_file(image: IsoImage, entry: IsoEntry) -> bytes:
    """Return one file's full content.

    Reads in chunks, but the result is a single ``bytes``, so it is capped at
    ``MAX_READ_FILE_BYTES``.  For the multi-hundred-megabyte ``.DAT`` blobs on
    these discs use ``extract_file`` (streams to disk) or ``iter_file_chunks``.
    """
    _require_readable_file(entry)
    _require(
        entry.length <= MAX_READ_FILE_BYTES,
        f"{entry.path} is {entry.length} bytes, above the "
        f"{MAX_READ_FILE_BYTES}-byte in-memory cap. Use extract_file() to "
        f"stream it to disk, or iter_file_chunks() to process it in pieces.",
    )
    parts = list(iter_file_chunks(image, entry))
    return b"".join(parts)


def sha256_of(image: IsoImage, entry: IsoEntry) -> str:
    """SHA-256 of one file's content, computed streaming."""
    digest = hashlib.sha256()
    for chunk in iter_file_chunks(image, entry):
        digest.update(chunk)
    return digest.hexdigest()


def extract_file(image: IsoImage, entry: IsoEntry, destination: "str | Path") -> dict:
    """Stream one file out to a new path.  Never overwrites, never follows a link."""
    # Validate the source before touching the filesystem, so a refused entry
    # never creates and then removes an output file.
    _require_readable_file(entry)
    check_extent(image, entry.lba, entry.length, entry.path)

    target = Path(destination)
    _require(
        not target.is_symlink(),
        f"Refusing to write through a symlink: {target}.",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o644,
        )
    except FileExistsError:
        raise Iso9660Error(
            f"Refusing to overwrite an existing file: {target}. Choose a name "
            f"that does not exist yet."
        ) from None
    except OSError as exc:
        raise Iso9660Error(f"Cannot create {target}: {exc}") from None

    digest = hashlib.sha256()
    written = 0
    try:
        with os.fdopen(descriptor, "wb") as sink:
            for chunk in iter_file_chunks(image, entry):
                sink.write(chunk)
                digest.update(chunk)
                written += len(chunk)
    except BaseException:
        try:
            os.unlink(target)
        except OSError:
            pass
        raise
    _require(
        written == entry.length,
        f"{entry.path}: wrote {written} bytes but the record declares "
        f"{entry.length}.",
    )
    return {
        "iso_path": entry.path,
        "output": str(target),
        "bytes": written,
        "sha256": digest.hexdigest(),
    }


# --------------------------------------------------------------------------
# Boot identity
# --------------------------------------------------------------------------

def _parse_system_cnf(text: str) -> dict:
    """Fold SYSTEM.CNF into upper-cased keys, tolerating CRLF and loose spacing."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().upper()
        if key:
            values[key] = value.strip()
    return values


def _boot_file_name(boot2: str) -> Optional[str]:
    """'cdrom0:\\SLUS_217.70;1' -> 'SLUS_217.70'."""
    text = boot2.strip()
    if not text:
        return None
    text = text.replace("\\", "/")
    device = _DEVICE_PREFIX.match(text)
    if device is not None:
        text = text[device.end():]
    name = text.rsplit("/", 1)[-1]
    name = _strip_version(name).strip()
    return name or None


_SERIAL_SHAPE = re.compile(r"^([A-Za-z]{4})_(\d{3})\.(\d{2})$")


def _serial_of(boot_file: str) -> str:
    """'SLUS_209.19' -> 'SLUS-20919', the form every catalogue spells.

    The disc stores the serial as an ISO9660 level-1 file name.  The hyphen is
    illegal there, so it became an underscore, and the 8.3 name limit forced a
    dot into the digit run.  Both are artefacts of the file system, not of the
    serial: PCSX2, redump and this repository's own capability registry and
    ``nfl2k5_ps2_replacement_pack_audit.SERIAL`` all write ``SLUS-20919``.  An
    earlier version emitted ``SLUS-209.19`` here, which silently failed every
    join against them.

    A boot file outside the ``SXXX_NNN.NN`` shape falls back to the plain
    underscore-to-hyphen rule, so an unusual mod disc still reports something
    rather than ``None``.
    """
    match = _SERIAL_SHAPE.match(boot_file)
    if match is not None:
        prefix, high, low = match.groups()
        return f"{prefix.upper()}-{high}{low}"
    return boot_file.replace("_", "-", 1)


def boot_identity(image: IsoImage) -> dict:
    """Recover the disc's identity from ``/SYSTEM.CNF``.

    Returns exactly::

        {"system_cnf": <raw text>, "boot2": "cdrom0:\\\\SLUS_217.70;1",
         "boot_file": "SLUS_217.70", "serial": "SLUS-21770",
         "boot_sha256": <hex>, "boot_size": int}

    ``boot_file`` is the name exactly as the disc spells it; ``serial`` is the
    catalogue form (see ``_serial_of``), which is what the capability registry
    and the replacement-pack audit key on.

    A missing ``SYSTEM.CNF`` raises -- without it there is no identity to
    report.  Anything *inside* the file that is missing or malformed degrades to
    ``None`` on that key rather than raising, so a mod disc with an unusual
    ``SYSTEM.CNF`` still inspects.
    """
    entry = find(image, "/SYSTEM.CNF")
    _require(
        entry is not None,
        f"{image.path}: no /SYSTEM.CNF in the volume root. Every PS2 disc "
        f"carries one; this image is not a PS2 title (or the wrong volume "
        f"descriptor was parsed).",
    )
    assert entry is not None  # for type checkers; _require already raised
    _require(
        not entry.is_dir,
        f"{image.path}: /SYSTEM.CNF is a directory, not a file.",
    )
    _require(
        entry.length <= MAX_SYSTEM_CNF_BYTES,
        f"{image.path}: /SYSTEM.CNF is {entry.length} bytes, far past the "
        f"{MAX_SYSTEM_CNF_BYTES}-byte cap for a boot config. Refusing to read it.",
    )
    raw = read_file(image, entry)
    text = raw.decode("latin-1")
    values = _parse_system_cnf(text)

    boot2 = values.get("BOOT2") or values.get("BOOT")
    boot_file = _boot_file_name(boot2) if boot2 else None
    serial = _serial_of(boot_file) if boot_file else None

    boot_sha256 = None
    boot_size = None
    if boot2:
        try:
            boot_entry = find(image, boot2)
        except Iso9660Error:
            boot_entry = None
        if boot_entry is not None and not boot_entry.is_dir:
            boot_sha256 = sha256_of(image, boot_entry)
            boot_size = boot_entry.length

    return {
        "system_cnf": text,
        "boot2": boot2,
        "boot_file": boot_file,
        "serial": serial,
        "boot_sha256": boot_sha256,
        "boot_size": boot_size,
    }


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def summarise(image: IsoImage) -> dict:
    """A JSON-safe volume summary: header fields plus tree counts."""
    files = 0
    directories = 0
    declared_bytes = 0
    for entry in iter_entries(image):
        if entry.is_dir:
            directories += 1
        else:
            files += 1
            declared_bytes += entry.length
    return {
        "schema": "ps2_iso9660_inspect/v1",
        "path": str(image.path),
        "sector_size": image.sector_size,
        "data_offset": image.data_offset,
        "layout": ("2048-byte logical sectors" if image.sector_size == SECTOR_USER_BYTES
                   else f"raw CD, {image.sector_size}-byte sectors, "
                        f"payload at +{image.data_offset}"),
        "volume_id": image.volume_id,
        "volume_blocks": image.volume_blocks,
        "block_size": image.block_size,
        "root_lba": image.root_lba,
        "root_length": image.root_length,
        "file_size": image.file_size,
        "slack_bytes": image.slack_bytes,
        "directories": directories,
        "files": files,
        "declared_file_bytes": declared_bytes,
    }


def _print_report(image: IsoImage, show_tree: bool) -> None:
    summary = summarise(image)
    print(f"image           {summary['path']}")
    print(f"layout          {summary['layout']}")
    print(f"volume id       {summary['volume_id']!r}")
    print(f"volume blocks   {summary['volume_blocks']} "
          f"({summary['volume_blocks'] * image.sector_size} bytes)")
    print(f"block size      {summary['block_size']}")
    print(f"root            LBA {summary['root_lba']}, "
          f"{summary['root_length']} bytes")
    print(f"file size       {summary['file_size']}")
    slack = summary["slack_bytes"]
    note = "" if slack >= 0 else "  (image is shorter than the volume declares)"
    print(f"slack past vol  {slack}{note}")
    print(f"tree            {summary['directories']} directories, "
          f"{summary['files']} files, "
          f"{summary['declared_file_bytes']} declared bytes")

    if show_tree:
        print()
        for entry in iter_entries(image):
            kind = "dir " if entry.is_dir else "file"
            print(f"  {kind} {entry.path:<44} lba={entry.lba:<9} "
                  f"len={entry.length:<12} "
                  f"rec={entry.parent_lba}+{entry.record_offset}")

    print()
    try:
        identity = boot_identity(image)
    except Iso9660Error as exc:
        print(f"boot identity   unavailable: {exc}")
        return
    print(f"BOOT2           {identity['boot2']}")
    print(f"boot file       {identity['boot_file']}")
    print(f"serial          {identity['serial']}")
    print(f"boot size       {identity['boot_size']}")
    print(f"boot sha256     {identity['boot_sha256']}")


# --------------------------------------------------------------------------
# Synthetic images, for the self-test (no game data required)
# --------------------------------------------------------------------------

# A fixed timestamp keeps synthetic fixtures byte-reproducible.  ISO9660's
# 7-byte form is: years since 1900, month, day, hour, minute, second, and the
# offset from GMT in 15-minute steps.
_FIXED_RECORD_TIME = bytes([124, 1, 1, 0, 0, 0, 0])       # 2024-01-01 00:00 GMT
_FIXED_VOLUME_TIME = b"2024010100000000" + bytes([0])     # 17-byte decimal form


def _directory_record_bytes(name: bytes, lba: int, length: int,
                            is_dir: bool) -> bytes:
    record_length = DIRECTORY_RECORD_MIN + len(name)
    if record_length % 2:
        record_length += 1
    record = bytearray(record_length)
    record[0] = record_length
    record[1] = 0
    struct.pack_into("<I", record, 2, lba)
    struct.pack_into(">I", record, 6, lba)
    struct.pack_into("<I", record, 10, length)
    struct.pack_into(">I", record, 14, length)
    record[18:25] = _FIXED_RECORD_TIME
    record[25] = FLAG_DIRECTORY if is_dir else 0
    struct.pack_into("<H", record, 28, 1)
    struct.pack_into(">H", record, 30, 1)
    record[32] = len(name)
    record[33:33 + len(name)] = name
    return bytes(record)


def _pack_directory(records: Sequence[bytes]) -> bytes:
    """Lay records out without letting one straddle a logical block."""
    out = bytearray()
    for record in records:
        room = SECTOR_USER_BYTES - (len(out) % SECTOR_USER_BYTES)
        if len(record) > room:
            out.extend(bytes(room))
        out.extend(record)
    return bytes(out)


def _build_synthetic_iso(slack: int = 0, sector_size: int = SECTOR_USER_BYTES,
                         data_offset: int = 0) -> bytes:
    """A minimal but structurally valid PS2-shaped ISO9660 volume.

    Layout: 16 blank system blocks, PVD, terminator, path tables, root
    directory, one subdirectory, then file data.
    """
    root_lba = 20
    sub_lba = 21
    path_table_l_lba = 18
    path_table_m_lba = 19

    files = [
        (b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_217.70;1\r\nVER = 1.00\r\n"
                          b"VMODE = NTSC\r\n"),
        (b"SLUS_217.70;1", b"ELF" + bytes(4093)),
        (b"EMPTY.BIN;1", b""),
    ]
    sub_files = [
        (b"FOO.BIN;1", bytes(range(256)) * 12),
        (b"BAR.DAT;1", b"bar" * 1000),
    ]

    data_lba = 22
    placed = []
    for name, blob in files + sub_files:
        blocks = max(1, (len(blob) + SECTOR_USER_BYTES - 1) // SECTOR_USER_BYTES)
        placed.append((name, blob, data_lba))
        data_lba += blocks
    by_name = {name: (blob, lba) for name, blob, lba in placed}

    def child(name: bytes) -> bytes:
        blob, lba = by_name[name]
        return _directory_record_bytes(name, lba, len(blob), False)

    sub_records = [
        _directory_record_bytes(b"\x00", sub_lba, 0, True),
        _directory_record_bytes(b"\x01", root_lba, 0, True),
    ] + [child(name) for name, _ in sub_files]
    sub_dir = _pack_directory(sub_records)
    sub_length = len(sub_dir)

    root_records = [
        _directory_record_bytes(b"\x00", root_lba, 0, True),
        _directory_record_bytes(b"\x01", root_lba, 0, True),
        _directory_record_bytes(b"DATA", sub_lba, sub_length, True),
    ] + [child(name) for name, _ in files]
    root_dir = _pack_directory(root_records)
    root_length = len(root_dir)

    # Fix up the self/parent records now that the lengths are known.
    root_dir = bytearray(root_dir)
    struct.pack_into("<I", root_dir, 10, root_length)
    struct.pack_into(">I", root_dir, 14, root_length)
    offset = root_dir[0]
    struct.pack_into("<I", root_dir, offset + 10, root_length)
    struct.pack_into(">I", root_dir, offset + 14, root_length)
    root_dir = bytes(root_dir)

    sub_dir = bytearray(sub_dir)
    struct.pack_into("<I", sub_dir, 10, sub_length)
    struct.pack_into(">I", sub_dir, 14, sub_length)
    offset = sub_dir[0]
    struct.pack_into("<I", sub_dir, offset + 10, root_length)
    struct.pack_into(">I", sub_dir, offset + 14, root_length)
    sub_dir = bytes(sub_dir)

    # Path tables (written for structural validity; the reader never uses them).
    def path_table(endian: str) -> bytes:
        table = bytearray()
        for identifier, lba, parent in ((b"\x00", root_lba, 1),
                                        (b"DATA", sub_lba, 1)):
            table.append(len(identifier))
            table.append(0)
            table.extend(struct.pack(endian + "I", lba))
            table.extend(struct.pack(endian + "H", parent))
            table.extend(identifier)
            if len(identifier) % 2:
                table.append(0)
        return bytes(table)

    table_l = path_table("<")
    table_m = path_table(">")

    total_blocks = data_lba

    pvd = bytearray(SECTOR_USER_BYTES)
    pvd[0] = DESC_PRIMARY
    pvd[1:6] = STANDARD_IDENTIFIER
    pvd[6] = 1
    pvd[8:40] = b"PLAYSTATION".ljust(32)
    pvd[40:72] = b"".ljust(32)                       # blank, as retail ships it
    struct.pack_into("<I", pvd, 80, total_blocks)
    struct.pack_into(">I", pvd, 84, total_blocks)
    struct.pack_into("<H", pvd, 120, 1)
    struct.pack_into(">H", pvd, 122, 1)
    struct.pack_into("<H", pvd, 124, 1)
    struct.pack_into(">H", pvd, 126, 1)
    struct.pack_into("<H", pvd, 128, SECTOR_USER_BYTES)
    struct.pack_into(">H", pvd, 130, SECTOR_USER_BYTES)
    struct.pack_into("<I", pvd, 132, len(table_l))
    struct.pack_into(">I", pvd, 136, len(table_l))
    struct.pack_into("<I", pvd, 140, path_table_l_lba)
    struct.pack_into(">I", pvd, 148, path_table_m_lba)
    pvd[156:156 + ROOT_RECORD_SIZE] = _directory_record_bytes(
        b"\x00", root_lba, root_length, True)
    for start in (190, 318, 446, 574):
        pvd[start:start + 128] = b"".ljust(128)
    for start in (702, 739, 776):
        pvd[start:start + 37] = b"".ljust(37)
    for start in (813, 830, 847, 864):
        pvd[start:start + 17] = _FIXED_VOLUME_TIME
    pvd[881] = 1

    terminator = bytearray(SECTOR_USER_BYTES)
    terminator[0] = DESC_TERMINATOR
    terminator[1:6] = STANDARD_IDENTIFIER
    terminator[6] = 1

    blocks = {
        16: bytes(pvd),
        17: bytes(terminator),
        path_table_l_lba: table_l,
        path_table_m_lba: table_m,
        root_lba: root_dir,
        sub_lba: sub_dir,
    }
    for name, blob, lba in placed:
        blocks[lba] = blob

    def user_block(index: int) -> bytes:
        blob = blocks.get(index, b"")
        return blob[:SECTOR_USER_BYTES].ljust(SECTOR_USER_BYTES, b"\x00")

    # Multi-block file payloads spill into the following blocks.
    spill = {}
    for name, blob, lba in placed:
        for step in range(1, (len(blob) + SECTOR_USER_BYTES - 1)
                          // SECTOR_USER_BYTES):
            spill[lba + step] = blob[step * SECTOR_USER_BYTES:
                                     (step + 1) * SECTOR_USER_BYTES]
    for index, blob in spill.items():
        blocks.setdefault(index, blob)

    out = bytearray()
    for index in range(total_blocks):
        payload = user_block(index)
        if sector_size == SECTOR_USER_BYTES:
            out.extend(payload)
            continue
        # Raw CD sector: sync, header (mode 2), subheader, user bytes, then a
        # zeroed EDC/ECC field.  The reader is pure addressing and never
        # validates EDC/ECC, so the fixture does not fake one.
        minute, rest = divmod(index + 150, 60 * 75)
        second, frame = divmod(rest, 75)

        def bcd(value: int) -> int:
            return ((value // 10) << 4) | (value % 10)

        sector = bytearray(RAW_SECTOR_BYTES)
        sector[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"
        sector[12:16] = bytes([bcd(minute), bcd(second), bcd(frame), 2])
        sector[16:24] = bytes([0, 0, 8, 0, 0, 0, 8, 0])
        sector[data_offset:data_offset + SECTOR_USER_BYTES] = payload
        out.extend(sector)
    out.extend(bytes(slack))
    return bytes(out)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------

def selftest(tmp: "Path | None" = None) -> int:
    """Prove the reader against synthetic images.  Needs no disc, no network."""
    import tempfile

    def check(condition: object, message: str) -> None:
        if not condition:
            raise Iso9660Error(f"selftest: {message}")

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        root = Path(work)

        # -- 2048-byte layout, with trailing slack ------------------------
        plain = root / "plain.iso"
        plain.write_bytes(_build_synthetic_iso(slack=18432))
        image = open_image(plain)
        check(image.sector_size == SECTOR_USER_BYTES, "2048 layout not detected")
        check(image.data_offset == 0, "2048 layout must have data_offset 0")
        check(image.block_size == SECTOR_USER_BYTES, "block size")
        check(image.volume_id == "", "retail-style blank volume id must fold to ''")
        check(image.slack_bytes == 18432, f"slack {image.slack_bytes} != 18432")
        check(
            image.file_size == image.volume_blocks * image.sector_size + 18432,
            "slack must be file_size - volume_blocks * sector_size",
        )

        entries = list(iter_entries(image))
        paths = [entry.path for entry in entries]
        expected = [
            "/DATA", "/DATA/FOO.BIN", "/DATA/BAR.DAT",
            "/SYSTEM.CNF", "/SLUS_217.70", "/EMPTY.BIN",
        ]
        check(paths == expected, f"tree order {paths} != {expected}")
        check(
            list(iter_entries(image)) == entries,
            "iter_entries must be deterministic across calls",
        )

        # Directories carry no ';1'; files keep theirs in raw_name.
        by_path = {entry.path: entry for entry in entries}
        check(by_path["/DATA"].raw_name == "DATA", "directory raw_name")
        check(by_path["/SYSTEM.CNF"].raw_name == "SYSTEM.CNF;1", "file raw_name")
        check(by_path["/DATA"].is_dir, "/DATA must be a directory")
        check(not by_path["/SYSTEM.CNF"].is_dir, "/SYSTEM.CNF must be a file")

        # parent_lba + record_offset must land exactly on the record, because a
        # writer patches the length field at +10 of it.  Re-read from the raw
        # bytes and confirm the both-endian length there is this entry's length.
        raw = plain.read_bytes()
        for entry in entries:
            base = extent_byte_offset(image, entry.parent_lba, entry.record_offset)
            record = raw[base:base + 33]
            check(record[0] >= DIRECTORY_RECORD_MIN,
                  f"{entry.path}: record_offset does not point at a record")
            little = struct.unpack_from("<I", record, 10)[0]
            big = struct.unpack_from(">I", record, 14)[0]
            check(little == entry.length and big == entry.length,
                  f"{entry.path}: length at record_offset is {little}/{big}, "
                  f"not {entry.length}")
            name_length = record[32]
            stored = raw[base + 33:base + 33 + name_length].decode("latin-1")
            check(stored == entry.raw_name,
                  f"{entry.path}: name at record_offset is {stored!r}")

        # -- find(): case, version suffix, separators, device prefix ------
        target = by_path["/DATA/FOO.BIN"]
        for query in ("/DATA/FOO.BIN", "/data/foo.bin", "DATA/FOO.BIN;1",
                      "\\DATA\\FOO.BIN", "/DATA//FOO.BIN;9",
                      "cdrom0:\\DATA\\FOO.BIN;1"):
            found = find(image, query)
            check(found == target, f"find({query!r}) returned {found}")
        check(find(image, "/NOPE.BIN") is None, "missing path must return None")
        check(find(image, "/SYSTEM.CNF/INSIDE") is None,
              "descending through a file must return None")

        # -- content -----------------------------------------------------
        foo = read_file(image, target)
        check(foo == bytes(range(256)) * 12, "read_file returned wrong bytes")
        check(len(foo) == target.length, "read_file length")
        check(sha256_of(image, target) == hashlib.sha256(foo).hexdigest(),
              "sha256_of disagrees with read_file")
        check(sha256_of(image, target) == sha256_of(image, target),
              "sha256_of must be stable")
        empty = by_path["/EMPTY.BIN"]
        check(read_file(image, empty) == b"", "zero-length file must read empty")
        check(sha256_of(image, empty) == hashlib.sha256(b"").hexdigest(),
              "zero-length sha256")
        bar = find(image, "/data/bar.dat")
        check(bar is not None and read_file(image, bar) == b"bar" * 1000,
              "multi-block file content")

        try:
            read_file(image, by_path["/DATA"])
        except Iso9660Error:
            pass
        else:
            raise Iso9660Error("selftest: reading a directory must be refused")

        # -- extract_file ------------------------------------------------
        out = root / "extracted" / "FOO.BIN"
        report = extract_file(image, target, out)
        check(out.read_bytes() == foo, "extract_file content")
        check(report["sha256"] == sha256_of(image, target), "extract_file sha256")
        try:
            extract_file(image, target, out)
        except Iso9660Error:
            pass
        else:
            raise Iso9660Error("selftest: extract must refuse to overwrite")

        # -- boot identity -----------------------------------------------
        identity = boot_identity(image)
        check(set(identity) == {"system_cnf", "boot2", "boot_file", "serial",
                                "boot_sha256", "boot_size"},
              f"boot_identity keys {sorted(identity)}")
        check(identity["boot2"] == "cdrom0:\\SLUS_217.70;1", identity["boot2"])
        check(identity["boot_file"] == "SLUS_217.70", str(identity["boot_file"]))
        check(identity["serial"] == "SLUS-21770", str(identity["serial"]))
        check(_serial_of("SLUS_209.19") == "SLUS-20919", "2K5 serial shape")
        check(_serial_of("SLES_502.10") == "SLES-50210", "PAL serial shape")
        check(_serial_of("MODDISC") == "MODDISC", "non-serial boot name passes through")
        check(_serial_of("MY_BOOT.ELF") == "MY-BOOT.ELF", "fallback underscore rule")
        check(identity["boot_size"] == 4096, str(identity["boot_size"]))
        check(identity["boot_sha256"] ==
              hashlib.sha256(b"ELF" + bytes(4093)).hexdigest(), "boot sha256")
        check("\r\n" in identity["system_cnf"], "system_cnf must be raw text")

        # -- raw CD (2352 / Mode 2 Form 1) --------------------------------
        rawcd = root / "raw.bin"
        rawcd.write_bytes(_build_synthetic_iso(
            sector_size=RAW_SECTOR_BYTES, data_offset=RAW_MODE2_FORM1_OFFSET))
        raw_image = open_image(rawcd)
        check(raw_image.sector_size == RAW_SECTOR_BYTES, "raw CD sector size")
        check(raw_image.data_offset == RAW_MODE2_FORM1_OFFSET, "raw CD offset")
        check(raw_image.block_size == SECTOR_USER_BYTES, "raw CD block size")
        check([entry.path for entry in iter_entries(raw_image)] == expected,
              "raw CD tree must match the 2048 tree")
        raw_target = find(raw_image, "/DATA/FOO.BIN")
        check(raw_target is not None and read_file(raw_image, raw_target) == foo,
              "raw CD content must match")
        check(boot_identity(raw_image)["serial"] == "SLUS-21770",
              "raw CD boot identity")
        check(raw_image.slack_bytes == 0, "raw CD slack")

        # -- both-endian disagreement is corruption ------------------------
        corrupt = root / "corrupt.iso"
        payload = bytearray(plain.read_bytes())
        # Flip the big-endian copy of the volume space size.
        payload[16 * SECTOR_USER_BYTES + 84] ^= 0xFF
        corrupt.write_bytes(bytes(payload))
        try:
            open_image(corrupt)
        except Iso9660Error as exc:
            check("both-endian" in str(exc), f"unexpected message: {exc}")
        else:
            raise Iso9660Error(
                "selftest: a both-endian disagreement must raise")

        # A disagreement inside a directory record must raise too.
        record_base = extent_byte_offset(image, target.parent_lba,
                                         target.record_offset)
        payload = bytearray(plain.read_bytes())
        payload[record_base + 14] ^= 0xFF
        corrupt2 = root / "corrupt2.iso"
        corrupt2.write_bytes(bytes(payload))
        try:
            list(iter_entries(open_image(corrupt2)))
        except Iso9660Error as exc:
            check("both-endian" in str(exc), f"unexpected message: {exc}")
        else:
            raise Iso9660Error(
                "selftest: a corrupt record length must raise")

        # -- out-of-bounds extent ------------------------------------------
        payload = bytearray(plain.read_bytes())
        struct.pack_into("<I", payload, record_base + 2, 10 ** 6)
        struct.pack_into(">I", payload, record_base + 6, 10 ** 6)
        oob = root / "oob.iso"
        oob.write_bytes(bytes(payload))
        oob_image = open_image(oob)
        oob_entry = find(oob_image, "/DATA/FOO.BIN")
        check(oob_entry is not None, "the out-of-bounds record still parses")
        try:
            read_file(oob_image, oob_entry)
        except Iso9660Error as exc:
            check("past the" in str(exc), f"unexpected message: {exc}")
        else:
            raise Iso9660Error(
                "selftest: an extent past the volume must be refused")

        # -- a file that is not an image ------------------------------------
        junk = root / "junk.iso"
        junk.write_bytes(b"not a disc" * 5000)
        try:
            open_image(junk)
        except Iso9660Error as exc:
            check("volume descriptor" in str(exc), f"unexpected message: {exc}")
        else:
            raise Iso9660Error("selftest: junk must be refused")

        # -- symlinks and directories ----------------------------------------
        try:
            open_image(root)
        except Iso9660Error:
            pass
        else:
            raise Iso9660Error("selftest: a directory must be refused")
        link = root / "link.iso"
        try:
            link.symlink_to(plain)
        except (OSError, NotImplementedError):
            pass                       # no symlink privilege (Windows runners)
        else:
            try:
                open_image(link)
            except Iso9660Error as exc:
                check("symlink" in str(exc), f"unexpected message: {exc}")
            else:
                raise Iso9660Error("selftest: a symlink must be refused")

    print(f"PS2_ISO9660_SELFTEST_PASS entries={len(expected)} "
          f"layouts=2048+2352 slack=18432 serial=SLUS-21770")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: "Sequence[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--inspect", type=Path, metavar="IMAGE",
                        help="print the volume summary, entry tree and boot identity")
    parser.add_argument("--image", type=Path,
                        help="the disc image other operations act on")
    parser.add_argument("--list", action="store_true",
                        help="print the entry tree only")
    parser.add_argument("--extract", metavar="ISO_PATH",
                        help="path inside the image to extract, e.g. /SYSTEM.CNF")
    parser.add_argument("--output", type=Path,
                        help="where --extract writes; must not exist yet")
    parser.add_argument("--sha256", metavar="ISO_PATH",
                        help="stream-hash one file inside the image")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON instead of a text report")
    parser.add_argument("--selftest", action="store_true",
                        help="verify the reader against synthetic images; no disc needed")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    source = args.image or args.inspect
    if source is None:
        parser.error("give --inspect IMAGE, or --image IMAGE with an action")
    if args.extract and not args.output:
        parser.error("--extract needs --output (the file to write)")
    if args.output and not args.extract:
        parser.error("--output only makes sense with --extract")

    image = open_image(source)

    did_something = False
    if args.inspect is not None:
        did_something = True
        if args.json:
            report = summarise(image)
            report["entries"] = [
                {
                    "path": entry.path,
                    "raw_name": entry.raw_name,
                    "lba": entry.lba,
                    "length": entry.length,
                    "is_dir": entry.is_dir,
                    "parent_lba": entry.parent_lba,
                    "record_offset": entry.record_offset,
                }
                for entry in iter_entries(image)
            ]
            try:
                report["boot"] = boot_identity(image)
            except Iso9660Error as exc:
                report["boot"] = {"error": str(exc)}
            print(json.dumps(report, indent=2))
        else:
            _print_report(image, show_tree=True)

    if args.list:
        did_something = True
        for entry in iter_entries(image):
            kind = "dir " if entry.is_dir else "file"
            print(f"{kind} {entry.path:<48} lba={entry.lba:<9} "
                  f"len={entry.length}")

    if args.sha256:
        did_something = True
        entry = find(image, args.sha256)
        if entry is None:
            raise Iso9660Error(f"{args.sha256}: not present in {image.path}")
        print(f"{sha256_of(image, entry)}  {entry.path}")

    if args.extract:
        did_something = True
        entry = find(image, args.extract)
        if entry is None:
            raise Iso9660Error(f"{args.extract}: not present in {image.path}")
        report = extract_file(image, entry, args.output)
        print(json.dumps(report, indent=2))

    if not did_something:
        _print_report(image, show_tree=False)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Iso9660Error as error:      # a clean message beats a traceback
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
