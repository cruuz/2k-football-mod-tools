"""Paired ROST allocation and native consumer migration. EXPERIMENTAL / UNWITNESSED.

Reserve REQUESTS in the complete union first. Existing practice-squad entry
addresses remain stable ABI bridges into sealed allocator code. Their original
owner validates the exact delegated installation before accepting those bytes.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_roster_arena as arena
from . import nfl2k5_roster_arena_code as assembly
from . import nfl2k5_xbe_space as space
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_practice_squad as ps
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = 'nfl2k5_roster_arena_growth'
CODE_SIZE = 8192
REQUESTS = ((OWNER, 'code', CODE_SIZE, 16),)
OPTION_OFFSET = (len(assembly.CODE) + 3) & ~3
HELP_TEXT = ('EXPERIMENTAL / UNWITNESSED. Retail: 65 player slots and two created teams. '
             'Patch: a larger roster save supports 16 reserves, an explicitly eligible 17th, '
             'and two optional extra created teams. Requires a migrated save.')
GUARDS = (
    (0xc0500, 0x227, 'eb0e521db60f858a2012e8bf17e648f6d8e58ebcbae0abe7e5fce385caeacf44'),
    (0xc0730, 0x225, 'a36864f678485ca058c4506c0829984abdff8afe38920f0d8d627828db2d77c6'),
    (0xc1e30, 0x4c, '379b8d859f833a1677e9166383ff1ba7f0af16c081727596636ff99cc17430e7'),
    (0xc1f00, 0x4f, '1ffd2c08ad85815ac48587bc51d1d7a2219c45c666e6e993ab90dbc47e6a119d'),
    (0xc1f90, 0xb0, '09b50a61bd32716f93d7e57a35235cbe85b1e4b911d9c4c6d15a554eeb711bb7'),
    (0xc2040, 0x13b, '2e1295f7287f5707b49f59df455eb22164804cac0cc8e50fee1d3d6dcee4f43c'),
    (0xc2180, 0x115, '2659d44266d6cfb39953d4bdba8eca2f5fa71c70a1c9b009723652e5b876dc04'),
)
BRIDGES = {
    **{name: name for name in ('ps_append', 'ps_fa_add', 'ps_clear', 'ps_rollover',
                               'ps_cut', 'ps_ir_append', 'ps_limit', 'ps_room',
                               'ps_trade_room', 'ps_demote', 'ps_promote', 'size_adapter')},
    'reserve_count': 'count_adapter', 'ps_export': 'arena_export', 'ps_import': 'arena_import',
}


class ArenaGrowthError(ValueError):
    """Mixed executable/resource state, unsupported configuration or missing allocation."""


def require(ok, message):
    if not ok:
        raise ArenaGrowthError(message)


def options(reserves_16=True, created_teams_extra=0):
    require(type(reserves_16) is bool and type(created_teams_extra) is int
            and created_teams_extra in (0, 2), 'select 16 reserves and/or zero or two extra teams')
    require(reserves_16 or created_teams_extra, 'select at least one arena growth option')
    return (0x100 if reserves_16 else 0) | created_teams_extra


def allocation(payload):
    matches = [a for a in space.layout(payload)['allocations'] if a['owner'] == OWNER]
    require(len(matches) == 1, 'reserve the complete arena growth allocator union first')
    result = matches[0]
    require((result['kind'], result['size'], result['align']) == ('code', CODE_SIZE, 16),
            'foreign arena growth allocation')
    return result


def code_for(va, flags):
    options(bool(flags & 0x100), flags & 255)
    require(flags & ~0x102 == 0, 'unknown arena executable options')
    out = bytearray(assembly.CODE)
    out.extend(b'\xcc' * (OPTION_OFFSET - len(out)))
    out.extend(struct.pack('<I', flags))
    symbols = {'code': va, 'arena_options': va + OPTION_OFFSET, '': 0}
    for off, kind, symbol, value in assembly.RELOCATIONS:
        addend = struct.unpack_from('<I', out, off)[0]
        target = symbols[symbol] + value + addend
        if kind == 2:
            target -= va + off
        struct.pack_into('<I', out, off, target & 0xFFFFFFFF)
    require(len(out) <= CODE_SIZE, 'arena growth exceeds its RX request')
    return bytes(out).ljust(CODE_SIZE, b'\xcc')


def _jump(va, target, size):
    return b'\xe9' + struct.pack('<i', target - va - 5) + b'\x90' * (size - 5)


def sites(va):
    from . import nfl2k5_practice_reserves as pr
    labels = {name: va + offset for name, offset in assembly.LABELS.items()}
    result = []
    for old_name, new_name in BRIDGES.items():
        address = ps.SYMBOLS[old_name]
        cave = next(s for s in ps.sites() if s.name == 'runtime' and s.va <= address < s.va + s.size)
        before = cave.patched[address - cave.va:address - cave.va + 5]
        require(len(before) == 5, 'bridge crosses its original owner extent')
        result.append((old_name, address, before, _jump(address, labels[new_name], 5)))
    for name, address, pin, target in (
        ('remove', 0xC3A90, '0fb6901c010000', 'remove_adapter'),
        ('save', 0xC1F90, 'a11829b700', 'arena_save'),
        ('load', 0xC2040, '568bf185f6', 'arena_load'),
        ('roster_load', 0xC2180, '85c90f840c010000', 'arena_load'),
        ('single_team_export', 0xC0FA0, '81ec04010000', 'arena_export_one'),
        ('created_predicate', 0x319370, '668b8018010000', 'created_adapter'),
    ):
        before = bytes.fromhex(pin)
        result.append((name, address, before, _jump(address, labels[target], len(before))))
    result.extend((
        ('arena_capacity', 0xC1F2D, bytes.fromhex('c7050828b70000100900'), bytes.fromhex('c7050828b70000200900')),
        ('arena_allocation', 0xC1F3C, bytes.fromhex('ba00100900'), bytes.fromhex('ba00200900')),
        ('resource_admission', 0xC1EB3, bytes.fromhex('393d0828b700'), bytes.fromhex('81ff60200900')),
        ('practice_projection', pr.STAGE_VA, pr.sites()[0][3], _jump(pr.STAGE_VA, labels['arena_stage'], pr.STAGE_SIZE)),
    ))
    return tuple(result)


def _check_guards(image, edits):
    for address, size, digest in GUARDS:
        raw = bytearray(image.read(address, size))
        for _name, va, before, after in edits:
            if address <= va and va + len(before) <= address + size:
                at = va-address
                require(bytes(raw[at:at+len(before)]) in (before, after), 'foreign guarded arena instruction')
                raw[at:at+len(before)] = before
        require(hashlib.sha256(raw).hexdigest() == digest, 'foreign arena load/save/relocation consumer')


def _owned_state(payload):
    layout = space.layout(payload)
    found = [a for a in layout['allocations'] if a['owner'] == OWNER]
    image = XbeImage(payload)
    _check_guards(image, sites(found[0]["va"] if found else 0))
    if not found:
        # Only our new hook sites are relevant before the base PS prerequisites
        # exist; their runtime caves remain the original owner's responsibility.
        for _name, address, before, _after in sites(0):
            if _name in ('remove', 'save', 'load', 'roster_load', 'single_team_export', 'created_predicate', 'arena_capacity',
                         'arena_allocation', 'resource_admission'):
                require(image.read(address, len(before)) == before, 'arena hook without allocation')
        require(ps._base_status(payload) != 'foreign', 'foreign unallocated reserve bridges')
        return 'retail', None, None
    site = allocation(payload)
    blob = image.read(site['va'], CODE_SIZE)
    edits = sites(site['va'])
    if blob == b'\xcc' * CODE_SIZE:
        for name, address, before, _after in edits:
            if name not in BRIDGES and name != 'practice_projection':
                require(image.read(address, len(before)) == before, 'arena hook with empty allocation')
        require(ps._base_status(payload) != 'foreign', 'reserve bridge installed with empty arena allocation')
        return 'retail', site, None
    flags = struct.unpack_from('<I', blob, OPTION_OFFSET)[0]
    require(blob == code_for(site['va'], flags), 'foreign arena runtime code/options')
    require(rdata.status(payload, edits) == 'applied', 'mixed arena runtime bridges/hooks')
    return 'applied', site, flags


def project(payload):
    """Restore only exactly verified delegated bytes for prerequisite status.

    Never normalize a partial/foreign installation or bypass the allocator seals.
    """
    state, site, _ = _owned_state(payload)
    if state == 'retail':
        return payload
    out = bytearray(payload)
    for _, address, before, _after in sites(site['va']):
        at = rdata.offset_of(payload, address)
        out[at:at + len(before)] = before
    for section in _sections(out):
        at = section.header_offset + 36
        out[at:at + 20] = section_digest(out, section)
    return bytes(out)


def status(payload):
    try:
        state = _owned_state(payload)[0]
        if state == 'applied':
            require(ps._base_status(project(payload)) == 'applied', 'missing practice-squad runtime')
        return state
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError, StopIteration):
        return 'foreign'


def read_settings(payload):
    state = status(payload)
    if state != 'applied':
        return {'status': state, 'reserves_16': False, 'created_teams_extra': 0}
    flags = _owned_state(payload)[2]
    return {'status': state, 'reserves_16': bool(flags & 0x100), 'created_teams_extra': flags & 255}


def apply(payload, *, reserves_16=True, created_teams_extra=0):
    flags = options(reserves_16, created_teams_extra)
    state = status(payload)
    require(state != 'foreign', 'foreign/mixed arena growth executable; refusing')
    common = {'owner': OWNER, 'experimental': True, 'runtime_witnessed': False,
              'reserves_16': reserves_16, 'created_teams_extra': created_teams_extra,
              'arena_size': arena.ARENA_SIZE, 'overflow_offset': arena.BLOCK_OFFSET,
              'active_limit': 53, 'reserve_limit': 16 if reserves_16 else 12,
              'eligible_reserve_limit': 17 if reserves_16 else 12, 'code_bytes': len(assembly.CODE),
              'code_capacity': CODE_SIZE, 'runtime_state_bytes': 0,
              'requires_paired_rost_resource': True, 'requires_save_migration': True}
    if state == 'applied':
        require(_owned_state(payload)[2] == flags, 'arena options differ; rebuild from original')
        return payload, {**common, 'already_applied': True, 'changed_bytes': 0}
    # Validate the full input before constructing any candidate. Each dependency
    # also pins complete foreign/mixed states, and all operations are copy-only.
    from . import nfl2k5_franchise_practice as fp
    from . import nfl2k5_practice_reserves as pr
    payload_before = payload
    if space.status(payload) == 'retail':
        payload, _ = space.apply(payload, REQUESTS, scaleout=True)
    site = allocation(payload)
    payload, _ = ps.apply(payload)
    payload, _ = fp.apply(payload)
    payload, _ = pr.apply(payload)
    require(rdata.status(payload, sites(site['va'])) == 'retail', 'foreign arena prerequisites')
    result, code_receipt = space.install_code(payload, OWNER, code_for(site['va'], flags))
    result, receipt = rdata.apply(result, sites(site['va']), OWNER)
    require(status(result) == 'applied', 'arena growth postcondition failed')
    return result, {**common, **receipt, 'already_applied': False, 'code_install': code_receipt,
                    'before_sha256': hashlib.sha256(payload_before).hexdigest(),
                    'after_sha256': hashlib.sha256(result).hexdigest(),
                    'file_growth': len(result) - len(payload_before),
                    'changed_bytes': sum(a != b for a, b in zip(payload_before, result)) + len(result) - len(payload_before),
                    'consumers': [{'name': name, 'address': hex(address)} for name, address, _, _ in sites(site['va'])]}
