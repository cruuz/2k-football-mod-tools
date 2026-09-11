"""Bounded instruction proofs. No game boot or complete gameplay simulation.

Every added instruction executes. Movement/transition callees are recorded at
entry and returned with their pinned cleanup ABI, so decision/target assertions
are not a movement or tackle witness. The loader, command, assignment reset,
and signed-depth helper run their actual retail instructions without stubs.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / 'tools'): sys.path.insert(0, str(entry))
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_qb_spy_runtime import XBE, compiled_spy
try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:
    uc = x86 = None


class Machine:
    P, QB, RB, OTHER = 0x3000000, 0x3002000, 0x3004000, 0x3006000
    DEF, OFF, BALL, GAME, DIR, OFFMETA = 0x3010000, 0x3011000, 0x3012000, 0x3013000, 0x3014000, 0x3015000
    STACK, STOP, SOURCE = 0x310F000, 0x3120000, 0x3200000
    def __init__(self, payload, *, direction=1, patched=True):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        # Map real sections with the union of permissions on shared pages.
        pages = {}
        for section in image.sections:
            permission = uc.UC_PROT_READ | (uc.UC_PROT_WRITE if section.writable else 0) | (uc.UC_PROT_EXEC if section.flags & 4 else 0)
            for va in range(section.start & -4096, (section.end + 4095) & -4096, 4096): pages[va] = pages.get(va, 0) | permission
        # Some legacy header stubs execute; header page is distinct from sections.
        pages[0x10000] = uc.UC_PROT_ALL
        ranges = []
        for va, permission in sorted(pages.items()):
            if ranges and ranges[-1][1] == va and ranges[-1][2] == permission:
                ranges[-1][1] += 4096
            else:
                ranges.append([va, va+4096, permission])
        for start, end, permission in ranges: self.uc.mem_map(start, end-start, permission)
        self.uc.mem_write(0x10000, payload[:4096])
        for section in image.sections:
            if section.raw_size:
                self.uc.mem_write(section.start, image.read(section.start, section.raw_size))
        self.uc.mem_map(0x3000000, 0x100000)
        self.uc.mem_map(0x3100000, 0x20000)
        self.uc.mem_map(self.STOP, 0x1000)
        self.uc.mem_map(self.SOURCE, 0x20000)
        self.state_va = spy.allocations(payload)['data']['va'] if patched else None
        self.patched = patched
        self.player(self.P, self.DEF)
        self.player(self.QB, self.OFF)
        self.player(self.RB, self.OFF)
        self.player(self.OTHER, self.DEF)
        self.u32(0xE60280, self.OFF); self.u32(0xE60284, self.DEF)
        self.u32(0xE60288, self.OFF); self.u32(0xE602B8, 14)
        self.u32(0xE602EC, self.GAME); self.u32(0xE5FC00, self.BALL)
        self.u32(0xBE4F8C, self.QB); self.u32(self.BALL, self.QB)
        self.u32(self.OFF+8, self.OFFMETA); self.u32(self.OFFMETA+12, self.DIR)
        self.f32(self.DIR+4, direction)
        self.f32(self.GAME+0x18, 1200)
        self.u32(self.DEF+12, self.DEF+0x100)
        self.qb(x=0, depth=-5, vx=0, vz=0, direction=direction)
        self.direction = direction
        self.calls, self.hits = [], []
        self.stop_at = None
        self.code_hook = self.uc.hook_add(uc.UC_HOOK_CODE, self.observe)
        self.writes = []
        self.write_hook = self.uc.hook_add(uc.UC_HOOK_MEM_WRITE, lambda _u, _t, address, size, _value, _data: self.writes.append((address, size)))
        if patched: self.snap()

    def player(self, p, team):
        for off, value in ((0xC, p+0x100), (0x10, p+0x200), (0x14, p+0x300), (0x18, p+0x400),
                           (0x1C, 1), (0x20, p+0x600), (0x3C, p+0xD00), (0x38, team)):
            self.u32(p+off, value)
        self.u32(p+0x100, -1)
        self.u32(p+0x600+0x310, p+0xE00)
        self.u32(p+0x600+0x41C, p+0xF00)
        self.u32(p+0xE00, 0x1A5790)
        self.uc.mem_write(p+0x2E, b'\x05')

    def u32(self, a, v): self.uc.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))
    def get(self, a): return struct.unpack('<I', self.uc.mem_read(a, 4))[0]
    def f32(self, a, v): self.uc.mem_write(a, struct.pack('<f', v))
    def readf(self, a): return struct.unpack('<f', self.uc.mem_read(a, 4))[0]
    def qb(self, *, x=0, depth=-5, vx=0, vz=0, direction=None):
        direction = self.direction if direction is None else direction
        for off, value in ((0x30, x*91.44), (0x38, 1200+depth*91.44*direction), (0x40, vx*91.44), (0x48, vz*91.44*direction)):
            self.f32(self.QB+0x400+off, value)
    def slot(self, p=None):
        p = self.P if p is None else p
        for i in range(22):
            a = self.state_va+64+i*32
            if self.get(a) == p: return a
        return None
    def mode(self):
        a = self.slot()
        return self.get(a+20) if a else 0
    def observe(self, _u, address, _size, _data):
        self.hits.append(address)
        if address == self.stop_at:
            self.uc.emu_stop(); return
        if address in (0x1A5796, 0x1A5096):
            self.calls.append(('retail', address))
            self.uc.emu_stop(); return
        if address not in (0x1A4170, 0x1ADF90, 0x214B90): return
        esp = self.uc.reg_read(x86.UC_X86_REG_ESP)
        ecx, edx = (self.uc.reg_read(r) for r in (x86.UC_X86_REG_ECX, x86.UC_X86_REG_EDX))
        if address == 0x214B90:
            self.calls.append(('transition', ecx, edx)); cleanup = 0
        else:
            args = tuple(self.get(esp+4+i*4) for i in range(4 if address == 0x1A4170 else 8))
            target = args[0] if address == 0x1A4170 else edx
            vector = struct.unpack('<4f', self.uc.mem_read(target, 16))
            self.calls.append(('steer' if address == 0x1A4170 else 'pursue', vector, ecx, edx, args))
            cleanup = 16 if address == 0x1A4170 else 32
        ret = self.get(esp)
        self.uc.reg_write(x86.UC_X86_REG_ESP, esp + 4 + cleanup)
        self.uc.reg_write(x86.UC_X86_REG_EIP, ret)
    def run(self, va=0x1A5790, *, stop_at=None, count=10000, args=(), **registers):
        self.stop_at, self.calls, self.hits, self.writes = stop_at, [], [], []
        values = dict(ESP=self.STACK, ECX=self.P, EDX=0x2345, EBX=0x3456, ESI=0x4567, EDI=0x5678, EBP=0x6789, EAX=0x789A, EFLAGS=0x202)
        values.update({k.upper(): v for k, v in registers.items()})
        for name, value in values.items(): self.uc.reg_write(getattr(x86, 'UC_X86_REG_'+name), value)
        for i, arg in enumerate((self.STOP, *args)): self.u32(self.STACK+i*4, arg)
        self.uc.emu_start(va, self.STOP, timeout=2_000_000, count=count)
        at = self.uc.reg_read(x86.UC_X86_REG_EIP)
        if at not in (self.STOP, stop_at, 0x1A5796, 0x1A5096):
            raise AssertionError(f'instruction budget exhausted at {at:#x} after {len(self.hits)} instructions')
        if at == self.STOP and self.uc.reg_read(x86.UC_X86_REG_ESP) != self.STACK+4+len(args)*4:
            raise AssertionError('wrapper/retail ABI stack imbalance')
        return at
    def snap(self):
        self.run(0xB6FB3, stop_at=0xB6FBD)
    def command(self):
        self.run(0x18ADA0, edx=12)
    def load_book(self, resource, index=0):
        self.uc.mem_write(self.SOURCE, resource[32:])
        self.run(0x161E30, ecx=self.SOURCE, edx=index, count=60000)
        return spy.BOOK_BASES[index]


@unittest.skipUnless(XBE.is_file() and uc is not None, 'pinned USA retail extraction and Unicorn required for instruction proofs')
class InstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('XBE is not pinned USA retail evidence')
        cls.payload = spy.apply(cls.retail)[0]
    def machine(self, **kwargs): return Machine(self.payload, **kwargs)

    def test_snap_captures_before_delayed_callback_and_replays_cmp_flags(self):
        m = self.machine()
        m.qb(x=-7); m.snap()
        self.assertEqual(m.get(m.state_va), m.QB)
        self.assertAlmostEqual(m.readf(m.state_va+4), -7*91.44, places=3)
        m.qb(x=-3.9); m.command(); m.run()
        self.assertEqual((m.mode(), m.calls[0][0]), (2, 'pursue'))
        for flags in (0x202, 0x247, 0xA93):
            m.run(0xB6FB3, stop_at=0xB6FBD, eflags=flags)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EFLAGS), flags)
            self.assertEqual(m.get(0xE602B8), 14)
            self.assertIsNone(m.slot())

    def test_22_records_are_distinct_and_overflow_uses_retail(self):
        m = self.machine()
        players = [0x3050000+i*0x2000 for i in range(23)]
        slots = []
        for p in players[:22]:
            m.player(p, m.DEF)
            m.run(0x18ADA0, ecx=p, edx=12)
            m.run(ecx=p)
            self.assertEqual(m.calls[0][0], 'steer')
            self.assertEqual(m.get(p+0xE40), m.QB)
            self.assertIsNotNone(m.slot(p))
            slots.append(m.slot(p))
        self.assertEqual(len(set(slots)), 22)
        m.player(players[22], m.DEF)
        m.run(0x18ADA0, ecx=players[22], edx=12)
        before = bytes(m.uc.mem_read(m.state_va, 768))
        m.run(ecx=players[22])
        self.assertEqual(m.calls[0][0], 'retail')
        self.assertEqual(bytes(m.uc.mem_read(m.state_va, 768)), before)
        m.snap()
        self.assertEqual(bytes(m.uc.mem_read(m.state_va+64, 704)), bytes(704))

    def test_exact_release_edges_and_prediction_clamp(self):
        for direction in (-1, 1):
            m = self.machine(direction=direction); m.command(); m.run()
            m.qb(x=3); m.run(); self.assertEqual(m.mode(), 1)
            m.f32(m.GAME+0x18, 0)
            m.f32(m.QB+0x438, -91.44*direction)
            m.f32(m.QB+0x448, direction)
            m.run(); self.assertEqual(m.mode(), 2)
        for sign in (-1,1):
            m = self.machine(); m.qb(x=sign*20); m.snap(); m.command()
            m.qb(x=sign*22, vx=sign*10); m.run()
            self.assertEqual(m.mode(), 1)
            self.assertAlmostEqual(m.calls[0][1][0], sign*2164.08, places=3)

    def test_qb_controller_ratings_and_scramble_parity_do_not_change_decision(self):
        for controller in (-1,0):
            for scramble, agility in ((74,75),(75,75),(75,76)):
                m = self.machine(); m.u32(m.QB+0x100, controller)
                m.uc.mem_write(m.QB+0xD4F, bytes([scramble]))
                m.uc.mem_write(m.QB+0xD37, bytes([agility]))
                m.command(); m.run(); self.assertEqual(m.mode(), 1)
                m.qb(depth=-.5, vz=2); m.run(); self.assertEqual(m.mode(), 2)

    def test_stationary_qb_both_zone_callbacks_both_directions(self):
        for direction in (-1, 1):
            for callback in (0x1A5790, 0x1A5090):
                m = self.machine(direction=direction); m.command(); m.run(callback)
                self.assertEqual(m.mode(), 1)
                self.assertEqual(m.calls[0][0], 'steer')
                self.assertAlmostEqual(m.calls[0][1][0], 0)
                self.assertAlmostEqual(m.calls[0][1][2], 1200+4*91.44*direction, places=3)
                self.assertEqual(m.get(m.P+0xE40), m.QB)
                self.assertNotIn(0x1A1510, m.hits)

    def test_left_right_rollout_prediction_and_wide_release_latch(self):
        for sign in (-1, 1):
            m = self.machine(); m.command(); m.run()
            m.qb(x=sign*2, vx=sign*1); m.run(0x1A5090)
            self.assertEqual(m.mode(), 1)
            self.assertAlmostEqual(m.calls[0][1][0], sign*2.5*91.44, places=3)
            m.qb(x=sign*3.01); m.run()
            self.assertEqual((m.mode(), m.calls[0][0]), (2, 'pursue'))
            m.qb(x=0); m.run(0x1A5090)
            self.assertEqual((m.mode(), m.calls[0][0]), (2, 'pursue'))

    def test_straight_scramble_threshold_forward_motion_both_directions(self):
        for direction in (-1, 1):
            m = self.machine(direction=direction); m.command(); m.run()
            for depth, vz in ((-1.01, 3), (-.9, 0), (-.9, -3)):
                m.qb(depth=depth, vz=vz); m.run(); self.assertEqual(m.mode(), 1)
            m.qb(depth=-.99, vz=3); m.run()
            self.assertEqual((m.mode(), m.calls[0][0]), (2, 'pursue'))
            m.qb(depth=-4, vz=-3); m.run(); self.assertEqual(m.mode(), 2)

    def test_crossing_receiver_and_rb_release_never_take_priority(self):
        m = self.machine(); m.command()
        for target in (m.OTHER, m.RB):
            m.u32(m.P+0xE40, target); m.u32(m.P+0xE48, m.RB)
            m.run()
            self.assertEqual(m.get(m.P+0xE40), m.QB)
            self.assertEqual(m.get(m.P+0xE48), 0)
            self.assertEqual(m.calls[0][0], 'steer')
            self.assertNotIn(0x1A1510, m.hits)

    def test_handoff_turnover_pass_and_dead_ball_exit(self):
        for event in ('handoff', 'turnover', 'pass', 'free', 'dead', 'phase'):
            for pursuit in (False, True):
                m = self.machine(); m.command(); m.run()
                if pursuit: m.qb(x=4); m.run()
                if event == 'handoff': m.u32(m.BALL, m.RB)
                elif event == 'turnover': m.u32(m.RB+0x38, m.DEF); m.u32(m.BALL, m.RB)
                elif event == 'pass': m.u32(m.BALL, m.BALL+0x100); m.u32(m.BALL+0x11C, 2)
                elif event == 'free': m.u32(m.BALL, 0)
                elif event == 'dead': m.u32(m.GAME+0x1C4, 1)
                else: m.u32(0xE602B8, 15)
                m.run()
                self.assertEqual(m.mode(), 3, event)
                self.assertEqual(m.get(m.P+0xE40), 0)
                self.assertEqual(m.get(m.P+0x600+0x420) & 0x20000000, 0)
                self.assertEqual(m.calls[0][0], 'transition' if event in ('handoff','turnover') else 'retail')
                if event in ('handoff','turnover'):
                    self.assertEqual(m.calls[0][1:], (0x2EB330, m.P))
                m.u32(m.BALL, m.QB); m.u32(0xE602B8, 14); m.u32(m.GAME+0x1C4, 0)
                m.command(); m.run(); self.assertEqual(m.mode(), 3)

    def test_repeat_command_native_bit_no_pursuit_restart(self):
        m = self.machine(); m.command(); first = m.get(m.P+0x600+0x420)
        m.command(); self.assertEqual(m.get(m.P+0x600+0x420), first)
        m.run(); m.qb(x=4); m.run()
        slot = bytes(m.uc.mem_read(m.slot(), 32))
        m.command(); self.assertEqual(bytes(m.uc.mem_read(m.slot(), 32)), slot)
        m.qb(x=0); m.run(); self.assertEqual(m.calls[0][0], 'pursue')

    def test_assignment_reset_actual_retail_next_snap_and_substitution(self):
        m = self.machine(); m.command(); m.run(); m.qb(x=4); m.run()
        m.run(0x1B8570, ecx=m.P+0x600+0x41C, edx=1)
        self.assertIsNone(m.slot())
        self.assertEqual(m.get(m.P+0x600+0x420), 0)
        self.assertEqual(m.get(m.P+0x600+0x41C), 0xAAD0E8)
        m.qb(x=-8); m.u32(m.P+0x600+0x41C, m.P+0xF00)
        m.snap(); m.command(); m.run(); self.assertEqual(m.mode(), 1)
        self.assertAlmostEqual(m.readf(m.slot()+16), -8*91.44, places=3)
        m.u32(m.P+0x3C, m.P+0xD10); m.qb(x=4); m.run()
        self.assertEqual(m.mode(), 2)  # same snap baseline survives substitution
        self.assertEqual(m.get(m.slot()+24), m.P+0xD10)

    def test_command_reset_replays_displaced_instructions_and_clears_record(self):
        m = self.machine(); m.command(); m.run()
        m.u32(m.DEF+0x10C, 0x12345678)
        m.run(0x18AEFC, stop_at=0x18AF03, esi=m.DEF+0x100)
        self.assertIsNone(m.slot())
        self.assertEqual(m.get(m.P+0x600+0x420) & 0x20000000, 0)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 5)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EBX), 0x12345678)
        m.run(); self.assertEqual(m.calls[0][0], 'retail')

    def test_user_takeover_non_qb_and_bad_float_leave_spy(self):
        for kind in ('controller','lock','roster','nan','infinity','offense','cached_qb','line_nan','direction_nan'):
            m = self.machine(); m.command(); m.run()
            if kind == 'controller': m.u32(m.P+0x100, 0)
            elif kind == 'lock': m.u32(m.P+0x600+0x584, 0x20)
            elif kind == 'roster': m.uc.mem_write(m.QB+0xD35, b'\x01')
            elif kind == 'nan': m.f32(m.QB+0x430, float('nan'))
            elif kind == 'infinity': m.f32(m.QB+0x448, float('inf'))
            elif kind == 'offense': m.u32(m.P+0x38, m.OFF)
            elif kind == 'line_nan': m.f32(m.GAME+0x18, float('nan'))
            elif kind == 'direction_nan': m.f32(m.DIR+4, float('nan'))
            else: m.u32(0xBE4F8C, m.RB)
            m.run(); self.assertEqual(m.mode(), 3, kind)

    def test_unflagged_replays_both_prologues_abi_identically(self):
        for callback in (0x1A5790, 0x1A5090):
            actual = self.machine(); expected = Machine(self.retail, patched=False)
            actual.run(callback); expected.run(callback)
            registers = ('EAX','EBX','ECX','EDX','ESI','EDI','EBP','ESP','EFLAGS')
            for register in registers:
                reg = getattr(x86, 'UC_X86_REG_'+register)
                self.assertEqual(actual.uc.reg_read(reg), expected.uc.reg_read(reg), register)
            self.assertEqual(actual.uc.mem_read(actual.STACK-4, 8), expected.uc.mem_read(expected.STACK-4, 8))

    def test_active_abi_x87_sse_preserved_and_writes_only_state_actor_stack(self):
        m = self.machine(); m.command()
        for i in range(8): m.uc.reg_write(getattr(x86, 'UC_X86_REG_XMM'+str(i)), (i+1)*0x123456789ABCDEF123456789ABCDEF)
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0xB7F)
        m.uc.mem_write(m.STOP+0x100, b'\xd9\xeb\xd9\xe8\xc3') # actual fldpi/fld1
        m.run(m.STOP+0x100)
        fpu_before = [m.uc.reg_read(r) for r in (x86.UC_X86_REG_FPCW,x86.UC_X86_REG_FPSW,x86.UC_X86_REG_FPTAG,*[getattr(x86,'UC_X86_REG_FP'+str(i)) for i in range(8)])]
        m.run()
        fpu_after = [m.uc.reg_read(r) for r in (x86.UC_X86_REG_FPCW,x86.UC_X86_REG_FPSW,x86.UC_X86_REG_FPTAG,*[getattr(x86,'UC_X86_REG_FP'+str(i)) for i in range(8)])]
        self.assertEqual(fpu_after, fpu_before)
        for i in range(8): self.assertEqual(m.uc.reg_read(getattr(x86, 'UC_X86_REG_XMM'+str(i))), (i+1)*0x123456789ABCDEF123456789ABCDEF)
        for name,value in (('EBX',0x3456),('ESI',0x4567),('EDI',0x5678),('EBP',0x6789)):
            self.assertEqual(m.uc.reg_read(getattr(x86,'UC_X86_REG_'+name)), value)
        for address,size in m.writes:
            self.assertTrue(m.state_va <= address < m.state_va+768 or m.P <= address < m.P+0x2000
                            or 0x3100000 <= address < 0x3110000, hex(address))

    def test_authored_lookup_through_actual_retail_loader_both_buffers(self):
        raw, compiled = compiled_spy()
        table, _ = spy.compile_intent_table([(compiled.replacement, compiled.report)])
        payload = spy.apply(self.retail, intent_table=table)[0]
        for index in (0,1):
            m = Machine(payload); base = m.load_book(compiled.replacement, index)
            field = base+0x33FC+254*96+8+5*8
            m.u32(m.P+0x600+0x41C, field)
            self.assertEqual(m.get(base+0x60), base+0x33FC)
            m.run(); self.assertEqual((m.mode(), m.calls[0][0]), (1,'steer'))
            # Same name/slot but ordinary book, wrong script or slot never opts in.
            for change in ('node','name','book','slot'):
                m = Machine(payload); base = m.load_book(compiled.replacement, index)
                m.u32(m.P+0x600+0x41C, field)
                if change == 'node': m.u32(m.get(field+4)+12, 0)
                elif change == 'name': m.uc.mem_write(m.get(base+0x33FC+254*96), b'Z\0')
                elif change == 'book': m.uc.mem_write(m.get(base+0x30), b'Z\0')
                else: m.u32(m.P+0x600+0x41C, field+8)
                m.run(); self.assertEqual(m.calls[0][0], 'retail', change)


if __name__ == '__main__': unittest.main()
