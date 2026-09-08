"""M2 prerequisite: execute actual CAP completion and its FA-capacity edge.

No new-mode entry is installed here. These tests expose the preflight and
return hooks the in-game adapter needs, without fabricating a franchise/hub.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, Machine, draft_save


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "Unicorn and pinned USA retail default.xbe required")
class CreationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("retail evidence exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("USA retail XBE evidence pin differs")
        cls.payload = career.apply(retail)[0]

    def machine(self, free_agents=1):
        m = Machine(self.payload, draft_save())
        manager = m.BODIES
        m.put(manager + 0x100, 3)
        m.put(manager + 0x10C, manager + 0x1000)
        for index, descriptor in enumerate((0x515660, 0x56E9C4, 0x56F050, 0x56EBA0)):
            m.put(manager + index * 8, descriptor)
        m.put(0xCB8B14, m.player)
        m.put(0xCB8BA0, 0)
        m.uc.mem_write(m.player + 8, b"\x01")
        # Give the native FA helpers their actual 2500-pointer capacity. The
        # ordinary synthetic writer fixture only needs its current short list.
        fa = manager + 0x4000
        m.put(m.root + 0x38, free_agents)
        m.put(m.root + 0x3C, fa)
        m.uc.mem_write(fa, struct.pack("<I", m.player - 84) * free_agents
                       + bytes((2500 - free_agents) * 4))
        # Descriptor rendering/destruction and notification subscribers are
        # services. Native CAP commit, roster membership and menu pops execute.
        m.stub(0x6E4E0, lambda: m.ret(pop=4))
        m.stub(0x110E60, lambda: m.ret())
        return m, manager, fa

    def finish(self, m, manager):
        m.call(0x346C50, ecx=manager, budget=300000)
        self.assertEqual(m.get(manager + 0x100), 1)
        self.assertEqual(m.get(manager + 8), 0x56E9C4)
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222),
                            ("EDI", 0x33333333), ("EBP", 0x44444444)):
            self.assertEqual(m.reg(name), value, name)

    def test_completion_marks_created_player_appends_fa_and_pops_to_creator_list(self):
        m, manager, fa = self.machine()
        before = bytes(m.uc.mem_read(m.player - 7 * 84, 7 * 84))
        self.finish(m, manager)
        self.assertEqual(m.uc.mem_read(m.player + 8, 1), b"\x05")
        self.assertEqual(m.get(m.root + 0x38), 2)
        self.assertEqual(m.get(fa + 4), m.player)
        self.assertEqual(m.uc.mem_read(m.player - 7 * 84, 7 * 84), before)
        self.assertEqual(m.uc.mem_read(m.state, career.STATE_SIZE), bytes(career.STATE_SIZE))
        self.assertEqual(m.get(0xCB8C30), 1)

    def test_repeated_completion_keeps_only_one_fa_membership(self):
        m, manager, fa = self.machine()
        self.finish(m, manager)
        self.finish(m, manager)
        self.assertEqual(m.get(m.root + 0x38), 2)
        self.assertEqual([m.get(fa + 4 * i) for i in range(2)].count(m.player), 1)

    def test_existing_team_membership_is_not_also_added_to_free_agents(self):
        m, manager, fa = self.machine()
        m.put(m.team + 3 * 4, m.player)
        m.uc.mem_write(m.team + 0x11C, b"\x04")
        self.finish(m, manager)
        self.assertEqual(m.get(m.root + 0x38), 1)
        self.assertNotEqual(m.get(fa), m.player)
        self.assertEqual(m.get(m.team + 12), m.player)

    def test_full_fa_list_can_leave_native_creation_unassigned_so_adapter_must_preflight(self):
        m, manager, fa = self.machine(free_agents=2500)
        before = bytes(m.uc.mem_read(fa, 10000))
        self.finish(m, manager)
        # This is the native edge, NOT a desired new-mode behavior: completion
        # marks the player, but append refuses capacity and no team owns him.
        self.assertEqual(m.uc.mem_read(m.player + 8, 1), b"\x05")
        self.assertEqual(m.get(m.root + 0x38), 2500)
        self.assertEqual(m.uc.mem_read(fa, 10000), before)
        self.assertFalse(any(m.get(fa + i * 4) == m.player for i in range(2500)))


if __name__ == "__main__":
    unittest.main()
