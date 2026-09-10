"""Gameplay Patches page: gates each executable patch on the source state, composes a BuildPlan."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.gui.gameplay_patches_panel_qt import NEEDS_IMAGE, PATCHES, GameplayPatchesPanel  # noqa: E402
from nfl2k5_throw_tuning_test import _build_progression_xbe as _build_synthetic_xbe   # every gameplay patch reads retail on it  # noqa: E402


class GameplayPatchesPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_three_patches_with_explanations_and_gating(self) -> None:
        self.assertEqual([k for k, _l, _e in PATCHES], ['catch_slider', 'accel_ramp', 'momentum', 'momentum_contact', 'team_names_2026', 'coverage_slider', 'scramble_tuning', 'chop_block_toggle', 'flatter_deep_ball', 'all_stadiums', 'music_shuffle', 'practice_squad_screen', 'abilities', 'qb_spy', 'defensive_try', 'zone_drop_cap', 'draft_ai', 'returner_fix', 'progression', 'team_column', 'kick_rules', 'dynamic_kickoff', 'overtime', 'camera', 'position_row', 'probowl_order', 'penalties', 'uniform_choice', 'kick_laces', 'prospect_names', 'franchise_practice', 'seven_on_seven', 'player_star', 'position_pools', 'depth_roles', 'depth_chart_rows', 'practice_squad', 'xbe_space', 'kickoff_relocated', 'screen_timing', 'music_policy', 'music_unlock', 'music_userlist', 'scorebug', 'scorebug_runtime', 'guardian_cap', 'season_cap', 'depth_locks', 'espn25_plan', 'espn25_rosters', 'momentum_collisions', 'read_option_runtime', 'screen_hooks', 'coverage_trail', 'franchise_edit_player', 'cpu_money_downs', 'accelerated_clock', 'playbook_pair', 'deep_zone_facing', 'deep_zone_bail', 'weekly_prep', 'weekly_prep_cpu', 'weekly_prep_remember', 'franchise_2026_rules', 'senior_bowl', 'guardian_overlay', 'my_career', 'franchise_autosave', 'crib_reclaim', 'modern_naming', 'reserves_16', 'created_teams_extra'])
        for _k, _l, explanation in PATCHES:
            self.assertIn("Retail", explanation)
            self.assertIn("Patch", explanation)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(_build_synthetic_xbe())
            panel = GameplayPatchesPanel()
            try:
                panel.apply_state(mod_build.inspect(source))
                # the throw-tuning synthetic XBE models every cave site but not the camera preset
                # table, the Edit Player row lists, the Pro Bowl tab list, the penalty curves or the held-ball hook, so those toggles must gate
                # themselves off as "foreign" there
                for key, check in panel.checks.items():
                    if key == "depth_roles":          # lives in the playbooks: a bare default.xbe cannot take it
                        self.assertFalse(check.isEnabled(), key)
                        self.assertIn("Full disc required", check.toolTip())
                        continue
                    if key in ("chop_block_toggle", "depth_locks", "music_policy", "music_unlock", "music_userlist", "camera", "kick_rules", "overtime", "position_row", "probowl_order", "penalties", "uniform_choice", "kick_laces", "prospect_names", "dynamic_kickoff", "depth_chart_rows", "franchise_practice", "practice_squad", "player_star"):
                        self.assertFalse(check.isEnabled(), key)
                        self.assertIn("neither retail nor this patch", check.toolTip())
                    elif key in NEEDS_IMAGE:
                        self.assertFalse(check.isEnabled(), key)  # disc-only change on a loose executable
                    else:
                        self.assertTrue(check.isEnabled(), key)
                self.assertFalse(panel.write_button.isEnabled())
                panel.target_field.setText(str(Path(tmp) / "out.xbe"))
                panel.checks["draft_ai"].setChecked(True)
                self.assertTrue(panel.write_button.isEnabled())
                plan = panel.plan()
                self.assertTrue(plan.draft_ai and not plan.catch_slider and not plan.throw)
                self.assertEqual(plan.uniform_choice, "")
                panel.checks["uniform_choice"].setChecked(True)
                self.assertEqual(panel.plan().uniform_choice, "choice")
            finally:
                panel.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
