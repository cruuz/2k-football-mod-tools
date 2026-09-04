"""No executable patch may write into a read-only section of default.xbe.

The Xbox kernel maps XBE sections with their header flags: .text (0x16) is read-only, .rdata and
.data (0x7) are writable. A cave that keeps a variable inside .text faults the first time it is
written; the 7-on-7 practice type did exactly that and froze the game when the Scrimmage screen
opened (2026-09-03). This test parses the section table, applies every XBE patch the studio ships to
the retail executable, disassembles the changed code, and checks every absolute memory write."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

try:
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs
    from capstone.x86 import X86_OP_MEM
except Exception:  # noqa: BLE001
    Cs = None

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
BASE = 0x10000
WRITING = {"mov", "movzx", "or", "and", "add", "sub", "xor", "inc", "dec", "not", "neg", "movsb", "movsd", "stosb", "stosd", "push", "pop", "xchg", "adc", "sbb", "shl", "shr", "sal", "sar", "bts", "btr", "btc", "cmpxchg", "setne", "sete", "setg", "setl"}


def sections(xbe: bytes) -> list[tuple[str, int, int, bool]]:
    base = struct.unpack_from("<I", xbe, 0x104)[0]
    count = struct.unpack_from("<I", xbe, 0x11C)[0]
    header = struct.unpack_from("<I", xbe, 0x120)[0] - base
    out = []
    for i in range(count):
        flags, vaddr, vsize, _raw, _rawsize, name_addr = struct.unpack_from("<IIIIII", xbe, header + i * 0x38)
        name = xbe[name_addr - base: name_addr - base + 16].split(b"\0")[0].decode("ascii", "replace")
        out.append((name, vaddr, vaddr + vsize, bool(flags & 1)))
    return out


def writable(table, va: int) -> bool | None:
    """True/False for a section byte; None for the alignment gaps between sections (writable when the
    neighbours on that page are)."""
    for _name, start, end, w in table:
        if start <= va < end:
            return w
    page = va & ~0xFFF
    neighbours = [w for _n, start, end, w in table if start < page + 0x1000 and end > page]
    return all(neighbours) if neighbours else None


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class SectionTableTests(unittest.TestCase):
    def test_text_is_read_only_and_the_data_sections_are_writable(self) -> None:
        table = sections(XBE.read_bytes())
        names = {name: w for name, _s, _e, w in table}
        self.assertFalse(names[".text"])
        self.assertTrue(names[".rdata"])
        self.assertTrue(names[".data"])

    def test_the_uniform_flip_words_live_in_writable_memory(self) -> None:
        from mod_editor.core import nfl2k5_uniform_choice as uniform
        table = sections(XBE.read_bytes())
        for va in (uniform.HOME_FLIP_VA, uniform.AWAY_FLIP_VA, uniform.AWAY_VALUE_VA):
            self.assertTrue(writable(table, va), hex(va))
        for va in (uniform.RULE_BLOCK_VA, uniform.HOME_PREV_VA, uniform.RESET_TAIL_VA):
            self.assertFalse(writable(table, va), hex(va))

    def test_the_seven_on_seven_flag_lives_in_writable_memory(self) -> None:
        from mod_editor.core import nfl2k5_seven_on_seven as seven
        table = sections(XBE.read_bytes())
        self.assertTrue(writable(table, seven.FLAG_VA), hex(seven.FLAG_VA))
        # the cave itself is code and constants in .text: nothing may write there
        self.assertFalse(writable(table, seven.CAVE_VA))


@unittest.skipUnless(XBE.is_file() and Cs is not None, "retail extraction or capstone not present")
class PatchWriteTests(unittest.TestCase):
    """Every absolute memory write in every patch's changed code targets writable memory."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_throw_tuning as tt
        cls.retail = XBE.read_bytes()
        cls.table = sections(cls.retail)
        flags = {name: True for name in ("catch_slider", "accel_ramp", "draft_ai", "edge_rename", "returner_fix", "progression",
                                          "scheme_labels", "camera", "kick_rules", "widescreen", "overtime", "team_column", "seven_on_seven")}
        cls.patched, cls.receipt = tt._apply_all(cls.retail, None, **flags, arc_table=False, kick_power=False, penalties="nfl", uniform_choice="choice", kick_laces=True, prospect_names="modern", player_star=True)
        cls.md = Cs(CS_ARCH_X86, CS_MODE_32)
        cls.md.detail = True

    def _changed_ranges(self) -> list[tuple[int, int]]:
        text = next(s for s in self.table if s[0] == ".text")
        ranges: list[tuple[int, int]] = []
        start = None
        for off in range(text[1] - BASE, text[2] - BASE):
            if self.retail[off] != self.patched[off]:
                if start is None:
                    start = off
            elif start is not None:
                ranges.append((start, off))
                start = None
        if start is not None:
            ranges.append((start, text[2] - BASE))
        # merge neighbours closer than 64 bytes so an instruction straddling an unchanged byte is kept whole
        merged: list[list[int]] = []
        for a, b in ranges:
            if merged and a - merged[-1][1] < 64:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        return [(a - 16, b + 16) for a, b in merged]

    def test_every_absolute_write_in_changed_code_targets_writable_memory(self) -> None:
        offenders = []
        checked = 0
        for a, b in self._changed_ranges():
            for insn in self.md.disasm(self.patched[a:b], a + BASE):
                if insn.mnemonic not in WRITING or not insn.operands:
                    continue
                dest = insn.operands[0]
                if dest.type != X86_OP_MEM or dest.mem.base != 0 or dest.mem.index != 0:
                    continue
                target = dest.mem.disp & 0xFFFFFFFF
                if not (BASE <= target < 0x1000000):
                    continue
                checked += 1
                if not writable(self.table, target):
                    offenders.append(f"{insn.address:#x}: {insn.mnemonic} {insn.op_str}")
        self.assertGreater(checked, 0, "no absolute writes found; the scan is broken")
        self.assertEqual(offenders, [], "writes into read-only sections:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
