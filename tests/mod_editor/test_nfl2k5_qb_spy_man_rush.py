"""Bounded man/rush instruction proofs, EXPERIMENTAL / UNWITNESSED.

Native initializer and callback bodies execute from the pinned XBE. Explicit
helper boundaries model allocation, animation, selection and movement only;
these are ABI/decision proofs, not complete navigation or gameplay simulation.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_qb_spy_runtime import XBE, compiled_spy
from tests.mod_editor.test_nfl2k5_qb_spy_unicorn import Machine, uc, x86

CALLBACKS = (0x2FE120, 0x2FE130, 0x2FD930, 0x2EFDB0,
             0x1A4830, 0x1A4DA0, 0x1A4D70, 0x1A4DD0)
CONTINUATIONS = dict(rush_main=0x2FDF36, rush_delay=0x2FE136,
                     rush_lane=0x2EFDB5, man_main=0x1A4836,
                     man_press=0x1A4DA9, man_release=0x1A4D76,
                     man_exchange=0x1A4DD6)
REGISTERS = ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP', 'EFLAGS')


class NativeMachine(Machine):
    def __init__(self, payload, **kwargs):
        self.initializing = False
        self.boundaries = []
        self.man_target = self.RB
        self.exchange = 0
        self.press = 0
        self.delay = 0.0
        self.native_early = False
        self.transition_rewrite = False
        super().__init__(payload, **kwargs)
        for p in (self.P, self.QB, self.RB, self.OTHER):
            self.u32(p+0x24, p+0x1100)
            self.u32(p+0x204, p+0x1200)
            self.u32(p+0xE40, self.RB)
            self.u32(p+0xE48, self.OTHER)
        self.u32(self.DEF+8, self.DEF+0x200)
        self.u32(self.DEF+0x20C, self.DEF+0x300)
        self.f32(self.DEF+0x304, -self.direction)
        self.u32(0xC8F164, self.QB)
        self.u32(0xE6029C, self.GAME+0x400)
        self.f32(self.GAME+0x410, 0.25)

    def return_helper(self, address, *, result=None, cleanup=0):
        self.boundaries.append(address)
        esp = self.uc.reg_read(x86.UC_X86_REG_ESP)
        target = self.get(esp)
        if result is not None:
            self.uc.reg_write(x86.UC_X86_REG_EAX, result)
        self.uc.reg_write(x86.UC_X86_REG_ESP, esp+4+cleanup)
        self.uc.reg_write(x86.UC_X86_REG_EIP, target)

    def observe(self, u, address, size, data):
        if address == self.stop_at:
            return super().observe(u, address, size, data)
        if self.initializing:
            # Allocation and animation/event boundaries. The original three
            # initializer bodies, their branches and callback writes run intact.
            if address == 0x2C9AB0:
                state = u.reg_read(x86.UC_X86_REG_ECX)
                self.u32(self.get(state+0x310), 0x1ABE40)
                return self.return_helper(address)
            if address in (0x2E6790, 0x23A8D0, 0x23A8C0, 0xAF510):
                return self.return_helper(address)
            if address == 0x1A0200:
                return self.return_helper(address, result=self.man_target)
            if address == 0x1A0190:
                return self.return_helper(address, cleanup=4)
            if address == 0x20F230:
                return self.return_helper(address, result=1)
            if address == 0x19FC90:
                return self.return_helper(address, result=self.exchange)
            if address in (0x1AE370, 0x217AE0):
                return self.return_helper(address, result=0, cleanup=4 if address == 0x1AE370 else 0)
            if address == 0x1894F0:
                return self.return_helper(address, result=self.OTHER)
            if address in (0x1B8CA0, 0x1B8C40):
                esp = u.reg_read(x86.UC_X86_REG_ESP)
                operand, output = self.get(esp+4), self.get(esp+8)
                opcode = u.reg_read(x86.UC_X86_REG_EDX)
                if address == 0x1B8C40:
                    self.f32(output, self.delay if opcode in (11, 12) else 4*91.44)
                else:
                    self.u32(output, self.press if opcode == 14 and operand == 0 else 0)
                return self.return_helper(address, result=0, cleanup=8)
            if address == 0x1F1610:
                return self.return_helper(address, cleanup=4)
        if self.native_early:
            if address == 0x1A0200:
                return self.return_helper(address, result=self.man_target)
            if address == 0x19FC60:
                return self.return_helper(address, result=1, cleanup=4)
            if address == 0x19E5B0:
                return self.return_helper(address, result=1, cleanup=8)
            if address == 0x231EE0:
                return self.return_helper(address, result=0)
            if address == 0x2FD700:
                output = u.reg_read(x86.UC_X86_REG_ESI)
                self.uc.mem_write(output, bytes(16))
                return self.return_helper(address, cleanup=8)
            if address == 0x2FD940:
                return self.return_helper(address, cleanup=4)
        if address == 0x214B90 and self.transition_rewrite:
            # Model a native initializer replacing the SAME state buffer, the
            # important case for avoiding stale target/callback restoration.
            actor = u.reg_read(x86.UC_X86_REG_EDX)
            ai = self.get(self.get(actor+0x20)+0x310)
            self.u32(ai, 0x2EB100)
            self.u32(ai+0x40, self.RB)
            self.u32(ai+0x48, 0)
        if address in (0x1A4170, 0x1ADF90):
            actor = u.reg_read(x86.UC_X86_REG_ECX)
            ai = self.get(self.get(actor+0x20)+0x310)
            self.movement_targets = (self.get(ai+0x40), self.get(ai+0x48))
        return super().observe(u, address, size, data)

    def initialize(self, opcode):
        self.run(0x1B85A0)  # actual dispatch-table setup, including patched MOVs
        entry = self.get(0xBE5110+opcode*4)
        self.initializing = True
        self.boundaries = []
        try:
            self.run(entry, count=30000)
        finally:
            self.initializing = False
        return self.get(self.P+0xE00)

    def tick(self, **kwargs):
        return self.run(self.get(self.P+0xE00), **kwargs)


@unittest.skipUnless(XBE.is_file() and uc is not None,
                     'pinned USA retail extraction and Unicorn required for man/rush proofs')
class ManRushTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('XBE is not pinned USA retail evidence')
        cls.payload = spy.apply(cls.retail)[0]

    def machine(self, **kwargs):
        return NativeMachine(self.payload, **kwargs)

    def test_all_native_initializers_and_man_early_exit_preserve_native_state(self):
        for opcode, settings, expected in (
            (11, {}, 0x2FE120), (11, {'delay': 1.0}, 0x2FE130),
            (12, {}, 0x2EFDB0), (14, {}, 0x1A4830),
            (14, {'press': 1}, 0x1A4DA0), (14, {'exchange': 1}, 0x1A4DD0),
            (14, {'man_target': 0}, 0x1ABE40),
        ):
            with self.subTest(opcode=opcode, settings=settings):
                actual = self.machine()
                retail = NativeMachine(self.retail, patched=False)
                for m in (actual, retail):
                    m.uc.reg_write(x86.UC_X86_REG_FPCW, 0xB7F)
                    for key, value in settings.items(): setattr(m, key, value)
                    m.u32(m.P+0x600+0x420, 0x20000)
                    self.assertEqual(m.initialize(opcode), expected)
                self.assertEqual(actual.boundaries, retail.boundaries)
                native = {11: 0x2FE190, 12: 0x2F10B0, 14: 0x1A5BC0}[opcode]
                self.assertEqual(actual.hits.count(native), 1)
                self.assertEqual(actual.uc.mem_read(actual.P, 0x2000), retail.uc.mem_read(retail.P, 0x2000))
                for name in REGISTERS:
                    reg = getattr(x86, 'UC_X86_REG_'+name)
                    self.assertEqual(actual.uc.reg_read(reg), retail.uc.reg_read(reg), name)
                for name in ('FPCW', 'FPSW', 'FPTAG', *('FP'+str(i) for i in range(8)),
                             *('XMM'+str(i) for i in range(8))):
                    reg = getattr(x86, 'UC_X86_REG_'+name)
                    self.assertEqual(actual.uc.reg_read(reg), retail.uc.reg_read(reg), name)

    def test_initialized_man_and_both_rushes_late_command_release_and_latch(self):
        for opcode in (11, 12, 14):
            for direction in (-1, 1):
                with self.subTest(opcode=opcode, direction=direction):
                    m = self.machine(direction=direction)
                    callback = m.initialize(opcode)
                    native_targets = (m.get(m.P+0xE40), m.get(m.P+0xE48))
                    m.command(); m.tick()
                    self.assertEqual((m.mode(), m.calls[0][0]), (1, 'steer'))
                    self.assertEqual(m.movement_targets, (m.QB, 0))
                    self.assertEqual(m.get(m.P+0xE00), callback)
                    self.assertEqual((m.get(m.P+0xE40), m.get(m.P+0xE48)), native_targets)
                    m.qb(depth=-1, vz=1); m.tick()
                    self.assertEqual((m.mode(), m.calls[0][0]), (2, 'pursue'))
                    m.command(); m.qb(depth=-5); m.tick()
                    self.assertEqual((m.mode(), m.calls[0][0]), (2, 'pursue'))
                    m.snap(); m.qb(x=4); m.tick()
                    self.assertEqual((m.mode(), m.calls[0][0]), (2, 'pursue'))

    def test_every_callback_uses_same_spy_and_retains_native_identity(self):
        for callback in CALLBACKS:
            with self.subTest(callback=hex(callback)):
                m = self.machine(); m.u32(m.P+0xE00, callback)
                m.command(); m.tick()
                self.assertEqual((m.mode(), m.calls[0][0]), (1, 'steer'))
                self.assertEqual(m.movement_targets, (m.QB, 0))
                self.assertEqual(m.get(m.P+0xE00), callback)
                self.assertEqual(m.get(m.P+0xE40), m.RB)
                self.assertEqual(m.get(m.P+0xE48), m.OTHER)
                self.assertNotIn(0x1A1510, m.hits)

    def test_all_unflagged_prologues_match_retail_registers_flags_and_stack(self):
        for name, continuation in CONTINUATIONS.items():
            for flags in (0x202, 0x246, 0xA97):
                with self.subTest(name=name, flags=flags):
                    actual = self.machine(); retail = NativeMachine(self.retail, patched=False)
                    entry = spy.HOOKS[name][0]
                    for m in (actual, retail):
                        m.u32(m.P+0xE00, entry)
                        m.run(entry, stop_at=continuation, eflags=flags)
                    for register in REGISTERS:
                        reg = getattr(x86, 'UC_X86_REG_'+register)
                        self.assertEqual(actual.uc.reg_read(reg), retail.uc.reg_read(reg), register)
                    # Compare initialized save slots and the caller return;
                    # native stack locals/alignment holes are uninitialized.
                    slots = [actual.STACK]
                    if name in ('rush_main', 'man_main', 'man_exchange', 'rush_delay'):
                        slots += [actual.STACK-4]
                    if name == 'rush_lane':
                        slots += [actual.STACK-28, actual.STACK-32]
                    for slot in slots: self.assertEqual(actual.get(slot), retail.get(slot))

    def test_handoff_transition_never_restores_old_callback_or_targets(self):
        for opcode in (11, 12, 14):
            m = self.machine(); m.initialize(opcode); m.command(); m.tick()
            m.u32(m.BALL, m.RB); m.transition_rewrite = True; m.tick()
            self.assertEqual(m.calls, [('transition', 0x2EB330, m.P)])
            self.assertEqual(m.mode(), 3)
            self.assertEqual((m.get(m.P+0xE00), m.get(m.P+0xE40), m.get(m.P+0xE48)), (0x2EB100, m.RB, 0))

    def test_pass_dead_ball_takeover_and_reset_restore_native_assignment(self):
        for opcode, name in ((11, 'rush_main'), (12, 'rush_lane'), (14, 'man_main')):
            for cause in ('pass', 'dead', 'controller', 'lock', 'reset'):
                with self.subTest(opcode=opcode, cause=cause):
                    m = self.machine(); callback = m.initialize(opcode)
                    targets = (m.get(m.P+0xE40), m.get(m.P+0xE48))
                    m.command(); m.tick()
                    if cause == 'pass': m.u32(m.BALL, 0)
                    elif cause == 'dead': m.u32(0xE602B8, 15)
                    elif cause == 'controller': m.u32(m.P+0x100, 0)
                    elif cause == 'lock': m.u32(m.P+0x600+0x584, 0x20)
                    else: m.run(0x18AEFC, stop_at=0x18AF03, esi=m.DEF+0x100)
                    m.tick(stop_at=CONTINUATIONS[name])
                    self.assertEqual(m.mode(), 0 if cause == 'reset' else 3)
                    self.assertEqual(m.get(m.P+0xE00), callback)
                    self.assertEqual((m.get(m.P+0xE40), m.get(m.P+0xE48)), targets)

    def test_native_rush_delay_rewrites_to_later_rush_then_late_command_engages(self):
        actual = self.machine(); retail = NativeMachine(self.retail, patched=False)
        for m in (actual, retail):
            m.delay = 1.0
            m.u32(m.P+0x600+0x420, 0x20000)
            self.assertEqual(m.initialize(11), 0x2FE130)
            m.f32(m.P+0xE60, 0.0)  # native delay countdown has expired
            m.f32(m.GAME+0x410, 100.0)  # beyond native rush phase timer
            m.native_early = True
            m.tick()
            self.assertIn(0x2FE153, m.hits)  # delay -> main rush
            self.assertIn(0x2FE03F, m.hits)  # main -> later rush
            self.assertEqual(m.get(m.P+0xE00), 0x2FD930)
        self.assertEqual(actual.uc.mem_read(actual.P, 0x2000), retail.uc.mem_read(retail.P, 0x2000))
        actual.command(); actual.tick()
        self.assertEqual((actual.mode(), actual.calls[0][0]), (1, 'steer'))
        actual.qb(x=4); actual.tick()
        self.assertEqual((actual.mode(), actual.calls[0][0]), (2, 'pursue'))

    def test_native_man_exchange_and_release_rewrites_remain_intercepted(self):
        for callback in (0x1A4DD0, 0x1A4D70):
            actual = self.machine(); retail = NativeMachine(self.retail, patched=False)
            for m in (actual, retail):
                m.u32(m.P+0xE00, callback)
                m.f32(m.GAME+0x410, 1.0)
                m.native_early = True
                m.tick()
                self.assertEqual(m.get(m.P+0xE00), 0x1A4830)
            self.assertEqual(actual.uc.mem_read(actual.P, 0x2000), retail.uc.mem_read(retail.P, 0x2000))
            actual.command(); actual.tick()
            self.assertEqual((actual.mode(), actual.calls[0][0]), (1, 'steer'))

    def test_native_exchange_peer_comparison_and_writes_match_retail(self):
        actual = self.machine(); retail = NativeMachine(self.retail, patched=False)
        for m in (actual, retail):
            m.u32(m.P+0xE00, 0x1A4DD0)
            m.u32(m.OTHER+0xE00, 0x1A4DD0)
            m.u32(m.DEF+4, m.OTHER)
            m.man_target = m.QB
            m.native_early = True
            m.tick(count=30000)
            self.assertIn(0x1A4E49, m.hits)  # native equality against peer callback
        self.assertEqual(actual.uc.mem_read(actual.P, 0x8000), retail.uc.mem_read(retail.P, 0x8000))
        self.assertEqual(actual.calls, retail.calls)

    def test_initializer_reset_assignment_snap_and_substitution_clear_stale_latch(self):
        for opcode in (11, 12, 14):
            m = self.machine(); m.initialize(opcode); m.command(); m.tick()
            m.qb(x=4); m.tick(); self.assertEqual(m.mode(), 2)
            m.initialize(opcode)  # same actor, roster and assignment addresses
            self.assertIsNone(m.slot())
            m.qb(x=0); m.tick(); self.assertEqual(m.mode(), 1)
            m.u32(m.P+0x3C, m.P+0xD10); m.qb(x=4); m.tick()
            self.assertEqual(m.get(m.slot()+24), m.P+0xD10)
            self.assertEqual(m.mode(), 2)
            m.run(0x1B8570, ecx=m.P+0x600+0x41C, edx=1)
            self.assertIsNone(m.slot())
            m.initialize(opcode); m.qb(x=-8); m.snap(); m.command(); m.tick()
            self.assertEqual(m.mode(), 1)
            self.assertAlmostEqual(m.readf(m.slot()+16), -8*91.44, places=3)

    def test_extension_fp_nonvolatile_registers_and_write_bounds(self):
        fp_regs = (x86.UC_X86_REG_FPCW, x86.UC_X86_REG_FPSW, x86.UC_X86_REG_FPTAG,
                   *[getattr(x86, 'UC_X86_REG_FP'+str(i)) for i in range(8)],
                   *[getattr(x86, 'UC_X86_REG_XMM'+str(i)) for i in range(8)])
        for callback in CALLBACKS:
            m = self.machine(); m.u32(m.P+0xE00, callback); m.command()
            for i in range(8):
                m.uc.reg_write(getattr(x86, 'UC_X86_REG_XMM'+str(i)), (i+1)*0x123456789ABCDEF123456789ABCDEF)
            m.uc.reg_write(x86.UC_X86_REG_FPCW, 0xB7F)
            m.uc.mem_write(m.STOP+0x100, b'\xd9\xeb\xd9\xe8\xc3')
            m.run(m.STOP+0x100)
            before = [m.uc.reg_read(r) for r in fp_regs]
            m.tick()
            self.assertEqual([m.uc.reg_read(r) for r in fp_regs], before)
            for name, value in (('EBX', 0x3456), ('ESI', 0x4567), ('EDI', 0x5678), ('EBP', 0x6789)):
                self.assertEqual(m.uc.reg_read(getattr(x86, 'UC_X86_REG_'+name)), value)
            for address, size in m.writes:
                self.assertTrue(any(lo <= address and address+size <= hi for lo, hi in (
                    (m.state_va, m.state_va+768), (m.P, m.P+0x2000), (0x3100000, 0x3110000))), hex(address))

    def test_extension_dispatch_consults_same_paired_v1_table(self):
        # Deliberately enter each extension callback with a loaded v1 identity.
        # This proves shared lookup, not a new authored man/rush PLAY grammar.
        _, compiled = compiled_spy()
        table, _ = spy.compile_intent_table([(compiled.replacement, compiled.report)])
        payload = spy.apply(self.retail, intent_table=table)[0]
        for callback in (0x2FE120, 0x2EFDB0, 0x1A4830):
            m = NativeMachine(payload)
            base = m.load_book(compiled.replacement)
            field = base+0x33FC+254*96+8+5*8
            m.u32(m.P+0x600+0x41C, field)
            m.u32(m.P+0xE00, callback)
            m.tick()
            self.assertEqual((m.mode(), m.calls[0][0]), (1, 'steer'))
            self.assertEqual(m.get(m.P+0x600+0x420) & 0x20000000, 0)

    def test_full_record_table_and_unknown_initializer_result_remain_native(self):
        m = self.machine()
        for i in range(22): m.u32(m.state_va+64+i*32, m.OTHER+i*4)
        m.u32(m.P+0xE00, 0x1A4830); m.command()
        m.tick(stop_at=CONTINUATIONS['man_main'])
        self.assertIsNone(m.slot())
        self.assertEqual((m.get(m.P+0xE40), m.get(m.P+0xE48)), (m.RB, m.OTHER))
        # The native man initializer can exit through pursuit before assigning
        # a supported callback; the wrapper must leave that result untouched.
        m = self.machine(); m.man_target = 0; m.transition_rewrite = True
        self.assertEqual(m.initialize(14), 0x2EB100)
        self.assertIsNone(m.slot())
        self.assertEqual((m.get(m.P+0xE40), m.get(m.P+0xE48)), (m.RB, 0))

    def test_zone_and_extension_execution_in_full_union_both_orders(self):
        from tests.nfl2k5_allocator_stack import compose
        forward, _ = compose(self.retail)
        reverse, _ = compose(self.retail, reverse=True)
        self.assertEqual(forward, reverse)
        for payload in (forward, reverse):
            for callback in (0x1A5790, 0x1A5090, 0x1A4830, 0x2FE120, 0x2EFDB0):
                m = NativeMachine(payload); m.u32(m.P+0xE00, callback)
                m.command(); m.tick()
                self.assertEqual((m.mode(), m.calls[0][0]), (1, 'steer'))
                m.qb(x=4); m.tick()
                self.assertEqual((m.mode(), m.calls[0][0]), (2, 'pursue'))
                m.qb(x=0); m.tick()
                self.assertEqual(m.calls[0][0], 'pursue')


if __name__ == '__main__':
    unittest.main()
