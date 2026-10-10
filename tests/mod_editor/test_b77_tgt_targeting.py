"""Target policy invariants and unmodified native CPU component controls."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pb.v2 import targeting
from pb.research.targets_2026 import aggregate, norm
from mod_editor.core import nfl2k5_offense_concepts as oc


class TargetingTests(unittest.TestCase):
    def test_season_filter_and_share_denominator_inputs(self):
        base = dict(season="2026", season_type="REG", week="1", game_id="g", play_id="1",
                    game_date="2026-09-13", play_type="pass", pass_attempt="1", two_point_attempt="0",
                    receiver_player_id="p", receiver_player_name="A.Player", posteam="LV")
        rows = [base, dict(base, play_id="2", receiver_player_id="q")]
        for i, change in enumerate((dict(season="2025"), dict(season_type="POST"), dict(week="0"),
                                  dict(play_type="no_play"), dict(two_point_attempt="1"),
                                  dict(receiver_player_id=""), dict(pass_attempt="0")), 3):
            rows.append(dict(base, play_id=str(i), **change))
        counts, _, coverage = aggregate(rows)
        self.assertEqual(dict(counts["OAK"]), {"p": 1, "q": 1})
        self.assertEqual(coverage["weeks"], [1])
        with self.assertRaises(ValueError):
            aggregate([base, base])
        self.assertEqual(norm("Mike Washington Jr."), norm("Mike Washington"))

    def test_all_32_sources_totals_and_depth_join(self):
        data = targeting.target_data()
        self.assertEqual(data["coverage"]["weeks"], [1, 2, 3, 4])
        for team in data["teams"].values():
            self.assertEqual(sum(p["targets"] for p in team["players"]), team["targets"])
            self.assertAlmostEqual(sum(p["share"] for p in team["players"]), 1)
            self.assertEqual(sum(team["role_targets"].values())+team["unmapped_targets"], team["targets"])
        self.assertEqual(data["teams"]["MIN"]["depth_chart"]["WR1"]["name"], "Justin Jefferson")
        self.assertGreater(data["teams"]["MIN"]["role_shares"]["TE1"], data["teams"]["MIN"]["role_shares"]["WR1"])
        self.assertGreater(data["teams"]["CIN"]["role_shares"]["WR2"], data["teams"]["CIN"]["role_shares"]["WR1"])

    def test_native_personnel_chains_select_the_claimed_build_roles(self):
        for row in targeting.target_data()["teams"].values():
            for spec in oc.FORMATIONS.values():
                expected = targeting.roles(spec)
                for slot, role in list(expected.items()):
                    if role not in row["depth_chart"]:
                        expected[slot] = "unresolved_" + role
                self.assertEqual(targeting.resolve_roles(spec.codes(), row["depth_chart"]), expected)

    def test_single_rank_chain_uses_the_full_ordinal_and_missing_pool_is_unresolved(self):
        chart = {"RB1": dict(rank=0, side=2), "RB2": dict(rank=1, side=0),
                 "RB3": dict(rank=2, side=1)}
        self.assertEqual(targeting.resolve_roles([oc.HB | (2 << 5)], chart), {0: "RB3"})
        self.assertEqual(targeting.resolve_roles([oc.FB], chart), {0: "unresolved_FB1"})

    def test_every_concept_preserves_geometry_protection_and_depth_tiers(self):
        changed = 0
        for spec in oc.FORMATIONS.values():
            for name in oc.CONCEPTS:
                try:
                    before = oc.design(name, spec.context())
                except oc.ConceptUnavailable:
                    continue
                snapshot = copy.deepcopy(before)
                after = targeting.apply(before, spec, "DAL")
                self.assertEqual(before, snapshot)
                self.assertEqual(after.chains[1:], before.chains[1:], (spec.name, name))
                self.assertCountEqual(after.reads, before.reads)
                self.assertEqual(len(after.chains[0]), len(before.chains[0]))
                for a, b in zip(after.chains[0], before.chains[0]):
                    if a[0] != 0x06:
                        self.assertEqual(a, b)
                    else:
                        self.assertEqual(a[1][0], b[1][0])
                        self.assertEqual(a[1][5], b[1][5])
                        self.assertEqual([s-5 for s in after.reads[:4]], [int(x) for x in a[1][1:5] if x])
                for old, new in zip(before.reads, after.reads):
                    self.assertEqual(targeting.direct_band(spec.context(), old, before.chains[old]),
                                     targeting.direct_band(spec.context(), new, after.chains[new]))
                self.assertEqual(targeting.apply(after, spec, "DAL"), after)
                changed += after.reads != before.reads
        self.assertGreater(changed, 50)

    def test_screens_gadgets_and_moving_pocket_retain_primary(self):
        for spec in oc.FORMATIONS.values():
            for name in ("RB Screen", "WR Slip Screen", "Bubble Screen", "TE Screen", "Flea Flicker", "PA Boot"):
                try:
                    design = oc.design(name, spec.context())
                except (oc.ConceptUnavailable, KeyError):
                    continue
                self.assertEqual(targeting.apply(design, spec, "MIN"), design)

    def test_zero_share_roles_are_never_promoted(self):
        spec = oc.FORMATIONS["Gun Doubles"]
        design = oc.design("Four Verticals", spec.context()) if "Four Verticals" in oc.CONCEPTS else oc.design("Verts", spec.context())
        slot_roles = targeting.roles(spec)
        sole = slot_roles[design.reads[-1]]
        result = targeting.apply(design, spec, "MIN", {sole: 1})
        for slot in design.reads:
            if slot_roles[slot] != sole:
                self.assertGreaterEqual(result.reads.index(slot), design.reads.index(slot))
        self.assertEqual(targeting.apply(design, spec, "MIN", {}), design)

    def test_zero_share_primary_yields_to_a_compatible_positive_share_read(self):
        spec = oc.FORMATIONS["Gun Doubles"]
        design = oc.design("Double Slants", spec.context())
        slot_roles = targeting.roles(spec)
        positive = design.reads[1]
        result = targeting.apply(design, spec, "IND", {slot_roles[positive]: 1})
        self.assertEqual(result.primary, positive)
        self.assertEqual([s for s in result.reads if s != positive],
                         [s for s in design.reads if s != positive])

    def test_higher_share_role_leads_and_equal_shares_keep_authored_order(self):
        spec = oc.FORMATIONS["Gun Doubles"]
        base = oc.design("Double Slants", spec.context())
        slot_roles = targeting.roles(spec)
        first, second = base.reads[:2]
        for high, low in ((first, second), (second, first)):
            shares = {slot_roles[high]: .9, slot_roles[low]: .1}
            self.assertEqual(targeting.apply(base, spec, "MIN", shares).primary, high)
        equal = {slot_roles[first]: .5, slot_roles[second]: .5}
        self.assertEqual(targeting.apply(base, spec, "MIN", equal).primary, first)

    def test_real_higher_share_reads_precede_lower_shares_in_each_compatible_band(self):
        spec = oc.FORMATIONS["Gun Doubles"]
        roles = targeting.roles(spec)
        for team in ("MIN", "CIN", "DAL", "OAK", "TEN"):
            shares = targeting.target_data()["teams"][team]["role_shares"]
            for name in ("Double Slants", "Four Verticals", "Mesh", "Slant Flat"):
                design = oc.design(name, spec.context())
                after = targeting.apply(design, spec, team)
                bands = {}
                for slot in after.reads[:4]:
                    band = targeting.direct_band(spec.context(), slot, after.chains[slot])
                    if band is not None:bands.setdefault(band, []).append(shares.get(roles[slot], 0))
                for values in bands.values():
                    self.assertEqual(values, sorted(values, reverse=True), (team, name))

    def test_read_normalization_retains_distinct_named_team_plays(self):
        from pb.v2.build import build_designs
        core = json.loads((ROOT / "pb/v2/core.json").read_text())
        for team, formation, name in (
            ("KC", "Gun Doubles", "KC Double Slants"),
            ("NYG", "Gun Doubles", "NYG Slant Flat"),
            ("SD", "Gun Doubles", "SD Slant Flat"),
            ("SD", "Gun Doubles", "SD Double Slants"),
            ("SEA", "Gun Doubles", "SEA Slant Flat"),
            ("NO", "Gun Doubles", "NO Slant Flat"),
        ):
            package = json.loads((ROOT / f"pb/v2/teams/{team}.json").read_text())
            signature = next(s for s in package["signature"] if s["name"] == name)
            formation = signature["formation"]
            rows = build_designs([formation], core, package)[formation]
            self.assertIn(name, [design.name for _, design, _ in rows], team)

    def test_menu_fit_keeps_a_named_play_when_a_later_formation_shares_its_chain(self):
        from pb.v2.build import chain_key, fit_menus
        ordinary = oc.design("Double Slants", oc.FORMATIONS["Gun Doubles"].context())
        named = copy.deepcopy(ordinary)
        named.name = "KC Double Slants"
        key = ("11", ordinary.header, chain_key(ordinary.chains))
        candidates = {"Gun Doubles": [(key, named, True)], "Gun Trips": [(key, ordinary, False)]}
        menus, designs = fit_menus(candidates, 1, dict(menu_min=1, menu_max=3),
                                   dict(team="KC", signature=[dict(name=named.name)]))
        self.assertEqual(designs[key].name, named.name)
        self.assertEqual(menus, {"Gun Doubles": [key], "Gun Trips": [key]})


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn
        except ImportError:
            raise unittest.SkipTest("needs the existing Unicorn native harness dependency")

    def test_paired_openness_ignores_renames_indices_and_read_permutations(self):
        from tools.b77.tgt_target_probe import openness_seed
        from mod_editor.core import nfl2k5_playbook_lint as lint
        from mod_editor.core import nfl2k5_play_codec as codec
        spec = oc.FORMATIONS["Gun Doubles"]
        design = oc.design("Double Slants", spec.context())
        view = lint.PlayView(0, "A", 0, "First", 0, spec.positions_cm(), spec.codes(),
                             [codec.encode_chain(c) for c in design.chains])
        seed = openness_seed("MIN", view)
        changed = copy.deepcopy(view)
        changed.formation, changed.play = 9, 200
        changed.formation_name, changed.play_name = "renamed formation", "renamed play"
        node = next(n for n in changed.chains[0] if n.op == 0x06)
        node.operands[1:5] = reversed(node.operands[1:5])
        self.assertEqual(openness_seed("MIN", changed), seed)
        node.operands[5] += .1
        self.assertNotEqual(openness_seed("MIN", changed), seed)

    def test_native_order_cadence_and_openness_controls(self):
        from tools.b77.tgt_target_probe import proof
        from tools.nfl2k5_back_throws_replay import DEFAULT_XBE
        if not DEFAULT_XBE.is_file():
            self.skipTest("needs the retail default.xbe")
        result = proof(DEFAULT_XBE.read_bytes())
        self.assertEqual(result["native_helpers_substituted"], [])
        self.assertEqual(result["rows"][0]["native_cycle"], [0, 1, 2, 3, 4, 0])
        self.assertEqual(result["rows"][1]["only_first_evaluated_target"], 9)


if __name__ == "__main__":
    unittest.main()
