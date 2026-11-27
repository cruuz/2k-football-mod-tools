"""b81 #43 (coordinator ruling 3): a full build's receipt carries the readback of the FINISHED build.

The combined lead's B build (022022548) took its receipt readback at verify_composed, before the late owner steps;
the receipt read modern injured reserve "retail" on a disc that carries it, because the injured reserve step writes
only its own "injured_reserve" key. mod_build._refresh_readback reads the finished build again after the last step.
Synthetic (no game files).
"""
import inspect as pyinspect
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build  # noqa: E402


class RefreshRule(unittest.TestCase):
    def test_keys_no_step_wrote_take_the_finished_builds_readback(self):
        taken = {"modern_injured_reserve": "retail", "injured_reserve": "retail", "team_building": "retail",
                 "cpu_trades": "retail", "classic_crowd": "retail"}
        receipt = {"result": dict(taken, injured_reserve="modern", cpu_trades="realistic", team_building="left_out")}
        fresh = {"modern_injured_reserve": "applied", "injured_reserve": "applied", "team_building": "retail",
                 "cpu_trades": "applied", "classic_crowd": "applied", "sportscenter_news": "applied"}
        with patch.object(mod_build, "inspect", return_value=fresh) as read:
            mod_build._refresh_readback(receipt, Path("final.iso"), taken, "fast")
        read.assert_called_once_with(Path("final.iso"), screen_timing="fast")
        self.assertEqual(receipt["result"], {
            "modern_injured_reserve": "applied",   # derived from the injured reserve owner: stale before
            "classic_crowd": "applied",            # no step wrote it
            "sportscenter_news": "applied",        # only the fresh readback has it
            "injured_reserve": "modern",           # the step's own key (its mode) stays
            "cpu_trades": "realistic",             # the step's level stays
            "team_building": "left_out",           # a step's "left_out" stays
        })

    def test_the_hires_path_keeps_its_identity_verified_result(self):
        receipt = {"result": {"hires_pack": "applied"}}
        with patch.object(mod_build, "inspect") as read:
            mod_build._refresh_readback(receipt, Path("final.iso"), None)
        read.assert_not_called()
        self.assertEqual(receipt["result"], {"hires_pack": "applied"})


class RefreshPlace(unittest.TestCase):
    def test_the_full_build_refreshes_after_its_last_step_and_before_the_disc_verification(self):
        source = pyinspect.getsource(mod_build._build)
        refresh = source.index("_refresh_readback(receipt, target, readback_taken, plan.screen_timing)")
        for late in ("_apply_team_building(plan, target", "_apply_injured_reserve(plan, target",
                     "_apply_qb_room(plan, target", "_apply_cpu_trades(plan, target",
                     "_apply_sportscenter_news(plan, target", "_apply_modern_numbers(plan, target",
                     "_compact_build_disc(target, _retail_source", '_step("final_checks")'):
            self.assertLess(source.rindex(late), refresh, late)
        self.assertLess(refresh, source.rindex("_verify_finished_game_disc(target, receipt, progress)"))
        self.assertEqual(source.count("readback_taken = copy.deepcopy("), 2)   # both readback points snapshot
        self.assertLess(source.index("readback_taken = None"), source.index("readback_taken = copy.deepcopy("))


if __name__ == "__main__":
    unittest.main()
