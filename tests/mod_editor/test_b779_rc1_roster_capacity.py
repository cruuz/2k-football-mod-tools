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
import os
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


# ------------------------------------------------------------------------------------------- draft classes
# The disc class window's position mix (retail; SOFTDRINK folds OLB into LB): QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE
WINDOW_MIX = (27, 19, 23, 41, 34, 12, 16, 10, 13, 24, 21, 20, 25, 31, 18, 23, 23)


def _revision_three(current, retail):
    """The beta-78 / v0.7 economy (revision 3): the current image with the revision-4 sites back to retail."""
    from mod_editor.core import nfl2k5_franchise_economy as economy
    from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    image, source, out = XbeImage(current), XbeImage(retail), bytearray(current)
    for site in economy.sites():
        if site.va in economy.REVISION_4_SITES:
            offset = image.offset(site.va, len(site.patched))
            out[offset:offset + len(site.patched)] = source.read(site.va, len(site.patched))
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


def _turnover(payload, body):
    """A fresh native franchise (0x13EE10 generates the first class), then one league year's record turnover:
    the retirement pass 0x2BDB00, the Combine cleanup 0x2BDA90 that frees the retirees, and the class generator
    0x2BE940(380). Returns (vacancies before, vacancies after, generated positions, positions written)."""
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    size = len(body) - 0x40
    m.uc.mem_write(m.ARENA + 0x300, body)
    m.put(0xB72804, m.ARENA + 0x300)
    m.put(0xB72808, size if size > 0x91000 else 0x91000)
    m.put(0xB7280C, size)
    m.fixup_roster(m.ARENA + 0x340)
    m.seed(12345)
    for a, v in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 5), (0xE60010, 5)):
        m.put(a, v)
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
    generated = []   # Unicorn code hooks must exist before the generator's blocks are first translated
    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: generated.append((m.reg("ECX"), m.reg("EDX") & 0xFF)),
                  begin=0x2BE6F0, end=0x2BE6F0)
    m.call(0x13EE10, budget=2_000_000_000)
    n, base = m.get(m.root), m.get(m.root + 4)

    def vacancies():
        raw = bytes(m.uc.mem_read(base, 84 * n))
        return sum(1 for i in range(n) if raw[84 * i + 8] & 5 == 1)

    before = vacancies()
    m.call(0x2BDB00, budget=4_000_000_000)
    m.call(0x2BDA90, budget=2_000_000_000)
    generated.clear()
    m.call(0x2BE940, ecx=380, budget=4_000_000_000)
    written = [m.uc.mem_read(record + 0x35, 1)[0] for record, _ in generated]
    return before, vacancies(), [p for _, p in generated], written


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class DraftClassSupplyTests(unittest.TestCase):
    """Native class turnover on the retail roster with the economy owner (unsigned free agents survive)."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, retail_roster
        from mod_editor.core import nfl2k5_franchise_economy as economy
        cls.retail, cls.body = retail_bytes(), retail_roster()
        cls.current = economy.apply(cls.retail)[0]
        cls.previous = _revision_three(cls.current, cls.retail)

    def test_revision_three_reads_legacy_and_upgrades_in_place(self):
        from mod_editor.core import nfl2k5_franchise_economy as economy
        self.assertEqual(economy.REVISION, 4)
        self.assertEqual(economy.status(self.previous), "legacy")
        upgraded, receipt = economy.apply(self.previous)
        self.assertEqual(upgraded, self.current)
        self.assertEqual(receipt.get("upgraded_from"), "legacy")
        self.assertEqual(sorted(int(e["va"], 16) for e in receipt["edits"]), sorted(economy.REVISION_4_SITES))

    def test_every_class_keeps_the_vacancies_and_samples_every_position(self):
        # The retail roster has only 241 free agents: retiring all of them still frees fewer than 380 records, so
        # this class is short (retail itself spends vacancies here). It keeps every vacancy and every group.
        before, after, positions, written = _turnover(self.current, self.body)
        self.assertGreater(before, 100)
        self.assertEqual(after, before)                    # Create Player / MyCareer / imports keep their records
        self.assertGreater(len(positions), 224)            # still more than seven full rounds
        counts = [positions.count(p) for p in range(17)]
        share = len(positions) / 380
        for code, want in enumerate(WINDOW_MIX):           # the retail roster carries OLBs, so none fold to LB
            self.assertGreaterEqual(counts[code], int(want * share) - 1, code)
        self.assertEqual(written, positions)               # the generator wrote each prospect at that position

    def test_revision_three_spends_the_vacancies_and_skews_the_class(self):
        # Negative control: the released (v0.7) economy. Revision 4 must differ from this.
        before, after, positions, _ = _turnover(self.previous, self.body)
        self.assertEqual(len(positions), 380)
        self.assertLess(after, before)


RELEASED_BODY = Path(os.environ.get("NFL2K5_RC1_V07_BODY",
                                    "/home/noah/2k-worktrees/.b77-scratch/b779/rc1/work/rel_body.bin"))


@unittest.skipUnless(HAVE_UC and RELEASED_BODY.is_file(), "the released v0.7 main ROST body (private) is absent")
class ReleasedRosterClassTests(unittest.TestCase):
    """The v0.7 disc roster (0xB0000 arena, 879 free agents, 144 create vacancies), retail XBE + economy only."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        from mod_editor.core import nfl2k5_franchise_economy as economy
        cls.retail, cls.body = retail_bytes(), RELEASED_BODY.read_bytes()
        cls.current = economy.apply(cls.retail)[0]
        cls.previous = _revision_three(cls.current, cls.retail)

    def test_the_second_class_has_the_first_class_mix_and_keeps_144_vacancies(self):
        before, after, positions, written = _turnover(self.current, self.body)
        self.assertEqual((before, after), (144, 144))
        mix = list(WINDOW_MIX)
        mix[11] += mix[10]
        mix[10] = 0                                         # one pool: no rostered OLB, so OLB slots are LB
        self.assertEqual(tuple(positions.count(p) for p in range(17)), tuple(mix))
        self.assertEqual(written, positions)

    def test_released_economy_reproduces_the_reports(self):
        # v0.7 (revision 3): 144 FB, 4 QB, 0 K, 0 P and no vacancy left (SWeaR 10/27: 4 QBs, punters empty).
        before, after, positions, _ = _turnover(self.previous, self.body)
        self.assertEqual((before, after), (144, 0))
        self.assertEqual(positions.count(8), 144)          # every vacancy is a fullback record
        self.assertLess(positions.count(0), 10)             # the full v0.7 XBE measured 4 QB, 0 K, 0 P
        self.assertLess(positions.count(1) + positions.count(2), 5)


if __name__ == "__main__":
    unittest.main()
