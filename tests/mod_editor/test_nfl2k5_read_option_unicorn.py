"""Bounded installed native instructions. No game loop, display or disc build.

The native PLAY loader, held-command lookup, receiver readiness, decision-cache
reader, and interpreter advancement run unstubbed. Mesh movement/collision and
animation entry are outside the named tick-boundary fixture, not witnessed.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / 'tools'):
    sys.path.insert(0, str(entry))
from mod_editor.core import nfl2k5_read_option_runtime as patch
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_read_option_runtime import XBE, compiled_reads
try:
    import unicorn as uc
    from unicorn import x86_const as x86
    from tests.mod_editor.test_nfl2k5_qb_spy_unicorn import Machine as NativeMachine
except ImportError:
    uc = x86 = None
    NativeMachine = object


class Machine(NativeMachine):
    def run(self, *args, **kwargs):
        super().run(*args, **kwargs)
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def __init__(self, payload, resource, *, rpo=False, controller=-1, layout=0, context=8, buffer=0, direction=1):
        super().__init__(payload, patched=False, direction=direction)
        self.load_book(resource, buffer)
        self.base = 0xB75A40 + buffer*0x13390
        self.pi = 157 if rpo else 155
        self.qs = self.QB+0x600
        self.task = self.QB+0xE00
        self.interp = self.qs+0x41C
        self.rpo = rpo
        self.player(self.OTHER, self.OFF)
        self.u32(self.OFF, self.DEF)
        self.u32(self.DEF, self.OFF)
        self.u32(self.OFF+4, self.QB)
        self.u32(self.OFF+12, self.OFF+0x100)
        self.u32(self.QB+0x34, self.RB)
        self.u32(self.RB+0x34, self.OTHER)
        self.u32(self.DEF+4, self.P)
        self.u32(self.P+0x34, 0)
        self.uc.mem_write(self.QB+0x2E, b'\0')
        self.uc.mem_write(self.RB+0x2E, b'\x0a')
        self.uc.mem_write(self.OTHER+0x2E, b'\x07')
        # Both legacy fixtures need correction: slot2 is a DT, slot6 is an
        # off-ball OLB. The authored formation's run-side EDGE is slot1.
        self.uc.mem_write(self.P+0x2E, b'\x01')
        self.u32(0xBE4E20, 0x521078)
        self.u32(self.interp, self.base+0x3404+self.pi*96)
        self.u32(self.interp+4, 4<<3)
        self.uc.mem_write(self.qs+0x450, b'\x02')
        for i, value in enumerate((4, -91.44, -274.32, 2, 4, 1, 13, 0)):
            self.f32(self.interp+0x14+4*i, value)
        self.u32(self.task, 0x1AEF80)
        self.u32(self.task+0x40, self.P)
        self.f32(self.task+0x44, 13)
        self.f32(self.task+0x20, -91.44*direction)
        self.f32(self.task+0x28, 1200-274.32*direction)
        self.f32(self.task+0x60, .15)
        self.u32(0xE6029C, self.GAME+0x400)
        self.f32(self.GAME+0x10, 0)
        self.u32(self.QB+0x100, controller)
        if 0 <= controller <= 3:
            self.u32(0xA9B960+controller*44, context)
            self.u32(0xE5FE90+controller*28, layout)
        self.controller = controller
        self.edge(x=-2*direction, vx=4*direction)
        self.ready(True)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)

    def edge(self, *, x=-2, vx=4, z=-1, vz=0):
        for off, value in ((0x30, x*91.44), (0x38, z*91.44), (0x40, vx*91.44), (0x48, vz*91.44)):
            self.f32(self.P+0x400+off, value)

    def ready(self, yes):
        self.u32(self.OTHER+0x200+4, 0x50F4EC)
        self.u32(self.OTHER+0x600+0x420, 0x20000 if yes else 0)

    def tick(self, time=.35, *, held=True, throw=False, stop_at=None):
        self.f32(self.GAME+0x400+0x10, time)
        if 0 <= self.controller <= 3:
            self.u32(0xA9B95C+self.controller*44, 0x100 if held else 0)
            self.u32(0xA9B954+self.controller*44, 0x200 if throw else 0)
        # Actual stack geometry at1AF191 after the retail aligned prologue.
        native_sp = self.STACK-0x60
        self.u32(self.STACK-4, 0x6789)
        self.u32(native_sp, 0x5678)
        self.u32(native_sp+4, 0x4567)
        self.u32(native_sp+8, 0x3456)
        self.u32(native_sp+0x24, self.interp)
        self.u32(native_sp+0x28, 0)
        self.u32(self.STACK, self.STOP)
        self.stop_at, self.calls, self.hits, self.writes = stop_at, [], [], []
        values = dict(ESP=native_sp, EBP=self.STACK-4, ESI=self.QB, EDI=self.task,
                      ECX=self.interp, EBX=0xFFFFFFFF, EDX=0x2345, EAX=0x789A, EFLAGS=0x246)
        for name, value in values.items():
            self.uc.reg_write(getattr(x86, 'UC_X86_REG_'+name), value)
        self.uc.emu_start(0x1AF191, self.STOP, count=12000)
        end = self.uc.reg_read(x86.UC_X86_REG_EIP)
        if end != (stop_at or self.STOP):
            raise AssertionError(f'bounded tick failed to stop: {end:#x}')
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def back_result(self):
        state = self.RB+0x600
        interp = state+0x41C
        self.u32(interp, self.base+0x3404+self.pi*96+10*8)
        self.uc.mem_write(interp+0x34, b'\x01')
        for i, value in enumerate((6, -91.44, -274.32, 0, 3, 0, 2, 0)):
            self.f32(interp+0x14+i*4, value)
        return self.run(0x1ACE40, eax=self.QB, args=(self.RB, 0x1A, 0))


@unittest.skipUnless(uc is not None and XBE.is_file(), 'Unicorn and pinned retail USA XBE are required')
class InstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('local XBE differs from pinned USA evidence')
        _, compiled = compiled_reads()
        cls.resource = compiled.replacement
        cls.table = patch.compile_intent_table([(compiled.replacement, compiled.report)])[0]
        cls.payload, _ = patch.apply(retail, intent_table=cls.table)

    def machine(self, **kwargs):
        return Machine(self.payload, self.resource, **kwargs)

    def test_cpu_crash_keep_widen_give_position_velocity_and_both_directions(self):
        for direction in (1, -1):
            for x, vx, expected in ((-2, 4, 0), (-2, 0, 1), (-4, -2, 1), (-8, 4, 1)):
                with self.subTest(direction=direction, x=x, vx=vx):
                    m = self.machine(direction=direction)
                    m.edge(x=x*direction, vx=vx*direction)
                    self.assertEqual(m.tick(), 1)
                    self.assertEqual(m.get(m.task+0x44), expected)
                    self.assertEqual(m.get(0xBE4E28+2*4), expected)
                    self.assertEqual(m.back_result(), expected)
                    self.assertEqual(m.get(m.BALL), m.QB)

    def test_human_hold_release_boundary_all_layouts_contexts_and_controllers(self):
        for controller in range(4):
            for layout in range(3):
                for context in (8, 10):
                    for held, expected in ((False, 1), (True, 0)):
                        with self.subTest(controller=controller, layout=layout, context=context, held=held):
                            m = self.machine(controller=controller, layout=layout, context=context)
                            self.assertEqual(m.tick(.349, held=held), 0)
                            self.assertEqual(m.get(0xBE4E28+8), 0xFFFFFFFF)
                            self.assertEqual(m.tick(.35, held=held), 1)
                            self.assertEqual(m.get(m.task+0x44), expected)
                            self.assertIn(0x120960, m.hits)
                            self.assertIn(0x77230, m.hits)

    def test_release_is_sticky_reholding_and_late_input_cannot_change_commit(self):
        m = self.machine(controller=0)
        m.tick(.1, held=False)
        m.tick(.2, held=True)
        m.tick(.35, held=True)
        self.assertEqual(m.get(m.task+0x44), 1)
        m.edge(x=-2, vx=4)
        m.tick(.4, held=True, throw=True)
        self.assertEqual(m.get(m.task+0x44), 1)
        self.assertNotIn(0x120960, m.hits)

    def test_rpo_cpu_throw_ready_default_give_unready_and_human_keep_exit(self):
        for ready, decision in ((True, 2), (False, 1)):
            m = self.machine(rpo=True); m.ready(ready)
            m.tick()
            self.assertIn(0x19B800, m.hits)
            self.assertEqual(m.get(m.task+0x44), decision)
            self.assertEqual(m.back_result(), int(decision == 1))
        m = self.machine(rpo=True, controller=0)
        m.tick(stop_at=0x1AF292)
        self.assertEqual(m.get(m.task+0x44), 0)
        self.assertTrue(m.get(m.interp+4) & 0x20000)
        self.assertEqual(m.get(0xBE4E28+8), 0)

    def test_human_rpo_press_has_single_priority_and_receiver_readiness(self):
        m = self.machine(rpo=True, controller=1)
        m.tick(.2, throw=True)
        m.tick(.3, held=False)
        m.tick(.35, held=False)
        self.assertEqual(m.get(m.task+0x44), 2)
        m.tick(.5, held=False)
        self.assertEqual(m.get(m.task+0x44), 2)
        m = self.machine(rpo=True, controller=0); m.ready(False)
        m.tick(.2, throw=True); m.tick(.35)
        self.assertEqual(m.get(m.task+0x44), 1)

    def test_native_loader_buffers_script_name_and_slot_scope(self):
        for buffer in (0, 1):
            m = self.machine(buffer=buffer)
            m.tick()
            self.assertEqual(m.get(m.task+0x44), 0)
        for field in ('name', 'qb_script', 'back_script', 'slot', 'node', 'assignment'):
            m = self.machine()
            descriptor = m.base+0x3404+m.pi*96
            address = dict(name=m.get(descriptor-8), qb_script=m.get(descriptor+4),
                           back_script=m.get(descriptor+84), slot=m.QB+0x2E,
                           node=m.qs+0x450, assignment=m.interp)[field]
            old = m.uc.mem_read(address, 1)
            m.uc.mem_write(address, bytes([old[0] ^ 1]))
            m.tick(stop_at=0x1AF19A)
            self.assertEqual(m.get(m.task+0x44), 0x41500000)

    def test_instructions_relocate_in_the_complete_owner_allocation_union(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        from mod_editor.core import nfl2k5_xbe_space as space
        allocated, _ = space.apply(XBE.read_bytes(), REQUESTS, scaleout=True)
        output, _ = patch.apply(allocated, intent_table=self.table)
        self.assertNotEqual(patch.allocations(output), patch.allocations(self.payload))
        m = Machine(output, self.resource, controller=2, layout=2, context=10)
        m.tick(.2, held=False)
        m.tick(.35, held=True)
        self.assertEqual(m.get(m.task+0x44), 1)
        self.assertEqual(m.back_result(), 1)

    def test_native_cache_wait_and_interpreter_give_keep_pass_advancement(self):
        for rpo, held, expected in ((False, False, 4), (False, True, 3), (True, True, 3)):
            m = self.machine(rpo=rpo, controller=-1 if rpo else 0)
            m.tick(.1, held=held)
            self.assertEqual(m.back_result(), 0xFFFFFFFF)
            m.tick(.35, held=held)
            self.assertEqual(m.run(0x1B8A20, ecx=m.interp), expected)

    def test_missing_read_and_nonfinite_geometry_default_give(self):
        for value in (float('nan'), float('inf'), -float('inf'), 1e8):
            m = self.machine(); m.edge(x=value)
            m.tick(); self.assertEqual(m.get(m.task+0x44), 1)
        m = self.machine(); m.u32(m.DEF+4, 0)
        m.tick(); self.assertEqual(m.get(m.task+0x44), 1)

    def test_downfield_crash_and_a_blocked_edge(self):
        for direction in (1, -1):
            m = self.machine(direction=direction)
            m.edge(x=-2*direction, vx=0, vz=-4*direction)
            m.tick()
            self.assertEqual(m.get(m.task+0x44), 0)
        m = self.machine()
        m.u32(m.RB+0xE00+0x40, m.P)
        m.tick()
        self.assertEqual(m.get(m.task+0x44), 1)

    def test_native_speed_option_pitch_keep_and_back_requests_remain_native(self):
        for request, expected in ((False, 0), (True, 1)):
            m = self.machine(controller=0)
            descriptor = m.base+0x3404+24*96  # untouched native MIN24 control
            m.u32(m.interp, descriptor)
            m.uc.mem_write(m.interp+0x34, b'\x03')
            m.u32(m.interp+4, 4<<3 | 0x20000)
            for i, value in enumerate((4, -1280, 0, 10, 4, 0, 13, 1)):
                m.f32(m.interp+0x14+i*4, value)
            m.u32(m.RB+0xE00+0x40, m.QB)
            m.f32(m.GAME+0x400+0x10, .35)
            m.u32(m.QB+0x100+0x18, 0xA400 | (0x100 if request else 0))
            self.assertEqual(m.run(0x1ACE40, eax=m.RB, args=(m.QB, 0x1A, 1)), expected)
            self.assertEqual(m.get(m.QB+0x100+0x18), 0xA400)
            if request:
                m.u32(m.interp+4, 4<<3 | 4)
            self.assertEqual(m.run(0x1B8A20, ecx=m.interp), 4 if request else 0xFFFFFFFF)
            if request:
                pitch_node = m.get(descriptor+4)+4*8
                self.assertEqual(m.uc.mem_read(pitch_node, 1), b'\x13')

    def test_dead_ball_lost_ownership_takeover_and_fresh_initializer_state(self):
        m = self.machine(); m.u32(0xE602B8, 15)
        m.tick(); self.assertEqual(m.get(0xBE4E28+8), 0xFFFFFFFF)
        m = self.machine(rpo=True); m.u32(m.BALL, m.RB)
        m.tick(stop_at=0x1AF292)
        self.assertEqual(m.get(m.task+0x44), 0)
        m = self.machine(); m.tick(); m.controller = 0; m.u32(m.QB+0x100, 0)
        m.tick(.4, held=False); self.assertEqual(m.get(m.task+0x44), 0)
        # The actual initializer writes the argument at1AF98D. Execute that
        # slice to reset the documented union, retaining the native callback.
        m.u32(m.STACK+0x2C, 0x41500000)
        m.run(0x1AF98D, stop_at=0x1AF994, ebx=m.task)
        m.u32(0xA9B960, 8); m.u32(0xE5FE90, 0)
        m.tick(.1, held=False); m.tick(.35, held=False)
        self.assertEqual(m.get(m.task+0x44), 1)

    def test_native_new_play_clears_prior_shared_decisions_before_either_actor(self):
        m = self.machine(controller=0)
        m.tick(held=False)
        self.assertEqual(m.get(0xBE4E28+8), 1)
        m.run(0x1AD9C0, stop_at=0x1AD9DE)
        self.assertEqual(bytes(m.uc.mem_read(0xBE4E28, 88*4)), b'\xff'*(88*4))
        self.assertEqual(m.back_result(), 0xFFFFFFFF)

    def test_added_work_preserves_abi_float_state_and_writes_only_native_state(self):
        m = self.machine(controller=0)
        m.uc.reg_write(x86.UC_X86_REG_XMM0, 0x0123456789ABCDEF)
        m.tick(.2, stop_at=0x1AF210)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK-0x60)
        for register, expected in ((x86.UC_X86_REG_EBP, m.STACK-4), (x86.UC_X86_REG_ESI, m.QB),
                (x86.UC_X86_REG_EDI, m.task), (x86.UC_X86_REG_ECX, m.interp),
                (x86.UC_X86_REG_EDX, 0x2345), (x86.UC_X86_REG_EFLAGS, 0x246)):
            self.assertEqual(m.uc.reg_read(register), expected)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_XMM0), 0x0123456789ABCDEF)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW), 0x37F)
        for address, size in m.writes:
            self.assertTrue(0x3100000 <= address < m.STACK or
                            m.task+0x40 <= address and address+size <= m.task+0x48, hex(address))


if __name__ == '__main__':
    unittest.main()
