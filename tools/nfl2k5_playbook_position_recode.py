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
* **Prevent** (type 0x10, b776-de1): the retail slot 0 is a linebacker that drops in every Prevent coverage
  (``OLB0`` in 31 books; ``ILB1`` in MIA and reference), while its three linemen (``DE1 DE0 DT0``) rush. The old odd rule
  made slot 0 an EDGE, so the team's first edge rusher dropped into zone or man on all six Prevent coverage plays (Noah,
  SB XLII moment: "Strahan in coverage, he's an edge, why would the edge be in coverage"). Prevent now takes the even
  rule: OLB codes become LB codes, DE stays EDGE, DT stays interior, which fields ``LB1 EDGE EDGE DT0``;
* **odd front** ``(2, 1)`` (3-4, 3-4 Nickel/Dime, 3-3, 3-2, Dime Odd): the DT and DE codes
  become interior codes ``DT0 DT1 DT2`` (retail DTs first in variant order, then DE0, DE1), OLB codes
  become EDGE codes with the same variant (kind 12), ILB codes are unchanged (kind 14 = the LB pool);
* **5-2** ``(3, 2)``: DE0/DE1 stay (EDGE), DE2 becomes the next free interior variant, OLB codes
  become LB codes (below), ILB unchanged;
* **even front and everything else** (4-3, Nickel, Dime, Bear, Goalline, special teams): DE and DT
  codes are unchanged (EDGE is the DE kind), ILB codes unchanged, OLB codes become LB codes with
  variant ``v + 1`` bumped past any variant an ILB code already uses (4-3 ``OLB1 ILB0 OLB0`` ->
  ``LB2 LB0 LB1``: MIKE = #1, WILL = #2 via the side chain, SAM = #3 via rank row 1 + skip;
  Kickoff ``OLB2 OLB3`` -> ``LB3 LB4``);
* ``--prevent-two-edges``: kept for old command lines. Prevent always keeps both ends as EDGE now (see above), so the
  flag changes nothing.

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
    if rule == "odd" and (formation_type & 0x3F) == FORMATION_TYPE_PREVENT:
        rule = "prevent"          # the even recode: slot 0 is a dropping linebacker, the three linemen rush
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
        used: set[int] = set()
        assign_interior(dts + des, used)
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
    assign_lb_codes()                      # even fronts and Prevent
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
        with index.open("rb") as handle:
            header = handle.read(HEADER_SIZE)
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

    def relocated_table_sha256(self) -> str:
        """Hash the ordered distinct records without category-table indices.

        Menu compaction moves records and can retire an unused duplicate such as
        Bear sharing 4-3's personnel. Every distinct type/personnel record must
        still match the retail sequence; new or changed records are refused.
        """
        records = self.defensive_records()
        distinct = dict.fromkeys(records[i + 1:i + 13] for i in range(0, len(records), 13))
        return hashlib.sha256(b"".join(distinct)).hexdigest()


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
# Distinct retail records in order, excluding relocatable table indices and duplicates.
RELOCATED_RETAIL_TABLE_SHA256: Mapping[str, str] = {
    "ARZ": "1af4d126f5ac2ce1925acef2d30d62e7f5d93aa94706f7decabf1ac6ec01e908",
    "ATL": "9868944a28e95eb36ebf895a5ddaea1a82df9387c0f317c8fc955812a552336a",
    "BAL": "8d350d7d9c8379c87d1693d2c80059bbbe9a4e712ec1e84f75267e6e2b879a45",
    "BUF": "fc0d8c95bcc192ec55fca2fc1773d9b54a45ce9885f092eadeb33650d2ec9ea1",
    "CAR": "fae3d45d720ddaa1e0119792d7b91f1be5a8ff243d906a69b7fd48cc955c2156",
    "CHI": "1dc277c3f07ec966b2f1d947968fa724ead42641407864e4ade043ddb4a39a28",
    "CIN": "6dca7f3a22443c24ff08d123951f875959f80d580d60560169ed4f6092c6f8b1",
    "CLE": "c4da3abfea91fd488b584fb472cc92d1023325046871c157e459e6db901f2bf1",
    "DAL": "45b8f8ec8428ea44fb5a7759a82a1d3835f4a4e1c649886e26c2107cf29b097a",
    "DEN": "b4842555326b9ffda7b6f1c74f1613262b7402db9540a6b3eda21c42b56efdec",
    "DET": "8f1427036448f77303817385768084269c7c18bc5c351a2cc8a194564b31bfb5",
    "Editor": "be9408b6bb41a761874ca35845bb899f2eddc3925f95554622ed3be1f3f7aaf2",
    "GB": "bc83e558cbe572bf80e69dbf4550886199990b54cb172919774679d956ead780",
    "GEN": "04d71c51657181646eaccce4d9dbb7a6590a0fe3b903ec3c176ca95235020c9e",
    "HOU": "732dba2a66a03dfd9e2edba2589888a7a084b4b28ed044bc50913a72e2168cd3",
    "IND": "9511ec189f07182657b32a1d5d93504e09c9058ef0ce93cd9de84a37ab1d0458",
    "JAX": "f8dc2ec8ac4d9176bbd070c31fcb4ec9e32919310bcf87dcbfaf3d36b7fea512",
    "KC": "3a3278a1097b347f48cdc1bb678bc4d87994a1c70848dbe40134f17413df7fc3",
    "MIA": "dcc47b6b76b73d089d4b0d55e05c897d47db30ad715cc37dd1cd4ab403076f49",
    "MIN": "eca8b207e0772d5353b1f900656071df382c83f5279f9f5d89787bb6ee13d174",
    "NE": "6426aa558fe3af981890805fee826b4e3e51e2e693042c57ad192e226240d166",
    "NO": "eb0fb505cb6b92b60edd0d95a704b97e136f97735834367e109efad02e0daa43",
    "NYG": "ab240e035c73945a90a51e27518469e44dcecd4d65c7fed888bc89f79123faac",
    "NYJ": "f922c610ce6191303457227b6687046ff3e766d61a03ec8d15cbcb29ca2849e2",
    "OAK": "dacfadd3a8c00ce884264e80bc0ba925d730bb292c8eb23cf579ea2f6f474aed",
    "PHI": "98ca6f3570acf83b35a47e1545a176b99c213c3ad38865101e7534669590f876",
    "PIT": "8158394ab419b6c21cfd452acf9b7a8be88658be775fbf92d90fd41dd98f1fcc",
    "PRACTICE": "0fd63b2c3b0ac9891f4f15168868f96562dc53c5856be08836cd163b6d5976c6",
    "reference": "e4f06f548ac3706ebc3f907128539f7c01c558f2c4d1da4c628a55f8edd09f4e",
    "SD": "50d87c6794a5d6abe877ea6ebf2880452357da4cc4a17e94a35e678d0d35ca3d",
    "SEA": "fe0116549cddc01d14bda063beef1794baaa1f3316bb61f9dda3e3bddbcf1f8f",
    "SF": "dbdf02025e87dfc44cd4cca16f3d45342e5c2fbf0769e4aa37ca860170646b1e",
    "STL": "50c3efc616531a25993c9f804e372800fac029a6a4b2558fd5301660d80b3b45",
    "TB": "4d91809d74b936f9030a53420acec5654102a3dda3782cfaba3ed1b017f9ed36",
    "TEN": "3cfd0bf9c7b692e7e673f838962e7eab62eadad99ddf507ab54f8298ba4f0daf",
    "WAS": "fe0116549cddc01d14bda063beef1794baaa1f3316bb61f9dda3e3bddbcf1f8f",
    "WCO": "27e47f71689cc594cc0d6593cfe7239d60f5fb9644f3c76e8873ce3636a7e8f5",
}
# sha256 of the same records after the default recode (prevent_two_edges=False)
APPLIED_TABLE_SHA256: Mapping[str, str] = {
    "ARZ": "2fdbd84a138ab5a62db01f05063b116263f66133aac25861af1b4b2ff71abe9e",
    "ATL": "f836e2c18f93aad0125fb0c0523732fcebbf9f295577101b3cf71ff6c924c733",
    "BAL": "0a2b45b6adddb5475bd8231a4a6effb379442ec825a6d1c700018b619923746e",
    "BUF": "2890147578dd41e3159acd86e945fb98c77128905f8f036a6f21730527ff5d03",
    "CAR": "d42e4d904815971cb7ed77d9966067e806f222e4dbd5a8588014a163ea7962b8",
    "CHI": "79235548a260684518a5c1fbe35e7f067e4d6f6ebc36844aff9271f8ae3d0430",
    "CIN": "a6daff7385fb3e148873a7c8083195cc6eb851fb232d808e87c13d32bbb0ac50",
    "CLE": "2457ba6d46996d90fd27987dbc257658535b2038416a6ce3b14e02e5986f3c2c",
    "DAL": "0e9dd579236e408c22dc83cff14fbe46aa56e83bd5edf0f83cd4219a59bf14e0",
    "DEN": "00a8d445d4bc5e9133bbf1f7d67cafb2a4b490908a56785c0bcc28fe11f11ce0",
    "DET": "7d535e938488ae0264d9b8d6039e0bdc0552ca7402468bb21f07840d6e347190",
    "Editor": "4891411459a523bf30e6f2aafbfabac1dc2bff0876641fea464f83ea7d2b3ef7",
    "GB": "c64deb4f7c533c90817fcfea215afd08b490812404ee3e6da58418b20ff677cc",
    "GEN": "57f2703c4cb396e3d280ccecedd97183e1dd5be40919cdfc05e697de1a868ebb",
    "HOU": "f7bce49706bdb5e57271d68b6e77cb909f763ebe71149b395ac208d0f77a589f",
    "IND": "e9df6ebe470379b5da4b42a4335167c5ca63848c27dce796a28559b223bfe3a8",
    "JAX": "cbfa6768ac82b520f969844ad954a928c4d9376ef8ce770275c751f80b567f87",
    "KC": "f9f3e04a1b3492320a104949bb582b76f065fddb897f53aa32e9494770b8296f",
    "MIA": "e9df7f132003e728ca5cb77ca17e0aba05be621489e80c1d44f9cd7e6f897ae7",
    "MIN": "0522ed0c9707230abffd41beaf66e46e22fa531fcb01cffd6a6951c068699387",
    "NE": "2036475d18aa3f03681e4e21d5afef9e4ffbe404eb398f3ad32574e39afd361e",
    "NO": "c62c05ecd01af5b5d905c44f38c90dc8e0f20d4ace1e96a08a3cfa4fa35e07e8",
    "NYG": "8881ead98c7c9d3dbb55510b1f1872cd64186a5f43742dd98d1d52148e5903ad",
    "NYJ": "78b082733ff12575577bd72c63a628d594df6af45054b66b33187c4b1d75d92e",
    "OAK": "ef3857bfe52e8c02687001dac4aaeb9d8e9cbf985b772b98cc1f143acfa25e7a",
    "PHI": "8db6801dbf16fb6e3d2608ce4d26a0892c3eab4a4031377d82cbdf5a026ff624",
    "PIT": "0b88a313d99933646a237422811b97f3be2c5ca6302ed6b6ed547ef1b2fc917a",
    "PRACTICE": "7e18f29a1cab36808768989882026087a530d6557a92d1c654588e339da4dda6",
    "reference": "e9db23c1078783c0b444946d707c59b484d15ae1b70890cdc2cd4d85f9be41e1",
    "SD": "3db228f0f9eebb465f78344a47c74b8a45a8167346d4fa48854c5e271c0fdc79",
    "SEA": "70675cb2b6b45383d6f0c1be89a60741d0ea3f3fa2da7054019adb61f3ecb77d",
    "SF": "9cce52cb66ef2572310a17e9f91e78fde5add5e7cbd9f9e50f1af996ed73cdba",
    "STL": "b3b948a74a106245d675f8c1b31a3eab634d357470fb9e0be6836f92a0d859d1",
    "TB": "a6552636842b0b91a736e72a01dce5b606bbe246c91f6970483d669bb6232e14",
    "TEN": "26f6676e19f62f4ad27386a7eada443802f50bd61457e1fd5fe5b4a9154d918a",
    "WAS": "0d23527c4d0d814a2836331aa7e4d1afc9bdabed9e95ea20ad9293ecbc900896",
    "WCO": "e9abc42c566c5c37fa99e1ffd333b8160da9befccc718c8976c71b26024f056f",
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
    if retail is None and RELOCATED_RETAIL_TABLE_SHA256.get(book.name) == book.relocated_table_sha256():
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
