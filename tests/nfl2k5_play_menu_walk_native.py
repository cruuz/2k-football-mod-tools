"""Bounded native harness: the play call's own formation play-list code, run under Unicorn on one PLAY book.

The game lists a formation's plays with 0xE1320 (the play in the first menu link) and 0xE1360 (the play in the
link after the FIRST link holding the current play); the play-list screen's enter callback 0xACCE0 (record
0x50FD50) repeats 0xE1360 with no bound while a formation is picked. On the retail executable a book is loaded as
the PLAY body with its header table pointers made absolute (+0x30 strings, +0x44 formations, +0x48 formation aux
records, +0x60 plays, +0x64 categories, +0x68 nodes), which is exactly what the accessors 0xE0660, 0xE0830,
0xE06E0, 0xE0950 and 0xE0990 read. Nothing else is modelled: 0xACCE0's six menu calls are answered by stubs.

Used by tests/mod_editor/test_nfl2k5_play_menu_walk.py (vb2, 2026-09-23: Noah's Practice hang)."""
from __future__ import annotations

import struct

FIRST_PLAY, NEXT_PLAY, PAGE_BUILDER = 0xE1320, 0xE1360, 0xACCE0
BOOK_VA, STATE_VA, MENU_VA = 0x2000000, 0x2400000, 0x2401000
STACK, STOP = 0x3008000, 0x3100000
RELOCATED_HEADER_FIELDS = (0x30, 0x44, 0x48, 0x60, 0x64, 0x68)
PAGE_BUILDER_BUDGET = 400_000     # every retail formation returns in well under 20,000 instructions


class MenuWalker:
    """One Unicorn machine over the retail executable and one book; walk(), page_builder()."""

    def __init__(self, xbe: bytes, resource: bytes):
        import unicorn as u
        from unicorn import x86_const as r
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from mod_editor.core.nfl2k5_playbook_inspector import RESOURCE_HEADER_SIZE, BODY_SIZE

        self.u, self.r = u, r
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        image = XbeImage(xbe)
        top = max(section.start + section.raw_size for section in image.sections)
        self.uc.mem_map(0x10000, ((top + 0xFFFF) & ~0xFFFF) - 0x10000)
        for section in image.sections:
            if section.raw_size:
                self.uc.mem_write(section.start, image.read(section.start, section.raw_size))
        if len(resource) != RESOURCE_HEADER_SIZE + BODY_SIZE:
            raise ValueError("expected one whole PLAY resource")
        body = bytearray(resource[RESOURCE_HEADER_SIZE:])
        for field in RELOCATED_HEADER_FIELDS:
            value = struct.unpack_from("<i", body, field)[0]
            struct.pack_into("<I", body, field, BOOK_VA + field - 1 + value)
        for address, size in ((BOOK_VA, 0x40000), (STATE_VA, 0x2000), (0x3000000, 0x10000), (STOP, 0x1000)):
            self.uc.mem_map(address, size)
        self.uc.mem_write(BOOK_VA, bytes(body))
        self.stubs: dict[int, object] = {}
        self.page_items: list[int] = []
        self.uc.hook_add(u.UC_HOOK_CODE, self._hook, begin=0xF3500, end=0xF3700)
        self.uc.hook_add(u.UC_HOOK_CODE, self._hook, begin=0xABB70, end=0xABB71)

    @staticmethod
    def formation_va(index: int) -> int:
        return BOOK_VA + 0x134 + index * 0xB4

    @staticmethod
    def play_index(va: int) -> int:
        return (va - (BOOK_VA + 0x33FC)) // 0x60

    def _hook(self, uc, address, _size, _data):
        stub = self.stubs.get(address)
        if stub is not None:
            stub()

    def _return(self, value=0, pop=0):
        r = self.r
        sp = self.uc.reg_read(r.UC_X86_REG_ESP)
        back = struct.unpack("<I", self.uc.mem_read(sp, 4))[0]
        self.uc.reg_write(r.UC_X86_REG_EAX, value)
        self.uc.reg_write(r.UC_X86_REG_ESP, sp + 4 + pop)
        self.uc.reg_write(r.UC_X86_REG_EIP, back)

    def _call(self, va, *, ecx=0, edx=0, args=(), budget):
        r = self.r
        self.uc.mem_write(STACK, struct.pack("<I", STOP) + b"".join(struct.pack("<I", a) for a in args))
        for reg, value in ((r.UC_X86_REG_ESP, STACK), (r.UC_X86_REG_EAX, 0), (r.UC_X86_REG_ECX, ecx),
                           (r.UC_X86_REG_EDX, edx), (r.UC_X86_REG_EBX, 0), (r.UC_X86_REG_ESI, 0),
                           (r.UC_X86_REG_EDI, 0), (r.UC_X86_REG_EBP, 0)):
            self.uc.reg_write(reg, value)
        self.uc.emu_start(va, STOP, count=budget)
        return self.uc.reg_read(r.UC_X86_REG_EAX), self.uc.reg_read(r.UC_X86_REG_EIP) == STOP

    def walk(self, formation: int, limit: int = 72) -> tuple[list[int], bool]:
        """(play order, ended): 0xE1320 then 0xE1360 until it gives no play, at most ``limit`` plays."""
        fva = self.formation_va(formation)
        play, _ = self._call(FIRST_PLAY, ecx=BOOK_VA, edx=fva, budget=20_000)
        order: list[int] = []
        while play and len(order) < limit:
            order.append(self.play_index(play))
            play, _ = self._call(NEXT_PLAY, ecx=BOOK_VA, edx=fva, args=(play,), budget=20_000)
        return order, not play

    def page_builder(self, formation: int, page: int = 0, budget: int = PAGE_BUILDER_BUDGET) -> tuple[bool, list[int]]:
        """(returned within ``budget`` instructions, the plays put on the page) for 0xACCE0 with the formation
        picked; the menu object's six calls are stubs."""
        state = STATE_VA
        self.uc.mem_write(state, bytes(0x100))
        self.uc.mem_write(state + 0x30, bytes([page]))
        self.uc.mem_write(state + 0x20, struct.pack("<I", BOOK_VA))
        self.uc.mem_write(state + 0x50, struct.pack("<I", self.formation_va(formation)))
        items: list[int] = []
        self.stubs = {
            0xF3540: lambda: self._return(state),        # the menu's play-call state
            0xF3520: lambda: self._return(0),            # clear the menu
            0xF3560: lambda: self._return(0),            # construct an item on the stack
            0xF36F0: lambda: (items.append(self.play_index(self.uc.reg_read(self.r.UC_X86_REG_EDX))),
                              self._return(0)),          # bind the item to a play
            0xF36A0: lambda: self._return(0),            # append the item
            0xABB70: lambda: self._return(0, pop=4),     # page arrows (callee pops one argument)
        }
        try:
            _, returned = self._call(PAGE_BUILDER, ecx=MENU_VA, budget=budget)
        finally:
            self.stubs = {}
        return returned, items
