"""b780 mc1: Franchise load user-team guard (EMU1 crash_load: bugcheck 0x1E at 0x142BBD after a load).

Static: the 17-byte cave and its one five-byte site, idempotent apply on retail, status, the presets, the last late
owner. Native (Unicorn, pinned USA retail executable and the signed f0 Franchise, the game's own season and
front-office deserializers 0xC5800 / 0x2D0CE0): with no human-controlled club ([0xE5775C + i*4] all 0) the retail
deserializer leaves the user team [0xE3C0A0] at 0 and the Desk's front-office scene 0x142BB0 faults reading
user_team+0x10C (negative control); with the guard the user team is club 0 and the read goes through. A load with a
human club is byte-identical with and without the guard.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_load_user_team_guard as guard  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, XBE  # noqa: E402

HUMAN, USER_TEAM, TEAM_TABLE = 0xE5775C, 0xE3C0A0, 0xE5786C


class StaticTests(unittest.TestCase):
    def test_cave_and_site(self):
        va = 0x150F000
        code = guard.code_for(va)
        self.assertEqual(len(code), guard.CODE_SIZE)
        self.assertEqual(code[0], 0xE8)
        self.assertEqual(va + 5 + struct.unpack_from('<i', code, 1)[0], guard.FIRST_HUMAN_CLUB)
        self.assertEqual(code[5:11], bytes.fromhex('85c0' '7507' '31c9'))
        self.assertEqual(code[11], 0xE8)
        self.assertEqual(va + 16 + struct.unpack_from('<i', code, 12)[0], guard.CLUB_BY_INDEX)
        self.assertEqual(code[16], 0xC3)
        self.assertEqual(code[17:], b'\xcc' * (guard.CODE_SIZE - 17))
        ((name, site, before, after),) = guard.sites(va)
        self.assertEqual((site, before), (0x2D0D53, bytes.fromhex('e81840dfff')))
        self.assertEqual(site + 5 + struct.unpack_from('<i', after, 1)[0], va)

    def test_last_late_owner_and_presets(self):
        from mod_editor.core import mod_build
        self.assertEqual(space.LATE_OWNERS[-1], guard.OWNER)
        for name in ('softdrink_basic', 'softdrink_advanced', 'softdrink_experimental'):
            self.assertIs(mod_build.PRESETS[name]['load_user_team_guard'], True, name)

    @unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required')
    def test_apply_status_and_replay(self):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        retail = retail_bytes()
        self.assertEqual(guard.status(retail), 'retail')
        patched, receipt = guard.apply(retail)
        self.assertEqual(guard.status(patched), 'applied')
        self.assertFalse(receipt['already_applied'])
        again, replay = guard.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(replay['already_applied'])


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, the signed f0 Franchise and Unicorn required')
class NativeLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, signed_save
        cls.retail = retail_bytes()
        cls.save = signed_save()
        cls.guarded = guard.apply(cls.retail)[0]

    def loaded(self, payload, *, human):
        """The f0 Franchise through the game's own season and FO deserializers, its human table set as asked, then
        the FO deserializer again (it recomputes the user team at 0x2D0D53)."""
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(payload, trace_writes=False)
        m.load_franchise(self.save)
        for i in range(34):
            m.put(HUMAN + 4 * i, 0)
        if human is not None:
            m.put(HUMAN + 4 * human, 1)
        m.call(0x2D0CE0, ecx=m.ARENA + 0x996FC, budget=3000000)
        return m

    def desk_scene_read(self, m):
        """0x142BB0 (the Desk's front-office scene) up to just after its user_team+0x10C read."""
        return m.call(0x142BB0, stop=0x142BC3, budget=2000000)

    def test_no_human_club_retail_faults_and_the_guard_uses_club_0(self):
        import unicorn
        m = self.loaded(self.retail, human=None)
        self.assertEqual(m.get(USER_TEAM), 0, 'retail: no human club leaves the user team 0')
        with self.assertRaises(unicorn.UcError):
            self.desk_scene_read(m)
        g = self.loaded(self.guarded, human=None)
        self.assertEqual(g.get(USER_TEAM), g.get(TEAM_TABLE), 'the guard falls back to club 0')
        self.assertEqual([g.get(HUMAN + 4 * i) for i in range(34)], [0] * 34, 'the human table stays as saved')
        self.assertEqual(self.desk_scene_read(g), g.get(g.get(TEAM_TABLE) + 0x10C))

    def test_a_load_with_a_human_club_is_byte_identical(self):
        r = self.loaded(self.retail, human=7)
        g = self.loaded(self.guarded, human=7)
        self.assertEqual(r.get(USER_TEAM), r.get(TEAM_TABLE + 4 * 7))
        self.assertEqual(g.get(USER_TEAM), r.get(USER_TEAM))
        for va, size in ((0xE57000, 0x2000), (0xE3C000, 0x4000), (r.ARENA, 0x100000)):
            self.assertEqual(bytes(g.uc.mem_read(va, size)), bytes(r.uc.mem_read(va, size)), hex(va))


if __name__ == '__main__':
    unittest.main()
