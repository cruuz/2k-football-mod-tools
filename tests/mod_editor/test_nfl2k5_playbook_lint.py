"""Playbook execution linter and the Studio's compile-time repair rules (b77 job p13)."""
from pathlib import Path
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
