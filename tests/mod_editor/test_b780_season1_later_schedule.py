"""b780-season1 (Q70): later franchise seasons keep the 2026 schedule's weekdays, kickoffs and Thanksgiving hosts.

The game's own regular-season generator (FUN_002bf270, its template copy, remap and division rotation) runs under
Unicorn on the retail executable with the 2026 season groups, the 128-season calendar and this owner, for every season
of a four-season rotation and beyond, with a shuffled finish order and the real divisions (the team-code lookup and the
two division readers are answered from the real 32-club table; nothing else is stubbed but the per-team marquee reset).
Without the owner the same harness shows the reported schedule: no Thursday games after the first season.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import importlib.util
import json
import os
import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from mod_editor.core import nfl2k5_calendar_engine as c  # noqa: E402
from mod_editor.core import nfl2k5_later_schedule as ls  # noqa: E402
from mod_editor.core import nfl2k5_preseason as pre  # noqa: E402
from mod_editor.core import nfl2k5_season_length as season  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
NICKNAMES = ("49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns", "Buccaneers", "Cardinals", "Chargers", "Chiefs",
             "Colts", "Cowboys", "Dolphins", "Eagles", "Falcons", "Giants", "Jaguars", "Jets", "Lions", "Packers",
             "Panthers", "Patriots", "Raiders", "Rams", "Ravens", "Redskins", "Saints", "Seahawks", "Steelers", "Texans",
             "Titans", "Vikings")
# the retail division table's codes (0xACEE38, division order 0..7) and their clubs
CODES = {"STL": "Rams", "SF": "49ers", "SEA": "Seahawks", "ARZ": "Cardinals", "CHI": "Bears", "GB": "Packers",
         "MIN": "Vikings", "DET": "Lions", "TB": "Buccaneers", "NO": "Saints", "ATL": "Falcons", "CAR": "Panthers",
         "PHI": "Eagles", "WAS": "Redskins", "NYG": "Giants", "DAL": "Cowboys", "OAK": "Raiders", "DEN": "Broncos",
         "KC": "Chiefs", "SD": "Chargers", "PIT": "Steelers", "BAL": "Ravens", "CLE": "Browns", "CIN": "Bengals",
         "TEN": "Titans", "IND": "Colts", "JAX": "Jaguars", "HOU": "Texans", "NE": "Patriots", "MIA": "Dolphins",
         "NYJ": "Jets", "BUF": "Bills"}


def thanksgiving(year: int) -> dt.date:
    return next(dt.date(year, 11, d) for d in range(22, 29) if dt.date(year, 11, d).weekday() == 3)


class StaticTests(unittest.TestCase):
    def test_every_routine_fits_its_dead_function(self) -> None:
        blobs = ls.code_regions(0x1500000, 0x1500100, ls.base_opening_days(2026))
        for label, va, size, _digest in ls.REGIONS:
            self.assertEqual(len(blobs[label]), size, label)
        self.assertEqual((ls.DETROIT, ls.DALLAS), (NICKNAMES.index("Lions"), NICKNAMES.index("Cowboys")))
        # the template's opening Thursday: September 10, 2026 (77 days before Thanksgiving)
        self.assertEqual(ls.base_opening_days(2026), (dt.date(2026, 9, 10) - dt.date(2000, 1, 1)).days)

    def test_hook_and_calls_land_on_function_entries(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        blobs = ls.code_regions(0x1500000, 0x1500100, ls.base_opening_days(2026))
        entries = {va for _l, va, _s, _d in ls.REGIONS}
        allowed = entries | {0x1500000, 0x1500100, ls.SEASON_FN, ls.DONE_VA}
        for label, va, size, _d in ls.REGIONS:
            code = blobs[label].rstrip(b"\xcc")
            ins = list(md.disasm(code, va))
            self.assertEqual(ins[-1].address + ins[-1].size, va + len(code), f"{label} decodes completely")
            for i in ins:
                if i.mnemonic in ("call", "jmp") and i.op_str.startswith("0x"):
                    target = int(i.op_str, 16)
                    inside = va <= target < va + size
                    self.assertTrue(inside or target in allowed, f"{label}: {i.mnemonic} {i.op_str}")
        hook = ls._hook_bytes()
        self.assertEqual(hook[0], 0xE9)
        self.assertEqual(ls.HOOK_VA + 5 + struct.unpack("<i", hook[1:])[0], ls._region("main")[1])

    def test_the_build_installs_it_right_after_the_calendar(self) -> None:
        from mod_editor.core import nfl2k5_throw_tuning as tt
        self.assertIs(tt.later_schedule_patch, ls)
        text = (ROOT / "mod_editor/core/nfl2k5_throw_tuning.py").read_text(encoding="utf-8")
        calendar_row = text.index('(calendar_engine, calendar_engine_patch, "calendar_engine_patch"')
        self.assertLess(calendar_row, text.index('(calendar_engine, later_schedule_patch, "later_schedule_patch"'))

    def test_module_text_rules(self) -> None:
        text = (ROOT / "mod_editor/core/nfl2k5_later_schedule.py").read_text(encoding="utf-8")
        self.assertNotIn("—", text)
        self.assertNotIn("/home/", text)
        allow = set((ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").split())
        self.assertIn("mod_editor/core/nfl2k5_later_schedule.py", allow)
        self.assertIn("tests/mod_editor/test_b780_season1_later_schedule.py", allow)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "Unicorn and the private retail executable are needed")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from tests.mod_editor.test_nfl2k5_calendar_engine_unicorn import Machine
        cls.Machine = Machine
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("retail hash mismatch")
        cls.stock = c.apply(season.apply(retail)[0])[0]
        cls.fixed, cls.receipt = ls.apply(cls.stock)
        import nfl2k5_franchise_schedule as fs
        doc = json.loads((ROOT / "data/nfl_2026_schedule.json").read_text())
        cls.regular, _ = fs.encode_schedule(doc)
        cls.block, _ = fs.encode_preseason(doc)
        image = XbeImage(retail)
        cls.division = {}
        for d in range(8):
            for k in range(4):
                pointer = struct.unpack("<I", image.read(0xACEE38 + 0x30 * d + 12 * k, 4))[0]
                code = image.read(pointer, 16).decode("utf-16le").split("\0")[0]
                cls.division[NICKNAMES.index(CODES[code])] = d
        cls.template = cls.generate(cls.fixed, 2026, list(range(32)))

    @classmethod
    def generate(cls, payload: bytes, year: int, order: list[int]):
        """Run FUN_002bf270 for ``year`` with the clubs ranked ``order`` (0xE41BB8): the 18 regular-season rows."""
        m = cls.Machine(payload, year)
        pool = m.POOL
        m.put(pre.POOL_POINTER_GLOBAL, pool)
        m.put(pool + 0x28, len(cls.regular) // 8)
        m.put(pool + 0x2C, pool + 0x100)
        m.uc.mem_write(pool + 0x100, cls.regular + cls.block)
        m.uc.mem_write(0xE41BB8, bytes(order))
        m.uc.mem_write(0xE576D4, b"".join(struct.pack("<I", cls.division[t]) for t in range(32)))
        m.uc.mem_write(0xE57C40, bytes([7, 0, 0, 0, 0, 0, 0, 0]) * (22 * 17))
        club = lambda t: m.PLAYER + t * 0x100            # noqa: E731  a synthetic club record per league index
        m.stub[pre.FN_MARQUEE_RESET] = lambda: m.ret()

        def code_lookup():                                # FUN_002bea40: code pointer (edi) -> league index
            text = bytes(m.uc.mem_read(m.reg("EDI"), 16)).decode("utf-16le").split("\0")[0]
            m.ret(NICKNAMES.index(CODES[text]) if text in CODES else 0xFFFFFFFF)
        m.stub[0x2BEA40] = code_lookup
        m.stub[0xC4C50] = lambda: m.ret(club(m.reg("ECX")))
        m.stub[0xC6480] = lambda: m.ret(cls.division[(m.reg("ECX") - m.PLAYER) // 0x100])
        if ls.status(payload) != "applied":               # the retail tail's own helpers (dead once the owner is in)
            def by_code():                                # FUN_002bea70: code pointer (ebx) -> club record
                text = bytes(m.uc.mem_read(m.reg("EBX"), 16)).decode("utf-16le").split("\0")[0]
                m.ret(club(NICKNAMES.index(CODES[text])) if text in CODES else 0)
            m.stub[0x2BEA70] = by_code
            m.stub[0x2BF1B0] = lambda: m.ret(m.reg("EDX"))  # marquee ranking: the slot index, as the calendar tests do
        m.call(0x2BF270, budget=3_000_000)
        rows = []
        for r in range(18):
            row = []
            for s in range(17):
                raw = bytes(m.uc.mem_read(0xE57C40 + (r * 17 + s) * 8, 8))
                if raw[0] != 7:
                    row.append(raw)
            rows.append(row)
        return rows

    def check_structure(self, rows, year):
        games = collections.Counter()
        home = collections.Counter()
        for week, row in enumerate(rows):
            seen = collections.Counter()
            for raw in row:
                seen[raw[1]] += 1
                seen[raw[2]] += 1
                games[raw[1]] += 1
                games[raw[2]] += 1
                home[raw[1]] += 1
            self.assertTrue(all(v == 1 for v in seen.values()), (year, week))
        self.assertEqual(sorted(games.values()), [17] * 32, year)
        self.assertEqual(sorted(home.values()), sorted(collections.Counter(r[1] for row in self.template for r in row).values()))
        for raw in rows[17]:                               # week 18: every game inside a division
            self.assertEqual(self.division[raw[1]], self.division[raw[2]], year)

    def test_season_zero_is_the_template(self) -> None:
        stock = self.generate(self.stock, 2026, list(range(32)))
        self.assertEqual(self.template, stock)
        self.assertEqual(b"".join(r for row in self.template for r in row), self.regular)

    def test_later_seasons_keep_weekday_kickoff_and_thanksgiving_hosts(self) -> None:
        rng = random.Random(780)
        for year in (2027, 2028, 2029, 2030, 2031, 2034, 2053, 2100, 2153):
            order = list(range(32))
            rng.shuffle(order)
            rows = self.generate(self.fixed, year, order)
            with self.subTest(year=year):
                self.check_structure(rows, year)
                shift = c.opening_date(year) - c.opening_date(2026)
                self.assertEqual(shift.days % 7, 0)
                for week, (row, original) in enumerate(zip(rows, self.template)):
                    self.assertEqual(len(row), len(original), (year, week))
                    for raw, src in zip(row, original):
                        when = dt.date(2000 + raw[5], raw[3], raw[4])
                        self.assertEqual(when, dt.date(2000 + src[5], src[3], src[4]) + shift, (year, week))
                        self.assertEqual(raw[6:], src[6:], (year, week))          # the slot's own kickoff
                thanks = rows[ls.THANKSGIVING_ROW]
                self.assertEqual((thanks[0][1], thanks[1][1]), (ls.DETROIT, ls.DALLAS), year)
                for raw in thanks[:2]:
                    self.assertEqual(dt.date(2000 + raw[5], raw[3], raw[4]), thanksgiving(year), year)
                days = collections.Counter(dt.date(2000 + r[5], r[3], r[4]).weekday() for row in rows for r in row)
                template_days = collections.Counter(dt.date(2000 + r[5], r[3], r[4]).weekday()
                                                    for row in self.template for r in row)
                self.assertEqual(days, template_days, year)                        # Thursday games stay
                monday = [r for row in rows for r in row if dt.date(2000 + r[5], r[3], r[4]).weekday() == 0]
                self.assertTrue(monday and all(r[6] >= 7 for r in monday), year)  # Monday night stays at night

    def test_without_the_owner_later_seasons_lose_thursday_games(self) -> None:
        rows = self.generate(self.stock, 2027, list(range(31, -1, -1)))
        thursday = [r for row in rows for r in row if dt.date(2000 + r[5], r[3], r[4]).weekday() == 3]
        template_thursday = [r for row in self.template for r in row if dt.date(2000 + r[5], r[3], r[4]).weekday() == 3]
        self.assertGreater(len(template_thursday), 17)
        self.assertLess(len(thursday), 4)                  # only the two Thanksgiving slots keep a Thursday

    @staticmethod
    def references(payload: bytes):
        image = XbeImage(payload)
        text = next(sec for sec in image.sections if sec.executable and sec.start <= 0x2BF1B0 < sec.end)
        data = image.read(text.start, text.raw_size)
        refs = []
        for off in range(len(data) - 6):
            op = data[off]
            if op in (0xE8, 0xE9):
                refs.append((text.start + off, text.start + off + 5 + struct.unpack_from("<i", data, off + 1)[0]))
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                refs.append((text.start + off, text.start + off + 6 + struct.unpack_from("<i", data, off + 2)[0]))
        for sec in image.sections:
            blob = image.read(sec.start, sec.raw_size)
            for off in range(0, len(blob) - 3, 1 if sec.executable else 4):
                value = struct.unpack_from("<I", blob, off)[0]
                if 0x2BEA00 <= value < 0x2BF300:
                    if sec.executable and not (blob[off - 1] == 0x68 or 0xB8 <= blob[off - 1] <= 0xBF):
                        continue
                    refs.append((sec.start + off, value))
        return refs

    def test_retail_code_reaches_the_rewritten_functions_only_at_their_entries(self) -> None:
        # the cave rule of test_xbe_patch_cave_references (it scans the retail image): no call, jump or pointer lands
        # inside a rewritten function except on its first byte
        for label, va, size, _d in ls.REGIONS:
            outside = [(hex(src), hex(dst)) for src, dst in self.references(XBE.read_bytes())
                       if va < dst < va + size and not va <= src < va + size]
            self.assertEqual(outside, [], label)
        # and on the image the owner installs over (the template preseason replaced the retail generator, whose date
        # writers at 0x2BF0BD.. and 0x2BF15B called two of these helpers), only the dead tail still calls them
        refs = self.references(self.stock)
        for label, va, size, _d in ls.REGIONS:
            callers = {src for src, dst in refs if dst == va and not va <= src < va + size}
            self.assertTrue(callers or label == "find", label)
            self.assertTrue(all(0x2BF474 <= src < ls.DONE_VA for src in callers), (label, [hex(x) for x in callers]))

    def test_status_apply_and_dependencies(self) -> None:
        self.assertEqual(ls.status(self.stock), "retail")
        self.assertEqual(ls.status(self.fixed), "applied")
        self.assertEqual(ls.apply(self.fixed)[0], self.fixed)
        self.assertEqual(c.status(self.fixed), "applied")
        self.assertEqual(season.status(self.fixed)["season_length"], "applied")
        with self.assertRaises(ls.LaterScheduleError):
            ls.apply(season.apply(XBE.read_bytes())[0])       # the calendar is not installed
        image = XbeImage(self.fixed)
        for _label, va, size, _d in ls.REGIONS:
            self.assertNotEqual(image.read(va, size), XbeImage(self.stock).read(va, size))
        broken = bytearray(self.fixed)
        broken[image.offset(ls._region("find")[1]) + 3] ^= 1
        self.assertEqual(ls.status(bytes(broken)), "foreign")


if __name__ == "__main__":
    unittest.main()
