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
        self.assertEqual(price["price_scale"], 0.80)
        qb = price["market_curve_capshare"]["QB"]
        self.assertAlmostEqual(qb[0], 0.245)                          # OverTheCap: the best-paid QB, 24.5% of the cap
        for group, row in price["market_curve_capshare"].items():
            self.assertEqual(row, sorted(row, reverse=True), group)
        self.assertEqual(DATA["reserve"]["permille"], [20, 25, 30, 35, 40, 50, 85, 130])
        self.assertEqual(DATA["cap_growth"]["factor"], economy.CAP_GROWTH)
        old_cheap = DATA["lengths"]["by_age_and_price"]["33+"]["<0.5%"]["length_pct"]
        self.assertEqual(old_cheap, {"1": 100.0})                     # a cheap 33+ veteran: one year, always

    def test_a_revision_eight_image_reads_legacy_and_upgrades_in_place(self):
        from tests.franchise_economy_revision8_sites import SITES
        old = dict(SITES)
        image = XbeImage(self.retail)
        for va in economy.REVISION_10_NEW:                            # the new sites back to retail
            size = len(next(s.patched for s in economy.sites() if s.va == va))
            old[va] = image.read(va, size)
        previous = _with(self.current, old)
        self.assertEqual(economy.status(previous), "legacy")
        upgraded, receipt = economy.apply(previous)
        self.assertEqual(upgraded, self.current)
        self.assertEqual(receipt.get("upgraded_from"), "legacy")
        # half an upgrade (one rewritten window new, the rest old) is foreign and refused
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
        # 24.5% of the cap x 0.80 = 19.6%: 1960 x (75300 / 100) / 100 game $1000 (rank 1); a tie at the top shares
        # ranks 1 and 2. Revision 8 priced the best QB at the top-five average x a cube of his overall.
        best = max(self.price(q) for t in range(32) for q in self.roster(t) if self.m.uc.mem_read(q + 0x35, 1)[0] == 0)
        self.assertIn(best, (1960 * 753 // 100, (1960 + 1880) // 2 * 753 // 100))

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

    def test_a_kicker_four_points_better_wins_the_job_in_camp(self):
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


if __name__ == "__main__":
    unittest.main()
