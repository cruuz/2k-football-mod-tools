"""Native final-season completion and year rollover with declared score inputs.

The regular/playoff result grid and final live team score are supplied inputs.
The native postseason/Pro Bowl constructor, played stat writer, result commit,
week/stage advance, year transition and Apartment all execute unchanged.
This does not claim a season of physical games or a played Pro Bowl.
"""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_played_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST and Unicorn required")
class SeasonTests(unittest.TestCase):
    def test_final_played_fixture_native_next_year_and_usable_apartment(self):
        if XBE.stat().st_size > 16 * 1024**2:
            self.skipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail XBE pin differs")
        roster, payload = retail_roster(), mode.apply(retail)[0]
        with Machine(payload) as created:
            created.create(roster, preseason=False)
            source = created.native_save(budget=500000000)
        with Machine(payload) as m:
            m.cold(roster, source)
            # Input precondition: prior regular fixtures completed. Keep the
            # native bye cells and all native roster/history pool structure.
            for i in range(17 * 17):
                at = 0xE57C40 + i * 8
                if m.uc.mem_read(at, 1) != b'\x07':
                    m.uc.mem_write(at, b'\x03')
            m.put(0xE576B4, 17)
            # Includes the two Pro Bowl donor teams needed by season teardown.
            m.call(0x2A7E50, ecx=0, budget=1000000000)
            for week, games in ((17, ((2, 3), (4, 5), (6, 7), (8, 9))),
                                (18, ((2, 10), (4, 11), (6, 12), (8, 13))),
                                (19, ((2, 4), (6, 8))), (20, ((2, 6),))):
                for slot, (home, away) in enumerate(games):
                    i = week * 17 + slot
                    m.uc.mem_write(0xE57C40 + i * 8, bytes((3, home, away, 9, 12, 4, 1, 0)))
                    m.uc.mem_write(0xE587F0 + i * 10, bytes((7, 0, 0, 0, 0, 0, 0, 0, 0, 0)))
            m.uc.mem_write(0xE57C40 + 20 * 136, b'\x00')
            for va, value in ((0xE576A4, 9), (0xE576B4, 20), (0xE576A8, 1)):
                m.put(va, value)
            year = m.get(0xE576B8)
            token = bytes(m.uc.mem_read(m.state + 40, 16))
            m.launch()
            m.appearance()
            m.passing_event()
            # Native team-stat provider CA3F0 sums its five quarter fields.
            # A 7-0 engine score is an explicit boundary input, not a mock of
            # that provider or the native schedule/history commit.
            m.put(0xBF08E0 + 0x254, 7)
            m.finish()
            self.assertEqual(m.get(0xE576B4), 21)
            self.assertEqual(bytes(m.uc.mem_read(0xE587F0 + 20 * 17 * 10, 10)),
                             bytes((7, 0, 0, 0, 0, 0, 0, 0, 0, 0)))
            self.assertEqual(m.get(m.state + 64), 25)
            watermark = m.get(m.state + 68)
            m.select(0, budget=1500000000)
            self.assertEqual(m.get(0xE576B4), 22)
            m.select(0, budget=1500000000)
            self.assertEqual((m.get(0xE576B8), m.get(0xE576A4)), (year + 1, 1))
            self.assertEqual(m.top(), m.labels["apartment"])
            self.assertNotEqual(m.call("primary"), 0)
            self.assertEqual(bytes(m.uc.mem_read(m.state + 40, 16)), token)
            for _ in range(3):
                m.call("settle")
                m.frame()
            self.assertEqual((m.get(m.state + 64), m.get(m.state + 68)), (25, watermark))
            m.select(2)
            self.assertEqual(m.top(), 0x535E70)
            m.frame(0x200)
            self.assertEqual(m.top(), m.labels["apartment"])
            saved = m.native_save(budget=500000000)
        with Machine(payload) as cold:
            cold.cold(roster, saved)
            self.assertEqual(cold.get(0xE576B8), year + 1)
            self.assertEqual(cold.top(), cold.labels["apartment"])
            self.assertNotEqual(cold.call("primary"), 0)
            self.assertEqual((cold.get(cold.state + 64), cold.get(cold.state + 68)), (25, watermark))
            self.assertEqual(bytes(cold.uc.mem_read(cold.state + 40, 16)), token)


if __name__ == "__main__":
    unittest.main()
