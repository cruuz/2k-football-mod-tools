"""b780 b8-mycareer (row C3): in the first three rounds a club takes MyPlayer only if he would start there.

HAIL ST. CLAIR (10/28): "me getting drafted by teams like the giants and bears who have respectable QBs". The draft AI
weighs a club's need by head count (and in round 1 by one fixed table per position), so the quarterback went to whichever
club's turn came first. The MyCareer draft tick now holds the AI's own already-taken flag (0x20) on MyPlayer for one pick
when the club on the clock already has m3_starters[position] players at his position with a native overall (0x246D90,
the Player Card number) at least as high as his, in display rounds 1 to 3.

Native fixtures: the pinned f0 franchise at the untouched Combine, the real CAP, draft AI, pick, signing and cleanup run;
only the services listed in tests/nfl2k5_my_career_*fixture.py are boundaries. The negative control writes 255 into the
starters table (the club always "needs" him), which is exactly the released draft.
"""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career_progression as progression
from mod_editor.core import nfl2k5_draft_ai as ai
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC

# QB K P WR CB FS SS RB FB TE OLB ILB C G T DT DE (retail position codes 0..16)
STARTERS = (1, 1, 1, 3, 2, 1, 1, 1, 1, 1, 2, 2, 1, 2, 2, 2, 2)
VETOES = mode.EXTRA_VA + 76     # M(76): how many picks the gate held MyPlayer back


class SourceTests(unittest.TestCase):
    """Host-only checks of the generated owner (no emulation)."""

    def test_starters_table_and_gate_are_in_the_owner(self):
        _, labels = mode.code_for(0x400000, 0x500000)
        for name in ('club_needs', 'm3_starters', 'm3_draft_tick'):
            self.assertIn(name, labels)
        self.assertEqual(labels['m3_starters'] - 0x400000 < mode.TAG_OFFSET, True)
        source = (ROOT / 'tools/mycareer_mode/runtime.c').read_text(encoding='utf-8')
        table = re.search(r'm3_starters\[17\]=\{([0-9,]+)\}', source)
        self.assertIsNotNone(table)
        self.assertEqual(tuple(int(x) for x in table.group(1).split(',')), STARTERS)
        self.assertIn('G(0xE3C0A8)<3', source)          # display rounds 1 to 3 only
        self.assertIn('CALL0(0x3254d0)', source)        # the club on the clock, the game's own getter

    def test_the_veto_uses_only_the_ai_taken_flag_and_restores_it(self):
        source = (ROOT / 'tools/mycareer_mode/runtime.c').read_text(encoding='utf-8')
        body = source[source.index('void FC m3_draft_tick'):source.index('/* M3 purchases.')]
        self.assertIn('me[8]|=0x20', body)
        self.assertIn('if(veto) me[8]&=0xdf', body)
        # the native pick, the draft AI and the retail need routine stay untouched: no write to any retail address
        self.assertNotRegex(body, r'G\(0x3[0-9a-f]{5}\)\s*=')

    def test_rating_names_live_in_the_m3_ascii_pool_and_the_pools_fit(self):
        blob, labels = mode.code_for(0x400000, 0x500000)
        for key in ('speed', 'agility', 'catch'):
            name = 'm3_rating_' + key
            self.assertGreaterEqual(labels[name], mode.EXTRA_VA + 2160)
            self.assertLess(labels[name], mode.EXTRA_VA + mode.POOL2_END)
        self.assertLessEqual(2160 + 2 * labels['text2_bytes'], mode.POOL2_END)
        self.assertLessEqual(labels['content_end'] - 0x400000, mode.TAG_OFFSET)
        self.assertGreater(mode.TAG_OFFSET - (labels['content_end'] - 0x400000), 0)
        self.assertEqual(len(blob), mode.CODE_SIZE)

    def test_the_text_scratch_buffer_is_clear_of_both_pools_and_the_league_menu(self):
        source = (ROOT / 'tools/mycareer_mode/runtime.c').read_text(encoding='utf-8')
        self.assertNotIn('m3+2700', source)
        self.assertEqual(source.count('m3+3200'), 6)
        # 190 characters (380 bytes) from +3200 end before the +3600 league menu
        self.assertEqual(source.count('m3+3200,190'), 3)
        self.assertLessEqual(3200 + 2 * 190, 3600)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, signed f0 and Unicorn required')
class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, signed_save
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        signed_save()  # precise private-evidence skip comes from the fixture
        cls.payload = mode.apply(ai.apply(retail_bytes())[0])[0]
        cls.roster = retail_roster()

    # ---- helpers over the live league -------------------------------------------------------------------------
    def machine(self):
        from tests.nfl2k5_my_career_draft_fixture import Machine
        return Machine(self.payload)

    @staticmethod
    def iovr(m, p):
        return m.call(0x246D90, ecx=p, edx=0)

    @staticmethod
    def set_ratings(m, p, value):
        for field, _, _ in progression.FIELDS:
            m.uc.mem_write(p + field, bytes((value,)))

    @staticmethod
    def position(m, p):
        return m.uc.mem_read(p + 0x35, 1)[0]

    def team(self, m, club):
        return m.get(m.root + 0x1C) + 500 * club

    def roster_of(self, m, club):
        t = self.team(m, club)
        return [m.get(t + 4 * i) for i in range(m.uc.mem_read(t + 0x11C, 1)[0])]

    def model_needs(self, m, club, me):
        """The rule, written independently of the C: fewer than STARTERS[pos] teammates at his position have a native
        overall at least as high as his (0 overall means unavailable: do not block)."""
        mine, pos = self.iovr(m, me), self.position(m, me)
        if not mine or pos >= 17:
            return True
        ahead = sum(1 for q in self.roster_of(m, club)
                    if q != me and self.position(m, q) == pos and self.iovr(m, q) >= mine)
        return ahead < STARTERS[pos]

    # ---- club_needs: the rule at every position ----------------------------------------------------------------
    def test_club_needs_matches_the_rule_at_every_position(self):
        with self.machine() as m:
            m.prepare_draft(self.roster, complete=False)
            me = m.get(0xCB8B14)
            for pos in range(17):
                with self.subTest(position=pos):
                    club = next((c for c in range(32)
                                 if sum(self.position(m, q) == pos for q in self.roster_of(m, c)) >= STARTERS[pos]), None)
                    self.assertIsNotNone(club, 'no club has enough players at the position for this check')
                    t = self.team(m, club)
                    same = [q for q in self.roster_of(m, club) if self.position(m, q) == pos]
                    m.uc.mem_write(me + 0x35, bytes((pos,)))
                    self.set_ratings(m, me, 90)
                    for q in same:
                        self.set_ratings(m, q, 0)
                    mine = self.iovr(m, me)
                    self.assertGreater(mine, 0)
                    k = STARTERS[pos]
                    # nobody at his position is as good: the club needs him
                    self.assertEqual(m.call('club_needs', ecx=t, edx=me), 1)
                    # k-1 clearly better players: one starting job is still open
                    for q in same[:k - 1]:
                        self.set_ratings(m, q, 99)
                        self.assertGreaterEqual(self.iovr(m, q), mine)
                    self.assertEqual(m.call('club_needs', ecx=t, edx=me), 1)
                    # k clearly better players fill every starting job: no need
                    self.set_ratings(m, same[k - 1], 99)
                    self.assertGreaterEqual(self.iovr(m, same[k - 1]), mine)
                    self.assertEqual(m.call('club_needs', ecx=t, edx=me), 0)
                    self.assertEqual(self.model_needs(m, club, me), False)
                    # an equal overall blocks (at least as high), a lower one does not
                    self.set_ratings(m, same[k - 1], 90)
                    self.assertEqual(self.iovr(m, same[k - 1]) >= mine, self.model_needs(m, club, me) is False)
                    self.assertEqual(m.call('club_needs', ecx=t, edx=me), int(self.model_needs(m, club, me)))
                    # a record that is not on the roster being scanned and is MyPlayer himself never blocks
                    self.assertEqual(self.iovr(m, me), mine)
            # overall 0 (unavailable) never vetoes
            m.uc.mem_write(me + 0x35, bytes((0,)))
            self.set_ratings(m, me, 0)
            if self.iovr(m, me) == 0:
                self.assertEqual(m.call('club_needs', ecx=self.team(m, 0), edx=me), 1)

    # ---- the draft tick ----------------------------------------------------------------------------------------
    def start_draft(self, m, *, blocked_picks, ratings=95):
        """Prepare a created QB, begin the draft, and make the clubs of the first picks `blocked_picks` hold a quarterback
        that is at least as good (99 in every attribute). Returns (me, order, blocked_clubs)."""
        me = m.prepare_draft(self.roster, ratings=ratings, position=0)
        m.select(0, budget=200000000)
        self.assertEqual(m.get(0xE576A4), 5)
        order = [m.uc.mem_read(0xE3C0B4 + i, 1)[0] for i in range(224)]
        for rnd in range(7):
            self.assertEqual(sorted(order[rnd * 32:rnd * 32 + 32]), list(range(32)), 'the draft order is not in memory')
        blocked = []
        for pick in range(blocked_picks):
            club = order[pick]
            qbs = [q for q in self.roster_of(m, club) if self.position(m, q) == 0]
            self.assertTrue(qbs, 'the club has no quarterback to make better')
            self.set_ratings(m, qbs[0], 99)
            self.assertGreaterEqual(self.iovr(m, qbs[0]), self.iovr(m, me))
            blocked.append(club)
        return me, order, blocked

    def run_ticks(self, m, me, order, limit=40):
        """Run one pick per frame until MyPlayer is drafted; check the model before every pick."""
        expected = 0
        for step in range(limit):
            rnd, pick = m.get(0xE3C0A8), m.get(0xE3C0A4)
            club = order[rnd * 32 + pick]
            flags = m.uc.mem_read(me + 8, 1)[0]
            self.assertEqual(flags & 0x34, 0x14, 'MyPlayer must be an undrafted prospect with the taken flag clear')
            needs = self.model_needs(m, club, me)
            if rnd < 3 and not needs:
                expected += 1
            m.frame(budget=6000000000)
            after = m.uc.mem_read(me + 8, 1)[0]
            if not after & 0x10:
                return dict(step=step, round=rnd, pick=pick, club=club, needs=needs, expected=expected,
                            vetoes=m.get(VETOES))
            # the hold lasts one pick only: he is still an available prospect with the flag clear
            self.assertEqual(after & 0x34, 0x14, f'the taken flag leaked after pick {step}')
            self.assertEqual(m.get(VETOES), expected)
        self.fail(f'MyPlayer was not drafted in {limit} picks')

    def test_released_behaviour_drafts_a_quarterback_to_the_club_with_a_better_one(self):
        """Negative control: with the starters table at 255 every club "needs" him, which is the released draft."""
        with self.machine() as m:
            me, order, blocked = self.start_draft(m, blocked_picks=3)
            m.uc.mem_write(m.labels['m3_starters'], bytes([255] * 17))
            result = self.run_ticks(m, me, order)
            self.assertEqual(result['vetoes'], 0)
            self.assertEqual(result['club'], blocked[0])      # the first club on the clock, with a better quarterback
            self.assertEqual((result['round'], result['pick']), (0, 0))

    def test_gate_skips_clubs_with_a_better_starter_and_takes_the_first_club_that_needs_him(self):
        with self.machine() as m:
            me, order, blocked = self.start_draft(m, blocked_picks=3)
            result = self.run_ticks(m, me, order)
            self.assertNotIn(result['club'], blocked)
            self.assertTrue(result['needs'], 'a club that has better starters cannot draft him in rounds 1 to 3')
            self.assertGreaterEqual(result['pick'], 3)         # the three clubs with a 99 quarterback were passed
            self.assertEqual(result['round'], 0)
            self.assertEqual(result['vetoes'], result['expected'])
            self.assertGreaterEqual(result['vetoes'], 3)
            # one native signing, on the club the model chose, and the record is a normal signed rookie
            self.assertEqual(len(m.native_signings), 1)
            self.assertEqual(m.native_signings[0]['stage'], 5)
            self.assertEqual(m.uc.mem_read(me + 8, 1)[0] & 0x30, 0)
            self.assertEqual([c for c in range(32) if me in self.roster_of(m, c)], [result['club']])

    def test_from_round_four_the_ai_alone_decides(self):
        """The gate is for display rounds 1 to 3: in round 4 a club with a better starter may still take him."""
        with self.machine() as m:
            me = m.prepare_draft(self.roster, ratings=95, position=0)
            m.select(0, budget=200000000)
            order = [m.uc.mem_read(0xE3C0B4 + i, 1)[0] for i in range(224)]
            m.put(0xE3C0A8, 3)
            m.put(0xE3C0A4, 0)
            club = order[3 * 32]
            qbs = [q for q in self.roster_of(m, club) if self.position(m, q) == 0]
            self.set_ratings(m, qbs[0], 99)
            self.assertFalse(self.model_needs(m, club, me))
            m.frame(budget=6000000000)
            self.assertEqual(m.get(VETOES), 0)
            self.assertFalse(m.uc.mem_read(me + 8, 1)[0] & 0x10, 'the AI took him in round 4 despite the better starter')
            self.assertEqual([c for c in range(32) if me in self.roster_of(m, c)], [club])


if __name__ == '__main__':
    unittest.main()
