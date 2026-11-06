"""Versioned 0x92000 ROST arena. EXPERIMENTAL / UNWITNESSED.

All offsets below are relative to the ROST root, not its wrapper. The block
at +0x91C00 belongs to this schema; the native auxiliary tail stays at the end.
Nothing in the original arena is treated as
free storage. A migration inserts records and rebases the exact pointer fields
enumerated by C0730 and its callees; old bytes, including padding, travel with
their objects. Existing team ordinals and primary indices do not change.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import struct
import zlib

RETAIL_SIZE = 0x91000
ARENA_SIZE = 0x92000
# b778 fa4: a capacity-grown arena keeps the same version numbers (18 disc / 1 save) and the same
# 0x54-byte primary records; only the declared arena length, the block position and the number of
# records/names change. The original 0x92000 reserve schema is still read and written exactly.
#
# b779 ag1 (Noah 10/28: "ideally we just add more slots"): THE capacity layout. Every size that the
# Studio, the save tools and the native owners name is derived from CAPACITY_ARENA_SIZE here (save
# sizes, wrapper sizes, the block position, the disc resource size); nothing else spells a literal.
# beta-78 / v0.7 shipped the 0xB0000 arena (3,231 primary records, 847,020-byte franchise saves); it
# stays readable and migrates: in the game an old save loads into the bigger arena with its own records
# (tools/roster_arena/lifecycle.h moves its tail), and Franchise > Upgrade can append the new records.
# 0xCA000 holds 4,096 primary records from the retail 2,619-record roster (1,477 appended records of
# 84 bytes plus 68 bytes of private names each, ending at 0xC7D18 for a retail save) with the reserve
# block and descriptor at the end and about 7.6 KB to spare. 4,096 is MyCareer's own bound on the pool
# (tools/mycareer_mode/runtime.c player_bounds / mode_create; its state stores the index below 4,096).
LEGACY_CAPACITY_ARENA_SIZE = 0xB0000      # beta-78 / v0.7
CAPACITY_ARENA_SIZE = 0xCA000             # beta-79 / v0.8
CAPACITY_ARENA_SIZES = (LEGACY_CAPACITY_ARENA_SIZE, CAPACITY_ARENA_SIZE)
ARENA_SIZES = (ARENA_SIZE,) + CAPACITY_ARENA_SIZES
NAME_BUFFER = 34       # one UTF-16 name buffer in the arena
CAPACITY_PRIMARY_LIMIT = 4096
CAPACITY_MAGIC = b'2K5CAP\0\0'
CAPACITY_DESCRIPTOR_SIZE = 16
CAPACITY_TAIL = 0x400                     # reserve block (and the save's auxiliary tail) before the arena end
CAPACITY_RECORD_BYTES = 84 + 68           # one appended primary record and its two private 34-byte names
BLOCK_SIZE = 352
BLOCK_OFFSET = 0x91C00
CAPACITY_BLOCK_OFFSET = CAPACITY_ARENA_SIZE - CAPACITY_TAIL
LEGACY_CAPACITY_BLOCK_OFFSET = LEGACY_CAPACITY_ARENA_SIZE - CAPACITY_TAIL
# Native franchise save geometry: settings 0x2E0 + ROST wrapper (arena + 0x40) + season 0x83DC + front
# office 0x165B0 (0x16AA10). A save's wrapper declares arena + 0x20; a disc main ROST resource is the arena
# plus its 0x20 wrapper and 0x40 object.
RETAIL_SAVE_SIZE = 720044


def save_size(arena_size: int = CAPACITY_ARENA_SIZE) -> int:
    """Native franchise save size (no footer) for an arena size, as 0x16AA10 computes it."""
    return RETAIL_SAVE_SIZE + arena_size - RETAIL_SIZE


def save_declared(arena_size: int = CAPACITY_ARENA_SIZE) -> int:
    """ROST wrapper +4 of a franchise save (version 0/1) with this arena."""
    return arena_size + 0x20


def disc_resource_size(arena_size: int = CAPACITY_ARENA_SIZE) -> int:
    """Outer-archive size of a grown disc main ROST (version 18) with this arena."""
    return arena_size + 0x60


CAPACITY_SAVE_SIZE = save_size(CAPACITY_ARENA_SIZE)                   # 953,516
LEGACY_CAPACITY_SAVE_SIZE = save_size(LEGACY_CAPACITY_ARENA_SIZE)     # 847,020
CAPACITY_SAVE_SIZES = tuple(save_size(size) for size in CAPACITY_ARENA_SIZES)
CAPACITY_SAVE_GROWTH = CAPACITY_ARENA_SIZE - RETAIL_SIZE


def is_capacity_size(arena_size) -> bool:
    return arena_size in CAPACITY_ARENA_SIZES


# Bare (unframed) ROST bodies by version: the save codec and the college check accept exactly these lengths.
BARE_BODY_SIZES = {0: (0x91020,), 1: (0x92020,), 17: (0x90F60,),
                   18: (ARENA_SIZE + 0x40,) + tuple(size + 0x40 for size in CAPACITY_ARENA_SIZES)}
MAGIC = b"2K5RSV2\0"
VERSION = 2
SAVE_VERSION = 1
DISC_VERSION = 18
EMPTY = 0xFFFF
NFL_TEAMS = 32
OVERFLOW_SLOTS = 5
RESERVES_ENABLED = 0x100
# Identity numbers (+0x118) of the two extra created teams (USER3, USER4). Retail's main roster uses numbers up to 45
# and 90..99, the 75 historic files 100..170 (71 distinct); new historic teams take numbers from 171 up
# (research e2, whose research team used 175). 250 and 251 are clear of all of them and fit in a byte: five retail
# readers of +0x118 take its low byte only. 100 and 101 (beta 76 f5) were the 1975 Cardinals' and the 1980
# Falcons' numbers. tools/roster_arena/lifecycle.h (arena_created) names the same two numbers.
CREATED_IDS = (250, 251)
# Disc main ROST (outer 5) framing: 0x20-byte wrapper and 0x40-byte object before the arena.
LEGACY_DISC_RESOURCE_SIZE = 0x90F80   # retail, version 17, 0x90F20 arena
GROWN_DISC_RESOURCE_SIZE = 0x92060    # version 18, ARENA_SIZE arena
TEAM_POINTERS = tuple(range(0, 260, 4)) + (
    0x104, 0x108, 0x10C, 0x110, 0x114, 0x138, 0x13C,
    0x140, 0x144, 0x148, 0x14C)
# C0730; player E5EB0, team 241A20, stadium 241EB0, coach 241610,
# college 2421E0, labels 197000, generated names 242360, FA 242630.
ROOT_POINTERS = (4, 12, 20, 28, 36, 44, 52, 60, 68, 76, 84, 92, 100, 104, 108)
TABLE_POINTERS = {
    'primary': (0, 0x10, 0x14, 0x2C),
    'secondary': (0, 0x10, 0x14, 0x2C),
    'stadiums': (0, 8, 12, 16, 20), 'teams': TEAM_POINTERS,
    'colleges': (0,), 'coaches': (0, 4, 8, 12, 16),
    'free_agents': (0,), 'team_labels': (0, 4),
    'generated_names': (0, 4), 'historic_descriptors': (12,),
}


class ArenaError(ValueError):
    """A migration or ownership edit cannot be represented without data loss."""


def require(ok, message):
    if not ok:
        raise ArenaError(message)


def block_offset(arena_size):
    """Offset of the 352-byte reserve block from the roster root for a supported arena size."""

    if arena_size == ARENA_SIZE:
        return BLOCK_OFFSET
    require(is_capacity_size(arena_size), 'unsupported arena size')
    return arena_size - CAPACITY_TAIL


def data_end(layout):
    """First byte that belongs to the reserve/capacity metadata, not ordinary arena data."""

    if layout.version in (SAVE_VERSION, DISC_VERSION):
        return layout.root + block_offset(layout.arena_size)
    return layout.end


def capacity_descriptor(payload, layout):
    """(records, old_end) from the capacity marker, or None for the reserve schema."""

    if not is_capacity_size(layout.arena_size):
        return None
    at = layout.root + block_offset(layout.arena_size) - CAPACITY_DESCRIPTOR_SIZE
    raw = bytes(payload[at:at + CAPACITY_DESCRIPTOR_SIZE])
    if raw[:8] != CAPACITY_MAGIC:
        return None
    records, old_end = struct.unpack_from('<II', raw, 8)
    require(0 < records < 0x10000 and layout.root < old_end < layout.end,
            'malformed capacity descriptor')
    return records, old_end


@dataclass(frozen=True)
class Overflow:
    epoch: int = 0
    eligible_mask: int = 0
    extra_teams: int = 0
    reserves_enabled: bool = True
    rows: tuple[tuple[int, ...], ...] = ((EMPTY,) * OVERFLOW_SLOTS,) * NFL_TEAMS

    def limit(self, team: int) -> int:
        require(type(team) is int and 0 <= team < NFL_TEAMS, 'select an NFL team')
        return (17 if self.eligible_mask & (1 << team) else 16) if self.reserves_enabled else 12

    def encode(self) -> bytes:
        require(type(self.epoch) is int and 0 <= self.epoch <= 0xFFFFFFFF, 'invalid pool epoch')
        require(type(self.eligible_mask) is int and 0 <= self.eligible_mask <= 0xFFFFFFFF,
                'invalid eligible-team mask')
        require(type(self.extra_teams) is int and self.extra_teams in (0, 2), 'extra teams must be zero or two')
        require(self.reserves_enabled or not self.eligible_mask, 'eligibility requires larger reserves')
        require(len(self.rows) == NFL_TEAMS and all(len(r) == OVERFLOW_SLOTS for r in self.rows),
                'overflow must contain 32 rows of five indices')
        require(all(type(i) is int and 0 <= i <= EMPTY for r in self.rows for i in r),
                'overflow index is not a u16')
        flags = self.extra_teams | (RESERVES_ENABLED if self.reserves_enabled else 0)
        out = bytearray(struct.pack('<8s4H4I', MAGIC, VERSION, NFL_TEAMS, OVERFLOW_SLOTS, 2,
                                    self.epoch, 0, self.eligible_mask, flags))
        out.extend(struct.pack('<160H', *(i for r in self.rows for i in r)))
        struct.pack_into('<I', out, 20, zlib.crc32(out))
        return bytes(out)

    def with_row(self, team: int, indices) -> 'Overflow':
        self.limit(team)
        values = tuple(indices)
        require(len(values) <= OVERFLOW_SLOTS and len(set(values)) == len(values),
                'overflow is full or has duplicate indices')
        require(all(type(i) is int and 0 <= i < EMPTY for i in values), 'invalid overflow identity')
        rows = list(self.rows)
        rows[team] = values + (EMPTY,) * (OVERFLOW_SLOTS - len(values))
        return replace(self, rows=tuple(rows))


def read(payload, root: int, end: int, version: int) -> Overflow | None:
    if version not in (SAVE_VERSION, DISC_VERSION):
        require(end - root not in ARENA_SIZES, 'grown arena has a legacy version')
        return None
    size = end - root
    require(size in ARENA_SIZES, 'grown ROST version has the wrong arena length')
    at = root + block_offset(size)
    raw = bytes(payload[at:at + BLOCK_SIZE])
    require(len(raw) == BLOCK_SIZE, 'truncated reserve overflow')
    magic, ver, teams, slots, width, epoch, crc, mask, flags = struct.unpack_from('<8s4H4I', raw)
    require((magic, ver, teams, slots, width) == (MAGIC, VERSION, NFL_TEAMS, OVERFLOW_SLOTS, 2),
            'unknown reserve overflow header')
    require(flags & ~0x1FF == 0 and flags & 0xFF in (0, 2), 'unknown arena feature flags')
    check = bytearray(raw)
    struct.pack_into('<I', check, 20, 0)
    require(zlib.crc32(check) == crc, 'reserve overflow checksum mismatch')
    indices = struct.unpack_from('<160H', raw, 32)
    result = Overflow(epoch, mask, flags & 0xFF, bool(flags & RESERVES_ENABLED),
                      tuple(tuple(indices[i:i + 5]) for i in range(0, 160, 5)))
    require(result.encode() == raw, 'noncanonical reserve overflow')
    count = struct.unpack_from('<I', payload, root)[0]
    require(all(i == EMPTY or i < count for i in indices), 'overflow index outside primary pool')
    for row in result.rows:
        values = tuple(i for i in row if i != EMPTY)
        require(row == values + (EMPTY,) * (5 - len(values)), 'nonempty unused overflow slot')
        require(len(set(values)) == len(values), 'duplicate overflow identity')
    return result


def write_block(payload: bytearray, root: int, block: Overflow, *, arena_size: int = ARENA_SIZE) -> None:
    at = root + block_offset(arena_size)
    require(at + BLOCK_SIZE <= len(payload), 'overflow write outside arena')
    payload[at:at + BLOCK_SIZE] = block.encode()


def pointer_fields(document) -> tuple[int, ...]:
    fields = [document.layout.root + f for f in ROOT_POINTERS]
    for name, offsets in TABLE_POINTERS.items():
        table = document.tables[name]
        if table.offset is not None:
            fields.extend(table.offset + i * table.stride + f
                          for i in range(table.count) for f in offsets)
    for field in fields:
        document.rel(field, label='arena relocation')
    require(len(set(fields)) == len(fields), 'overlapping relocation fields')
    return tuple(fields)


def migrate(payload: bytes, *, reserves_16: bool = True, created_teams_extra: int = 0,
            eligible_team_mask: int = 0, capacity_records: int = 0,
            class_records: int | None = None) -> tuple[bytes, dict]:
    """Copy-only v0/v17 migration. Eligibility is an explicit per-team decision.

    Created IDs CREATED_IDS (250/251) are distinct from the retail special
    teams 92..99 and from every historic identity (100..170). New records
    inherit the two existing created slots' assets/playbooks, with separate
    labels. This does not add teams to the 32-team franchise league.
    """
    from .nfl2k5_save_rost import decode
    from . import nfl2k5_practice_squad as ps
    require(type(reserves_16) is bool, 'reserves_16 must be a boolean')
    require(type(capacity_records) is int and capacity_records >= 0, 'invalid capacity record request')
    if capacity_records:
        require(not reserves_16 and not created_teams_extra and not eligible_team_mask,
                'capacity growth composes with neither the reserve overflow nor extra created teams')
        return _migrate_capacity(payload, capacity_records, class_records)
    require(reserves_16 or created_teams_extra, 'select at least one arena growth option')
    block = Overflow(eligible_mask=eligible_team_mask, extra_teams=created_teams_extra,
                     reserves_enabled=reserves_16)
    block.encode()
    document = decode(payload)
    layout = document.layout
    prior = read(payload, layout.root, layout.end, layout.version)
    if prior is not None:
        require((prior.reserves_enabled, prior.extra_teams, prior.eligible_mask) ==
                (reserves_16, created_teams_extra, eligible_team_mask), 'arena settings differ; rebuild from original')
        ps.validate_save(payload)
        return bytes(payload), {'already_applied': True, 'changed_bytes': 0, 'file_growth': 0}
    require(layout.arena_size <= RETAIL_SIZE, 'legacy arena exceeds supported capacity')
    require(len(document.teams) >= 32, 'arena migration requires the NFL ordinal table')
    ps.validate_save(payload)
    fields = pointer_fields(document)
    teams, labels = document.tables['teams'], document.tables['team_labels']
    insertions = []
    templates = []
    if created_teams_extra:
        require(teams.count == 52 and labels.count == 36 and labels.offset is not None,
                'extra-team proof requires the retail 52-team / 36-label layout')
        by_id = {team.asset_id: team for team in document.teams}
        require(len(by_id) == teams.count and not any(i in by_id for i in CREATED_IDS),
                'duplicate or occupied created-team IDs')
        require(90 in by_id and 91 in by_id, 'missing created-team templates')
        templates = [by_id[90], by_id[91]]
        require(all(struct.unpack_from('<I', payload, t.offset + 0x128)[0] == 2 for t in templates),
                'foreign created-team kind')
        insertions = [(teams.offset + teams.count * 500, 1000),
                      (labels.offset + labels.count * 8, 16)]
    def moved(offset):
        return offset + sum(size for at, size in insertions if offset >= at)
    root = layout.root
    body = bytearray(payload[root:layout.end])
    for at, size in sorted(insertions, reverse=True):
        body[at - root:at - root] = bytes(size)
    require(len(body) <= BLOCK_OFFSET, 'relocated legacy arena overlaps overflow block')
    content_end = len(body)
    body.extend(bytes(ARENA_SIZE - len(body)))
    out = bytearray(payload[:root]) + body + bytearray(payload[layout.end:])
    for field in fields:
        target = document.rel(field)
        new_field = moved(field)
        struct.pack_into('<i', out, new_field, 0 if target is None else moved(target) - new_field + 1)
    new_teams = moved(teams.offset)
    if created_teams_extra:
        struct.pack_into('<I', out, root + 0x18, teams.count + 2)
        struct.pack_into('<I', out, root + 0x48, labels.count + 2)
        text_cursor = root + content_end
        def name(field, text):
            nonlocal text_cursor
            encoded = text.encode('utf-16le') + b'\0\0'
            require(text_cursor + len(encoded) <= root + BLOCK_OFFSET, 'created labels exceed arena budget')
            out[text_cursor:text_cursor + len(encoded)] = encoded
            struct.pack_into('<i', out, field, text_cursor - field + 1)
            text_cursor += len(encoded)
        for j, template in enumerate(templates):
            dest = new_teams + (teams.count + j) * 500
            out[dest:dest + 500] = payload[template.offset:template.offset + 500]
            for f in TEAM_POINTERS:
                target = document.rel(template.offset + f)
                struct.pack_into('<i', out, dest + f, 0 if target is None else moved(target) - dest - f + 1)
            out[dest:dest + 260] = bytes(260)
            out[dest + ps.ACTIVE_COUNT] = 0
            out[dest + ps.VERSION_OFFSET] = out[dest + ps.COUNT] = out[dest + ps.MARKER_OFFSET] = 0
            struct.pack_into('<H', out, dest + 0x118, CREATED_IDS[j])
            name(dest + 0x104, f'Created {j + 3}')
            name(dest + 0x108, f'USER{j + 3}')
            label = moved(labels.offset) + (labels.count + j) * 8
            # Label and playbook identity are separate relative string pointers.
            source_label = labels.offset + (34 + j) * 8
            for f in (0, 4):
                target = document.rel(source_label + f)
                struct.pack_into('<i', out, label + f, 0 if target is None else moved(target) - label - f + 1)
            name(label, f'User {chr(67 + j)}')
    # Mark only NFL teams with the overflow-aware metadata version. Legacy
    # display-team aliases and the created slots retain their own metadata.
    for i in range(32):
        at = new_teams + i * 500
        out[at + ps.VERSION_OFFSET] = VERSION
        out[at + ps.MARKER_OFFSET] = ps.MARKER
    struct.pack_into('<I', out, layout.preamble + 16,
                     SAVE_VERSION if layout.version == 0 else DISC_VERSION)
    if layout.wrapper is not None:
        struct.pack_into('<I', out, layout.wrapper + 4, root + ARENA_SIZE - layout.preamble)
        auxiliary = struct.unpack_from('<I', payload, layout.wrapper + 8)[0]
        if layout.version == 0:
            require(auxiliary <= ARENA_SIZE - BLOCK_OFFSET - BLOCK_SIZE, 'native auxiliary tail overlaps overflow')
            if auxiliary:
                out[root + ARENA_SIZE - auxiliary:root + ARENA_SIZE] = payload[layout.end - auxiliary:layout.end]
        else:
            require(auxiliary == layout.end - layout.preamble, 'unsupported compressed disc ROST')
            struct.pack_into('<I', out, layout.wrapper + 8, root + ARENA_SIZE - layout.preamble)
    write_block(out, root, block)
    result = bytes(out)
    final = decode(result)
    require(len(final.teams) == teams.count + created_teams_extra, 'team migration count mismatch')
    ps.validate_save(result)
    return result, {'already_applied': False, 'experimental': True, 'runtime_witnessed': False,
                    'arena_size': ARENA_SIZE, 'overflow_offset': BLOCK_OFFSET,
                    'reserves_16': reserves_16, 'eligible_team_mask': eligible_team_mask,
                    'created_teams_extra': created_teams_extra, 'created_ids': list(CREATED_IDS) if created_teams_extra else [],
                    'pointer_fields_rebased': len(fields), 'file_growth': len(result) - len(payload),
                    'before_sha256': hashlib.sha256(payload).hexdigest(),
                    'after_sha256': hashlib.sha256(result).hexdigest()}


def capacity_fit(old_end_rel: int, arena_size: int = CAPACITY_ARENA_SIZE) -> int:
    """How many appended records (84 bytes plus 68 bytes of names) fit after arena-relative ``old_end_rel``."""
    room = arena_size - CAPACITY_TAIL - CAPACITY_DESCRIPTOR_SIZE - ((old_end_rel + 1) & ~1)
    return max(0, room // CAPACITY_RECORD_BYTES)


def capacity_class_records(primary_before: int, records: int, old_end_rel: int,
                           arena_size: int = CAPACITY_ARENA_SIZE) -> int:
    """b779 ag1: free records appended after the ``records`` create vacancies, up to CAPACITY_PRIMARY_LIMIT.

    They are the native "free for a draft class" state (flags & 5 == 0, like the disc's own 380-record first-class
    window): no team, no free-agent entry, no Create Player vacancy. The economy's class allocator and the
    retirement pass's free count (tools/franchise_economy/runtime.c economy_class_free) take them first, so the
    league can keep more unsigned players before it has to retire anyone to make a class."""
    fit = capacity_fit(old_end_rel, arena_size)
    return max(0, min(CAPACITY_PRIMARY_LIMIT - primary_before - records, fit - records))


def capacity_class_count(payload, layout) -> int:
    """Appended capacity records still in the free class state (flags byte 0): the class records a growth added."""
    from .nfl2k5_save_rost import decode
    descriptor = capacity_descriptor(payload, layout)
    if descriptor is None:
        return 0
    primary = decode(payload, preamble=layout.preamble).tables['primary']
    first = primary.count - descriptor[0]
    return sum(1 for i in range(first, primary.count) if payload[primary.offset + i * 84 + 8] == 0)


def _class_template(payload, document, primary):
    """The last free record (flags 0, a college, no history, owned by nobody): the disc's first-class window."""
    owned = set()
    for team in document.teams:
        owned.update(team.player_offsets)
    fa = document.tables['free_agents']
    if fa.offset is not None:
        owned.update(document.rel(fa.offset + i * 4) for i in range(fa.count))
    for index in range(primary.count - 1, 0, -1):
        at = primary.offset + index * 84
        if payload[at + 8] != 0 or at in owned or document.rel(at) is None or document.rel(at + 0x2C) is not None:
            continue
        return at
    return None


def _migrate_capacity(payload: bytes, records: int, class_records: int | None = None,
                      arena_size: int = CAPACITY_ARENA_SIZE, in_place: bool = False) -> tuple[bytes, dict]:
    """Append blank primary records and private name buffers, growing the arena to ``arena_size``.

    b780 b10: ``in_place`` runs the extension below on a save that is ALREADY ``arena_size`` big (the game moved a
    v0.7 save's tail to the bigger arena when it first saved it, but added none of the draft-class records): the free
    class records are inserted into the arena's own spare bytes and the tail stays where it is.

    Every existing table and object keeps its bytes; the primary insertion moves everything after
    the primary table by (appended records) * 0x54 and rebases the exact pointer inventory used by C0730.
    The first ``records`` new records copy the last vacant create record (Create Player and the dated
    refresh use them); the next ``class_records`` (default: up to CAPACITY_PRIMARY_LIMIT primary records,
    capacity_class_records) copy the last free first-class record (flags 0) so the draft class can use
    them. Every new record points at two fresh 34-byte names in the growth area: '*' blanks for a vacancy,
    zeros (empty, like the disc window's) for a class record. The free-agent list is not moved or extended
    here; the roster writers append entries into the native list's existing 2,500-slot capacity. The reserve
    block moves to the end of the grown arena and stays empty, which is what the capacity runtime validates.

    b779 ag1: a beta-78 capacity roster or save (0xB0000, with its descriptor) is grown the same way: the new
    records follow its existing appended records, their names follow its names, and the 0x400-byte tail
    (descriptor, block, a save's auxiliary bytes) moves to the new end. The result is byte for byte the layout a
    single growth of all the appended records would make, so one descriptor still describes it.
    """
    from .nfl2k5_save_rost import decode
    require(0 <= records < 0x10000, 'invalid capacity record request')
    require(is_capacity_size(arena_size) and arena_size > ARENA_SIZE, 'unsupported capacity arena size')
    payload = bytes(payload)
    document = decode(payload)
    layout = document.layout
    primary = document.tables['primary']
    require(primary.offset is not None, 'missing primary player table')
    prior = read(payload, layout.root, layout.end, layout.version)
    root = layout.root
    old_count = primary.count
    if prior is not None:
        descriptor = capacity_descriptor(payload, layout)
        require(descriptor is not None, 'arena settings differ; rebuild from the original')
        appended, old_end = descriptor
        if layout.arena_size == arena_size and not in_place:
            fill = capacity_class_records(old_count - appended, records, old_end - root, arena_size)
            ok = (records <= appended <= records + fill if class_records is None
                  else appended == records + class_records)
            require(ok, 'arena settings differ; rebuild from the original')
            return payload, {'already_applied': True, 'changed_bytes': 0, 'file_growth': 0,
                             'capacity_records': appended, 'arena_size': layout.arena_size}
        require(layout.arena_size < arena_size or (in_place and layout.arena_size == arena_size),
                'capacity arena is already larger than requested')
        # Extension: only free class records are added; the existing vacancies stay as they are.
        vacancies = 0
        base_count = old_count - appended
        tail_from = root + layout.arena_size - CAPACITY_TAIL - CAPACITY_DESCRIPTOR_SIZE
        names_old_start = (old_end + appended * 84 + 1) & ~1
        names_old_end = names_old_start + appended * 68
        # b779 up2: a save the game wrote can hold more name strings after the descriptor's names (the v0.7 game
        # puts 21 blank-name buffers there for its Create Player records); they move with the growth, after the
        # new names, and the pointers that select them are rebased.
        extra_end = tail_from
        while extra_end > names_old_end and not payload[extra_end - 1]:
            extra_end -= 1
        extra_end = min(tail_from, (extra_end + 1) & ~1)
        # A game-written save re-points some records at buffers that straddle the descriptor's names end; the
        # relocated block starts at the first such buffer so no string is cut.
        extra_from = names_old_end
        if extra_end > names_old_end:
            for field in pointer_fields(document):
                target = document.rel(field, label='capacity relocation')
                if target is not None and names_old_end - NAME_BUFFER < target < names_old_end:
                    extra_from = min(extra_from, target)
        extra = bytes(payload[extra_from:extra_end])
        free = (capacity_class_records(base_count, appended, old_end - root + max(0, extra_end - names_old_end), arena_size)
                if class_records is None else class_records)
        source = 'capacity'
    else:
        require(layout.version in (0, 17), 'capacity growth requires a retail or saved roster')
        require(layout.arena_size in (RETAIL_SIZE, 0x90F20), 'capacity growth requires the retail arena')
        appended, old_end, vacancies = 0, layout.end, records
        extra, extra_from = b'', None
        base_count = old_count
        free = (capacity_class_records(base_count, records, old_end - root, arena_size)
                if class_records is None else class_records)
        names_old_end = None
        source = 'retail'
    require(type(free) is int and free >= 0, 'invalid class record request')
    class_template = _class_template(payload, document, primary) if free else None
    wanted = free
    if class_records is None and class_template is None:
        free = 0        # no free first-class record to copy (a synthetic or emptied roster): vacancies only
    if in_place and free == 0:
        return payload, {'already_applied': True, 'changed_bytes': 0, 'file_growth': 0, 'capacity_records': appended,
                         'arena_size': layout.arena_size, 'class_records': 0, 'class_records_wanted': wanted,
                         'reason': 'no free draft-class record in the save to copy' if wanted else ''}
    total = appended + vacancies + free
    # an extension with nothing to copy (no free first-class record) still moves the tail to the bigger arena
    require(0 < total < 0x10000 and (vacancies + free > 0 or prior is not None), 'nothing to append')
    require(base_count + total <= CAPACITY_PRIMARY_LIMIT, 'the primary pool would exceed MyCareer\'s 4,096 records')
    point = primary.offset + old_count * 84
    insert = (vacancies + free) * 84
    names_start = (old_end + total * 84 + 1) & ~1
    names_end = names_start + total * 68
    block_at = root + block_offset(arena_size)
    require(names_end + len(extra) <= block_at - CAPACITY_DESCRIPTOR_SIZE,
            'capacity records and names do not fit the arena')
    names_shift = free * 68 if extra else 0       # the extra name strings follow the new names
    extra_moves = (names_old_end - extra_from + insert + names_shift) if extra else 0
    fields = pointer_fields(document)
    targets = {field: document.rel(field, label='capacity relocation') for field in fields}
    source_end = layout.end if prior is None else tail_from

    def moved(value):
        if value is None:
            return None
        require(value < source_end, 'pointer outside the source arena')
        if extra and value >= extra_from:
            return value + extra_moves
        return value + insert if value >= point else value

    # The last blank create record is the vacancy template; the last free window record is the class template.
    template = None
    if vacancies:
        for index in range(old_count - 1, 0, -1):
            at = primary.offset + index * 84
            if payload[at + 8] & 5 != 1:
                continue
            first = document.rel(at + 0x10)
            last = document.rel(at + 0x14)
            if first is None or last is None or last != first + 34:
                continue
            if document.original[first:first + 34] == '****************'.encode('utf-16le') + b'\0\0' \
                    and document.original[last:last + 34] == '****************'.encode('utf-16le') + b'\0\0':
                template = at
                break
        require(template is not None, 'capacity growth needs a blank create record to copy')
    require(not free or class_template is not None, 'capacity growth needs a free first-class record to copy')
    templates = {}
    for kind, at in (('vacancy', template), ('class', class_template)):
        if at is not None:
            templates[kind] = (payload[at:at + 84], {field: document.rel(at + field) for field in TABLE_POINTERS['primary']})

    if prior is None:
        new_end = root + arena_size
        out = bytearray(payload[:point]) + bytearray(insert) + bytearray(payload[point:old_end])
        out.extend(bytes(new_end - len(out)))
        out.extend(payload[old_end:])
    else:
        new_end = root + arena_size
        tail = payload[tail_from:layout.end]
        keep_to = extra_from if extra else names_old_end
        out = bytearray(payload[:point]) + bytearray(insert) + bytearray(payload[point:keep_to])
        if extra:
            require(not any(f >= extra_from for f in fields), 'a relocation field lies in the extra name strings')
            out.extend(bytes(names_old_end + insert + names_shift - len(out)))   # new names are written below
            out.extend(extra)
        out.extend(bytes(new_end - len(tail) - len(out)))
        out.extend(tail)
        out.extend(payload[layout.end:])
        require(len(out) == len(payload) + arena_size - layout.arena_size, 'capacity extension length mismatch')
    for field, target in targets.items():
        field_at = moved(field)
        target_at = moved(target)
        struct.pack_into('<i', out, field_at, 0 if target_at is None else target_at - field_at + 1)
    struct.pack_into('<I', out, root, old_count + vacancies + free)
    star = '****************'.encode('utf-16le') + b'\0\0'
    for i in range(vacancies + free):
        kind = 'vacancy' if i < vacancies else 'class'
        raw, template_targets = templates[kind]
        at = point + i * 84
        out[at:at + 84] = raw
        for field in TABLE_POINTERS['primary']:
            target_at = moved(template_targets[field])
            # A blank create record has no college/history identity; new vacancies start null. A class record keeps
            # the window's college (the class generator does not set one; a null college bugchecks the FA panel).
            if field == 0x2C or (field == 0 and kind == 'vacancy'):
                target_at = None
            struct.pack_into('<i', out, at + field, 0 if target_at is None else target_at - at - field + 1)
        name = names_start + (appended + i) * 68
        blank = star if kind == 'vacancy' else bytes(34)
        out[name:name + 34] = blank
        out[name + 34:name + 68] = blank
        for field, target_at in ((0x10, name), (0x14, name + 34)):
            struct.pack_into('<i', out, at + field, target_at - at - field + 1)
    if prior is None:
        struct.pack_into('<I', out, layout.preamble + 0x10,
                         SAVE_VERSION if layout.version == 0 else DISC_VERSION)
    descriptor_at = block_at - CAPACITY_DESCRIPTOR_SIZE
    out[descriptor_at:descriptor_at + CAPACITY_DESCRIPTOR_SIZE] = struct.pack(
        '<8sII', CAPACITY_MAGIC, total, old_end)
    if prior is None:
        write_block(out, root, Overflow(reserves_enabled=False), arena_size=arena_size)
    if layout.wrapper is not None:
        struct.pack_into('<I', out, layout.wrapper + 4, root + arena_size - layout.preamble)
        if layout.version in (0, 1) and prior is None:
            auxiliary = struct.unpack_from('<I', payload, layout.wrapper + 8)[0]
            if not auxiliary and any(payload[old_end - 366:old_end]):
                # Some real saves leave the native 366-byte auxiliary tail undeclared (wrapper +8 = 0)
                # while the tail still holds state. Preserve it and declare it in the grown wrapper.
                auxiliary = 366
            require(auxiliary <= CAPACITY_TAIL - BLOCK_SIZE,
                    'native auxiliary tail overlaps the capacity block')
            if auxiliary:
                out[new_end - auxiliary:new_end] = payload[old_end - auxiliary:old_end]
                struct.pack_into('<I', out, layout.wrapper + 8, auxiliary)
        elif layout.version in (17, 18):
            struct.pack_into('<I', out, layout.wrapper + 8, root + arena_size - layout.preamble)
    result = bytes(out)
    final = decode(result)
    require(final.layout.arena_size == arena_size, 'capacity arena size mismatch')
    require(final.tables['primary'].count == old_count + vacancies + free, 'capacity record count mismatch')
    require(capacity_descriptor(result, final.layout) == (total, old_end), 'capacity descriptor mismatch')
    require(read(result, final.layout.root, final.layout.end, final.layout.version) is not None,
            'capacity block missing after growth')
    return result, {'already_applied': False, 'experimental': True, 'runtime_witnessed': False,
                    'source': source, 'in_place': in_place, 'arena_size_before': layout.arena_size,
                    'arena_size': arena_size, 'capacity_records': total,
                    'vacancy_records': vacancies, 'class_records': free,
                    'primary_before': old_count, 'primary_after': old_count + vacancies + free,
                    'primary_limit': CAPACITY_PRIMARY_LIMIT,
                    'record_insert_offset': point, 'record_insert_bytes': insert,
                    'names_start': names_start, 'names_end': names_end,
                    'block_offset': block_offset(arena_size), 'pointer_fields_rebased': len(fields),
                    'file_growth': len(result) - len(payload),
                    'before_sha256': hashlib.sha256(payload).hexdigest(),
                    'after_sha256': hashlib.sha256(result).hexdigest()}


def fill_class_records(payload: bytes, class_records: int | None = None) -> tuple[bytes, dict]:
    """b780 b10: add the free draft-class records a capacity save lacks, inside the arena it already has.

    The v0.8 game moves a v0.7 save's tail to the bigger arena the first time it saves it, but it adds none of the 865
    draft-class records, so Franchise > Upgrade used to find "already the disc's arena size" and stop. The extension
    code runs unchanged on such a save: the records go after the primary table, their names after the descriptor's
    names, every pointer is rebased and the descriptor is rewritten, but the arena, the tail and everything after
    the arena keep their place (``file_growth`` is 0). A save that already holds all the records that fit is returned
    as it is; so is one with no capacity descriptor or no free class record to copy, with the reason in the receipt.
    """
    from .nfl2k5_save_rost import decode
    document = decode(bytes(payload))
    layout = document.layout
    require(is_capacity_size(layout.arena_size), 'in-place class records need a capacity arena')
    require(layout.version in (SAVE_VERSION, DISC_VERSION), 'in-place class records need a saved or disc roster')
    if capacity_descriptor(bytes(payload), layout) is None:
        return bytes(payload), {'already_applied': True, 'changed_bytes': 0, 'file_growth': 0, 'class_records': 0,
                                'arena_size': layout.arena_size,
                                'reason': 'this save has no capacity descriptor (the game migrated it itself)'}
    return _migrate_capacity(bytes(payload), 0, class_records, layout.arena_size, in_place=True)


def _legacy_capacity(payload: bytes, layout) -> bytes:
    """Inverse of _migrate_capacity for the retail-geometry inspectors."""

    from .nfl2k5_save_rost import decode
    document = decode(payload)
    descriptor = capacity_descriptor(payload, layout)
    require(descriptor is not None, 'not a capacity-grown roster')
    records, old_end = descriptor
    primary = document.tables['primary']
    require(primary.offset is not None, 'missing primary player table')
    if records == 0:
        return payload
    point = primary.offset + (primary.count - records) * 84
    insert = records * 84
    fields = pointer_fields(document)
    targets = {field: document.rel(field, label='capacity reverse') for field in fields}

    def unmoved(value):
        if value is None:
            return None
        require(value < layout.end, 'pointer outside the grown arena')
        if value >= names_start:
            require(value >= point + insert, 'pointer selects a removed capacity name')
        return value - insert if value >= point + insert else value

    names_start = old_end + insert
    fa = document.tables['free_agents']
    kept = fa.count
    if fa.offset is not None:
        while kept and (lambda target: target is not None and point <= target < point + insert)(
                document.rel(fa.offset + (kept - 1) * 4)):
            kept -= 1
        require(all(not (lambda target: target is not None and point <= target < point + insert)(
                    document.rel(fa.offset + i * 4)) for i in range(kept)),
                'a retained free agent selects a removed capacity record')
    out = bytearray(payload[:point]) + bytearray(payload[point + insert:names_start])
    out.extend(payload[layout.end:])
    for field, target in targets.items():
        if point <= field < point + insert or field >= layout.end:
            continue
        field_at = unmoved(field)
        target_at = unmoved(target)
        struct.pack_into('<i', out, field_at, 0 if target_at is None else target_at - field_at + 1)
    struct.pack_into('<I', out, layout.root, primary.count - records)
    if fa.offset is not None:
        struct.pack_into('<I', out, layout.root + 0x38, kept)
    struct.pack_into('<I', out, layout.preamble + 0x10, 17 if layout.version == DISC_VERSION else 0)
    if layout.wrapper is not None:
        struct.pack_into('<II', out, layout.wrapper + 4, old_end - layout.preamble,
                         old_end - layout.preamble)
    result = bytes(out)
    from .nfl2k5_save_rost import decode as _decode
    check = _decode(result)
    require(check.tables['primary'].count == primary.count - records, 'capacity reverse mismatch')
    require(check.tables['free_agents'].count == kept, 'capacity reverse free agents mismatch')
    return result


def legacy_disc_resource(payload: bytes) -> bytes:
    """Read-only inverse of migrate() for a grown disc main ROST (version 18).

    The retail-geometry inspectors (2026 team names, team history, prospect names, star tags) read a
    grown disc roster through this view; their writers still refuse it. The two inserted created-team
    records and label rows are removed, every relocation field is rebased back, the overflow block is
    dropped, the NFL reserve marks take their retail value 0 (migrate() overwrites them) and the
    version-17 framing is restored. The view is returned only when migrate() of it reproduces the input
    byte for byte, so it is exactly the roster the build migrated.
    """
    from .nfl2k5_save_rost import decode
    from . import nfl2k5_practice_squad as ps
    payload = bytes(payload)
    if len(payload) in tuple(disc_resource_size(size) for size in CAPACITY_ARENA_SIZES):
        document = decode(payload)
        require(disc_resource_size(document.layout.arena_size) == len(payload), 'not a grown disc roster')
        legacy = _legacy_capacity(payload, document.layout)
        require(len(legacy) == LEGACY_DISC_RESOURCE_SIZE, 'capacity reverse is not retail geometry')
        return legacy
    require(len(payload) == GROWN_DISC_RESOURCE_SIZE, 'not a grown disc roster resource')
    document = decode(payload)
    layout, block = document.layout, document.overflow
    require(layout.version == DISC_VERSION and block is not None and layout.wrapper == 0
            and layout.end - layout.root == ARENA_SIZE and layout.end == len(payload), 'not a grown disc roster')
    root, teams, labels = layout.root, document.tables['teams'], document.tables['team_labels']
    inserted = ()
    if block.extra_teams:
        require(teams.count == 54 and labels.count == 38 and labels.offset is not None,
                'foreign grown created-team layout')
        inserted = ((teams.offset + 52 * 500, 1000), (labels.offset + 36 * 8, 16))

    def inside(offset):
        return any(start <= offset < start + size for start, size in inserted)

    def unmoved(offset):
        return offset - sum(size for start, size in inserted if offset >= start + size)
    body = bytearray(payload[root:root + ARENA_SIZE])
    for start, size in sorted(inserted, reverse=True):
        del body[start - root:start - root + size]
    out = bytearray(payload[:root]) + body[:LEGACY_DISC_RESOURCE_SIZE - root]
    for field in pointer_fields(document):
        if inside(field):
            continue
        target = document.rel(field)
        require(target is None or not inside(target), 'a retail relocation field points into a created record')
        struct.pack_into('<i', out, unmoved(field), 0 if target is None else unmoved(target) - unmoved(field) + 1)
    if block.extra_teams:
        struct.pack_into('<I', out, root + 0x18, teams.count - 2)
        struct.pack_into('<I', out, root + 0x48, labels.count - 2)
    for i in range(NFL_TEAMS):
        at = unmoved(teams.offset) + i * 500
        out[at + ps.VERSION_OFFSET] = out[at + ps.MARKER_OFFSET] = 0
    struct.pack_into('<I', out, layout.preamble + 16, 17)
    struct.pack_into('<II', out, layout.wrapper + 4, LEGACY_DISC_RESOURCE_SIZE - layout.preamble,
                     LEGACY_DISC_RESOURCE_SIZE - layout.preamble)
    result = bytes(out)
    require(migrate(result, reserves_16=block.reserves_enabled, created_teams_extra=block.extra_teams,
                    eligible_team_mask=block.eligible_mask)[0] == payload,
            'the grown roster is not a migration of a retail-geometry roster')
    return result


def grown_outer(archive, index: int) -> bool:
    """True when outer ``index`` of an OuterImage-style archive has a grown disc roster size."""
    entries = archive.entries
    return len(entries) > index and entries[index].size in (
        (GROWN_DISC_RESOURCE_SIZE,) + tuple(disc_resource_size(size) for size in CAPACITY_ARENA_SIZES))


def inspection_resource(archive, index: int) -> bytes:
    """A grown outer main roster as the retail-geometry inspectors read it: legacy_disc_resource()."""
    require(grown_outer(archive, index), 'not a grown disc roster entry')
    entry = archive.entries[index]
    return legacy_disc_resource(archive.read(entry.virtual_offset, entry.size))


def repack(payload: bytearray, document, team_index: int, active, reserves, *, mark=True) -> None:
    """Update native tail, overflow, metadata and CRC in one private candidate."""
    from . import nfl2k5_practice_squad as ps
    team = document.teams[team_index]
    pool = document.tables['primary']
    layout = document.layout
    block = read(payload, layout.root, layout.end, layout.version)
    active, reserves = tuple(active), tuple(reserves)
    raw = bytes(payload[team.offset:team.offset + 500])
    if block is None or team_index >= NFL_TEAMS:
        payload[team.offset:team.offset + 500] = ps.repack_team(
            raw, active, reserves, team_offset=team.offset, player_pool_offset=pool.offset,
            player_count=pool.count, mark=mark)
        return
    require(len(active) <= 65 and len(active) + len(reserves) <= 70, 'combined roster is full (70 players)')
    require(len(reserves) <= block.limit(team_index), f'practice squad is full ({block.limit(team_index)} players)')
    require(len(set(active + reserves)) == len(active) + len(reserves), 'duplicate roster identity')
    require(all(type(i) is int and 0 <= i < pool.count for i in active + reserves), 'invalid primary identity')
    native = (active + reserves)[:65]
    payload[team.offset:team.offset + 260] = bytes(260)
    for i, index in enumerate(native):
        field = team.offset + i * 4
        struct.pack_into('<i', payload, field, pool.offset + index * 84 - field + 1)
    payload[team.offset + ps.ACTIVE_COUNT] = len(active)
    payload[team.offset + ps.VERSION_OFFSET] = VERSION
    payload[team.offset + ps.COUNT] = len(reserves)
    payload[team.offset + ps.MARKER_OFFSET] = ps.MARKER
    write_block(payload, layout.root, block.with_row(team_index, (active + reserves)[65:]),
                arena_size=layout.arena_size)


def remap_reserves(original, candidate, identity_map):
    """Finish a containing pool writer's reserve remap, returning a private copy.

    The candidate must have valid, empty reserve rows after a shrinking pool.
    The containing writer must already have relocated active, FA and IR references
    and all other pool-index consumers. A complete old-index map is mandatory;
    None removes a retired identity. This function does not compact player bytes.
    Native import uses its own two-batch allocation map and E64D0 clears ownership
    before a primary slot can be reused.
    """
    from . import nfl2k5_save_rost as codec, nfl2k5_practice_squad as ps
    old, new = codec.decode(original), codec.decode(candidate)
    require(old.overflow is not None and new.overflow is not None, 'remap requires migrated arenas')
    require(len(old.teams) == len(new.teams), 'team ordinals changed during pool remap')
    require(set(identity_map) == set(range(old.tables['primary'].count)), 'incomplete primary identity map')
    values = [v for v in identity_map.values() if v is not None]
    require(all(type(v) is int and 0 <= v < new.tables['primary'].count for v in values)
            and len(set(values)) == len(values), 'invalid or aliased primary identity map')
    require(old.overflow.epoch == new.overflow.epoch and new.overflow.epoch < 0xFFFFFFFF,
            'pool epoch changed or exhausted')
    squads = ps.validate_roster(original)
    out = bytearray(candidate)
    pool = new.tables['primary']
    for team in new.teams:
        active = [(p-pool.offset)//84 for p in team.player_offsets]
        reserves = [identity_map[i] for i in squads[team.index] if identity_map[i] is not None]
        repack(out, new, team.index, active, reserves)
    block = read(out, new.layout.root, new.layout.end, new.layout.version)
    write_block(out, new.layout.root, replace(block, epoch=block.epoch+1), arena_size=new.layout.arena_size)
    ps.validate_roster(out)
    return bytes(out)


def migrate_save(source, target, *, reserves_16=True, created_teams_extra=0, eligible_team_mask=0,
                 capacity_records=0, class_records=None):
    """Verify the original signature and write/reopen a newly signed COPY."""
    from . import nfl2k5_save_rost as codec
    document, container = codec.load_save(source)
    payload, receipt = migrate(document.to_bytes(), reserves_16=reserves_16,
                               created_teams_extra=created_teams_extra, eligible_team_mask=eligible_team_mask,
                               capacity_records=capacity_records, class_records=class_records)
    written = container.write(target, payload)
    reopened, _ = codec.load_save(target)
    require(reopened.to_bytes() == payload, 'migrated signed copy differs')
    return {**receipt, 'signed_copy': written, 'experimental': True, 'runtime_witnessed': False}


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('validate', 'migrate'))
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--created-teams-extra', type=int, choices=(0, 2), default=0)
    parser.add_argument('--reserves-16', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--capacity-records', type=int, default=0,
                        help='grow to the capacity arena (CAPACITY_ARENA_SIZE) with this many create vacancies; '
                             'free class records fill the pool up to CAPACITY_PRIMARY_LIMIT')
    parser.add_argument('--eligible-team-mask', type=lambda s: int(s, 0), default=0)
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            from . import nfl2k5_save_rost as codec, nfl2k5_practice_squad as ps
            doc, _ = codec.load_save(args.source)
            squads = ps.validate_roster(doc.to_bytes())
            result = dict(version=doc.layout.version, arena_size=doc.layout.arena_size,
                          teams=len(doc.teams), reserves={str(k): len(v) for k,v in squads.items()},
                          experimental=True, runtime_witnessed=False)
        else:
            if args.output is None:
                parser.error('migrate requires --output for the signed copy')
            result = migrate_save(args.source, args.output, reserves_16=args.reserves_16,
                                  created_teams_extra=args.created_teams_extra,
                                  eligible_team_mask=args.eligible_team_mask,
                                  capacity_records=args.capacity_records)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'arena migration refused: {exc}\n')


if __name__ == '__main__':
    main()
