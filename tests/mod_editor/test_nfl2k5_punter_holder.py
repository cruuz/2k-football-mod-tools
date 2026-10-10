"""Punter holds on FG/PAT (B77 H1): shape, retail round trip, cave rules, and the real depth-chart builder under Unicorn.

Shape tests need nothing; the retail tests read the extracted default.xbe; the emulation tests run the game's own
depth-chart constructor (0xE80D0 -> FUN_000e7c50) on the real image bytes with synthetic rosters, once on the retail
bytes and once on the patched bytes, and compare the finished chart."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import random
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.core import nfl2k5_punter_holder as ph  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
BASE = 0x10000
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
HOLDER_LIST, PUNTER_LIST, KICKER_LIST = 25, 23, 24     # chart lists of kinds H (3), P (1), K (2)


class ShapeTests(unittest.TestCase):
    def test_the_hook_is_a_jump_to_the_cave_over_the_two_displaced_instructions(self) -> None:
        self.assertEqual(ph.RETAIL_HOOK, bytes.fromhex("8b45008a9894010000"))      # mov eax,[ebp] ; mov bl,[eax+0x194]
        self.assertEqual(len(ph.PATCHED_HOOK), ph.HOOK_SIZE)
        self.assertEqual(ph.PATCHED_HOOK[0], 0xE9)
        self.assertEqual(ph.HOOK_VA + 5 + struct.unpack("<i", ph.PATCHED_HOOK[1:5])[0], ph.CAVE_VA)
        self.assertEqual(ph.PATCHED_HOOK[5:], b"\x90" * 4)
        self.assertEqual(ph.RESUME_VA, ph.HOOK_VA + ph.HOOK_SIZE)

    def test_the_cave_fits_the_dead_routine_and_is_int3_padded(self) -> None:
        self.assertEqual(ph.CAVE_SIZE, 0x30)
        self.assertEqual(ph.CAVE_VA + ph.CAVE_SIZE, ph.NEXT_ROUTINE_VA)
        self.assertLessEqual(ph.CODE_SIZE, ph.CAVE_SIZE)
        body = ph.cave_bytes()
        self.assertEqual(len(body), ph.CAVE_SIZE)
        self.assertEqual(body[: ph.CODE_SIZE], ph.CODE)
        self.assertEqual(body[ph.CODE_SIZE:], b"\xcc" * (ph.CAVE_SIZE - ph.CODE_SIZE))
        for label, _va, before, after in ph.sites():
            self.assertEqual(len(before), len(after), label)

    def test_local_array_offsets_follow_the_builders_kind_stride(self) -> None:
        # [esp + 0x48 + kind * 0x90]: kinds 1 (P), 2 (K), 3 (H)
        self.assertEqual((ph.LOCAL_PUNTER, ph.LOCAL_KICKER, ph.LOCAL_HOLDER), (0xD8, 0x168, 0x1F8))

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_the_cave_reads_the_local_lists_and_writes_only_the_holder_cell(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        insns = list(md.disasm(ph.CODE, ph.CAVE_VA))
        text = [f"{i.mnemonic} {i.op_str}".strip() for i in insns]
        self.assertEqual(text, [
            "mov bl, byte ptr [esp + 0xd8]", "cmp bl, 0xff", f"je 0x{ph.CAVE_LABELS['retail']:x}",
            "cmp bl, byte ptr [esp + 0x168]", f"je 0x{ph.CAVE_LABELS['retail']:x}",
            "mov byte ptr [esp + 0x1f8], bl", f"jmp 0x{ph.STORE_DONE_VA:x}",
            "mov eax, dword ptr [ebp]", "mov bl, byte ptr [eax + 0x194]", f"jmp 0x{ph.RESUME_VA:x}"])
        self.assertEqual(sum(i.size for i in insns), ph.CODE_SIZE)
        # the only memory write is the holder cell on the builder's own frame
        writes = [t for t in text if t.startswith("mov byte ptr [")]
        self.assertEqual(writes, ["mov byte ptr [esp + 0x1f8], bl"])

    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(ph.status(b"XBEH" + b"\0" * 0x200), "foreign")
        with self.assertRaises(ph.PunterHolderError):
            ph.apply(b"XBEH" + b"\0" * 0x200)

    def test_build_plan_and_presets(self) -> None:
        from mod_editor.core import mod_build
        self.assertTrue(mod_build.BuildPlan(source="s", target="t", punter_holder=True).wants_xbe_patch())
        self.assertFalse(mod_build.BuildPlan(source="s", target="t").punter_holder)
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["punter_holder"])
        self.assertTrue(mod_build.PRESETS["softdrink_advanced"]["punter_holder"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["punter_holder"])
        self.assertTrue(mod_build.availability()["punter_holder"])
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("punter_holder", settings.FEATURE_KEYS)


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = ph.apply(cls.retail)

    def _off(self, va: int) -> int:
        return ph._offset(self.retail, va)

    def test_retail_is_retail_and_the_patch_is_idempotent(self) -> None:
        self.assertEqual(ph.status(self.retail), "retail")
        self.assertEqual(ph.status(self.patched), "applied")
        again, receipt = ph.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])

    def test_only_the_hook_the_cave_and_the_text_digest_change(self) -> None:
        hook, cave = self._off(ph.HOOK_VA), self._off(ph.CAVE_VA)
        text = next(s for s in _sections(self.retail) if s.index == 0)
        digest = text.header_offset + 36
        spans = [(hook, ph.HOOK_SIZE), (cave, ph.CAVE_SIZE), (digest, 20)]
        restored = bytearray(self.patched)
        for off, size in spans:
            restored[off: off + size] = self.retail[off: off + size]
        self.assertEqual(bytes(restored), self.retail)
        self.assertEqual(len(self.patched), len(self.retail))
        for s in _sections(self.patched):
            self.assertEqual(self.patched[s.header_offset + 36: s.header_offset + 56], section_digest(self.patched, s), s.index)
        self.assertEqual(self.receipt["sections_repinned"], [0])

    def test_foreign_bytes_are_refused(self) -> None:
        for va in (ph.HOOK_VA, ph.CAVE_VA, ph.TAIL_VA):
            off = self._off(va)
            broken = bytearray(self.retail)
            broken[off] ^= 0xFF
            self.assertEqual(ph.status(bytes(broken)), "foreign", hex(va))
            with self.assertRaises(ph.PunterHolderError):
                ph.apply(bytes(broken))
        half = bytearray(self.retail)                    # hook applied, cave still retail
        off = self._off(ph.HOOK_VA)
        half[off: off + ph.HOOK_SIZE] = ph.PATCHED_HOOK
        self.assertEqual(ph.status(bytes(half)), "foreign")

    # -- cave rules ---------------------------------------------------------------------------------
    def _references_into(self, lo: int, hi: int) -> list:
        """The scan of tests/mod_editor/test_xbe_patch_cave_references.py, bytewise and a little wider: every
        rel32 call/jump, every rel8 jump/loop, every .text immediate and every .rdata/.data dword that lands in
        [lo, hi)."""

        data = self.retail
        text = next(s for s in _sections(data) if s.index == 0)
        text_lo, text_hi = text.virtual_address, text.virtual_address + text.raw_size
        hits = []
        for off in range(text_lo - BASE, text_hi - BASE - 6):
            op = data[off]
            tgt = None
            if op in (0xE8, 0xE9):
                tgt = BASE + off + 5 + struct.unpack_from("<i", data, off + 1)[0]
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                tgt = BASE + off + 6 + struct.unpack_from("<i", data, off + 2)[0]
            elif op == 0xEB or 0x70 <= op <= 0x7F or 0xE0 <= op <= 0xE3:
                tgt = BASE + off + 2 + struct.unpack_from("<b", data, off + 1)[0]
            if tgt is not None and lo <= tgt < hi:
                hits.append(("rel", hex(BASE + off), hex(tgt)))
        for section in _sections(data):
            if section.index not in (0, 12, 13):
                continue
            step = 1 if section.index == 0 else 4
            raw, size = section.raw_offset, section.raw_size
            for off in range(raw, raw + size - 4, step):
                v = struct.unpack_from("<I", data, off)[0]
                if lo <= v < hi:
                    hits.append(("ptr", section.index, hex(off), hex(v)))
        return hits

    def test_the_cave_host_is_unreferenced_in_the_retail_image(self) -> None:
        """No reference lands on any byte of the dead vec4-subtract routine or its pad (0x24B10..0x24B3F)."""

        self.assertEqual(self._references_into(ph.CAVE_VA, ph.NEXT_ROUTINE_VA), [])
        # the routine is 34 bytes ending in `ret`, then 14 nops, then the next dead routine
        self.assertEqual(self.retail[self._off(0x24B31): self._off(0x24B32)], b"\xc3")
        self.assertEqual(self.retail[self._off(0x24B32): self._off(0x24B40)], b"\x90" * 14)

    def test_the_hook_is_entered_only_at_its_first_byte(self) -> None:
        lo, hi = ph.HOOK_VA + 1, ph.RESUME_VA
        self.assertEqual(self._references_into(lo, hi), [])
        hits = self._references_into(ph.HOOK_VA, ph.HOOK_VA + 1)
        self.assertTrue(hits)       # the retail branches into the block (jle/je at 0xE7FD1, 0xE7FD3, ...)

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_the_retail_block_is_exactly_what_the_cave_replays_and_resumes_into(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        code = self.retail[self._off(ph.HOOK_VA): self._off(ph.HOOK_VA) + 0x40]
        text = [f"{i.address:x} {i.mnemonic} {i.op_str}" for i in md.disasm(code, ph.HOOK_VA)]
        self.assertEqual(text[0], "e8006 mov eax, dword ptr [ebp]")
        self.assertEqual(text[1], "e8009 mov bl, byte ptr [eax + 0x194]")
        self.assertEqual(text[2], "e800f cmp bl, 0xff")
        self.assertIn("e8030 mov byte ptr [esp + 0x1f8], bl", text)
        self.assertIn("e8037 test esi, esi", text)
        self.assertIn("e803b inc edi", text)
        self.assertEqual(self.retail[self._off(ph.TAIL_VA): self._off(ph.TAIL_VA) + len(ph.RETAIL_TAIL)], ph.RETAIL_TAIL)

    def test_the_holder_byte_has_no_other_gameplay_reader(self) -> None:
        """Every byte-wide access of team +0x194 in .text, decoded bytewise: only the accessors, copiers and
        roster-removal helpers listed here exist, and only 0xE8009 reads it for the depth chart."""

        text = next(s for s in _sections(self.retail) if s.index == 0)
        hits = []
        data = self.retail
        for off in range(text.raw_offset, text.raw_offset + text.raw_size - 7):
            # mov r8,[reg+disp32] (8A /r mod=10) and movsx/movzx r32,byte [reg+disp32] (0F BE/B6 /r mod=10)
            if data[off] == 0x8A and data[off + 1] & 0xC0 == 0x80 and data[off + 1] & 7 != 4 \
                    and struct.unpack_from("<I", data, off + 2)[0] == 0x194:
                hits.append(BASE + off)
            if data[off] == 0x0F and data[off + 1] in (0xBE, 0xB6) and data[off + 2] & 0xC0 == 0x80 \
                    and data[off + 2] & 7 != 4 and struct.unpack_from("<I", data, off + 3)[0] == 0x194:
                hits.append(BASE + off)
        self.assertIn(ph.HOOK_VA + 3, hits)
        self.assertEqual(sorted(hits), [0xBF2F0, 0xC13C4, 0xC3AE1, 0xC3B4A, 0xC3D78, 0xC9D80, 0xE7410, 0xE8009])


@unittest.skipUnless(XBE.is_file() and HAVE_UNICORN, "retail extraction or unicorn not present")
class BuilderEmulationTests(unittest.TestCase):
    """The game's own chart builder on synthetic rosters (the finished chart is the observable)."""

    STACK = 0x7FF00000
    SCRATCH = 0x0BAD0000
    TEAM = SCRATCH
    PLAYERS = SCRATCH + 0x1000
    CHART = SCRATCH + 0x8000
    RET = SCRATCH + 0x10000

    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched = ph.apply(cls.retail)[0]

    def _machine(self, payload: bytes):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(BASE, 0xEC0000 - BASE)
        uc.mem_write(BASE, payload[: struct.unpack_from("<I", payload, 0x108)[0]])
        for s in _sections(payload):
            if s.virtual_address + s.raw_size <= 0xEC0000:
                uc.mem_write(s.virtual_address, payload[s.raw_offset: s.raw_offset + s.raw_size])
        uc.mem_map(self.STACK - 0x100000, 0x200000)
        uc.mem_map(self.SCRATCH, 0x20000)
        uc.mem_write(self.RET, b"\xf4")
        return uc

    def _build(self, payload: bytes, roster, holder_byte: int, *, unit: int = 0, flag: int = 0):
        """Run 0xE80D0 (chart constructor -> FUN_000e7c50). roster = [(position name, rank, squad)]."""
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP

        uc = self._machine(payload)
        for i, (pos, rank, squad) in enumerate(roster):
            a = self.PLAYERS + i * 0x54
            uc.mem_write(self.TEAM + i * 4, struct.pack("<I", a))
            uc.mem_write(a + 0x24, struct.pack("<I", squad << 28))
            uc.mem_write(a + 0x28, struct.pack("<H", rank << 10))
            uc.mem_write(a + 0x35, bytes([POSITIONS.index(pos)]))
        uc.mem_write(self.TEAM + 0x11C, bytes([len(roster)]))
        uc.mem_write(self.TEAM + 0x194, bytes([holder_byte & 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]))
        esp = self.STACK - 0x1000
        uc.mem_write(esp, struct.pack("<III", self.RET, unit, flag))
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.reg_write(UC_X86_REG_ECX, self.TEAM)
        uc.reg_write(UC_X86_REG_EDX, self.CHART)
        uc.emu_start(0xE80D0, self.RET, count=3_000_000)
        pointers = [struct.unpack("<I", bytes(uc.mem_read(self.CHART + 0x9C + 4 * n, 4)))[0] for n in range(28)]
        chart = bytes(uc.mem_read(self.CHART, 0x334))
        return uc, pointers, chart

    def _lists(self, pointers, chart: bytes, skip=()) -> dict:
        """List n of the finished chart as bytes (to the next list's start); lists are packed, so a list that gains
        or loses an entry moves every later pointer, which is not a change of any other list."""
        out = {}
        for n in range(27):
            if n not in skip:
                out[n] = chart[pointers[n] - self.CHART: pointers[n + 1] - self.CHART]
        out[27] = chart[pointers[27] - self.CHART: pointers[27] - self.CHART + 2]
        return out

    def _row0(self, uc, pointers, lst: int) -> int:
        if lst < 27 and pointers[lst] == pointers[lst + 1]:          # packed lists: an empty list has no first byte
            return 0xFF
        return bytes(uc.mem_read(pointers[lst], 1))[0]

    def _formation_player(self, uc, list_index: int) -> int:
        """FUN_000e7810 with no mapping object: the player pointer behind (list, row 0), as the line-up code reads it."""
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

        esp = self.STACK - 0x3000
        uc.mem_write(esp, struct.pack("<III", self.RET, self.CHART, 0))
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.reg_write(UC_X86_REG_EAX, list_index)
        uc.reg_write(UC_X86_REG_ECX, 0)
        uc.emu_start(0xE7810, self.RET, count=100_000)
        return uc.reg_read(UC_X86_REG_EAX)

    ROSTER = [("QB", 0, 0), ("QB", 1, 0), ("K", 0, 0), ("P", 0, 0), ("P", 1, 0), ("WR", 0, 0), ("WR", 1, 0), ("RB", 0, 0)]

    def test_retail_holder_is_the_team_record_byte_and_patched_holder_is_the_first_punter(self) -> None:
        uc, ptr, _ = self._build(self.retail, self.ROSTER, holder_byte=1)
        self.assertEqual(self._row0(uc, ptr, HOLDER_LIST), 1)                      # the second quarterback
        uc, ptr, _ = self._build(self.patched, self.ROSTER, holder_byte=1)
        self.assertEqual(self._row0(uc, ptr, HOLDER_LIST), 3)                      # punter rank 0
        self.assertEqual(self._row0(uc, ptr, PUNTER_LIST), 3)                      # he is still the punter
        self.assertEqual(self._formation_player(uc, HOLDER_LIST), self.PLAYERS + 3 * 0x54)

    def test_the_depth_chart_rank_decides_not_the_roster_order(self) -> None:
        roster = [("QB", 0, 0), ("QB", 1, 0), ("K", 0, 0), ("P", 1, 0), ("P", 0, 0)]    # slot 4 is P1
        uc, ptr, _ = self._build(self.patched, roster, holder_byte=1)
        self.assertEqual(self._row0(uc, ptr, HOLDER_LIST), 4)
        roster = [("QB", 0, 0), ("QB", 1, 0), ("K", 0, 0), ("P", 0, 0), ("P", 1, 0)]
        uc, ptr, _ = self._build(self.patched, roster, holder_byte=1)
        self.assertEqual(self._row0(uc, ptr, HOLDER_LIST), 3)

    def test_without_a_punter_the_retail_rule_runs_unchanged(self) -> None:
        roster = [("QB", 0, 0), ("QB", 1, 0), ("K", 0, 0), ("WR", 0, 0)]
        before = self._build(self.retail, roster, holder_byte=1)
        after = self._build(self.patched, roster, holder_byte=1)
        self.assertEqual(self._row0(after[0], after[1], HOLDER_LIST), 1)
        self.assertEqual(after[2], before[2])                                       # the whole chart is identical
        # a stale holder byte (null player) is ignored exactly as in retail
        before = self._build(self.retail, roster, holder_byte=40)
        after = self._build(self.patched, roster, holder_byte=40)
        self.assertEqual(self._row0(after[0], after[1], HOLDER_LIST), 0xFF)
        self.assertEqual(after[2], before[2])

    def test_a_missing_holder_byte_is_filled_by_the_punter(self) -> None:
        uc, ptr, _ = self._build(self.retail, self.ROSTER, holder_byte=0xFF)
        self.assertEqual(self._row0(uc, ptr, HOLDER_LIST), 0xFF)
        uc, ptr, _ = self._build(self.patched, self.ROSTER, holder_byte=0xFF)
        self.assertEqual(self._row0(uc, ptr, HOLDER_LIST), 3)

    def test_the_only_chart_byte_that_changes_is_the_holder_cell(self) -> None:
        for flag in (0, 1):
            ub, pb, cb = self._build(self.retail, self.ROSTER, holder_byte=1, flag=flag)
            ua, pa, ca = self._build(self.patched, self.ROSTER, holder_byte=1, flag=flag)
            cell = pa[HOLDER_LIST] - self.CHART
            diff = [i for i in range(len(cb)) if cb[i] != ca[i]]
            self.assertEqual(diff, [cell], f"flag {flag}")
            self.assertEqual(ca[cell], 3)

    def test_random_rosters_change_only_the_holder_cell_and_only_to_the_first_punter(self) -> None:
        rng = random.Random(77)
        names = [p for p in POSITIONS if p not in ("K", "P")]
        for trial in range(40):
            n = rng.randint(6, 28)
            roster = [(rng.choice(names), rng.randint(0, 3), rng.choice((0, 0, 0, 1))) for _ in range(n)]
            roster[rng.randrange(n)] = ("K", 0, 0)
            punters = rng.randint(0, 2)
            for k in range(punters):
                roster[rng.randrange(n)] = ("P", k, rng.choice((0, 0, 1)))
            holder = rng.choice((rng.randrange(n), 0xFF, 40))
            ub, pb, cb = self._build(self.retail, roster, holder_byte=holder)
            ua, pa, ca = self._build(self.patched, roster, holder_byte=holder)
            first_punter = self._row0(ua, pa, PUNTER_LIST)
            kicker = self._row0(ua, pa, KICKER_LIST)
            new_holder = self._row0(ua, pa, HOLDER_LIST)
            if first_punter != 0xFF and first_punter != kicker:
                self.assertEqual(new_holder, first_punter, trial)
            else:
                self.assertEqual(new_holder, self._row0(ub, pb, HOLDER_LIST), trial)
            self.assertEqual(self._lists(pa, ca, skip=(HOLDER_LIST,)), self._lists(pb, cb, skip=(HOLDER_LIST,)), trial)

    def test_the_kicker_is_never_also_the_holder(self) -> None:
        """Run the hook with a frame whose punter and kicker rows name the same man: the cave must fall back."""
        from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_EIP, UC_X86_REG_ESP

        for punter, kicker, expect_store in ((5, 5, False), (5, 6, True), (0xFF, 6, False)):
            uc = self._machine(self.patched)
            esp = self.STACK - 0x4000
            frame = bytearray(b"\xa5" * 0x300)
            frame[ph.LOCAL_PUNTER] = punter
            frame[ph.LOCAL_KICKER] = kicker
            frame[ph.LOCAL_HOLDER] = 0xFF
            uc.mem_write(esp, bytes(frame))
            chart = self.CHART
            uc.mem_write(chart, struct.pack("<I", self.TEAM))                  # [ebp] = team
            uc.mem_write(self.TEAM + 0x194, bytes([2]))                        # retail holder byte: roster slot 2
            uc.mem_write(self.TEAM + 2 * 4, struct.pack("<I", 0))              # ...which is a null player: retail skips it
            uc.reg_write(UC_X86_REG_ESP, esp)
            uc.reg_write(UC_X86_REG_EBP, chart)
            uc.reg_write(UC_X86_REG_EBX, 0xB0B0B0B0)
            uc.reg_write(UC_X86_REG_EIP, ph.HOOK_VA)
            stops = ph.STORE_DONE_VA
            uc.emu_start(ph.HOOK_VA, stops, count=1000)
            stored = bytes(uc.mem_read(esp + ph.LOCAL_HOLDER, 1))[0]
            if expect_store:
                self.assertEqual(stored, punter)
                self.assertEqual(uc.reg_read(UC_X86_REG_EIP), ph.STORE_DONE_VA)
            else:
                self.assertEqual(stored, 0xFF)       # the retail rule found a null player and stored nothing


if __name__ == "__main__":
    unittest.main()
