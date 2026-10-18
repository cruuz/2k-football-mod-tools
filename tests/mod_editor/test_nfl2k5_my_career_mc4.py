"""mc4 (Noah, 2026-10-18 video): the prior-season sim stays black between weeks.

While Enter the Draft simulates the year before the rookie season, every week is one update frame of the real
MyCareer progress menu (m3_boot_tick runs a native league week inside it). The week's own frames draw the
draw-only league context (black, two lines, the native sim ticker); between weeks the manager drew the real
progress menu natively: the Giants menu with the ESPN header and the QUIT TO MAIN MENU row came up for about
one frame per week. The progress menu's handler now draws exactly what the league context draws, and draws no
native menu, while the prior season runs (M(0) == 1). Everything else about the frame is unchanged.

Native (Unicorn, pinned USA XBE, retail ROST/FONT/LAYT/MRKS; no display, xemu or pad): the real route to the
progress menu, the real update frames with the native league week replaced by a counter, and the native menu
draw functions (background 6C080/F2810, rows 150260, caption F26F0) observed by code hooks.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_supersim_draft_fixture import retail_bytes
from tests.nfl2k5_my_career_draft_fixture import Machine as DraftMachine
from tests.nfl2k5_my_career_mode4_fixture import Machine as FontMachine
from tests.nfl2k5_my_career_navigation_fixture import resources, install as navigation
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster

ENTRY, CREATE_PLAYER = 0x5015CC, 0x56F050
LEAGUE = mode.EXTRA_VA + 3600
TITLE, NOTE = "Preparing the prior season", "The league is playing the year before your rookie season."
#: The native menu draw: background scene (F2810 -> 6C080), rows (150260) and the caption (F26F0).
NATIVE_DRAW = (0xF2810, 0x6C080, 0x150260, 0xF26F0)


class Machine(DraftMachine, FontMachine):
    pass


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, FONT, LAYT, MRKS and Unicorn required')
class QuietProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload, cls.roster = mode.apply(retail_bytes())[0], retail_roster()
        cls.navigation = resources()
        from nfl2k5_scorebug_projection import read_fonts
        try:
            cls.fonts = read_fonts(XBE.parent / 'vc_53450030/0')
        except (OSError, ValueError) as exc:
            raise unittest.SkipTest(f'pinned bounded FONT evidence unavailable: {exc}') from exc

    def progress(self, m, finish_after=None):
        """Enter the draft on the real route; the native league week is a counter (the draw is what is tested)."""
        m.frontend(self.roster)
        m.call(0x6E390, ecx=m.manager, edx=ENTRY)
        m.select(1)
        m.select(0, budget=500000000)
        self.assertEqual(m.top(), m.labels['m3_progress_menu'])
        self.assertEqual(m.get(mode.EXTRA_VA), 1)
        m.fonts(self.fonts)
        navigation(m, self.navigation)
        m.sims = []

        def sim():
            m.sims.append(m.reg('ECX'))
            m.put(0xE576B4, m.get(0xE576B4) + 1)
            if finish_after is not None and len(m.sims) >= finish_after:
                m.put(0xE576A4, 4)
                m.put(0xE576B8, 1)
            m.ret()
        for va in (0x247D40, 0x2480B0):
            m.replace_stub(va, sim)
        m.replace_stub(0x48BC0, None)
        m.native_draws = []
        for va in NATIVE_DRAW:
            m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: m.native_draws.append(1), begin=va, end=va))

    @staticmethod
    def drawn(m, events, *, league=False):
        out = []
        for event in events:
            m.draws.clear()
            if league:
                m.call(0x6E4E0, ecx=LEAGUE, eax=LEAGUE, args=(event,), budget=3000000)
            else:
                m.event(event, budget=8000000)
            out.append([(d['text'], d['font'], d['position'], d['color'], d['vertices'])
                        for d in m.draws if d['text'].strip()])
        return out

    def test_between_weeks_the_manager_draws_exactly_what_the_sim_frames_draw(self):
        with Machine(self.payload) as m:
            self.progress(m)
            m.frame(budget=500000000)                       # one native league week: the league context exists
            self.assertEqual(m.sims, [LEAGUE])
            sim = self.drawn(m, (9, 7, 8), league=True)
            self.assertEqual([[t[0] for t in e] for e in sim], [[], [TITLE, NOTE], []])
            m.native_draws.clear()
            manager = self.drawn(m, (9, 7, 8))
            # Same strings, fonts, positions, tints and glyph vertices, and no native menu draw at all.
            self.assertEqual(manager, sim)
            self.assertEqual(m.native_draws, [])

    def test_the_week_flow_is_the_same_with_the_draws_between_frames(self):
        with Machine(self.payload) as m:
            self.progress(m, finish_after=6)
            seen = []
            for frame in range(5):
                m.frame(budget=500000000)
                self.drawn(m, (9, 7, 8))
                seen.append((m.get(0xE576B4), m.get(mode.EXTRA_VA), m.get(mode.EXTRA_VA + 4), m.depth(), m.top()))
                # M(0) == 1 only ever coincides with the progress menu on top, so the handler's quiet path
                # can never draw over another owned menu.
                self.assertEqual(m.top(), m.labels['m3_progress_menu'])
            self.assertEqual([s[0] for s in seen], [1, 2, 3, 4, 5])
            self.assertEqual({s[1] for s in seen}, {1})
            self.assertEqual([s[2] for s in seen], [1, 2, 3, 4, 5])
            self.assertEqual(m.sims, [LEAGUE] * 5)
            self.assertEqual(m.native_draws, [])
            # The sixth week brings the league to the draft; the next update frame sees it: M(0) becomes 2 and the
            # native Create Player screen opens without another league call.
            m.frame(budget=500000000)
            self.assertEqual((len(m.sims), m.get(mode.EXTRA_VA)), (6, 1))
            m.frame(budget=500000000)
            self.assertEqual((m.get(mode.EXTRA_VA), m.top()), (2, CREATE_PLAYER))
            self.assertEqual(len(m.sims), 6)

    def test_the_native_menu_draws_again_when_the_season_did_not_finish(self):
        # 41 weeks without the league reaching the draft is the existing failure: M(0) = 3 and a notice. The menu
        # is then the native Giants screen (title, the Quit row); it no longer repeats the misleading
        # "league is playing" line there.
        with Machine(self.payload) as m:
            self.progress(m)
            for _ in range(41):
                m.frame(budget=500000000)
            self.assertEqual(m.get(mode.EXTRA_VA), 3)
            self.assertEqual(m.top(), m.labels['m3_progress_menu'])
            self.assertEqual([e for e in m.events if isinstance(e, tuple)][-1][0], 'notice')
            m.native_draws.clear()
            texts = self.drawn(m, (9, 7, 8))
            self.assertEqual(set(m.native_draws), {1})
            self.assertGreaterEqual(len(m.native_draws), 3)
            self.assertEqual(texts, [[], [], []])

    def test_other_owned_menus_still_draw_natively(self):
        # The entry menu (M(0) == 0) goes through the unchanged native draw, with its own rows.
        with Machine(self.payload) as m:
            m.frontend(self.roster)
            m.call(0x6E390, ecx=m.manager, edx=ENTRY)
            m.select(1)
            self.assertEqual(m.top(), m.labels['entry_menu'])
            self.assertEqual(m.get(mode.EXTRA_VA), 0)
            m.fonts(self.fonts)
            navigation(m, self.navigation)
            hits = []
            for va in NATIVE_DRAW:
                m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: hits.append(1), begin=va, end=va))
            m.draw()
            self.assertGreaterEqual(len(hits), 2)
            rows = {r['text'] for r in m.native_rows if r['text']}
            self.assertTrue({'Enter the draft', 'Undrafted free agent', 'Quit to main menu'} <= rows, rows)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, FONT, LAYT, MRKS and Unicorn required')
class QuietProgressWithCareerHomeTests(QuietProgressTests):
    """The same proofs on the image that also carries the Career Home section (the b775 test disc's layout)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from mod_editor.core import nfl2k5_my_career_home as home
        cls.payload = home.apply(cls.payload)[0]
        assert mode.status(cls.payload) == 'applied' and home.status(cls.payload) == 'applied'

    def test_other_owned_menus_still_draw_natively(self):
        self.skipTest('the entry menu is covered on the plain image; Career Home only replaces the Apartment')


if __name__ == '__main__':
    unittest.main()
