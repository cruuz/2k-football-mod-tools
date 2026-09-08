"""Bounded USA instruction fixtures, no game loop or played-game claim.

The target selector and loaded PLAY classifier run with no substituted
helpers. Decision replay may supply only the kicker-derived maximum FG range;
the retail caller, punt/FG decisions, time, score, distance and RNG run natively.
"""
from __future__ import annotations

import struct
import random

from mod_editor.core import nfl2k5_cpu_money_downs as patch
from mod_editor.core import nfl2k5_xbe_space as space
from tests.mod_editor.test_nfl2k5_qb_spy_unicorn import Machine as BaseMachine, uc, x86


def bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


class Machine(BaseMachine):
    FRAME = 0x310E000

    def __init__(self, payload):
        super().__init__(payload, patched=False)
        self.owner = next((a["va"] for a in space.layout(payload)["allocations"]
                           if a["owner"] == patch.OWNER), None)
        self.u32(self.OFF, self.DEF)
        self.u32(self.DEF, self.OFF)
        self.u32(self.DEF+8, self.DEF+0x200)
        self.u32(self.OFF+12, self.OFF+0x100)
        self.u32(0xE6028C, self.GAME+0x500)
        self.u32(0xE60294, self.GAME+0x600)
        self.f32(self.GAME+0x600+0x10, 25)
        self.u32(0xE601EC, 0)
        self.f32(0xBF1244, .5)
        self.f32(0xBF1484, .5)
        self.f32(0xBF1240, 120)
        self.f32(0xBF1480, 120)
        self.f32(0xE602AC, 5)
        self.run(0x164000)           # native opcode-table installation
        self.configure()

    def observe(self, _u, address, _size, _data):
        self.hits.append(address)
        if address == self.stop_at:
            self.uc.emu_stop()

    def configure(self, *, down=4, own_yard=50, distance=2, score_margin=0,
                  quarter=2, seconds=600, cpu=True, phase=4, direction=1):
        self.u32(self.GAME+4, down)
        self.u32(0xE602B4, phase)
        self.u32(0xE602C4, quarter)
        self.u32(self.OFF+0x30, 0 if cpu else 1)
        self.f32(self.DIR+4, direction)
        self.f32(self.GAME+0x18, (own_yard-50)*91.44*direction)
        self.f32(self.GAME+0x28, (own_yard-50+distance)*91.44*direction)
        self.u32(self.OFFMETA, 30+score_margin)
        self.u32(self.DEF+0x200, 30)
        self.u32(self.OFFMETA+4, 3)
        self.u32(self.DEF+0x204, 3)
        self.f32(self.GAME+0x510, seconds)
        self.f32(0xE602B0, 0)
        self.direction = direction
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)

    def policy(self, **settings):
        self.configure(**settings)
        self.run(self.owner+patch.assembly.LABELS["policy"])
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def supply_fg_range(self, yards=40):
        # Environmental input only: replace the kicker/roster-derived helper.
        # All decision code, constants and native continuations stay installed.
        self.f32(self.SOURCE+0x1F000, yards*91.44)
        self.uc.mem_write(0x18B120, b"\xd9\x05" + struct.pack("<I", self.SOURCE+0x1F000) + b"\xc3")

    def category(self, **settings):
        self.configure(**settings)
        self.u32(0xBF16FC, 0)
        self.u32(0xBF1700, 0)
        self.seed(1)
        self.run(0x20B180, ecx=self.OFF, count=10000)
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def seed(self, seed):
        generator = random.Random(seed)
        self.u32(0xE5FCA0, 54)
        self.u32(0xE5FCA4, 23)
        for index in range(110):
            self.u32(0xE5FCA8+index*4, generator.getrandbits(32))

    def difficulty(self, value):
        self.u32(0xE5FF84, value)
        self.run(0xE3740, count=30000)
        return self.readf(0xE600F8), self.readf(0xE600D4)

    def prepare_selection(self, resource, *, buffer=0):
        self.load_book(resource, buffer)
        base = 0xB75A40+buffer*0x13390
        self.u32(self.OFF+0x20, base)
        for index in range(self.get(base+0x38)):
            self.run(0x1A9A80, ecx=base+0x33FC+index*96, count=30000)
        return base

    def selection_weights(self, *, formation=8, category=4, buffer=0, **settings):
        """Real selector through native scoring, before its random choice.

        The harness supplies initialized zero team tendency/history tables.
        Retail loader, validator, formation eligibility and scorer all execute.
        Returned weights are the actual normalized native candidate array.
        """
        self.configure(**settings)
        base = 0xB75A40+buffer*0x13390
        self.run(0x2096A0, ecx=self.OFF, edx=8,
                 args=(base+0x134+formation*180, base+0x993C+category*16, 0),
                 stop_at=0x209C3A, count=1000000)
        frame = self.uc.reg_read(x86.UC_X86_REG_EBP)
        count = self.uc.reg_read(x86.UC_X86_REG_EDI)
        rows = []
        for index in range(count):
            play = self.get(frame-0x120+4*index)
            weight = struct.unpack("<f", self.uc.mem_read(frame-0xA8+4*index, 4))[0]
            mirror = bool(self.get(frame-0x198+4*index))
            rows.append({"play_index": (play-base-0x33FC)//96, "weight": weight,
                         "mirrored": mirror})
        return rows

    def sample_weights(self, rows, seed):
        """The game's real cubed-weight roulette and real RNG, bounded array."""
        self.seed(seed)
        for index, row in enumerate(rows):
            self.f32(self.GAME+0x900+index*4, row["weight"])
        self.run(0x203440, args=(self.GAME+0x900, len(rows), 3), count=2000)
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def primary(self, resource, play, formation, *, buffer=0, mirrored=False):
        self.load_book(resource, buffer)
        return self.primary_loaded(play, formation, buffer=buffer, mirrored=mirrored)

    def primary_loaded(self, play, formation, *, buffer=0, mirrored=False):
        base = 0xB75A40+buffer*0x13390
        self.u32(self.FRAME+8, base+0x134+formation*180)
        self.u32(self.FRAME-0x28, int(mirrored))
        self.run(self.owner+patch.assembly.LABELS["primary_depth"],
                 esi=base+0x33FC+play*96, ebp=self.FRAME)
        value = self.uc.reg_read(x86.UC_X86_REG_EAX)
        return None if value == 0xFFFF8000 else (value if value < 2**31 else value-2**32)

    def play_weight(self, play, formation, *, buffer=0, mirrored=False, native_weight=1):
        base = 0xB75A40+buffer*0x13390
        self.u32(self.FRAME+8, base+0x134+formation*180)
        self.u32(self.FRAME-0x28, int(mirrored))
        self.u32(self.FRAME-0x20, self.OFF)
        self.f32(self.SOURCE+0x1E000, native_weight)
        # Push a native score onto x87, then enter the real six-byte hook.
        trampoline = b"\xd9\x05" + struct.pack("<I", self.SOURCE+0x1E000)
        trampoline += b"\xe9" + struct.pack("<i", 0x20980D-(self.SOURCE+0x1D000+11))
        self.uc.mem_write(self.SOURCE+0x1D000, trampoline)
        self.run(self.SOURCE+0x1D000, stop_at=0x209813, esi=base+0x33FC+play*96, ebp=self.FRAME)
        return struct.unpack("<f", self.uc.mem_read(self.FRAME-0x18, 4))[0]

    def targets(self, candidates, *, threshold=.5, human_passer=False, **settings):
        self.configure(**settings)
        self.u32(self.QB+0x100, 0 if human_passer else -1)
        los = struct.unpack("<f", self.uc.mem_read(self.GAME+0x18, 4))[0]
        self.u32(0xBE480C, len(candidates))
        self.uc.mem_write(0xBE4820, bytes(0xA0*5))
        for index, candidate in enumerate(candidates):
            actor = self.RB + index*0x2000
            self.player(actor, self.OFF)
            self.u32(actor+0xD30, actor+0xD80)
            self.u32(actor+0xDA0, 0)
            self.uc.mem_write(0xAA4498, b"\0")
            row = 0xBE4820+index*0xA0
            self.u32(row, actor)
            self.u32(row+8, int(candidate.get("available", True)))
            self.u32(row+0x10, int(candidate.get("viable", True)))
            for projection in range(4):
                score = row+0x34+projection*0x20
                self.f32(score, candidate["score"] if projection == 0 else -float("inf"))
                self.f32(score-12, los+candidate["yards"]*91.44*self.direction)
                self.f32(score-4, candidate.get("penalty", 0))
        args = (self.GAME+0x800, self.GAME+0x804, bits(threshold), self.GAME+0x808)
        self.run(0x1985E0, args=args, count=10000)
        row = self.get(self.GAME+0x800)
        return None if row == 0 else (row-0xBE4820)//0xA0
