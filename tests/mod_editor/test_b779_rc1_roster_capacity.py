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
# Revision 4's class mix per 450 (Noah 10/28: deep classes, undrafted players at every position):
#             QB   K   P  WR  CB  FS  SS  HB  FB  TE OLB ILB   C   G   T  DT  DE
CLASS_MIX = (24, 5, 5, 37, 54, 15, 15, 28, 9, 28, 19, 19, 24, 26, 40, 48, 54)
ONE_POOL_MIX = CLASS_MIX[:10] + (0, CLASS_MIX[10] + CLASS_MIX[11]) + CLASS_MIX[12:]   # no rostered OLB: OLB is LB


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


def _turnover(payload, body, class_size=380):
    """A fresh native franchise (0x13EE10 generates the first class), then one league year's record turnover:
    the retirement pass 0x2BDB00, the Combine cleanup 0x2BDA90 that frees the retirees, and the class generator
    0x2BE940(class_size). Returns (vacancies before, vacancies after, generated positions, positions written,
    years past his position's age of every free agent the pass's top-up call (0x2BDCD6) retired)."""
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
    topped = []

    def retiring_agents():
        lst, count = m.get(m.root + 0x3C), m.get(m.root + 0x38)
        return {p for p in (m.get(lst + 4 * i) for i in range(count)) if m.uc.mem_read(p + 8, 1)[0] & 8}

    def past_age(p):
        season = m.get(0x247AC7) + m.get(0xE576B8) + 1
        raw = (m.get(p + 24) >> 21) & 127
        position = m.uc.mem_read(p + 0x35, 1)[0]
        return (season - raw) % 100 - (m.get(0xACEDE0 + 4 * position) + 24)

    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: topped.append(retiring_agents()), begin=0x2BDCD6, end=0x2BDCD6)
    def after_topup():   # ages now: the Combine cleanup clears these records before the class reuses them
        topped.append([past_age(p) for p in retiring_agents() - topped[0]])
    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: after_topup(), begin=0x2BDCDB, end=0x2BDCDB)
    m.call(0x13EE10, budget=2_000_000_000)
    n, base = m.get(m.root), m.get(m.root + 4)

    def vacancies():
        raw = bytes(m.uc.mem_read(base, 84 * n))
        return sum(1 for i in range(n) if raw[84 * i + 8] & 5 == 1)

    before = vacancies()
    m.call(0x2BDB00, budget=4_000_000_000)
    m.call(0x2BDA90, budget=2_000_000_000)
    generated.clear()
    m.call(0x2BE940, ecx=class_size, budget=4_000_000_000)
    written = [m.uc.mem_read(record + 0x35, 1)[0] for record, _ in generated]
    ages = topped[1] if len(topped) == 2 else []
    return before, vacancies(), [p for _, p in generated], written, ages


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

    def test_a_small_pool_still_gets_a_full_draft_and_keeps_the_vacancies(self):
        # The retail roster has only 241 free agents, mostly young: retiring by age alone frees far fewer than
        # 450 records. The default floor (variant B) may take only generated never-played players, and a fresh
        # retail franchise has none, so the draft floor (DRAFT_FLOOR, 256) takes the oldest free agents until the
        # class can fill the 224-pick draft. Every create vacancy survives and every position group is in the class.
        from mod_editor.core import nfl2k5_franchise_economy as economy
        before, after, positions, written, _ = _turnover(self.current, self.body, economy.CLASS_SIZE)
        self.assertGreater(before, 100)
        self.assertEqual(after, before)                    # Create Player / MyCareer / imports keep their records
        self.assertGreaterEqual(len(positions), 256)
        counts = [positions.count(p) for p in range(17)]
        self.assertTrue(all(counts), counts)               # the retail roster carries OLBs, so none fold to LB
        self.assertEqual(written, positions)               # the generator wrote each prospect at that position

    def test_revision_three_spends_the_vacancies_and_skews_the_class(self):
        # Negative control: the released (v0.7) economy. Revision 4 must differ from this.
        before, after, positions, _, _ = _turnover(self.previous, self.body)
        self.assertEqual(len(positions), 380)
        self.assertLess(after, before)


def _preseason_advance(payload, body, user=1):
    """A native franchise with the preseason on, one user club signed one over the in-season limit (the gate's own
    immediate at 0x2BF978) during the preseason, the preseason weeks played natively (0x247D40), then the stage
    advance 0x2480B0 twice. Returns (stage after, user club count after, notices)."""
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    size = len(body) - 0x40
    m.uc.mem_write(m.ARENA + 0x300, body)
    m.put(0xB72804, m.ARENA + 0x300)
    m.put(0xB72808, size if size > 0x91000 else 0x91000)
    m.put(0xB7280C, size)
    m.fixup_roster(m.ARENA + 0x340)
    m.seed(12345)
    for a, v in ((0xE5FF80, 4), (0xE60120, 1), (0xE6000C, 5), (0xE60010, 5)):
        m.put(a, v)
    notices = []

    def notice():
        p = m.reg("EDX")
        notices.append(bytes(m.uc.mem_read(p, 400)).decode("utf-16-le", "replace").split("\0")[0])
        m.ret()
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, notice, reason="informational dialog acknowledgement only")
    m.call(0x13EE10, budget=2_000_000_000)
    team = m.team_base + 500 * user
    m.call(0xC4D30, ecx=team, edx=1)
    limit = m.uc.mem_read(0x2BF978, 1)[0]
    lst = m.root + 0x38
    while m.uc.mem_read(team + 0x11C, 1)[0] <= limit:
        p = m.call(0x242500, ecx=lst, edx=0)
        m.call(0x2425C0, ecx=lst, edx=p)
        assert m.call(0xC3EE0, ecx=team, edx=p), "preseason append refused"
    m.call(0xC3F00, ecx=team)
    menu = m.ARENA + 0x1A0000
    advances = 0
    while m.get(0xE576A4) == 7 and advances < 2:
        if m.get(0xE576B4) < m.get(0xE576B0):
            m.call(0x247D40, ecx=menu, budget=int(2e10))
        else:
            m.call(0x2480B0, ecx=menu, budget=int(2e10))
            advances += 1
    return m.get(0xE576A4), m.uc.mem_read(team + 0x11C, 1)[0], limit, notices


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class PreseasonGateTests(unittest.TestCase):
    """SWeaR 10/27: "You must be under the salary cap and have a maximum of 53 players to enter the regular season.
    The Titans need attention." did not go away and locked the season."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, retail_roster
        from mod_editor.core import nfl2k5_franchise_economy as economy
        cls.retail, cls.body = retail_bytes(), retail_roster()
        cls.current = economy.apply(cls.retail)[0]
        cls.previous = _revision_three(cls.current, cls.retail)

    def test_a_user_club_over_the_limit_is_cut_down_and_the_season_starts(self):
        stage, count, limit, notices = _preseason_advance(self.current, self.body)
        self.assertEqual((stage, notices), (8, []))
        self.assertLessEqual(count, limit)

    def test_revision_three_repeats_the_notice_and_stays_in_the_preseason(self):
        stage, count, limit, notices = _preseason_advance(self.previous, self.body)
        self.assertEqual((stage, count, len(notices)), (7, limit + 1, 2))
        self.assertIn("need attention", notices[0])


RELEASED_BODY = Path(os.environ.get("NFL2K5_RC1_V07_BODY",
                                    "/home/noah/2k-worktrees/.b77-scratch/b779/rc1/work/rel_body.bin"))


RELEASED_XBE = Path(os.environ.get("NFL2K5_RC1_V07_XBE", "/home/noah/2k-worktrees/.b77-scratch/b779/rc1/work/rel.xbe"))


@unittest.skipUnless(HAVE_UC and RELEASED_BODY.is_file() and RELEASED_XBE.is_file(),
                     "the released v0.7 default.xbe and main ROST body (private) are absent")
class ReleasedRosterClassTests(unittest.TestCase):
    """The released v0.7 executable (every owner, season 2026) and disc roster (0xB0000 arena, 879 free agents,
    144 create vacancies): as shipped (revision 3) and upgraded in place to revision 4."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_franchise_economy as economy
        cls.released, cls.body = RELEASED_XBE.read_bytes(), RELEASED_BODY.read_bytes()
        cls.fixed = economy.apply(cls.released)[0]

    def test_the_second_class_is_350_deep_by_age_and_keeps_144_vacancies(self):
        # Retirement by each position's age plus each player's own 0-6 extra years: the year-0 turnover frees about
        # 358 records on the v0.7 roster; no generated never-played player exists yet for the floor.
        from mod_editor.core import nfl2k5_franchise_economy as economy
        before, after, positions, written, ages = _turnover(self.fixed, self.body, economy.CLASS_SIZE)
        self.assertEqual((before, after), (144, 144))
        self.assertGreaterEqual(len(positions), 350)
        share = len(positions) / economy.CLASS_SIZE
        for code, want in enumerate(ONE_POOL_MIX):          # a short class samples every group (stride 151)
            if want:
                self.assertGreaterEqual(positions.count(code), max(1, int(want * share * 0.75)), code)
        self.assertEqual(written, positions)
        self.assertTrue(ages)
        # Every top-up retiree is past his position's age, or (second pass) within two years of it: never younger.
        self.assertGreaterEqual(min(ages), -2)

    def test_released_economy_reproduces_the_reports(self):
        # v0.7 (revision 3): 144 FB, 4 QB, 0 K, 0 P and no vacancy left (SWeaR 10/27: 4 QBs, punters empty).
        before, after, positions, _, _ = _turnover(self.released, self.body)
        self.assertEqual((before, after), (144, 0))
        self.assertEqual(positions.count(8), 144)          # every vacancy is a fullback record
        self.assertEqual((positions.count(0), positions.count(1), positions.count(2)), (4, 0, 0))


def _drafts(payload, body, drafts=2):
    """Native franchise seasons with the regular-season games skipped (stage 8 week counter set to its end; the
    playoffs, rollover, offseason stages, draft and class generator all run natively, CPU clubs throughout).
    Returns one {position code: undrafted prospects} per draft, read when the native undrafted pass 0x31E430
    starts, and the class sizes generated."""
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
    m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog acknowledgement only")
    leftovers, classes = [], []

    def census():
        n, base = m.get(m.root), m.get(m.root + 4)
        raw = bytes(m.uc.mem_read(base, 84 * n))
        owned = {m.get(m.team_base + 500 * t + 4 * i) for t in range(32) for i in range(65)}
        counts = [0] * 17
        for i in range(n):
            if raw[84 * i + 8] & 0x10 and base + 84 * i not in owned and raw[84 * i + 0x35] < 17:
                counts[raw[84 * i + 0x35]] += 1
        leftovers.append(counts)

    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: census(), begin=0x31E430, end=0x31E430)
    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: classes.append(m.reg("ECX")), begin=0x2BE940, end=0x2BE940)
    m.call(0x13EE10, budget=2_000_000_000)
    menu = m.ARENA + 0x1A0000
    for _ in range(200):
        if len(leftovers) >= drafts:
            break
        stage, week, end, year = (m.get(a) for a in (0xE576A4, 0xE576B4, 0xE576B0, 0xE576B8))
        if stage == 8 and week < end:
            m.put(0xE576B4, end)
        elif stage == 9 and week >= end:
            m.call(0xC4D30, ecx=m.team_base, edx=1)       # the native exit needs one user club
        m.call(0x247D40 if stage in (7, 9) and week < end else 0x2480B0, ecx=menu, budget=int(2e10))
        if m.get(0xE576B8) != year:
            for t in range(32):
                if m.call(0x13EC30, ecx=m.team_base + 500 * t):
                    m.call(0xC4D30, ecx=m.team_base + 500 * t, edx=0)
    return leftovers, classes


@unittest.skipUnless(HAVE_UC and RELEASED_BODY.is_file() and RELEASED_XBE.is_file(),
                     "the released v0.7 default.xbe and main ROST body (private) are absent")
class ReleasedRosterDraftTests(unittest.TestCase):
    """Noah 10/28: "Every draft, every position pool should have undrafted players that nobody wants." Two native
    drafts on the v0.7 executable upgraded to revision 4: the disc's own first class, then the first generated one."""

    def test_no_position_runs_out_in_the_first_two_drafts(self):
        from mod_editor.core import nfl2k5_franchise_economy as economy
        fixed = economy.apply(RELEASED_XBE.read_bytes())[0]
        leftovers, classes = _drafts(fixed, RELEASED_BODY.read_bytes())
        self.assertEqual(len(leftovers), 2)
        self.assertIn(economy.CLASS_SIZE, classes)
        for draft in leftovers:
            for code, left in enumerate(draft):
                if code != 10:                              # one pool: no OLB at all (they are LB)
                    self.assertGreater(left, 0, f"position {code} ran out: {draft}")


# Modern 53-man minimums the smart cut keeps (2024 rosters, atlantafalcons.com 2024-08-28), one-pool LB = ILB 5.
#            QB K  P  WR CB FS SS HB FB TE OLB ILB C  G  T  DT DE
MODERN_MIN = (2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 0, 5, 2, 3, 3, 3, 4)


def _cut(payload, body, composition, target):
    """A fresh native franchise; club 1 is rebuilt from free agents to exactly `composition` (count per position
    code, each with a one-year contract), then the native cut-down 0x2BF9A0(club, target) runs. Returns (counts
    after, positions released)."""
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    size = len(body) - 0x40
    m.uc.mem_write(m.ARENA + 0x300, body)
    m.put(0xB72804, m.ARENA + 0x300)
    m.put(0xB72808, size if size > 0x91000 else 0x91000)
    m.put(0xB7280C, size)
    m.fixup_roster(m.ARENA + 0x340)
    m.seed(12345)
    for a, v in ((0xE5FF80, 4), (0xE60120, 1), (0xE6000C, 5), (0xE60010, 5)):
        m.put(a, v)
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog acknowledgement only")
    released = []
    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append(m.reg("EDX")), begin=0x2BD900, end=0x2BD900)
    m.call(0x13EE10, budget=2_000_000_000)
    team, lst = m.team_base + 500, m.root + 0x38

    def members():
        return [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]

    def position(p):
        return m.uc.mem_read(p + 0x35, 1)[0]

    pool = [m.call(0x242500, ecx=lst, edx=i) for i in range(m.call(0x2424F0, ecx=lst))]
    for code, want in enumerate(composition):
        have = [p for p in members() if position(p) == code]
        for p in have[want:]:                               # native release to the free-agent list
            m.call(0x2BD900, ecx=team, edx=p, args=(1, 1), budget=int(2e9))
        for p in [p for p in pool if position(p) == code][:max(0, want - len(have))]:
            m.call(0x2425C0, ecx=lst, edx=p)
            raw = bytearray(m.uc.mem_read(p, 84))
            raw[0x27] = (raw[0x27] & 0xF0) | 1; raw[0x24] = (raw[0x24] & 0xF0) | 1   # a one-year contract
            struct.pack_into("<H", raw, 10, 60)
            m.uc.mem_write(p, bytes(raw))
            assert m.call(0xC3EE0, ecx=team, edx=p), "preseason append refused"
    assert sorted(position(p) for p in members()) == sorted(c for c, k in enumerate(composition) for _ in range(k))
    m.call(0xC3F00, ecx=team)
    released.clear()
    m.call(0x2BF9A0, ecx=team, edx=target, budget=int(2e10))
    n = m.uc.mem_read(team + 0x11C, 1)[0]
    counts = [0] * 17
    for i in range(n):
        counts[m.uc.mem_read(m.get(team + 4 * i) + 0x35, 1)[0]] += 1
    return counts, [m.uc.mem_read(p + 0x35, 1)[0] for p in released]


@unittest.skipUnless(HAVE_UC and RELEASED_BODY.is_file() and RELEASED_XBE.is_file(),
                     "the released v0.7 default.xbe and main ROST body (private) are absent")
class SmartCutTests(unittest.TestCase):
    """Noah 10/28: "make it smart, so teams aren't cutting guys that they need at certain positions"."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_franchise_economy as economy
        cls.released, cls.body = RELEASED_XBE.read_bytes(), RELEASED_BODY.read_bytes()
        cls.fixed = economy.apply(cls.released)[0]

    def test_a_58_man_club_cut_to_53_keeps_every_modern_minimum(self):
        # Every position at its modern minimum (46 with FB 1 and DT 4) plus 12 extras.
        club = list(MODERN_MIN)
        club[8], club[15] = 1, 4
        for code, extra in ((3, 3), (4, 2), (13, 2), (16, 3), (0, 1), (7, 1)):
            club[code] += extra
        self.assertEqual(sum(club), 58)
        counts, cut = _cut(self.fixed, self.body, club, 53)
        self.assertEqual(sum(counts), 53)
        for code, least in enumerate(MODERN_MIN):
            self.assertGreaterEqual(counts[code], least, f"position {code}: {counts}")
        self.assertEqual(len(cut), 5)

    def test_a_club_at_the_modern_minimums_cuts_only_its_extras(self):
        # 46 players: every position at its modern minimum except FB 1 and DT 4 (one over each). Cut to 44.
        club = list(MODERN_MIN)
        club[8], club[15] = 1, 4
        counts, cut = _cut(self.fixed, self.body, club, 44)
        self.assertEqual(sorted(cut), [8, 15])
        self.assertEqual(counts, list(MODERN_MIN))

    def test_the_released_cut_goes_below_the_modern_minimums(self):
        # Negative control: v0.7's native cut uses the old minimum table (FS 1, SS 1, HB 2, TE 2, DT 4, FB 1),
        # so on the same club it takes the safeties below two and keeps the extra fullback and tackle.
        club = list(MODERN_MIN)
        club[8], club[15] = 1, 4
        counts, cut = _cut(self.released, self.body, club, 44)
        self.assertNotEqual(sorted(cut), [8, 15])
        self.assertTrue(any(counts[code] < least for code, least in enumerate(MODERN_MIN)), counts)


if __name__ == "__main__":
    unittest.main()
