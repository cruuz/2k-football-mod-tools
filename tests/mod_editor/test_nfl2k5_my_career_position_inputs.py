"""Bounded native input proofs, explicitly short of locomotion/animation proof.

Hardware is represented by retail controller caches. Layout selection and
presentation callbacks are stubbed; native input math, decoder, context restore,
phase walk and command dispatcher execute unchanged. No emulator or game I/O.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_my_career as career
from tools import nfl2k5_my_career_position_evidence as evidence
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, Machine, prepared


@unittest.skipUnless(XBE.is_file() and HAVE_UC, 'pinned USA retail XBE or Unicorn absent')
class PositionInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != evidence.RETAIL_SHA256:
            raise unittest.SkipTest('USA retail XBE evidence pin differs')
        cls.proof = evidence.inspect(cls.retail)
        cls.payload = career.apply(cls.retail)[0]

    def machine(self):
        m = Machine(self.payload)
        # Remove fixture's port-context boundary: execute 120880 -> 120730.
        m.uc.hook_del(m.stubs[0])
        m.layout = 0
        m.stub(0x77230, lambda: m.ret(m.layout))
        m.stub(0x156330, lambda: m.ret(0))  # exclude orientation-lock behavior
        # Presentation/event services, not command mapping or body behavior.
        for va in (0x18E310, 0x872A0, 0x87340, 0x873F0, 0x87470, 0x87540, 0x87590):
            m.stub(va, lambda: m.ret())
        m.put(0xE60280, 0xE5FC20)
        m.put(0xE60284, 0xE5FC60)
        m.put(0xE5FFE4, 0)
        m.put(0xE602B8, 14)
        return m

    def body(self, m, i=0, position=0, port=0):
        body, block = m.BODIES + i * 0x100, 0xBD8210 + i * 36
        m.put(body + 0xC, block)
        m.put(body + 0x38, 0xE5FC20)
        m.put(body + 0x3C, m.BODIES + 0x8000 + 84 * i)
        m.uc.mem_write(m.get(body + 0x3C) + 0x35, bytes([position]))
        m.put(block, port)
        m.put(0xE60268, body)
        return body, block

    def input(self, m, block, context, bits=0, port=0):
        m.uc.mem_write(0xA9B954 + port * 44, bytes(44))
        m.put(block + 4, 0)  # do not invoke the special exit-from-kick path
        m.call(0x1565F0, ecx=block, edx=context)
        m.put(0xA9B954 + port * 44, bits)
        m.put(0xA9B95C + port * 44, bits)
        m.uc.mem_write(0xB37B40 + port * 0x244, struct.pack('<f', 0.6))
        m.uc.mem_write(0xB37B48 + port * 0x244, struct.pack('<f', 0.8))
        m.call(0x1563F0, budget=20000)
        return m.get(block + 0x1C)

    def test_pins_and_all_layouts_body_to_port_restore_are_independent(self):
        self.assertEqual(len(self.proof['layouts']), 3)
        m = self.machine()
        body, block = self.body(m)
        for layout in range(3):
            m.layout = layout
            for port in range(8):
                for context in evidence.CONTEXTS:
                    m.uc.mem_write(0xA9B954, bytes(8 * 44))
                    m.put(block, port)
                    m.put(block + 4, 0)
                    m.put(block + 0x1C, 0xBEEF)
                    m.call(0x1565F0, ecx=block, edx=context)
                    self.assertEqual(m.get(block + 4), context)
                    self.assertEqual(m.get(block + 0x1C), 0)
                    for other in range(8):
                        self.assertEqual(m.get(0xA9B960 + 44 * other), context if other == port else 0)
                    commands = self.proof['layouts'][str(layout)][str(context)]
                    mask = 0 if 0x16 not in commands else m.get(0x4FAAC0 + 4 * commands.index(0x16))
                    self.assertEqual(m.get(0xA9B978 + 44 * port), mask)
        m.put(block, -1)
        m.put(block + 4, 0)
        previous = bytes(m.uc.mem_read(0xA9B954, 8 * 44))
        m.call(0x1565F0, ecx=block, edx=9)
        self.assertEqual(bytes(m.uc.mem_read(0xA9B954, 8 * 44)), previous)

    def test_every_position_decodes_stick_and_offball_button_without_fpf(self):
        m = self.machine()
        for pos in range(17):
            body, block = self.body(m, position=pos)
            for port in (0, 3, 7):
                m.put(block, port)
                self.assertEqual(self.input(m, block, 9, 0x400, port), 0x67)
                self.assertAlmostEqual(struct.unpack('<f', m.uc.mem_read(block + 0x10, 4))[0], 1.0)
                self.assertEqual(m.get(block + 0x14), 0xE5C8)
                self.assertEqual(m.get(0xE5FFE4), 0)
            m.put(block, -1)
            self.assertEqual(self.input(m, block, 9, 0x400), 0)
            self.assertEqual(m.get(block + 0x10), 0)
            m.put(block, 0)
            m.put(body + 0x48, 1)
            m.put(block + 0x1C, 0xBEEF)
            self.assertEqual(self.input(m, block, 9, 0x400), 0)  # setter cleared; walk skipped
            m.put(body + 0x48, 0)

    def test_native_phase_assignment_is_team_and_carrier_based_not_position_or_fpf(self):
        m = self.machine()
        for pos in range(17):
            body, block = self.body(m, position=pos)
            m.put(body + 0x20, m.BODIES + 0x4000)
            m.put(body + 0x24, m.BODIES + 0x5000)
            for side, carrier, context in ((0xE5FC20, 0, 9), (0xE5FC20, 1, 10), (0xE5FC60, 0, 11)):
                m.put(body, carrier)
                m.put(body + 0x38, side)
                m.put(block + 4, 0)
                m.call(0x1569E0)
                self.assertEqual(m.get(block + 4), context)
                self.assertEqual(m.get(0xA9B960), context)
                m.call(0xAF000)
                self.assertEqual(m.get(block + 4), 3 if side == 0xE5FC20 else 4)
        m.put(0xE602B8, 13)
        m.put(block + 4, 15)
        m.call(0x1569E0)
        self.assertEqual(m.get(block + 4), 15)

    def test_kick_qb_carrier_presnap_and_engaged_defense_decode_native_commands(self):
        m = self.machine()
        _, block = self.body(m)
        # Physical cache masks, default layout. These prove command selection,
        # not player-facing button names or execution of the resulting action.
        cases = ((2, 0x400, 0x37), (3, 0x100, 3), (5, 1, 0x93),
                 (6, 0x400, 0x43), (8, 0x40000, 0x24), (9, 0x800, 0x68),
                 (10, 0x40000, 0x24), (11, 0x400, 4), (16, 0x40000, 6))
        for ctx, bits, expected in cases:
            self.assertEqual(self.input(m, block, ctx, bits), expected, (ctx, bits))

    def test_offball_command_reaches_native_handler_without_global_fpf_flag(self):
        m = self.machine()
        body, block = self.body(m, position=8)
        state, match = m.BODIES + 0x4000, m.BODIES + 0x6000
        m.put(body + 0x10, state)
        m.put(0xE602EC, match)
        m.put(match + 0x1C8, body)
        m.put(0xE602C0, 3)
        m.put(state + 0x188, 99)
        # Bounded at animation bookkeeping. Native dispatcher and contextual
        # decision run; no catch animation/ball-flight success is asserted.
        m.stub(0x1B3340, lambda: m.ret())
        m.stub(0x1E2FC0, lambda: m.ret())
        self.assertEqual(self.input(m, block, 9, 0x400), 0x67)
        m.call(0x18EC40)
        self.assertEqual(m.get(block + 0x1C), 4)
        self.assertEqual(m.get(state + 0x188), 0)
        self.assertEqual(m.get(0xE5FFE4), 0)

    def test_native_offball_command68_requests_action_with_fpf_off(self):
        m = self.machine()
        body, block = self.body(m, position=9)
        m.stub(0x1E2FC0, lambda: m.ret())
        m.stub(0x1E3110, lambda: m.ret(0))  # animation-state boundary
        m.stub(0x1B3340, lambda: m.ret())
        for ball_state, request in ((3, 0x5A), (4, 0x55)):
            m.put(0xE602C0, ball_state)
            self.assertEqual(self.input(m, block, 9, 0x800), 0x68)
            m.call(0x18EC40)
            self.assertEqual(m.get(block + 0x1C), request)
            self.assertEqual(m.get(0xE5FFE4), 0)

    def test_fpf_exhibition_entry_sets_global_mode_not_receiver_context(self):
        m = self.machine()
        body, block = self.body(m, position=3)
        m.put(block + 4, 9)
        m.put(0xE5FF8C, 5)
        before = bytes(m.uc.mem_read(body, 0x100))
        context = bytes(m.uc.mem_read(block, 36))
        # Entry UI/audio/team selection is outside this bounded proof.
        m.stub(0x38650, lambda: m.ret(0, pop=24))
        for va in (0x89DA0, 0x77560, 0x77AA0, 0x77AE0, 0x77AC0, 0x77B20):
            m.stub(va, lambda: m.ret())
        flow = []
        m.stub(0x2C1950, lambda: (flow.append(m.reg('EAX')), m.ret()))
        m.call(0x2C1FC0, ecx=m.BODIES + 0x4000)
        self.assertEqual(flow, [7])
        self.assertEqual(m.get(0xE5FFE4), 1)
        self.assertEqual(m.get(0xE5FF80), 4)
        self.assertEqual(m.get(0xACF610), 5)
        self.assertEqual(m.get(0xE5FF8C), 1)
        self.assertEqual(bytes(m.uc.mem_read(body, 0x100)), before)
        self.assertEqual(bytes(m.uc.mem_read(block, 36)), context)

    def test_engaged_move_consumes_input_in_native_accumulator_only_in_its_behavior(self):
        m = self.machine()
        body, block = self.body(m, position=16)
        state, descriptor = m.BODIES + 0x4000, m.BODIES + 0x6000
        m.put(body + 0x10, state)
        m.put(state + 4, descriptor)
        for active in (False, True):
            m.put(descriptor, 0x02000000 if active else 0x01000000)
            m.put(state + 0x124, 0)
            self.assertEqual(self.input(m, block, 16, 0x40000), 6)
            m.uc.mem_write(0xB37B58, struct.pack('<f', 1.0))
            m.call(0x18DBE0, ecx=body)
            self.assertEqual(m.get(block + 0x1C), 0)
            self.assertEqual(m.get(state + 0x124), 0x80 if active else 0)

    def test_bound_non_default_defender_survives_each_switch_and_transfer_guard(self):
        for pos in (4, 5, 6, 10, 11, 15, 16):
            save, setup, _ = prepared(pos)
            payload = career.apply(self.retail, setup=setup)[0]
            m = Machine(payload, save, career.read_setup(setup))
            m.activate()
            body = m.bodies()
            for hook, args in ((0x1A7970, ()), (0x1A77A0, ()), (0x1A85E0, ()),
                               (0x1A70E0, (body, body + 0x100, 0))):
                # Retail requested a different defender. The guard resolves the
                # roster identity again; it must not accept that requested body.
                m.put(0xBD8210, -1)
                m.put(0xBD8210 + 36, 0)
                m.call(hook, ecx=body + 0x100, args=args)
                self.assertEqual([m.get(0xBD8210 + 36 * i) for i in range(22)],
                                 [0] + [0xFFFFFFFF] * 21, (pos, hex(hook)))
                self.assertEqual(m.get(m.state + 2568), body)


if __name__ == '__main__':
    unittest.main()
