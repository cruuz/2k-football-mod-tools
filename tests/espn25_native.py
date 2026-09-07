"""Bounded native x86 harness. No console, graphics, sound, or game emulation.

Only explicit archive/controller/presentation boundaries are substituted. Native
ROST imports, SITU relocation, formatting, setup writes and completion code run.
"""
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn import x86_const as regs
from espn25_fixture import RETAIL
from mod_editor.core import nfl2k5_espn25_scenarios as e

XBE_SHA256 = '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'


class CPU:
    STOP, STACK, MAIN, SITU = 0x27FF000, 0x27F0000, 0x2000000, 0x2100000

    def __init__(self, catalog):
        self.catalog = catalog
        with (RETAIL / 'default.xbe').open('rb') as stream:
            payload = stream.read(16 * 1024 * 1024 + 1)
        assert len(payload) <= 16 * 1024 * 1024 and e.sha(payload) == XBE_SHA256, 'foreign retail XBE'
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1500000)
        self.uc.mem_map(0x2000000, 0x800000)
        image_base = e.u32(payload, 0x104)
        table = e.u32(payload, 0x120) - image_base
        for i in range(e.u32(payload, 0x11C)):
            _, va, virtual_size, offset, size = struct.unpack_from('<5I', payload, table + i * 56)
            assert 0x10000 <= va and va + virtual_size <= 0x1510000 and offset + size <= len(payload)
            self.write(va, payload[offset:offset + size])
        self.stubs, self.events = {}, []
        self.uc.hook_add(UC_HOOK_CODE, self._hook)
        self.write(self.MAIN, catalog.resource(5)[32:])
        self.w(0xB72918, self.MAIN + 64)
        self.run(0xC0500, ecx=self.MAIN + 64)
        self.load_situ(catalog.resource(22)[:32 + 29104])

    def read(self, at, size):
        return bytes(self.uc.mem_read(at, size))

    def write(self, at, raw):
        self.uc.mem_write(at, bytes(raw))

    def r(self, at):
        return struct.unpack('<I', self.read(at, 4))[0]

    def w(self, at, value):
        self.write(at, struct.pack('<I', value & 0xFFFFFFFF))

    def f(self, at):
        return struct.unpack('<f', self.read(at, 4))[0]

    def reg(self, name):
        return self.uc.reg_read(getattr(regs, 'UC_X86_REG_' + name.upper()))

    def text(self, at):
        raw = bytearray()
        for i in range(2048):
            pair = self.read(at + 2 * i, 2)
            if pair == b'\0\0':
                return raw.decode('utf-16le')
            raw.extend(pair)
        raise AssertionError('native string exceeds 2048 characters')

    def ret(self, value=0, pop=0):
        esp = self.reg('esp')
        self.uc.reg_write(regs.UC_X86_REG_EAX, value)
        self.uc.reg_write(regs.UC_X86_REG_ESP, esp + 4 + pop)
        self.uc.reg_write(regs.UC_X86_REG_EIP, self.r(esp))

    def _hook(self, uc, at, size, data):
        if at in self.stubs:
            self.stubs[at]()

    def run(self, at, **registers):
        self.w(self.STACK, self.STOP)
        for name in ('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp'):
            self.uc.reg_write(getattr(regs, 'UC_X86_REG_' + name.upper()), registers.get(name, 0))
        for index, value in enumerate(registers.get('args', ())):
            self.w(self.STACK + 4 + index * 4, value)
        self.uc.reg_write(regs.UC_X86_REG_ESP, self.STACK)
        self.uc.emu_start(at, self.STOP, count=2_000_000)
        assert self.reg('eip') == self.STOP, f'instruction budget exhausted at {self.reg("eip"):x}'
        return self.reg('eax')

    def load_situ(self, wrapped):
        body = wrapped[32:]
        assert len(body) <= 256 * 1024 and e.u32(wrapped, 4) == len(body)
        self.write(self.SITU, body)
        # The resource framework relocates the preamble before this callback.
        self.w(self.SITU + 20, self.SITU + 64)
        self.run(0x165EE0, ecx=self.SITU)
        self.stubs[0x449E0] = lambda: self.ret(self.SITU + 64, 4)
        self.run(0x2CFD00, ecx=0, edx=0)
        del self.stubs[0x449E0]

    def archive_stubs(self):
        by_name = {d['filename']: d['outer'] for d in self.catalog.descriptors}
        def load():
            filename = self.text(self.reg('edx'))
            assert filename in by_name, f'unexpected archive request {filename}'
            index = by_name[filename]
            assert len(self.events) < 100, 'archive event budget'
            self.events.append({'filename': filename, 'outer': index})
            self.write(0x2200000, self.catalog.resource(index)[32:])
            self.ret(1, 16)
        self.stubs.update({0x43F50: load, 0x432D0: lambda: self.ret(1),
                           0x449E0: lambda: self.ret(0x2200040, 4), 0x432F0: lambda: self.ret(1)})

    def select(self, index=0):
        self.archive_stubs()
        self.stubs.update({0xF3210: lambda: self.ret(index), 0x6E390: lambda: self.ret(0),
                           0xE3150: lambda: self.ret(1), 0xF3580: lambda: self.ret(0),
                           0x773F0: lambda: self.ret(0)})
        self.run(0x20CB30, ecx=0x2310000)
        self.run(0x20C5C0, ecx=0x2310000)

    def setup(self):
        for at, target in ((0xE5FC28, 0x2320000), (0xE5FC68, 0x2321000),
                           (0xE6028C, 0x2322000), (0xE602EC, 0x2323000)):
            self.w(at, target)
        # Spatial/model callbacks and clock start/stop are outside scalar setup.
        for at in (0xE9460, 0x10BD60, 0xAF510, 0x61B80, 0x61C70, 0x61C80, 0xE7C50):
            self.stubs[at] = lambda: self.ret(0)
        self.stubs[0x9CBD0] = lambda: self.ret(0, 8)
        self.run(0x10C040)
        return {'home_score': self.r(0x2320000), 'away_score': self.r(0x2321000),
                'home_timeouts': self.r(0x2320004), 'away_timeouts': self.r(0x2321004),
                'quarter': self.r(0xE602C4), 'clock_seconds': self.f(0x2322010),
                'down': self.r(0x2323004), 'ball_cm': self.f(0x2323018),
                'first_down_cm': self.f(0x2323028), 'possession': self.r(0xE60280)}
