"""Beta 81: CPU fake field goals and fake punts (player report via Noah, 2026-11-21: "teams running fake field goal plays
when it isn't 4th down in a field goal situation... CPU should rarely run those, like play calling should be tuned to
also match irl percentages").

Bounded Unicorn replay of the installed Modern 2 owner on the USA executable (tests/nfl2k5_cpu_money_downs_native).
Only the kicker's roster-derived range (0x18B120) and, for the late-trailing states, the second-half points reader
(0x250DD0) are supplied; the dispatcher 0x20B180, the commit code 0x20B6C0..0x20B6F9, the native field-goal and punt
tests and the game's match RNG (0x48B50 / 0x48B90, state 0xE5FCA0) run as installed. Not a played game.

The cause: Modern 2's ``policy`` called the late-trailing helper before its own fourth-down check, so on downs 1 to 3
in the last two minutes of the fourth quarter, trailing by 1 to 3 inside the kicker's range minus 5 yards, the
dispatcher returned the field-goal category while the commit-time field-goal test (native, early-down branch) said no:
the game's fake flag then picked FG Pass / FG Sweep / Fake FG End Zone on 1st, 2nd and 3rd down.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
import struct
import unittest
from unittest import mock

from mod_editor.core import nfl2k5_cpu_money_downs as patch

try:
    from tests.nfl2k5_cpu_money_downs_native import Machine, uc, x86
except ImportError:      # pragma: no cover
    uc = None

FG, PUNT = 0x13, 0x11
KICKS = (FG, PUNT)


def _points_stub(machine, points):
    machine.uc.mem_write(0x250DD0, b"\xb8" + struct.pack("<I", points) + b"\xc3")
    machine.uc.ctl_flush_tb()


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class CpuFakeKickTests(unittest.TestCase):
    RANGE = 45

    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
        cls.retail = retail_xbe()
        cls.payload = patch.apply(cls.retail, level="modern2")[0]
        cls.m = Machine(cls.payload)
        cls.m.supply_fg_range(cls.RANGE)
        _points_stub(cls.m, 14)          # the opponent scored 14 in the second half: the late rule never punts
        cls.native = Machine(cls.retail)
        cls.native.supply_fg_range(cls.RANGE)

    # -- helpers ----------------------------------------------------------------------------------------------------
    def category(self, machine, draw=.5, **state):
        machine.f32(0xBF1244, draw)
        machine.f32(0xBF1484, draw)
        return machine.category(**state)

    def fake_flag(self, category, seed=1, machine=None, **state):
        """The commit's fake flag (ESI at 0x20B6F9) for a kick category record, on the configured state."""
        machine = machine or self.m
        machine.configure(**state)
        record = machine.SOURCE + 0x1E800
        machine.u32(record + 4, category)
        machine.seed(seed)
        machine.run(0x20B6C0, stop_at=0x20B6F9, ebx=record, count=200000)
        return machine.uc.reg_read(x86.UC_X86_REG_ESI)

    def late_states(self):
        """Last two minutes of the fourth quarter, offense trailing by 1 to 3, downs 1 to 3; the 12-second rows are the
        native buzzer window (with no timeout left) inside the kicker's range."""
        # (A 12-second state with a timeout left takes the native Hail Mary / kneel path, which needs a loaded book.)
        clocks = ((110, 2, (62, 75, 85)), (60, 3, (62, 75, 85)), (30, 0, (62, 75, 85)), (12, 0, (75, 85)))
        for down in (1, 2, 3):
            for seconds, timeouts, yards in clocks:
                for margin in (-1, -2, -3):
                    for own_yard in yards:
                        for distance in (3, 7, 10):
                            yield dict(down=down, own_yard=own_yard, distance=distance, score_margin=margin, quarter=4,
                                       seconds=seconds, quarter_seconds=900, timeouts=timeouts)

    def native_field_goal(self, **state):
        """The retail game's own field-goal test (0x20AF80, retail executable) on the same state."""
        self.native.configure(**state)
        self.native.run(0x20AF80, count=200000)
        return self.native.uc.reg_read(x86.UC_X86_REG_EAX)

    # -- downs 1 to 3 ---------------------------------------------------------------------------------------------------
    def test_policy_leaves_downs_1_to_3_to_the_game(self):
        """The late-trailing rule is a fourth-down rule (its own header and the reviewable oracle say so)."""
        for state in self.late_states():
            with self.subTest(**state):
                oracle = patch.decision(level="modern2", kick_range=self.RANGE, **{
                    "down": state["down"], "own_yard": state["own_yard"], "distance": state["distance"],
                    "score_margin": state["score_margin"], "quarter": 4, "seconds": state["seconds"],
                    "quarter_seconds": 900, "timeouts": state["timeouts"]})
                self.assertEqual(oracle, "retail")
                self.assertEqual(self.m.policy(**state), 0)

    def test_no_fake_kick_on_downs_1_to_3(self):
        """Downs 1-3: a kick category only where the retail game kicks too (end-of-half buzzer kick), and never a fake."""
        early_kicks = 0
        for state in self.late_states():
            with self.subTest(**state):
                category = self.category(self.m, **state)
                if category in KICKS:
                    self.assertEqual(category, FG)
                    self.assertTrue(self.native_field_goal(**state),
                                    "a kick before fourth down that the retail game would not line up")
                    self.assertEqual(self.fake_flag(category, **state), 0, "fake kick before fourth down")
                    early_kicks += 1
                for kick in KICKS:          # whatever produced a kick category, the commit never fakes on downs 1-3
                    self.assertEqual(self.fake_flag(kick, seed=7, **state), 0)
        self.assertGreater(early_kicks, 0, "the native buzzer field goal on an early down must survive")

    SHORT_EARLY = tuple(dict(down=down, own_yard=own_yard, distance=distance, score_margin=margin, quarter=quarter,
                             seconds=seconds, quarter_seconds=900, timeouts=timeouts)
                        for down in (1, 2, 3) for distance in (1, 2)
                        for quarter, seconds, margin, timeouts, own_yard in ((4, 60, -2, 3, 80), (2, 12, 0, 0, 97),
                                                                              (3, 600, 0, 3, 70), (4, 600, 7, 3, 30)))

    def forced_draw(self, machine, value):
        """Stub the match RNG's uniform draw 0x48B90 to return ``value`` (0.0 lies below every fake rate)."""
        original = bytes(machine.uc.mem_read(0x48B90, 8))
        code = b"\xd9\xee\xc3" if value == 0 else b"\xd9\xe8\xc3"          # fldz / fld1; ret
        machine.uc.mem_write(0x48B90, code)
        machine.uc.ctl_flush_tb()
        return original

    def restore_draw(self, machine, original):
        machine.uc.mem_write(0x48B90, original)
        machine.uc.ctl_flush_tb()

    def early_short_fakes(self, machine):
        original = self.forced_draw(machine, 0)
        try:
            return [(state, kick) for state in self.SHORT_EARLY for kick in KICKS
                    if self.fake_flag(kick, machine=machine, **state)]
        finally:
            self.restore_draw(machine, original)

    def test_no_fake_on_downs_1_to_3_even_at_1_or_2_yards_with_the_lowest_draw(self):
        """Review 11/22 (finding 1): 1 and 2 yards to go before fourth down, with the RNG forced to 0.0, never fake. The
        reviewer's mutant (the gate's down check 0x20B26B, 6 bytes, made NOPs) must fail this check."""
        self.assertEqual(self.early_short_fakes(self.m), [])
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        mutant = bytearray(self.payload)
        at = rdata.offset_of(self.payload, 0x20B26B)
        self.assertEqual(bytes(mutant[at:at + 6]), bytes.fromhex("837804047535"))   # cmp [eax+4],4; jne fake_done
        mutant[at:at + 6] = b"\x90" * 6
        machine = Machine(bytes(mutant))
        machine.supply_fg_range(self.RANGE)
        _points_stub(machine, 14)
        self.assertEqual(len(self.early_short_fakes(machine)), len(self.SHORT_EARLY) * len(KICKS))

    # -- fourth down ----------------------------------------------------------------------------------------------------
    def rate(self, category, trials, **state):
        return sum(self.fake_flag(category, seed=seed, **state) for seed in range(1, trials + 1))

    def test_fourth_down_fakes_only_in_short_yardage(self):
        for category, own_yard in ((PUNT, 30), (FG, 75)):
            for distance in (3, 5, 9):
                with self.subTest(category=category, distance=distance):
                    self.assertEqual(self.rate(category, 150, down=4, own_yard=own_yard, distance=distance,
                                               quarter=3, seconds=600, quarter_seconds=900), 0)

    def test_fourth_and_short_fake_rates_match_the_league(self):
        """nflverse 2021-2025 regular season, 4th and 1-2: fake punts 45 of 1,210 punt-formation snaps (3.7%), fake
        field goals 1 of 453 (all distances 12 of 5,364, 0.22%). Binomial bounds well outside 4 standard deviations."""
        punts = self.rate(PUNT, 3000, down=4, own_yard=30, distance=1, quarter=3, seconds=600, quarter_seconds=900)
        self.assertTrue(65 <= punts <= 160, punts)              # expected 111
        kicks = self.rate(FG, 3000, down=4, own_yard=75, distance=2, quarter=3, seconds=600, quarter_seconds=900)
        self.assertTrue(0 <= kicks <= 20, kicks)                 # expected 6.6
        self.assertGreater(kicks + punts, 0)
        self.assertAlmostEqual(patch.FAKE_RATES["punt"], 0.037, places=3)
        self.assertAlmostEqual(patch.FAKE_RATES["field_goal"], 0.0022, places=4)

    def lottery(self, draw, **state):
        """Enter the dispatcher's native fake lottery (0x20B258, reached after the field-goal, punt, Hail Mary and kneel
        tests all said no) with its frame: [esp] the cached draw, [esp+4] scratch, then the return address."""
        self.m.configure(**state)
        self.m.seed(1)
        self.m.f32(self.m.STACK - 8, draw)
        self.m.u32(self.m.STACK - 4, 0)
        self.m.run(0x20B258, esp=self.m.STACK - 8, count=200000)
        return self.m.uc.reg_read(x86.UC_X86_REG_EAX)

    def test_native_time_to_spare_lottery_no_longer_lines_up_a_kick(self):
        """Retail: on a fourth down the game had decided to go for, with time to spare and a cached draw above 0.95, the
        dispatcher returned the field-goal or punt category and the commit re-test faked it (5% of those downs, any
        distance). That block now answers the ordinary category, as it does for a draw of 0.5."""
        for own_yard, distance in ((50, 1), (50, 9), (62, 4), (80, 12)):
            state = dict(down=4, own_yard=own_yard, distance=distance, quarter=3, seconds=600, quarter_seconds=900)
            with self.subTest(**state):
                ordinary = self.lottery(.5, **state)
                self.assertNotIn(ordinary, KICKS)
                self.assertEqual(self.lottery(.99, **state), ordinary)

    # -- two-point tries ------------------------------------------------------------------------------------------------
    def try_category(self, draw):
        self.m.configure(down=1, own_yard=97, distance=3, quarter=3, seconds=600, quarter_seconds=900, phase=3)
        self.m.f32(0xBF1244, draw)
        self.m.f32(0xBF1484, draw)
        self.m.seed(1)
        self.m.run(0x209FE0, ecx=self.m.OFF, count=100000)
        return self.m.uc.reg_read(x86.UC_X86_REG_EAX)

    def test_two_point_kick_formation_rate(self):
        """nflverse 2020-2025: 14 of 794 two-point tries came from the kick formation (1.8%); retail used 5%."""
        self.assertNotEqual(self.try_category(.97), FG)
        self.assertNotEqual(self.try_category(.98), FG)
        self.assertEqual(self.try_category(.99), FG)
        self.assertAlmostEqual(patch.FAKE_RATES["two_point"], 0.0176, places=4)


class V09UpdateCarriesCpuDecisionsTests(unittest.TestCase):
    """Review 11/22 (finding 3): a player who updates the released v0.9 disc in the Studio gets the fix too."""

    def test_every_v09_update_brings_cpu_decisions_to_the_current_template(self):
        import tempfile
        from mod_editor.core import mod_build
        disc = Path(os.environ.get("NFL2K5_V09_XISO", "") or "missing")
        if not disc.is_file():
            self.skipTest("the released v0.9 disc is absent")
        source = mod_build._xbe_bytes(disc)
        self.assertEqual((patch.read_settings(source) or {}).get("variant"), "b778_late")
        seen = []
        original = patch.apply

        def keep(payload, **kwargs):
            result = original(payload, **kwargs)
            seen.append(result[0])
            return result
        release = mod_build._v09_reference(disc, source)
        with tempfile.TemporaryDirectory() as folder:
            plan = mod_build.v09_disc_update(str(disc), str(Path(folder) / "copy.iso"), backfield_cards=True)
            with mock.patch.object(patch, "apply", new=keep), \
                    mock.patch("mod_editor.core.modpack.hash_file", return_value=release["image_sha256"]):
                receipt = mod_build._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
        self.assertIn("cpu_decisions", receipt["v09_update"])
        self.assertEqual(len(seen), 1)
        self.assertEqual(patch.read_settings(seen[0])["variant"], patch.CURRENT_LATE)
        self.assertEqual(patch.status(seen[0]), "applied")


class CpuDecisionsDiscEditTests(unittest.TestCase):
    """The Studio's single-setting update of a built disc (CLI edit-cpu-decisions), as edit-gadget-play and edit-sim-qb."""

    def test_plan_cli_and_preflight(self):
        from mod_editor.core import mod_build as build
        from tools import nfl2k5_modpack as cli
        plan = build.cpu_decisions_disc_edit("built.iso", "copy.iso")
        self.assertIs(type(plan), build._InstalledCpuDecisionsEdit)
        self.assertEqual(plan.cpu_money_downs, "modern2")
        self.assertTrue(build._only_cpu_decisions_changes(plan))
        self.assertFalse(build._only_cpu_decisions_changes(build.BuildPlan("built.iso", "copy.iso", cpu_money_downs="modern2")))
        with mock.patch.object(build, "build", return_value={}) as run, mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(cli.main(["edit-cpu-decisions", "--source", "a.iso", "--out", "b.iso", "--json"]), 0)
        self.assertIs(type(run.call_args.args[0]), build._InstalledCpuDecisionsEdit)
        disc = Path(os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC", "") or "missing")
        if not disc.is_file():
            self.skipTest("the reviewed private standard disc is absent")
        target = Path(__file__).resolve().parents[2] / "never-written-cpu-decisions.xiso.iso"
        receipt = build.preflight_plan(build.cpu_decisions_disc_edit(str(disc), str(target)))
        self.assertFalse(target.exists())
        update = receipt["cpu_decisions_source_update"]
        self.assertIn(update["from_variant"], patch.LATE_VARIANTS)
        self.assertNotEqual(update["source_sha256"], update["result_sha256"])


if __name__ == "__main__":
    unittest.main()
