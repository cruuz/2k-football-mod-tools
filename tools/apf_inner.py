#!/usr/bin/env python3
"""Inspect APF 2K8 Visual Concepts IFF records inside the 0A archive.

The tool deliberately defaults to metadata-only reads.  It understands the
outer archive through ``apf_outer.py``, validates the big-endian IFF header and
block table, parses the little-endian trailing name directory, and can verify
or decode one bounded H7A-compressed block at a time.

For a selected ``TXTR``, the evidence-backed path can export the base mip of a
non-stacked tiled 2D DXT1, DXT3, DXT5, or 8_8_8_8 texture to PNG.  Remaining
formats, mips, cube/3D layouts, texture import, and the proprietary ``SCNE``
scene representation are reported as PORTME items instead of being guessed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import AbstractContextManager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import BinaryIO, Iterable
import zlib

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_outer


IFF_MAGIC = 0xFF3BEF94
H7A_MAGIC = 0x0E4837C3
NAME_FOOTER_MAGIC = 0xAA171516
IFF_HEADER_SIZE = 0x20
IFF_BLOCK_SIZE = 0x20
H7A_HEADER_SIZE = 0x14
MAX_COUNT = 1_000_000
DEFAULT_MAX_DECOMPRESSED = 256 * 1024 * 1024

XENOS_FORMATS = {
    2: "8",
    3: "1_5_5_5",
    4: "5_6_5",
    6: "8_8_8_8",
    7: "2_10_10_10",
    10: "8_8",
    15: "4_4_4_4",
    18: "DXT1",
    19: "DXT2_3",
    20: "DXT4_5",
    49: "DXN",
    58: "DXT3A",
    59: "DXT5A",
    60: "CTX1",
}
XENOS_ENDIAN = {0: "none", 1: "8in16", 2: "8in32", 3: "16in32"}
XENOS_DIMENSION = {0: "1D", 1: "2D_or_stacked", 2: "3D", 3: "cube"}

HASH_LABELS = {
    zlib.crc32(label.encode("ascii")) & 0xFFFFFFFF: label
    for label in (
        "DRAM",
        "VRAM",
        "SRAM",
        "TXTR",
        "SCNE",
        "AUDO",
        "LAYT",
        "MRKS",
        "PRIV",
        "TXT",
        "DRCT",
        "CLTH",
        "AMBO",
        "HILT",
        "NAME",
        "CDAN",
    )
}

ASSET_CLASSES = {
    "TXTR": "texture",
    "SCNE": "scene_model_package",
    "AUDO": "audio",
    "AUSB": "audio_bank_candidate",
    "MOVI": "movie_candidate",
    "CurveAnim": "animation_curve",
    "SingleMoCap": "animation_mocap",
    "CDAN": "crowd_animation_candidate",
    "MRKS": "animation_marker_candidate",
    "BoneScaleMap": "skeleton_scale_map",
    "LAYT": "layout_config_candidate",
    "ROST": "roster_data",
    "PLAY": "playbook_data",
    "SPCI": "sports_config_candidate",
    "STRG": "string_table_candidate",
    "TXT loc system": "localization_text_candidate",
    "DRCT": "director_config_candidate",
    "FONT": "font",
    "NumberFont": "font",
    "NameFont": "font",
    "KERN": "font_kerning",
    "CRED": "credits_data",
    "CLTH": "cloth_simulation",
}

EXECUTABLE_NAME_EXTENSIONS = (
    "iff",
    "bin",
    "dat",
    "cdf",
    "bnk",
    "txt",
    "xml",
    "csv",
    "ini",
    "lua",
)
EXECUTABLE_NAME_RE = re.compile(
    r"[A-Za-z0-9_./\\%+-]+\.(?:" + "|".join(EXECUTABLE_NAME_EXTENSIONS) + r")",
    re.IGNORECASE,
)
ASCII_RUN_RE = re.compile(rb"[\x20-\x7e]{4,}")
UTF16LE_RUN_RE = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")


class FormatError(ValueError):
    """Raised when an inner record is inconsistent or out of bounds."""


@dataclass(frozen=True)
class H7AHeader:
    magic: int
    uncompressed_length: int
    compressed_length: int
    unknown: int
    shift: int


@dataclass(frozen=True)
class Block:
    descriptor_index: int
    name_hash: int
    type_hash: int
    unknown_08: int
    uncompressed_length: int
    unknown_10: int
    start_offset: int
    compressed_length: int
    indexed: int
    wrapper: H7AHeader | None

    @property
    def is_compressed(self) -> bool:
        return self.uncompressed_length != self.compressed_length

    @property
    def stored_length(self) -> int:
        if self.is_compressed:
            return self.compressed_length
        return self.uncompressed_length

    @property
    def end_offset(self) -> int:
        return self.start_offset + self.stored_length


@dataclass(frozen=True)
class FilePart:
    block_index: int
    offset: int
    length: int


@dataclass
class DataFile:
    index: int
    file_id: int
    type_hash: int
    offsets: tuple[int, ...]
    parts: tuple[FilePart, ...] = ()
    name: str | None = None
    type_name: str | None = None


@dataclass(frozen=True)
class Footer:
    offset: int
    magic: int
    payload_size: int
    name_count: int


@dataclass
class IFFRecord:
    entry: apf_outer.Entry
    header_size: int
    file_length: int
    zero: int
    block_count: int
    unknown_14: int
    file_count: int
    unknown_1c: int
    file_header_offsets: tuple[int, ...]
    file_descriptor_offsets: tuple[int, ...]
    header_padding_size: int
    blocks: tuple[Block, ...]
    files: tuple[DataFile, ...]
    footer: Footer | None
    warnings: list[str]


class ArchiveReader(AbstractContextManager["ArchiveReader"]):
    """Random-access reader for entry-relative ranges across APF volumes."""

    def __init__(self, archive: apf_outer.Archive):
        self.archive = archive
        self._streams: dict[int, BinaryIO] = {}

    def __enter__(self) -> "ArchiveReader":
        for pack in self.archive.packs:
            self._streams[pack.ordinal] = pack.path.open("rb")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        for stream in self._streams.values():
            stream.close()
        self._streams.clear()

    def read(self, entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > entry.size:
            raise FormatError(
                f"entry {entry.table_index}: range 0x{offset:x}+0x{size:x} "
                f"exceeds entry size 0x{entry.size:x}"
            )
        if size == 0:
            return b""

        wanted_start = offset
        wanted_end = offset + size
        entry_cursor = 0
        pieces: list[bytes] = []
        for segment in entry.segments:
            segment_start = entry_cursor
            segment_end = entry_cursor + segment.size
            read_start = max(wanted_start, segment_start)
            read_end = min(wanted_end, segment_end)
            if read_start < read_end:
                stream = self._streams[segment.pack_ordinal]
                stream.seek(segment.pack_offset + read_start - segment_start)
                count = read_end - read_start
                piece = stream.read(count)
                if len(piece) != count:
                    raise FormatError(
                        f"entry {entry.table_index}: short read in "
                        f"{segment.pack_name} at 0x{segment.pack_offset:x}"
                    )
                pieces.append(piece)
            entry_cursor = segment_end
            if entry_cursor >= wanted_end:
                break

        data = b"".join(pieces)
        if len(data) != size:
            raise FormatError(
                f"entry {entry.table_index}: mapped 0x{len(data):x} of "
                f"requested 0x{size:x} bytes"
            )
        return data


def _u32be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FormatError(f"truncated {what} at 0x{offset:x}")
    return struct.unpack_from(">I", data, offset)[0]


def _u32le(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FormatError(f"truncated {what} at 0x{offset:x}")
    return struct.unpack_from("<I", data, offset)[0]


def _hash_label(value: int) -> str | None:
    return HASH_LABELS.get(value)


def _parse_h7a_header(
    reader: ArchiveReader, entry: apf_outer.Entry, block: Block
) -> H7AHeader:
    if block.stored_length < H7A_HEADER_SIZE:
        raise FormatError(
            f"entry {entry.table_index} block {block.descriptor_index}: "
            "compressed block is shorter than its 0x14-byte wrapper"
        )
    raw = reader.read(entry, block.start_offset, H7A_HEADER_SIZE)
    header = H7AHeader(*struct.unpack(">5I", raw))
    if header.magic != H7A_MAGIC:
        raise FormatError(
            f"entry {entry.table_index} block {block.descriptor_index}: "
            f"bad H7A magic 0x{header.magic:08x}"
        )
    if header.uncompressed_length != block.uncompressed_length:
        raise FormatError(
            f"entry {entry.table_index} block {block.descriptor_index}: "
            "wrapper/table uncompressed lengths disagree"
        )
    if header.compressed_length != block.compressed_length:
        raise FormatError(
            f"entry {entry.table_index} block {block.descriptor_index}: "
            "wrapper/table compressed lengths disagree"
        )
    if header.unknown != block.unknown_10:
        raise FormatError(
            f"entry {entry.table_index} block {block.descriptor_index}: "
            "wrapper/table codec fields disagree"
        )
    if not 1 <= header.shift <= 15:
        raise FormatError(
            f"entry {entry.table_index} block {block.descriptor_index}: "
            f"invalid H7A shift {header.shift}"
        )
    return header


def _decode_utf16le_z(data: bytes, offset: int, what: str) -> str:
    if offset < 0 or offset >= len(data):
        raise FormatError(f"{what} offset 0x{offset:x} is out of bounds")
    end = offset
    while end + 1 < len(data):
        if data[end : end + 2] == b"\0\0":
            break
        end += 2
    else:
        raise FormatError(f"unterminated UTF-16LE {what} at 0x{offset:x}")
    try:
        return data[offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise FormatError(f"invalid UTF-16LE {what} at 0x{offset:x}") from exc


def _parse_footer_names(payload: bytes, file_count: int) -> list[tuple[str, str]]:
    if len(payload) < 8:
        raise FormatError("name footer payload is shorter than 8 bytes")
    name_count = _u32le(payload, 0, "footer name count")
    if name_count > MAX_COUNT:
        raise FormatError(f"implausible footer name count {name_count}")
    table_offset = _u32le(payload, 4, "footer name-table pointer") + 4 - 1
    if table_offset < 0 or table_offset + name_count * 4 > len(payload):
        raise FormatError("footer name pointer table is out of bounds")

    names: list[tuple[str, str]] = []
    for index in range(name_count):
        pointer_offset = table_offset + index * 4
        record_offset = (
            _u32le(payload, pointer_offset, f"footer record pointer {index}")
            + pointer_offset
            - 1
        )
        if record_offset < 0 or record_offset + 8 > len(payload):
            raise FormatError(f"footer record {index} is out of bounds")
        name_offset = (
            _u32le(payload, record_offset, f"footer name pointer {index}")
            + record_offset
            - 1
        )
        type_pointer_offset = record_offset + 4
        type_offset = (
            _u32le(payload, type_pointer_offset, f"footer type pointer {index}")
            + type_pointer_offset
            - 1
        )
        if name_offset > type_offset:
            raise FormatError(f"footer name {index} begins after its type")
        name = _decode_utf16le_z(payload, name_offset, f"name {index}")
        type_name = _decode_utf16le_z(payload, type_offset, f"type {index}")
        names.append((name, type_name))

    if name_count != file_count:
        raise FormatError(
            f"footer has {name_count} names but IFF header has {file_count} files"
        )
    return names


def parse_iff(
    reader: ArchiveReader, entry: apf_outer.Entry, strict_footer: bool = True
) -> IFFRecord:
    raw_header = reader.read(entry, 0, IFF_HEADER_SIZE)
    fields = struct.unpack(">8I", raw_header)
    magic, header_size, file_length, zero, block_count, unknown_14, file_count, unknown_1c = fields
    if magic != IFF_MAGIC:
        raise FormatError(
            f"entry {entry.table_index}: magic 0x{magic:08x} is not a VC IFF"
        )
    if block_count > MAX_COUNT or file_count > MAX_COUNT:
        raise FormatError(
            f"entry {entry.table_index}: implausible counts "
            f"blocks={block_count}, files={file_count}"
        )
    minimum_header = IFF_HEADER_SIZE + block_count * IFF_BLOCK_SIZE + file_count * 4
    if not minimum_header <= header_size <= entry.size:
        raise FormatError(
            f"entry {entry.table_index}: header size 0x{header_size:x} is outside "
            f"minimum 0x{minimum_header:x} / entry 0x{entry.size:x}"
        )
    if not header_size <= file_length <= entry.size:
        raise FormatError(
            f"entry {entry.table_index}: file length 0x{file_length:x} is outside "
            f"header/entry bounds"
        )

    # IFF pointers are stored as one-based self-relative values:
    # target = address_of_pointer + stored_value - 1.  The 0x0D at 0x14
    # therefore resolves to the block table at 0x20.  The value at 0x1C
    # resolves to the per-file pointer table after the block descriptors.
    block_table_offset = 0x14 + unknown_14 - 1
    if block_table_offset != IFF_HEADER_SIZE:
        raise FormatError(
            f"entry {entry.table_index}: block-table pointer resolves to "
            f"0x{block_table_offset:x}, expected 0x{IFF_HEADER_SIZE:x}"
        )
    file_pointer_table_offset = 0x1C + unknown_1c - 1
    expected_file_pointer_table_offset = IFF_HEADER_SIZE + block_count * IFF_BLOCK_SIZE
    if file_pointer_table_offset != expected_file_pointer_table_offset:
        raise FormatError(
            f"entry {entry.table_index}: file-pointer-table pointer resolves to "
            f"0x{file_pointer_table_offset:x}, expected "
            f"0x{expected_file_pointer_table_offset:x}"
        )

    header = reader.read(entry, 0, header_size)
    blocks: list[Block] = []
    cursor = IFF_HEADER_SIZE
    for index in range(block_count):
        values = struct.unpack_from(">8I", header, cursor)
        provisional = Block(index, *values, wrapper=None)
        if provisional.start_offset < header_size:
            raise FormatError(
                f"entry {entry.table_index} block {index}: data starts inside header"
            )
        if provisional.end_offset > entry.size:
            raise FormatError(
                f"entry {entry.table_index} block {index}: data ends outside entry"
            )
        wrapper = None
        if provisional.is_compressed:
            wrapper = _parse_h7a_header(reader, entry, provisional)
        blocks.append(Block(index, *values, wrapper=wrapper))
        cursor += IFF_BLOCK_SIZE

    file_header_offsets = tuple(
        _u32be(header, cursor + index * 4, f"file-header offset {index}")
        for index in range(file_count)
    )
    file_descriptor_offsets = tuple(
        cursor + index * 4 + value - 1
        for index, value in enumerate(file_header_offsets)
    )
    cursor += file_count * 4

    files: list[DataFile] = []
    for index in range(file_count):
        descriptor_offset = file_descriptor_offsets[index]
        if descriptor_offset != cursor:
            raise FormatError(
                f"entry {entry.table_index}: file pointer {index} resolves to "
                f"0x{descriptor_offset:x}, expected packed descriptor at 0x{cursor:x}"
            )
        if cursor + 12 > header_size:
            raise FormatError(
                f"entry {entry.table_index}: file descriptor {index} is truncated"
            )
        file_id, type_hash, offset_count = struct.unpack_from(">3I", header, cursor)
        if offset_count > block_count:
            raise FormatError(
                f"entry {entry.table_index}: file {index} references {offset_count} "
                f"blocks but IFF has {block_count}"
            )
        descriptor_end = cursor + 12 + offset_count * 4
        if descriptor_end > header_size:
            raise FormatError(
                f"entry {entry.table_index}: file descriptor {index} offsets are truncated"
            )
        offsets = tuple(
            _u32be(header, cursor + 12 + part * 4, f"file {index} block offset")
            for part in range(offset_count)
        )
        files.append(DataFile(index, file_id, type_hash, offsets))
        cursor = descriptor_end

    header_padding_size = header_size - cursor
    warnings: list[str] = []
    ordered_blocks = sorted(blocks, key=lambda item: item.start_offset)
    for previous, current in zip(ordered_blocks, ordered_blocks[1:]):
        if current.start_offset != previous.end_offset:
            warnings.append(
                f"block gap/overlap: block {previous.descriptor_index} ends "
                f"0x{previous.end_offset:x}, block {current.descriptor_index} starts "
                f"0x{current.start_offset:x}"
            )
    if ordered_blocks and ordered_blocks[0].start_offset != header_size:
        warnings.append(
            f"first block starts 0x{ordered_blocks[0].start_offset:x}, "
            f"header ends 0x{header_size:x}"
        )
    expected_file_length = ordered_blocks[-1].end_offset if ordered_blocks else header_size
    if expected_file_length != file_length:
        warnings.append(
            f"last block ends 0x{expected_file_length:x}, file_length is "
            f"0x{file_length:x}"
        )

    for block_index, block in enumerate(blocks):
        # 0xFFFFFFFF is an observed absent-part sentinel.  It is common for
        # files with DRAM/SRAM data but no VRAM data; treating it as a real
        # offset incorrectly makes the preceding file appear to span 4 GiB.
        present = [
            file
            for file in files
            if len(file.offsets) > block_index
            and file.offsets[block_index] != 0xFFFFFFFF
        ]
        present.sort(key=lambda file: file.offsets[block_index])
        for position, file in enumerate(present):
            start = file.offsets[block_index]
            end = (
                present[position + 1].offsets[block_index]
                if position + 1 < len(present)
                else block.uncompressed_length
            )
            if not 0 <= start <= end <= block.uncompressed_length:
                raise FormatError(
                    f"entry {entry.table_index}: file {file.index} block {block_index} "
                    "range is outside decompressed block"
                )
            file.parts += (FilePart(block_index, start, end - start),)

    footer: Footer | None = None
    if file_length + 8 <= entry.size:
        footer_header = reader.read(entry, file_length, 8)
        footer_magic = struct.unpack_from(">I", footer_header, 0)[0]
        footer_size = struct.unpack_from("<I", footer_header, 4)[0]
        if footer_magic == 0 and footer_size == 0:
            warnings.append("no trailing name directory")
        else:
            if file_length + 8 + footer_size > entry.size:
                raise FormatError(
                    f"entry {entry.table_index}: name footer extends outside entry"
                )
            if footer_magic != NAME_FOOTER_MAGIC:
                message = f"unknown name footer magic 0x{footer_magic:08x}"
                if strict_footer:
                    raise FormatError(f"entry {entry.table_index}: {message}")
                warnings.append(message)
            payload = reader.read(entry, file_length + 8, footer_size)
            name_count = _u32le(payload, 0, "footer name count") if footer_size >= 4 else 0
            footer = Footer(file_length, footer_magic, footer_size, name_count)
            try:
                names = _parse_footer_names(payload, file_count)
                for file, (name, type_name) in zip(files, names):
                    expected_file_id = zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF
                    expected_type_hash = zlib.crc32(type_name.encode("ascii")) & 0xFFFFFFFF
                    if file.file_id != expected_file_id:
                        raise FormatError(
                            f"file {file.index} ID 0x{file.file_id:08x} is not "
                            f"CRC32({name!r}) = 0x{expected_file_id:08x}"
                        )
                    if file.type_hash != expected_type_hash:
                        raise FormatError(
                            f"file {file.index} type ID 0x{file.type_hash:08x} is not "
                            f"CRC32({type_name!r}) = 0x{expected_type_hash:08x}"
                        )
                    file.name = name
                    file.type_name = type_name
            except FormatError as exc:
                if strict_footer:
                    raise FormatError(f"entry {entry.table_index}: {exc}") from exc
                warnings.append(str(exc))
    else:
        warnings.append("entry has no room for a trailing name-directory header")

    return IFFRecord(
        entry=entry,
        header_size=header_size,
        file_length=file_length,
        zero=zero,
        block_count=block_count,
        unknown_14=unknown_14,
        file_count=file_count,
        unknown_1c=unknown_1c,
        file_header_offsets=file_header_offsets,
        file_descriptor_offsets=file_descriptor_offsets,
        header_padding_size=header_padding_size,
        blocks=tuple(blocks),
        files=tuple(files),
        footer=footer,
        warnings=warnings,
    )


def decompress_h7a(data: bytes, expected_size: int, shift: int) -> bytes:
    """Decode the LSB-first VC/H7A literal/back-reference stream.

    Match words use the upper ``16-shift`` bits for ``length - 3`` and the
    lower ``shift`` bits for the backward distance.  The result is rejected if
    any input/output bound or look-back invariant is violated.
    """

    if expected_size < 0:
        raise FormatError("negative H7A output size")
    if not 1 <= shift <= 15:
        raise FormatError(f"invalid H7A shift {shift}")
    output = bytearray(expected_size)
    source = 0
    target = 0
    distance_mask = (1 << shift) - 1
    length_mask = (1 << (16 - shift)) - 1

    while source < len(data) and target < expected_size:
        descriptor = data[source]
        source += 1
        for _ in range(8):
            if target >= expected_size:
                break
            if descriptor & 1:
                if source + 2 > len(data):
                    raise FormatError("truncated H7A back-reference")
                word = (data[source] << 8) | data[source + 1]
                source += 2
                distance = word & distance_mask
                length = ((word >> shift) & length_mask) + 3
                if distance == 0 or distance > target:
                    raise FormatError(
                        f"invalid H7A distance {distance} at output 0x{target:x}"
                    )
                if target + length > expected_size:
                    raise FormatError("H7A match overruns declared output")
                for _ in range(length):
                    output[target] = output[target - distance]
                    target += 1
            else:
                if source >= len(data):
                    raise FormatError("truncated H7A literal")
                output[target] = data[source]
                source += 1
                target += 1
            descriptor >>= 1

    if target != expected_size:
        raise FormatError(
            f"H7A produced 0x{target:x}, expected 0x{expected_size:x} bytes"
        )
    # Some valid blocks have a single zero alignment byte after the token that
    # completes the declared output.  Nonzero trailing data remains an error.
    if source != len(data) and any(data[source:]):
        raise FormatError(
            f"H7A left 0x{len(data) - source:x} nonzero compressed bytes unread"
        )
    return bytes(output)


@dataclass(frozen=True)
class _H7AToken:
    kind: str
    output_start: int
    length: int
    literal: int | None
    distance: int | None


def _parse_h7a_tokens(
    payload: bytes,
    expected_size: int,
    shift: int,
) -> tuple[list[_H7AToken], int]:
    """Parse a validated H7A stream without losing its token boundaries."""

    if expected_size < 0 or not 1 <= shift <= 15:
        raise FormatError("invalid H7A token-preservation parameters")
    tokens: list[_H7AToken] = []
    source = 0
    target = 0
    distance_mask = (1 << shift) - 1
    while target < expected_size:
        if source >= len(payload):
            raise FormatError("H7A descriptor stream is truncated")
        descriptor = payload[source]
        source += 1
        for bit in range(8):
            if target >= expected_size:
                break
            start = target
            if descriptor & (1 << bit):
                if source + 2 > len(payload):
                    raise FormatError("H7A match token is truncated")
                word = int.from_bytes(payload[source : source + 2], "big")
                source += 2
                distance = word & distance_mask
                length = (word >> shift) + 3
                if (
                    distance == 0
                    or distance > target
                    or target + length > expected_size
                ):
                    raise FormatError("H7A match token violates decoded bounds")
                tokens.append(
                    _H7AToken("match", start, length, None, distance)
                )
                target += length
            else:
                if source >= len(payload):
                    raise FormatError("H7A literal token is truncated")
                tokens.append(
                    _H7AToken("literal", start, 1, payload[source], None)
                )
                source += 1
                target += 1
    if any(payload[source:]):
        raise FormatError("H7A has unread nonzero trailing bytes")
    return tokens, source


def _preserved_h7a_match_run(
    data: bytes,
    position: int,
    end: int,
    distance: int,
) -> int:
    length = 0
    while (
        position + length < end
        and data[position + length] == data[position + length - distance]
    ):
        length += 1
    return length


def encode_h7a_preserving_tokens(
    retail_payload: bytes,
    retail_decoded: bytes,
    wanted: bytes,
    shift: int,
) -> tuple[bytes, dict[str, int]]:
    """Re-encode H7A while preserving every still-valid retail token.

    Only retail match tokens invalidated by changed decoded bytes are split into
    smaller matches/literals. This keeps runtime-sensitive streams close to
    their source transport instead of greedily retokenizing the complete body.
    The result is independently decoded before it is returned.
    """

    if len(retail_decoded) != len(wanted):
        raise FormatError("retail and wanted H7A outputs differ in length")
    if decompress_h7a(retail_payload, len(retail_decoded), shift) != retail_decoded:
        raise FormatError("retail H7A payload does not decode to its source body")
    original, consumed = _parse_h7a_tokens(
        retail_payload,
        len(retail_decoded),
        shift,
    )
    emitted: list[tuple[str, int, int]] = []
    preserved = 0
    split = 0
    max_length = ((1 << (16 - shift)) - 1) + 3
    for token in original:
        start = token.output_start
        end = start + token.length
        first = len(emitted)
        if token.kind == "literal":
            if token.literal is None:
                raise FormatError("parsed H7A literal has no value")
            emitted.append(("literal", wanted[start], 1))
        else:
            if token.distance is None:
                raise FormatError("parsed H7A match has no distance")
            cursor = start
            while cursor < end:
                run = _preserved_h7a_match_run(
                    wanted,
                    cursor,
                    end,
                    token.distance,
                )
                if run >= 3:
                    length = min(run, max_length)
                    emitted.append(("match", token.distance, length))
                    cursor += length
                else:
                    emitted.append(("literal", wanted[cursor], 1))
                    cursor += 1
        local = emitted[first:]
        exact = (
            token.kind == "literal"
            and token.literal is not None
            and local == [("literal", token.literal, 1)]
        ) or (
            token.kind == "match"
            and token.distance is not None
            and local == [("match", token.distance, token.length)]
        )
        if exact:
            preserved += 1
        else:
            split += 1

    output = bytearray()
    for group_start in range(0, len(emitted), 8):
        group = emitted[group_start : group_start + 8]
        descriptor = sum(
            (kind == "match") << bit
            for bit, (kind, _value, _length) in enumerate(group)
        )
        output.append(descriptor)
        for kind, value, length in group:
            if kind == "literal":
                output.append(value)
            else:
                word = ((length - 3) << shift) | value
                if not 0 < value < (1 << shift) or not 0 <= word <= 0xFFFF:
                    raise FormatError("emitted H7A match is outside word bounds")
                output.extend(word.to_bytes(2, "big"))
    encoded = bytes(output)
    if decompress_h7a(encoded, len(wanted), shift) != wanted:
        raise FormatError("preservation-aware H7A encode/decode is not exact")
    return encoded, {
        "retail_token_count": len(original),
        "output_token_count": len(emitted),
        "retail_tokens_preserved_semantically": preserved,
        "retail_tokens_split_or_replaced": split,
        "retail_payload_consumed_bytes": consumed,
        "retail_zero_alignment_bytes": len(retail_payload) - consumed,
    }


def decode_block(
    reader: ArchiveReader,
    record: IFFRecord,
    block_index: int,
    max_decompressed: int,
) -> bytes:
    try:
        block = record.blocks[block_index]
    except IndexError as exc:
        raise FormatError(
            f"entry {record.entry.table_index}: no block {block_index}"
        ) from exc
    if block.uncompressed_length > max_decompressed:
        raise FormatError(
            f"block output 0x{block.uncompressed_length:x} exceeds limit "
            f"0x{max_decompressed:x}"
        )
    raw = reader.read(record.entry, block.start_offset, block.stored_length)
    if not block.is_compressed:
        return raw
    if block.wrapper is None:
        raise FormatError("compressed block is missing validated H7A metadata")
    return decompress_h7a(
        raw[H7A_HEADER_SIZE:],
        block.wrapper.uncompressed_length,
        block.wrapper.shift,
    )


def parse_txtr_metadata(header_data: bytes) -> dict[str, object]:
    """Parse the stable VC texture header and embedded Xenos fetch constant."""

    if len(header_data) < 0xAC:
        raise FormatError(
            f"TXTR DRAM part is 0x{len(header_data):x}, shorter than fetch metadata"
        )
    fetch = struct.unpack_from(">6I", header_data, 0x94)
    dword_0, dword_1, dword_2, dword_3, dword_4, dword_5 = fetch
    fetch_type = dword_0 & 0x3
    pitch_pixels = ((dword_0 >> 22) & 0x1FF) << 5
    tiled = bool((dword_0 >> 31) & 1)
    format_value = dword_1 & 0x3F
    endian_value = (dword_1 >> 6) & 0x3
    width = (dword_2 & 0x1FFF) + 1
    height = ((dword_2 >> 13) & 0x1FFF) + 1
    stack_depth_minus_one = (dword_2 >> 26) & 0x3F
    swizzle = (dword_3 >> 1) & 0xFFF
    swizzle_components = [(swizzle >> (component * 3)) & 0x7 for component in range(4)]
    dimension = (dword_5 >> 9) & 0x3

    warnings: list[str] = []
    declared_width, declared_height = struct.unpack_from(">HH", header_data, 0x60)
    if declared_width != width or declared_height != height:
        warnings.append(
            f"VC dimensions {declared_width}x{declared_height} disagree with "
            f"fetch dimensions {width}x{height}"
        )
    if fetch_type != 2:
        warnings.append(f"fetch constant type is {fetch_type}, expected texture type 2")

    return {
        "vc_file_id": _hex(_u32be(header_data, 0, "TXTR file id")),
        "vc_width": declared_width,
        "vc_height": declared_height,
        "vc_base_data_length": _u32be(header_data, 0x70, "TXTR base length"),
        "vc_mip_data_length": _u32be(header_data, 0x74, "TXTR mip length"),
        "fetch_offset": 0x94,
        "fetch_dwords": [_hex(value) for value in fetch],
        "fetch_type": fetch_type,
        "pitch_pixels": pitch_pixels,
        "tiled": tiled,
        "format": format_value,
        "format_name": XENOS_FORMATS.get(format_value, f"unknown_{format_value}"),
        "endianness": endian_value,
        "endianness_name": XENOS_ENDIAN[endian_value],
        "request_size": (dword_1 >> 8) & 0x3,
        "stacked": bool((dword_1 >> 10) & 1),
        "base_address_pages": dword_1 >> 12,
        "width": width,
        "height": height,
        "stack_depth_minus_one": stack_depth_minus_one,
        "swizzle": swizzle,
        "swizzle_components": swizzle_components,
        "mip_min_level": (dword_4 >> 2) & 0xF,
        "mip_max_level": (dword_4 >> 6) & 0xF,
        "dimension": dimension,
        "dimension_name": XENOS_DIMENSION[dimension],
        "packed_mips": bool((dword_5 >> 11) & 1),
        "mip_address_pages": dword_5 >> 12,
        "warnings": warnings,
    }


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _tiled_2d_offset(
    x: int, y: int, pitch_blocks_aligned: int, bytes_per_block_log2: int
) -> int:
    """Xenos 2D tiled byte offset, following Xenia's texture_address.h."""

    if pitch_blocks_aligned & 31:
        raise FormatError("Xenos tiled pitch is not 32-block aligned")
    outer_blocks = (
        (y >> 5) * (pitch_blocks_aligned >> 5) + (x >> 5)
    ) << 6
    inner_blocks = (((y >> 1) & 0b111) << 3) | (x & 0b111)
    outer_inner_bytes = (outer_blocks | inner_blocks) << bytes_per_block_log2
    bank = (y >> 4) & 1
    pipe = ((x >> 3) & 0b11) ^ (((y >> 3) & 1) << 1)
    y_lsb = y & 1
    return (
        (y_lsb << 4)
        | (pipe << 6)
        | (bank << 11)
        | (outer_inner_bytes & 0xF)
        | (((outer_inner_bytes >> 4) & 1) << 5)
        | (((outer_inner_bytes >> 5) & 0b111) << 8)
        | ((outer_inner_bytes >> 8) << 12)
    )


def _endian_swap(data: bytes, mode: int) -> bytes:
    if mode == 0:
        return data
    unit = 2 if mode == 1 else 4
    if len(data) % unit:
        raise FormatError(
            f"texture block length {len(data)} is not aligned for endian mode {mode}"
        )
    result = bytearray(len(data))
    for offset in range(0, len(data), unit):
        chunk = data[offset : offset + unit]
        if mode == 1:  # 8-in-16
            result[offset : offset + 2] = chunk[::-1]
        elif mode == 2:  # 8-in-32
            result[offset : offset + 4] = chunk[::-1]
        elif mode == 3:  # 16-in-32
            result[offset : offset + 4] = chunk[2:4] + chunk[0:2]
        else:
            raise FormatError(f"unsupported endian mode {mode}")
    return bytes(result)


def _untile_2d(
    source: bytes,
    width: int,
    height: int,
    pitch_pixels: int,
    block_width: int,
    block_height: int,
    bytes_per_block: int,
) -> bytes:
    if bytes_per_block <= 0 or bytes_per_block & (bytes_per_block - 1):
        raise FormatError("Xenos block size must be a positive power of two")
    width_blocks = (width + block_width - 1) // block_width
    height_blocks = (height + block_height - 1) // block_height
    pitch_blocks = (pitch_pixels + block_width - 1) // block_width
    pitch_blocks_aligned = _align_up(pitch_blocks, 32)
    height_blocks_aligned = _align_up(height_blocks, 32)
    required = pitch_blocks_aligned * height_blocks_aligned * bytes_per_block
    if len(source) < required:
        raise FormatError(
            f"tiled base level needs 0x{required:x} bytes, source has 0x{len(source):x}"
        )
    output = bytearray(width_blocks * height_blocks * bytes_per_block)
    log2_size = bytes_per_block.bit_length() - 1
    for y in range(height_blocks):
        for x in range(width_blocks):
            source_offset = _tiled_2d_offset(
                x, y, pitch_blocks_aligned, log2_size
            )
            destination = (y * width_blocks + x) * bytes_per_block
            if source_offset + bytes_per_block > len(source):
                raise FormatError("tiled address exceeds texture source")
            output[destination : destination + bytes_per_block] = source[
                source_offset : source_offset + bytes_per_block
            ]
    return bytes(output)


def _rgb565(value: int) -> tuple[int, int, int]:
    red = (value >> 11) & 31
    green = (value >> 5) & 63
    blue = value & 31
    return (
        (red << 3) | (red >> 2),
        (green << 2) | (green >> 4),
        (blue << 3) | (blue >> 2),
    )


def _bc_color_table(
    block: bytes, force_four_colors: bool
) -> tuple[list[tuple[int, int, int, int]], int]:
    color_0, color_1, indices = struct.unpack_from("<HHI", block, 0)
    rgb_0 = _rgb565(color_0)
    rgb_1 = _rgb565(color_1)
    colors: list[tuple[int, int, int, int]] = [(*rgb_0, 255), (*rgb_1, 255)]
    if color_0 > color_1 or force_four_colors:
        colors.extend(
            [
                tuple((2 * rgb_0[i] + rgb_1[i]) // 3 for i in range(3)) + (255,),
                tuple((rgb_0[i] + 2 * rgb_1[i]) // 3 for i in range(3)) + (255,),
            ]
        )
    else:
        colors.extend(
            [
                tuple((rgb_0[i] + rgb_1[i]) // 2 for i in range(3)) + (255,),
                (0, 0, 0, 0),
            ]
        )
    return colors, indices


def _decode_bc1(block: bytes) -> list[tuple[int, int, int, int]]:
    if len(block) != 8:
        raise FormatError("BC1 block is not 8 bytes")
    colors, indices = _bc_color_table(block, False)
    return [colors[(indices >> (pixel * 2)) & 3] for pixel in range(16)]


def _decode_bc2(block: bytes) -> list[tuple[int, int, int, int]]:
    if len(block) != 16:
        raise FormatError("BC2 block is not 16 bytes")
    alpha = int.from_bytes(block[:8], "little")
    colors, indices = _bc_color_table(block[8:], True)
    pixels = []
    for pixel in range(16):
        color = colors[(indices >> (pixel * 2)) & 3]
        alpha_value = ((alpha >> (pixel * 4)) & 0xF) * 17
        pixels.append((*color[:3], alpha_value))
    return pixels


def _decode_bc3(block: bytes) -> list[tuple[int, int, int, int]]:
    if len(block) != 16:
        raise FormatError("BC3 block is not 16 bytes")
    alpha_0, alpha_1 = block[0], block[1]
    alpha_indices = int.from_bytes(block[2:8], "little")
    alphas = [alpha_0, alpha_1]
    if alpha_0 > alpha_1:
        alphas.extend(
            (alpha_0 * (7 - index) + alpha_1 * index) // 7
            for index in range(1, 7)
        )
    else:
        alphas.extend(
            (alpha_0 * (5 - index) + alpha_1 * index) // 5
            for index in range(1, 5)
        )
        alphas.extend((0, 255))
    colors, indices = _bc_color_table(block[8:], True)
    pixels = []
    for pixel in range(16):
        color = colors[(indices >> (pixel * 2)) & 3]
        alpha_value = alphas[(alpha_indices >> (pixel * 3)) & 7]
        pixels.append((*color[:3], alpha_value))
    return pixels


def _swizzle_pixel(
    pixel: tuple[int, int, int, int], selectors: list[int]
) -> tuple[int, int, int, int]:
    values = (*pixel, 0, 255, 0, 0)
    return tuple(values[selector] for selector in selectors)  # type: ignore[return-value]


def decode_txtr_base_rgba(
    metadata: dict[str, object], base_data: bytes
) -> tuple[int, int, bytes]:
    width = int(metadata["width"])
    height = int(metadata["height"])
    pitch = int(metadata["pitch_pixels"])
    format_value = int(metadata["format"])
    endian = int(metadata["endianness"])
    selectors = list(metadata["swizzle_components"])
    if metadata["dimension"] != 1 or metadata["stacked"]:
        dim = int(metadata["dimension"])
        dim_hint = {
            0: "1D",
            1: "2D",
            2: "3D",
            3: "cubemap",
        }.get(dim, f"dimension={dim}")
        raise FormatError(
            "PORTME: PNG conversion currently supports only non-stacked 2D TXTR "
            f"(this asset is {dim_hint}"
            f"{', stacked' if metadata['stacked'] else ''}; "
            f"format {format_value} {metadata.get('format_name', '')}). "
            "Cubemap/3D lightmaps (e.g. SpecularLightBox format 32) remain "
            "raw-export only until a face-preview path ships."
        )
    if not metadata["tiled"]:
        raise FormatError("PORTME: linear TXTR base-level routing is unverified")

    if format_value == 18:
        block_width, block_height, block_size = 4, 4, 8
        decoder = _decode_bc1
    elif format_value == 19:
        block_width, block_height, block_size = 4, 4, 16
        decoder = _decode_bc2
    elif format_value == 20:
        block_width, block_height, block_size = 4, 4, 16
        decoder = _decode_bc3
    elif format_value == 6:
        # 8_8_8_8 — 4 bytes/texel
        block_width, block_height, block_size = 1, 1, 4
        decoder = None
    elif format_value in (3, 4, 15):
        # 1_5_5_5, 5_6_5, 4_4_4_4 — 2 bytes/texel
        block_width, block_height, block_size = 1, 1, 2
        decoder = None
    elif format_value == 2:
        # 8 — single 8-bit luminance/alpha channel
        block_width, block_height, block_size = 1, 1, 1
        decoder = None
    elif format_value == 10:
        # 8_8 — two 8-bit channels
        block_width, block_height, block_size = 1, 1, 2
        decoder = None
    else:
        raise FormatError(
            f"PORTME: Xenos format {format_value} "
            f"({metadata['format_name']}) is not implemented for PNG. "
            f"Supported PNG previews: 8, 1_5_5_5, 5_6_5, 8_8_8_8, 8_8, "
            f"4_4_4_4, DXT1, DXT2_3, DXT4_5. Export raw TXTR parts instead."
        )

    linear = _untile_2d(
        base_data,
        width,
        height,
        pitch,
        block_width,
        block_height,
        block_size,
    )
    linear = _endian_swap(linear, endian)
    rgba = bytearray(width * height * 4)
    if decoder is None:
        if format_value == 15:
            for pixel_index in range(width * height):
                raw = linear[pixel_index * 2 : pixel_index * 2 + 2]
                if len(raw) != 2:
                    raise FormatError("truncated 4_4_4_4 texel")
                value = int.from_bytes(raw, "little")
                a = (value >> 12) & 0xF
                r = (value >> 8) & 0xF
                g = (value >> 4) & 0xF
                b = value & 0xF
                a8 = (a << 4) | a
                r8 = (r << 4) | r
                g8 = (g << 4) | g
                b8 = (b << 4) | b
                pixel = _swizzle_pixel((r8, g8, b8, a8), selectors)
                rgba[pixel_index * 4 : pixel_index * 4 + 4] = bytes(pixel)
        elif format_value == 4:
            # 5_6_5 RGB, opaque alpha
            for pixel_index in range(width * height):
                raw = linear[pixel_index * 2 : pixel_index * 2 + 2]
                if len(raw) != 2:
                    raise FormatError("truncated 5_6_5 texel")
                value = int.from_bytes(raw, "little")
                r5 = (value >> 11) & 0x1F
                g6 = (value >> 5) & 0x3F
                b5 = value & 0x1F
                r8 = (r5 << 3) | (r5 >> 2)
                g8 = (g6 << 2) | (g6 >> 4)
                b8 = (b5 << 3) | (b5 >> 2)
                pixel = _swizzle_pixel((r8, g8, b8, 255), selectors)
                rgba[pixel_index * 4 : pixel_index * 4 + 4] = bytes(pixel)
        elif format_value == 3:
            # 1_5_5_5 ARGB
            for pixel_index in range(width * height):
                raw = linear[pixel_index * 2 : pixel_index * 2 + 2]
                if len(raw) != 2:
                    raise FormatError("truncated 1_5_5_5 texel")
                value = int.from_bytes(raw, "little")
                a1 = (value >> 15) & 0x1
                r5 = (value >> 10) & 0x1F
                g5 = (value >> 5) & 0x1F
                b5 = value & 0x1F
                a8 = 255 if a1 else 0
                r8 = (r5 << 3) | (r5 >> 2)
                g8 = (g5 << 3) | (g5 >> 2)
                b8 = (b5 << 3) | (b5 >> 2)
                pixel = _swizzle_pixel((r8, g8, b8, a8), selectors)
                rgba[pixel_index * 4 : pixel_index * 4 + 4] = bytes(pixel)
        elif format_value == 2:
            for pixel_index in range(width * height):
                if pixel_index >= len(linear):
                    raise FormatError("truncated 8-bit texel")
                v = linear[pixel_index]
                pixel = _swizzle_pixel((v, v, v, 255), selectors)
                rgba[pixel_index * 4 : pixel_index * 4 + 4] = bytes(pixel)
        elif format_value == 10:
            for pixel_index in range(width * height):
                raw = linear[pixel_index * 2 : pixel_index * 2 + 2]
                if len(raw) != 2:
                    raise FormatError("truncated 8_8 texel")
                # Common: R=first, G=second, B=0, A=255 (normal/gloss pairs vary)
                r8, g8 = raw[0], raw[1]
                pixel = _swizzle_pixel((r8, g8, 0, 255), selectors)
                rgba[pixel_index * 4 : pixel_index * 4 + 4] = bytes(pixel)
        else:
            # format 6 8_8_8_8
            for pixel_index in range(width * height):
                raw = linear[pixel_index * 4 : pixel_index * 4 + 4]
                pixel = _swizzle_pixel(tuple(raw), selectors)
                rgba[pixel_index * 4 : pixel_index * 4 + 4] = bytes(pixel)
    else:
        width_blocks = (width + 3) // 4
        height_blocks = (height + 3) // 4
        for block_y in range(height_blocks):
            for block_x in range(width_blocks):
                block_offset = (block_y * width_blocks + block_x) * block_size
                pixels = decoder(linear[block_offset : block_offset + block_size])
                for local_y in range(4):
                    for local_x in range(4):
                        x = block_x * 4 + local_x
                        y = block_y * 4 + local_y
                        if x >= width or y >= height:
                            continue
                        pixel = _swizzle_pixel(
                            pixels[local_y * 4 + local_x], selectors
                        )
                        destination = (y * width + x) * 4
                        rgba[destination : destination + 4] = bytes(pixel)
    return width, height, bytes(rgba)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_rgba_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    if len(rgba) != width * height * 4:
        raise FormatError("RGBA buffer size does not match PNG dimensions")
    scanlines = b"".join(
        b"\0" + rgba[row * width * 4 : (row + 1) * width * 4]
        for row in range(height)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk("IHDR".encode(), struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _png_chunk("IDAT".encode(), zlib.compress(scanlines, 9))
        + _png_chunk("IEND".encode(), b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _candidate_strings(data: bytes) -> Iterable[tuple[int, str, str]]:
    for match in ASCII_RUN_RE.finditer(data):
        value = match.group().decode("ascii")
        for candidate in EXECUTABLE_NAME_RE.finditer(value):
            yield match.start() + candidate.start(), "ascii", candidate.group()
    for match in UTF16LE_RUN_RE.finditer(data):
        value = match.group().decode("utf-16le")
        for candidate in EXECUTABLE_NAME_RE.finditer(value):
            yield match.start() + candidate.start() * 2, "utf-16le", candidate.group()


def executable_name_candidates(
    executable_path: Path, entries: Iterable[apf_outer.Entry]
) -> tuple[dict[int, list[dict[str, object]]], str]:
    data = executable_path.read_bytes()
    wanted = {entry.name_id for entry in entries}
    matches: dict[int, list[dict[str, object]]] = defaultdict(list)
    seen: set[tuple[int, str, int, str]] = set()
    for offset, encoding, raw_name in _candidate_strings(data):
        normalized = raw_name.replace("\\", "/")
        for candidate in (normalized, normalized.rsplit("/", 1)[-1]):
            try:
                value = zlib.crc32(candidate.upper().encode("ascii")) & 0xFFFFFFFF
            except UnicodeEncodeError:
                continue
            key = (value, candidate.lower(), offset, encoding)
            if value not in wanted or key in seen:
                continue
            seen.add(key)
            matches[value].append(
                {"name": candidate, "offset": offset, "encoding": encoding}
            )
    return dict(matches), hashlib.sha256(data).hexdigest()


def _hex(value: int) -> str:
    return f"0x{value:08x}"


def _record_document(
    record: IFFRecord, outer_names: dict[int, list[dict[str, object]]]
) -> dict[str, object]:
    entry = record.entry
    return {
        "table_index": entry.table_index,
        "name_id": _hex(entry.name_id),
        "outer_name_candidates": outer_names.get(entry.name_id, []),
        "virtual_offset": entry.virtual_offset,
        "outer_size": entry.size,
        "segments": [
            {
                "pack_name": segment.pack_name,
                "pack_offset": segment.pack_offset,
                "size": segment.size,
            }
            for segment in entry.segments
        ],
        "header": {
            "magic": _hex(IFF_MAGIC),
            "header_size": record.header_size,
            "file_length_excluding_name_footer": record.file_length,
            "zero": record.zero,
            "block_count": record.block_count,
            "block_table_pointer_raw": record.unknown_14,
            "block_table_offset": 0x14 + record.unknown_14 - 1,
            "file_count": record.file_count,
            "file_pointer_table_raw": record.unknown_1c,
            "file_pointer_table_offset": 0x1C + record.unknown_1c - 1,
            "file_descriptor_pointer_values": list(record.file_header_offsets),
            "file_descriptor_offsets": list(record.file_descriptor_offsets),
            "unparsed_header_padding_size": record.header_padding_size,
        },
        "blocks": [
            {
                "descriptor_index": block.descriptor_index,
                "name_hash": _hex(block.name_hash),
                "name_label": _hash_label(block.name_hash),
                "type_hash": _hex(block.type_hash),
                "type_label": _hash_label(block.type_hash),
                "unknown_08": block.unknown_08,
                "uncompressed_length": block.uncompressed_length,
                "unknown_10": block.unknown_10,
                "start_offset": block.start_offset,
                "compressed_length": block.compressed_length,
                "stored_length": block.stored_length,
                "is_compressed": block.is_compressed,
                "indexed": block.indexed,
                "h7a": None
                if block.wrapper is None
                else {
                    "magic": _hex(block.wrapper.magic),
                    "uncompressed_length": block.wrapper.uncompressed_length,
                    "compressed_length": block.wrapper.compressed_length,
                    "unknown": block.wrapper.unknown,
                    "shift": block.wrapper.shift,
                },
            }
            for block in record.blocks
        ],
        "files": [
            {
                "index": file.index,
                "id": _hex(file.file_id),
                "type_hash": _hex(file.type_hash),
                "type_hash_label": _hash_label(file.type_hash),
                "name": file.name,
                "type_name": file.type_name,
                "asset_class": ASSET_CLASSES.get(file.type_name or "", "unknown"),
                "raw_offsets": list(file.offsets),
                "parts": [
                    {
                        "block_index": part.block_index,
                        "offset": part.offset,
                        "length": part.length,
                    }
                    for part in file.parts
                ],
            }
            for file in record.files
        ],
        "footer": None
        if record.footer is None
        else {
            "offset": record.footer.offset,
            "magic": _hex(record.footer.magic),
            "payload_size": record.footer.payload_size,
            "name_count": record.footer.name_count,
        },
        "warnings": record.warnings,
    }


def _non_iff_document(
    entry: apf_outer.Entry, outer_names: dict[int, list[dict[str, object]]]
) -> dict[str, object]:
    return {
        "table_index": entry.table_index,
        "name_id": _hex(entry.name_id),
        "outer_name_candidates": outer_names.get(entry.name_id, []),
        "virtual_offset": entry.virtual_offset,
        "outer_size": entry.size,
        "head_hex": entry.head_hex,
        "segments": [
            {
                "pack_name": segment.pack_name,
                "pack_offset": segment.pack_offset,
                "size": segment.size,
            }
            for segment in entry.segments
        ],
        "portme": "unknown non-IFF record; identify loader before decoding",
    }


def _summary(
    archive: apf_outer.Archive,
    records: list[IFFRecord],
    failures: list[dict[str, object]],
    outer_names: dict[int, list[dict[str, object]]],
) -> dict[str, object]:
    blocks = [block for record in records for block in record.blocks]
    files = [file for record in records for file in record.files]
    type_counts = Counter(file.type_name or "<unnamed>" for file in files)
    class_counts = Counter(
        ASSET_CLASSES.get(file.type_name or "", "unknown") for file in files
    )
    return {
        "outer_entry_count": len(archive.entries),
        "iff_head_count": sum(entry.head_hex == "ff3bef94" for entry in archive.entries),
        "parsed_iff_count": len(records),
        "parse_failure_count": len(failures),
        "outer_name_candidate_id_count": len(outer_names),
        "total_inner_file_count": len(files),
        "named_inner_file_count": sum(file.name is not None for file in files),
        "validated_inner_name_hash_count": sum(file.name is not None for file in files),
        "validated_inner_type_hash_count": sum(file.type_name is not None for file in files),
        "absent_part_sentinel_count": sum(
            offset == 0xFFFFFFFF for file in files for offset in file.offsets
        ),
        "compressed_block_count": sum(block.is_compressed for block in blocks),
        "uncompressed_block_count": sum(not block.is_compressed for block in blocks),
        "block_count_distribution": {
            str(key): value
            for key, value in sorted(Counter(record.block_count for record in records).items())
        },
        "h7a_shift_distribution": {
            str(key): value
            for key, value in sorted(
                Counter(
                    block.wrapper.shift
                    for block in blocks
                    if block.wrapper is not None
                ).items()
            )
        },
        "block_name_hash_counts": {
            f"{_hex(key)}:{_hash_label(key) or 'unknown'}": value
            for key, value in Counter(block.name_hash for block in blocks).most_common()
        },
        "inner_type_counts": dict(type_counts.most_common()),
        "asset_class_counts": dict(class_counts.most_common()),
        "records_with_warnings": sum(bool(record.warnings) for record in records),
    }


def _select_codec_samples(records: list[IFFRecord], count: int) -> list[tuple[IFFRecord, Block]]:
    candidates = [
        (record, block)
        for record in records
        for block in record.blocks
        if block.is_compressed and block.wrapper is not None
    ]
    candidates.sort(key=lambda item: (item[1].uncompressed_length, item[0].entry.table_index))
    selected: list[tuple[IFFRecord, Block]] = []
    seen_signatures: set[tuple[int, int, int, int]] = set()

    for pack_name in ("0A", "0B", "1A", "1B"):
        for candidate in candidates:
            record, block = candidate
            if record.entry.segments[0].pack_name == pack_name:
                selected.append(candidate)
                seen_signatures.add(
                    (
                        block.name_hash,
                        block.type_hash,
                        block.wrapper.shift if block.wrapper else -1,
                        block.uncompressed_length,
                    )
                )
                break
        if len(selected) >= count:
            return selected[:count]

    for candidate in candidates:
        record, block = candidate
        signature = (
            block.name_hash,
            block.type_hash,
            block.wrapper.shift if block.wrapper else -1,
            block.uncompressed_length,
        )
        if signature in seen_signatures:
            continue
        selected.append(candidate)
        seen_signatures.add(signature)
        if len(selected) >= count:
            break
    return selected[:count]


def verify_codec_samples(
    reader: ArchiveReader,
    records: list[IFFRecord],
    count: int,
    max_decompressed: int,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for record, block in _select_codec_samples(records, count):
        result: dict[str, object] = {
            "table_index": record.entry.table_index,
            "pack_name": record.entry.segments[0].pack_name,
            "block_index": block.descriptor_index,
            "name_hash": _hex(block.name_hash),
            "name_label": _hash_label(block.name_hash),
            "uncompressed_length": block.uncompressed_length,
            "compressed_length": block.compressed_length,
            "shift": block.wrapper.shift if block.wrapper else None,
        }
        try:
            decoded = decode_block(
                reader,
                record,
                block.descriptor_index,
                max_decompressed,
            )
            result["status"] = "ok"
            result["sha256"] = hashlib.sha256(decoded).hexdigest()
            result["head_hex"] = decoded[:16].hex()
        except FormatError as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
        results.append(result)
    return results


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned[:120] or "unnamed"


def dump_file_parts(
    reader: ArchiveReader,
    record: IFFRecord,
    file_index: int,
    output_dir: Path,
    max_decompressed: int,
    png_path: Path | None = None,
) -> list[Path]:
    try:
        file = record.files[file_index]
    except IndexError as exc:
        raise FormatError(
            f"entry {record.entry.table_index}: no inner file {file_index}"
        ) from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    base = _safe_component(file.name or f"file_{file.index:04d}")
    written: list[Path] = []
    metadata = {
        "outer_table_index": record.entry.table_index,
        "inner_file_index": file.index,
        "name": file.name,
        "type_name": file.type_name,
        "type_hash": _hex(file.type_hash),
        "asset_class": ASSET_CLASSES.get(file.type_name or "", "unknown"),
        "parts": [],
        "portme": (
            "TXTR import, remaining formats/mips/cube/3D layouts, and SCNE "
            "scene/mesh decoding remain before complete PNG/glTF round-tripping"
        ),
    }
    block_cache: dict[int, bytes] = {}
    part_payloads: list[tuple[FilePart, bytes]] = []
    png_error: FormatError | None = None
    for part in file.parts:
        if part.block_index not in block_cache:
            block_cache[part.block_index] = decode_block(
                reader, record, part.block_index, max_decompressed
            )
        block_data = block_cache[part.block_index]
        data = block_data[part.offset : part.offset + part.length]
        part_payloads.append((part, data))
        destination = output_dir / f"{base}.block{part.block_index}.bin"
        destination.write_bytes(data)
        written.append(destination)
        metadata["parts"].append(
            {
                "path": destination.name,
                "block_index": part.block_index,
                "offset": part.offset,
                "length": part.length,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    if file.type_name == "TXTR" and part_payloads:
        txtr_metadata = parse_txtr_metadata(part_payloads[0][1])
        metadata["txtr"] = txtr_metadata
        if png_path is not None:
            try:
                if len(part_payloads) >= 2:
                    base_data = part_payloads[1][1]
                    base_data_offset = 0
                else:
                    combined = part_payloads[0][1]
                    base_data_offset = _align_up(0xE0, 0x1000)
                    base_data = combined[base_data_offset:]
                width, height, rgba = decode_txtr_base_rgba(txtr_metadata, base_data)
                write_rgba_png(png_path, width, height, rgba)
                metadata["png"] = {
                    "status": "ok",
                    "path": str(png_path),
                    "width": width,
                    "height": height,
                    "base_data_offset_within_selected_part": base_data_offset,
                    "scope": "base mip only",
                }
                written.append(png_path)
            except FormatError as exc:
                png_error = exc
                metadata["png"] = {
                    "status": "failed",
                    "requested_path": str(png_path),
                    "error": str(exc),
                }
    elif png_path is not None:
        png_error = FormatError("--png requires a selected TXTR inner file")
        metadata["png"] = {
            "status": "failed",
            "requested_path": str(png_path),
            "error": str(png_error),
        }

    metadata_path = output_dir / f"{base}.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
    written.append(metadata_path)
    if png_error is not None:
        raise FormatError(f"{png_error}; metadata written to {metadata_path}")
    return written


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to APF first volume (0A)")
    parser.add_argument(
        "--entry",
        type=int,
        metavar="TABLE_INDEX",
        help="inspect only one outer table index",
    )
    parser.add_argument("--list", action="store_true", help="print compact TSV rows")
    parser.add_argument("--manifest", type=Path, help="write deterministic JSON report")
    parser.add_argument(
        "--inventory-tsv",
        type=Path,
        metavar="PATH",
        help="write one searchable row per parsed inner file",
    )
    parser.add_argument(
        "--decoded-executable",
        type=Path,
        metavar="PE",
        help="mine exact CRC32-matching outer names from the decoded APF PE",
    )
    parser.add_argument(
        "--verify-codec-samples",
        type=int,
        default=0,
        metavar="N",
        help="fully decode N small, stratified H7A samples",
    )
    parser.add_argument(
        "--max-decompressed",
        type=int,
        default=DEFAULT_MAX_DECOMPRESSED,
        metavar="BYTES",
        help="per-block decode ceiling (default: 256 MiB)",
    )
    parser.add_argument(
        "--dump-iff",
        type=Path,
        metavar="PATH",
        help="write the selected outer entry verbatim (requires --entry)",
    )
    parser.add_argument(
        "--dump-file",
        type=int,
        metavar="INNER_INDEX",
        help="decode and dump one selected IFF file's block parts (requires --entry)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="destination for --dump-file",
    )
    parser.add_argument(
        "--png",
        type=Path,
        metavar="PATH",
        help="convert the selected TXTR base mip to PNG (DXT1/3/5 or 8_8_8_8)",
    )
    parser.add_argument(
        "--lenient-footer",
        action="store_true",
        help="record malformed/unknown name footer details as warnings",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.entry is None and (args.dump_iff is not None or args.dump_file is not None):
        print("error: --dump-iff/--dump-file requires --entry", file=sys.stderr)
        return 2
    if args.dump_file is not None and args.output_dir is None:
        print("error: --dump-file requires --output-dir", file=sys.stderr)
        return 2
    if args.png is not None and args.dump_file is None:
        print("error: --png requires --dump-file", file=sys.stderr)
        return 2
    if args.verify_codec_samples < 0 or args.max_decompressed < 0:
        print("error: decode counts/limits cannot be negative", file=sys.stderr)
        return 2

    try:
        archive = apf_outer.parse_archive(args.index)
        selected_entries = list(archive.entries)
        if args.entry is not None:
            selected_entries = [
                entry for entry in archive.entries if entry.table_index == args.entry
            ]
            if not selected_entries:
                raise FormatError(f"no outer table index {args.entry}")

        outer_names: dict[int, list[dict[str, object]]] = {}
        executable_sha256 = None
        if args.decoded_executable is not None:
            outer_names, executable_sha256 = executable_name_candidates(
                args.decoded_executable, archive.entries
            )

        records: list[IFFRecord] = []
        failures: list[dict[str, object]] = []
        non_iff = [
            entry for entry in selected_entries if entry.head_hex != "ff3bef94"
        ]
        with ArchiveReader(archive) as reader:
            for entry in selected_entries:
                if entry.head_hex != "ff3bef94":
                    continue
                try:
                    records.append(
                        parse_iff(reader, entry, strict_footer=not args.lenient_footer)
                    )
                except FormatError as exc:
                    failures.append(
                        {
                            "table_index": entry.table_index,
                            "name_id": _hex(entry.name_id),
                            "error": str(exc),
                            "portme": "inspect malformed/variant IFF manually",
                        }
                    )

            codec_results = verify_codec_samples(
                reader,
                records,
                args.verify_codec_samples,
                args.max_decompressed,
            )

            if args.dump_iff is not None:
                entry = selected_entries[0]
                args.dump_iff.parent.mkdir(parents=True, exist_ok=True)
                args.dump_iff.write_bytes(reader.read(entry, 0, entry.size))
            dumped_paths: list[Path] = []
            if args.dump_file is not None:
                if not records:
                    raise FormatError("selected entry is not a parsed VC IFF")
                dumped_paths = dump_file_parts(
                    reader,
                    records[0],
                    args.dump_file,
                    args.output_dir,
                    args.max_decompressed,
                    args.png,
                )

        summary = _summary(archive, records, failures, outer_names)
        document = {
            "schema": "apf_inner_manifest/v1",
            "source_index": str(archive.index_path),
            "decoded_executable": None
            if args.decoded_executable is None
            else {
                "path": str(args.decoded_executable),
                "sha256": executable_sha256,
                "name_hash_algorithm": "CRC32 of uppercase ASCII path/basename",
            },
            "constants": {
                "iff_magic": _hex(IFF_MAGIC),
                "h7a_magic": _hex(H7A_MAGIC),
                "name_footer_magic": _hex(NAME_FOOTER_MAGIC),
                "inner_name_and_type_hash_algorithm": "CRC32 of case-sensitive ASCII text",
            },
            "summary": summary,
            "codec_verification": codec_results,
            "failures": failures,
            "non_iff_entries": [
                _non_iff_document(entry, outer_names) for entry in non_iff
            ],
            "iff_entries": [
                _record_document(record, outer_names) for record in records
            ],
            "portme": [
                "implement remaining Xenos TXTR formats, mip chains, cube/3D/stacked layouts, and reversible import",
                "decode SCNE geometry, skeleton, material, and animation records before glTF export",
                "identify AUDO codec/framing and map samples to standard audio containers",
                "classify non-IFF outer signatures and the semantic meaning of remaining unknown IFF fields",
            ],
        }

        if args.list:
            print(
                "table_index\tname_id\touter_name\touter_size\theader_size\t"
                "blocks\tfiles\ttypes\twarnings"
            )
            for record in records:
                candidates = outer_names.get(record.entry.name_id, [])
                outer_name = candidates[0]["name"] if candidates else ""
                types = Counter(file.type_name or "?" for file in record.files)
                type_text = ",".join(f"{key}:{value}" for key, value in types.most_common())
                print(
                    f"{record.entry.table_index}\t{_hex(record.entry.name_id)}\t"
                    f"{outer_name}\t{record.entry.size}\t{record.header_size}\t"
                    f"{record.block_count}\t{record.file_count}\t{type_text}\t"
                    f"{len(record.warnings)}"
                )
            for entry in non_iff:
                candidates = outer_names.get(entry.name_id, [])
                outer_name = candidates[0]["name"] if candidates else ""
                print(
                    f"{entry.table_index}\t{_hex(entry.name_id)}\t{outer_name}\t"
                    f"{entry.size}\t\t\t\tNON_IFF:{entry.head_hex}\t"
                )

        if args.manifest is not None:
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            args.manifest.write_text(
                json.dumps(document, indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
    newline="\n",
)

        if args.inventory_tsv is not None:
            args.inventory_tsv.parent.mkdir(parents=True, exist_ok=True)
            with args.inventory_tsv.open("w", encoding="utf-8", newline="") as output:
                output.write(
                    "outer_table_index\touter_name_id\touter_name_candidate\t"
                    "inner_index\tinner_name\ttype_name\ttype_hash\tasset_class\tparts\n"
                )
                for record in records:
                    candidates = outer_names.get(record.entry.name_id, [])
                    outer_name = str(candidates[0]["name"]) if candidates else ""
                    for file in record.files:
                        parts = ",".join(
                            f"b{part.block_index}:0x{part.offset:x}+0x{part.length:x}"
                            for part in file.parts
                        )
                        values = (
                            str(record.entry.table_index),
                            _hex(record.entry.name_id),
                            outer_name,
                            str(file.index),
                            file.name or "",
                            file.type_name or "",
                            _hex(file.type_hash),
                            ASSET_CLASSES.get(file.type_name or "", "unknown"),
                            parts,
                        )
                        output.write("\t".join(value.replace("\t", " ") for value in values) + "\n")

        print(
            f"APF inner: parsed {len(records)}/{summary['iff_head_count']} IFF heads; "
            f"{summary['total_inner_file_count']} inner files; "
            f"{summary['compressed_block_count']} compressed blocks; "
            f"{len(failures)} failures; {len(outer_names)} outer names matched"
        )
        if codec_results:
            passed = sum(result["status"] == "ok" for result in codec_results)
            print(f"H7A verification: {passed}/{len(codec_results)} samples passed")
        if args.dump_iff is not None:
            print(f"wrote IFF: {args.dump_iff}")
        for path in dumped_paths:
            print(f"wrote: {path}")
        return 1 if failures else 0
    except (apf_outer.FormatError, FormatError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
