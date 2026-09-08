"""Bounded native menu/record fixture, without a game boot or graphics.

Screen management, event/input/binding dispatch, table construction, player
selection, popup filtering, editor pages, field setters and parent restoration
execute the installed x86. Services below cover heap, controller hardware,
modal interaction, cell drawing/geometry/sorting and the 3D preview.
"""
from __future__ import annotations

from collections import Counter, deque
import struct

from mod_editor.core import nfl2k5_franchise_edit_player as edit
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise


class Machine:
    BASE, UI, HEAP = 0x2000000, 0x2200000, 0x2300000
    MANAGER, STATE = UI + 0x100, UI + 0x1000
    STACK, STOP = 0x3008000, 0x3100000
    MAIN, DESK, OFFICE = 0x515660, 0x522190, 0x52533C

    def __init__(self, payload, *, face=False, desk_depth=1, stage=8):
        import unicorn as u
        from unicorn import x86_const as x
        import gc
        gc.collect()  # release prior Unicorn hook cycles before mapping another fixture
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        im = XbeImage(payload)
        self.uc.mem_map(0x10000, 0x1600000 - 0x10000)
        for s in im.sections:
            self.uc.mem_write(s.start, im.read(s.start, s.raw_size))
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        for region in space.layout(payload)["regions"]:
            section = im.section(region["va"])
            if section is None:  # retail layout reports planned, unmapped grown pages
                continue
            flags = u.UC_PROT_READ | (u.UC_PROT_WRITE if section.writable else 0) | (u.UC_PROT_EXEC if section.executable else 0)
            self.uc.mem_protect(region["va"], region["size"], flags)
        for va, size in ((self.BASE, 0x500000), (0x3000000, 0x10000), (self.STOP, 0x1000)):
            self.uc.mem_map(va, size)
        self.trace = deque(maxlen=80)
        self.calls, self.services = Counter(), Counter()
        self.events, self.writes, self.modals = [], [], []
        self.heap_next, self.live = self.HEAP, set()
        self.buttons, self.face, self.choice = 0, face, edit.EDIT_ACTION
        self.uc.hook_add(u.UC_HOOK_CODE, self._hook)
        self.uc.hook_add(u.UC_HOOK_MEM_WRITE, self._write)
        self.save = synthetic_franchise()
        self.uc.mem_write(self.BASE, self.save)
        self.root = self.BASE + 0x320
        self.put(0xB72918, self.root)
        self.call(0xC0500, ecx=self.root)
        self.team = self.get(self.root + 0x1C)
        self.player = self.get(self.team + 4)  # deliberately not the first player
        self.put(0xE576A0, 2)
        self.put(0xE576A4, stage)
        self.put(0xE576AC, 32)
        self.put(0xE576B4, 3)
        self.put(0xE576B8, 7)
        self.put(0xE576BC, 0)
        for i in range(32):
            self.put(0xE5786C + 4*i, self.team + 500*i if i < 3 else 0)
        self.put(0xE3C0A0, self.team)
        self.put(0xE5775C, 1)
        self.put(0xACECD4, 0)
        self.put(0xACED60, 32)
        self.put(0xACECD0, 2)
        self.put(0xE60148, 1)
        self.put(0xBD8050, 1)
        self.put(0xCB8D10, self.UI + 0x500)  # completed Front Office fade
        self.put(self.UI + 0x504, 0x3F800000)
        self.put(0xCB8FD0, 0x3F800000)
        self.put(0xCB8FD8, 0)
        self.put(self.MANAGER + 0x10C, self.STATE)
        self.put(self.MANAGER, self.MAIN)
        self.put(self.MANAGER + desk_depth * 8, self.DESK)
        self.put(self.MANAGER + (desk_depth + 1) * 8, self.OFFICE)
        self.put(self.MANAGER + (desk_depth + 2) * 8, edit.CONTRACTS_VA)
        self.put(self.MANAGER + 0x100, desk_depth + 2)
        self.contracts_depth = self.depth()
        # Meaningful, nonzero depth locks/abilities, contract fields and cap.
        self.uc.mem_write(self.player + 0x52, b"\xff\xff")
        self.put(0xE3C278, 80500)
        self.put(0xE3C600, self.player - 84)  # unrelated pending offer, not this player's contract
        self.put(0xE3C604, self.team)
        self.put(0xE3C608, 0x01000000)
        self.put(0xE3C60C, 123456)
        self.snapshots = {va: bytes(self.uc.mem_read(va, n)) for va, n in (
            (self.BASE, len(self.save)), (0xE576A0, 0x5A0), (0xE3C0A0, 0x63C0))}

    @property
    def table(self):
        return self.STATE + 0x65C

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def reg(self, name, value=None):
        key = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(key)
        self.uc.reg_write(key, value & 0xFFFFFFFF)

    def ret(self, value=0, pop=0):
        sp = self.reg("ESP")
        self.reg("EIP", self.get(sp))
        self.reg("ESP", sp + 4 + pop)
        self.reg("EAX", value)

    def depth(self):
        return self.get(self.MANAGER + 0x100)

    def top(self):
        return self.get(self.MANAGER + 8*self.depth())

    def text(self, va):
        data = bytearray()
        for i in range(160):
            pair = bytes(self.uc.mem_read(va + 2*i, 2))
            if pair == b"\0\0":
                return data.decode("utf-16le")
            data.extend(pair)
        raise AssertionError("unterminated fixture text")

    def _write(self, uc, access, va, size, value, _):
        if self.BASE <= va < self.UI or 0xE3C0A0 <= va < 0xE42460 or 0xE576A0 <= va < 0xE57C40:
            self.writes.append((self.reg("EIP"), va, size, value))

    def _hook(self, uc, pc, size, _):
        self.trace.append(pc)
        self.calls[pc] += 1
        if pc == 0x6E4E0:
            self.events.append((self.top(), self.get(self.reg("ESP") + 4)))
        if pc == 0x48700:
            count = self.reg("EDX")
            assert count < 0x100000, "unbounded native heap request"
            at = self.heap_next
            self.heap_next += (max(count, 4) + 15) & -16
            assert self.heap_next < self.HEAP + 0x100000, "native heap budget exhausted"
            self.live.add(at)
            self.ret(at)
        elif pc == 0x48870:
            at = self.reg("ECX")
            assert not at or at in self.live, f"foreign native free {at:#x}"
            self.live.discard(at)
            self.ret()
        elif pc in (0x1701A0, 0x16F570):
            self.services[pc] += 1
            self.ret(pop={0x16F570: 24}.get(pc, 0))
        elif pc in (0xF2920, 0xF3CD0, 0xF3D60, 0xF37E0, 0xF2D40,
                    0x14D310, 0x14D390, 0x91900, 0x91930, 0x91A40,
                    0x2498A0, 0x6B730, 0x6B740):
            self.services[pc] += 1
            self.ret()
        elif pc == 0x346890:  # 3D preview camera; return depth is recorded by 346B90
            self.services[pc] += 1
            self.ret(pop=4)
        elif pc == 0x912E0:  # real-face asset lookup, two controlled availability cases
            self.services[pc] += 1
            self.ret(int(self.face))
        elif pc == 0x91940:  # asynchronous player preview loading
            self.services[pc] += 1
            self.ret(0)
        elif pc in (0x709B0,):
            self.services[pc] += 1
            self.ret(int(self.reg("ECX") == 0))
        elif pc in (0xF3750, 0xF3780, 0xF3720):
            self.services[pc] += 1
            self.ret(self.buttons if self.reg("EDX") == 0 else 0, pop=4)
        elif pc in (0x70A50, 0x70AC0):
            self.services[pc] += 1
            self.buttons &= ~self.get(self.reg("ESP") + 4)
            self.ret(pop=4)
        elif pc == 0x14E540:  # Rosters confirmation modal, used only by the parity test
            self.services[pc] += 1
            self.ret(1)
        elif pc == 0x145B60:  # title formatting; live player lookup above this call runs
            self.services[pc] += 1
            self.ret(edit.EDIT_LABEL_VA)
        elif pc == 0x14E440:
            self.services[pc] += 1
            at = self.get(self.reg("ESP") + 4)
            entries = []
            for i in range(12):
                label, action = self.get(at + 8*i), self.get(at + 8*i + 4)
                if not label:
                    assert action == 0, "popup terminator is not completely zero"
                    break
                entries.append((self.text(label), action))
            else:
                raise AssertionError("popup has no bounded terminator")
            self.modals.append(entries)
            selected = self.choice if self.choice in [v for _, v in entries] else 7
            self.ret(selected, pop=24)
        elif pc in (0xC5D60, 0x13F1B0):
            raise AssertionError(f"editor reached season commit/new Franchise {pc:#x}")

    def call(self, entry, *, ecx=0, edx=0, eax=0, args=(), budget=300000):
        self.put(self.STACK, self.STOP)
        for i, value in enumerate(args, 1):
            self.put(self.STACK + 4*i, value)
        for name, value in (("ESP", self.STACK), ("ECX", ecx), ("EDX", edx), ("EAX", eax),
                            ("EBX", 0x11111111), ("ESI", 0x22222222),
                            ("EDI", 0x33333333), ("EBP", 0x44444444), ("EFLAGS", 0x202)):
            self.reg(name, value)
        try:
            self.uc.emu_start(entry, self.STOP, count=budget)
        except Exception as exc:
            raise AssertionError(f"{exc}; PC={self.reg('EIP'):#x}; trace={[hex(p) for p in self.trace]}") from exc
        assert self.reg("EIP") == self.STOP, f"instruction budget exhausted: {[hex(p) for p in self.trace]}"
        assert self.reg("ESP") == self.STACK + 4 + 4*len(args), f"stack imbalance: {self.reg('ESP'):#x}"
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
            assert self.reg(name) == value, f"callee-saved {name} changed: {self.reg(name):#x}"
        return self.reg("EAX")

    def event(self, event):
        return self.call(0x6E4E0, ecx=self.MANAGER, args=(event,))

    def frame(self, buttons=0):
        self.buttons = buttons
        self.event(6)
        self.buttons = 0

    def build_contracts(self):
        self.event(3)

    def open(self):
        count, players = self.get(self.table + 0xA4), self.get(self.table + 0x40)
        selected = next(i for i in range(count) if self.get(players + 4*i) == self.player)
        self.put(self.table + 0xBC, selected)
        self.frame(0x100)

    def preserved(self, changed_offsets=()):
        for va, before in self.snapshots.items():
            after = bytearray(self.uc.mem_read(va, len(before)))
            for offset in changed_offsets:
                at = self.player + offset - va
                if 0 <= at < len(after):
                    after[at] = before[at]
            assert bytes(after) == before, f"unexpected roster/contract/season edit in {va:#x}"

    def field_descriptor(self, index):
        cell = self.get(self.get(self.table + 0x3C) + 4*index) + 0x2C
        return self.get(cell)

    def fields(self):
        return [self.text(self.get(self.field_descriptor(i) + 0x70))
                for i in range(self.get(self.table + 0xA4))]

    def select_field(self, label):
        index = self.fields().index(label)
        # Row movement itself executes the game's controller dispatch.
        for _ in range(self.get(self.table + 0xA4) + 1):
            current = self.get(self.table + 0xBC)
            if current == index:
                break
            self.frame(0x02000000 if current < index else 0x01000000)
        else:
            raise AssertionError("native row navigation exceeded the table's row count")
        return self.field_descriptor(index)

    def change(self, label, *, reverse=False):
        descriptor = self.select_field(label)
        setter = self.get(descriptor + (0x38 if reverse else 0x20))
        before = self.calls[setter]
        self.frame(0x800 if reverse else 0x100)
        assert self.calls[setter] == before + 1, "selected field did not reach its native setter"
        return setter

    def cursor(self):
        return tuple(self.get(self.table + off) for off in (0x5C, 0xAC, 0xBC, 0xC0, 0xC4, 0xC8))
