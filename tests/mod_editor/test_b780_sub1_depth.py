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


# ------------------------------------------------------------------------------------------------ Q64: the KR arm
try:
    import unicorn
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    unicorn = None

from mod_editor.core import nfl2k5_depth_locks as locks  # noqa: E402


def run_kr_arm(code: bytes, roles: tuple[int, int], locks_bits: list[int], selected: int, count: int = 6):
    """Run the confirmed KR selection arm (its own bytes at 0x244360, up to its exit 0x244499) on a synthetic team."""
    uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
    uc.mem_map(0x244000, 0x1000)
    uc.mem_write(locks.KR_SET_VA, code)
    team, players = 0x300000, 0x310000
    uc.mem_map(team, 0x10000)
    uc.mem_map(players, 0x10000)
    record = bytearray(0x1F4)
    for i in range(count):
        record[i * 4:i * 4 + 4] = (players + i * 0x54).to_bytes(4, "little")
        uc.mem_write(players + i * 0x54 + 0x52, bytes([locks_bits[i]]))
    record[0x11C] = count
    record[0x195], record[0x196] = roles
    uc.mem_write(team, bytes(record))
    uc.reg_write(x86.UC_X86_REG_EDI, team)
    uc.reg_write(x86.UC_X86_REG_ESI, players + selected * 0x54)
    uc.reg_write(x86.UC_X86_REG_ESP, 0x308000)
    uc.emu_start(locks.KR_SET_VA, 0x244499, count=10000)
    after = bytes(uc.mem_read(team, 0x1F4))
    bits = [uc.mem_read(players + i * 0x54 + 0x52, 1)[0] for i in range(count)]
    return (after[0x195], after[0x196]), bits


@unittest.skipUnless(unicorn is not None, "Python unicorn required")
class KickReturnerArmTests(unittest.TestCase):
    # slot 1 is KR1 (lock 4), slot 3 is KR2 (lock 8); slot 2 carries an unrelated PR lock (16)
    BITS = [0, 4, 16, 8, 0, 0]

    def test_choosing_the_current_kr1_again_changes_nothing(self):
        roles, bits = run_kr_arm(locks.PATCHED_KR_SET, (1, 3), list(self.BITS), selected=1)
        self.assertEqual((roles, bits), ((1, 3), self.BITS))

    def test_revision_5_lost_the_second_returner(self):
        roles, bits = run_kr_arm(locks.V5_PATCHED_KR_SET, (1, 3), list(self.BITS), selected=1)
        self.assertEqual(roles, (1, 1))                       # KR2 became KR1 too (the bug)
        self.assertEqual(bits[3] & 0x0C, 0)

    def test_a_new_kr1_moves_the_old_one_to_kr2(self):
        for code in (locks.PATCHED_KR_SET, locks.V5_PATCHED_KR_SET):
            roles, bits = run_kr_arm(code, (1, 3), list(self.BITS), selected=4)
            self.assertEqual(roles, (4, 1))
            self.assertEqual([b & 0x0C for b in bits], [0, 8, 0, 0, 4, 0])
            self.assertEqual(bits[2] & 16, 16)                 # the punt returner keeps his lock

    def test_no_kr1_yet(self):
        for code in (locks.PATCHED_KR_SET, locks.V5_PATCHED_KR_SET):
            roles, bits = run_kr_arm(code, (0xFF, 0xFF), [0] * 6, selected=2)
            self.assertEqual((roles, [b & 0x0C for b in bits]), ((2, 0xFF), [0, 0, 4, 0, 0, 0]))

    def test_the_arm_fits_its_retail_allocation_and_upgrades_revision_5(self):
        self.assertLessEqual(len(locks.PATCHED_KR_SET), len(locks.RETAIL_KR_SET))
        site = next(s for s in locks.sites("retail", 6) if s.label == "screen_kr")
        old = next(s for s in locks.sites("retail", 5) if s.label == "screen_kr")
        self.assertNotEqual(site.after, old.after)
        self.assertEqual(locks.REVISION, 6)
