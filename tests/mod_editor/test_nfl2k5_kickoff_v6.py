"""Native kickoff catch, retail kneel clip/event, commentary queue and next play.

Standalone unittest; --record writes compact v6 evidence, never a private asset.
The 27 frame phases execute natively. A supplied contact at the ball-update
boundary calls the real touch/attachment/task APIs. Synthetic skeletons, run
clips and decoded intent remain the v5 fixture's inputs. The kneel clip and
its event table come from the pinned retail executable. No audio is played.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import RETAIL, PRIVATE_REASON, uni, x86, Cs
from tests.mod_editor.test_nfl2k5_kickoff_v5 import ReturnMachine, RECEIPT as V5_RECEIPT
from tests.mod_editor.test_nfl2k5_kickoff_v3 import patch_evidence, replay_edits, digest
from tests.nfl2k5_kickoff_frame import PHASES
from mod_editor.core import nfl2k5_dynamic_kickoff as dk
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
from mod_editor.core.nfl2k5_bump_strength import RETAIL_XBE_SHA256
from mod_editor.core.nfl2k5_draft_ai import _Asm

RECEIPT = Path(__file__).resolve().parents[2] / 'docs/nfl2k5_kickoff_v6_receipts.json'
SITES = (0x2EE1F0, 0x2EE090, 0x1ABCD0, 0x222C20, 0x305580, 0xA1920,
         0xB7550, 0xA1A20, 0xA0390, 0xA7B40, 0x2D6B70, 0xB78C0,
         0x26A4A0, 0x1E91F0, 0xA7AD0, 0x22EB70, 0x22EA20, 0x22DF90,
         0x22E3A0, 0x1E8E20)


class TouchbackMachine(ReturnMachine):
    def __init__(self, payload, *, yard=-6, ground=False, **kwargs):
        self.yard, self.grounded = yard, ground
        self.events, self.state_events = [], []
        self.injected, self.next_injected = False, False
        self.contact_frame = -1
        self.return_frame = -1
        super().__init__(payload, **kwargs)
        for pc in SITES:
            self.uc.hook_add(uni.UC_HOOK_CODE, self._hook, begin=pc, end=pc)
        self.uc.hook_add(uni.UC_HOOK_MEM_WRITE, self._state_event,
                         begin=dk.PLAY_STATE, end=dk.PLAY_STATE + 3)

    def begin_catch(self):
        self.put(dk.PLAY_STATE, 14)
        self.launch()
        z = self.direction * (50 - self.yard) * 91.44
        self.place(self.RETURNER, 0, z)
        self.position(0, z)
        self.put(self.BALL + 0x14, self.BALL_POS if self.grounded else self.RETURNER + 0xB30)
        self.put(self.BALL + 0x1C, self.CONTACT + 0x80)
        if self.grounded:
            self.run(0x1ABCD0, ecx=self.RETURNER)  # native wait task for the unfielded ball
        self.put(self.RETURNER + 0x200, 1)
        self.put(self.RECEIVE_TEAM + 0x110, self.RECEIVE_TEAM + 0x250)
        self.uc.mem_write(self.RECEIVE_TEAM + 0x250, struct.pack('<4f', -2438.4,
            4572 if self.direction > 0 else -5486.4, 2438.4,
            5486.4 if self.direction > 0 else -4572))
        # Adversarial clear-lane input: coverage behind the carrier, within
        # the field. Native 1BB3B0 must count zero defenders ahead, not a stub.
        for who in self.players[:11]:
            self.place(who, 2000, z + self.direction * 250)
        # Descriptor exit 2FC210 polls the decoded controller after the whistle.
        # Supply neutral action at that input ABI, not a replacement kneel task.
        self.uc.mem_write(self.CALLBACK + 0x500, bytes.fromhex('c7411c00000000c3'))
        for index, who in enumerate(self.players):
            self.put(self.get(who + 0xC) + 0xC, self.CALLBACK + 0x500)
            base = 0x2100000 + index * 0x8000
            # Separate fatigue clock storage from the roster's actor pointer,
            # now consumed by the real event-ring writer A7690.
            self.put(base + 0x3D04, base + 0x3D30)
            self.f32(base + 0x3D30, 1); self.f32(base + 0x3D34, 1)
            self.put(base + 0x3D10, who)
        self.put(0xB6FF64, -1); self.put(0xB6FF68, 0)
        self.put(0xB6E7E0, 0); self.put(0xB6E7E4, 0); self.put(0xB6E7E8, 0)
        self.put(0xB6FF88, 0)  # no audio listener; queue producer still executes
        self.uc.mem_write(0xB6E7F0, b'\0' * (5 * 0x4B0))
        for n in range(5):
            self.put(0xB6E7F0 + n * 0x4B0 + 0x4A4, 511)
        self.run(0xA82E0, args=(0,))  # actual play-record and commentary reset
        self.events.clear()
        self.inject_va, self.next_va = self.CALLBACK + 0x300, self.CALLBACK + 0x400
        a = _Asm(self.inject_va); a.b('60')
        if self.grounded:
            a.b('6a00b9' + dk._imm(self.BALL) + 'ba' + dk._imm(self.CONTACT))
            a.call(0xA06E0)  # complete ground collision callback, including RET 4
        else:
            a.b('b9' + dk._imm(self.RETURNER)); a.call(0xB78C0)
            a.b('b9' + dk._imm(self.BALL) + 'ba' + dk._imm(self.RETURNER)); a.call(0xDDCD0)
            a.b('b9' + dk._imm(self.RETURNER)); a.call(0x2EE1F0)
            # A queued contact is a separate explicit stress input. Mode 2
            # defers it until the whistle; execute its native producer.
            a.b('b9' + dk._imm(self.RETURNER)); a.call(0x1E8FA0)
        a.b('61c3'); self.uc.mem_write(self.inject_va, a.assemble())
        self.next_record = 0x205E000
        a = _Asm(self.next_va); a.b('606a0068' + dk._imm(self.KICK_TEAM))
        a.b('ba' + dk._imm(self.CTX + 0x30) + 'b9' + dk._imm(self.next_record))
        a.call(0x22EB70)  # native next-play record / receiving first down
        a.b('6a00'); a.call(0xA82E0)  # native next-play commentary reset
        a.b('61c3'); self.uc.mem_write(self.next_va, a.assemble())

    def _state_event(self, uc, access, address, size, value, data):
        self.state_events.append([self.return_frame, self.phase,
            uc.reg_read(x86.UC_X86_REG_EIP), self.get(dk.PLAY_STATE), value])

    def _hook(self, uc, address, size, data):
        if address == 0x1E08D0 and hasattr(self, 'inject_va'):
            target = None
            if not self.injected:
                self.injected = True; self.contact_frame = self.return_frame
                target = self.inject_va
            elif (self.get(dk.PLAY_STATE) == 18 and not self.next_injected
                  and self.return_frame > self.contact_frame):
                self.next_injected = True; target = self.next_va
            if target is not None:
                # Supply one contact/advance command, then return to and run
                # the entire original phase. No native phase is replaced.
                sp = uc.reg_read(x86.UC_X86_REG_ESP) - 4
                self.put(sp, address); uc.reg_write(x86.UC_X86_REG_ESP, sp)
                uc.reg_write(x86.UC_X86_REG_EIP, target)
                return
        if address in SITES:
            value = (uc.reg_read(x86.UC_X86_REG_ECX) if address in (0xA7B40, 0xA7AD0)
                     else uc.reg_read(x86.UC_X86_REG_EDX) if address == 0x2D6B70 else 0)
            self.events.append([self.return_frame, address, value])
        super()._hook(uc, address, size, data)

    def queue(self):
        return [self.get(0xB667E0 + n * 64) for n in range(self.get(0xB6E7E4))]


def replay(test, payload, state, direction, yard, ground=False):
    m = TouchbackMachine(payload, state_va=state, direction=direction, yard=yard, ground=ground)
    rows = []
    for frame in range(100):
        m.return_frame = frame
        m.frame()  # includes all 27 phases, real exit and stack balance
        who = m.RETURNER
        rows.append([frame, m.get(dk.PLAY_STATE), m.flags(), m.get(who + 0x904),
            m.readf(who + 0xB30), m.readf(who + 0xB34), m.readf(who + 0xB38),
            m.readf(m.get(who + 0xC58) + 4),
            hashlib.sha256(bytes(m.uc.mem_read(m.get(who + 4), 25 * 64))).hexdigest(),
            m.queue()])
        if m.next_injected or (yard > 0 and frame == 89):
            break
    else:
        test.fail('touchback did not reach the next-play record within 100 frames')
    next_play = None
    if m.next_injected:
        record = m.next_record
        next_play = dict(kind=m.get(record), possession=m.get(record + 0x14),
            down=m.get(record + 8), yard=50 - abs(m.readf(record + 0x48)) / 91.44,
            pending_contact=m.readf(0xBEC160))
        test.assertEqual(next_play['kind'], 4)
        test.assertEqual(next_play['possession'], m.RECEIVE_TEAM)
        test.assertEqual(next_play['down'], 1)
        test.assertEqual(next_play['pending_contact'], -1)
    return dict(direction=direction, yard=yard, ground=ground, rows=rows,
        events=m.events, state_writes=m.state_events, next_play=next_play,
        phase_calls={hex(pc): m.visited[pc] for pc in PHASES}), m


RECORDING = sys.argv[1:] == ['--record']


@unittest.skipUnless(RETAIL.is_file() and uni is not None and Cs is not None,
                     PRIVATE_REASON + '; unicorn/capstone required')
class V6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest('private retail XBE SHA-256 differs')
        (cls.base, cls.legacy, cls.allocated, cls.grown), cls.evidence = patch_evidence(cls.retail)
        cls.v5 = replay_edits(cls.base, json.loads(V5_RECEIPT.read_text())['executable'], 'legacy')
        cls.results = {}
        cls.saved = None if RECORDING else json.loads(RECEIPT.read_text())

    def variants(self):
        return [('legacy', self.legacy, dk.FLAGS),
                ('grown', self.grown, relocated._sites(self.grown)[1]['va'])]

    def case(self, key, payload, state, direction, yard, ground=False):
        case, machine = replay(self, payload, state, direction, yard, ground)
        self.results[key] = case
        for count in case['phase_calls'].values():
            self.assertEqual(count, len(case['rows']), key)
        if self.saved is not None:
            self.assertEqual(digest(case), digest(self.saved['cases'][key]), key)
        return case, machine

    def assert_kneel(self, case, *, frame, yard):
        self.assertEqual([r[0] for r in case['rows'] if r[1] == 18], [frame, frame + 1])
        self.assertTrue(all(r[1] == 14 for r in case['rows'][:frame]))
        self.assertAlmostEqual(case['next_play']['yard'], yard, places=4)
        events = case['events']
        clips = [e for e in events if e[1] == 0x2D6B70 and e[2] in (0x71CA7C, 0x71CAB0)]
        self.assertEqual(len(clips), 1)
        kneel = [r for r in case['rows'] if r[3] == 0x5103A0]
        self.assertGreaterEqual(len(kneel), 60)
        self.assertGreater(len({r[8] for r in kneel}), 15)  # native skeletal pose changes
        self.assertGreater(max(r[5] for r in kneel) - min(r[5] for r in kneel), 25)
        timed = [e for e in events if e[0] == frame]
        order = [next(i for i, e in enumerate(timed) if e[1] == pc)
                 for pc in (0x305580, 0xA1920, 0xB7550, 0xA1A20, 0xA0390)]
        self.assertEqual(order, sorted(order))
        self.assertEqual([e[2] for e in timed if e[1] == 0xA7AD0][:2], [0x3A, 0x5B])
        self.assertEqual(len([e for e in events if e[1] == 0xA0390]), 1)
        self.assertEqual(len(case['state_writes']), 1)
        self.assertEqual(case['state_writes'][0][3:], [14, 18])
        self.assertGreaterEqual(case['rows'][frame][7], 66064 / 65536)
        self.assertLess(case['rows'][frame - 1][7], 66064 / 65536)

    def test_retail_and_v5_root_cause(self):
        retail, _ = self.case('retail_end', self.retail, dk.FLAGS, 1, -6)
        old, _ = self.case('v5_end', self.v5, dk.FLAGS, 1, -6)
        self.assert_kneel(retail, frame=61, yard=20)
        self.assertEqual([e[2] for e in retail['events'] if e[1] == 0xA7AD0],
                         [0x5D, 0x1D, 0x3E, 0x33, 0x24, 0x3A, 0x5B, 0x0D, 7])
        self.assertEqual([r[1] for r in old['rows']], [18, 18])
        self.assertEqual([e[0] for e in old['events'] if e[1] == 0xA0390], [0])
        self.assertFalse(any(e[0] == 0 and e[1] == 0x2EE090 for e in old['events']))
        self.assertFalse(any(e[1] in (0x222C20, 0x305580) for e in old['events']))
        self.assertEqual([e[2] for e in old['events'] if e[1] == 0xA7AD0],
                         [0x5D, 0x1D, 0x3E, 0x0D, 7])
        self.assertAlmostEqual(old['next_play']['yard'], 35, places=4)

    def test_caught_touchback_both_directions_and_placements(self):
        for name, payload, state in self.variants():
            for direction in (-1, 1):
                for yard in (-6, -1):
                    case, _ = self.case(f'{name}_{direction}_{yard}', payload, state, direction, yard)
                    self.assert_kneel(case, frame=60, yard=35)
                    self.assertEqual([e[2] for e in case['events'] if e[1] == 0xA7AD0],
                                     [0x5D, 0x1D, 0x3E, 0x3A, 0x5B, 7])
                    self.assertFalse(any(event in (0x0D, 0x33) for row in case['rows'] for event in row[9]))

    def test_grounded_end_zone_both_directions_and_placements(self):
        for name, payload, state in self.variants():
            for direction in (-1, 1):
                case, m = self.case(f'{name}_{direction}_ground', payload, state, direction, -6, True)
                self.assertEqual([r[1] for r in case['rows']], [18, 18])
                self.assertAlmostEqual(case['next_play']['yard'], 35, places=4)
                self.assertEqual(m.get(m.BALL), 0)
                self.assertEqual(case['rows'][0][2] & 7, dk.END_ZONE)
                self.assertFalse(any(e[1] in (0x26A4A0, 0x222C20, 0x305580) for e in case['events']))
                self.assertFalse(any(event in (0x0D, 0x33) for row in case['rows'] for event in row[9]))

    def test_fielded_three_and_one_are_returns(self):
        for direction in (-1, 1):
            for yard in (3, 1):
                previous, _ = self.case(f'v5_{direction}_{yard}', self.v5, dk.FLAGS, direction, yard)
                for name, payload, state in self.variants():
                    case, _ = self.case(f'{name}_{direction}_{yard}', payload, state, direction, yard)
                    self.assertEqual(case, previous)  # every pose, position, queue event and phase
                    self.assertEqual(len(case['rows']), 90)
                    self.assertTrue(all(r[1] == 14 and r[2] & dk.RETURNED for r in case['rows']))
                    self.assertFalse(any(e[1] in (0x222C20, 0xA1A20, 0xA0390) for e in case['events']))
                    self.assertIn(0x33, case['rows'][-1][9])  # native return announcement retained
                    progress = direction * (case['rows'][0][6] - case['rows'][-1][6])
                    self.assertGreater(progress, 10 * 91.44)
                    self.assertIsNone(case['next_play'])

    def test_ground_rule_does_not_depend_on_cpu_roll_or_human_controller(self):
        for _, payload, state in self.variants():
            for human in (False, True):
                m = TouchbackMachine(payload, state_va=state, ground=True,
                                     rolls=(99, 0, 0), human_returner=human)
                self.assertFalse(m.flags() & dk.TAKE_TB)
                for frame in range(2):
                    m.return_frame = frame; m.frame()
                    self.assertEqual(m.get(dk.PLAY_STATE), 18)
                self.assertTrue(m.next_injected)
                self.assertEqual(m.get(m.next_record + 0x14), m.RECEIVE_TEAM)
                self.assertAlmostEqual(50 - abs(m.readf(m.next_record + 0x48)) / 91.44, 35, places=4)

    def test_native_task_waits_for_busy_catch_animation(self):
        for _, payload, state in self.variants():
            m = TouchbackMachine(payload, state_va=state)
            m.put(m.RETURNER + 0x928, m.get(m.RETURNER + 0x928) | 1)
            for frame in range(3):
                m.return_frame = frame; m.frame()
                self.assertEqual(m.get(dk.PLAY_STATE), 14)
            self.assertTrue(any(e[1] == 0x2EE090 for e in m.events))
            self.assertFalse(any(e[1] in (0x222C20, 0xA0390) for e in m.events))

    def test_commentary_scope_and_original_thunk_abi(self):
        for _, payload, state in self.variants():
            m = TouchbackMachine(payload, state_va=state)
            m.put(0xB6FF64, -1)  # native producer's own early return for this ABI check
            for phase, flags, yard, live, enters in (
                (1, dk.ACTIVE, -6, 14, True), (4, dk.ACTIVE, -6, 14, True),
                (2, 0, -6, 14, True), (2, dk.ACTIVE | dk.RETURNED, -6, 14, True),
                (2, dk.ACTIVE, 1, 14, True), (2, dk.ACTIVE, -6, 14, False),
                (2, dk.ACTIVE, -6, 18, False),
            ):
                m.put(dk.PHASE, phase); m.put(dk.PLAY_STATE, live)
                m.uc.mem_write(state, bytes([flags]))
                m.f32(m.RETURNER + 0xB38, (50 - yard) * 91.44)
                m.events.clear()
                m.run(0xA7930, args=(0x3C888889,))
                self.assertEqual(any(e[1] == 0x1E91F0 for e in m.events), enters)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 8)

    def test_exact_current_patch_receipt(self):
        if self.saved is not None:
            self.assertEqual(digest(self.evidence), digest(self.saved['executable']))
        self.assertEqual(self.evidence['code_bytes_used'], 1939)
        self.assertEqual(self.evidence['code_allocation'], 1939)
        self.assertEqual(self.evidence['state_allocation'], 10)
        self.assertEqual(self.evidence['hook_count'], 20)
        for source, expected, placement in ((self.base, self.legacy, 'legacy'),
                                            (self.allocated, self.grown, 'relocated')):
            self.assertEqual(replay_edits(source, self.evidence, placement), expected)


class PublicReceiptTests(unittest.TestCase):
    def test_compact_evidence_retains_native_events_and_frame_boundaries(self):
        saved = json.loads(RECEIPT.read_text())
        self.assertTrue(saved['experimental'])
        self.assertFalse(saved['runtime_witnessed'])
        self.assertLess(RECEIPT.stat().st_size, 2_000_000)
        self.assertEqual(len(saved['cases']), 26)
        for case in saved['cases'].values():
            self.assertEqual(list(case['phase_calls']), [hex(pc) for pc in PHASES])
            self.assertTrue(all(n == len(case['rows']) for n in case['phase_calls'].values()))
            self.assertTrue(all(len(row) == 10 and len(row[8]) == 64 for row in case['rows']))
        self.assertEqual(saved['clip_event']['type'], 0x5F)
        self.assertEqual(saved['clip_event']['seconds'], 66064 / 65536)


def record():
    V6Tests.setUpClass(); test = V6Tests()
    for method in sorted(name for name in dir(test) if name.startswith('test_')):
        getattr(test, method)()
        print(method, 'PASS', flush=True)
    result = dict(schema=1, experimental=True, runtime_witnessed=False,
        executable=test.evidence, cases=test.results,
        frame_entry='0x11a7c0', dt='1/60',
        row_columns=['frame', 'play_state', 'owner_flags', 'descriptor', 'x_cm', 'height_cm',
                     'z_cm', 'clip_seconds', 'low_skeleton_sha256', 'native_event_queue'],
        event_columns=['frame', 'native_pc', 'event_id_or_clip_va'],
        boundaries=['supplied contact invokes native B78C0, DDCD0 and 2EE1F0 during the ball phase',
                    'deferred contact stress input invokes native 1E8FA0',
                    'v5 synthetic run clips, skeletons, roster and decoded controller input',
                    'retail kneel clip and timed event execute without a clip/clock substitute',
                    'post-whistle advance invokes native 22EB70 and A82E0 during a complete frame',
                    'existing unrelated asset/service leaves; B7330 cutscene path remains a leaf',
                    'no audio listener, device, waveform or spoken-line lookup'],
        clip_event=dict(type=0x5F, callback='0x305580', seconds=66064 / 65536,
                        clips=['0x71ca7c', '0x71cab0']))
    RECEIPT.write_text(json.dumps(result, separators=(',', ':')) + '\n', encoding='utf-8')
    print(RECEIPT.name, RECEIPT.stat().st_size, 'bytes', flush=True)


if __name__ == '__main__':
    record() if RECORDING else unittest.main()
