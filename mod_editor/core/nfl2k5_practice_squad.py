"""Experimental franchise practice squads: 53 active plus up to 12 reserves.

The brief's 16-entry side-list was disproved: +19C..+1A9 is future cap
accounting, +1AA..+1F1 contains live season statistics. The permitted fallback
uses the existing 65-pointer array, with active pointers followed immediately
by up to 12 reserve pointers, then explicit NULL sentinels. All 65 participate
in the unmodified retail loader/serializer. Metadata uses padding only:
+19B = version 1, +1F2 = count, +1F3 = marker A5. Legacy metadata is all zero.

reserve_list/set_reserve_list take a serialized 500-byte team record. Without
pool coordinates, identities are byte offsets relative to the team record;
with team_offset and player_pool_offset they are primary player indices.
They validate storage, not complete ownership. validate_roster validates the
whole ROST after a transaction. Engine promote/demote also enforce ownership.

All runtime state is in writable roster memory. Generated original C/assembly
is reproducible with tools/practice_squad/build_runtime.py. No in-game UI is
added. See ASTRA_PRACTICE_SQUAD_REPORT.md for proof boundaries and simplifications.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from typing import Iterable, Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_practice_squad_runtime import CAVES, SYMBOLS

TEAM_SIZE = 0x1F4
ACTIVE_LIMIT = 53
RESERVE_LIMIT = 12
VERSION = 1
VERSION_OFFSET = 0x19B
COUNT = 0x1F2
MARKER_OFFSET = 0x1F3
MARKER = 0xA5
EMPTY = 0
ACTIVE_COUNT = 0x11C
RETAIL_SHA256 = '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
CAVE_PINS = {
    0x374111: '17750d4dd2974aaa113b8be392dae37f3829e6b1d62c63331335fb26fedb7325',
    0x3BA610: '61574f4d1e18a37f9f14d2860cf8068cb958986bd16dd6f227686d6cf23ae1ac',
    0x3DCB20: 'cbfbc602761355d62e013dd99a172ee94d32c1930f718ad4acf968668670276c',
    0x3BABE0: '3618380916966b2e4b00ffe433e604ff54dc7dd724aa0ba5e969ffce360f3a41',
    0x3D1E20: 'c9679f0a501810dd16cdd5dec5bd1d50aa4b45c8861a357d75c997a042398e03',
    0x3E1600: 'dd57bd505fb9c011367df66de970f7a36439606f9aff3a987efafdb0c2f433f0',
    0x3E81B0: '3331e4d46bf069569197ea5a9e9b5df408ffa0c7a2d6a75b6e7b89e867cb6a78',
    0x3EE0D0: 'b31438428c4cf0ef1e8ece87a0ae62da67521501fb12bf4a16bcb0b233bc324c',
    0x2EAEE0: 'fbe47b9ca9b5eab39cdd3fe3f44bef1628c56b17dd96623f539c87129e703e19',
    0x3D1610: '515c12a4e6f69edaa3d8b461cfb02e2684310a06e90cf47801ac450e0d153ee2',
    0x2952B0: '54a22018feff00113ab406137df13fdce3e78ec7d7ef1aac9e30f5ff8d5e4834',
}


class PracticeSquadError(ValueError):
    """Foreign storage, conflicting ownership, or unsupported executable."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise PracticeSquadError(reason)


def _record(team_record: bytes | bytearray | memoryview) -> tuple[bytes, int, int, tuple[int | None, ...]]:
    data = bytes(team_record)
    _require(len(data) == TEAM_SIZE, 'expected one 500-byte team record')
    active = data[ACTIVE_COUNT]
    version, count, marker = data[VERSION_OFFSET], data[COUNT], data[MARKER_OFFSET]
    _require((version, count, marker) == (0, 0, 0) or
             (version == VERSION and marker == MARKER), 'unsupported reserve metadata')
    _require(count <= RESERVE_LIMIT and active + count <= 65, 'reserve/physical roster capacity exceeded')
    refs = tuple(i*4 + value - 1 if value else None
                 for i, value in enumerate(struct.unpack_from('<65i', data)))
    _require(all(x is not None for x in refs[:active+count]), 'null occupied player reference')
    _require(all(x is None for x in refs[active+count:]), 'nonempty unused player slot')
    _require(len(set(refs[:active+count])) == active+count, 'duplicate active/reserve player identity')
    return data, active, count, refs


def reserve_list(team_record: bytes | bytearray | memoryview, *, team_offset: int = 0,
                 player_pool_offset: int | None = None) -> tuple[int, ...]:
    """Return reserve identities; optionally resolve to primary pool indices."""
    _data, active, count, refs = _record(team_record)
    targets = refs[active:active+count]
    if player_pool_offset is None:
        return tuple(int(x) for x in targets)
    offsets = tuple(int(x) + team_offset - player_pool_offset for x in targets)
    _require(all(x >= 0 and x % 84 == 0 for x in offsets), 'reserve reference outside/alignment of primary pool')
    return tuple(x // 84 for x in offsets)


def set_reserve_list(team_record: bytes | bytearray | memoryview, identities: Iterable[int], *,
                     team_offset: int = 0, player_pool_offset: int | None = None,
                     player_count: int | None = None) -> bytes:
    """Copy-only storage edit; keep every cap/stat field and all active slots.

    Supply both pool coordinates to use indices. Otherwise identities are
    team-relative byte offsets, exactly as returned by reserve_list(record).
    Existing ownership must be transferred before this low-level storage edit.
    """
    data, active, _count, refs = _record(team_record)
    values = tuple(identities)
    _require(len(values) <= RESERVE_LIMIT, 'practice squad is full (12 players)')
    _require(active + len(values) <= 65, 'physical roster is full (65 players)')
    _require(all(type(x) is int for x in values), 'expected integer player identities')
    if player_pool_offset is not None:
        _require(all(x >= 0 for x in values), 'negative primary index')
        if player_count is not None:
            _require(type(player_count) is int and player_count >= 0, 'invalid primary pool size')
            _require(all(x < player_count for x in values), 'reserve index outside primary pool')
        values = tuple(player_pool_offset + 84*x - team_offset for x in values)
    else:
        _require(player_count is None, 'player_count requires player_pool_offset')
    _require(len(set(values)) == len(values), 'duplicate reserve identity')
    _require(not set(values).intersection(refs[:active]), 'reserve player is still active')
    out = bytearray(data)
    out[active*4:260] = bytes(260-active*4)
    for i, target in enumerate(values, active):
        relative = target - 4*i + 1
        _require(-(1<<31) <= relative < (1<<31) and relative != 0, 'unrepresentable player reference')
        struct.pack_into('<i', out, 4*i, relative)
    out[VERSION_OFFSET], out[COUNT], out[MARKER_OFFSET] = VERSION, len(values), MARKER
    _record(out)
    return bytes(out)


def remap_reserve_list(team_record: bytes, identity_map: Mapping[int, int | None], **coordinates) -> bytes:
    """Explicit complete remap for import/compaction; None retires an identity.

    Active pointers must be remapped separately by the containing roster writer.
    No absent map entry is silently retained after a pool move.
    """
    read_coordinates = {k:v for k,v in coordinates.items() if k != 'player_count'}
    values = reserve_list(team_record, **read_coordinates)
    _require(all(x in identity_map for x in values), 'incomplete reserve identity remap')
    return set_reserve_list(team_record, (identity_map[x] for x in values if identity_map[x] is not None),
                            **coordinates)


def validate_roster(payload: bytes, *, ir_player_indices: Iterable[int] = ()) -> dict[int, tuple[int, ...]]:
    """Check ownership in a complete disc/v0-save ROST using the shared codec.

    IR belongs to the franchise container, not its ROST resource. The caller
    supplies its primary indices if validating that container's IR ownership.
    All-star aliases are excluded from active ownership (retail convention).
    """
    from .nfl2k5_save_rost import decode
    document = decode(payload)
    owners: dict[int, str] = {}
    primary = document.tables['primary']
    by_offset = {p.offset: p.index for p in document.players if p.pool == 'primary'}
    for team in document.teams:
        kind = struct.unpack_from('<I', payload, team.offset + 0x128)[0]
        if team.index < 32 or kind in (2, 4):
            for off in team.player_offsets:
                if off in by_offset:
                    owners.setdefault(by_offset[off], f'active team {team.index}')
    agents = document.tables['free_agents']
    if agents.offset is not None:
        for i in range(agents.count):
            off = document.rel(agents.offset + i * 4)
            if off in by_offset:
                owners.setdefault(by_offset[off], 'free agent')
    for index in ir_player_indices:
        _require(type(index) is int and 0 <= index < primary.count, 'invalid IR player index')
        owners.setdefault(index, 'injured reserve')
    squads = {}
    for team in document.teams:
        values = reserve_list(payload[team.offset:team.offset + TEAM_SIZE],
                              team_offset=team.offset, player_pool_offset=primary.offset)
        squads[team.index] = values
        for index in values:
            _require(index < primary.count, f'team {team.index}: reserve index outside primary pool')
            _require(index not in owners, f'team {team.index}: reserve {index} is already {owners.get(index)}')
            player = document.by_key['primary', index]
            flags = payload[player.offset + 8]
            _require(bool(flags & 4) and not flags & 0x18,
                     f'team {team.index}: reserve {index} is inactive, retired, or a draft prospect')
            owners[index] = f'reserve team {team.index}'
    return squads


@dataclass(frozen=True)
class Site:
    name: str
    va: int
    patched: bytes
    retail: bytes | None = None
    digest: str | None = None

    @property
    def size(self) -> int:
        return len(self.patched)


def _branch(va: int, target: str, retail: str, *, call: bool = False) -> Site:
    pin = bytes.fromhex(retail)
    code = bytes((0xE8 if call else 0xE9,)) + struct.pack('<i', SYMBOLS[target] - va - 5)
    return Site(target, va, code + b'\x90' * (len(pin) - 5), pin)


def sites() -> tuple[Site, ...]:
    hooks = (
        _branch(0xC3EE0, 'ps_append', '8a811c010000'),
        _branch(0x242560, 'ps_fa_add', '8b013dc4090000'),
        _branch(0xE64D0, 'ps_clear', '53568bf10fb65e35'),
        _branch(0x247B40, 'ps_rollover', '53555657e867d3e7ff'),
        _branch(0xBFC30, 'size_adapter', '83ec0885c9'),
        _branch(0xC0B90, 'ps_export', '83ec1c8bc1'),
        _branch(0xC1030, 'ps_import', '81ec30010000'),
        _branch(0x2BFA6E, 'ps_cut', 'e88ddeffff', call=True),
        _branch(0x246FB6, 'ir_restore', 'e825cfe7ffc70600000000', call=True),
        _branch(0x323DD4, 'offer_limit', 'e8173df2ff', call=True),
        _branch(0x325B9E, 'capacity_flags', '80b81c01000041', call=True),
        _branch(0x3269DF, 'draft_limit', 'e89ce1d9ff0fb68e1c01000083e802f7d81bc083e0f583c0413bc8', call=True),
        _branch(0x322BB0, 'cpu_sign_guard', '81ec14010000'),
        _branch(0x323B30, 'pending_sign_guard', '51578bf86a01'),
        _branch(0x325B50, 'draft_sign_guard', '56578bfa8b54240c'),
        _branch(0x2BC670, 'trade_guard', '83ec088b44240c'),
        Site('remove_shift_start', 0xC3ABE, bytes.fromhex('9090'), bytes.fromhex('7d13')),
        Site('remove_shift_bound', 0xC3AC7, bytes.fromhex('4683fe407cf3') + b'\x90'*6,
             bytes.fromhex('0fb6901c010000463bf27ced')),
        Site('remove_null_last', 0xC3AD3, bytes.fromhex('c7800001000000000000') + b'\x90'*4,
             bytes.fromhex('0fb6901c010000c7049000000000')),

        Site('cpu_season_limit', 0x2BFACD, bytes.fromhex('ba35000000'), bytes.fromhex('ba36000000')),
        Site('human_season_limit', 0x2BF977, bytes.fromhex('b035'), bytes.fromhex('b036')),
        Site('season_limit_message', 0xE892B6, '53'.encode('utf-16-le'), '54'.encode('utf-16-le')),
        Site('phase_season_limit', 0x247AFE, bytes.fromhex('83e1f4'), bytes.fromhex('83e1f5')),
        Site('human_auto_cut_limit', 0x2BFD8C, bytes.fromhex('ba35000000'), bytes.fromhex('ba36000000')),
        Site('move_team_limit', 0x2B8340, bytes.fromhex('83fa35'), bytes.fromhex('83fa36')),
        Site('sign_limit_a', 0x36F844, bytes.fromhex('80bf1c01000035'), bytes.fromhex('80bf1c01000036')),
        Site('sign_limit_b', 0x36F9AC, bytes.fromhex('80bf1c01000035'), bytes.fromhex('80bf1c01000036')),
        Site('sign_limit_c', 0x36FC15, bytes.fromhex('80b81c01000035'), bytes.fromhex('80b81c01000036')),
        Site('sign_limit_d', 0x36FC39, bytes.fromhex('80b81c01000035'), bytes.fromhex('80b81c01000036')),
        Site('sign_screen_limit', 0x36ED17, bytes.fromhex('80b81c01000035'), bytes.fromhex('80b81c01000036')),
        Site('sign_limit_text', 0x36FD53, bytes.fromhex('c744240835000000'), bytes.fromhex('c744240836000000')),
        Site('trade_limit', 0x352A51, bytes.fromhex('83fe35'), bytes.fromhex('83fe36')),
        Site('trade_limit_text', 0x352A76, bytes.fromhex('c744243035000000'), bytes.fromhex('c744243036000000')),

    )
    caves = tuple(Site('runtime', va, code + b'\x90' * (size-len(code)), digest=CAVE_PINS[va])
                  for va, size, code in CAVES)
    return hooks + caves


def _offset(payload: bytes, va: int, sections) -> int:
    for section in sections:
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + va - section.virtual_address
    raise PracticeSquadError(f'VA 0x{va:X} is outside file-backed XBE sections')


def _state(payload: bytes, site: Site, sections) -> str:
    off = _offset(payload, site.va, sections)
    got = payload[off:off + site.size]
    if len(got) != site.size:
        return 'foreign'
    if got == site.patched:
        return 'applied'
    if site.retail is not None:
        return 'retail' if got == site.retail else 'foreign'
    return 'retail' if hashlib.sha256(got).hexdigest() == site.digest else 'foreign'


def status(xbe: bytes) -> str:
    """retail/applied/foreign; partial patches and malformed images fail closed."""
    try:
        sections = _sections(xbe)
        states = {_state(xbe, site, sections) for site in sites()}
        return states.pop() if len(states) == 1 else 'foreign'
    except (ValueError, struct.error, IndexError):
        return 'foreign'


def apply(xbe: bytes) -> tuple[bytes, dict[str, object]]:
    """Apply atomically to a copy and repair each changed XBE section digest."""
    state = status(xbe)
    _require(state != 'foreign', 'practice-squad sites are foreign or partially patched')
    receipt: dict[str, object] = {'status': 'applied', 'active_limit': ACTIVE_LIMIT,
        'reserve_limit': RESERVE_LIMIT, 'storage_version': VERSION,
        'preset_tier': 'EXPERIMENTAL', 'runtime_verified': False,
        'reserve_salary': 'zero cap cost; existing contract retained for promotion',
        'in_game_ui': False, 'changed_bytes': 0, 'sections_repinned': []}
    if state == 'applied':
        return bytes(xbe), receipt
    sections = _sections(xbe)
    out = bytearray(xbe)
    touched = set()
    for site in sites():
        off = _offset(xbe, site.va, sections)
        section = _section_for_offset(sections, off)
        _require(off + site.size <= section.raw_offset + section.raw_size, 'patch straddles XBE sections')
        out[off:off + site.size] = site.patched
        touched.add(section.index)
    for section in sections:
        if section.index in touched:
            at = section.header_offset + 36
            out[at:at+20] = section_digest(bytes(out), section)
    patched = bytes(out)
    _require(status(patched) == 'applied', 'practice-squad post-apply verification failed')
    receipt['changed_bytes'] = sum(a != b for a,b in zip(xbe, patched))
    receipt['sections_repinned'] = sorted(touched)
    return patched, receipt
