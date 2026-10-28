"""b779 rc1: the v0.7 roster capacity family (MyCareer "Roster is full.", draft-class records, CPU signings).

v0.7 ships the 0xB0000 capacity arena. Its runtime marks every club with reserve schema version 2 (team +0x19B),
the same marker as the 0x92000 reserve arena, with the reserve block 0x400 before the arena end. MyCareer's
mode_grown_member only accepted [0xB72808] == 0x92000, so on the capacity arena every free record read as
league-wide invalid and creation refused "Roster is full." on any boot (Enter the Draft and Undrafted FA).

Native fixtures run the pinned USA executable with the Studio's owners in the released order (practice squad,
generic MyCareer, capacity arena) in Unicorn; no game boot. Skipped when the retail extraction is absent.
"""
from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_my_career_mode as mc  # noqa: E402
from mod_editor.core import nfl2k5_my_career_mode_code as mc_code  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
RELEASED_GROWN_MEMBER_BYTES = 150  # v0.7 (57576211c): the fix must not move any later MyCareer label


class LayoutTests(unittest.TestCase):
    def test_grown_member_keeps_its_released_size(self):
        labels = mc_code.LABELS
        self.assertEqual(labels["slot_clean"] - labels["mode_grown_member"], RELEASED_GROWN_MEMBER_BYTES)

    def test_grown_member_no_longer_names_one_arena_size(self):
        source = (ROOT / "tools/mycareer_mode/runtime.c").read_text(encoding="utf-8")
        body = source[source.index("u32 FC mode_grown_member"):source.index("static NI u32 slot_clean")]
        self.assertNotIn("0x92000", body)
        self.assertNotIn("0x91c20", body)
        self.assertIn("G(0xB72808)-0x3e0", body)


def _composed_capacity_xbe():
    from tests.nfl2k5_my_career_fixture import XBE
    from mod_editor.core import nfl2k5_roster_arena_growth as growth, nfl2k5_k128 as k128
    from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_practice_squad as ps
    retail = XBE.read_bytes()
    requests = tuple(k128.REQUESTS) + tuple(growth.REQUESTS) + tuple(mc.REQUESTS)
    xbe, _ = space.apply(retail, requests, scaleout=True)
    xbe, _ = k128.apply(xbe, roster_heap=True, require=True)
    xbe, _ = ps.apply(xbe)
    xbe, _ = mc.apply(xbe)
    xbe, _ = growth.apply(xbe, reserves_16=False, created_teams_extra=0, capacity=True)
    return xbe


def _capacity_roster():
    """The retail roster grown to the 0xB0000 capacity arena, its 32 clubs marked as the released disc's are
    (reserve schema version 2, magic 0xA5, no reserves), so MyCareer takes the grown-member path."""
    from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
    from mod_editor.core import nfl2k5_roster_arena as arena
    body, _ = arena.migrate(retail_roster(), reserves_16=False, capacity_records=612)
    body = bytearray(body)
    root = 0x40
    teams = 0x1C + struct.unpack_from("<i", body, root + 0x1C)[0] - 1
    for index in range(32):
        team = root + teams + 500 * index
        body[team + 0x19B], body[team + 0x1F2], body[team + 0x1F3] = 2, 0, 0xA5
    return bytes(body)


def _machine_class():
    from tests.nfl2k5_my_career_played_fixture import Machine

    class CapacityMachine(Machine):
        def capacity_frontend(self, body):
            """The mode fixture's menu seams over a bare capacity ROST body (0x40 object + 0xB0000 arena)."""
            retail_sized = bytes(12) + b"ROST" + bytes(593760 - 16)
            self.frontend(retail_sized)
            size = len(body) - 0x40
            self.uc.mem_write(self.ARENA, body[0x40:])
            self.put(0xB72808, size)
            self.put(0xB7280C, size)
            self.call(0xC0500, ecx=self.ARENA, budget=5000000)

    return CapacityMachine


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class MyCareerCapacityCreateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_my_career_fixture import XBE
        if not XBE.is_file():
            raise unittest.SkipTest("pinned USA XBE required")
        cls.body = _capacity_roster()
        cls.xbe = _composed_capacity_xbe()
        cls.machine = _machine_class()

    def undrafted(self):
        m = self.machine(self.xbe)
        m.capacity_frontend(self.body)
        self.assertEqual(m.get(0xB72808), 0xB0000)
        for rng in (0xB12680, 0xE5FCA0):
            m.call(0x48BE0, ecx=rng, edx=12345)
        m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
        m.select(1)                         # MyCareer
        m.select(1, budget=500000000)       # Undrafted Free Agent
        return m

    def test_undrafted_free_agent_opens_create_player_on_a_vacancy(self):
        m = self.undrafted()
        notices = [text for kind, text in m.events if kind == "notice"]
        self.assertNotIn("Roster is full.", notices)
        record = m.get(0xCB8B14)
        self.assertTrue(record)
        base, count = m.get(m.root + 4), m.get(m.root)
        self.assertEqual((record - base) % 84, 0)
        self.assertLess((record - base) // 84, count)
        # A clean vacant create record: flags & 5 == 1 before the native initializer runs.
        index = (record - base) // 84
        primary = 0x40 + 4 + struct.unpack_from("<i", self.body, 0x44)[0] - 1   # self-relative +1 pointer
        self.assertEqual(self.body[primary + 84 * index + 8] & 5, 1)


if __name__ == "__main__":
    unittest.main()
