#!/usr/bin/env python3
"""Resource-name inventory of the ESPN NFL 2K5 PlayStation 2 disc (SLUS-20919).

Opens a user's own ISO read-only, checks its identity against the digests the
capability registry pins, locates the ``/VC_20919`` resource packs, walks the
outer entry table and every 0x20-byte resource chunk inside it, and recovers
each object's name, type, size, offset and -- for textures -- GS pixel format
and dimensions.  With an Xbox resource-name inventory alongside it also emits
the PS2 <-> Xbox correspondence, which is a *name join*: both discs carry the
same Visual Concepts container, so a PS2 resource's Xbox counterpart is the
Xbox resource of the same name.  That correspondence is what a PCSX2
texture-replacement pack author lacks -- a GS hash dump has no names in it.

RETAIL-FREE BY CONSTRUCTION
---------------------------
Every resource chunk stores ``system_bytes`` of metadata followed by
``video_bytes`` of pixel or sample payload, in that order, inside one optional
LZ stream.  This tool decodes at most ``system_bytes`` of output and reads at
most the compressed bytes that could possibly produce them, so pixels and
audio are never read off the disc, never decompressed and never emitted.  The
outputs carry names, FourCCs, sizes, offsets, dimensions and digests only.  The
self-test plants a payload sentinel and proves no output contains it.

Nothing is written outside the paths given on the command line; the ISO is
opened read-only and its size is re-checked afterwards.

PS2 FORMAT NOTES (established against the retail disc)
------------------------------------------------------
* The outer pack container is byte-identical to the Xbox build's: 12-byte
  header, 36 pack-size slots (in 0x800 blocks), 12-byte entry records
  ``(name_id, size, offset_blocks)``, entries 0x800-aligned.  The packs are the
  files ``/VC_20919/0.`` .. ``/VC_20919/4.`` and are addressed as one virtual
  byte range, so an entry may straddle two packs.
* A resource chunk header is 0x20 bytes: FourCC, stored_size, system_bytes,
  video_bytes, then ``0xFEEDBEEF`` when the body is LZ-compressed.
* VC objects carry a FourCC at +0x0C and *field-local, minus-one-biased*
  relative pointers: ``target = field + s32 - 1``.  +0x10 points at the
  object's UTF-16LE name, +0x14 at its descriptor.
* The TXTR descriptor is PS2-specific and 0x38 bytes: GS TEX0 at +0x00 (PSM
  at bits 20..25, TW 26..29, TH 30..33, CPSM 51..54), MIPTBP1 at +0x08,
  MIPTBP2 at +0x10, and the authoritative texel width/height as u16 at
  +0x2C/+0x2E.  TEX0's TW/TH agree with that pair except for atlases taller
  than the GS's 1024-texel ceiling, where TEX0 clamps.  The Xbox build packs a
  D3DFORMAT bitfield here instead.
* A TSET is a versioned table (version 0x0D) of embedded TXTR records, 0x24
  bytes each from +0x18: marker, name pointer, descriptor pointer.
* SCNE table strides differ from the Xbox build: texture 0x38, material 0x60
  (name at +0x58), node 0x60, shape 0x70, marker 0x40.

USAGE
-----
    python3 tools/nfl2k5_ps2_disc_inventory.py --iso <SLUS-20919.iso> \\
        --json <report.json> --csv <inventory.csv> \\
        [--xbox-inventory <xbox_inventory.tsv|.csv[.gz]> --join-csv <join.csv>] \\
        [--hash-image] [--require-retail] [--jobs N] [--limit N]
    python3 tools/nfl2k5_ps2_disc_inventory.py --selftest

Python 3.9 compatible, standard library only.  Imports its sibling
``tools/ps2_iso9660.py`` with its own directory placed on ``sys.path`` first,
because the installed Windows runtime does not add it.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ps2_iso9660 as iso  # noqa: E402

__all__ = [
    "SERIAL", "RETAIL_BOOT_ELF_SHA256", "RETAIL_IMAGE_SHA256", "SCHEMA",
    "InventoryError", "decompress_prefix", "compress", "texture_geometry",
    "name_key", "inventory", "load_name_side", "name_join", "selftest", "main",
]

SCHEMA = "nfl2k5_ps2_disc_inventory/v1"
SERIAL = "SLUS-20919"
PACK_DIRECTORY = "/VC_20919"

# Pinned identity of the supported retail image.  These duplicate
# mod_editor/capabilities/registry.v1.json games[nfl2k5_ps2].retail_identity
# (and mod_editor/core/sources.py) on purpose: a shipped tool may import only
# its own siblings, and tests/mod_editor/test_nfl2k5_ps2_disc_inventory.py
# asserts the three stay equal.
RETAIL_BOOT_ELF_SHA256 = "e8c3ba9a3224d567e3abb50c91e9d6fdd9820138226c05e525f9dbf34a47d8aa"
RETAIL_IMAGE_SHA256 = "f1300699ab445ad04b1e27f6e2df87f7a4d1d080d06c7d73499e1be9618a4ebe"

# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

ALIGNMENT = 0x800
PACK_SLOT_COUNT = 36
PACK_NAMES = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
OUTER_HEADER_SIZE = 0x0C + PACK_SLOT_COUNT * 4          # 156
OUTER_ENTRY_SIZE = 12
MAX_OUTER_ENTRIES = 1 << 20

CHUNK_HEADER_SIZE = 0x20
COMPRESSED_SENTINEL = 0xFEEDBEEF
MAX_ZERO_PADDING_SCAN = 0x100000

METADATA_CAP = 1 << 20          # never decode more than 1 MiB of system buffer
NO_SYSTEM_PREFIX = 0x200        # chunks that declare system_bytes == 0

TSET_VERSION = 0x0D
TSET_REF_BASE = 0x18
TSET_REF_STRIDE = 0x24

TXTR_DESCRIPTOR_SIZE = 0x38
SCNE_DESCRIPTOR_SIZE = 0x54
MAX_TABLE_RECORDS = 1_000_000
# key, count offset, pointer offset, stride, name-field offsets in the record
SCNE_TABLES = (
    ("texture", 0x14, 0x18, 0x38, ()),
    ("material", 0x1C, 0x20, 0x60, (0x58,)),
    ("node", 0x24, 0x28, 0x60, (0x00, 0x04)),
    ("shape", 0x2C, 0x30, 0x70, (0x40,)),
    ("marker", 0x34, 0x38, 0x40, (0x00, 0x30)),
)

# PlayStation 2 Graphics Synthesiser pixel storage modes.
GS_PSM = {
    0x00: "PSMCT32", 0x01: "PSMCT24", 0x02: "PSMCT16", 0x0A: "PSMCT16S",
    0x13: "PSMT8", 0x14: "PSMT4", 0x1B: "PSMT8H", 0x24: "PSMT4HL",
    0x2C: "PSMT4HH", 0x30: "PSMZ32", 0x31: "PSMZ24", 0x32: "PSMZ16",
    0x3A: "PSMZ16S",
}

COLUMNS = ["pack", "entry_index", "name", "name_key", "fourcc", "size",
           "width", "height", "format", "extra"]
JOIN_COLUMNS = ["name_key", "presence",
                "ps2_rows", "ps2_fourccs", "ps2_formats", "ps2_dims",
                "xbox_rows", "xbox_fourccs", "xbox_formats", "xbox_dims"]


class InventoryError(ValueError):
    """A refusal with a sentence attached; never a silent partial result."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise InventoryError(message)


# ---------------------------------------------------------------------------
# Bit-level helpers
# ---------------------------------------------------------------------------

def printable_fourcc(value: bytes) -> bool:
    return len(value) == 4 and all(0x20 <= byte <= 0x7E for byte in value)


def s32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def relative_pointer(data: bytes, field: int, limit: int) -> Optional[int]:
    """VC's field-local, minus-one-biased relative pointer.  None when null."""
    if field < 0 or field + 4 > limit:
        return None
    value = s32(data, field)
    if value == 0:
        return None
    target = field + value - 1
    if not 0 <= target < limit:
        return None
    return target


def utf16z(data: bytes, offset: Optional[int], limit: int) -> Optional[str]:
    """Null-terminated UTF-16LE string, or None when it is not one."""
    if offset is None or offset % 2 or not 0 <= offset < limit:
        return None
    end = offset
    while end + 1 < limit and data[end:end + 2] != b"\0\0":
        end += 2
    if end + 1 >= limit or end == offset:
        return None
    try:
        value = data[offset:end].decode("utf-16le")
    except UnicodeDecodeError:
        return None
    if not value or not all(character.isprintable() for character in value):
        return None
    return value


def pointer_name(data: bytes, field: int, limit: int) -> Optional[str]:
    return utf16z(data, relative_pointer(data, field, limit), limit)


def name_key(name: Optional[str]) -> str:
    """The join key: the name with surrounding whitespace dropped, upper-cased.

    Both discs are inventoried with this same rule, and the recorded
    correspondence (24,187 shared keys, 99.60% of the Xbox disc's 24,285) was
    measured under it.
    """
    return (name or "").strip().upper()


# ---------------------------------------------------------------------------
# VC-LZ: prefix decoder (the tool) and a small encoder (the self-test)
# ---------------------------------------------------------------------------

def decompress_prefix(stream: bytes, want: int) -> bytes:
    """VC-LZ decode, stopping the instant ``want`` output bytes exist.

    Matches copy backwards out of already-produced output, exactly as the game
    does, so this prefix is byte-identical to a full decode's prefix.  Bytes
    past ``want`` -- the pixel / sample payload -- are never produced.
    """
    if len(stream) < 10:
        raise InventoryError("compressed stream shorter than its 10-byte prefix")
    output_size = struct.unpack_from("<I", stream, 0)[0]
    offset_bits = stream[8]
    if not 1 <= offset_bits <= 15:
        raise InventoryError("invalid offset bit count %d" % offset_bits)
    length_bits = 16 - offset_bits
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << length_bits) - 1

    want = min(want, output_size)
    out = bytearray(want)
    src = 9
    flags = stream[src]
    src += 1
    flag_mask = 1
    dst = 0
    while dst < want:
        if flags & flag_mask:
            if src + 2 > len(stream):
                raise InventoryError("truncated match token")
            code = struct.unpack_from("<H", stream, src)[0]
            src += 2
            distance = code & distance_mask
            length = ((code >> offset_bits) & length_mask) + 3
            if distance == 0 or distance > dst:
                raise InventoryError("invalid match distance")
            for index in range(length - 1, -1, -1):
                position = dst + index
                if position < want:
                    out[position] = out[position - distance]
            dst += length
        else:
            if src >= len(stream):
                raise InventoryError("truncated literal")
            out[dst] = stream[src]
            src += 1
            dst += 1
        flag_mask = (flag_mask << 1) & 0xFF
        if flag_mask == 0 and dst < want:
            if src >= len(stream):
                raise InventoryError("missing flag byte")
            flags = stream[src]
            src += 1
            flag_mask = 1
    return bytes(out[:want])


def compress(data: bytes, offset_bits: int = 12) -> bytes:
    """A greedy VC-LZ encoder, good enough to build self-test fixtures.

    It is the inverse of ``decompress_prefix`` for the whole buffer: header
    ``u32 output_size``, four reserved bytes, ``u8 offset_bits``, then groups
    of one flag byte and up to eight tokens (bit set = ``u16`` match with the
    distance in the low ``offset_bits`` and ``length - 3`` above it; bit clear
    = one literal byte).  Never used on game data; it exists so the LZ path of
    the walk is exercised without a disc.
    """
    _require(1 <= offset_bits <= 15, "offset_bits must be 1..15")
    length_bits = 16 - offset_bits
    max_distance = (1 << offset_bits) - 1
    max_length = ((1 << length_bits) - 1) + 3
    tokens: List[Tuple[bool, bytes]] = []
    position = 0
    while position < len(data):
        best_length = 0
        best_distance = 0
        window_start = max(0, position - max_distance)
        for candidate in range(window_start, position):
            # The decoder copies a match back-to-front, so a match may not
            # overlap the bytes it is producing: cap it at the distance.
            longest = min(max_length, len(data) - position, position - candidate)
            length = 0
            while (length < longest
                   and data[candidate + length] == data[position + length]):
                length += 1
            if length > best_length:
                best_length, best_distance = length, position - candidate
        if best_length >= 3:
            code = best_distance | ((best_length - 3) << offset_bits)
            tokens.append((True, struct.pack("<H", code)))
            position += best_length
        else:
            tokens.append((False, data[position:position + 1]))
            position += 1
    out = bytearray(struct.pack("<I", len(data)) + bytes(4) + bytes([offset_bits]))
    for group in range(0, len(tokens), 8):
        flags = 0
        body = bytearray()
        for bit, (is_match, payload) in enumerate(tokens[group:group + 8]):
            if is_match:
                flags |= 1 << bit
            body.extend(payload)
        out.append(flags)
        out.extend(body)
    return bytes(out)


# ---------------------------------------------------------------------------
# Virtual archive over the ISO's pack extents
# ---------------------------------------------------------------------------

class VirtualPacks:
    """Concatenation of /VC_20919/0. .. N. addressed by virtual byte offset.

    Reads go through one plain file handle per process (seek + read), which
    every platform the product ships on provides; the image is never opened for
    writing.
    """

    def __init__(self, iso_path: str, packs: Sequence[Tuple[str, int, int]]):
        self.iso_path = iso_path
        self.packs = list(packs)                 # [(name, iso_byte_base, size)]
        self.starts = [0]
        for _, _, size in self.packs:
            self.starts.append(self.starts[-1] + size)
        self.handle = None

    def open(self) -> None:
        if self.handle is None:
            self.handle = open(self.iso_path, "rb")

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    @property
    def size(self) -> int:
        return self.starts[-1]

    def pack_of(self, virtual_offset: int) -> int:
        for index in range(len(self.packs) - 1, -1, -1):
            if self.starts[index] <= virtual_offset:
                return index
        raise InventoryError("negative virtual offset")

    def read(self, virtual_offset: int, size: int) -> bytes:
        if size <= 0:
            return b""
        if virtual_offset < 0 or virtual_offset + size > self.starts[-1]:
            raise InventoryError("read outside the virtual archive")
        self.open()
        parts = []
        while size:
            index = self.pack_of(virtual_offset)
            inside = virtual_offset - self.starts[index]
            take = min(size, self.packs[index][2] - inside)
            self.handle.seek(self.packs[index][1] + inside)
            block = self.handle.read(take)
            if len(block) != take:
                raise InventoryError("short read from pack %s" % self.packs[index][0])
            parts.append(block)
            virtual_offset += take
            size -= take
        return b"".join(parts)


# ---------------------------------------------------------------------------
# PS2 texture descriptor
# ---------------------------------------------------------------------------

def mip_levels(data: bytes, descriptor: int) -> Optional[int]:
    """1 + the number of GS MIPTBP entries in use, or None when unreadable.

    MIPTBP1 holds TBP1..TBP3 and MIPTBP2 TBP4..TBP6, each 14 bits at
    bit 0 / 20 / 40 of its 64-bit register.  A level is in use when its TBP is
    nonzero; the levels must be strictly increasing addresses and, once one is
    zero, all later ones must be too.  Anything else is reported as unknown
    rather than guessed at.
    """
    low1, high1, low2, high2 = struct.unpack_from("<4I", data, descriptor + 8)
    register1 = low1 | (high1 << 32)
    register2 = low2 | (high2 << 32)
    if register1 == 0:
        return 1
    pointers = [
        (register1 >> 0) & 0x3FFF, (register1 >> 20) & 0x3FFF,
        (register1 >> 40) & 0x3FFF,
        (register2 >> 0) & 0x3FFF, (register2 >> 20) & 0x3FFF,
        (register2 >> 40) & 0x3FFF,
    ]
    used = 0
    for index, pointer in enumerate(pointers):
        if pointer == 0:
            break
        if index and pointer <= pointers[index - 1]:
            return None
        used += 1
    if any(pointers[used:]):
        return None
    return 1 + used


def texture_geometry(data: bytes, descriptor: Optional[int], limit: int) -> Optional[dict]:
    """Decode one PS2 TXTR descriptor from its header bytes alone."""
    if descriptor is None or descriptor + TXTR_DESCRIPTOR_SIZE > limit:
        return None
    low, high = struct.unpack_from("<II", data, descriptor)
    tex0 = low | (high << 32)
    psm = (tex0 >> 20) & 0x3F
    tex0_width = 1 << ((tex0 >> 26) & 0xF)
    tex0_height = 1 << ((tex0 >> 30) & 0xF)
    clut_psm = (tex0 >> 51) & 0xF
    width, height = struct.unpack_from("<HH", data, descriptor + 0x2C)
    try:
        mips = mip_levels(data, descriptor)
    except struct.error:
        mips = None
    return {
        "width": width,
        "height": height,
        "format": GS_PSM.get(psm, "GS_PSM_0x%02X" % psm),
        "clut_format": GS_PSM.get(clut_psm, "GS_PSM_0x%02X" % clut_psm),
        "tex0_width": tex0_width,
        "tex0_height": tex0_height,
        "mips": mips,
        "tex0": tex0,
        "descriptor_offset": descriptor,
    }


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------

def make_row(name: Optional[str], fourcc: str, size, geometry: Optional[dict],
             extra: dict) -> dict:
    name = name or ""
    row = {
        "name": name,
        "name_key": name_key(name),
        "fourcc": fourcc,
        "size": "" if size is None or size == "" else int(size),
        "width": "", "height": "", "format": "",
    }
    if geometry is not None:
        extra = dict(extra)
        if geometry["width"] and geometry["height"]:
            row["width"] = geometry["width"]
            row["height"] = geometry["height"]
        row["format"] = geometry["format"]
        extra["clut"] = geometry["clut_format"]
        if geometry["mips"] is not None:
            extra["mips"] = geometry["mips"]
        if (geometry["tex0_width"] != geometry["width"]
                or geometry["tex0_height"] != geometry["height"]):
            extra["tex0wh"] = "%dx%d" % (geometry["tex0_width"],
                                         geometry["tex0_height"])
        extra["tex0"] = "0x%016x" % geometry["tex0"]
        extra["desc"] = "0x%x" % geometry["descriptor_offset"]
    row["extra"] = ";".join("%s=%s" % (key, value) for key, value in extra.items())
    return row


# ---------------------------------------------------------------------------
# Sub-object walks
# ---------------------------------------------------------------------------

def walk_tset(system: bytes, limit: int, rows: list, base_extra: dict,
              stats: Counter) -> None:
    """A TSET is a versioned table of embedded TXTR object records."""
    if limit < TSET_REF_BASE + TSET_REF_STRIDE:
        return
    version, count = struct.unpack_from("<II", system, 0)
    if version != TSET_VERSION:
        stats["tset_bad_version"] += 1
        return
    if count == 0 or count > 4096 or TSET_REF_BASE + count * TSET_REF_STRIDE > limit:
        stats["tset_bad_count"] += 1
        return
    for index in range(count):
        record = TSET_REF_BASE + index * TSET_REF_STRIDE
        if system[record:record + 4] != b"TXTR":
            stats["tset_missing_marker"] += 1
            continue
        name = pointer_name(system, record + 4, limit)
        geometry = texture_geometry(
            system, relative_pointer(system, record + 8, limit), limit)
        rows.append(make_row(
            name, "TXTR", "", geometry,
            dict(base_extra, role="tset_texture", idx=index, rec="0x%x" % record)))
        stats["tset_texture"] += 1


def walk_scne(system: bytes, limit: int, rows: list, base_extra: dict,
              scene_name: Optional[str], stats: Counter) -> None:
    descriptor = relative_pointer(system, 0x14, limit)
    if descriptor is None or descriptor + SCNE_DESCRIPTOR_SIZE > limit:
        stats["scne_no_descriptor"] += 1
        return
    for key, count_offset, pointer_offset, stride, name_fields in SCNE_TABLES:
        count = u32(system, descriptor + count_offset)
        if count == 0:
            continue
        if count > MAX_TABLE_RECORDS:
            stats["scne_bad_count"] += 1
            continue
        start = relative_pointer(system, descriptor + pointer_offset, limit)
        if start is None or start + count * stride > limit:
            stats["scne_table_out_of_bounds"] += 1
            continue
        for index in range(count):
            record = start + index * stride
            if key == "texture":
                geometry = texture_geometry(system, record, limit)
                rows.append(make_row(
                    "%s/embedded_%04d" % (scene_name or "", index), "TXTR", "",
                    geometry,
                    dict(base_extra, role="scne_texture", idx=index,
                         rec="0x%x" % record)))
                stats["scne_texture"] += 1
                continue
            primary = None
            for slot, field in enumerate(name_fields):
                name = pointer_name(system, record + field, limit)
                if name is None:
                    stats["scne_%s_unnamed" % key] += 1
                    continue
                if slot and name == primary:
                    continue
                if slot == 0:
                    primary = name
                role = "scne_%s%s" % (key, "" if slot == 0 else "_alt")
                rows.append(make_row(
                    name, "SCNE", "", None,
                    dict(base_extra, role=role, idx=index, rec="0x%x" % record)))
                stats[role] += 1


# ---------------------------------------------------------------------------
# Per-entry work (runs in worker processes)
# ---------------------------------------------------------------------------

_state: dict = {}


def initialise(iso_path: str, packs: Sequence[Tuple[str, int, int]],
               entries: Sequence[Tuple[int, int, int]]) -> None:
    _state["archive"] = VirtualPacks(iso_path, packs)
    _state["entries"] = list(entries)


def find_after_zero_padding(archive: VirtualPacks, virtual_base: int,
                            entry_size: int, offset: int) -> Optional[int]:
    """First 0x10-aligned, fully bounded chunk header after an all-zero gap."""
    scan_end = min(entry_size, offset + MAX_ZERO_PADDING_SCAN)
    cursor = offset
    while cursor < scan_end:
        size = min(0x4000, scan_end - cursor)
        block = archive.read(virtual_base + cursor, size)
        relative = next((i for i, v in enumerate(block) if v), None)
        if relative is None:
            cursor += size
            continue
        candidate = cursor + relative
        if candidate % 0x10 or entry_size - candidate < CHUNK_HEADER_SIZE:
            return None
        header = archive.read(virtual_base + candidate, CHUNK_HEADER_SIZE)
        stored = u32(header, 4)
        if (printable_fourcc(header[:4]) and stored
                and candidate + CHUNK_HEADER_SIZE + stored <= entry_size):
            return candidate
        return None
    return None


def process_entry(index: int) -> dict:
    archive = _state["archive"]
    name_id, entry_size, offset_blocks = _state["entries"][index]
    virtual_base = offset_blocks * ALIGNMENT
    pack_name = archive.packs[archive.pack_of(virtual_base)][0]
    rows: List[dict] = []
    errors: List[dict] = []
    stats: Counter = Counter()

    offset = 0
    chunk_index = 0
    padding_before = 0
    while entry_size - offset >= CHUNK_HEADER_SIZE:
        header = archive.read(virtual_base + offset, CHUNK_HEADER_SIZE)
        fourcc = header[:4]
        stored, system_bytes, video_bytes, magic = struct.unpack_from("<4I", header, 4)
        bounded = (printable_fourcc(fourcc) and stored
                   and offset + CHUNK_HEADER_SIZE + stored <= entry_size)
        if not bounded:
            successor = find_after_zero_padding(
                archive, virtual_base, entry_size, offset)
            if successor is None:
                break
            padding_before = successor - offset
            offset = successor
            continue

        compressed = magic == COMPRESSED_SENTINEL
        limit = min(system_bytes if system_bytes else NO_SYSTEM_PREFIX, METADATA_CAP)
        if not compressed:
            limit = min(limit, stored)
        kind = fourcc.decode("ascii")
        base_extra = {
            "id": "0x%08x" % name_id,
            "chunk": chunk_index,
            "coff": "0x%x" % offset,
            "voff": "0x%x" % (virtual_base + offset),
            "sys": system_bytes,
            "vid": video_bytes,
            "lz": 1 if compressed else 0,
        }
        if padding_before:
            base_extra["pad"] = padding_before
            padding_before = 0

        system = b""
        inner = ""
        object_name = None
        try:
            if compressed:
                # upper bound on compressed bytes able to yield `limit` output
                need = 10 + limit + (limit + 7) // 8 + 16
                body = archive.read(virtual_base + offset + CHUNK_HEADER_SIZE,
                                    min(stored, need))
                system = decompress_prefix(body, limit)
            else:
                system = archive.read(
                    virtual_base + offset + CHUNK_HEADER_SIZE, limit)
        except (InventoryError, struct.error) as exc:
            errors.append({"entry": index, "chunk": chunk_index,
                           "fourcc": kind, "error": str(exc)})
            stats["decode_failed"] += 1

        available = len(system)
        if available >= 0x18 and printable_fourcc(system[0x0C:0x10]):
            inner = system[0x0C:0x10].decode("ascii")
            object_name = pointer_name(system, 0x10, available)
            base_extra["obj"] = inner

        geometry = None
        if inner == "TXTR":
            geometry = texture_geometry(
                system, relative_pointer(system, 0x14, available), available)
            if geometry is None:
                stats["txtr_no_descriptor"] += 1

        rows.append(make_row(object_name, kind, stored, geometry,
                             dict(base_extra, role="chunk")))
        stats["chunk"] += 1

        sub_extra = {"id": base_extra["id"], "chunk": chunk_index,
                     "coff": base_extra["coff"]}
        try:
            if kind == "TSET":
                walk_tset(system, available, rows, sub_extra, stats)
            if inner == "SCNE":
                walk_scne(system, available, rows, sub_extra, object_name, stats)
        except (struct.error, ValueError) as exc:
            errors.append({"entry": index, "chunk": chunk_index, "fourcc": kind,
                           "error": "sub-object walk: %s" % exc})
            stats["sub_walk_failed"] += 1

        offset += CHUNK_HEADER_SIZE + stored
        chunk_index += 1

    trailing = entry_size - offset if chunk_index else 0
    if chunk_index == 0:
        head = archive.read(virtual_base, min(16, entry_size))
        rows.append(make_row(
            None, head[:4].decode("ascii") if printable_fourcc(head[:4]) else "",
            entry_size, None,
            {"id": "0x%08x" % name_id, "chunk": 0, "coff": "0x0",
             "voff": "0x%x" % virtual_base, "role": "unstructured_entry",
             "head": head[:8].hex()}))

    for row in rows:
        row["pack"] = pack_name
        row["entry_index"] = index
    return {
        "rows": rows, "errors": errors, "stats": dict(stats),
        "chunks": chunk_index, "trailing": trailing,
        "entry_size": entry_size, "name_id": name_id,
        "virtual_offset": virtual_base, "pack": pack_name,
    }


# ---------------------------------------------------------------------------
# Disc-level discovery
# ---------------------------------------------------------------------------

def discover_packs(image) -> List[Tuple[str, int, int]]:
    """``[(name, iso_byte_offset, size)]`` for /VC_20919/0. .. N., in order."""
    packs = []
    for letter in PACK_NAMES:
        found = iso.find(image, "%s/%s." % (PACK_DIRECTORY, letter))
        if found is None:
            found = iso.find(image, "%s/%s" % (PACK_DIRECTORY, letter))
        if found is None or found.is_dir:
            break
        packs.append((letter, iso.extent_byte_offset(image, found.lba), found.length))
    _require(packs, "no %s packs found; this is not a SLUS-20919 resource layout"
             % PACK_DIRECTORY)
    return packs


def read_outer_table(archive: VirtualPacks) -> Tuple[dict, List[Tuple[int, int, int]]]:
    header = archive.read(0, OUTER_HEADER_SIZE)
    entry_count, reserved, populated = struct.unpack_from("<III", header, 0)
    block_counts = struct.unpack_from("<%dI" % PACK_SLOT_COUNT, header, 12)
    _require(populated == len(archive.packs),
             "outer index declares %d packs, the ISO has %d"
             % (populated, len(archive.packs)))
    for ordinal, (letter, _base, size) in enumerate(archive.packs):
        _require(block_counts[ordinal] * ALIGNMENT == size,
                 "pack %s: index says %d bytes, ISO says %d"
                 % (letter, block_counts[ordinal] * ALIGNMENT, size))
    _require(0 < entry_count <= MAX_OUTER_ENTRIES,
             "outer index declares %d entries" % entry_count)
    table = archive.read(OUTER_HEADER_SIZE, entry_count * OUTER_ENTRY_SIZE)
    entries = [struct.unpack_from("<III", table, i * OUTER_ENTRY_SIZE)
               for i in range(entry_count)]
    for index, (_name_id, size, offset_blocks) in enumerate(entries):
        _require(offset_blocks * ALIGNMENT + size <= archive.size,
                 "outer entry %d runs past the packs" % index)
    outer = {"entry_count": entry_count, "reserved": reserved,
             "populated_pack_count": populated, "block_counts": list(block_counts)}
    return outer, entries


def image_identity(image, hash_image: bool) -> dict:
    """Boot identity plus the comparison against the registry's pins."""
    identity = iso.boot_identity(image)
    result = {
        "boot2": identity["boot2"],
        "boot_file": identity["boot_file"],
        "serial": identity["serial"],
        "boot_size": identity["boot_size"],
        "boot_sha256": identity["boot_sha256"],
        "expected_serial": SERIAL,
        "serial_matches": identity["serial"] == SERIAL,
        "retail_boot_elf": identity["boot_sha256"] == RETAIL_BOOT_ELF_SHA256,
        "image_sha256": None,
        "retail_image": None,
    }
    if hash_image:
        digest = hashlib.sha256()
        with open(image.path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 22), b""):
                digest.update(block)
        result["image_sha256"] = digest.hexdigest()
        result["retail_image"] = result["image_sha256"] == RETAIL_IMAGE_SHA256
    return result


# ---------------------------------------------------------------------------
# The name side of the join
# ---------------------------------------------------------------------------

class NameSide:
    """Per-name-key aggregate of one disc's rows: what a join needs, no more."""

    def __init__(self) -> None:
        self.keys: Dict[str, list] = {}

    def add(self, key: str, fourcc: str, fmt: str, width, height) -> None:
        if not key:
            return
        slot = self.keys.get(key)
        if slot is None:
            slot = [0, Counter(), Counter(), set()]
            self.keys[key] = slot
        slot[0] += 1
        slot[1][fourcc or "<none>"] += 1
        if fmt:
            slot[2][fmt] += 1
        if width not in ("", None) and height not in ("", None):
            slot[3].add("%sx%s" % (width, height))

    def add_row(self, row: dict) -> None:
        self.add(row["name_key"], row["fourcc"], row["format"],
                 row["width"], row["height"])

    def describe(self, key: str) -> Tuple[str, str, str, str]:
        rows, fourccs, formats, dims = self.keys[key]
        return (
            str(rows),
            "|".join("%s:%d" % item for item in sorted(fourccs.items())),
            "|".join("%s:%d" % item for item in sorted(formats.items())),
            "|".join(sorted(dims)),
        )


def _open_text(path: str):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")


def load_name_side(path: str) -> Tuple[NameSide, dict]:
    """Read a resource-name inventory (this tool's CSV, or the Xbox one).

    Accepts ``.csv`` / ``.tsv`` (optionally ``.gz``) with a header row that
    names at least ``name_key`` or ``name``; ``fourcc``, ``format``, ``width``
    and ``height`` are used when present.  Returns the aggregate and a small
    provenance block (basename, size, digest, row count) for the report.
    """
    _require(os.path.isfile(path), "inventory is not a file: %s" % path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    stem = path[:-3] if path.endswith(".gz") else path
    delimiter = "\t" if stem.lower().endswith(".tsv") else ","
    side = NameSide()
    rows = 0
    with _open_text(path) as stream:
        reader = csv.reader(stream, delimiter=delimiter)
        header = next(reader, None)
        _require(header is not None, "inventory has no header row: %s" % path)
        columns = {column.strip(): index for index, column in enumerate(header)}
        _require("name_key" in columns or "name" in columns,
                 "inventory header lacks name_key/name: %s" % path)

        def cell(record, column):
            index = columns.get(column)
            return record[index] if index is not None and index < len(record) else ""

        for record in reader:
            rows += 1
            key = cell(record, "name_key") or name_key(cell(record, "name"))
            side.add(key, cell(record, "fourcc"), cell(record, "format"),
                     cell(record, "width"), cell(record, "height"))
    provenance = {
        "name": os.path.basename(path),
        "size_bytes": os.path.getsize(path),
        "sha256": digest.hexdigest(),
        "rows": rows,
        "distinct_name_keys": len(side.keys),
    }
    return side, provenance


def name_join(ps2: NameSide, xbox: NameSide) -> Tuple[List[list], dict]:
    """Rows for every name key on either disc, plus the counts."""
    keys = sorted(set(ps2.keys) | set(xbox.keys))
    rows = []
    shared = ps2_only = xbox_only = 0
    blank = ("", "", "", "")
    for key in keys:
        in_ps2 = key in ps2.keys
        in_xbox = key in xbox.keys
        if in_ps2 and in_xbox:
            presence = "both"
            shared += 1
        elif in_ps2:
            presence = "ps2_only"
            ps2_only += 1
        else:
            presence = "xbox_only"
            xbox_only += 1
        rows.append([key, presence,
                     *(ps2.describe(key) if in_ps2 else blank),
                     *(xbox.describe(key) if in_xbox else blank)])
    xbox_total = len(xbox.keys)
    summary = {
        "join_key": "name_key = name.strip().upper(); rows without a name never join",
        "ps2_name_keys": len(ps2.keys),
        "xbox_name_keys": xbox_total,
        "shared": shared,
        "ps2_only": ps2_only,
        "xbox_only": xbox_only,
        "xbox_keys_matched_percent": (round(100.0 * shared / xbox_total, 2)
                                      if xbox_total else None),
    }
    return rows, summary


def write_join_csv(path: str, rows: Iterable[list]) -> int:
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(JOIN_COLUMNS)
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


# ---------------------------------------------------------------------------
# The inventory itself
# ---------------------------------------------------------------------------

def _entry_results(iso_path: str, packs, entries, indices, jobs: int, progress):
    """Yield per-entry results in entry order, in-process or across workers."""
    if jobs <= 1:
        initialise(iso_path, packs, entries)
        try:
            for position, index in enumerate(indices):
                if progress and position % 500 == 0:
                    progress("entry %d/%d" % (position, len(indices)))
                yield process_entry(index)
        finally:
            _state["archive"].close()
        return
    with ProcessPoolExecutor(max_workers=jobs, initializer=initialise,
                             initargs=(iso_path, packs, entries)) as pool:
        for position, result in enumerate(pool.map(process_entry, indices, chunksize=4)):
            if progress and position % 500 == 0:
                progress("entry %d/%d" % (position, len(indices)))
            yield result


def inventory(iso_path: str, *, csv_path: Optional[str] = None,
              jobs: int = 1, limit: int = 0, hash_image: bool = False,
              progress=None) -> Tuple[dict, NameSide]:
    """Inventory one disc.  Returns the JSON-ready report and the name side.

    Rows stream straight into ``csv_path`` as each entry completes, so memory
    stays flat over a 550,000-row disc; only censuses and the per-name
    aggregate are kept.
    """
    stat_before = os.stat(iso_path)
    image = iso.open_image(iso_path)
    identity = image_identity(image, hash_image)

    filesystem = [
        {"path": entry.path, "kind": "dir" if entry.is_dir else "file",
         "lba": entry.lba, "size": entry.length}
        for entry in iso.iter_entries(image)
    ]
    packs = discover_packs(image)
    archive = VirtualPacks(iso_path, packs)
    try:
        outer, entries = read_outer_table(archive)
    finally:
        archive.close()

    indices = list(range(len(entries) if not limit else min(limit, len(entries))))

    fourcc_census: Counter = Counter()
    chunk_fourcc_census: Counter = Counter()
    object_census: Counter = Counter()
    role_census: Counter = Counter()
    format_census: Counter = Counter()
    walk_stats: Counter = Counter()
    entry_rows = []
    named = unnamed = txtr_rows = total_rows = 0
    chunk_total = unstructured = trailing_entries = 0
    errors: List[dict] = []
    side = NameSide()

    stream = None
    writer = None
    if csv_path is not None:
        stream = open(csv_path, "w", encoding="utf-8", newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(COLUMNS)
    try:
        for result in _entry_results(iso_path, packs, entries, indices, jobs, progress):
            chunk_total += result["chunks"]
            if result["chunks"] == 0:
                unstructured += 1
            elif result["trailing"]:
                trailing_entries += 1
            errors.extend(result["errors"])
            walk_stats.update(result["stats"])
            entry_rows.append({
                "entry_index": len(entry_rows), "pack": result["pack"],
                "name_id": "0x%08x" % result["name_id"],
                "virtual_offset": result["virtual_offset"],
                "size": result["entry_size"], "chunks": result["chunks"],
                "trailing_bytes": result["trailing"],
            })
            for row in result["rows"]:
                total_rows += 1
                fourcc_census[row["fourcc"] or "<none>"] += 1
                if row["name"]:
                    named += 1
                else:
                    unnamed += 1
                if row["fourcc"] == "TXTR" or "obj=TXTR" in row["extra"]:
                    txtr_rows += 1
                if row["format"]:
                    format_census[row["format"]] += 1
                for piece in row["extra"].split(";"):
                    if piece.startswith("role="):
                        role_census[piece[5:]] += 1
                        if piece[5:] in ("chunk", "unstructured_entry"):
                            chunk_fourcc_census[row["fourcc"] or "<none>"] += 1
                    elif piece.startswith("obj="):
                        object_census[piece[4:]] += 1
                side.add_row(row)
                if writer is not None:
                    writer.writerow([
                        str(row[column]).replace("\t", " ").replace("\n", " ")
                        for column in COLUMNS])
    finally:
        if stream is not None:
            stream.close()

    stat_after = os.stat(iso_path)
    _require(stat_before.st_size == stat_after.st_size
             and stat_before.st_mtime_ns == stat_after.st_mtime_ns,
             "the disc image changed underneath the inventory")

    report = {
        "schema": SCHEMA,
        "tool": "tools/nfl2k5_ps2_disc_inventory.py",
        "image": {
            "name": os.path.basename(iso_path),
            "size_bytes": stat_before.st_size,
            "volume_id": image.volume_id,
            "volume_blocks": image.volume_blocks,
            "sector_size": image.sector_size,
            "slack_bytes": image.slack_bytes,
            "identity": identity,
        },
        "filesystem": {
            "directories": sum(1 for e in filesystem if e["kind"] == "dir"),
            "files": sum(1 for e in filesystem if e["kind"] == "file"),
            "entries": filesystem,
        },
        "packs": [
            {"name": name, "ordinal": ordinal, "iso_byte_offset": base,
             "size": size, "blocks": outer["block_counts"][ordinal],
             "virtual_start": archive.starts[ordinal]}
            for ordinal, (name, base, size) in enumerate(packs)
        ],
        "outer": {
            "entry_count": outer["entry_count"], "reserved": outer["reserved"],
            "populated_pack_count": outer["populated_pack_count"],
            "virtual_size": archive.size,
            "entries_scanned": len(indices),
            "entries": entry_rows,
        },
        "resources": {
            "row_count": total_rows,
            "chunk_count": chunk_total,
            "unstructured_entry_count": unstructured,
            "entries_with_trailing_bytes": trailing_entries,
            "named_rows": named,
            "unnamed_rows": unnamed,
            "distinct_name_keys": len(side.keys),
            "txtr_rows": txtr_rows,
            "fourcc_census": dict(sorted(fourcc_census.items())),
            "chunk_fourcc_census": dict(sorted(chunk_fourcc_census.items())),
            "object_fourcc_census": dict(sorted(object_census.items())),
            "role_census": dict(sorted(role_census.items())),
            "texture_format_census": dict(sorted(format_census.items())),
            "walk_diagnostics": dict(sorted(walk_stats.items())),
        },
        "errors": errors[:500],
        "error_count": len(errors),
        "method": {
            "retail_free": (
                "Only system_bytes (the metadata half) of each resource is read "
                "or decoded; video_bytes (pixels / audio samples) is never read "
                "off the disc. Output carries names, FourCCs, sizes, offsets, "
                "dimensions and digests only."
            ),
            "fourcc_column": (
                "role=chunk rows carry the outer 0x20-byte chunk FourCC; the "
                "decoded object's own FourCC is extra's obj=. Sub-object rows "
                "carry the sub-object FourCC and a role= naming its table."
            ),
            "size_column": (
                "role=chunk rows: stored (on-disc) chunk size in bytes. "
                "role=unstructured_entry rows: the whole outer entry size. "
                "Sub-object rows have no independent on-disc size and are blank."
            ),
            "geometry": (
                "PS2 TXTR descriptor: GS TEX0 at +0x00 (PSM bits 20..25), "
                "MIPTBP1/2 at +0x08/+0x10, explicit u16 width/height at "
                "+0x2C/+0x2E. format is the GS pixel storage mode; extra "
                "carries clut=, mips= and tex0=, plus tex0wh= when TEX0's "
                "power-of-two TW/TH disagree with the explicit dimensions."
            ),
        },
    }
    return report, side


def write_json(path: str, document: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=2, sort_keys=False)
        stream.write("\n")


# ---------------------------------------------------------------------------
# Self-test: a synthetic SLUS-20919-shaped disc, no game data
# ---------------------------------------------------------------------------

PAYLOAD_SENTINEL = b"PIXELS-MUST-NEVER-LEAVE-THE-DISC"


def _utf16(text: str) -> bytes:
    return text.encode("utf-16le") + b"\0\0"


def _pointer(field: int, target: int) -> bytes:
    """Encode VC's field-local minus-one-biased relative pointer."""
    return struct.pack("<i", target - field + 1)


def _tex0(psm: int, width: int, height: int, cpsm: int = 0) -> int:
    return ((psm & 0x3F) << 20) | ((width.bit_length() - 1) << 26) \
        | ((height.bit_length() - 1) << 30) | ((cpsm & 0xF) << 51)


def _txtr_descriptor(psm: int, width: int, height: int, mips: int = 1) -> bytes:
    descriptor = bytearray(TXTR_DESCRIPTOR_SIZE)
    struct.pack_into("<Q", descriptor, 0, _tex0(psm, width, height))
    if mips > 1:
        register1 = 0
        register2 = 0
        for level in range(1, mips):
            pointer = 0x100 * level
            if level <= 3:
                register1 |= pointer << (20 * (level - 1))
            else:
                register2 |= pointer << (20 * (level - 4))
        struct.pack_into("<QQ", descriptor, 8, register1, register2)
    struct.pack_into("<HH", descriptor, 0x2C, width, height)
    return bytes(descriptor)


def _txtr_object(name: str, psm: int, width: int, height: int,
                 mips: int = 1) -> bytes:
    """A VC TXTR object: header, name and descriptor, all inside system_bytes."""
    system = bytearray(0x18)
    system[0x0C:0x10] = b"TXTR"
    name_offset = 0x18
    encoded = _utf16(name)
    descriptor_offset = name_offset + len(encoded)
    if descriptor_offset % 4:
        descriptor_offset += 4 - descriptor_offset % 4
    system[0x10:0x14] = _pointer(0x10, name_offset)
    system[0x14:0x18] = _pointer(0x14, descriptor_offset)
    system.extend(encoded)
    system.extend(bytes(descriptor_offset - len(system)))
    system.extend(_txtr_descriptor(psm, width, height, mips))
    return bytes(system)


def _chunk(fourcc: bytes, system: bytes, video: bytes, compressed: bool) -> bytes:
    if compressed:
        body = compress(system + video)
        magic = COMPRESSED_SENTINEL
    else:
        body = system + video
        magic = 0
    header = bytearray(CHUNK_HEADER_SIZE)
    header[0:4] = fourcc
    struct.pack_into("<4I", header, 4, len(body), len(system), len(video), magic)
    return bytes(header) + body


def _tset_object(names: Sequence[Tuple[str, int, int, int]]) -> bytes:
    """A version-0x0D TSET: records at 0x18, then the names and descriptors."""
    count = len(names)
    system = bytearray(TSET_REF_BASE + count * TSET_REF_STRIDE)
    struct.pack_into("<II", system, 0, TSET_VERSION, count)
    tail = bytearray()
    tail_base = len(system)
    for index, (name, psm, width, height) in enumerate(names):
        record = TSET_REF_BASE + index * TSET_REF_STRIDE
        system[record:record + 4] = b"TXTR"
        name_offset = tail_base + len(tail)
        tail.extend(_utf16(name))
        while (tail_base + len(tail)) % 4:
            tail.append(0)
        descriptor_offset = tail_base + len(tail)
        tail.extend(_txtr_descriptor(psm, width, height))
        system[record + 4:record + 8] = _pointer(record + 4, name_offset)
        system[record + 8:record + 12] = _pointer(record + 8, descriptor_offset)
    return bytes(system) + bytes(tail)


def _scne_object(scene_name: str, textures: Sequence[Tuple[int, int, int]],
                 materials: Sequence[str], nodes: Sequence[Tuple[str, str]],
                 shapes: Sequence[str], markers: Sequence[Tuple[str, str]]) -> bytes:
    """A VC SCNE object whose descriptor tables tile the system buffer."""
    system = bytearray(0x18)
    system[0x0C:0x10] = b"SCNE"
    strings = bytearray()
    string_offsets: Dict[str, int] = {}

    def intern(text: str) -> int:
        # Resolved once the string area's base is known; store the relative slot.
        if text not in string_offsets:
            string_offsets[text] = len(strings)
            strings.extend(_utf16(text))
            while len(strings) % 4:
                strings.append(0)
        return string_offsets[text]

    name_slot = intern(scene_name)
    descriptor_offset = 0x18
    descriptor = bytearray(SCNE_DESCRIPTOR_SIZE)
    tables_offset = descriptor_offset + SCNE_DESCRIPTOR_SIZE
    tables = bytearray()
    pending = []          # (field offset in the whole buffer, string slot)
    for key, count_offset, pointer_offset, stride, name_fields in SCNE_TABLES:
        items = {"texture": textures, "material": materials, "node": nodes,
                 "shape": shapes, "marker": markers}[key]
        if not items:
            continue
        start = tables_offset + len(tables)
        struct.pack_into("<I", descriptor, count_offset, len(items))
        descriptor[pointer_offset:pointer_offset + 4] = _pointer(
            descriptor_offset + pointer_offset, start)
        for item in items:
            record_start = tables_offset + len(tables)
            record = bytearray(stride)
            if key == "texture":
                psm, width, height = item
                record[:TXTR_DESCRIPTOR_SIZE] = _txtr_descriptor(psm, width, height)
            else:
                names = (item,) if isinstance(item, str) else tuple(item)
                for field, text in zip(name_fields, names):
                    pending.append((record_start + field, intern(text)))
            tables.extend(record)
    strings_base = tables_offset + len(tables)
    buffer = bytearray(system) + descriptor + tables + strings
    buffer[0x10:0x14] = _pointer(0x10, strings_base + name_slot)
    buffer[0x14:0x18] = _pointer(0x14, descriptor_offset)
    for field, slot in pending:
        buffer[field:field + 4] = _pointer(field, strings_base + slot)
    return bytes(buffer)


def _build_synthetic_disc() -> Tuple[bytes, dict]:
    """A two-pack /VC_20919 archive inside a bootable-looking ISO9660 volume."""
    entries_payload = []
    expected = {"names": [], "textures": {}, "sentinel_chunks": 0}

    # E0: plain TXTR with a payload sentinel after its metadata.
    system = _txtr_object("selftest_logo", 0x13, 512, 256)
    entries_payload.append(_chunk(b"TXTR", system, PAYLOAD_SENTINEL * 8, False))
    expected["textures"]["SELFTEST_LOGO"] = ("PSMT8", 512, 256)

    # E1: LZ-compressed TXTR; the LZ prefix decode must stop before the pixels.
    system = _txtr_object("selftest_lz", 0x14, 64, 32, mips=3)
    entries_payload.append(_chunk(b"HITX", system, PAYLOAD_SENTINEL * 64, True))
    expected["textures"]["SELFTEST_LZ"] = ("PSMT4", 64, 32)

    # E2: a TSET of three textures, then a second chunk in the same entry.
    tset = _tset_object([("tset_helmet", 0x13, 256, 256),
                         ("tset_jersey", 0x13, 128, 64),
                         ("tset_pants", 0x14, 32, 32)])
    second = _txtr_object("after_tset", 0x00, 16, 16)
    entries_payload.append(_chunk(b"TSET", tset, b"", False)
                           + _chunk(b"TXTR", second, PAYLOAD_SENTINEL, False))
    for name, fmt, width, height in (("TSET_HELMET", "PSMT8", 256, 256),
                                     ("TSET_JERSEY", "PSMT8", 128, 64),
                                     ("TSET_PANTS", "PSMT4", 32, 32),
                                     ("AFTER_TSET", "PSMCT32", 16, 16)):
        expected["textures"][name] = (fmt, width, height)

    # E3: a scene with every table populated, LZ-compressed, large enough to
    # straddle the pack boundary placed below.
    scene = _scne_object(
        "stadium_selftest",
        textures=[(0x13, 1024, 1024), (0x02, 8, 8)],
        materials=["mat_grass", "mat_seats"],
        nodes=[("node_root", "node_root"), ("node_upper", "node_upper_alt")],
        shapes=["shape_field"],
        markers=[("marker_50", "marker_50_alt")],
    )
    entries_payload.append(_chunk(b"SCNE", scene, PAYLOAD_SENTINEL * 256, True))

    # E4: zero padding before a valid chunk (the padding-skip path).
    system = _txtr_object("padded_texture", 0x13, 64, 64)
    entries_payload.append(bytes(0x40) + _chunk(b"TXTR", system, b"", False))
    expected["textures"]["PADDED_TEXTURE"] = ("PSMT8", 64, 64)

    # E5: an entry that is not a chunk stream at all.
    entries_payload.append(b"RAWD" + bytes(12) + b"opaque entry body" * 4)

    # Lay the entries out 0x800-aligned after the outer table, then split the
    # virtual archive into two packs so E3 crosses the boundary.
    table_size = OUTER_HEADER_SIZE + len(entries_payload) * OUTER_ENTRY_SIZE
    cursor = (table_size + ALIGNMENT - 1) // ALIGNMENT
    records = []
    for ordinal, payload in enumerate(entries_payload):
        records.append((0x1000_0000 + ordinal, len(payload), cursor))
        cursor += (len(payload) + ALIGNMENT - 1) // ALIGNMENT
    virtual = bytearray(cursor * ALIGNMENT)
    for (_name_id, size, offset_blocks), payload in zip(records, entries_payload):
        virtual[offset_blocks * ALIGNMENT:offset_blocks * ALIGNMENT + size] = payload
    e3_start = records[3][2] * ALIGNMENT
    split_blocks = (e3_start // ALIGNMENT) + 1          # one block into E3
    pack0 = bytes(virtual[:split_blocks * ALIGNMENT])
    pack1 = bytes(virtual[split_blocks * ALIGNMENT:])
    header = bytearray(OUTER_HEADER_SIZE)
    struct.pack_into("<III", header, 0, len(records), 0, 2)
    struct.pack_into("<II", header, 12, len(pack0) // ALIGNMENT, len(pack1) // ALIGNMENT)
    table = b"".join(struct.pack("<III", *record) for record in records)
    pack0 = bytes(header) + table + pack0[len(header) + len(table):]
    _require(len(pack0) % ALIGNMENT == 0 and len(pack1) % ALIGNMENT == 0,
             "self-test packs must stay block aligned")

    boot_elf = b"\x7fELF" + bytes(2044)
    image = iso.build_synthetic_iso(
        files=[
            (b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_209.19;1\r\nVER = 1.01\r\n"
                              b"VMODE = NTSC\r\n"),
            (b"SLUS_209.19;1", boot_elf),
        ],
        sub_name=b"VC_20919",
        sub_files=[(b"0.;1", pack0), (b"1.;1", pack1)],
    )
    expected["entries"] = len(records)
    expected["pack_sizes"] = (len(pack0), len(pack1))
    expected["boot_sha256"] = hashlib.sha256(boot_elf).hexdigest()
    expected["scene_names"] = {
        "STADIUM_SELFTEST": "chunk",
        "MAT_GRASS": "scne_material", "MAT_SEATS": "scne_material",
        "NODE_ROOT": "scne_node", "NODE_UPPER": "scne_node",
        "NODE_UPPER_ALT": "scne_node_alt",
        "SHAPE_FIELD": "scne_shape",
        "MARKER_50": "scne_marker", "MARKER_50_ALT": "scne_marker_alt",
    }
    return image, expected


def selftest(tmp: Optional[str] = None) -> int:
    """Prove the walk on a synthetic disc.  Needs no game data."""
    failures: List[str] = []

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    # The LZ codec round-trips, and the prefix decode is a true prefix.
    sample = (b"abcabcabcabcXYZ" * 40 + bytes(range(256)) + b"tail" * 20)
    stream = compress(sample)
    check(decompress_prefix(stream, len(sample)) == sample, "LZ round-trip")
    check(decompress_prefix(stream, 100) == sample[:100], "LZ prefix decode")
    check(decompress_prefix(stream, 1 << 20) == sample, "LZ want past end clamps")

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        image_bytes, expected = _build_synthetic_disc()
        iso_path = os.path.join(work, "selftest_slus_20919.iso")
        with open(iso_path, "wb") as handle:
            handle.write(image_bytes)
        csv_path = os.path.join(work, "inventory.csv")
        json_path = os.path.join(work, "report.json")
        join_path = os.path.join(work, "join.csv")

        report, side = inventory(iso_path, csv_path=csv_path, jobs=1, hash_image=True)
        identity = report["image"]["identity"]
        check(identity["serial"] == SERIAL, "serial %r" % identity["serial"])
        check(identity["serial_matches"], "serial_matches")
        check(identity["boot_sha256"] == expected["boot_sha256"], "boot digest")
        check(identity["retail_boot_elf"] is False, "a synthetic ELF is not retail")
        check(identity["retail_image"] is False, "a synthetic image is not retail")
        check(len(identity["image_sha256"]) == 64, "image digest present")
        check([p["size"] for p in report["packs"]] == list(expected["pack_sizes"]),
              "pack sizes %r" % [p["size"] for p in report["packs"]])
        check(report["outer"]["entry_count"] == expected["entries"], "entry count")
        check(report["resources"]["unstructured_entry_count"] == 1, "unstructured entry")
        check(report["error_count"] == 0, "errors: %r" % report["errors"][:3])
        diagnostics = report["resources"]["walk_diagnostics"]
        check(diagnostics.get("tset_texture") == 3, "tset textures %r" % diagnostics)
        check(diagnostics.get("scne_texture") == 2, "scene textures %r" % diagnostics)
        check(diagnostics.get("scne_material") == 2, "scene materials %r" % diagnostics)
        check(diagnostics.get("scne_node") == 2 and diagnostics.get("scne_node_alt") == 1,
              "scene nodes %r" % diagnostics)
        check(diagnostics.get("scne_shape") == 1, "scene shapes %r" % diagnostics)
        check(diagnostics.get("scne_marker") == 1 and diagnostics.get("scne_marker_alt") == 1,
              "scene markers %r" % diagnostics)

        with open(csv_path, "r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        check(len(rows) == report["resources"]["row_count"], "CSV row count")
        by_key: Dict[str, List[dict]] = {}
        for row in rows:
            by_key.setdefault(row["name_key"], []).append(row)
        for key, (fmt, width, height) in expected["textures"].items():
            hits = [row for row in by_key.get(key, []) if row["format"]]
            check(len(hits) == 1, "texture %s rows=%d" % (key, len(hits)))
            if hits:
                row = hits[0]
                check((row["format"], row["width"], row["height"]) == (fmt, str(width), str(height)),
                      "texture %s geometry %r" % (key, (row["format"], row["width"], row["height"])))
        lz_rows = by_key.get("SELFTEST_LZ", [])
        check(lz_rows and "lz=1" in lz_rows[0]["extra"] and "mips=3" in lz_rows[0]["extra"],
              "LZ texture extra %r" % (lz_rows[0]["extra"] if lz_rows else None))
        padded = by_key.get("PADDED_TEXTURE", [])
        check(padded and "pad=64" in padded[0]["extra"], "padding skip recorded")
        for key, role in expected["scene_names"].items():
            roles = [piece[5:] for row in by_key.get(key, [])
                     for piece in row["extra"].split(";") if piece.startswith("role=")]
            check(role in roles, "scene name %s role %s in %r" % (key, role, roles))
        embedded = [row for row in rows if row["name_key"].startswith("STADIUM_SELFTEST/EMBEDDED_")]
        check(len(embedded) == 2 and {row["format"] for row in embedded} == {"PSMT8", "PSMCT16"},
              "embedded scene textures %r" % [(r["name"], r["format"]) for r in embedded])
        straddling = [row for row in rows if row["name_key"] == "STADIUM_SELFTEST"]
        check(straddling and straddling[0]["pack"] == "0" and "lz=1" in straddling[0]["extra"],
              "scene chunk read across the pack boundary")
        raw = [row for row in rows if "role=unstructured_entry" in row["extra"]]
        check(len(raw) == 1 and raw[0]["fourcc"] == "RAWD", "unstructured row %r" % raw)

        # Retail-free: the payload sentinel is in the image and in no output.
        check(PAYLOAD_SENTINEL in image_bytes, "sentinel planted")
        write_json(json_path, report)
        xbox_side = NameSide()
        for key, (fmt, width, height) in list(expected["textures"].items())[:4]:
            xbox_side.add(key, "TXTR", "P8", width, height)
        xbox_side.add("XBOX_ONLY_TEXTURE", "TXTR", "DXT1", 64, 64)
        join_rows, join_summary = name_join(side, xbox_side)
        write_join_csv(join_path, join_rows)
        check(join_summary["shared"] == 4 and join_summary["xbox_only"] == 1,
              "join summary %r" % join_summary)
        check(join_summary["ps2_only"] == len(side.keys) - 4, "ps2-only count")
        presence = {row[0]: row[1] for row in join_rows}
        check(presence.get("XBOX_ONLY_TEXTURE") == "xbox_only"
              and presence.get("SELFTEST_LOGO") == "both"
              and presence.get("PADDED_TEXTURE") == "ps2_only", "presence column")
        for path in (csv_path, json_path, join_path):
            with open(path, "rb") as handle:
                check(PAYLOAD_SENTINEL not in handle.read(),
                      "payload bytes leaked into %s" % os.path.basename(path))
        with open(json_path, "r", encoding="utf-8") as handle:
            reloaded = json.load(handle)
        check(reloaded["schema"] == SCHEMA and reloaded["image"]["name"]
              == os.path.basename(iso_path), "JSON reloads")
        check(os.path.sep not in reloaded["image"]["name"], "JSON carries no local paths")

        # A non-PS2 volume is refused with a sentence, not a traceback.
        other = os.path.join(work, "not_2k5.iso")
        with open(other, "wb") as handle:
            handle.write(iso.build_synthetic_iso())
        try:
            inventory(other, jobs=1)
        except InventoryError as exc:
            check(PACK_DIRECTORY in str(exc), "refusal names the pack directory")
        else:
            check(False, "a disc without /VC_20919 must be refused")

    if failures:
        for failure in failures:
            print("SELFTEST FAIL: %s" % failure, file=sys.stderr)
        return 1
    print("NFL2K5_PS2_DISC_INVENTORY_SELFTEST_PASS entries=%d textures=%d "
          "scene_rows=%d lz=prefix-only packs=2 straddle=proved sentinel=contained"
          % (expected["entries"], len(expected["textures"]),
             len(expected["scene_names"])))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only resource-name inventory of an ESPN NFL 2K5 (PS2) disc.")
    parser.add_argument("--iso", help="the user's own SLUS-20919 ISO (opened read-only)")
    parser.add_argument("--json", help="write the report here")
    parser.add_argument("--csv", help="write the full inventory (one row per resource) here")
    parser.add_argument("--xbox-inventory",
                        help="an Xbox resource-name inventory (.csv/.tsv, optionally .gz) "
                             "to join against by name")
    parser.add_argument("--join-csv", help="write the PS2 <-> Xbox name join here")
    parser.add_argument("--hash-image", action="store_true",
                        help="also SHA-256 the whole image and compare it with the retail pin")
    parser.add_argument("--require-retail", action="store_true",
                        help="refuse (exit 2) unless the boot ELF matches the retail pin")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after N outer entries (smoke test)")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the walk on a synthetic disc; needs no game data")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.iso:
        parser.error("--iso is required (or --selftest)")
    if args.join_csv and not args.xbox_inventory:
        parser.error("--join-csv needs --xbox-inventory")
    for path in (args.json, args.csv, args.join_csv):
        if path and os.path.exists(path):
            parser.error("refusing to overwrite an existing output: %s" % path)
    for path in (args.json, args.csv, args.join_csv):
        if path and os.path.abspath(path) == os.path.abspath(args.iso):
            parser.error("an output path is the disc image itself")

    def progress(message: str) -> None:
        if not args.quiet:
            print(message, file=sys.stderr)

    try:
        report, side = inventory(args.iso, csv_path=args.csv, jobs=args.jobs,
                                 limit=args.limit, hash_image=args.hash_image,
                                 progress=progress)
        if args.xbox_inventory:
            xbox_side, provenance = load_name_side(args.xbox_inventory)
            join_rows, join_summary = name_join(side, xbox_side)
            join_summary["xbox_inventory"] = provenance
            if args.join_csv:
                join_summary["rows_written"] = write_join_csv(args.join_csv, join_rows)
            report["name_join"] = join_summary
        if args.json:
            write_json(args.json, report)
    except (InventoryError, iso.Iso9660Error, OSError) as exc:
        print("NFL2K5_PS2_DISC_INVENTORY_REFUSED %s" % exc, file=sys.stderr)
        return 2

    identity = report["image"]["identity"]
    resources = report["resources"]
    print("NFL2K5_PS2_DISC_INVENTORY serial=%s retail_boot_elf=%s retail_image=%s "
          "entries=%d rows=%d named=%d textures=%d name_keys=%d errors=%d"
          % (identity["serial"], identity["retail_boot_elf"], identity["retail_image"],
             report["outer"]["entries_scanned"], resources["row_count"],
             resources["named_rows"], resources["txtr_rows"],
             resources["distinct_name_keys"], report["error_count"]))
    if "name_join" in report:
        join = report["name_join"]
        print("NFL2K5_PS2_XBOX_NAME_JOIN shared=%d ps2_only=%d xbox_only=%d "
              "xbox_matched=%s%%" % (join["shared"], join["ps2_only"],
                                     join["xbox_only"], join["xbox_keys_matched_percent"]))
    if args.require_retail and not identity["retail_boot_elf"]:
        print("NFL2K5_PS2_DISC_INVENTORY_REFUSED boot ELF %s is not the retail "
              "SLUS_209.19 (%s)" % (identity["boot_sha256"], RETAIL_BOOT_ELF_SHA256),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
