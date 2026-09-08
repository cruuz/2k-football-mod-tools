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
    def observe(self, u, address, size, user):
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
            0x2146C0: (0, None),  # animation transition bookkeeping
            0x214790: (0, 1),     # all fixture actors scheduled this update
            0x1A4340: (0, None),  # independent defensive team prepass
            0x217AE0: (0, 0),    # model-bone facing in the sampled stationary pose
            0x2D6B70: (28, None), # load the selected animation asset
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

    def frame(self, time, *, held=False, throw=False, stick=0):
        self.f32(self.GAME+0x410, time)
        self.f32(0xB71D0C, 1/60)
        if self.controller >= 0:
            self.u32(0xA9B95C+self.controller*44, 0x100 if held else 0)
            self.u32(0xA9B954+self.controller*44, 0x200 if throw else 0)
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
                   decision=self.get(self.task+0x44), cache=self.get(0xBE4E30),
                   callback=hex(self.get(self.task)), back_callback=hex(self.get(self.RB+0xE00)),
                   throttle=self.readf(self.QB+0x110), ball=hex(self.get(self.BALL)),
                   edge=hex(self.get(self.state_va+40)),
                   read_updates=self.get(self.state_va+20))
        self.trace.append(row)
        return row

    def exchange(self, *, stick=0):
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

    def test_full_native_frame_holds_mesh_against_stick(self):
        m = self.machine(controller=0)
        for t in (.05, .2, .5, .9):
            row = m.frame(t, held=True, stick=1)
            self.assertEqual(row['qb_node'], 2)
            self.assertEqual(row['cache'], 0xFFFFFFFF)
            self.assertEqual(row['throttle'], 0)
            self.assertEqual(row['ball'], hex(m.QB))
            self.assertFalse(any(actor == m.QB for actor, _ in m.steering))
            targets = [v for actor, v in m.steering if actor == m.RB]
            self.assertEqual(len(targets), 1)
            # The retail packed operand decoder quantizes the authored half
            # yard to 60 world units (about 0.66 yd), still beside the QB.
            self.assertAlmostEqual(targets[0][0], m.readf(m.QB+0x430)-60, places=3)
            self.assertAlmostEqual(targets[0][2], m.readf(m.QB+0x438), places=3)

    def test_final_book_lookup_both_plays_and_native_loader_buffers(self):
        from mod_editor.core.nfl2k5_read_option_runtime_code import LABELS
        for buffer in (0, 1):
            for rpo in (False, True):
                m = self.machine(controller=0, buffer=buffer, rpo=rpo)
                code = patch.allocations(self.payload)['code']['va']
                row = m.run(code+LABELS['lookup'], esi=m.QB)
                expected = next(r for r in self.receipt['records'] if r['play_index'] == m.pi)
                self.assertNotEqual(row, 0)
                self.assertEqual(bytes(m.uc.mem_read(row, 24)).hex(), expected['record'])
                descriptor = m.get(m.interp)
                identity = dict(book_hash=m.run(code+LABELS['name_hash'], edi=m.base,
                                               esi=m.get(m.base+0x30)),
                    name_hash=m.run(code+LABELS['name_hash'], edi=m.base, esi=m.get(descriptor-8)),
                    qb_hash=m.run(code+LABELS['script_hash'], edi=m.base, edx=descriptor),
                    back_hash=m.run(code+LABELS['script_hash'], edi=m.base, edx=descriptor+80))
                book_hash, offset, qb_hash, back_hash, name_hash, *_ = patch.RECORD.unpack(
                    bytes.fromhex(expected['record']))
                self.assertEqual(identity, dict(book_hash=book_hash, name_hash=name_hash,
                                               qb_hash=qb_hash, back_hash=back_hash))
                self.assertEqual(descriptor-m.base, offset)
                self.assertEqual(m.readf(m.task+0x34), 1)  # native movement trigger
                m.frame(.05, held=False, stick=1)
                self.assertEqual(m.get(m.state_va), m.QB)
                self.assertEqual(m.readf(m.QB+0x110), 0)
                self.evidence.append(dict(case='final native lookup', play=m.pi, buffer=buffer,
                    descriptor=hex(descriptor), record=expected['record'],
                    native_hashes={k: hex(v) for k, v in identity.items()}, trace=m.trace))

    def test_release_early_mid_window_and_do_nothing_execute_native_handoff(self):
        for rpo in (False, True):
            for case, release_at in (('release early', .08), ('release mid', .55), ('do nothing', 0)):
                m = self.machine(controller=0, rpo=rpo)
                for t in (.05, .08, .3, .55, .8, 1.0):
                    row = m.frame(t, held=t < release_at, stick=1)
                    self.assertEqual((row['qb_node'], row['back_node'], row['cache']),
                                     (2, 1, 0xFFFFFFFF))
                    self.assertEqual(row['throttle'], 0)
                    self.assertEqual(m.get(m.BALL), m.QB)
                row = m.frame(m.readf(m.state_va+44), stick=1)
                self.assertEqual((row['qb_node'], row['back_node'], row['cache']), (4, 3, 1))
                self.assertIn(0x300B00, m.hits)
                self.assertIn(0x2E41F0, m.hits)
                event = m.exchange(stick=1)
                self.assertEqual((m.get(m.BALL), m.get(m.QB), m.get(m.RB)), (m.RB, 0, m.BALL))
                self.assertEqual(len(event['native_calls']), 5)
                m.run(0x313520, args=(0, m.QB))
                self.assertEqual(m.get(m.BALL), m.RB)
                self.assertNotIn(0x26A4A0, m.hits)  # repeated event cannot give twice
                self.evidence.append(dict(case=case, play=m.pi, trace=m.trace))

    def test_hold_through_returns_native_human_carry_and_stick_control(self):
        for rpo in (False, True):
            m = self.machine(controller=0, rpo=rpo)
            for t in (.05, .4, .8, 1.0): m.frame(t, held=True, stick=1)
            row = m.frame(m.readf(m.state_va+44), held=True)
            # RPO keep takes the terminal native carry exit at node2; node3
            # is its pass, which a keep must never execute.
            self.assertEqual((row['qb_node'], row['back_node'], row['cache']),
                             (2 if rpo else 3, 2, 0))
            if rpo:
                self.assertIn(0x2E36F0, m.hits)
                self.assertTrue(m.get(m.interp+4) & 0x800000)
            else:
                self.assertEqual(m.get(m.task), 0x2E3800)
            self.assertEqual(m.get(m.BALL), m.QB)
            row = m.frame(1.1, held=True, stick=1)
            self.assertEqual(row['throttle'], 1)
            self.assertEqual(m.get(m.BALL), m.QB)
            self.assertNotIn(0x313A00, m.hits)
            self.evidence.append(dict(case='hold through', play=m.pi, trace=m.trace))

    def test_rpo_press_emits_native_throw_before_human_priority_resumes(self):
        m = self.machine(controller=0, rpo=True)
        for t in (.05, .45, .8, 1.0):
            row = m.frame(t, held=True, throw=t == .45, stick=1)
            self.assertEqual(row['qb_node'], 2)
            self.assertEqual(m.get(m.QB+0x11C), 0)
        row = m.frame(m.readf(m.state_va+44), held=True, stick=1)
        self.assertEqual((row['qb_node'], row['back_node'], row['cache']), (3, 2, 0))
        self.assertEqual(m.get(m.task), 0x19BAE0)
        self.assertEqual(m.get(m.task+0x40), m.OTHER)
        self.assertEqual(m.get(m.QB+0x11C), 0x42)
        self.assertEqual(m.get(m.state_va+32), 0)
        for pc in (0x19C740, 0x19BAE0, 0x1907D0, 0x19B800, 0x199260):
            self.assertIn(pc, m.hits)
        self.assertNotIn(0x300B00, m.hits)
        self.evidence.append(dict(case='RPO receiver press', command='0x42', trace=m.trace))

    def test_cpu_same_live_edge_crash_wide_and_hysteresis(self):
        for direction in (-1, 1):
            for case, velocities, expected in (
                    ('crash', (4, 4, 4, 4, 0), 0),
                    ('wide', (0, 0, 0, 0, 0), 1),
                    ('one twitch', (0, 0, 0, 4, 0), 1)):
                m = self.machine(direction=direction)
                for t, vx in zip((.05, .3, .6, .9, 1.05), velocities):
                    m.edge(x=-2*direction, vx=vx*direction)
                    row = m.frame(t)
                    self.assertEqual(m.get(m.state_va+40), m.P)
                    if t < 1.05: self.assertEqual(row['qb_node'], 2)
                self.assertEqual(row['cache'], expected)
                self.assertEqual(row['back_node'], 3 if expected else 2)
                self.evidence.append(dict(case='CPU '+case, direction=direction, trace=m.trace))

    def test_clock_seconds_survive_frame_rates_duplicates_and_stalls(self):
        for rate in (15, 30, 60):
            m = self.machine(controller=0)
            start = .05
            m.frame(start, held=True)
            for n in range(1, rate):
                t = start+n/rate
                m.frame(t, held=True, stick=1)
                self.assertEqual(m.get(m.qs+0x450) & 255, 2)
            count = m.get(m.state_va+20)
            m.frame(m.readf(m.GAME+0x410), held=False)
            self.assertEqual(m.get(m.state_va+20), count)
            row = m.frame(m.readf(m.state_va+44), held=False)
            self.assertEqual(row['cache'], 0)  # release at expiry is too late
            self.evidence.append(dict(case='clock rate', rate=rate, trace=m.trace))
        m = self.machine(controller=0)
        m.frame(.05, held=False)
        row = m.frame(1.3, held=True)
        self.assertEqual(row['cache'], 1)  # released default survives a stall

    def test_gun_zone_read_final_pairing_hold_and_native_give(self):
        resource, table, receipt = final_reads(shotgun=True)
        self.assertEqual({r['play_index'] for r in receipt['records']}, {134, 31})
        payload = patch.apply(self.retail, intent_table=table)[0]
        for held, expected in ((False, 1), (True, 0)):
            gc.collect()
            m = FrameMachine(payload, resource, controller=0, play_index=134)
            for t in (.05, .35, .7, 1.0):
                row = m.frame(t, held=held, stick=1)
                self.assertEqual(row['throttle'], 0)
                self.assertEqual(row['qb_node'], 2)
            row = m.frame(m.readf(m.state_va+44), held=held)
            self.assertEqual(row['cache'], expected)
            if expected:
                m.exchange()
                self.assertEqual(m.get(m.BALL), m.RB)
            else:
                self.assertEqual(m.get(m.BALL), m.QB)
            self.evidence.append(dict(case='Gun Zone Read', held=held, trace=m.trace))

    def test_cue_follows_selected_edge_through_native_projection_and_atlas(self):
        m = self.machine(controller=0)
        m.frame(.05, held=True)
        for x, y in ((300, 90), (410, 140)):
            projected, vertices = m.cue(m.P, x, y)
            self.assertEqual(projected, (x, y, x, y+100))
            self.assertEqual(len(vertices), 4)
            self.assertIn(0xF97F0, m.hits)
        self.assertEqual(m.cue(m.OTHER, 300, 90)[1], [])
        m.frame(m.readf(m.state_va+44), held=True)
        self.assertEqual(m.cue(m.P, 300, 90)[1], [])


if __name__ == '__main__':
    unittest.main()
