"""b780 sub1: the default SPECIAL third-down back in a shipped roster (nfl2k5_third_down_back).

The 3DRB row is RB side row 1 (SPECIAL rows revision 3). The 2026 roster tools wrote RB3 there on every club with three
or more backs. The default is now the club's best receiving back (catch + route running; the starter included, the
power back at side row 0 excluded; a tie goes to the higher-ranked back), and running it twice changes nothing.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_third_down_back as tdb  # noqa: E402
from test_nfl2k5_roster_records import league_body  # noqa: E402

V09_ROST = Path(os.environ.get("NFL2K5_V09_ROST_BODY", "") or "missing")


def club_backs(body: bytes, club: int = 0):
    doc = rr.RosterDocument(body)
    slots = doc.team_players(club)
    # b780-int (rst2): the candidates are the club's backs on a locked chart row, as the default picks them (an injured
    # player the refresh put back at the overflow row is out)
    backs = tdb._locked(slots, tdb.HB)
    side = sorted(backs, key=lambda p: (p.record.values["depth_side"], slots.index(p)))
    return doc, backs, side


def with_backs(ratings: list[tuple[int, int]]) -> tuple[bytes, list[int]]:
    """Club 0 with len(ratings) running backs ranked in list order, sides as the 2026 tools write them."""
    doc = rr.RosterDocument(league_body())
    players = doc.team_players(0)
    for p in players:
        if p.record.values["position"] == tdb.HB:
            p.record.values["position"] = 3                     # no other backs on this club
    chosen = players[:len(ratings)]
    for rank, (p, (catch, route)) in enumerate(zip(chosen, ratings)):
        p.record.values.update(position=tdb.HB, depth_rank=rank, catch=catch, run_route=route,
                               depth_side=min(rr.DEPTH_SIDE_FOR_RANK.get(rank, rank), rr.DEPTH_ROW_CAP))
    return doc.to_body(normalise_commentary=False), [p.offset for p in chosen]


class DefaultThirdDownBackTests(unittest.TestCase):
    def run_once(self, ratings):
        body, offsets = with_backs(ratings)
        out, changes = tdb.default_third_down_backs(body)
        doc, _backs, side = club_backs(out)
        by = {p.offset: i for i, p in enumerate(offsets and [doc.by_offset[o] for o in offsets])}
        return body, out, changes, [by[p.offset] for p in side], offsets

    def test_a_better_receiving_backup_becomes_the_3drb(self):
        _, out, changes, order, _ = self.run_once([(60, 60), (50, 50), (40, 40), (70, 70)])
        self.assertEqual(order, [1, 3, 2, 0])                   # power back RB2 stays; RB4 is the 3DRB
        self.assertEqual(changes[0]["third_down_back_rank"], 4)
        self.assertEqual(tdb.default_third_down_backs(out), (out, []))   # twice changes nothing

    def test_the_starter_is_the_3drb_when_he_is_the_best_receiver(self):
        _, out, _, order, _ = self.run_once([(80, 80), (50, 50), (40, 40), (70, 70)])
        self.assertEqual(order, [1, 0, 2, 3])                   # the starter keeps passing downs
        self.assertEqual(tdb.default_third_down_backs(out)[1], [])

    def test_a_tie_goes_to_the_higher_ranked_back(self):
        _, _, _, order, _ = self.run_once([(60, 60), (50, 50), (40, 40), (60, 60)])
        self.assertEqual(order[:2], [1, 0])

    def test_the_power_back_is_never_the_3drb(self):
        _, _, _, order, _ = self.run_once([(40, 40), (90, 90), (50, 50)])   # RB2 is the best receiver
        self.assertEqual(order, [1, 2, 0])                      # he stays the power back; RB3 beats the starter

    def test_only_running_back_side_fields_change(self):
        body, out, _, _, offsets = self.run_once([(60, 60), (50, 50), (40, 40), (70, 70)])
        diff = [i for i, (a, b) in enumerate(zip(body, out)) if a != b]
        self.assertEqual(len(body), len(out))
        self.assertTrue(diff)
        self.assertTrue(all(any(o + 0x28 <= i <= o + 0x29 for o in offsets) for i in diff))
        before, after = rr.RosterDocument(body), rr.RosterDocument(out)
        for o in offsets:
            self.assertEqual(before.by_offset[o].record.values["depth_rank"], after.by_offset[o].record.values["depth_rank"])

    def test_one_or_two_backs_change_nothing(self):
        for ratings in ([(60, 60)], [(60, 60), (70, 70)]):
            body, _ = with_backs(ratings)
            self.assertEqual(tdb.default_third_down_backs(body), (body, []))


def with_receivers(speeds: list[int]) -> tuple[bytes, list[int]]:
    """Club 0 with len(speeds) receivers ranked in list order, sides as the 2026 tools write them."""
    doc = rr.RosterDocument(league_body())
    players = doc.team_players(0)
    for p in players:
        if p.record.values["position"] == tdb.WR:
            p.record.values["position"] = 9                     # no other receivers on this club
    chosen = players[:len(speeds)]
    for rank, (p, speed) in enumerate(zip(chosen, speeds)):
        p.record.values.update(position=tdb.WR, depth_rank=rank, speed=speed,
                               depth_side=min(rr.DEPTH_SIDE_FOR_RANK.get(rank, rank), rr.DEPTH_ROW_CAP))
    return doc.to_body(normalise_commentary=False), [p.offset for p in chosen]


def receiver_side_order(body: bytes, offsets: list[int]) -> list[int]:
    """Side order as rank indexes (0 = WR1)."""
    doc = rr.RosterDocument(body)
    slots = doc.team_players(0)
    wrs = [p for p in slots if p.record.values["position"] == tdb.WR]
    side = sorted(wrs, key=lambda p: (p.record.values["depth_side"], slots.index(p)))
    return [offsets.index(p.offset) for p in side]


class DefaultGadgetTests(unittest.TestCase):
    # the 2026 side order for six receivers: WR2, WR3, WR1, WR4, WR5, WR6 (rank indexes 1, 2, 0, 3, 4, 5)
    def run_once(self, speeds):
        body, offsets = with_receivers(speeds)
        self.assertEqual(receiver_side_order(body, offsets), [1, 2, 0, 3, 4, 5])
        out, rows = tdb.default_gadget_receivers(body)
        self.assertEqual(tdb.default_gadget_receivers(out)[0], out)          # twice changes nothing
        return receiver_side_order(out, offsets), rows[0]

    def test_the_fastest_deep_receiver_becomes_the_gad(self):
        order, row = self.run_once([80, 82, 81, 79, 95, 70])                # WR5 is the fastest
        self.assertEqual(order, [1, 2, 0, 4, 3, 5])                         # Z, slot and row 2 unchanged
        self.assertEqual((row["gad_rank"], row["exception"], row["changed"]), (5, False, True))

    def test_a_fastest_x_moves_from_the_kick_return_row(self):
        order, row = self.run_once([95, 82, 81, 79, 80, 70])                # WR1 (side row 2) is the fastest
        self.assertEqual(order, [1, 2, 3, 0, 4, 5])                         # the old row-3 receiver takes row 2
        self.assertEqual((row["gad_rank"], row["exception"]), (1, False))

    def test_a_fastest_z_or_slot_receiver_defaults_the_gad_to_the_x(self):
        for speeds in ([80, 95, 81, 79, 78, 70], [80, 82, 95, 79, 78, 70]):  # the Z, then WR3, is the fastest
            order, row = self.run_once(speeds)
            self.assertEqual(order[:2], [1, 2])                              # base-set side receivers unchanged
            self.assertEqual(order[3], 0)                                    # GAD = WR1, the X
            self.assertEqual((row["gad_rank"], row["exception"]), (1, True))

    def test_the_current_gad_already_fastest_changes_nothing(self):
        body, _ = with_receivers([80, 82, 81, 95, 78, 70])                  # WR4 is already side row 3
        out, rows = tdb.default_gadget_receivers(body)
        self.assertEqual((out, rows[0]["changed"], rows[0]["gad_rank"]), (body, False, 4))

    def test_fewer_than_four_receivers_change_nothing(self):
        body, _ = with_receivers([80, 82, 95])
        self.assertEqual(tdb.default_gadget_receivers(body)[0], body)


@unittest.skipUnless(V09_ROST.is_file(), "NFL2K5_V09_ROST_BODY (the released v0.9 roster body) required")
class ReleasedRosterTests(unittest.TestCase):
    def test_every_club_gets_its_best_receiving_back_and_twice_changes_nothing(self):
        body = V09_ROST.read_bytes()
        out, changes = tdb.default_third_down_backs(body)
        self.assertEqual(tdb.default_third_down_backs(out), (out, []))
        for club in tdb.CLUBS:
            doc, backs, side = club_backs(out, club)
            if len(backs) < 2:
                continue
            _, _, before = club_backs(body, club)
            self.assertEqual(side[0].offset, before[0].offset)           # the power back stays at side row 0
            best = max(tdb._receiving(p) for p in backs if p is not side[0])
            self.assertEqual(tdb._receiving(side[1]), best)
        self.assertGreater(len(changes), 0)
        rows = [c for c in changes if c["third_down_back_rank"] != 1]
        self.assertTrue(all(c["receiving"] > c["starter_receiving"] for c in rows))

    def test_both_defaults_in_one_pass(self):
        body = V09_ROST.read_bytes()
        out, report = tdb.default_special_rows(body)
        self.assertEqual(tdb.default_special_rows(out)[0], out)
        exceptions = [r["club"] for r in report["gadgets"] if r.get("exception")]
        self.assertEqual(len(exceptions), 9)                                # the fastest WR is the Z or WR3
        before, after = rr.RosterDocument(body), rr.RosterDocument(out)
        for club in tdb.CLUBS:
            slots_b, slots_a = before.team_players(club), after.team_players(club)
            wr_b = tdb._locked(slots_b, tdb.WR)                            # b780-int (rst2): locked rows, as the default
            wr_a = tdb._locked(slots_a, tdb.WR)
            side_b, rank_b = tdb._orders(slots_b, wr_b)
            side_a, _ = tdb._orders(slots_a, wr_a)
            self.assertEqual([p.offset for p in side_a[:2]], [p.offset for p in side_b[:2]])   # Z and slot stay
            fastest = min(wr_b, key=lambda p: (-tdb._speed(p), rank_b.index(p)))
            want = rank_b[0] if club in exceptions else fastest
            self.assertEqual(side_a[3].offset, want.offset)


if __name__ == "__main__":
    unittest.main()
