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

    def __init__(self, payload, resource, *, rpo=False, controller=-1, layout=0, context=8, buffer=0, direction=1, play_index=None):
        super().__init__(payload, patched=False, direction=direction)
        self.load_book(resource, buffer)
        self.base = getattr(self, 'loaded_base', 0xB75A40 + buffer*0x13390)
        self.pi = (157 if rpo else 155) if play_index is None else play_index
        self.qs = self.QB+0x600
        self.task = self.QB+0xE00
        self.interp = self.qs+0x41C
        self.rpo = rpo
        self.player(self.OTHER, self.OFF)
        self.u32(self.OFF+0x20, self.base)
        self.u32(self.DEF+0x20, self.base)
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
        self.state_va = patch.allocations(payload)['data']['va']
        self.uc.mem_write(self.P+0xD35, b'\x10')  # roster DE
        self.u32(self.P+0x600+0x41C, self.base+0x3404+8)  # live MIN GL Pinch rush
        self.snap_read()
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)

    def edge(self, *, x=-2, vx=4, z=-1, vz=0):
        for off, value in ((0x30, x*91.44), (0x38, 1200+z*91.44), (0x40, vx*91.44), (0x48, vz*91.44)):
            self.f32(self.P+0x400+off, value)

    def ready(self, yes):
        self.u32(self.OTHER+0x200+4, 0x50F4EC)
        self.u32(self.OTHER+0x600+0x420, 0x20000 if yes else 0)

    def tick(self, time=.35, *, held=True, throw=False, stop_at=None):
        self.f32(self.GAME+0x400+0x10, time)
        if 0 <= self.controller <= 3:
            self.u32(0xA9B95C+self.controller*44, 0x100 if held else 0)
            self.u32(0xA9B954+self.controller*44, getattr(self, 'throw_mask', 0x200) if throw else 0)
        # Actual stack geometry at1AF009 after the retail aligned prologue.
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
        self.uc.emu_start(patch.HOOKS['tick'][0], self.STOP, count=12000)
        end = self.uc.reg_read(x86.UC_X86_REG_EIP)
        if end != (stop_at or self.STOP):
            raise AssertionError(f'bounded tick failed to stop: {end:#x}')
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def snap_read(self):
        self.run(0xB6FBD, stop_at=0xB6FC3)

    def frames(self, count, **kwargs):
        result = None
        for _ in range(count):
            time = self.readf(self.GAME+0x400+0x10) + 1/60
            result = self.tick(time, **kwargs)
        return result

    def finish(self, **kwargs):
        result = None
        stop_at = kwargs.pop('stop_at', None)
        for _ in range(patch.MESH_FRAMES+2):
            now = self.readf(self.GAME+0x410)
            deadline = self.readf(self.state_va+44)
            when = min(now+1/60, deadline) if deadline > now else now+1/60
            result = self.tick(when, stop_at=stop_at if deadline and when >= deadline else None,
                               **kwargs)
            if self.get(self.task+0x44) <= 2:
                return result
        raise AssertionError('mesh failed to reach its game-time deadline')

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
        import gc
        gc.collect()  # release prior Unicorn callback cycles before mapping another XBE
        return Machine(self.payload, self.resource, **kwargs)

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


    def test_tick_before_snap_reception_keeps_native_condition_pending(self):
        m=self.machine(controller=0)
        before=bytes(m.uc.mem_read(m.state_va,256))
        m.tick(.2,stop_at=0x1AF210)
        self.assertEqual(bytes(m.uc.mem_read(m.state_va,256)),before)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EBX),0xFFFFFFFF)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EFLAGS),0x246)

    def test_unpaired_tick_retains_retail_condition(self):
        m=self.machine(controller=0)
        m.u32(m.state_va+12,0)
        m.tick(.2,stop_at=0x1AF013)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EBX),0xFFFFFFFF)

    def test_stopped_or_cancelled_tick_cannot_reenter_give(self):
        for decision in (0, 1, 2, 3, 4):
            m = self.machine(controller=0)
            m.u32(m.state_va+76, 1)
            m.u32(m.state_va+28, decision)
            m.tick(.2, stop_at=0x1AF013)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EBX), 0xFFFFFFFF)

    def test_started_tick_has_native_give_result_without_float_or_register_damage(self):
        # Isolate the hook ABI; full frames prove the scheduler produces start.
        m=self.machine(controller=0);m.u32(m.state_va+76,1)
        m.uc.reg_write(x86.UC_X86_REG_XMM0,0x0123456789ABCDEF)
        m.tick(.2,stop_at=0x1AF210)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EBX),1)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP),m.STACK-0x60)
        for register,expected in (('EBP',m.STACK-4),('ESI',m.QB),('EDI',m.task),('ECX',m.interp),('EDX',0x2345),('EFLAGS',0x246)):
            self.assertEqual(m.uc.reg_read(getattr(x86,'UC_X86_REG_'+register)),expected)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_XMM0),0x0123456789ABCDEF)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW),0x37F)
        self.assertEqual(m.get(m.state_va+28),0xFFFFFFFF)

    def test_native_xbox_packet_conversion_proves_a_x_and_black_masks(self):
        m=self.machine(controller=0)
        # Execute the packet decoder after XInputGetState returns. Hardware
        # polling and the later game input copy are outside this proof.
        native=0x3040000
        m.uc.mem_write(native+0x24,struct.pack('<12h',*([8192]*12)))
        for button,expected in ((0,0x100),(1,0x200),(2,0x400),(4,0x1000)):
            m.uc.mem_write(m.STACK+0x2A,bytes(22))
            m.u32(m.STACK+0x2A,button+1)
            m.uc.mem_write(m.STACK+0x30+button,b'\xff')
            m.run(0x39480,esi=native,edi=0,stop_at=0x396CE)
            self.assertEqual(m.get(native+0x6C),expected)


if __name__ == '__main__':
    unittest.main()
