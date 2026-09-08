"""Bounded native weekly prep probes on a signed private Franchise fixture.

No game boot or I/O. By default every native prep, roster fixup, season and
front-office routine executes. Individual tests name any substituted service.
"""
from __future__ import annotations

import struct

from mod_editor.core import nfl2k5_weekly_prep as patch
from mod_editor.core import nfl2k5_weekly_prep_save as prep
from mod_editor.core import nfl2k5_xbe_space as space
from tests.nfl2k5_supersim_draft_fixture import Machine as NativeMachine, HAVE_UC, retail_bytes, signed_save


class Machine(NativeMachine):
    def __init__(self, payload, save=None):
        super().__init__(payload, trace_writes=False)
        for region in space.layout(payload)["regions"]:
            self.uc.mem_protect(region["va"], region["size"], self.u.UC_PROT_READ |
                                (self.u.UC_PROT_EXEC if region["kind"] == "code" else self.u.UC_PROT_WRITE))
        self.labels = {}
        if patch.status(payload) == "applied":
            base = patch.allocation(payload)["va"]
            self.labels = {k: base + v for k, v in patch.assembly.LABELS.items()}
        self.uc.reg_write(self.x.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(self.x.UC_X86_REG_MXCSR, 0x1F80)
        if save is not None:
            self.load_franchise(save)
            self.uc.mem_write(0xE5FF80, save[:0x2E0])
            self.seed(12345)

    def call(self, address, **kwargs):
        value = super().call(self.labels.get(address, address), **kwargs)
        if kwargs.get("stop") is None:
            expected = self.STACK + 4 + 4 * len(kwargs.get("args", ()))
            if self.reg("ESP") != expected:
                raise AssertionError(f"unbalanced native stack at {address}: {self.reg('ESP'):#x}")
        return value

    def team(self, index):
        return self.get(0xE5786C + index * 4)

    def players(self, team):
        at = self.team(team)
        count = self.uc.mem_read(at + 0x11C, 1)[0]
        return [self.get(at + i * 4) for i in range(count)]

    def plan(self, team, words=None):
        va = prep.PLAN_VA + team * 2000
        if words is not None:
            self.uc.mem_write(va, struct.pack("<500I", *words))
        return struct.unpack("<500I", self.uc.mem_read(va, 2000))

    def game(self, home=0, away=1, *, week=0, slot=0, stage=8):
        for va, value in ((0xE576A0, 2), (0xE576A4, stage), (0xE576AC, 32),
                          (0xE576B4, week), (0xE576BC, slot), (0xE6011C, 1)):
            self.put(va, value)
        self.uc.mem_write(0xE57C40 + (week * 17 + slot) * 8, bytes((0, home, away, 0, 0, 0, 0, 0)))

    def ratings(self, team):
        return tuple(bytes(self.uc.mem_read(p + 0x36, 28)) for p in self.players(team))

    def snapshot(self, team):
        for i, player in enumerate(self.players(team)):
            self.uc.mem_write(prep.SNAPSHOT_VA + team * 195 + i * 3,
                              bytes(self.uc.mem_read(player + at, 1)[0] for at in (0x4C, 0x39, 0x3B)))

    def eligible(self, player, activity):
        self.put(self.ARENA + 0x180000, prep.encode(activity=activity))
        return self.call(0x2AB610, ebx=self.ARENA + 0x180000, edi=player, args=(self.team(0),))
