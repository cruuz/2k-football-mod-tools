"""Bounded retail x86 movie loader. File I/O, clocks and renderer are host services.

Executes retail list registration, header callbacks, size calculations, failure
cleanup and caller dispatch. Does not run the MPEG decoder, Xbox or emulator.
"""
from collections import deque
import struct
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_my_career_fixture import Machine


class MovieMachine(Machine):
    def __init__(self, payload):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        im = XbeImage(payload)
        self.uc.mem_map(0x10000, 0x1510000-0x10000)
        for s in im.sections:
            if s.raw_size:
                self.uc.mem_write(s.start, im.read(s.start, s.raw_size))
        for va, size in ((self.SAVE, 0x100000), (self.BODIES, 0x20000),
                         (self.STACK & ~65535, 65536), (self.STOP, 4096)):
            self.uc.mem_map(va, size)
        self.labels, self.stubs = {}, []
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.files, self.pending, self.reads, self.opens, self.allocations_seen = {}, deque(), [], [], []
        self.closed = []
        self.put(0xaf5884, 0xaf57c8)
        self.put(0xaf5880, 0xaf57c8)
        self.put(0xaf58c0, 1)  # clock denominator, frozen time avoids hardware work
        self.stub(0x3cae50, lambda: (self.reg('EDX', 0), self.ret()))
        self.stub(0x432d0, lambda: self.ret())
        self.stub(0x38fb0, lambda: self.ret(self.BODIES))
        self.stub(0x48ef0, self.open_file)
        self.stub(0x48ff0, self.read_file)
        self.stub(0x48fc0, lambda: (self.closed.append(self.reg('ECX')), self.ret(1)))
        self.stub(0x48700, self.allocation)
        self.stub(0x38cd0, self.pump)
        self.trampoline = self.STOP + 128
        self.uc.mem_write(self.trampoline, b'\xe8' + struct.pack('<i', 0x3cd120-self.trampoline-5)+b'\xc3')

    def string(self, va):
        result = bytearray()
        for at in range(0, 1024, 2):
            b = bytes(self.uc.mem_read(va+at, 2))
            if b == b'\0\0':
                return result.decode('utf-16le')
            result.extend(b)
        raise AssertionError('unterminated movie name')

    def open_file(self):
        name = self.string(self.reg('EDX'))
        self.opens.append(name)
        self.active_file = self.files.get(name)
        self.ret(int(self.active_file is not None))

    def read_file(self):
        sp = self.reg('ESP')
        lo, hi, n, callback, user = (self.get(sp+4*i) for i in range(1,6))
        at = lo + (hi << 32)
        context, destination = self.reg('ECX'), self.reg('EDX')
        self.reads.append((at,n))
        data = self.active_file(at,n) if self.active_file else b''
        if len(data) != n:
            self.ret(0, pop=20)
            return
        self.uc.mem_write(destination, data)
        self.put(context, (at+n) & 0xffffffff)
        self.put(context+4, (at+n) >> 32)
        self.put(context+0x18, n)
        self.put(context+0x20, 0)
        self.pending.append((callback, user, context))
        self.ret(1, pop=20)

    def pump(self):
        if self.pending:
            callback, user, context = self.pending.popleft()
            sp = self.reg('ESP')
            self.put(sp-4, user)
            self.put(sp-8, self.trampoline)
            self.reg('ESP',sp-8)
            self.reg('EDX',context)
            self.reg('EIP',callback)
        else:
            self.reg('EIP',0x3cd120)

    def allocation(self):
        self.allocations_seen.append(self.reg('EDX'))
        # Return allocation failure deliberately: executes native cleanup without
        # entering decoder/GPU. The requested size, not host RSS, is measured.
        self.ret(0)
