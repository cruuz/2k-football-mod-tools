"""Bounded CPU execution of the actual XBE paths, with GPU/service boundaries stubbed.

The gate, entity-to-controller queue, queue decoder, model-selection routine,
new tag walk, material copy, vertex arithmetic and NV2A inline vertex writer
all execute actual machine code. Stubs supply models/graphics context, coach
visibility, off-screen projection, animation angle/status and replay recording.
This proves submissions, not rasterization or an emulator play session.
"""
from __future__ import annotations

import struct
from mod_editor.core import nfl2k5_player_star as ps
from mod_editor.core.nfl2k5_bump_strength import _sections
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                              UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
                              UC_X86_REG_EIP, UC_X86_REG_FPCW)

STOP = 0x03000000
STACK = 0x02F00004  # deliberately unaligned entry; runtime must align its material
HEAP = 0x02000000
ENTITIES = 0x00B3EF60
MODEL = HEAP + 0x1000
POWER_MODEL = HEAP + 0x2000
MATERIAL = HEAP + 0x3000
POWER_MATERIAL = HEAP + 0x4000
INSTANCE = HEAP + 0x5000
CONTEXT = HEAP + 0x6000
PUSH_BUFFER = HEAP + 0x10000


class Machine:
    def __init__(self, payload: bytes, *, coach=False, coach_visible=True, offscreen=False):
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1000000)
        for s in _sections(payload):
            self.uc.mem_write(s.virtual_address, payload[s.raw_offset:s.raw_offset+s.raw_size])
        self.uc.mem_map(HEAP, 0x1100000)
        self.uc.mem_protect(0x11000, 0x40F000, UC_PROT_READ | UC_PROT_EXEC)
        self.uc.reg_write(UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(UC_X86_REG_ESP, STACK)
        self.coach = coach
        self.coach_visible = coach_visible
        self.offscreen = offscreen
        self.models = []
        self.strips = []
        self.trace = []
        self._pending = None
        self.set32(0xE5FC50, 1)
        self.set32(0xE5FF80, 4)
        self.set32(0xE602B8, 0xC)
        self.set32(ps.DRAW_READY_VA, 1)
        self.set32(ps.DRAW_VISIBLE_VA, 1)
        self.set32(0xBA28A4, MODEL)
        self.set32(0xBA28A8, POWER_MODEL)
        self.set32(ps.MATERIAL_VA, MATERIAL)
        self.set32(0xBA28B0, POWER_MATERIAL)
        # Same registered material group/defaults as the real controller scene.
        self.uc.mem_write(MATERIAL, bytes(self.uc.mem_read(0x4E60C0, 128)))
        self.set32(MATERIAL + 0x18, 0xFF0B6AAB)
        self.set32(MATERIAL + 0x30, HEAP + 0x7000)
        self.set32(MATERIAL + 0x60, 0x245F0008)
        self.set32(MATERIAL + 0x70, 0x02060203)
        self.uc.hook_add(UC_HOOK_CODE, self._hook)

    def set32(self, address, value):
        self.uc.mem_write(address, struct.pack('<I', value & 0xFFFFFFFF))

    def u32(self, address):
        return struct.unpack('<I', self.uc.mem_read(address, 4))[0]

    def f32(self, address):
        return struct.unpack('<f', self.uc.mem_read(address, 4))[0]

    def ret(self, value=0, cleanup=0):
        sp = self.uc.reg_read(UC_X86_REG_ESP)
        self.uc.reg_write(UC_X86_REG_EAX, value)
        self.uc.reg_write(UC_X86_REG_ESP, sp + 4 + cleanup)
        self.uc.reg_write(UC_X86_REG_EIP, self.u32(sp))

    def _hook(self, uc, address, size, _):
        if address in (ps.GATE_VA, 0xF9030, 0xF9320, 0xF8880, *ps.SYMBOLS.values()):
            self.trace.append(address)
        if address == 0x627C0:
            self.ret(int(self.coach))
        elif address == 0x7D930:
            self.ret(int(self.coach_visible))
        elif address == 0xF82C0:
            self.ret(int(self.offscreen), 16)
        elif address in (0x1A8890, 0x283FB0):
            self.ret()
        elif address == 0x84AB0:
            self.ret(0, 8)  # recorder consumes the packet, no persistent file/device
        elif address == 0x21970:
            self.ret(INSTANCE)
        elif address == 0x37EB0:
            self.uc.mem_write(INSTANCE, struct.pack('<16f', *[1.0 if i % 5 == 0 else 0.0 for i in range(16)]))
            self.ret()
        elif address == 0x21860:
            self.models.append({'model': uc.reg_read(UC_X86_REG_ECX),
                                'x': self.f32(INSTANCE + 0x30), 'z': self.f32(INSTANCE + 0x38),
                                'color': self.u32(MATERIAL + 0x18)})
            self.ret()
        elif address == 0x2D2A0:
            sp = uc.reg_read(UC_X86_REG_ESP)
            material = self.u32(sp + 8)
            self._pending = {'primitive': self.u32(sp + 4), 'transform': self.u32(sp + 12),
                             'vertex_mode': uc.reg_read(UC_X86_REG_ECX),
                             'material': bytes(uc.mem_read(material, 128)), 'vertices': []}
            self.set32(CONTEXT + 0x318, 4)
            self.set32(0xA6B274, CONTEXT)
            for va, value in ((0xA6B27C, PUSH_BUFFER), (0xA6B280, PUSH_BUFFER),
                              (0xA6B284, 0), (0xA6B288, 0), (0xA6B28C, 1),
                              (0xA6B290, 0), (0xA6B2AC, 0xFFFFFFFF), (0xA6B2A0, 0), (0xA6B2A4, 0)):
                self.set32(va, value)
            self.ret(0, 12)
        elif address == 0x2CA00 and self._pending is not None:
            count = self.u32(0xA6B284)
            raw = bytes(uc.mem_read(PUSH_BUFFER, count * 28))
            for i in range(count):
                x, y, z, marker, color, u, v = struct.unpack_from('<3f4I', raw, i * 28)
                self._pending['vertices'].append((x, y, z, color))
            self.strips.append(self._pending)
            self._pending = None
            # Execute the actual end/flush too; its RDTSC timing helper is pure.

    def entities(self, tags, *, controlled=(), mode=4, inactive=(), missing_record=(), missing_body=(), cycle=False):
        tags = list(tags)
        if len(tags) > ps.ENTITY_LIMIT:
            raise ValueError('the retail entity array has 22 slots')
        self.set32(0xE5FF80, mode)
        self.set32(ps.ENTITY_LIST_VA, ENTITIES if tags else 0)
        self.centers = []
        for i, tag in enumerate(tags):
            e = ENTITIES + 0x50 * i
            body = HEAP + 0x30000 + 0x1000 * i
            record = 0xB30C4C + 0x54 * i
            controller = HEAP + 0x60000 + 0x100 * i
            stats = controller + 0x40
            self.set32(e, 0)
            self.set32(e+4, body if i not in missing_body else 0)
            self.set32(e+0xC, controller)
            self.set32(controller, 0 if i in controlled else -1)
            self.set32(e+0x10, stats)
            self.uc.mem_write(e+0x2C, b'\x06')
            self.set32(e+0x30, e+0x50 if i+1 < len(tags) else (ENTITIES if cycle else 0))
            self.set32(e+0x38, HEAP + 0x80000)  # pure is-user-body predicate misses
            self.set32(e+0x3C, record if i not in missing_record else 0)
            self.set32(e+0x48, int(i in inactive))
            self.uc.mem_write(record+0x53, bytes([int(tag)]))
            self.set32(record+0x20, (10+i) << 3)
            x, z = -250.25 + i * 160, -1500.5 + i * 170
            self.centers.append((x+2, z+3))
            self.uc.mem_write(body+0x130, struct.pack('<3f', x, 0, z))
            self.uc.mem_write(body+0x230, struct.pack('<3f', x+4, 0, z+6))
        return [ENTITIES+0x50*i for i in range(len(tags))]

    def run(self, entry, *, ecx=0, edx=0, eax=0, args=(), budget=100000):
        self.uc.reg_write(UC_X86_REG_ECX, ecx)
        self.uc.reg_write(UC_X86_REG_EDX, edx)
        self.uc.reg_write(UC_X86_REG_EAX, eax)
        self.uc.reg_write(UC_X86_REG_ESP, STACK)
        self.uc.mem_write(STACK, struct.pack('<'+'I'*(1+len(args)), STOP, *args))
        nonvolatile = (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)
        saved = [self.uc.reg_read(reg) for reg in nonvolatile]
        self.uc.emu_start(entry, STOP, count=budget)
        if self.uc.reg_read(UC_X86_REG_EIP) != STOP:
            raise AssertionError(f'execution budget exhausted at {self.uc.reg_read(UC_X86_REG_EIP):#x}')
        if saved != [self.uc.reg_read(reg) for reg in nonvolatile]:
            raise AssertionError('callee-saved registers changed')
        if self.uc.reg_read(UC_X86_REG_ESP) != STACK+4+len(args)*4:
            raise AssertionError('unbalanced call stack')
        return self.uc.reg_read(UC_X86_REG_EAX)

    def frame(self, *, build=True):
        if build:
            self.run(0xF9030, args=(0x3C888889,))  # 1/60 s
        displacement = struct.unpack('<i', self.uc.mem_read(ps.DRAW_CALL_VA+1, 4))[0]
        self.run(ps.DRAW_CALL_VA+5+displacement)
        return self.strips
