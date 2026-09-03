"""Build page: gates toggles on the source's state, composes one BuildPlan."""

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
from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402


class BuildPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_state_gates_toggles_and_plan_reflects_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(_build_synthetic_xbe())
            panel = BuildPanel()
            try:
                panel.apply_state(mod_build.inspect(source))
                self.assertTrue(panel.catch_check.isEnabled())
                self.assertTrue(panel.draft_check.isEnabled())
                self.assertFalse(panel.scorebug_check.isEnabled())      # bare xbe: no mesh
                self.assertFalse(panel.build_button.isEnabled())        # no target, nothing ticked
                panel.target_field.setText(str(Path(tmp) / "out.xbe"))
                panel.throw_check.setChecked(True)
                panel.draft_check.setChecked(True)
                self.assertTrue(panel.build_button.isEnabled())
                plan = panel.plan()
                self.assertTrue(plan.throw and plan.draft_ai and not plan.catch_slider)
                self.assertEqual(plan.max_deep_yards, 80.0)
                # already-applied sources disable the toggle
                patched, _ = __import__("mod_editor.core.nfl2k5_draft_ai", fromlist=["apply"]).apply(source.read_bytes())
                applied = Path(tmp) / "applied.xbe"
                applied.write_bytes(patched)
                panel.apply_state(mod_build.inspect(applied))
                self.assertFalse(panel.draft_check.isEnabled())
                self.assertIn("draft AI: applied", panel.source_status.text())
            finally:
                panel.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()


class PresetButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_presets_tick_only_what_the_source_can_take(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(_build_synthetic_xbe())
            panel = BuildPanel()
            panel.apply_state(mod_build.inspect(source))
            result = panel.apply_preset("softdrink_basic")
            plan = panel.plan()
            self.assertTrue(plan.throw and plan.realistic_flight and plan.catch_slider)
            self.assertFalse(plan.scorebug or plan.accel_ramp or plan.progression or plan.edge_rename
                             or plan.kick_rules or plan.overtime)
            self.assertIn("throw", result["applied"])
            # the synthetic XBE has no FG tables, so the power-only kick fix is skipped, never silently dropped
            self.assertIn("kick_power", result["skipped"])
            self.assertFalse(plan.kick_power)
            result = panel.apply_preset("softdrink_advanced")
            plan = panel.plan()
            self.assertTrue(plan.arc_by_distance)
            # a bare default.xbe has no scorebug mesh: advanced must skip it, not fail
            self.assertIn("scorebug", result["skipped"])
            self.assertIn("position_pools", result["skipped"])
            self.assertIn("season_2026", result["skipped"])
            self.assertFalse(plan.scorebug)
            self.assertIn("not available", panel.preset_note.text())
            result = panel.apply_preset("softdrink_experimental")
            plan = panel.plan()
            # the synthetic XBE has neither the widescreen sites nor a disc: both experimental toggles are skipped, named
            self.assertIn("widescreen", result["skipped"])
            self.assertIn("kickoff_alignment", result["skipped"])
            self.assertFalse(plan.widescreen or plan.kickoff_alignment)
            self.assertTrue(plan.arc_by_distance and plan.accel_ramp)
            self.assertIn("experimental", panel.preset_note.text())
            panel.deleteLater()
            self.app.processEvents()
