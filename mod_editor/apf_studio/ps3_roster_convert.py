"""Convert a PS3 All-Pro Football 2K8 roster ``USERDATA`` into the Xbox 360 raw ``Roster.ROS`` layout.

Both platforms serialise the roster as the same 2,715,908-byte object graph
(40 root tables, players at ``0x150`` with stride 332, teams with stride 384,
self-relative pointers ``target = field + stored - 1``).  A stock PS3 save and
the Xbox 360 fixture are byte-identical outside content edits except for four
classes of bytes, all proved from the data rather than one sample:

1. Root pointer fields 15..18 hold serialised runtime addresses.  The Xbox
   fixture carries ``0xA3E7FD5C + file offset of the table`` for tables 15..18
   (the four differences are exactly the table sizes 532, 12768 and 29792
   bytes); the converter writes the same rule.
2. The 266 x 10 palette colours are ``RR GG BB FF`` on PS3 and ``FF RR GG BB``
   on Xbox 360 (2,660 of 2,660 colours in both files; the channel triplets are
   identical after rotation wherever the two rosters share a palette).
3. An eight-word runtime block at ``0x230224`` after the string pool and three
   words in each user-playbook bank header (``BLPS`` magic - 0x20, + 4, + 8,
   plus the truncated sixth header at the end of the file) hold runtime words
   whose Xbox values are constant across both Xbox fixtures.
4. Text.  The PS3 save format uses even-aligned UTF-16BE like Xbox (the 2019
   stock PS3 backup has zero odd pointers), but the 2026 editor pass that
   built the 1993 roster wrote six gapless runs of strings one byte early
   (2,602 bytes, 208 odd allocations, 1,344 odd nickname references) and left
   1,127 references pointing at stale offsets inside other strings.  Each odd
   run is shifted back by one byte when the guard byte before it is free,
   otherwise relocated into free pool space, and every reference to it is
   repointed; every interior/below-pool/empty reference is canonicalised to
   the shared empty string that the game's own serialiser interns.

The writer creates a new raw payload plus a JSON receipt, never touches the
source, and re-parses its output with the studio's strict readers
(:mod:`save_roster_players`, :mod:`apf_save_playbook_assignments`,
:mod:`apf_save_custom_team_appearance`) before returning.  Nothing here is
an in-game claim: loading the converted roster in Xenia is UNWITNESSED.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
from typing import Any, Mapping
import zipfile

from mod_editor.core import platform_compat

from .backend import ensure_tools_importable
from . import save_roster_players as players_reader

ensure_tools_importable()
import apf_roster  # type: ignore  # noqa: E402
import apf_save_custom_team_appearance as save_layout  # type: ignore  # noqa: E402
import apf_save_playbook_assignments as labels_reader  # type: ignore  # noqa: E402


SCHEMA = "apf2k8_ps3_roster_convert/v1"
RECEIPT_SCHEMA = "apf2k8_ps3_roster_convert_receipt/v1"
PLATFORM_PS3 = "ps3"
PLATFORM_XBOX360 = "xbox360"
PLATFORM_UNKNOWN = "unknown"
RUNTIME_STATUS = "UNWITNESSED: nobody has loaded a converted roster in Xenia or on a console"

MAX_SOURCE_BYTES = players_reader.MAX_SOURCE_BYTES
ROSTER_SIZE = 2_715_908
ROOT_OFFSET = save_layout.ROOT_OFFSET
ROOT_PAIR_COUNT = save_layout.ROOT_PAIR_COUNT
ARRAYS_END_FIELDS = (ROOT_OFFSET + 0x140, ROOT_OFFSET + 0x144)
POOL_FIELD = ROOT_OFFSET + 0x148
PLAYER_TABLE = 0
TEAM_TABLE = save_layout.TEAM_TABLE_INDEX
PALETTE_TABLE = save_layout.PALETTE_TABLE_INDEX
SELECTOR_TABLE = save_layout.SELECTOR_TABLE_INDEX
PACKED_TABLE = save_layout.PACKED_TABLE_INDEX
CONFIG_TABLE = save_layout.CONFIG_TABLE_INDEX
PALETTE_FLAG_TABLE = 15
PALETTE_COLOURS = 10
PALETTE_STRIDE = save_layout.PALETTE_STRIDE
MAX_TEXT_BYTES = players_reader.MAX_PLAYER_TEXT_UNITS * 2 + 2
EMPTY_TEXT = b"\0\0"

# Root tables that carry UTF-16BE string pointers, proved on the Xbox fixture:
# every non-null row of these columns resolves to an even, non-interior,
# printable allocation in the string pool.  Strides come from the contiguous
# root-table layout (table start + count * stride == next table start).
STRING_TABLES: Mapping[int, tuple[int, tuple[int, ...]]] = {
    PLAYER_TABLE: (players_reader.PLAYER_STRIDE, tuple(sorted(apf_roster.PLAYER_STRING_FIELDS))),
    3: (36, (0x00, 0x04, 0x08)),
    TEAM_TABLE: (players_reader.TEAM_STRIDE, tuple(sorted(apf_roster.TEAM_STRING_FIELDS))),
    5: (8, (0x00,)),
    9: (180, (0x00, 0x04, 0x08, 0x0C, 0x10)),
    10: (188, (0xB8,)),
    11: (12, (0x00, 0x04)),
    12: (8, (0x00,)),
    13: (8, (0x00,)),
    CONFIG_TABLE: (save_layout.CONFIG_STRIDE, (0x94,)),
    20: (152, (0x94,)),
    21: (32, (0x00, 0x08, 0x14, 0x18, 0x1C)),
    22: (120, (0x00, 0x04, 0x08, 0x10, 0x14, 0x18)),
}
TABLE_STRIDES: Mapping[int, int] = {
    **{index: stride for index, (stride, _cols) in STRING_TABLES.items()},
    6: 24, 7: 24, 8: 24, 14: 8, PALETTE_FLAG_TABLE: 2, PALETTE_TABLE: PALETTE_STRIDE,
    SELECTOR_TABLE: save_layout.SELECTOR_STRIDE, PACKED_TABLE: 5,
}
# Runtime words: derived receipts from the Xbox 360 fixtures (both carry the
# same values), not retail bytes.
XBOX_ROOT_RUNTIME_BASE = 0xA3E7FD5C
XBOX_ROOT_RUNTIME_TABLES = (15, 16, 17, 18)
RUNTIME_BLOCK_OFFSET = 0x230224
RUNTIME_BLOCK_WORDS = 8
RUNTIME_BLOCK_GUARD = 0x10
XBOX_RUNTIME_BLOCK = (
    0xAA90D500, 0xBF82B360, 0xAAB3D740, 0xAAB3D740,
    0xA1920000, 0x84503798, 0x00086A1C, 0x14CEDC00,
)
USER_REGION = 0x26D030
BANK_MAGIC = b"BLPS"
BANK_STRIDE = 32_288
BANK_COUNT = 5
BANK_WORD_OFFSETS = (-0x20, 0x04, 0x08)
XBOX_BANK_WORDS = (0xA72720A0, 0xA0E35203, 0x80E35203)
TRAILING_BANK_WORD = ROSTER_SIZE - 0x14


class PS3RosterConvertError(ValueError):
    """The source is not a convertible PS3 roster or the conversion did not verify."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PS3RosterConvertError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _be32(data: bytes, offset: int) -> int:
    _require(0 <= offset <= len(data) - 4, f"32-bit field is outside the roster: 0x{offset:X}")
    return struct.unpack_from(">I", data, offset)[0]


def _stored(data: bytes, offset: int) -> int:
    return struct.unpack_from(">i", data, offset)[0]


def _target(data: bytes, offset: int) -> int:
    return offset + _stored(data, offset) - 1


def _pointer_bytes(field_offset: int, target: int) -> bytes:
    stored = target + 1 - field_offset
    _require(-(1 << 31) <= stored < (1 << 31), "relocated pointer is outside the signed 32-bit range")
    return struct.pack(">i", stored)


# --------------------------------------------------------------------------
# Input


def find_roster_member(archive: Path) -> str:
    """Pick the one ``USERDATA`` roster member of a PS3 save archive."""

    with zipfile.ZipFile(archive) as bundle:
        names = [i.filename for i in bundle.infolist() if not i.filename.endswith("/")]
    candidates = [
        name for name in names
        if name.split("/")[-1] == "USERDATA" and "-ROS" in name.split("/")[-2:-1][0] if len(name.split("/")) >= 2
    ]
    if not candidates:
        candidates = [name for name in names if name.split("/")[-1] == "USERDATA"]
    _require(bool(candidates), "the archive holds no USERDATA roster member")
    _require(len(candidates) == 1, f"choose one roster member explicitly; candidates: {candidates}")
    return candidates[0]


def read_source(path: Path, member: str | None = None) -> bytes:
    """Read a raw ``USERDATA``/``Roster.ROS`` or one bounded ZIP member, read-only."""

    path = Path(path)
    if member is None and zipfile.is_zipfile(path):
        member = find_roster_member(path)
    if member is not None:
        with zipfile.ZipFile(path) as bundle:
            matches = [i for i in bundle.infolist() if i.filename == member]
            _require(len(matches) == 1, f"missing or duplicate roster member: {member}")
            _require(0 < matches[0].file_size <= MAX_SOURCE_BYTES, "roster member size is outside the bounded range")
            with bundle.open(matches[0]) as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
    else:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise PS3RosterConvertError(f"cannot open roster source read-only: {path}: {exc}") from exc
        try:
            info = os.fstat(descriptor)
            _require(stat.S_ISREG(info.st_mode), f"roster source is not a regular file: {path}")
            _require(0 < info.st_size <= MAX_SOURCE_BYTES, "roster source size is outside the bounded range")
            chunks = bytearray()
            while len(chunks) < info.st_size:
                block = os.read(descriptor, min(1024 * 1024, info.st_size - len(chunks)))
                _require(bool(block), f"short read from roster source: {path}")
                chunks.extend(block)
            data = bytes(chunks)
        finally:
            os.close(descriptor)
    _require(0 < len(data) <= MAX_SOURCE_BYTES, "roster source size is outside the bounded range")
    return data


# --------------------------------------------------------------------------
# Structure


@dataclass(frozen=True)
class TableSpan:
    index: int
    start: int
    count: int
    stride: int

    @property
    def end(self) -> int:
        return self.start + self.count * self.stride


@dataclass(frozen=True)
class Reference:
    field_offset: int
    target: int
    table: int
    column: int
    row: int

    @property
    def owner(self) -> str:
        return f"t{self.table}:{self.row}:+0x{self.column:X}"


@dataclass(frozen=True)
class Allocation:
    target: int
    text: str | None
    end: int
    reference_count: int

    @property
    def size(self) -> int:
        return self.end - self.target

    @property
    def odd(self) -> bool:
        return self.target % 2 == 1


@dataclass(frozen=True)
class RosterStructure:
    size: int
    tables: Mapping[int, TableSpan]
    arrays_end: int
    pool_start: int
    references: tuple[Reference, ...]
    allocations: Mapping[int, Allocation]
    interior: Mapping[int, int]
    skipped_tables: tuple[int, ...]

    @property
    def sorted_targets(self) -> list[int]:
        return sorted(self.allocations)


def _decode_text(data: bytes, target: int) -> tuple[str | None, int]:
    end = target
    limit = min(len(data) - 1, target + MAX_TEXT_BYTES)
    while end < limit and data[end:end + 2] != EMPTY_TEXT:
        end += 2
    if data[end:end + 2] != EMPTY_TEXT:
        return None, end
    try:
        return data[target:end].decode("utf-16-be"), end + 2
    except UnicodeDecodeError:
        return None, end + 2


def _table_spans(data: bytes) -> tuple[dict[int, TableSpan], tuple[int, ...]]:
    _require(len(data) >= ROOT_OFFSET + ROOT_PAIR_COUNT * 8 + 12, "roster root is truncated")
    for index, expected in enumerate(apf_roster.EXPECTED_COUNTS):
        _require(save_layout._root_count(data, index) == expected, f"root table {index} count changed")
    spans: dict[int, TableSpan] = {}
    skipped: list[int] = []
    for index, stride in TABLE_STRIDES.items():
        count = save_layout._root_count(data, index)
        if index in XBOX_ROOT_RUNTIME_TABLES:
            continue
        pointer_field = ROOT_OFFSET + index * 8 + 4
        if _stored(data, pointer_field) == 0:
            skipped.append(index)
            continue
        start = _target(data, pointer_field)
        _require(ROOT_OFFSET + ROOT_PAIR_COUNT * 8 <= start and start + count * stride <= len(data),
                 f"root table {index} resolves outside the roster")
        spans[index] = TableSpan(index, start, count, stride)
    try:
        layout = save_layout._table_layout(data)
    except (save_layout.SaveAppearanceError, ValueError) as exc:
        raise PS3RosterConvertError(str(exc)) from exc
    for index in (PALETTE_TABLE, SELECTOR_TABLE, CONFIG_TABLE):
        start, count, stride = layout[index]
        spans[index] = TableSpan(index, start, count, stride)
    packed_count = save_layout._root_count(data, PACKED_TABLE)
    spans[PACKED_TABLE] = TableSpan(PACKED_TABLE, spans[SELECTOR_TABLE].end, packed_count, 5)
    flag_count = save_layout._root_count(data, PALETTE_FLAG_TABLE)
    spans[PALETTE_FLAG_TABLE] = TableSpan(PALETTE_FLAG_TABLE, spans[PALETTE_TABLE].start - flag_count * 2, flag_count, 2)
    if 14 in spans:
        _require(spans[14].end == spans[PALETTE_FLAG_TABLE].start, "root tables 14 and 15 are not contiguous")
    ordered = [spans[i] for i in sorted(spans)]
    for previous, following in zip(ordered, ordered[1:]):
        _require(previous.end <= following.start, f"root tables {previous.index} and {following.index} overlap")
    return spans, tuple(skipped)


def inspect_structure(data: bytes) -> RosterStructure:
    """Resolve every string reference and allocation in a raw roster payload."""

    _require(isinstance(data, bytes), "roster payload must be immutable bytes")
    spans, skipped = _table_spans(data)
    arrays_end = _target(data, ARRAYS_END_FIELDS[0])
    _require(arrays_end == _target(data, ARRAYS_END_FIELDS[1]), "save array-end pointers disagree")
    pool_start = _target(data, POOL_FIELD)
    _require(0 < arrays_end <= pool_start < len(data), "string pool bounds are invalid")
    references: list[Reference] = []
    for index, (stride, columns) in STRING_TABLES.items():
        span = spans.get(index)
        if span is None:
            continue
        for row in range(span.count):
            record = span.start + row * stride
            for column in columns:
                field_offset = record + column
                stored = _stored(data, field_offset)
                if stored == 0:
                    continue
                target = field_offset + stored - 1
                _require(0 <= target < len(data) - 1, f"string pointer {index}:{row}:+0x{column:X} resolves outside the roster")
                references.append(Reference(field_offset, target, index, column, row))
    counts: dict[int, int] = {}
    for reference in references:
        counts[reference.target] = counts.get(reference.target, 0) + 1
    allocations: dict[int, Allocation] = {}
    for target, count in counts.items():
        text, end = _decode_text(data, target)
        allocations[target] = Allocation(target, text, end, count)
    return RosterStructure(len(data), spans, arrays_end, pool_start, tuple(references), allocations,
                           _damaged_allocations(allocations), skipped)


def _clean_text(text: str | None) -> bool:
    """True for text the game's serialiser could have written.

    A reference that lands one byte off the alignment of the string it reads
    decodes ASCII as U+xx00 code points (CJK/Hangul) and spaces as U+2000, so
    any code point at or above U+2C00 or a non-printable, non-newline
    character marks the read as garbage rather than a name or biography.
    """

    return text is not None and all(
        (character.isprintable() or character.isspace()) and ord(character) < 0x2C00
        for character in text
    )


def _damaged_allocations(allocations: Mapping[int, Allocation]) -> dict[int, int]:
    """Resolve nested allocations into ``damaged target -> allocation it conflicts with``.

    The Xbox 360 fixture and the stock PS3 save contain no nested allocations
    at all, so every nesting is editor damage.  When an outer allocation reads
    garbage across a clean inner one, the outer reference is the stale one;
    otherwise the inner reference (a suffix of a clean string) is stale.
    """

    starts = sorted(allocations)

    def enclosing(target: int, skip: set[int]) -> list[int]:
        found: list[int] = []
        position = bisect.bisect_left(starts, target)
        for previous in range(position - 1, max(-1, position - 512), -1):
            candidate = starts[previous]
            # An empty allocation is two terminator bytes; it has no content a
            # later string could be a suffix of, so it never encloses anything.
            if candidate in skip or allocations[candidate].text == "":
                continue
            if candidate < target < allocations[candidate].end:
                found.append(candidate)
        return found

    garbage_outers: set[int] = set()
    for target in starts:
        for outer in enclosing(target, set()):
            if not _clean_text(allocations[outer].text) and _clean_text(allocations[target].text):
                garbage_outers.add(outer)
    damaged: dict[int, int] = {}
    for outer in garbage_outers:
        inner = next((t for t in starts if outer < t < allocations[outer].end and t not in garbage_outers), outer)
        damaged[outer] = inner
    for target in starts:
        if target in damaged:
            continue
        outers = enclosing(target, garbage_outers)
        if outers:
            damaged[target] = outers[0]
    return damaged


def _palette_votes(data: bytes, palette: TableSpan) -> tuple[int, int]:
    alpha_first = alpha_last = 0
    for row in range(palette.count):
        record = palette.start + row * palette.stride
        for colour in range(PALETTE_COLOURS):
            word = data[record + colour * 4: record + colour * 4 + 4]
            if word[0] == 0xFF and word[3] != 0xFF:
                alpha_first += 1
            elif word[3] == 0xFF and word[0] != 0xFF:
                alpha_last += 1
    return alpha_first, alpha_last


def detect_platform(data: bytes, structure: RosterStructure | None = None) -> str:
    """Vote on the palette alpha position; ambiguous or mixed files are ``unknown``."""

    structure = structure or inspect_structure(data)
    alpha_first, alpha_last = _palette_votes(data, structure.tables[PALETTE_TABLE])
    if alpha_last and not alpha_first:
        return PLATFORM_PS3
    if alpha_first and not alpha_last:
        return PLATFORM_XBOX360
    return PLATFORM_UNKNOWN


# --------------------------------------------------------------------------
# Conversion


@dataclass
class _Edits:
    output: bytearray
    spans: dict[tuple[int, int], str] = field(default_factory=dict)

    def write(self, offset: int, payload: bytes, reason: str) -> None:
        self.output[offset:offset + len(payload)] = payload
        self.spans[(offset, offset + len(payload))] = reason


def _canonical_empty(structure: RosterStructure) -> int | None:
    best: tuple[int, int] | None = None
    for target, allocation in structure.allocations.items():
        if allocation.text == "" and not allocation.odd and target not in structure.interior and target >= structure.pool_start:
            key = (allocation.reference_count, -target)
            if best is None or key > best:
                best = key
                chosen = target
    return None if best is None else chosen


def _free_gap(data: bytes, structure: RosterStructure, reserved: list[tuple[int, int]], size: int) -> int:
    """Find an even-aligned run of zero bytes inside the pool that no allocation touches."""

    busy = sorted([(a.target if not a.odd else a.target, a.end) for a in structure.allocations.values()] + reserved)
    cursor = (structure.pool_start + 1) & ~1
    limit = min(len(data), USER_REGION) if len(data) == ROSTER_SIZE else len(data)
    for start, end in busy + [(limit, limit)]:
        if start - cursor >= size and not any(data[cursor:cursor + size]):
            return cursor
        cursor = max(cursor, (end + 1) & ~1)
    raise PS3RosterConvertError("no free even-aligned pool space for relocated strings")


def team_appearance(data: bytes, structure: RosterStructure | None = None) -> list[dict]:
    """Resolve both 14-selector banks, including the 11 known asset selectors.

    USERDATA and raw ROS use the same one-based self-relative graph. Runtime
    root words for tables 16/17 are not file pointers; _table_spans bounds them
    from the adjacent config table, as the Xbox appearance reader does.
    """
    structure = structure or inspect_structure(data)
    teams = structure.tables[TEAM_TABLE]
    configs = structure.tables[CONFIG_TABLE]
    selectors = structure.tables[SELECTOR_TABLE]
    palettes = structure.tables[PALETTE_TABLE]

    def resolve(field: int, table: TableSpan) -> int:
        _require(_stored(data, field) != 0, f"null appearance pointer at {field:#x}")
        target = _target(data, field)
        _require(table.start <= target < table.end and (target - table.start) % table.stride == 0,
                 f"appearance pointer at {field:#x} is outside/aligned incorrectly for table {table.index}")
        return target

    result = []
    families = {2: "glove", 3: "helmet", 4: "jersey", 5: "logo", 6: "textlogo",
                7: "font", 8: "number", 9: "pants", 10: "shoe", 11: "shoulder", 12: "sock"}
    for team in range(teams.count):
        config = resolve(teams.start + team * teams.stride + 0xBC, configs)
        banks = []
        for bank in range(2):
            slots = []
            for slot in range(14):
                offset = resolve(config + (bank * 14 + slot) * 4, selectors)
                slots.append({"slot": slot, "family": families.get(slot, "unresolved"),
                              "offset": offset, "asset_index": data[offset],
                              "record_hex": data[offset:offset + 8].hex()})
            palette = resolve(config + 0x70 + bank * 4, palettes)
            banks.append({"bank": bank, "selectors": slots, "palette_offset": palette,
                          "palette_sha256": _sha256(data[palette:palette + palettes.stride])})
        result.append({"team_index": team, "config_offset": config, "banks": banks})
    return result


def _retain_appearance(edits: _Edits, source: bytes, baseline: bytes) -> None:
    """Copy appearance values through each roster's graph, preserving pointers.

    Conflicting shared destinations are refused before export. No team strings,
    roster memberships, book assignments or opaque config words are copied.
    """
    wanted = team_appearance(baseline)
    target = team_appearance(source)
    source_tables, _ = _table_spans(source)
    base_tables, _ = _table_spans(baseline)
    writes: dict[int, int] = {}

    def copy(dst: int, src: int, count: int) -> None:
        for i in range(count):
            value = baseline[src + i]
            _require(dst + i not in writes or writes[dst + i] == value,
                     "shared team appearance destination requires conflicting values")
            writes[dst + i] = value

    for old, new in zip(wanted, target):
        for ob, nb in zip(old["banks"], new["banks"]):
            for oslot, nslot in zip(ob["selectors"], nb["selectors"]):
                copy(nslot["offset"], oslot["offset"], 8)
            copy(nb["palette_offset"], ob["palette_offset"], 0x30)
            oi = (ob["palette_offset"] - base_tables[PALETTE_TABLE].start) // 0x30
            ni = (nb["palette_offset"] - source_tables[PALETTE_TABLE].start) // 0x30
            copy(source_tables[PALETTE_FLAG_TABLE].start + ni * 2,
                 base_tables[PALETTE_FLAG_TABLE].start + oi * 2, 2)
    for offset, value in sorted(writes.items()):
        edits.write(offset, bytes((value,)), "appearance retained from Xbox roster")


def _appearance_receipt(before: bytes, after: bytes) -> list[dict]:
    result = []
    for old, new in zip(team_appearance(before), team_appearance(after)):
        changes = []
        for ob, nb in zip(old["banks"], new["banks"]):
            for a, b in zip(ob["selectors"], nb["selectors"]):
                changes.append({"bank": ob["bank"], "slot": a["slot"], "family": a["family"],
                                "before": a["asset_index"], "after": b["asset_index"],
                                "record_changed": a["record_hex"] != b["record_hex"]})
        result.append({"team_index": old["team_index"], "selectors": changes,
                       "selector_changes": sum(x["record_changed"] for x in changes),
                       "palette_before_sha256": [b["palette_sha256"] for b in old["banks"]],
                       "palette_after_sha256": [b["palette_sha256"] for b in new["banks"]]})
    return result


def convert(data: bytes, *, apply_team_appearance: bool = True,
            xbox_appearance: bytes | None = None) -> tuple[bytes, dict[str, Any]]:
    """Convert one PS3 roster payload; returns the Xbox-layout payload and its receipt."""

    _require(len(data) == ROSTER_SIZE, f"roster payload is {len(data)} bytes, expected {ROSTER_SIZE}")
    _require(data[:4] not in players_reader.stfs_reader.STFS_MAGICS, "an STFS container is already an Xbox 360 save")
    structure = inspect_structure(data)
    platform = detect_platform(data, structure)
    _require(platform != PLATFORM_XBOX360, "this roster already uses the Xbox 360 layout (palette alpha first); nothing to convert")
    _require(platform == PLATFORM_PS3, "cannot tell the roster platform from its palette colours; refusing to guess")
    _require(type(apply_team_appearance) is bool, "apply_team_appearance must be boolean")
    _require(apply_team_appearance or xbox_appearance is not None,
             "Choose an Xbox roster whose appearance should be retained, or apply the PS3 appearance")
    source_appearance = team_appearance(data, structure)
    if xbox_appearance is not None:
        _require(detect_platform(xbox_appearance) == PLATFORM_XBOX360,
                 "Appearance baseline must be a raw Xbox 360 roster")
        team_appearance(xbox_appearance)
    undecodable = [t for t, a in structure.allocations.items() if a.text is None and t not in structure.interior]
    _require(not undecodable, f"{len(undecodable)} referenced strings have no UTF-16BE terminator; refusing")
    garbage_outers = sum(1 for t, other in structure.interior.items() if t < other)
    edits = _Edits(bytearray(data))
    remap: dict[int, int] = {}
    receipt_counts: dict[str, int] = {}

    # 1. Canonical empty string, shared the way the game's serialiser interns it.
    empty = _canonical_empty(structure)
    reserved: list[tuple[int, int]] = []
    if empty is None:
        empty = _free_gap(data, structure, reserved, 2)
        reserved.append((empty, empty + 2))
        receipt_counts["empty_allocation_created"] = 1

    # 2. Classify every allocation.
    interior_targets = set(structure.interior)
    odd_runs: list[dict[str, Any]] = []
    below_pool = [t for t in structure.allocations if t < structure.pool_start]
    empty_targets = [t for t, a in structure.allocations.items() if a.text == "" and t != empty]
    garbage_targets = [t for t, a in structure.allocations.items()
                       if not _clean_text(a.text) and t not in interior_targets and t not in below_pool]
    for target in below_pool + list(interior_targets) + empty_targets + garbage_targets:
        remap[target] = empty
    odd_live = sorted(t for t, a in structure.allocations.items() if a.odd and t not in remap)
    runs: list[list[int]] = []
    for target in odd_live:
        end = structure.allocations[target].end
        if runs and runs[-1][1] == target:
            runs[-1][1] = end
            runs[-1][2] += 1
        else:
            runs.append([target, end, 1])
    shifted = relocated = 0
    for start, end, strings in runs:
        run = bytes(data[start:end])
        guard_free = (
            start - 1 >= structure.pool_start
            and data[start - 1] == 0
            and data[start] == 0
            and (start - 1) not in structure.allocations
            and not any(a.target < start - 1 < a.end for a in structure.allocations.values() if a.target not in remap)
        )
        if guard_free:
            destination = start - 1
            edits.write(destination, run, "odd string run shifted one byte earlier")
            edits.output[end - 1] = 0
            shifted += 1
            method = "shift"
        else:
            destination = _free_gap(data, structure, reserved, len(run))
            reserved.append((destination, destination + len(run)))
            edits.write(destination, run, "odd string run relocated into free pool space")
            edits.write(start, bytes(len(run)), "vacated odd string run")
            relocated += 1
            method = "relocate"
        for target in odd_live:
            if start <= target < end:
                remap[target] = destination + (target - start)
        odd_runs.append({"source_offset": start, "bytes": len(run), "strings": strings,
                         "destination_offset": destination, "method": method})

    # 3. Repoint every reference whose target moved or was canonicalised.
    repointed: dict[str, int] = {}
    for reference in structure.references:
        if reference.target not in remap:
            continue
        new_target = remap[reference.target]
        if new_target == reference.target:
            continue
        edits.write(reference.field_offset, _pointer_bytes(reference.field_offset, new_target), "string pointer repointed")
        kind = ("below_pool" if reference.target in below_pool else
                "interior" if reference.target in interior_targets else
                "empty" if reference.target in empty_targets else
                "garbage" if reference.target in garbage_targets else "odd")
        repointed[kind] = repointed.get(kind, 0) + 1

    # 4. Palette colours RR GG BB FF -> FF RR GG BB.
    palette = structure.tables[PALETTE_TABLE]
    rotated = 0
    for row in range(palette.count):
        record = palette.start + row * palette.stride
        for colour in range(PALETTE_COLOURS):
            offset = record + colour * 4
            word = data[offset:offset + 4]
            edits.write(offset, word[3:4] + word[0:3], "palette colour rotated to ARGB")
            rotated += 1

    # 5. Runtime words the way the Xbox fixtures carry them.
    for index in XBOX_ROOT_RUNTIME_TABLES:
        span = structure.tables[index]
        value = (XBOX_ROOT_RUNTIME_BASE + span.start) & 0xFFFFFFFF
        edits.write(ROOT_OFFSET + index * 8 + 4, struct.pack(">I", value), f"root {index} runtime address")
    block_start = RUNTIME_BLOCK_OFFSET
    _require(not any(data[block_start - RUNTIME_BLOCK_GUARD:block_start]) and not any(
        data[block_start + RUNTIME_BLOCK_WORDS * 4:block_start + RUNTIME_BLOCK_WORDS * 4 + RUNTIME_BLOCK_GUARD]),
        "runtime block after the string pool is not where this layout keeps it")
    _require(all(a.end <= block_start for a in structure.allocations.values()), "a string allocation overlaps the runtime block")
    edits.write(block_start, struct.pack(">8I", *XBOX_RUNTIME_BLOCK), "post-pool runtime block")
    magics = [i for i in range(USER_REGION, len(data) - 3) if data[i:i + 4] == BANK_MAGIC]
    _require(len(magics) == BANK_COUNT and all(b - a == BANK_STRIDE for a, b in zip(magics, magics[1:])),
             "user playbook banks are not the five BLPS banks this layout keeps")
    for magic in magics:
        for relative, value in zip(BANK_WORD_OFFSETS, XBOX_BANK_WORDS):
            edits.write(magic + relative, struct.pack(">I", value), "user book bank runtime word")
    edits.write(TRAILING_BANK_WORD, struct.pack(">I", XBOX_BANK_WORDS[0]), "trailing bank header runtime word")

    if not apply_team_appearance:
        _retain_appearance(edits, data, xbox_appearance)
    output = bytes(edits.output)
    expected_appearance = source_appearance if apply_team_appearance else team_appearance(xbox_appearance)
    actual_appearance = team_appearance(output)
    for expected, actual in zip(expected_appearance, actual_appearance):
        for eb, ab in zip(expected["banks"], actual["banks"]):
            _require([x["record_hex"] for x in eb["selectors"]] == [x["record_hex"] for x in ab["selectors"]],
                     "team appearance selectors changed during conversion")
            if not apply_team_appearance:
                _require(eb["palette_sha256"] == ab["palette_sha256"], "retained palette differs after reparse")
    changed = [i for i in range(len(data)) if data[i] != output[i]]
    allowed = [False] * len(data)
    for (start, end) in edits.spans:
        for position in range(start, end):
            allowed[position] = True
    _require(all(allowed[i] for i in changed), "conversion changed a byte outside its declared spans")
    verification = verify_converted(output)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "source": {"sha256": _sha256(data), "size": len(data), "platform": platform},
        "output": {"sha256": _sha256(output), "size": len(output), "platform": PLATFORM_XBOX360,
                   "changed_byte_count": len(changed)},
        "counts": {
            "players": structure.tables[PLAYER_TABLE].count,
            "teams": structure.tables[TEAM_TABLE].count,
            "appearance_teams": len(actual_appearance),
            "appearance_applied_from_ps3": apply_team_appearance,
            "team_memberships": verification["team_memberships"],
            "playbook_labels": verification["playbook_labels"],
            "string_references": len(structure.references),
            "string_allocations": len(structure.allocations),
            "odd_references": sum(1 for r in structure.references if r.target % 2),
            "odd_allocations": sum(1 for a in structure.allocations.values() if a.odd),
            "odd_runs": len(runs),
            "odd_run_bytes": sum(end - start for start, end, _n in runs),
            "odd_runs_shifted": shifted,
            "odd_runs_relocated": relocated,
            "interior_references": sum(1 for r in structure.references if r.target in interior_targets),
            "interior_allocations": len(interior_targets),
            "interior_allocations_garbage_outer": garbage_outers,
            "below_pool_references": sum(1 for r in structure.references if r.target in below_pool),
            "garbage_references": repointed.get("garbage", 0),
            "garbage_allocations": len(garbage_targets),
            "empty_references_canonicalised": repointed.get("empty", 0),
            "references_repointed": sum(repointed.values()),
            "palette_colours_rotated": rotated,
            "root_runtime_fields_rewritten": len(XBOX_ROOT_RUNTIME_TABLES),
            "runtime_block_words_rewritten": RUNTIME_BLOCK_WORDS,
            "bank_runtime_words_rewritten": len(magics) * len(BANK_WORD_OFFSETS) + 1,
            "skipped_tables": list(structure.skipped_tables),
            **receipt_counts,
        },
        "team_appearance": {
            "applied_from_ps3": apply_team_appearance,
            "baseline_sha256": _sha256(xbox_appearance) if xbox_appearance is not None else None,
            "teams": _appearance_receipt(xbox_appearance if xbox_appearance is not None else data, output),
            "same_selector_layout": True, "selectors_reparsed": True,
            "texture_payloads_imported": False,
        },
        "repointed_by_kind": repointed,
        "canonical_empty_offset": empty,
        "odd_runs": odd_runs,
        "interior_references_by_table": _interior_by_table(structure),
        "verification": verification,
        "claims": {
            "every_player_team_label_and_user_bank_kept": True,
            "strict_readers_reparsed_output": True,
            "container_written": False,
            "runtime_in_game_proved": False,
        },
        "runtime": RUNTIME_STATUS,
    }
    return output, receipt


def _interior_by_table(structure: RosterStructure) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reference in structure.references:
        if reference.target in structure.interior:
            key = f"t{reference.table}+0x{reference.column:X}"
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def verify_converted(output: bytes) -> dict[str, Any]:
    """Re-parse a converted payload with every strict reader the studio owns."""

    structure = inspect_structure(output)
    _require(detect_platform(output, structure) == PLATFORM_XBOX360, "converted roster is not Xbox 360 layout")
    odd = [t for t in structure.allocations if t % 2]
    _require(not odd, f"converted roster still has {len(odd)} odd string allocations")
    _require(not structure.interior, f"converted roster still has {len(structure.interior)} interior references")
    _require(all(t >= structure.pool_start for t in structure.allocations), "converted roster references text below the pool")
    _require(all(a.text is not None for a in structure.allocations.values()), "converted roster has undecodable text")
    _require(all(_clean_text(a.text) for a in structure.allocations.values()), "converted roster still references misaligned text")
    ordered = structure.sorted_targets
    for first, second in zip(ordered, ordered[1:]):
        _require(structure.allocations[first].end <= second, "converted string allocations overlap")
    try:
        document = players_reader.inspect_bytes(output)
    except players_reader.SaveRosterPlayerError as exc:
        raise PS3RosterConvertError(f"player reader refused the converted roster: {exc}") from exc
    for player_index in range(players_reader.PLAYER_COUNT):
        document.player_text_values(player_index)
    try:
        labels = labels_reader.parse_save(output)
    except labels_reader.SaveError as exc:
        raise PS3RosterConvertError(f"playbook label reader refused the converted roster: {exc}") from exc
    team_span = structure.tables[TEAM_TABLE]
    team_strings = 0
    try:
        save_layout._table_layout(output)
        for row in range(team_span.count):
            for column in STRING_TABLES[TEAM_TABLE][1]:
                field_offset = team_span.start + row * team_span.stride + column
                if _stored(output, field_offset) == 0:
                    continue
                save_layout._decode_utf16be(output, save_layout._relative_target(output, field_offset, f"team {row} text"), f"team {row} text")
                team_strings += 1
    except (save_layout.SaveAppearanceError, ValueError) as exc:
        raise PS3RosterConvertError(f"team reader refused the converted roster: {exc}") from exc
    # The custom-team appearance reader additionally requires the stock user
    # slot categories (content the roster author may have changed), so its
    # verdict is recorded, never gated on.
    try:
        save_layout.parse_save(output)
        appearance_verdict = "accepted"
    except (save_layout.SaveAppearanceError, ValueError) as exc:
        appearance_verdict = f"refused for a content reason: {exc}"
    for index in XBOX_ROOT_RUNTIME_TABLES:
        expected = (XBOX_ROOT_RUNTIME_BASE + structure.tables[index].start) & 0xFFFFFFFF
        _require(_be32(output, ROOT_OFFSET + index * 8 + 4) == expected, f"root {index} runtime address differs from the Xbox rule")
    return {
        "players_parsed": players_reader.PLAYER_COUNT,
        "player_text_allocations": len(document.text_allocations),
        "team_memberships": len(document.memberships),
        "playbook_labels": len(labels.playbooks),
        "team_strings_decoded": team_strings,
        "custom_team_appearance_reader": appearance_verdict,
        "string_references": len(structure.references),
        "string_allocations": len(structure.allocations),
    }


# --------------------------------------------------------------------------
# Files


@dataclass(frozen=True)
class ConversionReceipt:
    source: Path
    member: str | None
    output: Path
    receipt_path: Path
    source_sha256: str
    output_sha256: str
    changed_byte_count: int
    counts: Mapping[str, Any]
    runtime: str = RUNTIME_STATUS


def _reserve(path: Path) -> int:
    _require(path.parent.is_dir(), f"destination directory does not exist: {path.parent}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags, platform_compat.private_file_mode())
    except OSError as exc:
        raise PS3RosterConvertError(f"refusing to overwrite destination: {path}: {exc}") from exc


def _write_all(descriptor: int, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        count = os.write(descriptor, payload[position:])
        _require(count > 0, "short write while creating the converted roster")
        position += count
    os.fsync(descriptor)


def receipt_path_for(output: Path) -> Path:
    return output.with_name(f"{output.name}.ps3-import.json")


def write_conversion(source: Path, output: Path, *, member: str | None = None, receipt_path: Path | None = None,
                     apply_team_appearance: bool = True, xbox_appearance: Path | None = None) -> ConversionReceipt:
    """Convert ``source`` (raw or ZIP member) into a new ``output`` plus a JSON receipt."""

    source = Path(source)
    output = Path(output)
    receipt_file = Path(receipt_path) if receipt_path is not None else receipt_path_for(output)
    _require(output != source and receipt_file not in (source, output), "output, receipt and source paths must differ")
    if member is None and zipfile.is_zipfile(source):
        member = find_roster_member(source)
    data = read_source(source, member)
    payload, receipt = convert(data, apply_team_appearance=apply_team_appearance,
                               xbox_appearance=read_source(xbox_appearance) if xbox_appearance is not None else None)
    receipt["source"]["path"] = str(source)
    receipt["source"]["member"] = member
    receipt["output"]["path"] = str(output)
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output_fd = receipt_fd = -1
    created: list[Path] = []
    try:
        output_fd = _reserve(output)
        created.append(output)
        receipt_fd = _reserve(receipt_file)
        created.append(receipt_file)
        _write_all(output_fd, payload)
        _write_all(receipt_fd, receipt_bytes)
    except Exception:
        for descriptor in (output_fd, receipt_fd):
            if descriptor >= 0:
                os.close(descriptor)
        output_fd = receipt_fd = -1
        for path in created:
            path.unlink(missing_ok=True)
        raise
    finally:
        for descriptor in (output_fd, receipt_fd):
            if descriptor >= 0:
                os.close(descriptor)
    written = read_source(output)
    _require(_sha256(written) == receipt["output"]["sha256"], "converted roster on disk differs from the verified payload")
    verify_converted(written)
    return ConversionReceipt(source, member, output, receipt_file, receipt["source"]["sha256"],
                             receipt["output"]["sha256"], receipt["output"]["changed_byte_count"], receipt["counts"])


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", type=Path, help="PS3 save ZIP or its extracted USERDATA")
    parser.add_argument("output", type=Path, help="new raw Xbox 360 Roster.ROS to create")
    parser.add_argument("--member", help="ZIP member holding the roster USERDATA")
    parser.add_argument("--receipt", type=Path, help="receipt path (default: <output>.ps3-import.json)")
    args = parser.parse_args(argv)
    try:
        result = write_conversion(args.source, args.output, member=args.member, receipt_path=args.receipt)
    except PS3RosterConvertError as exc:
        print(f"error: {exc}")
        return 2
    counts = result.counts
    print(f"APF_PS3_ROSTER_CONVERT_PASS players={counts['players']} teams={counts['teams']} "
          f"odd_runs={counts['odd_runs']} repointed={counts['references_repointed']} "
          f"colours={counts['palette_colours_rotated']} changed_bytes={result.changed_byte_count}")
    print(result.runtime)
    return 0


__all__ = [
    "Allocation", "ConversionReceipt", "PLATFORM_PS3", "PLATFORM_UNKNOWN", "PLATFORM_XBOX360",
    "PS3RosterConvertError", "Reference", "RosterStructure", "RUNTIME_STATUS", "SCHEMA",
    "TableSpan", "XBOX_ROOT_RUNTIME_BASE", "convert", "detect_platform", "find_roster_member",
    "inspect_structure", "read_source", "receipt_path_for", "verify_converted", "write_conversion",
]


if __name__ == "__main__":
    raise SystemExit(main())
