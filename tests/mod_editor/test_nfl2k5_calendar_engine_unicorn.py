"""Bounded real x86 calendar/generator proofs. No Xbox boot or played witness.

Gregorian/date/grid/buffer routines execute natively. Synthetic team ranking and
name lookups are explicitly stubbed; no date result is supplied by Python.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from mod_editor.core import nfl2k5_calendar_engine as c, nfl2k5_season_length as season
from mod_editor.core import nfl2k5_preseason as pre, nfl2k5_playoffs14 as p14
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
YEARS = (2053, 2098, 2099, 2100, 2101, 2104, 2153)


class Machine:
    HEAP, STACK, STOP = 0x3000000, 0x4000000, 0x5000000
    DATE, POOL, PLAYER = HEAP + 0x100, HEAP + 0x10000, HEAP + 0x1000
    SP = STACK + 0x8000

    def __init__(self, payload, year=None):
        import unicorn as u
        from unicorn import x86_const as x
        self.x, self.u = x, u
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.image = XbeImage(payload)
        pages = {}
        for s in self.image.sections:
            for va in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096):
                pages[va] = pages.get(va, u.UC_PROT_READ) | (u.UC_PROT_WRITE if s.writable else 0) | (u.UC_PROT_EXEC if s.executable else 0)
        for page in pages:
            self.uc.mem_map(page, 4096)
        for s in self.image.sections:
            self.uc.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        for page, flags in pages.items():
            self.uc.mem_protect(page, 4096, flags)
        self.uc.mem_map(self.HEAP, 0x40000)
        self.uc.mem_map(self.STACK, 0x10000)
        self.uc.mem_map(self.STOP, 4096)
        a = c._allocations(payload)
        self.base_year = season.read_year(payload)
        self.labels = c.code_for(a["code"]["va"], a["read_only"]["va"], self.base_year)[1]
        self.put(0xE576B8, 0 if year is None else year - self.base_year)
        # Retail mode getter's actual global, pinned by the patch's dependent context.
        self.stub = {}
        self.visits, self.writes = [], []
        self.stop = self.STOP
        self.uc.hook_add(u.UC_HOOK_CODE, self._visit)
        self.uc.hook_add(u.UC_HOOK_MEM_WRITE, self._write)

    def reg(self, name, value=None):
        register = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value & 0xffffffff)

    def put(self, at, n):
        self.uc.mem_write(at, struct.pack("<I", n & 0xffffffff))

    def get(self, at):
        return struct.unpack("<I", self.uc.mem_read(at, 4))[0]

    def ret(self, value=None, pops=0):
        if value is not None:
            self.reg("EAX", value)
        sp = self.reg("ESP")
        self.reg("EIP", self.get(sp))
        self.reg("ESP", sp + 4 + pops)

    def _visit(self, uc, at, _size, _data):
        if at == self.stop:
            uc.emu_stop()
            return
        self.visits.append(at)
        if at in self.stub:
            self.stub[at]()

    def _write(self, _uc, _access, at, size, _value, _data):
        self.writes.append((at, size))

    def call(self, entry, *, eax=0, ecx=0, edx=0, budget=5000, stop=None):
        self.stop = self.STOP if stop is None else stop
        self.put(self.SP, self.STOP)
        for name, value in (("EAX", eax), ("ECX", ecx), ("EDX", edx), ("ESP", self.SP),
                            ("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
            self.reg(name, value)
        self.reg("EFLAGS", 0x202)
        self.visits, self.writes = [], []
        self.uc.emu_start(self.labels.get(entry, entry), self.stop, count=budget)
        if self.reg("EIP") != self.stop:
            raise AssertionError(f"budget {budget} exhausted at {self.reg('EIP'):#x}, expected {self.stop:#x}")
        if stop is None and self.reg("ESP") != self.SP + 4:
            raise AssertionError(f"unbalanced stack at {entry}: {self.reg('ESP'):#x}")
        return self.reg("EAX")

    def date(self, date):
        self.uc.mem_write(self.DATE, bytes([date.month, date.day, date.year - 2000]))

    def read_date(self, va=None):
        month, day, year = self.uc.mem_read(self.DATE if va is None else va, 3)
        return dt.date(year + 2000, month, day)

    def text(self, ptr):
        return bytes(self.uc.mem_read(ptr, 128)).decode("utf-16le").split("\0")[0]

    def records(self):
        return [[bytes(self.uc.mem_read(0xE57C40 + (r * 17 + s) * 8, 8)) for s in range(17)] for r in range(22)]

    def schedule_inputs(self):
        import nfl2k5_franchise_schedule as fs
        doc = json.loads((ROOT / "data/nfl_2026_schedule.json").read_text())
        regular, _ = fs.encode_schedule(doc)
        block, _ = fs.encode_preseason(doc)
        self.put(pre.POOL_POINTER_GLOBAL, self.POOL)
        self.put(self.POOL + 0x28, len(regular) // 8)
        self.put(self.POOL + 0x2C, self.POOL + 0x100)
        self.uc.mem_write(self.POOL + 0x100, regular + block)
        self.uc.mem_write(0xE41BB8, bytes(range(32)))
        self.stub[pre.FN_MARQUEE_RESET] = lambda: self.ret()
        self.stub[pre.FN_TEAM_LOOKUP] = lambda: self.ret(self.reg("EDI"))
        # External synthetic standings, team division, named-team and marquee ranking.
        self.stub[0xC4C50] = lambda: self.ret(self.PLAYER + self.reg("ECX") * 0x100)
        self.stub[0xC6480] = lambda: self.ret((self.reg("ECX") - self.PLAYER) // 0x400)
        self.stub[0x2BEA70] = lambda: self.ret(0 if self.reg("EBX") == 0xE9A4D4 else 1)
        self.stub[0x2BF1B0] = lambda: self.ret(self.reg("EDX"))
        return regular, block


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "Unicorn or pinned USA retail default.xbe absent")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("retail hash mismatch")
        seed, _ = season.apply(retail)
        cls.payload, _ = c.apply(seed)
        cls.payload_2004, _ = c.apply(retail)

    def test_all_128_season_anchors_and_final_postseason_at_both_bases(self):
        for payload, base in ((self.payload_2004, 2004), (self.payload, 2026)):
            m = Machine(payload)
            for index in range(128):
                year = base + index
                m.put(0xE576B8, index)
                # Independent fourth-Thursday oracle; do not reuse opening_date().
                thanksgiving = next(dt.date(year, 11, day) for day in range(22, 29)
                                    if dt.date(year, 11, day).weekday() == 3)
                opening = thanksgiving - dt.timedelta(days=77)
                self.assertEqual(m.call("opening_day"), (opening - c.EPOCH).days, (base, index))
                m.date(dt.date(year, 11, 1))
                self.assertEqual(m.call("regular_anchor", ecx=m.DATE), year - 2000)
                self.assertEqual(m.read_date(), dt.date(year, 11, 1))
                for offset in (-35, 0, 77, 122, 128, 149, 157):
                    self.assertEqual(m.call("redate", ecx=m.DATE, edx=offset), 1)
                    self.assertEqual(m.read_date(), opening + dt.timedelta(days=offset), (base, index, offset))
                # At index 127 the championship remains in the following year.
                if index == 127:
                    m.call("redate", ecx=m.DATE, edx=c.POSTSEASON_OFFSETS[-1])
                    self.assertEqual(m.read_date().year, base + 128)

    def test_full_year_leap_ordinal_weekday_and_inverse(self):
        m = Machine(self.payload)
        for y in (1900, 1999, 2000, 2004, 2053, 2098, 2099, 2100, 2101, 2104, 2153, 2255, 2400):
            self.assertEqual(m.call("leap", eax=y), int(y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)), y)
            if y > 2255:
                continue
            for mo, day in ((1, 1), (2, 28), (3, 1), (12, 31)):
                d = dt.date(y, mo, day)
                m.uc.mem_write(m.DATE, bytes([mo, day, 0]))
                n = m.call("ordinal", eax=y, ecx=m.DATE)
                self.assertEqual(n, (d - c.EPOCH).days & 0xffffffff, d)
                self.assertEqual(m.reg("ECX"), m.DATE)
                for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
                    self.assertEqual(m.reg(name), value)
                if y >= 2000:
                    self.assertEqual(m.call("inverse", eax=n, ecx=m.DATE), 1)
                    self.assertEqual(m.read_date(), d)
                    self.assertEqual(m.call("weekday", ecx=m.DATE), d.weekday(), d)
        m.uc.mem_write(m.DATE, b"\x02\x1d\x64")
        self.assertEqual(m.call("ordinal", eax=2100, ecx=m.DATE), 0x80000000)
        m.uc.mem_write(m.DATE, b"\x02\x1d\x68")
        self.assertNotEqual(m.call("ordinal", eax=2104, ecx=m.DATE), 0x80000000)

    def test_add_subtract_century_boundaries_and_atomic_refusal(self):
        m = Machine(self.payload)
        for y in YEARS:
            for start in (dt.date(y, 12, 25), dt.date(y, 2, 25), dt.date(y, 1, 2)):
                for delta in (-400, -8, -1, 0, 1, 8, 400):
                    for helper, sign in (("add_days", 1), ("sub_days", -1)):
                        m.date(start)
                        self.assertEqual(m.call(helper, ecx=m.DATE, edx=delta), 1)
                        self.assertEqual(m.read_date(), start + dt.timedelta(days=sign * delta))
                        self.assertTrue(all(m.STACK <= va < m.STACK + 0x10000 or m.DATE <= va < m.DATE + 3 for va, _ in m.writes))
        for raw, delta in ((b"\x02\x1d\x64", 1), (b"\x00\x01\x64", 1), (b"\x01\x01\x00", -1), (b"\x0c\x1f\xff", 1), (b"\x01\x01\x64", 0x7fffffff)):
            m.uc.mem_write(m.DATE, raw)
            self.assertEqual(m.call("add_days", ecx=m.DATE, edx=delta), 0x80000000)
            self.assertEqual(bytes(m.uc.mem_read(m.DATE, 3)), raw)
        m.date(dt.date(2100, 2, 28))
        m.call("add_days", ecx=m.DATE, edx=1)
        self.assertEqual(m.read_date(), dt.date(2100, 3, 1))
        m.date(dt.date(2104, 2, 28))
        m.call("add_days", ecx=m.DATE, edx=1)
        self.assertEqual(m.read_date(), dt.date(2104, 2, 29))
        m.call("add_days", ecx=m.DATE, edx=1)
        self.assertEqual(m.read_date(), dt.date(2104, 3, 1))

    def test_historical_templates_keep_1999_epoch_and_week_break(self):
        m = Machine(self.payload, 2100)
        for d in (dt.date(1999, 12, 31), dt.date(2000, 2, 29), dt.date(2026, 9, 10)):
            raw = bytes([0, 1, 2, d.month, d.day, d.year % 100, 7, 30])
            m.uc.mem_write(m.DATE, raw)
            result = m.call(0x1C19F0, ecx=m.DATE)
            self.assertEqual(result, (d - dt.date(1999, 1, 1)).days)
            self.assertEqual(bytes(m.uc.mem_read(m.DATE, 8)), raw)
        for first, second, expected in ((dt.date(1999, 12, 30), dt.date(2000, 1, 2), 0),
                                        (dt.date(2026, 9, 14), dt.date(2026, 9, 17), 1)):
            for at, d in ((m.DATE, first), (m.DATE + 16, second)):
                m.uc.mem_write(at, bytes([0, 1, 2, d.month, d.day, d.year % 100, 7, 30]))
            self.assertEqual(m.call(0x1C1A90, ecx=m.DATE, edx=m.DATE + 16), expected)

    def test_dob_formatter_native_with_2053_prospects_and_moving_century(self):
        m = Machine(self.payload)
        for year in YEARS:
            m.put(0xE576B8, year - 2026)
            for age in (0, 22, 24, 39, 99):
                birth = year - age
                raw = birth % 100
                m.put(m.PLAYER + 0x18, (raw << 21) | (2 << 16) | (8 << 12))
                ptr = m.call(season.DOB_FORMATTER_VA, ecx=m.PLAYER, budget=20000)
                self.assertEqual(m.text(ptr), f"8/2/{birth}", (year, birth))
                self.assertEqual(m.get(m.PLAYER + 0x18), (raw << 21) | (2 << 16) | (8 << 12))
        for raw in (100, 127):
            year = 2104
            m.put(0xE576B8, year - 2026)
            self.assertEqual(m.call("birth_year", eax=raw), year - ((year - raw % 100) % 100))

    def test_preseason_native_at_every_sentinel_and_first_year_source(self):
        for year in (2026,) + YEARS:
            m = Machine(self.payload, year)
            _regular, block = m.schedule_inputs()
            source = bytes(m.uc.mem_read(m.POOL + 0x100, len(_regular) + len(block)))
            m.call(pre.GENERATOR_VA, budget=300000)
            rows = [[r for r in row if r[0] != 7] for row in m.records()]
            self.assertEqual([len(row) for row in rows], [1, 16, 16, 16] + [0] * 18)
            for raw, i in zip([r for row in rows for r in row], range(49)):
                original = block[4 + i * 8:12 + i * 8]
                source_date = dt.date(2000 + original[5], original[3], original[4])
                expected = source_date if year == 2026 else c.opening_date(year) - dt.timedelta(days=35) + (source_date - dt.date(2026, 8, 6))
                self.assertEqual((raw[3], raw[4], raw[5]), (expected.month, expected.day, expected.year - 2000), (year, i))
                self.assertEqual(raw[1:3] + raw[6:], original[1:3] + original[6:])
            self.assertEqual(bytes(m.uc.mem_read(m.POOL + 0x100, len(source))), source)

    def test_regular_generator_native_through_last_season(self):
        for year in (2026,) + YEARS:
            m = Machine(self.payload, year)
            regular, _block = m.schedule_inputs()
            m.call(0x2BF270, budget=1500000)
            rows = [[r for r in row if r[0] != 7] for row in m.records()]
            self.assertEqual(sum(map(len, rows)), 272, year)
            self.assertEqual(rows[18:], [[], [], [], []])
            if year == 2026:
                self.assertEqual(b"".join(r for row in rows for r in row), regular)
            else:
                opening = c.opening_date(year)
                for week, row in enumerate(rows[:18]):
                    for slot, raw in enumerate(row):
                        when = dt.date(raw[5] + 2000, raw[3], raw[4])
                        self.assertTrue(opening + dt.timedelta(days=week * 7) <= when <= opening + dt.timedelta(days=week * 7 + 4), (year, week, when))
                        day_offset = 0 if week == 11 and slot < 2 else 2 if week >= 16 and slot < 4 else 4 if slot == len(row) - 1 else 3
                        self.assertEqual(when, opening + dt.timedelta(days=week * 7 + day_offset))
                self.assertEqual(dt.date(rows[11][0][5] + 2000, rows[11][0][3], rows[11][0][4]).weekday(), 3)
            self.assertEqual(bytes(m.uc.mem_read(m.POOL + 0x100, len(regular))), regular)

    def test_postseason_builder_native_all_sentinels(self):
        from tests.nfl2k5_playoffs14_test import League, TEAMS_VA, TEAM_STRIDE
        for year in (2026,) + YEARS:
            m, league = Machine(self.payload, year), League()
            m.put(0xE576B0, 18)
            m.uc.mem_write(0xE576D4, b"".join(struct.pack("<I", league.division[t]) for t in range(32)))
            m.uc.mem_write(0xE57C40, bytes([7, 0, 0, 0, 0, 0, 0, 0]) * (22 * 17))
            m.uc.mem_write(TEAMS_VA, bytes(32 * TEAM_STRIDE))
            m.stub[p14.FN_TEAM_COUNT] = lambda: m.ret(32)
            m.stub[p14.FN_TEAM_AT] = lambda: m.ret(league.ptr(m.reg("ECX")) if m.reg("ECX") < 32 else 0)
            m.stub[p14.FN_USER_TEAM] = lambda: m.ret(0)
            def division():
                div = m.reg("ECX")
                best = max((t for t in range(32) if league.division[t] == div), key=league.strength.get)
                m.ret(league.ptr(best))
            def sort():
                arr, count = m.reg("ECX"), m.reg("EDX")
                ptrs = list(struct.unpack("<%dI" % count, m.uc.mem_read(arr, count * 4)))
                ptrs.sort(key=lambda ptr: league.strength[league.team(ptr)], reverse=True)
                m.uc.mem_write(arr, struct.pack("<%dI" % count, *ptrs))
                m.ret()
            m.stub[p14.FN_SEED_DIVISION], m.stub[p14.FN_SORT_TEAMS] = division, sort
            m.call(0x2A7E50, stop=p14.BUILDER_END_VA, budget=100000)
            self.assertEqual(m.reg("ESI"), 21)
            self.assertEqual(m.reg("ESP"), m.SP - 0x3c)
            rows, seeds = m.records(), league.seeds(0) + league.seeds(1)
            for i, (week, slot, home, away, flag_a, flag_b) in enumerate(p14.GAME_TABLE):
                raw = rows[18 + week][slot]
                when = c.opening_date(year) + dt.timedelta(days=c.POSTSEASON_OFFSETS[i])
                self.assertEqual(raw[3:6], bytes([when.month, when.day, when.year - 2000]), (year, i))
                self.assertEqual(raw[6:], p14.date_table_14(p14.CALENDAR_2026_14)[i * 8 + 6:i * 8 + 8])
                if home != 255:
                    self.assertEqual(raw[1], seeds[home])
                if away != 255:
                    self.assertEqual(raw[2], seeds[away])
                at = 0xE57954 + ((18 + week) * 17 + slot) * 2
                self.assertEqual(bytes(m.uc.mem_read(at, 2)), bytes([flag_a, flag_b]))
            final_sunday = c.opening_date(year) + dt.timedelta(days=17 * 7 + 3)
            first_wc = dt.date(2000 + rows[18][0][5], rows[18][0][3], rows[18][0][4])
            self.assertEqual((first_wc - final_sunday).days, 6)
            self.assertEqual(rows[18][6][0], 7)

    def test_visible_year_labels_use_full_year_and_dedicated_formats(self):
        m = Machine(self.payload)
        m.put(0xE576A0, 2)
        for year in YEARS:
            m.put(0xE576B8, year - 2026)
            # Native future cap-label callback (ESI horizon), including actual formatter.
            for horizon in (0, 1, 6):
                ptr = m.call(0x3663E0, ecx=horizon, budget=20000)
                self.assertEqual(m.text(ptr), f"{year + horizon:04}")
            # The other label's patched getter and unchanged +4 LEA are executed as a slice.
            m.call(0x347714, stop=0x347721)
            self.assertEqual(m.reg("EDX"), year + 0x22222222)
            # History getters' full immediates keep their row-bank subtraction (bank 11 current).
            image = XbeImage(self.payload)
            for va in (0x3204AD, 0x3218A7):
                base = struct.unpack("<I", image.read(va, 4))[0]
                self.assertEqual((year - 2026) + base - 11, year)
            # Current date-line weekday differs from historical byte 99 only in franchise mode.
            m.date(dt.date(year, 11, 1))
            self.assertEqual(m.call(0x1C1940, ecx=m.DATE), m.get(0xAADF90 + dt.date(year, 11, 1).weekday() * 4))
        m.uc.mem_write(m.DATE, b"\x0c\x1f\x63")
        m.put(0xE576A0, 0)
        self.assertEqual(m.call("display_weekday", ecx=m.DATE), dt.date(1999, 12, 31).weekday())
        m.put(0xE576A0, 2)
        self.assertEqual(m.call("display_weekday", ecx=m.DATE), dt.date(2099, 12, 31).weekday())

    def test_completion_gate_127_passes_128_refuses_only_retirement(self):
        m = Machine(self.payload)
        # Execute the actual pinned compare and stage branch. Stop before UI/lifecycle calls.
        for index, stage, target in ((127, 1, 0x2480F7), (128, 1, 0x2480DA), (128, 7, 0x2480F7)):
            m.put(0xE576B8, index)
            # Stage getter is native; locate its existing global from the pinned instructions.
            m.put(0xE576A4, stage)
            m.call(0x2480C6, stop=target, budget=50)
            self.assertEqual(m.reg("EIP"), target)


if __name__ == "__main__":
    unittest.main()
