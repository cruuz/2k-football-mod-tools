"""b77 / a5: what each 25th Anniversary side wore, and the kit this build gives it (period-correct uniforms).

Noah (10/8 evening): "in 25th mode, in brady superbowls patriots need old jerseys, like giants would have grey pants, we need
uniforms selected for 2005-2020 and stuff with variations for teams so these scenarios make more sense, also super bowl branding
and stuff relative to the season". These tests cover the a5 data in data/nfl2k5_moment_uniform_eras.json (the worn uniforms read
from the Gridiron Uniform Database per-game graphics, the designated home team, the sourced R0 overrides, the fit of every side)
and the era kit plan in data/nfl2k5_moment_era_kit_plan.json, over all 26 authored moments (52 sides) and, for the 25 retail
moments, the seasons in which the retail 2004 look is used. Retail free (no disc).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tools/b77"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import a1_uniforms as uni  # noqa: E402

PLAN = "data/nfl2k5_moment_era_kit_plan.json"
SLOTS = "data/nfl2k5_uniform_slots_2026.json"
MENU_RUN = Path("/home/noah/Desktop/2K5-8 Editors/b77_session/reports/a1_menu_v05_repaired.json")


def side_key(entry):
    return entry["moment"], entry["side"]


class WornDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eras = uni.load(ROOT, uni.ERAS)
        cls.moments = uni.load(ROOT, uni.SPEC)["moments"]
        cls.worn = {side_key(w): w for w in cls.eras["a5_worn"]}
        cls.decisions = {side_key(d): d for d in cls.eras["decisions"]}
        cls.plan = uni.load(ROOT, PLAN)
        cls.slots = uni.load(ROOT, SLOTS)["teams"]

    def test_the_compiled_data_is_consistent(self):
        self.assertEqual(uni.check(ROOT), [])

    def test_all_26_games_and_52_sides_are_sourced_from_a_dated_graphic(self):
        self.assertEqual(len(self.moments), 26)
        self.assertEqual(set(self.worn), {(m["id"], side) for m in self.moments for side in ("away", "home")})
        for key, w in self.worn.items():
            self.assertTrue(w["gud_page"].startswith("http://www.gridiron-uniforms.com/GUD/controller/"), key)
            self.assertIn(f"year={w['team_key'].rsplit('_', 1)[1]}", w["gud_page"], key)
            self.assertRegex(w["gud_graphic"], r"^https://www\.gridiron-uniforms\.com/GUD/images/singles/.+\.(png|gif)$", key)
            for field in ("jersey", "pants", "socks", "helmet", "note"):
                self.assertTrue(w[field].strip(), (key, field))
            self.assertIn(w["confidence"], ("high", "medium"), key)
            self.assertIn("viewed by the lead", w["basis"])

    def test_the_designated_home_team_is_the_moments_home_side_in_all_26_games(self):
        for (moment, side), w in self.worn.items():
            self.assertEqual(w["designated_home"], side == "home", (moment, side))

    def test_the_colours_a_role_gives_it_and_the_sides_that_differ(self):
        """The engine gives the home side its home kit file and the away side its road kit file (white). Sides whose worn
        jersey is the other colour: Super Bowl LII (the home Patriots wore white, the visiting Eagles green) and the Unc Bowl
        (the Bengals white at home, the visiting Steelers black). The Bengals' White Bengal (style 5, built) has the white set
        in both kits, and a5k supplies the black Steelers kit (G4), so both Unc Bowl sides select their worn set."""
        odd = sorted(k for k, w in self.worn.items()
                     if (k[1] == "home" and w["jersey"].startswith("white")) or (k[1] == "away" and not w["jersey"].startswith("white")))
        self.assertEqual(odd, [("philly_special", "away"), ("philly_special", "home"), ("unc_bowl", "away"), ("unc_bowl", "home")])
        self.assertEqual(self.decisions[("unc_bowl", "home")]["v06_kit"], 5)
        fits = {side_key(f): f for f in self.eras["a5_fit"]}
        self.assertEqual({k: fits[k]["era_kit"] for k in odd},
                         {("philly_special", "away"): "G1b", ("philly_special", "home"): "G1",
                          ("unc_bowl", "away"): "G4", ("unc_bowl", "home"): "G4"})

    def test_brady_patriots_and_the_giants_wear_their_period_kit(self):
        """Noah's two examples: every Patriots side in the moments (2001-2017) is the retail 2004 look (the 2000-2019 navy and
        silver design), never the 2026 kit; every Giants side (2007, 2010, 2011) is the retail 2004 look (gray pants)."""
        seen = set()
        for m in self.moments:
            for side in ("away", "home"):
                selector, season = uni.franchise_of(m[side])
                if selector in ("patriots", "giants"):
                    seen.add((selector, season))
                    expected = 11 if (m['id'], side) == ('philly_special', 'home') else 0
                    self.assertEqual(m["kits"][side], expected, f"{m['id']} {side}: {selector} {season}")
                    self.assertIn(self.decisions[(m["id"], side)]["rule"], ("R0", "R3"))
        self.assertEqual({s for s in seen if s[0] == "patriots"},
                         {("patriots", y) for y in (2001, 2003, 2007, 2011, 2014, 2016, 2017)})
        self.assertEqual({s for s in seen if s[0] == "giants"}, {("giants", 2007), ("giants", 2010), ("giants", 2011)})

    def test_overrides_are_sourced_and_name_a_kit_that_exists(self):
        overrides = self.eras["overrides"]
        self.assertEqual(sorted(side_key(o) for o in overrides), sorted(k for k, d in self.decisions.items() if d["rule"] == "R0"))
        for o in overrides:
            key = side_key(o)
            self.assertTrue(o["reason"].startswith("worn:"), key)
            self.assertTrue(o["sources"] and all(s.startswith("http") for s in o["sources"]), key)
            self.assertGreaterEqual(len(o["sources"]), 1)
            self.assertIn(o["sources"][0], self.worn[key]["gud_page"])
            if isinstance(o["kit"], int):
                selector = uni.franchise_of(self.worn[key]["team_key"])[0]
                franchise = self.eras["franchises"][selector]
                era = {i for i, _a, _b in franchise["retail_era_sets"]}
                built = {a["style"] for a in self.slots[franchise["abbreviation"]].get("assignments", [])
                         if a["status"] in ("built", "shipped")}
                built |= {r['style'] for r in uni.load(ROOT, 'data/nfl2k5_moment_era_kits.json')['items']
                          if r['team'] == franchise['abbreviation']}
                self.assertTrue(o["kit"] in era or o["kit"] in built, f"{key}: style {o['kit']} is neither a retail era set nor a built alternate")
            else:
                self.assertEqual(o["kit"], "retail_current")

    def test_every_side_has_a_fit_and_every_gap_is_planned(self):
        fits = {side_key(f): f for f in self.eras["a5_fit"]}
        self.assertEqual(set(fits), set(self.worn))
        planned = {item["id"]: item for item in self.plan["items"]}
        self.assertFalse(any(f['fit'] == 'gap' for f in fits.values()))
        gaps = {k: f["era_kit"] for k, f in fits.items() if f.get('era_kit')}
        self.assertEqual(len(gaps), 8)
        self.assertEqual(sorted(gaps.values()), ["G1", "G1b", "G2", "G2", "G3", "G3", "G4", "G4"])
        for key, gap in gaps.items():
            self.assertIn(gap, planned)
            self.assertIn(f"{key[0]} {key[1]}", planned[gap]["moments"])
        for item in planned.values():
            for ref in item["moments"]:
                moment, side = ref.split()
                self.assertIn((moment, side), self.worn, ref)
        self.assertTrue(all(f["fit"] in ("exact", "close", "gap") for f in fits.values()))

    def test_plan_targets_were_unowned_before_the_approved_trades(self):
        """Each plan item names one free style of its franchise: not style 0, the spare or a style an a5 moment selected before these approved trades,
        not an alternate the u3 jobs built, and different from every other item's target of the same team."""
        franchise_of_code = {f["abbreviation"]: f for f in self.eras["franchises"].values()}
        used = {}
        for m in self.moments:
            for side in ("away", "home"):
                selector, _season = uni.franchise_of(m[side])
                abbr = self.eras["franchises"][selector]["abbreviation"]
                d = self.decisions[(m["id"], side)]
                used.setdefault(abbr, set()).add(d["a5_kit"])
        targets = set()
        for item in self.plan["items"]:
            abbr = item["team"]
            style = int(re.search(r"style (\d+)", item["target_slot"]).group(1))
            self.assertNotEqual(style, 0)
            self.assertNotIn(style, used.get(abbr, set()), item["id"])
            self.assertNotEqual(style, franchise_of_code[abbr]["retail_spare_style_v05"], item["id"])
            built = {a["style"] for a in self.slots[abbr].get("assignments", [])}
            self.assertNotIn(style, built, f"{item['id']}: the slot belongs to a u3 alternate")
            self.assertNotIn((abbr, style), targets, item["id"])
            targets.add((abbr, style))
            self.assertIn(item["effort"], ("S", "M", "L"))
            self.assertTrue(item["photo_sources"] and item["nearest_kit"] and item["method"])


@unittest.skipUnless(MENU_RUN.is_file(), "the a1 menu run is a private session report")
class RetailRowTests(unittest.TestCase):
    def test_retail_rows_21_to_25_use_the_2004_look_only_inside_its_years(self):
        """The 25 retail moments keep their retail kits (the a3 repair never touches rows 1 to 25). Rows 21 to 25 (1997-2003)
        draw the franchise's spare style = the retail 2004 look; that look must have been worn in the game's season."""
        eras = uni.load(ROOT, uni.ERAS)
        spare = {f["abbreviation"]: f for f in eras["franchises"].values()}
        names = {"Packers": "GB", "Broncos": "DEN", "Titans": "TEN", "Patriots": "NE", "Giants": "NYG", "49ers": "SF", "Eagles": "PHI"}
        seasons = {21: 1997, 22: 1999, 23: 2001, 24: 2002, 25: 2003}
        rows = {r["physical_row"]: r for r in json.loads(MENU_RUN.read_text())["rows"]}
        checked = 0
        for row, season in seasons.items():
            for side in ("away", "home"):
                team, style = rows[row]["helmets"][side]
                if team not in names:
                    continue
                f = spare[names[team]]
                if style == f["retail_spare_style_v05"]:
                    through = f["design_2004_through_home" if side == "home" else "design_2004_through_road"]
                    self.assertTrue(f["design_2004_from"] <= season <= through, f"row {row} {side} {team} {season}")
                    checked += 1
        self.assertGreaterEqual(checked, 8)


if __name__ == "__main__":
    unittest.main()
