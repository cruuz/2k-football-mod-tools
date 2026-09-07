"""Native pre-kick state/pose proofs, exact executable replay and public receipts.

Run standalone with python3; --record explicitly refreshes only v4 evidence.
Synthetic clocks/clips/controller samples are inputs, never a console witness.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import RETAIL, PRIVATE_REASON, uni, x86, Cs
from tests.mod_editor.test_nfl2k5_kickoff_v3 import (
    patch_evidence, replay_edits, v3_payload, digest, HELD,
)
from tests.nfl2k5_kickoff_frame import PreKickMachine, WriteReceipt, PHASES, PREKICK_FIELDS, PREKICK_SITES
from mod_editor.core import nfl2k5_dynamic_kickoff as dk, nfl2k5_dynamic_kickoff_relocated as relocated
from mod_editor.core.nfl2k5_bump_strength import RETAIL_XBE_SHA256, _sections, section_digest

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / 'docs/nfl2k5_kickoff_v4_receipts.json'
TRACES = ROOT / 'docs/nfl2k5_kickoff_v4_frames.json'
WINDOWS = (('completed_lineup', 72, 12), ('ready_delay', 72, 13),
           ('approach', 24, 14), ('flight', 72, 14))


def held_state(snapshot):
    return {key: value for key, value in snapshot.items() if key[0] in HELD}


def exercise(test, payload, *, state, direction, historical=False):
    m = PreKickMachine(payload, state_va=state, direction=direction,
                       radius=30 if historical else 250)
    m.seed_residuals()
    trace, packets, native = WriteReceipt(), [], []

    def capture(label, snapshot):
        trace.add(m, snapshot)
        packets.append(label)
        native.append(m.native_state())
        return snapshot

    capture('initial_inputs', m.snapshot())
    capture('native_complete_held', m.complete_lineup(m.held))
    test.assertEqual(m.get(dk.PLAY_STATE), 12)
    previous = capture('entry_frame_0', m.frame())
    baseline = held_state(previous)
    changes, free_changes, windows = [], Counter(), []
    # The historical counterexample covers the newly observed state-12 gap.
    # The played v3 ready/approach/flight regression remains in the v3 suite.
    for name, count, play_state in (WINDOWS[:1] if historical else WINDOWS):
        if name == 'ready_delay':
            capture('native_complete_free', m.complete_lineup(m.free))
        elif name == 'approach':
            m.approach()
            capture('native_approach_command', m.snapshot())
        elif name == 'flight':
            m.phase = 0
            m.writes.clear()
            m.launch()
            test.assertEqual(m.flags() & 15, dk.ACTIVE)
            capture('native_launch_opcode_08', m.snapshot())
        # A three-frame historical counterexample suffices to retain every
        # changing writer without publishing seventy duplicate pose states.
        count = 3 if historical else count
        for frame in range(1, count + 1):
            current = capture(f'{name}_{frame}', m.frame())
            delta = Counter(kind for (p, kind), value in current.items()
                            if p in HELD and previous[p, kind] != value)
            changes.append([delta[k] for k in PREKICK_FIELDS])
            if not historical:
                test.assertEqual(held_state(current), baseline,
                                 f'{name} frame {frame}: {dict(delta)}')
            test.assertEqual(m.get(dk.PLAY_STATE), play_state)
            test.assertEqual(m.flags() & 7, 0, 'time/input released the hold')
            if play_state == 12:
                test.assertEqual(m.input_frames[-1], [1.0, 1.0])
            else:
                # Native ready/approach input routing can suppress coverage
                # throttle before our hook; retain its actual output as evidence.
                test.assertTrue(all(v in (0.0, 1.0) for v in m.input_frames[-1]))
            for p in (0, 11, 12):
                if current[p, 'transform'] != previous[p, 'transform']:
                    free_changes[p] += 1
            previous = current
        windows.append([name, count, play_state])
    if historical:
        for kind in ('transform', 'sampled_pose', 'turn_spring', 'primary_clock',
                     'head_rotation', 'skeleton_low', 'skeleton_high'):
            test.assertTrue(any(row[PREKICK_FIELDS.index(kind)] for row in changes), kind)
        test.assertTrue(any(e[3] == 0x1DF68A and e[5] != e[6] for e in trace.events))
        contact = None
    else:
        test.assertEqual(m.state_writes, [[0xE9210, 0x158CC1, 12, 13],
                                         [0, 0xB6FB3, 13, 14]])
        test.assertEqual(set(free_changes), {0, 11, 12})
        # Both added hook sites and every state/pose/input phase execute natively.
        for pc in (0x1853D0, 0x2111D0, 0x183CD0, 0x1881E0, 0x1FF940,
                   0x158C90, 0xB6F30, 0x1211E0, 0x70AF0, 0x28F310, 0x1DF430):
            test.assertGreater(m.visited[pc], 0, hex(pc))
            test.assertNotIn(pc, m.stub_pops)
        for phase in PHASES:
            test.assertEqual(m.visited[phase], 241)
            test.assertNotIn(phase, m.stub_pops)
        for who in m.held:
            test.assertEqual(m.get(who + 0x904), 0x50F4EC)
            test.assertEqual(m.get(who + 0xAA8), 0)
        before = m.flags()
        m.position(0, direction * 3600, m.RETURNER)
        event = 'ground' if direction < 0 else 'touch'
        m.event(event)
        test.assertEqual(m.flags() & 7, dk.LANDING)
        released = capture('first_contact_release_frame', m.frame())
        moved = [p for p in HELD if released[p, 'transform'] != previous[p, 'transform']]
        test.assertEqual(moved, list(HELD))
        for who in m.held:
            test.assertNotEqual(m.readf(m.get(who + 0xC58) + 4), 0)
        # The task's look request was kept. Native head tracking resumes as
        # soon as its next target is in view; at least one native interpolation
        # runs on this exact release frame in each field direction.
        test.assertTrue(any(e[1] == 'head_rotation' and e[5] != e[6]
                            for e in m.writes if e[0] in HELD))
        contact = dict(event=event, before=before, after=m.flags(), moved_players=moved)
    result = dict(direction=direction, historical=historical, radius=m.readf(0x2103C30),
                  windows=windows, packets=packets, native_states=native,
                  global_state_writes=m.state_writes, fields=list(PREKICK_FIELDS),
                  per_frame_changed_players=changes,
                  free_changed_frames={str(k): v for k, v in sorted(free_changes.items())},
                  decoded_input=[.8, -.6], native_prehold_throttle=m.input_frames,
                  native_calls={hex(k): m.visited[k] for k in sorted(PREKICK_SITES)},
                  phase_calls={hex(k): m.visited[k] for k in PHASES},
                  abi_leaf_calls={hex(k): v for k, v in sorted(Counter(m.calls).items())},
                  contact=contact, trace_sha256=trace.digest(),
                  total_held_player_writes=sum(len(trace.sequences[s]) for s, _ in trace.frames))
    return result, trace.result()


@unittest.skipUnless(RETAIL.is_file() and uni is not None and Cs is not None,
                     PRIVATE_REASON + '; unicorn/capstone required')
class V4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()  # bounded ~12 MB, never a disc/pack
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest('private retail XBE SHA-256 differs')
        cls.payloads, cls.evidence = patch_evidence(cls.retail)
        cls.base, cls.legacy, cls.allocated, cls.grown = cls.payloads
        cls.v3 = v3_payload(cls.base)

    def variants(self):
        return [('legacy', self.legacy, dk.FLAGS),
                ('grown', self.grown, relocated._sites(self.grown)[1]['va'])]

    def test_exact_replay_status_digests_and_mixed_new_hooks(self):
        receipt = json.loads(RECEIPT.read_text())
        for key, value in self.evidence.items():
            self.assertEqual(digest(value), digest(receipt[key]), key)
        for source, expected, name in ((self.base, self.legacy, 'legacy'),
                                       (self.allocated, self.grown, 'relocated')):
            self.assertEqual(replay_edits(source, receipt, name), expected)
            self.assertEqual(dk.status(expected), 'applied')
            self.assertEqual(dk.apply(expected)[0], expected)
            for section in _sections(expected):
                self.assertEqual(section.stored_digest, section_digest(expected, section))
            for hook in ('ready', 'head_pose'):
                va, pin = dk.HOOKS[hook]
                off = dk._offset(expected, va, len(pin))
                for replacement in (pin, b'\xcc' * len(pin)):
                    mixed = bytearray(expected)
                    mixed[off:off + len(pin)] = replacement
                    before = bytes(mixed)
                    self.assertEqual(dk.status(before), 'foreign')
                    with self.assertRaises(ValueError):
                        dk.apply(before)
                    self.assertEqual(bytes(mixed), before)
        self.assertEqual(dk.status(self.v3), 'foreign')
        with self.assertRaises(ValueError):
            dk.apply(self.v3)

    def test_native_pre_kick_sequence_240_frames_both_directions_and_placements(self):
        receipt = json.loads(RECEIPT.read_text())
        for placement, payload, state in self.variants():
            for direction in (-1, 1):
                key = f'{placement}_{direction:+d}'
                with self.subTest(case=key):
                    summary, trace = exercise(self, payload, state=state, direction=direction)
                    self.assertEqual(summary, receipt['cases'][key])
                    self.assertEqual(digest(trace), summary['trace_sha256'])

    def test_historical_v3_pre_kick_counterexample(self):
        summary, trace = exercise(self, self.v3, state=dk.FLAGS, direction=1, historical=True)
        self.assertEqual(summary, json.loads(RECEIPT.read_text())['cases']['v3_counterexample'])
        self.assertEqual(digest(trace), summary['trace_sha256'])

    def test_completion_readiness_and_guard_scope(self):
        for _, payload, state in self.variants():
            m = PreKickMachine(payload, state_va=state)
            code_va = dk.CAVE_VA if state == dk.FLAGS else relocated._sites(payload)[0]['va']
            _, labels = dk._code(dk._settings(), cave_va=code_va,
                                 storage_ranges=((state, 7), (dk.TB_YARD if state == dk.FLAGS else state + 7, 3)))
            # Readiness is still the native descriptor query before completion;
            # completed held roles survive replacement of ready by fixed idle.
            for who in m.players:
                m.put(who + 0x904, 0x50F4EC)
                m.run(0x1FF940, ecx=who)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)
            m.complete_lineup(m.held)
            for index, who in enumerate(m.players):
                m.run(0x1FF940, ecx=who)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), int(index in HELD))
            for play_state in range(25):
                m.put(dk.PLAY_STATE, play_state)
                for player_state in (12, 13, 14):
                    m.put(m.COVERAGE + 0x5E4, player_state)
                    m.run(labels['held'], ecx=m.COVERAGE)
                    expected = play_state in (13, 14) or (play_state == 12 and player_state == 13)
                    self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), expected)
            m.put(dk.PLAY_STATE, 12)
            m.put(m.COVERAGE + 0x5E4, 13)
            # Non-player late-pass objects may have no player-state pointer.
            saved_pointer = m.get(m.COVERAGE + 0x20)
            m.put(m.COVERAGE + 0x20, 0)
            for kind in (1, 2, 3):
                m.put(m.COVERAGE + 0x1C, kind)
                m.run(labels['held'], ecx=m.COVERAGE)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)
            m.put(m.COVERAGE + 0x1C, 1)
            m.put(m.COVERAGE + 0x20, saved_pointer)
            for address, value in ((dk.PHASE, 0), (dk.PHASE, 1), (m.COVERAGE + 0x48, 1),
                                   (m.COVERAGE + 0x1C, 2), (m.KICK_BOOK + 0x204, 10 << 8),
                                   (state, dk.LANDING), (state, dk.END_ZONE), (state, dk.SHORT),
                                   (state, dk.OUT)):
                saved = m.get(address)
                m.put(address, value)
                m.run(labels['held'], ecx=m.COVERAGE)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)
                m.put(address, saved)
            # A ready query must not clobber its player's ECX or callee-saved
            # registers and must preserve the native one-return-address ABI.
            for reg in (x86.UC_X86_REG_EBX, x86.UC_X86_REG_ESI,
                        x86.UC_X86_REG_EDI, x86.UC_X86_REG_EBP):
                m.uc.reg_write(reg, 0x24682468)
            m.run(0x1FF940, ecx=m.COVERAGE, esi=0x24682468)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 4)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ECX), m.COVERAGE)
            for reg in (x86.UC_X86_REG_EBX, x86.UC_X86_REG_ESI,
                        x86.UC_X86_REG_EDI, x86.UC_X86_REG_EBP):
                self.assertEqual(m.uc.reg_read(reg), 0x24682468)

    def test_fixed_idle_readiness_does_not_deadlock_native_transition(self):
        for _, payload, state in self.variants():
            for query_guard in (False, True):
                m = PreKickMachine(payload, state_va=state)
                m.complete_lineup(m.players)
                for who in m.held:
                    m.put(who + 0x904, 0x50F4EC)
                if not query_guard:
                    va, pin = dk.HOOKS['ready']
                    m.uc.mem_write(va, pin)  # explicit native-query counterexample
                m.frame()
                self.assertEqual(m.get(dk.PLAY_STATE), 13 if query_guard else 12)
                self.assertEqual(m.get(m.KICK_TEAM + 0x324) & 2, 2 if query_guard else 0)

    def test_fitted_diagram_instruction_body_is_unchanged(self):
        from capstone import CS_ARCH_X86, CS_MODE_32
        va, pin = dk.HOOKS['diagram']
        off = dk._offset(self.v3, va, len(pin))
        old_start = va + 5 + struct.unpack_from('<i', self.v3, off + 1)[0]
        _, labels = dk._code(dk._settings())
        size = labels['returner'] - labels['diagram']

        def instructions(payload, start):
            off = dk._offset(payload, start, size)
            result = []
            for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(payload[off:off + size], start):
                operand = ins.op_str
                if ins.mnemonic.startswith('j'):
                    target = int(operand, 16)
                    if start <= target < start + size:
                        operand = f'local+{target - start}'
                result.append((ins.mnemonic, operand))
            return result
        self.assertEqual(instructions(self.v3, old_start), instructions(self.legacy, labels['diagram']))

    def test_native_kicker_delay_and_early_approach_in_state_13(self):
        from mod_editor.core.nfl2k5_play_codec import Node
        for _, payload, state in self.variants():
            for controller, threshold_bits in ((-1, 0x3FCCCCCD), (0, 0x3F8CCCCD)):
                m = PreKickMachine(payload, state_va=state)
                m.complete_lineup(m.players)
                baseline = m.frame()
                self.assertEqual(m.get(dk.PLAY_STATE), 13)
                m.put(m.KICKER + 0x100, controller)
                m.f32(0xB71D00, 0)
                # Retail Kickoff Middle: Start(wait, ready) -> Ball Action(2)
                # -> Place Kick. Supply the decoded opcode-3 operand cache,
                # then execute its real initializer and kickoff-specific arm.
                m.uc.mem_write(m.OPS, Node(3, 6, [2]).to_bytes())
                m.f32(m.KICKER + 0x630, 2)
                m.run(0x2D3E80, ecx=m.KICKER)
                task = m.get(m.KICKER + 0x510)
                self.assertEqual(m.get(task), 0x2F15C0)
                self.assertEqual(m.readf(task + 0xA4), 0)
                # Both readiness queries gate the delay, even long after its
                # deadline. No global state transition occurs inside this task.
                for team in (m.KICK_TEAM, m.RECEIVE_TEAM):
                    saved = m.get(team + 0x324)
                    m.put(team + 0x324, 0)
                    m.f32(0xB71D00, 100)
                    m.run(0x2F15C0, ecx=m.KICKER)
                    self.assertEqual(m.get(task), 0x2F15C0)
                    m.put(team + 0x324, saved)
                for bits in (threshold_bits - 1, threshold_bits):
                    m.put(0xB71D00, bits)
                    m.run(0x2F15C0, ecx=m.KICKER)
                    self.assertEqual(m.get(task), 0x2F15C0)
                    self.assertEqual(m.get(dk.PLAY_STATE), 13)
                m.put(0xB71D00, threshold_bits + 1)
                m.run(0x2F15C0, ecx=m.KICKER, stop=0x2EE950)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EIP), 0x2EE950)
                # Run native meter preparation, then provide its latched input
                # outcome. This is not a simulation of the CPU's meter choice.
                m.run(0x2F15C0, ecx=m.KICKER)
                self.assertEqual(m.get(task), 0x2F1550)
                m.put(0xB72710, 8)
                m.put(0xB72694, 1)
                m.run(0x2F1550, ecx=m.KICKER)
                self.assertEqual(m.get(task), 0x2F0DD0)
                m.run(0x2F0DD0, ecx=m.KICKER)
                self.assertGreater(m.readf(m.KICKER + 0x110), 0)
                self.assertEqual(m.get(dk.PLAY_STATE), 13)
                self.assertEqual(held_state(m.snapshot()), held_state(baseline))


class PublicReceiptTests(unittest.TestCase):
    def test_lossless_full_pose_receipts_without_private_assets(self):
        receipt = json.loads(RECEIPT.read_text())
        raw = TRACES.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt['frame_file_sha256'])
        traces = json.loads(raw)
        for name, trace in traces.items():
            case = receipt['cases'][name]
            self.assertEqual(digest(trace), case['trace_sha256'])
            self.assertEqual(len(trace['frames']), len(case['packets']))
            self.assertEqual(sum(len(trace['sequences'][s]) for s, _ in trace['frames']),
                             case['total_held_player_writes'])
            for event in trace['events']:
                p, field, phase, pc, off, before, after = event
                self.assertIn(p, HELD)
                self.assertIn(field, PREKICK_FIELDS + ('lineup_state',))
                self.assertIn(phase, (0,) + PHASES)
                self.assertEqual(len(before), len(after))
                self.assertIn(len(bytes.fromhex(after)), (1, 2, 4, 8))
                self.assertGreater(pc, 0)
                self.assertGreaterEqual(off, 0)
            if name != 'v3_counterexample':
                self.assertEqual(len({state for _, state in trace['frames'][2:-1]}), 1)
                self.assertEqual(case['global_state_writes'],
                                 [[0xE9210, 0x158CC1, 12, 13], [0, 0xB6FB3, 13, 14]])


def record():
    V4Tests.setUpClass()
    test = V4Tests()
    result = dict(V4Tests.evidence, cases={})
    traces = {}
    cases = [('v3_counterexample', V4Tests.v3, dk.FLAGS, 1, True)]
    cases += [(f'{name}_{direction:+d}', payload, state, direction, False)
              for name, payload, state in test.variants() for direction in (-1, 1)]
    for name, payload, state, direction, historical in cases:
        summary, trace = exercise(test, payload, state=state, direction=direction, historical=historical)
        result['cases'][name], traces[name] = summary, trace
        print(name, summary['total_held_player_writes'], 'writes', flush=True)
    raw = (json.dumps(traces, separators=(',', ':')) + '\n').encode()
    result['frame_file_sha256'] = hashlib.sha256(raw).hexdigest()
    TRACES.write_bytes(raw)
    RECEIPT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    if sys.argv[1:] == ['--record']:
        record()
    else:
        unittest.main()
