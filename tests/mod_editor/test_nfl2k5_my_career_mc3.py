"""mc3: MyCareer draft preparation after other modes, and draft-path save/load (b775).

D01 (Noah 2026-10-16, Oct 13 disc): MyCareer > Enter the draft showed "Roster is full." after the prior season,
then "Draft preparation failed. Quit and try again." His boot had put the Quick Game away side on a historic team
(Packers '96) and then pressed Random Team, which left that team, 53 players, in the USER2 spare slot. The Oct 13
(and public v0.6) main roster has 13 free player records whose two name cells are not adjacent; with 53 records
taken, the game's own first free record (BFF50) is one of them, and MyCareer refused the whole career.

These tests use the played discs' own executable, roster and historic files (read only) and skip without them.
Retail-fixture tests cover a loaded career, quit, then a new career. EXPERIMENTAL / UNWITNESSED: offline evidence.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_my_career_mode as mode  # noqa: E402
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC  # noqa: E402

DISCS = Path(os.environ.get("NFL2K5_DISC_FOLDER", "/media/noah/Storage/2K5 Discs"))
OCT13_DISC = Path(os.environ.get("NFL2K5_IC1_BASE", DISCS / "SOFTDRINK 2K28 v0.6.1 fixes (2026-10-13).xiso.iso"))
V06_DISC = DISCS / "SOFTDRINK 2K28 v0.6 (2026-10-09).xiso.iso"
I4_DISC = DISCS / "SOFTDRINK 2K28 v0.6.1 i4 test (2026-10-17).xiso.iso"
OCT13_XBE = "1b41ec19aac6377484b9b30ee7a5c5ab220fb93d61aa3c14bafdb70092a9504f"
PACKERS_96 = "HTS-h-10-1996-packers-2.iff"   # the season-alias file Quick Game loads on these discs
USER2 = 33
ENTRY, MAIN_MENU, CREATE_PLAYER = 0x5015CC, 0x515660, 0x56F050


def disc_inputs(disc):
    """(default.xbe, main ROST resource, {file name: bytes}) read from a disc image, never written."""
    from mod_editor.core import nfl2k5_espn25_more_moments as mm
    from mod_editor.core import nfl2k5_music_archive as archive
    from tools.b77 import frz_xbe_bisect as bisect
    payload, _ = bisect.read_xbe(disc)
    with archive.Disc(disc, descriptors=()) as d:
        entries = d.archive_entries
        main = d.read_entry_range(entries[5], 0, entries[5].size)
        by_id = {e.name_id: e for e in entries}
        team = by_id[mm.name_id(PACKERS_96)]
        files = {PACKERS_96: d.read_entry_range(team, 0, team.size)}
    return payload, main, files


def body_of(resource):
    return resource[32:32 + struct.unpack_from("<I", resource, 4)[0]]


def split_free_records(body):
    """Free primary records (flags & 5 == 1) whose last-name cell is not the 34 bytes after the first-name cell."""
    arena = body[64:]
    u = lambda at: struct.unpack_from("<I", arena, at)[0]  # noqa: E731
    rel = lambda at: at + u(at) - 1  # noqa: E731
    count, table = u(0), rel(4)
    out, free = [], 0
    for i in range(count):
        p = table + 84 * i
        if arena[p + 8] & 5 != 1:
            continue
        free += 1
        if rel(p + 20) != rel(p + 16) + 34:
            out.append(i)
    return free, out


def free_records(m):
    n, pool = m.get(m.root), m.get(m.root + 4)
    return [pool + 84 * i for i in range(n) if m.uc.mem_read(pool + 84 * i + 8, 1)[0] & 5 == 1]


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class HeldHistoricTeamTests(unittest.TestCase):
    """The game's own importer holds Packers '96 in USER2, as Noah's Random Team spin left it, then MyCareer."""

    @classmethod
    def setUpClass(cls):
        if not OCT13_DISC.is_file():
            raise unittest.SkipTest("the Oct 13 played disc is absent")
        cls.shipped, main, files = disc_inputs(OCT13_DISC)
        if hashlib.sha256(cls.shipped).hexdigest() != OCT13_XBE:
            raise unittest.SkipTest("Oct 13 disc executable pin differs")
        from tools.b77 import mc2_repair
        cls.current = mc2_repair.build(cls.shipped)[0]    # the Studio's MyCareer owner on the same executable
        cls.roster, cls.team = body_of(main), files[PACKERS_96]

    def held(self, m):
        from tests.nfl2k5_my_career_played_fixture import Machine  # noqa: F401
        m.frontend(self.roster)
        m.uc.mem_write(m.OUT, self.team[32:])
        user2 = m.get(m.root + 0x1C) + 500 * USER2
        self.assertEqual(m.call(0xC1030, ecx=m.OUT + 0x40, edx=user2, budget=50000000), 1)  # practice squad ps_import
        self.assertEqual(m.uc.mem_read(user2 + 0x11C, 1)[0], 53)
        m.call(0x6E390, ecx=m.manager, edx=ENTRY)
        m.select(1)
        self.assertEqual(m.top(), m.labels["entry_menu"])
        return free_records(m)

    def test_the_held_team_makes_the_first_free_record_a_split_one(self):
        from tests.nfl2k5_my_career_played_fixture import Machine
        free, split = split_free_records(self.roster)
        self.assertEqual((free, len(split)), (155, 13))
        with Machine(self.current) as m:
            pool = self.held(m)
            first = m.call(0xBFF50)
            self.assertEqual(first, pool[0])
            self.assertIn((first - m.get(m.root + 4)) // 84, split)
            self.assertNotEqual(m.get(first + 20), m.get(first + 16) + 34)

    def test_shipped_myCareer_refuses_with_roster_is_full(self):
        from tests.nfl2k5_my_career_played_fixture import Machine
        with Machine(self.shipped) as m:
            self.held(m)
            m.select(1, budget=50000000)                   # Undrafted free agent: the same creation step
            self.assertIn(("notice", "Roster is full."), m.events)
            self.assertEqual(m.top(), m.labels["entry_menu"])

    def test_current_myCareer_creates_on_the_next_clean_record(self):
        from tests.nfl2k5_my_career_played_fixture import Machine
        with Machine(self.current) as m:
            pool = self.held(m)
            before = bytes(m.uc.mem_read(pool[0], 84))
            m.select(1, budget=50000000)
            self.assertNotIn(("notice", "Roster is full."), m.events)
            self.assertEqual(m.top(), CREATE_PLAYER)
            self.assertEqual(m.get(0xCB8B14), pool[1])
            self.assertEqual(m.get(m.state + 2676), pool[1])
            self.assertEqual(bytes(m.uc.mem_read(pool[0], 84)), before)   # the split record is left alone


class RosterSplitNameRecordTests(unittest.TestCase):
    """Which shipped main rosters can hand MyCareer a split free record at all (read-only disc ROSTs)."""

    def check(self, disc, expected):
        if not disc.is_file():
            self.skipTest(f"{disc.name} is absent")
        from mod_editor.core import nfl2k5_music_archive as archive
        with archive.Disc(disc, descriptors=()) as d:
            entry = d.archive_entries[5]
            body = body_of(d.read_entry_range(entry, 0, entry.size))
        free, split = split_free_records(body)
        self.assertEqual((free, len(split)), expected)
        return body

    def test_public_v06_and_oct13_carry_thirteen(self):
        self.check(V06_DISC, (155, 13))
        self.check(OCT13_DISC, (155, 13))

    def test_the_release_candidate_roster_path_carries_none(self):
        # i4 = the 10/14 dated refresh (it took those records); then mo1's import floor adds 69 blank records.
        body = self.check(I4_DISC, (65, 0))
        from mod_editor.core import nfl2k5_spare_capacity as capacity
        floored, _receipt = capacity.restore_import_floor(body)
        free, split = split_free_records(floored)
        self.assertGreaterEqual(free, 106)
        self.assertEqual(split, [])


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST and Unicorn required")
class AfterLoadedCareerTests(unittest.TestCase):
    """Load a saved career, quit with B, then start a new one: Enter the draft and Undrafted both prepare."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        from tests.nfl2k5_my_career_played_fixture import Machine
        cls.payload, cls.roster = mode.apply(retail_bytes())[0], retail_roster()
        with Machine(cls.payload) as m:
            m.create(cls.roster, preseason=False)
            m.child_services()
            cls.saved = m.native_save(budget=500000000)

    def loaded_then_quit(self, m):
        m.cold(self.roster, self.saved)
        self.assertEqual(m.top(), m.labels["apartment"])
        m.dialog_answer = 2
        m.frame(0x200)                                      # B on the Apartment, Yes
        self.assertEqual((m.depth(), m.top()), (0, MAIN_MENU))
        self.assertEqual(m.get(m.state + 2672), 0)
        m.call(0x6E390, ecx=m.manager, edx=ENTRY)
        m.select(1)
        self.assertEqual(m.top(), m.labels["entry_menu"])

    def test_enter_the_draft_starts_the_prior_season(self):
        from tests.nfl2k5_my_career_played_fixture import Machine
        with Machine(self.payload) as m:
            self.loaded_then_quit(m)
            m.select(0, budget=500000000)
            self.assertEqual(m.top(), m.labels["m3_progress_menu"])
            self.assertEqual(m.get(mode.EXTRA_VA), 1)
            self.assertEqual((m.get(0xE576B8), m.get(0xE576B4)), (0, 0))   # a new league, year 0, week 0
            m.replace_stub(0x48BC0, None)
            m.replace_stub(0x177990, lambda: m.ret(pop=4))
            m.frame(budget=4000000000)                      # one native league week
            self.assertEqual((m.get(mode.EXTRA_VA), m.get(0xE576B4)), (1, 1))
            self.assertFalse([e for e in m.events if isinstance(e, tuple)])

    def test_undrafted_creates_after_a_loaded_career(self):
        from tests.nfl2k5_my_career_played_fixture import Machine
        with Machine(self.payload) as m:
            self.loaded_then_quit(m)
            pool = free_records(m)
            m.select(1, budget=50000000)
            self.assertEqual(m.top(), CREATE_PLAYER)
            self.assertEqual(m.get(0xCB8B14), pool[0])
            self.assertFalse([e for e in m.events if isinstance(e, tuple)])


if __name__ == "__main__":
    unittest.main()
