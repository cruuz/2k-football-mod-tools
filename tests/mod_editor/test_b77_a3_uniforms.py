"""b77 / a3 + a5: every 25th Anniversary moment selects a sourced uniform style (modern by default, period kit by design).

Noah (10/8, the Unc Bowl): the newer moments showed 2004 stock jerseys. A moment side selects a style of its franchise
(SITU kit index); in v0.5 every authored "kit 0" was moved to the franchise's spare style (the retail 2004 look). These
tests cover the sourced eras data and its rules, the compile into the moment data, the historic styles step leaving
"modern" sides on style 0, and the native repair of the v0.5 situation.iff, over all 51 moments. a5 (Noah 10/8: "Brady Super
Bowl Patriots need old jerseys, Giants grey pants"): R3 no longer stops at the Reebok/Nike template year, and sourced R0
overrides pick the closest kit for what each side wore (tests/mod_editor/test_b77_a5_uniforms.py covers that data).

  * EraRuleTests / EraDataTests (retail free): the rules, the data, and "a side on the retail 2004 look is R3 inside the
    years that look was worn (any template) or a sourced R0 override" over the 26 authored moments.
  * V05DiscTests (the v0.5 disc): the shipped kits are what the data records; the repair moves 35 sides and nothing else
    (the a1x output moves 17 more); all 51 moments are checked (rows 1 to 25 are retail seasons up to 2004 and unchanged);
    the historic styles plan on the repaired file keeps the modern sides at 0; scope, idempotence, refusals.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tools/b77"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import a1_uniforms as uni  # noqa: E402
import a1_uniforms_repair as repair  # noqa: E402
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_historic_styles as hs  # noqa: E402

V05_DISC = Path(os.environ.get("B77_V05_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso"))
RETAIL_ISO = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")


def eras():
    return uni.load(ROOT, uni.ERAS)


def moments():
    return uni.load(ROOT, uni.SPEC)["moments"]


class EraRuleTests(unittest.TestCase):
    """The four rules on a synthetic franchise."""

    def setUp(self):
        self.eras = dict(rule=dict(retail_kit_template_through=2011), franchises={"x": dict(
            design_2026_since=2013, retail_era_sets=[[1, 1998, 2003], [2, 1990, 1997]], retail_spare_style_v05=7,
            design_2004_from=1996, design_2004_through_home=2011, design_2004_through_road=2004)})

    def test_rules_in_order(self):
        d = lambda season, role="home": uni.decide(self.eras, "x", season, role)[:2]
        self.assertEqual(d(2013), (uni.MODERN, "R1"))          # the current design began in 2013
        self.assertEqual(d(2025), (uni.MODERN, "R1"))
        self.assertEqual(d(1999), (1, "R2"))                   # a retail period set covers it
        self.assertEqual(d(1992), (2, "R2"))
        self.assertEqual(d(2008), ("retail_current", "R3"))    # the 2004 look was still worn, Reebok template
        self.assertEqual(d(2011), ("retail_current", "R3"))
        self.assertEqual(d(2012), (uni.MODERN, "R4"))          # the 2004 look's years (home) ended in 2011
        self.assertEqual(d(2008, "away"), (uni.MODERN, "R4"))  # the road kit changed after 2004
        self.assertEqual(d(1994, "away"), (2, "R2"))

    def test_r3_has_no_template_cutoff(self):
        """a5: the Reebok/Nike year does not decide; the years the 2004 look was worn do (Patriots 2000-2019)."""
        eras = dict(self.eras)
        eras["franchises"] = {"x": dict(self.eras["franchises"]["x"], design_2004_through_home=2019, design_2004_through_road=2019,
                                         design_2026_since=2020)}
        for season in (2012, 2014, 2017, 2019):
            self.assertEqual(uni.decide(eras, "x", season, "home")[:2], ("retail_current", "R3"), season)
            self.assertEqual(uni.decide(eras, "x", season, "away")[:2], ("retail_current", "R3"), season)
        self.assertEqual(uni.decide(eras, "x", 2020, "home")[:2], (uni.MODERN, "R1"))
        self.assertIn("Nike", uni.decide(eras, "x", 2016, "home")[2])

    def test_r0_override_wins(self):
        eras = dict(self.eras, overrides=[dict(moment="m", side="away", kit=10, reason="worn", sources=["u"])])
        self.assertEqual(uni.decide(eras, "x", 2013, "away", "m"), (10, "R0", "worn"))
        self.assertEqual(uni.decide(eras, "x", 2013, "home", "m")[1], "R1")      # only the named side
        self.assertEqual(uni.decide(eras, "x", 2013, "away", "other")[1], "R1")

    def test_decision_values(self):
        self.assertEqual(uni.kit_value("retail_current"), 0)
        self.assertEqual(uni.kit_value(uni.MODERN), "modern")
        self.assertEqual(uni.kit_value(3), 3)
        self.assertEqual(uni.situ_value(uni.MODERN, "x", self.eras), 0)
        self.assertEqual(uni.situ_value("retail_current", "x", self.eras), 7)     # the spare the historic step writes
        self.assertEqual(uni.situ_value(2, "x", self.eras), 2)

    def test_modern_kit_index(self):
        self.assertEqual(mm.kit_index([(0, 0, 0)], "modern"), 0)
        self.assertEqual(mm.kit_index([(0, 0, 0), (3, 1990, 1991)], 3), 3)
        with self.assertRaises(mm.MoreMomentsError):
            mm.kit_index([(0, 0, 0)], 5)


class EraDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eras = eras()
        cls.moments = moments()

    def test_compiled_data_agrees_with_the_decisions(self):
        self.assertEqual(uni.check(ROOT), [])

    def test_every_franchise_is_sourced(self):
        used = {uni.franchise_of(m[side])[0] for m in self.moments for side in ("away", "home")}
        self.assertEqual(used, set(self.eras["franchises"]))
        for selector, f in self.eras["franchises"].items():
            self.assertTrue(f["sources"] and all(u.startswith("https://") for u in f["sources"]), selector)
            self.assertTrue(f["designs"], selector)
            self.assertIsInstance(f["retail_spare_style_v05"], int, selector)

    def test_all_52_sides_are_decided_and_recorded(self):
        decisions = self.eras["decisions"]
        self.assertEqual(len(decisions), 52)
        self.assertEqual({d["situ_row"] for d in decisions}, set(range(25, 51)))
        for d in decisions:
            self.assertIn(d["rule"], ("R0", "R1", "R2", "R3", "R4"))
            self.assertEqual(d["v06_kit"], uni.situ_value(d["kit"], uni.franchise_of(d["team_key"])[0], self.eras))

    def test_a_2004_kit_is_period_correct_or_a_sourced_override(self):
        """A side that keeps the retail 2004 look (kit 0 in the moment data) from 2010 on must be R3 (the season is inside the
        years that look was worn by that kit, whatever the template) or an R0 override; every other late side is style 0, an
        R0 override, or a retail era set that covers the season."""
        decisions = {(d["moment"], d["side"]): d for d in self.eras["decisions"]}
        for m in self.moments:
            for side in ("away", "home"):
                selector, season = uni.franchise_of(m[side])
                f = self.eras["franchises"][selector]
                kit = m["kits"][side]
                d = decisions[(m["id"], side)]
                if season >= 2010 and kit == 0:
                    if d["rule"] == "R3":
                        through = f["design_2004_through_home" if side == "home" else "design_2004_through_road"]
                        self.assertTrue(f["design_2004_from"] <= season <= through, f"{m['id']} {side}: not period-correct")
                    else:
                        self.assertEqual(d["rule"], "R0", f"{m['id']} {side}")
                if season > 2011 and kit != "modern":
                    self.assertIn(d["rule"], ("R0", "R3"), f"{m['id']} {side}: {season}")

    def test_old_throwback_stand_ins_are_gone(self):
        """Bills 4, 49ers 3 and Rams 4 were 'closest to' picks while style 0 was the 2004 look; an int style above 0 is only
        kept when a retail era row really covers the season (R2) or a sourced R0 override names the worn look."""
        decisions = {(d["moment"], d["side"]): d for d in self.eras["decisions"]}
        for m in self.moments:
            for side in ("away", "home"):
                kit = m["kits"][side]
                if isinstance(kit, int) and kit > 0:
                    selector, season = uni.franchise_of(m[side])
                    d = decisions[(m["id"], side)]
                    if d["rule"] == "R0":
                        self.assertTrue(d["reason"].startswith("worn:"), f"{m['id']} {side}")
                        continue
                    rows = {i: (a, b) for i, a, b in self.eras["franchises"][selector]["retail_era_sets"]}
                    self.assertTrue(rows[kit][0] <= season <= rows[kit][1], f"{m['id']} {side}")

    def test_unc_bowl_and_recent_moments(self):
        by = {m["id"]: m for m in self.moments}
        self.assertEqual(by["unc_bowl"]["kits"], {"away": 4, "home": 5})
        for m in self.moments:
            if int(m["date"][-4:]) >= 2021:
                for side in ("away", "home"):
                    if (m["id"], side) not in (("donald_fourth_down", "away"), ("unc_bowl", "away"), ("unc_bowl", "home")):
                        self.assertEqual(m["kits"][side], "modern", f"{m['id']} {side}")

    def test_the_spec_and_the_compiled_moments_agree(self):
        compiled = uni.load(ROOT, uni.MOMENTS)["moments"]
        self.assertEqual([(m["id"], m["kits"]) for m in compiled], [(m["id"], m["kits"]) for m in self.moments])

    def test_the_shipped_data_loads_and_marks_the_modern_sides(self):
        data = mm.Data.load()
        modern = mm.modern_sides(data)
        want = {(25 + i, side) for i, m in enumerate(self.moments) for side in ("away", "home") if m["kits"][side] == "modern"}
        self.assertEqual(modern, want)
        self.assertEqual(len(modern), 25)

    def test_worn_colours_are_recorded_with_their_basis(self):
        """Home/away colours as worn are text-sourced; the sides where the game's home/away set differs are listed."""
        sides = self.eras["sides"]
        self.assertEqual(len(sides), 52)
        for s in sides:
            self.assertIn("no photo checked", s["worn_basis"])
        mismatched = sorted((s["moment"], s["side"]) for s in sides
                            if (s["side"] == "home" and s["worn_in_game"].startswith("white"))
                            or (s["side"] == "away" and s["worn_in_game"].startswith("dark")))
        self.assertEqual(mismatched, [("philly_special", "away"), ("philly_special", "home")])   # Super Bowl LII: colours swapped


@unittest.skipUnless(V05_DISC.is_file() and RETAIL_ISO.is_file(), "the v0.5 disc and the retail disc are private inputs")
class V05DiscTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_music_archive as archive
        cls.eras = eras()
        cls.disc = archive.Disc(V05_DISC, descriptors=())
        cls.disc.__enter__()
        cls.target = hs.Target(cls.disc)
        cls.situ = cls.target.get(identity=hs.SITU_OUTER_ID)
        cls.main = cls.target.get(identity=hs.ROSTER_OUTER_ID)
        cls.new, cls.receipt = repair.transform(cls.situ, cls.eras)

    @classmethod
    def tearDownClass(cls):
        cls.disc.__exit__(None, None, None)

    def test_the_v05_file_is_the_one_the_repair_knows(self):
        self.assertEqual(repair.sha(self.situ), repair.V05_SITU_SHA256)
        self.assertEqual(len(self.situ), repair.V05_SITU_SIZE)

    def test_recorded_shipped_kits_are_what_the_disc_holds(self):
        kits = uni.read_situ_kits(self.situ)
        for d in self.eras["decisions"]:
            self.assertEqual(kits[(d["situ_row"], d["side"])], d["v05_kit"], d["moment"])

    def test_the_repair_moves_35_sides_and_nothing_else(self):
        self.assertEqual(len(self.receipt["changed"]), 35)
        before, after = uni.read_situ_kits(self.situ), uni.read_situ_kits(self.new)
        changed = {k for k in before if before[k] != after[k]}
        self.assertEqual(len(changed), 35)
        decided = {(d["situ_row"], d["side"]): d["v06_kit"] for d in self.eras["decisions"]}
        self.assertTrue(all(after[k] == decided[k] for k in changed))
        self.assertEqual({k: after[k] for k in changed if after[k] != 0},
                         {(35, "away"): 10, (47, "away"): 2, (34, "away"): 6, (37, "away"): 6,
                          (38, "away"): 1, (39, "away"): 1, (44, "away"): 14, (44, "home"): 11,
                          (50, "away"): 4, (50, "home"): 5})
        self.assertTrue(all(k[0] >= 25 for k in changed))
        diff = [i for i in range(len(self.situ)) if self.situ[i] != self.new[i]]
        declared = {c["offset"] + k for c in self.receipt["changed"] for k in range(4)}
        self.assertTrue(set(diff) <= declared)
        self.assertEqual(len(self.new), len(self.situ))
        self.assertTrue(self.receipt["outside_scope_identical"])

    def test_unc_bowl_selects_white_bengal_and_black_steelers(self):
        """The Bengals wore the all-white White Bengal (style 5, built) and the Steelers their black home set as the visitor.
        The engine gives the visiting Steelers their white kit, so selecting style 5 would put two white teams on the field:
        a5k now supplies the black Steelers away kit, so both worn sets are selected."""
        after = uni.read_situ_kits(self.new)
        self.assertEqual((after[(50, "away")], after[(50, "home")]), (4, 5))

    def test_all_51_moments_a_2004_kit_is_period_correct_or_an_override(self):
        """Over every SITU row of the repaired file: the club's season (SITU +0x1C/+0x20) and kit index. A side on the
        franchise's spare style (the retail 2004 look) from 2010 on must be a sourced R3 or R0 decision."""
        body = self.new[32:32 + struct.unpack_from("<I", self.new, 4)[0]]
        count = struct.unpack_from("<I", body, 64)[0]
        self.assertEqual(count, 51)
        kits = uni.read_situ_kits(self.new)
        spare_of = {f["asset_code"]: f["retail_spare_style_v05"] for f in self.eras["franchises"].values()}
        decisions = {(d["situ_row"], d["side"]): d for d in self.eras["decisions"]}
        seen = 0
        for row in range(count):
            at = 0x44 + row * 0x6C
            for side, year_at in (("away", 0x1C), ("home", 0x20)):
                season = struct.unpack_from("<I", body, at + year_at)[0]
                kit = kits[(row, side)]
                if row < 25:
                    self.assertLess(season, 2005, f"retail row {row + 1}")
                    continue
                seen += 1
                d = decisions[(row, side)]
                self.assertEqual(season, d["season"])
                if season >= 2010 and kit != 0:
                    self.assertIn(d["rule"], ("R0", "R3"), f"row {row + 1} {side}: kit {kit} in {season}")
                    if d["rule"] == "R3":
                        selector = d["team_key"].rsplit("_", 1)[0]
                        self.assertEqual(kit, spare_of[self.eras["franchises"][selector]["asset_code"]])
                if season > 2011 and kit != 0:
                    self.assertIn(d["rule"], ("R0", "R3"), f"row {row + 1} {side}: {season}")
        self.assertEqual(seen, 52)

    def test_retail_rows_and_authored_rows_outside_the_decisions_are_untouched(self):
        before, after = uni.read_situ_kits(self.situ), uni.read_situ_kits(self.new)
        for key in before:
            if key[0] < 25:
                self.assertEqual(before[key], after[key], key)

    def test_the_historic_styles_step_keeps_modern_sides_on_style_0(self):
        """plan_spares on the repaired file: no franchise is 'affected' (the modern sides' kit 0 is not a retail style-0 user)
        and compile_spares writes no kit into them. Without the exemption the same file would be re-spared."""
        outer = self.target.outer(identity=hs.SITU_OUTER_ID)
        new = self.new

        class Repaired(hs.Target):
            def get(self, name=None, *, identity=None):
                return new if identity == hs.SITU_OUTER_ID else super().get(name, identity=identity)

        with hs.Source(RETAIL_ISO) as src:
            target = Repaired(self.disc)
            plan = hs.plan_spares(target, src)
            self.assertEqual(len(plan["modern"]), 25)
            self.assertEqual(plan["affected"], {})
            edits, appended = hs.compile_spares(target, src, plan)
            self.assertNotIn(outer, edits)                                   # the situation file is not rewritten
            blind = hs.plan_spares(target, src, modern=set())
            self.assertTrue(blind["affected"], "without the exemption the 25 sides would count as retail style-0 users")

    def test_the_a1x_output_upgrades_to_the_same_file(self):
        """The first version of this repair (a1x) moved 42 sides to style 0; a stacked file that already holds it gets the a5
        selection on top (17 sides change) and ends byte-identical to the route from v0.5."""
        a1x = bytearray(self.situ)
        for r, side, _before, _after, at, kit in repair.table(self.eras):
            struct.pack_into("<I", a1x, at, kit)
        a1x = bytes(a1x)
        self.assertEqual(repair.sha(a1x), repair.A1X_SITU_SHA256)         # the file a1x shipped as its receipt
        up, receipt = repair.transform(a1x, self.eras)
        self.assertEqual(up, self.new)
        self.assertEqual(receipt["state_before"], "a1x")
        self.assertEqual(len(receipt["changed"]), 17)

    def test_idempotent_and_replays_as_applied(self):
        again, receipt = repair.transform(self.new, self.eras)
        self.assertEqual(again, self.new)
        self.assertEqual(receipt["state_before"], "applied")
        self.assertEqual(receipt["bytes_changed"], 0)

    def test_refusals(self):
        broken = bytearray(self.situ)
        at = repair.table(self.eras)[2][4]                                  # a side the repair changes
        struct.pack_into("<I", broken, at, 13)
        with self.assertRaises(repair.UniformRepairError):
            repair.transform(bytes(broken), self.eras)                       # neither v0.5 nor new on every side
        mixed = bytearray(self.new)
        struct.pack_into("<I", mixed, at, 9)
        with self.assertRaises(repair.UniformRepairError):
            repair.transform(bytes(mixed), self.eras)

    def test_command_line_hash_check_and_output_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "in").mkdir()
            (tmp / "in" / repair.NAME).write_bytes(self.situ)
            self.assertEqual(repair.main(["--input-dir", str(tmp / "in"), "--output-dir", str(tmp / "out")]), 0)
            self.assertEqual((tmp / "out" / repair.NAME).read_bytes(), self.new)
            (tmp / "foreign").mkdir()
            (tmp / "foreign" / repair.NAME).write_bytes(self.situ[:-1] + b"\x01")
            with self.assertRaises(repair.UniformRepairError):
                repair.main(["--input-dir", str(tmp / "foreign"), "--output-dir", str(tmp / "out2")])
            (tmp / "out3").mkdir()
            (tmp / "out3" / repair.NAME).write_bytes(b"other")
            with self.assertRaises(repair.UniformRepairError):
                repair.main(["--input-dir", str(tmp / "in"), "--output-dir", str(tmp / "out3")])


if __name__ == "__main__":
    unittest.main()
