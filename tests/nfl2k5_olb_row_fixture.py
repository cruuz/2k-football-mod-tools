"""Bounded native selector/list fixture. No game boot, graphics or audio.

Run the real page builder, count/getters, argument bindings, draft cache,
navigation and allocator callers. Only heap, cell art/geometry, visual sorting,
Pro Bowl eligibility scores, and a trade team's context callback are supplied.
Membership tests are never stubbed. The small scenario uses real recoded player
records with controlled team, FA and prospect membership in emulated RAM.
"""
from __future__ import annotations

from collections import Counter
import struct

from mod_editor.core import nfl2k5_position_pools as pools


class Machine:
    BASE = 0x2000000
    ROOT = BASE + 0x40
    UI = 0x2400000
    MANAGER = UI + 0x2000
    HEAP = 0x2500000
    STACK = 0x3008000
    STOP = 0x3100000

    def __init__(self, payload, resource, pooled_body, *, custom=False):
        import unicorn as u
        from unicorn import x86_const as r
        self.u, self.r = u, r
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1500000 - 0x10000)
        for section in pools._sections(payload):
            if section.raw_size:
                self.uc.mem_write(section.virtual_address,
                                  payload[section.raw_offset:section.raw_offset + section.raw_size])
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_protect(0x4E0000, 0x550000, u.UC_PROT_READ)
        for at, size in ((self.BASE, 0x600000), (0x3000000, 0x10000), (self.STOP, 0x1000)):
            self.uc.mem_map(at, size)
        self.uc.mem_write(self.BASE, pooled_body)
        self.put(0xB72918, self.ROOT)
        self.call(0xC0500, ecx=self.ROOT)  # actual ROST pointer relocation
        self.team = self.word(self.ROOT + 0x1C)
        team_candidates = [self.BASE + p for p in resource.teams[0].roster]
        fa_count, fa_table = self.word(self.ROOT + 0x38), self.word(self.ROOT + 0x3C)
        fa_candidates = [self.word(fa_table + 4 * i) for i in range(fa_count)]
        positions = (0, 11, 16, 11) if custom else (0, 11, 16)

        def select(candidates):
            selected = []
            for enum in positions:
                ptr = next(p for p in candidates if p not in selected and self.byte(p + 0x35) == enum)
                selected.append(ptr)
            if custom:
                self.uc.mem_write(selected[-1] + 0x35, b"\x0a")
            return selected

        self.team_players, self.fa_players = select(team_candidates), select(fa_candidates)
        for team in resource.teams:
            self.uc.mem_write(self.BASE + team.offset + 0x11C, b"\0")
        for i, ptr in enumerate(self.team_players):
            self.put(self.team + 4 * i, ptr)
        self.uc.mem_write(self.team + 0x11C, bytes([len(self.team_players)]))
        self.put(self.ROOT + 0x38, len(self.fa_players))
        for i, ptr in enumerate(self.fa_players):
            self.put(fa_table + 4 * i, ptr)
        # Supply a tiny draft class from distinct FA records. Other players are
        # still present in the primary table, with their prospect flag cleared.
        table = resource.tables["primary_players"]
        for i in range(int(table["count"])):
            p = self.BASE + int(table["offset"]) + 0x54 * i
            self.uc.mem_write(p + 8, bytes([self.byte(p + 8) & ~0x10]))
        for p in self.fa_players:
            self.uc.mem_write(p + 8, bytes([self.byte(p + 8) | 0x10]))
        self.put(0xCC0D44, 0xFFFFFFFF)  # force native draft cache population
        # Native team selectors and conference mapping, with all teams except
        # the first empty. Division 4 belongs to conference 0, the selected tab.
        self.put(0xE576A0, 1)
        self.put(0xE576A4, 7)
        self.put(0xE576AC, 32)
        self.uc.mem_write(0xE421E0, bytes(160 * 4))
        self.uc.mem_write(0xE5775C, bytes(34 * 4))
        for i in range(32):
            self.put(0xE5786C + 4 * i, self.team + 500 * i)
            self.put(0xE576D4 + 4 * i, 4)
        self.put(0xE5775C, 1)
        self.put(0xE3C0A0, self.team)
        self.put(0xCC3294, 0x2201000)
        self.put(0x2201008, self.STOP + 0x100)
        self.put(self.MANAGER + 0x10C, self.UI + 0x4000)
        self.put(self.UI + 4, self.MANAGER)
        self.put(0xACECD0, 1)
        self.put(0xACED60, 0xFFFFFFFF)
        self.heap_next = self.HEAP
        self.live = set()
        self.services = Counter()
        self.native_calls = Counter()
        self.uc.hook_add(u.UC_HOOK_CODE, self._hook)
        self.body_size = len(pooled_body)
        self.roster_before = bytes(self.uc.mem_read(self.BASE, self.body_size))

    def word(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def byte(self, va):
        return self.uc.mem_read(va, 1)[0]

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def _ret(self, value=0, pop=0):
        r = self.r
        sp = self.uc.reg_read(r.UC_X86_REG_ESP)
        self.uc.reg_write(r.UC_X86_REG_EAX, value)
        self.uc.reg_write(r.UC_X86_REG_EIP, self.word(sp))
        self.uc.reg_write(r.UC_X86_REG_ESP, sp + 4 + pop)

    def _hook(self, uc, pc, _size, _data):
        if pc in (0x174140, 0x170910, 0x174CB0, 0x174CE0, 0x174D30,
                  0x35FD40, 0x35F140, 0x2B8D90, 0x3213E0, 0x31AB20,
                  0x36F720, 0xC3CB0, 0xC3D30, 0x242670, 0x242520):
            self.native_calls[pc] += 1
        if pc == 0x48700:
            size = uc.reg_read(self.r.UC_X86_REG_EDX)
            assert size < 0x100000, "unbounded allocation"
            at = self.heap_next
            self.heap_next += (max(size, 4) + 15) & -16
            assert self.heap_next < self.HEAP + 0x100000, "heap budget exhausted"
            self.live.add(at)
            self._ret(at)
        elif pc == 0x48870:
            at = uc.reg_read(self.r.UC_X86_REG_ECX)
            assert not at or at in self.live, "free outside fixture heap"
            self.live.discard(at)
            self._ret()
            if not self.live:
                self.heap_next = self.HEAP
        elif pc in (0x172660, 0x1739F0, 0x1701A0, 0x16F570):
            self.services[pc] += 1
            self._ret(pop={0x1739F0: 8, 0x16F570: 24}.get(pc, 0))
        elif pc == 0xE6520:
            # Positive, equal vote scores; native position/conference filtering
            # and top-ten insertion remain real. No claim about season stats.
            self.services[pc] += 1
            self._ret(100)
        elif pc == self.STOP + 0x100:
            self.services[pc] += 1
            self._ret(self.team)

    def call(self, address, *, ecx=0, edx=0, eax=0, args=(), extra=()):
        r = self.r
        saved = {r.UC_X86_REG_EBX: 0x11111111, r.UC_X86_REG_ESI: 0x22222222,
                 r.UC_X86_REG_EDI: 0x33333333, r.UC_X86_REG_EBP: 0x44444444}
        saved.update(extra)
        self.put(self.STACK, self.STOP)
        for i, value in enumerate(args, 1):
            self.put(self.STACK + 4 * i, value)
        for reg, value in {**saved, r.UC_X86_REG_ESP: self.STACK, r.UC_X86_REG_ECX: ecx,
                           r.UC_X86_REG_EDX: edx, r.UC_X86_REG_EAX: eax}.items():
            self.uc.reg_write(reg, value)
        self.uc.emu_start(address, self.STOP, count=3000000)
        assert self.uc.reg_read(r.UC_X86_REG_EIP) == self.STOP, "native instruction budget exhausted"
        assert self.uc.reg_read(r.UC_X86_REG_ESP) == self.STACK + 4 + 4 * len(args), "stack imbalance"
        for reg, value in saved.items():
            assert self.uc.reg_read(reg) == value, f"callee-saved register {reg} changed"
        return self.uc.reg_read(r.UC_X86_REG_EAX)

    def open(self, table):
        self.put(self.UI + 0x58, table - 0xF4)
        self.put(self.UI + 0x5C, table)
        self.call(0x1746C0, eax=self.UI)

    def result(self):
        count, table = self.word(self.UI + 0xA4), self.word(self.UI + 0x40)
        assert count < 1024, "fixture player-list budget exceeded"
        title = self.word(self.UI + 0xF0)
        raw = bytearray()
        for i in range(80):
            pair = bytes(self.uc.mem_read(title + 2 * i, 2))
            if pair == b"\0\0":
                break
            raw.extend(pair)
        return {"enum": self.word(self.UI + 0x64), "title": raw.decode("utf-16le"),
                "players": [self.word(table + 4 * i) for i in range(count)]}

    def close(self):
        self.call(0x1707F0, ecx=self.UI)
        assert not self.live, "native sheet cleanup leaked allocations"
        assert bytes(self.uc.mem_read(self.BASE, self.body_size)) == self.roster_before, "list build mutated roster"
