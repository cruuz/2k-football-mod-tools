"""b779 au1: the plain Situation mode takes the same playbook decision as Quick Game and Franchise.

Ju3tin, 10/27: "In situation mode, teams playbooks go back to vanilla and they don't have the new plays etc you made."
Game mode 8 is shared by the 25th Anniversary moments and the Situation mode; the Situation flag 0xE6014C is 1 in the
Situation mode and 0 in a moment. The stock-book resolver (0x62902) sent every mode-8 side to its moment decision,
which, with no moment row, falls to the preserved retail bank (E2R-<key>-pb.iff). The current body tests the flag
first. Bounded native proof under Unicorn on the resolver alone (synthetic team record); no gameplay claim here.
"""

import hashlib
import struct
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import nfl2k5_stock_books as books  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256  # noqa: E402

RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')
try:
    import unicorn
except ImportError:
    unicorn = None


class BodyShape(unittest.TestCase):
    def test_current_body_tests_the_situation_flag_and_fits_its_budget(self):
        va = 0x14E3BD0
        current = books.code_for(va)
        v07 = books.code_for(va, situation_flag=False, classic_ids=books.V07_CLASSIC_IDS)
        self.assertNotEqual(current, v07)
        self.assertEqual(len(current), books.CODE_SIZE)
        self.assertIn(b"\x83\x3d" + struct.pack("<I", books.SITUATION_FLAG) + b"\x00", current[:books.TABLE])
        self.assertNotIn(struct.pack("<I", books.SITUATION_FLAG), v07[:books.TABLE])
        self.assertLessEqual(len(current[:books.TABLE].rstrip(b"\xcc")), books.TABLE)
        # Earlier generations are rebuilt exactly as before (the flag defaults off for them).
        old = dict(first_season=books.LEGACY_FIRST_SEASON, classic_ids=None)
        self.assertEqual(books.code_for(va, **old), books.code_for(va, situation_flag=False, **old))
        self.assertEqual(books.code_for(va, legacy=True, **old), books.code_for(va, legacy=True, situation_flag=False, **old))


@unittest.skipUnless(RETAIL.is_file() and unicorn, 'USA retail XBE and Unicorn required')
class SituationModeBooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        cls.Machine = Machine
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise ValueError('USA retail XBE pin differs')
        cls.current = books.apply(cls.retail)[0]
        owned = books.allocation(cls.current)
        # The b776 .. v0.7 body, as the released v0.7 disc holds it.
        cls.v07 = books._write_body(cls.current, owned, books.code_for(owned['va'], situation_flag=False,
                                                                       classic_ids=books.V07_CLASSIC_IDS))

    def machine(self, payload):
        m = self.Machine(payload, trace_writes=False)
        a = m.ARENA
        m.put(a + 0x110, a + 0x300)
        m.put(a + 0x304, a + 0x400)
        m.uc.mem_write(a + 0x400, 'BUF\0'.encode('utf-16le'))
        m.put(0xC8F0D4, a + 0x1000)
        m.put(0xC8F0D8, books.MOMENT_COUNT)
        return m

    def resolve(self, m, *, mode=8, situation=1, category=0, identity=0, ordinal=0, season=2022):
        """True when the side keeps the default decision (the franchise's current book), False for the retail bank."""
        a = m.ARENA
        m.uc.mem_write(a + 0x118, struct.pack('<H', identity))
        m.put(0xE5FF80, mode)
        m.put(books.SITUATION_FLAG, situation)
        m.put(0xBF1858, ordinal)
        m.put(a + 0x128, category)
        m.put(a + 0x508, 1)
        at = a + 0x1000 + ordinal * 0x6C
        m.put(at + 0x1C, season)
        m.put(at + 0x20, season)
        m.uc.mem_write(a + 0x600, b'\xA5' * 32)
        for name, value in dict(EAX=a, EBX=0x1234, EDI=0, ESI=a + 0x600, EBP=a + 0x500, ESP=m.STACK,
                                EFLAGS=0x202).items():
            m.reg(name, value)
        stops = (0x62A1B, 0x62A37)
        hook = m.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, va, *_: uc.emu_stop() if va in stops else None)
        try:
            m.uc.emu_start(books.SITE, m.STOP, count=1000)
        finally:
            m.uc.hook_del(hook)
        self.assertIn(m.reg('EIP'), stops)
        self.assertEqual(m.reg('ESP'), m.STACK)
        modern = m.reg('EIP') == 0x62A1B
        if not modern:
            self.assertEqual(bytes(m.uc.mem_read(a + 0x600, 32)).decode('utf-16le').rstrip('\0'), 'E2R-BUF-pb.iff')
        return modern

    def test_plain_situation_takes_the_club_book_like_quick_game(self):
        m = self.machine(self.current)
        for season in (1990, 2004, 2022):
            self.assertTrue(self.resolve(m, situation=1, category=0, season=season))
            # The same answer Quick Game (mode 4) gives the same side.
            self.assertTrue(self.resolve(m, mode=4, situation=0, category=0, season=season))

    def test_v07_body_sent_plain_situation_to_the_retail_bank(self):
        """The released behaviour: a plain Situation side got the moment decision, so with no moment table loaded, or a
        stale pre-2010 row, it loaded the retail bank (Ju3tin's report; the v0.7 disc showed retail OAK in run S1).
        The current body gives the club book in every one of these states."""
        for count, season in ((0, 2022), (books.MOMENT_COUNT, 1990), (books.MOMENT_COUNT, 2004)):
            old, cur = self.machine(self.v07), self.machine(self.current)
            for m in (old, cur):
                m.put(0xC8F0D8, count)
            self.assertFalse(self.resolve(old, situation=1, category=0, season=season))
            self.assertTrue(self.resolve(cur, situation=1, category=0, season=season))

    def test_historic_and_classic_teams_in_situation_follow_the_other_modes(self):
        m = self.machine(self.current)
        self.assertFalse(self.resolve(m, situation=1, category=4, identity=100))     # a retail historic team
        self.assertFalse(self.resolve(m, mode=4, situation=0, category=4, identity=100))
        for identity in (232, 249, 252):                                             # classic teams of 2010 on
            self.assertTrue(self.resolve(m, situation=1, category=4, identity=identity))
            self.assertTrue(self.resolve(m, mode=4, situation=0, category=4, identity=identity))

    def test_anniversary_moments_are_unchanged(self):
        cur, old = self.machine(self.current), self.machine(self.v07)
        for season in (1958, 2004, 2009, 2010, 2022):
            for category in (0, 4):
                want = books.MODERN_FIRST_SEASON <= season <= books.MODERN_LAST_SEASON
                self.assertEqual(self.resolve(cur, situation=0, category=category, season=season), want)
                self.assertEqual(self.resolve(old, situation=0, category=category, season=season), want)
        # An unloaded moment table still keeps the retail bank in a moment.
        cur.put(0xC8F0D8, 0)
        self.assertFalse(self.resolve(cur, situation=0, season=2022))

    def test_every_classic_team_gets_its_own_era_book(self):
        """b779 au1: each classic team-season, by the identity nfl2k5_classic_teams writes into its file
        (IDENTITIES[list position]), takes its club book from 2010 on and the retail bank before, in Quick Game and in
        Situation. The v0.7 range (231..249) failed two of them: Lions 2008 (231) and Seahawks 2025 (252)."""
        from mod_editor.core import nfl2k5_classic_teams as ct
        data = ct.Data.load()
        cur, old = self.machine(self.current), self.machine(self.v07)
        wrong_v07 = []
        for n, key in enumerate(data.order()):
            identity, season = ct.IDENTITIES[n], data.teams[key]['season']
            want = season >= books.MODERN_FIRST_SEASON
            with self.subTest(team=key, identity=identity):
                self.assertEqual(books.classic_modern(identity), want)
                self.assertEqual(self.resolve(cur, mode=4, situation=0, category=4, identity=identity), want)
                self.assertEqual(self.resolve(cur, situation=1, category=4, identity=identity), want)
            if self.resolve(old, mode=4, situation=0, category=4, identity=identity) != want:
                wrong_v07.append(key)
        self.assertEqual(wrong_v07, ['lions_2008', 'seahawks_2025'])
        # Not classic teams: the created teams 250/251, retail historic teams and the Anniversary team-seasons
        # keep the retail bank, as on v0.7.
        for identity in (250, 251, 120, 170, 176, 225, 0, 253):
            self.assertFalse(self.resolve(cur, mode=4, situation=0, category=4, identity=identity))
            self.assertFalse(self.resolve(old, mode=4, situation=0, category=4, identity=identity))

    def test_v07_body_upgrades_in_place(self):
        self.assertEqual(books.status(self.v07), 'needs_fix')
        fixed, receipt = books.apply(self.v07)
        self.assertEqual(fixed, self.current)
        self.assertTrue(receipt['upgraded_moment_routing'])
        self.assertEqual(books.status(fixed), 'applied')
        self.assertEqual(books.apply(fixed)[0], fixed)


if __name__ == '__main__':
    unittest.main()
