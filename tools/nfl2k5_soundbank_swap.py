#!/usr/bin/env python3
"""Swap NFL 2K5 in-game sound-bank samples (BANK -> ABNK/WBNK) inside a COPIED disc.

Every hit, grunt, pad, ball, whistle, crowd reaction and QB cadence line the
game plays during a down lives in one of three sound banks inside the outer
archive ``vc_53450030``.  Each bank is described by a tiny ``BANK`` chunk and
stored as one external outer entry that is a stack of equal-size *sub-banks*::

    BANK descriptor (outer 510 / 511 / 512, the whole outer entry):
      +0x00  0x20-byte wrapper ("BANK", stored_size, 0 ...)
      +0x20  UTF-16LE file name        "sfx_game.bnk" / "sfx_safe.bnk" / "qb_at_line.bnk"
      +0x60  u32 sub-bank count N      20 / 12 / 40
      +0x64  u32 sub-bank stride S     471,200 / 1,565,556 / 71,528   (external size = N x S)
      +0x68  u32 ABNK body size
      +0x6C  u32 WBNK capacity         (largest WBNK body of any sub-bank)
      +0x70  u32[N] sub-bank ids       CRC32(UTF-16LE "000.iff"), "001.iff", ...

    External bank (outer entry named CRC32(upper UTF-16LE "SFX_GAME.BNK") ...):
      N x [ 0x20 "ABNK" wrapper | ABNK body | 0x20 "WBNK" wrapper | WBNK body | "ENDB" + zero pad to S ]

    ABNK body:  u32 count; u32 0; count x { u32 sample_id, u32 desc_off };
                descriptors at (8 + 8*count) + desc_off, 0x40 bytes mono / 0x80 stereo:
                { ch, ch, 0x11, data_off, bytes, 0, bytes/ch, rate } ...
    WBNK body:  raw Xbox IMA ADPCM (36 bytes per channel per 64-frame block);
                sample payload = body[data_off : data_off + bytes]

``sample_id`` is the CRC32 (standard polynomial) of the case-sensitive UTF-16LE
sample name ``<base>_<NN>`` (``hit-pads_03``, ``snap-hut-num1_02``).  The slot
list (ids) is identical in every sub-bank of a bank, but the *allocation* of a
slot -- bytes, and on two whistle slots even the rate -- varies per sub-bank,
because each sub-bank carries its own recording of the variant.  The game
rotates the sub-bank in use every play (``"%03d.iff"`` counter), so replacing a
sample means writing every sub-bank; ``--subbank N`` narrows it to one.

Sub-commands (only ``replace`` writes, and only in place, so use a copy)::

    list     XISO [--bank sfx_game] [--json]
    export   XISO --bank B --sample NAME [--subbank N ...] --out DIR
    conform  XISO --bank B --sample NAME --input ANY_AUDIO --out clip.wav   (ffmpeg)
    synth    --out tone.wav --rate 20000 --channels 2 --seconds 3 [--kind tone|beep2]
    replace  XISO --bank B --sample NAME --wav clip.wav --retail-packs DIR [--subbank N] [--receipt R.json]
    verify   XISO --bank B --sample NAME --wav clip.wav [--decoded-dir DIR]

Allocation rule: the replacement is encoded at the payload's own rate and
channel count (resampled / re-mixed from the WAV when they differ), padded with
digital silence or trimmed (with a short fade) to the payload's exact block
count, and written over exactly those bytes.  Descriptors, directories, the
WBNK sizes and every other byte of the disc are untouched, so nothing that the
game indexes by offset moves.  ``replace`` re-reads the retail bytes of every
span from the extracted retail packs first and refuses to write over anything
else unless ``--force`` is given.

The codec is ``tools/xbox_ima_encoder.py``; the XDVDFS walk is
``tools/nfl_uniform_color_xiso_direct_patch.parse_xdvdfs``; the outer-archive
model is ``tools/nfl_outer``.  ``nfl2k5_audo_swap.py`` shares ``XisoArchive``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402
from nfl_outer import (  # noqa: E402
    ALIGNMENT,
    ENTRY_SIZE,
    HEADER_SIZE,
    MAX_ENTRIES,
    PACK_NAMES,
    PACK_SLOT_COUNT,
    Entry,
    Pack,
    align_up,
    range_segments,
)
import xbox_ima_encoder as ima  # noqa: E402

PACK_FOLDER = "vc_53450030"
WRAPPER_SIZE = 0x20
BLOCK_FRAMES = ima.BLOCK_FRAMES
CHANNEL_BLOCK_BYTES = ima.CHANNEL_BLOCK_BYTES
CODEC_WORD = 0x11
MONO_DESCRIPTOR_SIZE = 0x40
STEREO_DESCRIPTOR_SIZE = 0x80
MAX_SUBBANKS = 256
MAX_SLOTS = 4096
MAX_VARIANT_SUFFIX = 64

# (bank key, BANK descriptor outer index, external file name) of the retail disc.
# The descriptor is verified at open time (magic, name, N x S == external size,
# sub-bank id list), so a disc whose banks moved fails closed.
PINNED_BANKS: tuple[tuple[str, int, str], ...] = (
    ("sfx_game", 510, "sfx_game.bnk"),
    ("sfx_safe", 511, "sfx_safe.bnk"),
    ("QB_at_line", 512, "qb_at_line.bnk"),
)

BANK_ROLES = {
    "sfx_game": "in-game SFX: hits, pads, helmets, grunts, grabs, ball, snap, kick, pass, tips (rotates every play, mod 20)",
    "sfx_safe": "referee whistles, crowd reactions (cheer/aww, front+rear layers), play-call menu (rotates at play end, mod 12)",
    "QB_at_line": "QB cadence: down / set / colour / hut / audible (sub-banks 0-19 home offence voice, 20-39 away)",
}

# Sample base names known from the AMCR cue tables and the audio map.  A slot is
# named only when CRC32(UTF-16LE "<base>_<NN>") equals its directory id, so a
# wrong guess here can never mislabel a slot; unresolved slots are "slotNN".
KNOWN_SAMPLE_BASES: tuple[str, ...] = (
    # sfx_game
    "tip", "tacklewhoosh", "subhit", "stiffarm-soft", "stiffarm-hard", "snap",
    "push-hit-mult", "push-hit", "pass", "padhit-light", "padclatter", "limbfall",
    "kick", "hit-swtnr", "hit-subchannel", "hit-pads2", "hit-pads", "hit-midsub",
    "hit-grntlow", "helmets", "handhithelmet", "handcontact", "handclap",
    "grunttackle", "grunt-line", "gruntcon-soft", "gruntcon-hard", "grunt-throw",
    "grableg", "grabbody", "grabarm", "catchhands", "catchbody", "bodyfall",
    "ballsoft", "ballhitpost", "ballhitnet", "ballhard", "grunt-effort-soft",
    "grunt-effort-hard",
    # sfx_safe
    "playcall-menu-go-away", "playcall-menu-display", "whistleshort", "whistlemulti",
    "whistlelong", "cheer-small-rear", "cheer-large-rear", "cheer-small-front",
    "cheer-large-front", "cheer-rear", "cheer-front", "aww-rear", "aww-front",
    "idle-mem-front", "idle-mem-rear", "boo-front", "boo-rear", "chant-def-front",
    "chant-def-rear",
    # QB_at_line
    "snap-num1", "snap-hut-num1", "snap-audible-num1", "snap-color-num1",
    "set-num1", "down-num1",
)

O_BINARY = getattr(os, "O_BINARY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class SoundbankSwapError(ValueError):
    """Anything that must stop the tool before it touches the disc."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SoundbankSwapError(message)


def sample_name_id(name: str) -> int:
    """The game's sample id: CRC32 of the case-sensitive UTF-16LE name."""

    return zlib.crc32(name.encode("utf-16le")) & 0xFFFFFFFF


def outer_name_id(filename: str) -> int:
    """The outer-archive entry id: CRC32 of the upper-cased UTF-16LE file name."""

    return zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF


def subbank_file_id(index: int) -> int:
    return sample_name_id(f"{index:03d}.iff")


def build_name_table(bases=KNOWN_SAMPLE_BASES, max_suffix: int = MAX_VARIANT_SUFFIX) -> dict[int, str]:
    table: dict[int, str] = {}
    for base in bases:
        for number in range(1, max_suffix + 1):
            name = f"{base}_{number:02d}"
            table.setdefault(sample_name_id(name), name)
    return table


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- disc
@dataclass(frozen=True)
class DiscSpan:
    """One contiguous byte range of the disc image."""

    xiso_offset: int
    length: int
    pack_name: str
    pack_offset: int

    def describe(self) -> dict[str, object]:
        return {"xiso_offset": self.xiso_offset, "length": self.length,
                "pack": self.pack_name, "pack_offset": self.pack_offset}


def _pread_exact(descriptor: int, offset: int, length: int) -> bytes:
    parts: list[bytes] = []
    done = 0
    while done < length:
        chunk = xiso.pread(descriptor, length - done, offset + done)
        _require(bool(chunk), f"short read at 0x{offset + done:x}")
        parts.append(chunk)
        done += len(chunk)
    return b"".join(parts)


def _pwrite_exact(descriptor: int, data: bytes, offset: int) -> None:
    view = memoryview(data)
    done = 0
    while done < len(view):
        count = xiso.pwrite(descriptor, bytes(view[done:]), offset + done)
        _require(count > 0, f"short write at 0x{offset + done:x}")
        done += count


def _utf16z(data: bytes, offset: int, limit: int) -> str:
    end = offset
    while end + 1 < limit and data[end:end + 2] != b"\0\0":
        end += 2
    _require(end + 1 < limit, f"unterminated UTF-16 string at 0x{offset:x}")
    return data[offset:end].decode("utf-16le")


class XisoArchive:
    """The outer archive ``vc_53450030`` of one XISO, addressed by disc byte spans.

    Opens the image (read-only unless ``writable``), walks XDVDFS to find the
    16 pack files, parses the archive index in pack ``0`` and maps any relative
    range of any outer entry to absolute disc spans, crossing pack seams.
    """

    def __init__(self, path: Path, *, writable: bool = False) -> None:
        self.path = Path(path)
        _require(self.path.is_file(), f"not a file: {self.path}")
        _require(not self.path.is_symlink(), f"refusing a symlink: {self.path}")
        flags = (os.O_RDWR if writable else os.O_RDONLY) | O_BINARY | O_NOFOLLOW
        self.descriptor = os.open(self.path, flags)
        self.writable = writable
        try:
            self.image_size = os.fstat(self.descriptor).st_size
            try:
                entries, _info = xiso.parse_xdvdfs(self.descriptor, self.image_size)
            except xiso.PatchError as exc:
                raise SoundbankSwapError(f"not an NFL 2K5 XISO: {exc}") from exc
            self.entries = entries
            self.pack_extents = self._pack_extents()
            self.archive_entries = self._parse_archive()
        except Exception:
            os.close(self.descriptor)
            self.descriptor = -1
            raise

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def __enter__(self) -> "XisoArchive":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _pack_extents(self) -> dict[str, xiso.XdvdfsEntry]:
        header_entry = self.entries.get(f"{PACK_FOLDER}/0".casefold())
        _require(header_entry is not None, f"disc has no {PACK_FOLDER}/0 pack")
        fixed = _pread_exact(self.descriptor, header_entry.byte_offset, HEADER_SIZE)
        _entry_count, _reserved, populated = struct.unpack_from("<III", fixed)
        _require(1 <= populated <= PACK_SLOT_COUNT, "implausible pack count")
        result: dict[str, xiso.XdvdfsEntry] = {}
        for name in PACK_NAMES[:populated]:
            entry = self.entries.get(f"{PACK_FOLDER}/{name}".casefold())
            _require(entry is not None, f"disc has no {PACK_FOLDER}/{name} pack")
            _require(entry.byte_offset + entry.size <= self.image_size,
                     f"pack {name} extent escapes the image")
            result[name] = entry
        return result

    def _parse_archive(self) -> tuple[Entry, ...]:
        pack0 = self.pack_extents["0"]
        fixed = _pread_exact(self.descriptor, pack0.byte_offset, HEADER_SIZE)
        entry_count, reserved, populated = struct.unpack_from("<III", fixed)
        _require(1 <= entry_count <= MAX_ENTRIES, "implausible entry count")
        _require(reserved == 0, "archive reserved word is not zero")
        block_counts = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", fixed, 12)
        packs: list[Pack] = []
        virtual_start = 0
        for ordinal, blocks in enumerate(block_counts[:populated]):
            name = PACK_NAMES[ordinal]
            size = blocks * ALIGNMENT
            _require(self.pack_extents[name].size == size,
                     f"pack {name}: archive declares 0x{size:x} bytes, disc has "
                     f"0x{self.pack_extents[name].size:x}")
            packs.append(Pack(ordinal, name, blocks, size, virtual_start,
                              Path(f"/xiso/{PACK_FOLDER}/{name}")))
            virtual_start += size
        self.packs = tuple(packs)
        starts = [pack.virtual_start for pack in self.packs]
        table = _pread_exact(self.descriptor, pack0.byte_offset + HEADER_SIZE,
                             entry_count * ENTRY_SIZE)
        entries: list[Entry] = []
        previous_end = 0
        for index in range(entry_count):
            name_id, size, offset_blocks = struct.unpack_from("<III", table, index * ENTRY_SIZE)
            offset = offset_blocks * ALIGNMENT
            _require(size > 0 and offset >= previous_end, f"archive entry {index} is malformed")
            _require(index == 0 or offset == align_up(previous_end),
                     f"archive entry {index} is not contiguous")
            segments = range_segments(self.packs, starts, offset, size)
            entries.append(Entry(index, name_id, size, offset_blocks, offset, "", "", segments))
            previous_end = offset + size
        _require(entries[0].virtual_offset == align_up(HEADER_SIZE + entry_count * ENTRY_SIZE),
                 "archive first payload does not follow its table")
        return tuple(entries)

    def entry(self, index: int) -> Entry:
        _require(0 <= index < len(self.archive_entries), f"archive lacks entry {index}")
        return self.archive_entries[index]

    def entry_by_name_id(self, name_id: int) -> Entry | None:
        matches = [candidate for candidate in self.archive_entries if candidate.name_id == name_id]
        _require(len(matches) <= 1, f"outer id 0x{name_id:08x} is not unique")
        return matches[0] if matches else None

    def entry_spans(self, entry: Entry, relative_offset: int, size: int) -> tuple[DiscSpan, ...]:
        """Map a relative range of one outer entry to absolute disc byte spans."""

        _require(0 <= relative_offset and size > 0 and relative_offset + size <= entry.size,
                 f"range 0x{relative_offset:x}+0x{size:x} escapes entry {entry.table_index}")
        spans: list[DiscSpan] = []
        logical_start = 0
        relative_end = relative_offset + size
        for segment in entry.segments:
            logical_end = logical_start + segment.size
            part_start = max(relative_offset, logical_start)
            part_end = min(relative_end, logical_end)
            if part_start < part_end:
                pack_offset = segment.pack_offset + part_start - logical_start
                extent = self.pack_extents[segment.pack_name]
                spans.append(DiscSpan(extent.byte_offset + pack_offset,
                                      part_end - part_start, segment.pack_name, pack_offset))
            logical_start = logical_end
            if part_end == relative_end:
                break
        _require(sum(span.length for span in spans) == size, "range mapping is incomplete")
        return tuple(spans)

    def pack_spans(self, pack_name: str, pack_offset: int, size: int) -> tuple[DiscSpan, ...]:
        """Absolute span of a pack-relative range (one pack, so always contiguous)."""

        extent = self.pack_extents.get(pack_name)
        _require(extent is not None, f"disc has no pack {pack_name}")
        _require(0 <= pack_offset and size > 0 and pack_offset + size <= extent.size,
                 f"range 0x{pack_offset:x}+0x{size:x} escapes pack {pack_name}")
        return (DiscSpan(extent.byte_offset + pack_offset, size, pack_name, pack_offset),)

    def read_spans(self, spans: tuple[DiscSpan, ...]) -> bytes:
        return b"".join(_pread_exact(self.descriptor, span.xiso_offset, span.length)
                        for span in spans)

    def write_spans(self, spans: tuple[DiscSpan, ...], data: bytes) -> None:
        _require(self.writable, "disc was opened read-only")
        _require(len(data) == sum(span.length for span in spans),
                 "data length does not equal the span length")
        cursor = 0
        for span in spans:
            _pwrite_exact(self.descriptor, data[cursor:cursor + span.length], span.xiso_offset)
            cursor += span.length

    def read_entry_range(self, entry: Entry, relative_offset: int, size: int) -> bytes:
        return self.read_spans(self.entry_spans(entry, relative_offset, size))

    def fsync(self) -> None:
        os.fsync(self.descriptor)


# --------------------------------------------------------------------------- banks
@dataclass(frozen=True)
class Payload:
    """One sample recording: (bank, slot, sub-bank) -> exact WBNK bytes on disc."""

    bank: str
    slot: int
    subbank: int
    name: str
    sample_id: int
    channels: int
    sample_rate: int
    data_offset: int
    size: int
    entry_offset: int
    spans: tuple[DiscSpan, ...]

    @property
    def payload_id(self) -> str:
        return f"{self.bank}/{self.name}@{self.subbank}"

    @property
    def block_align(self) -> int:
        return CHANNEL_BLOCK_BYTES * self.channels

    @property
    def block_count(self) -> int:
        return self.size // self.block_align

    @property
    def frame_count(self) -> int:
        return self.block_count * BLOCK_FRAMES

    @property
    def duration(self) -> float:
        return self.frame_count / self.sample_rate

    def describe(self) -> dict[str, object]:
        return {
            "payload": self.payload_id,
            "bank": self.bank,
            "slot": self.slot,
            "subbank": self.subbank,
            "name": self.name,
            "sample_id": f"0x{self.sample_id:08x}",
            "channels": self.channels,
            "sample_rate": self.sample_rate,
            "wbnk_data_offset": self.data_offset,
            "bytes": self.size,
            "blocks": self.block_count,
            "frames": self.frame_count,
            "duration_seconds": round(self.duration, 6),
            "entry_offset": self.entry_offset,
            "xiso_spans": [span.describe() for span in self.spans],
        }


@dataclass(frozen=True)
class Slot:
    index: int
    sample_id: int
    name: str
    named: bool
    channels: int
    sample_rates: tuple[int, ...]
    min_bytes: int
    max_bytes: int


@dataclass(frozen=True)
class SubbankLayout:
    index: int
    abnk_body_size: int
    wbnk_body_size: int
    trailer_magic: str


@dataclass(frozen=True)
class SoundBank:
    key: str
    external_filename: str
    descriptor_outer_index: int
    external_outer_index: int
    external_size: int
    subbank_count: int
    stride: int
    abnk_size: int
    wbnk_capacity: int
    subbank_ids: tuple[int, ...]
    slots: tuple[Slot, ...]
    subbanks: tuple[SubbankLayout, ...]
    payloads: dict[tuple[int, int], Payload] = field(repr=False, compare=False)
    entry: Entry = field(repr=False, compare=False)

    def payload(self, slot: int, subbank: int) -> Payload:
        _require(0 <= slot < len(self.slots), f"{self.key} has {len(self.slots)} slots; {slot} is out of range")
        _require(0 <= subbank < self.subbank_count,
                 f"{self.key} has {self.subbank_count} sub-banks; {subbank} is out of range")
        return self.payloads[(slot, subbank)]

    def slot_by_name(self, name: str) -> Slot | None:
        for slot in self.slots:
            if slot.name == name:
                return slot
        return None

    def select_slots(self, patterns) -> list[Slot]:
        """Resolve names / globs / ``slotN`` labels to slots, in slot order."""

        chosen: dict[int, Slot] = {}
        for pattern in patterns:
            matched = [slot for slot in self.slots
                       if fnmatch.fnmatchcase(slot.name, pattern) or slot.name == pattern
                       or f"slot{slot.index}" == pattern]
            if not matched:
                lowered = pattern.casefold()
                matched = [slot for slot in self.slots if slot.name.casefold() == lowered]
            _require(bool(matched), f"{self.key}: no sample matches {pattern!r}; "
                                    f"names: {', '.join(slot.name for slot in self.slots)}")
            for slot in matched:
                chosen[slot.index] = slot
        return [chosen[index] for index in sorted(chosen)]

    def describe(self) -> dict[str, object]:
        return {
            "bank": self.key,
            "external_filename": self.external_filename,
            "descriptor_outer_index": self.descriptor_outer_index,
            "external_outer_index": self.external_outer_index,
            "external_size": self.external_size,
            "subbank_count": self.subbank_count,
            "subbank_stride": self.stride,
            "abnk_body_size": self.abnk_size,
            "wbnk_capacity": self.wbnk_capacity,
            "slot_count": len(self.slots),
            "role": BANK_ROLES.get(self.key, ""),
        }


def parse_bank_descriptor(raw: bytes) -> tuple[str, int, int, int, int, tuple[int, ...]]:
    """(file name, N, S, abnk size, wbnk capacity, ids) from one BANK outer entry."""

    _require(len(raw) >= WRAPPER_SIZE + 0x50, "BANK descriptor is too short")
    magic, stored = struct.unpack_from("<4sI", raw, 0)
    _require(magic == b"BANK" and stored == len(raw) - WRAPPER_SIZE,
             "not a BANK descriptor (magic / stored size)")
    body = raw[WRAPPER_SIZE:]
    filename = _utf16z(body, 0, 0x40)
    count, stride, abnk_size, wbnk_capacity = struct.unpack_from("<4I", body, 0x40)
    _require(1 <= count <= MAX_SUBBANKS and stride > 0, "BANK descriptor: implausible sub-bank count/stride")
    _require(0x50 + 4 * count <= len(body), "BANK descriptor: id list is truncated")
    ids = struct.unpack_from(f"<{count}I", body, 0x50)
    _require(WRAPPER_SIZE + abnk_size + WRAPPER_SIZE + wbnk_capacity <= stride,
             "BANK descriptor: ABNK + WBNK do not fit the sub-bank stride")
    _require(ids == tuple(subbank_file_id(index) for index in range(count)),
             "BANK descriptor: sub-bank ids are not CRC32(\"%03d.iff\")")
    return filename, count, stride, abnk_size, wbnk_capacity, ids


class SoundBanks(XisoArchive):
    """The three rotating sound banks of one XISO, every payload span resolved."""

    def __init__(self, path: Path, *, writable: bool = False,
                 banks: tuple[tuple[str, int, str], ...] = PINNED_BANKS,
                 name_table: dict[int, str] | None = None) -> None:
        super().__init__(path, writable=writable)
        try:
            self.name_table = build_name_table() if name_table is None else name_table
            self.banks: dict[str, SoundBank] = {}
            for key, outer_index, expected_file in banks:
                self.banks[key] = self._read_bank(key, outer_index, expected_file)
        except Exception:
            self.close()
            raise

    def bank(self, key: str) -> SoundBank:
        bank = self.banks.get(key)
        if bank is None:
            lowered = key.casefold()
            for candidate, value in self.banks.items():
                if candidate.casefold() == lowered:
                    bank = value
                    break
        _require(bank is not None, f"unknown bank {key!r}; known: {', '.join(self.banks)}")
        return bank

    def _read_bank(self, key: str, outer_index: int, expected_file: str) -> SoundBank:
        descriptor_entry = self.entry(outer_index)
        raw = self.read_entry_range(descriptor_entry, 0, descriptor_entry.size)
        try:
            filename, count, stride, abnk_size, wbnk_capacity, ids = parse_bank_descriptor(raw)
        except SoundbankSwapError as exc:
            raise SoundbankSwapError(f"outer {outer_index}: {exc}") from exc
        _require(filename.casefold() == expected_file.casefold(),
                 f"outer {outer_index} describes {filename!r}, expected {expected_file!r}")
        external = self.entry_by_name_id(outer_name_id(filename))
        _require(external is not None, f"bank {key}: external entry {filename!r} not found")
        _require(external.size == count * stride,
                 f"bank {key}: external size {external.size} != {count} x {stride}")

        payloads: dict[tuple[int, int], Payload] = {}
        layouts: list[SubbankLayout] = []
        slot_ids: tuple[int, ...] | None = None
        per_slot: dict[int, list[Payload]] = {}
        for subbank in range(count):
            base = subbank * stride
            head_size = WRAPPER_SIZE + abnk_size + WRAPPER_SIZE
            head = self.read_entry_range(external, base, head_size)
            magic, stored = struct.unpack_from("<4sI", head, 0)
            _require(magic == b"ABNK" and stored == abnk_size,
                     f"bank {key} sub-bank {subbank}: ABNK wrapper differs from the BANK descriptor")
            body = head[WRAPPER_SIZE:WRAPPER_SIZE + abnk_size]
            _require(len(body) >= 8, f"bank {key} sub-bank {subbank}: ABNK body is too short")
            slot_count, zero = struct.unpack_from("<II", body, 0)
            _require(1 <= slot_count <= MAX_SLOTS and zero == 0,
                     f"bank {key} sub-bank {subbank}: implausible ABNK directory")
            directory_end = 8 + 8 * slot_count
            _require(directory_end <= len(body), f"bank {key} sub-bank {subbank}: ABNK directory is truncated")
            wmagic, wbnk_size = struct.unpack_from("<4sI", head, WRAPPER_SIZE + abnk_size)
            _require(wmagic == b"WBNK", f"bank {key} sub-bank {subbank}: WBNK wrapper missing")
            _require(wbnk_size <= wbnk_capacity and head_size + wbnk_size <= stride,
                     f"bank {key} sub-bank {subbank}: WBNK body escapes the sub-bank")
            wbnk_data_base = base + head_size
            trailer = b""
            if head_size + wbnk_size + 4 <= stride:
                trailer = self.read_entry_range(external, wbnk_data_base + wbnk_size, 4)
            layouts.append(SubbankLayout(subbank, abnk_size, wbnk_size,
                                         trailer.decode("latin-1") if trailer.isalpha() else ""))

            ids_here: list[int] = []
            ranges: list[tuple[int, int, int]] = []
            for slot in range(slot_count):
                sample_id, desc_off = struct.unpack_from("<II", body, 8 + 8 * slot)
                descriptor_at = directory_end + desc_off
                _require(descriptor_at + 32 <= len(body),
                         f"bank {key} sub-bank {subbank} slot {slot}: descriptor escapes the ABNK body")
                ch, ch2, codec, data_off, size, zero2, per_channel, rate = struct.unpack_from(
                    "<8I", body, descriptor_at)
                _require(ch in (1, 2) and ch2 == ch and codec == CODEC_WORD and zero2 == 0,
                         f"bank {key} sub-bank {subbank} slot {slot}: not an Xbox IMA descriptor")
                align = CHANNEL_BLOCK_BYTES * ch
                _require(size > 0 and size % align == 0 and size == ch * per_channel,
                         f"bank {key} sub-bank {subbank} slot {slot}: allocation is not whole blocks")
                _require(1000 <= rate <= 96_000, f"bank {key} sub-bank {subbank} slot {slot}: implausible rate {rate}")
                _require(data_off + size <= wbnk_size,
                         f"bank {key} sub-bank {subbank} slot {slot}: payload escapes the WBNK body")
                ids_here.append(sample_id)
                ranges.append((data_off, data_off + size, slot))
                name = self.name_table.get(sample_id, f"slot{slot}")
                entry_offset = wbnk_data_base + data_off
                payload = Payload(key, slot, subbank, name, sample_id, ch, rate, data_off, size,
                                  entry_offset, self.entry_spans(external, entry_offset, size))
                payloads[(slot, subbank)] = payload
                per_slot.setdefault(slot, []).append(payload)
            ranges.sort()
            for left, right in zip(ranges, ranges[1:]):
                _require(left[1] <= right[0],
                         f"bank {key} sub-bank {subbank}: slots {left[2]} and {right[2]} overlap")
            if slot_ids is None:
                slot_ids = tuple(ids_here)
            _require(tuple(ids_here) == slot_ids,
                     f"bank {key} sub-bank {subbank}: slot id list differs from sub-bank 0")
            _require(len(set(ids_here)) == len(ids_here), f"bank {key} sub-bank {subbank}: duplicate sample ids")

        assert slot_ids is not None
        slots: list[Slot] = []
        for slot, sample_id in enumerate(slot_ids):
            rows = per_slot[slot]
            channels = {row.channels for row in rows}
            _require(len(channels) == 1, f"bank {key} slot {slot}: channel count differs between sub-banks")
            name = self.name_table.get(sample_id, f"slot{slot}")
            slots.append(Slot(slot, sample_id, name, sample_id in self.name_table, rows[0].channels,
                              tuple(sorted({row.sample_rate for row in rows})),
                              min(row.size for row in rows), max(row.size for row in rows)))
        _require(len({slot.name for slot in slots}) == len(slots), f"bank {key}: sample names collide")
        return SoundBank(key, filename, outer_index, external.table_index, external.size, count, stride,
                         abnk_size, wbnk_capacity, ids, tuple(slots), tuple(layouts), payloads, external)

    def payloads_for(self, bank_key: str, patterns, subbanks=None) -> list[Payload]:
        bank = self.bank(bank_key)
        slots = bank.select_slots(patterns)
        chosen = list(range(bank.subbank_count)) if not subbanks else sorted(set(subbanks))
        for index in chosen:
            _require(0 <= index < bank.subbank_count,
                     f"{bank.key} has {bank.subbank_count} sub-banks; --subbank {index} is out of range")
        return [bank.payload(slot.index, index) for slot in slots for index in chosen]

    def read_payload(self, payload: Payload) -> bytes:
        data = self.read_spans(payload.spans)
        _require(len(data) == payload.size, "payload read was short")
        return data


# --------------------------------------------------------------------------- codec / pcm
def decode_payload(payload: bytes, channels: int) -> bytes:
    """Xbox IMA -> interleaved PCM16, vectorised when the studio decoder is importable."""

    try:
        root = TOOLS.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from mod_editor.core.nfl2k5_audio_source_scan import decode_xbox_ima_batch
    except Exception:  # noqa: BLE001 - the scalar decoder is the reference path anyway
        return ima.decode_stream(payload, channels)
    return decode_xbox_ima_batch(payload, channels)


def write_wav(path: Path, pcm: bytes, channels: int, sample_rate: int) -> None:
    block_align = channels * 2
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1,
                         channels, sample_rate, sample_rate * block_align, block_align, 16,
                         b"data", len(pcm))
    Path(path).write_bytes(header + pcm)


def read_wav(path: Path) -> tuple[int, int, bytes]:
    """Return (channels, sample_rate, pcm16 bytes); walks chunks so LIST/fact are tolerated."""

    data = Path(path).read_bytes()
    _require(len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE", f"not a RIFF WAVE: {path}")
    offset = 12
    fmt: tuple[int, ...] | None = None
    pcm: bytes | None = None
    while offset + 8 <= len(data):
        chunk_id, size = struct.unpack_from("<4sI", data, offset)
        body = data[offset + 8:offset + 8 + size]
        if chunk_id == b"fmt ":
            _require(size >= 16, "fmt chunk too short")
            fmt = struct.unpack_from("<HHIIHH", body, 0)
        elif chunk_id == b"data":
            pcm = body
        offset += 8 + size + (size & 1)
    _require(fmt is not None and pcm is not None, f"WAV lacks fmt/data: {path}")
    tag, channels, rate, _byte_rate, block_align, bits = fmt
    _require(tag == 1 and bits == 16 and block_align == channels * 2,
             f"WAV must be integer PCM16 (tag 1, 16-bit): {path}")
    _require(channels in (1, 2), "WAV must be mono or stereo")
    _require(len(pcm) % block_align == 0, "WAV data is not whole frames")
    _require(len(pcm) > 0, "WAV is empty")
    return channels, rate, pcm


def _samples(pcm: bytes) -> tuple[int, ...]:
    return struct.unpack(f"<{len(pcm) // 2}h", pcm)


def _pack(samples) -> bytes:
    return struct.pack(f"<{len(samples)}h", *[max(-32_768, min(32_767, int(round(v)))) for v in samples])


def remix_channels(pcm: bytes, channels: int, wanted: int) -> bytes:
    """Mono <-> stereo: duplicate, or average the pair."""

    if channels == wanted:
        return pcm
    samples = _samples(pcm)
    if channels == 1 and wanted == 2:
        out = [value for value in samples for _ in range(2)]
    elif channels == 2 and wanted == 1:
        out = [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)]
    else:
        raise SoundbankSwapError(f"cannot remix {channels} -> {wanted} channels")
    return _pack(out)


def resample_pcm(pcm: bytes, channels: int, source_rate: int, target_rate: int) -> bytes:
    """Linear-interpolation resample (with a 2-tap box pre-average when going down).

    Good enough for sound effects and the two 20 kHz/16 kHz whistle slots; a
    studio path that needs better should ``conform`` through ffmpeg first.
    """

    if source_rate == target_rate:
        return pcm
    _require(source_rate > 0 and target_rate > 0, "resample rates must be positive")
    samples = _samples(pcm)
    frames = len(samples) // channels
    out_frames = max(1, int(round(frames * target_rate / source_rate)))
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None:
        data = np.asarray(samples, dtype=np.float64).reshape(frames, channels)
        if target_rate < source_rate and frames > 1:
            data = np.concatenate([data[:1], (data[1:] + data[:-1]) / 2.0], axis=0)
        positions = np.arange(out_frames) * (source_rate / target_rate)
        base = np.minimum(np.floor(positions).astype(np.int64), frames - 1)
        nxt = np.minimum(base + 1, frames - 1)
        frac = (positions - base)[:, None]
        mixed = data[base] * (1 - frac) + data[nxt] * frac
        return _pack(np.rint(mixed).astype(np.int64).reshape(-1).tolist())
    out: list[int] = []
    step = source_rate / target_rate
    for index in range(out_frames):
        position = index * step
        base = min(int(position), frames - 1)
        nxt = min(base + 1, frames - 1)
        frac = position - base
        for channel in range(channels):
            a = samples[base * channels + channel]
            b = samples[nxt * channels + channel]
            out.append(int(round(a * (1 - frac) + b * frac)))
    return _pack(out)


@dataclass(frozen=True)
class Fit:
    pcm: bytes
    source_frames: int
    padded_frames: int
    trimmed_frames: int
    fade_frames: int


def fit_pcm(pcm: bytes, channels: int, frame_count: int, *, allow_trim: bool = True,
            fade_ms: float = 10.0, sample_rate: int = 0) -> Fit:
    """Pad with digital silence or trim (with a linear fade-out) to ``frame_count`` frames."""

    frame_bytes = channels * 2
    _require(len(pcm) % frame_bytes == 0, "PCM is not whole frames")
    source_frames = len(pcm) // frame_bytes
    _require(source_frames > 0, "clip is empty")
    _require(frame_count > 0 and frame_count % BLOCK_FRAMES == 0, "allocation is not whole blocks")
    if source_frames <= frame_count:
        return Fit(pcm + bytes((frame_count - source_frames) * frame_bytes), source_frames,
                   frame_count - source_frames, 0, 0)
    _require(allow_trim, f"clip is {source_frames} frames; the slot holds {frame_count} -- "
                         "trim it first or allow trimming")
    kept = bytearray(pcm[:frame_count * frame_bytes])
    fade_frames = 0
    if fade_ms > 0 and sample_rate > 0:
        fade_frames = min(frame_count, int(round(sample_rate * fade_ms / 1000.0)))
        if fade_frames > 1:
            start = frame_count - fade_frames
            for frame in range(start, frame_count):
                gain = (frame_count - 1 - frame) / fade_frames
                for channel in range(channels):
                    at = (frame * channels + channel) * 2
                    value = struct.unpack_from("<h", kept, at)[0]
                    struct.pack_into("<h", kept, at, int(round(value * gain)))
    return Fit(bytes(kept), source_frames, 0, source_frames - frame_count, fade_frames)


def snr_db(reference: bytes, decoded: bytes) -> float:
    count = min(len(reference), len(decoded)) // 2
    ref = struct.unpack(f"<{count}h", reference[:count * 2])
    out = struct.unpack(f"<{count}h", decoded[:count * 2])
    signal = sum(value * value for value in ref)
    noise = sum((a - b) * (a - b) for a, b in zip(ref, out))
    if noise == 0:
        return math.inf
    if signal == 0:
        return -math.inf
    return 10 * math.log10(signal / noise)


class ClipEncoder:
    """Shapes one WAV to every payload it must fill; caches per (rate, channels, frames)."""

    def __init__(self, channels: int, sample_rate: int, pcm: bytes, *, allow_trim: bool = True,
                 fade_ms: float = 10.0, strict: bool = False) -> None:
        self.channels = channels
        self.sample_rate = sample_rate
        self.pcm = pcm
        self.allow_trim = allow_trim
        self.fade_ms = fade_ms
        self.strict = strict
        self._shaped: dict[tuple[int, int], bytes] = {}
        self._encoded: dict[tuple[int, int, int], tuple[bytes, Fit, bytes]] = {}

    def shaped(self, channels: int, sample_rate: int) -> bytes:
        key = (channels, sample_rate)
        if key not in self._shaped:
            _require(not self.strict or (channels, sample_rate) == (self.channels, self.sample_rate),
                     f"WAV is {self.channels} ch / {self.sample_rate} Hz but the payload needs "
                     f"{channels} ch / {sample_rate} Hz (strict mode)")
            pcm = remix_channels(self.pcm, self.channels, channels)
            self._shaped[key] = resample_pcm(pcm, channels, self.sample_rate, sample_rate)
        return self._shaped[key]

    def encode(self, payload: Payload) -> tuple[bytes, Fit, bytes]:
        """(encoded bytes == payload.size, fit info, decoded PCM of the encode)."""

        key = (payload.channels, payload.sample_rate, payload.frame_count)
        if key not in self._encoded:
            pcm = self.shaped(payload.channels, payload.sample_rate)
            fit = fit_pcm(pcm, payload.channels, payload.frame_count, allow_trim=self.allow_trim,
                          fade_ms=self.fade_ms, sample_rate=payload.sample_rate)
            encoded = ima.encode_stream(fit.pcm, payload.channels)
            _require(len(encoded) == payload.size, "encoded payload does not equal the allocation")
            self._encoded[key] = (encoded, fit, decode_payload(encoded, payload.channels))
        return self._encoded[key]

    def conversions(self, payload: Payload) -> dict[str, object]:
        return {
            "resampled": payload.sample_rate != self.sample_rate,
            "remixed": payload.channels != self.channels,
            "wav_channels": self.channels,
            "wav_sample_rate": self.sample_rate,
        }


# --------------------------------------------------------------------------- retail gate
def retail_bytes_from_packs(retail_packs: Path, spans: tuple[DiscSpan, ...]) -> bytes:
    """Read the exact span from the extracted retail pack files (read-only)."""

    parts: list[bytes] = []
    for span in spans:
        pack = retail_packs / span.pack_name
        if not pack.is_file():
            pack = retail_packs / span.pack_name.lower()
        _require(pack.is_file(), f"retail pack {span.pack_name} not found under {retail_packs}")
        with open(pack, "rb") as handle:
            handle.seek(span.pack_offset)
            chunk = handle.read(span.length)
        _require(len(chunk) == span.length, f"short read from retail pack {pack}")
        parts.append(chunk)
    return b"".join(parts)


def refuse_retail_identity(target: Path, guards) -> None:
    info = target.stat()
    for guard in guards or []:
        guard = Path(guard)
        if guard.exists():
            other = guard.stat()
            _require((info.st_dev, info.st_ino) != (other.st_dev, other.st_ino),
                     f"refusing to write the guarded retail image {guard}")
    _require("for codex 1.0" not in str(target.resolve()),
             "refusing to write inside the retail source folder")


# --------------------------------------------------------------------------- operations
def replace_samples(disc_path: Path, bank_key: str, patterns, wav_path: Path, *,
                    subbanks=None, retail_packs: Path | None, force: bool = False,
                    guards=None, allow_trim: bool = True, fade_ms: float = 10.0,
                    strict: bool = False, banks=PINNED_BANKS) -> dict[str, object]:
    """Encode ``wav_path`` into every selected payload and write them in place; returns a receipt."""

    disc_path = Path(disc_path)
    refuse_retail_identity(disc_path, guards)
    channels, rate, pcm = read_wav(wav_path)
    encoder = ClipEncoder(channels, rate, pcm, allow_trim=allow_trim, fade_ms=fade_ms, strict=strict)
    with SoundBanks(disc_path, writable=True, banks=banks) as disc:
        bank = disc.bank(bank_key)
        payloads = disc.payloads_for(bank.key, patterns, subbanks)
        _require(bool(payloads), "nothing selected")
        _require(retail_packs is not None or force,
                 "give --retail-packs DIR so every span is verified before it is overwritten (or --force)")

        # Pass 1: gate every span and prepare every encode before anything is written.
        prepared: list[tuple[Payload, bytes, bytes, str, str]] = []
        for payload in payloads:
            before = disc.read_payload(payload)
            before_sha = sha256_bytes(before)
            gate = "forced"
            if retail_packs is not None:
                retail = retail_bytes_from_packs(Path(retail_packs), payload.spans)
                _require(retail == before or force,
                         f"{payload.payload_id} on this disc no longer carries the retail bytes "
                         f"(disc {before_sha[:16]}..., retail {sha256_bytes(retail)[:16]}...); "
                         "pass --force to overwrite anyway")
                gate = "retail-packs" if retail == before else "forced"
            encoded, _fit, _decoded = encoder.encode(payload)
            prepared.append((payload, before, encoded, before_sha, gate))

        # Pass 2: write, read back, receipt.
        rows: list[dict[str, object]] = []
        for payload, before, encoded, before_sha, gate in prepared:
            disc.write_spans(payload.spans, encoded)
            after = disc.read_payload(payload)
            _require(after == encoded, f"{payload.payload_id}: read-back after write does not match")
            _encoded, fit, decoded = encoder.encode(payload)
            reference = encoder.shaped(payload.channels, payload.sample_rate)
            rows.append({
                **payload.describe(),
                "retail_gate": gate,
                "before_sha256": before_sha,
                "after_sha256": sha256_bytes(after),
                "decoded_pcm_sha256": sha256_bytes(decoded),
                "changed": before != after,
                "clip_frames": fit.source_frames,
                "padded_silence_frames": fit.padded_frames,
                "trimmed_frames": fit.trimmed_frames,
                "fade_out_frames": fit.fade_frames,
                "encode_snr_db": round(snr_db(reference[:len(fit.pcm)], decoded[:len(fit.pcm)]), 2),
                **encoder.conversions(payload),
            })
        disc.fsync()
        receipt = {
            "schema": "nfl2k5_soundbank_swap_receipt/v1",
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "xiso": str(disc_path),
            "xiso_size": disc.image_size,
            "bank": bank.describe(),
            "samples": sorted({payload.name for payload in payloads}),
            "subbanks": sorted({payload.subbank for payload in payloads}),
            "wav": str(Path(wav_path)),
            "wav_sha256": sha256_bytes(Path(wav_path).read_bytes()),
            "wav_channels": channels,
            "wav_sample_rate": rate,
            "wav_frames": len(pcm) // (channels * 2),
            "allow_trim": allow_trim,
            "fade_ms": fade_ms,
            "descriptors_changed": False,
            "payload_count": len(rows),
            "payloads": rows,
        }
    return receipt


def verify_samples(disc_path: Path, bank_key: str, patterns, wav_path: Path, *, subbanks=None,
                   decoded_dir: Path | None = None, allow_trim: bool = True, fade_ms: float = 10.0,
                   banks=PINNED_BANKS) -> dict[str, object]:
    channels, rate, pcm = read_wav(wav_path)
    encoder = ClipEncoder(channels, rate, pcm, allow_trim=allow_trim, fade_ms=fade_ms)
    rows: list[dict[str, object]] = []
    with SoundBanks(disc_path, banks=banks) as disc:
        bank = disc.bank(bank_key)
        for payload in disc.payloads_for(bank.key, patterns, subbanks):
            expected, fit, _decoded = encoder.encode(payload)
            actual = disc.read_payload(payload)
            decoded = decode_payload(actual, payload.channels)
            reference = encoder.shaped(payload.channels, payload.sample_rate)
            if decoded_dir is not None:
                Path(decoded_dir).mkdir(parents=True, exist_ok=True)
                write_wav(Path(decoded_dir) / f"{bank.key}_{payload.name}_sb{payload.subbank:02d}.wav",
                          decoded, payload.channels, payload.sample_rate)
            rows.append({
                **payload.describe(),
                "matches_encoded_clip": actual == expected,
                "disc_payload_sha256": sha256_bytes(actual),
                "expected_payload_sha256": sha256_bytes(expected),
                "clip_frames": fit.source_frames,
                "decoded_snr_db_vs_clip": round(snr_db(reference[:len(fit.pcm)], decoded[:len(fit.pcm)]), 2),
            })
    return {"bank": bank_key, "all_match": all(row["matches_encoded_clip"] for row in rows),
            "payload_count": len(rows), "payloads": rows}


def export_samples(disc: SoundBanks, payloads, out_dir: Path) -> list[dict[str, object]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for payload in payloads:
        raw = disc.read_payload(payload)
        pcm = decode_payload(raw, payload.channels)
        name = f"{payload.bank}_{payload.name}_sb{payload.subbank:02d}.wav"
        write_wav(out_dir / name, pcm, payload.channels, payload.sample_rate)
        rows.append({"file": name, "payload_sha256": sha256_bytes(raw), **payload.describe()})
    (out_dir / "manifest.json").write_text(json.dumps(rows, indent=2), newline="\n")
    return rows


def slot_table(disc: SoundBanks, bank: SoundBank) -> list[dict[str, object]]:
    """Per-slot summary including how many distinct recordings the sub-banks hold."""

    hashes: dict[int, set[str]] = {slot.index: set() for slot in bank.slots}
    for subbank in range(bank.subbank_count):
        base = subbank * bank.stride
        layout = bank.subbanks[subbank]
        head = WRAPPER_SIZE + layout.abnk_body_size + WRAPPER_SIZE
        data = disc.read_entry_range(bank.entry, base + head, layout.wbnk_body_size)
        for slot in bank.slots:
            payload = bank.payload(slot.index, subbank)
            hashes[slot.index].add(sha256_bytes(data[payload.data_offset:payload.data_offset + payload.size]))
    rows: list[dict[str, object]] = []
    for slot in bank.slots:
        payloads = [bank.payload(slot.index, index) for index in range(bank.subbank_count)]
        rows.append({
            "slot": slot.index,
            "name": slot.name,
            "named": slot.named,
            "sample_id": f"0x{slot.sample_id:08x}",
            "channels": slot.channels,
            "sample_rates": list(slot.sample_rates),
            "subbanks": bank.subbank_count,
            "bytes_min": slot.min_bytes,
            "bytes_max": slot.max_bytes,
            "seconds_min": round(min(p.duration for p in payloads), 3),
            "seconds_max": round(max(p.duration for p in payloads), 3),
            "distinct_payloads": len(hashes[slot.index]),
            "total_bytes": sum(p.size for p in payloads),
        })
    return rows


# --------------------------------------------------------------------------- synth / conform
def synth_pcm(kind: str, sample_rate: int, channels: int, seconds: float, *, hz: float = 440.0,
              hz2: float = 660.0, amplitude: float = 0.6, fade_ms: float = 30.0) -> bytes:
    """Obviously-artificial test material: a faded tone, or an alternating two-tone beep."""

    frames = max(BLOCK_FRAMES, int(round(sample_rate * seconds)))
    fade = max(1, int(sample_rate * fade_ms / 1000.0))
    out: list[int] = []
    for frame in range(frames):
        t = frame / sample_rate
        if kind == "tone":
            value = math.sin(2 * math.pi * hz * t)
            envelope = min(1.0, frame / fade, (frames - frame) / fade)
        elif kind == "beep2":
            period = 0.12
            phase = (t % (2 * period)) / period
            freq = hz if phase < 1.0 else hz2
            local = (t % period) * sample_rate
            envelope = min(1.0, local / fade, (period * sample_rate - local) / fade)
            envelope *= min(1.0, (frames - frame) / fade)
            value = math.sin(2 * math.pi * freq * t)
        else:
            raise SoundbankSwapError(f"unknown synth kind {kind!r}")
        sample = int(round(amplitude * envelope * value * 32767))
        out.extend([sample] * channels)
    return _pack(out)


def conform_clip(input_path: Path, out_path: Path, *, channels: int, sample_rate: int,
                 max_seconds: float, start: float = 0.0, duration: float | None = None,
                 gain_db: float = 0.0, fade_ms: int = 15, ffmpeg: str = "ffmpeg") -> dict[str, object]:
    """Cut / downmix / resample any audio file into a slot-shaped PCM16 WAV via ffmpeg."""

    length = max_seconds if duration is None else min(duration, max_seconds)
    _require(length > 0, "nothing to cut")
    filters: list[str] = []
    if gain_db:
        filters.append(f"volume={gain_db}dB")
    if fade_ms > 0:
        fade = fade_ms / 1000
        filters.append(f"afade=t=in:st=0:d={fade}")
        filters.append(f"afade=t=out:st={max(0.0, length - fade)}:d={fade}")
    command = [ffmpeg, "-y", "-v", "error", "-ss", f"{start}", "-t", f"{length}", "-i", str(input_path),
               "-ac", str(channels), "-ar", str(sample_rate), "-sample_fmt", "s16"]
    if filters:
        command += ["-af", ",".join(filters)]
    command += ["-f", "wav", str(out_path)]
    subprocess.run(command, check=True)
    got_channels, got_rate, pcm = read_wav(out_path)
    _require(got_channels == channels and got_rate == sample_rate, "ffmpeg did not produce the requested shape")
    frames = len(pcm) // (channels * 2)
    return {"out": str(out_path), "frames": frames, "seconds": round(frames / sample_rate, 6),
            "channels": channels, "sample_rate": sample_rate, "ffmpeg": command}


# --------------------------------------------------------------------------- CLI
def _banks(args: argparse.Namespace) -> tuple[tuple[str, int, str], ...]:
    fixture = getattr(args, "banks_fixture", None)
    if not fixture:
        return PINNED_BANKS
    return tuple((str(key), int(outer), str(name)) for key, outer, name in json.loads(fixture))


def _cmd_list(args: argparse.Namespace) -> int:
    with SoundBanks(Path(args.xiso), banks=_banks(args)) as disc:
        if args.bank is None:
            rows = [bank.describe() for bank in disc.banks.values()]
            if args.json:
                print(json.dumps(rows, indent=2))
                return 0
            print(f"{'bank':12s} {'file':16s} {'desc':>5s} {'ext':>5s} {'subbanks':>8s} {'stride':>10s} "
                  f"{'slots':>5s} {'bytes':>12s}  role")
            for bank in disc.banks.values():
                print(f"{bank.key:12s} {bank.external_filename:16s} {bank.descriptor_outer_index:5d} "
                      f"{bank.external_outer_index:5d} {bank.subbank_count:8d} {bank.stride:10,d} "
                      f"{len(bank.slots):5d} {bank.external_size:12,d}  {BANK_ROLES.get(bank.key, '')}")
            return 0
        bank = disc.bank(args.bank)
        rows = slot_table(disc, bank)
        if args.sample:
            wanted = {slot.index for slot in bank.select_slots(args.sample)}
            rows = [row for row in rows if row["slot"] in wanted]
        if args.json:
            print(json.dumps({"bank": bank.describe(), "slots": rows}, indent=2))
            return 0
        print(f"{bank.key}: {bank.subbank_count} sub-banks x {bank.stride:,} bytes, {len(bank.slots)} slots "
              f"({BANK_ROLES.get(bank.key, '')})")
        print(f"{'slot':>4s} {'name':26s} {'ch':>2s} {'rate':>12s} {'bytes':>15s} {'seconds':>15s} {'distinct':>8s}")
        for row in rows:
            rates = "/".join(str(rate) for rate in row["sample_rates"])
            print(f"{row['slot']:4d} {row['name']:26s} {row['channels']:2d} {rates:>12s} "
                  f"{row['bytes_min']:7d}..{row['bytes_max']:<7d} {row['seconds_min']:7.3f}..{row['seconds_max']:<7.3f} "
                  f"{row['distinct_payloads']:5d}/{row['subbanks']}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    with SoundBanks(Path(args.xiso), banks=_banks(args)) as disc:
        bank = disc.bank(args.bank)
        patterns = args.sample or ["*"]
        payloads = disc.payloads_for(bank.key, patterns, args.subbank)
        rows = export_samples(disc, payloads, Path(args.out))
    print(f"exported {len(rows)} payload(s) to {args.out}")
    return 0


def _cmd_replace(args: argparse.Namespace) -> int:
    receipt = replace_samples(Path(args.xiso), args.bank, args.sample, Path(args.wav),
                              subbanks=args.subbank,
                              retail_packs=Path(args.retail_packs) if args.retail_packs else None,
                              force=args.force, guards=args.guard, allow_trim=not args.no_trim,
                              fade_ms=args.fade_ms, strict=args.strict, banks=_banks(args))
    text = json.dumps(receipt, indent=2)
    if args.receipt:
        Path(args.receipt).write_text(text, newline="\n")
    if args.quiet:
        print(f"wrote {receipt['payload_count']} payload(s): {', '.join(receipt['samples'])} "
              f"in {receipt['bank']['bank']} sub-banks {receipt['subbanks']}")
    else:
        print(text)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify_samples(Path(args.xiso), args.bank, args.sample, Path(args.wav), subbanks=args.subbank,
                            decoded_dir=Path(args.decoded_dir) if args.decoded_dir else None,
                            allow_trim=not args.no_trim, fade_ms=args.fade_ms, banks=_banks(args))
    print(json.dumps(result, indent=2))
    return 0 if result["all_match"] else 1


def _cmd_conform(args: argparse.Namespace) -> int:
    with SoundBanks(Path(args.xiso), banks=_banks(args)) as disc:
        bank = disc.bank(args.bank)
        payloads = disc.payloads_for(bank.key, args.sample, args.subbank)
    channels = payloads[0].channels
    rates = {payload.sample_rate for payload in payloads}
    sample_rate = max(rates)
    info = conform_clip(Path(args.input), Path(args.out), channels=channels, sample_rate=sample_rate,
                        max_seconds=max(payload.duration for payload in payloads), start=args.start,
                        duration=args.duration, gain_db=args.gain_db, fade_ms=args.fade_ms)
    info["slot_seconds_min"] = round(min(payload.duration for payload in payloads), 6)
    info["slot_seconds_max"] = round(max(payload.duration for payload in payloads), 6)
    info["slot_sample_rates"] = sorted(rates)
    print(json.dumps(info, indent=2))
    return 0


def _cmd_synth(args: argparse.Namespace) -> int:
    pcm = synth_pcm(args.kind, args.rate, args.channels, args.seconds, hz=args.hz, hz2=args.hz2,
                    amplitude=args.amplitude)
    write_wav(Path(args.out), pcm, args.channels, args.rate)
    print(f"wrote {args.out}: {args.kind} {args.rate} Hz x{args.channels} {args.seconds}s")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, *, need_sample: bool) -> None:
        p.add_argument("xiso")
        p.add_argument("--bank", required=need_sample, help="sfx_game | sfx_safe | QB_at_line")
        p.add_argument("--sample", action="append", required=need_sample,
                       help="sample name, glob ('snap-hut-num1_*') or slotN (repeatable)")
        p.add_argument("--subbank", action="append", type=int,
                       help="only this sub-bank (repeatable); default = every sub-bank")
        p.add_argument("--banks-fixture", help=argparse.SUPPRESS)   # tests: JSON [[key, outer, file], ...]

    p = sub.add_parser("list", help="list banks, or the slots of one bank")
    common(p, need_sample=False)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("export", help="decode payloads to PCM16 WAV")
    common(p, need_sample=False)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_export)

    p = sub.add_parser("conform", help="cut/resample any audio to a sample's shape with ffmpeg")
    common(p, need_sample=True)
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--duration", type=float)
    p.add_argument("--gain-db", type=float, default=0.0)
    p.add_argument("--fade-ms", type=int, default=15)
    p.set_defaults(func=_cmd_conform)

    p = sub.add_parser("synth", help="write an obviously artificial test WAV")
    p.add_argument("--out", required=True)
    p.add_argument("--rate", type=int, required=True)
    p.add_argument("--channels", type=int, default=1)
    p.add_argument("--seconds", type=float, default=1.0)
    p.add_argument("--kind", choices=("tone", "beep2"), default="tone")
    p.add_argument("--hz", type=float, default=440.0)
    p.add_argument("--hz2", type=float, default=660.0)
    p.add_argument("--amplitude", type=float, default=0.6)
    p.set_defaults(func=_cmd_synth)

    p = sub.add_parser("replace", help="write one WAV into the selected payloads IN PLACE (use a copy!)")
    common(p, need_sample=True)
    p.add_argument("--wav", required=True)
    p.add_argument("--retail-packs", help="extracted retail vc_53450030 folder used to verify every span first")
    p.add_argument("--force", action="store_true")
    p.add_argument("--guard", action="append", help="path(s) that must never be written (retail image)")
    p.add_argument("--no-trim", action="store_true", help="refuse clips longer than an allocation")
    p.add_argument("--fade-ms", type=float, default=10.0, help="fade-out applied when a clip is trimmed")
    p.add_argument("--strict", action="store_true", help="refuse rate/channel conversions")
    p.add_argument("--receipt", help="write the JSON receipt here too")
    p.add_argument("--quiet", action="store_true", help="print a one-line summary instead of the receipt")
    p.set_defaults(func=_cmd_replace)

    p = sub.add_parser("verify", help="check payloads hold exactly the encoded WAV")
    common(p, need_sample=True)
    p.add_argument("--wav", required=True)
    p.add_argument("--decoded-dir", help="also write what the game will play, decoded from the disc")
    p.add_argument("--no-trim", action="store_true")
    p.add_argument("--fade-ms", type=float, default=10.0)
    p.set_defaults(func=_cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except SoundbankSwapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ima.XboxImaEncodeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
