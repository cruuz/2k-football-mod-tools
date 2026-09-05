"""Lossless version-0 save / version-17 disc ROST codec.

The runtime save is NOT a disc body with its version changed.  A resource has
a 0x20 outer wrapper; its inner header puts the root at +0x20 (version 0) or
+0x40 (version 17).  All relocated pointers are field-local signed offsets:
target = field + value - 1.  The declared resource length bounds every read,
even when a franchise or other container has an opaque suffix.

Addresses establishing the contract: retail 0xC2040 (resource framing),
0xC0500/0xC0730 (root relocation), 0x2418C0/0x241A20 (500-byte teams).
This module never changes headers, EXTRA, or signatures.  Signing remains the
existing SaveContainer's responsibility after to_bytes().  No file writer or
XBE patch is involved.  Unknown bytes remain verbatim, including arena slack.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Mapping

from . import nfl2k5_roster_records as records


class SaveRostError(ValueError):
    """Unknown, ambiguous, truncated, or structurally unsafe ROST data."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SaveRostError(message)


@dataclass(frozen=True)
class Layout:
    version: int
    wrapper: int | None
    preamble: int
    root: int
    end: int

    @property
    def arena_size(self) -> int:
        return self.end - self.root


@dataclass(frozen=True)
class Table:
    name: str
    count: int
    offset: int | None
    stride: int


# Root offsets and strides proved by the retail relocation routines.  Unknown
# root fields are preserved, not assigned invented record layouts.
TABLES = (
    ('primary', 0x00, 0x04, 0x54, 8000),
    ('secondary', 0x08, 0x0C, 0x54, 8000),
    ('stadiums', 0x10, 0x14, 0x80, 1024),
    ('teams', 0x18, 0x1C, 0x1F4, 128),
    ('colleges', 0x20, 0x24, 8, 4000),
    ('coaches', 0x30, 0x34, 0xA8, 1024),
    ('free_agents', 0x38, 0x3C, 4, 8000),
    ('team_labels', 0x48, 0x4C, 8, 1024),
    ('generated_names', 0x50, 0x54, 8, 16000),
    ('historic_descriptors', 0x58, 0x5C, 16, 4000),
)


@dataclass(frozen=True)
class Player:
    pool: str
    index: int
    offset: int
    first: str
    last: str
    record: records.PlayerRecord

    @property
    def key(self) -> tuple[str, int]:
        return self.pool, self.index


@dataclass(frozen=True)
class Team:
    index: int
    offset: int
    asset_id: int
    abbreviation: str
    player_offsets: tuple[int, ...]


class SaveRost:
    """Decoded records with an exact-size, copy-only serializer.

    Use edit_player() for typed edits, or read players/tables/history_words.
    to_bytes() emits the complete original payload, including opaque prefix
    and suffix.  Direct mutations of record pointer fields are refused.
    This is not a drop-in RosterDocument GUI adapter (see wiring notes).
    """

    def __init__(self, payload: bytes, layout: Layout):
        self.original = bytes(payload)
        self.layout = layout
        self.tables: dict[str, Table] = {}
        self.players: list[Player] = []
        self.teams: list[Team] = []
        self.history_words: dict[tuple[str, int], tuple[int, ...]] = {}
        self.history_offsets: dict[tuple[str, int], int | None] = {}
        self._parse()

    def span(self, offset: int, size: int, label: str) -> None:
        _require(size >= 0 and self.layout.root + 0x70 <= offset
                 and offset + size <= self.layout.end, f'{label}: range outside ROST arena')

    def u32(self, offset: int) -> int:
        _require(self.layout.root <= offset <= self.layout.end - 4, 'word outside ROST arena')
        return struct.unpack_from('<I', self.original, offset)[0]

    def rel(self, field: int, *, size: int = 1, label: str = 'pointer') -> int | None:
        value = self.u32(field)
        if not value:
            return None
        signed = value if value < 0x80000000 else value - 0x100000000
        target = field + signed - 1
        self.span(target, size, label)
        return target

    def string(self, field: int) -> str:
        target = self.rel(field, size=2, label='UTF-16 pointer')
        if target is None:
            return ''
        _require(target % 2 == 0, 'unaligned UTF-16 string')
        end = target
        # Labels are short; a corrupt pointer must not scan arbitrary megabytes.
        limit = min(self.layout.end, target + 8192)
        while end + 2 <= limit:
            if self.original[end:end + 2] == b'\0\0':
                try:
                    return self.original[target:end].decode('utf-16-le')
                except UnicodeDecodeError as exc:
                    raise SaveRostError('invalid UTF-16 string') from exc
            end += 2
        raise SaveRostError('unterminated UTF-16 string')

    def _parse(self) -> None:
        root = self.layout.root
        occupied = []
        for name, count_field, pointer_field, stride, maximum in TABLES:
            count = self.u32(root + count_field)
            _require(count <= maximum, f'{name}: implausible count {count}')
            target = self.rel(root + pointer_field, size=count * stride, label=name)
            _require(count == 0 or target is not None, f'{name}: null table with nonzero count')
            if count:
                assert target is not None
                occupied.append((target, target + count * stride, name))
            self.tables[name] = Table(name, count, target, stride)
        _require(self.tables['primary'].count > 0 and self.tables['teams'].count > 0,
                 'primary players and teams are required')
        occupied.sort()
        for left, right in zip(occupied, occupied[1:]):
            _require(left[1] <= right[0], f'overlapping {left[2]}/{right[2]} tables')

        colleges = self.tables['colleges']
        college_records = set()
        if colleges.offset is not None:
            for i in range(colleges.count):
                off = colleges.offset + i * colleges.stride
                college_records.add(off)
                self.string(off)
        for pool in ('primary', 'secondary'):
            table = self.tables[pool]
            if table.offset is None:
                continue
            for index in range(table.count):
                off = table.offset + index * table.stride
                college = self.rel(off, size=8, label='player college')
                _require(college is None or college in college_records, 'player college is not a college record')
                self.players.append(Player(pool, index, off, self.string(off + 0x10),
                                           self.string(off + 0x14), records.PlayerRecord.decode(
                                               self.original[off:off + records.PLAYER_SIZE])))
        self.by_key = {p.key: p for p in self.players}
        offsets = {p.offset for p in self.players}
        table = self.tables['teams']
        assert table.offset is not None
        for index in range(table.count):
            off = table.offset + index * table.stride
            count = self.original[off + 0x11C]
            _require(count <= 65, f'team {index}: roster count exceeds 65')
            slots = []
            # Every physical slot participates in retail relocation, even if it
            # is not active.  Preserve valid non-null unused slots, don't hide them.
            for slot in range(65):
                target = self.rel(off + slot * 4, size=0x54, label='team player')
                _require(target is None or target in offsets, f'team {index}: invalid player reference')
                if slot < count:
                    _require(target is not None, f'team {index}: null active player')
                    slots.append(target)
            for field in (0x104, 0x108, 0x10C, 0x138, 0x13C):
                self.string(off + field)
            self.teams.append(Team(index, off, struct.unpack_from('<H', self.original, off + 0x118)[0],
                                   self.string(off + 0x108), tuple(slots)))
        agents = self.tables['free_agents']
        if agents.offset is not None:
            for i in range(agents.count):
                target = self.rel(agents.offset + i * 4, size=0x54, label='free agent')
                _require(target in offsets, 'free agent is not a player record')

        self.pool_used = self.u32(root + 0x40)
        self.pool_capacity = 50000 if table.count >= 35 else 20000
        _require(self.pool_used <= self.pool_capacity, 'history used count exceeds retail capacity')
        self.pool = self.rel(root + 0x44, size=self.pool_used * 4, label='history pool')
        _require(self.pool is not None or self.pool_used == 0, 'null used history pool')
        cache: dict[int, tuple[int, ...]] = {}
        total_words = 0
        for player in self.players:
            start = self.rel(player.offset + 0x2C, size=4, label='history stream')
            self.history_offsets[player.key] = start
            if start is None:
                self.history_words[player.key] = ()
                continue
            _require(self.pool is not None and self.pool <= start < self.pool + self.pool_used * 4
                     and (start - self.pool) % 4 == 0, 'history stream outside used pool')
            if start not in cache:
                words = []
                at = start
                while at < self.pool + self.pool_used * 4:
                    word = self.u32(at)
                    words.append(word)
                    at += 4
                    total_words += 1
                    _require(total_words <= self.pool_capacity, 'overlapping or excessive history streams')
                    if word & 0x80000000:
                        break
                _require(bool(words[-1] & 0x80000000), 'unterminated history stream')
                cache[start] = tuple(words)
            self.history_words[player.key] = cache[start]
        if self.pool is not None and self.pool_used:
            for start, end, label in occupied:
                _require(end <= self.pool or start >= self.pool + self.pool_used * 4,
                         f'history pool overlaps {label}')

    def edit_player(self, pool: str, index: int, changes: Mapping[str, int]) -> None:
        """Validate the whole edit before changing a single record field."""
        try:
            player = self.by_key[pool, index]
        except KeyError as exc:
            raise SaveRostError(f'unknown player {pool}/{index}') from exc
        trial = records.PlayerRecord.decode(player.record.encode())
        for name, value in changes.items():
            _require(name not in records.POINTER_FIELDS, f'{name}: pointer edits require a typed relocation writer')
            _require(type(value) is int, f'{name}: expected integer')
            try:
                trial.set(name, value)
            except records.RosterRecordError as exc:
                raise SaveRostError(str(exc)) from exc
        player.record.values.clear()
        player.record.values.update(trial.values)

    def to_bytes(self) -> bytes:
        out = bytearray(self.original)
        for player in self.players:
            encoded = player.record.encode()
            before = records.PlayerRecord.decode(self.original[player.offset:player.offset + 0x54])
            for name in records.POINTER_FIELDS:
                _require(player.record.values[name] == before.values[name], f'{name}: direct pointer mutation refused')
            out[player.offset:player.offset + 0x54] = encoded
        _require(len(out) == len(self.original), 'save length changed')
        return bytes(out)

    def summary(self) -> dict[str, object]:
        return {'version': self.layout.version, 'root': self.layout.root,
                'preamble': self.layout.preamble, 'wrapper': self.layout.wrapper,
                'end': self.layout.end, 'arena_size': self.layout.arena_size,
                'players': len(self.players), 'teams': len(self.teams),
                'history_used': self.pool_used, 'history_capacity': self.pool_capacity}


def decode(payload: bytes | bytearray, *, preamble: int | None = None) -> SaveRost:
    """Find exactly one supported framed ROST, or use an explicit preamble.

    Bare bodies are accepted only at offset zero and only at their exact known
    size.  Wrapped resources may have arbitrary opaque prefix/suffix bytes.
    Candidate headers that fail structural validation do not become records.
    """
    data = bytes(payload)
    _require(len(data) <= 32 * 1024 * 1024, 'payload exceeds 32 MiB codec limit')
    candidates = []
    failures = []
    if preamble is not None:
        starts = [preamble]
    else:
        starts = []
        point = data.find(b'ROST', 0, min(len(data), 0x10000))
        while point >= 0:
            if point >= 12:
                starts.append(point - 12)
            point = data.find(b'ROST', point + 1, min(len(data), 0x10000))
    for base in starts:
        try:
            _require(0 <= base <= len(data) - 0x20, 'truncated ROST preamble')
            _require(data[base + 12:base + 16] == b'ROST', 'ROST inner magic missing')
            version, relative = struct.unpack_from('<Ii', data, base + 16)
            _require(version in (0, 17), f'unsupported ROST version {version}')
            delta = 0x20 if version == 0 else 0x40
            root = base + 0x14 + relative - 1
            _require(root == base + delta, f'version {version}: unexpected root offset')
            if base >= 0x20 and data[base - 0x20:base - 0x1C] == b'ROST':
                wrapper = base - 0x20
                declared = struct.unpack_from('<I', data, wrapper + 4)[0]
                end = base + declared
                _require(delta + 0x70 <= declared <= 16 * 1024 * 1024, 'implausible resource length')
                _require(end <= len(data), 'truncated declared ROST resource')
            else:
                wrapper = None
                expected = 0x91020 if version == 0 else 0x90F60
                _require(base == 0 and len(data) == expected, 'unframed ROST has unknown boundaries')
                end = len(data)
            candidates.append(SaveRost(data, Layout(version, wrapper, base, root, end)))
        except SaveRostError as exc:
            failures.append(str(exc))
    _require(len(candidates) == 1, 'ambiguous ROST resources' if len(candidates) > 1
             else 'no supported ROST: ' + ('; '.join(failures[:3]) or 'inner header not found'))
    return candidates[0]


def encode(document: SaveRost) -> bytes:
    return document.to_bytes()


def load_save(path: Path | str, *, require_signature: bool = True) -> tuple[SaveRost, records.SaveContainer]:
    """Verify via the unchanged container layer, then decode without its v17 scanner.

    The caller signs/writes a COPY with container.write(target, document.to_bytes()).
    No signature key, EXTRA bytes or authentication policy is changed here.
    """
    container = records.SaveContainer.load(path, require_signature=require_signature)
    return decode(container.savegame), container
