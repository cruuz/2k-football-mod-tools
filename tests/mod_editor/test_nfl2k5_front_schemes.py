"""b776-de1: EDGE players fill edge slots, LB slots are LBs (Noah, 10/18 playtest, 22 Giants classic team).

Covers the roster half (which rule an authored historic file takes, and what the 3-4 rule does) and the book half
(Prevent keeps its dropping linebacker at LB). Pure data and synthetic resources: no private files needed.
"""
import csv
import glob
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "tools"):
    sys.path.insert(0, str(path))
from mod_editor.core import nfl2k5_front_schemes as fs  # noqa: E402
import nfl2k5_roster_reclassify as rc  # noqa: E402
import nfl2k5_playbook_position_recode as pr  # noqa: E402

OLB, ILB, DT, DE = rc.ENUM_OLB, rc.ENUM_ILB, rc.ENUM_DT, rc.ENUM_DE


def team_resource(rows, label="h-test"):
    """rows: (name, position enum, rank, weight). A one-team Resource without bytes."""
    players = {}
    for i, (name, pos, rank, weight) in enumerate(rows):
        off = 0x100 + i * 0x54
        players[off] = rc.Player(off, pos, rank << rc.RANK_SHIFT, name, [0], weight)
    team = rc.Team(0, 0, "T", "TST", 0, None, list(players), 0)
    tables = {"secondary_players": {"offset": 0x10, "end": 0x20}}
    return rc.Resource(0, 0, label, b"", tables, players, [team])


def pools(resource, moves):
    out = {}
    for m in moves:
        pos = m.new_position
        out.setdefault({DE: "EDGE", DT: "DT", ILB: "LB"}[pos], []).append((m.new_word >> rc.RANK_SHIFT & 7, m.player.name))
    return {k: [n for _r, n in sorted(v)] for k, v in out.items()}


GIANTS_22 = [("Williams", DE, 0, 302), ("Ojulari", DE, 1, 250), ("Ward", DE, 2, 287), ("Mondeaux", DE, 3, 280),
             ("Lawrence", DT, 0, 342), ("Ellis", DT, 1, 350), ("Anderson", DT, 2, 266),
             ("Thibodeaux", OLB, 0, 250), ("Ximines", OLB, 1, 250), ("Fox", OLB, 2, 260),
             ("McFadden", ILB, 0, 232), ("Coughlin", ILB, 1, 245), ("Smith", ILB, 2, 245), ("Brown", ILB, 3, 233)]


class MappingTests(unittest.TestCase):
    def test_modern_cut_matches_the_stock_book_resolver(self):
        from mod_editor.core import nfl2k5_stock_books as stock
        self.assertEqual(fs.MODERN_FIRST_SEASON, stock.MODERN_FIRST_SEASON)
        self.assertEqual(set(fs.STOCK_ODD_BOOKS), set(rc.PURE_THREE_FOUR_BOOKS))

    def test_listed_team_seasons_take_the_three_four_rule_where_the_book_asks_for_roles(self):
        self.assertEqual(fs.mapping_scheme("classic", "giants_2022", "NYG", 2022), "3-4")
        self.assertEqual(fs.mapping_scheme("classic", "packers_2010", "GB", 2010), "3-4")
        self.assertEqual(fs.mapping_scheme("moments", "patriots_2007", "NE", 2007), "3-4")      # modern NE book
        self.assertEqual(fs.mapping_scheme("moments", "steelers_2025", "PIT", 2025), "3-4")     # modern PIT book

    def test_pure_three_four_stock_books_keep_the_retail_slot_meaning(self):
        for key, abbr, season in (("steelers_2005", "PIT", 2005), ("ravens_2019", "BAL", 2019), ("chargers_2006", "SD", 2006)):
            self.assertEqual(fs.mapping_scheme("classic", key, abbr, season), "4-3", key)
        self.assertEqual(fs.mapping_scheme("moments", "patriots_2003", "NE", 2003), "4-3")      # stock NE book

    def test_unlisted_team_seasons_keep_the_historic_rule(self):
        self.assertEqual(fs.mapping_scheme("classic", "giants_2016", "NYG", 2016), "4-3")
        self.assertEqual(fs.mapping_scheme("moments", "giants_2007", "NYG", 2007), "4-3")

    def test_every_listed_key_exists_and_heavy_end_cross_check_holds(self):
        data = fs.load()
        groups = {"classic": ROOT / "data/nfl2k5_classic_teams", "moments": ROOT / "data/nfl2k5_espn25_more_teams"}
        reviewed = data["heavy_end_cross_check"]["reviewed_four_three"]

        def share(path):
            with open(path, encoding="utf-8") as handle:
                rows = sorted((r for r in csv.DictReader(handle) if r["position"] == "DE"),
                              key=lambda r: int(r["depth"]))[:3]
            return sum(int(r["weight"]) >= 280 for r in rows) / max(1, len(rows))
        for group, folder in groups.items():
            keys = {Path(p).stem for p in glob.glob(str(folder / "*.csv"))}
            self.assertTrue(set(data["three_four"][group]) <= keys, group)
            for key in keys:
                heavy = share(folder / f"{key}.csv")
                if key in data["three_four"][group]:
                    self.assertGreaterEqual(heavy, 1 / 3 - 1e-9, key)
                elif heavy >= 2 / 3 - 1e-9:
                    self.assertIn(key, reviewed[group], f"{key}: heavy ends but not listed; review it")


class ThreeFourRuleTests(unittest.TestCase):
    def plan(self, rows, **kw):
        res = team_resource(rows)
        moves, _ = rc.plan_resource(res, {}, **kw)
        return pools(res, moves)

    def test_default_historic_rule_is_unchanged(self):
        got = self.plan(GIANTS_22)
        self.assertEqual(got["EDGE"][:2], ["Williams", "Ojulari"])         # the old bug, kept for unlisted teams
        self.assertIn("Thibodeaux", got["LB"])

    def test_three_four_rule_fields_the_rusher_at_edge_and_the_big_end_inside(self):
        got = self.plan(GIANTS_22, historic_scheme="3-4", historic_min_lb=3, historic_light_end=rc.LIGHT_END_POUNDS)
        self.assertEqual(got["EDGE"][0], "Thibodeaux")
        self.assertIn("Ojulari", got["EDGE"])                               # 250 lb "end" is an edge rusher
        self.assertEqual(set(got["EDGE"]), {"Thibodeaux", "Ojulari", "Ximines", "Fox"})
        self.assertEqual(got["DT"][0], "Lawrence")
        self.assertIn("Williams", got["DT"][:2])
        self.assertEqual(got["LB"][0], "McFadden")
        self.assertNotIn("Thibodeaux", got["LB"])

    def test_every_player_lands_in_exactly_one_pool(self):
        got = self.plan(GIANTS_22, historic_scheme="3-4", historic_min_lb=3, historic_light_end=rc.LIGHT_END_POUNDS)
        names = [n for v in got.values() for n in v]
        self.assertEqual(sorted(names), sorted(r[0] for r in GIANTS_22))

    def test_a_three_four_roster_short_of_inside_backers_keeps_three_lbs_and_three_edge(self):
        rows = [("A", DE, 0, 300), ("N", DT, 0, 330),
                ("O1", OLB, 0, 255), ("O2", OLB, 1, 250), ("O3", OLB, 2, 250), ("O4", OLB, 3, 245), ("O5", OLB, 4, 240),
                ("I1", ILB, 0, 240), ("I2", ILB, 1, 235)]
        got = self.plan(rows, historic_scheme="3-4", historic_min_lb=3)
        self.assertEqual(len(got["LB"]), 3)
        self.assertEqual(got["LB"][2], "O5")                                # the lowest-ranked outside backer
        self.assertEqual(len(got["EDGE"]), 4)
        # no top-up when the pool is already three deep, or when it would leave fewer than three EDGE
        full = self.plan(GIANTS_22, historic_scheme="3-4", historic_min_lb=3)
        self.assertNotIn("Fox", full["LB"])
        thin = self.plan([r for r in rows if r[0] not in ("O4", "O5")], historic_scheme="3-4", historic_min_lb=3)
        self.assertEqual(len(thin["EDGE"]), 3)
        self.assertEqual(len(thin["LB"]), 2)

    def test_unknown_scheme_is_refused(self):
        with self.assertRaises(rc.ReclassifyError):
            rc.plan_resource(team_resource(GIANTS_22), {}, historic_scheme="5-2")


class PreventTests(unittest.TestCase):
    def test_prevent_slot_zero_is_never_edge_for_any_retail_shape(self):
        shapes = (
            [pr.make_code(pr.KIND_OLB, 0), pr.make_code(pr.KIND_DE, 1), pr.make_code(pr.KIND_DE, 0), pr.make_code(pr.KIND_DT, 0)],
            [pr.make_code(pr.KIND_ILB, 1), pr.make_code(pr.KIND_DE, 1), pr.make_code(pr.KIND_DE, 0), pr.make_code(pr.KIND_DT, 1)],
        )
        for front in shapes:
            codes = front + [pr.make_code(k, v) for k, v in ((17, 1), (18, 2), (16, 1), (16, 0), (17, 0), (18, 1), (18, 0))]
            new, rule = pr.recode_codes(codes, 0x10)
            self.assertEqual(rule, "prevent")
            self.assertEqual(new[0] & 31, pr.KIND_ILB)
            self.assertEqual([c & 31 for c in new[1:4]], [pr.KIND_DE, pr.KIND_DE, pr.KIND_DT])


if __name__ == "__main__":
    unittest.main()
