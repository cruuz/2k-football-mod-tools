"""b780 sub1: Rosters position changes (Q63).

Every club player on the v0.8 and v0.9 rosters is rank- and side-locked. A position change used to keep the old rank,
side and locks, so a locked starter moved onto a row that another locked starter owns at the new position and the
roster could not be saved or built ("conflicting depth locks"). Now the change unlocks him and puts him at the bottom
of his new position's chain on his club, the way sign and transfer do, and undo restores every field.
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
from test_nfl2k5_roster_records import league_body  # noqa: E402

V08_ROST = Path(os.environ.get("NFL2K5_V08_ROST_BODY", "") or "missing")


def lock_starter(doc: rr.RosterDocument, player: rr.Player) -> None:
    player.record.values["depth_rank"] = 0
    player.record.values["depth_side"] = 2
    player.record.values["unknown_52"] |= 0x03


class PositionChangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = rr.RosterDocument(league_body())
        players = self.doc.team_players(0)
        by_code: dict[int, list[rr.Player]] = {}
        for p in players:
            by_code.setdefault(p.record.values["position"], []).append(p)
        codes = sorted(c for c, ps in by_code.items() if ps and c not in (10,))
        self.a, self.b = by_code[codes[0]][0], by_code[codes[1]][0]
        for p in (self.a, self.b):
            lock_starter(self.doc, p)
        self.new_code = self.b.record.values["position"]

    def test_a_locked_starter_moves_to_the_bottom_of_his_new_position_unlocked(self) -> None:
        before = self.doc.change_position(self.a, self.new_code)
        peers = [p for p in self.doc.team_players(0) if p is not self.a and p.record.values["position"] == self.new_code]
        self.assertEqual(self.a.record.values["position"], self.new_code)
        self.assertEqual(self.a.record.values["depth_rank"], min(len(peers), rr.DEPTH_ROW_CAP))
        self.assertEqual(self.a.record.values["unknown_52"] & 0x1F, 0)
        self.doc.check_depth_locks()                          # before Q63 this refused the roster
        self.doc.restore_position(self.a, before)
        self.assertEqual({k: self.a.record.values[k] for k in before}, before)

    def test_the_same_position_changes_nothing(self) -> None:
        values = {k: self.a.record.values[k] for k in ("position", "depth_rank", "depth_side", "unknown_52")}
        self.doc.change_position(self.a, self.a.record.values["position"])
        self.assertEqual({k: self.a.record.values[k] for k in values}, values)

    def test_a_free_agent_only_changes_position(self) -> None:
        agent = self.doc.by_offset[self.doc.free_agents[0]]
        rank, side = agent.record.values["depth_rank"], agent.record.values["depth_side"]
        self.doc.change_position(agent, 0)
        self.assertEqual((agent.record.values["position"], agent.record.values["depth_rank"],
                          agent.record.values["depth_side"]), (0, rank, side))


@unittest.skipUnless(V08_ROST.is_file(), "NFL2K5_V08_ROST_BODY (the released v0.8 roster body) required")
class ReleasedRosterPositionChangeTests(unittest.TestCase):
    def test_sf_starting_lb_to_edge_saves(self) -> None:
        doc = rr.RosterDocument(V08_ROST.read_bytes(), scheme="one_pool")
        players = doc.team_players(0)
        lb = next(p for p in players if p.record.values["position"] == 11 and p.record.values["depth_rank"] == 0)
        self.assertTrue(lb.record.depth_locks["rank"])
        doc.change_position(lb, 16)
        doc.check_depth_locks()
        edges = [p for p in players if p.record.values["position"] == 16]
        self.assertEqual(lb.record.values["depth_rank"], min(len(edges) - 1, rr.DEPTH_ROW_CAP))


if __name__ == "__main__":
    unittest.main()
