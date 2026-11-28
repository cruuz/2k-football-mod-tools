"""mc3: MyCareer draft preparation after other modes, and draft-path save/load (b775).

D01 (Noah 2026-10-16, Oct 13 disc): MyCareer > Enter the draft showed "Roster is full." after the prior season,
then "Draft preparation failed. Quit and try again." His boot had put the Quick Game away side on a historic team
(Packers '96) and then pressed Random Team, which left that team, 53 players, in the USER2 spare slot. The Oct 13
(and public v0.6) main roster has 13 free player records whose two name cells are not adjacent; with 53 records
taken, the game's own first free record (BFF50) is one of them, and MyCareer refused the whole career.

The draft save/load case also accepts the exact extracted October 13 executable in B773_SP2_BASE_XBE.
The roster censuses accept the original complete entry 5 in NFL2K5_V06_ROST_ENTRY, NFL2K5_OCT13_ROST_ENTRY
and NFL2K5_I4_ROST_ENTRY for their respective discs. The held-team cases accept the same October 13 executable
and roster alongside its original team resource in NFL2K5_OCT13_PACKERS_ENTRY. Each extracted input is hash-pinned.
Retail-fixture tests cover a loaded career, quit, then a new career. EXPERIMENTAL / UNWITNESSED: offline evidence.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

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
V06_ROSTER = ("NFL2K5_V06_ROST_ENTRY", "d50958ccd181e5c9b466e9cd75323105a20fa9909f90a541fd029e180c765e5e")
OCT13_ROSTER = ("NFL2K5_OCT13_ROST_ENTRY", "dcf17df2eb03e0bb2c17d9a78eef2a2894b4cd85fcd73f2c3ff0d713a026e68a")
I4_ROSTER = ("NFL2K5_I4_ROST_ENTRY", "462024a53258032901bdf4794443e5ebcb51a5e13d7c97e40d7fce2571e41b27")
PACKERS_96 = "HTS-h-10-1996-packers-2.iff"   # the season-alias file Quick Game loads on these discs
OCT13_PACKERS = ("NFL2K5_OCT13_PACKERS_ENTRY", "04451d081b7af4692fa11a5146315f36d85d897b962f9d68e42a23617a3b2f34")
USER2 = 33
ENTRY, MAIN_MENU, CREATE_PLAYER = 0x5015CC, 0x515660, 0x56F050
# The Oct 13 disc's own MyCareer entry menu. Machine takes its labels from the Studio's CURRENT template, whose code
# was re-laid out after beta-77.1 (the current entry_menu is 12 bytes earlier, 0x14F27A4), so the shipped executable's
# menu is pinned here: it is the address the shipped code itself reaches, and it equals entry_menu of the beta-77.1
# template (0c739fb0f), which is the layout the Oct 13 owner kept.
SHIPPED_ENTRY_MENU = 0x14F27B0


def verify_member(payload: bytes, expected: str, name: str) -> bytes:
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(f"{name} SHA-256 differs from the recorded disc member")
    return payload


def october_13_executable(disc: Path, extracted: str | None) -> bytes:
    if disc.is_file():
        from tools.b77 import frz_xbe_bisect as bisect
        payload, _ = bisect.read_xbe(disc)
    elif extracted:
        payload = Path(extracted).read_bytes()
    else:
        raise unittest.SkipTest("October 13 played disc or its exact B773_SP2_BASE_XBE is required")
    return verify_member(payload, OCT13_XBE, "October 13 default.xbe")


def archive_member(disc: Path, member: tuple[str, str], name: str | None = None) -> bytes:
    label = name or "entry 5"
    if disc.is_file():
        from mod_editor.core import nfl2k5_music_archive as archive
        with archive.Disc(disc, descriptors=()) as image:
            if name is None:
                entry = image.archive_entries[5]
            else:
                from mod_editor.core import nfl2k5_espn25_more_moments as mm
                entry = {row.name_id: row for row in image.archive_entries}[mm.name_id(name)]
            resource = image.read_entry_range(entry, 0, entry.size)
    elif path := os.environ.get(member[0]):
        resource = Path(path).read_bytes()
    else:
        raise unittest.SkipTest(f"{disc.name} or its exact {member[0]} is required")
    return verify_member(resource, member[1], label)


class HistoricalInputTests(unittest.TestCase):
    def test_unrelated_executable_is_rejected_before_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            extracted = root / "default.xbe"
            extracted.write_bytes(b"different executable")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                october_13_executable(root / "absent.iso", str(extracted))

    def test_wrong_archive_members_are_rejected_before_native_use(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            extracted = root / "main.resource"
            extracted.write_bytes(b"different roster")
            members = ((V06_ROSTER, None), (OCT13_ROSTER, None), (I4_ROSTER, None), (OCT13_PACKERS, PACKERS_96))
            for member, name in members:
                with self.subTest(member=member[0]), patch.dict(os.environ, {member[0]: str(extracted)}):
                    with self.assertRaisesRegex(ValueError, "SHA-256"):
                        archive_member(root / "absent.iso", member, name)


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
        cls.shipped = october_13_executable(OCT13_DISC, os.environ.get("B773_SP2_BASE_XBE"))
        cls.roster = body_of(archive_member(OCT13_DISC, OCT13_ROSTER))
        cls.team = archive_member(OCT13_DISC, OCT13_PACKERS, PACKERS_96)
        from tools.b77 import mc2_repair
        cls.current = mc2_repair.build(cls.shipped)[0]    # the Studio's MyCareer owner on the same executable

    def held(self, m, entry_menu=None):
        from tests.nfl2k5_my_career_played_fixture import Machine  # noqa: F401
        m.frontend(self.roster)
        m.uc.mem_write(m.OUT, self.team[32:])
        user2 = m.get(m.root + 0x1C) + 500 * USER2
        self.assertEqual(m.call(0xC1030, ecx=m.OUT + 0x40, edx=user2, budget=50000000), 1)  # practice squad ps_import
        self.assertEqual(m.uc.mem_read(user2 + 0x11C, 1)[0], 53)
        m.call(0x6E390, ecx=m.manager, edx=ENTRY)
        m.select(1)
        self.assertEqual(m.top(), entry_menu or m.labels["entry_menu"])
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
            self.held(m, SHIPPED_ENTRY_MENU)
            m.select(1, budget=50000000)                   # Undrafted free agent: the same creation step
            self.assertIn(("notice", "Roster is full."), m.events)
            self.assertEqual(m.top(), SHIPPED_ENTRY_MENU)

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


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST and Unicorn required")
class DiscDraftSaveLoadTests(unittest.TestCase):
    """Discord D01 'drafted, then save or exit, then load failed': the draft path saved and cold-loaded at Senior
    Bowl preparation, after ten picks on the NFL Draft screen (Save / Quit to main menu) and on the Apartment after
    the draft, on a SOFTDRINK disc executable with the Studio's current MyCareer owner. The pinned f0 franchise at
    the Combine stands in for the native prior season (the 40-minute bootstrap is evidence, not a test)."""

    @classmethod
    def setUpClass(cls):
        from tools.b77 import mc2_repair
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        shipped = october_13_executable(OCT13_DISC, os.environ.get("B773_SP2_BASE_XBE"))
        cls.payload = mc2_repair.build(shipped)[0]
        code, state = mode.legacy.allocations(cls.payload)
        cls.labels = mc2_repair.studio_owner(cls.payload, code, state)[1]
        cls.roster = retail_roster()

    def reload(self, saved, menu):
        from tests.nfl2k5_my_career_draft_fixture import Machine
        self.assertEqual(saved[-128:-124], b"MCPL")                 # the career footer is present
        with Machine(self.payload) as cold:
            cold.labels = self.labels
            cold.cold(self.roster, saved)
            self.assertNotIn(("notice", "Career load failed."), cold.events)
            self.assertEqual(cold.top(), self.labels[menu])
            return cold.call("primary"), bytes(cold.uc.mem_read(cold.state + 40, 16)), saved[-128 + 36]

    def test_prep_mid_draft_and_after_draft_saves_load(self):
        from tests.nfl2k5_my_career_draft_fixture import Machine
        with Machine(self.payload) as m:
            m.labels = self.labels
            p = m.prepare_draft(self.roster)
            token = bytes(m.uc.mem_read(m.state + 40, 16))
            self.assertEqual(self.reload(m.native_save(budget=500000000), "m3_prep_menu"), (p, token, 2))
            m.select(0, budget=200000000)                           # Continue to the draft
            for _ in range(10):
                m.frame(budget=500000000)
            self.assertEqual(m.top(), self.labels["m3_draft_menu"])
            self.assertEqual(self.reload(m.native_save(budget=500000000), "m3_draft_menu")[:2], (p, token))
            for _ in range(260):
                if m.get(0xE576A4) != 5:
                    break
                m.frame(budget=6000000000)
            self.assertEqual(m.top(), self.labels["apartment"])
            self.assertEqual(self.reload(m.native_save(budget=500000000), "apartment"), (p, token, 3))


class RosterSplitNameRecordTests(unittest.TestCase):
    """Which shipped main rosters can hand MyCareer a split free record at all (read-only disc ROSTs)."""

    def check(self, disc, expected, member):
        body = body_of(archive_member(disc, member))
        free, split = split_free_records(body)
        self.assertEqual((free, len(split)), expected)
        return body

    def test_public_v06_carries_thirteen(self):
        self.check(V06_DISC, (155, 13), V06_ROSTER)

    def test_oct13_carries_thirteen(self):
        self.check(OCT13_DISC, (155, 13), OCT13_ROSTER)

    def test_the_release_candidate_roster_path_carries_none(self):
        # i4 = the 10/14 dated refresh (it took those records); then mo1's import floor adds 69 blank records.
        body = self.check(I4_DISC, (65, 0), I4_ROSTER)
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
