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
BLOCK_SIZE = 352
BLOCK_OFFSET = 0x91C00
MAGIC = b"2K5RSV2\0"
VERSION = 2
SAVE_VERSION = 1
DISC_VERSION = 18
EMPTY = 0xFFFF
NFL_TEAMS = 32
OVERFLOW_SLOTS = 5
RESERVES_ENABLED = 0x100
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
        require(end - root != ARENA_SIZE, 'grown arena has a legacy version')
        return None
    require(end - root == ARENA_SIZE, 'grown ROST version has the wrong arena length')
    raw = bytes(payload[root + BLOCK_OFFSET:root + BLOCK_OFFSET + BLOCK_SIZE])
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


def write_block(payload: bytearray, root: int, block: Overflow) -> None:
    require(root + ARENA_SIZE <= len(payload), 'overflow write outside arena')
    payload[root + BLOCK_OFFSET:root + BLOCK_OFFSET + BLOCK_SIZE] = block.encode()


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
            eligible_team_mask: int = 0) -> tuple[bytes, dict]:
    """Copy-only v0/v17 migration. Eligibility is an explicit per-team decision.

    Created IDs 100/101 are distinct from retail special teams 92..99. New
    records inherit the two existing created slots' assets/playbooks, with
    separate labels. This does not add teams to the 32-team franchise league.
    """
    from .nfl2k5_save_rost import decode
    from . import nfl2k5_practice_squad as ps
    require(type(reserves_16) is bool, 'reserves_16 must be a boolean')
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
        require(len(by_id) == teams.count and 100 not in by_id and 101 not in by_id,
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
            struct.pack_into('<H', out, dest + 0x118, 100 + j)
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
                    'created_teams_extra': created_teams_extra, 'created_ids': [100, 101] if created_teams_extra else [],
                    'pointer_fields_rebased': len(fields), 'file_growth': len(result) - len(payload),
                    'before_sha256': hashlib.sha256(payload).hexdigest(),
                    'after_sha256': hashlib.sha256(result).hexdigest()}


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
    write_block(payload, layout.root, block.with_row(team_index, (active + reserves)[65:]))


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
    write_block(out, new.layout.root, replace(block, epoch=block.epoch+1))
    ps.validate_roster(out)
    return bytes(out)


def migrate_save(source, target, *, reserves_16=True, created_teams_extra=0, eligible_team_mask=0):
    """Verify the original signature and write/reopen a newly signed COPY."""
    from . import nfl2k5_save_rost as codec
    document, container = codec.load_save(source)
    payload, receipt = migrate(document.to_bytes(), reserves_16=reserves_16,
                               created_teams_extra=created_teams_extra, eligible_team_mask=eligible_team_mask)
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
                                  eligible_team_mask=args.eligible_team_mask)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'arena migration refused: {exc}\n')


if __name__ == '__main__':
    main()
