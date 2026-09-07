"""Bounded retail instruction probes. No game boot, renderer or I/O services.

No native routine is mocked by default. A test must name every substituted
leaf and describe its narrower claim. Synthetic RAM is not a captured game.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256

XBE = (Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
            "/media/noah/Storage/for codex 1.0/extracted")) /
       "ESPN NFL 2K5 (USA)/default.xbe")
HAVE_UC = importlib.util.find_spec("unicorn") is not None


def retail_bytes():
    if not XBE.is_file():
        raise unittest.SkipTest("private USA retail default.xbe is absent")
    with XBE.open("rb") as stream:
        payload = stream.read(16 * 1024**2 + 1)
    if len(payload) > 16 * 1024**2 or hashlib.sha256(payload).hexdigest() != RETAIL_SHA256:
        raise unittest.SkipTest("USA retail executable evidence pin differs")
    return payload


def retail_roster():
    from mod_editor.core import nfl2k5_roster_records as rr
    if not (XBE.parent / "vc_53450030/0").is_file():
        raise unittest.SkipTest("private retail roster archive is absent")
    with rr._outer_image()(XBE.parent) as archive:
        entry = rr._entry(archive)
        if entry.size > 1024**2:
            raise AssertionError("roster resource exceeds 1 MiB")
        body = archive.read(entry.virtual_offset, entry.size)[rr.RESOURCE_HEADER_SIZE:]
    if hashlib.sha256(body).hexdigest() != rr.RETAIL_BODY_SHA256:
        raise unittest.SkipTest("private retail roster evidence pin differs")
    return body


def signed_save():
    from mod_editor.core import nfl2k5_senior_bowl as bowl
    from tests.nfl2k5_senior_bowl_fixture import SAVE_PATHS
    if not SAVE_PATHS[0].is_file() or not SAVE_PATHS[0].with_name("EXTRA").is_file():
        raise unittest.SkipTest("private signed f0 franchise evidence is absent")
    document, _ = bowl.read_franchise(SAVE_PATHS[0])
    payload = bytes(document.body)
    if hashlib.sha256(payload).hexdigest() != "56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8":
        raise unittest.SkipTest("private signed f0 franchise evidence pin differs")
    return payload


def sim_machine(payload, *, seed=12345, trace_writes=False):
    m = Machine(payload, trace_writes=trace_writes)
    m.load_franchise(signed_save())
    m.seed(seed)
    for address, value in ((0xE5FF80, 4), (0xE576A4, 8), (0xE6000C, 5), (0xE60010, 5)):
        m.put(address, value)
    m.call(0x77AE0, ecx=m.team_base)
    m.call(0x77B20, ecx=m.team_base + 500)
    m.call(0x10B280, ecx=m.team_base, edx=m.team_base + 500,
           args=(0, 1, 0, 0, 0, 0), budget=3000000)
    # Native initialization leaves offense unset until the kickoff/setup tick.
    m.call(0x10B250, budget=1000000)
    return m


def read_sim(m):
    from mod_editor.core import nfl2k5_supersim as sim
    return sim.read_snapshot(m.uc.mem_read,
                             lambda side: m.call(0x250DD0, ecx=side, edx=0))


def live_context(m):
    """Synthetic live scalar/clock objects, with native team/depth setup separate."""
    a = m.ARENA + 0x120000
    m.put(0xE5FC20, 0xE5FC60)
    m.put(0xE5FC60, 0xE5FC20)
    m.put(0xE5FC28, a)
    m.put(0xE5FC68, a + 0x100)
    m.put(0xE6028C, a + 0x200)
    m.put(0xE602EC, a + 0x300)
    for va in (0xE60290, 0xE60294, 0xE60298, 0xE602A0):
        m.put(va, a + 0x200)
    return a


class Machine:
    ARENA, STACK, STOP = 0x2000000, 0x3008000, 0x3100000

    def __init__(self, payload, *, trace_writes=True):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1510000 - 0x10000)
        im = XbeImage(payload)
        for section in im.sections:
            if section.raw_size:
                self.uc.mem_write(section.start, im.read(section.start, section.raw_size))
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_map(self.ARENA, 0x200000, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(0x3000000, 0x10000, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(self.STOP, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.leaves = []
        self.write_ranges = set()
        if trace_writes:
            self.uc.hook_add(u.UC_HOOK_MEM_WRITE, self._write)

    def _write(self, uc, access, address, size, value, _):
        if not 0x3000000 <= address < 0x3010000:
            # Page + writer, bounded even for a long native loop.
            self.write_ranges.add((address & ~4095, self.reg("EIP")))

    def reg(self, name, value=None):
        key = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(key)
        self.uc.reg_write(key, value & 0xFFFFFFFF)

    def put(self, address, value):
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, address):
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def f32(self, address, value=None):
        if value is None:
            return struct.unpack("<f", self.uc.mem_read(address, 4))[0]
        self.uc.mem_write(address, struct.pack("<f", value))

    def ret(self, value=0, pop=0):
        sp = self.reg("ESP")
        self.reg("EAX", value)
        self.reg("EIP", self.get(sp))
        self.reg("ESP", sp + 4 + pop)

    def leaf(self, address, action, *, reason):
        if not reason:
            raise ValueError("a substituted leaf requires its evidence boundary")
        self.leaves.append((address, reason))
        return self.uc.hook_add(self.u.UC_HOOK_CODE, lambda *_: action(), begin=address, end=address)

    def call(self, address, *, ecx=0, edx=0, eax=0, args=(), stop=None,
             budget=500000, ebx=0x11111111, esi=0x22222222, edi=0x33333333):
        for name, value in dict(ECX=ecx, EDX=edx, EAX=eax, EBX=ebx, ESI=esi,
                                EDI=edi, EBP=0x44444444, ESP=self.STACK,
                                EFLAGS=0x202).items():
            self.reg(name, value)
        self.uc.mem_write(self.STACK, struct.pack("<" + "I" * (len(args) + 1),
                                                self.STOP, *(a & 0xFFFFFFFF for a in args)))
        end = self.STOP if stop is None else stop
        self.uc.emu_start(address, end, count=budget)
        if self.reg("EIP") != end:
            raise AssertionError(f"instruction budget exhausted at {self.reg('EIP'):#x}")
        return self.reg("EAX")

    def load_roster(self, save):
        if len(save) != 720044:
            raise ValueError("expected one bounded retail franchise body")
        self.uc.mem_write(self.ARENA, save)
        self.fixup_roster(self.ARENA + 0x320)

    def load_retail_roster(self, body):
        from mod_editor.core import nfl2k5_roster_records as rr
        if hashlib.sha256(body).hexdigest() != rr.RETAIL_BODY_SHA256:
            raise ValueError("retail roster evidence pin differs")
        self.uc.mem_write(self.ARENA + 0x300, body)
        self.fixup_roster(self.ARENA + 0x340)

    def fixup_roster(self, root):
        self.root = root
        self.put(0xB72918, self.root)
        self.call(0xC0500, ecx=self.root)
        self.team_base = self.get(self.root + 0x1C)
        for team in range(min(32, self.get(self.root + 0x18))):
            self.put(0xE5786C + 4 * team, self.team_base + team * 500)

    def load_franchise(self, save):
        self.load_roster(save)
        self.call(0xC5800, ecx=self.ARENA + 0x91320, budget=3000000)
        self.call(0x2D0CE0, ecx=self.ARENA + 0x996FC, budget=3000000)

    def seed(self, value):
        # Separate native draft/league and match PRNGs; zeroing RAM is not seeding.
        for address in (0xB12680, 0xE5FCA0):
            self.call(0x48BE0, ecx=address, edx=value)
