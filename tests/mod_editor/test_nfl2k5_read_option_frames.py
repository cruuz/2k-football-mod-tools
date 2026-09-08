"""Native per-frame dispatcher and participant replays, no game or display.

The fixture supplies an actor list, clock/controller samples and task storage.
Asset-dependent animation allocation and GPU submission are named boundaries.
Control priority, paired lookup, both participant callbacks, branch advancement,
operand decoding, native give/pass initialization and command stores execute
retail instructions. This is not a collision or rendered animation witness.
"""
from __future__ import annotations

import gc
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_read_option_runtime as patch
from mod_editor.core import nfl2k5_playbook_pack as packs
from tests.mod_editor.test_nfl2k5_read_option_controls import ControlsMachine, shotgun_reads
from tests.mod_editor.test_nfl2k5_read_option_runtime import XBE, compiled_reads
from tests.mod_editor.test_nfl2k5_play_intents import pool_resource, resolve, roles
from tests.mod_editor.test_nfl2k5_read_option_unicorn import uc, x86
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256


def final_reads(shotgun=False):
    if shotgun:
        _, compiled = shotgun_reads()
    else:
        raw, _ = compiled_reads()
        compiled = packs.apply_pack_to_resource(raw,
            packs.load_pack(ROOT / 'data/playbooks/softdrink_option.2k5book'), asset_id='book:MIN')
    final = roles.normalise(pool_resource(compiled.replacement)).replacement
    pairs, _, _ = resolve({'MIN': final}, [(compiled.replacement, compiled.report)])
    table, receipt = patch.compile_intent_table(pairs)
    return final, table, receipt


class FrameMachine(ControlsMachine):
    loaded_books = {}

    def load_book(self, resource, index=0):
        # Execute the generic gameplay PLAY relocator at a heap-like address.
        # B72918 is ancillary metadata; zero entries means no extra tags.
        self.loaded_base = 0x3050000 + index*0x14000
        self.u32(0xB72918, 0x304F000)
        self.u32(0xBE4E20, 0x521078)  # retail opcode descriptors, startup value
        key = (hashlib.sha256(resource).digest(), self.loaded_base)
        if key in self.loaded_books:
            self.uc.mem_write(self.loaded_base, self.loaded_books[key])
            return self.loaded_base
        self.uc.mem_write(self.loaded_base, resource[32:])
        try:
            self.run(0xE0D90, ecx=self.loaded_base, count=1000000)
        except AssertionError as exc:
            if 'instruction budget exhausted' not in str(exc):
                raise
            for _ in range(8):
                self.hits = []
                self.uc.emu_start(self.uc.reg_read(x86.UC_X86_REG_EIP),
                                  self.STOP, count=1000000, timeout=2_000_000)
                if self.uc.reg_read(x86.UC_X86_REG_EIP) == self.STOP:
                    break
            else:
                raise AssertionError('generic PLAY loader exceeded nine bounded segments')
        self.loaded_books[key] = bytes(self.uc.mem_read(self.loaded_base, len(resource)-32))
        return self.loaded_base

    def observe(self, u, address, size, user):
        if address == 0x2C9AF0:
            # Native task arena allocation only. The native initializer writes
            # its own callback, operands and command into this owned storage.
            self.boundaries[address] = (0, self.get(u.reg_read(x86.UC_X86_REG_ECX)+0x310))
        # Execute the real callback dispatcher and native steering function;
        # their parent fixtures used to stop at these boundaries.
        if address in (0x214B90, 0x1ADF90, 0x1A4170):
            self.hits.append(address)
            if address == 0x1ADF90:
                actor = u.reg_read(x86.UC_X86_REG_ECX)
                target = u.reg_read(x86.UC_X86_REG_EDX)
                self.steering.append((actor, struct.unpack('<4f', u.mem_read(target, 16))))
            return
        super().observe(u, address, size, user)

    def __init__(self, *args, **kwargs):
        self.steering = []
        super().__init__(*args, **kwargs)
        self.u32(0xE60268, self.QB)
        self.u32(self.QB+0x30, self.RB)
        self.u32(self.RB+0x30, 0)
        self.u32(self.DEF+8, self.OFFMETA)
        from mod_editor.core.nfl2k5_playbook_inspector import (
            parse_playbook_resource, FORMATION_BASE, FORMATION_SIZE)
        book = parse_playbook_resource(args[1], asset_id='book:MIN')
        formation = next(f for f in book.formations if f.name == (
            'Gun: Doubles Right' if self.pi in (134, 31) else 'I Jokers'))
        for team in (self.OFF, self.DEF):
            self.u32(team+12, team+0x100)
            self.u32(team+0x108, self.base+FORMATION_BASE+formation.index*FORMATION_SIZE)
            self.u32(team+0x10C, self.base+0x3404+self.pi*96-8)
        self.u32(self.QB, self.BALL)
        self.u32(self.BALL+0x14, self.BALL+0x200)
        self.u32(self.BALL+0x1C, self.BALL+0x100)
        # Sampled post-snap pose; positions are inputs, never integrated physics.
        self.f32(self.RB+0x438, self.readf(self.QB+0x438)-2*91.44*self.direction)
        for actor in (self.QB, self.RB, self.P, self.OTHER):
            self.u32(actor+0x24, actor+0x500)
            self.f32(actor+8, 1)
            self.u32(actor+0x204, 0x50F4EC)
            self.u32(actor+0x374, actor+0x1800)
            self.u32(actor+0x1800, actor+0x1900)
            self.u32(actor+0x600, 1)
            self.u32(actor+0x600+0x3E4, 14)
        self.boundaries = {
            0x2C9AB0: (0, None),  # preallocated task arena
            0x2D6790: (0, None),  # release asset-owned task animation
            0x214790: (0, 1),     # all fixture actors scheduled this update
            0x1A4340: (0, None),  # independent defensive team prepass
            0x217AE0: (0, 0),    # model-bone facing in the sampled stationary pose
            0x2D6B70: (28, None), # load the selected animation asset
            0x2132A0: (0, None),  # neutral locomotion clip initializer; destructor runs
            0x2E2DA0: (0, 0),    # CPU downfield running AI after completed KEEP initialization
            0x198C20: (4, 'float'), # pass aim calculation, native x87 ABI
        }
        for actor, slot, node in ((self.QB, 0, 2), (self.RB, 10, 1)):
            interp = actor+0x600+0x41C
            self.u32(interp, self.base+0x3404+self.pi*96+slot*8)
            self.run(0x1B8790, ecx=interp, edx=node)
            self.run(0x1B84E0, eax=interp)
            self.run(0x1AF870, ecx=actor)
        self.run(0x1B85A0)  # retail opcode-to-initializer table, never guessed
        self.uc.mem_write(0xBDFCD0+7*2, b'\x01')  # receiver button B
        self.trace = []

    def frame(self, time, *, held=False, throw=False, stick=0, press=None):
        self.f32(self.GAME+0x410, time)
        self.f32(0xB71D0C, 1/60)
        if self.controller >= 0:
            self.u32(0xA9B95C+self.controller*44, 0x100 if held else 0)
            self.u32(0xA9B954+self.controller*44, (0x200 if throw else 0) if press is None else press)
            self.f32(self.QB+0x110, stick)
            self.u32(self.QB+0x11C, 22 if held else 0)
        self.steering = []
        try:
            self.run(0x214FC0, count=100000)
        except Exception:
            print('last native PCs', [hex(pc) for pc in self.hits[-20:]])
            raise
        row = dict(time=time, qb_node=self.get(self.qs+0x450) & 255,
                   back_node=self.get(self.RB+0x600+0x450) & 255,
                   decision=self.get(self.state_va+28), cache=self.get(0xBE4E30),
                   callback=hex(self.get(self.task)), back_callback=hex(self.get(self.RB+0xE00)),
                   throttle=self.readf(self.QB+0x110), ball=hex(self.get(self.BALL)),
                   edge=hex(self.get(self.state_va+40)),
                   read_updates=self.get(self.state_va+20))
        self.trace.append(row)
        return row

    def exchange(self, *, stick=0, deliver=True):
        """Finish native approach/handshake using collision-free pose samples.

        The test supplies the actor positions and the animation's exchange
        event. It never writes a decision, callback, readiness flag or owner.
        Both native ownership-list operations execute inside the event.
        """
        for step in range(10):
            if self.get(self.QB+0x204) == 0x531A08:
                break
            for actor in (self.QB, self.RB):
                self.f32(actor+0x430, self.readf(actor+0xE20))
                self.f32(actor+0x438, self.readf(actor+0xE28))
            self.frame(self.readf(self.GAME+0x410)+1/60, stick=stick)
        else:
            raise AssertionError('native give/take did not start the paired handoff')
        assert self.get(self.QB+0x2D0) == self.RB
        assert self.get(self.RB+0x2D0) == self.QB
        assert self.get(self.QB+0x300) & 0xA1 == 0x80  # give, no toss/fake
        assert self.get(self.RB+0x300) & 0x89 == 0x88
        assert self.get(self.BALL) == self.QB
        if not deliver:
            return dict(animation=hex(self.get(self.QB+0x204)), time=self.readf(self.GAME+0x410))
        # Post-detach, post-attach and handoff stat/notification callbacks are
        # outside this ownership proof. They cannot choose or perform transfer.
        self.boundaries.update({0xA0910: (0, None), 0xA0870: (0, None),
                                0xA0CC0: (0, None)})
        self.run(0x313520, args=(0, self.QB))
        event = dict(event='native animation exchange', time=self.readf(self.GAME+0x410),
                     ball=hex(self.get(self.BALL)), qb_ball=hex(self.get(self.QB)),
                     back_ball=hex(self.get(self.RB)),
                     native_calls=[hex(pc) for pc in (0x313520, 0xDDCA0, 0x26A4C0,
                         0xDDCD0, 0x26A4A0) if pc in self.hits])
        self.trace.append(event)
        return event

    def cue(self, actor, x, y):
        # Execute the real queue producer and world-to-screen matrix path.
        # Identity camera provides deterministic visible, positive-depth points.
        camera, vector = 0x3040000, 0x3040400
        self.u32(0xA6AFB4, camera)
        self.uc.mem_write(camera+0xF0, struct.pack('<16f',
                         *[1 if i % 5 == 0 else 0 for i in range(16)]))
        self.uc.mem_write(vector, struct.pack('<4f', x, y, 1, 1))
        self.run(0xFA270, ecx=vector, edx=vector, args=(actor, 5, 0, 0, 0, 0, 0))
        projected = struct.unpack('<4h', self.uc.mem_read(0xA94EB0, 8))
        self.u32(0xA94EA0, 1)
        self.boundaries.update({0x2D2A0: (12, None), 0x2CB90: (8, None),
                                0x2CB50: (12, None), 0x2CA00: (0, None)})
        self.submissions = []
        self.run(0x646A1, stop_at=0x646A6)
        vertices = [args for address, args in self.submissions if address == 0x2CB50]
        return projected, vertices


@unittest.skipUnless(uc is not None and XBE.is_file(), 'Unicorn and pinned USA retail XBE required')
class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('local XBE differs from pinned USA evidence')
        cls.resource, cls.table, cls.receipt = final_reads()
        cls.payload = patch.apply(cls.retail, intent_table=cls.table)[0]
        cls.evidence = []

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('NFL2K5_READ_OPTION_FRAME_TRACE'):
            Path(os.environ['NFL2K5_READ_OPTION_FRAME_TRACE']).write_text(
                json.dumps(dict(pairing=cls.receipt, traces=cls.evidence), indent=2)+'\n')

    def machine(self, **kwargs):
        gc.collect()
        return FrameMachine(self.payload, self.resource, **kwargs)

    def test_receive_snap_can_advance_to_condition_before_ball_arrives(self):
        # Native 30C2B0 -> 9FF80 -> 9FE50 -> B6F30 sets phase 14 and
        # invokes the snap hook before 30B8D0 transfers the center's ball.
        # The real receive callback may already advance QB node 1 to 2.
        # Supply delayed arrival via native ownership calls; no decision,
        # callback, condition cache or ball owner is assigned by this test.
        for shotgun in (False, True):
            resource, table, _ = final_reads(shotgun=shotgun)
            for diagnostic in (False, True):
                payload = patch.apply(self.retail, intent_table=table,
                                      diagnostic=diagnostic)[0]
                for pi in ((134, 31) if shotgun else (155, 157)):
                    gc.collect()
                    m = FrameMachine(payload, resource, controller=0, play_index=pi)
                    m.run(0x1B8790, ecx=m.interp, edx=1)
                    m.run(0x1B84E0, eax=m.interp)
                    m.run(0x2D3E80, ecx=m.QB)
                    m.run(0x1AD9C0)  # native per-play condition cache reset
                    m.boundaries.update({0xA0910: (0, None), 0xA0870: (0, None)})
                    m.run(0xDDCD0, ecx=m.BALL, edx=m.OTHER)  # center stand-in
                    m.snap_read()
                    for t in (.05, .1, .4):
                        row = m.frame(t, held=True, press=0x1500, stick=1)
                        self.assertEqual((row['qb_node'], row['back_node']), (2, 1))
                        self.assertEqual((row['decision'], row['cache']),
                                         (0xFFFFFFFF, 0xFFFFFFFF))
                        self.assertEqual((row['read_updates'], row['throttle']), (0, 0))
                        self.assertEqual(m.get(m.BALL), m.OTHER)
                    m.run(0xDDCA0, ecx=m.BALL)  # snap in flight
                    row = m.frame(.45, held=True, press=0x1500, stick=1)
                    self.assertEqual((row['decision'], row['read_updates']),
                                     (0xFFFFFFFF, 0))
                    self.assertEqual(m.get(m.BALL), 0)
                    m.run(0xDDCD0, ecx=m.BALL, edx=m.QB)  # supplied snap arrival
                    row = m.frame(.5, held=True, stick=1)
                    self.assertEqual((row['qb_node'], row['back_node'], row['cache']),
                                     (4, 3, 1))
                    self.assertEqual(row['decision'], 0xFFFFFFFF)
                    m.exchange(stick=1)
                    self.assertEqual(m.get(m.BALL), m.RB)
                    self.evidence.append(dict(case='delayed native snap reception',
                        play=pi, diagnostic=diagnostic, trace=m.trace))

    def test_native_give_starts_on_first_frame_and_only_event_moves_ball(self):
        for rpo in (False, True):
            for held in (False, True):
                m = self.machine(controller=0, rpo=rpo)
                row = m.frame(.05, held=held, stick=1)
                self.assertEqual((row['qb_node'], row['back_node'], row['cache']), (4, 3, 1))
                self.assertEqual(row['decision'], 0xFFFFFFFF)
                self.assertEqual(row['throttle'], 0)
                self.assertIn(0x300B00, m.hits)
                self.assertIn(0x2E41F0, m.hits)
                event = m.exchange(stick=1)
                self.assertEqual((m.get(m.BALL), m.get(m.QB), m.get(m.RB)), (m.RB, 0, m.BALL))
                self.assertEqual(m.get(m.state_va+28), 1)
                self.assertEqual(len(event['native_calls']), 5)
                m.run(0x313520, args=(0, m.QB))
                self.assertNotIn(0x26A4A0, m.hits)
                self.evidence.append(dict(case='no new input, native give', held=held, play=m.pi, trace=m.trace))

    def test_back_advances_from_native_take_to_carry_after_animation_completion(self):
        m = self.machine(controller=0)
        m.frame(.05)
        m.exchange()
        # Supply animation completion through the real transition/destructor,
        # not a node, task callback, readiness flag or ownership assignment.
        for actor in (m.QB, m.RB):
            m.run(0x1CD550, ecx=actor, edx=0x50F4EC)
        row = m.frame(.2)
        self.assertEqual(row['back_node'], 4)
        self.assertEqual(m.get(m.RB+0xE00), 0x2E3800)
        self.assertEqual(m.get(m.BALL), m.RB)
        m.frame(.3)
        self.assertIn(0x2E3800, m.hits)
        self.assertGreater(m.readf(m.RB+0x110), 0)
        self.evidence.append(dict(case='native TAKE to back carry', trace=m.trace))

    def test_keep_pitch_and_rpo_cancel_before_and_during_paired_animation(self):
        for animated in (False, True):
            for rpo in (False, True):
                for choice, press, decision in [('keep', 0x100, 0), ('pitch', 0x1000, 3)] + (
                        [('pass X', 0x400, 2), ('pass receiver B', 0x200, 2)] if rpo else []):
                    m = self.machine(controller=0, rpo=rpo)
                    m.frame(.05)
                    if animated:
                        m.exchange(deliver=False)
                    row = m.frame(.25, held=choice=='keep', press=press, stick=1)
                    self.assertEqual(row['decision'], decision)
                    self.assertEqual(m.get(m.BALL), m.QB)
                    if animated:
                        self.assertEqual(m.hits.count(0x3133A0), 2)
                        self.assertFalse(m.get(m.QB+0x228) & 1)
                        self.assertFalse(m.get(m.RB+0x228) & 1)
                    if decision == 0:
                        self.assertIn(0x2E36F0, m.hits)
                        self.assertEqual(m.get(m.RB+0xA50)&255, 2)
                        self.assertEqual(m.frame(.3, stick=1)['throttle'], 1)
                    elif decision == 2:
                        self.assertEqual(m.get(m.QB+0x11C), 0x42)
                        self.assertEqual(m.get(m.task+0x40), m.OTHER)
                        self.assertEqual(m.get(m.state_va+36), 0)
                        for pc in (0x19C740, 0x19BAE0, 0x1907D0, 0x19B800, 0x199260):
                            self.assertIn(pc, m.hits)
                    else:
                        self.assertIn(0x300B00, m.hits)
                        self.assertIn(0x2FF7C0, m.hits)
                        self.assertEqual(m.readf(m.interp+0x18), 1)
                        self.assertEqual(m.get(m.QB+0x11C), 0x4E)
                        self.assertEqual(m.get(m.task+0x40), m.RB)
                    m.run(0x313520, args=(0, m.QB))
                    self.assertEqual(m.get(m.BALL), m.QB)
                    self.assertNotIn(0xDDCA0, m.hits)
                    self.evidence.append(dict(case=choice, animated=animated, play=m.pi, trace=m.trace))

    def test_snap_held_is_not_keep_release_repress_is_required(self):
        m = self.machine(controller=0)
        for t in (.05, .1, .2):
            self.assertEqual(m.frame(t, held=True, press=0x100)['decision'], 0xFFFFFFFF)
        m.frame(.25)
        self.assertEqual(m.frame(.3, held=True, press=0x100)['decision'], 0)
        self.assertEqual(m.frame(.35, press=0x1000)['decision'], 0)

    def test_cpu_snap_edge_crash_pitch_wide_hysteresis_and_both_directions(self):
        for direction in (-1, 1):
            for case, xs, vs, expected in (
                    ('crash keep', [-2]*4, [4]*4, 0),
                    ('close crash pitch', [-.5]*4, [1]*4, 3),
                    ('wide give', [-2]*4, [0]*4, 1),
                    ('one twitch gives', [-2]*4, [0,4,0,0], 1)):
                m = self.machine(direction=direction)
                for t,x,v in zip((.05,.15,.25,1.1),xs,vs):
                    m.edge(x=x*direction, vx=v*direction)
                    row=m.frame(t)
                self.assertEqual(row['decision'], expected, (case,row))
                self.assertEqual(m.get(m.state_va+40), m.P)
                self.evidence.append(dict(case=case, direction=direction, trace=m.trace))

    def test_human_mesh_cancels_after_a_stall_and_duplicate_clocks_do_not_sample(self):
        for rate in (15,30,60):
            m = self.machine(controller=0)
            m.frame(.05, held=True)
            for n in range(1, rate):
                self.assertEqual(m.frame(.05+n/rate,held=True)['decision'],0xFFFFFFFF)
            count=m.get(m.state_va+20)
            m.frame(m.readf(m.GAME+0x410),press=0x1000)
            self.assertEqual(m.get(m.state_va+20),count)
            self.assertEqual(m.frame(1.3,press=0x1000)['decision'],3)
            self.assertEqual(m.get(m.BALL),m.QB)

    def test_unready_rpo_and_changed_lifecycle_cannot_pull(self):
        m=self.machine(controller=0,rpo=True);m.frame(.05);m.ready(False)
        self.assertEqual(m.frame(.1,press=0x400)['decision'],0xFFFFFFFF)
        self.assertEqual(m.frame(1.1)['decision'],0xFFFFFFFF)
        m.exchange()
        self.assertEqual(m.get(m.BALL),m.RB)
        for change in ('phase','roster','assignment','back assignment','controller','clock','ball'):
            m=self.machine(controller=0);m.frame(.05)
            if change=='phase':m.u32(0xE602B8,15)
            elif change=='roster':m.u32(m.QB+0x3C,m.RB+0xD00)
            elif change=='assignment':m.u32(m.interp,m.get(m.interp)+96)
            elif change=='back assignment':m.u32(m.RB+0xA1C,m.get(m.RB+0xA1C)+96)
            elif change=='controller':m.u32(m.QB+0x100,-1)
            elif change=='ball':m.u32(m.BALL,m.OTHER)
            else:m.f32(m.state_va+16,2)
            # Observe the scoped hook and its retail tail without executing
            # unrelated AI on deliberately invalid fixture state.
            m.f32(m.GAME+0x410,.1)
            m.run(0x21516A,ebp=m.QB,stop_at=0x215170)
            self.assertEqual(m.get(m.state_va+28),4,change)

    def test_gun_recipes_native_give_pitch_keep_and_rpo_pass(self):
        resource,table,receipt=final_reads(shotgun=True)
        self.assertEqual({r['play_index'] for r in receipt['records']},{134,31})
        payload=patch.apply(self.retail,intent_table=table)[0]
        for pi in (134,31):
            for press,expected in ((0,1),(0x100,0),(0x1000,3),*(([(0x400,2)] if pi==31 else []))):
                gc.collect();m=FrameMachine(payload,resource,controller=0,play_index=pi)
                m.frame(.05)
                if press: self.assertEqual(m.frame(.1,press=press)['decision'],expected)
                else:
                    m.exchange();self.assertEqual(m.get(m.BALL),m.RB)
                self.evidence.append(dict(case='Gun control',play=pi,press=press,trace=m.trace))

    def test_both_variants_relocate_and_preserve_exact_native_scripts(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        from tests.nfl2k5_allocator_stack import REQUESTS
        for diagnostic in (False,True):
            seed=space.apply(self.retail,REQUESTS+(('aaa_read_v5_probe','code',1024,16),),scaleout=True)[0]
            payload=patch.apply(seed,intent_table=self.table,diagnostic=diagnostic)[0]
            gc.collect();m=FrameMachine(payload,self.resource,controller=0,buffer=1)
            before=bytes(m.uc.mem_read(m.base,len(self.resource)-32))
            m.frame(.05);m.frame(.1,press=0x1000)
            self.assertEqual(m.get(m.state_va+28),3)
            self.assertEqual(bytes(m.uc.mem_read(m.base,len(self.resource)-32)),before)
            self.assertNotEqual(patch.allocations(payload)['code']['va'],patch.allocations(self.payload)['code']['va'])


if __name__ == '__main__':
    unittest.main()
