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
    backs = [p for p in slots if p.record.values["position"] == tdb.HB]
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


if __name__ == "__main__":
    unittest.main()
