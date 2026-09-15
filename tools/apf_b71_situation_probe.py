"""Bounded APF-3 witnesses; no image patch, emulator, or retail output files.

The lineup witness runs native category consumption, substitutions, depth
selection, eligibility checks and all eleven assignments. Only two equipment
refresh leaves are bounded out. Player pools are explicit synthetic inputs;
they are not a reconstruction of a saved roster or a gameplay witness.
"""
from __future__ import annotations

from tools.apf_playcall_research_probe import MANAGER, MASTER, TEAM
from mod_editor.core import apf2k8_splb_writer as splb


def straight_for_queens(index, plays=None):
    """The named edit, using the donor's 25 plays unless Fine-tune supplies IDs."""
    original = splb.read_book(index, 130)
    donor = splb.read_book(index, 1411)
    assert (original.name, donor.name) == ('O-ManBlock', 'O-Shotgun')
    record = next(r for r in donor.records if r.populated and r.formation_index == 133)
    ids = tuple(e.play_index for e in record.entries) if plays is None else tuple(plays)
    slot = next(r.record_index for r in original.records if not r.populated)
    changes = [splb.MembershipChange(130, slot, play, True) for play in ids]
    changes.append(splb.TrailerReplace(130, slot, 133, 7))
    compiled = splb.compile_book(original, changes)
    splb.verify_book(original.body, compiled.replacement, changes)
    queens = tuple(r.formation_index for r in original.records if r.populated and r.category_index == 6)
    assert queens == (2, 14, 24)
    stages = [(None, compiled.replacement)]
    body = compiled.replacement
    for formation in queens:
        body = splb.remove_formation(body, formation).book
        stages.append((formation, body))
    return original, tuple(stages)


def call_tuple(machine, address=TEAM + 4):
    result = []
    for d, offset, stride, count in ((0, 0x44, 16, 28), (4, 0x244, 184, 163), (12, 0x80C4, 100, 586)):
        pointer = machine.get(address + d)
        if not pointer:
            result.append(None)
            continue
        index, remainder = divmod(pointer - MASTER - offset, stride)
        assert remainder == 0 and 0 <= index < count, 'Foreign pointer in native call tuple'
        result.append(index)
    return tuple(result)


def finish_lineup(machine, *, tight_end_available=True):
    """Consume the already native-committed TEAM+4 call through 84859958.

    84859820 -> 848608B8 -> 84860020 -> 847B2DA0 -> 847B29E8,
    then 8485E768 writes player pointers and role bytes. No call/category,
    substitution, player-selection or assignment routine is replaced.
    The two intentionally bounded leaves refresh equipment, not personnel.
    """
    m = machine
    before = call_tuple(m)
    delta = 0x30 if m.updated else 0
    # The pinned native table maps role 8 (TE) to depth position 3, and
    # role 11 (FB) to depth position 2, on both images.
    role_table = 0x820B3D40 if m.updated else 0x820B3D30
    assert tuple(m.get(role_table + 8 * role + part) for role in (8, 11) for part in (0, 4)) == (3, 3, 2, 2)
    roster = 0x851D100C + delta  # Actual away roster getter 849D45A8 / 849D5470.
    m.put(MANAGER + 4, 0x3B0000)
    m.put(0x84F3F7DC, 0x3D0000)
    m.put(roster, 0x3F0000)
    m.put(roster + 4, 0)
    pool, depths = {}, []
    for position in range(28):
        m.put(roster + 0x70 + position * 4, 0x3F1000 + len(depths))
        count = int(tight_end_available) if position == 3 else 3 if position in (4, 5) else 1
        for depth in range(count):
            i = len(depths)
            player, descriptor = 0x3A0000 + i * 0x200, 0x3C0000 + i * 0x100
            pool[player] = (position, depth)
            m.put(0x3F0000 + i * 4, player)
            m.put(player + 0xDC, descriptor)
            m.put(descriptor, descriptor + 0x40)
            m.put(descriptor + 4, descriptor + 0x50)
            m.putf(descriptor + 0x54, 1.0)
            depths.append(i)
    m.put(roster + 0xE0, 0x3F1000 + len(depths))
    # Position 27 also accepts a sentinel-ended list; its search must terminate.
    m.cpu.mem_write(0x3F1000, bytes(depths) + b'\xff')
    for i in range(11):
        output = 0x3B0000 + i * 0x200
        m.put(output + 0x3C, output + 0x200 if i < 10 else 0)
        m.put(output + 0x44, 0x3A0000 + i * 0x200)
    requested, returned, attempts = [], [], []
    provider_delta = 0xAD8 if m.updated else 0
    observers = {
        0x847B29E8 + provider_delta: lambda z: requested.append((z.reg(6), z.reg(10))),
        0x847B2FF0 + provider_delta: lambda z: returned.append(pool.get(z.reg(3))),
        0x847B2A94 + provider_delta: lambda z: attempts.append((z.reg(24), z.reg(20), z.reg(23), z.reg(26))),
    }
    equipment = tuple(pc + (0xC20 if m.updated else 0) for pc in (0x847C1728, 0x847C16D0))
    assert not any(pc in m.observers for pc in observers)
    assert not any(pc in m.boundaries for pc in equipment)
    m.observers.update(observers)
    for pc in equipment:
        m.boundaries[pc] = lambda z: z.ret(0)
    start_steps = m.steps
    try:
        m.call(m.va(0x84859820), 1, stop=m.va(0x84859958), bound=2000000)
    finally:
        for pc in observers:
            del m.observers[pc]
        for pc in equipment:
            del m.boundaries[pc]
    players = [m.get(0x3B0044 + i * 0x200) for i in range(11)]
    assert len(set(players)) == 11 and all(player in pool for player in players)
    selected = [pool[player] for player in players]
    roles = [m.cpu.mem_read(0x3B0034 + i * 0x200, 1)[0] for i in range(11)]
    primary_roles = [m.cpu.mem_read(0x3B0035 + i * 0x200, 1)[0] for i in range(11)]
    slots = [m.cpu.mem_read(0x3B0036 + i * 0x200, 1)[0] for i in range(11)]
    after = call_tuple(m)
    assert before == after
    assert slots == list(range(11))
    assert (6, 8, 0, 3) in attempts
    assert ((6, 8, 1, 2) in attempts) is (not tight_end_available)
    return {'tuple_before': before, 'tuple_after': after,
            'role_to_depth_table': f'{role_table:08X}',
            'synthetic_pool_players': len(depths), 'tight_end_available': tight_end_available,
            'requested_roles': requested, 'provider_depths': returned,
            'selected_depths': selected, 'provider_attempts': attempts,
            'selected_te_depth_players': sum(position == 3 for position, _ in selected),
            'roles_34': roles, 'primary_roles_35': primary_roles, 'slots_36': slots,
            'instructions': m.steps - start_steps,
            'executed': [f'{pc:08X}' for pc in (m.va(0x84859820), m.va(0x848608B8),
                         m.va(0x84860020), 0x847B2DA0 + provider_delta,
                         0x847B29E8 + provider_delta, m.va(0x8485E768)) if pc in m.visited],
            'bounded_equipment_leaves': [f'{pc:08X}' for pc in equipment],
            'scope': 'PROVED bounded native with synthetic depth chart; gameplay UNWITNESSED'}
