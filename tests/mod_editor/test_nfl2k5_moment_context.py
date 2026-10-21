"""Static checks for the Anniversary moment context (b775 mo2): data, block layout, code and hook bytes.

No emulator. The stats data must add up per moment, the Super Bowl mask must name exactly the Super Bowl rows,
and the owner's code must decode completely with every branch landing on an instruction or a declared target.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core import nfl2k5_moment_context as m

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    Cs = None

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) \
    / "ESPN NFL 2K5 (USA)" / "default.xbe"
STATE = 0x14BBD60
EXTERNAL = {0x65D3D, 0xF4660, 0x20CC0B, m.PLAYER_LIVE, m.TEAM_LIVE, m.HEAP_ALLOC}


def doc():
    return json.loads(m.STATS_JSON.read_text(encoding="utf-8"))


class StatsData(unittest.TestCase):
    def test_every_row_present_and_super_bowl_flags_only_on_super_bowls(self):
        d = doc()
        self.assertEqual([x["row"] for x in d["moments"]], list(range(1, 52)))
        flagged = [x["row"] for x in d["moments"] if x["super_bowl"]]
        self.assertEqual(tuple(flagged), m.SUPER_BOWL_ROWS)
        for x in d["moments"]:
            if x["super_bowl"]:
                self.assertEqual(x["title"], m.SUPER_BOWL_TITLES[x["row"]])

    def test_seeded_moments_cite_a_pinned_source_and_their_rows(self):
        d = doc()
        seeded = [x for x in d["moments"] if x["status"] == "seeded"]
        self.assertEqual(len(seeded), 35)
        for x in d["moments"]:
            src = d["sources"][x["source"]]
            self.assertRegex(src["sha256"], "^[0-9a-f]{64}$")
            self.assertTrue(src["url"].startswith("https://"))
            if x["status"] == "seeded":
                self.assertTrue(x.get("included_play_ids") or x.get("included_rows"), x["row"])
                self.assertTrue(x["cut"]["first_play"], x["row"])
            else:
                self.assertEqual((x["team"], x["players"]), ({}, []))
                self.assertTrue(x["omitted"])

    def test_stat_sums_per_moment(self):
        """Team totals equal the sum over that side's players (team-only rows and net passing excepted)."""
        d = doc()
        team_only = set(("first_downs", "third_att", "third_conv", "fourth_att", "fourth_conv", "pass_plays",
                         "rush_plays", "penalties", "penalty_yds", "turnovers", "time_of_possession"))
        for x in d["moments"]:
            if x["status"] != "seeded":
                continue
            for side in ("away", "home"):
                team = x["team"][side]["stats"]
                sums = {}
                for p in x["players"]:
                    self.assertTrue(set(p["stats"]) <= set(d["stat_ids"]) - team_only, (x["row"], p["name"]))
                    if p["side"] == side:
                        for k, v in p["stats"].items():
                            sums[k] = sums.get(k, 0) + v
                for k, v in sums.items():
                    if k == "pass_yds":
                        self.assertLessEqual(team.get(k, 0), v, (x["row"], side, k))   # net of sack yards
                    else:
                        self.assertEqual(team.get(k, 0), v, (x["row"], side, k))
                for k in set(team) - team_only - {"pass_yds"}:
                    self.assertEqual(team[k], sums.get(k, 0), (x["row"], side, k))
                if "rush_plays" in team:
                    self.assertEqual(team["rush_plays"], team.get("rush_att", 0))
                if "pass_plays" in team:
                    self.assertGreaterEqual(team["pass_plays"], team.get("pass_att", 0))
                if "turnovers" in team:
                    self.assertGreaterEqual(team["turnovers"], team.get("pass_int", 0))
                if "third_conv" in team:
                    self.assertLessEqual(team["third_conv"], team["third_att"])
                for k, v in team.items():
                    self.assertGreaterEqual(v, -500, (x["row"], side, k))
                    self.assertLessEqual(v, 4000, (x["row"], side, k))

    def test_clock_time_of_possession_never_exceeds_elapsed_time(self):
        for x in doc()["moments"]:
            if x["status"] != "seeded" or "time_of_possession" not in x["team"]["home"]["stats"]:
                continue
            q, clock = x["situ"]["quarter"], x["situ"]["clock_seconds"]
            elapsed = (q - 1) * 900 + (900 - clock)
            top = sum(x["team"][s]["stats"].get("time_of_possession", 0) for s in ("away", "home"))
            self.assertLessEqual(top, elapsed + 120, x["row"])


class Blocks(unittest.TestCase):
    def moment(self):
        return {"row": 30, "team": {"home": {"stats": {"first_downs": 13, "pass_yds": 181}},
                                    "away": {"stats": {"pass_yds": 173}}},
                "players": [{"side": "home", "name": "Matt Ryan", "first": "Matthew", "last": "Ryan",
                             "stats": {"pass_att": 17, "pass_yds": 197}},
                            {"side": "away", "name": "Tom Brady", "first": "Thomas", "last": "Brady",
                             "stats": {"pass_cmp": 17}},
                            {"side": "away", "name": "Nobody Here", "stats": {"rush_att": 1}}]}

    def test_block_layout_keys_and_round_trip(self):
        rosters = {"home": [("Jake", "Matthews"), ("Matt", "Ryan")], "away": [("Tom", "Brady")]}
        raw, receipt = m.block_for(self.moment(), rosters)
        self.assertEqual(raw[:4], b"MST1")
        entries = m.parse_block(raw)
        ids = doc()["stat_ids"]
        self.assertEqual(entries, [(0xFE, ids["first_downs"], 13), (0xFE, ids["pass_yds"], 181),
                                   (0xFF, ids["pass_yds"], 173), (1, ids["pass_att"], 17),
                                   (1, ids["pass_yds"], 197), (65, ids["pass_cmp"], 17)])
        self.assertEqual(receipt["mapped"], 2)
        self.assertEqual(receipt["team_only"], ["away: Nobody Here"])
        self.assertEqual(len(raw), 8 + 4 * len(entries))

    def test_name_matching(self):
        roster = [("Dominique", "Rodgers-C."), ("Mike", "Thomas"), ("Michael", "Thomas"), ("Tony", "Romo")]
        players = [{"name": "Dominique Rodgers-Cromartie"}, {"name": "Mike Thomas", "first": "Michael",
                                                              "last": "Thomas"},
                   {"name": "Tony Romo", "first": "Antonio", "last": "Romo"}, {"name": ""}]
        mapping, _ = m.map_players(players, roster)
        self.assertEqual(mapping, {0: 0, 1: 1, 2: 3})

    def test_selection_layout_in_rebuilt_situ(self):
        """The selection hook reads: objective text, NUL, MCO1 (172 bytes), then MST1."""
        block, _ = m.block_for(self.moment(), {"home": [("Matt", "Ryan")], "away": [("Tom", "Brady")]})
        tail = m.COACH_MAGIC + bytes(m.COACH_SIZE - 4) + block + b"junk"
        self.assertEqual(m.trailer_after_coaches(tail), block)
        self.assertEqual(m.trailer_after_coaches(b"XXXX" + tail[4:]), b"")


@unittest.skipUnless(Cs, "capstone required")
class Code(unittest.TestCase):
    def test_code_decodes_and_branches_stay_inside_or_reach_declared_targets(self):
        code, labels = m.code_for(m.CAVE_VA, STATE)
        self.assertEqual(len(code), m.CAVE_SIZE)
        body = code[:labels["mask"] - m.CAVE_VA]
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        insns = list(md.disasm(body, m.CAVE_VA))
        self.assertEqual(sum(i.size for i in insns), len(body))
        starts = {i.address for i in insns}
        for i in insns:
            if i.mnemonic.startswith("j") or i.mnemonic == "call":
                target = i.operands[0].imm
                if m.CAVE_VA <= target < m.CAVE_VA + m.CAVE_SIZE:
                    self.assertIn(target, starts, f"{i.address:#x} {i.mnemonic}")
                else:
                    self.assertIn(target, EXTERNAL, f"{i.address:#x} {i.mnemonic} {target:#x}")
        self.assertEqual(code[len(body):len(body) + 8], struct.pack("<Q", m.super_bowl_mask()))
        self.assertTrue(set(code[len(body) + 8:]) <= {0xCC})

    def test_super_bowl_mask_names_exactly_the_super_bowl_rows(self):
        mask = m.super_bowl_mask()
        self.assertEqual([r for r in range(1, 52) if mask >> (r - 1) & 1], list(m.SUPER_BOWL_ROWS))

    def test_hooks_decode_and_reach_their_labels(self):
        _, labels = m.code_for(m.CAVE_VA, STATE)
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, va, before in m.HOOKS:
            self.assertEqual(sum(i.size for i in md.disasm(before, va)), len(before), name)
            after = m.hook_bytes(name, labels)
            self.assertEqual(len(after), len(before))
            first = next(md.disasm(after, va))
            self.assertEqual(first.mnemonic, "call" if name in ("player_stat", "team_stat") else "jmp")
            self.assertEqual(int(first.op_str, 16), labels[name])

    def test_state_and_constants_are_referenced_only_as_declared(self):
        code, labels = m.code_for(m.CAVE_VA, STATE)
        body = code[:labels["mask"] - m.CAVE_VA]
        self.assertEqual(body.count(struct.pack("<I", STATE)), 3)       # read, store, lookup
        self.assertEqual(body.count(struct.pack("<I", STATE + 4)), 2)   # arm, compare
        self.assertEqual(body.count(struct.pack("<I", m.MAIN_HEAP)), 1)


@unittest.skipUnless(RETAIL.exists(), f"private retail default.xbe required at {RETAIL}")
class Retail(unittest.TestCase):
    def test_cave_and_hook_sites_are_retail(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        import hashlib
        image = XbeImage(RETAIL.read_bytes())
        self.assertEqual(hashlib.sha256(image.read(m.CAVE_VA, m.CAVE_SIZE)).hexdigest(), m.RETAIL_CAVE_SHA256)
        for name, va, before in m.HOOKS:
            self.assertEqual(image.read(va, len(before)), before, name)
        self.assertEqual(image.read(m.SITUATION_TEXT, 20).decode("utf-16le"), "Situation\0")
        self.assertEqual(image.read(m.SUPER_BOWL_TEXT, 22).decode("utf-16le"), "Super Bowl\0")
        self.assertEqual(m.status(RETAIL.read_bytes()), "retail")



class MapPlayersOneSlotEach(unittest.TestCase):
    """fx1 (reviews pr69 #3, r3-native M3): two source players could map to one roster slot."""

    def test_a_loose_match_never_takes_an_exact_players_slot(self):
        roster = [("Mike", "Thomas"), ("Joe", "Burrow")]
        mapping, notes = m.map_players([{"name": "Michael Thomas"}, {"name": "Mike Thomas"}], roster)
        self.assertEqual(mapping, {1: 0})
        self.assertIn("team totals only", notes[0])

    def test_two_loose_matches_on_one_slot_leave_both_in_the_team_totals(self):
        roster = [("A.", "Smith"), ("Joe", "Burrow")]
        mapping, _notes = m.map_players([{"name": "Aldon Smith"}, {"name": "Alex Smith"}], roster)
        self.assertEqual(mapping, {})

    def test_distinct_slots_map_as_before(self):
        roster = [("Tony", "Romo"), ("Jason", "Witten"), ("T.", "Owens")]
        mapping, notes = m.map_players([{"name": "Antonio Romo", "first": "Tony", "last": "Romo"},
                                        {"name": "Jason Witten"}, {"name": "Terrell Owens"}], roster)
        self.assertEqual(mapping, {0: 0, 1: 1, 2: 2})
        self.assertEqual(len(notes), 1)


if __name__ == "__main__":
    unittest.main()
