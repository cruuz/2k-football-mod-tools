"""Beta 69 native play-call hand-backs. Every physical outcome is UNWITNESSED.

The beta 68 scene, animation-completion, snap/dead-ball and game-completion
inputs remain explicit boundaries. Add empty loaded play-call background
scenes and the real match port mapper. Selection enters the same native
207440 callback used by AE66E/AE645; cursor drawing is not simulated.
"""
from tests.nfl2k5_b68_series import Machine, ready_input as _ready_input, snap_input


def ready_input(m):
    """Complete alignment with a valid native clip-slot input.

    B68's direct clip at descriptor+D4 was latent in its shorter paths.
    1FE0CD..1FE0E3 dereferences D4 once before selecting the clip. Supplying
    63C8C0 directly reads its 00540017 header as a pointer on the defensive
    return. Keep the same declared clip, behind the expected pointer slot.
    No native animation selection or sampling routine is substituted.
    """
    _ready_input(m)
    slot = m.BODIES + 0x1F400
    m.put(slot, 0x63C8C0)
    for actor in m.actors:
        m.put(m.get(actor + 16) + 0xD4, slot)


def menu_services(m, side):
    scene = m.BODIES + 0x1F000
    m.call(0x2F140, ecx=scene)
    m.put(0xB719B8, scene)
    cell, empty = m.BODIES + 0x1F200, m.BODIES + 0x1F300
    m.put(cell, empty)
    for pointer in (0xB38C3C, 0xB38C40): m.put(pointer, cell)
    for entry in (0x771F0, 0x77200): m.replace_stub(entry, None)
    m.call(0x77200, ecx=0, edx=1 if side == 0xE5FC20 else 2)


def policy_probe(payload, position, policy, *, drives=5):
    rows = []
    with Machine(payload) as m:
        m.series_scene(); m.presentation_services()
        actor = next(a for a in m.actors
                     if m.uc.mem_read(m.get(a + 0x3C) + 53, 1)[0] == position)
        m.adopt_native_player(actor)
        side = m.get(actor + 0x38)
        m.put(m.state + 2736, policy)
        # The initial scenario already has its first CPU-selected lineup.
        # Play it, then exercise actual absent/returning possessions twice.
        m.put(m.state + 2708, 0); m.put(m.state + 2716, 0)
        menu_services(m, side)
        for drive in range(drives):
            context = m.get(0xE602EC)
            m.put(context + 4, 4)  # supplied fourth-down situation
            m.put(0xE60288, m.get(0xE60280))
            m.call(0xCD560, ecx=m.get(0xE60284), budget=2000000)
            m.call(0xA8680, budget=2000000)
            m.call(0x1B9E70, ecx=m.get(0xE60280), budget=2000000)
            ready_input(m)
            present = bool(m.call('mode_unit_present'))
            if drive and present:
                choice = m.get(side + 12)
                group, formation, play, second = (m.get(choice + at) for at in (4, 8, 12, 16))
                m.presented_frame()
                human = policy == 0 or policy == 1 and position in (0, 11)
                menu = 0xB70B2C if side == m.get(0xE60280) else 0xB71840
                # Menu +174 stores the native admitted controller mask.
                if bool(m.call(0x1891B0, ecx=side)) != human:
                    raise AssertionError('first-play caller differs from saved policy')
                if human:
                    if not m.get(menu) or not m.get(menu + 0x174) or m.get(choice + 36) & 8:
                        raise AssertionError('native play-call screen/controller not open')
                    if side == m.get(0xE60280):
                        # A declared human menu choice: native ATL Split Pro,
                        # 90 Z Speed Under. Its personnel includes QB and HB.
                        book = 0xB75A40 + (0x13390 if side == 0xE5FC60 else 0)
                        group, formation = 0, book + 0x134
                        play = second = book + 0x33FC + 61 * 96
                    m.call(0x207440, ecx=side, edx=group,
                           args=(formation, play, second), budget=20000000)
                    if not m.get(choice + 36) & 8:
                        raise AssertionError('native menu selection was not accepted')
                    for _ in range(4): m.presented_frame()
                    ready_input(m)
                elif not m.get(choice + 36) & 8:
                    raise AssertionError('coach did not leave a native selected call')
                # Observe the installed input/frame binder, including the
                # personnel change after a menu selection, without calling
                # the binder ourselves to make the assertion pass.
                m.presented_frame()
                body = m.call('mode_unit_present')
                if not body or m.get(m.get(body + 12)) != 0 or m.get(0xBE4D60) != body:
                    raise AssertionError(f'human execution controller not restored: body={body:#x}, '
                        f'port={m.get(m.get(body + 12)) if body else None}, selected={m.get(0xBE4D60):#x}, '
                        f'wait={m.get(m.state + 2708)}, phase={m.get(0xE602B8)}')
                if m.get(m.state + 2708) or m.get(m.state + 2716):
                    raise AssertionError('hand-back retained Fast forward')
                rows.append(dict(drive=drive, menu=human, controller_port=0,
                                 selected=True, position=position, policy=policy))
            else:
                m.presented_frame()
            snap_input(m)
            before = m.counts['updates']; m.presented_frame()
            cadence = m.counts['updates'] - before
            if cadence != (1 if present else 8):
                raise AssertionError(f'snap cadence {cadence}, present={present}')
            if rows and rows[-1]['drive'] == drive: rows[-1]['snap_state'] = m.get(0xE602B8)
            m.call(0xA0390, budget=3000000)
            m.offense, m.defense = m.get(0xE60280), m.get(0xE60284)
            m.call(0x189080, budget=3000000)
            m.cpu_choice()
            m.call(0xA5B00, ecx=0, args=(0,))
            next_absent = not m.call('mode_unit_present')
            before = m.counts['updates']; m.presented_frame()
            if present and next_absent:
                updates = m.counts['updates'] - before
                if updates != 8 or not m.get(m.state + 2716):
                    raise AssertionError('Fast forward did not rearm after the human possession')
                if rows and rows[-1]['drive'] == drive:
                    rows[-1]['next_fast_forward_updates'] = updates
        if len(rows) != (drives - 1) // 2:
            raise AssertionError(f'missing hand-backs: {rows}')
        if m.counts['updates'] != m.counts['complete_updates']:
            raise AssertionError('native outer update did not complete')
        cadence = dict(m.counts)
        for entry in (0xF3E90, 0xF3970): m.replace_stub(entry, None)
        m.finish()
        if (m.get(m.state + 2696), m.get(m.state + 2736)) != (2, policy):
            raise AssertionError('post-game changed saved preferences')
        m.select(5)
        m.call('inline_encode', ecx=m.state + 1280)
        flags = m.uc.mem_read(m.state + 1280 + 82, 1)[0]
        if flags & 106 != 8 | policy << 5:
            raise AssertionError('post-game footer changed saved preferences')
        return dict(handbacks=rows, cadence=cadence, postgame_supersim=2,
                    postgame_policy=policy, saved_bits=flags & 106)
