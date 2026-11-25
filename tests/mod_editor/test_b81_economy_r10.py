"""b81 franchise economy revision 10 (economy lane; coordinator rulings 2026-11-25 on its DESIGN.txt).

The ten-season panel 68001-68004 (8b180ed5): from 2031 every CPU club sat at 96-100% of the cap, up to 17 starter-grade
free agents a league were unsigned at week 18, 5-6 year deals were 22% of the active book (real 0.8%), and kickers and
punters never changed clubs. Each test fails on the revision-8 code (job/b81-economy-r10 6dd73d743): the owner, the
price by rank on the real market curve, falling free-agent asks, the length of a renewal by age and price, the reserve,
the restructure once, the cap casualties before re-signing, camp competition for kickers, and the upgrade in place.
Native tests run the real economy code under Unicorn on the retail executable and roster (skipped without them).
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import nfl2k5_franchise_economy as economy  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes, retail_roster  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "data/nfl2k5_franchise_economy.json").read_text())["revision_10"]
SYM = economy.SYMBOLS


def _with(payload, sites):
    """The image with `sites` ({va: bytes}) written and every section digest re-pinned."""
    image, out = XbeImage(payload), bytearray(payload)
    for va, code in sites.items():
        at = image.offset(va, len(code))
        out[at:at + len(code)] = code
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


class OwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.current, cls.receipt = economy.apply(cls.retail)

    def test_revision_ten_sites_and_cap_growth(self):
        self.assertEqual((economy.REVISION, self.receipt["revision"], economy.status(self.current)), (10, 10, "applied"))
        image = XbeImage(self.current)
        self.assertEqual(image.read(economy.OFFER_JITTER, 6), bytes.fromhex("31f690909090"))   # the offer's jitter is 0
        self.assertEqual(struct.unpack("<f", image.read(0x4FE7A0, 4))[0], struct.unpack("<f", struct.pack("<f", 1.065))[0])
        call = image.read(economy.RESIGN_STAGE, 5)
        self.assertEqual(call[0], 0xE8)
        self.assertEqual(economy.RESIGN_STAGE + 5 + struct.unpack("<i", call[1:])[0], SYM["economy_resign_stage"])
        self.assertEqual(SYM["economy_years_entry"], 0x322690)
        # the symbols other owners reach at fixed addresses did not move
        for name, va in (("economy_value", 0x2BD440), ("economy_cap", 0x2BD6D7), ("economy_restructure", 0x3B9F60),
                         ("economy_smart_cut", 0x3E21D0), ("economy_fill_gate", 0x31E605)):
            self.assertEqual(SYM[name], va, name)

    def test_the_tables_come_from_the_real_market(self):
        price = DATA["price"]
        self.assertEqual(price["price_scale"], 1.0)                  # retune 11/25 (0.80 left ~20% of the cap unspent)
        qb = price["market_curve_capshare"]["QB"]
        self.assertAlmostEqual(qb[0], 0.245)                          # OverTheCap: the best-paid QB, 24.5% of the cap
        for group, row in price["market_curve_capshare"].items():
            self.assertEqual(row, sorted(row, reverse=True), group)
        self.assertEqual(DATA["reserve"]["permille"], [15, 20, 25, 30, 35, 40, 60, 90])   # retune 11/25
        self.assertEqual(DATA["cap_growth"]["factor"], economy.CAP_GROWTH)
        old_cheap = DATA["lengths"]["by_age_and_price"]["33+"]["<0.5%"]["length_pct"]
        self.assertEqual(old_cheap, {"1": 100.0})                     # a cheap 33+ veteran: one year, always

    def test_revision_eight_and_nine_images_read_legacy_and_upgrade_in_place(self):
        from tests.franchise_economy_revision8_sites import as_revision
        for revision in (8, 9):                               # 9: the team-building lane's economy_room_for_signing
            previous = as_revision(self.current, self.retail, revision)
            self.assertEqual(economy.status(previous), "legacy", revision)
            upgraded, receipt = economy.apply(previous)
            self.assertEqual(upgraded, self.current, revision)
            self.assertEqual(receipt.get("upgraded_from"), "legacy")
        # half an upgrade (one rewritten window new, the rest old) is foreign and refused
        previous = as_revision(self.current, self.retail, 8)
        half = _with(previous, {0x2BD440: next(s.patched for s in economy.sites() if s.va == 0x2BD440)})
        self.assertEqual(economy.status(half), "foreign")
        with self.assertRaises(economy.EconomyError):
            economy.apply(half)

    def test_the_new_windows_are_unreferenced_retail_functions(self):
        from tools.franchise_economy import dead_code
        report = dead_code.verify(self.retail)
        self.assertEqual(report["references"], 0)
        for va in economy.R10_WINDOWS - {0x322690}:
            self.assertIn(hex(va), report["windows"])


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.franchise_economy.probe import start
        cls.patched = economy.apply(retail_bytes())[0]
        cls.m = m = start(retail_roster(), cls.patched)
        m.leaf(0x14E540, lambda: m.ret(1), reason="user confirmation only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational display only")
        cls.menu = m.ARENA + 0x1A0000
        cls.p = m.ARENA + 0x190000
        cls.human = [t for t in range(32) if m.call(0x13EC30, ecx=cls.team(t))]

    @classmethod
    def team(cls, t):
        return cls.m.team_base + 500 * t

    def roster(self, t):
        team = self.team(t)
        return [self.m.get(team + 4 * i) for i in range(self.m.uc.mem_read(team + 0x11C, 1)[0])]

    def price(self, p, aging=0):
        return self.m.call(0x2BD440, ecx=p, edx=0, args=(0, aging, 0), budget=50_000_000) & 0xFFFF

    def setUp(self):
        self.m.put(0xE3C278, economy.GAME_CAP)
        self.m.put(0xE576B8, 0)
        self.m.put(0xE576A4, 2)

    def synthetic(self, *, pos=3, rating=60, age=27, pro=5, weeks=0, value=0, years=0, kind=2, bonus=0):
        b = bytearray(84)
        b[8] = 4
        struct.pack_into("<H", b, 10, value)
        b[0x24:0x28] = bytes((years, pro | weeks << 5, kind | bonus << 4, years))
        b[0x35] = pos
        b[0x38:] = bytes([rating] * (84 - 0x38))
        season = self.m.get(0x247AC7) + 1
        struct.pack_into("<I", b, 24, ((season - age) % 100) << 21)
        self.m.uc.mem_write(self.p, bytes(b))
        return self.p

    def test_the_best_quarterback_is_priced_at_the_top_of_the_market(self):
        # 24.5% of the cap x 1.0 (retune 11/25; 0.80 before) = 2450 x (75300 / 100) / 100 game $1000 (rank 1); a tie at
        # the top shares ranks 1 and 2 (23.5%). Revision 8 priced the best QB at the top-five average x a cube of his overall.
        best = max(self.price(q) for t in range(32) for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 0)
        self.assertIn(best, (2450 * 753 // 100, (2450 + 2350) // 2 * 753 // 100))

    def test_a_league_wide_rating_shift_moves_no_price(self):
        # Every rostered receiver three points worse at everything: the ranks are the same men's ranks, so the
        # receivers' prices are the same prices (revision 8: every one of them falls with his overall).
        wrs = [q for t in range(32) for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 3]
        before = sorted(self.price(q) for q in wrs)
        saved = {q: bytes(self.m.uc.mem_read(q + 0x38, 84 - 0x38)) for q in wrs}
        try:
            for q in wrs:
                self.m.uc.mem_write(q + 0x38, bytes(max(0, v - 3) for v in saved[q]))
            after = sorted(self.price(q) for q in wrs)
        finally:
            for q, raw in saved.items():
                self.m.uc.mem_write(q + 0x38, raw)
        # the few receivers rated at the native rating's ceiling tie when lowered together, so the top 8 are left out
        self.assertEqual(after[:-8], before[:-8])
        self.assertGreater(len(before), 150)

    def test_a_free_agents_ask_falls_with_the_weeks_and_the_stage(self):
        asks = []
        for weeks in range(8):                             # a top-ten quarterback's ask, week by week unsigned
            p = self.synthetic(pos=0, rating=90, weeks=weeks)
            asks.append(self.price(p, aging=1))
        full = asks[0]
        self.assertEqual(asks, sorted(asks, reverse=True))
        self.assertLess(asks[-1], full)
        p = self.synthetic(pos=0, rating=90)
        self.m.put(0xE576A4, 6)
        self.assertLessEqual(self.price(p, aging=1), max(full // 2, asks[-1]))
        self.m.put(0xE576A4, 8)
        self.assertLessEqual(self.price(p, aging=1), max(full // 4, min(asks)))   # in season: a quarter, or his minimum

    def test_a_cheap_old_veteran_renews_for_one_year(self):
        # Revision 8 renewed every expiring player for 2-6 years (economy_contract(p, 2, 6) at 0x322ECE).
        t = next(t for t in range(32) if t not in self.human)
        team = self.team(t)
        p = next(q for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 3)
        saved = bytes(self.m.uc.mem_read(p, 84))
        try:
            season = self.m.get(0x247AC7) + 1
            word = struct.unpack("<I", self.m.uc.mem_read(p + 24, 4))[0] & ~(127 << 21)
            self.m.uc.mem_write(p + 24, struct.pack("<I", word | ((season - 35) % 100) << 21))   # 35 years old
            self.m.uc.mem_write(p + 0x38, bytes([45] * (84 - 0x38)))                            # a backup's ratings
            self.m.uc.mem_write(p + 0x24, bytes((self.m.uc.mem_read(p + 0x24, 1)[0] & 0xF0,)))  # expiring
            self.m.put(0xE3C278, 200000)
            self.m.call(0x322EB0, esi=p, edi=team, budget=50_000_000)
            self.assertEqual((self.m.uc.mem_read(p + 0x27, 1)[0] & 15, self.m.uc.mem_read(p + 0x24, 1)[0] & 15), (1, 1))
        finally:
            self.m.uc.mem_write(p, saved)
            self.m.call(0xC3F00, ecx=team)

    def test_the_years_a_player_wants_follow_the_real_mix(self):
        # 0x322690 (EDI = player) answers economy_years: a cheap 33+ veteran always 1, a young star 3 to 5.
        cheap = [self.m.call(0x322690, edi=self.synthetic(rating=40, age=34), budget=50_000_000)]
        self.assertEqual(cheap, [1])
        # retune 11/25 (gate E2: 88% of the <=25 veterans were on 1-year deals, real 27%): a man 29 or under signs for
        # 2-3 years where the draw said 1
        young = {self.m.call(0x322690, edi=self.synthetic(rating=r, age=a, pro=3), budget=50_000_000)
                 for a in (22, 25, 27, 29) for r in (40, 55, 70)}
        self.assertTrue(young and min(young) >= 2, young)
        self.assertEqual(self.m.call(0x322690, edi=0), 0xFFFFFFFF)

    def test_an_offer_must_leave_the_clubs_reserve(self):
        t = next(t for t in range(32) if t not in self.human)
        team = self.team(t)
        p = self.synthetic(rating=60)
        offer = self.m.ARENA + 0x1A0400
        self.m.uc.mem_write(offer, struct.pack("<II", p, team) + bytes((0, 0, 1, 2 << 5)) + struct.pack("<H", 200))
        charge = self.m.call(0xE6040, ecx=200, edx=2, args=(0, 0, 1)) + self.m.call(0xE6020, ecx=200, edx=0, args=(1,))
        self.m.call(0xC3F00, ecx=team)
        need = self.m.get(team + 0x124) + charge
        # exactly enough room for the deal: revision 8 signed him; the club now keeps its reserve (2-13% of the cap)
        for cap, expected in ((need, 0), (need * 6 // 5, 1)):
            self.m.put(0xE3C278, cap)
            self.assertGreater(self.m.call(SYM["economy_reserve"], ecx=team), 0)
            self.assertEqual(self.m.call(SYM["economy_offer_room"], ecx=offer), expected, cap)
        for h in self.human:                                  # a club a person owns keeps no reserve (ruling 7)
            self.assertEqual(self.m.call(SYM["economy_reserve"], ecx=self.team(h)), 0)

    def test_a_deal_is_restructured_once_and_only_with_three_years_left(self):
        # the same modest deal (not overpaid) three ways: revision 8 restructured all three
        fresh = self.synthetic(rating=80, value=100, years=4)          # the positive control: a plain 4-year deal
        self.assertGreater(self.m.call(0x3B9F60, ecx=fresh, edx=0) & 0xFFFFFFFF, 0)
        restructured = self.synthetic(rating=80, value=100, years=4, kind=6, bonus=2)
        self.assertEqual(self.m.call(0x3B9F60, ecx=restructured, edx=0), 0)
        two_left = self.synthetic(rating=80, value=100, years=2)
        self.assertEqual(self.m.call(0x3B9F60, ecx=two_left, edx=0), 0)

    def test_a_club_restructures_three_deals_at_most(self):
        # retune 11/25 (gate E3: some clubs held 5-9 restructured deals): economy_restructure_best refuses a club that
        # already has three; with two it restructures its best deal as before.
        t = next(t for t in range(32) if t not in self.human)
        team, men = self.team(t), self.roster(t)
        saved = {q: bytes(self.m.uc.mem_read(q, 84)) for q in men}
        try:
            for q in men:                                           # nobody restructured, nobody worth restructuring
                self.m.uc.mem_write(q + 0x24, bytes((1, self.m.uc.mem_read(q + 0x25, 1)[0], 2, 1)))
            big = men[0]                                            # one large 4-year deal: a restructure saves a lot
            self.m.uc.mem_write(big + 10, struct.pack("<H", 3000))
            self.m.uc.mem_write(big + 0x24, bytes((4, self.m.uc.mem_read(big + 0x25, 1)[0], 2, 4)))
            for q in men[1:3]:
                self.m.uc.mem_write(q + 0x26, bytes((6 | 2 << 4,)))
            self.assertEqual(self.m.call(SYM["economy_restructured"], args=(team,)), 2)
            self.assertEqual(self.m.call(SYM["economy_restructure_best"], args=(team,), budget=200_000_000), 1)
            self.assertEqual(self.m.uc.mem_read(big + 0x26, 1)[0], 6 | 2 << 4)
            self.m.uc.mem_write(big + 0x24, bytes((4, self.m.uc.mem_read(big + 0x25, 1)[0], 2, 4)))   # a fresh deal again
            self.m.uc.mem_write(men[3] + 0x26, bytes((6 | 2 << 4,)))                                     # three now
            self.assertEqual(self.m.call(SYM["economy_restructured"], args=(team,)), 3)
            self.assertEqual(self.m.call(SYM["economy_restructure_best"], args=(team,), budget=200_000_000), 0)
            self.assertEqual(self.m.uc.mem_read(big + 0x26, 1)[0], 2)
        finally:
            for q, raw in saved.items():
                self.m.uc.mem_write(q, raw)

    def test_a_release_cancels_the_trade_offers_that_name_the_man(self):
        # Panel 74003, 2031 (gate E8 / G6): an offer kept naming a man the economy had released after another club took
        # him onto its IR or practice squad (I8 "side B names a player his club does not have", eleven weeks). Every
        # economy release now runs the board's pruner 0x2BB9A0, which cancels an offer naming a man with no contract
        # years: the released man's offer goes, another offer stays. The native release alone leaves both.
        board, size = 0xE3C27C, 0x3C
        cpu = [t for t in range(32) if t not in self.human]
        x, y, z = cpu[0], cpu[1], cpu[2]

        def run(release):
            px, py, pz = self.roster(x)[5], self.roster(y)[5], self.roster(z)[6]
            saved = {q: bytes(self.m.uc.mem_read(q, 84)) for q in (px, py, pz)}
            rows = bytes(self.m.uc.mem_read(board, 15 * size))
            teams = {t: bytes(self.m.uc.mem_read(self.team(t), 500)) for t in (y,)}
            try:
                for slot, (b, pb) in ((2, (y, py)), (3, (z, pz))):
                    raw = bytearray(size)
                    struct.pack_into("<IIII", raw, 0, 2, 0, self.team(x), px)
                    struct.pack_into("<II", raw, 0x20, self.team(b), pb)
                    self.m.uc.mem_write(board + size * slot, bytes(raw))
                release(self.team(y), py)
                self.assertNotIn(py, self.roster(y))
                return self.m.get(board + 2 * size), self.m.get(board + 3 * size)
            finally:
                self.m.uc.mem_write(board, rows)
                for t, raw in teams.items():
                    self.m.uc.mem_write(self.team(t), raw)
                for q, raw in saved.items():
                    self.m.uc.mem_write(q, raw)

        self.assertEqual(run(lambda team, p: self.m.call(0x2BD900, ecx=team, edx=p, args=(1, 1), budget=50_000_000)), (2, 2))
        self.assertEqual(run(lambda team, p: self.m.call(SYM["economy_release"], ecx=team, edx=p, budget=50_000_000)), (0, 2))

    def test_cap_casualties_before_re_signing(self):
        # A CPU club short of its reserve + 2% of the cap cuts its most overpaid veteran (a 33-year-old receiver paid far
        # above his price) before the re-signing stage; a club a person owns is never touched.
        self.m.leaf(0x323720, lambda: self.m.ret(), reason="the native re-signing stage itself is not under test")
        wrs = {t: [q for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 3] for t in range(32)}
        cpu = next(t for t in range(32) if t not in self.human and len(wrs[t]) > 5)
        teams = [cpu] + self.human[:1]
        marks, saved = {}, {}
        season = self.m.get(0x247AC7) + 1
        for t in teams:
            p = wrs[t][-1]
            saved[p] = bytes(self.m.uc.mem_read(p, 84))
            word = struct.unpack("<I", self.m.uc.mem_read(p + 24, 4))[0] & ~(127 << 21)
            self.m.uc.mem_write(p + 24, struct.pack("<I", word | ((season - 33) % 100) << 21))
            self.m.uc.mem_write(p + 10, struct.pack("<H", 9000))
            self.m.uc.mem_write(p + 0x24, bytes((2, 10, 2, 2)))
            self.m.call(0xC3F00, ecx=self.team(t))
            marks[t] = p
        self.m.put(0xE3C278, max(self.m.get(self.team(t) + 0x124) for t in teams) + 100)
        self.m.call(SYM["economy_resign_stage"], ecx=self.menu, budget=2_000_000_000)
        self.assertNotIn(marks[cpu], self.roster(cpu))
        for t in self.human[:1]:
            self.assertIn(marks[t], self.roster(t))

    def test_a_club_with_a_hole_gets_first_call_on_a_prove_it_man(self):
        # Coordinator 11/25 (team building DESIGN 3.4): among the clubs that can sign a long-unsigned man, a club with a
        # hole he fills (shared team-need rule: its weakest need seat in the league's bottom quarter, 3+ points below
        # him) gets him first; otherwise the prove-it pass's own choice stands. Revision 8 had no such call.
        cpu = [t for t in range(32) if t not in self.human]
        x, other = cpu[0], cpu[1]
        team = self.team(x)
        wrs = [q for q in self.roster(x) if self.m.uc.mem_read(q + 0x35, 1)[0] == 3]
        saved = {q: bytes(self.m.uc.mem_read(q + 0x38, 84 - 0x38)) for q in wrs}
        count = self.m.uc.mem_read(team + 0x11C, 1)[0]
        try:
            for q in wrs:                                       # every receiver of club x far below the league's
                self.m.uc.mem_write(q + 0x38, bytes([30] * (84 - 0x38)))
            self.m.uc.mem_write(team + 0x11C, bytes((min(count, 52),)))   # an open spot this week
            self.m.put(0xE3C278, 200000)
            p = self.synthetic(pos=3, rating=90, weeks=7)
            chosen = self.m.call(SYM["economy_hole_first"], ecx=0, args=(p, 1, self.team(other)), budget=2_000_000_000)
            self.assertEqual(chosen, team)
            qb = self.synthetic(pos=0, rating=90, weeks=7)       # quarterbacks keep the old choice
            self.assertEqual(self.m.call(SYM["economy_hole_first"], args=(qb, 1, self.team(other)),
                                         budget=2_000_000_000), self.team(other))
        finally:
            self.m.uc.mem_write(team + 0x11C, bytes((count,)))
            for q, raw in saved.items():
                self.m.uc.mem_write(q + 0x38, raw)

    def _mirror_holes(self, pools, him):
        """(native, mirror) hole answers for every club and pool: economy_hole_p against team building's Python mirror
        of the shared rule (nfl2k5_team_building.view: need seats by depth row, empty seats 0, review S1's bench step;
        the header's mid-rank percentile; HOLE and MARGIN), on the league as it stands in memory."""
        from mod_editor.core import nfl2k5_team_building as tb, nfl2k5_team_need as tn
        point = lambda q: self.m.call(SYM["economy_points"], args=(q,), budget=5_000_000)
        league = []
        for t in range(32):
            men = []
            for q in self.roster(t):
                rec = bytes(self.m.uc.mem_read(q, 84))
                men.append(tb.Man(q, rec[0x35], point(q), tn.row(rec), rec[0x25] & 31, tn.present(rec)))
            league.append(men)
        native, mirror = [], []
        for pos in pools:
            p = self.synthetic(pos=pos, rating=him, weeks=7)
            mine, pool = point(p), tn.POOL[pos]
            for t in range(32):
                v = tb.view(league, t)
                weak = v.weak[pool]
                mirror.append(mine >= weak + tb.MARGIN and tb.percentile(v.scale[pool], weak) < tb.HOLE)
                native.append(bool(self.m.call(SYM["economy_hole_p"], args=(self.team(t), p), budget=200_000_000)))
        return native, mirror

    def _rate(self, q, value):
        self.m.uc.mem_write(q + 0x38, bytes([value] * (84 - 0x38)))

    def test_the_hole_is_team_buildings_rule(self):
        # Coordinator ruling N1 and the 11/25 header ruling (team building 713152903, 6c5a4ec17): one need rule. The
        # economy's prove-it hole equals team building's own reading of it (its Python mirror) for every club and pool:
        # the retail league, then an empty need seat (out three weeks: not present), an unseated better man (review S1:
        # he takes the seat, so the hole closes), and a tie at the quarter line (the mid-rank: not a hole; the
        # strictly-below count the first hole code used said it was).
        pools = (3, 4, 5, 6, 7, 9, 11, 12, 13, 14, 15, 16)
        native, mirror = self._mirror_holes(pools, 75)
        self.assertEqual(native, mirror)
        self.assertTrue(any(mirror) and not all(mirror))
        cpu = [t for t in range(32) if t not in self.human]
        x = cpu[0]
        wr = [q for q in self.roster(x) if self.m.uc.mem_read(q + 0x35, 1)[0] == 3]
        fs = {t: [q for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 5] for t in range(32)}
        saved = {q: bytes(self.m.uc.mem_read(q, 84)) for q in wr + [q for t in fs for q in fs[t]]}
        try:
            for q in wr:                                        # every receiver of club x out three weeks
                self.m.put(q + 0x20, (self.m.get(q + 0x20) & ~(255 << 22)) | 3 << 22)
            native, mirror = self._mirror_holes((3,), 75)
            self.assertEqual(native, mirror)
            self.assertTrue(native[x])
            for q, raw in saved.items():
                self.m.uc.mem_write(q, raw)
            # x's two receiver seats one weak, one strong, the rest as weak as the weak seat: a hole; then its
            # last-listed receiver, moved to the overflow row (an unsorted signing), rated well above that seat: he
            # takes it (review S1) and the hole closes
            row = lambda q: self.m.uc.mem_read(q + 0x28, 2)[0] | self.m.uc.mem_read(q + 0x29, 1)[0] << 8
            seats = sorted(wr[:-1], key=lambda q: (row(q) >> 10 & 7, wr.index(q)))[:2]
            for q in wr:
                self._rate(q, 30)                               # 0 points
            self._rate(seats[1], 85)
            last = wr[-1]
            self.m.uc.mem_write(last + 0x28, struct.pack("<H", (row(last) & 0xE3FF) | 7 << 10))
            self._rate(last, 31)                                # not three points above the seat: the hole stays
            native, mirror = self._mirror_holes((3,), 75)
            self.assertEqual(native, mirror)
            self.assertTrue(native[x])
            self._rate(last, 95)
            native, mirror = self._mirror_holes((3,), 75)
            self.assertEqual(native, mirror)
            self.assertFalse(native[x])
            for q, raw in saved.items():
                self.m.uc.mem_write(q, raw)
            for t in range(32):                                 # free safeties: 4 clubs low, 10 (x among them) tied
                for q in fs[t]:
                    self._rate(q, 40 if t in cpu[1:5] else 50 if t in cpu[5:14] or t == x else 80)
            native, mirror = self._mirror_holes((5,), 75)
            self.assertEqual(native, mirror)
            self.assertFalse(native[x])
        finally:
            for q, raw in saved.items():
                self.m.uc.mem_write(q, raw)

    def test_a_kicker_well_ahead_wins_the_job_in_camp(self):
        t = next(t for t in range(32) if t not in self.human and
                 sum(self.m.uc.mem_read(q + 0x35, 1)[0] == 1 for q in self.roster(t)) == 1)
        team = self.team(t)
        mine = next(q for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 1)
        root = self.m.get(0xB72918)
        fas = [self.m.get(self.m.get(root + 0x3C) + 4 * i) for i in range(self.m.get(root + 0x38))]
        fa = next(q for q in fas if self.m.uc.mem_read(q + 0x35, 1)[0] == 1)
        self.m.uc.mem_write(mine + 0x38, bytes([50] * (84 - 0x38)))
        self.m.uc.mem_write(fa + 0x38, bytes([95] * (84 - 0x38)))
        for q in (mine, fa):                                       # both healthy
            self.m.uc.mem_write(q + 0x23, bytes((self.m.uc.mem_read(q + 0x23, 1)[0] & 0x7F,)))
        self.m.put(0xE3C278, 200000)
        self.m.put(0xE576A4, 6)
        self.m.call(SYM["economy_camp"], ecx=team, edx=self.menu, budget=500_000_000)
        kickers = [q for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 1]
        self.assertEqual(kickers, [fa])


    def test_the_camp_edge_is_two_points(self):
        # retune 11/25 (gate E5: K/P jobs changed hands 10% a year at a four-point edge; real 34% / 28%): a free-agent
        # kicker who rates 3 points above the incumbent (0x246D80 in whole points) now wins the job; 1 point does not.
        t = next(t for t in range(32) if t not in self.human and
                 sum(self.m.uc.mem_read(q + 0x35, 1)[0] == 1 for q in self.roster(t)) == 1)
        team = self.team(t)
        mine = next(q for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 1)
        root = self.m.get(0xB72918)
        fas = [self.m.get(self.m.get(root + 0x3C) + 4 * i) for i in range(self.m.get(root + 0x38))]
        fa = next(q for q in fas if self.m.uc.mem_read(q + 0x35, 1)[0] == 1)
        point = lambda q: self.m.call(SYM["economy_points"], args=(q,), budget=5_000_000)
        saved = {q: bytes(self.m.uc.mem_read(q, 84)) for q in (mine, fa)}
        roster = bytes(self.m.uc.mem_read(team, 500))
        results = {}
        try:
            self.m.uc.mem_write(mine + 0x38, bytes([70] * (84 - 0x38)))
            base = point(mine)
            for want in (1, 3):
                v = next(v for v in range(70, 100) if (self.m.uc.mem_write(fa + 0x38, bytes([v] * (84 - 0x38))) or True)
                         and point(fa) - base == want)
                for q in (mine, fa):
                    self.m.uc.mem_write(q + 0x23, bytes((self.m.uc.mem_read(q + 0x23, 1)[0] & 0x7F,)))
                self.m.put(0xE3C278, 200000)
                self.m.put(0xE576A4, 6)
                self.m.call(SYM["economy_camp"], ecx=team, edx=self.menu, budget=500_000_000)
                results[want] = [q for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 1]
                self.m.uc.mem_write(team, roster)
                self.m.uc.mem_write(fa, saved[fa])
                self.m.uc.mem_write(mine, saved[mine][:0x38] + bytes([70] * (84 - 0x38)))
        finally:
            self.m.uc.mem_write(team, roster)
            for q, raw in saved.items():
                self.m.uc.mem_write(q, raw)
        self.assertEqual(results, {1: [mine], 3: [fa]})


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class ReviewFixTests(unittest.TestCase):
    """The Fable review of revision 10 (economy/FABLE_REVIEW.txt, 11/25): M1, S1, S2. Each case in a fresh machine
    (the reviewer's probe_camp4.py scenarios): the club with exactly one kicker, its kicker and the free-agent kickers
    rated by hand, every free-agent punter hurt, stage 6."""

    def camp(self, scenario):
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), economy.apply(retail_bytes())[0])
        m.leaf(0x14E540, lambda: m.ret(1), reason="user confirmation only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational display only")
        team = lambda t: m.team_base + 500 * t
        rb = lambda a: m.uc.mem_read(a, 1)[0]
        roster = lambda t: [m.get(team(t) + 4 * i) for i in range(rb(team(t) + 0x11C))]
        human = [t for t in range(32) if m.call(0x13EC30, ecx=team(t))]
        root = m.get(0xB72918)
        fas = [m.get(m.get(root + 0x3C) + 4 * i) for i in range(m.get(root + 0x38))]
        t = next(t for t in range(32) if t not in human and sum(rb(q + 0x35) == 1 for q in roster(t)) == 1)
        club = team(t)
        mine = next(q for q in roster(t) if rb(q + 0x35) == 1)
        kickers = [q for q in fas if rb(q + 0x35) == 1]
        m.put(0xE576A4, 6)
        m.put(0xE576B8, 0)
        mine_r = {"dear": 80, "wide": 45, "control": 80}[scenario]
        m.uc.mem_write(mine + 0x38, bytes([mine_r] * (84 - 0x38)))
        star = kickers[0]
        m.uc.mem_write(star + 0x38, bytes([99] * (84 - 0x38)))
        for q in kickers[1:]:
            m.uc.mem_write(q + 0x38, bytes([55] * (84 - 0x38)))
        for q in [mine] + kickers:
            m.uc.mem_write(q + 0x23, bytes((rb(q + 0x23) & 0x7F,)))
        for q in fas:
            if rb(q + 0x35) == 2:
                m.uc.mem_write(q + 0x23, bytes((rb(q + 0x23) | 0x80,)))
        m.call(0xC3F00, ecx=club)
        payroll = m.get(club + 0x124)
        s32 = lambda v: v - ((v >> 31) << 32)
        if scenario == "wide":                           # usable room just past 65,536 (the reviewer's 66,056)
            cap = payroll + 66000
            for _ in range(1000):
                m.put(0xE3C278, cap)
                u = s32(m.call(SYM["economy_usable_room"], ecx=club))
                if 65536 + 400 <= u <= 65536 + 700:
                    break
                cap += (65536 + 550) - u if abs((65536 + 550) - u) > 2 else 1
        else:
            cap = payroll + (700 if scenario == "dear" else 30000)
        m.put(0xE3C278, cap)
        m.call(0xC3F00, ecx=club)
        budget = s32(m.call(SYM["economy_fill_budget"], ecx=club))
        star_ask = m.call(0x2BD440, ecx=star, edx=0, args=(0, 1, 0), budget=50_000_000) & 0xFFFF
        m.call(SYM["economy_camp"], ecx=club, edx=m.ARENA + 0x1A0000, budget=1_500_000_000)
        now = [q for q in roster(t) if rb(q + 0x35) == 1]
        return dict(budget=budget, star_ask=star_ask, mine=mine, star=star, now=now,
                    usable=s32(m.call(SYM["economy_usable_room"], ecx=club)))

    def test_m1_a_club_that_cannot_afford_the_better_kicker_keeps_its_own(self):
        # Room 700 (usable negative, fill budget four minimums): the best free agent asks more than that. Before the
        # fix the club signed a 55-rated (43-point) kicker and released its 80-rated (75-point) one.
        got = self.camp("dear")
        self.assertGreater(got["star_ask"], got["budget"])
        self.assertEqual(got["now"], [got["mine"]])

    def test_m1_control_a_club_with_room_signs_the_better_kicker(self):
        got = self.camp("control")
        self.assertEqual(got["now"], [got["star"]])

    def test_s1_the_fill_budget_stops_at_16_bits(self):
        # Usable room past 65,535: the native signing compares the low word only, so an unclamped budget of 66,056 read
        # as 520 and the club signed a cheap kicker over the star (asking 1,736) it could easily pay.
        got = self.camp("wide")
        self.assertGreater(got["usable"], 0xFFFF)
        self.assertEqual(got["budget"], 0xFFFF)
        self.assertEqual(got["now"], [got["star"]])

    def test_s2_a_cell_at_one_year_always_draws_one_year(self):
        # The length cell "33+, under 0.5% of the cap" is 100 per cent one year; the hash's top byte 255 used to pass
        # its 255 and draw five years once in 256 seasons (the reviewer's 34-year-old receiver rated 40, season 125).
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), economy.apply(retail_bytes())[0])
        p = m.ARENA + 0x190000
        b = bytearray(84)
        b[8] = 4
        b[0x24:0x28] = bytes((0, 12, 2, 0))
        b[0x35] = 3
        b[0x38:] = bytes([40] * (84 - 0x38))
        season = m.get(0x247AC7) + 1
        struct.pack_into("<I", b, 24, ((season - 34) % 100) << 21)
        m.uc.mem_write(p, bytes(b))
        years = set()
        for index in range(600):
            m.put(0xE576B8, index)
            struct.pack_into("<I", b, 24, ((season + index - 34) % 100) << 21)
            m.uc.mem_write(p, bytes(b))
            years.add(m.call(0x322690, edi=p, budget=50_000_000))
        self.assertEqual(years, {1})

if __name__ == "__main__":
    unittest.main()
