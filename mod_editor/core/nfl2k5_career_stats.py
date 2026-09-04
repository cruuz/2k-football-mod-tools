"""Lossless, transactional career-stat import for the version-17 disc ROST.

No network, XBE edits, or source-file writes. Run after reclassification and
team_history. Only verified direct counters are writable; unknown, deleted,
postseason and folded words remain lossless. A source-missing cell is not zero.

Retail evidence: 0x320430 -> 0xCB240 -> 0xCAD50 -> 0x14EF20;
direct field = i32[0xA8A51C + 28*selector]. SACK selector 184 is derived via
0xA8B918 from selector 47 / field 19, multiplied by f32[0x4E4184] = 0.5.
Field goal totals are derived sums of distance buckets, not standalone fields.
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import io
import re
import struct
from typing import Iterable

from . import nfl2k5_save_rost as rost
from . import nfl2k5_roster_records as records


class CareerStatsError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise CareerStatsError(message)


@dataclass(frozen=True)
class Field:
    id: int
    name: str
    selector: int
    signed: bool = False
    units: int = 1             # raw units per displayed unit


FIELDS = (
    Field(0, 'games', 99),
    Field(1, 'rushing_attempts', 3), Field(2, 'rushing_yards', 80, True), Field(3, 'rushing_touchdowns', 63),
    Field(6, 'passing_attempts', 35), Field(7, 'passing_completions', 4),
    Field(8, 'passing_yards', 76, True), Field(9, 'passing_touchdowns', 64), Field(10, 'passing_interceptions', 22),
    Field(12, 'receptions', 46), Field(13, 'receiving_yards', 79, True), Field(14, 'receiving_touchdowns', 62),
    Field(18, 'defensive_tackles', 50), Field(19, 'defensive_sacks', 47, units=2),
    Field(20, 'defensive_interceptions', 23), Field(21, 'forced_fumbles', 17),
    Field(55, 'interception_return_yards', 72, True),
    Field(25, 'extra_points_made', 88), Field(26, 'extra_points_attempted', 89),
    Field(32, 'punts', 43), Field(33, 'punting_yards', 78, True),
    Field(34, 'punts_inside_20', 45), Field(71, 'punt_touchbacks', 58),
    Field(61, 'field_goals_made_1_29', 173), Field(62, 'field_goals_attempted_1_29', 169),
    Field(63, 'field_goals_made_30_39', 174), Field(64, 'field_goals_attempted_30_39', 170),
    Field(65, 'field_goals_made_40_49', 175), Field(66, 'field_goals_attempted_40_49', 171),
    Field(67, 'field_goals_made_50_plus', 176), Field(68, 'field_goals_attempted_50_plus', 172),
)
BY_NAME = {f.name: f for f in FIELDS}
BY_ID = {f.id: f for f in FIELDS}
DERIVED = {'field_goals_made', 'field_goals_attempted', 'field_goal_percentage',
           'passing_rating', 'completion_percentage', 'rushing_average', 'receiving_average', 'punting_average'}
SCHEMA = 'nfl2k5_career_stats/v1'
CSV_COLUMNS = ('player_pool', 'player_index', 'first_name', 'last_name', 'birth_date',
               'record_sha256', 'season', 'phase', 'stat', 'value', 'source', 'source_sha256', 'source_player_id')
CSV_COLUMNS += ('occurrence', 'expected_word')
REQUIRED_COLUMNS = {'first_name', 'last_name', 'birth_date', 'season', 'stat', 'value', 'source', 'source_sha256'}
MAX_ROWS = 100000


@dataclass(frozen=True)
class Word:
    raw: int

    def __post_init__(self):
        _require(type(self.raw) is int and 0 <= self.raw <= 0xFFFFFFFF, 'word must be an unsigned dword')

    @property
    def field(self):
        return (self.raw >> 16) & 127

    @property
    def slot(self):
        return (self.raw >> 23) & 31

    @property
    def phase(self):
        return 'postseason' if self.raw & 0x20000000 else 'regular'

    @property
    def deleted(self):
        return bool(self.raw & 0x10000000)

    @property
    def folded(self):
        return bool(self.raw & 0x40000000)

    def value(self, field: Field) -> Decimal:
        _require(self.field == field.id, 'field/value mismatch')
        raw = self.raw & 65535
        if field.signed and raw >= 32768:
            raw -= 65536
        return Decimal(raw) / field.units


def decode_word(raw: int) -> Word:
    return Word(raw)


def encode_word(word: Word) -> int:
    return word.raw


def _raw_value(field: Field, value: Decimal) -> int:
    _require(value.is_finite(), f'{field.name}: value must be finite')
    low = -32768 if field.signed else 0
    _require(Decimal(low) / field.units <= value <= Decimal(32767) / field.units,
             f'{field.name}: value is outside the signed historical getter range')
    scaled = int(value * field.units)
    # Compare against the original Decimal, not a context-rounded product.
    # Otherwise tiny exponents can underflow to zero, or excess precision can
    # silently turn a fractional source value into an apparently integral one.
    _require(value == Decimal(scaled) / field.units,
             f'{field.name}: value is not an exact multiple of {Decimal(1) / field.units}')
    _require(low <= scaled <= 32767, f'{field.name}: raw value is outside {low}..32767')
    return scaled & 65535


@dataclass(frozen=True)
class Row:
    first_name: str
    last_name: str
    birth_date: dt.date | None
    season: int
    stat: str
    value: Decimal | None
    source: str
    source_sha256: str
    player_pool: str = 'primary'
    player_index: int | None = None
    phase: str = 'regular'
    record_sha256: str = ''
    source_player_id: str = ''
    occurrence: int | None = None
    expected_word: str = ''


def read_csv(text: str) -> list[Row]:
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff'), newline=''))
    names = reader.fieldnames or []
    _require(len(names) == len(set(names)), 'duplicate CSV column')
    _require(REQUIRED_COLUMNS <= set(names), f'CSV requires columns: {", ".join(sorted(REQUIRED_COLUMNS))}')
    _require(set(names) <= set(CSV_COLUMNS), f'unknown CSV columns: {set(names) - set(CSV_COLUMNS)}')
    rows = []
    for line, item in enumerate(reader, 2):
        _require(len(rows) < MAX_ROWS, f'CSV exceeds {MAX_ROWS} rows')
        _require(None not in item and all(v is not None for v in item.values()), f'CSV line {line}: wrong cell count')
        cell = {k: v.strip() for k, v in item.items()}
        try:
            value = Decimal(cell['value']) if cell['value'] else None
            birth = dt.date.fromisoformat(cell['birth_date']) if cell['birth_date'] else None
            index = int(cell['player_index']) if cell.get('player_index') else None
            season = int(cell['season'])
            occurrence = int(cell['occurrence']) if cell.get('occurrence') else None
        except (ValueError, InvalidOperation) as exc:
            raise CareerStatsError(f'CSV line {line}: invalid date or number') from exc
        rows.append(Row(cell['first_name'], cell['last_name'], birth, season, cell['stat'], value,
                        cell['source'], cell['source_sha256'], cell.get('player_pool') or 'primary',
                        index, cell.get('phase') or 'regular', cell.get('record_sha256', ''),
                        cell.get('source_player_id', ''), occurrence, cell.get('expected_word', '')))
    return rows


def record_digest(player: rost.Player) -> str:
    # Pool repacking alone must not invalidate an otherwise exact record pin.
    raw = bytearray(player.record.encode())
    raw[0x2C:0x30] = bytes(4)
    return hashlib.sha256(raw).hexdigest()


def _name(text: str) -> str:
    # Don't discard suffixes or punctuation and accidentally merge identities.
    return ' '.join(text.split()).casefold()


def _match(document: rost.SaveRost, row: Row) -> tuple[rost.Player, str]:
    _require(row.player_pool in ('primary', 'secondary'), 'unknown player pool')
    _require(bool(row.first_name.strip()) and bool(row.last_name.strip()), 'first and last name are required')
    if row.player_index is not None:
        _require(type(row.player_index) is int and row.player_index >= 0, 'invalid player index')
        player = document.by_key.get((row.player_pool, row.player_index))
        candidates = [] if player is None else [player]
    else:
        _require(row.birth_date is not None, 'name-only identity is refused; supply birth date or index plus record SHA-256')
        candidates = [p for p in document.players if p.pool == row.player_pool]
    candidates = [p for p in candidates if _name(p.first) == _name(row.first_name) and _name(p.last) == _name(row.last_name)]
    if row.birth_date is not None:
        candidates = [p for p in candidates if p.record.birth_date == row.birth_date]
    else:
        _require(bool(row.record_sha256), 'missing birth date requires index and record SHA-256')
    if row.record_sha256:
        _require(re.fullmatch('[0-9a-f]{64}', row.record_sha256) is not None, 'invalid record SHA-256')
        candidates = [p for p in candidates if record_digest(p) == row.record_sha256]
    _require(len(candidates) == 1, f'ambiguous or unmatched identity: {row.first_name} {row.last_name}')
    return candidates[0], 'index+identity' if row.player_index is not None else 'unique-name+birth'


def decode_body(body: bytes) -> rost.SaveRost:
    _require(len(body) == records.BODY_SIZE, 'career importer requires the bare 0x90F60 disc ROST body')
    try:
        document = rost.decode(body, preamble=0)
    except rost.SaveRostError as exc:
        raise CareerStatsError(str(exc)) from exc
    _require(document.layout.version == 17, 'career importer currently accepts disc version 17 only')
    _require(document.pool is not None, 'history pool pointer is missing')
    return document


def encode_body(document: rost.SaveRost) -> bytes:
    """Lossless codec, including unknown words, flags, padding and pointer order."""
    return document.to_bytes()


def export_csv(body: bytes, *, base_year: int = 2004) -> str:
    """Editable known counters only; omitted opaque words stay in the input body.

    Export does not manufacture missing counters or historical games. Deleted
    and folded entries are omitted, never flattened into real season rows.
    """
    _require(type(base_year) is int and 1901 <= base_year <= 2100, 'invalid roster epoch')
    document = decode_body(body)
    source_hash = hashlib.sha256(body).hexdigest()
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator='\n')
    writer.writeheader()
    for player in document.players:
        identity_hash = record_digest(player)
        occurrences = {}
        count = (struct.unpack_from('<I', body, player.offset + 0x24)[0] >> 8) & 31
        for raw in document.history_words[player.key]:
            word = Word(raw)
            field = BY_ID.get(word.field)
            season = base_year - (count - word.slot)
            if field is None or word.deleted or word.folded or not 1900 <= season <= min(2004, base_year - 1):
                continue
            key = (word.slot, word.phase, field.id)
            occurrence = occurrences.get(key, 0)
            occurrences[key] = occurrence + 1
            writer.writerow({'player_pool': player.pool, 'player_index': player.index,
                             'first_name': player.first, 'last_name': player.last,
                             'birth_date': player.record.birth_date.isoformat() if player.record.birth_date else '',
                             'record_sha256': identity_hash, 'season': season, 'phase': word.phase,
                             'stat': field.name, 'value': format(word.value(field), 'f'),
                             'source': 'roster:' + source_hash, 'source_sha256': source_hash, 'source_player_id': '',
                             'occurrence': occurrence, 'expected_word': f'{raw:08x}'})
    return output.getvalue()


def apply_body(body: bytes, rows: Iterable[Row], *, base_year: int = 2004,
               reserved_tail_words: int = 0) -> tuple[bytes, dict[str, object]]:
    """Preflight every row and the shared pool, then return new bytes + receipt.

    Changing an existing counter preserves its flags and position. New counters
    are inserted at the player's stream head, as retail does. No stream/pool
    expansion is allowed into a nonzero slack byte or a caller-reserved tail.
    A player-season needs a games entry in that phase, existing or in this batch.
    """
    _require(type(base_year) is int and 1901 <= base_year <= 2100, 'invalid roster epoch')
    document = decode_body(body)
    pool = document.pool
    assert pool is not None
    capacity = document.pool_capacity
    _require(type(reserved_tail_words) is int and 0 <= reserved_tail_words <= capacity, 'invalid reserved tail budget')
    usable = capacity - reserved_tail_words
    _require(document.pool_used <= usable, 'existing history overlaps the reserved tail budget')
    _require(pool + capacity * 4 <= len(body), 'declared history capacity runs past body')
    for table in document.tables.values():
        if table.offset is not None and table.count:
            _require(table.offset + table.count * table.stride <= pool or table.offset >= pool + usable * 4,
                     f'history capacity overlaps {table.name}')
    # To repack, each used word must have one owner. Raw decode remains able to
    # preserve more exotic layouts, but this writer refuses to guess ownership.
    ordered = sorted((p for p in document.players if document.history_offsets[p.key] is not None),
                     key=lambda p: document.history_offsets[p.key])
    at = pool
    for player in ordered:
        _require(document.history_offsets[player.key] == at, 'history streams have gaps, overlap or shared ownership')
        at += len(document.history_words[player.key]) * 4
    _require(at == pool + document.pool_used * 4, 'used pool has unowned words')

    streams = {p.key: list(document.history_words[p.key]) for p in document.players}
    def matches(words, slot, phase, field):
        return [i for i, raw in enumerate(words) if not raw & 0x50000000
                and Word(raw).slot == slot and Word(raw).phase == phase and Word(raw).field == field]

    staged = {}
    log = []
    missing = 0
    for n, row in enumerate(rows):
        _require(n < MAX_ROWS, 'too many source rows')
        _require(isinstance(row, Row), 'expected Row objects')
        _require(row.stat not in DERIVED, f'{row.stat} is derived; import the underlying counters/distance buckets')
        _require(row.stat in BY_NAME, f'unknown/unproved stat: {row.stat}')
        _require(row.phase in ('regular', 'postseason'), 'phase must be regular or postseason')
        _require(type(row.season) is int and 1900 <= row.season <= min(2004, base_year - 1),
                 'season must be completed, <=2004, and consistent with base_year')
        _require(bool(row.source.strip()) and re.fullmatch('[0-9a-f]{64}', row.source_sha256) is not None,
                 'each source row needs provenance and a lowercase SHA-256')
        if row.value is None:
            missing += 1
            continue
        player, match_kind = _match(document, row)
        count = (struct.unpack_from('<I', body, player.offset + 0x24)[0] >> 8) & 31
        slot = count - (base_year - row.season)
        _require(0 <= slot < count <= 31, f'{player.first} {player.last}: season has no representable completed slot')
        field = BY_NAME[row.stat]
        try:
            value = Decimal(str(row.value))
        except InvalidOperation as exc:
            raise CareerStatsError('invalid numeric value') from exc
        raw_value = _raw_value(field, value)
        candidates = matches(streams[player.key], slot, row.phase, field.id)
        if row.occurrence is not None:
            _require(type(row.occurrence) is int and 0 <= row.occurrence < len(candidates), 'invalid counter occurrence')
            _require(re.fullmatch('[0-9a-f]{8}', row.expected_word) is not None, 'occurrence needs an exact expected_word pin')
            target = candidates[row.occurrence]
            actual = streams[player.key][target]
            expected = int(row.expected_word, 16)
            _require(actual == expected or (actual & 0xFFFF0000 == expected & 0xFFFF0000
                                            and actual & 65535 == raw_value),
                     'counter occurrence pin changed; export a fresh CSV')
        else:
            _require(not row.expected_word, 'expected_word requires an occurrence')
            _require(len(candidates) <= 1, 'duplicate live destination counters; supply an exported occurrence/pin')
            target = candidates[0] if candidates else None
        key = (player.key, slot, row.phase, field.id, target)
        _require(key not in staged, f'duplicate source counter: {player.first} {player.last}/{row.season}/{row.stat}/{row.phase}')
        staged[key] = raw_value
        log.append({'player_pool': player.pool, 'player_index': player.index, 'season': row.season,
                    'slot': slot, 'phase': row.phase, 'stat': field.name, 'field': field.id,
                    'value': str(value), 'raw_value': raw_value, 'match': match_kind,
                    'occurrence': row.occurrence,
                    'source': row.source, 'source_sha256': row.source_sha256, 'source_player_id': row.source_player_id})

    added = replaced = unchanged = 0
    additions = {}
    staged_games = {(key, slot, phase) for key, slot, phase, field, target in staged if field == 0}
    for (player_key, slot, phase, field, target), value in staged.items():
        words = streams[player_key]
        if field != 0:
            games_key = (player_key, slot, phase)
            _require(games_key in staged_games or bool(matches(words, slot, phase, 0)),
                     'player-season has no games entry in this phase; supply games in the same batch')
        if target is not None:
            index = target
            if words[index] & 65535 == value:
                unchanged += 1
            else:
                words[index] = (words[index] & 0xFFFF0000) | value
                replaced += 1
        else:
            raw = (slot << 23) | (field << 16) | value | (0x20000000 if phase == 'postseason' else 0)
            additions.setdefault(player_key, []).append(raw)
            added += 1
    new_used = document.pool_used + added
    _require(new_used <= usable, f'history needs {new_used} dwords; usable capacity {usable} (reserved {reserved_tail_words})')
    _require(not any(body[pool + document.pool_used * 4:pool + new_used * 4]),
             'history growth would overwrite nonzero/unowned slack')
    for key, new in additions.items():
        new.sort(key=lambda raw: (Word(raw).slot, Word(raw).phase, Word(raw).field))
        streams[key] = new + streams[key]
        if not document.history_words[key]:
            streams[key][-1] |= 0x80000000
    order = ordered + sorted((p for p in document.players if document.history_offsets[p.key] is None and streams[p.key]),
                             key=lambda p: p.key)
    output = bytearray(body)
    at = pool
    for player in order:
        words = streams[player.key]
        _require(words[-1] & 0x80000000 and not any(w & 0x80000000 for w in words[:-1]), 'invalid stream terminators')
        struct.pack_into('<i', output, player.offset + 0x2C, at - (player.offset + 0x2C) + 1)
        for word in words:
            struct.pack_into('<I', output, at, word)
            at += 4
    struct.pack_into('<I', output, document.layout.root + 0x40, new_used)
    result = bytes(output)
    check = decode_body(result)
    for (key, slot, phase, field, target), wanted in staged.items():
        words = check.history_words[key]
        indices = matches(words, slot, phase, field) if target is None else [target + len(additions.get(key, []))]
        _require(len(indices) == 1 and words[indices[0]] & 65535 == wanted, 'written value failed decode-back verification')
    # Verify exact unknown-word/flag/order preservation, accounting only for
    # declared insertions and value substitutions, and check the write boundary.
    for player in document.players:
        _require(tuple(streams[player.key]) == check.history_words[player.key], 'stream decode-back mismatch')
    allowed = bytearray(len(body))
    allowed[pool:pool + new_used * 4] = b'\1' * (new_used * 4)
    root = document.layout.root
    allowed[root + 0x40:root + 0x44] = b'\1' * 4
    for player in document.players:
        allowed[player.offset + 0x2C:player.offset + 0x30] = b'\1' * 4
    _require(all(a == b or allowed[i] for i, (a, b) in enumerate(zip(body, result))), 'write outside pool/pointers/used count')
    return result, {'schema': SCHEMA, 'base_year': base_year, 'source_body_sha256': hashlib.sha256(body).hexdigest(),
                    'output_body_sha256': hashlib.sha256(result).hexdigest(), 'pool_capacity': capacity,
                    'reserved_tail_words': reserved_tail_words, 'usable_capacity': usable,
                    'used_before': document.pool_used, 'used_after': new_used, 'free_after': usable - new_used,
                    'added': added, 'replaced': replaced, 'unchanged': unchanged, 'source_missing': missing,
                    'rows': log, 'no_xbe_change': True, 'roundtrip_verified': True}
