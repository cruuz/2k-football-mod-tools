"""The template-driven preseason must be well-formed, pattern-checked, disjoint from every other
patch, and -- where the retail executable and unicorn are available -- run for real.

Static: the rewritten generator decodes completely (capstone), every call hits an intended retail
helper, every branch lands on an instruction start, the region is unreferenced except at its entry,
the sites do not overlap any other season-length group or any other module's cave, and the retail
bytes are pinned against the real default.xbe.

Emulated (unicorn): the rewritten FUN_002bec20 runs on the patched real code with the retail grid
helpers, date helpers and pool lookups native (only the two team/marquee helpers stubbed): season 0
copies the 2026 template into rows 0..3 verbatim, seasons 1/2/4 re-date it from Thanksgiving - 119
days, a missing or oversized block leaves the preseason empty, an over-full week is capped at 17
slots, and the retail regular-season generator run straight after it lands the 2026 template in
rows 0..17 with rows 18..21 untouched (the preseason rows never shift the regular season).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_preseason as pre  # noqa: E402
from mod_editor.core import nfl2k5_season_length as season  # noqa: E402
import nfl2k5_franchise_schedule as fs  # noqa: E402

RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
SCHEDULE_JSON = ROOT / "data" / "nfl_2026_schedule.json"
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None

GRID_VA = 0xE57C40
FLAGS_VA = 0xE57954
SCORES_VA = 0xE587F0
SEASON_INDEX_VA = 0xE576B8
CUR_WEEK_VA = 0xE576B4
REGULAR_GENERATOR_VA = 0x2BF270
STACK_VA = 0x7F000000
POOL_VA = 0x02000000
SENTINEL = 0x7FFF0000
GRID_ROWS, GRID_SLOTS = 22, 17

HELPERS = {pre.FN_RESET_GRID, pre.FN_SET_WEEK, pre.FN_SET_SLOT, pre.FN_MARQUEE_RESET, pre.FN_TEAM_LOOKUP,
           pre.FN_SEASON_INDEX, pre.FN_DAY_NUMBER, pre.FN_WEEKDAY, pre.FN_ADD_DAYS, pre.FN_SUB_DAYS, pre.FN_MEMCPY,
           pre.FN_FLAG_A, pre.FN_FLAG_B, pre.FN_WRITE_RECORD, pre.FN_SCORE_HOME, pre.FN_SCORE_AWAY}


def _thanksgiving(year: int) -> dt.date:
    first = dt.date(year, 11, 1)
    return first + dt.timedelta(days=(3 - first.weekday()) % 7 + 21)


def _synthetic_block(games_per_week: tuple[int, ...] = (1, 16, 16, 16), year: int = 2026) -> bytes:
    """A block with the given number of games per week (teams cycle; shape only)."""
    hof = dt.date(year, 8, 6)
    blob = bytearray()
    for week, count in enumerate(games_per_week):
        for slot in range(count):
            home, away = (slot * 2) % 32, (slot * 2 + 1) % 32
            blob += fs.encode_record(home, away, hof + dt.timedelta(days=7 * week + slot % 3), 7, 30, kind=week)
    total = len(blob) // 8
    return struct.pack("<I", (pre.PRESEASON_TAG << 16) | total) + bytes(blob)


class StaticTests(unittest.TestCase):
    def test_sites_are_well_formed(self) -> None:
        sites = pre.sites()
        self.assertEqual([s.label for s in sites], ["preseason_generator", "stage_preseason_weeks", "stage_preseason_prep"])
        for site in sites:
            self.assertEqual(len(site.retail), len(site.patched), site.label)
            self.assertNotEqual(site.retail, site.patched, site.label)
        gen = sites[0]
        self.assertEqual((gen.va, gen.size), (0x2BEC20, 0x590))
        self.assertEqual(gen.retail[:4], b"\x55\x8b\xec\x83")                       # retail prologue
        self.assertEqual(gen.retail[0x569:0x56A], b"\xc3")                          # retail ret at 0x2BF189
        code, labels = pre.generator_code()
        self.assertLess(len(code), 0x200)
        self.assertEqual(gen.patched[len(code):], b"\xcc" * (0x590 - len(code)))
        self.assertEqual(labels["entry"], 0x2BEC20)
        self.assertEqual(sites[1].va, 0x5151B4)
        self.assertEqual((sites[1].retail, sites[1].patched), (b"\x05", b"\x04"))
        self.assertEqual((sites[2].retail, sites[2].patched), (b"\x05", b"\x04"))
        self.assertEqual(pre.code_report()["preseason_weeks"], 4)

    def test_sites_do_not_overlap_other_patches(self) -> None:
        mine = [(s.va, s.va + s.size, s.label) for s in pre.sites()]
        mine += [(s.va, s.va + s.size, s.label) for s in season.year_sites(2026)]
        spans = list(mine)
        for group in ("calendar", "season_length", "playoffs_14"):
            spans += [(s.va, s.va + s.size, f"{group}:{s.label}") for s in season.group_sites(group)]
        spans.sort()
        for (a0, a1, la), (b0, _b1, lb) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0, f"{la} overlaps {lb}")
        # every other module's named virtual addresses stay outside the rewritten regions
        regions = [(lo, hi) for lo, hi, _ in mine if hi - lo > 1]
        for name in ("nfl2k5_overtime", "nfl2k5_kick_rules", "nfl2k5_draft_ai", "nfl2k5_returner_fix",
                     "nfl2k5_position_pools", "nfl2k5_progression", "nfl2k5_camera", "nfl2k5_hud_layout",
                     "nfl2k5_widescreen", "nfl2k5_edge_rename", "nfl2k5_modern_positions", "nfl2k5_catch_slider",
                     "nfl2k5_accel_ramp", "nfl2k5_playoffs14", "nfl2k5_kickoff_alignment"):
            try:
                module = importlib.import_module(f"mod_editor.core.{name}")
            except Exception:  # noqa: BLE001 - other work streams may not have landed the module
                continue
            for attr, value in vars(module).items():
                if isinstance(value, int) and not isinstance(value, bool) and attr.upper() == attr and "VA" in attr:
                    for lo, hi in regions:
                        self.assertFalse(lo <= value < hi, f"{name}.{attr}=0x{value:x} inside 0x{lo:x}..0x{hi:x}")

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone needed")
    def test_generator_decodes_and_targets_the_retail_helpers(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        code, labels = pre.generator_code()
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        insns = list(md.disasm(code, pre.GENERATOR_VA))
        starts = {i.address for i in insns}
        self.assertEqual(insns[-1].address + insns[-1].size, pre.GENERATOR_VA + len(code))
        self.assertEqual(insns[-1].mnemonic, "ret")
        calls = set()
        for ins in insns:
            if ins.mnemonic == "call":
                calls.add(int(ins.op_str, 16))
            elif ins.mnemonic.startswith("j"):
                target = int(ins.op_str, 16)
                self.assertIn(target, starts, f"{ins.mnemonic} at {ins.address:#x} lands mid-instruction")
        self.assertEqual(calls, HELPERS)
        self.assertEqual(set(labels) >= {"loop", "done", "write", "scores", "next"}, True)
        # the DOB formatter (year group) decodes to a single ret at its end too
        dob = season.dob_formatter_bytes(2026)
        dob_insns = list(md.disasm(dob, season.DOB_FORMATTER_VA))
        self.assertEqual([i.mnemonic for i in dob_insns if i.mnemonic == "ret"], ["ret"])
        self.assertEqual(dob_insns[-1].mnemonic, "nop")


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail default.xbe not present")
class RetailSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()
        cls.sections = strength._sections(cls.retail)

    def _off(self, va: int) -> int:
        for s in self.sections:
            if s.virtual_address <= va < s.virtual_address + s.raw_size:
                return s.raw_offset + (va - s.virtual_address)
        raise AssertionError(hex(va))

    def test_sites_are_retail_and_apply_repins_text_and_rdata(self) -> None:
        for site in pre.sites():
            off = self._off(site.va)
            self.assertEqual(self.retail[off: off + site.size], site.retail, site.label)
        self.assertEqual(season.group_status(self.retail, "preseason"), "retail")
        patched, receipt = season.apply(self.retail, groups=("preseason",))
        self.assertEqual(season.group_status(patched, "preseason"), "applied")
        self.assertEqual(receipt["preseason_games"], 3)
        self.assertEqual(receipt["sections_repinned"], [0, 12])
        for s in strength._sections(patched):
            if s.index in (0, 12):
                self.assertEqual(strength.section_digest(patched, s), s.stored_digest)
        off = self._off(pre.GENERATOR_VA)
        self.assertEqual(patched[off: off + 0x590], pre.generator_bytes())
        self.assertEqual(patched[self._off(0x2BF1B0): self._off(0x2BF1B0) + 4], self.retail[self._off(0x2BF1B0): self._off(0x2BF1B0) + 4])

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone needed")
    def test_region_is_reached_only_through_its_entry(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        text = next(s for s in self.sections if s.index == 0)
        code = self.retail[text.raw_offset: text.raw_offset + text.raw_size]
        lo, hi = pre.GENERATOR_VA, pre.GENERATOR_VA + pre.GENERATOR_SIZE
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        into, entry_callers = [], []
        off = 0
        while off < len(code):                                   # linear sweep, one byte on undecodable
            got = 0
            for ins in md.disasm(code[off:], text.virtual_address + off):
                got += ins.size
                if (ins.mnemonic == "call" or ins.mnemonic.startswith("j")) and ins.op_str.startswith("0x"):
                    target = int(ins.op_str, 16)
                    if lo <= ins.address < hi:
                        continue
                    if lo < target < hi:
                        into.append((ins.address, target))
                    elif target == lo:
                        entry_callers.append(ins.address)
            off += got + 1
        self.assertEqual(into, [])
        self.assertIn(pre.GENERATOR_THUNK_VA, entry_callers)
        needle_hits = [va for va in range(lo + 1, hi, 4) if self.retail.find(struct.pack("<I", va)) >= 0]
        # the retail jump table inside the region points at its own switch cases; nothing else does
        self.assertTrue(all(0x2BEF85 <= va <= 0x2BEFAF for va in needle_hits), needle_hits)


@unittest.skipUnless(RETAIL_XBE.is_file() and HAVE_UNICORN and SCHEDULE_JSON.is_file(), "retail default.xbe, unicorn and the schedule JSON needed")
class EmulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()
        cls.patched, _ = season.apply(cls.retail)
        doc = json.loads(SCHEDULE_JSON.read_text())
        cls.template, _ = fs.encode_schedule(doc)
        cls.block, _ = fs.encode_preseason(doc)
        cls.records = fs.decode_records(cls.block, 4, 49)

    def _boot(self, season_index: int, block: bytes):
        from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESP

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0, 0x1000000)
        uc.mem_map(STACK_VA, 0x100000)
        uc.mem_map(POOL_VA, 0x100000)
        uc.mem_map(SENTINEL & ~0xFFF, 0x1000)
        for s in strength._sections(self.patched):
            if s.raw_size:
                uc.mem_write(s.virtual_address, self.patched[s.raw_offset: s.raw_offset + s.raw_size])
        uc.mem_write(SENTINEL, b"\xc3")
        uc.mem_write(SEASON_INDEX_VA, struct.pack("<I", season_index))
        # a resolved ROST pool: pair +0x28/+0x2C -> the regular template, the preseason block right after it
        uc.mem_write(POOL_VA + 0x28, struct.pack("<II", len(self.template) // 8, POOL_VA + 0x100))
        uc.mem_write(POOL_VA + 0x100, self.template + block)
        uc.mem_write(pre.POOL_POINTER_GLOBAL, struct.pack("<I", POOL_VA))

        def ret() -> None:
            esp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
            uc.reg_write(UC_X86_REG_ESP, esp + 4)

        def on_code(uc_, address, _size, _user):
            if address == pre.FN_MARQUEE_RESET:
                ret()
            elif address == pre.FN_TEAM_LOOKUP:
                uc.reg_write(UC_X86_REG_EAX, uc.reg_read(UC_X86_REG_EDI))
                ret()

        uc.hook_add(UC_HOOK_CODE, on_code)
        return uc

    @staticmethod
    def _run(uc, entry: int) -> None:
        from unicorn.x86_const import UC_X86_REG_ESP

        esp = STACK_VA + 0x80000
        uc.mem_write(esp, struct.pack("<I", SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.emu_start(entry, SENTINEL, count=5_000_000)

    @staticmethod
    def _record(uc, row: int, slot: int) -> bytes:
        return bytes(uc.mem_read(GRID_VA + (row * GRID_SLOTS + slot) * 8, 8))

    @staticmethod
    def _flags(uc, row: int, slot: int) -> tuple[int, int]:
        return tuple(uc.mem_read(FLAGS_VA + (row * GRID_SLOTS + slot) * 2, 2))

    def _rows(self, uc) -> list[list[bytes]]:
        out = []
        for row in range(GRID_ROWS):
            games = []
            for slot in range(GRID_SLOTS):
                rec = self._record(uc, row, slot)
                if rec[0] == 7:
                    break
                games.append(rec)
            out.append(games)
        return out

    def test_season_zero_copies_the_2026_preseason_verbatim(self) -> None:
        uc = self._boot(0, self.block)
        self._run(uc, pre.GENERATOR_VA)
        rows = self._rows(uc)
        self.assertEqual([len(r) for r in rows], [1, 16, 16, 16] + [0] * 18)
        expected = [[], [], [], []]
        for rec in self.records:
            raw = bytes([0, rec["home"], rec["away"], rec["month"], rec["day"], rec["year"] - 2000, rec["hour_field"], rec["minute_field"]])
            expected[rec["type"]].append(raw)
        self.assertEqual(rows[:4], expected)
        self.assertEqual(rows[0][0][1:3], bytes([7, 20]))                 # Cardinals host the Panthers
        for row in range(4):
            for slot in range(len(rows[row])):
                self.assertEqual(self._flags(uc, row, slot), (1, 1))
                self.assertEqual(bytes(uc.mem_read(SCORES_VA + (row * GRID_SLOTS + slot) * 10, 10)), bytes(10))
            self.assertEqual(self._flags(uc, row, len(rows[row])), (0, 0))
        self.assertEqual(struct.unpack("<I", uc.mem_read(CUR_WEEK_VA, 4))[0], 0)

    def test_later_seasons_are_re_dated_from_thanksgiving(self) -> None:
        for season_index in (1, 2, 4):
            year = 2026 + season_index
            anchor = _thanksgiving(year) - dt.timedelta(days=119)
            self.assertEqual(anchor.weekday(), 3)
            uc = self._boot(season_index, self.block)
            self._run(uc, pre.GENERATOR_VA)
            rows = self._rows(uc)
            self.assertEqual([len(r) for r in rows[:5]], [1, 16, 16, 16, 0])
            first = dt.date(2026, 8, 6)
            flat = [rec for row in rows[:4] for rec in row]
            self.assertEqual(len(flat), 49)
            for raw, rec in zip(flat, self.records):
                want = anchor + (dt.date(rec["year"], rec["month"], rec["day"]) - first)
                self.assertEqual((raw[3], raw[4], raw[5]), (want.month, want.day, want.year - 2000), (season_index, rec["date"]))
                self.assertEqual(raw[1:3], bytes([rec["home"], rec["away"]]))
                self.assertEqual(raw[6:8], bytes([rec["hour_field"], rec["minute_field"]]))
            self.assertEqual((rows[0][0][3], rows[0][0][4], rows[0][0][5]), (anchor.month, anchor.day, year - 2000))

    def test_missing_or_bad_block_leaves_the_preseason_empty(self) -> None:
        for block in (b"", b"\0" * 400, struct.pack("<I", (pre.PRESEASON_TAG << 16) | 69) + b"\0" * 560,
                      struct.pack("<I", pre.PRESEASON_TAG << 16) + b"\0" * 64):
            uc = self._boot(0, block)
            self._run(uc, pre.GENERATOR_VA)
            self.assertEqual([len(r) for r in self._rows(uc)], [0] * GRID_ROWS, block[:4].hex())

    def test_rows_and_slots_are_capped(self) -> None:
        uc = self._boot(0, _synthetic_block((18, 3, 2, 1)))
        self._run(uc, pre.GENERATOR_VA)
        self.assertEqual([len(r) for r in self._rows(uc)][:5], [17, 3, 2, 1, 0])
        # a record whose week byte is out of range is skipped, the rest still land
        raw = bytearray(_synthetic_block((1, 2, 2, 2)))
        raw[4 + 8 * 1] = 9                                                   # second record: week 9
        uc = self._boot(0, bytes(raw))
        self._run(uc, pre.GENERATOR_VA)
        self.assertEqual([len(r) for r in self._rows(uc)][:5], [1, 1, 2, 2, 0])

    def test_dob_line_prints_four_digit_years_after_the_year_group(self) -> None:
        """The year group's rewritten FUN_00145d20 (player card 'DOB:') on the real formatter chain."""
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

        player = 0x03000000

        def run(payload: bytes, yy: int, month: int, day: int) -> str:
            uc = Uc(UC_ARCH_X86, UC_MODE_32)
            uc.mem_map(0, 0x1000000)
            uc.mem_map(STACK_VA, 0x100000)
            uc.mem_map(player, 0x1000)
            uc.mem_map(SENTINEL & ~0xFFF, 0x1000)
            for s in strength._sections(payload):
                if s.raw_size:
                    uc.mem_write(s.virtual_address, payload[s.raw_offset: s.raw_offset + s.raw_size])
            uc.mem_write(SENTINEL, b"\xc3")
            uc.mem_write(player + 0x18, struct.pack("<I", (yy << 21) | (day << 16) | (month << 12)))
            esp = STACK_VA + 0x80000
            uc.mem_write(esp, struct.pack("<I", SENTINEL))
            uc.reg_write(UC_X86_REG_ESP, esp)
            uc.reg_write(UC_X86_REG_ECX, player)
            uc.emu_start(season.DOB_FORMATTER_VA, SENTINEL, count=200_000)
            return bytes(uc.mem_read(uc.reg_read(UC_X86_REG_EAX), 64)).decode("utf-16le").split("\0")[0]

        year_only, _ = season.apply(self.retail, groups=("year",))
        self.assertEqual(run(self.retail, 80, 8, 2), "8/2/80")
        self.assertEqual(run(self.patched, 80, 8, 2), "8/2/1980")
        self.assertEqual(run(year_only, 54, 1, 31), "1/31/1954")
        self.assertEqual(run(year_only, 2, 6, 26), "6/26/2002")        # a 2026 draft class birth year
        self.assertEqual(run(year_only, 30, 3, 4), "3/4/2030")         # pivot for 2026
        self.assertEqual(run(year_only, 31, 3, 4), "3/4/1931")

    def test_regular_season_generator_still_lands_rows_0_to_17(self) -> None:
        uc = self._boot(0, self.block)
        self._run(uc, pre.GENERATOR_VA)
        self.assertEqual([len(r) for r in self._rows(uc)][:4], [1, 16, 16, 16])
        self._run(uc, REGULAR_GENERATOR_VA)                                  # Preseason -> Season transition
        rows = self._rows(uc)
        regular = fs.decode_records(self.template, 0, len(self.template) // 8)
        weeks = fs.split_weeks(regular)
        self.assertEqual(len(weeks), 18)
        self.assertEqual([len(r) for r in rows], [len(w) for w in weeks] + [0] * 4)
        for row, week in enumerate(weeks):
            for slot, rec in enumerate(week):
                self.assertEqual(rows[row][slot], bytes([0, rec["home"], rec["away"], rec["month"], rec["day"], rec["year"] - 2000, rec["hour_field"], rec["minute_field"]]))
                self.assertEqual(self._flags(uc, row, slot), (1, 1))
        rdata = next(s for s in strength._sections(self.patched) if s.index == 12)
        wc_row = self.patched[rdata.raw_offset + (0x5151C4 - rdata.virtual_address)]
        self.assertEqual(wc_row, 18)
        for row in range(18, GRID_ROWS):
            self.assertEqual(self._record(uc, row, 0)[0], 7)


if __name__ == "__main__":
    unittest.main()
