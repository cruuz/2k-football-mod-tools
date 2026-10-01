"""Noah's 2026-09-23 recordings (job vb1): MyCareer bugs A4, A3 and A2.

A4: the native Create Player initializer (0xC0A80), its Birth Year row handlers (0x343D20 up, 0x343D70 down,
0x346B50 display) and MyCareer's own creation entry. A3: the prior-season sim's league context. A2: Noah's
post-season MyNFL2 roster with the practice squad installed. All execute under Unicorn on the pinned retail
executable; no emulator.
"""
from pathlib import Path
import hashlib
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC

#: Noah's MyNFL2 Franchise save (private; extracted read-only from his xemu HDD by tools/nfl2k5_xemu_saves.py). It was
#: written by the 2026-09-23 video disc after a simulated season.
MYNFL2 = Path(os.environ.get("NFL2K5_VB1_MYNFL2", "/media/noah/Storage/.b76-research/vb1/saves/"
                             "12051C2F122C-MyNFL2/UDATA/53450030/12051C2F122C/SAVEGAME.DAT"))


def birth_raw(m, player):
    return (m.get(player + 0x18) >> 21) & 0x7F


def shown_year(m):
    """The Birth Year row's text, from the native display handler."""
    buffer = m.call(0x346B50, budget=200000)
    raw = bytes(m.uc.mem_read(buffer, 16))
    return raw[:raw.index(b"\0\0") + (raw.index(b"\0\0") % 2)].decode("utf-16le")


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA retail XBE, ROST and Unicorn required")
class BirthYearTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        cls.roster = retail_roster()
        cls.retail_year = mode.apply(retail)[0]
        cls.year_2026 = mode.apply(season.apply(retail, groups=("year", "created_player_dates"), year=2026)[0])[0]

    def created(self, payload):
        """Game Modes > MyCareer > Undrafted free agent: the native Create Player is open."""
        from tests.nfl2k5_my_career_played_fixture import Machine
        m = Machine(payload)
        m.frontend(self.roster)
        for rng in (0xB12680, 0xE5FCA0):
            m.call(0x48BE0, ecx=rng, edx=12345)
        m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
        m.select(1)
        m.select(1)
        player = m.get(0xCB8B14)
        self.assertEqual(m.get(m.state + 2676), player)
        self.assertEqual(m.top(), 0x56F050, "native Create Player screen")
        return m, player

    def test_retail_year_executable_defaults_to_1982(self):
        with self.created(self.retail_year)[0] as m:
            player = m.get(0xCB8B14)
            self.assertEqual(birth_raw(m, player), 82)
            self.assertEqual(shown_year(m), "1982")
            # January 1st stays the native default.
            word = m.get(player + 0x18)
            self.assertEqual(((word >> 12) & 15, (word >> 16) & 31), (1, 1))

    def test_2026_executable_defaults_to_2004_and_follows_the_season_index(self):
        m, player = self.created(self.year_2026)
        with m:
            self.assertEqual(birth_raw(m, player), 104)
            self.assertEqual(shown_year(m), "2004")
        # A draft-path creation happens at season index 1 (the 2027 draft):
        # mode_draft's creation entry after the prior season (M(0) == 2).
        from tests.nfl2k5_my_career_played_fixture import Machine
        with Machine(self.year_2026) as m:
            m.frontend(self.roster)
            m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
            m.select(1)
            self.assertEqual(m.top(), m.labels["entry_menu"])
            m.put(mode.EXTRA_VA, 2)
            m.put(0xE576A4, 4)
            m.put(0xE576B8, 1)
            m.call("mode_draft", ecx=m.manager, budget=2000000)
            self.assertEqual(m.top(), 0x56F050, "native Create Player screen")
            self.assertEqual(birth_raw(m, m.get(0xCB8B14)), 105)
            self.assertEqual(shown_year(m), "2005")

    def test_birth_year_row_steps_1981_to_2008(self):
        m, player = self.created(self.year_2026)
        with m:
            def put_raw(raw):
                word = m.get(player + 0x18)
                m.put(player + 0x18, (word & ~0x0FE00000) | (raw << 21))
            for start, up, down in ((104, 105, 103), (108, 81, 107), (81, 82, 108), (84, 85, 83)):
                put_raw(start)
                m.call(0x343D20, budget=100000)
                self.assertEqual(birth_raw(m, player), up, ("up", start))
                put_raw(start)
                m.call(0x343D70, budget=100000)
                self.assertEqual(birth_raw(m, player), down, ("down", start))
            for raw, text in ((81, "1981"), (99, "1999"), (100, "2000"), (108, "2008")):
                put_raw(raw)
                self.assertEqual(shown_year(m), text)

    def test_season_create_player_defaults_to_2004_without_mycareer_creation(self):
        # The season option now updates the shared native initializer too.
        from tests.nfl2k5_my_career_played_fixture import Machine
        with Machine(self.year_2026) as m:
            m.frontend(self.roster)
            player = m.call(0xBFF50, budget=200000)
            m.call(0xC0A80, ecx=player, budget=200000)
            self.assertEqual(birth_raw(m, player), 104)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST, FONT and Unicorn required")
class PriorSeasonScreenTests(unittest.TestCase):
    """A3: the prior-season sim's own frames draw the MyCareer progress title."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        sys.path.insert(0, str(ROOT / "tools"))
        from nfl2k5_scorebug_projection import read_fonts
        cls.payload, cls.roster = mode.apply(retail_bytes())[0], retail_roster()
        try:
            cls.fonts = read_fonts(XBE.parent / "vc_53450030/0")
        except (OSError, ValueError) as exc:
            raise unittest.SkipTest(f"pinned bounded FONT evidence unavailable: {exc}") from exc

    def test_league_context_draws_title_and_note_only_while_the_prior_season_runs(self):
        from tests.mod_editor.test_nfl2k5_my_career_m3_menus import Machine
        league = mode.EXTRA_VA + 3600
        with Machine(self.payload) as m:
            m.frontend(self.roster)
            m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
            m.select(1)
            sims = []

            def sim():
                # The native week/stage advance is outside this proof; it only
                # records the context it is given and moves the week on.
                sims.append(m.reg("ECX"))
                m.put(0xE576B4, m.get(0xE576B4) + 1)
                m.ret()
            for va in (0x247D40, 0x2480B0):
                m.replace_stub(va, sim)
            m.select(0, budget=500000000)  # Enter the draft, the native Yes
            self.assertEqual(m.top(), m.labels["m3_progress_menu"])
            self.assertEqual(m.get(mode.EXTRA_VA), 1)
            m.fonts(self.fonts)
            m.frame()
            self.assertEqual(sims, [league])
            self.assertEqual(m.get(mode.EXTRA_VA), 1)
            self.assertEqual(m.get(league + 0x100), 0)
            descriptor = m.get(league)
            self.assertEqual(m.get(descriptor + 4), 0, "no hook table")
            self.assertEqual(m.get(descriptor + 8), m.labels["m3_sim_draw"])
            # 0x177990 hands the league context to 0x6E6E0, which dispatches
            # render events 9, 7 and 8 through the native 0x6E4E0.
            texts = []
            for event in (9, 7, 8):
                m.draws.clear()
                m.call(0x6E4E0, ecx=league, eax=league, args=(event,), budget=3000000)
                texts += [d for d in m.draws if d["text"].strip()]
            self.assertEqual([d["text"] for d in texts],
                             ["Preparing the prior season",
                              "The league is playing the year before your rookie season."])
            for draw in texts:
                self.assertTrue(draw["vertices"])
                self.assertTrue(all(20 <= p[0] <= 620 and 150 <= p[1] <= 330 for p in draw["vertices"]),
                                draw["text"])
            # Once the class is ready (M(0) == 2) the same frames draw nothing.
            m.put(mode.EXTRA_VA, 2)
            m.draws.clear()
            m.call(0x6E4E0, ecx=league, eax=league, args=(7,), budget=3000000)
            self.assertEqual([d for d in m.draws if d["text"].strip()], [])


@unittest.skipUnless(HAVE_UC and XBE.is_file() and MYNFL2.is_file(),
                     "pinned retail XBE, Unicorn and Noah's private MyNFL2 save required")
class DraftPathCreationTests(unittest.TestCase):
    """A2 on Noah's own post-season roster: the AFC and NFC all-star teams are cut to 40 with old players past the
    count. With the practice squad installed, owner() used to call every player owned, ps_fa_add refused the Create
    Player slot, mode_created() saw no free-agent entry and the native completion popped to the main menu."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_practice_squad as ps
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.payload = mode.apply(ps.apply(retail)[0])[0]
        cls.save = MYNFL2.read_bytes()

    def machine(self):
        from tests.nfl2k5_my_career_mode_fixture import Machine
        m = Machine(self.payload)
        m.uc.mem_write(m.SAVE, self.save)
        m.root = m.SAVE + 0x320
        m.put(0xB72918, m.root)
        m.call(0xC0500, ecx=m.root, budget=20000000)
        m.put(0xE576A4, 5)
        return m

    def stale_all_star_teams(self, m):
        names = []
        table = m.get(m.root + 0x1C)
        for i in range(m.get(m.root + 0x18)):
            t = table + 500 * i
            active = m.uc.mem_read(t + 0x11C, 1)[0]
            if any(m.get(t + 4 * j) for j in range(active, 65)) and m.get(t + 0x128) == 1:
                text = m.get(t + 0x104)
                names.append(bytes(m.uc.mem_read(text, 6)).decode("utf-16le"))
        return names

    def test_the_saved_roster_has_the_all_star_shape(self):
        with self.machine() as m:
            self.assertEqual(sorted(self.stale_all_star_teams(m)), ["AFC", "NFC"])
            self.assertEqual(m.get(m.root + 0x38), 0)

    def test_guarded_appends_accept_players_again(self):
        with self.machine() as m:
            fa = m.root + 0x38
            p = m.call(0xBFF50, budget=200000)
            self.assertEqual(m.call(0x242560, ecx=fa, edx=p, budget=500000), 1)
            self.assertEqual(m.get(fa), 1)
            team = m.get(m.root + 0x1C)
            pool, count = m.get(m.root + 4), m.get(m.root)
            free = [pool + 84 * i for i in range(count)
                    if m.uc.mem_read(pool + 84 * i + 8, 1)[0] & 5 == 1 and pool + 84 * i != p]
            active = m.uc.mem_read(team + 0x11C, 1)[0]
            from mod_editor.core import nfl2k5_practice_squad as ps
            self.assertEqual(m.call(ps.SYMBOLS["ps_append"], ecx=team, edx=free[0], budget=500000), 1)
            self.assertEqual(m.call(ps.SYMBOLS["ps_ir_append"], ecx=team, edx=free[1], budget=500000), 1)
            self.assertEqual(m.uc.mem_read(team + 0x11C, 1)[0], active + 2)

    def test_create_player_completion_reaches_choose_team(self):
        with self.machine() as m:
            manager = m.BODIES
            for index, descriptor in enumerate((0x515660, 0x5015CC, m.labels["entry_menu"], 0x56F050)):
                m.put(manager + index * 8, descriptor)
            m.put(manager + 0x100, 3)
            m.put(manager + 0x10C, manager + 0x1000)
            # Render/destroy dispatch and notification subscribers are services, as in the creation boundary test.
            m.replace_stub(0x6E4E0, lambda: m.ret(pop=4))
            m.replace_stub(0x110E60, lambda: m.ret())
            p = m.call(0xBFF50, budget=200000)
            m.put(m.state + 2672, manager)
            m.put(m.state + 2676, p)
            m.put(m.state + 2680, 1)
            m.put(0xCB8B14, p)
            m.put(0xCB8BA0, 0)
            m.call(0x346C50, ecx=manager, budget=3000000)
            self.assertEqual(m.get(m.root + 0x38), 1)
            self.assertEqual(m.get(manager + 0x100), 3)
            self.assertEqual(m.get(manager + 24), m.labels["team_menu"])
            self.assertEqual(m.get(m.state + 2680), 2)


if __name__ == "__main__":
    unittest.main()
