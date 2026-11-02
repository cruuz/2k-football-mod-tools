"""b780 b4-economy: retirements by age (row B4), camp churn (row D10) and injured players on no club (row D6).

B4 (SWeaR 11/01: Chuba Hubbard retired after a 1,600-yard season, an 8-year DT after career bests). The retirement
decision 0x2BCF90 behind every retirement asked only years pro and overall. nfl2k5_progression now rewrites it in
place: by age, and a club player who starts or played RETIRE_GAMES games never retires before his position's age.
The native tests run the pinned USA executable in Unicorn (skipped when the retail extraction is absent).

D6 (v0.8 known issue: 69 real players on no club and not free agents). The dated refresh checked the identity of every
2026 injured-reserve player and then placed him nowhere; nfl2k5_roster_refresh now puts him back on his club.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/mod_editor"), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_progression as pg  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_roster_refresh as refresh  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
# Private fixtures (skipped when the variables are unset): the released v0.8 disc's main ROST body and default.xbe
# (read out of the disc image), and the v0.8 recipe's roster-edits document.
V08_ROST = Path(os.environ.get("NFL2K5_V08_ROST_BODY", "") or "missing")
V08_PLAN = Path(os.environ.get("NFL2K5_V08_ROSTER_EDITS", "") or "missing")
V08_ROST_SHA256 = "526291e894e40ea92b3d5f0611b6a246d5c1ade2e7603d89b59cb24ecad6b048"


# ------------------------------------------------------------------------------------------------- D6 (synthetic)
def _sample():
    import test_roster_refresh as fixture
    return fixture.sample()


def _set(body, changes):
    """Apply {index: {field: value}} to the primary records of a body; ratings by name."""
    doc = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
    for index, fields in changes.items():
        record = doc.by_pool("primary")[index].record
        for key, value in fields.items():
            record.set(key, value)
    return doc.to_body()


class InjuredReserveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body, cls.plan = _sample()

    def _injured(self, plan, index, team):
        plan["free_agents"].remove(index)
        row = next(r for r in plan["players"] if r["index"] == index)
        row.update(status="RES", team=team)
        return row

    def test_an_injured_player_rejoins_a_club_with_room_unlocked_at_the_overflow_row(self):
        plan = copy.deepcopy(self.plan)
        index = plan["free_agents"][0]
        self._injured(plan, index, "T3")
        out, receipt = refresh.apply_body(self.body, plan)
        doc = rr.RosterDocument(out, scheme="one_pool", reference_year=2026)
        player = doc.by_pool("primary")[index]
        self.assertEqual(doc.club_of(player), 3)
        self.assertNotIn(player.offset, doc.free_agents)
        self.assertEqual((player.record.get("depth_rank"), player.record.get("depth_side")), (7, 7))
        self.assertFalse(any(player.record.depth_locks.values()))
        self.assertEqual(receipt["injured_reserve"]["rejoined"], 1)
        self.assertEqual(receipt["injured_reserve"]["released_for_room"], 0)
        self.assertEqual(len(doc.teams[3].slots), 43)
        self.assertEqual(refresh.apply_body(out, plan)[0], out)

    def test_a_full_club_releases_the_lowest_rated_small_deal_never_a_specialist_or_a_paid_player(self):
        plan = copy.deepcopy(self.plan)
        extra = plan["free_agents"][:11]
        for index in extra:
            plan["free_agents"].remove(index)
        plan["teams"][0]["active"] += extra                       # 53
        injured = plan["free_agents"][0]
        self._injured(plan, injured, "T0")
        active = plan["teams"][0]["active"]
        lowest_paid, low_small, kicker = active[5], active[6], active[7]
        plan["teams"][0]["specialists"]["k"] = kicker
        weak = {k: 10 for k in rr.RATING_BYTE_ORDER}
        weaker = {k: 5 for k in rr.RATING_BYTE_ORDER}
        body = _set(self.body, {
            lowest_paid: {**weaker, "contract_value": 900, "contract_length": 3, "contract_remaining": 3},
            low_small: {**weak, "contract_value": 30, "contract_length": 1, "contract_remaining": 1},
            kicker: {**weaker, "contract_value": 25, "contract_length": 1, "contract_remaining": 1}})
        out, receipt = refresh.apply_body(body, plan)
        doc = rr.RosterDocument(out, scheme="one_pool", reference_year=2026)
        primary = doc.by_pool("primary")
        self.assertEqual(len(doc.teams[0].slots), 53)
        self.assertEqual(doc.club_of(primary[injured]), 0)
        self.assertIsNone(doc.club_of(primary[low_small]))
        self.assertIn(primary[low_small].offset, doc.free_agents)
        self.assertEqual({k: primary[low_small].record.get(k) for k in refresh.CONTRACT_FIELDS},
                         dict.fromkeys(refresh.CONTRACT_FIELDS, 0))
        self.assertEqual(doc.club_of(primary[lowest_paid]), 0)    # the paid player stays
        self.assertEqual(doc.club_of(primary[kicker]), 0)         # the specialist stays
        self.assertEqual(doc.body[doc.teams[0].offset + rr.SPECIAL_TEAM_OFFSETS["k"]],
                         [doc.by_offset[o].index for o in doc.teams[0].slots].index(kicker))
        self.assertEqual(receipt["injured_reserve"]["released_players"], [primary[low_small].display])
        self.assertEqual(refresh.apply_body(out, plan)[0], out)

    def test_an_injured_player_without_a_contract_or_a_club_joins_the_free_agents(self):
        plan = copy.deepcopy(self.plan)
        no_contract, no_club = plan["free_agents"][0], plan["free_agents"][1]
        self._injured(plan, no_contract, "T2")
        self._injured(plan, no_club, "XX")
        body = _set(self.body, {no_contract: dict.fromkeys(refresh.CONTRACT_FIELDS, 0)})
        out, receipt = refresh.apply_body(body, plan)
        doc = rr.RosterDocument(out, scheme="one_pool", reference_year=2026)
        for index in (no_contract, no_club):
            self.assertIn(doc.by_pool("primary")[index].offset, doc.free_agents)
            self.assertIsNone(doc.club_of(doc.by_pool("primary")[index]))
        self.assertEqual(receipt["injured_reserve"]["to_free_agents"], 2)

    def test_every_injured_player_ends_on_a_club_or_the_free_agent_list(self):
        plan = copy.deepcopy(self.plan)
        injured = plan["free_agents"][:40]
        for k, index in enumerate(injured):
            self._injured(plan, index, f"T{k % 32}")
        out, receipt = refresh.apply_body(self.body, plan)
        doc = rr.RosterDocument(out, scheme="one_pool", reference_year=2026)
        placed = set(doc.free_agents) | {o for t in doc.teams[:32] for o in t.slots}
        self.assertEqual({i for i in injured if doc.by_pool("primary")[i].offset not in placed}, set())
        self.assertEqual(receipt["injured_reserve"]["rejoined"], 40)

    def test_cut_minimums_are_the_economy_smart_cut_table(self):
        source = (ROOT / "tools/franchise_economy/runtime.c").read_text(encoding="utf-8")
        start = source.index("cut_min[17] = {") + len("cut_min[17] = {")
        table = tuple(int(v) for v in source[start:source.index("}", start)].split(","))
        self.assertEqual(table, refresh.CUT_MINIMUMS)


@unittest.skipUnless(V08_ROST.is_file() and V08_PLAN.is_file(), "private v0.8 disc roster / b779 roster edits absent")
class InjuredReserveReleasedDiscTests(unittest.TestCase):
    """The v0.8 recipe's dated refresh replayed on the released disc roster (the old writer replays it unchanged)."""

    def test_the_injured_2026_players_are_back_on_their_clubs(self):
        import hashlib
        body = V08_ROST.read_bytes()
        if hashlib.sha256(body).hexdigest() != V08_ROST_SHA256:
            self.skipTest("v0.8 disc roster pin differs")
        plan = json.loads(V08_PLAN.read_text(encoding="utf-8"))["roster_refresh"]
        out, receipt = refresh.apply_body(body, plan)

        def nowhere(data):
            doc = rr.RosterDocument(data, scheme="one_pool", reference_year=2026)
            clubs = {o for t in doc.teams if t.is_club for o in t.slots}   # the franchise clubs, not alias squads
            reserves = {doc.primary_table + i * rr.PLAYER_SIZE for ids in doc.reserves.values() for i in ids}
            return doc, {p.index for p in doc.by_pool("primary") if doc.body[p.offset + 8] & 0x1C == 4 and
                         p.offset not in clubs and p.offset not in reserves and p.offset not in doc.free_agents}

        before_doc, before = nowhere(body)
        after_doc, after = nowhere(out)
        injured = {r["index"]: r["team"] for r in plan["players"] if r["status"] == "RES"}
        self.assertEqual(len(injured), 81)
        on_clubs = {p.index for p in before_doc.by_pool("primary") if any(before_doc.teams[t].is_club for t in p.teams)}
        self.assertEqual(set(injured) & on_clubs, set())          # the released disc: none of them on a club
        self.assertEqual(receipt["injured_reserve"]["rejoined"], 81)
        abbreviation = {t.index: t.abbreviation for t in after_doc.teams[:32]}
        for index, team in injured.items():
            self.assertEqual(abbreviation[after_doc.club_of(after_doc.by_pool("primary")[index])], team, index)
        self.assertTrue(all(len(t.slots) <= 53 for t in after_doc.teams[:32]))
        self.assertEqual(len(after_doc.free_agents),
                         len(before_doc.free_agents) + receipt["injured_reserve"]["released_for_room"])
        # what stays on no list is the retail legends and celebrities (no 2026 identity)
        self.assertEqual((len(before), len(after)), (93, 12))
        self.assertTrue(after <= before)
        self.assertEqual(before - after, set(injured))
        self.assertEqual(refresh.apply_body(out, plan)[0], out)


# ------------------------------------------------------------------------------------------------- B4 (native)
def _machine(payload, body):
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    m.load_retail_roster(body)
    m.seed(4242)
    # the rating as the decision reads it: call 0x246D80 (edx = 1), store st0
    stub, out = Machine.STOP + 0x100, Machine.ARENA + 0x1F8000
    m.uc.mem_write(stub, b"\xe8" + struct.pack("<i", 0x246D80 - (stub + 5)) + b"\xd9\x1d" + struct.pack("<I", out)
                   + b"\xc3")
    m.rating = lambda p: (m.call(stub, ecx=p, edx=1), struct.unpack("<f", bytes(m.uc.mem_read(out, 4)))[0])[1]
    return m


def _player(m, p, *, age, depth_row, games, prospect=False, value=None):
    """Set a record's age (as the decision computes it), depth row, prospect bit and this season's games."""
    raw = bytearray(m.uc.mem_read(p, 84))
    season = m.get(0x247AC7) + m.get(0xE576B8) + 1
    word = struct.unpack_from("<I", raw, 0x18)[0] & ~(127 << 21)
    struct.pack_into("<I", raw, 0x18, word | (((season - age) - 1900) & 127) << 21)
    depth = struct.unpack_from("<H", raw, 0x28)[0] & ~(7 << 10)
    struct.pack_into("<H", raw, 0x28, depth | depth_row << 10)
    raw[8] = (raw[8] | 0x10) if prospect else (raw[8] & ~0x10)
    if value is not None:
        struct.pack_into("<H", raw, 10, value)
    elif not struct.unpack_from("<H", raw, 10)[0]:
        struct.pack_into("<H", raw, 10, 50)
    pro = (struct.unpack_from("<I", raw, 0x24)[0] >> 8) & 31
    stream = m.ARENA + 0x1F0000 + 16 * ((p >> 2) & 0x3FF)
    m.uc.mem_write(stream, struct.pack("<I", (games & 0xFFFF) | pro << 23 | 0x80000000))
    struct.pack_into("<I", raw, 0x2C, stream)
    m.uc.mem_write(p, bytes(raw))


def _rate(m, p, club, n):
    return sum(m.call(pg.RETIRE_VA, edi=p, args=(club,), budget=200000) == 1 for _ in range(n)) / n


@unittest.skipUnless(HAVE_UC, "unicorn is not installed")
class RetirementDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, retail_roster
        cls.retail = retail_bytes()
        cls.roster = retail_roster()
        cls.applied, cls.receipt = pg.apply(cls.retail)

    def test_layout_fits_in_place_and_reads_applied(self):
        code, labels = pg.retirement_code()
        self.assertEqual(len(code), pg.RETIRE_SIZE)
        self.assertLessEqual(labels["used"], pg.RETIRE_SIZE)
        self.assertEqual(pg.status(self.retail), "retail")
        self.assertEqual(pg.status(self.applied), "applied")
        self.assertEqual(self.receipt["retirement_rule"]["contributor_games"], pg.RETIRE_GAMES)

    def test_a_beta79_image_reads_legacy_and_upgrades_only_the_decision(self):
        image = bytearray(self.applied)
        start = pg._offset(self.applied, pg.RETIRE_VA)
        image[start:start + pg.RETIRE_SIZE] = self.retail[start:start + pg.RETIRE_SIZE]
        image = bytes(image)                      # the b778 layer with the retail decision (digests are not read)
        self.assertEqual(pg.status(image), "legacy")
        upgraded, receipt = pg.apply(image)
        self.assertTrue(receipt["upgraded_from_legacy"])
        self.assertEqual(pg.status(upgraded), "applied")
        changed = [i for i in range(len(image)) if image[i] != upgraded[i]]
        self.assertTrue(all(start <= i < start + pg.RETIRE_SIZE or i < 0x1000 for i in changed))

    def test_a_contributor_never_retires_before_his_position_age(self):
        m = _machine(self.applied, self.roster)
        club = m.team_base
        for slot in range(0, 40, 5):
            p = m.get(club + 4 * slot)
            age = pg.NFL_RETIRE_BASE[m.uc.mem_read(p + 0x35, 1)[0]] + 24
            for row, games in ((0, 0), (6, pg.RETIRE_GAMES), (6, 16)):
                _player(m, p, age=age - 1, depth_row=row, games=games)
                self.assertEqual(_rate(m, p, club, 150), 0.0, (slot, row, games))
            # the same idle player off the club (a free agent): the age rule, never zero at a low overall
            _player(m, p, age=age - 1, depth_row=6, games=0)
            expect = pg.retirement_chance(position=m.uc.mem_read(p + 0x35, 1)[0], age=age - 1, overall=m.rating(p),
                                          year=0, club=False)
            rate = _rate(m, p, 0, 150)
            if expect == 0:
                self.assertEqual(rate, 0.0, slot)
            elif expect >= 0.05:
                self.assertGreater(rate, 0.0, slot)

    def test_the_native_decision_matches_the_model(self):
        m = _machine(self.applied, self.roster)
        club = m.team_base
        n = 700
        for slot in (1, 9, 17, 25, 33):
            p = m.get(club + 4 * slot)
            pos = m.uc.mem_read(p + 0x35, 1)[0]
            age0 = pg.NFL_RETIRE_BASE[pos] + 24
            for age, row, games, on_club in ((age0 - 3, 6, 2, True), (age0 - 3, 6, 12, False), (age0 + 1, 0, 14, True),
                                             (age0 + 3, 6, 0, True), (age0 + 6, 6, 0, True)):
                _player(m, p, age=age, depth_row=row, games=games)
                chance = pg.retirement_chance(position=pos, age=age, overall=m.rating(p), year=0, club=on_club,
                                              depth_row=row, games=games)
                rate = _rate(m, p, club if on_club else 0, n)
                bound = 4.5 * (chance * (1 - chance) / n) ** 0.5 + 0.012
                self.assertLess(abs(rate - chance), bound, (slot, age, row, games, on_club, rate, chance))

    def test_prospects_never_and_unsigned_players_always_as_retail(self):
        m = _machine(self.applied, self.roster)
        p = m.get(m.team_base + 4 * 3)
        _player(m, p, age=60, depth_row=6, games=0, prospect=True)
        self.assertEqual(_rate(m, p, m.team_base, 50), 0.0)
        _player(m, p, age=23, depth_row=0, games=16, value=0)
        self.assertEqual(_rate(m, p, m.team_base, 20), 1.0)

    def test_negative_control_retail_retires_producing_starters_in_their_twenties(self):
        m = _machine(self.retail, self.roster)
        club = m.team_base
        hits = 0
        for slot in range(0, 40, 2):
            p = m.get(club + 4 * slot)
            age = pg.NFL_RETIRE_BASE[m.uc.mem_read(p + 0x35, 1)[0]] + 24 - 2
            _player(m, p, age=age, depth_row=0, games=16)
            hits += _rate(m, p, club, 60) > 0
        self.assertGreater(hits, 0)


# ------------------------------------------------------------------------------------------------- D10 (native)
V08_XBE = Path(os.environ.get("NFL2K5_V08_XBE", "") or "missing")
V08_XBE_SHA256 = "5f987568bc88122f566e30cb5bb8a574acde4549b915b6f2514beab37ab3e9f3"


def _franchise(payload, body):
    """A fresh native franchise on the v0.8 disc roster (regular season, week 0), every club run by the CPU."""
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    size = len(body) - 0x40
    m.uc.mem_write(m.ARENA + 0x300, body)
    m.put(0xB72804, m.ARENA + 0x300)
    m.put(0xB72808, size)
    m.put(0xB7280C, size)
    m.fixup_roster(m.ARENA + 0x340)
    m.seed(12345)
    for a, v in ((0xE5FF80, 4), (0xE60120, 1), (0xE6000C, 5), (0xE60010, 5)):
        m.put(a, v)
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog acknowledgement only")
    m.released = []
    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: m.released.append(m.reg("EDX")), begin=0x2BD900, end=0x2BD900)
    m.call(0x13EE10, budget=2_000_000_000)
    return m


def _count(m, team):
    return m.uc.mem_read(team + 0x11C, 1)[0]


def _free_agents(m):
    lst = m.root + 0x38
    return [m.call(0x242500, ecx=lst, edx=i) for i in range(m.call(0x2424F0, ecx=lst))]


@unittest.skipUnless(HAVE_UC and V08_XBE.is_file() and V08_ROST.is_file(), "private v0.8 XBE / disc roster absent")
class CampTests(unittest.TestCase):
    """Revision 5 of the economy against the released (revision 4) bytes, on the v0.8 disc roster."""

    @classmethod
    def setUpClass(cls):
        import hashlib
        from mod_editor.core import nfl2k5_franchise_economy as economy
        cls.released, cls.body = V08_XBE.read_bytes(), V08_ROST.read_bytes()
        if hashlib.sha256(cls.released).hexdigest() != V08_XBE_SHA256:
            raise unittest.SkipTest("v0.8 XBE pin differs")
        cls.economy = economy
        cls.fixed, cls.receipt = economy.apply(cls.released)

    def test_the_released_economy_reads_legacy_and_upgrades_five_sites(self):
        self.assertEqual(self.economy.status(self.released), "legacy")
        self.assertEqual(self.receipt.get("upgraded_from"), "legacy")
        self.assertEqual(sorted(int(e["va"], 16) for e in self.receipt["edits"]),
                         sorted(self.economy.REVISION_5_SITES))
        self.assertEqual(self.economy.status(self.fixed), "applied")

    def _camp(self, payload, stage, size):
        """CPU club 1 brought to `size` with one-year free agents, then the economy's reconcile at `stage`."""
        from mod_editor.core import nfl2k5_franchise_economy_code as code
        m = _franchise(payload, self.body)
        team, lst = m.team_base + 500, m.root + 0x38
        m.put(0xE576A4, 5)                    # the draft stage: the native append takes up to 65 (less reserves)
        for p in _free_agents(m):
            if _count(m, team) >= size:
                break
            raw = bytearray(m.uc.mem_read(p, 84))
            if raw[0x35] >= 17:
                continue
            m.call(0x2425C0, ecx=lst, edx=p)
            raw[0x27] = (raw[0x27] & 0xF0) | 1; raw[0x24] = (raw[0x24] & 0xF0) | 1
            struct.pack_into("<H", raw, 10, 30)
            m.uc.mem_write(p, bytes(raw))
            self.assertTrue(m.call(0xC3EE0, ecx=team, edx=p))
        self.assertEqual(_count(m, team), size)
        m.put(0xE576A4, stage)
        m.released.clear()
        m.call(code.SYMBOLS["economy_reconcile"], ecx=team, budget=int(2e9))
        return _count(m, team), len(m.released)

    def test_after_the_draft_a_cpu_club_keeps_its_camp_until_the_season(self):
        self.assertEqual(self._camp(self.fixed, 5, 60), (60, 0))
        self.assertEqual(self._camp(self.fixed, 7, 60), (60, 0))
        self.assertEqual(self._camp(self.fixed, 8, 60)[0], 54)

    def test_negative_control_the_released_economy_cuts_the_camp_on_draft_day(self):
        self.assertEqual(self._camp(self.released, 5, 60), (54, 6))

    def _week(self, payload):
        """Every free agent unsigned for two weeks, then one in-season weekly pass (no retail fill draws)."""
        from mod_editor.core import nfl2k5_franchise_economy_code as code
        m = _franchise(payload, self.body)
        for p in _free_agents(m):
            raw = bytearray(m.uc.mem_read(p, 84))
            raw[0x25] = (raw[0x25] & 31) | 0x40
            m.uc.mem_write(p, bytes(raw))
        before = [_count(m, m.team_base + 500 * t) for t in range(32)]
        m.released.clear()
        m.call(code.SYMBOLS["economy_week"], ecx=m.ARENA + 0x1A0000, edx=0, args=(0, 0), budget=int(2e10))
        after = [_count(m, m.team_base + 500 * t) for t in range(32)]
        return before, after, len(m.released)

    def test_in_season_a_prove_it_deal_needs_an_open_spot_and_nobody_is_cut_for_it(self):
        before, after, released = self._week(self.fixed)
        self.assertEqual(released, 0)
        self.assertTrue(all(a >= b for a, b in zip(after, before)))
        self.assertTrue(all(a <= 53 for a in after))
        self.assertGreater(sum(after) - sum(before), 0)          # clubs with an open spot still sign

    def test_negative_control_the_released_economy_cuts_a_player_for_every_prove_it_deal(self):
        before, after, released = self._week(self.released)
        self.assertGreater(released, 10)


# ------------------------------------------------------------------------------------------------- B4 (a real season)
STATE_Y0 = Path(os.environ.get("NFL2K5_B780_Y0_STATE", "") or "missing")


def _season_end(payload, state, seed):
    """Run the native retirement pass 0x2BDB00 on the league saved at the end of a simulated v0.8 season (b4-economy
    sim/base3, every game played) with `payload`'s code, and return every retiree as (on a club, contributor, years
    past his position's age). Contributor = the rewritten decision's test: a starting depth row or 8+ games."""
    import zlib
    from tests.nfl2k5_supersim_draft_fixture import Machine
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    released = V08_XBE.read_bytes()
    m = Machine(payload, trace_writes=False)
    raw = state.read_bytes()
    meta, blob, offset = json.loads(raw[:256]), zlib.decompress(raw[256:]), 0
    for address, size in ((0x10000, 0x1510000 - 0x10000), (Machine.ARENA, 0x200000), (0x3000000, 0x10000)):
        m.uc.mem_write(address, blob[offset:offset + size]); offset += size
    m.team_base, m.root = meta["team_base"], meta["root"]
    new, old = XbeImage(payload), XbeImage(released)
    for section in new.sections:                     # the saved league ran the released code: write this payload's
        if section.raw_size:                         # code over it
            a, b = new.read(section.start, section.raw_size), old.read(section.start, section.raw_size)
            if a != b:
                m.uc.mem_write(section.start, a)
    m.uc.ctl_flush_tb()
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog acknowledgement only")
    clubs = {m.get(m.team_base + 500 * t + 4 * i) for t in range(32)
             for i in range(m.uc.mem_read(m.team_base + 500 * t + 0x11C, 1)[0])}
    m.seed(seed)
    m.call(0x2BDB00, budget=3_000_000_000)
    count, base = m.get(m.root), m.get(m.root + 4)
    records = bytes(m.uc.mem_read(base, 84 * count))
    season = m.get(0x247AC7) + m.get(0xE576B8) + 1
    out = []
    for i in range(count):
        rec = records[84 * i: 84 * i + 84]
        if not rec[8] & 8 or rec[0x35] >= 17:
            continue
        p = base + 84 * i
        pro = (struct.unpack_from("<I", rec, 0x24)[0] >> 8) & 31
        games, stream = 0, m.get(p + 0x2C)
        while stream:
            word = m.get(stream)
            if (word >> 16) & 0x7F == 0 and (word >> 23) & 0x1F == pro and not word & 0x30000000:
                games = word & 0xFFFF
            if word & 0x80000000:
                break
            stream += 4
        row = (struct.unpack_from("<H", rec, 0x28)[0] >> 10) & 7
        age = (season - ((struct.unpack_from("<I", rec, 0x18)[0] >> 21) & 127)) % 100
        over = age - pg.NFL_RETIRE_BASE[rec[0x35]] - 24
        out.append((p in clubs, p in clubs and (row < pg.RETIRE_STARTERS[rec[0x35]] or games >= pg.RETIRE_GAMES), over))
    return out


@unittest.skipUnless(HAVE_UC and STATE_Y0.is_file() and V08_XBE.is_file(), "private end-of-season league state absent")
class SeasonEndRetirementTests(unittest.TestCase):
    """The retirement pass on a real league after one simulated v0.8 season, released decision against the rewrite."""

    @classmethod
    def setUpClass(cls):
        cls.released = V08_XBE.read_bytes()
        cls.fixed = pg.apply(cls.released)[0]

    def test_no_contributor_retires_before_his_position_age_and_old_players_still_retire(self):
        for seed in (101, 202):
            retirees = _season_end(self.fixed, STATE_Y0, seed)
            self.assertEqual([r for r in retirees if r[1] and r[2] < 0], [], seed)
            self.assertGreater(sum(1 for r in retirees if r[0] and r[2] >= 0), 20, seed)
            self.assertGreater(len(retirees), 100, seed)

    def test_negative_control_the_released_decision_retires_contributors_in_their_prime(self):
        for seed in (101, 202):
            retirees = _season_end(self.released, STATE_Y0, seed)
            self.assertGreater(sum(1 for r in retirees if r[1] and r[2] < 0), 5, seed)


if __name__ == "__main__":
    unittest.main()
