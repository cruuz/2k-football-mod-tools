"""b780 rst2: the release roster fixes of the 11/03 wave (BETA81_QUEUE Q39-Q49).

* Q43: the injured-reserve pass that releases players for room protects the dated chart's starters and releases the
  deepest chart rank first (synthetic league, the b780 b4-economy fixture).
* Q44: every free agent's contract block is zero after the refresh (the held b778 fd1 fix).
* The creation tool's pure rules: names without a generational suffix, body type from height and weight, face shape per
  build, the chart-slot position rules, commentary by recorded surname else jersey.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/mod_editor"), str(ROOT / "tools"), str(ROOT / "tools/b780")]

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_roster_refresh as refresh  # noqa: E402
from test_b780_b4_economy import _sample, _set  # noqa: E402


def entry(rank, abb="LCB", grp="Base 4-3 D"):
    return {"pos_grp": grp, "pos_abb": abb, "pos_rank": str(rank), "pos_slot": "1"}


class ReleaseForRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body, cls.plan = _sample()

    def full_club(self):
        """T0 holds 53 players and one injured player rejoins: exactly one player must go."""
        plan = copy.deepcopy(self.plan)
        extra = plan["free_agents"][:11]
        for index in extra:
            plan["free_agents"].remove(index)
        plan["teams"][0]["active"] += extra
        injured = plan["free_agents"][0]
        plan["free_agents"].remove(injured)
        next(r for r in plan["players"] if r["index"] == injured).update(status="RES", team="T0")
        return plan, plan["teams"][0]["active"], injured

    def chart(self, plan, ranks):
        by = {r["index"]: r for r in plan["players"]}
        for index, rank in ranks.items():
            by[index]["depth_source"] = entry(rank)

    def weak_small_deal(self, players, rating):
        ratings = {k: rating for k in rr.RATING_BYTE_ORDER}
        return {i: {**ratings, "contract_value": 30, "contract_length": 1, "contract_remaining": 1} for i in players}

    def test_the_seam_is_the_release_policy(self):
        self.assertEqual(refresh.ROOM_POLICY, "release")
        left = refresh._make_room("T0", [1, 2, 3], set(), {1: 3, 2: 3, 3: 3}, [0] * 17, {}, lambda i: False,
                                  lambda i: 50 - i, 2)
        self.assertEqual(left, [3])

    def test_a_charted_starter_stays_while_a_backup_can_go(self):
        plan, active, injured = self.full_club()
        starter, backup = active[5], active[6]
        self.chart(plan, {**{i: 2 for i in active}, starter: 1, backup: 3})      # everyone else is a listed backup
        # the starter is the lowest rated small deal, as the old rule would release him
        body = _set(self.body, {**self.weak_small_deal([starter], 1), **self.weak_small_deal([backup], 40)})
        out, receipt = refresh.apply_body(body, plan)
        self.assertEqual(len(receipt["injured_reserve"]["released_players"]), 1)
        doc = rr.RosterDocument(out, scheme="one_pool", reference_year=2026)
        primary = doc.by_pool("primary")
        self.assertEqual(doc.club_of(primary[starter]), 0)
        self.assertIsNone(doc.club_of(primary[backup]))
        self.assertEqual(refresh.apply_body(out, plan)[0], out)

    def test_the_deepest_chart_rank_goes_first_and_a_player_the_chart_does_not_list_is_the_deepest(self):
        ranks = {1: 2, 2: 6}                                  # player 3 is not on the chart, player 4 is kept
        left = refresh._make_room("T0", [1, 2, 3, 4], {4}, {i: 3 for i in (1, 2, 3, 4)}, [0] * 17, ranks,
                                  lambda i: False, lambda i: 50, 2)
        self.assertEqual(left, [3, 2])
        self.assertEqual(refresh.charted_ranks([{"index": 1, "depth_source": entry(4)}, {"index": 2}]), {1: 4})

    def test_a_starter_goes_when_nobody_else_can(self):
        refresh_rank = refresh.STARTER_CHART_RANK
        left = refresh._make_room("T0", [1, 2], set(), {1: 3, 2: 3}, [0] * 17, {1: refresh_rank, 2: refresh_rank},
                                  lambda i: False, lambda i: 50 + i, 1)
        self.assertEqual(left, [1])                           # both are starters: the old order (lowest rated) decides


class FreeAgentContractTests(unittest.TestCase):
    def test_every_free_agent_ends_with_a_zero_contract_block(self):
        body, plan = _sample()
        free = plan["free_agents"][:3]
        with_contract = {i: {"contract_value": 40, "contract_length": 2, "contract_remaining": 2, "contract_type": 1,
                             "contract_bonus": 3} for i in free[:2]}
        out, receipt = refresh.apply_body(_set(body, with_contract), plan)
        doc = rr.RosterDocument(out, scheme="one_pool", reference_year=2026)
        for index in free:
            record = doc.by_pool("primary")[index].record
            self.assertEqual({k: record.get(k) for k in refresh.CONTRACT_FIELDS}, dict.fromkeys(refresh.CONTRACT_FIELDS, 0))
        self.assertEqual(receipt["free_agent_contracts_cleared"] >= 2, True)
        self.assertEqual(refresh.apply_body(out, plan)[0], out)


class CreationRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import rst2_create_players as create
        cls.create = create

    def test_names_lose_a_generational_suffix_and_split_at_the_first_space(self):
        c = self.create
        self.assertEqual(c.split_name("Kenneth Murray, Jr."), ("Kenneth", "Murray"))
        self.assertEqual(c.split_name("Joe Milton III"), ("Joe", "Milton"))
        self.assertEqual(c.split_name("A.J. Terrell"), ("A.J.", "Terrell"))
        self.assertEqual(c.split_name("Jared Harrison-Hunte"), ("Jared", "Harrison-Hunte"))
        self.assertEqual(c.split_name("Dont'e Thornton Jr."), ("Dont'e", "Thornton"))

    def test_body_type_from_bmi(self):
        c = self.create
        self.assertEqual([c.body_for(70, 165), c.body_for(72, 200), c.body_for(75, 250), c.body_for(78, 325)], [0, 1, 2, 3])

    def test_face_shape_is_a_function_of_the_build_and_the_gsis_id(self):
        c = self.create
        for body in range(4):
            self.assertEqual(c.face_for("00-0031345", body), c.face_for("00-0031345", body))
            self.assertIn(c.face_for("00-0031345", body), c.FACES[body])
        self.assertEqual(c.face_for("00-0029592", 3), 6)      # Kevin Zeitler (10/14 plan): extra-large build, face 6

    def test_chart_slots_decide_defensive_positions(self):
        c = self.create
        rows = [{"fields": {"position": 15}, "depth_source": {"pos_grp": "Base 3-4 D", "pos_abb": "LDE"}},
                {"fields": {"position": 16}, "depth_source": {"pos_grp": "Base 4-3 D", "pos_abb": "LDE"}},
                {"fields": {"position": 16}, "depth_source": {"pos_grp": "Base 3-4 D", "pos_abb": "SLB"}},
                {"fields": {"position": 11}, "depth_source": {"pos_grp": "Base 4-3 D", "pos_abb": "SLB"}}]
        slots = c.Slots(rows)
        de = {"depth_chart_position": "DE", "position": "DL"}
        olb = {"depth_chart_position": "OLB", "position": "LB"}
        four = {"pos_grp": "Base 4-3 D", "pos_abb": "LDE", "pos_rank": "1"}
        three = {"pos_grp": "Base 3-4 D", "pos_abb": "LDE", "pos_rank": "1"}
        self.assertEqual(slots.position(de, [four], 250), "EDGE")
        self.assertEqual(slots.position(de, [three], 250), "DT")
        self.assertEqual(slots.position(de, [four, three], 250), "EDGE")      # a heavy end with both listings is a tackle
        self.assertEqual(slots.position(de, [four, three], 300), "DT")
        self.assertEqual(slots.position(de, [], 265), "EDGE")
        self.assertEqual(slots.position(olb, [], 230), "LB")
        self.assertEqual(slots.position(olb, [], 255), "EDGE")
        self.assertEqual(slots.position({"depth_chart_position": "LS", "position": "LS"}, [], 250), "C")
        self.assertEqual(slots.position({"depth_chart_position": "RB", "position": "RB"}, [], 210), "HB")
        fs = {"depth_chart_position": "FS", "position": "DB"}
        ss_slot = {"pos_grp": "Base 4-3 D", "pos_abb": "SS", "pos_rank": "3"}
        slots.slot[("Base 4-3 D", "SS")] = "SS"
        self.assertEqual(slots.position(fs, [ss_slot], 200), "SS")

    def test_commentary_is_the_recorded_surname_else_the_jersey_number(self):
        c = self.create
        ids = rr.recorded_surname_ids()
        name, cue = next(iter(ids.items()))
        self.assertEqual(c.commentary(name, 5), cue)
        self.assertEqual(c.commentary("Zzyzzyva", 49), rr.number_commentary_id(49))


if __name__ == "__main__":
    unittest.main()
