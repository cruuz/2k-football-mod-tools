#!/usr/bin/env python3
"""Catalog the bounded, fixed-allocation text banks on the ESPN NFL 2K5 PS2 disc.

The Xbox build of this game keeps its user-visible text in a handful of
Visual Concepts resource banks, and the studio edits them under one rule: a
replacement must fit the bytes the original string already owns, so no pointer,
record count, allocation boundary or resource size ever moves.  This tool asks
whether that same discipline is available on the PlayStation 2 disc
(``SLUS-20919``) and, where it is, writes down exactly which strings qualify.

WHAT IT FOUND (measured against the retail disc, not assumed)
-------------------------------------------------------------
The PS2 disc carries the **same 716 text-bearing resource banks as the Xbox
disc**, kind for kind: ``CRED`` 1, ``NAME`` 635, ``ROST`` 76, ``SITU`` 1,
``STRG`` 2, ``TRIV`` 1.  Four of those kinds -- CRED, SITU, STRG and TRIV, five
banks in all -- are the fixed-allocation string banks the Xbox writer proved.
On PS2 they are byte-for-byte the same size as their Xbox counterparts, carry
the same resource ids, the same record counts and the same descriptor offsets.

* **Encoding is UTF-16LE**, the same as Xbox.  Both machines are little-endian,
  and the VC object header's name pointer decodes as UTF-16LE on both.  A
  character therefore costs two bytes on PS2 exactly as it does on Xbox, so the
  Xbox character budgets transfer unchanged.  This is measured per bank and
  recorded in the catalog; a bank whose pool does not decode as UTF-16LE is
  refused rather than guessed at.
* **Every text bank is stored uncompressed** (chunk magic is 0, not
  ``0xFEEDBEEF``).  No VC-LZ recompression is involved in a text edit, so the
  "recompress to fit or refuse" path is a refusal the writer can state but
  never has to exercise on this disc.
* **Every text bank lives entirely inside one pack file**, ``/VC_20919/0.``, so
  one bounded ISO9660 file replacement covers any edit.
* **No allocation has spare room.**  Measured across all 6,873 strings, an
  allocation is exactly ``len(text) * 2 + 2`` bytes -- the pool is packed with
  no padding anywhere.  So the character budget is not "the allocation minus
  what is used", it is *the original string's own length*: a replacement may be
  shorter or the same length, never longer, not even by one character.  This is
  the single most surprising thing about the surface and the writer states it
  in every refusal.
* **The corpus is plain ASCII.**  No string contains a character above U+007E.
  Newlines do occur (45 line feeds, one carriage return), so a multi-line
  replacement is legitimate.

``NAME`` and ``ROST`` are deliberately excluded, for the same reasons as on
Xbox.  A ``NAME`` resource is a 160-byte player-name-atlas *metric* table (one
object label, then 29 pairs of 16-bit atlas offsets and advances) -- inventing
string assets for it would be wrong.  ``ROST`` is roster identity data, owned by
the bounded roster writer, not by a text editor.  635 + 76 of the 716 banks are
therefore out of scope by design, not by failure.

THE SAFETY ARGUMENT, AND WHERE IT STOPS
---------------------------------------
A string is listed as editable only when all of the following are proved from
the disc bytes:

1. the whole resource body **rebuilds byte-identically** from the decoded
   structure -- every pointer, count, id and pool boundary re-serialized and
   compared, so nothing is being carried across as an unexamined blob;
2. the string's allocation is a NUL-terminated UTF-16LE run whose start is a
   pool entry boundary, not the interior of a longer string;
3. the allocation has room for at least one code unit past its terminator;
4. its consumer is display copy, not lookup or scenario logic.

Rule 4 is what keeps ``SITU``'s two team-resource selectors and its scenario
state read-only, and what keeps ``TRIV``'s numeric correct-answer key untouched
while its seven display fields open up.  Where a consumer cannot be shown to be
display-only, the string stays read-only and says why.

Aliasing is reported, never hidden: one ``STRG`` or ``CRED`` pool allocation can
be referenced by several lookup records, so editing it changes every one of
them.  The catalog carries a reference count per allocation for that reason.

RETAIL-FREE BY CONSTRUCTION
---------------------------
The catalog records names, kinds, offsets, allocation sizes, code-unit counts,
reference counts, inline-token shapes and SHA-256 digests.  **It never records
decoded string text.**  The digest is of the UTF-16LE bytes, so a caller can
prove it is looking at the same string without the string being present here.
The ISO is opened read-only and its size re-checked afterwards.

USAGE
-----
    nfl2k5_ps2_text_target_catalog.py --iso <SLUS-20919.iso> --output cat.json
    nfl2k5_ps2_text_target_catalog.py --iso <...> --summary
    nfl2k5_ps2_text_target_catalog.py --selftest

Python 3.9 compatible, standard library only.  Imports its sibling
``tools/ps2_iso9660.py`` with its own directory placed on ``sys.path`` first,
because the installed Windows runtime does not add it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ps2_iso9660 as iso  # noqa: E402


SCHEMA = "nfl2k5_ps2_text_target_catalog/v1"

PACK_DIRECTORY = "/VC_20919"
PACK_NAMES = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PACK_SLOT_COUNT = 36
ALIGNMENT = 0x800
OUTER_HEADER_SIZE = 0x0C + PACK_SLOT_COUNT * 4          # 156
OUTER_ENTRY_SIZE = 12
MAX_OUTER_ENTRIES = 1_000_000

CHUNK_HEADER_SIZE = 0x20
LZ_MAGIC = 0xFEEDBEEF

# The four fixed-allocation string kinds.  NAME (glyph metrics) and ROST
# (roster identity, owned by the roster writer) are excluded on purpose.
TEXT_KINDS = ("CRED", "SITU", "STRG", "TRIV")
# Every text-bearing kind, counted for the parity statement only.
ALL_TEXT_BANK_KINDS = ("CRED", "NAME", "ROST", "SITU", "STRG", "TRIV")

# Xbox-proved layout constants, re-checked against the PS2 bytes on every run.
CRED_DESCRIPTOR = 0x30
CRED_RECORD_COUNT = 619
CRED_RECORD_SIZE = 0x0C
CRED_POINTER_FIELDS = (("primary_text", 0x04), ("secondary_text", 0x08))
CRED_NUMERIC_FIELDS = (0x00,)

TRIV_DESCRIPTOR = 0x44
TRIV_RECORD_COUNT = 691
TRIV_RECORD_SIZE = 0x24
TRIV_POINTER_FIELDS = (
    ("category", 0x04), ("subject", 0x08), ("question", 0x0C),
    ("answer_a", 0x10), ("answer_b", 0x14), ("answer_c", 0x18),
    ("answer_d", 0x1C),
)
TRIV_NUMERIC_FIELDS = (0x00, 0x20)

SITU_DESCRIPTOR = 0x40
SITU_RECORD_COUNT = 25
SITU_RECORD_SIZE = 0x6C
SITU_POOL_OFFSET = 0xAD0
SITU_DISPLAY_FIELDS = (
    ("title", 0x00), ("historical_description", 0x04),
    ("challenge_objective", 0x08), ("date", 0x0C),
)
SITU_SELECTOR_FIELDS = (
    ("away_team_asset_code", 0x14), ("home_team_asset_code", 0x18),
)

STRG_RECORD_SIZE = 0x0C
STRG_TRAILER_MAX = 4096
MAX_RECORDS = 1_000_000

# Inline formatted tokens, in the two shapes this engine consumes.
#
# NFL 2K5's formatted-string loop renders 57 pipe-delimited markers -- |CROSS|,
# |M_BACK|, |LINK| -- as button glyphs and inline art; see
# ``tools/nfl_formatted_token.py`` for the recovered table.  Separately, a
# printf-style conversion hands the formatter an argument to read.  Both are
# tracked because both change what the engine does at draw time, and both are
# required to survive an edit unchanged.
#
# Measured over all 6,873 PS2 pool strings: two carry pipe tokens, and **none
# carries a printf conversion**.  Twelve contain a literal '%' -- trivia answers
# such as "20%" -- which the strict conversion pattern below deliberately does
# not match, because a '%' with no conversion character after it is not a
# conversion.
PIPE_TOKEN_PATTERN = re.compile(r"\|[A-Za-z0-9_]{1,24}\|")
PRINTF_TOKEN_PATTERN = re.compile(r"%[-+ #0]*[0-9]*(?:\.[0-9]+)?[diouxXeEfgGcsp%]")


class CatalogError(ValueError):
    """The disc did not match the layout this catalog is willing to claim."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise CatalogError(message)


# ---------------------------------------------------------------------------
# Virtual archive over the /VC_20919 pack files
# ---------------------------------------------------------------------------

class VirtualPacks:
    """``/VC_20919/0.`` .. ``N.`` addressed as one virtual byte range.

    The packs are separate ISO9660 files but the outer entry table addresses
    them as a single concatenation, so an entry may straddle two of them.  Any
    span that does straddle is refused for editing later on, because one
    bounded ISO file replacement cannot cover two files.
    """

    def __init__(self, iso_path: str, packs: Sequence[Tuple[str, int, int]]):
        self.iso_path = iso_path
        self.packs = list(packs)                 # [(name, iso_byte_base, size)]
        self.starts = [0]
        for _name, _base, size in self.packs:
            self.starts.append(self.starts[-1] + size)
        self._handle = None

    def __enter__(self) -> "VirtualPacks":
        self._handle = open(self.iso_path, "rb")
        return self

    def __exit__(self, *_exc) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    @property
    def size(self) -> int:
        return self.starts[-1]

    def pack_of(self, virtual_offset: int) -> int:
        _require(virtual_offset >= 0, "negative virtual offset")
        for index in range(len(self.packs) - 1, -1, -1):
            if self.starts[index] <= virtual_offset:
                return index
        raise CatalogError("negative virtual offset")

    def locate(self, virtual_offset: int, size: int) -> Tuple[str, int, int, bool]:
        """``(pack_name, offset_in_pack, iso_byte_offset, crosses_pack)``."""
        index = self.pack_of(virtual_offset)
        name, base, _pack_size = self.packs[index]
        inside = virtual_offset - self.starts[index]
        crosses = (virtual_offset + size) > self.starts[index + 1]
        return name, inside, base + inside, crosses

    def read(self, virtual_offset: int, size: int) -> bytes:
        if size <= 0:
            return b""
        _require(
            0 <= virtual_offset and virtual_offset + size <= self.starts[-1],
            "read outside the virtual archive",
        )
        _require(self._handle is not None, "virtual archive is not open")
        parts = []
        while size:
            index = self.pack_of(virtual_offset)
            inside = virtual_offset - self.starts[index]
            take = min(size, self.packs[index][2] - inside)
            self._handle.seek(self.packs[index][1] + inside)
            block = self._handle.read(take)
            _require(len(block) == take, "short read from pack %s" % self.packs[index][0])
            parts.append(block)
            virtual_offset += take
            size -= take
        return b"".join(parts)


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


def read_outer_table(archive: VirtualPacks) -> List[Tuple[int, int, int]]:
    """``[(name_id, size, offset_blocks)]`` from the outer index at virtual 0."""
    header = archive.read(0, OUTER_HEADER_SIZE)
    entry_count, _reserved, populated = struct.unpack_from("<III", header, 0)
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
    return entries


def find_text_chunks(archive: VirtualPacks,
                     entries: Sequence[Tuple[int, int, int]]) -> List[dict]:
    """Walk every outer entry's resource chunks and keep the text kinds.

    A chunk header is 0x20 bytes: FourCC, stored_size, system_bytes,
    video_bytes, then ``0xFEEDBEEF`` when the body is LZ-compressed.  Chunks run
    back to back inside an entry, so the walk is a forward scan; a header that
    does not look like a chunk ends the entry rather than being guessed past.
    """
    found: List[dict] = []
    wanted = {kind.encode("ascii") for kind in TEXT_KINDS}
    for outer_index, (name_id, entry_size, offset_blocks) in enumerate(entries):
        if entry_size < CHUNK_HEADER_SIZE:
            continue
        base = offset_blocks * ALIGNMENT
        offset = 0
        chunk_index = 0
        while offset + CHUNK_HEADER_SIZE <= entry_size:
            header = archive.read(base + offset, CHUNK_HEADER_SIZE)
            fourcc = header[0:4]
            stored, system_bytes, video_bytes, magic = struct.unpack_from(
                "<IIII", header, 4)
            if not fourcc.isalnum() and not _printable_fourcc(fourcc):
                break
            if stored == 0 or offset + CHUNK_HEADER_SIZE + stored > entry_size:
                break
            if fourcc in wanted:
                found.append({
                    "kind": fourcc.decode("ascii"),
                    "outer_index": outer_index,
                    "outer_name_id": name_id,
                    "chunk_index": chunk_index,
                    "chunk_offset": offset,
                    "virtual_offset": base + offset,
                    "stored_size": stored,
                    "system_bytes": system_bytes,
                    "video_bytes": video_bytes,
                    "compressed": magic == LZ_MAGIC,
                })
            offset += CHUNK_HEADER_SIZE + stored
            offset = (offset + 15) & ~15
            chunk_index += 1
    return found


def _printable_fourcc(fourcc: bytes) -> bool:
    return all(0x20 <= byte < 0x7F for byte in fourcc)


# ---------------------------------------------------------------------------
# Shared VC object decoding
# ---------------------------------------------------------------------------

def relative_target(body: bytes, field_offset: int, label: str) -> int:
    """VC's field-local, minus-one-biased pointer: ``field + s32 - 1``."""
    _require(0 <= field_offset and field_offset + 4 <= len(body),
             "%s pointer field is out of bounds" % label)
    stored = struct.unpack_from("<i", body, field_offset)[0]
    target = field_offset + stored - 1
    _require(0 <= target < len(body), "%s pointer resolves outside its resource" % label)
    return target


def utf16z(body: bytes, offset: int, label: str) -> Tuple[str, int]:
    """Decode one NUL-terminated UTF-16LE run; return ``(text, end_offset)``."""
    _require(0 <= offset and offset + 2 <= len(body) and not (offset & 1),
             "%s has an invalid UTF-16 offset" % label)
    cursor = offset
    while cursor + 2 <= len(body):
        if body[cursor:cursor + 2] == b"\0\0":
            try:
                return body[offset:cursor].decode("utf-16le"), cursor + 2
            except UnicodeDecodeError as exc:
                raise CatalogError("%s is not valid UTF-16LE: %s" % (label, exc))
        cursor += 2
    raise CatalogError("%s is not NUL-terminated" % label)


def tokens_in(text: str) -> List[str]:
    """Every inline formatted token, in order, with duplicates kept.

    Order matters as much as membership: ``"|L1| then |R1|"`` and
    ``"|R1| then |L1|"`` draw different glyphs in different places, and two
    printf conversions swapped read their arguments in the wrong order.
    """
    return PIPE_TOKEN_PATTERN.findall(text) + PRINTF_TOKEN_PATTERN.findall(text)


def check_tokens_preserved(original: str, replacement: str, label: str) -> None:
    """Refuse a replacement that drops, adds, renames or reorders a token."""
    before = tokens_in(original)
    after = tokens_in(replacement)
    if before == after:
        return
    missing = [token for token in before if token not in after]
    added = [token for token in after if token not in before]
    if missing:
        raise CatalogError(
            "%s drops the inline token%s %s; the engine draws %s from %s, so it "
            "must appear in the replacement too."
            % (label, "" if len(missing) == 1 else "s",
               ", ".join(sorted(set(missing))),
               "a glyph" if len(missing) == 1 else "glyphs",
               "it" if len(missing) == 1 else "them"))
    if added:
        raise CatalogError(
            "%s introduces the inline token%s %s, which the original does not "
            "have. A pipe marker draws a glyph and a %% conversion makes the "
            "formatter read an argument that was never passed."
            % (label, "" if len(added) == 1 else "s",
               ", ".join(sorted(set(added)))))
    raise CatalogError(
        "%s keeps the same inline tokens but reorders them (%s becomes %s); "
        "the engine draws them in the order it finds them."
        % (label, " ".join(before), " ".join(after)))


def encode_fixed_utf16le(value: str, allocation_bytes: int, label: str) -> bytes:
    """Encode one nonempty NUL-terminated value without moving its allocation.

    Shorter values keep their terminator and zero-fill the rest of the
    allocation, so no stale tail of the old string survives to be read by a
    consumer that walks past the terminator.
    """
    _require(isinstance(value, str) and value != "", "%s cannot be empty" % label)
    _require("\0" not in value, "%s cannot contain a NUL character" % label)
    _require(allocation_bytes >= 2 and not (allocation_bytes & 1),
             "%s has an invalid UTF-16 allocation" % label)
    try:
        encoded = value.encode("utf-16le")
    except UnicodeEncodeError as exc:
        raise CatalogError("%s contains invalid Unicode: %s" % (label, exc))
    required = len(encoded) + 2
    limit = allocation_bytes // 2 - 1
    if required > allocation_bytes:
        raise CatalogError(
            "%s uses %d UTF-16 code units; this allocation allows %d. "
            "Some emoji and uncommon symbols cost two units."
            % (label, len(encoded) // 2, limit))
    return encoded + b"\0\0" + bytes(allocation_bytes - required)


# ---------------------------------------------------------------------------
# Bank parsers.  Each returns (bank dict, [string dict]) and every one of them
# rebuilds the whole body byte-identically before claiming anything.
# ---------------------------------------------------------------------------

def _trailer_report(body: bytes, pool_end: int) -> dict:
    """Describe the bytes past the string pool without interpreting them.

    Every one of these banks ends with a short run the pool does not reach.
    Three of the five are zero padding; the small STRG bank ends in four
    nonzero bytes whose meaning is not proved.  Rather than pretend they are
    padding -- or refuse an otherwise fully decoded bank because of them --
    they are carried through verbatim, digested, and reported as opaque.  No
    string allocation overlaps them, so a fixed-span edit cannot reach them.
    """
    tail = body[pool_end:]
    return {
        "bytes": len(tail),
        "all_zero": tail == bytes(len(tail)),
        "sha256": hashlib.sha256(tail).hexdigest(),
        "preserved_verbatim": True,
    }


class _Pool:
    __slots__ = ("index", "start", "end", "text", "references")

    def __init__(self, index: int, start: int, end: int, text: str) -> None:
        self.index = index
        self.start = start
        self.end = end
        self.text = text
        self.references = 0


def _check_vc_header(body: bytes, kind: str) -> Tuple[int, int, str]:
    """``(name_offset, descriptor_offset, name)`` with the reserved prefix proved."""
    marker = kind.encode("ascii")
    _require(len(body) > 0x18, "%s body is shorter than its inner header" % kind)
    _require(body[0x0C:0x10] == marker, "%s inner marker is missing at +0x0C" % kind)
    _require(body[:0x0C] == bytes(0x0C), "%s reserved prefix is not zero" % kind)
    name_offset = relative_target(body, 0x10, "%s name" % kind)
    descriptor = relative_target(body, 0x14, "%s descriptor" % kind)
    name, name_end = utf16z(body, name_offset, "%s name" % kind)
    _require(name_end <= descriptor, "%s name overlaps its descriptor" % kind)
    return name_offset, descriptor, name


def _rebuild_prefix(body: bytes, kind: str, name_offset: int,
                    descriptor: int, name: str) -> bytearray:
    prefix = bytearray(descriptor)
    prefix[0x0C:0x10] = kind.encode("ascii")
    struct.pack_into("<i", prefix, 0x10, name_offset - 0x10 + 1)
    struct.pack_into("<i", prefix, 0x14, descriptor - 0x14 + 1)
    encoded = name.encode("utf-16le") + b"\0\0"
    prefix[name_offset:name_offset + len(encoded)] = encoded
    _require(body[:descriptor] == bytes(prefix),
             "%s inner-header reserved bytes differ from the proved layout" % kind)
    return prefix


def parse_pointer_pool(body: bytes, kind: str, *, descriptor_offset: int,
                       record_count: int, record_size: int,
                       pointer_fields: Sequence[Tuple[str, int]],
                       numeric_fields: Sequence[int],
                       trailer_bytes: Optional[int] = None) -> dict:
    """Parse and byte-identically rebuild a fixed-record UTF-16LE pointer pool."""
    name_offset, descriptor, name = _check_vc_header(body, kind)
    _require(descriptor == descriptor_offset,
             "%s descriptor is at 0x%x; the proved layout has 0x%x"
             % (kind, descriptor, descriptor_offset))
    prefix = _rebuild_prefix(body, kind, name_offset, descriptor, name)

    count = struct.unpack_from("<I", body, descriptor)[0]
    _require(count == record_count,
             "%s record count is %d; expected %d" % (kind, count, record_count))
    table = descriptor + 4
    pool_offset = table + count * record_size
    _require(pool_offset <= len(body), "%s record table exceeds its body" % kind)

    decoded: Dict[int, Tuple[str, int]] = {}
    targets: Dict[Tuple[int, str], int] = {}
    references: Dict[int, int] = {}
    for record_index in range(count):
        base = table + record_index * record_size
        for field_name, relative in pointer_fields:
            field = base + relative
            label = "%s record %d %s" % (kind, record_index, field_name)
            target = relative_target(body, field, label)
            _require(target >= pool_offset, "%s points before its string pool" % label)
            value, end = utf16z(body, target, label)
            prior = decoded.setdefault(target, (value, end))
            _require(prior == (value, end), "%s alias decoding is inconsistent" % kind)
            references[target] = references.get(target, 0) + 1
            targets[(record_index, field_name)] = target

    pool_end = max((end for _v, end in decoded.values()), default=pool_offset)
    cursor = pool_offset
    pool: List[_Pool] = []
    while cursor < pool_end:
        value, end = utf16z(body, cursor, "%s pool entry" % kind)
        _require(decoded.get(cursor) == (value, end),
                 "%s pool holds an unreferenced or interior allocation at 0x%x"
                 % (kind, cursor))
        item = _Pool(len(pool), cursor, end, value)
        item.references = references[cursor]
        pool.append(item)
        cursor = end
    _require(set(decoded) == {item.start for item in pool},
             "%s pool and reference boundaries disagree" % kind)

    trailer = len(body) - cursor
    if trailer_bytes is not None:
        _require(trailer == trailer_bytes,
                 "%s trailer is %d bytes; the proved layout has %d"
                 % (kind, trailer, trailer_bytes))
    _require(0 <= trailer <= STRG_TRAILER_MAX,
             "%s trailer is %d bytes, past the sanity cap" % (kind, trailer))

    rebuilt = bytearray(len(body))
    rebuilt[:descriptor] = prefix
    struct.pack_into("<I", rebuilt, descriptor, count)
    by_start = {item.start: item for item in pool}
    record_pool_indices: Dict[Tuple[int, str], int] = {}
    for record_index in range(count):
        base = table + record_index * record_size
        for relative in numeric_fields:
            rebuilt[base + relative:base + relative + 4] = \
                body[base + relative:base + relative + 4]
        for field_name, relative in pointer_fields:
            field = base + relative
            target = targets[(record_index, field_name)]
            struct.pack_into("<i", rebuilt, field, target - field + 1)
            record_pool_indices[(record_index, field_name)] = by_start[target].index
    for item in pool:
        rebuilt[item.start:item.end] = item.text.encode("utf-16le") + b"\0\0"
    # The bytes past the pool are carried through unexamined -- see
    # ``_trailer_report``.  They lie outside every string allocation, so a
    # bounded edit never reaches them.
    rebuilt[cursor:] = body[cursor:]
    _require(bytes(rebuilt) == body, "%s did not rebuild byte-identically" % kind)

    return {
        "name": name, "count": count, "descriptor_offset": descriptor,
        "record_table_offset": table, "pool_offset": pool_offset,
        "pool": pool, "record_pool_indices": record_pool_indices,
        "trailer": _trailer_report(body, cursor),
    }


def parse_strg(body: bytes) -> dict:
    """STRG: ``(id_a, id_b, code_units)`` records indexing a UTF-16LE pool."""
    name_offset, descriptor, name = _check_vc_header(body, "STRG")
    prefix = _rebuild_prefix(body, "STRG", name_offset, descriptor, name)
    count = struct.unpack_from("<I", body, descriptor)[0]
    _require(0 < count <= MAX_RECORDS, "STRG declares %d records" % count)
    table = descriptor + 4
    pool_offset = table + count * STRG_RECORD_SIZE
    _require(pool_offset <= len(body), "STRG record table exceeds its body")

    rows: List[Tuple[int, int, int, int]] = []
    decoded: Dict[int, Tuple[str, int]] = {}
    references: Dict[int, int] = {}
    for index in range(count):
        offset = table + index * STRG_RECORD_SIZE
        id_a, id_b, code_units = struct.unpack_from("<III", body, offset)
        target = pool_offset + code_units * 2
        _require(pool_offset <= target < len(body),
                 "STRG record %d targets 0x%x, outside its pool" % (index, target))
        value, end = utf16z(body, target, "STRG record %d text" % index)
        prior = decoded.setdefault(target, (value, end))
        _require(prior == (value, end), "STRG shared offset disagrees")
        references[target] = references.get(target, 0) + 1
        rows.append((id_a, id_b, code_units, target))

    pool_end = max((end for _v, end in decoded.values()), default=pool_offset)
    cursor = pool_offset
    pool: List[_Pool] = []
    while cursor < pool_end:
        value, end = utf16z(body, cursor, "STRG pool entry")
        _require(decoded.get(cursor) == (value, end),
                 "STRG pool holds an unreferenced or interior allocation at 0x%x" % cursor)
        item = _Pool(len(pool), cursor, end, value)
        item.references = references[cursor]
        pool.append(item)
        cursor = end
    _require(set(decoded) == {item.start for item in pool},
             "STRG pool and reference boundaries disagree")
    trailer = len(body) - cursor
    _require(0 <= trailer <= STRG_TRAILER_MAX,
             "STRG trailer is %d bytes, past the sanity cap" % trailer)

    by_start = {item.start: item.index for item in pool}
    rebuilt = bytearray(len(body))
    rebuilt[:descriptor] = prefix
    struct.pack_into("<I", rebuilt, descriptor, count)
    for index, (id_a, id_b, code_units, target) in enumerate(rows):
        offset = table + index * STRG_RECORD_SIZE
        delta = pool[by_start[target]].start - pool_offset
        _require(not (delta & 1), "STRG text offset is not in UTF-16 code units")
        struct.pack_into("<III", rebuilt, offset, id_a, id_b, delta // 2)
        _require(delta // 2 == code_units, "STRG re-derived a different pool index")
    for item in pool:
        rebuilt[item.start:item.end] = item.text.encode("utf-16le") + b"\0\0"
    rebuilt[cursor:] = body[cursor:]
    _require(bytes(rebuilt) == body, "STRG did not rebuild byte-identically")

    return {"name": name, "count": count, "descriptor_offset": descriptor,
            "record_table_offset": table, "pool_offset": pool_offset,
            "pool": pool, "trailer": _trailer_report(body, cursor)}


def parse_situ(body: bytes) -> dict:
    """SITU: 25 anniversary-moment records, four display pointers each."""
    name_offset, descriptor, name = _check_vc_header(body, "SITU")
    _require(descriptor == SITU_DESCRIPTOR,
             "SITU descriptor is at 0x%x; the proved layout has 0x%x"
             % (descriptor, SITU_DESCRIPTOR))
    prefix = _rebuild_prefix(body, "SITU", name_offset, descriptor, name)
    count = struct.unpack_from("<I", body, descriptor)[0]
    _require(count == SITU_RECORD_COUNT,
             "SITU moment count is %d; the proved layout has %d"
             % (count, SITU_RECORD_COUNT))
    table = descriptor + 4
    pool_offset = table + count * SITU_RECORD_SIZE
    _require(pool_offset == SITU_POOL_OFFSET,
             "SITU record table ends at 0x%x; the proved pool starts at 0x%x"
             % (pool_offset, SITU_POOL_OFFSET))

    all_fields = tuple(SITU_DISPLAY_FIELDS) + tuple(SITU_SELECTOR_FIELDS)
    targets: Dict[Tuple[int, str], int] = {}
    decoded: Dict[int, Tuple[str, int]] = {}
    for moment in range(count):
        base = table + moment * SITU_RECORD_SIZE
        for field_name, relative in all_fields:
            field = base + relative
            label = "SITU moment %d %s" % (moment + 1, field_name)
            target = relative_target(body, field, label)
            _require(target >= pool_offset, "%s points before its string pool" % label)
            value, end = utf16z(body, target, label)
            _require(target not in decoded,
                     "SITU unexpectedly aliases two text allocations")
            decoded[target] = (value, end)
            targets[(moment, field_name)] = target

    cursor = pool_offset
    pool: List[_Pool] = []
    for start in sorted(decoded):
        _require(start == cursor, "SITU string pool is not a contiguous owned sequence")
        value, end = decoded[start]
        item = _Pool(len(pool), start, end, value)
        item.references = 1
        pool.append(item)
        cursor = end
    by_start = {item.start: item.index for item in pool}
    rebuilt = bytearray(len(body))
    rebuilt[:descriptor] = prefix
    struct.pack_into("<I", rebuilt, descriptor, count)
    for moment in range(count):
        base = table + moment * SITU_RECORD_SIZE
        # Every byte of the record that is not one of the six pointers is
        # scenario state; copy it through verbatim and prove it round-trips.
        rebuilt[base:base + SITU_RECORD_SIZE] = body[base:base + SITU_RECORD_SIZE]
        for field_name, relative in all_fields:
            field = base + relative
            struct.pack_into("<i", rebuilt, field, targets[(moment, field_name)] - field + 1)
    for item in pool:
        rebuilt[item.start:item.end] = item.text.encode("utf-16le") + b"\0\0"
    rebuilt[cursor:] = body[cursor:]
    _require(bytes(rebuilt) == body, "SITU did not rebuild byte-identically")

    return {"name": name, "count": count, "descriptor_offset": descriptor,
            "record_table_offset": table, "pool_offset": pool_offset,
            "pool": pool, "targets": targets, "pool_by_start": by_start,
            "trailer": _trailer_report(body, cursor)}


# ---------------------------------------------------------------------------
# Catalog assembly
# ---------------------------------------------------------------------------

# Per-string prose is factored out into codes.  6,873 copies of the same
# sentence is 750 KB of repetition in a file a reviewer has to open.
REASON_CODES = {
    "fixed_allocation_sole_owner":
        "Fixed allocation with a single owning record.",
    "fixed_allocation_aliased":
        "Fixed allocation. Editing this updates every record that shares it; "
        "see reference_count.",
    "terminator_only":
        "This allocation holds only its terminator, so no nonempty text fits "
        "inside it.",
    "situ_display_string":
        "This display string has a unique fixed allocation and a display-only "
        "consumer. Scenario state is unchanged.",
    "situ_team_selector":
        "This is a team-resource selector consumed by scenario lookup, not "
        "display copy; its lookup constraints are not proved, so it stays "
        "read-only.",
    "triv_display_field":
        "Category, subject, question and the four answers each own a unique "
        "fixed allocation. The numeric correct-answer key is not touched.",
}


def _string_record(*, selector: str, label: str, kind: str, item: _Pool,
                   body_offset: int, editable: bool, reason_code: str,
                   field_name: str, owner_index: int) -> dict:
    """One catalog row.

    ``character_limit`` is ``allocation_bytes // 2 - 1`` and the spare capacity
    is that minus ``used_code_units``; both are left to the reader rather than
    stored 6,873 times.  On this disc the spare is always zero.
    """
    _require(reason_code in REASON_CODES, "unknown reason code %s" % reason_code)
    encoded = item.text.encode("utf-16le")
    return {
        "selector": selector,
        "label": label,
        "bank_kind": kind,
        "field_name": field_name,
        "owner_index": owner_index,
        "pool_index": item.index,
        "body_offset": body_offset,
        "allocation_bytes": item.end - item.start,
        "used_code_units": len(encoded) // 2,
        "ascii_only": all(ord(char) < 0x7F for char in item.text),
        "reference_count": item.references,
        "tokens": tokens_in(item.text),
        "text_sha256": hashlib.sha256(encoded).hexdigest(),
        "editable": editable,
        "reason_code": reason_code,
    }


def _bank_common(chunk: dict, archive: VirtualPacks) -> dict:
    body_voff = chunk["virtual_offset"] + CHUNK_HEADER_SIZE
    pack_name, pack_offset, iso_offset, crosses = archive.locate(
        body_voff, chunk["stored_size"])
    return {
        "pack_iso_path": "%s/%s." % (PACK_DIRECTORY, pack_name),
        "pack_name": pack_name,
        "pack_offset": pack_offset,
        "iso_byte_offset": iso_offset,
        "crosses_pack_boundary": crosses,
        "body_virtual_offset": body_voff,
    }


def build_catalog(iso_path: str) -> dict:
    """Open the ISO read-only and derive the whole catalog from its bytes."""
    image = iso.open_image(iso_path)
    identity = iso.boot_identity(image)
    size_before = os.stat(iso_path).st_size
    packs = discover_packs(image)

    banks: List[dict] = []
    strings: List[dict] = []
    with VirtualPacks(iso_path, packs) as archive:
        entries = read_outer_table(archive)
        chunks = find_text_chunks(archive, entries)
        for chunk in sorted(chunks, key=lambda c: (c["outer_index"], c["chunk_index"])):
            kind = chunk["kind"]
            bank_id = "nfl2k5.ps2.text-bank.%s.%d.%d" % (
                kind.lower(), chunk["outer_index"], chunk["chunk_index"])
            common = _bank_common(chunk, archive)
            record: dict = dict(chunk)
            record.update(common)
            record["bank_id"] = bank_id
            if chunk["compressed"]:
                record.update(decoded=False, editable_count=0, read_only_count=0,
                              encoding=None, rebuild_byte_identical=False,
                              reason="The chunk body is LZ-compressed; a bounded "
                                     "fixed-span edit of it is not proved.")
                banks.append(record)
                continue
            if common["crosses_pack_boundary"]:
                record.update(decoded=False, editable_count=0, read_only_count=0,
                              encoding=None, rebuild_byte_identical=False,
                              reason="The chunk body spans two pack files; one "
                                     "bounded ISO file replacement cannot cover it.")
                banks.append(record)
                continue
            body = archive.read(common["body_virtual_offset"], chunk["stored_size"])
            try:
                added = _decode_bank(kind, body, bank_id, chunk)
            except CatalogError as exc:
                record.update(decoded=False, editable_count=0, read_only_count=0,
                              encoding=None, rebuild_byte_identical=False,
                              reason="Not decoded: %s" % exc)
                banks.append(record)
                continue
            bank_extra, bank_strings = added
            record.update(bank_extra)
            record["decoded"] = True
            record["encoding"] = "utf-16le"
            record["rebuild_byte_identical"] = True
            record["body_sha256"] = hashlib.sha256(body).hexdigest()
            record["editable_count"] = sum(1 for s in bank_strings if s["editable"])
            record["read_only_count"] = sum(1 for s in bank_strings if not s["editable"])
            banks.append(record)
            strings.extend(bank_strings)

    _require(os.stat(iso_path).st_size == size_before,
             "the ISO changed size while it was being catalogued")

    kinds = {}
    for bank in banks:
        kinds[bank["kind"]] = kinds.get(bank["kind"], 0) + 1
    return {
        "schema": SCHEMA,
        "disc": {
            "boot2": identity.get("boot2"),
            "serial": identity.get("serial"),
            "boot_sha256": identity.get("boot_sha256"),
            "volume_id": image.volume_id,
            "size_bytes": size_before,
            "pack_count": len(packs),
            "packs": [{"name": n, "iso_byte_offset": b, "size": s} for n, b, s in packs],
        },
        "scope": {
            "in_scope_kinds": list(TEXT_KINDS),
            "excluded_kinds": {
                "NAME": "160-byte player-name-atlas metric tables, not user text",
                "ROST": "roster identity, owned by the bounded roster writer",
            },
            "encoding": "utf-16le",
            "reason_codes": dict(REASON_CODES),
            "character_limit_formula": "allocation_bytes // 2 - 1",
            "fixed_allocation_only": True,
            "pointers_unchanged": True,
            "resource_sizes_unchanged": True,
            "tokens_preserved": True,
            "catalog_contains_decoded_text": False,
        },
        "summary": {
            "bank_count": len(banks),
            "bank_kind_counts": dict(sorted(kinds.items())),
            "decoded_bank_count": sum(1 for b in banks if b["decoded"]),
            "compressed_bank_count": sum(1 for b in banks if b["compressed"]),
            "string_count": len(strings),
            "editable_count": sum(1 for s in strings if s["editable"]),
            "read_only_count": sum(1 for s in strings if not s["editable"]),
            "tokenised_string_count": sum(1 for s in strings if s["tokens"]),
            "aliased_allocation_count": sum(
                1 for s in strings if s["reference_count"] > 1),
            "strings_with_spare_capacity": sum(
                1 for s in strings
                if s["allocation_bytes"] // 2 - 1 > s["used_code_units"]),
            "non_ascii_string_count": sum(
                1 for s in strings if not s["ascii_only"]),
        },
        "banks": banks,
        "strings": strings,
    }


def _decode_bank(kind: str, body: bytes, bank_id: str,
                 chunk: dict) -> Tuple[dict, List[dict]]:
    if kind == "STRG":
        return _strg_assets(body, bank_id)
    if kind == "CRED":
        return _cred_assets(body, bank_id)
    if kind == "TRIV":
        return _triv_assets(body, bank_id)
    if kind == "SITU":
        return _situ_assets(body, bank_id)
    raise CatalogError("unsupported text kind %s" % kind)


def _capacity_code(editable: bool, references: int) -> str:
    if not editable:
        return "terminator_only"
    return ("fixed_allocation_aliased" if references > 1
            else "fixed_allocation_sole_owner")


def _strg_assets(body: bytes, bank_id: str) -> Tuple[dict, List[dict]]:
    parsed = parse_strg(body)
    strings = []
    for item in parsed["pool"]:
        editable = (item.end - item.start) > 2
        strings.append(_string_record(
            selector="%s:message:%d" % (bank_id, item.index),
            label="String message %d" % item.index,
            kind="STRG", item=item, body_offset=item.start,
            editable=editable,
            reason_code=_capacity_code(editable, item.references),
            field_name="text", owner_index=item.index))
    return ({"resource_name": parsed["name"], "record_count": parsed["count"],
             "pool_entry_count": len(parsed["pool"]),
             "descriptor_offset": parsed["descriptor_offset"],
             "pool_offset": parsed["pool_offset"],
             "trailer": parsed["trailer"],
             "reason": "Lookup records index a UTF-16LE pool by code-unit "
                       "offset. Pool allocations are fixed-span editable; ids, "
                       "record order and pool starts do not move."},
            strings)


def _cred_assets(body: bytes, bank_id: str) -> Tuple[dict, List[dict]]:
    parsed = parse_pointer_pool(
        body, "CRED", descriptor_offset=CRED_DESCRIPTOR,
        record_count=CRED_RECORD_COUNT, record_size=CRED_RECORD_SIZE,
        pointer_fields=CRED_POINTER_FIELDS, numeric_fields=CRED_NUMERIC_FIELDS)
    strings = []
    for item in parsed["pool"]:
        editable = (item.end - item.start) > 2
        strings.append(_string_record(
            selector="%s:string:%d" % (bank_id, item.index),
            label="Credits string %d" % item.index,
            kind="CRED", item=item, body_offset=item.start,
            editable=editable,
            reason_code=_capacity_code(editable, item.references),
            field_name="text", owner_index=item.index))
    return ({"resource_name": parsed["name"], "record_count": parsed["count"],
             "pool_entry_count": len(parsed["pool"]),
             "descriptor_offset": parsed["descriptor_offset"],
             "pool_offset": parsed["pool_offset"],
             "trailer": parsed["trailer"],
             "reason": "Both credit-event text pointers and the whole UTF-16LE "
                       "pool decode and rebuild. Numeric event types are "
                       "untouched; zero-capacity allocations stay read-only."},
            strings)


def _triv_assets(body: bytes, bank_id: str) -> Tuple[dict, List[dict]]:
    parsed = parse_pointer_pool(
        body, "TRIV", descriptor_offset=TRIV_DESCRIPTOR,
        record_count=TRIV_RECORD_COUNT, record_size=TRIV_RECORD_SIZE,
        pointer_fields=TRIV_POINTER_FIELDS, numeric_fields=TRIV_NUMERIC_FIELDS)
    by_index = {item.index: item for item in parsed["pool"]}
    strings = []
    for question in range(parsed["count"]):
        for field_name, _relative in TRIV_POINTER_FIELDS:
            item = by_index[parsed["record_pool_indices"][(question, field_name)]]
            _require(item.references == 1,
                     "TRIV unexpectedly aliases a display string")
            strings.append(_string_record(
                selector="%s:question:%d:%s" % (bank_id, question, field_name),
                label="Trivia question %d - %s" % (
                    question + 1, field_name.replace("_", " ")),
                kind="TRIV", item=item, body_offset=item.start,
                editable=True, reason_code="triv_display_field",
                field_name=field_name, owner_index=question))
    return ({"resource_name": parsed["name"], "record_count": parsed["count"],
             "pool_entry_count": len(parsed["pool"]),
             "descriptor_offset": parsed["descriptor_offset"],
             "pool_offset": parsed["pool_offset"],
             "trailer": parsed["trailer"],
             "reason": "Seven display pointers per question decode and rebuild; "
                       "answer keys and progress state are untouched."},
            strings)


def _situ_assets(body: bytes, bank_id: str) -> Tuple[dict, List[dict]]:
    parsed = parse_situ(body)
    display = {name for name, _ in SITU_DISPLAY_FIELDS}
    by_start = parsed["pool_by_start"]
    pool = parsed["pool"]
    strings = []
    for moment in range(parsed["count"]):
        for field_name, _relative in tuple(SITU_DISPLAY_FIELDS) + tuple(SITU_SELECTOR_FIELDS):
            item = pool[by_start[parsed["targets"][(moment, field_name)]]]
            editable = field_name in display and (item.end - item.start) > 2
            strings.append(_string_record(
                selector="%s:moment:%d:%s" % (bank_id, moment, field_name),
                label="Anniversary moment %d - %s" % (
                    moment + 1, field_name.replace("_", " ")),
                kind="SITU", item=item, body_offset=item.start,
                editable=editable,
                reason_code=("situ_display_string" if editable
                             else "situ_team_selector"),
                field_name=field_name, owner_index=moment))
    return ({"resource_name": parsed["name"], "record_count": parsed["count"],
             "pool_entry_count": len(pool),
             "descriptor_offset": parsed["descriptor_offset"],
             "pool_offset": parsed["pool_offset"],
             "trailer": parsed["trailer"],
             "reason": "Title, historical description, objective and date are "
                       "fixed-span editable. Team selectors and scenario state "
                       "stay read-only."},
            strings)


# ---------------------------------------------------------------------------
# Selftest: a synthetic disc, so the parsers are exercised with no retail bytes
# ---------------------------------------------------------------------------

def build_synthetic_strg_body(texts: Sequence[str], name: str = "strings") -> bytes:
    """A structurally exact STRG body built from scratch, for tests."""
    descriptor = 0x30
    body = bytearray(descriptor)
    body[0x0C:0x10] = b"STRG"
    encoded_name = name.encode("utf-16le") + b"\0\0"
    _require(0x20 + len(encoded_name) <= descriptor, "synthetic name does not fit")
    struct.pack_into("<i", body, 0x10, 0x20 - 0x10 + 1)
    struct.pack_into("<i", body, 0x14, descriptor - 0x14 + 1)
    body[0x20:0x20 + len(encoded_name)] = encoded_name
    body.extend(struct.pack("<I", len(texts)))
    body.extend(bytes(len(texts) * STRG_RECORD_SIZE))
    table = descriptor + 4
    pool_offset = table + len(texts) * STRG_RECORD_SIZE
    cursor = pool_offset
    for index, text in enumerate(texts):
        struct.pack_into("<III", body, table + index * STRG_RECORD_SIZE,
                         0x1000 + index, 0x2000 + index, (cursor - pool_offset) // 2)
        blob = text.encode("utf-16le") + b"\0\0"
        body.extend(blob)
        cursor += len(blob)
    return bytes(body)


def selftest() -> int:
    failures: List[str] = []

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    texts = ["MENU", "Press |CROSS| to continue", "Score: %d", "x"]
    body = build_synthetic_strg_body(texts)
    parsed = parse_strg(body)
    check(parsed["count"] == 4, "synthetic STRG record count")
    check(len(parsed["pool"]) == 4, "synthetic STRG pool size")
    check([item.text for item in parsed["pool"]] == texts, "synthetic STRG texts")

    check(tokens_in("Press |CROSS| then |M_BACK|") == ["|CROSS|", "|M_BACK|"],
          "pipe token census")
    check(tokens_in("%s scored %d") == ["%s", "%d"], "printf token census")
    check(tokens_in("plain text") == [], "untokenised text yields no tokens")
    check(tokens_in("20%") == [], "a trailing literal percent is not a conversion")

    check_tokens_preserved("Press |CROSS|", "Hit |CROSS|", "t")
    for original, replacement, why in (
        ("Press |CROSS|", "Press now", "dropped token accepted"),
        ("Press now", "Press |CROSS|", "added token accepted"),
        ("|L1| then |R1|", "|R1| then |L1|", "reordered tokens accepted"),
        ("Score", "Score %d", "added conversion accepted"),
    ):
        try:
            check_tokens_preserved(original, replacement, "t")
            failures.append(why)
        except CatalogError:
            pass

    encoded = encode_fixed_utf16le("AB", 10, "t")
    check(encoded == "AB".encode("utf-16le") + b"\0\0" + bytes(4),
          "fixed encode zero-fills its tail")
    try:
        encode_fixed_utf16le("ABCDE", 10, "t")
        failures.append("over-length encode was accepted")
    except CatalogError:
        pass
    try:
        encode_fixed_utf16le("", 10, "t")
        failures.append("empty encode was accepted")
    except CatalogError:
        pass

    # A corrupted pointer must be refused, not silently re-derived.
    broken = bytearray(body)
    struct.pack_into("<I", broken, parsed["record_table_offset"] + 8, 0xFFFF)
    try:
        parse_strg(bytes(broken))
        failures.append("out-of-range STRG target was accepted")
    except CatalogError:
        pass

    # An interior (non-boundary) target must be refused.
    interior = bytearray(body)
    struct.pack_into("<I", interior, parsed["record_table_offset"] + 8, 1)
    try:
        parse_strg(bytes(interior))
        failures.append("interior STRG target was accepted")
    except CatalogError:
        pass

    for line in failures:
        print("FAIL: %s" % line, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_TEXT_CATALOG_SELFTEST_PASS checks=%d" % 15)
    return 0


def dump_catalog(catalog: dict) -> str:
    """Serialize the catalog with one string row per line.

    The header blocks are indented because people read them.  The 6,873 string
    rows are not: fully indenting them costs about two megabytes of leading
    whitespace, and one compact object per line is both smaller and easier to
    grep than a pretty-printed array.  The result is still ordinary JSON.
    """
    head = {key: value for key, value in catalog.items() if key != "strings"}
    lines = [json.dumps(head, indent=1, sort_keys=True)[:-2].rstrip()]
    lines.append(',\n "strings": [')
    rows = [json.dumps(row, sort_keys=True, separators=(",", ":"))
            for row in catalog["strings"]]
    lines.append(",\n".join("  " + row for row in rows))
    lines.append(" ]\n}\n")
    text = "".join(lines)
    # A serializer that quietly emits invalid JSON would be worse than a slow
    # one, so prove the round trip rather than trusting the string surgery.
    _require(json.loads(text) == catalog, "the catalog did not round-trip")
    return text


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--iso", help="path to the user's own SLUS-20919 ISO")
    parser.add_argument("--output", help="write the catalog JSON here")
    parser.add_argument("--summary", action="store_true",
                        help="print the summary block instead of the catalog")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.iso:
        parser.error("--iso is required unless --selftest is given")
    try:
        catalog = build_catalog(args.iso)
    except (CatalogError, iso.Iso9660Error, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(dump_catalog(catalog))
    if args.summary or not args.output:
        print(json.dumps(catalog["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
