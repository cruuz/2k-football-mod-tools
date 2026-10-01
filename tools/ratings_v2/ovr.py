"""The game's own OVERALL for a 0x54 roster record: FUN_00246d80 / the display routine FUN_00246d90 of the retail
USA default.xbe, executed natively under Unicorn (the whole image mapped at its virtual addresses). PROVED OFFLINE:
it is the routine every roster screen calls (job b75-t1 decoded it; job r1 extended the decode to all 17 positions).
Needs the user's retail default.xbe; nothing from it is stored."""
from __future__ import annotations

import struct
from pathlib import Path

from common import CFG
from mod_editor.core.nfl2k5_bump_strength import _sections

PAGE = 0x1000
DISPLAY_VA = 0x00246D90
OVERALL_VA = 0x00246D80


class OvrEmu:
    STACK = 0x0F000000
    REC = 0x0E000000
    RET = 0x0D000000

    def __init__(self, xbe_path=None):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        data = Path(xbe_path or Path(CFG["retail"]) / "default.xbe").read_bytes()
        secs = _sections(data)
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        spans = []
        for s in secs:
            vsize = struct.unpack_from("<I", data, s.header_offset + 8)[0]
            lo = s.virtual_address & ~(PAGE - 1)
            hi = (s.virtual_address + max(vsize, s.raw_size) + PAGE - 1) & ~(PAGE - 1)
            spans.append((lo, hi))
        merged = []
        for lo, hi in sorted(spans):
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
            else:
                merged.append((lo, hi))
        for lo, hi in merged:
            mu.mem_map(lo, hi - lo)
        for s in secs:
            mu.mem_write(s.virtual_address, data[s.raw_offset:s.raw_offset + s.raw_size])
        mu.mem_map(self.STACK - 0x10000, 0x20000)
        mu.mem_map(self.REC, PAGE)
        mu.mem_map(self.RET, PAGE)
        mu.mem_write(self.RET, b"\xf4")
        self.mu = mu

    def _call(self, va, record, mode):
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EDX
        mu = self.mu
        mu.mem_write(self.REC, bytes(record[:0x54]).ljust(0x54, b"\0"))
        sp = self.STACK - 4
        mu.mem_write(sp, struct.pack("<I", self.RET))
        mu.reg_write(UC_X86_REG_ESP, sp)
        mu.reg_write(UC_X86_REG_ECX, self.REC)
        mu.reg_write(UC_X86_REG_EDX, mode)
        mu.emu_start(va, self.RET, count=200000)

    def overall01(self, record: bytes, mode: int = 0) -> float:
        self._call(OVERALL_VA, record, mode)
        stub = self.RET + 0x100
        self.mu.mem_write(stub, b"\xd9\x1d" + struct.pack("<I", self.RET + 0x800) + b"\xf4")   # fstp [x]; hlt
        self.mu.emu_start(stub, stub + 6, count=10)
        return struct.unpack("<f", self.mu.mem_read(self.RET + 0x800, 4))[0]

    def display(self, record: bytes, mode: int = 0) -> int:
        from unicorn.x86_const import UC_X86_REG_EAX
        self._call(DISPLAY_VA, record, mode)
        v = self.mu.reg_read(UC_X86_REG_EAX)
        return v - (1 << 32) if v & 0x80000000 else v


_EMU = None


def game_ovr(record_bytes: bytes, body_terms: bool = False) -> tuple[int, float]:
    """(display integer, unrounded 0..1). body_terms=False runs the routine on a copy whose weight byte (+0x2A) is 0
    (150 lb) and height (+0x2B) 60 in: below every Href/Wref of the 15 composites, so the formula's size bonus
    (0.001 per lb over 220-300, 0.005 per inch over 70-75) is off and nothing else changes."""
    global _EMU
    if _EMU is None:
        _EMU = OvrEmu()
    rec = bytearray(record_bytes)
    if not body_terms:
        rec[0x2A] = 0
        rec[0x2B] = 60
    return _EMU.display(bytes(rec)), _EMU.overall01(bytes(rec))
