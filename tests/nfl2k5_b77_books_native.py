"""b77 / a4: which book does the executable pick for each side of each Anniversary moment? (the game's own code, Unicorn)

Selects a menu row with the Anniversary list's handler (20CB30), stages the match, and for each side runs the book resolver
hook at 62902 (``nfl2k5_stock_books``) with that side's real team object, the real SITU record and the real mode word. The
hook ends at one of three places: the franchise's own book formatter (62A1B, "default"), the stock alias copy (62A37, the
preserved retail bank), or the retail fall-through. Boundaries substituted are the harness's own (archive, list and clock
seams); no graphics, audio or complete game.
"""
from __future__ import annotations

import struct

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as regs

from mod_editor.core import nfl2k5_stock_books as books

ARENA = 0x2600000
EXITS = {0x62A1B: "default", 0x62A37: "stock_alias", 0x6290C: "retail_fall_through"}


def resolve_side(cpu, home: bool) -> dict:
    team = cpu.run(0x77B00 if home else 0x77B40)
    saved = cpu.run(0x775F0 if home else 0x77720)
    buf = 0xB307D0 if home else 0xB30810
    cpu.write(buf, b"\xA5" * 64)
    cpu.write(ARENA, bytes(0x100))
    cpu.w(0xE5FF80, 8)
    category = cpu.r(team + 0x128)
    key_object = cpu.r(team + 0x110)
    key = cpu.text(cpu.r(key_object + 4)) if key_object else None
    seen = {}

    def stop(uc, at, size, data):
        if at in EXITS:
            seen["at"] = at
            uc.emu_stop()

    handle = cpu.uc.hook_add(UC_HOOK_CODE, stop, begin=0x6290C, end=0x62A37)
    try:
        cpu.w(cpu.STACK, cpu.STOP)
        for name, value in dict(eax=team, ebx=0, edi=saved, esi=buf, ebp=ARENA + 0x18).items():
            cpu.uc.reg_write(getattr(regs, "UC_X86_REG_" + name.upper()), value)
        cpu.w(ARENA + 0x20, int(home))                      # [ebp+8], the formatter's argument: 1 home, 0 away
        cpu.uc.reg_write(regs.UC_X86_REG_ESP, cpu.STACK)
        cpu.uc.reg_write(regs.UC_X86_REG_EFLAGS, 0x202)
        cpu.uc.emu_start(books.SITE, cpu.STOP, count=4000)
    finally:
        cpu.uc.hook_del(handle)
    alias = cpu.text(buf) if seen.get("at") == 0x62A37 else None
    return dict(exit=EXITS.get(seen.get("at"), "none"), category=category, franchise_key=key, alias=alias)


def resolve_moment(cpu, display_row: int, record_fields) -> dict:
    """Everything the book decision depends on for one menu row (zero-based display row)."""
    cpu.events.clear()
    cpu.select(display_row)
    physical = cpu.r(0xBF1858)
    record = cpu.run(0x20C6F0)
    fields = record_fields(cpu, record)
    cpu.match()
    out = dict(display_row=display_row + 1, physical_row=physical + 1, title=fields["title"], date=fields["date"],
               user_side=fields["user_side"], situ_season_words=dict(away=cpu.r(record + 0x1C), home=cpu.r(record + 0x20)),
               away=resolve_side(cpu, False), home=resolve_side(cpu, True))
    cpu.run(0x20C3C0)
    return out
