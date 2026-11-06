"""b780 rst2 (coordinator 11/04): every injury the roster marks for modern injured reserve carries the game's own injury
type, so the Injury Report names it (it said just "injury" before). The type table, the weeks and the status are proved
on the real v0.9 executable and roster body (private fixtures NFL2K5_V09_XBE / NFL2K5_V09_ROST_BODY, skipped without them)."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_refresh as refresh

HAVE_UC = importlib.util.find_spec("unicorn") is not None
XBE = Path(os.environ.get("NFL2K5_V09_XBE", "") or "missing")
BODY = Path(os.environ.get("NFL2K5_V09_ROST_BODY", "") or "missing")
TABLE_VA, TABLE_ROWS = 0x4F2D00, 0x41      # the first 0x41 sixteen-byte rows hold the 65 types


class TypeChoiceTests(unittest.TestCase):
    def test_the_table_has_65_distinct_types_in_the_game_order(self):
        keys = [(g, i) for g, i, *_ in refresh.INJURY_TYPES]
        self.assertEqual(len(keys), 65)
        self.assertEqual(len(set(keys)), 65)
        self.assertTrue(all(0 <= g < 32 and 0 < i < 32 for g, i in keys))

    def test_a_body_part_takes_a_type_that_is_out_and_ends_no_career(self):
        by_key = {row[:2]: row for row in refresh.INJURY_TYPES}
        for part in refresh.INJURY_PARTS:
            for weeks in range(4, 80):
                choice = refresh.injury_type(part, weeks)
                if choice is None:
                    continue
                _, _, name, duration, out_from, career_above = by_key[choice[:2]]
                self.assertIsNotNone(out_from, (part, weeks, name))
                self.assertGreaterEqual(weeks, out_from, (part, weeks, name))
                self.assertTrue(career_above is None or weeks <= career_above, (part, weeks, name))

    def test_the_duration_closest_to_the_weeks_wins_and_a_tie_goes_to_the_game_order(self):
        self.assertEqual(refresh.injury_type("Ankle", 8)[2], "broken ankle")
        self.assertEqual(refresh.injury_type("Achilles", 17)[2], "ruptured achilles")      # torn achilles ends a career above 16
        self.assertEqual(refresh.injury_type("Knee", 17)[2], "torn ACL")                    # ACL and MCL are both 16 weeks
        self.assertEqual(refresh.injury_type("Hamstring", 8)[2], "torn hamstring")
        self.assertEqual(refresh.injury_type("Foot", 17)[2], "broken foot")                  # a stress fracture ends a career above 10

    def test_a_part_the_game_has_no_type_for_stays_untyped(self):
        for part in ("Concussion", "Neck", "Illness", "Chest", "Pectoral", "Groin", "Abdomen", "Stinger", "", None,
                     "Not injury related - resting player"):
            self.assertIsNone(refresh.injury_type(part, 8), part)

    def test_the_type_bits_leave_the_depth_rank_and_side_alone(self):
        half = refresh.with_injury_type(0b101_110_0000000000, 20, 23)
        self.assertEqual(half & 0x3FF, 20 | (23 << 5))
        self.assertEqual(half >> 10, 0b101_110)


@unittest.skipUnless(HAVE_UC and XBE.is_file() and BODY.is_file(), "private v0.9 XBE / roster body absent")
class InjuryTypeNativeTests(unittest.TestCase):
    """The writer's table against the executable, and the Injury Report, the weekly advance and the career check on typed
    records."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        cls.payload, cls.body = XBE.read_bytes(), BODY.read_bytes()
        m = cls.m = Machine(cls.payload, trace_writes=False)
        size = len(cls.body) - 0x40
        m.uc.mem_write(m.ARENA + 0x300, cls.body)
        m.put(0xB72804, m.ARENA + 0x300)
        m.put(0xB72808, size)
        m.put(0xB7280C, size)
        m.fixup_roster(m.ARENA + 0x340)
        m.seed(12345)
        for address, value in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 5), (0xE60010, 5)):
            m.put(address, value)
        doc = rr.RosterDocument(cls.body, scheme="one_pool", reference_year=2026)
        cls.players = [m.ARENA + 0x300 + p.offset for p in doc.players[:60]]

    def text(self, pointer):
        out = bytearray()
        while True:
            unit = bytes(self.m.uc.mem_read(pointer, 2))
            if unit == b"\0\0" or len(out) > 200:
                return out.decode("utf-16-le")
            out += unit
            pointer += 2

    def mark(self, address, weeks, choice=None, injured=True):
        m = self.m
        word20, word24 = m.get(address + 0x20), m.get(address + 0x24)
        (half,) = struct.unpack("<H", bytes(m.uc.mem_read(address + 0x28, 2)))
        w20, w24 = refresh.long_injury_words(word20 & ~0x40000000, word24, weeks)
        m.put(address + 0x20, w20)
        m.put(address + 0x24, w24)
        half = refresh.with_injury_type(half, choice[0], choice[1]) if choice else half & 0xFC00
        m.uc.mem_write(address + 0x28, struct.pack("<H", half))

    def test_the_writer_table_is_the_executables_table(self):
        data = self.payload
        base, sections = 0x10000, None
        for row in range(TABLE_ROWS):
            word, name_va, *_ = struct.unpack_from("<IIff", data, TABLE_VA + 16 * row)
            if not (0xE60320 <= name_va < 0xE60320 + 381857):
                continue
            start = 11464704 + name_va - 15074080
            end = start
            while data[end:end + 2] != b"\0\0":
                end += 2
            name = data[start:end].decode("utf-16-le")
            group, index, duration = word & 31, (word >> 5) & 31, (word >> 19) & 63
            limit = word >> 26 if (word >> 17) & 1 else None
            got = next(r for r in refresh.INJURY_TYPES if r[:2] == (group, index))
            self.assertEqual((got[2], got[3], got[5]), (name, duration, limit), (group, index))

    def test_the_injury_report_names_the_type_and_the_weeks_run_down_the_same(self):
        address = self.players[3]
        self.mark(address, 8)
        self.assertEqual(self.text(self.m.call(0x21DC30, eax=address, ecx=address)), "injury")       # untyped: the old report
        typed = refresh.injury_type("Hamstring", 8)
        self.mark(address, 8, typed)
        self.assertEqual(self.text(self.m.call(0x21DC30, eax=address, ecx=address)), "torn hamstring")
        self.assertEqual((self.m.get(address + 0x20) >> 22) & 0xFF, 8)

    def test_the_weekly_advance_takes_the_same_weeks_with_or_without_the_type_and_a_type_keeps_him_out(self):
        for part, weeks in (("Ankle", 8), ("Knee", 17), ("Calf", 8), ("Foot", 17), ("Back", 17)):
            choice = refresh.injury_type(part, weeks)
            untyped, typed = self.players[10], self.players[11]
            self.mark(untyped, weeks)
            self.mark(typed, weeks, choice)
            for week in range(1, weeks + 1):
                self.m.call(0x133BD0, ecx=untyped)
                self.m.call(0x133BD0, ecx=typed)
                self.assertEqual(self.m.get(untyped + 0x20) >> 22, self.m.get(typed + 0x20) >> 22, (part, week))
                self.assertEqual((self.m.get(typed + 0x20) >> 22) & 0xFF, weeks - week, (part, week))
                if week < weeks:
                    self.assertEqual((self.m.get(typed + 0x24) >> 28) & 7, 4, (part, week))          # still Out
                    self.assertEqual((self.m.get(untyped + 0x24) >> 28) & 7, 0, (part, week))       # untyped: status lost
            self.assertEqual(self.m.get(typed + 0x20) >> 31, 0)                                     # healthy after the weeks

    def test_a_typed_player_is_out_for_the_weeks_and_never_a_career_ending_injury(self):
        for part in refresh.INJURY_PARTS:
            for weeks in (8, 17):
                choice = refresh.injury_type(part, weeks)
                if choice is None:
                    continue
                for address in self.players[:16]:
                    self.mark(address, weeks, choice)
                    self.assertEqual(self.m.call(0x13E3A0, ecx=address), 0, (part, weeks, choice))   # not career ending
                    self.assertEqual(self.m.call(0x13E190, ecx=address), 4, (part, weeks, choice))   # status Out


if __name__ == "__main__":
    unittest.main()
