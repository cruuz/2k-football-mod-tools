#!/usr/bin/env python3
"""Swap one NFL 2K5 commentary / speech line inside a COPIED disc image.

NFL 2K5's speech does not live in loose files.  Seventeen tiny ``AUSB``
descriptors (all inside the outer archive ``vc_53450030``) each name one
external streaming bank (``lines.bin``, ``players.bin``, ``teams.bin``,
``cutsceneaudio.bin`` ...) that is itself an outer-archive entry striped across
the ``vc_53450030/0..F`` packs.  A descriptor is::

    +0x00  0x20-byte resource wrapper ("AUSB", stored_size, 0...)
    +0x2C  "AUSB" inner marker            (body +0x0C)
    +0x30  self-relative UTF-16LE name    (body +0x10 -> "lines")
    +0x60  UTF-16LE external filename     (body +0x40 -> "lines.bin")
    +0xA0  entry_count, unknown, channels, sample_rate(22050), unit(0x12000)
    +0xB8  boundaries[entry_count + 1]    (byte offsets into the external bank)

Every sub-stream ``i`` is the external-bank bytes ``boundaries[i] ..
boundaries[i+1]``: Xbox IMA ADPCM, 36 bytes per channel per 64-frame block,
22,050 Hz.  Because the table stores absolute offsets, a replacement that keeps
the sub-stream's byte length identical needs no other change on the disc.

Sub-command overview (all read-only except ``replace``)::

    list      XISO [--bank lines] [--start 0] [--count 50]
    export    XISO --out DIR (--stream lines:12 ... | --bank X --start --count)
    conform   XISO --stream ID --input ANY_AUDIO --out clip.wav [--start S]
    replace   XISO --stream ID --wav clip.wav --retail-packs DIR [--receipt R.json]
    verify    XISO --stream ID --wav clip.wav [--decoded-wav out.wav]
    transcribe DIR --model VOSK_MODEL_DIR [--out transcripts.json]

``replace`` writes IN PLACE: point it at a copy, never at the retail image.  It
re-reads the exact retail bytes of the span from the extracted retail packs
(``--retail-packs``) and refuses to write unless the disc still carries them.

The codec is the repository's reviewed ``tools/xbox_ima_encoder.py``; the
XDVDFS walk is ``tools/nfl_uniform_color_xiso_direct_patch.parse_xdvdfs`` and
the outer-archive model is ``tools/nfl_outer``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
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
SAMPLE_RATE = 22_050
UNIT_WORD = 0x12000
WRAPPER_SIZE = 0x20
BLOCK_FRAMES = ima.BLOCK_FRAMES
CHANNEL_BLOCK_BYTES = ima.CHANNEL_BLOCK_BYTES

# The 17 AUSB descriptors of the retail disc, pinned by (outer entry, chunk
# offset inside that entry, stored body size, bank name).  They are verified at
# open time (wrapper magic, name, external-bank ownership, table extent), so a
# disc whose descriptors moved fails closed instead of reading garbage.
PINNED_DESCRIPTORS: tuple[tuple[int, int, int, int, str], ...] = (
    (3, 211, 2106416, 121248, "lines"),
    (3, 213, 2273152, 89840, "players"),
    (3, 215, 2382736, 1168, "teams"),
    (3, 217, 2384368, 192, "femusic"),
    (3, 218, 2384592, 176, "loadm"),
    (3, 219, 2384800, 176, "drafta"),
    (3, 220, 2385008, 208, "coacha"),
    (3, 221, 2385248, 1280, "cutsceneaudio"),
    (3, 222, 2386560, 400, "cribmusic"),
    (3, 223, 2386992, 400, "crib22"),
    (15, 13, 215360, 176, "cwdloop"),
    (18, 14, 443776, 192, "wrapupm"),
    (346, 134, 2975376, 176, "cwdloop"),
    (346, 135, 2975584, 176, "cwdsurr"),
    (346, 136, 2975792, 224, "overlayaudio"),
    (346, 137, 2976048, 192, "halftimeaudio"),
    (346, 138, 2976272, 880, "animationaudio"),
)

BANK_ROLES = {
    "lines": "play-by-play / colour / studio phrases (Stevens, O'Keefe, Berman)",
    "players": "player-name inserts",
    "teams": "team-name inserts",
    "cutsceneaudio": "pregame / halftime / postgame studio cutscene speech",
    "halftimeaudio": "halftime show beds",
    "overlayaudio": "overlay stingers",
    "animationaudio": "animation-synced audio",
    "coacha": "coach / PA",
    "drafta": "draft presentation",
    "femusic": "frontend music",
    "loadm": "loading music",
    "cribmusic": "crib music (stereo)",
    "crib22": "crib music (mono)",
    "cwdloop": "crowd loop",
    "cwdsurr": "crowd surround",
    "wrapupm": "wrap-up show music",
}

O_BINARY = getattr(os, "O_BINARY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class CommentarySwapError(ValueError):
    """Anything that must stop the tool before it touches the disc."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CommentarySwapError(message)


# --------------------------------------------------------------------------- model
@dataclass(frozen=True)
class DiscSpan:
    """One contiguous byte range of the disc image."""

    xiso_offset: int
    length: int
    pack_name: str
    pack_offset: int


@dataclass(frozen=True)
class Bank:
    name: str
    descriptor_outer_index: int
    descriptor_chunk_index: int
    descriptor_xiso_offset: int
    external_filename: str
    external_outer_index: int
    external_size: int
    channels: int
    sample_rate: int
    unknown_word: int
    boundaries: tuple[int, ...]
    entry: Entry = field(repr=False, compare=False)

    @property
    def count(self) -> int:
        return len(self.boundaries) - 1

    @property
    def block_align(self) -> int:
        return CHANNEL_BLOCK_BYTES * self.channels


@dataclass(frozen=True)
class Stream:
    bank: Bank
    index: int
    start: int
    end: int
    spans: tuple[DiscSpan, ...]

    @property
    def stream_id(self) -> str:
        return f"{self.bank.name}:{self.index}"

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def channels(self) -> int:
        return self.bank.channels

    @property
    def sample_rate(self) -> int:
        return self.bank.sample_rate

    @property
    def block_count(self) -> int:
        return self.size // self.bank.block_align

    @property
    def frame_count(self) -> int:
        return self.block_count * BLOCK_FRAMES

    @property
    def duration(self) -> float:
        return self.frame_count / self.sample_rate

    @property
    def contiguous(self) -> bool:
        return len(self.spans) == 1

    def describe(self) -> dict[str, object]:
        return {
            "stream": self.stream_id,
            "bank": self.bank.name,
            "index": self.index,
            "bank_offset_start": self.start,
            "bank_offset_end": self.end,
            "bytes": self.size,
            "blocks": self.block_count,
            "frames": self.frame_count,
            "channels": self.channels,
            "sample_rate": self.sample_rate,
            "duration_seconds": round(self.duration, 6),
            "xiso_spans": [
                {"xiso_offset": s.xiso_offset, "length": s.length,
                 "pack": s.pack_name, "pack_offset": s.pack_offset}
                for s in self.spans
            ],
        }


def parse_stream_id(text: str) -> tuple[str, int]:
    _require(":" in text, f"stream id must look like bank:index, got {text!r}")
    bank, _, number = text.rpartition(":")
    _require(bank != "" and number.isdigit(), f"stream id must look like bank:index, got {text!r}")
    return bank, int(number)


# --------------------------------------------------------------------------- disc
def _pread_exact(descriptor: int, offset: int, length: int) -> bytes:
    parts: list[bytes] = []
    done = 0
    while done < length:
        chunk = _pread(descriptor, length - done, offset + done)
        _require(bool(chunk), f"short read at 0x{offset + done:x}")
        parts.append(chunk)
        done += len(chunk)
    return b"".join(parts)


def _pwrite_exact(descriptor: int, data: bytes, offset: int) -> None:
    view = memoryview(data)
    done = 0
    while done < len(view):
        count = _pwrite(descriptor, view[done:], offset + done)
        _require(count > 0, f"short write at 0x{offset + done:x}")
        done += count


def _utf16z(data: bytes, offset: int, limit: int) -> str:
    end = offset
    while end + 1 < limit and data[end:end + 2] != b"\0\0":
        end += 2
    _require(end + 1 < limit, f"unterminated UTF-16 string at 0x{offset:x}")
    return data[offset:end].decode("utf-16le")


class DiscBanks:
    """Read-only (or in-place writable) view of the AUSB banks inside one XISO."""

    def __init__(self, path: Path, *, writable: bool = False,
                 descriptors: tuple[tuple[int, int, int, int, str], ...] = PINNED_DESCRIPTORS) -> None:
        self.path = Path(path)
        self.descriptors = tuple(tuple(item) for item in descriptors)
        _require(self.path.is_file(), f"not a file: {self.path}")
        _require(not self.path.is_symlink(), f"refusing a symlink: {self.path}")
        flags = (os.O_RDWR if writable else os.O_RDONLY) | O_BINARY | O_NOFOLLOW
        self.descriptor = os.open(self.path, flags)
        self.writable = writable
        self.image_size = os.fstat(self.descriptor).st_size
        try:
            entries, _info = xiso.parse_xdvdfs(self.descriptor, self.image_size)
            self.entries = entries
            self.pack_extents = self._pack_extents()
            self.archive_entries = self._parse_archive()
            self.banks = self._read_banks()
        except BaseException:
            # Parsing can fail after the directory walk (e.g. a bad second
            # descriptor). Windows must not retain that reader through replace.
            self.close()
            raise

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def __enter__(self) -> "DiscBanks":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- archive topology -------------------------------------------------------
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

    def read_spans(self, spans: tuple[DiscSpan, ...]) -> bytes:
        return b"".join(_pread_exact(self.descriptor, span.xiso_offset, span.length)
                        for span in spans)

    def read_entry_range(self, entry: Entry, relative_offset: int, size: int) -> bytes:
        return self.read_spans(self.entry_spans(entry, relative_offset, size))

    # -- banks ------------------------------------------------------------------
    def _read_banks(self) -> dict[str, Bank]:
        banks: dict[str, Bank] = {}
        for outer_index, chunk_index, chunk_offset, stored_size, expected_name in self.descriptors:
            _require(outer_index < len(self.archive_entries), f"archive lacks entry {outer_index}")
            entry = self.archive_entries[outer_index]
            spans = self.entry_spans(entry, chunk_offset, WRAPPER_SIZE + stored_size)
            raw = self.read_spans(spans)
            magic, declared = struct.unpack_from("<4sI", raw, 0)
            _require(magic == b"AUSB" and declared == stored_size,
                     f"outer {outer_index}+0x{chunk_offset:x}: not the pinned AUSB descriptor")
            body = raw[WRAPPER_SIZE:]
            _require(body[0x0C:0x10] == b"AUSB", "AUSB inner marker missing")
            name_offset = 0x0F + struct.unpack_from("<i", body, 0x10)[0]
            name = _utf16z(body, name_offset, len(body))
            _require(name == expected_name, f"descriptor names {name!r}, expected {expected_name!r}")
            external_filename = _utf16z(body, 0x40, 0x80)
            _require(external_filename.casefold() == f"{name}.bin",
                     f"bank {name} names external file {external_filename!r}")
            count, unknown, channels, rate, unit = struct.unpack_from("<5I", body, 0x80)
            _require(count > 0 and channels in (1, 2) and rate == SAMPLE_RATE and unit == UNIT_WORD,
                     f"bank {name}: unsupported descriptor words")
            _require(0x98 + (count + 1) * 4 <= len(body), f"bank {name}: truncated boundary table")
            boundaries = struct.unpack_from(f"<{count + 1}I", body, 0x98)
            external_id = zlib.crc32(external_filename.upper().encode("utf-16le")) & 0xFFFFFFFF
            matches = [candidate for candidate in self.archive_entries if candidate.name_id == external_id]
            _require(len(matches) == 1, f"bank {name}: external entry not unique")
            external = matches[0]
            align = CHANNEL_BLOCK_BYTES * channels
            _require(boundaries[0] == 0 and boundaries[-1] == external.size
                     and all(left < right and (right - left) % align == 0
                             for left, right in zip(boundaries, boundaries[1:])),
                     f"bank {name}: boundary table is not whole Xbox IMA blocks")
            bank = Bank(
                name=name,
                descriptor_outer_index=outer_index,
                descriptor_chunk_index=chunk_index,
                descriptor_xiso_offset=spans[0].xiso_offset,
                external_filename=external_filename,
                external_outer_index=external.table_index,
                external_size=external.size,
                channels=channels,
                sample_rate=rate,
                unknown_word=unknown,
                boundaries=boundaries,
                entry=external,
            )
            # cwdloop is described twice (outer 15 and outer 346) for one bank.
            if name in banks:
                _require(banks[name].boundaries == boundaries
                         and banks[name].external_outer_index == external.table_index,
                         f"bank {name}: duplicate descriptors disagree")
                continue
            banks[name] = bank
        return banks

    def stream(self, bank_name: str, index: int) -> Stream:
        bank = self.banks.get(bank_name)
        _require(bank is not None, f"unknown bank {bank_name!r}; known: {', '.join(sorted(self.banks))}")
        _require(0 <= index < bank.count, f"{bank_name} has {bank.count} streams; index {index} is out of range")
        start, end = bank.boundaries[index], bank.boundaries[index + 1]
        return Stream(bank, index, start, end, self.entry_spans(bank.entry, start, end - start))

    def stream_by_id(self, stream_id: str) -> Stream:
        return self.stream(*parse_stream_id(stream_id))

    def iter_streams(self, bank_name: str, start: int = 0, count: int | None = None):
        bank = self.banks.get(bank_name)
        _require(bank is not None, f"unknown bank {bank_name!r}")
        stop = bank.count if count is None else min(bank.count, start + count)
        for index in range(max(0, start), stop):
            yield self.stream(bank_name, index)

    def read_stream(self, stream: Stream) -> bytes:
        payload = self.read_spans(stream.spans)
        _require(len(payload) == stream.size, "stream read was short")
        return payload


# --------------------------------------------------------------------------- codec
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


def write_wav(path: Path, pcm: bytes, channels: int, sample_rate: int = SAMPLE_RATE) -> None:
    block_align = channels * 2
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1,
                         channels, sample_rate, sample_rate * block_align, block_align, 16,
                         b"data", len(pcm))
    path.write_bytes(header + pcm)


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
    _require(len(pcm) % block_align == 0, "WAV data is not whole frames")
    return channels, rate, pcm


def fit_pcm(pcm: bytes, channels: int, frame_count: int) -> tuple[bytes, int]:
    """Pad PCM16 with digital silence to exactly ``frame_count`` frames.

    Returns (padded_pcm, source_frames).  A clip longer than the allocation is
    refused: nothing here shortens audio silently, use ``conform``.
    """

    frame_bytes = channels * 2
    _require(len(pcm) % frame_bytes == 0, "PCM is not whole frames")
    source_frames = len(pcm) // frame_bytes
    _require(source_frames > 0, "clip is empty")
    _require(source_frames <= frame_count,
             f"clip is {source_frames} frames ({source_frames / SAMPLE_RATE:.3f}s); the slot "
             f"holds {frame_count} frames ({frame_count / SAMPLE_RATE:.3f}s) -- trim it first")
    return pcm + bytes((frame_count - source_frames) * frame_bytes), source_frames


def encode_for_stream(pcm: bytes, stream: Stream) -> tuple[bytes, int]:
    padded, source_frames = fit_pcm(pcm, stream.channels, stream.frame_count)
    encoded = ima.encode_stream(padded, stream.channels)
    _require(len(encoded) == stream.size, "encoded payload does not equal the allocation")
    return encoded, source_frames


def snr_db(reference: bytes, decoded: bytes) -> float:
    """Signal-to-noise of decoded vs reference PCM16, in dB (inf for identical)."""

    import math

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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- retail gate
def retail_bytes_from_packs(retail_packs: Path, stream: Stream) -> bytes:
    """Read the exact stream span from the extracted retail pack files (read-only)."""

    parts: list[bytes] = []
    for span in stream.spans:
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


def refuse_retail_identity(target: Path, guards: list[Path]) -> None:
    info = target.stat()
    for guard in guards:
        if guard.exists():
            other = guard.stat()
            _require((info.st_dev, info.st_ino) != (other.st_dev, other.st_ino),
                     f"refusing to write the guarded retail image {guard}")
    _require("for codex 1.0" not in str(target.resolve()),
             "refusing to write inside the retail source folder")


# --------------------------------------------------------------------------- operations
def replace_stream(
    disc_path: Path,
    stream_id: str,
    wav_path: Path,
    *,
    retail_packs: Path | None,
    expect_sha256: str | None = None,
    force: bool = False,
    guards: list[Path] | None = None,
    descriptors: tuple[tuple[int, int, int, int, str], ...] = PINNED_DESCRIPTORS,
) -> dict[str, object]:
    """Encode ``wav_path`` into the sub-stream and write it in place; returns a receipt."""

    disc_path = Path(disc_path)
    refuse_retail_identity(disc_path, guards or [])
    channels, rate, pcm = read_wav(wav_path)
    with DiscBanks(disc_path, writable=True, descriptors=descriptors) as disc:
        stream = disc.stream_by_id(stream_id)
        _require(channels == stream.channels,
                 f"WAV has {channels} channel(s); {stream.stream_id} needs {stream.channels}")
        _require(rate == stream.sample_rate,
                 f"WAV is {rate} Hz; {stream.stream_id} needs {stream.sample_rate} Hz")
        before = disc.read_stream(stream)
        before_sha = sha256_bytes(before)
        gate = "none"
        if retail_packs is not None:
            retail = retail_bytes_from_packs(Path(retail_packs), stream)
            _require(retail == before or force,
                     f"{stream.stream_id} on this disc no longer carries the retail bytes "
                     f"(disc {before_sha[:16]}..., retail {sha256_bytes(retail)[:16]}...); "
                     "pass --force to overwrite anyway")
            gate = "retail-packs" if retail == before else "forced"
        elif expect_sha256 is not None:
            _require(before_sha == expect_sha256 or force,
                     f"{stream.stream_id} current sha256 {before_sha} != expected {expect_sha256}")
            gate = "expect-sha256" if before_sha == expect_sha256 else "forced"
        else:
            _require(force, "give --retail-packs DIR or --expect-sha256 HEX (or --force) so the span is verified before it is overwritten")
            gate = "forced"

        encoded, source_frames = encode_for_stream(pcm, stream)
        decoded = decode_payload(encoded, stream.channels)
        cursor = 0
        for span in stream.spans:
            _pwrite_exact(disc.descriptor, encoded[cursor:cursor + span.length], span.xiso_offset)
            cursor += span.length
        os.fsync(disc.descriptor)
        after = disc.read_stream(stream)
        _require(after == encoded, "read-back after write does not match the encoded payload")
        receipt = {
            "schema": "nfl2k5_commentary_swap_receipt/v1",
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "xiso": str(disc_path),
            "xiso_size": disc.image_size,
            "retail_gate": gate,
            "wav": str(Path(wav_path)),
            "wav_sha256": sha256_bytes(Path(wav_path).read_bytes()),
            "clip_frames": source_frames,
            "clip_seconds": round(source_frames / stream.sample_rate, 6),
            "padded_silence_frames": stream.frame_count - source_frames,
            "before_sha256": before_sha,
            "after_sha256": sha256_bytes(after),
            "decoded_pcm_sha256": sha256_bytes(decoded),
            "encode_snr_db": round(snr_db(pcm, decoded[:len(pcm)]), 2),
            "descriptor_xiso_offset": stream.bank.descriptor_xiso_offset,
            "descriptor_changed": False,
            **stream.describe(),
        }
    return receipt


def verify_stream(disc_path: Path, stream_id: str, wav_path: Path,
                  decoded_wav: Path | None = None,
                  descriptors: tuple[tuple[int, int, int, int, str], ...] = PINNED_DESCRIPTORS,
                  ) -> dict[str, object]:
    channels, rate, pcm = read_wav(wav_path)
    with DiscBanks(disc_path, descriptors=descriptors) as disc:
        stream = disc.stream_by_id(stream_id)
        _require(channels == stream.channels and rate == stream.sample_rate,
                 "WAV shape does not match the stream")
        expected, source_frames = encode_for_stream(pcm, stream)
        actual = disc.read_stream(stream)
        decoded = decode_payload(actual, stream.channels)
        if decoded_wav is not None:
            write_wav(Path(decoded_wav), decoded, stream.channels, stream.sample_rate)
        return {
            "stream": stream.stream_id,
            "matches_encoded_clip": actual == expected,
            "disc_payload_sha256": sha256_bytes(actual),
            "expected_payload_sha256": sha256_bytes(expected),
            "decoded_pcm_sha256": sha256_bytes(decoded),
            "clip_frames": source_frames,
            "decoded_snr_db_vs_clip": round(snr_db(pcm, decoded[:len(pcm)]), 2),
            **stream.describe(),
        }


def export_streams(disc: DiscBanks, streams, out_dir: Path) -> list[dict[str, object]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for stream in streams:
        payload = disc.read_stream(stream)
        pcm = decode_payload(payload, stream.channels)
        name = f"{stream.bank.name}_{stream.index:05d}.wav"
        write_wav(out_dir / name, pcm, stream.channels, stream.sample_rate)
        rows.append({"file": name, "payload_sha256": sha256_bytes(payload), **stream.describe()})
    (out_dir / "manifest.json").write_text(json.dumps(rows, indent=2), newline="\n")
    return rows


RETAIL_SPEECH_RMS_DB = -14.3     # median of 800 retail lines/team inserts; p10..p90 span 0.6 dB
LIMITER_CEILING = 0.94           # about -0.5 dBFS; retail peaks touch 0 dBFS


def pcm_rms_db(pcm: bytes) -> float:
    import math

    count = len(pcm) // 2
    _require(count > 0, "PCM is empty")
    values = struct.unpack(f"<{count}h", pcm[:count * 2])
    mean_square = sum(value * value for value in values) / count / (32768.0 * 32768.0)
    return 10 * math.log10(mean_square) if mean_square > 0 else -120.0


def _ffmpeg_cut(ffmpeg: str, input_path: Path, out_path: Path, *, channels: int, start: float,
                length: float, filters: list[str]) -> list[str]:
    command = [ffmpeg, "-y", "-v", "error", "-ss", f"{start}", "-t", f"{length}", "-i", str(input_path),
               "-ac", str(channels), "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16"]
    if filters:
        command += ["-af", ",".join(filters)]
    command += ["-f", "wav", str(out_path)]
    subprocess.run(command, check=True)
    return command


def conform_clip(input_path: Path, out_path: Path, *, channels: int, max_seconds: float,
                 start: float = 0.0, duration: float | None = None, gain_db: float = 0.0,
                 loudnorm_lufs: float | None = None, target_rms_db: float | None = None,
                 fade_ms: int = 15, ffmpeg: str = "ffmpeg") -> dict[str, object]:
    """Cut / downmix / resample any audio file into a slot-shaped PCM16 WAV via ffmpeg.

    Retail speech is hard-normalised (RMS -14.3 dBFS, peaks at 0 dBFS); a home
    recording is usually 10-20 dB quieter with far more crest.  ``target_rms_db``
    measures the cut, applies the gain that lands its RMS on the target and tames
    the resulting peaks with a look-ahead limiter at -0.5 dBFS, then re-measures
    and corrects once so limiting losses do not leave it short.  ``loudnorm_lufs``
    is the gentler EBU R128 alternative (peak-bound, so it cannot reach retail
    level on an uncompressed voice).
    """

    length = max_seconds if duration is None else min(duration, max_seconds)
    _require(length > 0, "nothing to cut")
    fades: list[str] = []
    if fade_ms > 0:
        fade = fade_ms / 1000
        fades.append(f"afade=t=in:st=0:d={fade}")
        fades.append(f"afade=t=out:st={max(0.0, length - fade)}:d={fade}")
    limiter = f"alimiter=limit={LIMITER_CEILING}:attack=3:release=40:level=false"

    applied_gain = gain_db
    measured: dict[str, float] = {}
    if target_rms_db is not None:
        _ffmpeg_cut(ffmpeg, input_path, out_path, channels=channels, start=start, length=length, filters=[])
        _channels, _rate, raw = read_wav(out_path)
        raw_rms = pcm_rms_db(raw)
        measured["input_rms_db"] = round(raw_rms, 2)
        applied_gain = gain_db + (target_rms_db - raw_rms)
        for _attempt in range(2):
            filters = [f"volume={applied_gain:.2f}dB", limiter, *fades]
            command = _ffmpeg_cut(ffmpeg, input_path, out_path, channels=channels, start=start,
                                  length=length, filters=filters)
            _channels, _rate, pcm = read_wav(out_path)
            got = pcm_rms_db(pcm)
            if abs(got - target_rms_db) <= 0.3:
                break
            applied_gain += target_rms_db - got
        measured["output_rms_db"] = round(got, 2)
    else:
        filters = []
        if loudnorm_lufs is not None:
            filters.append(f"loudnorm=I={loudnorm_lufs}:TP=-1.0:LRA=11")
        if gain_db:
            filters.append(f"volume={gain_db}dB")
        filters += fades
        command = _ffmpeg_cut(ffmpeg, input_path, out_path, channels=channels, start=start,
                              length=length, filters=filters)
        _channels, _rate, pcm = read_wav(out_path)
        measured["output_rms_db"] = round(pcm_rms_db(pcm), 2)
    got_channels, got_rate, pcm = read_wav(out_path)
    _require(got_channels == channels and got_rate == SAMPLE_RATE, "ffmpeg did not produce the requested shape")
    frames = len(pcm) // (channels * 2)
    return {"out": str(out_path), "frames": frames, "seconds": round(frames / SAMPLE_RATE, 6),
            "channels": channels, "sample_rate": SAMPLE_RATE, "applied_gain_db": round(applied_gain, 2),
            **measured, "ffmpeg": command}


def transcribe_directory(wav_dir: Path, model_dir: Path, out_path: Path | None = None,
                         pattern: str = "*.wav") -> list[dict[str, object]]:
    """Run Vosk over a directory of exported WAVs (lazy import; needs the vosk package)."""

    try:
        import vosk  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise CommentarySwapError("the vosk package is not installed in this interpreter") from exc
    vosk.SetLogLevel(-1)
    model = vosk.Model(str(model_dir))
    rows: list[dict[str, object]] = []
    for wav in sorted(Path(wav_dir).glob(pattern)):
        channels, rate, pcm = read_wav(wav)
        if channels == 2:
            samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
            pcm = struct.pack(f"<{len(samples) // 2}h",
                              *[(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)])
        recognizer = vosk.KaldiRecognizer(model, rate)
        recognizer.SetWords(True)
        for offset in range(0, len(pcm), 8000):
            recognizer.AcceptWaveform(pcm[offset:offset + 8000])
        result = json.loads(recognizer.FinalResult())
        rows.append({"file": wav.name, "seconds": round(len(pcm) / 2 / rate, 3),
                     "text": result.get("text", ""), "words": result.get("result", [])})
    if out_path is not None:
        Path(out_path).write_text(json.dumps(rows, indent=2), newline="\n")
    return rows


# --------------------------------------------------------------------------- CLI
def _descriptors(args: argparse.Namespace) -> tuple[tuple[int, int, int, int, str], ...]:
    fixture = getattr(args, "descriptors_fixture", None)
    if not fixture:
        return PINNED_DESCRIPTORS
    return tuple(tuple(item) for item in json.loads(fixture))


def _cmd_list(args: argparse.Namespace) -> int:
    with DiscBanks(Path(args.xiso), descriptors=_descriptors(args)) as disc:
        if args.bank is None:
            print(f"{'bank':15s} {'streams':>8s} {'ch':>2s} {'bytes':>14s} {'total s':>10s}  {'ext outer':>9s}  role")
            for name, bank in sorted(disc.banks.items()):
                total = bank.external_size // bank.block_align * BLOCK_FRAMES / bank.sample_rate
                print(f"{name:15s} {bank.count:8d} {bank.channels:2d} {bank.external_size:14,d} "
                      f"{total:10.1f}  {bank.external_outer_index:9d}  {BANK_ROLES.get(name, '')}")
            return 0
        rows = []
        for stream in disc.iter_streams(args.bank, args.start, args.count):
            if args.min_seconds is not None and stream.duration < args.min_seconds:
                continue
            if args.max_seconds is not None and stream.duration > args.max_seconds:
                continue
            rows.append(stream)
        if args.json:
            print(json.dumps([row.describe() for row in rows], indent=2))
            return 0
        print(f"{'stream':22s} {'seconds':>8s} {'bytes':>9s} {'blocks':>7s}  xiso offset (spans)")
        for stream in rows:
            spans = " + ".join(f"0x{s.xiso_offset:x}:{s.length}" for s in stream.spans)
            print(f"{stream.stream_id:22s} {stream.duration:8.3f} {stream.size:9d} {stream.block_count:7d}  {spans}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    with DiscBanks(Path(args.xiso)) as disc:
        if args.stream:
            streams = [disc.stream_by_id(item) for item in args.stream]
        else:
            _require(args.bank is not None, "give --stream IDs or --bank NAME")
            streams = list(disc.iter_streams(args.bank, args.start, args.count))
        rows = export_streams(disc, streams, Path(args.out))
    print(f"exported {len(rows)} stream(s) to {args.out}")
    return 0


def _cmd_conform(args: argparse.Namespace) -> int:
    with DiscBanks(Path(args.xiso)) as disc:
        stream = disc.stream_by_id(args.stream)
    target = RETAIL_SPEECH_RMS_DB if args.match_game else args.target_rms
    info = conform_clip(Path(args.input), Path(args.out), channels=stream.channels,
                        max_seconds=stream.duration, start=args.start, duration=args.duration,
                        gain_db=args.gain_db, loudnorm_lufs=args.loudnorm, target_rms_db=target,
                        fade_ms=args.fade_ms)
    info["slot_seconds"] = round(stream.duration, 6)
    info["stream"] = stream.stream_id
    print(json.dumps(info, indent=2))
    return 0


def _cmd_replace(args: argparse.Namespace) -> int:
    guards = [Path(item) for item in (args.guard or [])]
    receipt = replace_stream(Path(args.xiso), args.stream, Path(args.wav),
                             retail_packs=Path(args.retail_packs) if args.retail_packs else None,
                             expect_sha256=args.expect_sha256, force=args.force, guards=guards)
    text = json.dumps(receipt, indent=2)
    if args.receipt:
        Path(args.receipt).write_text(text, newline="\n")
    print(text)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify_stream(Path(args.xiso), args.stream, Path(args.wav),
                           Path(args.decoded_wav) if args.decoded_wav else None)
    print(json.dumps(result, indent=2))
    return 0 if result["matches_encoded_clip"] else 1


def _cmd_transcribe(args: argparse.Namespace) -> int:
    rows = transcribe_directory(Path(args.dir), Path(args.model), Path(args.out) if args.out else None,
                                args.pattern)
    for row in rows:
        print(f"{row['file']:28s} {row['seconds']:7.2f}s  {row['text']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="list banks, or the streams of one bank")
    p.add_argument("xiso")
    p.add_argument("--bank")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--min-seconds", type=float)
    p.add_argument("--max-seconds", type=float)
    p.add_argument("--json", action="store_true")
    p.add_argument("--descriptors-fixture", help=argparse.SUPPRESS)   # tests: JSON descriptor table
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("export", help="decode streams to PCM16 WAV")
    p.add_argument("xiso")
    p.add_argument("--out", required=True)
    p.add_argument("--stream", action="append", help="bank:index (repeatable)")
    p.add_argument("--bank")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=50)
    p.set_defaults(func=_cmd_export)

    p = sub.add_parser("conform", help="cut/resample any audio to a stream's shape with ffmpeg")
    p.add_argument("xiso")
    p.add_argument("--stream", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--duration", type=float)
    p.add_argument("--gain-db", type=float, default=0.0)
    p.add_argument("--loudnorm", type=float, metavar="LUFS",
                   help="EBU R128 normalise to this integrated loudness (e.g. -16) before the fades")
    p.add_argument("--target-rms", type=float, metavar="DBFS",
                   help="gain + look-ahead limiter so the clip's RMS lands here (retail speech is -14.3)")
    p.add_argument("--match-game", action="store_true",
                   help=f"shorthand for --target-rms {RETAIL_SPEECH_RMS_DB}")
    p.add_argument("--fade-ms", type=int, default=15)
    p.set_defaults(func=_cmd_conform)

    p = sub.add_parser("replace", help="write one WAV into one stream IN PLACE (use a copy!)")
    p.add_argument("xiso")
    p.add_argument("--stream", required=True)
    p.add_argument("--wav", required=True)
    p.add_argument("--retail-packs", help="extracted retail vc_53450030 folder used to verify the span first")
    p.add_argument("--expect-sha256", help="alternative gate: sha256 the span must currently have")
    p.add_argument("--force", action="store_true")
    p.add_argument("--guard", action="append", help="path(s) that must never be written (retail image)")
    p.add_argument("--receipt", help="write the JSON receipt here too")
    p.set_defaults(func=_cmd_replace)

    p = sub.add_parser("verify", help="check a stream holds exactly the encoded WAV")
    p.add_argument("xiso")
    p.add_argument("--stream", required=True)
    p.add_argument("--wav", required=True)
    p.add_argument("--decoded-wav", help="also write what the game will play, decoded from the disc")
    p.set_defaults(func=_cmd_verify)

    p = sub.add_parser("transcribe", help="Vosk-transcribe a folder of exported WAVs")
    p.add_argument("dir")
    p.add_argument("--model", required=True)
    p.add_argument("--out")
    p.add_argument("--pattern", default="*.wav")
    p.set_defaults(func=_cmd_transcribe)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except CommentarySwapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
