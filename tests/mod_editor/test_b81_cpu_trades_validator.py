"""The validator's T2 checks (tools/franchise_invariants.py) for the CPU trades at every position (nfl2k5_cpu_trades).

A GENUINE trade of the CPU trades' shape: one man at a position other than QB for the buyer's own pick, posted on the
week 10 kick-off image (root 2505, 2026; the validator's own fixture, see test_b81_franchise_invariants) and run through
the game's own pending scan 0x2BC900, exactly as TradeExecutionTests does for 4b's quarterback. previous = the image
before the post (week counter 8), view = the state after the scan (week counter 9, the advance's own week + 1). Each
case changes the state in one way and must add exactly the named T2 failure. Fails on c4406481b (no T2 checks there:
the genuine trade is not even classified).
"""
from __future__ import annotations

import unittest

from tools import franchise_invariants as fi
from tests.mod_editor.test_b81_franchise_invariants import (MINNESOTA_KICKOFF, PICK_ROW1, QB34, Ram, failing, pinned)

USER_FLAG = 0xE5775C


def t2(report):
    return {r["invariant"] for r in report.violations if r["invariant"].startswith("T2")}


class CpuTradeValidatorTests(unittest.TestCase):
    BUYER = 5                            # CLE (52 active) pays its own fifth; the seller and man are found on the image

    @classmethod
    def setUpClass(cls):
        path = QB34 / "no-qb-2505-2026-w10-kickoff.b81mem.gz"
        pinned(path, MINNESOTA_KICKOFF)
        cls.image = fi.load_memory(path).regions
        view = Ram(cls.image).view()

        def tradeable(i):
            r = view.record(i)
            return r[0x25] & 31 >= 2 and r[0x24] & 15 and not r[0x53] & 1 and fi._fully_healthy(r)
        # The first legal package in club order: a seller no person manages with 51+ active, a position other than QB, K,
        # P (and LB, whose minimum pools two codes) where it keeps its starters healthy and its cut minimum after the sale.
        from mod_editor.core import nfl2k5_team_need as tn
        for seller in range(32):
            club = view.clubs[seller]
            if seller in (cls.BUYER, 15) or club.human or club.count < 51:
                continue
            for pos in (3, 4, 5, 6, 7, 9, 12, 13, 14, 15, 16):
                men = [i for i in club.active if tn.POOL[view.record(i)[0x35]] == pos]
                present = [i for i in men if tn.present(view.record(i))]
                if (len(men) >= tn.CUT_MIN[pos] + 1 and len(present) >= tn.SEATS[pos] + 1
                        and any(map(tradeable, men))):
                    cls.SELLER, cls.man = seller, next(i for i in reversed(men) if tradeable(i))
                    break
            else:
                continue
            break
        cls.word = 5 | cls.BUYER << 6

    def run_trade(self, before_edit=None, after_edit=None, prior_week=None, before_post=None):
        ram = Ram(self.image)
        if before_edit:
            before_edit(ram)
        if before_post:                                  # rows the same advance writes before the trade call
            before_post(ram)
        ram.post(self.SELLER, self.man, self.BUYER, self.word)
        after = ram.native_pending_scan()
        prior = Ram(self.image)
        if before_edit:
            before_edit(prior)
        prior.put(fi.WEEK, (prior_week if prior_week is not None else Ram(self.image).view().week - 1))
        previous = prior.view()
        after.put(fi.WEEK, previous.week + 1)
        if after_edit:
            after_edit(after)
        view = after.view()
        return fi.check(view, previous=previous), view, after

    def test_the_genuine_trade_is_classified_and_passes_every_T2_check(self):
        report, view, after = self.run_trade()
        q, = view.info["trades_since_previous"]["player_for_pick"]
        self.assertEqual((q["seller"], q["buyer"], q["player"], q["round"], q["year"]),
                         (self.SELLER, self.BUYER, self.man, 5, 0))
        self.assertNotIn(q["position"], (0, 1, 2))
        self.assertIn(self.man, view.clubs[self.BUYER].active)
        self.assertEqual(after.get(PICK_ROW1 + 32 * 4 + self.BUYER, 1), self.SELLER)
        self.assertEqual(t2(report), set())
        self.assertEqual(view.info["trades_since_previous"]["qb_for_pick"], [])

    def test_a_club_a_person_manages_fails_T2_human(self):
        report, _v, _a = self.run_trade(after_edit=lambda ram: ram.put(USER_FLAG + 4 * self.BUYER, 1))
        self.assertIn("T2.human", t2(report))

    def test_a_trade_at_or_after_the_deadline_week_fails_T2_deadline(self):
        deadline = Ram(self.image).get(0x5151C5, 1)
        report, _v, _a = self.run_trade(prior_week=deadline)
        self.assertEqual(t2(report), {"T2.deadline"})

    def test_the_first_contract_year_counts_only_in_the_preseason_from_the_second_season(self):
        """The starting roster carries length = years left for every man (this image: all of them), so in year index 0
        the rule would forbid every trade; from year index 1 it applies in the preseason only (N2: in season the
        ledger's signing rows say "just signed", and one-year veterans are the deadline's rentals), and only to the first
        year of a deal of 2+ years (b81 #46b)."""
        p = Ram(self.image).player(self.man)
        self.assertEqual(Ram(self.image).get(p + 0x24, 1) & 15, Ram(self.image).get(p + 0x27, 1) & 15)
        self.assertEqual(Ram(self.image).view().year_index, 0)
        year1 = lambda ram: ram.put(fi.YEAR, 1)
        report, _v, _a = self.run_trade(before_edit=year1, after_edit=year1)
        self.assertEqual(t2(report), set())                                  # in season: allowed (N2)

        def preseason(length):
            def edit(ram):
                ram.put(fi.YEAR, 1)
                ram.put(fi.STAGE, 7)
                at = ram.player(self.man)
                for off in (0x24, 0x27):
                    ram.put(at + off, (ram.get(at + off, 1) & 0xF0) | length, 1)
            return edit
        # b81 #46b: in the preseason only the first year of a deal of 2+ years is "just signed"; a one-year deal reads
        # "first contract year" for its whole term and is not.
        report, _v, _a = self.run_trade(before_edit=preseason(2), after_edit=preseason(2))
        self.assertIn("T2.player", t2(report))
        report, _v, _a = self.run_trade(before_edit=preseason(1), after_edit=preseason(1))
        self.assertNotIn("T2.player", t2(report))

    def test_a_buyer_over_the_cap_after_the_trade_fails_T2_cap(self):
        report, view, _a = self.run_trade(after_edit=lambda ram: ram.put(ram.team(self.BUYER) + 0x124,
                                                                          ram.get(fi.SALARY_CAP) + 1))
        self.assertIn("T2.cap", t2(report))

    def test_a_star_tagged_man_fails_T2_player(self):
        report, _v, _a = self.run_trade(before_edit=lambda ram: ram.put(ram.player(self.man) + 0x53,
                                                                         ram.get(ram.player(self.man) + 0x53, 1) | 1, 1))
        self.assertEqual(t2(report), {"T2.player"})

    def test_a_rookie_fails_T2_player(self):
        def rookie(ram):
            p = ram.player(self.man)
            ram.put(p + 0x25, ram.get(p + 0x25, 1) & 0xE0 | 1, 1)
        report, _v, _a = self.run_trade(before_edit=rookie)
        self.assertEqual(t2(report), {"T2.player"})

    def test_a_club_in_three_ledger_trade_groups_fails_T2_load(self):
        def busy(ram):
            cursor = ram.get(fi.LEDGER_CURSOR)
            for k in range(3):
                at = fi.LEDGER + 12 * ((cursor - 1 - k) % fi.LEDGER_CAPACITY)
                ram.put(at, 7 | fi.LAST_IN_GROUP)
                ram.put(at + 4, 0)
                ram.put(at + 8, ram.team(self.BUYER))
        report, _v, _a = self.run_trade(before_edit=busy)
        self.assertIn("T2.load", t2(report))

    def test_a_man_the_ledger_shows_signed_fails_T2_repeat(self):
        def signed(ram):
            at = fi.LEDGER + 12 * ((ram.get(fi.LEDGER_CURSOR) - 1) % fi.LEDGER_CAPACITY)
            ram.put(at, 1)
            ram.put(at + 4, ram.player(self.man))
            ram.put(at + 8, ram.team(self.SELLER))
        report, _v, _a = self.run_trade(before_edit=signed)
        self.assertEqual(t2(report), {"T2.repeat"})

    def test_a_ledger_row_the_advance_overwrote_does_not_count(self):
        """A signing row at a slot the same advance overwrote (here first by an injury row) may have been gone at the
        call, so T2.repeat leaves it to the observer's TT.repeat at the call; a row the advance did not touch counts
        (test_a_man_the_ledger_shows_signed_fails_T2_repeat)."""
        def oldest_signed(ram):
            at = fi.LEDGER + 12 * ram.get(fi.LEDGER_CURSOR)         # the oldest row: the next one written
            ram.put(at, 1 | fi.LAST_IN_GROUP)
            ram.put(at + 4, ram.player(self.man))
            ram.put(at + 8, ram.team(self.SELLER))

        def injury_row_first(ram):                                   # the advance writes one row before the call
            cursor = ram.get(fi.LEDGER_CURSOR)
            at = fi.LEDGER + 12 * cursor
            ram.put(at, 10 | fi.LAST_IN_GROUP)
            ram.put(at + 4, ram.player(self.man))
            ram.put(at + 8, ram.team(self.SELLER))
            ram.put(fi.LEDGER_CURSOR, (cursor + 1) % fi.LEDGER_CAPACITY)

        report, _v, _a = self.run_trade(before_edit=oldest_signed, before_post=injury_row_first)
        self.assertNotIn("T2.repeat", t2(report))

    def test_health_is_left_to_the_call(self):
        """A man hurt in both snapshots of one advance can be healthy at the call (healed, traded, hurt in that week's
        games): T2.player does not judge health; the observer's TT.player does, at the call."""
        def hurt(ram):
            p = ram.player(self.man)
            ram.put(p + 0x20, ram.get(p + 0x20) | 0x80000000 | 1 << 22)
        report, _v, _a = self.run_trade(before_edit=hurt)
        self.assertNotIn("T2.player", t2(report))

    def test_a_seller_left_without_its_starters_fails_T2_seller_depth(self):
        def hurt(ram):
            view = ram.view()
            pos = view.record(self.man)[0x35]
            for i in view.clubs[self.SELLER].active:
                if view.record(i)[0x35] == pos:
                    p = ram.player(i)
                    ram.put(p + 0x20, ram.get(p + 0x20) | 0x80000000 | 4 << 22)
        # hurt in both views (a man hurt only after the trade still counts as healthy at the trade)
        report, _v, _a = self.run_trade(before_edit=None, after_edit=hurt, prior_week=None)
        self.assertNotIn("T2.seller_depth", t2(report))
        ram = Ram(self.image)
        ram.post(self.SELLER, self.man, self.BUYER, self.word)
        after = ram.native_pending_scan()
        prior = Ram(self.image)
        hurt(prior)
        prior.put(fi.WEEK, Ram(self.image).view().week - 1)
        hurt(after)
        after.put(fi.WEEK, prior.view().week + 1)
        report = fi.check(after.view(), previous=prior.view())
        self.assertIn("T2.seller_depth", t2(report))

    def test_a_pick_that_did_not_pass_fails_T2_pick(self):
        report, _v, _a = self.run_trade(after_edit=lambda ram: ram.put(PICK_ROW1 + 32 * 4 + self.BUYER, self.BUYER, 1))
        self.assertEqual(t2(report), {"T2.pick"})

    def test_across_a_stage_advance_only_human_and_position_are_judged(self):
        ram = Ram(self.image)
        ram.post(self.SELLER, self.man, self.BUYER, self.word)
        after = ram.native_pending_scan()
        prior = Ram(self.image)
        prior.put(fi.STAGE, 7)                                 # not one weekly advance apart
        after.put(USER_FLAG + 4 * self.BUYER, 1)
        report = fi.check(after.view(), previous=prior.view())
        self.assertEqual(t2(report), {"T2.human"})
        self.assertTrue(failing(report))


if __name__ == "__main__":
    unittest.main()
