"""mc2: MyCareer controller port, B to quit and the backup prompt (Noah's 2026-10-16 video).

Bounded native fixtures on the pinned USA executable with the Studio's MyCareer owner. No game boot,
display or physical controller. The menu input leaves (F3750/709B0/70A10) are the existing fixture seams.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_supersim_draft_fixture import retail_bytes
from tests.nfl2k5_my_career_played_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster

MAIN_MENU, TEAM_SELECT = 0x515660, 0x51B908


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST and Unicorn required')
class Mc2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload, cls.roster = mode.apply(retail_bytes())[0], retail_roster()

    def career(self, m):
        p = m.create(self.roster, preseason=False)
        m.child_services()
        return p

    def context(self, m):
        return m.get(m.manager + 0x10C)

    def ports(self, m, connected):
        m.replace_stub(0x709B0, lambda: m.ret(int(m.reg('ECX') in connected)))

    def dialogs(self, m):
        texts = []

        def ask():
            p = m.reg('EDX')
            raw = bytes(m.uc.mem_read(p, 200))
            end = next(i for i in range(0, len(raw), 2) if raw[i:i + 2] == b'\0\0')
            texts.append(raw[:end].decode('utf-16le'))
            m.ret(m.dialog_answer, pop=24)
        m.replace_stub(0x14E440, ask)
        return texts

    def pad(self, m, port):
        """Noah's case: one controller, in a port other than 1. Port 1 stays connected but idle."""
        self.ports(m, (0, port))
        for va in (0xF3750, 0xF3780, 0xF3720):
            m.replace_stub(va, lambda: m.ret(m.inputs if m.reg('EDX') == port else 0, pop=4))
        for va in (0x70A10, 0x70A30, 0x709F0):
            m.replace_stub(va, lambda: m.ret(m.inputs if m.reg('ECX') == port else 0))

    def test_play_claims_the_port_that_drives_the_menus(self):
        with Machine(self.payload) as m:
            self.career(m)
            self.assertEqual(m.get(m.state + 32), 0)
            self.ports(m, (0, 1))
            m.put(self.context(m) + 0x594, 1)  # native F3970 records the input's port here
            m.call('claim_port', ecx=m.manager, eax=m.manager)  # local regparm
            self.assertEqual(m.get(m.state + 32), 1)
            for port in (3, 4, 7, 0xFFFFFFFF):  # absent or out-of-range ports never move ownership
                m.put(self.context(m) + 0x594, port)
                m.call('claim_port', ecx=m.manager, eax=m.manager)
                self.assertEqual(m.get(m.state + 32), 1)
            # End to end: A on Play next game from a pad in port 2 (index 1),
            # through the native menu input loop, hands that port to MyPlayer.
            m.put(m.state + 32, 0)
            self.pad(m, 1)
            m.select(0)
            self.assertEqual(m.top(), TEAM_SELECT)
            self.assertEqual(m.get(self.context(m) + 0x594), 1)
            self.assertEqual(m.get(m.state + 32), 1)

    def test_practice_claims_the_port_before_its_descriptor(self):
        with Machine(self.payload) as m:
            self.career(m)
            self.ports(m, (0, 1))
            m.put(self.context(m) + 0x594, 1)
            pushed = []
            m.replace_stub(0x6E390, lambda: (pushed.append((m.reg('EDX'), m.get(m.state + 32))), m.ret()))
            m.call('mode_practice', ecx=m.manager)
            self.assertEqual(pushed, [(m.labels['practice_menu'], 1)])

    def test_b_on_the_apartment_asks_then_quits_to_the_main_menu(self):
        with Machine(self.payload) as m:
            self.career(m)
            texts = self.dialogs(m)
            m.dialog_answer = 3  # No
            m.frame(0x200)
            self.assertEqual(m.top(), m.labels['apartment'])
            self.assertEqual(m.get(m.state + 2672), m.manager)
            self.assertEqual(m.get(0xE576A0), 2)
            self.assertEqual(len(texts), 1)
            m.dialog_answer = 2  # Yes
            m.frame(0x200)
            self.assertEqual((m.depth(), m.top()), (0, MAIN_MENU))
            self.assertEqual(m.get(m.state + 2672), 0)
            self.assertNotEqual(m.get(0xE576A0), 2)

    def test_b_on_the_entry_screen_returns_to_the_main_menu(self):
        with Machine(self.payload) as m:
            m.frontend(self.roster)
            m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
            m.select(1)
            self.assertEqual(m.top(), m.labels['entry_menu'])
            m.frame(0x200)
            self.assertEqual(m.top(), MAIN_MENU)
            self.assertEqual(m.get(m.state + 2672), 0)
            # A new entry works after leaving with B.
            m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
            m.select(1)
            self.assertEqual(m.top(), m.labels['entry_menu'])

    def bench(self, m):
        p = self.career(m)
        # A drafted tier keeps its first depth (start_player skips re-ranking);
        # put him second in both native chains, as a 1st Day QB is placed.
        m.put(m.state + 2744, 1)
        m.put(m.state + 184, 1)
        m.uc.mem_write(p + 41, bytes(((m.uc.mem_read(p + 41, 1)[0] & 3) | 0x24,)))
        return p

    def test_backup_is_told_before_kickoff_and_b_stays_home(self):
        with Machine(self.payload) as m:
            p = self.bench(m)
            texts = self.dialogs(m)
            m.dialog_answer = 0xFFFFFFFF
            m.select(0)
            self.assertEqual(texts, ['MyPlayer is a backup. Yes: start him. No: Supersim to his snaps.'])
            self.assertEqual(m.top(), m.labels['apartment'])
            self.assertEqual(m.uc.mem_read(p + 41, 1)[0] & 0xFC, 0x24)

    def test_backup_no_runs_supersim_to_his_snaps(self):
        with Machine(self.payload) as m:
            self.bench(m)
            m.put(m.state + 2696, 1)  # Supersim Off before the prompt
            self.dialogs(m)
            m.dialog_answer = 3
            m.select(0)
            self.assertEqual(m.top(), TEAM_SELECT)
            self.assertEqual((m.get(m.state + 2696), m.get(m.state + 2708)), (2, 1))

    def test_backup_yes_starts_myplayer_then_plays(self):
        with Machine(self.payload) as m:
            p = self.bench(m)
            self.dialogs(m)
            m.dialog_answer = 2
            m.select(0)
            self.assertEqual(m.top(), TEAM_SELECT)
            self.assertEqual(m.uc.mem_read(p + 41, 1)[0] & 0x1C, 0)
            self.assertEqual(m.get(m.state + 2708), 0)

    def test_starter_sees_no_prompt(self):
        with Machine(self.payload) as m:
            self.career(m)
            texts = self.dialogs(m)
            m.select(0)
            self.assertEqual((texts, m.top()), ([], TEAM_SELECT))

    def free_records(self, m):
        n, pool = m.get(m.root), m.get(m.root + 4)
        return [pool + 84*i for i in range(n) if m.uc.mem_read(pool + 84*i + 8, 1)[0] & 5 == 1]

    def enter(self, m):
        m.frontend(self.roster)
        m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
        m.select(1)
        self.assertEqual(m.top(), m.labels['entry_menu'])

    def test_d01_contradictory_first_free_record_uses_the_next_clean_one(self):
        with Machine(self.payload) as m:
            self.enter(m)
            free = self.free_records(m)
            # The native first-free record (BFF50) now shares a name cell with a real
            # player, as a league that already played a season can leave it. Before mc2
            # this refused with "Roster is full." although 154 other records were free.
            other = m.get(m.root + 4)
            m.put(free[0] + 16, m.get(other + 16))
            self.assertEqual(m.call(0xBFF50), free[0])
            before = bytes(m.uc.mem_read(m.root, len(self.roster) - 64))
            m.select(1)  # Undrafted free agent -> mode_create
            self.assertNotIn(('notice', 'Roster is full.'), m.events)
            self.assertEqual(m.get(0xCB8B14), free[1])
            self.assertEqual(m.get(m.state + 2676), free[1])
            self.assertEqual(m.top(), 0x56F050)  # native Create Player
            self.assertEqual(bytes(m.uc.mem_read(free[0], 84)), before[free[0] - m.root:free[0] - m.root + 84])

    def test_d01_clean_league_keeps_the_native_first_free_record(self):
        with Machine(self.payload) as m:
            self.enter(m)
            free = self.free_records(m)
            self.assertEqual(m.call(0xBFF50), free[0])
            m.select(1)
            self.assertEqual((m.get(0xCB8B14), m.top()), (free[0], 0x56F050))

    def test_d01_no_clean_free_record_still_refuses_without_writes(self):
        with Machine(self.payload) as m:
            self.enter(m)
            for p in self.free_records(m):
                m.uc.mem_write(p + 0x28, b'\xee')
            before = bytes(m.uc.mem_read(m.root, len(self.roster) - 64))
            m.select(1)
            self.assertIn(('notice', 'Roster is full.'), m.events)
            self.assertEqual((m.get(m.state + 2676), m.top()), (0, m.labels['entry_menu']))
            self.assertEqual(bytes(m.uc.mem_read(m.root, len(before))), before)

    def test_d01_skipped_record_career_completes_signing_on_the_clean_record(self):
        with Machine(self.payload) as m:
            original = m.frontend
            dirty = []

            def frontend(roster):
                original(roster)
                free = self.free_records(m)
                m.put(free[0] + 16, m.get(m.get(m.root + 4) + 16))
                dirty.extend(free[:2])
            m.frontend = frontend
            player = self.career(m)  # native CAP, team choice, Sign, capture, Apartment
            self.assertEqual(player, dirty[1])
            self.assertEqual(m.call('primary'), dirty[1])
            self.assertEqual(m.top(), m.labels['apartment'])


if __name__ == '__main__':
    unittest.main()
