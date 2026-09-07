"""Generic inline identity through native assignment and play-call predicates.

These are bounded control decisions, not snaps, drives or a witnessed game.
"""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_save_rost as roster
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, draft_save
from tests.nfl2k5_my_career_mode_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_inline import block_for


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE and Unicorn required")
class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.payload = mode.apply(retail)[0]

    def load(self, m, position, away=False):
        source = bytearray(draft_save())
        record = roster.decode(source).by_key["primary", 0].offset
        source[record + 0x35] = position
        m.native_load(bytes(source) + block_for(source))
        m.team = m.get(m.root + 0x1C)
        match = 0xB321A0 if away else 0xB30C4C
        side = 0xE5FC60 if away else 0xE5FC20
        m.call(0xC3C60, ecx=m.team, edx=match)
        m.put(0xE60268, m.BODIES + 0x8000)
        for i in range(22):
            body = m.BODIES + 0x8000 + i * 0x100
            m.put(body + 0x30, body + 0x100 if i < 21 else 0)
            m.put(body + 0x3C, match + 84 * int(i != 0))
            m.put(body + 0x38, side)
        m.put(0xE576A4, 8)
        m.put(0xE5FF80, 5)
        m.put(0xE602B4, 4)
        m.put(0xE602B8, 11)
        m.put(0xE60280, 0xE5FC20)
        m.put(0xE60284, 0xE5FC60)
        m.put(0xE5FC2C, m.BODIES + 0xC000)
        m.put(0xE5FC6C, m.BODIES + 0xC100)
        m.call(0x1561C0, args=(0,))
        return m.BODIES + 0x8000, side

    def test_all_positions_on_both_sides_control_only_the_owned_body(self):
        offense, defense = {0, 3, 7, 8, 9}, {4, 5, 6, 10, 11, 15, 16}
        for position in range(17):
            for away in (False, True):
                with self.subTest(position=position, away=away), Machine(self.payload) as m:
                    body, side = self.load(m, position, away)
                    self.assertEqual(m.call("mode_unit_present"), body)
                    self.assertEqual(m.get(0xBD8210), 0)
                    for i in range(1, 22):
                        self.assertEqual(m.get(body + 0x100 * i + 0x44), 0)
                        self.assertEqual(m.get(0xBD8210 + 36 * i), 0xFFFFFFFF)
                    self.assertEqual(m.get(0xE5FC50), 0)
                    self.assertEqual(m.get(0xE5FC90), 0)
                    expected = int(position in (defense if away else offense))
                    self.assertEqual(m.call(0x1891B0, ecx=side), expected)
                    # Change possession using the same two native team objects.
                    m.put(0xE60280, 0xE5FC60)
                    m.put(0xE60284, 0xE5FC20)
                    self.assertEqual(m.call(0x1891B0, ecx=side),
                                     int(position in (offense if away else defense)))

    def test_absent_duplicate_cycle_and_special_teams_use_cpu_calls(self):
        for kind in ("absent", "duplicate", "cycle", "special"):
            with self.subTest(kind=kind), Machine(self.payload) as m:
                body, side = self.load(m, 0)
                self.assertEqual(m.call(0x1891B0, ecx=side), 1)
                if kind == "absent":
                    m.put(body + 0x48, 1)
                elif kind == "duplicate":
                    m.put(body + 0x100 + 0x3C, m.get(body + 0x3C))
                elif kind == "cycle":
                    m.put(body + 21 * 0x100 + 0x30, body)
                else:
                    m.put(0xE602B4, 1)
                self.assertEqual(m.call(0x1891B0, ecx=side), 0)


if __name__ == "__main__":
    unittest.main()
