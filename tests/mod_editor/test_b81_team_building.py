"""CPU team building (beta 81, owner nfl2k5_team_building; the coordinator's rulings of 2026-11-25 and the review fixes
of the same day): the draft's need order and the free-agent wishes judged by the shared team-need rule.

Every class fails on c4406481b: there is no nfl2k5_team_building owner, code template or window proof there.

- Windows: the 29 code windows are proven unreferenced on the retail executable (tools/team_building/dead_code.py:
  references including loop/jecxz, digests, return + padding, decode synchronisation, entry/TLS), clear of the
  reservation inventory and of the economy's windows; the template reproduces from runtime.c (when gcc is present);
  its tables equal the draft AI's VALUE and the economy's aging line.
- Oracle: the Python mirror of runtime.c on built rosters: holes first by key, premium 3:2, QB in, a position drafted
  this draft out, an unseated development asset out in rounds 1 and 2 only, a bench man 3 better takes the seat,
  aging read in, OLB keyed with LB only in the two-pool scheme, the kept positions' tiers, a person's club keeps the
  retail order.
- Owner (TEAM_BUILDING_STANDARD_XBE, a standard executable with the draft AI and the economy; else skip): install,
  Retail, foreign, needs, and the draft AI reading applied with the branches retargeted.
- Studio and UpdateRoutes: the option, the v0.9 update (its in-place steps on a written copy of the released
  executable when NFL2K5_V09_XISO is set) and the single-setting edit (which sends the released v0.9 disc to the
  update).
- Image and EntryPoints (TEAM_BUILDING_IMAGE, a kept .b81mem.gz, and TEAM_BUILDING_IMAGE_XBE, its executable; else
  skip): the code runs natively in Unicorn on a real league: the native view equals the oracle's for every club,
  tb_order equals the oracle's order for every CPU club and round, the draft pick 0x31E0F0 and the retail wish routine
  0x3242C0 reach the code with their frames and registers intact, a person's club goes to the draft AI's cave, QB, K,
  P and FB keep the draft AI's score, a signed starter takes his seat, and each guard has a check that fails when
  the guard is changed in runtime.c (built with tools/team_building/assemble.py).
Fixtures come from the environment only (no private paths in the repo).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import unittest

from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, XBE as RETAIL_XBE

ROOT = Path(__file__).resolve().parents[2]
STANDARD_XBE = os.environ.get("TEAM_BUILDING_STANDARD_XBE", "")
IMAGE = os.environ.get("TEAM_BUILDING_IMAGE", "")
IMAGE_XBE = os.environ.get("TEAM_BUILDING_IMAGE_XBE", "")
NAMES = "QB K P WR CB FS SS HB FB TE OLB LB C G T DT EDGE".split()
P = {n: i for i, n in enumerate(NAMES)}


def _tb():
    from mod_editor.core import nfl2k5_team_building as tb
    return tb


def _with_economy_9(payload: bytes) -> bytes:
    """The franchise economy at revision 9 (a revision-8 or -7 executable upgrades in place, as the Studio does)."""
    from mod_editor.core import nfl2k5_franchise_economy as economy
    return economy.apply(payload)[0] if economy.status(payload) == "legacy" else payload


def _fixture(path):
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("TEAM_BUILDING_* fixture not set or absent")
    return Path(path).read_bytes()


class Windows(unittest.TestCase):
    def test_proof_on_retail(self):
        if not RETAIL_XBE.is_file():
            self.skipTest("retail extraction required")
        from tools.team_building import dead_code
        report = dead_code.verify(RETAIL_XBE.read_bytes())
        self.assertEqual(len(report["windows"]), 29)
        self.assertEqual(report["references"], 0)
        self.assertEqual(report["loop_references"], 0)
        self.assertEqual(dead_code.reservations_clear(), [])
        # The loop/jecxz scan finds a planted `loop` into a window (review N7).
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        payload = bytearray(RETAIL_XBE.read_bytes())
        start = min(dead_code.WINDOWS)
        image = XbeImage(bytes(payload))
        at = image.offset(start - 40, 2)
        payload[at - 30: at] = b"\x90" * 30                         # synchronise the decodes: nops, then the loop
        payload[at: at + 2] = bytes((0xE2, 40 - 2 + 4))
        self.assertTrue(dead_code.loop_references(XbeImage(bytes(payload))))

    def test_windows_clear_of_the_economy_and_each_other(self):
        from tools.franchise_economy import dead_code as economy
        from tools.team_building.dead_code import WINDOWS
        spans = sorted((va, va + n) for va, (n, _) in WINDOWS.items())
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])))
        for lo, hi in spans:
            for elo, (en, _) in economy.WINDOWS.items():
                self.assertFalse(lo < elo + en and elo < hi, hex(lo))

    def test_template_matches_the_proof_and_the_inputs(self):
        from mod_editor.core import nfl2k5_draft_ai as draft
        from mod_editor.core import nfl2k5_team_building_code as code
        from tools.team_building.dead_code import WINDOWS
        self.assertEqual({va: len(b) for va, b in code.WINDOWS.items()}, {va: n for va, (n, _) in WINDOWS.items()})
        self.assertEqual(code.RETAIL_SHA256, {va: d for va, (_, d) in WINDOWS.items()})
        self.assertEqual(code.INPUTS["value_x100"], [round(draft.VALUE[p] * 100) for p in draft.POSITIONS])
        data = json.loads((ROOT / "data/nfl2k5_franchise_economy.json").read_text())
        self.assertEqual(code.INPUTS["decline_after"], data["model"]["decline_after_years_pro"])
        from mod_editor.core import nfl2k5_franchise_economy_code as economy
        self.assertEqual(economy.SYMBOLS["economy_room_for_signing"], 0x2D82F0)   # the economy's pinned entry
        self.assertIn("tb_order", code.SYMBOLS)
        self.assertIn("tb_wish_entry", code.SYMBOLS)

    @unittest.skipUnless(shutil.which("gcc") and shutil.which("ld") and shutil.which("objcopy"), "GNU i386 tools")
    def test_template_reproduces(self):
        from tools.team_building import assemble
        self.assertEqual(assemble.generate(), assemble.TARGET.read_text())


def man(pos, points, row=0, pro=5, present=True, ref=0):
    from mod_editor.core.nfl2k5_team_building import Man
    return Man(ref, P[pos], points, row, pro, present)


BASE = (("QB", 85, 0), ("WR", 86, 0), ("WR", 84, 1), ("WR", 80, 2), ("T", 82, 0), ("T", 81, 1), ("EDGE", 80, 0),
        ("EDGE", 79, 1), ("CB", 82, 0), ("CB", 80, 1), ("DT", 78, 0), ("DT", 77, 1), ("TE", 80, 0), ("HB", 85, 0),
        ("FS", 80, 0), ("SS", 80, 0), ("LB", 82, 0), ("LB", 81, 1), ("C", 85, 0), ("G", 84, 0), ("G", 83, 1))


def club(spread=0):
    """An average club; `spread` moves every starter (the 31 others use -8..+7 so a club at 0 sits mid-league)."""
    return [man(pos, pts + spread, row) for pos, pts, row in BASE]


def league(own_roster):
    """31 clubs spread around the average and one under test (index 0)."""
    return [own_roster] + [club(i % 16 - 8) for i in range(31)]


RETAIL = [16, 7, 14, 3, 4, 6, 9, 11, 13, 5, 15, 0, 8, 12, 1, 2, 10]      # the round-1 board (picks 6-32), OLB last


class Oracle(unittest.TestCase):
    def setUp(self):
        self.tb = _tb()
        self.decline = [12, 14, 14, 7, 7, 8, 8, 5, 8, 8, 7, 7, 10, 10, 10, 9, 8]

    def _order(self, roster, rnd=0, human=False):
        v = self.tb.view(league(roster), 0)
        return self.tb.order(RETAIL, v, rnd, self.decline, human=human)

    def average(self, **change):
        roster = club(0)
        for pos, pts in change.items():
            roster = [m for m in roster if m.pos != P[pos]] + [man(pos, pts[0], 0), man(pos, pts[1], 1)] \
                if isinstance(pts, tuple) else [m for m in roster if m.pos != P[pos]] + [man(pos, pts)]
        return roster

    def test_no_hole_keeps_the_retail_order(self):
        self.assertEqual(self._order(self.average()), RETAIL)

    def test_a_wr_hole_goes_first_every_round(self):
        roster = self.average(WR=(85, 70))
        for rnd in range(7):
            self.assertEqual(self._order(roster, rnd)[0], P["WR"], rnd)

    def test_premium_holes_before_a_deeper_non_premium_hole(self):
        roster = self.average(WR=(86, 75), TE=66)                 # WR2 under the line; TE further under
        order = self._order(roster)
        self.assertLess(order.index(P["WR"]), order.index(P["TE"]))

    def test_quarterback_is_in_the_draft_need(self):
        self.assertEqual(self._order(self.average(QB=70))[0], P["QB"])

    def test_a_position_drafted_this_draft_is_not_a_hole(self):
        roster = self.average(WR=(85, 70)) + [man("WR", 72, 3, pro=1)]
        self.assertEqual(self._order(roster, 2), RETAIL)

    def test_a_development_asset_waits_until_round_three(self):
        # A compressed league (every other club's receivers at 78, the median starter 78) so that an unseated young man
        # can sit above the median and still be under the bench line (weakest + 3): the only place the rule still acts
        # now that a man 3 better takes the seat (review S1).
        own = [m for m in club(0) if m.pos != P["WR"]] + [man("WR", 86, 0), man("WR", 77, 1), man("WR", 79, 4, pro=2)]
        clubs = [own] + [[m for m in club(i % 16 - 8) if m.pos != P["WR"]] + [man("WR", 78, 0), man("WR", 78, 1)]
                         for i in range(31)]
        v = self.tb.view(clubs, 0)
        self.assertEqual((v.weak[P["WR"]], v.young[P["WR"]]), (77, 79))
        self.assertEqual(self.tb.order(RETAIL, v, 0, self.decline)[0], RETAIL[0])
        self.assertEqual(self.tb.order(RETAIL, v, 2, self.decline)[0], P["WR"])

    def test_the_own_seated_starter_is_not_a_development_asset(self):
        """Review S3: a young star in one receiver seat does not excuse a bottom-quarter man in the other."""
        roster = [m for m in self.average() if m.pos != P["WR"]] + [man("WR", 88, 0, pro=2), man("WR", 70, 1)]
        v = self.tb.view(league(roster), 0)
        self.assertEqual(v.young[P["WR"]], 0)
        self.assertEqual(self._order(roster, 0)[0], P["WR"])

    def test_a_better_man_on_the_bench_takes_the_seat(self):
        """Review S1: a CPU signing joins with his old club's depth row; a man 3 or more better than the weakest seat
        takes it in the view (the next depth sort will), so a hole just filled stops bidding. 2 better does not."""
        hole = self.average(WR=(85, 70))
        self.assertEqual(self._order(hole)[0], P["WR"])
        for extra, seated in ((man("WR", 86, 3), True), (man("WR", 73, 3), True), (man("WR", 72, 3), False),
                              (man("WR", 90, 3, present=False), False)):
            with self.subTest(points=extra.points, present=extra.present):
                v = self.tb.view(league(hole + [extra]), 0)
                self.assertEqual(v.weak[P["WR"]], min(85, extra.points) if seated else 70)
        self.assertNotEqual(self._order(hole + [man("WR", 86, 3)])[0], P["WR"])      # the hole is filled
        self.assertEqual(self._order(hole + [man("WR", 72, 3)])[0], P["WR"])         # 2 better: still the hole
        # The scale keeps the depth-row seats (the header's rule): the bench check is the own club's view only.
        self.assertEqual(self.tb.view(league(hole + [man("WR", 86, 3)]), 0).scale, self.tb.view(league(hole), 0).scale)

    def test_two_bench_men_fill_two_seats(self):
        roster = [m for m in self.average() if m.pos != P["CB"]] + [man("CB", 70, 0), man("CB", 69, 1),
                                                                     man("CB", 84, 4), man("CB", 83, 5)]
        v = self.tb.view(league(roster), 0)
        self.assertEqual(v.weak[P["CB"]], 83)

    def test_aging_reads_the_next_season(self):
        base = [m for m in self.average() if m.pos != P["WR"]]
        old = base + [man("WR", 86, 0), man("WR", 81, 1, pro=11)]      # 81 at eleven years pro reads as 77 next season
        young = base + [man("WR", 86, 0), man("WR", 81, 1, pro=4)]
        self.assertEqual(self._order(old)[0], P["WR"])
        self.assertEqual(self._order(young), RETAIL)

    def test_a_person_keeps_the_retail_order(self):
        self.assertEqual(self._order(self.average(WR=(85, 60)), human=True), RETAIL)

    def test_fullback_kicker_punter_never_holes(self):
        roster = [m for m in self.average() if m.pos not in (P["FB"], P["K"], P["P"])]
        self.assertEqual(self._order(roster), RETAIL)

    def test_olb_is_the_alias_or_keyed_with_lb_in_the_two_pool_scheme(self):
        """Review S6: in the one-pool scheme OLB (10) keeps its retail place; when some rostered man carries OLB (the
        economy's league_has_olb test) an LB hole moves OLB forward with LB."""
        hole = self.average(LB=(82, 66))
        one = self._order(hole)
        self.assertEqual(one[0], P["LB"])
        self.assertEqual(one.index(P["OLB"]), len(RETAIL) - 1)
        clubs = league(hole)
        clubs[5] = clubs[5] + [man("OLB", 75, 2)]
        v = self.tb.view(clubs, 0)
        self.assertTrue(v.olb)
        self.assertEqual(sorted(self.tb.order(RETAIL, v, 0, self.decline)[:2]), [P["OLB"], P["LB"]])

    def test_kept_positions_and_their_tiers(self):
        """Ruling 3 and review M1/S2: QB, K, P and FB keep the draft AI's score; whether they wish is its decision; short
        of the roster minimum they rank with the count deficits, a K or P the club has none of above the holes."""
        tb = self.tb
        self.assertEqual(tb.KEPT, (P["QB"], P["K"], P["P"], P["FB"]))
        self.assertEqual([p for p in range(17) if not tb.tn.NEED_SEATS[tb.tn.POOL[p]] or p == 0],
                         list(tb.KEPT))                                          # runtime.c tb_score's test
        self.assertEqual(tb.kept_score(P["QB"], 900, 0, 3), 900)               # today's score as it was
        self.assertEqual(tb.kept_score(P["QB"], -50, 1, 1), -50)               # the draft AI says no: no wish
        self.assertEqual(tb.kept_score(P["QB"], 900, 1, 1), 900 // 16 + 51200)  # a count deficit
        self.assertEqual(tb.kept_score(P["K"], 9000, 1, 0), 9000 // 16 + 200000)  # no kicker at all: above the holes
        self.assertEqual(tb.kept_score(P["FB"], 900, 1, 0), 900 // 16 + 51200)
        v = tb.view(league(self.average(WR=(86, 60))), 0)
        deepest = tb.new_score(v, P["WR"], 90, 0)
        self.assertLess(deepest, tb.kept_score(P["P"], 1, 1, 0))
        self.assertGreater(deepest, tb.kept_score(P["QB"], 20000, 4, 0))

    def test_new_score_tiers(self):
        v = self.tb.view(league(self.average(WR=(86, 70))), 0)
        hole = self.tb.new_score(v, P["WR"], 80, 0)
        deficit = self.tb.new_score(v, P["CB"], 0, 1)
        upgrade = self.tb.new_score(v, P["CB"], 90, 0)
        nothing = self.tb.new_score(v, P["CB"], 81, 0)           # CB's weakest need seat is 80: 81 is not 3 better
        self.assertGreater(hole, 100000)
        self.assertEqual(deficit, 51200)
        self.assertTrue(0 < upgrade < 50000)
        self.assertEqual(nothing, -1)
        self.assertEqual(self.tb.new_score(v, P["WR"], 72, 0), -1)  # not 3 points better: no wish even at a hole


class Owner(unittest.TestCase):
    def setUp(self):
        self.payload = _with_economy_9(_fixture(STANDARD_XBE))
        self.tb = _tb()

    def test_economy_revision_9(self):
        """A revision-8 economy reads legacy and upgrades in place by its one new window; team building needs it."""
        from mod_editor.core import nfl2k5_franchise_economy as economy
        old = _fixture(STANDARD_XBE)
        self.assertEqual(economy.REVISION, 9)
        if economy.status(old) == "legacy":
            self.assertFalse(self.tb.needs_met(old))
            with self.assertRaises(self.tb.TeamBuildingError):
                self.tb.apply(old)
            upgraded, receipt = economy.apply(old)
            changed = [i for i, (a, b) in enumerate(zip(old, upgraded)) if a != b]
            window = self.tb._offset(old, economy.ROOM_FOR_SIGNING_WINDOW)
            self.assertTrue(all(window <= i < window + 110 or i < 0x1000 for i in changed))
        self.assertEqual(economy.status(self.payload), "applied")
        self.assertTrue(self.tb.needs_met(self.payload))

    def test_install_restore_and_the_draft_ai(self):
        from mod_editor.core import nfl2k5_draft_ai as draft
        tb = self.tb
        self.assertEqual(tb.status(self.payload), "retail")
        self.assertTrue(tb.needs_met(self.payload))
        patched, receipt = tb.apply(self.payload)
        self.assertEqual(tb.status(patched), "applied")
        self.assertEqual(draft.status(patched), "applied")
        self.assertEqual(tb.apply(patched)[0], patched)
        e = tb.entries()
        self.assertEqual(tb._rel(patched, tb.HEAD_CALL_VA, 0xE8), e["order"])
        self.assertEqual(tb._rel(patched, tb.WISH_JUMP_VA, 0xE9), e["wish"])
        self.assertEqual(tb.as_draft_ai(patched)[tb._offset(patched, tb.HEAD_CALL_VA):][:5],
                         self.payload[tb._offset(self.payload, tb.HEAD_CALL_VA):][:5])
        if RETAIL_XBE.is_file():
            restored, _ = tb.restore(patched, RETAIL_XBE.read_bytes())
            self.assertEqual(restored, self.payload)
        self.assertLessEqual(receipt["code_bytes"], 3727)

    def test_foreign_and_needs(self):
        tb = self.tb
        patched, _ = tb.apply(self.payload)
        broken = bytearray(patched)
        off = tb._offset(patched, 0x2CE070)
        broken[off] ^= 0xFF
        self.assertEqual(tb.status(bytes(broken)), "foreign")
        with self.assertRaises(tb.TeamBuildingError):
            tb.apply(bytes(broken))
        if RETAIL_XBE.is_file():
            retail = RETAIL_XBE.read_bytes()
            self.assertEqual(tb.status(retail), "retail")
            self.assertFalse(tb.needs_met(retail))
            with self.assertRaises(tb.TeamBuildingError):
                tb.apply(retail)


class Studio(unittest.TestCase):
    """The option: plan field, presets, settings key, availability row, wording, and the build step itself."""

    def test_plan_presets_and_settings(self):
        from mod_editor.core import mod_build, nfl2k5_build_settings as settings
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).team_building, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["team_building"], name == "softdrink_experimental", name)
        self.assertIn("team_building", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_team_building", "CPU team building"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        tb = _tb()
        self.assertNotIn("\u2014", tb.HELP_TEXT + tb.BUILD_CAPTION)
        for path in ("mod_editor/core/nfl2k5_team_building.py", "tools/team_building/runtime.c",
                     "tests/mod_editor/test_b81_team_building.py"):
            self.assertNotIn("/" + "home/", (ROOT / path).read_text(encoding="utf-8"), path)

    def test_build_step_installs_or_leaves_out_with_a_note(self):
        import tempfile
        from mod_editor.core import mod_build
        payload = _fixture(STANDARD_XBE)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "default.xbe"
            plan = mod_build.BuildPlan(Path("source.iso"), target, team_building=True)
            target.write_bytes(payload)
            receipt = {"steps": [], "result": {}}
            mod_build._apply_team_building(plan, target, receipt, lambda *a: None)
            if not _tb().needs_met(payload):              # a revision-8 economy: left out with the note, nothing written
                self.assertEqual(receipt["result"]["team_building"], "left_out")
                self.assertIn(mod_build.TEAM_BUILDING_LEFT_OUT, receipt["user_notes"])
                self.assertEqual(target.read_bytes(), payload)
            target.write_bytes(_with_economy_9(payload))
            receipt = {"steps": [], "result": {}}
            mod_build._apply_team_building(plan, target, receipt, lambda *a: None)
            self.assertEqual(receipt["result"]["team_building"], "applied")
            self.assertEqual(_tb().status(target.read_bytes()), "applied")
            before = target.read_bytes()
            off = mod_build.BuildPlan(Path("source.iso"), target, team_building=False)
            mod_build._apply_team_building(off, target, {"steps": [], "result": {}}, lambda *a: None)
            self.assertEqual(target.read_bytes(), before)


class UpdateRoutes(unittest.TestCase):
    """Coordinator 11/25: the v0.9 update route and the single-setting edit offer CPU team building."""

    def test_v09_update_plan_and_cli(self):
        from unittest import mock
        from mod_editor.core import mod_build as build
        from tools import nfl2k5_modpack as cli
        self.assertIn("team_building", build.V09_UPDATE_CHOICES)
        plan = build.v09_disc_update("a.iso", "b.iso", team_building=True)
        self.assertIs(plan.team_building, True)
        self.assertIs(build.v09_disc_update("a.iso", "b.iso", backfield_cards=True).team_building, False)
        with self.assertRaises(ValueError):
            build.v09_disc_update("a.iso", "b.iso", team_building="yes")
        with mock.patch.object(build, "build", return_value={}) as run, \
                mock.patch("sys.stdout", new_callable=__import__("io").StringIO):
            self.assertEqual(cli.main(["update-v09", "--source", "a.iso", "--out", "b.iso", "--team-building", "--json"]), 0)
        self.assertIs(run.call_args.args[0].team_building, True)

    def test_single_setting_edit_plan_and_cli(self):
        from unittest import mock
        from mod_editor.core import mod_build as build
        from tools import nfl2k5_modpack as cli
        plan = build.team_building_disc_edit("built.iso", "copy.iso")
        self.assertIs(type(plan), build._InstalledTeamBuildingEdit)
        self.assertTrue(plan.team_building and build._only_team_building_changes(plan))
        self.assertFalse(build._only_team_building_changes(build.BuildPlan("built.iso", "copy.iso", team_building=True)))
        with mock.patch.object(build, "build", return_value={}) as run, \
                mock.patch("sys.stdout", new_callable=__import__("io").StringIO):
            self.assertEqual(cli.main(["edit-team-building", "--source", "a.iso", "--out", "b.iso", "--json"]), 0)
        self.assertIs(type(run.call_args.args[0]), build._InstalledTeamBuildingEdit)

    def test_edit_payload_upgrades_the_economy_then_installs(self):
        from mod_editor.core import mod_build as build
        payload = _fixture(STANDARD_XBE)
        patched, economy_receipt, receipt = build._team_building_edit_payload(payload)
        self.assertEqual(_tb().status(patched), "applied")
        self.assertEqual(patched, _tb().apply(_with_economy_9(payload))[0])
        self.assertEqual(economy_receipt is not None, payload != _with_economy_9(payload))
        if RETAIL_XBE.is_file():
            with self.assertRaises(ValueError):
                build._team_building_edit_payload(RETAIL_XBE.read_bytes())

    def test_single_setting_edit_preflight_on_a_built_disc(self):
        """Preflight on the reviewed private standard disc writes nothing and reports the executable it would write."""
        import hashlib
        from mod_editor.core import mod_build as build
        disc = Path(os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC", "") or "missing")
        if not disc.is_file():
            self.skipTest("the reviewed private standard disc is absent")
        target = ROOT / "never-written-team-building.xiso.iso"
        receipt = build.preflight_plan(build.team_building_disc_edit(str(disc), str(target)))
        self.assertFalse(target.exists())
        source = build._xbe_bytes(disc)
        expected = build._team_building_edit_payload(source)[0]
        self.assertEqual(receipt["team_building_source_update"]["result_sha256"], hashlib.sha256(expected).hexdigest())
        if receipt["team_building_source_update"]["economy_upgraded"]:              # review N8: the user is told
            self.assertIn(build.TEAM_BUILDING_ECONOMY_NOTE, receipt.get("user_notes", []))

    def test_v09_update_preflight_carries_team_building(self):
        from unittest import mock
        from mod_editor.core import mod_build as build
        import tempfile
        disc = Path(os.environ.get("NFL2K5_V09_XISO", "") or "missing")
        if not disc.is_file():
            self.skipTest("the released v0.9 disc is absent")
        source = build._xbe_bytes(disc)
        release = build._v09_reference(disc, source)
        with tempfile.TemporaryDirectory() as folder:
            plan = build.v09_disc_update(str(disc), str(Path(folder) / "copy.iso"), team_building=True)
            with mock.patch("mod_editor.core.modpack.hash_file", return_value=release["image_sha256"]):
                receipt = build._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
        self.assertIn("team_building", receipt["v09_update"])
        self.assertIn("franchise_economy", receipt["v09_update"])


    def test_the_released_v09_disc_goes_to_the_v09_update(self):
        """Review S7: the single-setting edit refuses the released v0.9 disc before anything is read or written and
        names the v0.9 update, which also brings the disc's CPU decisions, kick aim and history storage current."""
        from unittest import mock
        from mod_editor.core import mod_build as build
        plan = build.team_building_disc_edit("v09.iso", "copy.iso")
        with mock.patch.object(build, "_v09_reference", return_value={"name": "SOFTDRINK 2K28 v0.9"}), \
                mock.patch.object(build, "_team_building_edit_payload") as payload, \
                mock.patch.object(build, "_copy_private_build_source") as copying:
            with self.assertRaisesRegex(ValueError, "update-v09 --team-building"):
                build._edit_installed_team_building(plan, Path("v09.iso"), Path("copy.iso"), b"xbe",
                                                    {"steps": [], "result": {}}, lambda *_: None, preflight=False,
                                                    consume=False, reference=None)
        payload.assert_not_called()
        copying.assert_not_called()
        disc = Path(os.environ.get("NFL2K5_V09_XISO", "") or "missing")
        if disc.is_file():
            target = ROOT / "never-written-team-building-v09.xiso.iso"
            with self.assertRaisesRegex(ValueError, "v0.9 update"):
                build.preflight_plan(build.team_building_disc_edit(str(disc), str(target)))
            self.assertFalse(target.exists())

    def test_v09_update_in_place_steps_on_a_written_executable(self):
        """Review S5: the v0.9 update with CPU team building, run through its real in-place steps on a written copy of
        the released executable (the disc copy, compaction and the finished-disc checks stubbed): the product's own
        final comparison with the expected chain holds, and the owner, the draft AI and the economy read applied."""
        import tempfile
        from unittest import mock
        from mod_editor.core import mod_build as build
        from mod_editor.core import nfl2k5_draft_ai as draft, nfl2k5_franchise_economy as economy
        disc = Path(os.environ.get("NFL2K5_V09_XISO", "") or "missing")
        if not disc.is_file():
            self.skipTest("the released v0.9 disc is absent")
        original = build._xbe_bytes(disc)
        release = build._v09_reference(disc, original)
        self.assertIsNotNone(release)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "default.xbe"

            def copy(source, out, receipt, progress, consume):
                out.write_bytes(original)
                receipt["source_sha256"] = release["image_sha256"]

            for team_building in (True, False):
                with self.subTest(team_building=team_building):
                    plan = build.v09_disc_update(str(disc), str(target), team_building=team_building,
                                                 backfield_cards=not team_building, overwrite=True)
                    with mock.patch.object(build, "_copy_private_build_source", side_effect=copy), \
                            mock.patch.object(build, "_compact_build_disc"), \
                            mock.patch.object(build, "_verify_finished_game_disc"), \
                            mock.patch.object(build, "inspect", return_value={}):
                        receipt = build._update_v09_disc(plan, lambda *_: None, preflight=False, project=False)
                    written = target.read_bytes()
                    self.assertEqual(_tb().status(written), "applied" if team_building else "retail")
                    self.assertEqual(draft.status(written), "applied")
                    self.assertEqual(economy.status(written), "applied")
                    self.assertEqual(receipt["result"].get("team_building"), "applied" if team_building else None)


class MidRank(unittest.TestCase):
    """Coordinator 11/25 and header 1fbb90087: the scale holds every club's need-seat starters (an empty seat rates 0),
    the percentile is the mid-rank, so a tie at the quarter line is not a hole."""

    def test_a_tie_at_the_line_is_not_a_hole(self):
        tb = _tb()
        scale = [70] * 10 + [80] * 16 + [90] * 38             # 64 values; 80 sits across the quarter line
        self.assertEqual(tb.percentile(scale, 80), (2 * 10 + 16) * 128 // 64)
        self.assertGreaterEqual(tb.percentile(scale, 80), tb.HOLE)
        self.assertLess(tb.percentile(scale, 79), tb.HOLE)

    def test_an_empty_need_seat_rates_zero_on_the_scale(self):
        tb = _tb()
        roster = [m for m in club(0) if m.pos != P["CB"]] + [man("CB", 82, 0)]   # one present corner: one seat empty
        v = tb.view(league(roster), 0)
        self.assertEqual(v.weak[P["CB"]], 0)
        self.assertEqual(len(v.scale[P["CB"]]), 64)
        self.assertEqual(v.scale[P["CB"]][0], 0)


def code_economy_cap():
    from mod_editor.core import nfl2k5_franchise_economy_code as economy
    return economy.SYMBOLS["economy_cap"]


def _load_image(cls):
    """The kept league image in a fresh Unicorn machine on `cls`: its executable with the economy upgrade and this owner
    (every changed code byte written over the image's own code), the clubs, the user's clubs and the league as Man
    rows. Keeps the image's RAM outside the code range for _restore_ram."""
    from tests.nfl2k5_supersim_draft_fixture import Machine
    from tools import franchise_invariants as fi
    from mod_editor.core import nfl2k5_team_building_code as code
    tb = _tb()
    xbe, image = _with_economy_9(_fixture(IMAGE_XBE)), IMAGE
    if not image or not Path(image).is_file():
        raise unittest.SkipTest("TEAM_BUILDING_IMAGE not set or absent")
    cls.tb, cls.code = tb, code
    original = _fixture(IMAGE_XBE)
    patched, _ = tb.apply(xbe)
    cls.m = m = Machine(patched, trace_writes=False)
    cls.ram = []
    for lo, data in fi.load_memory(Path(image)).regions:
        if lo < 0x3000000:
            m.uc.mem_write(lo, data)
            if lo + len(data) > CODE_END or lo < CODE_START:
                cls.ram.append((lo, bytes(data)))
    # The image holds the code it was made with: write back every byte the economy upgrade and this owner changed.
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    new, old = XbeImage(patched), XbeImage(original)
    for section in new.sections:
        if not section.raw_size or not section.start < 0x420000:
            continue
        a, b = old.read(section.start, section.raw_size), new.read(section.start, section.raw_size)
        i = 0
        while i < len(b):
            if a[i] != b[i]:
                j = i
                while j < len(b) and a[j] != b[j]:
                    j += 1
                m.uc.mem_write(section.start + i, b[i:j])
                i = j
            else:
                i += 1
    cls.PROBE = 0x3200000
    m.uc.mem_map(cls.PROBE, 0x1000)
    m.uc.ctl_flush_tb()
    root = m.get(0xB72918)
    cls.teams = [m.get(root + 0x1C) + 500 * i for i in range(32)]
    cls.user = [i for i in range(32) if m.call(0x13EC30, ecx=cls.teams[i], budget=100000)]
    cls._points = {}
    cls.league = [[cls._man(m.get(t + 4 * k)) for k in range(m.uc.mem_read(t + 0x11C, 1)[0])] for t in cls.teams]


CODE_START, CODE_END = 0x10000, 0x420200      # the executable's code (and the draft AI's header cave) in the image


def _restore_ram(cls):
    """The image's RAM back, outside the code range (a wish pass creates bids; a signing changes a roster)."""
    for lo, data in cls.ram:
        hi = lo + len(data)
        if hi <= CODE_START or lo >= CODE_END:
            cls.m.uc.mem_write(lo, data)
        else:
            if lo < CODE_START:
                cls.m.uc.mem_write(lo, data[:CODE_START - lo])
            if hi > CODE_END:
                cls.m.uc.mem_write(CODE_END, data[CODE_END - lo:])


class _ImageBase(unittest.TestCase):
    """A kept league image in its own machine (no tests here)."""

    @classmethod
    def setUpClass(cls):
        if not HAVE_UC:
            raise unittest.SkipTest("Unicorn required")
        _load_image(cls)

    @classmethod
    def _rating(cls, p, flag):
        m = cls.m
        code = (b"\xb9" + struct.pack("<I", p) + b"\xba" + struct.pack("<I", flag) + b"\xb8" +
                struct.pack("<I", 0x246D80) + b"\xff\xd0\xd9\x1d" + struct.pack("<I", cls.PROBE + 0x800) + b"\xc3")
        m.uc.mem_write(cls.PROBE, code)
        m.uc.ctl_flush_tb()
        m.call(cls.PROBE, budget=2_000_000)
        return m.get(cls.PROBE + 0x800)

    @classmethod
    def _man(cls, p):
        from mod_editor.core import nfl2k5_team_need as tn
        rec = bytes(cls.m.uc.mem_read(p, 0x54))
        if p not in cls._points:
            cls._points[p] = tn.points(cls._rating(p, 0))
        return cls.tb.Man(p, rec[0x35], cls._points[p], tn.row(rec), rec[0x25] & 31, tn.present(rec))

    def _native_order(self, fn, club, rnd, pick=15):
        need = 0x3000800
        self.m.uc.mem_write(need, bytes(68))
        self.m.put(0xE3C0A8, rnd)
        self.m.call(fn, ecx=self.teams[club], edx=rnd, args=(pick, need), budget=200_000_000)
        return list(struct.unpack("<17i", bytes(self.m.uc.mem_read(need, 68))))

    def _free_agents(self):
        root = self.m.get(0xB72918)
        count, table = self.m.get(root + 0x38), self.m.get(root + 0x3C)
        return [self.m.get(table + 4 * i) for i in range(count)]

    def _best_free_agents(self):
        """best[17] as the retail wish routine hands it over: the best free agent by 0x246D80(p, 1) at each position."""
        best, top = [0] * 17, [-1.0] * 17
        for p in self._free_agents():
            pos = self.m.uc.mem_read(p + 0x35, 1)[0]
            if pos < 17:
                r = struct.unpack("<f", struct.pack("<I", self._rating(p, 1)))[0]
                if r > top[pos]:
                    top[pos], best[pos] = r, p
        return best

    def _scores(self, team, best, view=0x3002000, target=0x3001100):
        """{position: (score, target)} from the native tb_view and tb_score with the club's own room."""
        m, code = self.m, self.code
        m.call(code.SYMBOLS["tb_view"], args=(view, team), budget=400_000_000)
        room = m.call(0x2D82F0, ecx=team, budget=50_000_000)
        out = {}
        for p in range(17):
            score = m.call(code.SYMBOLS["tb_score"], args=(view, team, p, best[p], room, target), budget=400_000_000)
            out[p] = (score - (1 << 32) if score >= 1 << 31 else score, m.get(target))
        return out

    def _install(self, blobs, symbols):
        """A runtime build (blobs, symbols from assemble.build) over the installed one, both branches retargeted."""
        m, tb = self.m, self.tb
        for va, blob in blobs.items():
            m.uc.mem_write(va, blob.ljust(len(self.code.WINDOWS[va]), b"\xcc"))
        m.uc.mem_write(tb.HEAD_CALL_VA, tb._branch(tb.HEAD_CALL_VA, 0xE8, symbols["tb_order"]))
        m.uc.mem_write(tb.WISH_JUMP_VA, tb._branch(tb.WISH_JUMP_VA, 0xE9, symbols["tb_wish_entry"]))
        m.uc.ctl_flush_tb()

    def _wish_pass(self, symbols):
        """The retail wish routine 0x3242C0 whole, with its jump retargeted: what each club's pass did."""
        import unicorn
        m, rec = self.m, {"entry": [], "wishes": [], "cave": [], "exit": 0}

        def on_entry(uc, a, n, _):
            esp = m.reg("ESP")
            rec["entry"].append({"team": m.reg("ESI"), "ebx": m.reg("EBX"), "count": m.get(esp + 0x10),
                                 "best": esp + 0x20, "row": [m.get(esp + 0x20 + 4 * i) for i in range(17)]})

        def on_wishes(uc, a, n, _):
            rec["wishes"].append({"team": m.reg("ECX"), "best": m.reg("EDX"), "count": m.get(m.reg("ESP") + 4)})

        hooks = [m.uc.hook_add(unicorn.UC_HOOK_CODE, on_entry, begin=symbols["tb_wish_entry"],
                               end=symbols["tb_wish_entry"]),
                 m.uc.hook_add(unicorn.UC_HOOK_CODE, on_wishes, begin=symbols["tb_wishes"], end=symbols["tb_wishes"]),
                 m.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, n, _: rec["cave"].append(m.reg("ESI")),
                               begin=self.tb.DRAFT_CAVE_VA, end=self.tb.DRAFT_CAVE_VA),
                 m.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, n, _: rec.__setitem__("exit", rec["exit"] + 1),
                               begin=0x324545, end=0x324545)]
        try:
            m.call(0x3242C0, budget=3_000_000_000)
            rec["registers"] = tuple(m.reg(r) for r in ("EBX", "ESI", "EDI", "EBP", "ESP"))
        finally:
            for hook in hooks:
                m.uc.hook_del(hook)
            _restore_ram(type(self))
        return rec

    def _kept_paths(self, club, symbols):
        """{position: 'old' | 'new'}: which score tb_score took for each position (code hooks on tb_old_score and
        tb_seek), with the club's K and P moved off the roster so those positions are reached too; and the scores."""
        import unicorn
        m, team = self.m, self.teams[club]
        best = self._best_free_agents()
        for pos in range(17):                     # a position without a free agent: any man there (only rated)
            if not best[pos]:
                best[pos] = next((x.ref for c in self.league for x in c if x.pos == pos), 0)
        moved = [x.ref for x in self.league[club] if x.pos in (1, 2)]
        for ref in moved:
            m.uc.mem_write(ref + 0x35, bytes([17]))
        path, cur = {}, {}
        hooks = [m.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, n, _: path.setdefault(cur["p"], "old"),
                               begin=symbols["tb_old_score"], end=symbols["tb_old_score"]),
                 m.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, n, _: path.setdefault(cur["p"], "new"),
                               begin=symbols["tb_seek"], end=symbols["tb_seek"])]
        scores = {}
        try:
            view, target = 0x3002000, 0x3001100
            m.call(symbols["tb_view"], args=(view, team), budget=400_000_000)
            room = m.call(0x2D82F0, ecx=team, budget=50_000_000)
            for p in range(17):
                cur["p"] = p
                score = m.call(symbols["tb_score"], args=(view, team, p, best[p], room, target), budget=400_000_000)
                scores[p] = score - (1 << 32) if score >= 1 << 31 else score
        finally:
            for hook in hooks:
                m.uc.hook_del(hook)
            for x in self.league[club]:
                if x.pos in (1, 2):
                    m.uc.mem_write(x.ref + 0x35, bytes([x.pos]))
        return path, scores


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class Image(_ImageBase):
    """The code runs natively on a kept league image (the executable it was made with plus this owner)."""

    def test_native_view_equals_the_oracle(self):
        tb, m = self.tb, self.m
        x = 0x3001000
        for club in (0, 9, 14, 21):
            m.call(self.code.SYMBOLS["tb_view"], args=(x, self.teams[club]), budget=200_000_000)
            raw = bytes(m.uc.mem_read(x, 17 * 5 + 17 * 64))
            v = tb.view(self.league, club)
            self.assertEqual(list(raw[0:17]), v.weak, club)
            self.assertEqual(list(raw[17:34]), v.wpro, club)
            self.assertEqual(list(raw[34:51]), v.young, club)
            self.assertEqual(list(raw[51:68]), v.drafted, club)
            for pool in range(17):
                n = raw[68 + pool]
                self.assertEqual(list(raw[85 + 64 * pool: 85 + 64 * pool + n]), v.scale[pool], (club, pool))
            self.assertEqual(m.uc.mem_read(x + 85 + 17 * 64, 1)[0], int(v.olb), club)

    def test_native_order_equals_the_oracle_for_every_cpu_club(self):
        tb, decline = self.tb, self.tb.decline_after()
        holes_first = 0
        for club in range(32):
            human = club in self.user
            v = tb.view(self.league, club)
            for rnd in (0, 1, 3, 6):
                retail = self._native_order(0x31DEA0, club, rnd)
                ours = self._native_order(self.code.SYMBOLS["tb_order"], club, rnd)
                self.assertEqual(ours, tb.order(retail, v, rnd, decline, human=human), (club, rnd))
                if human:
                    self.assertEqual(ours, retail, club)
                elif ours[0] != retail[0]:
                    holes_first += 1
        self.assertGreater(holes_first, 0)     # fails on the retail need (it never puts a hole first by quality)

    def test_hole_first_where_the_retail_need_had_it_lower(self):
        tb, decline = self.tb, self.tb.decline_after()
        moved = []
        for club in range(32):
            if club in self.user:
                continue
            v = tb.view(self.league, club)
            holes = [p for p in range(17) if p != 10 and tb.key(v, tb.tn.POOL[p], 0, decline) < 255]
            if not holes:
                continue
            retail = self._native_order(0x31DEA0, club, 0)
            ours = self._native_order(self.code.SYMBOLS["tb_order"], club, 0)
            self.assertIn(ours[0], holes, club)
            if retail.index(ours[0]) > 0:
                moved.append((club, NAMES[ours[0]], retail.index(ours[0])))
        self.assertTrue(moved)

    def test_wishes_go_to_holes_first(self):
        """Hole scores carry no jitter: the routine tries the holes whose affordable 3-point upgrade scores above 100000
        first, in score order, before any other position (the native wish may still refuse one)."""
        m, code = self.m, self.code
        root = m.get(0xB72918)
        count, table = m.get(root + 0x38), m.get(root + 0x3C)
        best, top = [0] * 17, [-1.0] * 17
        for i in range(count):
            p = m.get(table + 4 * i)
            pos = m.uc.mem_read(p + 0x35, 1)[0]
            if pos < 17:
                r = struct.unpack("<f", struct.pack("<I", self._rating(p, 1)))[0]
                if r > top[pos]:
                    top[pos], best[pos] = r, p
        m.uc.mem_write(0x3001000, struct.pack("<17I", *best))
        view, target = 0x3002000, 0x3001100
        clubs_with_holes = 0
        for club in range(32):
            if club in self.user:
                continue
            team = self.teams[club]
            m.call(code.SYMBOLS["tb_view"], args=(view, team), budget=200_000_000)
            room = m.call(0x2D82F0, ecx=team, budget=50_000_000)       # economy_room_for_signing (revision 9)
            cap = m.call(code_economy_cap(), ecx=team, edx=1, args=(0,), budget=50_000_000)
            self.assertEqual(room, (cap - m.get(team + 0x124) - 10) & 0xFFFFFFFF, club)
            room = room - (1 << 32) if room >= 1 << 31 else room
            holes = []
            for p in range(17):
                score = m.call(code.SYMBOLS["tb_score"], args=(view, team, p, best[p], room & 0xFFFFFFFF, target),
                               budget=200_000_000)
                score = score - (1 << 32) if score >= 1 << 31 else score
                if score > 100000:
                    holes.append((score, m.get(target)))
            tried = []
            hook = m.uc.hook_add(__import__("unicorn").UC_HOOK_CODE, lambda uc, a, n, _: tried.append(m.get(m.reg("ESP") + 4)),
                                 begin=code.SYMBOLS["tb_wish"], end=code.SYMBOLS["tb_wish"])
            m.call(code.SYMBOLS["tb_wishes"], ecx=team, edx=0x3001000, args=(0,), budget=400_000_000)
            m.uc.hook_del(hook)
            if holes:
                clubs_with_holes += 1
                wanted = [t for _s, t in sorted(holes, key=lambda h: -h[0])]
                self.assertEqual(tried[:min(len(wanted), len(tried))], wanted[:len(tried)], club)
                self.assertGreaterEqual(len(tried), min(4, len(wanted)), club)
        self.assertGreater(clubs_with_holes, 0)


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class EntryPoints(_ImageBase):
    """Review S5: the real entry points on the kept image (the draft pick 0x31E0F0 and the retail wish routine 0x3242C0
    with their branches retargeted), the kept positions, a signing's seat, and guard mutations that the checks catch."""

    SAVED = (0x11111111, 0x22222222, 0x33333333, 0x44444444)

    def test_the_draft_pick_head_reaches_tb_order_for_every_club(self):
        import unicorn
        m, code = self.m, self.code
        seen = []
        hook = m.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, n, _: seen.append(m.reg("ECX")),
                             begin=code.SYMBOLS["tb_order"], end=code.SYMBOLS["tb_order"])
        try:
            for rnd in (0, 3):
                m.put(0xE3C0A8, rnd)
                m.put(0xE3C0A4, 15)
                for club in range(32):
                    pick = m.call(0x31E0F0, ecx=self.teams[club], edx=0 if club in self.user else 1,
                                  budget=2_000_000_000)
                    self.assertEqual(tuple(m.reg(r) for r in ("EBX", "ESI", "EDI", "EBP", "ESP")),
                                     self.SAVED + (m.STACK + 4,), (club, rnd))
                    self.assertTrue(m.uc.mem_read(pick + 8, 1)[0] & 0x10, (club, rnd))      # a prospect
        finally:
            m.uc.hook_del(hook)
            _restore_ram(type(self))
        self.assertEqual(len(seen), 64)
        self.assertEqual(set(seen), set(self.teams))

    def test_the_wish_routine_sends_a_persons_club_to_the_draft_ai(self):
        """Review M3: with "CPU signs and cuts for me" on (0xE6013C, set in the image) retail asks for the user's club's
        wishes too; it goes on to the draft AI's own cave, every CPU club to tb_wishes with the routine's frame."""
        m, tb = self.m, self.tb
        users = {self.teams[i] for i in self.user}
        if not m.get(0xE6013C) or not users:
            self.skipTest("the image's own club gets no wishes")
        rec = self._wish_pass(self.code.SYMBOLS)
        self.assertEqual(rec["registers"], self.SAVED + (m.STACK + 4,))
        entered = [e["team"] for e in rec["entry"]]
        self.assertTrue(users & set(entered))
        self.assertEqual(sorted(rec["cave"]), sorted(t for t in entered if t in users))
        self.assertEqual([w["team"] for w in rec["wishes"]], [t for t in entered if t not in users])
        cpu = [e for e in rec["entry"] if e["team"] not in users]
        self.assertGreater(len(cpu), 20)
        for e, w in zip(cpu, rec["wishes"]):
            self.assertEqual((w["best"], w["count"], e["count"]), (e["best"], e["ebx"], e["ebx"]))
            for pos, player in enumerate(e["row"]):
                if player:
                    self.assertEqual(m.uc.mem_read(player + 0x35, 1)[0], pos)
        self.assertEqual(rec["exit"], len(entered))

    def _cpu_club_with_quarterback_room(self):
        return next(i for i in range(32) if i not in self.user and sum(x.pos == 0 for x in self.league[i]) < 4)

    def test_kept_positions_take_the_draft_ai_score(self):
        """Review M1 and S2: QB, K, P and FB score by the draft AI's own rule; a club with no K or P ranks that wish
        above every hole."""
        tb = self.tb
        path, scores = self._kept_paths(self._cpu_club_with_quarterback_room(), self.code.SYMBOLS)
        self.assertTrue({0, 1, 2} <= set(path), path)
        for p, how in path.items():
            self.assertEqual(how, "old" if p in tb.KEPT else "new", NAMES[p])
        self.assertTrue(set(path) - set(tb.KEPT))
        for p in (1, 2):
            self.assertGreaterEqual(scores[p], 200000, NAMES[p])
        self.assertLess(max(v for p, v in scores.items() if p not in (1, 2)), 200000)

    def test_a_signed_starter_takes_his_seat_and_the_hole_closes(self):
        """Review S1: the CPU signing appends the man with his old club's depth row and sorts nothing. For every hole
        wish of every CPU club, the man joins the roster the way the build's acceptance does it (off the free-agent
        list 0x2425C0, appended by 0xC3EE0 at an offseason stage); the native view then seats him and equals the
        oracle's, and the hole closes unless the club's other seat is a hole too."""
        m, tb, code = self.m, self.tb, self.code
        root, view = m.get(0xB72918), 0x3002000
        best = self._best_free_agents()
        cases, closed = 0, 0
        try:
            for club in range(32):
                if club in self.user:
                    continue
                team = self.teams[club]
                holes = [(p, t) for p, (score, t) in self._scores(team, best).items()
                         if score > 100000 and p not in tb.KEPT and t]
                for p, t in holes:
                    n0 = m.uc.mem_read(team + 0x11C, 1)[0]
                    stage = m.get(0xE576A4)
                    m.put(0xE576A4, 3)
                    m.call(0x2425C0, ecx=root + 0x38, edx=t, budget=5_000_000)
                    m.call(0xC3EE0, ecx=team, edx=t, budget=5_000_000)
                    m.put(0xE576A4, stage)
                    if m.uc.mem_read(team + 0x11C, 1)[0] != n0 + 1:      # the build refused: the retail append's effect
                        m.put(team + 4 * n0, t)
                        m.uc.mem_write(team + 0x11C, bytes([n0 + 1]))
                    newcomer = self._man(t)
                    own = list(self.league[club]) + [newcomer]
                    clubs = list(self.league)
                    clubs[club] = own
                    v = tb.view(clubs, club)
                    m.call(code.SYMBOLS["tb_view"], args=(view, team), budget=400_000_000)
                    self.assertEqual(list(m.uc.mem_read(view, 17)), v.weak, (club, NAMES[p]))
                    men = tb.seats(own)
                    tb.bench(own, men)
                    pool = tb.tn.POOL[p]
                    self.assertIn(newcomer, men[pool][:tb.tn.NEED_SEATS[pool]], (club, NAMES[p]))
                    cases += 1
                    closed += tb.percentile(v.scale[pool], v.weak[pool]) >= tb.HOLE
                    _restore_ram(type(self))
        finally:
            _restore_ram(type(self))
        self.assertGreater(cases, 10)
        self.assertGreater(closed, cases // 2)

    @unittest.skipUnless(shutil.which("gcc") and shutil.which("ld") and shutil.which("objcopy"), "GNU i386 tools")
    def test_each_guard_has_a_check_that_fails_without_it(self):
        """Review S5: build runtime.c with one guard changed and run the check that covers it: the real build passes
        every check, each mutant fails its own (the kept positions, the person's club, the hole line, the margin)."""
        from tools.team_building import assemble
        tb, code = self.tb, self.code
        decline = tb.decline_after()
        source = (ROOT / "tools/team_building/runtime.c").read_text()
        cpu = [i for i in range(32) if i not in self.user]

        def kept(symbols):
            path, _ = self._kept_paths(self._cpu_club_with_quarterback_room(), symbols)
            return all(how == ("old" if p in tb.KEPT else "new") for p, how in path.items())

        def person(symbols):
            users = {self.teams[i] for i in self.user}
            rec = self._wish_pass(symbols)
            return not users & {w["team"] for w in rec["wishes"]} and bool(users & set(rec["cave"]))

        def hole_line(symbols):
            return all(self._native_order(symbols["tb_order"], c, 0) ==
                       tb.order(self._native_order(0x31DEA0, c, 0), tb.view(self.league, c), 0, decline) for c in cpu)

        def margin(symbols):
            for c in cpu:
                self.m.call(symbols["tb_view"], args=(0x3002000, self.teams[c]), budget=400_000_000)
                if list(self.m.uc.mem_read(0x3002000, 17)) != tb.view(self.league, c).weak:
                    return False
            return True

        mutants = {"kept": (kept, "|| p == 0) return tb_kept", ") return tb_kept"),
                   "person": (person, r"test %eax, %eax\n\tjnz 0x10B40\n\t", ""),
                   "hole line": (hole_line, "#define HOLE (TN_SCALE / 4u)", "#define HOLE (TN_SCALE / 8u)"),
                   "margin": (margin, "#define MARGIN 3u", "#define MARGIN 1u")}
        if not self.user or not self.m.get(0xE6013C):
            del mutants["person"]
        try:
            for name, (check, old, new) in mutants.items():
                with self.subTest(guard=name):
                    self.assertEqual(source.count(old), 1)
                    self.assertTrue(check(code.SYMBOLS), "the real build fails its own check")
                    blobs, _place, symbols, _info = assemble.build(source.replace(old, new))
                    self._install(blobs, symbols)
                    try:
                        self.assertFalse(check(symbols), "the mutant passes")
                    finally:
                        self._install(code.WINDOWS, code.SYMBOLS)
        finally:
            _restore_ram(type(self))


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class SpecialistPolicy(unittest.TestCase):
    """Review S5 (T10): the draft AI's kicker and punter policy with the owner installed, in b780's native worst-case
    draft (the signed franchise, no club with a K or P, five K and five P prospects made outliers; and the same with
    none made outliers). One specialist before display round 5, one K and one P a round after, and the same K and P
    picks round by round as the draft AI and economy without the owner: holes ahead of K and P in the need order
    change neither."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, signed_save
        from mod_editor.core import nfl2k5_draft_ai as ai, nfl2k5_franchise_economy as economy
        signed_save()                                 # skip early without the private franchise
        cls.ai = ai
        cls.economy_only = economy.apply(ai.apply(retail_bytes())[0])[0]
        cls.owner = _tb().apply(cls.economy_only)[0]

    def test_specialists_with_the_owner(self):
        from tests.mod_editor.test_b780_draft_class import _worst_case_draft
        for stars in (5, 0):
            with self.subTest(stars=stars):
                rows, _edges, done = _worst_case_draft(self.owner, seed=1, stars=stars)
                base, _edges, base_done = _worst_case_draft(self.economy_only, seed=1, stars=stars)
                self.assertEqual((done, base_done), (1, 1))
                early = sum(rows[(r, p)] for r in range(4) for p in (1, 2))
                self.assertEqual(early, self.ai.EARLY_SPECIALIST_CAP if stars else 0)
                for round_number in (4, 5, 6):
                    self.assertLessEqual(rows[(round_number, 1)], 1)
                    self.assertLessEqual(rows[(round_number, 2)], 1)
                self.assertEqual({k: v for k, v in rows.items() if v}, {k: v for k, v in base.items() if v})


if __name__ == "__main__":
    unittest.main()
