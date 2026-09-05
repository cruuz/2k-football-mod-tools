#!/usr/bin/env python3
"""Recode the defensive personnel categories of NFL 2K5's 37 stock playbooks for one-pool positions.

Context (``MODERN_POSITIONS_2026-09-03.md`` sections 2.2 / 3.2b / A.2).  Every playbook carries up
to 26 personnel *categories* of 16 bytes at body ``0x993C`` (name pointer, formation type at ``+4``,
eleven slot codes at ``+5..+15``).  A code is ``kind | variant << 5``: the kind is the 19-way
on-field position (12 DE, 13 DT, 14 ILB, 15 OLB ...) and the variant selects which of the kind's
two roster lists (bit 0: 0 = rank order, 1 = side order) and the starting row (bits 1-2).  The fill
skips players already on the field, so ``LB0 LB1 LB2`` field the #1, #2 and #3 of one pool.

The executable half (``mod_editor/core/nfl2k5_position_pools.py``) merges the OLB enum into the
LB lists and the ROST half (``tools/nfl2k5_roster_reclassify.py``) moves 3-4 outside backers to
EDGE (enum 16) and 3-4 ends to the interior (enum 15).  This tool rewrites the category codes so a
category asks the new pools for the players it fielded in retail, by rule, per category:

* front shape ``(#DE, #DT)`` in the category decides the rule;
* **odd front** ``(2, 1)`` (3-4, 3-4 Nickel/Dime, 3-3, 3-2, Prevent, Dime Odd): the DT and DE codes
  become interior codes ``DT0 DT1 DT2`` (retail DTs first in variant order, then DE0, DE1), OLB codes
  become EDGE codes with the same variant (kind 12), ILB codes are unchanged (kind 14 = the LB pool);
* **5-2** ``(3, 2)``: DE0/DE1 stay (EDGE), DE2 becomes the next free interior variant, OLB codes
  become LB codes (below), ILB unchanged;
* **even front and everything else** (4-3, Nickel, Dime, Bear, Goalline, special teams): DE and DT
  codes are unchanged (EDGE is the DE kind), ILB codes unchanged, OLB codes become LB codes with
  variant ``v + 1`` bumped past any variant an ILB code already uses (4-3 ``OLB1 ILB0 OLB0`` ->
  ``LB2 LB0 LB1``: MIKE = #1, WILL = #2 via the side chain, SAM = #3 via rank row 1 + skip;
  Kickoff ``OLB2 OLB3`` -> ``LB3 LB4``);
* ``--prevent-two-edges``: in Prevent (type 0x10) keep DE1 as the second EDGE instead of the third
  interior lineman (the spec's alternative for teams that want both rushers on the field).

Offensive categories never carry those kinds and are untouched; formation records (coordinates,
stances) are untouched: only who fills each slot changes.  Every book is verified against its retail
category table digest before anything is written, the rewrite is a fixed-span edit inside the disc
COPY, and the receipt lists every category before/after.  ``inspect`` lists every defensive slot's
category before/after per book without writing.

Usage::

    nfl2k5_playbook_position_recode.py inspect  IMAGE_OR_PACK_DIR [--book ARZ] [--prevent-two-edges]
    nfl2k5_playbook_position_recode.py status   IMAGE_OR_PACK_DIR
    nfl2k5_playbook_position_recode.py apply    IMAGE.xiso.iso [--prevent-two-edges] [--receipt PATH]
    nfl2k5_playbook_position_recode.py digests  IMAGE_OR_PACK_DIR      (print the category-table digests)

``apply`` only ever writes into the image it is given: copy the disc first.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Callable, Iterable, Mapping, Sequence

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from nfl_outer import ALIGNMENT, HEADER_SIZE, PACK_NAMES, PACK_SLOT_COUNT, align_up  # noqa: E402


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

PACK_FOLDER = "vc_53450030"
RESOURCE_HEADER_SIZE = 0x20
BODY_SIZE = 0x13390
BOOK_ENTRY_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE
CATEGORY_BASE = 0x993C
CATEGORY_SIZE = 0x10
CATEGORY_CAPACITY = 26
CATEGORY_TABLE_SIZE = CATEGORY_SIZE * CATEGORY_CAPACITY
SLOT_COUNT = 11
FORMATION_TYPE_PREVENT = 0x10

BOOK_NAMES = ("ARZ", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "Editor", "GB", "GEN",
              "HOU", "IND", "JAX", "KC", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "OAK", "PHI", "PIT", "PRACTICE",
              "reference", "SD", "SEA", "SF", "STL", "TB", "TEN", "WAS", "WCO")
FIRST_BOOK_ENTRY = 307
BOOK_ENTRIES: Mapping[str, int] = {name: FIRST_BOOK_ENTRY + i for i, name in enumerate(BOOK_NAMES)}

# on-field kinds (HUD table 0x4F68F8 order)
KIND_NAMES = ("QB", "P", "K", "H", "KR", "T", "C", "G", "TE", "WR", "HB", "FB", "DE", "DT", "ILB", "OLB", "FS", "SS", "CB")
KIND_DE, KIND_DT, KIND_ILB, KIND_OLB = 12, 13, 14, 15
FRONT_KINDS = frozenset((KIND_DE, KIND_DT, KIND_ILB, KIND_OLB))
MAX_VARIANT = 7
# how the recoded kinds read under one pool (the EDGE rename labels kind 12, the pool patch kind 14)
POOL_LABELS = {KIND_DE: "EDGE", KIND_DT: "DT", KIND_ILB: "LB", KIND_OLB: "OLB"}


class RecodeError(ValueError):
    """The playbook recode cannot be applied to this image."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecodeError(message)


def code_label(code: int, pooled: bool = False) -> str:
    kind, variant = code & 0x1F, code >> 5
    name = (POOL_LABELS.get(kind) if pooled else None) or (KIND_NAMES[kind] if kind < len(KIND_NAMES) else f"k{kind}")
    return f"{name}{variant}"


def make_code(kind: int, variant: int) -> int:
    _require(0 <= variant <= MAX_VARIANT, f"variant {variant} does not fit three bits")
    return kind | (variant << 5)


# ---------------------------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------------------------

def front_shape(codes: Sequence[int]) -> tuple[int, int]:
    kinds = [c & 0x1F for c in codes]
    return kinds.count(KIND_DE), kinds.count(KIND_DT)


def rule_for(codes: Sequence[int]) -> str:
    kinds = {c & 0x1F for c in codes}
    if not kinds & FRONT_KINDS:
        return "untouched"
    n_de, n_dt = front_shape(codes)
    if (n_de, n_dt) == (2, 1):
        return "odd"
    if (n_de, n_dt) == (3, 2):
        return "five_two"
    return "even"


def recode_codes(codes: Sequence[int], formation_type: int, *, prevent_two_edges: bool = False) -> tuple[list[int], str]:
    """Return (new codes, rule name).  Pure; the rule is described in the module docstring."""

    codes = list(codes)
    _require(len(codes) == SLOT_COUNT, "a category has eleven slot codes")
    rule = rule_for(codes)
    if rule == "untouched":
        return codes, rule
    out = list(codes)
    kinds = [c & 0x1F for c in codes]
    variants = [c >> 5 for c in codes]

    def assign_lb_codes() -> None:
        used = {variants[i] for i, k in enumerate(kinds) if k == KIND_ILB}
        for i in sorted((i for i, k in enumerate(kinds) if k == KIND_OLB), key=lambda i: (variants[i], i)):
            target = variants[i] + 1
            while target in used:
                target += 1
            used.add(target)
            out[i] = make_code(KIND_ILB, target)

    def assign_interior(indices: Iterable[int], used: set[int]) -> None:
        for i in indices:
            target = 0
            while target in used:
                target += 1
            used.add(target)
            out[i] = make_code(KIND_DT, target)

    if rule == "odd":
        dts = sorted((i for i, k in enumerate(kinds) if k == KIND_DT), key=lambda i: (variants[i], i))
        des = sorted((i for i, k in enumerate(kinds) if k == KIND_DE), key=lambda i: (variants[i], i))
        keep_edge: list[int] = []
        if prevent_two_edges and (formation_type & 0x3F) == FORMATION_TYPE_PREVENT and len(des) == 2:
            keep_edge = [des[1]]                       # DE1 stays the second EDGE
            des = des[:1]
        used: set[int] = set()
        assign_interior(dts + des, used)
        for i in keep_edge:
            out[i] = make_code(KIND_DE, 1)
        for i, k in enumerate(kinds):
            if k == KIND_OLB:
                out[i] = make_code(KIND_DE, variants[i])
        return out, rule
    if rule == "five_two":
        des = sorted((i for i, k in enumerate(kinds) if k == KIND_DE), key=lambda i: (variants[i], i))
        used = {variants[i] for i, k in enumerate(kinds) if k == KIND_DT}
        for i in des[:2]:
            out[i] = make_code(KIND_DE, variants[i])
        assign_interior(des[2:], used)
        assign_lb_codes()
        return out, rule
    assign_lb_codes()
    return out, rule


# ---------------------------------------------------------------------------------------------
# Disc access: the outer archive inside an XDVDFS image (or a loose pack directory)
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PackSpan:
    name: str
    virtual_start: int
    size: int
    image_offset: int          # absolute byte offset of the pack in the image (or 0 for loose files)
    path: Path | None = None   # loose pack file when not inside an image


@dataclass(frozen=True)
class OuterEntry:
    index: int
    name_id: int
    virtual_offset: int
    size: int


class OuterImage:
    """Read/write access to the ``vc_53450030`` outer archive, either inside a disc image (the
    packs are located through the XDVDFS directory) or as loose pack files in a folder."""

    def __init__(self, path: Path | str, *, writable: bool = False) -> None:
        self.path = Path(path)
        self.writable = writable
        self._fd: int | None = None
        self.packs: list[PackSpan] = []
        try:
            if self.path.is_dir():
                _require(not writable, "loose pack folders are read-only here")
                folder = self.path / PACK_FOLDER if (self.path / PACK_FOLDER).is_dir() else self.path
                self._open_loose(folder)
            else:
                self._open_image()
            self.entries: list[OuterEntry] = self._read_table()
        except BaseException:
            # A failed constructor never reaches __enter__/__exit__. Recipe
            # probes may catch the error and later replace this same image.
            # Construction only reads, so close directly without a writable fsync.
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise

    # -- construction
    def _open_loose(self, folder: Path) -> None:
        index = folder / "0"
        _require(index.is_file(), f"{folder} has no pack '0'")
        header = index.read_bytes()[:HEADER_SIZE]
        _, _, populated = struct.unpack_from("<III", header, 0)
        blocks = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", header, 12)
        virtual = 0
        for ordinal in range(populated):
            name = PACK_NAMES[ordinal]
            size = blocks[ordinal] * ALIGNMENT
            path = folder / name
            _require(path.is_file() and path.stat().st_size == size, f"pack {name} missing or the wrong size")
            self.packs.append(PackSpan(name, virtual, size, 0, path))
            virtual += size

    def _open_image(self) -> None:
        try:
            import nfl_uniform_color_xiso_direct_patch as xc
        except ImportError as exc:  # pragma: no cover
            raise RecodeError("the XDVDFS reader (tools/nfl_uniform_color_xiso_direct_patch.py) is unavailable") from exc
        flags = os.O_RDWR if self.writable else os.O_RDONLY
        self._fd = os.open(self.path, flags | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0))
        size = os.fstat(self._fd).st_size
        entries, _directory = xc.parse_xdvdfs(self._fd, size)
        first = entries.get(f"{PACK_FOLDER}/0")
        _require(first is not None, f"disc image has no {PACK_FOLDER}/0")
        header = _pread(self._fd, HEADER_SIZE, int(first.byte_offset))
        _, _, populated = struct.unpack_from("<III", header, 0)
        blocks = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", header, 12)
        virtual = 0
        for ordinal in range(populated):
            name = PACK_NAMES[ordinal]
            entry = entries.get(f"{PACK_FOLDER}/{name.lower()}") or entries.get(f"{PACK_FOLDER}/{name}")
            _require(entry is not None, f"disc image has no {PACK_FOLDER}/{name}")
            pack_size = blocks[ordinal] * ALIGNMENT
            _require(int(entry.size) == pack_size, f"pack {name}: directory size 0x{int(entry.size):x} != table 0x{pack_size:x}")
            self.packs.append(PackSpan(name, virtual, pack_size, int(entry.byte_offset)))
            virtual += pack_size

    def _read_table(self) -> list[OuterEntry]:
        header = self.read(0, HEADER_SIZE)
        count, reserved, _populated = struct.unpack_from("<III", header, 0)
        _require(reserved == 0 and 1 <= count <= 1_000_000, "implausible outer archive header")
        table = self.read(HEADER_SIZE, 12 * count)
        entries: list[OuterEntry] = []
        previous_end = 0
        for index in range(count):
            name_id, size, offset_blocks = struct.unpack_from("<III", table, 12 * index)
            offset = offset_blocks * ALIGNMENT
            _require(index == 0 or offset == align_up(previous_end), f"outer entry {index} is out of order")
            entries.append(OuterEntry(index, name_id, offset, size))
            previous_end = offset + size
        return entries

    # -- raw access by virtual offset
    def _segments(self, virtual_offset: int, size: int) -> list[tuple[PackSpan, int, int]]:
        out: list[tuple[PackSpan, int, int]] = []
        end = virtual_offset + size
        for pack in self.packs:
            a, b = max(virtual_offset, pack.virtual_start), min(end, pack.virtual_start + pack.size)
            if a < b:
                out.append((pack, a - pack.virtual_start, b - a))
        _require(sum(s for _p, _o, s in out) == size, f"virtual range 0x{virtual_offset:x}+0x{size:x} is outside the packs")
        return out

    def read(self, virtual_offset: int, size: int) -> bytes:
        chunks: list[bytes] = []
        for pack, pack_offset, length in self._segments(virtual_offset, size):
            if self._fd is not None:
                data = _pread(self._fd, length, pack.image_offset + pack_offset)
            else:
                with open(pack.path, "rb") as handle:  # type: ignore[arg-type]
                    handle.seek(pack_offset)
                    data = handle.read(length)
            _require(len(data) == length, "short read inside the outer archive")
            chunks.append(data)
        return b"".join(chunks)

    def write(self, virtual_offset: int, data: bytes) -> int:
        _require(self.writable and self._fd is not None, "archive was opened read-only")
        written = 0
        for pack, pack_offset, length in self._segments(virtual_offset, len(data)):
            part = data[written: written + length]
            count = _pwrite(self._fd, part, pack.image_offset + pack_offset)
            _require(count == length, "short write inside the outer archive")
            written += count
        return written

    def image_offset(self, virtual_offset: int) -> int:
        """Absolute image offset of a virtual offset (for receipts; must not cross a pack seam)."""

        (pack, pack_offset, _length), = self._segments(virtual_offset, 1)
        return pack.image_offset + pack_offset

    def read_entry(self, index: int) -> bytes:
        entry = self.entries[index]
        return self.read(entry.virtual_offset, entry.size)

    def entries_with_head(self, head: bytes) -> list[OuterEntry]:
        return [e for e in self.entries if e.size >= len(head) and self.read(e.virtual_offset, len(head)) == head]

    def close(self) -> None:
        if self._fd is not None:
            if self.writable:
                os.fsync(self._fd)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "OuterImage":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


# ---------------------------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------------------------

@dataclass
class Category:
    index: int
    name: str
    formation_type: int
    codes: list[int]

    @property
    def raw_type(self) -> int:
        return self.formation_type


@dataclass
class Book:
    name: str
    entry_index: int
    virtual_offset: int
    body: bytes
    book_name: str
    categories: list[Category] = field(default_factory=list)

    @property
    def table_offset(self) -> int:
        """Virtual offset of the category table inside the archive."""

        return self.virtual_offset + RESOURCE_HEADER_SIZE + CATEGORY_BASE

    def table_bytes(self) -> bytes:
        return self.body[CATEGORY_BASE: CATEGORY_BASE + CATEGORY_TABLE_SIZE]

    def defensive_records(self, table: bytes | None = None) -> bytes:
        """The formation-type byte and eleven slot codes (``+4..+15``) of every category the rule
        touches (those carrying a front kind), in table order.  Offensive categories and the name
        pointers (both of which a Create-a-Play author may have rewritten or shifted) are not part
        of the retail check because the recode never writes them."""

        table = self.table_bytes() if table is None else table
        out = []
        for cat in self.categories:
            if rule_for(cat.codes) != "untouched":
                off = cat.index * CATEGORY_SIZE
                out.append(bytes([cat.index]) + table[off + 4: off + CATEGORY_SIZE])
        return b"".join(out)

    def table_sha256(self, table: bytes | None = None) -> str:
        return hashlib.sha256(self.defensive_records(table)).hexdigest()


def _utf16z(body: bytes, offset: int) -> str:
    end = offset
    while end + 2 <= len(body) and body[end: end + 2] != b"\0\0":
        end += 2
    return body[offset: end].decode("utf-16le", "replace")


def _relative(body: bytes, field_offset: int) -> int | None:
    value = struct.unpack_from("<i", body, field_offset)[0]
    return None if value == 0 else field_offset + value - 1


def parse_book(name: str, entry: OuterEntry, raw: bytes) -> Book:
    _require(len(raw) == BOOK_ENTRY_SIZE, f"{name}: outer entry {entry.index} is 0x{len(raw):x} bytes, not a playbook")
    magic, stored, sys_bytes, video_bytes, comp, _scratch, r0, r1 = struct.unpack_from("<4s7I", raw, 0)
    _require(magic == b"PLAY" and stored == BODY_SIZE and sys_bytes == BODY_SIZE and video_bytes == 0 and comp == 0
             and r0 == 0 and r1 == 0, f"{name}: outer entry {entry.index} is not an uncompressed PLAY resource")
    body = raw[RESOURCE_HEADER_SIZE:]
    _require(body[0x0C:0x10] == b"PLAY" and body[0x20:0x28] == b"p\0l\0b\0\0\0", f"{name}: playbook body magic")
    count = struct.unpack_from("<I", body, 0x3C)[0]
    _require(count <= CATEGORY_CAPACITY, f"{name}: {count} categories")
    _require(_relative(body, 0x64) == CATEGORY_BASE, f"{name}: category table pointer")
    name_off = _relative(body, 0x30)
    book_name = _utf16z(body, name_off) if name_off is not None else ""
    categories = []
    for index in range(count):
        off = CATEGORY_BASE + index * CATEGORY_SIZE
        cname_off = _relative(body, off)
        cname = _utf16z(body, cname_off) if cname_off is not None else ""
        categories.append(Category(index, cname, body[off + 4], list(body[off + 5: off + 16])))
    return Book(name, entry.index, entry.virtual_offset, body, book_name, categories)


def load_books(archive: OuterImage, names: Sequence[str] | None = None) -> list[Book]:
    names = list(BOOK_NAMES if names is None else names)
    books = []
    for name in names:
        index = BOOK_ENTRIES[name]
        _require(index < len(archive.entries), f"{name}: the archive has no outer entry {index}")
        books.append(parse_book(name, archive.entries[index], archive.read_entry(index)))
    return books


# ---------------------------------------------------------------------------------------------
# Retail / applied recognition
# ---------------------------------------------------------------------------------------------

# sha256 of each book's defensive category records (see Book.defensive_records) on the retail disc
RETAIL_TABLE_SHA256: Mapping[str, str] = {
    "ARZ": "089655c6e8e7ff9e065db5d6caf3daaa161d3fbd2a8ad6bddda15765ad637fa1",
    "ATL": "b677d20cc287518f2c5d9ec93c85855b102f2a0c3eb500a6004d35c27692b32b",
    "BAL": "ca84d9a7435fbae3af71ce674831fa9306d4fa87fc245903d4c89841bf7ba4de",
    "BUF": "0babcb0dcf17ee609fef1d884c4d500e73878a11aee223c38eb46a6452395cc0",
    "CAR": "37a11316479bbed6a64955510277106e5434c87ec0f379055a1cfb3c9eba3900",
    "CHI": "788612b98cca23abd88137605e7050a2630ca3e1d599080851000e8328521702",
    "CIN": "f3d4b01cf365cbb8ca8af27af5ca0595e5c6ed2bb2a8d1f553217aa77a4b6f1d",
    "CLE": "8cf76ee215489e1e6ac00667740993c5fb94083e881b7f2c2a393a2e02c6b156",
    "DAL": "13a30e3b346cece302c29a8ecb7685083f939da839b9ac720a22aa762af9165b",
    "DEN": "06196e5ca489a83bbbd1b3245149a2f382ba6bcd80c05761e02bf1a7eea6f463",
    "DET": "a7ca1415195e30a5eaded6962a3c80f832279a9751178784451fb798b265ff8d",
    "Editor": "bf197de62574e8c9dcb0bc14bbbe184946dcdd158fca2a7aeeb227a57ba65b69",
    "GB": "80dcc69d7106cd347e65b34d3433303036ffd703c233167b48395a478e2438da",
    "GEN": "4eb1f145a547e474255ef604c234a6a738b72883abe7f897dac980763db9c03d",
    "HOU": "4c59372dd440fdd6ad4b96f8821c22ba04a8eae6ded573b9b5b1af03e9a22ad9",
    "IND": "1dd03aea126a70fcdaffb43a2c10ce42f856a719071e1b3e8b70ce77893530c5",
    "JAX": "0bf0c7c098d0b3dcb0b60956beb2ff099f6226b65ea4b0c328ffef6004875e7f",
    "KC": "3745be5761257d33532844a2267ce4b486091692d4348d2ce2aaeed6ade80e25",
    "MIA": "e8a89622dd578fb4082c4bd5e1406d09aa26eb2b72c8f5729b6bf5a2fe2392f9",
    "MIN": "154defbef9ee33cd45d3437eac7c74dc32caa3ed74d4732d3c607decc1a94a69",
    "NE": "fc44933dac09943b0c589ce6f50db3907cd296e4d366fa81d8389ca856d2a659",
    "NO": "6104b7ee451028880b5a5859b4db7f212553ce0edfce5203db747747d79e8796",
    "NYG": "c4617db381c8c813de5b50adf5a74d92fd0709ecf1ed55f621f9d1446ed38c4b",
    "NYJ": "da2d4d3e8eea163a2fdb5c083739452b568e307adea0608b82687994fcb0f5fb",
    "OAK": "8dfcbc861300492238a07bb356c5665e52817119a6939d94b650222eff6692b2",
    "PHI": "4c5ee328ccd7d0574256e0c6c73921d8652b7f991e2a73dbfe44fe54d4816339",
    "PIT": "8bcbae3eb04da78cecdd853f5e240c700b07250443131d63463f83c0884c8ee6",
    "PRACTICE": "4a37c352eb044b962d569fd6fe733685709281c22e22b79d6753d6567351267a",
    "reference": "0960070f20aa24eed8105a06ff8ad870cedf9cd29383f8d6b6b43fe463fb2428",
    "SD": "677293e34f837d378fccb197482f8c659d198d478ac79090832653290753ca2f",
    "SEA": "347505f9f4166118c538a721b3460b877df61ae6f4644f36487afd6f0e92e134",
    "SF": "cd03fbd32c7bb6bfc2761331707ea2de48179d502bdd1b2d7e2d12abbe3e6684",
    "STL": "01e068a82f83b6bc34c8e324a9b6bb01002922bca0e25d8d58df890b85bd256e",
    "TB": "486a5ad141a00dd2585de6cc29715f307940c24528b2c57cb37107879230e5f8",
    "TEN": "c0ae8f345311815e0a3b99992fc8f281b2fe0079bc080908668b0098dc38a54d",
    "WAS": "f56eaacfec458fb24ad3f737e82e49051fe7581b740f6c5e9dd43cef9a4987d8",
    "WCO": "e6bb5d305e90800feaa2b2a1f4fe58cee1a82f92ff8387314c6a10f99b1af744",
}
# sha256 of the same records after the default recode (prevent_two_edges=False)
APPLIED_TABLE_SHA256: Mapping[str, str] = {
    "ARZ": "86c40eb534457658f2ec727a752669dc46420b12752ccdb5134e1c4c190e0aab",
    "ATL": "e9444879fc1ff05ec13919a0a61bf2bbd2eb6ff029c99b55c65647c1391a6cdc",
    "BAL": "ea63b06fd77a02ef036fda559da499adb7254f5b6766382495c12b1ac1405f83",
    "BUF": "6740f9a204671e30b76d688007fbb51dcd822b89a5a57614ff7ba1307806efa1",
    "CAR": "a58fb3819da21b454255a916771928ecd52ea0f31f8cfb485a38861d675da728",
    "CHI": "193301f52cc79cb4bd1cfe68c635ee82f075553c68c404ade6e570c0b982e9aa",
    "CIN": "fd7245b53bdcdc57f6bf8bd852213f60d9dfbc117c8bf76d4ce279e3d01e6363",
    "CLE": "a9cc14c5d13b6b9367982a29afeae1e1153458c2c51b17741ff23135620f6964",
    "DAL": "bf32e1dee22b6da6cb3f50cc6ce65558094389e3391e21192437b78591352454",
    "DEN": "482b67b4064d941b672d40cc38816a52de9b7e37fb30f10335b48a7bcab67df3",
    "DET": "19c989cc450c23d4d81c23766bc0d835cde779db0823f300ff886e9e4b61b146",
    "Editor": "4891411459a523bf30e6f2aafbfabac1dc2bff0876641fea464f83ea7d2b3ef7",
    "GB": "bfc89d1534af252ca47e22be0391be9092c4f069e95bd90da731b31bf33030e3",
    "GEN": "4ee7df6868e300c1c27bebca184371dd336a24845c6ea5a899e2f345a896f9b5",
    "HOU": "f690995886c61bdd253738f0c81cc7a714eb0f8945f596388856e71e5d8d7757",
    "IND": "01dae56029cc32f6aa714628f67f2c9927d7249bee4a84fcbb288fc2d9bcf717",
    "JAX": "ea920220f1ea44cea70e3f99179dc15afe2267fb565608fe75e4761f7fa83dbc",
    "KC": "96826f79d9109b505ee2ce5ad9015d71bbccc9c5c5a280526180a01845628603",
    "MIA": "d89ad8dfa2463d15e5daba303c2888ef1ceb803f76ad2c76c3a1790d11ba818e",
    "MIN": "8ad49fe6467c0a1c998a836998cc01d93a7ce28584cb6bf16022a3752e60d73b",
    "NE": "e177e248694e1330f5f791df70f4a9819c4c7c0aedd00e8881cbfe68eba38d51",
    "NO": "96a117a97e39892ab9eaa4b0b9f381da29de1ab77bfe8f6331599ffe71a75c9d",
    "NYG": "5457a201c09e850e6b9ab50f70aa34cdef11c2ec4bbe34fd24f86f93b97811b5",
    "NYJ": "0d6a9b3ac4ff8b7723069db3c4cb4a7fe3b6996119ffb7f091783692fefd3ec1",
    "OAK": "408f69cb58f9b7f188c41215d5e6f69b3803634d34cc7f5b64b0df281cfc60a5",
    "PHI": "e1738121b37c6238b42afa589d8d38a85cdfab1e4e350300deef27eb72e3b6b7",
    "PIT": "d472c0300a745834f3617bb3fe8c81143fc3ee6b8b94a9545f66f67c0029528c",
    "PRACTICE": "7e18f29a1cab36808768989882026087a530d6557a92d1c654588e339da4dda6",
    "reference": "4f6f78bbe16e3914956c89c7408da4a3201eaa54178f0a8890d60b867bcf7b5c",
    "SD": "090c5cd0248bcc680ac9a6c1d4df5fe45d63db198987936ff6836f8576d8a794",
    "SEA": "359d8c8a4c8b13e95d0ac88a5216aa1666c217fe4486a107461a6f7d7cc6afc1",
    "SF": "e4ecbe9fa22767c3518637a422580b2557a7f32b1841ee8cedf0505c459d1e00",
    "STL": "2a704669c1228306014ed09df479912f3bf5bae0fba1fdfa163a7629dd2153df",
    "TB": "79c38fbec0ec58c58a6e5747387b03ff7b5ed16d15fa3ede5f9358d88b8d71a7",
    "TEN": "c29df10a68fd851cca39068f4f96398a68d79673d7befd296d4a0bd11c00ef1c",
    "WAS": "1a21181ec869730fd66f1695dd16f074b3476ab2e9721945957eeeef377edab3",
    "WCO": "d493dbdeee63f07efb00d101fd4da5f086127c869ec4d099d5ee985ab14bdc80",
}


def recoded_table(book: Book, *, prevent_two_edges: bool = False) -> tuple[bytes, list[tuple[Category, list[int], str]]]:
    table = bytearray(book.table_bytes())
    changes = []
    for cat in book.categories:
        new, rule = recode_codes(cat.codes, cat.formation_type, prevent_two_edges=prevent_two_edges)
        off = cat.index * CATEGORY_SIZE
        table[off + 5: off + 16] = bytes(new)
        changes.append((cat, new, rule))
    return bytes(table), changes


def book_state(book: Book, retail: Mapping[str, str] | None = None, applied: Mapping[str, str] | None = None) -> str:
    """'retail' / 'applied' / 'applied-custom' / 'foreign' for one book; ``retail``/``applied`` override
    the embedded digest maps (tests, other discs)."""

    digest = book.table_sha256()
    if (RETAIL_TABLE_SHA256 if retail is None else retail).get(book.name) == digest:
        return "retail"
    if (APPLIED_TABLE_SHA256 if applied is None else applied).get(book.name) == digest:
        return "applied"
    if not any((c & 0x1F) == KIND_OLB for cat in book.categories for c in cat.codes):
        return "applied-custom"        # recoded with non-default options (no OLB-kind code survives)
    return "foreign"


def summarize(states: Mapping[str, str]) -> str:
    values = set(states.values())
    if values == {"retail"}:
        return "retail"
    if values and values <= {"applied", "applied-custom"}:
        return "applied" if values == {"applied"} else "applied-custom"
    return "foreign" if values == {"foreign"} else "partial"


def status(path: Path | str, names: Sequence[str] | None = None, *, retail: Mapping[str, str] | None = None,
           applied: Mapping[str, str] | None = None) -> dict[str, object]:
    with OuterImage(path) as archive:
        books = load_books(archive, names)
    states = {b.name: book_state(b, retail, applied) for b in books}
    return {"status": summarize(states), "books": states}


# ---------------------------------------------------------------------------------------------
# Inspect / apply
# ---------------------------------------------------------------------------------------------

def inspect_rows(books: Iterable[Book], *, prevent_two_edges: bool = False) -> list[dict[str, object]]:
    rows = []
    for book in books:
        _table, changes = recoded_table(book, prevent_two_edges=prevent_two_edges)
        for cat, new, rule in changes:
            if rule == "untouched":
                continue
            rows.append({"book": book.name, "category": cat.name, "index": cat.index,
                         "type": f"0x{cat.formation_type & 0x3F:02x}", "rule": rule,
                         "shape": front_shape(cat.codes),
                         "before": " ".join(code_label(c) for c in cat.codes),
                         "after": " ".join(code_label(c, pooled=True) for c in new),
                         "before_hex": bytes(cat.codes).hex(), "after_hex": bytes(new).hex(),
                         "changed": new != cat.codes})
    return rows


def format_inspect(rows: Iterable[dict[str, object]]) -> str:
    lines = []
    current = None
    for row in rows:
        if row["book"] != current:
            current = row["book"]
            lines.append(f"== {current}")
        mark = "*" if row["changed"] else " "
        lines.append(f"  {mark} cat{row['index']:2d} {row['category']:<18} type={row['type']} {row['rule']:<9} "
                     f"{row['before']:<52} -> {row['after']}")
    return "\n".join(lines)


def apply(path: Path | str, *, prevent_two_edges: bool = False, names: Sequence[str] | None = None,
          retail: Mapping[str, str] | None = None, applied: Mapping[str, str] | None = None,
          progress: Callable[[str], None] | None = None) -> dict[str, object]:
    """Recode every stock book inside the image at ``path`` (a COPY).  Refuses non-retail tables."""

    say = progress or (lambda _m: None)
    with OuterImage(path, writable=True) as archive:
        books = load_books(archive, names)
        states = {b.name: book_state(b, retail, applied) for b in books}
        bad = {n: s for n, s in states.items() if s != "retail"}
        _require(not bad, "refusing: category tables are not retail in " + ", ".join(f"{n} ({s})" for n, s in bad.items()))
        written = []
        rows = []
        for book in books:
            table, changes = recoded_table(book, prevent_two_edges=prevent_two_edges)
            before = book.table_bytes()
            if table != before:
                count = archive.write(book.table_offset, table)
                _require(count == len(table), f"{book.name}: short write")
                check = archive.read(book.table_offset, len(table))
                _require(check == table, f"{book.name}: read-back differs")
            changed_categories = [cat.name for cat, new, _r in changes if new != cat.codes]
            written.append({"book": book.name, "entry": book.entry_index,
                            "table_virtual_offset": f"0x{book.table_offset:x}",
                            "table_image_offset": f"0x{archive.image_offset(book.table_offset):x}",
                            "changed_bytes": sum(1 for a, b in zip(before, table) if a != b),
                            "categories_changed": changed_categories,
                            "before_sha256": book.table_sha256(before),
                            "after_sha256": book.table_sha256(table)})
            rows.extend(inspect_rows([book], prevent_two_edges=prevent_two_edges))
            say(f"recoded {book.name}: {len(changed_categories)} categories")
        after = {b.name: book_state(b, retail, applied) for b in load_books(archive, names)}
    return {"schema": "nfl2k5_playbook_position_recode/v1", "image": str(path),
            "prevent_two_edges": prevent_two_edges, "before": states, "after": after,
            "status": summarize(after), "books": written,
            "changed_bytes": sum(int(w["changed_bytes"]) for w in written), "categories": rows}


def digests(path: Path | str, names: Sequence[str] | None = None) -> dict[str, dict[str, str]]:
    with OuterImage(path) as archive:
        books = load_books(archive, names)
    return {"retail": {b.name: b.table_sha256() for b in books},
            "applied": {b.name: b.table_sha256(recoded_table(b)[0]) for b in books}}


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_inspect = sub.add_parser("inspect", help="list every defensive category before/after per book (no writes)")
    p_inspect.add_argument("path")
    p_inspect.add_argument("--book", action="append", help="limit to these books (repeatable)")
    p_inspect.add_argument("--prevent-two-edges", action="store_true")
    p_inspect.add_argument("--json", action="store_true")
    p_status = sub.add_parser("status", help="retail / applied / foreign per book")
    p_status.add_argument("path")
    p_apply = sub.add_parser("apply", help="recode the category tables inside the image (a COPY)")
    p_apply.add_argument("path")
    p_apply.add_argument("--prevent-two-edges", action="store_true")
    p_apply.add_argument("--receipt", help="write the JSON receipt here")
    p_digests = sub.add_parser("digests", help="print the retail and applied category-table digests")
    p_digests.add_argument("path")
    args = parser.parse_args(argv)

    if args.command == "inspect":
        with OuterImage(args.path) as archive:
            books = load_books(archive, args.book)
        rows = inspect_rows(books, prevent_two_edges=args.prevent_two_edges)
        print(json.dumps(rows, indent=1) if args.json else format_inspect(rows))
        return 0
    if args.command == "status":
        print(json.dumps(status(args.path), indent=1))
        return 0
    if args.command == "apply":
        receipt = apply(args.path, prevent_two_edges=args.prevent_two_edges, progress=print)
        if args.receipt:
            Path(args.receipt).write_text(json.dumps(receipt, indent=1), encoding="utf-8", newline="\n")
        print(json.dumps({k: receipt[k] for k in ("status", "changed_bytes", "prevent_two_edges")}, indent=1))
        return 0
    if args.command == "digests":
        print(json.dumps(digests(args.path), indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
