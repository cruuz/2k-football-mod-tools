"""Beta 68 native series boundaries; physical plays remain UNWITNESSED.

Uses the beta-66 uninterrupted scene and installed presented-frame scheduler.
Ready-animation/camera completion, possession/snap/dead-ball commands and game
completion are explicit inputs. No outer update, possession, lineup, score or save callee is
substituted. The inherited scene/device services remain declared boundaries.
"""
from tests.nfl2k5_supersim_series import Machine as SeriesMachine


class Machine(SeriesMachine):
    def call(self, entry, *args, **kwargs):
        try:
            return super().call(entry, *args, **kwargs)
        except Exception:
            print('B68 native failure', entry,
                  {r: hex(self.reg(r)) for r in ('EIP', 'EAX', 'ECX', 'EDX', 'ESI', 'EDI')},
                  'football', self.get(0xE602B4), self.get(0xE602B8),
                  'camera', self.get(0xB616C0), 'pause', self.get(0xA83A14),
                  'phases', [hex(p) for p in getattr(self, 'frame_phases', [])], flush=True)
            raise


def ready_input(m):
    """The same loaded/completed readiness input as the 66.1 boundary suite."""
    for actor in m.actors:
        m.call(0x186160, ecx=actor, budget=2000000)
        descriptor = m.get(actor + 16)
        m.put(descriptor + 4, 0x50F1E4)
        m.put(descriptor + 0xD4, 0x63C8C0)
        m.put(descriptor + 0x110, 0)
    m.call(0x18C1F0, budget=2000000)
    m.call(0xE9210, args=(0x3C888889,), budget=2000000)
    if m.get(0xE602B8) != 13:
        raise AssertionError('native readiness did not reach pre-snap state 13')


def snap_input(m):
    offense = m.get(0xE60280)
    lineup = {m.uc.mem_read(m.get(a + 0x3C) + 53, 1)[0]: a
              for a in m.actors if m.get(a + 0x38) == offense}
    qb, center = lineup[0], lineup[12]
    # A direct result/re-spot leaves the ball enum at 1 until its receiver's
    # native possession event. Supply that omitted center animation event.
    m.call(0xB9B50, ecx=center, budget=3000000)
    before = (m.get(0xE602B8), m.get(0xE602C0))
    m.call(0x9FF80, edx=center, args=(qb,), budget=3000000)
    if m.get(0xE602B8) != 14:
        raise AssertionError(f'native snap did not enter live state 14: '
            f'phase={m.get(0xE602B4)}, state={m.get(0xE602B8)}, '
            f'snap={m.get(0xE602C0)}, plays={m.get(0xE53804)}, before={before}')
    m.call(0xB9B50, ecx=qb, budget=3000000)
    return qb


def possession_probe(payload):
    rows = []
    with Machine(payload) as m:
        m.series_scene(); m.presentation_services()
        original = m.get(0xE60280)
        for drive in range(3):
            context = m.get(0xE602EC)
            m.put(context + 4, 4)  # fourth-down situation, before this snap
            m.put(0xE60288, m.get(0xE60280))
            m.call(0xCD560, ecx=m.get(0xE60284), budget=2000000)
            m.call(0xA8680, budget=2000000)
            m.call(0x1B9E70, ecx=m.get(0xE60280), budget=2000000)
            ready_input(m)
            snap_input(m)
            before = m.counts['updates']
            m.presented_frame()
            if m.counts['updates'] - before != 8:
                raise AssertionError('Fast forward failed to resume at CPU snap')
            if drive == 0:
                m.put(0xB37A78, 0x200)
                before = m.counts['updates']
                m.presented_frame()
                if m.counts['updates'] - before != 1 or m.get(m.state + 2696) != 2:
                    raise AssertionError('B changed saved choice or failed to cancel')
                m.put(0xB37A78, 0)
                before = m.counts['updates']
                m.presented_frame()
                if m.counts['updates'] - before != 1:
                    raise AssertionError('cancel resumed before next snap')
            prior = m.get(0xE60280)
            m.call(0xA0390, budget=3000000)
            if m.get(0xE60280) == prior or m.get(0xE602B8) != 18:
                raise AssertionError('native fourth-down completion did not change possession')
            rows.append(dict(drive=drive, offense=hex(prior),
                next_offense=hex(m.get(0xE60280)), plays=m.get(0xE53804),
                saved_supersim=m.get(m.state + 2696)))
            m.offense, m.defense = m.get(0xE60280), m.get(0xE60284)
            m.call(0x189080, budget=3000000)
            m.cpu_choice()
            # The supplied dead-ball jump can leave the native camera's
            # world hold active. Supply its completion through the real setter
            # (A5AF0 reads B665E8); never bypass 64D3F's suppression branch.
            m.call(0xA5B00, ecx=0, args=(0,))
            if drive == 0:
                before = m.counts['updates']
                m.presented_frame()
                if m.counts['updates'] - before != 1:
                    raise AssertionError('cancel must wait through next pre-snap')
        if [r['offense'] for r in rows] != [hex(original), rows[0]['next_offense'], hex(original)]:
            raise AssertionError('three drives did not alternate sides')
        if m.counts['updates'] != m.counts['complete_updates']:
            raise AssertionError('native outer update did not finish')
        cadence = dict(m.counts)
        # Restore the real menu handlers after the frame fixture's device/menu
        # service. Complete via the native postgame parent, then open Settings.
        for va in (0xF3E90, 0xF3970):
            m.replace_stub(va, None)
        m.finish()
        if m.get(m.state + 2696) != 2:
            raise AssertionError('postgame changed Fast forward preference')
        m.select(5)
        label = m.get(m.labels['settings_rows'] + 52 + 4)
        if label != m.labels['m3_supersim_fast_text']:
            raise AssertionError('Apartment did not display Fast forward')
        m.call('inline_encode', ecx=m.state + 1280)
        encoded = m.uc.mem_read(m.state + 1280 + 82, 1)[0]
        if encoded & 10 != 8:
            raise AssertionError('postgame save encoded another Supersim choice')
        return dict(drives=rows, cadence=cadence, postgame_word=2,
                    apartment_label='Supersim: Fast forward', save_supersim_bits=encoded & 10)


def pat_probe(payload, *, modern=False):
    """TD scoring callback -> native try record -> choice -> kickoff.

The scorer identity, completed TD result and made conversion are supplied
events. The test does not claim physical scoring, kicking or controller UI.
"""
    rows = []
    with Machine(payload) as m:
        m.series_scene(); m.presentation_services()
        # The play-call update always advances this scene clock at AE7C6.
        # The CPU-only base fixture omitted it. Supply an empty loaded scene
        # and execute its native constructor, as for its other empty overlays.
        scene = m.BODIES + 0x1F000
        m.call(0x2F140, ecx=scene, budget=3000000)
        m.put(0xB719B8, scene)
        qb = next(a for a in m.actors if m.get(a + 0x38) == m.offense and
                  m.uc.mem_read(m.get(a + 0x3C) + 53, 1) == b'\0')
        m.adopt_native_player(qb)
        formation = m.get(m.get(m.offense + 12) + 8)
        play = m.get(m.get(m.offense + 12) + 12)
        ready_input(m)
        m.call(0xB6F30, budget=3000000)  # supplied snap/approach command
        m.call(0xB9B50, ecx=qb, budget=3000000)
        m.outer_frame()
        m.call(0xA0390, budget=3000000)
        context = m.get(0xE602EC)
        record = m.BODIES + 0x1E000
        m.put(context + 0x178, 1)
        m.put(context + 0x19C, qb)
        m.put(record + 0x14, m.offense)
        m.call(0x22E050, esi=record, budget=3000000)
        m.call(0xB8400, ecx=qb, budget=3000000)  # supplied touchdown scoring callback
        m.call(0x22E4D0, ecx=record, budget=3000000)
        m.call(0xA11F0, budget=20000000)
        if (m.get(0xE602B4) != 3 or m.get(0xE602B8) != 11 or
                not m.call(0x1891B0, ecx=m.offense) or
                m.get(m.get(m.offense + 12) + 36) & 8):
            raise AssertionError('native PAT play-call screen was skipped')
        initial = m.checkpoint()
        for kick in (False, True):
            m.restore(initial)
            base = 0xB75A40 + (0x13390 if m.offense == 0xE5FC60 else 0)
            # Native ATL Field Goal formation/play; scrimmage uses the actual
            # previously chosen record. These are play-menu selection inputs.
            chosen_formation = base + 0x134 + 37 * 180 if kick else formation
            chosen_play = base + 0x33FC + 220 * 96 if kick else play
            m.call(0xA31E0, ecx=chosen_play, edx=chosen_formation,
                   args=(0,), budget=20000000)
            if m.get(m.get(m.offense + 12) + 8) != chosen_formation:
                raise AssertionError('native selection ignored the chosen formation')
            spot = abs(m.f32(context + 0x18))
            expected = 3200.4 if kick and modern else 4389.12
            if abs(spot - expected) > .01:
                raise AssertionError(f'PAT spot {spot} differs from {expected}')
            # Both completed-try scoring callbacks retain the scoring side
            # and choose native kickoff phase 2. No phase or score word is set.
            m.call(0xB8420 if kick else 0xB8480, ecx=qb, budget=3000000)
            m.call(0x189080, budget=3000000)
            m.cpu_choice()
            m.presented_frame()
            if (m.get(0xE602B4) != 2 or m.get(0xE602B8) != 13 or
                    m.get(m.state + 2696) != 2 or not m.get(m.state + 2716)):
                raise AssertionError('PAT did not restore Fast forward at CPU kickoff')
            kicker = next(a for a in m.actors if m.get(a + 0x38) == m.offense and
                m.uc.mem_read(m.get(a + 0x3C) + 53, 1) == b'\x01')
            m.call(0xB9B50, ecx=kicker, budget=3000000)
            m.call(0xB6F30, budget=3000000)
            if m.get(0xE602B8) != 14:
                raise AssertionError('native kickoff approach did not start')
            rows.append(dict(choice='kick' if kick else 'two points', spot_cm=spot,
                kickoff_phase=2, ready_state=13, approach_state=14,
                saved_supersim=m.get(m.state + 2696), cadence=dict(m.counts)))
    return dict(modern_kick_rules_and_clock=modern, choices=rows)
