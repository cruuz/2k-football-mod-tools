"""Playbook execution linter and the Studio's compile-time repair rules (b77 job p13)."""
from pathlib import Path
import contextlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_lint as lint
from mod_editor.core import nfl2k5_playbook_pack as packs

YD = codec.YD_CM
RUN_FLAGS, PASS_FLAGS = 0x840E, 0x620E
CODES_11 = (0, 5, 37, 6, 7, 39, 8, 41, 73, 9, 10)          # QB T T2 C G G2 TE WR2 WR3 WR HB
LINE = [(302, 0), (-302, 0), (0, 0), (155, 0), (-155, 0)]


def positions(qb_z, skills):
    return [(0, round(qb_z * YD))] + LINE + [(round(x * YD), round(z * YD)) for x, z in skills]


def view(pos, chains, flags, codes=CODES_11, name="play"):
    nodes = [list(codec.encode_chain(c)) for c in chains]
    return lint.PlayView(0, "formation", 0, name, flags, [tuple(map(float, p)) for p in pos], list(codes), nodes)


def validate(flags, chains):
    assignments = [(len(c), [n.to_bytes() for n in codec.encode_chain(c)]) for c in chains]
    for s in range(11):
        assignments[s] = (codec.build_descriptor(flags, assignments, s, 0), assignments[s][1])
    return codec.validate_play(flags, assignments)


GUN_WIDE = positions(-5, [(-5, 0), (18, 0), (12, -1.5), (-18, -1.5), (2.5, -5)])
UC_SLOT = positions(-2, [(-5, 0), (-15, 0), (9, -2.4), (15, 0), (0, -7)])


class HandoffRules(unittest.TestCase):
    def test_far_end_around_is_flagged_and_retargeted_inside_the_envelope(self):
        chains = lint.end_around_template(GUN_WIDE, CODES_11, 9)          # WR 18 yd wide
        self.assertIsNone(validate(RUN_FLAGS, chains))
        report = lint.lint_views([view(GUN_WIDE, chains, RUN_FLAGS)], "synthetic")
        self.assertEqual([f.code for f in report.findings], ["HANDOFF_FAR"])
        self.assertGreater(report.findings[0].data["separation_yd"], 18)
        fixed, receipts = lint.normalize_offense_play(GUN_WIDE, CODES_11, chains)
        self.assertEqual(receipts[0]["status"], "retargeted")
        self.assertEqual((receipts[0]["old_runner"], receipts[0]["new_runner"]), (9, 6))   # the TE, 7.1 yd away
        self.assertLessEqual(receipts[0]["new_separation_yd"], lint.END_AROUND_MAX_SEPARATION_YD)
        self.assertIsNone(validate(RUN_FLAGS, fixed))
        self.assertEqual(lint.lint_views([view(GUN_WIDE, fixed, RUN_FLAGS)], "fixed").findings, [])
        # The run now goes away from the TE's side; every blocker follows the new direction.
        self.assertEqual(int(fixed[0][-1][1][0]), 6)
        again, more = lint.normalize_offense_play(GUN_WIDE, CODES_11, fixed)
        self.assertIsNone(again)

    def test_retail_slot_reverse_geometry_is_inside_the_envelope(self):
        chains = lint.end_around_template(UC_SLOT, CODES_11, 8)           # WR 9 yd out, 2.4 yd back
        report = lint.lint_views([view(UC_SLOT, chains, RUN_FLAGS)], "retail-like")
        self.assertEqual(report.findings, [])
        self.assertEqual(lint.normalize_offense_play(UC_SLOT, CODES_11, chains)[0], None)

    def test_unrecognised_play_is_never_rewritten(self):
        chains = lint.end_around_template(GUN_WIDE, CODES_11, 9)
        chains[1] = [lib.start(3), lib.leg(0, 0, 1, turn=2)]              # hand-edited tackle
        fixed, receipts = lint.normalize_offense_play(GUN_WIDE, CODES_11, chains)
        self.assertIsNone(fixed)
        self.assertEqual(receipts, [])
        self.assertEqual([f.code for f in lint.lint_views([view(GUN_WIDE, chains, RUN_FLAGS)], "x").findings],
                         ["HANDOFF_FAR"])


class ScreenRules(unittest.TestCase):
    def test_under_center_screen_drops_nine_yards(self):
        chains = lint.rb_screen_template(UC_SLOT, CODES_11, 1, 7.0)
        codes = [f.code for f in lint.lint_views([view(UC_SLOT, chains, PASS_FLAGS)], "uc").findings]
        self.assertIn("SCREEN_DEPTH_MARGIN", codes)
        fixed, receipts = lint.normalize_offense_play(UC_SLOT, CODES_11, chains)
        screen = next(r for r in receipts if r["rule"] == "rb_screen")
        self.assertEqual((screen["old_drop_yd"], screen["new_drop_yd"]), (7.0, 9.0))
        self.assertEqual(screen["new_side"], 1)                             # centred back keeps the side
        self.assertIsNone(validate(PASS_FLAGS, fixed))
        self.assertEqual(lint.lint_views([view(UC_SLOT, fixed, PASS_FLAGS)], "fixed").findings, [])
        self.assertIsNone(lint.normalize_offense_play(UC_SLOT, CODES_11, fixed)[0])

    def test_offset_back_screen_turns_to_his_own_side(self):
        chains = lint.rb_screen_template(GUN_WIDE, CODES_11, -1, 7.0)    # back at +2.5, screen left
        codes = [f.code for f in lint.lint_views([view(GUN_WIDE, chains, PASS_FLAGS)], "gun").findings]
        self.assertEqual(codes, ["SCREEN_SIDE_CROSS"])
        fixed, receipts = lint.normalize_offense_play(GUN_WIDE, CODES_11, chains)
        screen = next(r for r in receipts if r["rule"] == "rb_screen")
        self.assertEqual((screen["new_side"], screen["new_drop_yd"]), (1, 7.0))
        released = [s for s in range(1, 6) if any(n[0] == 0x18 for n in fixed[s])]
        self.assertEqual(len(released), 3)
        self.assertTrue(all(fixed[s][2][1][1] > 0 for s in released))      # every release goes right
        self.assertEqual(lint.lint_views([view(GUN_WIDE, fixed, PASS_FLAGS)], "fixed").findings, [])

    def test_screen_drop_never_hits_retail_ten(self):
        for depth in range(-1000, -50, 7):
            drop = lint.screen_drop_yd(depth, 7.0)
            self.assertNotAlmostEqual(drop, 10.0, places=4)
            self.assertGreaterEqual(-depth / YD - (-drop) + 1e-6, lint.SCREEN_MARGIN_YD)
        self.assertEqual(lint.screen_drop_yd(-640.08, 7.0), 9.0)
        self.assertEqual(lint.screen_drop_yd(-457.2, 7.0), 7.0)


class CheckdownRules(unittest.TestCase):
    def pass_play(self, back_route):
        chains = [lib.qb_pass_chain(True)] + [lib.center_chain(0, "pass", False) if s == 3 else
                                              lib.blocker_chain("pass", 0, False) for s in range(1, 6)]
        chains += [lib.route_chain("Go", 20, 1) for _ in range(4)] + [back_route]
        return chains

    def test_gun_flat_at_qb_depth_gains_depth_first(self):
        chains = self.pass_play(lib.route_chain("Flat", 5, 1))
        report = lint.lint_views([view(GUN_WIDE, chains, PASS_FLAGS)], "gun")
        self.assertEqual([f.code for f in report.findings], ["CHECKDOWN_BACKWARD"])
        self.assertEqual(report.findings[0].data["margin_yd"], 0.0)
        fixed, receipts = lint.normalize_offense_play(GUN_WIDE, CODES_11, chains)
        self.assertEqual(receipts[0]["rule"], "back_routes")
        self.assertEqual([n[0] for n in fixed[10]], [0x01, 0x12, 0x12])
        self.assertEqual([int(n[1][0]) for n in fixed[10][1:]], [0, 5])
        self.assertIsNone(validate(PASS_FLAGS, fixed))
        self.assertEqual(lint.lint_views([view(GUN_WIDE, fixed, PASS_FLAGS)], "fixed").findings, [])

    def test_d2b_deep_flat_and_safe_back_are_left_alone(self):
        d2b = lib.back_flat_chain(5, 1, -640.08, -457.2)                   # already depth first
        self.assertEqual(lint.normalize_offense_play(UC_SLOT, CODES_11, self.pass_play(d2b))[0], None)
        shallow = positions(-5, [(-5, 0), (18, 0), (12, -1.5), (-18, -1.5), (6, -1.5)])
        self.assertEqual(lint.normalize_offense_play(shallow, CODES_11,
                                                     self.pass_play(lib.route_chain("Flat", 5, 1)))[0], None)


class TossRules(unittest.TestCase):
    """b780 b6-plays: out of the gun or the pistol a toss goes to the back's own side (SWeaR 11/01, Crack Toss under
    Gun Spread: the back "starts to go outside then cuts immediately back into the middle")."""
    CODES = (0, 5, 37, 6, 7, 39, 9, 73, 105, 41, 10)                   # QB T T2 C G G2, four WRs, HB (the JAX Gun Spread)
    WRS = [(-1554, 0), (823, -137), (-823, -137), (1554, 0)]
    GUN_LEFT = [(0, -482)] + LINE + WRS + [(-229, -482)]               # back 2.5 yd left of the QB
    GUN_RIGHT = [(0, -482)] + LINE + WRS + [(229, -482)]
    PISTOL = [(0, -365)] + LINE + WRS + [(0, -640)]                    # back 3 yd directly behind him
    UC_SPLIT = [(0, -183)] + LINE + WRS + [(250, -502)]                # retail Split Pro back, 2.7 yd right
    FLAGS = 0x0200820E                                                 # retail Weak G-Toss header: run, toss class

    @classmethod
    def design(cls, pos, scheme, direction):
        from mod_editor.core import nfl2k5_offense_concepts as oc, nfl2k5_offense_modern as om
        ctx = oc.FormationContext.build(pos, cls.CODES)
        d = om.run_design(ctx, scheme, direction=direction, codes=cls.CODES, own_side_only=False)
        oc.fill_unassigned(ctx, d)
        return d.chains

    def lint_codes(self, pos, chains):
        return [f for f in lint.lint_views([view(pos, chains, self.FLAGS, codes=self.CODES)], "toss").findings]

    def test_crossing_gun_toss_is_flagged_and_turned_to_the_backs_side(self):
        for scheme in ("HB Toss", "Crack Toss", "Zone Toss"):
            chains = self.design(self.GUN_LEFT, scheme, +1)                # back at -2.5, lane +5.83
            self.assertIsNone(validate(self.FLAGS, chains), scheme)
            found = self.lint_codes(self.GUN_LEFT, chains)
            self.assertEqual([f.code for f in found], ["TOSS_SIDE_CROSS"], scheme)
            self.assertEqual((found[0].data["offset_yd"], found[0].data["lane_yd"]), (-2.5, 5.83))
            fixed, receipts = lint.normalize_offense_play(self.GUN_LEFT, self.CODES, chains)
            toss = next(r for r in receipts if r["rule"] == "toss_side")
            self.assertEqual((toss["scheme"], toss["old_side"], toss["new_side"], toss["carrier"]), (scheme, 1, -1, 10))
            self.assertIsNone(validate(self.FLAGS, fixed), scheme)
            self.assertEqual(self.lint_codes(self.GUN_LEFT, fixed), [])
            # the QB's pitch, the lane, the run path and the line all turn to the back's side
            self.assertEqual(fixed[10][1][0], 0x16)
            self.assertEqual(int(fixed[10][1][1][2]), 8)                     # take handoff hole 8 = 5.83 yd left
            self.assertLess(fixed[10][2][1][1], 0)                           # run path aims left
            mirror, built, before = (lint._as_bytes(c) for c in (self.design(self.GUN_LEFT, scheme, -1), fixed, chains))
            core = (0, 1, 2, 3, 4, 5, 10)
            self.assertEqual([built[s] for s in core], [mirror[s] for s in core])
            self.assertEqual([built[s] for s in range(6, 10)], [before[s] for s in range(6, 10)])   # receivers keep their blocks
            again, more = lint.normalize_offense_play(self.GUN_LEFT, self.CODES, fixed)
            self.assertIsNone(again)
            self.assertEqual([r for r in more if r["rule"] == "toss_side"], [])

    def test_gun_toss_to_the_backs_own_side_is_left_alone(self):
        chains = self.design(self.GUN_RIGHT, "Crack Toss", +1)              # back at +2.5, lane +5.83: retail's shape
        self.assertEqual(self.lint_codes(self.GUN_RIGHT, chains), [])
        self.assertIsNone(lint.normalize_offense_play(self.GUN_RIGHT, self.CODES, chains)[0])

    def test_pistol_toss_to_a_back_behind_the_qb_is_not_a_side_problem(self):
        for direction in (+1, -1):
            chains = self.design(self.PISTOL, "Zone Toss", direction)
            self.assertNotIn("TOSS_SIDE_CROSS", [f.code for f in self.lint_codes(self.PISTOL, chains)])
            self.assertIsNone(lint.normalize_offense_play(self.PISTOL, self.CODES, chains)[0])

    def test_under_center_split_back_toss_keeps_retails_cross_behind(self):
        chains = self.design(self.UC_SPLIT, "HB Toss", -1)                  # retail Split Pro "Strong Toss": back right, lane left
        self.assertNotIn("TOSS_SIDE_CROSS", [f.code for f in self.lint_codes(self.UC_SPLIT, chains)])
        self.assertIsNone(lint.normalize_offense_play(self.UC_SPLIT, self.CODES, chains)[0])

    def test_edited_toss_is_never_rewritten(self):
        chains = self.design(self.GUN_LEFT, "Crack Toss", +1)
        chains[2] = [lib.start(3), lib.leg(0, 0, 1, turn=2)]               # hand-edited tackle
        fixed, receipts = lint.normalize_offense_play(self.GUN_LEFT, self.CODES, chains)
        self.assertIsNone(fixed)
        self.assertEqual([r for r in receipts if r["rule"] == "toss_side"], [])
        self.assertEqual([f.code for f in self.lint_codes(self.GUN_LEFT, chains)], ["TOSS_SIDE_CROSS"])

    def test_generator_only_offers_the_back_side_toss_out_of_the_gun(self):
        from mod_editor.core import nfl2k5_offense_concepts as oc, nfl2k5_offense_modern as om
        ctx = oc.FormationContext.build(self.GUN_LEFT, self.CODES)
        self.assertEqual((ctx.run_strong, om.toss_own_side(ctx, ctx.slot("B"))), (1, -1))
        with self.assertRaises(oc.ConceptUnavailable):
            om.run_design(ctx, "Crack Toss", codes=self.CODES)               # strong side: across behind the QB
        weak = om.run_design(ctx, "Crack Toss", weak=True, codes=self.CODES)
        self.assertEqual(weak.name, "Crack Toss Wk")
        self.assertEqual(int(weak.chains[10][1][1][2]), 8)
        # an explicit direction names the weak side itself; the wizard concept picks the back's side on its own
        self.assertEqual(om.run_design(ctx, "Crack Toss", direction=-1, codes=self.CODES).name, "Crack Toss Wk")
        built = oc.CONCEPTS["Crack Toss"].build(ctx)
        self.assertEqual(int(built.chains[10][1][1][2]), 8)
        # a back directly behind the QB (pistol) keeps both sides
        pistol = oc.FormationContext.build(self.PISTOL, self.CODES)
        self.assertIsNone(om.toss_own_side(pistol, pistol.slot("B")))
        for weak_flag in (False, True):
            om.run_design(pistol, "Zone Toss", weak=weak_flag, codes=self.CODES)

    # ---- b780 b6fix: the integration blockers from the review ----
    UNBALANCED = [(0, -482), (302, 0), (-302, 0), (0, 0), (155, 0), (230, 0)] + WRS + [(-229, -482)]   # both guards on the plus-x side

    def test_an_unbalanced_line_never_aborts_the_compile_rule(self):
        # the generator cannot block this line (one lineman gets no chain): the toss stays as authored, no ValueError
        chains = self.design(self.GUN_LEFT, "HB Toss", +1)
        self.assertEqual([f.code for f in self.lint_codes(self.UNBALANCED, chains)], ["TOSS_SIDE_CROSS"])
        self.assertEqual(lint.normalize_offense_play(self.UNBALANCED, self.CODES, chains), (None, []))
        two_tackles = [(0, -482), (302, 0), (302, 0), (0, 0), (155, 0), (-155, 0)] + self.WRS + [(-229, -482)]
        self.assertEqual(lint.normalize_offense_play(two_tackles, self.CODES, chains), (None, []))
        self.assertIsNotNone(lint.normalize_shared_offense_play([(self.UNBALANCED, self.CODES), (self.GUN_LEFT, self.CODES)],
                                                                chains)[0])                  # the balanced link still turns it

    def test_a_toss_linked_to_opposite_side_formations_picks_one_side(self):
        chains = self.design(self.GUN_LEFT, "Crack Toss", +1)               # authored once for a back-left set: lane plus x
        both = [(self.GUN_LEFT, self.CODES), (self.GUN_RIGHT, self.CODES)]
        # one link each: the play crosses in one of them either way, a tie keeps the play as authored and says so
        fixed, receipts = lint.normalize_shared_offense_play(both, chains, labels=["left", "right"])
        self.assertIsNone(fixed)
        self.assertEqual([(r["rule"], r["status"], r["crossing_formations"]) for r in receipts],
                         [("toss_side", "kept_mixed_links", ["left"])])
        # two back-left links against one back-right link: the side that crosses less (his own) wins and the receipt names the rest
        fixed, receipts = lint.normalize_shared_offense_play(both[:1] + both[:1] + both[1:], chains, labels=["l1", "l2", "r"])
        self.assertIsNotNone(fixed)
        self.assertEqual([(r["status"], r["new_side"], r["crossing_formations"]) for r in receipts],
                         [("rebuilt_mixed_links", -1, ["r"])])
        self.assertTrue(lint.toss_crosses(self.GUN_RIGHT, self.CODES, fixed))
        self.assertFalse(lint.toss_crosses(self.GUN_LEFT, self.CODES, fixed))
        self.assertIsNone(validate(self.FLAGS, fixed))
        # two back-right links against one back-left link: the authored side already crosses less
        fixed, receipts = lint.normalize_shared_offense_play(both[:1] + both[1:] + both[1:], chains, labels=["l", "r1", "r2"])
        self.assertIsNone(fixed)
        self.assertEqual(receipts[0]["crossing_formations"], ["l"])
        # every link crossing: a plain rebuild with the ordinary receipt, same as one formation alone
        fixed, receipts = lint.normalize_shared_offense_play(both[:1] + both[:1], chains)
        self.assertEqual(lint._as_bytes(fixed), lint._as_bytes(lint.normalize_offense_play(self.GUN_LEFT, self.CODES, chains)[0]))
        self.assertEqual([r["status"] for r in receipts], ["rebuilt"])
        # nothing to turn (no link crosses, a pistol link never does): untouched
        self.assertEqual(lint.normalize_shared_offense_play([(self.GUN_RIGHT, self.CODES), (self.PISTOL, self.CODES)], chains),
                         (None, []))

    def test_other_rules_must_still_agree_across_the_links_of_one_play(self):
        # an end-around fixed in one link and not in the other is still a conflict, not a silent pick
        flats = lint.end_around_template(GUN_WIDE, CODES_11, 9)
        self.assertIsNotNone(lint.normalize_offense_play(GUN_WIDE, CODES_11, flats)[0])
        self.assertIsNone(lint.normalize_offense_play(UC_SLOT, CODES_11, flats)[0])
        with self.assertRaises(lint.SharedPlayConflict):
            lint.normalize_shared_offense_play([(GUN_WIDE, CODES_11), (UC_SLOT, CODES_11)], flats)

    def test_studio_rules_lint_judges_a_shared_toss_as_the_compiler_writes_it(self):
        chains = self.design(self.GUN_LEFT, "Crack Toss", +1)

        def play_view(formation, pos):
            nodes = [list(codec.encode_chain(c)) for c in chains]
            return lint.PlayView(formation, f"f{formation}", 7, "Crack Toss", self.FLAGS, [tuple(map(float, q)) for q in pos],
                                 list(self.CODES), nodes)
        views = [play_view(0, self.GUN_LEFT), play_view(1, self.GUN_LEFT), play_view(2, self.GUN_RIGHT)]
        built = lint.as_built_views(views)
        report = lint.lint_views(built, "mixed")
        # the compiler turns the play to the minus-x side (two links) and leaves the lone back-right link crossing
        self.assertEqual([(f.formation, f.code) for f in report.findings], [(2, "TOSS_SIDE_CROSS")])
        self.assertEqual(built[0].chains, built[1].chains)
        self.assertEqual(built[0].chains, built[2].chains)

    def test_the_wizards_plain_toss_goes_to_the_backs_side_in_every_gun_formation(self):
        from mod_editor.core import nfl2k5_offense_concepts as oc
        checked = 0
        for name, spec in oc.FORMATIONS.items():
            ctx = spec.context()
            try:
                design = oc.design("Toss", ctx)
                weak = oc.design("Toss", ctx, {"direction": "weak"})
            except oc.ConceptUnavailable:
                continue
            car = ctx.slot("B")
            own = oc.toss_own_side(ctx, car) if car is not None else None
            if own is None:
                continue
            checked += 1
            for d in (design, weak):
                lane = codec.HANDOFF_HOLE_CM[int(next(n[1][2] for n in d.chains[car] if n[0] == 0x16))]
                self.assertGreater(lane * own, 0, f"{name}: Toss crosses behind the QB")
        self.assertGreaterEqual(checked, 30)                                  # 35 gun formations stand the back off to a side
        # the engine constant and the linter's copy of it stay the same number
        from mod_editor.core import nfl2k5_offense_modern as om
        self.assertEqual((om.TOSS_BEHIND_DEADBAND_YD, om.toss_own_side), (lint.TOSS_BEHIND_DEADBAND_YD, oc.toss_own_side))


class TossPackTool(unittest.TestCase):
    """b780 b6-plays: pb/v2/toss_side.py turns the shipped crossing shotgun tosses (the books written before the generator
    knew the back's side) and leaves everything else alone."""
    #: JAX Gun Spread "Crack Toss" exactly as SOFTDRINK v0.8 shipped it: the back (slot 10, 2.5 yd on the minus-x side of the QB)
    #: runs to the lane 5.83 yd on the plus-x side, across behind the QB
    V08_CRACK_TOSS = [
        [[1, [1, 4, 0, 0, 0, 0]], [3, [0]], [19, [10, 1]]],
        [[1, [1, 3, 0, 0, 0, 0]], [17, [0, 0, 1, 0, 0, 91.44, 91.44, 0]]],
        [[1, [1, 3, 0, 0, 0, 0]], [17, [0, 0, 1, 0, 0, 91.44, 91.44, 0]]],
        [[1, [1, 2, 0, 0, 0, 0]], [2, [0]], [17, [0, 0, 1, 0, 2, 91.44, 91.44, 0]]],
        [[1, [1, 3, 0, 0, 0, 0]], [17, [0, 0, 1, 0, 0, 91.44, 91.44, 0]]],
        [[1, [1, 3, 0, 0, 0, 0]], [17, [0, 0, 1, 0, 0, 91.44, 91.44, 0]]],
        [[1, [1, 3, 0, 0, 0, 0]], [17, [3, 0, 1, 0, 2, 0, 457.2, 1]], [17, [4, 0, 0, 0, 2, 640.08, 0, 1]]],
        [[1, [1, 3, 0, 0, 0, 0]], [17, [0, 0, 1, 0, 2, -274.32, 91.44, 0]]],
        [[1, [1, 3, 0, 0, 0, 0]], [17, [3, 0, 1, 0, 2, 0, 457.2, 1]]],
        [[1, [1, 3, 0, 0, 0, 0]], [17, [0, 0, 1, 0, 2, -274.32, 91.44, 0]]],
        [[1, [1, 3, 0, 0, 0, 0]], [22, [0, 0, 1]], [21, [0, 914.4, -91.44, 2, 15, 0, 0]]],
    ]

    def jax(self):
        return json.loads((ROOT / "data/playbooks/softdrink_jax_modern.2k5book").read_text(encoding="utf-8"))

    def test_tool_turns_the_v08_crossing_toss_once(self):
        from pb.v2 import toss_side
        doc = self.jax()
        play = next(p for p in doc["plays"] if p["id"] == "p111")
        play["assignments"], play["custom_name"] = json.loads(json.dumps(self.V08_CRACK_TOSS)), "Crack Toss"
        stats, changed = toss_side.fix_doc(doc, {"p111": "Gun Spread"})
        self.assertEqual((stats["tosses_rebuilt"], stats["links"]), (1, 1))
        self.assertEqual(changed["p111"], ("Crack Toss", "Crack Toss Wk", 4, 0, ["Gun Spread"]))
        self.assertEqual(play["custom_name"], "Crack Toss Wk")                # the lane is on the formation's weak side now
        back = play["assignments"][10]
        self.assertEqual([n[0] for n in back], [1, 22, 21])
        self.assertEqual(back[1][1][2], 8)                                    # take handoff hole 8: 5.83 yd on the back's (minus x) side
        self.assertEqual(back[2][1][1], -914.4)                               # and the run path out to the same side
        self.assertEqual(play["assignments"][0], self.V08_CRACK_TOSS[0])      # the QB's pitch to slot 10 is unchanged
        again, _ = toss_side.fix_doc(doc, {"p111": "Gun Spread"})
        self.assertEqual(dict(again), {})                                     # a second pass changes nothing
        self.assertEqual(toss_side.new_name("Crack Toss Wk"), "Crack Toss")   # the " Wk" mark follows the side

    def test_tool_resolves_the_packs_folder_and_refuses_an_empty_one(self):
        # b780 b6fix: a relative --packs used to skip the catalogs and manifests, and a missing folder passed --check
        from pb.v2 import toss_side
        self.assertTrue(toss_side.is_shipped_folder(ROOT / "data" / "playbooks"))
        try:
            relative = os.path.relpath(ROOT / "data" / "playbooks")           # ValueError on Windows when cwd is on another drive
        except ValueError:
            relative = None
        if relative is not None:
            self.assertTrue(toss_side.is_shipped_folder(Path(relative)))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(toss_side.main(["--check", "--packs", relative]), 0)
        self.assertTrue(toss_side.is_shipped_folder(ROOT / "data" / ".." / "data" / "playbooks"))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(toss_side.is_shipped_folder(Path(tmp)))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(toss_side.main(["--check", "--packs", tmp]), 2)                   # no packs in the folder
                self.assertEqual(toss_side.main(["--check", "--packs", os.path.join(tmp, "missing")]), 2)

    def test_shipped_packs_hold_the_own_side_toss(self):
        doc = self.jax()
        form = next(f for f in doc["formations"] if f["custom_name"] == "Gun Spread")
        self.assertLess(form["slot_positions"][10][0], 0)                     # the back stands on the minus-x side of the QB ...
        play = next(p for p in doc["plays"] if p["id"] == "p111")
        self.assertEqual(play["assignments"][10][1][1][2], 8)                 # ... and the lane is on his side (hole 8, minus x)
        self.assertEqual(play["custom_name"], "Crack Toss Wk")


IMAGE = Path(os.environ.get("NFL2K5_RETAIL_IMAGE", ""))


@unittest.skipUnless(IMAGE.is_file(), "needs the retail image")
class MixedLinksCompile(unittest.TestCase):
    """b780 b6fix, real compile: a toss linked to a back-left and a back-right formation used to stop the compile
    ("shared play has conflicting execution fixes"); now it compiles, the side with fewer crossings wins and the fix
    receipt names the formations that still cross."""
    raw = None

    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        with OuterImage(IMAGE) as image:
            cls.raw = image.read_entry(BOOK_ENTRIES["JAX"])

    def pack_with(self, extra_menus):
        """JAX with p111 (Crack Toss) as v0.8 authored it (crossing in Gun Spread f16, back minus x), also linked to
        ``extra_menus`` formations; f17 and f26 stand the back on the plus x side, f05 on the minus x side."""
        doc = json.loads((ROOT / "data/playbooks/softdrink_jax_modern.2k5book").read_text(encoding="utf-8"))
        play = next(p for p in doc["plays"] if p["id"] == "p111")
        play["assignments"], play["custom_name"] = json.loads(json.dumps(TossPackTool.V08_CRACK_TOSS)), "Crack Toss"
        for fid in extra_menus:
            doc["menus"][fid].append("p111")
        return packs.pack_from_json(doc)

    def compile(self, extra_menus):
        from mod_editor.core import nfl2k5_complete_offense as full
        compiled = full.compile_offense(self.raw, self.pack_with(extra_menus), asset_id="b6fix")
        fixes = {r["play_id"]: r["rules"] for r in compiled.report["execution_fixes"]["plays"]}
        crossing = sorted({f.formation_name for f in lint.lint_resource(compiled.replacement).findings
                           if f.code == "TOSS_SIDE_CROSS"})
        return fixes.get("p111", []), crossing

    def test_one_link_each_side_keeps_the_play_and_names_the_crossing_link(self):
        rules, crossing = self.compile(["f17"])
        self.assertEqual([(r["rule"], r["status"], r["crossing_formations"]) for r in rules], [("toss_side", "kept_mixed_links", ["f16"])])
        self.assertEqual(crossing, ["Gun Spread"])

    def test_more_back_left_links_turn_the_play_and_name_the_back_right_link(self):
        rules, crossing = self.compile(["f17", "f05"])                    # f16 + f05 back left, f17 back right
        self.assertEqual([(r["status"], r["new_side"], r["crossing_formations"]) for r in rules], [("rebuilt_mixed_links", -1, ["f17"])])
        self.assertEqual(crossing, ["Gun Doubles Clamp Stack"])


class DefenseAndPacks(unittest.TestCase):
    def test_mug_front_in_a_pack_is_reported(self):
        from types import SimpleNamespace
        dcodes = (12, 44, 13, 45, 14, 46, 78, 16, 17, 18, 50)
        pts = [(366, 0), (-366, 0), (146, 0), (-146, 0), (73, 91), (-73, 91), (0, 457), (640, 1189),
               (-640, 1097), (1372, 366), (-1372, 366)]
        pack = SimpleNamespace(formations=[SimpleNamespace(position_codes=dcodes, slot_positions=pts,
                                                           replace_index=28, custom_name="Nickel Mug")])
        found = lint.pack_defense_findings(pack)
        self.assertEqual([f.code for f in found], ["DEF_MIDDLE_MUG"])
        self.assertEqual(found[0].data["slots"], [4, 5])

    def test_all_shipped_softdrink_packs_lint_clean_as_built(self):
        totals = {}
        for team in packs.TEAM_BOOKS:
            name = "softdrink_giants_modern" if team == "NYG" else f"softdrink_{team.lower()}_modern"
            pack = packs.load_pack(ROOT / "data/playbooks" / f"{name}.2k5book")
            authored = lint.lint_pack(pack).counts()
            built = lint.lint_pack(pack, studio_rules=True)
            for code, n in authored.items():
                totals[code] = totals.get(code, 0) + n
            with self.subTest(team=team):
                bad = [f for f in built.findings if f.code in lint.EXECUTION_CODES]
                self.assertEqual(bad, [])
        # the v2 offense (job p48o) is generated against this linter: no authored finding in any of the 32 books
        self.assertEqual(totals, {})

    def test_back_primary_share_is_a_book_level_warning(self):
        pack = packs.load_pack(ROOT / "data/playbooks/softdrink_buf_modern.2k5book")
        found = [f for f in lint.lint_pack(pack, studio_rules=True).findings if f.code == "BACK_PRIMARY_SHARE"]
        self.assertEqual(found, [])                # v2 books spread the first read across the formation


class Cli(unittest.TestCase):
    def test_cli_pack_mode_outputs_and_exit_codes(self):
        tool = ROOT / "tools/nfl2k5_playbook_lint.py"
        pack = ROOT / "data/playbooks/softdrink_jax_modern.2k5book"
        with tempfile.TemporaryDirectory() as temp:
            out_json, out_md = Path(temp) / "lint.json", Path(temp) / "lint.md"
            authored = subprocess.run([sys.executable, str(tool), "--pack", str(pack), "--json", str(out_json),
                                       "--markdown", str(out_md)], capture_output=True, text=True)
            self.assertEqual(authored.returncode, 0, authored.stdout + authored.stderr)
            doc = json.loads(out_json.read_text())
            self.assertEqual(doc["schema"], lint.SCHEMA)
            self.assertEqual(doc["reports"][0]["counts"], {})
            self.assertIn("| book | links |", out_md.read_text())
            built = subprocess.run([sys.executable, str(tool), "--pack", str(pack), "--studio-rules"],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            self.assertIn("clean", built.stdout)
            again = subprocess.run([sys.executable, str(tool), "--pack", str(pack), "--json", str(out_json)],
                                   capture_output=True, text=True)
            self.assertEqual(again.returncode, 2)                         # outputs are exclusive


if __name__ == "__main__":
    unittest.main()
