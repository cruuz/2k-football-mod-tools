"""Bounded native fixtures for the b776 CPU AI owners (cpu_qb_reads, db_ball_play). No game boot.

* ``OpenMachine`` runs the real openness function 0x199F40 for one receiver point against
  constructed defenders (zone spots, man assignments, positions and velocities are inputs).
* ``ReadsMachine`` runs the owner's stamp / pick / hold caves with the real native picker
  0x1985E0 and the real rating getter and curve interpolator; target rows are inputs.
* ``BallFrame`` uses the native zone/man initializers, release 0x1CFA40, event queue
  0x212CB0, dispatcher and behavior 37 init 0x2E95F0, then the reaction task 0x2E7240 with
  native steering and locomotion (tests/nfl2k5_deep_zone_frame.py); the ball path, receiver
  path and catch point are supplied inputs.
Every number is an offline instruction result for the stated inputs, not a played game.
"""
from __future__ import annotations

import math
import random
import struct

from tests.mod_editor.test_nfl2k5_qb_spy_unicorn import Machine as SpyMachine, uc, x86
from tests.nfl2k5_cpu_money_downs_native import Machine as MoneyMachine

YD = 91.44


def bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def seed_rng(m, seed):
    gen = random.Random(seed)
    put = m.u32 if hasattr(m, "u32") else m.put
    put(0xE5FCA0, 54)
    put(0xE5FCA4, 23)
    for index in range(110):
        put(0xE5FCA8 + index * 4, gen.getrandbits(32))


class OpenMachine(SpyMachine):
    """Receiver ``RB`` against up to four defenders; returns the native openness score."""

    def __init__(self, payload, *, direction=1):
        super().__init__(payload, patched=False, direction=direction)
        self.defs = []
        self.arrivals = []
        self.u32(self.OFF, self.DEF)
        self.u32(self.DEF, self.OFF)
        self.player(self.RB, self.OFF)
        self.u32(self.BALL + 0x14, self.BALL + 0x100)
        seed_rng(self, 1)
        self.uc.hook_add(uc.UC_HOOK_CODE, self._arrival, begin=0x19A5F2, end=0x19A5F2)

    def _arrival(self, u, _a, _s, _d):
        # Ball time minus this defender's arrival time, the native curve argument at 0x19A5F2.
        self.arrivals.append(struct.unpack("<f", u.mem_read(u.reg_read(x86.UC_X86_REG_ESP), 4))[0])

    def place(self, p, x, depth, vx=0.0, vz=0.0):
        d = self.direction
        for off, value in ((0x30, x * YD), (0x38, 1200 + depth * YD * d), (0x40, vx * YD), (0x48, vz * YD * d)):
            self.f32(p + 0x400 + off, value)

    def defender(self, *, role, x, depth, vx=0.0, vz=0.0, coverage=0.8, man=0, man2=0, spot=None,
                 position=18, speed=1.0):
        p = self.P if not self.defs else self.SOURCE + 0x8000 + len(self.defs) * 0x1000
        if self.defs:
            self.player(p, self.DEF)
        for off, value in ((0x48, 0), (0x34, 0), (0xF04, p + 0xF40), (0x600 + 0x584, 0),
                           (0xE00 + 0x40, man), (0xE00 + 0x48, man2)):
            self.u32(p + off, value)
        self.uc.mem_write(p + 0x2C, bytes([position]))
        self.uc.mem_write(p + 0xF40, bytes([role]))
        self.uc.mem_write(p + 0x600 + 0x450, b"\0")
        self.f32(p + 0x200 + 0x190, coverage)
        self.f32(p + 0x200 + 0x1B4, speed)
        if spot is not None:
            self.uc.mem_write(p + 0xE20, struct.pack("<4f", spot[0] * YD, 0, 1200 + spot[1] * YD * self.direction, 1))
        self.place(p, x, depth, vx, vz)
        self.u32((self.defs[-1] + 0x34) if self.defs else (self.DEF + 4), p)
        self.defs.append(p)
        return p

    def openness(self, point, *, tb=1.0, tr=0.35, seed=1):
        d = self.direction
        seed_rng(self, seed)
        self.uc.mem_write(self.GAME + 0x900, struct.pack("<4f", point[0] * YD, 0, 1200 + point[1] * YD * d, 1))
        self.uc.mem_write(self.BALL + 0x100, struct.pack("<4f", 0, 100, 1200 - 5 * YD * d, 1))
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.arrivals = []
        # Constant trampoline code (Unicorn may keep a translated block): the arguments live in memory.
        tramp, args = self.SOURCE + 0x1D000, self.SOURCE + 0x1F100
        self.uc.mem_write(args, struct.pack("<5I", self.RB, self.GAME + 0x900, bits(tr), bits(tb), 0))
        code = b"".join(b"\xff\x35" + struct.pack("<I", args + 4 * i) for i in (4, 3, 2, 1, 0))
        code += b"\xe8" + struct.pack("<i", 0x199F40 - (tramp + len(code) + 5))
        code += b"\xd9\x1d" + struct.pack("<I", self.SOURCE + 0x1F000) + b"\xc3"
        self.uc.mem_write(tramp, code)
        self.run(tramp, count=200000)
        return self.readf(self.SOURCE + 0x1F000)

    def curve(self, table_va, x):
        """Native interpolator 0x1B0AE0 on a retail curve table (count at table_va)."""
        tramp, args = self.SOURCE + 0x1C000, self.SOURCE + 0x1F200
        self.uc.mem_write(args, struct.pack("<II", bits(x), table_va))
        code = b"\xff\x35" + struct.pack("<I", args)                  # push x
        code += b"\x8b\x0d" + struct.pack("<I", args + 4)              # ecx = table
        code += b"\x8b\x11\x83\xc1\x04"                               # edx = count; ecx = first point
        code += b"\xe8" + struct.pack("<i", 0x1B0AE0 - (tramp + len(code) + 5))
        code += b"\xd9\x1d" + struct.pack("<I", self.SOURCE + 0x1F004) + b"\xc3"
        self.uc.mem_write(tramp, code)
        self.run(tramp, count=20000)
        return self.readf(self.SOURCE + 0x1F004)


class ReadsMachine(MoneyMachine):
    """The owner's caves around the real picker. ``rows`` are (actor, scores[4]) inputs."""
    CLOCK = MoneyMachine.GAME + 0x700
    STATE_KEYS = dict(LAST=0x00, ABORTS=0x04, THR=0x08, COMMITTED=0x0C, COMMIT_CLOCK=0x10, AGE=0x14,
                      VALID=0x18, SAVED=0x1C, STAMPS=0x20, KEEP=0x70)

    def __init__(self, payload):
        from mod_editor.core import nfl2k5_cpu_qb_reads as reads, nfl2k5_cpu_qb_reads_code as assembly
        super().__init__(payload)
        self.u32(0xE6029C, self.CLOCK)
        self.set_clock(1.0)
        self.labels = assembly.LABELS
        owned = reads.allocations(payload) if reads.read_settings(payload).get("recheck") else None
        self.code = owned["code"]["va"] if owned else None
        self.state = owned["data"]["va"] if owned else None
        self.task = self.QB + 0xE00
        self.actors = []
        self.stops = []
        for va in (0x19BC78, 0x19BF19):
            self.uc.hook_add(uc.UC_HOOK_CODE, self._stop, begin=va, end=va)
        # The roster attribute getter is an input: Pass Read Coverage for the QB (0x17B010, ret 4).
        self.rating_stub = self.SOURCE + 0x1E800
        self.uc.mem_write(self.rating_stub, b"\xd9\x05" + struct.pack("<I", self.rating_stub + 0x10) + b"\xc2\x04\x00")
        self.set_read_coverage(0.85)
        self.rating_calls = []
        self.uc.hook_add(uc.UC_HOOK_CODE, self._rating, begin=0x17B010, end=0x17B010)

    def set_read_coverage(self, value):
        self.f32(self.rating_stub + 0x10, value)

    def _rating(self, u, _a, _s, _d):
        self.rating_calls.append((u.reg_read(x86.UC_X86_REG_ECX), u.reg_read(x86.UC_X86_REG_EDX)))
        u.reg_write(x86.UC_X86_REG_EIP, self.rating_stub)

    def _stop(self, u, address, _s, _d):
        self.stops.append(address)
        u.emu_stop()

    def set_clock(self, t):
        self.f32(self.CLOCK + 0x10, t)

    def field(self, name):
        return self.STATE_KEYS[name]

    def stamp_value(self, row, point):
        return self.readf(self.state + 0x20 + 4 * (row * 4 + point))

    def rows(self, candidates, *, distance=10, down=1, direction=1, current=0):
        """candidates: dict(scores=[4 floats], yards=depth) per receiver row."""
        self.configure(down=down, distance=distance, direction=direction)
        self.u32(self.QB + 0x100, -1)
        los = self.readf(self.GAME + 0x18)
        self.u32(0xBE480C, len(candidates))
        self.u32(0xBE4810, current)
        self.uc.mem_write(0xBE4820, bytes(0xA0 * 5))
        self.actors = []
        for index, candidate in enumerate(candidates):
            actor = self.RB + index * 0x2000
            self.player(actor, self.OFF)
            self.u32(actor + 0xD30, actor + 0xD80)
            self.u32(actor + 0xDA0, 0)
            self.uc.mem_write(0xAA4498, b"\0")
            row = 0xBE4820 + index * 0xA0
            self.u32(row, actor)
            self.u32(row + 8, 1)
            self.u32(row + 0x10, 1)
            for point, score in enumerate(candidate["scores"]):
                at = row + 0x34 + point * 0x20
                self.f32(at, score)
                self.f32(at - 12, los + candidate.get("yards", 8) * YD * self.direction)
                self.f32(at - 4, candidate.get("time", 0.8))
            self.actors.append(actor)

    def snapshot(self):
        return bytes(self.uc.mem_read(0xBE4820, 0xA0 * 5))

    def native_pick(self, threshold):
        """The retail picker alone (what 0x19BD8C calls on a retail XBE)."""
        args = (self.GAME + 0x800, self.GAME + 0x804, bits(threshold), self.GAME + 0x808)
        self.u32(self.GAME + 0x800, 0)
        self.run(0x1985E0, args=args, count=20000)
        return self._chosen()

    def _chosen(self):
        row = self.get(self.GAME + 0x800)
        return None if row == 0 else (row - 0xBE4820) // 0xA0

    def stamp(self, row, point, t):
        self.set_clock(t)
        self.run(self.code + self.labels["stamp"], stop_at=0x19A7E0, eax=row, edx=point, ecx=self.QB, count=4000)
        return [self.uc.reg_read(r) for r in (x86.UC_X86_REG_EAX, x86.UC_X86_REG_ECX, x86.UC_X86_REG_EDX)]

    def pick(self, threshold, t):
        self.set_clock(t)
        args = (self.GAME + 0x800, self.GAME + 0x804, bits(threshold), self.GAME + 0x808)
        self.u32(self.GAME + 0x800, 0)
        self.run(self.code + self.labels["pick"], args=args, edi=self.QB, ebx=self.task, count=40000)
        return self._chosen()

    def commit(self, row, *, timer=0.3):
        self.u32(self.task + 0x40, self.actors[row])
        self.f32(self.task + 0x60, timer)

    def hold(self, t, *, committed_local=None):
        """Enter the cave as the taken native jne does; returns 'pick' (abort) or 'release'."""
        self.set_clock(t)
        self.stops = []
        self.u32(self.STACK + 0x18, self.get(self.task + 0x40) if committed_local is None else committed_local)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        values = dict(ESP=self.STACK, EDI=self.QB, EBX=self.task, ESI=0x4567, EBP=0x6789, EAX=0x789A, ECX=0x1111,
                      EDX=0x2222, EFLAGS=0x246)
        for name, value in values.items():
            self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)
        self.u32(self.STACK, self.STOP)
        self.uc.emu_start(self.code + self.labels["hold"], self.STOP, timeout=2_000_000, count=40000)
        at = self.uc.reg_read(x86.UC_X86_REG_EIP)
        if not self.stops or at != self.stops[-1]:
            raise AssertionError(f"hold cave did not reach a native continuation (at {at:#x})")
        regs = {name: self.uc.reg_read(getattr(x86, "UC_X86_REG_" + name)) for name in values}
        if {k: v for k, v in regs.items() if k != "EFLAGS"} != {k: v for k, v in values.items() if k != "EFLAGS"}:
            raise AssertionError(f"hold cave changed registers: {regs}")
        if (regs["EFLAGS"] ^ values["EFLAGS"]) & 0x8D5:
            raise AssertionError("hold cave changed the native branch flags")
        return {0x19BC78: "pick", 0x19BF19: "release"}[at]


def ball_frame_class():
    """Late import: the deep-zone frame needs the private kickoff skeleton fixtures."""
    from tests.nfl2k5_deep_zone_frame import DeepFrame

    class BallFrame(DeepFrame):
        """A man (or zone) defender through the real release, event dispatch and behavior 37."""

        def __init__(self, payload, node, *, coverage=0.5, seed=0x600000, direction=1, depth=6):
            super().__init__(payload, direction=direction, depth=depth)
            self.component(0x1B85A0)                   # native behavior table 0xBE5110
            g = self.gameplay
            self.f32(self.get(self.p + 0x10) + 0x190, coverage)
            self.uc.mem_write(g + 0x3E8, b"\x30" * 0x31)
            self.uc.mem_write(0xBE4C10, bytes(0xF0))
            self.put(0xBE4C10, self.target)            # receiver registry row (formation scan not run)
            self.command(node)
            self.component(self.get(0xBE5110 + node.op * 4), ecx=self.p)
            self.task = self.get(g + 0x310)
            seed_rng(self, seed)
            self.inits = []
            self.uc.hook_add(uni_code(), lambda u, a, s, d: self.inits.append(a), begin=0x2E95F0, end=0x2E95F0)

        def release(self, catch=None, receiver=None):
            """Real release to ``receiver``; ``catch`` (x, z) in cm replaces the computed catch point."""
            self.component(0x1CFA40, ecx=receiver or self.target)
            if catch is not None:
                self.f32(0xBF0DF0, catch[0]); self.f32(0xBF0DF8, catch[1]); self.put(0xBF0E08, 1)
            self.put(self.gameplay + 0x3E4, 14)
            for frame in range(1, 31):
                self.f32(0xB71D00, frame / 60); self.put(0xB71D10, frame + 1)
                self.component(0x212CB0, ecx=self.p)
                if self.get(self.get(self.gameplay + 0x310)) == 0x2E7240:
                    break
            self.task = self.get(self.gameplay + 0x310)
            return self.get(self.task) == 0x2E7240

        def point(self):
            return [self.readf(self.task + 0x20 + 4 * i) for i in range(4)]

    return BallFrame


def uni_code():
    from tests.mod_editor.test_nfl2k5_dynamic_kickoff import uni
    return uni.UC_HOOK_CODE
