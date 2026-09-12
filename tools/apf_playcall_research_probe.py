"""Read-only beta-67 research instrument; never writes an image or patch.

PPC32 adapters implement Xenon stack spills, extsw/fcfid, low-word rldicl
and cmpdi, and the two position-vector transports. Every adapted PC is
recorded. RNG and the optional kicker-range boundary are explicit inputs,
never represented as native callee execution. No category/formation/play
selection callee is replaced by the instrument.
"""
from __future__ import annotations

import hashlib
import struct
from collections import deque

from mod_editor.core.apf2k8_playcall_patch import IMAGE_BASE, PROFILES

BOOK, MASTER, MANAGER, STATE, TEAM = 0x100000, 0x200000, 0x300000, 0x310000, 0x320000
STACK, STOP = 0x4FF000, 0x400000
GAME, HISTORY, OUTPUT = 0x851A2780, 0x851595D0, 0x380000

# Only the covered function families. This is not a general TU relocator.
def code_address(base_address, updated=False):
    if not updated:
        return base_address
    for start, end, delta in (
        (0x84815000, 0x84864700, 0xCA0),
        (0x84864B48, 0x84867938, 0xCD0),
        (0x84867BF8, 0x8486D200, 0xD00),
        (0x84928000, 0x8493E000, 0xEC8),
        (0x849FD000, 0x849FE000, 0xEB8),
        (0x84A3CEC8, 0x84A3CF20, 0xED8),
        (0x84A85000, 0x84BE0000, 0xFD0),
    ):
        if start <= base_address < end:
            return base_address + delta
    raise ValueError(f"No reviewed TU mapping for {base_address:08X}")


class Machine:
    def __init__(self, image: bytes, master: bytes):
        import unicorn as u
        from unicorn import ppc_const as r
        if hashlib.sha256(image).hexdigest() not in {p.sha256 for p in PROFILES}:
            raise ValueError("Expected a pinned BASE or TU 1.1 image")
        self.image, self.u, self.r = image, u, r
        self.updated = hashlib.sha256(image).hexdigest() == PROFILES[1].sha256
        self.cpu = u.Uc(u.UC_ARCH_PPC, u.UC_MODE_32 | u.UC_MODE_BIG_ENDIAN)
        self.cpu.mem_map(IMAGE_BASE, (len(image) + 4095) & ~4095)
        self.cpu.mem_write(IMAGE_BASE, image)
        self.cpu.mem_map(BOOK, 0x400000)
        self.cpu.mem_write(MASTER, master)
        self.cpu.reg_write(r.UC_PPC_REG_MSR, 0x2000)  # enable floating point
        self.trace = deque(maxlen=80)
        self.adapted = set()
        self.visited = set()
        self.boundaries = {}
        self.observers = {}
        self.vector0 = bytes(16)
        self.steps = 0
        self.cpu.hook_add(u.UC_HOOK_CODE, self._step)

    def reg(self, index):
        return self.cpu.reg_read(self.r.UC_PPC_REG_0 + index)

    def setreg(self, index, value):
        self.cpu.reg_write(self.r.UC_PPC_REG_0 + index, value & 0xFFFFFFFF)

    def put(self, address, value):
        self.cpu.mem_write(address, struct.pack(">I", value & 0xFFFFFFFF))

    def get(self, address):
        return int.from_bytes(self.cpu.mem_read(address, 4), "big")

    def putf(self, address, value):
        self.cpu.mem_write(address, struct.pack(">f", value))

    def fpr(self, index):
        bits = self.cpu.reg_read(self.r.UC_PPC_REG_FPR0 + index)
        return struct.unpack(">d", bits.to_bytes(8, "big"))[0]

    def setfpr(self, index, value):
        self.cpu.reg_write(self.r.UC_PPC_REG_FPR0 + index,
                           int.from_bytes(struct.pack(">d", value), "big"))

    def random_boundaries(self, fraction=0.5, integer=1, delta=0):
        def floating(machine):
            machine.setfpr(1, fraction)
            machine.ret(0)
        self.boundaries[0x84B3E858 + delta] = lambda machine: machine.ret(integer)
        self.boundaries[0x84B3E8B8 + delta] = floating

    def va(self, address):
        return code_address(address, self.updated)

    def configure(self, *, down=1, yards=1, goal_yards=1, period=1,
                  clock=900, score=0, timeouts=3, urgency=0, run_share=0.5,
                  fraction=0.5, integer=1):
        """Explicit minimal match state, no roster/player skill objects.

        Period/yard/clock names are research interpretations; their addresses
        and numeric effects are asserted independently in the retail tests.
        """
        delta = 0x30 if self.updated else 0
        game, history = GAME + delta, HISTORY + delta
        self.random_boundaries(fraction, integer, 0xFD0 if self.updated else 0)
        self.boundaries[self.va(0x84861288)] = lambda machine: (
            machine.setfpr(1, 4572.0), machine.ret(0))
        for address, value in (
            (game, MANAGER), (game + 4, 0x360000), (game + 0x6C, STATE),
            (game + 0x34, 4), (game + 0x44, period), (game + 0xC, 0x350000),
            (MANAGER + 0xC, TEAM), (MANAGER + 8, 0x330000),
            (MANAGER, 0x360000), (0x360008, 0x370000),
            (0x33000C, 0x340000), (STATE + 4, down),
            (0x330000, score), (0x330004, timeouts),
            (0x8522C9B8 + delta, MASTER),
            # Native MASTER initializer's type metadata (84A94068/84A877C8).
            (0x8522C9B4 + delta, 0x820FBFC8 + (0x20 if self.updated else 0)),
        ):
            self.put(address, value)
        self.putf(0x340004, 1.0)
        self.putf(0x350010, clock)
        ball = 4572 - goal_yards * 91.44
        self.putf(STATE + 0x18, ball)
        self.putf(STATE + 0x28, ball + yards * 91.44)
        self.putf(TEAM + 0xE4, urgency)
        self.putf(history + 0x67C, run_share)

    def normalize(self, repair_tail=True):
        self.call(self.va(0x84A8C790), BOOK, 0, int(repair_tail), bound=2500000)
        return bytes(self.cpu.mem_read(BOOK, 0x7E20))

    def ret(self, value):
        self.setreg(3, value)
        self.cpu.reg_write(self.r.UC_PPC_REG_PC, self.cpu.reg_read(self.r.UC_PPC_REG_LR))

    def _step(self, cpu, pc, size, data):
        self.steps += 1
        self.trace.append(pc)
        self.visited.add(pc)
        if pc in self.observers:
            self.observers[pc](self)
        if pc in self.boundaries:
            self.boundaries[pc](self)
            return
        word = struct.unpack_from(">I", self.image, pc - IMAGE_BASE)[0]
        op, rt, ra = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        xo = (word >> 1) & 1023
        # Xenon lvx128 v0,0,r9/r10 and ordinary stvx v0. These only
        # transport the two position vectors to a scalar distance helper.
        if word in (0x100048C3, 0x100050C3):
            self.vector0 = bytes(cpu.mem_read(self.reg((word >> 11) & 31) & ~15, 16))
        elif op == 31 and xo == 231 and rt == 0:
            address = ((self.reg(ra) if ra else 0) + self.reg((word >> 11) & 31)) & ~15
            cpu.mem_write(address, self.vector0)
        else:
            address = None
        if word in (0x100048C3, 0x100050C3) or (op == 31 and xo == 231 and rt == 0):
            self.adapted.add(pc)
            cpu.reg_write(self.r.UC_PPC_REG_PC, pc + 4)
            return
        if op == 30 and (word >> 2) & 7 == 0:  # rldicl, low-word operands
            shift = ((word >> 11) & 31) | ((word & 2) << 4)
            mask = ((word >> 6) & 31) | (word & 32)
            value = self.reg(rt)
            value = ((value << shift) | (value >> (64 - shift))) & ((1 << 64) - 1)
            self.setreg(ra, value & ((1 << (64 - mask)) - 1))
            self.adapted.add(pc)
            cpu.reg_write(self.r.UC_PPC_REG_PC, pc + 4)
            return
        if op in (10, 11) and word & (1 << 21):  # cmp[ l ]di on low-word values
            field = (word >> 23) & 7
            value, immediate = self.reg(ra), word & 0xFFFF
            if op == 11 and value & 0x80000000:
                value -= 0x100000000
            if op == 11 and immediate & 0x8000:
                immediate -= 0x10000
            result = 8 if value < immediate else 4 if value > immediate else 2
            shift = (7 - field) * 4
            cr = cpu.reg_read(self.r.UC_PPC_REG_CR)
            cpu.reg_write(self.r.UC_PPC_REG_CR, (cr & ~(15 << shift)) | (result << shift))
            self.adapted.add(pc)
            cpu.reg_write(self.r.UC_PPC_REG_PC, pc + 4)
            return
        if op == 31 and xo == 986:  # extsw; std below carries the signed value
            self.setreg(ra, self.reg(rt))
        elif op == 63 and xo == 846:  # fcfid, absent from the PPC32 engine
            source = (word >> 11) & 31
            bits = cpu.reg_read(self.r.UC_PPC_REG_FPR0 + source)
            integer = bits if bits < (1 << 63) else bits - (1 << 64)
            cpu.reg_write(self.r.UC_PPC_REG_FPR0 + rt,
                          int.from_bytes(struct.pack(">d", float(integer)), "big"))
        else:
            integer = None
        if (op == 31 and xo == 986) or (op == 63 and xo == 846):
            self.adapted.add(pc)
            cpu.reg_write(self.r.UC_PPC_REG_PC, pc + 4)
            return
        if op in (58, 62):
            if ra != 1 or word & 3 not in (0, 1):
                raise AssertionError(f"Non-ABI 64-bit instruction at {pc:08X}")
            displacement = word & 0xFFFC
            if displacement & 0x8000:
                displacement -= 0x10000
            address = (self.reg(ra) + displacement) & 0xFFFFFFFF
            if op == 62:
                value = self.reg(rt)
                if value & 0x80000000:
                    value |= 0xFFFFFFFF00000000
                cpu.mem_write(address, struct.pack(">Q", value))
            else:
                self.setreg(rt, int.from_bytes(cpu.mem_read(address, 8), "big"))
            if word & 1:
                self.setreg(ra, address)
            self.adapted.add(pc)
            cpu.reg_write(self.r.UC_PPC_REG_PC, pc + 4)

    def install(self, book):
        self.cpu.mem_write(BOOK, book.body)
        self.put(BOOK + 0x7E0C, MASTER)
        self.put(0x84F3F808, BOOK)
        self.put(MANAGER + 0x20, BOOK)

    def call(self, address, *args, stop=STOP, bound=200000):
        self.trace.clear()
        self.visited.clear()
        self.setreg(1, STACK)
        self.cpu.reg_write(self.r.UC_PPC_REG_LR, STOP)
        for index, value in enumerate(args, 3):
            self.setreg(index, value)
        try:
            self.cpu.emu_start(address, stop, count=bound)
        except Exception as exc:
            pc = self.cpu.reg_read(self.r.UC_PPC_REG_PC)
            raise AssertionError(f"Native call failed at {pc:08X}; trace="
                                 + ",".join(f"{a:08X}" for a in self.trace)) from exc
        if self.cpu.reg_read(self.r.UC_PPC_REG_PC) != stop:
            raise AssertionError("Native instruction bound exceeded")
        return self.reg(3)
